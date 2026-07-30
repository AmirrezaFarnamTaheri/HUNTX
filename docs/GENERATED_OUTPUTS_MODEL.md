# Generated outputs publication model

`huntx-production` is the trusted producer. `Publish Generated Outputs` validates a completed successful producer run, downloads its verified checkpoint, distributable bundle, and diagnostics, and then publishes one deterministic snapshot.

## Directory semantics

- `outputs/` contains the artifacts produced by the source workflow run being published. A later run replaces the previously mirrored generated artifacts; the `generated-outputs` Git history records prior published runs.
- `outputs_dev/` is an all-time cumulative, deduplicated proxy data set. Before publishing, the workflow loads the previous `generated-outputs` snapshot, merges its `_manifest.json` with the current run manifest, preserves the earliest `first_seen` value for duplicates, and regenerates all public dev files.
- `dist/` and `run-summary/` belong to the current source run.
- `manifests/publication.json` records provenance and cumulative counts.

This means `outputs_dev/` remains cumulative even when the production workflow is stateless because no S3 bucket is configured.

## Publication targets

Each successful publication updates both:

1. `generated-outputs`, an orphan generated-data branch containing only the verified snapshot.
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
- cumulative `outputs_dev/` never loses an already published proxy identity
- duplicate proxy identities keep the earliest known `first_seen` value
- repeated publication of the same run is deterministic and idempotent
- generated-only branch replacement uses `--force-with-lease`
- main synchronization retries non-fast-forward races without force-pushing
- stale generated files are removed through an explicit ownership inventory
- unmanaged source-branch files are not deleted

## Recovery

If generated-branch publication or the main mirror fails, the producer artifacts remain the recovery source. A manual dispatch can republish a validated producer run by its run ID and attempt. A failed main push does not require regenerating runtime data; rerunning the publisher reuses the same verified artifacts and deterministic snapshot.
