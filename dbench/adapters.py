"""Turn one item into each system's native request, and each system's response back into one shape.

Jev's request shape follows Decision Bench's TypeSafe adapter (github.com/atlanai/decision-bench,
decision_bench/adapters.py). OpenAI's follows the Decisions guide. Opus 5.5 uses the native Messages
API with a JSON schema; it rejects temperature, top_p, forced tool use and prefill, so none are sent.
Run `python -m dbench probe` on a dev item before the run to confirm all three still match.
"""
from __future__ import annotations

import base64
import json
import math
from dataclasses import dataclass, field
from pathlib import Path

from .items import POLICY, Item

JEV_URL = "https://api.typesafe.ai/v1/systemone"
DECISIONS_URL = "https://api.openai.com/v1/decisions"
ANTHROPIC_URL = "https://api.anthropic.com/v1/messages"

OPUS_SYSTEM = (POLICY + "Return only the required JSON. For every question, choose one allowed value and give a "
               "probability for every option; probabilities are numbers from 0 to 1 that sum to 1.")


@dataclass
class Answer:
    label: str | None
    probs: dict[str, float] | None  # renormalised over the question's options
    confidence: float | None = None
    raw_sum: float | None = None


@dataclass
class Parsed:
    status: str  # ok, invalid, refusal, truncated
    answers: dict[str, Answer] = field(default_factory=dict)
    input_tokens: int = 0
    output_tokens: int = 0
    cache_read_tokens: int = 0
    cache_write_tokens: int = 0
    model: str | None = None
    detail: str = ""


def _data_uri(item: Item, data_dir: Path) -> list[str]:
    out = []
    for im in item.images:
        blob = (data_dir / im.path).read_bytes()
        out.append(f"data:{im.mime};base64,{base64.b64encode(blob).decode()}")
    return out


# ---------- requests ----------

def jev_request(item: Item, data_dir: Path, model: str) -> tuple[dict, dict]:
    payload = {"model": model, "state": item.text,
               "questions": {q.name: {"type": "choice", "instructions": POLICY + q.instructions,
                                      "criteria": {o.value: o.description for o in q.options}}
                             for q in item.questions}}
    headers = {}
    if item.images:
        payload["images"] = _data_uri(item, data_dir)
        headers["TypeSafe-Danger-Zone-Images"] = "true"
    return payload, headers


def decisions_request(item: Item, data_dir: Path, model: str) -> tuple[dict, dict]:
    if item.images:
        content = [{"type": "input_text", "text": item.text}]
        content += [{"type": "input_image", "image_url": u} for u in _data_uri(item, data_dir)]
        inp: object = [{"role": "user", "content": content}]
    else:
        inp = item.text
    payload = {"model": model, "input": inp,
               "questions": [{"name": q.name, "type": "choice", "instructions": POLICY + q.instructions,
                              "choices": [{"value": o.value, "description": o.description} for o in q.options]}
                             for q in item.questions]}
    return payload, {}


def opus_schema(item: Item) -> dict:
    props = {}
    for q in item.questions:
        values = q.values()
        props[q.name] = {
            "type": "object",
            "properties": {
                "choice": {"type": "string", "enum": values},
                "probabilities": {"type": "array", "items": {
                    "type": "object",
                    "properties": {"value": {"type": "string", "enum": values}, "probability": {"type": "number"}},
                    "required": ["value", "probability"], "additionalProperties": False}},
            },
            "required": ["choice", "probabilities"], "additionalProperties": False}
    return {"type": "object", "properties": props, "required": [q.name for q in item.questions],
            "additionalProperties": False}


def opus_prompt(item: Item) -> str:
    lines = [item.text, "", "Questions:"]
    for q in item.questions:
        lines.append(f"- {q.name}: {q.instructions}")
        lines.append("  Options (value: description):")
        lines += [f"  - {o.value}: {o.description}" for o in q.options]
    return "\n".join(lines)


def opus_request(item: Item, data_dir: Path, model: str, effort: str, max_tokens: int = 4096) -> tuple[dict, dict]:
    content: list[dict] = []
    for im in item.images:
        blob = (data_dir / im.path).read_bytes()
        content.append({"type": "image", "source": {"type": "base64", "media_type": im.mime,
                                                    "data": base64.b64encode(blob).decode()}})
    content.append({"type": "text", "text": opus_prompt(item)})
    payload = {"model": model, "max_tokens": max_tokens, "system": OPUS_SYSTEM,
               "messages": [{"role": "user", "content": content}],
               "output_config": {"effort": effort, "format": {"type": "json_schema", "schema": opus_schema(item)}}}
    return payload, {"anthropic-version": "2023-06-01"}


# ---------- responses ----------

