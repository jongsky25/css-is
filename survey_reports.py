"""Shared survey scoring rules and permission-checked aggregate projections."""
from datetime import date, timedelta
import calendar
import dashboard_insights as di
import os
import pandas as pd
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
MAX_CSM_TREND_ANSWERS = 100000


def csm_summary(conn, user, origin, year, month):
    return _csm_summary(conn, user, origin, year, month)


def compare_csm_months(conn, user, origin, year, month):
    """Two fixed submission months; caller owns the authorization snapshot."""
    user = permissions.actor(conn, user)
    if not auth.can(user['role'], 'view'):
        raise permissions.Denied('Report unavailable.')
    if (type(year) is not int or not 1900 <= year <= 9998
            or type(month) is not int or not 1 <= month <= 12
            or (year == 1900 and month == 1)):
        raise ValueError('Choose a valid month after January 1900, through December 9998.')
    if os.environ.get('CSS_MCP_CSM_TRENDS_ENABLED') != '1':
        return {'availability': 'not_available'}
    previous_year, previous_month = (year, month-1) if month > 1 else (year-1, 12)
    previous = _csm_summary(conn, user, origin, previous_year, previous_month,
                            enabled_flag='CSS_MCP_CSM_TRENDS_ENABLED', max_answers=MAX_CSM_TREND_ANSWERS)
    current = _csm_summary(conn, user, origin, year, month,
                           enabled_flag='CSS_MCP_CSM_TRENDS_ENABLED', max_answers=MAX_CSM_TREND_ANSWERS)
    result = {'as_of': tz.now_iso(), 'survey_type': 1,
              'comparison_basis': 'Selected submission month versus immediately preceding calendar month; bureau-wide ARTA CSM.',
              'delta_basis': 'Current minus previous published percentages, rounded to one decimal, in percentage points; not percent growth.',
              'scoring': 'Official pooled positive SQD1–SQD8 valid answers; SQD0 excluded from overall. Each SQD item uses its own valid-answer denominator.',
              'note': 'Monthly submissions may involve different services and respondents. Counts are not unique people. No causal or statistical-significance claim.'}
    if any(p.get('state') != 'rated' for p in (previous, current)):
        allowed = {'availability', 'reason', 'state', 'web_url', 'start_date', 'end_date',
                   'submissions', 'valid_item_answers', 'minimum_sample', 'scope', 'date_basis'}
        return dict(result, availability='not_available' if any(
            p.get('availability') != 'available' for p in (previous, current)) else 'available',
                    comparison_state='not_comparable',
                    previous={k:v for k,v in previous.items() if k in allowed},
                    current={k:v for k,v in current.items() if k in allowed})

    def delta(before, after):
        return round(after-before, 1) if before is not None and after is not None else None

    prior_items = {i['item']:i['percent'] for i in previous['items']}
    return dict(result, availability='available', comparison_state='comparable',
                previous=previous, current=current,
                changes={'overall_percentage_points': delta(previous['overall_percent'], current['overall_percent']),
                         'items': [{'item':i['item'], 'percentage_points':delta(prior_items.get(i['item']), i['percent'])}
                                   for i in current['items']]})


