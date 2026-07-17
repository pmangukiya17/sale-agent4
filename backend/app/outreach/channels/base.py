"""
ChannelProvider plugin contract - structurally mirrors DiscoveryProvider/
ResearchProvider's fetch-provider pattern, but for RENDERING output rather
than fetching input: a new channel (LinkedIn, WhatsApp, phone script,
meeting request, ...) is a new class + a registry entry, never a schema
change. Exactly one concrete implementation exists for M4
(EmailChannelProvider), deterministic and rule-based - no network calls,
no model weights, fully reproducible, same explicit-stub convention as
M2's/M3's engines. A real LLM-backed provider can replace it later with
zero schema/pipeline change, provided it honors the dataclass shapes below.
"""
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any


@dataclass
class OutreachEvidenceDraft:
    """One evidence link for a rendered draft (or one block within it).
    References an existing PersonalizationStrategy/Signal/Recommendation/
    IntelligenceSnapshot by id - never duplicates their content. At least
    one of the four ids should be set; excerpt is a short human-readable
    pointer, not a copy of the underlying record. confidence_score lets
    future prompting filter/prioritize evidence by source reliability."""

    block_key: str | None = None
    personalization_strategy_id: Any | None = None
    signal_id: Any | None = None
    recommendation_id: Any | None = None
    intelligence_snapshot_id: Any | None = None
    excerpt: str | None = None
    confidence_score: float | None = None


@dataclass
class RenderedBlockDraft:
    """One rendered OutreachBlock, keyed by block_key so per-block
    explainability/editing stays possible even though everything is
    ultimately assembled into one channel-shaped output."""

    block_key: str
    behavior: str
    content: str
    reasoning: str | None = None


@dataclass
class ChannelRenderOutcome:
    model_used: str
    prompt_version_marker: str
    rendered_prompt: str
    blocks: list[RenderedBlockDraft]
    # Final channel-shaped output, e.g. {"subject": str, "body": str} for
    # email, {"message": str} for linkedin_message/whatsapp - documented
    # per channel_key, not a fixed column shape.
    assembled: dict[str, Any]
    reasoning: str | None = None
    confidence: float | None = None
    evidence: list[OutreachEvidenceDraft] = field(default_factory=list)


class ChannelProvider(ABC):
    """Abstract base every concrete channel renderer implements."""

    key: str

    @abstractmethod
    def render(self, context: "OutreachContext") -> ChannelRenderOutcome:  # noqa: F821 - avoid circular import
        """Render one piece of outreach for the contact/channel in context.
        Must not raise for "not enough information" - return a low-
        confidence, generic-but-honest outcome instead; only raise for a
        genuine provider failure."""
        raise NotImplementedError
