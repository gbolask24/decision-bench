# R1D04 data pack

Every figure the X Article and the site article use. Built by `scripts/data_pack.py` from `results/summary.json`, `results/opus-medium-exploratory.json`, `results/replay/replay.json` and the call logs in `logs/runs/`. Percentages are share right; intervals are 95% paired bootstrap (10,000 resamples). Re-run the script after any change to the results and check the articles against it.

## A. The run

| Run | Started | Ended | Calls | Errors | Cost at list price |
|---|---|---|---|---|---|
| stability-2026-10-17 | 16:38:26 UTC | 16:39:05 UTC | 624 | 0 | $0.612 |
| test-2026-10-17 | 16:22:53 UTC | 16:36:58 UTC | 14,847 | 13 | $13.56 |
| test-2026-10-17-opus-medium | 16:37:00 UTC | 16:38:25 UTC | 100 | 0 | $2.41 |
| latency evening-a | 16:39:06 UTC | 16:45:03 UTC | 686 | 1 | $0.843 |
| latency evening-b | 16:45:05 UTC | 16:50:37 UTC | 680 | 0 | $0.780 |

All on Saturday 17 October 2026 (London is UTC+1). Pre-registration tag `prereg-2026-10-17`, commit 03fc011; first test call 16:22:53 UTC. Models: jev-1.14.0, gpt-6-luna, claude-opus-5-5 at effort low (medium on the T1 sample only, exploratory). Seed 1017. Prices from `dbench/prices.py` (checked 16 October): Jev $0.042 per million input tokens, output free; Decisions $0.10 per million input, output free; Opus $4 input and $20 output per million. No caching on any arm. Billing pages not yet reconciled.

## B. Jev against the Decisions API, every item (primary)

| Test | Items | Jev | Decisions | Jev minus Decisions, points | McNemar p | Verdict | Only Jev right / only Decisions right |
|---|---|---|---|---|---|---|---|
| T1 Customer-support routing (Bitext, intent) | 1,000 | 92.2% (90.5 to 93.8) | 91.1% (89.3 to 92.8) | +1.1 (-0.6 to +2.8) | 0.248 | no detectable difference | 43 / 32 |
| T2 Product category, text (Amazon electrical) | 2,000 | 85.9% (84.4 to 87.4) | 85.8% (84.3 to 87.3) | +0.1 (-0.8 to +1.1) | 0.916 | no detectable difference | 46 / 44 |
| T3 Product category, text and photo (Amazon electrical) | 1,999 | 86.5% (85.0 to 88.0) | 85.7% (84.1 to 87.2) | +0.9 (+0.0 to +1.7) | 0.068 | no detectable difference | 47 / 30 |
| T4 Intent with off-topic messages (CLINC150) | 1,000 | 88.2% (86.1 to 90.1) | 84.2% (81.9 to 86.4) | +4.0 (+2.1 to +5.9) | <0.0001 | Jev ahead | 68 / 28 |
| T5 Decision Bench bench-v4 | 1,071 | 94.5% (93.1 to 95.8) | 90.6% (88.8 to 92.3) | +3.9 (+2.2 to +5.6) | <0.0001 | Jev ahead | 64 / 22 |

Smallest detectable gap (PREREGISTRATION.md, Power): about 1.4 to 4 points at 1,000 items, 1.4 to 1.8 on T2 and T3 at 2,000. A gap below it is reported as no detectable difference, never a tie.

All five tests together (each item counted once): Jev 1.14 6,264 of 7,070 right (88.6%); OpenAI Decisions API 6,152 of 7,070 right (87.0%).

## C. Calibration and answer shape (every item)

| Test | Brier, Jev / Decisions (lower is better) | Brier difference | Brier verdict | ECE (shown, not claimed) | Answers with top probability exactly 1 | Decisions non-ok |
|---|---|---|---|---|---|---|
| T1 | 0.121 / 0.161 | -0.040 (-0.058 to -0.023) | Jev better | 0.018 / 0.102 | 41.8% / 7.4% | refusal 0.1% |
| T2 | 0.262 / 0.283 | -0.021 (-0.032 to -0.010) | Jev better | 0.064 / 0.086 | 42.4% / 57.5% | refusal 0.4% |
| T3 | 0.254 / 0.287 | -0.033 (-0.045 to -0.022) | Jev better | 0.046 / 0.088 | 26.3% / 59.1% | refusal 0.2% |
| T4 | 0.172 / 0.261 | -0.088 (-0.109 to -0.068) | Jev better | 0.021 / 0.080 | 20.1% / 5.6% | none |
| T5 | 0.091 / 0.135 | -0.044 (-0.061 to -0.029) | Jev better | 0.021 / 0.016 | 54.1% / 44.0% | none |

