"""The combined Quality Index (css_is_engine.quality_index).

Locks in: all ten satisfaction questions count (nine SERVQUAL B-items on 1-7 + the
OSQ item C on 1-4), each min-max rescaled to 0-100, equal weight per question, the
expectation question (A) excluded, and a missing OSQ falling back to the B-items.
"""
import pandas as pd
import css_is_engine as eng


def _atoms(rows):
    return pd.DataFrame([{"response_id": r, "item_id": i, "value": v, "is_na": False}
                         for (r, i, v) in rows])


def test_top_and_bottom_of_both_scales():
    # respondent 1 = every answer maxed (B=7, C=4) -> 100; respondent 2 = every answer
    # at the floor (B=1, C=1) -> 0. Mean across the two respondents = 50.
    rows = []
    for it in eng.SERVQUAL_ITEMS:
        rows += [(1, it, 7), (2, it, 1)]
    rows += [(1, "C", 4), (2, "C", 1)]
    idx, n = eng.quality_index(_atoms(rows))
    assert n == 2
    assert idx == 50.0


def test_missing_osq_falls_back_to_servqual_only():
    # No C answers at all -> score is the nine B-items only. All B=7 -> 100.
    rows = [(1, it, 7) for it in eng.SERVQUAL_ITEMS]
    idx, n = eng.quality_index(_atoms(rows))
    assert n == 1
    assert idx == 100.0


def test_expectation_A_is_excluded():
    # A (expectation) must never enter the index. All B=7, C=4, A=1 -> still 100.
    rows = [(1, it, 7) for it in eng.SERVQUAL_ITEMS] + [(1, "C", 4), (1, "A", 1)]
    idx, _ = eng.quality_index(_atoms(rows))
    assert idx == 100.0


def test_equal_weight_per_question():
    # One respondent: eight B=7, one B=1, and C=4. Each question is 1/10.
    #   B norm: 7->100, 1->0 ; C norm: 4->100.
    #   answered = eight 100s + one 0 (B) + one 100 (C) = 900/10 = 90.
    rows = [(1, it, 7) for it in eng.SERVQUAL_ITEMS[:8]] + [(1, "B9", 1), (1, "C", 4)]
    idx, _ = eng.quality_index(_atoms(rows))
    assert round(idx, 6) == 90.0


def test_na_answers_are_ignored():
    df = _atoms([(1, it, 7) for it in eng.SERVQUAL_ITEMS] + [(1, "C", 4)])
    # mark the C answer N/A -> index becomes the B-only 100, unchanged here
    df.loc[df["item_id"] == "C", "is_na"] = True
    idx, _ = eng.quality_index(df)
    assert idx == 100.0


def test_empty_slice_returns_none():
    assert eng.quality_index(_atoms([(1, "A", 5)])) == (None, 0)   # only expectation -> nothing scorable
