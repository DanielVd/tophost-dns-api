# Upstream compatibility canary

The repository includes a live, read-only compatibility canary for the
unofficial Tophost integration.

Its purpose is not to detect arbitrary HTML changes. It exercises the same
authentication, product discovery, control-panel SSO and DNS parser code used
by the API and reports only changes that affect compatibility.

## What it checks

The canary performs these read-only stages:

1. primary login and trusted 2FA reuse;
2. product/domain discovery;
3. control-panel SSO;
4. DNS page retrieval;
5. DNS record parsing.

It never creates, updates or deletes DNS records.

The canary output is deliberately sanitized. It does not include domain names,
credentials, cookies, OTP values, authenticated HTML or response bodies.

## Exit codes

| Code | Status | Meaning |
| ---: | --- | --- |
| 0 | compatible | The live Tophost path is compatible. |
| 10 | transient | Network, rate-limit or temporary upstream failure. |
| 20 | attention | Authentication or local canary configuration needs attention. |
| 30 | drift | Tophost structure/protocol is no longer compatible. |
| 1 | error | Unexpected internal canary failure. |

Transient failures are retried by the GitHub Actions workflow before the run is
marked failed.

Only exit code 30 creates or updates the public upstream-drift issue. A later
successful run comments on and closes that issue automatically.

## GitHub Actions workflow

The workflow is defined in:

`.github/workflows/upstream-canary.yml`

It runs every six hours at minute 23 in the `Europe/Rome` timezone and can
also be started manually with `workflow_dispatch`.

The workflow uses a GitHub-hosted runner. It does not use a self-hosted runner,
which keeps a future public repository from exposing a machine on the local
network to untrusted pull-request code.

The workflow token is restricted to:

- `contents: read`
- `issues: write`

## Required repository secrets

Configure these GitHub Actions repository secrets:

- `TOPHOST_USER`
- `TOPHOST_PASS`
- `TOPHOST_DEFAULT_DOMAIN`
- `TOPHOST_TRUST_B64`

`TOPHOST_API_KEY` is not required because the canary calls the client layer
directly rather than the REST API.

The trusted 2FA state is transported as base64 only to keep the GitHub secret
single-line. Base64 is not encryption; GitHub Actions secret storage provides
the secret protection.

Set the secrets interactively:

```bash
gh secret set TOPHOST_USER --repo OWNER/tophost-dns-api
gh secret set TOPHOST_PASS --repo OWNER/tophost-dns-api
gh secret set TOPHOST_DEFAULT_DOMAIN --repo OWNER/tophost-dns-api
```

Encode the existing trusted state file directly into the fourth secret:

```bash
base64 -w0 /path/to/tophost-state/2fa.json \
  | gh secret set TOPHOST_TRUST_B64 --repo OWNER/tophost-dns-api
```

Refresh `TOPHOST_TRUST_B64` whenever the trusted 2FA state is renewed.

## Local execution

The canary uses the standard Tophost environment variables and state directory:

```bash
python -m tophost_api.canary
```

For a legitimately empty DNS zone:

```bash
python -m tophost_api.canary --allow-empty-dns
```

The default behavior requires at least one parsed DNS record. This makes a
complete DNS markup change fail closed rather than appearing as an empty,
healthy zone.

## Public repository behavior

Repository secrets are not exposed to workflows triggered from fork pull
requests. The canary workflow itself has no `pull_request` trigger.

Scheduled workflows in public repositories may be disabled by GitHub after a
long period of repository inactivity. If that happens, re-enable the workflow
or update its schedule from an account with write access.
