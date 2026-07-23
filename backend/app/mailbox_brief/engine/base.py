"""
MailboxBriefEngine plugin contract - mirrors PersonalizationEngine's
shape (app/personalization/engine/base.py). Exactly one concrete
implementation exists for this initial slice
(DeterministicMailboxBriefEngine) - deliberately NOT a real LLM call, for
the same reason this project's other AI-shaped capabilities shipped a
deterministic stub first (Discovery's scoring, M2's AI Analysis Engine,
M3's Personalization engine): no third-party provider SDK
(anthropic/openai/google-genai) is installed in the environment this was
authored in, and this project's own established discipline is to prove
the schema/service/API machinery end to end with a real, deterministic,
zero-network implementation before wiring in a real provider call - not
to write an untestable code path against a live API key. A real
LLM-backed engine can replace this one later as a second class
implementing this same interface, with zero schema/route change,
provided it honors the BriefOutcome shape below.
"""
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any

from app.mailbox_brief.context import MailboxBriefContext


@dataclass(frozen=True)
class BriefRecommendation:
    """One concrete, traceable-back-to-real-data action item - never
    free-floating advice with nothing behind it. `source_type`/
    `source_id` point at the real row (a Recommendation, a Conversation,
    or None for a purely statistical observation like "N deals in
    negotiation") this suggestion was derived from."""

    title: str
    rationale: str
    source_type: str | None = None
    source_id: Any | None = None


@dataclass(frozen=True)
class BriefOutcome:
    ai_provider: str
    ai_model: str
    summary: str
    recommendations: list[BriefRecommendation] = field(default_factory=list)
    statistics: dict[str, Any] = field(default_factory=dict)


class MailboxBriefEngine(ABC):
    """Abstract base every concrete mailbox-brief engine implements."""

    @abstractmethod
    def synthesize(self, context: MailboxBriefContext) -> BriefOutcome:
        """Synthesize an executive summary from the given context. Must
        not raise for "nothing to report" (an empty workspace) - return
        an honest, low-content outcome instead (a summary saying so, an
        empty recommendations list); only raise for a genuine engine
        failure."""
        raise NotImplementedError
