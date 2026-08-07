# NetClaw on `isovalent-demo`

This is the lab deployment for NetClaw. It uses the existing in-cluster
BridgeIT/OpenAI-compatible gateway at
`http://openclaw.defenseclaw.svc.cluster.local:18789/v1` and is intentionally
private by default. The deployed lab configuration also defines a dedicated
public TLS ELB at `https://netclaw.fso-tme.click`, serving the authenticated
NetClaw Visual HUD. The OpenClaw gateway remains cluster-internal.

The manifest is rendered with explicit, reviewed ECR image digests for the
lab.
The repositories retain mutable tags for publishing, but a later tag change
cannot silently change a `kubectl apply -k` deployment.
It expects namespace-local Secrets created outside Git:

- `netclaw-runtime`: `BRIDGEIT_PROXY_API_KEY`, `OPENCLAW_GATEWAY_TOKEN`,
  `TE_TOKEN` (ThousandEyes API v7 OAuth bearer token), and
  `MERAKI_DASHBOARD_API_KEY` (a read-only Meraki Dashboard API key)
- `netclaw-observability`: `GALILEO_API_KEY`
- `netclaw-agent-control`: `AGENT_CONTROL_API_KEY` for the hosted Galileo
  Agent Control API (created and stored separately from telemetry)
- `netclaw-hud-auth`: `username`, `password` for the public HUD's HTTP Basic
  authentication. The public edition disables credential, testbed, transcript,
  and RAG management routes.

Telemetry flows as follows:

```text
NetClaw (Node auto-instrumentation)
  -> NetClaw OpenTelemetry Collector
     -> existing Splunk OTel collector
     -> Galileo demo-v2 https://api.demo-v2.galileocloud.io/otel/traces
        project=network, logstream=netclaw
```

The dedicated collector exports trace attributes unredacted to both Galileo and
Splunk O11y, as explicitly approved for this lab. Its Node instrumentation uses
OTLP/HTTP on port 4318. The Visual HUD emits Galileo's required current GenAI
semantic conventions (`gen_ai.operation.name`, `gen_ai.provider.name`,
`gen_ai.input.messages`, and `gen_ai.output.messages`) together with
OpenInference input/output fields, the complete upstream request/response,
response identity/model/finish reasons, status, and latency. An authenticated,
content-free gateway plugin correlates the completion run ID with OpenClaw's
local transcript metadata so the span carries the real provider/model, session
ID, every model call, cache usage, cost, and token counts; the compatibility
endpoint itself returns zero-valued usage placeholders. The plugin never
returns prompt, completion, tool-call, or tool-result content. The HUD
also emits OpenInference's normalized model, provider, finish reason,
prompt/completion/total/cache token counts, and all provider-reported cost
dimensions. It retains `gen_ai.request.prompt` and `gen_ai.response.content` for existing
Splunk searches. The initial image enables the
self-contained read-only BGP, analysis, and document MCPs. Device, NetBox, and
ServiceNow integrations stay opt-in until separately scoped credentials and
their change path are available.

The lab rollout was verified live on 2026-08-07 with gateway digest
`sha256:c4a4e5288711fbc1ce0da71ed073736727003ca265ac0a85c754001c0b23c8f0`
and Visual digest
`sha256:a903cc3ddbea4c8717480c7c99d47618181e8499468c5cbe4c3a7fdae05be35d`.
Galileo's span API returned the controlled chat's complete multi-turn input,
assistant output, actual `gpt-4o-mini` model, finish reason, duration, token
counts, status, session, trace, and external IDs. The provider reports cost as
zero in this lab; that zero is emitted without inventing a price. The detailed collector exporter used during validation was removed after
that proof; the deployed collector sends traces only to the configured Galileo
and Splunk OTLP exporters.

The Cisco-hosted official ThousandEyes MCP is enabled at
`https://api.thousandeyes.com/mcp` through a pinned `mcp-remote` stdio bridge;
its bearer token stays in `netclaw-runtime`. It includes instant-test
capabilities that consume ThousandEyes units, so use those tools only with an
explicit operational need.

The Cisco-hosted official Meraki MCP is enabled at `https://mcp.meraki.com/mcp`
through the same pinned bridge. The Dashboard API key is injected only from
`netclaw-runtime`; it should be associated with a read-only administrator. The
hosted MCP exposes read-only capability discovery and API execution.

