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
  0 alias      — an admin already answered this exact name once; remembered
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
    """Active accounts as match candidates: [{user_id, name, nickname, words, first}]."""
    out = []
    for uid, username, rp_name, nick in conn.execute(
            "SELECT a.id, a.username, rp.name, a.nickname FROM admin_user a "
            "LEFT JOIN resource_person rp ON rp.id = a.rp_id "
            "WHERE a.active = 1 AND (rp.id IS NULL OR rp.archived_at IS NULL)"):
        name = (rp_name or "").strip()
        if "," in name:                                   # "Santos, Maria" -> "Maria Santos"
            last, _, first = name.partition(",")
            name = f"{first.strip()} {last.strip()}"
        ws = [w for w in _words(name) if w not in HONORIFICS]
        out.append({"user_id": uid, "name": name or username, "nickname": " ".join(_words(nick)),
                    "words": ws, "first": ws[0] if ws else ""})
    return out


def match(key, directory, aliases=None):
    """{'level', 'candidates': [user ids], 'status': alias|suggested|ambiguous|possible|unmatched}.
    Only `alias` and `suggested` are ever pre-selected."""
    alias = (aliases or {}).get(key)
    if alias and any(p["user_id"] == alias for p in directory):
        return {"level": 0, "candidates": [alias], "status": "alias"}
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


def expand(raw, directory, aliases=None):
    """Keys for one raw token. Usually one; "Riza Desten" becomes ["riza", "desten"]
    when it matches no single person as a whole but every word matches someone."""
    c = clean(raw)
    if not c:
        return []
    key = c[0]
    words = key.split()
    if len(words) > 1 and match(key, directory, aliases)["status"] == "unmatched":
        parts = [match(w, directory, aliases)["status"] for w in words]
        if all(s != "unmatched" for s in parts):
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
    order = {"alias": 0, "suggested": 1, "ambiguous": 2, "possible": 3, "unmatched": 4}
    rows.sort(key=lambda r: (r["decision"] is not None, r["ignored"], order[r["match"]["status"]],
                             -r["n"], r["key"]))
    return rows
