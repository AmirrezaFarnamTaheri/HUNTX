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
      selector:
        include_formats: ["npvt"]
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
# Run Go ingestion stream parser
go run ./cmd/huntx-engine --input data/raw/sources.txt --output docs/artifacts/dev/proxies.json
```

### Option 2: Python Orchestration Pipeline
```bash
# Run full python pipeline with auto-delivery
python -m huntx.cli.main --config configs/config.prod.yaml run
```

---

## CLI Commands

| Command | Usage | Description |
|---|---|---|
| `run` | `huntx --config config.yaml run` | Execute ingestion, merge, build, and delivery |
| `bot` | `huntx --config config.yaml bot` | Run persistent GatherX Telegram bot |
| `clean` | `huntx --config config.yaml clean` | Prune stale raw blobs and expired cache |
| `reset` | `huntx --config config.yaml reset` | Full reset of database and stored offsets |

---

## Interactive Web Telemetry Dashboard

HUNTX includes a sovereign, offline-first Web Dashboard located at [`docs/index.html`](index.html).

### Features
1. **Interactive 3D Geo-Radar**: GPU-accelerated canvas globe rendering global node hubs (Frankfurt, Amsterdam, Helsinki, Singapore, London, New York, Istanbul, Tokyo) with click-to-filter capability.
2. **Real-Time Client-Side Protocol Decoder**: Press `D` or click **Decoder** to paste raw proxy URIs for instant JSON parameter inspection.
3. **Standalone QR Code Generator**: Click the QR icon on any node card to generate a scannable SVG QR code for mobile import (v2rayNG, Sing-box, Shadowrocket).
4. **Subscription Feed Generator**: Generate Base64 subscription URLs (`proxies_b64sub.txt`) or plain text config feeds (`proxies.txt`).
5. **Interactive 3D Architecture Topology**: Explore the system data flow via [`docs/architecture.html`](architecture.html).

### Offline / Local Use
You can open [`docs/index.html`](index.html) directly via `file:///` double-click or host it on any static server:
```bash
python -m http.server 8000 --directory docs
```

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
