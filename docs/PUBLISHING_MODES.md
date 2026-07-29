# Publishing modes and credentials

HUNTX publishes route artifacts through the Telegram transport. The canonical
configuration is:

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

`post_on_change` remains accepted as a backward-compatible alias for
`telegram`. It does not select a different transport. Publication is already
change-gated by the durable artifact hash and publication-intent ledger, so the
alias is normalized to `telegram` before validation and delivery.

Unknown destination modes fail during configuration loading rather than later
inside the production publish stage.

## Credential precedence

Destination credentials use one consistent order during validation and
runtime:

1. `destination.token`
2. `PUBLISH_BOT_TOKEN`
3. `TELEGRAM_TOKEN`

Production should configure a distinct `PUBLISH_BOT_TOKEN`. Falling back to
`TELEGRAM_TOKEN` is retained for compatibility, but sharing an ingestion token
with a persistent bot can cause Telegram consumer conflicts.

## Health-gate semantics

A release remains successful when a minority of independent external sources
fail but at least one source completes and every build and publication route
succeeds. The summary still reports `ingest_err` and
`degraded_source_failures` for operational follow-up.

The run remains non-successful when:

- every ingestion attempt fails;
- a build route fails;
- a publication attempt fails;
- the run times out;
- no output artifacts are produced; or
- output verification fails.
