# MergeBot Outputs

This directory contains the full build output from each pipeline run.
Files are auto-generated and committed by CI — **do not edit manually**.

## Contents

Each run produces artifacts named `{route}.{format}` plus derived files:

- **`.npvt`** — Raw proxy URI list (one per line)
- **`.npvtsub`** — Subscription proxy URI list
- **`_decoded.json`** — Structured JSON of decoded proxy URIs
- **`_b64sub.txt`** — Base64-encoded subscription (for v2rayN/v2rayNG)
- **`.ovpn`** / **`.ehi`** / **`.hc`** / **`.hat`** / **`.sip`** / **`.nm`** / **`.dark`** — Binary config archives (ZIP)
- **`.conf_lines`** — Plain config lines
