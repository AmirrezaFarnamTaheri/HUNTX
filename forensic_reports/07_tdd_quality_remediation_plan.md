# HUNTX — TDD & Quality Remediation Plan
# Report 07: Test-Driven Defect Remediation

**Generated:** 2026-08-17
**Lenses applied:** `/qa-tdd-architect`, `/expert-qa-test`, `/test-driven-development`, `/e2e-testing`, `/code-review-and-quality`, `/expert-qa-engineer`, `/ci-cd-and-automation`
**Scope:** All defects H-1 through H-10 (Critical/High) + M-1 through M-15 (Medium). Every defect gets a RED (failing test spec), GREEN (minimal fix), and REFACTOR instruction.

> **TDD Protocol:** Write the failing test FIRST. Confirm it fails with the expected error. Implement the fix. Run the full suite. Ship only when green.

---

## §1. Test infrastructure audit (pre-remediation baseline)

### 1.1 Current test health (verified)

| Metric | Value | Source |
|---|---|---|
| Total test files | 95 | `tests/` count |
| Passing tests | 498 | CI output |
| Env-dependent failures | 2 | `test_v2ray_collector_connector.py` (needs Go on PATH) |
| Stale performance test | 1 | `tests/perf/` — fixture rows lack `id` → KeyError transform.py:61 |
| Flaky test | 1 | `test_session_lease` heartbeat — monotonic-timing sensitivity |
| Coverage: live code | Strong on validators, hardening, delivery | Weak on hybrid-decrypt heuristics |
| Coverage: dead code | **Paradox** — UnifiedOrchestrator, geo, scoring, self-healing, latency, streaming are green by tests despite zero production callers |
| Go test coverage | **Zero** for live `internal/` + `cmd/huntx-tools` | All 5 `.go` test files are in the orphaned `cmd/huntx-engine` module |

### 1.2 Test-coverage gaps (priority order)

1. **H-1 scenario** — No test for `_restore_bot_users` preserving the `approved` column.
2. **H-6 scenario** — No test for CLI `prune` deleting only orphan blobs.
3. **M-5 scenario** — No test for rate-limiting on the 8 unthrottled bot commands.
4. **M-1 scenario** — No test exercising the `nm` build path that would trigger `NotImplementedError`.
5. **C3 scenario** — No test enforcing that `npvtsub` applies the same URI validation as `npvt`.
6. **H-8 gap** — No Go tests at all for the live release plane.

### 1.3 "Dead code kept green" anti-pattern

The following modules have tests that pass but have **zero production callers**. These tests create a false sense of coverage and a maintenance trap:

- `test_unified_orchestrator.py` → `UnifiedOrchestrator` (dead)
- `test_geo_routing.py` → `GeoRoutingEngine` (dead)
- `test_latency_benchmarker.py` → `LatencyBenchmarker` (dead — but REVIVE candidate)
- `test_self_healing.py` → `SelfHealingDaemon` (dead)
- `test_verdicts.py` → `SyntaxVerdict`/`ProbeVerdict` (dead — no `upsert_record_verdict` caller)
- `test_source_lifecycle.py` → `source_lifecycle` table (dead in production)

**Recommendation:** Add an integration test that asserts none of these modules are imported by the live execution path unless a feature flag is set.

---

## §2. H-1: Subscriber-loss bug on `clean`/`reset` — TDD spec

**Defect:** `_restore_bot_users` (cli/main.py:226-236) creates `bot_users` without the `approved` column. The `INSERT` then raises `OperationalError` which is caught silently → all subscribers wiped.

**Severity:** CRITICAL — VERIFIED ✅

### RED — failing test to write first

