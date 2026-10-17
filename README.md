# Decision bench

Jev 1.14 (TypeSafe), OpenAI's Decisions API (GPT-6 Luna) and Claude Opus 5.5 on the same five decision tests, all public data: 1,000 items each on T1 and T4, 2,000 on T2 and T3 (1,999 on T3), 1,071 on T5. Run from London on 17-18 October 2026 by Gbolagade Ishola. Results, items and logs are published here; nothing is tuned on test items.

## The tests

| Test | Data (licence) | Question | Items |
|---|---|---|---|
| T1 | Bitext customer-support dataset (CDLA-Sharing-1.0) | Category (11) and intent (27) in one call | 1,000 test, 100 dev, stratified by intent |
| T2 | Amazon Reviews 2023, Tools and Home Improvement, Electrical (research use; ids only published) | Product category from the listing text | 2,000 test, 50 dev |
| T3 | Same products as T2 | Same question with the listing's main image | Same items |
| T4 | CLINC150 (CC BY 3.0) | 150 intents or out of scope | 800 in-scope stratified plus 200 out-of-scope; 100 dev |
| T5 | Decision Bench bench-v4 (MIT code, rows under their source licences) | Each row's own question, 122 rows with images | All 1,071 |

Seed for every draw and every option shuffle: 1017. Each item's options are shuffled once and the same order goes to all three systems. Options are plain text, never A/B/C letters.

## The three systems

- Jev: `POST https://api.typesafe.ai/v1/systemone`, model `jev-1.14.0` pinned (never `jev-latest`). Images go in `images` with the header `TypeSafe-Danger-Zone-Images: true`. Request shape from Decision Bench's TypeSafe adapter.
- Decisions: `POST https://api.openai.com/v1/decisions`, model `gpt-6-luna`, choice questions with `choices`; images as `input_image` data URLs.
- Opus 5.5: native Messages API, `output_config.format` JSON schema with an `enum` per question, `effort: "low"` (plus an `opus-medium` arm on T1). No temperature or top_p (Opus 5.5 rejects both), no forced tool use, no prefill, no reasoning field. Opus has no logprobs, so its probabilities are numbers it writes; the other two return a distribution.

All three go through one Python HTTP client with one keep-alive session per thread. Retries happen only on transport errors (408, 409, 425, 429, 5xx, 529, timeouts, dropped connections), at most three, with the identical request. An invalid, truncated or refused answer is never retried and counts as wrong; each rate is reported.

## Setup

```
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt
cp .env.example .env    # add the three keys; .env is never committed
.venv/bin/python -m pytest -q
```

## Before the run

1. Sample: `python -m dbench sample T1`, `sample T2T3` (streams the Amazon file and fetches about 2,050 images: the first draw of 1,050 plus 1,000 more test products by their own seed, resized to a 1,024 px longest side, JPEG), `sample T4`, `sample T5 --bench-repo ../atlanai-decision-bench` (a sparse clone of github.com/atlanai/decision-bench, data only).
2. Probe each system on one dev item: `python -m dbench probe --task T1 --arms jev,decisions,opus-low`, then `--task T3` for images. Every arm must come back `ok`. If Jev's or Decisions' response shape has changed, fix `dbench/adapters.py` before anything else.
3. Pilot on the dev splits: `python -m dbench run --task T1,T2,T3,T4 --split dev --run pilot` (T5 has no dev split). Any change to wording after the pilot is logged and applied to all three systems.
4. Freeze: `python -m dbench manifest` writes SHA-256 hashes of every item file and image. Commit items, manifest, code and `PREREGISTRATION.md`, sign a tag, push, post the commit hash on X.

## The run

Each run logs into its own folder, `logs/runs/<name>/`: `calls.jsonl` (every call, appended as it lands), `run.json` (commit, command, split, tests, systems, start and end) and `summary.json` (one row per test and system, rewritten every few seconds). Follow a run live with `python -m dbench watch` and open http://127.0.0.1:8765.

```
python -m dbench run --task T1,T2,T3,T4,T5 --run test-2026-10-18
python -m dbench run --task T1 --arms opus-medium --run test-2026-10-18-opus-medium
python -m dbench run --task T1 --limit 100 --repeats 3 --run stability-2026-10-18
python -m dbench latency --window london-morning
python -m dbench latency --window us-afternoon
python -m dbench score logs/runs/test-2026-10-18/calls.jsonl logs/runs/stability-2026-10-18/calls.jsonl logs/latency.jsonl
python -m dbench export logs/runs/*/calls.jsonl
```

A run can be stopped and restarted with the same name; calls already logged are skipped and `run.json` counts the restart. Accuracy runs use eight parallel workers with tests and systems interleaved. Latency is a separate sample: 300 items, one request at a time, each item sent to the three systems in a random order, the first 20 discarded as warm-up. `python -m dbench summary --run <name>` rebuilds a run's summary from its calls.

## Scoring

- Accuracy, with a paired bootstrap 95% interval (10,000 resamples, seeded). Pairs compared with McNemar's exact test, Holm-corrected across the three pairs. A difference is claimed only when the corrected p is below 0.05 and the interval excludes zero.
- Multiclass Brier score, with a paired bootstrap interval for each difference. A failed answer scores as all zeros. ECE is shown and not claimed.
- Share of answers whose top probability is exactly 1, status rates, flip rate across repeats, T3 minus T2 per system, p50 and p95 latency with intervals, cost per 1,000 decisions from logged usage at list price (`dbench/prices.py`), reconciled against each billing page a day later.

From the dev pilot, the smallest accuracy gap this design can detect is about 1.4 to 4 points at 1,000 items, and 1.4 to 1.8 points on T2 and T3 at 2,000 (PREREGISTRATION.md). Smaller gaps are reported as no detectable difference.

## What is published

Code, item files (T1, T4 and T5 text; T2 and T3 as Amazon ids, gold labels and option lists, without listing text or images), the manifest, logs with image data removed, and `results/summary.json`. Amazon listing text and images are not redistributed; `sample T2T3` rebuilds them from the public file.