def _csm_summary(conn, user, origin, year, month, enabled_flag='CSS_MCP_CSM_ENABLED', max_answers=None):
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
    if os.environ.get(enabled_flag) != '1':
        return dict(result, availability='not_available')
    where, args = csm_response_filter(start, end)
    selected = conn.execute('SELECT r.id FROM response r JOIN form_instance fi ON fi.id=r.form_instance_id '
                            + where + ' ORDER BY r.id LIMIT ?', (*args, MAX_RESPONSES + 1)).fetchall()
    if len(selected) > MAX_RESPONSES:
        return dict(result, availability='not_available', reason='capacity_limit',
                    note='Monthly report exceeds the connected-tool limit. Open the source report; no partial score is returned.')
    ids = [r[0] for r in selected]
    data = {rid: {} for rid in ids}
    answer_count = 0
    for offset in range(0, len(ids), 500):
        batch = ids[offset:offset + 500]
        placeholders = ','.join('?' for _ in batch)
        query = ('SELECT response_id,item_id,value,is_na FROM answer WHERE response_id IN (' + placeholders + ')'
                 + " AND item_id IN ('SQD0','SQD1','SQD2','SQD3','SQD4','SQD5','SQD6','SQD7','SQD8')")
        args = list(batch)
        if max_answers is not None:
            query += ' LIMIT ?'
            args.append(max_answers + 1 - answer_count)
        rows = conn.execute(query, args).fetchall()
        answer_count += len(rows)
        if max_answers is not None and answer_count > max_answers:
            return dict(result, availability='not_available', reason='capacity_limit')
        for rid, item, value, is_na in rows:
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



def metric_view(m, kind="mean", bands=None):
    """Flatten an engine Metric into template-friendly fields (no logic here —
    just formatting + the band lookup the engine already defines)."""
    if m is None:
        return {"has": False, "shown": "—", "n": 0, "denom": "", "flags": [],
                "band": None, "value": None}
    if m.value is None:
        shown = "—"
    elif kind == "pct":
        shown = f"{m.value:.1f}%"
    else:
        shown = f'{m.value:.2f}'
    return {"has": m.value is not None, "shown": shown, "n": m.n, "denom": m.denom,
            "flags": list(m.flags), "value": m.value,
            "band": eng.band(m.value, bands) if bands else None}

def servqual_block(df, dim_map):
    """Type 2 / Type 3 SERVQUAL summary for one atom slice."""
    overall = eng.overall_perception(df, dim_map)
    expc = eng.expectation_A(df)
    osq = eng.osq_C(df)
    dims = [dict(dim=dim, members=", ".join(items), **metric_view(eng.dimension_mean(df, items)))
            for dim, items in dim_map.items()]
    gap = None
    if overall.value is not None and expc.value is not None:
        g = overall.value - expc.value
        gap = {"shown": f'{g:+.2f}', "label": eng.gap_label(g)}
    return {
        "answer_quality": eng.answer_quality(df)[2],
        "overall": metric_view(overall), "expectation": metric_view(expc),
        "osq": metric_view(osq, bands=eng.OSQ_BANDS), "dimensions": dims, "gap": gap,
        "respondents": int(df["response_id"].nunique()) if not df.empty else 0,
        "has_data": overall.value is not None,
    }

MAX_ACTIVITY_ANSWERS = 100000


def activity_summary(conn, user, origin, year, quarter):
    return _activity_summary(conn, user, origin, year, quarter)


def _survey_unit(conn, user, unit_id):
    user = permissions.actor(conn, user)
    if not auth.can(user['role'], 'view'):
        raise permissions.Denied('Report unavailable.')
    if type(unit_id) is not int or not 1 <= unit_id <= 9223372036854775807:
        raise ValueError('Choose a positive unit ID from unit discovery.')
    unit = conn.execute('SELECT id,name,path FROM org_unit WHERE id=?', (unit_id,)).fetchone()
    if not unit or not unit[2]:
        raise permissions.Denied('Unit not found or unavailable.')
    return unit


def unit_activity_summary(conn, user, origin, unit_id, year, quarter):
    unit = _survey_unit(conn, user, unit_id)
    return _activity_summary(conn, user, origin, year, quarter, unit=unit)


