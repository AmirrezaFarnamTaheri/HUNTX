# HUNTX Remediation Plan — Part 3: Waves 3 & 4
# Parts: [Part 1] [Part 2] [Part 3 — Waves 3 & 4] [Part 4]

## Wave 3: Feature/Validate — Complete Dead Stubs

Entry gate: All Wave 2 tests green. Full suite >= 522 passing. 3 consecutive stable CI runs.
Defects: H-4 (secure-tier dead stub), M-1 (nm residual), M-5 (rate-limit gap), C3 (npvtsub parity).

---

### Task 3.1: H-4 — Secure-Tier Gate

Description: config/validate.py references secure_tier but the enforcement stub always returns True.
The gate must actually evaluate config["secure_tier"] and raise SecureTierError on violation.
Feature flag HUNTX_SECURE_TIER_ENABLED allows gradual rollout.

Files:
- Create: tests/test_secure_tier_gate.py
- Create: src/huntx/config/errors.py
- Modify: src/huntx/config/validate.py

Step 3.1.1 — Write failing tests:

```python
# tests/test_secure_tier_gate.py
import os
import pytest


def test_secure_tier_error_importable():
    from huntx.config.errors import SecureTierError
    assert issubclass(SecureTierError, Exception)


def test_gate_raises_for_insecure_config(monkeypatch):
    """H-4: validate_config must raise SecureTierError when tls=False and secure_tier=True."""
    monkeypatch.setenv("HUNTX_SECURE_TIER_ENABLED", "true")
    from huntx.config.validate import validate_config
    from huntx.config.errors import SecureTierError
    with pytest.raises(SecureTierError):
        validate_config({"secure_tier": True, "tls": False, "sources": [], "bot": {}})


def test_gate_passes_for_secure_config(monkeypatch):
    """H-4: no exception when all security requirements met."""
    monkeypatch.setenv("HUNTX_SECURE_TIER_ENABLED", "true")
    from huntx.config.validate import validate_config
    validate_config({"secure_tier": True, "tls": True, "auth_required": True,
                     "sources": [], "bot": {}})


def test_gate_disabled_when_flag_false(monkeypatch):
    """H-4: gate must be a no-op when HUNTX_SECURE_TIER_ENABLED=false."""
    monkeypatch.setenv("HUNTX_SECURE_TIER_ENABLED", "false")
    from huntx.config.validate import validate_config
    from huntx.config.errors import SecureTierError
    try:
        validate_config({"secure_tier": True, "tls": False, "sources": [], "bot": {}})
    except SecureTierError:
        pytest.fail("H-4: gate fired even though flag=false")


def test_gate_not_evaluated_when_key_absent():
    """H-4: configs without secure_tier key must not trigger the gate."""
    from huntx.config.validate import validate_config
    validate_config({"sources": [], "bot": {}})


def test_error_message_names_violated_policy(monkeypatch):
    """H-4: SecureTierError must include the policy name in the message."""
    monkeypatch.setenv("HUNTX_SECURE_TIER_ENABLED", "true")
    from huntx.config.validate import validate_config
    from huntx.config.errors import SecureTierError
    with pytest.raises(SecureTierError) as exc_info:
        validate_config({"secure_tier": True, "tls": False, "sources": [], "bot": {}})
    assert "tls" in str(exc_info.value).lower() or "secure" in str(exc_info.value).lower()
```

Step 3.1.2 — Run to confirm RED:
  python -m pytest tests/test_secure_tier_gate.py -v

Step 3.1.3 — Create src/huntx/config/errors.py:

```python
# src/huntx/config/errors.py
class ConfigError(ValueError):
    """Base class for all configuration errors."""

class SecureTierError(ConfigError):
    """H-4: raised when a secure-tier policy requirement is violated."""
    def __init__(self, violated_policy: str, detail: str = "") -> None:
        self.violated_policy = violated_policy
        msg = f"Secure-tier policy violated: {violated_policy!r}"
        if detail:
            msg += f" — {detail}"
        super().__init__(msg)
```

