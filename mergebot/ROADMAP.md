# MergeBot Roadmap

## Status: Active Development / Stable Beta

### Completed Features

- [x] **Core Pipeline**
  - Ingestion from Telegram channels
  - Content-based deduplication (SHA256)
  - Transformation of configs and binary blobs
  - Atomic publishing to Telegram

- [x] **Formats**
  - V2Ray/VLESS (`npvt`) normalization
  - OpenVPN (`ovpn`) handling
  - Conf lines (`conf_lines`)
  - Opaque Bundle (`opaque_bundle`) for unknown formats

- [x] **Robustness & Security**
  - Environment variable expansion in configs (Fixed regex)
  - Strict configuration validation (Loader robustness)
  - Non-root systemd service configuration
  - SQLite state management

### Future Considerations

- [ ] **External Integrations**
  - Evaluate `python-telegram-bot` for richer Telegram interactions (currently using `urllib` for minimal footprint).
  - Evaluate `Pydantic` for advanced schema validation (currently using custom dataclasses).

- [ ] **Scalability**
  - Support for S3-compatible storage for artifacts.
  - Horizontal scaling for ingestion workers.

- [ ] **Monitoring**
  - Prometheus metrics endpoint.
