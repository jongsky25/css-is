"""Presentation snapshots retain every registry boundary and refuse truncation."""
import pytest
import documents_dashboard as dashboard
import documents_grid as grid
import documents_permissions as permissions
from tests.test_documents import registry
from tests.test_document_registry_pagination import mixed,seed_many,legacy_visible


def test_presentation_all_queues_current_authority_and_read_only_snapshot(mixed):
    c,users,_,_,_=mixed
    for queue in sorted(grid.QUEUES):
        for user in users:
            scope={'queue':queue,'q':'Needle'}
            if queue=='instruction' and not permissions.director(c,user):
                with pytest.raises(permissions.Denied):dashboard.report(c,user,scope,presentation=True)
                continue
            before=c.total_changes
            result=dashboard.report(c,user,scope,presentation=True)
            expected=legacy_visible(c,user,'' if queue=='instruction' else 'Needle',queue)
            assert result['total']==len(expected) and c.total_changes==before
            assert result['queue_label']==dict(dashboard.QUEUE_LABELS)[queue]
            for dimension in ('workflow','deadlines','leads'):
                assert sum(row['count'] for row in result[dimension])==len(expected)
            baseline=dashboard.report(c,user,scope)
            assert {key:value for key,value in result.items() if key!='as_of'}=={
                key:value for key,value in baseline.items() if key!='as_of'}
            assert result['as_of']
    c.execute('UPDATE admin_user SET active=0 WHERE id=?',(users[-1]['id'],));c.commit()
    with pytest.raises(permissions.Denied):dashboard.report(c,users[-1],{},presentation=True)


def test_presentation_lead_limit_is_complete_or_refused_and_dashboard_unaffected(registry,monkeypatch):
    c,u,unit,_=registry
    ids=seed_many(c,u[0],unit,3,subject='Meeting report')
    for index,identifier in enumerate(ids):
        c.execute('UPDATE document SET lead_id=? WHERE id=?',(u[index]['id'],identifier))
    c.commit();monkeypatch.setattr(dashboard,'MAX_PRESENTATION_LEADS',2)
    with pytest.raises(ValueError,match='Narrow the dashboard queue or search'):
        dashboard.report(c,u[4],{},presentation=True)
    assert len(dashboard.report(c,u[4],{})['leads'])==3
    c.execute("UPDATE document SET visibility='restricted' WHERE id=?",(ids[-1],));c.commit()
    result=dashboard.report(c,u[4],{},presentation=True)
    assert result['total']==2 and len(result['leads'])==2
    assert str(u[2]['id']) not in {row['key'] for row in result['leads']}
    assert dashboard.report(c,u[4],{'q':'No matching report'},presentation=True)['total']==0
    with pytest.raises(ValueError):dashboard.report(c,u[4],{'queue':'bad'},presentation=True)
    with pytest.raises(ValueError):dashboard.report(c,u[4],{'q':'x'*121},presentation=True)
