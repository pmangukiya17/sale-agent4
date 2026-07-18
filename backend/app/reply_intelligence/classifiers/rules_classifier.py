"""
RulesReplyClassifier - the M6.4 MVP ReplyClassifier implementation:
deterministic, keyword/pattern-based, no AI provider, no network call.
Registered as backend key "rules" in registry.py (the default via
REPLY_CLASSIFIER_BACKEND).

Modular by construction: each category (OUT_OF_OFFICE, NEGATIVE,
POSITIVE) is its own independent _RuleSet (a name + an ordered tuple of
compiled regexes), and classify() is a single small loop over an ordered
list of rule sets - not an if/elif chain. Adding a keyword is a one-line
change to a pattern tuple; adding an entirely new category is a new
_RuleSet appended to _RULES_IN_PRIORITY_ORDER, with no change to the
matching logic itself.

Priority order matters and is deliberate, checked top to bottom, first
match wins:

  1. OUT_OF_OFFICE - checked FIRST. An auto-responder has a recognizable,
     structural signature (its own generated subject/opening line, e.g.
     "Automatic reply:"/"Out of Office") - checking this before scanning
     for sentiment keywords prevents an auto-reply's incidental wording
     (e.g. "I am currently not available") from ever being confused with
     a real human's NEGATIVE reply.
  2. NEGATIVE - checked before POSITIVE. A commercially important signal
     (see needs_human_review below) - a reply containing both a decline
     phrase and an unrelated positive-sounding word should still be
     treated as a decline, not silently overridden.
  3. POSITIVE - checked last of the three specific categories.
  4. NEUTRAL - the default when nothing above matched: no confident
     signal either way, not "no reply."

needs_human_review, per explicit M6.4 direction (negative replies are
commercially important and must be surfaced):
    POSITIVE        -> False (confident, no action needed beyond normal flow)
    OUT_OF_OFFICE    -> False (confident, purely informational)
    NEGATIVE        -> True  (commercially important, always surfaced)
    NEUTRAL         -> True  (no confident signal - ambiguous by definition)
"""
import re
from dataclasses import dataclass

from app.models.enums import ReplyStatus
from app.reply_intelligence.classifiers.base import ReplyClassificationInput, ReplyClassificationResult, ReplyClassifier

_NEEDS_HUMAN_REVIEW_BY_STATUS: dict[ReplyStatus, bool] = {
    ReplyStatus.POSITIVE: False,
    ReplyStatus.OUT_OF_OFFICE: False,
    ReplyStatus.NEGATIVE: True,
    ReplyStatus.NEUTRAL: True,
}


@dataclass(frozen=True)
class _RuleSet:
    reply_status: ReplyStatus
    name: str
    patterns: tuple[re.Pattern, ...]


def _compile_phrases(*phrases: str) -> tuple[re.Pattern, ...]:
    """Case-insensitive, word-boundary-anchored substring match for each
    phrase - `\\b` around a multi-word phrase still correctly anchors on
    its first/last word boundaries, so this works for both single words
    ("yes") and phrases ("not interested") without a separate code path."""
    return tuple(re.compile(r"\b" + re.escape(phrase) + r"\b", re.IGNORECASE) for phrase in phrases)


_OUT_OF_OFFICE = _RuleSet(
    reply_status=ReplyStatus.OUT_OF_OFFICE,
    name="out_of_office",
    patterns=_compile_phrases(
        "out of office",
        "out of the office",
        "automatic reply",
        "auto-reply",
        "autoreply",
        "away from the office",
        "away from my email",
        "on leave",
        "on vacation",
        "vacation responder",
        "currently out",
        "will be back on",
        "i am currently away",
        "i'm currently away",
    ),
)

_NEGATIVE = _RuleSet(
    reply_status=ReplyStatus.NEGATIVE,
    name="negative",
    patterns=_compile_phrases(
        "not interested",
        "no thanks",
        "no thank you",
        "remove me",
        "unsubscribe",
        "stop emailing",
        "please stop",
        "do not contact",
        "don't contact",
        "not looking",
        "not a good fit",
        "no longer interested",
        "we're all set",
        "we are all set",
        "please remove",
    ),
)

_POSITIVE = _RuleSet(
    reply_status=ReplyStatus.POSITIVE,
    name="positive",
    patterns=_compile_phrases(
        "yes",
        "interested",
        "let's schedule",
        "lets schedule",
        "sounds good",
        "sign me up",
        "let's talk",
        "lets talk",
        "let's connect",
        "lets connect",
        "set up a call",
        "schedule a call",
        "book a time",
        "count me in",
        "works for me",
        "happy to chat",
    ),
)

# Priority order - see module docstring for why this exact order.
_RULES_IN_PRIORITY_ORDER: tuple[_RuleSet, ...] = (_OUT_OF_OFFICE, _NEGATIVE, _POSITIVE)


class RulesReplyClassifier(ReplyClassifier):
    backend_key = "rules"

    def classify(self, input_data: ReplyClassificationInput) -> ReplyClassificationResult:
        text = input_data.text or ""

        for rule_set in _RULES_IN_PRIORITY_ORDER:
            for pattern in rule_set.patterns:
                match = pattern.search(text)
                if match:
                    return ReplyClassificationResult(
                        reply_status=rule_set.reply_status,
                        needs_human_review=_NEEDS_HUMAN_REVIEW_BY_STATUS[rule_set.reply_status],
                        reason=f"matched {rule_set.name} keyword: '{match.group(0)}'",
                    )

        return ReplyClassificationResult(
            reply_status=ReplyStatus.NEUTRAL,
            needs_human_review=_NEEDS_HUMAN_REVIEW_BY_STATUS[ReplyStatus.NEUTRAL],
            reason="no rule matched",
        )
