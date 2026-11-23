"""Admin page: restructure the directory onto a new bureau structure (/admin/restructure).

Owner-requested (docs/ORG_RESTRUCTURE_RUNBOOK.md): from a phone, an administrator
uploads the PRIVATE staff mapping, sees exactly what would change against live data
(a preview that rolls back), and applies it in one step. Applying takes a verified
backup first and makes every change in ONE transaction -- all or nothing. Open
Work, documents and approvals are never reassigned (directory_restructure).

The uploaded mapping (staff names and ids) is kept only as the pending preview in
app_setting, the same database that already holds those names, and is removed on
apply or discard. Only the administrator capability reaches /admin paths.
"""
from __future__ import annotations

import hashlib
import json
from urllib.parse import parse_qs

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse, RedirectResponse

import backups as bk
import directory_restructure as dr
import storage as st
import tzutil as tz

PENDING = "restructure.pending"
MAX_UPLOAD = 512 * 1024


def _digest(mapping):
    return hashlib.sha256(json.dumps(mapping, sort_keys=True, ensure_ascii=False).encode()).hexdigest()[:16]


def _validate(mapping):
    if not isinstance(mapping, dict) or not isinstance(mapping.get("staff", []), list):
        raise ValueError("That file is not a restructure mapping (it needs a \"staff\" list).")
    for key in ("reuse",):
        if key in mapping and not isinstance(mapping[key], dict):
            raise ValueError(f"\"{key}\" must be an object of old path -> new unit.")
    if "retire" in mapping and not isinstance(mapping["retire"], list):
        raise ValueError("\"retire\" must be a list of old unit paths.")


def run(conn, mapping, *, apply):
    """(ok, log, error). Runs the restructure in one immediate transaction and commits
    only when `apply` is True and nothing went wrong; otherwise rolls back."""
    log = []
    conn.execute("BEGIN IMMEDIATE")
    try:
        dr.build(conn, dr.load_plan(), mapping, log)
    except ValueError as exc:
        conn.rollback()
        return False, log, str(exc)
    except Exception:
        conn.rollback()
        raise
    if apply:
        conn.commit()
    else:
        conn.rollback()
    return True, log, None


def make_router(templates, get_conn, db_path, audit):
    """`db_path` is a callable returning the live database path (backed up before apply)."""
    router = APIRouter()

    def page(request, conn, **ctx):
        pending = _pending(conn)
        log = ctx.get("log") or []
        counts = {"units": sum(l.startswith(("CREATE", "MOVE", "UPDATE")) for l in log),
                  "staff": sum(l.startswith("STAFF") for l in log),
                  "created": sum(l.startswith("NEW") for l in log),
                  "retired": sum(l.startswith("RETIRE") for l in log)}
        return templates.TemplateResponse(request, "admin_restructure.html", {
            "nav_active": "directory", "pending": pending, "counts": counts, **ctx})

    def _pending(conn):
        try:
            return json.loads(st.get_setting(conn, PENDING) or "null")
        except ValueError:
            return None

    @router.get("/admin/restructure", response_class=HTMLResponse)
    def restructure_page(request: Request):
        conn = get_conn()
        try:
            return page(request, conn)
        finally:
            conn.close()

    @router.post("/admin/restructure/preview", response_class=HTMLResponse)
    async def restructure_preview(request: Request):
        form = await request.form()
        up = form.get("mapping")
        data = await up.read() if hasattr(up, "read") else b""
        conn = get_conn()
        try:
            try:
                if not data or len(data) > MAX_UPLOAD:
                    raise ValueError("Choose the restructure mapping file (.json).")
                mapping = json.loads(data.decode("utf-8-sig"))
                _validate(mapping)
            except (ValueError, UnicodeDecodeError) as exc:
                msg = str(exc) if isinstance(exc, ValueError) and "mapping" in str(exc) else \
                    "That file could not be read as a restructure mapping (.json)."
                return page(request, conn, error=msg)
            ok, log, error = run(conn, mapping, apply=False)
            if ok:
                st.set_setting(conn, PENDING, json.dumps({
                    "digest": _digest(mapping), "mapping": mapping, "at": tz.now_iso(),
                    "by": request.state.user["username"]}, ensure_ascii=False))
            audit(request, conn, "restructure_preview", target_type="directory",
                  summary=f"previewed a directory restructure ({len(mapping.get('staff', []))} staff): "
                          + ("ready to apply" if ok else "stopped"))
            return page(request, conn, log=log, error=error, previewed=ok)
        finally:
            conn.close()

    @router.post("/admin/restructure/apply", response_class=HTMLResponse)
    async def restructure_apply(request: Request):
        raw = parse_qs((await request.body()).decode("utf-8"), keep_blank_values=True)
        f = {k: (v[0] if v else "").strip() for k, v in raw.items()}
        conn = get_conn()
        try:
            pending = _pending(conn)
            if not pending or f.get("digest") != pending.get("digest"):
                return page(request, conn, error="Preview the mapping again before applying: "
                                                 "the previewed file is no longer the pending one.")
            if f.get("confirm") != "1":
                return page(request, conn, error="Tick the confirmation box to apply.")
            try:
                meta = bk.make_backup(db_path(), kind="manual")
            except Exception as exc:          # noqa: BLE001 -- never restructure without a backup
                return page(request, conn, error=f"The backup failed, so nothing was changed: {exc!r}")
            ok, log, error = run(conn, pending["mapping"], apply=True)
            if ok:
                conn.execute("DELETE FROM app_setting WHERE key=?", (PENDING,))
                conn.commit()
            audit(request, conn, "restructure_apply", target_type="directory", target_id=meta["name"],
                  summary=(f"applied the directory restructure ({sum(1 for l in log if l.startswith('STAFF'))} "
                           f"staff placed); backup {meta['name']}") if ok
                  else f"directory restructure stopped, nothing changed; backup {meta['name']}")
            return page(request, conn, log=log, error=error, applied=ok, backup=meta["name"])
        finally:
            conn.close()

    @router.post("/admin/restructure/discard")
    def restructure_discard(request: Request):
        conn = get_conn()
        try:
            conn.execute("DELETE FROM app_setting WHERE key=?", (PENDING,))
            conn.commit()
        finally:
            conn.close()
        return RedirectResponse("/admin/restructure", status_code=303)

    return router
