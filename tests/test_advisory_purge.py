"""Owner decision (Nov 25, 2026): delete the old-editor trial advisories; keep Slides advisories and audit history."""
import sqlite3
import uuid

import pytest

import advisory_purge
import advisory_workflow as aw
import storage as st
from tests.test_advisory_distribution import approved, issue, act  # noqa: F401  (fixtures/helpers)
from tests.test_advisory_review import cycle  # noqa: F401
from tests.test_advisory_workflow import drafts  # noqa: F401


def counts(c):
    return {t: c.execute(f'SELECT COUNT(*) FROM {t}').fetchone()[0] for t in (
        'advisory_record', 'advisory_revision', 'advisory_artifact', 'advisory_issue', 'advisory_delivery',
        'advisory_review_packet', 'advisory_decision', 'event_advisory')}


def test_purge_removes_an_issued_trial_and_keeps_history_and_slides_advisories(approved):
    data, r = approved
    c, u, unit, _, ev, _ = data
    r = issue(c, u[0], r)
    slides_doc = c.execute('SELECT document_id FROM advisory_record WHERE id=?', (r['id'],)).fetchone()[0]
    before = counts(c)
    assert before['advisory_issue'] == 1 and before['advisory_delivery'] >= 1 and before['event_advisory'] == 1
    preview = advisory_purge.preview(c)
    assert [x['id'] for x in preview['records']] == [r['id']] and preview['issued'] == 1
    done = advisory_purge.purge(c, u[0], reason='Trial cleanup')
    assert done['records'] == 1 and done['issues'] == 1 and done['posters'] == 1
    after = counts(c)
    assert all(v == 0 for v in after.values()), after
    # Audit history is kept and says why; the Documents record is archived.
    doc = c.execute('SELECT archived_at FROM document WHERE id=?', (slides_doc,)).fetchone()
    assert doc[0]
    assert c.execute("SELECT COUNT(*) FROM document_event WHERE document_id=? AND action='advisory_trial_removed'",
                     (slides_doc,)).fetchone()[0] == 1
    # Unsent emails were stopped, not deleted.
    assert c.execute("SELECT COUNT(*) FROM document_job WHERE kind='dispatch' AND state='pending'").fetchone()[0] == 0
    # The append-only protection is back on.
    names = {r[0] for r in c.execute("SELECT name FROM sqlite_master WHERE type='trigger' AND name LIKE 'advisory_%_no_%'")}
    assert {'advisory_revision_no_delete', 'advisory_issue_no_delete', 'advisory_artifact_no_update'} <= names
    assert advisory_purge.preview(c)['total'] == 0
    # The activity's public page no longer shows the old poster.
    import activity_advisory as aa
    assert aa.public_summary(c, ev['id']) is None


def test_purge_keeps_google_slides_advisories(drafts):
    c, users, unit, _, ev, _ = drafts
    import advisory_new as new_flow
    import advisory_slides as slides
    st.add_rp(c, 'Author', True, unit, email='author@doh.gov.ph')
    form = {'kind': 'general', 'operation_key': str(uuid.uuid4()), 'title': 'Slides notice', 'dates': '', 'venue': '',
            'message': '', 'attention': '', 'contact': '', 'link': '', 'audience': 'internal', 'external': '',
            'variant': '1', 'unit_id': str(unit)}
    aid = new_flow.start(c, users[0], form, variants=[{'variant': 1}])
    new_flow.make_file(c, users[0], aid, create=lambda **k: slides.Outcome(True, value=slides.Created(
        id='SLIDESKEEP00000000000001', url='u', name='n', version='1')))
    assert advisory_purge.preview(c)['total'] == 0
    advisory_purge.purge(c, users[0], reason='nothing to do')
    assert c.execute('SELECT COUNT(*) FROM advisory_record WHERE id=?', (aid,)).fetchone()[0] == 1


def test_a_failure_part_way_changes_nothing(approved, monkeypatch):
    data, r = approved
    c, u, *_ = data
    before = counts(c)
    real = advisory_purge.event

    def boom(*a, **k):
        raise RuntimeError('simulated failure')
    monkeypatch.setattr(advisory_purge, 'event', boom)
    with pytest.raises(RuntimeError):
        advisory_purge.purge(c, u[0], reason='x')
    monkeypatch.setattr(advisory_purge, 'event', real)
    assert counts(c) == before
    with pytest.raises(sqlite3.DatabaseError):
        c.execute('DELETE FROM advisory_revision')


def test_trials_page_is_for_the_super_administrator_and_backs_up_first(cycle, admin, manager, monkeypatch):
    data, r = cycle
    c, u, *_ = data
    import backups
    made = []
    monkeypatch.setattr(backups, 'make_backup', lambda path, kind='manual': made.append(kind) or {'name': 'css_is_test_manual.db'})
    assert manager.get('/advisories/trials').status_code == 404
    page = admin.get('/advisories/trials')
    assert page.status_code == 200 and r['number'] in page.text
    assert 'old trial advisor' in admin.get('/advisories').text
    assert admin.post('/advisories/trials', data={}).status_code == 422 and not made
    done = admin.post('/advisories/trials', data={'confirm': '1'})
    assert done.status_code == 200 and 'css_is_test_manual.db' in done.text and made == ['manual']
    assert c.execute('SELECT COUNT(*) FROM advisory_record').fetchone()[0] == 0
    assert 'no old trial advisories left' in admin.get('/advisories/trials').text

    def broken(path, kind='manual'):
        raise OSError('disk full')
    monkeypatch.setattr(backups, 'make_backup', broken)
    failed = admin.post('/advisories/trials', data={'confirm': '1'})
    assert failed.status_code == 500 and 'backup failed' in failed.text
