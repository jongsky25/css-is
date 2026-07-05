"""Trends page logic: top-box reframe, auto-zoom y-bounds, recent-window geom.
Pure functions — no DB, no period assignment needed."""
import pandas as pd
import dashboard_insights as di


# ---- servqual_topbox: % of perception item-answers rated 6-7 -----------------

def _sq_rows(rid, b1, b2):
    return [
        {"response_id": rid, "item_id": "B1", "value": float(b1), "is_na": False},
        {"response_id": rid, "item_id": "B2", "value": float(b2), "is_na": False},
    ]


def test_servqual_topbox_share_rated_top():
    df = pd.DataFrame(
        _sq_rows(1, 7, 6) + _sq_rows(2, 5, 6) + _sq_rows(3, 7, 7) + _sq_rows(4, 4, 5)
    )
    m = di.servqual_topbox(df, {"d": ["B1", "B2"]})
    # 8 valid item-answers, 5 of them >= 6  ->  62.5%
    assert abs(m.value - 62.5) < 1e-9
    assert m.n == 4                       # respondents, not item-answers


def test_servqual_topbox_empty():
    df = pd.DataFrame([{"response_id": 1, "item_id": "B1", "value": 6.0, "is_na": True}])
    m = di.servqual_topbox(df, {"d": ["B1"]})
    assert m.value is None and m.n == 0


# ---- _nice_bounds: tight, honest zoom + flat-ceiling guard -------------------

def test_nice_bounds_zooms_to_data():
    lo, hi, grid, flat = di._nice_bounds(6.4, 6.7, 7.0, pct=False)
    assert not flat
    assert lo <= 6.4 and hi >= 6.7 and hi <= 7.0
    assert lo > 0                          # not anchored at zero — that's the whole point
    assert grid and min(grid) >= lo and max(grid) <= hi + 1e-9


def test_nice_bounds_flat_ceiling_guard():
    # All values pinned at 100% (walk-in): no divide-by-zero, show an honest band.
    lo, hi, grid, flat = di._nice_bounds(100.0, 100.0, 100.0, pct=True)
    assert flat
    assert hi == 100.0 and lo < 100.0
    assert 100.0 in grid


# ---- _svg_geom: recent-window default + gridlines ---------------------------

def _series(vals):
    return [{"key": i, "label": f"P{i}", "value": v, "n": 10} for i, v in enumerate(vals)]


def test_svg_geom_windows_to_recent():
    vals = [90 + (i % 5) for i in range(12)]            # 12 periods
    series = _series(vals)
    dims = [{"name": "Area", "points": _series(vals)}]
    g = di._svg_geom(series, dims, 100, pct=True, window=8, show_full=False)
    assert g["full_n"] == 12 and g["shown_n"] == 8 and g["windowed"] is True
    assert len(g["main_dots"]) == 8                     # only the recent window is plotted
    assert g["grid"]                                    # gridlines computed
    assert g["ylo"] < g["yhi"] <= 100


def test_svg_geom_full_history_toggle():
    vals = [90 + (i % 5) for i in range(12)]
    series = _series(vals)
    dims = [{"name": "Area", "points": _series(vals)}]
    g = di._svg_geom(series, dims, 100, pct=True, window=8, show_full=True)
    assert g["shown_n"] == 12 and g["windowed"] is False
    assert len(g["main_dots"]) == 12
    # long history thins x-labels so they don't crowd
    assert sum(1 for x in g["xlabels"] if x["show"]) < 12


# ---- SPC control band: signal vs noise --------------------------------------

def test_control_stats_flags_real_outlier():
    # Eleven steady ~95% periods + one genuine crash to 40% -> a special-cause signal.
    vals = [95, 96, 94, 95, 96, 95, 94, 96, 95, 95, 40]
    stats = di._control_stats(_series(vals), pct=True)
    assert stats is not None
    assert (len(vals) - 1) in stats["signals"]          # the 40% period is flagged
    assert stats["lcl"] < 95 < stats["ucl"]


