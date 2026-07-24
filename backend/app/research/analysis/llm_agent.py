"""
ResearchAnalysisAgent — M2 Phase 3. The first concrete Agent this
codebase has ever shipped (AGENT_REGISTRY was an empty dict before this
- see app/ai_agents/__init__.py's own scope note, updated alongside this
file). Gives the AI Gateway/Agent Runtime stack (built and stable since
M7.2, never called in production) its first real caller.

Deliberately lives here, in app.research.analysis (the Research domain's
own package), NOT inside app.ai_agents - mirrors exactly how concrete
Workflow Actions live in app.workflow_actions rather than in
app.workflow_engine.actions itself (that package's own registry.py
docstring: "must never import a concrete Agent implementation at module
level"). This module imports the generic infra
(app.ai_agents.base/registry/execution_policy) the same way
research_execution_action.py imports app.workflow_engine.actions.base/
registry - the dependency arrow points from the domain into the generic
infra, never the reverse.

Deliberately a SINGLE combined analysis call, not four separate Agent
invocations (one per AIAnalysisType). One LLM call producing all four
sections costs one API round-trip instead of four, and lets the model
cross-reference across sections the way a human analyst reading the
same documents once would (e.g. a sales_intelligence recommendation
citing a business_signals finding). app/research/analysis/llm_engine.py
is the ORM-touching caller that assembles this Agent's opaque `context`
dict from a ResearchContext + raw_documents, invokes it via
AgentRuntime.run_with_metadata(), and maps its AgentOutput.result back
into a list[AnalysisOutcome] - the exact same return shape
DeterministicAnalysisEngine already produces, so nothing about
run_research_request()'s own pipeline changes (see analysis/base.py's
own docstring: "a real LLM-backed engine can replace [the stub] later...
with zero schema or pipeline change").

build_context()/interpret() below are fully sqlalchemy-free (only
app.ai_agents.base / app.ai_gateway.request / app.prompt_builder.base /
app.prompt_builder.policy / app.research.analysis.llm_mapping - all
stdlib-only or pure dataclasses) - genuinely unit-testable without a
database, mirroring app.discovery.providers.brave_search_mapping's own
"pure logic split from the ORM-touching caller" precedent from Phase 2.
Importing this module (and therefore registering the Agent + its
ExecutionPolicy) does NOT require sqlalchemy - only llm_engine.py, which
imports ResearchContext/RawDocument/AnalysisOutcome alongside this
module, carries that requirement (same as DeterministicAnalysisEngine
already does today).

Prompt storage: uses app.ai_agents.prompts.registry's PROMPT_REGISTRY -
built in M7.2, shipped deliberately empty ("no concrete Agent exists yet
... ready for the first real Agent to populate" - see that module's own
docstring) and never populated until now. This is the correct, existing
"extend rather than build new" seam for exactly this need (a concrete
Agent's own system-instructions text, versioned, revisable without a
code change to this class's logic) - preferred over hardcoding the
prompt as a bare module-level string.
"""
from app.ai_agents.base import Agent, AgentInput, AgentOutcome, AgentOutput
from app.ai_agents.execution_policy import EXECUTION_POLICY_REGISTRY, register_execution_policy
from app.ai_agents.registry import is_agent_registered, register_agent
from app.ai_agents.prompts.registry import PromptTemplate, get_prompt_template, register_prompt_template
from app.ai_gateway.request import GatewayResponse, ResponseFormat, ResponseFormatType
from app.prompt_builder.base import PromptContext
from app.prompt_builder.policy import ExecutionPolicy
from app.research.analysis.llm_mapping import parse_agent_response_content, validate_sections

RESEARCH_ANALYSIS_AGENT_KEY = "research_analysis"
PROMPT_VERSION = 1

