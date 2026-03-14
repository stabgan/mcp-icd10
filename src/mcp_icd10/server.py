"""MCP server for offline ICD code lookup.

Zero API keys. Zero network calls. Zero data leakage.
124K codes across ICD-10-CM, ICD-9-CM, ICD-10 WHO + 102K GEMs crosswalk mappings.
"""

from mcp.server.fastmcp import FastMCP
from mcp_icd10 import db

mcp = FastMCP(
    "mcp-icd",
    instructions=(
        "Offline medical code lookup: ICD-10-CM, ICD-9-CM, ICD-10 WHO. "
        "GEMs crosswalk for ICD-9↔ICD-10 translation. "
        "124K codes, 102K mappings, zero network calls."
    ),
)


@mcp.tool()
def lookup_code(code: str, system: str = "") -> str:
    """Look up a medical code and return its description.

    Args:
        code: Medical code (e.g., 'E11.9', '250.00'). Dots optional.
        system: 'icd10cm', 'icd9cm', or 'icd10who'. Empty = search all.
    """
    sys_f = system.lower().strip() or None
    if sys_f and sys_f not in db.SYSTEMS:
        return f"Unknown system '{system}'. Valid: {', '.join(db.SYSTEMS)}"

    results = [db.lookup_code(code, sys_f)] if sys_f else db.lookup_code_all_systems(code)
    results = [r for r in results if r]
    if not results:
        return f"Code '{code}' not found. Try search_codes() to find it."
    return "\n".join(
        f"[{r['system']}] {r['code']}: {r['description']}" for r in results
    )


@mcp.tool()
def search_codes(query: str, system: str = "", limit: int = 20) -> str:
    """Search codes by clinical description using full-text search.

    Args:
        query: Clinical description or keywords (e.g., 'type 2 diabetes').
        system: 'icd10cm', 'icd9cm', or 'icd10who'. Empty = all systems.
        limit: Max results (default 20, max 50).
    """
    sys_f = system.lower().strip() or None
    if sys_f and sys_f not in db.SYSTEMS:
        return f"Unknown system '{system}'. Valid: {', '.join(db.SYSTEMS)}"
    limit = min(max(1, limit), 50)
    results = db.search_codes(query, sys_f, limit)
    if not results:
        return f"No codes found for '{query}'. Try broader terms."
    lines = [f"Found {len(results)} result(s) for '{query}':\n"]
    for r in results:
        lines.append(f"  [{r['system']}] {r['code']}: {r['description']}")
    return "\n".join(lines)


@mcp.tool()
def browse_category(prefix: str, system: str = "icd10cm", limit: int = 50) -> str:
    """Browse all codes under a category prefix.

    Args:
        prefix: Category prefix (e.g., 'E11', 'I25', '250').
        system: 'icd10cm' (default), 'icd9cm', or 'icd10who'.
        limit: Max results (default 50, max 100).
    """
    sys_f = system.lower().strip()
    if sys_f not in db.SYSTEMS:
        return f"Unknown system '{system}'. Valid: {', '.join(db.SYSTEMS)}"
    limit = min(max(1, limit), 100)
    results = db.browse_category(prefix, sys_f, limit)
    if not results:
        return f"No codes under '{prefix}' in {sys_f}."
    lines = [f"{len(results)} code(s) under '{prefix}' [{sys_f}]:\n"]
    for r in results:
        lines.append(f"  {r['code']}: {r['description']}")
    return "\n".join(lines)


@mcp.tool()
def translate_code(code: str, source_system: str = "") -> str:
    """Translate between ICD-9-CM and ICD-10-CM using GEMs crosswalk.

    Args:
        code: Source code (e.g., '250.00' for ICD-9, 'E119' for ICD-10-CM).
        source_system: 'icd9cm' or 'icd10cm'. Empty = auto-detect.
    """
    src = source_system.lower().strip() or None
    if src and src not in ("icd9cm", "icd10cm"):
        return "GEMs only supports 'icd9cm' and 'icd10cm'."
    results = db.crosswalk(code, src)
    if not results:
        return f"No crosswalk mappings for '{code}'."
    lines = [f"Crosswalk for '{code}':\n"]
    for r in results:
        flags = []
        if r["approximate"]: flags.append("≈")
        if r["no_map"]: flags.append("no-map")
        if r["combination"]: flags.append("combo")
        flag_s = f" [{','.join(flags)}]" if flags else ""
        desc = f" — {r['target_description']}" if r["target_description"] else ""
        lines.append(f"  {r['source_code']} → [{r['target_system']}] {r['target_code']}{desc}{flag_s}")
    return "\n".join(lines)


@mcp.tool()
def get_stats() -> str:
    """Database statistics: code counts per system and crosswalk mappings."""
    s = db.get_stats()
    return (
        f"ICD-10-CM: {s['icd10cm']:,} codes\n"
        f"ICD-9-CM:  {s['icd9cm']:,} codes\n"
        f"ICD-10 WHO: {s['icd10who']:,} codes\n"
        f"GEMs crosswalk: {s['crosswalk_mappings']:,} mappings\n"
        f"Total: {s['total_codes']:,} codes"
    )


def main():
    mcp.run()

if __name__ == "__main__":
    main()
