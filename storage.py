"""
Office Connect storage
==============

The part that REMEMBERS. A single database file on your laptop that holds:

  - the org directory      (bureau -> divisions -> sections)
  - the resource-person registry (internal staff and external guests)
  - external organizers    (bodies that run events you were invited to)
  - form instances         (one per QR code: the RP, topic, organizer, date are
                            bound here at creation, NOT typed by the rater)
  - responses              (one per person who answered)
  - answers                (THE ATOMS: one row per rating -- the only ground truth)

It uses SQLite, which is built into Python (nothing to install) and keeps the
whole database in one file you can copy or back up.

The important function is load_atoms(): it stitches everything together into the
exact table the calculator (css_is_engine) already knows how to read. Storage
and calculator stay cleanly separated -- storage remembers, the engine computes.
"""

from __future__ import annotations
import hashlib
import json
import sqlite3
import uuid
import re
import difflib
from datetime import datetime, timedelta, date, time
import pandas as pd
import css_is_engine as eng
import tzutil as tz  # local (PH) wall-clock — never stamp with the server clock


# ---------------------------------------------------------------------
# Open / create the database
# ---------------------------------------------------------------------

def connect(db_path="css_is.db"):
    conn = sqlite3.connect(db_path)
    conn.execute("PRAGMA foreign_keys = ON")
    # WAL: readers never block the single writer (and vice-versa), so a long
    # atoms rebuild or a live survey-submission write no longer stalls every
    # other request. journal_mode is persistent (a no-op once the DB is WAL);
    # synchronous/busy_timeout are per-connection and set each time.
    # Backup-safe: backups.py uses the SQLite online-backup API (captures WAL
    # pages), not a raw file copy. (:memory: silently stays in memory mode.)
    conn.execute("PRAGMA journal_mode = WAL")
    conn.execute("PRAGMA synchronous = NORMAL")
    conn.execute("PRAGMA busy_timeout = 5000")
    return conn


def init_db(conn):
    """Create all the tables (safe to run again -- it won't duplicate)."""
    conn.executescript("""
    CREATE TABLE IF NOT EXISTS org_unit (
        id         INTEGER PRIMARY KEY,
        name       TEXT NOT NULL,         -- official long name
        short_name TEXT,                  -- abbreviation used in path + compact UI
        level      TEXT NOT NULL,         -- 'bureau' / 'division' / 'section'
        path       TEXT NOT NULL UNIQUE   -- e.g. 'BLHSD/HSMED/Equity' (used for rollups)
    );

    CREATE TABLE IF NOT EXISTS resource_person (
        id          INTEGER PRIMARY KEY,
        honorific   TEXT,               -- standardized title: Mr./Ms./Mrs./Dr./Engr./Atty. (NULL = none)
        agency      TEXT,               -- external speaker's office/agency/affiliation
        name        TEXT NOT NULL,
        is_internal INTEGER NOT NULL,   -- 1 = bureau staff, 0 = external guest
        org_unit_id INTEGER REFERENCES org_unit(id),  -- set only if internal
        photo       BLOB,               -- profile picture bytes (kept in the one db file)
        photo_mime  TEXT,               -- e.g. 'image/jpeg'
        -- HR detail (internal staff):
        position        TEXT,           -- plantilla / official position title
        designation     TEXT,           -- functional role (e.g. Section Head, OIC)
        focus_area      TEXT,           -- programme / area of responsibility
        email           TEXT,
        employment_type TEXT,           -- 'plantilla' / 'job_order' / 'consultant'
        hidden_public   INTEGER NOT NULL DEFAULT 0, -- 1 = admin hid this person's scores from the public People view
        archived_at     TEXT,           -- resigned/transferred out: NULL = current, a timestamp = archived
        archived_reason TEXT            -- free-text note kept with the archive ('Resigned 31 Jul 2026')
    );

    CREATE TABLE IF NOT EXISTS external_organizer (
        id   INTEGER PRIMARY KEY,
        name TEXT NOT NULL UNIQUE       -- the thin registry, so one body = one entry
    );

    CREATE TABLE IF NOT EXISTS form_instance (
        id           INTEGER PRIMARY KEY,
        survey_type  INTEGER NOT NULL,  -- 1 ARTA / 2 Activity / 3 Resource-person
        form         TEXT NOT NULL,     -- 'F1' / 'F2' / 'F3'
        qr_token     TEXT NOT NULL UNIQUE,
        event_date   TEXT NOT NULL,     -- 'YYYY-MM-DD' (the event/transaction START date; sets the reporting period)
        end_date     TEXT,              -- 'YYYY-MM-DD' end of a multi-day activity; NULL = single-day (= event_date)
        venue        TEXT,              -- where it was held / online platform link (display only; the engine ignores it)
        modality     TEXT,              -- 'f2f' | 'online' (NULL = face-to-face); online => venue holds the platform link
        -- context bound at creation by the section manager:
        serving_staff        TEXT,                 -- T1: who served
        serving_staff_org_id INTEGER REFERENCES org_unit(id),  -- T1
        service              TEXT,                  -- T1
        lead_org_id          INTEGER REFERENCES org_unit(id),  -- T2 lead unit / T3 internal organizer
        rp_id                INTEGER REFERENCES resource_person(id),  -- T3
        topic                TEXT,                  -- T2 activity name / T3 topic
        organizer_external_id INTEGER REFERENCES external_organizer(id),  -- T3 external; NULL => internal
        created_at           TEXT,
        -- Response window ("allowed time to entry"). NULL on either side means
        -- no bound on that side; both NULL = always open (all pre-existing forms).
        open_at              TEXT,                  -- ISO 'YYYY-MM-DDTHH:MM'
        close_at             TEXT
    );

    CREATE TABLE IF NOT EXISTS response (
        id               INTEGER PRIMARY KEY,
        form_instance_id INTEGER NOT NULL REFERENCES form_instance(id),
        submitted_at     TEXT,
        remarks          TEXT,            -- one overall free-text comment (the verbatim)
        served_by_rp_id  INTEGER REFERENCES resource_person(id)  -- walk-in: who the client says served them
    );

    CREATE TABLE IF NOT EXISTS answer (          -- THE ATOMS
        id          INTEGER PRIMARY KEY,
        response_id INTEGER NOT NULL REFERENCES response(id),
        item_id     TEXT NOT NULL,               -- 'SQD1','B6','A','C', ...
        value       REAL,                        -- the rating; NULL means N/A
        is_na       INTEGER NOT NULL DEFAULT 0   -- 1 = the person marked N/A
    );

    CREATE TABLE IF NOT EXISTS item_remark (     -- optional note tied to one item
        id          INTEGER PRIMARY KEY,
        response_id INTEGER NOT NULL REFERENCES response(id),
        item_id     TEXT NOT NULL,               -- which item the note is about
        text        TEXT NOT NULL
    );

    CREATE TABLE IF NOT EXISTS comment_override ( -- manual appreciate/improve re-tag of a verbatim
        response_id INTEGER NOT NULL REFERENCES response(id),
        item_id     TEXT NOT NULL DEFAULT '',     -- '' = the overall remark; else the item note's item_id
        tag         TEXT NOT NULL,                -- 'appreciate' | 'improve' — the user's correction
        actor       TEXT,                         -- who set it
        set_at      TEXT,                         -- ISO timestamp
        PRIMARY KEY (response_id, item_id)
    );

    CREATE TABLE IF NOT EXISTS audit_log (       -- append-only: who did what, when
        id          INTEGER PRIMARY KEY,
        ts          TEXT NOT NULL,               -- ISO timestamp
        actor       TEXT NOT NULL,               -- username (email) of the signed-in user
        action      TEXT NOT NULL,               -- 'edit_remark' / 'hide_person' / 'export' / ...
        target_type TEXT,                        -- 'response' / 'person' / 'user' / 'event' / 'visual'
        target_id   TEXT,
        summary     TEXT,                        -- one human-readable line
        before_text TEXT,                        -- old value (for edits)
        after_text  TEXT,                        -- new value (for edits)
        ip          TEXT,
        prev_hash   TEXT NOT NULL,               -- hash chain: this row commits to the one before it
        row_hash    TEXT NOT NULL
    );

    -- An EVENT is a persistent grouping of the form_instances created together
    -- (one F2 event review + N F3 speaker reviews). It powers the public
    -- "link tree" landing page at /e/<event_token> that bundles every rating
    -- link for the event and gates them behind attendee identity + consent.
    CREATE TABLE IF NOT EXISTS event (
        id           INTEGER PRIMARY KEY,
        event_token  TEXT NOT NULL UNIQUE,  -- public link-tree slug (/e/<token>)
        title        TEXT NOT NULL,         -- activity name
        event_date   TEXT NOT NULL,         -- START date (reporting period keys off this)
        end_date     TEXT,                  -- end of a multi-day activity; NULL = single-day
        venue        TEXT,                  -- venue, or online platform link when modality='online'
        modality     TEXT,                  -- 'f2f' | 'online' (NULL = face-to-face)
        organizer    TEXT,                  -- display label (internal section / external body)
        lead_org_id  INTEGER REFERENCES org_unit(id),
        created_at   TEXT
    );

    CREATE TABLE IF NOT EXISTS event_form (  -- which forms belong to an event, in order
        event_id         INTEGER NOT NULL REFERENCES event(id),
        form_instance_id INTEGER NOT NULL REFERENCES form_instance(id),
        ordinal          INTEGER NOT NULL DEFAULT 0,
        PRIMARY KEY (event_id, form_instance_id)
    );

    -- Attendee identity + CONSENT, captured once per event before rating.
    -- Capturing PII turns anonymous feedback into personal data (PH Data Privacy
    -- Act), so a consent record is mandatory and the PII fields are purged after
    -- a retention period (see retention.py) — the row survives as a consent
    -- record while name/email/contact are nulled. Ratings themselves stay in the
    -- response/answer tables and remain analytically anonymous (load_atoms never
    -- reads identity), so purging identity never loses a single rating.
    CREATE TABLE IF NOT EXISTS attendee (
        id           INTEGER PRIMARY KEY,
        event_id     INTEGER NOT NULL REFERENCES event(id),
        name         TEXT,                  -- PII — nulled on retention purge
        email        TEXT,                  -- PII — nulled on retention purge
        contact      TEXT,                  -- PII (optional) — nulled on retention purge
        consent_at   TEXT NOT NULL,         -- when the attendee gave consent
        consent_text TEXT NOT NULL,         -- snapshot of the privacy notice they agreed to
        ip           TEXT,
        created_at   TEXT,
        purged_at    TEXT                   -- set when the PII fields were purged
    );
    -- Lookup index for dedup-aware registration (resume by email per event).
    -- Deliberately NON-unique: any pre-existing duplicate rows must not block
    -- index creation — duplicates are prevented going forward in register_attendee.
    CREATE INDEX IF NOT EXISTS idx_attendee_event_email ON attendee(event_id, email);

    -- Hot-path join/filter indexes for the aggregate stats (home strip, dashboard,
    -- reports). Without these, every windowed metric does a full SCAN of answer
    -- (hundreds of K rows) even when it only needs the last 30 days. idx_answer_response
    -- drives the answer->response join; idx_response_submitted lets windowed queries
    -- start from the date filter instead of scanning everything; idx_response_form_instance
    -- speeds response->form_instance. All cut cold-start home_stats roughly in half.
    CREATE INDEX IF NOT EXISTS idx_answer_response        ON answer(response_id);
    CREATE INDEX IF NOT EXISTS idx_response_submitted     ON response(submitted_at);
    CREATE INDEX IF NOT EXISTS idx_response_form_instance ON response(form_instance_id);

    CREATE TABLE IF NOT EXISTS admin_user (      -- staff accounts that log in (RBAC)
        id          INTEGER PRIMARY KEY,
        username    TEXT NOT NULL UNIQUE,        -- the login id; for staff this is their EMAIL
        pw_hash     TEXT NOT NULL,               -- pbkdf2-hmac hex; '' = pending (not set yet)
        salt        TEXT NOT NULL,               -- '' while pending
        role        TEXT NOT NULL,               -- viewer / encoder / section_manager / admin
        active      INTEGER NOT NULL DEFAULT 1,  -- 0 = pending invite OR deactivated
        must_change INTEGER NOT NULL DEFAULT 0,  -- 1 = temp password, force a reset on next sign-in
        rp_id       INTEGER REFERENCES resource_person(id),  -- the directory staff this account belongs to
        created_at  TEXT,
        created_by  TEXT,                        -- username of the admin/process that made it
        bureau_access TEXT NOT NULL DEFAULT ''   -- '' / 'awa' / 'all' (BUREAU_ACCESS_LEVELS)
    );

    CREATE TABLE IF NOT EXISTS app_setting (     -- small key/value store for app config
        key   TEXT PRIMARY KEY,                  -- e.g. 'backup_enabled', 'backup_freq'
        value TEXT
    );
    """)
    # --- Wellness module (DOH DM 2025-0135: the 2-hour weekly wellness break) ---
    conn.executescript("""
    CREATE TABLE IF NOT EXISTS wellness_claim (  -- one row per requested 1-hour break
        id          INTEGER PRIMARY KEY,
        user_id     INTEGER NOT NULL REFERENCES admin_user(id),
        week_start  TEXT NOT NULL,               -- Monday of the break's week 'YYYY-MM-DD' (entitlement key)
        break_date  TEXT NOT NULL,               -- 'YYYY-MM-DD'
        start_time  TEXT NOT NULL,               -- 'HH:MM' (24h)
        hours       INTEGER NOT NULL DEFAULT 1,  -- always 1: the DM's 2 h/week is claimed in 1-h slots
        activity    TEXT NOT NULL,               -- key into WELLNESS_ACTIVITIES (the DM's allowed list)
        activity_other TEXT,                     -- when activity='other': what the person specified
        note        TEXT,
        status      TEXT NOT NULL DEFAULT 'pending',  -- pending/approved/denied/cancelled/completed
        decided_by  INTEGER REFERENCES admin_user(id),
        decided_at  TEXT,
        decide_note TEXT,                        -- approver's remark (e.g. reason for denial)
        created_at  TEXT
    );
    CREATE INDEX IF NOT EXISTS idx_wellness_claim_user_week ON wellness_claim(user_id, week_start);
    CREATE INDEX IF NOT EXISTS idx_wellness_claim_status    ON wellness_claim(status);

    CREATE TABLE IF NOT EXISTS wellness_reflection (  -- post-break check-in, one per claim
        id            INTEGER PRIMARY KEY,
        claim_id      INTEGER NOT NULL UNIQUE REFERENCES wellness_claim(id),
        mood_before   INTEGER,                   -- 1-5 before the break
        mood_after    INTEGER,                   -- 1-5 after
        activity_done TEXT,                      -- what they actually did
        takeaway      TEXT,                      -- one thing they're taking from it
        usefulness    INTEGER,                   -- 1-5 how useful the break was (Annex A scale)
        felt_refreshed INTEGER,                  -- 0/1: did it help you feel refreshed/energized?
        managed_stress INTEGER,                  -- 0/1: did it help you manage stress/anxiety?
        focus_impact  TEXT,                      -- 'improved' | 'no_change' | 'worsened'
        suggestions   TEXT,                      -- ideas for improving the program (optional)
        submitted_at  TEXT
    );

    CREATE TABLE IF NOT EXISTS wellness_badge (  -- persisted awards (points/streaks are derived)
        id         INTEGER PRIMARY KEY,
        user_id    INTEGER NOT NULL REFERENCES admin_user(id),
        badge      TEXT NOT NULL,                -- key into WELLNESS_BADGES
        awarded_at TEXT,
        UNIQUE(user_id, badge)
    );
    """)
    # --- Work arrangement module (ANNEX C: the semi-monthly internal work
    # arrangement schedule — who is on-site, compressed, or working from home) ---
    conn.executescript("""
    CREATE TABLE IF NOT EXISTS work_arrangement (  -- one live row per person per half-month
        id           INTEGER PRIMARY KEY,
        user_id      INTEGER NOT NULL REFERENCES admin_user(id),
        period_start TEXT NOT NULL,               -- 'YYYY-MM-01' or 'YYYY-MM-16' (the period key)
        arrangement  TEXT NOT NULL,               -- 'REG' | 'CWW' | 'WFH' (WORK_ARRANGEMENT_TYPES)
        weekday      INTEGER,                     -- 0=Mon..4=Fri; NULL for REG (no day applies).
                                                  -- CWW: the day OFF. WFH: the day worked remotely.
                                                  -- The nominated day recurs every week of the
                                                  -- period, exactly as the paper form reads.
        note         TEXT,                        -- the requester's own reason, if any
        status       TEXT NOT NULL DEFAULT 'pending',  -- see WORK_ARRANGEMENT_STATUSES
        -- Set when this row is a staff-initiated CHANGE to an already-approved
        -- arrangement: the id of the row it replaces. The old row stays 'approved'
        -- (it is still the schedule in force) until this one is approved, at which
        -- point it flips to 'superseded'. NULL on an original filing.
        supersedes_id INTEGER REFERENCES work_arrangement(id),
        decided_by   INTEGER REFERENCES admin_user(id),
        decided_at   TEXT,
        decide_note  TEXT,                        -- approver's remark (e.g. reason for denial)
        created_at   TEXT
    );
    -- Two partial constraints, not one: a person may hold at most one APPROVED
    -- arrangement per period AND at most one PENDING row against it (the change
    -- request), which is exactly "one schedule in force plus one change in
    -- flight". Denied/cancelled/superseded rows stay as the audit trail and fall
    -- outside both, so re-filing after a denial still works.
    CREATE UNIQUE INDEX IF NOT EXISTS ux_work_arrangement_approved
        ON work_arrangement(user_id, period_start) WHERE status = 'approved';
    CREATE UNIQUE INDEX IF NOT EXISTS ux_work_arrangement_pending
        ON work_arrangement(user_id, period_start) WHERE status = 'pending';
    CREATE INDEX IF NOT EXISTS idx_work_arrangement_period
        ON work_arrangement(period_start, status);

    -- "No AWA" — a standing statement that someone has NO alternative work
    -- arrangement, and why: on leave, awaiting a decision from OSEC, and so on.
    -- Unlike a filed arrangement this is not per-period and not approved. It
    -- simply holds from the period it starts in until someone ends it, which is
    -- what lets it cover a situation arising mid-period, after filing closed —
    -- the one case the Friday deadline otherwise had no answer for.
    CREATE TABLE IF NOT EXISTS work_arrangement_noawa (
        id             INTEGER PRIMARY KEY,
        user_id        INTEGER NOT NULL REFERENCES admin_user(id),
        remark         TEXT NOT NULL,      -- free text: why there is no arrangement
        effective_from TEXT NOT NULL,      -- period_start it begins in
        effective_to   TEXT,               -- period_start it stops applying FROM;
                                           -- NULL = still in force. An interval
                                           -- spans every period between its ends,
                                           -- so carry-over needs nothing to run
                                           -- at a period boundary.
        created_by     INTEGER REFERENCES admin_user(id),   -- the person, or an admin
        created_at     TEXT,
        ended_by       INTEGER REFERENCES admin_user(id),
        ended_at       TEXT
    );
    CREATE INDEX IF NOT EXISTS idx_wa_noawa_user
        ON work_arrangement_noawa(user_id, effective_from);
    -- At most one tag in force per person, the same partial-index trick the
    -- arrangement table uses: closed intervals fall outside it, so the history
    -- of past reasons accumulates instead of being overwritten.
    CREATE UNIQUE INDEX IF NOT EXISTS ux_wa_noawa_live
        ON work_arrangement_noawa(user_id) WHERE effective_to IS NULL;

    -- An admin's temporary exception to the Friday filing deadline: reopens
    -- one period for everyone, so people can file or change their own
    -- arrangement for it past the normal cutoff. One row per period; closing
    -- it again deletes the row rather than leaving an "off" one lying around.
    CREATE TABLE IF NOT EXISTS work_arrangement_reopen (
        period_start TEXT PRIMARY KEY,
        reopened_by  INTEGER REFERENCES admin_user(id),
        reopened_at  TEXT,
        note         TEXT                  -- admin's reason, shown to filers
    );
    """)
    _add_missing_columns(conn)
    _wa_install_week_guard(conn)
    conn.commit()


# --- the "one AWA day a week" guard, in SQL ---------------------------------
#
# A nominated weekday recurs every week of its period, so a filing occupies a
# RANGE of calendar weeks. Two filings clash when those ranges overlap. Within
# one period ux_work_arrangement_approved/_pending already allow only a single
# filing, so the only clash left is ACROSS periods — and it is a real one,
# because a half-month boundary cuts through the middle of a working week:
# Monday the 14th belongs to the 1st-15th period while Wednesday the 16th
# belongs to the 16th-30th one, yet both fall in the same Mon-Fri week.
#
# Since periods never overlap, the later filing's FIRST week is the only one
# that can meet the earlier filing's LAST week — so comparing just the two ends
# of each range decides it exactly, with no need to enumerate the weeks between.
#
# Both ends are GENERATED columns rather than stored ones: derived from
# period_start and weekday on every read, they cannot drift out of step with the
# filing the way a cached copy could — the same reasoning as _wa_remarks.

# Monday of the week holding the FIRST occurrence of `weekday` in the period:
# step forward from period_start to that weekday, then back to its Monday.
_WA_WEEK_HEAD_SQL = (
    "date(date(period_start, '+' || "
    "((weekday - (CAST(strftime('%w', period_start) AS INTEGER) + 6) % 7 + 7) % 7)"
    " || ' days'), '-' || weekday || ' days')")

# The period's last day: the 15th, or whatever the month's real end is.
_WA_PERIOD_END_SQL = (
    "CASE WHEN substr(period_start, 9, 2) = '01' "
    "THEN date(period_start, '+14 days') "
    "ELSE date(period_start, 'start of month', '+1 month', '-1 day') END")

# Monday of the week holding the LAST occurrence: step back from the period's
# end to that weekday, then back to its Monday.
_WA_WEEK_TAIL_SQL = (
    f"date(date({_WA_PERIOD_END_SQL}, '-' || "
    f"(((CAST(strftime('%w', {_WA_PERIOD_END_SQL}) AS INTEGER) + 6) % 7"
    " - weekday + 7) % 7) || ' days'), '-' || weekday || ' days')")

# The refusal a person should never see: create_work_arrangement and
# decide_work_arrangement both check first and raise something explanatory. This
# is the backstop for any path that does not.
_WA_WEEK_GUARD_BODY = """
      SELECT RAISE(ABORT,
                   'work_arrangement: one alternative work arrangement per week')
       WHERE EXISTS (
             SELECT 1 FROM work_arrangement w
              WHERE w.user_id = NEW.user_id
                AND w.status IN ('pending', 'approved')
                AND w.weekday IS NOT NULL
                -- Same period is the other indexes' business, and a change
                -- request legitimately sits alongside the row it replaces.
                AND w.period_start <> NEW.period_start
                AND w.id <> NEW.id
                AND (w.week_head IN (NEW.week_head, NEW.week_tail)
                  OR w.week_tail IN (NEW.week_head, NEW.week_tail)));
"""


def _wa_install_week_guard(conn):
    """Add the two derived week-boundary columns and the trigger that enforces
    one alternative work arrangement per calendar week.

    Separate from _add_missing_columns because a GENERATED column cannot be
    written in CREATE TABLE for a database that already exists — it has to be
    ALTERed in either way — so the columns and the trigger that reads them are
    installed together, in one place, for new and old databases alike."""
    # table_xinfo, not table_info: the latter hides VIRTUAL generated columns,
    # so it would report them missing on every boot and re-ALTER them.
    cols = {row[1] for row in conn.execute("PRAGMA table_xinfo(work_arrangement)")}
    if "week_head" not in cols:
        conn.execute("ALTER TABLE work_arrangement ADD COLUMN week_head TEXT "
                     f"GENERATED ALWAYS AS ({_WA_WEEK_HEAD_SQL}) VIRTUAL")
    if "week_tail" not in cols:
        conn.execute("ALTER TABLE work_arrangement ADD COLUMN week_tail TEXT "
                     f"GENERATED ALWAYS AS ({_WA_WEEK_TAIL_SQL}) VIRTUAL")
    # REG nominates no day and is exempt; a denied, withdrawn or superseded row
    # has already let its week go. Filings that predate this rule are left
    # exactly as they stand — the guard only judges what is written from now on.
    for name, event in (("ins", "INSERT"), ("upd", "UPDATE")):
        conn.execute(
            f"CREATE TRIGGER IF NOT EXISTS trg_wa_one_per_week_{name} "
            f"BEFORE {event} ON work_arrangement "
            "WHEN NEW.weekday IS NOT NULL AND NEW.status IN ('pending', 'approved') "
            f"BEGIN {_WA_WEEK_GUARD_BODY} END")


def _add_missing_columns(conn):
    """Lightweight migration: bring an older css_is.db up to the current schema.

    CREATE TABLE IF NOT EXISTS leaves pre-existing tables untouched, so a column
    added after a database was first created has to be ALTERed in by hand.
    """
    fi_cols = {row[1] for row in conn.execute("PRAGMA table_info(form_instance)")}
    if "end_date" not in fi_cols:
        # End of a multi-day activity. NULL on pre-existing rows = single-day
        # (the activity is its event_date only). Reporting still keys off event_date.
        conn.execute("ALTER TABLE form_instance ADD COLUMN end_date TEXT")
    if "venue" not in fi_cols:
        conn.execute("ALTER TABLE form_instance ADD COLUMN venue TEXT")
    if "modality" not in fi_cols:
        # 'f2f' | 'online'. NULL on pre-existing rows = treated as face-to-face
        # (every historical activity was physical). For online events the venue
        # column instead holds the platform / meeting link.
        conn.execute("ALTER TABLE form_instance ADD COLUMN modality TEXT")
    if "open_at" not in fi_cols:
        conn.execute("ALTER TABLE form_instance ADD COLUMN open_at TEXT")
    if "close_at" not in fi_cols:
        conn.execute("ALTER TABLE form_instance ADD COLUMN close_at TEXT")
    if "archived" not in fi_cols:
        # 1 = excluded from all analytics (dashboard + reports) but kept in the DB
        conn.execute("ALTER TABLE form_instance ADD COLUMN archived INTEGER NOT NULL DEFAULT 0")
    if "pooled" not in fi_cols:
        # 1 = NOT a standalone, named, counted event: its responses STILL count in
        # every aggregate/score (unlike archived), but it is hidden from the event
        # list/count and rolled up into one "Other small activities (pooled)" line.
        conn.execute("ALTER TABLE form_instance ADD COLUMN pooled INTEGER NOT NULL DEFAULT 0")
    if "attendance" not in fi_cols:
        # real event headcount (Total No. of Participants from the official report),
        # distinct from the survey-response count. NULL = unknown.
        conn.execute("ALTER TABLE form_instance ADD COLUMN attendance INTEGER")
    if "attendance_suspect" not in fi_cols:
        # 1 = the official figures are internally inconsistent (more survey responses
        # than participants), so the headcount/rate should be treated with caution.
        conn.execute("ALTER TABLE form_instance ADD COLUMN attendance_suspect INTEGER NOT NULL DEFAULT 0")
    if "encoding_locked" not in fi_cols:
        # 1 = hidden from the encode picker but still counted in every report/analytic.
        # Distinct from `archived` (which hides from everything). Lets admins close
        # historical activities to new paper entries without wiping them from analytics.
        conn.execute("ALTER TABLE form_instance ADD COLUMN encoding_locked INTEGER NOT NULL DEFAULT 0")
    if "created_by" not in fi_cols:
        # Who created this activity (admin_user.username), so the home "Your recent
        # activities" strip can show a manager what they made — including "outside
        # events" (Form 3 only, no event record) that the bureau-event lifecycle
        # feeds deliberately skip. NULL on every pre-existing row (creation was never
        # recorded before this column), so the strip is forward-looking only.
        conn.execute("ALTER TABLE form_instance ADD COLUMN created_by TEXT")
    ou_cols = {row[1] for row in conn.execute("PRAGMA table_info(org_unit)")}
    if "short_name" not in ou_cols:
        conn.execute("ALTER TABLE org_unit ADD COLUMN short_name TEXT")
    resp_cols = {row[1] for row in conn.execute("PRAGMA table_info(response)")}
    if "remarks" not in resp_cols:
        conn.execute("ALTER TABLE response ADD COLUMN remarks TEXT")
    if "served_by_rp_id" not in resp_cols:
        conn.execute("ALTER TABLE response ADD COLUMN served_by_rp_id INTEGER")
    if "attendee_id" not in resp_cols:
        # Links a response to the consented attendee session it came from (event
        # link-tree flow). NULL on every walk-in/QR/legacy response. load_atoms
        # never selects this column, so ratings stay analytically anonymous.
        conn.execute("ALTER TABLE response ADD COLUMN attendee_id INTEGER REFERENCES attendee(id)")
    if "archived_at" not in resp_cols:
        # Reversible per-response archive (mirrors form_instance.archived) — for the
        # standing Type-1 walk-in form, where a whole-form archive can't reach a single
        # bad/duplicate/test submission. NULL = active; a timestamp = archived.
        conn.execute("ALTER TABLE response ADD COLUMN archived_at TEXT")
    rp_cols = {row[1] for row in conn.execute("PRAGMA table_info(resource_person)")}
    for col, decl in (("position", "TEXT"), ("designation", "TEXT"),
                      ("focus_area", "TEXT"), ("email", "TEXT"),
                      ("employment_type", "TEXT"), ("honorific", "TEXT"),
                      ("agency", "TEXT")):
        if col not in rp_cols:
            conn.execute(f"ALTER TABLE resource_person ADD COLUMN {col} {decl}")
    if "photo" not in rp_cols:
        conn.execute("ALTER TABLE resource_person ADD COLUMN photo BLOB")
    if "photo_mime" not in rp_cols:
        conn.execute("ALTER TABLE resource_person ADD COLUMN photo_mime TEXT")
    # Signature image (a PNG/JPEG of the person's handwritten signature), used
    # only when this person is named as a certificate signatory. Stored as bytes
    # in the db like the profile photo. Sensitive (forgery risk) — never exposed
    # at a public URL the way /photo/ is; the certificate embeds the bytes.
    if "signature" not in rp_cols:
        conn.execute("ALTER TABLE resource_person ADD COLUMN signature BLOB")
    if "signature_mime" not in rp_cols:
        conn.execute("ALTER TABLE resource_person ADD COLUMN signature_mime TEXT")
    if "hidden_public" not in rp_cols:
        conn.execute("ALTER TABLE resource_person ADD COLUMN hidden_public INTEGER NOT NULL DEFAULT 0")
    # Reversible archive for people who left the bureau (resigned, retired,
    # transferred out). NULL = currently with the bureau; a timestamp = archived.
    # An archive is NOT a delete: the row stays, so every certificate, rating and
    # report that names this person keeps resolving. What it does is take them
    # out of the CURRENT roster — the directory's staff table, every speaker /
    # served-by / signatory picker, and the org chain of command — so a resigned
    # section head can never be offered as this week's approver.
    if "archived_at" not in rp_cols:
        conn.execute("ALTER TABLE resource_person ADD COLUMN archived_at TEXT")
    if "archived_reason" not in rp_cols:
        conn.execute("ALTER TABLE resource_person ADD COLUMN archived_reason TEXT")
    # admin_user.rp_id (links a login account to a directory person). The unique
    # index is created here (not in the CREATE TABLE script) so it runs only after
    # the column is guaranteed to exist, on both fresh and migrated databases.
    au_cols = {row[1] for row in conn.execute("PRAGMA table_info(admin_user)")}
    if au_cols:
        if "rp_id" not in au_cols:
            conn.execute("ALTER TABLE admin_user ADD COLUMN rp_id INTEGER REFERENCES resource_person(id)")
        if "must_change" not in au_cols:
            conn.execute("ALTER TABLE admin_user ADD COLUMN must_change INTEGER NOT NULL DEFAULT 0")
        # Staff onboarding + avatar companion (see
        # docs/STAFF_ONBOARDING_AVATAR_PLAN.md). avatar_kind/avatar_name hold the
        # adopted pet's species + given name (the SAME companion the wellness
        # module grows); onboarded_at is NULL until the person completes the
        # one-time /welcome flow — so every existing account is treated as
        # "not yet onboarded" and sees it once after this update ships.
        if "avatar_kind" not in au_cols:
            conn.execute("ALTER TABLE admin_user ADD COLUMN avatar_kind TEXT")
        if "avatar_name" not in au_cols:
            conn.execute("ALTER TABLE admin_user ADD COLUMN avatar_name TEXT")
        if "onboarded_at" not in au_cols:
            conn.execute("ALTER TABLE admin_user ADD COLUMN onboarded_at TEXT")
        # When the companion was last cared for (watered/fed). Purely cosmetic:
        # it drives the pet's mood (happy/okay/droopy), never the growth stage,
        # so the wellness gamification record stays the only source of growth.
        if "avatar_last_care_at" not in au_cols:
            conn.execute("ALTER TABLE admin_user ADD COLUMN avatar_last_care_at TEXT")
        # Consecutive calendar days of care — feeds the "Devoted caretaker"
        # badge only, never points. Can't be derived from the single last-care
        # timestamp, so it's the one extra persisted care artifact.
        if "avatar_care_streak" not in au_cols:
            conn.execute("ALTER TABLE admin_user ADD COLUMN avatar_care_streak INTEGER")
        # Self-service profile fields on the account itself, so EVERY viewer —
        # not just accounts linked to a directory person — can set a profile
        # photo and their own designation from the /me page. Linked accounts
        # keep writing their photo/designation onto the directory row; these
        # columns are the store for the unlinked ones.
        if "photo" not in au_cols:
            conn.execute("ALTER TABLE admin_user ADD COLUMN photo BLOB")
        if "photo_mime" not in au_cols:
            conn.execute("ALTER TABLE admin_user ADD COLUMN photo_mime TEXT")
        if "designation" not in au_cols:
            conn.execute("ALTER TABLE admin_user ADD COLUMN designation TEXT")
        # The account holder's own handwritten signature — drawn with a finger or
        # stylus on /me, or uploaded onto their directory row by an admin. Same
        # linked/unlinked split as the photo above: linked accounts keep theirs on
        # resource_person.signature (the field certificates already sign with),
        # these columns are the store for the unlinked ones. Sensitive (forgery
        # risk) — never served at a public URL, only back to its owner.
        if "signature" not in au_cols:
            conn.execute("ALTER TABLE admin_user ADD COLUMN signature BLOB")
        if "signature_mime" not in au_cols:
            conn.execute("ALTER TABLE admin_user ADD COLUMN signature_mime TEXT")
        # An EXPLICIT grant of bureau-wide sight (BUREAU_ACCESS_LEVELS). Scope
        # otherwise comes from the directory — the unit a person is recorded in
        # — and a role does not widen it. Some seats genuinely need more than
        # their own unit (the Admin Officer consolidating ANNEX C for the whole
        # bureau), and this is how they get it: named, per account, revocable,
        # and visible in the audit log, rather than a role quietly meaning
        # "everyone".
        if "bureau_access" not in au_cols:
            conn.execute("ALTER TABLE admin_user ADD COLUMN bureau_access TEXT "
                         "NOT NULL DEFAULT ''")
        # When this account last opened its own wellness / work-arrangement hub —
        # the requester-side twin of spot_feedback.submitter_seen_at. Drives the
        # nav bell's "your request was decided" notice: a decided row newer than
        # this timestamp is unseen. NULL (never opened) counts as "everything
        # decided so far is unseen", same convention as submitter_seen_at.
        if "wellness_seen_at" not in au_cols:
            conn.execute("ALTER TABLE admin_user ADD COLUMN wellness_seen_at TEXT")
        if "wa_seen_at" not in au_cols:
            conn.execute("ALTER TABLE admin_user ADD COLUMN wa_seen_at TEXT")
        conn.execute("CREATE UNIQUE INDEX IF NOT EXISTS ux_admin_user_rp "
                     "ON admin_user(rp_id) WHERE rp_id IS NOT NULL")
    # Respondent demographics captured at Type-2 pre-registration. These are NON-PII
    # aggregate tallies (sex = M/F, affiliation = DOH/NON-DOH) and are deliberately
    # NOT nulled by the retention purge — they carry no identity on their own.
    att_cols = {row[1] for row in conn.execute("PRAGMA table_info(attendee)")}
    if att_cols:
        if "sex" not in att_cols:
            conn.execute("ALTER TABLE attendee ADD COLUMN sex TEXT")          # M / F
        if "affiliation" not in att_cols:
            conn.execute("ALTER TABLE attendee ADD COLUMN affiliation TEXT")  # DOH / NON-DOH
        # Optional courtesy title (Mr./Ms./Mrs./Dr./Engr./Atty.) captured at
        # registration so the Certificate of Appearance can address the person
        # properly. Not identifying on its own, so (like sex/affiliation) it is
        # NOT nulled by the retention purge.
        if "honorific" not in att_cols:
            conn.execute("ALTER TABLE attendee ADD COLUMN honorific TEXT")
        # Set the first (and only) time the "your certificate is ready" email goes
        # out, so a participant who revisits the link-tree or resubmits a form
        # after finishing feedback doesn't get emailed the certificate link twice.
        if "certificate_emailed_at" not in att_cols:
            conn.execute("ALTER TABLE attendee ADD COLUMN certificate_emailed_at TEXT")
    # Manual demographic counts for older activities that predate capture. Keyed by
    # the activity's representative form_instance id (the event id the report uses).
    conn.execute(
        """CREATE TABLE IF NOT EXISTS activity_demographics (
               event_id   INTEGER PRIMARY KEY,
               male       INTEGER,
               female     INTEGER,
               doh        INTEGER,
               nondoh     INTEGER,
               updated_at TEXT,
               updated_by TEXT
           )""")
    # The account that created an event (username). NULL on events made before this
    # column existed -> those are manageable by admins only (safe default).
    # public_share (0/1) = the deliberate human "publish" gate: an activity's
    # curated resources only ever reach the public link tree once a manager flips
    # this on (and the global public_sharing_enabled setting is on). Default 0 so
    # nothing is exposed until someone chooses to.
    ev_cols = {row[1] for row in conn.execute("PRAGMA table_info(event)")}
    if ev_cols and "end_date" not in ev_cols:
        # End of a multi-day activity; NULL = single-day. Mirrors form_instance.end_date.
        conn.execute("ALTER TABLE event ADD COLUMN end_date TEXT")
    if ev_cols and "created_by" not in ev_cols:
        conn.execute("ALTER TABLE event ADD COLUMN created_by TEXT")
    if ev_cols and "modality" not in ev_cols:
        # 'f2f' | 'online'. NULL = face-to-face (legacy). Mirrors form_instance.modality.
        conn.execute("ALTER TABLE event ADD COLUMN modality TEXT")
    if ev_cols and "public_share" not in ev_cols:
        conn.execute("ALTER TABLE event ADD COLUMN public_share INTEGER NOT NULL DEFAULT 0")
    # Organizer-authored free-text messages shown on the public link tree:
    # welcome_message (seen post-consent by a registered participant) and
    # ending_message (auto-shown once the participant has finished ALL the
    # activity's feedback). NULL/blank => nothing shown (that is the on/off).
    if ev_cols and "welcome_message" not in ev_cols:
        conn.execute("ALTER TABLE event ADD COLUMN welcome_message TEXT")
    if ev_cols and "ending_message" not in ev_cols:
        conn.execute("ALTER TABLE event ADD COLUMN ending_message TEXT")
    # Certificate of Appearance (opt-in per activity). certificate_enabled (0/1)
    # is the on/off; signatory_rp_id points at the directory person who signs
    # (their name, position and signature image are pulled from that record);
    # certificate_verb is the template verb ("attended" / "appeared" /
    # "conducted") — defaults to "attended" when blank.
    if ev_cols and "certificate_enabled" not in ev_cols:
        conn.execute("ALTER TABLE event ADD COLUMN certificate_enabled INTEGER NOT NULL DEFAULT 0")
    if ev_cols and "signatory_rp_id" not in ev_cols:
        conn.execute("ALTER TABLE event ADD COLUMN signatory_rp_id INTEGER REFERENCES resource_person(id)")
    if ev_cols and "certificate_verb" not in ev_cols:
        conn.execute("ALTER TABLE event ADD COLUMN certificate_verb TEXT")
    # 'bureau' (default) | 'outside'. An "outside event — we were invited" groups its
    # speaker forms into an event record so it has a name + identity to manage and
    # monitor, but it has NO public link tree and NO registration (no Form 2 event
    # review). NULL = bureau (every event made before this column was bureau-organized).
    if ev_cols and "event_kind" not in ev_cols:
        conn.execute("ALTER TABLE event ADD COLUMN event_kind TEXT")
    # slug: optional human-readable alias for event_token, set by the activity's
    # manager so the public link can be tailored to the activity ("/e/les-quezon-june"
    # instead of "/e/42e21444c427"). NULL = no custom link (use the token). The random
    # token always keeps working, so QR codes already printed never break; get_event()
    # resolves token first, then slug. A partial UNIQUE index guards collisions while
    # allowing many NULLs.
    if ev_cols and "slug" not in ev_cols:
        conn.execute("ALTER TABLE event ADD COLUMN slug TEXT")
    conn.execute(
        "CREATE UNIQUE INDEX IF NOT EXISTS ux_event_slug ON event(slug) WHERE slug IS NOT NULL")
    # Comment raffle (opt-in per activity; face-to-face or online): when on, a
    # respondent who leaves a real comment is shown a stable claim CODE on the
    # thank-you screen, and the organizer can draw a random winner from the
    # commenters. raffle_prize is an optional label ("a tumbler") shown to the
    # respondent. 0 = off (the default; nothing changes for activities that don't
    # opt in). Works for both bureau and outside ("invited") activities.
    if ev_cols and "raffle_enabled" not in ev_cols:
        conn.execute("ALTER TABLE event ADD COLUMN raffle_enabled INTEGER NOT NULL DEFAULT 0")
    if ev_cols and "raffle_prize" not in ev_cols:
        conn.execute("ALTER TABLE event ADD COLUMN raffle_prize TEXT")
    # respondent_target: optional manager-entered "number of respondents" for an
    # activity, used as the completion-rate DENOMINATOR in place of the live
    # registered count. NULL (the default) = no override -> the Monitor computes
    # completion the way it always has (completed / registered). When set, the
    # rate becomes (completed + walk-ins) / respondent_target, so an organizer who
    # knows the real attendance (including QR/paper/walk-in respondents the roster
    # never captured) can make the figure honest. See event_registration_summary.
    if ev_cols and "respondent_target" not in ev_cols:
        conn.execute("ALTER TABLE event ADD COLUMN respondent_target INTEGER")
    # Each raffle draw is recorded so a multi-prize event can exclude prior winners,
    # the result survives a page refresh, and the draws are auditable. response_id
    # is the winning entry; the claim code is derived from it (claim_code), never
    # stored, so it can never drift from what the respondent was shown.
    conn.execute(
        """CREATE TABLE IF NOT EXISTS raffle_draw (
               id          INTEGER PRIMARY KEY,
               event_id    INTEGER NOT NULL REFERENCES event(id),
               response_id INTEGER NOT NULL REFERENCES response(id),
               prize       TEXT,
               drawn_at    TEXT NOT NULL,
               drawn_by    TEXT
           )""")
    # Curated resource/detail links a creator attaches to an event — slides,
    # programme, registration form, recordings, etc. Shown on the public link tree
    # (after consent) as the activity's single source of truth.
    # visible_after_done (0/1): 1 = this link only appears once the activity's CSS
    # is "done" (the day after the event_date, Asia/Manila) — e.g. certificates or
    # recordings; 0 = visible as soon as the activity is published.
    conn.execute(
        """CREATE TABLE IF NOT EXISTS event_link (
               id                 INTEGER PRIMARY KEY,
               event_id           INTEGER NOT NULL REFERENCES event(id),
               kind               TEXT NOT NULL DEFAULT 'other',
               label              TEXT NOT NULL,
               url                TEXT NOT NULL,
               note               TEXT,
               ordinal            INTEGER NOT NULL DEFAULT 0,
               visible_after_done INTEGER NOT NULL DEFAULT 0,
               created_by         TEXT,
               created_at         TEXT
           )""")
    el_cols = {row[1] for row in conn.execute("PRAGMA table_info(event_link)")}
    if el_cols and "visible_after_done" not in el_cols:
        conn.execute("ALTER TABLE event_link ADD COLUMN visible_after_done INTEGER NOT NULL DEFAULT 0")
    # Spot Feedback — a logged-in user flags a spot on a dashboard page and leaves a
    # comment; admins triage it on a board. element_selector + region_json locate the
    # spot (D4=A: no screenshot). status walks the SPOT_STATUSES workflow.
    conn.execute(
        """CREATE TABLE IF NOT EXISTS spot_feedback (
               id               INTEGER PRIMARY KEY,
               created_at       TEXT NOT NULL,
               user_id          INTEGER,
               submitter        TEXT,
               page_url         TEXT NOT NULL,
               element_selector TEXT,
               region_json      TEXT,
               message          TEXT NOT NULL,
               status           TEXT NOT NULL DEFAULT 'New',
               assignee         TEXT,
               admin_note       TEXT,
               updated_at       TEXT
           )""")
    sf_cols = {row[1] for row in conn.execute("PRAGMA table_info(spot_feedback)")}
    # submitter_seen_at: when the person who left the feedback last looked at their
    # "My feedback" page. Drives the unread badge (any newer update = unread).
    if sf_cols and "submitter_seen_at" not in sf_cols:
        conn.execute("ALTER TABLE spot_feedback ADD COLUMN submitter_seen_at TEXT")
    # archived_at: when the submitter tucked a resolved thread (Done / Won't fix)
    # into the collapsed "Archived" section of their own "My feedback" page. Purely
    # a per-submitter view convenience — the admin board still sees everything.
    if sf_cols and "archived_at" not in sf_cols:
        conn.execute("ALTER TABLE spot_feedback ADD COLUMN archived_at TEXT")
    # severity / duplicate_of: added for AI-assisted triage (AI integration plan
    # Phase 6) — a suggested urgency and a possible duplicate's id, both always
    # human-confirmed via the existing triage form before they're saved here.
    if sf_cols and "severity" not in sf_cols:
        conn.execute("ALTER TABLE spot_feedback ADD COLUMN severity TEXT")
    if sf_cols and "duplicate_of" not in sf_cols:
        conn.execute("ALTER TABLE spot_feedback ADD COLUMN duplicate_of INTEGER")
    # feedback_update — the phased "we heard you" trail the SUBMITTER sees: one
    # 'ack' row the moment they send it, then one 'status' row each time an admin
    # moves it along, optionally carrying a short heartfelt reply. Distinct from the
    # internal audit_log (which drives the admin-only triage timeline).
    conn.execute(
        """CREATE TABLE IF NOT EXISTS feedback_update (
               id          INTEGER PRIMARY KEY,
               feedback_id INTEGER NOT NULL,
               ts          TEXT NOT NULL,
               actor       TEXT,
               status      TEXT,
               reply       TEXT,
               kind        TEXT NOT NULL DEFAULT 'status'
           )""")

    # submission_log — idempotency ledger for the offline PWA queue (UX #5 Phase 2).
    # A response captured offline is replayed from the device when connectivity
    # returns, and that replay can fire more than once (page flush + Background Sync,
    # or a retry after a dropped connection). Each *submit action* carries one
    # client-generated id; the first replay records normally and logs the id here,
    # so any later replay of the same id is recognised as a duplicate and skipped.
    # Online submits carry no id and never touch this table.
    conn.execute(
        """CREATE TABLE IF NOT EXISTS submission_log (
               client_submission_id TEXT PRIMARY KEY,
               created_at           TEXT NOT NULL
           )""")

    # ui_event — passive UX-behavior telemetry (docs/UX_TELEMETRY_HANDOFF_PLAN.md;
    # ported from jongsky25/ofis-platform's ui_event, commit 7a7e369). One row per
    # interface interaction written best-effort from static/js/telemetry.js via
    # POST /telemetry — pageviews, dead/rage clicks, failed searches, client errors.
    # Distinct from spot_feedback above: that's what a user bothers to type up; this
    # is what happens passively, so friction can eventually be ranked without anyone
    # having to report it. Every text-bearing field is sanitized (route masked to a
    # pattern, element text/selector capped and digit-masked) both client-side and
    # again on ingest — see ui_telemetry.py.
    conn.execute(
        """CREATE TABLE IF NOT EXISTS ui_event (
               id               INTEGER PRIMARY KEY,
               created_at       TEXT NOT NULL,
               user_id          INTEGER,
               role             TEXT,
               session_id       TEXT NOT NULL,
               event_type       TEXT NOT NULL,
               route            TEXT NOT NULL,
               component        TEXT,
               element_selector TEXT,
               element_text     TEXT,
               meta_json        TEXT
           )""")
    conn.execute("CREATE INDEX IF NOT EXISTS ui_event_type_created_idx "
                 "ON ui_event(event_type, created_at)")
    conn.execute("CREATE INDEX IF NOT EXISTS ui_event_route_created_idx "
                 "ON ui_event(route, created_at)")

    # ai_interaction / ai_budget — docs/AI_INTEGRATION_PLAN.md Phase 0. Every
    # ai_core.ask()/test_connection() call writes one ai_interaction row,
    # success or fallback, so misbehavior is diagnosed from logs (the point
    # of the per-use 👍/👎 feedback columns — rating lives on the row rather
    # than a separate table). ai_budget is the DB-backed daily spend counter
    # ai_core.budget_check_and_consume reads/writes: keyed by local calendar
    # date, so it survives a restart with no scheduler needed.
    conn.execute(
        """CREATE TABLE IF NOT EXISTS ai_interaction (
               id               INTEGER PRIMARY KEY,
               created_at       TEXT NOT NULL,
               user_id          INTEGER,
               role             TEXT,
               feature          TEXT NOT NULL,
               mode             TEXT NOT NULL,
               model            TEXT,
               prompt_masked    TEXT,
               response_masked  TEXT,
               outcome          TEXT NOT NULL,
               destination      TEXT,
               confidence       REAL,
               latency_ms       INTEGER,
               tokens_in        INTEGER,
               tokens_out       INTEGER,
               error            TEXT,
               rating           INTEGER,
               rating_comment   TEXT,
               rated_at         TEXT
           )""")
    conn.execute("CREATE INDEX IF NOT EXISTS ai_interaction_feature_created_idx "
                 "ON ai_interaction(feature, created_at)")
    conn.execute("CREATE INDEX IF NOT EXISTS ai_interaction_rating_idx "
                 "ON ai_interaction(rating)")
    conn.execute(
        """CREATE TABLE IF NOT EXISTS ai_budget (
               day     TEXT NOT NULL,
               feature TEXT NOT NULL,
               calls   INTEGER NOT NULL DEFAULT 0,
               PRIMARY KEY (day, feature)
           )""")

    # report_draft — docs/AI_INTEGRATION_PLAN.md Phase 5. AI-drafted (then
    # possibly analyst-edited) report-narrative text, keyed by which report
    # scope it belongs to (e.g. one activity's MRR columns, or one period's
    # official-report closing sections). One row per (scope, scope_key,
    # field); the latest write simply wins — unlike comment_override there is
    # no human > ai precedence to protect, since an analyst editing an AI
    # draft IS the expected refine-and-save flow. Overwritten in place, never
    # appended, so unlike ai_interaction it needs no retention purge.
    conn.execute(
        """CREATE TABLE IF NOT EXISTS report_draft (
               scope      TEXT NOT NULL,
               scope_key  TEXT NOT NULL,
               field      TEXT NOT NULL,
               text       TEXT NOT NULL,
               actor      TEXT NOT NULL,
               updated_at TEXT NOT NULL,
               PRIMARY KEY (scope, scope_key, field)
           )""")

    ai_cols = {row[1] for row in conn.execute("PRAGMA table_info(ai_interaction)")}
    if "provider" not in ai_cols:
        # docs/AI_FALLBACK_PLAN.md — which provider actually answered (NULL on
        # every pre-existing row, treated as "gemini" when displayed).
        conn.execute("ALTER TABLE ai_interaction ADD COLUMN provider TEXT")
    if "question_norm" not in ai_cols:
        # The clean, normalized user question (qa_rules.normalize) — captured
        # so the learned-rules layer can mine frequently-asked questions
        # without parsing them back out of the masked router-prompt blob.
        # NULL on every pre-existing row and whenever prompt logging is off.
        conn.execute("ALTER TABLE ai_interaction ADD COLUMN question_norm TEXT")
        conn.execute("CREATE INDEX IF NOT EXISTS ai_interaction_question_idx "
                     "ON ai_interaction(question_norm)")

    # learned_rule — the deterministic FAQ layer in front of the NL router
    # (qa_rules.py, app.py's _ai_try_rules). One row per learned/seeded/
    # hand-authored question->target mapping: a rule stores only a `kind`
    # (navigate|answer|help) + `target_key`, never a URL or prose, so serving
    # it reuses the router's own cap-filtered catalog and can never surface a
    # screen/answer the user isn't allowed to see. `pattern` is the normalized
    # question (qa_rules.normalize); `keywords` optionally widens matching.
    # `source` is 'seed' | 'promoted' | 'manual'; `hits`/`last_hit_at` track
    # how much AI spend each rule has saved.
    conn.execute(
        """CREATE TABLE IF NOT EXISTS learned_rule (
               id           INTEGER PRIMARY KEY,
               pattern      TEXT NOT NULL,
               keywords     TEXT,
               sample_query TEXT,
               kind         TEXT NOT NULL,
               target_key   TEXT NOT NULL,
               enabled      INTEGER NOT NULL DEFAULT 1,
               source       TEXT NOT NULL DEFAULT 'manual',
               hits         INTEGER NOT NULL DEFAULT 0,
               last_hit_at  TEXT,
               notes        TEXT,
               created_by   TEXT,
               created_at   TEXT NOT NULL,
               updated_at   TEXT NOT NULL
           )""")
    conn.execute("CREATE UNIQUE INDEX IF NOT EXISTS learned_rule_uq "
                 "ON learned_rule(kind, target_key, pattern)")

    # Wellness: free-text specification for the "Others" activity, and the richer
    # post-break report fields (DOH Post-Activity Report). All nullable / additive,
    # so pre-existing rows read as "not provided".
    wc_cols = {row[1] for row in conn.execute("PRAGMA table_info(wellness_claim)")}
    if wc_cols and "activity_other" not in wc_cols:
        conn.execute("ALTER TABLE wellness_claim ADD COLUMN activity_other TEXT")
    wr_cols = {row[1] for row in conn.execute("PRAGMA table_info(wellness_reflection)")}
    if wr_cols:
        if "usefulness" not in wr_cols:
            conn.execute("ALTER TABLE wellness_reflection ADD COLUMN usefulness INTEGER")
        if "felt_refreshed" not in wr_cols:
            conn.execute("ALTER TABLE wellness_reflection ADD COLUMN felt_refreshed INTEGER")
        if "managed_stress" not in wr_cols:
            conn.execute("ALTER TABLE wellness_reflection ADD COLUMN managed_stress INTEGER")
        if "focus_impact" not in wr_cols:
            conn.execute("ALTER TABLE wellness_reflection ADD COLUMN focus_impact TEXT")
        if "suggestions" not in wr_cols:
            conn.execute("ALTER TABLE wellness_reflection ADD COLUMN suggestions TEXT")

    # The Office of the Director heads the whole bureau — it is NOT one of the
    # administrative sections that sit beside the divisions. Promote it to its own
    # 'office' level so org_structure surfaces it as the directorate (above the
    # divisions) instead of mis-tagging it "Administrative". Guarded so it only
    # writes once (init_db re-runs on every connection — an unconditional
    # UPDATE+commit here would contend for the write lock on every request).
    if conn.execute("""SELECT 1 FROM org_unit
                       WHERE level='section' AND name LIKE 'Office of the Director%'
                       LIMIT 1""").fetchone():
        conn.execute("""UPDATE org_unit SET level='office'
                        WHERE level='section' AND name LIKE 'Office of the Director%'""")
        conn.commit()

    _seed_bureau_access(conn)


# ---------------------------------------------------------------------
# Adding things (the directory, people, forms, answers)
# ---------------------------------------------------------------------

def add_org_unit(conn, name, level, path, short_name=None):
    cur = conn.execute("INSERT INTO org_unit(name, short_name, level, path) VALUES (?,?,?,?)",
                       (name, short_name, level, path))
    conn.commit()
    return cur.lastrowid


def add_rp(conn, name, is_internal, org_unit_id=None, *,
           position=None, designation=None, focus_area=None,
           email=None, employment_type=None, honorific=None, agency=None):
    cur = conn.execute(
        """INSERT INTO resource_person(name, is_internal, org_unit_id,
               position, designation, focus_area, email, employment_type, honorific, agency)
           VALUES (?,?,?,?,?,?,?,?,?,?)""",
        (name, 1 if is_internal else 0, org_unit_id,
         position, designation, focus_area, email, employment_type, honorific, agency))
    conn.commit()
    return cur.lastrowid


def add_external_organizer(conn, name):
    cur = conn.execute("INSERT OR IGNORE INTO external_organizer(name) VALUES (?)", (name,))
    conn.commit()
    row = conn.execute("SELECT id FROM external_organizer WHERE name=?", (name,)).fetchone()
    return row[0]


def create_form_instance(conn, survey_type, form, event_date, *, end_date=None,
                         serving_staff=None, serving_staff_org_id=None, service=None,
                         lead_org_id=None, rp_id=None, topic=None,
                         organizer_external_id=None, venue=None, modality=None,
                         created_by=None):
    """
    The section manager creates this; it bakes in the context. The returned
    qr_token is what the QR code points to -- each scan inherits this context,
    so the rater only supplies ratings. created_by stamps the manager who made it
    (powers the home "Your recent activities" strip).

    end_date (optional) marks the last day of a multi-day activity; NULL means a
    single-day activity. The reporting period always keys off event_date (start).
    """
    token = uuid.uuid4().hex[:12]
    cur = conn.execute("""
        INSERT INTO form_instance(survey_type, form, qr_token, event_date, end_date, venue, modality,
            serving_staff, serving_staff_org_id, service, lead_org_id, rp_id,
            topic, organizer_external_id, created_at, created_by)
        VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
        (survey_type, form, token, event_date, end_date or None, venue, modality,
         serving_staff, serving_staff_org_id,
         service, lead_org_id, rp_id, topic, organizer_external_id,
         tz.now_iso(), created_by))
    conn.commit()
    return cur.lastrowid


def record_response(conn, form_instance_id, answers, submitted_at=None,
                    remarks=None, item_remarks=None, served_by_rp_id=None,
                    attendee_id=None):
    """
    answers = list of (item_id, value). Use value=None to mean N/A.
    For SERVQUAL forms a 0 also counts as N/A and is normalised here.

    remarks      = one overall free-text comment for the whole response (the
                   "verbatim" the engine points to when a score ceilings out).
    item_remarks = optional {item_id: text} of notes tied to a single item.
    Both are kept out of the atoms table -- they are read by humans, never scored.
    """
    remarks = (remarks or "").strip() or None
    cur = conn.execute(
        "INSERT INTO response(form_instance_id, submitted_at, remarks, served_by_rp_id, attendee_id) "
        "VALUES (?,?,?,?,?)",
        (form_instance_id, submitted_at or tz.now_iso(),
         remarks, served_by_rp_id, attendee_id))
    rid = cur.lastrowid
    for item_id, value in answers:
        is_na = 1 if (value is None or value == 0) else 0
        stored = None if is_na else float(value)
        conn.execute("INSERT INTO answer(response_id, item_id, value, is_na) VALUES (?,?,?,?)",
                     (rid, item_id, stored, is_na))
    for item_id, text in (item_remarks or {}).items():
        text = (text or "").strip()
        if text:
            conn.execute("INSERT INTO item_remark(response_id, item_id, text) VALUES (?,?,?)",
                         (rid, item_id, text))
    conn.commit()
    return rid


def submission_seen(conn, sid):
    """True if this client submission id was already recorded (offline-queue
    replay dedup — see the submission_log table)."""
    if not sid:
        return False
    return conn.execute(
        "SELECT 1 FROM submission_log WHERE client_submission_id=?", (sid,)
    ).fetchone() is not None


def mark_submission(conn, sid):
    """Log a client submission id as processed. Idempotent: a concurrent replay
    that already inserted the same id raises IntegrityError, which we swallow."""
    if not sid:
        return
    try:
        conn.execute(
            "INSERT INTO submission_log(client_submission_id, created_at) VALUES (?,?)",
            (sid, tz.now_iso()))
        conn.commit()
    except sqlite3.IntegrityError:
        pass


# ---------------------------------------------------------------------
# App settings (tiny key/value store — e.g. the backup schedule)
# ---------------------------------------------------------------------

def get_setting(conn, key, default=None):
    row = conn.execute("SELECT value FROM app_setting WHERE key=?", (key,)).fetchone()
    return row[0] if row else default


def set_setting(conn, key, value):
    conn.execute(
        "INSERT INTO app_setting(key, value) VALUES (?,?) "
        "ON CONFLICT(key) DO UPDATE SET value=excluded.value",
        (key, None if value is None else str(value)))
    conn.commit()


def get_settings(conn, keys):
    """Fetch many settings at once as a {key: value} dict (missing -> absent)."""
    if not keys:
        return {}
    qs = ",".join("?" * len(keys))
    return {k: v for k, v in conn.execute(
        f"SELECT key, value FROM app_setting WHERE key IN ({qs})", tuple(keys))}


# ---------------------------------------------------------------------
# Events (the link-tree grouping) + attendee identity / consent capture
# ---------------------------------------------------------------------

def create_event(conn, title, event_date, *, end_date=None, venue=None, organizer=None,
                 lead_org_id=None, form_instance_ids=None, created_by=None,
                 modality=None, event_kind="bureau"):
    """Persist an event that groups the forms created together, and return
    {id, event_token}. The token is the public /e/<token> link-tree slug.
    form_instance_ids are linked in the order given (the F2 event review first,
    then each F3 speaker), which is the order the link tree renders them.
    created_by = the username of the account that created it (drives who may
    manage the activity's curated links).
    event_kind = 'bureau' (default, public link tree + registration) or 'outside'
    (an invited activity: grouping + name only, no link tree, no registration)."""
    token = uuid.uuid4().hex[:12]
    cur = conn.execute(
        """INSERT INTO event(event_token, title, event_date, end_date, venue, modality, organizer,
               lead_org_id, created_at, created_by, event_kind) VALUES (?,?,?,?,?,?,?,?,?,?,?)""",
        (token, title, event_date, end_date or None, venue, modality, organizer, lead_org_id,
         tz.now_iso(), created_by, event_kind or "bureau"))
    event_id = cur.lastrowid
    for i, fid in enumerate(form_instance_ids or []):
        conn.execute(
            "INSERT OR IGNORE INTO event_form(event_id, form_instance_id, ordinal) VALUES (?,?,?)",
            (event_id, fid, i))
    conn.commit()
    return {"id": event_id, "event_token": token}


def find_recent_duplicate_event(conn, title, event_date):
    """The most recently created event with the same title (case/space-insensitive)
    and the same event date — the shape of an accidental resubmit on /create
    (spot-feedback #67: the same manager created a same-day duplicate 26 minutes
    after the original, leaving an empty twin with zero responses; a second pair
    3 minutes apart went unnoticed). Matches regardless of who created it or how
    long ago — a same-title, same-date pair is worth flagging even when two
    different staff logged it, or one re-entered it days later. The create screen
    shows this as a "did you mean to create another one?" warning instead of
    silently doubling the activity. Returns None if nothing matches."""
    title = (title or "").strip()
    if not title or not event_date:
        return None
    row = conn.execute("""
        SELECT e.id, e.event_token, e.created_at, e.event_kind,
               (SELECT COUNT(*) FROM event_form ef JOIN response r
                  ON r.form_instance_id = ef.form_instance_id WHERE ef.event_id = e.id)
        FROM event e
        WHERE lower(trim(e.title)) = lower(trim(?))
              AND e.event_date = ?
        ORDER BY e.created_at DESC LIMIT 1
    """, (title, event_date)).fetchone()
    if not row:
        return None
    return {"id": row[0], "event_token": row[1], "created_at": row[2],
            "event_kind": row[3] or "bureau", "responses": row[4]}


_EVENT_COLS = """
        SELECT e.id, e.event_token, e.title, e.event_date, e.venue, e.organizer,
               ou.name AS lead_name, e.created_by, COALESCE(e.public_share, 0),
               e.welcome_message, e.ending_message, e.modality,
               COALESCE(e.certificate_enabled, 0), e.signatory_rp_id, e.certificate_verb,
               e.event_kind, e.slug,
               COALESCE(e.raffle_enabled, 0), e.raffle_prize, e.end_date,
               e.respondent_target
        FROM event e
        LEFT JOIN org_unit ou ON ou.id = e.lead_org_id
"""


def _event_row(row):
    return {"id": row[0], "event_token": row[1], "title": row[2],
            "event_date": row[3], "venue": row[4], "organizer": row[5],
            "lead_name": row[6], "created_by": row[7],
            "public_share": bool(row[8]),
            "welcome_message": row[9], "ending_message": row[10],
            "modality": row[11] or "f2f",
            "certificate_enabled": bool(row[12]),
            "signatory_rp_id": row[13],
            "certificate_verb": row[14] or "attended",
            "event_kind": row[15] or "bureau",
            "slug": row[16],
            "raffle_enabled": bool(row[17]),
            "raffle_prize": row[18],
            "end_date": row[19],
            "respondent_target": row[20]}


def set_event_messages(conn, event_id, welcome, ending):
    """Persist the organizer's welcome + ending messages for an event. Blank
    text is stored as NULL so the participant page simply shows nothing."""
    conn.execute(
        "UPDATE event SET welcome_message = ?, ending_message = ? WHERE id = ?",
        ((welcome or "").strip() or None, (ending or "").strip() or None, event_id))
    conn.commit()


_CERT_VERBS = ("attended", "appeared at", "conducted", "participated in")


def set_event_certificate(conn, event_id, *, enabled, signatory_rp_id, verb):
    """Persist an activity's Certificate-of-Appearance settings. signatory_rp_id
    is a directory person (their name/position/signature drive the certificate);
    verb is one of _CERT_VERBS (anything else falls back to 'attended')."""
    verb = verb if verb in _CERT_VERBS else "attended"
    conn.execute(
        """UPDATE event SET certificate_enabled = ?, signatory_rp_id = ?,
                            certificate_verb = ? WHERE id = ?""",
        (1 if enabled else 0,
         signatory_rp_id if signatory_rp_id else None,
         verb, event_id))
    conn.commit()


def get_event(conn, event_token):
    """Resolve an event by its random token OR its custom slug, or None. The
    random token is tried first so it always wins over a slug (the token is the
    canonical, never-changing key behind printed QR codes); the slug is only a
    convenience alias a manager may set (set_event_slug)."""
    row = conn.execute(_EVENT_COLS + " WHERE e.event_token = ?",
                       (event_token,)).fetchone()
    if not row and event_token:
        row = conn.execute(_EVENT_COLS + " WHERE e.slug = ?",
                           (event_token,)).fetchone()
    return _event_row(row) if row else None


def list_events_on_date(conn, event_date):
    """Every event (bureau or outside) whose event_date is exactly this day —
    the "happening tomorrow" query for the scheduled reminder job. A multi-day
    activity only matches on its start date, same as everywhere else event_date
    is treated as the day-of."""
    rows = conn.execute(_EVENT_COLS + " WHERE e.event_date = ? ORDER BY e.id",
                        (event_date,)).fetchall()
    return [_event_row(r) for r in rows]


def event_lead_org_id(conn, event_id):
    """The org unit an event was filed under (lead_org_id), or None. Not part
    of the _event_row shape (which only carries the resolved org NAME), so a
    caller that needs to look up that unit's chiefs (org_unit_chiefs) queries
    it here instead."""
    row = conn.execute("SELECT lead_org_id FROM event WHERE id=?", (event_id,)).fetchone()
    return row[0] if row else None


# A slug is lowercase letters/digits in hyphen-joined words (no leading/trailing
# or doubled hyphens): "les-quezon-june", "lhsi-2026". Short reserved words that
# are top-level route names are refused so a vanity link can never read like one.
_SLUG_RE = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
_RESERVED_SLUGS = {"e", "r", "seq", "encode", "activities", "monitor", "login",
                   "logout", "admin", "static", "dashboard", "reports", "my",
                   "create", "arta", "directory", "search", "ops", "shared"}


def set_event_slug(conn, event_id, slug):
    """Set or clear an event's custom slug (the vanity alias for event_token).
    A blank value clears it. Returns (ok: bool, error: str|None) — the error is a
    short, participant-friendly reason when the slug is rejected."""
    slug = (slug or "").strip().lower()
    if not slug:
        conn.execute("UPDATE event SET slug = NULL WHERE id = ?", (event_id,))
        conn.commit()
        return True, None
    if not (3 <= len(slug) <= 40) or not _SLUG_RE.match(slug):
        return False, ("Use 3–40 lowercase letters, numbers and single hyphens, "
                       "e.g. les-quezon-june.")
    if slug in _RESERVED_SLUGS:
        return False, "That word is reserved — please pick another."
    # Must not collide with ANY other event's token or slug (so every key resolves
    # to exactly one activity). The partial unique index is the backstop.
    clash = conn.execute(
        "SELECT 1 FROM event WHERE (event_token = ? OR slug = ?) AND id <> ?",
        (slug, slug, event_id)).fetchone()
    if clash:
        return False, "That link is already taken — try another."
    conn.execute("UPDATE event SET slug = ? WHERE id = ?", (slug, event_id))
    conn.commit()
    return True, None


def get_event_by_id(conn, event_id):
    """Resolve an event id to its header details, or None."""
    row = conn.execute(_EVENT_COLS + " WHERE e.id = ?", (event_id,)).fetchone()
    return _event_row(row) if row else None


def event_css_done(conn, event_id):
    """Is the activity's CSS "done"? Derived purely from the date — an event is
    done once the LOCAL (Asia/Manila) calendar day has changed past its
    event_date, i.e. from the start of the day after the activity. No grace day,
    no stored flag. An event with a blank/missing date is never "done" (the safe
    default). "Today" comes from the Manila clock (tzutil), so the flip lands on
    real local midnight rather than the UTC container's midnight."""
    row = conn.execute("SELECT event_date FROM event WHERE id = ?",
                       (event_id,)).fetchone()
    if not row or not row[0]:
        return False
    # Manila today vs the event day (see tzutil): SQLite 'localtime' is the UTC
    # container zone, ~8 h off the Manila-stamped event_date.
    done = conn.execute("SELECT ? > date(?)",
                        (_local_today(), row[0])).fetchone()[0]
    return bool(done)


def list_shared_events(conn, limit=60):
    """Concluded activities (event day has lapsed) that carry at least one
    "shared immediately" resource — the materials any registered staff member can
    browse on the /shared index. Newest first. The "after feedback" bucket is a
    per-participant reward and is deliberately excluded here. Each row carries its
    immediate-resource count."""
    rows = conn.execute(
        """SELECT id, event_token, title, event_date, venue, organizer, modality
           FROM event
           WHERE event_date IS NOT NULL AND event_date <> ''
                 AND ? > date(event_date)      -- Manila today (see tzutil), not UTC 'localtime'
           ORDER BY date(event_date) DESC, id DESC""", (_local_today(),)).fetchall()
    out = []
    for r in rows:
        links = [l for l in list_event_links(conn, r[0]) if not l["visible_after_done"]]
        if not links:
            continue
        out.append({"id": r[0], "event_token": r[1], "title": r[2],
                    "event_date": r[3], "venue": r[4], "organizer": r[5],
                    "modality": r[6] or "f2f", "n_links": len(links)})
        if len(out) >= limit:
            break
    return out


def get_event_forms(conn, event_id):
    """The form instances of an event, in link-tree order, with their qr_token,
    survey_type and a display label. Archived forms are excluded (they vanish
    everywhere else too)."""
    rows = conn.execute("""
        SELECT fi.qr_token, fi.survey_type, fi.topic, rp.name AS rp_name, ef.ordinal,
               fi.id AS form_instance_id
        FROM event_form ef
        JOIN form_instance fi ON fi.id = ef.form_instance_id
        LEFT JOIN resource_person rp ON rp.id = fi.rp_id
        WHERE ef.event_id = ? AND COALESCE(fi.archived, 0) = 0
        ORDER BY ef.ordinal
    """, (event_id,)).fetchall()
    out = []
    for tok, stype, topic, rp_name, _, fi_id in rows:
        out.append({"qr_token": tok, "survey_type": stype, "topic": topic,
                    "rp_name": rp_name, "form_instance_id": fi_id})
    return out


def list_event_resource_persons(conn, event_id):
    """Distinct resource persons featured in an event (its Type-3 speaker forms),
    in link-tree order, with the bits the public page shows — name, role line and
    whether a photo exists (served by /photo/<id>). Hidden-public RPs are dropped."""
    rows = conn.execute("""
        SELECT rp.id, rp.name, rp.honorific, rp.position, rp.designation,
               rp.agency, rp.is_internal, (rp.photo IS NOT NULL) AS has_photo,
               MIN(ef.ordinal) AS ord
        FROM event_form ef
        JOIN form_instance fi ON fi.id = ef.form_instance_id
        JOIN resource_person rp ON rp.id = fi.rp_id
        WHERE ef.event_id = ? AND fi.survey_type = 3
              AND COALESCE(fi.archived, 0) = 0
              AND COALESCE(rp.hidden_public, 0) = 0
        GROUP BY rp.id
        ORDER BY ord, rp.name
    """, (event_id,)).fetchall()
    out = []
    for r in rows:
        role = r[3] or r[4] or r[5] or ("Bureau staff" if r[6] else None)
        out.append({"id": r[0], "name": r[1], "honorific": r[2], "role": role,
                    "agency": r[5], "is_internal": bool(r[6]), "has_photo": bool(r[7])})
    return out


def event_speaker_names(conn, event_id):
    """Compact 'Honorific Name' list of an event's resource persons, for the
    home lifecycle cards (the RP lens over upcoming/ongoing activities). Empty for
    backfilled rows that have no event record."""
    if not event_id:
        return []
    names = []
    for s in list_event_resource_persons(conn, event_id):
        hon = (s["honorific"] or "").strip()
        names.append(f"{hon} {s['name']}".strip())
    return names


# --- Curated event links (the managed link tree) ---------------------------

EVENT_LINK_KINDS = ("program", "slides", "registration", "recording",
                    "certificate", "info", "other")


def _event_link_row(r):
    return {"id": r[0], "event_id": r[1], "kind": r[2], "label": r[3],
            "url": r[4], "note": r[5], "ordinal": r[6],
            "visible_after_done": bool(r[7]), "created_by": r[8]}


_EVENT_LINK_COLS = ("SELECT id, event_id, kind, label, url, note, ordinal, "
                    "COALESCE(visible_after_done, 0), created_by FROM event_link")


def list_event_links(conn, event_id):
    """Every curated resource link for an event, in display order (the manage
    view — includes unpublished and after-done links)."""
    rows = conn.execute(
        _EVENT_LINK_COLS + " WHERE event_id = ? ORDER BY ordinal, id",
        (event_id,)).fetchall()
    return [_event_link_row(r) for r in rows]


def attendee_completed_feedback(conn, event_id, attendee_id):
    """True once this attendee has submitted a response for EVERY non-archived
    feedback form in the event — i.e. they have finished the CSS. This is what
    unlocks the "after feedback" resource bucket for them. False for no attendee
    or an event with no forms."""
    if not attendee_id:
        return False
    total = conn.execute(
        """SELECT COUNT(*) FROM event_form ef
           JOIN form_instance fi ON fi.id = ef.form_instance_id
           WHERE ef.event_id = ? AND COALESCE(fi.archived, 0) = 0""",
        (event_id,)).fetchone()[0]
    if not total:
        return False
    answered = conn.execute(
        """SELECT COUNT(DISTINCT r.form_instance_id) FROM response r
           JOIN event_form ef ON ef.form_instance_id = r.form_instance_id
           WHERE ef.event_id = ? AND r.attendee_id = ?""",
        (event_id, attendee_id)).fetchone()[0]
    return answered >= total


def mark_certificate_emailed(conn, attendee_id):
    """Record that the "your certificate is ready" email went out for this
    attendee. Returns True the first time (the caller should send the email),
    False if it was already sent (an UPDATE ... WHERE IS NULL touches no row) —
    so a retry or a second feedback-completing submission never double-sends."""
    cur = conn.execute(
        "UPDATE attendee SET certificate_emailed_at = ? "
        "WHERE id = ? AND certificate_emailed_at IS NULL",
        (tz.now_iso(), attendee_id))
    conn.commit()
    return cur.rowcount > 0


def attendee_answered_forms(conn, event_id, attendee_id):
    """The set of form_instance ids in this event that this attendee has already
    submitted a response for. Drives the "one response per form" guard: a form in
    this set must not be answered again. Empty for no attendee."""
    if not attendee_id:
        return set()
    rows = conn.execute(
        """SELECT DISTINCT r.form_instance_id FROM response r
           JOIN event_form ef ON ef.form_instance_id = r.form_instance_id
           WHERE ef.event_id = ? AND r.attendee_id = ?""",
        (event_id, attendee_id)).fetchall()
    return {row[0] for row in rows}


def attendee_answered_form(conn, form_instance_id, attendee_id):
    """True if this attendee has already submitted a response for this exact form
    instance — the server-side check that stops a second submission of the same
    rating link (whether from a double-tap, a back-button, or a re-opened link)."""
    if not attendee_id:
        return False
    return conn.execute(
        "SELECT 1 FROM response WHERE form_instance_id = ? AND attendee_id = ? LIMIT 1",
        (form_instance_id, attendee_id)).fetchone() is not None


def list_public_event_links(conn, event_id, completed=False):
    """The curated links a participant may see: always the "immediate" bucket
    (visible_after_done = 0), plus the "after feedback" bucket only once they have
    completed the activity's feedback (completed=True). The global master switch
    is applied by the caller."""
    return [l for l in list_event_links(conn, event_id)
            if completed or not l["visible_after_done"]]


def get_event_link(conn, link_id):
    r = conn.execute(_EVENT_LINK_COLS + " WHERE id = ?", (link_id,)).fetchone()
    return _event_link_row(r) if r else None


def add_event_link(conn, event_id, kind, label, url, note=None,
                   visible_after_done=False, created_by=None):
    """Append a curated link to an event; ordinal = next slot. Returns the id."""
    nxt = conn.execute(
        "SELECT COALESCE(MAX(ordinal), -1) + 1 FROM event_link WHERE event_id = ?",
        (event_id,)).fetchone()[0]
    kind = kind if kind in EVENT_LINK_KINDS else "other"
    cur = conn.execute(
        """INSERT INTO event_link(event_id, kind, label, url, note, ordinal,
               visible_after_done, created_by, created_at)
           VALUES (?,?,?,?,?,?,?,?,?)""",
        (event_id, kind, label, url, note or None, nxt,
         1 if visible_after_done else 0, created_by,
         tz.now_iso()))
    conn.commit()
    return cur.lastrowid


def update_event_link(conn, link_id, *, kind, label, url, note=None,
                      visible_after_done=False):
    kind = kind if kind in EVENT_LINK_KINDS else "other"
    conn.execute(
        "UPDATE event_link SET kind=?, label=?, url=?, note=?, visible_after_done=? "
        "WHERE id=?",
        (kind, label, url, note or None, 1 if visible_after_done else 0, link_id))
    conn.commit()


def delete_event_link(conn, link_id):
    conn.execute("DELETE FROM event_link WHERE id=?", (link_id,))
    conn.commit()


# ---------------------------------------------------------------------
# Spot Feedback (in-page UI/UX feedback + admin triage board)
# ---------------------------------------------------------------------

# The triage workflow, in order. First value is the default for new submissions.
SPOT_STATUSES = ["New", "Reviewing", "Will address", "Won't fix", "Done"]

# Optional urgency tag an admin can set (by hand or from an AI suggestion, Phase 6
# of the AI integration plan). No default — most items are never tagged.
SPOT_SEVERITIES = ["Low", "Medium", "High", "Critical"]

# Terminal statuses — a thread here is finished, so the submitter may archive it.
SPOT_RESOLVED_STATUSES = ["Won't fix", "Done"]

# How each internal status reads to the person who left the feedback — warm,
# plain language for the "My feedback" page (the admin board keeps the raw names).
SPOT_USER_STATUS = {
    "New": "Received",
    "Reviewing": "Being looked at",
    "Will address": "We're on it",
    "Won't fix": "Reviewed — not planned",
    "Done": "Done",
}

# The acknowledgement the submitter sees the instant they send feedback (phase 1).
SPOT_ACK_MESSAGE = ("Thank you for taking the time to flag this — we've received "
                    "your note and a real person will look at it. We'll keep you "
                    "posted right here as it moves along.")

_SPOT_COLS = ("SELECT id, created_at, user_id, submitter, page_url, element_selector, "
              "region_json, message, status, admin_note, updated_at, submitter_seen_at, "
              "archived_at, severity, duplicate_of "
              "FROM spot_feedback")


def _spot_row(r):
    return {"id": r[0], "created_at": r[1], "user_id": r[2], "submitter": r[3],
            "page_url": r[4], "element_selector": r[5], "region_json": r[6],
            "message": r[7], "status": r[8], "admin_note": r[9],
            "updated_at": r[10], "submitter_seen_at": r[11],
            "archived_at": r[12], "severity": r[13], "duplicate_of": r[14]}


def _feedback_update_row(r):
    return {"ts": r[0], "actor": r[1], "status": r[2], "reply": r[3], "kind": r[4]}


def add_feedback_update(conn, feedback_id, *, status, reply, kind, actor, commit=True):
    """Append one phase event to a submission's submitter-facing trail."""
    conn.execute(
        "INSERT INTO feedback_update(feedback_id, ts, actor, status, reply, kind) "
        "VALUES (?,?,?,?,?,?)",
        (feedback_id, tz.now_iso(), actor,
         status, (reply or "").strip() or None, kind))
    if commit:
        conn.commit()


def list_feedback_updates(conn, feedback_id):
    """The phase trail for one submission, oldest first (ack, then each status move)."""
    rows = conn.execute(
        "SELECT ts, actor, status, reply, kind FROM feedback_update "
        "WHERE feedback_id=? ORDER BY id ASC", (feedback_id,)).fetchall()
    return [_feedback_update_row(r) for r in rows]


def create_spot_feedback(conn, *, user_id, submitter, page_url, element_selector,
                         region_json, message):
    """Record one Spot Feedback submission (status defaults to 'New') and seed the
    acknowledgement phase event the submitter sees immediately. Returns its id."""
    cur = conn.execute(
        """INSERT INTO spot_feedback(created_at, user_id, submitter, page_url,
               element_selector, region_json, message, status)
           VALUES (?,?,?,?,?,?,?, 'New')""",
        (tz.now_iso(), user_id, submitter,
         page_url, element_selector or None, region_json or None, message))
    fid = cur.lastrowid
    add_feedback_update(conn, fid, status="New", reply=SPOT_ACK_MESSAGE,
                        kind="ack", actor="system", commit=False)
    conn.commit()
    return fid


def list_spot_feedback(conn, status=None):
    """All submissions, newest first; optionally filtered to one status."""
    if status:
        rows = conn.execute(_SPOT_COLS + " WHERE status = ? ORDER BY id DESC",
                            (status,)).fetchall()
    else:
        rows = conn.execute(_SPOT_COLS + " ORDER BY id DESC").fetchall()
    return [_spot_row(r) for r in rows]


def get_spot_feedback(conn, fid):
    r = conn.execute(_SPOT_COLS + " WHERE id = ?", (fid,)).fetchone()
    return _spot_row(r) if r else None


def update_spot_feedback(conn, fid, *, status, admin_note, severity=None, duplicate_of=None):
    """Triage an entry: set its status + internal note (+ optional severity /
    duplicate-of, Phase 6) and stamp updated_at. The submitter-facing phase
    event (with any reply) is added separately via add_feedback_update so the
    two trails stay distinct."""
    conn.execute(
        "UPDATE spot_feedback SET status=?, admin_note=?, severity=?, duplicate_of=?, "
        "updated_at=? WHERE id=?",
        (status, (admin_note or "").strip() or None, severity or None,
         duplicate_of, tz.now_iso(), fid))
    conn.commit()


def list_user_feedback(conn, user_id):
    """One person's own submissions, newest first — each with its phase trail and
    an `unread` flag (any update newer than when they last viewed). Powers the
    'My feedback' page."""
    rows = [_spot_row(r) for r in conn.execute(
        _SPOT_COLS + " WHERE user_id=? ORDER BY id DESC", (user_id,)).fetchall()]
    for row in rows:
        seen = row["submitter_seen_at"]
        ups = list_feedback_updates(conn, row["id"])
        row["updates"] = ups
        row["unread"] = any((not seen) or (u["ts"] > seen) for u in ups)
        row["archived"] = bool(row["archived_at"])
        # Only a resolved thread can be archived; the rest stay in the active list.
        row["resolved"] = row["status"] in SPOT_RESOLVED_STATUSES
    return rows


def archive_feedback(conn, fid, user_id):
    """Owner-only: move one of the user's own resolved threads into their archived
    section. Scoped by user_id and gated to resolved statuses so a request can never
    archive someone else's thread or hide a still-active one. No-op if it doesn't match."""
    conn.execute(
        "UPDATE spot_feedback SET archived_at=? WHERE id=? AND user_id=? "
        "AND status IN (%s)" % ",".join("?" * len(SPOT_RESOLVED_STATUSES)),
        (tz.now_iso(), fid, user_id, *SPOT_RESOLVED_STATUSES))
    conn.commit()


def unarchive_feedback(conn, fid, user_id):
    """Owner-only: bring an archived thread back into the active list."""
    conn.execute("UPDATE spot_feedback SET archived_at=NULL WHERE id=? AND user_id=?",
                 (fid, user_id))
    conn.commit()


def count_unread_feedback(conn, user_id):
    """How many of the user's submissions have an update they haven't seen yet —
    the nav bell badge. Cheap enough to run on every request that has a session."""
    if not user_id:
        return 0
    row = conn.execute(
        "SELECT COUNT(*) FROM spot_feedback sf WHERE sf.user_id=? AND EXISTS ("
        "  SELECT 1 FROM feedback_update fu WHERE fu.feedback_id=sf.id AND "
        "  (sf.submitter_seen_at IS NULL OR fu.ts > sf.submitter_seen_at))",
        (user_id,)).fetchone()
    return row[0] if row else 0


def mark_feedback_seen(conn, user_id):
    """Stamp all of the user's submissions as seen now — clears their bell badge."""
    conn.execute("UPDATE spot_feedback SET submitter_seen_at=? WHERE user_id=?",
                 (tz.now_iso(), user_id))
    conn.commit()


def spot_feedback_status_counts(conn):
    """{status: count} across all submissions (for the board's filter chips)."""
    rows = conn.execute(
        "SELECT status, COUNT(*) FROM spot_feedback GROUP BY status").fetchall()
    return {r[0]: r[1] for r in rows}


def spot_feedback_history(conn, fid):
    """The audit trail for one submission (creation + every triage), oldest first.
    Drives the timeline on the feedback detail page."""
    rows = conn.execute(
        "SELECT ts, actor, action, summary, before_text, after_text "
        "FROM audit_log WHERE target_type='spot_feedback' AND target_id=? "
        "ORDER BY id ASC", (str(fid),)).fetchall()
    return [{"ts": r[0], "actor": r[1], "action": r[2], "summary": r[3],
             "before": r[4], "after": r[5]} for r in rows]


def add_attendee(conn, event_id, *, name=None, email=None, contact=None,
                 sex=None, affiliation=None, honorific=None, consent_text="", ip=None):
    """Record an attendee's identity + their CONSENT (consent_at = now). Returns
    the new attendee id. Name/email/contact are PII held only here; ratings are
    written separately as anonymous responses. sex (M/F) and affiliation
    (DOH/NON-DOH) are non-PII demographics used only for aggregate reporting.
    honorific (Mr./Ms./Dr./…) is an optional courtesy title for certificates."""
    now = tz.now_iso()
    name = (name or "").strip() or None
    email = (email or "").strip() or None
    contact = (contact or "").strip() or None
    sex = (sex or "").strip().upper() or None
    affiliation = (affiliation or "").strip().upper() or None
    honorific = (honorific or "").strip() or None
    cur = conn.execute(
        """INSERT INTO attendee(event_id, name, email, contact, sex, affiliation,
               honorific, consent_at, consent_text, ip, created_at)
           VALUES (?,?,?,?,?,?,?,?,?,?,?)""",
        (event_id, name, email, contact, sex, affiliation, honorific,
         now, consent_text, ip, now))
    conn.commit()
    return cur.lastrowid


def find_attendee_by_email(conn, event_id, email):
    """Return the existing (non-purged) attendee for this event whose email matches
    `email` case-insensitively, or None. Used so a participant who lost their link
    can re-submit the same email and RESUME their registration instead of creating
    a duplicate. Purged rows (email nulled by retention) never match. If duplicates
    already exist, the earliest (smallest id) wins so resume is deterministic."""
    email = (email or "").strip().lower()
    if not email:
        return None
    row = conn.execute(
        """SELECT id, event_id, name, email, contact, consent_at, purged_at
             FROM attendee
            WHERE event_id=? AND purged_at IS NULL AND email IS NOT NULL
              AND LOWER(email)=?
            ORDER BY id LIMIT 1""",
        (event_id, email)).fetchone()
    if not row:
        return None
    return {"id": row[0], "event_id": row[1], "name": row[2], "email": row[3],
            "contact": row[4], "consent_at": row[5], "purged_at": row[6]}


def update_attendee(conn, attendee_id, *, name=None, contact=None,
                    sex=None, affiliation=None, honorific=None):
    """Refresh an existing attendee's profile fields with the supplied NON-empty
    values (a blank field keeps the stored value — never wipes it). Email, consent_at
    and consent_text are intentionally left untouched: the consent record stays as
    first captured. Used when a participant re-registers (resume) with new details."""
    sets, params = [], []
    for col, val in (("name", name), ("contact", contact),
                     ("sex", sex), ("affiliation", affiliation),
                     ("honorific", honorific)):
        v = (val or "").strip()
        if col in ("sex", "affiliation"):
            v = v.upper()
        if v:
            sets.append(f"{col}=?")
            params.append(v)
    if not sets:
        return
    params.append(attendee_id)
    conn.execute(f"UPDATE attendee SET {', '.join(sets)} WHERE id=?", params)
    conn.commit()


def register_attendee(conn, event_id, *, name=None, email=None, contact=None,
                      sex=None, affiliation=None, honorific=None, consent_text="", ip=None):
    """Dedup-aware registration. If an attendee with the same email already exists
    for this event, RESUME it — refresh non-empty profile fields and return its id —
    instead of inserting a duplicate. Otherwise insert a fresh attendee. Returns
    (attendee_id, resumed) where `resumed` is True when an existing row was reused."""
    existing = find_attendee_by_email(conn, event_id, email)
    if existing:
        update_attendee(conn, existing["id"], name=name, contact=contact,
                        sex=sex, affiliation=affiliation, honorific=honorific)
        return existing["id"], True
    new_id = add_attendee(conn, event_id, name=name, email=email, contact=contact,
                          sex=sex, affiliation=affiliation, honorific=honorific,
                          consent_text=consent_text, ip=ip)
    return new_id, False


def _tally_demo(out, sex, affil):
    """Fold one respondent's sex/affiliation strings into a running tally."""
    s = (sex or "").strip().upper()
    if s in ("M", "MALE"):
        out["male"] += 1
    elif s in ("F", "FEMALE"):
        out["female"] += 1
    a = (affil or "").strip().upper().replace("-", "").replace(" ", "")
    if a == "DOH":
        out["doh"] += 1
    elif a == "NONDOH":
        out["nondoh"] += 1


def demographics_for_responses(conn, response_ids):
    """Tally captured sex (M/F) and affiliation (DOH/NON-DOH) over a set of
    responses — from the consented attendee each response is linked to (Type-2
    pre-registration) and from per-response items (SEX / AFFIL on Type 1/3)."""
    out = {"male": 0, "female": 0, "doh": 0, "nondoh": 0}
    ids = [int(r) for r in response_ids]
    if not ids:
        return out
    ph = ",".join("?" * len(ids))
    for sex, affil in conn.execute(
            f"""SELECT a.sex, a.affiliation FROM response r
                JOIN attendee a ON a.id = r.attendee_id
                WHERE r.id IN ({ph})""", ids).fetchall():
        _tally_demo(out, sex, affil)
    by_resp = {}
    for rid, item, text in conn.execute(
            f"SELECT response_id, item_id, text FROM item_remark "
            f"WHERE item_id IN ('SEX','AFFIL') AND response_id IN ({ph})", ids).fetchall():
        by_resp.setdefault(rid, {})[item] = text
    for d in by_resp.values():
        _tally_demo(out, d.get("SEX"), d.get("AFFIL"))
    return out


def get_activity_demographics(conn, event_id):
    """Manual demographic override for one activity, or {} if none set."""
    row = conn.execute(
        "SELECT male, female, doh, nondoh FROM activity_demographics WHERE event_id=?",
        (event_id,)).fetchone()
    if not row:
        return {}
    return {"male": row[0], "female": row[1], "doh": row[2], "nondoh": row[3]}


def set_activity_demographics(conn, event_id, *, male=None, female=None,
                              doh=None, nondoh=None, by=None):
    """Upsert the manual demographic counts for one activity. Blank/non-numeric
    fields are stored as NULL (so the captured tally shows through for them)."""
    def _n(v):
        v = str(v).strip() if v is not None else ""
        return int(v) if v.isdigit() else None
    now = tz.now_iso()
    conn.execute(
        """INSERT INTO activity_demographics(event_id, male, female, doh, nondoh,
               updated_at, updated_by)
           VALUES (?,?,?,?,?,?,?)
           ON CONFLICT(event_id) DO UPDATE SET
               male=excluded.male, female=excluded.female,
               doh=excluded.doh, nondoh=excluded.nondoh,
               updated_at=excluded.updated_at, updated_by=excluded.updated_by""",
        (event_id, _n(male), _n(female), _n(doh), _n(nondoh), now, by))
    conn.commit()


def get_attendee(conn, attendee_id, event_id=None):
    """Fetch an attendee row (to validate a session). If event_id is given, the
    attendee must belong to that event, else None — stops a link-tree session
    from carrying an attendee id minted for a different event."""
    row = conn.execute(
        "SELECT id, event_id, name, email, contact, consent_at, purged_at, honorific "
        "FROM attendee WHERE id=?", (attendee_id,)).fetchone()
    if not row:
        return None
    if event_id is not None and row[1] != event_id:
        return None
    return {"id": row[0], "event_id": row[1], "name": row[2], "email": row[3],
            "contact": row[4], "consent_at": row[5], "purged_at": row[6],
            "honorific": row[7]}


def delete_attendee_entry(conn, event_id, attendee_id):
    """Permanently remove ONE registrant entry from an event's roster — admin
    cleanup for a test / duplicate / no-show registration.

    REFUSES if the entry has any submitted response. Those ratings are part of the
    reports, and the durable high-water guard treats survey rows (response/answer)
    as append-only — hard-deleting them could lower MAX(rowid) and read as a data
    revert (see backups._HIGHWATER_TABLES). So a responded entry is never
    hard-deleted here (same rule as removing a speaker that already has responses);
    correct it another way or leave it. An entry that never answered touches only
    the attendee table, which is safe to delete.

    Returns one of:
      ('ok', None)            — deleted.
      ('notfound', None)      — id isn't this event's (stale row / wrong event).
      ('hasresponses', n)     — kept; the entry has n responses in the reports.
    """
    row = conn.execute("SELECT id FROM attendee WHERE id=? AND event_id=?",
                       (attendee_id, event_id)).fetchone()
    if not row:
        return "notfound", None
    n = conn.execute("SELECT COUNT(*) FROM response WHERE attendee_id=?",
                     (attendee_id,)).fetchone()[0]
    if n:
        return "hasresponses", n
    conn.execute("DELETE FROM attendee WHERE id=?", (attendee_id,))
    conn.commit()
    return "ok", None


def purge_expired_attendees(conn, cutoff_iso, now_iso=None):
    """RETENTION enforcement: null the PII fields (name/email/contact) of every
    attendee whose consent is older than cutoff_iso and not already purged. The
    row is KEPT (consent_at/consent_text remain as the consent record) and
    purged_at is stamped. Returns the number of rows purged. Ratings are
    untouched — they live in response/answer and were never identifying."""
    now_iso = now_iso or tz.now_iso()
    cur = conn.execute(
        """UPDATE attendee
              SET name=NULL, email=NULL, contact=NULL, purged_at=?
            WHERE consent_at < ? AND purged_at IS NULL""",
        (now_iso, cutoff_iso))
    conn.commit()
    return cur.rowcount


# ---------------------------------------------------------------------
# Registration monitoring — who registered for an event (via the public link
# tree) and how far they have got with its feedback (the CSS). All three
# functions are read-only and derive entirely from existing tables, so they add
# no schema. They cover ONLY the link-tree registration flow: a response carries
# an attendee_id only when it came from a consented /e/<token> session, so
# walk-in / QR / paper responses (attendee_id NULL) are not — and cannot be —
# attributed to a named registrant. event_registration_summary surfaces that
# unattributed count separately so it is never silently dropped.
# ---------------------------------------------------------------------

def _event_form_count(conn, event_id):
    """How many non-archived feedback forms the event has — the denominator for
    'completed'. Archived forms vanish everywhere else, so they don't count here."""
    return conn.execute(
        """SELECT COUNT(*) FROM event_form ef
           JOIN form_instance fi ON fi.id = ef.form_instance_id
           WHERE ef.event_id = ? AND COALESCE(fi.archived, 0) = 0""",
        (event_id,)).fetchone()[0]


def event_attendees_status(conn, event_id):
    """The registration roster for one event: one row per attendee, newest-consent
    last, each with how many of the event's feedback forms they have answered and a
    derived CSS status.

      status = 'completed'   -> answered every non-archived form (n_answered >= n_forms)
               'in_progress' -> answered at least one, but not all
               'not_started' -> registered/consented but has answered nothing yet

    Only an attendee's responses to THIS event's non-archived forms are counted
    (event_form join), so a stray response can't inflate the tally. Purged
    attendees (PII nulled by the retention sweep) keep their row + status but show
    name/email/contact = None — the caller renders them as '(identity removed)'."""
    n_forms = _event_form_count(conn, event_id)
    rows = conn.execute(
        """SELECT a.id, a.name, a.email, a.contact, a.sex, a.affiliation,
                  a.consent_at, a.purged_at,
                  COUNT(DISTINCT CASE
                      WHEN ef.event_id = a.event_id AND COALESCE(fi.archived, 0) = 0
                      THEN r.form_instance_id END) AS answered,
                  MAX(r.submitted_at) AS last_at
           FROM attendee a
           LEFT JOIN response r   ON r.attendee_id = a.id
           LEFT JOIN event_form ef ON ef.form_instance_id = r.form_instance_id
           LEFT JOIN form_instance fi ON fi.id = r.form_instance_id
           WHERE a.event_id = ?
           GROUP BY a.id
           ORDER BY a.consent_at, a.id""",
        (event_id,)).fetchall()
    out = []
    for r in rows:
        answered = r[8] or 0
        if answered <= 0:
            status = "not_started"
        elif n_forms and answered >= n_forms:
            status = "completed"
        else:
            status = "in_progress"
        out.append({
            "id": r[0], "name": r[1], "email": r[2], "contact": r[3],
            "sex": r[4], "affiliation": r[5], "consent_at": r[6],
            "purged": bool(r[7]), "n_answered": answered, "n_forms": n_forms,
            "status": status, "last_submitted_at": r[9],
        })
    return out


def event_registration_summary(conn, event_id):
    """Headline counts for an event's registration monitor: how many registered,
    and of those how many completed / are in progress / have not started, plus the
    completion rate. unattributed = responses to this event's forms that carry no
    registrant (walk-in/QR/paper) — surfaced so the funnel never hides them.

    completion_rate has TWO modes, driven by the activity's respondent_target:
      - No override (respondent_target is NULL): the rate is computed over EVERYONE
        who took part, not just the pre-registered roster — the denominator is the
        registered roster PLUS the not-pre-registered responses, and each of those
        walk-in/QR/paper responses is itself treated as a completed submission (it
        is already an answer that came in). So it is
        (completed + unattributed) / (registered + unattributed): a walk-in helps
        rather than hurts, and 100% is reached exactly when no REGISTERED person is
        left unfinished (the extra unattributed term cancels in that case).
      - Override set: the manager's entered respondent count is the denominator and
        the numerator still counts walk-ins — (completed + unattributed) / target —
        so an activity whose real attendance the roster never captured still reads
        honestly. denominator_source tells the UI which mode is live.

    NOTE (multi-form activities): 'unattributed' is a raw response-row count, so a
    walk-in who answers two forms counts as two. For the common single-form
    activity it equals people; treat the override numerator as approximate when an
    activity has several forms."""
    people = event_attendees_status(conn, event_id)
    registered = len(people)
    completed = sum(1 for p in people if p["status"] == "completed")
    in_progress = sum(1 for p in people if p["status"] == "in_progress")
    not_started = sum(1 for p in people if p["status"] == "not_started")
    unattributed = conn.execute(
        """SELECT COUNT(*) FROM response r
           JOIN event_form ef ON ef.form_instance_id = r.form_instance_id
           WHERE ef.event_id = ? AND r.attendee_id IS NULL""",
        (event_id,)).fetchone()[0]
    target = conn.execute(
        "SELECT respondent_target FROM event WHERE id = ?", (event_id,)).fetchone()[0]
    if target:
        completion_rate = _completion_rate_target(completed + unattributed, target)
        denominator_source = "target"
    else:
        # Everyone who took part: walk-ins fold into both sides (see docstring).
        completion_rate = _completion_rate(completed + unattributed,
                                           registered + unattributed)
        denominator_source = "registered"
    return {
        "n_forms": _event_form_count(conn, event_id),
        "registered": registered, "completed": completed,
        "in_progress": in_progress, "not_started": not_started,
        "answered_any": completed + in_progress,
        "completion_rate": completion_rate,
        "unattributed": unattributed,
        "respondent_target": target,
        "denominator_source": denominator_source,
    }


def _completion_rate(done, total):
    """Completion as a whole-number percent from a `done`-out-of-`total` count, with
    the invariant the Monitor cards rely on: it is None when `total` is 0, exactly
    100 only when `done >= total` (everyone counted has finished), and otherwise
    strictly below 100 — a near-complete event (e.g. 199/200) reads 99%, never
    rounding up to a misleading 100%. Callers pass `done <= total`, so the rate is
    always in [0, 100]."""
    if not total:
        return None
    if done >= total:
        return 100
    return min(99, round(done * 100 / total))


def _completion_rate_target(numerator, target):
    """Completion percent against a manager-entered respondent target. None when
    the target is falsy (no denominator to divide by). Clamped to [0, 100] as a
    defensive net: the save path rejects a target below the current respondent
    count, but later responses can still push the numerator past a once-valid
    target, and the card must never read above 100%."""
    if not target:
        return None
    return min(100, round(numerator * 100 / target))


def attendee_response_detail(conn, event_id, attendee_id):
    """Read-only: one link-tree registrant's OWN responses to this event's
    non-archived forms — the data sitting behind their CSS status on the Monitor
    roster. Returns a list, in link-tree order, of:

        {response_id, form_instance_id, qr_token, form, survey_type, topic,
         submitted_at,
         answers: {item_id: {"value": float|None, "is_na": bool}},
         item_remarks: {item_id: text},
         remark: overall free-text comment or None}

    Only rows carrying THIS attendee_id are returned, so it reflects solely what
    this consented registrant submitted. Anonymous walk-in / QR / paper responses
    (attendee_id NULL) are not attributable to anyone and never appear here.
    Empty when the attendee has answered nothing (or attendee_id is falsy)."""
    if not attendee_id:
        return []
    rows = conn.execute(
        """SELECT r.id, r.form_instance_id, r.submitted_at, r.remarks,
                  fi.qr_token, fi.form, fi.survey_type, fi.topic
           FROM response r
           JOIN event_form ef     ON ef.form_instance_id = r.form_instance_id
           JOIN form_instance fi  ON fi.id = r.form_instance_id
           WHERE ef.event_id = ? AND r.attendee_id = ?
                 AND COALESCE(fi.archived, 0) = 0
           ORDER BY ef.ordinal, r.submitted_at, r.id""",
        (event_id, attendee_id)).fetchall()
    out = []
    for (rid, fiid, submitted, remark, qr_token, form, stype, topic) in rows:
        answers = {item_id: {"value": value, "is_na": bool(is_na)}
                   for (item_id, value, is_na) in conn.execute(
                       "SELECT item_id, value, is_na FROM answer WHERE response_id=?",
                       (rid,))}
        item_remarks = {item_id: text for (item_id, text) in conn.execute(
            "SELECT item_id, text FROM item_remark WHERE response_id=?", (rid,))}
        out.append({
            "response_id": rid, "form_instance_id": fiid, "qr_token": qr_token,
            "form": form, "survey_type": stype, "topic": topic,
            "submitted_at": submitted, "answers": answers,
            "item_remarks": item_remarks, "remark": remark,
        })
    return out


def event_in_team_scope(ev, scope_path):
    """Is this activity the viewer's team's, for the MANAGEMENT feeds?

    The same rule the landing card uses: the ORGANISING unit is inside the
    scope, or one of the team spoke at it. `created_by` is deliberately not part
    of it — it records who filled in the form, which is a fact about the app
    rather than about whose work the activity was, and an administrator files
    activities for sections all over the bureau.

    The speaker half is not a nicety here, it is the only thing that can answer
    for an INVITED (outside) activity: those are created with no organising unit
    at all — neither the event row nor its Form 3s carry one, because the
    organiser is an external body. The section whose person was invited is the
    section that owns the engagement, which is also the right answer.

    A None scope_path is bureau-wide and lets everything through (_path_in_scope).
    """
    if _path_in_scope(ev.get("lead_path"), scope_path):
        return True
    return any(_path_in_scope(p, scope_path) for p in (ev.get("rp_paths") or ()))


def list_events(conn, created_by=None, lifecycles=None, team_scope=None):
    """Events newest-first for the monitor index, each enriched with its form count,
    registration funnel (registered / completed / in progress / not started) and its
    `lifecycle` (upcoming / ongoing / concluded — see lifecycle_of).
    created_by, when given, limits the list to events a particular manager created.
    lifecycles, when given (e.g. {'upcoming','ongoing'}),
    keeps only events in those states — the strict rule keeps the monitor list to
    activities still worth monitoring.
    team_scope, when given, is the (scope_path, kind) pair from
    team_scope_for_user: rows outside that team are dropped by
    event_in_team_scope. It is applied BEFORE the per-event rollups, so the
    expensive work stays proportional to what is actually shown. Per-event
    rollups reuse event_registration_summary — fine at the bureau's event volume
    and keeps the 'completed' rule in one place."""
    where, args = "", ()
    if created_by:
        where, args = "WHERE e.created_by = ?", (created_by,)
    today = today_local(conn)
    now = tz.now_iso()   # Manila clock (see tzutil), not SQLite 'localtime' (UTC container)
    rows = conn.execute(
        f"""SELECT e.id, e.event_token, e.title, e.event_date, e.venue,
                   e.organizer, e.modality, e.created_by,
                   (SELECT fi.close_at FROM event_form ef
                      JOIN form_instance fi ON fi.id = ef.form_instance_id
                      WHERE ef.event_id = e.id AND fi.survey_type = 2 LIMIT 1) AS close_at,
                   e.event_kind, e.end_date, olead.path,
                   -- the home units of the INTERNAL people who spoke at it, which
                   -- is all an invited activity has to be scoped by. Paths never
                   -- contain a comma, so the concat is safe to split.
                   (SELECT group_concat(DISTINCT ou.path) FROM event_form ef2
                      JOIN form_instance fi2 ON fi2.id = ef2.form_instance_id
                      JOIN resource_person rp ON rp.id = fi2.rp_id
                      JOIN org_unit ou ON ou.id = rp.org_unit_id
                     WHERE ef2.event_id = e.id AND COALESCE(rp.is_internal, 0) = 1)
            FROM event e
            LEFT JOIN org_unit olead ON olead.id = e.lead_org_id
            {where}
            ORDER BY date(e.event_date) DESC, e.id DESC""",
        args).fetchall()
    out = []
    for r in rows:
        life = lifecycle_of(r[3], r[8], today, now, end_date=r[10])
        if lifecycles and life not in lifecycles:
            continue
        ev = {
            "id": r[0], "event_token": r[1], "title": r[2], "event_date": r[3],
            "end_date": r[10], "venue": r[4], "organizer": r[5], "modality": r[6] or "f2f",
            "created_by": r[7], "lifecycle": life, "event_kind": r[9] or "bureau",
            "lead_path": r[11],
            "rp_paths": [p for p in (r[12] or "").split(",") if p],
        }
        if team_scope and not event_in_team_scope(ev, team_scope[0]):
            continue
        out.append({**ev, **event_registration_summary(conn, r[0])})
    return out


def count_attendees(conn, event_id=None):
    """How many attendees were captured (optionally for one event)."""
    if event_id is None:
        return conn.execute("SELECT COUNT(*) FROM attendee").fetchone()[0]
    return conn.execute("SELECT COUNT(*) FROM attendee WHERE event_id=?",
                        (event_id,)).fetchone()[0]


# ---------------------------------------------------------------------
# Lookups + seeding for the form-creation screen
# ---------------------------------------------------------------------

# The bureau that owns this app. Bureau-organized events are auto-attributed
# to it (internal organizer), shown locked, never typed by a rater.
BLHSD_NAME = "BLHSD"
BLHSD_PATH = "BLHSD"


def get_or_create_blhsd(conn):
    """Return (id, name, path) for the bureau treated as the internal organizer.

    Reuses an existing bureau-level org_unit if one is present (so the demo's
    'Bureau' keeps working); otherwise creates 'BLHSD'.
    """
    row = conn.execute(
        "SELECT id, name, path FROM org_unit WHERE level='bureau' ORDER BY id LIMIT 1"
    ).fetchone()
    if row:
        return row[0], row[1], row[2]
    new_id = add_org_unit(conn, BLHSD_NAME, "bureau", BLHSD_PATH)
    return new_id, BLHSD_NAME, BLHSD_PATH


def get_or_create_walkin_form(conn):
    """The single, permanent bureau-wide walk-in (ARTA) form.

    It is NOT created per transaction: one standing form_instance whose QR/link
    stays posted and is filled by every walk-in or online client. It carries no
    baked staff/service/date -- each response supplies its own submission date
    (the period) and its own 'who served you' pick (the attribution). Returns
    {id, qr_token, form_id}.
    """
    row = conn.execute("""
        SELECT id, qr_token FROM form_instance
        WHERE survey_type=1 AND form='F1'
          AND serving_staff IS NULL AND serving_staff_org_id IS NULL
          AND service IS NULL AND lead_org_id IS NULL
        ORDER BY id LIMIT 1
    """).fetchone()
    if row:
        fid, token = row
    else:
        opened = tz.now_local().date().isoformat()
        fid = create_form_instance(conn, survey_type=1, form="F1", event_date=opened)
        token = conn.execute("SELECT qr_token FROM form_instance WHERE id=?", (fid,)).fetchone()[0]
    return {"id": fid, "qr_token": token, "form_id": f"F1-WALKIN-{fid:04d}"}


def list_org_units(conn, level=None):
    """Org units for the section pickers (e.g. the ARTA 'who served' section).
    Pass level='section' to list only sections."""
    sql = "SELECT id, name, short_name, level, path FROM org_unit"
    args = ()
    if level is not None:
        sql += " WHERE level=?"
        args = (level,)
    sql += " ORDER BY path"
    return [{"id": r[0], "name": r[1], "short_name": r[2], "level": r[3], "path": r[4]}
            for r in conn.execute(sql, args).fetchall()]


def update_org_unit(conn, unit_id, name=None, short_name=None):
    if name is not None:
        conn.execute("UPDATE org_unit SET name=? WHERE id=?", (name, unit_id))
    if short_name is not None:
        conn.execute("UPDATE org_unit SET short_name=? WHERE id=?", (short_name, unit_id))
    conn.commit()


def org_structure(conn):
    """The organogram shaped for the directory UI:
        {bureau, directorate, divisions:[{... , sections:[...]}], admin_sections:[...]}
    A section's parent is found from its path; sections whose parent is the
    bureau (no division) are the administrative sections. The Office of the
    Director (level 'office') is the head office that sits ABOVE the divisions —
    the whole bureau rolls up to it — so it is surfaced separately as the
    `directorate`, NOT lumped with the administrative sections."""
    units = list_org_units(conn)
    by_path = {u["path"]: u for u in units}
    bureau = next((u for u in units if u["level"] == "bureau"), None)
    directorate = next((u for u in units if u["level"] == "office"), None)

    def parent(u):
        return by_path.get(u["path"].rsplit("/", 1)[0]) if "/" in u["path"] else None

    divisions = [dict(u, sections=[]) for u in units if u["level"] == "division"]
    div_by_path = {d["path"]: d for d in divisions}
    admin_sections = []
    for u in units:
        if u["level"] != "section":
            continue
        par = parent(u)
        if par and par["path"] in div_by_path:
            div_by_path[par["path"]]["sections"].append(u)
        else:
            admin_sections.append(u)        # directly under bureau => administrative
    return {"bureau": bureau, "directorate": directorate,
            "divisions": divisions, "admin_sections": admin_sections}


def org_unit_deletable(conn, unit_id):
    """A unit can be removed only if nothing hangs off it: no child units, no
    staff assigned, and no survey bound to it. Returns (ok, reason)."""
    row = conn.execute("SELECT path FROM org_unit WHERE id=?", (unit_id,)).fetchone()
    if not row:
        return False, "not found"
    path = row[0]
    if conn.execute("SELECT 1 FROM org_unit WHERE path LIKE ? LIMIT 1", (path + "/%",)).fetchone():
        return False, "has child units"
    if conn.execute("SELECT 1 FROM resource_person WHERE org_unit_id=? LIMIT 1", (unit_id,)).fetchone():
        return False, "has staff assigned"
    if conn.execute("""SELECT 1 FROM form_instance
                       WHERE serving_staff_org_id=? OR lead_org_id=? LIMIT 1""",
                    (unit_id, unit_id)).fetchone():
        return False, "used by a survey"
    return True, ""


def delete_org_unit(conn, unit_id):
    ok, reason = org_unit_deletable(conn, unit_id)
    if not ok:
        return False, reason
    conn.execute("DELETE FROM org_unit WHERE id=?", (unit_id,))
    conn.commit()
    return True, ""


def clear_sample_data(conn):
    """Wipe all directory + survey data for a fresh start, then recreate the
    bureau root. Schema is untouched."""
    for tbl in ("item_remark", "answer", "response", "form_instance",
                "resource_person", "external_organizer", "org_unit"):
        conn.execute(f"DELETE FROM {tbl}")
    conn.commit()
    get_or_create_blhsd(conn)


def list_resource_persons(conn, include_archived=False):
    """All people who can be picked as a speaker: internal staff + external RPs.

    Returns dicts so a template can show the source. RP source per the spec is
    internal staff (directory) AND external RPs (registry) -- both live in the
    resource_person table, split by is_internal.

    ARCHIVED PEOPLE ARE OUT BY DEFAULT. Someone who has left the bureau must not
    be offerable as this week's speaker, served-by or certificate signatory, and
    the default is what every picker gets, so the safe answer is the one you get
    without thinking about it. Pass include_archived=True where the list is used
    to RESOLVE HISTORY rather than to choose someone now — get_rp, the People
    grid, participation and the exports all have to keep naming a person whose
    ratings are still on the record. `archived` rides along on every dict so
    those callers can label the row instead of dropping it.
    """
    rows = conn.execute(f"""
        SELECT rp.id, rp.name, rp.is_internal, rp.org_unit_id, ou.path,
               rp.photo IS NOT NULL, rp.position, rp.designation,
               rp.focus_area, rp.email, rp.employment_type, rp.hidden_public,
               rp.honorific, rp.agency, rp.signature IS NOT NULL,
               rp.archived_at, rp.archived_reason
        FROM resource_person rp
        LEFT JOIN org_unit ou ON ou.id = rp.org_unit_id
        {"" if include_archived else "WHERE rp.archived_at IS NULL"}
        ORDER BY rp.is_internal DESC, rp.name
    """).fetchall()
    return [{"id": r[0], "name": r[1], "is_internal": bool(r[2]),
             "org_unit_id": r[3], "org_path": r[4], "has_photo": bool(r[5]),
             "position": r[6], "designation": r[7], "focus_area": r[8],
             "email": r[9], "employment_type": r[10], "hidden_public": bool(r[11]),
             "honorific": r[12], "agency": r[13], "has_signature": bool(r[14]),
             "archived": bool(r[15]), "archived_at": r[15], "archived_reason": r[16]}
            for r in rows]


# A certificate may only be signed by the bureau's signing authorities: a
# Section Chief, a Division Chief, or the Director. Everyone else in the
# directory never needs a signature on file. The functional role lives in
# `designation` ("Section Head"/"Division Chief"); the Director carries no
# designation — the title sits in `position` ("Director IV").
_SIGNATORY_DESIGNATIONS = {"section head", "section chief", "division chief"}
# Sort rank for the picker: Director first, then Division Chief, then Section
# Chief, then anything else that slipped through.
_SIGNATORY_RANK = {"director": 0, "division chief": 1,
                   "section head": 2, "section chief": 2}


def is_bureau_director(person):
    """True if this directory person currently holds the Director role — i.e.
    the bureau head, whoever that is at any given time (the role turns over
    faster than anyone remembers to re-flag a new occupant by hand). Same
    'director' in position/designation match as is_eligible_signatory, used
    to automatically exclude the Director from per-person CSS rankings and
    reports — a standing rule, not a per-person toggle, so it never needs to
    be re-applied when the Director changes. `person` is a
    list_resource_persons() dict (or anything carrying position/designation)."""
    desig = (person.get("designation") or "").strip().lower()
    posn = (person.get("position") or "").strip().lower()
    return "director" in posn or "director" in desig


def is_eligible_signatory(person):
    """True if a directory person may sign a Certificate of Appearance — i.e.
    they hold a Section Chief, Division Chief, or Director role. `person` is a
    list_resource_persons() dict. Matching is case-insensitive; the Director is
    detected by 'director' appearing in the position (e.g. 'Director IV')."""
    if not person.get("is_internal"):
        return False
    desig = (person.get("designation") or "").strip().lower()
    posn = (person.get("position") or "").strip().lower()
    if desig in _SIGNATORY_DESIGNATIONS:
        return True
    return "director" in posn or "director" in desig


def _signatory_rank(person):
    desig = (person.get("designation") or "").strip().lower()
    posn = (person.get("position") or "").strip().lower()
    if "director" in posn or "director" in desig:
        return 0
    return _SIGNATORY_RANK.get(desig, 3)


def list_signatories(conn):
    """The directory people eligible to sign a certificate (see
    is_eligible_signatory), ordered by signing rank then name."""
    people = [p for p in list_resource_persons(conn) if is_eligible_signatory(p)]
    people.sort(key=lambda p: (_signatory_rank(p), (p.get("name") or "").lower()))
    return people


def get_signatory(conn, rp_id):
    """Resolve a certificate signatory (a directory person) to the fields a
    certificate needs: full name, an honorific-prefixed display name, the title
    line (position / designation), and the signature image bytes if any. Returns
    None if rp_id is falsy or the person no longer exists."""
    if not rp_id:
        return None
    rp = get_rp(conn, rp_id)
    if not rp:
        return None
    name = (rp.get("name") or "").strip()
    hon = (rp.get("honorific") or "").strip()
    display = f"{hon} {name}".strip() if hon and not name.lower().startswith(hon.lower()) else name
    title = (rp.get("position") or rp.get("designation") or "").strip()
    sig = get_rp_signature(conn, rp_id)
    return {"id": rp_id, "name": name, "display_name": display, "title": title,
            "has_signature": sig is not None,
            "signature_bytes": sig[0] if sig else None,
            "signature_mime": sig[1] if sig else None}


def set_rp_hidden(conn, rp_id, hidden):
    """Admin toggle: hide (or unhide) one person's scores from the public People
    view. Stored as a flag on the record — the person still appears as an event
    organizer/speaker name elsewhere; only their People-view card is affected."""
    conn.execute("UPDATE resource_person SET hidden_public=? WHERE id=?",
                 (1 if hidden else 0, rp_id))
    conn.commit()


def get_rp(conn, rp_id):
    """Full record for one person (the directory edit page). Resolves ARCHIVED
    people too: every certificate, rating and approval trail that already names
    someone has to keep resolving after they leave."""
    people = list_resource_persons(conn, include_archived=True)
    return next((p for p in people if p["id"] == rp_id), None)


# ---------------------------------------------------------------------
# UX telemetry — passive interface-friction signal (see ui_event in init_db
# above + ui_telemetry.py for the vocabulary/sanitizers). Written best-effort,
# batched, from POST /telemetry; read back for the future ranked digest.
# ---------------------------------------------------------------------

def create_ui_events(conn, events):
    """Insert a batch of already-sanitized UX telemetry events (each a dict with
    user_id, role, session_id, event_type, route, component, element_selector,
    element_text, meta). Caller has already re-sanitized server-side — this just
    stores the rows. One shared created_at per batch (they all arrived together)."""
    if not events:
        return
    ts = tz.now_iso()
    conn.executemany(
        """INSERT INTO ui_event(created_at, user_id, role, session_id, event_type,
               route, component, element_selector, element_text, meta_json)
           VALUES (?,?,?,?,?,?,?,?,?,?)""",
        [(ts, e.get("user_id"), e.get("role"), e["session_id"], e["event_type"],
          e["route"], e.get("component"), e.get("element_selector"),
          e.get("element_text"), json.dumps(e["meta"]) if e.get("meta") else None)
         for e in events])
    conn.commit()


def _ui_event_row(r):
    try:
        meta = json.loads(r[10]) if r[10] else None
    except ValueError:
        meta = None
    return {"id": r[0], "created_at": r[1], "user_id": r[2], "role": r[3],
            "session_id": r[4], "event_type": r[5], "route": r[6],
            "component": r[7], "element_selector": r[8], "element_text": r[9],
            "meta": meta}


def list_ui_events(conn, since=None, limit=500):
    """UX telemetry events, newest first. `since` (an ISO timestamp, same naive
    local format as created_at) scopes to a rolling window — the ux_insights
    digest passes one; a plain read-back for debugging omits it. meta_json is
    parsed back into `meta`."""
    sql = ("SELECT id, created_at, user_id, role, session_id, event_type, route, "
           "component, element_selector, element_text, meta_json FROM ui_event")
    params = []
    if since:
        sql += " WHERE created_at >= ?"
        params.append(since)
    sql += " ORDER BY id DESC LIMIT ?"
    params.append(limit)
    rows = conn.execute(sql, params).fetchall()
    return [_ui_event_row(r) for r in rows]


def purge_stale_ui_events(conn, cutoff_iso):
    """RETENTION enforcement for passive UX telemetry: delete every ui_event row
    older than cutoff_iso. Unlike attendee PII (purge_expired_attendees), there
    is no consent record to keep — this is behavioral data, not audit-of-record,
    so the row is simply gone. Returns the number of rows deleted."""
    cur = conn.execute("DELETE FROM ui_event WHERE created_at < ?", (cutoff_iso,))
    conn.commit()
    return cur.rowcount


# ---------------------------------------------------------------------
# AI interaction log + budget (docs/AI_INTEGRATION_PLAN.md Phase 0; see
# ai_interaction/ai_budget in init_db above and ai_core.py for the caller).
# ---------------------------------------------------------------------

def create_ai_interaction(conn, *, user_id=None, role=None, feature, mode, model=None,
                          prompt_masked=None, response_masked=None, outcome,
                          destination=None, confidence=None, latency_ms=None,
                          tokens_in=None, tokens_out=None, error=None, provider=None,
                          question_norm=None):
    ts = tz.now_iso()
    cur = conn.execute(
        """INSERT INTO ai_interaction(created_at, user_id, role, feature, mode, model,
               prompt_masked, response_masked, outcome, destination, confidence,
               latency_ms, tokens_in, tokens_out, error, provider, question_norm)
           VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
        (ts, user_id, role, feature, mode, model, prompt_masked, response_masked,
         outcome, destination, confidence, latency_ms, tokens_in, tokens_out, error,
         provider, question_norm))
    conn.commit()
    return cur.lastrowid


def update_ai_interaction_outcome(conn, interaction_id, outcome, *, destination=None,
                                  confidence=None, feature=None):
    """Let a feature backfill router-only columns (destination/confidence) and/or
    override the outcome ai_core.ask() already logged — used by the NL router
    (docs/AI_INTEGRATION_PLAN.md Phase 1) when its own server-side validation
    rejects an otherwise-successful model response (unknown destination, or
    confidence below the floor): the call reached Gemini fine, but the answer
    isn't trusted, so the log should read rejected_validation, not ok.

    `feature` reclassifies the logged feature after the fact — the single NL
    router call is always billed/rate-limited under "nl_router" (it's one
    physical Gemini call regardless of which `kind` it resolves to), but Phase
    2's answer/help resolutions correct the log's feature column to
    "nl_answer"/"nl_help" so /admin/ai's per-feature browser can tell them
    apart from a plain navigation."""
    conn.execute(
        "UPDATE ai_interaction SET outcome=?, destination=COALESCE(?, destination), "
        "confidence=COALESCE(?, confidence), feature=COALESCE(?, feature) WHERE id=?",
        (outcome, destination, confidence, feature, interaction_id))
    conn.commit()


def set_ai_feedback(conn, interaction_id, user_id, rating, comment=None, is_admin=False):
    """Record 👍(1)/👎(-1) on an interaction, the per-use signal the AI plan
    relies on to diagnose misbehavior from logs. Row-ownership check: only the
    user the interaction was logged for may rate it, unless `is_admin`.
    Returns True if a row was updated, False if not found / not owned."""
    row = conn.execute("SELECT user_id FROM ai_interaction WHERE id=?",
                       (interaction_id,)).fetchone()
    if not row or (not is_admin and row[0] != user_id):
        return False
    cur = conn.execute(
        "UPDATE ai_interaction SET rating=?, rating_comment=?, rated_at=? WHERE id=?",
        (rating, comment, tz.now_iso(), interaction_id))
    conn.commit()
    return cur.rowcount > 0


def _ai_interaction_row(r):
    return {"id": r[0], "created_at": r[1], "user_id": r[2], "role": r[3],
            "feature": r[4], "mode": r[5], "model": r[6],
            "prompt_masked": r[7], "response_masked": r[8], "outcome": r[9],
            "destination": r[10], "confidence": r[11], "latency_ms": r[12],
            "tokens_in": r[13], "tokens_out": r[14], "error": r[15],
            "rating": r[16], "rating_comment": r[17], "rated_at": r[18],
            "provider": r[19] or "gemini", "question_norm": r[20]}


def list_ai_interactions(conn, feature=None, outcome=None, rating=None, since=None, limit=200):
    """AI interaction log, newest first — the diagnose-from-user-feedback
    surface on /admin/ai. Any of feature/outcome/rating/since narrows it."""
    sql = ("SELECT id, created_at, user_id, role, feature, mode, model, prompt_masked, "
           "response_masked, outcome, destination, confidence, latency_ms, tokens_in, "
           "tokens_out, error, rating, rating_comment, rated_at, provider, question_norm "
           "FROM ai_interaction")
    where, params = [], []
    if feature:
        where.append("feature=?"); params.append(feature)
    if outcome:
        where.append("outcome=?"); params.append(outcome)
    if rating is not None:
        where.append("rating=?"); params.append(rating)
    if since:
        where.append("created_at >= ?"); params.append(since)
    if where:
        sql += " WHERE " + " AND ".join(where)
    sql += " ORDER BY id DESC LIMIT ?"
    params.append(limit)
    rows = conn.execute(sql, params).fetchall()
    return [_ai_interaction_row(r) for r in rows]


def purge_stale_ai_interactions(conn, cutoff_iso):
    """RETENTION enforcement for the AI interaction log — same shape as
    purge_stale_ui_events: behavioral/operational data, not audit-of-record."""
    cur = conn.execute("DELETE FROM ai_interaction WHERE created_at < ?", (cutoff_iso,))
    conn.commit()
    return cur.rowcount


def purge_stale_ai_budget(conn, cutoff_day):
    """ai_budget rows are keyed by calendar day (a 'YYYY-MM-DD' string, not a
    timestamp) — cutoff_day must be the same shape. Old daily-spend rows are
    pure clutter once their day has passed retention; nothing reads them."""
    cur = conn.execute("DELETE FROM ai_budget WHERE day < ?", (cutoff_day,))
    conn.commit()
    return cur.rowcount


# ---------------------------------------------------------------------
# Learned rules — the deterministic FAQ layer in front of the NL router
# (qa_rules.py + app.py's _ai_try_rules). A rule maps a normalized question to
# a {kind, target_key} the router already knows how to render server-side, so a
# hit answers with zero AI spend. See the learned_rule table in
# _add_missing_columns above.
# ---------------------------------------------------------------------

_LEARNED_RULE_COLS = ("SELECT id, pattern, keywords, sample_query, kind, target_key, "
                      "enabled, source, hits, last_hit_at, notes, created_by, "
                      "created_at, updated_at FROM learned_rule")


def _learned_rule_row(r):
    return {"id": r[0], "pattern": r[1], "keywords": r[2], "sample_query": r[3],
            "kind": r[4], "target_key": r[5], "enabled": bool(r[6]), "source": r[7],
            "hits": r[8], "last_hit_at": r[9], "notes": r[10], "created_by": r[11],
            "created_at": r[12], "updated_at": r[13]}


def create_learned_rule(conn, *, pattern, kind, target_key, keywords=None,
                        sample_query=None, source="manual", enabled=True,
                        notes=None, created_by=None):
    """Add one FAQ rule. `pattern` should already be normalized
    (qa_rules.normalize). Idempotent on (kind, target_key, pattern): a repeat
    insert (e.g. re-seeding on startup) is ignored and returns the existing id
    rather than raising on the unique index. Returns the rule id, or None if
    the row existed and couldn't be re-read."""
    now = tz.now_iso()
    conn.execute(
        """INSERT OR IGNORE INTO learned_rule(pattern, keywords, sample_query, kind,
               target_key, enabled, source, hits, notes, created_by, created_at, updated_at)
           VALUES (?,?,?,?,?,?,?,0,?,?,?,?)""",
        (pattern, (keywords or "").strip() or None, sample_query, kind, target_key,
         1 if enabled else 0, source, (notes or "").strip() or None, created_by, now, now))
    conn.commit()
    row = conn.execute("SELECT id FROM learned_rule WHERE kind=? AND target_key=? AND pattern=?",
                       (kind, target_key, pattern)).fetchone()
    return row[0] if row else None


def list_learned_rules(conn, enabled=None):
    """All rules, most-hit first then newest — the admin board order. `enabled`
    (True/False) narrows to just the live or just the paused ones; the route's
    matcher passes enabled=True so a paused rule never serves."""
    sql = _LEARNED_RULE_COLS
    params = []
    if enabled is not None:
        sql += " WHERE enabled=?"
        params.append(1 if enabled else 0)
    sql += " ORDER BY hits DESC, id DESC"
    return [_learned_rule_row(r) for r in conn.execute(sql, params).fetchall()]


def get_learned_rule(conn, rid):
    r = conn.execute(_LEARNED_RULE_COLS + " WHERE id=?", (rid,)).fetchone()
    return _learned_rule_row(r) if r else None


def update_learned_rule(conn, rid, *, pattern=None, keywords=None, kind=None,
                        target_key=None, enabled=None, notes=None):
    """Edit one rule in place (any subset of fields) and stamp updated_at. Only
    provided fields change — mirrors the COALESCE-by-arg style used elsewhere.
    Returns True if a row was updated."""
    sets, params = [], []
    if pattern is not None:
        sets.append("pattern=?"); params.append(pattern)
    if keywords is not None:
        sets.append("keywords=?"); params.append((keywords or "").strip() or None)
    if kind is not None:
        sets.append("kind=?"); params.append(kind)
    if target_key is not None:
        sets.append("target_key=?"); params.append(target_key)
    if enabled is not None:
        sets.append("enabled=?"); params.append(1 if enabled else 0)
    if notes is not None:
        sets.append("notes=?"); params.append((notes or "").strip() or None)
    if not sets:
        return False
    sets.append("updated_at=?"); params.append(tz.now_iso())
    params.append(rid)
    cur = conn.execute("UPDATE learned_rule SET " + ", ".join(sets) + " WHERE id=?", params)
    conn.commit()
    return cur.rowcount > 0


def delete_learned_rule(conn, rid):
    cur = conn.execute("DELETE FROM learned_rule WHERE id=?", (rid,))
    conn.commit()
    return cur.rowcount > 0


def bump_learned_rule_hit(conn, rid):
    """Record that a rule just answered a question (its whole point: one more
    question served without an AI call). Increments hits + stamps last_hit_at."""
    conn.execute("UPDATE learned_rule SET hits=hits+1, last_hit_at=? WHERE id=?",
                 (tz.now_iso(), rid))
    conn.commit()


def top_questions(conn, since=None, limit=50):
    """Candidate feed for the /admin/rules 'promote' panel: model-answered
    questions grouped by their normalized text, most-asked first. Only rows the
    model actually resolved (outcome='ok', a real destination/feature) and that
    the rules layer did NOT already serve (provider != 'rules') — those are the
    questions worth turning into a zero-cost rule. Each group carries its
    dominant destination + feature + a rough confidence/rating read so an admin
    can promote with the right target pre-filled. Excludes questions that
    already have a matching rule pattern."""
    where = ["question_norm IS NOT NULL", "question_norm != ''",
             "outcome = 'ok'", "(provider IS NULL OR provider != 'rules')"]
    params = []
    if since:
        where.append("created_at >= ?"); params.append(since)
    # One flat fetch, then aggregate in Python — cheaper to reason about than a
    # window-function query and portable across SQLite versions.
    rows = conn.execute(
        "SELECT question_norm, confidence, rating, destination, feature "
        "FROM ai_interaction WHERE " + " AND ".join(where) +
        " ORDER BY id DESC", params).fetchall()
    agg = {}
    for qn, conf, rating, dest, feat in rows:
        g = agg.get(qn)
        if g is None:
            g = agg[qn] = {"question": qn, "count": 0, "conf_sum": 0.0, "conf_n": 0,
                           "net_rating": 0, "dests": {}, "feats": {}}
        g["count"] += 1
        if conf is not None:
            g["conf_sum"] += conf; g["conf_n"] += 1
        if rating:
            g["net_rating"] += rating
        if dest:
            g["dests"][dest] = g["dests"].get(dest, 0) + 1
        if feat:
            g["feats"][feat] = g["feats"].get(feat, 0) + 1
    out = []
    have = {r[0] for r in conn.execute("SELECT pattern FROM learned_rule")}
    for qn, g in agg.items():
        if qn in have:
            continue                                   # already a rule — not a candidate
        dest = max(g["dests"], key=g["dests"].get) if g["dests"] else None
        feat = max(g["feats"], key=g["feats"].get) if g["feats"] else None
        out.append({
            "question": qn, "count": g["count"],
            "avg_confidence": (g["conf_sum"] / g["conf_n"]) if g["conf_n"] else None,
            "net_rating": g["net_rating"], "destination": dest, "feature": feat})
    out.sort(key=lambda x: (-x["count"], x["question"]))
    return out[:limit]


# ---------------------------------------------------------------------
# Report-narrative drafts (docs/AI_INTEGRATION_PLAN.md Phase 5) — AI-drafted
# (then possibly analyst-edited) text for one report section. Export routes
# read whatever is saved here, falling back to the deterministic default when
# nothing has been saved — export never depends on AI being available.
# ---------------------------------------------------------------------

def set_report_draft(conn, scope, scope_key, field, text, actor):
    """Upsert one drafted/edited report-narrative field. `actor` is 'ai' for
    an AI draft or the editing user's username for a human save."""
    now = tz.now_iso()
    conn.execute(
        "INSERT INTO report_draft(scope, scope_key, field, text, actor, updated_at) "
        "VALUES (?,?,?,?,?,?) "
        "ON CONFLICT(scope, scope_key, field) DO UPDATE SET "
        "text=excluded.text, actor=excluded.actor, updated_at=excluded.updated_at",
        (scope, scope_key, field, text, actor, now))
    conn.commit()


def clear_report_draft(conn, scope, scope_key, field):
    """Delete one field's saved draft, reverting it to its computed default —
    the "leave blank to fall back" convention used by this edit form."""
    conn.execute("DELETE FROM report_draft WHERE scope=? AND scope_key=? AND field=?",
                (scope, scope_key, field))
    conn.commit()


def get_report_drafts(conn, scope, scope_key):
    """{field: {"text", "actor", "updated_at"}} for one scope/scope_key."""
    out = {}
    for field, text, actor, updated_at in conn.execute(
            "SELECT field, text, actor, updated_at FROM report_draft "
            "WHERE scope=? AND scope_key=?", (scope, scope_key)):
        out[field] = {"text": text, "actor": actor, "updated_at": updated_at}
    return out


def get_report_drafts_bulk(conn, scope, scope_keys):
    """{scope_key: {field: {"text","actor","updated_at"}}} for many scope_keys
    at once — the batch form of get_report_drafts, used when an export covers
    many activities so it's one query instead of N."""
    keys = list(dict.fromkeys(scope_keys))
    if not keys:
        return {}
    out = {}
    CHUNK = 900
    for i in range(0, len(keys), CHUNK):
        chunk = keys[i:i + CHUNK]
        qmarks = ",".join("?" * len(chunk))
        for scope_key, field, text, actor, updated_at in conn.execute(
                f"SELECT scope_key, field, text, actor, updated_at FROM report_draft "
                f"WHERE scope=? AND scope_key IN ({qmarks})", [scope] + chunk):
            out.setdefault(scope_key, {})[field] = {
                "text": text, "actor": actor, "updated_at": updated_at}
    return out


# ---------------------------------------------------------------------
# Audit log — append-only, hash-chained. Every governance-relevant action
# (editing collected data, hiding a person, managing users, exporting) writes
# one row here. Each row's hash commits to the previous row's hash, so any
# after-the-fact tampering with history breaks the chain and is detectable.
# ---------------------------------------------------------------------

def _audit_hash(prev_hash, ts, actor, action, target_type, target_id,
                summary, before_text, after_text):
    material = "|".join(str(x or "") for x in
                        (prev_hash, ts, actor, action, target_type, target_id,
                         summary, before_text, after_text))
    return hashlib.sha256(material.encode("utf-8")).hexdigest()


def audit(conn, actor, action, *, target_type=None, target_id=None,
          summary=None, before=None, after=None, ip=None):
    """Append one audit entry. Never raises into the caller's request — a
    failed audit write should surface loudly in logs, not break the action…
    except that silent-loss is worse for an audit trail, so we DO raise: the
    surrounding transaction simply fails with it, which is the safer default."""
    ts = tz.now_iso()
    row = conn.execute("SELECT row_hash FROM audit_log ORDER BY id DESC LIMIT 1").fetchone()
    prev_hash = row[0] if row else "genesis"
    row_hash = _audit_hash(prev_hash, ts, actor, action, target_type, target_id,
                           summary, before, after)
    conn.execute(
        """INSERT INTO audit_log(ts, actor, action, target_type, target_id,
               summary, before_text, after_text, ip, prev_hash, row_hash)
           VALUES (?,?,?,?,?,?,?,?,?,?,?)""",
        (ts, actor, action, target_type, str(target_id) if target_id is not None else None,
         summary, before, after, ip, prev_hash, row_hash))
    conn.commit()


def list_audit(conn, action=None, actor=None, limit=200):
    sql = ("SELECT id, ts, actor, action, target_type, target_id, summary, "
           "before_text, after_text, ip FROM audit_log")
    where, args = [], []
    if action:
        where.append("action=?"); args.append(action)
    if actor:
        where.append("actor=?"); args.append(actor)
    if where:
        sql += " WHERE " + " AND ".join(where)
    sql += " ORDER BY id DESC LIMIT ?"
    args.append(limit)
    return [{"id": r[0], "ts": r[1], "actor": r[2], "action": r[3],
             "target_type": r[4], "target_id": r[5], "summary": r[6],
             "before": r[7], "after": r[8], "ip": r[9]}
            for r in conn.execute(sql, args)]


def audit_actions(conn):
    return [r[0] for r in conn.execute("SELECT DISTINCT action FROM audit_log ORDER BY action")]


def audit_insights(conn):
    """A plain-language read on the whole audit log for the page header — how much
    has been recorded, how much landed today and this week, who's been busiest, the
    most common kind of action, and when the last one happened. Computed across the
    FULL log (independent of the table's action/actor filter). Windows are PH-local.
    Returns None for an empty log."""
    total = conn.execute("SELECT COUNT(*) FROM audit_log").fetchone()[0]
    if not total:
        return None
    today = tz.today_local().isoformat()                     # 'YYYY-MM-DD'
    week_ago = (tz.today_local() - timedelta(days=6)).isoformat()
    today_n = conn.execute(
        "SELECT COUNT(*) FROM audit_log WHERE date(ts) = ?", (today,)).fetchone()[0]
    week_n = conn.execute(
        "SELECT COUNT(*) FROM audit_log WHERE date(ts) >= ?", (week_ago,)).fetchone()[0]
    busiest = conn.execute(
        "SELECT actor, COUNT(*) c FROM audit_log WHERE date(ts) >= ? "
        "GROUP BY actor ORDER BY c DESC, actor LIMIT 1", (week_ago,)).fetchone()
    common = conn.execute(
        "SELECT action, COUNT(*) c FROM audit_log WHERE date(ts) >= ? "
        "GROUP BY action ORDER BY c DESC, action LIMIT 1", (week_ago,)).fetchone()
    last = conn.execute(
        "SELECT actor, action, ts FROM audit_log ORDER BY id DESC LIMIT 1").fetchone()
    return {
        "total": total, "today": today_n, "week": week_n,
        "busiest": ({"who": busiest[0], "n": busiest[1]} if busiest else None),
        "common": ({"action": common[0], "label": audit_label(common[0]),
                    "n": common[1]} if common else None),
        "last": ({"who": last[0], "action": last[1], "label": audit_label(last[1]),
                  "ts": last[2]} if last else None),
    }


# Plain-language names + a grouping category for every audit action code, so the
# log reads for a non-technical admin (the raw code stays available on hover and in
# the filter). (label, category). A code not listed here falls back to a humanized
# form of the code itself (see audit_label / audit_category), so a NEW action type
# is never blank — it just isn't categorised until added here.
_AUDIT_ACTIONS = {
    # Sign-in
    "login":               ("Signed in", "Sign-in"),
    "login_failed":        ("Failed sign-in", "Sign-in"),
    "logout":              ("Signed out", "Sign-in"),
    "first_run_admin":     ("First-run admin created", "Sign-in"),
    # Accounts
    "create_account":      ("Created an account", "Accounts"),
    "reset_password":      ("Reset a password", "Accounts"),
    "change_role":         ("Changed a role", "Accounts"),
    "activate_account":    ("Activated/deactivated an account", "Accounts"),
    "change_login_email":  ("Changed a login email", "Accounts"),
    # Directory
    "directory_add":       ("Added a directory person", "Directory"),
    "directory_edit":      ("Edited a directory person", "Directory"),
    "directory_delete":    ("Removed a directory person", "Directory"),
    "directory_populate":  ("Populated the directory", "Directory"),
    # Activities
    "activity_rename":     ("Renamed an activity", "Activities"),
    "activity_retag":      ("Re-filed an activity", "Activities"),
    "activity_archive":    ("Archived an activity", "Activities"),
    "archive_activities":  ("Archived activities", "Activities"),
    "form_archive":        ("Archived/restored a form", "Activities"),
    "walkin_entry_edit":   ("Edited a walk-in entry", "Activities"),
    "walkin_entry_archive": ("Archived/restored a walk-in entry", "Activities"),
    "harmonize_merge":     ("Merged activities", "Activities"),
    "manual_entry":        ("Keyed in a paper response", "Activities"),
    "tag_section":         ("Tagged an activity's section", "Activities"),
    "tag_sections":        ("Backfilled activity sections", "Activities"),
    "set_demographics":    ("Set activity demographics", "Activities"),
    "event_slug_set":      ("Set an activity's short link", "Activities"),
    "event_link_add":      ("Added an activity resource link", "Activities"),
    "event_link_edit":     ("Edited an activity resource link", "Activities"),
    "event_link_delete":   ("Removed an activity resource link", "Activities"),
    "event_message_set":   ("Set an activity's welcome/ending note", "Activities"),
    "event_certificate_set": ("Set an activity's certificate", "Activities"),
    "event_window_set":    ("Set an activity's response window", "Activities"),
    "event_dates_set":     ("Changed an activity's dates", "Activities"),
    "raffle_settings":     ("Changed raffle settings", "Activities"),
    "raffle_draw":         ("Drew a raffle winner", "Activities"),
    "raffle_reset":        ("Reset a raffle", "Activities"),
    "outside_speaker_add": ("Added an invited-activity speaker", "Activities"),
    "outside_speaker_rename": ("Renamed an invited-activity speaker", "Activities"),
    "outside_speaker_remove": ("Removed an invited-activity speaker", "Activities"),
    "outside_close":       ("Closed an invited activity", "Activities"),
    "outside_reopen":      ("Reopened an invited activity", "Activities"),
    "outside_archive":     ("Archived an invited activity", "Activities"),
    "resend_link":         ("Resent an activity link", "Activities"),
    "attendee_view_response": ("Viewed a registrant's response", "Activities"),
    "speaker_cleanup":     ("Cleaned up speakers", "Activities"),
    "roster_split":        ("Split a roster", "Activities"),
    "external_wipe":       ("Wiped external resource persons", "Activities"),
    # Comments
    "edit_remark":         ("Edited a comment", "Comments"),
    "retag_comment":       ("Re-sorted a comment", "Comments"),
    # Feedback
    "spot_feedback_add":   ("Sent Spot Feedback", "Feedback"),
    "spot_feedback_switch": ("Toggled Spot Feedback", "Feedback"),
    "spot_feedback_triage": ("Updated feedback status", "Feedback"),
    # Data & backups
    "export":              ("Exported data", "Data & backups"),
    "backup_settings":     ("Changed backup settings", "Data & backups"),
    "backup_run":          ("Ran a backup", "Data & backups"),
    "backup_failed":       ("Backup failed", "Data & backups"),
    "offsite_backup":      ("Off-site backup to GitHub", "Data & backups"),
    "backup_download":     ("Downloaded a backup", "Data & backups"),
    "backup_delete":       ("Deleted a backup", "Data & backups"),
    "backup_restore":      ("Restored a backup", "Data & backups"),
    "retention_purge":     ("Purged old personal data", "Data & backups"),
    "clear_sample_data":   ("Cleared sample data", "Data & backups"),
    "name_cleanup_backup": ("Backed up before a name cleanup", "Data & backups"),
    # Sharing
    "sharing_master_switch": ("Toggled public sharing", "Sharing"),
}


def audit_label(action):
    """Plain-English name for an audit action code. Unknown/new codes fall back to a
    humanized form ('event_foo' -> 'Event foo') so the log is never blank."""
    if action in _AUDIT_ACTIONS:
        return _AUDIT_ACTIONS[action][0]
    return (action or "").replace("_", " ").strip().capitalize() or "—"


def audit_category(action):
    """Grouping category for an audit action code (for chip tinting); 'Other' when
    the code isn't mapped yet."""
    return _AUDIT_ACTIONS.get(action, (None, "Other"))[1]


def audit_breakdown(conn, days=7, top=6):
    """The SHAPE of recent activity for the audit page: the ranked action types and
    busiest actors over the last `days` (PH-local), each carrying its plain-language
    label. Returns None for an empty window so the template can skip the panel."""
    since = (tz.today_local() - timedelta(days=days - 1)).isoformat()
    types = conn.execute(
        "SELECT action, COUNT(*) c FROM audit_log WHERE date(ts) >= ? "
        "GROUP BY action ORDER BY c DESC, action LIMIT ?", (since, top)).fetchall()
    if not types:
        return None
    actors = conn.execute(
        "SELECT actor, COUNT(*) c FROM audit_log WHERE date(ts) >= ? "
        "GROUP BY actor ORDER BY c DESC, actor LIMIT 5", (since,)).fetchall()
    top_n = types[0][1] if types else 0
    return {
        "days": days,
        "by_type": [{"action": a, "label": audit_label(a),
                     "category": audit_category(a), "n": c,
                     "pct": round(c / top_n * 100) if top_n else 0} for a, c in types],
        "by_actor": [{"who": a, "n": c} for a, c in actors],
    }


def verify_audit_chain(conn):
    """Walk the whole chain; returns (ok, first_bad_id). Detects edited or
    deleted rows (a gap breaks the prev_hash linkage)."""
    prev = "genesis"
    for r in conn.execute("""SELECT id, ts, actor, action, target_type, target_id,
                                    summary, before_text, after_text, prev_hash, row_hash
                             FROM audit_log ORDER BY id"""):
        if r[9] != prev:
            return False, r[0]
        if _audit_hash(prev, *r[1:9]) != r[10]:
            return False, r[0]
        prev = r[10]
    return True, None


# ---------------------------------------------------------------------
# Editing collected data (section managers): fix misspellings or unreadable
# text in the free-text comments. The RATINGS themselves are never editable —
# only words. Each function returns the BEFORE value so the caller can audit.
# ---------------------------------------------------------------------

def update_response_remarks(conn, response_id, text):
    """Replace a response's overall comment. Returns (ok, before_text)."""
    row = conn.execute("SELECT remarks FROM response WHERE id=?", (response_id,)).fetchone()
    if not row:
        return False, None
    text = (text or "").strip() or None
    conn.execute("UPDATE response SET remarks=? WHERE id=?", (text, response_id))
    conn.commit()
    return True, row[0]


def update_item_remark(conn, response_id, item_id, text):
    """Replace one item-level note. Returns (ok, before_text)."""
    row = conn.execute("SELECT id, text FROM item_remark WHERE response_id=? AND item_id=?",
                       (response_id, item_id)).fetchone()
    if not row:
        return False, None
    text = (text or "").strip()
    if text:
        conn.execute("UPDATE item_remark SET text=? WHERE id=?", (text, row[0]))
    else:
        conn.execute("DELETE FROM item_remark WHERE id=?", (row[0],))
    conn.commit()
    return True, row[1]


# ---------------------------------------------------------------------
# Walk-in (Type-1 / ARTA) entry manager — admin-only. The standing walk-in form
# has no per-instance activity page (it's one permanent form, not created per
# transaction), so this is the only place a bad/miskeyed/duplicate individual
# response can be corrected or reversibly put away.
# ---------------------------------------------------------------------

# item_remark rows tied to a Type-1 response are either a CO-CSM metadata field
# (this list) or a per-item note keyed by the SQD item_id it's about.
CSM_META_FIELDS = ["RESPONSE_NO", "SERVICE", "TYPE_OF_SERVICE", "CLIENT_TYPE", "EMAIL",
                   "SEX", "AGE", "REGION", "VERSION", "CC1", "CC2", "CC3", "FEEDBACK_TYPE"]


def walkin_entries_page(conn, page=1, per_page=50, include_archived=False):
    """Paginated list of individual Type-1 responses, newest first, for the entries
    manager. Returns (rows, total_count)."""
    page = max(1, page)
    where = "WHERE fi.survey_type = 1" + ("" if include_archived else " AND r.archived_at IS NULL")
    total = conn.execute(
        f"SELECT COUNT(*) FROM response r JOIN form_instance fi ON fi.id = r.form_instance_id {where}"
    ).fetchone()[0]
    rows = conn.execute(f"""
        SELECT r.id, r.submitted_at, sb.name, r.archived_at,
               (SELECT value FROM answer WHERE response_id = r.id AND item_id = 'SQD0'),
               (SELECT text FROM item_remark WHERE response_id = r.id AND item_id = 'RESPONSE_NO'),
               (SELECT text FROM item_remark WHERE response_id = r.id AND item_id = 'SERVICE'),
               (SELECT text FROM item_remark WHERE response_id = r.id AND item_id = 'CLIENT_TYPE')
        FROM response r
        JOIN form_instance fi ON fi.id = r.form_instance_id
        LEFT JOIN resource_person sb ON sb.id = r.served_by_rp_id
        {where}
        ORDER BY r.submitted_at DESC, r.id DESC
        LIMIT ? OFFSET ?
    """, (per_page, (page - 1) * per_page)).fetchall()
    return [{"id": r[0], "submitted_at": r[1], "served_by_name": r[2], "archived": bool(r[3]),
             "sqd0": r[4], "response_no": r[5], "service": r[6], "client_type": r[7]}
            for r in rows], total


def get_walkin_entry(conn, response_id):
    """Everything the entries editor needs for one Type-1 response: its SQD ratings,
    per-item notes, CO-CSM metadata, overall remarks, served-by and archived state.
    Returns None if it doesn't exist or isn't a Type-1 response."""
    row = conn.execute("""
        SELECT r.id, r.submitted_at, r.remarks, r.served_by_rp_id, r.archived_at, fi.survey_type
        FROM response r JOIN form_instance fi ON fi.id = r.form_instance_id
        WHERE r.id = ?
    """, (response_id,)).fetchone()
    if not row or row[5] != 1:
        return None
    answers = {a[0]: {"value": a[1], "is_na": bool(a[2])} for a in conn.execute(
        "SELECT item_id, value, is_na FROM answer WHERE response_id = ?", (response_id,)).fetchall()}
    remark_rows = dict(conn.execute(
        "SELECT item_id, text FROM item_remark WHERE response_id = ?", (response_id,)).fetchall())
    metadata = {f: remark_rows.get(f, "") for f in CSM_META_FIELDS}
    item_notes = {k: v for k, v in remark_rows.items() if k not in CSM_META_FIELDS}
    return {"id": row[0], "submitted_at": row[1], "remarks": row[2],
            "served_by_rp_id": row[3], "archived": bool(row[4]),
            "answers": answers, "metadata": metadata, "item_notes": item_notes}


def update_walkin_entry(conn, response_id, submitted_at, served_by_rp_id, remarks,
                        ratings, remark_fields):
    """Full edit of one Type-1 response: submission date, served-by, overall remarks,
    SQD0-8 ratings (`ratings` = {item_id: value_or_None}), and every item_remark row —
    both CO-CSM metadata and per-item notes (`remark_fields` = {item_id: text}, blank
    text deletes the row). Returns False if the response isn't a Type-1 response."""
    row = conn.execute(
        "SELECT fi.survey_type FROM response r JOIN form_instance fi ON fi.id = r.form_instance_id "
        "WHERE r.id = ?", (response_id,)).fetchone()
    if not row or row[0] != 1:
        return False
    conn.execute(
        "UPDATE response SET submitted_at=?, served_by_rp_id=?, remarks=? WHERE id=?",
        (submitted_at, served_by_rp_id, (remarks or "").strip() or None, response_id))
    for item_id, value in ratings.items():
        is_na = value is None
        stored = None if is_na else float(value)
        existing = conn.execute(
            "SELECT id FROM answer WHERE response_id=? AND item_id=?",
            (response_id, item_id)).fetchone()
        if existing:
            conn.execute("UPDATE answer SET value=?, is_na=? WHERE id=?",
                        (stored, int(is_na), existing[0]))
        else:
            # Older/legacy responses can be missing a row for an item added since
            # (e.g. SQD0 on an old walk-in slip) — insert it rather than silently
            # dropping the edit.
            conn.execute(
                "INSERT INTO answer(response_id, item_id, value, is_na) VALUES (?,?,?,?)",
                (response_id, item_id, stored, int(is_na)))
    for item_id, text in remark_fields.items():
        text = (text or "").strip()
        existing = conn.execute(
            "SELECT id FROM item_remark WHERE response_id=? AND item_id=?",
            (response_id, item_id)).fetchone()
        if text:
            if existing:
                conn.execute("UPDATE item_remark SET text=? WHERE id=?", (text, existing[0]))
            else:
                conn.execute(
                    "INSERT INTO item_remark(response_id, item_id, text) VALUES (?,?,?)",
                    (response_id, item_id, text))
        elif existing:
            conn.execute("DELETE FROM item_remark WHERE id=?", (existing[0],))
    conn.commit()
    return True


def set_response_archived(conn, response_id, archived):
    """Archive (hide from every report/analytic) or restore one Type-1 response.
    Reversible — the response-level counterpart to `set_form_archived`. Returns
    rows updated."""
    cur = conn.execute("UPDATE response SET archived_at=? WHERE id=?",
                       (tz.now_iso() if archived else None, response_id))
    conn.commit()
    return cur.rowcount


def set_comment_override(conn, response_id, item_id, tag, actor=None):
    """Manually re-tag a verbatim as 'appreciate', 'improve', or 'mixed' (correcting
    the auto-classification; 'mixed' shows on both columns). item_id='' is the
    response's overall remark. Upserts; returns the previous tag (or None) so the
    caller can audit the change."""
    item_id = item_id or ""
    now = tz.now_iso()
    prev = conn.execute(
        "SELECT tag FROM comment_override WHERE response_id=? AND item_id=?",
        (response_id, item_id)).fetchone()
    if prev:
        conn.execute("UPDATE comment_override SET tag=?, actor=?, set_at=? "
                     "WHERE response_id=? AND item_id=?",
                     (tag, actor, now, response_id, item_id))
    else:
        conn.execute("INSERT INTO comment_override(response_id, item_id, tag, actor, set_at) "
                     "VALUES (?,?,?,?,?)", (response_id, item_id, tag, actor, now))
    conn.commit()
    return prev[0] if prev else None


def get_comment_overrides(conn, response_ids):
    """Manual re-tags for a set of responses -> {(response_id, item_id): tag}. Used by
    story_panel to override the auto appreciate/improve split."""
    ids = [int(r) for r in response_ids]
    if not ids:
        return {}
    out = {}
    CHUNK = 900
    for i in range(0, len(ids), CHUNK):
        chunk = ids[i:i + CHUNK]
        qmarks = ",".join("?" * len(chunk))
        for rid, item_id, tag in conn.execute(
                f"SELECT response_id, item_id, tag FROM comment_override "
                f"WHERE response_id IN ({qmarks})", chunk):
            out[(rid, item_id or "")] = tag
    return out


def get_comment_overrides_with_actor(conn, response_ids):
    """Same as get_comment_overrides but keeping `actor` alongside the tag ->
    {(response_id, item_id): (tag, actor)}. Lets a caller tell a human re-tag
    (actor != 'ai') apart from an earlier AI one or none at all — the
    precedence an AI re-classify feature (docs/AI_INTEGRATION_PLAN.md Phase 4)
    must respect: human > ai > lexicon, so it never overwrites a person's
    correction."""
    ids = [int(r) for r in response_ids]
    if not ids:
        return {}
    out = {}
    CHUNK = 900
    for i in range(0, len(ids), CHUNK):
        chunk = ids[i:i + CHUNK]
        qmarks = ",".join("?" * len(chunk))
        for rid, item_id, tag, actor in conn.execute(
                f"SELECT response_id, item_id, tag, actor FROM comment_override "
                f"WHERE response_id IN ({qmarks})", chunk):
            out[(rid, item_id or "")] = (tag, actor)
    return out


# ---------------------------------------------------------------------
# Admin accounts (RBAC). Passwords are hashed in auth.py; storage only keeps
# the hash + salt. Roles: viewer / encoder / section_manager / admin.
# ---------------------------------------------------------------------

def count_admin_users(conn):
    return conn.execute("SELECT COUNT(*) FROM admin_user").fetchone()[0]


def system_inventory(conn):
    """Everyday 'what's in the system' tallies for the ops page — the plain counts a
    non-technical admin recognises (accounts, directory size, activities run,
    participants registered, feedback collected), not the technical health signals.
    Cheap COUNT(*)s computed on demand."""
    one = lambda sql: conn.execute(sql).fetchone()[0]
    return {
        "accounts_active": one("SELECT COUNT(*) FROM admin_user WHERE active=1"),
        "accounts_total": one("SELECT COUNT(*) FROM admin_user"),
        "staff": one("SELECT COUNT(*) FROM resource_person "
                     "WHERE is_internal=1 AND archived_at IS NULL"),
        "activities": one("SELECT COUNT(*) FROM event"),
        "attendees": one("SELECT COUNT(*) FROM attendee"),
        "responses": one("SELECT COUNT(*) FROM response"),
    }


def usage_pulse(conn):
    """Live 'who's using it + what's happened lately' read for the ops page, in
    everyday words. Derived from the audit log (sign-ins) and the cheap timestamp
    columns — NO schema change. Windows are PH-local.

    'active_now' is a soft proxy: distinct people with ANY audit action in the last
    15 minutes. There is no live session store, so recent activity is the honest
    'who's on right now' signal — labelled as such on the page so it never
    overpromises real-time presence. Timestamps are stored naive-local (tzutil), so
    date(ts) and lexical >= comparisons stay correct (no UTC-shift)."""
    one = lambda sql, *a: conn.execute(sql, a).fetchone()[0]
    today = tz.today_local().isoformat()
    week_ago = (tz.today_local() - timedelta(days=6)).isoformat()
    active_since = (tz.now_local() - timedelta(minutes=15)).isoformat(timespec="seconds")
    last = conn.execute("SELECT actor, ts FROM audit_log WHERE action='login' "
                        "ORDER BY id DESC LIMIT 1").fetchone()
    recent = conn.execute("SELECT actor, ts FROM audit_log WHERE action='login' "
                          "ORDER BY id DESC LIMIT 6").fetchall()
    return {
        # People & sign-ins (from the audit log)
        "active_now": one("SELECT COUNT(DISTINCT actor) FROM audit_log WHERE ts >= ?",
                          active_since),
        "signed_in_today": one("SELECT COUNT(DISTINCT actor) FROM audit_log "
                               "WHERE action='login' AND date(ts) = ?", today),
        "signed_in_week": one("SELECT COUNT(DISTINCT actor) FROM audit_log "
                              "WHERE action='login' AND date(ts) >= ?", week_ago),
        "last_login": ({"who": last[0], "ts": last[1]} if last else None),
        "recent_logins": [{"who": r[0], "ts": r[1]} for r in recent],
        # 'Lately' freshness deltas, to read beside the all-time totals
        "responses_today": one("SELECT COUNT(*) FROM response WHERE date(submitted_at) = ?",
                               today),
        "responses_week": one("SELECT COUNT(*) FROM response WHERE date(submitted_at) >= ?",
                              week_ago),
        "activities_week": one("SELECT COUNT(*) FROM event WHERE date(created_at) >= ?",
                               week_ago),
        "participants_week": one("SELECT COUNT(*) FROM attendee WHERE date(created_at) >= ?",
                                 week_ago),
    }


def create_admin_user(conn, username, pw_hash, salt, role, created_by=None,
                      rp_id=None, active=True, must_change=False):
    """Create an account. For a pilot account, pass a hashed default password with
    must_change=True — the person signs in with it once and is forced to choose
    their own. (Legacy invite mode passes pw_hash='', salt='', active=False.)"""
    cur = conn.execute(
        """INSERT INTO admin_user(username, pw_hash, salt, role, active, must_change,
                                  rp_id, created_at, created_by)
           VALUES (?,?,?,?,?,?,?,?,?)""",
        (username, pw_hash, salt, role, 1 if active else 0, 1 if must_change else 0, rp_id,
         tz.now_iso(), created_by))
    conn.commit()
    return cur.lastrowid


def _admin_row(r):
    return {"id": r[0], "username": r[1], "pw_hash": r[2], "salt": r[3],
            "role": r[4], "active": bool(r[5]), "must_change": bool(r[6]),
            "rp_id": r[7], "created_at": r[8], "created_by": r[9],
            "avatar_kind": r[10], "avatar_name": r[11], "onboarded_at": r[12],
            "avatar_last_care_at": r[13], "avatar_care_streak": r[14] or 0,
            "designation": r[15], "has_account_photo": bool(r[16]),
            "bureau_access": r[17] or "", "has_account_signature": bool(r[18]),
            "pending": (r[2] == "")}      # no password set yet => still invited


# The account's own photo and signature are BLOBs, so the shared row loader never
# SELECTs their bytes (that would drag whole images into every user-list read) —
# it takes cheap booleans instead; get_user_photo()/get_user_signature() fetch the
# bytes only when serving.
_ADMIN_COLS = ("id, username, pw_hash, salt, role, active, must_change, rp_id, "
               "created_at, created_by, avatar_kind, avatar_name, onboarded_at, "
               "avatar_last_care_at, avatar_care_streak, designation, "
               "(photo IS NOT NULL) AS has_account_photo, "
               "COALESCE(bureau_access, ''), "
               "(signature IS NOT NULL) AS has_account_signature")


def get_admin_user(conn, username):
    r = conn.execute(f"SELECT {_ADMIN_COLS} FROM admin_user WHERE username=?",
                     (username,)).fetchone()
    return _admin_row(r) if r else None


def get_admin_user_by_id(conn, user_id):
    r = conn.execute(f"SELECT {_ADMIN_COLS} FROM admin_user WHERE id=?",
                     (user_id,)).fetchone()
    return _admin_row(r) if r else None


def get_admin_user_by_rp(conn, rp_id):
    r = conn.execute(f"SELECT {_ADMIN_COLS} FROM admin_user WHERE rp_id=?",
                     (rp_id,)).fetchone()
    return _admin_row(r) if r else None


def list_admin_users(conn):
    rows = conn.execute(f"SELECT {_ADMIN_COLS} FROM admin_user ORDER BY username").fetchall()
    return [_admin_row(r) for r in rows]


def admin_accounts_by_rp(conn):
    """{rp_id: account} for accounts linked to a directory person."""
    return {u["rp_id"]: u for u in list_admin_users(conn) if u["rp_id"] is not None}


# ---- Staff onboarding + avatar profile (STAFF_ONBOARDING_AVATAR_PLAN.md) ----

def set_user_avatar(conn, user_id, kind, name):
    """Adopt (or change) an account's avatar companion: species + pet name.
    Validates the species against the catalog and trims/caps the name. Raises
    ValueError on an unknown species. Leaves onboarded_at alone."""
    if not valid_avatar_kind(kind):
        raise ValueError("Pick one of the available companions.")
    conn.execute("UPDATE admin_user SET avatar_kind=?, avatar_name=? WHERE id=?",
                 (kind, clean_avatar_name(name), user_id))
    conn.commit()


def record_avatar_care(conn, user_id, now=None):
    """Log a care action (watering a plant / feeding an animal) for the mood
    layer. Care only *counts* once per AVATAR_CARE_COOLDOWN_HOURS — a repeat tap
    inside the window still gets its animation client-side but leaves the
    timestamp (and therefore the mood decay clock) unmoved, so tap-spamming
    can't pin the pet at 'happy' forever.

    A counted care also advances the consecutive-day streak (same day: keeps
    it, next day: +1, gap: back to 1); seven days running earns the one-time
    'Devoted caretaker' wellness badge — cosmetic like the mood, never points.
    Returns {"counted", "mood", "last_care_at", "streak", "badge"} where badge
    is the freshly-awarded label or None."""
    now_dt = now or tz.now_local()
    acct = get_admin_user_by_id(conn, user_id)
    if not acct:
        return {"counted": False, "mood": "droopy", "last_care_at": None,
                "streak": 0, "badge": None}
    last = acct.get("avatar_last_care_at")
    last_dt = _parse_care_ts(last)
    if last_dt and (now_dt - last_dt) < timedelta(hours=AVATAR_CARE_COOLDOWN_HOURS):
        return {"counted": False, "mood": avatar_mood(last, now=now_dt),
                "last_care_at": last, "streak": acct.get("avatar_care_streak") or 0,
                "badge": None}
    if last_dt and last_dt.date() == now_dt.date():
        streak = acct.get("avatar_care_streak") or 1        # second care today
    elif last_dt and last_dt.date() == now_dt.date() - timedelta(days=1):
        streak = (acct.get("avatar_care_streak") or 0) + 1  # kept it going
    else:
        streak = 1                                          # first care / lapsed
    stamp = now_dt.isoformat(timespec="seconds")
    conn.execute("UPDATE admin_user SET avatar_last_care_at=?, avatar_care_streak=? "
                 "WHERE id=?", (stamp, streak, user_id))
    badge = _award_badge(conn, user_id, "avatar_care_7",
                         when=stamp) if streak >= 7 else None
    conn.commit()
    return {"counted": True, "mood": avatar_mood(stamp, now=now_dt),
            "last_care_at": stamp, "streak": streak, "badge": badge}


def mark_onboarded(conn, user_id, when=None):
    """Stamp the account as having finished the one-time /welcome flow. Idempotent
    — re-stamping just refreshes the timestamp; the redirect guard only cares
    whether onboarded_at is NULL."""
    conn.execute("UPDATE admin_user SET onboarded_at=? WHERE id=?",
                 (when or tz.now_iso(), user_id))
    conn.commit()


def get_user_profile(conn, user_id):
    """Everything the chooser / profile pages show about one account in a single
    read: the account row (incl. avatar_kind/avatar_name/onboarded_at) plus,
    when the account is linked to a directory person, that person's display
    name, org path, designation and whether they have a profile photo. Returns
    None for an unknown account. `avatar_kind` is normalized to the default
    species when the account has not chosen one, so callers can always draw
    something."""
    acct = get_admin_user_by_id(conn, user_id)
    if not acct:
        return None
    rp = get_rp(conn, acct["rp_id"]) if acct.get("rp_id") else None
    rp_has_photo = bool((rp or {}).get("has_photo"))
    account_has_photo = bool(acct.get("has_account_photo"))
    # The photo shown on the profile/greeting: the directory picture when the
    # account is linked and has one, otherwise the account's own uploaded photo
    # (served from /me/photo). Every account can now carry a photo.
    if rp_has_photo:
        photo_url = f"/photo/{acct['rp_id']}"
    elif account_has_photo:
        photo_url = "/me/photo"
    else:
        photo_url = None
    # Same linked-first precedence for the signature the account signs with, so
    # /me can show what is currently on file (the bytes are never returned here).
    has_signature = bool((rp or {}).get("has_signature")) or bool(acct.get("has_account_signature"))
    return {
        "user_id": acct["id"],
        "username": acct["username"],
        "role": acct["role"],
        "rp_id": acct.get("rp_id"),
        "avatar_kind": acct.get("avatar_kind") or AVATAR_DEFAULT,
        "avatar_name": acct.get("avatar_name") or "",
        "avatar_last_care_at": acct.get("avatar_last_care_at"),
        "avatar_mood": avatar_mood(acct.get("avatar_last_care_at")),
        "avatar_care_streak": acct.get("avatar_care_streak") or 0,
        "onboarded": bool(acct.get("onboarded_at")),
        "onboarded_at": acct.get("onboarded_at"),
        "person_name": (rp or {}).get("name") or "",
        "has_signature": has_signature,
        "org_unit_id": (rp or {}).get("org_unit_id"),
        "org_path": (rp or {}).get("org_path"),
        # For a linked account the staff directory is authoritative (an admin
        # may edit it there too, and /me writes through to it), so its value
        # wins; an unlinked account uses the designation stored on the account.
        "designation": ((rp or {}).get("designation") if rp
                        else acct.get("designation")) or "",
        # position rides along too (unlinked accounts have none) so callers
        # can apply is_bureau_director() — the Director's title lives here,
        # not in designation (see is_bureau_director).
        "position": (rp or {}).get("position") or "",
        "has_photo": rp_has_photo,
        "account_has_photo": account_has_photo,
        "photo_url": photo_url,
        "hidden_public": bool((rp or {}).get("hidden_public")),
    }


def set_admin_active(conn, user_id, active):
    conn.execute("UPDATE admin_user SET active=? WHERE id=?", (1 if active else 0, user_id))
    conn.commit()


def set_admin_username(conn, user_id, username):
    """Re-point an account's login email (its username) to a new address."""
    conn.execute("UPDATE admin_user SET username=? WHERE id=?", (username, user_id))
    conn.commit()


def set_admin_role(conn, user_id, role):
    conn.execute("UPDATE admin_user SET role=? WHERE id=?", (role, user_id))
    conn.commit()


# ---- bureau-wide access (an explicit grant, never a side effect of a role) ---

# What one account may see beyond its own directory unit.
#   ''    — nothing extra. The directory decides, which is the default and the
#           right answer for almost everyone.
#   'awa' — work arrangement only: the bureau's whole ANNEX C on screen and in
#           print. The Admin Officer consolidating the fortnight's submission
#           needs every section; they do not need anyone's wellness claims.
#   'all' — every scoped view: work arrangement, the wellness register and the
#           landing page's team view.
# Deliberately NOT a role. A role is a set of things you may DO; this is how far
# you may SEE, it is granted per account, and it shows up in the audit log when
# it changes.
BUREAU_ACCESS_LEVELS = [
    ("", "Their own unit only"),
    ("awa", "Work arrangement, bureau-wide"),
    ("all", "Everything, bureau-wide"),
]
BUREAU_ACCESS_LABELS = dict(BUREAU_ACCESS_LEVELS)


def valid_bureau_access(level):
    return level in BUREAU_ACCESS_LABELS


def set_bureau_access(conn, user_id, level):
    """Grant or revoke bureau-wide sight. Raises ValueError on an unknown level."""
    if not valid_bureau_access(level):
        raise ValueError("Unknown bureau access level.")
    conn.execute("UPDATE admin_user SET bureau_access=? WHERE id=?", (level, user_id))
    conn.commit()


def bureau_access_of(conn, user):
    """This account's grant, read fresh from the row.

    Read from the DATABASE, never from the request user dict: that dict comes
    out of the signed session cookie, which was minted at sign-in and would keep
    asserting a grant for as long as the cookie lives — including after an admin
    revoked it."""
    if not user:
        return ""
    row = conn.execute("SELECT COALESCE(bureau_access, '') FROM admin_user WHERE id=?",
                       (user.get("id"),)).fetchone()
    return (row[0] if row else "") or ""


# The grants the bureau asked for by name, applied once each when the account
# exists. Keyed per username, not one global marker: an account that hasn't been
# created yet still gets its grant on a later start, and one that was revoked in
# Admin → Users stays revoked instead of being re-granted by the next deploy.
BUREAU_ACCESS_SEED = [
    # The Admin Officer consolidates ANNEX C for the whole bureau, so he needs
    # every section's schedule on screen and in print — and nothing else.
    ("armedel@doh.gov.ph", "awa", None),
    # Bureau-wide across all three modules, with the administrator role.
    ("ray@gmail.com", "all", "admin"),
]


def _seed_bureau_access(conn):
    """Apply BUREAU_ACCESS_SEED once per named account. Never overwrites a level
    an administrator has since chosen: the marker is written the first time the
    account is seen, whatever happens to the grant afterwards."""
    for username, level, role in BUREAU_ACCESS_SEED:
        marker = f"bureau_access_seeded:{username.lower()}"
        if get_setting(conn, marker):
            continue
        row = conn.execute(
            "SELECT id, role, COALESCE(bureau_access,'') FROM admin_user "
            "WHERE lower(username)=?", (username.lower(),)).fetchone()
        if not row:
            continue                      # not created yet — try again next start
        uid, cur_role, cur_level = row
        if cur_level != level:
            conn.execute("UPDATE admin_user SET bureau_access=? WHERE id=?",
                         (level, uid))
        if role and cur_role != role:
            conn.execute("UPDATE admin_user SET role=? WHERE id=?", (role, uid))
        set_setting(conn, marker, tz.now_iso())
        conn.commit()


def user_sees_whole_bureau(conn, user, area=None):
    """Does this account's grant cover `area` ('awa', 'wellness', or None for a
    view that spans modules)? 'all' covers everything; 'awa' covers only the work
    arrangement, and only when the caller says that is what it is showing."""
    level = bureau_access_of(conn, user)
    if level == "all":
        return True
    return level == "awa" and area == "awa"


def set_admin_password(conn, user_id, pw_hash, salt, activate=True, must_change=False):
    """Set (or reset) a password. Activating clears the pending state. By default
    this clears the must_change flag (the user just chose their own password); pass
    must_change=True for an admin-set temporary/default password."""
    conn.execute(
        "UPDATE admin_user SET pw_hash=?, salt=?, must_change=?"
        + (", active=1" if activate else "") + " WHERE id=?",
        (pw_hash, salt, 1 if must_change else 0, user_id))
    conn.commit()


def list_external_organizers(conn):
    return [{"id": r[0], "name": r[1]}
            for r in conn.execute("SELECT id, name FROM external_organizer ORDER BY name")]


def add_org_unit_under(conn, parent_id, name, level, short_name=None):
    """Add an org unit under a parent, deriving its rollup path from the parent's.
    The path segment uses the short_name (or the name if none). parent_id=None
    creates a top-level unit."""
    seg = (short_name or name).strip()
    if parent_id:
        parent_path = conn.execute("SELECT path FROM org_unit WHERE id=?", (parent_id,)).fetchone()[0]
        path = parent_path + "/" + seg
    else:
        path = seg
    return add_org_unit(conn, name, level, path, short_name=short_name)


_UNSET = object()


def update_rp(conn, rp_id, *, name=_UNSET, org_unit_id=_UNSET, position=_UNSET,
              designation=_UNSET, focus_area=_UNSET, email=_UNSET, employment_type=_UNSET,
              honorific=_UNSET, agency=_UNSET):
    """Update a resource person. Only the fields you pass are touched; passing
    None clears that field (used by the directory edit page)."""
    fields = {"name": name, "org_unit_id": org_unit_id, "position": position,
              "designation": designation, "focus_area": focus_area,
              "email": email, "employment_type": employment_type,
              "honorific": honorific, "agency": agency}
    sets = [(k, v) for k, v in fields.items() if v is not _UNSET]
    if not sets:
        return
    conn.execute("UPDATE resource_person SET " + ", ".join(f"{k}=?" for k, _ in sets) +
                 " WHERE id=?", [v for _, v in sets] + [rp_id])
    conn.commit()


def set_rp_archived(conn, rp_id, archived, reason=None, when=None):
    """Archive (or restore) a directory person — the admin's answer to "this one
    resigned". Returns {"ok", "msg", "account"} where `account` is the username
    of the sign-in account that was deactivated along with them, if any.

    Archiving deactivates the person's linked login: someone who has left the
    bureau should not still be able to sign in, and leaving that to a second trip
    through Admin -> Users is how it gets forgotten.

    Restoring deliberately does NOT re-enable that login. Re-granting access is a
    decision about permissions, not about a directory row, so it stays an explicit
    act on the accounts page — restoring is for fixing a mis-click or a rehire,
    and neither should quietly hand back a session.
    """
    rp = get_rp(conn, rp_id)
    if not rp:
        return {"ok": False, "msg": "That person is no longer in the directory.", "account": None}
    if archived and rp["archived"]:
        return {"ok": True, "msg": f"{rp['name']} is already archived.", "account": None}
    if not archived and not rp["archived"]:
        return {"ok": True, "msg": f"{rp['name']} is already active.", "account": None}
    conn.execute("UPDATE resource_person SET archived_at=?, archived_reason=? WHERE id=?",
                 ((when or tz.now_iso()) if archived else None,
                  (reason or "").strip() or None if archived else None, rp_id))
    account = None
    if archived:
        row = conn.execute("SELECT id, username FROM admin_user WHERE rp_id=? AND active=1",
                           (rp_id,)).fetchone()
        if row:
            conn.execute("UPDATE admin_user SET active=0 WHERE id=?", (row[0],))
            account = row[1]
    conn.commit()
    if archived:
        msg = f"{rp['name']} archived."
        if account:
            msg += f" Their sign-in ({account}) was deactivated too."
        return {"ok": True, "msg": msg, "account": account}
    return {"ok": True, "msg": (f"{rp['name']} restored to the directory. Re-enable their "
                                "sign-in from Admin → Users if they need one."),
            "account": None}


def set_rp_photo(conn, rp_id, blob, mime):
    """Store (or replace) a person's profile picture as bytes inside the db."""
    conn.execute("UPDATE resource_person SET photo=?, photo_mime=? WHERE id=?",
                 (sqlite3.Binary(blob), mime, rp_id))
    conn.commit()


def set_user_photo(conn, user_id, blob, mime):
    """Store (or replace) an account's own profile picture. Used for accounts
    that aren't linked to a directory person, so every viewer can still set a
    photo from /me (linked accounts write to their resource_person row instead)."""
    conn.execute("UPDATE admin_user SET photo=?, photo_mime=? WHERE id=?",
                 (sqlite3.Binary(blob), mime, user_id))
    conn.commit()


def get_user_photo(conn, user_id):
    """Return (bytes, mime) for an account's own photo, or None if it has none."""
    row = conn.execute("SELECT photo, photo_mime FROM admin_user WHERE id=?",
                       (user_id,)).fetchone()
    if not row or row[0] is None:
        return None
    return bytes(row[0]), (row[1] or "image/jpeg")


def set_user_designation(conn, user_id, designation):
    """Set (or clear) the account's self-service designation shown on /me.
    Trimmed; blank clears it. Kept on the account so unlinked viewers can fill
    one in without touching the admin-managed directory."""
    val = (designation or "").strip() or None
    conn.execute("UPDATE admin_user SET designation=? WHERE id=?", (val, user_id))
    conn.commit()


def get_rp_photo(conn, rp_id):
    """Return (bytes, mime) for a person's photo, or None if they have none."""
    row = conn.execute("SELECT photo, photo_mime FROM resource_person WHERE id=?",
                       (rp_id,)).fetchone()
    if not row or row[0] is None:
        return None
    return bytes(row[0]), (row[1] or "image/jpeg")


def set_rp_signature(conn, rp_id, blob, mime):
    """Store (or replace) a person's signature image as bytes inside the db.
    Used only for certificate signatories; never served at a public URL."""
    conn.execute("UPDATE resource_person SET signature=?, signature_mime=? WHERE id=?",
                 (sqlite3.Binary(blob), mime, rp_id))
    conn.commit()


def clear_rp_signature(conn, rp_id):
    """Remove a person's stored signature image."""
    conn.execute("UPDATE resource_person SET signature=NULL, signature_mime=NULL WHERE id=?",
                 (rp_id,))
    conn.commit()


def get_rp_signature(conn, rp_id):
    """Return (bytes, mime) for a person's signature image, or None."""
    row = conn.execute("SELECT signature, signature_mime FROM resource_person WHERE id=?",
                       (rp_id,)).fetchone()
    if not row or row[0] is None:
        return None
    return bytes(row[0]), (row[1] or "image/png")


def set_user_signature(conn, user_id, blob, mime):
    """Store (or replace) an account's own signature image. Used for accounts
    that aren't linked to a directory person, so every viewer can still sign
    from /me (linked accounts write to their resource_person row instead)."""
    conn.execute("UPDATE admin_user SET signature=?, signature_mime=? WHERE id=?",
                 (sqlite3.Binary(blob), mime, user_id))
    conn.commit()


def clear_user_signature(conn, user_id):
    """Remove an account's own stored signature image."""
    conn.execute("UPDATE admin_user SET signature=NULL, signature_mime=NULL WHERE id=?",
                 (user_id,))
    conn.commit()


def get_user_signature(conn, user_id):
    """Return (bytes, mime) for an account's own signature, or None."""
    row = conn.execute("SELECT signature, signature_mime FROM admin_user WHERE id=?",
                       (user_id,)).fetchone()
    if not row or row[0] is None:
        return None
    return bytes(row[0]), (row[1] or "image/png")


def user_signature(conn, user_id):
    """The signature to sign WITH for an account: the directory row's when the
    account is linked and has one, otherwise the account's own. Same precedence
    get_user_profile uses for the profile photo, so a person has one signature
    whichever page they drew it on. Returns (bytes, mime) or None."""
    acct = get_admin_user_by_id(conn, user_id)
    if not acct:
        return None
    if acct.get("rp_id"):
        sig = get_rp_signature(conn, acct["rp_id"])
        if sig:
            return sig
    return get_user_signature(conn, user_id)


# ---------------------------------------------------------------------
# Fuzzy duplicate detection (stdlib only) — so near-identical names don't
# pile up in the directory: 'Dr. Vince Reyes' ~ 'Vince Reyes', typos, reorders.
# ---------------------------------------------------------------------

_HONORIFICS = {"dr", "dra", "prof", "engr", "atty", "mr", "ms", "mrs", "hon", "rev", "sir"}
_DUP_THRESHOLD = 0.85


def _norm_name(s):
    """Lowercase, drop punctuation + honorifics, sort tokens — so order and
    titles don't matter when comparing."""
    s = re.sub(r"[^\w\s]", " ", (s or "").lower())
    toks = sorted(t for t in s.split() if t and t not in _HONORIFICS)
    return " ".join(toks)


def names_match(a, b):
    """True if two names are the same or close enough to be a likely duplicate."""
    na, nb = _norm_name(a), _norm_name(b)
    if not na or not nb:
        return False
    if na == nb:
        return True
    return difflib.SequenceMatcher(None, na, nb).ratio() >= _DUP_THRESHOLD


def similar_names(conn, name, kind, exclude_id=None):
    """Existing names of the given kind that look like duplicates of `name`.
    kind: 'staff' | 'external_rp' | 'organizer' | 'unit'."""
    if kind == "staff":
        rows = conn.execute("SELECT id, name FROM resource_person WHERE is_internal=1").fetchall()
    elif kind == "external_rp":
        rows = conn.execute("SELECT id, name FROM resource_person WHERE is_internal=0").fetchall()
    elif kind == "organizer":
        rows = conn.execute("SELECT id, name FROM external_organizer").fetchall()
    elif kind == "unit":
        rows = conn.execute("SELECT id, name FROM org_unit").fetchall()
    else:
        rows = []
    return [nm for rid, nm in rows
            if rid != exclude_id and names_match(name, nm)]


def seed_directory_if_empty(conn):
    """Momentum path: on a brand-new (empty) database, drop in a few sample
    sections, internal staff, and external RPs so the screen is immediately
    testable. Only fires when there is NO org structure at all, so 'Clear sample
    data & start fresh' (which leaves a bare bureau) is NOT undone by re-seeding."""
    if conn.execute("SELECT COUNT(*) FROM org_unit").fetchone()[0]:
        return False

    blhsd_id, _, blhsd_path = get_or_create_blhsd(conn)
    div = add_org_unit(conn, "Division 1", "division", blhsd_path + "/Div1")
    sec_a = add_org_unit(conn, "Section A", "section", blhsd_path + "/Div1/SecA")
    add_org_unit(conn, "Section B", "section", blhsd_path + "/Div1/SecB")

    add_rp(conn, "Dr. Vince Reyes", is_internal=True, org_unit_id=sec_a)
    add_rp(conn, "Ana Cruz", is_internal=True, org_unit_id=div)
    add_rp(conn, "Guest Speaker (External)", is_internal=False)
    add_rp(conn, "Prof. Maria Santos", is_internal=False)
    return True


def human_form_id(form, event_date, instance_id):
    """The displayed form ID, e.g. 'F2-2026-0007'. Derived (not stored): the
    family ('F2'/'F3') + the EVENT-date year + the zero-padded row id."""
    year = (event_date or "")[:4] or "0000"
    return f"{form}-{year}-{int(instance_id):04d}"


def form_noun(form):
    """Fallback activity label when a comment's form instance has no stored
    title or topic and no `event` link to borrow a name from — common in the
    historical backlog, where speaker (F3) forms were imported without a topic
    and were never grouped under a named event. We deliberately do NOT guess the
    activity from date/org (one unit runs many activities a day, so a guess would
    mislabel), so an un-named activity simply reads 'Untitled event'. Walk-in
    (F1) feedback isn't tied to an event, so it keeps its own plain name."""
    return {"F1": "Walk-in service"}.get(form, "Untitled event")


def form_verbatims(conn, form_instance_id):
    """All free-text feedback for one form instance, for the 'see verbatims' view.

    Returns a list (one entry per response that left any comment) of
    {response_id, remarks, items: {item_id: text}}.
    """
    out = {}
    for rid, remarks in conn.execute(
            "SELECT id, remarks FROM response WHERE form_instance_id=? ORDER BY id",
            (form_instance_id,)):
        if remarks:
            out.setdefault(rid, {"response_id": rid, "remarks": remarks, "items": {}})
    for rid, item_id, text in conn.execute("""
            SELECT ir.response_id, ir.item_id, ir.text
            FROM item_remark ir JOIN response r ON r.id = ir.response_id
            WHERE r.form_instance_id=? ORDER BY ir.response_id, ir.item_id""",
            (form_instance_id,)):
        entry = out.setdefault(rid, {"response_id": rid, "remarks": None, "items": {}})
        entry["items"][item_id] = text
    return list(out.values())


def verbatims_for_responses(conn, response_ids):
    """Free-text feedback for an arbitrary set of responses — the dashboard
    drill-down. The dashboard scopes the ATOMS through the engine, hands us the
    surviving response_ids, and we just fetch the human-readable text for them.
    Scope logic stays in one place (the engine); storage only remembers words.

    Returns newest-first [{response_id, when, form_id, topic, remarks, items}].
    """
    ids = [int(r) for r in response_ids]
    if not ids:
        return []
    out = {}
    # Chunk the IN lists: SQLite caps bound variables (~32k, 999 on old builds),
    # and a bureau-wide scope can pass tens of thousands of response ids.
    CHUNK = 900
    for i in range(0, len(ids), CHUNK):
        chunk = ids[i:i + CHUNK]
        qmarks = ",".join("?" * len(chunk))
        for rid, when, remarks, form, edate, fid, topic, etitle in conn.execute(f"""
                SELECT r.id, r.submitted_at, r.remarks, fi.form, fi.event_date, fi.id, fi.topic,
                       e.title
                FROM response r
                JOIN form_instance fi ON fi.id = r.form_instance_id
                LEFT JOIN event_form ef ON ef.form_instance_id = fi.id
                LEFT JOIN event e       ON e.id = ef.event_id
                WHERE r.id IN ({qmarks})""", chunk):
            # Human activity name: the real event title, else the talk/activity
            # topic, else a plain-language family noun — never a bare code.
            activity = (etitle or topic or "").strip() or form_noun(form)
            out[rid] = {"response_id": rid, "when": (when or "")[:16].replace("T", " "),
                        "_sort": (when or "", rid),
                        "form_id": human_form_id(form, edate, fid),
                        "activity": activity, "topic": topic,
                        "remarks": remarks, "notes": {}}
        for rid, item_id, text in conn.execute(f"""
                SELECT response_id, item_id, text FROM item_remark
                WHERE response_id IN ({qmarks}) ORDER BY response_id, item_id""", chunk):
            if rid in out:
                out[rid]["notes"][item_id] = text
    # Newest first across all chunks; drop responses with no text.
    rows = [v for v in out.values() if v["remarks"] or v["notes"]]
    rows.sort(key=lambda v: v.pop("_sort"), reverse=True)
    return rows


# item_remark ids that are encoding metadata (a physical form's response number,
# demographic tallies), never a respondent's own words — excluded from the
# per-activity "edit the words" editor.
_NON_COMMENT_ITEMS = ("SEX", "AFFIL", "RESPONSE_NO")

# Public alias — the MRR export reads item notes as verbatims too and needs the
# same exclusion list, without reaching into a name marked private.
NON_COMMENT_ITEMS = _NON_COMMENT_ITEMS


def activity_editable_comments(conn, response_ids):
    """Flat, newest-first list of every respondent-written comment across a set of
    responses, shaped for the per-activity "edit the words" (encoding) editor —
    one entry per editable text box. Unlike the story panel (a curated digest that
    shows only a handful), this is the COMPLETE set, so any comment can be fixed.

    Each entry:
        {response_id, item_id, text, kind, activity, when, form_id}
    `item_id` is '' for the response's overall comment — posting to
    /responses/{id}/edit-remark with a blank item_id updates `response.remarks`;
    otherwise it's the item code for a per-item note. Demographic / metadata items
    (SEX/AFFIL/RESPONSE_NO) are never words, so they're excluded."""
    out = []
    for v in verbatims_for_responses(conn, response_ids):
        base = {"response_id": v["response_id"], "activity": v["activity"],
                "when": v["when"], "form_id": v["form_id"]}
        if (v.get("remarks") or "").strip():
            out.append({**base, "item_id": "", "text": v["remarks"], "kind": "overall"})
        for item_id, text in (v.get("notes") or {}).items():
            if item_id in _NON_COMMENT_ITEMS or not (text or "").strip():
                continue
            out.append({**base, "item_id": item_id, "text": text, "kind": "item"})
    return out


def response_context_for_ids(conn, response_ids):
    """Per-response identity for an arbitrary set of responses — submitted time,
    the human activity name, and any response-level comment — for EVERY response,
    whether or not it left free text (unlike verbatims_for_responses, which is
    comment-only). This is what the raw-data / per-submission export needs so each
    row is labelled with when it came in and which activity it belongs to.

    Returns {response_id: {"when": "YYYY-MM-DD HH:MM", "activity": str,
                           "comment": str}}.
    """
    ids = [int(r) for r in response_ids]
    if not ids:
        return {}
    out = {}
    CHUNK = 900
    for i in range(0, len(ids), CHUNK):
        chunk = ids[i:i + CHUNK]
        qmarks = ",".join("?" * len(chunk))
        for rid, when, remarks, form, edate, fid, topic, etitle in conn.execute(f"""
                SELECT r.id, r.submitted_at, r.remarks, fi.form, fi.event_date, fi.id,
                       fi.topic, e.title
                FROM response r
                JOIN form_instance fi ON fi.id = r.form_instance_id
                LEFT JOIN event_form ef ON ef.form_instance_id = fi.id
                LEFT JOIN event e       ON e.id = ef.event_id
                WHERE r.id IN ({qmarks})""", chunk):
            # Same human activity name the verbatims drill-down uses: the real event
            # title, else the talk/activity topic, else a plain-language family noun.
            activity = (etitle or topic or "").strip() or form_noun(form)
            out[rid] = {"when": (when or "")[:16].replace("T", " "),
                        "activity": activity,
                        "comment": (remarks or "").strip()}
    return out


def list_activity_instances(conn):
    """Every Type 2 (event review) and Type 3 (resource-person) form instance with
    the context bound at creation — the raw material the Activities view groups
    into events. Scoring still happens on the atoms; this is only the structure
    (who/what/when/where), so the view can show one row per event that expands to
    its event review (F2) and each speaker (F3)."""
    rows = conn.execute("""
        SELECT fi.id, fi.survey_type, fi.form, fi.event_date, fi.venue, fi.topic,
               fi.rp_id, rp.name, rp.is_internal, rp.hidden_public,
               fi.lead_org_id, olead.path, olead.name,
               fi.organizer_external_id, xo.name, fi.created_at,
               fi.open_at, fi.close_at, fi.attendance, COALESCE(fi.attendance_suspect,0),
               fi.modality, fi.end_date, COALESCE(fi.encoding_locked, 0),
               rp.position, rp.designation, fi.created_by
        FROM form_instance fi
        LEFT JOIN resource_person rp   ON rp.id  = fi.rp_id
        LEFT JOIN org_unit olead       ON olead.id = fi.lead_org_id
        LEFT JOIN external_organizer xo ON xo.id  = fi.organizer_external_id
        WHERE fi.survey_type IN (2, 3) AND COALESCE(fi.archived, 0) = 0
              AND COALESCE(fi.pooled, 0) = 0
        ORDER BY fi.event_date DESC, fi.created_at, fi.id
    """).fetchall()
    return [{"id": r[0], "survey_type": r[1], "form": r[2], "event_date": r[3],
             "venue": r[4], "topic": r[5], "rp_id": r[6], "rp_name": r[7],
             "rp_internal": (None if r[8] is None else bool(r[8])),
             "rp_hidden": bool(r[9]) if r[9] is not None else False,
             "lead_org_id": r[10], "lead_path": r[11], "lead_name": r[12],
             "organizer_external_id": r[13], "organizer_name": r[14],
             "created_at": r[15], "open_at": r[16], "close_at": r[17],
             "attendance": r[18], "attendance_suspect": bool(r[19]),
             "modality": r[20] or "f2f",
             "end_date": r[21],
             # Per-form "locked to encoding" flag — an event is CLOSED when every
             # one of its (non-archived) forms is locked; see event_is_closed.
             "encoding_locked": bool(r[22]),
             # position/designation ride along so callers can apply
             # is_bureau_director() without a second query per speaker.
             "rp_position": r[23], "rp_designation": r[24],
             # The account username that filed this form (nullable on historical
             # rows). Joinable to admin_user.username — one of the few relations
             # tying a STAFF MEMBER to an activity, since attendees are external
             # registrants with no account link.
             "created_by": r[25]}
            for r in rows]


# "Today"/"now" are the local (Asia/Manila, UTC+8) calendar day and wall-clock — the
# same Manila rule the rest of the app uses for the activity lifecycle. Callers pass
# them in from tzutil (today_local / now_iso), never from SQLite 'localtime', so the
# day flips at real local midnight, not the UTC container's midnight.
def lifecycle_of(event_date, close_at, today, now, end_date=None):
    """Classify an activity's monitoring lifecycle from its dates (pure — pass in
    `today` = local YYYY-MM-DD and `now` = local 'YYYY-MM-DD HH:MM:SS' once, so a
    whole list can be classified without re-querying the clock):

      'upcoming'  — the activity has not happened yet (START day is in the future):
                    the REGISTRATION phase, monitor who has signed up.
      'ongoing'   — the activity has started AND its CSS is still collecting:
                    its close_at is still in the future, or — when no close was set
                    — today still falls within the activity's run (start..end, where
                    end defaults to the start day). Monitor who has answered the CSS.
      'concluded' — past, with the feedback window closed.

    A blank event_date can't be placed on the timeline, so it is treated as
    concluded (the safe default — it never demands monitoring attention)."""
    if not event_date:
        return "concluded"
    ed = event_date[:10]
    if ed > today:
        return "upcoming"
    if close_at:
        # close_at is stored ISO with a 'T' separator; callers pass `now` with either
        # a 'T' (tz.now_iso) or a space (SQLite datetime('now','localtime')). A text
        # compare across a mismatched separator flips same-date order — ' ' (0x20)
        # sorts before 'T' (0x54) — so a just-closed activity would read as still
        # ongoing until midnight. Normalise both to one separator first.
        return ("ongoing" if now.replace("T", " ") <= close_at.replace("T", " ")
                else "concluded")
    # No explicit feedback deadline: a multi-day activity stays ongoing through
    # its last day (end_date); a single-day activity only on its event day.
    last = (end_date or ed)[:10]
    return "ongoing" if ed <= today <= last else "concluded"


# The app's canonical clock is Asia/Manila (see tzutil): every stored timestamp —
# event_date, close_at, submitted_at — is written in it. SQLite's date/datetime
# ('now','localtime') follows the CONTAINER zone instead, which is UTC on a stock
# Hugging Face image, so it drifts ~8 h from those stamps and would split the
# activity day (and the "is the window still open?" test) on the wrong boundary.
# The lifecycle feeds below therefore BIND the Manila clock in as parameters rather
# than reaching for SQLite 'localtime'. `datetime(...)` still wraps close_at so the
# stored 'T' separator normalises to the space form both sides then share.
def _local_now():
    """Manila 'now' as a naive ISO string, for binding into time comparisons."""
    return tz.now_iso()


def _local_today():
    """Manila 'today' as 'YYYY-MM-DD', for binding into date comparisons."""
    return tz.today_local().isoformat()


def upcoming_events(conn, limit=6):
    """Type-2 activities dated AFTER today (strictly future) — the registration
    phase, soonest first, for the home 'Upcoming' feed. One row per event (the F2
    event-review form). `event_token` (the /e/<token> link tree) and `n_registered`
    (how many have signed up so far) are included for app-created activities so the
    feed doubles as a registration monitor; backfilled rows lack a token and report
    0 registered. Today's events are NOT here — they are 'ongoing' (see
    ongoing_events)."""
    rows = conn.execute("""
        SELECT fi.id, fi.event_date, fi.venue, fi.topic, e.event_token, e.id, fi.modality
        FROM form_instance fi
        LEFT JOIN event_form ef ON ef.form_instance_id = fi.id
        LEFT JOIN event e       ON e.id = ef.event_id
        WHERE fi.survey_type = 2
              AND COALESCE(fi.archived, 0) = 0 AND COALESCE(fi.pooled, 0) = 0
              AND fi.event_date <> '' AND date(fi.event_date) > ?
        ORDER BY fi.event_date ASC, fi.id ASC
        LIMIT ?
    """, (_local_today(), limit)).fetchall()
    out = []
    for r in rows:
        event_id = r[5]
        summ = event_registration_summary(conn, event_id) if event_id else None
        out.append({"id": r[0], "event_date": r[1], "venue": r[2], "topic": r[3],
                    "event_token": r[4], "event_id": event_id, "modality": r[6] or "f2f",
                    "n_registered": summ["registered"] if summ else 0,
                    "speakers": event_speaker_names(conn, event_id)})
    return out


def ongoing_events(conn, limit=20):
    """Activities whose CSS is CURRENTLY collecting — the event day has arrived
    (date <= today) and the feedback window is still open: close_at is in the
    future, or, when no close_at is set, it is the event day itself. Newest first.

    Only app-created activities appear (an INNER join on event/event_form): the
    strict rule is that registration + CSS monitoring is for new activities created
    through the link-tree flow, never the historical backlog (those have no event
    and no registrants). Each row carries the registration funnel (registered /
    answered_any / completed) so the home feed can show who has answered."""
    rows = conn.execute("""
        SELECT fi.id, fi.event_date, fi.venue, fi.topic, e.event_token, e.id,
               fi.modality, fi.close_at
        FROM form_instance fi
        JOIN event_form ef ON ef.form_instance_id = fi.id
        JOIN event e       ON e.id = ef.event_id
        WHERE fi.survey_type = 2
              AND COALESCE(fi.archived, 0) = 0 AND COALESCE(fi.pooled, 0) = 0
              AND fi.event_date <> ''
              AND date(fi.event_date) <= ?                      -- Manila today
              -- Window still open: close in the future (datetime() normalises close_at's
              -- 'T' to the space form the bound Manila now shares), or no close set and
              -- it is the event day. Bound clock, not SQLite 'localtime' — see _local_now.
              AND ( (fi.close_at IS NOT NULL AND datetime(?) <= datetime(fi.close_at))
                 OR (fi.close_at IS NULL AND date(fi.event_date) = ?) )
        ORDER BY fi.event_date DESC, fi.id ASC
        LIMIT ?
    """, (_local_today(), _local_now(), _local_today(), limit)).fetchall()
    out = []
    for r in rows:
        summ = event_registration_summary(conn, r[5])
        out.append({"id": r[0], "event_date": r[1], "venue": r[2], "topic": r[3],
                    "event_token": r[4], "event_id": r[5], "modality": r[6] or "f2f",
                    "close_at": r[7], "speakers": event_speaker_names(conn, r[5]), **summ})
    return out


# How each survey type reads to the manager who created it (home strip badge).
_ACTIVITY_KIND = {1: "Walk-in service", 2: "Event review", 3: "Speaker review"}


def ongoing_standalone(conn, limit=20):
    """Currently-collecting activities the bureau `ongoing_events` feed misses: app-
    created speaker/event reviews that have NO event record (so no registration
    funnel) — e.g. a standalone "invited" speaker review. These are the "open
    surveys/collections" a manager expects to see on the home Ongoing card while
    their window is open; without this they were silently absent.

    Same open-window guard as `ongoing_events` (event day arrived + window still
    open). Restricted to app-created rows (created_by IS NOT NULL) so the historical
    backlog — which has no creator and no event — never leaks in. One row per form,
    newest first, each carrying a response count and its public rating link instead
    of a registration funnel."""
    rows = conn.execute("""
        SELECT fi.id, fi.event_date, fi.venue, fi.topic, fi.qr_token,
               fi.modality, fi.close_at, fi.survey_type, fi.rp_id,
               (SELECT COUNT(*) FROM response r WHERE r.form_instance_id = fi.id)
        FROM form_instance fi
        LEFT JOIN event_form ef ON ef.form_instance_id = fi.id
        WHERE ef.form_instance_id IS NULL
              AND fi.created_by IS NOT NULL
              AND COALESCE(fi.archived, 0) = 0 AND COALESCE(fi.pooled, 0) = 0
              AND fi.survey_type IN (2, 3)
              AND fi.event_date <> ''
              AND date(fi.event_date) <= ?                      -- Manila today
              -- Same open-window guard as ongoing_events, against the bound Manila clock
              -- (see _local_now): close in the future — datetime() normalises close_at's
              -- 'T' separator — or no close set and it is the event day.
              AND ( (fi.close_at IS NOT NULL AND datetime(?) <= datetime(fi.close_at))
                 OR (fi.close_at IS NULL AND date(fi.event_date) = ?) )
        ORDER BY fi.event_date DESC, fi.id DESC
        LIMIT ?
    """, (_local_today(), _local_now(), _local_today(), limit)).fetchall()
    out = []
    for r in rows:
        rp_name = None
        if r[8]:
            nm = conn.execute("SELECT name FROM resource_person WHERE id=?", (r[8],)).fetchone()
            rp_name = nm[0] if nm else None
        out.append({
            "id": r[0], "event_date": r[1], "venue": r[2], "topic": r[3],
            "qr_token": r[4], "modality": r[5] or "f2f", "close_at": r[6],
            "kind": _ACTIVITY_KIND.get(r[7], "Activity"),
            "responses": r[9], "speakers": [rp_name] if rp_name else [],
            "link": f"/r/{r[4]}", "tip": "Open this activity",
            # Markers the home Ongoing feed branches on: no registration funnel.
            "standalone": True, "event_token": None,
            "registered": None, "answered_any": None,
        })
    return out


def ongoing_invited(conn, limit=20):
    """Invited / "outside" activities (event_kind='outside') that are CURRENTLY
    collecting — the event day has arrived (date <= today) and the feedback window
    is still open: close_at is in the future, or no close_at was ever set (the
    public /seq form stays open until an explicit close, so the manager should keep
    seeing it here until they close it). One row per event, newest first.

    These activities have only Form-3 speaker reviews grouped under an event record,
    so they fall through BOTH other ongoing feeds: `ongoing_events` needs a Form 2
    (they have none) and `ongoing_standalone` needs NO event record (they have one).
    Without this feed a still-open invited activity is unreachable from the home page
    once it drops off the 7-day "recent activities" strip — live to respondents but
    invisible to its manager. Each row shows the activity name, the total responses
    across its speakers, and links to the activity's manage page."""
    rows = conn.execute("""
        SELECT e.id, e.event_token, e.title,
               MIN(fi.event_date), MIN(fi.venue), MIN(fi.modality), MIN(fi.close_at),
               MIN(fi.id),
               (SELECT COUNT(*) FROM response r
                  JOIN event_form ef2 ON ef2.form_instance_id = r.form_instance_id
                 WHERE ef2.event_id = e.id)
        FROM event e
        JOIN event_form ef    ON ef.event_id = e.id
        JOIN form_instance fi ON fi.id = ef.form_instance_id
        WHERE e.event_kind = 'outside'
              AND COALESCE(fi.archived, 0) = 0 AND COALESCE(fi.pooled, 0) = 0
              AND fi.event_date <> ''
              AND date(fi.event_date) <= ?                      -- Manila today
              -- Still collecting: no close set, or the close is in the future against the
              -- bound Manila now (datetime() normalises close_at's stored 'T' separator).
              -- Binding the app clock, not SQLite 'localtime', is what makes a just-closed
              -- activity leave this feed immediately regardless of the container's zone.
              AND ( fi.close_at IS NULL OR datetime(?) <= datetime(fi.close_at) )
        GROUP BY e.id
        ORDER BY MIN(fi.event_date) DESC, e.id DESC
        LIMIT ?
    """, (_local_today(), _local_now(), limit)).fetchall()
    out = []
    for r in rows:
        event_id, event_token = r[0], r[1]
        out.append({
            # `id` is a representative form of the event; the inline-archive route
            # expands any event-bound form id to the whole event, so the admin
            # Archive button on this row archives the entire invited activity.
            "id": r[7], "event_date": r[3], "venue": r[4], "topic": r[2],
            "modality": r[5] or "f2f", "close_at": r[6],
            "kind": "Invited activity", "responses": r[8],
            "speakers": event_speaker_names(conn, event_id),
            "link": f"/activities/{event_token}/manage", "tip": "Manage this activity",
            # Render in the template's standalone branch (response count + link),
            # not the registration-funnel branch — invited activities have no funnel.
            "standalone": True, "event_token": None,
            "registered": None, "answered_any": None,
        })
    return out


def activities_by_creator(conn, created_by, limit=6, archived=0, all_creators=False,
                          since_days=None):
    """The most recent activities a manager created, newest first, with a response
    count and a usable link — so they can always find what they made, *especially*
    an "outside event" (Form 3 only, no event record) that the bureau-event
    lifecycle feeds on the home page deliberately skip. Powers the home "Your recent
    activities" strip.

    Bureau events (an F2 review + N speaker F3s, all created in one go) collapse to
    a single row — the F2 review — so the strip lists one entry per activity, not
    one per form. Outside events have no event, so each stands alone. Rows created
    before the created_by column existed are unattributed and never appear.

    `archived` selects which side to list: 0 = the live strip (default), 1 = the
    Archived page. Each row also carries `fid` (the form id), `archivable` (True
    only for a standalone form — no event — the only shape the per-form archive
    route accepts), and `has_event` (True for a bureau/outside event, which
    archives/restores at the event level via the per-instance route instead).

    `all_creators` (admins only) drops the creator scope and lists every creator's
    activities — including the historical rows with no `created_by` — so an admin can
    reach (and archive) any activity from the home strip, not just ones they made.

    `since_days` (e.g. 30) keeps only activities whose own `event_date` falls within
    that many days of today — plus any dated in the future — so the home strip is a
    genuinely *recent* window and the years-old imported backlog drops off. (We key on
    `event_date`, not `created_at`, because the historical rows were all imported on one
    recent day and would otherwise all read as "new".) None = no time bound (the default;
    used by the Archived page)."""
    if not all_creators and not (created_by or "").strip():
        return []
    where = "COALESCE(fi.archived, 0) = ? AND COALESCE(fi.pooled, 0) = 0"
    params = [1 if archived else 0]
    if since_days is not None:
        # event_date is a PH-local 'YYYY-MM-DD' string; the cutoff date is the same
        # shape, so a plain lexicographic >= compares correctly. Undated rows are kept
        # (an activity with no date shouldn't silently vanish from the strip).
        cutoff = (tz.now_local() - timedelta(days=since_days)).strftime("%Y-%m-%d")
        where += " AND (fi.event_date IS NULL OR fi.event_date >= ?)"
        params.append(cutoff)
    if not all_creators:
        where = "fi.created_by = ? AND " + where
        params.insert(0, created_by)
    rows = conn.execute(f"""
        SELECT fi.id, fi.survey_type, fi.event_date, fi.venue, fi.modality, fi.topic,
               fi.qr_token, fi.close_at, fi.created_at, e.event_token,
               e.title, e.event_kind,
               (SELECT COUNT(*) FROM response r WHERE r.form_instance_id = fi.id) AS responses
        FROM form_instance fi
        LEFT JOIN event_form ef ON ef.form_instance_id = fi.id
        LEFT JOIN event e       ON e.id = ef.event_id
        WHERE {where}
        ORDER BY fi.created_at DESC, fi.id ASC
        LIMIT ?
    """, (*params, max(limit, 60))).fetchall()
    now = tz.now_iso()
    reps, orphans, resp_sum = {}, [], {}
    for r in rows:
        tok = r[9]                                  # the grouping event's token (or None)
        kind_ev = (r[11] or "bureau") if tok else None
        outside = kind_ev == "outside"
        d = {"id": r[0], "survey_type": r[1],
             # Outside activities read as one "invited activity"; bureau/standalone
             # forms keep their own kind label.
             "kind": "Invited activity" if outside else _ACTIVITY_KIND.get(r[1], "Activity"),
             "event_date": r[2], "venue": r[3], "modality": r[4] or "f2f",
             # Outside (and bureau) bundled rows show the ACTIVITY NAME (event title);
             # an unbundled form falls back to its own topic.
             "topic": (r[10] if tok else None) or r[5],
             "qr_token": r[6], "close_at": r[7], "created_at": r[8],
             # Expose event_token only for bureau events — it drives the strip's
             # "see who answered" registration affordance, which outside events lack.
             "event_token": tok if (tok and not outside) else None,
             "event_kind": kind_ev, "responses": r[12],
             "open": (r[7] is None) or (now <= r[7]),
             # The per-form archive route only accepts standalone forms (no event);
             # bureau/outside events archive at the event level via the per-instance
             # route instead (`has_event`). `fid` is the form id either route keys on.
             "fid": r[0], "archivable": (tok is None), "has_event": tok is not None}
        # The usable link + its tooltip: a bureau event opens its registration/CSS
        # monitor; an outside activity opens its (registration-free) manage page; a
        # standalone form opens its public rating page.
        if tok and not outside:
            d["link"], d["tip"] = f"/monitor/{tok}", "See who answered"
        elif outside:
            d["link"], d["tip"] = f"/activities/{tok}/manage", "Manage this activity"
        else:
            d["link"], d["tip"] = f"/r/{d['qr_token']}", "Open this activity"
        if tok:
            resp_sum[tok] = resp_sum.get(tok, 0) + (r[12] or 0)
            # one row per event — prefer the F2 review as the representative.
            if tok not in reps or (d["survey_type"] == 2 and reps[tok]["survey_type"] != 2):
                reps[tok] = d
        else:
            orphans.append(d)
    # An outside activity has no single representative form (no F2), so its headline
    # count is the total across all its speaker forms; bureau keeps its review count.
    for tok, d in reps.items():
        if d["event_kind"] == "outside":
            d["responses"] = resp_sum[tok]
    items = list(reps.values()) + orphans
    items.sort(key=lambda x: (x["created_at"] or "", x["id"]), reverse=True)
    return items[:limit]


def today_local(conn=None):
    """Today's date as 'YYYY-MM-DD' in the app's local zone (Asia/Manila) — the same
    Manila clock every stored timestamp uses, and the same boundary the lifecycle
    feeds now split on. Derived from tzutil, NOT SQLite's date('now','localtime'):
    the container runs in UTC (see tzutil), so 'localtime' there is ~8 h off and would
    split the day on the wrong boundary. `conn` is accepted for call-site compatibility
    but no longer used."""
    return _local_today()


# 'Recently concluded' is derived from build_events() in the route (not raw SQL):
# build_events keys each event by min(all_ids) of its date/venue/organizer group
# and only includes events with a renderable score, so the report link
# (/reports/activities/<id>) always resolves. A raw form_instance id would not
# match that representative id.


# ---------------------------------------------------------------------
# Restored 2026-06-11 after tail truncation (reconstructed from the
# storage.cpython-314 bytecode constants + caller contracts).
# ---------------------------------------------------------------------

_SEARCH_SQL = """
        SELECT fi.id, fi.qr_token, fi.survey_type, fi.form, fi.event_date,
               fi.venue, fi.topic, rp.name,
               COALESCE(xo.name, olead.name) AS organizer,
               COALESCE(rc.n, 0) AS n,
               fi.open_at, fi.close_at, fi.modality
        FROM form_instance fi
        LEFT JOIN resource_person rp    ON rp.id = fi.rp_id
        LEFT JOIN org_unit olead        ON olead.id = fi.lead_org_id
        LEFT JOIN external_organizer xo ON xo.id = fi.organizer_external_id
        LEFT JOIN (SELECT form_instance_id, COUNT(*) AS n FROM response
                   GROUP BY form_instance_id) rc ON rc.form_instance_id = fi.id
        WHERE fi.survey_type IN (2, 3) AND COALESCE(fi.archived, 0) = 0
              AND COALESCE(fi.pooled, 0) = 0
              AND COALESCE(fi.encoding_locked, 0) = 0
        ORDER BY fi.event_date DESC, fi.id DESC
    """


def search_form_instances(conn, q, limit=50):
    """Event/speaker forms for the encode picker. Empty q = newest first.
    Tokenised match over form id, names, topic, venue, organizer."""
    rows = conn.execute(_SEARCH_SQL).fetchall()
    toks = [t for t in (q or "").lower().split() if t]
    out = []
    for r in rows:
        fid, tok, stype, form, edate, venue, topic, rp_name, organizer, n, open_at, close_at, modality = r
        form_id = human_form_id(form, edate, fid)
        hay = " ".join(filter(None, (form_id, form, edate, venue, topic,
                                     rp_name, organizer))).lower()
        if toks and not all(t in hay for t in toks):
            continue
        out.append({"id": fid, "qr_token": tok, "survey_type": stype, "form": form,
                    "event_date": edate, "venue": venue, "topic": topic,
                    "rp_name": rp_name, "organizer": organizer,
                    "form_id": form_id, "response_count": n,
                    "open_at": open_at, "close_at": close_at,
                    "modality": modality or "f2f"})
        if len(out) >= limit:
            break
    return out


def get_form_context(conn, qr_token):
    """Resolve a QR token back to the context bound at creation, for the
    respondent landing. Returns None if the token is unknown."""
    row = conn.execute("""
        SELECT fi.id, fi.survey_type, fi.form, fi.event_date, fi.venue, fi.topic,
               rp.name AS rp_name,
               olead.name AS lead_name,
               xo.name AS external_name,
               fi.rp_id, rp.photo IS NOT NULL,
               fi.open_at, fi.close_at, fi.modality, fi.end_date,
               COALESCE(fi.encoding_locked, 0)
        FROM form_instance fi
        LEFT JOIN resource_person rp ON rp.id = fi.rp_id
        LEFT JOIN org_unit olead     ON olead.id = fi.lead_org_id
        LEFT JOIN external_organizer xo ON xo.id = fi.organizer_external_id
        WHERE fi.qr_token = ?
    """, (qr_token,)).fetchone()
    if not row:
        return None
    (fid, stype, form, edate, venue, topic, rp_name,
     lead_name, external_name, rp_id, has_photo, open_at, close_at, modality,
     end_date, encoding_locked) = row
    if external_name:
        organizer = f"{external_name} (external)"
    elif lead_name:
        organizer = f"{lead_name} (internal)"
    else:
        organizer = "Bureau"
    initials = None
    if rp_name:
        parts = [p for p in rp_name.split() if p]
        if parts:
            initials = (parts[0][0] + (parts[-1][0] if len(parts) > 1 else "")).upper()
    return {"id": fid, "qr_token": qr_token, "survey_type": stype, "form": form,
            "event_date": edate, "end_date": end_date, "venue": venue, "topic": topic,
            "rp_name": rp_name, "organizer": organizer,
            "form_id": human_form_id(form, edate, fid),
            "rp_id": rp_id, "rp_initials": initials,
            "rp_photo": (f"/photo/{rp_id}" if (rp_id and has_photo) else None),
            "open_at": open_at, "close_at": close_at,
            "encoding_locked": bool(encoding_locked),
            "modality": modality or "f2f"}


def set_lead_org(conn, form_instance_id, org_id):
    """Set the organizing unit (section/division/bureau) of a form instance.
    This is what `load_atoms` rolls a Type-2 event up by, so it drives
    per-section analytics."""
    conn.execute("UPDATE form_instance SET lead_org_id=? WHERE id=?",
                 (org_id, form_instance_id))
    conn.commit()


def lead_org_of(conn, form_instance_id):
    row = conn.execute("SELECT lead_org_id FROM form_instance WHERE id=?",
                       (form_instance_id,)).fetchone()
    return row[0] if row else None


def set_response_window(conn, form_instance_id, open_at, close_at):
    """Bind the entry window (ISO datetime strings or None/'' = unbounded)."""
    conn.execute("UPDATE form_instance SET open_at=?, close_at=? WHERE id=?",
                 (open_at or None, close_at or None, form_instance_id))
    conn.commit()


def get_event_window(conn, event_id):
    """The entry window shared by an event's forms, as {'open_at', 'close_at'}.
    All forms of an event are created with the same window, so we read it off the
    first form (lowest ordinal). Returns None on both sides when none of the
    event's forms carry a window. Used by the manage page to pre-fill the editor."""
    row = conn.execute("""
        SELECT fi.open_at, fi.close_at
        FROM event_form ef
        JOIN form_instance fi ON fi.id = ef.form_instance_id
        WHERE ef.event_id = ? AND COALESCE(fi.archived, 0) = 0
        ORDER BY ef.ordinal
        LIMIT 1
    """, (event_id,)).fetchone()
    if not row:
        return {"open_at": None, "close_at": None}
    return {"open_at": row[0], "close_at": row[1]}


def set_event_window(conn, event_id, open_at, close_at):
    """Apply one entry window to EVERY (non-archived) form of an event, so the
    organizer edits it once for the whole activity. Blank/None on either side =
    unbounded on that side. Returns the number of forms updated."""
    cur = conn.execute("""
        UPDATE form_instance SET open_at=?, close_at=?
        WHERE COALESCE(archived, 0) = 0
          AND id IN (SELECT form_instance_id FROM event_form WHERE event_id = ?)
    """, (open_at or None, close_at or None, event_id))
    conn.commit()
    return cur.rowcount


def set_event_respondent_target(conn, event_id, value):
    """Set (or clear) an activity's manager-entered respondent count — the override
    denominator for its completion rate (see event_registration_summary). A falsy /
    None value clears the override (NULL), so the Monitor falls back to the live
    registered count; a positive int is stored as-is. Returns the value stored
    (int or None). The caller is responsible for rejecting a target below the
    current respondent count — this setter only persists what it is given."""
    stored = int(value) if value else None
    if stored is not None and stored <= 0:
        stored = None
    conn.execute("UPDATE event SET respondent_target = ? WHERE id = ?",
                 (stored, event_id))
    conn.commit()
    return stored


def set_event_dates(conn, event_id, event_date, end_date):
    """Re-date a whole activity after creation: update the event row AND every
    (non-archived) form of it, so the link tree header and the reporting atoms
    never disagree. event_date is the START (and must be a real 'YYYY-MM-DD');
    end_date marks a multi-day activity (None/blank = single-day). Returns the
    number of forms updated. NOTE: changing the start date moves the reporting
    period, so the CALLER must invalidate the atoms cache afterwards."""
    end_date = end_date or None
    conn.execute("UPDATE event SET event_date=?, end_date=? WHERE id=?",
                 (event_date, end_date, event_id))
    cur = conn.execute("""
        UPDATE form_instance SET event_date=?, end_date=?
        WHERE COALESCE(archived, 0) = 0
          AND id IN (SELECT form_instance_id FROM event_form WHERE event_id = ?)
    """, (event_date, end_date, event_id))
    conn.commit()
    return cur.rowcount


# ---------------------------------------------------------------------
# Outside-activity management — the manage page for an "outside event — we were
# invited" activity (no registration / link tree; just its speaker reviews).
# ---------------------------------------------------------------------

def _outside_event_context(conn, event_id):
    """The baked context shared by an outside activity's speaker forms (read off the
    first form), so a newly added speaker inherits the same date/venue/modality/
    external organizer/creator. {} if the event has no forms left."""
    row = conn.execute("""
        SELECT fi.event_date, fi.venue, fi.modality, fi.organizer_external_id,
               fi.created_by, fi.end_date
        FROM event_form ef JOIN form_instance fi ON fi.id = ef.form_instance_id
        WHERE ef.event_id = ?
        ORDER BY ef.ordinal, fi.id LIMIT 1
    """, (event_id,)).fetchone()
    if not row:
        return {}
    return {"event_date": row[0], "venue": row[1], "modality": row[2],
            "organizer_external_id": row[3], "created_by": row[4], "end_date": row[5]}


def manage_event_speakers(conn, event_id):
    """Per-speaker rows for an outside activity's manage page: form_instance id, its
    qr_token, the resource person (id + name), the topic, the response count and the
    entry-window bounds. In the order they were added."""
    rows = conn.execute("""
        SELECT fi.id, fi.qr_token, fi.rp_id, rp.name, fi.topic, fi.open_at, fi.close_at,
               (SELECT COUNT(*) FROM response r WHERE r.form_instance_id = fi.id) AS responses
        FROM event_form ef
        JOIN form_instance fi ON fi.id = ef.form_instance_id
        LEFT JOIN resource_person rp ON rp.id = fi.rp_id
        WHERE ef.event_id = ? AND fi.survey_type = 3 AND COALESCE(fi.archived, 0) = 0
        ORDER BY ef.ordinal, fi.id
    """, (event_id,)).fetchall()
    return [{"id": r[0], "qr_token": r[1], "rp_id": r[2], "rp_name": r[3],
             "topic": r[4], "open_at": r[5], "close_at": r[6], "responses": r[7]}
            for r in rows]


def _form_in_event(conn, event_id, form_instance_id):
    return conn.execute(
        "SELECT 1 FROM event_form WHERE event_id=? AND form_instance_id=?",
        (event_id, form_instance_id)).fetchone() is not None


def event_form_counts(conn, event_id):
    """(active, archived) speaker-form counts for an event — lets the manage page
    tell an archived activity apart from a genuinely empty one."""
    row = conn.execute("""
        SELECT SUM(CASE WHEN COALESCE(fi.archived,0)=0 THEN 1 ELSE 0 END),
               SUM(CASE WHEN COALESCE(fi.archived,0)=1 THEN 1 ELSE 0 END)
        FROM event_form ef JOIN form_instance fi ON fi.id = ef.form_instance_id
        WHERE ef.event_id = ?
    """, (event_id,)).fetchone()
    return (row[0] or 0, row[1] or 0)


def update_speaker_topic(conn, event_id, form_instance_id, topic):
    """Rename a speaker's topic — always allowed, even with responses (it doesn't
    change any rating). Guarded to the event's own forms. Returns True if applied."""
    if not _form_in_event(conn, event_id, form_instance_id):
        return False
    conn.execute("UPDATE form_instance SET topic=? WHERE id=?",
                 ((topic or "").strip() or None, form_instance_id))
    conn.commit()
    return True


def add_event_speaker(conn, event_id, rp_id, topic):
    """Add a new speaker review (Form 3) to an outside activity, inheriting the
    activity's baked context and linked after the current last speaker. Returns
    {id, qr_token}, or None if the event has no context to inherit."""
    ctx = _outside_event_context(conn, event_id)
    if not ctx:
        return None
    fid = create_form_instance(
        conn, survey_type=3, form="F3", event_date=ctx["event_date"],
        end_date=ctx.get("end_date"),
        venue=ctx["venue"], modality=ctx["modality"], rp_id=int(rp_id),
        topic=(topic or "").strip() or None,
        organizer_external_id=ctx["organizer_external_id"], created_by=ctx["created_by"])
    nxt = conn.execute(
        "SELECT COALESCE(MAX(ordinal), -1) + 1 FROM event_form WHERE event_id=?",
        (event_id,)).fetchone()[0]
    conn.execute(
        "INSERT OR IGNORE INTO event_form(event_id, form_instance_id, ordinal) VALUES (?,?,?)",
        (event_id, fid, nxt))
    conn.commit()
    token = conn.execute("SELECT qr_token FROM form_instance WHERE id=?",
                         (fid,)).fetchone()[0]
    return {"id": fid, "qr_token": token}


def speaker_response_count(conn, form_instance_id):
    return conn.execute("SELECT COUNT(*) FROM response WHERE form_instance_id=?",
                        (form_instance_id,)).fetchone()[0]


def delete_event_speaker(conn, event_id, form_instance_id):
    """Remove a speaker that has NO responses (hard delete + unlink). Refuses while
    any response exists, so collected ratings are never silently destroyed — the
    caller should keep it or archive the whole activity instead. Returns True if
    deleted, False if blocked/not found."""
    if not _form_in_event(conn, event_id, form_instance_id):
        return False
    if speaker_response_count(conn, form_instance_id):
        return False
    conn.execute("DELETE FROM event_form WHERE event_id=? AND form_instance_id=?",
                 (event_id, form_instance_id))
    conn.execute("DELETE FROM form_instance WHERE id=?", (form_instance_id,))
    conn.commit()
    return True


def close_event_now(conn, event_id):
    """Close the activity for good (until reopened): on every non-archived form set
    close_at=now (stops the public link) AND encoding_locked=1 (stops paper entry and
    drops it from the /encode picker). A hard stop on both surfaces, reversible via
    reopen_event_now. Returns rows updated."""
    cur = conn.execute("""
        UPDATE form_instance SET close_at=?, encoding_locked=1
        WHERE COALESCE(archived, 0) = 0
          AND id IN (SELECT form_instance_id FROM event_form WHERE event_id = ?)
    """, (tz.now_iso(), event_id))
    conn.commit()
    return cur.rowcount


def reopen_event_now(conn, event_id):
    """Reverse close_event_now: clear close_at and unlock encoding on every
    non-archived form, so both the public link and paper entry resume. Used to
    back-enter a late form or correct a typo, after which the activity is closed
    again. Returns rows updated."""
    cur = conn.execute("""
        UPDATE form_instance SET close_at=NULL, encoding_locked=0
        WHERE COALESCE(archived, 0) = 0
          AND id IN (SELECT form_instance_id FROM event_form WHERE event_id = ?)
    """, (event_id,))
    conn.commit()
    return cur.rowcount


def event_is_closed(conn, event_id):
    """True when the activity has been explicitly closed — it has at least one
    non-archived form and every one of them is locked to encoding. This is the
    signal close_event_now sets and reopen_event_now clears; a merely-elapsed
    response window does NOT count (back-entry there stays allowed)."""
    row = conn.execute("""
        SELECT COUNT(*), SUM(COALESCE(encoding_locked, 0))
        FROM form_instance
        WHERE COALESCE(archived, 0) = 0
          AND id IN (SELECT form_instance_id FROM event_form WHERE event_id = ?)
    """, (event_id,)).fetchone()
    total, locked = (row[0] or 0), (row[1] or 0)
    return total > 0 and locked == total


def set_event_archived(conn, event_id, archived):
    """Archive (hide from every list, feed and analytic) or restore all of an
    event's forms. Archiving is the reversible 'put it away' action; it keeps the
    rows but drops them from reports. Returns rows updated."""
    cur = conn.execute("""
        UPDATE form_instance SET archived=?
        WHERE id IN (SELECT form_instance_id FROM event_form WHERE event_id = ?)
    """, (1 if archived else 0, event_id))
    conn.commit()
    return cur.rowcount


def set_form_archived(conn, form_instance_id, archived):
    """Archive (hide from every list, feed and analytic) or restore a single form
    instance. The standalone-activity counterpart to `set_event_archived` — used for
    forms that have NO event record, so the event-level archive can't reach them.
    Keeps the row; just flips the reversible `archived` flag. Returns rows updated."""
    cur = conn.execute(
        "UPDATE form_instance SET archived=? WHERE id=?",
        (1 if archived else 0, form_instance_id))
    conn.commit()
    return cur.rowcount


def lock_all_forms_for_encoding(conn):
    """Close every non-archived event/speaker form to new paper encoding.
    Locked forms vanish from the encode picker but remain in all reports/analytics.
    Returns the number of forms locked."""
    cur = conn.execute(
        "UPDATE form_instance SET encoding_locked=1 "
        "WHERE survey_type IN (2, 3) AND COALESCE(archived, 0) = 0 "
        "AND COALESCE(encoding_locked, 0) = 0"
    )
    conn.commit()
    return cur.rowcount


def form_archive_info(conn, form_instance_id):
    """Everything the per-form archive route needs to authorize and act on a single
    form: its creator (for the ownership check), current archived state, and whether
    it belongs to an event (in which case the route refuses — bureau/outside events
    archive at the event level). Returns None if the form does not exist."""
    row = conn.execute("""
        SELECT fi.created_by, fi.qr_token, fi.topic, fi.survey_type,
               COALESCE(fi.archived, 0),
               (SELECT 1 FROM event_form ef WHERE ef.form_instance_id = fi.id LIMIT 1)
        FROM form_instance fi WHERE fi.id = ?
    """, (form_instance_id,)).fetchone()
    if not row:
        return None
    return {"created_by": row[0], "qr_token": row[1], "topic": row[2],
            "survey_type": row[3], "archived": bool(row[4]),
            "has_event": row[5] is not None}


def event_for_form_instance(conn, form_instance_id):
    """The event a form belongs to (its header — title, organizer, kind …), or None.
    Lets the combined single-page survey title itself with the activity name."""
    row = conn.execute(
        "SELECT event_id FROM event_form WHERE form_instance_id=? LIMIT 1",
        (form_instance_id,)).fetchone()
    return get_event_by_id(conn, row[0]) if row else None


def event_response_total(conn, event_id):
    """Total responses across an event's non-archived forms."""
    return conn.execute("""
        SELECT COUNT(*) FROM response r
        JOIN event_form ef ON ef.form_instance_id = r.form_instance_id
        JOIN form_instance fi ON fi.id = ef.form_instance_id
        WHERE ef.event_id = ? AND COALESCE(fi.archived, 0) = 0
    """, (event_id,)).fetchone()[0]


def event_report_url(conn, event_id):
    """The best report link for a managed activity, or None if it has no live forms.
    A bureau activity whose Form-2 review has answers opens its per-activity SERVQUAL
    report (/reports/activities/{repr}); a Form-3-only or RP-answered-only activity
    opens its resource-person results in the Type-3 report. The choice follows where
    the responses actually are (not merely which forms exist), so the link matches
    what build_events renders and never lands on an empty per-activity report.

    `repr` is the build_events representative id = min(non-archived form_instance id)
    — the id BOTH report routes match (NOT the event-table id); see
    event_rp_results_url."""
    rows = conn.execute(
        "SELECT fi.id, fi.survey_type, "
        "       EXISTS(SELECT 1 FROM response r WHERE r.form_instance_id = fi.id) "
        "FROM event_form ef JOIN form_instance fi ON fi.id = ef.form_instance_id "
        "WHERE ef.event_id = ? AND COALESCE(fi.archived, 0) = 0", (event_id,)).fetchall()
    if not rows:
        return None
    repr_id = min(r[0] for r in rows)
    f2_has_resp = any(r[1] == 2 and r[2] for r in rows)
    f3_has_resp = any(r[1] == 3 and r[2] for r in rows)
    has_f2_form = any(r[1] == 2 for r in rows)
    # Form-2 side answered → the per-activity report. Otherwise the RP results, if
    # any. A yet-unanswered bureau activity defaults to its (empty) per-activity
    # report; the caller only surfaces the link once there are responses anyway.
    if f2_has_resp or (has_f2_form and not f3_has_resp):
        return f"/reports/activities/{repr_id}"
    return f"/reports?type=3&activity={repr_id}"


def event_rp_results_url(conn, event_id):
    """Deep link to the Resource Persons report (Type-3) narrowed to ONE event's
    activity, or None if the event has no live RP forms yet.

    An outside (invited) activity is Form-3-only — it has resource-person reviews but
    no Form-2 event report, so the per-activity SERVQUAL report (/reports/activities/{id})
    404s for it. Its RP scores live in the Type-3 report's Activity filter instead. That
    filter matches an event's `build_events` representative id, which is
    `min(non-archived form_instance id)` (see dashboard_insights.build_events) — NOT the
    event-table id. So compute the same id and hand back the filtered-report URL."""
    row = conn.execute(
        "SELECT MIN(fi.id) FROM event_form ef "
        "JOIN form_instance fi ON fi.id = ef.form_instance_id "
        "WHERE ef.event_id = ? AND COALESCE(fi.archived, 0) = 0", (event_id,)).fetchone()
    fid = row[0] if row else None
    return f"/reports?type=3&activity={fid}" if fid else None


# Below this many responses the demographic mix is hidden, so a handful of answers
# can't single anyone out (outside activities have no roster to fall back on).
MIN_DEMOG_N = 5


def outside_response_tracker(conn, event_id):
    """Anonymous response tracking for an outside activity. There are NO identities
    (outside surveys capture none) — only per-speaker counts, the arrival timing, and
    the sex / affiliation MIX read from the per-response SEX / AFFIL items. The mix is
    suppressed below MIN_DEMOG_N responses for anonymity."""
    speakers = conn.execute("""
        SELECT fi.topic, rp.name,
               (SELECT COUNT(*) FROM response r WHERE r.form_instance_id = fi.id),
               (SELECT MAX(r.submitted_at) FROM response r WHERE r.form_instance_id = fi.id)
        FROM event_form ef
        JOIN form_instance fi ON fi.id = ef.form_instance_id
        LEFT JOIN resource_person rp ON rp.id = fi.rp_id
        WHERE ef.event_id = ? AND fi.survey_type = 3 AND COALESCE(fi.archived, 0) = 0
        ORDER BY ef.ordinal, fi.id
    """, (event_id,)).fetchall()
    sp = [{"topic": r[0], "rp_name": r[1], "responses": r[2], "last_at": r[3]}
          for r in speakers]
    total = sum(s["responses"] for s in sp)

    base = ("""
        FROM response r
        JOIN event_form ef ON ef.form_instance_id = r.form_instance_id
        JOIN form_instance fi ON fi.id = ef.form_instance_id
        WHERE ef.event_id = ? AND fi.survey_type = 3 AND COALESCE(fi.archived, 0) = 0
    """)
    span = conn.execute("SELECT MIN(r.submitted_at), MAX(r.submitted_at) " + base,
                        (event_id,)).fetchone()
    by_day = conn.execute(
        "SELECT date(r.submitted_at) AS d, COUNT(*) " + base +
        " GROUP BY d ORDER BY d DESC LIMIT 14", (event_id,)).fetchall()

    def _mix(item_id, keys):
        rows = conn.execute(
            "SELECT UPPER(ir.text), COUNT(*) FROM item_remark ir "
            "JOIN response r ON r.id = ir.response_id "
            "JOIN event_form ef ON ef.form_instance_id = r.form_instance_id "
            "JOIN form_instance fi ON fi.id = ef.form_instance_id "
            "WHERE ef.event_id = ? AND fi.survey_type = 3 AND COALESCE(fi.archived,0)=0 "
            "AND ir.item_id = ? GROUP BY UPPER(ir.text)",
            (event_id, item_id)).fetchall()
        counts = {k: 0 for k in keys}
        known = 0
        for text, n in rows:
            if text in counts:
                counts[text] += n
                known += n
        counts["Unknown"] = max(0, total - known)
        return counts

    suppressed = total < MIN_DEMOG_N
    return {
        "speakers": sp, "total": total,
        "first_at": span[0], "last_at": span[1],
        "by_day": [{"day": d, "n": n} for d, n in by_day],
        "demographics_suppressed": suppressed, "min_demog_n": MIN_DEMOG_N,
        "sex": None if suppressed else _mix("SEX", ["M", "F"]),
        "affiliation": None if suppressed else _mix("AFFIL", ["DOH", "NON-DOH"]),
    }


# --- Comment raffle ---------------------------------------------------------
# Draw a random winner from everyone who left a real comment. Works for bureau and
# outside ("invited") activities, face-to-face AND online. The only difference is
# identity — a registered attendee's response carries their name; an anonymous or
# online response is identified by a CLAIM CODE shown to them on the thank-you
# screen (which they present, e.g. in chat, to claim). The code is DERIVED from the
# response id (never stored), so the screen and a later draw always agree.

# Unambiguous alphabet — no 0/O or 1/I to misread when read aloud or off a phone.
_RAFFLE_ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"


def claim_code(response_id):
    """A short, stable, human-readable raffle ticket for a response. Deterministic
    (the thank-you screen and the draw must agree) and non-sequential (so one
    entrant can't read a neighbour's code off the next id). It is a DISPLAY label
    only — the draw's source of truth is always the response id."""
    h = hashlib.sha256(f"css-raffle:{int(response_id)}".encode()).digest()
    n = int.from_bytes(h[:8], "big")
    out = []
    for _ in range(5):
        out.append(_RAFFLE_ALPHABET[n % 32])
        n //= 32
    return "".join(out)


# item_remark rows that are demographic tallies, not a free-text comment.
_DEMOG_ITEMS = ("SEX", "AFFIL")


def set_event_raffle(conn, event_id, enabled, prize=None):
    """Turn the comment raffle on/off for an activity and set its (optional) prize
    label. Blank prize is stored as NULL."""
    conn.execute("UPDATE event SET raffle_enabled = ?, raffle_prize = ? WHERE id = ?",
                 (1 if enabled else 0, (prize or "").strip() or None, event_id))
    conn.commit()


def raffle_pool(conn, event_id):
    """Eligible raffle entries for an activity: one per response that carries a real
    free-text comment (the overall remark, or an item note that is not a demographic
    tally). Archived forms are excluded. Both face-to-face and ONLINE responses are
    entered — an online entrant is identified by their claim code on the thank-you
    screen exactly like an anonymous walk-in, which they present (e.g. in chat) to
    claim a prize.

    Each entry gets its stable claim code and, when the response came through
    registration, the attendee's name (None when anonymous or after a retention
    purge — the code is then the only identifier). Returns oldest-first."""
    rows = conn.execute("""
        SELECT r.id, r.submitted_at, r.remarks, fi.topic, a.name, a.email
        FROM response r
        JOIN event_form ef    ON ef.form_instance_id = r.form_instance_id
        JOIN form_instance fi ON fi.id = ef.form_instance_id
        LEFT JOIN attendee a  ON a.id = r.attendee_id
        WHERE ef.event_id = ?
          AND COALESCE(fi.archived, 0) = 0
        ORDER BY r.id
    """, (event_id,)).fetchall()
    # Free-text item notes (excluding the SEX/AFFIL demographic items), so a
    # response whose only words are a per-item note still counts as a commenter.
    qmarks = ",".join("?" * len(_DEMOG_ITEMS))
    notes = {}
    for rid, text in conn.execute(f"""
            SELECT ir.response_id, ir.text
            FROM item_remark ir
            JOIN response r       ON r.id = ir.response_id
            JOIN event_form ef    ON ef.form_instance_id = r.form_instance_id
            WHERE ef.event_id = ? AND ir.item_id NOT IN ({qmarks})
            ORDER BY ir.response_id, ir.item_id""",
            (event_id, *_DEMOG_ITEMS)):
        if (text or "").strip():
            notes.setdefault(rid, []).append(text.strip())
    pool = []
    for rid, when, remarks, topic, name, email in rows:
        comment = (remarks or "").strip() or " · ".join(notes.get(rid, []))
        if not comment:
            continue
        pool.append({"response_id": rid, "code": claim_code(rid),
                     "name": (name or "").strip() or None,
                     "email": (email or "").strip() or None,
                     "comment": comment, "topic": topic,
                     "when": (when or "")[:16].replace("T", " ")})
    return pool


def raffle_drawn_ids(conn, event_id):
    """response_ids already drawn as winners for this activity (so a multi-prize
    draw can avoid repeating)."""
    return {r[0] for r in conn.execute(
        "SELECT response_id FROM raffle_draw WHERE event_id = ?", (event_id,))}


def raffle_record_draw(conn, event_id, response_id, prize=None, drawn_by=None):
    """Record that a response won a raffle draw."""
    conn.execute(
        "INSERT INTO raffle_draw(event_id, response_id, prize, drawn_at, drawn_by) "
        "VALUES (?,?,?,?,?)",
        (event_id, response_id, (prize or "").strip() or None,
         tz.now_iso(), drawn_by))
    conn.commit()


def raffle_winners(conn, event_id):
    """Past draws for an activity, newest first, each resolved to the winner's
    claim code, name (if any) and comment — the history shown on the draw screen."""
    out = []
    for rid, prize, drawn_at, drawn_by in conn.execute(
            "SELECT response_id, prize, drawn_at, drawn_by FROM raffle_draw "
            "WHERE event_id = ? ORDER BY id DESC", (event_id,)):
        r = conn.execute(
            "SELECT r.remarks, a.name FROM response r "
            "LEFT JOIN attendee a ON a.id = r.attendee_id WHERE r.id = ?",
            (rid,)).fetchone()
        out.append({"response_id": rid, "code": claim_code(rid),
                    "name": (r[1] if r and r[1] else None),
                    "comment": (r[0] if r else None), "prize": prize,
                    "drawn_by": drawn_by,
                    "when": (drawn_at or "")[:16].replace("T", " ")})
    return out


def raffle_reset(conn, event_id):
    """Clear all recorded draws for an activity (start the raffle over). Returns
    how many draws were removed."""
    n = conn.execute("DELETE FROM raffle_draw WHERE event_id = ?",
                     (event_id,)).rowcount
    conn.commit()
    return n


_LOAD_SQL = """
SELECT
  a.response_id                                   AS response_id,
  fi.survey_type                                  AS survey_type,
  fi.form                                         AS form,
  a.item_id                                       AS item_id,
  a.value                                         AS value,
  a.is_na                                         AS is_na,
  -- Identity columns the insight dashboard slices on (the engine ignores extras):
  --   form_instance_id -> group the atoms of one event/form together
  --   rp_id            -> the resource person being rated (Type 3)
  --   served_by_rp_id  -> the staff member a walk-in client says served them (Type 1)
  fi.id                                           AS form_instance_id,
  fi.rp_id                                        AS rp_id,
  r.served_by_rp_id                               AS served_by_rp_id,
  CASE fi.survey_type
       -- Type 1: who served comes from the response (standing walk-in) first,
       -- falling back to a dated form's baked staff for older/seeded records.
       WHEN 1 THEN 'staff:'    || COALESCE(sb.name, fi.serving_staff, '?')
       WHEN 2 THEN 'activity:' || fi.id
       WHEN 3 THEN 'rp:' || COALESCE(rp.id,0) || ':' || COALESCE(fi.topic,'-')
  END                                             AS rateable_unit,
  CASE fi.survey_type
       WHEN 1 THEN COALESCE(osb.path, ostaff.path, 'Bureau')
       WHEN 2 THEN olead.path
       WHEN 3 THEN CASE WHEN rp.is_internal=1 THEN orp.path ELSE 'External' END
  END                                             AS org_path,
  CASE WHEN fi.survey_type=3 THEN rp.is_internal ELSE NULL END AS rp_internal,
  CASE
       WHEN fi.survey_type IN (1,2)            THEN 'internal'
       WHEN fi.organizer_external_id IS NOT NULL THEN 'external'
       ELSE 'internal'
  END                                             AS organizer_type,
  CASE
       WHEN fi.organizer_external_id IS NOT NULL THEN xo.name
       WHEN fi.survey_type=2                     THEN olead.name
       WHEN fi.survey_type=3                     THEN COALESCE(olead.name,'Bureau')
       ELSE 'Bureau'
  END                                             AS organizer_ref,
  fi.topic                                        AS topic,
  fi.service                                      AS service,
  -- Delivery format, for the Trends segment-split (online vs face-to-face).
  -- NULL = legacy face-to-face, so coalesce to 'f2f' to keep the column clean.
  COALESCE(fi.modality, 'f2f')                    AS modality,
  -- A standing walk-in (Type 1 with no baked staff) counts in the period of the
  -- transaction itself, i.e. when the client submitted. Dated forms keep their
  -- event_date. This honours "count in the EVENT period", where for a walk-in
  -- the event IS the transaction.
  CASE WHEN fi.survey_type=1 AND fi.serving_staff IS NULL
       THEN substr(r.submitted_at, 1, 10)
       ELSE fi.event_date
  END                                             AS event_date,
  COALESCE(fi.pooled, 0)                          AS pooled
FROM answer a
JOIN response r        ON r.id  = a.response_id
JOIN form_instance fi  ON fi.id = r.form_instance_id
LEFT JOIN resource_person rp ON rp.id = fi.rp_id
LEFT JOIN resource_person sb ON sb.id = r.served_by_rp_id
LEFT JOIN org_unit ostaff    ON ostaff.id = fi.serving_staff_org_id
LEFT JOIN org_unit osb       ON osb.id   = sb.org_unit_id
LEFT JOIN org_unit olead     ON olead.id  = fi.lead_org_id
LEFT JOIN org_unit orp       ON orp.id    = rp.org_unit_id
LEFT JOIN external_organizer xo ON xo.id  = fi.organizer_external_id
WHERE COALESCE(fi.archived, 0) = 0          -- archived forms vanish from all analytics
  AND r.archived_at IS NULL                 -- archived individual responses too (Type-1 entries)
"""


def load_atoms(conn, after_answer_id=None, upto_answer_id=None):
    """Return the atoms table in exactly the shape css_is_engine expects.

    after_answer_id: if given, load ONLY answers with id > that value
    (an incremental append). The transform is row-independent — assign_periods
    derives each row's period from its own event_date — so an incremental frame
    concatenates cleanly onto a previously built one (old + new == full).

    upto_answer_id: if given, load ONLY answers with id <= that value. The caller
    snapshots MAX(answer.id) BEFORE loading and passes it here, so the frame it
    gets back covers EXACTLY answers up to that id — never a moving target. Pairing
    the frame with the same high-water mark it was bounded to is what keeps the
    incremental cache honest: any answer another connection commits after the
    snapshot is > that id, excluded from this frame, and picked up cleanly by the
    next (after_answer_id=that id) append instead of being silently skipped."""
    sql = _LOAD_SQL
    if after_answer_id is not None:
        # int() guard — never interpolate untrusted text into SQL.
        sql = sql + f"\n  AND a.id > {int(after_answer_id)}"
    if upto_answer_id is not None:
        sql = sql + f"\n  AND a.id <= {int(upto_answer_id)}"
    df = pd.read_sql_query(sql, conn)
    df["event_date"] = df["event_date"].astype(str)
    df["value"] = pd.to_numeric(df["value"], errors="coerce")
    df["is_na"] = df["is_na"].map({1: True, 0: False}).fillna(False).astype(bool)
    return _categorize_atoms(eng.assign_periods(df))


# Low-cardinality label/grouping columns. Stored as `category` they cut the live
# atoms frame ~12x (≈353 MB → ≈30 MB on the production data) and make every
# dashboard/report groupby ~2-3x faster, because grouping on small integer codes
# beats grouping on strings. They are pure labels here — no arithmetic, and every
# order-sensitive caller already does its own sorted()/.sort(), so category order
# never leaks into output. Identity/measure columns (response_id, value, *_id,
# rp_internal, pooled, is_na) stay native.
# NOTE: event_date is deliberately NOT here. It's a label by cardinality but it's
# used in ORDERED ops — `ed >= since` window filters, .min()/.max() date spans —
# which an *unordered* categorical rejects. Keeping it a plain ISO string (which
# sorts chronologically) preserves those ops; it's not a groupby key anyway (the
# period columns derived from it are). Every column below is pure equality/groupby.
_ATOMS_CAT_COLS = (
    "organizer_ref", "topic", "org_path", "rateable_unit",
    "organizer_type", "semester", "month", "quarter", "year", "modality",
    "form", "item_id", "service", "served_by_rp_id",
)


def _categorize_atoms(df):
    """Downcast the label columns to `category` in place. Safe on a fresh full
    frame and on the small incremental delta alike — concat_atoms() re-unions the
    categories so an append stays equal to a from-scratch build (dtype included)."""
    for c in _ATOMS_CAT_COLS:
        if c in df.columns and not isinstance(df[c].dtype, pd.CategoricalDtype):
            df[c] = df[c].astype("category")
    return df


def concat_atoms(base, add):
    """Append an incremental atoms delta onto the cached base frame, PRESERVING
    the `category` dtypes that a plain pd.concat would silently collapse (pandas
    3.0 widens mismatched categoricals to str). Cost is ~O(len(add)), not the
    whole frame: union_categoricals fuses the two category sets without rescanning
    base's codes. The result equals _categorize_atoms(full_rebuild) exactly —
    same values, same dtypes — which is the incremental≡full contract the atoms
    cache relies on (see tests/test_atoms_cache.py)."""
    if add is None or not len(add):
        return base
    from pandas.api.types import union_categoricals
    cols = {}
    for c in base.columns:
        b, a = base[c], add[c]
        if isinstance(b.dtype, pd.CategoricalDtype):
            av = a.array if isinstance(a.dtype, pd.CategoricalDtype) else a.astype(b.dtype).array
            cols[c] = union_categoricals([b.array, av])
        else:
            cols[c] = pd.concat([b, a], ignore_index=True).array
    return pd.DataFrame(cols)


# =====================================================================
# Avatar companions — the named pet each staff member adopts at onboarding.
# The SAME companion is the wellness module's growth mascot: an account picks a
# SPECIES (avatar_kind) and NAMES it (avatar_name); the wellness point level
# (1..6) is the growth STAGE the chosen species is drawn at. One companion
# means the profile pet and the wellness mascot can never disagree. The art
# itself is inline SVG in templates/_avatars.html (no external assets — keeps
# the PWA offline-safe); here we keep only the catalog metadata and the
# per-family stage-name arrays.
# =====================================================================

# Growth-stage names, one array of 6 per FAMILY, indexed by stage-1 (stage is
# 1..6). Plants keep the original wellness vocabulary; animals grow through
# their own life stages, both ending at "Flourishing".
AVATAR_STAGE_NAMES = {
    "plant":  ["Seed", "Sprout", "Seedling", "Budding", "In bloom", "Flourishing"],
    "animal": ["Hatchling", "Little one", "Growing", "Spirited", "Full-grown", "Flourishing"],
}

# The species a staff member may adopt. `family` selects the stage-name array
# and the idle-animation style; `label` is what the picker shows and `blurb` is
# the one-line personality note under it. List order is picker order. Adding a
# species = one row here + its SVG macro in _avatars_art.html + its behavior
# entry in static/js/avatars.js.
AVATAR_CATALOG = [
    {"key": "plant",      "label": "Blossom plant", "family": "plant",
     "blurb": "Classic — sways and blooms"},
    {"key": "cactus",     "label": "Cactus",        "family": "plant",
     "blurb": "Tough — thrives on little"},
    {"key": "bonsai",     "label": "Bonsai",        "family": "plant",
     "blurb": "Patient — shaped over years"},
    {"key": "sunflower",  "label": "Sunflower",     "family": "plant",
     "blurb": "Cheerful — follows the light"},
    {"key": "fern",       "label": "Fern",          "family": "plant",
     "blurb": "Graceful — fronds ripple"},
    {"key": "mushroom",   "label": "Mushroom",      "family": "plant",
     "blurb": "Quirky — wobbles and puffs"},
    {"key": "succulent",  "label": "Succulent",     "family": "plant",
     "blurb": "Chill — barely bothered"},
    {"key": "cat",        "label": "Cat",           "family": "animal",
     "blurb": "Independent — flicks and stretches"},
    {"key": "bird",       "label": "Bird",          "family": "animal",
     "blurb": "Chirpy — hops and preens"},
    {"key": "turtle",     "label": "Turtle",        "family": "animal",
     "blurb": "Steady — slow but sure"},
    {"key": "dog",        "label": "Dog",           "family": "animal",
     "blurb": "Loyal — wags and jumps"},
    {"key": "rabbit",     "label": "Rabbit",        "family": "animal",
     "blurb": "Shy — twitches and peeks"},
    {"key": "fish",       "label": "Fish",          "family": "animal",
     "blurb": "Serene — glides and bubbles"},
    {"key": "dolphin",    "label": "Dolphin",       "family": "animal",
     "blurb": "Joyful — swims and leaps"},
    {"key": "owl",        "label": "Owl",           "family": "animal",
     "blurb": "Watchful — follows your pointer"},
    {"key": "bat",        "label": "Bat",           "family": "animal",
     "blurb": "Playful — flies around"},
]
AVATAR_KEYS = {a["key"] for a in AVATAR_CATALOG}
AVATAR_DEFAULT = "plant"          # accounts that never chose keep the classic plant
AVATAR_NAME_MAXLEN = 24
_AVATAR_FAMILY = {a["key"]: a["family"] for a in AVATAR_CATALOG}
# Species that live in water and roam by swimming (avatars.js glides them around
# a fixed home-water backdrop). Kept here so the template and the JS can never
# disagree on who gets the water surface drawn behind them.
AVATAR_SWIMMERS = {"fish", "dolphin"}


def valid_avatar_kind(kind):
    """True if `kind` is a species we know how to draw."""
    return kind in AVATAR_KEYS


def avatar_family(kind):
    """The family ('plant' / 'animal') of a species key. Unknown/None keys fall
    back to the default species' family, so callers never KeyError."""
    return _AVATAR_FAMILY.get(kind, _AVATAR_FAMILY[AVATAR_DEFAULT])


def avatar_is_swimmer(kind):
    """True for water species (fish, dolphin) — the ones avatars.js swims around
    a static home-water backdrop. avatar_svg draws that backdrop OUTSIDE the
    roaming layer so it stays put while the creature glides."""
    return kind in AVATAR_SWIMMERS


def clean_avatar_name(name):
    """Trim + length-cap a pet name for storage. Returns '' for blank input."""
    return (name or "").strip()[:AVATAR_NAME_MAXLEN]


def avatar_stage_name(kind, stage):
    """The growth-stage label (e.g. 'In bloom') for a species at a 1..6 stage.
    Clamps out-of-range stages so gamification drift can never index-error."""
    names = AVATAR_STAGE_NAMES[avatar_family(kind)]
    idx = max(1, min(int(stage or 1), len(names))) - 1
    return names[idx]


# --- Companion mood (cosmetic care layer) ------------------------------------
# Watering a plant / feeding an animal stamps admin_user.avatar_last_care_at;
# the mood is DERIVED from how long ago that was, on every read, exactly like
# the wellness stage is derived from points — nothing else persists. Mood never
# feeds back into points or stage: neglecting the pet only makes it droop.

AVATAR_CARE_COOLDOWN_HOURS = 6    # care counts at most once per window
AVATAR_MOOD_HAPPY_HOURS = 24      # cared for within a day  -> happy
AVATAR_MOOD_OKAY_HOURS = 72       # within three days       -> okay; beyond -> droopy
AVATAR_MOODS = ("happy", "okay", "droopy")


def _parse_care_ts(value):
    """A stored care stamp as a datetime, or None for blank/garbage — never
    raises, so a hand-edited DB can't break every profile read."""
    try:
        return datetime.fromisoformat(value) if value else None
    except (TypeError, ValueError):
        return None


def avatar_mood(last_care_at, now=None):
    """'happy' / 'okay' / 'droopy' from the last-care stamp. A pet never cared
    for starts droopy — the first watering/feeding is the hook."""
    last = _parse_care_ts(last_care_at)
    if not last:
        return "droopy"
    age = (now or tz.now_local()) - last
    if age < timedelta(hours=AVATAR_MOOD_HAPPY_HOURS):
        return "happy"
    if age < timedelta(hours=AVATAR_MOOD_OKAY_HOURS):
        return "okay"
    return "droopy"


def avatar_care_verb(kind):
    """What caring for this species means: plants are watered, animals fed."""
    return "water" if avatar_family(kind) == "plant" else "feed"


def avatar_accessory_month():
    """Current month 1..12 (PH wall-clock) — picks the companion's seasonal
    accessory. A function, not a constant, so a long-running process rolls
    over at midnight of the 1st without a restart."""
    return tz.now_local().month


# The bureau's full name as it must read on any official form we generate
# (the wellness Annex A register, the ANNEX C work arrangement schedule).
# One constant so two forms can never drift apart.
BUREAU_NAME = "Bureau of Local Health Systems Development"


# =====================================================================
# Org chain of command — shared approval routing.
#
# Who approves you is a fact about the ORG CHART, not about what you are
# asking for, so this block is shared by every module that needs a decision
# routed upwards: the wellness break (DM 2025-0135) and the semi-monthly
# work arrangement schedule (ANNEX C) both hang off it. Keeping one copy is
# deliberate — the rank-matching rules below encode a bug that took a round
# trip to find (see the note on _org_rank), and a second copy would be a
# second place for it to come back.
# =====================================================================

# Approval escalates by directory RANK (STAFF_ONBOARDING_AVATAR_PLAN.md §7a.2):
# staff -> section chief -> division chief -> Director, with admins the catch-all
# above the Director and for anyone off the chain. The "up one level" hop walks
# org_unit.path (section -> its parent division -> the directorate).
#
# Rank is read from BOTH `designation` and `position`, matched case-insensitively
# as a substring, because real directory data is uneven (Spot Feedback #76):
#   * section heads / division chiefs carry a clean functional `designation`
#     ("Section Head" / "Division Chief");
#   * the Director carries NO such designation — the plantilla title "Director IV"
#     lives in `position` — so an exact designation match never found them, and
#     everyone under a division chief escalated to nobody -> "an administrator".
# We deliberately do NOT match a bare "chief" in `position`: many section heads
# hold the position "Chief Health Program Officer", which must not read as a
# division chief.
def _org_rank(designation, position=None):
    d = (designation or "").strip().lower()
    p = (position or "").strip().lower()
    if "director" in d or "director" in p:
        return 3
    if "division chief" in d:
        return 2
    if "section head" in d or "section chief" in d:
        return 1
    return 0


def _org_parent_path(path):
    """The org path one level up ('A/B/C' -> 'A/B'), or None at the top."""
    return path.rsplit("/", 1)[0] if path and "/" in path else None


# ---- approver resolution ------------------------------------------------

def _org_accounts_at_rank(conn, rank, org_path=None, exclude_uid=None):
    """Active accounts whose directory role resolves to `rank` (see
    _org_rank), optionally restricted to an exact org_unit.path. The building
    block of the escalation chain. Rank is computed in Python from designation +
    position so the Director (leadership in `position`, not `designation`) is
    found like anyone else."""
    sql = ("SELECT a.id, rp.designation, rp.position FROM admin_user a "
           "JOIN resource_person rp ON rp.id = a.rp_id AND rp.is_internal = 1 "
           "LEFT JOIN org_unit ou ON ou.id = rp.org_unit_id "
           "WHERE a.active = 1 AND rp.archived_at IS NULL")
    params = []
    if org_path is not None:
        sql += " AND ou.path = ?"
        params.append(org_path)
    out = []
    for aid, desig, pos in conn.execute(sql, params).fetchall():
        if aid != exclude_uid and _org_rank(desig, pos) == rank:
            out.append(aid)
    return out


_ORG_LEVEL_RANK = {"section": 1, "division": 2, "bureau": 3}


def org_unit_chiefs(conn, org_unit_id):
    """Account ids of the chief(s) who head `org_unit_id` (its own path, not
    one level up — unlike get_approvers_for). Used to notify a section/division
    when something happens under it (e.g. a new event). [] if the unit is
    unknown or its level doesn't map to a chief rank."""
    if not org_unit_id:
        return []
    row = conn.execute("SELECT level, path FROM org_unit WHERE id=?",
                       (org_unit_id,)).fetchone()
    if not row:
        return []
    level, path = row
    rank = _ORG_LEVEL_RANK.get(level)
    if not rank:
        return []
    if rank == 3:
        # Mirror get_approvers_for's own escalation to the Director: don't
        # restrict by path, since the Director's directory record isn't
        # reliably tied to a specific org_unit.
        return _org_accounts_at_rank(conn, 3)
    return _org_accounts_at_rank(conn, rank, org_path=path)


def _org_role_filled(conn, rank, org_path=None):
    """Does ANY internal person (account or not) hold `rank` in the given unit?
    Used for the apply-page copy: we name the org-correct approver ("your division
    chief") whenever that seat is filled in the directory, even if that person has
    no app account yet — the claim still gets handled by the admin fallback until
    they're onboarded, so this tells staff who it's *for*, not who happens to be
    clickable today."""
    sql = ("SELECT rp.designation, rp.position FROM resource_person rp "
           "LEFT JOIN org_unit ou ON ou.id = rp.org_unit_id "
           "WHERE rp.is_internal = 1 AND rp.archived_at IS NULL")
    params = []
    if org_path is not None:
        sql += " AND ou.path = ?"
        params.append(org_path)
    return any(_org_rank(d, p) == rank
               for d, p in conn.execute(sql, params).fetchall())


def _org_seat_name(conn, rank, org_path=None, exclude_uid=None):
    """Name(s) of the internal person(s) filling `rank` in the given unit — the
    same seat _org_role_filled tests, but returning who holds it so the apply
    page can name the approver. Joins multiple holders with ' / '; returns None when
    the seat is empty. Names the directory person even if they have no app account
    yet (the claim still routes to the admin fallback until they're onboarded)."""
    sql = ("SELECT rp.name, rp.designation, rp.position, a.id "
           "FROM resource_person rp "
           "LEFT JOIN org_unit ou ON ou.id = rp.org_unit_id "
           "LEFT JOIN admin_user a ON a.rp_id = rp.id "
           "WHERE rp.is_internal = 1 AND rp.archived_at IS NULL")
    params = []
    if org_path is not None:
        sql += " AND ou.path = ?"
        params.append(org_path)
    names = []
    for name, desig, pos, aid in conn.execute(sql, params).fetchall():
        if aid is not None and aid == exclude_uid:
            continue
        if name and _org_rank(desig, pos) == rank and name not in names:
            names.append(name)
    return " / ".join(names) if names else None


def approver_name_for(conn, user_id):
    """The NAME of who decides THIS person's requests, for the apply/hub copy
    ('Send for approval of Ray Justin Ventura'). Mirrors approver_title_for's
    rank/org-path walk but resolves the seat-holder's name; returns None when the
    seat is unfilled or unresolvable so callers fall back to the role title."""
    me = get_admin_user_by_id(conn, user_id)
    rp = get_rp(conn, me["rp_id"]) if me and me.get("rp_id") else None
    if not rp:
        return None
    rank = _org_rank(rp.get("designation"), rp.get("position"))
    path = rp.get("org_path")
    if rank == 0:                                   # staff -> section chief (same unit)
        return _org_seat_name(conn, 1, org_path=path, exclude_uid=user_id)
    if rank == 1:                                   # section chief -> division chief (parent)
        parent = _org_parent_path(path)
        return _org_seat_name(conn, 2, org_path=parent, exclude_uid=user_id) if parent else None
    if rank == 2:                                   # division chief -> the Director
        return _org_seat_name(conn, 3, exclude_uid=user_id)
    return None


def get_approvers_for(conn, user_id):
    """Account ids that may decide this person's requests — a wellness break, a
    work arrangement, anything routed by rank — one level UP the chain of command
    (STAFF_ONBOARDING_AVATAR_PLAN.md §7a.2):
      * regular staff        -> their section chief(s), same unit
      * a section chief/head -> the division chief of the parent division
      * a division chief      -> the Director
      * the Director (or an unlinked account) -> nobody here; admins are the
        fallback (see is_approver_for).
    Never the requester themselves."""
    me = get_admin_user_by_id(conn, user_id)
    if not me or not me.get("rp_id"):
        return []
    rp = get_rp(conn, me["rp_id"])
    if not rp:
        return []
    rank = _org_rank(rp.get("designation"), rp.get("position"))
    path = rp.get("org_path")
    if rank == 0:                                   # staff -> section chief (same unit)
        return _org_accounts_at_rank(conn, 1, org_path=path, exclude_uid=user_id)
    if rank == 1:                                   # section chief -> division chief (parent)
        parent = _org_parent_path(path)
        if not parent:
            return []
        return _org_accounts_at_rank(conn, 2, org_path=parent, exclude_uid=user_id)
    if rank == 2:                                   # division chief -> the Director
        return _org_accounts_at_rank(conn, 3, exclude_uid=user_id)
    return []                                       # Director -> admin fallback


def is_approver_for(conn, user, subject_user_id):
    """May `user` (the request's user dict) decide requests filed by
    `subject_user_id`? Admins always may — they are the fallback above the
    Director and for accounts off the chain. Nobody decides their own request."""
    if user["id"] == subject_user_id:
        return False
    if user.get("role") == "admin":
        return True
    return user["id"] in get_approvers_for(conn, subject_user_id)


def user_is_approving_chief(conn, user):
    """Does this user see an approvals queue at all? Admins, plus anyone whose
    directory role can approve SOMEONE — section head/chief, division chief, or
    the Director (who decides a division chief's own requests). Rank is read from
    designation + position (see _org_rank) so the Director qualifies."""
    if user.get("role") == "admin":
        return True
    row = conn.execute("""
        SELECT rp.designation, rp.position FROM admin_user a
        JOIN resource_person rp ON rp.id = a.rp_id
        WHERE a.id=? AND rp.is_internal=1 LIMIT 1
    """, (user["id"],)).fetchone()
    return bool(row) and _org_rank(row[0], row[1]) >= 1


def pending_approval_counts(conn, user):
    """{'wellness': n, 'awa': n} — items in the two approval queues actually
    routed to this user right now. {'wellness':0,'awa':0} for anyone who isn't
    an approving chief, so callers never have to check user_is_approving_chief
    themselves first.

    Single source of truth for every place that teases "something's waiting on
    you" — the home page banner and the nav bell both call this, so neither can
    ever show a number the real queue (list_wellness_approvals /
    list_work_arrangement_approvals — the exact functions the queue pages
    themselves call) disagrees with."""
    if not user_is_approving_chief(conn, user):
        return {"wellness": 0, "awa": 0}
    return {"wellness": len(list_wellness_approvals(conn, user)),
            "awa": len(list_work_arrangement_approvals(conn, user))}


def user_can_view_work_arrangement_schedule(conn, user):
    """Who may open the team schedule and download ANNEX C.

    Every approving chief (they need the roster they decide on), plus anyone
    holding a bureau-wide work-arrangement grant — the Admin Officer who
    consolidates the fortnight's submission has to see and print every section
    without being anybody's approver.

    Kept apart from user_is_approving_chief on purpose: this grant is about
    SIGHT. Letting it decide the approvals queue as well would hand someone the
    power to approve their colleagues' schedules as a side effect of being asked
    to print them."""
    return (user_is_approving_chief(conn, user)
            or user_sees_whole_bureau(conn, user, "awa"))


def approver_title_for(conn, user_id):
    """Human label for who decides THIS person's requests, for the apply/hub copy:
    'your section chief' / 'your division chief' / 'the Director', or 'an
    administrator' at the top of the chain / for an unlinked account.

    This names the org-correct approver as long as that seat is FILLED in the
    directory (see _org_role_filled) — it doesn't require that person to have
    an app account yet. That's deliberate (Spot Feedback #76): a section head used
    to read "an administrator" because their division chief wasn't onboarded,
    which hid the real chain. Until the chief is onboarded the claim is still
    handled by the admin fallback; the copy just tells staff who it's *for*."""
    me = get_admin_user_by_id(conn, user_id)
    rp = get_rp(conn, me["rp_id"]) if me and me.get("rp_id") else None
    if not rp:
        return "an administrator"
    rank = _org_rank(rp.get("designation"), rp.get("position"))
    path = rp.get("org_path")
    if rank == 0 and _org_role_filled(conn, 1, org_path=path):
        return "your section chief"
    if rank == 1:
        parent = _org_parent_path(path)
        if parent and _org_role_filled(conn, 2, org_path=parent):
            return "your division chief"
    if rank == 2 and _org_role_filled(conn, 3):
        return "the Director"
    return "an administrator"


def team_scope_for_user(conn, user, *, area=None):
    """(scope_path, kind) for a page that shows one person their TEAM.

    Returns kind "unit" (scope_path is an org_unit.path subtree), "bureau"
    (scope_path None — everyone), or "none" (no team at all).

    THE DIRECTORY DECIDES THE TEAM, NOT THE ACCOUNT ROLE. Where someone sits on
    the org chart is a fact about the bureau; "admin" is a fact about what the
    app lets them administer, and the two answer different questions. This used
    to short-circuit on role == "admin" and hand back the whole bureau, so a
    section head who also administers the app opened the wellness register and
    the AWA schedule on all five sections instead of their own — the team view
    stopped being a team view for exactly the people most likely to hold the
    admin role. Resolving the directory FIRST fixes that at the source, for every
    caller at once, rather than page by page.

    The order is therefore:

      * an explicit bureau_access grant covering `area` -> "bureau". This is the
        one deliberate way past your own unit (BUREAU_ACCESS_LEVELS): granted per
        account in Admin -> Users, audited, revocable. Callers pass the area they
        are showing ("awa" / "wellness"), so a work-arrangement grant widens the
        ANNEX C and nothing else; a view spanning modules passes no area and is
        widened only by the full 'all' grant.
      * linked to a directory person holding the DIRECTOR seat (org rank 3) ->
        "bureau". The Director's team really is the whole bureau, and their own
        unit (the Office of the Director) is not it.
      * linked to a directory person with an org unit -> "unit", that unit's
        subtree. A section head gets their section, a division chief their whole
        division — whatever their app role happens to be.
      * anyone else -> "none". Including an admin: the role stopped being a way
        to see everyone, and a system administrator with no seat on the org chart
        now gets the grant above instead — same reach, named and revocable rather
        than implied.

    The "none" case is why this function exists at all: _org_scope_for_user
    collapses "no team" and "the whole bureau" onto the same None, and
    _path_in_scope(path, None) is True for everything. That is safe for the
    monitoring pages, which sit behind a route guard (user_is_approving_chief)
    that has already excluded unlinked staff — but a landing page shown to EVERY
    signed-in user has no such guard by design, so an unlinked account has to
    resolve to "none" here and its caller must render a personal view, never a
    bureau-wide roster of everyone's filings."""
    if user_sees_whole_bureau(conn, user, area):
        return None, "bureau"
    row = conn.execute("""
        SELECT ou.path, rp.designation, rp.position
        FROM admin_user a
        JOIN resource_person rp ON rp.id = a.rp_id
        LEFT JOIN org_unit ou ON ou.id = rp.org_unit_id
        WHERE a.id = ? AND rp.archived_at IS NULL LIMIT 1
    """, (user["id"],)).fetchone() if user else None
    if row:
        path, designation, position = row
        if _org_rank(designation, position) >= 3:      # the Director
            return None, "bureau"
        if path:
            return path, "unit"
    return None, "none"


def _org_scope_for_user(conn, user, *, area=None):
    """The org_unit.path a viewer's monitoring is limited to, or None for the
    whole bureau — team_scope_for_user's answer with the "no team" case folded
    back onto None.

    Every caller of THIS name sits behind a chief-only route guard, so folding
    "none" onto "bureau-wide" is safe here and only here; anything shown to every
    signed-in user must call team_scope_for_user and handle "none" itself.

    `area` names the module being shown so a per-area grant can widen it — see
    team_scope_for_user."""
    scope, _kind = team_scope_for_user(conn, user, area=area)
    return scope


def _path_in_scope(path, scope_path):
    """Is org path `path` inside `scope_path` (that unit or a descendant)? A None
    scope means bureau-wide, so everything is in scope."""
    if not scope_path:
        return True
    return path == scope_path or (bool(path) and path.startswith(scope_path + "/"))


# =====================================================================
# Wellness module — the DOH DM 2025-0135 two-hour weekly wellness break.
# Claims are filed in 1-hour slots (max 2/week), approved by the claimant's
# section chief (resolved through the directory), closed out with a short
# reflection, and rolled up for the Administrative Service's monitoring
# register. Gamification (points / level / streak / avatar stage) is DERIVED
# from the claim + reflection rows on every read — only badge awards persist —
# so the fun layer can never drift out of sync with the underlying record.
# =====================================================================

# The approval chain is shared org-chart machinery (see "Org chain of
# command" above). These names are kept because the wellness call sites in
# app.py, its templates and its test suite all speak them — they are bound to
# the SAME functions, not copies of them.
_wellness_rank             = _org_rank
_wellness_parent_path      = _org_parent_path
_wellness_accounts_at_rank = _org_accounts_at_rank
_wellness_role_filled      = _org_role_filled
_wellness_seat_name        = _org_seat_name
_wellness_dashboard_scope  = _org_scope_for_user
_wellness_in_scope         = _path_in_scope
wellness_approver_name     = approver_name_for
get_wellness_approvers     = get_approvers_for
is_wellness_approver       = is_approver_for
user_is_wellness_chief     = user_is_approving_chief
wellness_approver_title    = approver_title_for

WELLNESS_WEEKLY_HOURS = 2          # the DM's per-week entitlement
# How far ahead a break can be scheduled: a rolling window of this many ISO weeks
# starting with the current week. The 2 h/week cap still applies independently to
# whichever week the chosen date falls in — this only bounds how far out you can plan.
WELLNESS_WINDOW_WEEKS = 4
# A break must be filed at least this many minutes before its start time, so the
# approving chief has a real window to see and act on it before it happens
# (Spot Feedback #73). Also stops same-day requests for a time that's already
# passed.
WELLNESS_MIN_LEAD_MINUTES = 30
WELLNESS_STATUSES = ("pending", "approved", "denied", "cancelled", "completed")
# Statuses that consume the weekly entitlement (denied/cancelled free the hour).
_WELLNESS_COUNTED = ("pending", "approved", "completed")

# The DM's encouraged activities (smoking/vaping/alcohol are explicitly out).
WELLNESS_ACTIVITIES = [
    ("exercise",      "Physical exercise"),
    ("meditation",    "Meditation & relaxation"),
    ("mental_health", "Mental health activity / consultation"),
    ("hobby",         "Hobby & creative recreation"),
    ("other",         "Others"),
]

# The bureau's full Office/Unit name as it must read on the DM's official
# "Annex A. Weekly Wellness Break Log" register.
WELLNESS_OFFICE_UNIT = BUREAU_NAME

# Our activity keys -> the Annex A "Activity Type" column's six official
# categories (Physical Exercise, Relaxation, Wellness Consult, Recreation,
# Arts, Others). Anything unmapped falls back to "Others".
WELLNESS_ANNEX_ACTIVITY = {
    "exercise":      "Physical Exercise",
    "meditation":    "Relaxation",
    "mental_health": "Wellness Consult",
    "hobby":         "Recreation",
    "other":         "Others",
}


# Cumulative point thresholds for levels 1..6; the avatar stage == the level.
WELLNESS_LEVELS = [0, 30, 75, 150, 250, 400]
# The classic plant vocabulary, kept as the wellness default. Single source of
# truth: it IS the avatar catalog's plant-family array (see AVATAR_STAGE_NAMES),
# so the mascot and the plant avatar always read the same stage names.
WELLNESS_STAGE_NAMES = AVATAR_STAGE_NAMES["plant"]

# Points: completed break +10, reflection +5, both hours in one week +5,
# +2 per week of the current streak.
WELLNESS_PTS_BREAK = 10
WELLNESS_PTS_REFLECTION = 5
WELLNESS_PTS_FULL_WEEK = 5
WELLNESS_PTS_STREAK_WEEK = 2

WELLNESS_BADGES = {
    "first_break": ("First break", "Completed your first wellness break"),
    "full_week":   ("Full week",   "Used the full 2 hours in one week"),
    "reflect_5":   ("Reflective",  "Wrote 5 post-break reflections"),
    "streak_4":    ("On a roll",   "Wellness breaks 4 weeks in a row"),
    "streak_12":   ("Habit built", "Wellness breaks 12 weeks in a row"),
    # Awarded by record_avatar_care, not wellness_award_badges: it tracks the
    # companion-care day streak (cosmetic layer), not the break record.
    "avatar_care_7": ("Devoted caretaker", "Cared for your companion 7 days in a row"),
}


def wellness_week_start(d=None):
    """Monday of `d`'s week (PH-local today when d is None), as 'YYYY-MM-DD'.
    The whole module keys entitlement on this string."""
    d = d or tz.today_local()
    return (d - timedelta(days=d.weekday())).isoformat()


def wellness_window_last_date(d=None):
    """Last date a break can be scheduled for: the Friday of the last week in the
    rolling WELLNESS_WINDOW_WEEKS-week window (current week + the next ones). Used
    both to cap the apply-form date picker and to validate the request server-side."""
    d = d or tz.today_local()
    monday = d - timedelta(days=d.weekday())
    # Monday of the last week in the window, then its Friday (weekday 4).
    return monday + timedelta(days=(WELLNESS_WINDOW_WEEKS - 1) * 7 + 4)


def wellness_window_weeks(d=None):
    """The Monday-of-week ISO strings covered by the rolling window, in order."""
    d = d or tz.today_local()
    monday = d - timedelta(days=d.weekday())
    return [(monday + timedelta(days=7 * i)).isoformat()
            for i in range(WELLNESS_WINDOW_WEEKS)]


def wellness_hours_used(conn, user_id, week_start):
    """Hours of the week's entitlement already spoken for (pending + approved +
    completed; denied/cancelled don't count)."""
    qs = ",".join("?" * len(_WELLNESS_COUNTED))
    return conn.execute(
        f"SELECT COALESCE(SUM(hours),0) FROM wellness_claim "
        f"WHERE user_id=? AND week_start=? AND status IN ({qs})",
        (user_id, week_start, *_WELLNESS_COUNTED)).fetchone()[0]


def create_wellness_claim(conn, user_id, break_date, start_time, activity,
                          note=None, hours=1, activity_other=None):
    """File a break request of `hours` hours (1 or 2 — the DM allows the whole
    weekly entitlement in one sitting). Validates the DM's rules and raises
    ValueError with a human-readable reason; returns the new claim id."""
    try:
        hours = int(hours)
    except (TypeError, ValueError):
        raise ValueError("Pick a valid break length.")
    if hours < 1 or hours > WELLNESS_WEEKLY_HOURS:
        raise ValueError(
            f"A break is 1 to {WELLNESS_WEEKLY_HOURS} hours long.")
    try:
        d = date.fromisoformat((break_date or "").strip())
    except ValueError:
        raise ValueError("Pick a valid date for your break.")
    start_time = (start_time or "").strip()
    if not re.fullmatch(r"([01]\d|2[0-3]):[0-5]\d", start_time):
        raise ValueError("Pick a valid start time (HH:MM).")
    if activity not in dict(WELLNESS_ACTIVITIES):
        raise ValueError("Pick one of the allowed wellness activities.")
    activity_other = (activity_other or "").strip() or None
    if activity == "other" and not activity_other:
        raise ValueError("Tell us what the 'Others' activity is.")
    if activity != "other":
        activity_other = None            # only meaningful for the "Others" option
    if d < tz.today_local():
        raise ValueError("Breaks are scheduled ahead — pick today or a future date.")
    if d > wellness_window_last_date():
        raise ValueError(
            f"Breaks can be scheduled up to {WELLNESS_WINDOW_WEEKS} weeks ahead — "
            "pick a date within the next few weeks.")
    if d.weekday() >= 5:
        raise ValueError("Wellness breaks are taken within the work week (Mon–Fri).")
    # Require a minimum lead time before the break's start so the approver has a
    # window to act (Spot Feedback #73). Combining date + time also rejects a
    # same-day request for a start that's already passed — which the date-only
    # check above lets through.
    starts_at = datetime.combine(d, time.fromisoformat(start_time))
    earliest = tz.now_local() + timedelta(minutes=WELLNESS_MIN_LEAD_MINUTES)
    if starts_at < earliest:
        raise ValueError(
            f"File a break at least {WELLNESS_MIN_LEAD_MINUTES} minutes before it "
            "starts, so your approver has time to see it.")
    ws = wellness_week_start(d)
    used = wellness_hours_used(conn, user_id, ws)
    if used + hours > WELLNESS_WEEKLY_HOURS:
        left = WELLNESS_WEEKLY_HOURS - used
        if left <= 0:
            raise ValueError(f"That week's {WELLNESS_WEEKLY_HOURS}-hour wellness "
                             "entitlement is already fully claimed.")
        raise ValueError(
            f"Only {left} hour{'s' if left != 1 else ''} left in that week's "
            f"{WELLNESS_WEEKLY_HOURS}-hour entitlement.")
    dup = conn.execute(
        "SELECT 1 FROM wellness_claim WHERE user_id=? AND break_date=? AND "
        "start_time=? AND status IN ('pending','approved','completed')",
        (user_id, d.isoformat(), start_time)).fetchone()
    if dup:
        raise ValueError("You already have a break at that date and time.")
    cur = conn.execute(
        """INSERT INTO wellness_claim(user_id, week_start, break_date, start_time,
                                      hours, activity, activity_other, note, status,
                                      created_at)
           VALUES (?,?,?,?,?,?,?,?,'pending',?)""",
        (user_id, ws, d.isoformat(), start_time, hours, activity, activity_other,
         (note or "").strip() or None, tz.now_iso()))
    conn.commit()
    return cur.lastrowid


def get_wellness_claim(conn, claim_id):
    row = conn.execute(
        """SELECT c.id, c.user_id, c.week_start, c.break_date, c.start_time, c.hours,
                  c.activity, c.note, c.status, c.decided_by, c.decided_at,
                  c.decide_note, c.created_at, u.username,
                  rp.name, ou.short_name, ou.path,
                  r.id IS NOT NULL, r.mood_before, r.mood_after,
                  c.activity_other, r.usefulness, r.felt_refreshed, r.managed_stress,
                  r.focus_impact, r.suggestions
           FROM wellness_claim c
           JOIN admin_user u ON u.id = c.user_id
           LEFT JOIN resource_person rp ON rp.id = u.rp_id
           LEFT JOIN org_unit ou ON ou.id = rp.org_unit_id
           LEFT JOIN wellness_reflection r ON r.claim_id = c.id
           WHERE c.id=?""", (claim_id,)).fetchone()
    if not row:
        return None
    base_label = dict(WELLNESS_ACTIVITIES).get(row[6], row[6])
    activity_other = row[20]
    # For "Others", show what was specified, e.g. "Others — gardening".
    activity_label = (f"{base_label} — {activity_other}"
                      if row[6] == "other" and activity_other else base_label)
    return {"id": row[0], "user_id": row[1], "week_start": row[2],
            "break_date": row[3], "start_time": row[4], "hours": row[5],
            "activity": row[6], "activity_label": activity_label,
            "activity_other": activity_other,
            "note": row[7], "status": row[8], "decided_by": row[9],
            "decided_at": row[10], "decide_note": row[11], "created_at": row[12],
            "username": row[13], "person_name": row[14] or row[13],
            "section": row[15] or (row[16].rsplit("/", 1)[-1] if row[16] else None),
            "has_reflection": bool(row[17]),
            "mood_before": row[18], "mood_after": row[19],
            "usefulness": row[21], "felt_refreshed": row[22],
            "managed_stress": row[23], "focus_impact": row[24],
            "suggestions": row[25]}


def list_my_wellness_claims(conn, user_id, limit=25):
    """The employee's own claims, newest break first."""
    ids = [r[0] for r in conn.execute(
        "SELECT id FROM wellness_claim WHERE user_id=? "
        "ORDER BY break_date DESC, start_time DESC LIMIT ?", (user_id, limit))]
    return [get_wellness_claim(conn, i) for i in ids]


def list_wellness_approvals(conn, user):
    """Pending claims this user may decide, oldest break first. A chief sees
    exactly the claims the escalation chain routes to them (their section's
    staff, or — for a division chief — their division's section chiefs, etc.).
    Own claims are excluded (they escalate one level further).

    Admins are the fallback ABOVE the chain, not a bypass around it, so an admin
    who also holds a seat on the org chart gets their own chain's claims plus the
    orphans — the pending claims no chief can reach, because the claimant is
    unlinked, sits under an unfilled seat, or is the Director. Without that split
    a section head who administers the app opened a queue holding all five
    sections' routine claims; with it, nothing is stranded and nothing routine
    leaks sideways. An admin with no directory seat still sees every orphan,
    which is every claim they used to see minus the ones with a real chief."""
    ids = [r[0] for r in conn.execute(
        "SELECT id FROM wellness_claim WHERE status='pending' AND user_id != ? "
        "ORDER BY break_date, start_time", (user["id"],)).fetchall()]
    claims = [get_wellness_claim(conn, i) for i in ids]
    return _mine_or_orphaned(conn, user, claims, lambda c: c["user_id"])


def _mine_or_orphaned(conn, user, rows, subject_of):
    """The approval-queue filter shared by the wellness break and the work
    arrangement: rows the chain routes to `user`, plus — for an admin — the rows
    it routes to nobody. See list_wellness_approvals for why."""
    is_admin = user.get("role") == "admin"
    if not is_admin and not user_is_approving_chief(conn, user):
        return []
    out = []
    for r in rows:
        approvers = get_approvers_for(conn, subject_of(r))
        if user["id"] in approvers or (is_admin and not approvers):
            out.append(r)
    return out


def unseen_wellness_decisions(conn, user_id):
    """Statuses ('approved'/'denied') of MY OWN wellness break requests decided
    since I last opened /wellness, newest first — empty if none. The requester
    side of the approvals queue: what happened to what I filed, feeding the nav
    bell the same way count_unread_feedback feeds it for spot feedback."""
    rows = conn.execute(
        "SELECT w.status FROM wellness_claim w JOIN admin_user a ON a.id = w.user_id "
        "WHERE w.user_id=? AND w.status IN ('approved','denied') "
        "AND w.decided_at IS NOT NULL "
        "AND (a.wellness_seen_at IS NULL OR w.decided_at > a.wellness_seen_at) "
        "ORDER BY w.decided_at DESC", (user_id,)).fetchall()
    return [r[0] for r in rows]


def mark_wellness_seen(conn, user_id):
    """Stamp now as this account's last look at /wellness — clears the nav
    bell's 'your break was decided' notice."""
    conn.execute("UPDATE admin_user SET wellness_seen_at=? WHERE id=?",
                 (tz.now_iso(), user_id))
    conn.commit()


def decide_wellness_claim(conn, claim_id, user, action, note=None):
    """Approve or deny a pending claim. Raises ValueError (bad state/input) or
    PermissionError (not this user's to decide). Returns the updated claim."""
    claim = get_wellness_claim(conn, claim_id)
    if not claim:
        raise ValueError("That break request no longer exists.")
    if claim["status"] != "pending":
        raise ValueError("That break request has already been decided.")
    if action not in ("approve", "deny"):
        raise ValueError("Unknown decision.")
    if not is_approver_for(conn, user, claim["user_id"]):
        raise PermissionError("Only the claimant's section chief (or an admin) "
                              "can decide this request.")
    conn.execute(
        "UPDATE wellness_claim SET status=?, decided_by=?, decided_at=?, decide_note=? "
        "WHERE id=?",
        ("approved" if action == "approve" else "denied", user["id"], tz.now_iso(),
         (note or "").strip() or None, claim_id))
    conn.commit()
    return get_wellness_claim(conn, claim_id)


def cancel_wellness_claim(conn, claim_id, user_id):
    """The claimant withdraws their own request (pending or approved-but-not-
    taken); the hour returns to the week's entitlement."""
    claim = get_wellness_claim(conn, claim_id)
    if not claim or claim["user_id"] != user_id:
        raise ValueError("That break request isn't yours to cancel.")
    if claim["status"] not in ("pending", "approved"):
        raise ValueError("Only a pending or approved break can be cancelled.")
    conn.execute("UPDATE wellness_claim SET status='cancelled' WHERE id=?", (claim_id,))
    conn.commit()
    return claim


WELLNESS_FOCUS_IMPACTS = ("improved", "no_change", "worsened")


def _wellness_yesno(v):
    """Parse a Yes/No form value to 1/0, or None when not answered."""
    if v is None:
        return None
    s = str(v).strip().lower()
    if s in ("1", "yes", "y", "true", "on"):
        return 1
    if s in ("0", "no", "n", "false", "off"):
        return 0
    return None


def complete_wellness_claim(conn, claim_id, user_id, mood_before, mood_after,
                            activity_done, takeaway, usefulness=None,
                            felt_refreshed=None, managed_stress=None,
                            focus_impact=None, suggestions=None):
    """Close out an approved break with its post-break reflection (they are one
    move: answering the questions is what marks the break taken). The DOH
    Post-Activity Report fields (usefulness, refreshed/stress, focus impact,
    suggestions) are optional keyword args so older callers keep working. Returns
    (claim, newly_awarded_badges)."""
    claim = get_wellness_claim(conn, claim_id)
    if not claim or claim["user_id"] != user_id:
        raise ValueError("That break request isn't yours.")
    if claim["status"] != "approved":
        raise ValueError("Only an approved break can be completed.")
    if claim["break_date"] > tz.today_local().isoformat():
        raise ValueError("You can check in once the break's day arrives.")
    try:
        mb, ma = int(mood_before), int(mood_after)
    except (TypeError, ValueError):
        raise ValueError("Rate your mood before and after (1–5).")
    if not (1 <= mb <= 5 and 1 <= ma <= 5):
        raise ValueError("Mood ratings go from 1 to 5.")
    activity_done = (activity_done or "").strip()
    if not activity_done:
        raise ValueError("Tell us what you did on your break.")
    use = None
    if usefulness not in (None, ""):
        try:
            use = int(usefulness)
        except (TypeError, ValueError):
            raise ValueError("Rate how useful the break was (1–5).")
        if not (1 <= use <= 5):
            raise ValueError("Usefulness goes from 1 to 5.")
    refreshed = _wellness_yesno(felt_refreshed)
    stress = _wellness_yesno(managed_stress)
    focus = (focus_impact or "").strip().lower() or None
    if focus is not None and focus not in WELLNESS_FOCUS_IMPACTS:
        raise ValueError("Pick how the break affected your focus.")
    conn.execute("UPDATE wellness_claim SET status='completed' WHERE id=?", (claim_id,))
    conn.execute(
        """INSERT INTO wellness_reflection(claim_id, mood_before, mood_after,
                                           activity_done, takeaway, usefulness,
                                           felt_refreshed, managed_stress,
                                           focus_impact, suggestions, submitted_at)
           VALUES (?,?,?,?,?,?,?,?,?,?,?)""",
        (claim_id, mb, ma, activity_done, (takeaway or "").strip() or None,
         use, refreshed, stress, focus, (suggestions or "").strip() or None,
         tz.now_iso()))
    new_badges = wellness_award_badges(conn, user_id)
    conn.commit()
    return get_wellness_claim(conn, claim_id), new_badges


# ---- gamification (derived) ----------------------------------------------

def _wellness_counts(conn, user_id):
    """The raw counts the points formula and badges share."""
    completed = conn.execute(
        "SELECT COUNT(*) FROM wellness_claim WHERE user_id=? AND status='completed'",
        (user_id,)).fetchone()[0]
    reflections = conn.execute(
        "SELECT COUNT(*) FROM wellness_reflection r JOIN wellness_claim c "
        "ON c.id = r.claim_id WHERE c.user_id=?", (user_id,)).fetchone()[0]
    full_weeks = conn.execute(
        "SELECT COUNT(*) FROM (SELECT week_start FROM wellness_claim "
        "WHERE user_id=? AND status='completed' GROUP BY week_start "
        "HAVING SUM(hours) >= ?)", (user_id, WELLNESS_WEEKLY_HOURS)).fetchone()[0]
    return completed, reflections, full_weeks


def wellness_streak(conn, user_id):
    """Consecutive weeks with at least one completed break, counted back from
    the current week — which doesn't break the streak while still in progress
    (no completed break YET this week starts counting from last week)."""
    weeks = {r[0] for r in conn.execute(
        "SELECT DISTINCT week_start FROM wellness_claim "
        "WHERE user_id=? AND status='completed'", (user_id,))}
    if not weeks:
        return 0
    cur = date.fromisoformat(wellness_week_start())
    if cur.isoformat() not in weeks:
        cur -= timedelta(days=7)
    streak = 0
    while cur.isoformat() in weeks:
        streak += 1
        cur -= timedelta(days=7)
    return streak


def wellness_stats(conn, user_id):
    """Everything the hub page shows: points, level, avatar stage, streak,
    badges, and progress toward the next stage."""
    completed, reflections, full_weeks = _wellness_counts(conn, user_id)
    streak = wellness_streak(conn, user_id)
    points = (completed * WELLNESS_PTS_BREAK + reflections * WELLNESS_PTS_REFLECTION
              + full_weeks * WELLNESS_PTS_FULL_WEEK + streak * WELLNESS_PTS_STREAK_WEEK)
    level = sum(1 for t in WELLNESS_LEVELS if points >= t)          # 1..6
    stage = min(level, len(WELLNESS_STAGE_NAMES))
    next_at = WELLNESS_LEVELS[level] if level < len(WELLNESS_LEVELS) else None
    prev_at = WELLNESS_LEVELS[level - 1]
    progress = 100 if next_at is None else round(
        (points - prev_at) * 100 / (next_at - prev_at))
    badges = [{"key": r[0], "awarded_at": r[1],
               "label": WELLNESS_BADGES.get(r[0], (r[0], ""))[0],
               "blurb": WELLNESS_BADGES.get(r[0], (r[0], ""))[1]}
              for r in conn.execute(
                  "SELECT badge, awarded_at FROM wellness_badge WHERE user_id=? "
                  "ORDER BY awarded_at", (user_id,))]
    return {"points": points, "level": level, "stage": stage,
            "stage_name": WELLNESS_STAGE_NAMES[stage - 1],
            "streak": streak, "completed": completed, "reflections": reflections,
            "full_weeks": full_weeks, "badges": badges,
            "next_at": next_at, "progress": progress}


def avatar_growth_ladder(kind, stats):
    """The six growth stages of ONE species, with where this person stands.

    Pure presentation over what wellness_stats already derives — no new state,
    nothing persisted, so it cannot drift from the points that actually drive the
    avatar. Returns one entry per stage:

        {stage, name, points_at, reached, current}

    `points_at` is the cumulative point threshold from WELLNESS_LEVELS, which is
    what makes the ladder honest: a locked stage shows the number that unlocks
    it rather than a vague "keep going".

    Exists because the companion's growth was invisible — you could see the
    creature you had, but not the one you were working toward, and nothing on
    screen said how it grew."""
    stage_now = (stats or {}).get("stage", 1)
    return [{"stage": i + 1,
             "name": avatar_stage_name(kind, i + 1),
             "points_at": pts,
             "reached": (i + 1) <= stage_now,
             "current": (i + 1) == stage_now}
            for i, pts in enumerate(WELLNESS_LEVELS)]


def avatar_growth_actions(kind):
    """How the companion grows, read straight off the scoring constants so the
    explanation can never disagree with the arithmetic. `care` is the cosmetic
    day-streak, which earns a badge rather than points — said plainly rather than
    left to look like a fifth way to level up."""
    return {
        "points": [
            {"label": "Take a wellness break", "points": WELLNESS_PTS_BREAK},
            {"label": "Write a reflection afterwards", "points": WELLNESS_PTS_REFLECTION},
            {"label": f"Use your full {WELLNESS_WEEKLY_HOURS} hours in a week",
             "points": WELLNESS_PTS_FULL_WEEK},
            {"label": "Each week of an unbroken streak", "points": WELLNESS_PTS_STREAK_WEEK},
        ],
        "care": {"verb": avatar_care_verb(kind),
                 "badge": WELLNESS_BADGES["avatar_care_7"][0],
                 "blurb": WELLNESS_BADGES["avatar_care_7"][1]},
    }


def wellness_award_badges(conn, user_id):
    """Grant any newly earned badges (idempotent — UNIQUE(user_id,badge) makes
    re-checks free). Returns the labels of badges awarded on THIS call. Does not
    commit — callers commit with their surrounding write."""
    completed, reflections, full_weeks = _wellness_counts(conn, user_id)
    streak = wellness_streak(conn, user_id)
    earned = []
    if completed >= 1:
        earned.append("first_break")
    if full_weeks >= 1:
        earned.append("full_week")
    if reflections >= 5:
        earned.append("reflect_5")
    if streak >= 4:
        earned.append("streak_4")
    if streak >= 12:
        earned.append("streak_12")
    fresh = []
    for b in earned:
        label = _award_badge(conn, user_id, b)
        if label:
            fresh.append(label)
    return fresh


def _award_badge(conn, user_id, key, when=None):
    """Persist one badge award. Idempotent (INSERT OR IGNORE against the
    UNIQUE(user_id, badge) constraint); returns the badge LABEL only when this
    call actually inserted it — i.e. exactly once per user per badge — else
    None. Does NOT commit; the caller's surrounding write commits."""
    cur = conn.execute(
        "INSERT OR IGNORE INTO wellness_badge(user_id, badge, awarded_at) "
        "VALUES (?,?,?)", (user_id, key, when or tz.now_iso()))
    return WELLNESS_BADGES[key][0] if cur.rowcount else None


# ---- monitoring dashboard + the submission register -----------------------

def wellness_week_rollup(conn, week_start, user=None):
    """One week's hours per person, in the viewer's scope — one query, no writes.

    This is the cheap half of wellness_dashboard_data: the per-person rows and
    the per-section rollup, WITHOUT the all-weeks pending queue (which scans
    every pending claim in the bureau and hydrates each one individually before
    filtering by scope) or the bureau-wide reflection rate. Both are right for
    the monitoring page and far too expensive for a landing page that every user
    loads at every sign-in.

    wellness_dashboard_data now calls THIS and adds the queue on top, so the
    monitoring register and the landing page can never quietly disagree about
    how many hours a section used.

    `rp_id` / `has_photo` / `avatar_kind` / `position` / `designation` ride along
    as joined columns — no extra query — so a caller drawing faces can resolve
    each person's picture (or their companion, or their initials) and apply
    is_bureau_director() without a second pass.

    Scoping is _org_scope_for_user's: everyone sees their own directory unit's
    subtree, whatever their app role; an unscoped call (user=None) sees the
    bureau. Wellness is health information, so only a full 'all' grant widens it
    — a bureau-wide WORK-ARRANGEMENT grant deliberately does not. Callers that
    show this to EVERY user must resolve scope with team_scope_for_user first —
    see its docstring for why None is not a safe default there."""
    scope_path = _org_scope_for_user(conn, user, area="wellness")
    people = conn.execute("""
        SELECT u.id, u.username, rp.name, ou.short_name, ou.path,
               COALESCE(SUM(CASE WHEN c.status='pending'   THEN c.hours END), 0),
               COALESCE(SUM(CASE WHEN c.status='approved'  THEN c.hours END), 0),
               COALESCE(SUM(CASE WHEN c.status='completed' THEN c.hours END), 0),
               COUNT(r.id),
               u.rp_id, (rp.photo IS NOT NULL), u.avatar_kind,
               rp.position, rp.designation
        FROM admin_user u
        LEFT JOIN resource_person rp ON rp.id = u.rp_id
        LEFT JOIN org_unit ou ON ou.id = rp.org_unit_id
        LEFT JOIN wellness_claim c ON c.user_id = u.id AND c.week_start = ?
        LEFT JOIN wellness_reflection r ON r.claim_id = c.id
        WHERE u.active = 1 AND rp.archived_at IS NULL
        GROUP BY u.id ORDER BY ou.path, rp.name, u.username
    """, (week_start,)).fetchall()
    people = [p for p in people if _path_in_scope(p[4], scope_path)]
    rows = [{"user_id": p[0], "username": p[1], "name": p[2] or p[1],
             "section": p[3] or (p[4].rsplit("/", 1)[-1] if p[4] else "—"),
             "org_path": p[4] or "",
             "pending": p[5], "approved": p[6], "completed": p[7],
             "reflections": p[8],
             "used": p[6] + p[7], "left": max(0, WELLNESS_WEEKLY_HOURS - p[6] - p[7]),
             "rp_id": p[9], "has_photo": bool(p[10]), "avatar_kind": p[11],
             "position": p[12] or "", "designation": p[13] or ""}
            for p in people]
    sections = {}
    for r in rows:
        s = sections.setdefault(r["section"], {"section": r["section"], "people": 0,
                                               "used": 0, "completed": 0})
        s["people"] += 1
        s["used"] += r["used"]
        s["completed"] += r["completed"]
    for s in sections.values():
        s["entitled"] = s["people"] * WELLNESS_WEEKLY_HOURS
        s["pct"] = round(s["used"] * 100 / s["entitled"]) if s["entitled"] else 0
    total_used = sum(r["used"] for r in rows)
    entitled = len(rows) * WELLNESS_WEEKLY_HOURS
    return {"rows": rows,
            "sections": sorted(sections.values(), key=lambda s: s["section"]),
            "scope_path": scope_path,
            "week_used": total_used, "week_entitled": entitled,
            "week_pct": round(total_used * 100 / entitled) if entitled else 0}


# ---- the habit behind the week --------------------------------------------

# Eight weeks: long enough that a weekday pattern is a pattern rather than last
# week repeated, short enough to still describe how the team works NOW.
WELLNESS_PATTERN_WEEKS = 8

# Start-time buckets. Coarse on purpose — the useful question is "morning or
# afternoon, before or after lunch", not which of nine start times won.
WELLNESS_SLOTS = [("early", "Before 10", 0, 10), ("mid", "10am-12nn", 10, 12),
                  ("lunch", "12nn-2pm", 12, 14), ("late", "After 2pm", 14, 24)]

_WELL_DAY_NAMES = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday",
                   "Saturday", "Sunday"]


def _wellness_slot_index(start_time):
    """Which WELLNESS_SLOTS bucket a 'HH:MM' start time falls in."""
    try:
        hour = int(str(start_time).split(":")[0])
    except (ValueError, AttributeError, IndexError):
        return 0
    for i, (_key, _label, lo, hi) in enumerate(WELLNESS_SLOTS):
        if lo <= hour < hi:
            return i
    return len(WELLNESS_SLOTS) - 1


def wellness_pattern(conn, week_start, user=None, weeks=WELLNESS_PATTERN_WEEKS,
                     *, only_user_id=None):
    """WHEN breaks are actually taken, over the last `weeks` weeks.

    The week rollup above answers "who has filed this week"; this answers the
    question a chief asks next — which day and hour the team actually protects,
    what they do with it, and whether it helps. Counts only, no geometry and no
    HTML: the caller turns these into bars (see dashboard_insights).

    Only APPROVED and COMPLETED claims count. A pending request is a plan, and a
    denied or cancelled one never happened; putting either in a pattern would
    describe intentions as behaviour.

    Scoping is wellness_week_rollup's, for the same reason — a landing page must
    resolve scope with team_scope_for_user first — and so is its exclusion of
    ARCHIVED people: the wall of faces on the card and the eight weeks behind it
    have to describe the same team, or the card's own two halves disagree about
    who is on it. `only_user_id` is the one exception on both counts: it is ONE
    person's own history, so no scope filter applies and their own record is
    theirs to see (you may always see yourself, wherever the directory puts you).

    Wellness, so a bureau-wide work-arrangement grant does not widen it — see
    wellness_week_rollup."""
    first_week = (date.fromisoformat(week_start)
                  - timedelta(weeks=max(1, weeks) - 1)).isoformat()
    sql = """
        SELECT c.break_date, c.start_time, c.hours, c.activity, c.week_start,
               c.user_id, ou.path, r.mood_before, r.mood_after, r.felt_refreshed,
               r.id
        FROM wellness_claim c
        JOIN admin_user u ON u.id = c.user_id
        LEFT JOIN resource_person rp ON rp.id = u.rp_id
        LEFT JOIN org_unit ou ON ou.id = rp.org_unit_id
        LEFT JOIN wellness_reflection r ON r.claim_id = c.id
        WHERE c.week_start >= ? AND c.week_start <= ?
          AND c.status IN ('approved', 'completed')
    """
    args = [first_week, week_start]
    if only_user_id is not None:
        sql += " AND c.user_id = ?"
        args.append(only_user_id)
    else:
        # Same team as the faces above it: people who have left the bureau are
        # out of the roster, so they are out of its history too.
        sql += " AND rp.archived_at IS NULL"
    rows = conn.execute(sql, args).fetchall()
    if only_user_id is None:
        scope_path = _org_scope_for_user(conn, user, area="wellness")
        rows = [r for r in rows if _path_in_scope(r[6], scope_path)]

    slots = [{"key": k, "label": lab} for k, lab, _lo, _hi in WELLNESS_SLOTS]
    days = [{"idx": i, "name": n, "short": n[:3], "n": 0}
            for i, n in enumerate(_WELL_DAY_NAMES)]
    grid = [[0] * len(slots) for _ in _WELL_DAY_NAMES]
    slot_counts = [0] * len(slots)
    by_activity, by_week, people = {}, {}, set()
    hours = 0
    moods, refreshed, reflected, answered = [], 0, 0, 0

    week_keys = [(date.fromisoformat(week_start) - timedelta(weeks=i)).isoformat()
                 for i in range(max(1, weeks) - 1, -1, -1)]
    for k in week_keys:
        by_week[k] = {"week_start": k, "people": set(), "hours": 0}

    for (break_date, start_time, hrs, activity, wk, uid, _path,
         mood_before, mood_after, felt, reflection_id) in rows:
        try:
            day = date.fromisoformat(str(break_date)[:10]).weekday()
        except ValueError:
            continue
        slot = _wellness_slot_index(start_time)
        days[day]["n"] += 1
        grid[day][slot] += 1
        slot_counts[slot] += 1
        hours += hrs or 0
        people.add(uid)
        label = dict(WELLNESS_ACTIVITIES).get(activity, "Others")
        by_activity[label] = by_activity.get(label, 0) + 1
        if wk in by_week:
            by_week[wk]["people"].add(uid)
            by_week[wk]["hours"] += hrs or 0
        if mood_before is not None and mood_after is not None:
            moods.append(mood_after - mood_before)
        if reflection_id is not None:
            reflected += 1
            answered += 1 if felt is not None else 0
            refreshed += 1 if felt else 0

    for i, s in enumerate(slots):
        s["n"] = slot_counts[i]
    peak_day = max(days, key=lambda d: d["n"]) if any(d["n"] for d in days) else None
    peak_slot = max(slots, key=lambda s: s["n"]) if any(s["n"] for s in slots) else None
    return {
        "weeks": max(1, weeks), "first_week": first_week, "week_start": week_start,
        "claims": sum(d["n"] for d in days), "hours": hours,
        "people": len(people),
        "by_day": days, "by_slot": slots, "grid": grid,
        "by_activity": sorted(({"label": k, "n": v} for k, v in by_activity.items()),
                              key=lambda a: (-a["n"], a["label"])),
        "by_week": [{"week_start": k, "people": len(v["people"]), "hours": v["hours"]}
                    for k, v in by_week.items()],
        "peak_day": peak_day, "peak_slot": peak_slot,
        "mood": {
            # `refreshed_pct` is out of the people who ANSWERED that question,
            # not out of every reflection — the field is optional, and counting
            # a blank as a "no" would read as dissatisfaction that nobody voiced.
            "reflections": reflected,
            "delta": round(sum(moods) / len(moods), 1) if moods else None,
            "moods": len(moods),
            "refreshed_pct": (round(refreshed * 100 / answered)
                              if answered else None),
            "answered": answered,
        },
    }


def wellness_dashboard_data(conn, week_start, user=None):
    """One week's utilization for the monitoring page: a per-person table with
    section, hours by status and reflection state; a per-section rollup against
    the 2 h/person entitlement; the all-weeks pending queue with its age; and
    the overall reflection completion rate.

    When `user` is a directory-linked chief the whole view is scoped to their own
    unit's subtree (see _org_scope_for_user) so the "By person" table — and
    the section rollup, week tiles and pending queue derived from it — shows only
    the section(s) they are concerned with, not every employee. Admins and an
    unscoped call see the whole bureau."""
    roll = wellness_week_rollup(conn, week_start, user)
    rows, sections = roll["rows"], {s["section"]: s for s in roll["sections"]}
    scope_path = roll["scope_path"]
    in_scope = {r["user_id"] for r in rows}
    today = tz.today_local().isoformat()
    queue = [dict(get_wellness_claim(conn, r[0]),
                  age_days=(date.fromisoformat(today)
                            - date.fromisoformat(r[1])).days)
             for r in conn.execute(
                 "SELECT id, date(created_at) FROM wellness_claim "
                 "WHERE status='pending' ORDER BY created_at")]
    if scope_path:
        queue = [c for c in queue if c["user_id"] in in_scope]
    done, reflected = conn.execute(
        "SELECT COUNT(*), COUNT(r.id) FROM wellness_claim c "
        "LEFT JOIN wellness_reflection r ON r.claim_id = c.id "
        "WHERE c.status='completed'").fetchone()
    return {"rows": rows,
            "sections": sorted(sections.values(), key=lambda s: s["section"]),
            "queue": queue,
            "reflect_rate": round(reflected * 100 / done) if done else None,
            "week_used": roll["week_used"], "week_entitled": roll["week_entitled"],
            "week_pct": roll["week_pct"]}


def wellness_export_rows(conn, date_from=None, date_to=None):
    """The monitoring register (the Administrative Service's submission output):
    one row per claim, chronological. Optional inclusive 'YYYY-MM-DD' bounds."""
    where, args = "", []
    if date_from:
        where += " AND c.break_date >= ?"
        args.append(date_from)
    if date_to:
        where += " AND c.break_date <= ?"
        args.append(date_to)
    rows = conn.execute(f"""
        SELECT c.week_start, COALESCE(ou.short_name, ou.path, ''),
               COALESCE(rp.name, u.username), c.break_date, c.start_time, c.hours,
               c.activity, c.status, COALESCE(rpd.name, ud.username, ''),
               r.id IS NOT NULL, r.mood_before, r.mood_after,
               c.activity_other, r.usefulness, r.takeaway
        FROM wellness_claim c
        JOIN admin_user u ON u.id = c.user_id
        LEFT JOIN resource_person rp ON rp.id = u.rp_id
        LEFT JOIN org_unit ou ON ou.id = rp.org_unit_id
        LEFT JOIN admin_user ud ON ud.id = c.decided_by
        LEFT JOIN resource_person rpd ON rpd.id = ud.rp_id
        LEFT JOIN wellness_reflection r ON r.claim_id = c.id
        WHERE 1=1 {where}
        ORDER BY c.break_date, c.start_time, c.id
    """, args).fetchall()
    acts = dict(WELLNESS_ACTIVITIES)
    out = []
    for w in rows:
        label = acts.get(w[6], w[6])
        if w[6] == "other" and w[12]:
            label = f"{label} — {w[12]}"
        # Annex A category (the DM's official 6-way activity type). "Others" carries
        # the free-text specification the same way the label does.
        annex = WELLNESS_ANNEX_ACTIVITY.get(w[6], "Others")
        if w[6] == "other" and w[12]:
            annex = f"{annex} — {w[12]}"
        out.append({"week": w[0], "section": w[1] or "—", "employee": w[2],
                    "date": w[3], "start_time": w[4], "hours": w[5],
                    "activity": label, "activity_key": w[6],
                    "activity_annex": annex, "status": w[7],
                    "approved_by": w[8],
                    "reflection_done": "yes" if w[9] else "no",
                    "mood_before": w[10], "mood_after": w[11],
                    "usefulness": w[13], "remarks": w[14]})
    return out


# ---- personal monthly register (the downloadable PDF) -------------------
# A person's own record of the breaks they availed, one calendar month at a
# time, laid out like the DOH monitoring form (see wellness_register.py). Only
# breaks that were actually granted count — approved or completed; pending,
# denied and cancelled are not breaks taken.
_WELLNESS_AVAILED = ("approved", "completed")


def wellness_availed_months(conn, user_id):
    """Months in which this person has an availed (approved/completed) break,
    newest first, with a count — drives the hub's register download picker.
    Each item: {'ym','year','month','label','count'}."""
    qs = ",".join("?" * len(_WELLNESS_AVAILED))
    rows = conn.execute(
        f"SELECT substr(break_date,1,7) AS ym, COUNT(*) FROM wellness_claim "
        f"WHERE user_id=? AND status IN ({qs}) "
        f"GROUP BY ym ORDER BY ym DESC", (user_id, *_WELLNESS_AVAILED)).fetchall()
    out = []
    for ym, n in rows:
        try:
            y, m = int(ym[:4]), int(ym[5:7])
        except (TypeError, ValueError):
            continue
        out.append({"ym": ym, "year": y, "month": m,
                    "label": f"{_MONTH_NAMES[m - 1]} {y}", "count": n})
    return out


_MONTH_NAMES = ["January", "February", "March", "April", "May", "June", "July",
                "August", "September", "October", "November", "December"]


def wellness_person_month(conn, user_id, year, month):
    """Everything the monthly register PDF needs for one person and month: their
    name and office, and the availed (approved/completed) breaks in that month,
    each carrying the deciding approver's name. Days are chronological."""
    ym = f"{int(year):04d}-{int(month):02d}"
    prof = get_user_profile(conn, user_id)
    name = (prof or {}).get("person_name") or (prof or {}).get("username") or ""
    office = ""
    if prof and prof.get("org_unit_id"):
        row = conn.execute(
            "SELECT short_name, path, name FROM org_unit WHERE id=?",
            (prof["org_unit_id"],)).fetchone()
        if row:
            office = (row[0] or (row[1].rsplit("/", 1)[-1] if row[1] else "")
                      or row[2] or "")
    qs = ",".join("?" * len(_WELLNESS_AVAILED))
    rows = conn.execute(
        f"""SELECT c.break_date, c.start_time, c.hours, c.activity, c.activity_other,
                   c.status, COALESCE(rpd.name, ud.username, ''), c.decided_by
            FROM wellness_claim c
            LEFT JOIN admin_user ud ON ud.id = c.decided_by
            LEFT JOIN resource_person rpd ON rpd.id = ud.rp_id
            WHERE c.user_id=? AND substr(c.break_date,1,7)=?
              AND c.status IN ({qs})
            ORDER BY c.break_date, c.start_time, c.id""",
        (user_id, ym, *_WELLNESS_AVAILED)).fetchall()
    acts = dict(WELLNESS_ACTIVITIES)
    # One signature read per approver, not one per break: a month is usually a
    # handful of breaks all signed by the same chief, and the image is a blob.
    sigs = {}
    for uid in {r[7] for r in rows if r[7]}:
        sigs[uid] = user_signature(conn, uid)
    entries = []
    for r in rows:
        label = acts.get(r[3], r[3])
        if r[3] == "other" and r[4]:
            label = f"{label} — {r[4]}"
        sig = sigs.get(r[7])
        entries.append({"date": r[0], "start_time": r[1], "hours": r[2],
                        "activity_label": label, "status": r[5],
                        "approver": r[6] or "",
                        "approver_signature": sig[0] if sig else None,
                        "approver_signature_mime": sig[1] if sig else None})
    return {"name": name, "office": office, "year": int(year), "month": int(month),
            "entries": entries}


# =====================================================================
# Work arrangement module — ANNEX C, the internal work arrangement schedule.
#
# Every staff member files ONE arrangement per half-month period (the 1st–15th
# and the 16th–end of month, the two sheets the bureau circulates): REG for a
# regular 5-day on-site week, CWW for a compressed workweek with one weekday
# off, or WFH for one day worked from home. The nominated weekday recurs every
# week of the period, exactly as the paper form reads.
#
# Filing closes on the Friday BEFORE a period begins, so the schedule is settled
# before the period it governs starts. Once approved an arrangement is the
# schedule in force and is never edited in place: the employee — and only the
# employee — requests a change, which files a successor row that supersedes the
# original once the same approver signs off.
#
# Approval routes through the shared org chain (see "Org chain of command"
# above): staff to their section chief, a section chief to their division chief.
#
# Coverage is the one rule here that WARNS rather than blocks. A section with
# nobody on-site on a Friday is a real operational problem, but it is the
# chief's call to make, not the database's — so section coverage is computed by
# a separate read-only function and surfaced as advice at both ends (the
# employee sees it while picking a day, the chief sees it on the queue), and
# never raises.
# =====================================================================

# (code, short label, the long form used on the picker cards and the legend)
WORK_ARRANGEMENT_TYPES = [
    ("REG", "Regular",            "Regular 5-day on-site schedule"),
    ("CWW", "Compressed workweek", "Compressed workweek — one weekday off"),
    ("WFH", "Work from home",     "Work from home, one day a week"),
]
WORK_ARRANGEMENT_LABELS = {c: short for c, short, _long in WORK_ARRANGEMENT_TYPES}
# Only these two nominate a weekday; REG applies to the whole week.
_WA_DAY_TYPES = ("CWW", "WFH")

WORK_ARRANGEMENT_WEEKDAYS = [(0, "Monday"), (1, "Tuesday"), (2, "Wednesday"),
                             (3, "Thursday"), (4, "Friday")]
_WA_DAY_NAMES = [name for _i, name in WORK_ARRANGEMENT_WEEKDAYS]

WORK_ARRANGEMENT_STATUSES = ("pending", "approved", "denied", "cancelled",
                             "superseded")
# The label for someone with no alternative work arrangement, printed verbatim in
# the Work Arrangement column of ANNEX C. One constant so the screen, the workbook
# and the PDF cannot word it three ways.
WORK_ARRANGEMENT_NOAWA = "No AWA"
# Rows that occupy a person's period. A denied or withdrawn filing frees it
# again; a superseded one has already been replaced.
_WA_LIVE = ("pending", "approved")

# Filing and changes close on the last Friday BEFORE a period begins.
WORK_ARRANGEMENT_DEADLINE_WEEKDAY = 4          # 0=Mon .. 4=Fri
# How many periods are accepting filings at once: the next one and the one after,
# so people can plan a month out. The CURRENT period is never among them — its
# deadline was the Friday before it started.
WORK_ARRANGEMENT_OPEN_PERIODS = 2

# The legend exactly as it prints at the foot of ANNEX C. Do not reflow.
WORK_ARRANGEMENT_LEGEND = ("*CWW- compressed workweek, -WFH- Work from Home(1Day) , "
                           "REG-Regular 5-day on-site schedule")


# ---- semi-monthly periods and the filing deadline -------------------------

def work_arrangement_period(d=None):
    """The half-month period a date falls in, keyed by its first day:
    'YYYY-MM-01' for the 1st–15th, 'YYYY-MM-16' for the 16th–end of month.
    An ISO date rather than a synthetic '2026-08-A' key so it sorts, parses and
    compares like every other date in the schema — the same trick
    wellness_claim.week_start uses to key entitlement on a Monday."""
    d = d or tz.today_local()
    return date(d.year, d.month, 1 if d.day <= 15 else 16).isoformat()


def work_arrangement_period_bounds(period_start):
    """(first day, last day) of a period. The second half runs to whatever the
    month's real last day is — 28, 29, 30 or 31."""
    s = date.fromisoformat(period_start)
    if s.day == 1:
        return s, s.replace(day=15)
    # First of next month, minus a day = this month's last day.
    nxt = (s.replace(day=28) + timedelta(days=7)).replace(day=1)
    return s, nxt - timedelta(days=1)


def work_arrangement_period_label(period_start):
    """'August 1-15, 2026' / 'August 16-31, 2026' — the wording the source
    ANNEX C sheets use as their titles, so ours match byte for byte."""
    s, e = work_arrangement_period_bounds(period_start)
    return f"{_MONTH_NAMES[s.month - 1]} {s.day}-{e.day}, {s.year}"


def work_arrangement_next_period(period_start):
    s = date.fromisoformat(period_start)
    if s.day == 1:
        return s.replace(day=16).isoformat()
    return (s.replace(day=28) + timedelta(days=7)).replace(day=1).isoformat()


def work_arrangement_prev_period(period_start):
    s = date.fromisoformat(period_start)
    if s.day == 16:
        return s.replace(day=1).isoformat()
    return (s - timedelta(days=1)).replace(day=16).isoformat()


def work_arrangement_deadline(period_start):
    """The last Friday STRICTLY before the period begins — when filing and
    changes close for it. 'Strictly': a period that itself starts on a Friday
    closes the Friday prior, not on its own first day."""
    d = date.fromisoformat(period_start) - timedelta(days=1)
    return d - timedelta(days=(d.weekday() - WORK_ARRANGEMENT_DEADLINE_WEEKDAY) % 7)


def work_arrangement_open_periods(d=None, ahead=WORK_ARRANGEMENT_OPEN_PERIODS):
    """The periods still accepting filings, earliest first. Note what this
    implies and the UI must say plainly: once a period has BEGUN it is closed,
    because its deadline was the Friday before it started. On August 20 you are
    filing for September, not fixing the second half of August."""
    d = d or tz.today_local()
    ps = work_arrangement_period(d)
    out = []
    # The current period is normally already closed, so allow a couple of hops
    # before the first open one; deadlines only move later from there.
    for _ in range(ahead + 2):
        if d <= work_arrangement_deadline(ps):
            out.append(ps)
            if len(out) >= ahead:
                break
        ps = work_arrangement_next_period(ps)
    return out


def work_arrangement_period_workdays(period_start):
    """The Mon–Fri dates inside a period, as (date, weekday index). A nominated
    weekday recurs 2–3 times in a half-month — 'Friday Day off' means EVERY
    Friday in the period — so the schedule view and the printed annex need the
    actual dates, not just the day name."""
    s, e = work_arrangement_period_bounds(period_start)
    out, d = [], s
    while d <= e:
        if d.weekday() < 5:
            out.append((d, d.weekday()))
        d += timedelta(days=1)
    return out


def work_arrangement_schedule_period(d=None):
    """The period whose schedule people actually need to SEE — what the hub,
    the landing card and the team schedule open on.

    Normally that is the calendar period today falls in. But a period stops
    being the answer once it has no workdays left: on Saturday the 15th nobody
    will work another day under the 1st–15th arrangement, so the schedule worth
    showing is already the 16th-to-end-of-month one.

    Deliberately NOT work_arrangement_period(), which answers the calendar
    question — which half of the month is this date in — and is what filing
    deadlines, the "No AWA" intervals and the annex key on. Rolling those
    forward early would change what people may file and which period a tag
    covers; this changes only what a page opens on."""
    d = d or tz.today_local()
    ps = work_arrangement_period(d)
    if any(day >= d for day, _wd in work_arrangement_period_workdays(ps)):
        return ps
    return work_arrangement_next_period(ps)


# Monday..Sunday. _WA_DAY_NAMES is the WORKING week and stops at Friday, but a
# day view can be pointed at a Saturday and still has to name it.
_WA_ALL_DAY_NAMES = _WA_DAY_NAMES + ["Saturday", "Sunday"]


def work_arrangement_date_label(d):
    """'Tuesday, August 18, 2026'. A date is always quoted with its weekday
    spelled out, because 'the 18th' is ambiguous the week you read it — and
    because the weekday is the half that decides who is off."""
    return (f"{_WA_ALL_DAY_NAMES[d.weekday()]}, {_MONTH_NAMES[d.month - 1]} "
            f"{d.day}, {d.year}")


def _wa_friday(d):
    """A deadline, quoted in full. Deadlines are always Fridays by
    construction (work_arrangement_deadline), so this is the general date
    label — kept as its own name because the callers are about deadlines."""
    return work_arrangement_date_label(d)


def work_arrangement_deadline_label(period_start):
    return _wa_friday(work_arrangement_deadline(period_start))


# ---- validation + derived text --------------------------------------------

def work_arrangement_weeks(period_start, weekday):
    """(first, last) Monday of the calendar weeks a nominated weekday actually
    falls in inside a period — the Python twin of the week_head/week_tail
    columns, and what the readable refusals are built from.

    Not simply the period's own first and last week: a Wednesday filing for
    September 1-15, 2026 runs out on the 9th, so it never reaches the week the
    15th sits in and leaves that week free for the period after it.
    """
    days = [d for d, wd in work_arrangement_period_workdays(period_start)
            if wd == weekday]
    if not days:                       # Mon-Fri always recurs in a half-month
        return None, None
    return (days[0] - timedelta(days=weekday), days[-1] - timedelta(days=weekday))


def work_arrangement_week_label(monday):
    """'September 14-18, 2026' — the working week, named the way the period
    labels are, so a refusal about a week reads like the rest of the module."""
    fri = monday + timedelta(days=4)
    if monday.month == fri.month:
        return (f"{_MONTH_NAMES[monday.month - 1]} {monday.day}-{fri.day}, "
                f"{fri.year}")
    return (f"{_MONTH_NAMES[monday.month - 1]} {monday.day} - "
            f"{_MONTH_NAMES[fri.month - 1]} {fri.day}, {fri.year}")


def _wa_remarks(arrangement, weekday, note=None):
    """The ANNEX C Remarks cell. The source file's hidden dropdown list is just
    weekday x {Day off, WFH}, so this is derived from the two stored columns and
    never kept as its own text — one fewer thing that can contradict the record.
    The person's own note is appended after it."""
    base = ""
    if weekday is not None and 0 <= weekday < len(_WA_DAY_NAMES):
        if arrangement == "CWW":
            base = f"{_WA_DAY_NAMES[weekday]} Day off"
        elif arrangement == "WFH":
            base = f"{_WA_DAY_NAMES[weekday]} WFH"
    note = (note or "").strip()
    return f"{base} — {note}" if base and note else (base or note)


def _wa_validate(arrangement, weekday):
    """Shared field checks for both filing and changing. Returns the cleaned
    (arrangement, weekday); raises ValueError with copy a person can act on."""
    arrangement = (arrangement or "").strip().upper()
    if arrangement not in WORK_ARRANGEMENT_LABELS:
        raise ValueError("Pick a work arrangement: regular, compressed workweek, "
                         "or work from home.")
    if arrangement not in _WA_DAY_TYPES:
        return arrangement, None            # a regular week nominates no day
    try:
        weekday = int(weekday)
    except (TypeError, ValueError):
        raise ValueError("Pick which weekday this applies to — Monday to Friday.")
    if not 0 <= weekday <= 4:
        raise ValueError("Work arrangements are set within the work week (Mon–Fri).")
    return arrangement, weekday


def get_work_arrangement_reopen(conn, period_start):
    """The admin override row for this period, or None if it isn't reopened."""
    row = conn.execute(
        "SELECT period_start, reopened_by, reopened_at, note "
        "FROM work_arrangement_reopen WHERE period_start=?", (period_start,)
    ).fetchone()
    if not row:
        return None
    return {"period_start": row[0], "reopened_by": row[1],
            "reopened_at": row[2], "note": row[3]}


def list_work_arrangement_reopens(conn):
    """Every period an admin has reopened, most recent period first — for the
    admin console and for folding into the periods a person sees as fileable."""
    rows = conn.execute(
        "SELECT r.period_start, r.reopened_by, r.reopened_at, r.note, "
        "       COALESCE(rp.name, u.username, '') AS reopened_by_name "
        "FROM work_arrangement_reopen r "
        "LEFT JOIN admin_user u ON u.id = r.reopened_by "
        "LEFT JOIN resource_person rp ON rp.id = u.rp_id "
        "ORDER BY r.period_start DESC"
    ).fetchall()
    return [{"period_start": r[0], "reopened_by": r[1], "reopened_at": r[2],
             "note": r[3], "reopened_by_name": r[4]} for r in rows]


def set_work_arrangement_reopen(conn, period_start, admin_user_id, note=None):
    """Reopen `period_start` for filing again, past its own Friday deadline.
    Setting it again (e.g. to change the note) just refreshes who and when."""
    conn.execute(
        "INSERT INTO work_arrangement_reopen(period_start, reopened_by, "
        "                                    reopened_at, note) "
        "VALUES (?,?,?,?) "
        "ON CONFLICT(period_start) DO UPDATE SET "
        "  reopened_by=excluded.reopened_by, reopened_at=excluded.reopened_at, "
        "  note=excluded.note",
        (period_start, admin_user_id, tz.now_iso(),
         (note or "").strip() or None))
    conn.commit()


def clear_work_arrangement_reopen(conn, period_start):
    """Close a period back up — undoes set_work_arrangement_reopen."""
    conn.execute("DELETE FROM work_arrangement_reopen WHERE period_start=?",
                 (period_start,))
    conn.commit()


def _wa_check_period_open(conn, period_start, d=None):
    """Return the period key if it is still accepting filings, else raise with a
    message that names BOTH the deadline that was missed and the next period the
    person can still file for — a refusal that doesn't say what to do instead is
    just a dead end.

    An admin's reopen override (work_arrangement_reopen) short-circuits this:
    a period an admin has temporarily reopened is accepted even though its own
    Friday deadline has passed."""
    d = d or tz.today_local()
    ps = (period_start or "").strip()
    try:
        date.fromisoformat(ps)
    except ValueError:
        raise ValueError("Pick a valid half-month period.")
    open_ps = work_arrangement_open_periods(d)
    if ps in open_ps or get_work_arrangement_reopen(conn, ps):
        return ps
    if open_ps and ps > open_ps[-1]:
        raise ValueError(
            f"{work_arrangement_period_label(ps)} isn't open for filing yet — "
            f"the schedule is set a period or two at a time. You can file for "
            f"{work_arrangement_period_label(open_ps[-1])} now.")
    msg = (f"The deadline for {work_arrangement_period_label(ps)} was "
           f"{work_arrangement_deadline_label(ps)}.")
    if open_ps:
        msg += (f" You can file for {work_arrangement_period_label(open_ps[0])} "
                f"until {work_arrangement_deadline_label(open_ps[0])}.")
    raise ValueError(msg)


# ---- reads ----------------------------------------------------------------

_WA_SELECT = """
    SELECT w.id, w.user_id, w.period_start, w.arrangement, w.weekday, w.note,
           w.status, w.supersedes_id, w.decided_by, w.decided_at, w.decide_note,
           w.created_at, u.username, rp.name, rp.position,
           ou.short_name, ou.path, COALESCE(rpd.name, ud.username, '')
    FROM work_arrangement w
    JOIN admin_user u ON u.id = w.user_id
    LEFT JOIN resource_person rp ON rp.id = u.rp_id
    LEFT JOIN org_unit ou ON ou.id = rp.org_unit_id
    LEFT JOIN admin_user ud ON ud.id = w.decided_by
    LEFT JOIN resource_person rpd ON rpd.id = ud.rp_id
"""


def _wa_hydrate(row):
    """One DB row -> the flat dict every caller and template reads. Labels and
    the Remarks text are derived here so the screen, the queue and the printed
    annex can never word the same record differently."""
    (wid, user_id, period_start, arrangement, weekday, note, status,
     supersedes_id, decided_by, decided_at, decide_note, created_at,
     username, name, position, short_name, path, decided_by_name) = row
    return {
        "id": wid, "user_id": user_id, "period_start": period_start,
        "period_label": work_arrangement_period_label(period_start),
        "deadline_label": work_arrangement_deadline_label(period_start),
        "arrangement": arrangement,
        "arrangement_label": WORK_ARRANGEMENT_LABELS.get(arrangement, arrangement),
        "weekday": weekday,
        "weekday_name": _WA_DAY_NAMES[weekday] if weekday is not None else "",
        "remarks": _wa_remarks(arrangement, weekday, note),
        "note": note, "status": status, "supersedes_id": supersedes_id,
        "is_change": supersedes_id is not None,
        "decided_by": decided_by, "decided_by_name": decided_by_name,
        "decided_at": decided_at, "decide_note": decide_note,
        "created_at": created_at, "username": username,
        "person_name": name or username, "position": position or "",
        "section": short_name or "", "org_path": path or "",
    }


def get_work_arrangement(conn, wa_id):
    """One arrangement, hydrated. When it is a change request, `replaces`
    carries a short summary of the row still in force, so the approver sees the
    delta rather than just the destination."""
    row = conn.execute(_WA_SELECT + " WHERE w.id = ?", (wa_id,)).fetchone()
    if not row:
        return None
    out = _wa_hydrate(row)
    if out["supersedes_id"]:
        prev = conn.execute(
            "SELECT arrangement, weekday, note FROM work_arrangement WHERE id=?",
            (out["supersedes_id"],)).fetchone()
        if prev:
            out["replaces"] = {
                "arrangement": prev[0],
                "arrangement_label": WORK_ARRANGEMENT_LABELS.get(prev[0], prev[0]),
                "weekday": prev[1],
                "remarks": _wa_remarks(prev[0], prev[1], prev[2]),
            }
    return out


def list_my_work_arrangements(conn, user_id, limit=12):
    """The person's own filings, newest period first — their record and the
    trail of anything denied, withdrawn or superseded along the way."""
    rows = conn.execute(
        _WA_SELECT + " WHERE w.user_id = ? ORDER BY w.period_start DESC, w.id DESC "
        "LIMIT ?", (user_id, limit)).fetchall()
    return [_wa_hydrate(r) for r in rows]


def _wa_one_by_status(conn, user_id, period_start, status):
    row = conn.execute(
        _WA_SELECT + " WHERE w.user_id = ? AND w.period_start = ? AND w.status = ?",
        (user_id, period_start, status)).fetchone()
    return _wa_hydrate(row) if row else None


def my_work_arrangement_for(conn, user_id, period_start):
    """The APPROVED arrangement for a period — the schedule actually in force."""
    return _wa_one_by_status(conn, user_id, period_start, "approved")


def my_pending_work_arrangement(conn, user_id, period_start):
    """The in-flight filing or change for a period, if any."""
    return _wa_one_by_status(conn, user_id, period_start, "pending")


def work_arrangement_week_conflict(conn, user_id, period_start, arrangement,
                                   weekday, exclude_id=None):
    """The live filing in ANOTHER period whose nominated day shares a Mon-Fri
    week with the one described, or None. The returned row carries `week_start`
    (the Monday they collide in) and `clash_date` (the day already spoken for),
    so the caller can say which week and which day rather than just "no".

    An alternative work arrangement is one day a week. Inside a period that is
    already true — there is only ever one filing — but a half-month period ends
    mid-week, so the week of the 14th to the 18th is half in one period and half
    in the next, and two separate filings can land in it. This is the only place
    that can happen, and the only thing this looks for.

    REG nominates no day and never conflicts, in either direction."""
    if arrangement not in _WA_DAY_TYPES or weekday is None:
        return None
    head, tail = work_arrangement_weeks(period_start, weekday)
    if head is None:
        return None
    qs = ",".join("?" * len(_WA_LIVE))
    sql = (_WA_SELECT + f" WHERE w.user_id = ? AND w.status IN ({qs}) "
           "AND w.weekday IS NOT NULL AND w.period_start <> ? "
           "AND (w.week_head IN (?, ?) OR w.week_tail IN (?, ?))")
    args = [user_id, *_WA_LIVE, period_start,
            head.isoformat(), tail.isoformat(),
            head.isoformat(), tail.isoformat()]
    if exclude_id is not None:        # re-checking a row against everything else
        sql += " AND w.id <> ?"
        args.append(exclude_id)
    rows = conn.execute(sql + " ORDER BY w.period_start LIMIT 1", args).fetchall()
    if not rows:
        return None
    other = _wa_hydrate(rows[0])
    o_head, o_tail = work_arrangement_weeks(other["period_start"],
                                            other["weekday"])
    shared = o_head if o_head in (head, tail) else o_tail
    other["week_start"] = shared
    other["clash_date"] = shared + timedelta(days=other["weekday"])
    return other


def _wa_check_week_free(conn, user_id, period_start, arrangement, weekday,
                        exclude_id=None):
    """Raise the refusal a person can act on if this filing would be their
    second alternative work arrangement day in one week."""
    other = work_arrangement_week_conflict(conn, user_id, period_start,
                                           arrangement, weekday, exclude_id)
    if not other:
        return
    standing = ("already approved" if other["status"] == "approved"
                else "already waiting for approval")
    raise ValueError(
        f"That would be your second work arrangement day in the week of "
        f"{work_arrangement_week_label(other['week_start'])}. "
        f"{_wa_remarks(other['arrangement'], other['weekday'])} on "
        f"{work_arrangement_date_label(other['clash_date'])} is {standing} "
        f"under {other['period_label']}, and that week runs across both "
        f"periods. An alternative work arrangement is one day a week — pick a "
        f"weekday outside that week, or change the other filing first.")


# ---- writes ---------------------------------------------------------------

def create_work_arrangement(conn, user_id, period_start, arrangement,
                            weekday=None, note=None):
    """File this person's work arrangement for one half-month period. Validates
    ANNEX C's rules and raises ValueError with a human-readable reason; returns
    the new row id.

    Section coverage is deliberately NOT checked here. A thin day is a warning
    both the employee and the approving chief see, never a block — see
    work_arrangement_coverage_note."""
    arrangement, weekday = _wa_validate(arrangement, weekday)
    ps = _wa_check_period_open(conn, period_start)
    # Refuse rather than silently dropping the tag: someone stated a reason they
    # have no arrangement, and deleting that as a side effect of an unrelated
    # action is the kind of surprise that costs trust in the record.
    if get_work_arrangement_noawa(conn, user_id, ps):
        raise ValueError(
            "You're currently marked “No AWA”. Remove that first if you're "
            "filing a work arrangement again.")
    if my_work_arrangement_for(conn, user_id, ps):
        raise ValueError(
            f"You already have an approved work arrangement for "
            f"{work_arrangement_period_label(ps)}. Use “Request a change” to "
            f"file a different one.")
    if my_pending_work_arrangement(conn, user_id, ps):
        raise ValueError(
            f"You already have a work arrangement waiting for approval for "
            f"{work_arrangement_period_label(ps)}. Withdraw it first if you "
            f"want to file something different.")
    # One AWA day a week, counting across the period boundary that splits a
    # working week in two. A filing still waiting for approval holds its week:
    # letting a second one through would only queue up a clash for the chief.
    _wa_check_week_free(conn, user_id, ps, arrangement, weekday)
    cur = conn.execute(
        """INSERT INTO work_arrangement(user_id, period_start, arrangement,
                                        weekday, note, status, created_at)
           VALUES (?,?,?,?,?,'pending',?)""",
        (user_id, ps, arrangement, weekday, (note or "").strip() or None,
         tz.now_iso()))
    conn.commit()
    return cur.lastrowid


def request_work_arrangement_change(conn, wa_id, user_id, arrangement,
                                    weekday=None, note=None):
    """Ask to change an arrangement that has already been approved. Only the
    person it belongs to may start this — a chief or an admin cannot rewrite
    someone's schedule for them.

    The approved row is left alone and stays in force; this files a SUCCESSOR
    that supersedes it only once the same approver signs off. So at no point is
    the person without a schedule, and a denied change simply leaves the
    original standing."""
    current = get_work_arrangement(conn, wa_id)
    if not current:
        raise ValueError("That work arrangement no longer exists.")
    if current["user_id"] != user_id:
        raise PermissionError(
            "Only the person a work arrangement belongs to can change it.")
    if current["status"] != "approved":
        raise ValueError(
            "That request hasn't been approved yet — withdraw it and file "
            "again instead of changing it.")
    arrangement, weekday = _wa_validate(arrangement, weekday)
    ps = _wa_check_period_open(conn, current["period_start"])
    if my_pending_work_arrangement(conn, user_id, ps):
        raise ValueError(
            "You already have a change waiting for approval for this period.")
    if arrangement == current["arrangement"] and weekday == current["weekday"]:
        raise ValueError("That is the arrangement you already have — pick a "
                         "different one.")
    # Changing a day can walk INTO a boundary week the old day stayed clear of,
    # so the weekly rule is checked against the new day, not the filed one.
    _wa_check_week_free(conn, user_id, ps, arrangement, weekday)
    cur = conn.execute(
        """INSERT INTO work_arrangement(user_id, period_start, arrangement,
                                        weekday, note, status, supersedes_id,
                                        created_at)
           VALUES (?,?,?,?,?,'pending',?,?)""",
        (user_id, ps, arrangement, weekday, (note or "").strip() or None,
         wa_id, tz.now_iso()))
    conn.commit()
    return cur.lastrowid


def cancel_work_arrangement(conn, wa_id, user_id):
    """Withdraw a request that is still waiting for approval. On an original
    filing this frees the period to be filed again; on a change request the
    arrangement it would have replaced simply stays in force."""
    row = get_work_arrangement(conn, wa_id)
    if not row:
        raise ValueError("That work arrangement no longer exists.")
    if row["user_id"] != user_id:
        raise ValueError("That isn't your work arrangement to withdraw.")
    if row["status"] != "pending":
        raise ValueError("Only a request still waiting for approval can be "
                         "withdrawn.")
    conn.execute("UPDATE work_arrangement SET status='cancelled' WHERE id=?",
                 (wa_id,))
    conn.commit()
    return get_work_arrangement(conn, wa_id)


# ---- "No AWA": a standing tag, not a filing ---------------------------------
#
# Some people have no alternative work arrangement and a reason for it: on leave,
# or waiting on a decision made outside the bureau (the source ANNEX C had both —
# "Leave", and "for approval from OSEC"). On the spreadsheet those read as blank
# rows, indistinguishable from someone who simply never filed.
#
# A tag is a statement of fact rather than a request for a schedule, so it needs
# no approver and no filing window — which is also what lets it cover a situation
# that arises mid-period, after the Friday deadline has closed. It is stored as an
# INTERVAL so it carries into each new period on its own, and editing the reason
# closes the old interval and opens a new one: a submitted August annex keeps what
# it said in August even if the wording changes in September.

def _wa_noawa_hydrate(row):
    (nid, user_id, remark, eff_from, eff_to, created_by, created_at,
     ended_by, ended_at) = row
    return {
        "id": nid, "user_id": user_id, "remark": remark,
        "effective_from": eff_from,
        "effective_from_label": work_arrangement_period_label(eff_from),
        "effective_to": eff_to, "created_by": created_by,
        "created_at": created_at, "ended_by": ended_by, "ended_at": ended_at,
        "arrangement": WORK_ARRANGEMENT_NOAWA,
    }


_WA_NOAWA_COLS = ("id, user_id, remark, effective_from, effective_to, "
                  "created_by, created_at, ended_by, ended_at")


def get_work_arrangement_noawa(conn, user_id, period_start=None):
    """The tag in force for a period (the current one by default), or None. An
    interval covers a period when it started on or before it and hasn't ended by
    then — so a tag set in August is still there in September without anything
    having run in between."""
    ps = period_start or work_arrangement_period()
    row = conn.execute(
        f"SELECT {_WA_NOAWA_COLS} FROM work_arrangement_noawa "
        "WHERE user_id = ? AND effective_from <= ? "
        "AND (effective_to IS NULL OR ? < effective_to) "
        "ORDER BY effective_from DESC LIMIT 1",
        (user_id, ps, ps)).fetchone()
    return _wa_noawa_hydrate(row) if row else None


def _wa_noawa_for_period(conn, period_start):
    """{user_id: tag} for everyone tagged in one period — one query behind the
    roster, the coverage tally and both exports, so they cannot disagree."""
    rows = conn.execute(
        f"SELECT {_WA_NOAWA_COLS} FROM work_arrangement_noawa "
        "WHERE effective_from <= ? AND (effective_to IS NULL OR ? < effective_to) "
        "ORDER BY effective_from",
        (period_start, period_start)).fetchall()
    return {r[1]: _wa_noawa_hydrate(r) for r in rows}


def _wa_noawa_may_act(actor, user_id):
    """Either the person themselves or an admin. Deliberately symmetric with who
    may remove it: an admin has to be able to record a leave for someone who
    isn't logging in, and nobody else should be able to speak for them."""
    return bool(actor) and (actor.get("id") == user_id
                            or actor.get("role") == "admin")


def set_work_arrangement_noawa(conn, user_id, remark, actor):
    """Start the tag, or replace its reason. Takes effect immediately — there is
    no approval step and no deadline. Returns the live tag.

    Replacing the reason ends the current interval and opens a new one from the
    current period rather than editing in place, so a period whose annex has
    already gone out keeps the wording it was submitted with."""
    if not _wa_noawa_may_act(actor, user_id):
        raise PermissionError(
            "Only the person themselves or an administrator can record this.")
    remark = (remark or "").strip()
    if not remark:
        raise ValueError("Say why there's no work arrangement — a short reason "
                         "is what makes the blank row on the form mean something.")
    ps = work_arrangement_period()
    now = tz.now_iso()
    live = conn.execute(
        "SELECT id, remark, effective_from FROM work_arrangement_noawa "
        "WHERE user_id = ? AND effective_to IS NULL", (user_id,)).fetchone()
    try:
        if live:
            if live[1] == remark:
                return get_work_arrangement_noawa(conn, user_id, ps)
            if live[2] == ps:
                # Started this period and reworded within it — no history to keep
                # yet, so just correct it rather than opening a second interval.
                conn.execute(
                    "UPDATE work_arrangement_noawa SET remark = ? WHERE id = ?",
                    (remark, live[0]))
                conn.commit()
                return get_work_arrangement_noawa(conn, user_id, ps)
            conn.execute(
                "UPDATE work_arrangement_noawa SET effective_to = ?, ended_by = ?, "
                "ended_at = ? WHERE id = ?", (ps, actor.get("id"), now, live[0]))
        conn.execute(
            "INSERT INTO work_arrangement_noawa(user_id, remark, effective_from, "
            "created_by, created_at) VALUES (?,?,?,?,?)",
            (user_id, remark, ps, actor.get("id"), now))
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    return get_work_arrangement_noawa(conn, user_id, ps)


def end_work_arrangement_noawa(conn, user_id, actor):
    """Remove the tag from the current period on. Earlier periods keep it, so a
    form already submitted still reads the way it was submitted."""
    if not _wa_noawa_may_act(actor, user_id):
        raise PermissionError(
            "Only the person themselves or an administrator can remove this.")
    live = conn.execute(
        "SELECT id, effective_from FROM work_arrangement_noawa "
        "WHERE user_id = ? AND effective_to IS NULL", (user_id,)).fetchone()
    if not live:
        raise ValueError("There's no “No AWA” to remove.")
    ps = work_arrangement_period()
    if live[1] >= ps:
        # Never applied to a completed period, so there is nothing to preserve.
        conn.execute("DELETE FROM work_arrangement_noawa WHERE id = ?", (live[0],))
    else:
        conn.execute(
            "UPDATE work_arrangement_noawa SET effective_to = ?, ended_by = ?, "
            "ended_at = ? WHERE id = ?",
            (ps, actor.get("id"), tz.now_iso(), live[0]))
    conn.commit()


# ---- approval --------------------------------------------------------------

def decide_work_arrangement(conn, wa_id, user, action, note=None):
    """Approve or deny a pending arrangement. Raises ValueError (bad state or
    input) or PermissionError (not this user's to decide). Returns the updated
    row.

    Approving a CHANGE retires the row it replaces in the same transaction, so
    the "one approved per period" index is never momentarily violated and the
    person is never momentarily without a schedule."""
    row = get_work_arrangement(conn, wa_id)
    if not row:
        raise ValueError("That work arrangement request no longer exists.")
    if row["status"] != "pending":
        raise ValueError("That request has already been decided.")
    if action not in ("approve", "deny"):
        raise ValueError("Unknown decision.")
    if not is_approver_for(conn, user, row["user_id"]):
        raise PermissionError("That request isn't yours to decide.")
    # Filing already refuses a second day in one week, so this should never
    # fire — unless the clashing row predates the rule or was written around it.
    # Better the approver learns that here than signs off a schedule the annex
    # would then have to print twice in one week.
    if action == "approve":
        _wa_check_week_free(conn, row["user_id"], row["period_start"],
                            row["arrangement"], row["weekday"],
                            exclude_id=wa_id)
    status = "approved" if action == "approve" else "denied"
    note = (note or "").strip() or None
    try:
        if status == "approved" and row["supersedes_id"]:
            conn.execute("UPDATE work_arrangement SET status='superseded' "
                         "WHERE id=? AND status='approved'",
                         (row["supersedes_id"],))
        conn.execute(
            "UPDATE work_arrangement SET status=?, decided_by=?, decided_at=?, "
            "decide_note=? WHERE id=?",
            (status, user["id"], tz.now_iso(), note, wa_id))
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    return get_work_arrangement(conn, wa_id)


def list_work_arrangement_approvals(conn, user):
    """Pending arrangements this user may decide, earliest period first. A chief
    sees exactly what the escalation chain routes to them; an admin additionally
    sees the requests it routes to nobody (see list_wellness_approvals — the same
    rule, so the two queues can't disagree about who decides what). Each row
    carries its coverage verdict, so the queue can flag a decision that would
    empty a section before it is made rather than after."""
    rows = conn.execute(
        _WA_SELECT + " WHERE w.status='pending' AND w.user_id != ? "
        "ORDER BY w.period_start, w.id", (user["id"],)).fetchall()
    out = _mine_or_orphaned(conn, user,
                            [get_work_arrangement(conn, r[0]) for r in rows],
                            lambda w: w["user_id"])
    for w in out:
        w["coverage_flag"] = work_arrangement_coverage_flag(conn, w)
    return out


def unseen_work_arrangement_decisions(conn, user_id):
    """Statuses ('approved'/'denied') of MY OWN work-arrangement requests
    decided since I last opened /work-arrangement, newest first — empty if
    none. See unseen_wellness_decisions — same idea, the AWA twin."""
    rows = conn.execute(
        "SELECT w.status FROM work_arrangement w JOIN admin_user a ON a.id = w.user_id "
        "WHERE w.user_id=? AND w.status IN ('approved','denied') "
        "AND w.decided_at IS NOT NULL "
        "AND (a.wa_seen_at IS NULL OR w.decided_at > a.wa_seen_at) "
        "ORDER BY w.decided_at DESC", (user_id,)).fetchall()
    return [r[0] for r in rows]


def mark_work_arrangement_seen(conn, user_id):
    """Stamp now as this account's last look at /work-arrangement — clears the
    nav bell's 'your request was decided' notice."""
    conn.execute("UPDATE admin_user SET wa_seen_at=? WHERE id=?",
                 (tz.now_iso(), user_id))
    conn.commit()


# ---- section coverage — advice, never a block ------------------------------

def work_arrangement_coverage(conn, org_path, period_start, exclude_user_id=None,
                              tagged=None):
    """Per-weekday staffing for ONE section in one period.

    Scope is the EXACT org path, not the subtree: "who is left in my section on
    Friday" is the operational question, and rolling a whole division up would
    hide an empty section behind a full one.

    CWW and WFH are counted apart on purpose. A compressed-workweek day off
    removes a person entirely; someone working from home is still working, just
    not in the building. "Nobody on-site" and "nobody working" are different
    problems and the copy has to be able to say which.

    Live rows only (pending + approved) — a denied or withdrawn filing frees its
    day again. Where a person holds both an approved row and a pending change,
    the PENDING one counts: that is the state being asked about.

    Anyone tagged "No AWA" drops out entirely — not on-site, not off-site, just
    out of the denominator. Someone on leave was never going to be at a desk on
    Friday, and counting them either way misstates the coverage this whole
    warning exists to report.

    Returns {"headcount": n, "excluded": n, "weekdays": [{idx, name, cww, wfh,
    offsite, onsite, names}, ...]} — five entries, Monday to Friday. Only
    accounts take part, so headcount is the set of people who could file."""
    people = conn.execute("""
        SELECT a.id, COALESCE(rp.name, a.username)
        FROM admin_user a
        JOIN resource_person rp ON rp.id = a.rp_id AND rp.is_internal = 1
        JOIN org_unit ou ON ou.id = rp.org_unit_id
        WHERE a.active = 1 AND rp.archived_at IS NULL AND ou.path = ?
    """, (org_path or "",)).fetchall()
    people = [(uid, name) for uid, name in people if uid != exclude_user_id]
    # `tagged` is identical for every org path in a period, so a caller looping
    # over sections passes it in once instead of paying this query per section
    # (see work_arrangement_period_summary).
    if tagged is None:
        tagged = _wa_noawa_for_period(conn, period_start)
    excluded = sum(1 for uid, _n in people if uid in tagged)
    people = [(uid, name) for uid, name in people if uid not in tagged]
    ids = {uid for uid, _n in people}
    names = dict(people)

    qs = ",".join("?" * len(_WA_LIVE))
    rows = conn.execute(
        f"SELECT user_id, arrangement, weekday, status FROM work_arrangement "
        f"WHERE period_start=? AND status IN ({qs}) ORDER BY id",
        (period_start, *_WA_LIVE)).fetchall()
    # A pending change outranks the approved row it would replace.
    picked = {}
    for uid, arrangement, weekday, status in rows:
        if uid not in ids:
            continue
        if status == "pending" or uid not in picked:
            picked[uid] = (arrangement, weekday)

    weekdays = []
    for idx, name in WORK_ARRANGEMENT_WEEKDAYS:
        cww = [names[u] for u, (a, w) in picked.items() if a == "CWW" and w == idx]
        wfh = [names[u] for u, (a, w) in picked.items() if a == "WFH" and w == idx]
        weekdays.append({
            "idx": idx, "name": name,
            "cww": len(cww), "wfh": len(wfh),
            "offsite": len(cww) + len(wfh),
            "onsite": len(people) - len(cww) - len(wfh),
            "names": sorted(cww + wfh),
        })
    return {"headcount": len(people), "excluded": excluded, "weekdays": weekdays}


def _wa_org_path(conn, user_id):
    """The section path an account sits in, or None when they aren't linked to
    the directory (coverage is meaningless for them)."""
    row = conn.execute("""
        SELECT ou.path FROM admin_user a
        JOIN resource_person rp ON rp.id = a.rp_id
        JOIN org_unit ou ON ou.id = rp.org_unit_id
        WHERE a.id = ? LIMIT 1
    """, (user_id,)).fetchone()
    return row[0] if row and row[0] else None


def work_arrangement_coverage_note(conn, user_id, period_start, arrangement,
                                   weekday):
    """The one-line advisory for a hypothetical pick, as the employee sees it
    while choosing a day. Returns "" when there is nothing worth saying.

    This NEVER raises and is never consulted by create_work_arrangement — a thin
    day is the section chief's call, not the database's."""
    if arrangement not in _WA_DAY_TYPES or weekday is None:
        return ""
    path = _wa_org_path(conn, user_id)
    if not path:
        return ""
    cov = work_arrangement_coverage(conn, path, period_start,
                                    exclude_user_id=user_id)
    day = cov["weekdays"][weekday]
    others = cov["headcount"]                    # already excludes this person
    if others <= 0 or day["offsite"] <= 0:
        return ""
    left = day["onsite"] - 1                     # this person would be off too
    who = f"{day['offsite']} of {others}"
    if left <= 0:
        return (f"{who} others in your section are already off on {day['name']} — "
                f"adding yours would leave nobody on-site that day.")
    return (f"{who} others in your section are already off on {day['name']}. "
            f"Filing this leaves {left} on-site.")


def work_arrangement_coverage_flag(conn, row):
    """The approver's verdict on one pending request: a short phrase when
    approving it would leave the section thin or empty on that weekday, else "".
    Same computation as the employee's note — one function behind both, so the
    two can never contradict each other."""
    if row.get("arrangement") not in _WA_DAY_TYPES or row.get("weekday") is None:
        return ""
    path = row.get("org_path")
    if not path:
        return ""
    cov = work_arrangement_coverage(conn, path, row["period_start"],
                                    exclude_user_id=row["user_id"])
    day = cov["weekdays"][row["weekday"]]
    left = day["onsite"]                         # this person is excluded already
    if left <= 0:
        return f"Approving leaves nobody on-site on {day['name']}"
    if left == 1:
        return f"Only 1 on-site on {day['name']} after this"
    return ""


# ---- the period roster (the ANNEX C body, on screen and in print) ----------

def work_arrangement_roster(conn, period_start, user=None, tagged=None):
    """Every participating account for a period, filed or not, ordered the way
    ANNEX C groups them (by division/section, then name).

    This reads FROM admin_user outward, not from work_arrangement inward, which
    is the whole point: the blanks ARE the information. Someone who never filed
    appears as a row with no arrangement, so the Admin Officer has a chase list
    before the deadline instead of 23 silent gaps after it.

    Scoped to the viewer's own directory unit subtree (see _org_scope_for_user),
    widened by a bureau-wide work-arrangement grant; an unscoped call
    (user=None) — which is what the ANNEX C export makes — sees the whole
    bureau."""
    scope = _org_scope_for_user(conn, user, area="awa") if user else None
    rows = conn.execute("""
        SELECT a.id, a.username, rp.name, rp.position, ou.short_name, ou.path,
               a.rp_id, (rp.photo IS NOT NULL), a.avatar_kind
        FROM admin_user a
        LEFT JOIN resource_person rp ON rp.id = a.rp_id
        LEFT JOIN org_unit ou ON ou.id = rp.org_unit_id
        WHERE a.active = 1 AND rp.archived_at IS NULL
        ORDER BY ou.path, rp.name, a.username
    """).fetchall()
    live = {}
    qs = ",".join("?" * len(_WA_LIVE))
    for r in conn.execute(
            _WA_SELECT + f" WHERE w.period_start=? AND w.status IN ({qs})",
            (period_start, *_WA_LIVE)).fetchall():
        w = _wa_hydrate(r)
        # An approved row is what's in force; a pending one is only ever shown
        # as such, so let 'approved' win when a person holds both.
        if w["user_id"] not in live or w["status"] == "approved":
            live[w["user_id"]] = w
    if tagged is None:
        tagged = _wa_noawa_for_period(conn, period_start)
    out = []
    for (uid, username, name, position, short_name, path,
         rp_id, has_photo, avatar_kind) in rows:
        if not _path_in_scope(path, scope):
            continue
        base = {"user_id": uid, "name": name or username,
                "position": position or "", "section": short_name or "",
                "org_path": path or "",
                # Joined, not a second query: enough for a caller to draw this
                # person's face (directory photo -> companion -> initials).
                "rp_id": rp_id, "has_photo": bool(has_photo),
                "avatar_kind": avatar_kind}
        tag = tagged.get(uid)
        if tag:
            # A stated reason outranks any stale filing: the person told us they
            # have no arrangement, and that is not a gap to chase.
            out.append({**base, "arrangement": WORK_ARRANGEMENT_NOAWA,
                        "arrangement_label": WORK_ARRANGEMENT_NOAWA,
                        "weekday": None, "remarks": tag["remark"],
                        "status": "noawa", "id": None, "filed": True,
                        "approved": True, "noawa": True})
            continue
        w = live.get(uid)
        out.append({
            **base,
            "arrangement": w["arrangement"] if w else "",
            "arrangement_label": w["arrangement_label"] if w else "",
            "weekday": w["weekday"] if w else None,
            "remarks": w["remarks"] if w else "",
            "status": w["status"] if w else "",
            "id": w["id"] if w else None,
            "filed": bool(w),
            "approved": bool(w and w["status"] == "approved"),
            "noawa": False,
        })
    return out


# ---- one calendar day (who is actually in the office) ---------------------

# What an arrangement means on ONE date, in the order the day view lists them:
# present first, then the two kinds of absence, then the two kinds of nothing
# on record. (key, heading, what it means)
WORK_ARRANGEMENT_DAY_GROUPS = [
    ("onsite",  "In the office",     "On-site for the day"),
    ("wfh",     "Working from home", "Working, but not in the building"),
    ("dayoff",  "Day off",           "Compressed workweek — not working today"),
    ("noawa",   WORK_ARRANGEMENT_NOAWA,
     "Out of the schedule entirely, with a stated reason"),
    ("unfiled", "Nothing filed",
     "No arrangement on record — expected on-site unless their section says otherwise"),
]


def _wa_day_state(row, weekday):
    """Which group one roster row falls in on a given weekday.

    The nominated weekday RECURS: "Friday Day off" is EVERY Friday in the
    fortnight, not one of them. That is the whole reason a day-by-day view can
    be derived from a fortnightly filing and needs nothing stored per date."""
    if row.get("noawa"):
        return "noawa"
    if not row.get("filed"):
        return "unfiled"
    if row.get("arrangement") in _WA_DAY_TYPES and row.get("weekday") == weekday:
        # CWW's nominated day is a day OFF; WFH's is a day worked from home.
        # Conflating them would report someone on leave as reachable.
        return "dayoff" if row["arrangement"] == "CWW" else "wfh"
    return "onsite"


def work_arrangement_day_step(day, delta):
    """The next or previous WORKING day — Friday steps to Monday, never into a
    weekend nobody is scheduled for."""
    d = day + timedelta(days=delta)
    while d.weekday() >= 5:
        d += timedelta(days=delta)
    return d


def work_arrangement_day(conn, day, user=None):
    """Who is physically in the office on ONE date, by name — and for whoever
    is not, whether that is a day off or a day working from home.

    Derived entirely from the fortnight's ANNEX C filings (see _wa_day_state),
    so it reports the schedule of RECORD, not attendance: this app has no
    attendance relation and must not be read as one. There is also no holiday
    or work-suspension concept anywhere in the system, so a declared non-working
    day still reads here as an ordinary one.

    SCOPE — the load-bearing part. Every other work-arrangement read sits behind
    the chief guard; this one is shown to every signed-in user, so it resolves
    scope itself and stops on "none" rather than calling the roster.
    work_arrangement_roster scopes through _org_scope_for_user, which folds an
    unlinked account's "no team" onto None — the same None that means
    bureau-wide — so falling through would hand someone with no directory
    record every section in the bureau. Guarding here rather than in the
    handler keeps that true for whoever calls this next."""
    day = day if isinstance(day, date) else date.fromisoformat(str(day))
    ps = work_arrangement_period(day)
    out = {
        "date": day, "date_iso": day.isoformat(),
        "date_label": work_arrangement_date_label(day),
        "weekday": day.weekday(), "weekday_name": _WA_ALL_DAY_NAMES[day.weekday()],
        "is_weekend": day.weekday() >= 5,
        "period_start": ps, "period_label": work_arrangement_period_label(ps),
        "kind": "bureau",
        "groups": {k: [] for k, _h, _m in WORK_ARRANGEMENT_DAY_GROUPS},
    }
    if user is not None:
        _scope, out["kind"] = team_scope_for_user(conn, user, area="awa")
    # An unlinked account has no team to show, and a weekend has nobody
    # scheduled. Both are empty for different reasons the caller can tell apart.
    if out["kind"] != "none" and not out["is_weekend"]:
        for r in work_arrangement_roster(conn, ps, user):
            state = _wa_day_state(r, day.weekday())
            out["groups"][state].append({**r, "day_state": state})
    out["counts"] = {k: len(v) for k, v in out["groups"].items()}
    out["headcount"] = sum(out["counts"].values())
    return out


def work_arrangement_period_summary(conn, period_start, user=None):
    """Roster + per-section coverage + the tiles the schedule page leads with.
    `thinnest` is the weekday with the fewest people on-site across the sections
    in view — the Friday problem, surfaced before it is submitted rather than
    noticed in a spreadsheet afterwards."""
    # The "No AWA" set is per-PERIOD, not per-section, so look it up once and
    # hand it to the roster and to every coverage call. It used to be re-queried
    # inside each of them: for a section-scoped chief that was a small waste, but
    # for a bureau-wide view it was one redundant query per section on top of
    # coverage's own two.
    tagged = _wa_noawa_for_period(conn, period_start)
    roster = work_arrangement_roster(conn, period_start, user, tagged=tagged)
    paths = []
    for r in roster:
        if r["org_path"] and r["org_path"] not in paths:
            paths.append(r["org_path"])
    sections = []
    for path in paths:
        cov = work_arrangement_coverage(conn, path, period_start, tagged=tagged)
        if not cov["headcount"]:
            continue
        short = next((r["section"] for r in roster if r["org_path"] == path), "")
        sections.append({"org_path": path, "section": short or path, **cov})
    # Bureau-wide tally across the sections in view, for the coverage panel.
    totals = []
    for idx, name in WORK_ARRANGEMENT_WEEKDAYS:
        onsite = sum(s["weekdays"][idx]["onsite"] for s in sections)
        offsite = sum(s["weekdays"][idx]["offsite"] for s in sections)
        totals.append({"idx": idx, "name": name, "onsite": onsite,
                       "offsite": offsite,
                       "empty_sections": [s["section"] for s in sections
                                          if s["weekdays"][idx]["onsite"] <= 0]})
    thinnest = min(totals, key=lambda t: t["onsite"]) if totals else None
    deadline = work_arrangement_deadline(period_start)
    return {
        "period_start": period_start,
        "period_label": work_arrangement_period_label(period_start),
        "deadline": deadline,
        "deadline_label": work_arrangement_deadline_label(period_start),
        "deadline_passed": tz.today_local() > deadline,
        "roster": roster, "sections": sections, "totals": totals,
        "thinnest": thinnest,
        # People tagged "No AWA" are out of the schedule entirely, so they are
        # not part of the "filed n of m" denominator either — counting them
        # would make the period look permanently incomplete.
        "headcount": sum(1 for r in roster if not r.get("noawa")),
        "noawa": [r["name"] for r in roster if r.get("noawa")],
        "filed": sum(1 for r in roster if r["filed"] and not r.get("noawa")),
        "approved": sum(1 for r in roster if r["approved"] and not r.get("noawa")),
        "pending": sum(1 for r in roster if r["filed"] and not r["approved"]),
        "unfiled": [r["name"] for r in roster if not r["filed"]],
    }


# ---- the printed annex -----------------------------------------------------

def work_arrangement_export_rows(conn, period_start):
    """The ANNEX C body for one period: one row per participating account,
    numbered, grouped by division/section then name — the order the source
    sheets use.

    Only APPROVED arrangements print, plus "No AWA" for anyone carrying a tag.
    Pending, denied and unfiled people appear with the Work Arrangement and
    Remarks cells BLANK — which is exactly how the real sheet reads when someone
    hasn't been dealt with, except that now a blank means only one thing. A
    person who has no arrangement and a reason for it says so on the form
    instead of looking identical to a person nobody chased.

    Both the workbook and the PDF read this, so the two can never disagree."""
    rows = work_arrangement_roster(conn, period_start)
    out = []
    for i, r in enumerate(rows, start=1):
        shown = r["approved"]              # covers 'No AWA' too — it needs no approval
        out.append({
            "no": i,
            "name": r["name"],
            "position": r["position"],
            "division_unit": r["section"],
            "arrangement": r["arrangement"] if shown else "",
            "remarks": r["remarks"] if shown else "",
            "filed": r["filed"],
            "noawa": r.get("noawa", False),
            "status": r["status"],
        })
    return out


def work_arrangement_signatories(conn, user_id=None):
    """Who signs the annex.

    Names turn over faster than anyone remembers to edit a constant, so both are
    resolved from live data rather than hardcoded — nothing else in this repo
    hardcodes a person's name and this shouldn't be the first thing that does.

      * Approved by — the directory's Director (org rank 3).
      * Prepared by — the app_setting override if an admin has pinned one,
        otherwise whoever is generating the export.
    """
    approved_name = _org_seat_name(conn, 3) or ""
    approved_title = ""
    if approved_name:
        row = conn.execute(
            "SELECT position, designation FROM resource_person "
            "WHERE name = ? AND is_internal = 1 LIMIT 1",
            (approved_name.split(" / ")[0],)).fetchone()
        if row:
            approved_title = row[0] or row[1] or ""
    s = get_settings(conn, ["wa_prepared_by_name", "wa_prepared_by_title"])
    prepared_name = (s.get("wa_prepared_by_name") or "").strip()
    prepared_title = (s.get("wa_prepared_by_title") or "").strip()
    if not prepared_name and user_id:
        me = get_admin_user_by_id(conn, user_id)
        rp = get_rp(conn, me["rp_id"]) if me and me.get("rp_id") else None
        if rp:
            prepared_name = rp.get("name") or ""
            prepared_title = prepared_title or rp.get("position") or ""
        elif me:
            prepared_name = me.get("username") or ""
    return {
        "prepared_by": {"name": prepared_name, "title": prepared_title},
        "approved_by": {"name": approved_name, "title": approved_title},
    }


def work_arrangement_annex_data(conn, period_start, user_id=None):
    """Everything either annex format needs, in one dict."""
    return {
        "period_start": period_start,
        "period_label": work_arrangement_period_label(period_start),
        "office_unit": BUREAU_NAME,
        "legend": WORK_ARRANGEMENT_LEGEND,
        "rows": work_arrangement_export_rows(conn, period_start),
        **work_arrangement_signatories(conn, user_id),
    }


def work_arrangement_month_periods(ym):
    """The two half-month periods of 'YYYY-MM'. The bureau circulates ANNEX C as
    one file with a sheet per half, so the export can offer a whole month."""
    y, m = ym.split("-")
    first = f"{int(y):04d}-{int(m):02d}-01"
    return [first, work_arrangement_next_period(first)]
