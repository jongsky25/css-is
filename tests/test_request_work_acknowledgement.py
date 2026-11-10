"""Acknowledgement of changed request sources (design: docs/REQUEST_RECONCILIATION_DESIGN.md).

Acknowledgement is an append-only record about a work item. It must never change work,
the document, notifications or any formal review.
"""
import json
import sqlite3
import pytest
import documents as docs
import documents_permissions as permissions
import documents_request_work as proposals
import storage as st
import work_review
from test_document_request_work_routes import proposal_record, payload
from test_document_understanding_review_routes import review_record
from test_document_request_comparison_routes import revise_record
from test_document_registry_pagination import seed_many

WATCHED = ('work_task', 'work_case', 'work_event', 'work_review_packet', 'work_review_invalidation',
           'document', 'document_event', 'document_request_work', 'document_understanding',
           'document_understanding_revision', 'document_notice', 'document_job')


def propose(record, viewer, lead=True):
    c, u, doc, unit, url = record
    assert viewer.post(url, data=payload(viewer.get(url), doc, unit), follow_redirects=False).status_code == 303
    saved = proposals.existing(c, u, doc['id'], 0)
    if lead:
        c.execute('UPDATE work_case SET lead_id=? WHERE id=?', (u['id'], saved['case_id'])); c.commit()
    return saved


def fields(c, doc_id, task_id, **changes):
    current = proposals.digest(proposals.source(c, doc_id, 0))
    revision = c.execute('SELECT revision FROM work_task WHERE id=?', (task_id,)).fetchone()[0]
    return {'confirmed': 'yes', 'source_hash': current, 'task_revision': str(revision), 'note': 'Checked', **changes}


def tables(c):
    return {t: c.execute(f'SELECT * FROM {t}').fetchall() for t in WATCHED}


def changed(record, viewer):
    """A proposal whose source was then edited, ready to acknowledge."""
    c, u, doc, unit, url = record
    saved = propose(record, viewer)
    revise_record(c, u, doc, need_0_output='Changed deliverable')
    return c, u, doc, saved


def add_reviewed_outgoing(c, u, unit, case_id):
    """An outgoing document in the same case with a current consolidation review packet."""
    (out_id,) = seed_many(c, u, unit, 1)
    c.execute("INSERT INTO work_document VALUES (?,?,'reference',?,'2026-11-01')", (case_id, out_id, u['id']))
    c.execute("""INSERT INTO document_file_version(id,document_id,url,file_id,fingerprint,role,actor_id,created_at)
        VALUES (?,?,'https://example.test/draft','fake','hash','draft',?,'2026-11-01')""", (out_id, out_id, u['id']))
    c.execute("UPDATE document SET current_version=?,approved_version=?,status='approved',policy_json=? WHERE id=?",
              (out_id, out_id, json.dumps({'closure': [], 'signature_required': False, 'release': [], 'ack_required': False}), out_id))
    snapshot, digest = work_review.snapshot(c, case_id, out_id)
    c.execute("""INSERT INTO work_review_packet(case_id,document_id,version_id,reviewer_id,actor_id,snapshot_json,
        snapshot_hash,reason,created_at) VALUES (?,?,?,?,?,?,?,'Synthetic','2026-11-01')""",
              (case_id, out_id, out_id, u['id'], u['id'], json.dumps(snapshot), digest))
    c.commit()
    return out_id


def test_acknowledgement_is_recorded_once_and_a_retry_returns_the_same_record(proposal_record, viewer):
    c, u, doc, saved = changed(proposal_record, viewer)
    data = fields(c, doc['id'], saved['task_id'])
    first = proposals.acknowledge(c, u, doc['id'], 0, data)
    assert (first['actor_id'], first['source_hash'], first['note']) == (u['id'], data['source_hash'], 'Checked')
    assert first['task_revision'] == int(data['task_revision']) and first['understanding_revision'] >= 2
    assert proposals.acknowledge(c, u, doc['id'], 0, data)['id'] == first['id']
    assert c.execute('SELECT COUNT(*) FROM document_request_work_review').fetchone()[0] == 1
    assert proposals.latest_acknowledgement(c, u, doc['id'], 0)['id'] == first['id']
    assert c.execute("SELECT COUNT(*) FROM audit_log WHERE action='document_request_work_acknowledged'").fetchone()[0] == 1


