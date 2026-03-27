"""Memory benchmarks comparing PersistentMap vs dict.copy()"""
import tracemalloc
import time
import sys

sys.path.insert(0, '.')
from persistent_collections import PersistentMap


def bench_dict_copy(n_keys, n_updates):
    d = {f"key_{i}": i for i in range(n_keys)}
    tracemalloc.start()
    start = time.perf_counter()
    for i in range(n_updates):
        d2 = d.copy()
        d2[f"key_0"] = i
    elapsed = time.perf_counter() - start
    current, peak = tracemalloc.get_traced_memory()
    tracemalloc.stop()
    return elapsed, current, peak


def bench_persistent_map(n_keys, n_updates):
    m = PersistentMap.from_dict({f"key_{i}": i for i in range(n_keys)})
    tracemalloc.start()
    start = time.perf_counter()
    for i in range(n_updates):
        m2 = m.set("key_0", i)
    elapsed = time.perf_counter() - start
    current, peak = tracemalloc.get_traced_memory()
    tracemalloc.stop()
    return elapsed, current, peak


if __name__ == "__main__":
    for n_keys in [10, 100, 1000]:
        n_updates = 10000
        print(f"\n--- {n_keys} keys, {n_updates} updates ---")

        t, cur, peak = bench_dict_copy(n_keys, n_updates)
        print(f"dict.copy():      {t:.4f}s, current={cur:,} bytes, peak={peak:,} bytes")

        t, cur, peak = bench_persistent_map(n_keys, n_updates)
        print(f"PersistentMap:    {t:.4f}s, current={cur:,} bytes, peak={peak:,} bytes")
