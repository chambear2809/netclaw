# Pin to the OpenClaw release already used by DefenseClaw on isovalent-demo.
FROM ghcr.io/openclaw/openclaw@sha256:d65cc3d5fd0c8b1f752c2f70377843230112250c10e99c3b61769234c217c5db

USER root

# Copy dependency manifests before application code so package resolution is cached.
COPY mcp-servers/bgp-intel-mcp/requirements.txt /tmp/requirements-bgp.txt
COPY mcp-servers/document-mcp/requirements.txt /tmp/requirements-document.txt
COPY mcp-servers/analysis-mcp/requirements.txt /tmp/requirements-analysis.txt

# The lab image enables only self-contained NetClaw capabilities. Integrations
# requiring device, NetBox, or ServiceNow credentials remain opt-in.
RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        python3 \
        python3-pip \
        python3-venv \
        graphviz \
        libmagic1 \
    && python3 -m venv /opt/netclaw/.venv \
    && /opt/netclaw/.venv/bin/pip install --no-cache-dir \
        -r /tmp/requirements-bgp.txt \
        -r /tmp/requirements-document.txt \
        -r /tmp/requirements-analysis.txt \
    && rm -f /tmp/requirements-bgp.txt /tmp/requirements-document.txt /tmp/requirements-analysis.txt \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

# Bridge Cisco's authenticated remote ThousandEyes MCP into OpenClaw's stdio
# runtime. Pin the adapter and use the public registry so the image build does
# not inherit a corporate npm proxy configuration.
RUN npm install --global --registry=https://registry.npmjs.org mcp-remote@0.1.38 \
    && npm cache clean --force

COPY --chown=node:node src /opt/netclaw/src
COPY --chown=node:node workspace /opt/netclaw/workspace-template
COPY --chown=node:node mcp-servers/bgp-intel-mcp /opt/netclaw/mcp-servers/bgp-intel-mcp
COPY --chown=node:node mcp-servers/document-mcp /opt/netclaw/mcp-servers/document-mcp
COPY --chown=node:node mcp-servers/analysis-mcp /opt/netclaw/mcp-servers/analysis-mcp
COPY --chown=node:node deploy/kubernetes/openclaw.json /opt/netclaw/deploy/openclaw.json
COPY --chown=node:node deploy/kubernetes/openclaw-telemetry /opt/netclaw/openclaw-telemetry

USER node
WORKDIR /app
