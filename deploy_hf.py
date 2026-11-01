#!/usr/bin/env python
"""Canonical — and ONLY — deploy for the live Hugging Face Space `equityinhealth/office-connect`.

    python deploy_hf.py            # interactive: confirms the live-DB swap
    python deploy_hf.py --yes      # non-interactive: auto-confirm (also used when backgrounded)

This is the whole shipping routine. There is NO GitHub step — git push is not how
this app deploys, and the GitHub mirror is not part of the workflow. Shipping = run
this script.

Why upload_folder and not `git push`: the local repo and the Space's git repo have
DISJOINT histories (no common ancestor) — `git push space main` is rejected and a
force-push would WIPE the live Space. `upload_folder` adds one commit on top of the
Space's current state (additive; preserves server-side files). See DEPLOY.md.

What it does:
  1. Legacy (no persistence): PULLS the live DB from ~/Downloads into css_is.db (the
     carrier that ships). Under persistence this is skipped (the bucket is the truth).
  2. Guards the version bump: aborts if APP_VERSION still equals the live version.
  3. Stamps build_info.json (version, git commit, deployer, timestamp) — build
     telemetry the live /ops admin dashboard reads to show which build is running.
  4. REDUNDANT-BACKUP GATE (persistence only): before the upload that restarts the
     Space, forces a fresh live snapshot, confirms it actually wrote, and downloads +
     integrity-checks a local copy — ABORTS if it can't, so a restart never discards
     un-snapshotted writes (the 2026-06-25 data-loss condition). Override only with
     --skip-backup / CSS_DEPLOY_SKIP_BACKUP=1. Needs CSS_ADMIN_USER/PASS (env/.env.local).
  5. upload_folder of the runtime closure (incl. version.py, build_info.json).
  6. Waits for RUNNING, then verifies /login shows the expected version.

Auth: HF token cached at ~/.cache/huggingface/token (user equityinhealth).
"""
import os, sys, time, glob, shutil, sqlite3, subprocess, json, urllib.error, urllib.request
import re
from html.parser import HTMLParser
from pathlib import Path

# Silence huggingface_hub's tqdm progress bars. When stdout is a pipe/file (every
# backgrounded deploy), the upload bars don't get a carriage-return TTY — each
# refresh writes a fresh line, so a single large file's upload spews tens of
# thousands of identical "100%" lines (a multi-MB log) and buries the real status.
os.environ.setdefault("HF_HUB_DISABLE_PROGRESS_BARS", "1")

# Force UTF-8 stdout: the status lines use ⚠️/✅, which crash under Windows' default
# cp1252 codec when stdout is redirected (e.g. a background run).
try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

# Floor EVERY socket with a read timeout. huggingface_hub's HTTP client issues
# upload/commit requests with no socket read timeout, so a stalled keep-alive
# connection blocks the whole deploy FOREVER (observed 2026-06-22: the commit hung
# for 20+ min with frozen CPU and a multi-MB progress-bar redraw storm). A default
# timeout makes a stuck read raise and retry instead of hanging indefinitely.
import socket
socket.setdefaulttimeout(float(os.environ.get("HF_DEPLOY_TIMEOUT", "120")))

# Optional verbose tracing (set HF_DEPLOY_DEBUG=1): stream every HF/urllib3 HTTP
# request so we can see exactly which call stalls if a deploy misbehaves again.
if os.environ.get("HF_DEPLOY_DEBUG"):
    import logging
    logging.basicConfig(level=logging.DEBUG, stream=sys.stdout,
                        format="%(asctime)s %(name)s %(levelname)s %(message)s")
    for n in ("huggingface_hub", "urllib3", "requests", "httpx", "httpcore"):
        logging.getLogger(n).setLevel(logging.DEBUG)

REPO_ID = "equityinhealth/office-connect"
LIVE_BASE = f"https://{REPO_ID.replace('/', '-')}.hf.space"
LOCAL_DB = "css_is.db"


