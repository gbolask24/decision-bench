import json
from collections import Counter

from dbench import sample
from dbench.items import Image, Option, read_items, shuffled, write_items


def bitext_rows():
    rows = []
    for intent in sample.BITEXT_INTENTS:
        cat = "ORDER" if "order" in intent else "ACCOUNT"
        rows += [{"instruction": f"{intent} please {k}", "intent": intent, "category": cat} for k in range(60)]
    return rows


def test_t1_is_stratified_disjoint_and_repeatable():
    rows = bitext_rows()
    a, b = sample.t1_bitext(rows), sample.t1_bitext(rows)
    assert [i.id for i in a] == [i.id for i in b]
    test = [i for i in a if i.split == "test"]
    dev = [i for i in a if i.split == "dev"]
    assert len(test) == 1000 and len(dev) == 100
    assert not {i.id for i in test} & {i.id for i in dev}
    counts = Counter(i.gold["intent"] for i in test)
    assert max(counts.values()) - min(counts.values()) <= 1  # 37 or 38 per intent
    assert [q.name for q in test[0].questions] == ["category", "intent"]
    assert len(test[0].questions[1].options) == 27


def test_shuffle_is_fixed_per_item_and_differs_between_items():
    opts = [Option(str(k), str(k)) for k in range(10)]
    assert [o.value for o in shuffled(opts, 1017, "x")] == [o.value for o in shuffled(opts, 1017, "x")]
    assert [o.value for o in shuffled(opts, 1017, "x")] != [o.value for o in shuffled(opts, 1017, "y")]


def amazon_row(asin, cat="Light Switches", img=True):
    return {"parent_asin": asin, "title": f"Switch {asin}", "features": ["15 A", "white"], "description": ["Wall switch."],
            "categories": ["Tools & Home Improvement", "Electrical", cat, "Toggle"],
            "images": [{"variant": "MAIN", "hi_res": f"https://example.com/{asin}.jpg"}] if img else []}


def test_amazon_filter_text_never_shows_the_category():
    r = amazon_row("B1")
    assert sample.amazon_keep(r)
    assert not sample.amazon_keep(amazon_row("B2", img=False))
    assert not sample.amazon_keep({**r, "categories": ["Tools & Home Improvement", "Lighting", "Bulbs"]})
    text = sample.amazon_text(r)
    assert "Light Switches" not in text and "Switch B1" in text and "- 15 A" in text


def test_t2_t3_share_products_options_and_only_t3_has_images():
    rows = [amazon_row(f"B{k:03d}", cat=("Light Switches", "Outlets", "Fuses")[k % 3]) for k in range(60)]
    pool = sample.amazon_pool(rows, exclude=frozenset({"B000"}))
    assert "B000" not in {r["parent_asin"] for r in pool}
    draw = sample.amazon_draw(pool, n_test=40, n_dev=5)
    imgs = {r["parent_asin"]: Image(f"images/T3/{r['parent_asin']}.jpg", "image/jpeg", "h") for r in draw[1:]}
    items, cats = sample.t2_t3_amazon(pool, draw, n_test=40, image_paths=imgs)
    t2 = {i.id[3:]: i for i in items if i.task == "T2"}
    t3 = {i.id[3:]: i for i in items if i.task == "T3"}
    assert cats == ["Fuses", "Light Switches", "Outlets"]
    assert len(t2) == 45 and len(t3) == 44  # the product without an image is left out of T3 only
    k = next(iter(t3))
    assert t2[k].questions[0].values() == t3[k].questions[0].values()
    assert not t2[k].images and t3[k].images


def test_t4_clinc_counts_and_out_of_scope_option():
    data = {"test": [[f"t{k}", f"intent_{k % 150}"] for k in range(4500)],
            "oos_test": [[f"o{k}", "oos"] for k in range(1000)],
            "val": [[f"v{k}", f"intent_{k % 150}"] for k in range(3000)],
            "oos_val": [[f"ov{k}", "oos"] for k in range(100)]}
    items = sample.t4_clinc(data)
    test = [i for i in items if i.split == "test"]
    assert len(test) == 1000 and sum(i.gold["intent"] == "out_of_scope" for i in test) == 200
    assert len([i for i in items if i.split == "dev"]) == 100
    assert len(test[0].questions[0].options) == 151


