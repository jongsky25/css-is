"""
name_cleanup.py — backend for the temporary "Name cleanup" admin tool.

A directory-gated UI (/directory/cleanup) for fixing the external resource-person
roster fast: proper-case ALL-CAPS names, strip leading honorifics, archive
non-people, MERGE duplicates, and SPLIT rosters (one field holding several
people) with the ratings duplicated per person.

All destructive ops reuse the proven apply_speakers machinery (merge_speaker /
copy_instance_to / delete_instance / split_roster) so a split duplicates each
session's ratings to every named individual exactly as the earlier roster passes
did. Every op is audited; the first destructive op of a server run takes one
safety backup automatically (plus a manual "restore point" button in the UI).

Safety rules baked in here, not left to the UI:
  * MERGE keeps the INTERNAL record as the survivor when exactly one side is
    internal — the official plantilla name must never be clobbered by an external
    duplicate (see the harmonize-internal-name rule).
  * Proper-case / strip-honorific never touch a name unless asked per-record;
    the bulk title-case helper only offers ALL-CAPS records (all external).
"""
from __future__ import annotations

import re
import difflib
import storage as st
import harmonize as h
import apply_speakers as aps

# ---------------------------------------------------------------------------
# Name normalisation helpers
# ---------------------------------------------------------------------------

# Canonical spelling for every honorific we recognise (lowercase key -> display).
_HON_CANON = {
    "mr": "Mr.", "mrs": "Mrs.", "ms": "Ms.", "miss": "Ms.",
    "dr": "Dr.", "dra": "Dra.", "doc": "Dr.", "doctor": "Dr.",
    "engr": "Engr.", "enr": "Engr.", "engineer": "Engr.", "eng": "Engr.",
    "atty": "Atty.", "attorney": "Atty.",
    "prof": "Prof.", "professor": "Prof.",
    "dir": "Dir.", "director": "Dir.",
    "hon": "Hon.", "honorable": "Hon.",
    "sir": "Sir", "maam": "Maam", "mam": "Maam", "maam": "Maam",
    "mons": "Mons.", "rev": "Rev.",
}
# Tokens that are honorifics for the purpose of stripping a leading prefix.
# NB: "ma" is deliberately NOT here — Filipino "Ma." abbreviates "Maria"
# (e.g. "Ma. Cynthia"); the "Ma'am" case is handled as a two-token lookahead.
_HON_KEYS = set(_HON_CANON) | {"ma'am", "maam", "mam"}

# Tokens that should stay upper-case when title-casing (initials, roman numerals,
# common post-nominal credentials).
_KEEP_UPPER = {"ii", "iii", "iv", "v", "vi", "md", "rn", "cpa", "mph",
               "dmd", "rmt", "rnd", "llb", "jd", "phd", "msw", "rsw"}
_SUFFIX_CAP = {"jr": "Jr.", "sr": "Sr."}


def _clean_token(tok):
    """Strip wrapping punctuation but remember it so we can re-attach a period."""
    return tok.strip(".,")


def title_case(name):
    """Proper-case a name: 'RAY JUSTIN VENTURA' -> 'Ray Justin Ventura',
    keeping initials ('T.'), roman numerals ('III'), credentials ('MD') and
    intra-name hyphens/apostrophes ('Bunoan-Macazo', \"O'Brien\")."""
    if not name:
        return name
    out = []
    for raw in name.split():
        bare = _clean_token(raw).lower()
        if not bare:
            out.append(raw)
            continue
        # a leading/standalone honorific -> canonical spelling
        if bare in _HON_CANON and raw.endswith((".", "")) and len(out) == 0:
            out.append(_HON_CANON[bare]); continue
        # single-letter initial like 'T' or 'T.' -> always 'T.'
        if len(bare) == 1 and bare.isalpha():
            out.append(bare.upper() + "."); continue
        if not bare.isalnum() and not re.search(r"[A-Za-z]", bare):
            out.append(raw); continue   # standalone punctuation token e.g. '-'
        if bare in _KEEP_UPPER:
            out.append(bare.upper()); continue
        if bare in _SUFFIX_CAP:
            out.append(_SUFFIX_CAP[bare]); continue
        # capitalise across hyphen and apostrophe boundaries
        word = re.sub(r"[A-Za-z]+", lambda m: m.group(0).capitalize(), raw)
        out.append(word)
    return " ".join(out)


