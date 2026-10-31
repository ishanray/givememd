# Security

## Reporting
Please report vulnerabilities privately through GitHub's "Report a vulnerability" (Security tab) rather than a public issue.

## What givememd protects against
givememd fetches URLs that someone else supplies. The plain-request tier refuses server-side request forgery by:
- resolving the host and rejecting it if any address is private, loopback, link-local, multicast or otherwise
  non-public;
- **pinning** the connection to the address it checked, so DNS rebinding can't swap it between check and connect;
- following redirects itself and re-checking every hop;
- allowing only ports 80 and 443 by default (`GIVEMEMD_ALLOWED_PORTS`);
- capping response size (`GIVEMEMD_MAX_BYTES`, default 15 MB) and setting timeouts.

## Before running a public server
The bundled `givememd-server` is a small stdlib server meant for local use. A public deployment also needs:
- **An egress firewall for the browser tiers.** Lightpanda and Chromium resolve names themselves and run page
  JavaScript, which can request internal addresses. Run them in a sandbox or network namespace that blocks private
  ranges and cloud metadata endpoints (169.254.169.254, fd00::/8…).
- **Rate limits** per IP and per key, a global cap on browser concurrency, and per-domain politeness.
- **A caching policy** that never stores content fetched with a user's cookies or login.
- **A takedown and opt-out process** for site owners.
