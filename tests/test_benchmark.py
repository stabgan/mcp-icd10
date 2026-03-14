"""Benchmarks for mcp-icd10: DB build time, query latency, throughput."""

import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from mcp_icd10 import db


def benchmark_db_build():
    """Benchmark: time to build SQLite DB from compressed CSVs."""
    if db._DB_PATH.exists():
        db._DB_PATH.unlink()
    db._connection = None

    start = time.perf_counter()
    db._build_db()
    elapsed = time.perf_counter() - start

    size_mb = db._DB_PATH.stat().st_size / 1024 / 1024
    print(f"\n{'='*60}")
    print(f"DB BUILD")
    print(f"  Time:     {elapsed:.3f}s")
    print(f"  DB size:  {size_mb:.1f}MB")
    print(f"{'='*60}")
    return elapsed


def benchmark_lookup(n=1000):
    """Benchmark: exact code lookup latency across systems."""
    db._connection = None
    conn = db.get_connection()

    codes_10cm = [r[0] for r in conn.execute(
        "SELECT code FROM codes WHERE system='icd10cm' LIMIT ?", (n,)
    ).fetchall()]
    codes_9cm = [r[0] for r in conn.execute(
        "SELECT code FROM codes WHERE system='icd9cm' LIMIT ?", (min(n, 500),)
    ).fetchall()]

    # ICD-10-CM lookup
    start = time.perf_counter()
    for code in codes_10cm:
        db.lookup_code(code, "icd10cm")
    elapsed_10 = time.perf_counter() - start
    avg_10 = (elapsed_10 / len(codes_10cm)) * 1_000_000

    # ICD-9-CM lookup
    start = time.perf_counter()
    for code in codes_9cm:
        db.lookup_code(code, "icd9cm")
    elapsed_9 = time.perf_counter() - start
    avg_9 = (elapsed_9 / len(codes_9cm)) * 1_000_000

    # All-systems lookup
    start = time.perf_counter()
    for code in codes_10cm[:200]:
        db.lookup_code_all_systems(code)
    elapsed_all = time.perf_counter() - start
    avg_all = (elapsed_all / 200) * 1_000_000

    print(f"\nEXACT LOOKUP")
    print(f"  ICD-10-CM ({len(codes_10cm)} queries): {avg_10:.1f}µs avg, {len(codes_10cm)/elapsed_10:,.0f} QPS")
    print(f"  ICD-9-CM  ({len(codes_9cm)} queries):  {avg_9:.1f}µs avg, {len(codes_9cm)/elapsed_9:,.0f} QPS")
    print(f"  All-systems (200 queries):  {avg_all:.1f}µs avg, {200/elapsed_all:,.0f} QPS")


def benchmark_fts_search(n=100):
    """Benchmark: full-text search latency."""
    queries = [
        "diabetes", "hypertension", "myocardial infarction",
        "chronic kidney disease", "pneumonia", "fracture femur",
        "breast cancer", "asthma", "heart failure", "stroke",
        "sepsis", "anemia", "obesity", "depression", "anxiety",
        "covid", "cholera", "tuberculosis", "hepatitis", "malaria",
    ]

    # All systems
    start = time.perf_counter()
    total_results = 0
    for i in range(n):
        results = db.search_codes(queries[i % len(queries)], limit=20)
        total_results += len(results)
    elapsed = time.perf_counter() - start
    avg_ms = (elapsed / n) * 1000

    # Single system
    start2 = time.perf_counter()
    for i in range(n):
        db.search_codes(queries[i % len(queries)], system="icd10cm", limit=20)
    elapsed2 = time.perf_counter() - start2
    avg_ms2 = (elapsed2 / n) * 1000

    print(f"\nFTS5 SEARCH ({n} queries)")
    print(f"  All systems:  {avg_ms:.2f}ms avg, {n/elapsed:,.0f} QPS, {total_results/n:.1f} results/query")
    print(f"  ICD-10-CM:    {avg_ms2:.2f}ms avg, {n/elapsed2:,.0f} QPS")


def benchmark_crosswalk(n=200):
    """Benchmark: crosswalk translation latency."""
    conn = db.get_connection()
    codes_9 = [r[0] for r in conn.execute(
        "SELECT DISTINCT source_code FROM crosswalk WHERE source_system='icd9cm' LIMIT ?", (n,)
    ).fetchall()]
    codes_10 = [r[0] for r in conn.execute(
        "SELECT DISTINCT source_code FROM crosswalk WHERE source_system='icd10cm' LIMIT ?", (n,)
    ).fetchall()]

    start = time.perf_counter()
    for code in codes_9:
        db.crosswalk(code, "icd9cm")
    elapsed_9 = time.perf_counter() - start

    start = time.perf_counter()
    for code in codes_10:
        db.crosswalk(code, "icd10cm")
    elapsed_10 = time.perf_counter() - start

    print(f"\nCROSSWALK TRANSLATION")
    print(f"  ICD-9→10 ({len(codes_9)} queries): {(elapsed_9/len(codes_9))*1000:.2f}ms avg, {len(codes_9)/elapsed_9:,.0f} QPS")
    print(f"  ICD-10→9 ({len(codes_10)} queries): {(elapsed_10/len(codes_10))*1000:.2f}ms avg, {len(codes_10)/elapsed_10:,.0f} QPS")