## Verified environment constraints

Baseline captured 2026-08-07 from the `isovalent-demo` context:

- The EKS control plane is Kubernetes 1.36. The `standard` managed node group
  is three on-demand `m5.xlarge` amd64 nodes running EKS 1.34.4 in private
  subnets. Build and publish `linux/amd64` images for this deployment.
- Use `deploy/kubernetes/publish-amd64-image.sh` to publish either the gateway
  or Visual HUD. It runs Buildx with `--platform linux/amd64`, then prints the
  ECR digest to promote. An ARM64-only image cannot be pulled by this cluster.
- The gateway is intentionally a single `Recreate` replica because its 10 Gi
  `ReadWriteOnce` EBS volume cannot be mounted by active replicas on separate
  nodes. Do not add an HPA or switch to rolling updates without redesigning
  persistent state.
- The cluster's only StorageClass is the non-expandable in-tree `gp2` class.
  The existing claim is bound to it; changing the manifest to `gp3` would not
  migrate that live volume. Plan a separate data migration before changing
  storage class or size.
- The HUD is exposed through an internet-facing Classic ELB on port 443. It
  has HTTP Basic authentication in addition to TLS. The manifest requests the
  TLS-1.2-only Classic ELB policy; confirm listener policy and client
  compatibility after an apply.
- All gateway, HUD, and collector pods disable service-account-token mounting,
  run as non-root, drop Linux capabilities, use the runtime-default seccomp
  profile, and mount their root filesystems read-only.

The gateway used about 1.9 GiB of memory during the baseline, while the worker
fleet was 80–86% memory utilized and had memory-limit overcommit. Its request
is therefore set to 2 GiB, and the health probes include a five-minute startup
window plus ten-second response timeouts. This protects slow starts and avoids
placing a restarted gateway based on an unrealistically small reservation.

## Security and operational follow-up

- No Kubernetes `NetworkPolicy` currently applies to `netclaw`; with confirmed
  cluster-wide policy visibility, that means all ingress and egress are
  permitted. Do not introduce a blanket deny policy until the required egress
  flows (BridgeIT, Meraki, ThousandEyes, Galileo, Splunk, DNS, and BGP data
  sources) have been tested in a staged Cilium policy.
- ECR scan-on-push is enabled, but scan findings were unavailable for the two
  currently deployed image digests at the time of this baseline. Treat that as
  *scan not verified*, not as a clean vulnerability result, and verify each
  new digest before promotion.
- EKS control-plane audit logs and an EKS secrets envelope-encryption
  configuration are not enabled. Those are cluster-owner changes, outside this
  namespace manifest, and should be scheduled separately. The control plane is
  also two minor versions ahead of its worker group; coordinate node upgrades
  with the cluster owner.
- The public HUD build intentionally excludes `testbed/`, and the checked-in
  testbed resolves device credentials from `NETCLAW_*` environment variables.
  Create those values only in the local runtime secret store; do not put them
  in Git or the public image.
- Galileo Agent Control is implemented at the HUD's LLM boundary but remains
  inactive until a dedicated Galileo Agent Control API key is stored in
  `netclaw-agent-control`. The telemetry key in `netclaw-observability` is not
  accepted by the hosted control API. Do not enable the hook until a direct
  pre-stage evaluation with the intended runtime key succeeds; a key that is
  valid for the Galileo API may still be unauthorized for Agent Control. After
  that verification, add the secret reference, set `AGENT_CONTROL_ENABLED=true`,
  and validate it before allowing user traffic. Attached pre/post LLM controls
  then take effect with no further HUD deployment; tool controls need an
  upstream OpenClaw tool-lifecycle hook to block a tool before it runs. The
  selected HUD digest contains a `linux/amd64` image; verify that the new pod
  becomes Ready after promotion.

## Pre-apply checks

```bash
kubectl config current-context
kubectl kustomize deploy/kubernetes > /tmp/netclaw-rendered.yaml
kubectl apply --dry-run=server -k deploy/kubernetes
kubectl diff -k deploy/kubernetes
```

Use the lab's approved change path for a live apply, then verify the three
deployments are Available, the ELB listener uses the requested TLS policy, and
the gateway health endpoint is stable under a normal chat request.
