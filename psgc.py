"""
psgc.py — PSGC crosswalk infrastructure (E4.1)
==============================================

The part that ANCHORS GEOGRAPHY IN TIME.

The Philippine Statistics Authority (PSA) publishes the **Philippine Standard
Geographic Code (PSGC)** every quarter. Between vintages the map moves:
provinces are created, municipalities become cities, barangays split or merge,
and — most disruptively — PSA has renumbered codes wholesale (the legacy
9-digit codes were replaced by 10-digit codes in the 2019 3rd-quarter
publication). A code that meant "Cotabato City" in one file can be absent,
reassigned, or reparented in the next.

So a raw PSGC code is only meaningful *within its own vintage*. Any dataset we
ingest later — CSM rosters, respondent addresses, DOH facility masterlists —
carries codes from whatever PSGC vintage was current when it was encoded. If we
joined those codes to each other directly, we would silently mismatch places
across vintages.

This module builds the bridge that makes those joins safe:

  * ``dim_geo`` — one row per **canonical place**, identified by a stable
    surrogate key (``geo_sk``) that we mint once and never change. This is the
    identity every downstream fact table points at.

  * ``dim_psgc_crosswalk`` — one row per **(vintage, published code)**, each
    carrying the ``geo_sk`` of the canonical place it denotes. This is the
    lookup: *"in vintage 2024Q4, code 1380700000 → geo_sk 42"*.

  * ``psgc_vintage`` — the registry of loaded publications (label, publication
    date, row counts), so we know what we hold and can reload deterministically.

The public contract every later load depends on is one function::

    resolve_geo(conn, vintage, code) -> geo_sk | None

Give it a code and the vintage that code came from, and it hands back the
stable ``geo_sk``. That is the whole point of E4.1: it is loaded FIRST, and
everything downstream maps its own vintage's codes onto our ``dim_geo`` through
it.

Design notes
------------
* **Boundary-free hierarchy.** PSA has used both 9- and 10-digit codes, and the
  internal segment widths (how many digits the province vs. city segment takes)
  have changed. Rather than hard-code segment boundaries, we exploit the one
  invariant that has held across every format: **an ancestor's significant
  digits (its code with trailing zeros removed) are a prefix of every
  descendant's code.** Region ``1300000000`` → "13" is a prefix of district
  ``1339000000`` → "1339" is a prefix of city ``1339020000`` → "133902" is a
  prefix of barangay ``1339020001``. So a place's parent is simply the loaded
  entity, one tier up, whose stripped code is the longest proper prefix of this
  code. No segment arithmetic required.

* **Resolution ladder.** When a publication row is loaded we decide which
  canonical place it is, in this order (most to least certain):
    1. Exact code already seen in an earlier vintage  → same place.
    2. PSA "correspondence code" links to a code we know → same place
       (this bridges the 9→10-digit renumbering, which PSA itself documents).
    3. Same level + same resolved parent + same normalized name → same place
       (a pure recode with no other change).
    4. Otherwise it is a NEW place and gets a fresh ``geo_sk``.
  Each crosswalk row records which rung matched (``match_method``) so the
  linkage is auditable, never a black box.

* **Self-contained.** This module owns its own schema (``ensure_schema``) and
  does not import ``storage``; ``storage.init_db`` calls into it so a normal
  database gets the tables. pandas is imported lazily (only the .xlsx/.csv
  parser needs it), so ``ensure_schema``/``resolve_geo`` work with nothing but
  the standard library.
"""
from __future__ import annotations

import re
import sqlite3
import unicodedata
from typing import Iterable, Optional


# ---------------------------------------------------------------------
# Geographic levels
# ---------------------------------------------------------------------
# PSA's "Geographic Level" column uses these short tokens. We keep them verbatim
# as the source of truth for a row's level (the positional code only *confirms*
# it) and rank them coarse→fine so we can find "the tier just above" a place.
LEVEL_REGION       = "Reg"
LEVEL_PROVINCE     = "Prov"
LEVEL_DISTRICT     = "Dist"     # NCR is split into districts, not provinces
LEVEL_CITY         = "City"
LEVEL_MUNICIPALITY = "Mun"
LEVEL_SUBMUN       = "SubMun"   # sub-municipalities (Manila's Tondo I/II, etc.)
LEVEL_BARANGAY     = "Bgy"

