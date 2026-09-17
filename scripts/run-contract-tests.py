#!/usr/bin/env python3
"""Prepare and run NetClaw's declared MCP contract-test suites.

The suite manifest is the inventory authority. This runner keeps dependency
setup isolated, executes the existing shell harnesses unchanged, and reports
optional live/Docker capability gaps separately from offline assertion results.

Two suite kinds are supported:

``shell`` (default)  an existing ``tests/<suite>/run-tests.sh`` harness, run as-is.
``pytest``           a repository path or paths collected by pytest. These are
                     the test families that never had a harness entry point, so
                     nothing ran them at all.

A suite may set ``ci: {"include": false, "reason": ...}`` to stay runnable
locally while being held out of the CI matrix. The reason is mandatory: an
exclusion without a recorded justification is the silent omission this manifest
exists to prevent.
"""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import platform
import re
import shutil
import socket
import subprocess
import sys
import tempfile
import time
from urllib import error as urlerror
from urllib import parse as urlparse
from urllib import request as urlrequest


REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_MANIFEST = REPO_ROOT / "tests" / "contract-suites.json"
MARKER_NAME = ".netclaw-contract-env.json"
MAX_OUTPUT = 16_000
SUITE_STATUSES = {"PASS", "FAIL", "BLOCKED_DEPENDENCY", "ERROR"}
CAPABILITY_GAPS = {"NEEDS_LIVE_CREDENTIALS", "NEEDS_DOCKER"}
SUITE_KINDS = {"shell", "pytest"}


class ManifestError(ValueError):
    """The contract-suite manifest is malformed or out of sync."""


def _inside_repo(root: Path, value: str, label: str) -> Path:
    if not isinstance(value, str) or not value:
        raise ManifestError(f"{label} must be a non-empty repository-relative path")
    path = (root / value).resolve()
    try:
        path.relative_to(root.resolve())
    except ValueError as exc:
        raise ManifestError(f"{label} escapes repository root: {value}") from exc
    return path


def _string_list(value, label: str, *, allow_empty: bool = True) -> list[str]:
    if not isinstance(value, list) or (not allow_empty and not value):
        qualifier = "non-empty " if not allow_empty else ""
        raise ManifestError(f"{label} must be a {qualifier}list")
    if any(not isinstance(item, str) or not item for item in value):
        raise ManifestError(f"{label} entries must be non-empty strings")
    return value


def suite_kind(config: dict) -> str:
    """Return a suite's kind. Absent means the historical shell harness."""
    return config.get("kind", "shell")


def suite_ci_exclusion(config: dict) -> str | None:
    """Return the recorded reason this suite is held out of CI, or None."""
    ci = config.get("ci")
    if not isinstance(ci, dict) or ci.get("include", True):
        return None
    return ci.get("reason") or "no reason recorded"


def suite_command(suite_id: str, config: dict, repo_root: Path) -> list[str]:
    """Return the argv this suite executes.

    Shell suites carry their own command. A pytest suite is collected by the
    interpreter the runner already isolated for it, so the suite cannot silently
    fall back to the shared interpreter or to whatever pytest is on PATH.
    """
    if suite_kind(config) == "shell":
        return list(config["command"])
    env_path = config["environment"]["path"]
    interpreter = _venv_python(_inside_repo(repo_root, env_path, f"suite {suite_id}.environment.path")) \
        if env_path is not None else Path(sys.executable)
    return [str(interpreter), "-m", "pytest", *config["paths"], *config.get("args", [])]


def discover_suites(repo_root: Path) -> set[str]:
    """Return immediate tests/* directories containing run-tests.sh."""
    tests_dir = Path(repo_root) / "tests"
    if not tests_dir.is_dir():
        raise ManifestError(f"tests directory not found: {tests_dir}")
    return {
        item.name
        for item in tests_dir.iterdir()
        if item.is_dir() and (item / "run-tests.sh").is_file()
    }


