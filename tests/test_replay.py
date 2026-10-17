import json
from pathlib import Path

import pytest

from dbench.items import Image, Item, Option, Question
from dbench.replay import ReplayError, build_replay

SYSTEMS = [{"id": "jev", "name": "Jev 1.14", "model": "jev-1.14.0", "kind": "decision model"},
           {"id": "opus-low", "name": "Opus 5.5", "model": "claude-opus-5-5", "kind": "general model"}]


def config(**over):
    c = {"title": "Jev vs Opus", "run_date": "2026-10-18", "commit": "abc1234", "tag": "run-2026-10-18",
         "logs_url": "https://github.com/gbolask24/decision-bench/tree/main/public/logs",
         "repo_url": "https://github.com/gbolask24/decision-bench",
         "selection_rule": "test items in seeded random order, seed 1017", "seed": 1017,
         "systems": SYSTEMS,
         "scenes": [{"type": "title", "duration_s": 3}, {"type": "race", "race": "t1", "duration_s": "auto"},
                    {"type": "spotlight", "duration_s": 6}, {"type": "results", "duration_s": 10},
                    {"type": "receipt", "duration_s": 3}],
         "races": {"t1": {"test": "T1", "label": "Customer-support routing", "question": "intent",
                          "show_items": True, "placeholder": "", "segments": [{"from_s": 0, "to_s": 5, "speed": 1}]}},
         "spotlight": {"test": "T5", "licences": {"photo-task": "CC BY 4.0"},
                       "allowed_licences": ["CC BY 4.0", "CC0 1.0"]}}
    c.update(over)
    return c


def t1_items(n=6, long=False):
    q = Question("intent", "What does the customer want?", [Option("a", "A"), Option("b", "B")])
    text = ("x" * 200) if long else "where is my order"
    return [Item(f"T1-{k:05d}", "T1", "test", text, [q], {"intent": "a"}) for k in range(n)]


def t5_items(tmp):
    (tmp / "images" / "T5").mkdir(parents=True)
    (tmp / "images" / "T5" / "p.jpg").write_bytes(b"jpg")
    q = Question("decision", "Which?", [Option("yes", "yes"), Option("no", "no")])
    return [Item("T5-c1", "T5", "test", "state", [q], {"decision": "yes"},
                 [Image("images/T5/p.jpg", "image/jpeg", "h")], source={"task": "photo-task"}),
            Item("T5-c2", "T5", "test", "state", [q], {"decision": "no"}, [], source={"task": "text-task"})]


def rec(item_id, arm, label, elapsed, status="ok", task="T1", q="intent"):
    return {"mode": "accuracy", "task": task, "item_id": item_id, "arm": arm, "repeat": 0, "status": status,
            "started_at": "2026-10-18T09:00:00+00:00", "elapsed_s": elapsed, "latency_s": elapsed,
            "cost_usd": 0.001, "answers": {q: {"label": label, "probs": {label: 0.9, ("b" if label == "a" else "a"): 0.1}}}
            if status == "ok" else {}}


def summary():
    arm = {"accuracy": 0.9, "accuracy_ci": [0.88, 0.92], "brier": 0.15, "brier_ci": [0.1, 0.2],
           "cost_per_1000_usd": 0.04, "status_rates": {"ok": 1.0}}
    return {"tasks": {"T1": {"primary": {"n": 1000, "arms": {"jev": arm, "opus-low": arm},
                                         "pairs": {"jev vs opus-low": {"accuracy_claim": False, "brier_claim": True}}}}},
            "latency": {"jev": {"p50_s": 0.3, "p95_s": 0.6}, "opus-low": {"p50_s": 3.0, "p95_s": 5.0}}}


def records():
    out = []
    for it in t1_items():
        out.append(rec(it.id, "jev", "a", 1.0))
        out.append(rec(it.id, "opus-low", "b", 2.0))
    out.append(rec("T5-c1", "jev", "yes", 0.2, task="T5", q="decision"))
    out.append(rec("T5-c1", "opus-low", "no", 2.0, task="T5", q="decision"))
    return out


