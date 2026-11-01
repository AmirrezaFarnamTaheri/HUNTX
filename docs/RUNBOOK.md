# HUNTX operational runbook

This runbook covers the repository-owned Python pipeline, static dashboard,
and optional daemon/probe fleet. It does not grant a deployed dashboard live
telemetry or make third-party proxy endpoints trustworthy.

## Prerequisites and ownership

| Boundary | Owner | Required before operation |
| --- | --- | --- |
| Ingestion and publication | Pipeline operator | Python 3.11+, approved source configuration, destination credentials, writable data directory |
| Signed artifact workflow | Release operator | `HUNTX_SIGNING_KEY` supplied by secret management |
| Static dashboard | Site/release operator | Verified artifact snapshot and a static HTTP host |
| Daemon rotation | Fleet operator | Private control plane and `HUNTX_DAEMON_CONTROL_TOKEN` |
| Probe reporting receiver | Telemetry-platform operator | Reachable private receiver URL and network policy; HUNTX does not implement this receiver |

Keep all tokens outside version control. A destination-specific token wins over
`PUBLISH_BOT_TOKEN`, which wins over the legacy `TELEGRAM_TOKEN` fallback.
Using the same Telegram token for a persistent bot and ingestion can cause
Telegram consumer conflicts.

## Normal pipeline operation

1. Create and activate a Python environment, then install `pip install -e ".[dev]"`.
2. Supply the source and publication environment variables referenced by the
   selected configuration. Set `HUNTX_SIGNING_KEY` for signing workflows.
3. Perform a dry operational run that creates artifacts but does not send them:

   ```bash
   huntx --config configs/config.prod.yaml run --no-publish --no-auto-deliver
   ```

4. Inspect logs under the configured data directory and verify the produced
   manifest before enabling destination delivery.
5. Run without the two opt-out flags only when publication is authorized.

A `success` or `degraded` disposition can preserve trustworthy work, but a
degraded run needs operator review of source coverage and route failures. A
`fatal` disposition must not be released. See [run-health semantics](RUN_HEALTH.md).

## Recovery

### Source or destination failure

Keep the verified local output, correct credentials or source access, and
rerun. Do not delete state merely to retry: offsets and content-addressed raw
data prevent needless re-ingestion. If a release is incomplete, validate the
current artifact manifest before serving it; otherwise retain the last known
good release.

### Disk/state maintenance

Use `huntx --config <file> prune --days 30` first. It only removes expired
database records and raw blobs no longer referenced by live state.

`clean` and `reset` are recovery actions of last resort. They are destructive,
prompt by default, and cause sources to be treated as first-seen. Copy needed
outputs and check the state backup before accepting their prompt. `reset`
attempts to place a backup at `<data-dir>/state.db.bak`; verify it exists before
starting a fresh run.

### Daemon control

Check the local daemon before rotating:

```bash
curl http://127.0.0.1:9090/status
curl -X POST http://127.0.0.1:9090/rotate \
  -H "Authorization: Bearer $HUNTX_DAEMON_CONTROL_TOKEN"
```

`503 No live proxy node available` means the daemon has no eligible node; it is
not a condition a retry can fix. Restore a healthy node pool or stop serving
the PAC endpoint until one is available.

## Fleet deployment check

Before starting Compose or Helm, confirm all of the following:

- The daemon token is nonempty and stored in deployment secret management.
- `ORCHESTRATOR_URL` is a private, reachable receiver endpoint. The supplied
  probe only POSTs JSON; it does not host that endpoint.
- If the receiver requires bearer auth, set `ORCHESTRATOR_BEARER_TOKEN` in the
  probe environment or Helm values.
- `PROBE_TARGETS` contains only endpoints the operator is authorized to probe.
- Compose fills runtime `PROBE_TARGETS` from `HUNTX_PROBE_TARGETS`; Helm must
  set `probeTargets` explicitly.
- The daemon control service is private. Compose binds it to loopback; Helm
  uses a ClusterIP service and should be paired with namespace/network policy.

Render before applying Helm:

```bash
helm template huntx-fleet deploy/helm/huntx-fleet \
  --set daemon.controlToken="$HUNTX_DAEMON_CONTROL_TOKEN" \
  --set orchestratorUrl="https://telemetry.example.internal/api/vantage/report" \
  --set orchestratorBearerToken="$HUNTX_ORCHESTRATOR_BEARER_TOKEN" \
  --set probeTargets="$HUNTX_PROBE_TARGETS"
```

Then inspect the generated resource names, image tags, and required probe
environment before using `helm upgrade --install` in the intended namespace.

## Validation boundary

Repository checks can validate unit behavior, generated assets, and Helm
rendering. They cannot prove that Telegram credentials work, that a remote
receiver accepts reports, that a proxy endpoint is reachable from a target
region, or that a public deployment is correctly firewalled. Validate those in
the deployment environment and record the result with the release.
