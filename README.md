# Tophost DNS API

[![CI](https://github.com/DanielVd/tophost-dns-api/actions/workflows/ci.yml/badge.svg)](https://github.com/DanielVd/tophost-dns-api/actions/workflows/ci.yml)
[![Upstream Canary](https://github.com/DanielVd/tophost-dns-api/actions/workflows/upstream-canary.yml/badge.svg)](https://github.com/DanielVd/tophost-dns-api/actions/workflows/upstream-canary.yml)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

Unofficial REST API for managing DNS records on Tophost accounts.

> This project is not affiliated with, endorsed by, or supported by Tophost.

The project wraps the Tophost web control panel behind a structured Python service layer and a versioned FastAPI REST interface.

## Features

- Tophost account authentication
- trusted 2FA session persistence
- OTP challenge flow
- automatic discovery of all domains in the account
- no hardcoded Tophost product IDs
- multi-domain support
- DNS record listing and filtering
- DNS record create, update and delete
- optimistic concurrency checks for destructive changes
- no-op detection
- structured application errors
- API key protection for `/v1`
- scheduled read-only upstream compatibility canary
- automatic GitHub issue creation for detected upstream drift
- separation between HTTP protocol, service layer and REST API

## Architecture

```text
REST client / future MCP
        |
        v
FastAPI /v1
        |
        v
Service layer
        |
        +---- AuthService
        |
        +---- DNSService
                 |
                 v
        Tophost clients
                 |
                 +---- account/auth
                 +---- product discovery
                 +---- control-panel SSO
                 +---- DNS operations
                          |
                          v
                       Tophost
```

Tophost-specific implementation details such as cookies, internal product IDs,
HTML structure and SSO URLs are intentionally hidden below the service layer.

## Requirements

- Python 3.11 or newer
- a Tophost account
- access to the domains being managed

## Installation

```bash
python -m venv .venv
. .venv/bin/activate
pip install -e .
```

For development:

```bash
pip install -e '.[dev]'
```

## Configuration

Copy `.env.example` or provide the variables through your preferred secret
management mechanism.

Required:

```env
TOPHOST_USER=user@example.com
TOPHOST_PASS=change-me
TOPHOST_API_KEY=change-me
```

Optional:

```env
TOPHOST_DEFAULT_DOMAIN=example.com
TOPHOST_STATE_DIR=/var/lib/tophost-dns-api
TOPHOST_REQUEST_TIMEOUT=20
```

`TOPHOST_DEFAULT_DOMAIN` is only a convenience. Domains are discovered
dynamically from the authenticated Tophost account.

The internal Tophost product ID is not part of the public configuration.

## Runtime state

Authentication state is stored separately from the source tree.

The state directory contains:

```text
2fa.json
otp-session.json
```

State files are written atomically and restricted to mode `0600`. The state
directory is restricted to mode `0700`.

Do not commit runtime state.

## Running the API

For local development:

```bash
uvicorn tophost_api.api.app:app \
  --host 127.0.0.1 \
  --port 8765
```

`/health` is public.

All `/v1` endpoints require:

```http
X-API-Key: <TOPHOST_API_KEY>
```

## API

### Health

```http
GET /health
```

### Authentication status

```http
GET /v1/auth/status
```

### Request an OTP

```http
POST /v1/auth/otp
```

Returns a challenge identifier.

### Verify an OTP

```http
POST /v1/auth/otp/{challenge_id}/verify
Content-Type: application/json

{
  "code": "123456"
}
```

### List domains

```http
GET /v1/domains
```

Example:

```json
[
  {
    "name": "example.com",
    "is_default": true
  }
]
```

Internal Tophost product IDs are deliberately not exposed.

### List DNS records

```http
GET /v1/domains/{domain}/dns/records
```

Optional filters:

```text
?name=www
?type=A
?value=192.0.2.10
```

Filters can be combined.

### Get one DNS record

```http
GET /v1/domains/{domain}/dns/records/{record_id}
```

### Create a DNS record

```http
POST /v1/domains/{domain}/dns/records
Content-Type: application/json

{
  "name": "www",
  "type": "A",
  "value": "192.0.2.10",
  "priority": 0
}
```

Creation is idempotent for an already-identical record and may return
`"changed": false`.

### Update a DNS record

```http
PATCH /v1/domains/{domain}/dns/records/{record_id}
Content-Type: application/json

{
  "value": "192.0.2.11",
  "expected_value": "192.0.2.10",
  "expected_priority": 0
}
```

Tophost record IDs can change after an update. The returned `after.id` must be
treated as the current identifier.

`expected_value` and `expected_priority` provide optimistic concurrency
protection. If the record changed after it was read, the mutation is refused.

### Delete a DNS record

```http
DELETE /v1/domains/{domain}/dns/records/{record_id}?expected_value=192.0.2.11&expected_priority=0
```

For automated clients, supplying the expected state is strongly recommended.

## Error format

Application errors use a stable envelope:

```json
{
  "error": {
    "code": "RECORD_CHANGED",
    "message": "DNS record value changed since it was read",
    "retryable": false,
    "context": null
  }
}
```

Examples of error codes include:

- `AUTH_FAILED`
- `OTP_REQUIRED`
- `OTP_CHALLENGE_NOT_FOUND`
- `OTP_INVALID`
- `DOMAIN_NOT_FOUND`
- `AMBIGUOUS_DOMAIN`
- `RECORD_NOT_FOUND`
- `RECORD_CHANGED`
- `UPSTREAM_UNAVAILABLE`
- `UPSTREAM_PROTOCOL_ERROR`

## Tests

Run the normal test suite:

```bash
pytest -q
```

Real Tophost integration tests are opt-in.

Read-only integration test:

```bash
TOPHOST_RUN_INTEGRATION_TESTS=1 \
pytest -q -s tests/integration/test_real_services_read.py
```

Real DNS mutation test:

```bash
TOPHOST_RUN_MUTATION_TESTS=1 \
pytest -q -s tests/integration/test_real_dns_crud.py
```

The mutation test creates a temporary DNS record, updates it, verifies it and
deletes it.

## Security

This API controls DNS records and must therefore be treated as a privileged
service.

At minimum:

- keep `TOPHOST_PASS` and `TOPHOST_API_KEY` outside the repository;
- keep the state directory private;
- bind to loopback unless an authenticated reverse proxy is intentionally used;
- use TLS before exposing the API over a network;
- use a high-entropy API key;
- never log passwords, cookies, OTP codes or trusted-session material.

See [SECURITY.md](SECURITY.md).

## Protocol notes

The Tophost protocol used by this project is unofficial and reverse engineered
from normal browser interactions with the account owner's own control panel.

Implementation notes are documented in
[`docs/protocol.md`](docs/protocol.md).

Because this is an unofficial integration, upstream HTML or endpoint changes
may require updates to the client.

## Upstream compatibility canary

A scheduled read-only canary exercises the same authentication, product
discovery, control-panel SSO and DNS parsing path used by the API.

True upstream compatibility drift creates or updates a deduplicated GitHub
issue automatically, and a later successful run closes it.

See [docs/canary.md](docs/canary.md) for the security model, exit codes and
repository-secret setup.

## Status

The current implementation has been validated against a real Tophost account
for:

- authentication using a persisted trusted 2FA session;
- domain discovery;
- control-panel SSO;
- DNS listing;
- DNS filtering;
- create;
- update including Tophost record-ID changes;
- delete;
- final absence verification.

Version `0.1.0` is an experimental public release. It has been validated against
a real Tophost account, including read-only discovery and DNS CRUD, but it relies
on unofficial reverse-engineered web flows that may change without notice.