def test_changes_no_work_document_review_or_notification_state(proposal_record, viewer):
    c, u, doc, saved = changed(proposal_record, viewer)
    before = tables(c)
    proposals.acknowledge(c, u, doc['id'], 0, fields(c, doc['id'], saved['task_id']))
    assert tables(c) == before
    # The warning now compares against the last reviewed source; the proposal comparison is kept.
    current = proposals.existing(c, u, doc['id'], 0)
    assert current['changed'] is False and current['changed_since_proposal'] is True
    revise_record(c, u, doc, need_0_output='Changed a second time')
    assert proposals.existing(c, u, doc['id'], 0)['changed'] is True
    revise_record(c, u, doc, need_0_output='Comments matrix')  # back to the proposed source
    returned = proposals.existing(c, u, doc['id'], 0)
    assert returned['changed'] is False and returned['changed_since_proposal'] is False


def test_nothing_to_acknowledge_before_the_source_changes(proposal_record, viewer):
    c, u, doc, unit, url = proposal_record
    saved = propose(proposal_record, viewer)
    with pytest.raises(ValueError, match='has not changed') as caught:
        proposals.acknowledge(c, u, doc['id'], 0, fields(c, doc['id'], saved['task_id']))
    assert type(caught.value) is ValueError
    assert c.execute('SELECT COUNT(*) FROM document_request_work_review').fetchone()[0] == 0


def test_stale_source_or_work_revision_conflicts_and_writes_nothing(proposal_record, viewer):
    c, u, doc, saved = changed(proposal_record, viewer)
    stale = fields(c, doc['id'], saved['task_id'])
    revise_record(c, u, doc, need_0_output='Changed again')
    with pytest.raises(docs.Conflict, match='changed again'):
        proposals.acknowledge(c, u, doc['id'], 0, stale)
    data = fields(c, doc['id'], saved['task_id'])
    c.execute('UPDATE work_task SET revision=revision+1 WHERE id=?', (saved['task_id'],)); c.commit()
    with pytest.raises(docs.Conflict, match='contribution changed'):
        proposals.acknowledge(c, u, doc['id'], 0, data)
    assert c.execute('SELECT COUNT(*) FROM document_request_work_review').fetchone()[0] == 0


@pytest.mark.parametrize('bad', [{'confirmed': ''}, {'source_hash': 'xyz'}, {'source_hash': 'A' * 64},
                                 {'task_revision': '-1'}, {'task_revision': '١'}, {'note': 'x' * 501},
                                 {'note': {}}, {'source_hash': 5}, {'task_revision': 3}])
def test_invalid_fields_are_rejected(proposal_record, viewer, bad):
    c, u, doc, saved = changed(proposal_record, viewer)
    with pytest.raises(ValueError):
        proposals.acknowledge(c, u, doc['id'], 0, fields(c, doc['id'], saved['task_id'], **bad))
    assert c.execute('SELECT COUNT(*) FROM document_request_work_review').fetchone()[0] == 0


def test_only_lead_or_officer_may_acknowledge_and_unrelated_accounts_see_nothing(proposal_record, viewer):
    c, u, doc, unit, url = proposal_record
    saved = propose(proposal_record, viewer, lead=False)
    revise_record(c, u, doc, need_0_output='Changed deliverable')
    data = fields(c, doc['id'], saved['task_id'])
    c.execute('UPDATE work_case SET lead_id=NULL WHERE id=?', (saved['case_id'],)); c.commit()
    if not proposals.can_acknowledge(u, proposals.work.raw(c, saved['case_id']), c):
        with pytest.raises(permissions.Denied, match='lead or an authorized'):
            proposals.acknowledge(c, u, doc['id'], 0, data)
    c.execute('UPDATE work_case SET lead_id=? WHERE id=?', (u['id'], saved['case_id'])); c.commit()
    outsider = st.get_admin_user(c, 'admin@test.local')
    with pytest.raises(permissions.Denied):
        proposals.acknowledge(c, outsider, doc['id'], 0, data)
    assert c.execute('SELECT COUNT(*) FROM document_request_work_review').fetchone()[0] == 0
    assert proposals.acknowledge(c, u, doc['id'], 0, data)['actor_id'] == u['id']


