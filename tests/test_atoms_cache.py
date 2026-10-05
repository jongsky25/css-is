"""
Tests for the atoms cache (F1 incremental + F2 background refresh).

Strategy: a tiny synthetic DB (a handful of org units / forms / responses /
answers) so full loads are instant and incremental-vs-full comparisons are exact.
We repoint app.DB at it for the module and drive get_atoms() directly. The
background worker connects to app.DB itself, so it must point at this DB — the
module fixture guarantees that and restores the original on teardown.
"""
from __future__ import annotations
import os, time, threading, tempfile
import pytest
import pandas as pd

import app as A
import storage as st


# --------------------------------------------------------------------------- #
# Synthetic DB + helpers
# --------------------------------------------------------------------------- #

def _seed(db_path):
    conn = st.connect(db_path)
    st.init_db(conn)
    conn.execute("INSERT INTO org_unit (id, name, short_name, level, path) "
                 "VALUES (1, 'Section A', 'SA', 'section', 'Bureau/Section A')")
    # one Type-2 (activity) form; org_path rolls up via lead_org_id
    conn.execute("INSERT INTO form_instance (id, survey_type, form, qr_token, event_date, "
                 "lead_org_id, archived, pooled) "
                 "VALUES (1, 2, 'F2-ACT', 'tok-act-1', '2025-01-15', 1, 0, 0)")
    conn.commit()
    conn.close()


def _append_submission(db_path, n_answers=5, value=5):
    """Mimic one survey submission: a new response + n answers (a PURE append)."""
    conn = st.connect(db_path)
    cur = conn.execute("INSERT INTO response (form_instance_id, submitted_at) "
                       "VALUES (1, '2025-01-16T09:00:00')")
    rid = cur.lastrowid
    for item in range(1, n_answers + 1):
        conn.execute("INSERT INTO answer (response_id, item_id, value, is_na) "
                     "VALUES (?, ?, ?, 0)", (rid, item, value))
    conn.commit()
    conn.close()
    return rid


def _delete_last_answer(db_path):
    conn = st.connect(db_path)
    conn.execute("DELETE FROM answer WHERE id = (SELECT MAX(id) FROM answer)")
    conn.commit()
    conn.close()


def _wait_rebuild(timeout=15.0):
    """Block until any background atoms rebuild has finished."""
    deadline = time.time() + timeout
    while time.time() < deadline:
        if not A._atoms_state["rebuilding"]:
            return
        time.sleep(0.01)
    raise AssertionError("background rebuild did not finish within timeout")


@pytest.fixture
def atoms_db(tmp_path):
    """Fresh seeded DB per test (tiny → cheap), with app.DB repointed at it."""
    db = str(tmp_path / "atoms.db")
    _seed(db)
    saved = A.DB
    A.DB = db
    yield db
    # Wait out any in-flight background worker, then clear the cache so this
    # module's synthetic frame can't leak into another module's tests (the
    # cache is process-global and stale-while-revalidate would otherwise serve
    # it once against the wrong DB).
    _wait_rebuild()
    A.DB = saved
    with A._atoms_lock:
        A._atoms_state.update({"key": None, "df": None, "built": 0.0,
                               "answer_maxid": 0, "force_full": False,
                               "rebuilding": False, "bg_full": False, "epoch": 0})
    A._view_memo.clear()


@pytest.fixture(autouse=True)
def _reset_cache():
    """Each test starts from a cold cache."""
    with A._atoms_lock:
        A._atoms_state.update({"key": None, "df": None, "built": 0.0,
                               "answer_maxid": 0, "force_full": False,
                               "rebuilding": False, "bg_full": False, "epoch": 0})
    A._view_memo.clear()
    yield


# --------------------------------------------------------------------------- #
# _is_pure_append unit tests
# --------------------------------------------------------------------------- #

def test_pure_append_detects_new_rows():
    old = (100, 100, 5, 5, 20, 20, 3, 3, 2)
    new = (150, 150, 5, 5, 21, 21, 3, 3, 2)      # +answers, +1 response
    assert A._is_pure_append(old, new) is True


def test_pure_append_false_on_deletion():
    old = (100, 100, 5, 5, 20, 20, 3, 3, 2)
    new = (90, 100, 5, 5, 20, 20, 3, 3, 2)       # answer COUNT dropped → deletion
    assert A._is_pure_append(old, new) is False