def benchmark_browse(n=100):
    """Benchmark: category browse latency."""
    prefixes = ["A00", "E11", "I25", "J18", "K70", "M54", "N18", "S72", "C50", "F32"]

    start = time.perf_counter()
    for i in range(n):
        db.browse_category(prefixes[i % len(prefixes)], "icd10cm", 50)
    elapsed = time.perf_counter() - start

    print(f"\nCATEGORY BROWSE ({n} queries)")
    print(f"  {(elapsed/n)*1000:.2f}ms avg, {n/elapsed:,.0f} QPS")


def test_correctness():
    """Verify data integrity across all systems."""
    stats = db.get_stats()
    print(f"\nCORRECTNESS CHECKS")
    for sys_name in db.SYSTEMS:
        s = stats[sys_name]
        print(f"  {sys_name}: {s['codes']:,} codes, {s['categories']:,} categories")
    print(f"  crosswalk: {stats['crosswalk_mappings']:,} mappings")

    # ICD-10-CM checks
    r = db.lookup_code("E119", "icd10cm")
    assert r and "diabetes" in r["description"].lower(), f"E119 check failed: {r}"
    print(f"  ✓ E119 (ICD-10-CM): {r['description'][:50]}")

    r = db.lookup_code("U071", "icd10cm")
    assert r and "covid" in r["description"].lower(), f"U071 check failed: {r}"
    print(f"  ✓ U071 (ICD-10-CM): {r['description'][:50]}")

    # ICD-9-CM checks
    r = db.lookup_code("25000", "icd9cm")
    assert r and "diabetes" in r["description"].lower(), f"25000 check failed: {r}"
    print(f"  ✓ 25000 (ICD-9-CM): {r['description'][:50]}")

    r = db.lookup_code("0010", "icd9cm")
    assert r and "cholera" in r["description"].lower(), f"0010 check failed: {r}"
    print(f"  ✓ 0010 (ICD-9-CM): {r['description'][:50]}")

    # ICD-10 WHO checks
    r = db.lookup_code("A00", "icd10who")
    assert r and "cholera" in r["description"].lower(), f"A00 WHO check failed: {r}"
    print(f"  ✓ A00 (ICD-10 WHO): {r['description'][:50]}")

    # Cross-system lookup
    results = db.lookup_code_all_systems("A00")
    assert len(results) >= 2, f"A00 should exist in multiple systems, got {len(results)}"
    print(f"  ✓ A00 found in {len(results)} systems")

    # Crosswalk checks
    xw = db.crosswalk("E119", "icd10cm")
    assert len(xw) > 0, "E119 should have crosswalk mappings"
    print(f"  ✓ E119 crosswalk: {len(xw)} mapping(s) → {xw[0]['target_code']}")

    xw = db.crosswalk("25000", "icd9cm")
    assert len(xw) > 0, "25000 should have crosswalk mappings"
    print(f"  ✓ 25000 crosswalk: {len(xw)} mapping(s) → {xw[0]['target_code']}")

    # FTS search
    results = db.search_codes("type 2 diabetes")
    assert len(results) > 0
    print(f"  ✓ FTS 'type 2 diabetes': {len(results)} results")

    # Code counts
    assert stats["icd10cm"]["codes"] == 98186, f"Expected 98186 ICD-10-CM, got {stats['icd10cm']['codes']}"
    assert stats["icd9cm"]["codes"] == 14567, f"Expected 14567 ICD-9-CM, got {stats['icd9cm']['codes']}"
    assert stats["icd10who"]["codes"] == 11243, f"Expected 11243 ICD-10 WHO, got {stats['icd10who']['codes']}"

    print(f"\n  ALL CHECKS PASSED ✓")


if __name__ == "__main__":
    print("mcp-icd10 Benchmark Suite (Multi-System)")
    print("=" * 60)

    benchmark_db_build()
    test_correctness()
    benchmark_lookup(n=5000)
    benchmark_fts_search(n=500)
    benchmark_crosswalk(n=500)
    benchmark_browse(n=500)

    print(f"\n{'='*60}")
    print("DONE")
