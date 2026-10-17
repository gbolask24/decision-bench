"""Draw and freeze the five test sets from public data. Every draw is seeded; the same seed gives the same items."""
from __future__ import annotations

import csv
import gzip
import io
import json
import random
from collections import defaultdict
from pathlib import Path
from typing import Iterable, Iterator

from .items import Image, Item, Option, Question, sha256_file, shuffled

SEED = 1017

BITEXT_URL = ("https://huggingface.co/datasets/bitext/Bitext-customer-support-llm-chatbot-training-dataset/"
              "resolve/main/Bitext_Sample_Customer_Support_Training_Dataset_27K_responses-v11.csv")
AMAZON_URL = ("https://mcauleylab.ucsd.edu/public_datasets/data/amazon_2023/raw/meta_categories/"
              "meta_Tools_and_Home_Improvement.jsonl.gz")
CLINC_URL = "https://raw.githubusercontent.com/clinc/oos-eval/master/data/data_full.json"

BITEXT_CATEGORIES = {
    "ACCOUNT": "Creating, editing, deleting, switching or recovering an account",
    "CANCEL": "Fees for cancelling",
    "CONTACT": "Wants to reach customer service or a person",
    "DELIVERY": "Delivery options or how long delivery takes",
    "FEEDBACK": "A complaint or a review",
    "INVOICE": "Getting or checking an invoice",
    "ORDER": "Placing, changing, cancelling or tracking an order",
    "PAYMENT": "Payment methods or a problem with a payment",
    "REFUND": "Refund policy, getting a refund or tracking one",
    "SHIPPING": "Setting up or changing a shipping address",
    "SUBSCRIPTION": "The newsletter subscription",
}
BITEXT_INTENTS = {
    "cancel_order": "Cancel an order already placed",
    "change_order": "Change items or details on an existing order",
    "change_shipping_address": "Change the shipping address on file or on an order",
    "check_cancellation_fee": "Ask what cancelling costs",
    "check_invoice": "Look at or check an existing invoice",
    "check_payment_methods": "Ask which payment methods are accepted",
    "check_refund_policy": "Ask about the refund policy",
    "complaint": "Complain about the service, a product or an experience",
    "contact_customer_service": "Ask how to contact customer service",
    "contact_human_agent": "Ask to speak to a person rather than a bot",
    "create_account": "Open a new account",
    "delete_account": "Close or delete an account",
    "delivery_options": "Ask which delivery options exist",
    "delivery_period": "Ask how long delivery takes or when an order arrives",
    "edit_account": "Change details on an existing account",
    "get_invoice": "Ask to be sent an invoice",
    "get_refund": "Ask for a refund",
    "newsletter_subscription": "Subscribe to or unsubscribe from the newsletter",
    "payment_issue": "Report a problem with a payment",
    "place_order": "Place a new order",
    "recover_password": "Reset or recover a password",
    "registration_problems": "Report a problem signing up",
    "review": "Leave a review or feedback",
    "set_up_shipping_address": "Add a new shipping address",
    "switch_account": "Switch between accounts or account types",
    "track_order": "Ask where an order is",
    "track_refund": "Ask where a refund is",
}


def _stratified(groups: dict[str, list], n: int, rng: random.Random) -> list:
    """About n items, spread evenly over the groups, with the remainder from a shuffled group order."""
    keys = sorted(groups)
    per, extra = divmod(n, len(keys))
    order = keys[:]
    rng.shuffle(order)
    out = []
    for k in keys:
        take = per + (1 if k in order[:extra] else 0)
        out += rng.sample(groups[k], take)
    return out


# ---------- T1 Bitext ----------