def telegram_snapshot_summary(path):
    """Read only queue-state totals from the already verified pre-deploy backup."""
    conn = None
    try:
        conn = sqlite3.connect(Path(path).resolve().as_uri() + '?mode=ro', uri=True)
        result = {}
        for table, states in (
            ('telegram_update', {'queued', 'processing', 'processed', 'ignored', 'cancelled'}),
            ('telegram_delivery', {'queued', 'claimed', 'sending', 'retry_wait', 'accepted', 'failed', 'uncertain', 'cancelled'}),
            ('telegram_link_challenge', {'issued', 'claimed', 'confirmed', 'cancelled'}),
        ):
            result[table] = {state: count for state, count in conn.execute('SELECT state,count(*) FROM ' + table + ' GROUP BY state')
                             if state in states}
        return result
    except (OSError, sqlite3.Error):
        return {'available': False}
    finally:
        if conn is not None:
            conn.close()


def telegram_ops_summary(html):
    """Extract only typed operational fields; never print an admin page or raw JSON."""
    class Parser(HTMLParser):
        def __init__(self):
            super().__init__()
            self.active = False
            self.parts = []
        def handle_starttag(self, tag, attrs):
            if tag == 'script' and dict(attrs).get('id') == 'telegram-diagnostics':
                self.active = True
        def handle_endtag(self, tag):
            if tag == 'script':
                self.active = False
        def handle_data(self, data):
            if self.active:
                self.parts.append(data)
    parser = Parser()
    parser.feed(html)
    value = json.loads(''.join(parser.parts))
    worker = value['worker']
    result = {}
    for key, pattern in (('version', r'\d+\.\d{2}'), ('commit', r'[a-f0-9]{7,40}')):
        item = value.get(key)
        if isinstance(item, str) and re.fullmatch(pattern, item):
            result[key] = item
    for key in ('scheduler_disabled', 'stale', 'bot_configured', 'webhook_configured',
                'link_origin_configured', 'queue_available'):
        if type(worker.get(key)) is bool:
            result[key] = worker[key]
    for key in ('processed', 'sent', 'webhook_responses'):
        if type(worker.get(key)) is int and 0 <= worker[key] < 2**63:
            result[key] = worker[key]
    if worker.get('reply_transport') in ('webhook', 'direct'):
        result['reply_transport'] = worker['reply_transport']
    if isinstance(worker.get('location'), str) and re.fullmatch(r'[a-z_]+\.py:[0-9]{1,6}', worker['location']):
        result['location'] = worker['location']
    for key, allowed in (
        ('state', {'not_started', 'running', 'finished', 'failed'}),
        ('stage', {'connect', 'updates', 'change_routes', 'change_notices', 'reminders', 'delivery', 'cleanup'}),
        ('error', {'database_error', 'configuration_error', 'worker_error'}),
    ):
        if isinstance(worker.get(key), str) and worker[key] in allowed:
            result[key] = worker[key]
    result['switches'] = {key: worker.get('switches', {}).get(key) for key in ('inbound', 'delivery', 'link')
                          if type(worker.get('switches', {}).get(key)) is bool}
    for key, states in (
        ('updates', {'queued', 'processing', 'processed', 'ignored', 'cancelled'}),
        ('deliveries', {'queued', 'claimed', 'sending', 'retry_wait', 'accepted', 'failed', 'uncertain', 'cancelled'}),
    ):
        result[key] = {state: count for state, count in worker.get(key, {}).items()
                       if state in states and type(count) is int and 0 <= count < 2**63}
    provider = worker.get('provider')
    if isinstance(provider, dict):
        safe = {}
        for key, allowed in (
            ('state', {'accepted', 'failed', 'retry_wait', 'uncertain'}),
            ('error', {'provider_rejected', 'rate_limited', 'transport_failure', 'response_unverified'}),
            ('transport_error', {'tls_certificate', 'tls', 'dns', 'proxy', 'connect_timeout',
                                 'read_timeout', 'timeout', 'connection', 'protocol',
                                 'client_error', 'transport_failure'}),
        ):
            if isinstance(provider.get(key), str) and provider[key] in allowed:
                safe[key] = provider[key]
        status = provider.get('http_status')
        if type(status) is int and 100 <= status <= 599:
            safe['http_status'] = status
        result['provider'] = safe
    network = worker.get('network')
    if isinstance(network, dict):
        result['network'] = {}
        for name in ('requests', 'httpx'):
            item = network.get(name)
            if not isinstance(item, dict):
                continue
            safe = {}
            for key, allowed in (
                ('state', {'ok', 'http_error', 'invalid_response', 'failed', 'not_configured'}),
                ('error', {'tls_certificate', 'tls', 'dns', 'proxy', 'connect_timeout',
                           'read_timeout', 'timeout', 'connection', 'protocol',
                           'client_error', 'transport_failure'}),
            ):
                if isinstance(item.get(key), str) and item[key] in allowed:
                    safe[key] = item[key]
            status = item.get('http_status')
            if type(status) is int and 100 <= status <= 599:
                safe['http_status'] = status
            result['network'][name] = safe
    return result


