"""One box: search and ask together (docs/HOME_SEARCH_ASSISTANT_PLAN.md Phase 7).

The behaviour lives in static/js (assistant.js, start.js, search.js), so the checks are: the markup hooks
the pages need, the question heuristic (run for real under node when it is installed), and that the
/start page still loads what it needs.
"""
from __future__ import annotations

import json
import os
import re
import shutil
import subprocess

import pytest

JS = os.path.join(os.path.dirname(__file__), "..", "static", "js")


def _read(name):
    with open(os.path.join(JS, name), encoding="utf-8") as f:
        return f.read()


# ── script wiring ─────────────────────────────────────────────────────────────

def test_start_page_loads_assistant_before_start_js(admin):
    html = admin.get("/start").text
    assert "/static/js/assistant.js" in html and "/static/js/start.js" in html
    assert html.index("/static/js/assistant.js") < html.index("/static/js/start.js")
    for hook in ('id="startForm"', 'id="startInput"', 'id="startStatus"', 'id="startResults"'):
        assert hook in html                                  # the ids start.js reads


def test_every_signed_in_page_loads_the_assistant_next_to_search(admin):
    html = admin.get("/").text
    assert html.index("/static/js/search.js") < html.index("/static/js/assistant.js")


def test_login_page_loads_neither(app_mod):
    from starlette.testclient import TestClient
    html = TestClient(app_mod.app).get("/login").text
    assert "assistant.js" not in html and "search.js" not in html


def test_the_route_call_moved_out_of_start_js():
    assert "/api/ai/route" in _read("assistant.js")
    assert "fetch(" not in _read("start.js")                  # no network code left in the thin caller
    assert "/api/ai/feedback" in _read("assistant.js")
    assert "CSSAssistant.ask" in _read("start.js") and "CSSAssistant.ask" in _read("search.js")


def test_the_search_box_offers_ask_only_when_unscoped():
    js = _read("search.js")
    assert 'scope === "all" && window.CSSAssistant && looksLikeQuestion(raw)' in js
    assert "data-ask" in js and "autoNavigate: false" in js


def test_admin_ai_page_explains_the_landing_choice(admin):
    assert "full-page assistant" in admin.get("/admin/ai").text


def test_assistant_cards_styles_live_in_app_css_not_only_start_html(admin):
    css = open(os.path.join(JS, "..", "css", "app.css"), encoding="utf-8").read()
    assert ".start-card" in css and ".fb-btn" in css
    assert ".start-card" not in admin.get("/start").text.split("</style>")[0].split("<style>")[-1]


# ── the question heuristic, run for real ──────────────────────────────────────

NODE = shutil.which("node")

QUESTIONS = ["who is in the office today", "Who is in?", "what time", "sino ang nasa opisina", "may meeting ba ako",
             "ilan oras", "kailan ang awa", "saan ang room", "anything at all?", "is the room free", "do I have approvals",
             "am I on leave", "can I book", "does it work", "how to file", "where is it", "when is it",
             "one two three four"]
NOT_QUESTIONS = ["trends", "wellness", "walk-in report", "new survey", "room", "a b c", "team monitoring"]


@pytest.mark.skipif(not NODE, reason="node is not installed")
def test_question_heuristic_matches_the_plan():
    script = r"""
      const vm = require('vm'), fs = require('fs');
      const code = fs.readFileSync(process.argv[1], 'utf8');
      const sandbox = { window: { SEARCH_INDEX: [] },
        document: { readyState: 'loading', addEventListener() {}, getElementById() { return null; },
                    querySelectorAll() { return []; } } };
      sandbox.window.window = sandbox.window;
      vm.createContext(sandbox);
      vm.runInContext(code, sandbox);
      const f = sandbox.window.CSSSearch.looksLikeQuestion;
      const qs = JSON.parse(process.argv[2]);
      console.log(JSON.stringify(qs.map(q => f(q))));
    """
    out = subprocess.run([NODE, "-e", script, os.path.join(JS, "search.js"), json.dumps(QUESTIONS + NOT_QUESTIONS)],
                         capture_output=True, text=True, timeout=30)
    assert out.returncode == 0, out.stderr
    got = json.loads(out.stdout)
    assert got[:len(QUESTIONS)] == [True] * len(QUESTIONS), dict(zip(QUESTIONS, got))
    assert got[len(QUESTIONS):] == [False] * len(NOT_QUESTIONS), dict(zip(NOT_QUESTIONS, got[len(QUESTIONS):]))
