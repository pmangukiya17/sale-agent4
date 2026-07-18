"""
Pure subject-normalization logic - no I/O, no DB, unit-testable in
isolation, same "extract pure helpers" precedent as normalize.py. Shared
by two call sites that must never drift apart on what "the same subject"
means: conversation_resolver.py (computing Conversation.conversation_key
at creation time) and thread_matching.py (subject-fallback matching,
step 6 of the M6.3 threading algorithm).
"""
import re

# Repeated, case-insensitive Re:/Fwd:/Fw:/RE:/FWD:/FW: prefixes - applied
# in a loop below because real mail clients commonly produce chains like
# "Re: Fwd: Re: Quote request", not just one prefix.
_PREFIX_RE = re.compile(r"^\s*(re|fwd?|fw)\s*:\s*", re.IGNORECASE)


def normalize_subject(subject: str | None) -> str:
    """Strips repeated reply/forward prefixes, case-folds, and trims -
    returns "" for a missing subject (never None), so callers can always
    treat the result as a plain string for comparison/storage without a
    None-check. Deliberately NOT a hash or any other lossy transform -
    Conversation.conversation_key stores this value directly (see that
    model's own docstring: "indexed for fast lookup, never constrained"),
    so a human reading the column should be able to see the real
    normalized subject, not an opaque digest."""
    if not subject:
        return ""
    text = subject
    while True:
        stripped = _PREFIX_RE.sub("", text)
        if stripped == text:
            break
        text = stripped
    return text.strip().lower()
