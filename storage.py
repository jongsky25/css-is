"""
CSS-IS storage
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
import sqlite3
import uuid
import re
import difflib
from datetime import datetime, timedelta
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
        hidden_public   INTEGER NOT NULL DEFAULT 0  -- 1 = admin hid this person's scores from the public People view
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
        created_by  TEXT                         -- username of the admin/process that made it
    );

    CREATE TABLE IF NOT EXISTS app_setting (     -- small key/value store for app config
        key   TEXT PRIMARY KEY,                  -- e.g. 'backup_enabled', 'backup_freq'
        value TEXT
    );
    """)
    _add_missing_columns(conn)
    conn.commit()


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
    # admin_user.rp_id (links a login account to a directory person). The unique
    # index is created here (not in the CREATE TABLE script) so it runs only after
    # the column is guaranteed to exist, on both fresh and migrated databases.
    au_cols = {row[1] for row in conn.execute("PRAGMA table_info(admin_user)")}
    if au_cols:
        if "rp_id" not in au_cols:
            conn.execute("ALTER TABLE admin_user ADD COLUMN rp_id INTEGER REFERENCES resource_person(id)")
        if "must_change" not in au_cols:
            conn.execute("ALTER TABLE admin_user ADD COLUMN must_change INTEGER NOT NULL DEFAULT 0")
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


_EVENT_COLS = """
        SELECT e.id, e.event_token, e.title, e.event_date, e.venue, e.organizer,
               ou.name AS lead_name, e.created_by, COALESCE(e.public_share, 0),
               e.welcome_message, e.ending_message, e.modality,
               COALESCE(e.certificate_enabled, 0), e.signatory_rp_id, e.certificate_verb,
               e.event_kind, e.slug,
               COALESCE(e.raffle_enabled, 0), e.raffle_prize, e.end_date
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
            "end_date": row[19]}


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
    default). The 'localtime' qualifier makes the flip land on real local
    midnight rather than UTC midnight."""
    row = conn.execute("SELECT event_date FROM event WHERE id = ?",
                       (event_id,)).fetchone()
    if not row or not row[0]:
        return False
    done = conn.execute("SELECT date('now','localtime') > date(?)",
                        (row[0],)).fetchone()[0]
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
                 AND date('now','localtime') > date(event_date)
           ORDER BY date(event_date) DESC, id DESC""").fetchall()
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
              "archived_at "
              "FROM spot_feedback")


def _spot_row(r):
    return {"id": r[0], "created_at": r[1], "user_id": r[2], "submitter": r[3],
            "page_url": r[4], "element_selector": r[5], "region_json": r[6],
            "message": r[7], "status": r[8], "admin_note": r[9],
            "updated_at": r[10], "submitter_seen_at": r[11],
            "archived_at": r[12]}


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


def update_spot_feedback(conn, fid, *, status, admin_note):
    """Triage an entry: set its status + internal note and stamp updated_at.
    The submitter-facing phase event (with any reply) is added separately via
    add_feedback_update so the two trails stay distinct."""
    conn.execute(
        "UPDATE spot_feedback SET status=?, admin_note=?, updated_at=? WHERE id=?",
        (status, (admin_note or "").strip() or None,
         tz.now_iso(), fid))
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
    registrant (walk-in/QR/paper) — surfaced so the funnel never hides them."""
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
    return {
        "n_forms": _event_form_count(conn, event_id),
        "registered": registered, "completed": completed,
        "in_progress": in_progress, "not_started": not_started,
        "answered_any": completed + in_progress,
        "completion_rate": round(completed * 100 / registered) if registered else None,
        "unattributed": unattributed,
    }


def list_events(conn, created_by=None, lifecycles=None):
    """Events newest-first for the monitor index, each enriched with its form count,
    registration funnel (registered / completed / in progress / not started) and its
    `lifecycle` (upcoming / ongoing / concluded — see lifecycle_of).
    created_by, when given, limits the list to events a particular manager created
    (admins pass None to see all). lifecycles, when given (e.g. {'upcoming','ongoing'}),
    keeps only events in those states — the strict rule keeps the monitor list to
    activities still worth monitoring. Per-event rollups reuse
    event_registration_summary — fine at the bureau's event volume and keeps the
    'completed' rule in one place."""
    where, args = "", ()
    if created_by:
        where, args = "WHERE e.created_by = ?", (created_by,)
    today = today_local(conn)
    now = conn.execute("SELECT datetime('now','localtime')").fetchone()[0]
    rows = conn.execute(
        f"""SELECT e.id, e.event_token, e.title, e.event_date, e.venue,
                   e.organizer, e.modality, e.created_by,
                   (SELECT fi.close_at FROM event_form ef
                      JOIN form_instance fi ON fi.id = ef.form_instance_id
                      WHERE ef.event_id = e.id AND fi.survey_type = 2 LIMIT 1) AS close_at,
                   e.event_kind, e.end_date
            FROM event e
            {where}
            ORDER BY date(e.event_date) DESC, e.id DESC""",
        args).fetchall()
    out = []
    for r in rows:
        life = lifecycle_of(r[3], r[8], today, now, end_date=r[10])
        if lifecycles and life not in lifecycles:
            continue
        summ = event_registration_summary(conn, r[0])
        out.append({
            "id": r[0], "event_token": r[1], "title": r[2], "event_date": r[3],
            "end_date": r[10], "venue": r[4], "organizer": r[5], "modality": r[6] or "f2f",
            "created_by": r[7], "lifecycle": life, "event_kind": r[9] or "bureau",
            **summ,
        })
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


