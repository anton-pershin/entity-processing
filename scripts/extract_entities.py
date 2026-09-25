"""Run prompt-based extraction over a JSONL document file."""

from __future__ import annotations

import json
import logging
import time
from pathlib import Path
from typing import Any, Callable

import hydra
from hydra.utils import instantiate
from omegaconf import DictConfig

logger = logging.getLogger(__name__)
CONFIG_NAME = "config_extract_entities"


def _request_factory(
    llm: Any, retries: int = 3, backoff_seconds: float = 1.0
) -> Callable[[str, str], str]:
    from rally.interaction import request_based_on_message_history

    if retries < 0:
        raise ValueError("retries must be non-negative")
    if backoff_seconds < 0:
        raise ValueError("backoff_seconds must be non-negative")

    def request(system_prompt: str, user_prompt: str) -> str:
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ]
        last_error: Exception | None = None
        for attempt in range(retries + 1):
            try:
                response = request_based_on_message_history(
                    llm_server_url=llm.url,
                    message_history=messages,
                    authorization=llm.authorization,
                    model=llm.model,
                    max_output_tokens=llm.max_output_tokens,
                    enable_thinking=llm.enable_thinking,
                )
                if not isinstance(response, dict) or not isinstance(
                    response.get("content"), str
                ):
                    logger.error("rally returned an invalid response: %r", response)
                    raise ValueError("rally returned a response without text content")
                return response["content"]
            except Exception as error:
                last_error = error
                if attempt == retries:
                    break
                delay = backoff_seconds * (2**attempt)
                logger.warning(
                    "LLM request failed (attempt %d/%d); retrying in %.2f seconds: %s",
                    attempt + 1,
                    retries,
                    delay,
                    error,
                )
                time.sleep(delay)
        assert last_error is not None
        raise last_error

    return request


def _config_tuple(value: Any) -> tuple[str, ...]:
    return tuple(str(item) for item in value)


def run(cfg: DictConfig) -> None:
    """Process all configured input documents in order."""
    from entity_processing import ExtractionConfig, extract_document

    if cfg.input is None or cfg.output is None:
        raise ValueError("Both input and output must be supplied")

    input_path = Path(str(cfg.input))
    output_path = Path(str(cfg.output))
    output_path.parent.mkdir(parents=True, exist_ok=True)
    extraction_config = ExtractionConfig(
        entity_types=_config_tuple(cfg.entity_types),
        relation_types=_config_tuple(cfg.relation_types),
        sentiment_types=_config_tuple(cfg.sentiment_types),
        system_prompt=str(cfg.system_prompt),
    )
    llm = instantiate(cfg.llm)
    request = _request_factory(
        llm,
        retries=int(getattr(cfg, "retries", 3)),
        backoff_seconds=float(getattr(cfg, "backoff_seconds", 1.0)),
    )

    with (
        input_path.open(encoding="utf-8") as input_file,
        output_path.open("w", encoding="utf-8") as output_file,
    ):
        for line_number, line in enumerate(input_file, start=1):
            if not line.strip():
                logger.error("Skipping blank input line %d", line_number)
                continue
            try:
                document = json.loads(line)
                if not isinstance(document, dict):
                    raise ValueError("input record must be a JSON object")
                doc_id = document["doc_id"]
                text = document["text"]
            except Exception:
                logger.exception("Failed to parse input line %d", line_number)
                continue

            try:
                result = extract_document(str(text), extraction_config, request)
            except Exception:
                logger.exception(
                    "Failed to process document %r on line %d", doc_id, line_number
                )
                result = {"entities": [], "relations": []}
            output_file.write(
                json.dumps({"doc_id": doc_id, **result}, ensure_ascii=False) + "\n"
            )


if __name__ == "__main__":
    hydra.main(
        config_path="../config",
        config_name=CONFIG_NAME,
        version_base="1.3",
    )(run)()
