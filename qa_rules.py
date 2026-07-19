"""
CSS-IS learned-question matcher — the deterministic FAQ layer that sits in
front of the NL router (app.py's /api/ai/route, docs/AI_INTEGRATION_PLAN.md).

Why this exists
---------------
The NL router already uses the model only as a *classifier*: it maps a
question to a short key (a destination, an AI_ANSWER_SLOTS key, or a help
section) and the answer text is always rendered server-side. So a
frequently-asked question can be answered with **no model call at all** by
storing `normalized question -> {kind, target_key}` rules and reusing the
exact same server-side render the router already does. That saves the daily
AI budget and keeps answering even when AI is turned off — see
storage.py's learned_rule table and app.py's _ai_try_rules().

This module is PURE (no DB, no FastAPI import), mirroring ui_telemetry.py, so
matching is cheap to unit-test and safe to import from both the route and the
admin page. Persistence lives in storage.py; this file only decides *whether*
a query matches a rule and *how well*.

Matching (confirmed design): exact normalized match wins outright; otherwise a
conservative keyword/token-overlap score must clear MATCH_THRESHOLD. Anything
below falls through to the model, so a near-miss never confidently serves the
wrong FAQ answer. The scorer echoes the term-coverage idea in
static/js/search.js (every query term must land somewhere) rather than any
ML — "learning" here is admins promoting mined questions into rules, not a
trained model.
"""
from __future__ import annotations
import re

# The three read-only resolution kinds a learned rule may serve. Actions stay
# model-only: they need validated arguments + a Confirm step, which a static
# rule can't supply. Kept here so both storage and the route validate against
# one list.
RULE_KINDS = ("navigate", "answer", "help")

# Precision floor for a non-exact (keyword) match. The hard gate is that EVERY
# content word of the query must appear in the rule (see score()); this floor
# then rejects matches where the query covers only a small slice of a broad,
# keyword-stuffed rule — e.g. a one-word query landing on a rule with ten
# keywords (1/10 = 0.1) shouldn't auto-answer. Tuned so a genuine multi-word
# paraphrase against a focused rule clears it while a token-scavenging broad
# rule does not. Exact-match (score 1.0) always wins and ignores this floor.
MATCH_THRESHOLD = 0.3

# Tiny, high-frequency function words carry no routing signal; dropping them
# lets "how many responses this month" and "responses this month" match the
# same rule. Deliberately small — anything domain-specific stays a real token.
_STOPWORDS = frozenset((
    "a", "an", "the", "is", "are", "am", "do", "does", "did", "to", "of", "for",
    "in", "on", "at", "and", "or", "my", "our", "me", "we", "i", "you", "it",
    "this", "that", "these", "those", "with", "how", "what", "where", "which",
    "who", "can", "could", "would", "should", "please", "show", "see", "get",
    "find", "give", "tell", "want", "need", "there", "here", "any", "some",
))

_WORD_RE = re.compile(r"[a-z0-9]+")


def normalize(q):
    """Canonical form used both as the stored `pattern` and the lookup key:
    lowercase, keep only alphanumerics-and-single-spaces, collapse runs of
    whitespace. Two questions that differ only in punctuation/casing/spacing
    normalize identically, which is what makes exact-match robust."""
    if not q:
        return ""
    return " ".join(_WORD_RE.findall(q.lower()))


def tokens(q):
    """Content-word set for the keyword scorer — normalized tokens with
    stopwords removed. Falls back to the full token set when a query is *all*
    stopwords (e.g. "how do i") so it can still exact-match a stored pattern."""
    toks = normalize(q).split()
    content = [t for t in toks if t not in _STOPWORDS]
    return set(content or toks)


def score(query_tokens, rule_tokens):
    """Match strength of a rule for a query, 0..1.

    Hard gate (precision): EVERY content word of the query must appear in the
    rule's token set (mirroring search.js's "every term must match somewhere").
    A rule that doesn't cover the whole query scores 0 — so a query with a word
    the rule never mentions can't be answered by that rule.

    Given full coverage, the score is |query| / |rule tokens|: it rewards a rule
    that wraps the query tightly (few extra tokens) over a sprawling,
    keyword-stuffed one. This is what lets a focused rule win over a broad one
    for the same query, and — with MATCH_THRESHOLD — rejects a short query that
    only scavenges a few tokens out of a very broad rule. Note a rule that piles
    on many keywords lowers its own score, so keep keywords focused; the
    canonical phrasing is always covered exactly by the exact-match path."""
    if not query_tokens or not rule_tokens:
        return 0.0
    if not query_tokens <= rule_tokens:               # every query token must be covered
        return 0.0
    return len(query_tokens) / len(rule_tokens)


def _rule_tokens(rule):
    """Content tokens a rule matches on: its normalized pattern plus any
    optional space-separated `keywords` an admin added for extra phrasings.
    Cached on the dict so repeated queries in one request don't recompute."""
    cached = rule.get("_tokens")
    if cached is not None:
        return cached
    text = (rule.get("pattern") or "")
    kw = rule.get("keywords") or ""
    toks = tokens(text + " " + kw) if kw else tokens(text)
    rule["_tokens"] = toks
    return toks


def match(query, rules):
    """Best enabled rule for `query`, or None to fall through to the model.

    `rules` is an iterable of dicts with at least `pattern` (normalized) and
    `kind`/`target_key`; an optional `keywords` string widens matching. Exact
    normalized-string equality wins immediately (score 1.0). Otherwise the
    highest keyword-coverage score that clears MATCH_THRESHOLD wins; ties break
    toward the earlier rule so seed/admin ordering is stable. Returns the rule
    dict (unmodified except for a cached `_tokens` key) or None.
    """
    norm = normalize(query)
    if not norm:
        return None
    qtokens = tokens(query)

    best = None
    best_score = 0.0
    for rule in rules:
        if rule.get("enabled") is False:
            continue
        if normalize(rule.get("pattern") or "") == norm:
            return rule                                   # exact match wins outright
        s = score(qtokens, _rule_tokens(rule))
        if s >= MATCH_THRESHOLD and s > best_score:
            best_score = s
            best = rule
    return best
