"""
OutreachEmailAgent - M-AIGW-5 (Outreach as the Gateway's second production
consumer - see docs/architecture/provider-neutral-ai-gateway-plan.md
Section 12). The SECOND concrete Agent this codebase has ever shipped
(app.ai_agents.registry.AGENT_REGISTRY's first real populator was
ResearchAnalysisAgent, M2 Phase 3). Deliberately chosen to differ in
shape from Research's Agent, to prove the Agent/Gateway/PromptBuilder
stack generalizes rather than merely "worked once": this Agent's
response is a variable-length list of per-block content, not a fixed set
of always-present keys.

Deliberately lives here, in app.outreach.channels (the Outreach domain's
own package), NOT inside app.ai_agents - identical reasoning to
research/analysis/llm_agent.py's own docstring (mirrors how concrete
Workflow Actions live in app.workflow_actions rather than
app.workflow_engine.actions itself).

Only asked to write AI_ASSISTED/AI_GENERATED block content - FIXED
blocks (legal disclaimers, unsubscribe links, ...) are never sent to this
Agent at all and are always rendered deterministically by
llm_email_provider.py itself, reusing email_provider.py's own
_substitute()/_flatten_variables() helpers. This Agent's build_context()
therefore only ever receives the subset of blocks it was actually asked
to generate - see llm_email_provider.py's own docstring for the full
FIXED/AI_ASSISTED/AI_GENERATED split rationale.

build_context()/interpret() below are fully sqlalchemy-free (only
app.ai_agents.base / app.ai_gateway.request / app.prompt_builder.base /
app.prompt_builder.policy / app.outreach.channels.llm_mapping - all
stdlib-only or pure dataclasses), mirroring
research/analysis/llm_agent.py's identical "genuinely unit-testable
without a database" precedent exactly. Importing this module (and
therefore registering the Agent + its ExecutionPolicy) does NOT require
sqlalchemy - only llm_email_provider.py, which imports OutreachContext
alongside this module, carries that requirement.

Prompt storage: uses app.ai_agents.prompts.registry's PROMPT_REGISTRY -
the same "extend rather than build new" seam ResearchAnalysisAgent
already populated, now with its second real entry.
"""
from app.ai_agents.base import Agent, AgentInput, AgentOutcome, AgentOutput
from app.ai_agents.execution_policy import EXECUTION_POLICY_REGISTRY, register_execution_policy
from app.ai_agents.registry import is_agent_registered, register_agent
from app.ai_agents.prompts.registry import PromptTemplate, get_prompt_template, register_prompt_template
from app.ai_gateway.request import GatewayResponse, ResponseFormat, ResponseFormatType
from app.outreach.channels.llm_mapping import parse_agent_response_content, validate_email_response
from app.prompt_builder.base import PromptContext
from app.prompt_builder.policy import ExecutionPolicy

OUTREACH_EMAIL_AGENT_KEY = "outreach_email_generation"
PROMPT_VERSION = 1

RESPONSE_JSON_SCHEMA: dict = {
    "type": "object",
    "required": ["subject", "blocks"],
    "properties": {
        "subject": {"type": "string"},
        "blocks": {
            "type": "array",
            "items": {
                "type": "object",
                "required": ["block_key", "content"],
                "properties": {
                    "block_key": {"type": "string"},
                    "content": {"type": "string"},
                    "reasoning": {"type": ["string", "null"]},
                },
            },
        },
        "confidence": {"type": ["number", "null"]},
        "reasoning": {"type": ["string", "null"]},
    },
}

SYSTEM_INSTRUCTIONS = (
    "You are a B2B sales outreach copywriter. You are given context about "
    "a seller (company), a prospect (buyer's company) and buyer contact, "
    "the personalization strategy evidence available for this buyer, and "
    "a list of email blocks you must write content for - each identified "
    "by a block_key and a behavior hint (ai_assisted means lightly "
    "personalize the given base text; ai_generated means write the block "
    "from the provided strategy evidence). Return a single JSON object "
    "with 'subject' (an email subject line), 'blocks' (an array with one "
    "entry per requested block_key, each with 'content' and a short "
    "'reasoning'), and top-level 'confidence' (0.0-1.0) and 'reasoning'. "
    "Only use facts given in the context - never invent a signal, pain "
    "point, product, or fact not present in the supplied evidence. If a "
    "block has no supporting evidence, write brief, honest, generic "
    "content for it rather than fabricating specifics."
)

RESPONSE_FORMAT = ResponseFormat(type=ResponseFormatType.JSON, json_schema=RESPONSE_JSON_SCHEMA)


class OutreachEmailAgent(Agent):
    key = OUTREACH_EMAIL_AGENT_KEY

    def build_context(self, input_data: AgentInput) -> PromptContext:
        """`input_data.context` is the opaque dict LLMEmailChannelProvider
        assembled (variables/strategy/blocks-to-generate primitives only -
        no ORM objects ever reach this method, per Agent's own contract)."""
        template = get_prompt_template(OUTREACH_EMAIL_AGENT_KEY, PROMPT_VERSION)
        return PromptContext(
            system_instructions=template.system_instructions,
            user_instructions=(
                "Write the subject line and the requested block content "
                "described below, returning the JSON object described above."
            ),
            business_context=dict(input_data.context),
        )

    def interpret(self, response: GatewayResponse, input_data: AgentInput) -> AgentOutput:
        try:
            parsed = parse_agent_response_content(response.content)
            validate_email_response(parsed)
        except ValueError as exc:
            # Malformed/incomplete response - AgentRuntime.run() retries
            # (bounded by settings.AGENT_RUNTIME_MAX_ATTEMPTS) with a fresh
            # build_context()/PromptBuilder.build()/gateway.complete() call
            # before giving up and reporting FAILURE.
            return AgentOutput(status=AgentOutcome.RETRY, error=str(exc))
        return AgentOutput(status=AgentOutcome.SUCCESS, result=parsed)


if not is_agent_registered(OUTREACH_EMAIL_AGENT_KEY):
    register_agent(OUTREACH_EMAIL_AGENT_KEY, OutreachEmailAgent())
try:
    get_prompt_template(OUTREACH_EMAIL_AGENT_KEY, PROMPT_VERSION)
except KeyError:
    register_prompt_template(
        PromptTemplate(
            agent_key=OUTREACH_EMAIL_AGENT_KEY,
            version=PROMPT_VERSION,
            system_instructions=SYSTEM_INSTRUCTIONS,
        )
    )
# ExecutionPolicy registration - the one place this Agent's provider
# capability/response_format is decided (never inside the Agent itself,
# per base.py's own build_context()/interpret() split). No entry needs
# adding to app.ai_gateway.router.CAPABILITY_PROVIDER_PREFERENCE: an
# unrecognized capability already falls through to
# CAPABILITY_PROVIDER_PREFERENCE["default"] by design - identical to
# ResearchAnalysisAgent's own "research_analysis" capability key.
if OUTREACH_EMAIL_AGENT_KEY not in EXECUTION_POLICY_REGISTRY:
    register_execution_policy(
        OUTREACH_EMAIL_AGENT_KEY,
        ExecutionPolicy(provider_capability=OUTREACH_EMAIL_AGENT_KEY, response_format=RESPONSE_FORMAT),
    )
