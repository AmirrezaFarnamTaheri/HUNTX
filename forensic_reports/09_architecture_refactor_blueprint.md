# HUNTX — Architecture Refactor Blueprint
# Report 09: From Monkey-Patched Orchestrator to Production-Grade System

**Generated:** 2026-08-17
**Lenses applied:** `/expert-tech-architect`, `/elite-database-architect`, `/elite-frontend-architect`, `/ecc-backend-patterns`, `/golang-design-patterns`, `/golang-dependency-management`, `/expert-product-owner`, `/expert-dev`
**Scope:** The full production execution path — from `hardened_main.py` import-time patching through to the Go release plane, with the dead next-gen infrastructure as the migration target.

> **Intent:** This document does NOT prescribe a big-bang rewrite. It prescribes a **strangler-fig migration** — wire the dead infrastructure one gate at a time, with each step fully tested and independently deployable. Every phase must ship with green CI.

---

## §1. Current architecture (as-found, evidence-verified)

```
┌─────────────────────────────────────────────────────────────────────┐
│  Python: Production execution path (verified @ main:8ffd830)        │
│                                                                     │
│  CI cron (every 2h)                                                 │
│    └── python -m huntx.core.hardened_main                           │
│          ├── IMPORT-TIME: installs 6 monkey-patches                 │
│          │     ├── install_runtime_resilience()     ─┐              │
│          │     ├── install_health_check_server()      │ 6 patches  │
│          │     ├── install_watchdog_monitor()          │ executed   │
│          │     ├── install_checkpoint_manager()        │ on import  │
│          │     ├── install_adaptive_executor()       ─┘              │
│          │     └── install_rate_limited_api()                        │
│          └── calls: from huntx.core.main import run_orchestrator()  │
│                        (FROZEN "core" orchestrator, unchanged)       │
│                                                                     │
│  Database: SQLite (single file, WAL mode, NO connection pooling)     │
│  Raw store: Files sharded by hash prefix                            │
│  Bot: Telethon + python-telegram-bot (both live simultaneously)     │
│  Formats: 10 live parsers, 2 stub parsers (nm, slipnet)             │
│  Publishing: 3 routes (telegram, file, subscription endpoint)        │
└─────────────────────────────────────────────────────────────────────┘
                        │
                        ▼
┌─────────────────────────────────────────────────────────────────────┐
│  Go: Release plane (verified @ main:8ffd830)                        │
│                                                                     │
│  python -m huntx.core.hardened_main → (on success)                 │
│    └── ./huntx-tools generateOutputs                                │
│          ├── internal/runtimegen  — builds all output formats        │
│          ├── internal/sitegen     — generates index.html + catalog  │
│          ├── internal/releasemanifest — writes manifest.json        │
│          └── internal/outputverify   — verifies output integrity    │
└─────────────────────────────────────────────────────────────────────┘
```

### 1.1 Architecture defects (verified)

| Defect | Location | Impact |
|---|---|---|
| Import-time side effects (6 monkey-patches) | `hardened_main.py:1-80` | Untestable in isolation; ordering-dependent; invisible to type-checker |
| Duplicate bot clients | `bot/interactive.py` (Telethon) + `bot/polling.py` (PTB) | Race conditions on shared state; double-handling of some events |
| Schema DDL duplicated in 3 files | `interactive.py`, `cli/main.py`, `state/repo.py` | H-1 was caused by schema drift between these copies |
| Dead next-gen infrastructure | `UnifiedOrchestrator`, `GeoRoutingEngine`, `SelfHealingDaemon`, etc. | Green tests, zero prod callers → false confidence + maintenance trap |
| upsert_record_verdict: 0 callers | `state/verdict_store.py` | H-4: `secure` tier silently dead |
| Go test coverage: 0% live packages | `cmd/huntx-tools/`, `internal/` | H-8: release plane unguarded |

---

## §2. Migration strategy: strangler-fig phases

The strangler-fig pattern applies a thin adapter at each integration point. The existing orchestrator stays untouched; new components are wired at the boundary and promoted one at a time.

### Phase 0 (Wave 1 — NOW): Schema single-source-of-truth

**Goal:** Eliminate schema drift (root cause of H-1).

```
src/huntx/bot/
  schema_constants.py      ← NEW: authoritative DDL constants
  interactive.py           ← MODIFY: import schema_constants
cli/
  main.py                  ← MODIFY: import schema_constants (fixes H-1)
state/
  repo.py                  ← MODIFY: import schema_constants
```

