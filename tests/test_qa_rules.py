"""
Unit tests for qa_rules — the pure matcher behind the deterministic FAQ layer
(no DB, no app import). Covers normalization, the "every query token must be
covered" scorer, exact vs keyword matching, the threshold cutoff, and the
enabled/empty edge cases app.py's _ai_try_rules relies on.
"""
import qa_rules as qr


def _rule(pattern, kind="navigate", target="pulse", keywords=None, enabled=True):
    return {"pattern": pattern, "kind": kind, "target_key": target,
            "keywords": keywords, "enabled": enabled}


def test_normalize_strips_punctuation_case_and_spacing():
    assert qr.normalize("  How MANY   responses?? ") == "how many responses"
    assert qr.normalize("") == ""
    assert qr.normalize(None) == ""


def test_tokens_drops_stopwords_but_keeps_content():
    assert qr.tokens("how many responses this month") == {"many", "responses", "month"}


def test_tokens_falls_back_when_all_stopwords():
    # "how do i" is all stopwords — keep them so an exact pattern can still match.
    assert qr.tokens("how do i") == {"how", "do", "i"}


def test_exact_match_wins_regardless_of_punctuation():
    rules = [_rule("open the dashboard")]
    assert qr.match("Open the dashboard!", rules) is rules[0]


def test_keyword_match_above_threshold():
    rules = [_rule("responses this month", kind="answer", target="responses_30d",
                   keywords="responses received submissions recently month")]
    # Not an exact string, but all content tokens are covered by the rule.
    hit = qr.match("responses received this month", rules)
    assert hit is not None and hit["target_key"] == "responses_30d"


def test_near_miss_below_threshold_falls_through():
    # Query introduces a content word the rule doesn't cover -> no full coverage.
    rules = [_rule("open the dashboard")]
    assert qr.match("open the finance dashboard export", rules) is None


def test_unrelated_query_returns_none():
    rules = [_rule("open the dashboard")]
    assert qr.match("archive an old activity", rules) is None


def test_disabled_rule_never_matches():
    rules = [_rule("open the dashboard", enabled=False)]
    assert qr.match("open the dashboard", rules) is None


def test_empty_query_returns_none():
    assert qr.match("", [_rule("open the dashboard")]) is None
    assert qr.match("   ??? ", [_rule("open the dashboard")]) is None


def test_most_specific_rule_wins_on_keyword_tie():
    # A tight rule (few extra tokens) should beat a sprawling one for the same
    # covered query, so a broad rule can't shadow a precise one.
    tight = _rule("trends", kind="navigate", target="trends", keywords="trends")
    broad = _rule("dashboard trends people teams reports", kind="navigate",
                  target="pulse", keywords="dashboard trends people teams reports")
    hit = qr.match("trends", [broad, tight])
    assert hit["target_key"] == "trends"