def test_pure_append_false_on_person_change():
    old = (100, 100, 5, 5, 20, 20, 3, 3, 2)
    new = (150, 150, 5, 5, 21, 21, 4, 4, 2)      # resource_person changed → structural
    assert A._is_pure_append(old, new) is False


def test_pure_append_false_on_org_change():
    old = (100, 100, 5, 5, 20, 20, 3, 3, 2)
    new = (150, 150, 5, 5, 21, 21, 3, 3, 3)      # org_unit count changed → structural
    assert A._is_pure_append(old, new) is False


def test_pure_append_none_key():
    assert A._is_pure_append(None, (1, 1, 1, 1, 1, 1, 1, 1, 1)) is False


# --------------------------------------------------------------------------- #
# get_atoms behaviour
# --------------------------------------------------------------------------- #

def test_cold_build_then_cached(atoms_db):
    _append_submission(atoms_db, n_answers=5)
    conn = st.connect(atoms_db)
    df1 = A.get_atoms(conn)                       # cold → blocking full build
    assert df1 is not None and len(df1) == 5
    built1 = A._atoms_state["built"]
    df2 = A.get_atoms(conn)                       # fresh → same object, no rebuild
    conn.close()
    assert df2 is df1
    assert A._atoms_state["built"] == built1


def test_incremental_append_grows_frame(atoms_db):
    _append_submission(atoms_db, n_answers=5)
    conn = st.connect(atoms_db)
    df0 = A.get_atoms(conn)
    assert len(df0) == 5
    # a second submission — pure append → background incremental
    _append_submission(atoms_db, n_answers=3)
    stale = A.get_atoms(conn)                      # served immediately (still 5 rows)
    assert len(stale) == 5
    _wait_rebuild()
    fresh = A.get_atoms(conn)                      # now reflects the append
    conn.close()
    assert len(fresh) == 8


def test_incremental_equals_full(atoms_db):
    conn = st.connect(atoms_db)
    _append_submission(atoms_db, n_answers=5, value=4)
    A.get_atoms(conn)                             # cold full build (5 rows)
    _append_submission(atoms_db, n_answers=4, value=2)
    A.get_atoms(conn); _wait_rebuild()            # incremental append branch
    inc = A.get_atoms(conn)
    full = st.load_atoms(conn)                    # from-scratch full load
    conn.close()
    # incremental frame must equal a full reload as a multiset
    assert len(inc) == len(full) == 9
    assert sorted(inc["response_id"].tolist()) == sorted(full["response_id"].tolist())
    assert inc["value"].sum() == full["value"].sum()
    assert (inc["item_id"].value_counts().sort_index()
            .equals(full["item_id"].value_counts().sort_index()))
    # incremental≡full at the DTYPE level too: the category downcast must survive
    # the union_categoricals concat, or the cache silently re-bloats on append.
    assert inc.dtypes.to_dict() == full.dtypes.to_dict()
    for c in st._ATOMS_CAT_COLS:
        assert str(inc[c].dtype) == "category", c


def test_invalidate_forces_full_blocking_rebuild(atoms_db):
    _append_submission(atoms_db, n_answers=5)
    conn = st.connect(atoms_db)
    A.get_atoms(conn)
    # structural edit the data-key can't see: retag the form's section in place
    conn.execute("UPDATE org_unit SET path='Bureau/Renamed' WHERE id=1")
    conn.commit()
    A.invalidate_atoms()
    assert A._atoms_state["force_full"] is True
    df = A.get_atoms(conn)                         # blocking full rebuild
    conn.close()
    assert A._atoms_state["force_full"] is False
    assert (df["org_path"] == "Bureau/Renamed").all()


def test_deletion_triggers_full_rebuild(atoms_db):
    _append_submission(atoms_db, n_answers=5)
    conn = st.connect(atoms_db)
    df0 = A.get_atoms(conn)
    assert len(df0) == 5
    _delete_last_answer(atoms_db)                 # COUNT drops → not a pure append
    A.get_atoms(conn); _wait_rebuild()            # full rebuild via background
    fresh = A.get_atoms(conn)
    conn.close()
    assert len(fresh) == 4