```python
# src/huntx/bot/schema_constants.py
BOT_USERS_DDL = """
    CREATE TABLE IF NOT EXISTS bot_users (
        user_id             TEXT    PRIMARY KEY,
        chat_id             TEXT    NOT NULL,
        username            TEXT,
        registered_at       REAL    NOT NULL,
        muted               INTEGER DEFAULT 0,
        last_delivered_at   REAL    DEFAULT 0,
        default_format      TEXT    DEFAULT 'npvt',
        approved            INTEGER NOT NULL DEFAULT 0
    )
"""

SEEN_FILES_DDL = """
    CREATE TABLE IF NOT EXISTS seen_files (
        id          INTEGER PRIMARY KEY AUTOINCREMENT,
        source_id   TEXT    NOT NULL,
        external_id TEXT    NOT NULL,
        raw_hash    TEXT    NOT NULL,
        status      TEXT    NOT NULL DEFAULT 'pending',
        processed_at REAL,
        UNIQUE(source_id, external_id)
    )
"""

BOT_USERS_SCHEMA_VERSION = 3  # increment when schema changes; triggers migration check
```

**CI drift-check (add to `test_schema_drift.py`):**

```python
import sqlite3
from huntx.bot.schema_constants import BOT_USERS_DDL, BOT_USERS_SCHEMA_VERSION


def test_bot_users_schema_matches_across_all_modules(tmp_path):
    """Schema drift guard: all modules must use the same DDL constant."""
    # Any deviation in import path shows that a module has a local DDL copy
    from huntx.cli.main import _restore_bot_users
    from huntx.bot.interactive import _create_db_schema
    
    db1 = str(tmp_path / "a.db")
    db2 = str(tmp_path / "b.db")
    
    _restore_bot_users(db1, [])
    _create_db_schema(db2)
    
    def get_cols(db):
        with sqlite3.connect(db) as conn:
            return {r[1] for r in conn.execute("PRAGMA table_info(bot_users)")}
    
    assert get_cols(db1) == get_cols(db2), (
        "Schema drift detected: cli/main.py and bot/interactive.py create different bot_users schemas."
    )
```

---

### Phase 1 (Wave 2): Inline the monkey-patches — dependency injection

**Goal:** Replace import-time side effects with explicit dependency injection.

**Current problematic pattern:**
```python
# hardened_main.py (current — BAD):
from huntx.core.hardened_orchestrator import (
    install_runtime_resilience,   # side effect on import
    install_health_check_server,  # side effect on import
    ...
)
install_runtime_resilience()   # modifies globals
install_health_check_server()
...
run_orchestrator()             # now depends on those globals
```

**Target pattern:**
```python
# hardened_main.py (target — GOOD):
from huntx.core.hardened_orchestrator import HardenedOrchestrator

def main() -> int:
    cfg = load_config()
    orch = HardenedOrchestrator.from_config(cfg)  # explicit, injectable, testable
    return orch.run()

if __name__ == "__main__":
    raise SystemExit(main())
```

**Strangler adapter (intermediate step, zero risk):**
```python
# src/huntx/core/harness.py  (NEW FILE — thin wrapper)
"""
Harness: provides explicit construction of the runtime resilience stack.
Replaces the import-time monkey-patching without changing the frozen core.
"""
from dataclasses import dataclass, field
from typing import Callable


@dataclass
class RuntimeHarness:
    """Explicit, injectable container for all runtime-patched capabilities."""
    resilience:   Callable | None = None
    health_check: Callable | None = None
    watchdog:     Callable | None = None
    checkpoint:   Callable | None = None
    executor:     Callable | None = None
    rate_limiter: Callable | None = None

    def install(self) -> None:
        """Install all registered capabilities in deterministic order."""
        for name, fn in (
            ("resilience",   self.resilience),
            ("health_check", self.health_check),
            ("watchdog",     self.watchdog),
            ("checkpoint",   self.checkpoint),
            ("executor",     self.executor),
            ("rate_limiter", self.rate_limiter),
        ):
            if fn is not None:
                fn()

    @classmethod
    def production(cls) -> "RuntimeHarness":
        from huntx.core.hardened_orchestrator import (
            install_runtime_resilience,
            install_health_check_server,
            install_watchdog_monitor,
            install_checkpoint_manager,
            install_adaptive_executor,
            install_rate_limited_api,
        )
        return cls(
            resilience=install_runtime_resilience,
            health_check=install_health_check_server,
            watchdog=install_watchdog_monitor,
            checkpoint=install_checkpoint_manager,
            executor=install_adaptive_executor,
            rate_limiter=install_rate_limited_api,
        )

    @classmethod
    def test_mode(cls) -> "RuntimeHarness":
        """No-op harness for unit tests — zero side effects."""
        return cls()
```

