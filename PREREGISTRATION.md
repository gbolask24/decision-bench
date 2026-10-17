# Pre-registration

Written before any test item is sent to any system. The signed tag on the commit that contains this file, and the commit hash posted on X, are the timestamps. Anything changed after the tag is listed under Deviations, with the reason.

## Systems and settings

| Arm | Model | Settings |
|---|---|---|
| jev | `jev-1.14.0` at `api.typesafe.ai/v1/systemone` | `TypeSafe-Danger-Zone-Images: true` on image items only |
| decisions | `gpt-6-luna` at `api.openai.com/v1/decisions` | none |
| opus-low | `claude-opus-5-5`, Messages API | `effort: "low"`, `max_tokens` 4096, JSON schema output, no sampling fields |
| opus-medium (T1 only, exploratory) | as above | `effort: "medium"` |

The primary comparison is between jev, decisions and opus-low. opus-medium is reported but not part of the corrected tests.

## Tests, items and primary metrics

| Test | Test items | Dev items | Primary metric | Secondary |
|---|---|---|---|---|
| T1 Bitext routing | 1,000 | 100 | Intent accuracy | Category accuracy; Brier (intent) |
| T2 Amazon category, text | 2,000 | 50 | Accuracy | Brier |
| T3 Amazon category, text and image | the T2 products with an image | 50 | Accuracy | T3 minus T2 per arm |
| T4 CLINC150 | 1,000 (200 out of scope) | 100 | Accuracy | Out-of-scope false-accept rate |
| T5 Decision Bench bench-v4 | 1,071 | none | Accuracy | Brier; image rows separately |

Item files and their SHA-256 hashes are in `manifest.json`. Seed 1017 for every draw and option shuffle.

## Gold labels and ambiguity

Gold labels are the datasets' own. T2 and T3 also count as correct any category listed for the gold category in `data/items/T2-accept.json` (for example, two near-duplicate categories). That file is fixed from a hand audit of 100 items before the tag, with the audit notes in `data/items/T2-audit.md`, and the same rule applies to every arm. After the tag, no gold label changes; a label found wrong after the run goes in a separate before-and-after table with both scores.

## Analysis

- Accuracy per arm with a paired bootstrap 95% interval, 10,000 resamples, seed 2026.
- Pairwise accuracy: McNemar's exact test on discordant items, Holm correction across the three pairs within each test, alpha 0.05. A difference is claimed only when the corrected p is below 0.05 and the bootstrap interval of the difference excludes zero.
- Brier (multiclass, failed answers scored as all zeros): paired bootstrap interval of each difference; a difference is claimed only when the interval excludes zero. ECE is shown and not claimed.
- Invalid, refusal, truncation and error rates; share of answers with a top probability of exactly 1; flip rate across three repeats on 100 T1 items.
- Latency: 300 items per window, two windows (London morning, US afternoon), one request at a time, systems interleaved, 20 warm-up calls discarded; p50 and p95 with bootstrap intervals.
- Cost per 1,000 decisions from logged usage at the list prices in `dbench/prices.py`, reconciled against billing a day later; both published.

## Power

At 1,000 independent items, 80% power, and a correction for three comparisons, the smallest detectable accuracy gap is about 3 to 4 points, assuming the arms disagree on 15 to 20% of items. Pilot on the dev splits, 17 October 2026 (100 T1, 50 T2, 50 T3 and 100 T4 items, all three systems, 900 calls, all status ok; `scripts/pilot_score.py`): the systems disagreed on 2 to 15% of items, depending on the pair and test, below the 15 to 20% assumed above. At 1,000 items the smallest detectable gap is therefore 1.4 to 4.0 points: about 2 to 2.5 points on T2 and T3, where the pilot races were closest, and up to 4.0 points on T4. Decision, made after the pilot and before the tag: T2 and T3 go to 2,000 test items, because their races were the closest; at 2,000 the smallest detectable gap there is about 1.4 to 1.8 points. The first draw of 1,050 products (1,000 test, 50 dev) is kept exactly; 1,000 more test products are drawn from the rest of the pool with their own seed (`amazon_extend`, seed "1017:extend"), so no dev or probe item changed. T3 has 1,999 because one product's image link is dead (`data/items/T3-image-failures.txt`). T1 and T4 stay at 1,000 and T5 at 1,071. A gap below the detectable size is reported as no detectable difference, never as a tie or a win.

## Stopping rule

One run per test. No reruns except the declared repeats and transport-error retries. If a system is unavailable for a whole test, that test is reported without it, with the reason.

## Checks before the tag

- Images: every T3 and T5 image is inside Jev's input limits (each side 280 to 1568 px, docs.typesafe.ai/images). Images outside them were padded with white to 280 px or shrunk to 1568 px, never cropped, by `python -m dbench fit-images` on 17 October 2026: 78 T3 and 54 T5 files (16 of the T5 files were in range but not plain RGB and were flattened onto white). All three systems are sent the same file.
- Probes on 17 October 2026, one item per test, to check request shapes and parsing (status only; nothing was tuned on them): T1 `T1-00075`, T2 `T2-B01C5YGXB8` and T3 `T3-B01C5YGXB8` (dev), T4 `T4-val-02789` (dev), and T5 `T5-fin-3-cord-test-025`, a test item, because T5 has no dev split. All three systems returned status ok on all five.

## Deviations

None yet.
