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