**Test for the harness:**
```python
# tests/test_runtime_harness.py
def test_harness_test_mode_has_no_side_effects():
    from huntx.core.harness import RuntimeHarness
    harness = RuntimeHarness.test_mode()
    harness.install()  # must not raise, must not modify any globals

def test_harness_production_mode_constructs():
    from huntx.core.harness import RuntimeHarness
    harness = RuntimeHarness.production()
    assert harness.resilience is not None
    assert harness.rate_limiter is not None
```

---

### Phase 2 (Wave 3): Wire UnifiedOrchestrator as an A/B flag

**Goal:** Graduate the validated `UnifiedOrchestrator` from dead code to a feature-flag-gated production path.

**Feature flag:**
```python
# src/huntx/config/schema.py — add to OrchestratorConfig:
@dataclass
class OrchestratorConfig:
    use_unified: bool = False  # default: legacy path; set to true to activate next-gen
```

**Gating logic (thin adapter in main entry point):**
```python
# src/huntx/core/harness.py — add:
def make_orchestrator(cfg: OrchestratorConfig, harness: RuntimeHarness):
    if cfg.use_unified:
        from huntx.core.unified_orchestrator import UnifiedOrchestrator
        return UnifiedOrchestrator(cfg)
    else:
        harness.install()
        from huntx.core.main import run_orchestrator
        return LegacyOrchestratorAdapter(run_orchestrator)
```

**Acceptance criterion:** With `use_unified: false` (default), behavior is identical to today. With `use_unified: true`, the CI `real-investigation-gate` passes with the same markers.

---

### Phase 3 (Wave 4): Activate LatencyBenchmarker and wire ProbeVerdict

**Goal:** Connect the validated but dead observability stack to the live execution path.

```python
# src/huntx/core/main.py — after collection, before publishing:
from huntx.core.latency_benchmarker import LatencyBenchmarker

if cfg.observability.enable_latency_benchmarking:
    benchmarker = LatencyBenchmarker()
    proxy_results = await benchmarker.run(proxies, timeout=cfg.observability.probe_timeout_s)
    # Results feed into SyntaxVerdict / ProbeVerdict
    await upsert_record_verdicts(repo, proxy_results)  # H-4 fix wire-up
```

---

### Phase 4 (Wave 5): Bot architecture consolidation

**Goal:** Eliminate the dual-client race condition (Telethon + PTB simultaneously).

**Current state (DEFECT):**
```
bot/interactive.py    → Telethon client for admin commands
bot/polling.py        → PTB client for user commands
Both listen on the same bot token → message routing is non-deterministic
```

**Target state:**
```
bot/interactive.py    → SINGLE Telethon client for ALL commands
                         (admin commands kept; user commands migrated)
bot/polling.py        → DEPRECATED → removed (PTB dependency removed)
```

**Migration path:**
1. Add all PTB handler logic to `interactive.py` under the Telethon event system.
2. Add feature flag: `use_ptb_polling: false` in `BotConfig`.
3. When `use_ptb_polling: false`, skip `polling.py` startup in `run_orchestrator`.
4. Once stable for 2 weeks, remove `polling.py` and `python-telegram-bot` dependency.

---

## §3. Database architecture recommendations

### 3.1 Schema versioning

Add a `schema_versions` table to track migrations:

```python
SCHEMA_VERSIONS_DDL = """
    CREATE TABLE IF NOT EXISTS schema_versions (
        version     INTEGER PRIMARY KEY,
        applied_at  REAL    NOT NULL,
        description TEXT    NOT NULL
    )
"""
```

On startup:
```python
def ensure_schema(conn: sqlite3.Connection, target_version: int) -> None:
    current = conn.execute(
        "SELECT COALESCE(MAX(version), 0) FROM schema_versions"
    ).fetchone()[0]
    for v in range(current + 1, target_version + 1):
        MIGRATIONS[v](conn)
        conn.execute(
            "INSERT INTO schema_versions VALUES (?, ?, ?)",
            (v, time.time(), MIGRATION_DESCRIPTIONS[v])
        )
    conn.commit()
```

**Current migrations to implement:**

| Version | Change |
|---|---|
| v1 | Initial schema (seen_files + bot_users without approved) |
| v2 | Add `approved INTEGER NOT NULL DEFAULT 0` to bot_users |
| v3 | Add `source_lifecycle` table |
| v4 | Add `schema_versions` table itself (bootstrapped) |

### 3.2 Connection pooling (medium-term)

SQLite WAL mode supports concurrent reads. Add a connection pool adapter:

```python
# src/huntx/state/connection_pool.py  (NEW FILE)
from contextlib import contextmanager
import queue, sqlite3, threading


class SQLitePool:
    """Thread-safe SQLite connection pool for WAL-mode databases."""
    
    def __init__(self, db_path: str, pool_size: int = 4):
        self._pool: queue.Queue[sqlite3.Connection] = queue.Queue(maxsize=pool_size)
        for _ in range(pool_size):
            conn = sqlite3.connect(db_path, check_same_thread=False)
            conn.execute("PRAGMA journal_mode=WAL")
            conn.execute("PRAGMA synchronous=NORMAL")
            conn.row_factory = sqlite3.Row
            self._pool.put(conn)
    
    @contextmanager
    def acquire(self, timeout: float = 5.0):
        try:
            conn = self._pool.get(timeout=timeout)
        except queue.Empty:
            raise RuntimeError("SQLite pool exhausted after {timeout}s")
        try:
            yield conn
        finally:
            self._pool.put(conn)
```

### 3.3 Dangerous cleanup operations — authorization pattern

All operations that bulk-delete data (CLI `clean`, `reset`, `prune`) must follow a two-step authorization pattern:

```python
def _cmd_clean(args) -> int:
    # Step 1: Show blast radius
    stats = repo.count_records_and_users()
    print(f"⚠️  CLEAN will wipe:")
    print(f"   {stats['records']:,} records")
    print(f"   {stats['bot_users']:,} bot subscribers")
    print(f"   {stats['raw_blobs']:,} raw blobs")
    
    # Step 2: Require explicit confirmation (or --yes flag with warning)
    if not args.yes:
        confirm = input("Type 'CONFIRM' to proceed: ")
        if confirm != "CONFIRM":
            print("Aborted.")
            return 1
    
    # Step 3: Backup
    backup = _backup_bot_users(args.db_path)
    
    # Step 4: Execute with error handling
    try:
        _perform_clean(args)
    except Exception as e:
        print(f"Clean failed: {e}. Attempting restore...")
        _restore_bot_users(args.db_path, backup)
        raise
    
    return 0
```

---

## §4. Format handler architecture (evidence-based findings)

### 4.1 Handler registry pattern (current vs. target)

**Current (implicit, by file):**
```python
# Each format is imported by name in the routes config
# "npvt" → huntx.formats.npvt → NpvtHandler
# This mapping is undocumented and lives only in the config loader
```

**Target (explicit registry):**
```python
# src/huntx/formats/registry.py
from typing import Type
from huntx.formats.base import BaseFormatHandler

_REGISTRY: dict[str, Type[BaseFormatHandler]] = {}


def register(name: str):
    def decorator(cls: Type[BaseFormatHandler]):
        _REGISTRY[name] = cls
        return cls
    return decorator


def get_handler(name: str) -> Type[BaseFormatHandler]:
    if name not in _REGISTRY:
        raise KeyError(f"Unknown format handler: {name!r}. Registered: {list(_REGISTRY)}")
    return _REGISTRY[name]


def list_handlers() -> list[str]:
    return sorted(_REGISTRY.keys())


# Usage — in each format file:
@register("npvt")
class NpvtHandler(BaseFormatHandler):
    ...
```

**Config validator addition:**
```python
# validate_config checks every format name in every route:
for route in config.routes:
    for fmt in route.formats:
        try:
            handler_cls = get_handler(fmt)
        except KeyError as e:
            raise ConfigurationError(str(e))
        # Verify build() is implemented (not stub):
        import inspect
        if getattr(handler_cls.build, "__isabstractmethod__", False):
            raise ConfigurationError(
                f"Route '{route.name}' uses format '{fmt}' whose build() is not implemented."
            )
```

### 4.2 Stub handler excision (M-1 and slipnet)

Routes with unimplemented `build()` must raise `ConfigurationError` at validation time (not silently produce empty output at runtime). The validator above implements this. The `nm` and `slipnet` handlers stay in the source tree but cannot be included in routes until their `build()` is implemented.

---

## §5. Observability architecture

### 5.1 Structured logging (current gap)

Current logging uses `print()` and `logging.basicConfig()` with no structured output. Adding structured JSON logs enables monitoring:

```python
# src/huntx/core/logging.py  (NEW FILE — thin adapter)
import json, logging, time
from dataclasses import dataclass, asdict


@dataclass
class RunEvent:
    event: str
    run_id: str
    timestamp: float = 0.0
    sources_processed: int = 0
    records_added: int = 0
    formats_published: int = 0
    error: str | None = None

    def __post_init__(self):
        if not self.timestamp:
            self.timestamp = time.time()


def emit(event: RunEvent) -> None:
    """Emit a structured log line. Parseable by CloudWatch/Datadog/Loki."""
    print(json.dumps(asdict(event)), flush=True)
```

