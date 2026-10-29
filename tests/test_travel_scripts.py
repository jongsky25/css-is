"""The Apps Script sources (relay and template maker): syntax, and the sheet logic run against a fake."""
from __future__ import annotations
import json
import pathlib
import shutil
import subprocess

import pytest

ROOT = pathlib.Path(__file__).resolve().parent.parent
node = pytest.mark.skipif(shutil.which("node") is None, reason="node is not installed")


@node
@pytest.mark.parametrize("name", ["travel_docs.gs", "travel_templates.gs"])
def test_the_scripts_parse(name, tmp_path):
    copy = tmp_path / (name + ".js")
    copy.write_text((ROOT / "apps_script" / name).read_text())
    out = subprocess.run(["node", "--check", str(copy)], capture_output=True, text=True, timeout=30)
    assert out.returncode == 0, out.stderr


@pytest.fixture(scope="module")
def harness():
    if shutil.which("node") is None:
        pytest.skip("node is not installed")
    out = subprocess.run(["node", "tests/js/sheet_harness.js"], capture_output=True, text=True, cwd=ROOT, timeout=60)
    assert out.returncode == 0, out.stderr
    return json.loads(out.stdout)


def flat(rows):
    return "\n".join(rows)


def test_cenrr_template_has_one_repeating_line_and_every_placeholder(harness):
    t = flat(harness["cenrrTemplate"])
    for k in ("employee_name", "employee_no", "office", "division", "p_date", "p_text", "p_amount", "total", "purpose", "dates",
              "dpo_ref", "printed_name", "designation", "noted_by_name", "noted_by_title"):
        assert "{{%s}}" % k in t, k
    assert "March 10, 2026" not in t and "Taxi fare" not in t and "DR. JUNE" not in t and "20240016" not in t
    assert t.count("{{p_date}}") == 1 and t.count("{{employee_name}}") == 1 and t.count("{{printed_name}}") == 1


def test_cenrr_rows_grow_and_the_form_is_filled(harness):
    rows = harness["cenrrFilled"]
    lines = [r for r in rows if r.startswith("September")]
    assert [l.split("|")[0].split(":")[0] for l in lines] == ["September 1, 2026", "September 2, 2026", "September 4, 2026"]
    assert [l.split("|")[-1] for l in lines] == ["250", "300", "120"]
    t = flat(rows)
    assert "Name of Employee: Juan Dela Cruz" in t and "Employee No. 12345" in t and "Office: Manila" in t
    assert "To attend Workshop on September 01-04, 2026 per DPO No. 2026-123" in t
    assert any(r.startswith("TOTAL") and r.endswith("670") for r in rows)
    assert "{{" not in t and "}}" not in t                                    # nothing raw is left behind
    assert "Dr. Ana Reyes" in t and "OIC-Director" in t and "Nurse II" in t


def test_cenrr_with_no_rows_leaves_no_placeholders(harness):
    t = flat(harness["emptyRows"])
    assert "{{" not in t


def test_rer_template_and_fill(harness):
    tpl = flat(harness["rerTemplate"])
    for k in ("payee_name", "payee_designation", "amount_words", "amount_figures", "ride_mode", "ride_from", "ride_to", "ride_date",
              "activity_title", "dpo_ref"):
        assert "{{%s}}" % k in tpl, k
    assert "RALIE" not in tpl and "5451" not in tpl
    assert "Fund Cluster : ______" in tpl and "RER No. : ______" in tpl            # the blanks left for handwriting stay
    filled = flat(harness["rerFilled"])
    assert "RECEIVED from MR. RALIE" not in filled and "Juan" in filled
    assert "the amount of Five Hundred Pesos (P500)" in filled                       # spot feedback #203
    assert "Taxi fare from Home to Airport" in filled and "on September 1, 2026" in filled
    assert "Rental or transportation should show inclusive dates, purpose, distance, inclusive points of travel, etc." in filled
    assert "in attendance to Workshop as per DPO No. 2026-123" in filled and "{{" not in filled


def test_the_relay_picks_sheet_or_doc_from_the_template_type():
    src = (ROOT / "apps_script" / "travel_docs.gs").read_text()
    assert "application/vnd.google-apps.spreadsheet" in src and "applyRowsSheet_" in src and "applyFieldsSheet_" in src
    assert "doc.saveAndClose()" in src                                       # the Doc path is still there


def test_the_template_maker_covers_every_template_key_the_app_asks_for():
    import travel_docs as td
    src = (ROOT / "apps_script" / "travel_templates.gs").read_text()
    # Appendix B is no longer a template of its own: a liquidation and a reimbursement are made as one Appendix A and B form
    asked = {k for k in td.DOC_TEMPLATES if k != "appendix_b"} | set(td.CLAIM_TEMPLATES.values())
    for key in asked:
        assert f"key: '{key}'" in src, key
    assert "key: 'appendix_b'" not in src


@pytest.mark.parametrize("name", ["travel_docs.gs", "travel_templates.gs"])
def test_the_scripts_use_the_real_sheets_method_names(name):
    """Google's Sheets TextFinder spells it useRegularExpression (no s); the plural is a runtime error."""
    src = (ROOT / "apps_script" / name).read_text()
    assert "useRegularExpressions" not in src


