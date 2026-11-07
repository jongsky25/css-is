"""Next review respects the full Inbox scope without taking another reviewer's claim."""
from urllib.parse import urlencode, urlsplit, parse_qs
import pytest
import documents as docs
import documents_intake as intake
import documents_permissions as permissions
from tests.test_documents import registry
from tests.test_documents_intake import seed, fields
from tests.test_document_intake_friction import intake_http
from tests.test_documents_routes import token


def test_next_matches_beyond_first_page_and_skips_other_claims(registry):
    conn,users,_,_=registry
    seed(registry,65)
    conn.execute("UPDATE document_intake SET original_name='Target.pdf',claimed_by=?,claim_until='2099-01-01' WHERE id>30",(users[0]['id'],))
    conn.execute("UPDATE document_intake SET claimed_by=NULL WHERE id=64")
    conn.execute("UPDATE document_intake SET claimed_by=?,claim_until=NULL WHERE id=65",(users[0]['id'],))
    conn.commit()
    assert intake.next_review(conn,users[1],query='Target')['id']==64
    assert intake.next_review(conn,users[1],review='others',query='Target') is None
    assert intake.next_review(conn,users[1],review='mine',query='Target') is None
    assert conn.execute('SELECT MAX(revision) FROM document_intake').fetchone()[0]==1
    with pytest.raises(permissions.Denied):intake.next_review(conn,users[4])
    intake.claim(conn,users[1],64,1)
    assert intake.next_review(conn,users[1],review='mine',query='Target')['id']==64
    assert intake.next_review(conn,users[1],review='ready',query='Target')['id']==65


def register_first(admin,conn,user,origin):
    csrf=token(admin.get('/documents/intake'))
    item=intake.claim(conn,user,1,1)
    return admin.post('/documents/intake/1?'+urlencode({'return_to':origin}),
        data={**fields(),'csrf':csrf,'revision':item['revision'],'action':'register_next'},follow_redirects=False)


@pytest.mark.parametrize('origin,expected',[
    ('/documents/intake?state=waiting&review=ready&q=Letter', '/documents/intake/2'),
    ('/documents/intake?state=waiting&review=ready&q=Letter+1', '/documents/intake'),
    ('/documents/intake?state=waiting&review=mine&q=Letter', '/documents/intake'),
    ('https://evil.test/documents/intake?q=nomatch', '/documents/intake/2'),
])
def test_register_next_uses_scope_and_never_external_redirect(intake_http,admin,origin,expected):
    conn,user,_=intake_http
    response=register_first(admin,conn,user,origin)
    assert response.status_code==303,response.text
    target=urlsplit(response.headers['location'])
    assert target.path==expected and not target.netloc
    assert conn.execute('SELECT COUNT(*) FROM document').fetchone()[0]==1
    assert 'evil.test' not in response.headers['location']
    if expected=='/documents/intake':
        params=parse_qs(target.query)
        assert params['registered']==['1']
        assert intake.get(conn,user,2)['claimed_by'] is None
        assert params.get('q')==parse_qs(urlsplit(origin).query).get('q')
    else:
        assert intake.get(conn,user,2)['claimed_by']==user['id']


def test_attention_scope_and_conflicting_next_claim_keep_registration(intake_http,admin,monkeypatch):
    conn,user,_=intake_http
    conn.execute("UPDATE document_intake SET state='attention' WHERE id=2");conn.commit()
    assert intake.next_review(conn,user,state='attention')['id']==2
    original=intake.claim
    def concurrent_claim(c,u,item_id,revision):
        if item_id==2:raise docs.Conflict('Another reviewer claimed this entry.')
        return original(c,u,item_id,revision)
    monkeypatch.setattr(intake,'claim',concurrent_claim)
    response=register_first(admin,conn,user,'/documents/intake?state=attention&q=Letter')
    assert response.status_code==303
    assert parse_qs(urlsplit(response.headers['location']).query)=={'state':['attention'],'review':['all'],'q':['Letter'],'registered':['1']}
    assert conn.execute('SELECT COUNT(*) FROM document').fetchone()[0]==1
    assert intake.get(conn,user,1)['state']=='registered'
