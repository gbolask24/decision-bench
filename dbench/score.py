"""Score the logs against the gold labels and run the pre-registered comparisons."""
from __future__ import annotations

import json
from collections import defaultdict
from itertools import combinations
from pathlib import Path

from .items import Item
from .stats import bootstrap_ci, holm, mcnemar_exact, percentile

MAIN_ARMS = ["jev", "decisions", "opus-low"]
FAILED = ("invalid", "refusal", "truncated", "http_error", "transport_error")


def load_logs(paths: list[Path]) -> list[dict]:
    out = []
    for p in paths:
        out += [json.loads(line) for line in p.read_text().splitlines() if line.strip()]
    return out


def brier(probs: dict[str, float] | None, gold: str, values: list[str]) -> float:
    """Multiclass Brier: sum of squared errors over the options. A failed answer scores as all zeros (1.0)."""
    if probs is None:
        return 1.0
    return sum((probs.get(v, 0.0) - (1.0 if v == gold else 0.0)) ** 2 for v in values)


def ece(confidences: list[float], correct: list[bool], bins: int = 10) -> float:
    n = len(confidences)
    if n == 0:
        return float("nan")
    total = 0.0
    for b in range(bins):
        lo, hi = b / bins, (b + 1) / bins
        idx = [i for i, c in enumerate(confidences) if (lo < c <= hi) or (b == 0 and c == 0)]
        if idx:
            acc = sum(correct[i] for i in idx) / len(idx)
            conf = sum(confidences[i] for i in idx) / len(idx)
            total += len(idx) / n * abs(acc - conf)
    return total


def item_rows(items: list[Item], records: list[dict], question: str | None, arms: list[str]) -> dict[str, dict]:
    """First accuracy-mode record per (item, arm) at repeat 0, scored on one question.
    question=None scores each item's first question (Decision Bench rows each name their own)."""
    first = {}
    for r in records:
        if r["mode"] == "accuracy" and r["repeat"] == 0 and r["arm"] in arms:
            first.setdefault((r["item_id"], r["arm"]), r)
    rows = {}
    for it in items:
        q = it.questions[0] if question is None else next(q for q in it.questions if q.name == question)
        name = q.name
        row = {}
        for arm in arms:
            r = first.get((it.id, arm))
            if r is None:
                continue
            a = r.get("answers", {}).get(name)
            label = a["label"] if a and r["status"] == "ok" else None
            probs = a["probs"] if a and r["status"] == "ok" else None
            row[arm] = {"correct": it.is_correct(name, label), "label": label, "probs": probs,
                        "brier": brier(probs, it.gold[name], q.values()),
                        "top": max(probs.values()) if probs else None,
                        "status": r["status"], "cost": r.get("cost_usd", 0.0)}
        rows[it.id] = row
    return rows


