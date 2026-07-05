"""Backups module — schedule arithmetic, snapshot file ops, and admin routes."""
import os
from datetime import datetime

import pytest
import backups as bk
import storage as st


def _cfg(**over):
    base = {"enabled": True, "freq": "daily", "time": "02:00", "weekday": 0,
            "keep": 14, "purge": True, "last_backup_at": "", "last_backup_status": ""}
    base.update(over)
    return base


# ---- persist-loop decision: ok / skip / realign (the 2026-06-25 self-heal) ----

def test_persist_action_ok_when_at_or_above_mark():
    hw = {"response": 100, "audit_log": 50}
    assert bk.persist_action({"response": 100, "audit_log": 50},
                             {"response": 100, "audit_log": 50}, hw) == "ok"
    assert bk.persist_action({"response": 120, "audit_log": 60}, {}, hw) == "ok"
    # no high-water recorded yet -> never stale -> ok
    assert bk.persist_action({"response": 1}, {"response": 50}, {}) == "ok"


def test_persist_action_skip_when_a_richer_snapshot_exists():
    # live below the mark AND a snapshot is strictly ahead of live -> protect it.
    hw = {"response": 100, "audit_log": 50}
    assert bk.persist_action({"response": 90, "audit_log": 50},
                             {"response": 100, "audit_log": 50}, hw) == "skip"


def test_persist_action_realign_when_mark_is_orphaned():
    # live below the mark but NO surviving snapshot beats live -> the mark is
    # orphaned; realign instead of skipping forever (the deadlock that lost June 24).
    hw = {"response": 100, "audit_log": 50}
    assert bk.persist_action({"response": 90, "audit_log": 50},
                             {"response": 90, "audit_log": 50}, hw) == "realign"
    assert bk.persist_action({"response": 90, "audit_log": 50},
                             {"response": 80, "audit_log": 40}, hw) == "realign"
    # no snapshot at all to protect -> realign
    assert bk.persist_action({"response": 90, "audit_log": 50}, {}, hw) == "realign"


# ---- stall detection: catch a wedged loop the ok/skip/fail state can't (2026-06-26) ----

def test_persist_is_stalled_not_before_first_tick():
    # never ticked yet (just booted) -> not stalled regardless of unsaved.
    assert bk.persist_is_stalled(last_tick=None, last_ok=None, unsaved=True,
                                 now=1000.0, tick=60, stall_ticks=5) is False


def test_persist_is_stalled_when_loop_stops_ticking():
    # last tick was 6 min ago, window = 5*60s = 300s -> stalled (wedged worker).
    assert bk.persist_is_stalled(last_tick=1000.0, last_ok=1000.0, unsaved=False,
                                 now=1000.0 + 360, tick=60, stall_ticks=5) is True
    # ticked recently -> alive, not stalled.
    assert bk.persist_is_stalled(last_tick=1000.0, last_ok=1000.0, unsaved=False,
                                 now=1000.0 + 120, tick=60, stall_ticks=5) is False


def test_persist_is_stalled_when_unsaved_data_goes_unwritten():
    # loop still ticking, but unsaved changes haven't been persisted for > window.
    assert bk.persist_is_stalled(last_tick=2000.0, last_ok=1000.0, unsaved=True,
                                 now=2000.0, tick=60, stall_ticks=5) is True
    # unsaved but last save was recent -> the saver is keeping up.
    assert bk.persist_is_stalled(last_tick=1200.0, last_ok=1100.0, unsaved=True,
                                 now=1200.0, tick=60, stall_ticks=5) is False
    # unsaved, never saved yet (last_ok None) but only just past one tick -> within
    # the window, so not yet stalled.
    assert bk.persist_is_stalled(last_tick=1000.0, last_ok=None, unsaved=True,
                                 now=1000.0 + 120, tick=60, stall_ticks=5) is False
    # unsaved, never saved, and well past the window -> stalled.
    assert bk.persist_is_stalled(last_tick=1000.0, last_ok=None, unsaved=True,
                                 now=1000.0 + 400, tick=60, stall_ticks=5) is True


# ---- pure schedule arithmetic -------------------------------------------

