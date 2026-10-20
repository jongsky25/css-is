"""Travel filing pages (docs/TRAVEL_FILING_PLAN.md, section 8). Rules live in travel.py and
travel_rules.py; this module reads the request, calls them and renders.

Every handler checks the feature switch and ownership (travel.can_view / travel.is_owner).
Writes also use the shared exact-origin policy, including in a standalone router."""
from __future__ import annotations
import asyncio
import hashlib
import json
import logging
import os
import re
from datetime import timedelta
from urllib.parse import parse_qs, quote, urlencode, urlparse

from fastapi import APIRouter, Request
from starlette.background import BackgroundTask
from starlette.concurrency import run_in_threadpool
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse

import gdocs_relay
import travel_docs
import travel_rates
import ratelimit
import rooms
import storage as st
import travel
import travel_submissions as submissions
import travel_checklist as tc
import travel_rules as tr
import travel_readings
import travel_scan
import ai_core

_REF = re.compile(r"^TF-\d{4}-\d{4,}$")
STATUS_BADGE = {"open": "amber", "ready": "blue", "submitted": "green", "withdrawn": "grey"}
_OPERATION_PATH = {'parameters': [{'name': 'operation_id', 'in': 'path', 'required': True,
                                  'schema': {'type': 'string', 'format': 'uuid'}}]}