def test_t5_decision_bench_rows_and_images(tmp_path):
    repo, data = tmp_path / "repo", tmp_path / "data"
    (repo / "data" / "assets").mkdir(parents=True)
    from PIL import Image as PILImage
    PILImage.new("RGB", (400, 400), (10, 20, 30)).save(repo / "data" / "assets" / "p.png", "PNG")  # inside Jev's limits
    original = (repo / "data" / "assets" / "p.png").read_bytes()
    cases = [{"id": "c1", "task": "spam", "state": {"text": "hi"}, "assets": [{"path": "data/assets/p.png", "mime_type": "image/png", "alt_text": "x"}],
              "questions": [{"id": "is_spam", "type": "choice", "instructions": "Spam?", "options": {"yes": "Spam", "no": "Not spam"},
                             "gold": "no", "option_order": ["no", "yes"]}]}]
    items = sample.t5_decision_bench(cases, repo, data)
    it = items[0]
    assert it.id == "T5-c1" and it.gold == {"is_spam": "no"} and it.questions[0].values() == ["no", "yes"]
    assert json.loads(it.text) == {"text": "hi"} and (data / it.images[0].path).read_bytes() == original


def test_items_round_trip(tmp_path):
    items = sample.t1_bitext(bitext_rows(), n_test=54, n_dev=27)
    write_items(tmp_path / "T1.jsonl", items)
    back = read_items(tmp_path / "T1.jsonl")
    assert [i.to_json() for i in back] == [i.to_json() for i in items]


def test_export_strips_amazon_text_and_t2_t3_requests(tmp_path):
    from dbench.export import export
    data = tmp_path / "data"
    (data / "items").mkdir(parents=True)
    t3 = {"id": "T3-B1", "task": "T3", "split": "test", "text": "Secret listing text", "questions": [], "gold": {},
          "images": [{"path": "images/T3/B1.jpg", "mime": "image/jpeg", "sha256": "h"}],
          "source": {"parent_asin": "B1", "image_url": "https://example.com/x.jpg"}}
    t1 = {"id": "T1-1", "task": "T1", "split": "test", "text": "public text", "questions": [], "gold": {}}
    (data / "items" / "T3.jsonl").write_text(json.dumps(t3) + "\n")
    (data / "items" / "T1.jsonl").write_text(json.dumps(t1) + "\n")
    log = tmp_path / "accuracy.jsonl"
    log.write_text(json.dumps({"task": "T3", "payload": {"state": "Secret listing text"}, "response": {}, "status": "ok"}) + "\n"
                   + json.dumps({"task": "T1", "payload": {"state": "public text"}, "status": "ok"}) + "\n")
    out = tmp_path / "public"
    export(data, [log], out)
    everything = "".join(p.read_text() for p in out.rglob("*.jsonl"))
    assert "Secret listing text" not in everything and "example.com" not in everything
    assert "public text" in everything and "sha256" in everything


def test_amazon_extension_keeps_the_first_draw_and_adds_only_new_test_products():
    rows = [amazon_row(f"B{k:03d}", cat=("Light Switches", "Outlets", "Fuses")[k % 3]) for k in range(200)]
    pool = sample.amazon_pool(rows)
    first = sample.amazon_draw(pool, n_test=40, n_dev=5)
    taken = {r["parent_asin"] for r in first}
    more = sample.amazon_extend(pool, taken, 40)
    assert len(more) == 40 and not taken & {r["parent_asin"] for r in more}
    assert more == sample.amazon_extend(pool, taken, 40)  # seeded
    assert sample.amazon_draw(pool, n_test=40, n_dev=5) == first  # the first draw is untouched
    items, _ = sample.t2_t3_amazon(pool, more, n_test=len(more))
    assert {i.split for i in items} == {"test"}


def test_export_of_a_run_folder_splits_calls_by_test_and_keeps_run_files(tmp_path):
    from dbench.export import export
    data = tmp_path / "data"
    (data / "items").mkdir(parents=True)
    run = tmp_path / "runs" / "test-1"
    run.mkdir(parents=True)
    (run / "calls.jsonl").write_text(
        json.dumps({"task": "T3", "payload": {"state": "Secret listing text"}, "status": "ok"}) + "\n"
        + json.dumps({"task": "T1", "payload": {"state": "public text"}, "status": "ok"}) + "\n")
    (run / "run.json").write_text('{"name": "test-1"}')
    (run / "summary.json").write_text('{"done_total": 2}')
    out = tmp_path / "public"
    export(data, [run / "calls.jsonl"], out)
    assert sorted(p.name for p in (out / "logs" / "test-1").iterdir()) == ["T1.jsonl", "T3.jsonl", "run.json", "summary.json"]
    assert "Secret listing text" not in (out / "logs" / "test-1" / "T3.jsonl").read_text()
    assert "public text" in (out / "logs" / "test-1" / "T1.jsonl").read_text()
