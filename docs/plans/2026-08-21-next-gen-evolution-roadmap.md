---
artifact_contract: ce-unified-plan/v1
artifact_readiness: implementation-ready
product_contract_source: ce-brainstorm
date: 2026-08-21
status: approved
title: HUNTX Next-Gen Multi-Track Evolution Roadmap & Architecture Plan
---

# HUNTX Next-Gen Multi-Track Evolution Roadmap Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Implement all 6 core evolution tracks for HUNTX: (1) Sing-box 1.10+ & Xray-core multi-outbound config compiler, (2) Go WebAssembly client-side decoder & worker pipeline, (3) Visual Rule & Profile Studio Cockpit, (4) Synthetic Trace Matrix & Anomaly Detection engine, (5) Real-Time Subscriptions Diff Sync Daemon, and (6) Go Zero-Allocation Micro-Benchmarking & Profiling Suite.

**Architecture:** A dual-plane architecture consisting of a Python ingestion and compiler core (`src/huntx/`) paired with an ultra-high performance Go Release & Telemetry engine (`cmd/huntx-engine/` and `cmd/huntx-wasm/`), delivering 100% offline client-side execution via WebAssembly in `docs/index.html` alongside robust backend daemons.

**Tech Stack:** Go 1.23.1 (Standard Library `crypto/tls`, `net`, `syscall/js`, `sync`, `log/slog`), Python 3.11+ (`asyncio`, `pytest`), Sing-box 1.10+ Schema, Xray-core 1.8+ Schema, Vanilla ES2024 JavaScript + Web Workers + WebAssembly, Tailwind CSS v4 / Sovereign Glass UI.

---

## 1. Source-Driven Authority & Official Standards

Every architectural choice, protocol AST, and configuration schema is grounded in official specifications:

| Component | Standard / Reference | Authority Citation |
| :--- | :--- | :--- |
| **Sing-box 1.10+ Schema** | SagerNet Sing-box Specification | https://sing-box.sagernet.org/configuration/ |
| **Xray-core 1.8+ Schema** | XTLS / Project X Foundation | https://xtls.github.io/config/ |
| **WebAssembly JS API** | W3C WebAssembly Specification | https://www.w3.org/TR/wasm-js-api-2/ |
| **FoxIO JA4 / JA4S** | FoxIO Network Security Standard | https://github.com/FoxIO-LLC/ja4 |
| **IETF TLS 1.3 Protocol** | IETF RFC 8446 | https://datatracker.ietf.org/doc/html/rfc8446 |
| **IETF ALPN Extension** | IETF RFC 7301 | https://datatracker.ietf.org/doc/html/rfc7301 |
| **HTTP Conditional Requests** | IETF RFC 9110 (ETag / If-None-Match) | https://datatracker.ietf.org/doc/html/rfc9110#section-13.1.1 |
| **Go Memory Allocation & Benchmarks** | Go Testing & Profiling Standard | https://pkg.go.dev/testing#Benchmark |

---

## 2. Dependency Graph & Architectural Decomposition

```text
┌─────────────────────────────────────────────────────────────────────────────────────────┐
│                                HUNTX DUAL-PLANE PLATFORM                                │
├─────────────────────────────────────────────┬───────────────────────────────────────────┤
│          PYTHON INGESTION & COMPILER        │          GO TELEMETRY & WASM ENGINE       │
│                                             │                                           │
│  [Track 1] Sing-box & Xray Config Compiler  │  [Track 2] WebAssembly Browser Engine     │
│  - src/huntx/formats/singbox.py             │  - cmd/huntx-wasm/main.go                 │
│  - src/huntx/formats/xray.py                │  - docs/assets/js/wasm-worker.js          │
│  - src/huntx/formats/compiler.py            │                                           │
│                                             │  [Track 4] Anomaly & Synthetic Tracing    │
│  [Track 5] Diff Sync & Ingestion Daemon     │  - cmd/huntx-engine/telemetry/            │
│  - src/huntx/pipeline/diff_sync.py          │                                           │
│  - cmd/huntx-engine/subsync/                │  [Track 6] Micro-Benchmarking & Alloc     │
│                                             │  - cmd/huntx-engine/benchmark/bench_test  │
├─────────────────────────────────────────────┴───────────────────────────────────────────┤
│                             BROWSER INTERACTION & STUDIO COCKPIT                        │
│                                                                                         │
│  [Track 3] Visual Rule & Profile Studio                                                 │
│  - docs/assets/js/rule-studio.js                                                        │
│  - docs/index.html (Sovereign Glass UI + Topology Graph)                                │
└─────────────────────────────────────────────────────────────────────────────────────────┘
```