def test_control_stats_practical_floor_ignores_ceiling_blip():
    # Near-ceiling: a 2pp dip must NOT be a 'signal' just because limits are razor-thin.
    vals = [100, 100, 99, 100, 100, 98, 100, 100, 100, 100]
    stats = di._control_stats(_series(vals), pct=True)
    assert stats["signals"] == []
    assert stats["drift"] is None                       # spread < floor -> no false trend


def test_control_read_window_consistency():
    # A signal only in OLD history (index 0) must not be narrated as if its dot were
    # on the chart; with the recent window starting later it's deferred to 'Full
    # history'. Craft the stats directly so the read logic is tested in isolation.
    series = _series([40, 95, 96, 94, 95, 96, 94, 95])
    stats = {"cl": 93.0, "ucl": 99.0, "lcl": 88.0, "sigma": 2.0,
             "signals": [0], "drift": None}
    cr_recent = di._control_read(stats, series, pct=True, view_from=3)
    assert cr_recent["label"] == "In control" and "Full history" in cr_recent["detail"]
    cr_full = di._control_read(stats, series, pct=True, view_from=0)
    assert cr_full["label"] == "Signal"


def test_conf_halfwidth_wider_for_small_sample():
    big = [{"value": 90.0, "n": 1000}]
    small = [{"value": 90.0, "n": 10}]
    hw_big = di._conf_halfwidths(big, pct=True)[0]
    hw_small = di._conf_halfwidths(small, pct=True)[0]
    assert hw_small > hw_big > 0
    assert di._conf_halfwidths([{"value": 6.5, "n": 10}], pct=False) is None


# ---- Phase C: distribution (unhappy share) + driver --------------------------

def test_bottombox_share_rated_low():
    df = pd.DataFrame(
        _sq_rows(1, 2, 3) + _sq_rows(2, 7, 6) + _sq_rows(3, 1, 7) + _sq_rows(4, 6, 6)
    )
    # rated <=3 of 8 valid item-answers: r1 both(2), r3 the '1' -> 3 of 8 = 37.5%
    m = di._bottombox_metric(df, ["B1", "B2"], 3)
    assert abs(m.value - 37.5) < 1e-9 and m.n == 4


def test_unhappy_phrase_bands():
    assert di._unhappy_phrase(_series([1, 0, 1, 0]))["tone"] == "good"
    assert "Worth watching" in di._unhappy_phrase(_series([1, 12, 3]))["text"]
    assert di._unhappy_phrase([{"value": None, "n": 0}]) is None


def test_latest_driver_picks_largest_same_direction_mover():
    # Headline dips in the last period; the area that moved most the SAME way wins.
    series = _series([90, 80])                       # headline -10
    dims = [
        {"name": "Steady", "points": _series([85, 84])},      # -1, small
        {"name": "Culprit", "points": _series([88, 70])},     # -18, largest down
        {"name": "Rose", "points": _series([70, 82])},        # +12, wrong direction
    ]
    drv = di._latest_driver(series, dims, pct=True)
    assert drv["name"] == "Culprit" and drv["dir"] == "down"


def test_latest_driver_none_when_flat():
    series = _series([90, 90])
    dims = [{"name": "X", "points": _series([85, 86])}]
    assert di._latest_driver(series, dims, pct=True) is None


def test_svg_geom_mover_roles_and_endlabels():
    series = _series([90, 91, 92, 95])
    dims = [
        {"name": "Climber", "points": _series([80, 84, 88, 95])},
        {"name": "Flatline", "points": _series([90, 90, 91, 90])},
    ]
    g = di._svg_geom(series, dims, 100, pct=True, window=8, show_full=True,
                     mover_roles={"Climber": "up"})
    by_name = {d["name"]: d for d in g["dims"]}
    assert by_name["Climber"]["role"] == "up" and by_name["Flatline"]["role"] is None
    assert by_name["Climber"]["endx"] is not None and by_name["Climber"]["endy"] is not None
