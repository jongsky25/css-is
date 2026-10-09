"""Office calendar importer — the pure .docx parser (docs/OFFICE_CALENDAR_PLAN.md §9, B1).

`parse(path_or_file)` reads the bureau's yearly "Calendar of Activities" Word file
and returns DRAFT entries. It never touches the database and never decides
anything final: the review screen (B2) lets a person approve, edit or skip every
draft, and name the people (B3).

What the Word file looks like (CY 2026 BLHSD):
  * one table per month: row 0 = "JANUARY 2026", row 1 = weekday names, then one row
    per week, Sunday first; a day cell = the day number on its first line, then one
    paragraph per activity;
  * who OWNS an activity is only its colour: Bureau = green, Section 1 = yellow,
    Section 2 = magenta, Section 3 = orange, Section 4 = cyan, Section 5 = blue.
    It is run-level highlight or shading, not the cell. Pastel cell tints
    (weekday/week backgrounds) mean nothing and are ignored;
  * a multi-day activity is repeated in every day cell, weekends blank;
  * times, status ("(Tentative)", "POSTPONED") and people are free text.

What `parse` does:
  1. one line per activity (wrapped lines such as "(S4: Carole)" are joined);
  2. owner from the colour, kind / modality / status / times / tags guessed from the
     words; people kept as a raw hint for the resolver;
  3. holiday lines are set aside (the `holiday` table already has them);
  4. identical activities on consecutive working days become ONE range, including
     across a weekend or a holiday and across months, and typo variants that differ
     by two characters or fewer ("Strat Plannin" / "Strat Planning") are grouped.

Everything is a guess a person can overrule, so every draft carries `warnings` and
the raw source lines it came from.
"""
from __future__ import annotations

import calendar as _cal
import colorsys
import hashlib
import re
from collections import Counter
from dataclasses import asdict, dataclass, field
from datetime import date, timedelta
from difflib import SequenceMatcher

import docx
from docx.oxml.ns import qn

OWNERS = ("bureau", "s1", "s2", "s3", "s4", "s5")
OWNER_LABELS = {"bureau": "Bureau", "s1": "Section 1", "s2": "Section 2",
                "s3": "Section 3", "s4": "Section 4", "s5": "Section 5"}

# Word highlight names that carry an owner (the legend). Anything else — white,
# red, the dark* shades — is decoration and votes for nobody.
_HIGHLIGHT_OWNER = {"green": "bureau", "yellow": "s1", "magenta": "s2",
                    "cyan": "s4", "blue": "s5"}

_MONTHS = {n.lower(): i for i, n in enumerate(_cal.month_name) if n}
_MONTHS.update({n.lower(): i for i, n in enumerate(_cal.month_abbr) if n})

W = lambda tag: qn("w:" + tag)       # noqa: E731


@dataclass
class Draft:
    title: str
    kind: str
    status: str
    start_date: str
    end_date: str | None
    start_time: str | None
    end_time: str | None
    time_note: str | None
    modality: str | None
    owner: str | None                     # one of OWNERS, or None when the colour said nothing
    tags: list[str]
    people_hint: str | None               # raw "(Malou, Fe)" / "- Sir Jong, Doc AC" text
    people_tokens: list[str]
    import_key: str
    raw: list[str] = field(default_factory=list)       # "2026-10-06: <line as written>"
    warnings: list[str] = field(default_factory=list)

    def to_dict(self):
        return asdict(self)


@dataclass
class ParseResult:
    drafts: list[Draft]
    holidays: list[dict]                  # [{"date": iso, "name": text}] — set aside, not drafts
    warnings: list[str]
    stats: dict
    unmapped_colors: dict                 # colour token -> lines using it (for the mapping screen)


# ── colour → owner ───────────────────────────────────────────────────────────

def _fill_owner(hex_fill):
    """Owner for a shading fill. Orange (saturated, hue ~36°) = Section 3; a real blue
    (hue 195–235°, clearly saturated) = Section 5; every pale tint is background."""
    try:
        r, g, b = (int(hex_fill[i:i + 2], 16) / 255 for i in (0, 2, 4))
    except (ValueError, TypeError):
        return None
    h, s, _v = colorsys.rgb_to_hsv(r, g, b)
    hue = h * 360
    if s >= 0.6 and 20 <= hue <= 45:
        return "s3"
    if s >= 0.15 and 195 <= hue <= 235:
        return "s5"
    return None


