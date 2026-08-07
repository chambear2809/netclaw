#!/usr/bin/env bash
# gait-venv-setup.sh - Create the dedicated GAIT virtualenv
#
# Usage: ./scripts/gait-venv-setup.sh
#
# The 25 skills that record to the GAIT audit trail invoke the server as
# `python3 -u $GAIT_MCP_SCRIPT`. When a distro upgrade moves `python3` to a new
# minor version, the previously installed `gait-ai` is stranded in the old
# site-packages and every one of those skills fails with
# `ModuleNotFoundError: No module named 'gait'`.
#
# This script pins GAIT's dependencies into a venv that survives interpreter
# upgrades. scripts/gait-stdio.py re-execs into it automatically when `gait` is
# not importable, so no skill needs to change.
#
# Re-run this after a Python upgrade.

set -euo pipefail

GAIT_VENV="${GAIT_VENV:-${HOME}/.openclaw/gait-venv}"
GAIT_MCP_REF="${GAIT_MCP_REF:-d17cab9b10428f6d7cecd8a4f0a537ec6943981b}"
PUBLIC_PYPI="https://pypi.org/simple"

echo "=== GAIT venv setup ==="
echo ""

if ! command -v uv &> /dev/null; then
    echo "ERROR: uv not found. Please install uv first:"
    echo "  curl -LsSf https://astral.sh/uv/install.sh | sh"
    echo ""
    echo "(uv is required because Debian/Ubuntu ship python3 without ensurepip,"
    echo " so 'python3 -m venv' cannot bootstrap pip on this host.)"
    exit 1
fi

# GAIT publishes classifiers through Python 3.13. Prefer the system
# interpreter when it is in that supported range; otherwise use uv's managed
# 3.13 runtime. This is the same boundary required by pyATS on current hosts.
SYSTEM_PYTHON="$(command -v python3)"
PYTHON_BIN="${GAIT_PYTHON:-${SYSTEM_PYTHON}}"
PYTHON_MINOR="$("${PYTHON_BIN}" -c 'import sys; print(sys.version_info.minor)')"
if [ "${PYTHON_MINOR}" -lt 10 ] || [ "${PYTHON_MINOR}" -gt 13 ]; then
    PYTHON_BIN="$(uv python find 3.13)"
fi
echo "Base interpreter: ${PYTHON_BIN} ($("${PYTHON_BIN}" -V 2>&1))"
echo "Target venv     : ${GAIT_VENV}"
echo ""

uv venv --no-config --clear "${GAIT_VENV}" --python "${PYTHON_BIN}"

# Dependencies mirror mcp-servers/gait_mcp/pyproject.toml
# Bounds are LOAD-BEARING. mcp 2.0.0 removed mcp.server.fastmcp, and gait_mcp
# imports it (with a fallback to the standalone fastmcp, so either works — but
# only if both are constrained to a major that still provides the API).
#
# This install was previously FULLY UNBOUNDED and sits OUTSIDE any
# requirements.txt, so the spec-077 audit of requirements files missed it
# entirely; it was found only by grepping for venv creation. GAIT is the audit
# trail Constitution Principle IV makes non-negotiable, so it failing on a fresh
# install is not cosmetic.
# Ignore workstation pip/uv configuration here. GAIT is public software; an
# inherited private index previously returned HTTP 403 and left behind an
# empty venv. Install both the library and the MCP server at reviewed pins so
# scripts/gait-stdio.py works even when the optional source checkout is absent.
uv pip install \
    --no-config \
    --default-index "${PUBLIC_PYPI}" \
    --python "${GAIT_VENV}/bin/python" \
    'gait-ai==0.0.9' \
    'mcp>=1.0.0,<2' \
    'fastmcp>=2.0.0,<3' \
    "gait-mcp @ git+https://github.com/automateyournetwork/gait_mcp.git@${GAIT_MCP_REF}"

echo ""
echo "Verifying..."
"${GAIT_VENV}/bin/python" -c "import gait, gait_mcp, mcp, fastmcp; print('  gait   :', gait.__file__); print('  MCP    :', gait_mcp.__file__)"

# The venv only covers callers that go through scripts/gait-stdio.py. Some
# long-running servers import gait *directly* in-process and cannot re-exec:
#   mcp-servers/memory-mcp/memory_mcp_server.py  (gait_log)
#   mcp-servers/rag-mcp/rag_mcp_server.py        (gait_log)
# Both wrap the import in `except Exception: pass`, so a missing gait makes
# their audit logging a silent no-op rather than an error. Ensure the default
# interpreter can import it too.
echo ""
DIRECT_PYTHON="${GAIT_DIRECT_PYTHON:-${SYSTEM_PYTHON}}"
if "${DIRECT_PYTHON}" -c "import gait" 2>/dev/null; then
    echo "Direct importers: ${DIRECT_PYTHON} can already import gait."
else
    echo "Installing gait-ai for ${DIRECT_PYTHON} (direct in-process importers)..."
    "${DIRECT_PYTHON}" -m pip install --isolated --index-url "${PUBLIC_PYPI}" \
        --user --break-system-packages -q 'gait-ai==0.0.9' \
        || echo "  WARNING: could not install gait-ai for ${DIRECT_PYTHON};" \
                "memory-mcp and rag-mcp audit logging will silently no-op."
    "${DIRECT_PYTHON}" -c "import gait; print('  ok:', gait.__file__)" 2>/dev/null || true
fi

echo ""
echo "GAIT venv ready. scripts/gait-stdio.py will re-exec into it as needed."
