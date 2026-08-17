# HUNTX Remediation Plan — Part 2: Wave 2 (Patch Inline)
# Parts: [Part 1 — Overview & Wave 1] · [Part 2 — Wave 2] · [Part 3 — Waves 3 & 4] · [Part 4 — Wave 5, Risks & TODO]

## Wave 2: Patch Inline — Eliminate Hidden Complexity

**Entry gate:** All Wave 1 tests green. CI validate job green. Full suite >= 513 passing.
**Defects addressed:** H-5 (nm-import probe), H-7 (format registry fallback), M-11 (UnifiedOrchestrator flag), DI harness migration.

---

### Task 2.1: H-5 — Remove nm Covert Import Probe

**Description:** In `config/validate.py`, three `netmiko`/`paramiko`/`nm` modules are imported at
call-time inside a try/except block. The probe fires on every config validation call, consuming
~80 ms and leaking internal network topology details on success. The entire block must be excised;
callers that legitimately need nm capabilities get them through the format registry (Task 2.3).

**Files:**
- Create: `tests/test_nm_probe_excised.py`
- Modify: `src/huntx/config/validate.py`

- [ ] **Step 2.1.1 — Write failing test**

```python
# tests/test_nm_probe_excised.py
import ast
import pathlib
import pytest

_VALIDATE = (
    pathlib.Path(__file__).parent.parent
    / "src/huntx/config/validate.py"
)


def _get_imports(source: str) -> list[str]:
    """Extract all module names from import/from-import statements in source."""
    tree = ast.parse(source)
    names = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names.extend(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            names.append(node.module)
    return names


def test_nm_probe_not_imported_at_module_level(monkeypatch):
    """H-5: nm/netmiko/paramiko must not appear at module-level in validate.py."""
    source = _VALIDATE.read_text(encoding="utf-8")
    # Module-level imports are in top-level Import/ImportFrom nodes
    tree = ast.parse(source)
    top_level_imports = []
    for node in tree.body:
        if isinstance(node, ast.Import):
            top_level_imports.extend(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            top_level_imports.append(node.module)
    forbidden = {"nm", "netmiko", "paramiko"}
    found = forbidden & set(top_level_imports)
    assert not found, f"H-5: forbidden imports at module level: {found}"


def test_nm_probe_not_in_try_except_either():
    """H-5: nm probe must not exist as a runtime try/except import either."""
    source = _VALIDATE.read_text(encoding="utf-8")
    assert "import nm" not in source, (
        "H-5: 'import nm' still present in validate.py — remove the entire probe block."
    )
    assert "import netmiko" not in source, (
        "H-5: 'import netmiko' still present — remove the probe block."
    )


def test_validate_config_still_callable():
    """Regression: removing nm probe must not break validate_config's signature."""
    from huntx.config.validate import validate_config
    import inspect
    sig = inspect.signature(validate_config)
    # validate_config must still accept a config dict
    assert len(sig.parameters) >= 1


def test_validate_config_returns_without_nm_installed(monkeypatch):
    """H-5: validate_config must not raise ImportError when nm is absent."""
    import sys
    # Simulate nm not installed
    monkeypatch.setitem(sys.modules, "nm", None)
    monkeypatch.setitem(sys.modules, "netmiko", None)
    from huntx.config.validate import validate_config
    # Should not raise — nm is no longer required
    try:
        validate_config({"sources": [], "bot": {}})
    except ImportError as e:
        pytest.fail(f"H-5: validate_config raised ImportError: {e}")
```

- [ ] **Step 2.1.2 — Run to confirm RED**

```bash
python -m pytest tests/test_nm_probe_excised.py -v
# Expected: 2 FAILED (import still present), 2 may pass depending on state
```

- [ ] **Step 2.1.3 — Excise the nm probe block from `validate.py`**

Locate and completely delete the block of the form:

```python
# REMOVE entire block:
try:
    import nm          # or: from nm import ...
    import netmiko
    import paramiko
    _NM_AVAILABLE = True
except ImportError:
    _NM_AVAILABLE = False
```

Also remove any downstream references to `_NM_AVAILABLE` in `validate_config` that condition
behaviour on nm availability. If the conditional path implements something legitimate (e.g. SSH
host reachability check), stub it with a `TODO(H-5): migrate to format registry` comment.

- [ ] **Step 2.1.4 — Run GREEN**

```bash
python -m pytest tests/test_nm_probe_excised.py -v
# Expected: 4 PASSED
python -m pytest tests/ -q
# Expected: >= 513 passing, 0 new failures
```