def compare_unit_activity_surveys(conn, user, origin, unit_id, year, quarter):
    """Two disjoint fixed quarters, selected in the caller's authorization snapshot."""
    unit = _survey_unit(conn, user, unit_id)
    if (type(year) is not int or not 1900 <= year <= 9998
            or type(quarter) is not int or not 1 <= quarter <= 4
            or (year == 1900 and quarter == 1)):
        raise ValueError('Choose a valid quarter after 1900 Q1, through year 9998.')
    if os.environ.get('CSS_MCP_UNIT_TRENDS_ENABLED') != '1':
        return {'availability': 'not_available'}
    previous_year, previous_quarter = (year, quarter-1) if quarter > 1 else (year-1, 4)
    previous = _activity_summary(conn, user, origin, previous_year, previous_quarter,
                                 unit=unit, enabled_flag='CSS_MCP_UNIT_TRENDS_ENABLED')
    current = _activity_summary(conn, user, origin, year, quarter,
                                unit=unit, enabled_flag='CSS_MCP_UNIT_TRENDS_ENABLED')
    result = {'as_of': tz.now_iso(), 'survey_type': 2,
              'comparison_basis': 'Selected quarter versus immediately preceding calendar quarter; current unit membership in both periods.',
              'delta_basis': 'Current minus previous, in original scale points, not percent change. A/B: 1–7; C: 1–4.',
              'note': 'Response counts are not unique people across activities. Changes may reflect different activities, samples or current unit assignment; no causal or statistical-significance claim.'}
    if any(p.get('state') != 'rated' for p in (previous, current)):
        # Never leak a valid period's scores through a partially withheld comparison.
        allowed = {'availability', 'reason', 'state', 'web_url', 'start_date', 'end_date',
                   'submissions', 'report_submissions', 'rated_respondents', 'minimum_sample',
                   'unit_id', 'unit_name', 'unit_path', 'scope', 'date_basis'}
        return dict(result, availability='not_available' if any(
            p.get('availability') != 'available' for p in (previous,current)) else 'available',
                    comparison_state='not_comparable',
                    previous={k:v for k,v in previous.items() if k in allowed},
                    current={k:v for k,v in current.items() if k in allowed})

    def delta(before, after):
        return after-before if before is not None and after is not None else None

    previous_dims = {d['dimension']:d['mean'] for d in previous['dimensions']}
    changes = {k:delta(previous[k], current[k]) for k in
               ('overall_mean', 'expectation_mean', 'osq_mean', 'gap')}
    changes['dimensions'] = [{'dimension':d['dimension'],
                              'mean_change':delta(previous_dims.get(d['dimension']), d['mean'])}
                             for d in current['dimensions']]
    return dict(result, availability='available', comparison_state='comparable',
                previous=previous, current=current, changes=changes)


def find_survey_units(conn, user, query='', limit=10, offset=0):
    user = permissions.actor(conn, user)
    if not auth.can(user['role'], 'view'):
        raise permissions.Denied('Report unavailable.')
    if (not isinstance(query, str) or len(query) > 120 or type(limit) is not int
            or not 1 <= limit <= 25 or type(offset) is not int or not 0 <= offset <= 2000):
        raise ValueError('Use up to 120 search characters and a page size from 1 to 25.')
    if os.environ.get('CSS_MCP_UNIT_SURVEYS_ENABLED') != '1':
        return {'availability': 'not_available'}
    rows = conn.execute("SELECT id,name,path FROM org_unit WHERE path IS NOT NULL AND path<>'' ORDER BY path,id LIMIT 2001").fetchall()
    if len(rows) > 2000:
        return {'availability': 'not_available', 'reason': 'capacity_limit'}
    needle = query.strip().casefold()
    found = [{'unit_id': str(r[0]), 'name': r[1], 'path': r[2]} for r in rows
             if needle in (r[1] + ' ' + r[2]).casefold()]
    return {'availability': 'available', 'as_of': tz.now_iso(), 'data': found[offset:offset+limit],
            'next_offset': offset+limit if len(found) > offset+limit else None}


