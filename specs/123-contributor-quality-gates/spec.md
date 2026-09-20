# Feature Specification: Contributor Quality Gates

**Feature Branch**: `feat/123-contributor-quality-gates`  
**Created**: 2026-08-27  
**Status**: Implemented  
**Input**: User request to fix stale README registration/count claims, protect those claims with the existing documentation gate, and provide one reproducible entry point that runs all 14 contract suites in CI while distinguishing failures from missing dependencies, live credentials, and Docker requirements.

## Problem Statement

NetClaw has strong per-feature contract tests and documentation reconciliation, but the contributor experience is fragmented:

- the README headline correctly reports 223 skills while its project tree still claims 82;
- the README says `config/openclaw.json` contains no MCP configuration even though `mcpServers` begins at line 33;
- the existing documentation check does not cover either claim;
- 14 contract suites expose 14 independent shell entry points with inconsistent dependency and skip behavior;
- only four suites are invoked by the main MCP workflow;
- a missing package can look like a test failure, while an absent live lab or Docker service can look like a successful but incomplete run.

The feature makes repository claims and contributor verification durable. It adds no network capability and performs no live operation by default.

## User Scenarios & Testing

### User Story 1 - Documentation Claims Stay True (Priority: P1)

As a contributor, I want repository documentation to describe the current skill inventory and MCP registration role accurately so I do not begin work from a false architecture model.

**Why this priority**: Incorrect architecture documentation sends every new contributor toward the wrong files and currently survives the existing gate.

**Independent Test**: Run the documentation reconciliation on a clean tree, then mutate either protected README claim in a fixture and confirm the check fails with the claim name, observed value, and expected value.

**Acceptance Scenarios**:

1. **Given** 223 directories containing `SKILL.md`, **When** the documentation check runs, **Then** every current-inventory claim, including the project tree, reports 223.
2. **Given** `config/openclaw.json` contains `mcpServers`, **When** the documentation check runs, **Then** the README describes it as the pre-registered MCP catalog/config template rather than claiming it contains no MCP configuration.
3. **Given** either protected phrase is removed or reworded beyond recognition, **When** the check runs, **Then** it fails as an unlocatable claim rather than silently dropping coverage.

---

### User Story 2 - One Honest Local Test Command (Priority: P1)

As a contributor, I want one command to discover and run the contract suites so I can understand repository health without learning 14 unrelated harnesses.

**Why this priority**: A green or red result is not useful unless it distinguishes code defects from an incomplete local environment.

**Independent Test**: Run the entry point in a fresh checkout without preparing dependencies and confirm it reports each suite using the documented status vocabulary and exits according to the status contract.

**Acceptance Scenarios**:

1. **Given** all offline prerequisites are available, **When** all suites run, **Then** each suite reports `PASS` or `FAIL` and the aggregate is deterministic.
2. **Given** an offline dependency is absent, **When** the suite is selected, **Then** it reports `BLOCKED_DEPENDENCY`, names only the missing package/path, and exits as cannot-run rather than test-failed.
3. **Given** a suite has optional live coverage and credentials are absent, **When** its offline contract passes, **Then** it reports `PASS` plus `NEEDS_LIVE_CREDENTIALS`; the absent credentials do not become a failure.
4. **Given** Docker or a required Docker-backed service is absent, **When** the relevant suite runs, **Then** it reports `NEEDS_DOCKER` separately from dependency and assertion results.

---

### User Story 3 - Reproducible Isolated Test Environments (Priority: P1)

As a contributor, I want the test command to prepare isolated environments from repository declarations so running one integration's tests does not mutate or break another integration's dependencies.

**Why this priority**: The repository deliberately carries incompatible dependency families, including FastMCP 2/3 and different cryptography versions. A shared test install is unsafe.

**Independent Test**: Prepare two suites with conflicting dependency families, confirm they receive different environments, rerun preparation without changes, and confirm the existing environment is reused from its content fingerprint.