def report_live_telegram_status():
    """Use the existing deployment admin identity for read-only, sanitized health."""
    if not os.environ.get('CSS_ADMIN_USER') or not os.environ.get('CSS_ADMIN_PASS'):
        print('Telegram diagnostics: unavailable (deployment admin credentials not configured).')
        return False
    try:
        import pull_backup as pb
        opener, _ = pb._opener()
        pb.login(opener, LIVE_BASE, os.environ['CSS_ADMIN_USER'], os.environ['CSS_ADMIN_PASS'])
        for attempt in range(3):
            suffix = '?telegram_probe=1' if attempt == 0 else ''
            request = urllib.request.Request(LIVE_BASE + '/ops' + suffix, headers={'User-Agent': 'deploy-hf-telegram-health'})
            with opener.open(request, timeout=60 if attempt == 0 else 30) as response:
                body = response.read(2 * 1024 * 1024 + 1)
            if len(body) > 2 * 1024 * 1024:
                raise ValueError('Oversized page')
            summary = telegram_ops_summary(body.decode('utf-8'))
            print('Telegram diagnostics: ' + json.dumps(summary, sort_keys=True), flush=True)
            if attempt < 2:
                time.sleep(35)  # Three observations cover the one-minute worker cadence.
        return True
    except (Exception, SystemExit):
        # Login/network exceptions and HTML can contain secrets, cookies or staff data.
        print('Telegram diagnostics: unavailable (login, response or network check failed).')
        return False