@pytest.fixture(scope="module")
def formatted():
    if shutil.which("node") is None:
        pytest.skip("node is not installed")
    out = subprocess.run(["node", "tests/js/format_harness.js"], capture_output=True, text=True, cwd=ROOT, timeout=60)
    assert out.returncode == 0, out.stderr
    return json.loads(out.stdout)


def test_titles_are_title_case_and_keep_acronyms_and_initials(formatted):
    assert formatted["titles"] == [
        "Certification of Expenses Not Requiring Receipts", "Appendix A", "Itinerary of Travel",
        "DPO and CENRR for the MC 114 Trip", "June Rose A", "Post-Travel Report", "Appendix 46 Reimbursement Expense Receipt"]


def test_only_short_lines_without_sentence_punctuation_count_as_titles(formatted):
    assert formatted["looks"] == [True, False, False, False, False, False]


def test_every_paragraph_is_times_new_roman_12_and_body_text_is_justified(formatted):
    d = formatted["doc"]
    assert all(p["font"] == "Times New Roman" and p["size"] == 12 for p in d.values())
    assert d["body"]["align"] == "justify" and d["cell"]["align"] == "justify"          # tables too
    assert d["bodyCentered"]["align"] == "center" and d["bodyRight"]["align"] == "right"  # deliberate alignment is kept
    assert d["short"]["align"] is None                                                   # short lines are left alone


def test_titles_are_bold_and_title_case_but_names_and_sentences_are_not_touched(formatted):
    d = formatted["doc"]
    assert (d["title"]["text"], d["title"]["bold"], d["title"]["align"]) == ("Post Travel Report", True, "center")
    assert d["capsLeft"]["text"] == "Certificate of Travel Completed" and d["capsLeft"]["bold"]
    assert d["dpoTitle"]["text"] == "DEPARTMENT PERSONNEL ORDER" and d["dpoTitle"]["bold"]      # spot feedback #164
    assert d["heading"]["text"] == "Overview of the Trip"
    assert d["name"]["text"] == "MAR WYNN D. BELLO, MD, MPA"                              # has punctuation: a name, not a title
    assert d["sentenceBold"]["text"].startswith("NOTE THAT THIS IS BOLD")


def test_sheets_get_the_font_and_titles_but_numbers_and_formulas_are_left(formatted):
    cells = formatted["sheet"]
    assert all(c["font"] == "Times New Roman" and c["size"] == 12 for row in cells for c in row)
    assert cells[0][0]["value"] == "Certification of Expenses Not Requiring Receipts" and cells[0][0]["weight"] == "bold"
    assert cells[2][0]["value"] == "Total" and cells[2][1]["value"] == 670
    assert cells[2][2]["value"] == "=SUM(A1)"                                           # a formula is never overwritten
    assert cells[3][0]["value"] == "MAR WYNN D. BELLO, MD"


def test_the_report_script_applies_the_letterhead_and_plain_paragraphs():
    """Spot feedback #168/#169: DPO letterhead on the report; only titles bold; one blank line of space."""
    src = open("apps_script/travel_docs.gs", encoding="utf-8").read()
    assert "req.template_key === 'travel_report'" in src and "at_letterhead_(header)" in src
    assert "setSpacingAfter(12)" in src and "p.setBold(false)" in src and "'conclusion'" in src


def test_the_report_lists_itinerary_days_outside_the_activity():
    """Spot feedback #167: the October 11 trip is in the report even though the activity starts on the 12th."""
    import travel_docs as td
    rows = [dict(td.blank_row("2026-10-11"), mode="plane", **{"from": "Manila", "to": "Cebu"}), td.blank_row("2026-10-12")]
    ctx = {"filing": {"act_start": "2026-10-12", "act_end": "2026-10-13"}, "rows": rows,
           "texts": {"day_by_day": ["October 12, 2026: Opening.", "October 13, 2026: Closing."]}}
    assert td._report_days(ctx) == ["October 11, 2026: Travelled from Manila to Cebu by plane.",
                                    "October 12, 2026: Opening.", "October 13, 2026: Closing."]


def test_every_sheet_made_for_a_row_gets_a_link():
    """Spot feedback #159: a CENRR or RER is one sheet per ride; the second and later links are shown, not just kept."""
    import travel
    assert travel.extra_doc_urls("More: https://x/1 https://x/2") == ["https://x/1", "https://x/2"]
    assert travel.extra_doc_urls(None) == [] and travel.extra_doc_urls("a paper note") == []


def test_activity_document_titles_keep_their_capitals(formatted):
    for key, title in {
        "memoTitle": "MEMORANDUM", "conceptTitle": "CONCEPT NOTE",
        "noticeTitle": "NOTICE OF MEETING", "minutesTitle": "MINUTES OF THE MEETING",
        "brieferTitle": "EXECUTIVE BRIEFER",
    }.items():
        assert formatted["doc"][key]["text"] == title
        assert formatted["doc"][key]["bold"] is True