# Coarse (0) → fine (n). District sits at the province tier; sub-municipality
# sits just below city/municipality. Two entries can share a rank when they are
# alternatives at the same tier (City vs Mun, Prov vs Dist).
LEVEL_RANK = {
    LEVEL_REGION:       0,
    LEVEL_PROVINCE:     1,
    LEVEL_DISTRICT:     1,
    LEVEL_CITY:         2,
    LEVEL_MUNICIPALITY: 2,
    LEVEL_SUBMUN:       3,
    LEVEL_BARANGAY:     4,
}

# Tolerant mapping of the many spellings PSA (and hand-made extracts) use for
# the level column onto our canonical tokens.
_LEVEL_ALIASES = {
    "reg": LEVEL_REGION, "region": LEVEL_REGION,
    "prov": LEVEL_PROVINCE, "province": LEVEL_PROVINCE,
    "dist": LEVEL_DISTRICT, "district": LEVEL_DISTRICT,
    "city": LEVEL_CITY,
    "mun": LEVEL_MUNICIPALITY, "municipality": LEVEL_MUNICIPALITY,
    "submun": LEVEL_SUBMUN, "sub-mun": LEVEL_SUBMUN,
    "submunicipality": LEVEL_SUBMUN, "sub-municipality": LEVEL_SUBMUN,
    "bgy": LEVEL_BARANGAY, "brgy": LEVEL_BARANGAY,
    "barangay": LEVEL_BARANGAY, "bgy.": LEVEL_BARANGAY,
}


def normalize_level(raw: object) -> Optional[str]:
    """Map a free-text geographic-level value onto a canonical LEVEL_* token.

    Returns None when the value is blank or unrecognised (the loader treats an
    unrecognised level as "derive it positionally" rather than guessing).
    """
    if raw is None:
        return None
    key = re.sub(r"[^a-z-]", "", str(raw).strip().lower())
    return _LEVEL_ALIASES.get(key)


# ---------------------------------------------------------------------
# Code helpers (boundary-free)
# ---------------------------------------------------------------------
def clean_code(raw: object) -> Optional[str]:
    """Normalise a PSGC code to a digit string.

    PSA files variously store the code as a string, or as a float when a
    numeric cell was read ("1380700000.0"). We keep only the digits and return
    them verbatim — we never guess-pad, because padding the wrong side would
    change the place a code denotes. (The parser reads with ``dtype=str`` so
    genuine leading zeros survive; callers passing an int-derived code must
    preserve their own leading zeros, since matching is exact.)
    """
    if raw is None:
        return None
    s = str(raw).strip()
    if not s:
        return None
    if re.fullmatch(r"\d+\.0+", s):   # a numeric cell pandas rendered as float
        s = s.split(".")[0]
    digits = re.sub(r"\D", "", s)
    return digits or None


def _sig(code: str) -> str:
    """The 'significant' code: trailing zeros removed.

    This is the prefix an ancestor contributes to all its descendants. Region
    "1300000000" -> "13"; province "0340000000" -> "034". A code that is all
    zeros (should never happen for a real place) collapses to "" and can parent
    nothing, which is the safe outcome.
    """
    return code.rstrip("0")


def is_ancestor_code(ancestor: str, descendant: str) -> bool:
    """True when `ancestor` encloses `descendant` in the PSGC hierarchy.

    Boundary-free: holds for 9- and 10-digit codes alike because an ancestor's
    significant digits always prefix its descendants' codes. A code is never its
    own ancestor.
    """
    a = _sig(ancestor)
    if not a or ancestor == descendant:
        return False
    return descendant.startswith(a)


# ---------------------------------------------------------------------
# Name normalisation (for the name+parent resolution rung)
# ---------------------------------------------------------------------
_CITY_WORDS = re.compile(r"\b(city|municipality|of)\b")
_PAREN = re.compile(r"\([^)]*\)")

# Abbreviations PSA (and encoders) use interchangeably with their long forms.
# Expanded token-by-token so "Sto. Niño" and "Santo Nino" fold to one key — a
# common shape when a barangay is recoded and only the spelling differs.
_ABBREV = {
    "sto": "santo", "sta": "santa", "sn": "san",
    "gen": "general", "pob": "poblacion", "mt": "mount",
}


