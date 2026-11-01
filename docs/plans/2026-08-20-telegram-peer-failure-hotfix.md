# Telegram peer failure hotfix

## Production evidence

The post-merge production trace showed four Telegram sources repeatedly failing while healthy sources continued ingesting:

- dead usernames raised `ValueError: No user has ... as username`;
- one numeric `-100...` source fell back to a raw `PeerChannel` and then raised `ValueError: Could not find the input entity ...`;
- the persistent-window worker treated both classes as generic retryable exceptions, causing repeated window retries;
- numeric channel IDs bypassed canonical reachability checks because parseable IDs were assumed usable.

## Required behavior

1. Permanent Telegram peer identity failures quarantine/terminalize all unfinished work for that source.
2. Transport and other transient failures keep the existing retry/backoff behavior.
3. Numeric `-100...` peers are reachability-checked during canonical preflight instead of being trusted solely because their ID parses.
4. Permanent preflight failures exclude the source for that run and terminalize existing queued work.
5. No source is removed from production configuration automatically; a later run may re-evaluate it if Telegram/session reachability changes.

## Verification

The regression suite in `tests/test_telegram_peer_failure_quarantine.py` must fail on the merged PR #77 baseline, then pass with the hotfix. The ordinary pull-request validation workflow remains the final repository-wide gate.
