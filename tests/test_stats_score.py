from dbench import score, stats
from dbench.items import Item, Option, Question


def test_mcnemar_exact_known_values():
    assert stats.mcnemar_exact(0, 0) == 1.0
    assert abs(stats.mcnemar_exact(10, 2) - 0.03857421875) < 1e-12
    assert stats.mcnemar_exact(5, 5) == 1.0


def test_holm_is_monotone_and_capped():
    adj = stats.holm({"a": 0.01, "b": 0.04, "c": 0.03})
    assert adj == {"a": 0.03, "c": 0.06, "b": 0.06}
    assert stats.holm({"a": 0.9, "b": 0.8})["a"] == 1.0


def test_percentile_and_bootstrap_are_deterministic():
    assert stats.percentile([1, 2, 3, 4], 50) == 2.5
    xs = [1, 0, 1, 1, 0, 1, 1, 1, 0, 1]
    ci1 = stats.bootstrap_ci(len(xs), lambda ix: sum(xs[i] for i in ix) / len(ix), 2000)
    ci2 = stats.bootstrap_ci(len(xs), lambda ix: sum(xs[i] for i in ix) / len(ix), 2000)
    assert ci1 == ci2 and ci1[0] < 0.7 < ci1[1]


def test_brier_penalises_failures_as_all_zero():
    vals = ["a", "b", "c"]
    assert score.brier({"a": 1.0, "b": 0.0, "c": 0.0}, "a", vals) == 0.0
    assert abs(score.brier({"a": 0.5, "b": 0.5, "c": 0.0}, "a", vals) - 0.5) < 1e-12
    assert score.brier(None, "a", vals) == 1.0


def _items(n):
    q = Question("intent", "?", [Option("a", "A"), Option("b", "B")])
    return [Item(f"T1-{k:05d}", "T1", "test", "x", [q], {"intent": "a"}) for k in range(n)]


def _rec(item_id, arm, label, status="ok", repeat=0, p=0.9):
    other = "b" if label == "a" else "a"
    answers = {"intent": {"label": label, "probs": {label: p, other: 1 - p}}} if status == "ok" else {}
    return {"mode": "accuracy", "task": "T1", "item_id": item_id, "arm": arm, "repeat": repeat,
            "status": status, "answers": answers, "cost_usd": 0.001}


def test_summarise_counts_failures_as_wrong_and_compares_pairs():
    items = _items(100)
    recs = []
    for k, it in enumerate(items):
        recs.append(_rec(it.id, "jev", "a"))                          # 100 right
        recs.append(_rec(it.id, "opus-low", "a" if k < 70 else "b"))  # 70 right
        recs.append(_rec(it.id, "decisions", "a", status="invalid" if k < 5 else "ok"))  # 95 right
    rows = score.item_rows(items, recs, "intent", ["jev", "decisions", "opus-low"])
    s = score.summarise(rows, ["jev", "decisions", "opus-low"], resamples=500)
    assert s["n"] == 100
    assert s["arms"]["jev"]["accuracy"] == 1.0 and s["arms"]["decisions"]["accuracy"] == 0.95
    assert s["arms"]["decisions"]["status_rates"]["invalid"] == 0.05
    pair = s["pairs"]["jev vs opus-low"]
    assert pair["only_first_right"] == 30 and pair["only_second_right"] == 0 and pair["accuracy_claim"]
    assert abs(s["arms"]["jev"]["cost_per_1000_usd"] - 1.0) < 1e-9


def test_flip_rate_and_image_effect():
    recs = [_rec("T1-00000", "jev", "a", repeat=0), _rec("T1-00000", "jev", "b", repeat=1),
            _rec("T1-00001", "jev", "a", repeat=0), _rec("T1-00001", "jev", "a", repeat=1)]
    assert score.flip_rate(recs, "intent", ["jev"])["jev"] == {"items": 2, "flip_rate": 0.5}
    text = {"T2-X1": {"jev": {"correct": True}}, "T2-X2": {"jev": {"correct": False}}}
    image = {"T3-X1": {"jev": {"correct": True}}, "T3-X2": {"jev": {"correct": True}}}
    eff = score.image_effect(text, image, ["jev"], resamples=200)
    assert eff["jev"]["n"] == 2 and eff["jev"]["diff"] == 0.5


def test_latency_ignores_warmup_and_errors():
    recs = [{"mode": "latency", "arm": "jev", "warmup": True, "status": "ok", "latency_s": 99.0}]
    recs += [{"mode": "latency", "arm": "jev", "warmup": False, "status": "ok", "latency_s": float(k)} for k in range(1, 101)]
    recs.append({"mode": "latency", "arm": "jev", "warmup": False, "status": "http_error", "latency_s": 50.0})
    lat = score.latency(recs, ["jev"], resamples=200)["jev"]
    assert lat["n"] == 100 and lat["p50_s"] == 50.5
