"""python -m dbench <command>. Commands: sample, manifest, probe, run, latency, score, export, replay, summary, watch."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from . import run as runner
from . import sample, score
from .items import Image, read_items, sha256_file, write_items

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
        more = sample.amazon_extend(pool, {r["parent_asin"] for r in draw}, a.extend) if a.extend else []
        images, failed = {}, []
        for r in draw + more:
            asin = r["parent_asin"]
            dest = data / "images" / "T3" / f"{asin}.jpg"
            try:
                images[asin] = (Image(str(dest.relative_to(data)), "image/jpeg", sha256_file(dest)) if dest.exists()
                                else sample.fetch_image(sample.main_image(r), dest, data))
            except Exception as e:  # a dead link drops the product from T3 only; it is reported
                failed.append(f"{asin} {type(e).__name__}")
        items, cats = sample.t2_t3_amazon(pool, draw, image_paths=images)
        items += sample.t2_t3_amazon(pool, more, n_test=len(more), image_paths=images)[0]
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


def cmd_fit_images(a):
    from .images import fit_items
    data = Path(a.data)
    for t in a.tasks:
        n = fit_items(data, items_path(data, t))
        print(f"{t}: {n} images brought inside Jev's limits; hashes rewritten")
    print("re-run `python -m dbench manifest` so the manifest matches")


def _items(a, split, task=None):
    its = [i for i in read_items(items_path(Path(a.data), task or a.task)) if i.split == split]
    return its[: a.limit] if getattr(a, "limit", None) else its


def probe_item(items: list, with_images: bool):
    """The item a probe sends: the first one, or the first with an image."""
    pool = [i for i in items if i.images] if with_images else items
    if not pool:
        raise SystemExit("probe: no matching item in that split")
    return pool[0]


def cmd_probe(a):
    load_env()
    # A probe checks request shapes and parsing only; T5 has no dev split, so its probe uses one test item,
    # whose status is checked and which nothing is tuned on (recorded in PREREGISTRATION.md).
    item = probe_item(_items(a, a.split), a.with_images)
    for arm in a.arms.split(","):
        rec = runner.call(arm, item, Path(a.data))
        print(json.dumps({k: rec.get(k) for k in ("arm", "status", "http_status", "detail", "model_returned",
                                                   "answers", "usage", "cost_usd", "latency_s")},
                         indent=1, ensure_ascii=False)[:3000])
        if rec["status"] != "ok":
            print("response:", json.dumps(rec.get("response"), ensure_ascii=False)[:2000])


def cmd_run(a):
    load_env()
    tasks, arms = a.task.split(","), a.arms.split(",")
    unknown = [t for t in tasks if t not in TASKS]
    if unknown:
        raise SystemExit(f"run: unknown test {', '.join(unknown)}")
    by_task = {t: _items(a, a.split, t) for t in tasks}
    items = [i for its in by_task.values() for i in its]
    if not a.run:
        n = runner.run_accuracy(items, arms, Path(a.data), runner.Log(Path(a.log)), workers=a.workers, repeats=a.repeats)
        print(f"{n} calls written to {a.log}")
        return
    import threading
    import time
    from .live import Run
    run = Run.start(Path(a.runs_root), a.run, {"split": a.split, "tasks": tasks, "arms": arms, "repeats": a.repeats,
                                                "workers": a.workers, "command": " ".join(["python -m dbench"] + sys.argv[1:])})
    stats = _run_stats(run, Path(a.data))
    run.write_summary(stats)
    lock, last = threading.Lock(), [0.0]

    def on_record(rec):
        with lock:
            stats.add(rec)
            if time.monotonic() - last[0] >= 2:
                run.write_summary(stats)
                last[0] = time.monotonic()

    try:
        n = runner.run_accuracy(items, arms, Path(a.data), runner.Log(run.calls), workers=a.workers,
                                repeats=a.repeats, on_record=on_record)
    except BaseException:
        run.finish(stats, "stopped")
        raise
    run.finish(stats)
    print(f"{n} calls written to {run.calls}")


def _run_stats(run, data: Path):
    from .live import RunStats
    m = run.meta()
    by_task = {t: [i for i in read_items(items_path(data, t)) if i.split == m.get("split", "test")] for t in m["tasks"]}
    stats = RunStats(by_task, {t: TASKS[t] for t in m["tasks"]}, m["arms"], m.get("repeats", 1))
    if run.calls.exists():
        for line in run.calls.read_text().splitlines():
            stats.add(json.loads(line))
    return stats


def cmd_summary(a):
    from .live import Run
    run = Run(Path(a.runs_root) / a.run)
    s = run.write_summary(_run_stats(run, Path(a.data)))
    print(f"{run.folder / 'summary.json'}: {s['done_total']} of {s['planned_total']} calls, ${s['cost_total_usd']:.2f}")


def cmd_watch(a):
    from .watch import make_server
    srv = make_server(Path(a.runs_root), a.port)
    print(f"Watching {a.runs_root} at http://127.0.0.1:{srv.server_address[1]}  (Ctrl+C to stop)")
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        pass


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


def cmd_replay(a):
    from .replay import REQUIRED_META, ReplayError, build_replay
    cfg = json.loads(Path(a.config).read_text())
    missing = [f for f in REQUIRED_META if not cfg.get(f)]
    if missing:  # checked before any file is read, so an unfinished config fails fast and clearly
        print(f"replay: config is missing {', '.join(missing)}")
        return 1
    data = Path(a.data)
    summary = json.loads(Path(a.summary).read_text())
    tests = {r["test"] for r in cfg["races"].values()} | ({cfg["spotlight"]["test"]} if cfg.get("spotlight") else set())
    tests |= set(summary.get("tasks", {}))  # totals cover every scored test, not only the raced ones
    items = {t: read_items(items_path(data, t)) for t in tests}
    out = Path(a.out)
    try:
        replay = build_replay(cfg, items, score.load_logs([Path(p) for p in a.logs]), summary, data, out)
    except ReplayError as e:
        print(f"replay: {e}")
        return 1
    out.mkdir(parents=True, exist_ok=True)
    (out / "replay.json").write_text(json.dumps(replay, indent=1, ensure_ascii=False) + "\n")
    print(f"wrote {out / 'replay.json'}")


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
    s.add_argument("--extend", type=int, default=1000,
                   help="T2T3: test products drawn after the first 1,050, by their own seed (pre-registered: 1,000)")
    s.add_argument("--exclude", help="file of parent_asin values to leave out (the SKU-50 items)")
    s.add_argument("--clinc")
    s.add_argument("--bench-repo", default="../atlanai-decision-bench")
    m = sub.add_parser("manifest")
    m.add_argument("--out", default="manifest.json")
    for name in ("probe", "run"):
        p = sub.add_parser(name)
        if name == "probe":
            p.add_argument("--task", required=True, choices=list(TASKS))
        else:
            p.add_argument("--task", required=True, help="one test, or several joined by commas: T1,T4")
        p.add_argument("--arms", default="jev,decisions,opus-low")
        if name == "probe":
            p.add_argument("--split", default="dev", choices=["dev", "test"])
            p.add_argument("--with-images", action="store_true")
        if name == "run":
            p.add_argument("--split", default="test", choices=["test", "dev"])
            p.add_argument("--workers", type=int, default=8)
            p.add_argument("--repeats", type=int, default=1)
            p.add_argument("--limit", type=int)
            p.add_argument("--log", default="logs/accuracy.jsonl", help="used only without --run")
            p.add_argument("--run", help="log into logs/runs/<name>/ with run.json and a live summary.json")
            p.add_argument("--runs-root", default="logs/runs")
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
    fi = sub.add_parser("fit-images", help="pad or shrink images to Jev's 280-1568 px limits; same file for every system")
    fi.add_argument("--tasks", nargs="+", default=["T3", "T5"])
    sm = sub.add_parser("summary", help="rebuild a run's summary.json from its calls")
    sm.add_argument("--run", required=True)
    sm.add_argument("--runs-root", default="logs/runs")
    w = sub.add_parser("watch", help="local page that follows runs live")
    w.add_argument("--runs-root", default="logs/runs")
    w.add_argument("--port", type=int, default=8765)
    rp = sub.add_parser("replay", help="write replay.json for a race video")
    rp.add_argument("--config", required=True)
    rp.add_argument("--logs", nargs="+", default=["logs/accuracy.jsonl"])
    rp.add_argument("--summary", default="results/summary.json")
    rp.add_argument("--out", default="results/replay")
    a = ap.parse_args(argv)
    return {"sample": cmd_sample, "manifest": cmd_manifest, "probe": cmd_probe, "run": cmd_run,
            "latency": cmd_latency, "score": cmd_score, "export": cmd_export, "replay": cmd_replay,
            "fit-images": cmd_fit_images, "summary": cmd_summary, "watch": cmd_watch}[a.cmd](a) or 0


if __name__ == "__main__":
    sys.exit(main())
