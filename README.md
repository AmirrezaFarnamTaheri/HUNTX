# HUNTX (GatherX) — Cyber Telemetry & Sovereign Ingestion Engine

[![Go Tests](https://github.com/AmirrezaFarnamTaheri/HUNTX/actions/workflows/ci.yml/badge.svg)](https://github.com/AmirrezaFarnamTaheri/HUNTX/actions)
[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)
[![Platform](https://img.shields.io/badge/platform-Linux%20%7C%20macOS%20%7C%20Windows-blue)](https://github.com/AmirrezaFarnamTaheri/HUNTX)
[![Architecture: C4 Model](https://img.shields.io/badge/Architecture-C4%20Model-cyan)](#architecture)

**HUNTX** (powered by GatherX) is a proxy-configuration ingestion, normalization, and publishing platform. It ingests approved sources, produces deterministic artifacts, and ships a static dashboard for inspecting the latest published snapshot. Runtime probe telemetry is an optional deployment integration that depends on a separate private receiver; it is not implied by the static dashboard.

---

## ⚡ Key Capabilities

- **Go analysis tool (`cmd/huntx-engine`)**: A concurrency-safe parser and diagnostic CLI for proxy streams, benchmarking, geo-routing, chain synthesis, and TLS inspection. It is not the production ingestion orchestrator.
- **Static Dashboard & Web SPA (`docs/`)**: Browser dashboard with client-side protocol decoding and QR generation. It shows the published snapshot and clearly falls back when current artifacts are unavailable.
- **Multi-Protocol Coverage**: Native decoding and normalization for **VLESS Reality**, **VMess (Base64 JSON)**, **Trojan TLS**, **Shadowsocks (SIP002)**, and **Hysteria2 / Hy2**.
- **Cryptographic Deduplication**: Content-addressed SHA-256 fingerprinting prevents configuration duplication across heterogeneous channels.
- **GeoRoute Intelligence (`georoute`)**: Automatic GeoIP/CIDR resolution mapping nodes to ISO-3166 alpha-2 regional telemetry hubs (DE, NL, FI, SG, GB, US, TR, JP).
- **Proactive Node Healing (`healing`)**: Automated failure detection, jitter analysis, and fallback route restoration.
- **CI/CD Zero-Budget Automation**: Fully automated GitHub Actions workflow scheduled every 2 hours with atomic GitHub Pages deployment.

---

<a id="architecture"></a>

## 🏗️ Architecture (C4)

One model, three zoom levels. This section is the **single source of truth** for HUNTX diagrams — the former 3D topology page and the standalone C4 document were consolidated here. Shapes: rounded = person · box = system or container · cylinder = datastore · dashed border = optional or partial.

### Level 1 — System context

*Who interacts with HUNTX, over what protocol?*

```mermaid
flowchart TB
    user(["Proxy consumer"])
    admin(["Maintainer"])

    subgraph HUNTX["HUNTX (GatherX)"]
        huntx["Node intelligence platform:<br>ingest · decode · dedupe · publish"]
    end

    tg["Telegram channels + bots"]
    ci["GitHub Actions"]
    s3["S3 generation state"]
    cdn["GitHub Pages CDN"]
    clients["Proxy clients<br>(v2rayNG, sing-box, Clash…)"]

    admin -- "source config · health checks" --> huntx
    tg -- "MTProto / Bot API feeds" --> huntx
    ci -- "scheduled runs every 2 h" --> huntx
    s3 -. "optional durable state" .- ci
    huntx -- "git push verified snapshot" --> cdn
    cdn -- "dashboard + JSON/TXT feeds" --> user
    cdn -- "base64 subscriptions" --> clients

    classDef person fill:#fef3c7,stroke:#b45309,color:#78350f
    classDef system fill:#e0f2fe,stroke:#0369a1,color:#0c4a6e
    classDef external fill:#f1f5f9,stroke:#64748b,color:#334155
    classDef optional fill:#fffbeb,stroke:#d97706,color:#92400e,stroke-dasharray:4 3
    class user,admin person
    class huntx system
    class tg,ci,cdn,clients external
    class s3 optional
```

### Level 2 — Containers

*What runtime units make up the platform?*

```mermaid
flowchart LR
    tg["Telegram sources"]

    subgraph PIPE["Ingestion plane — Python"]
        pipe["huntx pipeline<br>(src/huntx)"]
        db[("SQLite + raw store")]
    end

    subgraph GOV["Governance plane — Go"]
        engine["huntx-engine<br>parse · bench · georoute"]
        tools["huntx-tools<br>verify · manifest · site-data"]
    end

    subgraph DELIVER["Delivery plane"]
        dist[("Release artifacts<br>dist/ + manifests")]
        spa["Dashboard SPA<br>(docs/, static PWA)"]
    end

    subgraph FLEET["Optional fleet — partial"]
        daemon["huntx-daemon<br>PAC / control API"]
        probe["huntx-probe<br>TCP vantage reports"]
    end

    ci["GitHub Actions"]
    s3["S3 state"]
    cdn["GitHub Pages CDN"]
    clients["Proxy clients"]

    tg -- "raw streams" --> pipe
    pipe <-- "state · checkpoints" --> db
    pipe -- "outputs" --> dist
    engine -- "analysis commands" --> pipe
    tools -- "verify · SHA-256 catalog" --> dist
    tools -- "site-data" --> spa
    dist -. "unread telemetry" .-> daemon
    daemon <-- "reports" --> probe
    ci -- "run · verify · publish" --> PIPE
    s3 -. "restore / persist" .- ci
    ci -- "deploy" --> cdn
    spa --- cdn
    cdn -- "feeds" --> clients

    classDef container fill:#dcfce7,stroke:#15803d,color:#14532d
    classDef datastore fill:#ede9fe,stroke:#6d28d9,color:#4c1d95
    classDef external fill:#f1f5f9,stroke:#64748b,color:#334155
    classDef optional fill:#fffbeb,stroke:#d97706,color:#92400e,stroke-dasharray:4 3
    class pipe,engine,tools,spa container
    class db,dist datastore
    class tg,ci,cdn,clients external
    class daemon,probe,s3 optional
```

### Runtime — publication flow per scheduled run

*How does a run move data from backend to frontend?*

```mermaid
flowchart LR
    cron(["cron every 2 h"]) --> gate["quality gate<br>Go + Python tests"]
    gate --> restore{"Restore state"}
    restore -- "S3 configured" --> dur["restore + verify generation"]
    restore -- "no S3 keys" --> fresh["explicit fresh start"]
    dur --> runn
    fresh --> runn["ingest · build · package"]
    runn --> chk[("checkpoint artifact<br>manifest-verified")]
    chk --> persist{"Persist"}
    persist -- "S3 configured" --> ptr["advance S3 pointer"]
    persist -- "stateless" --> done["skip durable upload"]
    chk --> pages["deploy-pages<br>fresh SPA data live"]
    chk --> pub["publish workflow"]
    pub --> mirror[("main branch:<br>outputs + docs/catalog.json<br>+ docs/artifacts")]

    classDef event fill:#fef3c7,stroke:#b45309,color:#78350f
    classDef step fill:#dcfce7,stroke:#15803d,color:#14532d
    classDef decision fill:#e0f2fe,stroke:#0369a1,color:#0c4a6e
    classDef data fill:#ede9fe,stroke:#6d28d9,color:#4c1d95
    class cron event
    class gate,runn,dur,fresh,pages,pub,done step
    class restore,persist decision
    class chk,mirror data
    class ptr optional
```

The two dashed paths are the **no-cloud mode**: without any AWS/S3 configuration the production workflow starts from a verified-empty state, keeps checkpoints as run artifacts, and still ships a fresh dashboard — and the publication mirror lands both `outputs*/` and the SPA's `docs/catalog.json` + `docs/artifacts/**`, so the checked-in frontend can never lag behind the backend.
## 🚀 Quick Start

### 1. Web Dashboard (Local preview & GitHub Pages)

Open the dashboard directly in any browser:
```bash
# Option A: open the checked-in snapshot directly. Network-hosted fonts and
# utility CSS may be unavailable, so use an HTTP server for the supported view.
open docs/index.html   # macOS
xdg-open docs/index.html # Linux
start docs/index.html  # Windows

# Option B: Local HTTP server
python -m http.server 8000 --directory docs
```

### 2. Building and Running the Go Engine

```bash
# Clone the repository
git clone https://github.com/AmirrezaFarnamTaheri/HUNTX.git
cd HUNTX

# Run all test suites
go test ./...

# Build the HUNTX ingestion engine binary
go build -o bin/huntx-engine ./cmd/huntx-engine
go build -o bin/huntx-tools ./cmd/huntx-tools
```

### 3. Pipeline Ingestion Execution

```bash
# Parse a file with the engine subcommand (or pipe raw/base64 input on stdin)
./bin/huntx-engine parse --file data/raw/sources.txt
```

### 4. Run the Python production pipeline

The `huntx` command is the supported ingestion and publishing entry point. It
requires Python 3.11+, a valid configuration, and the credentials appropriate
to its configured sources and destinations. Start by building artifacts
without contacting destination channels:

```bash
python -m venv .venv
# PowerShell: .\.venv\Scripts\Activate.ps1
# POSIX: source .venv/bin/activate
pip install -e ".[dev]"

huntx --config configs/config.prod.yaml run --no-publish --no-auto-deliver
```

Set `HUNTX_SIGNING_KEY` before any workflow that signs supply-chain manifests.
Do not place Telegram tokens, signing keys, or daemon tokens in committed YAML.
See [the user guide](docs/USER_GUIDE.md) for credentials, recovery commands,
and fleet deployment prerequisites.

For fleet deployments, set `HUNTX_DAEMON_CONTROL_TOKEN`,
`HUNTX_ORCHESTRATOR_URL`, a scoped `HUNTX_PROBE_TARGETS` list, and optionally
`HUNTX_ORCHESTRATOR_BEARER_TOKEN` when the receiver expects bearer auth. The
Compose stack maps the daemon to loopback on the host and forwards probe
settings into each container; the Helm chart now requires
`daemon.controlToken`, `orchestratorUrl`, and `probeTargets` to render a
runnable probe fleet.

---

## 📂 Repository Structure

```
HUNTX/
├── cmd/
│   ├── huntx-engine/          # High-performance Go ingestion & stream engine
│   │   ├── benchmark/         # TCP/TLS latency & jitter benchmarker
│   │   ├── georoute/          # IP & GeoIP regional classification engine
│   │   ├── healing/           # Proactive node recovery daemon
│   │   ├── internal/parse/    # Protocol grammar parsers (VLESS, VMess, Trojan, SS, Hy2)
│   │   ├── stream/            # Stream tokenizer and payload isolator
│   │   └── main.go            # Engine CLI entrypoint
│   └── huntx-tools/           # Administrative utilities and manifest verifiers
│   ├── huntx-daemon/          # Authenticated local PAC/control API
│   └── huntx-probe/           # TCP vantage probe reporter
├── docs/                      # GitHub Pages Static Site & Telemetry SPA
│   ├── index.html             # Pre-rendered cyber telemetry dashboard
│   ├── C4_ARCHITECTURE.md     # Pointer to the canonical C4 model (README#architecture)
│   ├── DESIGN.md              # Master UI design tokens & accessibility specification
│   ├── DEVELOPMENT.md         # Developer guide & technical notes
│   ├── USER_GUIDE.md          # Comprehensive user manual & bot commands
│   ├── catalog.json           # SHA-256 verified artifact manifest
│   ├── artifacts/dev/         # Published proxy bundles (JSON, TXT, Base64 Sub)
│   └── assets/js/
│       ├── bundle.js          # CORS-immune standalone single-file bundle
│       ├── app.js             # Reactive UI state controller & ARIA modal manager
│       ├── data.js            # Node dataset, hub coordinates & catalog fallback
│       ├── decoder.js         # Multi-protocol client-side URI parser
│       ├── globe.js           # 3D WebGL Canvas radar engine
│       └── qrcode.js          # Standalone SVG QR code matrix generator
├── configs/                   # Production & development YAML configurations
├── data/                      # Local cache, raw inboxes, and persistent state
└── internal/                  # Shared Go packages (output verification, release manifests)
```

---

## 🛡️ Security & Privacy Model

1. **Client-Side URI Sanitization**: All proxy parameters, query arguments, and node titles are sanitized with `escapeHTML()` prior to DOM rendering, preventing stored and reflected XSS attacks.
2. **Deny-by-Default Ingestion**: Non-proxy media (images, voice notes, APKs, executables) are automatically discarded at the stream boundary.
3. **Redacted Telemetry**: Node passwords, UUIDs, and private keys are never logged or transmitted to third-party analytics services.
4. **Control-plane boundary**: The daemon binds to `127.0.0.1:9090` by default. Its state-changing `POST /rotate` endpoint requires `Authorization: Bearer <HUNTX_DAEMON_CONTROL_TOKEN>`; do not expose it through an unauthenticated reverse proxy.
5. **Probe receiver boundary**: Probe agents only originate TCP checks and POST JSON. They do not host a collector; point them at a private receiver URL and use `ORCHESTRATOR_BEARER_TOKEN` when that receiver requires bearer auth.
6. **Privacy boundary**: HUNTX does not include analytics beacons or cookies. The checked-in dashboard currently references CDN-hosted fonts and utility CSS; serve it over HTTP for the supported experience or replace those assets with locally bundled equivalents before claiming fully offline use.

---

## 📜 License

MIT License. See [LICENSE](LICENSE) for details.
