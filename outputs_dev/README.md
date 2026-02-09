# Dev Outputs

Auto-generated proxy config outputs with a **48-hour rolling window**.
Each pipeline run accumulates new URIs and prunes entries older than 48 hours.
Duplicates across runs are automatically deduplicated.

| File | Description |
|---|---|
| `proxies.txt` | Unique proxy URIs (plain text, one per line) |
| `proxies_b64sub.txt` | Base64-encoded subscription (for v2rayN/v2rayNG) |
| `proxies.json` | Structured JSON with URIs and last-seen timestamps |
| `_manifest.json` | Internal dedup/pruning state — do not edit |

These files are committed back to the repo by the CI workflow after each run.

**Do not edit manually** — they are regenerated on every pipeline run.