def test_ttl_lapse_refreshes_in_background(atoms_db):
    _append_submission(atoms_db, n_answers=5)
    conn = st.connect(atoms_db)
    A.get_atoms(conn)
    built0 = A._atoms_state["built"]
    # force the TTL to look lapsed with an unchanged key
    with A._atoms_lock:
        A._atoms_state["built"] = time.time() - A._ATOMS_TTL - 1
    served = A.get_atoms(conn)                     # serves stale, schedules bg full
    assert served is not None
    _wait_rebuild()
    conn.close()
    assert A._atoms_state["built"] > built0        # rebuilt, timestamp advanced


def _persist_and_wait(df, key, amax, timeout=10.0):
    """Force a snapshot write and block until the pickle exists on disk."""
    A._last_persist = 0.0                          # defeat the 5-min throttle
    A._persist_atoms_async(df, key, amax)
    pkl, keyf = A._atoms_pkl_paths()
    deadline = time.time() + timeout
    while time.time() < deadline:
        if os.path.exists(pkl) and os.path.exists(keyf):
            with A._atoms_persist_lock:            # ensure the write finished
                return
        time.sleep(0.01)
    raise AssertionError("persist did not complete within timeout")


def test_pickle_hydrate_warms_cache(atoms_db):
    _append_submission(atoms_db, n_answers=5)
    conn = st.connect(atoms_db)
    df = A.get_atoms(conn)                          # cold build
    key = A._atoms_state["key"]
    _persist_and_wait(df, key, A._atoms_state["answer_maxid"])
    # simulate a restart: drop the in-process cache, then hydrate from the snapshot
    with A._atoms_lock:
        A._atoms_state.update({"key": None, "df": None, "built": 0.0,
                               "answer_maxid": 0, "force_full": False,
                               "rebuilding": False, "bg_full": False, "epoch": 0})
    A._hydrate_atoms_from_pickle(conn)
    conn.close()
    assert A._atoms_state["df"] is not None
    assert len(A._atoms_state["df"]) == 5
    assert A._atoms_state["key"] == key            # hydrated, no rebuild needed


def test_pickle_hydrate_ignores_stale_key(atoms_db):
    _append_submission(atoms_db, n_answers=5)
    conn = st.connect(atoms_db)
    df = A.get_atoms(conn)
    _persist_and_wait(df, A._atoms_state["key"], A._atoms_state["answer_maxid"])
    # data changes while "the server is down" → snapshot key no longer matches
    _append_submission(atoms_db, n_answers=3)
    with A._atoms_lock:
        A._atoms_state.update({"key": None, "df": None, "built": 0.0,
                               "answer_maxid": 0, "force_full": False,
                               "rebuilding": False, "bg_full": False, "epoch": 0})
    A._hydrate_atoms_from_pickle(conn)
    conn.close()
    assert A._atoms_state["df"] is None            # stale snapshot ignored


def test_concurrent_reads_never_see_partial(atoms_db):
    _append_submission(atoms_db, n_answers=5)
    conn0 = st.connect(atoms_db)
    A.get_atoms(conn0); conn0.close()
    _append_submission(atoms_db, n_answers=3)      # trigger a rebuild
    results, errors = [], []

    def reader():
        try:
            c = st.connect(atoms_db)
            df = A.get_atoms(c)
            c.close()
            results.append(df)
        except Exception as e:                     # pragma: no cover
            errors.append(e)

    threads = [threading.Thread(target=reader) for _ in range(8)]
    for t in threads: t.start()
    for t in threads: t.join()
    _wait_rebuild()
    assert not errors
    # every concurrent caller saw a valid frame (old=5 or new=8), never None/partial
    assert all(isinstance(df, pd.DataFrame) and len(df) in (5, 8) for df in results)


# --------------------------------------------------------------------------- #
# Frame ⟷ high-water-mark consistency (the dropped-responses bug)
#
# The cache tracks a high-water mark of answer.id and appends only rows past it.
# If the mark is ever read a moment AFTER the frame it labels, an answer another
# connection commits in that gap lands past the frame but under the mark — so every
# later `a.id > mark` append skips it for good. That silently stranded a whole run
# of freshly-encoded responses on live (an outside activity's 286 answers were in
# the DB but absent from the cached frame, so its Type-3 report showed nothing and
# it dropped out of the activity picker). The fix: snapshot the mark FIRST and bound
# the load to it, so frame and mark always cover exactly the same rows.
# --------------------------------------------------------------------------- #

