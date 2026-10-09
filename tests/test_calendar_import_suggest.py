"""Import suggestions (docs/CALENDAR_UX_PLAN.md P0.2): they suggest, they never decide."""
from __future__ import annotations
from datetime import date, timedelta

import calendar_import_suggest as cis


def d(title, start, owner=None, tags=(), hint=None, end=None, kind="meeting"):
    return {"title": title, "start_date": start, "end_date": end, "owner": owner, "tags": list(tags),
            "people_hint": hint, "kind": kind}


def test_a_section_named_in_the_line_suggests_that_unit():
    out = cis.suggest_owners([d("BUHC for BARMM KII (Doc Malou, Tek, Sec1)", "2026-01-26")])
    assert out[0]["owner"] == "s1" and "Section 1" in out[0]["why"]


def test_two_different_sections_in_a_line_suggest_nothing():
    assert cis.suggest_owners([d("Joint (S4: Carole, S2: Analyn)", "2026-04-27")]) == {}


def test_a_tag_one_unit_almost_owns_suggests_that_unit_for_an_unowned_item():
    owned = [d(f"PK {i}", "2026-02-02", owner="s4", tags=["PK"]) for i in range(4)]
    out = cis.suggest_owners(owned + [d("PK something", "2026-03-02", tags=["PK"])])
    assert out[4]["owner"] == "s4"


def test_a_shared_tag_suggests_nothing():
    owned = ([d("a", "2026-02-02", owner="s4", tags=["UHC"]) for _ in range(2)]
             + [d("b", "2026-02-02", owner="s1", tags=["UHC"]) for _ in range(2)])
    assert cis.suggest_owners(owned + [d("c", "2026-03-02", tags=["UHC"])]) == {}


def test_an_owned_item_is_never_given_a_suggestion():
    assert cis.suggest_owners([d("Sec 3 thing", "2026-01-26", owner="s1")]) == {}


def test_a_regular_repeat_is_suggested_as_a_series():
    start = date(2026, 6, 2)                                  # a Tuesday
    items = [d("Weekly sync", (start + timedelta(weeks=n)).isoformat()) for n in range(4)]
    out = cis.suggest_series(items)
    assert len(out) == 1 and out[0]["repeat"] == "weekly" and out[0]["indexes"] == [0, 1, 2, 3]


def test_an_irregular_repeat_is_not_suggested():
    items = [d("HSDD Monthly Mtg", x) for x in ("2026-06-26", "2026-08-07", "2026-09-03", "2026-10-02")]
    assert cis.suggest_series(items) == []


def test_a_rule_that_would_add_an_occurrence_is_not_suggested():
    items = [d("Sync", x) for x in ("2026-06-02", "2026-06-09", "2026-06-23")]      # the 16th is missing
    assert cis.suggest_series(items) == []


def test_multi_day_items_are_never_part_of_a_series():
    items = [d("Workshop", (date(2026, 6, 2) + timedelta(weeks=n)).isoformat(),
               end=(date(2026, 6, 3) + timedelta(weeks=n)).isoformat()) for n in range(4)]
    assert cis.suggest_series(items) == []