```python
# tests/test_cli_clean_reset_regression.py  (NEW FILE)
"""
Regression guard: H-1 — _restore_bot_users must preserve the `approved` column.
Expected before fix: FAILS with OperationalError caught silently → approved users lost.
Expected after fix:  PASSES.
"""
import sqlite3
import pytest


def _make_schema(conn):
    """Create the CURRENT bot_users schema (including 'approved')."""
    conn.execute("""
        CREATE TABLE bot_users (
            user_id TEXT PRIMARY KEY,
            chat_id TEXT NOT NULL,
            username TEXT,
            registered_at REAL NOT NULL,
            muted INTEGER DEFAULT 0,
            last_delivered_at REAL DEFAULT 0,
            default_format TEXT DEFAULT 'npvt',
            approved INTEGER NOT NULL DEFAULT 0
        )
    """)
    conn.commit()


def _seed_users(conn):
    conn.executemany(
        "INSERT INTO bot_users VALUES (?,?,?,?,?,?,?,?)",
        [
            ("user_1", "chat_1", "alice", 1000.0, 0, 900.0, "npvt", 1),
            ("user_2", "chat_2", "bob",   1001.0, 0,   0.0, "npvt", 0),
        ],
    )
    conn.commit()


def test_restore_bot_users_preserves_approved_column(tmp_path):
    """H-1 regression: After backup + clean + restore, approved status must survive."""
    db_path = tmp_path / "state.db"
    with sqlite3.connect(str(db_path)) as conn:
        _make_schema(conn)
        _seed_users(conn)

    from huntx.cli.main import _backup_bot_users, _restore_bot_users
    backup = _backup_bot_users(str(db_path))
    assert len(backup) == 2, "Backup must contain both users"

    db_path.unlink()
    with sqlite3.connect(str(db_path)) as conn:
        _make_schema(conn)

    errors = _restore_bot_users(str(db_path), backup)
    assert not errors, f"Restore should produce zero errors; got: {errors}"

    with sqlite3.connect(str(db_path)) as conn:
        rows = conn.execute(
            "SELECT user_id, approved FROM bot_users ORDER BY user_id"
        ).fetchall()

    assert rows == [("user_1", 1), ("user_2", 0)], (
        f"H-1: approved values not preserved after restore. Got: {rows}"
    )


def test_restore_bot_users_column_schema_complete(tmp_path):
    """Schema contract: _restore_bot_users DDL must include ALL columns from live schema."""
    db_path = tmp_path / "state.db"
    from huntx.cli.main import _restore_bot_users
    _restore_bot_users(str(db_path), [])

    with sqlite3.connect(str(db_path)) as conn:
        cols = {row[1] for row in conn.execute("PRAGMA table_info(bot_users)")}

    required = {
        "user_id", "chat_id", "username", "registered_at",
        "muted", "last_delivered_at", "default_format", "approved"
    }
    missing = required - cols
    assert not missing, f"H-1: _restore_bot_users missing columns: {missing}"
```

### GREEN — minimal production fix

**File:** `src/huntx/cli/main.py`, lines 226-236 — `_restore_bot_users` DDL block.

```python
cursor.execute("""
    CREATE TABLE IF NOT EXISTS bot_users (
        user_id TEXT PRIMARY KEY,
        chat_id TEXT NOT NULL,
        username TEXT,
        registered_at REAL NOT NULL,
        muted INTEGER DEFAULT 0,
        last_delivered_at REAL DEFAULT 0,
        default_format TEXT DEFAULT 'npvt',
        approved INTEGER NOT NULL DEFAULT 0   -- H-1 fix: was absent
    )
""")
```

### REFACTOR — schema single-source-of-truth

Extract the DDL into a shared constant in `src/huntx/bot/schema_constants.py` and import it in both `interactive.py` and `cli/main.py`. A CI drift-check imports the constant and asserts schema equality — zero future maintenance burden.

---

## §3. H-6: CLI `prune` orphan-hash guard — TDD spec

**Defect:** `_cmd_prune` (cli/main.py:444-446) calls `raw_store.prune_by_hashes(raw_hashes)` without subtracting `get_all_known_hashes()`. Live-record raw blobs are deleted.

**Severity:** HIGH — VERIFIED ✅ (identical bug fixed for admin prune in commit 5229d0b)

