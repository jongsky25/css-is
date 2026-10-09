"""Matching the names in the Word calendar to accounts (docs/OFFICE_CALENDAR_PLAN.md §9, B3).

The Word file names people the way an office talks: "Riza", "Mae", "Doc Malou",
"Sir Jong", "Ma'am Riz", "Dir. Mar". The parser keeps those as raw hints
(`Draft.people_tokens`); this module decides who each one probably is.

THE RULE THAT MATTERS: a name is only ever SUGGESTED, and only when exactly one
person fits at the best level of match. Two people called Mae — or a first name
that is also somebody else's surname — is "ambiguous" and nothing is pre-selected;
a place ("Palawan"), an initialism ("KJF") or a word that matches nobody is
"unmatched". Nothing is written until an admin confirms every decision, and a
name left undecided stays undecided.

Match levels, best first (a lower level always beats a higher one):
  0 alias      — an admin already answered this exact name once; remembered.
                 Next to it, the NAME GUIDE (below): who the bureau itself says a calendar
                 name is ("Tek" = Teresita Guzman). It is looked up by full name, so it
                 needs no user ids and survives a re-created account.
  1 nickname   — equals someone's nickname (My profile)
  2 full name  — all the words of a multi-word name are in one person's name
  3 first name — equals the first word of someone's name
  4 other name — equals another word of someone's name (surname, middle name)
  5 prefix     — three or more letters that start someone's nickname/first name
                 ("Riz" -> Riza). Too weak to pre-select ("Mar" would pick Maria):
                 it is offered as "possible" and the admin decides.
"""
from __future__ import annotations

import re

HONORIFICS = {"sir", "doc", "dr", "dra", "maam", "mam", "madam", "engr", "atty", "dir",
              "director", "usec", "asec", "prof", "mr", "ms", "mrs", "hon"}

# THE NAME GUIDE — supplied by the bureau (2026-10-09): what each name means in the
# Word calendar. Keys are the cleaned form (`clean`): honorifics gone, lower case.
# Values are the person's full name as it is in the directory. A name that is not in
# here is matched the ordinary way (nickname / first name / ...), so people whose
# calendar name is simply their first name or nickname need no entry. Edit freely.
NAME_GUIDE = {
    "june": "June Naig", "tek": "Teresita Guzman", "malou": "Maria Lourdes Gajitos",
    "olga": "Maria Olga Bulasa", "mimi": "Irene Hizon", "mi": "Irene Hizon",
    "vlanche": "Vlanche Dulfo", "feng": "Marifel Santiago", "ronnel": "Ronnel Manaloto",
    "rj": "Ronnel John Dela Cruz", "dheng": "Catherine Dimaano",
    "mar": "Mar Wynn Bello", "mar wynn": "Mar Wynn Bello", "mwb": "Mar Wynn Bello",   # previous Director
    "carole": "Carole Dela Fuente", "analyn": "Analyn Fortaleza", "krisha": "Krisha Carayag",
    "cha": "Chariza Cruz", "riza": "Maria Teresa Santiago", "riz": "Maria Teresa Santiago",
    "modesto": "Modesto Lazo", "desten": "Modesto Lazo",               # same person, two names
    "ac": "Apple Charm Agulto", "jong": "Ray Justin Ventura",
    "mae": "Maejorie Orpilla",                                          # archived: still matched
    "mmc": "Mary Anne Milliscent Castro", "asf": "Analyn Fortaleza",    # initials
    "cath": "Cathrina Laurio",
    "kjf": "Kathrine Joyce Flores", "jap": "Juan Alfonso Perez",       # initials
    "mm": "Mary Anne Milliscent",
}
# Known not-people, from the CY 2026 file: places, regions, teams and phrases the parser picked
# up from the end of a line ("(Davao)", "- CAR", "(BLHSD IQA Team)"). Marked, never silently dropped.
# People the guide names who have no account at all (so there is nobody to attach an item to).
# Their names pre-select "skip" on the people step instead of lingering as unmatched.
NO_ACCOUNT = {"Mar Wynn Bello"}                                    # the previous Director

