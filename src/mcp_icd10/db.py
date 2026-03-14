"""Unified SQLite + FTS5 database for ICD-10-CM, ICD-9-CM, ICD-10 WHO, and GEMs crosswalk.

Ships a pre-built, gzipped SQLite database (~4.5MB). Decompresses on first run
into a ~21MB read-only DB. All queries use indexes or FTS5 — sub-millisecond.

Systems (integer IDs for compact storage):
  0 = icd10cm  ICD-10-CM FY2026 (98,186 codes incl. 74,719 billable)
  1 = icd9cm   ICD-9-CM (14,567 codes)
  2 = icd10who ICD-10 WHO 2019 (11,243 codes)

Crosswalk flags packed as bitmask:
  bit0=approximate, bit1=no_map, bit2=combination, bit3=scenario, bit4=choice_list
"""

import gzip
import shutil
import sqlite3
from pathlib import Path

_DATA_DIR = Path(__file__).parent / "data"
_DB_GZ = _DATA_DIR / "icd.db.gz"
_DB_PATH = _DATA_DIR / "icd.db"

_connection: sqlite3.Connection | None = None

# System name ↔ integer mapping
SYS_ID = {"icd10cm": 0, "icd9cm": 1, "icd10who": 2}
SYS_NAME = {0: "icd10cm", 1: "icd9cm", 2: "icd10who"}
SYSTEMS = tuple(SYS_ID.keys())

# Flag bit positions
FLAG_APPROXIMATE = 1
FLAG_NO_MAP = 2
FLAG_COMBINATION = 4

# Max rows FTS5 will rank before returning. Caps worst-case latency for broad
# single-word queries (e.g. 'fracture' → 21K matches) from ~11ms to <0.5ms.
# 500 is enough to surface the best BM25 results for LIMIT 20–50 queries.
_FTS_CAP = 500


def _unpack_flags(flags: int) -> dict:
    return {
        "approximate": bool(flags & FLAG_APPROXIMATE),
        "no_map": bool(flags & FLAG_NO_MAP),
        "combination": bool(flags & FLAG_COMBINATION),
    }


def get_connection() -> sqlite3.Connection:
    """Get or create the database connection. Decompresses DB on first run."""
    global _connection
    if _connection is not None:
        return _connection
    if not _DB_PATH.exists() and _DB_GZ.exists():
        with gzip.open(_DB_GZ, "rb") as f_in, open(_DB_PATH, "wb") as f_out:
            shutil.copyfileobj(f_in, f_out)
    _connection = sqlite3.connect(str(_DB_PATH), check_same_thread=False)
    _connection.row_factory = sqlite3.Row
    _connection.execute("PRAGMA query_only=ON")
    _connection.execute("PRAGMA mmap_size=268435456")  # 256MB mmap for speed
    return _connection


def lookup_code(code: str, system: str | None = None) -> dict | None:
    """Exact lookup. Returns first match or None."""
    conn = get_connection()
    clean = code.upper().strip().replace(".", "")
    if system:
        sid = SYS_ID.get(system)
        if sid is None:
            return None
        row = conn.execute(
            "SELECT code, description, sys, billable FROM codes WHERE sys=? AND code=?",
            (sid, clean),
        ).fetchone()
    else:
        row = conn.execute(
            "SELECT code, description, sys, billable FROM codes WHERE code=? ORDER BY sys",
            (clean,),
        ).fetchone()
    if not row:
        return None
    return {"code": row["code"], "description": row["description"],
            "system": SYS_NAME[row["sys"]], "billable": bool(row["billable"])}


def lookup_code_all_systems(code: str) -> list[dict]:
    """Look up a code across all systems."""
    conn = get_connection()
    clean = code.upper().strip().replace(".", "")
    rows = conn.execute(
        "SELECT code, description, sys, billable FROM codes WHERE code=? ORDER BY sys",
        (clean,),
    ).fetchall()
    return [{"code": r["code"], "description": r["description"],
             "system": SYS_NAME[r["sys"]], "billable": bool(r["billable"])} for r in rows]


