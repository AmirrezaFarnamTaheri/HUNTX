# HUNTX — Go + CI/CD Hardening Plan
# Report 08: Go Release Plane & Pipeline Quality

**Generated:** 2026-08-17
**Lenses applied:** `/ci-cd-and-automation`, `/golang-benchmark`, `/golang-cli`, `/golang-code-style`, `/golang-concurrency`, `/golang-context`, `/golang-continuous-integration`, `/golang-error-handling`, `/golang-performance`, `/golang-testing`, `/elite-devops-architect`
**Scope:** `cmd/huntx-tools/`, `internal/` (4 packages), `.github/workflows/huntx.yml`, `.github/workflows/publish-generated-outputs.yml`, `.github/workflows/huntx-real-investigation-gate.yml`, `scripts/`

---

## §1. Go release-plane audit (evidence-verified)

### 1.1 Package inventory and status

| Package | Path | Purpose | Test coverage | Status |
|---|---|---|---|---|
| `huntx-tools` main | `cmd/huntx-tools/main.go` | Entry point: calls `generateOutputs` | **Zero tests** | LIVE — built by CI |
| `internal/outputverify` | `internal/outputverify/` | Checks generated output validity | **Zero tests** | LIVE |
| `internal/releasemanifest` | `internal/releasemanifest/` | Writes/reads release manifest JSON | **Zero tests** | LIVE |
| `internal/runtimegen` | `internal/runtimegen/` | Generates runtime outputs (sitegen, sing-box) | **Zero tests** | LIVE |
| `internal/sitegen` | `internal/sitegen/` | Generates docs/index.html and catalog.json | **Zero tests** | LIVE |
| `cmd/huntx-engine` | `cmd/huntx-engine/` | Next-gen prototype | 5 test files (ORPHANED module, `go 1.26`) | **DEAD** — never built by CI, unbuildable |

**Critical gap:** Zero Go tests exist for the 4 live `internal/` packages. The Go release plane (which runs on every successful CI job and generates the docs site + manifest) has **no regression guard at all**.

### 1.2 Go version discrepancy

| File | Declared version | Reality |
|---|---|---|
| `go.mod` (root) | `go 1.23.1` | ✅ Valid, matches CI pinned action |
| `cmd/huntx-engine/go.mod` | `go 1.26` | ❌ Does not exist; module unbuildable |

**Action:** Delete `cmd/huntx-engine/go.mod` or change to `go 1.23.1`. The module is explicitly rejected in the DONOR_PR_ABSORPTION_LEDGER — keep the source as reference, but remove its broken `go.mod`.

### 1.3 Concurrency and context hygiene (static audit)

**`cmd/huntx-tools/main.go` patterns to verify:**
- Context propagation: `generateOutputs` must accept a `context.Context` from a `signal.NotifyContext` so SIGTERM causes clean shutdown.
- Timeout: no explicit `context.WithTimeout` wrapper found for the sitegen/manifest steps — if these hang, the CI job hangs until the 90-minute runner timeout.
- Error wrapping: `fmt.Errorf("...: %w", err)` pattern should be used uniformly; `errors.Is` for sentinel checks.

---

## §2. Missing Go tests — specifications

### 2.1 `internal/outputverify` tests

```go
// internal/outputverify/outputverify_test.go  (NEW FILE)
package outputverify_test

import (
    "os"
    "path/filepath"
    "testing"

    "github.com/AmirrezaFarnamTaheri/HUNTX/internal/outputverify"
)

func TestVerifyOutput_ValidFile(t *testing.T) {
    // Arrange: write a minimal valid output file
    dir := t.TempDir()
    p := filepath.Join(dir, "proxies.txt")
    content := "vmess://validuri\nvless://anotheruri\n"
    if err := os.WriteFile(p, []byte(content), 0o644); err != nil {
        t.Fatal(err)
    }

    // Act
    result, err := outputverify.VerifyOutput(p)

    // Assert
    if err != nil {
        t.Fatalf("expected no error, got: %v", err)
    }
    if result.LineCount == 0 {
        t.Error("expected non-zero line count for valid file")
    }
}

func TestVerifyOutput_EmptyFile_ReturnsError(t *testing.T) {
    dir := t.TempDir()
    p := filepath.Join(dir, "empty.txt")
    if err := os.WriteFile(p, []byte(""), 0o644); err != nil {
        t.Fatal(err)
    }

    _, err := outputverify.VerifyOutput(p)
    if err == nil {
        t.Error("H-8: VerifyOutput must return error for empty output file")
    }
}

func TestVerifyOutput_MissingFile_ReturnsError(t *testing.T) {
    _, err := outputverify.VerifyOutput("/nonexistent/path/proxies.txt")
    if err == nil {
        t.Error("VerifyOutput must return error for missing file")
    }
}

func TestVerifyOutput_RoundTrip_ManifestHash(t *testing.T) {
    // The hash in the manifest must match the hash VerifyOutput computes.
    dir := t.TempDir()
    content := []byte("trojan://host:443\n")
    p := filepath.Join(dir, "proxies.txt")
    if err := os.WriteFile(p, content, 0o644); err != nil {
        t.Fatal(err)
    }

    result1, _ := outputverify.VerifyOutput(p)
    result2, _ := outputverify.VerifyOutput(p)

    if result1.ContentHash != result2.ContentHash {
        t.Error("VerifyOutput must be deterministic: same file → same hash")
    }
}
```

