"""Office calendar importer, the pure .docx parser (increment B1). The Word file is
built in the test (python-docx) with the same shape as the bureau's: one table per
month, Sunday first, owner = run highlight / shading, pastel cell tints = noise."""
from __future__ import annotations
import calendar
import io
from datetime import date

import docx
import pytest
from docx.oxml import OxmlElement
from docx.oxml.ns import qn

import calendar_import as ci

Y = 2026


def _color_run(par, text, color):
    run = par.add_run(text)
    if color:
        kind, val = color.split(":")
        rpr = run._r.get_or_add_rPr()
        el = OxmlElement("w:highlight" if kind == "hl" else "w:shd")
        if kind == "hl":
            el.set(qn("w:val"), val)
        else:
            el.set(qn("w:val"), "clear"); el.set(qn("w:fill"), val)
        rpr.append(el)
    return run


def month_table(doc, month, days, year=Y, title=None):
    """days: {day_number: [line | (line, 'hl:cyan') | ('shd:ff9900')…]} -> one month table."""
    cal = calendar.Calendar(firstweekday=6).monthdayscalendar(year, month)
    t = doc.add_table(rows=2 + len(cal), cols=7)
    top = t.rows[0].cells[0].merge(t.rows[0].cells[6])
    top.text = title or f"{calendar.month_name[month].upper()} {year}"
    for i, name in enumerate(("SUNDAY", "MONDAY", "TUESDAY", "WEDNESDAY", "THURSDAY",
                              "FRIDAY", "SATURDAY")):
        t.rows[1].cells[i].text = name
    for r, week in enumerate(cal):
        for c, d in enumerate(week):
            if not d:
                continue
            cell = t.rows[2 + r].cells[c]
            cell.paragraphs[0].text = str(d)
            for line in days.get(d, []):
                text, color = (line, None) if isinstance(line, str) else line
                _color_run(cell.add_paragraph(), text, color)
    return t


def build(*tables):
    """tables: (month, {day: lines}) pairs -> an in-memory .docx and its parse."""
    doc = docx.Document()
    for month, days in tables:
        month_table(doc, month, days)
        doc.add_paragraph()
    buf = io.BytesIO(); doc.save(buf); buf.seek(0)
    return ci.parse(buf)


def one(text, color="hl:cyan", day=6, month=10):
    res = build((month, {day: [(text, color)]}))
    assert len(res.drafts) == 1, [d.title for d in res.drafts]
    return res.drafts[0]


# ----------------------------------------------------------------- owners ---

@pytest.mark.parametrize("color, owner", [
    ("hl:green", "bureau"), ("hl:yellow", "s1"), ("hl:magenta", "s2"),
    ("shd:ff9900", "s3"), ("hl:cyan", "s4"),
    ("shd:6fa8dc", "s5"), ("shd:9fc5e8", "s5"), ("shd:c9daf8", "s5"), ("shd:4a86e8", "s5"),
    ("hl:blue", "s5"),
])
def test_owner_comes_from_the_colour_legend(color, owner):
    assert one("Some Meeting", color).owner == owner


@pytest.mark.parametrize("color", [None, "hl:white", "shd:e2efd9", "shd:fbe5d5", "shd:ededed",
                                   "shd:deebf6", "shd:fff2cc", "shd:d9e2f3", "shd:9900ff"])
def test_pastel_tints_and_unknown_colours_mean_no_owner(color):
    d = one("Some Meeting", color)
    assert d.owner is None and any("No owner" in w for w in d.warnings)


def test_unmapped_colours_are_reported_for_the_mapping_screen():
    res = build((10, {6: [("A meeting", "shd:9900ff"), ("B meeting", "hl:white")]}))
    assert res.unmapped_colors == {"shd:9900ff": 1, "hl:white": 1}


def test_the_colour_covering_most_of_the_text_wins():
    doc = docx.Document()
    t = month_table(doc, 10, {})
    cell = t.rows[3].cells[2]                       # Tue Oct 6
    par = cell.add_paragraph()
    _color_run(par, "Big yellow part of the line ", "hl:yellow")
    _color_run(par, "(1pm)", "hl:cyan")
    buf = io.BytesIO(); doc.save(buf); buf.seek(0)
    assert ci.parse(buf).drafts[0].owner == "s1"


