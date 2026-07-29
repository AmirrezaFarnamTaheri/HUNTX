# Generated outputs branch model

`generated-outputs` is a generated data-plane branch. It is not a source branch.

## Producer contract

The `huntx-production` workflow produces:

- `huntx-output-<run_id>-<attempt>`: distributable artifacts from `persist/data/dist/`
- `runtime-checkpoint-<run_id>-<attempt>`: verified recoverable state
- `huntx-logs-<run_id>-<attempt>`: structured runtime diagnostics

The publication workflow consumes these artifacts only after validating the originating successful `huntx-production` run.

## Publication guarantees

- generated branch contains generated data only
- publication is atomic
- repeated publication of identical content is idempotent
- source/control-plane history is not copied into the generated branch
- provenance is stored under `manifests/publication.json`

## Recovery

If publication fails, the source workflow artifacts remain the recovery source. The generated branch is never partially updated.
