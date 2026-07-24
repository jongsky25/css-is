"""Standing rules (people + teams share dashboard_insights._standing).

Locks in the current design:
* QUALITY ranks on the combined Quality Index (card["quality"]["index"], 0-100) —
  the number shown — with a low-sample guard so a thin sample can't top the list.
* ENGAGEMENT ranks on a 50/50 blend of activities run and respondents reached, so
  reach counts, not just activity count.
"""
import dashboard_insights as di
import css_is_engine as eng


def _card(path, index, n, events, servqual=6.4, osq=3.5):
    """Minimal peer card with the keys _standing / _quality_rank_key read."""
    return {"path": path, "short": path, "rp": {"value": servqual},
            "ratings": n, "events": events, "adj": 0.0,
            "quality": {"index": index, "servqual": servqual, "osq": osq, "n": n}}


def test_quality_ranks_on_the_index():
    # Higher Quality Index ranks higher, regardless of respondent count (volume ≠ quality).
    a = _card("A", 92.0, 40, 8)      # highest index, fewest ratings
    b = _card("B", 90.5, 55, 9)
    c = _card("C", 88.0, 210, 14)    # lowest index, most ratings
    peers = [a, b, c]
    assert di._standing(a, peers)["quality"]["rank"] == 1
    assert di._standing(b, peers)["quality"]["rank"] == 2
    assert di._standing(c, peers)["quality"]["rank"] == 3


def test_quality_shows_index_and_components():
    a = _card("A", 91.3, 40, 8, servqual=6.55, osq=3.8)
    b = _card("B", 80.0, 40, 8)
    q = di._standing(a, [a, b])["quality"]
    assert q["my"] == 91.3                 # ranked-on index, shown
    assert q["servqual"] == 6.55           # /7 component
    assert q["osq"] == 3.8                 # /4 component
    assert q["avg"] == round((91.3 + 80.0) / 2, 1)


def test_low_sample_ranks_below_fully_rated_peers():
    # A high index from a thin sample (< N_MIN ratings) must not top quality.
    thin = _card("Thin", 99.0, eng.N_MIN - 1, 2)   # best index, too few ratings
    full = _card("Full", 90.0, 200, 10)
    peers = [thin, full]
    assert di._standing(full, peers)["quality"]["rank"] == 1
    thin_q = di._standing(thin, peers)["quality"]
    assert thin_q["rank"] == 2
    assert thin_q["low_n"] is True
    assert thin_q["my_n"] == eng.N_MIN - 1


def test_engagement_blends_activities_and_respondents():
    # A: few activities but far more respondents. B: most activities, fewest respondents.
    # Under an activities-only rule B would win engagement; the 50/50 blend flips it.
    a = _card("A", 90.0, 300, 4)     # 4 activities, 300 respondents
    b = _card("B", 90.0, 60, 12)     # 12 activities, 60 respondents
    peers = [a, b]
    # activities-only would make B #1; the blend (reach counts) puts A ahead.
    assert di._standing(a, peers)["engagement"]["rank"] == 1
    e = di._standing(a, peers)["engagement"]
    assert e["acts"] == 4 and e["resp"] == 300


def test_overall_can_diverge_from_quality_via_engagement():
    # Lowest quality but strongest engagement (most activities AND most respondents)
    # can still win overall (engagement carries 55%).
    a = _card("A", 92.0, 40, 4)
    b = _card("B", 90.0, 80, 8)
    c = _card("C", 88.0, 400, 20)    # worst quality, most activities + respondents
    peers = [a, b, c]
    s = di._standing(c, peers)
    assert s["quality"]["rank"] == 3
    assert s["engagement"]["rank"] == 1
    assert s["overall"]["rank"] == 1
