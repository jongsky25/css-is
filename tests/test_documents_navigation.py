"""Queue context is bounded navigation, never an access grant."""
from urllib.parse import parse_qs, urlsplit, urlencode
from html import unescape
import re
import pytest
import documents_navigation as nav
import documents as docs
from tests.test_document_guidance_routes import detail_record

@pytest.mark.parametrize('value', ['https://evil.test/documents','//evil.test/documents', '/%64ocuments', '/documents/1', '/documents?q=%0Aevil', '/documents\n', '/documents?q='+'a'*4096, '/documents?'+'&'.join('q=x' for _ in range(33))])
def test_invalid_context_rejected(value):
    assert nav.safe_return(value) == ''


def test_context_is_normalized_and_targets_preserved():
    origin='/documents?q=one%26two&page=2&evil=1#document-row-3'
    result=nav.record_url('/documents/3?file=4#requests',origin)
    parts=urlsplit(result)
    assert parts.fragment=='requests'
    assert parse_qs(parts.query)=={'file':['4'],'return_to':['/documents?q=one%26two&page=2#document-row-3']}
    assert nav.record_url('/work/3',origin)=='/work/3'
    assert nav.record_url('https://evil.test/documents/3',origin)=='https://evil.test/documents/3'


def test_queue_detail_save_and_revocation(detail_record,viewer,admin):
    conn,user,doc,url=detail_record
    queue=viewer.get('/documents?q=Guided')
    link=next(unescape(x) for x in re.findall(r'href="([^"]+)"',queue.text) if x.startswith(url+'?return_to='))
    origin=parse_qs(urlsplit(link).query)['return_to'][0]
    assert origin==f'/documents?q=Guided#document-row-{doc["id"]}'
    page=viewer.get(link)
    assert 'Back to register' in page.text
    assert f'href="{origin}"' in page.text
    action=next(unescape(x) for x in re.findall(r'action="([^"]+)"',page.text) if x.startswith(url+'/verify?'))
    csrf=re.search(r'name="csrf" value="([a-f0-9]+)"',page.text)[1]
    result=viewer.post(action,data={'csrf':csrf,'revision':doc['revision'],'verification':'verified','reason':'Checked again'},follow_redirects=False)
    assert result.status_code==303, result.text
    assert parse_qs(urlsplit(result.headers['location']).query)['return_to']==[origin]
    assert docs.raw(conn,doc['id'])['revision']>doc['revision']
    conn.execute("UPDATE document SET visibility='restricted' WHERE id=?",(doc['id'],));conn.commit()
    assert admin.get(link).status_code==404


def test_unsafe_return_not_rendered(detail_record,viewer):
    _,_,_,url=detail_record
    page=viewer.get(url+'?'+urlencode({'return_to':'https://evil.test/documents'}))
    assert page.status_code==200
    assert 'evil.test' not in page.text
    assert 'doc-queue-return' not in page.text