RUNTIME_PY = [
    "app.py", "css_is_engine.py", "storage.py", "tzutil.py", "fix_timezone_history.py",
    "dashboard_insights.py", "dashboard_export.py", "dashboard_docs.py", "report_docs.py",
    "csm_report.py", "auth.py", "request_security.py", "request_reads.py", "browser_security.py", "mailer.py", "backups.py", "retention.py", "monitoring.py",
    "name_cleanup.py", "apply_speakers.py", "harmonize.py", "activity_admin.py",
    "activity_messages.py", "reg_questions.py", "certificate.py", "ratelimit.py", "i18n.py",
    "realtime.py", "short_links.py",
    "appearance.py", "appearance_storage.py", "appearance_routes.py", "companion_wardrobe.py", "companion_leaderboard.py",
    "tours.py", "ui_telemetry.py", "ux_handoff.py", "ai_core.py", "ai_facts.py", "ai_report_drafts.py", "qa_rules.py",
    "wellness_register.py", "work_arrangement_annex.py",
    "work_arrangement_backfill.py", "office_connect.py",
    "calendar_schedule.py",
    "telegram_storage.py", "telegram_changes.py", "telegram_notices.py", "telegram_preferences.py", "telegram_reminders.py", "telegram_preference_routes.py", "telegram_bot.py", "telegram_transport.py", "telegram_links.py", "telegram_link_routes.py", "telegram_groups.py", "telegram_group_routes.py", "telegram_calendar.py", "telegram_rooms.py", "telegram_work.py", "telegram_group_reads.py", "telegram_actions.py", "calendar_actions.py", "telegram_meetings.py", "telegram_meeting_rooms.py", "telegram_meeting_routes.py", "telegram_room_requests.py", "telegram_room_request_routes.py", "room_actions.py",

    "integration_api.py", "integration_operations.py", "integration_access.py", "integration_access_routes.py", "integration_changes.py", "work_reads.py", "search_typo.py",
    "mcp_auth.py", "mcp_read.py", "mcp_actions.py", "mcp_supply_drafts.py", "mcp_comment_drafts.py", "mcp_report_views.py", "mcp_personal_calendar.py", "mcp_travel_drafts.py", "mcp_task_acknowledgements.py", "task_acceptance.py", "mcp_task_acceptances.py", "mcp_task_submissions.py", "supply_approval.py", "mcp_supply_approvals.py", "mcp_supply_submissions.py", "mcp_travel_reviews.py", "mcp_travel_decisions.py", "travel_decision_delivery.py", "mcp_travel_submissions.py", "room_approval.py", "room_approval_delivery.py", "mcp_room_approvals.py", "mcp_room_requests.py", "mcp_meal_requests.py", "mcp_work_arrangements.py", "mcp_activity_dates.py", "mcp_activity_drafts.py", "mcp_activity_creation.py", "activity_announcements.py", "mcp_activity_announcements.py", "activity_creation.py", "activity_creation_delivery.py", "activity_drafts.py", "activity_draft_routes.py", "activity_permissions.py", "activity_scheduling.py", "work_arrangement_delivery.py", "room_request_delivery.py", "travel_review_delivery.py", "travel_drafts.py", "personal_calendar.py", "report_views.py", "survey_reports.py",
    "work_comment_drafts.py",
    "work.py", "work_inbox.py", "work_intake.py", "work_readiness.py", "work_discussion.py", "work_updates.py", "work_digests.py", "work_channels.py", "apprise_transport.py", "work_blockers.py", "work_decisions.py", "work_handoff.py", "work_team.py", "work_support.py", "work_review.py", "work_completion.py", "work_routes.py", "work_compat.py", "work_tasks.py", "work_storage.py",
    "documents.py", "documents_registry.py", "documents_registration.py", "documents_actions.py", "documents_external.py", "documents_jobs.py", "documents_guidance.py", "documents_annotations.py", "documents_file_text.py", "documents_memo.py", "documents_instruction_tags.py", "documents_search.py", "documents_intake.py", "documents_sync.py", "documents_intake_routes.py", "documents_email.py", "documents_gmail_settings.py", "documents_storage.py", "documents_permissions.py", "documents_rules.py", "documents_operations.py", "documents_workspace.py", "documents_notify.py", "documents_routes.py", "documents_calendar.py", "documents_reader.py", "pdf_reader_process.py", "pdf_reader_worker.py", "documents_ocr.py", "bounded_pipes.py", "ocr_process.py", "ocr_worker.py", "ocr_engine.py", "ocr_tesseract.py", "documents_dtrak.py", "documents_page_reader.py",
    "documents_grid.py", "documents_dashboard.py", "dashboard_pdf.py",
    "office_calendar.py", "calendar_routes.py", "calendar_notice.py", "calendar_guidance.py", "activity_docs.py", "activity_invitation.py", "rooms.py", "rooms_guidance.py", "rooms_routes.py", "rooms_notify.py", "travel.py", "travel_guidance.py", "travel_grid.py", "travel_routes.py", "travel_submissions.py", "travel_notify.py", "travel_review.py", "gdocs_relay.py", "meet_relay.py", "travel_rules.py", "travel_checklist.py", "travel_docs.py", "travel_rates.py", "travel_scan.py", "travel_readings.py", "meals.py", "meals_routes.py", "rooms_meals.py", "rooms_meals_routes.py", "room_meal_form.py", "calendar_import.py", "calendar_import_apply.py", "calendar_import_suggest.py", "calendar_people.py", "birthdays.py", "birthday_cards.py", "calendar_ics.py", "recurrence.py", "calendar_answers.py", "search_sources.py", "office_answers.py",
    "supplies.py", "supplies_storage.py", "supplies_permissions.py", "supplies_stock.py", "supplies_grid.py", "supplies_stock_dashboard.py",
    "supplies_import.py", "supplies_import_review.py", "supplies_requests.py", "supplies_shop.py", "supplies_pictures.py", "supplies_approvals.py",
    "supplies_allocations.py", "supplies_backorders.py", "supplies_issues.py", "supplies_acknowledgments.py",
    "supplies_print.py", "supplies_corrections.py", "supplies_notify.py", "supplies_mail.py", "supplies_dashboard.py", "supplies_status.py",
    "supplies_replenishment.py", "supplies_replenishment_flow.py", "supplies_deliveries.py",
    "supplies_reports.py", "supplies_routes.py",
    # Imported by app.py for the daily reminder sweep the scheduler loop fires.
    "send_reminders.py", "email_params.py",
]
ALLOW = RUNTIME_PY + [
    "version.py",            # drives the login version string
    "css_is.db",             # the live DB carrier
    "build_info.json",       # build telemetry for the /ops admin dashboard
    "Dockerfile", ".dockerignore", "requirements.txt", "README.md",
    "templates/**", "static/**", "assets/**",
]
IGNORE = ["**/__pycache__/**"]