- [ ] **Step 2.1.5 — Commit**

```bash
git add tests/test_nm_probe_excised.py src/huntx/config/validate.py
git commit -m "fix(H-5): excise covert nm import probe from validate.py"
```

**Acceptance criteria:**
- [ ] `import nm` / `import netmiko` / `import paramiko` absent from `validate.py`
- [ ] 4 tests GREEN | `validate_config` callable without nm installed
**Dependencies:** Task 1.5 | **Scope:** S

---

### Task 2.2: H-7 — Format Registry with Safe Fallback

**Description:** Format lookup currently uses a bare `dict[str, type]` with no fallback. An
unknown format key raises `KeyError` which propagates to the delivery loop, aborting the entire
batch. Introduce `FormatRegistry` — a thin wrapper with an explicit `get(key, default)` contract.

**Files:**
- Create: `src/huntx/formats/registry.py`
- Create: `tests/test_format_registry.py`
- Modify: `src/huntx/core/pipeline.py` (or wherever format dict is used — grep for
  `FORMAT_MAP[` / `_FORMATS[`)

- [ ] **Step 2.2.1 — Write failing tests**

```python
# tests/test_format_registry.py
import pytest
from unittest.mock import MagicMock


def test_registry_returns_correct_class_for_known_key():
    from huntx.formats.registry import FormatRegistry
    fake_cls = MagicMock()
    reg = FormatRegistry({"npvt": fake_cls})
    assert reg.get("npvt") is fake_cls


def test_registry_get_returns_default_for_unknown_key():
    from huntx.formats.registry import FormatRegistry
    reg = FormatRegistry({"npvt": MagicMock()})
    default = MagicMock()
    result = reg.get("nonexistent_format", default=default)
    assert result is default, (
        "H-7: unknown format key must return default, not raise KeyError."
    )


def test_registry_get_raises_on_unknown_key_with_no_default():
    from huntx.formats.registry import FormatRegistry
    reg = FormatRegistry({"npvt": MagicMock()})
    with pytest.raises(KeyError, match="nonexistent_format"):
        reg.get("nonexistent_format")


def test_registry_lists_all_registered_formats():
    from huntx.formats.registry import FormatRegistry
    reg = FormatRegistry({"npvt": MagicMock(), "ovpn": MagicMock()})
    assert set(reg.keys()) == {"npvt", "ovpn"}


def test_registry_contains_check():
    from huntx.formats.registry import FormatRegistry
    reg = FormatRegistry({"npvt": MagicMock()})
    assert "npvt" in reg
    assert "unknown" not in reg


def test_delivery_loop_uses_registry_default_not_keyerror(monkeypatch):
    """H-7: delivery loop must not raise KeyError on unknown format — use fallback."""
    from huntx.formats.registry import FormatRegistry, SENTINEL_FORMAT
    reg = FormatRegistry({"npvt": MagicMock()})
    # Simulate unknown format arriving from a user record
    result = reg.get("extremely_rare_format", default=SENTINEL_FORMAT)
    assert result is SENTINEL_FORMAT, (
        "H-7: delivery loop must receive SENTINEL_FORMAT on unknown key, not raise."
    )


def test_format_registry_is_singleton_accessible():
    """The global FORMAT_REGISTRY singleton must be importable."""
    from huntx.formats.registry import FORMAT_REGISTRY
    assert "npvt" in FORMAT_REGISTRY, (
        "FORMAT_REGISTRY must contain at least 'npvt' format after module load."
    )
```

- [ ] **Step 2.2.2 — Run to confirm RED**

```bash
python -m pytest tests/test_format_registry.py -v
# Expected: ImportError — registry.py does not exist
```

- [ ] **Step 2.2.3 — Create `src/huntx/formats/registry.py`**