def discover_pytest_suites(repo_root: Path) -> set[str]:
    """Return immediate tests/* directories that hold tests but no harness.

    These are the families that had no entry point of any kind, so no workflow
    or script executed them. Parities over this set are what stop the next such
    directory from being added unnoticed.
    """
    tests_dir = Path(repo_root) / "tests"
    if not tests_dir.is_dir():
        raise ManifestError(f"tests directory not found: {tests_dir}")
    return {
        item.name
        for item in tests_dir.iterdir()
        if item.is_dir()
        and not (item / "run-tests.sh").is_file()
        and next(item.glob("test_*.py"), None) is not None
    }


def _parity_problems(kind: str, declared: set[str], discovered: set[str],
                     stale_label: str, undeclared_label: str) -> list[str]:
    undeclared = sorted(discovered - declared)
    stale = sorted(declared - discovered)
    detail = []
    if undeclared:
        detail.append(f"{undeclared_label}: " + ", ".join(undeclared))
    if stale:
        detail.append(f"{stale_label}: " + ", ".join(stale))
    return [f"[{kind}] {item}" for item in detail]


def load_manifest(path: Path, repo_root: Path) -> dict:
    """Load, validate, and enforce manifest/discovery parity."""
    path = Path(path)
    root = Path(repo_root).resolve()
    try:
        raw = json.loads(path.read_text())
    except (OSError, json.JSONDecodeError) as exc:
        raise ManifestError(f"cannot load manifest {path}: {exc}") from exc

    if not isinstance(raw, dict) or raw.get("schema_version") != 1:
        raise ManifestError("manifest schema_version must be 1")
    if not re.fullmatch(r"\d+\.\d+", str(raw.get("default_python", ""))):
        raise ManifestError("default_python must be a major.minor string")
    suites = raw.get("suites")
    if not isinstance(suites, dict) or not suites:
        raise ManifestError("suites must be a non-empty object")

    for suite_id, config in suites.items():
        prefix = f"suite {suite_id}"
        if not re.fullmatch(r"[a-z0-9][a-z0-9-]*", suite_id):
            raise ManifestError(f"invalid suite id: {suite_id!r}")
        if not isinstance(config, dict):
            raise ManifestError(f"{prefix} must be an object")
        kind = config.get("kind", "shell")
        if kind not in SUITE_KINDS:
            raise ManifestError(f"{prefix}.kind must be one of {sorted(SUITE_KINDS)}")
        if kind == "shell":
            command = _string_list(config.get("command"), f"{prefix}.command", allow_empty=False)
            for arg in command:
                if "/" in arg and not arg.startswith("-"):
                    candidate = _inside_repo(root, arg, f"{prefix}.command")
                    if arg == command[0] and not candidate.exists():
                        raise ManifestError(f"{prefix}.command does not exist: {arg}")
        else:
            if "command" in config:
                raise ManifestError(f"{prefix}.command is not valid for a pytest suite")
            for relative in _string_list(config.get("paths"), f"{prefix}.paths", allow_empty=False):
                if not _inside_repo(root, relative, f"{prefix}.paths").exists():
                    raise ManifestError(f"{prefix}.paths does not exist: {relative}")
            extra_args = _string_list(config.get("args", []), f"{prefix}.args")
            if any(not arg.startswith("-") for arg in extra_args):
                raise ManifestError(f"{prefix}.args must contain pytest flags")

        ci = config.get("ci")
        if ci is not None:
            if not isinstance(ci, dict):
                raise ManifestError(f"{prefix}.ci must be an object")
            if not isinstance(ci.get("include", True), bool):
                raise ManifestError(f"{prefix}.ci.include must be boolean")
            if ci.get("include", True) is False:
                reason = ci.get("reason")
                if not isinstance(reason, str) or not reason.strip():
                    raise ManifestError(
                        f"{prefix}.ci.reason is required when a suite is held out of CI"
                    )

        env = config.get("environment")
        if not isinstance(env, dict):
            raise ManifestError(f"{prefix}.environment must be an object")
        env_path = env.get("path")
        if env_path is not None:
            _inside_repo(root, env_path, f"{prefix}.environment.path")
        requirements = _string_list(env.get("requirements"), f"{prefix}.environment.requirements")
        _string_list(env.get("packages"), f"{prefix}.environment.packages")
        _string_list(env.get("required_imports"), f"{prefix}.environment.required_imports")
        if not isinstance(env.get("prepend_path"), bool):
            raise ManifestError(f"{prefix}.environment.prepend_path must be boolean")
        for requirement in requirements:
            requirement_path = _inside_repo(root, requirement, f"{prefix}.requirements")
            if not requirement_path.is_file():
                raise ManifestError(f"{prefix} requirements file not found: {requirement}")

        timeout = config.get("timeout_seconds")
        if not isinstance(timeout, int) or isinstance(timeout, bool) or timeout <= 0:
            raise ManifestError(f"{prefix}.timeout_seconds must be a positive integer")
        python_version = config.get("python", raw["default_python"])
        if not re.fullmatch(r"\d+\.\d+", str(python_version)):
            raise ManifestError(f"{prefix}.python must be a major.minor string")

        live = config.get("live")
        if live is not None:
            if not isinstance(live, dict) or live.get("mode") not in {"all", "any", "any_group"}:
                raise ManifestError(f"{prefix}.live has an invalid mode")
            names = live.get("env", [])
            groups = live.get("env_groups", [])
            if names:
                _string_list(names, f"{prefix}.live.env", allow_empty=False)
            if groups:
                if not isinstance(groups, list) or any(not isinstance(group, list) for group in groups):
                    raise ManifestError(f"{prefix}.live.env_groups must be a list of lists")
                for group in groups:
                    _string_list(group, f"{prefix}.live.env_groups", allow_empty=False)
            all_names = list(names) + [name for group in groups for name in group]
            if not all_names or any(not re.fullmatch(r"[A-Z][A-Z0-9_]*", name) for name in all_names):
                raise ManifestError(f"{prefix}.live must declare environment variable names")
            if "command" in live:
                _string_list(live["command"], f"{prefix}.live.command", allow_empty=False)

        docker = config.get("docker")
        if docker is not None:
            if not isinstance(docker, dict) or docker.get("level") not in {"daemon", "service"}:
                raise ManifestError(f"{prefix}.docker has an invalid level")
            if docker["level"] == "service" and not isinstance(docker.get("service_url"), str):
                raise ManifestError(f"{prefix}.docker.service_url is required")
            if docker["level"] == "service":
                service_host = urlparse.urlparse(docker["service_url"]).hostname
                if service_host not in {"127.0.0.1", "localhost", "::1"}:
                    raise ManifestError(f"{prefix}.docker.service_url must use a loopback host")
            images = docker.get("images", [])
            _string_list(images, f"{prefix}.docker.images")
            if any("@sha256:" not in image for image in images):
                raise ManifestError(f"{prefix}.docker.images must be pinned by SHA-256 digest")

        artifacts = config.get("artifacts", [])
        if not isinstance(artifacts, list):
            raise ManifestError(f"{prefix}.artifacts must be a list")
        for artifact in artifacts:
            if not isinstance(artifact, dict):
                raise ManifestError(f"{prefix}.artifacts entries must be objects")
            _inside_repo(root, artifact.get("destination"), f"{prefix}.artifact.destination")
            if not isinstance(artifact.get("url"), str) or not artifact["url"].startswith("https://"):
                raise ManifestError(f"{prefix}.artifact.url must use https")
            if not re.fullmatch(r"[0-9a-f]{64}", str(artifact.get("sha256", ""))):
                raise ManifestError(f"{prefix}.artifact.sha256 must be lowercase SHA-256")
            if not isinstance(artifact.get("executable"), bool):
                raise ManifestError(f"{prefix}.artifact.executable must be boolean")

    declared_shell = {suite_id for suite_id, config in suites.items() if suite_kind(config) == "shell"}
    declared_pytest = {suite_id for suite_id, config in suites.items() if suite_kind(config) == "pytest"}
    # A pytest suite may own several repository paths instead of one directory,
    # so only directory-backed entries take part in directory parity.
    dir_backed_pytest = {
        suite_id for suite_id in declared_pytest if (root / "tests" / suite_id).is_dir()
    }
    problems = _parity_problems(
        "shell", declared_shell, discover_suites(root),
        "manifest entries without run-tests.sh",
        "tests/* directories with run-tests.sh but no manifest entry",
    ) + _parity_problems(
        "pytest", dir_backed_pytest, discover_pytest_suites(root),
        "manifest entries without a tests/<suite> directory",
        "tests/* directories holding tests but no manifest entry",
    )
    if problems:
        raise ManifestError("manifest/discovery mismatch: " + "; ".join(problems))
    return raw


