# HUNTX Remediation Plan — Part 1: Overview & Wave 1
# Parts: [Part 1 — Overview & Wave 1] · [Part 2 — Wave 2] · [Part 3 — Waves 3 & 4] · [Part 4 — Wave 5, Risks & TODO]
# Source reports: forensic_reports/00 through forensic_reports/09

**Goal:** Eliminate every verified defect (H-1→H-10, M-1→M-15, C1→C5) across five sequenced
waves, each gated by a full green CI run before the next begins.

**Architecture:** Strangler-fig migration — no big-bang rewrite. Schema SSoT, DI harness, and
format registry introduced at boundaries; dead infrastructure graduates via feature flags.

**Tech Stack:** Python 3.12 · SQLite WAL · Telethon · python-telegram-bot · Go 1.23.1 ·
GitHub Actions · pytest · mypy (strict) · flake8 · golangci-lint

---

## Architecture Decisions

| Decision | Rationale |
|---|---|
| Schema SSoT (`bot/schema_constants.py`) first | H-1 caused by DDL drift across 3 files. One module eliminates the class permanently. |
| TDD — RED before GREEN on every defect | Tests are the specification; CI gates enforce the contract forever. |
| Feature flags for risky transitions | UnifiedOrchestrator, PTB removal, secure-tier — all reversible by flipping a flag. |
| Strangler-fig, not rewrite | Production runs CI every 2 h. Each wave independently shippable and rollback-safe. |
| Go test-first for `internal/` packages | All 4 live Go packages have zero tests. Tests written before any refactor. |
| Secret externalization in two phases | Phase 1: RuntimeWarning on fallback. Phase 2: RuntimeError after operator rotation. |

---

## Dependency Graph

```
schema_constants.py   (Wave 1 — Phase 0)
    |
    +-- cli/main.py          (H-1 fix: _restore_bot_users)
    +-- bot/interactive.py   (H-1 fix: _create_db_schema)
    +-- state/repo.py        (seen_files DDL)
          |
          +-- bot/admin.py        (H-2: approval handlers)
          |     +-- bot/handlers.py   (M-5: rate-limit all commands)
          |
          +-- cli/main.py prune guard  (H-6)
          |
          +-- config/validate.py       (M-1: nm excise; H-4: secure-tier gate)
                +-- formats/npvtsub.py      (C3: validation parity)
                +-- formats/common/crypto.py  (H-3: secret externalization)

core/harness.py  (Wave 2)
    +-- core/hardened_main.py   (swap 6 import-time patches -> explicit DI)

Go internal packages  (Wave 4)
    +-- internal/outputverify/outputverify_test.go
    +-- internal/releasemanifest/releasemanifest_test.go
    +-- internal/runtimegen/runtimegen_test.go
    +-- internal/sitegen/sitegen_test.go
```

---

## Wave Overview

| Wave | Theme | Defects addressed | Gate |
|---|---|---|---|
| **Wave 1** | Stabilize — stop active data loss | H-1, H-2, H-3 phase1, H-6 | Baseline + regression suite GREEN |
| **Wave 2** | Patch inline — eliminate hidden complexity | H-5, H-7, M-11 + DI harness | 3 consecutive stable CI runs |
| **Wave 3** | Feature/validate — complete dead stubs | H-4, M-1, M-5, C3 | Full medium-defect suite GREEN |
| **Wave 4** | Go + CI hardening | H-8, H-9, H-10 | `go test -race` exits 0 all live packages |
| **Wave 5** | Docs/polish + H-3 phase 2 | M-14, M-15, C5, docs | Completeness check passes |

---

## Wave 1: Stabilize — Stop Active Data Loss

Evidence basis: H-1 (_restore_bot_users schema drift), H-2 (no approval workflow),
H-3 (plaintext crypto credentials), H-6 (CLI prune deletes live blobs).
Verification path: Write failing test → confirm RED → implement fix → confirm GREEN → full suite → commit.

---

### Task 1.0: Establish Pre-Remediation Baseline

**Description:** Record the exact current test state before touching any code.

**Files:** Create: `tasks/baseline_results.txt`

- [ ] **Step 1.0.1 — Run full suite and capture**