# ------------------------------------------------------------------- days ---

def test_dates_come_from_the_day_number_and_month_title():
    res = build((10, {6: ["Tue thing"], 31: ["End of month"]}), (11, {1: ["Next month"]}))
    assert [(d.start_date, d.title) for d in res.drafts] == [
        ("2026-10-06", "Tue thing"), ("2026-10-31", "End of month"), ("2026-11-01", "Next month")]
    assert res.stats["tables"] == 2 and not res.warnings


def test_holiday_lines_are_set_aside_but_a_work_line_with_a_day_number_is_not():
    doc = docx.Document()
    t = month_table(doc, 10, {})
    t.rows[2].cells[4].paragraphs[0].text = "1  New Year's Day"       # Thu, number + holiday text
    t.rows[3].cells[1].paragraphs[0].text = "5 Refresher training on the TOT"
    buf = io.BytesIO(); doc.save(buf); buf.seek(0)
    res = ci.parse(buf)
    assert [(h["date"], h["name"]) for h in res.holidays] == [("2026-10-01", "New Year's Day")]
    assert [(d.start_date, d.title) for d in res.drafts] == [("2026-10-05", "Refresher training on the TOT")]


def test_a_named_month_in_a_cell_is_the_next_month_spill_over():
    res = build((8, {31: ["Last day thing"]}))
    doc = docx.Document()
    t = month_table(doc, 8, {})
    t.rows[7].cells[1].paragraphs[0].text = "SEPTEMBER 1"
    _color_run(t.rows[7].cells[1].add_paragraph(), "Locking of LHS ML IS Access", "hl:green")
    buf = io.BytesIO(); doc.save(buf); buf.seek(0)
    assert [(d.start_date, d.title) for d in ci.parse(buf).drafts] == [
        ("2026-09-01", "Locking of LHS ML IS Access")]
    assert res.drafts[0].start_date == "2026-08-31"


def test_december_spills_into_january_of_the_next_year():
    doc = docx.Document()
    t = month_table(doc, 12, {})
    t.rows[6].cells[5].paragraphs[0].text = "JANUARY 1"
    t.rows[6].cells[5].add_paragraph("New thing")
    buf = io.BytesIO(); doc.save(buf); buf.seek(0)
    assert ci.parse(buf).drafts[0].start_date == "2027-01-01"


def test_legend_noise_and_stray_marks_are_ignored():
    res = build((10, {6: ["Activity Legend:", "Bureau", "Section 1  Section 2", "X", "—", "Real thing"]}))
    assert [d.title for d in res.drafts] == ["Real thing"]


def test_a_table_without_a_month_title_is_skipped_with_a_warning():
    doc = docx.Document()
    month_table(doc, 10, {6: ["Lost"]}, title="Something else")
    buf = io.BytesIO(); doc.save(buf); buf.seek(0)
    res = ci.parse(buf)
    assert res.drafts == [] and any("without a 'MONTH YYYY'" in w for w in res.warnings)


def test_a_day_in_the_wrong_weekday_column_is_warned_about():
    doc = docx.Document()
    t = month_table(doc, 10, {})
    t.rows[3].cells[3].paragraphs[0].text = "6"          # the 6th is a Tuesday, this is Wednesday's cell
    t.rows[3].cells[3].add_paragraph("Shifted")
    buf = io.BytesIO(); doc.save(buf); buf.seek(0)
    res = ci.parse(buf)
    assert res.drafts[0].start_date == "2026-10-06" and any("Wed column" in w for w in res.warnings)


def test_an_impossible_date_is_skipped_not_fatal():
    doc = docx.Document()
    t = month_table(doc, 2, {})
    t.rows[2].cells[1].paragraphs[0].text = "30"
    t.rows[2].cells[1].add_paragraph("Never")
    buf = io.BytesIO(); doc.save(buf); buf.seek(0)
    res = ci.parse(buf)
    assert res.drafts == [] and any("not a real date" in w for w in res.warnings)


