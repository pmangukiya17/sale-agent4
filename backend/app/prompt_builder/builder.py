"""
PromptBuilder - M7.2. The only place a PromptContext + ExecutionPolicy
become a GatewayRequest. Everything provider-shaped (model/temperature/
max_tokens/timeout_seconds/response_format/budget_usd) is copied through
from the ExecutionPolicy unchanged - this module never invents or
defaults any of those values itself (see policy.py's own docstring for
why `None` there means "let the provider layer decide", not "let
PromptBuilder decide").

Rendering convention for PromptContext.business_context (v1, deliberately
simple): each key becomes a labeled section in the system message, in
insertion order. A string value is inserted verbatim; anything else
(dict/list/etc.) is rendered via json.dumps for a stable, structured
representation. This is a generic, provider-agnostic convention, not a
per-agent one - an Agent contributing business_context={"company_profile":
{...}, "icp": {...}} does not need to know or care how PromptBuilder
turns that into text; if a future agent needs materially different
rendering (e.g. RAG results formatted as numbered citations), that's a
real, scoped future extension to this function, not a redesign of
PromptContext itself.
"""
import json

from app.ai_gateway.request import GatewayRequest
from app.prompt_builder.base import PromptContext
from app.prompt_builder.policy import ExecutionPolicy


def _render_business_context(business_context: dict) -> str:
    sections = []
    for key, value in business_context.items():
        rendered = value if isinstance(value, str) else json.dumps(value, default=str)
        sections.append(f"### {key}\n{rendered}")
    return "\n\n".join(sections)


class PromptBuilder:
    @staticmethod
    def build(context: PromptContext, policy: ExecutionPolicy) -> GatewayRequest:
        system_parts = []
        if context.system_instructions:
            system_parts.append(context.system_instructions)
        if context.business_context:
            system_parts.append(_render_business_context(context.business_context))

        messages: list[dict] = []
        if system_parts:
            messages.append({"role": "system", "content": "\n\n".join(system_parts)})
        if context.user_instructions:
            messages.append({"role": "user", "content": context.user_instructions})

        return GatewayRequest(
            capability=policy.provider_capability,
            messages=messages,
            model=policy.model,
            temperature=policy.temperature,
            max_tokens=policy.max_tokens,
            timeout_seconds=policy.timeout_seconds,
            response_format=policy.response_format,
            budget_usd=policy.budget_usd,
        )
