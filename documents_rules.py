"""Bounded declarative policy evaluation; never eval, executable expressions, or model actions."""
from datetime import date, timedelta
import json
import unicodedata
import storage as st
from documents_storage import rows

FIELDS = {'subject', 'sender', 'type'}
POLICY_KEYS = {'default_days', 'buffer_days', 'anchor', 'cutoff', 'reminder_time', 'escalate_chief_days',
               'escalate_director_days', 'approval', 'signature_required', 'ack_required', 'closure', 'release'}


def normalize(text):
    return ' '.join(unicodedata.normalize('NFKC', str(text)).casefold().split())


def validate(body):
    if not isinstance(body, dict) or set(body) - {'type','field','keywords','mode','priority','lead_id','lead_unit_id','unit_ids','assignees','policy'}:
        raise ValueError('Unknown rule fields.')
    if body.get('field', 'subject') not in FIELDS or body.get('mode', 'any') not in ('any','all','exact'):
        raise ValueError('Choose a supported field and match mode.')
    words = body.get('keywords', [])
    if not isinstance(words, list) or len(words) > 30 or any(not isinstance(w,str) or not w.strip() or len(w)>100 for w in words):
        raise ValueError('Use up to 30 nonempty keywords, 100 characters each.')
    if not isinstance(body.get('priority',0), int):
        raise ValueError('Rule priority must be an integer.')
    for key in ('assignees','unit_ids'):
        if not isinstance(body.get(key,[]),list) or len(body.get(key,[]))>100:
            raise ValueError(key+' must be a list of at most 100 IDs.')
    for uid in [body.get('lead_id')] + body.get('assignees', []):
        if uid is not None and (type(uid) is not int or uid < 1):
            raise ValueError('Assignees must be account IDs.')
    for unit in [body.get('lead_unit_id')] + body.get('unit_ids',[]):
        if unit is not None and (type(unit) is not int or unit<1):
            raise ValueError('Routing units must be positive directory IDs.')
    policy = body.get('policy', {})
    if not isinstance(policy,dict) or set(policy) - POLICY_KEYS:
        raise ValueError('Unknown policy fields.')
    for key in ('default_days','buffer_days','escalate_chief_days','escalate_director_days'):
        if key in policy and (type(policy[key]) is not int or not 0 <= policy[key] <= 366):
            raise ValueError(key + ' must be between 0 and 366.')
    if policy.get('approval','director') not in ('routine','director') or policy.get('anchor','registration') not in ('registration','receipt'):
        raise ValueError('Invalid approval class or deadline anchor.')
    for key in ('signature_required','ack_required'):
        if key in policy and type(policy[key]) is not bool:
            raise ValueError(key + ' must be true or false.')
    import re
    for key in ('cutoff','reminder_time'):
        if key in policy and not re.fullmatch(r'([01]\d|2[0-3]):[0-5]\d', policy[key]):
            raise ValueError(key + ' must be HH:MM.')
    for key in ('closure','release'):
        if key in policy and (not isinstance(policy[key],list) or any(not isinstance(v,str) or not v.strip() or len(v)>100 for v in policy[key])):
            raise ValueError(key + ' must list required evidence labels.')
    return body


def evaluate(conn, fields):
    matches = []
    for rule in rows(conn, "SELECT * FROM document_rule_version WHERE state='active' ORDER BY id"):
        body = json.loads(rule['body_json'])
        if body.get('type') and normalize(body['type']) != normalize(fields.get('type','')):
            continue
        hay = normalize(fields.get(body.get('field','subject'),''))
        checks = [(normalize(w) == hay if body.get('mode') == 'exact' else normalize(w) in hay) for w in body.get('keywords',[])]
        if checks and not (all(checks) if body.get('mode') == 'all' else any(checks)):
            continue
        matches.append({'id':rule['id'], 'name':rule['name'], 'body':body})
    leads = sorted({m['body']['lead_id'] for m in matches if m['body'].get('lead_id')})
    assignees = sorted({u for m in matches for u in m['body'].get('assignees',[])})
    lead_units=sorted({m['body']['lead_unit_id'] for m in matches if m['body'].get('lead_unit_id')})
    unit_ids=sorted(set(lead_units) | {unit for m in matches for unit in m['body'].get('unit_ids',[])})
    for unit_id in unit_ids:
        unit=conn.execute('SELECT path FROM org_unit WHERE id=?',(unit_id,)).fetchone()
        if unit:
            for uid,path in conn.execute('SELECT a.id,u.path FROM admin_user a JOIN resource_person r ON r.id=a.rp_id JOIN org_unit u ON u.id=r.org_unit_id WHERE a.active=1 AND r.is_internal=1 AND r.archived_at IS NULL'):
                if path==unit[0] or path.startswith(unit[0]+'/'):
                    assignees.append(uid)
    for unit_id in lead_units:
        leads.extend(st.org_unit_chiefs(conn,unit_id))
        oic=conn.execute('SELECT admin_user_id FROM section_oic WHERE org_unit_id=?',(unit_id,)).fetchone()
        if oic:
            leads.append(oic[0])
    leads,assignees=sorted(set(leads)),sorted(set(assignees))
    # Priority resolves policy values only; conflicting ownership is always explicit.
    policy, conflicts = {}, []
    for key in POLICY_KEYS:
        values = [(m['body'].get('priority',0), m['body']['policy'][key]) for m in matches if key in m['body'].get('policy',{})]
        if values:
            top = max(p for p,v in values)
            choices = {json.dumps(v,sort_keys=True) for p,v in values if p==top}
            if len(choices)>1:
                conflicts.append(key)
            else:
                policy[key] = json.loads(choices.pop())
    return {'matches':matches, 'leads':leads, 'lead_units':lead_units, 'unit_ids':unit_ids, 'assignees':assignees, 'policy':policy, 'conflicts':conflicts}


def working_day(conn, day):
    return day.weekday() < 5 and st.get_holiday(conn, day) is None


def shift(conn, day, n):
    day = date.fromisoformat(day) if isinstance(day,str) else day
    step = 1 if n >= 0 else -1
    for _ in range(abs(n)):
        day += timedelta(days=step)
        while not working_day(conn, day):
            day += timedelta(days=step)
    return day


def coverage(conn, *days):
    years = {date.fromisoformat(d[:10]).year for d in days if d}
    return [f'Holiday coverage for {y} has not been confirmed.' for y in sorted(years)
            if st.get_setting(conn, f'documents.holidays_confirmed.{y}', '0') != '1']
