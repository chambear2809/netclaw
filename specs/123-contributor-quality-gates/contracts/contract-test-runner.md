# Contract: Unified Contract-Test Runner

## Commands

```text
python3 scripts/run-contract-tests.py --list [--json]
python3 scripts/run-contract-tests.py --matrix
python3 scripts/run-contract-tests.py --suite <id|all> --prepare [--json]
python3 scripts/run-contract-tests.py --suite <id|all> [--prepare] [--strict-capabilities] [--json]
```

Paths resolve from the script location, not the caller's current directory.

## Human Output

Each suite produces one terminal summary line:

```text
PASS                 analysis       3.42s  offline contracts passed
FAIL                 reconcile      1.09s  harness exited 1
BLOCKED_DEPENDENCY   document       0.03s  missing imports: docx, openpyxl, pptx, fitz
```

Capability lines are additive and never replace the assertion result:

```text
NEEDS_LIVE_CREDENTIALS  catc        missing: CATC_TEST_HOST, CATC_TEST_USER, CATC_TEST_PASS
NEEDS_DOCKER            redfish     service unavailable: http://127.0.0.1:8000/redfish/v1
```

Docker details distinguish an absent executable, unreachable daemon, missing
digest-pinned image, and unavailable declared service. A suite may still pass
its offline assertions while one of those optional capabilities is unavailable.

## JSON Output

JSON follows `AggregateResult` in `data-model.md`. Credential values and the inherited environment are forbidden fields.

## Matrix Output

`--matrix` writes one compact JSON object suitable for GitHub Actions:

```json
{"include":[{"suite":"analysis","python":"3.12"}]}
```

The include list is sorted by suite id and contains exactly the declared/discovered suite set.

## Exit Codes

- `0`: all selected offline suites passed; optional capability gaps may be present.
- `1`: at least one selected harness executed and failed an assertion/contract.
- `2`: manifest invalid, suite unknown, command unavailable, preparation failed, required offline dependency missing, timeout, or `--strict-capabilities` found an optional capability gap.

If both failure and cannot-run conditions exist, exit 2 wins because the aggregate is incomplete. Individual suite statuses remain unchanged.

## Safety

- Default execution never enables opt-in live commands.
- `--prepare` may access package registries and declared artifact URLs; it says so in the quickstart.
- The runner never prints environment variable values.
- The runner never invokes device configuration or ticketing tools.

## Suite Kinds

- `kind` defaults to `shell`; a `pytest` suite declares `paths` instead of `command`.
- A `pytest` suite is invoked as `<its prepared interpreter> -m pytest <paths>`. The interpreter is the one the runner isolated for that suite, never the shared interpreter and never a pytest found on `PATH`.
- `--list` reports the kind for every suite.
- Parity is enforced per kind: `run-tests.sh` directories must be declared as shell suites, and directories holding tests without a harness must be declared as pytest suites. Adding either without a manifest entry fails before any test executes.

## CI Posture

- A suite may declare `ci: {include: false, reason: ...}`. The reason is mandatory; a blank or absent reason is a manifest error.
- `--matrix` omits held-out suites and is otherwise unchanged, so the manifest remains the single place a suite is added or withheld.
- `--list` prints held-out suites with their recorded reasons.
