"""Warn before a request edit makes a linked formal review out of date (a read-only notice)."""
import json
import pytest
import documents_request_work as proposals
import storage as st
import work
import work_review
from test_document_request_work_routes import proposal_record, payload
from test_document_understanding_review_routes import review_record
from test_document_request_comparison_routes import revise_record
from test_request_work_acknowledgement import propose, add_reviewed_outgoing, tables
from test_document_registry_pagination import seed_many

TITLE = 'Saving will require a renewed formal review'


def add_reviewed_outgoing_many(c, u, unit, case_id, count):
    """Link every outgoing document first: adding a link changes earlier snapshots."""
    ids = seed_many(c, u, unit, count)
    for out_id in ids:
        c.execute("INSERT INTO work_document VALUES (?,?,'reference',?,'2026-11-01')", (case_id, out_id, u['id']))
        c.execute("""INSERT INTO document_file_version(id,document_id,url,file_id,fingerprint,role,actor_id,created_at)
            VALUES (?,?,'https://example.test/draft','fake','hash','draft',?,'2026-11-01')""", (out_id, out_id, u['id']))
        c.execute("UPDATE document SET current_version=?,approved_version=?,status='approved',policy_json=? WHERE id=?",
                  (out_id, out_id, json.dumps({'closure': [], 'signature_required': False, 'release': [], 'ack_required': False}), out_id))
    for out_id in ids:
        snapshot, digest = work_review.snapshot(c, case_id, out_id)
        c.execute("""INSERT INTO work_review_packet(case_id,document_id,version_id,reviewer_id,actor_id,snapshot_json,
            snapshot_hash,reason,created_at) VALUES (?,?,?,?,?,?,?,'Synthetic','2026-11-01')""",
                  (case_id, out_id, out_id, u['id'], u['id'], json.dumps(snapshot), digest))
    c.commit()
    return ids


def understanding_page(viewer, doc):
    page = viewer.get(f"/documents/{doc['id']}/understanding")
    assert page.status_code == 200 and page.headers['cache-control'] == 'no-store'
    return page.text


def test_warning_lists_linked_outgoing_documents_with_a_current_review(proposal_record, viewer):
    c, u, doc, unit, url = proposal_record
    saved = propose(proposal_record, viewer)
    out_id = add_reviewed_outgoing(c, u, unit, saved['case_id'])
    text = understanding_page(viewer, doc)
    subject = c.execute('SELECT subject FROM document WHERE id=?', (out_id,)).fetchone()[0]
    assert TITLE in text and subject in text and f'/documents/{out_id}' in text
    assert 'for 1 outgoing document whose' in text and 'that review' in text
    assert [x['document_id'] for x in work_review.stale_if_source_edited(c, u, doc['id'])] == [out_id]


def test_plural_wording_for_several_linked_documents(proposal_record, viewer):
    c, u, doc, unit, url = proposal_record
    saved = propose(proposal_record, viewer)
    add_reviewed_outgoing_many(c, u, unit, saved['case_id'], 2)
    text = understanding_page(viewer, doc)
    assert 'for 2 outgoing documents whose' in text and 'those reviews' in text


def test_no_warning_without_a_linked_current_review(proposal_record, viewer):
    c, u, doc, unit, url = proposal_record
    assert TITLE not in understanding_page(viewer, doc)
    saved = propose(proposal_record, viewer)
    assert TITLE not in understanding_page(viewer, doc)  # linked work but no review packet
    add_reviewed_outgoing(c, u, unit, saved['case_id'])
    assert TITLE in understanding_page(viewer, doc)
    revise_record(c, u, doc, need_0_output='Changed deliverable')  # the review is now already out of date
    assert TITLE not in understanding_page(viewer, doc)
    assert work_review.stale_if_source_edited(c, u, doc['id']) == []


def test_documents_linked_through_an_alias_are_found(proposal_record, viewer):
    c, u, doc, unit, url = proposal_record
    (alias_id,) = seed_many(c, u, unit, 1, subject='Alias record')
    c.execute('UPDATE document SET canonical_id=? WHERE id=?', (doc['id'], alias_id)); c.commit()
    other = work.create(c, u, {'title': 'Other work', 'outcome': 'Other output', 'unit_id': str(unit)})
    c.execute("INSERT INTO work_document VALUES (?,?,'reference',?,'2026-11-01')", (other['id'], alias_id, u['id'])); c.commit()
    out_id = add_reviewed_outgoing(c, u, unit, other['id'])
    assert [x['document_id'] for x in work_review.stale_if_source_edited(c, u, doc['id'])] == [out_id]


def test_nothing_is_disclosed_to_someone_without_access_and_the_page_load_writes_nothing(proposal_record, viewer):
    c, u, doc, unit, url = proposal_record
    saved = propose(proposal_record, viewer)
    add_reviewed_outgoing(c, u, unit, saved['case_id'])
    outsider = st.get_admin_user(c, 'admin@test.local')
    assert work_review.stale_if_source_edited(c, outsider, doc['id']) == []
    before = tables(c); audits = c.execute('SELECT COUNT(*) FROM audit_log').fetchone()[0]
    understanding_page(viewer, doc)
    assert tables(c) == before and c.execute('SELECT COUNT(*) FROM audit_log').fetchone()[0] == audits


def test_saving_still_works_and_then_the_warning_is_gone(proposal_record, viewer):
    c, u, doc, unit, url = proposal_record
    saved = propose(proposal_record, viewer)
    out_id = add_reviewed_outgoing(c, u, unit, saved['case_id'])
    packet = work_review.latest(c, out_id)
    assert work_review.current(c, packet) is True
    revise_record(c, u, doc, need_0_output='Changed deliverable')
    assert work_review.current(c, packet) is False  # the behavior the warning describes
    assert TITLE not in understanding_page(viewer, doc)