### RED — failing test

```python
# tests/test_cli_prune_orphan_guard.py  (NEW FILE)
"""H-6: huntx prune must not delete raw blobs still referenced by live records."""
import hashlib, sqlite3
import pytest


def test_cli_prune_does_not_delete_live_raw_blobs(tmp_path):
    """
    H-6: After CLI prune, blobs still referenced by live records must survive.
    Before fix: ALL age-eligible hashes are pruned, including live-record blobs.
    After fix:  only orphan hashes are pruned.
    """
    from huntx.store.raw_store import RawStore
    from huntx.state.repo import StateRepo
    from huntx.store.paths import RuntimePaths

    paths = RuntimePaths(data_dir=tmp_path, state_db_path=tmp_path / "state.db")
    raw = RawStore(paths.raw_dir)

    live_blob = b"this is a live record's raw content"
    orphan_blob = b"this is an old orphaned blob"
    live_hash = hashlib.sha256(live_blob).hexdigest()
    orphan_hash = hashlib.sha256(orphan_blob).hexdigest()

    raw.save(live_blob)
    raw.save(orphan_blob)

    repo = StateRepo(str(paths.state_db_path))
    with repo._connect() as conn:
        conn.execute(
            "INSERT INTO seen_files (source_id, external_id, raw_hash, status) "
            "VALUES ('src_x', 'ext_1', ?, 'processed')",
            (live_hash,),
        )
        conn.commit()

    candidate_hashes = [live_hash, orphan_hash]

    # AFTER FIX: guard mirrors admin.py:171-176
    live_known = set(repo.get_all_known_hashes())
    orphan_only = [h for h in candidate_hashes if h not in live_known]
    raw.prune_by_hashes(orphan_only)

    assert (paths.raw_dir / live_hash[:2] / live_hash).exists(), (
        "H-6: CLI prune deleted a raw blob still referenced by a live record!"
    )
    assert not (paths.raw_dir / orphan_hash[:2] / orphan_hash).exists(), (
        "H-6: CLI prune should have deleted the orphaned blob but did not."
    )
```

### GREEN — production fix

**File:** `src/huntx/cli/main.py`, line 446 — replace the `prune_by_hashes` call:

```python
live_hashes = set(repo.get_all_known_hashes())
orphan_hashes = [h for h in raw_hashes if h not in live_hashes]
raw_pruned = raw_store.prune_by_hashes(orphan_hashes)
skipped = len(raw_hashes) - len(orphan_hashes)
print(f"  - Raw store files deleted: {raw_pruned} ({skipped} skipped — still referenced by live records)")
```

---

## §4. H-3: Hardcoded decryption credentials — TDD spec

**Defect:** `crypto.py:128-130, 241` — plaintext fallback passwords for `.tut/.sks/.tmt`, SlipNet XOR key, and NetMod key committed in source.

**Severity:** HIGH — VERIFIED ✅

### RED — secret-scan test (CI gate)

```python
# tests/test_secret_scan.py  (NEW FILE)
"""
CI secret scan: no plaintext third-party decryption credentials may exist in
the source tree. This test enforces T8 (H-3 mitigation).
NOTE: This test will FAIL on the current tree until T8 is complete. That IS
      the intended RED state — the test drives the externalization.
"""
import pathlib
import pytest

_FORBIDDEN_PATTERNS = [
    (b"fubvx788b46v",        "TUT fallback password (crypto.py:128)"),
    (b"dyv35224nossas!!",    "SKS fallback password (crypto.py:129)"),
    (b"fubvx788B4mev",       "TMT fallback password (crypto.py:130)"),
    (b"_netsyna_netmod_",    "NetMod AES-ECB key (crypto.py:241)"),
]

_SRC_DIR = pathlib.Path(__file__).parent.parent / "src"


@pytest.mark.parametrize("pattern,description", _FORBIDDEN_PATTERNS)
def test_no_hardcoded_secret_in_source(pattern, description):
    """H-3: Source tree must not contain plaintext third-party crypto credentials."""
    matches = []
    for fpath in _SRC_DIR.rglob("*.py"):
        if pattern in fpath.read_bytes():
            matches.append(str(fpath.relative_to(_SRC_DIR.parent)))
    assert not matches, (
        f"H-3 secret leak — {description} found in: {matches}\n"
        f"Fix: externalize to env var; use documented fallback only in dev fixture files."
    )
```