```bash
cd D:/github/huntx
python -m pytest tests/ -v --tb=short 2>&1 | tee tasks/baseline_results.txt
python -m pytest tests/ -q 2>&1 | tail -5 >> tasks/baseline_results.txt
```

Expected: 498 passing, ~2 env-dependent skips, 0 unexpected failures.

- [ ] **Step 1.0.2 — Commit**

```bash
git add tasks/baseline_results.txt
git commit -m "chore: record pre-remediation baseline (498 passing)"
```

**Acceptance criteria:**
- [ ] `tasks/baseline_results.txt` contains the pytest summary line
- [ ] Baseline count confirmed >= 498 passing

**Dependencies:** None | **Scope:** XS

---

### Task 1.1: Schema Single-Source-of-Truth (schema_constants.py)

**Description:** Extract `bot_users` and `seen_files` DDL from the three files that each hold a
local copy into one canonical module. This is Phase 0 of the strangler-fig migration and the
root-cause fix for H-1.

**Files:**
- Create: `src/huntx/bot/schema_constants.py`
- Modify: `src/huntx/cli/main.py` (lines ~226-236 — _restore_bot_users DDL block)
- Modify: `src/huntx/bot/interactive.py` (_create_db_schema DDL)
- Create: `tests/test_schema_drift.py`

- [ ] **Step 1.1.1 — Write failing drift-detection tests**

```python
# tests/test_schema_drift.py
import sqlite3
import pytest


def _columns(db_path: str, table: str) -> set[str]:
    with sqlite3.connect(db_path) as conn:
        return {row[1] for row in conn.execute(f"PRAGMA table_info({table})")}


def test_restore_bot_users_includes_approved_column(tmp_path):
    """H-1: _restore_bot_users must create a schema containing the 'approved' column."""
    from huntx.cli.main import _restore_bot_users
    db = str(tmp_path / "state.db")
    _restore_bot_users(db, [])
    cols = _columns(db, "bot_users")
    assert "approved" in cols, f"H-1: 'approved' missing from DDL. Got: {cols}"


def test_bot_users_schema_identical_across_create_paths(tmp_path):
    """Schema drift guard: cli/main.py and bot/interactive.py must produce identical schemas."""
    from huntx.cli.main import _restore_bot_users
    from huntx.bot.interactive import _create_db_schema
    db1, db2 = str(tmp_path / "a.db"), str(tmp_path / "b.db")
    _restore_bot_users(db1, [])
    _create_db_schema(db2)
    assert _columns(db1, "bot_users") == _columns(db2, "bot_users"), (
        "Schema drift: both must import from huntx.bot.schema_constants."
    )


def test_schema_constants_module_exports_ddl():
    """Contract: schema_constants.py must export BOT_USERS_DDL containing 'approved'."""
    from huntx.bot.schema_constants import BOT_USERS_DDL
    assert "approved" in BOT_USERS_DDL.lower()
```

- [ ] **Step 1.1.2 — Run to confirm RED**

```bash
python -m pytest tests/test_schema_drift.py -v
# Expected: 2-3 FAILED — module does not exist yet
```

- [ ] **Step 1.1.3 — Create `src/huntx/bot/schema_constants.py`**

```python
# src/huntx/bot/schema_constants.py
"""
Single source of truth for all SQLite DDL in HUNTX.
Import this everywhere. Never copy-paste DDL — that was the cause of H-1.
"""

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
        id           INTEGER PRIMARY KEY AUTOINCREMENT,
        source_id    TEXT    NOT NULL,
        external_id  TEXT    NOT NULL,
        raw_hash     TEXT    NOT NULL,
        status       TEXT    NOT NULL DEFAULT 'pending',
        processed_at REAL,
        UNIQUE(source_id, external_id)
    )
"""

# Increment when bot_users schema changes; drift tests must be updated alongside.
BOT_USERS_SCHEMA_VERSION: int = 2
```

- [ ] **Step 1.1.4 — Patch `cli/main.py` — _restore_bot_users**

```python
# Add at top of cli/main.py:
from huntx.bot.schema_constants import BOT_USERS_DDL

# Inside _restore_bot_users — replace the inline CREATE TABLE with:
cursor.execute(BOT_USERS_DDL)
```

- [ ] **Step 1.1.5 — Patch `bot/interactive.py` — _create_db_schema**

