# Tophost protocol notes

This document describes the behavior currently required by the client.

It is not official Tophost API documentation.

No credentials, account identifiers, domain names, session values or captured
authentication tokens belong in this document.

## Account authentication

The login flow starts by retrieving the Tophost access page.

The page contains a CSRF token used by the asynchronous login request.

The login request submits:

- username;
- password;
- the CSRF token;
- the fields expected by the Tophost login form.

After successful primary authentication, accessing the account area indicates
one of two relevant states:

- the trusted 2FA session is accepted and the account continues to the product
  area;
- two-factor authentication is required.

## Two-factor authentication

Entering the 2FA page causes Tophost to initiate the OTP flow.

After successful OTP verification, Tophost can issue a trusted 2FA cookie with
a configurable validity period.

The application persists only the authentication material required to reuse the
trusted session.

Pending OTP state is also persisted so an API process restart between requesting
and verifying an OTP does not destroy the challenge.

Public API clients receive a generated challenge ID rather than the underlying
Tophost session data.

## Product and domain discovery

The authenticated product page contains links whose function parameter embeds
an internal Tophost product identifier.

The surrounding page content contains the associated domain.

The parser discovers the relationship dynamically.

The public API uses domain names as resource identifiers and deliberately hides
Tophost product IDs.

An account may contain multiple domains.

## Control-panel SSO

DNS management is hosted on the Tophost control-panel host.

Selecting a product through the authenticated account page initiates an SSO
redirect to the control panel.

The HTTP session follows that handoff and receives the control-panel cookies
needed for DNS operations.

The client validates that SSO terminates on the expected Tophost control-panel
host instead of trusting an arbitrary redirect destination.

## DNS listing

The DNS page renders records as HTML table rows.

Each record exposes:

- record identifier;
- name;
- type;
- value;
- priority.

The record identifier is an upstream implementation detail but is required to
address individual records.

## DNS creation

DNS records are created through the control panel's DNS mutation endpoint.

The request contains:

- a temporary client record identifier;
- record name;
- type;
- value;
- priority when applicable.

The response contains the actual Tophost record identifier.

The client treats an already-identical record as a no-op and avoids sending a
mutation.

## DNS update

Updating a record submits both the current state and requested new state.

The upstream record identifier may change when record contents change.

Therefore callers must always use the identifier returned in the mutation
result rather than assuming the old identifier remains valid.

## DNS deletion

Deletion addresses the current upstream record identifier.

The service supports an expected value and expected priority before issuing the
delete.

## Optimistic concurrency

Before update or delete, the client can reread the record and compare its
current state with values previously observed by the caller.

If they differ, the operation fails with `RECORD_CHANGED` and no mutation is
sent upstream.

This behavior is particularly important for automated clients and LLM/MCP
integrations that may operate on stale context.

## Upstream mutation responses

Mutation responses are expected to identify whether the control-panel session
is authenticated.

Unexpected authentication states or response structures are treated as protocol
errors.

The client does not guess when the upstream response changes.

## Compatibility

This protocol is based on observed browser behavior and may change without
notice.

Parsing and mutation logic should therefore remain isolated inside the client
layer and covered by tests.
