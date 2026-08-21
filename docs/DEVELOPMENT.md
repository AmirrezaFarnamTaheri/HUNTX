# HUNTX Development & Architecture Guide

## 1. System Overview

HUNTX (GatherX) is composed of three core subsystems:

1. **High-Performance Go Ingestion Daemon (`cmd/huntx-engine`)**: Stream parser, GeoRoute engine, benchmark runner, and healing daemon.
2. **Python Ingestion & Bot Pipeline (`src/huntx/`)**: MTProto/Bot API connectors, format normalization, and GatherX Telegram bot.
3. **Cyber Telemetry SPA (`docs/`)**: Offline-first (`file:///` compliant) 3D WebGL radar, protocol decoder, and artifact manifest.

---

## 2. Directory Layout

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
├── src/huntx/                 # Python pipeline & GatherX bot
│   ├── bot/                   # GatherX Telegram bot (interactive commands)
│   ├── cli/                   # Python CLI entry points
│   ├── config/                # YAML configuration loader & validator
│   ├── connectors/            # Telegram Bot API & MTProto connectors
│   ├── core/                  # Orchestration, locking, and routing
│   ├── formats/               # Format handlers (npvt, ovpn, conf_lines, etc.)
│   ├── pipeline/              # Ingest, transform, build, and publish stages
│   └── state/                 # SQLite WAL state database repository
├── docs/                      # GitHub Pages static dashboard & documentation
│   ├── index.html             # Master pre-rendered cyber telemetry dashboard
│   ├── architecture.html      # Interactive 3D isometric system topology map
│   ├── C4_ARCHITECTURE.md     # Formal C4 architecture model document
│   ├── DESIGN.md              # Master UI design tokens & accessibility specification
│   ├── DEVELOPMENT.md         # This development guide
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

## 3. Development Setup & Verification

### Go Engine Setup

```bash
# Verify Go version (Go 1.24 recommended)
go version

# Run all Go unit and integration tests
go test ./...

# Build Go engine and tools
go build -o bin/huntx-engine ./cmd/huntx-engine
go build -o bin/huntx-tools ./cmd/huntx-tools
```

### Python Pipeline Setup

```bash
python -m venv .venv
source .venv/bin/activate  # or .venv\Scripts\activate on Windows
pip install -e .
pip install pytest black flake8 mypy

# Run Python test suite
pytest tests/ -v

# Run linting and type checks
flake8 src/ tests/ --max-line-length 120
mypy src/ --ignore-missing-imports
```

### Frontend Telemetry SPA Verification

```bash
# Verify JS ES modules in Node.js
node -e "
(async () => {
  const fs = require('fs');
  const path = require('path');
  const dir = 'docs/assets/js';
  for (const f of fs.readdirSync(dir).filter(f => f.endsWith('.js') && f !== 'bundle.js')) {
    const mod = await import('file:///' + path.resolve(dir, f).replace(/\\\\/g, '/'));
    console.log('[PASS]', f, Object.keys(mod));
  }
})();
"

# Test local web server
python -m http.server 8000 --directory docs
```

---

## 4. Architectural Invariants

1. **Zero-Dependency Frontend Resilience**: The web UI must operate seamlessly when double-clicked locally (`file:///` protocol) as well as over HTTP/HTTPS. All CSS tokens and core scripts must be bundled and CORS-immune.
2. **Deterministic SHA-256 Content Hashing**: Duplicate proxy configurations from multiple channels are identified and collapsed using cryptographic fingerprinting of normalized parameters.
3. **Strict Output Sanitization**: Any external string, node label, or URL query parameter rendered to the DOM must pass through `escapeHTML()`.
4. **Resilience Dispositions**: Execution outcomes follow the formal tri-state health model: `success`, `degraded`, or `fatal` (see [`RUN_HEALTH.md`](RUN_HEALTH.md)).
5. **Atomic Storage**: All artifact and SQLite disk writes use atomic temporary-file replacement (`os.replace`) to prevent state corruption during process interruption.

---

## 5. Adding New Features

### Adding a New Proxy Protocol
1. **Frontend Decoder**: Update [`docs/assets/js/decoder.js`](assets/js/decoder.js) with parser logic and safe fallback handling.
2. **Go Protocol Parser**: Update [`cmd/huntx-engine/internal/parse/parse.go`](../cmd/huntx-engine/internal/parse/parse.go) with grammar rules.
3. **Python Pipeline**: Add scheme to `src/huntx/formats/npvt.py` and `src/huntx/pipeline/build.py`.
4. **Re-Bundle Frontend**: Rebuild `docs/assets/js/bundle.js` and run automated module tests.

### Adding a New Source Connector
1. Implement the `SourceConnector` protocol in `src/huntx/connectors/base.py`.
2. Register configuration schema in `src/huntx/config/schema.py`.
3. Add worker lifecycle handling in `src/huntx/core/orchestrator.py`.
4. Add unit test coverage in `tests/test_connectors.py`.
