"""The new box's telemetry, accessibility hooks and help text (docs/HOME_SEARCH_ASSISTANT_PLAN.md Phase 8)."""
from __future__ import annotations

import pytest

import storage as st
import tours
import ui_telemetry as ut
import version as ver


def _post(client, events):
    return client.post("/telemetry", json={"events": events})


def _ev(event_type, meta):
    return {"event_type": event_type, "route": "/", "session_id": "s-test", "meta": meta}


@pytest.fixture()
def conn(app_mod):
    c = st.connect(app_mod.DB)
    st.init_db(c)
    c.execute("DELETE FROM ui_event")
    c.commit()
    yield c
    c.execute("DELETE FROM ui_event")
    c.commit()
    c.close()


def _stored(conn, event_type):
    rows = [r for r in st.list_ui_events(conn) if r["event_type"] == event_type]
    return [{k: v for k, v in (r["meta"] or {}).items() if k != "v"} for r in rows]


# ── ingest ────────────────────────────────────────────────────────────────────

def test_search_sections_are_kept_as_counts_from_a_fixed_vocabulary(admin, conn):
    r = _post(admin, [_ev("search", {"hits": 4, "sections": {
        "People": 2, "Calendar": 1, "Help": 99999, "Totally Made Up": 3, "Colleagues": "x", "My to-do": True}})])
    assert r.status_code == 204
    (m,) = _stored(conn, "search")
    assert m["hits"] == 4
    assert m["sections"] == {"People": 2, "Calendar": 1, "Help": 100}      # unknown / non-int dropped, capped


def test_ask_events_keep_only_the_stage_and_kind(admin, conn):
    _post(admin, [_ev("ask", {"stage": "fired", "term": "who is in the office"}),
                  _ev("ask", {"stage": "answered", "kind": "answer"}),
                  _ev("ask", {"stage": "fallback", "kind": "delete everything"}),
                  _ev("ask", {"stage": "bogus"})])
    got = sorted(_stored(conn, "ask"), key=lambda m: m.get("stage", ""))
    assert {"stage": "answered", "kind": "answer"} in got
    assert {"stage": "fired"} in got and {"stage": "fallback"} in got
    assert all("term" not in m and m.get("kind") != "delete everything" for m in got)
    assert not any(m.get("stage") == "bogus" for m in got) or {} in got      # a bogus stage keeps nothing


def test_the_ask_event_type_is_in_the_vocabulary():
    assert "ask" in ut.UI_EVENT_TYPES


# ── the digest ────────────────────────────────────────────────────────────────

def _row(event_type, meta, route="/"):
    return {"event_type": event_type, "route": route, "meta": meta, "session_id": "s", "user_id": 1,
            "role": "admin", "created_at": "2026-10-09T10:00:00"}


def test_ask_stats_and_section_totals():
    rows = [_row("ask", {"stage": "fired"}), _row("ask", {"stage": "fired"}), _row("ask", {"stage": "fired"}),
            _row("ask", {"stage": "answered", "kind": "answer"}), _row("ask", {"stage": "answered", "kind": "help"}),
            _row("ask", {"stage": "fallback"}, route="/start"),
            _row("search", {"hits": 3, "sections": {"People": 2, "Help": 1}}),
            _row("search", {"hits": 1, "sections": {"People": 1}})]
    a = ut.ask_stats(rows)
    assert (a["fired"], a["answered"], a["fallback"], a["answer_rate"]) == (3, 2, 1, 67)
    assert a["kinds"] == {"answer": 1, "help": 1}
    assert ut.search_sections(rows) == {"People": 3, "Help": 1}
    d = ut.build_digest(rows, [])
    assert d["ask"]["fired"] == 3 and d["search_sections"]["People"] == 3
    assert ut.ask_stats([])["answer_rate"] is None


def test_ux_insights_page_shows_the_assistant_line(admin, conn):
    _post(admin, [_ev("ask", {"stage": "fired"}), _ev("ask", {"stage": "answered", "kind": "answer"})])
    r = admin.get("/admin/ux-insights")
    assert r.status_code == 200 and "Assistant: 1 asked" in r.text


# ── the client side emits them ────────────────────────────────────────────────

def test_clients_dispatch_and_forward_the_signals():
    import os
    js = os.path.join(os.path.dirname(__file__), "..", "static", "js")
    read = lambda n: open(os.path.join(js, n), encoding="utf-8").read()          # noqa: E731
    assert '"csi:ask"' in read("assistant.js") and '"csi:ask"' in read("telemetry.js")
    assert "sections: sections" in read("search.js") and "meta.sections" in read("telemetry.js")
    assert 'signal("fired")' in read("assistant.js") and 'signal("fallback")' in read("assistant.js")


# ── accessibility ─────────────────────────────────────────────────────────────

@pytest.mark.parametrize("path,scope", [("/", "all"), ("/css", "css")])
def test_inline_search_box_is_a_combobox(admin, path, scope):
    html = admin.get(path).text
    assert 'role="combobox"' in html and 'aria-autocomplete="list"' in html and 'aria-expanded="false"' in html
    assert f'aria-controls="gsearch-res-{scope}"' in html
    assert f'id="gsearch-res-{scope}" role="listbox"' in html


def test_the_palette_is_a_combobox_and_answers_are_announced(admin):
    html = admin.get("/").text
    assert 'id="cmdkInput"' in html and 'role="combobox"' in html and 'aria-controls="cmdkResults"' in html
    import os
    js = open(os.path.join(os.path.dirname(__file__), "..", "static", "js", "search.js"), encoding="utf-8").read()
    assert 'aria-live", "polite"' in js and 'aria-expanded' in js


# ── help ──────────────────────────────────────────────────────────────────────

def test_home_page_tour_is_well_formed_and_in_the_guide(admin):
    steps = tours.tour_for("home_page")
    assert len(steps) >= 3 and all(s["target"] and s["title"] and s["body"] for s in steps)
    assert any("colleague" in s["body"].lower() for s in steps)
    html = admin.get("/help").text
    assert ">Home page<" in html and "Search and ask in one box" in html


def test_the_home_page_carries_its_tour_and_the_targets_exist(admin):
    html = admin.get("/").text
    assert 'window.PAGE_KEY="home_page"' in html
    assert "data-tour=\"search\"" in html and 'class="try-assistant"' in html


def test_feedback_button_is_tucked_away_while_the_results_are_open():
    import os
    css = open(os.path.join(os.path.dirname(__file__), "..", "static", "css", "app.css"), encoding="utf-8").read()
    assert ".gsearch.js .gsearch-results:not(:empty)) .sf-float" in css