# The nickname each person goes by in the calendar, to prefill on their account (My profile).
# Only names that are NOT already the person's first name. The bureau's initials (KJF, JAP,
# MM, ASF) count as nicknames by default; each person can change theirs on My profile.
# One nickname per person: Mary Anne Milliscent Castro is both "MM" and "MMC" in the file,
# and "MM" is the one used most. (MWB has no account.)
NICKNAME_PREFILL = {
    "Teresita Guzman": "Tek", "Maria Lourdes Gajitos": "Malou", "Maria Olga Bulasa": "Olga",
    "Irene Hizon": "Mimi", "Marifel Santiago": "Feng", "Catherine Dimaano": "Dheng",
    "Chariza Cruz": "Cha", "Maria Teresa Santiago": "Riza", "Ronnel John Dela Cruz": "RJ",
    "Modesto Lazo": "Desten", "Apple Charm Agulto": "AC", "Ray Justin Ventura": "Jong",
    "Cathrina Laurio": "Cath", "Maejorie Orpilla": "Mae",
    "Kathrine Joyce Flores": "KJF", "Juan Alfonso Perez": "JAP",
    "Mary Anne Milliscent Castro": "MM", "Analyn Fortaleza": "ASF",
}

NOT_PEOPLE = {
    "tolosa", "cebu", "iloilo", "pampanga", "mindanao", "northern mindanao", "bicol region",
    "car", "un avenue", "who regional office", "moh barmm basilan", "moh barmm maguindanao",
    "mimaropa chd", "blhsd iqa team", "interagency twg", "doh rep", "zbb", "lha", "ta requests",
    "aop activity", "dovetail activity", "subprogram", "am for coordinators", "auditor hemb",
}
PROBABLY_NOT = set()                       # names the bureau doubts are people: offered, never chosen

LEVEL_LABELS = {0: "remembered", 1: "nickname", 2: "full name", 3: "first name",
                4: "surname / other name", 5: "starts like"}


def _words(text):
    """Lower-case words, apostrophes and dots dropped ("Ma’am" -> "maam", "Dr." -> "dr")."""
    text = (text or "").replace("’", "'").replace("`", "'").lower()
    text = re.sub(r"['.]", "", text)
    return [w for w in re.split(r"[^a-z0-9ñ]+", text) if w]


def clean(raw):
    """(key, label) for a raw token: honorifics stripped from the front ("Sir Jong" ->
    "jong"). None when nothing is left."""
    ws = _words(raw)
    while ws and ws[0] in HONORIFICS:
        ws = ws[1:]
    if not ws:
        return None
    return " ".join(ws), " ".join(w.capitalize() for w in ws)


def load_directory(conn):
    """Every account as a match candidate: [{user_id, name, nickname, words, first, inactive}].
    `inactive` = deactivated/pending, or linked to an archived directory person. Ordinary
    matching (nickname, first name...) only looks at ACTIVE people; the name guide may name
    someone who has since left (the previous Director, an archived colleague), and the
    calendar should still be able to show who an old item was for."""
    out = []
    for uid, username, rp_name, nick, active, archived in conn.execute(
            "SELECT a.id, a.username, rp.name, a.nickname, a.active, rp.archived_at FROM admin_user a "
            "LEFT JOIN resource_person rp ON rp.id = a.rp_id"):
        name = (rp_name or "").strip()
        if "," in name:                                   # "Santos, Maria" -> "Maria Santos"
            last, _, first = name.partition(",")
            name = f"{first.strip()} {last.strip()}"
        ws = [w for w in _words(name) if w not in HONORIFICS]
        out.append({"user_id": uid, "name": name or username, "nickname": " ".join(_words(nick)),
                    "words": ws, "first": ws[0] if ws else "", "nickname_raw": (nick or "").strip(),
                    "inactive": (not active) or bool(archived)})
    return out


