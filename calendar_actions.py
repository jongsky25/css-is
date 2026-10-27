"""Shared calendar form validation and actor-aware transactional creation.

No transport or relay calls occur in a business transaction. The UI retains its
existing post-save room/Meet orchestration; bot orchestration is a later increment.
"""
from datetime import date

from documents_storage import rows,transaction
import office_calendar as oc
import recurrence
import storage as st

FORM_KINDS=('meeting','training','travel','deadline','audit_mr','banner')
STATUSES=('confirmed','tentative','postponed','cancelled')


def parse(f, existing=None, allowed_people=()):
    """(storage fields, people [(uid, role)], tags, error) from a posted form."""
    if f["kind"] not in FORM_KINDS:
        return None, None, None, "Pick a type from the list."
    if f["status"] not in STATUSES or f["status"] == "cancelled":
        return None, None, None, "Pick a status from the list."
    if any(int(u) not in allowed_people for u in f["people"]):
        return None, None, None, "One of the people you chose isn't an active account."
    if f["audience"] == "people" and not f["people"]:
        return None, None, None, "Choose who this is for, or pick a wider audience."
    if f["audience"] == "unit" and not f["owner_org_id"]:
        return None, None, None, ("Choose the unit this belongs to, or nobody outside "
                                  "the people you add will see it.")
    fields = {k: f.get(k, "") or None for k in (
        "end_date", "start_time", "end_time", "time_note", "venue", "modality",
        "meeting_url", "note")}
    fields.update(title=f["title"], start_date=f["start_date"], kind=f["kind"],
                  status=f["status"], audience=f["audience"],
                  owner_org_id=int(f["owner_org_id"]) if f["owner_org_id"].isdigit() else None,
                  extra_org_ids=[int(x) for x in f.get("extra_org_ids", [])])
    repeat = f.get("repeat") or "none"
    if (existing or {}).get("event_id"):
        repeat = "none"                                      # an activity's item never repeats
    try:
        start = date.fromisoformat(f["start_date"])
        until = date.fromisoformat(f["until"]) if f.get("until") else None
        fields["rrule"] = recurrence.build(repeat, start, until)
    except ValueError as ex:
        return None, None, None, (str(ex) if repeat != "none" else "Pick a real start date.")
    if repeat != "none" and f["kind"] == "travel":
        return None, None, None, "A trip can't repeat. Add each trip on its own."
    had = {p["user_id"]: p["role"] for p in (existing or {}).get("people", [])}
    default = "travel" if f["kind"] == "travel" else "attending"
    people = [(int(u), "lead" if had.get(int(u)) == "lead" else default)
              for u in f["people"]]
    tags = [t for t in f.get("tags", "").split(",")]
    return fields, people, tags, ""



def actor(conn,user):
    found=rows(conn,"SELECT * FROM admin_user WHERE id=? AND active=1 AND must_change=0",(user['id'],))
    if not found or found[0]['role'] not in ('viewer','encoder','section_manager','admin'):
        raise ValueError('A current staff account is required.')
    return found[0]


def prepare(conn,user,form):
    user=actor(conn,user)
    fields,people,tags,error=parse(form,allowed_people={p['user_id'] for p in oc.people_choices(conn)})
    if error:
        raise ValueError(error)
    # Use storage's normalizer at preview time too, before accepting a confirmation.
    clean=st.cal_validate(**{k:v for k,v in fields.items() if k!='extra_org_ids'})
    clean['extra_org_ids']=fields.get('extra_org_ids',[])
    return clean,people,tags


def create_in_transaction(conn,user,fields,people,tags, *, audit_it=True):
    """Create atomically; a caller disabling the normal audit must supply its own."""
    if not conn.in_transaction:
        raise RuntimeError('Calendar creation requires a caller-owned writer transaction.')
    user=actor(conn,user)
    allowed={p['user_id'] for p in oc.people_choices(conn)}
    if any(uid not in allowed for uid,_ in people):
        raise ValueError("One of the people you chose isn't an active account.")
    if fields.get('kind') not in FORM_KINDS or fields.get('status') not in STATUSES[:-1]:
        raise ValueError('Choose a supported calendar type and status.')
    if fields.get('audience')=='people' and not people:
        raise ValueError('Choose who this is for, or pick a wider audience.')
    if fields.get('audience')=='unit' and not fields.get('owner_org_id'):
        raise ValueError('Choose the unit this belongs to, or nobody outside the people you add will see it.')
    if fields.get('owner_org_id') and not conn.execute('SELECT 1 FROM org_unit WHERE id=?',(fields['owner_org_id'],)).fetchone():
        raise ValueError('Choose an existing owning unit.')
    if set(fields)-{'title','start_date','end_date','kind','status','start_time','end_time','time_note','venue','modality','meeting_url','note','owner_org_id','extra_org_ids','audience','rrule','exdates'}:
        raise ValueError('Unsupported calendar create fields.')
    values=dict(fields);title=values.pop('title');start=values.pop('start_date')
    return st.cal_create(conn,title,start,people=people,tags=tags,by=user['username'],commit=False,audit_it=audit_it,**values)


def create(conn,user,fields,people,tags):
    with transaction(conn):
        return create_in_transaction(conn,user,fields,people,tags)