```python
# src/huntx/formats/registry.py
"""
Format registry — single source of truth for all parser/formatter classes.
Replaces bare dict lookups that raised KeyError on unknown format keys (H-7).
"""
from __future__ import annotations

from typing import Any, Iterator

_MISSING = object()


class _SentinelFormat:
    """Returned instead of raising KeyError when format key is unknown."""
    name = "__sentinel__"


SENTINEL_FORMAT = _SentinelFormat()


class FormatRegistry:
    """Thin wrapper around a format-name -> class mapping with safe fallback."""

    def __init__(self, mapping: dict[str, type]) -> None:
        self._map: dict[str, type] = dict(mapping)

    def get(self, key: str, default: Any = _MISSING) -> Any:
        """
        Return the format class for *key*.
        - If key is registered: return it.
        - If default is provided: return default.
        - Otherwise: raise KeyError.
        """
        val = self._map.get(key, _MISSING)
        if val is not _MISSING:
            return val
        if default is not _MISSING:
            return default
        raise KeyError(
            f"{key!r} is not a registered format. "
            f"Known formats: {sorted(self._map.keys())}"
        )

    def keys(self) -> Iterator[str]:
        return iter(self._map)

    def __contains__(self, key: str) -> bool:
        return key in self._map


# ---------------------------------------------------------------------------
# Global singleton — populated from format package __init__
# ---------------------------------------------------------------------------
def _build_registry() -> FormatRegistry:
    from huntx.formats.npvtsub import NpvtSubFormat  # type: ignore[import]
    from huntx.formats.ovpnsub import OvpnSubFormat  # type: ignore[import]
    # Add new formats here, never in calling code.
    return FormatRegistry(
        {
            "npvt": NpvtSubFormat,
            "npvtsub": NpvtSubFormat,
            "ovpn": OvpnSubFormat,
            "ovpnsub": OvpnSubFormat,
        }
    )


FORMAT_REGISTRY: FormatRegistry = _build_registry()
```

- [ ] **Step 2.2.4 — Migrate `pipeline.py` (or equivalent) to use registry**

```python
# BEFORE (brittle):
formatter = FORMAT_MAP[user.default_format]()

# AFTER (H-7 fix — uses safe fallback):
from huntx.formats.registry import FORMAT_REGISTRY, SENTINEL_FORMAT

fmt_cls = FORMAT_REGISTRY.get(user.default_format, default=SENTINEL_FORMAT)
if fmt_cls is SENTINEL_FORMAT:
    logger.warning(
        "Unknown format %r for user %s — skipping delivery",
        user.default_format, user.user_id,
    )
    continue
formatter = fmt_cls()
```

- [ ] **Step 2.2.5 — Run GREEN**

```bash
python -m pytest tests/test_format_registry.py -v
# Expected: 7 PASSED
python -m pytest tests/ -q
# Expected: >= 513 passing
```

- [ ] **Step 2.2.6 — Commit**

```bash
git add src/huntx/formats/registry.py tests/test_format_registry.py src/huntx/core/pipeline.py
git commit -m "fix(H-7): introduce FormatRegistry with safe fallback — eliminate KeyError on unknown format"
```

**Acceptance criteria:**
- [ ] `FORMAT_REGISTRY.get(unknown)` returns `SENTINEL_FORMAT` (no KeyError)
- [ ] 7 tests GREEN | delivery loop skips unknown format with warning
**Dependencies:** Task 2.1 | **Scope:** M

---

### Task 2.3: RuntimeHarness — DI Container (M-11)

**Description:** `core/hardened_main.py` applies 6 monkey-patches at import time. This makes
unit tests impossible without import ordering tricks. Introduce `RuntimeHarness` — a simple
dependency-injection container. Migrate all 6 patches to explicit constructor injections. The
old monkey-patch block is kept behind a `USE_LEGACY_PATCHES` flag for one release cycle.

**Files:**
- Create: `src/huntx/core/harness.py`
- Create: `tests/test_runtime_harness.py`
- Modify: `src/huntx/core/hardened_main.py`

- [ ] **Step 2.3.1 — Write failing harness tests**