def _rpr_token(rpr):
    """('hl', 'cyan') | ('shd', 'ff9900') | None for a run/paragraph-mark rPr."""
    if rpr is None:
        return None
    hl = rpr.find(W("highlight"))
    if hl is not None and hl.get(W("val")) not in (None, "none"):
        return ("hl", hl.get(W("val")))
    shd = rpr.find(W("shd"))
    if shd is not None and shd.get(W("fill")) not in (None, "auto"):
        return ("shd", shd.get(W("fill")).lower())
    return None


def _token_owner(tok):
    if tok is None:
        return None
    kind, val = tok
    return _HIGHLIGHT_OWNER.get(val) if kind == "hl" else _fill_owner(val)


# ── lines of a cell ──────────────────────────────────────────────────────────

@dataclass
class _Line:
    text: str
    owner: str | None
    tokens: Counter


def _paragraph_lines(p):
    """Split one paragraph at line breaks; each line carries the owner its text is
    coloured with (the colour covering most of its characters), falling back to the
    paragraph mark's colour when no run is coloured."""
    out, buf, votes, toks = [], [], Counter(), Counter()

    def flush():
        text = re.sub(r"\s+", " ", "".join(buf)).strip()
        if text:
            owner = votes.most_common(1)[0][0] if votes else None
            out.append(_Line(text, owner, Counter(toks)))
        buf.clear(); votes.clear(); toks.clear()

    for r in p.iter(W("r")):
        tok = _rpr_token(r.find(W("rPr")))
        owner = _token_owner(tok)
        for node in r:
            if node.tag == W("t"):
                t = node.text or ""
                buf.append(t)
                n = len(t.strip())
                if n and owner:
                    votes[owner] += n
                if n and tok:
                    toks[tok] += n
            elif node.tag == W("tab"):
                buf.append(" ")
            elif node.tag in (W("br"), W("cr")):
                flush()
    flush()
    ppr = p.find(W("pPr"))
    mark = _token_owner(_rpr_token(ppr.find(W("rPr")) if ppr is not None else None))
    for line in out:
        if line.owner is None:
            line.owner = mark          # an uncoloured line takes the paragraph mark's colour
    return out


# ── words → fields ───────────────────────────────────────────────────────────

_LEGEND = re.compile(r"^(activity legend:?|bureau|section\s*[1-5])(\s+(bureau|section\s*[1-5]))*\s*$", re.I)
_HOLIDAY = re.compile(
    r"(holiday|new year|independence day|hero.?s day|labor day|christmas|rizal|bonifacio|"
    r"maundy|good friday|black saturday|araw ng|kagitingan|ninoy|manila day|all saints|"
    r"all soul|eid|edsa)", re.I)
_WORKY = re.compile(r"(meeting|mtg|workshop|training|orientation|consultation|monitoring|"
                    r"technical assistance|summit|conference|session|writeshop)", re.I)

_STATUS = (("postponed", re.compile(r"\bpostponed\b", re.I)),
           ("tentative", re.compile(r"\b(tentative|pending)\b", re.I)))
_ONLINE = re.compile(r"\b(online|virtual|webinar|zoom)\b", re.I)
_F2F = re.compile(r"\b(f2f|face[- ]to[- ]face)\b", re.I)

_TAGS = (("PK", r"\bPK\b"), ("BHW", r"\bBHWs?\b"), ("UUC-PHC", r"UUC-?\s?PHC"),
         ("LHS ML", r"\bLHS ML\b"), ("ZBB", r"\bZBB\b"), ("Sulu", r"\bSulu\b"),
         ("SHF", r"\bSHF\b"), ("LIPH", r"\bLIPH\b"), ("HSRP", r"\bHSRP\b"),
         ("GPH", r"\bGPH\b"), ("EBDM", r"\bEBDM\b"), ("AOP", r"\bAOP\b"),
         ("UHC", r"\bUHC\b"), ("LHSI", r"\bLHSI\b"), ("PHALGA", r"\bPHALGA\b"),
         ("SGLG", r"\bSGLG\b"), ("IQA", r"\bIQA\b"), ("DOH Rep", r"\bDOH ?Reps?\b"),
         ("LHB", r"\bLHBs?\b"), ("LGU HSC", r"\bLGU HSC\b"), ("MAIFIP", r"\bMAIFIP\b"))

