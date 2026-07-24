"""Rating-quality standing rules (people + teams share dashboard_insights._standing).

Locks in the transparency fix: the QUALITY axis ranks on the average rating people
actually see (to 3 decimals), NOT on the volume-adjusted `adj` score — so the rank
matches the number on the card. Volume lives only on the engagement axis, with a
low-sample guard so a thin sample can't top the list.
"""
import dashboard_insights as di
import css_is_engine as eng


def _card(path, raw, n, events):
    """Minimal peer card with the keys _standing / _quality_rank_key read."""
    return {"path": path, "short": path, "rp": {"value": raw},
            "ratings": n, "events": events, "adj": 0.0}


def test_quality_ranks_on_raw_average_not_volume():
    # All three display 6.4 at 1 dp; they differ only at the 3rd decimal. The higher
    # average must rank higher REGARDLESS of respondent count (volume ≠ quality).
    a = _card("A", 6.44, 40, 8)     # highest avg, fewest ratings
    b = _card("B", 6.41, 55, 9)
    c = _card("C", 6.38, 210, 14)   # lowest avg, most ratings
    peers = [a, b, c]
    assert di._standing(a, peers)["quality"]["rank"] == 1
    assert di._standing(b, peers)["quality"]["rank"] == 2
    assert di._standing(c, peers)["quality"]["rank"] == 3


def test_low_sample_ranks_below_fully_rated_peers():
    # A high average from a thin sample (< N_MIN ratings) must not top the quality
    # rank — it sorts below every peer with a full sample.
    thin = _card("Thin", 6.99, eng.N_MIN - 1, 2)   # best avg, too few ratings
    full = _card("Full", 6.40, 200, 10)
    peers = [thin, full]
    assert di._standing(full, peers)["quality"]["rank"] == 1
    thin_q = di._standing(thin, peers)["quality"]
    assert thin_q["rank"] == 2
    assert thin_q["low_n"] is True
    assert thin_q["my_n"] == eng.N_MIN - 1


def test_quality_fields_carry_three_decimals():
    a = _card("A", 6.444, 40, 8)
    b = _card("B", 6.111, 40, 8)
    q = di._standing(a, [a, b])["quality"]
    # avg = mean(6.444, 6.111) = 6.2775 -> rounded to 3 dp; my keeps 3 dp precision.
    assert q["avg"] == round((6.444 + 6.111) / 2, 3)
    assert q["my"] == 6.444
    assert round(q["diff"], 3) == q["diff"]


def test_overall_can_outrank_quality_via_engagement():
    # The classic case: the unit with the LOWEST quality but the MOST activities
    # still wins overall, because overall is engagement-weighted (55%). Quality and
    # overall ranks legitimately differ — and quality now tracks the visible average.
    a = _card("A", 6.44, 40, 8)
    b = _card("B", 6.41, 55, 9)
    c = _card("C", 6.38, 210, 14)   # worst quality, most activities
    peers = [a, b, c]
    s = di._standing(c, peers)
    assert s["quality"]["rank"] == 3        # last on quality (lowest average)
    assert s["engagement"]["rank"] == 1     # first on volume
    assert s["overall"]["rank"] == 1        # first overall (engagement premium)