def normalize_name(raw: object) -> str:
    """Fold a place name to a comparison key.

    Lowercases, drops parenthetical notes ("Bacoor (Capital)"), collapses the
    filler words "City"/"Municipality"/"of", expands common abbreviations
    (Sto.→Santo, Sta.→Santa …), and strips punctuation/whitespace runs. Used
    only to decide "is this the same place under the same parent after a
    recode?" — never for display.
    """
    if raw is None:
        return ""
    s = str(raw).strip().lower()
    # Fold accents first so "Niño"→"nino" (ñ→n), not "ni o": decompose to base
    # letters + combining marks, then drop the marks. Ubiquitous in PH names.
    s = "".join(ch for ch in unicodedata.normalize("NFKD", s)
                if not unicodedata.combining(ch))
    s = _PAREN.sub(" ", s)
    s = _CITY_WORDS.sub(" ", s)
    s = re.sub(r"[^a-z0-9 ]", " ", s)
    tokens = [_ABBREV.get(t, t) for t in s.split()]
    return " ".join(tokens)


# ---------------------------------------------------------------------
# Schema
# ---------------------------------------------------------------------
def ensure_schema(conn: sqlite3.Connection) -> None:
    """Create the PSGC dimension tables. Idempotent (safe to re-run).

    Called by storage.init_db so any database — fresh or migrated — carries the
    crosswalk tables. Also callable standalone (loaders/tests open their own
    connection).
    """
    conn.executescript(
        """
        -- Loaded PSGC publications. One row per quarterly datafile we ingest.
        CREATE TABLE IF NOT EXISTS psgc_vintage (
            vintage      TEXT PRIMARY KEY,   -- our label, e.g. '2024Q4'
            published_on TEXT,               -- PSA publication date (YYYY-MM-DD), if known
            source       TEXT,               -- filename / URL the rows came from
            code_digits  INTEGER,            -- dominant code width in this file (9 or 10)
            row_count    INTEGER,            -- entities loaded from this vintage
            loaded_at    TEXT,               -- when we ingested it (caller-supplied ISO ts)
            notes        TEXT
        );

        -- Canonical places: stable identity across every vintage. geo_sk is the
        -- key downstream fact tables point at; it is minted once and never
        -- reused. canonical_code/canonical_name track the *latest* vintage that
        -- described the place, so joins to "current" PSGC are trivial.
        CREATE TABLE IF NOT EXISTS dim_geo (
            geo_sk          INTEGER PRIMARY KEY,          -- our surrogate key
            level           TEXT NOT NULL,                -- LEVEL_* token
            canonical_code  TEXT,                         -- code in the newest vintage seen
            canonical_name  TEXT,                         -- name in the newest vintage seen
            parent_geo_sk   INTEGER REFERENCES dim_geo(geo_sk),
            region_geo_sk   INTEGER REFERENCES dim_geo(geo_sk),   -- denormalised ancestry
            province_geo_sk INTEGER REFERENCES dim_geo(geo_sk),   -- (Prov or Dist tier)
            citymun_geo_sk  INTEGER REFERENCES dim_geo(geo_sk),
            first_vintage   TEXT,                         -- vintage we first saw the place
            last_vintage    TEXT,                         -- most recent vintage describing it
            active          INTEGER NOT NULL DEFAULT 1    -- 1 while present in last_vintage
        );

        -- The bridge: every published code, in every vintage, → its geo_sk.
        -- (vintage, psgc_code) is unique; that pair is what resolve_geo() keys on.
        CREATE TABLE IF NOT EXISTS dim_psgc_crosswalk (
            id                  INTEGER PRIMARY KEY,
            vintage             TEXT NOT NULL REFERENCES psgc_vintage(vintage),
            psgc_code           TEXT NOT NULL,            -- code as published in this vintage
            correspondence_code TEXT,                     -- PSA's link to the legacy/old code
            level               TEXT NOT NULL,            -- LEVEL_* token as published
            name                TEXT,                     -- name as published
            geo_sk              INTEGER NOT NULL REFERENCES dim_geo(geo_sk),
            parent_code         TEXT,                     -- resolved parent's code (this vintage)
            match_method        TEXT,                     -- which resolution rung linked it
            match_confidence    REAL,                     -- 1.0 exact … lower for fuzzier rungs
            UNIQUE (vintage, psgc_code)
        );

        CREATE INDEX IF NOT EXISTS ix_xwalk_code  ON dim_psgc_crosswalk(psgc_code);
        CREATE INDEX IF NOT EXISTS ix_xwalk_geo   ON dim_psgc_crosswalk(geo_sk);
        CREATE INDEX IF NOT EXISTS ix_xwalk_corr  ON dim_psgc_crosswalk(correspondence_code);
        CREATE INDEX IF NOT EXISTS ix_geo_code    ON dim_geo(canonical_code);
        CREATE INDEX IF NOT EXISTS ix_geo_parent  ON dim_geo(parent_geo_sk);
        """
    )