def guide_candidates(full, directory):
    """User ids the directory has for a guide's full name: everyone whose name holds ALL
    its words, else (a directory that omits middle names) first AND last word."""
    gw = [w for w in _words(full) if w not in HONORIFICS]
    people = [p for p in directory if p["words"]]
    hit = [p for p in people if set(gw) <= set(p["words"])]
    if not hit and len(gw) > 2:
        hit = [p for p in people if {gw[0], gw[-1]} <= set(p["words"])]
    live = [p for p in hit if not p.get("inactive")]
    return [p["user_id"] for p in (live or hit)]               # an active account beats an archived namesake


def match(key, directory, aliases=None):
    """{'level', 'candidates': [user ids], 'guide': full name|None,
        'status': alias|guided|suggested|ambiguous|possible|unlikely|not_person|unmatched}.
    Only `alias`, `guided` and `suggested` are ever pre-selected (`not_person` pre-selects
    "Not a person"). A guide entry whose person has no active account is `unmatched` (several
    accounts: `ambiguous`) with `guide` set so the page can say so — it never falls back to a
    first-name guess."""
    out = _match(key, directory, aliases)
    out.setdefault("guide", None)
    return out


def _match(key, directory, aliases):
    alias = (aliases or {}).get(key)
    if alias and any(p["user_id"] == alias for p in directory):
        return {"level": 0, "candidates": [alias], "status": "alias"}
    if key in NOT_PEOPLE:
        return {"level": None, "candidates": [], "status": "not_person"}
    guide = NAME_GUIDE.get(key)
    if guide:
        found = guide_candidates(guide, directory)
        if len(found) == 1:
            return {"level": 0, "candidates": found, "status": "guided", "guide": guide}
        if not found and guide in NO_ACCOUNT:
            return {"level": None, "candidates": [], "status": "no_account", "guide": guide,
                    "guide_found": 0}
        # The bureau said who this is, so a loose first-name guess would only be noise
        # ("Mar" must not become Maria when the previous Director has no account).
        return {"level": 0 if found else None, "candidates": found, "guide": guide,
                "guide_found": len(found), "status": "ambiguous" if found else "unmatched"}
    if key in PROBABLY_NOT:
        return {"level": None, "candidates": [], "status": "unlikely"}
    return _ordinary(key, directory)


def _ordinary(key, directory):
    directory = [p for p in directory if not p.get("inactive")]     # guesses never reach someone who has left
    words = key.split()
    tiers = {1: [], 2: [], 3: [], 4: [], 5: []}
    for p in directory:
        if p["nickname"] and p["nickname"] == key:
            tiers[1].append(p["user_id"])
        elif len(words) > 1 and p["words"] and set(words) <= set(p["words"]):
            tiers[2].append(p["user_id"])
        elif len(words) == 1 and p["first"] == key:
            tiers[3].append(p["user_id"])
        elif len(words) == 1 and key in p["words"]:
            tiers[4].append(p["user_id"])
        elif (len(words) == 1 and len(key) >= 3
              and ((p["nickname"] and p["nickname"].startswith(key)) or p["first"].startswith(key))):
            tiers[5].append(p["user_id"])
    for level in (1, 2, 3, 4, 5):
        if tiers[level]:
            c = tiers[level]
            if level == 5:
                return {"level": 5, "candidates": c, "status": "possible"}
            return {"level": level, "candidates": c,
                    "status": "suggested" if len(c) == 1 else "ambiguous"}
    return {"level": None, "candidates": [], "status": "unmatched"}


_SEPARATORS = re.compile(r"\s*(?:[-–—]|℅)\s*")
_MATCHED = ("alias", "guided", "suggested", "ambiguous", "possible")