def make_router(templates, get_conn, today_local, *, audit, base_url):
    router = APIRouter()
    templates.env.globals["travel_kind_labels"] = travel.KIND_LABELS
    templates.env.globals["travel_status_labels"] = travel.STATUS_LABELS
    templates.env.globals["travel_status_badge"] = STATUS_BADGE
    templates.env.globals["travel_flag_label"] = tr.flag_label

    async def _posted(request):
        raw = parse_qs((await request.body()).decode("utf-8"), keep_blank_values=True)
        return {k: (v[0] if v else "").strip() for k, v in raw.items()}

    def _same_origin(request) -> bool:
        """Keep standalone-router checks aligned with the shared boundary."""
        from request_security import same_origin_write
        canonical = os.environ.get("CSS_BASE_URL")
        if not canonical and os.environ.get("SPACE_HOST"):
            canonical = "https://" + os.environ["SPACE_HOST"]
        return same_origin_write(request, canonical)

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
        base, hash_, fragment = path.partition("#")          # the query goes before the #fragment, or it is never sent
        return RedirectResponse(base + q + hash_ + fragment, status_code=303)

    def _decorate(f, today):
        words, tone = travel.deadline_words(f, today) if f["status"] in ("open", "ready") else (None, None)
        return {**f, "deadline_text": words, "deadline_tone": tone}

    # ------------------------------------------------------- policy rates (T9) ---

    def _rate_opts(filing, raw):
        """The posted claim-level options, cleaned, plus the length of the trip."""
        opts = travel_docs.normalize_rates(raw)
        opts["trip_days"] = len(travel_docs.trip_days(filing["act_start"], filing["act_end"]))
        return opts

    def _working(conn):
        return lambda day: rooms.is_working_day(conn, day)

    @router.get("/travel/rates", response_class=HTMLResponse)
    def travel_rate_card(request: Request):
        """The policy rates the prepare page applies, printed in full so anyone can check one."""
        conn = get_conn()
        try:
            if not travel.enabled(conn):
                return _off(request)
            return templates.TemplateResponse(request, "travel_rates.html", {
                "nav_active": "travel_mine", "tab": "rates", "r": travel_rates,
                "clusters": [(n, travel_rates.CLUSTER_DTE[n], [x for x in travel_rates.REGIONS if x[2] == n]) for n in (3, 2, 1)]})
        finally:
            conn.close()

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

    def _new_context(conn, user, source, f, *, error="", ack=False, operation_id=None):
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
        operation_id = operation_id or submissions.issue(conn, user['id'])
        return {"nav_active": "travel_mine", "tab": "new", "source": source, "f": f, "error": error, "ack": ack,
                "operation_id": operation_id, "submission_status_url": f'/travel/submissions/{operation_id}',
                "live_ca": live, "ca_msg": ca_msg if has_dates else None, "cas": cas, "jo_default": jo_default,
                "kinds": [(k, travel.KIND_LABELS[k]) for k in travel.KINDS
                          if not (k == "reimbursement" and live)],
                "questions": tc.ANSWER_KEYS, "roles": tc.ROLES, "mc114": travel.MC114_FORMATS,
                "kind_labels": travel.KIND_LABELS}

    @router.get('/travel/new/{operation_id}', response_class=HTMLResponse, openapi_extra=_OPERATION_PATH)
    @router.get("/travel/new", response_class=HTMLResponse)
    def travel_new(request: Request):
        user, q = request.state.user, dict(request.query_params)
        conn = get_conn()
        try:
            if not travel.enabled(conn):
                return _off(request)
            operation_id = request.path_params.get('operation_id')
            if operation_id:
                try:
                    outcome = _submission_state(conn, user, operation_id)
                except submissions.MissingOperation:
                    return _submission_page(request, {'state': 'unknown', 'location': None,
                        'message': 'This submission could not be found.'}, 404)
                if outcome['state'] == 'completed' and outcome['location']:
                    response = _go(outcome['location'])
                    response.headers['Cache-Control'] = 'no-store'
                    return response
                if outcome['state'] != 'ready':
                    return _submission_page(request, outcome,
                        status_url=f'/travel/submissions/{operation_id}')
            try:
                source = travel.resolve_source(
                    conn, user, today_local(), entry_id=int(q["entry"]) if (q.get("entry") or "").isdigit() else None,
                    event_id=int(q["event"]) if (q.get("event") or "").isdigit() else None, on=q.get("date"))
            except travel.TravelError as e:
                return _go("/travel", err=str(e))
            if not operation_id:
                key = submissions.issue(conn, user['id'])
                params = {k: q[k] for k in ('entry', 'event', 'date', 'kind') if k in q}
                suffix = '?' + urlencode(params) if params else ''
                return RedirectResponse('/travel/new/' + key + suffix, status_code=303,
                                        headers={'Cache-Control': 'no-store'})
            live = travel.live_ca(conn, user["id"], source["entry_id"], source["event_id"])
            default_kind = "liquidation" if live else "ca"
            if not live and source["start"] and tr.ca_lead_error(source["start"], today_local()):
                default_kind = "reimbursement"
            f = {"kind": q.get("kind") if q.get("kind") in travel.KINDS else default_kind,
                 "title": "", "start": "", "end": "", "venue": ""}
            ctx = _new_context(conn, user, source, f, operation_id=operation_id)
            ctx["f"]["jo_cos"] = "1" if ctx["jo_default"] else ""
            ctx["f"]["cert_of_appearance_available"] = "1"
            return templates.TemplateResponse(request, "travel_new.html", ctx, headers={'Cache-Control': 'no-store'})
        finally:
            conn.close()

    def _json_requested(request):
        return 'application/json' in request.headers.get('accept', '')

    def _submission_json(data, status=200):
        return JSONResponse(data, status_code=status, headers={'Cache-Control': 'no-store'})

    def _submission_page(request, outcome, status=200, *, status_url=None):
        return templates.TemplateResponse(request, 'travel_submission.html',
            {'nav_active': 'travel_mine', 'outcome': outcome, 'status_url': status_url},
            status_code=status, headers={'Cache-Control': 'no-store'})

    def _submission_state(conn, user, operation_id):
        row = submissions.lookup(conn, user['id'], operation_id)
        state, location = row['state'], None
        message = {
            'ready': 'No completed filing is recorded yet. Check again or retry the original form.',
            'pending': 'The result is not confirmed yet. Check again or retry this same submission.',
            'rejected': 'This attempt did not open a filing. Review the form and submit again.',
            'completed': 'Your filing was opened. Continue to its checklist.'}[state]
        if state == 'completed':
            filing = travel.get_by_ref(conn, row['ref'])
            if filing and travel.is_owner(user, filing):
                location = f'/travel/f/{filing["ref_code"]}'
            else:
                message = 'This filing was opened previously but is no longer available. Contact the Admin Unit.'
        return {'state': state, 'message': message, 'location': location}

    @router.get('/travel/submissions/{operation_id}', response_class=HTMLResponse)
    def travel_submission_status(request: Request, operation_id: str):
        conn = get_conn()
        try:
            try:
                outcome = _submission_state(conn, request.state.user, operation_id)
                status = 200
            except submissions.MissingOperation:
                outcome = {'state': 'unknown', 'message': 'This submission could not be found.', 'location': None}
                status = 404
            if _json_requested(request):
                return _submission_json(outcome, status)
            return _submission_page(request, outcome, status)
        finally:
            conn.close()

    @router.post('/travel/new/{operation_id}', openapi_extra=_OPERATION_PATH)
    @router.post("/travel/new")
    async def travel_new_post(request: Request):
        if not _same_origin(request):
            return _forbidden(request, "this request (it came from another site)")
        f, user = await _posted(request), request.state.user
        conn = get_conn()
        try:
            if not travel.enabled(conn):
                return _off(request)
            today, src = today_local(), None

            def source_for_form():
                source = travel.resolve_source(
                    conn, user, today, entry_id=int(f["entry"]) if (f.get("entry") or "").isdigit() else None,
                    event_id=int(f["event"]) if (f.get("event") or "").isdigit() else None, on=f.get("date"))
                if source['source_kind'] == 'blank':
                    source.update(title=f.get('title', ''), start=f.get('start', ''), end=f.get('end', ''),
                                  venue=f.get('venue', ''))
                return source

            def create():
                nonlocal src
                src = source_for_form()
                filing = travel.create_filing(
                    conn, user, kind=f.get('kind', ''), source=src, answers=f, mc114_format=f.get("mc114_format", "none"),
                    role=f.get("role", ""), dpo_no=f.get("dpo_no", ""), dpo_date=f.get("dpo_date", ""),
                    ca_filing_id=int(f["ca"]) if (f.get("ca") or "").isdigit() else None,
                    advance_amount=f.get("advance_amount"), today=today, acknowledged=f.get("ack") == "1", commit=False)
                audit(request, conn, "travel_open", target_type="travel_filing", target_id=filing["id"],
                      summary=f"opened {filing['ref_code']} ({travel.KIND_LABELS[filing['kind']].lower()})", commit=False)
                return filing['ref_code']

            try:
                path_key = request.path_params.get('operation_id')
                if path_key and path_key != f.get('operation_id'):
                    raise submissions.ChangedSubmission('This form has changed. Check the submission status before continuing.')
                if not f.get('operation_id'):
                    raise travel.TravelError('This form needs a refresh to prevent duplicate filings. Review it and submit again.')
                submissions.execute(conn, user['id'], f['operation_id'], f, create,
                                    rejected_exceptions=(travel.TravelError,))
                outcome = _submission_state(conn, user, f['operation_id'])
                if _json_requested(request):
                    return _submission_json(outcome)
                if outcome['location']:
                    return _go(outcome['location'], msg='Filing opened. Work through the checklist below.')
                return _submission_page(request, outcome, 410)
            except (travel.TravelError, submissions.RejectedSubmission) as e:
                key = submissions.issue(conn, user['id']) if _json_requested(request) else None
                if _json_requested(request):
                    return _submission_json({'state': 'rejected', 'message': str(e), 'operation_id': key,
                        'status_url': f'/travel/submissions/{key}', 'ack_required': isinstance(e, travel.Unliquidated)},
                        200 if isinstance(e, travel.Unliquidated) else 400)
                if src is None:
                    try:
                        src = source_for_form()
                    except travel.TravelError:
                        return _go('/travel', err=str(e))
                ctx = _new_context(conn, user, src, f, error=str(e))
                if isinstance(e, travel.Unliquidated):
                    ctx['warn'] = [_decorate(x, today) for x in e.filings]
                return templates.TemplateResponse(request, 'travel_new.html', ctx,
                    status_code=200 if isinstance(e, travel.Unliquidated) else 400, headers={'Cache-Control': 'no-store'})
            except (submissions.MissingOperation, submissions.ChangedSubmission) as e:
                outcome = {'state': 'unknown', 'message': str(e), 'location': None}
                status = 404 if isinstance(e, submissions.MissingOperation) else 409
                if _json_requested(request):
                    return _submission_json(outcome, status)
                return _submission_page(request, outcome, status)
            except Exception as e:
                conn.rollback()
                logging.getLogger(__name__).error('Travel submission result not confirmed (%s)', type(e).__name__)
                outcome = {'state': 'unknown', 'message': 'The result could not be confirmed. Check the submission status before starting another filing.', 'location': None}
                if _json_requested(request):
                    return _submission_json(outcome, 503)
                return _submission_page(request, outcome, 503,
                    status_url=f'/travel/submissions/{f.get("operation_id", "")}')
        finally:
            conn.close()

    @router.post('/travel/submissions/{operation_id}/close')
    def travel_close_submission(request: Request, operation_id: str):
        if not _same_origin(request):
            return _forbidden(request, 'this request (it came from another site)')
        conn = get_conn()
        try:
            try:
                submissions.close_unfinished(conn, request.state.user['id'], operation_id,
                    on_close=lambda: audit(request, conn, 'travel_submission_close',
                        target_type='travel_submission', target_id=operation_id,
                        summary='Closed an unfinished travel filing attempt.', commit=False))
            except submissions.MissingOperation:
                return _submission_json({'state': 'unknown', 'message': 'This submission could not be found.'}, 404)
            except Exception as e:
                conn.rollback()
                logging.getLogger(__name__).error('Travel submission close not confirmed (%s)', type(e).__name__)
                return _submission_page(request, {'state': 'unknown', 'location': None,
                    'message': 'The result is not confirmed. Check again before starting another filing.'},
                    503, status_url=f'/travel/submissions/{operation_id}')
            return _go(f'/travel/submissions/{operation_id}')
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
        travel.carry_from_ca(conn, filing)
        items = travel.view_items(conn, filing)
        flags = travel.flags_of(conn, filing["id"])
        missing = travel.missing_for(conn, filing)
        ans = travel.answers_of(filing)
        liqs = travel.liquidations_of(conn, filing["id"]) if filing["kind"] == "ca" else []
        ca = travel.get_filing(conn, filing["ca_filing_id"]) if filing["ca_filing_id"] else None
        questions = [q_ for q_ in tc.ANSWER_KEYS if filing["kind"] in q_[2]]
        return templates.TemplateResponse(request, "travel_filing.html", {
            "nav_active": "travel_mine", "tab": "mine", "missing": False, "f": _decorate(filing, today),
            "items": items, "flags": flags, "missing_list": missing, "ans": ans, "owner": travel.is_owner(request.state.user, filing),
            "next_action": travel.next_action(filing, items, flags, missing),
            "draftable": travel.forms_ready_to_draft(items) if filing["status"] in ("open", "ready") else [],
            "questions": questions, "roles": tc.ROLES,
            "role_label": dict(tc.ROLES).get(ans.get("role"), ""), "yes_answers": [label for key, label, _k in questions if ans.get(key)],
            "mc114": travel.MC114_FORMATS, "liquidations": liqs, "ca": ca, "editable": filing["status"] in ("open", "ready"),
            "msg": (q.get("ok") or "")[:200] or None, "err": error or (q.get("err") or "")[:200] or None,
            "peers": len(travel.peers_of(conn, filing)) if travel.is_owner(request.state.user, filing) else 0,
            "uploads_ready": _uploads_ready(conn), "rev": tc.CHECKLIST_REV, "can_manual_amount": filing["kind"] in ("ca", "liquidation") and not filing["ca_filing_id"],
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
            if "drive_url" in f:
                folder = travel.uploaded_folder(conn, filing, code)
                if folder and not _trash(folder):
                    return _go(f"/travel/f/{ref}#item-{code}", err="The files you uploaded could not be removed from "
                                                                  "Drive just now. Try again in a minute.")
            try:
                travel.save_item(conn, filing, code,
                                 drive_url=f["drive_url"] if "drive_url" in f else None,
                                 na=(f["na"] == "1") if "na" in f else None,
                                 fmis_ref=f["fmis_ref"] if "fmis_ref" in f else None,
                                 note=f["note"] if "note" in f else None)
            except travel.TravelError as e:
                return _go(f"/travel/f/{ref}#item-{code}", err=str(e))
            said = "Saved."
            if f.get("everyone") == "1" and "na" in f:        # "apply to everyone on this DPO"
                n = travel.apply_na_to_peers(conn, filing, code, f["na"] == "1", by=request.state.user["username"])
                said = "Saved" + (f" for you and {n} other traveller{'s' if n != 1 else ''} on this DPO." if n
                                  else ". Nobody else on this DPO needed changing.")
            return _go(f"/travel/f/{ref}#item-{code}", msg=said)
        finally:
            conn.close()

    def _uploads_ready(conn):
        """Upload to Drive is offered only once the relay has answered a test with the version that has it."""
        try:
            v = int(st.get_setting(conn, "travel.relay_version", "0") or 0)
        except ValueError:
            v = 0
        return gdocs_relay.configured() and v >= gdocs_relay.UPLOAD_VERSION

    def _trash(file_id):
        try:
            return gdocs_relay.get_relay().trash_file(file_id).ok
        except Exception:                                   # noqa: BLE001 - a failed trash is reported, not raised
            return False

    @router.post("/travel/f/{ref}/upload")
    async def travel_upload(request: Request, ref: str, code: str = ""):
        """The raw bytes of one file for a checklist row (X-Filename carries its name). The file goes to the
        office's Drive through the relay and is dropped here; only the folder link is kept. The file is saved
        only after the relay confirms it, so a failure leaves the row as it was."""
        if not _same_origin(request):
            return _jerr("This request came from another site.", 403)
        try:
            if int(request.headers.get("content-length") or 0) > travel_scan.MAX_BYTES:
                return _jerr("That file is too large. Use one under 6 MB.", 413)
        except ValueError:
            return _jerr("Send the file.")
        raw = await request.body()
        if not raw or len(raw) > travel_scan.MAX_BYTES:
            return _jerr("That file is empty or too large. Use one under 6 MB.", 413)
        mime = travel_scan.sniff(raw)
        if not mime:
            return _jerr("Use a photo (JPG, PNG, WebP) or a PDF.", 415)
        conn = get_conn()
        try:
            if not travel.enabled(conn):
                return _jerr("Travel filing is not switched on.", 403)
            filing = travel.get_by_ref(conn, ref) if _REF.match(ref) else None
            user = request.state.user
            if not travel.can_view(conn, user, filing):
                return _jerr("Not found.", 404)
            if not travel.is_owner(user, filing):
                return _jerr("Only the person who filed can change this.", 403)
            if not _uploads_ready(conn):
                return _jerr("Uploading is not switched on yet. Paste a Google Drive link instead.", 503)
            try:
                travel._editable(filing)
                spec = travel._item_spec(filing, code)
                if spec.handling not in ("upload", "carry"):
                    raise travel.TravelError("This document does not take an uploaded file.")
            except travel.TravelError as e:
                return _jerr(str(e))
            if not ratelimit.allow("travel_upload", f"u{user['id']}"):
                return _jerr("Too many uploads. Wait a minute and try again.", 429)
            from urllib.parse import unquote
            stem = re.sub(r"[^A-Za-z0-9._ -]", "_", unquote(request.headers.get("x-filename") or "")).strip(" .")[:60]
            ext = {"image/jpeg": "jpg", "image/png": "png", "image/webp": "webp", "application/pdf": "pdf"}[mime]
            stem = re.sub(r"\.(jpe?g|png|webp|pdf)$", "", stem, flags=re.I) or "file"
            digest = hashlib.sha256(raw).hexdigest()[:12]
            share = [user.get("username")] if user.get("username") else []
            ip = request.client.host if request.client else None
            upload = run_in_threadpool(
                gdocs_relay.get_relay().upload_file, request_id=f"{ref}:{code}:{digest}", folder_key=ref, item_key=code,
                name=f"{ref}_{code}_{stem}.{ext}", mime=mime, data=raw, share_with=share)
            # A ticket, receipt, DPO or Certificate of Appearance is also read, at the same time. The reading is only
            # offered back to the browser (checked against the filing for the DPO and the certificate); a failed or
            # refused read never stops the file from being saved.
            doc = travel_scan.DOC_FOR.get(code)
            reading, ai_off = None, False
            if doc and ratelimit.allow("travel_scan", f"u{user['id']}"):
                res, found = await asyncio.gather(upload, travel_scan.read_doc(doc, conn, user, ip, raw, mime),
                                                  return_exceptions=True)
                if isinstance(found, dict):
                    reading = found
                else:
                    ai_off = isinstance(found, ai_core.AIError)
            else:
                res = await upload
            del raw
            if isinstance(res, BaseException):
                return _jerr("The documents relay failed. Try again.", 502)
            if not res.ok:
                return _jerr(gdocs_relay.describe(res.error), 502 if res.error in ("not_configured", "unreachable") else 400)
            try:
                travel.save_upload(conn, filing, code, res.data.get("folder_id"), res.data.get("folder_url"))
            except travel.TravelError as e:
                return _jerr(str(e))
            checks, fill = travel_scan.check(doc, reading, filing) if reading else ([], None)
            if reading and doc in (travel_scan.DOC_RECEIPT, travel_scan.DOC_APPEARANCE):
                travel_readings.save(conn, filing["id"], code, doc, reading)
            if fill and doc == travel_scan.DOC_DPO and fill.get("dpo_date") and not fill.get("dpo_no") and not filing["dpo_date"]:
                travel.set_dpo_date(conn, filing, fill["dpo_date"])          # the number matches and the date was empty: no button needed
                checks = checks + [f"The DPO date ({fill['dpo_date']}) was added to this filing from your DPO."]
                fill = None
            audit(request, conn, "travel_upload", target_type="travel_filing", target_id=ref,
                  summary=f"stored a file for {code}")
            return JSONResponse({"ok": True, "name": res.data.get("name", ""), "count": res.data.get("count"),
                                 "url": res.data.get("folder_url"), "reading": reading, "doc": doc if reading else None,
                                 "checks": checks, "fill": fill, "ai": not ai_off})
        finally:
            conn.close()

    @router.post("/travel/f/{ref}/item/{code}/remove-upload")
    async def travel_remove_upload(request: Request, ref: str, code: str):
        """Trash the files uploaded for a row (in Drive), then clear the row. Pasted links are never touched."""
        if not _same_origin(request):
            return _forbidden(request, "this request (it came from another site)")
        conn = get_conn()
        try:
            filing, bad = _load(request, conn, ref, owner=True)
            if bad:
                return bad
            folder = travel.uploaded_folder(conn, filing, code)
            if not folder:
                return _go(f"/travel/f/{ref}#item-{code}", err="There are no uploaded files on this row.")
            if not _trash(folder):
                return _go(f"/travel/f/{ref}#item-{code}", err="The files could not be removed from Drive just now. "
                                                              "Try again in a minute.")
            try:
                travel.clear_upload(conn, filing, code)
            except travel.TravelError as e:
                return _go(f"/travel/f/{ref}#item-{code}", err=str(e))
            audit(request, conn, "travel_remove_upload", target_type="travel_filing", target_id=ref,
                  summary=f"removed the files stored for {code}")
            return _go(f"/travel/f/{ref}#item-{code}", msg="Uploaded files removed.")
        finally:
            conn.close()

    @router.post("/travel/f/{ref}/link-check")
    async def travel_link_check(request: Request, ref: str):
        """JSON: {code, url}. Asks the relay whether the office mailbox can open the pasted file,
        then saves the link and the file id. Owner only; rate limited per account."""
        def fail(msg, status=400):
            return JSONResponse({"ok": False, "error": msg}, status_code=status)
        if not _same_origin(request):
            return fail("This request came from another site.", 403)
        try:
            body = await request.json()
        except ValueError:
            return fail("Send JSON with a code and a url.")
        code, url = str((body or {}).get("code") or ""), str((body or {}).get("url") or "")
        conn = get_conn()
        try:
            if not travel.enabled(conn):
                return fail("Travel filing is not switched on.", 403)
            filing = travel.get_by_ref(conn, ref) if _REF.match(ref) else None
            user = request.state.user
            if not travel.can_view(conn, user, filing):
                return fail("Not found.", 404)
            if not travel.is_owner(user, filing):
                return fail("Only the person who filed can change this.", 403)
            if not ratelimit.allow("travel_relay", f"u{user['id']}"):
                return fail("Too many checks. Wait a minute and try again.", 429)
            link = travel.valid_drive_link(url)
            if not link:
                return fail("Paste a Google Drive link (it starts with https://drive.google.com/).")
            try:
                travel._item_spec(filing, code)
            except travel.TravelError as e:
                return fail(str(e))
            res = gdocs_relay.get_relay().check_link(link)
            if not res.ok:
                return fail(gdocs_relay.describe(res.error), 502 if res.error in ("not_configured", "unreachable") else 400)
            try:
                travel.save_item(conn, filing, code, drive_url=link)
            except travel.TravelError as e:
                return fail(str(e))
            travel.set_drive_file_id(conn, filing, code, res.data.get("id"))
            return JSONResponse({"ok": True, "name": res.data.get("name", ""), "mime": res.data.get("mime", "")})
        finally:
            conn.close()

    # ----------------------------------------------- prepare and generate (T5) ---

    SIG_SETTINGS = ("head_name", "head_title", "certifier_name", "certifier_title", "station")

    def _sig_settings(conn, user_id=None):
        """The signatory names the forms start with: the Travel filing settings, with the Director and the filer's
        division head filled in from the directory where the settings leave them blank (see travel.directory_signers)."""
        base = {k: st.get_setting(conn, f"travel.sig.{k}", "") for k in SIG_SETTINGS}
        return travel.directory_signers(conn, user_id, base) if user_id else base

    def _generate_items(conn, filing):
        return [it for it in travel.view_items(conn, filing) if it["handling"] == "generate" and it["state"] != "na"]

    def _jerr(msg, status=400):
        return JSONResponse({"ok": False, "error": msg}, status_code=status)

    @router.get("/travel/f/{ref}/prepare", response_class=HTMLResponse)
    def travel_prepare(request: Request, ref: str):
        conn = get_conn()
        try:
            filing, bad = _load(request, conn, ref, owner=True)
            if bad:
                return bad
            if filing["status"] not in ("open", "ready"):
                return _go(f"/travel/f/{ref}", err="This filing can no longer be changed.")
            profile = st.get_user_profile(conn, request.state.user["id"]) or {}
            data = travel_docs.defaults(conn, filing, profile, _sig_settings(conn, request.state.user["id"]),
                                        readings=travel_readings.for_filing(conn, filing["id"]))
            data["ceilings"] = [[m, rt, a] for (m, rt), a in sorted(travel.ceilings(conn).items())]
            data["routes"] = [[r[0], r[1]] for r in conn.execute("SELECT code, label FROM travel_route_type WHERE active=1 ORDER BY sort, code")]
            data["policy"] = {
                "regions": [[c, label, travel_rates.region_dte(c)] for c, label, _cl in travel_rates.REGIONS],
                "day_kinds": [[c, g, label, rule] for c, g, label, rule in travel_rates.DAY_KINDS],
                "bases": [[c, label, inp, note] for c, label, inp, note in travel_rates.BASES],
                "places": {b: [[c, label, float(a), q] for c, label, a, q in travel_rates.place_choices(b)]
                           for b in ("airport", "terminal", "shuttle")},
                "rates_url": f"/travel/f/{ref}/rates"}
            data["ref"] = ref
            data["post_url"] = f"/travel/f/{ref}/generate"
            data["status_url"] = f"/travel/f/{ref}/status"
            data["scan_url"] = f"/travel/f/{ref}/scan"
            items = _generate_items(conn, filing)
            data["kind"] = filing["kind"]
            data["advance"] = filing["advance_amount"]
            data["codes"] = [it["code"] for it in items]
            data["answers"] = travel.answers_of(filing)
            data["mc114_format"] = filing["mc114_format"]
            data["filing_url"] = f"/travel/f/{ref}"
            return templates.TemplateResponse(request, "travel_prepare.html", {
                "nav_active": "travel_mine", "tab": "mine", "f": filing, "items": items, "relay_ready": gdocs_relay.configured(),
                "prep_json": json.dumps(data, default=str).replace("</", "<\\/"),
                "ans": travel.answers_of(filing)})
        finally:
            conn.close()

    def _run_generation(ref, filing_id, payloads, revs, share_with):
        """BackgroundTask: one relay call per document, one at a time. Own connection; never raises."""
        conn = get_conn()
        try:
            relay = gdocs_relay.get_relay()
            by_code = {}
            for pl in payloads:
                by_code.setdefault(pl.item_code, []).append(pl)
            for code, docs in by_code.items():
                rev, urls, err = revs[code], [], ""
                for pl in docs:
                    res = relay.generate_doc(request_id=f"{ref}:{code}:{rev}:{pl.index}", template_key=pl.template_key,
                                             folder_key=ref, title=pl.title if pl.index == 1 else f"{pl.title} {pl.index}",
                                             fields=pl.fields, blocks=pl.blocks, rows=pl.rows, share_with=share_with)
                    if res.ok and res.data.get("url"):
                        urls.append(res.data["url"])
                    else:
                        err = gdocs_relay.describe_for_filer(res.error)
                        break
                if err or not urls:
                    travel.finish_item(conn, filing_id, code, rev, error=err or "No document came back.")
                else:
                    travel.finish_item(conn, filing_id, code, rev, url=urls[0],
                                       extra=("More: " + " ".join(urls[1:])) if len(urls) > 1 else None)
            travel.finish_generation(conn, filing_id)
        except Exception:                                   # noqa: BLE001 - never leave a run 'running'
            try:
                conn.execute("UPDATE travel_item SET doc_state=REPLACE(doc_state,'pending:','failed:'), "
                             "note='Something went wrong. Try again.' WHERE filing_id=? AND doc_state LIKE 'pending:%'", (filing_id,))
                travel.finish_generation(conn, filing_id)
            except Exception:                               # noqa: BLE001
                pass
        finally:
            conn.close()

    @router.post("/travel/f/{ref}/generate")
    async def travel_generate(request: Request, ref: str):
        """JSON: {rows, texts, signatories, mc114_text, codes?}. Rechecks the rides, opens flags,
        then makes the documents after the response. The posted values are used and dropped."""
        if not _same_origin(request):
            return _jerr("This request came from another site.", 403)
        try:
            body = await request.json()
        except ValueError:
            return _jerr("Send JSON.")
        conn = get_conn()
        try:
            if not travel.enabled(conn):
                return _jerr("Travel filing is not switched on.", 403)
            filing = travel.get_by_ref(conn, ref) if _REF.match(ref) else None
            user = request.state.user
            if not travel.can_view(conn, user, filing):
                return _jerr("Not found.", 404)
            if not travel.is_owner(user, filing):
                return _jerr("Only the person who filed can make these documents.", 403)
            if filing["status"] not in ("open", "ready"):
                return _jerr("This filing can no longer be changed.", 409)
            if filing["gen_state"] == "running" and travel.generation_status(conn, filing)["gen_state"] == "running":
                return _jerr("The documents are already being made.", 409)
            if not gdocs_relay.configured():
                return _jerr("Making forms automatically is not set up yet. Make the form yourself and paste its link on the filing page.", 503)
            if not ratelimit.allow("travel_relay", f"u{user['id']}"):
                return _jerr("Too many requests. Wait a minute and try again.", 429)
            norm = travel_docs.normalize(body)
            ceilings = travel.ceilings(conn)
            opts = _rate_opts(filing, norm["rates"])
            filing = travel.set_derived_answers(conn, filing, travel_docs.ride_answers(norm["rows"], ceilings, opts))
            travel.sync_flags(conn, filing, tr.flags_for(filing, norm["rows"], travel.answers_of(filing), ceilings,
                                                         opts, _working(conn)))
            items = _generate_items(conn, filing)
            wanted = body.get("codes") if isinstance(body.get("codes"), list) else None
            codes = [it["code"] for it in items if (not wanted or it["code"] in wanted)]
            if not codes:
                return _jerr("There is nothing to make for this filing.")
            profile = st.get_user_profile(conn, user["id"]) or {}
            payloads = travel_docs.build_payloads(
                filing["kind"], filing, profile, _sig_settings(conn, user["id"]), body, codes, ceilings=ceilings,
                items=travel.view_items(conn, filing), today=today_local())
            made = {pl.item_code for pl in payloads}
            if not made:
                return _jerr("Nothing to make: no rides need a form.")
            revs = travel.start_generation(conn, filing, sorted(made))
            share = [user.get("username")] if user.get("username") else []
            audit(request, conn, "travel_generate", target_type="travel_filing", target_id=filing["ref_code"],
                  summary="started making " + ", ".join(sorted(made)))
            task = BackgroundTask(_run_generation, ref, filing["id"], payloads, revs, share)
            return JSONResponse({"ok": True, "started": sorted(made), "flags": len(travel.flags_of(conn, filing["id"]))},
                                background=task)
        finally:
            conn.close()

    @router.post("/travel/f/{ref}/rates")
    async def travel_rates_calc(request: Request, ref: str):
        """JSON: {rows, rates}. What the policy allows for each day and ride, worked out here so the
        rules live in one place. Read-only: nothing is stored, so it is not audited."""
        if not _same_origin(request):
            return _jerr("This request came from another site.", 403)
        try:
            body = await request.json()
        except ValueError:
            return _jerr("Send JSON.")
        conn = get_conn()
        try:
            if not travel.enabled(conn):
                return _jerr("Travel filing is not switched on.", 403)
            filing = travel.get_by_ref(conn, ref) if _REF.match(ref) else None
            user = request.state.user
            if not travel.can_view(conn, user, filing):
                return _jerr("Not found.", 404)
            if not travel.is_owner(user, filing):
                return _jerr("Only the person who filed can use this.", 403)
            if not ratelimit.allow("travel_rates", f"u{user['id']}"):
                return _jerr("Too many requests. Wait a moment and try again.", 429)
            norm = travel_docs.normalize(body)
            opts = _rate_opts(filing, norm["rates"])
            calc = travel_rates.rates_for_rows(norm["rows"], opts, _working(conn))
            dte = travel_rates.region_dte(opts["region"])
            return JSONResponse({"ok": True, "dte": float(dte) if dte else None, "rows": [c.as_dict() for c in calc]})
        finally:
            conn.close()

    @router.post("/travel/f/{ref}/scan")
    async def travel_scan_document(request: Request, ref: str):
        """The raw bytes of one ticket, boarding pass or receipt (image or PDF) as the body. The AI reads the
        amount; the file is dropped as soon as the answer is back, so nothing is stored or audited."""
        if not _same_origin(request):
            return _jerr("This request came from another site.", 403)
        try:
            if int(request.headers.get("content-length") or 0) > travel_scan.MAX_BYTES:
                return _jerr("That file is too large. Use one under 6 MB.", 413)
        except ValueError:
            return _jerr("Send the file.")
        raw = await request.body()
        if not raw or len(raw) > travel_scan.MAX_BYTES:
            return _jerr("That file is empty or too large. Use one under 6 MB.", 413)
        mime = travel_scan.sniff(raw)
        if not mime:
            return _jerr("Use a photo (JPG, PNG, WebP) or a PDF.", 415)
        conn = get_conn()
        try:
            if not travel.enabled(conn):
                return _jerr("Travel filing is not switched on.", 403)
            filing = travel.get_by_ref(conn, ref) if _REF.match(ref) else None
            user = request.state.user
            if not travel.can_view(conn, user, filing):
                return _jerr("Not found.", 404)
            if not travel.is_owner(user, filing):
                return _jerr("Only the person who filed can use this.", 403)
            if not ratelimit.allow("travel_scan", f"u{user['id']}"):
                return _jerr("Too many scans. Wait a minute and try again.", 429)
            ip = request.client.host if request.client else None
            try:
                found = await travel_scan.read(conn, user, ip, raw, mime)
            except ai_core.AIError:
                return JSONResponse({"ok": False, "ai": False,
                                     "error": "Reading documents is not available right now. Type the amount in."})
            return JSONResponse({"ok": True, **found})
        finally:
            conn.close()

    @router.get("/travel/f/{ref}/status")
    def travel_status(request: Request, ref: str):
        conn = get_conn()
        try:
            if not travel.enabled(conn):
                return _jerr("Travel filing is not switched on.", 403)
            filing = travel.get_by_ref(conn, ref) if _REF.match(ref) else None
            if not travel.can_view(conn, request.state.user, filing):
                return _jerr("Not found.", 404)
            return JSONResponse({"ok": True, **travel.generation_status(conn, filing)})
        finally:
            conn.close()

    # ----------------------------------------------- Admin Unit: verify queue (T6) ---

    def _admin_unit(request, conn):
        """(None, None) when the signed-in user may decide flags, else (None, response)."""
        if not travel.enabled(conn):
            return _off(request)
        if not rooms.is_room_admin(conn, request.state.user):
            return _forbidden(request, "the travel verify queue (Administrative Section only)")
        return None

    @router.get("/travel/verify", response_class=HTMLResponse)
    def travel_verify(request: Request):
        q = dict(request.query_params)
        conn = get_conn()
        try:
            bad = _admin_unit(request, conn)
            if bad:
                return bad
            return templates.TemplateResponse(request, "travel_verify.html", {
                "nav_active": "travel_verify", "queue": travel.flag_queue(conn, "open"),
                "decided": travel.flag_queue(conn, "decided", limit=30), "flag_labels": tr.FLAG_LABELS,
                "msg": (q.get("ok") or "")[:200] or None, "err": (q.get("err") or "")[:200] or None})
        finally:
            conn.close()

    @router.post("/travel/verify/{flag_id}")
    async def travel_verify_decide(request: Request, flag_id: int):
        if not _same_origin(request):
            return _forbidden(request, "this request (it came from another site)")
        f = await _posted(request)
        conn = get_conn()
        try:
            bad = _admin_unit(request, conn)
            if bad:
                return bad
            flag = travel.get_flag(conn, flag_id)
            if not flag:
                return _go("/travel/verify", err="That flag does not exist.")
            try:
                done = travel.decide_flag(conn, flag, request.state.user.get("username") or "",
                                          f.get("outcome", ""), f.get("note", ""), f.get("supervisor_confirmed") == "1")
            except travel.TravelError as e:
                return _go("/travel/verify", err=str(e))
            audit(request, conn, "travel_flag_decide", target_type="travel_flag", target_id=str(flag_id),
                  summary=f"{done['state']} {flag['kind']} on filing {flag['filing_id']}")
            return _go("/travel/verify", msg=f"Marked {done['state']}.")
        finally:
            conn.close()

    # ------------------------------------- ceilings, routes and the library (T7) ---

    def _page(request, conn, name, ctx, status_code=200):
        q = dict(request.query_params)
        return templates.TemplateResponse(request, name, {
            "msg": (q.get("ok") or "")[:200] or None, "err": ctx.pop("err", None) or (q.get("err") or "")[:200] or None,
            **ctx}, status_code=status_code)

    @router.get("/travel/admin", response_class=HTMLResponse)
    def travel_admin(request: Request):
        conn = get_conn()
        try:
            bad = _admin_unit(request, conn)
            if bad:
                return bad
            return _page(request, conn, "travel_admin.html", {
                "nav_active": "travel_admin", "routes": travel.route_types(conn), "flat": travel.flat_ceilings(conn),
                "holiday_notice": travel.holiday_notice(conn, today_local())})
        finally:
            conn.close()

    @router.post("/travel/admin/ceilings")
    async def travel_admin_ceilings(request: Request):
        if not _same_origin(request):
            return _forbidden(request, "this request (it came from another site)")
        f = await _posted(request)
        conn = get_conn()
        try:
            bad = _admin_unit(request, conn)
            if bad:
                return bad
            try:
                n = travel.save_ceilings(conn, request.state.user.get("username") or "", f)
            except travel.TravelError as e:
                return _go("/travel/admin", err=str(e))
            audit(request, conn, "travel_ceiling_save", target_type="travel_ceiling", target_id="ceilings",
                  summary=f"saved travel ceilings and routes ({n} change{'s' if n != 1 else ''})")
            return _go("/travel/admin", msg="Saved." if n else "Nothing changed.")
        finally:
            conn.close()

    @router.post("/travel/admin/route")
    async def travel_admin_route(request: Request):
        if not _same_origin(request):
            return _forbidden(request, "this request (it came from another site)")
        f = await _posted(request)
        conn = get_conn()
        try:
            bad = _admin_unit(request, conn)
            if bad:
                return bad
            try:
                code = travel.add_route(conn, request.state.user.get("username") or "", f.get("label", ""), f.get("rer", ""))
            except travel.TravelError as e:
                return _go("/travel/admin", err=str(e))
            audit(request, conn, "travel_ceiling_save", target_type="travel_route_type", target_id=code,
                  summary=f"added approved route {code} with an RER ceiling")
            return _go("/travel/admin", msg="Route added. It now counts as approved.")
        finally:
            conn.close()

    @router.get("/travel/library", response_class=HTMLResponse)
    def travel_library(request: Request):
        conn = get_conn()
        try:
            bad = _admin_unit(request, conn)
            if bad:
                return bad
            return _page(request, conn, "travel_library.html", {
                "nav_active": "travel_library", "rows": travel.justifications(conn), "tokens": travel.LIB_TOKENS,
                "can_edit": travel.is_template_admin(conn, request.state.user), "formats": travel.MC114_FORMATS[1:]})
        finally:
            conn.close()

    @router.post("/travel/library")
    async def travel_library_save(request: Request):
        if not _same_origin(request):
            return _forbidden(request, "this request (it came from another site)")
        f = await _posted(request)
        conn = get_conn()
        try:
            bad = _admin_unit(request, conn)
            if bad:
                return bad
            if not travel.is_template_admin(conn, request.state.user):
                return _forbidden(request, "editing the justification library (template administrators only)")
            jid = int(f["id"]) if (f.get("id") or "").isdigit() else None
            try:
                jid = travel.save_justification(conn, request.state.user.get("username") or "", jid, f.get("title", ""),
                                                f.get("format", ""), f.get("body", ""), active=f.get("active") == "1")
            except travel.TravelError as e:
                return _go("/travel/library", err=str(e))
            audit(request, conn, "travel_library_save", target_type="travel_justification", target_id=str(jid),
                  summary="saved a justification text")
            return _go("/travel/library", msg="Saved.")
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

    def _admin_context(conn, q, **extra):
        keys = ("head_name", "head_title", "certifier_name", "certifier_title", "station")
        return {"nav_active": "admin_travel", "enabled": travel.enabled(conn),
                "relay_ready": gdocs_relay.configured(),
                "relay_host": urlparse(os.environ.get(gdocs_relay.ENV_URL, "")).netloc,
                "holiday_notice": travel.holiday_notice(conn, today_local()),
                "sig": {k: st.get_setting(conn, f"travel.sig.{k}", "") for k in keys},
                "template_admins": st.get_setting(conn, "travel.template_admins", ""),
                "msg": (q.get("ok") or "")[:200] or None, "err": (q.get("err") or "")[:200] or None, **extra}

    @router.get("/admin/travel", response_class=HTMLResponse)
    def admin_travel(request: Request):
        conn = get_conn()
        try:
            return templates.TemplateResponse(request, "admin_travel.html", _admin_context(conn, dict(request.query_params)))
        finally:
            conn.close()

    @router.post("/admin/travel/ping")
    async def admin_travel_ping(request: Request):
        if not _same_origin(request):
            return _forbidden(request, "this request (it came from another site)")
        conn = get_conn()
        try:
            if not ratelimit.allow("travel_relay", f"u{request.state.user['id']}"):
                return _go("/admin/travel", err="Too many tests. Wait a minute and try again.")
            res = gdocs_relay.get_relay().ping()
            if res.ok:                                      # remember which script version answered (gates uploads)
                try:
                    st.set_setting(conn, "travel.relay_version", str(int(res.data.get("version") or 1)))
                except (TypeError, ValueError):
                    pass
            return _go("/admin/travel", msg="The documents relay answered." if res.ok else None,
                       err=None if res.ok else gdocs_relay.describe(res.error))
        finally:
            conn.close()

    @router.post("/admin/travel/signatories")
    async def admin_travel_signatories(request: Request):
        if not _same_origin(request):
            return _forbidden(request, "this request (it came from another site)")
        f = await _posted(request)
        conn = get_conn()
        try:
            for k in ("head_name", "head_title", "certifier_name", "certifier_title", "station"):
                st.set_setting(conn, f"travel.sig.{k}", " ".join(f.get(k, "").split())[:120])
            names = [n.strip().lower() for n in f.get("template_admins", "").replace("\n", ",").split(",") if n.strip()]
            st.set_setting(conn, "travel.template_admins", ",".join(dict.fromkeys(names))[:1000])
            audit(request, conn, "travel_settings_save", target_type="setting", target_id="travel.sig",
                  summary="saved travel signatories and template administrators")
            return _go("/admin/travel", msg="Saved.")
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
