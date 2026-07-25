# Technology Stack: HuntX

## Core Runtimes & Languages
- **Python**: 3.11+ (Primary pipeline, bot API, format decoders, and CLI)
- **Go**: 1.20+ (V2Ray collector auxiliary service in `src/huntx/connectors/v2ray_collector/`)

## Frameworks & Core Libraries
- **Telethon**: 1.42+ (Telegram MTProto client & bot API framework)
- **Pydantic**: 2.0+ (Configuration validation and structured data modeling)
- **PyYAML**: 6.0+ (YAML configuration parsing)
- **Cryptography / PyAES / RSA**: Payload decryption, token validation, and secure hashing

## Persistence & Storage
- **SQLite**: Embedded database (`temp_state.db`) for proxy state, deduplication hashes, and user preferences
- **Raw File Store**: Local disk storage (`data/`, `data_archive/`, `outputs/`, `outputs_dev/`) for raw and decoded proxy artifacts

## Testing & Code Quality
- **Pytest**: Automated unit, integration, and pipeline test suite
- **Mypy**: Static type validation
- **Flake8 & Black**: Formatting and style enforcement (max line length: 120)

## Infrastructure & CI/CD
- **GitHub Actions**: Automated pipeline triggers (cron every 2h), PR validation, and quality gates
- **GitHub Pages**: Automated hosting of static proxy catalog output (`docs/`)