def list_resource_persons(conn):
    """All people who can be picked as a speaker: internal staff + external RPs.

    Returns dicts so a template can show the source. RP source per the spec is
    internal staff (directory) AND external RPs (registry) -- both live in the
    resource_person table, split by is_internal.
    """
    rows = conn.execute("""
        SELECT rp.id, rp.name, rp.is_internal, rp.org_unit_id, ou.path,
               rp.photo IS NOT NULL, rp.position, rp.designation,
               rp.focus_area, rp.email, rp.employment_type, rp.hidden_public,
               rp.honorific, rp.agency, rp.signature IS NOT NULL
        FROM resource_person rp
        LEFT JOIN org_unit ou ON ou.id = rp.org_unit_id
        ORDER BY rp.is_internal DESC, rp.name
    """).fetchall()
    return [{"id": r[0], "name": r[1], "is_internal": bool(r[2]),
             "org_unit_id": r[3], "org_path": r[4], "has_photo": bool(r[5]),
             "position": r[6], "designation": r[7], "focus_area": r[8],
             "email": r[9], "employment_type": r[10], "hidden_public": bool(r[11]),
             "honorific": r[12], "agency": r[13], "has_signature": bool(r[14])}
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
    """Full record for one person (the directory edit page)."""
    people = list_resource_persons(conn)
    return next((p for p in people if p["id"] == rp_id), None)


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
        "staff": one("SELECT COUNT(*) FROM resource_person WHERE is_internal=1"),
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
            "pending": (r[2] == "")}      # no password set yet => still invited


_ADMIN_COLS = "id, username, pw_hash, salt, role, active, must_change, rp_id, created_at, created_by"


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


def set_rp_photo(conn, rp_id, blob, mime):
    """Store (or replace) a person's profile picture as bytes inside the db."""
    conn.execute("UPDATE resource_person SET photo=?, photo_mime=? WHERE id=?",
                 (sqlite3.Binary(blob), mime, rp_id))
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
               fi.modality, fi.end_date, COALESCE(fi.encoding_locked, 0)
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
             "encoding_locked": bool(r[22])}
            for r in rows]


# "Today" is the local (Asia/Manila, UTC+8) calendar day — the same rule the
# rest of the app uses for the activity lifecycle. The 'localtime' qualifier is
# required so the day flips at real local midnight, not UTC midnight.
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
        return "ongoing" if now <= close_at else "concluded"
    # No explicit feedback deadline: a multi-day activity stays ongoing through
    # its last day (end_date); a single-day activity only on its event day.
    last = (end_date or ed)[:10]
    return "ongoing" if ed <= today <= last else "concluded"


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
              AND fi.event_date <> '' AND date(fi.event_date) > date('now','localtime')
        ORDER BY fi.event_date ASC, fi.id ASC
        LIMIT ?
    """, (limit,)).fetchall()
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
              AND date(fi.event_date) <= date('now','localtime')
              AND ( (fi.close_at IS NOT NULL AND datetime('now','localtime') <= fi.close_at)
                 OR (fi.close_at IS NULL AND date(fi.event_date) = date('now','localtime')) )
        ORDER BY fi.event_date DESC, fi.id ASC
        LIMIT ?
    """, (limit,)).fetchall()
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
              AND date(fi.event_date) <= date('now','localtime')
              AND ( (fi.close_at IS NOT NULL AND datetime('now','localtime') <= fi.close_at)
                 OR (fi.close_at IS NULL AND date(fi.event_date) = date('now','localtime')) )
        ORDER BY fi.event_date DESC, fi.id DESC
        LIMIT ?
    """, (limit,)).fetchall()
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
    Archived page. Each row also carries `fid` (the form id) and `archivable` (True
    only for a standalone form — no event — which is the only shape the per-form
    archive route accepts; bureau events archive at the event level).

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
             # bureau/outside events archive at the event level. `fid` is the form id
             # the route keys on.
             "fid": r[0], "archivable": (tok is None)}
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


def today_local(conn):
    """Today's date as 'YYYY-MM-DD' in the server's local zone (Asia/Manila),
    matching the `date('now','localtime')` boundary used for the activity
    lifecycle — so the home feeds split on the same calendar day everywhere."""
    return conn.execute("SELECT date('now','localtime')").fetchone()[0]


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
        SELECT r.id, r.submitted_at, r.remarks, fi.topic, a.name
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
    for rid, when, remarks, topic, name in rows:
        comment = (remarks or "").strip() or " · ".join(notes.get(rid, []))
        if not comment:
            continue
        pool.append({"response_id": rid, "code": claim_code(rid),
                     "name": (name or "").strip() or None,
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
"""


def load_atoms(conn, after_answer_id=None):
    """Return the atoms table in exactly the shape css_is_engine expects.

    after_answer_id: if given, load ONLY answers with id > that value
    (an incremental append). The transform is row-independent — assign_periods
    derives each row's period from its own event_date — so an incremental frame
    concatenates cleanly onto a previously built one (old + new == full)."""
    sql = _LOAD_SQL
    if after_answer_id is not None:
        # int() guard — never interpolate untrusted text into SQL.
        sql = sql + f"\n  AND a.id > {int(after_answer_id)}"
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
