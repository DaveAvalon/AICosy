# AICosy security

This is an experimental local research service. It has not received an independent security audit and is not presented as a hardened multi-tenant service.

## Access boundary

- The default HTTP listener is `127.0.0.1:8765`. Without a token, a process that can reach this port has instance-wide research access, including session creation, eligible raw exports and profile resets.
- Binding to a non-loopback address requires a configured bearer token. When a token is configured, every `/v1/` route requires it. The shared token grants access to the whole instance; it does not isolate individual players or researchers.
- The built-in server does not provide TLS. Remote use requires an appropriately configured HTTPS proxy and access controls. Do not expose an unauthenticated local listener through a public tunnel.
- Host/Origin checks, request limits and basic per-IP rate limiting reduce specific risks; they do not replace authentication, TLS, a gateway or an audit. Static HTML, schemas and OpenAPI are publicly readable.
- CLI and MCP stdio access inherit the caller's local filesystem and process permissions. They are not separate authentication boundaries.

## Data and credentials

Normal observations omit hidden world state. Research debug and raw player exports intentionally contain more data; the export endpoint requires that player's normal sessions to have ended. This protects experiment boundaries, not confidentiality from other users holding the same instance token.

Keep provider credentials and access tokens in environment variables. Do not include them in source, query strings, screenshots, logs or bug reports. The observer can read a token from a URL fragment and keeps it in memory; do not share a link containing that fragment. Review exported states and model transcripts before making them public.

Game content and model output are untrusted data. A connected model client may send its visible game observations to the provider selected by its operator. Use a suitable provider and inspect the client configuration before sending sensitive research data.

## Reporting

Do not open a public issue containing credentials, private transcripts or a working exploit against someone else's deployment. Where GitHub private vulnerability reporting is enabled for the published repository, use its Security tab. Otherwise request a private contact channel from the maintainer without including sensitive details. No response-time guarantee or audited support policy is currently offered.
