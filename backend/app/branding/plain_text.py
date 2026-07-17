"""
Deterministic HTML -> plain text derivation for BrandEmailSignature.
signature_plain_text is ALWAYS derived server-side from signature_html -
never accepted from the client - so it can never drift out of sync with
the actual HTML. Stdlib-only (re + html.unescape), no new dependency,
consistent with every other deterministic-stub piece of this project.

Not intended to be a general-purpose HTML-to-text converter - just enough
to give non-HTML consumers (plain-text email clients, future search/index
use) a readable fallback of a signature block.
"""
import html
import re

_BLOCK_TAGS = re.compile(
    r"</(p|div|h[1-6]|li|tr|table|blockquote)\s*>",
    re.IGNORECASE,
)
_LINE_BREAK_TAGS = re.compile(r"<(br|hr)\s*/?>", re.IGNORECASE)
_TAG_PATTERN = re.compile(r"<[^>]+>")
_BLANK_LINES = re.compile(r"\n{3,}")
_TRAILING_SPACES = re.compile(r"[ \t]+\n")


def html_to_plain_text(signature_html: str | None) -> str | None:
    if not signature_html or not signature_html.strip():
        return None

    text = _LINE_BREAK_TAGS.sub("\n", signature_html)
    text = _BLOCK_TAGS.sub("\n", text)
    text = _TAG_PATTERN.sub("", text)
    text = html.unescape(text)
    text = _TRAILING_SPACES.sub("\n", text)
    text = _BLANK_LINES.sub("\n\n", text)
    text = text.strip()
    return text or None
