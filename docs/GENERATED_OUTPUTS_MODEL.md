# Generated outputs publication model

`huntx-production` is the trusted producer. `Publish Generated Outputs` validates a completed successful producer run, downloads its verified checkpoint, distributable bundle, and diagnostics, and then publishes one deterministic snapshot.

## Directory semantics

- `outputs/` contains the artifacts produced by the source workflow run being published. A later run replaces the default-branch mirror; the `generated-outputs` commit history records prior published runs.
- `outputs_dev/` is an all-time cumulative, deduplicated proxy data set. Before publishing, the workflow merges the previous generated manifest, recoverable legacy history from the default branch, and the current run manifest.
- `dist/` and `run-summary/` belong to the current source run.
- `manifests/publication.json` records provenance and previous, legacy, current, and cumulative counts.

This means `outputs_dev/` remains cumulative even when the production workflow is stateless because no S3 bucket is configured.

## Legacy cumulative bootstrap

Older repository states can contain a large, valid `outputs_dev/proxies.txt` or `proxies.json` while `_manifest.json` is blank or absent. The rendered history is authoritative migration input and must not be discarded merely because the newer manifest contract was introduced later.

The publisher checks the default-branch `outputs_dev/` directory on every publication:

1. A non-empty legacy manifest is loaded when valid.
2. Proxy identities are recovered from `proxies.txt` and `proxies.json`.
3. `proxies_b64sub.txt` is used as a fallback when no identities were recovered from the other representations.
4. Known timestamps are preserved. Identities that have no historical timestamp receive the sentinel `0`.
5. Legacy identities seed only missing entries; they never replace a known timestamp from the generated manifest.
6. A non-empty but unrecoverable legacy layout fails publication closed instead of silently shrinking the cumulative set.

After a successful publication, the newly generated `_manifest.json` becomes the durable cumulative contract, while legacy recovery remains idempotent protection for default-branch history.

## Publication targets

Each successful publication updates both:

1. `generated-outputs`, a generated-data-only branch whose commits form one publication history chain.
2. `main/outputs/` and `main/outputs_dev/`, a source-branch mirror for users who browse the default branch.

The main mirror is ownership-scoped by `.github/huntx-generated-files.txt`. Only paths listed in that inventory are replaced or removed. Unmanaged helper files such as `outputs/verify_output.py` are preserved.

## Producer artifacts

The `huntx-production` workflow produces:

- `huntx-output-<run_id>-<attempt>`: distributable artifacts from `persist/data/dist/`
- `runtime-checkpoint-<run_id>-<attempt>`: verified recoverable state, including the current run outputs
- `huntx-logs-<run_id>-<attempt>`: structured runtime diagnostics

The publisher accepts artifacts only after validating the originating workflow name, workflow path, source branch, completion state, conclusion, and run attempt.

## Guarantees

- current-run `outputs/` never inherits files from an older snapshot
- cumulative `outputs_dev/` never loses an identity present in generated, legacy, or current verified inputs
- duplicate proxy identities keep a known earliest `first_seen` value
- blank legacy manifests do not erase rendered cumulative history
- repeated publication of the same run and parent snapshot is deterministic and idempotent
- generated publication commits preserve ancestry and use `--force-with-lease`
- main synchronization retries non-fast-forward races without force-pushing
- stale generated files are removed through an explicit ownership inventory
- unmanaged source-branch files are not deleted

## Recovery

If generated-branch publication or the main mirror fails, the producer artifacts remain the recovery source. A manual dispatch can republish a validated producer run by its run ID and attempt. A failed main push does not require regenerating runtime data; rerunning the publisher reuses the same verified artifacts and deterministic snapshot.