def test_next_due_interval():
    last = "2026-06-11T10:00:00"
    assert bk.next_due(_cfg(freq="h6"), last) == datetime(2026, 6, 11, 16, 0)
    assert bk.next_due(_cfg(freq="h12"), last) == datetime(2026, 6, 11, 22, 0)


def test_next_due_daily():
    # last backup after today's slot -> tomorrow's slot
    assert bk.next_due(_cfg(freq="daily", time="02:00"), "2026-06-11T03:00:00") \
        == datetime(2026, 6, 12, 2, 0)
    # last backup before today's slot -> today's slot
    assert bk.next_due(_cfg(freq="daily", time="02:00"), "2026-06-11T01:00:00") \
        == datetime(2026, 6, 11, 2, 0)


def test_next_due_weekly():
    # base Wed 2026-06-10; weekday=0 (Mon) -> next Mon 2026-06-15 02:00
    nd = bk.next_due(_cfg(freq="weekly", weekday=0, time="02:00"), "2026-06-10T12:00:00")
    assert nd == datetime(2026, 6, 15, 2, 0)


def test_is_due_respects_enabled_and_time():
    cfg = _cfg(freq="h6")
    last = "2026-06-11T10:00:00"
    assert bk.is_due(cfg, last, now=datetime(2026, 6, 11, 16, 0))
    assert not bk.is_due(cfg, last, now=datetime(2026, 6, 11, 15, 59))
    assert not bk.is_due(_cfg(freq="h6", enabled=False), last, now=datetime(2026, 6, 11, 18, 0))


def test_empty_anchor_is_never_due_without_seeding():
    """The deadlock this fix addresses: with no last_backup_at, a daily schedule
    is never 'due' at ANY hour, so it can never run the first backup that would
    set the anchor. (Documents why ensure_schedule_anchor exists.)"""
    cfg = _cfg(freq="daily", time="02:00", last_backup_at="")
    for h in (1, 2, 3, 9, 23):
        assert bk.is_due(cfg, "", now=datetime(2026, 7, 6, h, 0)) is False


def test_ensure_schedule_anchor_seeds_then_it_fires(db_path):
    conn = st.connect(db_path)
    try:
        bk.write_config(conn, enabled=True, freq="daily", time="02:00")
        assert bk.read_config(conn)["last_backup_at"] == ""      # stuck: no anchor
        # seeding gives it a starting point...
        assert bk.ensure_schedule_anchor(conn) is True
        anchored = bk.read_config(conn)
        assert anchored["last_backup_at"]                        # now set
        # ...and it's a no-op the second time (idempotent)
        assert bk.ensure_schedule_anchor(conn) is False
        # once anchored to a past slot, a later time reads as due (and stays due,
        # so a slot missed while the Space slept still runs on the next wake)
        assert bk.is_due(_cfg(last_backup_at="2026-07-05T02:00:00"), "2026-07-05T02:00:00",
                         now=datetime(2026, 7, 6, 9, 0)) is True
    finally:
        conn.close()


def test_ensure_schedule_anchor_noop_when_disabled(db_path):
    conn = st.connect(db_path)
    try:
        bk.write_config(conn, enabled=False, freq="daily", time="02:00")
        st.set_setting(conn, "last_backup_at", "")           # explicit precondition
        assert bk.ensure_schedule_anchor(conn) is False       # off -> never seeds
        assert bk.read_config(conn)["last_backup_at"] == ""
    finally:
        conn.close()


# ---- snapshot files ------------------------------------------------------

@pytest.fixture
def sched_dir(tmp_path, monkeypatch):
    d = tmp_path / "sched"
    monkeypatch.setattr(bk, "SCHED_DIR", str(d))
    return d


def _make_db(path):
    conn = st.connect(str(path)); st.init_db(conn)
    conn.execute("INSERT INTO app_setting(key,value) VALUES ('probe','1')"); conn.commit()
    conn.close()


