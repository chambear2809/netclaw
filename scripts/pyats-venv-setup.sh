#!/usr/bin/env bash
# Create the isolated pyATS runtime used by the NetClaw MCP server.
#
# pyATS publishes wheels through Python 3.13, while current Homebrew systems
# may default to Python 3.14. uv supplies the supported interpreter and keeps
# the network-automation dependency set out of the system Python.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
NETCLAW_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"
PYATS_VENV="${PYATS_VENV:-${HOME}/.openclaw/pyats-venv}"
PYATS_MCP_DIR="${PYATS_MCP_DIR:-${NETCLAW_DIR}/mcp-servers/pyATS_MCP}"
PYATS_MCP_REF="${PYATS_MCP_REF:-441fae38a8f7da00905942b14635ef73f0448605}"
PYATS_VERSION="${PYATS_VERSION:-3.13}"
PUBLIC_PYPI="https://pypi.org/simple"

echo "=== pyATS venv setup ==="
echo ""

for required_command in uv git; do
    if ! command -v "${required_command}" >/dev/null 2>&1; then
        echo "ERROR: ${required_command} is required." >&2
        exit 1
    fi
done

if [ ! -d "${PYATS_MCP_DIR}/.git" ]; then
    echo "Cloning pyATS MCP at reviewed commit ${PYATS_MCP_REF}..."
    git clone --filter=blob:none https://github.com/automateyournetwork/pyATS_MCP.git "${PYATS_MCP_DIR}"
fi

CURRENT_REF="$(git -C "${PYATS_MCP_DIR}" rev-parse HEAD)"
if [ "${CURRENT_REF}" != "${PYATS_MCP_REF}" ]; then
    if ! git -C "${PYATS_MCP_DIR}" diff --quiet \
        || ! git -C "${PYATS_MCP_DIR}" diff --cached --quiet; then
        echo "ERROR: ${PYATS_MCP_DIR} has local changes; refusing to replace them." >&2
        exit 1
    fi
    git -C "${PYATS_MCP_DIR}" fetch --depth 1 origin "${PYATS_MCP_REF}"
    git -C "${PYATS_MCP_DIR}" checkout --detach "${PYATS_MCP_REF}"
fi

PYTHON_BIN="${PYATS_BASE_PYTHON:-$(uv python find "${PYATS_VERSION}")}"
echo "Base interpreter: ${PYTHON_BIN} ($("${PYTHON_BIN}" -V 2>&1))"
echo "Target venv     : ${PYATS_VENV}"
echo "MCP source      : ${PYATS_MCP_DIR} @ ${PYATS_MCP_REF}"
echo ""

uv venv --no-config --clear "${PYATS_VENV}" --python "${PYTHON_BIN}"
uv pip install \
    --no-config \
    --default-index "${PUBLIC_PYPI}" \
    --python "${PYATS_VENV}/bin/python" \
    --requirement "${PYATS_MCP_DIR}/requirements.txt" \
    'setuptools<81'

echo ""
echo "Verifying..."
"${PYATS_VENV}/bin/python" -c \
    "from importlib.metadata import version; import genie, mcp, pyats; print('  pyATS :', version('pyats')); print('  Genie :', genie.__file__); print('  MCP   :', mcp.__file__)"
"${PYATS_VENV}/bin/python" -m py_compile "${PYATS_MCP_DIR}/pyats_mcp_server.py"

echo ""
echo "pyATS runtime ready. Set:"
echo "  PYATS_PYTHON=${PYATS_VENV}/bin/python"
echo "  PYATS_MCP_SCRIPT=${PYATS_MCP_DIR}/pyats_mcp_server.py"
echo "  PYATS_TESTBED_PATH=${NETCLAW_DIR}/testbed/testbed.yaml"