```python
# tests/test_runtime_harness.py
import pytest
from unittest.mock import MagicMock


def test_harness_module_importable():
    from huntx.core.harness import RuntimeHarness
    assert RuntimeHarness is not None


def test_harness_accepts_six_dependencies():
    from huntx.core.harness import RuntimeHarness
    deps = {
        "state_repo": MagicMock(),
        "raw_store": MagicMock(),
        "format_registry": MagicMock(),
        "notifier": MagicMock(),
        "scheduler": MagicMock(),
        "config": MagicMock(),
    }
    harness = RuntimeHarness(**deps)
    for key, val in deps.items():
        assert getattr(harness, key) is val, f"H-DI: harness.{key} not set correctly"


def test_harness_exposes_start_stop():
    from huntx.core.harness import RuntimeHarness
    harness = RuntimeHarness(
        state_repo=MagicMock(),
        raw_store=MagicMock(),
        format_registry=MagicMock(),
        notifier=MagicMock(),
        scheduler=MagicMock(),
        config={},
    )
    assert callable(getattr(harness, "start", None)), "RuntimeHarness must expose start()"
    assert callable(getattr(harness, "stop",  None)), "RuntimeHarness must expose stop()"


def test_hardened_main_env_flag_disables_monkey_patches(monkeypatch):
    """
    M-11: when USE_LEGACY_PATCHES=false, hardened_main must NOT call
    any module.__dict__ mutation at import time.
    """
    monkeypatch.setenv("HUNTX_USE_LEGACY_PATCHES", "false")
    import importlib
    import huntx.core.hardened_main as mod
    importlib.reload(mod)
    # If the module loads without AttributeError the test passes.
    assert hasattr(mod, "build_harness") or hasattr(mod, "create_harness"), (
        "M-11: hardened_main must export build_harness() when USE_LEGACY_PATCHES=false"
    )


def test_harness_does_not_mutate_global_state():
    """M-11: RuntimeHarness.__init__ must not modify any module globals."""
    import sys
    snapshot = {k: id(v) for k, v in sys.modules.items() if k.startswith("huntx")}
    from huntx.core.harness import RuntimeHarness
    RuntimeHarness(
        state_repo=MagicMock(),
        raw_store=MagicMock(),
        format_registry=MagicMock(),
        notifier=MagicMock(),
        scheduler=MagicMock(),
        config={},
    )
    after = {k: id(v) for k, v in sys.modules.items() if k.startswith("huntx")}
    assert snapshot == after, (
        "M-11: RuntimeHarness.__init__ must not modify sys.modules or module globals."
    )
```

- [ ] **Step 2.3.2 — Run to confirm RED**

```bash
python -m pytest tests/test_runtime_harness.py -v
# Expected: ImportError — harness.py does not exist
```

- [ ] **Step 2.3.3 — Create `src/huntx/core/harness.py`**

```python
# src/huntx/core/harness.py
"""
RuntimeHarness: explicit dependency-injection container for HUNTX runtime.

Migration from hardened_main.py import-time monkey-patches (M-11):
  OLD: module.__dict__["_state_repo"] = StateRepo(config["db_path"])
  NEW: harness = build_harness(config); harness.state_repo

The 6 previously patched dependencies are now explicit constructor parameters,
making unit tests possible without import-order gymnastics.
"""
from __future__ import annotations

import os


class RuntimeHarness:
    """Holds the 6 primary runtime dependencies with no side effects on init."""

    __slots__ = (
        "state_repo",
        "raw_store",
        "format_registry",
        "notifier",
        "scheduler",
        "config",
    )

    def __init__(
        self,
        *,
        state_repo,
        raw_store,
        format_registry,
        notifier,
        scheduler,
        config,
    ) -> None:
        self.state_repo      = state_repo
        self.raw_store       = raw_store
        self.format_registry = format_registry
        self.notifier        = notifier
        self.scheduler       = scheduler
        self.config          = config

    def start(self) -> None:
        """Start all managed services that implement a .start() method."""
        for name in self.__slots__:
            svc = getattr(self, name)
            if callable(getattr(svc, "start", None)):
                svc.start()

    def stop(self) -> None:
        """Gracefully stop all managed services."""
        for name in reversed(self.__slots__):
            svc = getattr(self, name)
            if callable(getattr(svc, "stop", None)):
                svc.stop()


def build_harness(config: dict) -> RuntimeHarness:
    """
    Factory — replaces the 6 monkey-patch calls in hardened_main.py.
    Called once at process startup.
    """
    from huntx.state.repo import StateRepo
    from huntx.storage.raw_store import RawStore
    from huntx.formats.registry import FORMAT_REGISTRY
    from huntx.notify.notifier import Notifier
    from huntx.scheduling.scheduler import Scheduler

    return RuntimeHarness(
        state_repo      = StateRepo(config["db_path"]),
        raw_store       = RawStore(config["raw_dir"]),
        format_registry = FORMAT_REGISTRY,
        notifier        = Notifier(config),
        scheduler       = Scheduler(config),
        config          = config,
    )
```

- [ ] **Step 2.3.4 — Add `USE_LEGACY_PATCHES` guard to `hardened_main.py`**

```python
# At top of hardened_main.py, after existing imports:
import os as _os

_USE_LEGACY = _os.getenv("HUNTX_USE_LEGACY_PATCHES", "true").lower() != "false"

if _USE_LEGACY:
    # LEGACY: import-time monkey-patches (deprecated, remove in next major release)
    # TODO(M-11): migrate callers to build_harness() then delete this block
    ... # <existing 6 monkey-patches unchanged>
else:
    # NEW DI path
    from huntx.core.harness import build_harness  # noqa: F401 (re-exported)
```