def test_make_list_prune(sched_dir, tmp_path):
    db = tmp_path / "x.db"; _make_db(db)
    names = []
    for i in range(3):
        # vary the timestamp so names sort distinctly
        m = bk.make_backup(str(db), kind="auto")
        names.append(m["name"])
        # rename to deterministic increasing timestamps
        new = f"css_is_2026061{i}_0100{i}0_auto.db"
        os.rename(m["path"], os.path.join(str(sched_dir), new))
    # one protected pre_restore snapshot
    pr = bk.make_backup(str(db), kind="pre_restore")
    os.rename(pr["path"], os.path.join(str(sched_dir), "css_is_20260101_000000_pre_restore.db"))

    listed = bk.list_backups()
    assert len(listed) == 4
    deleted = bk.prune_backups(keep=1)
    # keeps newest 1 auto, deletes the other 2 autos, never the pre_restore
    assert len(deleted) == 2
    remaining = {m["name"] for m in bk.list_backups()}
    assert "css_is_20260101_000000_pre_restore.db" in remaining
    assert len(remaining) == 2


def test_prune_keeps_daily_anchors(sched_dir, tmp_path):
    db = tmp_path / "y.db"; _make_db(db)
    # 6 snapshots across 3 distinct days (2 per day), newest first when sorted
    stamps = ["20260620_010000", "20260620_120000",
              "20260621_010000", "20260621_120000",
              "20260622_010000", "20260622_120000"]
    for s in stamps:
        m = bk.make_backup(str(db), kind="auto")
        os.rename(m["path"], os.path.join(str(sched_dir), f"css_is_{s}_auto.db"))
    # keep=1 fine-grained but keep one anchor per day for the last 2 days
    bk.prune_backups(keep=1, keep_daily=2)
    remaining = {m["name"] for m in bk.list_backups()}
    # newest overall (kept by keep=1) + newest-of-day for the 2 most recent days.
    # 22 noon = newest (covered by both rules); 21 noon = 2nd day's anchor.
    assert "css_is_20260622_120000_auto.db" in remaining   # newest / day-22 anchor
    assert "css_is_20260621_120000_auto.db" in remaining   # day-21 anchor
    # day 20 is beyond keep_daily=2 and beyond keep=1 -> both pruned
    assert "css_is_20260620_120000_auto.db" not in remaining
    assert "css_is_20260620_010000_auto.db" not in remaining


def test_boot_decision_rules():
    # a valid snapshot always wins -> restore
    assert bk.boot_decision(valid_snapshot="x", mount_ready=False,
                            snapshots_present=True, initialized=True,
                            allow_seed=False) == "restore"
    # genuine first boot: mount ready, truly empty, never initialized -> seed
    assert bk.boot_decision(valid_snapshot=None, mount_ready=True,
                            snapshots_present=False, initialized=False,
                            allow_seed=False) == "seed"
    # mount not ready -> never overwrite live with the seed
    assert bk.boot_decision(valid_snapshot=None, mount_ready=False,
                            snapshots_present=False, initialized=False,
                            allow_seed=False) == "abort"
    # snapshots exist but none valid -> corruption, abort (not first boot)
    assert bk.boot_decision(valid_snapshot=None, mount_ready=True,
                            snapshots_present=True, initialized=False,
                            allow_seed=False) == "abort"
    # initialized before but bucket now empty -> data vanished, abort
    assert bk.boot_decision(valid_snapshot=None, mount_ready=True,
                            snapshots_present=False, initialized=True,
                            allow_seed=False) == "abort"
    # explicit operator override forces a seed past the abort guards
    assert bk.boot_decision(valid_snapshot=None, mount_ready=True,
                            snapshots_present=True, initialized=True,
                            allow_seed=True) == "seed"


# ---- high-water mark: the stale-snapshot revert guard --------------------

def test_marker_is_stale_pure():
    # no recorded high-water yet -> nothing to compare against, never stale
    assert bk.marker_is_stale({"response": 5}, None) is False
    assert bk.marker_is_stale({"response": 5}, {}) is False
    # candidate equal to / ahead of the mark -> fresh
    assert bk.marker_is_stale({"response": 5, "audit_log": 9},
                              {"response": 5, "audit_log": 9}) is False
    assert bk.marker_is_stale({"response": 6, "audit_log": 9},
                              {"response": 5, "audit_log": 9}) is False
    # behind on ANY tracked counter -> stale (data would be lost)
    assert bk.marker_is_stale({"response": 4, "audit_log": 9},
                              {"response": 5, "audit_log": 9}) is True
    # a counter missing from the candidate scores 0 < mark -> stale
    assert bk.marker_is_stale({"audit_log": 9}, {"response": 5}) is True
    # an unreadable candidate (empty marker) vs a known mark -> treat as stale
    assert bk.marker_is_stale({}, {"response": 1}) is True


