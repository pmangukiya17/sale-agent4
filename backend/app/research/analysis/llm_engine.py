"""
LLMAnalysisEngine — M2 Phase 3. Second AIAnalysisEngine implementation,
selected via app/research/analysis/registry.py's
RESEARCH_ANALYSIS_ENGINE_BACKEND setting (default stays
"deterministic" - see that module's own docstring). Delegates the
actual analysis to ResearchAnalysisAgent (llm_agent.py), the first
concrete Agent this codebase has shipped, via
AgentRuntime.run_with_metadata() - the same orchestration
(build_context -> PromptBuilder.build -> AIGateway.complete ->
interpret) every future Agent will use.

ORM -> primitives split: analyze() is the one place that touches
ResearchContext/RawDocument (ORM types) - it extracts only plain
dicts/strings/lists before calling AgentRuntime, mirroring
app.discovery.pipeline's own "_build_query_plan_input(context)"
precedent from Phase 2 (touch ORM here, hand primitives to the
pure/agent layer below). llm_mapping.py (imported here and by
llm_agent.py) does the actual JSON-parsing/section-extraction work in a
form that needs no ORM types at all.

Failure handling: if the agent call fails (a GatewayError escaping
AgentRuntime as AgentOutcome.FAILURE, or AgentOutcome.RETRY exhausted)
this does NOT raise - it returns four AnalysisOutcome objects with
confidence=None and reasoning carrying the failure string, exactly
mirroring DeterministicAnalysisEngine's own "nothing found" shape, per
AIAnalysisEngine's own contract ("must not raise for nothing found...
only raise for a genuine engine failure"). A Gateway/Agent failure is
treated as "no AI analysis available this run", not a pipeline-fatal
error - matching the Phase 3 architecture review's own risk analysis
("degrade not crash", mirroring Discovery's per-provider resilience).
"""
from app.ai_agents.base import AgentInput, AgentOutcome
from app.ai_agents.runtime import AgentRuntime
from app.models.enums import AIAnalysisType
from app.models.raw_document import RawDocument
from app.research.analysis.base import AIAnalysisEngine, AnalysisOutcome
from app.research.analysis.llm_agent import PROMPT_VERSION, RESEARCH_ANALYSIS_AGENT_KEY
from app.research.analysis.llm_mapping import degraded_structured_output, extract_section
from app.research.context import ResearchContext

MODEL_USED_FALLBACK = "research-analysis-agent-unresolved"

# M11 (AI Provider Hierarchy). A fixed, greppable prefix so the frontend can
# detect "this run needs premium approval, not a genuine failure" from the
# stored AnalysisOutcome.reasoning string WITHOUT a schema change (no new
# AIAnalysis column this phase - see the AI Provider Hierarchy design doc's
# Section 3.3 for why schema changes are being deliberately minimized this
# pass). A future phase that wants this structured rather than string-
# matched can add a dedicated column then; this is the honest, disclosed
# v1 shortcut, not a hidden one.
PREMIUM_APPROVAL_REASONING_PREFIX = "PREMIUM_APPROVAL_REQUIRED: "

# Ordered so BUSINESS_SIGNALS/SALES_INTELLIGENCE always render after the
# two profile sections - cosmetic only, has no bearing on correctness.
_SECTION_TO_ANALYSIS_TYPE: dict[str, AIAnalysisType] = {
    "company_profile": AIAnalysisType.COMPANY_PROFILE,
    "buyer_profile": AIAnalysisType.BUYER_PROFILE,
    "business_signals": AIAnalysisType.BUSINESS_SIGNALS,
    "sales_intelligence": AIAnalysisType.SALES_INTELLIGENCE,
}


def _build_document_context(raw_documents: list[RawDocument]) -> list[dict]:
    return [
        {
            "index": i,
            "document_type": doc.document_type,
            # Truncated defensively - a single document's extracted_text
            # could be arbitrarily large; discovering that for the first
            # time against a real token/cost budget in production would
            # be the wrong place to find out.
            "extracted_text": (doc.extracted_text or "")[:8000],
        }
        for i, doc in enumerate(raw_documents)
    ]


def _build_agent_context(context: ResearchContext, raw_documents: list[RawDocument]) -> dict:
    """The one ORM -> primitives boundary in this module. Everything
    past this function is plain dicts/strings/lists - see module
    docstring."""
    prospect = context.prospect
    company_profile = context.company_profile
    return {
        "prospect": {
            "name": prospect.name,
            "website": prospect.website,
            "country": prospect.country,
            "industry": prospect.industry_raw,
            "company_size_range": prospect.company_size_range,
            "description": prospect.description,
        },
        "company_profile": {
            "name": company_profile.name,
            "about": company_profile.about,
            "description": company_profile.description,
            "business_type": company_profile.business_type or [],
        },
        "products": [
            {
                "id": str(product.id),
                "name": product.name,
                "keywords": product.keywords or [],
                "applications": product.applications or [],
            }
            for product in context.products
        ],
        "documents": _build_document_context(raw_documents),
    }


