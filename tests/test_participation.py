"""Participation v2 (volume redesign): count-scale geometry, the volume SPC read,
the consolidated participation read, and the normalized by-unit movers. Pure
functions + small synthetic atoms frames — no DB."""
import pandas as pd
import dashboard_insights as di


# ---- count-scale auto-zoom + gridlines --------------------------------------

def test_count_gridvals_nice_integer_steps():
    grid = di._count_gridvals(0, 100)
    assert grid and all(g == int(g) for g in grid)
    assert max(grid) <= 100 and min(grid) >= 0
    # step is a 'nice' value from the ladder (here ~50 for a span of 100)
    assert grid[1] - grid[0] in di._COUNT_STEPS


def test_count_bounds_zooms_to_data_not_zero():
    lo, hi, grid, flat = di._count_bounds(120, 180)
    assert not flat
    assert lo <= 120 and hi >= 180
    assert lo > 0                                  # honest auto-zoom, not anchored at 0
    assert grid and min(grid) >= lo and max(grid) <= hi + 1e-9


def test_count_bounds_flat_series_shows_band():
    lo, hi, grid, flat = di._count_bounds(50, 50)
    assert flat and lo < 50 < hi


# ---- _count_geom: recent window + control band ------------------------------

def _cseries(vals):
    return [{"key": i, "label": f"P{i}", "value": v, "n": v} for i, v in enumerate(vals)]


def test_count_geom_windows_and_flags_signal():
    vals = [100, 102, 98, 101, 99, 100, 103, 97, 101, 40]   # last one crashes
    series = _cseries(vals)
    control = di._control_stats(series, False)
    g = di._count_geom(series, control=control, window=8, show_full=False)
    assert g["full_n"] == 10 and g["shown_n"] == 8 and g["windowed"] is True
    assert g["control"] is not None and g["control"]["has_signal"]
    assert any(d["signal"] for d in g["main_dots"])         # the crash dot is flagged
    assert g["grid"] and g["ylo"] < g["yhi"]


# ---- _volume_read: plain-language SPC read for counts -----------------------

def test_volume_read_signal_drop_is_bad():
    series = _cseries([100, 102, 98, 101, 99, 100, 103, 97, 101, 40])
    stats = di._control_stats(series, False)
    cr = di._volume_read(stats, series, view_from=0)
    assert cr["label"] == "Signal" and cr["tone"] == "bad"
    assert "drop" in cr["headline"]


def test_volume_read_steady_when_in_control():
    series = _cseries([100, 101, 99, 100, 102, 98, 101, 100])
    stats = di._control_stats(series, False)
    cr = di._volume_read(stats, series, view_from=0)
    assert cr["label"] == "In control" and cr["tone"] == "neutral"


def test_volume_read_handles_too_few_periods():
    cr = di._volume_read(None, _cseries([10, 12]))
    assert cr["label"] == "Early days"


# ---- participation_read: consolidated headline ------------------------------

def _vol(total, latest, prev, dir):
    return {"has_data": True, "total": total,
            "headline": {"latest": latest, "prev": prev, "dir": dir,
                         "latest_label": "May 2026", "delta": (latest - prev)}}


def test_participation_read_rising_and_driver():
    volumes = [_vol(500, 120, 100, "up"), _vol(300, 40, 38, "up")]
    by_unit = [{"label": "Div A", "role": "up", "delta": 15},
               {"label": "Div B", "role": "down", "delta": -8}]
    cover = {"events_pct": 82.0, "staff_pct": 60.0}
    r = di.participation_read(volumes, by_unit, cover, "monthly")
    assert r["tone"] == "good" and "rising" in r["lead"]
    assert "82%" in r["coverage"]
    assert "Div A grew most" in r["driver"] and "Div B fell most" in r["driver"]


def test_participation_read_easing_when_down():
    volumes = [_vol(500, 80, 120, "down")]
    r = di.participation_read(volumes, [], {"events_pct": 50.0, "staff_pct": 40.0}, "quarterly")
    assert r["tone"] == "watch" and "eased off" in r["lead"]
    assert r["driver"] is None


# ---- volume_view + volume_by_unit2 on synthetic atoms -----------------------

def _atoms(rows):
    return pd.DataFrame(rows)


def test_volume_view_builds_series_and_read():
    rows = []
    counts = {"2026-01": 100, "2026-02": 102, "2026-03": 98, "2026-04": 101,
              "2026-05": 40}
    rid = 0
    for month, n in counts.items():
        for _ in range(n):
            rid += 1
            rows.append({"survey_type": 1, "response_id": rid, "month": month,
                         "event_date": month + "-15"})
    v = di.volume_view(_atoms(rows), 1, "monthly", show_full=True)
    assert v["has_data"] and v["total"] == sum(counts.values())
    assert v["geom"]["control"] is not None
    assert v["control_read"]["label"] in ("Signal", "In control", "Trend")


def test_volume_by_unit2_normalizes_and_marks_movers():
    org_struct = {"divisions": [{"name": "D1", "path": "BLHSD/D1",
                                 "sections": [{"path": "BLHSD/D1/S1"}]}],
                  "admin_sections": []}
    rows = []
    rid = 0
    # S1: 3 responses in the prior month, 9 in the latest -> +6 -> a riser. 4 events.
    plan = [("2026-01", 3), ("2026-02", 9)]
    inst = 0
    for month, n in plan:
        for _ in range(n):
            rid += 1
            inst = inst + 1 if rid % 3 == 1 else inst
            rows.append({"survey_type": 1, "response_id": rid, "month": month,
                         "org_path": "BLHSD/D1/S1", "form_instance_id": inst,
                         "event_date": month + "-15"})
    out = di.volume_by_unit2(_atoms(rows), org_struct, "monthly")
    s1 = next(r for r in out if r["label"] == "D1/S1")
    assert s1["count"] == 12 and s1["events"] > 0
    assert s1["per_event"] is not None and s1["delta"] == 6   # normalized + movement read
    # the single biggest riser (here the division/section tie at +6) is highlighted
    risers = [r for r in out if r.get("role") == "up"]
    assert risers and risers[0]["delta"] == 6