def test_highwater_advances_and_detects_stale(sched_dir, tmp_path, monkeypatch):
    # track a table we can grow trivially, decoupled from the real schema
    monkeypatch.setattr(bk, "_HIGHWATER_TABLES", ("app_setting",))
    db = tmp_path / "hw.db"; _make_db(db)
    # a snapshot records / advances the high-water to the live DB's marker
    bk.make_backup(str(db), kind="auto")
    hw1 = bk.read_highwater()
    assert hw1 and hw1.get("app_setting", 0) >= 1
    assert bk.live_db_is_stale(str(db)) is False        # live == high-water

    # grow the live DB and snapshot again -> mark advances
    conn = st.connect(str(db))
    conn.execute("INSERT INTO app_setting(key,value) VALUES ('probe2','1')")
    conn.commit(); conn.close()
    bk.make_backup(str(db), kind="auto")
    hw2 = bk.read_highwater()
    assert hw2["app_setting"] > hw1["app_setting"]

    # a DB that sits BELOW the mark (a reverted lineage) is flagged stale
    old = tmp_path / "old.db"; _make_db(old)            # only the single probe row
    assert bk.marker_is_stale(bk.db_marker(str(old)), bk.read_highwater()) is True
    assert bk.live_db_is_stale(str(old)) is True


def test_highwater_protects_accounts(sched_dir, tmp_path):
    """An account-only change (no new response/audit row) must advance the
    high-water mark, so a stale FUSE view that would restore a snapshot
    predating the account is caught as stale — the 'accounts reset on update'
    guard. Uses the REAL _HIGHWATER_TABLES (no monkeypatch) on purpose.
    """
    assert "admin_user" in bk._HIGHWATER_TABLES
    db = tmp_path / "acct.db"; _make_db(db)
    bk.make_backup(str(db), kind="auto")           # baseline mark, 0 accounts
    base = bk.read_highwater().get("admin_user", 0)

    # Snapshot the pre-account state, THEN add an account (nothing else).
    pre_account = bk.make_backup(str(db), kind="manual")
    conn = st.connect(str(db))
    st.create_admin_user(conn, "new@doh.gov.ph", "h", "s", "admin",
                         created_by="test")
    conn.commit(); conn.close()
    bk.make_backup(str(db), kind="auto")           # advances the mark for the account

    assert bk.read_highwater()["admin_user"] > base
    # the snapshot taken BEFORE the account now reads as stale (restoring it
    # would silently drop the account) — exactly what the boot guard rejects.
    pre_path = os.path.join(str(sched_dir), pre_account["name"])
    assert bk.marker_is_stale(bk.db_marker(pre_path), bk.read_highwater()) is True


def test_highwater_is_monotonic(sched_dir, tmp_path, monkeypatch):
    monkeypatch.setattr(bk, "_HIGHWATER_TABLES", ("app_setting",))
    big = tmp_path / "big.db"; _make_db(big)
    conn = st.connect(str(big))
    for i in range(5):
        conn.execute("INSERT INTO app_setting(key,value) VALUES (?, '1')", (f"k{i}",))
    conn.commit(); conn.close()
    bk.make_backup(str(big), kind="auto")
    hi = bk.read_highwater()["app_setting"]
    # a stale writer (fewer rows) must NOT be able to lower the mark
    small = tmp_path / "small.db"; _make_db(small)
    bk.write_highwater(str(small))
    assert bk.read_highwater()["app_setting"] == hi