_AM = {"am", "an", "a.m."}
_PM = {"pm", "p.m."}
_NOON = {"nn", "noon"}


def _kind(text, online):
    low = text.lower()
    if "moratorium" in low:
        return "banner"
    if re.search(r"^\s*due\b|\bdue:|\bdeadline\b", low):
        return "deadline"
    if re.search(r"\b(iqa|eqa|iso\b|audit|surveillance|management review|mancom|strat(egic)?\.? ?plan|"
                 r"opcr|wfp|q[1-4] mr\b)", low) or re.search(r"\bmr\b", low):
        return "audit_mr"
    if not online and re.search(
            r"technical assistance|monitoring|field (visit|testing)|data collection|"
            r"pilot (test|implementation)|validation|site visit|\bta\b", low):
        return "travel"
    if re.search(r"orientation|workshop|training|trng|writeshop|summit|conference|forum|"
                 r"convention|learning (exchange|session)|capdev|webinar|\btot\b|seminar|"
                 r"cascading|les\b", low):
        return "training"
    if re.search(r"\b(meeting|mtg|mtng|meet|huddle)\b", low):
        return "meeting"
    if re.search(r"consultation", low):
        return "training"
    return "meeting"


# --- times -------------------------------------------------------------------

_CLOCK = r"(\d{1,2})(?::(\d{2}))?\s*(a\.?m\.?|p\.?m\.?|an|nn|noon)?"
_NB = r"(?<![\d:./\-])"            # not glued to a digit/colon/dot/slash/dash before
_COMPACT = re.compile(_NB + r"(\d{1,2})(\d{2})\s*(am|pm|an)\b", re.I)           # 130pm, 1030am
_RANGE = re.compile(_NB + _CLOCK + r"\s*(?:-|–|—|\bto\b)\s*" + r"(\d{1,2})(?::(\d{2}))?\s*(a\.?m\.?|p\.?m\.?|an|nn|noon)?(?!\d)", re.I)
_SINGLE = re.compile(_NB + r"(\d{1,2})(?::(\d{2}))?\s*(a\.?m\.?|p\.?m\.?|an|nn)\b", re.I)
_DAYPART_LEAD = re.compile(r"^(am|pm)(\s*/\s*(am|pm))?\s*[:\-]\s*", re.I)
_DAYPART_TAIL = re.compile(r"\s+(am|pm)\s*$", re.I)


def _hm(h, m, ap):
    """24-hour (h, m) from a 12-hour clock + meridiem, or None when implausible."""
    h, m = int(h), int(m or 0)
    if not (1 <= h <= 12 and 0 <= m < 60):
        return None
    ap = (ap or "").lower().replace(".", "")
    if ap in _NOON or (ap == "" and h == 12):
        return (12, m) if h == 12 else None
    if ap in _AM:
        return (h % 12, m)
    if ap in _PM:
        return (h % 12 + 12, m)
    return None


def _fmt(t):
    return f"{t[0]:02d}:{t[1]:02d}"


def _bare_hm(h, m, is_end):
    """A bare hour ("9-12 Review…"): office-hours guess — 7-11 morning, 12 noon, 1-6 afternoon."""
    h, m = int(h), int(m or 0)
    if not (1 <= h <= 12 and 0 <= m < 60):
        return None
    return (h if 7 <= h <= 11 else 12 if h == 12 else h + 12, m)


