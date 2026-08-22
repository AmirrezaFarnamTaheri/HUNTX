# HUNTX User Guide

## Table of Contents

1. [Configuration](#configuration)
2. [Supported Formats](#supported-formats)
3. [Supported Proxy Protocols](#supported-proxy-protocols)
4. [Running Locally](#running-locally)
5. [CLI Commands](#cli-commands)
6. [Interactive Web Telemetry Dashboard](#interactive-web-telemetry-dashboard)
7. [Running on GitHub Actions](#running-on-github-actions)
8. [Telegram User Session (MTProto)](#telegram-user-session-mtproto)
9. [GatherX Bot](#gatherx-bot)
10. [Media Filtering](#media-filtering)
11. [Architecture & C4 Model](#architecture--c4-model)
12. [Output Artifacts](#output-artifacts)

---

## Configuration

### Runtime Secrets

Set secrets outside committed configuration. `HUNTX_SIGNING_KEY` is required whenever supply-chain manifests are signed, and daemon control requests require `HUNTX_DAEMON_CONTROL_TOKEN`. Fleet probes require an explicit private orchestrator endpoint and target list; if that receiver uses bearer auth, set `HUNTX_ORCHESTRATOR_BEARER_TOKEN`. A static dashboard does not itself receive or display live probe reports.

HUNTX is controlled by a YAML configuration file with environment variable expansion (`${VAR}`).

### Sources

#### Bot API Source

For private channels where the bot is an admin:

```yaml
sources:
  - id: "source_channel_1"
    type: "telegram"
    selector:
      include_formats: ["all"]
    telegram:
      token: "${TELEGRAM_TOKEN}"
      chat_id: "-1001234567890"
```

#### MTProto User Source

For public channels, message history, and text content:

```yaml
sources:
  - id: "public_channel"
    type: "telegram_user"
    selector:
      include_formats: ["npvt", "npvtsub", "conf_lines"]
    telegram_user:
      api_id: ${TELEGRAM_API_ID}
      api_hash: "${TELEGRAM_API_HASH}"
      session: "${TELEGRAM_USER_SESSION}"
      peer: "@ChannelName"
```

### Publishing Routes

```yaml
publishing:
  routes:
    - name: "merged_vpn"
      from_sources: ["source_channel_1"]
      formats: ["npvt"]
      destinations:
        - chat_id: "-1001234567890"
          mode: "telegram"
```

---

## Supported Formats

| Format | Extension | Type | Handler |
|---|---|---|---|
| NPVT (Proxy URIs) | `.npvt` | Text | `NpvtHandler` |
| NPVT Subscription | `.npvtsub` | Base64 Text | `NpvtsubHandler` |
| Config Lines | `.txt` / `.conf` | Text | `ConfLinesHandler` |
| OpenVPN | `.ovpn` | Binary / ZIP | `OvpnHandler` |
| HTTP Custom | `.hc` | Binary / ZIP | `HcHandler` |
| HTTP Injector | `.ehi` | Binary / ZIP | `EhiHandler` |
| HA Tunnel | `.hat` | Binary / ZIP | `HatHandler` |
| NapsternetV | `.npv4` | Binary / ZIP | `Npv4Handler` |
| NetMod | `.nm` | Binary / ZIP | `NmHandler` |
| SocksIP | `.sip` | Binary / ZIP | `SipHandler` |
| Dark Tunnel | `.dark` | Binary / ZIP | `DarkHandler` |
| Generic Binary | `*` | Binary / ZIP | `OpaqueBundleHandler` |

---

## Supported Proxy Protocols

HUNTX natively parses, sanitizes, and normalizes the following proxy URI protocols:

- **VLESS Reality / TLS**: `vless://uuid@host:port?security=reality&...#name`
- **VMess (Base64 JSON)**: `vmess://eyJhZGQiOiI...`
- **Trojan TLS / gRPC**: `trojan://password@host:port?security=tls...#name`
- **Shadowsocks (SIP002)**: `ss://base64(method:pass)@host:port#name`
- **Hysteria2 / Hy2**: `hysteria2://auth@host:port?sni=...#name`
- **TUIC**: `tuic://uuid:password@host:port?...`
- **WireGuard**: `wireguard://...`
- **SOCKS5 / HTTP(S)**: `socks5://...`, `http://...`

---

## Running Locally

### Option 1: Go Engine Ingestion
```bash
# Parse a subscription file to JSON. The engine writes to stdout;
# redirect only after reviewing the result.
go run ./cmd/huntx-engine parse --file data/raw/sources.txt > parsed.json
```

Other supported engine commands are `benchmark`, `georoute`, `chain`, and
`tlsdiag`; run `go run ./cmd/huntx-engine` to see their required flags. The
engine is an analysis tool and does not publish artifacts.

### Option 2: Python Orchestration Pipeline
```bash
# Build with production orchestration but do not publish or auto-deliver.
huntx --config configs/config.prod.yaml run --no-publish --no-auto-deliver
```

Remove the two safety flags only after validating source access and the
destination configuration. A run can retain verified output while reporting a
degraded health disposition; inspect the structured log and artifact manifest
before treating it as a release.

---

## CLI Commands

| Command | Usage | Description |
|---|---|---|
| `run` | `huntx --config config.yaml run` | Execute ingestion, merge, build, and delivery |
| `bot` | `huntx --config config.yaml bot` | Run persistent GatherX Telegram bot |
| `clean` | `huntx --config config.yaml clean` | Prune stale raw blobs and expired cache |
| `reset` | `huntx --config config.yaml reset` | Factory reset of data, outputs, caches, and source offsets |
| `prune` | `huntx --config config.yaml prune --days 30` | Remove expired database records and unreferenced raw blobs |

`clean` and `reset` are destructive. Both prompt by default. `clean` preserves
registered bot users when it can back them up; `reset` also writes a local
`state.db.bak` before removing the state directory. Do not pass `--yes` until
you have copied any required artifacts and verified the backup location. Both
commands make every source look first-seen on its next ingestion pass.

---

## Interactive Web Telemetry Dashboard

HUNTX includes a static dashboard located at [`docs/index.html`](index.html).

### Features
1. **Interactive 3D Geo-Radar**: Canvas globe for filtering the published snapshot by mapped hub.
2. **Real-Time Client-Side Protocol Decoder**: Press `D` or click **Decoder** to paste raw proxy URIs for instant JSON parameter inspection.
3. **Standalone QR Code Generator**: Click the QR icon on any node card to generate a scannable SVG QR code for mobile import (v2rayNG, Sing-box, Shadowrocket).
4. **Subscription Feed Generator**: Generate Base64 subscription URLs (`proxies_b64sub.txt`) or plain text config feeds (`proxies.txt`).
5. **Interactive 3D Architecture Topology**: Explore the system data flow via [`docs/architecture.html`](architecture.html).

### Offline / Local Use

The page and JavaScript bundle can open directly, but the checked-in page uses
CDN fonts and utility CSS. Use a local HTTP server for the supported preview;
for a truly offline deployment, vendor those external assets before making that
claim.

```bash
python -m http.server 8000 --directory docs
```

The dashboard displays a published snapshot. Labels or latency values are not
live measurements unless the artifact producer has populated them from an
actual probe integration.

---

## GatherX Bot

The GatherX Telegram bot provides DM-based node delivery and subscription control:

| Command | Description |
|---|---|
| `/start` | Register and view help menu |
| `/get` | Request latest merged proxy configuration |
| `/latest` | View timestamp and active proxy count |
| `/formats` | List all supported file formats |
| `/protocols` | List recognized proxy URI schemes |
| `/status` | View pipeline health status |
| `/mute` | Opt out of automatic broadcast delivery |
| `/unmute` | Re-enable automatic broadcast delivery |

---

## Architecture & C4 Model

Detailed C4 Architecture diagrams and component contracts are documented in:
- [`docs/C4_ARCHITECTURE.md`](C4_ARCHITECTURE.md) (Context, Container, Component, Code levels)
- [`docs/DESIGN.md`](DESIGN.md) (Design system, OKLCH tokens, component states)
- [`docs/DEVELOPMENT.md`](DEVELOPMENT.md) (Developer and build instructions)

---

## Output Artifacts

| Artifact | Path | Description |
|---|---|---|
| **JSON Proxy Array** | `docs/artifacts/dev/proxies.json` | Structured JSON array of verified proxy nodes |
| **Raw URI Text** | `docs/artifacts/dev/proxies.txt` | Line-separated raw proxy URIs |
| **Base64 Subscription** | `docs/artifacts/dev/proxies_b64sub.txt` | Base64-encoded subscription feed for proxy clients |
| **Catalog Manifest** | `docs/catalog.json` | Cryptographic SHA-256 catalog with file sizes and timestamps |
| **Output Manifest** | `docs/artifacts/dev/_manifest.json` | Pipeline generation metadata |

## Daemon and probe fleet

The daemon is a small PAC/control service, separate from the Python pipeline.
It binds to `127.0.0.1:9090` by default. `GET /status` and `GET /proxy.pac`
are read-only; `POST /rotate` requires this header:

```text
Authorization: Bearer <HUNTX_DAEMON_CONTROL_TOKEN>
```

Do not publish the control API through an unauthenticated load balancer. The
Compose file deliberately maps it to `127.0.0.1:9090` on the host.

Probe agents read `PROBE_ID`, `REGION`, `ORCHESTRATOR_URL`,
`ORCHESTRATOR_BEARER_TOKEN`, and `PROBE_TARGETS` (the runtime variable
populated from `HUNTX_PROBE_TARGETS` in Compose or `probeTargets` in Helm;
comma, semicolon, or space separated), sweep their targets every 30 seconds,
and POST a report to `ORCHESTRATOR_URL`. HUNTX does not ship the receiver at
that URL; make the receiver private and use `ORCHESTRATOR_BEARER_TOKEN` when
it requires bearer authentication. See
[Development](DEVELOPMENT.md#6-fleet-deployment-boundary) for Compose and Helm
prerequisites.
