"""Benchmarks for mcp-icd10: DB build time, query latency, throughput."""

import sys
import time
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from mcp_icd10 import db


def benchmark_db_build():
    """Benchmark: time to build SQLite DB from compressed CSV."""
    # Remove existing DB to force rebuild
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
    """Benchmark: exact code lookup latency."""
    db._connection = None  # Reset connection
    conn = db.get_connection()
    
    # Get some real codes to look up
    codes = [r[0] for r in conn.execute("SELECT code FROM codes LIMIT ?", (n,)).fetchall()]
    
    start = time.perf_counter()
    for code in codes:
        db.lookup_code(code)
    elapsed = time.perf_counter() - start
    
    avg_us = (elapsed / n) * 1_000_000
    qps = n / elapsed
    print(f"\nEXACT LOOKUP ({n} queries)")
    print(f"  Total:    {elapsed:.3f}s")
    print(f"  Avg:      {avg_us:.1f}µs per query")
    print(f"  QPS:      {qps:,.0f}")
    return avg_us


def benchmark_fts_search(n=100):
    """Benchmark: full-text search latency."""
    queries = [
        "diabetes", "hypertension", "myocardial infarction",
        "chronic kidney disease", "pneumonia", "fracture femur",
        "breast cancer", "asthma", "heart failure", "stroke",
        "sepsis", "anemia", "obesity", "depression", "anxiety",
        "covid", "cholera", "tuberculosis", "hepatitis", "malaria",
    ]
    
    start = time.perf_counter()
    total_results = 0
    for i in range(n):
        q = queries[i % len(queries)]
        results = db.search_codes(q, limit=20)
        total_results += len(results)
    elapsed = time.perf_counter() - start
    
    avg_ms = (elapsed / n) * 1000
    qps = n / elapsed
    print(f"\nFTS5 SEARCH ({n} queries)")
    print(f"  Total:    {elapsed:.3f}s")
    print(f"  Avg:      {avg_ms:.2f}ms per query")
    print(f"  QPS:      {qps:,.0f}")
    print(f"  Avg results/query: {total_results/n:.1f}")
    return avg_ms


def benchmark_browse(n=100):
    """Benchmark: category browse latency."""
    prefixes = ["A00", "E11", "I25", "J18", "K70", "M54", "N18", "S72", "C50", "F32"]
    
    start = time.perf_counter()
    for i in range(n):
        p = prefixes[i % len(prefixes)]
        db.browse_category(p, limit=50)
    elapsed = time.perf_counter() - start
    
    avg_ms = (elapsed / n) * 1000
    qps = n / elapsed
    print(f"\nCATEGORY BROWSE ({n} queries)")
    print(f"  Total:    {elapsed:.3f}s")
    print(f"  Avg:      {avg_ms:.2f}ms per query")
    print(f"  QPS:      {qps:,.0f}")
    return avg_ms


def test_correctness():
    """Verify data integrity."""
    stats = db.get_stats()
    print(f"\nCORRECTNESS CHECKS")
    print(f"  Total codes:      {stats['total_codes']}")
    print(f"  Total categories: {stats['total_categories']}")
    
    # Check known codes
    r = db.lookup_code("E119")
    assert r is not None, "E119 (Type 2 diabetes) should exist"
    assert "diabetes" in r["description"].lower(), f"E119 description should mention diabetes: {r['description']}"
    print(f"  E119: ✓ {r['description'][:60]}...")
    
    r = db.lookup_code("U071")
    assert r is not None, "U071 (COVID-19) should exist"
    assert "covid" in r["description"].lower(), f"U071 should mention COVID: {r['description']}"
    print(f"  U071: ✓ {r['description'][:60]}...")
    
    r = db.lookup_code("A000")
    assert r is not None, "A000 (Cholera) should exist"
    print(f"  A000: ✓ {r['description'][:60]}...")
    
    # Check dot-notation works
    r = db.lookup_code("E11.9")
    assert r is not None, "E11.9 should resolve to E119"
    print(f"  E11.9 → E119: ✓")
    
    # Check search returns results
    results = db.search_codes("type 2 diabetes")
    assert len(results) > 0, "Search for 'type 2 diabetes' should return results"
    print(f"  Search 'type 2 diabetes': ✓ ({len(results)} results)")
    
    # Check browse
    results = db.browse_category("E11")
    assert len(results) > 0, "Browse E11 should return results"
    print(f"  Browse 'E11': ✓ ({len(results)} codes)")
    
    assert stats["total_codes"] == 74260, f"Expected 74260 codes, got {stats['total_codes']}"
    print(f"\n  ALL CHECKS PASSED ✓")


if __name__ == "__main__":
    print("mcp-icd10 Benchmark Suite")
    print("=" * 60)
    
    benchmark_db_build()
    test_correctness()
    benchmark_lookup(n=10000)
    benchmark_fts_search(n=500)
    benchmark_browse(n=500)
    
    print(f"\n{'='*60}")
    print("DONE")
