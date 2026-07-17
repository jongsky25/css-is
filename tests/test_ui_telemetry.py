"""
Passive UX telemetry — sanitizer + route-mask unit tests (docs/UX_TELEMETRY_HANDOFF_PLAN.md).

Pure-function tests for ui_telemetry.py, no DB — mirrors the edge cases OFIS's own
__tests__/telemetry.ts suite covers for the reference implementation being ported
(sanitizeText / maskRoute): whitespace collapse, digit masking, length cap, root
route, empty input, query/hash stripped, origin stripped, static path untouched.
"""
import ui_telemetry as ui_tel


# ---- sanitize_text -----------------------------------------------------------

def test_sanitize_text_empty_is_none():
    assert ui_tel.sanitize_text("") is None
    assert ui_tel.sanitize_text(None) is None
    assert ui_tel.sanitize_text("   ") is None


def test_sanitize_text_collapses_whitespace():
    assert ui_tel.sanitize_text("  a\n  b   c ") == "a b c"


def test_sanitize_text_masks_digit_runs():
    assert ui_tel.sanitize_text("Total 1,234") == "Total 1,###"
    assert ui_tel.sanitize_text("attendee 90210") == "attendee ###"


def test_sanitize_text_keeps_short_numbers():
    assert ui_tel.sanitize_text("Q2 42") == "Q2 42"


def test_sanitize_text_caps_length():
    out = ui_tel.sanitize_text("x" * 300)
    assert len(out) == 161  # 160 + the ellipsis char
    assert out.endswith("…")


# ---- sanitize_selector --------------------------------------------------------

def test_sanitize_selector_empty_is_none():
    assert ui_tel.sanitize_selector("") is None
    assert ui_tel.sanitize_selector(None) is None


def test_sanitize_selector_caps_length():
    out = ui_tel.sanitize_selector("a" * 1500)
    assert len(out) == ui_tel.MAX_SELECTOR


# ---- mask_route ----------------------------------------------------------------

def test_mask_route_root_stays_root():
    assert ui_tel.mask_route("/") == "/"


def test_mask_route_empty_is_root():
    assert ui_tel.mask_route("") == "/"
    assert ui_tel.mask_route(None) == "/"


def test_mask_route_masks_numeric_id():
    assert ui_tel.mask_route("/directory/person/482/edit") == "/directory/person/{id}/edit"


def test_mask_route_masks_hex_token():
    assert ui_tel.mask_route("/r/9f2c1e4a1234") == "/r/{token}"


def test_mask_route_masks_date_segment():
    assert ui_tel.mask_route("/x/2025-01-31") == "/x/{date}"
    assert ui_tel.mask_route("/x/2025-01") == "/x/{date}"


def test_mask_route_drops_query_and_hash():
    assert ui_tel.mask_route("/dashboard?tab=ar#top") == "/dashboard"


def test_mask_route_strips_origin():
    assert ui_tel.mask_route("https://app.example.com/reports/activities/91") == \
        "/reports/activities/{id}"


def test_mask_route_static_path_untouched():
    assert ui_tel.mask_route("/reports/activities-export") == "/reports/activities-export"


def test_mask_route_is_idempotent():
    """Masking an already-masked route (what the client sends) must be a no-op —
    this is exactly what makes server-side re-masking safe defense-in-depth."""
    once = ui_tel.mask_route("/directory/person/482/edit")
    twice = ui_tel.mask_route(once)
    assert once == twice == "/directory/person/{id}/edit"
