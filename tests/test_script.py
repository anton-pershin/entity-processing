import json
from pathlib import Path

import pytest
from hydra import compose, initialize_config_dir
from omegaconf import OmegaConf

import scripts.extract_entities as extract_script


class FakeLlm:
    url = "http://test-llm/v1/chat/completions"
    authorization = "Bearer test"
    model = "test-model"
    max_output_tokens = 2048
    enable_thinking = False


def _run_with_stub(monkeypatch, responses: list[object], cfg):
    calls = []
    response_iter = iter(responses)

    def request_based_on_message_history(**kwargs):
        calls.append(kwargs)
        response = next(response_iter)
        if isinstance(response, Exception):
            raise response
        return {"content": response}

    monkeypatch.setattr(
        "rally.interaction.request_based_on_message_history",
        request_based_on_message_history,
    )
    monkeypatch.setattr(extract_script, "instantiate", lambda _config: FakeLlm())
    extract_script.run(cfg)
    return calls


def _config(input_path: Path, output_path: Path, **overrides):
    values = {
        "input": str(input_path),
        "output": str(output_path),
        "entity_types": ["PEOPLE", "ORGANIZATION"],
        "relation_types": ["WORK_FOR"],
        "sentiment_types": ["POSITIVE", "NEUTRAL"],
        "system_prompt": "Test system prompt",
        "llm": {},
    }
    values.update(overrides)
    return OmegaConf.create(values)


def _write_input(path: Path, documents: list[dict]) -> None:
    path.write_text(
        "".join(
            json.dumps(document, ensure_ascii=False) + "\n" for document in documents
        ),
        encoding="utf-8",
    )


def _read_output(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]


def _empty_response() -> str:
    return json.dumps({"entities": [], "relations": []})


def test_script_smoke_preserves_order_ids_and_contract(
    monkeypatch, tmp_path: Path
) -> None:
    input_path = tmp_path / "input.jsonl"
    output_path = tmp_path / "output.jsonl"
    documents = [
        {"doc_id": "first", "text": "Первый документ"},
        {"doc_id": "second", "text": "Second document"},
    ]
    _write_input(input_path, documents)

    calls = _run_with_stub(
        monkeypatch,
        responses=[_empty_response(), _empty_response()],
        cfg=_config(input_path, output_path),
    )

    output = _read_output(output_path)
    assert [record["doc_id"] for record in output] == ["first", "second"]
    assert all(set(record) == {"doc_id", "entities", "relations"} for record in output)
    assert [call["model"] for call in calls] == ["test-model", "test-model"]
    assert [call["max_output_tokens"] for call in calls] == [2048, 2048]
    assert "Первый документ" in calls[0]["message_history"][1]["content"]
    assert "PEOPLE" in calls[0]["message_history"][1]["content"]