def build_matrix(manifest: dict) -> dict:
    default_python = manifest["default_python"]
    return {
        "include": [
            {"suite": suite_id, "python": manifest["suites"][suite_id].get("python", default_python)}
            for suite_id in sorted(manifest["suites"])
            if suite_ci_exclusion(manifest["suites"][suite_id]) is None
        ]
    }


def ci_held_out(manifest: dict) -> list[dict]:
    """Return the suites deliberately kept out of the CI matrix, with reasons."""
    return [
        {
            "suite": suite_id,
            "kind": suite_kind(config),
            "reason": suite_ci_exclusion(config),
        }
        for suite_id, config in sorted(manifest["suites"].items())
        if suite_ci_exclusion(config) is not None
    ]


def _platform_id() -> str:
    system = platform.system().lower()
    machine = platform.machine().lower()
    machine = {"amd64": "x86_64", "aarch64": "arm64"}.get(machine, machine)
    return f"{system}-{machine}"


def _fingerprint(suite_id: str, config: dict, manifest: dict, root: Path) -> tuple[str, dict]:
    env = config["environment"]
    requirements = []
    for relative in env["requirements"]:
        content = (root / relative).read_bytes()
        requirements.append({"path": relative, "sha256": hashlib.sha256(content).hexdigest()})
    payload = {
        "schema_version": manifest["schema_version"],
        "suite": suite_id,
        "kind": suite_kind(config),
        "paths": config.get("paths", []),
        "python": config.get("python", manifest["default_python"]),
        "implementation": sys.implementation.name,
        "requirements": requirements,
        "packages": env["packages"],
        "environment": {"path": env["path"], "prepend_path": env["prepend_path"]},
        "artifacts": [
            {key: item.get(key) for key in ("platform", "url", "destination", "sha256", "executable")}
            for item in config.get("artifacts", [])
        ],
    }
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(encoded).hexdigest(), payload