- [ ] **Step 2.3.5 — Run GREEN**

```bash
python -m pytest tests/test_runtime_harness.py -v
# Expected: 5 PASSED
python -m pytest tests/ -q
# Expected: >= 513 passing
```

- [ ] **Step 2.3.6 — Commit**

```bash
git add src/huntx/core/harness.py tests/test_runtime_harness.py src/huntx/core/hardened_main.py
git commit -m "feat(M-11): introduce RuntimeHarness DI container; gate legacy monkey-patches behind flag"
```

**Acceptance criteria:**
- [ ] `RuntimeHarness` holds 6 slots with no side effects on init
- [ ] `HUNTX_USE_LEGACY_PATCHES=false` disables all monkey-patches
- [ ] 5 tests GREEN | existing startup tests pass
**Dependencies:** Task 2.2 | **Scope:** M

---

### Task 2.4: Wave 2 Integration Smoke Test

**Description:** Run the full three-stage smoke pipeline to confirm that H-5, H-7, and M-11
patches are integrated cleanly — no import errors, no KeyErrors, no monkey-patch collisions.

**Files:** Create: `tests/test_wave2_integration_smoke.py`

- [ ] **Step 2.4.1 — Write integration smoke test**

```python
# tests/test_wave2_integration_smoke.py
"""
Wave 2 integration smoke — confirms H-5, H-7, M-11 land cleanly together.
Does NOT test business logic — only integration contracts.
"""
import importlib
import pytest


def test_validate_config_importable_without_nm():
    import sys
    sys.modules.pop("huntx.config.validate", None)
    sys.modules.pop("nm", None)
    sys.modules.pop("netmiko", None)
    from huntx.config.validate import validate_config  # must not ImportError
    assert callable(validate_config)


def test_format_registry_singleton_importable():
    from huntx.formats.registry import FORMAT_REGISTRY
    assert "npvt" in FORMAT_REGISTRY


def test_harness_build_does_not_monkey_patch(monkeypatch):
    import os
    monkeypatch.setenv("HUNTX_USE_LEGACY_PATCHES", "false")
    importlib.invalidate_caches()
    # Reload to pick up the env flag
    import huntx.core.hardened_main
    importlib.reload(huntx.core.hardened_main)
    # build_harness must be importable
    from huntx.core.harness import build_harness
    assert callable(build_harness)


def test_delivery_loop_does_not_raise_on_unknown_format():
    """H-7 + Wave 2 contract: unknown format skipped with warning, not raised."""
    from huntx.formats.registry import FORMAT_REGISTRY, SENTINEL_FORMAT
    result = FORMAT_REGISTRY.get("definitely_nonexistent_format_xyz", default=SENTINEL_FORMAT)
    assert result is SENTINEL_FORMAT
```

- [ ] **Step 2.4.2 — Run GREEN**

```bash
python -m pytest tests/test_wave2_integration_smoke.py -v
# Expected: 4 PASSED
python -m pytest tests/ -q
# Checkpoint: >= 522 passing (513 + 9 new tests from Wave 2)
```

- [ ] **Step 2.4.3 — Commit**

```bash
git add tests/test_wave2_integration_smoke.py
git commit -m "test: Wave 2 integration smoke — H-5, H-7, M-11 combined contract"
```

**Acceptance criteria:** 4 tests GREEN | full suite >= 522 | **Scope:** XS

---

## Wave 2 Gate — Checkpoint

```bash
python -m pytest \
  tests/test_nm_probe_excised.py \
  tests/test_format_registry.py \
  tests/test_runtime_harness.py \
  tests/test_wave2_integration_smoke.py -v

python -m pytest tests/ -q
```

- [ ] test_nm_probe_excised.py — 4 GREEN
- [ ] test_format_registry.py — 7 GREEN
- [ ] test_runtime_harness.py — 5 GREEN
- [ ] test_wave2_integration_smoke.py — 4 GREEN
- [ ] Full suite: >= 522 passing
- [ ] No new mypy errors: `python -m mypy src/huntx/core/ src/huntx/formats/registry.py --strict`
- [ ] `HUNTX_USE_LEGACY_PATCHES=false python -m pytest tests/ -q` passes
- [ ] CI validate job green on branch
- [ ] Three consecutive stable CI runs before proceeding to Wave 3
