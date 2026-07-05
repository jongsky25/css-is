"""Pulse sparkline enhancement: exact-progress chips (short labels) + the
plain-language movement insight under each vital card. Pure functions — no DB."""
import dashboard_insights as di


def _pts(*pairs):
    # (label, value, n) triples -> the shape _spark_points / _spark_delta consume
    return [{"label": lab, "value": v, "n": n} for lab, v, n in pairs]


# ---- _spark_points: now carries a short month label for the chips ------------

def test_spark_points_adds_short_label():
    pts = di._spark_points(
        _pts(("March 2026", 88.0, 40), ("April 2026", 90.0, 41),
             ("May 2026", 92.0, 43), ("June 2026", 94.0, 50)),
        "pct",
    )["pts"]
    assert [p["short"] for p in pts] == ["Mar", "Apr", "May", "Jun"]
    # the rich fields the hover card + native title still rely on are intact
    assert pts[0]["shown"] == "88%" and pts[-1]["shown"] == "94%"
    assert pts[1]["n"] == 41
    assert all("x" in p and "y" in p for p in pts)


def test_spark_points_too_few():
    out = di._spark_points(_pts(("May 2026", 6.0, 3)), "mean7")
    assert out == {"poly": None, "pts": []}


# ---- _spark_delta: first->last movement, worded for laypeople ----------------

def test_spark_delta_rising_pct_is_good():
    d = di._spark_delta(
        _pts(("March 2026", 88.0, 40), ("June 2026", 94.0, 50)), "pct")
    assert d["tone"] == "good"
    assert d["text"] == "▲ Up 6 points since March 2026"


def test_spark_delta_falling_pct_is_bad():
    d = di._spark_delta(
        _pts(("March 2026", 92.0, 40), ("June 2026", 90.0, 50)), "pct")
    assert d["tone"] == "bad"
    assert d["text"] == "▼ Down 2 points since March 2026"


def test_spark_delta_steady_when_tiny():
    d = di._spark_delta(
        _pts(("March 2026", 90.4, 40), ("June 2026", 90.6, 50)), "pct")
    assert d["tone"] == "neutral"
    assert d["text"] == "Holding steady since March 2026"


def test_spark_delta_mean7_uses_one_decimal():
    d = di._spark_delta(
        _pts(("Feb 2026", 5.5, 40), ("June 2026", 5.8, 50)), "mean7")
    assert d["tone"] == "good"
    assert d["text"] == "▲ Up 0.3 since Feb 2026"


def test_spark_delta_single_point_safe_default():
    d = di._spark_delta(_pts(("June 2026", 6.0, 3)), "mean7")
    assert d == {"text": None, "tone": "neutral"}
