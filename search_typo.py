"""Bounded spelling suggestions over caller-authorized text, never a stored index."""
import re
import unicodedata

from rapidfuzz.distance import OSA

MAX_QUERY = 128
MAX_TERMS = 8
MAX_TEXT = 16000
MAX_WORDS = 1024
MAX_CANDIDATES = 2500
MAX_CLOSE = 5


def words(value):
    normalized = unicodedata.normalize('NFKD', value.casefold())
    normalized = ''.join(c for c in normalized if not unicodedata.combining(c))
    return re.findall(r'[^\W_]+', normalized, re.UNICODE)


def eligible(query):
    if len(query) > MAX_QUERY:
        return False
    terms = words(query)
    return (0 < len(terms) <= MAX_TERMS
            and any(t.isalpha() and len(t) >= 4 for t in terms))


def exact(query, text):
    return all(t in text.lower() for t in query.lower().split())


def close_score(query, text):
    if not eligible(query) or len(text) > MAX_TEXT or exact(query, text):
        return None
    if any(any(c.isdigit() for c in term) and term not in text.lower()
           for term in query.lower().split()):
        return None
    terms, targets = words(query), set(words(text))
    if not targets or len(targets) > MAX_WORDS:
        return None
    penalty = 0
    for term in terms:
        if any(term in target for target in targets):
            continue
        # Short fragments and numbers/identifiers must match literally.
        if not term.isalpha() or len(term) < 4:
            return None
        budget = 2 if len(term) >= 9 else 1
        distance = min((OSA.distance(term, target, score_cutoff=budget)
                        for target in targets if target.isalpha() and len(target) >= 4
                        and abs(len(term)-len(target)) <= budget), default=budget+1)
        if distance > budget:
            return None
        penalty += distance / len(term)
    return penalty


def rank(query, candidates, excluded=()):
    """candidates: (row, allowed search text). No candidate data leaves this call."""
    if not eligible(query) or len(candidates) > MAX_CANDIDATES:
        return []
    denied = set(excluded)
    found = []
    for order, (row, text) in enumerate(candidates):
        if row['url'] in denied:
            continue
        score = close_score(query, text)
        if score is not None:
            found.append((score, order, row))
    found.sort(key=lambda item: (item[0], item[1]))
    out = []
    for _, _, row in found:
        if row['url'] in denied:
            continue
        denied.add(row['url'])
        out.append({**row, 'match': 'close'})
        if len(out) == MAX_CLOSE:
            break
    return out
