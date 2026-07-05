"""Verbatim sentiment: 3-way classify_quote (appreciate / improve / mixed) and the
story_panel that credits a 'mixed' (good-but-bad) comment to BOTH columns.
Pure functions — no DB."""
import pandas as pd
import dashboard_insights as di


# ---- classify_quote ----------------------------------------------------------

def test_pure_praise_is_appreciate():
    assert di.classify_quote("Thank you, the staff were very helpful and kind.") == "appreciate"


def test_pure_complaint_is_improve():
    assert di.classify_quote("The process was slow and confusing.") == "improve"


def test_negated_positive_is_improve():
    # "not clear" — a negated praise word, no live praise alongside.
    assert di.classify_quote("The instructions were not clear at all.") == "improve"


def test_negated_negative_is_not_a_complaint():
    # "no problem" / "walang problema" must NOT read as a live complaint.
    assert di.classify_quote("No problem at all, thank you so much!") == "appreciate"
    assert di.classify_quote("Walang problema, salamat sa tulong helpful kayo.") == "appreciate"


def test_good_but_bad_is_mixed_english():
    # Praise (kind) + a live complaint ("too long" phrase) => mixed.
    assert di.classify_quote("The staff were so kind, but the wait was too long.") == "mixed"


def test_bad_but_good_is_mixed():
    # Order shouldn't matter — a complaint wrapped in thanks is still mixed.
    assert di.classify_quote("Slow service honestly, but thank you for being patient.") == "mixed"


def test_mixed_taglish():
    # Bilingual data: English praise + Filipino negative ("mabagal").
    assert di.classify_quote("Thank you very helpful staff, pero mabagal ang proseso.") == "mixed"


def test_factual_neutral_defaults_to_appreciate():
    # No live praise, no live complaint — defaults to appreciate (as before).
    assert di.classify_quote("I attended the morning session.") == "appreciate"


# ---- story_panel: mixed shows on both sides ----------------------------------

def _verb(rid, remarks=None, notes=None):
    return {"response_id": rid, "remarks": remarks, "notes": notes or {},
            "when": "2026-06-01", "form_id": "F2", "activity": "Orientation", "topic": ""}


def _texts_on_side(side):
    return {q["text"] for b in side["buckets"] for q in b["quotes"]}


def test_mixed_comment_appears_on_both_columns():
    text = "The staff were so kind, but the wait was too long."
    story = di.story_panel([_verb(1, remarks=text)])
    # one comment in, not double-counted in the total
    assert story["total"] == 1
    assert text in _texts_on_side(story["appreciate"])
    assert text in _texts_on_side(story["improve"])
    # and it carries the mixed flag for the template badge
    q = next(q for b in story["appreciate"]["buckets"] for q in b["quotes"])
    assert q["sentiment"] == "mixed"


def test_pure_sides_stay_on_one_column():
    good = "Very helpful and clear, thank you!"
    bad = "The venue was cramped and the audio was poor."
    story = di.story_panel([_verb(1, remarks=good), _verb(2, remarks=bad)])
    assert good in _texts_on_side(story["appreciate"])
    assert good not in _texts_on_side(story["improve"])
    assert bad in _texts_on_side(story["improve"])
    assert bad not in _texts_on_side(story["appreciate"])


def test_override_to_mixed_forces_both_sides():
    # A pure-praise comment manually re-tagged 'mixed' must land on both columns.
    text = "Everything was perfect, thank you!"
    story = di.story_panel([_verb(7, remarks=text)], overrides={(7, ""): "mixed"})
    assert text in _texts_on_side(story["appreciate"])
    assert text in _texts_on_side(story["improve"])
    q = next(q for b in story["improve"]["buckets"] for q in b["quotes"])
    assert q["sentiment"] == "mixed"
    assert q["overridden"] is True


def test_override_to_one_side_still_works():
    # The existing binary override path is unchanged.
    text = "The process was slow and confusing."   # auto -> improve
    story = di.story_panel([_verb(3, remarks=text)], overrides={(3, ""): "appreciate"})
    assert text in _texts_on_side(story["appreciate"])
    assert text not in _texts_on_side(story["improve"])


# ---- sentiment_trend: 3-way breakdown over time -----------------------------

def _atoms(rows):
    """Tiny atoms frame: rows of (response_id, quarter), all survey_type 2."""
    return pd.DataFrame([{"survey_type": 2, "response_id": r, "quarter": q}
                         for r, q in rows])