def _venv_python(env_path: Path) -> Path:
    return env_path / ("Scripts/python.exe" if os.name == "nt" else "bin/python")


def _credential_names(config: dict) -> list[str]:
    live = config.get("live", {})
    return sorted(set(live.get("env", []) + [name for group in live.get("env_groups", []) for name in group]))


def _redact(text: str, config: dict) -> str:
    secret_names = set(_credential_names(config))
    secret_names.update(
        name for name in os.environ
        if re.search(r"(?:TOKEN|PASSWORD|SECRET|API_KEY|PRIVATE_KEY|CREDENTIAL|AUTH)", name, re.I)
    )
    for name in secret_names:
        value = os.environ.get(name)
        if value and len(value) >= 4:
            text = text.replace(value, "[REDACTED]")
    text = re.sub(r"://[^/\s:@]+:[^@\s/]+@", "://[REDACTED]@", text)
    return text


def _live_capability(config: dict) -> dict | None:
    live = config.get("live")
    if not live:
        return None
    names = live.get("env", [])
    groups = live.get("env_groups", [])
    mode = live["mode"]
    if mode == "all":
        missing = [name for name in names if not os.environ.get(name)]
        available = not missing
    elif mode in {"any", "any_group"} and groups:
        available = any(all(os.environ.get(name) for name in group) for group in groups)
        missing = sorted({name for group in groups for name in group if not os.environ.get(name)})
    else:
        available = any(os.environ.get(name) for name in names)
        missing = [name for name in names if not os.environ.get(name)]
    if available:
        return {"status": "AVAILABLE", "kind": "live", "names": sorted(_credential_names(config)),
                "detail": live.get("description", "live credentials available")}
    return {"status": "NEEDS_LIVE_CREDENTIALS", "kind": "live", "names": sorted(missing),
            "detail": "missing: " + ", ".join(sorted(missing))}