class LLMAnalysisEngine(AIAnalysisEngine):
    def analyze(
        self,
        context: ResearchContext,
        raw_documents: list[RawDocument],
        *,
        premium_approved: bool = False,
        company_profile_id: str | None = None,
        user_id: str | None = None,
    ) -> list[AnalysisOutcome]:
        """`premium_approved` (M11, AI Provider Hierarchy) - default False
        preserves this method's exact prior signature/behavior for any
        existing caller that doesn't pass it. Threaded from
        run_research_request()'s own new optional parameter, itself read
        from the /run request body - see pipeline.py and
        app/api/routes/research_requests.py's ai-preflight endpoint for
        where a human actually makes this decision.

        `company_profile_id`/`user_id` (M11) - logging/observability only
        (see GatewayRequest's own docstring for the full "Workspace"/
        "User" logging-field mapping) - both optional, both default None."""
        agent_context = _build_agent_context(context, raw_documents)
        execution_result = AgentRuntime.run_with_metadata(
            RESEARCH_ANALYSIS_AGENT_KEY,
            AgentInput(
                context=agent_context,
                premium_approved=premium_approved,
                company_profile_id=company_profile_id,
                user_id=user_id,
            ),
        )
        model_used = execution_result.model or MODEL_USED_FALLBACK

        if execution_result.premium_approval is not None:
            return self._premium_approval_outcomes(model_used, execution_result.premium_approval)

        if execution_result.output.status != AgentOutcome.SUCCESS:
            return self._degraded_outcomes(model_used, execution_result.output.error)

        parsed = execution_result.output.result or {}
        return self._map_outcomes(parsed, model_used, len(raw_documents))

    def _map_outcomes(self, parsed: dict, model_used: str, raw_document_count: int) -> list[AnalysisOutcome]:
        all_indices = list(range(raw_document_count))
        outcomes = []
        for section_key, analysis_type in _SECTION_TO_ANALYSIS_TYPE.items():
            structured_output, confidence, reasoning = extract_section(
                parsed, section_key, raw_document_count=raw_document_count
            )
            outcomes.append(
                AnalysisOutcome(
                    analysis_type=analysis_type,
                    model_used=model_used,
                    prompt_version=str(PROMPT_VERSION),
                    structured_output=structured_output,
                    confidence=confidence,
                    reasoning=reasoning,
                    raw_model_output=parsed.get(section_key),
                    source_document_indices=all_indices,
                )
            )
        return outcomes

    def _premium_approval_outcomes(self, model_used: str, premium_approval) -> list[AnalysisOutcome]:
        cost = f"${premium_approval.estimated_cost_usd:.4f}" if premium_approval.estimated_cost_usd is not None else "unknown"
        reasons = ", ".join(premium_approval.reasons) if premium_approval.reasons else "no specific reason recorded"
        reasoning = (
            f"{PREMIUM_APPROVAL_REASONING_PREFIX}local/free AI providers were unavailable; "
            f"'{premium_approval.candidate_provider_key}' (premium) would be used next, estimated cost {cost}. "
            f"Reason(s): {reasons}. Re-run this research request with premium approval to proceed."
        )
        return [
            AnalysisOutcome(
                analysis_type=analysis_type,
                model_used=model_used,
                prompt_version=str(PROMPT_VERSION),
                structured_output=degraded_structured_output(section_key),
                confidence=None,
                reasoning=reasoning,
                raw_model_output=None,
                source_document_indices=[],
            )
            for section_key, analysis_type in _SECTION_TO_ANALYSIS_TYPE.items()
        ]

    def _degraded_outcomes(self, model_used: str, error: str | None) -> list[AnalysisOutcome]:
        reasoning = f"AI analysis failed: {error}" if error else "AI analysis failed for an unknown reason."
        return [
            AnalysisOutcome(
                analysis_type=analysis_type,
                model_used=model_used,
                prompt_version=str(PROMPT_VERSION),
                structured_output=degraded_structured_output(section_key),
                confidence=None,
                reasoning=reasoning,
                raw_model_output=None,
                source_document_indices=[],
            )
            for section_key, analysis_type in _SECTION_TO_ANALYSIS_TYPE.items()
        ]
