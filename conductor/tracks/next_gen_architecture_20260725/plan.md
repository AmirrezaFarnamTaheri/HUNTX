# Implementation Plan: Next-Gen Architecture

- [x] **Task 1: Zero-Copy Streaming Ingestion Engine**
  - Implement `StreamingChunkParser` in `src/huntx/formats/streaming.py`
  - Add unit tests in `tests/test_streaming_parser.py`
  - Verify zero-copy 64KB chunk parsing behavior

- [x] **Task 2: Intelligent Geo-Clustering & Dynamic Target Routing**
  - Implement `GeoRoutingEngine` in `src/huntx/core/geo_routing.py`
  - Add unit tests in `tests/test_geo_routing.py`
  - Verify protocol taxonomy and country/ASN classification

- [x] **Task 3: Autonomous Self-Healing Daemon**
  - Implement `SelfHealingDaemon` in `src/huntx/core/self_healing.py`
  - Add unit tests in `tests/test_self_healing.py`
  - Verify exponential backoff and 48h dead node purging

- [x] **Task 4: Unified Integration & System Verification**
  - Wire components into `src/huntx/core/unified_orchestrator.py`
  - Run full test suite verification `python -m pytest`

> **Delivery status (verified 2026-09-18):** every module and test file above exists and passes. They are delivered as helper modules imported by `src/huntx/__init__.py` and exercised by their own tests, not as production pipeline stages: the production runtime is constructed through `core.runtime_factory.create_production_orchestrator()`. See `conductor/tracks.md` for the track-level caveat.
