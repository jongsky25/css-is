"""Spot Feedback #54 — Mixed comments get their own column on the Verbatims page.

The Verbatims drill-down showed two columns (Appreciate / Improve) with a Mixed
comment duplicated onto both. `story_panel(split_mixed=True)` instead routes Mixed
comments to their own third group, so the page can render three columns. The
default (every other caller) is unchanged: Mixed still shows on both sides.
"""
import dashboard_insights as di
import storage as st


def _verbatims():
    # Three comments; sentiment is forced via overrides so the test doesn't depend
    # on the wording classifier. rid identifies each; item "" = the overall remark.
    return (
        [{"response_id": 1, "remarks": "aaa", "notes": {}},
         {"response_id": 2, "remarks": "bbb", "notes": {}},
         {"response_id": 3, "remarks": "ccc", "notes": {}}],
        {(1, ""): "appreciate", (2, ""): "improve", (3, ""): "mixed"},
    )


def _rids(group):
    return sorted({q["rid"] for b in group["buckets"] for q in b["quotes"]})


def test_split_mixed_gives_mixed_its_own_column():
    verbs, overrides = _verbatims()
    story = di.story_panel(verbs, overrides, split_mixed=True)
    assert _rids(story["appreciate"]) == [1]        # only the appreciate comment
    assert _rids(story["improve"]) == [2]           # only the improve comment
    assert _rids(story["mixed"]) == [3]             # mixed lands in its own group
    # and it is NOT duplicated onto the two sides
    assert 3 not in _rids(story["appreciate"])
    assert 3 not in _rids(story["improve"])


def test_default_keeps_mixed_on_both_sides():
    verbs, overrides = _verbatims()
    story = di.story_panel(verbs, overrides)          # split_mixed defaults to False
    assert 3 in _rids(story["appreciate"])            # mixed shown on both sides…
    assert 3 in _rids(story["improve"])
    assert story["mixed"]["buckets"] == []            # …and the mixed group is empty


# ---- the page actually renders the third column ----------------------------

_F3 = [("A", 6), ("B1", 6), ("B2", 6), ("B3", 6), ("B4", 6),
       ("B5", 6), ("B6", 6), ("B7", 6), ("B8", 6), ("B9", 6), ("C", 4)]


def test_verbatims_page_renders_three_columns(manager, app_mod):
    db_path = app_mod.DB
    fid = None
    conn = st.connect(db_path)
    fid = conn.execute("SELECT id FROM form_instance WHERE survey_type=3 "
                       "ORDER BY id LIMIT 1").fetchone()[0]
    rid = st.record_response(conn, fid, _F3)
    # a comment so the story renders (scope has at least one verbatim)
    conn.execute("UPDATE response SET remarks=? WHERE id=?",
                 ("clear and helpful session", rid))
    conn.commit(); conn.close()
    app_mod.invalidate_atoms()

    r = manager.get("/reports/verbatims", params={"survey_type": 3})
    assert r.status_code == 200
    body = r.text
    assert "What people appreciated" in body
    assert "What people would improve" in body
    assert "Mixed — good and bad" in body                  # the new third column
    assert "repeat(3, 1fr)" in body                        # three-column grid
