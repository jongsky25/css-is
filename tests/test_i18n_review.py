"""
tools/i18n_review.py — docs/AI_INTEGRATION_PLAN.md Phase 10.

This is an offline, one-off CLI assist (not a web route), so there is no
RBAC/HTTP surface to cover. Instead: build_review_items() collects every
DRAFT English/Filipino pair in i18n.py (skipping the official ARTA_TEXT_FIL
wording); review_batch() calls ai_core.ask() and validates the model's
suggestions against a server-side key allow-list plus a placeholder-
preservation check (a suggestion that drops/alters a {subject}/{months}
token is rejected, never silently used); main() wires the CLI, gates on the
same ai_mode/feature/config checks every other feature uses, and never
writes back to i18n.py — it only prints a report.

Autouse fixture below guarantees this file never reaches the real network —
it always monkeypatches ai_core._http_generate.
"""
import httpx
import pytest

import ai_core as ai
import storage as st
import tools.i18n_review as tr


@pytest.fixture(autouse=True)
def _no_real_network(monkeypatch):
    def _boom(*a, **kw):
        raise AssertionError("a real httpx.post reached the network in an AI test — mock it")
    monkeypatch.setattr(httpx, "post", _boom)
    ai.reset_cooldown()
    yield
    ai.reset_cooldown()


@pytest.fixture
def conn(tmp_path):
    c = st.connect(str(tmp_path / "test.db"))
    st.init_db(c)
    yield c
    c.close()


def _configure(conn, monkeypatch, *, mode="router", enabled=True):
    monkeypatch.setenv("CSS_GEMINI_API_KEY", "test-key")
    st.set_setting(conn, "ai_mode", mode)
    st.set_setting(conn, "ai_feature_i18n_review", "1" if enabled else "0")
    conn.commit()


def _mock_suggestions(monkeypatch, transform=None):
    """Mock _http_generate to echo back a suggestion for every key it was
    asked about, optionally mangled by `transform(key, suggested_fil)`."""
    def fake(prompt, *, system=None, response_schema=None, temperature=0.2,
             max_output_tokens=1024, timeout=8.0):
        import re
        keys = re.findall(r"key: (\S+)", prompt)
        suggestions = []
        for k in keys:
            text = f"REVISED {k}"
            if transform:
                text = transform(k, text)
            suggestions.append({"key": k, "suggested_fil": text, "note": "tightened wording"})
        return {"text": "{}", "parsed": {"suggestions": suggestions},
                "tokens_in": 10, "tokens_out": 10, "latency_ms": 5, "model": "gemini-test"}
    monkeypatch.setattr(ai, "_http_generate", fake)


# ---- build_review_items ----------------------------------------------------

def test_build_review_items_covers_every_draft_group_with_unique_keys():
    items = tr.build_review_items()
    keys = [i["key"] for i in items]
    assert len(keys) == len(set(keys)), "duplicate review keys"
    prefixes = {k.split(".")[0].split("[")[0] for k in keys}
    assert prefixes >= {"B_TEXT_FIL", "A_TEXT_FIL", "C_TEXT_FIL", "CONSENT_TMPL_FIL",
                        "LIKERT5_FIL", "OSQ4_FIL", "REMARK_CHIPS_FIL", "UI"}


def test_build_review_items_skips_official_arta_wording():
    items = tr.build_review_items()
    assert not any(i["key"].startswith("ARTA_TEXT_FIL") for i in items)


def test_build_review_items_pairs_english_source_correctly():
    items = {i["key"]: i for i in tr.build_review_items()}
    assert items["B_TEXT_FIL.B1"]["en"] == "{subject} delivered the session as promised and announced."
    assert "{subject}" in items["B_TEXT_FIL.B1"]["fil"]


# ---- review_batch: allow-list + placeholder validation ----------------------

def test_review_batch_accepts_a_valid_suggestion(conn, monkeypatch):
    _configure(conn, monkeypatch)
    _mock_suggestions(monkeypatch, transform=lambda k, t: t.replace(k, "{subject}")
                       if "B_TEXT_FIL" in k else t)
    items = [i for i in tr.build_review_items() if i["key"] == "UI.submit"]
    out = tr.review_batch(conn, items)
    assert out["UI.submit"]["ok"] is True
    assert out["UI.submit"]["text"] == "REVISED UI.submit"
    assert out["UI.submit"]["note"] == "tightened wording"


def test_review_batch_rejects_suggestion_missing_a_placeholder(conn, monkeypatch):
    _configure(conn, monkeypatch)
    _mock_suggestions(monkeypatch)  # plain "REVISED <key>" — no {subject} token
    items = [i for i in tr.build_review_items() if i["key"] == "B_TEXT_FIL.B1"]
    out = tr.review_batch(conn, items)
    assert out["B_TEXT_FIL.B1"]["ok"] is False
    assert "placeholder" in out["B_TEXT_FIL.B1"]["reason"]


