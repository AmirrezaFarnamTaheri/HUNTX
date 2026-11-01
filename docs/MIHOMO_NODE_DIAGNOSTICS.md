# Authenticated Mihomo named-node diagnostics

HUNTX's optional `mihomo-node` command tests **one named, concrete Mihomo proxy** through Mihomo's authenticated local external-controller API. This is a stronger and more precisely attributed signal than a generic local HTTP/SOCKS5 path check, but it is not independent proof of TLS configuration or recovery of a dead server.

## Prerequisites

- Run Mihomo locally with an **external controller bound to loopback** (example: `127.0.0.1:9097`), and configure a private `secret`. Do not expose the controller on a LAN/public interface.
- Know the exact name of a leaf proxy. The command refuses `DIRECT`, `REJECT`, `Selector`, `URLTest`, `Fallback`, `LoadBalance`, unknown types, chained `dialer-proxy` nodes, and nodes with group membership metadata.
- Store the controller secret in a separate, **private regular file** (0600 on Unix). Never put the secret in command arguments, a URL, or screenshots.

For example, in an interactive Unix shell (the secret you type is hidden):

```bash
umask 077
read -r -s -p "Local Mihomo API secret: " HUNTX_MIHOMO_SECRET; echo
printf '%s' "$HUNTX_MIHOMO_SECRET" > "$HOME/.mihomo-huntx-secret"
unset HUNTX_MIHOMO_SECRET
chmod 600 "$HOME/.mihomo-huntx-secret"

go run ./cmd/huntx-tools mihomo-node \
  --controller http://127.0.0.1:9097 \
  --token-file "$HOME/.mihomo-huntx-secret" \
  --node "My Trojan Node" \
  --attempts 3 --timeout 8s --json
```

Choose the configured Mihomo controller port. **Do not assume 9090 is available**: HUNTX's own daemon uses 9090 by default. HUNTX will never start a controller, switch proxy groups, change client settings, or read a Mihomo profile.

## What is tested

The command first retrieves `GET /proxies/{name}` and verifies the exact name is a concrete leaf, then performs 1–3 sequential `GET /proxies/{name}/delay` requests with the **fixed HTTPS target** `https://www.gstatic.com/generate_204`, a bounded timeout, and an expected HTTP response of `204`. It rereads the node metadata afterward and rejects a changed type or a group transition. The URL-test API's reported latency is summarized as a median in milliseconds.

**Successful output represents Mihomo-controller-attested named-node URL-test success**, not a separately observed end-to-end TLS handshake by HUNTX. Underlying Mihomo versions and profile options may affect certificate validation; no certificate-validation settings are changed here. The command cannot determine whether the remote proxy had previously failed, so `original_recovered` and `tls_independently_verified` remain `false`. `node_attributed` means the controller reported a successful test for the explicitly selected leaf, *not* an independent HUNTX attestation of its underlying server identity.

A failed/partial check exits nonzero and returns generic privacy-safe diagnostics. The target may be blocked or unreachable without the proxy being globally dead. Results must **not** drive automatic global quarantine or feed publication decisions.

## Safeguards and limits

- Only `http://127.0.0.0/8:port`, `http://[::1]:port`, or `http://localhost:port` controllers are accepted; localhost is pinned to numeric loopback before dialing.
- The command makes authenticated `GET` requests only, follows **no redirects**, uses a direct transport for the controller (not system proxy settings), and pins all controller TCP dials to that loopback socket.
- A private token file is mandatory; unreadable, symlink, oversized, or group/world-readable token files are rejected on Unix. Node names are URL-escaped and validated.
- At most three sequential native tests, each within a 1–15-second budget, are permitted. Controller response bodies are bounded; errors never print the token, selected node, controller address, or returned remote error text.
- No device SSID, client credentials, proxy URI, endpoint, target browsing history, or full profile are saved/uploaded.
- This is a **CLI-only opt-in tool**, not a browser-accessible controller. Do not expose token-authenticated local APIs to public webpages via broad CORS rules.

## Test

```bash
go test -race ./internal/localmihomo ./cmd/huntx-tools
go vet ./internal/localmihomo ./cmd/huntx-tools
```

The integration tests use a local fake controller to verify authentication, exact leaf selection, URL encoding, 204-test parameters, rejecting policy groups and DIRECT, rejecting unsafe token files and remote URLs, and preventing false recovery classifications. They do **not** constitute a live test against a real Mihomo installation.

Reference: [Mihomo API documentation](https://wiki.metacubex.one/en/api/), especially `/proxies/{name}`, `/proxies/{name}/delay`, and Bearer authentication.