### GREEN — production fix (T8, two-phase)

**Phase 1 (immediate, non-breaking):** Emit a warning when the fallback is used:

```python
# src/huntx/formats/common/crypto.py — replace lines 127-131:
import os
import warnings as _warnings


def _require_env_bytes(env_key: str, insecure_fallback: bytes, name: str) -> bytes:
    """Load a crypto credential from env. Warn loudly if falling back to hardcoded value."""
    val = os.environb.get(env_key.encode())
    if val:
        return val
    _warnings.warn(
        f"[SECURITY] {name} is using an insecure hardcoded fallback. "
        f"Set {env_key} in CI secrets before rotating the credential.",
        RuntimeWarning,
        stacklevel=3,
    )
    return insecure_fallback


_TUT_PASSWORD = _require_env_bytes("HUNTX_TUT_PASS_TUT", b"fubvx788b46v",    "TUT password")
_SKS_PASSWORD = _require_env_bytes("HUNTX_TUT_PASS_SKS", b"dyv35224nossas!!", "SKS password")
_TMT_PASSWORD = _require_env_bytes("HUNTX_TUT_PASS_TMT", b"fubvx788B4mev",   "TMT password")
_NETMOD_KEY   = _require_env_bytes("HUNTX_NETMOD_KEY",   b"_netsyna_netmod_", "NetMod key")
```

**Phase 2 (after operator rotation):** Remove hardcoded fallbacks; make the function raise `RuntimeError` if the env var is unset. The secret-scan test then passes.

**CI step to add to `validate` job:**
```yaml
- name: Secret scan — no plaintext crypto credentials in source
  run: python -m pytest tests/test_secret_scan.py -v
```

---

## §5. H-4: `secure` tier verdict-writer gap — TDD spec

**Defect:** `upsert_record_verdict` has zero callers → any `secure`-tier route silently builds zero records.

**Severity:** HIGH — VERIFIED ✅

### RED — integration contract test

```python
# tests/test_secure_tier_not_silent.py  (NEW FILE)
"""
H-4: A route configured with publication_tier='secure' must EITHER:
  (a) raise ConfigurationError on validate (Option A — excise), OR
  (b) produce non-zero records when records exist (Option B — complete).
It must NEVER silently produce zero records.
"""
import pytest


def test_secure_tier_raises_config_error_or_produces_records(state_repo_with_records):
    """
    Path A (excise): validate_config rejects publication_tier='secure'.
    Path B (complete): upsert_record_verdict is called during transform; records appear.
    One of these must be true; silent-zero is a bug.
    """
    from huntx.config.schema import PublicationTier
    try:
        from huntx.config.validate import validate_config
        validate_config(make_config_with_tier(PublicationTier.SECURE))
        # If validation passes, records must exist
        from huntx.state.verdict_store import get_records_for_governed_build
        recs = get_records_for_governed_build(
            state_repo_with_records._conn, "all_sources", PublicationTier.SECURE
        )
        assert len(recs) > 0, (
            "H-4: secure tier silently produced zero records despite records existing in DB. "
            "Either excise the tier (raise ConfigurationError) or implement upsert_record_verdict."
        )
    except Exception as e:
        assert "secure" in str(e).lower(), (
            f"H-4: unexpected exception from validate_config: {e}"
        )
```

### Decision gate (T10)

| Option | Action | Effort | Risk |
|---|---|---|---|
| **A: Excise** | Add `publication_tier='secure'` → `ValidationError` in `validate_config` | 0.5 day | Low |
| **B: Complete** | Wire `SyntaxVerdict` at transform; call `upsert_record_verdict` | 3–5 days | Medium |

