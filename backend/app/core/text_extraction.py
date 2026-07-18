"""
Shared, reusable EmailMessage -> plain-text extraction - lives in
app/core, deliberately NOT inside app/reply_intelligence, per explicit
M6.4 architecture direction: Reply Intelligence must not own HTML
parsing, because this helper is not a reply-classification concern. It
is the one place in this codebase that turns an EmailMessage's raw,
provider-shaped content (body_text, body_html, subject) into a single
plain-text string - every future consumer that needs "what did this
email actually say" as text (sentiment analysis, lead scoring,
summarization, search indexing, embeddings, and whatever AI-first
features arrive after M6.4) is expected to call this function rather
than re-implement HTML handling itself.

Pipeline (per the approved M6.4 design):

    EmailMessage -> extract_plain_text() -> plain text -> (classifier / any future consumer)

Real, disclosed limitation this module exists to work around: as of
M6.4, OutlookProvider (the only implemented IncrementalSyncCapable
provider - see app/delivery/providers/outlook_provider.py) never
populates EmailMessage.body_text; only body_html is ever set for a real
inbound message today. Every consumer of "the text of this email" would
otherwise have to know that and handle HTML itself - this helper is the
single place that fact lives, so nothing downstream has to know or care
which field a given provider happened to populate.

Deliberately minimal HTML handling for the MVP: strips tags and decodes
common entities via the standard library's html.unescape - no third-party
HTML parser, no attempt at semantic extraction (e.g. dropping quoted
reply chains, signature blocks, or tracking pixels). If that precision is
ever needed by a future consumer, it belongs as an evolution of this one
shared function, not a parallel implementation.
"""
import html as html_module
import re
from typing import Protocol

_TAG_RE = re.compile(r"<[^>]+>")
_WHITESPACE_RE = re.compile(r"[ \t\f\v]+")
_BLANK_LINES_RE = re.compile(r"\n\s*\n+")
# A stripped inline tag (e.g. "...<b>interested</b>, thanks" -> "...
# interested , thanks") leaves a stray space directly before punctuation
# - collapse "word <punct>" back to "word<punct>" so tag-stripping never
# changes a phrase's actual wording/punctuation, which matters here since
# the classifier matches literal phrases like "not interested,".
_SPACE_BEFORE_PUNCT_RE = re.compile(r"\s+([,.;:!?])")


class _HasEmailText(Protocol):
    """Structural type, not app.models.email_message.EmailMessage
    directly - keeps this module import-light and usable against any
    object shaped like an email (an ORM row, a test fixture, a future
    non-EmailMessage source) without a hard model dependency."""

    subject: str | None
    body_text: str | None
    body_html: str | None


def _strip_html(raw_html: str) -> str:
    """Best-effort tag-strip + entity-decode - not a substitute for a
    real HTML parser, sufficient for keyword/phrase matching against
    short reply bodies, which is all M6.4's rule-based classifier needs."""
    without_tags = _TAG_RE.sub(" ", raw_html)
    decoded = html_module.unescape(without_tags)
    collapsed = _WHITESPACE_RE.sub(" ", decoded)
    depunctuated = _SPACE_BEFORE_PUNCT_RE.sub(r"\1", collapsed)
    return _BLANK_LINES_RE.sub("\n\n", depunctuated).strip()


def extract_plain_text(message: _HasEmailText) -> str:
    """Returns the best available plain-text representation of an email:
    subject followed by a blank line and the body. Body preference order:
    body_text if present and non-blank (the provider gave us real plain
    text - trust it verbatim, no need to touch body_html at all), else a
    tag-stripped/entity-decoded version of body_html, else "" (a message
    can genuinely have no body). Subject is always included when present
    - it is part of "what this email says" (e.g. an Out-of-Office
    auto-reply's signal is often carried entirely in the subject line, or
    a terse reply that puts its entire content in the subject), not
    metadata to be handled separately by callers.

    Never raises - a message with no subject and no body of either kind
    returns "".
    """
    subject = (message.subject or "").strip()

    if message.body_text and message.body_text.strip():
        body = message.body_text.strip()
    elif message.body_html and message.body_html.strip():
        body = _strip_html(message.body_html)
    else:
        body = ""

    if subject and body:
        return f"{subject}\n\n{body}"
    return subject or body