def test_reset_highwater_allows_deliberate_restore(sched_dir, tmp_path, monkeypatch):
    monkeypatch.setattr(bk, "_HIGHWATER_TABLES", ("app_setting",))
    big = tmp_path / "b.db"; _make_db(big)
    conn = st.connect(str(big))
    for i in range(4):
        conn.execute("INSERT INTO app_setting(key,value) VALUES (?, '1')", (f"k{i}",))
    conn.commit(); conn.close()
    bk.make_backup(str(big), kind="auto")
    assert bk.read_highwater()["app_setting"] >= 5
    # restoring an older/smaller DB on purpose realigns the mark DOWN to it, so
    # the admin's chosen snapshot isn't then rejected as stale
    small = tmp_path / "s.db"; _make_db(small)
    bk.reset_highwater(str(small))
    assert bk.live_db_is_stale(str(small)) is False


def test_restore_backup_resets_highwater(sched_dir, tmp_path, monkeypatch):
    monkeypatch.setattr(bk, "_HIGHWATER_TABLES", ("app_setting",))
    live = tmp_path / "live.db"; _make_db(live)
    # take an OLD snapshot (few rows), then grow the live DB a lot
    old_snap = bk.make_backup(str(live), kind="manual")
    conn = st.connect(str(live))
    for i in range(6):
        conn.execute("INSERT INTO app_setting(key,value) VALUES (?, '1')", (f"g{i}",))
    conn.commit(); conn.close()
    bk.make_backup(str(live), kind="auto")              # mark now high
    assert bk.live_db_is_stale(str(live)) is False
    # deliberately restore the old snapshot -> mark realigns down, not "stale"
    bk.restore_backup(old_snap["name"], db_path=str(live))
    assert bk.live_db_is_stale(str(live)) is False


def test_bucket_writable_and_wait(tmp_path):
    good = tmp_path / "bucket"
    assert bk.bucket_writable(str(good)) is True          # creatable + writable
    assert bk.wait_for_bucket(str(good), timeout=0) is True
    # a path under a file (can't be a dir) is never writable; wait times out fast
    blocker = tmp_path / "afile"; blocker.write_text("x")
    bad = str(blocker / "sub")
    assert bk.bucket_writable(bad) is False
    assert bk.wait_for_bucket(bad, timeout=1, interval=1) is False


def test_snapshots_present(sched_dir, tmp_path):
    assert bk.snapshots_present() is False                 # empty bucket
    db = tmp_path / "z.db"; _make_db(db)
    bk.make_backup(str(db), kind="auto")
    assert bk.snapshots_present() is True


def test_safe_name_blocks_traversal(sched_dir):
    assert bk.safe_name("../../etc/passwd") is None
    assert bk.safe_name("css_is_20260611_010000_auto.db") == "css_is_20260611_010000_auto.db"
    assert bk.safe_name("random.db") is None


def test_restore_round_trips(sched_dir, tmp_path):
    db = tmp_path / "live.db"; _make_db(db)
    snap = bk.make_backup(str(db), kind="manual")
    # mutate the live DB after the snapshot
    conn = st.connect(str(db))
    conn.execute("UPDATE app_setting SET value='2' WHERE key='probe'"); conn.commit(); conn.close()
    # restore -> value reverts, and a pre_restore safety snapshot is created
    safety = bk.restore_backup(snap["name"], str(db))
    assert safety["kind"] == "pre_restore"
    conn = st.connect(str(db))
    v = conn.execute("SELECT value FROM app_setting WHERE key='probe'").fetchone()[0]
    conn.close()
    assert v == "1"


def test_run_scheduled_job_purges(sched_dir, tmp_path):
    db = tmp_path / "job.db"; _make_db(db)
    conn = st.connect(str(db))
    bk.write_config(conn, purge=True, keep=14)
    ev = st.create_event(conn, "T", "2026-01-01")
    aid = st.add_attendee(conn, ev["id"], name="Old", email="o@e.com", consent_text="x")
    conn.execute("UPDATE attendee SET consent_at='2020-01-01T00:00:00' WHERE id=?", (aid,))
    conn.commit(); conn.close()

    res = bk.run_scheduled_job(str(db))
    assert res["ok"] and res["backup"] and res["purged"] == 1
    conn = st.connect(str(db))
    name = conn.execute("SELECT name FROM attendee WHERE id=?", (aid,)).fetchone()[0]
    last = st.get_setting(conn, "last_backup_at")
    conn.close()
    assert name is None and last        # PII purged, last_backup_at stamped


