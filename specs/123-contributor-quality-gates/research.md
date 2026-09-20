# Research: Contributor Quality Gates

**Date**: 2026-08-27  
**Scope**: Documentation truth enforcement and the 14 existing `tests/*/run-tests.sh` contract suites.

## R1 — Extend the Existing Documentation Surface

**Decision**: Extend `scripts/verify-inventory-counts.py`; do not create a second documentation checker.

**Why**: `scripts/reconcile-mcp.py --surface docs` already delegates to this script, CI already gates that surface, and the script already treats an unlocatable protected claim as failure. The gap is coverage, not orchestration.

**Measured issue**:

- README headline and section heading report 223 skills.
- README project tree still says `82 skill definitions`.
- README `What Goes Where` says `config/openclaw.json` has no MCP config.
- Actual `config/openclaw.json` contains `mcpServers` from line 33.

**Rejected**: Broad numeric scanning. It confuses subsection counts such as `Microsoft 365 Skills (3)` with current inventory claims.

## R2 — One Manifest Is the Source for Local and CI Discovery

**Decision**: Add `tests/contract-suites.json` and make both the runner and CI matrix consume it.

**Why**: A hardcoded YAML matrix would create a second list and repeat the omission problem. Runtime discovery alone cannot express dependencies, live credentials, Docker posture, or dedicated environment paths.

**Invariant**: The manifest set must equal the set of immediate `tests/*/run-tests.sh` paths. A mismatch is `ERROR`/exit 2 before any suite runs.

## R3 — Preserve the Existing Harnesses

**Decision**: The runner invokes each existing shell harness rather than rewriting their assertions.

**Why**: The suites encode domain-specific distinctions and direct exit-code handling. Rewriting them would expand risk and make this feature responsible for hundreds of unrelated assertions.

**Compatibility**: Direct `bash tests/<suite>/run-tests.sh` remains supported. Small changes may allow `NETCLAW_PY` or an environment path override, but the default behavior stays intact.

## R4 — Status Is Two-Dimensional

**Decision**: Separate the offline assertion result from optional capability gaps.

| Condition | Primary status | Exit |
|---|---|---:|
| Assertions passed, no required offline gap | `PASS` | 0 |
| Assertion or contract failed | `FAIL` | 1 |
| Required offline package/path/interpreter unavailable | `BLOCKED_DEPENDENCY` | 2 |
| Manifest/runner/command malformed | `ERROR` | 2 |
| Optional live variables absent | capability `NEEDS_LIVE_CREDENTIALS` | unchanged |
| Docker/daemon/service absent | capability `NEEDS_DOCKER` | unchanged |

`--strict-capabilities` may return 2 when optional evidence is unavailable, but it must not rename the gap to `FAIL`.

**Why**: A single scalar status cannot honestly say both “offline contracts passed” and “the live claim remains unverified.”

## R5 — Isolated Environments, Not a Shared CI Install

**Decision**: Build one environment per suite. Default environments live under `.contract-test-envs/<suite>`; suites whose contracts require the production-shaped location may declare `mcp-servers/<name>/.venv`.

**Why**:

- Zabbix requires FastMCP 3.x while several servers pin below 3.
- ANTA and multivendor dependencies can move `cryptography` independently of the federation stack.
- Several suites import `mcp.server.fastmcp`, removed in MCP 2.x.

The runner prefers `uv venv`/`uv pip`; standard `venv`/pip is a fallback when ensurepip exists. It never invokes bare system pip.

**Freshness**: Hash Python major/minor, requirements file bytes, explicit package specs, environment path policy, and manifest schema version. Store the hash in the environment. A mismatch triggers recreation/preparation.

**Rejected**: One root development venv. It cannot satisfy the deliberate FastMCP and cryptography isolation contracts.

## R6 — Dependency Metadata by Suite

| Suite | Offline dependency source | Dedicated environment | Optional external evidence |
|---|---|---|---|
| analysis | `analysis-mcp/requirements.txt` | no | DuckDB package is required for full offline coverage |
| anta | `anta-mcp/requirements.txt` | yes | `ANTA_TEST_HOST` for live device validation |
| bgp-intel | `bgp-intel-mcp/requirements.txt` | no | none; public-source calls are intentionally excluded |
| catc | `catc-mcp/requirements.txt` | no | Catalyst Center lab credentials |
| cisco-psirt | `cisco-psirt-mcp/requirements.txt` | no | separate opt-in live API script |
| document | `document-mcp/requirements.txt` | no | none |
| fortinet | `fortinet-mcp/requirements.txt` | no | live appliance checks are outside default harness |
| globalping | stdlib only | no | separate opt-in token/measurement script |
| k8s | MCP client plus pinned Go binary | no | kubeconfigs for live narrowing reproduction |
| multivendor | `multivendor-cli-mcp/requirements.txt` | yes | separate device lab script |
| nsm | `nsm-mcp/requirements.txt` | no | Docker daemon/images for PCAP analysis |
| reconcile | stdlib only | no | none |
| redfish | `redfish-mcp/requirements.txt` | no | Docker-backed DMTF mock service on localhost |
| zabbix | `zabbix-mcp/requirements.txt` | yes | Zabbix URL/token for live traps |

## R7 — CI Uses a Generated Matrix

**Decision**: Add an enumeration job whose output is `run-contract-tests.py --matrix`; a dependent matrix job prepares and runs each suite.

**Why**: This keeps the manifest as the only suite list and gives each dependency family a clean filesystem/process boundary.

**CI default**: Offline only. Credential variables are neither required nor read. Docker-dependent details are reported honestly; pull-request success depends on offline assertions, not unavailable production evidence.

## R8 — K8s Binary Is an Artifact Dependency

**Decision**: Model the pinned Kubernetes Go binary as an artifact dependency with platform, URL, destination, and SHA-256 metadata. Preparation downloads only on a supported platform and refuses a checksum mismatch.

**Why**: The existing static harness passes while skipping its manifest assertions when the 75 MB binary is absent. CI needs to know that this is an unverified dependency gap rather than silently calling the suite complete.

**Limitation**: The existing checksum covers Linux amd64 only. Other platforms report `BLOCKED_DEPENDENCY` for the artifact-dependent portion unless a verified artifact is added later.

## R9 — Docker Is Capability, Not Python Dependency

**Decision**: Probe executable, daemon, and optional declared service separately. Report all under `NEEDS_DOCKER` with a reason.

**Why**: `docker` on PATH does not mean the daemon is reachable, and a reachable daemon does not mean Redfish's mock is listening on port 8000.

## R10 — Credential Hygiene

**Decision**: Manifest contains environment variable names only. Reports emit missing/present names and counts, never values.

**Why**: Matrix logs and JSON artifacts are broadly visible; a diagnostic runner must not become a secret exfiltration path.

## R11 — The Pre-Existing Dependency Failure Was Fixed Independently

When this feature was written, `reconcile-mcp.py` failed the dependency surface because
`zoom-rtms-mcp` declared `websockets>=12.0` without an upper bound. Spec 123 did not hide or
reclassify it: the `reconcile` matrix entry was expected to stay red until that unrelated issue was
fixed on its own.

That fix landed on `main` independently (PR #259), so the dependency surface passes and the
`reconcile` matrix entry is expected green with no exception carved out for it. This section is kept
as the record of why the feature deliberately shipped no workaround.

