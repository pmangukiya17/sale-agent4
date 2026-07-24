"""
llm_mapping.py — M2 Phase 3. Pure, stdlib-only helpers shared between
ResearchAnalysisAgent (app/ai_agents/research_analysis_agent.py, which
must stay importable without sqlalchemy) and LLMAnalysisEngine
(app/research/analysis/llm_engine.py, which already requires sqlalchemy
via ResearchContext/RawDocument/AnalysisOutcome - same as
DeterministicAnalysisEngine does today). Splitting the parsing/
validation/extraction logic out here means it is genuinely unit-testable
in any environment, with or without sqlalchemy installed - mirrors the
Phase 2 app.discovery.providers.brave_search_mapping precedent exactly
(pure candidate-extraction module, separate from the ORM-touching
caller).

Expected model response shape - ONE JSON object with four top-level
keys, produced by a SINGLE combined agent call (not four separate
AIAnalysisType-specific calls - see ResearchAnalysisAgent's own
docstring for why):

{
  "company_profile": {"structured_output": {...per
      app/research/analysis/base.py's own COMPANY_PROFILE contract...},
      "confidence": float, "reasoning": str},
  "buyer_profile": {"structured_output": {...BUYER_PROFILE contract...},
      "confidence": float, "reasoning": str},
  "business_signals": {"structured_output":
      {"signals": [...], "signals_summary": str},
      "confidence": float, "reasoning": str},
  "sales_intelligence": {"structured_output": {"recommendations": [...]},
      "confidence": float, "reasoning": str}
}

Per-signal/per-recommendation confidence/reasoning/evidence_document_indices
live INSIDE each list item, exactly as base.py's own contract documents.
The section-level confidence/reasoning above is a separate, outcome-level
pair (mirrors AnalysisOutcome.confidence/reasoning, which is likewise
kept separate from structured_output's own contents in
DeterministicAnalysisEngine).
"""
import copy
import json
from typing import Any

REQUIRED_SECTIONS = ("company_profile", "buyer_profile", "business_signals", "sales_intelligence")

_EMPTY_STRUCTURED_OUTPUT: dict[str, dict[str, Any]] = {
    "company_profile": {
        "business_model": None,
        "products_offered": [],
        "markets_served": [],
        "certifications": [],
        "manufacturing_or_trading": None,
        "sustainability_notes": None,
        "import_export_activity": [],
    },
    "buyer_profile": {"buyer_notes": None, "procurement_structure": None, "purchasing_process": None},
    "business_signals": {"signals": [], "signals_summary": "No AI analysis available."},
    "sales_intelligence": {"recommendations": []},
}


def parse_agent_response_content(content: Any) -> dict:
    """`content` is GatewayResponse.content (str | dict). Returns a plain
    dict or raises ValueError - never anything else, so callers can treat
    ValueError uniformly as "malformed response, worth a retry."."""
    if isinstance(content, dict):
        return content
    if isinstance(content, str):
        try:
            parsed = json.loads(content)
        except json.JSONDecodeError as exc:
            raise ValueError(f"response content is not valid JSON: {exc}") from exc
        if not isinstance(parsed, dict):
            raise ValueError("response content did not decode to a JSON object")
        return parsed
    raise ValueError(f"unexpected response content type: {type(content).__name__}")


def validate_sections(parsed: dict) -> None:
    """Raises ValueError describing exactly what's missing/malformed -
    never silently accepts a partial response. Both parse_agent_response_content
    and validate_sections are called from ResearchAnalysisAgent.interpret();
    either raising ValueError there is mapped to AgentOutcome.RETRY."""
    missing = [key for key in REQUIRED_SECTIONS if key not in parsed]
    if missing:
        raise ValueError(f"response is missing required section(s): {missing}")
    for key in REQUIRED_SECTIONS:
        section = parsed[key]
        if not isinstance(section, dict) or "structured_output" not in section:
            raise ValueError(f"section '{key}' is missing its 'structured_output' object")
        if not isinstance(section["structured_output"], dict):
            raise ValueError(f"section '{key}'.structured_output must be a JSON object")


def extract_section(parsed: dict, section_key: str, *, raw_document_count: int) -> tuple[dict, float | None, str | None]:
    """Returns (structured_output, confidence, reasoning) for one section.
    Defensively bounds any evidence_document_indices against
    raw_document_count so a hallucinated out-of-range index never reaches
    the pipeline (which resolves indices into real RawDocument rows and
    would otherwise IndexError)."""
    section = parsed.get(section_key) or {}
    structured_output = section.get("structured_output") or copy.deepcopy(_EMPTY_STRUCTURED_OUTPUT[section_key])
    confidence = section.get("confidence")
    reasoning = section.get("reasoning")

    if section_key == "business_signals":
        for signal in structured_output.get("signals") or []:
            if isinstance(signal, dict):
                signal["evidence_document_indices"] = _bounded_indices(
                    signal.get("evidence_document_indices"), raw_document_count
                )
    if section_key == "sales_intelligence":
        for rec in structured_output.get("recommendations") or []:
            if isinstance(rec, dict):
                rec["evidence_document_indices"] = _bounded_indices(
                    rec.get("evidence_document_indices"), raw_document_count
                )
    return structured_output, confidence, reasoning


def _bounded_indices(indices: Any, raw_document_count: int) -> list[int]:
    if not isinstance(indices, list):
        return []
    return sorted({i for i in indices if isinstance(i, int) and 0 <= i < raw_document_count})


def degraded_structured_output(section_key: str) -> dict:
    """Used when the whole agent call failed (GatewayError, or
    AgentRuntime exhausted its bounded retries) - an empty-but-contract-
    shaped structured_output, never a missing key, so every downstream
    reader (IntelligenceSnapshot construction, API schemas) sees the exact
    same shape it always does regardless of which engine ran. A deep
    copy - not a shallow dict(...) - because several sections' template
    values are themselves mutable lists (e.g. "signals": []); a shallow
    copy would let two unrelated calls silently share and mutate the same
    list object."""
    return copy.deepcopy(_EMPTY_STRUCTURED_OUTPUT[section_key])
