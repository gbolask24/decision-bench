"""Every number the R1D04 articles use, computed from results/summary.json, the replay and the call logs.
Writes results/data-pack.md (tables) and results/data-pack.json. Run from the repo root:
    .venv/bin/python scripts/data_pack.py
Figures marked "post hoc" were not pre-registered; figures marked "secondary" are pre-registered secondary metrics
that the scorer does not yet output."""
from __future__ import annotations

import json
import random
import statistics
import sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(sys.argv[1]) if len(sys.argv) > 1 else Path.cwd()
sys.path.insert(0, str(ROOT))
from dbench import score  # noqa: E402
from dbench.__main__ import TASKS, items_path  # noqa: E402
from dbench.items import read_items  # noqa: E402
from dbench.run import arm_subsets  # noqa: E402

ARMS = ["jev", "decisions", "opus-low"]
NAME = {"jev": "Jev 1.14", "decisions": "OpenAI Decisions API", "opus-low": "Claude Opus 5.5 (low)",
        "opus-medium": "Claude Opus 5.5 (medium)"}
TEST = {"T1": "Customer-support routing (Bitext, intent)", "T2": "Product category, text (Amazon electrical)",
        "T3": "Product category, text and photo (Amazon electrical)", "T4": "Intent with off-topic messages (CLINC150)",
        "T5": "Decision Bench bench-v4"}
RUNS = ROOT / "logs" / "runs"
MAIN = RUNS / "test-2026-10-17" / "calls.jsonl"

pct = lambda x: "–" if x is None else f"{x * 100:.1f}%"
pts = lambda x: "–" if x is None else f"{x * 100:+.1f}"
ci = lambda c: f"{c[0] * 100:.1f} to {c[1] * 100:.1f}"
dci = lambda c: f"{c[0] * 100:+.1f} to {c[1] * 100:+.1f}"
usd = lambda x: f"${x:,.2f}" if x >= 1 else f"${x:.3f}" if x >= 0.01 else f"${x:.4f}"
pv = lambda p: "<0.0001" if p < 0.0001 else f"{p:.4f}" if p < 0.01 else f"{p:.3f}"

summary = json.loads((ROOT / "results" / "summary.json").read_text())
medium = json.loads((ROOT / "results" / "opus-medium-exploratory.json").read_text())
replay = json.loads((ROOT / "results" / "replay" / "replay.json").read_text())
records = score.load_logs([MAIN])
items = {t: [i for i in read_items(items_path(ROOT / "data", t)) if i.split == "test"] for t in TASKS}
accept = json.loads((ROOT / "data" / "items" / "T2-accept.json").read_text())
for t in ("T2", "T3"):
    for i in items[t]:
        i.accept = {"category": accept.get(i.gold["category"], [])}
sample = arm_subsets(items)["opus-low"]
rows = {t: score.item_rows(items[t], records, TASKS[t], ARMS) for t in TASKS}
first = {}
for r in records:
    if r["mode"] == "accuracy" and r["repeat"] == 0:
        first.setdefault((r["item_id"], r["arm"]), r)

out: list[str] = []
data: dict = {}
h = lambda s: out.extend(["", f"## {s}", ""])
table = lambda head, body: out.extend(["| " + " | ".join(head) + " |", "|" + "---|" * len(head)]
                                      + ["| " + " | ".join(str(c) for c in r) + " |" for r in body])
note = lambda s: out.extend(["", s])

out += ["# R1D04 data pack", "",
        "Every figure the X Article and the site article use. Built by `scripts/data_pack.py` from `results/summary.json`, "
        "`results/opus-medium-exploratory.json`, `results/replay/replay.json` and the call logs in `logs/runs/`. "
        "Percentages are share right; intervals are 95% paired bootstrap (10,000 resamples). Re-run the script after any "
        "change to the results and check the articles against it."]

# A. The run
h("A. The run")
runs = []
for d in sorted(RUNS.iterdir()):
    if not (d / "summary.json").exists() or d.name.startswith("pilot"):
        continue
    s = json.loads((d / "summary.json").read_text())
    m = s["run"]
    runs.append([d.name, m.get("started_at", "")[11:19] + " UTC", (m.get("ended_at") or "")[11:19] + " UTC",
                 f"{s['done_total']:,}", s["failed_total"], usd(s["cost_total_usd"])])