def build(tmp, cfg=None, recs=None, items=None):
    items = items or {"T1": t1_items(), "T5": t5_items(tmp)}
    return build_replay(cfg or config(), items, recs if recs is not None else records(), summary(), tmp, tmp / "out")


def test_calls_are_laid_end_to_end_in_seeded_order_and_cut_at_the_race_span(tmp_path):
    r = build(tmp_path)
    jev = r["races"]["t1"]["calls"]["jev"]
    opus = r["races"]["t1"]["calls"]["opus-low"]
    assert [c["start_s"] for c in jev] == [0.0, 1.0, 2.0, 3.0, 4.0]  # 5 s span, 1 s calls: the sixth starts at 5
    assert [c["start_s"] for c in opus] == [0.0, 2.0, 4.0]
    assert jev[0]["correct"] is True and opus[0]["correct"] is False
    assert r["races"]["t1"]["n_items"] == 6
    order = [c["item_id"] for c in jev]
    assert order == [c["item_id"] for c in opus][: len(order)] or order[: len(opus)] == [c["item_id"] for c in opus]
    assert order == [c["item_id"] for c in build(tmp_path / "again")["races"]["t1"]["calls"]["jev"]]


def test_failed_calls_count_as_made_not_correct(tmp_path):
    recs = records()
    recs[0] = rec(recs[0]["item_id"], "jev", "a", 1.0, status="refusal")
    jev = build(tmp_path, recs=recs)["races"]["t1"]["calls"]["jev"]
    failed = [c for c in jev if c["status"] == "refusal"]
    assert failed and failed[0]["correct"] is False and failed[0]["label"] is None


def test_item_text_is_one_line_and_hidden_when_not_allowed(tmp_path):
    r = build(tmp_path, items={"T1": t1_items(long=True), "T5": t5_items(tmp_path)})
    preview = r["races"]["t1"]["calls"]["jev"][0]["text_preview"]
    assert len(preview) == 80 and preview.endswith("…")
    cfg = config()
    cfg["races"]["t1"]["show_items"] = False
    cfg["races"]["t1"]["placeholder"] = "Product photo and listing sent"
    hidden = build(tmp_path / "h", cfg=cfg)["races"]["t1"]
    assert all(c["text_preview"] == "" for c in hidden["calls"]["jev"])
    assert hidden["placeholder"] == "Product photo and listing sent"


def test_spotlight_uses_only_licensed_images_and_copies_the_file(tmp_path):
    r = build(tmp_path)
    s = r["spotlight"]
    assert s["item_id"] == "T5-c1" and s["image_licence"] == "CC BY 4.0"
    assert (tmp_path / "out" / s["image"]).read_bytes() == b"jpg"
    assert {p["system"]: p["label"] for p in s["picks"]} == {"jev": "yes", "opus-low": "no"}
    cfg = config()
    cfg["spotlight"]["licences"] = {"photo-task": "All rights reserved"}
    with pytest.raises(ReplayError, match="no T5 image item with an allowed licence"):
        build(tmp_path / "x", cfg=cfg)


def test_results_are_copied_from_the_scorer_unchanged(tmp_path):
    r = build(tmp_path)
    assert r["results"]["tests"]["T1"] == summary()["tasks"]["T1"]["primary"]
    assert r["results"]["latency"] == summary()["latency"]


@pytest.mark.parametrize("field", ["commit", "logs_url", "run_date", "selection_rule"])
def test_missing_honesty_fields_fail(tmp_path, field):
    cfg = config()
    del cfg[field]
    with pytest.raises(ReplayError, match=field):
        build(tmp_path, cfg=cfg)