Step 3.1.4 — Implement gate in validate.py:

```python
# validate.py additions:
import os as _os
_SECURE_TIER_ENABLED = _os.getenv("HUNTX_SECURE_TIER_ENABLED", "false").lower() == "true"

_SECURE_TIER_POLICIES = [
    ("tls",           lambda cfg: bool(cfg.get("tls"))),
    ("auth_required", lambda cfg: bool(cfg.get("auth_required", True))),
]

def _check_secure_tier(config: dict) -> None:
    if not _SECURE_TIER_ENABLED or not config.get("secure_tier"):
        return
    from huntx.config.errors import SecureTierError
    for name, pred in _SECURE_TIER_POLICIES:
        if not pred(config):
            raise SecureTierError(name, f"config[{name!r}] must be truthy for secure_tier=True")

# In validate_config body — add as first call:
def validate_config(config: dict) -> None:
    _check_secure_tier(config)
    ... # existing logic unchanged
```

Step 3.1.5 — Run GREEN:
  python -m pytest tests/test_secure_tier_gate.py -v  # Expected: 6 PASSED
  python -m pytest tests/ -q

Step 3.1.6 — Commit:
  git add tests/test_secure_tier_gate.py src/huntx/config/errors.py src/huntx/config/validate.py
  git commit -m "fix(H-4): implement secure-tier enforcement gate; gate behind HUNTX_SECURE_TIER_ENABLED"

Acceptance criteria:
- [ ] SecureTierError raised for insecure config when flag=true
- [ ] Flag=false makes gate a no-op
- [ ] 6 tests GREEN
Dependencies: Task 2.1 | Scope: S

---

### Task 3.2: M-1 — Excise nm from Secure-Tier Path

Description: After H-5 removed the nm probe from validate_config, residual nm references may
remain inside the secure-tier enforcement path. Audit and excise all remaining nm usage.

Files:
- Create: tests/test_nm_fully_excised.py
- Modify: src/huntx/config/validate.py (if residual nm refs found)

Step 3.2.1 — Audit for residual nm references:

  grep -rn "import nm\|from nm\|_NM_AVAILABLE\|netmiko\|paramiko" \
       src/huntx/config/ src/huntx/core/ | tee tasks/nm_residual_audit.txt

Step 3.2.2 — Write exhaustive excision test:

```python
# tests/test_nm_fully_excised.py
import pathlib
import pytest

_ROOT = pathlib.Path(__file__).parent.parent / "src" / "huntx"
_TARGETS = ["config", "core"]
_FORBIDDEN = [
    "import nm", "from nm", "import netmiko", "from netmiko",
    "import paramiko", "from paramiko", "_NM_AVAILABLE", "nm.get_device",
]

@pytest.mark.parametrize("pattern", _FORBIDDEN)
def test_nm_pattern_absent_from_config_core(pattern):
    matches = []
    for pkg in _TARGETS:
        for f in (_ROOT / pkg).rglob("*.py"):
            if pattern in f.read_text(encoding="utf-8"):
                matches.append(str(f.relative_to(_ROOT.parent.parent)))
    assert not matches, (
        f"M-1: pattern {pattern!r} still present in config/core:\n"
        + "\n".join(f"  {m}" for m in matches)
    )
```

Step 3.2.3 — Fix any remaining references found.
  For each match: delete the nm call, replace with:
  # TODO(M-1): nm removed. Implement SSH probe via dedicated adapter if needed.

Step 3.2.4 — Run GREEN:
  python -m pytest tests/test_nm_fully_excised.py -v
  python -m pytest tests/ -q

Step 3.2.5 — Commit:
  git add tests/test_nm_fully_excised.py src/huntx/config/ tasks/nm_residual_audit.txt
  git commit -m "fix(M-1): excise all residual nm references from config/core packages"

