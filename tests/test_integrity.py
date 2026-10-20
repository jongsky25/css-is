"""Integrity invariants exercised against a populated, isolated application database.

These are storage regression tests, not a health assertion about production data.
No test opens or creates css_is.db in the repository.
"""
import pytest
import storage as st


@pytest.fixture(scope="module")
def conn(tmp_path_factory):
    c = st.connect(str(tmp_path_factory.mktemp("integrity") / "reference.db"))
    st.init_db(c)
    rp = c.execute("INSERT INTO resource_person(name, is_internal) VALUES ('Integrity reference',1)").lastrowid
    for survey_type in (1, 2, 3):
        fid = st.create_form_instance(c, survey_type, f"F{survey_type}", "2026-01-01",
                                      rp_id=rp if survey_type == 3 else None)
        answers = [("SQD1", 5), ("SQD2", 4)] if survey_type == 1 else [("B1", 6), ("C", 4)]
        st.record_response(c, fid, answers, submitted_at="2026-01-01T09:00:00",
                           served_by_rp_id=rp if survey_type == 1 else None,
                           item_remarks={answers[0][0]: "Reference note"})
    c.commit()
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

def test_reference_counts_present(conn):
    responses = conn.execute("SELECT COUNT(*) FROM response").fetchone()[0]
    answers = conn.execute("SELECT COUNT(*) FROM answer").fetchone()[0]
    assert responses == 3
    assert answers == 6
    assert conn.execute("SELECT COUNT(*) FROM item_remark").fetchone()[0] == 3