def _service_available(service_url: str) -> tuple[bool, str]:
    parsed = urlparse.urlparse(service_url)
    if parsed.scheme == "tcp":
        host = parsed.hostname or "127.0.0.1"
        port = parsed.port
        if port is None:
            return False, f"invalid service URL: {service_url}"
        try:
            with socket.create_connection((host, port), timeout=1):
                return True, f"service available: {service_url}"
        except OSError:
            return False, f"service unavailable: {service_url}"
    try:
        req = urlrequest.Request(service_url, method="GET")
        with urlrequest.urlopen(req, timeout=2):
            return True, f"service available: {service_url}"
    except (OSError, urlerror.URLError, ValueError):
        return False, f"service unavailable: {service_url}"


def _docker_capability(config: dict) -> dict | None:
    requirement = config.get("docker")
    if not requirement:
        return None
    docker = shutil.which("docker")
    if not docker:
        return {"status": "NEEDS_DOCKER", "kind": "docker-daemon", "names": [],
                "detail": "docker executable is not installed"}
    try:
        probe = subprocess.run([docker, "info"], capture_output=True, text=True, timeout=5)
    except (OSError, subprocess.TimeoutExpired):
        probe = None
    if probe is None or probe.returncode != 0:
        return {"status": "NEEDS_DOCKER", "kind": "docker-daemon", "names": [],
                "detail": "docker daemon is unreachable"}
    missing_images = []
    for image in requirement.get("images", []):
        try:
            inspect = subprocess.run([docker, "image", "inspect", image], capture_output=True,
                                     text=True, timeout=5)
        except (OSError, subprocess.TimeoutExpired):
            inspect = None
        if inspect is None or inspect.returncode != 0:
            missing_images.append(image)
    if missing_images:
        return {"status": "NEEDS_DOCKER", "kind": "docker-image", "names": [],
                "detail": "pinned images unavailable: " + ", ".join(missing_images)}
    if requirement["level"] == "service":
        service_url = requirement["service_url"]
        available, detail = _service_available(service_url)
        return {"status": "AVAILABLE" if available else "NEEDS_DOCKER", "kind": "docker-service",
                "names": [], "detail": detail}
    return {"status": "AVAILABLE", "kind": "docker-daemon", "names": [],
            "detail": "docker daemon is available"}


def preflight_suite(suite_id: str, suite_config: dict, repo_root: Path, manifest: dict | None = None) -> dict:
    """Inspect offline dependencies and optional capabilities without running a suite."""
    root = Path(repo_root).resolve()
    capabilities = [item for item in (_live_capability(suite_config), _docker_capability(suite_config)) if item]
    result = {
        "suite": suite_id,
        "status": "PASS",
        "exit_code": None,
        "duration_seconds": 0.0,
        "command": suite_command(suite_id, suite_config, root),
        "environment": {"path": suite_config["environment"]["path"], "fingerprint": None},
        "capabilities": capabilities,
        "detail": "offline dependencies available",
    }
    env = suite_config["environment"]
    interpreter = Path(sys.executable)
    if env["path"] is not None:
        env_path = _inside_repo(root, env["path"], f"suite {suite_id}.environment.path")
        interpreter = _venv_python(env_path)
        marker = env_path / MARKER_NAME
        if manifest is not None:
            fingerprint, _ = _fingerprint(suite_id, suite_config, manifest, root)
            result["environment"]["fingerprint"] = fingerprint
            try:
                marker_data = json.loads(marker.read_text())
            except (OSError, json.JSONDecodeError):
                marker_data = {}
            if marker_data.get("fingerprint") != fingerprint:
                result["status"] = "BLOCKED_DEPENDENCY"
                result["detail"] = "isolated environment is missing or stale; run with --prepare"
                return result
        if not interpreter.is_file():
            result["status"] = "BLOCKED_DEPENDENCY"
            result["detail"] = f"isolated interpreter is missing: {interpreter.relative_to(root)}"
            return result

    imports = env["required_imports"]
    if imports:
        code = "import importlib.util,sys; missing=[x for x in sys.argv[1:] if importlib.util.find_spec(x) is None]; print('\\n'.join(missing))"
        try:
            probe = subprocess.run([str(interpreter), "-c", code, *imports], capture_output=True,
                                   text=True, timeout=15, cwd=root)
        except (OSError, subprocess.TimeoutExpired) as exc:
            result["status"] = "BLOCKED_DEPENDENCY"
            result["detail"] = f"dependency probe failed: {type(exc).__name__}"
            return result
        missing = [line for line in probe.stdout.splitlines() if line]
        if probe.returncode != 0 or missing:
            result["status"] = "BLOCKED_DEPENDENCY"
            result["detail"] = "missing imports: " + ", ".join(missing or imports)
            return result

    artifacts = suite_config.get("artifacts", [])
    matching_artifacts = [item for item in artifacts if item.get("platform") == _platform_id()]
    if artifacts and not matching_artifacts:
        declared = ", ".join(sorted(item["platform"] for item in artifacts))
        result["status"] = "BLOCKED_DEPENDENCY"
        result["detail"] = f"no artifact for {_platform_id()} (declared: {declared})"
        return result
    for artifact in matching_artifacts:
        destination = _inside_repo(root, artifact["destination"], f"suite {suite_id}.artifact")
        if not destination.is_file():
            result["status"] = "BLOCKED_DEPENDENCY"
            result["detail"] = f"artifact is missing: {artifact['destination']}; run with --prepare"
            return result
        digest = hashlib.sha256(destination.read_bytes()).hexdigest()
        if digest != artifact["sha256"]:
            result["status"] = "BLOCKED_DEPENDENCY"
            result["detail"] = (
                f"artifact checksum mismatch: {artifact['destination']}; run with --prepare"
            )
            return result
    return result