# ---------------------------------------------------------------------
# The public contract
# ---------------------------------------------------------------------
def resolve_geo(conn: sqlite3.Connection, vintage: str, code: object) -> Optional[int]:
    """Map a (vintage, published code) to its stable canonical ``geo_sk``.

    THIS is what every downstream load calls: it holds codes from whatever PSGC
    vintage it was encoded in, and this returns the vintage-independent identity
    to join on. Returns None when the code is not present in that vintage's
    crosswalk (unknown code / typo / un-loaded vintage) — callers decide whether that is a
    reject or a to-review row.
    """
    c = clean_code(code)
    if not c:
        return None
    row = conn.execute(
        "SELECT geo_sk FROM dim_psgc_crosswalk WHERE vintage=? AND psgc_code=?",
        (vintage, c),
    ).fetchone()
    return int(row[0]) if row else None


def resolve_geo_any_vintage(conn: sqlite3.Connection, code: object) -> Optional[int]:
    """Best-effort resolve when the caller does NOT know its data's vintage.

    Prefers the most recent vintage that published the code. Less safe than
    :func:`resolve_geo` (a code reused for a different place across a renumber
    would resolve to the newer meaning), so it is a fallback, not the contract.
    """
    c = clean_code(code)
    if not c:
        return None
    row = conn.execute(
        "SELECT geo_sk FROM dim_psgc_crosswalk WHERE psgc_code=? "
        "ORDER BY vintage DESC LIMIT 1",
        (c,),
    ).fetchone()
    return int(row[0]) if row else None


def geo_row(conn: sqlite3.Connection, geo_sk: int) -> Optional[sqlite3.Row]:
    """Fetch a canonical place by surrogate key (as a Row; None if absent)."""
    cur = conn.execute(
        "SELECT geo_sk, level, canonical_code, canonical_name, parent_geo_sk, "
        "region_geo_sk, province_geo_sk, citymun_geo_sk, first_vintage, "
        "last_vintage, active FROM dim_geo WHERE geo_sk=?",
        (int(geo_sk),),
    )
    cur.row_factory = sqlite3.Row
    return cur.fetchone()


def current_code(conn: sqlite3.Connection, geo_sk: int) -> Optional[str]:
    """The place's code in the most recent vintage that described it."""
    row = conn.execute(
        "SELECT canonical_code FROM dim_geo WHERE geo_sk=?", (int(geo_sk),)
    ).fetchone()
    return row[0] if row else None


# ---------------------------------------------------------------------
# Loading a publication
# ---------------------------------------------------------------------
class PublicationRow:
    """One normalised entity from a PSGC publication, ready to load.

    The parser (:func:`read_publication`) produces these; the loader
    (:func:`load_publication`) consumes them. Keeping this a plain object (not a
    dict) makes the resolution code below read as prose.
    """

    __slots__ = ("code", "name", "level", "correspondence_code", "raw")

    def __init__(self, code, name, level, correspondence_code=None, raw=None):
        self.code = clean_code(code)
        self.name = None if name is None else str(name).strip()
        self.level = level                      # already a canonical LEVEL_* token or None
        self.correspondence_code = clean_code(correspondence_code)
        self.raw = raw or {}

    def __repr__(self):
        return f"PublicationRow({self.code!r}, {self.name!r}, {self.level!r})"


def _derive_level(code: str, others_by_code: dict) -> Optional[str]:
    """Positional fallback for a row whose level column was missing/garbled.

    We can't rely on absolute segment widths, but we CAN rank a place by how
    deep it sits: count how many loaded codes are its strict ancestors. Depth 0
    = region, 1 = province/district tier, and so on. Barangays (the leaves) are
    whatever is left. This only runs when the file didn't tell us the level.
    """
    depth = sum(1 for oc in others_by_code if is_ancestor_code(oc, code) and oc != code)
    by_depth = {0: LEVEL_REGION, 1: LEVEL_PROVINCE, 2: LEVEL_CITY, 3: LEVEL_SUBMUN}
    return by_depth.get(depth, LEVEL_BARANGAY)


