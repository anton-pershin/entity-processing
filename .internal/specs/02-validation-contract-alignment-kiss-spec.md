## Validation-contract alignment

### 1. Requirement analysis

This KISS change aligns the solution project with the revised entity-processing constitution and makes the validation-facing contract executable and testable. It does not change the extraction algorithm or validation service.

R1. Revised master-label defaults

The solution’s default configuration must use only the current master vocabularies:

- Entity labels: `PEOPLE`, `ORGANIZATION`, `LOCATION`
- Relation labels: `WORK_FOR`, `KILL`, `ORGANIZATION_BASED_IN`, `LIVE_IN`, `LOCATED_IN`
- Sentiment labels: `POSITIVE`, `NEUTRAL`, `NEGATIVE`

`OTHER` must not appear as a default or master entity label.

B1. A default-configured run accepts and emits only the current master labels.

R2. Dataset-specific label subsets

The solution must process each validation invocation using exactly the label lists supplied through Hydra. It must not assume that every master label is available for every dataset entry.

B2. An invocation may supply a strict subset such as `entity_types=[PEOPLE,LOCATION]`; entities using unavailable labels are discarded during normalization, while available labels remain valid.

R3. Revised multi-invocation contract

The solution must remain independently runnable for repeated validation invocations, each with its own input/output paths and label subsets. No labels, results, or state may leak between invocations.

B3. Two sequential invocations with different label subsets produce independently valid JSONL outputs.

R4. Configurable prompt template

All task-specific prompt text must be supplied through Hydra configuration. The processor must not hardcode the user-prompt instructions, JSON-shape description, or label-list wording.

The configured template must be able to receive at least:

- document text;
- available entity labels;
- available relation labels;
- available sentiment labels.

B4. Replacing the configured prompt template changes the prompt sent to the LLM while preserving the runtime label values and document text.

R5. Revised sentiment contract

The solution must preserve the constitution’s sentiment-bearing entity shape and runtime sentiment validation. It must not assume that entity type participates in sentiment matching or that sentiment recall is part of the solution contract.

B5. Sentiment values are accepted only when present in the invocation’s `sentiment_types` list; the output remains compatible with validation’s `(doc_id, mention, sentiment)` matching key.

R6. Validation-facing test coverage

The solution test suite must cover the revised contract at script level, using a deterministic LLM double and no real network or credentials.

Coverage must include:

- current default labels without `OTHER`;
- restricted label subsets;
- repeated invocations with different subsets;
- configurable prompt-template overrides;
- output IDs and relation endpoint validity;
- per-document failure isolation;
- malformed and fenced model responses;
- the exact validation invocation argument shape.

R7. Dependency and invocation readiness

The solution’s declared runtime dependencies and import placement must allow the validation-shaped execution path to be inspected and executed in the intended environment. The implementation must not require the validation service’s working directory or undeclared local modules.

This includes ensuring that:

- the `rally` dependency resolves to the intended Anton Pershin repository rather than an unrelated package;
- configuration inspection with `scripts/extract_entities.py --cfg job` does not require runtime-only imports;
- the solution test suite can install/import the declared dependencies in a clean solution environment.

B7. The exact Hydra configuration inspection command exits successfully without credentials or input data.

R8. Credential configuration failure

Before processing any input documents, the solution must reject a missing LLM credential with a clear logged error and a nonzero failure. It must not invoke the LLM, write per-document empty fallback records, or report a successful run when the configured credential is absent.

B8. A run with an absent credential fails before opening the input/output processing loop; document-level empty fallback records remain reserved for failures that occur after a credentialed request begins.

### 2. Tests

All tests use deterministic LLM doubles and temporary files. No test makes a real LLM or network request.

T1. Default master-label configuration

Compose the default Hydra configuration and assert that:

- `entity_types` is exactly `[LOCATION, ORGANIZATION, PEOPLE]` or the constitutionally equivalent order;
- `OTHER` is absent;
- relation and sentiment defaults contain the current master vocabularies.

Covers R1/B1.

T2. Runtime label-subset normalization

Return a response containing:

- an entity whose type is in the supplied subset;
- an entity whose type is not in the supplied subset;
- valid and invalid sentiments relative to the supplied sentiment list;
- valid and invalid relation types relative to the supplied relation list.

Run the processor with restricted runtime labels and assert that only values allowed by that invocation remain, with valid relations retaining resolvable endpoints.

Covers R2/B2 and R5/B5.

T3. Independent repeated invocations

Run the script twice sequentially using different temporary input/output files and different label subsets. Assert that:

- each output corresponds only to its own input;
- labels from the first invocation do not affect the second;
- each output satisfies the document-local entity and relation contracts.

Covers R3/B3.

T4. Configurable prompt template

Compose the script configuration with a custom prompt template. Use a recording LLM double and assert that the request contains:

- the custom template text;
- the current document text;
- the supplied entity labels;
- the supplied relation labels;
- the supplied sentiment labels.

Assert that the default task-specific user-prompt wording is not added independently by the processor when the custom template replaces it.

Covers R4/B4.

T5. Sentiment output contract

Return entities with:

- an allowed sentiment;
- an unavailable sentiment;
- different entity types sharing the same sentiment.

Assert that allowed sentiment values are retained, unavailable values are removed, and the output contains the constitution’s entity-level sentiment field without adding any type-dependent sentiment behavior.

Covers R5/B5.

T6. Script-level output contract

Run `scripts/extract_entities.py` through its callable script path with multiple documents and a deterministic LLM double. Assert:

- one output record per valid input document;
- input order and `doc_id` preservation;
- unique entity IDs within each document;
- every relation endpoint resolves within that document;
- output labels belong to the labels supplied for that invocation.

Covers R6 and the output portions of R1–R3/R5.

T7. Failure isolation and response parsing

Run a multi-document input where:

- one response is raw JSON;
- one response is fenced JSON;
- one response is malformed or raises an LLM error;
- a later response is valid.

Assert that the malformed document receives empty entity and relation lists, the failure is logged, and later documents are still written and processed.

Covers R6 and the existing failure-isolation behavior.

T8. Exact validation invocation shape

Execute the script using the validation service’s argument shape:

```text
input=<path>
output=<path>
entity_types=<list>
relation_types=<list>
sentiment_types=<list>
```

Assert successful completion and parseable JSONL output.

Covers R6.

T9. Configuration inspection

Run:

```text
python scripts/extract_entities.py --cfg job
```

in the intended solution environment without credentials, input data, or output data. Assert exit status zero and assert that the resolved configuration contains the expected default model and current default labels.

Covers R7/B7.

T10. Dependency and import-path verification

In a clean temporary solution environment or clone:

- install the project from its declared metadata;
- verify that the intended `rally` package is importable;
- run the configuration inspection command;
- run the deterministic test suite.

Assert that no dependency resolves to an unrelated package and that configuration inspection does not require runtime-only imports.

Covers R7.

T11. Missing-credential fail-fast

Run `run(cfg)` with a deterministic fake LLM whose credential and authorization are absent or placeholder values. Assert that it raises a clear credential error before opening the input/output processing loop and that the request double is never called.

Covers R8/B8.

### 3. Implementation plan

#### 3.1 Implementation repos

The implementation uses the `entity-processing` repository only.

#### 3.2 Solution design

1. Configuration defaults

   Update `config/config_extract_entities.yaml` so its default entity labels contain only `LOCATION`, `ORGANIZATION`, and `PEOPLE`. Keep the current relation and sentiment master vocabularies.

2. Configurable prompt template

   Add a Hydra-configured user prompt template to `config/config_extract_entities.yaml`.

   The template will receive these named values:

   - `document`;
   - `entity_types`;
   - `relation_types`;
   - `sentiment_types`.

   `build_user_prompt()` will format the configured template with these values and will no longer append hardcoded extraction instructions, JSON-shape text, or label-list text. The default configuration will contain the current baseline prompt wording, preserving existing behavior while making it replaceable.

