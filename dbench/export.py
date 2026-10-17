"""Public copies of items and logs. Amazon listing text and images are not redistributed, so T2 and T3
items keep their ids, options and gold labels only, and their logged requests and responses are dropped."""
from __future__ import annotations

import json
from pathlib import Path

PRIVATE_TEXT_TASKS = {"T2", "T3"}


def public_item(d: dict) -> dict:
    if d["task"] in PRIVATE_TEXT_TASKS:
        d = {**d, "text": "[Amazon listing text: rebuild with python -m dbench sample T2T3]",
             "images": [{**i, "path": "[not redistributed]"} for i in d.get("images", [])]}
        d["source"] = {k: v for k, v in d.get("source", {}).items() if k != "image_url"}
    return d


def public_record(r: dict) -> dict:
    if r.get("task") in PRIVATE_TEXT_TASKS:
        r = {k: v for k, v in r.items() if k not in ("payload", "response")}
    return r


def export(data: Path, logs: list[Path], out: Path) -> list[Path]:
    written = []
    (out / "items").mkdir(parents=True, exist_ok=True)
    for f in sorted((data / "items").glob("*.jsonl")):
        rows = [public_item(json.loads(l)) for l in f.read_text().splitlines() if l.strip()]
        dest = out / "items" / f.name
        dest.write_text("".join(json.dumps(r, ensure_ascii=False, sort_keys=True) + "\n" for r in rows))
        written.append(dest)
    (out / "logs").mkdir(parents=True, exist_ok=True)
    for f in logs:
        rows = [public_record(json.loads(l)) for l in f.read_text().splitlines() if l.strip()]
        if f.name != "calls.jsonl":
            dest = out / "logs" / f.name
            dest.write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows))
            written.append(dest)
            continue
        # a run folder: one file per test keeps each under GitHub's file size limit; run.json and summary.json go along
        folder = out / "logs" / f.parent.name
        folder.mkdir(parents=True, exist_ok=True)
        by_task: dict[str, list[dict]] = {}
        for r in rows:
            by_task.setdefault(r.get("task", "unknown"), []).append(r)
        for task, rs in sorted(by_task.items()):
            dest = folder / f"{task}.jsonl"
            dest.write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rs))
            written.append(dest)
        for name in ("run.json", "summary.json"):
            if (f.parent / name).exists():
                (folder / name).write_bytes((f.parent / name).read_bytes())
                written.append(folder / name)
    return written
