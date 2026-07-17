"""
PersonalizationEngine plugin contract - mirrors AIAnalysisEngine's shape
(M2). Exactly one concrete implementation exists for M3
(DeterministicPersonalizationEngine) - deliberately NOT a real LLM call,
same explicit prohibition as M2's AI Analysis Engine. A real LLM-backed
engine can replace it later as a second class implementing this same
interface, with zero schema/pipeline change, provided it honors the
dataclass shapes below - those, not any specific engine, are what the
pipeline and DB depend on.
"""
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any

from app.models.enums import (
    BuyerReadinessLevel,
    CommunicationFormality,
    CommunicationIntensityLevel,
    CommunicationLength,
    PersonalizationStrategyRank,
)
from app.personalization.context import PersonalizationContext


@dataclass
class EvidenceDraft:
    """One evidence link for a strategy - references an existing Signal/
    Recommendation/IntelligenceSnapshot by id. At least one of the three
    ids should be set; excerpt is a short human-readable pointer, not a
    copy of the underlying record."""

    signal_id: Any | None = None
    recommendation_id: Any | None = None
    intelligence_snapshot_id: Any | None = None
    excerpt: str | None = None


@dataclass
class StrategyDraft:
    strategy_rank: PersonalizationStrategyRank
    title: str
    narrative: str
    confidence: float | None = None
    reasoning: str | None = None
    evidence: list[EvidenceDraft] = field(default_factory=list)


@dataclass
class CommunicationStrategyDraft:
    formality: CommunicationFormality
    directness: CommunicationIntensityLevel
    warmth: CommunicationIntensityLevel
    technical_depth: CommunicationIntensityLevel
    authority: CommunicationIntensityLevel
    consultative_level: CommunicationIntensityLevel
    urgency: CommunicationIntensityLevel
    message_length: CommunicationLength
    rationale: str | None = None


@dataclass
class PersonalizationOutcome:
    model_used: str
    prompt_version: str
    buyer_persona: dict[str, Any]
    buyer_readiness: BuyerReadinessLevel
    buyer_readiness_reasoning: str | None
    communication_strategy: CommunicationStrategyDraft
    # 1-3 entries, ranks must be distinct (PRIMARY required; SECONDARY/
    # FALLBACK optional depending on how much material is available).
    strategies: list[StrategyDraft]
    # Derived projection - see PersonalizationSnapshot's docstring for the
    # exact shape. Assembled by the pipeline from this outcome, not
    # authored directly by the engine, so every engine implementation
    # (stub or future LLM) automatically gets it for free and consistent.


class PersonalizationEngine(ABC):
    """Abstract base every concrete personalization engine implements."""

    @abstractmethod
    def synthesize(self, context: PersonalizationContext) -> PersonalizationOutcome:
        """Synthesize a sales strategy for the prospect in context. Must
        not raise for "not enough information" - return a low-confidence
        outcome (buyer_readiness=UNKNOWN, a single cautious fallback
        strategy) instead; only raise for a genuine engine failure."""
        raise NotImplementedError