def test_script_failure_isolation_logs_and_continues(
    monkeypatch, tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    input_path = tmp_path / "input.jsonl"
    output_path = tmp_path / "output.jsonl"
    _write_input(
        input_path,
        [
            {"doc_id": "failed", "text": "bad"},
            {"doc_id": "later", "text": "good"},
        ],
    )

    _run_with_stub(
        monkeypatch,
        responses=[ValueError("stub failure"), _empty_response()],
        cfg=_config(input_path, output_path),
    )

    output = _read_output(output_path)
    assert output[0] == {"doc_id": "failed", "entities": [], "relations": []}
    assert output[1]["doc_id"] == "later"
    assert "failed" in caplog.text
    assert "stub failure" in caplog.text


def test_hydra_validation_overrides_and_model_boundary(
    monkeypatch, tmp_path: Path
) -> None:
    input_path = tmp_path / "input.jsonl"
    output_path = tmp_path / "output.jsonl"
    _write_input(input_path, [{"doc_id": "one", "text": "text"}])

    with initialize_config_dir(
        config_dir=str(Path(__file__).parents[1] / "config"), version_base="1.3"
    ):
        cfg = compose(
            config_name="config_extract_entities",
            overrides=[
                f"input={input_path}",
                f"output={output_path}",
                "entity_types=[CUSTOM]",
                "relation_types=[RELATES]",
                "sentiment_types=[MIXED]",
                "llm.model=override-model",
            ],
        )

    calls = _run_with_stub(monkeypatch, responses=[_empty_response()], cfg=cfg)
    prompt = calls[0]["message_history"][1]["content"]
    assert calls[0]["model"] == "test-model"
    assert "CUSTOM" in prompt
    assert "RELATES" in prompt
    assert "MIXED" in prompt


def test_malformed_input_lines_are_skipped_and_later_documents_continue(
    monkeypatch, tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    input_path = tmp_path / "input.jsonl"
    output_path = tmp_path / "output.jsonl"
    input_path.write_text(
        json.dumps({"doc_id": "first", "text": "first"})
        + "\nnot-json\n\n"
        + json.dumps({"doc_id": "last", "text": "last"})
        + "\n",
        encoding="utf-8",
    )

    _run_with_stub(
        monkeypatch,
        responses=[_empty_response(), _empty_response()],
        cfg=_config(input_path, output_path),
    )

    output = _read_output(output_path)
    assert [record["doc_id"] for record in output] == ["first", "last"]
    assert "input line 2" in caplog.text
    assert "input line 3" in caplog.text


def test_validation_contract_asserts_ids_and_relation_endpoints(
    monkeypatch, tmp_path: Path
) -> None:
    input_path = tmp_path / "input.jsonl"
    output_path = tmp_path / "output.jsonl"
    documents = [
        {"doc_id": "first", "text": "First document"},
        {"doc_id": "second", "text": "Second document"},
    ]
    _write_input(input_path, documents)
    response = json.dumps(
        {
            "entities": [
                {
                    "entity_id": "e1",
                    "mention": "Alice",
                    "type": "PEOPLE",
                    "sentiment": "NEUTRAL",
                },
                {
                    "entity_id": "e2",
                    "mention": "Acme",
                    "type": "ORGANIZATION",
                    "sentiment": "POSITIVE",
                },
            ],
            "relations": [{"relation_type": "WORK_FOR", "head": "e1", "tail": "e2"}],
        }
    )

    _run_with_stub(
        monkeypatch,
        responses=[response, response],
        cfg=_config(input_path, output_path),
    )

    output = _read_output(output_path)
    assert {record["doc_id"] for record in output} == {
        document["doc_id"] for document in documents
    }
    for record in output:
        entity_ids = [entity["entity_id"] for entity in record["entities"]]
        assert len(entity_ids) == len(set(entity_ids))
        entity_id_set = set(entity_ids)
        for relation in record["relations"]:
            assert relation["head"] in entity_id_set
            assert relation["tail"] in entity_id_set


def test_exact_validation_overrides_compose_and_run(
    monkeypatch, tmp_path: Path
) -> None:
    input_path = tmp_path / "input.jsonl"
    output_path = tmp_path / "output.jsonl"
    _write_input(input_path, [{"doc_id": "one", "text": "text"}])

    with initialize_config_dir(
        config_dir=str(Path(__file__).parents[1] / "config"), version_base="1.3"
    ):
        cfg = compose(
            config_name="config_extract_entities",
            overrides=[
                f"input={input_path}",
                f"output={output_path}",
                "entity_types=[LOCATION,ORGANIZATION,PEOPLE,OTHER]",
                "relation_types=[WORK_FOR,KILL,ORGANIZATION_BASED_IN,LIVE_IN,LOCATED_IN]",
                "sentiment_types=[POSITIVE,NEUTRAL,NEGATIVE]",
            ],
        )

    _run_with_stub(monkeypatch, responses=[_empty_response()], cfg=cfg)
    assert _read_output(output_path)[0]["doc_id"] == "one"
