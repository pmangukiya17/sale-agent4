"""
DeterministicAnalysisEngine: the ONLY AIAnalysisEngine implementation in
M2, per explicit instruction. Rule-based keyword/pattern extraction over
RawDocument.extracted_text - no network calls, no model weights, fully
reproducible. model_used is a literal marker string (not a real model
name) so a future real engine is unambiguously distinguishable in stored
AIAnalysis rows.

This is intentionally simple: a handful of keyword lists and substring
matches. It exists to prove the schema/pipeline/evidence machinery end
to end, not to be a good NLP system. Swapping this out later for a real
LLM-backed engine requires only a new class honoring the same
structured_output contract (see analysis/base.py) - no other change.
"""
import re
from datetime import datetime, timezone

from app.models.enums import AIAnalysisType
from app.models.raw_document import RawDocument
from app.research.analysis.base import AIAnalysisEngine, AnalysisOutcome
from app.research.context import ResearchContext

MODEL_USED = "deterministic-keyword-stub"
PROMPT_VERSION = "v1"

CERTIFICATION_KEYWORDS = [
    "ISO 9001", "ISO 14001", "OEKO-TEX", "OEKO TEX", "GOTS", "BSCI", "SEDEX",
    "WRAP", "GRS", "SA8000", "Fair Trade", "ISO 45001",
]

BUSINESS_MODEL_KEYWORDS = {
    "manufacturer": ["manufacturer", "factory", "production facility", "mill"],
    "trading_company": ["trading company", "export house", "sourcing agent", "trader"],
    "exporter": ["exporter", "export company"],
}

SUSTAINABILITY_KEYWORDS = ["sustainable", "recycled", "organic cotton", "carbon neutral", "eco-friendly"]

IMPORT_EXPORT_KEYWORDS = ["importer", "importing", "exporter", "exporting", "fob", "cif", "customs"]

PROCUREMENT_KEYWORDS = ["procurement team", "sourcing office", "buying office", "merchandising team", "central buying"]

# signal_type -> (keywords, importance, urgency)
SIGNAL_KEYWORDS: dict[str, tuple[list[str], str, str]] = {
    "hiring": (["hiring", "we're hiring", "job opening", "recruiting"], "medium", "medium"),
    "expansion": (["new facility", "expanding", "expansion", "new factory", "opening a new"], "high", "medium"),
    "trade_fair_participation": (["trade fair", "exhibiting at", "booth at", "trade show"], "medium", "low"),
    "investment": (["investment", "funding round", "raised capital", "invested in"], "high", "medium"),
    "leadership_change": (["new ceo", "appointed as", "new head of", "joins as"], "medium", "high"),
}


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _lower_texts(raw_documents: list[RawDocument]) -> list[str]:
    return [(doc.extracted_text or "").lower() for doc in raw_documents]


def _find_matches(keyword: str, texts: list[str]) -> list[int]:
    needle = keyword.lower()
    return [i for i, text in enumerate(texts) if needle in text]