Jev returned no refusals, invalid or truncated answers on any test. Decisions refused 13 of 7,070 (1 T1, 8 T2, 4 T3), scored as wrong. Brier differences are not corrected for the number of comparisons. Option order was shuffled once per item and sent identically to all three systems.

## D. What the photo changed (T3 minus T2, same products)

| System | Paired products | T2 text | T3 text and photo | Photo effect, points | Net extra right | Input tokens per call | Cost per 1,000 | Exact-1 answers |
|---|---|---|---|---|---|---|---|---|
| Jev 1.14 | 1,999 | 85.9% | 86.5% | +0.7 (+0.1 to +1.3) | 13 | 878 → 2,716 | $0.037 → $0.114 (3.1x) | 42.4% → 26.3% |
| OpenAI Decisions API | 1,999 | 85.8% | 85.7% | -0.1 (-0.8 to +0.6) | -2 | 551 → 1,246 | $0.055 → $0.124 (2.3x) | 57.5% → 59.1% |
| Claude Opus 5.5 (low) (sample) | 199 | 91.0% | 89.4% | -1.5 (-4.0 to +0.5) | -3 | 1,729 → 2,635 | $15.23 → $18.76 (1.2x) | 0.0% → 0.0% |

Secondary metric, no pre-registered claim rule: report Jev's gain as small and at the edge of what the test can see. Same image file to every system; 78 T3 images padded or shrunk into Jev's 280-1,568 px limits, never cropped. Images bill as input tokens at the text price for Jev (TypeSafe docs).

Post hoc, not pre-registered: the nine T2 test products with under 30 characters of listing text, text only → with photo.

| Product | Text length | Jev 1.14 | OpenAI Decisions API | Claude Opus 5.5 (low) |
|---|---|---|---|---|
| B003U4MTR0 | 13 | wrong → right | wrong → right | – → – |
| B00413B196 | 9 | wrong → right | wrong → right | – → – |
| B00WZQRZKU | 20 | wrong → right | wrong → wrong | – → – |
| B09SHJFK3J | 23 | right → right | right → right | – → – |
| B0044UR1FY | 21 | right → right | right → right | – → – |
| B07SPCQ2YB | 19 | right → right | right → right | – → – |
| B00HLNS3HQ | 22 | right → right | right → right | – → – |
| B00AK015C2 | 28 | right → right | right → right | – → – |
| B08NPKHTSX | 1 | wrong → wrong | wrong → wrong | – → – |

Secondary (pre-registered, not in summary.json): T5 image rows and text rows. Jev 1.14: image rows 122 of 122, text rows 890 of 949; OpenAI Decisions API: image rows 122 of 122, text rows 848 of 949; Claude Opus 5.5 (low): image rows 8 of 8, text rows 94 of 100. The image rows do not separate the systems; Jev's T5 lead comes from the text rows.

## E. T4: off-topic messages

| System | False accepts: off-topic answered as an intent (secondary) | In-scope accuracy | In-scope sent to out of scope (post hoc) |
|---|---|---|---|
| Jev 1.14 | 21 of 200 (10.5%) | 87.9% | 35 of 800 |
| OpenAI Decisions API | 19 of 200 (9.5%) | 82.6% | 80 of 800 |

## F. Claude Opus 5.5 on its one-in-ten sample (same items for all three)