def _find_parent_sk(code: str, level: str, code_to_sk: dict, code_to_level: dict):
    """Resolve the immediate parent's geo_sk within a single publication.

    The parent is the loaded place, of a strictly-coarser tier, whose stripped
    code is the LONGEST proper prefix of this code. Longest-prefix naturally
    yields the immediate parent (a barangay's city, not its region), and the
    tier check stops a place from parenting a same-tier sibling that happens to
    share a prefix.
    """
    my_rank = LEVEL_RANK.get(level, 99)
    best_sk = None
    best_len = -1
    for oc, sk in code_to_sk.items():
        if oc == code:
            continue
        if LEVEL_RANK.get(code_to_level.get(oc, ""), 99) >= my_rank:
            continue                       # parent must be strictly coarser
        if is_ancestor_code(oc, code):
            slen = len(_sig(oc))
            if slen > best_len:
                best_len, best_sk = slen, sk
    return best_sk


def load_publication(
    conn: sqlite3.Connection,
    rows: Iterable[PublicationRow],
    vintage: str,
    *,
    published_on: Optional[str] = None,
    source: Optional[str] = None,
    loaded_at: Optional[str] = None,
    notes: Optional[str] = None,
) -> dict:
    """Load one PSGC publication into ``dim_geo`` + ``dim_psgc_crosswalk``.

    IDEMPOTENT per vintage: re-loading the same ``vintage`` first deletes that
    vintage's crosswalk rows, so a corrected file cleanly replaces the old one.
    Canonical places from OTHER vintages are never deleted (that would orphan
    downstream facts); a reload simply re-points this vintage's codes.

    Resolution ladder per row (see module docstring): exact prior code →
    correspondence code → name+parent → new place. Returns a summary dict
    (counts per rung) for the caller/CLI to report.

    ``loaded_at`` is caller-supplied (an ISO timestamp) so this stays pure and
    deterministic — the module never reads the wall clock itself.
    """
    ensure_schema(conn)
    rows = [r for r in rows if r and r.code]

    # Clear any prior load of THIS vintage (idempotent reload).
    conn.execute("DELETE FROM dim_psgc_crosswalk WHERE vintage=?", (vintage,))
    # Register the vintage BEFORE inserting crosswalk rows: the crosswalk's FK
    # points at psgc_vintage, so the parent row must exist first. Counts are
    # filled in at the end (the final upsert below overwrites this stub).
    conn.execute(
        "INSERT INTO psgc_vintage (vintage, loaded_at) VALUES (?, ?) "
        "ON CONFLICT(vintage) DO UPDATE SET loaded_at=excluded.loaded_at",
        (vintage, loaded_at),
    )

    # Load coarse→fine so a child's parent already has a geo_sk when we reach it.
    def _rank(r):
        return LEVEL_RANK.get(r.level, 99)
    # First pass: make sure every row has a level (fill gaps positionally).
    all_codes = {r.code for r in rows}
    for r in rows:
        r.level = normalize_level(r.level) or r.level
        if r.level not in LEVEL_RANK:
            r.level = _derive_level(r.code, all_codes)
    rows.sort(key=lambda r: (_rank(r), len(r.code)))

    code_to_sk: dict = {}      # code (this vintage) -> geo_sk, filled as we go
    code_to_level: dict = {}
    used_sks: set = set()      # geo_sks already claimed by THIS vintage's rows
    stats = {"exact": 0, "correspondence": 0, "name_parent": 0, "new": 0, "total": 0}

    def _new_geo_sk() -> int:
        row = conn.execute("SELECT COALESCE(MAX(geo_sk), 0) + 1 FROM dim_geo").fetchone()
        return int(row[0])

    for r in rows:
        parent_sk = _find_parent_sk(r.code, r.level, code_to_sk, code_to_level)

        geo_sk = None
        method = None
        confidence = 1.0

        # Rung 1 — exact code seen in an earlier vintage.
        hit = conn.execute(
            "SELECT geo_sk FROM dim_psgc_crosswalk WHERE psgc_code=? AND vintage<>? "
            "ORDER BY vintage DESC LIMIT 1",
            (r.code, vintage),
        ).fetchone()
        if hit:
            geo_sk, method = int(hit[0]), "exact"

        # Rung 2 — PSA correspondence code links this to a code we already know.
        if geo_sk is None and r.correspondence_code:
            hit = conn.execute(
                "SELECT geo_sk FROM dim_psgc_crosswalk "
                "WHERE (psgc_code=? OR correspondence_code=?) AND vintage<>? "
                "ORDER BY vintage DESC LIMIT 1",
                (r.correspondence_code, r.correspondence_code, vintage),
            ).fetchone()
            if hit:
                geo_sk, method, confidence = int(hit[0]), "correspondence", 0.95

        # Rung 3 — same level + same resolved parent + same normalized name.
        if geo_sk is None and r.name:
            nkey = normalize_name(r.name)
            if nkey:
                if parent_sk is None:
                    cand = conn.execute(
                        "SELECT geo_sk, canonical_name FROM dim_geo "
                        "WHERE level=? AND parent_geo_sk IS NULL",
                        (r.level,),
                    ).fetchall()
                else:
                    cand = conn.execute(
                        "SELECT geo_sk, canonical_name FROM dim_geo "
                        "WHERE level=? AND parent_geo_sk=?",
                        (r.level, parent_sk),
                    ).fetchall()
                for sk, cname in cand:
                    # Never collapse into a place another row of THIS SAME
                    # vintage already claimed — two distinct same-named
                    # barangays under one city are different places.
                    if int(sk) in used_sks:
                        continue
                    if normalize_name(cname) == nkey:
                        geo_sk, method, confidence = int(sk), "name_parent", 0.80
                        break

        # Rung 4 — a genuinely new place.
        if geo_sk is None:
            geo_sk = _new_geo_sk()
            method, confidence = "new", 1.0
            conn.execute(
                "INSERT INTO dim_geo (geo_sk, level, canonical_code, canonical_name, "
                "parent_geo_sk, first_vintage, last_vintage, active) "
                "VALUES (?,?,?,?,?,?,?,1)",
                (geo_sk, r.level, r.code, r.name, parent_sk, vintage, vintage),
            )
        else:
            # Known place: refresh its "latest vintage" view and (re)parent it.
            conn.execute(
                "UPDATE dim_geo SET canonical_code=?, canonical_name=?, level=?, "
                "parent_geo_sk=COALESCE(?, parent_geo_sk), last_vintage=?, active=1 "
                "WHERE geo_sk=?",
                (r.code, r.name, r.level, parent_sk, vintage, geo_sk),
            )

        stats[method] += 1
        stats["total"] += 1
        code_to_sk[r.code] = geo_sk
        code_to_level[r.code] = r.level
        used_sks.add(geo_sk)

        parent_code = None
        if parent_sk is not None:
            for oc, sk in code_to_sk.items():
                if sk == parent_sk:
                    parent_code = oc
                    break

        conn.execute(
            "INSERT INTO dim_psgc_crosswalk (vintage, psgc_code, correspondence_code, "
            "level, name, geo_sk, parent_code, match_method, match_confidence) "
            "VALUES (?,?,?,?,?,?,?,?,?)",
            (vintage, r.code, r.correspondence_code, r.level, r.name, geo_sk,
             parent_code, method, confidence),
        )

    # Fill denormalised ancestry (region/province/citymun) for every place this
    # vintage touched, by walking resolved parent chains. Done after the main
    # pass so every parent_geo_sk is final.
    _backfill_ancestry(conn, set(code_to_sk.values()))

    # Mark places that DID NOT appear in this vintage inactive *iff* this is the
    # newest vintage (an older reload must not deactivate current places).
    newest = conn.execute("SELECT MAX(vintage) FROM psgc_vintage").fetchone()[0]
    if newest is None or vintage >= newest:
        present = tuple(code_to_sk.values()) or (-1,)
        qmarks = ",".join("?" * len(present))
        conn.execute(
            f"UPDATE dim_geo SET active=0 WHERE geo_sk NOT IN ({qmarks})", present
        )

    code_digits = _dominant_width([r.code for r in rows])
    conn.execute(
        "INSERT INTO psgc_vintage (vintage, published_on, source, code_digits, "
        "row_count, loaded_at, notes) VALUES (?,?,?,?,?,?,?) "
        "ON CONFLICT(vintage) DO UPDATE SET published_on=excluded.published_on, "
        "source=excluded.source, code_digits=excluded.code_digits, "
        "row_count=excluded.row_count, loaded_at=excluded.loaded_at, notes=excluded.notes",
        (vintage, published_on, source, code_digits, stats["total"], loaded_at, notes),
    )
    conn.commit()
    return stats