def strip_honorific(name):
    """Drop one or more leading honorific tokens: 'Dr. Ross Rosales' ->
    'Ross Rosales', \"Ma'am Sally\" -> 'Sally'. Never strips the whole name."""
    toks = (name or "").split()
    i = 0
    while i < len(toks) - 1:
        key = re.sub(r"[^a-z']", "", toks[i].lower())
        # 'Ma' 'am' written as two tokens -> drop both
        if key == "ma" and i + 1 < len(toks) - 1 and re.sub(r"[^a-z]", "", toks[i + 1].lower()) == "am":
            i += 2
            continue
        if key in _HON_KEYS:
            i += 1
            continue
        break
    stripped = " ".join(toks[i:]).strip()
    return stripped or (name or "")


def has_honorific(name):
    toks = (name or "").split()
    if not toks:
        return False
    return re.sub(r"[^a-z']", "", toks[0].lower()) in _HON_KEYS


# Standardized honorific set offered in the directory dropdown (staff_form.html).
HONORIFIC_CHOICES = ["Mr.", "Ms.", "Mrs.", "Dr.", "Engr.", "Atty."]

# Fold every recognised honorific (canonical spelling) to one of the six standard
# values. Extras map to the closest standard per the agreed policy; titles with no
# sensible equivalent (religious / officials) map to None -> the name is left
# untouched and flagged for manual review.
_HON_TO_STD = {
    "Mr.": "Mr.", "Ms.": "Ms.", "Mrs.": "Mrs.", "Dr.": "Dr.",
    "Engr.": "Engr.", "Atty.": "Atty.",
    "Dra.": "Dr.",      # female doctor -> Dr.
    "Prof.": "Dr.",     # academic title -> Dr.
    "Sir": "Mr.",
    "Maam": "Ms.",
    "Dir.": None, "Hon.": None, "Mons.": None, "Rev.": None,  # no standard match
}


def split_honorific(name):
    """Split a leading honorific off a name and standardize it.

    Returns (standard_honorific_or_None, remaining_name, note):
      'Dr. Maria Gajitos' -> ('Dr.', 'Maria Gajitos', '')
      'Engr Ray Lazo'     -> ('Engr.', 'Ray Lazo', '')
      'Ma. Cynthia Reyes' -> (None, 'Ma. Cynthia Reyes', '')   # Ma.=Maria, not a title
      'Hon. Juan Cruz'    -> (None, 'Hon. Juan Cruz', 'unmapped:Hon.')
      'Maria Santos'      -> (None, 'Maria Santos', '')
    Never empties a name (single-token names are returned unchanged).
    """
    toks = (name or "").split()
    if len(toks) < 2:
        return None, name, ""
    # 'Ma' 'am' written as two tokens -> Ma'am -> Ms.
    first = re.sub(r"[^a-z']", "", toks[0].lower())
    if first == "ma" and len(toks) >= 3 and re.sub(r"[^a-z]", "", toks[1].lower()) == "am":
        rest = " ".join(toks[2:]).strip()
        return ("Ms.", rest, "") if rest else (None, name, "")
    if first not in _HON_KEYS:      # not a honorific (note: 'Ma.' is deliberately not a key)
        return None, name, ""
    canon = _HON_CANON.get(first) or _HON_CANON.get(first.replace("'", ""))
    std = _HON_TO_STD.get(canon)
    rest = " ".join(toks[1:]).strip()
    if not rest:
        return None, name, ""
    if std is None:
        return None, name, f"unmapped:{canon or toks[0]}"
    return std, rest, ""


def is_allcaps(name):
    letters = re.sub(r"[^A-Za-z]", "", name or "")
    return bool(letters) and letters == letters.upper() and len(letters) > 1


def is_roster(name):
    """A name field that actually holds 2+ people."""
    return len(aps.split_roster(name or "")) >= 2


# Words that carry no identity (honorifics + roster/filler noise) — dropped
# before deciding whether two names are candidate duplicates.
_STOP = set(_HON_KEYS) | {
    "and", "others", "other", "speaker", "speakers", "last", "all", "resource",
    "using", "team", "the", "of", "po", "ng", "ang", "na", "ro", "md", "rn"}


def _sig_tokens(name):
    """Identity-bearing tokens: lowercase, no punctuation, no honorifics/filler,
    no single-letter initials."""
    s = re.sub(r"[^a-z ]", " ", (name or "").lower())
    return {t for t in s.split() if len(t) > 1 and t not in _STOP}


def candidate_match(a, b):
    """Higher-recall than storage.names_match — used only to SUGGEST merges the
    user then confirms. True when one name's identity tokens are a subset of the
    other's ('Corachea' in 'Andrea Corachea'), they share 2+ tokens, or the
    sorted-token strings are a close typo match ('Buenavintura'/'Buenaventura')."""
    A, B = _sig_tokens(a), _sig_tokens(b)
    if not A or not B:
        return False
    if A <= B or B <= A:
        return True
    if len(A & B) >= 2:
        return True
    sa, sb = " ".join(sorted(A)), " ".join(sorted(B))
    return difflib.SequenceMatcher(None, sa, sb).ratio() >= 0.84