lat_recs = [json.loads(l) for l in (ROOT / "logs" / "latency-2026-10-17.jsonl").read_text().splitlines()]
for w in ("evening-a", "evening-b"):
    rs = [r for r in lat_recs if r.get("window") == w]
    runs.append([f"latency {w}", rs[0]["ts"][11:19] + " UTC", rs[-1]["ts"][11:19] + " UTC", f"{len(rs):,}",
                 sum(r["status"] != "ok" for r in rs), usd(sum(r.get("cost_usd") or 0 for r in rs))])
table(["Run", "Started", "Ended", "Calls", "Errors", "Cost at list price"], runs)
note("All on Saturday 17 October 2026 (London is UTC+1). Pre-registration tag `prereg-2026-10-17`, commit 03fc011; "
     "first test call 16:22:53 UTC. Models: jev-1.14.0, gpt-6-luna, claude-opus-5-5 at effort low (medium on the T1 "
     "sample only, exploratory). Seed 1017. Prices from `dbench/prices.py` (checked 16 October): Jev $0.042 per million "
     "input tokens, output free; Decisions $0.10 per million input, output free; Opus $4 input and $20 output per million. "
     "No caching on any arm. Billing pages not yet reconciled.")

# B. The race on every item
h("B. Jev against the Decisions API, every item (primary)")
body = []
for t, v in summary["tasks"].items():
    p = v["primary"]
    a, b = p["arms"]["jev"], p["arms"]["decisions"]
    pr = p["pairs"]["jev vs decisions"]
    body.append([f"{t} {TEST[t]}", f"{p['n']:,}", f"{pct(a['accuracy'])} ({ci(a['accuracy_ci'])})",
                 f"{pct(b['accuracy'])} ({ci(b['accuracy_ci'])})", f"{pts(pr['accuracy_diff'])} ({dci(pr['accuracy_diff_ci'])})",
                 pv(pr["mcnemar_p"]), "Jev ahead" if pr["accuracy_claim"] else "no detectable difference",
                 f"{pr['only_first_right']} / {pr['only_second_right']}"])
table(["Test", "Items", "Jev", "Decisions", "Jev minus Decisions, points", "McNemar p", "Verdict",
       "Only Jev right / only Decisions right"], body)
note("Smallest detectable gap (PREREGISTRATION.md, Power): about 1.4 to 4 points at 1,000 items, 1.4 to 1.8 on T2 and T3 "
     "at 2,000. A gap below it is reported as no detectable difference, never a tie.")

tot = {a: [0, 0] for a in ("jev", "decisions")}
for t in TASKS:
    for row in rows[t].values():
        for a in tot:
            if a in row:
                tot[a][0] += row[a]["correct"]
                tot[a][1] += 1
note("All five tests together (each item counted once): " + "; ".join(
    f"{NAME[a]} {tot[a][0]:,} of {tot[a][1]:,} right ({pct(tot[a][0] / tot[a][1])})" for a in tot) + ".")

# C. Calibration and answer shape
h("C. Calibration and answer shape (every item)")
body = []
for t, v in summary["tasks"].items():
    p = v["primary"]
    a, b = p["arms"]["jev"], p["arms"]["decisions"]
    pr = p["pairs"]["jev vs decisions"]
    body.append([t, f"{a['brier']:.3f} / {b['brier']:.3f}", f"{pr['brier_diff']:+.3f} ({pr['brier_diff_ci'][0]:+.3f} to {pr['brier_diff_ci'][1]:+.3f})",
                 "Jev better" if pr["brier_claim"] and pr["brier_diff"] < 0 else "Decisions better" if pr["brier_claim"] else "no claim",
                 f"{a['ece_shown_not_claimed']:.3f} / {b['ece_shown_not_claimed']:.3f}",
                 f"{pct(a['exact_one_share'])} / {pct(b['exact_one_share'])}",
                 ", ".join(f"{k} {pct(x)}" for k, x in b["status_rates"].items() if k != "ok") or "none"])
table(["Test", "Brier, Jev / Decisions (lower is better)", "Brier difference", "Brier verdict", "ECE (shown, not claimed)",
       "Answers with top probability exactly 1", "Decisions non-ok"], body)
