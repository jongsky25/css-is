"""
One-shot backfill of the ANNEX C schedule for August 16-31, 2026.

WHY THIS EXISTS, AND WHY IT IS A SCRIPT RATHER THAN A FEATURE
------------------------------------------------------------
The bureau filled in the second-half-of-August schedule on the Excel sheet it
has always used, and that sheet is the record. The app only started carrying
ANNEX C at v2.59, part-way through the month, so the period's real data lives in
a file rather than in anyone's filings.

It cannot be replayed through the normal filing path. Filing for a period closes
on the last Friday BEFORE it starts — Friday, August 14, 2026 for this one — and
storage.create_work_arrangement refuses a closed period on purpose. That refusal
is right for staff and wrong for a transcription of a form that was already
submitted and already approved on paper, so this writes approved rows directly
and records where they came from in decide_note.

FAITHFUL, NOT TIDY
------------------
The sheet is copied as it stands, including the parts that are not arrangements:

  * 42 people carry REG / CWW / WFH with the nominated weekday the Remarks cell
    names ("Friday Day off" -> CWW on Friday; "Monday WFH" -> WFH on Monday).
  * Two people have no arrangement but a stated reason — Sales ("...for approval
    from OSEC") and Bagos ("Leave"). Those are No AWA tags, scoped to this period
    so they do not leak backwards onto the first half of August.
  * One person, Orpilla, is blank with no reason given. She STAYS blank. A blank
    that nobody explained is information: it is the difference between "no
    arrangement, and here's why" and "nobody chased this", and inventing a reason
    would destroy the only signal the Admin Officer has.

SAFE TO RE-RUN, AND IT NEVER OVERWRITES A PERSON
------------------------------------------------
Guarded by an app_setting marker so boot pays one SELECT once it has run. More
importantly it is non-destructive regardless of the marker: anyone who already
holds a live arrangement (or a live No AWA tag) for this period is skipped, so a
real filing or a later admin correction always outranks this transcription.

People are matched to accounts by name. Anyone the sheet names who has no active
account is reported and skipped — they would not print on the annex anyway, since
work_arrangement_roster reads outward from admin_user.

Usage:
    python work_arrangement_backfill.py             # apply (idempotent)
    python work_arrangement_backfill.py --dry-run   # match report only, no writes
    python work_arrangement_backfill.py --verify    # what's in the DB for the period
    python work_arrangement_backfill.py --force     # apply again, ignoring the marker
"""
from __future__ import annotations

import difflib
import re
import sys

import storage as st
import tzutil as tz

PERIOD = "2026-08-16"
# Set once the backfill has run to completion. Keyed on the period so a second
# period's backfill would not silently inherit this one's "already done".
MARKER = "wa_backfill_2026_08_16"
SOURCE = "Copy of Alternative Work Arrangement.xlsx August 16_31_2026.xlsx"
DECIDE_NOTE = f"Backfilled from the submitted ANNEX C sheet ({SOURCE})."

_DAY_INDEX = {name: i for i, name in st.WORK_ARRANGEMENT_WEEKDAYS}

