#!/usr/bin/env bash
# Contract tests for the unified contract-suite runner (spec 123).
#
# Self-contained: bash + Python standard library only, so it runs in a bare CI
# container with nothing installed. It exercises the runner against fixtures in
# a temporary directory and never modifies the repository.
#
# This harness exists because the runner's own tests had no entry point. Every
# other suite was declared in the manifest and reachable by name; these were
# not, so the gate guarding every other suite was itself unguarded.

set -uo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
PY="${NETCLAW_PY:-python3}"

exec "$PY" "$REPO_ROOT/tests/runner/test_run_contract_tests.py"