# Mirrors app/research/analysis/base.py's own structured_output contract
# verbatim, wrapped one level so each section also carries its own
# outcome-level confidence/reasoning - see llm_mapping.py's own docstring
# for the full expected shape and why.
RESPONSE_JSON_SCHEMA: dict = {
    "type": "object",
    "required": list(("company_profile", "buyer_profile", "business_signals", "sales_intelligence")),
    "properties": {
        "company_profile": {
            "type": "object",
            "required": ["structured_output"],
            "properties": {
                "structured_output": {
                    "type": "object",
                    "properties": {
                        "business_model": {"type": ["string", "null"]},
                        "products_offered": {"type": "array", "items": {"type": "string"}},
                        "markets_served": {"type": "array", "items": {"type": "string"}},
                        "certifications": {"type": "array", "items": {"type": "string"}},
                        "manufacturing_or_trading": {"type": ["string", "null"]},
                        "sustainability_notes": {"type": ["string", "null"]},
                        "import_export_activity": {"type": "array", "items": {"type": "string"}},
                    },
                },
                "confidence": {"type": ["number", "null"]},
                "reasoning": {"type": ["string", "null"]},
            },
        },
        "buyer_profile": {
            "type": "object",
            "required": ["structured_output"],
            "properties": {
                "structured_output": {
                    "type": "object",
                    "properties": {
                        "buyer_notes": {"type": ["string", "null"]},
                        "procurement_structure": {"type": ["string", "null"]},
                        "purchasing_process": {"type": ["string", "null"]},
                    },
                },
                "confidence": {"type": ["number", "null"]},
                "reasoning": {"type": ["string", "null"]},
            },
        },
        "business_signals": {
            "type": "object",
            "required": ["structured_output"],
            "properties": {
                "structured_output": {
                    "type": "object",
                    "properties": {
                        "signals": {
                            "type": "array",
                            "items": {
                                "type": "object",
                                "properties": {
                                    "signal_type": {"type": "string"},
                                    "title": {"type": "string"},
                                    "description": {"type": "string"},
                                    "importance": {"type": "string", "enum": ["low", "medium", "high", "critical"]},
                                    "urgency": {"type": "string", "enum": ["low", "medium", "high", "immediate"]},
                                    "confidence": {"type": "number"},
                                    "reasoning": {"type": "string"},
                                    "evidence_document_indices": {"type": "array", "items": {"type": "integer"}},
                                },
                            },
                        },
                        "signals_summary": {"type": "string"},
                    },
                },
                "confidence": {"type": ["number", "null"]},
                "reasoning": {"type": ["string", "null"]},
            },
        },
        "sales_intelligence": {
            "type": "object",
            "required": ["structured_output"],
            "properties": {
                "structured_output": {
                    "type": "object",
                    "properties": {
                        "recommendations": {
                            "type": "array",
                            "items": {
                                "type": "object",
                                "properties": {
                                    "recommendation_type": {"type": "string"},
                                    "title": {"type": "string"},
                                    "rationale": {"type": "string"},
                                    "product_id": {"type": ["string", "null"]},
                                    "confidence": {"type": "number"},
                                    "reasoning": {"type": "string"},
                                    "evidence_document_indices": {"type": "array", "items": {"type": "integer"}},
                                },
                            },
                        },
                    },
                },
                "confidence": {"type": ["number", "null"]},
                "reasoning": {"type": ["string", "null"]},
            },
        },
    },
}

SYSTEM_INSTRUCTIONS = (
    "You are a B2B sales research analyst. You are given context about a "
    "prospect company, the company profile doing the selling, its "
    "products, and a set of raw research documents about the prospect "
    "(each with an index). Analyze the documents and return a single "
    "JSON object with exactly four top-level keys: company_profile, "
    "buyer_profile, business_signals, sales_intelligence. Each key's "
    "value must have a 'structured_output' object plus 'confidence' "
    "(0.0-1.0) and 'reasoning' (a short explanation of how you reached "
    "that conclusion). Only report what the documents actually support - "
    "use null/empty values and low confidence when the documents don't "
    "say enough, never invent facts. Every signal and recommendation must "
    "include 'evidence_document_indices' pointing at the specific "
    "documents (by index) that support it."
)

RESPONSE_FORMAT = ResponseFormat(type=ResponseFormatType.JSON, json_schema=RESPONSE_JSON_SCHEMA)


class ResearchAnalysisAgent(Agent):
    key = RESEARCH_ANALYSIS_AGENT_KEY

    def build_context(self, input_data: AgentInput) -> PromptContext:
        """`input_data.context` is the opaque dict LLMAnalysisEngine
        assembled (prospect/company/products/documents primitives only -
        no ORM objects ever reach this method, per Agent's own contract)."""
        template = get_prompt_template(RESEARCH_ANALYSIS_AGENT_KEY, PROMPT_VERSION)
        return PromptContext(
            system_instructions=template.system_instructions,
            user_instructions=(
                "Analyze the supplied prospect, company, product, and document "
                "context below and return the JSON object described above."
            ),
            business_context=dict(input_data.context),
        )

    def interpret(self, response: GatewayResponse, input_data: AgentInput) -> AgentOutput:
        try:
            parsed = parse_agent_response_content(response.content)
            validate_sections(parsed)
        except ValueError as exc:
            # Malformed/incomplete response - AgentRuntime.run() retries
            # (bounded by settings.AGENT_RUNTIME_MAX_ATTEMPTS) with a fresh
            # build_context()/PromptBuilder.build()/gateway.complete() call
            # before giving up and reporting FAILURE.
            return AgentOutput(status=AgentOutcome.RETRY, error=str(exc))
        return AgentOutput(status=AgentOutcome.SUCCESS, result=parsed)


if not is_agent_registered(RESEARCH_ANALYSIS_AGENT_KEY):
    register_agent(RESEARCH_ANALYSIS_AGENT_KEY, ResearchAnalysisAgent())
try:
    get_prompt_template(RESEARCH_ANALYSIS_AGENT_KEY, PROMPT_VERSION)
except KeyError:
    register_prompt_template(
        PromptTemplate(
            agent_key=RESEARCH_ANALYSIS_AGENT_KEY,
            version=PROMPT_VERSION,
            system_instructions=SYSTEM_INSTRUCTIONS,
        )
    )
# ExecutionPolicy registration - the one place this Agent's provider
# capability/response_format is decided (never inside the Agent itself,
# per base.py's own build_context()/interpret() split - see that
# module's docstring). No entry needs adding to
# app.ai_gateway.router.ROUTING_POLICY: an unrecognized capability
# already falls through to ROUTING_POLICY["default"] by design.
if RESEARCH_ANALYSIS_AGENT_KEY not in EXECUTION_POLICY_REGISTRY:
    register_execution_policy(
        RESEARCH_ANALYSIS_AGENT_KEY,
        ExecutionPolicy(provider_capability=RESEARCH_ANALYSIS_AGENT_KEY, response_format=RESPONSE_FORMAT),
    )
