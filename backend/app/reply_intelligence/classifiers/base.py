"""
ReplyClassifier abstraction (M6.4) - exact mirror of this codebase's
existing plugin-interface pattern (EmailConnectionProvider in
app/delivery/providers/base.py, CredentialStore in
app/delivery/credentials/base.py, DiscoveryProvider/ResearchProvider):
a small ABC plus a narrow, provider-neutral input/output data shape, so
reply_intelligence_worker.py depends only on this interface and never on
a concrete implementation. Swapping the deterministic rules engine for
OpenAI/Claude/Gemini/a local model later is a new class + one registry
entry (see registry.py) - zero worker changes.

ReplyClassificationInput carries PLAIN TEXT only (see
app/core/text_extraction.py) - no classifier implementation, rule-based
or AI-based, ever receives an EmailMessage ORM object or raw HTML. This
keeps every classifier trivially testable in isolation (plain strings in,
a plain result out) and keeps the classifier layer completely decoupled
from SQLAlchemy.
"""
from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime

from app.models.enums import ReplyStatus


@dataclass(frozen=True)
class ReplyClassificationInput:
    """Everything a classifier is given to make its decision. `text` is
    the output of app.core.text_extraction.extract_plain_text() - subject
    + body, already flattened to plain text. from_email/received_at are
    plain metadata (not text-extraction concerns) included for classifiers
    that might use sender-domain or recency heuristics in the future; the
    MVP rules classifier does not use them today."""

    text: str
    from_email: str | None = None
    received_at: datetime | None = None


@dataclass(frozen=True)
class ReplyClassificationResult:
    """reason is optional and unused by the worker today - included now
    so a future AI-backed classifier can populate a human-readable
    explanation (e.g. "the model detected a scheduling request") without
    ever requiring a change to this dataclass's shape again, per explicit
    M6.4 direction to future-proof the interface up front."""

    reply_status: ReplyStatus
    needs_human_review: bool
    reason: str | None = None


class ReplyClassifier(ABC):
    """One method, deliberately - classify() is synchronous and pure
    from the worker's point of view (whether a concrete implementation
    makes a network call to an AI provider internally is that
    implementation's own concern, invisible to the interface)."""

    @abstractmethod
    def classify(self, input_data: ReplyClassificationInput) -> ReplyClassificationResult:
        raise NotImplementedError
