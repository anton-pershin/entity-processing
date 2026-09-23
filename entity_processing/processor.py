"""Core data structures and prompt processing for entity extraction."""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from typing import Any, Callable, Mapping, Sequence

logger = logging.getLogger(__name__)

LlmRequest = Callable[[str, str], str]


@dataclass(frozen=True)
class ExtractionConfig:
    """Configuration used to construct one document-level extraction request."""

    entity_types: tuple[str, ...]
    relation_types: tuple[str, ...]
    sentiment_types: tuple[str, ...]
    system_prompt: str


def build_user_prompt(text: str, config: ExtractionConfig) -> str:
    """Build the single prompt sent for one document."""
    return (
        f"{config.system_prompt}\n\n"
        "Extract entities, targeted sentiment, and local relations from the document.\n"
        "Return only a JSON object with this shape: "
        '{"entities": [{"entity_id": "e1", "mention": "...", '
        '"type": "...", "sentiment": "..."}], '
        '"relations": [{"relation_type": "...", "head": "e1", '
        '"tail": "e2"}]}\n'
        f"Allowed entity types: {list(config.entity_types)}\n"
        f"Allowed relation types: {list(config.relation_types)}\n"
        f"Allowed sentiment types: {list(config.sentiment_types)}\n\n"
        f"Document:\n{text}"
    )


def _as_string(value: Any) -> str | None:
    return value if isinstance(value, str) else None


def normalize_result(
    raw: Any,
    config: ExtractionConfig,
) -> dict[str, list[dict[str, str]]]:
    """Normalize a model result to the public output shape."""
    if not isinstance(raw, Mapping):
        raise ValueError("LLM result must be a JSON object")

    entities: list[dict[str, str]] = []
    retained_ids: set[str] = set()
    raw_entities = raw.get("entities", [])
    raw_relations = raw.get("relations", [])
    if not isinstance(raw_entities, Sequence) or isinstance(raw_entities, (str, bytes)):
        raise ValueError("entities must be a list")
    if not isinstance(raw_relations, Sequence) or isinstance(raw_relations, (str, bytes)):
        raise ValueError("relations must be a list")

    for candidate in raw_entities:
        if not isinstance(candidate, Mapping):
            continue
        entity_id = _as_string(candidate.get("entity_id"))
        mention = _as_string(candidate.get("mention"))
        entity_type = _as_string(candidate.get("type"))
        sentiment = _as_string(candidate.get("sentiment"))
        if (
            entity_id is None
            or mention is None
            or entity_type not in config.entity_types
            or sentiment not in config.sentiment_types
            or entity_id in retained_ids
        ):
            continue
        retained_ids.add(entity_id)
        entities.append(
            {
                "entity_id": entity_id,
                "mention": mention,
                "type": entity_type,
                "sentiment": sentiment,
            }
        )

    relations: list[dict[str, str]] = []
    for candidate in raw_relations:
        if not isinstance(candidate, Mapping):
            continue
        relation_type = _as_string(candidate.get("relation_type"))
        head = _as_string(candidate.get("head"))
        tail = _as_string(candidate.get("tail"))
        if (
            relation_type in config.relation_types
            and head in retained_ids
            and tail in retained_ids
        ):
            relations.append(
                {"relation_type": relation_type, "head": head, "tail": tail}
            )

    return {"entities": entities, "relations": relations}


def extract_document(
    text: str,
    config: ExtractionConfig,
    request: LlmRequest,
) -> dict[str, list[dict[str, str]]]:
    """Extract and normalize one document using exactly one LLM request."""
    response_text = request(config.system_prompt, build_user_prompt(text, config))
    raw = json.loads(response_text)
    return normalize_result(raw, config)
