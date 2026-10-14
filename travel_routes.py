"""Travel filing pages (docs/TRAVEL_FILING_PLAN.md, section 8). Rules live in travel.py and
travel_rules.py; this module reads the request, calls them and renders.

No middleware gate covers /travel, so every handler checks the switch, then ownership
(travel.can_view / travel.is_owner), and every POST checks that Origin / Referer, when
present, is this site."""
from __future__ import annotations
import re
from datetime import timedelta
from urllib.parse import parse_qs, quote, urlparse

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse, RedirectResponse

import rooms
import storage as st
import travel
import travel_checklist as tc
import travel_rules as tr

_REF = re.compile(r"^TF-\d{4}-\d{4,}$")
STATUS_BADGE = {"open": "amber", "ready": "blue", "submitted": "green", "withdrawn": "grey"}


def make_router(templates, get_conn, today_local, *, audit, base_url):
    router = APIRouter()
    templates.env.globals["travel_kind_labels"] = travel.KIND_LABELS
    templates.env.globals["travel_status_labels"] = travel.STATUS_LABELS
    templates.env.globals["travel_status_badge"] = STATUS_BADGE

    async def _posted(request):
        raw = parse_qs((await request.body()).decode("utf-8"), keep_blank_values=True)
        return {k: (v[0] if v else "").strip() for k, v in raw.items()}

    def _same_origin(request) -> bool:
        """Origin / Referer, when the browser sends them, must name this site (there is no CSRF
        token anywhere in the app and the session cookie is SameSite=Lax)."""
        allowed = {request.headers.get("host"), request.headers.get("x-forwarded-host")}
        try:
            allowed.add(urlparse(base_url(request)).netloc)
        except Exception:                                   # noqa: BLE001
            pass
        for h in ("origin", "referer"):
            v = request.headers.get(h)
            if v and urlparse(v).netloc not in allowed:
                return False
        return True

    def _forbidden(request, why="this page"):
        return templates.TemplateResponse(request, "forbidden.html",
                                          {"capability": why, "show_scope": False}, status_code=403)

    def _missing(request):
        return templates.TemplateResponse(request, "travel_filing.html",
                                          {"nav_active": "travel_mine", "missing": True}, status_code=404)

    def _off(request):
        return templates.TemplateResponse(request, "travel_index.html",
                                          {"nav_active": "travel_mine", "off": True, "filings": [], "todo": [],
                                           "warnings": [], "msg": None, "err": None})

    def _go(path, msg=None, err=None):
        q = f"?ok={quote(msg[:200])}" if msg else (f"?err={quote(err[:200])}" if err else "")
        return RedirectResponse(path + q, status_code=303)

    def _decorate(f, today):
        words, tone = travel.deadline_words(f, today) if f["status"] in ("open", "ready") else (None, None)
        return {**f, "deadline_text": words, "deadline_tone": tone}

    # ----------------------------------------------------------------- index ---

    @router.get("/travel", response_class=HTMLResponse)
    def travel_index(request: Request):
        user, q = request.state.user, dict(request.query_params)
        conn = get_conn()
        try:
            if not travel.enabled(conn):
                return _off(request)
            today = today_local()
            filings = [_decorate(travel.refresh_deadline(conn, f), today) for f in travel.list_for_user(conn, user["id"])]
            choices = travel.activity_choices(conn, user, today)
            lo, hi = (today - timedelta(days=60)).isoformat(), (today + timedelta(days=60)).isoformat()
            near = [c for c in choices if lo <= c["end"] and c["start"] <= hi]
            filed = travel.filing_summaries(conn, user["id"], [c["entry_id"] for c in near if c["entry_id"]],
                                            [c["event_id"] for c in near if c["event_id"]], today)
            todo = [c for c in near if ("entry", c["entry_id"]) not in filed and ("event", c["event_id"]) not in filed][:12]
            warnings = [{"filing": f, "text": f"{f['ref_code']} ({f['act_title']}) was submitted, but there is no liquidation yet."}
                        for f in travel.unliquidated_cas(conn, user["id"], today)]
            return templates.TemplateResponse(request, "travel_index.html", {
                "nav_active": "travel_mine", "tab": "mine", "filings": filings, "todo": todo, "warnings": warnings,
                "msg": (q.get("ok") or "")[:200] or None, "err": (q.get("err") or "")[:200] or None, "off": False})
        finally:
            conn.close()

    # ------------------------------------------------------------------- new ---

    def _new_context(conn, user, source, f, *, error="", ack=False):
        today = today_local()
        live = travel.live_ca(conn, user["id"], source["entry_id"], source["event_id"])
        has_dates = bool(source["start"] and source["end"])
        ca_msg = tr.ca_lead_error(source["start"], today) if has_dates else None
        cas = [c for c in travel.list_for_user(conn, user["id"])
               if c["kind"] == "ca" and c["status"] == "submitted" and not travel.liquidations_of(conn, c["id"])]
        jo_default = False
        prof = st.get_user_profile(conn, user["id"]) or {}
        if prof.get("rp_id"):
            rp = st.get_rp(conn, prof["rp_id"]) or {}
            jo_default = rp.get("employment_type") in ("job_order", "consultant")
        return {"nav_active": "travel_mine", "tab": "new", "source": source, "f": f, "error": error, "ack": ack,
                "live_ca": live, "ca_msg": ca_msg if has_dates else None, "cas": cas, "jo_default": jo_default,
                "kinds": [(k, travel.KIND_LABELS[k]) for k in travel.KINDS
                          if not (k == "reimbursement" and live)],
                "questions": tc.ANSWER_KEYS, "roles": tc.ROLES, "mc114": travel.MC114_FORMATS,
                "kind_labels": travel.KIND_LABELS}

    @router.get("/travel/new", response_class=HTMLResponse)
    def travel_new(request: Request):
        user, q = request.state.user, dict(request.query_params)
        conn = get_conn()
        try:
            if not travel.enabled(conn):
                return _off(request)
            try:
                source = travel.resolve_source(
                    conn, user, today_local(), entry_id=int(q["entry"]) if (q.get("entry") or "").isdigit() else None,
                    event_id=int(q["event"]) if (q.get("event") or "").isdigit() else None, on=q.get("date"))
            except travel.TravelError as e:
                return _go("/travel", err=str(e))
            live = travel.live_ca(conn, user["id"], source["entry_id"], source["event_id"])
            f = {"kind": q.get("kind") if q.get("kind") in travel.KINDS else ("liquidation" if live else "ca"),
                 "title": "", "start": "", "end": "", "venue": ""}
            ctx = _new_context(conn, user, source, f)
            ctx["f"]["jo_cos"] = "1" if ctx["jo_default"] else ""
            ctx["f"]["cert_of_appearance_available"] = "1"
            return templates.TemplateResponse(request, "travel_new.html", ctx)
        finally:
            conn.close()

    @router.post("/travel/new")
    async def travel_new_post(request: Request):
        if not _same_origin(request):
            return _forbidden(request, "this request (it came from another site)")
        f, user = await _posted(request), request.state.user
        conn = get_conn()
        try:
            if not travel.enabled(conn):
                return _off(request)
            today = today_local()
            try:
                src = travel.resolve_source(
                    conn, user, today, entry_id=int(f["entry"]) if (f.get("entry") or "").isdigit() else None,
                    event_id=int(f["event"]) if (f.get("event") or "").isdigit() else None, on=f.get("date"))
            except travel.TravelError as e:
                return _go("/travel", err=str(e))
            if src["source_kind"] == "blank":
                src.update(title=f.get("title", ""), start=f.get("start", ""), end=f.get("end", ""),
                           venue=f.get("venue", ""))
            kind = f.get("kind", "")
            try:
                filing = travel.create_filing(
                    conn, user, kind=kind, source=src, answers=f, mc114_format=f.get("mc114_format", "none"),
                    role=f.get("role", ""), dpo_no=f.get("dpo_no", ""), dpo_date=f.get("dpo_date", ""),
                    ca_filing_id=int(f["ca"]) if (f.get("ca") or "").isdigit() else None,
                    advance_amount=f.get("advance_amount"), today=today, acknowledged=f.get("ack") == "1")
            except travel.Unliquidated as e:
                ctx = _new_context(conn, user, src, f)
                ctx["warn"] = [_decorate(x, today) for x in e.filings]
                return templates.TemplateResponse(request, "travel_new.html", ctx)
            except travel.TravelError as e:
                return templates.TemplateResponse(request, "travel_new.html",
                                                  _new_context(conn, user, src, f, error=str(e)), status_code=400)
            audit(request, conn, "travel_open", target_type="travel_filing", target_id=filing["id"],
                  summary=f"opened {filing['ref_code']} ({travel.KIND_LABELS[filing['kind']].lower()})")
            return _go(f"/travel/f/{filing['ref_code']}", msg="Filing opened. Work through the checklist below.")
        finally:
            conn.close()

    # --------------------------------------------------------------- one filing ---

    def _load(request, conn, ref, *, owner=False):
        """(filing, None) or (None, response). A stranger gets 404; an Admin Unit member may look but
        not edit (`owner=True` makes that a 403)."""
        if not travel.enabled(conn):
            return None, _off(request)
        filing = travel.get_by_ref(conn, ref) if _REF.match(ref) else None
        user = request.state.user
        if not travel.can_view(conn, user, filing):
            return None, _missing(request)
        if owner and not travel.is_owner(user, filing):
            return None, _forbidden(request, "changing someone else's travel filing")
        return filing, None

    def _detail(request, conn, filing, *, status_code=200, error=None):
        q = dict(request.query_params)
        today = today_local()
        filing = travel.refresh_deadline(conn, filing)
        items = travel.view_items(conn, filing)
        flags = travel.flags_of(conn, filing["id"])
        missing = travel.missing_for(conn, filing)
        ans = travel.answers_of(filing)
        liqs = travel.liquidations_of(conn, filing["id"]) if filing["kind"] == "ca" else []
        ca = travel.get_filing(conn, filing["ca_filing_id"]) if filing["ca_filing_id"] else None
        return templates.TemplateResponse(request, "travel_filing.html", {
            "nav_active": "travel_mine", "tab": "mine", "missing": False, "f": _decorate(filing, today),
            "items": items, "flags": flags, "missing_list": missing, "ans": ans, "owner": travel.is_owner(request.state.user, filing),
            "questions": [q_ for q_ in tc.ANSWER_KEYS if filing["kind"] in q_[2]], "roles": tc.ROLES,
            "mc114": travel.MC114_FORMATS, "liquidations": liqs, "ca": ca, "editable": filing["status"] in ("open", "ready"),
            "msg": (q.get("ok") or "")[:200] or None, "err": error or (q.get("err") or "")[:200] or None,
            "rev": tc.CHECKLIST_REV, "can_manual_amount": filing["kind"] in ("ca", "liquidation") and not filing["ca_filing_id"],
        }, status_code=status_code)

    @router.get("/travel/f/{ref}", response_class=HTMLResponse)
    def travel_filing(request: Request, ref: str):
        conn = get_conn()
        try:
            filing, bad = _load(request, conn, ref)
            return bad or _detail(request, conn, filing)
        finally:
            conn.close()

    @router.post("/travel/f/{ref}/answers")
    async def travel_answers(request: Request, ref: str):
        if not _same_origin(request):
            return _forbidden(request, "this request (it came from another site)")
        f = await _posted(request)
        conn = get_conn()
        try:
            filing, bad = _load(request, conn, ref, owner=True)
            if bad:
                return bad
            try:
                travel.update_answers(conn, filing, f, mc114_format=f.get("mc114_format"), role=f.get("role"),
                                      dpo_no=f.get("dpo_no"), dpo_date=f.get("dpo_date"),
                                      advance_amount=f.get("advance_amount") if "advance_amount" in f else None)
            except travel.TravelError as e:
                return _go(f"/travel/f/{ref}", err=str(e))
            return _go(f"/travel/f/{ref}", msg="Answers saved. The checklist has been updated.")
        finally:
            conn.close()

    @router.post("/travel/f/{ref}/item/{code}")
    async def travel_item(request: Request, ref: str, code: str):
        if not _same_origin(request):
            return _forbidden(request, "this request (it came from another site)")
        f = await _posted(request)
        conn = get_conn()
        try:
            filing, bad = _load(request, conn, ref, owner=True)
            if bad:
                return bad
            try:
                travel.save_item(conn, filing, code,
                                 drive_url=f["drive_url"] if "drive_url" in f else None,
                                 na=(f["na"] == "1") if "na" in f else None,
                                 fmis_ref=f["fmis_ref"] if "fmis_ref" in f else None,
                                 note=f["note"] if "note" in f else None)
            except travel.TravelError as e:
                return _go(f"/travel/f/{ref}#item-{code}", err=str(e))
            return _go(f"/travel/f/{ref}#item-{code}", msg="Saved.")
        finally:
            conn.close()

    # ------------------------------------------------------- ready / submitted ---

    @router.get("/travel/f/{ref}/ready", response_class=HTMLResponse)
    def travel_ready_page(request: Request, ref: str):
        conn = get_conn()
        try:
            filing, bad = _load(request, conn, ref)
            if bad:
                return bad
            items = travel.view_items(conn, filing)
            printed = [i for i in items if i["requirement"] == "required" and i["state"] != "na"]
            return templates.TemplateResponse(request, "travel_ready.html", {
                "nav_active": "travel_mine", "tab": "mine", "f": _decorate(filing, today_local()),
                "printed": printed, "missing_list": travel.missing_for(conn, filing),
                "owner": travel.is_owner(request.state.user, filing),
                "msg": (request.query_params.get("ok") or "")[:200] or None,
                "err": (request.query_params.get("err") or "")[:200] or None})
        finally:
            conn.close()

    def _transition(name, fn, audit_action, done_msg, verb):
        @router.post(f"/travel/f/{{ref}}/{name}")
        async def handler(request: Request, ref: str):
            if not _same_origin(request):
                return _forbidden(request, "this request (it came from another site)")
            conn = get_conn()
            try:
                filing, bad = _load(request, conn, ref, owner=True)
                if bad:
                    return bad
                back = f"/travel/f/{ref}/ready" if name in ("ready", "submit") else f"/travel/f/{ref}"
                try:
                    fn(conn, filing)
                except travel.TravelError as e:
                    return _go(back, err=str(e))
                audit(request, conn, audit_action, target_type="travel_filing", target_id=filing["id"],
                      summary=f"{verb} {filing['ref_code']}")
                return _go(back if name != "withdraw" else "/travel", msg=done_msg)
            finally:
                conn.close()
        handler.__name__ = f"travel_{name}"
        return handler

    _transition("ready", travel.mark_ready, "travel_ready", "Marked ready. Print the documents below and sign where it says.", "marked ready")
    _transition("submit", travel.mark_submitted, "travel_submit", "Marked submitted. Good work.", "marked submitted")
    _transition("withdraw", travel.withdraw, "travel_withdraw", "Filing withdrawn.", "withdrew")

    # ------------------------------------------------- app admin: the switch ---
    # /admin/* is already gated to the app admin role by the auth middleware.

    @router.get("/admin/travel", response_class=HTMLResponse)
    def admin_travel(request: Request):
        q = dict(request.query_params)
        conn = get_conn()
        try:
            return templates.TemplateResponse(request, "admin_travel.html", {
                "nav_active": "admin_travel", "enabled": travel.enabled(conn),
                "msg": (q.get("ok") or "")[:200] or None, "err": (q.get("err") or "")[:200] or None})
        finally:
            conn.close()

    @router.post("/admin/travel")
    async def admin_travel_save(request: Request):
        if not _same_origin(request):
            return _forbidden(request, "this request (it came from another site)")
        f = await _posted(request)
        conn = get_conn()
        try:
            on = f.get("enabled") == "1"
            st.set_setting(conn, "travel.enabled", "1" if on else "0")
            audit(request, conn, "travel_settings_save", target_type="setting", target_id="travel.enabled",
                  summary="switched travel filing " + ("on" if on else "off"))
            return _go("/admin/travel", msg="Saved.")
        finally:
            conn.close()

    return router