def test_a_path_works_as_well_as_a_file_object(tmp_path):
    doc = docx.Document(); month_table(doc, 10, {6: ["On disk"]})
    p = tmp_path / "cal.docx"; doc.save(str(p))
    assert ci.parse(str(p)).drafts[0].title == "On disk"


# ------------------------------------------------------------------ lines ---

def test_wrapped_fragments_are_joined_to_their_activity():
    res = build((10, {6: ["Orientation on GPH VL - (Pampanga)", "(S4: Carole, S2: Analyn)",
                          "Analyn, Jas, Wardah)", "A separate meeting"]}))
    assert sorted(d.title for d in res.drafts) == [
        "A separate meeting",
        "Orientation on GPH VL - (Pampanga) (S4: Carole, S2: Analyn) Analyn, Jas, Wardah)"]


def test_a_line_break_inside_a_paragraph_makes_two_lines():
    doc = docx.Document()
    t = month_table(doc, 10, {})
    par = t.rows[3].cells[2].add_paragraph()
    _color_run(par, "First meeting", "hl:cyan"); par.add_run().add_break()
    _color_run(par, "Second meeting", "hl:yellow")
    buf = io.BytesIO(); doc.save(buf); buf.seek(0)
    assert [(d.title, d.owner) for d in ci.parse(buf).drafts] == [
        ("First meeting", "s4"), ("Second meeting", "s1")]


# ------------------------------------------------------------------ times ---

@pytest.mark.parametrize("text, start, end, note, title", [
    ("130pm: BHW mtng with UP", "13:30", None, "130pm", "BHW mtng with UP"),
    ("10am: Section 1 Mtg", "10:00", None, "10am", "Section 1 Mtg"),
    ("10an: Senate hearing", "10:00", None, "10an", "Senate hearing"),
    ("Alignment Meeting for 2027 Planning (1:30-3pm)", "13:30", "15:00", "1:30-3pm",
     "Alignment Meeting for 2027 Planning"),
    ("Prep meeting for the Natl TWG 4:30 PM", "16:30", None, "4:30 PM", "Prep meeting for the Natl TWG"),
    ("9-12 Review of CHD proposals", "09:00", "12:00", "9-12", "Review of CHD proposals"),
    ("Meeting with Asec. Domingo for ZBB policy 8-10AM", "08:00", "10:00", "8-10AM",
     "Meeting with Asec. Domingo for ZBB policy"),
    ("4th TWG (9:00 AM - 12:00 NN)", "09:00", "12:00", "9:00 AM - 12:00 NN", "4th TWG"),
    ("330PM Onboarding on SHF Tool", "15:30", None, "330PM", "Onboarding on SHF Tool"),
    ("Consultation 1-4PM", "13:00", "16:00", "1-4PM", "Consultation"),
    ("Workshop 11-1pm", "11:00", "13:00", "11-1pm", "Workshop"),
    ("Sulu TWG meeting 9-12 AM", "09:00", "12:00", "9-12 AM", "Sulu TWG meeting"),
])
def test_time_expressions_become_start_and_end(text, start, end, note, title):
    d = one(text)
    assert (d.start_time, d.end_time, d.time_note, d.title) == (start, end, note, title)


@pytest.mark.parametrize("text, note", [
    ("AM: Meeting with WHO", "AM"), ("PM: Online Orientation on FPE", "PM"),
    ("LIPH IS Orientation for CHDs online AM", "AM"),
])
def test_a_bare_part_of_day_is_kept_as_a_note_only(text, note):
    d = one(text)
    assert (d.start_time, d.end_time, d.time_note) == (None, None, note)


@pytest.mark.parametrize("text", [
    "Orientation on LIPH IS 3.0", "Amendment of AO 2021-0040", "DILG MC No. 2026-009 roll out",
    "CHD6 PK Consultation", "Q3 review", "Section 1 Mtg", "GC8 RSSH Module Workshop", "ICD-11 training",
    "Meeting at 12 Main St", "BLHSD Mancom 2",
])
def test_numbers_that_are_not_times_are_left_alone(text):
    d = one(text)
    assert d.start_time is None and d.end_time is None and d.title.startswith(text[:8])


# ------------------------------------------------------------------ guesses ---