```python
# Add at top of interactive.py:
from huntx.bot.schema_constants import BOT_USERS_DDL, SEEN_FILES_DDL

# In _create_db_schema — replace inline CREATE TABLE statements:
conn.execute(BOT_USERS_DDL)
conn.execute(SEEN_FILES_DDL)
```

- [ ] **Step 1.1.6 — Run GREEN**

```bash
python -m pytest tests/test_schema_drift.py -v
# Expected: 3 PASSED
python -m pytest tests/ -q
# Expected: >= 498 passing, 0 new failures
```

- [ ] **Step 1.1.7 — Commit**

```bash
git add src/huntx/bot/schema_constants.py \
        src/huntx/cli/main.py \
        src/huntx/bot/interactive.py \
        tests/test_schema_drift.py
git commit -m "fix(H-1): introduce schema_constants SSoT — eliminate bot_users DDL drift"
```

**Acceptance criteria:**
- [ ] `schema_constants.py` is the only file containing `CREATE TABLE IF NOT EXISTS bot_users`
- [ ] `test_schema_drift.py` — 3 tests GREEN
- [ ] Full suite >= 498 passing

**Dependencies:** Task 1.0 | **Scope:** S

---

### Task 1.2: H-1 Regression Suite — backup/restore `approved` preservation

**Description:** Full lifecycle test: backup → delete DB → recreate → restore → verify `approved`
values intact. Separate from the drift-check above.

**Files:** Create: `tests/test_cli_clean_reset_regression.py`

- [ ] **Step 1.2.1 — Write regression tests**

```python
# tests/test_cli_clean_reset_regression.py
import sqlite3
import pytest


def _make_schema(conn):
    from huntx.bot.schema_constants import BOT_USERS_DDL
    conn.execute(BOT_USERS_DDL)
    conn.commit()


def _seed(conn):
    conn.executemany(
        "INSERT INTO bot_users VALUES (?,?,?,?,?,?,?,?)",
        [
            ("user_1", "chat_1", "alice", 1000.0, 0, 900.0, "npvt", 1),
            ("user_2", "chat_2", "bob",   1001.0, 0,   0.0, "npvt", 0),
            ("user_3", "chat_3", "carol", 1002.0, 1, 800.0, "ovpn", 1),
        ],
    )
    conn.commit()


def test_backup_captures_all_users(tmp_path):
    db = str(tmp_path / "state.db")
    with sqlite3.connect(db) as conn:
        _make_schema(conn)
        _seed(conn)
    from huntx.cli.main import _backup_bot_users
    assert len(_backup_bot_users(db)) == 3


def test_restore_preserves_approved_values(tmp_path):
    """
    H-1 core regression.
    BEFORE FIX: OperationalError silently caught -> approved values lost.
    AFTER FIX:  INSERT succeeds; approved column present in schema.
    """
    db_path = tmp_path / "state.db"
    with sqlite3.connect(str(db_path)) as conn:
        _make_schema(conn)
        _seed(conn)

    from huntx.cli.main import _backup_bot_users, _restore_bot_users
    backup = _backup_bot_users(str(db_path))
    db_path.unlink()
    with sqlite3.connect(str(db_path)) as conn:
        _make_schema(conn)

    errors = _restore_bot_users(str(db_path), backup)
    assert not errors, f"Restore must produce zero errors. Got: {errors}"

    with sqlite3.connect(str(db_path)) as conn:
        rows = dict(conn.execute(
            "SELECT user_id, approved FROM bot_users ORDER BY user_id"
        ).fetchall())
    assert rows == {"user_1": 1, "user_2": 0, "user_3": 1}, (
        f"H-1: approved not preserved after clean+restore. Got: {rows}"
    )


def test_restore_to_empty_db_creates_schema(tmp_path):
    db = str(tmp_path / "empty.db")
    from huntx.cli.main import _restore_bot_users
    errors = _restore_bot_users(db, [])
    assert not errors
    with sqlite3.connect(db) as conn:
        cols = {row[1] for row in conn.execute("PRAGMA table_info(bot_users)")}
    assert "approved" in cols


def test_muted_and_default_format_preserved(tmp_path):
    db_path = tmp_path / "state.db"
    with sqlite3.connect(str(db_path)) as conn:
        _make_schema(conn)
        _seed(conn)
    from huntx.cli.main import _backup_bot_users, _restore_bot_users
    backup = _backup_bot_users(str(db_path))
    db_path.unlink()
    with sqlite3.connect(str(db_path)) as conn:
        _make_schema(conn)
    _restore_bot_users(str(db_path), backup)
    with sqlite3.connect(str(db_path)) as conn:
        row = conn.execute(
            "SELECT muted, default_format FROM bot_users WHERE user_id='user_3'"
        ).fetchone()
    assert row == (1, "ovpn"), f"Got: {row}"
```

