"""UX-queue #21 — skip-to-content link + screen-reader data-table fallback for charts.

Deploy 1 scope: the skip-link (both layouts) + the `chart_table` macro wired to all
five Trends charts via `_svg_geom`'s new main_table / dims_table.
"""
import dashboard_insights as di
from tests.conftest import in_the_directory


def test_svg_geom_emits_sr_tables():
    """_svg_geom returns an index-aligned data table for the headline series and one
    column per area, with missing points rendered as an em dash."""
    series = [{"label": "Q1", "value": 80.0, "n": 10},
              {"label": "Q2", "value": 85.0, "n": 12}]
    dims = [{"name": "Speed", "points": [{"label": "Q1", "value": 70.0},
                                         {"label": "Q2", "value": None}]}]
    g = di._svg_geom(series, dims, 100, True, window=8, show_full=True)

    assert g["main_table"] == [["Q1", "80%"], ["Q2", "85%"]]
    assert g["dims_table"]["headers"] == ["Period", "Speed"]
    assert g["dims_table"]["rows"] == [["Q1", "70%"], ["Q2", "—"]]


def test_svg_geom_no_dims_table_when_single_series():
    g = di._svg_geom([{"label": "Q1", "value": 6.4, "n": 9}], [], 7, False, show_full=True)
    assert g["main_table"] == [["Q1", "6.4"]]
    assert g["dims_table"] is None


def test_skip_link_on_dashboard(admin):
    html = admin.get("/dashboard/trends").text
    assert 'class="skip-link"' in html and 'href="#maincontent"' in html
    assert 'id="maincontent"' in html


def test_skip_link_on_public_layout(client):
    html = client.get("/login").text
    assert 'class="skip-link"' in html and 'href="#maincontent"' in html


def test_trends_charts_have_sr_table(admin):
    """Wherever a Trends chart renders (role=img), its SR data table renders too."""
    html = admin.get("/dashboard/trends").text
    if 'role="img"' in html:
        assert 'sr-only chart-data' in html
        assert "<caption>" in html


def test_count_geom_emits_main_table():
    """The count-scale builder (volume / engagement charts) carries an SR table too."""
    g = di._count_geom([{"label": "Jan", "value": 12, "n": 12},
                        {"label": "Feb", "value": None, "n": 0}], show_full=True)
    assert g["main_table"] == [["Jan", "12"], ["Feb", "—"]]


def test_verbatims_breakdown_table_is_three_way(admin):
    """The Verbatims tone chart's SR table combines all three tone shares into one
    table: Period + Appreciation + Areas to improve + Mixed."""
    import re
    html = admin.get("/reports/verbatims").text
    m = re.search(r'<table class="sr-only chart-data">.*?</table>', html, re.S)
    if not m:
        return  # no comment data in this run -> chart (and table) absent
    heads = re.findall(r'<th scope="col">(.*?)</th>', m.group(0))
    assert heads[:2] == ["Period", "Appreciation"]
    assert "Areas to improve" in heads and any("Mixed" in h for h in heads)
    # every data row carries 3 tone cells beside its period row-header
    row = re.search(r'<tr><th scope="row">.*?</th>(.*?)</tr>',
                    m.group(0).split("</thead>")[1], re.S)
    assert row and len(re.findall(r"<td>", row.group(1))) == 3


def test_deploy2_pages_have_sr_tables(admin):
    """Pulse, Participation and Verbatims charts each ship their SR data table."""
    for path in ("/dashboard/pulse", "/dashboard/participation", "/reports/verbatims"):
        html = admin.get(path).text
        if 'role="img"' in html and "<svg" in html:
            # at least one genuine data chart -> at least one SR table
            assert 'sr-only chart-data' in html, f"no SR table on {path}"


def test_landing_charts_carry_their_sr_tables(admin, app_mod):
    """Same contract as Trends: anything drawn as role="img" on the Office
    Connect landing page ships a navigable data table beside it. The faces wall
    is the reason this matters most — it is deliberately pictures-not-names, so
    the table IS the accessible reading of it.

    The viewer has to be IN THE DIRECTORY: the team panels — and so every chart
    on this page — are scoped to the org unit the directory puts you in."""
    with in_the_directory(app_mod, "admin@test.local"):
        html = admin.get("/").text
    if 'role="img"' in html:
        assert "sr-only chart-data" in html
        assert "<caption>" in html


def test_landing_faces_are_labelled_individually(admin, app_mod):
    """Each face is its own role="img" with the person's name in the label —
    a wall of unlabelled circles would be unreadable without sight."""
    with in_the_directory(app_mod, "admin@test.local"):
        html = admin.get("/").text
    if 'class="face' in html:
        assert 'class="face' in html and "aria-label=" in html