note("Jev returned no refusals, invalid or truncated answers on any test. Decisions refused 13 of 7,070 (1 T1, 8 T2, 4 T3), "
     "scored as wrong. Brier differences are not corrected for the number of comparisons. Option order was shuffled once "
     "per item and sent identically to all three systems.")

# D. The photo
h("D. What the photo changed (T3 minus T2, same products)")
ie = summary["image_effect_T3_minus_T2"]
tok = defaultdict(list)
for r in records:
    if r["task"] in ("T2", "T3") and r["status"] == "ok":
        tok[(r["task"], r["arm"])].append((r.get("usage") or {}).get("input_tokens", 0))
body = []
for a in ARMS:
    t2 = summary["tasks"]["T2"]["primary" if a != "opus-low" else "sample"]["arms"][a]
    t3 = summary["tasks"]["T3"]["primary" if a != "opus-low" else "sample"]["arms"][a]
    e = ie[a]
    body.append([NAME[a] + (" (sample)" if a == "opus-low" else ""), f"{e['n']:,}", pct(t2["accuracy"]), pct(t3["accuracy"]),
                 f"{pts(e['diff'])} ({dci(e['diff_ci'])})", round(e["diff"] * e["n"]),
                 f"{statistics.mean(tok[('T2', a)]):,.0f} → {statistics.mean(tok[('T3', a)]):,.0f}",
                 f"{usd(t2['cost_per_1000_usd'])} → {usd(t3['cost_per_1000_usd'])} ({t3['cost_per_1000_usd'] / t2['cost_per_1000_usd']:.1f}x)",
                 f"{pct(t2['exact_one_share'])} → {pct(t3['exact_one_share'])}"])
table(["System", "Paired products", "T2 text", "T3 text and photo", "Photo effect, points", "Net extra right",
       "Input tokens per call", "Cost per 1,000", "Exact-1 answers"], body)
note("Secondary metric, no pre-registered claim rule: report Jev's gain as small and at the edge of what the test can see. "
     "Same image file to every system; 78 T3 images padded or shrunk into Jev's 280-1,568 px limits, never cropped. "
     "Images bill as input tokens at the text price for Jev (TypeSafe docs).")

thin = [i for i in read_items(ROOT / "data" / "items" / "T2.jsonl") if i.split == "test" and len(i.text) < 30]
body = []
for i in thin:
    k = i.id[3:]
    r2, r3 = rows["T2"].get("T2-" + k, {}), rows["T3"].get("T3-" + k, {})
    mark = lambda r, a: ("right" if r[a]["correct"] else "wrong") if a in r else "–"
    body.append([k, len(i.text)] + [f"{mark(r2, a)} → {mark(r3, a)}" for a in ARMS])
note("Post hoc, not pre-registered: the nine T2 test products with under 30 characters of listing text, text only → with photo.")
out.append("")
table(["Product", "Text length"] + [NAME[a] for a in ARMS], body)

t5img = defaultdict(lambda: [0, 0])
t5txt = defaultdict(lambda: [0, 0])
for i in items["T5"]:
    for a in ARMS:
        r = rows["T5"].get(i.id, {}).get(a)
        if r:
            bucket = t5img if i.images else t5txt
            bucket[a][0] += r["correct"]
            bucket[a][1] += 1
note("Secondary (pre-registered, not in summary.json): T5 image rows and text rows. "
     + "; ".join(f"{NAME[a]}: image rows {t5img[a][0]} of {t5img[a][1]}, text rows {t5txt[a][0]} of {t5txt[a][1]}" for a in ARMS)
     + ". The image rows do not separate the systems; Jev's T5 lead comes from the text rows.")

# E. T4 out of scope
h("E. T4: off-topic messages")
body = []
for a in ("jev", "decisions"):
    oos = [i for i in items["T4"] if i.gold["intent"] == "out_of_scope"]
    ins = [i for i in items["T4"] if i.gold["intent"] != "out_of_scope"]
    lab = lambda i: rows["T4"][i.id][a]["label"]
    fa = sum(1 for i in oos if lab(i) not in ("out_of_scope", None))
    fr = sum(1 for i in ins if lab(i) == "out_of_scope")
    acc_in = sum(rows["T4"][i.id][a]["correct"] for i in ins) / len(ins)
    body.append([NAME[a], f"{fa} of {len(oos)} ({pct(fa / len(oos))})", pct(acc_in), f"{fr} of {len(ins)}"])