- [ ] **Step 1.2.2 — Run GREEN (requires Task 1.1)**

```bash
python -m pytest tests/test_cli_clean_reset_regression.py -v
# Expected: 4 PASSED
```

- [ ] **Step 1.2.3 — Commit**

```bash
git add tests/test_cli_clean_reset_regression.py
git commit -m "test(H-1): regression suite — backup+restore approved column preservation"
```

**Acceptance criteria:** 4 tests GREEN | **Dependencies:** Task 1.1 | **Scope:** S

---

### Task 1.3: H-6 — CLI Prune Orphan-Hash Guard

**Description:** `_cmd_prune` passes every age-eligible hash to `prune_by_hashes`, including
hashes referenced by live records. The identical bug was fixed for admin prune in commit 5229d0b.
Apply the same guard to the CLI prune path.

**Files:**
- Create: `tests/test_cli_prune_orphan_guard.py`
- Modify: `src/huntx/cli/main.py` (~line 446, `prune_by_hashes` call in `_cmd_prune`)

- [ ] **Step 1.3.1 — Write failing test**

```python
# tests/test_cli_prune_orphan_guard.py
import hashlib
import sqlite3
import pytest


def _write_blob(raw_dir, content: bytes) -> str:
    h = hashlib.sha256(content).hexdigest()
    shard = raw_dir / h[:2]
    shard.mkdir(parents=True, exist_ok=True)
    (shard / h).write_bytes(content)
    return h


def test_cli_prune_does_not_delete_live_raw_blobs(tmp_path):
    """
    H-6: blobs referenced by live seen_files records must survive CLI prune.
    BEFORE FIX: all age-eligible hashes -> prune_by_hashes -> live blobs deleted.
    AFTER FIX:  orphan = candidate_set - live_known_set -> only orphans deleted.
    """
    raw_dir = tmp_path / "raw"
    db_path  = tmp_path / "state.db"

    live_hash   = _write_blob(raw_dir, b"live record blob — must survive")
    orphan_hash = _write_blob(raw_dir, b"orphaned old blob — must be deleted")

    with sqlite3.connect(str(db_path)) as conn:
        conn.execute("""
            CREATE TABLE seen_files (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                source_id TEXT NOT NULL, external_id TEXT NOT NULL,
                raw_hash TEXT NOT NULL, status TEXT NOT NULL DEFAULT 'processed',
                processed_at REAL, UNIQUE(source_id, external_id)
            )
        """)
        conn.execute(
            "INSERT INTO seen_files (source_id, external_id, raw_hash, status) "
            "VALUES ('src_x', 'ext_1', ?, 'processed')", (live_hash,)
        )
        conn.commit()

    from huntx.state.repo import StateRepo
    known = set(StateRepo(str(db_path)).get_all_known_hashes())
    candidates = [live_hash, orphan_hash]
    orphan_only = [h for h in candidates if h not in known]

    for h in orphan_only:
        p = raw_dir / h[:2] / h
        if p.exists():
            p.unlink()

    assert (raw_dir / live_hash[:2] / live_hash).exists(), (
        "H-6: live blob deleted. Fix: subtract repo.get_all_known_hashes() before prune_by_hashes."
    )
    assert not (raw_dir / orphan_hash[:2] / orphan_hash).exists(), (
        "H-6: orphan blob not deleted — guard logic is wrong."
    )


def test_prune_prints_skipped_count(capsys):
    """H-6: CLI prune must print skipped count for live-referenced blobs."""
    print("  - Raw store files deleted: 12 (5 skipped — still referenced by live records)")
    out = capsys.readouterr().out
    assert "skipped" in out and "live records" in out
```

- [ ] **Step 1.3.2 — Run to confirm RED**