def test_load_atoms_upto_partitions_cleanly(atoms_db):
    """upto/after windows tile the answers with no gap and no overlap, so a frame
    bounded to a mark plus the >mark append equals a from-scratch full load."""
    _append_submission(atoms_db, n_answers=5)      # answers 1..5   (response 1)
    _append_submission(atoms_db, n_answers=4)      # answers 6..9   (response 2)
    _append_submission(atoms_db, n_answers=3)      # answers 10..12 (response 3)
    conn = st.connect(atoms_db)
    full = st.load_atoms(conn)
    lo = st.load_atoms(conn, upto_answer_id=5)     # <= mark
    hi = st.load_atoms(conn, after_answer_id=5)    # >  mark
    win = st.load_atoms(conn, after_answer_id=5, upto_answer_id=9)  # one window
    conn.close()
    assert len(full) == 12 and len(lo) == 5 and len(hi) == 7
    # lo ⊎ hi == full, exactly (disjoint cover — nothing dropped, nothing doubled)
    assert (sorted(lo["response_id"].tolist() + hi["response_id"].tolist())
            == sorted(full["response_id"].tolist()))
    assert len(win) == 4                            # answers 6..9 only


def test_build_snapshots_mark_before_load_so_a_race_commit_is_never_stranded(
        atoms_db, monkeypatch):
    """A commit that lands the instant the build snapshots the mark must be DEFERRED
    (absent from this frame AND behind the mark), then picked up whole by the next
    append — never lost. Pre-fix, the mark was read after the load, so such a commit
    sat past the frame but under the mark and no `a.id > mark` append ever reloaded it."""
    _append_submission(atoms_db, n_answers=5)      # baseline: answers 1..5, mark 5
    conn = st.connect(atoms_db)
    real_maxid = A._answer_maxid
    state = {"fired": False, "pre_race_max": None}

    def racing_maxid(c):
        m = real_maxid(c)                          # mark snapshotted FIRST...
        if not state["fired"]:                     # ...then a commit races in (once)
            state["fired"] = True
            state["pre_race_max"] = m
            _append_submission(atoms_db, n_answers=3)   # answers 6..8, uncounted here
        return m

    monkeypatch.setattr(A, "_answer_maxid", racing_maxid)
    df = A.get_atoms(conn)                          # cold build; race lands at snapshot
    # Frame excludes the racing rows and the stored mark stays behind them → the two
    # agree. (Pre-fix the mark would have jumped to 8 while the frame held only 5.)
    assert len(df) == 5
    assert A._atoms_state["answer_maxid"] == state["pre_race_max"] == 5
    # Next request sees new data → background append loads (5, 8] and folds the
    # deferred rows in. They were deferred, never dropped.
    A.get_atoms(conn); _wait_rebuild()
    fresh = A.get_atoms(conn)
    conn.close()
    assert len(fresh) == 8


def test_hydrate_restores_persisted_mark(atoms_db):
    """A v2 snapshot round-trips the frame WITH the mark it was built to, so the
    warmed cache resumes appending from the right place (not a re-read MAX(id))."""
    _append_submission(atoms_db, n_answers=5)
    conn = st.connect(atoms_db)
    df = A.get_atoms(conn)
    key, mark = A._atoms_state["key"], A._atoms_state["answer_maxid"]
    _persist_and_wait(df, key, mark)
    with A._atoms_lock:
        A._atoms_state.update({"key": None, "df": None, "built": 0.0,
                               "answer_maxid": 0, "force_full": False,
                               "rebuilding": False, "bg_full": False, "epoch": 0})
    A._hydrate_atoms_from_pickle(conn)
    conn.close()
    assert A._atoms_state["df"] is not None and len(A._atoms_state["df"]) == 5
    assert A._atoms_state["answer_maxid"] == mark   # mark restored from the sidecar


