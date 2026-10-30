"""Office memo/NOM converter contracts, activation checks and relay expansion."""
import json
import re
import shutil
import subprocess
from pathlib import Path

import pytest


@pytest.fixture(scope="module")
def office_template():
    if shutil.which("node") is None:
        pytest.skip("node is not installed")
    result = subprocess.run(["node", "tests/js/office_templates_harness.js"], capture_output=True, text=True, timeout=30)
    assert result.returncode == 0, result.stderr
    return json.loads(result.stdout)


def test_converter_keeps_one_original_and_replaces_source_personal_details(office_template):
    built = office_template["built"]
    assert built["text"].count("MEMORANDUM") == 1
    assert "SOURCE" not in built["text"]
    assert "[Reiteration" not in built["text"]
    assert set(built["expect"]) == set(re.findall(r"\{\{([a-z_]+)\}\}", built["text"]))
    assert not any(p["type"] == "T" for p in built["paragraphs"])
    bullet = next(p for p in built["paragraphs"] if p["text"] == "{{representatives}}")
    assert (bullet["type"], bullet["glyph"]) == ("L", "bullet")
    assert bullet["attrs"]["indentStart"] == 36 and bullet["attrs"]["indentFirstLine"] == 18
    assert built["writes"] == [{"TPL_invitation": "CANDIDATE", "TPLF_invitation": "CANDIDATE"}]
    # No global formatting or header/footer edit is used by the converter.
    source = Path("apps_script/activity_office_templates.gs").read_text()
    assert "formatDoc_" not in source and "getHeader(" not in source and "getFooter(" not in source


def test_source_changes_and_missing_placeholders_do_not_replace_active_template(office_template):
    for failure in office_template["failures"]:
        assert "FAILED" in failure["report"]
        assert failure["writes"] == [] and failure["active"] == "OLD"
    assert office_template["kept"]["copies"] == 0
    assert "kept" in office_template["kept"]["report"]
    assert office_template["forced"]["copies"] == 1
    assert office_template["unselected"]["writes"] == []
    assert "office template kept" in office_template["legacyRebuild"]


def test_repeated_addressees_keep_name_bold_title_indent_and_one_for_label(office_template):
    groups = office_template["groups"]
    assert [p["text"] for p in groups] == [
        "FOR:\tFIRST PERSON", "First title", "First office",
        "\tSECOND PERSON", "Second title", "Second office", "FROM: head"]
    assert groups[0]["bold"] and groups[3]["bold"]
    assert not groups[1]["bold"] and not groups[4]["bold"]
    assert groups[1]["attrs"] == groups[4]["attrs"] == {"indentStart": 180}


def test_notice_converter_preserves_grids_and_keeps_only_original(office_template):
    notice = office_template["notice"]
    assert "all placeholders present" in notice["report"]
    assert notice["text"].count("NOTICE OF MEETING") == 1
    assert "SOURCE" not in notice["text"]
    assert set(notice["expect"]) == set(re.findall(r"\{\{([a-z_]+)\}\}", notice["text"]))
    tables = [child for child in notice["children"] if child["type"] == "table"]
    assert [table["grid"] for table in tables] == [[4005, 5730], [1365, 735, 7275]]
    assert tables[0]["rows"] == [["Name", "Office"], ["{{inv_name}}", "{{inv_office}}"]]
    assert notice["children"][-1]["text"] == ""
    assert "pageBreak" not in notice["children"][-1]["attrs"]
    assert notice["writes"] == [{"TPL_notice_of_meeting": "CANDIDATE", "TPLF_notice_of_meeting": "CANDIDATE"}]
    assert "all placeholders present" in office_template["plainAgenda"]


def test_notice_refuses_unexpected_or_unflattened_source_without_activation(office_template):
    for failure in office_template["noticeFailures"]:
        assert "FAILED" in failure["report"]
        assert failure["writes"] == [] and failure["active"] == "OLD"


def test_notice_rows_and_list_blocks_fill_the_converted_tables(office_template):
    filled = office_template["noticeFilled"]
    assert "{{" not in filled["text"]
    tables = [child for child in filled["children"] if child["type"] == "table"]
    assert tables[0]["rows"] == [["Name", "Office"], ["Person One", "Office One"], ["Person Two", ""]]
    assert tables[0]["grid"] == [4005, 5730] and tables[1]["grid"] == [1365, 735, 7275]
    assert [p["text"] for p in office_template["noticeAgenda"]] == ["First topic", "Second topic"]
    assert all(p["type"] == "L" for p in office_template["noticeAgenda"])


@pytest.mark.parametrize("key,grids", [
    ("concept_note", [[7695, 1200], [1850, 7370], [1215, 7995]]),
    ("program_flow", [[2370, 4575, 2415]]),
])
def test_concept_and_program_converters_remove_source_content_and_preserve_grids(office_template, key, grids):
    converted = office_template["concepts"][key]
    assert "all placeholders present" in converted["report"]
    assert "SOURCE" not in converted["text"]
    assert set(converted["expect"]) == set(re.findall(r"\{\{([a-z_]+)\}\}", converted["text"]))
    assert [c["grid"] for c in converted["children"] if c["type"] == "table"] == grids
    assert converted["writes"] == [{"TPL_" + key: "CANDIDATE", "TPLF_" + key: "CANDIDATE"}]
    assert "{{" not in converted["filled"]["text"]
    assert [c["grid"] for c in converted["filled"]["children"] if c["type"] == "table"] == grids
    if key == "concept_note":
        tables = [c for c in converted["filled"]["children"] if c["type"] == "table"]
        assert tables[0]["rows"] == [["Participant", "Number"], ["Person One", "1"], ["Person Two", "1"], ["Estimated Total", "2"]]
        assert tables[2]["rows"] == [["Day", "Activity"], ["Day 1", "First activities"], ["Day 2", "Second activities"]]
    else:
        assert "CONCEPT NOTE" not in converted["text"]