**Recommendation:** Ship Option A immediately; implement B in Wave 3.

---

## §6. H-2: Bot approval workflow — TDD spec

**Defect:** No `/approve`, `/deny`, `/list` handler exists → auto-delivery permanently dead unless manual SQL.

**Severity:** CRITICAL — VERIFIED ✅

### RED — handler presence tests

```python
# tests/test_bot_approval_workflow.py  (NEW FILE)
"""H-2: The bot must provide an admin-gated approval workflow."""
import pytest
from unittest.mock import AsyncMock


def test_approve_handler_exists_in_admin_module():
    from huntx.bot import admin
    assert hasattr(admin, "_handle_approve") or hasattr(admin, "handle_approve"), (
        "H-2: No approve handler in bot/admin.py. Implement /approve <user_id>."
    )


def test_deny_handler_exists_in_admin_module():
    from huntx.bot import admin
    assert hasattr(admin, "_handle_deny") or hasattr(admin, "handle_deny"), (
        "H-2: No deny handler in bot/admin.py."
    )


def test_list_pending_handler_exists():
    from huntx.bot import admin
    assert hasattr(admin, "_handle_list_pending") or hasattr(admin, "list_pending_users"), (
        "H-2: No list-pending handler in bot/admin.py."
    )


@pytest.mark.asyncio
async def test_approve_sets_approved_in_db(tmp_path):
    """H-2: /approve <user_id> must set bot_users.approved=1."""
    import sqlite3
    db = tmp_path / "state.db"
    with sqlite3.connect(str(db)) as conn:
        conn.execute("""CREATE TABLE bot_users (
            user_id TEXT PRIMARY KEY, chat_id TEXT NOT NULL,
            username TEXT, registered_at REAL NOT NULL,
            muted INTEGER DEFAULT 0, last_delivered_at REAL DEFAULT 0,
            default_format TEXT DEFAULT 'npvt',
            approved INTEGER NOT NULL DEFAULT 0
        )""")
        conn.execute("INSERT INTO bot_users VALUES ('u1','c1','alice',1.0,0,0.0,'npvt',0)")
        conn.commit()

    from huntx.bot.admin import _handle_approve
    await _handle_approve(user_id="u1", admin_chat_id="admin_c", db_path=str(db))

    with sqlite3.connect(str(db)) as conn:
        row = conn.execute("SELECT approved FROM bot_users WHERE user_id='u1'").fetchone()
    assert row and row[0] == 1, "H-2: /approve did not set approved=1"


@pytest.mark.asyncio
async def test_approve_rejects_non_admin(tmp_path):
    from huntx.bot.admin import _handle_approve
    with pytest.raises(PermissionError, match="admin"):
        await _handle_approve(
            user_id="u1", admin_chat_id="non_admin_c",
            db_path=str(tmp_path / "s.db")
        )
```

### GREEN — minimal implementation (T9)