def _breakdown_shares(bd, period_idx):
    return {s["name"]: s["points"][period_idx]["value"] for s in bd["series_raw"]}


def test_breakdown_shares_sum_to_100_per_period():
    atoms = _atoms([(1, "2025-Q1"), (2, "2025-Q1"), (3, "2025-Q1"),
                    (4, "2025-Q2"), (5, "2025-Q2")])
    verb = [_verb(1, remarks="Excellent, very helpful and clear"),
            _verb(2, remarks="The process was slow and confusing"),
            _verb(3, remarks="The staff were so kind, but the wait was too long"),  # mixed
            _verb(4, remarks="Wonderful, learned a lot"),
            _verb(5, remarks="Cramped venue and poor audio")]
    r = di.sentiment_trend(atoms, verb, 2, "quarterly")
    bd = r["breakdown"]
    assert bd["has_data"] is True
    assert [s["name"] for s in bd["series_raw"]] == \
        ["Appreciation", "Areas to improve", "Mixed (good-but-bad)"]
    for i in range(2):                               # both quarters total 100%
        assert round(sum(_breakdown_shares(bd, i).values()), 6) == 100.0


def test_breakdown_does_not_change_binary_series():
    # The long-standing binary "% positive" line must be byte-identical: it counts
    # only appreciate, with a mixed-classified comment as not-positive.
    atoms = _atoms([(1, "2025-Q1"), (2, "2025-Q1"),
                    (3, "2025-Q1"), (4, "2025-Q1")])
    verb = [_verb(1, remarks="Very helpful and clear, thank you"),     # appreciate
            _verb(2, remarks="Pure praise, excellent session"),        # appreciate
            _verb(3, remarks="Slow and confusing"),                    # improve
            _verb(4, remarks="The staff were so kind, but the wait was too long")]  # mixed
    r = di.sentiment_trend(atoms, verb, 2, "quarterly")
    # 2 of 4 read as appreciation for the binary line (mixed is not positive)
    assert round(r["series"][0]["value"], 1) == 50.0
    assert r["series"][0]["n"] == 4
    # and the breakdown splits the other half into improve + mixed
    shares = _breakdown_shares(r["breakdown"], 0)
    assert shares == {"Appreciation": 50.0, "Areas to improve": 25.0,
                      "Mixed (good-but-bad)": 25.0}


def test_override_mixed_lands_in_mixed_bucket_not_positive():
    atoms = _atoms([(9, "2025-Q1"), (10, "2025-Q1")])
    verb = [_verb(9, remarks="Everything was perfect, thank you"),     # auto appreciate
            _verb(10, remarks="Pure praise too")]                      # auto appreciate
    # Force rid 9 to mixed: it must leave the appreciate bucket for mixed, and
    # must NOT count toward the binary positive line (which uses text class).
    r = di.sentiment_trend(atoms, verb, 2, "quarterly",
                           overrides={(9, ""): "mixed"})
    shares = _breakdown_shares(r["breakdown"], 0)
    assert shares["Mixed (good-but-bad)"] == 50.0
    assert shares["Appreciation"] == 50.0


def test_breakdown_read_flags_rising_improvement():
    # improve share climbs 0% -> 100% across two quarters => "tilting toward areas
    # to improve" (tone bad).
    atoms = _atoms([(1, "2025-Q1"), (2, "2025-Q2")])
    verb = [_verb(1, remarks="Very helpful and clear, thank you"),
            _verb(2, remarks="Slow, confusing and poorly organised")]
    bd = di.sentiment_trend(atoms, verb, 2, "quarterly")["breakdown"]
    assert bd["read"]["tone"] == "bad"


def test_breakdown_read_neutral_with_single_period():
    atoms = _atoms([(1, "2025-Q1"), (2, "2025-Q1")])
    verb = [_verb(1, remarks="Helpful"), _verb(2, remarks="Slow")]
    bd = di.sentiment_trend(atoms, verb, 2, "quarterly")["breakdown"]
    assert bd["read"]["tone"] == "neutral"


def test_sentiment_trend_no_comments_has_no_data():
    atoms = _atoms([(1, "2025-Q1")])
    assert di.sentiment_trend(atoms, [], 2, "quarterly") == {"has_data": False}