**Acceptance Scenarios**:

1. **Given** a suite declares one or more requirements files or packages, **When** preparation runs, **Then** dependencies install only into that suite's declared environment.
2. **Given** requirements, Python version, and setup metadata are unchanged, **When** preparation runs again, **Then** the fingerprinted environment is reused.
3. **Given** a requirements file changes, **When** preparation runs, **Then** the stale environment is not treated as current.
4. **Given** environment creation or installation cannot complete, **When** the runner reports the result, **Then** it is `BLOCKED_DEPENDENCY` with a remediation command and not `FAIL`.

---

### User Story 4 - All Contract Suites Run in CI (Priority: P1)

As a maintainer, I want all 14 contract suites represented in a CI matrix generated from the same suite manifest used locally so new suites cannot be silently omitted.

**Why this priority**: The current workflow runs only four suites, so ten contract surfaces can regress without CI observing them.

**Independent Test**: Generate the CI matrix from the manifest, confirm it has exactly the 14 discovered `tests/*/run-tests.sh` suites, and run every matrix entry in an isolated job.

**Acceptance Scenarios**:

1. **Given** the committed suite manifest and test directories, **When** matrix generation runs, **Then** both sets match exactly and contain 14 entries.
2. **Given** a fifteenth suite directory is added without manifest metadata, **When** the gate runs, **Then** CI fails before executing an incomplete matrix.
3. **Given** a suite is removed while its manifest entry remains, **When** the gate runs, **Then** CI fails and names the stale entry.
4. **Given** live credentials are unavailable in pull-request CI, **When** offline contracts pass, **Then** the job succeeds while visibly reporting `NEEDS_LIVE_CREDENTIALS`.

---

### User Story 5 - A Followable Contribution Workflow (Priority: P2)

As a first-time contributor, I want a short documented sequence from specification through local verification so I can produce a reviewable change without reverse-engineering maintainer habits.

**Independent Test**: Follow the quickstart from a fresh checkout to list suites, prepare one environment, run one suite, run documentation reconciliation, and generate the same matrix CI consumes.

**Acceptance Scenarios**:

1. **Given** a contributor is changing an MCP integration, **When** they read the contribution procedure, **Then** it links the SDD artifact sequence and the unified test command.
2. **Given** preparation requires downloads, **When** documentation describes it, **Then** the network and disk effects are explicit before the command is run.

### User Story 6 - Test families with no entry point become runnable (Priority: P1)

As a contributor, I want the tests that live under `tests/` but have no harness to be reachable by name, so a suite nobody can run stops being a suite nobody knows is failing.

**Why this priority**: These directories hold the largest concentration of tests in the repository and no workflow or script has ever executed them, so their real state is unknown rather than known-good.

**Independent Test**: Run the single entry point against a pytest-backed family by name in a fresh checkout and confirm it prepares only that family's declared dependencies, reports a status from the same vocabulary as a shell suite, and never falls back to the shared interpreter.

**Acceptance Scenarios**:

1. **Given** a `tests/*` directory containing tests but no `run-tests.sh`, **When** the manifest does not declare it, **Then** parity fails and names the directory before any test executes.
2. **Given** a declared pytest suite, **When** it is selected, **Then** it runs under its own prepared interpreter with the same status vocabulary, capability reporting, and timeout handling as a shell suite.
3. **Given** a suite whose greenness has not been established, **When** it is declared, **Then** it stays runnable locally and out of the CI matrix, and the exclusion states why.

### Edge Cases

- The runner is invoked outside the repository root.
- A manifest is malformed, duplicated, or does not match discovered suite directories.
- `uv` is unavailable and the selected Python lacks `venv`/`ensurepip`.
- A requirements file uses a relative local package, as Zabbix does.
- A suite needs a production-shaped dedicated venv path because its contract asserts isolation.
- Docker exists but its daemon is unreachable.
- Docker is reachable but a required mock service is not running.
- One of several required live environment variables is missing.
- Credential variables are set; output must never print their values.
- A suite times out or is terminated before producing its own summary.
- Preparation succeeds but the suite command itself is missing or non-executable.