AUTO_YES = "--yes" in sys.argv or "-y" in sys.argv


def _response_count(path):
    try:
        c = sqlite3.connect(path)
        n = c.execute("SELECT COUNT(*) FROM response").fetchone()[0]
        c.close()
        return n
    except Exception:
        return "?"


def _confirm(prompt):
    """One Y/n confirm. Auto-yes when --yes or stdin isn't a TTY (backgrounded)."""
    if AUTO_YES or not sys.stdin.isatty():
        print(f"{prompt} [auto-yes]")
        return True
    return (input(f"{prompt} [Y/n] ").strip().lower() or "y") == "y"


def pull_live_db():
    """Swap in the newest live DB the user downloaded to ~/Downloads (the 'pull' step)."""
    downloads = os.path.expanduser("~/Downloads")
    cands = sorted(glob.glob(os.path.join(downloads, "css_is_*.db")),
                   key=os.path.getmtime, reverse=True)
    if not cands:
        print(f"ℹ️  No css_is_*.db found in {downloads} — shipping the current local "
              f"{LOCAL_DB} as-is ({_response_count(LOCAL_DB)} responses).")
        return
    newest = cands[0]
    cur_m = os.path.getmtime(LOCAL_DB) if os.path.exists(LOCAL_DB) else 0
    new_m = os.path.getmtime(newest)
    fmt = lambda t: time.strftime("%Y-%m-%d %H:%M", time.localtime(t)) if t else "—"
    print("Pulling the live DB:")
    print(f"  downloaded : {os.path.basename(newest)}  ({fmt(new_m)}, "
          f"{_response_count(newest)} responses)")
    print(f"  local now  : {LOCAL_DB}  ({fmt(cur_m)}, {_response_count(LOCAL_DB)} responses)")
    if new_m <= cur_m:
        print("  → local DB is already at least as new; NOT swapping.")
        return
    if not _confirm("  → Swap the downloaded live DB into css_is.db before deploying?"):
        print("  → keeping the current local DB.")
        return
    if os.path.exists(LOCAL_DB):
        os.makedirs("_backups", exist_ok=True)
        bak = os.path.join("_backups", f"css_is_{time.strftime('%Y%m%d_%H%M%S')}_predeploy.db")
        shutil.copy2(LOCAL_DB, bak)
    shutil.copy2(newest, LOCAL_DB)
    print(f"  ✅ swapped in {os.path.basename(newest)} ({_response_count(LOCAL_DB)} responses).")


