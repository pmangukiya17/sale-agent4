"""
Pure scope-list math for the OAuth reconnect flow - Outlook Integration
milestone (found during CEO-reported live testing: outbound send was
failing with a Graph 403 because the draft-creation call needs
Mail.ReadWrite, which was never requested - see
app/delivery/providers/outlook_provider.py's own docstring for the full
root cause).

Deliberately its own zero-dependency module - nothing beyond the stdlib,
no sqlalchemy, no FastAPI - so this logic can be unit-tested without a
database connection at all. This mirrors the precedent
app/opportunities/state_machine.py already set for Track C3: pure logic
pulled out of a module that otherwise has heavy DB/ORM imports, so it can
actually be run to completion in an environment with no Postgres/Docker
access, rather than only checked via py_compile. connection_service.py
(which does need a real Session/ProviderConnection to look up a
connection at all) is the only caller - the database side of that
function is orthogonal to this list-math and was never a reason for the
two to live in the same untestable-without-a-DB module.
"""


def top_up_scopes(
    already_granted: list[str] | None,
    baseline: list[str],
    *,
    additional: list[str] | None = None,
) -> list[str]:
    """Builds the scope list a Reconnect authorize-URL should request.

    Before this fix, build_reconnect_authorize_url re-requested EXACTLY
    `already_granted` (or `baseline` as a fallback only when nothing was
    granted yet) - a literal replay of history. That meant a product-side
    change to what a provider's send_scopes baseline requires (e.g.
    adding Mail.ReadWrite once the create-draft-then-send send() pattern
    needed it) would never reach an already-connected business no matter
    how many times they reconnected - the old logic would just re-request
    the same, now-stale, too-narrow list forever, since the connection
    record itself has no way to know the baseline changed.

    This function instead always returns `already_granted` UNIONED with
    `baseline` (the provider class's CURRENT requirement, read fresh by
    the caller on every call) - so any Reconnect "tops up" a connection to
    at least today's baseline automatically. `additional` (e.g. a
    provider's read_scopes, for the separate, explicit mailbox-reading
    opt-in) is unioned in last, only when the caller actually wants it -
    never included by default, since mailbox reading is a materially more
    sensitive grant than "top up my send permissions" and must stay an
    explicit, deliberate ask, not a side effect of a routine repair.

    Order is preserved on first appearance (whichever list a scope first
    appears in wins its position) and duplicates are dropped - purely for
    a stable, predictable, diffable output; OAuth consent screens don't
    care about scope order.
    """
    scopes = list(already_granted or [])
    for scope in baseline:
        if scope not in scopes:
            scopes.append(scope)
    if additional:
        for scope in additional:
            if scope not in scopes:
                scopes.append(scope)
    return scopes
