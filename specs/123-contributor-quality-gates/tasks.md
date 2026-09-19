# Tasks: Contributor Quality Gates

**Input**: Design documents from `/specs/123-contributor-quality-gates/`  
**Prerequisites**: `spec.md`, `research.md`, `data-model.md`, `contracts/contract-test-runner.md`, `plan.md`, `quickstart.md`

## Format

`[ID] [P?] [Story] Description`

## Phase 1: Specification and Baseline

- [x] T001 Create the feature branch `feat/123-contributor-quality-gates`.
- [x] T002 Record the measured README, docs-gate, suite-count, CI, dependency, live, and Docker baseline in `research.md`.
- [x] T003 Create all required SDD artifacts under `specs/123-contributor-quality-gates/` before implementation.
- [x] T004 Run `scripts/verify-spec-artifacts.py` and correct any structural finding.

## Phase 2: Foundational Runner Contracts

- [x] T005 [P] Add fixture-based tests for manifest parity and deterministic matrix output in `tests/runner/test_run_contract_tests.py`.
- [x] T006 [P] Add fixture-based tests for `PASS`, `FAIL`, `BLOCKED_DEPENDENCY`, `ERROR`, `NEEDS_LIVE_CREDENTIALS`, and `NEEDS_DOCKER` mappings.
- [x] T007 [P] Add a credential-redaction assertion proving values never appear in human or JSON output.
- [x] T008 Add `tests/contract-suites.json` with exactly the 14 discovered suites and validate every required field/path.

**Checkpoint**: Metadata and result contracts fail before the runner implementation exists.

## Phase 3: User Story 1 — Durable Documentation Truth (P1)

- [x] T009 [US1] Correct the README project tree from 82 to the computed 223 skills.
- [x] T010 [US1] Correct the README description of `config/openclaw.json` to state that it contains model settings and pre-registered MCP server definitions.
- [x] T011 [US1] Extend `scripts/verify-inventory-counts.py` to protect both claims and fail if either becomes unlocatable.
- [x] T012 [US1] Add regression fixtures/assertions for the original stale count and original false config description.
- [x] T013 [US1] Verify `scripts/reconcile-mcp.py --surface docs` passes.

**Checkpoint**: Either original README defect now fails the existing docs surface.

## Phase 4: User Stories 2 and 3 — Unified Runner and Isolation (P1)

- [x] T014 [US2] Implement manifest loading, repository-relative path resolution, parity validation, `--list`, and `--matrix` in `scripts/run-contract-tests.py`.
- [x] T015 [US2] Implement sanitized preflight and aggregate result/exit-code mapping.
- [x] T016 [US3] Implement per-suite environment selection and content fingerprinting.
- [x] T017 [US3] Implement explicit `--prepare` with uv preference and standard-venv fallback, never shared pip.
- [x] T018 [US3] Implement requirements-file, explicit-package, and relative-local-package installation.
- [x] T019 [US3] Implement pinned artifact download with platform matching, temporary-file verification, SHA-256 refusal, and atomic placement.
- [x] T020 [US2] Implement harness execution, timeout handling, bounded output, human summaries, and JSON summaries.
- [x] T021 [US2] Implement live-variable and Docker executable/daemon/service capability probes.
- [x] T022 [US2] Implement `--strict-capabilities` without collapsing capability gaps into assertion failures.
- [x] T023 [US3] Adjust only hardcoded interpreter/venv harnesses (ANTA, Cisco PSIRT, Globalping, multivendor, Zabbix) to accept runner-provided overrides while preserving direct defaults.
- [x] T024 Run runner fixture tests and direct backwards-compatibility smoke tests.

**Checkpoint**: One command can honestly run any selected suite in its isolated environment.

## Phase 5: User Story 4 — Complete CI Matrix (P1)

- [x] T025 [US4] Add an enumeration job to `.github/workflows/mcp-reconciliation.yml` that exports `--matrix` output.
- [x] T026 [US4] Add a dependent matrix job that prepares and runs every suite entry in isolation.
- [x] T027 [US4] Remove the four hand-written per-suite invocations now represented by the generated matrix, retaining reconciliation declaration gates.
- [x] T028 [US4] Add a CI/manifest parity assertion so a new or removed suite cannot be omitted.
- [x] T029 [US4] Verify workflow syntax and generated matrix contains exactly 14 entries.

**Checkpoint**: All 14 contract harnesses are CI-visible; optional live/Docker gaps are explicit.

## Phase 6: User Story 5 — Contribution Workflow (P2)

- [x] T030 [P] [US5] Add the unified runner and SDD sequence to `docs/ADDING-AN-MCP.md`.
- [x] T031 [P] [US5] Add a concise contributor/testing section to README linking the detailed procedure.
- [x] T032 [US5] Validate every command in `quickstart.md` that does not require downloads or credentials.

## Phase 7: Polish and Verification

- [x] T033 Run all runner tests, spec artifact checks, documentation reconciliation, dependency reconciliation, and every locally runnable contract suite.
- [x] T034 Confirm no credential value appears in generated output or committed fixtures.
- [x] T035 Confirm no shared/system Python package was installed by implementation verification.
- [x] T036 Review `git diff --check`, branch status, and changed-file scope.
- [x] T037 Append the session result to `memory/2026-08-27.md`.
- [x] T038 Record the GAIT turn/log, or document the already-measured missing GAIT environment if still unavailable.

## Dependencies

```text
T001-T004
    ↓
T005-T008 (runner contracts + manifest)
    ├──→ T009-T013 (US1 docs)
    └──→ T014-T024 (US2/US3 runner)
                         ↓
                    T025-T029 (US4 CI)
                         ↓
                    T030-T032 (US5 docs)
                         ↓
                    T033-T038 (verification)
```

## Implementation Strategy

The minimum valuable increment is US1 plus manifest parity: stale architecture claims fail durably and the test inventory has one authority. The full requested outcome requires US2-US4 so all 14 suites are locally reproducible and CI-visible. Live systems remain explicitly outside the default path.

## Phase 5 — US6: test families with no entry point (T039-T048)

- [x] T039 Add `kind` to the manifest schema, defaulting absent entries to `shell`.
- [x] T040 Accept `paths` plus flag-only `args` for a pytest suite, and reject a shell `command` on one.
- [x] T041 Synthesize the pytest argv from the suite's own prepared interpreter.
- [x] T042 Enforce parity per kind, including directories that hold tests but no harness.
- [x] T043 Cover `kind` and `paths` in the environment fingerprint.
- [x] T044 Add the `ci` posture with a mandatory reason for any exclusion.
- [x] T045 Omit held-out suites from the generated matrix and print them from `--list`.
- [x] T046 Declare the runner's own contract tests as a suite and add `tests/runner/run-tests.sh`.
- [x] T047 Declare every discovered pytest family with its dependency set.
- [x] T048 Extend the runner contract tests to cover kinds, parity, exclusions, and fingerprints.

### Held out of the CI matrix

Declared, runnable by name, and not yet gated — each with its reason recorded in the manifest so the gap is visible rather than silent. Flipping one on is a one-line manifest change once it is green.

| Suite | Why it is not gated yet |
|---|---|
| `unit` | its chromadb dependency has never been installed by any workflow |
| `integration` | requires Playwright browser binaries this workflow does not install |
| `n2n` | no workflow has ever executed this suite |
| `auvik-mcp`, `halo-mcp` | dependency set still being established |
| `token-budget` | `tests/test_gcf_serializer.py` currently fails |