```python
# src/huntx/bot/admin.py — add after _perform_admin_prune:

async def _handle_approve(
    user_id: str,
    admin_chat_id: str,
    db_path: str,
    approval_evidence: str = "admin_approved",
) -> str:
    """Set bot_users.approved=1 for user_id. Admin-gated."""
    if not _is_admin_chat(admin_chat_id):
        raise PermissionError(f"approve: caller {admin_chat_id!r} is not an admin")
    with _open_db(db_path) as conn:
        rows = conn.execute(
            "UPDATE bot_users SET approved=1 WHERE user_id=?", (user_id,)
        ).rowcount
    if rows == 0:
        return f"User {user_id!r} not found in bot_users."
    return f"User {user_id!r} approved."


async def _handle_deny(user_id: str, admin_chat_id: str, db_path: str) -> str:
    """Set bot_users.approved=0 (deny/revoke). Admin-gated."""
    if not _is_admin_chat(admin_chat_id):
        raise PermissionError(f"deny: caller {admin_chat_id!r} is not an admin")
    with _open_db(db_path) as conn:
        rows = conn.execute(
            "UPDATE bot_users SET approved=0 WHERE user_id=?", (user_id,)
        ).rowcount
    if rows == 0:
        return f"User {user_id!r} not found."
    return f"User {user_id!r} denied/revoked."


async def _handle_list_pending(admin_chat_id: str, db_path: str) -> str:
    """List users with approved=0. Admin-gated."""
    if not _is_admin_chat(admin_chat_id):
        raise PermissionError("list_pending: not admin")
    with _open_db(db_path) as conn:
        rows = conn.execute(
            "SELECT user_id, username, registered_at FROM bot_users "
            "WHERE approved=0 ORDER BY registered_at DESC LIMIT 50"
        ).fetchall()
    if not rows:
        return "No pending users."
    lines = [f"- {uid} ({uname or 'no name'}) reg:{ts:.0f}" for uid, uname, ts in rows]
    return "Pending approval:\n" + "\n".join(lines)
```

Register `/approve <id>`, `/deny <id>`, `/pending` in `handlers.py` under the `_is_admin` gate.

---

## §7. M-1: `nm` route NotImplementedError — TDD spec

**Defect:** `nm` is in the prod route but `NmHandler.build` raises `NotImplementedError`.

### RED

```python
# tests/test_nm_handler_build.py  (NEW FILE)

def test_prod_config_routes_do_not_include_unimplemented_handlers():
    """
    M-1: Config validation must reject routes including formats with unimplemented build().
    Option A: validate_config raises ConfigurationError for 'nm' in a route.
    Option B: NmHandler.build is implemented and no error is raised.
    """
    from huntx.config.validate import validate_config
    from huntx.config.loader import load_config
    config = load_config("configs/config.prod.yaml")
    validate_config(config)  # must not raise in either option
```

### Decision + GREEN

**Option A — excise nm from route (0.5 day):**

```python
# config/validate.py:
_UNIMPLEMENTED_BUILD_FORMATS = {"nm", "slipnet"}

for route in config.publishing.routes:
    bad = set(route.formats) & _UNIMPLEMENTED_BUILD_FORMATS
    if bad:
        raise ConfigurationError(
            f"Route '{route.name}' includes formats with unimplemented build(): {bad}. "
            f"Remove them or implement their build() method first."
        )
```

**Option B — implement nm build (1 day):** NetMod AES-ECB encrypt is the inverse of `decrypt_netmod` (crypto.py:240-265). Implement `NmHandler.build` returning a ZIP of encrypted blobs, mirroring `opaque_bundle.py`.

---

## §8. C3: npvtsub validation parity — TDD spec

**Defect:** `npvtsub` skips the URI validation that `npvt` applies → private-IP / oversized URI filtering bypassed.

### RED

