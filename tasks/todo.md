# HUNTX Multi-Track Evolution Task Checklist

- [x] **Track 1: Sing-box & Xray-core Compilers**
  - [x] 1.1 Implement `src/huntx/formats/singbox.py` and `tests/test_singbox_compiler.py` (TDD)
  - [x] 1.2 Implement `src/huntx/formats/xray.py` and `tests/test_xray_compiler.py` (TDD)
  - [x] 1.3 Verify python test suite (`uv run pytest` - 662 passed)

- [x] **Track 2: Go WebAssembly Browser Engine**
  - [x] 2.1 Implement `cmd/huntx-wasm/main.go` and `cmd/huntx-wasm/wasm_test.go`
  - [x] 2.2 Compile `docs/assets/huntx_engine.wasm` (`GOOS=js GOARCH=wasm`)
  - [x] 2.3 Implement `docs/assets/js/wasm-worker.js` and wire into `docs/assets/js/decoder.js`

- [x] **Track 3: Visual Rule & Profile Studio Cockpit**
  - [x] 3.1 Implement `docs/assets/js/rule-studio.js` with Sovereign Glass UI
  - [x] 3.2 Wire Studio and topology visualizer into `docs/index.html`

- [x] **Track 4: Synthetic Trace Matrix & Anomaly Detection**
  - [x] 4.1 Implement `cmd/huntx-engine/telemetry/` with Jitter & Anomaly Scorer
  - [x] 4.2 Verify with `go test -race -v ./cmd/huntx-engine/telemetry/...`

- [x] **Track 5: Real-Time Subscriptions Diff Sync Daemon**
  - [x] 5.1 Implement `cmd/huntx-engine/subsync/` with 3-way hash diffing
  - [x] 5.2 Verify with `go test -race -v ./cmd/huntx-engine/subsync/...`

- [x] **Track 6: Go Micro-Benchmarking & Zero-Alloc Profiling**
  - [x] 6.1 Implement `bench_test.go` across `stream`, `chain`, and `subsync`
  - [x] 6.2 Record benchmarks and verify zero-allocation hot paths (`go test -bench=. -benchmem`)