3. Processor configuration boundary

   Extend `ExtractionConfig` with the configured user prompt template. Keep runtime label lists in `ExtractionConfig`, because normalization must continue to validate each response against the labels supplied for that invocation.

   `build_user_prompt()` remains responsible only for rendering the configured template with the current document and runtime label lists.

4. Runtime label handling

   Preserve the existing normalization behavior: entity types, relation types, and sentiments are validated against the `ExtractionConfig` for the current invocation. No global mutable label state will be introduced.

   This makes sequential invocations with different label subsets independent by construction.

5. Script-level configuration wiring

   Update `scripts/extract_entities.py` so `run()` passes the configured user prompt template into `ExtractionConfig`.

   Keep the existing callable `run(cfg)` boundary and deterministic request-factory seam used by the tests.

6. Validation-shaped tests

   Extend the existing tests rather than creating a second test framework:

   - test the revised default labels;
   - test restricted runtime vocabularies;
   - test two sequential invocations with different vocabularies;
   - test custom prompt-template rendering;
   - retain and extend output-contract, failure-isolation, malformed-response, fenced-response, and exact-invocation tests.

   All LLM interactions remain mocked.

7. Dependency and configuration-inspection readiness

   Preserve the Git-based `rally` dependency declaration already present in `pyproject.toml`.

   Move runtime-only imports out of module import paths that are exercised during configuration inspection. In particular, importing the script for `--cfg job` must not require the `rally` package or solution package imports before Hydra composition completes.

   Add or update a test/subprocess check for:

   ```text
   python scripts/extract_entities.py --cfg job
   ```

   The check must run without credentials, input data, or output data.

8. Credential validation

Validate the instantiated LLM credential before opening the input/output files or creating the request-processing loop. A missing or placeholder credential must log a clear error and raise a nonzero failure, preventing misleading empty fallback records from an entirely unauthenticated run.

Keep per-document empty fallback handling for failures that occur after a credentialed request begins.

9. Clean-environment verification

   Before considering the implementation complete, create a temporary clean environment or clone and verify:

   - installation from the declared project metadata;
   - importability of the intended `rally` package;
   - successful Hydra configuration inspection;
   - successful deterministic test execution.

#### 3.3 Todo list

1. [ ] Write the tests.
2. [ ] Run all the tests and ensure that they fail.
3. [ ] Update default entity labels and remove `OTHER` from configuration and obsolete test invocations.
4. [ ] Add the configurable user prompt template to Hydra configuration.
5. [ ] Extend `ExtractionConfig` and `build_user_prompt()` to render the configured template with runtime values.
6. [ ] Wire the configured template through `scripts/extract_entities.py`.
7. [ ] Add tests for restricted labels, independent repeated invocations, custom prompt templates, and the revised default vocabularies.
8. [ ] Add or update configuration-inspection and dependency/import-path verification.
9. [ ] Run the focused test suite and fix implementation or test issues.
10. [ ] Run the complete available test suite and verify the exact validation-service invocation shape locally with a mocked LLM.
9. [ ] Validate missing credentials before opening processing files and add the T11 fail-fast test.
10. [ ] Reproduce the clean-environment installation and configuration-inspection checks.
11. [ ] Review generated JSONL against the current constitution contract and remove temporary test artifacts.

#### 3.4 Modification summary

| File | Action |
|------|--------|
| `config/config_extract_entities.yaml` | Modified: replace the obsolete default `OTHER` label and add the configurable user prompt template. |
| `entity_processing/processor.py` | Modified: accept the configured user prompt template and render it with document text and runtime label lists instead of hardcoding the user-prompt content. |
| `scripts/extract_entities.py` | Modified: pass the configured prompt template into `ExtractionConfig` and keep configuration inspection independent of runtime-only imports. |
| `tests/test_processor.py` | Modified: test configurable prompt-template rendering and runtime label handling. |
| `tests/test_script.py` | Modified: test revised defaults, restricted labels, repeated independent invocations, the exact validation invocation shape, and configuration inspection. |
| `pyproject.toml` | Modified only if needed to make the declared dependency and clean-environment verification explicit; preserve the Git-based `rally` dependency. |
