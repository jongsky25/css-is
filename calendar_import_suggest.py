"""Suggestions for the calendar import review (docs/CALENDAR_UX_PLAN.md, P0.2).

Pure functions over the draft dicts of an import batch. They only ever *suggest*: the review
screen shows a suggestion next to the field a person still has to confirm, and nothing here
writes an owner or a series on its own.

  * `suggest_owners(drafts)`  for drafts the colour gave no owner: a "Section 3" / "S4:" in the
    line, or a tag that one unit owns almost entirely elsewhere in the same file;
  * `suggest_series(drafts)`  for same-title drafts that a repeat rule reproduces EXACTLY (every
    date, none extra): a rule that would invent an occurrence is never suggested.
"""
from __future__ import annotations

import re
from collections import Counter, defaultdict
from datetime import date

import calendar_import as ci
import recurrence

_SECTION = re.compile(r"\b(?:section|sec|s)\s*\.?\s*([1-5])\b(?!\s*\d)", re.I)
MIN_TAG_OWNED = 3          # a tag must be owned by at least this many other drafts ...
MIN_TAG_SHARE = 0.8        # ... and this share of them to count as that unit's


def _is_owned(d):
    return bool(d.get("owner"))


def suggest_owners(drafts):
    """{index: {"owner": key, "why": sentence}} for each unowned draft that has a signal."""
    by_tag = defaultdict(Counter)
    for d in drafts:
        if _is_owned(d):
            for t in d.get("tags") or []:
                by_tag[t][d["owner"]] += 1
    out = {}
    for i, d in enumerate(drafts):
        if _is_owned(d):
            continue
        text = " ".join(filter(None, [d.get("title"), d.get("people_hint")]))
        sections = {f"s{n}" for n in _SECTION.findall(text)}
        if len(sections) == 1:
            key = sections.pop()
            out[i] = {"owner": key, "why": f"The line mentions {ci.OWNER_LABELS[key]}."}
            continue
        votes = Counter()
        for t in d.get("tags") or []:
            c = by_tag.get(t)
            if c and sum(c.values()) >= MIN_TAG_OWNED:
                owner, n = c.most_common(1)[0]
                if n / sum(c.values()) >= MIN_TAG_SHARE:
                    votes[owner] += 1
        if len(votes) == 1:
            key = next(iter(votes))
            out[i] = {"owner": key, "why": f"{ci.OWNER_LABELS[key]} owns almost every other '{d['tags'][0]}' item in this file."}
    return out


def suggest_series(drafts):
    """[{"title", "repeat", "rrule", "dates", "indexes"}] — same-title single-day drafts whose
    dates a recurrence rule reproduces exactly."""
    groups = defaultdict(list)
    for i, d in enumerate(drafts):
        if not d.get("end_date"):
            groups[(ci._norm(d["title"]), d.get("owner"), d.get("kind"))].append(i)
    out = []
    for (_norm, _o, _k), idx in groups.items():
        if len(idx) < 3:
            continue
        idx.sort(key=lambda i: drafts[i]["start_date"])
        dates = [date.fromisoformat(drafts[i]["start_date"]) for i in idx]
        if len(set(dates)) != len(dates):
            continue
        first, last = dates[0], dates[-1]
        for repeat in ("weekdays", "weekly", "biweekly", "monthly_date", "monthly_nth"):
            try:
                rule = recurrence.build(repeat, first, last)
            except ValueError:
                continue
            if rule and recurrence._expand(rule, first, first, last) == dates:
                out.append({"title": drafts[idx[0]]["title"], "repeat": repeat, "rrule": rule,
                            "dates": [d.isoformat() for d in dates], "indexes": idx})
                break
    return out