Acceptance criteria:
- [ ] All _FORBIDDEN patterns absent from config/ and core/
- [ ] All parametrized tests GREEN
Dependencies: Task 2.1, Task 3.1 | Scope: XS-S

---

### Task 3.3: M-5 — Rate-Limit All Bot Commands

Description: Only 3 of 11 bot commands apply rate-limiting. Introduce rate_limit decorator
in bot/ratelimit.py and apply it to all missing handlers.

Files:
- Create: src/huntx/bot/ratelimit.py
- Create: tests/test_bot_ratelimit.py
- Modify: src/huntx/bot/handlers.py

Step 3.3.1 — Write failing tests:

```python
# tests/test_bot_ratelimit.py
import asyncio
import pytest


def test_rate_limit_module_importable():
    from huntx.bot.ratelimit import rate_limit, RateLimitExceeded
    assert callable(rate_limit)
    assert issubclass(RateLimitExceeded, Exception)


@pytest.mark.asyncio
async def test_allows_first_call():
    from huntx.bot.ratelimit import rate_limit

    @rate_limit(calls=3, period=60)
    async def handler(user_id: str) -> str:
        return "ok"

    assert await handler("u1") == "ok"


@pytest.mark.asyncio
async def test_blocks_after_threshold():
    from huntx.bot.ratelimit import rate_limit, RateLimitExceeded

    @rate_limit(calls=2, period=60)
    async def handler(user_id: str) -> str:
        return "ok"

    await handler("ux")
    await handler("ux")
    with pytest.raises(RateLimitExceeded):
        await handler("ux")


@pytest.mark.asyncio
async def test_is_per_user():
    """M-5: rate limiting must be per user_id, not global."""
    from huntx.bot.ratelimit import rate_limit, RateLimitExceeded

    @rate_limit(calls=1, period=60)
    async def handler(user_id: str) -> str:
        return "ok"

    await handler("user_a")
    assert await handler("user_b") == "ok"


@pytest.mark.asyncio
async def test_resets_after_period():
    from huntx.bot.ratelimit import rate_limit, RateLimitExceeded

    @rate_limit(calls=1, period=0.05)
    async def handler(user_id: str) -> str:
        return "ok"

    await handler("uz")
    with pytest.raises(RateLimitExceeded):
        await handler("uz")
    await asyncio.sleep(0.06)
    assert await handler("uz") == "ok"


def test_all_handlers_decorated():
    """M-5: every on_* handler in handlers.py must use @rate_limit."""
    import ast
    import pathlib
    src = (pathlib.Path(__file__).parent.parent / "src/huntx/bot/handlers.py").read_text()
    tree = ast.parse(src)
    undecorated = []
    for node in ast.walk(tree):
        if isinstance(node, ast.AsyncFunctionDef) and node.name.startswith("on_"):
            has_rl = any(
                "rate_limit" in ast.dump(d)
                for d in node.decorator_list
            )
            if not has_rl:
                undecorated.append(node.name)
    assert not undecorated, f"M-5: handlers missing @rate_limit: {sorted(undecorated)}"
```

Step 3.3.2 — Run to confirm RED:
  python -m pytest tests/test_bot_ratelimit.py -v

Step 3.3.3 — Create src/huntx/bot/ratelimit.py:

```python
# src/huntx/bot/ratelimit.py
from __future__ import annotations
import asyncio, collections, functools, time
from typing import Callable


class RateLimitExceeded(Exception):
    def __init__(self, user_id: str, calls: int, period: float) -> None:
        self.user_id = user_id
        super().__init__(f"Rate limit: {user_id!r} exceeded {calls} calls/{period}s")


def rate_limit(calls: int, period: float) -> Callable:
    """Per-user sliding window rate limiter. First arg of decorated func must be user_id."""
    _windows: dict[str, collections.deque] = collections.defaultdict(collections.deque)

    def decorator(func: Callable) -> Callable:
        @functools.wraps(func)
        async def wrapper(user_id: str, *args, **kwargs):
            now = time.monotonic()
            dq = _windows[user_id]
            while dq and now - dq[0] >= period:
                dq.popleft()
            if len(dq) >= calls:
                raise RateLimitExceeded(user_id=user_id, calls=calls, period=period)
            dq.append(now)
            return await func(user_id, *args, **kwargs)
        return wrapper

    return decorator
```