table(["System", "False accepts: off-topic answered as an intent (secondary)", "In-scope accuracy",
       "In-scope sent to out of scope (post hoc)"], body)

# F. Opus on its sample
h("F. Claude Opus 5.5 on its one-in-ten sample (same items for all three)")
body = []
for t, v in summary["tasks"].items():
    s = v["sample"]
    a = s["arms"]
    claims = [k.replace(" vs ", " vs ") + f" {pts(-x['accuracy_diff'])}" for k, x in s["pairs"].items()
              if "opus" in k and x["accuracy_claim"]]
    body.append([t, f"{s['n']} of {s['of']:,}", f"{pct(a['opus-low']['accuracy'])} ({ci(a['opus-low']['accuracy_ci'])})",
                 pct(a["jev"]["accuracy"]), pct(a["decisions"]["accuracy"]),
                 "; ".join(f"Opus ahead of {NAME[k.split(' vs ')[0]]} {pts(-x['accuracy_diff'])}" for k, x in s["pairs"].items()
                           if "opus" in k and x["accuracy_claim"]) or "none",
                 f"{a['opus-low']['brier']:.3f}"])
table(["Test", "Sample items", "Opus", "Jev, same items", "Decisions, same items", "Claims (Holm across the sample's three pairs)",
       "Opus Brier"], body)
note("Opus's Brier comes from probabilities it writes into a JSON schema (no logprobs); the other two return native distributions. "
     "Never put Opus's sample score beside the full-test scores of the other two: on T4 that reads as 97% against 88.2%, "
     "where the same-item gap is 4.0 points and not claimed. Sample noise: Jev led Decisions by "
     f"{pts(summary['tasks']['T5']['sample']['pairs']['jev vs decisions']['accuracy_diff'])} on the T5 sample against "
     f"{pts(summary['tasks']['T5']['primary']['pairs']['jev vs decisions']['accuracy_diff'])} on all 1,071.")

body = []
for t, v in replay["results"]["tests"].items():
    o = v["arms"]["opus-low"]
    e = o.get("estimate", {})
    body.append([t, pct(e.get("sample_accuracy")), pts(e.get("same_item_gap")), pct(v["arms"]["jev"]["accuracy"]),
                 f"{pct(o['accuracy'])} ({ci(o['accuracy_ci'])})"])
note("Whole-test estimate used in the video (Jev's whole-test score plus Opus's lead over Jev on the same items):")
out.append("")
table(["Test", "Opus raw sample score", "Opus minus Jev, same items", "Jev whole test", "Opus whole-test estimate"], body)

m = medium["tasks"]["T1"]["sample"]["arms"]
note(f"Exploratory: Opus at medium effort on the 100-item T1 sample scored {pct(m['opus-medium']['accuracy'])} against "
     f"{pct(m['opus-low']['accuracy'])} at low, at {usd(m['opus-medium']['cost_per_1000_usd'])} against "
     f"{usd(m['opus-low']['cost_per_1000_usd'])} per 1,000. Not part of the corrected tests.")

# G. Cost
h("G. Cost per 1,000 decisions at list price")
body = []
pooled = {a: [0.0, 0] for a in ARMS}
for t in TASKS:
    c = {}
    for a in ARMS:
        cs = [first[(i, a)]["cost_usd"] for i in rows[t] if i in sample and (i, a) in first]
        c[a] = sum(cs) / len(cs) * 1000
        pooled[a][0] += sum(cs)
        pooled[a][1] += len(cs)
    full = summary["tasks"][t]["primary"]["arms"]
    body.append([t, usd(full["jev"]["cost_per_1000_usd"]), usd(full["decisions"]["cost_per_1000_usd"]), usd(c["opus-low"]),
                 f"{c['opus-low'] / c['jev']:.0f}x", f"{c['opus-low'] / c['decisions']:.0f}x"])
table(["Test", "Jev (every item)", "Decisions (every item)", "Opus (sample)", "Opus / Jev, same items", "Opus / Decisions, same items"], body)
pj, pd, po = (pooled[a][0] / pooled[a][1] * 1000 for a in ARMS)
note(f"Pooled over all 707 sample items: Opus {usd(po)}, Jev {usd(pj)}, Decisions {usd(pd)} per 1,000; Opus is {po / pj:.0f} times "
     f"Jev and {po / pd:.0f} times Decisions. Use these two pooled figures as the headline ratio, and the per-test range "
     "beside them.")

