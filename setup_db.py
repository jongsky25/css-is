"""
Set up the database and prove it feeds the calculator.

Run:  python setup_db.py

It creates a fresh database file (css_is.db), fills it with a small sample --
an org directory, a couple of QR-bound forms, and some answers -- then reads it
all back and runs the calculator on it. If you see real scores at the end, your
storage and calculator are working together on your laptop.
"""

import os
import storage as st
import css_is_engine as eng

DB = "css_is.db"
if os.path.exists(DB):
    os.remove(DB)            # start clean each time you run this demo

conn = st.connect(DB)
st.init_db(conn)

# --- 1. Org directory: a small bureau -----------------------------------
bureau = st.add_org_unit(conn, "Bureau", "bureau", "Bureau")
div1   = st.add_org_unit(conn, "Division 1", "division", "Bureau/Div1")
secA   = st.add_org_unit(conn, "Section A", "section", "Bureau/Div1/SecA")
div2   = st.add_org_unit(conn, "Division 2", "division", "Bureau/Div2")
secC   = st.add_org_unit(conn, "Section C", "section", "Bureau/Div2/SecC")
secD   = st.add_org_unit(conn, "Section D", "section", "Bureau/Div2/SecD")

# --- 2. People and an outside organizer ---------------------------------
vince     = st.add_rp(conn, "Vince", is_internal=True, org_unit_id=secA)
guest     = st.add_rp(conn, "Guest Speaker", is_internal=False)
other_org = st.add_external_organizer(conn, "Other Agency")

# --- 3. QR-bound forms (the manager creates these) ----------------------
# Type 1 ARTA: a walk-in service in Section D, served by one staff member
f_arta = st.create_form_instance(conn, survey_type=1, form="F1",
                                 event_date="2026-02-12",
                                 serving_staff="Staff One",
                                 serving_staff_org_id=secD, service="Records Request")

# Type 3: Vince speaks at a BUREAU event (internal organizer = Division 1)
f_rp_internal = st.create_form_instance(conn, survey_type=3, form="F3",
                                        event_date="2026-03-05", rp_id=vince,
                                        topic="VPD Surveillance", lead_org_id=div1)

# Type 3: Vince INVITED by another agency (external organizer, no Form 2)
f_rp_external = st.create_form_instance(conn, survey_type=3, form="F3",
                                        event_date="2026-04-20", rp_id=vince,
                                        topic="Immunization Systems",
                                        organizer_external_id=other_org)

# --- 4. Some answers ----------------------------------------------------
# ARTA: 14 people, 11 of them rate every SQD as Strongly Agree (5), 3 as Neither (3)
for i in range(14):
    v = 5 if i < 11 else 3
    st.record_response(conn, f_arta, [(it, v) for it in eng.ARTA_HEADLINE_ITEMS])

# Vince at the bureau event: 12 people, mostly high
for i in range(12):
    base = 7 if i < 9 else 5
    answers = [("A", 6)] + [(b, base) for b in ["B1","B2","B3","B4","B5","B6","B7","B8","B9"]] + [("C", 4)]
    st.record_response(conn, f_rp_internal, answers)

# Vince at the external event: 10 people, even stronger
for i in range(10):
    answers = [("A", 6)] + [(b, 7) for b in ["B1","B2","B3","B4","B5","B6","B7","B8","B9"]] + [("C", 4)]
    st.record_response(conn, f_rp_external, answers)

# --- 5. Read it back and run the calculator -----------------------------
atoms = st.load_atoms(conn)

print("Database created:", os.path.abspath(DB))
print(f"Stored {atoms['response_id'].nunique()} responses "
      f"= {len(atoms)} individual answers (atoms).\n")

print("Now scoring straight from the database:\n")

# ARTA headline for Section D
arta = eng.arta_topbox(eng.scope(atoms, "Bureau/Div2/SecD"))
print(f"  ARTA  (Section D, Records Request) : {arta.show('pct')}  -> "
      f"{eng.band(arta.value, eng.ARTA_BANDS)}")

# Vince's overall as a resource person, split by who organized (Type 3 only)
own = eng.overall_perception(eng.scope(atoms, "Bureau", organizer_type="internal", survey_type=3), eng.DIM_MAP_FORM3)
ext = eng.overall_perception(eng.scope(atoms, organizer_type="external", survey_type=3), eng.DIM_MAP_FORM3)
print(f"  Vince RP  at our own events        : {own.show()}")
print(f"  Vince RP  invited externally       : {ext.show()}")

print("\nStorage and calculator are working together. Database saved to css_is.db")
conn.close()