# ---------------------------------------------------------------------------
# Read model for the UI
# ---------------------------------------------------------------------------

def _feedback_counts(conn):
    return {sid: n for sid, n in conn.execute(
        """SELECT rp.id, COUNT(r.id) FROM resource_person rp
           LEFT JOIN form_instance fi ON fi.rp_id=rp.id
           LEFT JOIN response r ON r.form_instance_id=fi.id
           GROUP BY rp.id""")}


PENDING_MIN_RATINGS = 5   # below this, an external record is a bulk-archive target


def list_people(conn, external_only=False):
    """Every resource_person with the flags + suggestions the UI renders.

    Duplicate/roster matching always runs over the FULL roster (so an external
    record can still be suggested to fold into a BLHSD staff record), but with
    `external_only` the returned rows are external-only — BLHSD plantilla names
    are already clean and aren't shown for editing."""
    fb = _feedback_counts(conn)
    rows = conn.execute(
        "SELECT id, name, COALESCE(is_internal,0), COALESCE(hidden_public,0) "
        "FROM resource_person ORDER BY name COLLATE NOCASE").fetchall()
    people = [{"id": r[0], "name": r[1], "internal": bool(r[2]),
               "hidden": bool(r[3]), "n": fb.get(r[0], 0)} for r in rows]
    by_id = {p["id"]: p for p in people}

    # pass 1: per-record flags (needed before the cross-referencing pass below)
    for p in people:
        nm = p["name"]
        p["caps"] = is_allcaps(nm)
        p["honorific"] = has_honorific(nm)
        p["roster"] = is_roster(nm)
        p["proper"] = title_case(nm)
        p["stripped"] = strip_honorific(nm)

    # pass 2: duplicate candidates + roster split previews
    for p in people:
        nm = p["name"]
        # duplicate candidates (token subset / shared / typo), best-fb first
        if not p["roster"]:
            cands = [q for q in people
                     if q["id"] != p["id"] and not q["roster"]
                     and candidate_match(nm, q["name"])]
            cands.sort(key=lambda q: -q["n"])
            p["dupes"] = [{"id": q["id"], "name": q["name"], "n": q["n"],
                           "internal": q["internal"]} for q in cands[:8]]
        else:
            p["dupes"] = []
        # roster split preview: resolve each named individual to a best match
        if p["roster"]:
            parts = []
            for nmpart in aps.split_roster(nm):
                match = None
                best = -1
                for q in people:
                    if q["id"] == p["id"] or q["roster"]:
                        continue
                    if candidate_match(nmpart, q["name"]) and q["n"] > best:
                        match, best = q, q["n"]
                parts.append({"name": nmpart,
                              "match_id": match["id"] if match else None,
                              "match_name": match["name"] if match else None})
            p["parts"] = parts
        else:
            p["parts"] = []

    # pass 3: derived "needs action" status. A record is still pending if it has
    # a real quality issue (ALL-CAPS, a roster, or a duplicate candidate) or too
    # few ratings to keep. Clean records with enough ratings drop off the default
    # view; handled records (merged/archived) are already gone or hidden.
    for p in people:
        p["low"] = p["n"] < PENDING_MIN_RATINGS
        p["pending"] = (not p["hidden"]) and (
            p["caps"] or p["roster"] or bool(p["dupes"]) or p["low"])

    if external_only:
        return [p for p in people if not p["internal"]]
    return people


def people_options(conn):
    """(id, name) for every person, for merge/split target pickers."""
    return conn.execute(
        "SELECT id, name FROM resource_person ORDER BY name COLLATE NOCASE").fetchall()


# ---------------------------------------------------------------------------
# Operations (each returns a short human summary string)
# ---------------------------------------------------------------------------

def _name(conn, rid):
    r = conn.execute("SELECT name FROM resource_person WHERE id=?", (rid,)).fetchone()
    return r[0] if r else None


def rename(conn, rid, new_name):
    old = _name(conn, rid)
    new_name = (new_name or "").strip()
    if old is None or not new_name or new_name == old:
        return None
    conn.execute("UPDATE resource_person SET name=? WHERE id=?", (new_name, rid))
    return f"Renamed #{rid} {old!r} -> {new_name!r}"