---

## 3. Detailed Task Breakdown & Step-by-Step TDD Cycles

### TRACK 1: Sing-box 1.10+ & Xray-core Multi-Outbound Config Compiler

#### Task 1.1: Implement Sing-box 1.10+ Config Compiler
**Files:**
- Create: `src/huntx/formats/singbox.py`
- Test: `tests/test_singbox_compiler.py`

- [ ] **Step 1: Write failing unit test for Sing-box compilation**
- [ ] **Step 2: Run test to verify it fails (`uv run pytest tests/test_singbox_compiler.py -v`)**
- [ ] **Step 3: Write minimal implementation in `src/huntx/formats/singbox.py`**
- [ ] **Step 4: Run test to verify it passes (`uv run pytest tests/test_singbox_compiler.py -v`)**
- [ ] **Step 5: Commit**

#### Task 1.2: Implement Xray-core 1.8+ Config Compiler
**Files:**
- Create: `src/huntx/formats/xray.py`
- Test: `tests/test_xray_compiler.py`

- [ ] **Step 1: Write failing unit test for Xray compilation**
- [ ] **Step 2: Run test to verify it fails (`uv run pytest tests/test_xray_compiler.py -v`)**
- [ ] **Step 3: Write minimal implementation in `src/huntx/formats/xray.py`**
- [ ] **Step 4: Run test to verify it passes (`uv run pytest tests/test_xray_compiler.py -v`)**
- [ ] **Step 5: Commit**

---

### TRACK 2: WebAssembly (Wasm) Client-Side Ingestion & Decoder Engine

#### Task 2.1: Implement Go WebAssembly Entrypoint (`cmd/huntx-wasm/main.go`)
**Files:**
- Create: `cmd/huntx-wasm/main.go`
- Create: `cmd/huntx-wasm/wasm_test.go`

- [ ] **Step 1: Write unit tests for Wasm export helper functions**
- [ ] **Step 2: Run test to verify it passes locally in Go (`go test -v ./cmd/huntx-wasm/...`)**
- [ ] **Step 3: Implement Wasm JS Bridge in `cmd/huntx-wasm/main.go`**
- [ ] **Step 4: Build Wasm binary (`set GOOS=js&& set GOARCH=wasm&& go build -o docs/assets/huntx_engine.wasm ./cmd/huntx-wasm`)**
- [ ] **Step 5: Commit**

#### Task 2.2: Implement Web Worker Wasm Bridge (`docs/assets/js/wasm-worker.js`)
**Files:**
- Create: `docs/assets/js/wasm-worker.js`
- Modify: `docs/assets/js/decoder.js`

- [ ] **Step 1: Write Web Worker script with message handling**
- [ ] **Step 2: Connect `decoder.js` to Wasm Worker with automatic fallback**
- [ ] **Step 3: Verify client-side decoding in browser test suite**
- [ ] **Step 4: Commit**

---

### TRACK 3: Visual Rule & Profile Studio Cockpit

#### Task 3.1: Implement Visual Rule Studio Module (`docs/assets/js/rule-studio.js`)
**Files:**
- Create: `docs/assets/js/rule-studio.js`
- Modify: `docs/index.html`

- [ ] **Step 1: Create interactive Rule Studio state store and exporter**
- [ ] **Step 2: Wire Studio view into `docs/index.html`**
- [ ] **Step 3: Verify interactive rule addition and instant Sing-box/Xray JSON download**
- [ ] **Step 4: Commit**

---