Step 3.3.4 — Apply @rate_limit to 8 missing handlers in handlers.py:

```python
# handlers.py — add import at top:
from huntx.bot.ratelimit import rate_limit

# Wrap every on_* handler (default: 5 calls/60s; admin commands: 20/60s):
@rate_limit(calls=5, period=60)
@client.on(events.NewMessage(pattern=r"^/start$"))
async def on_start(event):
    user_id = str(event.sender_id)
    ...

@rate_limit(calls=20, period=60)
@client.on(events.NewMessage(pattern=r"^/approve\s+(\S+)$"))
async def on_approve(event):
    ...
```

Step 3.3.5 — Run GREEN:
  python -m pytest tests/test_bot_ratelimit.py -v  # 6 PASSED
  python -m pytest tests/ -q

Step 3.3.6 — Commit:
  git add src/huntx/bot/ratelimit.py tests/test_bot_ratelimit.py src/huntx/bot/handlers.py
  git commit -m "fix(M-5): add per-user rate limiting to all bot command handlers"

Acceptance criteria:
- [ ] All on_* handlers decorated with @rate_limit
- [ ] 6 tests GREEN | per-user isolation confirmed
Dependencies: Task 1.5 | Scope: M

---

### Task 3.4: C3 — npvtsub Validation Parity

Description: formats/npvtsub.py skips field-level validation that all other format parsers
perform. Missing validation allows malformed records to reach the delivery loop silently.

Files:
- Create: tests/test_npvtsub_validation.py
- Modify: src/huntx/formats/npvtsub.py

Step 3.4.1 — Write failing validation tests:

```python
# tests/test_npvtsub_validation.py
import pytest


def _parse(data: dict):
    from huntx.formats.npvtsub import NpvtSubFormat
    return NpvtSubFormat().parse(data)


def test_rejects_missing_host():
    with pytest.raises((ValueError, KeyError), match="host|required"):
        _parse({"port": 443})


def test_rejects_invalid_port():
    with pytest.raises(ValueError, match="port"):
        _parse({"host": "1.2.3.4", "port": 99999})


def test_rejects_non_string_host():
    with pytest.raises((ValueError, TypeError)):
        _parse({"host": 12345, "port": 443})


def test_accepts_valid_record():
    result = _parse({"host": "1.2.3.4", "port": 443, "protocol": "tcp"})
    assert result is not None


def test_coerces_port_string_to_int():
    result = _parse({"host": "1.2.3.4", "port": "443"})
    assert result is not None


def test_rejects_empty_host():
    with pytest.raises(ValueError, match="host"):
        _parse({"host": "", "port": 443})


def test_rejects_bad_bytes_host():
    with pytest.raises((ValueError, UnicodeDecodeError)):
        _parse({"host": b"\xff\xfe", "port": 443})


def test_parity_with_ovpnsub():
    """C3: both parsers must validate 'host'."""
    import inspect
    from huntx.formats.npvtsub import NpvtSubFormat
    from huntx.formats.ovpnsub import OvpnSubFormat
    assert "host" in inspect.getsource(NpvtSubFormat.parse)
    assert "host" in inspect.getsource(OvpnSubFormat.parse)
```

Step 3.4.2 — Run to confirm RED:
  python -m pytest tests/test_npvtsub_validation.py -v

Step 3.4.3 — Add validation to NpvtSubFormat.parse:

```python
# In src/huntx/formats/npvtsub.py — at start of parse():
_REQUIRED = ("host",)
_PORT_MIN, _PORT_MAX = 1, 65535

def parse(self, data: dict) -> dict:
    # C3: required-field check
    for field in _REQUIRED:
        if field not in data:
            raise ValueError(f"npvtsub: required field {field!r} missing")

    host = data["host"]
    if isinstance(host, bytes):
        host = host.decode("utf-8")  # raises UnicodeDecodeError on bad bytes
    if not isinstance(host, str) or not host.strip():
        raise ValueError(f"npvtsub: 'host' must be a non-empty string, got {type(host)}")
    data = dict(data)
    data["host"] = host.strip()

    raw_port = data.get("port")
    if raw_port is not None:
        try:
            port = int(raw_port)
        except (TypeError, ValueError):
            raise ValueError(f"npvtsub: 'port' must be numeric, got {raw_port!r}")
        if not (_PORT_MIN <= port <= _PORT_MAX):
            raise ValueError(f"npvtsub: 'port' {port} out of valid range")
        data["port"] = port

    return data  # continue to existing parse logic
```

Step 3.4.4 — Run GREEN:
  python -m pytest tests/test_npvtsub_validation.py -v  # 8 PASSED
  python -m pytest tests/ -q

Step 3.4.5 — Commit:
  git add tests/test_npvtsub_validation.py src/huntx/formats/npvtsub.py
  git commit -m "fix(C3): add field validation to NpvtSubFormat.parse — parity with ovpnsub"

Acceptance criteria:
- [ ] 8 tests GREEN | required fields enforced | port range validated
Dependencies: Task 2.2 | Scope: S

---

## Wave 3 Gate — Checkpoint

  python -m pytest tests/test_secure_tier_gate.py tests/test_nm_fully_excised.py \
    tests/test_bot_ratelimit.py tests/test_npvtsub_validation.py -v
  python -m pytest tests/ -q

- [ ] test_secure_tier_gate.py — 6 GREEN
- [ ] test_nm_fully_excised.py — all parametrized GREEN
- [ ] test_bot_ratelimit.py — 6 GREEN
- [ ] test_npvtsub_validation.py — 8 GREEN
- [ ] Full suite: >= 541 passing
- [ ] python -m mypy src/huntx/config/ src/huntx/bot/ --strict — 0 new errors
- [ ] CI validate job green on branch

---

## Wave 4: Go + CI Hardening

Entry gate: All Wave 3 tests green. Full suite >= 541 passing.
Defects: H-8 (4 Go packages untested), H-9 (no race tests), H-10 (golangci-lint not in CI).

---

### Task 4.1: H-8 — Go Package Baselines (test-first)

Description: All 4 live Go packages have zero test files. Write table-driven tests for every
exported function before touching production code.

Files (create all):
- internal/outputverify/outputverify_test.go
- internal/releasemanifest/releasemanifest_test.go
- internal/runtimegen/runtimegen_test.go
- internal/sitegen/sitegen_test.go

Step 4.1.1 — Discover exported symbols:
  go doc ./internal/outputverify/...
  go doc ./internal/releasemanifest/...
  go doc ./internal/runtimegen/...
  go doc ./internal/sitegen/...
  # Save to tasks/go_exported_symbols.txt

Step 4.1.2 — Write outputverify_test.go (adapt field names from go doc output):

```go
// internal/outputverify/outputverify_test.go
package outputverify_test

import "testing"
import "github.com/huntx/internal/outputverify"

func TestVerify_NilInputReturnsError(t *testing.T) {
    if err := outputverify.Verify(nil); err == nil {
        t.Fatal("H-8: Verify(nil) must return error")
    }
}

func TestVerify_Table(t *testing.T) {
    cases := []struct {
        name    string
        input   *outputverify.Output
        wantErr bool
    }{
        {"nil", nil, true},
        {"empty_files", &outputverify.Output{Files: []string{}}, true},
        {"no_hash", &outputverify.Output{Files: []string{"f.html"}}, true},
        {"valid", &outputverify.Output{Files: []string{"f.html"}, Hash: "h1"}, false},
    }
    for _, tc := range cases {
        t.Run(tc.name, func(t *testing.T) {
            err := outputverify.Verify(tc.input)
            if (err != nil) != tc.wantErr {
                t.Errorf("got err=%v wantErr=%v", err, tc.wantErr)
            }
        })
    }
}
```