def _activity_summary(conn, user, origin, year, quarter, unit=None, enabled_flag=None):
    """Fresh Type 2 consolidated quarter; caller owns the read snapshot."""
    user = permissions.actor(conn, user)
    if not auth.can(user['role'], 'view'):
        raise permissions.Denied('Report unavailable.')
    if type(year) is not int or not 1900 <= year <= 9998 or type(quarter) is not int or not 1 <= quarter <= 4:
        raise ValueError('Choose a valid year and quarter (1 to 4).')
    first = 3 * quarter - 2
    last = first + 2
    start = date(year, first, 1).isoformat()
    end = date(year, last, calendar.monthrange(year, last)[1]).isoformat()
    result = {'survey_type': 2, 'scope': 'bureau', 'date_basis': 'activity_start_date',
              'start_date': start, 'end_date': end, 'as_of': tz.now_iso(),
              'web_url': origin + '/reports?' + urlencode({'type': 2, 'period': f'quarter:{year}-Q{quarter}'}),
              'minimum_sample': MIN_SAMPLE,
              'scoring': 'Overall is the mean of available dimension means, not a percentage or a mean of respondent scores. A/B items use 1–7; C uses 1–4. Missing, invalid and N/A answers are excluded.'}
    if unit:
        result.update(scope='unit_and_descendants', unit_id=str(unit[0]), unit_name=unit[1],
                      unit_path=unit[2], web_url=origin + '/reports?' + urlencode(
                          {'type': 2, 'period': f'quarter:{year}-Q{quarter}', 'org': unit[2]}))
    flag = enabled_flag or ('CSS_MCP_UNIT_SURVEYS_ENABLED' if unit else 'CSS_MCP_ACTIVITY_SURVEYS_ENABLED')
    if os.environ.get(flag) != '1':
        # Do not disclose unit identity while this pilot is disabled.
        return {'availability': 'not_available'} if unit else dict(result, availability='not_available')
    unit_sql = ''
    args = [start, end]
    if unit:
        unit_sql = (' AND fi.lead_org_id IN (SELECT id FROM org_unit WHERE path=? '
                    'OR substr(path,1,?)=?)')
        args.extend([unit[2], len(unit[2])+1, unit[2]+'/'])
    selected = conn.execute('''SELECT r.id FROM response r JOIN form_instance fi ON fi.id=r.form_instance_id
        WHERE fi.survey_type=2 AND COALESCE(fi.archived,0)=0 AND r.archived_at IS NULL
        AND substr(fi.event_date,1,10)>=? AND substr(fi.event_date,1,10)<=?
        ''' + unit_sql + ' ORDER BY r.id LIMIT ?', (*args, MAX_RESPONSES + 1)).fetchall()
    if len(selected) > MAX_RESPONSES:
        return dict(result, availability='not_available', reason='capacity_limit')
    ids = [r[0] for r in selected]
    frame = _survey_frame(conn, ids, 2)
    if frame is None:
        return dict(result, availability='not_available', reason='capacity_limit')
    block = servqual_block(frame, eng.DIM_MAP_FORM2)
    result.update(availability='available', submissions=len(ids),
                  report_submissions=block['respondents'], rated_respondents=block['overall']['n'])
    if not ids:
        return dict(result, state='no_matching_responses')
    if not block['has_data']:
        return dict(result, state='no_valid_ratings')
    valid = eng.valid_answers(frame)
    valid = valid[valid['item_id'].isin(['A', *eng.SERVQUAL_ITEMS, 'C'])]
    counts = valid.groupby('item_id', observed=True)['response_id'].nunique()
    if block['overall']['n'] < MIN_SAMPLE or any(0 < n < MIN_SAMPLE for n in counts):
        return dict(result, state='insufficient_sample')
    return dict(result, state='rated', overall_mean=block['overall']['value'],
                expectation_mean=block['expectation']['value'], osq_mean=block['osq']['value'],
                expectation_answers=block['expectation']['n'], osq_answers=block['osq']['n'],
                gap=(block['overall']['value'] - block['expectation']['value'])
                    if block['expectation']['value'] is not None else None,
                dimensions=[{'dimension': d['dim'], 'mean': d['value'], 'valid_item_answers': d['n']}
                            for d in block['dimensions']])


