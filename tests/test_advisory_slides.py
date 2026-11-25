"""Advisory Google Slides increment 1: the relay companion (run under Node with fake Google services)
and the app-side client (with a fake relay call). Real Slides behavior is an administrator check."""
import base64
import hashlib
import json
import shutil
import subprocess

import pytest

import advisory_slides as slides
import gdocs_relay


@pytest.fixture(scope="module")
def relay():
    if shutil.which("node") is None:
        pytest.skip("node is not installed")
    result = subprocess.run(["node", "tests/js/advisory_slides_harness.js"], capture_output=True, text=True, timeout=30)
    assert result.returncode == 0, result.stderr
    return json.loads(result.stdout)


# ---- relay (apps_script/advisory_slides.gs) ----

def test_create_keeps_one_variant_fills_text_literally_and_places_the_qr(relay):
    c = relay["create"]
    assert c["result"]["ok"] and c["result"]["qr"] == "placed" and c["result"]["unfilled"] == []
    assert c["slides"] == 1
    assert c["texts"] == ["ADVISORY 2026-1124-001", "JOAS Batch 2", "Price: $5 \\ok", ""]
    assert c["qrImage"] is True
    assert c["path"] == ["adv-7", "advisories"]


def test_create_shares_each_office_editor_once_without_email(relay):
    assert relay["create"]["shares"] == [["share", "ana@doh.gov.ph", "writer", False],
                                         ["share", "ben@doh.gov.ph", "writer", False]]


def test_create_retry_returns_the_same_file_without_a_second_copy(relay):
    assert relay["create"]["copies"] == 1
    assert relay["create"]["againId"] == relay["create"]["result"]["id"]


def test_create_reports_placeholders_left_and_a_missing_qr_box(relay):
    assert relay["unfilled"]["unfilled"] == ["dates", "venue"]
    assert relay["unfilled"]["qr"] == "no_qr_box"


def test_create_refuses_bad_input_before_copying_anything(relay):
    r = relay["refusals"]
    assert (r["outsider"], r["variant"], r["zero"], r["folder"], r["request"]) == (
        "bad_people", "bad_variant", "bad_variant", "bad_folder", "bad_request_id")
    assert r["qrKey"] == r["badKey"] == r["long"] == "bad_fields"
    assert (r["noTemplate"], r["locked"], r["unknown"]) == ("template_not_set", "busy", "unknown_action")
    assert r["copies"] == 0


def test_do_post_routes_advisory_actions_and_explains_a_missing_companion(relay):
    assert relay["route"]["info"]["ok"] and relay["route"]["info"]["version"] == 1
    assert relay["route"]["missing"] == {"ok": False, "error": "advisory_not_installed"}
    assert relay["route"]["ping"] == {"ok": True, "version": 3}         # travel_docs.gs ping (REVIEW_SHARE_VERSION)


def test_info_lists_each_variant_and_its_placeholders(relay):
    variants = relay["info"]["variants"]
    assert [v["variant"] for v in variants] == [1, 2, 3]
    assert variants[0]["placeholders"] == ["number", "title", "message", "qr"]
    assert "png_b64" not in variants[0]
    assert relay["thumbs"] == ["\x89PNG"] * 3


def test_snapshot_matches_digests_and_keeps_only_open_comments(relay):
    s = relay["snapshot"]
    assert s["ok"] and s["pdfOk"] and s["pngOk"] and s["version"] == "2"
    assert [c["id"] for c in s["comments"]] == ["c1"]
    assert s["comments"][0]["quoted"] == "Dec 15"
    assert s["comments"][0]["replies"] == [{"content": "Done", "created_time": "t2", "author": "Ana"}]


def test_snapshot_refuses_outside_files_edits_in_progress_and_failed_exports(relay):
    s = relay["snapshot"]
    assert (s["outside"], s["badId"]) == ("not_allowed", "not_allowed")
    assert s["changed"] == "changed_during_snapshot"
    assert s["exportFailed"] == "export_failed"


def test_access_sets_exactly_the_listed_people_and_keeps_the_owner(relay):
    a = relay["access"]
    assert a["perms"] == [["ana@doh.gov.ph", "commenter"], ["chief@doh.gov.ph", "commenter"],
                          ["dir@doh.gov.ph", "reader"], ["office@doh.gov.ph", "owner"]]
    assert all(entry[3] is False for entry in a["log"] if entry[0] == "share")
    assert (a["outsider"], a["masterRefused"]) == ("bad_people", "not_allowed")
    assert a["repeat"] == []                               # already right: nothing changes


def test_version_reports_the_drive_version_of_advisory_files_only(relay):
    assert relay["version"] == {"mine": "2", "outside": "not_allowed"}


# ---- client (advisory_slides.py) ----

class FakeCall:
    def __init__(self, data=None, ok=True, error=""):
        self.data, self.ok, self.error, self.calls = data or {}, ok, error, []

    def __call__(self, action, **fields):
        self.calls.append((action, fields))
        return gdocs_relay.RelayResult(self.ok, data=self.data, error=self.error)


FILE_ID = "COPY3000000000000000000000"