def search_codes(query: str, system: str | None = None, limit: int = 20) -> list[dict]:
    """Full-text search. Optionally filter by system.

    Two-phase approach that avoids FTS5's full-scan ranking:
      1. Grab _FTS_CAP unranked candidates (FTS stops early at LIMIT — no scoring).
      2. Sort by description length (shorter = more specific = better relevance
         proxy for medical codes, and actually outperforms BM25 for broad terms).
    Keeps worst-case latency under 0.5ms even for 21K-match queries like 'fracture'.
    """
    conn = get_connection()
    if system:
        sid = SYS_ID.get(system)
        if sid is None:
            return []
        rows = conn.execute(
            """SELECT c.code, c.description, c.sys
               FROM codes_fts fts CROSS JOIN codes c ON c.rowid = fts.rowid
               WHERE codes_fts MATCH ? AND c.sys = ?
               LIMIT ?""",
            (query, sid, _FTS_CAP),
        ).fetchall()
    else:
        rows = conn.execute(
            """SELECT c.code, c.description, c.sys
               FROM codes_fts fts CROSS JOIN codes c ON c.rowid = fts.rowid
               WHERE codes_fts MATCH ?
               LIMIT ?""",
            (query, _FTS_CAP),
        ).fetchall()
    # Rank by description length — shorter descriptions are more specific/relevant
    rows = sorted(rows, key=lambda r: len(r["description"]))[:limit]
    return [{"code": r["code"], "description": r["description"],
             "system": SYS_NAME[r["sys"]]} for r in rows]


def browse_category(prefix: str, system: str = "icd10cm", limit: int = 50) -> list[dict]:
    """Browse codes by prefix within a system."""
    conn = get_connection()
    sid = SYS_ID.get(system)
    if sid is None:
        return []
    clean = prefix.upper().strip().replace(".", "")
    upper = clean[:-1] + chr(ord(clean[-1]) + 1) if clean else "Z" * 10
    rows = conn.execute(
        "SELECT code, description, sys, billable FROM codes "
        "WHERE sys=? AND code>=? AND code<? ORDER BY code LIMIT ?",
        (sid, clean, upper, limit),
    ).fetchall()
    return [{"code": r["code"], "description": r["description"],
             "system": SYS_NAME[r["sys"]], "billable": bool(r["billable"])} for r in rows]


def crosswalk(code: str, source_system: str | None = None) -> list[dict]:
    """Find crosswalk mappings for a code."""
    conn = get_connection()
    clean = code.upper().strip().replace(".", "")
    if source_system:
        sid = SYS_ID.get(source_system)
        if sid is None:
            return []
        rows = conn.execute(
            """SELECT cw.src_sys, cw.src_code, cw.tgt_sys, cw.tgt_code, cw.flags,
                      tc.description as tgt_desc
               FROM crosswalk cw
               LEFT JOIN codes tc ON tc.code = cw.tgt_code AND tc.sys = cw.tgt_sys
               WHERE cw.src_sys=? AND cw.src_code=?
               ORDER BY cw.flags, cw.tgt_code""",
            (sid, clean),
        ).fetchall()
    else:
        rows = conn.execute(
            """SELECT cw.src_sys, cw.src_code, cw.tgt_sys, cw.tgt_code, cw.flags,
                      tc.description as tgt_desc
               FROM crosswalk cw
               LEFT JOIN codes tc ON tc.code = cw.tgt_code AND tc.sys = cw.tgt_sys
               WHERE cw.src_code=?
               ORDER BY cw.src_sys, cw.flags, cw.tgt_code""",
            (clean,),
        ).fetchall()
    return [{"source_system": SYS_NAME[r["src_sys"]], "source_code": r["src_code"],
             "target_system": SYS_NAME[r["tgt_sys"]], "target_code": r["tgt_code"],
             "target_description": r["tgt_desc"] or "",
             **_unpack_flags(r["flags"])} for r in rows]


_stats_cache: dict | None = None


def get_stats() -> dict:
    """Database statistics per system. Cached after first call (data is static)."""
    global _stats_cache
    if _stats_cache is not None:
        return _stats_cache
    conn = get_connection()
    stats = {}
    for name, sid in SYS_ID.items():
        count = conn.execute("SELECT COUNT(*) FROM codes WHERE sys=?", (sid,)).fetchone()[0]
        stats[name] = count
    stats["crosswalk_mappings"] = conn.execute("SELECT COUNT(*) FROM crosswalk").fetchone()[0]
    stats["total_codes"] = sum(v for k, v in stats.items() if k != "crosswalk_mappings")
    _stats_cache = stats
    return stats