def summarise(rows: dict[str, dict], arms: list[str], resamples: int = 10_000) -> dict:
    ids = [i for i, row in rows.items() if all(a in row for a in arms)]
    out = {"n": len(ids), "arms": {}, "pairs": {}}
    for arm in arms:
        cells = [rows[i][arm] for i in ids]
        n = len(cells)
        if n == 0:
            continue
        acc = [c["correct"] for c in cells]
        br = [c["brier"] for c in cells]
        valid = [c for c in cells if c["probs"] is not None]
        statuses = defaultdict(int)
        for c in cells:
            statuses[c["status"]] += 1
        out["arms"][arm] = {
            "accuracy": sum(acc) / n,
            "accuracy_ci": bootstrap_ci(n, lambda ix: sum(acc[i] for i in ix) / n, resamples),
            "brier": sum(br) / n,
            "brier_ci": bootstrap_ci(n, lambda ix: sum(br[i] for i in ix) / n, resamples),
            "ece_shown_not_claimed": ece([c["top"] for c in valid], [c["correct"] for c in valid]),
            "exact_one_share": sum(1 for c in valid if c["top"] >= 0.9999) / len(valid) if valid else None,
            "status_rates": {s: k / n for s, k in statuses.items()},
            "cost_per_1000_usd": sum(c["cost"] for c in cells) / n * 1000,
        }
    for a, b in combinations([x for x in arms if x in out["arms"]], 2):
        ca = [rows[i][a]["correct"] for i in ids]
        cb = [rows[i][b]["correct"] for i in ids]
        ba = [rows[i][a]["brier"] for i in ids]
        bb = [rows[i][b]["brier"] for i in ids]
        n = len(ids)
        only_a = sum(1 for x, y in zip(ca, cb) if x and not y)
        only_b = sum(1 for x, y in zip(ca, cb) if y and not x)
        out["pairs"][f"{a} vs {b}"] = {
            "accuracy_diff": (sum(ca) - sum(cb)) / n,
            "accuracy_diff_ci": bootstrap_ci(n, lambda ix: sum(ca[i] - cb[i] for i in ix) / n, resamples),
            "only_first_right": only_a, "only_second_right": only_b,
            "mcnemar_p": mcnemar_exact(only_a, only_b),
            "brier_diff": (sum(ba) - sum(bb)) / n,
            "brier_diff_ci": bootstrap_ci(n, lambda ix: sum(ba[i] - bb[i] for i in ix) / n, resamples),
        }
    adj = holm({k: v["mcnemar_p"] for k, v in out["pairs"].items()})
    for k, v in out["pairs"].items():
        v["mcnemar_p_holm"] = adj[k]
        v["accuracy_claim"] = v["mcnemar_p_holm"] < 0.05 and not (v["accuracy_diff_ci"][0] <= 0 <= v["accuracy_diff_ci"][1])
        v["brier_claim"] = not (v["brier_diff_ci"][0] <= 0 <= v["brier_diff_ci"][1])
    return out


def image_effect(rows_text: dict, rows_image: dict, arms: list[str], resamples: int = 10_000) -> dict:
    """Per arm, accuracy with the image minus without, on the same products (T3 minus T2)."""
    key = lambda i: i.split("-", 1)[1]
    t = {key(i): r for i, r in rows_text.items()}
    m = {key(i): r for i, r in rows_image.items()}
    out = {}
    for arm in arms:
        ids = [k for k in t if k in m and arm in t[k] and arm in m[k]]
        n = len(ids)
        if not n:
            continue
        d = [int(m[k][arm]["correct"]) - int(t[k][arm]["correct"]) for k in ids]
        out[arm] = {"n": n, "diff": sum(d) / n, "diff_ci": bootstrap_ci(n, lambda ix: sum(d[i] for i in ix) / n, resamples)}
    return out


def flip_rate(records: list[dict], question: str | None, arms: list[str]) -> dict:
    picks = defaultdict(list)
    for r in records:
        if r["mode"] == "accuracy" and r["arm"] in arms:
            answers = r.get("answers", {})
            a = next(iter(answers.values()), None) if question is None else answers.get(question)
            picks[(r["item_id"], r["arm"])].append(a["label"] if a and r["status"] == "ok" else None)
    out = {}
    for arm in arms:
        reps = [v for (i, a), v in picks.items() if a == arm and len(v) > 1]
        if reps:
            out[arm] = {"items": len(reps), "flip_rate": sum(1 for v in reps if len(set(v)) > 1) / len(reps)}
    return out


def latency(records: list[dict], arms: list[str], resamples: int = 10_000) -> dict:
    out = {}
    for arm in arms:
        xs = [r["latency_s"] for r in records if r["mode"] == "latency" and not r.get("warmup") and r["arm"] == arm
              and r["status"] not in ("transport_error", "http_error")]
        if not xs:
            continue
        n = len(xs)
        out[arm] = {"n": n, "p50_s": percentile(xs, 50), "p95_s": percentile(xs, 95),
                    "p50_ci": bootstrap_ci(n, lambda ix: percentile([xs[i] for i in ix], 50), resamples),
                    "p95_ci": bootstrap_ci(n, lambda ix: percentile([xs[i] for i in ix], 95), resamples)}
    return out
