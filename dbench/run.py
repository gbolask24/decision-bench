"""Call the systems on items and log every call as one JSON line."""
from __future__ import annotations

import hashlib
import json
import math
import os
import random
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path

from . import adapters
from .items import Item
from .prices import cost_usd

ARMS = {
    "jev": {"system": "jev", "model": "jev-1.14.0"},
    "decisions": {"system": "decisions", "model": "gpt-6-luna"},
    "opus-low": {"system": "opus", "model": "claude-opus-5-5", "effort": "low"},
    "opus-medium": {"system": "opus", "model": "claude-opus-5-5", "effort": "medium"},
}
# Pre-registered: Opus runs on a fixed one-in-ten sample of each test, the first tenth in the seeded race order.
SAMPLED_ARMS = {"opus-low": 0.1, "opus-medium": 0.1}
RETRYABLE = {408, 409, 425, 429, 500, 502, 503, 504, 529}
MAX_RETRIES = 3
TIMEOUT_S = 120

_local = threading.local()


def _session():
    import requests  # imported here so the scorer and tests run without it
    if not hasattr(_local, "s"):
        _local.s = requests.Session()  # one keep-alive session per thread, the same client for all systems
    return _local.s


def build(arm: str, item: Item, data_dir: Path) -> tuple[str, dict, dict]:
    cfg = ARMS[arm]
    if cfg["system"] == "jev":
        payload, extra = adapters.jev_request(item, data_dir, cfg["model"])
        url = os.environ.get("JEV_URL", adapters.JEV_URL)
        headers = {"Authorization": f"Bearer {os.environ.get('TYPESAFE_API_KEY', '')}", **extra}
    elif cfg["system"] == "decisions":
        payload, extra = adapters.decisions_request(item, data_dir, cfg["model"])
        url = adapters.DECISIONS_URL
        headers = {"Authorization": f"Bearer {os.environ.get('OPENAI_API_KEY', '')}", **extra}
    else:
        payload, extra = adapters.opus_request(item, data_dir, cfg["model"], cfg["effort"])
        url = adapters.ANTHROPIC_URL
        headers = {"x-api-key": os.environ.get("ANTHROPIC_API_KEY", ""), **extra}
    headers["Content-Type"] = "application/json"
    return url, headers, payload


def parse(arm: str, raw: dict, item: Item) -> adapters.Parsed:
    system = ARMS[arm]["system"]
    return {"jev": adapters.parse_jev, "decisions": adapters.parse_decisions, "opus": adapters.parse_opus}[system](raw, item)


def post(url: str, headers: dict, payload: dict) -> dict:
    """POST with retries on transport errors only. Latency is the wall-clock time of the final attempt."""
    import requests
    body = json.dumps(payload).encode()
    attempts, last = 0, {}
    while True:
        attempts += 1
        start = time.perf_counter()
        try:
            r = _session().post(url, data=body, headers=headers, timeout=TIMEOUT_S)
            latency = time.perf_counter() - start
            last = {"http_status": r.status_code, "latency_s": latency, "attempts": attempts, "text": r.text}
            if r.status_code not in RETRYABLE:
                return last
            wait = float(r.headers.get("retry-after") or 2 ** attempts)
        except (requests.Timeout, requests.ConnectionError) as e:
            last = {"http_status": None, "latency_s": time.perf_counter() - start, "attempts": attempts,
                    "text": f"{type(e).__name__}: {e}"}
            wait = 2 ** attempts
        if attempts > MAX_RETRIES:
            return last
        time.sleep(min(wait, 30))


def call(arm: str, item: Item, data_dir: Path) -> dict:
    url, headers, payload = build(arm, item, data_dir)
    started_at = datetime.now(timezone.utc).isoformat()
    t0 = time.perf_counter()
    res = post(url, headers, payload)
    record = {"arm": arm, "model_requested": ARMS[arm]["model"], "effort": ARMS[arm].get("effort"),
              "started_at": started_at, "elapsed_s": time.perf_counter() - t0,  # elapsed includes retries
              "http_status": res["http_status"], "attempts": res["attempts"], "latency_s": res["latency_s"],
              "headers_sent": sorted(k for k in headers if k.lower().startswith("typesafe-")),
              "payload_sha256": hashlib.sha256(json.dumps(payload, sort_keys=True).encode()).hexdigest(),
              "payload": adapters.strip_images(payload)}
    if res["http_status"] != 200:
        status = "transport_error" if res["http_status"] in RETRYABLE or res["http_status"] is None else "http_error"
        return {**record, "status": status, "detail": res["text"][:500], "answers": {}, "cost_usd": 0.0}
    try:
        raw = json.loads(res["text"])
    except ValueError:
        return {**record, "status": "invalid", "detail": "response is not JSON", "answers": {}, "cost_usd": 0.0}
    p = parse(arm, raw, item)
    system = ARMS[arm]["system"]
    return {**record, "status": p.status, "detail": p.detail, "model_returned": p.model,
            "answers": {k: asdict(v) for k, v in p.answers.items()},
            "usage": {"input_tokens": p.input_tokens, "output_tokens": p.output_tokens,
                      "cache_read_tokens": p.cache_read_tokens, "cache_write_tokens": p.cache_write_tokens},
            "cost_usd": cost_usd(system, p.input_tokens, p.output_tokens, p.cache_read_tokens, p.cache_write_tokens),
            "response": raw}


