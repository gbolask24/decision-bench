"""Paired tests and intervals. Pure Python, seeded, so a rerun of the scorer gives the same numbers."""
from __future__ import annotations

import math
import random
from typing import Callable, Sequence


def mcnemar_exact(b: int, c: int) -> float:
    """Two-sided exact McNemar p-value from the discordant counts b and c."""
    n = b + c
    if n == 0:
        return 1.0
    k = min(b, c)
    tail = sum(math.comb(n, i) for i in range(k + 1)) / 2 ** n
    return min(1.0, 2 * tail)


def holm(pvalues: dict[str, float]) -> dict[str, float]:
    """Holm-adjusted p-values, monotone, capped at 1."""
    order = sorted(pvalues, key=pvalues.get)
    m, out, running = len(order), {}, 0.0
    for i, key in enumerate(order):
        running = max(running, (m - i) * pvalues[key])
        out[key] = min(1.0, running)
    return out


def percentile(values: Sequence[float], q: float) -> float:
    """Linear-interpolated percentile, q in [0, 100]."""
    if not values:
        return float("nan")
    s = sorted(values)
    pos = (len(s) - 1) * q / 100
    lo, hi = math.floor(pos), math.ceil(pos)
    return s[lo] + (s[hi] - s[lo]) * (pos - lo)


def bootstrap_ci(n: int, stat: Callable[[list[int]], float], resamples: int = 10_000, seed: int = 2026,
                 level: float = 95.0) -> tuple[float, float]:
    """Percentile interval for stat(indices) over resampled index lists of length n.
    Paired comparisons pass a stat that computes both systems on the same indices."""
    rng = random.Random(seed)
    draws = []
    for _ in range(resamples):
        idx = [rng.randrange(n) for _ in range(n)]
        draws.append(stat(idx))
    tail = (100 - level) / 2
    return percentile(draws, tail), percentile(draws, 100 - tail)
