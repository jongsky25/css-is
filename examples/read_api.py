"""Standalone Python 3.11+ read client; no Office Connect imports or extra packages."""
import argparse
import json
import re
from http.client import HTTPException
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode, urlsplit
from urllib.request import HTTPRedirectHandler, Request, build_opener


class ApiFailure(Exception):
    pass


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        # Never forward the user's session to a redirect destination.
        return None


class ReadClient:
    def __init__(self, base_url, session, cookie_name='css_session', timeout=15):
        parsed = urlsplit(base_url)
        if parsed.username or parsed.password or parsed.query or parsed.fragment:
            raise ValueError('Choose an API base URL without credentials, query or fragment.')
        if parsed.scheme != 'https' and not (parsed.scheme == 'http' and parsed.hostname in ('127.0.0.1', 'localhost', '::1')):
            raise ValueError('Use HTTPS, or HTTP on loopback for a local test.')
        if not parsed.hostname or not parsed.path.rstrip('/').endswith('/api/v1'):
            raise ValueError('The base URL must end with /api/v1.')
        if not re.fullmatch(r'[A-Za-z0-9._~-]{1,4096}',session):
            raise ValueError('The session value is invalid.')
        if not re.fullmatch(r'[A-Za-z0-9_-]+',cookie_name):
            raise ValueError('The cookie name is invalid.')
        self.base_url = base_url.rstrip('/')
        self.session, self.cookie_name, self.timeout = session, cookie_name, timeout
        self.opener = build_opener(NoRedirect())

    def get(self, path):
        if not path.startswith('/') or path.startswith('//') or '\\' in path or '..' in urlsplit(path).path.split('/'):
            raise ValueError('Choose an API-relative read path.')
        if path == '/api/v1' or path.startswith('/api/v1/'):
            path = path[len('/api/v1'):] or '/'
        request = Request(self.base_url + path,
                          headers={'Accept': 'application/json', 'Cookie': self.cookie_name + '=' + self.session}, method='GET')
        try:
            with self.opener.open(request, timeout=self.timeout) as response:
                if response.headers.get_content_type() != 'application/json':
                    raise ApiFailure('The server did not return a JSON API response.')
                payload = response.read(4 * 1024 * 1024 + 1)
                if len(payload) > 4 * 1024 * 1024:
                    raise ApiFailure('The API response exceeds the client size limit.')
                return json.loads(payload)
        except HTTPError as exc:
            # Do not print cookies, response bodies, login HTML or internal details.
            raise ApiFailure(f'API read returned HTTP {exc.code}.') from None
        except (URLError, OSError, TimeoutError, UnicodeError, HTTPException, json.JSONDecodeError):
            raise ApiFailure('The API read could not be completed.') from None

    def pages(self, resource='documents', limit=25):
        if resource not in ('documents', 'work-items') or not 1 <= limit <= 100:
            raise ValueError('Choose documents or work-items and a page size from 1 to 100.')
        before, seen = None, set()
        while True:
            query = {'limit': limit}
            if before is not None:
                query['before'] = before
            page = self.get('/' + resource + '?' + urlencode(query))
            if not isinstance(page,dict) or not isinstance(page.get('data'),list) or not isinstance(page.get('page'),dict) or 'next_before' not in page['page']:
                raise ApiFailure('The API returned an invalid page response.')
            previous = before
            before = page['page']['next_before']
            if before is not None and (not isinstance(before,str) or not before.isdigit() or before in seen or (previous is not None and int(before)>=int(previous))):
                raise ApiFailure('The API returned a non-progressing page cursor.')
            yield page['data']
            if before is None:
                return
            seen.add(before)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--base-url', required=True)
    parser.add_argument('--session-file', required=True, help='Local private file containing an existing user session, never a password')
    parser.add_argument('--cookie-name', default='css_session')
    parser.add_argument('--resource', choices=('documents', 'work-items'), default='documents')
    options = parser.parse_args()
    try:
        session = Path(options.session_file).read_text().strip()
        client = ReadClient(options.base_url, session, options.cookie_name)
        for page in client.pages(options.resource):
            for item in page:
                print(json.dumps(item, ensure_ascii=False))
    except (ApiFailure, ValueError, OSError) as exc:
        # File errors can contain local paths, so only print public error text.
        parser.exit(1, ('Could not read the local session file.' if isinstance(exc, OSError) else str(exc)) + '\n')


if __name__ == '__main__':
    main()
