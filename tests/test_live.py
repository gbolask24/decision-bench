import json

import pytest

from dbench import live
from dbench.items import Item, Option, Question


def items(n=4, task="T1"):
    q = Question("intent", "What?", [Option("a", "A"), Option("b", "B")])
    return [Item(f"{task}-{k}", task, "test", "x", [q], {"intent": "a"}) for k in range(n)]


def rec(item_id, arm, label="a", status="ok", elapsed=1.0, cost=0.01, task="T1", ts="2026-10-18T09:00:00+00:00"):
    return {"ts": ts, "mode": "accuracy", "task": task, "item_id": item_id, "arm": arm, "repeat": 0, "status": status,
            "elapsed_s": elapsed, "cost_usd": cost, "detail": "" if status == "ok" else "HTTP 500 upstream",
            "usage": {"input_tokens": 100, "output_tokens": 5, "cache_read_tokens": 0, "cache_write_tokens": 0},
            "answers": {"intent": {"label": label, "probs": {label: 0.9}}} if status == "ok" else {}}


def stats():
    its = items()
    return live.RunStats({"T1": its}, {"T1": "intent"}, ["jev", "opus-low"], repeats=1), its


def row(summary, task, arm):
    return next(r for r in summary["rows"] if r["task"] == task and r["arm"] == arm)


def test_rows_count_calls_correct_tokens_cost_and_failures():
    s, its = stats()
    s.add(rec(its[0].id, "jev", "a", elapsed=0.2))
    s.add(rec(its[1].id, "jev", "b", elapsed=0.4))
    s.add(rec(its[2].id, "jev", status="http_error"))
    r = row(s.summary(), "T1", "jev")
    assert (r["planned"], r["done"], r["ok"], r["correct"]) == (4, 3, 2, 1)
    assert r["pct_right"] == pytest.approx(1 / 3)  # a failed call counts as made, not right
    assert r["failed"] == {"http_error": 1}
    assert (r["input_tokens"], r["output_tokens"]) == (300, 15)
    assert r["cost_usd"] == pytest.approx(0.03)
    assert r["p50_s"] == pytest.approx(0.4)
    assert row(s.summary(), "T1", "opus-low")["done"] == 0


def test_totals_recent_calls_and_errors():
    s, its = stats()
    s.add(rec(its[0].id, "jev"))
    s.add(rec(its[0].id, "opus-low", status="refusal"))
    out = s.summary()
    assert out["planned_total"] == 8 and out["done_total"] == 2
    assert out["cost_total_usd"] == pytest.approx(0.02)
    assert [c["arm"] for c in out["recent"]] == ["opus-low", "jev"]  # newest first
    assert out["errors"][0]["status"] == "refusal" and out["errors"][0]["item_id"] == its[0].id
    json.dumps(out)


def test_records_outside_the_run_are_ignored():
    s, its = stats()
    s.add(rec("T9-x", "jev"))
    s.add({**rec(its[0].id, "jev"), "mode": "latency"})
    assert s.summary()["done_total"] == 0


def test_a_retried_transport_error_is_replaced_by_the_retry():
    s, its = stats()
    s.add(rec(its[0].id, "jev", status="transport_error"))
    assert row(s.summary(), "T1", "jev")["failed"] == {"transport_error": 1}
    s.add(rec(its[0].id, "jev"))  # a resumed run retries it
    r = row(s.summary(), "T1", "jev")
    assert (r["done"], r["correct"], r["failed"]) == (1, 1, {})


def test_rate_and_time_left_come_from_the_last_minute():
    s, its = stats()
    for k in range(3):
        s.add(rec(its[k].id, "jev", ts=f"2026-10-18T09:00:{10 * k:02d}+00:00"))
    r = row(s.summary(now="2026-10-18T09:00:30+00:00"), "T1", "jev")
    assert r["per_min"] == 3 and r["eta_s"] == pytest.approx(20)  # one left at 3 a minute


def test_run_folder_writes_run_json_and_summary(tmp_path):
    run = live.Run.start(tmp_path, "pilot", {"split": "dev", "tasks": ["T1"], "arms": ["jev"], "command": "x"})
    assert run.calls.parent == tmp_path / "pilot"
    meta = json.loads((tmp_path / "pilot" / "run.json").read_text())
    assert meta["status"] == "running" and meta["name"] == "pilot" and "started_at" in meta and "commit" in meta
    s, _ = stats()
    run.write_summary(s)
    assert json.loads((tmp_path / "pilot" / "summary.json").read_text())["run"]["name"] == "pilot"
    run.finish(s)
    assert json.loads((tmp_path / "pilot" / "run.json").read_text())["status"] == "complete"
    again = live.Run.start(tmp_path, "pilot", {"split": "dev", "tasks": ["T1"], "arms": ["jev"], "command": "x"})
    assert json.loads((tmp_path / "pilot" / "run.json").read_text())["resumed"] == 1  # same folder, never a new one
    assert again.calls == run.calls


def test_list_runs_newest_first(tmp_path):
    live.Run.start(tmp_path, "a", {"command": "x"})
    live.Run.start(tmp_path, "b", {"command": "x"})
    assert [r["name"] for r in live.list_runs(tmp_path)] == ["b", "a"]


def test_run_command_logs_into_the_run_folder_and_keeps_the_summary(tmp_path, monkeypatch):
    from dbench import run as runner
    from dbench.__main__ import items_path, main
    from dbench.items import write_items
    data = tmp_path / "data"
    for t in ("T1", "T4"):
        write_items(items_path(data, t), [Item(f"{t}-{k}", t, "dev", "x",
                    [Question("intent", "What?", [Option("a", "A"), Option("b", "B")])], {"intent": "a"}) for k in range(3)])
    monkeypatch.setattr(runner, "call", lambda arm, item, d: {
        "arm": arm, "status": "ok", "elapsed_s": 0.1, "cost_usd": 0.001,
        "answers": {"intent": {"label": "a", "probs": {"a": 1.0}}}})
    monkeypatch.setattr("dbench.__main__.load_env", lambda: None)
    args = ["--data", str(data), "run", "--task", "T1,T4", "--split", "dev", "--arms", "jev,opus-low",
            "--run", "pilot", "--runs-root", str(tmp_path / "runs")]
    assert main(args) == 0
    folder = tmp_path / "runs" / "pilot"
    assert len((folder / "calls.jsonl").read_text().splitlines()) == 12
    s = json.loads((folder / "summary.json").read_text())
    assert s["run"]["status"] == "complete" and s["run"]["tasks"] == ["T1", "T4"] and s["done_total"] == 12
    assert {(r["task"], r["arm"], r["pct_right"]) for r in s["rows"]} == {
        (t, a, 1.0) for t in ("T1", "T4") for a in ("jev", "opus-low")}
    assert main(args) == 0  # a second run with the same name resumes: nothing left to call
    assert len((folder / "calls.jsonl").read_text().splitlines()) == 12
    assert json.loads((folder / "run.json").read_text())["resumed"] == 1
