"""
AI Analysis Engine plugin contract. Exactly one concrete implementation
exists in M2 (DeterministicAnalysisEngine, see deterministic_stub.py) -
a rule-based keyword/pattern extractor, deliberately NOT a real LLM call
(explicitly forbidden for this milestone: no OpenAI/Claude/Gemini/Azure/
Ollama). A real LLM-backed engine can replace it later as a second class
implementing this same interface, with zero schema or pipeline change,
provided it honors the structured_output contract documented per
AIAnalysisType below - that contract, not any specific engine, is what
the pipeline and DB schema depend on.

structured_output contract (a plain dict, validated at the Pydantic/API
layer per type, never at the DB layer):

- COMPANY_PROFILE: {business_model, products_offered[], markets_served[],
  certifications[], manufacturing_or_trading, sustainability_notes,
  import_export_activity[]}
- BUYER_PROFILE: {buyer_notes, procurement_structure, purchasing_process}
- BUSINESS_SIGNALS: {signals: [{signal_type, title, description,
  importance, urgency, confidence, reasoning, evidence_document_indices[]}],
  signals_summary}
- SALES_INTELLIGENCE: {recommendations: [{recommendation_type, title,
  rationale, product_id, confidence, reasoning, evidence_document_indices[]}]}

evidence_document_indices are positions into the raw_documents list
handed to analyze() - the pipeline resolves them to real RawDocument ids
when building Signal/RecommendationEvidence rows.
"""
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any

from app.models.enums import AIAnalysisType
from app.models.raw_document import RawDocument
from app.research.context import ResearchContext


@dataclass
class AnalysisOutcome:
    analysis_type: AIAnalysisType
    model_used: str
    prompt_version: str
    structured_output: dict[str, Any]
    confidence: float | None = None
    reasoning: str | None = None
    raw_model_output: dict[str, Any] | None = None
    # Which of the raw_documents passed to analyze() this particular
    # outcome actually drew on - becomes ai_analysis_source_documents rows.
    source_document_indices: list[int] = field(default_factory=list)


class AIAnalysisEngine(ABC):
    """Abstract base every concrete AI analysis engine implements."""

    @abstractmethod
    def analyze(
        self, context: ResearchContext, raw_documents: list[RawDocument], *, premium_approved: bool = False
    ) -> list[AnalysisOutcome]:
        """Analyze the given raw documents for one prospect and return zero
        or more AnalysisOutcome objects (at most one per AIAnalysisType).
        Must not raise for "nothing found" - return outcomes with empty/
        null fields and low confidence instead; only raise for a genuine
        engine failure.

        `premium_approved` (M11, AI Provider Hierarchy) - default False so
        every existing/future engine implementation keeps working
        unmodified if it has no notion of provider tiers at all (e.g.
        DeterministicAnalysisEngine simply accepts and ignores it - it
        never calls the AI Gateway in the first place)."""
        raise NotImplementedError
