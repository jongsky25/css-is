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


def test_section_split_restores_the_selected_footer_distance_and_letter_paper(office_template):
    concept = office_template["concepts"]["concept_note"]["requests"]
    program = office_template["concepts"]["program_flow"]["requests"]
    assert concept[0] == {"deleteContentRange": {"range": {"startIndex": 500, "endIndex": 1499}}}
    assert program[0] == {"deleteContentRange": {"range": {"startIndex": 1, "endIndex": 501}}}
    assert concept[1]["updateSectionStyle"]["sectionStyle"]["marginFooter"] == {"magnitude": 21.6, "unit": "PT"}
    assert program[1]["updateSectionStyle"]["sectionStyle"]["marginFooter"] == {"magnitude": 36, "unit": "PT"}
    for requests in (concept, program):
        assert requests[1]["updateSectionStyle"]["sectionStyle"]["useFirstPageHeaderFooter"] is True
        assert requests[2]["updateDocumentStyle"]["documentStyle"]["documentSize"] == {
            "width": {"magnitude": 612, "unit": "PT"}, "height": {"magnitude": 792, "unit": "PT"}}


def test_section_layout_drift_and_source_changes_leave_old_templates_selected(office_template):
    for failure in office_template["conceptFailures"]:
        assert "FAILED" in failure["report"]
        assert failure["writes"] == []