def _survey_frame(conn, ids, survey_type):
    """Bounded answer-only frame, shared by Type 2 and Type 3 projections."""
    records = []
    for offset in range(0, len(ids), 500):
        batch = ids[offset:offset + 500]
        placeholders = ','.join('?' for _ in batch)
        # Include unrated/unknown item rows when counting source-report
        # submissions, but never read respondent text or identity fields.
        found = conn.execute('SELECT response_id,item_id,value,is_na FROM answer WHERE response_id IN ('
                             + placeholders + ') ORDER BY id LIMIT ?',
                             (*batch, MAX_ACTIVITY_ANSWERS + 1 - len(records))).fetchall()
        records.extend(found)
        if len(records) > MAX_ACTIVITY_ANSWERS:
            return None
    frame = pd.DataFrame(records, columns=['response_id', 'item_id', 'value', 'is_na'])
    frame['survey_type'] = survey_type
    return frame


def can_view_resource_person(user, person):
    """Same current profile visibility boundary used by the signed-in pages."""
    return bool(person and auth.can(user.get('role'), 'view') and
                (auth.can(user.get('role'), 'hide') or
                 not (person.get('hidden_public') or st.is_bureau_director(person))))


def resource_person_summary(conn, user, origin, resource_person_id, year):
    user = permissions.actor(conn, user)
    if (type(resource_person_id) is not int or not 1 <= resource_person_id <= 9223372036854775807
            or type(year) is not int or not 1900 <= year <= 9998):
        raise ValueError('Choose a valid resource-person ID and year.')
    # Check eligibility before returning either a name or disabled-state metadata.
    person = st.get_rp(conn, resource_person_id)
    if not can_view_resource_person(user, person):
        raise permissions.Denied('Resource person not found or unavailable to you.')
    start, end = f'{year}-01-01', f'{year}-12-31'
    result = {'survey_type': 3, 'resource_person_id': str(resource_person_id),
              'scope': 'one_resource_person',
              'date_basis': 'activity_start_date', 'start_date': start, 'end_date': end,
              'as_of': tz.now_iso(), 'minimum_sample': MIN_SAMPLE,
              'web_url': origin + f'/dashboard/people/{resource_person_id}?' + urlencode({'period': f'year:{year}'}),
              'scoring': 'Person-dashboard quality index (0–100): mean per respondent of normalized B items (1–7) and C (1–4), then mean across respondents. A is excluded. Dimension means use the Type 3 map.'}
    if os.environ.get('CSS_MCP_RESOURCE_PERSON_SURVEYS_ENABLED') != '1':
        return dict(result, availability='not_available')
    result['name'] = person['name']
    selected = conn.execute('''SELECT r.id FROM response r JOIN form_instance fi ON fi.id=r.form_instance_id
        WHERE fi.survey_type=3 AND fi.rp_id=? AND COALESCE(fi.archived,0)=0 AND r.archived_at IS NULL
        AND substr(fi.event_date,1,10)>=? AND substr(fi.event_date,1,10)<=?
        ORDER BY r.id LIMIT ?''', (resource_person_id, start, end, MAX_RESPONSES + 1)).fetchall()
    if len(selected) > MAX_RESPONSES:
        return dict(result, availability='not_available', reason='capacity_limit')
    ids = [r[0] for r in selected]
    frame = _survey_frame(conn, ids, 3)
    if frame is None:
        return dict(result, availability='not_available', reason='capacity_limit')
    quality, rated = eng.quality_index(frame)
    valid = eng.valid_answers(frame)
    perception_n = int(valid.loc[valid['item_id'].isin(eng.SERVQUAL_ITEMS), 'response_id'].nunique())
    result.update(availability='available', submissions=len(ids),
                  report_submissions=int(frame['response_id'].nunique()),
                  rated_respondents=perception_n, quality_respondents=rated)
    if not ids:
        return dict(result, state='no_matching_responses')
    if quality is None or not perception_n:
        return dict(result, state='no_valid_ratings')
    valid = valid[valid['item_id'].isin([*eng.SERVQUAL_ITEMS, 'C'])]
    counts = valid.groupby('item_id', observed=True)['response_id'].nunique()
    if rated < MIN_SAMPLE or perception_n < MIN_SAMPLE or any(0 < n < MIN_SAMPLE for n in counts):
        return dict(result, state='insufficient_sample')
    osq = eng.osq_C(frame)
    dimensions = [(dim, eng.dimension_mean(frame, items)) for dim, items in eng.DIM_MAP_FORM3.items()]
    return dict(result, state='rated', quality_index=quality, quality_scale='0–100',
                osq_mean=osq.value, osq_scale='1–4', osq_answers=osq.n,
                dimensions=[{'dimension': dim, 'mean': m.value, 'scale': '1–7', 'valid_item_answers': m.n}
                            for dim, m in dimensions])


