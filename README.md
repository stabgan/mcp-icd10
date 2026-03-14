# mcp-icd10

Offline MCP server for ICD medical code lookup, search, and crosswalk translation.

**Zero API keys. Zero network calls. Zero data leakage.**

124K codes across three coding systems with 102K bidirectional crosswalk mappings, all running locally in a SQLite database.

[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)
[![Python 3.10+](https://img.shields.io/badge/python-3.10+-blue.svg)](https://python.org)
[![MCP](https://img.shields.io/badge/MCP-compatible-green.svg)](https://modelcontextprotocol.io)

## Why?

Existing medical terminology services are thin wrappers around remote APIs — rate-limited, network-dependent, and they send your clinical queries to third-party servers. That's a non-starter for HIPAA-conscious workflows.

This server embeds everything locally. A pre-built SQLite database with FTS5 full-text search ships inside the package. Queries resolve in microseconds. Nothing leaves your machine.

## What's included

| System | Codes | Source |
|--------|------:|--------|
| ICD-10-CM FY2026 | 98,186 | CMS.gov (incl. 74,719 billable) |
| ICD-9-CM | 14,567 | CMS GEMs package |
| ICD-10 WHO 2019 | 11,243 | WHO |
| GEMs crosswalk | 102,591 | CMS (bidirectional ICD-9 ↔ ICD-10) |

**Total: 123,996 codes + 102,591 crosswalk mappings**

## Performance

All benchmarks on Apple Silicon. Every query hits an index or FTS5 — no table scans.

| Operation | Latency |
|-----------|---------|
| Exact code lookup | **4.4 µs** |
| Full-text search | **0.23 ms** |
| Category browse | **0.04 ms** |
| Crosswalk translation | **5.9 µs** |
| DB decompress (first run only) | ~38 ms |

## Quick start

### Claude Desktop / Kiro / any MCP client

```json
{
  "mcpServers": {
    "icd": {
      "command": "uvx",
      "args": ["mcp-icd10"]
    }
  }
}
```

### Docker

```bash
docker build -t mcp-icd10 .
```

```json
{
  "mcpServers": {
    "icd": {
      "command": "docker",
      "args": ["run", "--rm", "-i", "mcp-icd10"]
    }
  }
}
```

### Install from source

```bash
git clone https://github.com/stabgan/mcp-icd10.git
cd mcp-icd10
pip install .
mcp-icd10
```

## Tools

### `lookup_code`

Look up a medical code and return its description. Accepts codes with or without dots. Searches across all systems when no system is specified.

```
> lookup_code("E11.9")
[icd10cm] E119: Type 2 diabetes mellitus without complications

> lookup_code("250.00")
[icd9cm] 25000: Diabetes mellitus without mention of complication, type II or unspecified type, not stated as uncontrolled
```

### `search_codes`

Full-text search across all 124K code descriptions. Supports natural language clinical queries.

```
> search_codes("acute myocardial infarction")
Found 20 result(s) for 'acute myocardial infarction':
  [icd10cm] I219: Acute myocardial infarction, unspecified
  [icd10cm] I2101: ST elevation (STEMI) myocardial infarction involving left main coronary artery
  [icd9cm] 41071: Acute myocardial infarction of subendocardial wall, initial episode of care
  ...
```

### `browse_category`

Browse all codes under a category prefix within a specific system.

```
> browse_category("E11", system="icd10cm")
50 code(s) under 'E11' [icd10cm]:
  E1100: Type 2 diabetes mellitus with hyperosmolarity without nonketotic hyperglycemic-hyperosmolar coma
  E1101: Type 2 diabetes mellitus with hyperosmolarity with coma
  ...
```

### `translate_code`

Translate between ICD-9-CM and ICD-10-CM using the CMS General Equivalence Mappings (GEMs).

```
> translate_code("250.00")
Crosswalk for '25000':
  25000 → [icd10cm] E119 — Type 2 diabetes mellitus without complications [≈]

> translate_code("E119", source_system="icd10cm")
Crosswalk for 'E119':
  E119 → [icd9cm] 25000 — Diabetes mellitus without mention of complication, type II ... [≈]
```

### `get_stats`

Returns code counts per system and total crosswalk mappings.

## Architecture

```
┌─────────────────────────────────────────────┐
│         Claude / Kiro / AI Agent            │
│              (MCP Client)                   │
└──────────────────┬──────────────────────────┘
                   │ MCP Protocol (stdio)
┌──────────────────▼──────────────────────────┐
│            mcp-icd10 Server                 │
│  ┌────────────────────────────────────────┐ │
│  │  FastMCP — 5 tools                     │ │
│  │  lookup · search · browse              │ │
│  │  translate · stats                     │ │
│  └──────────────┬─────────────────────────┘ │
│  ┌──────────────▼─────────────────────────┐ │
│  │  SQLite + FTS5 (read-only)             │ │
│  │  124K codes │ 102K crosswalk mappings  │ │
│  │  Integer system IDs │ Bitmask flags    │ │
│  └──────────────┬─────────────────────────┘ │
│  ┌──────────────▼─────────────────────────┐ │
│  │  Pre-built DB (5.2 MB gzipped)         │ │
│  │  Decompresses on first run → 23 MB     │ │
│  └────────────────────────────────────────┘ │
└─────────────────────────────────────────────┘
           100% local · zero network calls
```

## How it works

The package ships a pre-built, gzipped SQLite database (`icd.db.gz`, ~5 MB). On first run, it decompresses to ~23 MB and opens in read-only mode with memory-mapped I/O.

Key design decisions:
- **Integer system IDs** (0/1/2) instead of text strings for compact storage and fast comparisons
- **`CROSS JOIN` in FTS queries** forces SQLite's query planner to use the FTS index first, avoiding full table scans on broad search terms
- **No FTS5 ranking** — `ORDER BY rank` forces full-scan scoring on all matches. Instead, we cap at 500 FTS candidates and sort by description length (shorter = more specific = better relevance proxy for medical codes)
- **Bitmask flags** on crosswalk entries pack approximate/no-map/combination into a single integer
- **`WITHOUT ROWID`** on the crosswalk table for clustered primary key access

## Data sources

- **ICD-10-CM FY2026**: [CMS.gov](https://www.cms.gov/medicare/coding-billing/icd-10-codes)
- **ICD-9-CM + GEMs**: [CMS General Equivalence Mappings](https://www.cms.gov/medicare/coding-billing/icd-10-codes/general-equivalence-mappings-gems)
- **ICD-10 WHO 2019**: [WHO ICD-10](https://icd.who.int/browse10/2019/en)

## Limitations

- No ICD-10-PCS (procedure codes), ICD-11, or SNOMED CT
- GEMs crosswalk covers ICD-9-CM ↔ ICD-10-CM only (not WHO codes)
- FTS5 uses Porter stemming — some medical abbreviations may not stem perfectly
- Update frequency depends on new package releases

## License

MIT