def test_review_batch_ignores_a_key_it_never_asked_about(conn, monkeypatch):
    _configure(conn, monkeypatch)

    def fake(prompt, **kw):
        return {"text": "{}", "parsed": {"suggestions": [
            {"key": "UI.submit", "suggested_fil": "ok"},
            {"key": "NOT_A_REAL_KEY", "suggested_fil": "injected"},
        ]}, "tokens_in": 1, "tokens_out": 1, "latency_ms": 1, "model": "gemini-test"}
    monkeypatch.setattr(ai, "_http_generate", fake)

    items = [i for i in tr.build_review_items() if i["key"] == "UI.submit"]
    out = tr.review_batch(conn, items)
    assert set(out) == {"UI.submit"}


# ---- main(): gating + end-to-end -------------------------------------------

def test_main_reports_unconfigured_without_calling_ai(conn, monkeypatch, tmp_path, capsys):
    monkeypatch.delenv("CSS_GEMINI_API_KEY", raising=False)
    monkeypatch.delenv("CSS_GROQ_API_KEY", raising=False)
    rc = tr.main(["--db", str(tmp_path / "unused.db"), "--limit", "1"])
    assert rc == 1
    assert "not set" in capsys.readouterr().err


def test_main_runs_on_groq_alone_when_gemini_unconfigured(monkeypatch, tmp_path, capsys):
    """Gemini being unconfigured no longer stops the CLI cold if an admin has
    opted a Groq fallback into standalone use (ai_core.ai_available())."""
    db = tmp_path / "t.db"
    c = st.connect(str(db)); st.init_db(c)
    monkeypatch.delenv("CSS_GEMINI_API_KEY", raising=False)
    monkeypatch.setenv("CSS_GROQ_API_KEY", "groq-key")
    st.set_setting(c, "ai_mode", "router")
    st.set_setting(c, "ai_feature_i18n_review", "1")
    st.set_setting(c, "ai_fallback_enabled", "1")
    c.commit(); c.close()

    def fake_groq(prompt, *, system=None, response_schema=None, temperature=0.2,
                  max_output_tokens=1024, timeout=8.0):
        import re
        keys = re.findall(r"key: (\S+)", prompt)
        suggestions = [{"key": k, "suggested_fil": f"REVISED {k}", "note": "n"} for k in keys]
        return {"text": "{}", "parsed": {"suggestions": suggestions},
                "tokens_in": 10, "tokens_out": 10, "latency_ms": 5, "model": "groq-test"}
    monkeypatch.setattr(ai, "_http_generate_groq", fake_groq)

    rc = tr.main(["--db", str(db), "--limit", "1"])
    assert rc == 0
    assert "not set" not in capsys.readouterr().err


def test_main_reports_mode_off(conn, monkeypatch, tmp_path, capsys):
    monkeypatch.setenv("CSS_GEMINI_API_KEY", "test-key")
    db = tmp_path / "t.db"
    c = st.connect(str(db)); st.init_db(c); c.commit(); c.close()
    rc = tr.main(["--db", str(db), "--limit", "1"])
    assert rc == 1
    assert "mode is 'off'" in capsys.readouterr().err


def test_main_reports_feature_disabled(monkeypatch, tmp_path, capsys):
    db = tmp_path / "t.db"
    c = st.connect(str(db)); st.init_db(c)
    _configure(c, monkeypatch, enabled=False)
    c.close()
    rc = tr.main(["--db", str(db), "--limit", "1"])
    assert rc == 1
    assert "disabled" in capsys.readouterr().err


def test_main_end_to_end_writes_report_and_summary(monkeypatch, tmp_path, capsys):
    db = tmp_path / "t.db"
    c = st.connect(str(db)); st.init_db(c)
    _configure(c, monkeypatch)
    c.close()
    _mock_suggestions(monkeypatch, transform=lambda k, t: t + " {subject}"
                       if "B_TEXT_FIL" in k or k in ("A_TEXT_FIL", "C_TEXT_FIL") else t)

    out_file = tmp_path / "report.md"
    rc = tr.main(["--db", str(db), "--limit", "3", "--out", str(out_file)])
    assert rc == 0
    assert out_file.exists()
    content = out_file.read_text(encoding="utf-8")
    assert "### " in content
    printed = capsys.readouterr().out
    assert "item(s) got a suggestion" in printed


def test_main_survives_an_ai_error_mid_run(monkeypatch, tmp_path, capsys):
    db = tmp_path / "t.db"
    c = st.connect(str(db)); st.init_db(c)
    _configure(c, monkeypatch)
    c.close()
    monkeypatch.setattr(ai, "_http_generate", lambda *a, **kw: (_ for _ in ()).throw(
        ai.AIBadResponse("boom")))
    rc = tr.main(["--db", str(db), "--limit", "2"])
    assert rc == 0  # never crashes — the report just notes nothing was returned
    assert "unavailable" in capsys.readouterr().err


def test_i18n_review_is_registered_in_feature_defaults():
    assert "i18n_review" in ai.FEATURE_DEFAULTS
    assert "i18n_review" in ai.FEATURES