def aggregate_exit(results: list[dict], strict: bool) -> int:
    statuses = {result.get("status") for result in results}
    if statuses & {"BLOCKED_DEPENDENCY", "ERROR"}:
        return 2
    if strict and any(cap.get("status") in CAPABILITY_GAPS for result in results
                      for cap in result.get("capabilities", [])):
        return 2
    if "FAIL" in statuses:
        return 1
    return 0


def format_result(result: dict) -> str:
    duration = f"{result.get('duration_seconds', 0.0):.2f}s"
    lines = [f"{result['status']:<20} {result['suite']:<14} {duration:>8}  {result['detail']}"]
    for capability in result.get("capabilities", []):
        if capability["status"] in CAPABILITY_GAPS:
            lines.append(f"{capability['status']:<22} {result['suite']:<14} {capability['detail']}")
    if result.get("output"):
        lines.append(result["output"])
    return "\n".join(lines)


def _run_checked(argv: list[str], cwd: Path, timeout: int = 900) -> None:
    completed = subprocess.run(argv, cwd=cwd, text=True, capture_output=True, timeout=timeout)
    if completed.returncode:
        detail = (completed.stderr or completed.stdout).strip()[-4000:]
        raise RuntimeError(f"command failed ({completed.returncode}): {' '.join(argv)}\n{detail}")


def _prepare_artifacts(suite_id: str, config: dict, root: Path) -> None:
    artifacts = config.get("artifacts", [])
    if not artifacts:
        return
    matching = [item for item in artifacts if item["platform"] == _platform_id()]
    if not matching:
        declared = ", ".join(sorted(item["platform"] for item in artifacts))
        raise RuntimeError(f"{suite_id}: no artifact for {_platform_id()} (declared: {declared})")
    for artifact in matching:
        destination = _inside_repo(root, artifact["destination"], f"suite {suite_id}.artifact")
        if destination.is_file() and hashlib.sha256(destination.read_bytes()).hexdigest() == artifact["sha256"]:
            continue
        destination.parent.mkdir(parents=True, exist_ok=True)
        temp_name = None
        try:
            with tempfile.NamedTemporaryFile(dir=destination.parent, delete=False) as temp:
                temp_name = temp.name
                with urlrequest.urlopen(artifact["url"], timeout=60) as response:
                    shutil.copyfileobj(response, temp)
            downloaded = Path(temp_name)
            digest = hashlib.sha256(downloaded.read_bytes()).hexdigest()
            if digest != artifact["sha256"]:
                raise RuntimeError(f"{suite_id}: artifact SHA-256 mismatch; expected {artifact['sha256']}, got {digest}")
            if artifact["executable"]:
                downloaded.chmod(downloaded.stat().st_mode | 0o111)
            downloaded.replace(destination)
            temp_name = None
        finally:
            if temp_name:
                Path(temp_name).unlink(missing_ok=True)