# ---- admin routes (RBAC + behaviour) -------------------------------------

def test_backups_page_admin_only(app_mod, viewer, admin):
    from starlette.testclient import TestClient
    anon = TestClient(app_mod.app, raise_server_exceptions=True)   # guaranteed no cookie
    # unauthenticated -> redirect to login
    r = anon.get("/admin/backups", follow_redirects=False)
    assert r.status_code in (303, 307)
    # viewer lacks manage_users -> forbidden
    assert viewer.get("/admin/backups").status_code == 403
    # admin sees it
    assert admin.get("/admin/backups").status_code == 200


def test_backups_settings_and_now(admin, db_path, tmp_path, monkeypatch):
    monkeypatch.setattr(bk, "SCHED_DIR", str(tmp_path / "s"))
    r = admin.post("/admin/backups/settings", data={
        "enabled": "on", "freq": "weekly", "time": "23:30", "weekday": "2",
        "keep": "5", "purge": "on"}, follow_redirects=False)
    assert r.status_code == 303
    conn = st.connect(db_path)
    cfg = bk.read_config(conn); conn.close()
    assert cfg["enabled"] and cfg["freq"] == "weekly" and cfg["time"] == "23:30" \
        and cfg["weekday"] == 2 and cfg["keep"] == 5 and cfg["purge"]
    # back up now -> a snapshot file appears
    admin.post("/admin/backups/now", follow_redirects=False)
    assert any(m["kind"] == "manual" for m in bk.list_backups())


def test_restore_requires_confirmation(admin, db_path, tmp_path, monkeypatch):
    monkeypatch.setattr(bk, "SCHED_DIR", str(tmp_path / "s2"))
    meta = bk.make_backup(db_path, kind="manual")
    r = admin.post("/admin/backups/restore",
                   data={"name": meta["name"], "confirm": "nope"}, follow_redirects=False)
    assert r.status_code == 303 and "err=" in r.headers["location"]
    # no pre_restore snapshot should have been created
    assert not any(m["kind"] == "pre_restore" for m in bk.list_backups())


# ---- off-site (GitHub) backup ping + history -----------------------------

def test_offsite_ping_not_configured(app_mod, monkeypatch):
    """No CSS_OFFSITE_PING_TOKEN on the server -> 503 (misconfig is visible)."""
    from starlette.testclient import TestClient
    monkeypatch.delenv("CSS_OFFSITE_PING_TOKEN", raising=False)
    c = TestClient(app_mod.app)
    r = c.post("/offsite-backup/ping", headers={"X-Backup-Token": "x"}, json={"file": "f"})
    assert r.status_code == 503


def test_offsite_ping_bad_token(app_mod, monkeypatch):
    from starlette.testclient import TestClient
    monkeypatch.setenv("CSS_OFFSITE_PING_TOKEN", "s3cret")
    c = TestClient(app_mod.app)
    r = c.post("/offsite-backup/ping", headers={"X-Backup-Token": "wrong"}, json={"file": "f"})
    assert r.status_code == 401


def test_offsite_ping_records_and_surfaces(app_mod, admin, db_path, monkeypatch):
    """A valid ping writes one audit row and the Backups page then shows it."""
    from starlette.testclient import TestClient
    monkeypatch.setenv("CSS_OFFSITE_PING_TOKEN", "s3cret")
    fname = "prod_20260705_162945_manual.db.gpg"
    c = TestClient(app_mod.app)
    r = c.post("/offsite-backup/ping", headers={"X-Backup-Token": "s3cret"},
               json={"file": fname, "size": 6_100_000, "sha": "abcdef1234567890"})
    assert r.status_code == 204
    conn = st.connect(db_path)
    rows = st.list_audit(conn, action="offsite_backup")
    conn.close()
    assert rows and rows[0]["target_id"] == fname and rows[0]["actor"] == "(github-actions)"
    body = admin.get("/admin/backups").text
    assert "Off-site backups (GitHub)" in body and fname in body