def expand(raw, directory, aliases=None):
    """Keys for one raw token. Usually one. Two cases give more:
      * "Riza Desten" becomes ["riza", "desten"] when it matches no single person as a whole
        but every word matches someone;
      * a person glued to a place, "MDN - Malou" / "SGA - Arlene" / "℅ MM CHD-Cath", is
        split at the dash: the sides that match somebody are the names, the rest (the place)
        is dropped. When no side matches anyone the whole token is kept so it still shows up
        on the list to be marked "not a person"."""
    parts = [p for p in _SEPARATORS.split(raw) if p.strip()]
    if len(parts) > 1:
        keys = []
        for part in parts:
            for k in expand(part, directory, aliases):
                if match(k, directory, aliases)["status"] in _MATCHED and k not in keys:
                    keys.append(k)
        if keys:
            return keys
    c = clean(raw)
    if not c:
        return []
    key = c[0]
    words = key.split()
    if len(words) > 1 and match(key, directory, aliases)["status"] == "unmatched":
        parts = [match(w, directory, aliases)["status"] for w in words]
        if all(s in _MATCHED for s in parts):
            return words
    return [key]


def collect(drafts, created, directory, aliases, ignored, decided):
    """Every distinct name in the imported items, with where it is used and how it matched.
    `created` is {draft index: entry id} (only imported drafts count); `decided` is the
    {key: decision} already recorded for this batch. Sorted: pending first, matched before
    unmatched, then by how often the name appears."""
    found = {}
    for i, d in enumerate(drafts):
        if i not in created:
            continue
        seen = set()
        for raw in d["people_tokens"]:
            for key in expand(raw, directory, aliases):
                if key in seen:
                    continue
                seen.add(key)
                rec = found.setdefault(key, {"key": key, "label": clean(key)[1], "raws": set(),
                                             "drafts": []})
                rec["raws"].add(raw)
                rec["drafts"].append(i)
    rows = []
    for key, rec in found.items():
        m = match(key, directory, aliases)
        rows.append({**rec, "raws": sorted(rec["raws"]), "n": len(rec["drafts"]),
                     "titles": [drafts[i]["title"] for i in rec["drafts"][:3]],
                     "match": m, "ignored": key in ignored, "decision": decided.get(key)})
    order = {"alias": 0, "guided": 0, "suggested": 1, "not_person": 2, "no_account": 2, "ambiguous": 3,
             "possible": 4, "unlikely": 5, "unmatched": 6}
    rows.sort(key=lambda r: (r["decision"] is not None, r["ignored"], order[r["match"]["status"]],
                             -r["n"], r["key"]))
    return rows


def nickname_proposals(directory):
    """One row per person in NICKNAME_PREFILL: who they are in the directory and whether
    their account can be given the nickname.
      ready         — one account, no nickname yet            (ticked)
      same          — already has exactly this nickname        (nothing to do)
      has_nickname  — already has a DIFFERENT one              (left alone unless ticked)
      ambiguous     — two accounts carry that full name        (never ticked)
      no_account    — nobody in the directory by that name
    Never writes anything; the page applies what an admin ticks."""
    rows = []
    for full, nick in NICKNAME_PREFILL.items():
        ids = guide_candidates(full, directory)
        by_id = {p["user_id"]: p for p in directory}
        row = {"full": full, "proposed": nick, "ids": ids, "person": None, "current": "", "status": "no_account"}
        if len(ids) > 1:
            row["status"] = "ambiguous"
        elif ids:
            p = by_id[ids[0]]
            row.update(person=p, current=p["nickname_raw"])
            same = " ".join(_words(p["nickname_raw"])) == " ".join(_words(nick))
            row["status"] = ("same" if same else "has_nickname" if p["nickname_raw"] else "ready")
        rows.append(row)
    order = {"ready": 0, "has_nickname": 1, "ambiguous": 2, "no_account": 3, "same": 4}
    rows.sort(key=lambda r: (order[r["status"]], r["full"].lower()))
    return rows