def _backfill_ancestry(conn: sqlite3.Connection, geo_sks: set) -> None:
    """Populate region/province/citymun surrogate keys by walking parent chains."""
    for sk in geo_sks:
        region = province = citymun = None
        cur = sk
        seen = set()
        while cur is not None and cur not in seen:
            seen.add(cur)
            row = conn.execute(
                "SELECT level, parent_geo_sk FROM dim_geo WHERE geo_sk=?", (cur,)
            ).fetchone()
            if not row:
                break
            level, parent = row
            if level == LEVEL_REGION:
                region = cur
            elif level in (LEVEL_PROVINCE, LEVEL_DISTRICT):
                province = cur
            elif level in (LEVEL_CITY, LEVEL_MUNICIPALITY):
                citymun = cur
            cur = parent
        conn.execute(
            "UPDATE dim_geo SET region_geo_sk=?, province_geo_sk=?, citymun_geo_sk=? "
            "WHERE geo_sk=?",
            (region, province, citymun, sk),
        )


def _dominant_width(codes) -> Optional[int]:
    """Most common code length in a batch — recorded per vintage (9 vs 10)."""
    counts: dict = {}
    for c in codes:
        if c:
            counts[len(c)] = counts.get(len(c), 0) + 1
    if not counts:
        return None
    return max(counts, key=counts.get)