def prepare_suite(suite_id: str, config: dict, manifest: dict, root: Path) -> None:
    """Create or refresh a suite's declared environment and artifacts."""
    _prepare_artifacts(suite_id, config, root)
    env = config["environment"]
    if env["path"] is None:
        return
    env_path = _inside_repo(root, env["path"], f"suite {suite_id}.environment.path")
    fingerprint, payload = _fingerprint(suite_id, config, manifest, root)
    marker = env_path / MARKER_NAME
    try:
        existing = json.loads(marker.read_text())
    except (OSError, json.JSONDecodeError):
        existing = {}
    interpreter = _venv_python(env_path)
    if existing.get("fingerprint") == fingerprint and interpreter.is_file():
        return
    if env_path.exists():
        shutil.rmtree(env_path)
    env_path.parent.mkdir(parents=True, exist_ok=True)

    python_version = config.get("python", manifest["default_python"])
    uv = shutil.which("uv")
    current_version = f"{sys.version_info.major}.{sys.version_info.minor}"
    base_python = sys.executable if current_version == python_version else shutil.which(f"python{python_version}")
    if uv:
        try:
            _run_checked([uv, "venv", "--python", python_version, str(env_path)], root)
        except RuntimeError:
            if not base_python:
                raise RuntimeError(
                    f"{suite_id}: Python {python_version} is unavailable and uv could not create it"
                )
            _run_checked([str(base_python), "-m", "venv", str(env_path)], root)
    else:
        if not base_python:
            raise RuntimeError(
                f"{suite_id}: Python {python_version} is unavailable (install it or uv)"
            )
        _run_checked([str(base_python), "-m", "venv", str(env_path)], root)
    interpreter = _venv_python(env_path)
    if not interpreter.is_file():
        raise RuntimeError(f"{suite_id}: virtual environment did not create {interpreter}")

    def install(args: list[str], cwd: Path) -> None:
        if uv:
            _run_checked([uv, "pip", "install", "--python", str(interpreter), *args], cwd)
        else:
            _run_checked([str(interpreter), "-m", "pip", "install", *args], cwd)

    for relative in env["requirements"]:
        requirement = root / relative
        install(["-r", requirement.name], requirement.parent)
    if env["packages"]:
        install(list(env["packages"]), root)

    marker.write_text(json.dumps({
        "fingerprint": fingerprint,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "python": python_version,
        "definition": payload,
    }, indent=2, sort_keys=True) + "\n")


def run_suite(suite_id: str, config: dict, manifest: dict, root: Path) -> dict:
    started = time.monotonic()
    result = preflight_suite(suite_id, config, root, manifest)
    if result["status"] != "PASS":
        result["duration_seconds"] = time.monotonic() - started
        return result
    environment = os.environ.copy()
    # Live evidence is always opt-in outside this command. Some legacy shell
    # harnesses auto-enable live branches when variables happen to be present,
    # so remove declared credential inputs from the offline child process.
    for name in _credential_names(config):
        environment.pop(name, None)
    env_path_value = config["environment"]["path"]
    if env_path_value is not None:
        env_path = _inside_repo(root, env_path_value, f"suite {suite_id}.environment.path")
        interpreter = _venv_python(env_path)
        environment["NETCLAW_PY"] = str(interpreter)
        if config["environment"]["prepend_path"]:
            environment["PATH"] = str(interpreter.parent) + os.pathsep + environment.get("PATH", "")
    try:
        completed = subprocess.run(suite_command(suite_id, config, root), cwd=root, env=environment,
                                   text=True, capture_output=True, timeout=config["timeout_seconds"])
        result["exit_code"] = completed.returncode
        result["duration_seconds"] = time.monotonic() - started
        output = (completed.stdout + completed.stderr).strip()
        output = _redact(output, config)
        if completed.returncode == 0:
            result["status"] = "PASS"
            result["detail"] = "offline contracts passed"
        else:
            result["status"] = "FAIL"
            result["detail"] = f"harness exited {completed.returncode}"
            result["output"] = output[-MAX_OUTPUT:]
    except subprocess.TimeoutExpired as exc:
        result["status"] = "ERROR"
        result["duration_seconds"] = time.monotonic() - started
        result["detail"] = f"harness timed out after {config['timeout_seconds']}s"
        captured = ((exc.stdout or "") + (exc.stderr or "")) if isinstance(exc.stdout, str) else ""
        if captured:
            result["output"] = _redact(captured, config)[-MAX_OUTPUT:]
    except OSError as exc:
        result["status"] = "ERROR"
        result["duration_seconds"] = time.monotonic() - started
        result["detail"] = f"could not execute harness: {exc}"
    return result


