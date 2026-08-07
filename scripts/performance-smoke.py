"""Dependency-free bounded API latency smoke gate."""

from __future__ import annotations

import argparse
import statistics
import time
import urllib.request


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--url", required=True)
    parser.add_argument("--requests", type=int, default=30)
    parser.add_argument("--p95-ms", type=float, default=500)
    args = parser.parse_args()
    durations: list[float] = []
    for _ in range(args.requests):
        started = time.perf_counter()
        with urllib.request.urlopen(args.url, timeout=5) as response:  # noqa: S310
            if response.status != 200:
                raise RuntimeError(f"unexpected response status {response.status}")
        durations.append((time.perf_counter() - started) * 1000)
    p95 = statistics.quantiles(durations, n=20)[18]
    if p95 > args.p95_ms:
        raise RuntimeError(f"p95 {p95:.1f} ms exceeds {args.p95_ms:.1f} ms")
    print(f"performance smoke passed: p95={p95:.1f} ms")


if __name__ == "__main__":
    main()
