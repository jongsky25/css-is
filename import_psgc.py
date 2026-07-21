"""
import_psgc.py  —  Load a PSA quarterly PSGC publication into css_is.db.

The PSA (Philippine Statistics Authority) republishes the Philippine Standard
Geographic Code every quarter. This CLI parses one such publication file and
loads it as a named *vintage* into the crosswalk tables (see psgc.py), so every
later geographic load can map its own vintage's codes onto our dim_geo.

IDEMPOTENT per vintage: re-running with the same --vintage first clears that
vintage's crosswalk rows, then reloads — so a corrected file cleanly replaces
the previous one. Canonical places from other vintages are never disturbed.

Usage:
    # Load the 2024 Q4 publication (label it however you reference that vintage)
    python import_psgc.py --file PSGC-2024Q4-Publication-Datafile.xlsx --vintage 2024Q4

    # A specific sheet, a publication date, and a CSV instead of xlsx all work:
    python import_psgc.py --file psgc.csv --vintage 2020Q3 --published 2020-09-30
    python import_psgc.py --file psgc.xlsx --vintage 2024Q4 --sheet "PSGC"

    # Inspect what is loaded:
    python import_psgc.py --list                     # loaded vintages + counts
    python import_psgc.py --resolve 1380700000 --vintage 2024Q4   # code -> geo_sk
"""
from __future__ import annotations

import argparse
import sys

import storage as st
import psgc
import tzutil as tz   # local (PH) wall-clock — never stamp with the server clock

DB = "css_is.db"


def _list(conn) -> None:
    rows = conn.execute(
        "SELECT vintage, published_on, code_digits, row_count, loaded_at, source "
        "FROM psgc_vintage ORDER BY vintage"
    ).fetchall()
    if not rows:
        print("No PSGC vintages loaded yet.")
        return
    print(f"{'VINTAGE':<10} {'PUBLISHED':<12} {'DIGITS':>6} {'ROWS':>8}  SOURCE")
    for v, pub, digits, n, _loaded, src in rows:
        print(f"{v:<10} {(pub or '—'):<12} {(digits or '?'):>6} {(n or 0):>8}  {src or ''}")
    total_geo = conn.execute("SELECT COUNT(*) FROM dim_geo").fetchone()[0]
    active_geo = conn.execute("SELECT COUNT(*) FROM dim_geo WHERE active=1").fetchone()[0]
    print(f"\ndim_geo: {total_geo} canonical places ({active_geo} active in the newest vintage).")


def _resolve(conn, code: str, vintage: str | None) -> None:
    sk = (psgc.resolve_geo(conn, vintage, code) if vintage
          else psgc.resolve_geo_any_vintage(conn, code))
    if sk is None:
        print(f"{code!r} — not found"
              + (f" in vintage {vintage}" if vintage else " in any loaded vintage"))
        return
    row = psgc.geo_row(conn, sk)
    print(f"{code} → geo_sk {sk}: [{row['level']}] {row['canonical_name']} "
          f"(canonical code {row['canonical_code']}, "
          f"vintages {row['first_vintage']}..{row['last_vintage']})")


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Load a PSA PSGC publication as a vintage.")
    ap.add_argument("--db", default=DB, help="SQLite database (default: css_is.db)")
    ap.add_argument("--file", help="PSGC publication file (.xlsx/.xls/.csv)")
    ap.add_argument("--vintage", help="Vintage label for this publication, e.g. 2024Q4")
    ap.add_argument("--sheet", default=0, help="Worksheet name/index (xlsx only)")
    ap.add_argument("--published", help="PSA publication date (YYYY-MM-DD), optional")
    ap.add_argument("--notes", help="Free-text note stored with the vintage")
    ap.add_argument("--list", action="store_true", help="List loaded vintages and stop")
    ap.add_argument("--resolve", metavar="CODE", help="Resolve a code to a geo_sk and stop")
    args = ap.parse_args(argv)

    conn = st.connect(args.db)
    st.init_db(conn)          # guarantees the crosswalk schema exists

    if args.list:
        _list(conn)
        return 0
    if args.resolve:
        _resolve(conn, args.resolve, args.vintage)
        return 0

    if not args.file or not args.vintage:
        ap.error("--file and --vintage are required to load a publication "
                 "(or use --list / --resolve).")

    try:
        sheet = int(args.sheet)
    except (TypeError, ValueError):
        sheet = args.sheet

    print(f"Parsing {args.file} …")
    rows = psgc.read_publication(args.file, sheet=sheet)
    print(f"  {len(rows)} rows parsed. Loading as vintage {args.vintage} …")
    stats = psgc.load_publication(
        conn, rows, args.vintage,
        published_on=args.published,
        source=args.file,
        loaded_at=tz.now_iso(),
        notes=args.notes,
    )
    print(
        "  Loaded {total} entities — "
        "{exact} matched by code, {correspondence} by correspondence code, "
        "{name_parent} by name+parent, {new} new places.".format(**stats)
    )
    _list(conn)
    return 0


if __name__ == "__main__":
    sys.exit(main())