def test_output_has_schema_and_meta(tmp_path):
    r = build(tmp_path)
    assert r["schema"] == "bench-replay/1"
    assert r["meta"]["commit"] == "abc1234" and r["systems"] == SYSTEMS and r["scenes"][1]["race"] == "t1"
    json.dumps(r)  # serialisable


def test_cli_returns_1_when_the_config_is_incomplete(tmp_path):
    from dbench.__main__ import main
    cfg = config(commit="")
    (tmp_path / "cfg.json").write_text(json.dumps(cfg))
    (tmp_path / "s.json").write_text("{}")
    (tmp_path / "l.jsonl").write_text("")
    assert main(["--data", str(tmp_path), "replay", "--config", str(tmp_path / "cfg.json"),
                 "--logs", str(tmp_path / "l.jsonl"), "--summary", str(tmp_path / "s.json"),
                 "--out", str(tmp_path / "out")]) == 1


def test_test_labels_are_carried_to_results(tmp_path):
    r = build(tmp_path, cfg=config(test_labels={"T1": "Customer-support routing"}))
    assert r["results"]["labels"] == {"T1": "Customer-support routing"}
    assert "labels" not in build(tmp_path / "none")["results"]


def test_totals_sum_every_logged_test_call_per_system(tmp_path):
    t = build(tmp_path)["results"]["totals"]
    assert t["T1"]["jev"] == {"calls": 6, "elapsed_s": 6.0, "cost_usd": pytest.approx(0.006)}
    assert t["T1"]["opus-low"]["elapsed_s"] == 12.0
    assert t["T5"]["jev"]["calls"] == 1  # only test-split items, first repeat


def test_totals_count_failed_calls_and_skip_other_splits(tmp_path):
    recs = records()
    recs[0] = rec(recs[0]["item_id"], "jev", "a", 1.0, status="refusal")
    dev = Item("T1-dev", "T1", "dev", "x", t1_items()[0].questions, {"intent": "a"})
    recs.append(rec("T1-dev", "jev", "a", 50.0))
    items = {"T1": t1_items() + [dev], "T5": t5_items(tmp_path)}
    t = build(tmp_path, recs=recs, items=items)["results"]["totals"]["T1"]["jev"]
    assert t["calls"] == 6 and t["elapsed_s"] == 6.0


def test_a_sampled_system_is_merged_into_results_with_its_sample_size(tmp_path):
    s = summary()
    full = {"accuracy": 0.9, "accuracy_ci": [0.88, 0.92], "cost_per_1000_usd": 0.04, "status_rates": {"ok": 1.0}}
    opus = {"accuracy": 0.95, "accuracy_ci": [0.9, 0.99], "cost_per_1000_usd": 19.0, "status_rates": {"ok": 1.0}}
    s["tasks"]["T1"] = {"primary": {"n": 1000, "arms": {"jev": full}, "pairs": {}},
                        "sample": {"n": 100, "of": 1000, "arms": {"jev": full, "opus-low": opus},
                                   "pairs": {"jev vs opus-low": {"accuracy_claim": False}}}}
    r = build_replay(config(), {"T1": t1_items(), "T5": t5_items(tmp_path)}, records(), s, tmp_path, tmp_path / "out")
    t = r["results"]["tests"]["T1"]
    assert t["arms"]["opus-low"]["accuracy"] == 0.95 and t["arms"]["jev"] is not None
    assert t["pairs"]["jev vs opus-low"] == {"accuracy_claim": False}
    assert t["sampled"] == {"opus-low": {"n": 100, "of": 1000}}
    assert "sample" not in t


def test_the_spotlight_can_show_a_short_question_from_the_config(tmp_path):
    cfg = config()
    cfg["spotlight"]["question"] = "Which is it?"
    assert build(tmp_path, cfg=cfg)["spotlight"]["question"] == "Which is it?"
    assert build(tmp_path / "b")["spotlight"]["question"] == "Which?"  # the item's own wording otherwise
