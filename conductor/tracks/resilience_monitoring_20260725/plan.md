# Implementation Plan: Hardening & Health Benchmarking

## Phase 1: Format Decoder Test Expansion & Hardening
- [ ] Task: Write unit tests for edge cases across 12 decoders (`tests/test_formats_coverage.py`)
- [ ] Task: Implement error recovery & silent rejection for malformed payloads
- [ ] Task: Phase 1 Verification Checkpoint (`pytest tests/test_formats_coverage.py`)

## Phase 2: Health & Latency Benchmarking Gate
- [ ] Task: Write unit tests for async latency benchmarker (`tests/test_latency_benchmarker.py`)
- [ ] Task: Implement proxy benchmarker module in core/ and integrate into transform pipeline
- [ ] Task: Phase 2 Verification Checkpoint (`pytest tests/test_latency_benchmarker.py`)

## Phase 3: Telegram Bot Freshness Alerts
- [ ] Task: Write tests for admin freshness alerts (`tests/test_bot_alerts.py`)
- [ ] Task: Implement notification alert logic in `bot/delivery.py` and publish pipeline
- [ ] Task: Phase 3 Verification Checkpoint (`pytest tests/test_bot_alerts.py`)
