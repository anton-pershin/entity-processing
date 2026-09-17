## entity-processing constitution spec

### 1. Executive summary

#### 1.1 Project description 

entity-processing is a research-oriented Python toolkit for extracting structured information from text documents (messages, news articles). The toolkit provides three core capabilities: (1) entity extraction (NER-like identification of persons, organizations, locations, concepts, etc.), (2) sentiment analysis per entity (determining the author's sentiment toward each extracted entity) and (3) relation extraction (identification of relations between entities within one document). The project follows a hydra-backed repository structure with configurable executable scripts for each processing pipeline.

Knowledge graph construction is out of scope for this spec revision entirely (it was considered and deferred; subject to revision in future).

#### 1.2 Project motivation

The project addresses the need for systematic, research-grade text analysis that goes beyond simple keyword matching or flat NER. By combining entity extraction with sentiment attribution and relation extraction, it enables holistic understanding of large document corpora — supporting research questions about how entities are discussed, connected, and characterized across messages and news sources.

#### 1.3 Implementation repos

`entity-processing`

#### 1.4 Execution mode

Autonomous

### 2. Requirement analysis

#### 2.1 Functional requirements

**FR1. Entity Extraction**: Given a raw text document, identify and classify entities (persons, organizations, locations, dates, concepts, etc.) with their mentions and types.

**FR2. Sentiment Analysis per Entity**: For each extracted entity, determine the author's sentiment (positive, negative, neutral) toward that specific entity within the context of the document.

**FR3. Relation Extraction**: For extracted entities, identify relations between entities and classify these relations (located at, work at, etc.).

#### 2.2 Non-functional requirements

**NFR1. Time Performance**: 100 documents must be processed within 10 minutes.

**NFR2. LLM**: The default LLM is `glm-5.3-flash`. Model overrides via Hydra configuration are allowed (e.g. for research experiments), but validation is performed with `glm-5.3-flash` only.

#### 2.3 Preferences

**P1. Configurability**: All parameters (model, endpoint, prompt templates, entity types) must be configurable via Hydra YAML configs — no hardcoded values.

**P2. Modularity**: If possible, each processing step (e.g., NER, sentiment, relations) should be independently usable and composable.

**P3. LLM Backend**: All NLP capabilities use the `rally` library for LLM interaction, with the API endpoint and model name configurable via Hydra.

**P4. Type Safety**: All code must use Python type hints, enforced by linters.

**P5. Extensibility**: New entity types and relation types should be addable without modifying core code.

**P6. Multi-language Support**: All extraction and analysis capabilities should work across multiple languages, not limited to English.

### 3. Acceptance criteria

Any implementation is validated by the validation subproject.
The validation service should be invoked via HTTP (localhost, port 8456) where you should send the POST request with the following json payload:
```
{
  "repo": "<clonable link to repo>",
  "commit": "<commit hash>",
  "solution_overrides": "<args separated by whitespaces>"
}
```

The validation service will clone the repo, go to the specified commit and attempt to run `scripts/extract_entities.py` with the args provided in `solution_overrides` and three additional arguments:
- `entity_types=[type1, type2, ...]`
- `relation_types=[type1, type2, ...]`
- `sentiment_types=[type1, type2, ...]`

The script will also receive the following two arguments (Hydra-style `key=value`, same as above):
- `input=<path to a JSONL file with documents>` — each line is a document: `{"doc_id": "...", "text": "..."}`
- `output=<path to the JSONL output file>`

The dataset paths point to files prepared by the validation service; the script must not rely on anything else being present in the working directory.

Possible entity types: `LOCATION`, `ORGANIZATION`, `PEOPLE`, `OTHER`

Possible relation types: `WORK_FOR`, `KILL`, `ORGANIZATION_BASED_IN`, `LIVE_IN`, `LOCATED_IN`

Possible sentiment types: `POSITIVE`, `NEUTRAL`, `NEGATIVE`

It will expect the script to produce a JSONL file (at the path given by `output`) with one record per input document, in the following format:
```
{
  "doc_id":"...",
  "entities": [
    {
      "entity_id":"e1",
      "mention":"...",
      "type":"<entity type>",
      "sentiment":"<sentiment>"
    },
    ...
  ],
  "relations": [
    {
      "relation_type":"<relation type>",
      "head":"e4",
      "tail":"e2"
    },
    ...
  ]
}
...
```

### 4. Insight

**Idea 1: Traditional NLP pipeline (spaCy, transformers, rule-based).** Use dedicated models for each task: spaCy or a fine-tuned BERT for NER, sentiment classifiers for sentiment analysis, rule-based or pattern-matching extractors for facts, and a separate graph construction module. This approach offers full control over each component and can be highly optimized for speed and cost.

**Idea 2: LLM-based pipeline (chosen).** Use a single LLM (via the `rally` library) to perform all extraction tasks — entity recognition, sentiment attribution, fact extraction, and relation identification — through carefully designed prompts. The LLM handles multi-language natively and requires no task-specific model training.

**Rationale for choosing Idea 2:**
- **Research focus**: The project's primary goal is answering research questions, not achieving production-scale throughput. LLM-based extraction provides high-quality results with minimal engineering overhead.
- **Multi-language**: A capable LLM handles English and Russian (and other languages) out of the box, whereas traditional approaches require separate models per language.
- **Flexibility**: Prompts can be iterated quickly as research questions evolve, without retraining models or adjusting feature pipelines.
- **Unified interface**: Using `rally` as the LLM abstraction layer keeps the codebase clean and makes swapping models or endpoints trivial.
- **Simplicity**: Fewer dependencies, no model training infrastructure, and easier to onboard collaborators.

**Note 1:** we may gradually turn to Idea 1 if we want to optimize the computational cost in future. We should keep this in mind while developing the repo.

**Note 2:** the sentiment analysis task we need to solve is called *targeted sentiment analysis* in the literature. A classical citation would be [Jiang et al. Target-dependent Twitter sentiment classification (2011)](https://aclanthology.org/P11-1016.pdf). Another branch of sentiment analysis which might be useful in future is *aspect-based sentiment analysis (ABSA)* where we are interested in polarities towards various aspects of the entity rather than the overall sentiment about the entity. These two branches are combined in targeted aspect-based sentiment analysis, see [Saeidi et al. SentiHood: targeted aspect based sentiment analysis dataset for urban neighbourhoods](https://arxiv.org/pdf/1610.03771). 

### 5. Overall solution design

#### 5.1 High-level design

```mermaid
flowchart LR
    subgraph Input
        A["Raw text documents"]
    end

    subgraph EntityProcessing["entity-processing scripts"]
        B["scripts/extract_entities.py"]
    end

    subgraph Storage
        G["extracted.jsonl"]
    end

    subgraph Config["config/"]
        K["Hydra YAML configs"]
    end

    subgraph LLM
        L["rally library"]
        M["OpenAI-compatible API"]
    end

    A --> B --> G

    B <--> L <--> M
    B <--> K
```

**Note:** the output JSONL file includes sentiments and relations associated with entities.

#### 5.2 Core components

1. **`scripts/extract_entities.py`** — Executable script for entity extraction, configured via Hydra. Given that we implement NER by calling an LLM, we should extract local (to a document) relations and perform sentiment analysis within the same API call.
2. **`config/`** — Hydra configuration files defining prompts, LLM settings (`rally` backend config), and entity types.