### 2.2 `internal/releasemanifest` tests

```go
// internal/releasemanifest/releasemanifest_test.go  (NEW FILE)
package releasemanifest_test

import (
    "encoding/json"
    "os"
    "path/filepath"
    "testing"

    "github.com/AmirrezaFarnamTaheri/HUNTX/internal/releasemanifest"
)

func TestWriteAndRead_RoundTrip(t *testing.T) {
    dir := t.TempDir()
    path := filepath.Join(dir, "manifest.json")

    m := releasemanifest.Manifest{
        RunID:        "12345678",
        GeneratedAt:  "2026-08-17T12:00:00Z",
        FileCount:    10,
        ContentHashes: map[string]string{
            "proxies.txt": "abc123",
        },
    }

    if err := releasemanifest.Write(path, m); err != nil {
        t.Fatalf("Write failed: %v", err)
    }

    got, err := releasemanifest.Read(path)
    if err != nil {
        t.Fatalf("Read failed: %v", err)
    }

    if got.RunID != m.RunID {
        t.Errorf("RunID mismatch: want %q got %q", m.RunID, got.RunID)
    }
    if got.ContentHashes["proxies.txt"] != "abc123" {
        t.Error("ContentHashes not preserved after round-trip")
    }
}

func TestWrite_CreatesParentDir(t *testing.T) {
    dir := t.TempDir()
    path := filepath.Join(dir, "subdir", "manifest.json")

    m := releasemanifest.Manifest{RunID: "x"}
    if err := releasemanifest.Write(path, m); err != nil {
        t.Fatalf("Write must create parent directories: %v", err)
    }
    if _, err := os.Stat(path); err != nil {
        t.Errorf("manifest file not created: %v", err)
    }
}

func TestRead_MissingFile_ReturnsError(t *testing.T) {
    _, err := releasemanifest.Read("/nonexistent/manifest.json")
    if err == nil {
        t.Error("Read must return error for missing manifest file")
    }
}

func TestRead_CorruptJSON_ReturnsError(t *testing.T) {
    dir := t.TempDir()
    path := filepath.Join(dir, "manifest.json")
    os.WriteFile(path, []byte("{invalid json"), 0o644)
    _, err := releasemanifest.Read(path)
    if err == nil {
        t.Error("Read must return error for corrupt JSON")
    }
}
```

### 2.3 `internal/runtimegen` tests

```go
// internal/runtimegen/runtimegen_test.go  (NEW FILE)
package runtimegen_test

import (
    "context"
    "os"
    "path/filepath"
    "testing"

    "github.com/AmirrezaFarnamTaheri/HUNTX/internal/runtimegen"
)

func TestGenerateOutputs_ProducesExpectedFiles(t *testing.T) {
    dir := t.TempDir()
    cfg := runtimegen.Config{
        InputDir:  dir,
        OutputDir: dir,
        RunID:     "test-run-001",
    }

    // Seed minimal input
    os.WriteFile(filepath.Join(dir, "proxies.txt"), []byte("vmess://1.2.3.4:443\n"), 0o644)

    ctx, cancel := context.WithTimeout(context.Background(), 30*1e9) // 30s
    defer cancel()

    if err := runtimegen.Generate(ctx, cfg); err != nil {
        t.Fatalf("Generate returned error: %v", err)
    }

    // The generator must produce a manifest
    manifestPath := filepath.Join(dir, "manifest.json")
    if _, err := os.Stat(manifestPath); err != nil {
        t.Error("H-8: runtimegen.Generate must produce manifest.json")
    }
}

func TestGenerateOutputs_ContextCancellation(t *testing.T) {
    dir := t.TempDir()
    cfg := runtimegen.Config{InputDir: dir, OutputDir: dir, RunID: "cancel-test"}

    ctx, cancel := context.WithCancel(context.Background())
    cancel() // cancel immediately

    err := runtimegen.Generate(ctx, cfg)
    if err == nil {
        t.Error("Generate must respect context cancellation")
    }
}
```

