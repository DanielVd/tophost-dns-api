# Security Policy

## Scope

Tophost DNS API handles credentials and operations capable of changing DNS
configuration. Treat deployments as privileged infrastructure.

## Secrets

Never commit:

- Tophost usernames or passwords;
- REST API keys;
- OTP codes;
- session cookies;
- trusted 2FA cookies;
- runtime authentication state;
- browser captures containing authenticated requests.

The repository contains only configuration examples with placeholder values.

## Runtime state

Authentication state must be stored outside the source repository.

The application writes state files atomically and restricts them to mode
`0600`, with the containing directory restricted to mode `0700`.

## Network exposure

The recommended development binding is:

```text
127.0.0.1
```

Do not expose the development Uvicorn server directly to the Internet.

If remote access is required, place the application behind an appropriately
secured reverse proxy with TLS and additional network access controls.

## API authentication

All `/v1` routes require `X-API-Key`.

API-key comparisons use constant-time comparison.

`/health` intentionally does not require authentication and returns only a
minimal status value.

## DNS mutations

Update and delete operations support expected-state values for optimistic
concurrency.

Automated clients should use them to prevent mutations based on stale state.

## Logging

Passwords, API keys, OTP codes, cookies and authentication-state contents must
never be logged.

## Upstream dependency

This project uses an unofficial Tophost integration.

Changes to the Tophost control panel can cause parsing or protocol failures.
Unexpected upstream responses should fail closed rather than trigger guessed
mutations.

## Reporting security issues

Do not disclose suspected vulnerabilities through a public issue while a
repository is public.

Use a private communication channel provided by the repository owner.
