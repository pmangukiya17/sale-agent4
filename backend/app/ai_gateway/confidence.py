"""
Confidence evaluation - M9 (AI Provider Hierarchy). Produces the human-
readable "why does this task want a stronger model" reasons shown in the
premium-approval prompt (the spec's own "Reason: - Large document -
Advanced reasoning required - Multiple data sources" example) - and a
0-1 score, higher meaning "local/free is probably enough."

Deliberately a small set of legible if/then heuristics, NOT a trained/
learned model - disclosed explicitly per the AI Provider Hierarchy design
doc (Section 4.4): a real learned confidence system needs measured
cross-provider quality data this project doesn't have yet (that's the
prior AI-layer review's own Migration Plan v2 Phase 3 - the cross-provider
evaluation harness - which this module is deliberately scoped to leave for
later, not attempt to fake now). Pure module - no `settings` import, no
sqlalchemy - fully testable without the sandbox's disclosed
pydantic_settings/sqlalchemy limitation.
"""
from dataclasses import dataclass, field

from app.ai_gateway.request import ResponseFormat, ResponseFormatType

# Thresholds are intentionally simple, named constants - not tuned against
# real data yet (there is none). Revisit once Migration Plan v2's Phase 3
# evaluation harness produces real per-capability quality signal.
_LARGE_CONTEXT_CHAR_THRESHOLD = 12_000
_MULTI_DOCUMENT_THRESHOLD = 3


@dataclass(frozen=True)
class ConfidenceAssessment:
    score: float  # 0.0-1.0, higher = more confident local/free suffices
    reasons: list[str] = field(default_factory=list)


def assess_complexity(
    *,
    context_char_length: int = 0,
    document_count: int = 0,
    response_format: ResponseFormat | None = None,
    reasoning_depth_hint: str = "shallow",
) -> ConfidenceAssessment:
    """`reasoning_depth_hint` is caller-supplied ("shallow"|"deep") since
    this module has no way to measure reasoning depth itself from a
    GatewayRequest alone - an Agent/engine that knows its own task is
    inherently multi-step/judgment-heavy (vs. simple extraction) should
    pass "deep" explicitly. Defaults to "shallow" - the conservative-for-
    escalation direction is the CALLER's to request, not this function's
    to assume."""
    reasons: list[str] = []
    score = 1.0

    if context_char_length > _LARGE_CONTEXT_CHAR_THRESHOLD:
        reasons.append("Large document")
        score -= 0.3

    if document_count >= _MULTI_DOCUMENT_THRESHOLD:
        reasons.append("Multiple data sources")
        score -= 0.2

    if response_format is not None and response_format.type == ResponseFormatType.JSON and response_format.json_schema:
        reasons.append("Structured output required")
        score -= 0.15

    if reasoning_depth_hint == "deep":
        reasons.append("Advanced reasoning required")
        score -= 0.3

    score = max(0.0, min(1.0, score))
    return ConfidenceAssessment(score=score, reasons=reasons)
