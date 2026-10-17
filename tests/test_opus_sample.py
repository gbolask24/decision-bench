import json
import math

from dbench import run as runner
from dbench.items import Item, Option, Question


def items(task="T1", n=30, split="test"):
    qs = [Question(name, "What?", [Option("a", "A"), Option("b", "B")]) for name in ("intent", "category")]
    return [Item(f"{task}-{k:03d}", task, split, "x", qs, {"intent": "a", "category": "a"}) for k in range(n)]


def test_the_sample_is_the_first_tenth_of_each_test_in_the_race_order():
    by_task = {"T1": items("T1", 30), "T3": items("T3", 1999)}
    only = runner.arm_subsets(by_task)
    assert set(only) == {"opus-low", "opus-medium"}
    order = [i.id for i in runner.seeded_order(by_task["T1"])]
    assert {i for i in only["opus-low"] if i.startswith("T1")} == set(order[:3])
    assert sum(1 for i in only["opus-low"] if i.startswith("T3")) == math.ceil(1999 / 10) == 200
    assert only["opus-low"] == runner.arm_subsets(by_task)["opus-low"]  # seeded


def test_the_race_uses_the_same_order(tmp_path):
    from dbench.replay import build_race
    its = items("T1", 30)
    spec = {"test": "T1", "label": "x", "question": "intent", "show_items": False,
            "segments": [{"from_s": 0, "to_s": 1000, "speed": 1}]}
    recs = [{"mode": "accuracy", "repeat": 0, "task": "T1", "item_id": i.id, "arm": "jev", "status": "ok",
             "elapsed_s": 1.0, "answers": {"intent": {"label": "a"}}} for i in its]
    race = build_race(spec, its, recs, [{"id": "jev"}], 1017)
    assert [c["item_id"] for c in race["calls"]["jev"]] == [i.id for i in runner.seeded_order(its)]


def test_run_accuracy_sends_sampled_arms_only_their_items(tmp_path, monkeypatch):
    its = items("T1", 30)
    only = runner.arm_subsets({"T1": its})
    sent = []
    monkeypatch.setattr(runner, "call", lambda arm, item, d: sent.append((arm, item.id)) or
                        {"arm": arm, "status": "ok", "elapsed_s": 0.1, "answers": {}})
    runner.run_accuracy(its, ["jev", "opus-low"], tmp_path, runner.Log(tmp_path / "l.jsonl"), workers=1, only=only)
    assert sum(1 for a, _ in sent if a == "jev") == 30
    assert {i for a, i in sent if a == "opus-low"} == only["opus-low"] and len(only["opus-low"]) == 3


def test_run_latency_sends_sampled_arms_only_their_items(tmp_path, monkeypatch):
    its = items("T1", 40)
    only = runner.arm_subsets({"T1": its})
    sent = []
    monkeypatch.setattr(runner, "call", lambda arm, item, d: sent.append((arm, item.id)) or
                        {"arm": arm, "status": "ok", "elapsed_s": 0.1, "latency_s": 0.1, "answers": {}})
    runner.run_latency(its, ["jev", "opus-low"], tmp_path, runner.Log(tmp_path / "l.jsonl"), n=40, warmup=0, only=only)
    assert {i for a, i in sent if a == "opus-low"} <= only["opus-low"]
    assert sum(1 for a, _ in sent if a == "jev") == 40


def test_live_plan_counts_only_the_sample_for_sampled_arms():
    from dbench.live import RunStats
    its = items("T1", 30)
    only = runner.arm_subsets({"T1": its})
    s = RunStats({"T1": its}, {"T1": "intent"}, ["jev", "opus-low"], only=only)
    planned = {r["arm"]: r["planned"] for r in s.summary()["rows"]}
    assert planned == {"jev": 30, "opus-low": 3}


def test_score_compares_the_decision_systems_on_every_item_and_opus_on_its_sample(tmp_path):
    from dbench.__main__ import items_path, main
    from dbench.items import write_items
    data = tmp_path / "data"
    its = items("T1", 30)
    write_items(items_path(data, "T1"), its)
    only = runner.arm_subsets({"T1": its})["opus-low"]
    log = tmp_path / "calls.jsonl"
    recs = []
    for i in its:
        for arm in ("jev", "decisions", "opus-low"):
            if arm == "opus-low" and i.id not in only:
                continue
            recs.append({"mode": "accuracy", "repeat": 0, "task": "T1", "item_id": i.id, "arm": arm, "status": "ok",
                         "elapsed_s": 0.2, "latency_s": 0.2, "cost_usd": 0.001,
                         "answers": {"intent": {"label": "a", "probs": {"a": 0.9, "b": 0.1}},
                                     "category": {"label": "a", "probs": {"a": 0.9, "b": 0.1}}}})
    log.write_text("".join(json.dumps(r) + "\n" for r in recs))
    out = tmp_path / "summary.json"
    main(["--data", str(data), "score", str(log), "--out", str(out), "--resamples", "200"])
    t1 = json.loads(out.read_text())["tasks"]["T1"]
    assert t1["primary"]["n"] == 30 and set(t1["primary"]["arms"]) == {"jev", "decisions"}
    assert t1["sample"]["n"] == 3 and set(t1["sample"]["arms"]) == {"jev", "decisions", "opus-low"}
    assert t1["sample"]["of"] == 30


def test_the_t3_sample_is_the_t2_sample_products_with_their_images():
    t2 = items("T2", 60)
    t3 = [i for i in items("T3", 60) if i.id != "T3-007"]  # one product has no image, as in the real T3
    only = runner.arm_subsets({"T2": t2, "T3": t3})["opus-low"]
    s2 = {i[3:] for i in only if i.startswith("T2-")}
    s3 = {i[3:] for i in only if i.startswith("T3-")}
    assert len(s2) == 6 and s3 == s2 - {"007"}


def test_spotlight_only_draws_items_every_system_answered(tmp_path):
    from dbench.items import Image
    from dbench.replay import build_spotlight
    (tmp_path / "images").mkdir()
    q = Question("decision", "Which?", [Option("yes", "yes"), Option("no", "no")])
    its = []
    for k in range(5):
        (tmp_path / "images" / f"{k}.jpg").write_bytes(b"jpg")
        its.append(Item(f"T5-{k}", "T5", "test", "s", [q], {"decision": "yes"}, [Image(f"images/{k}.jpg", "image/jpeg", "h")],
                        source={"task": "photo"}))
    rec = lambda i, arm: {"mode": "accuracy", "repeat": 0, "task": "T5", "item_id": i, "arm": arm, "status": "ok",
                          "answers": {"decision": {"label": "yes", "probs": {"yes": 0.9}}}}
    recs = [rec(i.id, "jev") for i in its] + [rec("T5-3", "opus-low")]
    spec = {"test": "T5", "licences": {"photo": "CC0 1.0"}, "allowed_licences": ["CC0 1.0"]}
    picked = {build_spotlight(spec, its, recs, [{"id": "jev"}, {"id": "opus-low"}], seed, tmp_path, tmp_path / "out")["item_id"]
              for seed in range(20)}
    assert picked == {"T5-3"}
