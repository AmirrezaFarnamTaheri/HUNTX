# Security Policy

HUNTX ingests untrusted data from public channels, decodes it, and publishes
the result to a static site. That makes the boundary between "data we fetched"
and "code we run" the most important property in the project. This document
explains what we support, how to report a problem, and which behaviours are
already known and intentional.

## Supported versions

Only the `main` branch is supported. HUNTX publishes a rolling snapshot rather
than tagged releases, so fixes land on `main` and reach the published site on
the next scheduled run. There are no backports to older commits.

## Reporting a vulnerability

Report privately through GitHub's **Report a vulnerability** button under the
repository's Security tab, which opens a private advisory. Do not open a public
issue for anything that lets an attacker execute code, exfiltrate a token, or
poison the published artifacts.

Please include the affected component (`cmd/huntx-daemon`, `cmd/huntx-probe`,
the Python pipeline under `src/huntx`, or the dashboard under `docs/`), the
commit you tested, and a reproduction. A proof-of-concept proxy URI or a
crafted channel message is usually the fastest way to show impact.

Expect an acknowledgement within 7 days and an assessment within 30 days. If a
report is valid we will agree a disclosure date with you before publishing.

## Threat model

HUNTX assumes the following are hostile:

- **Every ingested proxy configuration.** Names, SNI values, hostnames, and
  query parameters arrive from public Telegram channels and are attacker
  controlled. They must be escaped before they reach the DOM and validated
  before they reach the published artifacts.
- **Every upstream source.** A source can go offline, serve garbage, or serve a
  large payload designed to exhaust the runner.

HUNTX assumes the following are trusted:

- The GitHub Actions runner and the repository's own secrets.
- The maintainer-curated source list in `configs/`.

## Boundaries that are intentional

These are deliberate design decisions, not vulnerabilities:

- **The dashboard exposes the proxy configurations it publishes.** That is the
  product. Credentials inside a published node are public by construction.
- **`cmd/huntx-daemon` binds to `127.0.0.1:9090`.** Its read-only endpoints
  (`/status`, `/ready`, `/proxy.pac`) are unauthenticated because the loopback
  boundary is the control. Exposing the daemon on a routable interface or
  through a reverse proxy is out of scope and unsupported.
- **`cmd/huntx-probe` originates connections and POSTs JSON.** It does not
  listen. It refuses to send a bearer token over plaintext to a non-loopback
  host.

## What we consider in scope

- Cross-site scripting or HTML injection in the published dashboard.
- Any path where an ingested value reaches a shell, a file path outside the
  designated output tree, or a deserializer.
- Authentication bypass on `POST /rotate`.
- Leaking a repository secret or a bearer token into logs, artifacts, or the
  published site.
- Supply-chain issues in the pinned dependency set or the workflow definitions.

## What we consider out of scope

- Denial of service against an upstream source or against a published proxy.
- Findings that require an already-compromised GitHub Actions runner.
- Reports produced solely by an automated scanner with no demonstrated impact.
- The availability or trustworthiness of any third-party proxy that HUNTX
  merely indexes.