## Requirements

### Functional Requirements

- **FR-001**: The existing documentation reconciliation MUST protect the README project-tree skill count as a current inventory claim.
- **FR-002**: The documentation reconciliation MUST protect a canonical README statement describing `config/openclaw.json` as containing pre-registered MCP server configuration.
- **FR-003**: Protected claims that become unlocatable MUST fail rather than silently lose coverage.
- **FR-004**: Documentation failures MUST name the document, claim, observed text/value, and expected truth.
- **FR-005**: A machine-readable suite manifest MUST contain exactly one entry for every `tests/*/run-tests.sh` contract suite and no stale entries.
- **FR-006**: The initial manifest MUST contain exactly these 14 suites: analysis, anta, bgp-intel, catc, cisco-psirt, document, fortinet, globalping, k8s, multivendor, nsm, reconcile, redfish, and zabbix.
- **FR-007**: Each manifest entry MUST declare its command, Python requirement, offline dependency source, environment location policy, optional live credential names, and Docker/service requirement.
- **FR-008**: The unified runner MUST support listing suites, emitting a GitHub Actions matrix, preparing environments, running one suite, and running all suites.
- **FR-009**: The runner MUST use `PASS`, `FAIL`, `BLOCKED_DEPENDENCY`, `NEEDS_LIVE_CREDENTIALS`, `NEEDS_DOCKER`, and `ERROR` as distinct machine-readable statuses.
- **FR-010**: Assertion failures MUST produce exit code 1; malformed metadata or unavailable required offline dependencies MUST produce exit code 2; a complete offline pass with only optional live/Docker gaps MUST produce exit code 0.
- **FR-011**: A strict-capabilities option MUST allow callers to treat optional live/Docker gaps as incomplete without relabeling them as assertion failures.
- **FR-012**: Preparation MUST create or update only the selected suite's isolated environment and MUST NOT install into the shared/system interpreter.
- **FR-013**: Environment freshness MUST be based on a fingerprint of the effective Python version, requirements content, explicit packages, and preparation metadata.
- **FR-014**: The runner MUST prefer `uv` when present and MAY fall back to standard `venv`; inability to create an environment MUST be reported as `BLOCKED_DEPENDENCY`.
- **FR-015**: Relative requirements and dedicated server venvs MUST be supported without copying or rewriting upstream dependency files.
- **FR-016**: Default test execution MUST make no live API, device, controller, or measurement request.
- **FR-017**: The runner MUST inspect live credential presence by variable name only and MUST never emit credential values.
- **FR-018**: Docker classification MUST distinguish executable absent, daemon unreachable, and declared service unavailable in its detail while retaining the top-level `NEEDS_DOCKER` status.
- **FR-019**: GitHub Actions MUST derive its test matrix from the committed suite manifest and execute all entries in isolated jobs.
- **FR-020**: CI MUST prepare each suite's declared offline dependencies before running its contracts.
- **FR-021**: Runner contract tests MUST cover manifest parity, status/exit mapping, credential redaction, dependency blocking, and matrix generation.
- **FR-022**: Contributor documentation MUST explain the SDD sequence and the local/CI contract-test workflow.
- **FR-023**: The feature MUST not add, remove, or invoke a network-operation capability.
- **FR-024**: The existing per-suite `run-tests.sh` commands MUST remain directly usable for backwards compatibility.
- **FR-025**: A manifest entry MUST declare its `kind`, defaulting to `shell` for the existing harnesses, and `pytest` for a repository path or paths collected by pytest.
- **FR-026**: A `pytest` suite MUST declare one or more existing repository paths and MUST NOT declare a shell `command`; the runner MUST invoke pytest through the interpreter it isolated for that suite rather than through the shared interpreter or whatever pytest is on `PATH`.
- **FR-027**: Manifest/discovery parity MUST cover both kinds: every `tests/*` directory containing `run-tests.sh` MUST be declared as a shell suite, and every `tests/*` directory containing tests but no harness MUST be declared as a pytest suite.
- **FR-028**: An environment fingerprint MUST include the suite kind and its declared paths, so a suite cannot reuse an environment prepared for a different kind.
- **FR-029**: A suite MAY be held out of the CI matrix with `ci.include: false`, and that exclusion MUST carry a recorded reason; an exclusion without a reason MUST be rejected.
- **FR-030**: The CI matrix MUST be generated from the manifest with held-out suites omitted, so the manifest remains the only place a suite can be added or withheld.
- **FR-031**: `--list` MUST report each suite's kind and, for held-out suites, the recorded reason.
- **FR-032**: The runner's own contract tests MUST be reachable as a declared suite, so the gate that guards every other suite is itself gated.

