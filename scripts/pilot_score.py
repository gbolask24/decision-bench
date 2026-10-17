"""Score the dev pilot with the harness's own summarise(), then the smallest gap n items can detect."""
import json
import statistics
import sys
from math import sqrt
from pathlib import Path

repo = Path(sys.argv[1]) if len(sys.argv) > 1 else Path.cwd()
sys.path.insert(0, str(repo))
from dbench.__main__ import TASKS, items_path  # noqa: E402
from dbench.items import read_items  # noqa: E402
from dbench import score  # noqa: E402

ARMS = ["jev", "decisions", "opus-low"]
Z = 2.394 + 0.842  # two-sided alpha 0.05/3 (Holm worst case), 80% power


def mde(discord: float, n: int) -> float:
    return Z * sqrt(discord / n)


recs = score.load_logs([repo / "logs" / "pilot-dev.jsonl"])
out = {}
for task in ["T1", "T2", "T3", "T4"]:
    items = [i for i in read_items(items_path(repo / "data", task)) if i.split == "dev"]
    s = score.summarise(score.item_rows(items, recs, TASKS[task], ARMS), ARMS, 2000)
    lat = {a: statistics.median([r["elapsed_s"] for r in recs if r["task"] == task and r["arm"] == a])
           for a in ARMS if any(r["task"] == task and r["arm"] == a for r in recs)}
    print(f"\n{task}  n={s['n']}")
    for a, v in s["arms"].items():
        st = ", ".join(f"{k} {x:.0%}" for k, x in v["status_rates"].items())
        print(f"  {a:10} acc {v['accuracy']:.1%} [{v['accuracy_ci'][0]:.1%}, {v['accuracy_ci'][1]:.1%}]"
              f"  ${v['cost_per_1000_usd']:.3f}/1k  p50 {lat.get(a, 0):.2f}s  ({st})")
    for k, p in s["pairs"].items():
        d = (p["only_first_right"] + p["only_second_right"]) / s["n"]
        print(f"  {k:24} diff {p['accuracy_diff']:+.1%}  discord {d:.1%}  "
              f"gap@1000 {mde(d, 1000):.1%}  gap@2000 {mde(d, 2000):.1%}  p_holm {p['mcnemar_p_holm']:.3f}")
    out[task] = s
(repo / "logs" / "pilot-dev-summary.json").write_text(json.dumps(out, indent=1) + "\n")