def _find_time(text):
    """(start 'HH:MM'|None, end|None, time_note|None, cleaned title) for the first time
    expression in `text`. The expression is cut out of the title only when it is a
    leading "10am: …" prefix or a trailing "(1:30-3pm)" / "9AM"; one in the middle of a
    sentence stays where it is. `time_note` always keeps the words as written."""
    m = _COMPACT.search(text)
    if m:
        t = _hm(m.group(1), m.group(2), m.group(3))
        if t:
            return _fmt(t), None, m.group(0).strip(), _cut(text, m)
    m = _RANGE.search(text)
    if m:
        h1, m1, a1, h2, m2, a2 = m.groups()
        a1, a2 = (a1 or "").lower().replace(".", ""), (a2 or "").lower().replace(".", "")
        if a1 or a2 or m.start() == 0:
            if not a1 and a2:                              # "1-3pm", "11-1pm", "9-12nn"
                if a2 in _NOON:
                    a1 = "am"
                elif a2 in _PM:
                    a1 = "pm" if int(h1) % 12 <= int(h2) % 12 else "am"
                else:
                    a1 = a2
            s = _hm(h1, m1, a1) if a1 else _bare_hm(h1, m1, False)
            e = _hm(h2, m2, a2) if a2 else _bare_hm(h2, m2, True)
            if s and e and a2 == "am" and e == (0, e[1]) and s[0] < 12:
                e = (12, e[1])                      # "9-12 am" means noon, not midnight
            if s and e and s < e:
                return _fmt(s), _fmt(e), m.group(0).strip(), _cut(text, m)
    m = _SINGLE.search(text)
    if m:
        t = _hm(*m.groups())
        if t:
            return _fmt(t), None, m.group(0).strip(), _cut(text, m)
    m = _DAYPART_LEAD.match(text)
    if m:
        return None, None, m.group(1).upper(), text[m.end():].strip()
    m = _DAYPART_TAIL.search(text)
    if m:
        return None, None, m.group(1).upper(), text[:m.start()].strip()
    return None, None, None, text


def _cut(text, m):
    """Remove a matched time from the title when it is a leading prefix or a trailing
    (optionally parenthesised) suffix."""
    before, after = text[:m.start()], text[m.end():]
    if not before.strip() and re.match(r"\s*[:\-–]?\s*\S", after):
        return re.sub(r"^\s*[:\-–]\s*", "", after).strip()
    if not after.strip(" )]"):
        return re.sub(r"[\s(\[\-–:,]+$", "", before).strip()
    return text


# --- people hint ---------------------------------------------------------------

_NOT_NAMES = {"online", "am", "pm", "f2f", "tentative", "postponed", "pending", "qc", "nn",
              "virtual", "face to face", "ncr", "manila"}


def _people_hint(text):
    """The raw "who" text at the end of a line — the last parenthesised group
    "(Malou, Fe)" or a trailing " - Sir Jong, Doc AC" — plus its names split apart.
    Advisory only: it can just as well be a place ("(Palawan)"); the resolver decides
    which tokens are people, and the title keeps the words as written."""
    m = re.search(r"\(([^()]*)\)\s*$", text)
    if not m:
        m = re.search(r"\s[-–]\s*([A-Z][^()\-–]{1,60})$", text)
    if not m:
        return None, []
    hint = m.group(1).strip()
    tokens = []
    for part in re.split(r"\s*(?:,|/|&|;|\band\b)\s*", re.sub(r"\bS\d:\s*", "", hint)):
        part = part.strip(" .")
        if (part and part.lower() not in _NOT_NAMES and len(part.split()) <= 3
                and not re.search(r"\d", part) and not (part.isupper() and len(part) >= 4)):
            tokens.append(part)
    return (hint if tokens else None), tokens


# --- one line ------------------------------------------------------------------

_CONT = re.compile(r"^\s*(\(|[-–]\s|,\s|pax:)", re.I)


def _continues(prev, text):
    """Does `text` carry on the previous activity ("(S4: Carole)", "- (Pampanga)…",
    "Analyn, Jas, Wardah)")? Such lines are fragments the Word cell wrapped."""
    if not prev:
        return False
    return bool(_CONT.match(text)) or (")" in text and "(" not in text and len(text) < 60)


def _norm(text):
    return re.sub(r"\s+", " ", re.sub(r"[^a-z0-9 ]", " ", text.lower())).strip()


def _entry(text, owner):
    """Everything guessable from one activity line, as a dict."""
    status = "confirmed"
    for name, rx in _STATUS:
        if rx.search(text):
            status = name
            break
    online = bool(_ONLINE.search(text))
    modality = "online" if online else "f2f" if _F2F.search(text) else None
    start, end, note, title = _find_time(text)
    title = re.sub(r"[\[(]\s*(tentative|postponed|pending)\s*[\])]", "", title, flags=re.I)
    title = re.sub(r"^(tentative|postponed)\s*[:\-]\s*", "", title, flags=re.I)
    title = re.sub(r"[\s\-–]*\(\s*(tentative|postponed|pending)\s*$", "", title, flags=re.I)
    title = re.sub(r"\s[-–]\s*(tentative|postponed|pending)\s*$", "", title, flags=re.I)
    title = re.sub(r"\s+", " ", title).strip(" -–:,")
    hint, tokens = _people_hint(title)
    return {"title": title or text, "owner": owner, "status": status, "modality": modality,
            "start_time": start, "end_time": end, "time_note": note,
            "kind": _kind(text, online),
            "tags": [t for t, rx in _TAGS if re.search(rx, text, re.I)],
            "people_hint": hint, "people_tokens": tokens, "norm": _norm(title or text)}


