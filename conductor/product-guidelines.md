# Product Guidelines: HUNTX

## Tone and operator communication

- **Technical and concise** — CLI/log output should identify the affected boundary, state, and actionable failure without decorative noise.
- **Security-conscious** — explain source trust, user authorization, bounded downloads/probes, and secret handling without implying third-party proxy endpoints are trustworthy.
- **Recoverability-aware** — distinguish fatal invariant/state failures from external degradation that preserved durable progress.
- **No secret echoing** — user-facing or diagnostic messages must not include bot-token URLs, session strings, API hashes, cloud keys, or decrypted credential material.

## GatherX interaction principles

- **Private-chat first** — GatherX commands execute only in DMs.
- **Registration is not authorization** — pending-safe information commands must remain separate from approved artifact/settings commands.
- **Administrative controls stay non-public** — `/status`, `/admin`, `/pending`, `/approve`, and `/deny` are numeric-ID administrator commands and are not part of the default user command menu.
- **Lower-layer authorization** — any artifact send must recheck approved private identity even when the caller already passed a handler-level policy wrapper.
- **Actionable feedback** — long-running admin operations should acknowledge start/duplicate-run state and report completion or failure without leaking internals/secrets.

## Engineering quality standards

- **CI is authoritative** — Go formatting/race tests/vet/build plus Python compile/Flake8/MyPy/Pytest must pass on the exact candidate head.
- **State changes are contractual** — migrations, leases, acknowledgements, publication receipts, pruning, and output ownership need explicit invariants and regression tests.
- **Bound external work** — network calls, downloads, transformations, retries, worker counts, and timeouts require finite limits.
- **Preserve parser/builder round trips** — raw/archive formats must retain source-blob identity when optional deep parsing enriches a record.
- **Document production reachability** — distinguish active production components from implemented helpers/alternatives.
- **Historical evidence stays historical** — do not silently rewrite old audit/forensic records to make current state appear cleaner; add reconciliation notices instead.