def t1_bitext(rows: list[dict], n_test: int = 1000, n_dev: int = 100, seed: int = SEED) -> list[Item]:
    rng = random.Random(seed)
    by_intent = defaultdict(list)
    for i, r in enumerate(rows):
        by_intent[r["intent"]].append(i)
    dev = set(_stratified(by_intent, n_dev, rng))
    rest = {k: [i for i in v if i not in dev] for k, v in by_intent.items()}
    test = _stratified(rest, n_test, rng)
    items = []
    for split, idx in (("test", test), ("dev", sorted(dev))):
        for i in idx:
            r = rows[i]
            iid = f"T1-{i:05d}"
            qs = [Question("category", "Which area of customer service is this message about?",
                           shuffled([Option(k, v) for k, v in BITEXT_CATEGORIES.items()], seed, iid + ":c")),
                  Question("intent", "What does the customer want?",
                           shuffled([Option(k, v) for k, v in BITEXT_INTENTS.items()], seed, iid + ":i"))]
            items.append(Item(iid, "T1", split, r["instruction"], qs, {"category": r["category"], "intent": r["intent"]},
                              source={"dataset": "bitext", "row": i}))
    return items


def read_bitext(path: Path) -> list[dict]:
    with open(path, newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


# ---------- T2 and T3 Amazon ----------

def main_image(r: dict) -> str | None:
    imgs = r.get("images") or []
    main = [im for im in imgs if im.get("variant") == "MAIN"] or imgs
    for im in main:
        u = im.get("hi_res") or im.get("large")
        if u:
            return u
    return None


def amazon_keep(r: dict) -> bool:
    cats = r.get("categories") or []
    return len(cats) >= 3 and cats[1] == "Electrical" and bool(main_image(r)) and bool(r.get("parent_asin"))


def amazon_text(r: dict, limit: int = 2000) -> str:
    """Title, features and description only. The category path is the label, so it is never shown."""
    parts = [r.get("title") or ""]
    parts += [f"- {f}" for f in r.get("features") or []]
    desc = " ".join(r.get("description") or [])
    if desc:
        parts.append(desc)
    return "\n".join(p for p in parts if p).strip()[:limit]


def stream_jsonl_gz(source: str | Path) -> Iterator[dict]:
    if str(source).startswith("http"):
        import requests
        resp = requests.get(str(source), stream=True, timeout=60)
        resp.raise_for_status()
        fh = gzip.GzipFile(fileobj=resp.raw)
    else:
        fh = gzip.open(source, "rb")
    for line in io.TextIOWrapper(fh, encoding="utf-8"):
        if line.strip():
            yield json.loads(line)


def amazon_pool(rows: Iterable[dict], exclude: frozenset[str] = frozenset()) -> list[dict]:
    pool = {}
    for r in rows:
        if amazon_keep(r) and r["parent_asin"] not in exclude:
            pool.setdefault(r["parent_asin"], r)
    return [pool[k] for k in sorted(pool)]


def amazon_draw(pool: list[dict], n_test: int = 1000, n_dev: int = 50, seed: int = SEED) -> list[dict]:
    return random.Random(seed).sample(pool, n_test + n_dev)


def amazon_extend(pool: list[dict], taken: set[str], n: int, seed: int = SEED) -> list[dict]:
    """More test products, drawn by their own seed from the pool minus those already drawn,
    so the first draw (and its dev items) stays exactly as it was."""
    rest = [r for r in pool if r["parent_asin"] not in taken]
    return random.Random(f"{seed}:extend").sample(rest, n)


def t2_t3_amazon(pool: list[dict], draw: list[dict], n_test: int = 1000, seed: int = SEED,
                 image_paths: dict[str, Image] | None = None) -> tuple[list[Item], list[str]]:
    """T2 is text only; T3 is the same products and options with the main image. A product whose
    image could not be fetched is left out of T3 and the gap is reported."""
    categories = sorted({r["categories"][2] for r in pool})
    items = []
    for k, r in enumerate(draw):
        split = "test" if k < n_test else "dev"
        asin = r["parent_asin"]
        text = amazon_text(r)
        gold = {"category": r["categories"][2]}
        opts = shuffled([Option(c, c) for c in categories], seed, f"P-{asin}")
        for task in ("T2", "T3"):
            images = [image_paths[asin]] if task == "T3" and image_paths and asin in image_paths else []
            if task == "T3" and not images:
                continue
            q = Question("category", "Which product category does this listing belong to?"
                         + (" The product's main image is attached." if task == "T3" else ""), list(opts))
            items.append(Item(f"{task}-{asin}", task, split, text, [q], gold, images,
                              source={"dataset": "amazon-reviews-2023", "parent_asin": asin,
                                      "image_url": main_image(r) if task == "T3" else None}))
    return items, categories


def fetch_image(url: str, dest: Path, data_dir: Path, longest: int = 1024) -> Image:
    """Download once, resize to the same longest side for every system, save as JPEG, hash it."""
    import requests
    from PIL import Image as PILImage
    resp = requests.get(url, timeout=30)
    resp.raise_for_status()
    im = PILImage.open(io.BytesIO(resp.content)).convert("RGB")
    im.thumbnail((longest, longest))
    dest.parent.mkdir(parents=True, exist_ok=True)
    im.save(dest, "JPEG", quality=90)
    from .images import fit_image
    fit_image(dest)  # inside Jev's 280-1568 px limits; every system gets this same file
    return Image(str(dest.relative_to(data_dir)), "image/jpeg", sha256_file(dest))


# ---------- T4 CLINC150 ----------

def t4_clinc(data: dict, n_in: int = 800, n_oos: int = 200, n_dev: int = 100, seed: int = SEED) -> list[Item]:
    rng = random.Random(seed)
    intents = sorted({lab for _, lab in data["test"]})
    options = [Option(i, i.replace("_", " ")) for i in intents]
    options.append(Option("out_of_scope", "None of the other options: the request is outside what this assistant handles"))
    by = defaultdict(list)
    for k, (_, lab) in enumerate(data["test"]):
        by[lab].append(k)
    test_in = _stratified(by, n_in, rng)
    test_oos = rng.sample(range(len(data["oos_test"])), n_oos)
    n_dev_oos = n_dev // 5
    dev_in = rng.sample(range(len(data["val"])), n_dev - n_dev_oos)
    dev_oos = rng.sample(range(len(data["oos_val"])), n_dev_oos)
    items = []

    def add(split, src, k, lab):
        iid = f"T4-{src}-{k:05d}"
        q = Question("intent", "Which request type is this message? Choose out_of_scope if none fits.",
                     shuffled(options, seed, iid))
        items.append(Item(iid, "T4", split, data[src][k][0], [q], {"intent": lab},
                          source={"dataset": "clinc150", "set": src, "row": k}))

    for k in test_in:
        add("test", "test", k, data["test"][k][1])
    for k in test_oos:
        add("test", "oos_test", k, "out_of_scope")
    for k in dev_in:
        add("dev", "val", k, data["val"][k][1])
    for k in dev_oos:
        add("dev", "oos_val", k, "out_of_scope")
    return items


# ---------- T5 Decision Bench ----------

def t5_decision_bench(cases: list[dict], repo: Path, data_dir: Path, seed: int = SEED) -> list[Item]:
    """All bench-v4 rows. Images are copied from the repo and hashed. The state is shown as a string to every system."""
    import shutil
    items = []
    for c in cases:
        q = c["questions"][0]
        raw = q["options"]
        opts = [Option(k, v) for k, v in raw.items()] if isinstance(raw, dict) else [Option(o, o) for o in raw]
        order = q.get("option_order")
        opts = [next(o for o in opts if o.value == v) for v in order] if order else shuffled(opts, seed, c["id"])
        images = []
        for a in c.get("assets", []):
            dst = data_dir / "images" / "T5" / Path(a["path"]).name
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(repo / a["path"], dst)
            from .images import fit_image
            fit_image(dst)  # inside Jev's limits; same file for every system
            images.append(Image(str(dst.relative_to(data_dir)), a["mime_type"], sha256_file(dst)))
        state = c["state"] if isinstance(c["state"], str) else json.dumps(c["state"], ensure_ascii=False)
        items.append(Item(f"T5-{c['id']}", "T5", "test", state, [Question(q["id"], q["instructions"], opts)],
                          {q["id"]: q["gold"]}, images,
                          source={"dataset": "decision-bench", "case": c["id"], "task": c["task"]}))
    return items
