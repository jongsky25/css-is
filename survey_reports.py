"""Shared CSM date/scoring rules and permission-checked aggregate projections."""
from datetime import date, timedelta
import calendar
import os
from urllib.parse import urlencode

import auth
import storage as st
import css_is_engine as eng
import documents_permissions as permissions
import tzutil as tz

ARTA_TEXT = {
    "SQD0": "I am satisfied with the service that I availed.",
    "SQD1": "I spent a reasonable amount of time for my transaction.",
    "SQD2": "The office followed the transaction's requirements and steps based on the information provided.",
    "SQD3": "The steps (including payment) I needed to do for my transaction were easy and simple.",
    "SQD4": "I easily found information about my transaction from the office or its website.",
    "SQD5": "I paid a reasonable amount of fees for my transaction.",
    # SQD6-SQD8 are the official ARTA CSM sentences word for word (MC 2022-05 as amended by 2023-05).
    "SQD6": "I feel the office was fair to everyone, or \u201cwalang palakasan\u201d, during my transaction.",
    "SQD7": "I was treated courteously by the staff, and (if asked for help) the staff was helpful.",
    "SQD8": "I got what I needed from the government office, or (if denied) denial of request was sufficiently explained to me.",
}

def csm_response_filter(date_from=None, date_to=None):
    """One active-row boundary for ARTA screen, extracts and comment drill-down."""
    where = f"WHERE fi.survey_type = 1 AND {st.WALKIN_FORM_ACTIVE_SQL} AND r.archived_at IS NULL"
    args = []
    if date_from:
        where += " AND r.submitted_at >= ?"
        args.append(date_from)
    if date_to:
        last = date.fromisoformat(date_to)
        # An exclusive next-date bound accepts both stored timestamp separators
        # and every fractional second while retaining the timestamp index.
        upper = (last + timedelta(days=1)).isoformat() if last < date.max else date_to + "\uffff"
        where += " AND r.submitted_at < ?"
        args.append(upper)
    return where, args

def arta_sqd_official(rows):
    """Per-item SQD0-8 distribution + top-box score + band; plus the pooled
    overall top-box over SQD1-8 (matches eng.arta_topbox)."""
    out = []
    pooled_top = pooled_n = 0
    for it in ["SQD0"] + list(eng.ARTA_HEADLINE_ITEMS):
        dist = {5: 0, 4: 0, 3: 0, 2: 0, 1: 0}
        na = 0
        for r in rows:
            raw = r.get(it, "")
            if raw in ("", None):
                continue
            try:
                v = int(round(float(raw)))
            except (ValueError, TypeError):
                continue
            if v == 0:          # N/A is stored as 0 in the row
                na += 1
            elif 1 <= v <= 5:
                dist[v] += 1
        n = dist[5] + dist[4] + dist[3] + dist[2] + dist[1]
        top, mid, bot = dist[5] + dist[4], dist[3], dist[2] + dist[1]
        score = (top / n * 100) if n else None
        out.append({
            "item": it, "text": ARTA_TEXT.get(it, it), "n": n, "na": na,
            "dist": {"SA": dist[5], "A": dist[4], "Neither": dist[3], "D": dist[2], "SD": dist[1]},
            "top": top, "mid": mid, "bot": bot,
            "score": round(score, 1) if score is not None else None,
            "band": eng.band(score, eng.ARTA_BANDS) if score is not None else None,
        })
        if it in eng.ARTA_HEADLINE_ITEMS and n:
            pooled_top += top
            pooled_n += n
    overall = (pooled_top / pooled_n * 100) if pooled_n else None
    return out, overall, pooled_n

MAX_RESPONSES = 5000
MIN_SAMPLE = 10


def csm_summary(conn, user, origin, year, month):
    user = permissions.actor(conn, user)
    if not auth.can(user['role'], 'view'):
        raise permissions.Denied('Report unavailable.')
    if type(year) is not int or not 1900 <= year <= 9998 or type(month) is not int or not 1 <= month <= 12:
        raise ValueError('Choose a valid year and month (1 to 12).')
    start = date(year, month, 1).isoformat()
    end = date(year, month, calendar.monthrange(year, month)[1]).isoformat()
    result = {'survey_type': 1, 'scope': 'bureau', 'date_basis': 'submission_date',
              'start_date': start, 'end_date': end, 'as_of': tz.now_iso(),
              'web_url': origin + '/reports?' + urlencode({'type': 1, 'date_from': start, 'date_to': end}),
              'scoring': 'Percent of valid SQD1–SQD8 answers rated 4 or 5; SQD0 excluded. N/A excluded.',
              'minimum_sample': MIN_SAMPLE}
    if os.environ.get('CSS_MCP_CSM_ENABLED') != '1':
        return dict(result, availability='not_available')
    where, args = csm_response_filter(start, end)
    selected = conn.execute('SELECT r.id FROM response r JOIN form_instance fi ON fi.id=r.form_instance_id '
                            + where + ' ORDER BY r.id LIMIT ?', (*args, MAX_RESPONSES + 1)).fetchall()
    if len(selected) > MAX_RESPONSES:
        return dict(result, availability='not_available', reason='capacity_limit',
                    note='Monthly report exceeds the connected-tool limit. Open the source report; no partial score is returned.')
    ids = [r[0] for r in selected]
    data = {rid: {} for rid in ids}
    for offset in range(0, len(ids), 500):
        batch = ids[offset:offset + 500]
        placeholders = ','.join('?' for _ in batch)
        for rid, item, value, is_na in conn.execute(
                'SELECT response_id,item_id,value,is_na FROM answer WHERE response_id IN (' + placeholders + ')'
                + " AND item_id IN ('SQD0','SQD1','SQD2','SQD3','SQD4','SQD5','SQD6','SQD7','SQD8')", batch):
            data[rid][item] = 0 if is_na else value
    items, overall, pooled_n = arta_sqd_official(list(data.values()))
    result.update(availability='available', submissions=len(ids), valid_item_answers=pooled_n)
    if not ids:
        return dict(result, state='no_matching_responses')
    if pooled_n == 0:
        return dict(result, state='no_valid_ratings')
    # No overlapping/ad-hoc filters in this first release. Suppress the whole
    # score projection when any populated item has fewer than ten respondents;
    # the overall must not reveal a withheld item's numerator by subtraction.
    if len(ids) < MIN_SAMPLE or any(0 < i['n'] < MIN_SAMPLE for i in items):
        return dict(result, state='insufficient_sample')
    return dict(result, state='rated', overall_percent=round(overall, 1),
                items=[{'item': i['item'], 'valid_answers': i['n'], 'na_answers': i['na'],
                        'positive_answers': i['top'], 'percent': i['score']} for i in items])