def snap(**over):
    pdf, png = b"%PDF-1.7 x", b"\x89PNG y"
    data = {"ok": True, "id": FILE_ID, "version": "5", "modified_time": "t",
            "pdf_b64": base64.b64encode(pdf).decode(), "pdf_sha256": hashlib.sha256(pdf).hexdigest(),
            "png_b64": base64.b64encode(png).decode(), "png_sha256": hashlib.sha256(png).hexdigest(),
            "comments": [{"id": "c1", "content": "Fix", "author": "Chief", "created_time": "t1",
                          "replies": [{"content": "Done", "author": "Ana"}]}]}
    data.update(over)
    return data


def test_fields_cleans_text_and_refuses_unknown_placeholders():
    f = slides.fields(title="  JOAS\r\nBatch 2  ", message="x" * 3000)
    assert set(f) == set(slides.TEXT_PLACEHOLDERS) and "qr" not in f
    assert f["title"] == "JOAS\nBatch 2" and f["venue"] == "" and len(f["message"]) == slides.MAX_FIELD
    with pytest.raises(ValueError):
        slides.fields(titel="typo")


def test_placeholders_match_the_relay_setup_list():
    src = open("apps_script/advisory_slides.gs", encoding="utf-8").read()
    line = next(l for l in src.splitlines() if l.startswith("const ADVISORY_PLACEHOLDERS_"))
    assert json.loads(line.split("=", 1)[1].strip().rstrip(";").replace("'", '"')) == list(slides.PLACEHOLDERS)


def test_create_sends_only_office_addresses_and_a_real_qr_png():
    call = FakeCall({"id": FILE_ID, "url": "u", "name": "n", "version": "2", "unfilled": ["venue"], "qr": "placed"})
    out = slides.create(request_id="adv-7-r1", folder_key="adv-7", variant=1, title="JOAS", link="https://e.example/x",
                        values=slides.fields(title="JOAS"), editors=["Ana@doh.gov.ph", "ana@doh.gov.ph", "x@gmail.com"],
                        call=call)
    assert out.ok and out.value.id == FILE_ID and out.value.unfilled == ["venue"] and out.value.qr == "placed"
    action, sent = call.calls[0]
    assert action == "advisory_create" and sent["editors"] == ["ana@doh.gov.ph"]
    assert base64.b64decode(sent["qr_png_b64"]).startswith(b"\x89PNG")
    no_link = FakeCall({"id": FILE_ID})
    slides.create(request_id="r", folder_key="k", variant=2, title="", values={}, call=no_link)
    assert "qr_png_b64" not in no_link.calls[0][1] and no_link.calls[0][1]["title"] == "Advisory"


def test_create_refuses_bad_ids_and_reports_relay_errors_plainly():
    with pytest.raises(ValueError):
        slides.create(request_id="a b", folder_key="k", variant=1, title="t", values={}, call=FakeCall())
    with pytest.raises(ValueError):
        slides.create(request_id="r", folder_key="k", variant=0, title="t", values={}, call=FakeCall())
    out = slides.create(request_id="r", folder_key="k", variant=1, title="t", values={},
                        call=FakeCall(ok=False, error="unreachable"))
    assert not out.ok and out.message.startswith("Google Slides could not be reached")
    assert slides.create(request_id="r", folder_key="k", variant=1, title="t", values={},
                         call=FakeCall({"id": "../x"})).error == "unconfirmed"


def test_snapshot_returns_verified_bytes_and_comments():
    out = slides.snapshot(FILE_ID, call=FakeCall(snap()))
    assert out.ok
    s = out.value
    assert s.pdf.startswith(b"%PDF") and s.png.startswith(b"\x89PNG") and s.version == "5"
    assert s.comments[0].content == "Fix" and s.comments[0].replies[0]["author"] == "Ana"


@pytest.mark.parametrize("over", [
    {"pdf_sha256": "0" * 64},                       # bytes do not match the digest
    {"png_b64": base64.b64encode(b"GIF89a").decode()},  # not a PNG
    {"pdf_b64": "!!not base64!!"},
    {"id": "SOMEOTHER000000000000000000"},          # a different file
    {"version": ""},
])
def test_snapshot_refuses_anything_that_does_not_check_out(over):
    out = slides.snapshot(FILE_ID, call=FakeCall(snap(**over)))
    assert not out.ok and out.error == "bad_snapshot"


def test_set_access_filters_addresses_and_returns_changes():
    call = FakeCall({"changed": [{"email": "a@doh.gov.ph", "role": "commenter"}]})
    out = slides.set_access(FILE_ID, editors=[], commenters=["A@doh.gov.ph", "z@yahoo.com"], readers=["d@doh.gov.ph"],
                            call=call)
    assert out.ok and out.value == [{"email": "a@doh.gov.ph", "role": "commenter"}]
    assert call.calls[0] == ("advisory_access", {"file_id": FILE_ID, "editors": [], "commenters": ["a@doh.gov.ph"],
                                                 "readers": ["d@doh.gov.ph"]})
    with pytest.raises(ValueError):
        slides.set_access("bad id", call=call)


def test_messages_are_plain_and_never_show_codes():
    for code in list(slides._MESSAGES) + ["something_new"]:
        text = slides.describe(code)
        assert "_" not in text and text.endswith(".")


def test_version_returns_the_relay_version():
    assert slides.version(FILE_ID, call=FakeCall({"id": FILE_ID, "version": "7"})).value == "7"
    assert slides.version(FILE_ID, call=FakeCall({"id": FILE_ID})).error == "unconfirmed"
    assert slides.version(FILE_ID, call=FakeCall(ok=False, error="unreachable")).error == "unreachable"
