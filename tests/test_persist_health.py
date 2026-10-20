"""/ops durability card — stall detection (the 2026-06-26 wedge).

A hung persist-loop worker froze _PERSIST_HEALTH at the last 'ok' while nothing
was actually being saved for ~5h, and the card stayed green. These lock that the
card now flips RED on a stall independently of the recorded state, and stays
green during normal operation. The pure rule itself is in test_backups.py
(persist_is_stalled); here we test the /ops wiring (_persist_health_view).
"""
import time
import pytest


@pytest.fixture
def persist_env(app_mod, monkeypatch):
    """Turn persistence on and isolate the health state for each test."""
    monkeypatch.setattr(app_mod, "PERSIST_DIR", "/data", raising=False)
    monkeypatch.setattr(app_mod, "PERSIST_TICK", 60, raising=False)
    monkeypatch.setattr(app_mod, "PERSIST_STALL_TICKS", 5, raising=False)

    def set_health(**kw):
        base = {"state": "ok", "reason": "snapshot written",
                "last_ok": "2026-06-26T11:16:42", "last_event": "2026-06-26T11:16:42",
                "consecutive_bad": 0, "last_tick_mono": time.monotonic(),
                "last_ok_mono": time.monotonic()}
        base.update(kw)
        monkeypatch.setattr(app_mod, "_PERSIST_HEALTH", base)
    return app_mod, set_health


def test_card_green_when_loop_healthy(persist_env):
    app_mod, set_health = persist_env
    set_health()                                   # fresh tick, nothing unsaved
    v = app_mod._persist_health_view()
    assert v["down"] is False and v["tone"] == "good"


def test_card_red_when_loop_stopped_ticking(persist_env):
    # state still reads 'ok' (frozen), but the loop hasn't ticked in > 5 ticks.
    app_mod, set_health = persist_env
    set_health(last_tick_mono=time.monotonic() - 6 * 60)
    v = app_mod._persist_health_view()
    assert v["down"] is True and v["tone"] == "bad"
    assert "not being saved" in v["text"].lower()


def test_card_red_when_success_goes_stale_even_if_loop_ticks(persist_env):
    # No guessed change counter can keep an old successful save looking green.
    app_mod, set_health = persist_env
    set_health(last_ok_mono=time.monotonic() - 6 * 60)
    v = app_mod._persist_health_view()
    assert v["down"] is True and v["tone"] == "bad"


def test_card_hidden_when_persistence_off(app_mod, monkeypatch):
    monkeypatch.setattr(app_mod, "PERSIST_DIR", "", raising=False)
    assert app_mod._persist_health_view() is None
