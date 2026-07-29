# Publishing modes and credentials

HUNTX publishes route artifacts through the Telegram transport. New and
repository-owned configurations should use the canonical spelling:

```yaml
publishing:
  routes:
    - name: all_sources
      destinations:
        - chat_id: "-1001234567890"
          mode: telegram
          caption_template: "Merged configs — {timestamp}"
```

## Legacy compatibility

`post_on_change` is a legacy-only, backward-compatible alias for `telegram`.
It does not select a different transport. Publication is already change-gated
by the durable artifact hash and publication-intent ledger, so the alias is
normalized to `telegram` before validation and again at the publisher boundary.
This second boundary check protects untyped internal callers that bypass the
Pydantic configuration model.

The alias is retained to avoid breaking deployed configurations. It should not
be emitted by new code or copied into new configuration. Removal, if pursued,
requires an explicitly announced major-version migration rather than a silent
minor release change.

Unknown or explicitly empty destination modes fail during configuration loading
rather than later inside the production publish stage.

## Migration

Existing configuration can be migrated without changing behaviour:

```diff
 destinations:
   - chat_id: "-1001234567890"
-    mode: post_on_change
+    mode: telegram
```

Credential resolution is now validated with the same precedence used during
publication:

1. `destination.token`
2. `PUBLISH_BOT_TOKEN`
3. `TELEGRAM_TOKEN`

An explicit destination token remains authoritative. A configured
`PUBLISH_BOT_TOKEN` is preferred for production. `TELEGRAM_TOKEN` remains a
compatibility fallback, but sharing an ingestion token with a persistent bot
can cause Telegram consumer conflicts.

## Health-gate semantics

External source availability is independent from release integrity. A minority
of source failures is reported as degraded coverage, while a successfully
built, verified, and published aggregate remains a completed release.

Concrete outcomes:

| Ingestion | Build and publish | Result |
|---|---|---|
| 67 succeeded, 8 failed | all routes succeeded | `completed`, with `degraded_source_failures: 8` |
| 0 succeeded, 8 failed | no healthy ingestion | `failed` |
| one or more succeeded | a build or publication route failed | `partial` |
| deadline exhausted | any unfinished stage | `timed_out` |

HUNTX deliberately does not introduce a new top-level `degraded` status in this
compatibility repair. Existing automation can continue consuming
`completed`/`partial`/`failed`/`timed_out`, while operators receive the explicit
`ingest_err` and `degraded_source_failures` counters and warning logs.

The run also remains non-successful when no output artifacts are produced or
output verification fails.