def archive_low_rating(conn, threshold=PENDING_MIN_RATINGS):
    """Archive every visible EXTERNAL record with fewer than `threshold` ratings
    (hide it + archive its forms). Returns the list of (id, name, n) archived.
    Internal/BLHSD staff and already-hidden records are left untouched."""
    fb = _feedback_counts(conn)
    rows = conn.execute(
        "SELECT id, name FROM resource_person "
        "WHERE COALESCE(is_internal,0)=0 AND COALESCE(hidden_public,0)=0").fetchall()
    done = []
    for rid, nm in rows:
        n = fb.get(rid, 0)
        if n < threshold:
            conn.execute("UPDATE resource_person SET hidden_public=1 WHERE id=?", (rid,))
            conn.execute("UPDATE form_instance SET archived=1 WHERE rp_id=?", (rid,))
            done.append((rid, nm, n))
    return done


def set_hidden(conn, rid, hidden):
    old = _name(conn, rid)
    if old is None:
        return None
    conn.execute("UPDATE resource_person SET hidden_public=? WHERE id=?",
                 (1 if hidden else 0, rid))
    if hidden:
        cur = conn.execute("UPDATE form_instance SET archived=1 WHERE rp_id=?", (rid,))
        return f"Archived #{rid} {old!r} (hidden; {cur.rowcount} form(s) archived)"
    conn.execute("UPDATE form_instance SET archived=0 WHERE rp_id=?", (rid,))
    return f"Un-archived #{rid} {old!r} (visible again)"


def merge(conn, src, dst):
    """Fold src into dst. If exactly one side is internal, the internal record is
    forced to be the survivor (its plantilla name is authoritative)."""
    if src == dst:
        return None
    s = conn.execute("SELECT name, COALESCE(is_internal,0) FROM resource_person WHERE id=?", (src,)).fetchone()
    d = conn.execute("SELECT name, COALESCE(is_internal,0) FROM resource_person WHERE id=?", (dst,)).fetchone()
    if s is None or d is None:
        return None
    src_name, src_int = s[0], int(s[1] or 0)
    dst_name, dst_int = d[0], int(d[1] or 0)
    # If exactly one side is internal, the official plantilla record must survive.
    # merge_speaker always keeps `dst`, so swap the pair when the internal record
    # is on the `src` side (see the harmonize-internal-name rule).
    swapped = False
    if src_int and not dst_int:
        src, dst = dst, src
        src_name, dst_name = dst_name, src_name
        src_int, dst_int = dst_int, src_int
        swapped = True
    n = conn.execute("SELECT COUNT(*) FROM form_instance WHERE rp_id=?", (src,)).fetchone()[0]
    aps.merge_speaker(conn, src, dst)
    note = " [kept internal record as survivor]" if swapped else ""
    return (f"Merged #{src} {src_name!r} into #{dst} {dst_name!r} "
            f"({n} form(s) moved){note}")


def split(conn, rid, assignments):
    """Split a roster record (one field holding several people) into individuals,
    duplicating every one of the roster's sessions to each assigned person — the
    same machinery the earlier roster passes used (copy_instance_to per person,
    then delete the originals and the roster record).

    `assignments` is a list of {"name": <str>, "target": <id|"new">} dicts: an
    existing person id folds the sessions into that record, while "new" (or a
    blank/unknown target) resolves the name against the roster — reusing a close
    match or creating a fresh external record. Returns a short human summary."""
    nm = _name(conn, rid)
    if nm is None or not assignments:
        return None
    fb = _feedback_counts(conn)
    targets = []
    created = 0
    for a in assignments:
        pname = (a.get("name") or "").strip()
        if not pname:
            continue
        tgt = a.get("target", "new")
        pid = None
        if tgt not in (None, "", "new") and str(tgt).isdigit():
            cand = int(tgt)
            if cand != rid and conn.execute(
                    "SELECT 1 FROM resource_person WHERE id=?", (cand,)).fetchone():
                pid = cand
        if pid is None:
            pid, isnew = aps.resolve_or_create(conn, pname, fb)
            created += 1 if isnew else 0
        if pid != rid and pid not in targets:
            targets.append(pid)
    if not targets:
        return None
    fis = [r[0] for r in conn.execute(
        "SELECT id FROM form_instance WHERE rp_id=?", (rid,)).fetchall()]
    for fi in fis:
        for pid in targets:
            aps.copy_instance_to(conn, fi, pid)
        aps.delete_instance(conn, fi)
    conn.execute("DELETE FROM resource_person WHERE id=?", (rid,))
    return (f"Split #{rid} {nm!r} into {len(targets)} person(s) "
            f"({created} new); {len(fis)} session(s) duplicated to each")