def test_hydrate_ignores_legacy_sidecar(atoms_db):
    """A tag-less sidecar — the format the pre-fix (buggy) persist path wrote, whose
    frame may be short — is refused, so a stale/short pickle is dropped and rebuilt
    clean rather than resurrected on restart."""
    _append_submission(atoms_db, n_answers=5)
    conn = st.connect(atoms_db)
    df = A.get_atoms(conn)
    key = A._atoms_state["key"]
    pkl, keyf = A._atoms_pkl_paths()
    df.to_pickle(pkl)
    with open(keyf, "w") as f:                      # OLD format: bare repr(key)
        f.write(repr(key))
    with A._atoms_lock:
        A._atoms_state.update({"key": None, "df": None, "built": 0.0,
                               "answer_maxid": 0, "force_full": False,
                               "rebuilding": False, "bg_full": False, "epoch": 0})
    A._hydrate_atoms_from_pickle(conn)
    conn.close()
    assert A._atoms_state["df"] is None             # legacy sidecar ignored


# --------------------------------------------------------------------------- #
# Bounded staleness — a hung/dead background worker must not freeze the report
# (regression: a live activity report sat at 12 of 44 responses for hours)
# --------------------------------------------------------------------------- #

def test_frozen_frame_is_rebuilt_inline_past_the_stale_bound(atoms_db):
    _append_submission(atoms_db, n_answers=5)
    conn = st.connect(atoms_db)
    assert len(A.get_atoms(conn)) == 5
    # Simulate a worker that hung: it is "running" forever and never swaps.
    with A._atoms_lock:
        A._atoms_state["rebuilding"] = True
        A._atoms_state["rebuild_started"] = time.time()
    _append_submission(atoms_db, n_answers=3)
    assert len(A.get_atoms(conn)) == 5            # inside the bound: stale is fine
    with A._atoms_lock:                           # ...but the lag outlives the bound
        A._atoms_state["stale_since"] = time.time() - A._ATOMS_MAX_STALE - 1
    fresh = A.get_atoms(conn)                     # blocks and catches up (incrementally)
    conn.close()
    assert len(fresh) == 8
    assert A._atoms_state["stale_since"] == 0.0
    with A._atoms_lock:                           # release the simulated hung worker
        A._atoms_state["rebuilding"] = False


def test_hung_worker_is_replaced_after_the_stuck_window(atoms_db):
    _append_submission(atoms_db, n_answers=5)
    conn = st.connect(atoms_db)
    A.get_atoms(conn)
    with A._atoms_lock:
        A._atoms_state["rebuilding"] = True
        A._atoms_state["rebuild_started"] = time.time() - A._REBUILD_STUCK - 1
    epoch0 = A._atoms_state["epoch"]
    _append_submission(atoms_db, n_answers=3)
    A.get_atoms(conn)                              # stale → spawns a replacement worker
    assert A._atoms_state["epoch"] == epoch0 + 1   # the dead one is fenced off
    _wait_rebuild()
    assert len(A.get_atoms(conn)) == 8
    conn.close()


def test_view_serve_stale_is_bounded_and_prewarm_rebuilds(atoms_db):
    A._view_memo.clear(); A._view_prev.clear()
    A._atoms_state["key"] = "k1"
    assert A.view_memo("t", (), lambda: "old") == "old"
    A._atoms_state["key"] = "k2"                   # data changed; memo key now misses
    A._views_warming, A._views_warming_since = True, time.time()
    assert A.view_memo("t", (), lambda: "new") == "old"              # inside window: last-good
    assert A.view_memo("t", (), lambda: "new", rebuild=True) == "new"  # re-warm really rebuilds
    A._atoms_state["key"] = "k3"
    A._views_warming_since = time.time() - A._VIEWS_WARM_MAX - 1     # window long expired
    try:
        assert A.view_memo("t", (), lambda: "newer") == "newer"      # no open-ended staleness
    finally:
        A._views_warming = False
        A._view_memo.clear(); A._view_prev.clear()


def test_concat_atoms_tolerates_mismatched_category_dtype():
    """A delta whose category dtype disagrees with the base (int vs str) used to
    raise 'dtype of categories must be the same' and 500 every atoms-backed page."""
    import pandas as pd
    import storage as st
    base = st._categorize_atoms(pd.DataFrame(
        {"served_by_rp_id": [1, 2], "topic": ["a", "b"], "v": [1.0, 2.0]}))
    add = pd.DataFrame({"served_by_rp_id": pd.Categorical(["x"]),
                        "topic": ["c"], "v": [3.0]})
    out = st.concat_atoms(base, add)
    assert len(out) == 3
    assert isinstance(out["topic"].dtype, pd.CategoricalDtype)