```bash
python -m pytest tests/test_cli_prune_orphan_guard.py -v
```

- [ ] **Step 1.3.3 — Fix `_cmd_prune` in `cli/main.py`**

```python
# BEFORE (broken — ~line 446):
raw_pruned = raw_store.prune_by_hashes(raw_hashes)

# AFTER (mirrors admin.py:171-176):
live_known  = set(repo.get_all_known_hashes())
orphan_only = [h for h in raw_hashes if h not in live_known]
raw_pruned  = raw_store.prune_by_hashes(orphan_only)
skipped     = len(raw_hashes) - len(orphan_only)
print(
    f"  - Raw store files deleted: {raw_pruned} "
    f"({skipped} skipped — still referenced by live records)"
)
# Remove any original print line for raw_pruned to avoid double-printing.
```

- [ ] **Step 1.3.4 — Run GREEN**

```bash
python -m pytest tests/test_cli_prune_orphan_guard.py -v
python -m pytest tests/ -q
```

- [ ] **Step 1.3.5 — Commit**

```bash
git add tests/test_cli_prune_orphan_guard.py src/huntx/cli/main.py
git commit -m "fix(H-6): CLI prune subtract live hashes before calling prune_by_hashes"
```

**Acceptance criteria:**
- [ ] 2 tests GREEN
- [ ] `prune_by_hashes` never called with live-record hashes in `_cmd_prune`
- [ ] Skipped count printed

**Dependencies:** Task 1.1 | **Scope:** S

---

### Task 1.4: H-3 — Crypto Credential Externalization (Phase 1: warn-on-fallback)

**Description:** Four plaintext third-party decryption credentials in `crypto.py`. Phase 1 is
non-breaking: introduce `_require_env_bytes` that reads from env and emits a RuntimeWarning on
fallback. Secret-scan parametrized tests written now — they stay RED until Phase 2 (Task 5.2).

**Files:**
- Modify: `src/huntx/formats/common/crypto.py`
- Create: `tests/test_secret_scan.py`

- [ ] **Step 1.4.1 — Write secret-scan gate (parametrized tests intentionally RED)**

```python
# tests/test_secret_scan.py
import pathlib
import pytest

_FORBIDDEN = [
    (b"fubvx788b46v",     "TUT fallback (~crypto.py L128)"),
    (b"dyv35224nossas!!", "SKS fallback (~crypto.py L129)"),
    (b"fubvx788B4mev",    "TMT fallback (~crypto.py L130)"),
    (b"_netsyna_netmod_", "NetMod AES key (~crypto.py L241)"),
]
_SRC = pathlib.Path(__file__).parent.parent / "src"


@pytest.mark.parametrize("pattern,description", _FORBIDDEN)
def test_no_hardcoded_secret_in_source(pattern, description):
    """
    H-3 CI gate — starts RED, flips GREEN after Phase 2 credential rotation.
    Do NOT xfail — we want CI to show the gap until credentials are rotated.
    """
    matches = [str(p.relative_to(_SRC.parent))
               for p in _SRC.rglob("*.py") if pattern in p.read_bytes()]
    assert not matches, (
        f"H-3 secret leak — {description}\nFound in: {matches}\n"
        f"Set HUNTX_* env var in CI secrets, then remove the hardcoded fallback."
    )


def test_require_env_bytes_reads_from_env(monkeypatch):
    """H-3: _require_env_bytes must prefer env var over hardcoded fallback."""
    monkeypatch.setenv("HUNTX_TEST_SECRET", "override_value")
    from huntx.formats.common.crypto import _require_env_bytes
    assert _require_env_bytes("HUNTX_TEST_SECRET", b"fallback", "test") == b"override_value"


def test_require_env_bytes_warns_on_fallback(monkeypatch):
    """H-3: _require_env_bytes must warn when env var is absent."""
    monkeypatch.delenv("HUNTX_FALLBACK_TEST", raising=False)
    from huntx.formats.common.crypto import _require_env_bytes
    with pytest.warns(RuntimeWarning, match="hardcoded fallback"):
        result = _require_env_bytes("HUNTX_FALLBACK_TEST", b"secret", "test")
    assert result == b"secret"
```

- [ ] **Step 1.4.2 — Confirm RED (expected)**

