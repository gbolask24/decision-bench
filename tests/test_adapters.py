import json
from pathlib import Path

from dbench import adapters
from dbench.items import Image, Item, Option, Question


def item(images=()):
    q = Question("intent", "What does the customer want?",
                 [Option("track_order", "Ask where an order is"), Option("get_refund", "Ask for a refund")])
    return Item("T1-00001", "T1", "dev", "where is my parcel", [q], {"intent": "track_order"}, list(images))


def test_jev_request_shape_follows_systemone():
    payload, headers = adapters.jev_request(item(), Path("."), "jev-1.14.0")
    assert payload["model"] == "jev-1.14.0" and payload["state"] == "where is my parcel"
    q = payload["questions"]["intent"]
    assert q["type"] == "choice" and q["instructions"].startswith(adapters.POLICY)
    assert list(q["criteria"]) == ["track_order", "get_refund"]  # the item's option order is kept
    assert "images" not in payload and headers == {}


def test_images_go_to_all_three_and_jev_gets_the_opt_in_header(tmp_path):
    (tmp_path / "a.jpg").write_bytes(b"\xff\xd8fake")
    it = item([Image("a.jpg", "image/jpeg", "x")])
    jp, jh = adapters.jev_request(it, tmp_path, "jev-1.14.0")
    dp, _ = adapters.decisions_request(it, tmp_path, "gpt-6-luna")
    op, _ = adapters.opus_request(it, tmp_path, "claude-opus-5-5", "low")
    assert jp["images"][0].startswith("data:image/jpeg;base64,")
    assert jh == {"TypeSafe-Danger-Zone-Images": "true"}
    parts = dp["input"][0]["content"]
    assert parts[0] == {"type": "input_text", "text": "where is my parcel"} and parts[1]["type"] == "input_image"
    assert op["messages"][0]["content"][0]["type"] == "image"


def test_opus_request_sends_no_sampling_fields_and_an_enum_schema():
    payload, headers = adapters.opus_request(item(), Path("."), "claude-opus-5-5", "low")
    assert "temperature" not in payload and "top_p" not in payload and "tool_choice" not in payload
    assert payload["output_config"]["effort"] == "low"
    schema = payload["output_config"]["format"]["schema"]
    assert schema["properties"]["intent"]["properties"]["choice"]["enum"] == ["track_order", "get_refund"]
    assert headers["anthropic-version"] == "2023-06-01"
    assert "reasoning" not in json.dumps(schema)


def test_parse_jev_choice_and_renormalises():
    raw = {"model": "jev-1.14.0", "usage": {"input_tokens": 120},
           "answers": {"intent": {"choice": "track_order", "probabilities": {"track_order": 0.8, "get_refund": 0.4},
                                  "confidence": 0.7}}}
    p = adapters.parse_jev(raw, item())
    assert p.status == "ok" and p.input_tokens == 120
    a = p.answers["intent"]
    assert a.label == "track_order" and abs(a.probs["track_order"] - 2 / 3) < 1e-9 and abs(a.raw_sum - 1.2) < 1e-9


def test_parse_jev_dropped_question_is_a_refusal():
    assert adapters.parse_jev({"answers": {}}, item()).status == "refusal"


def test_parse_decisions_list_probabilities_and_refusal():
    ok = {"answers": [{"type": "choice", "name": "intent", "choice": "get_refund",
                       "probabilities": [{"value": "get_refund", "probability": 1.0},
                                         {"value": "track_order", "probability": 0.0}], "confidence": 1.0}],
          "usage": {"input_tokens": 90}}
    p = adapters.parse_decisions(ok, item())
    assert p.status == "ok" and p.answers["intent"].probs == {"track_order": 0.0, "get_refund": 1.0}
    refused = {"answers": [{"type": "refusal", "name": "intent"}]}
    assert adapters.parse_decisions(refused, item()).status == "refusal"


def test_parse_opus_json_truncation_refusal_and_bad_label():
    body = {"intent": {"choice": "track_order", "probabilities": [{"value": "track_order", "probability": 0.9},
                                                                    {"value": "get_refund", "probability": 0.1}]}}
    raw = {"stop_reason": "end_turn", "content": [{"type": "text", "text": json.dumps(body)}],
           "usage": {"input_tokens": 500, "output_tokens": 60}}
    p = adapters.parse_opus(raw, item())
    assert p.status == "ok" and p.output_tokens == 60 and p.answers["intent"].label == "track_order"
    assert adapters.parse_opus({"stop_reason": "max_tokens"}, item()).status == "truncated"
    assert adapters.parse_opus({"stop_reason": "refusal"}, item()).status == "refusal"
    body["intent"]["choice"] = "not_an_option"
    raw["content"][0]["text"] = json.dumps(body)
    assert adapters.parse_opus(raw, item()).status == "invalid"


def test_negative_or_zero_probabilities_are_invalid():
    for probs in ({"track_order": -0.1, "get_refund": 1.1}, {"track_order": 0, "get_refund": 0}):
        raw = {"answers": {"intent": {"choice": "track_order", "probabilities": probs}}}
        assert adapters.parse_jev(raw, item()).status == "invalid"


def test_strip_images_keeps_logs_small():
    payload = {"images": ["data:image/jpeg;base64," + "A" * 5000],
               "messages": [{"content": [{"type": "image", "source": {"data": "B" * 5000}}]}]}
    s = json.dumps(adapters.strip_images(payload))
    assert "AAAA" not in s and "BBBB" not in s