def _is_noise(text):
    return (len(text) < 3 or _LEGEND.match(text) is not None or not re.search(r"[A-Za-z]", text)
            or text.strip().upper() in {"X", "N/A"})


# ── the tables ─────────────────────────────────────────────────────────────────

_DAY = re.compile(r"^\s*(?:(?P<mon>[A-Za-z]{3,9})\s+)?(?P<d>\d{1,2})(?:\s+(?P<rest>\S.*))?$")


def _month_title(table):
    text = re.sub(r"\s+", " ", table.rows[0].cells[0].text).strip()
    m = re.match(r"^([A-Za-z]+)\s+(\d{4})$", text)
    if m and m.group(1).lower() in _MONTHS:
        return _MONTHS[m.group(1).lower()], int(m.group(2))
    return None


def _day_cells(table):
    """Yield (column 0-6, [lines]) for every non-empty cell below the weekday row.
    A merged cell appears once, at its first column."""
    for row in table.rows[2:]:
        seen = set()
        for col, cell in enumerate(row.cells):
            tc = cell._tc
            if id(tc) in seen:
                continue
            seen.add(id(tc))
            lines = [ln for p in tc.findall(W("p")) for ln in _paragraph_lines(p)]
            if lines:
                yield col, lines


def _occurrences(doc, warnings, holidays, unmapped):
    """[(date, entry dict, raw line)] for every activity in every month table."""
    occ, n_tables = [], 0
    for table in doc.tables:
        month = _month_title(table)
        if not month:
            warnings.append("A table without a 'MONTH YYYY' title was skipped.")
            continue
        n_tables += 1
        mo, yr = month
        for col, lines in _day_cells(table):
            m = _DAY.match(lines[0].text)
            if not m:
                continue                       # the legend, or a stray cell: not a day
            mon, d = m.group("mon"), int(m.group("d"))
            if mon:
                if mon.lower() not in _MONTHS:
                    continue
                cm = _MONTHS[mon.lower()]
                cy = yr + (1 if (mo, cm) == (12, 1) else -1 if (mo, cm) == (1, 12) else 0)
            else:
                cm, cy = mo, yr
            try:
                day = date(cy, cm, d)
            except ValueError:
                warnings.append(f"{_cal.month_name[mo]} {yr}: '{lines[0].text[:30]}' is not a real date; skipped.")
                continue
            if (day.weekday() + 1) % 7 != col:
                warnings.append(f"{day.isoformat()} sits in the {('Sun','Mon','Tue','Wed','Thu','Fri','Sat')[col]} "
                                f"column but is a {day.strftime('%A')}.")
            rest = m.group("rest")
            body = ([_Line(rest, lines[0].owner, lines[0].tokens)] if rest else []) + lines[1:]
            prev = None
            for ln in body:
                if _is_noise(ln.text):
                    continue
                if _continues(prev, ln.text):
                    prev["raw"] += " " + ln.text
                    prev["text"] += " " + ln.text
                    prev["owner"] = prev["owner"] or ln.owner
                    prev["tokens"].update(ln.tokens)
                    continue
                prev = {"text": ln.text, "raw": ln.text, "owner": ln.owner, "tokens": Counter(ln.tokens)}
                occ.append((day, prev))
    finished = []
    for day, p in occ:
        text = re.sub(r"\s+", " ", p["text"]).strip()
        if _HOLIDAY.search(text) and len(text.split()) <= 7 and not _WORKY.search(text):
            holidays.setdefault((day.isoformat(), _norm(text)), text)
            continue
        e = _entry(text, p["owner"])
        if e["owner"] is None:
            for tok, n in p["tokens"].items():
                unmapped[f"{tok[0]}:{tok[1]}"] += 1
        finished.append((day, e, f"{day.isoformat()}: {p['raw']}"))
    return finished, n_tables