| Test | Sample items | Opus | Jev, same items | Decisions, same items | Claims (Holm across the sample's three pairs) | Opus Brier |
|---|---|---|---|---|---|---|
| T1 | 100 of 1,000 | 95.0% (90.0 to 99.0) | 94.0% | 92.0% | none | 0.066 |
| T2 | 200 of 2,000 | 91.0% (87.0 to 94.5) | 86.0% | 84.0% | Opus ahead of Jev 1.14 +5.0; Opus ahead of OpenAI Decisions API +7.0 | 0.215 |
| T3 | 199 of 1,999 | 89.4% (84.9 to 93.5) | 84.9% | 83.4% | Opus ahead of Jev 1.14 +4.5; Opus ahead of OpenAI Decisions API +6.0 | 0.230 |
| T4 | 100 of 1,000 | 97.0% (93.0 to 100.0) | 93.0% | 87.0% | Opus ahead of OpenAI Decisions API +10.0 | 0.056 |
| T5 | 108 of 1,071 | 94.4% (89.8 to 98.1) | 92.6% | 82.4% | Opus ahead of OpenAI Decisions API +12.0 | 0.089 |

Opus's Brier comes from probabilities it writes into a JSON schema (no logprobs); the other two return native distributions. Never put Opus's sample score beside the full-test scores of the other two: on T4 that reads as 97% against 88.2%, where the same-item gap is 4.0 points and not claimed. Sample noise: Jev led Decisions by +10.2 on the T5 sample against +3.9 on all 1,071.

Whole-test estimate used in the video (Jev's whole-test score plus Opus's lead over Jev on the same items):

| Test | Opus raw sample score | Opus minus Jev, same items | Jev whole test | Opus whole-test estimate |
|---|---|---|---|---|
| T1 | 95.0% | +1.0 | 92.2% | 93.2% (92.2 to 95.2) |
| T2 | 91.0% | +5.0 | 85.9% | 90.9% (87.9 to 93.9) |
| T3 | 89.4% | +4.5 | 86.5% | 91.1% (88.6 to 94.1) |
| T4 | 97.0% | +4.0 | 88.2% | 92.2% (88.2 to 97.2) |
| T5 | 94.4% | +1.9 | 94.5% | 96.3% (91.7 to 100.0) |

Exploratory: Opus at medium effort on the 100-item T1 sample scored 96.0% against 95.0% at low, at $24.08 against $24.03 per 1,000. Not part of the corrected tests.

## G. Cost per 1,000 decisions at list price

| Test | Jev (every item) | Decisions (every item) | Opus (sample) | Opus / Jev, same items | Opus / Decisions, same items |
|---|---|---|---|---|---|
| T1 | $0.046 | $0.073 | $24.03 | 525x | 327x |
| T2 | $0.037 | $0.055 | $15.23 | 409x | 275x |
| T3 | $0.114 | $0.124 | $18.76 | 165x | 151x |
| T4 | $0.107 | $0.139 | $22.45 | 210x | 161x |
| T5 | $0.052 | $0.083 | $8.90 | 176x | 104x |

Pooled over all 707 sample items: Opus $17.52, Jev $0.072, Decisions $0.094 per 1,000; Opus is 244 times Jev and 187 times Decisions. Use these two pooled figures as the headline ratio, and the per-test range beside them.

## H. Speed and whole-test totals

| System | Timed calls | Median (95% interval) | Slowest 5% (95% interval) |
|---|---|---|---|
| Jev 1.14 | 600 | 0.22 s (0.22 to 0.22) | 0.32 s (0.31 to 0.36) |
| OpenAI Decisions API | 600 | 0.27 s (0.27 to 0.28) | 0.49 s (0.44 to 0.52) |
| Claude Opus 5.5 (low) | 82 | 4.09 s (3.91 to 4.21) | 6.81 s (6.51 to 7.22) |

One request at a time from one London machine, two back-to-back windows on Saturday evening (DEVIATIONS.md, item 1). Opus's figures rest on 82 timed calls. The Jev-Decisions gap is the size network routing alone could move.

| System | Calls made | Summed call time | Cost | Opus scaled to all 7,070 (estimate, x10) |
|---|---|---|---|---|
| Jev 1.14 | 7,070 | 30 min | $0.510 | – |
| OpenAI Decisions API | 7,070 | 34 min | $0.660 | – |
| Claude Opus 5.5 (low) | 707 | 48 min | $12.39 | about 7.9 h, $123.88 |

Summed call time adds every call's own time end to end, as the race video does; the run itself took 14 minutes with eight calls in flight.

## I. Same question, three times (T1)

| System | Items sent three times | Answers that changed |
|---|---|---|
| Jev 1.14 | 100 | 0.0% |
| OpenAI Decisions API | 100 | 0.0% |
| Claude Opus 5.5 (low) | 8 | 0.0% |

Opus's 8 items say nothing about its stability; say so if the figure is used.

## J. Worked examples (licences allow reproduction; no Amazon text)


T4 in-scope message the Decisions API sent to out of scope (CLINC150, CC BY 3.0): `T4-test-02938`

> why can't i access my chase account

Gold: `account_blocked`. Jev 1.14: `account_blocked` (0.64); OpenAI Decisions API: `out_of_scope` (1.00).

T1 message Jev got wrong and the Decisions API got right (Bitext, CDLA-Sharing-1.0): `T1-23131`

> can i submit my new delivery address

Gold: `set_up_shipping_address`. Jev 1.14: `change_shipping_address` (0.53); OpenAI Decisions API: `set_up_shipping_address` (0.54).

T4 off-topic message Jev answered as an intent and the Decisions API rejected (CLINC150, CC BY 3.0): `T4-oos_test-00308`

> where's the best place to hike in the rockies

Gold: `out_of_scope`. Jev 1.14: `travel_suggestion` (0.97); OpenAI Decisions API: `out_of_scope` (0.53).

Examples are drawn by seed ("1017:examples") from the qualifying items, not chosen by hand.