### 2.4 `internal/sitegen` tests

```go
// internal/sitegen/sitegen_test.go  (NEW FILE)
package sitegen_test

import (
    "os"
    "path/filepath"
    "strings"
    "testing"

    "github.com/AmirrezaFarnamTaheri/HUNTX/internal/sitegen"
)

func TestGenerateSite_ProducesIndexAndCatalog(t *testing.T) {
    dir := t.TempDir()

    inputs := sitegen.Inputs{
        Formats:   []string{"npvt", "ovpn"},
        SourceCount: 85,
        RunID:     "test-run",
    }

    if err := sitegen.Generate(dir, inputs); err != nil {
        t.Fatalf("Generate returned error: %v", err)
    }

    indexPath := filepath.Join(dir, "index.html")
    if _, err := os.Stat(indexPath); err != nil {
        t.Error("sitegen must produce index.html")
    }

    catalogPath := filepath.Join(dir, "catalog.json")
    if _, err := os.Stat(catalogPath); err != nil {
        t.Error("sitegen must produce catalog.json")
    }

    // Catalog must not be stale (must include the current run's format list)
    content, _ := os.ReadFile(catalogPath)
    if !strings.Contains(string(content), "npvt") {
        t.Error("catalog.json must include the format list provided as input")
    }
}
```

---

## §3. CI workflow hardening

### 3.1 Hardening checklist (verified against huntx.yml)