class DeterministicAnalysisEngine(AIAnalysisEngine):
    def analyze(
        self,
        context: ResearchContext,
        raw_documents: list[RawDocument],
        *,
        premium_approved: bool = False,
        company_profile_id: str | None = None,
        user_id: str | None = None,
    ) -> list[AnalysisOutcome]:
        # M11 (AI Provider Hierarchy): premium_approved/company_profile_id/
        # user_id are all accepted (for signature compatibility with the
        # abstract base) and intentionally ignored - this engine never
        # calls the AI Gateway, so there is no provider tier to approve
        # and no request to attach logging context to.
        del premium_approved, company_profile_id, user_id
        texts = _lower_texts(raw_documents)
        all_indices = list(range(len(raw_documents)))

        outcomes: list[AnalysisOutcome] = []
        outcomes.append(self._company_profile(texts, all_indices))
        outcomes.append(self._buyer_profile(texts, all_indices))
        outcomes.append(self._business_signals(texts, all_indices))
        outcomes.append(self._sales_intelligence(context, texts, all_indices))
        return outcomes

    def _company_profile(self, texts: list[str], all_indices: list[int]) -> AnalysisOutcome:
        found_certs = [c for c in CERTIFICATION_KEYWORDS if _find_matches(c, texts)]
        business_model = None
        for model_name, keywords in BUSINESS_MODEL_KEYWORDS.items():
            if any(_find_matches(k, texts) for k in keywords):
                business_model = model_name
                break
        sustainability_hits = [k for k in SUSTAINABILITY_KEYWORDS if _find_matches(k, texts)]
        import_export_hits = [k for k in IMPORT_EXPORT_KEYWORDS if _find_matches(k, texts)]

        structured_output = {
            "business_model": business_model,
            "products_offered": [],
            "markets_served": [],
            "certifications": found_certs,
            "manufacturing_or_trading": business_model,
            "sustainability_notes": (
                f"Mentions of: {', '.join(sustainability_hits)}." if sustainability_hits else None
            ),
            "import_export_activity": import_export_hits,
        }
        has_any_signal = bool(found_certs or business_model or sustainability_hits or import_export_hits)
        return AnalysisOutcome(
            analysis_type=AIAnalysisType.COMPANY_PROFILE,
            model_used=MODEL_USED,
            prompt_version=PROMPT_VERSION,
            structured_output=structured_output,
            confidence=0.4 if has_any_signal else 0.0,
            reasoning="Keyword-matched against a fixed certification/business-model/sustainability vocabulary."
            if has_any_signal else "No recognized keywords found in the supplied documents.",
            source_document_indices=all_indices,
        )

    def _buyer_profile(self, texts: list[str], all_indices: list[int]) -> AnalysisOutcome:
        procurement_hits = [k for k in PROCUREMENT_KEYWORDS if _find_matches(k, texts)]
        structured_output = {
            "buyer_notes": f"Mentions of: {', '.join(procurement_hits)}." if procurement_hits else None,
            "procurement_structure": procurement_hits[0] if procurement_hits else None,
            "purchasing_process": None,
        }
        return AnalysisOutcome(
            analysis_type=AIAnalysisType.BUYER_PROFILE,
            model_used=MODEL_USED,
            prompt_version=PROMPT_VERSION,
            structured_output=structured_output,
            confidence=0.3 if procurement_hits else 0.0,
            reasoning="Keyword-matched against a fixed procurement-structure vocabulary."
            if procurement_hits else "No recognized procurement keywords found.",
            source_document_indices=all_indices,
        )

    def _business_signals(self, texts: list[str], all_indices: list[int]) -> AnalysisOutcome:
        signals = []
        for signal_type, (keywords, importance, urgency) in SIGNAL_KEYWORDS.items():
            matched_indices: list[int] = []
            matched_keyword = None
            for keyword in keywords:
                hits = _find_matches(keyword, texts)
                if hits:
                    matched_indices = sorted(set(matched_indices) | set(hits))
                    matched_keyword = matched_keyword or keyword
            if matched_indices:
                signals.append({
                    "signal_type": signal_type,
                    "title": f"Possible {signal_type.replace('_', ' ')} detected",
                    "description": f"Document text matched keyword '{matched_keyword}'.",
                    "importance": importance,
                    "urgency": urgency,
                    "confidence": 0.35,
                    "reasoning": f"Keyword '{matched_keyword}' matched for signal_type '{signal_type}'.",
                    "evidence_document_indices": matched_indices,
                })

        structured_output = {
            "signals": signals,
            "signals_summary": (
                f"{len(signals)} candidate signal(s) detected: " + ", ".join(s["signal_type"] for s in signals)
            ) if signals else "No candidate business signals detected in the supplied documents.",
        }
        return AnalysisOutcome(
            analysis_type=AIAnalysisType.BUSINESS_SIGNALS,
            model_used=MODEL_USED,
            prompt_version=PROMPT_VERSION,
            structured_output=structured_output,
            confidence=0.35 if signals else 0.0,
            reasoning=f"Matched {len(signals)} of {len(SIGNAL_KEYWORDS)} known signal keyword groups."
            if signals else "No known signal keyword groups matched.",
            source_document_indices=all_indices,
        )

    def _sales_intelligence(self, context: ResearchContext, texts: list[str], all_indices: list[int]) -> AnalysisOutcome:
        recommendations = []
        for product in context.products:
            candidate_keywords = [
                kw for kw in ((product.keywords or []) + (product.applications or [])) if isinstance(kw, str)
            ]
            matched_indices: list[int] = []
            matched_keywords: list[str] = []
            for kw in candidate_keywords:
                hits = _find_matches(kw, texts)
                if hits:
                    matched_indices = sorted(set(matched_indices) | set(hits))
                    matched_keywords.append(kw)
            if matched_keywords:
                recommendations.append({
                    "recommendation_type": "product_fit",
                    "title": f"Consider pitching '{product.name}'",
                    "rationale": f"Prospect documents mention: {', '.join(matched_keywords)}.",
                    "product_id": str(product.id),
                    "confidence": 0.3,
                    "reasoning": f"Keyword overlap between product.keywords/applications and prospect documents: {matched_keywords}.",
                    "evidence_document_indices": matched_indices,
                })

        structured_output = {"recommendations": recommendations}
        return AnalysisOutcome(
            analysis_type=AIAnalysisType.SALES_INTELLIGENCE,
            model_used=MODEL_USED,
            prompt_version=PROMPT_VERSION,
            structured_output=structured_output,
            confidence=0.3 if recommendations else 0.0,
            reasoning=f"Found keyword overlap for {len(recommendations)} of {len(context.products)} active product(s)."
            if recommendations else "No product keyword/application overlap found in the supplied documents.",
            source_document_indices=all_indices,
        )
