# Generated-output lifecycle and retention

The `huntx-production` workflow is the only trusted runtime producer. Its
checkpoint, current-run distributable, source-health report, and release receipt
have distinct provenance. A green build or a successful no-release verdict
does **not** imply that fresh proxies were published or authenticated.

## Publication targets (after #165)

- `generated-outputs`: a dedicated branch that records the validated public
  snapshot, historical identity manifest, and dashboard shell/assets.
- GitHub Pages: the publication workflow deploys the exact verified snapshot,
  rather than claiming that an older checked-in sample represents a new release.
- GitHub Actions artifacts: per-run checkpoint/output/log artifacts, retained
  according to their explicit workflow retention settings.
- `main`: **source code and historical data only**. The publisher does **not**
  commit or force-push generated `outputs/` or `outputs_dev/` back to `main`.
  Legacy tracked files may remain visible at old revisions and must not be
  interpreted as current live data.

`outputs/` refers to one verified producer run. `outputs_dev/` contains a
cumulative, semantically deduplicated set of historical proxy identities.
`dist/` and release receipts must match that producer's run ID, attempt and
commit. The publication manifest is an immutable audit record of the accepted
release. A no-release verdict leaves the previous distribution unchanged.

## Bootstrap and recovery

Older source history may contain valid `outputs_dev/proxies.txt`,
`proxies.json`, and manifests even when `_manifest.json` is empty. The
publisher recovers these as **migration inputs**, preserving known first-seen
timestamps and using zero only when history cannot establish a date.
Unrecoverable non-empty legacy layouts fail closed rather than silently
discarding cumulative identities.

A successful generated-branch publication is monotonic and uses
`--force-with-lease` against the expected previous generated head. Replaying
the same verified run should be idempotent; obsolete producers cannot overwrite
a newer publication. The old `main` mirror is **not** a recovery destination.
Use the validated producer artifacts and the generated branch.

## Repository growth and safe retention

The new default `.gitignore` patterns protect **untracked** local generated
payloads. Git ignores do not untrack or delete files already committed.
Historic `main` blobs and older `generated-outputs` commits still consume
Git storage, even if their latest working trees appear compact.

No automated job is allowed to rewrite `main` history or discard the
cumulative identity manifest. Before any planned reduction:

1. Export a verified, restorable backup of the latest source tree, the current
   generated branch snapshot, cumulative identity manifest, publication
   receipts, and configured state backend generation.
2. Inventory byte size and earliest/latest timestamps, then classify current
   distributables, replay state, historical public proxy payloads, and
   diagnostic logs separately. Treat generated proxy credentials as potentially
   sensitive user-facing data even when they are not HuntX control-plane keys.
3. Decide retention windows and who may access exported archives; do not
   silently discard the oldest `first_seen` provenance or unexpired release
   receipts.
4. Dry-run any retention script against a restored copy and verify checksums,
   continuity, legacy-bootstrap behavior, and replay/idempotency tests.
5. Schedule destructive history compaction as a separate, reviewed migration
   requiring a coordinated contributor re-clone and rollback procedure.

## Pages deployment configuration

The verified publisher's `actions/deploy-pages` deployment and GitHub's
independent legacy `pages build and deployment` activity must not race to
present different generations. On October 31 the repository showed a successful
legacy Jekyll Pages build from `main` after a publisher run that deliberately
skipped republishing stale output. **Those green runs do not establish that
the public dashboard is showing the newest verified generated snapshot.**
The repository owner must confirm GitHub Pages is configured to deploy the
GitHub Actions publication artifact, then verify the public page's manifest,
run ID, timestamp and download bytes against the immutable receipt.

## Gates

Keep fail-closed checks for the producer workflow identity and attempt,
current-run release receipt, output digest/manifest, allowed destinations,
proxy protocol authentication, and the final Pages package. Optional Telegram
availability is diagnostic, not a reason to fabricate successful ingestion.
