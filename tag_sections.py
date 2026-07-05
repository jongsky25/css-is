"""
Backfill the organizing SECTION of existing activities by setting
form_instance.lead_org_id to a section org_unit. load_atoms already rolls a
Type-2 event up by its lead_org_id path, so this immediately enables per-section
and per-division (path-prefix) analytics.

Suggestion per event-group (date+venue+current-lead):
  1. the modal home-section of the event's rated internal speakers, else
  2. a topic-keyword match to a section's focus area.
Events with neither signal are left at the bureau ('unassigned') for manual
tagging in the Activities view. Backs up + audits + journals (reversible).
"""
from __future__ import annotations
import sys
from collections import Counter, defaultdict
import storage as st
import harmonize as h

# section path -> focus keywords (from the official section names + title anchors)
KW = {
    "S4": ["gida", "bhw", "uua", "purok", "kalusugan", " pk ", "indigenous", "equity",
           "geographically", "disadvantaged", "special concern", "ip health", "ip oplan"],
    "S5": ["sglg", "lgu performance", "performance monitoring", "seal of good",
           "lgu scorecard", "monitoring and evaluation"],
    "S2": ["liph", "aop", "planning", "financing", "investment plan", "budget"],
    "S3": ["lhb", "local health board", "leadership", "governance", "guidebook"],
    "S1": ["integration", "lhs ml", "maturity level", "service delivery network",
           "sdn", "local health system integration"],
}


def _section_ids(conn):
    """short (S1..S5) -> org_unit id."""
    out = {}
    for oid, path in conn.execute("SELECT id, path FROM org_unit WHERE level='section'"):
        seg = path.rsplit("/", 1)[-1]
        out[seg] = oid
    return out


def _kw_guess(topics):
    blob = " ".join(topics).lower()
    hits = {s: sum(blob.count(k) for k in ks) for s, ks in KW.items()}
    best = max(hits, key=hits.get)
    return best if hits[best] > 0 else None


def build_suggestions(conn):
    rows = conn.execute("""
        SELECT fi.id, fi.survey_type, fi.event_date, COALESCE(fi.venue,''), fi.lead_org_id,
               fi.topic, ou.path
        FROM form_instance fi
        LEFT JOIN resource_person rp ON rp.id = fi.rp_id
        LEFT JOIN org_unit ou        ON ou.id = rp.org_unit_id
        WHERE fi.survey_type IN (2,3) AND COALESCE(fi.archived,0)=0
    """).fetchall()
    groups = defaultdict(lambda: {"ids": [], "secs": Counter(), "topics": []})
    for fid, stp, date, ven, lead, topic, path in rows:
        g = groups[(date, ven.strip().lower(), lead)]
        g["ids"].append(fid)
        if path and path.count("/") >= 2:
            g["secs"][path.rsplit("/", 1)[-1]] += 1
        if topic:
            g["topics"].append(topic)
    out = []        # (instance_ids, section_short, source)
    for key, g in groups.items():
        s_spk = g["secs"].most_common(1)[0][0] if g["secs"] else None
        pick = s_spk or _kw_guess(g["topics"])
        if pick:
            out.append((g["ids"], pick, "speaker" if s_spk else "keyword"))
    return out


def run(db_path):
    bk = h.backup_db(db_path, tag="presection")
    conn = st.connect(db_path)
    secids = _section_ids(conn)
    sugg = build_suggestions(conn)
    batch = f"section-{h._dt.datetime.now():%Y%m%d_%H%M%S}"
    conn.execute(h._UNDO_DDL)
    events = inst = 0
    by_sec = Counter()
    for ids, short, src in sugg:
        oid = secids.get(short)
        if not oid:
            continue
        for fid in ids:
            old = conn.execute("SELECT lead_org_id FROM form_instance WHERE id=?", (fid,)).fetchone()[0]
            h._journal(conn, batch, "fi_lead", fid, {"old": old})
            conn.execute("UPDATE form_instance SET lead_org_id=? WHERE id=?", (oid, fid))
            inst += 1
        events += 1
        by_sec[short] += 1
    conn.commit()
    st.audit(conn, "(section backfill)", "tag_sections",
             summary=f"Tagged {events} activities to their organizing section "
                     f"({inst} form instances) from speaker+keyword heuristics. By section: "
                     f"{dict(by_sec)}.")
    conn.close()
    return bk, events, inst, dict(by_sec)


if __name__ == "__main__":
    db = sys.argv[1] if len(sys.argv) > 1 else "css_is.db"
    bk, ev, inst, by = run(db)
    print("DB:", db, "| backup:", bk)
    print(f"tagged {ev} events / {inst} instances | by section: {by}")