Step 4.1.3 — Write releasemanifest_test.go (adapt types from go doc):

```go
// internal/releasemanifest/releasemanifest_test.go
package releasemanifest_test

import "testing"
import "github.com/huntx/internal/releasemanifest"

func TestBuild_EmptyVersionErrors(t *testing.T) {
    if _, err := releasemanifest.Build("", nil); err == nil {
        t.Fatal("H-8: Build empty version must error")
    }
}

func TestBuild_ValidManifest(t *testing.T) {
    m, err := releasemanifest.Build("1.0.0", []string{"dist/app.tar.gz"})
    if err != nil { t.Fatalf("Build failed: %v", err) }
    if m.Version != "1.0.0" { t.Errorf("got version %q", m.Version) }
}
```

Step 4.1.4 — Write runtimegen_test.go (adapt Config fields from go doc):

```go
// internal/runtimegen/runtimegen_test.go
package runtimegen_test

import "testing"
import "github.com/huntx/internal/runtimegen"

func TestGenerate_NilErrors(t *testing.T) {
    if _, err := runtimegen.Generate(nil); err == nil {
        t.Fatal("H-8: Generate(nil) must error")
    }
}

func TestGenerate_ValidConfig(t *testing.T) {
    cfg := &runtimegen.Config{OutputDir: t.TempDir()}
    if _, err := runtimegen.Generate(cfg); err != nil {
        t.Fatalf("Generate failed: %v", err)
    }
}
```

Step 4.1.5 — Write sitegen_test.go (adapt Options from go doc):

```go
// internal/sitegen/sitegen_test.go
package sitegen_test

import "os"
import "testing"
import "github.com/huntx/internal/sitegen"

func TestBuild_NilErrors(t *testing.T) {
    if err := sitegen.Build(nil); err == nil {
        t.Fatal("H-8: Build(nil) must error")
    }
}

func TestBuild_OutputDirCreated(t *testing.T) {
    dir := t.TempDir() + "/out"
    if err := sitegen.Build(&sitegen.Options{OutputDir: dir, SourceDir: "."}); err != nil {
        t.Fatalf("Build failed: %v", err)
    }
    if _, err := os.Stat(dir); os.IsNotExist(err) {
        t.Fatal("OutputDir not created")
    }
}
```

Step 4.1.6 — Run to confirm RED:
  go test -v ./internal/...
  # Expected: compilation errors or test failures — correct RED state

Step 4.1.7 — Make tests GREEN:
  For any "undefined: pkg.FuncName" error: add minimal implementation to the production file.
  Iterate until: go test ./internal/... exits 0

