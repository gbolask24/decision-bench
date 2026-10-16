"""python -m dbench <command>. Commands: sample, manifest, probe, run, latency, score, export."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from . import run as runner
from . import sample, score
from .items import read_items, sha256_file, write_items

TASKS = {  # task -> question scored as primary (None = each item's own question)
    "T1": "intent", "T2": "category", "T3": "category", "T4": "intent", "T5": None,
}
SECONDARY = {"T1": ["category"]}


def load_env(path: Path = Path(".env")):
    import os
    if path.exists():
        for line in path.read_text().splitlines():
            if "=" in line and not line.lstrip().startswith("#"):
                k, v = line.split("=", 1)
                os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))


def items_path(data: Path, task: str) -> Path:
    return data / "items" / f"{task}.jsonl"


def cmd_sample(a):
    data = Path(a.data)
    if a.task == "T1":
        csv_path = Path(a.bitext_csv) if a.bitext_csv else data / "raw" / "bitext.csv"
        if not csv_path.exists():
            import requests
            csv_path.parent.mkdir(parents=True, exist_ok=True)
            csv_path.write_bytes(requests.get(sample.BITEXT_URL, timeout=120).content)
        items = sample.t1_bitext(sample.read_bitext(csv_path))
        print("T1", write_items(items_path(data, "T1"), items), len(items))
    elif a.task == "T2T3":
        exclude = frozenset(Path(a.exclude).read_text().split()) if a.exclude else frozenset()
        pool = sample.amazon_pool(sample.stream_jsonl_gz(a.amazon or sample.AMAZON_URL), exclude)
        draw = sample.amazon_draw(pool)
        images, failed = {}, []
        for r in draw:
            asin = r["parent_asin"]
            try:
                images[asin] = sample.fetch_image(sample.main_image(r), data / "images" / "T3" / f"{asin}.jpg", data)
            except Exception as e:  # a dead link drops the product from T3 only; it is reported
                failed.append(f"{asin} {type(e).__name__}")
        items, cats = sample.t2_t3_amazon(pool, draw, image_paths=images)
        (data / "items").mkdir(parents=True, exist_ok=True)
        (data / "items" / "T2-categories.txt").write_text("\n".join(cats) + "\n")
        (data / "items" / "T3-image-failures.txt").write_text("\n".join(failed) + ("\n" if failed else ""))
        for t in ("T2", "T3"):
            sub = [i for i in items if i.task == t]
            print(t, write_items(items_path(data, t), sub), len(sub))
        print(f"pool {len(pool)}, categories {len(cats)}, image failures {len(failed)}")
    elif a.task == "T4":
        src = Path(a.clinc) if a.clinc else data / "raw" / "clinc_full.json"
        if not src.exists():
            import requests
            src.parent.mkdir(parents=True, exist_ok=True)
            src.write_bytes(requests.get(sample.CLINC_URL, timeout=120).content)
        items = sample.t4_clinc(json.loads(src.read_text()))
        print("T4", write_items(items_path(data, "T4"), items), len(items))
    elif a.task == "T5":
        repo = Path(a.bench_repo)
        cases_file = repo / "data" / "corpus" / "bench-v4" / "cases.jsonl"
        cases = [json.loads(l) for l in cases_file.read_text().splitlines() if l.strip()]
        items = sample.t5_decision_bench(cases, repo, data)
        print("T5", write_items(items_path(data, "T5"), items), len(items))


def cmd_manifest(a):
    data = Path(a.data)
    files = sorted((data / "items").glob("*"))
    images = sorted((data / "images").rglob("*.*")) if (data / "images").exists() else []
    man = {"items": {f.name: sha256_file(f) for f in files},
           "images": {str(f.relative_to(data)): sha256_file(f) for f in images}}
    out = Path(a.out)
    out.write_text(json.dumps(man, indent=1, sort_keys=True) + "\n")
    print(f"wrote {out}: {len(man['items'])} item files, {len(man['images'])} images")


def _items(a, split):
    its = [i for i in read_items(items_path(Path(a.data), a.task)) if i.split == split]
    return its[: a.limit] if getattr(a, "limit", None) else its


def cmd_probe(a):
    load_env()
    item = _items(a, "dev")[0]
    for arm in a.arms.split(","):
        rec = runner.call(arm, item, Path(a.data))
        print(json.dumps({k: rec.get(k) for k in ("arm", "status", "http_status", "detail", "model_returned",
                                                   "answers", "usage", "cost_usd", "latency_s")},
                         indent=1, ensure_ascii=False)[:3000])
        if rec["status"] != "ok":
            print("response:", json.dumps(rec.get("response"), ensure_ascii=False)[:2000])


def cmd_run(a):
    load_env()
    items = _items(a, a.split)
    n = runner.run_accuracy(items, a.arms.split(","), Path(a.data), runner.Log(Path(a.log)),
                            workers=a.workers, repeats=a.repeats)
    print(f"{n} calls written to {a.log}")


def cmd_latency(a):
    load_env()
    items = []
    for t in a.tasks.split(","):
        items += [i for i in read_items(items_path(Path(a.data), t)) if i.split == "test"]
    n = runner.run_latency(items, a.arms.split(","), Path(a.data), runner.Log(Path(a.log)), n=a.n, window=a.window)
    print(f"{n} calls written to {a.log}")


def cmd_score(a):
    data = Path(a.data)
    records = score.load_logs([Path(p) for p in a.logs])
    arms = a.arms.split(",")
    out = {"tasks": {}, "latency": score.latency(records, arms, a.resamples)}
    rows_by_task = {}
    for task, question in TASKS.items():
        path = items_path(data, task)
        if not path.exists():
            continue
        items = [i for i in read_items(path) if i.split == "test"]
        accept_file = data / "items" / "T2-accept.json"  # {gold category: [other categories also counted right]}
        if task in ("T2", "T3") and accept_file.exists():
            accept = json.loads(accept_file.read_text())
            for i in items:
                i.accept = {"category": accept.get(i.gold["category"], [])}
        rows = score.item_rows(items, records, question, arms)
        rows_by_task[task] = rows
        t = {"primary": score.summarise(rows, arms, a.resamples), "stability": score.flip_rate(
            [r for r in records if r["task"] == task], question, arms)}
        for q2 in SECONDARY.get(task, []):
            t[q2] = score.summarise(score.item_rows(items, records, q2, arms), arms, a.resamples)
        out["tasks"][task] = t
    if "T2" in rows_by_task and "T3" in rows_by_task:
        out["image_effect_T3_minus_T2"] = score.image_effect(rows_by_task["T2"], rows_by_task["T3"], arms, a.resamples)
    Path(a.out).parent.mkdir(parents=True, exist_ok=True)
    Path(a.out).write_text(json.dumps(out, indent=1) + "\n")
    print(f"wrote {a.out}")


def cmd_export(a):
    from .export import export
    for f in export(Path(a.data), [Path(p) for p in a.logs], Path(a.out)):
        print(f)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="dbench", description=__doc__)
    ap.add_argument("--data", default="data")
    sub = ap.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("sample")
    s.add_argument("task", choices=["T1", "T2T3", "T4", "T5"])
    s.add_argument("--bitext-csv")
    s.add_argument("--amazon", help="local meta_Tools_and_Home_Improvement.jsonl.gz, or the URL (default)")
    s.add_argument("--exclude", help="file of parent_asin values to leave out (the SKU-50 items)")
    s.add_argument("--clinc")
    s.add_argument("--bench-repo", default="../decision-bench")
    m = sub.add_parser("manifest")
    m.add_argument("--out", default="manifest.json")
    for name in ("probe", "run"):
        p = sub.add_parser(name)
        p.add_argument("--task", required=True, choices=list(TASKS))
        p.add_argument("--arms", default="jev,decisions,opus-low")
        if name == "run":
            p.add_argument("--split", default="test", choices=["test", "dev"])
            p.add_argument("--workers", type=int, default=8)
            p.add_argument("--repeats", type=int, default=1)
            p.add_argument("--limit", type=int)
            p.add_argument("--log", default="logs/accuracy.jsonl")
    l = sub.add_parser("latency")
    l.add_argument("--tasks", default="T1,T2,T3,T4,T5")
    l.add_argument("--arms", default="jev,decisions,opus-low")
    l.add_argument("--n", type=int, default=300)
    l.add_argument("--window", default="w1")
    l.add_argument("--log", default="logs/latency.jsonl")
    sc = sub.add_parser("score")
    sc.add_argument("logs", nargs="+")
    sc.add_argument("--arms", default="jev,decisions,opus-low")
    sc.add_argument("--resamples", type=int, default=10_000)
    sc.add_argument("--out", default="results/summary.json")
    e = sub.add_parser("export", help="public copies of items and logs, without Amazon text or images")
    e.add_argument("logs", nargs="*")
    e.add_argument("--out", default="public")
    a = ap.parse_args(argv)
    {"sample": cmd_sample, "manifest": cmd_manifest, "probe": cmd_probe, "run": cmd_run,
     "latency": cmd_latency, "score": cmd_score, "export": cmd_export}[a.cmd](a)
    return 0


if __name__ == "__main__":
    sys.exit(main())
