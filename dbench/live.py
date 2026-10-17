"""Run folders and the live summary of a run: one row per test and system, kept up to date as calls land.
The percentages here are a running count against the datasets' gold labels; the scorer's numbers are final."""
from __future__ import annotations

import json
import os
import subprocess
from collections import deque
from datetime import datetime, timedelta, timezone
from pathlib import Path

from .items import Item

REPO = Path(__file__).resolve().parents[1]
KEEP = 20  # recent calls and errors shown


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _pct(values: list[float], q: float) -> float | None:
    if not values:
        return None
    v = sorted(values)
    pos = q * (len(v) - 1)
    lo = int(pos)
    hi = min(lo + 1, len(v) - 1)
    return v[lo] + (v[hi] - v[lo]) * (pos - lo)


def _git(*args: str) -> str:
    try:
        return subprocess.run(["git", *args], cwd=REPO, capture_output=True, text=True, timeout=5).stdout.strip()
    except (OSError, subprocess.SubprocessError):
        return ""


class RunStats:
    """Every finished call of the run, keyed by (task, item, arm, repeat). A later record for the same key
    (a resumed run retrying a transport error) replaces the earlier one."""

    def __init__(self, items_by_task: dict[str, list[Item]], questions: dict[str, str | None], arms: list[str],
                 repeats: int = 1):
        self.items = {i.id: i for its in items_by_task.values() for i in its}
        self.questions, self.arms = questions, arms
        self.planned = {(t, a): len(its) * repeats for t, its in items_by_task.items() for a in arms}
        self.calls: dict[tuple, dict] = {}
        self.recent: deque = deque(maxlen=KEEP)
        self.errors: deque = deque(maxlen=KEEP)

    def add(self, r: dict) -> None:
        item = self.items.get(r.get("item_id"))
        if r.get("mode") != "accuracy" or item is None or (r["task"], r["arm"]) not in self.planned:
            return
        q = self.questions.get(r["task"]) or item.questions[0].name
        a = (r.get("answers") or {}).get(q) if r["status"] == "ok" else None
        u = r.get("usage") or {}
        c = {"ts": r.get("ts", ""), "task": r["task"], "arm": r["arm"], "item_id": r["item_id"], "status": r["status"],
             "correct": item.is_correct(q, a["label"] if a else None), "elapsed_s": float(r.get("elapsed_s") or 0.0),
             "cost_usd": float(r.get("cost_usd") or 0.0), "input_tokens": int(u.get("input_tokens") or 0),
             "output_tokens": int(u.get("output_tokens") or 0)}
        self.calls[(r["task"], r["item_id"], r["arm"], r.get("repeat", 0))] = c
        self.recent.append(c)
        if r["status"] != "ok":
            self.errors.append({**c, "detail": str(r.get("detail") or "")[:200]})

    def summary(self, now: str | None = None) -> dict:
        t_now = datetime.fromisoformat(now) if now else datetime.now(timezone.utc)
        minute_ago = (t_now - timedelta(seconds=60)).isoformat()
        rows = []
        by_row: dict[tuple, list[dict]] = {k: [] for k in self.planned}
        for c in self.calls.values():
            by_row[(c["task"], c["arm"])].append(c)
        for (task, arm), cs in by_row.items():
            done, planned = len(cs), self.planned[(task, arm)]
            failed: dict[str, int] = {}
            for c in cs:
                if c["status"] != "ok":
                    failed[c["status"]] = failed.get(c["status"], 0) + 1
            per_min = sum(1 for c in cs if c["ts"] >= minute_ago)
            times = [c["elapsed_s"] for c in cs]
            correct = sum(c["correct"] for c in cs)
            rows.append({"task": task, "arm": arm, "planned": planned, "done": done, "ok": done - sum(failed.values()),
                         "failed": failed, "correct": correct, "pct_right": correct / done if done else None,
                         "input_tokens": sum(c["input_tokens"] for c in cs),
                         "output_tokens": sum(c["output_tokens"] for c in cs),
                         "cost_usd": sum(c["cost_usd"] for c in cs), "p50_s": _pct(times, 0.5),
                         "p95_s": _pct(times, 0.95), "per_min": per_min,
                         "eta_s": (planned - done) / per_min * 60 if per_min and done < planned else None})
        rows.sort(key=lambda r: (r["task"], self.arms.index(r["arm"])))
        return {"updated_at": t_now.isoformat(), "planned_total": sum(self.planned.values()),
                "done_total": len(self.calls), "cost_total_usd": sum(r["cost_usd"] for r in rows),
                "failed_total": sum(sum(r["failed"].values()) for r in rows), "rows": rows,
                "recent": list(reversed(self.recent)), "errors": list(reversed(self.errors))}


class Run:
    """logs/runs/<name>/: calls.jsonl (every call, append only), run.json (what was run), summary.json (live)."""

    def __init__(self, folder: Path):
        self.folder = folder
        self.calls = folder / "calls.jsonl"
        self.meta_path = folder / "run.json"

    @classmethod
    def start(cls, root: Path, name: str, meta: dict) -> "Run":
        run = cls(root / name)
        run.folder.mkdir(parents=True, exist_ok=True)
        old = json.loads(run.meta_path.read_text()) if run.meta_path.exists() else None
        m = {**(old or {}), **meta, "name": name, "status": "running", "updated_at": _now(),
             "commit": _git("rev-parse", "HEAD"), "dirty": bool(_git("status", "--porcelain", "--untracked-files=no"))}
        if old:
            m["resumed"] = old.get("resumed", 0) + 1
            m.setdefault("started_at", old.get("started_at"))
        else:
            m.update(started_at=_now(), resumed=0)
        run._write(run.meta_path, m)
        return run

    def meta(self) -> dict:
        return json.loads(self.meta_path.read_text())

    def write_summary(self, stats: RunStats) -> dict:
        s = {"run": self.meta(), **stats.summary()}
        self._write(self.folder / "summary.json", s)
        return s

    def finish(self, stats: RunStats, status: str = "complete") -> None:
        m = {**self.meta(), "status": status, "ended_at": _now(), "updated_at": _now()}
        self._write(self.meta_path, m)
        self.write_summary(stats)

    @staticmethod
    def _write(path: Path, data: dict) -> None:
        tmp = path.with_suffix(".tmp")
        tmp.write_text(json.dumps(data, indent=1, ensure_ascii=False) + "\n")
        os.replace(tmp, path)  # a reader never sees half a file


def list_runs(root: Path) -> list[dict]:
    runs = [json.loads(p.read_text()) for p in root.glob("*/run.json")] if root.exists() else []
    return sorted(runs, key=lambda m: m.get("started_at", ""), reverse=True)
