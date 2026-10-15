"""Documents over the existing travel/Workspace and mail Apps Script connections.

Never retry a POST. Apps Script ContentService redirects are followed as GETs to
Google's reply host, without forwarding the signed body or secret.
"""
import os
from urllib.parse import urlparse
import httpx
import gdocs_relay

MAX_RESPONSE = 1024 * 1024


class Unconfigured(ValueError):
    pass


def _request(client,method,url,**kwargs):
    with client.stream(method,url,**kwargs) as response:
        content=bytearray()
        for chunk in response.iter_bytes():
            content.extend(chunk)
            if len(content)>MAX_RESPONSE:
                raise ValueError('Workspace response exceeded the metadata limit.')
        return httpx.Response(response.status_code,headers=response.headers,
                              content=bytes(content),request=response.request)


class WorkspaceRelay:
    def call(self, action, payload, operation_id):
        mail = action == 'dispatch' or (action == 'status' and payload.get('kind') == 'dispatch')
        prefix = 'CSS_MAIL_RELAY' if mail else 'CSS_DOCS_RELAY'
        endpoint, secret = os.environ.get(prefix+'_URL',''), os.environ.get(prefix+'_SECRET','')
        if not endpoint or not secret:
            raise Unconfigured('The existing '+('mail' if mail else 'travel documents')+' relay is not configured in this runtime.')
        parsed = urlparse(endpoint)
        if parsed.scheme != 'https' or parsed.hostname != 'script.google.com' or parsed.username or parsed.port not in (None,443) or not parsed.path.endswith('/exec'):
            raise ValueError('Use the existing Google Apps Script /exec deployment URL.')
        request = {**payload, 'action':'document_'+action, 'operation_id':operation_id}
        envelope = gdocs_relay.envelope(request, secret)
        with httpx.Client(timeout=httpx.Timeout(90,connect=10),follow_redirects=False) as client:
            response = _request(client,"POST",endpoint,json=envelope)
            # ContentService's 302/303 response is a result location, not another
            # execution. Never repeat the authenticated POST, including on timeout.
            for _ in range(3):
                if response.status_code not in (302,303):
                    break
                location=response.headers.get('location','')
                dest=urlparse(location)
                if dest.scheme!='https' or dest.hostname!='script.googleusercontent.com' or dest.username or dest.port not in (None,443):
                    raise ValueError('Unexpected Workspace redirect; the operation needs reconciliation.')
                response=_request(client,"GET",location)
            response.raise_for_status()
            if len(response.content)>MAX_RESPONSE:
                raise ValueError('Workspace response exceeded the metadata limit.')
            try:
                result=response.json()
            except ValueError:
                raise ValueError('Workspace returned no confirmed JSON receipt. Check the operation status before retrying.') from None
        if not isinstance(result,dict) or result.get('operation_id')!=operation_id:
            raise ValueError('The deployed relay lacks document operations or returned a mismatched receipt. Update the existing deployment.')
        if result.get('ok') is False:
            # Never echo arbitrary provider errors or document text into the UI.
            code=result.get('error','unconfirmed')
            messages={'version_changed':'The source file changed. Review its current version.',
                      'unsupported_format':'This operation does not support that file format.',
                      'signature_marker':'Use one signature marker on a paragraph of its own in the Google Doc.',
                      'sender_mismatch':'The configured sender is not the relay mailbox or an authorized alias.',
                      'not_found':'No stored service receipt was found. Do not assume no external effect.',
                      'operation_conflict':'This operation ID belongs to a different request.',
                      'input_too_large':'The file exceeds the configured processing limit.',
                      'not_configured':'Set the document root folder in the existing Apps Script project.',
                      'extraction_failed':'The source could not be read. Manual entry remains available.'}
            raise ValueError(messages.get(code,'The Workspace operation could not be confirmed. Check the relay execution and operation receipt.'))
        return result