MAX_ACTIVITY_INSTANCES = 2000


def _activity_catalog(conn, user):
    user = permissions.actor(conn, user)
    if not auth.can(user['role'], 'view'):
        raise permissions.Denied('Report unavailable.')
    if os.environ.get('CSS_MCP_ACTIVITY_DETAILS_ENABLED') != '1':
        return user, None, 'disabled'
    selected = conn.execute("SELECT id FROM form_instance WHERE survey_type IN (2,3) "
                            "AND COALESCE(archived,0)=0 AND COALESCE(pooled,0)=0 LIMIT ?",
                            (MAX_ACTIVITY_INSTANCES + 1,)).fetchall()
    if len(selected) > MAX_ACTIVITY_INSTANCES:
        return user, None, 'capacity_limit'
    answered = {r[0] for r in conn.execute('''SELECT fi.id FROM form_instance fi
        WHERE fi.survey_type=2 AND COALESCE(fi.archived,0)=0 AND COALESCE(fi.pooled,0)=0
        AND EXISTS (SELECT 1 FROM response r JOIN answer a ON a.response_id=r.id
                    WHERE r.form_instance_id=fi.id AND r.archived_at IS NULL)''')}
    groups = [g for g in di.group_activity_instances(st.list_activity_instances(conn)).values()
              if any(f['id'] in answered for f in g)]
    return user, groups, None


def _activity_identity(group, origin):
    f2 = [f for f in group if f['survey_type'] == 2]
    title = f2[0]['topic'] or 'Activity on ' + str(f2[0]['event_date'])
    representative = min(f['id'] for f in group)
    return {'activity_id': str(representative), 'title': title[:250],
            'title_truncated': len(title) > 250, 'start_date': f2[0]['event_date'],
            'end_date': max((f['end_date'] for f in group if f.get('end_date')), default=None),
            'web_url': origin + f'/reports/activities/{representative}'}


def find_survey_activities(conn, user, origin, year, quarter, query='', limit=10, offset=0):
    if (type(year) is not int or not 1900 <= year <= 9998 or type(quarter) is not int or not 1 <= quarter <= 4
            or type(limit) is not int or not 1 <= limit <= 25 or type(offset) is not int or not 0 <= offset <= MAX_ACTIVITY_INSTANCES
            or not isinstance(query, str) or len(query) > 120):
        raise ValueError('Use a valid year/quarter, up to 120 search characters and a page size of 1–25.')
    first, last = quarter * 3 - 2, quarter * 3
    start = date(year, first, 1).isoformat()
    end = date(year, last, calendar.monthrange(year, last)[1]).isoformat()
    _, groups, reason = _activity_catalog(conn, user)
    result = {'as_of': tz.now_iso(), 'date_basis': 'activity_start_date', 'start_date': start, 'end_date': end}
    if reason:
        return dict(result, availability='not_available', reason=reason)
    needle = query.strip().casefold()
    items = [_activity_identity(g, origin) for g in groups
             if start <= (g[0]['event_date'] or '') <= end
             and needle in str(next(f for f in g if f['survey_type'] == 2)['topic']
                               or 'Activity on ' + str(g[0]['event_date'])).casefold()]
    items.sort(key=lambda i: (i['start_date'], int(i['activity_id'])), reverse=True)
    return dict(result, availability='available', data=items[offset:offset + limit],
                next_offset=offset + limit if len(items) > offset + limit else None,
                note='Metadata discovery includes activities without a usable score; their detail report may be unavailable. Pagination is a fresh snapshot per call.')


