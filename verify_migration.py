import sys; sys.path.insert(0,'/sessions/hopeful-intelligent-hamilton/work')
import storage as st, css_is_engine as eng
DB=sys.argv[1] if len(sys.argv)>1 else '/tmp/css_test.db'
conn=st.connect(DB)
print("=== Referential integrity ===")
checks={
 "answers w/o response": "SELECT COUNT(*) FROM answer a LEFT JOIN response r ON r.id=a.response_id WHERE r.id IS NULL",
 "responses w/o form":   "SELECT COUNT(*) FROM response r LEFT JOIN form_instance f ON f.id=r.form_instance_id WHERE f.id IS NULL",
 "fi.rp_id dangling":    "SELECT COUNT(*) FROM form_instance f LEFT JOIN resource_person p ON p.id=f.rp_id WHERE f.rp_id IS NOT NULL AND p.id IS NULL",
 "response.served_by dangling":"SELECT COUNT(*) FROM response r LEFT JOIN resource_person p ON p.id=r.served_by_rp_id WHERE r.served_by_rp_id IS NOT NULL AND p.id IS NULL",
 "answer.value not null but is_na=1":"SELECT COUNT(*) FROM answer WHERE is_na=1 AND value IS NOT NULL",
 "duplicate qr_token":   "SELECT COUNT(*)-COUNT(DISTINCT qr_token) FROM form_instance",
}
ok=True
for name,q in checks.items():
    v=conn.execute(q).fetchone()[0]
    flag='' if v==0 else '  <-- PROBLEM'; ok = ok and v==0
    print(f"  {name:34} {v}{flag}")

print("\n=== MIG row counts by survey type ===")
for st_t in (1,2,3):
    fi=conn.execute("SELECT COUNT(*) FROM form_instance WHERE qr_token LIKE 'MIG-%' AND survey_type=?",(st_t,)).fetchone()[0]
    rs=conn.execute("SELECT COUNT(*) FROM response WHERE form_instance_id IN (SELECT id FROM form_instance WHERE qr_token LIKE 'MIG-%' AND survey_type=?)",(st_t,)).fetchone()[0]
    print(f"  type {st_t}: {fi} instances, {rs} responses")

print("\n=== load_atoms() + engine scoring ===")
atoms=st.load_atoms(conn)
print("  atoms rows:", len(atoms), "| unique responses:", atoms['response_id'].nunique())
print("  survey_type distribution:\n", atoms['survey_type'].value_counts().to_string().replace('\n','\n   '))
print("  item_id distinct:", sorted(atoms['item_id'].unique().tolist()))
print("  value range:", atoms['value'].min(), "->", atoms['value'].max())
print("  event_date range:", atoms['event_date'].min(), "->", atoms['event_date'].max())
print("  years present:", sorted(atoms['year'].dropna().unique().tolist()))

# Engine: overall perception for type 2 and type 3 (whole bureau)
ov2=eng.overall_perception(eng.scope(atoms, survey_type=2), eng.DIM_MAP_FORM2)
ov3=eng.overall_perception(eng.scope(atoms, survey_type=3), eng.DIM_MAP_FORM3)
print("  Type2 overall:", ov2.show())
print("  Type3 overall:", ov3.show())
osq2=eng.osq_C(eng.scope(atoms,survey_type=2)); print("  Type2 OSQ(C):", osq2.show(), "band:", eng.band(osq2.value,eng.OSQ_BANDS))

print("\n=== Spot-check: one F3 resource person end-to-end ===")
row=conn.execute("""SELECT p.id,p.name,COUNT(DISTINCT r.id)
   FROM resource_person p JOIN form_instance f ON f.rp_id=p.id
   JOIN response r ON r.form_instance_id=f.id
   WHERE f.qr_token LIKE 'MIG-%' GROUP BY p.id ORDER BY 3 DESC LIMIT 1""").fetchone()
print("  top RP:", row)
sub=atoms[(atoms['survey_type']==3) & (atoms['rp_id']==row[0])]
print("   their responses in atoms:", sub['response_id'].nunique(), "| overall:",
      eng.overall_perception(sub, eng.DIM_MAP_FORM3).show())
print("\nINTEGRITY:", "ALL OK" if ok else "PROBLEMS FOUND")
