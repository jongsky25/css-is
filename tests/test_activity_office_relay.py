"""Increment 1 relay behavior; Google rendering remains an administrator check."""
import json
import shutil
import subprocess

import pytest


@pytest.fixture(scope="module")
def office_relay():
    if shutil.which("node") is None:
        pytest.skip("node is not installed")
    result = subprocess.run(["node", "tests/js/office_relay_harness.js"], capture_output=True, text=True, timeout=30)
    assert result.returncode == 0, result.stderr
    return json.loads(result.stdout)


def test_office_marker_preserves_formatting_only_for_the_marked_template(office_relay):
    office = office_relay["office"]
    assert office["result"]["ok"]
    assert office["calls"] == ["rows", "blocks", "fields", "save"]
    assert (office["font"], office["size"]) == ("Office font", 10)
    for key in ("unmarked", "stale"):
        result = office_relay[key]
        assert result["calls"] == ["rows", "blocks", "fields", "format", "save"]
        assert (result["font"], result["size"]) == ("Times New Roman", 12)
    assert office_relay["travel"]["calls"] == [
        "rows", "report-sections", "blocks", "fields", "format", "report-letterhead", "report-format", "save"]


def test_block_lines_preserve_list_settings_and_surrounding_content(office_relay):
    items = office_relay["list"]
    assert [item["text"] for item in items] == ["before", "First", "Second", "Third", "after"]
    for item in items[1:-1]:
        assert item["type"] == "L"
        assert (item["glyph"], item["nesting"], item["list"]) == ("BULLET", 1, "source-list")
        assert item["attrs"] == {"indent": 36, "spacing": 12}
    assert [item["text"] for item in office_relay["emptyList"]] == ["before", "", "after"]


def test_paragraph_blocks_keep_existing_behavior(office_relay):
    items = office_relay["paragraph"]
    assert [item["text"] for item in items] == ["before", "First", "Second", "after"]
    assert all(item["type"] == "P" for item in items)
    assert items[1]["attrs"] == items[2]["attrs"]
