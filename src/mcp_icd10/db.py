"""SQLite + FTS5 database for ICD-10-CM codes.

Ships a gzipped CSV (~0.7MB) and builds a local SQLite database with
full-text search on first run. Subsequent runs use the cached DB.
"""

import csv
import gzip
import sqlite3
from pathlib import Path

_DATA_DIR = Path(__file__).parent / "data"
_CSV_GZ = _DATA_DIR / "icd10cm.csv.gz"
_DB_PATH = _DATA_DIR / "icd10cm.db"

_connection: sqlite3.Connection | None = None


def _parse_description(raw: str) -> tuple[str, str]:
    """Parse enhanced description into (category_desc, description).

    Input format: "Header: A00 - Cholera | Specific long description about this code: ..."
    Note: The header field from the source CSV can be inaccurate (it tracks the
    last sequential header, not the true parent). We extract the category from
    the code itself for reliability, but keep the header description for search.
    """
    if " | Specific long description about this code: " in raw:
        header_part, desc = raw.split(" | Specific long description about this code: ", 1)
        header_part = header_part.removeprefix("Header: ")
        if " - " in header_part:
            _, cat_desc = header_part.split(" - ", 1)
        else:
            cat_desc = header_part
    else:
        cat_desc, desc = "", raw
    return cat_desc.strip(), desc.strip()


def _build_db() -> None:
    """Build SQLite database with FTS5 index from compressed CSV."""
    conn = sqlite3.connect(str(_DB_PATH))
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA synchronous=NORMAL")

    conn.executescript("""
        CREATE TABLE IF NOT EXISTS codes (
            code TEXT PRIMARY KEY,
            description TEXT NOT NULL,
            category_code TEXT NOT NULL,
            category_description TEXT NOT NULL
        );
        CREATE VIRTUAL TABLE IF NOT EXISTS codes_fts USING fts5(
            code, description, category_description,
            content='codes', content_rowid='rowid',
            tokenize='porter unicode61'
        );
    """)

    with gzip.open(_CSV_GZ, "rt", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        rows = []
        for row in reader:
            cat_desc, desc = _parse_description(row["description"])
            code = row["code"]
            # Derive category from code: first 3 chars (e.g., E11 from E119)
            cat_code = code[:3] if len(code) >= 3 else code
            rows.append((code, desc, cat_code, cat_desc))

    conn.executemany(
        "INSERT OR REPLACE INTO codes VALUES (?, ?, ?, ?)", rows
    )
    conn.execute("CREATE INDEX IF NOT EXISTS idx_category ON codes(category_code)")
    # Populate FTS index
    conn.execute("""
        INSERT INTO codes_fts(codes_fts) VALUES('rebuild')
    """)
    conn.commit()
    conn.close()


def get_connection() -> sqlite3.Connection:
    """Get or create the database connection."""
    global _connection
    if _connection is not None:
        return _connection

    if not _DB_PATH.exists():
        _build_db()

    _connection = sqlite3.connect(str(_DB_PATH), check_same_thread=False)
    _connection.row_factory = sqlite3.Row
    _connection.execute("PRAGMA query_only=ON")
    return _connection


def lookup_code(code: str) -> dict | None:
    """Exact lookup by ICD-10-CM code. Returns None if not found."""
    conn = get_connection()
    row = conn.execute(
        "SELECT code, description, category_code, category_description FROM codes WHERE code = ?",
        (code.upper().strip().replace(".", ""),),
    ).fetchone()
    return dict(row) if row else None


def search_codes(query: str, limit: int = 20) -> list[dict]:
    """Full-text search across descriptions. Returns ranked results."""
    conn = get_connection()
    # Use FTS5 match with BM25 ranking
    rows = conn.execute(
        """
        SELECT c.code, c.description, c.category_code, c.category_description,
               rank
        FROM codes_fts fts
        JOIN codes c ON c.rowid = fts.rowid
        WHERE codes_fts MATCH ?
        ORDER BY rank
        LIMIT ?
        """,
        (query, limit),
    ).fetchall()
    return [dict(r) for r in rows]


def browse_category(prefix: str, limit: int = 50) -> list[dict]:
    """Browse codes by category prefix (e.g., 'A00', 'E11', 'I25')."""
    conn = get_connection()
    clean = prefix.upper().strip().replace(".", "")
    # Range query on the primary key index — fast for any prefix length
    upper = clean[:-1] + chr(ord(clean[-1]) + 1) if clean else "Z" * 10
    rows = conn.execute(
        "SELECT code, description, category_code, category_description "
        "FROM codes WHERE code >= ? AND code < ? ORDER BY code LIMIT ?",
        (clean, upper, limit),
    ).fetchall()
    return [dict(r) for r in rows]


def get_stats() -> dict:
    """Return database statistics."""
    conn = get_connection()
    count = conn.execute("SELECT COUNT(*) FROM codes").fetchone()[0]
    categories = conn.execute("SELECT COUNT(DISTINCT category_code) FROM codes").fetchone()[0]
    return {"total_codes": count, "total_categories": categories}
