"""
import_csm_blhsd.py  —  Load BLHSD CO-CSM walk-in data into css_is.db.

IDEMPOTENT: form_instances tagged with qr_token='CSM-BLHSD-IMPORT-YYYY-MM'.
Re-running purges all CSM-BLHSD-IMPORT-* data first, then reloads.

Usage:
    python import_csm_blhsd.py             # import
    python import_csm_blhsd.py --verify    # show current CSM-BLHSD counts
    python import_csm_blhsd.py --purge     # remove all CSM-BLHSD data and stop
"""
from __future__ import annotations
import sys, re, sqlite3, datetime
import pandas as pd
import storage as st

XLSX   = r"C:\Users\USER\Downloads\CENTRAL OFFICE - CLIENT SATISFACTION MEASUREMENT.xlsx"
SHEET  = "BLHSD"
DB     = "css_is.db"
TAG    = "CSM-BLHSD-IMPORT-"
BLHSD_ORG_ID = 1
SURVEY_TYPE  = 1
FORM_CODE    = "F1"

SQD_ITEMS = ["SQD0","SQD1","SQD2","SQD3","SQD4","SQD5","SQD6","SQD7","SQD8"]

# ── service name normalisations (all normalised to title-case canonical) ────────
SERVICE_NORM = {
    "technical assistance": "Technical Assistance",
    "techl assistance":     "Technical Assistance",
    "policy review":        "Policy Review",
    "inquiry on lgu-health score card": "Inquiry on LGU-Health Score Card",
    "inquiry":              "Inquiry",
    "interview/research":   "Interview/Research",
    "data request":         "Data Request",
    "meeting":              "Meeting",
}

def norm_service(raw):
    if pd.isna(raw):
        return None
    return SERVICE_NORM.get(str(raw).strip().lower(), str(raw).strip())


# ── date repair ─────────────────────────────────────────────────────────────────
def parse_date(raw, response_no: str):
    """Return ISO date string.  Falls back to YYYY-MM-01 derived from response_no."""
    if pd.notna(raw) and isinstance(raw, datetime.datetime):
        return raw.strftime("%Y-%m-%d")
    if isinstance(raw, str):
        cleaned = re.sub(r"/{2,}", "/", raw).strip()   # fix 11//12/2025
        for fmt in ("%m/%d/%Y", "%Y-%m-%d", "%d/%m/%Y"):
            try:
                return datetime.datetime.strptime(cleaned, fmt).strftime("%Y-%m-%d")
            except ValueError:
                pass
    # derive YYYY-MM from response_no  e.g. CSM-BLHSD-2025-11-062 → 2025-11
    m = re.search(r"CSM-BLHSD-(\d{4})-0*(\d+)-", str(response_no))
    if m:
        return f"{m.group(1)}-{int(m.group(2)):02d}-01"
    return None


# ── load & clean ────────────────────────────────────────────────────────────────
def load_blhsd():
    df = pd.read_excel(XLSX, sheet_name=SHEET, header=None)
    raw = df.iloc[4:, :27].copy()
    raw.columns = [
        "response_no","service_availed","type_of_service","client_type",
        "email","date","sex","age","region","_b1",
        "onsite_online","cc1","cc2","cc3","_b2",
        "sqd0","sqd1","sqd2","sqd3","sqd4","sqd5","sqd6","sqd7","sqd8",
        "_b3","suggestions","feedback_type",
    ]
    raw = raw[raw["response_no"].notna()].copy()

    raw["service_availed"]  = raw["service_availed"].apply(norm_service)
    raw["date_iso"]         = raw.apply(lambda r: parse_date(r["date"], r["response_no"]), axis=1)

    # age: coerce "none"/NaN → 0
    def clean_age(v):
        if pd.isna(v): return 0
        try: return int(float(v))
        except: return 0
    raw["age_int"] = raw["age"].apply(clean_age)

    # type_of_service: fill nulls → "External" (walk-in default)
    raw["type_of_service"] = raw["type_of_service"].fillna("External")

    # text fields — strip, replace NaN with ""
    for col in ["sex","region","onsite_online","cc1","cc2","cc3",
                "client_type","email","suggestions","feedback_type"]:
        raw[col] = raw[col].fillna("").astype(str).str.strip()

    # month key for form_instance grouping
    raw["month_key"] = raw["date_iso"].apply(
        lambda d: d[:7] if d else None   # "YYYY-MM"
    )

    return raw


# ── database helpers ─────────────────────────────────────────────────────────────
def get_conn():
    conn = sqlite3.connect(DB)
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def purge(conn):
    cur = conn.cursor()
    cur.execute("SELECT id FROM form_instance WHERE qr_token LIKE ?", (TAG + "%",))
    fi_ids = [r[0] for r in cur.fetchall()]
    if not fi_ids:
        print("Nothing to purge.")
        return
    placeholders = ",".join("?" * len(fi_ids))
    cur.execute(f"SELECT id FROM response WHERE form_instance_id IN ({placeholders})", fi_ids)
    resp_ids = [r[0] for r in cur.fetchall()]
    if resp_ids:
        rp = ",".join("?" * len(resp_ids))
        cur.execute(f"DELETE FROM answer       WHERE response_id IN ({rp})", resp_ids)
        cur.execute(f"DELETE FROM item_remark  WHERE response_id IN ({rp})", resp_ids)
        cur.execute(f"DELETE FROM response     WHERE id IN ({rp})", resp_ids)
    cur.execute(f"DELETE FROM form_instance WHERE id IN ({placeholders})", fi_ids)
    conn.commit()
    print(f"Purged {len(fi_ids)} form_instance(s), {len(resp_ids)} response(s).")