### 5.2 `run-summary.json` envelope verification

The CI real-investigation gate already verifies `run-summary.json`. Extend the verification to assert the envelope structure:

```python
# tests/test_run_summary_schema.py  (NEW FILE)
import json, pathlib


def test_run_summary_has_required_fields_if_present():
    """CI quality gate: if run-summary.json exists, validate its schema."""
    p = pathlib.Path("run-summary.json")
    if not p.exists():
        return  # not generated in unit-test runs

    with p.open() as f:
        summary = json.load(f)

    required = {"run_id", "started_at", "completed_at", "status", "sources_processed"}
    missing = required - summary.keys()
    assert not missing, f"run-summary.json missing fields: {missing}"
    assert summary["status"] in {"success", "partial", "failure"}, (
        f"Unexpected run status: {summary['status']!r}"
    )
```

---

## §6. Migration risk matrix

| Phase | Risk level | Rollback mechanism | Gate |
|---|---|---|---|
| Phase 0: Schema SSoT | **Low** — additive refactor | `git revert` on schema_constants.py | `test_schema_drift.py` GREEN |
| Phase 1: Inline patches via harness | **Medium** — behavior must be identical | Feature flag `use_harness: false` falls back to direct imports | 3 consecutive green CI runs |
| Phase 2: UnifiedOrchestrator flag | **Medium** — new code path | `use_unified: false` restores legacy path | `real-investigation-gate` passes on both paths |
| Phase 3: Observability wire-up | **Low** — additive | `enable_latency_benchmarking: false` disables | `test_secure_tier_not_silent.py` GREEN |
| Phase 4: Bot consolidation | **High** — removes PTB dependency | `use_ptb_polling: true` re-enables PTB for 2-week grace | No PTB-specific events lost for 1 week |

---

## §7. Documentation architecture (from report 06 gaps)

| Missing doc | Content required | Owner wave |
|---|---|---|
| `docs/architecture/system-overview.md` | Diagram in §1 of this report + dependency map | Wave 5 |
| `docs/runbooks/bot_approval.md` | How to run `/approve`, `/deny`, `/pending`; how to query `bot_users` directly | Wave 1 (before H-2 fix ships) |
| `docs/runbooks/disaster_recovery.md` | Full data loss scenario; how to restore from backup; what `clean`/`reset` does | Wave 2 |
| `docs/reference/env_vars.md` | Complete environment variable reference (all `HUNTX_*` vars, CI secrets) | Wave 2 |
| `docs/formats/catalog.md` | Per-format: parse → validate → build lifecycle, known credentials, test fixtures | Wave 3 |
| `CHANGELOG.md` | Structured changelog (ConventionalCommits format) populated from PR history | Wave 5 |
| `CONTRIBUTING.md` | Dev setup, test running instructions, PR checklist | Wave 5 |

---

## §8. North-star architecture (Wave 5+ target)

```
huntx v2.0 (target state after all 5 waves):

  CI (every 2h)
    └── python -m huntx.core.main  ← No monkey-patching; explicit DI
          ├── HardenedOrchestrator
          │     ├── Source collection (85 channels)
          │     ├── Format parsing (10 handlers, registry-validated)
          │     ├── URI validation (npvt + npvtsub unified)
          │     ├── Deduplication (hash-based, raw store)
          │     ├── [NEW] LatencyBenchmarker → ProbeVerdict
          │     ├── Schema-versioned SQLite (WAL, connection pool)
          │     └── Publishing (3 routes, secure-tier excised until complete)
          └── SIGTERM → clean shutdown via context propagation

  Bot (always-on)
    └── bot/interactive.py  ← Single Telethon client
          ├── Admin commands: /approve, /deny, /pending, /prune, /status
          └── User commands: /start, /stop, /format, /count, /ping (all rate-limited)

  Go release plane
    └── ./huntx-tools generateOutputs
          ├── internal/runtimegen   (tested, context-aware)
          ├── internal/sitegen      (tested, context-aware)
          ├── internal/releasemanifest (tested, deterministic)
          └── internal/outputverify    (tested, enforces non-empty)

  CI gates
    ├── Python: 500+ tests, mypy strict, flake8, secret scan
    ├── Go: go vet + go test -race + golangci-lint (all live packages)
    └── Integration: real-investigation-gate (anti-fake markers)
```