# The sheet, verbatim, in its own row order:
#   (no, name, position, division/unit, arrangement, weekday, no-AWA remark)
# `arrangement` None + a remark = No AWA. None + None = a blank nobody explained.
# Position and division/unit are carried for the match report only — the annex
# takes both from the directory, which is the authority on where someone sits.
ROWS = [
    (1,  "Medel Alexander R.", "Admin Officer IV", "Office of the Director", "REG", None, None),
    (2,  "Delmendo, Eric", "Admin Asst. III", "Office of the Director", "CWW", "Friday", None),
    (3,  "Enguio, Bimbo G.", "Admin Aide IV", "Office of the Director", "REG", None, None),
    (4,  "Sabello, Nora", "Admin Aide IV", "Office of the Director", "CWW", "Friday", None),
    (5,  "Villanueva, Gian Christian C.", "GIP", "Admin Unit", "CWW", "Friday", None),
    (6,  "De Guzman, Sophia Abigael D.", "GIP", "Admin Unit", "REG", None, None),
    (7,  "Flores, Kathrine Joyce D", "Medical Officer V", "HSDD", "WFH", "Tuesday", None),
    (8,  "Canares, Rustom", "Admin Asst III", "HSDD", "WFH", "Monday", None),
    (9,  "Ramos, Raile Jay", "Admin Asst III", "HSDD", "CWW", "Monday", None),
    (10, "Naig, June Rose", "Medical Officer IV", "HSDD-LHS Integration", "REG", None, None),
    (11, "Castro, Mary Anne Millscents", "SPVG", "HSDD", "WFH", "Friday", None),
    (12, "Santiago, Marifel", "SPVG", "HSDD", "WFH", "Friday", None),
    (13, "Carayag, Krisha Paula", "Sr HPO", "HSDD", "WFH", "Friday", None),
    (14, "Dimaano, Catherine", "Nurse III", "HSDD", "WFH", "Thursday", None),
    (15, "Salonga, John David", "CP III", "HSDD", "WFH", "Wednesday", None),
    (16, "Jamandri, Cheska Lian", "HPO II", "HSDD", "WFH", "Friday", None),
    (17, "Guzman, Teresita", "CHPO", "HSDD-LGU Planning & Health Financing", "WFH", "Friday", None),
    (18, "Fortaleza, Analyn", "SPVG", "HSDD", "WFH", "Friday", None),
    (19, "Javier, Roland Philip", "Sr HPO", "HSDD", "WFH", "Thursday", None),
    (20, "Mendoza, Jasmin Mae", "Sr HPO", "HSDD", "WFH", "Tuesday", None),
    (21, "Naranjo, John Vincent", "CP III", "HSDD", "CWW", "Friday", None),
    (22, "Bilao, Wardah", "HPO II", "HSDD", "WFH", "Wednesday", None),
    (23, "Bulasa, Maria Olga", "CHPO", "HSDD-Leadership and Governance for Health", "WFH", "Friday", None),
    (24, "Laurio, Catherina", "SPVG", "HSDD", "WFH", "Thursday", None),
    (25, "Barrida, Aicel", "Sr HPO", "HSDD", "WFH", "Wednesday", None),
    (26, "Reneva, Krizza Camille", "HPO II", "HSDD", "WFH", "Friday", None),
    (27, "Jurada, Maria Rhodalyn", "HPO II", "HSDD", "WFH", "Friday", None),
    (28, "Gajitos, Maria Lourdes", "Medical Officer V", "HSMED", "WFH", "Wednesday", None),
    (29, "Tibig, Arlina", "Admin Asst III", "HSMED", "WFH", "Friday", None),
    (30, "Canoy, Gilbert", "Admin Asst III", "HSMED", "WFH", "Friday", None),
    # The sheet writes "Ray Justin" here and "Ray Justine" on the first-half
    # sheet. The directory decides which is the person's name; the matcher is
    # token-based so either spelling resolves to the same account.
    (31, "Ventura, Ray Justin", "CHPO", "HSMED-Equity in Health", "WFH", "Friday", None),
    (32, "Hizon, Irene", "SPVG", "HSMED", "WFH", "Wednesday", None),
    (33, "Dulfo, Vlanche April", "Medical Officer III", "HSMED", "WFH", "Monday", None),
    (34, "Santiago, Maria Teresa", "Sr HPO", "HSMED", "WFH", "Monday", None),
    (35, "Sepe, Demi Arantxa", "Sr HPO", "HSMED", "WFH", "Thursday", None),
    (36, "Aventurado, Charlaine", "Policy & Finance Specialist", "HSMED", "WFH", "Thursday", None),
    (37, "Dela Fuente, Carole Anne", "HPO II", "HSMED", "WFH", "Thursday", None),
    (38, "Dela Cruz, Ronnel John", "HPO II", "HSMED", "WFH", "Monday", None),
    # Blank, and nobody said why. Left blank on purpose — see the module docstring.
    (39, "Orpilla, Maejorie", "HPO II", "HSMED", None, None, None),
    (40, "Lazo, Modesto", "CP III", "HSMED", "WFH", "Friday", None),
    # Transcribed as written, "requst" included: this is what was submitted.
    (41, "Sales, Miriam Cecilia", "Medical Officer IV", "HSMED-LGU Performance Monitoring",
     None, None, "With requst WFH due to medical condition, for approval from OSEC"),
    (42, "Sinson, Fe", "SPVG", "HSMED", "WFH", "Friday", None),
    (43, "Bagos, Jesel", "Sr HPO", "HSMED", None, None, "Leave"),
    (44, "Manaloto, Ronnel", "CP III", "HSMED", "WFH", "Monday", None),
    (45, "Cruz, Chariza Fe", "HPO II", "HSMED", "WFH", "Wednesday", None),
]


# ------------------------------------------------------------- matching ------