def _fetch_live_login():
    # Retried: the hosting edge can 5xx a request the app never saw (it
    # aborted two deploys in July 2026); a plain GET is always safe to re-send.
    req = urllib.request.Request(f"{LIVE_BASE}/login", headers={"User-Agent": "deploy_hf"})
    last = None
    for attempt in range(5):
        if attempt:
            time.sleep(2.0 * attempt)
        try:
            return urllib.request.urlopen(req, timeout=30).read().decode("utf-8", "ignore")
        except (urllib.error.HTTPError, urllib.error.URLError) as e:
            last = e
    raise last


def _load_env_local():
    """Read KEY=VALUE lines from a gitignored .env.local next to this script (for
    CSS_ADMIN_USER / CSS_ADMIN_PASS / CSS_BASE_URL). Env vars still win. Missing -> {}."""
    path = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env.local")
    out = {}
    try:
        with open(path, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    k, v = line.split("=", 1)
                    out[k.strip()] = v.strip()
    except OSError:
        return {}
    return out


def secure_predeploy_backup():
    """REDUNDANT-BACKUP GATE — run BEFORE the upload that restarts the Space.

    A deploy restarts the live Space, and boot-restore loads the newest BUCKET
    snapshot. If the running container holds writes that were never snapshotted,
    that restart silently discards them (this is exactly how the 2026-06-25 revert
    lost ~1.5 days of data). So before shipping we FORCE a fresh, verified snapshot
    of current live state and ABORT if we can't secure one — never restart blind.

    Triggers the app's own 'Back up now' (admin-authenticated), confirms a NEW
    snapshot actually appeared on the bucket, then downloads + integrity-checks a
    local copy. Needs admin creds (env or .env.local). Override with --skip-backup
    or CSS_DEPLOY_SKIP_BACKUP=1 only when you knowingly accept the risk."""
    if "--skip-backup" in sys.argv or os.environ.get("CSS_DEPLOY_SKIP_BACKUP") == "1":
        print("⚠️  Pre-deploy backup SKIPPED (--skip-backup / CSS_DEPLOY_SKIP_BACKUP=1). "
              "A restart could discard any un-snapshotted live writes.\n")
        return
    try:
        import pull_backup as pb
    except Exception as e:
        sys.exit(f"ABORT — can't import pull_backup for the pre-deploy backup ({e}). "
                 "Fix it or re-run with --skip-backup if you accept the risk.")
    fenv = _load_env_local()
    base = (os.environ.get("CSS_BASE_URL") or fenv.get("CSS_BASE_URL") or LIVE_BASE).rstrip("/")
    user = os.environ.get("CSS_ADMIN_USER") or fenv.get("CSS_ADMIN_USER")
    pwd = os.environ.get("CSS_ADMIN_PASS") or fenv.get("CSS_ADMIN_PASS")
    if not (user and pwd):
        sys.exit("ABORT — pre-deploy backup needs admin creds (CSS_ADMIN_USER / "
                 "CSS_ADMIN_PASS in env or .env.local). Set them, or re-run with "
                 "--skip-backup to deploy without securing a fresh backup.")
    print("Securing a fresh live backup before deploying (redundant-backup gate):")
    try:
        opener, _ = pb._opener()
        pb.login(opener, base, user, pwd)
        before = pb.list_snapshots(opener, base)
        newest_before = before[0] if before else None
        name = pb.make_fresh(opener, base)
        if not name:
            after = pb.list_snapshots(opener, base)
            name = after[0] if after else None
        if not name or name == newest_before:
            sys.exit("ABORT — could not confirm a NEW live snapshot was written. The "
                     "bucket snapshotter may be failing; do NOT restart the Space until "
                     "this is resolved (that is the data-loss condition). "
                     "Re-run with --skip-backup only if you accept the risk.")
        out_dir = os.path.join("_backups", "pulled")
        dst = pb.download(opener, base, name, out_dir)
        info = pb.verify(dst)   # raises SystemExit if the file is corrupt
        print(f"  ✅ fresh live snapshot secured + verified: {name} ({info})")
        print(f"     local copy: {dst}\n")
        print('Telegram pre-deploy queue totals: ' + json.dumps(telegram_snapshot_summary(dst), sort_keys=True))
    except SystemExit:
        raise
    except Exception as e:
        sys.exit(f"ABORT — pre-deploy backup FAILED ({e!r}). A restart could lose "
                 "un-snapshotted live data; resolve this or re-run with --skip-backup.")


def _git_commit():
    """Full commit SHA of the checkout being shipped, or None outside a git repo
    (e.g. a stripped-down CI checkout)."""
    try:
        return subprocess.check_output(
            ["git", "rev-parse", "HEAD"],
            cwd=os.path.dirname(os.path.abspath(__file__)),
            stderr=subprocess.DEVNULL, timeout=10,
        ).decode().strip()
    except Exception:
        return None


def write_build_info(version, deployed_by):
    """Stamp build_info.json with what THIS deploy is shipping — version, commit,
    who ran it, and when — so the live /ops admin dashboard can show which build
    is actually running. Written just before upload_folder (with build_info.json
    in ALLOW) so the file ships as part of the same bundle it describes."""
    import tzutil as tz
    commit = _git_commit()
    info = {
        "version": version,
        "commit": commit,
        "commit_short": commit[:7] if commit else None,
        "deployed_at": tz.now_local().isoformat(timespec="seconds"),
        "deployed_by": deployed_by,
    }
    with open("build_info.json", "w", encoding="utf-8") as f:
        json.dump(info, f, indent=2)
    print(f"  build_info.json → v{version} @ {info['commit_short'] or 'unknown commit'} "
          f"(deployed_by={deployed_by})")


def guard_version_bump(want):
    """Abort if the live site already shows this version (forgot to bump APP_VERSION)."""
    try:
        html = _fetch_live_login()
    except Exception as e:
        print(f"ℹ️  Could not pre-check live version ({e}); proceeding.")
        return
    if want in html:
        # CI/mobile deploys run non-interactively, where _confirm auto-yeses and
        # would silently ship without a version bump — violating the standing rule
        # that every deploy bumps APP_VERSION. In strict mode (set by the GitHub
        # Action) a stale version is a hard abort instead.
        if os.environ.get("CSS_DEPLOY_STRICT_VERSION") == "1":
            sys.exit(f"ABORT — the live site already shows v{want}. Bump APP_VERSION in "
                     "version.py and add a CHANGELOG entry before deploying (strict mode).")
        print(f"\n⚠️  The live site ALREADY shows v{want} — looks like APP_VERSION wasn't "
              f"bumped for this deploy. Bump version.py + add a CHANGELOG line first.")
        if not _confirm("  Deploy anyway (e.g. you only changed the DB/assets)?"):
            sys.exit("ABORT — bump the version, then re-run.")


def _unshipped_local_imports(allow):
    """Guard against the v2.39 wellness_register.py class of bug: a module that a
    SHIPPED file imports at boot, but which itself was never added to the deploy
    allowlist — so the Space boots straight into ModuleNotFoundError.

    Parses every shipped .py, collects its TOP-LEVEL imports (lazy imports inside
    functions don't run at boot, so they can't wedge startup), and reports any that
    resolve to a repo-local module not itself shipped. Returns [(module, imported_by)]."""
    import ast
    local_mods = {f[:-3] for f in os.listdir(".") if f.endswith(".py")}
    shipped = {f[:-3] for f in allow if f.endswith(".py")}
    offenders = []
    for mod in sorted(shipped):
        path = mod + ".py"
        if not os.path.exists(path):
            continue
        try:
            tree = ast.parse(open(path, encoding="utf-8").read(), path)
        except Exception:
            continue
        names = set()
        for node in tree.body:  # module scope only
            if isinstance(node, ast.Import):
                names |= {a.name.split(".")[0] for a in node.names}
            elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
                names.add(node.module.split(".")[0])
        for n in sorted(names):
            if n in local_mods and n not in shipped:
                offenders.append((n, mod))
    return offenders


def main():
    from huggingface_hub import HfApi
    import version

    api = HfApi()
    print(f"Authenticated as: {api.whoami().get('name')}\n")

    # Once the Space runs on bucket-backed persistence (CSS_PERSIST_DIR set), the
    # live DB lives on the mounted bucket — NOT in this repo. The repo css_is.db
    # is only a first-boot seed, so the old "pull the live DB and ship it as the
    # carrier" step is retired: shipping a DB can no longer move live data, and
    # pulling one risks reintroducing the very confusion that lost data before.
    persist_on = False
    try:
        persist_on = "CSS_PERSIST_DIR" in api.get_space_variables(REPO_ID)
    except Exception as e:
        print(f"ℹ️  Could not read Space variables ({e}); assuming legacy carrier mode.")
    # When persistence is active the repo css_is.db is a frozen seed that the
    # Space IGNORES on every boot (the bucket is the source of truth). Re-uploading
    # the 21.6 MB blob on every deploy is pointless AND committing it routinely
    # stalls the upload for many minutes — so ship code only and skip it. The seed
    # already on the Space from earlier deploys stays in place, untouched.
    allow = list(ALLOW)
    if persist_on:
        allow = [f for f in allow if f != LOCAL_DB]
        print("Persistence is ACTIVE (CSS_PERSIST_DIR set): the live DB lives on the "
              "bucket; shipping code only — skipping the frozen css_is.db seed.\n")
    else:
        pull_live_db()

    want = version.APP_VERSION
    deployed_by = os.environ.get("GITHUB_ACTOR") or api.whoami().get("name") or "unknown"
    write_build_info(want, deployed_by)   # stamps build_info.json — must run BEFORE
                                          # the missing-files check below, since
                                          # build_info.json is in ALLOW and doesn't
                                          # exist on disk until this call creates it.

    missing = [f for f in allow if "*" not in f and not os.path.exists(f)]
    if missing:
        sys.exit(f"ABORT — missing files: {missing}")

    unshipped = _unshipped_local_imports(allow)
    if unshipped:
        detail = "; ".join(f"{m} (imported by {by}.py)" for m, by in unshipped)
        sys.exit(f"ABORT — these local modules are imported at boot but are NOT in the "
                 f"deploy allowlist, so the Space would crash with ModuleNotFoundError. "
                 f"Add them to RUNTIME_PY: {detail}")

    guard_version_bump(want)

    if LOCAL_DB in allow:
        db_mb = os.path.getsize(LOCAL_DB) / 1e6
        print(f"\nShipping v{want} with css_is.db ({db_mb:.1f} MB, "
              f"{_response_count(LOCAL_DB)} responses).")
    else:
        print(f"\nShipping v{want} (code only).")

    # Under persistence a deploy RESTARTS the Space and boot-restore loads the
    # newest bucket snapshot — so secure a fresh, verified one FIRST or abort.
    if persist_on:
        secure_predeploy_backup()

    res = api.upload_folder(
        folder_path=".", repo_id=REPO_ID, repo_type="space",
        allow_patterns=allow, ignore_patterns=IGNORE,
        commit_message=f"Deploy v{want}",
    )
    print(f"Uploaded. Space commit: {getattr(res, 'oid', res)}")

    print("Waiting for the Space to rebuild...")
    last = None
    for _ in range(120):  # up to ~10 min
        stage = api.get_space_runtime(REPO_ID).stage
        if stage != last:
            print(f"  stage = {stage}")
            last = stage
        if stage == "RUNNING":
            break
        if stage in ("BUILD_ERROR", "RUNTIME_ERROR", "CONFIG_ERROR"):
            sys.exit(f"ABORT — Space entered {stage}; check the Space logs.")
        time.sleep(5)

    try:
        ok = want in _fetch_live_login()
        print(f"\nLive /login version check: {'OK' if ok else 'MISMATCH'} (expected v{want})")
        if not ok:
            sys.exit("ABORT — live page does not show the expected version yet.")
    except Exception as e:
        print(f"\nCould not verify /login automatically ({e}); check {LIVE_BASE}/login.")
        return

    print(f"\n✅ Deployed v{want} → {LIVE_BASE}")


if __name__ == "__main__":
    main()