Step 4.1.8 — Commit:
  git add internal/*/
  git commit -m "test(H-8): write baseline table-driven tests for all 4 Go internal packages"

Acceptance criteria:
- [ ] go test ./internal/... exits 0
- [ ] >= 3 table-driven test cases per package
- [ ] No production code changed beyond making tests compile
Dependencies: Task 3.4 | Scope: M

---

### Task 4.2: H-9 — Race-Condition Tests

Step 4.2.1 — Run race detector:
  go test -race -count=2 ./internal/... 2>&1 | tee tasks/go_race_report.txt

Step 4.2.2 — For each DATA RACE entry:
  1. Document in tasks/go_race_report.txt
  2. Write a TestXxx_Race that reliably triggers it
  3. Fix with sync.Mutex / sync/atomic / channel
  4. Verify: go test -race -run TestXxx_Race ./internal/pkg/

Step 4.2.3 — Run clean:
  go test -race -count=3 ./internal/...
  # Expected: exit 0, no "DATA RACE" in output

Step 4.2.4 — Commit:
  git add internal/ tasks/go_race_report.txt
  git commit -m "fix(H-9): resolve all race conditions in Go internal packages (-race clean)"

Acceptance criteria:
- [ ] go test -race -count=3 ./internal/... exits 0 with no DATA RACE
- [ ] Each race documented in go_race_report.txt
Dependencies: Task 4.1 | Scope: S-M

---

### Task 4.3: H-10 — golangci-lint Enforcement in CI

Files:
- Create: .golangci.yml
- Modify: .github/workflows/validate.yml

Step 4.3.1 — Create .golangci.yml:

```yaml
# .golangci.yml
run:
  timeout: 5m
  modules-download-mode: readonly

linters:
  enable:
    - errcheck
    - gosimple
    - govet
    - ineffassign
    - staticcheck
    - unused
    - gofmt
    - goimports
    - revive
    - gosec
    - bodyclose
    - noctx

linters-settings:
  gosec:
    excludes:
      - G304  # allow file path construction for raw store

issues:
  exclude-rules:
    - path: "_test.go"
      linters: [gosec, errcheck]
  max-issues-per-linter: 0
  max-same-issues: 0
```

Step 4.3.2 — Run locally to discover violations:
  golangci-lint run ./... 2>&1 | tee tasks/golangci_initial_report.txt

Step 4.3.3 — Fix all lint violations:
  errcheck: wrap ignored errors with _ = expr or handle them
  revive exported: add godoc comments to all exported symbols
  gosec G104: explicitly handle or annotate with //nolint:gosec

Step 4.3.4 — Confirm clean:
  golangci-lint run ./...
  # Expected: exit 0

Step 4.3.5 — Add to CI workflow in .github/workflows/validate.yml:

```yaml
  golangci-lint:
    name: Go Lint
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-go@v5
        with:
          go-version: '1.23.1'
      - name: golangci-lint
        uses: golangci/golangci-lint-action@v6
        with:
          version: v1.59
          args: --timeout=5m
```

Step 4.3.6 — Commit:
  git add .golangci.yml .github/workflows/validate.yml tasks/golangci_initial_report.txt
  git commit -m "fix(H-10): add golangci-lint config + CI enforcement; fix all violations"

Acceptance criteria:
- [ ] .golangci.yml covers 10+ linters including errcheck, gosec, revive
- [ ] golangci-lint run ./... exits 0
- [ ] CI lint job blocks merge on failure
Dependencies: Task 4.2 | Scope: M

---

### Task 4.4: Go CI Integration Verification

Step 4.4.1:  go build ./...                          # must exit 0
Step 4.4.2:  go test -race ./internal/... -coverprofile=tasks/go_coverage.out
             go tool cover -func=tasks/go_coverage.out | tail -1
             # Coverage must be >= 60% per package
Step 4.4.3:  golangci-lint run ./...                 # must exit 0

Step 4.4.4 — Commit:
  git add tasks/go_coverage.out
  git commit -m "ci: add go coverage report for Wave 4 gate"

Acceptance criteria:
- [ ] go build ./... exits 0
- [ ] go test -race exits 0
- [ ] golangci-lint exits 0
- [ ] Per-package coverage >= 60%
Dependencies: Task 4.3 | Scope: XS

---

## Wave 4 Gate — Checkpoint

  # Python suite
  python -m pytest tests/ -q

  # Go suite
  go test -race -count=3 ./internal/...
  golangci-lint run ./...
  go build ./...

- [ ] All Python tests: >= 541 passing
- [ ] go test -race -count=3 ./internal/... — exit 0, no DATA RACE
- [ ] golangci-lint run ./... — exit 0
- [ ] go build ./... — exit 0
- [ ] Per-package Go coverage >= 60%
- [ ] CI validate + golangci-lint jobs green on branch