# Titles and honorifics the sheet and the directory disagree about freely.
_HON = set("dir dr mr ms mrs engr atty prof hon sir maam miss doc dra jr sr iii ii iv".split())


def _tokens(name):
    """A name reduced to comparable word tokens.

    Deliberately ORDER-FREE (a set, compared as a set): the sheet writes
    'Delmendo, Eric' and one row as 'Medel Alexander R.' — surname first, with
    and without the comma — while the directory holds 'Eric Delmendo'. Comparing
    sequences would score those as different people. Single letters go too, so a
    middle initial that only one side carries cannot break a match.
    """
    n = re.sub(r"[^a-z ]", " ", str(name or "").lower().replace("-", " "))
    return {t for t in n.split() if t not in _HON and len(t) > 1}


def _score(sheet_name, directory_name):
    """0..1 confidence that two names are the same person."""
    a, b = _tokens(sheet_name), _tokens(directory_name)
    if not a or not b:
        return 0.0
    if a == b:
        return 1.0
    # One side carrying extra given names is the common case ('Maria Olga Bulasa'
    # in the directory vs 'Bulasa, Maria Olga' plus a middle name, and so on).
    if a <= b or b <= a:
        return 0.92
    overlap = len(a & b) / len(a | b)
    fuzzy = difflib.SequenceMatcher(None, " ".join(sorted(a)),
                                    " ".join(sorted(b))).ratio()
    return max(overlap, fuzzy)


# Below this two names are different people. Above it and clear of the runner-up
# (see _MARGIN) they are the same one.
_THRESHOLD = 0.86
# A match must beat the second-best candidate by this much. Two directory names
# that both look like the sheet row mean the sheet row is ambiguous, and a
# coin-flip that assigns someone else's schedule is worse than a blank row.
# This applies to a PERFECT score too: two accounts holding the same name is a
# directory problem, and guessing which one gets the schedule does not solve it.
_MARGIN = 0.06


def _accounts(conn):
    """Accounts that could appear on the annex, with their directory name.

    The WHERE clause is deliberately the same as work_arrangement_roster's: an
    archived person (resigned, transferred out) does not print on the annex, so
    letting one match here would both file a row nobody ever sees and — worse —
    take the name away from whoever is still in that seat."""
    return conn.execute("""
        SELECT a.id, COALESCE(rp.name, a.username), ou.short_name
        FROM admin_user a
        LEFT JOIN resource_person rp ON rp.id = a.rp_id
        LEFT JOIN org_unit ou ON ou.id = rp.org_unit_id
        WHERE a.active = 1 AND rp.archived_at IS NULL
    """).fetchall()


def resolve(conn):
    """Pair every sheet row with an account, or explain why it could not be.

    Returns a list of dicts: the row's fields plus `user_id`, `matched_name`,
    `score` and `why`. Nothing is written."""
    accounts = _accounts(conn)
    out = []
    for no, name, position, unit, arrangement, weekday, remark in ROWS:
        ranked = sorted(((_score(name, dname), uid, dname)
                         for uid, dname, _sn in accounts), reverse=True)
        best = ranked[0] if ranked else (0.0, None, None)
        runner = ranked[1][0] if len(ranked) > 1 else 0.0
        rec = {"no": no, "name": name, "position": position, "unit": unit,
               "arrangement": arrangement, "weekday": weekday, "remark": remark,
               "user_id": None, "matched_name": None, "score": round(best[0], 3),
               "why": ""}
        if best[0] < _THRESHOLD:
            rec["why"] = "no account matches this name"
        elif best[0] - runner < _MARGIN:
            rec["why"] = (f"ambiguous — {best[2]!r} and {ranked[1][2]!r} both "
                          f"match; left for a human")
        else:
            rec["user_id"], rec["matched_name"] = best[1], best[2]
        out.append(rec)
    return out


# ---------------------------------------------------------------- apply ------

def _has_live_arrangement(conn, user_id):
    return conn.execute(
        "SELECT 1 FROM work_arrangement WHERE user_id=? AND period_start=? "
        "AND status IN ('pending','approved')", (user_id, PERIOD)).fetchone()


def _has_live_noawa(conn, user_id):
    return conn.execute(
        "SELECT 1 FROM work_arrangement_noawa WHERE user_id=? AND effective_to IS NULL",
        (user_id,)).fetchone()