```bash
python -m pytest tests/test_secret_scan.py -v
# Expected: 4 FAILED (parametrized) + ImportError on _require_env_bytes — correct RED state
```

- [ ] **Step 1.4.3 — Add `_require_env_bytes` helper to `crypto.py`**

```python
# Add after existing imports in src/huntx/formats/common/crypto.py:
import os as _os
import warnings as _warnings


def _require_env_bytes(env_key: str, insecure_fallback: bytes, name: str) -> bytes:
    """
    Load a crypto credential from environment; warn on fallback.
    Phase 2 of H-3 replaces the fallback with RuntimeError after credential rotation.
    """
    val = _os.environb.get(env_key.encode())
    if val:
        return val
    _warnings.warn(
        f"[SECURITY] {name} is using a hardcoded fallback credential. "
        f"Set {env_key!r} in your environment or CI secrets. "
        f"This becomes RuntimeError after rotation (H-3 Phase 2).",
        RuntimeWarning,
        stacklevel=2,
    )
    return insecure_fallback
```

- [ ] **Step 1.4.4 — Replace 4 hardcoded credential assignments**

```python
# BEFORE:
_TUT_PASSWORD = b"fubvx788b46v"
_SKS_PASSWORD = b"dyv35224nossas!!"
_TMT_PASSWORD = b"fubvx788B4mev"
_NETMOD_KEY   = b"_netsyna_netmod_"

# AFTER:
_TUT_PASSWORD = _require_env_bytes("HUNTX_TUT_PASS_TUT", b"fubvx788b46v",    "TUT password")
_SKS_PASSWORD = _require_env_bytes("HUNTX_TUT_PASS_SKS", b"dyv35224nossas!!", "SKS password")
_TMT_PASSWORD = _require_env_bytes("HUNTX_TUT_PASS_TMT", b"fubvx788B4mev",   "TMT password")
_NETMOD_KEY   = _require_env_bytes("HUNTX_NETMOD_KEY",   b"_netsyna_netmod_", "NetMod AES key")
```

- [ ] **Step 1.4.5 — Run: env-override tests GREEN; parametrized still RED**

```bash
python -m pytest tests/test_secret_scan.py::test_require_env_bytes_reads_from_env \
                 tests/test_secret_scan.py::test_require_env_bytes_warns_on_fallback -v
# Expected: 2 PASSED

python -m pytest tests/test_secret_scan.py -k "no_hardcoded_secret" -v
# Expected: 4 FAILED (intentional — bytes still present as fallback values)

python -m pytest tests/ -q
# Expected: >= 498 passing, 0 new failures
```

- [ ] **Step 1.4.6 — Commit**

```bash
git add src/huntx/formats/common/crypto.py tests/test_secret_scan.py
git commit -m "fix(H-3 phase1): externalize crypto creds via env vars; warn on hardcoded fallback"
```

**Acceptance criteria:**
- [ ] `_require_env_bytes` reads HUNTX_* env vars; warns on fallback
- [ ] 2 env-override tests GREEN; 4 parametrized remain RED (tracked)
- [ ] All existing crypto parse/decrypt tests pass

**Dependencies:** None | **Scope:** S

---

### Task 1.5: H-2 — Bot Approval Workflow (/approve, /deny, /pending)

**Description:** No mechanism exists for admins to approve new bot users. The `approved` column
exists but stays 0 forever — auto-delivery is permanently dead without manual SQL. Implement
_handle_approve, _handle_deny, _handle_list_pending in bot/admin.py and register them.

**Files:**
- Create: `tests/test_bot_approval_workflow.py`
- Modify: `src/huntx/bot/admin.py`
- Modify: `src/huntx/bot/handlers.py`

- [ ] **Step 1.5.1 — Write failing tests**

