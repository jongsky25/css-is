"""
Data-integrity invariants on the delivered css_is.db (read-only).

These run against the REAL delivered database (not the seeded test copy) so they
double as a health check on the data that ships. They assert referential
integrity, no dangling foreign keys, unique QR tokens, and that the headline
counts the run logs claim still hold.
"""
import os
import pytest
import storage as st

REAL_DB = os.path.join(os.path.dirname(__file__), "..", "css_is.db")

@pytest.fixture(scope="module")
def conn():
    c = st.connect(REAL_DB)
    yield c
    c.close()

def test_sqlite_integrity_check(conn):
    assert conn.execute("PRAGMA integrity_check").fetchone()[0] == "ok"

def test_no_orphan_answers(conn):
    n = conn.execute("""SELECT COUNT(*) FROM answer a
                        LEFT JOIN response r ON a.response_id=r.id
                        WHERE r.id IS NULL""").fetchone()[0]
    assert n == 0, f"{n} answers reference a missing response"

def test_no_orphan_responses(conn):
    n = conn.execute("""SELECT COUNT(*) FROM response r
                        LEFT JOIN form_instance f ON r.form_instance_id=f.id
                        WHERE f.id IS NULL""").fetchone()[0]
    assert n == 0, f"{n} responses reference a missing form_instance"

def test_no_orphan_item_remarks(conn):
    n = conn.execute("""SELECT COUNT(*) FROM item_remark ir
                        LEFT JOIN response r ON ir.response_id=r.id
                        WHERE r.id IS NULL""").fetchone()[0]
    assert n == 0

def test_served_by_points_to_real_person(conn):
    n = conn.execute("""SELECT COUNT(*) FROM response r
                        WHERE r.served_by_rp_id IS NOT NULL
                          AND r.served_by_rp_id NOT IN (SELECT id FROM resource_person)""").fetchone()[0]
    assert n == 0, f"{n} responses serve-by a non-existent person"

def test_form_instance_rp_fk(conn):
    n = conn.execute("""SELECT COUNT(*) FROM form_instance f
                        WHERE f.rp_id IS NOT NULL
                          AND f.rp_id NOT IN (SELECT id FROM resource_person)""").fetchone()[0]
    assert n == 0

def test_unique_qr_tokens(conn):
    dupes = conn.execute("""SELECT qr_token, COUNT(*) c FROM form_instance
                            WHERE qr_token IS NOT NULL
                            GROUP BY qr_token HAVING c > 1""").fetchall()
    assert not dupes, f"duplicate qr_tokens: {dupes[:5]}"

def test_answer_values_in_sane_range(conn):
    # ratings are small ints; anything huge means a coercion bug let junk through
    n = conn.execute("SELECT COUNT(*) FROM answer WHERE value IS NOT NULL AND (value < 0 OR value > 100)").fetchone()[0]
    assert n == 0, f"{n} answers have implausible values"

def test_survey_types_valid(conn):
    bad = conn.execute("SELECT COUNT(*) FROM form_instance WHERE survey_type NOT IN (1,2,3)").fetchone()[0]
    assert bad == 0

def test_headline_counts_present(conn):
    responses = conn.execute("SELECT COUNT(*) FROM response").fetchone()[0]
    answers = conn.execute("SELECT COUNT(*) FROM answer").fetchone()[0]
    # the run logs claim ~41k responses / ~454k atoms; assert the data is there
    assert responses > 30000, f"only {responses} responses — data may be missing"
    assert answers > 300000, f"only {answers} answers"
