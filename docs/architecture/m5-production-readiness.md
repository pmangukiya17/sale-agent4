# M5 (Outreach Delivery Engine) — production-readiness review

**Status:** written during M5 Layer 7 (Integration & Final Verification),
after Layers 1–6 were each individually verified and approved. This is a
review of what M5 actually is once assembled, not a proposal — nothing
below is a design change, only documentation of decisions already made
and one explicit, permanent testing boundary a future reader shouldn't
mistake for an oversight.

## The permanent testing boundary

`GmailProvider.send()` and `OutlookProvider.send()` have never been
executed against a real mailbox, in this environment or any other. That
is not a sandbox limitation — no automated environment can complete a
real Google/Microsoft OAuth consent screen unattended, so this boundary
would exist in a full CI pipeline exactly as it does here. `verify_layer7.sh`
proves the entire pipeline around those two calls (worker polling,
`SELECT...FOR UPDATE SKIP LOCKED` claiming, `dispatch_service`, event
logging, campaign completion) end-to-end via the deterministic
no-credential FAILED path, but the provider `send()` call itself remains
unverified by execution until a human completes at least one real send
through each provider. Treat that as a required gate, not a nice-to-have:
see the checklist `verify_layer7.sh` prints at the end.

A related, narrower boundary: dispatch-time rate-limit enforcement (the
live rolling-window recheck in `dispatch_service.dispatch()`, as distinct
from the scheduling-time pacing in `windows.generate_send_times`, which
*is* unit-tested) can't be exercised either, for the same root cause —
triggering it requires prior `SENT` events, which requires a real send.

## CREDENTIAL_ENCRYPTION_KEY rotation

If this key ever changes, every row `PostgresFernetCredentialStore` has
already encrypted becomes silently undecryptable
(`CredentialStoreError` on next use). There is no migration path for a
key rotation today — a leaked key is a worse failure mode than a lost
one, so this was a deliberate omission, not a gap. The recovery is
Reconnect, per affected `ProviderConnection`, the same operation already
used for an expired token. Anyone rotating this key in production should
expect every connected mailbox to need reconnecting afterward.

## Worker concurrency safety

`FIFOSchedulingPolicy.claim_next_batch` uses `SELECT...FOR UPDATE SKIP
LOCKED`, which is safe under concurrent claimers by construction — this
is a well-established Postgres pattern specifically for this problem.
`docker-compose.yml` runs exactly one `worker` replica today, so this
guarantee is not currently exercised under real concurrency by anything
in this repository, automated or manual. **Before ever setting worker
replicas > 1**, run a stress test first: scale the worker
(`docker compose up -d --scale worker=3`), enqueue a batch of items, and
confirm no `DeliveryEvent(STARTED)` is ever logged twice for the same
queue item. This is deferred by explicit decision (current deployment
doesn't need it), not because the guarantee is in doubt.

## Cancel does not interrupt an in-flight send

`campaign_service.cancel_campaign` only cancels items in `QUEUED`,
`SCHEDULED`, or `RETRY`. An item already claimed (`SENDING`) at the
moment of cancellation is deliberately left alone to finish that attempt
— there is no way to interrupt a request already sent to Gmail/Graph's
API, so pretending to cancel it would be misleading. This is intended
behavior, documented here so a future reader doesn't mistake it for a
missed case.

## Secrets management

`SECRET_KEY` (also used to sign OAuth `state`), `GMAIL_OAUTH_CLIENT_SECRET`,
`MICROSOFT_OAUTH_CLIENT_SECRET`, and `CREDENTIAL_ENCRYPTION_KEY` all live
in `.env` as plain environment variables — consistent with how
`POSTGRES_PASSWORD` already worked before M5, not a new gap M5
introduced. Moving to a real secrets manager (Vault, AWS/Azure Key
Vault) is future work that applies to the whole application, not
something M5 should solve in isolation.

## M6-readiness re-check

`docs/architecture/future-milestones.md` note 9 (AI Mailbox Brief, M6)
was written during M5 planning and made specific claims about what M5
would leave in place. Re-checked against the actual code at the close of
M5:

- Capability-based providers: `EmailConnectionProvider`,
  `EmailSendCapable`, and `MailboxReadCapable` all exist as separate
  classes in `app/delivery/providers/base.py`, exactly as designed —
  confirmed still true.
- `scopes_granted` (JSONB) exists on `ProviderConnection`
  (`app/models/provider_connection.py`), so M6 can check read-scope
  presence before attempting a fetch — confirmed still true.
- Reconnect (`start_provider_reconnect` /
  `build_reconnect_authorize_url`) is generic — it takes a scope list,
  not a hardcoded send-only one — so M6 can reuse it for progressive
  read-scope consent without new OAuth plumbing — confirmed still true.

No drift found. M6 can proceed on the assumptions note 9 recorded.

## Required gate before tagging M5-Stable

1. All of `verify_layer7.sh` passes locally (46-step smoke test, full
   unit test suite, worker crash-recovery check).
2. At least one real send confirmed manually through a real Gmail
   account.
3. At least one real send confirmed manually through a real Microsoft
   365/Outlook account.

Once all three are confirmed, M5 is ready to be tagged `M5-Stable`.
