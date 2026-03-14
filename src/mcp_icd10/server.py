"""MCP server for offline ICD-10-CM code lookup.

Zero API keys. Zero network calls. Zero data leakage.
All 74,260 ICD-10-CM codes embedded locally with full-text search.
"""

from mcp.server.fastmcp import FastMCP

from mcp_icd10 import db

mcp = FastMCP(
    "mcp-icd10",
    instructions="Offline ICD-10-CM medical code lookup with full-text search. "
    "74,260 codes, zero network calls, instant results.",
)


@mcp.tool()
def lookup_code(code: str) -> str:
    """Look up an ICD-10-CM code and return its description.

    Args:
        code: ICD-10-CM code (e.g., 'E11.9', 'E119', 'A000'). Dots are optional.

    Returns:
        Code details including description and category, or 'not found' message.
    """
    result = db.lookup_code(code)
    if not result:
        return f"Code '{code}' not found. Try search_codes() to find the right code."
    return (
        f"Code: {result['code']}\n"
        f"Description: {result['description']}\n"
        f"Category: {result['category_code']}"
    )


@mcp.tool()
def search_codes(query: str, limit: int = 20) -> str:
    """Search ICD-10-CM codes by clinical description using full-text search.

    Supports natural language queries like 'type 2 diabetes with kidney disease'
    or 'acute myocardial infarction'. Uses BM25 ranking for relevance.

    Args:
        query: Clinical description or keywords to search for.
        limit: Maximum number of results (default 20, max 50).

    Returns:
        Ranked list of matching ICD-10-CM codes with descriptions.
    """
    limit = min(max(1, limit), 50)
    results = db.search_codes(query, limit)
    if not results:
        return f"No codes found for '{query}'. Try different keywords or broader terms."
    lines = [f"Found {len(results)} result(s) for '{query}':\n"]
    for r in results:
        lines.append(
            f"  {r['code']}: {r['description']}"
        )
    return "\n".join(lines)


@mcp.tool()
def browse_category(prefix: str, limit: int = 50) -> str:
    """Browse all ICD-10-CM codes under a category prefix.

    Args:
        prefix: Category prefix (e.g., 'E11' for Type 2 diabetes, 'I25' for chronic ischemic heart disease).
        limit: Maximum number of results (default 50, max 100).

    Returns:
        List of all codes under the given category prefix.
    """
    limit = min(max(1, limit), 100)
    results = db.browse_category(prefix, limit)
    if not results:
        return f"No codes found with prefix '{prefix}'."
    lines = [f"Found {len(results)} code(s) under '{prefix}':\n"]
    for r in results:
        lines.append(f"  {r['code']}: {r['description']}")
    return "\n".join(lines)


def main():
    mcp.run()


if __name__ == "__main__":
    main()
