# Deviations from the pre-registration

Changes made after the tag `prereg-2026-10-17` (commit 03fc011), each written and committed before the work it changes. The results report every one.

## 1. Latency windows (17 October 2026, about 17:30 London, before any latency call)

Pre-registered: two latency windows, London morning and US afternoon, 300 items each.

Run instead: both windows on the evening of Saturday 17 October, one straight after the other, so the whole benchmark finishes in one evening. Window 1 ("evening-a") starts as soon as the accuracy, Opus medium and stability runs finish, at about 17:45 London (12:45 US Eastern); window 2 ("evening-b") starts as soon as window 1 ends, about ten minutes later. Everything else about latency is unchanged: 300 items per window plus 20 warm-up calls, one request at a time, each item sent to the systems in a random order, Opus only on its sample items.

What this costs: the two windows are minutes apart at one time of day, in the US working day, so they act as one sample of 600 items and the results cannot say whether speed changes with time of day or US traffic. The write-up says so next to the latency figures.

(An earlier version of this entry, committed a few minutes before, kept window 2 at 21:00 London. Changed before any latency call.)

Decided by Gbolagade Ishola.

## 2. Correction: the tag is not signed, and what the timestamps show (18 October 2026)

PREREGISTRATION.md calls `prereg-2026-10-17` "the signed tag". It is an annotated git tag without a GPG signature, so its date (17 October 2026, 17:22:44 London) is git's own record, made on the machine that ran the benchmark. The first test call started at 17:22:53 London (`started_at` in `logs/runs/test-2026-10-17/calls.jsonl`). No hash was posted on X before the run.

GitHub's public event log, which would show when each push arrived, does not list every push that day. What it does show:

- The pre-registration as of commit 0ea4624 was on GitHub by 16:48 London, before the run: the five tests and item counts (T2 and T3 at 2,000), the systems and settings, the analysis, the power section and the stopping rule.
- Two later commits have only git's own timestamps: dddf064 at 17:15 (the Opus one-in-ten sample rule) and 03fc011 at 17:22 (the T2 audit, the T2 accept list and `manifest.json`). GitHub has both, but its event log does not record when they arrived.

What limits the risk: the Opus sample is set by seeded code (`arm_subsets` in `dbench/run.py`) that anyone can rerun on the published items and get the same 707 ids; the accept list counts the same category pairs as right for all three systems; the item files' hashes can be checked against the public copies. Future runs will be tagged and pushed, and the push confirmed on GitHub, before the first call.
