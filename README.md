# mcp-icd10

Offline MCP server for ICD-10-CM medical code lookup.

**Zero API keys. Zero network calls. Zero data leakage. Your medical data never leaves your machine.**

All 74,260 ICD-10-CM codes (April 2025 release) embedded locally with SQLite FTS5 full-text search.

[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)
[![Python 3.10+](https://img.shields.io/badge/python-3.10+-blue.svg)](https://python.org)

## Why?

Existing medical terminology MCP servers are thin wrappers around remote APIs — rate-limited (5 req/s), network-dependent, and they send your clinical queries to third-party servers. That's a non-starter for HIPAA-conscious workflows.

`mcp-icd10` embeds the entire ICD-10-CM codeset in a local SQLite database with full-text search. Queries resolve in microseconds, not milliseconds. No API keys, no network, no data leakage.

## Performance

| Operation | Latency | Throughput |
|-----------|---------|------------|
| Exact code lookup | **2.7µs** | 369K queries/sec |
| Full-text search | **0.18ms** | 5.5K queries/sec |
| Category browse | **0.02ms** | 43K queries/sec |
| DB build (one-time, first run) | 0.4s | — |

## Quick Start

### Install via pip/uv

```bash
pip install mcp-icd10
# or
uvx mcp-icd10
```

### Configure in Claude Desktop

```json
{
  "mcpServers": {
    "icd10": {
      "command": "uvx",
      "args": ["mcp-icd10"]
    }
  }
}
```

### Docker

```bash
docker build -t mcp-icd10 .
docker run -i --rm mcp-icd10
```

## Tools

### `lookup_code`

Exact ICD-10-CM code lookup. Accepts codes with or without dots.

```
> lookup_code("E11.9")

Code: E119
Description: Type 2 diabetes mellitus without complications
Category: E11
```

### `search_codes`

Full-text search across all 74,260 code descriptions. BM25-ranked results. Supports natural language queries.

```
> search_codes("acute myocardial infarction")

Found 20 result(s) for 'acute myocardial infarction':
  I219: Acute myocardial infarction, unspecified
  I240: Acute coronary thrombosis not resulting in myocardial infarction
  I238: Other current complications following acute myocardial infarction
  ...
```

### `browse_category`

Browse all codes under a category prefix.

```
> browse_category("E11")

Found 50 code(s) under 'E11':
  E1100: Type 2 diabetes mellitus with hyperosmolarity without ...
  E1101: Type 2 diabetes mellitus with hyperosmolarity with coma
  ...
```

## Architecture

```
┌─────────────────────────────────────────┐
│           Claude / AI Agent             │
│         (MCP Client)                    │
└──────────────┬──────────────────────────┘
               │ MCP Protocol (stdio)
┌──────────────▼──────────────────────────┐
│          mcp-icd10 Server               │
│  ┌────────────────────────────────────┐ │
│  │  FastMCP (3 tools)                 │ │
│  │  lookup_code | search | browse     │ │
│  └──────────────┬─────────────────────┘ │
│  ┌──────────────▼─────────────────────┐ │
│  │  SQLite + FTS5                     │ │
│  │  74,260 codes | BM25 ranking       │ │
│  │  Porter stemming | Unicode support │ │
│  └──────────────┬─────────────────────┘ │
│  ┌──────────────▼─────────────────────┐ │
│  │  Embedded Data (0.7MB gzipped)     │ │
│  │  ICD-10-CM April 2025 Release      │ │
│  └────────────────────────────────────┘ │
└─────────────────────────────────────────┘
         100% local. Zero network calls.
```

## Data Source

ICD-10-CM April 2025 release from the [CDC/CMS](https://www.cms.gov/medicare/coding-billing/icd-10-codes). The dataset is parsed and enhanced from the official order file.

## Limitations

- ICD-10-CM only (no ICD-10-PCS procedure codes, no ICD-11, no SNOMED CT)
- April 2025 release — update frequency depends on new package releases
- Full-text search uses Porter stemming which may not handle all medical abbreviations perfectly
- No cross-terminology mapping (ICD → SNOMED, etc.)

## License

MIT