@pytest.mark.parametrize("text, kind", [
    ("MORATORIUM MR SIA", "banner"), ("DUE: Q1 OPCR MOA", "deadline"),
    ("BLHSD IQA Team meeting", "audit_mr"), ("Q3 MR", "audit_mr"), ("Strat Planning", "audit_mr"),
    ("Technical Assistance on PK (Palawan)", "travel"), ("LGU HSC Monitoring in BARMM", "travel"),
    ("HSRP Field Visit Bohol", "travel"), ("Research Data Collection Aklan", "travel"),
    ("Orientation on LHB Guidebook", "training"), ("Writeshop on the AO", "training"),
    ("Public Health Conference 2026", "training"), ("Consultation on SHF Implementation", "training"),
    ("Meeting with WHO", "meeting"), ("Consultation Meeting on LGU ZBB", "meeting"),
    ("Pretesting of ZBB Monitoring Tools (online)", "meeting"),
    ("Something unclear", "meeting"),
])
def test_kind_is_guessed_from_the_words(text, kind):
    assert one(text).kind == kind


def test_status_modality_and_tags():
    d = one("Epimetrics Presentation (Tentative)")
    assert (d.status, d.title) == ("tentative", "Epimetrics Presentation")
    assert one("ISO Surveillance Closing Meeting online (POSTPONED)").status == "postponed"
    assert one("Regional Consultation for IP Health - Pending").status == "tentative"
    assert one("Tentative: SCMS Audit by Auditors").title == "SCMS Audit by Auditors"
    d = one("TUPAD-(Tentative 9-12 am)")
    assert (d.title, d.status, d.start_time, d.end_time) == ("TUPAD", "tentative", "09:00", "12:00")
    assert one("Equity Workshop [TENTATIVE]").title == "Equity Workshop"
    assert one("Meeting with DOH Rep Coordinators (Online)").modality == "online"
    assert one("Orientation (face to face)").modality == "f2f"
    assert one("Meeting with WHO").modality is None
    assert one("PK and BHW pilot for LHS ML and ZBB in Sulu").tags == ["PK", "BHW", "LHS ML", "ZBB", "Sulu"]


@pytest.mark.parametrize("text, hint, tokens", [
    ("Technical Assistance on PK (Palawan) - Sir Jong, Doc AC", "Sir Jong, Doc AC", ["Sir Jong", "Doc AC"]),
    ("EBDM for SGA (Malou, Fe)", "Malou, Fe", ["Malou", "Fe"]),
    ("Policy Forum in La Union (June and Mimi)", "June and Mimi", ["June", "Mimi"]),
    ("HSRP Field Visit Bohol (S4: Carole, S2: Analyn)", "S4: Carole, S2: Analyn", ["Carole", "Analyn"]),
    ("BHW Pilot (Sir Jong/Riza Desten/Vlanche)", "Sir Jong/Riza Desten/Vlanche", ["Sir Jong", "Riza Desten", "Vlanche"]),
    ("Meeting with DOH Rep Coordinators (Online)", None, []),
    ("AMMB - MANCOM", None, []),
    ("Meeting with WHO", None, []),
])
def test_people_are_kept_as_a_hint_for_the_resolver(text, hint, tokens):
    d = one(text)
    assert (d.people_hint, d.people_tokens) == (hint, tokens)
    assert d.title.startswith(text[:10])                 # the title keeps the words as written


# ---------------------------------------------------------------- merging ---

def test_the_same_activity_on_consecutive_weekdays_is_one_range():
    res = build((10, {5: [("TA Palawan", "hl:cyan")], 6: [("TA Palawan", "hl:cyan")],
                      7: [("TA Palawan", "hl:cyan")]}))
    (d,) = res.drafts
    assert (d.start_date, d.end_date) == ("2026-10-05", "2026-10-07") and len(d.raw) == 3
    assert res.stats["merged"] == 2


def test_a_weekend_between_two_days_does_not_break_a_range():
    res = build((10, {9: ["Planning"], 12: ["Planning"], 13: ["Planning"]}))     # Fri, Mon, Tue
    assert [(d.start_date, d.end_date) for d in res.drafts] == [("2026-10-09", "2026-10-13")]


