# Production Hardening, eBPF Acceleration & AI Routing Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Implement full-system E2E integration test suites across Python/Go planes (A1), high-performance eBPF/WireGuard kernel acceleration modules in Go (A4), and Multi-Armed Bandit / Z-score real-time AI proxy routing & traffic anomaly auto-mitigation in Python (A3).

**Architecture:**
1. **E2E Integration Harness (Python/Go)**: Coordinate `UnifiedOrchestrator`, `huntx-probe`, `huntx-daemon`, `TelemetryServer`, and `SupplyChainSigner` in an isolated integration pipeline.
2. **eBPF/WireGuard Acceleration (Go Engine)**: Build `cmd/huntx-engine/kernel/` providing zero-copy XDP packet filtering simulation, BPF filter rules, and Noise protocol WireGuard header parsing.
3. **AI Dynamic Routing & Anomaly Mitigation (Python)**: Build `src/huntx/pipeline/ai_router.py` (UCB1 / Thompson Sampling) and `src/huntx/pipeline/anomaly_mitigator.py` (statistical Z-score anomaly quarantine).

**Tech Stack:** Python 3.12 (Pytest, Asyncio), Go 1.22+ (Standard library, sync, atomic, net), WebSockets, SHA-256 Merkle Signatures, XDP/eBPF models, Multi-Armed Bandit (MAB/UCB1).

---

## Task Matrix & Breakdown

### Track 1: Production Hardening & E2E Live Integration Test Suite (A1)

#### Task 1.1: Comprehensive End-to-End Orchestration & Pipeline Lifecycle Integration Test
**Files:**
- Create: `tests/test_e2e_full_pipeline.py`
- Target Touchpoints: `src/huntx/orchestrator.py`, `src/huntx/pipeline/chain.py`, `src/huntx/pipeline/sign.py`, `src/huntx/formats/singbox.py`

- [ ] **Step 1: Write failing E2E test**
  - Verify complete flow: Raw input proxies -> Ingestion & Sanitization -> Dynamic Chain Synthesis -> Categorized Rule Generation -> Sing-box & Xray Compilation -> Cryptographic Manifest Signing -> Verification.
- [ ] **Step 2: Run test to verify RED**
  - Run: `uv run pytest tests/test_e2e_full_pipeline.py -v`
- [ ] **Step 3: Implement & refine pipeline glue if necessary**
- [ ] **Step 4: Run test to verify GREEN**
  - Run: `uv run pytest tests/test_e2e_full_pipeline.py -v`
- [ ] **Step 5: Commit**
  - `git commit -m "test(e2e): implement full-pipeline end-to-end integration test suite"`

#### Task 1.2: Go Daemon & Vantage Probe Cross-Plane E2E Integration Test
**Files:**
- Create: `cmd/huntx-daemon/e2e_integration_test.go`
- Target Touchpoints: `cmd/huntx-daemon/daemon.go`, `cmd/huntx-probe/probe.go`

- [ ] **Step 1: Write failing cross-plane integration test**
  - Launch live local Vantage probe server, ingest telemetry into daemon node pool, trigger health rotation, and verify `/status` and `/proxy.pac` dynamic responses.
- [ ] **Step 2: Run test to verify RED/Execution**
  - Run: `go test -race -v github.com/AmirrezaFarnamTaheri/HUNTX/cmd/huntx-daemon -run TestE2E`
- [ ] **Step 3: Implement minimal glue/fixes for daemon & probe interoperability**
- [ ] **Step 4: Run test to verify GREEN**
  - Run: `go test -race -v github.com/AmirrezaFarnamTaheri/HUNTX/cmd/huntx-daemon -run TestE2E`
- [ ] **Step 5: Commit**
  - `git commit -m "test(daemon): implement cross-plane live daemon and probe e2e integration test"`

---

### Track 2: High-Performance Custom Proxy Core Extension (A4)

#### Task 2.1: eBPF XDP Fast Packet Filter & BPF Map Simulator (Go)
**Files:**
- Create: `cmd/huntx-engine/kernel/xdp_filter.go`
- Create: `cmd/huntx-engine/kernel/xdp_filter_test.go`

- [ ] **Step 1: Write failing XDP filter tests**
  - Test XDP actions (`XDP_PASS`, `XDP_DROP`, `XDP_TX`), IP/Port blacklist BPF maps, rate-limiting counters, and sub-microsecond packet classification.
- [ ] **Step 2: Run test to verify RED**
  - Run: `go test -race -v github.com/AmirrezaFarnamTaheri/HUNTX/cmd/huntx-engine/kernel/...`