def _aggregate(results: list[dict], strict: bool) -> dict:
    counts = {status: 0 for status in sorted(SUITE_STATUSES | CAPABILITY_GAPS)}
    for result in results:
        counts[result["status"]] += 1
        for capability in result.get("capabilities", []):
            if capability["status"] in CAPABILITY_GAPS:
                counts[capability["status"]] += 1
    return {
        "schema_version": 1,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "results": results,
        "counts": counts,
        "exit_code": aggregate_exit(results, strict),
    }


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--list", action="store_true", help="list declared suites")
    mode.add_argument("--matrix", action="store_true", help="emit a GitHub Actions matrix")
    mode.add_argument("--suite", metavar="ID", help="suite id or 'all'")
    parser.add_argument("--prepare", action="store_true", help="prepare isolated dependencies before running")
    parser.add_argument("--strict-capabilities", action="store_true",
                        help="treat optional live/Docker gaps as exit 2")
    parser.add_argument("--json", action="store_true", help="emit machine-readable JSON")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    try:
        manifest = load_manifest(DEFAULT_MANIFEST, REPO_ROOT)
        if args.matrix:
            print(json.dumps(build_matrix(manifest), separators=(",", ":")))
            return 0
        if args.list:
            suites = [
                {
                    "suite": suite_id,
                    "kind": suite_kind(manifest["suites"][suite_id]),
                    "python": manifest["suites"][suite_id].get("python", manifest["default_python"]),
                    "ci_reason": suite_ci_exclusion(manifest["suites"][suite_id]),
                }
                for suite_id in sorted(manifest["suites"])
            ]
            if args.json:
                print(json.dumps({"schema_version": 1, "suites": suites,
                                  "ci_held_out": ci_held_out(manifest)}, indent=2))
            else:
                for item in suites:
                    marker = "  (not in CI)" if item["ci_reason"] else ""
                    print(f"{item['suite']:<14} {item['kind']:<7} Python {item['python']}{marker}")
                held_out = ci_held_out(manifest)
                if held_out:
                    print("\nHeld out of the CI matrix:")
                    for item in held_out:
                        print(f"  {item['suite']:<14} {item['reason']}")
            return 0

        selected = sorted(manifest["suites"]) if args.suite == "all" else [args.suite]
        unknown = [suite_id for suite_id in selected if suite_id not in manifest["suites"]]
        if unknown:
            raise ManifestError("unknown suite: " + ", ".join(unknown))
        results = []
        for suite_id in selected:
            config = manifest["suites"][suite_id]
            if args.prepare:
                try:
                    prepare_suite(suite_id, config, manifest, REPO_ROOT)
                except Exception as exc:
                    results.append({
                        "suite": suite_id, "status": "BLOCKED_DEPENDENCY", "exit_code": None,
                        "duration_seconds": 0.0, "command": suite_command(suite_id, config, REPO_ROOT),
                        "environment": {"path": config["environment"]["path"], "fingerprint": None},
                        "capabilities": [item for item in (_live_capability(config), _docker_capability(config)) if item],
                        "detail": _redact(f"preparation failed: {exc}", config),
                    })
                    continue
            results.append(run_suite(suite_id, config, manifest, REPO_ROOT))
        aggregate = _aggregate(results, args.strict_capabilities)
        if args.json:
            print(json.dumps(aggregate, indent=2, sort_keys=True))
        else:
            for result in results:
                print(format_result(result))
        return aggregate["exit_code"]
    except ManifestError as exc:
        if args.json:
            print(json.dumps({"schema_version": 1, "error": str(exc), "exit_code": 2}))
        else:
            print(f"ERROR: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
