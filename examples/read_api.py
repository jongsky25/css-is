"""Standalone Python 3.11+ API clients; the command line performs reads only."""
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
        # Never forward a session or read credential to a redirect destination.
        return None


class ReadClient:
    def __init__(self, base_url, session=None, cookie_name='css_session', timeout=15, *, credential=None):
        parsed = urlsplit(base_url)
        if parsed.username or parsed.password or parsed.query or parsed.fragment:
            raise ValueError('Choose an API base URL without credentials, query or fragment.')
        if parsed.scheme != 'https' and not (parsed.scheme == 'http' and parsed.hostname in ('127.0.0.1', 'localhost', '::1')):
            raise ValueError('Use HTTPS, or HTTP on loopback for a local test.')
        if not parsed.hostname or not parsed.path.rstrip('/').endswith('/api/v1'):
            raise ValueError('The base URL must end with /api/v1.')
        if (session is None)==(credential is None):
            raise ValueError('Supply one session or one read credential.')
        if credential is not None and (not isinstance(credential,str) or not re.fullmatch(r'oc_read_[0-9a-f]{32}\.[0-9a-f]{64}',credential)):
            raise ValueError('The read credential is invalid.')
        if session is not None and not re.fullmatch(r'[A-Za-z0-9._~-]{1,4096}',session):
            raise ValueError('The session value is invalid.')
        if not re.fullmatch(r'[A-Za-z0-9_-]+',cookie_name):
            raise ValueError('The cookie name is invalid.')
        self.base_url = base_url.rstrip('/')
        self.session, self.cookie_name, self.timeout = session, cookie_name, timeout
        self.credential = credential
        self.opener = build_opener(NoRedirect())

    def get(self, path):
        return self._request(path)

    def _request(self, path, *, data=None, headers=None):
        if self.credential is not None and data is not None:
            raise ValueError('Read credentials cannot perform writes.')
        if not path.startswith('/') or path.startswith('//') or '\\' in path or '..' in urlsplit(path).path.split('/'):
            raise ValueError('Choose an API-relative read path.')
        if path == '/api/v1' or path.startswith('/api/v1/'):
            path = path[len('/api/v1'):] or '/'
        identity = {'Authorization':'Bearer ' + self.credential} if self.credential is not None else {'Cookie':self.cookie_name + '=' + self.session}
        request = Request(self.base_url + path,
                          headers={'Accept': 'application/json', **identity,
                                   **(headers or {})}, data=data, method='POST' if data is not None else 'GET')
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
            recovery = ' Check the saved operation key before retrying.' if data is not None else ''
            raise ApiFailure(f'API request returned HTTP {exc.code}.' + recovery) from None
        except (URLError, OSError, TimeoutError, UnicodeError, HTTPException, json.JSONDecodeError):
            raise ApiFailure('The API request could not be completed. Check the operation result before retrying a write.') from None

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


class TaskClient(ReadClient):
    """Explicit acknowledgement/submission. Never generates keys or retries writes.

    Save a fresh UUID v4 key and the complete exact request locally before calling;
    after a lost response, look up that key or resubmit that identical request.
    """
    def operation(self, operation_id):
        self._operation_key(operation_id)
        return self.get('/operations/' + operation_id)

    @staticmethod
    def _operation_key(value):
        if not isinstance(value, str) or not re.fullmatch(
                r'[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}', value):
            raise ValueError('Supply the saved UUID v4 operation key.')

    def acknowledge(self, work_item_id, task_id, *, revision, reason, operation_id):
        return self._task_action(work_item_id, task_id, action='acknowledge', revision=revision,
                                 reason=reason, operation_id=operation_id)

    def submit(self, work_item_id, task_id, *, revision, reason, submission, operation_id):
        if not isinstance(submission, str) or not submission.strip() or len(submission) > 8000:
            raise ValueError('Supply output or evidence of at most 8000 characters.')
        try:
            submission.encode('utf-8')
        except UnicodeError:
            raise ValueError('Supply valid UTF-8 output or evidence.') from None
        return self._task_action(work_item_id, task_id, action='submit', revision=revision,
                                 reason=reason, operation_id=operation_id, submission=submission)

    def _task_action(self, work_item_id, task_id, *, action, revision, reason, operation_id, submission=None):
        self._operation_key(operation_id)
        for identifier in (work_item_id, task_id):
            if (not isinstance(identifier, str) or not re.fullmatch(r'[1-9][0-9]{0,18}', identifier)
                    or int(identifier) > 9223372036854775807):
                raise ValueError('Supply decimal string resource identifiers.')
        if type(revision) is not int or not 1 <= revision < 9223372036854775807:
            raise ValueError('Supply the exact current task revision.')
        if not isinstance(reason, str) or not reason.strip() or len(reason) > 2000:
            raise ValueError('Supply a reason of at most 2000 characters.')
        try:
            reason.encode('utf-8')
        except UnicodeError:
            raise ValueError('Supply a valid UTF-8 reason.') from None
        data = {'revision': revision, 'reason': reason}
        if submission is not None:
            data['submission'] = submission
        context = self.get('/write-context')
        token = context.get('csrf_token') if isinstance(context, dict) else None
        if not isinstance(token, str) or not re.fullmatch(r'[0-9a-f]{64}', token):
            raise ApiFailure('The API returned an invalid write context.')
        parsed = urlsplit(self.base_url)
        return self._request(f'/work-items/{work_item_id}/tasks/{task_id}/{action}',
            data=json.dumps(data, ensure_ascii=False, separators=(',', ':')).encode(),
            headers={'Origin': f'{parsed.scheme}://{parsed.netloc}', 'X-CSRF-Token': token,
                     'Idempotency-Key': operation_id, 'Content-Type': 'application/json'})


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--base-url', required=True)
    identity = parser.add_mutually_exclusive_group(required=True)
    identity.add_argument('--session-file', help='Local private file containing an existing user session, never a password')
    identity.add_argument('--credential-file', help='Local private file containing a delegated read credential')
    parser.add_argument('--cookie-name', default='css_session')
    parser.add_argument('--resource', choices=('documents', 'work-items'), default='documents')
    options = parser.parse_args()
    try:
        value = Path(options.credential_file or options.session_file).read_text().strip()
        client = (ReadClient(options.base_url,credential=value) if options.credential_file
                  else ReadClient(options.base_url,value,options.cookie_name))
        for page in client.pages(options.resource):
            for item in page:
                print(json.dumps(item, ensure_ascii=False))
    except (ApiFailure, ValueError, OSError) as exc:
        # File errors can contain local paths, so only print public error text.
        parser.exit(1, ('Could not read the local credential/session file.' if isinstance(exc, OSError) else str(exc)) + '\n')


if __name__ == '__main__':
    main()
