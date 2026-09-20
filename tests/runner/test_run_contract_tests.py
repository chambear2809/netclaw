#!/usr/bin/env python3
"""Contract tests for the unified contract-suite runner (spec 123)."""

from __future__ import annotations

import contextlib
import hashlib
import importlib.util
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile

REPO = Path(__file__).resolve().parents[2]
RUNNER_PATH = REPO / "scripts" / "run-contract-tests.py"


def load_runner():
    spec = importlib.util.spec_from_file_location("netclaw_contract_runner", RUNNER_PATH)
    if spec is None or spec.loader is None:
        raise AssertionError(f"cannot load {RUNNER_PATH}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def fake_repo(with_pytest: bool = False) -> tuple[tempfile.TemporaryDirectory, Path, Path]:
    temp = tempfile.TemporaryDirectory()
    root = Path(temp.name)
    (root / "tests" / "alpha").mkdir(parents=True)
    (root / "tests" / "beta").mkdir(parents=True)
    (root / "tests" / "alpha" / "run-tests.sh").write_text("#!/bin/sh\nexit 0\n")
    (root / "tests" / "beta" / "run-tests.sh").write_text("#!/bin/sh\nexit 1\n")
    suites = {
        "alpha": {
            "command": ["bash", "tests/alpha/run-tests.sh"],
            "environment": {
                "path": None,
                "requirements": [],
                "packages": [],
                "required_imports": [],
                "prepend_path": False,
            },
            "live": {
                "mode": "all",
                "env": ["ALPHA_TOKEN"],
                "description": "fake live source",
            },
            "timeout_seconds": 5,
        },
        "beta": {
            "command": ["bash", "tests/beta/run-tests.sh"],
            "environment": {
                "path": ".contract-test-envs/beta",
                "requirements": [],
                "packages": ["example-package==1"],
                "required_imports": ["module_that_cannot_exist_for_netclaw_test"],
                "prepend_path": True,
            },
            "docker": {"level": "daemon", "description": "fake daemon"},
            "timeout_seconds": 5,
        },
    }
    if with_pytest:
        (root / "tests" / "gamma").mkdir(parents=True)
        (root / "tests" / "gamma" / "test_gamma.py").write_text("def test_ok():\n    assert True\n")
        suites["gamma"] = {
            "kind": "pytest",
            "paths": ["tests/gamma"],
            "environment": {
                "path": ".contract-test-envs/gamma",
                "requirements": [],
                "packages": [],
                "required_imports": [],
                "prepend_path": True,
            },
            "timeout_seconds": 5,
        }
    # Declare the interpreter that is already running this test. Environment
    # preparation is under test, not Python-version resolution: pinning a
    # different major here would make the test depend on the host having uv or
    # that exact interpreter, which is how it would pass in CI and fail on a
    # developer's laptop.
    manifest = {
        "schema_version": 1,
        "default_python": f"{sys.version_info.major}.{sys.version_info.minor}",
        "suites": suites,
    }
    manifest_path = root / "tests" / "contract-suites.json"
    manifest_path.write_text(json.dumps(manifest))
    return temp, root, manifest_path


def check(label: str, condition: bool, detail: str = "") -> int:
    print(("  PASS " if condition else "  FAIL ") + label + (f" -- {detail}" if detail else ""))
    return 0 if condition else 1


def test_real_manifest_declares_every_discovered_suite(runner) -> int:
    manifest = runner.load_manifest(REPO / "tests" / "contract-suites.json", REPO)
    suites = manifest["suites"]
    shell = {sid for sid, config in suites.items() if runner.suite_kind(config) == "shell"}
    declared_pytest = {
        sid for sid, config in suites.items() if runner.suite_kind(config) == "pytest"
    }
    dir_backed_pytest = {sid for sid in declared_pytest if (REPO / "tests" / sid).is_dir()}
    ok = (
        shell == runner.discover_suites(REPO)
        and dir_backed_pytest == runner.discover_pytest_suites(REPO)
        and bool(shell)
        and bool(dir_backed_pytest)
    )
    return check("real manifest declares every discovered shell and pytest suite", ok,
                 f"shell={sorted(shell)} pytest={sorted(dir_backed_pytest)} "
                 f"discovered_pytest={sorted(runner.discover_pytest_suites(REPO))}")


def test_parity_rejects_an_undeclared_suite(runner) -> int:
    temp, root, path = fake_repo()
    try:
        (root / "tests" / "gamma").mkdir()
        (root / "tests" / "gamma" / "run-tests.sh").write_text("#!/bin/sh\nexit 0\n")
        try:
            runner.load_manifest(path, root)
        except runner.ManifestError as exc:
            return check("undeclared suite is rejected", "gamma" in str(exc), str(exc))
        return check("undeclared suite is rejected", False, "manifest unexpectedly accepted")
    finally:
        temp.cleanup()


def test_matrix_is_deterministic(runner) -> int:
    temp, root, path = fake_repo()
    try:
        manifest = runner.load_manifest(path, root)
        first = runner.build_matrix(manifest)
        second = runner.build_matrix(manifest)
        return check("matrix is sorted and deterministic",
                     first == second and [x["suite"] for x in first["include"]] == ["alpha", "beta"],
                     repr(first))
    finally:
        temp.cleanup()


def test_exit_contract(runner) -> int:
    cases = [
        ([{"status": "PASS", "capabilities": []}], False, 0),
        ([{"status": "FAIL", "capabilities": []}], False, 1),
        ([{"status": "BLOCKED_DEPENDENCY", "capabilities": []}], False, 2),
        ([{"status": "ERROR", "capabilities": []}], False, 2),
        ([{"status": "PASS", "capabilities": [{"status": "NEEDS_DOCKER"}]}], False, 0),
        ([{"status": "PASS", "capabilities": [{"status": "NEEDS_LIVE_CREDENTIALS"}]}], True, 2),
        ([{"status": "FAIL", "capabilities": []},
          {"status": "BLOCKED_DEPENDENCY", "capabilities": []}], False, 2),
    ]
    bad = [(results, strict, expected, runner.aggregate_exit(results, strict))
           for results, strict, expected in cases
           if runner.aggregate_exit(results, strict) != expected]
    return check("aggregate exit contract distinguishes fail/block/capability gaps", not bad, repr(bad))


def test_preflight_distinguishes_dependency_live_and_docker(runner) -> int:
    temp, root, path = fake_repo()
    try:
        manifest = runner.load_manifest(path, root)
        old = os.environ.pop("ALPHA_TOKEN", None)
        try:
            alpha = runner.preflight_suite("alpha", manifest["suites"]["alpha"], root)
            beta = runner.preflight_suite("beta", manifest["suites"]["beta"], root)
        finally:
            if old is not None:
                os.environ["ALPHA_TOKEN"] = old
        alpha_caps = {x["status"] for x in alpha["capabilities"]}
        beta_caps = {x["status"] for x in beta["capabilities"]}
        ok = (alpha["status"] == "PASS" and "NEEDS_LIVE_CREDENTIALS" in alpha_caps
              and beta["status"] == "BLOCKED_DEPENDENCY"
              and "NEEDS_DOCKER" in beta_caps)
        return check("preflight keeps dependency/live/docker states separate", ok,
                     f"alpha={alpha} beta={beta}")
    finally:
        temp.cleanup()


def test_output_never_contains_credential_value(runner) -> int:
    temp, root, path = fake_repo()
    secret = "super-secret-value-must-not-appear"
    try:
        manifest = runner.load_manifest(path, root)
        os.environ["ALPHA_TOKEN"] = secret
        try:
            result = runner.preflight_suite("alpha", manifest["suites"]["alpha"], root)
            rendered = json.dumps(result) + runner.format_result(result)
            rendered += runner._redact("https://user:password@example.invalid/simple", manifest["suites"]["alpha"])
        finally:
            os.environ.pop("ALPHA_TOKEN", None)
        return check("credential values are absent from structured and human output",
                     secret not in rendered and "password" not in rendered
                     and "ALPHA_TOKEN" in rendered, rendered)
    finally:
        temp.cleanup()


def test_default_run_strips_live_credentials(runner) -> int:
    temp, root, path = fake_repo()
    secret = "available-but-must-remain-opt-in"
    try:
        manifest = runner.load_manifest(path, root)
        alpha = manifest["suites"]["alpha"]
        alpha["command"] = [
            sys.executable,
            "-c",
            "import os,sys; sys.exit(1 if os.environ.get('ALPHA_TOKEN') else 0)",
        ]
        os.environ["ALPHA_TOKEN"] = secret
        try:
            result = runner.run_suite("alpha", alpha, manifest, root)
        finally:
            os.environ.pop("ALPHA_TOKEN", None)
        return check("default execution strips live credentials from the harness",
                     result["status"] == "PASS" and result["exit_code"] == 0,
                     repr(result))
    finally:
        temp.cleanup()


def test_prepare_is_isolated_and_fingerprinted(runner) -> int:
    temp, root, path = fake_repo()
    try:
        manifest = runner.load_manifest(path, root)
        beta = manifest["suites"]["beta"]
        beta["environment"]["packages"] = []
        beta["environment"]["required_imports"] = []
        runner.prepare_suite("beta", beta, manifest, root)
        interpreter = root / ".contract-test-envs" / "beta" / "bin" / "python"
        marker = root / ".contract-test-envs" / "beta" / runner.MARKER_NAME
        prepared = runner.preflight_suite("beta", beta, root, manifest)

        beta["environment"]["packages"] = ["changed-package==1"]
        stale = runner.preflight_suite("beta", beta, root, manifest)
        ok = (interpreter.is_file() and marker.is_file()
              and prepared["status"] == "PASS"
              and stale["status"] == "BLOCKED_DEPENDENCY"
              and "stale" in stale["detail"])
        return check("preparation is isolated, fingerprinted, and detects stale metadata", ok,
                     f"prepared={prepared} stale={stale}")
    finally:
        temp.cleanup()


def test_artifact_checksum_mismatch_is_refused(runner) -> int:
    temp, root, _ = fake_repo()
    payload = b"downloaded-but-untrusted"
    expected = hashlib.sha256(b"expected-content").hexdigest()
    config = {
        "command": ["bash", "tests/alpha/run-tests.sh"],
        "environment": {"path": None, "requirements": [], "packages": [],
                        "required_imports": [], "prepend_path": False},
        "artifacts": [{
            "platform": runner._platform_id(),
            "url": "https://example.invalid/artifact",
            "destination": "artifacts/probe",
            "sha256": expected,
            "executable": True,
        }],
        "timeout_seconds": 5,
    }
    manifest = {"schema_version": 1, "default_python": "3.12", "suites": {"alpha": config}}
    original = runner.urlrequest.urlopen
    runner.urlrequest.urlopen = lambda *_args, **_kwargs: io.BytesIO(payload)
    try:
        try:
            runner.prepare_suite("alpha", config, manifest, root)
        except RuntimeError as exc:
            destination = root / "artifacts" / "probe"
            placement_refused = "SHA-256 mismatch" in str(exc) and not destination.exists()
            destination.parent.mkdir(parents=True, exist_ok=True)
            destination.write_bytes(payload)
            preflight = runner.preflight_suite("alpha", config, root)
            return check("checksum mismatch is refused during preparation and preflight",
                         placement_refused and preflight["status"] == "BLOCKED_DEPENDENCY"
                         and "checksum mismatch" in preflight["detail"],
                         f"prepare={exc} preflight={preflight}")
        return check("checksum mismatch is refused before artifact placement", False,
                     "untrusted artifact was accepted")
    finally:
        runner.urlrequest.urlopen = original
        temp.cleanup()


def test_missing_pinned_image_is_a_docker_gap(runner) -> int:
    original_which = runner.shutil.which
    original_run = runner.subprocess.run

    def fake_which(name):
        return "/usr/bin/docker" if name == "docker" else original_which(name)

    def fake_run(argv, **_kwargs):
        return subprocess.CompletedProcess(argv, 0 if argv[1] == "info" else 1, "", "")

    runner.shutil.which = fake_which
    runner.subprocess.run = fake_run
    try:
        result = runner._docker_capability({
            "docker": {
                "level": "daemon",
                "images": ["example/image@sha256:" + "a" * 64],
                "description": "fake pinned image",
            }
        })
        return check("missing pinned image is NEEDS_DOCKER, not an assertion failure",
                     result["status"] == "NEEDS_DOCKER"
                     and result["kind"] == "docker-image"
                     and "example/image" in result["detail"], repr(result))
    finally:
        runner.shutil.which = original_which
        runner.subprocess.run = original_run


def test_pytest_suite_runs_under_its_own_interpreter(runner) -> int:
    temp, root, path = fake_repo(with_pytest=True)
    try:
        manifest = runner.load_manifest(path, root)
        gamma = manifest["suites"]["gamma"]
        command = runner.suite_command("gamma", gamma, root)
        expected = str(runner._venv_python((root / ".contract-test-envs" / "gamma").resolve()))
        ok = command[0] == expected and command[1:3] == ["-m", "pytest"] and command[3:] == ["tests/gamma"]
        return check("pytest suite runs under its own isolated interpreter", ok, repr(command))
    finally:
        temp.cleanup()


def test_pytest_suite_requires_existing_paths(runner) -> int:
    temp, root, path = fake_repo(with_pytest=True)
    try:
        manifest = json.loads(path.read_text())
        manifest["suites"]["gamma"]["paths"] = ["tests/does-not-exist"]
        path.write_text(json.dumps(manifest))
        try:
            runner.load_manifest(path, root)
        except runner.ManifestError as exc:
            return check("pytest suite with a missing path is rejected", "paths" in str(exc), str(exc))
        return check("pytest suite with a missing path is rejected", False, "manifest unexpectedly accepted")
    finally:
        temp.cleanup()


def test_pytest_suite_rejects_a_shell_command(runner) -> int:
    temp, root, path = fake_repo(with_pytest=True)
    try:
        manifest = json.loads(path.read_text())
        manifest["suites"]["gamma"]["command"] = ["bash", "tests/gamma/run-tests.sh"]
        path.write_text(json.dumps(manifest))
        try:
            runner.load_manifest(path, root)
        except runner.ManifestError as exc:
            return check("pytest suite carrying a shell command is rejected",
                         "command" in str(exc), str(exc))
        return check("pytest suite carrying a shell command is rejected", False,
                     "manifest unexpectedly accepted")
    finally:
        temp.cleanup()


def test_undeclared_pytest_directory_is_rejected(runner) -> int:
    temp, root, path = fake_repo()
    try:
        (root / "tests" / "delta").mkdir()
        (root / "tests" / "delta" / "test_delta.py").write_text("def test_ok():\n    assert True\n")
        try:
            runner.load_manifest(path, root)
        except runner.ManifestError as exc:
            return check("tests/* directory holding tests but no entry is rejected",
                         "delta" in str(exc), str(exc))
        return check("tests/* directory holding tests but no entry is rejected", False,
                     "manifest unexpectedly accepted")
    finally:
        temp.cleanup()


def test_ci_exclusion_requires_a_recorded_reason(runner) -> int:
    temp, root, path = fake_repo()
    try:
        manifest = json.loads(path.read_text())
        manifest["suites"]["alpha"]["ci"] = {"include": False}
        path.write_text(json.dumps(manifest))
        try:
            runner.load_manifest(path, root)
        except runner.ManifestError as exc:
            return check("holding a suite out of CI without a reason is rejected",
                         "reason" in str(exc), str(exc))
        return check("holding a suite out of CI without a reason is rejected", False,
                     "manifest unexpectedly accepted")
    finally:
        temp.cleanup()


def test_matrix_omits_held_out_suites(runner) -> int:
    temp, root, path = fake_repo(with_pytest=True)
    try:
        manifest = json.loads(path.read_text())
        manifest["suites"]["gamma"]["ci"] = {"include": False, "reason": "fake held-out suite"}
        path.write_text(json.dumps(manifest))
        loaded = runner.load_manifest(path, root)
        included = {item["suite"] for item in runner.build_matrix(loaded)["include"]}
        held = runner.ci_held_out(loaded)
        ok = ("gamma" not in included and included == {"alpha", "beta"}
              and [item["suite"] for item in held] == ["gamma"]
              and held[0]["reason"] == "fake held-out suite")
        return check("held-out suite leaves the matrix but keeps its reason", ok,
                     f"included={sorted(included)} held={held}")
    finally:
        temp.cleanup()


def test_fingerprint_separates_kinds_and_paths(runner) -> int:
    temp, root, path = fake_repo(with_pytest=True)
    try:
        manifest = runner.load_manifest(path, root)
        gamma = manifest["suites"]["gamma"]
        before, _ = runner._fingerprint("gamma", gamma, manifest, root)
        gamma["paths"] = ["tests/gamma", "tests/alpha"]
        after, _ = runner._fingerprint("gamma", gamma, manifest, root)
        return check("fingerprint covers kind and paths", before != after,
                     f"before={before} after={after}")
    finally:
        temp.cleanup()


def main() -> int:
    runner = load_runner()
    tests = [
        test_real_manifest_declares_every_discovered_suite,
        test_parity_rejects_an_undeclared_suite,
        test_matrix_is_deterministic,
        test_exit_contract,
        test_preflight_distinguishes_dependency_live_and_docker,
        test_output_never_contains_credential_value,
        test_default_run_strips_live_credentials,
        test_prepare_is_isolated_and_fingerprinted,
        test_artifact_checksum_mismatch_is_refused,
        test_missing_pinned_image_is_a_docker_gap,
        test_pytest_suite_runs_under_its_own_interpreter,
        test_pytest_suite_requires_existing_paths,
        test_pytest_suite_rejects_a_shell_command,
        test_undeclared_pytest_directory_is_rejected,
        test_ci_exclusion_requires_a_recorded_reason,
        test_matrix_omits_held_out_suites,
        test_fingerprint_separates_kinds_and_paths,
    ]
    failures = 0
    for test in tests:
        try:
            failures += test(runner)
        except Exception as exc:
            print(f"  FAIL {test.__name__} -- {type(exc).__name__}: {exc}")
            failures += 1
    print(f"\nrunner contracts: {len(tests) - failures} passed, {failures} failed")
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