### Key Entities

- **Contract Suite**: A named offline test surface with a command, dependency environment, optional live coverage, and optional Docker capability.
- **Suite Environment**: An isolated Python environment whose freshness is identified by a content fingerprint.
- **Capability Requirement**: Optional external evidence that cannot be manufactured in generic CI, such as credentials, a lab, Docker, or a local mock service.
- **Suite Result**: Assertion outcome, execution status, capability gaps, duration, command, and sanitized detail.
- **Protected Documentation Claim**: A repository statement tied to computable truth or a canonical structural fact.

## Success Criteria

### Measurable Outcomes

- **SC-001**: Mutating `82`/`223` in the protected project-tree claim makes the documentation surface fail.
- **SC-002**: Reintroducing the phrase that `config/openclaw.json` has no MCP config makes the documentation surface fail.
- **SC-003**: Manifest parity reports exactly 14 discovered and 14 declared suites on the completed tree.
- **SC-004**: One local command can prepare and run any of the 14 suites without installing into the shared interpreter.
- **SC-005**: GitHub Actions creates 14 contract-suite matrix jobs from runner output.
- **SC-006**: A simulated assertion failure exits 1, a simulated dependency block exits 2, and optional live/Docker gaps remain separately identifiable.
- **SC-007**: No default runner test contacts a live network system or consumes an external API budget.
- **SC-008**: Existing direct `bash tests/<suite>/run-tests.sh` entry points continue to work.
- **SC-009**: `python3 scripts/reconcile-mcp.py --surface docs` passes after the README correction and fails against fixtures containing either original stale claim.
- **SC-010**: The quickstart can be followed from outside the repository root without path errors.
- **SC-011**: `tests/*/run-tests.sh` directories and `tests/*` directories holding tests without a harness are each fully declared, and adding either kind without a manifest entry fails before any test executes.
- **SC-012**: A pytest suite invoked with an isolated environment runs under that environment's interpreter, and changing its kind or paths invalidates the prepared environment.
- **SC-013**: Every suite held out of the CI matrix carries a reason, and the generated matrix omits exactly those suites.
- **SC-014**: The runner's own contract tests run through the same single entry point as every other suite.

## Assumptions

- Pull-request CI has package-registry access but no production credentials.
- Python 3.12 is the default contract-test interpreter unless a suite declares another supported version.
- Live verification remains opt-in and is never fabricated by mocks unless the existing suite explicitly defines a mock service.
- Docker-backed assertions may be skipped on hosts without Docker, but the gap must remain visible in the aggregate result.
- Exact dependency versions remain governed by each server's existing bounded requirements; this feature standardizes isolation and recreation rather than introducing 14 new lockfiles.

## Out of Scope

- Running live network, cloud, controller, or SaaS tests in pull-request CI.
- Rewriting the 14 existing contract suites into one test framework.
- Adding every unrelated pytest directory in the repository to this matrix.
- Fixing pre-existing contract failures unrelated to the runner, including the Zoom `websockets` upper-bound finding.
- Installing or configuring a full OpenClaw/NetClaw runtime.