def test_a_holiday_between_two_days_does_not_break_a_range():
    doc = docx.Document()
    t = month_table(doc, 6, {11: ["Workshop"], 15: ["Workshop"]})                # Thu, Mon
    t.rows[3].cells[5].paragraphs[0].text = "12  Independence Day"              # Fri 12 holiday
    buf = io.BytesIO(); doc.save(buf); buf.seek(0)
    assert [(d.start_date, d.end_date) for d in ci.parse(buf).drafts] == [("2026-06-11", "2026-06-15")]


def test_a_working_day_gap_breaks_a_range():
    res = build((10, {5: ["Weekly sync"], 7: ["Weekly sync"]}))                  # Wed 6 missing
    assert [(d.start_date, d.end_date) for d in res.drafts] == [
        ("2026-10-05", None), ("2026-10-07", None)]


def test_a_weekly_meeting_is_not_merged_into_one_long_range():
    res = build((10, {6: ["HSDD Monthly Mtg"], 13: ["HSDD Monthly Mtg"]}))
    assert len(res.drafts) == 2


def test_ranges_cross_month_tables():
    res = build((1, {29: ["Pilot"], 30: ["Pilot"]}), (2, {2: ["Pilot"], 3: ["Pilot"]}))   # Thu, Fri, Mon, Tue
    assert [(d.start_date, d.end_date) for d in res.drafts] == [("2026-01-29", "2026-02-03")]


def test_a_different_place_is_a_different_activity():
    res = build((4, {6: ["Technical Assistance on PK (MOH-BARMM - Tawi Tawi)"],
                     7: ["Technical Assistance on PK (MOH-BARMM - Tawi Tawi)"],
                     13: ["Technical Assistance on PK (MOH-BARMM - Basilan)"],
                     14: ["Technical Assistance on PK (MOH-BARMM - Basilan)"]}))
    assert [(d.start_date, d.end_date) for d in res.drafts] == [
        ("2026-04-06", "2026-04-07"), ("2026-04-13", "2026-04-14")]


def test_typo_variants_merge_and_are_reported():
    res = build((2, {23: ["Strat Planning"], 24: ["Strat Plannin"], 25: ["Strat Planningv"],
                     26: ["Strat Planning"]}))
    (d,) = res.drafts
    assert d.title == "Strat Planning" and (d.start_date, d.end_date) == ("2026-02-23", "2026-02-26")
    assert any("Spelled differently" in w and "Strat Plannin" in w for w in d.warnings)


def test_spacing_and_punctuation_differences_are_not_worth_a_warning():
    res = build((7, {20: ["LGU HSC Monitoring in BARMM (MDN - Malou, Cha)"],
                     21: ["LGU HSC Monitoring in BARMM (MDN- Malou, Cha)"]}))
    (d,) = res.drafts
    assert d.end_date == "2026-07-21" and not any("Spelled" in w for w in d.warnings)


def test_the_same_line_twice_in_one_cell_is_collapsed():
    res = build((10, {6: ["Twice", "Twice"]}))
    assert len(res.drafts) == 1 and res.drafts[0].end_date is None


def test_owner_by_majority_with_a_warning_when_colours_disagree():
    res = build((10, {5: [("Joint thing", "hl:cyan")], 6: [("Joint thing", "hl:cyan")],
                      7: [("Joint thing", "hl:yellow")]}))
    (d,) = res.drafts
    assert d.owner == "s4" and any("different owners" in w for w in d.warnings)


def test_time_comes_from_the_first_day_of_a_range():
    res = build((10, {5: ["9am: Workshop"], 6: ["Workshop"]}))
    (d,) = res.drafts
    assert (d.start_time, d.title) == ("09:00", "Workshop")


# ------------------------------------------------------------- import keys ---

def test_import_keys_are_stable_across_parses_and_unique_per_draft():
    args = [(10, {5: ["Alpha"], 6: ["Alpha"], 13: ["Alpha"], 7: ["Beta"]})]
    a, b = build(*args), build(*args)
    assert [d.import_key for d in a.drafts] == [d.import_key for d in b.drafts]
    keys = [d.import_key for d in a.drafts]
    assert len(set(keys)) == len(keys) == 3 and all(k.startswith("docx:") for k in keys)


