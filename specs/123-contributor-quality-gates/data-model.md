# Data Model: Contributor Quality Gates

## ContractSuiteManifest

- `schema_version`: integer, currently `1`
- `default_python`: major/minor string
- `suites`: map keyed by stable suite id

Validation:

- suite ids are unique and sorted when emitted;
- declared ids equal discovered `tests/*/run-tests.sh` ids;
- all repository-relative paths remain inside the repository;
- credential metadata contains names only.

## ContractSuite

- `id`: manifest key
- `command`: non-empty argv list
- `python`: optional override of the manifest default
- `environment.path`: repository-relative venv location
- `environment.requirements`: zero or more repository-relative files
- `environment.packages`: zero or more explicit package constraints
- `environment.prepend_path`: whether the suite command runs with the venv first on `PATH`
- `required_imports`: import names used for preflight
- `artifacts`: zero or more `ArtifactDependency` objects
- `live`: optional `LiveRequirement`
- `docker`: optional `DockerRequirement`
- `timeout_seconds`: positive integer

## ArtifactDependency

- `platform`: normalized OS/architecture selector
- `url`: immutable or versioned download URL
- `destination`: repository-relative ignored path
- `sha256`: expected digest
- `executable`: boolean

The artifact is installed only by explicit preparation. A checksum mismatch is an error and the destination is not replaced with unverified bytes.

## LiveRequirement

- `mode`: `all` or `any`
- `env`: environment variable names
- `command`: optional alternate opt-in live command
- `description`: non-secret explanation

## DockerRequirement

- `level`: `daemon` or `service`
- `service_url`: optional loopback health URL
- `images`: optional list of digest-pinned images required by Docker-backed assertions
- `description`: reason Docker is needed

## EnvironmentFingerprint

SHA-256 over canonical JSON containing:

- schema version;
- suite id;
- Python major/minor and executable implementation;
- requirements paths and file SHA-256 values;
- explicit package strings;
- environment path/policy;
- artifact URL/destination/digest metadata.

The fingerprint is stored as `.netclaw-contract-env.json` inside the environment with creation time and Python version. No credential state is included.

## SuiteResult

- `suite`: suite id
- `status`: `PASS`, `FAIL`, `BLOCKED_DEPENDENCY`, or `ERROR`
- `exit_code`: underlying harness code when executed
- `duration_seconds`: elapsed wall time
- `command`: sanitized argv
- `environment`: path and fingerprint, without environment values
- `capabilities`: list of `CapabilityResult`
- `detail`: bounded human-readable diagnostic

## CapabilityResult

- `status`: `NEEDS_LIVE_CREDENTIALS`, `NEEDS_DOCKER`, or `AVAILABLE`
- `kind`: `live`, `docker-daemon`, or `docker-service`
- `names`: variable names only, where applicable
- `detail`: non-secret explanation

## AggregateResult

- `schema_version`
- `generated_at`
- `results`: ordered suite results
- `counts`: count per status and capability gap
- `exit_code`: 0, 1, or 2 under the CLI contract

## SuiteKind

A suite's `kind` decides how it is executed and what parity it participates in.

| `kind` | Declares | Executed as | Participates in |
|---|---|---|---|
| `shell` (default) | `command` | that argv, unchanged | `tests/*` directories holding `run-tests.sh` |
| `pytest` | `paths` (one or more repository paths) and optional flag-only `args` | `<suite interpreter> -m pytest <paths> <args>` | `tests/*` directories holding tests but no harness |

Existing entries carry no `kind` and are therefore shell suites; the field is additive.

## CIPosture

- `ci`: optional object.
  - `include`: boolean, default `true`.
  - `reason`: required when `include` is `false`, and rejected when it is blank.

A suite with `include: false` stays runnable by name but is omitted from the generated matrix. The reason is the recorded justification; there is no way to express the exclusion without one.