def apply(conn, force=False, dry_run=False):
    """Write the sheet into the period. Returns a summary dict.

    Skips silently over anyone who already holds something live for the period —
    the transcription never overwrites a person's own filing or an admin's
    correction, whatever order the two happen in."""
    if not force and st.get_setting(conn, MARKER):
        return {"skipped_marker": True, "applied": 0, "noawa": 0,
                "blank": 0, "already": 0, "unmatched": []}

    now = tz.now_iso()
    summary = {"skipped_marker": False, "applied": 0, "noawa": 0, "blank": 0,
               "already": 0, "unmatched": []}
    try:
        for rec in resolve(conn):
            if rec["user_id"] is None:
                summary["unmatched"].append((rec["name"], rec["why"]))
                continue
            uid = rec["user_id"]
            if rec["arrangement"]:
                if _has_live_arrangement(conn, uid) or _has_live_noawa(conn, uid):
                    summary["already"] += 1
                    continue
                weekday = _DAY_INDEX[rec["weekday"]] if rec["weekday"] else None
                if not dry_run:
                    conn.execute(
                        "INSERT INTO work_arrangement(user_id, period_start, "
                        "arrangement, weekday, status, decided_at, decide_note, "
                        "created_at) VALUES (?,?,?,?,'approved',?,?,?)",
                        (uid, PERIOD, rec["arrangement"], weekday, now,
                         DECIDE_NOTE, now))
                summary["applied"] += 1
            elif rec["remark"]:
                if _has_live_noawa(conn, uid):
                    summary["already"] += 1
                    continue
                if not dry_run:
                    # effective_from is the PERIOD, not today's period: this tag
                    # describes the second half of August and must not reach back
                    # over a first half whose annex has already gone out.
                    conn.execute(
                        "INSERT INTO work_arrangement_noawa(user_id, remark, "
                        "effective_from, created_at) VALUES (?,?,?,?)",
                        (uid, rec["remark"], PERIOD, now))
                summary["noawa"] += 1
            else:
                # Blank with no reason — nothing to write, and that is the point.
                summary["blank"] += 1
        if not dry_run:
            conn.commit()
            st.set_setting(conn, MARKER, now)
    except Exception:
        conn.rollback()
        raise
    return summary


def run_once(conn):
    """Boot hook. Costs one SELECT once the marker is set, and never lets a bad
    backfill take the app down with it — an annex row missing is a bug, an app
    that will not start is an outage."""
    try:
        if st.get_setting(conn, MARKER):
            return None
        return apply(conn)
    except Exception as e:                                        # noqa: BLE001
        print(f"[wa-backfill] {PERIOD} backfill skipped: {e!r}", file=sys.stderr)
        return None


# ------------------------------------------------------------------ CLI ------

def _print_report(conn):
    print(f"ANNEX C {st.work_arrangement_period_label(PERIOD)} — {len(ROWS)} sheet rows\n")
    matched = 0
    for rec in resolve(conn):
        if rec["user_id"] is not None:
            matched += 1
            detail = f"-> {rec['matched_name']} ({rec['score']})"
        else:
            detail = f"!! {rec['why']}"
        arr = rec["arrangement"] or ("No AWA" if rec["remark"] else "(blank)")
        day = f" {rec['weekday']}" if rec["weekday"] else ""
        print(f"  {rec['no']:>2}. {rec['name']:<34} {arr:<7}{day:<10} {detail}")
    print(f"\n  matched {matched}/{len(ROWS)}")


def _print_verify(conn):
    rows = st.work_arrangement_export_rows(conn, PERIOD)
    filled = [r for r in rows if r["arrangement"]]
    print(f"{st.work_arrangement_period_label(PERIOD)}: {len(rows)} on the roster, "
          f"{len(filled)} with an arrangement")
    for r in rows:
        print(f"  {r['no']:>2}. {r['name']:<34} {r['arrangement'] or '-':<7} {r['remarks']}")


def main(argv):
    conn = st.connect("css_is.db")
    st.init_db(conn)
    if "--dry-run" in argv:
        _print_report(conn)
        print("\nDry run — nothing written.")
        print(apply(conn, force=True, dry_run=True))
        return
    if "--verify" in argv:
        _print_verify(conn)
        return
    summary = apply(conn, force="--force" in argv)
    if summary["skipped_marker"]:
        print(f"Already applied ({MARKER} is set). Re-run with --force to redo.")
        return
    print(f"applied={summary['applied']} noawa={summary['noawa']} "
          f"blank={summary['blank']} already-had-one={summary['already']}")
    for name, why in summary["unmatched"]:
        print(f"  unmatched: {name} — {why}")


if __name__ == "__main__":
    main(sys.argv[1:])
