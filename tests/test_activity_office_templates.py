"""Office memo converter contract, fail-closed activation and relay paragraph groups."""
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
