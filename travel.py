"""Travel filing: database layer (docs/TRAVEL_FILING_PLAN.md). Rules live in travel_rules.py;
routes and templates only call these functions. This increment holds the seed data and the
small readers the rules need."""
from __future__ import annotations
import json

import storage as st
import tzutil as tz

_SEED_KEY = "travel.seeded"
SETTING_DEFAULTS = {
    "travel.enabled": "1",
    "travel.sig.head_name": "",
    "travel.sig.head_title": "OIC-Director",
    "travel.sig.certifier_name": "",
    "travel.sig.certifier_title": "Medical Officer V",
    "travel.sig.station": "",
    "travel.template_admins": "",
    "travel.retention_months": "12",
}

ROUTE_TYPES = (("residence_airport", "Residence ⇄ Airport"), ("residence_venue", "Residence ⇄ Venue"))
CEILINGS = (("rer", "residence_airport", 550), ("rer", "residence_venue", 450),
            ("tnvs", "*", 700), ("taxi", "*", 700), ("cenrr", "*", 300))

# Starter MC 114 wording: generic, with tokens the preview fills in. Template administrators
# edit or replace these in the justification library.
_STARTER = (
    ("Participation in an official activity", "separate",
     "This is to justify the participation of {{traveler_name}} in the official travel for "
     "{{activity_title}} on {{dates}} at {{venue}}.\n\n"
     "The activity required the traveller's participation for the reasons stated below. "
     "This justification is made to support approval of the travel."),
    ("Participation in an official activity (Appendix B)", "appendix_b",
     "The official travel for {{activity_title}} on {{dates}} at {{venue}} was necessary and "
     "was completed as planned."),
)


def ensure_defaults(conn):
    """Seed route types, ceilings, starter justifications and settings once. Keyed in
    app_setting so an administrator who later edits or removes a row never has it put back."""
    for k, v in SETTING_DEFAULTS.items():
        if st.get_setting(conn, k) is None:
            st.set_setting(conn, k, v)
    if st.get_setting(conn, _SEED_KEY) == "1":
        return
    now = tz.now_iso()
    for i, (code, label) in enumerate(ROUTE_TYPES):
        conn.execute("INSERT OR IGNORE INTO travel_route_type(code, label, active, sort) VALUES (?,?,1,?)",
                     (code, label, i))
    for mode, rt, amount in CEILINGS:
        conn.execute("INSERT OR IGNORE INTO travel_ceiling(mode, route_type, amount, updated_by, updated_at) "
                     "VALUES (?,?,?,?,?)", (mode, rt, amount, "system", now))
    for title, fmt, body in _STARTER:
        conn.execute("INSERT INTO travel_justification(title, format, body, active, updated_by, updated_at) "
                     "VALUES (?,?,?,1,'system',?)", (title, fmt, body, now))
    st.set_setting(conn, _SEED_KEY, "1")
    conn.commit()


def enabled(conn) -> bool:
    return st.get_setting(conn, "travel.enabled", "1") != "0"


def ceilings(conn) -> dict:
    """{(mode, route_type): amount} for travel_rules.ride_check, approved routes only."""
    active = {r[0] for r in conn.execute("SELECT code FROM travel_route_type WHERE active=1")}
    return {(m, rt): float(a) for m, rt, a in conn.execute("SELECT mode, route_type, amount FROM travel_ceiling")
            if m != "rer" or rt in active}


def answers_of(filing) -> dict:
    try:
        v = json.loads(filing.get("answers_json") or "{}")
        return v if isinstance(v, dict) else {}
    except ValueError:
        return {}