# H. Time and totals
h("H. Speed and whole-test totals")
lat = summary["latency"]
table(["System", "Timed calls", "Median (95% interval)", "Slowest 5% (95% interval)"],
      [[NAME[a], lat[a]["n"], f"{lat[a]['p50_s']:.2f} s ({lat[a]['p50_ci'][0]:.2f} to {lat[a]['p50_ci'][1]:.2f})",
        f"{lat[a]['p95_s']:.2f} s ({lat[a]['p95_ci'][0]:.2f} to {lat[a]['p95_ci'][1]:.2f})"] for a in ARMS])
note("One request at a time from one London machine, two back-to-back windows on Saturday evening (DEVIATIONS.md, item 1). "
     "Opus's figures rest on 82 timed calls. The Jev-Decisions gap is the size network routing alone could move.")
out.append("")
totals = replay["results"]["totals"]
body = []
for a in ARMS:
    calls = sum(totals[t][a]["calls"] for t in totals)
    secs = sum(totals[t][a]["elapsed_s"] for t in totals)
    cost = sum(totals[t][a]["cost_usd"] for t in totals)
    scale = 10 if a == "opus-low" else 1
    body.append([NAME[a], f"{calls:,}", f"{secs / 60:.0f} min", usd(cost),
                 f"about {secs * scale / 3600:.1f} h, {usd(cost * scale)}" if scale > 1 else "–"])
table(["System", "Calls made", "Summed call time", "Cost", "Opus scaled to all 7,070 (estimate, x10)"], body)
note("Summed call time adds every call's own time end to end, as the race video does; the run itself took 14 minutes with "
     "eight calls in flight.")

# I. Stability
h("I. Same question, three times (T1)")
st = summary["tasks"]["T1"]["stability"]
table(["System", "Items sent three times", "Answers that changed"], [[NAME[a], st[a]["items"], pct(st[a]["flip_rate"])] for a in ARMS])
note("Opus's 8 items say nothing about its stability; say so if the figure is used.")

# J. Examples from reusable items
h("J. Worked examples (licences allow reproduction; no Amazon text)")
rng = random.Random("1017:examples")
def pick(task, cond, k=1):
    pool = sorted((i for i in items[task] if cond(rows[task].get(i.id, {}))), key=lambda i: i.id)
    return rng.sample(pool, min(k, len(pool)))
ex = []
for i in [x for x in pick("T4", lambda r: "jev" in r and "decisions" in r and r["jev"]["correct"]
                          and r["decisions"]["label"] == "out_of_scope" and r["jev"]["label"] != "out_of_scope")]:
    ex.append(("T4 in-scope message the Decisions API sent to out of scope (CLINC150, CC BY 3.0)", i, "T4"))
for i in pick("T1", lambda r: "jev" in r and "decisions" in r and not r["jev"]["correct"] and r["decisions"]["correct"]):
    ex.append(("T1 message Jev got wrong and the Decisions API got right (Bitext, CDLA-Sharing-1.0)", i, "T1"))
for i in pick("T4", lambda r: "jev" in r and "decisions" in r and r["jev"]["label"] not in ("out_of_scope", None)
              and r["decisions"]["label"] == "out_of_scope" and not r["jev"]["correct"]):
    ex.append(("T4 off-topic message Jev answered as an intent and the Decisions API rejected (CLINC150, CC BY 3.0)", i, "T4"))
for title, i, t in ex:
    r = rows[t][i.id]
    out += ["", f"{title}: `{i.id}`", "", f"> {' '.join(i.text.split())[:300]}", "",
            f"Gold: `{i.gold[TASKS[t]]}`. " + "; ".join(
                f"{NAME[a]}: `{r[a]['label']}`" + (f" ({max(r[a]['probs'].values()):.2f})" if r[a]["probs"] else "")
                for a in ARMS if a in r) + "."]
note("Examples are drawn by seed (\"1017:examples\") from the qualifying items, not chosen by hand.")

(ROOT / "results" / "data-pack.md").write_text("\n".join(out) + "\n")
print(f"wrote results/data-pack.md ({len(out)} lines)")