def _probs(raw, values: list[str]) -> tuple[dict[str, float] | None, float | None]:
    """Accept {value: p} or [{value, probability}]; keep the question's options only; renormalise."""
    if isinstance(raw, list):
        try:
            raw = {str(d["value"]): d["probability"] for d in raw}
        except (KeyError, TypeError):
            return None, None
    if not isinstance(raw, dict):
        return None, None
    out = {}
    for v in values:
        p = raw.get(v, 0.0)
        if not isinstance(p, (int, float)) or isinstance(p, bool) or not math.isfinite(p) or p < 0:
            return None, None
        out[v] = float(p)
    total = sum(out.values())
    if total <= 0:
        return None, None
    return {v: p / total for v, p in out.items()}, total


def _answer(label, probs_raw, confidence, values: list[str]) -> Answer | None:
    probs, total = _probs(probs_raw, values)
    label = None if label is None else str(label)
    if label not in values or probs is None:
        return None
    conf = float(confidence) if isinstance(confidence, (int, float)) and not isinstance(confidence, bool) else None
    return Answer(label, probs, conf, total)


def parse_jev(raw: dict, item: Item) -> Parsed:
    usage = raw.get("usage") or {}
    out = Parsed("ok", input_tokens=int(usage.get("input_tokens") or 0), model=raw.get("model"))
    answers = raw.get("answers")
    if isinstance(answers, list):  # tolerate a list keyed by name
        answers = {a.get("name"): a for a in answers if isinstance(a, dict)}
    if not isinstance(answers, dict):
        return Parsed("invalid", input_tokens=out.input_tokens, model=out.model, detail="no answers")
    for q in item.questions:
        a = answers.get(q.name)
        if a is None:  # Jev drops a question it refuses
            out.status, out.detail = "refusal", f"{q.name} missing"
            continue
        parsed = _answer(a.get("choice"), a.get("probabilities"), a.get("confidence"), q.values())
        if parsed is None:
            out.status, out.detail = "invalid", f"{q.name} bad labels or probabilities"
            continue
        out.answers[q.name] = parsed
    return out


def parse_decisions(raw: dict, item: Item) -> Parsed:
    usage = raw.get("usage") or {}
    out = Parsed("ok", input_tokens=int(usage.get("input_tokens") or usage.get("prompt_tokens") or 0),
                 model=raw.get("model"))
    answers = {a.get("name"): a for a in raw.get("answers") or [] if isinstance(a, dict)}
    for q in item.questions:
        a = answers.get(q.name)
        if a is None or a.get("type") == "refusal":
            out.status, out.detail = "refusal", f"{q.name} refused or missing"
            continue
        parsed = _answer(a.get("choice"), a.get("probabilities"), a.get("confidence"), q.values())
        if parsed is None:
            out.status, out.detail = "invalid", f"{q.name} bad labels or probabilities"
            continue
        out.answers[q.name] = parsed
    return out


def parse_opus(raw: dict, item: Item) -> Parsed:
    usage = raw.get("usage") or {}
    out = Parsed("ok", input_tokens=int(usage.get("input_tokens") or 0),
                 output_tokens=int(usage.get("output_tokens") or 0),
                 cache_read_tokens=int(usage.get("cache_read_input_tokens") or 0),
                 cache_write_tokens=int(usage.get("cache_creation_input_tokens") or 0), model=raw.get("model"))
    stop = raw.get("stop_reason")
    if stop == "refusal":
        out.status, out.detail = "refusal", "stop_reason refusal"
        return out
    if stop == "max_tokens":
        out.status, out.detail = "truncated", "stop_reason max_tokens"
        return out
    text = "".join(b.get("text", "") for b in raw.get("content") or [] if b.get("type") == "text")
    try:
        body = json.loads(text)
    except ValueError:
        out.status, out.detail = "invalid", "not JSON"
        return out
    for q in item.questions:
        a = body.get(q.name) if isinstance(body, dict) else None
        parsed = _answer(a.get("choice"), a.get("probabilities"), None, q.values()) if isinstance(a, dict) else None
        if parsed is None:
            out.status, out.detail = "invalid", f"{q.name} bad labels or probabilities"
            continue
        out.answers[q.name] = parsed
    return out


def strip_images(payload: dict) -> dict:
    """The payload as logged: base64 image data replaced by its length, so logs stay small."""
    def walk(v):
        if isinstance(v, dict):
            return {k: ("[base64 omitted]" if k == "data" and isinstance(x, str) and len(x) > 200 else walk(x))
                    for k, x in v.items()}
        if isinstance(v, list):
            return [walk(x) for x in v]
        if isinstance(v, str) and v.startswith("data:image/"):
            return f"[{v.split(';', 1)[0][5:]} data URI, {len(v)} characters omitted]"
        return v
    return walk(payload)
