"""Build replay.json, the one file a race video is drawn from. Every number is copied from the logs or the scorer."""
from __future__ import annotations

import random
import shutil
from datetime import datetime, timezone
from pathlib import Path

from .items import Item
from .run import seeded_order

SCHEMA = "bench-replay/1"
REQUIRED_META = ("title", "run_date", "commit", "logs_url", "repo_url", "selection_rule")
PREVIEW_CHARS = 80


class ReplayError(Exception):
    pass


def _preview(text: str) -> str:
    line = " ".join(text.split())
    return line if len(line) <= PREVIEW_CHARS else line[: PREVIEW_CHARS - 1] + "…"


def _first(records: list[dict], task: str) -> dict[tuple[str, str], dict]:
    out = {}
    for r in records:
        if r.get("mode") == "accuracy" and r.get("repeat") == 0 and r.get("task") == task:
            out.setdefault((r["item_id"], r["arm"]), r)
    return out


def _call(item: Item, question: str, r: dict, start_s: float, show: bool) -> dict:
    a = (r.get("answers") or {}).get(question) if r["status"] == "ok" else None
    label = a["label"] if a else None
    return {"item_id": item.id, "started_at": r.get("started_at"), "start_s": round(start_s, 3),
            "elapsed_s": float(r.get("elapsed_s", r.get("latency_s", 0.0))), "status": r["status"],
            "label": label, "correct": item.is_correct(question, label), "cost_usd": float(r.get("cost_usd") or 0.0),
            "text_preview": _preview(item.text) if show else ""}


def build_race(spec: dict, items: list[Item], records: list[dict], systems: list[dict], seed: int) -> dict:
    """Each system's logged calls laid end to end in one seeded item order, cut where the race span ends."""
    span = spec["segments"][-1]["to_s"]
    test_items = [i for i in items if i.split == "test"]
    order = seeded_order(test_items, seed)  # the same order the Opus sample is cut from
    first = _first(records, spec["test"])
    calls = {}
    for s in systems:
        t, lane = 0.0, []
        for it in order:
            r = first.get((it.id, s["id"]))
            if r is None:
                continue
            if t >= span:
                break
            c = _call(it, spec["question"], r, t, spec["show_items"])
            lane.append(c)
            t += c["elapsed_s"]
        calls[s["id"]] = lane
    return {"test": spec["test"], "label": spec["label"], "n_items": len(test_items),
            "show_items": spec["show_items"], "placeholder": spec.get("placeholder", ""),
            "segments": spec["segments"], "calls": calls}


def build_spotlight(spec: dict, items: list[Item], records: list[dict], systems: list[dict], seed: int,
                    data_dir: Path, out_dir: Path) -> dict:
    """One image item, drawn by seed from those whose source licence allows reuse; the image is copied out."""
    allowed = set(spec["allowed_licences"])
    first = _first(records, spec["test"])
    answered = lambda i: all((i.id, s["id"]) in first for s in systems)  # Opus answers only its sample
    pool = sorted((i for i in items if i.images and spec["licences"].get(i.source.get("task")) in allowed and answered(i)),
                  key=lambda i: i.id)
    if not pool:
        raise ReplayError(f"no {spec['test']} image item with an allowed licence")
    item = random.Random(seed).choice(pool)
    img = item.images[0]
    dest = out_dir / "assets" / Path(img.path).name
    dest.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(data_dir / img.path, dest)
    q = item.questions[0]
    first = _first(records, spec["test"])
    picks = []
    for s in systems:
        r = first.get((item.id, s["id"]))
        a = (r.get("answers") or {}).get(q.name) if r and r["status"] == "ok" else None
        label = a["label"] if a else None
        conf = a["probs"].get(label) if a and a.get("probs") else None
        picks.append({"system": s["id"], "label": label, "confidence": conf, "correct": item.is_correct(q.name, label),
                      "status": r["status"] if r else "missing"})
    return {"item_id": item.id, "test": spec["test"], "text": _preview(item.text), "question": q.instructions,
            "gold": item.gold[q.name], "image": str(dest.relative_to(out_dir)),
            "image_licence": spec["licences"][item.source["task"]], "image_source": item.source.get("task", ""),
            "picks": picks}


def build_totals(items_by_task: dict[str, list[Item]], records: list[dict], systems: list[dict]) -> dict:
    """Per test and system: logged calls on test items (first repeat), their summed time and cost.
    Accuracy is not recomputed here; the video takes it from the scorer."""
    out = {}
    for task, items in items_by_task.items():
        test_ids = {i.id for i in items if i.split == "test"}
        first = _first(records, task)
        out[task] = {}
        for s in systems:
            rs = [r for (iid, arm), r in first.items() if arm == s["id"] and iid in test_ids]
            out[task][s["id"]] = {"calls": len(rs),
                                  "elapsed_s": round(sum(float(r.get("elapsed_s", r.get("latency_s", 0.0))) for r in rs), 3),
                                  "cost_usd": round(sum(float(r.get("cost_usd") or 0.0) for r in rs), 8)}
    return out


def _merged(task: dict) -> dict:
    """The decision systems from every item, plus each sampled system (Opus) from its sample, with n and of
    so a reader can scale its totals and must label them."""
    t = dict(task["primary"])
    sample = task.get("sample")
    if not sample:
        return t
    extra = [a for a in sample["arms"] if a not in t["arms"]]
    t["arms"] = {**t["arms"], **{a: sample["arms"][a] for a in extra}}
    t["pairs"] = {**t.get("pairs", {}), **{k: v for k, v in sample.get("pairs", {}).items()
                                           if any(a in k.split(" vs ") for a in extra)}}
    t["sampled"] = {a: {"n": sample["n"], "of": sample["of"]} for a in extra}
    return t


def build_replay(config: dict, items_by_task: dict[str, list[Item]], records: list[dict], summary: dict,
                 data_dir: Path, out_dir: Path) -> dict:
    for field in REQUIRED_META:
        if not config.get(field):
            raise ReplayError(f"config is missing {field}")
    systems, seed = config["systems"], int(config.get("seed", 1017))
    races = {rid: build_race(spec, items_by_task[spec["test"]], records, systems, seed)
             for rid, spec in config["races"].items()}
    spotlight = None
    if config.get("spotlight"):
        spec = config["spotlight"]
        spotlight = build_spotlight(spec, items_by_task[spec["test"]], records, systems, seed, data_dir, out_dir)
    tests = {t: _merged(v) for t, v in summary.get("tasks", {}).items()}
    meta = {k: config[k] for k in REQUIRED_META}
    meta.update(tag=config.get("tag", ""), generated_at=datetime.now(timezone.utc).isoformat())
    results = {"tests": tests, "latency": summary.get("latency", {}), "totals": build_totals(items_by_task, records, systems)}
    if config.get("test_labels"):
        results["labels"] = config["test_labels"]
    return {"schema": SCHEMA, "meta": meta, "systems": systems, "scenes": config["scenes"], "races": races,
            "spotlight": spotlight, "results": results}