def test_closed_case_and_disabled_module_block_the_write(proposal_record, viewer):
    c, u, doc, saved = changed(proposal_record, viewer)
    data = fields(c, doc['id'], saved['task_id'])
    st.set_setting(c, 'work.enabled', '0'); c.commit()
    with pytest.raises(ValueError, match='not enabled'):
        proposals.acknowledge(c, u, doc['id'], 0, data)
    st.set_setting(c, 'work.enabled', '1')
    c.execute("UPDATE work_case SET status='completed' WHERE id=?", (saved['case_id'],)); c.commit()
    with pytest.raises(ValueError):
        proposals.acknowledge(c, u, doc['id'], 0, data)
    assert c.execute('SELECT COUNT(*) FROM document_request_work_review').fetchone()[0] == 0


def test_no_proposed_work_for_the_request_means_nothing_to_acknowledge(proposal_record):
    c, u, doc, unit, url = proposal_record
    with pytest.raises(ValueError, match='already has proposed work'):
        proposals.acknowledge(c, u, doc['id'], 0, {'confirmed': 'yes', 'source_hash': '0' * 64, 'task_revision': '1'})
    with pytest.raises(ValueError):
        proposals.acknowledge(c, u, doc['id'], 9, {})


def test_a_cleared_request_can_be_acknowledged_and_keeps_its_receipt(proposal_record, viewer):
    c, u, doc, unit, url = proposal_record
    saved = propose(proposal_record, viewer)
    revise_record(c, u, doc, needs_status='unclear', **{f'need_0_{key}': '' for key in ('action', 'kind', 'output', 'deadline', 'evidence', 'page', 'confirmed')})
    record = proposals.acknowledge(c, u, doc['id'], 0, fields(c, doc['id'], saved['task_id']))
    assert record['source_hash'] != saved['source_hash']
    assert proposals.existing(c, u, doc['id'], 0)['task_id'] == saved['task_id']


def test_acknowledgements_are_append_only(proposal_record, viewer):
    c, u, doc, saved = changed(proposal_record, viewer)
    record = proposals.acknowledge(c, u, doc['id'], 0, fields(c, doc['id'], saved['task_id']))
    with pytest.raises(sqlite3.DatabaseError, match='append-only'):
        c.execute('UPDATE document_request_work_review SET note=? WHERE id=?', ('Edited', record['id']))
    c.rollback()
    with pytest.raises(sqlite3.DatabaseError, match='append-only'):
        c.execute('DELETE FROM document_request_work_review WHERE id=?', (record['id'],))
    c.rollback()
    revise_record(c, u, doc, need_0_output='Changed a third time')
    newer = proposals.acknowledge(c, u, doc['id'], 0, fields(c, doc['id'], saved['task_id']))
    assert newer['id'] > record['id'] and proposals.latest_acknowledgement(c, u, doc['id'], 0)['id'] == newer['id']


def test_schema_install_is_repeatable_and_keeps_records(proposal_record, viewer):
    c, u, doc, saved = changed(proposal_record, viewer)
    record = proposals.acknowledge(c, u, doc['id'], 0, fields(c, doc['id'], saved['task_id']))
    st.init_db(c); st.init_db(c)
    assert proposals.latest_acknowledgement(c, u, doc['id'], 0)['id'] == record['id']


def test_existing_behavior_editing_a_request_already_makes_a_linked_review_stale(proposal_record, viewer):
    """Pinned, not introduced here: a request edit sets the incoming document's reconcile flag,
    which is part of a linked outgoing document's consolidation snapshot. Acknowledging must
    neither cause this nor undo it."""
    c, u, doc, unit, url = proposal_record
    saved = propose(proposal_record, viewer)
    out_id = add_reviewed_outgoing(c, u, unit, saved['case_id'])
    packet = work_review.latest(c, out_id)
    assert work_review.current(c, packet) is True
    revise_record(c, u, doc, need_0_output='Changed deliverable')
    assert c.execute('SELECT reconcile FROM document WHERE id=?', (doc['id'],)).fetchone()[0] == 1
    assert work_review.current(c, packet) is False
    proposals.acknowledge(c, u, doc['id'], 0, fields(c, doc['id'], saved['task_id']))
    assert work_review.current(c, packet) is False
    assert c.execute('SELECT reconcile FROM document WHERE id=?', (doc['id'],)).fetchone()[0] == 1