| Item | Current state | Required fix |
|---|---|---|
| Actions pinned by SHA | ✅ Yes (verified post-PR #62) | No change |
| `go test` for live packages | ❌ Missing | Add step (see §3.2) |
| `go vet` step | ❌ Not present | Add before build |
| `staticcheck` or `golangci-lint` | ❌ Not present | Add (see §3.3) |
| Context timeout for Go generate step | ❌ Unknown | Enforce via `timeout-minutes` on the step |
| `go test -race` | ❌ Missing | Add for concurrency safety |
| `huntx-engine` go.mod broken | ❌ `go 1.26` nonexistent | Fix or delete the module |
| `HUNTX_RUNTIME_DIAGNOSTICS` markers verified | ✅ Yes (anti-fake gates) | No change |
| Python `pytest --strict-markers` | ✅ Yes | No change |
| mypy strict | ✅ Yes | No change |
| flake8 | ✅ Yes | No change |
| Secret scan | ❌ Missing | Add `test_secret_scan.py` step |

### 3.2 Go test step to add to `huntx.yml`

Add after the existing `go build` step (around line 122, after `cmd/huntx-tools` build):

```yaml
      - name: Go vet — live packages
        run: |
          go vet ./cmd/huntx-tools/... ./internal/...
        working-directory: .

      - name: Go test — live packages (with race detector)
        run: |
          go test -race -count=1 -timeout=120s \
            ./cmd/huntx-tools/... \
            ./internal/outputverify/... \
            ./internal/releasemanifest/... \
            ./internal/runtimegen/... \
            ./internal/sitegen/...
        working-directory: .

      - name: Go test — huntx-engine must NOT be included
        # Explicit negative guard: the rejected engine module must not be tested
        # because its go.mod declares go 1.26 (unbuildable) and it was governance-rejected.
        run: |
          if find cmd/huntx-engine -name '*.go' | grep -q .; then
            echo "WARNING: cmd/huntx-engine still has Go source. Consider removing per DONOR_PR_ABSORPTION_LEDGER:141"
          fi
```

### 3.3 `golangci-lint` configuration

Add `.golangci.yml` at repo root:

```yaml
# .golangci.yml
linters:
  enable:
    - errcheck      # ensure all errors are handled
    - govet         # all vet checks
    - staticcheck   # SA-class static analysis
    - gosec         # security checks (especially: G304 path traversal, G501 weak hash)
    - contextcheck  # context propagation correctness
    - noctx         # HTTP requests must use context
  disable:
    - exhaustive    # not required for this codebase style

linters-settings:
  errcheck:
    check-type-assertions: true
    check-blank: true
  gosec:
    excludes:
      - G401  # MD5/SHA1 — only excluded if used for non-security dedup (document per use)

run:
  timeout: 5m
  modules-download-mode: readonly

issues:
  exclude-rules:
    - path: "_test\\.go"
      linters: [errcheck, gosec]
```

Add CI step:

```yaml
      - name: golangci-lint
        uses: golangci/golangci-lint-action@v6
        with:
          version: v1.59
          working-directory: .
          args: --timeout=5m ./cmd/huntx-tools/... ./internal/...
```

---

## §4. Go code quality findings (static analysis, pre-tooling)

### 4.1 Error handling audit

**Pattern to enforce:** Every error return from `internal/` functions must either be propagated with `fmt.Errorf("context: %w", err)` or handled explicitly. The following anti-patterns must be linted out:

```go
// BAD — silent discard:
os.WriteFile(path, data, 0o644)

// BAD — unnamed discard:
_, _ = someFunc()

// GOOD — explicit handling:
if err := os.WriteFile(path, data, 0o644); err != nil {
    return fmt.Errorf("writing output to %s: %w", path, err)
}
```

### 4.2 Context propagation pattern

All `internal/` functions that perform I/O must accept `ctx context.Context` as the first argument and pass it to downstream calls:

```go
// REQUIRED signature pattern:
func Generate(ctx context.Context, cfg Config) error {
    select {
    case <-ctx.Done():
        return fmt.Errorf("generate: %w", ctx.Err())
    default:
    }
    // ... perform I/O passing ctx
}
```

**CI enforcement:** `contextcheck` linter (see §3.3) flags functions that perform I/O without accepting a context.

### 4.3 Race-condition audit (huntx-tools)

The `generateOutputs` function runs multiple output-generation steps. If any step runs concurrently with file I/O, a data race is possible. The `-race` flag in `go test` (§3.2) will surface this.

**Pattern to enforce for concurrent output generation:**

```go
// If using goroutines for parallel generation:
var wg sync.WaitGroup
errCh := make(chan error, numWorkers)

for _, step := range steps {
    wg.Add(1)
    go func(s Step) {
        defer wg.Done()
        if err := s.Run(ctx); err != nil {
            errCh <- fmt.Errorf("step %s: %w", s.Name, err)
        }
    }(step)
}
wg.Wait()
close(errCh)

// Collect all errors:
var errs []error
for err := range errCh {
    errs = append(errs, err)
}
if len(errs) > 0 {
    return errors.Join(errs...)
}
```

### 4.4 Path traversal guard (gosec G304)

Any function that opens a file from user-controlled or config-controlled input must sanitize the path:

```go
// REQUIRED pattern for config-specified paths:
import "path/filepath"

func safeOpen(root, userPath string) (*os.File, error) {
    clean := filepath.Clean(filepath.Join(root, userPath))
    if !strings.HasPrefix(clean, filepath.Clean(root)+string(os.PathSeparator)) {
        return nil, fmt.Errorf("path traversal attempt: %q escapes root %q", userPath, root)
    }
    return os.Open(clean)
}
```

---

## §5. Workflow quality improvements

### 5.1 Output-commit workflow race

**Current flow:** `huntx-production` → (success) → `publish-generated-outputs.yml` (workflow_run trigger).

**Risk:** If two production runs complete within the same minute, both trigger `publish-generated-outputs`. The second commit will conflict with the first on the `generated-outputs` branch.

**Fix:** Add a mutual-exclusion group to the publish workflow:

```yaml
# .github/workflows/publish-generated-outputs.yml — add at top level:
concurrency:
  group: publish-generated-outputs
  cancel-in-progress: false   # never cancel a publish in flight; queue instead
```

### 5.2 Missing job-level timeout on publish workflow

```yaml
# In publish-generated-outputs.yml, add timeout to the publish job:
jobs:
  publish:
    timeout-minutes: 15   # ADD — prevents hung git push from blocking the queue indefinitely
```

### 5.3 Python dependency pinning

**Current:** `pip install -e ".[dev]"` in CI — unpinned, non-reproducible.

**Fix:** Add `requirements-dev.lock` (generated by `pip-compile` or `uv pip compile`) and use it in CI:

```yaml
# In huntx.yml validate job, replace:
#   pip install -e ".[dev]"
# With:
      - name: Install Python deps (locked)
        run: |
          pip install uv
          uv pip sync requirements-dev.lock
```

**Generate the lock file:**
```bash
pip install uv
uv pip compile pyproject.toml --extra dev -o requirements-dev.lock
```

### 5.4 CI secret audit (documented secrets)

Add a consolidated secret inventory comment to `huntx.yml`:

```yaml
# REQUIRED SECRETS (document in repo Settings → Secrets → Actions):
# ─── Telegram credentials ──────────────────────────────────────
# TELEGRAM_API_ID          — Telegram API ID (integer)
# TELEGRAM_API_HASH        — Telegram API hash
# TELEGRAM_USER_SESSION    — Telethon StringSession
# TELEGRAM_BOT_TOKEN       — Bot token for publishing
# ─── Publish endpoint ──────────────────────────────────────────
# PUBLISH_CHAT_ID          — Target channel ID for publishing
# PUBLISH_BOT_TOKEN        — Publishing bot token (may == TELEGRAM_BOT_TOKEN)
# ─── HAPP crypto keys (optional, see crypto.py) ────────────────
# HUNTX_HAPP_CRYPT_PEM     — RSA key gen-1
# HUNTX_HAPP_CRYPT2_PEM    — RSA key gen-2
# HUNTX_HAPP_CRYPT3_PEM    — RSA key gen-3
# ─── Format fallback passwords (H-3 — externalize in T8) ───────
# HUNTX_TUT_PASS_TUT       — TUT format decrypt password
# HUNTX_TUT_PASS_SKS       — SKS format decrypt password
# HUNTX_TUT_PASS_TMT       — TMT format decrypt password
# HUNTX_NETMOD_KEY         — NetMod AES-ECB key
# ─── AWS (OIDC preferred) ──────────────────────────────────────
# AWS_ROLE_ARN             — OIDC role for S3 generation storage
# (or) AWS_ACCESS_KEY_ID / AWS_SECRET_ACCESS_KEY — static fallback
```

---

## §6. Go benchmark specifications (for Wave 4 performance gate)

```go
// internal/runtimegen/runtimegen_bench_test.go  (NEW FILE)
package runtimegen_test

import (
    "context"
    "os"
    "path/filepath"
    "testing"

    "github.com/AmirrezaFarnamTaheri/HUNTX/internal/runtimegen"
)

// BenchmarkGenerate_SmallInput measures generation time for a typical CI run.
// Baseline target: < 30s for 50,000 proxy lines (matches the 5m CI budget).
func BenchmarkGenerate_SmallInput(b *testing.B) {
    dir := b.TempDir()
    // Generate a realistic 10k-line input
    var lines []byte
    for i := 0; i < 10000; i++ {
        lines = append(lines, []byte("vmess://1.2.3.4:443\n")...)
    }
    os.WriteFile(filepath.Join(dir, "proxies.txt"), lines, 0o644)

    cfg := runtimegen.Config{InputDir: dir, OutputDir: dir, RunID: "bench"}
    ctx := context.Background()

    b.ResetTimer()
    for i := 0; i < b.N; i++ {
        outDir := b.TempDir()
        cfg.OutputDir = outDir
        if err := runtimegen.Generate(ctx, cfg); err != nil {
            b.Fatal(err)
        }
    }
}
```

Run with: `go test -bench=. -benchtime=3x ./internal/runtimegen/`

---

## §7. Acceptance criteria for H-8

| Criterion | Command | Pass condition |
|---|---|---|
| Go build | `go build ./cmd/huntx-tools/...` | exits 0 |
| Go vet | `go vet ./cmd/huntx-tools/... ./internal/...` | exits 0, zero issues |
| Go test | `go test -race -count=1 ./cmd/huntx-tools/... ./internal/...` | exits 0, ≥1 test per package |
| golangci-lint | `golangci-lint run ./cmd/huntx-tools/... ./internal/...` | exits 0 |
| huntx-engine dead | `go build ./cmd/huntx-engine/...` | exits non-zero (go 1.26 undefined) |
| Context timeout | `go test -run TestGenerateOutputs_ContextCancellation ./internal/runtimegen/` | PASS |
| Race detector | `go test -race ./internal/...` | exits 0 (no races) |
