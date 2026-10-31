# Third-party decryption credentials: provenance and handling

Status: **technical controls implemented; vendor provenance authorization
unverified**. Tracked by [security issue #78](https://github.com/AmirrezaFarnamTaheri/HUNTX/issues/78).

## What the historical audit established

The redacted Gitleaks v8.30.1 audit recorded 222 candidates across 698
historical commits: 218 generated/public proxy payload candidates, 3 historic
vendor decryption-key candidates and 1 test fixture. It identified **no
confirmed first-party HUNTX Telegram, GitHub or AWS credential** requiring
automatic rotation. Scanner findings do not, by themselves, prove active
secret exposure or authorize redistributing third-party key material.

## Current loading policy

`src/huntx/formats/common/crypto.py` resolves optional HAPP decrypt keys
through `HUNTX_HAPP_CRYPT_PEM`, `HUNTX_HAPP_CRYPT2_PEM` and
`HUNTX_HAPP_CRYPT3_PEM` environment variables or local untracked
`persist/keys/happ_{crypt,crypt2,crypt3}.pem` files. No vendor private-key
bytes should be embedded in tracked source, tests, generated reports or logs.
Missing credentials must remain missing; do not substitute a guessed key or
publish a decrypted payload that was never independently verified.

Deployment guidance:

- Provision only keys the operator is authorized to use and document the
  specific source and terms privately before granting production access.
- Limit local files to the executing account; keep `persist/` ignored and
  never attach key contents to CI artifacts, exceptions or issue comments.
- Prefer narrowly scoped secret storage. Avoid showing environment values in
  shell traces, crash dumps, test snapshots and screenshots.
- On evidence of a compromised **owned** credential, revoke/rotate via the
  issuing provider; historical vendor material requires the vendor's own
  authorization/disposition, not unilateral rotation.
- Record an audit decision before adding any secret-scanner allowlist. A
  false-positive classification is not permission to keep sensitive data.

## Open governance decision

The software can externalize vendor decryption material and keep missing
keys fail-closed, but it **cannot determine ownership or redistribution rights**
from the code alone. The repository owner must record the vendor's
authorization, or explicitly disable/remove the affected optional decryption
path if permission cannot be established.

Historical generated public proxy payloads have a separate retention and
privacy decision; see `docs/GENERATED_OUTPUTS_MODEL.md`. Do not combine an
unaudited history rewrite with credential or state migration.

This document intentionally contains **no private keys, sessions, raw
auth tokens, or captured credential values**.
