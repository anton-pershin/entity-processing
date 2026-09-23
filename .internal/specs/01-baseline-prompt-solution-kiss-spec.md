## Baseline prompt-based entity processing

### 1. Requirement analysis

This spec defines the first runnable baseline implementation for `entity-processing`. It intentionally uses one prompt-based LLM call per input document rather than separate NER, sentiment, and relation-extraction stages.

1. **Input contract.** `scripts/extract_entities.py` must accept the validation invocation's Hydra-style arguments: `input`, `output`, `entity_types`, `relation_types`, and `sentiment_types`. The input is JSONL with one object per line containing `doc_id` and `text`.
2. **Structured extraction.** For each document, the solution must ask the configured LLM to return structured data containing entities and relations. Each entity must contain a unique document-local `entity_id`, its exact text `mention`, an allowed configured `type`, and an allowed configured `sentiment`. Each relation must contain an allowed configured `relation_type` and `head`/`tail` references to entities from the same document.
3. **Single combined prompt.** Entity extraction, entity-targeted sentiment, and local relation extraction must be performed in one LLM request per document. The prompt must include the document text and the configured allowed labels, and must instruct the model to return only the required structured result.
4. **Configurable LLM access.** The LLM model, endpoint/backend settings, and prompt text must be supplied through Hydra configuration and the `rally` library. No model name, endpoint, entity label, relation label, or sentiment label may be hardcoded in the processing code. The default model remains `glm-5.3-flash` as required by the constitution.
5. **Output contract.** The solution must write exactly one JSON object per input document to the configured output JSONL path, preserving each input `doc_id` and using the constitution's `entities` and `relations` shape. Empty entity and relation lists are valid.
6. **Batch processing.** Documents must be processed independently in input order. One malformed or failed LLM response must not prevent later documents from being processed; the affected document must still receive a valid output record with empty `entities` and `relations`, and the failure must be reported through logging.
7. **Validation of model output.** The implementation must normalize model output before writing it: retain the first entity for each unique `entity_id`, discard entities with unknown types or sentiments, and discard relations with unknown types or endpoints that do not resolve to retained entities. An unparseable top-level response produces empty lists for that document.
8. **Baseline scope.** This implementation does not perform cross-document entity resolution, knowledge-graph construction, coreference resolution beyond what the prompt can infer locally, document chunking, parallel LLM requests, retries, or a separate sentiment/relation pipeline. These remain outside this KISS change.

### 2. Tests

The tests must use a deterministic mocked `rally` client or equivalent test double. No test may make a real LLM or network request. Temporary JSONL files should be used for script input and output.

1. **Input and output smoke test.** Run `scripts/extract_entities.py` against a small JSONL fixture with multiple documents and assert that it writes exactly one output record per input record, preserves document order and `doc_id`, and emits the required top-level fields.
2. **Prompt construction test.** Replace the LLM client with a recording test double and assert that one request is made for each document, each request contains the document text, and the configured entity, relation, and sentiment labels are present in the prompt. Assert that the configured model/backend is used.
3. **Structured extraction test.** Return a deterministic valid structured response from the mock client and assert that entity mentions, types, sentiments, and relations are copied into the output with the expected shape.
4. **Empty-result test.** Return a valid response containing empty `entities` and `relations` and assert that the empty lists are preserved.
5. **Output validation test.** Return responses containing an unknown entity type, unknown sentiment, unknown relation type, duplicate entity IDs, and relation endpoints that do not exist. Assert that invalid entities and relations are discarded, only the first valid occurrence of each entity ID is retained, and valid remaining data is retained.
6. **Per-document failure-isolation test.** Make the mock client fail or return malformed output for one document and succeed for a later document. Assert that the failed document receives empty lists, an error is logged, and the later document is still processed and written.
7. **Configuration test.** Run the script with non-default label lists and a non-default model value supplied through Hydra overrides. Assert that the prompt and output use those overrides rather than hardcoded defaults.
8. **Validation-contract test.** Run the produced JSONL through the same structural assumptions as the validation service and assert that every output `doc_id` corresponds to an input document, every entity ID is document-local and unique, and every relation endpoint resolves to an entity in that document.
9. **Regression test for the baseline invocation.** Execute the script with the exact argument shape used by the validation service (`input`, `output`, `entity_types`, `relation_types`, and `sentiment_types`) and assert successful completion and parseable JSONL output.

### 3. Implementation plan

#### 3.1 Implementation repos

The implementation uses the `entity-processing` repository only. The independently managed `entity-processing-validation` repository is not modified by this spec.

#### 3.2 Solution design

1. **Hydra entry point:** create `scripts/extract_entities.py` as the validation-facing executable. It loads the input/output paths, label lists, prompt settings, and `rally` LLM settings from Hydra, then processes documents sequentially.
2. **Configuration:** create the minimal project and Hydra configuration needed to run the script, including the default `glm-5.3-flash` model and configurable endpoint/backend parameters. Label lists and prompt text are exposed as configuration values.
3. **Prompt-based processor:** implement one document-level request that asks the LLM for a structured JSON result containing `entities` and `relations`. The processor uses the configured labels in the prompt and does not contain task-specific label constants.
4. **Output validation:** define typed internal models or equivalent validation helpers for the LLM result. Retain the first entity for each unique `entity_id`; discard entities with unknown types or sentiments; and discard relations with unknown types or unresolved endpoints. An unparseable response produces empty lists for that document.
5. **JSONL I/O and logging:** read documents line by line, write one result per input document in order, and log failures without terminating the remaining batch. Use standard logging rather than printing diagnostics from library logic.
6. **Tests:** add deterministic unit and integration tests with a mocked `rally` client. Tests must not require credentials or network access.

#### 3.3 Todo list

1. [ ] Write the tests.
2. [ ] Run all the tests and ensure that they fail.
3. [ ] Create the minimal Python project metadata and Hydra configuration required by the validation invocation.
4. [ ] Implement the structured internal result models and output-validation helpers.
5. [ ] Implement the single-document prompt processor using the configured `rally` client.
6. [ ] Implement `scripts/extract_entities.py` with sequential JSONL processing, failure isolation, logging, and output writing.
7. [ ] Run the focused tests and fix implementation or test issues.
8. [ ] Run the complete available test suite and verify the exact validation-service invocation shape locally with a mocked LLM.
9. [ ] Review the generated JSONL against the output contract and remove any temporary test artifacts.

#### 3.4 Modification summary

| File | Action |
|------|--------|
| `scripts/extract_entities.py` | New: Hydra entry point for document processing and JSONL I/O. |
| `entity_processing/` | New: prompt processor, typed result validation, and package initialization. |
| `config/` | New: Hydra defaults, model/backend settings, labels, and prompt configuration. |
| `tests/` | New: deterministic tests for prompt construction, processing, validation, failure isolation, and the CLI invocation. |
| `pyproject.toml` | New: project metadata and runtime/test dependencies required by the baseline. |