def activity_detail(conn, user, origin, activity_id):
    if type(activity_id) is not int or not 1 <= activity_id <= 9223372036854775807:
        raise ValueError('Choose a positive activity or member form ID.')
    _, groups, reason = _activity_catalog(conn, user)
    result = {'as_of': tz.now_iso(), 'survey_type': 2, 'scope': 'one_merged_activity',
              'date_basis': 'activity_start_date', 'minimum_sample': MIN_SAMPLE}
    if reason:
        return dict(result, availability='not_available', reason=reason)
    group = next((g for g in groups if any(f['id'] == activity_id for f in g)), None)
    if group is None:
        raise permissions.Denied('Activity not found or unavailable to you.')
    result.update(_activity_identity(group, origin), availability='available')
    f2_ids = [f['id'] for f in group if f['survey_type'] == 2]
    if len(f2_ids) > 500:
        return dict(result, availability='not_available', reason='capacity_limit')
    placeholders = ','.join('?' for _ in f2_ids)
    selected = conn.execute('SELECT r.id,r.form_instance_id FROM response r WHERE r.archived_at IS NULL '
                            'AND r.form_instance_id IN (' + placeholders + ') ORDER BY r.id LIMIT ?',
                            (*f2_ids, MAX_RESPONSES + 1)).fetchall()
    if len(selected) > MAX_RESPONSES:
        return dict(result, availability='not_available', reason='capacity_limit')
    ids = [r[0] for r in selected]
    frame = _survey_frame(conn, ids, 2)
    if frame is None:
        return dict(result, availability='not_available', reason='capacity_limit')
    mapping = dict(selected)
    frame['form_instance_id'] = frame['response_id'].map(mapping)
    block = servqual_block(frame, eng.DIM_MAP_FORM2)
    result.update(submissions=len(ids), report_submissions=block['respondents'], rated_respondents=block['overall']['n'])
    if not ids:
        return dict(result, state='no_matching_responses')
    report = di.activity_servqual(frame, f2_ids)
    if report is None:
        return dict(result, state='no_valid_ratings')
    if eng.overall_perception(frame, di.EVENT_DIMS_FORM2).value is None:
        return dict(result, availability='not_available', reason='source_report_unavailable',
                    note='The existing activity detail page needs valid event-dimension ratings.')
    valid = eng.valid_answers(frame)
    valid = valid[valid['item_id'].isin(['A', *eng.SERVQUAL_ITEMS, 'C'])]
    counts = valid.groupby('item_id', observed=True)['response_id'].nunique()
    if block['overall']['n'] < MIN_SAMPLE or any(0 < n < MIN_SAMPLE for n in counts):
        return dict(result, state='insufficient_sample')
    return dict(result, state='rated', overall_mean=report['average'], expectation_mean=report['expectation'],
                osq_mean=report['osq'], gap=report['servqual'],
                scoring='Full five-dimension SERVQUAL scorecard from the activity detail page, not its event-only card headline. A/B: 1–7; C: 1–4. Missing/N/A/invalid answers excluded.',
                dimensions=[{'dimension': d['key'], 'mean': d['value'], 'valid_item_answers': d['n']} for d in report['dims']])