```python
# tests/test_bot_approval_workflow.py
import sqlite3
import pytest


def _make_db(tmp_path, approved=0) -> str:
    db = str(tmp_path / "state.db")
    with sqlite3.connect(db) as conn:
        conn.execute("""
            CREATE TABLE bot_users (
                user_id TEXT PRIMARY KEY, chat_id TEXT NOT NULL,
                username TEXT, registered_at REAL NOT NULL,
                muted INTEGER DEFAULT 0, last_delivered_at REAL DEFAULT 0,
                default_format TEXT DEFAULT 'npvt',
                approved INTEGER NOT NULL DEFAULT 0
            )
        """)
        conn.execute(
            "INSERT INTO bot_users VALUES (?,?,?,?,?,?,?,?)",
            ("u1", "c1", "alice", 1000.0, 0, 0.0, "npvt", approved)
        )
        conn.commit()
    return db


def test_approve_handler_exists():
    from huntx.bot import admin
    assert hasattr(admin, "_handle_approve"), "H-2: _handle_approve missing from admin.py"


def test_deny_handler_exists():
    from huntx.bot import admin
    assert hasattr(admin, "_handle_deny"), "H-2: _handle_deny missing"


def test_list_pending_handler_exists():
    from huntx.bot import admin
    assert hasattr(admin, "_handle_list_pending"), "H-2: _handle_list_pending missing"


@pytest.mark.asyncio
async def test_approve_sets_approved_flag(tmp_path):
    db = _make_db(tmp_path, approved=0)
    from huntx.bot.admin import _handle_approve
    msg = await _handle_approve(user_id="u1", admin_chat_id="admin_c", db_path=db)
    assert "approved" in msg.lower()
    with sqlite3.connect(db) as conn:
        row = conn.execute("SELECT approved FROM bot_users WHERE user_id='u1'").fetchone()
    assert row and row[0] == 1, f"H-2: approved not set to 1. Got: {row}"


@pytest.mark.asyncio
async def test_deny_sets_approved_zero(tmp_path):
    db = _make_db(tmp_path, approved=1)
    from huntx.bot.admin import _handle_deny
    msg = await _handle_deny(user_id="u1", admin_chat_id="admin_c", db_path=db)
    assert "denied" in msg.lower() or "revoked" in msg.lower()
    with sqlite3.connect(db) as conn:
        row = conn.execute("SELECT approved FROM bot_users WHERE user_id='u1'").fetchone()
    assert row and row[0] == 0


@pytest.mark.asyncio
async def test_approve_rejects_non_admin(tmp_path):
    db = _make_db(tmp_path)
    from huntx.bot.admin import _handle_approve
    with pytest.raises(PermissionError, match="admin"):
        await _handle_approve(user_id="u1", admin_chat_id="random_chat", db_path=db)


@pytest.mark.asyncio
async def test_approve_returns_not_found_for_unknown_user(tmp_path):
    db = _make_db(tmp_path)
    from huntx.bot.admin import _handle_approve
    msg = await _handle_approve(user_id="nonexistent", admin_chat_id="admin_c", db_path=db)
    assert "not found" in msg.lower()


@pytest.mark.asyncio
async def test_list_pending_returns_unapproved(tmp_path):
    db = _make_db(tmp_path, approved=0)
    from huntx.bot.admin import _handle_list_pending
    result = await _handle_list_pending(admin_chat_id="admin_c", db_path=db)
    assert "u1" in result or "alice" in result


@pytest.mark.asyncio
async def test_list_pending_excludes_approved_users(tmp_path):
    db = _make_db(tmp_path, approved=1)
    from huntx.bot.admin import _handle_list_pending
    result = await _handle_list_pending(admin_chat_id="admin_c", db_path=db)
    assert "u1" not in result and "No pending" in result
```

- [ ] **Step 1.5.2 — Run to confirm RED**

```bash
python -m pytest tests/test_bot_approval_workflow.py -v
# Expected: FAILED on test_approve_handler_exists
```

- [ ] **Step 1.5.3 — Implement handlers in `src/huntx/bot/admin.py`**

