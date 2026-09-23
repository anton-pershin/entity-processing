import json

from entity_processing.processor import (
    ExtractionConfig,
    build_user_prompt,
    extract_document,
    normalize_result,
)


CONFIG = ExtractionConfig(
    entity_types=("PEOPLE", "ORGANIZATION"),
    relation_types=("WORK_FOR",),
    sentiment_types=("POSITIVE", "NEUTRAL"),
    system_prompt="Configured system prompt",
)


def test_prompt_contains_document_and_configured_labels() -> None:
    prompt = build_user_prompt("Elena joined Northstar Labs.", CONFIG)
    assert "Elena joined Northstar Labs." in prompt
    assert "PEOPLE" in prompt
    assert "WORK_FOR" in prompt
    assert "POSITIVE" in prompt


def test_extract_document_makes_one_request_and_returns_structured_result() -> None:
    calls = []

    def request(system_prompt: str, user_prompt: str) -> str:
        calls.append((system_prompt, user_prompt))
        return json.dumps(
            {
                "entities": [
                    {"entity_id": "e1", "mention": "Elena", "type": "PEOPLE", "sentiment": "NEUTRAL"},
                    {"entity_id": "e2", "mention": "Northstar Labs", "type": "ORGANIZATION", "sentiment": "POSITIVE"},
                ],
                "relations": [{"relation_type": "WORK_FOR", "head": "e1", "tail": "e2"}],
            }
        )

    result = extract_document("Elena joined Northstar Labs.", CONFIG, request)

    assert len(calls) == 1
    assert result["entities"][0]["mention"] == "Elena"
    assert result["relations"] == [{"relation_type": "WORK_FOR", "head": "e1", "tail": "e2"}]


def test_normalize_result_discards_invalid_values_and_keeps_first_duplicate() -> None:
    result = normalize_result(
        {
            "entities": [
                {"entity_id": "e1", "mention": "bad", "type": "UNKNOWN", "sentiment": "NEUTRAL"},
                {"entity_id": "e1", "mention": "Elena", "type": "PEOPLE", "sentiment": "NEUTRAL"},
                {"entity_id": "e1", "mention": "Other Elena", "type": "PEOPLE", "sentiment": "POSITIVE"},
                {"entity_id": "e2", "mention": "Labs", "type": "ORGANIZATION", "sentiment": "POSITIVE"},
            ],
            "relations": [
                {"relation_type": "WORK_FOR", "head": "e1", "tail": "e2"},
                {"relation_type": "UNKNOWN", "head": "e1", "tail": "e2"},
                {"relation_type": "WORK_FOR", "head": "e1", "tail": "missing"},
            ],
        },
        CONFIG,
    )
    assert [entity["mention"] for entity in result["entities"]] == ["Elena", "Labs"]
    assert len(result["relations"]) == 1


def test_empty_result_is_preserved() -> None:
    assert normalize_result({"entities": [], "relations": []}, CONFIG) == {
        "entities": [],
        "relations": [],
    }