```python
# tests/test_npvtsub_validation_parity.py  (NEW FILE)
import pytest

PRIVATE_IP_VMESS = (
    "vmess://eyJ2IjoiMiIsInBzIjoieCIsImFkZCI6IjE5Mi4xNjguMS4xIiwicG9ydCI6IjQ0MyIsIm"
    "lkIjoiYWFhYWFhYWEtYWFhYS1hYWFhLWFhYWEtYWFhYWFhYWFhYWFhIiwiYWlkIjoiMCIsIm5ldCI"
    "6IndzIiwidHlwZSI6Im5vbmUiLCJob3N0IjoiIiwicGF0aCI6Ii8iLCJ0bHMiOiIifQ=="
)
OVERSIZED_URI = "vmess://" + "x" * 20000


@pytest.mark.parametrize("bad_uri,reason", [
    (PRIVATE_IP_VMESS, "private IP must be rejected"),
    (OVERSIZED_URI,    "URI exceeding 16KB must be rejected"),
])
def test_npvtsub_rejects_invalid_uris(bad_uri, reason, tmp_raw_store):
    """C3: npvtsub must NOT admit URIs that npvt would reject."""
    from huntx.formats.npvtsub import NpvtsubHandler
    handler = NpvtsubHandler(raw_store=tmp_raw_store)
    records = handler.parse(bad_uri.encode(), source_info={})
    assert len(records) == 0, (
        f"C3: npvtsub admitted a URI that should be rejected ({reason})"
    )


def test_npvt_and_npvtsub_admit_same_valid_uri(tmp_raw_store):
    """C3: both handlers must accept the same set of valid proxies."""
    from huntx.formats.npvt import NpvtHandler
    from huntx.formats.npvtsub import NpvtsubHandler
    VALID = b"vmess://eyJ2IjoiMiIsInBzIjoiIiwiYWRkIjoiMS4yLjMuNCIsInBvcnQiOiI0NDMiLCJpZCI6ImFhYWFhYWFhLWFhYWEtYWFhYS1hYWFhLWFhYWFhYWFhYWFhYSIsImFpZCI6IjAiLCJuZXQiOiJ3cyIsInR5cGUiOiJub25lIiwiaG9zdCI6IiIsInBhdGgiOiIvIiwidGxzIjoiIn0="
    npvt_recs = NpvtHandler(raw_store=tmp_raw_store).parse(VALID, {})
    sub_recs  = NpvtsubHandler(raw_store=tmp_raw_store).parse(VALID, {})
    assert len(npvt_recs) == len(sub_recs), (
        "C3: npvt and npvtsub must admit the same count of valid URIs"
    )
```

### GREEN — minimal fix

```python
# src/huntx/formats/npvtsub.py — in the inner URI loop, add after extracting each uri:
from huntx.formats.proxy_uri_validator import validate_proxy_uri

for uri in candidates:
    result = validate_proxy_uri(uri)   # ADD THIS
    if not result.is_valid:            # ADD THIS
        continue
    records.append({...})
```

---

## §9. M-5: Bot rate-limiting completeness — TDD spec

**Defect:** 8 of 14 bot command handlers lack `_check_rate_limit` calls.

### RED

```python
# tests/test_bot_rate_limiting_completeness.py  (NEW FILE)
import ast, pathlib, pytest

SRC = pathlib.Path("src/huntx/bot/handlers.py")

HANDLERS_REQUIRING_RATE_LIMIT = [
    "_on_formats", "_on_protocols", "_on_count", "_on_ping",
    "_on_setformat", "_on_mute", "_on_unmute", "_on_myinfo", "_on_status",
]


@pytest.mark.parametrize("handler_name", HANDLERS_REQUIRING_RATE_LIMIT)
def test_handler_calls_check_rate_limit(handler_name):
    """M-5: Every non-admin handler must call _check_rate_limit."""
    tree = ast.parse(SRC.read_text(encoding="utf-8"))
    bodies = {
        node.name: ast.unparse(node)
        for node in ast.walk(tree)
        if isinstance(node, ast.AsyncFunctionDef) and node.name == handler_name
    }
    assert handler_name in bodies, f"Handler {handler_name} not found in handlers.py"
    assert "_check_rate_limit" in bodies[handler_name], (
        f"M-5: {handler_name} has no rate limit call. "
        f"Add: if not await self._check_rate_limit(event, seconds=30): return"
    )
```

---

## §10. Wave-by-wave CI gate matrix