def test_split_deletes_the_other_tab_and_keeps_the_selected_one_untouched(office_template):
    concept = office_template["concepts"]["concept_note"]["requests"]
    program = office_template["concepts"]["program_flow"]["requests"]
    assert concept == [{"deleteTab": {"tabId": "t.1"}}]
    assert program == [{"deleteTab": {"tabId": "t.0"}}]


def test_section_layout_drift_and_source_changes_leave_old_templates_selected(office_template):
    for failure in office_template["conceptFailures"]:
        assert "FAILED" in failure["report"]
        assert failure["writes"] == []


def test_external_letter_keeps_only_original_and_preserves_addressee_run_styles(office_template):
    letter = office_template["letter"]
    assert "all placeholders present" in letter["report"]
    assert letter["text"].count("Very truly yours,") == 1
    assert set(letter["expect"]) == set(re.findall(r"\{\{([a-z_]+)\}\}", letter["text"]))
    assert letter["writes"] == [{"TPL_invitation_external": "CANDIDATE", "TPLF_invitation_external": "CANDIDATE"}]
    runs = letter["children"][1]["runs"]
    assert runs == [{"text": "{{addressee_name}}", "bold": True},
                    {"text": "\n{{addressee_title}}\n{{addressee_agency}}\n{{addressee_address}}", "bold": False}]
    assert "{{" not in letter["filled"]["text"]
    assert "Activity details\nRequested representatives" in letter["filled"]["text"]
    assert letter["filled"]["children"][1]["runs"][0] == {"text": "RECIPIENT", "bold": True}


def test_changed_letter_source_does_not_replace_active_template(office_template):
    for failure in office_template["letterFailures"]:
        assert "FAILED" in failure["report"]
        assert failure["writes"] == [] and failure["active"] == "OLD"


def test_briefer_preserves_wide_grid_merged_title_repeated_vi_and_offset(office_template):
    briefer = office_template["briefer"]
    assert "all placeholders present" in briefer["report"]
    assert "SOURCE" not in briefer["text"]
    assert set(briefer["expect"]) == set(re.findall(r"\{\{([a-z_]+)\}\}", briefer["text"]))
    assert briefer["writes"] == [{"TPL_executive_briefer": "CANDIDATE", "TPLF_executive_briefer": "CANDIDATE"}]
    for children in (briefer["children"], briefer["filled"]["children"]):
        table = next(child for child in children if child["type"] == "table")
        assert table["grid"] == [2445, 8475] and sum(table["grid"]) > 9360
        assert len(table["rows"]) == 9 and table["rows"][0] == [" EXECUTIVE BRIEFER", ""]
        assert table["rows"][6][0] == "VI. Date/Venue/ References"
        assert table["rows"][7][0] == "VI. Prepared by"
        assert children[1]["attrs"]["indentStart"] == -27
    assert "{{" not in briefer["filled"]["text"]
    assert "DRAFTER\nStaff title\n\nNoted by:\n\nREVIEWER\nReviewer title" in briefer["filled"]["text"]


def test_unexpected_briefer_structure_and_signature_slots_do_not_activate(office_template):
    for failure in office_template["brieferFailures"]:
        assert "FAILED" in failure["report"]
        assert failure["writes"] == [] and failure["active"] == "OLD"


@pytest.mark.parametrize("key", ["dpo", "minutes"])
def test_office_dpo_minutes_use_actual_body_builders_without_redrawing_the_frame(office_template, key):
    template = office_template["officeBodies"][key]
    assert "all placeholders present" in template["report"]
    assert template["clears"] == 1 and template["reads"] == 2
    assert (template["font"], template["size"]) == ("Times New Roman", 12)
    assert template["writes"] == [{"TPL_" + key: "CANDIDATE", "TPLF_" + key: "CANDIDATE"}]
    assert set(template["expect"]) == set(re.findall(r"\{\{([a-z_]+)\}\}", template["text"]))
    assert "SOURCE" not in template["text"] and "MEMORANDUM" not in template["text"]
    assert "{{" not in template["filled"]["text"]
    if key == "dpo":
        assert "DEPARTMENT PERSONNEL ORDER" in template["text"]
        assert "By Authority of the Secretary of Health:" in template["text"]
        table = next(c for c in template["children"] if c["type"] == "table")
        assert table["columnWidths"] == [234, 234]
        filled_table = next(c for c in template["filled"]["children"] if c["type"] == "table")
        assert filled_table["rows"] == [["Name", "Designation"], ["Person One", "Role One"], ["Person Two", "Role Two"]]
    else:
        assert "MINUTES OF THE MEETING" in template["text"]
        assert "Action points:" in template["text"] and "Approved by:" in template["text"]
        assert "Person One\nPerson Two" in template["filled"]["text"]


def test_frame_or_source_drift_never_replaces_active_dpo_template(office_template):
    failures = office_template["officeBodyFailures"]
    assert len(failures) == 10
    for failure in failures:
        assert "FAILED" in failure["report"]
        assert failure["writes"] == [] and failure["active"] == "OLD"