# ── merging ────────────────────────────────────────────────────────────────────

def _same_activity(a, b):
    """Equal after normalising, or — for titles of 8+ characters — within two
    characters of each other (a typo variant). A different place or topic differs by
    far more, so "(Tawi Tawi)" and "(Basilan)" never merge."""
    if a == b:
        return True
    if min(len(a), len(b)) < 8:
        return False
    sm = SequenceMatcher(None, a, b, autojunk=False)
    return max(len(a), len(b)) - sum(m.size for m in sm.get_matching_blocks()) <= 2


def _adjacent(last, day, off_days):
    """Is `day` the next working day after `last`? Days in between must all be
    weekends or non-working days."""
    if day <= last:
        return False
    d = last + timedelta(days=1)
    while d < day:
        if d.weekday() < 5 and d not in off_days:
            return False
        d += timedelta(days=1)
    return True


def _merge(items, off_days):
    """Chain occurrences into ranges. Returns [{'days': [...], 'entries': [...], 'raw': [...]}]."""
    chains = []
    for day, e, raw in sorted(items, key=lambda x: (x[0], x[1]["norm"])):
        for ch in chains:
            if (ch["days"][-1] != day and _adjacent(ch["days"][-1], day, off_days)
                    and _same_activity(ch["norm"], e["norm"])):
                ch["days"].append(day); ch["entries"].append(e); ch["raw"].append(raw)
                break
            if ch["days"][-1] == day and _same_activity(ch["norm"], e["norm"]):
                ch["raw"].append(raw)                       # the same line twice in one cell
                break
        else:
            chains.append({"days": [day], "entries": [e], "raw": [raw], "norm": e["norm"]})
    return chains


def _draft(ch):
    es = ch["entries"]
    title = Counter(e["title"] for e in es).most_common()
    best = max((t for t, n in title if n == title[0][1]), key=len)
    owners = Counter(e["owner"] for e in es if e["owner"])
    first = es[0]
    warnings = []
    if len({e["norm"] for e in es}) > 1:            # a real typo variant, not just spacing/punctuation
        warnings.append("Spelled differently on different days: " +
                        "; ".join(sorted({e["title"] for e in es})))
    if len(owners) > 1:
        warnings.append("Coloured for different owners on different days: " +
                        ", ".join(f"{OWNER_LABELS[o]}×{n}" for o, n in owners.most_common()))
    if not owners:
        warnings.append("No owner colour — choose the owning unit.")
    start, end = ch["days"][0], ch["days"][-1]
    key = hashlib.sha1(f"{start}|{end}|{_norm(best)}".encode()).hexdigest()[:16]
    return Draft(
        title=best, kind=first["kind"], status=first["status"],
        start_date=start.isoformat(), end_date=end.isoformat() if end != start else None,
        start_time=first["start_time"], end_time=first["end_time"], time_note=first["time_note"],
        modality=first["modality"], owner=owners.most_common(1)[0][0] if owners else None,
        tags=first["tags"], people_hint=first["people_hint"], people_tokens=first["people_tokens"],
        import_key="docx:" + key, raw=ch["raw"], warnings=warnings)


# ── public ─────────────────────────────────────────────────────────────────────

def parse(source):
    """Parse the Word calendar at `source` (a path or a file object)."""
    doc = docx.Document(source)
    warnings, holidays, unmapped = [], {}, Counter()
    items, n_tables = _occurrences(doc, warnings, holidays, unmapped)
    hol_days = set()
    for (iso, _n) in holidays:
        hol_days.add(date.fromisoformat(iso))
    chains = _merge(items, hol_days)
    drafts = sorted((_draft(c) for c in chains), key=lambda d: (d.start_date, d.title.lower()))
    hol = [{"date": iso, "name": name} for (iso, _n), name in sorted(holidays.items())]
    return ParseResult(
        drafts=drafts, holidays=hol, warnings=warnings, unmapped_colors=dict(unmapped),
        stats={"tables": n_tables, "lines": len(items), "drafts": len(drafts),
               "merged": len(items) - len(drafts),
               "by_owner": dict(Counter(d.owner or "none" for d in drafts)),
               "by_kind": dict(Counter(d.kind for d in drafts))})