def test_drafts_are_sorted_and_serialisable():
    res = build((10, {13: ["Beta sync"], 6: ["Alpha sync"]}))
    assert [d.start_date for d in res.drafts] == ["2026-10-06", "2026-10-13"]
    assert res.drafts[0].to_dict()["title"] == "Alpha sync"
    assert res.stats["drafts"] == 2 and res.stats["by_owner"] == {"none": 2}


# ------------------------------------- CY 2026 file shapes (docs/CALENDAR_UX_PLAN.md P0.1) ---

def test_mr_sia_is_measles_rubella_not_a_management_review():
    assert one("Orientation on LIPH IS for MR SIA CHDs & LGUs").kind == "training"
    assert one("LIPH IS Orientation for non-MR SIA CHDs online").kind == "training"
    assert one("Q2 MR").kind == "audit_mr"             # a real management review stays one


def test_a_link_in_the_line_becomes_the_meeting_url_not_part_of_the_title():
    d = one("Learning Exchange Session on LHSI Meeting Link: https://bit.ly/LHSI-LES")
    assert d.meeting_url == "https://bit.ly/LHSI-LES"
    assert d.title == "Learning Exchange Session on LHSI"


def test_an_implausible_early_time_is_not_kept_and_is_flagged():
    d = one("Technical Discussions on the BUHC - Subprogram 3 AM")
    assert d.start_time is None
    assert any("3 AM" in w for w in d.warnings)


def test_a_bare_time_left_in_the_title_is_flagged_not_guessed():
    d = one("PK TWG 10-12")
    assert d.start_time is None and d.time_note is None
    assert any("10-12" in w for w in d.warnings)
    assert not [w for w in one("PK TWG", "hl:cyan").warnings if "time" in w.lower()]


def test_a_leftover_fragment_title_is_flagged():
    d = one("8:30-3pm and OOP")
    assert any("fragment" in w for w in d.warnings)


def test_days_that_differ_by_a_whole_word_are_flagged_as_possibly_different_activities():
    res = build((8, {3: [("LGU HSC Monitoring in BARMM (LDS - Arlene)", "shd:6fa8dc")],
                     4: [("LGU HSC Monitoring in BARMM (SGA - Arlene)", "shd:6fa8dc")]}))
    assert len(res.drafts) == 1
    assert any("different activities" in w for w in res.drafts[0].warnings)


def test_a_holiday_that_is_a_bare_name_is_set_aside():
    res = build((12, {8: [("Immaculate Concepcion of Mary", "hl:green")]}))
    assert res.drafts == [] and res.holidays[0]["date"] == "2026-12-08"


# ------------------------------- names written without brackets (CALENDAR_UX_PLAN P0.5) ---

@pytest.mark.parametrize("line, names", [
    ("BHW Mtg - Mindanao Cluster by UniGlobal in Davao City- Riza and Mae", ["Riza", "Mae"]),
    ("BHW Connect v2 Pilot Test in Bicol_Sir Jong/Riza Desten/Vlanche", ["Jong", "Riza", "Desten", "Vlanche"]),
    ("NEHP WS Baguio-Riza", ["Riza"]),
    ("UNICEF mtg_IMCI_BHW WS 2 Riza Doc Malou", ["Riza", "Malou"]),
    ("BHW Summit CHD sir Jong Riza and Mae", ["Mae", "Jong", "Riza"]),
])
def test_known_names_at_the_end_of_a_line_are_captured_without_brackets(line, names):
    assert sorted(one(line).people_tokens) == sorted(names)


def test_a_name_in_the_middle_of_a_line_or_a_place_is_not_taken_for_a_person():
    assert one("Riza orientation for the BHW Coordinators").people_tokens == []
    assert one("AOP Monitoring in Northern Mindanao").people_tokens == []
    assert one("Meeting with MM CHD").people_tokens == []              # "MM CHD" is a region, not a person


def test_a_name_already_found_in_brackets_is_not_added_twice():
    assert one("BHW Pilot Test (Riza, Mae)").people_tokens == ["Riza", "Mae"]