class Log:
    def __init__(self, path: Path):
        self.path, self.lock = path, threading.Lock()
        path.parent.mkdir(parents=True, exist_ok=True)

    def done(self) -> set[tuple]:
        if not self.path.exists():
            return set()
        out = set()
        for line in self.path.read_text().splitlines():
            r = json.loads(line)
            if r.get("status") != "transport_error":
                out.add((r["mode"], r["item_id"], r["arm"], r["repeat"], r.get("warmup", False)))
        return out

    def write(self, record: dict):
        with self.lock, open(self.path, "a") as f:
            f.write(json.dumps(record, ensure_ascii=False) + "\n")


def _stamp(record: dict, item: Item, mode: str, repeat: int, warmup: bool = False) -> dict:
    return {"ts": datetime.now(timezone.utc).isoformat(), "mode": mode, "task": item.task, "item_id": item.id,
            "split": item.split, "repeat": repeat, "warmup": warmup, **record}


def seeded_order(items: list[Item], seed: int = 1017) -> list[Item]:
    """The order a test's items are raced in: sorted by id, then shuffled by seed."""
    order = sorted(items, key=lambda i: i.id)
    random.Random(seed).shuffle(order)
    return order


def arm_subsets(items_by_task: dict[str, list[Item]], seed: int = 1017) -> dict[str, set[str]]:
    """For each sampled arm, the ids it is sent: the first tenth (rounded up) of each test in the seeded order.
    T3 takes T2's sampled products (those with an image), so the with-and-without-image comparison stays paired.
    Pass a whole split per test, so a limited or latency run never reaches beyond the sample."""
    out = {}
    for arm, frac in SAMPLED_ARMS.items():
        ids: set[str] = set()
        for task, its in items_by_task.items():
            if task == "T3" and "T2" in items_by_task:
                continue
            ids |= {i.id for i in seeded_order(its, seed)[: math.ceil(len(its) * frac)]}
        if "T3" in items_by_task and "T2" in items_by_task:
            t3 = {i.id for i in items_by_task["T3"]}
            ids |= {"T3-" + i[3:] for i in ids if i.startswith("T2-")} & t3
        out[arm] = ids
    return out


def _allowed(arm: str, item: Item, only: dict[str, set[str]] | None) -> bool:
    return not only or arm not in only or item.id in only[arm]


def run_accuracy(items: list[Item], arms: list[str], data_dir: Path, log: Log, workers: int = 8,
                 repeats: int = 1, seed: int = 1017, on_record=None, only: dict[str, set[str]] | None = None) -> int:
    done = log.done()
    jobs = [(i, a, r) for i in items for a in arms for r in range(repeats)
            if ("accuracy", i.id, a, r, False) not in done and _allowed(a, i, only)]
    random.Random(seed).shuffle(jobs)  # interleaves systems so load and time of day fall on all of them

    def work(job):
        item, arm, rep = job
        rec = _stamp(call(arm, item, data_dir), item, "accuracy", rep)
        log.write(rec)
        if on_record:
            on_record(rec)

    with ThreadPoolExecutor(max_workers=workers) as ex:
        list(ex.map(work, jobs))
    return len(jobs)


def run_latency(items: list[Item], arms: list[str], data_dir: Path, log: Log, n: int = 300, warmup: int = 20,
                window: str = "w1", seed: int = 1017, only: dict[str, set[str]] | None = None) -> int:
    """One request at a time. Each item goes to every arm in a random order, within seconds of each other."""
    rng = random.Random(f"{seed}:{window}")
    pool = rng.sample(items, min(len(items), n + warmup))
    calls = 0
    for k, item in enumerate(pool):
        order = list(arms)
        rng.shuffle(order)
        for arm in order:
            if not _allowed(arm, item, only):
                continue
            rec = _stamp(call(arm, item, data_dir), item, "latency", 0, warmup=k < warmup)
            rec["window"] = window
            log.write(rec)
            calls += 1
    return calls