# ---------------------------------------------------------------------
# Publication file parser (pandas — imported lazily)
# ---------------------------------------------------------------------
# PSA's published datafile is an .xlsx whose columns have varied in spelling and
# order across the years. We detect columns by fuzzy header match rather than by
# position, so a 2020 file and a 2025 file both parse.
_COL_PATTERNS = {
    "code":  [r"^10.?digit", r"psgc.*code", r"^psgc$", r"^code$"],
    "name":  [r"^name$", r"geographic.*name", r"^location$"],
    "level": [r"geographic.*level", r"^level$", r"inter.?level", r"^glevel$"],
    "corr":  [r"correspondence", r"^old.*code", r"^9.?digit", r"legacy.*code"],
}


def _match_column(columns, patterns) -> Optional[str]:
    for col in columns:
        h = str(col).strip().lower()
        for pat in patterns:
            if re.search(pat, h):
                return col
    return None


def read_publication(path: str, *, sheet: object = 0) -> list:
    """Parse a PSA PSGC publication file into ``PublicationRow`` objects.

    Accepts .xlsx/.xls (via openpyxl/pandas) or .csv. Columns are detected by
    header pattern, so files whose column order or exact wording differ across
    vintages still parse. Rows without a usable code are skipped.
    """
    import pandas as pd

    if str(path).lower().endswith(".csv"):
        df = pd.read_csv(path, dtype=str, keep_default_na=False)
    else:
        df = pd.read_excel(path, sheet_name=sheet, dtype=str)
    df.columns = [str(c).strip() for c in df.columns]

    code_col = _match_column(df.columns, _COL_PATTERNS["code"])
    name_col = _match_column(df.columns, _COL_PATTERNS["name"])
    level_col = _match_column(df.columns, _COL_PATTERNS["level"])
    corr_col = _match_column(df.columns, _COL_PATTERNS["corr"])
    if not code_col:
        raise ValueError(
            "Could not find a PSGC code column in "
            f"{list(df.columns)!r} — expected a header like '10-digit PSGC Code'."
        )

    out = []
    for _, r in df.iterrows():
        out.append(
            PublicationRow(
                code=r.get(code_col),
                name=r.get(name_col) if name_col else None,
                level=normalize_level(r.get(level_col)) if level_col else None,
                correspondence_code=r.get(corr_col) if corr_col else None,
                raw={c: r.get(c) for c in df.columns},
            )
        )
    return out
