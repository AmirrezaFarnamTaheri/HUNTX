# Technology Stack: HuntX

## Core Runtimes & Languages

- **Python 3.11+** — primary ingestion, transformation, build/publish pipeline, GatherX bot, and CLI runtime.
- **Go 1.23.1** — repository-root toolchain for `huntx-tools`, the standalone `huntx-engine`, and the V2Ray collector package invoked by its Python connector when configured.

## Frameworks & Core Libraries

- **Telethon 1.42+** — Telegram MTProto user-client ingestion and GatherX bot transport.
- **Pydantic 2.x** — configuration validation and source/publication policy modeling.
- **PyYAML 6.x** — YAML configuration parsing.
- **cryptography / PyAES / RSA** — format-specific cryptography and dependency support; operational secrets are supplied through environment/configuration rather than repository fallback values.

## Persistence & Storage

- **SQLite (WAL + `synchronous=FULL`)** — canonical embedded state store for observations, normalized records, source cursors, durable ingestion work/leases, publication intent/delivery state, Telegram Bot API inbox state, and GatherX users/delivery checkpoints. The default location is `data/state/state.db` and can be overridden by `HUNTX_STATE_DB_PATH`.
- **Content-addressed raw store** — SHA-256-addressed source blobs under `data/raw/`.
- **Artifact/output stores** — immutable internal artifacts plus current/cumulative generated products under runtime `data/` paths. Repository mirrors in `outputs/` and `outputs_dev/` are generated distribution surfaces, not runtime source code.
- **Optional S3 immutable generations** — the production workflow can restore and persist verified checkpoint generations through a manifest/pointer protocol when an S3 bucket is configured.

The former tracked `data_archive/` snapshot directory was legacy generated ballast and is no longer part of the live repository or runtime storage model.

## Testing & Code Quality

- **Pytest / pytest-asyncio** — unit, integration, regression, lifecycle, and policy tests.
- **Mypy** — static Python type validation.
- **Flake8** — enforced Python lint gate.
- **Black** — developer formatter configuration (line length 120); CI additionally compiles all Python source/tests/scripts.
- **Go test with race detector / go vet / gofmt** — repository-root Go quality gates.

Runtime Python dependencies are hash-pinned in `requirements.txt`; CI tooling is exact-version pinned in `requirements-ci.txt`.

## Infrastructure & CI/CD

- **GitHub Actions** — PR validation plus the two-hour `huntx-production` control plane for quality gating, optional state restore, bounded runtime execution, output verification, checkpoint packaging, diagnostics, optional S3 persistence, and Pages deployment.
- **Generated-output publication workflow** — consumes a successful production run, assembles a verified snapshot, updates the dedicated `generated-outputs` branch, and mirrors the intended generated files into `main/outputs` and `main/outputs_dev`.
- **GitHub Pages** — deploys the verified static catalog generated from production output.
- **AWS S3 (optional)** — immutable state-generation persistence; runs remain stateless/ephemeral when no bucket is configured.

## Runtime Shape

HUNTX is primarily a **single governed Python application**, not a microservice fleet. Production construction is centralized in `huntx.core.runtime_factory.create_production_orchestrator`; CLI and bot-admin run entrypoints delegate to the shared run service so source governance, durable window ingestion, governed build policy, output ownership, locking, and health reporting cannot drift by caller.