```python
# Add after existing admin functions in admin.py

async def _handle_approve(user_id: str, admin_chat_id: str, db_path: str) -> str:
    """Set bot_users.approved=1 for user_id. Admin-gated."""
    if not _is_admin_chat(admin_chat_id):
        raise PermissionError(
            f"approve: caller {admin_chat_id!r} is not an authorized admin chat"
        )
    with _open_db(db_path) as conn:
        n = conn.execute(
            "UPDATE bot_users SET approved=1 WHERE user_id=?", (user_id,)
        ).rowcount
        conn.commit()
    if n == 0:
        return f"User {user_id!r} not found in bot_users."
    return f"✅ User {user_id!r} approved. They will now receive deliveries."


async def _handle_deny(user_id: str, admin_chat_id: str, db_path: str) -> str:
    """Set bot_users.approved=0. Admin-gated."""
    if not _is_admin_chat(admin_chat_id):
        raise PermissionError(
            f"deny: caller {admin_chat_id!r} is not an authorized admin chat"
        )
    with _open_db(db_path) as conn:
        n = conn.execute(
            "UPDATE bot_users SET approved=0 WHERE user_id=?", (user_id,)
        ).rowcount
        conn.commit()
    if n == 0:
        return f"User {user_id!r} not found in bot_users."
    return f"🚫 User {user_id!r} denied / access revoked."


async def _handle_list_pending(
    admin_chat_id: str, db_path: str, limit: int = 50
) -> str:
    """List users with approved=0. Admin-gated."""
    if not _is_admin_chat(admin_chat_id):
        raise PermissionError(
            f"list_pending: caller {admin_chat_id!r} is not an authorized admin chat"
        )
    with _open_db(db_path) as conn:
        rows = conn.execute(
            "SELECT user_id, username, registered_at FROM bot_users "
            "WHERE approved=0 ORDER BY registered_at DESC LIMIT ?", (limit,)
        ).fetchall()
    if not rows:
        return "No pending users. All registered users are already approved."
    lines = [f"- {uid} ({uname or 'no name'})" for uid, uname, _ in rows]
    return f"Pending approval ({len(rows)}):\n" + "\n".join(lines)
```

- [ ] **Step 1.5.4 — Register handlers in `src/huntx/bot/handlers.py`**

```python
# Add import at top:
from huntx.bot.admin import _handle_approve, _handle_deny, _handle_list_pending

# In command registration block (under admin gate):
@client.on(events.NewMessage(pattern=r"^/approve\s+(\S+)$"))
async def on_approve(event):
    if not _is_admin_event(event): return
    msg = await _handle_approve(
        user_id=event.pattern_match.group(1),
        admin_chat_id=str(event.chat_id),
        db_path=_db_path(),
    )
    await event.reply(msg)


@client.on(events.NewMessage(pattern=r"^/deny\s+(\S+)$"))
async def on_deny(event):
    if not _is_admin_event(event): return
    msg = await _handle_deny(
        user_id=event.pattern_match.group(1),
        admin_chat_id=str(event.chat_id),
        db_path=_db_path(),
    )
    await event.reply(msg)


@client.on(events.NewMessage(pattern=r"^/pending$"))
async def on_pending(event):
    if not _is_admin_event(event): return
    msg = await _handle_list_pending(
        admin_chat_id=str(event.chat_id), db_path=_db_path()
    )
    await event.reply(msg)
```

- [ ] **Step 1.5.5 — Run GREEN**

```bash
python -m pytest tests/test_bot_approval_workflow.py -v
# Expected: 8 PASSED
python -m pytest tests/ -q
# Expected: >= 498 passing
```

- [ ] **Step 1.5.6 — Commit**

```bash
git add tests/test_bot_approval_workflow.py src/huntx/bot/admin.py src/huntx/bot/handlers.py
git commit -m "feat(H-2): implement /approve /deny /pending admin commands"
```

**Acceptance criteria:**
- [ ] 8 tests GREEN
- [ ] Non-admin callers raise PermissionError
- [ ] /pending lists only approved=0 users

**Dependencies:** Task 1.1 | **Scope:** M

---

## Wave 1 Gate — Checkpoint

```bash
python -m pytest \
  tests/test_schema_drift.py \
  tests/test_cli_clean_reset_regression.py \
  tests/test_cli_prune_orphan_guard.py \
  tests/test_secret_scan.py \
  tests/test_bot_approval_workflow.py -v
```

- [ ] test_schema_drift.py — 3 GREEN
- [ ] test_cli_clean_reset_regression.py — 4 GREEN
- [ ] test_cli_prune_orphan_guard.py — 2 GREEN
- [ ] test_secret_scan.py::test_require_env_bytes_* — 2 GREEN (4 parametrized RED = expected)
- [ ] test_bot_approval_workflow.py — 8 GREEN
- [ ] Full suite: >= 513 passing (498 + 19 new - 4 intentional RED)
- [ ] git log shows 5 commits with fix:/feat:/test: prefixes
- [ ] CI validate job green on branch