### TRACK 4: Synthetic Trace Matrix & Anomaly Detection Engine

#### Task 4.1: Implement Go Telemetry & Jitter Scorer (`cmd/huntx-engine/telemetry/`)
**Files:**
- Create: `cmd/huntx-engine/telemetry/types.go`
- Create: `cmd/huntx-engine/telemetry/options.go`
- Create: `cmd/huntx-engine/telemetry/analyzer.go`
- Create: `cmd/huntx-engine/telemetry/analyzer_test.go`

- [ ] **Step 1: Write failing TDD test for Jitter and Packet Loss anomaly scoring**
- [ ] **Step 2: Run test to verify it fails (`go test -v ./cmd/huntx-engine/telemetry/...`)**
- [ ] **Step 3: Implement Analyzer and Functional Options in Go**
- [ ] **Step 4: Run test to verify it passes with race detector (`go test -race -v ./cmd/huntx-engine/telemetry/...`)**
- [ ] **Step 5: Commit**

---

### TRACK 5: Real-Time Subscriptions Aggregator & Diff Sync Daemon

#### Task 5.1: Implement Subscriptions Diff Sync Daemon (`cmd/huntx-engine/subsync/`)
**Files:**
- Create: `cmd/huntx-engine/subsync/types.go`
- Create: `cmd/huntx-engine/subsync/diff.go`
- Create: `cmd/huntx-engine/subsync/diff_test.go`

- [ ] **Step 1: Write failing TDD test for 3-way node diff synchronization**
- [ ] **Step 2: Run test to verify it fails (`go test -v ./cmd/huntx-engine/subsync/...`)**
- [ ] **Step 3: Implement Diff Sync Engine in Go**
- [ ] **Step 4: Run test to verify it passes with race detector (`go test -race -v ./cmd/huntx-engine/subsync/...`)**
- [ ] **Step 5: Commit**

---

### TRACK 6: Go Micro-Benchmarking & Zero-Allocation Memory Profiling Suite

#### Task 6.1: Implement High-Throughput Allocation Benchmark Suite
**Files:**
- Create: `cmd/huntx-engine/stream/bench_test.go`
- Create: `cmd/huntx-engine/chain/bench_test.go`

- [ ] **Step 1: Write allocation and memory throughput benchmarks**
- [ ] **Step 2: Run benchmark suite to record baseline ops/sec and memory allocations (`go test -bench=. -benchmem ./cmd/huntx-engine/...`)**
- [ ] **Step 3: Add profiling flags to `cmd/huntx-engine/main.go`**
- [ ] **Step 4: Commit**

---

## 4. Verification Checkpoints & Quality Gates

```markdown
## Checkpoint 1: Python Compilers (Track 1)
- [ ] `uv run pytest tests/test_singbox_compiler.py tests/test_xray_compiler.py` passes 100% GREEN.

## Checkpoint 2: WebAssembly Engine (Track 2)
- [ ] `huntx_engine.wasm` compiles clean with `GOOS=js GOARCH=wasm`.
- [ ] Wasm unit tests pass in Node.js / Go test runner.

## Checkpoint 3: Visual Rule Studio (Track 3)
- [ ] `docs/index.html` loads without console errors on `file:///`.
- [ ] Interactive rules render and export valid JSON configs.

## Checkpoint 4: Go Engine Extensions (Tracks 4, 5, 6)
- [ ] `go test -race -v ./...` passes 100% across all Go packages.
- [ ] `go test -bench=. -benchmem ./...` verifies zero-allocation hot paths.
```

---

## 5. Risks and Mitigations

| Risk | Impact | Mitigation Strategy |
| :--- | :--- | :--- |
| **Wasm binary size exceeds browser budget** | Medium | Compile with `-ldflags="-s -w"` and strip debug symbols to achieve <2.5MB payload. |
| **Sing-box schema mismatch with legacy proxies** | High | Use strict schema validators and default to standard fallback selectors. |
| **Goroutine leak in SubSync poller** | Critical | Enforce `context.WithTimeout` and context cancellation select branches in all long-running loops. |
