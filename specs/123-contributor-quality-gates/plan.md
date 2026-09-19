# Implementation Plan: Contributor Quality Gates

**Branch**: `feat/123-contributor-quality-gates` | **Date**: 2026-08-27 | **Spec**: [spec.md](spec.md)  
**Input**: Feature specification from `/specs/123-contributor-quality-gates/spec.md`

## Summary

Correct two stale README architecture claims and extend the existing docs reconciliation to protect them. Add a standard-library Python runner driven by a machine-readable 14-suite manifest; it prepares isolated per-suite environments, reports assertion and capability states separately, and generates the GitHub Actions matrix used to run every suite.

## Technical Context

**Language/Version**: Python 3.10+ runner; Bash compatibility wrappers; YAML CI  
**Primary Dependencies**: Python standard library for orchestration; existing suite requirements for isolated environments  
**Storage**: JSON manifest and ignored virtual environments  
**Testing**: Existing shell contract suites plus runner unit/contract fixtures  
**Target Platform**: Linux CI; macOS/Linux local contributor environments  
**Project Type**: Repository tooling and CI  
**Performance Goals**: Manifest validation under 1 second; environment reuse when fingerprints match  
**Constraints**: No default live calls; no shared pip installs; secrets by name only; preserve direct suite entry points  
**Scale/Scope**: 14 suites, 11 Python dependency sets, one pinned binary artifact, three dedicated environment policies

## Constitution Check

- **I Safety-First**: PASS. No device operation is added; default execution is offline.
- **II Read-Before-Write**: PASS. Repository state and suite metadata are validated before environment creation.
- **III ITSM-Gated Changes**: N/A. No infrastructure configuration is performed.
- **IV Immutable Audit Trail**: DEGRADED in this development environment. GAIT is mandatory but unavailable because its dedicated venv is absent; this must be recorded, not concealed.
- **V MCP-Native Integration**: N/A. No new integration/tool surface is added.
- **VII Skill Modularity**: PASS. No skill behavior changes.
- **XI Artifact Coherence**: PASS with scoped N/A items. README, docs gate, tests, CI, and contributor procedure are affected; HUD/SOUL/env/config changes are not required because no capability is added.
- **XII Documentation-as-Code**: PASS. The corrected claims become executable checks.
- **XIII Credential Safety**: PASS. Only variable names enter metadata/output.
- **XV Backwards Compatibility**: PASS. Existing `run-tests.sh` entry points remain callable.
- **XVI Spec-Driven Development**: PASS. Spec, research, data model, contract, plan, quickstart, and tasks precede implementation.

## Project Structure

### Documentation

```text
specs/123-contributor-quality-gates/
├── spec.md
├── research.md
├── data-model.md
├── plan.md
├── quickstart.md
├── tasks.md
├── checklists/requirements.md
└── contracts/contract-test-runner.md
```

### Source Changes

```text
README.md
docs/ADDING-AN-MCP.md
scripts/
├── verify-inventory-counts.py
└── run-contract-tests.py
tests/
├── contract-suites.json
├── runner/
│   └── test_run_contract_tests.py
└── */run-tests.sh
.github/workflows/
└── mcp-reconciliation.yml
```

**Structure Decision**: Keep quality tooling under `scripts/`, metadata/tests under `tests/`, and extend the established MCP reconciliation workflow rather than adding a parallel CI authority.

## Implementation Phases

1. Add failing documentation and runner contract tests.
2. Correct README claims and extend the docs gate.
3. Add/validate the suite manifest and status model.
4. Implement isolated preparation, fingerprinting, and suite execution.
5. Adapt only the harnesses that hardcode a production interpreter/venv.
6. Generate and consume the CI matrix.
7. Document the contributor workflow and validate quickstart commands.

## Complexity Tracking

| Complexity | Why Needed | Simpler Alternative Rejected Because |
|---|---|---|
| Per-suite environments | Existing dependency families intentionally conflict | One shared venv can break FastMCP and cryptography consumers |
| Machine-readable manifest | CI and local runner need dependency/capability metadata | Directory discovery alone cannot describe requirements or live/Docker posture |
| Two-dimensional results | Offline assertions and external evidence are independent | A single pass/fail value turns skipped live coverage into false confidence or false failure |