def verify(conn):
    cur = conn.cursor()
    cur.execute("SELECT COUNT(*) FROM form_instance WHERE qr_token LIKE ?", (TAG + "%",))
    fi = cur.fetchone()[0]
    cur.execute("""
        SELECT COUNT(*) FROM response r
        JOIN form_instance fi ON r.form_instance_id = fi.id
        WHERE fi.qr_token LIKE ?
    """, (TAG + "%",))
    resp = cur.fetchone()[0]
    cur.execute("""
        SELECT COUNT(*) FROM answer a
        JOIN response r ON a.response_id = r.id
        JOIN form_instance fi ON r.form_instance_id = fi.id
        WHERE fi.qr_token LIKE ?
    """, (TAG + "%",))
    ans = cur.fetchone()[0]
    print(f"CSM-BLHSD records:  form_instances={fi}  responses={resp}  answers={ans}")


# ── main import ──────────────────────────────────────────────────────────────────
def run_import():
    df = load_blhsd()
    conn = get_conn()
    now = datetime.datetime.utcnow().isoformat()

    purge(conn)     # idempotent: wipe then reload

    cur = conn.cursor()

    # ── create one form_instance per year-month ──────────────────────────────────
    month_to_fi = {}
    for mk in sorted(df["month_key"].dropna().unique()):
        year, mon = mk.split("-")
        token = f"{TAG}{mk}"
        event_date = f"{mk}-01"
        cur.execute("""
            INSERT INTO form_instance
                (survey_type, form, qr_token, event_date, lead_org_id, created_at)
            VALUES (?, ?, ?, ?, ?, ?)
        """, (SURVEY_TYPE, FORM_CODE, token, event_date, BLHSD_ORG_ID, now))
        month_to_fi[mk] = cur.lastrowid

    # handle rows whose date could not be parsed (month_key is None)
    null_mk_rows = df[df["month_key"].isna()]
    if len(null_mk_rows):
        token = f"{TAG}UNKNOWN"
        cur.execute("""
            INSERT INTO form_instance
                (survey_type, form, qr_token, event_date, lead_org_id, created_at)
            VALUES (?, ?, ?, NULL, ?, ?)
        """, (SURVEY_TYPE, FORM_CODE, token, BLHSD_ORG_ID, now))
        month_to_fi[None] = cur.lastrowid

    # ── insert responses, answers, item_remarks ──────────────────────────────────
    n_resp = 0
    n_ans  = 0
    n_rem  = 0

    for _, row in df.iterrows():
        fi_id = month_to_fi.get(row["month_key"])
        submitted_at = row["date_iso"] or now[:10]
        suggestions  = row["suggestions"] if row["suggestions"] else None

        cur.execute("""
            INSERT INTO response (form_instance_id, submitted_at, remarks)
            VALUES (?, ?, ?)
        """, (fi_id, submitted_at, suggestions))
        resp_id = cur.lastrowid
        n_resp += 1

        # SQD answers (numeric 1-5; null or 0 → is_na=1, value=0)
        for item in SQD_ITEMS:
            raw_val = row[item.lower()]
            if pd.isna(raw_val) or raw_val == 0:
                cur.execute(
                    "INSERT INTO answer (response_id, item_id, value, is_na) VALUES (?,?,?,1)",
                    (resp_id, item, 0)
                )
            else:
                cur.execute(
                    "INSERT INTO answer (response_id, item_id, value, is_na) VALUES (?,?,?,0)",
                    (resp_id, item, float(raw_val))
                )
            n_ans += 1

        # text metadata as item_remarks
        meta = {
            "RESPONSE_NO":       row["response_no"],
            "SERVICE":           row["service_availed"] or "",
            "TYPE_OF_SERVICE":   row["type_of_service"],
            "CLIENT_TYPE":       row["client_type"],
            "EMAIL":             row["email"],
            "SEX":               row["sex"],
            "AGE":               str(row["age_int"]),
            "REGION":            row["region"],
            "VERSION":           row["onsite_online"],
            "CC1":               row["cc1"],
            "CC2":               row["cc2"],
            "CC3":               row["cc3"],
            "FEEDBACK_TYPE":     row["feedback_type"],
        }
        for item_id, text in meta.items():
            cur.execute(
                "INSERT INTO item_remark (response_id, item_id, text) VALUES (?,?,?)",
                (resp_id, item_id, text or "")
            )
            n_rem += 1

    # ── audit log (hash-chained — never write prev/row_hash by hand) ──────────────
    st.audit(
        conn, "(import:csm_blhsd)", "bulk_import",
        target_type="form_instance", target_id="CSM-BLHSD",
        summary=(f"Imported {n_resp} BLHSD CO-CSM walk-in responses "
                 f"({len(month_to_fi)} monthly form_instances, {n_ans} answers, "
                 f"{n_rem} item_remarks)"),
    )

    conn.commit()
    conn.close()

    print(f"Import complete:")
    print(f"  form_instances : {len(month_to_fi)}")
    print(f"  responses      : {n_resp}")
    print(f"  answers        : {n_ans}")
    print(f"  item_remarks   : {n_rem}")


# ── entry point ──────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    if "--verify" in sys.argv:
        verify(get_conn())
    elif "--purge" in sys.argv:
        conn = get_conn()
        purge(conn)
        conn.close()
    else:
        run_import()
        verify(get_conn())
