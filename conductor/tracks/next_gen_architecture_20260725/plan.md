# Implementation Plan: Next-Gen Architecture

- [ ] **Task 1: Zero-Copy Streaming Ingestion Engine**
  - Implement `StreamingChunkParser` in `src/huntx/formats/streaming.py`
  - Add unit tests in `tests/test_streaming_parser.py`
  - Verify zero-copy 64KB chunk parsing behavior

- [ ] **Task 2: Intelligent Geo-Clustering & Dynamic Target Routing**
  - Implement `GeoRoutingEngine` in `src/huntx/core/geo_routing.py`
  - Add unit tests in `tests/test_geo_routing.py`
  - Verify protocol taxonomy and country/ASN classification

- [ ] **Task 3: Autonomous Self-Healing Daemon**
  - Implement `SelfHealingDaemon` in `src/huntx/core/self_healing.py`
  - Add unit tests in `tests/test_self_healing.py`
  - Verify exponential backoff and 48h dead node purging

- [ ] **Task 4: Unified Integration & System Verification**
  - Wire components into `src/huntx/core/unified_orchestrator.py`
  - Run full test suite verification `python -m pytest`