- [ ] **Step 3: Implement `XDPPacketFilter` and `BPFMap` in Go**
  - Zero-alloc ring buffer handling, CIDR lookup, and port filtering.
- [ ] **Step 4: Run test to verify GREEN**
  - Run: `go test -race -v github.com/AmirrezaFarnamTaheri/HUNTX/cmd/huntx-engine/kernel/...`
- [ ] **Step 5: Commit**
  - `git commit -m "feat(kernel): implement zero-alloc eBPF XDP packet filter and BPF map engine"`

#### Task 2.2: WireGuard Protocol Handshake & Noise IK Kernel Frame Parser (Go)
**Files:**
- Create: `cmd/huntx-engine/kernel/wireguard.go`
- Create: `cmd/huntx-engine/kernel/wireguard_test.go`

- [ ] **Step 1: Write failing WireGuard packet parser tests**
  - Test message types: `TypeHandshakeInitiation (1)`, `TypeHandshakeResponse (2)`, `TypeCookieReply (3)`, `TypeTransportData (4)`.
  - Validate 32-byte public key extraction, receiver/sender indices, and zero-allocation framing.
- [ ] **Step 2: Run test to verify RED**
  - Run: `go test -race -v github.com/AmirrezaFarnamTaheri/HUNTX/cmd/huntx-engine/kernel/...`
- [ ] **Step 3: Implement `WireGuardParser` and `NoiseHeader` structures**
- [ ] **Step 4: Run test to verify GREEN**
  - Run: `go test -race -v github.com/AmirrezaFarnamTaheri/HUNTX/cmd/huntx-engine/kernel/...`
- [ ] **Step 5: Commit**
  - `git commit -m "feat(kernel): implement WireGuard Noise IK protocol frame parser and benchmark suite"`

---

### Track 3: Real-Time Dynamic AI Proxy Routing & Traffic Anomaly Auto-Mitigation Engine (A3)

#### Task 3.1: Multi-Armed Bandit (MAB / UCB1) Dynamic Proxy Router (Python)
**Files:**
- Create: `src/huntx/pipeline/ai_router.py`
- Create: `tests/test_ai_router.py`

- [ ] **Step 1: Write failing MAB UCB1 router tests**
  - Test `UCB1ProxyRouter` exploration vs exploitation tradeoff ($Q_t(a) + c \sqrt{\frac{\ln t}{N_t(a)}}$), dynamic latency reward updates, reward normalization, and cold-start exploration.
- [ ] **Step 2: Run test to verify RED**
  - Run: `uv run pytest tests/test_ai_router.py -v`
- [ ] **Step 3: Implement `UCB1ProxyRouter` with decaying memory**
- [ ] **Step 4: Run test to verify GREEN**
  - Run: `uv run pytest tests/test_ai_router.py -v`
- [ ] **Step 5: Commit**
  - `git commit -m "feat(ai): implement Multi-Armed Bandit UCB1 dynamic proxy router"`

#### Task 3.2: Statistical Anomaly Detection & Auto-Mitigation Circuit Breaker (Python)
**Files:**
- Create: `src/huntx/pipeline/anomaly_mitigator.py`
- Create: `tests/test_anomaly_mitigator.py`

- [ ] **Step 1: Write failing anomaly mitigator tests**
  - Test Z-score latency spike detection ($z = \frac{x - \mu}{\sigma}$), jitter volatility tripwires, automatic quarantine state transitions (`HEALTHY` -> `SUSPECT` -> `QUARANTINED` -> `PROBATION`), and recovery probing.
- [ ] **Step 2: Run test to verify RED**
  - Run: `uv run pytest tests/test_anomaly_mitigator.py -v`
- [ ] **Step 3: Implement `AnomalyMitigator` & `CircuitBreakerState`**
- [ ] **Step 4: Run test to verify GREEN**
  - Run: `uv run pytest tests/test_anomaly_mitigator.py -v`
- [ ] **Step 5: Commit**
  - `git commit -m "feat(pipeline): implement statistical Z-score anomaly detector and auto-mitigation circuit breaker"`

---

## Checkpoints & Verification Suite

- **Checkpoint 1 (Track 1)**: `uv run pytest tests/test_e2e_full_pipeline.py` & `go test -race ./cmd/huntx-daemon/...`
- **Checkpoint 2 (Track 2)**: `go test -race -v ./cmd/huntx-engine/kernel/...` & `go test -bench=. -benchmem ./cmd/huntx-engine/kernel/...`
- **Checkpoint 3 (Track 3)**: `uv run pytest tests/test_ai_router.py tests/test_anomaly_mitigator.py`
- **Full Suite Gate**: `uv run pytest` (680+ tests) + `go test -race ./...` (All 12 Go packages).