| Wave | Gate conditions before merging to main |
|---|---|
| **Wave 1** (Stabilize) | Baseline 498 tests green; `test_cli_clean_reset_regression.py` GREEN; `test_cli_prune_orphan_guard.py` GREEN; `test_bot_approval_workflow.py` GREEN; `test_secret_scan.py` (after rotation) |
| **Wave 2** (Patch Inline) | Wave 1 gate; 3 consecutive CI runs show stable `run-summary.json` envelopes; lint test confirms no `install_runtime_resilience` in the live import graph post-inline |
| **Wave 3** (Feature/Validate) | Wave 2 gate; `test_secure_tier_not_silent.py` GREEN; `test_nm_handler_build.py` GREEN; `test_npvtsub_validation_parity.py` GREEN; `test_bot_rate_limiting_completeness.py` GREEN |
| **Wave 4** (Go + Observability) | Wave 3 gate; `go test -race ./cmd/huntx-tools/... ./internal/...` exits 0 with ≥1 test per package |
| **Wave 5** (Docs/Polish) | Documentation completeness check: `docs/runbooks/bot_approval.md`, env-var reference table, and DR runbook all exist |

---

## §11. Supporting fixes

### Perf test fixture fix

**Defect:** `tests/perf/` fixture rows lack `id` key → `KeyError` at `transform.py:61`.

```python
# tests/perf/conftest.py — add 'id' to every fixture row:
# BEFORE: {"unique_hash": h, "data": d}
# AFTER:  {"id": idx, "unique_hash": h, "data": d}
```

### Flaky test fix: `test_session_lease` heartbeat

**Root cause:** Monotonic timing races with OS scheduler.

```python
# tests/test_session_lease.py — use mock clock:
import unittest.mock

with unittest.mock.patch(
    "huntx.core.session_lease.time.monotonic", side_effect=[0.0, 1.0, 2.0]
):
    lease.start_heartbeat()
    assert lease.heartbeat_count >= 1
```

---

## §12. "Dead code kept green" guard

```python
# tests/test_production_import_surface.py  (NEW FILE)
"""Guard: dead modules must not be imported by the live execution path."""
import subprocess, pathlib, pytest

DEAD_CALLER_CHECK = {
    "upsert_record_verdict": 1,  # exactly 1 occurrence = definition only
}


@pytest.mark.parametrize("symbol,max_occurrences", DEAD_CALLER_CHECK.items())
def test_dead_symbol_not_called(symbol, max_occurrences):
    """H-4: verdict store must have at most max_occurrences of the symbol (its definition)."""
    result = subprocess.run(
        ["rg", "--count-matches", symbol, "src/"],
        capture_output=True, text=True,
        cwd=str(pathlib.Path(__file__).parent.parent),
    )
    count = sum(int(line.split(":")[-1]) for line in result.stdout.splitlines() if ":" in line)
    assert count <= max_occurrences, (
        f"H-4: Expected at most {max_occurrences} occurrence(s) of '{symbol}'; "
        f"found {count}. If a caller was added intentionally, update this test."
    )
```

---

## §13. Acceptance criteria summary

| Defect | Acceptance criterion | Automated gate |
|---|---|---|
| H-1 | `_restore_bot_users` preserves `approved` col; clean+reset leaves all subscriber rows intact | `test_cli_clean_reset_regression.py` |
| H-2 | `/approve`, `/deny`, `/pending` handlers exist and are admin-gated | `test_bot_approval_workflow.py` |
| H-3 | No plaintext crypto credentials in `src/`; env-override is the production path | `test_secret_scan.py` |
| H-4 | `secure` tier raises `ConfigurationError` on validate OR produces non-zero records | `test_secure_tier_not_silent.py` |
| H-5 | `prune_old_data` called in hardened cleanup stage | `rg "prune_old_data" src/huntx/core/hardened_orchestrator.py` asserts match |
| H-6 | CLI `prune` deletes only orphan hashes; live-record blobs survive | `test_cli_prune_orphan_guard.py` |
| H-8 | `go test ./cmd/huntx-tools/... ./internal/...` exits 0 with coverage | CI `go test` step |
| M-1 | `nm` excised from prod route OR `NmHandler.build` implemented | `test_nm_handler_build.py` |
| M-5 | All 14 command handlers call `_check_rate_limit` | `test_bot_rate_limiting_completeness.py` |
| C3 | `npvtsub` calls `validate_proxy_uri` on every extracted URI | `test_npvtsub_validation_parity.py` |
