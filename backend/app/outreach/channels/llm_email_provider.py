"""
LLMEmailChannelProvider - M-AIGW-5 (Outreach as the Gateway's second
production consumer - see
docs/architecture/provider-neutral-ai-gateway-plan.md Section 12). A
second ChannelProvider implementation for the "email" channel_key,
selected instead of EmailChannelProvider via
settings.OUTREACH_EMAIL_CHANNEL_BACKEND (app.outreach.channels.registry) -
default stays "deterministic" (EmailChannelProvider), so this class has
zero effect on any deployment until an operator explicitly opts in.

FIXED vs. AI_ASSISTED/AI_GENERATED split (the one place this provider's
behavior deliberately differs from a naive "send everything to the
model" design): a playbook's FIXED blocks (legal disclaimers,
unsubscribe links, ...) are rendered here exactly the same way
EmailChannelProvider renders them - via _substitute()/_flatten_variables(),
imported and reused, never duplicated, from email_provider.py (same
"share implementation, keep behavior distinct" precedent M-AIGW-3 used
for the Gemini provider split) - and are NEVER sent to the model. Only
AI_ASSISTED/AI_GENERATED blocks are asked of OutreachEmailAgent
(llm_agent.py) via AgentRuntime.run_with_metadata(). This is a real
product-correctness requirement, not just an optimization: a FIXED block
exists specifically so its content is guaranteed verbatim regardless of
which rendering backend is selected.

Degrades, never crashes: on PremiumApprovalRequiredError or a genuine
Gateway failure, this returns a real ChannelRenderOutcome (FIXED blocks
still rendered correctly, AI blocks replaced with an honest low-
confidence placeholder explaining why) rather than raising - identical
contract to ChannelProvider.render()'s own docstring, and the same
"degrade not crash" precedent LLMAnalysisEngine established for
Research.
"""
from app.ai_agents.base import AgentInput, AgentOutcome
from app.ai_agents.runtime import AgentRuntime
from app.models.enums import OutreachBlockBehavior
from app.outreach.channels.base import ChannelProvider, ChannelRenderOutcome, RenderedBlockDraft
from app.outreach.channels.email_provider import (
    EmailChannelProvider,
    _fallback_strategy,
    _flatten_variables,
    _primary_strategy,
    _strategy_evidence_drafts,
    _substitute,
)
from app.outreach.channels.llm_agent import OUTREACH_EMAIL_AGENT_KEY
from app.outreach.channels.llm_mapping import index_blocks_by_key
from app.outreach.context import OutreachContext

MODEL_USED_FALLBACK = "outreach-email-agent-unresolved"
PROMPT_VERSION_MARKER = "v1-llm"

# M-AIGW-5, same fixed/greppable-prefix convention as
# research/analysis/llm_engine.py's own PREMIUM_APPROVAL_REASONING_PREFIX -
# lets a caller detect "this needs premium approval, not a genuine
# failure" from the stored reasoning string without a schema change.
PREMIUM_APPROVAL_REASONING_PREFIX = "PREMIUM_APPROVAL_REQUIRED: "

# Reused so the LLM path's subject-line fallback (when the model omits
# or empties "subject") is the same honest, deterministic composition
# EmailChannelProvider always produces - never a bare hardcoded string.
_DETERMINISTIC_SUBJECT_FALLBACK = EmailChannelProvider()


def _applicable_blocks(context: OutreachContext) -> list:
    return [b for b in context.outreach_playbook.blocks if not b.applicable_channels or "email" in b.applicable_channels]


def _build_agent_context(context: OutreachContext, generative_blocks: list, variables: dict) -> dict:
    """The one ORM -> primitives boundary in this module. Everything
    past this function (llm_agent.py's OutreachEmailAgent) is plain
    dicts/strings/lists - see module docstring."""
    primary = _primary_strategy(context)
    fallback = _fallback_strategy(context)
    comm = context.communication_strategy
    return {
        "variables": variables,
        "primary_strategy": (
            {"title": primary.title, "narrative": primary.narrative, "confidence": primary.confidence} if primary else None
        ),
        "fallback_strategy": ({"title": fallback.title, "narrative": fallback.narrative} if fallback else None),
        "communication_strategy_warmth": comm.warmth.value if comm is not None else None,
        "playbook_name": context.outreach_playbook.name,
        "blocks_to_write": [{"block_key": b.block_key, "behavior": b.behavior.value} for b in generative_blocks],
    }


class LLMEmailChannelProvider(ChannelProvider):
    key = "email"

    def render(
        self,
        context: OutreachContext,
        *,
        premium_approved: bool = False,
        company_profile_id: str | None = None,
        user_id: str | None = None,
    ) -> ChannelRenderOutcome:
        variables = _flatten_variables(context)
        primary = _primary_strategy(context)
        applicable = _applicable_blocks(context)
        fixed_blocks = [b for b in applicable if b.behavior == OutreachBlockBehavior.FIXED]
        generative_blocks = [b for b in applicable if b.behavior != OutreachBlockBehavior.FIXED]

        fixed_rendered: dict[str, str] = {b.block_key: _substitute(b.fixed_content, variables) for b in fixed_blocks}

        if not generative_blocks:
            # Nothing for the model to write (an all-FIXED playbook) -
            # no Gateway call needed at all, same "don't call the model
            # for work it has nothing to do" discipline as everywhere
            # else in this codebase.
            return self._assemble(
                context, applicable, fixed_rendered, {}, variables,
                model_used="deterministic-only-no-generative-blocks",
                confidence=primary.confidence if primary else 0.2,
                overall_reasoning="Playbook has no AI_ASSISTED/AI_GENERATED blocks for this channel - rendered FIXED content only.",
                subject=None,
            )

        agent_context = _build_agent_context(context, generative_blocks, variables)
        execution_result = AgentRuntime.run_with_metadata(
            OUTREACH_EMAIL_AGENT_KEY,
            AgentInput(
                context=agent_context,
                premium_approved=premium_approved,
                company_profile_id=company_profile_id,
                user_id=user_id,
            ),
        )
        model_used = execution_result.model or MODEL_USED_FALLBACK

        if execution_result.premium_approval is not None:
            pa = execution_result.premium_approval
            cost = f"${pa.estimated_cost_usd:.4f}" if pa.estimated_cost_usd is not None else "unknown"
            reasons = ", ".join(pa.reasons) if pa.reasons else "no specific reason recorded"
            reasoning = (
                f"{PREMIUM_APPROVAL_REASONING_PREFIX}local/free AI providers were unavailable; "
                f"'{pa.candidate_provider_key}' (premium) would be used next, estimated cost {cost}. "
                f"Reason(s): {reasons}. Re-run with premium approval to generate AI content for this draft."
            )
            return self._degraded(context, applicable, fixed_rendered, variables, model_used, reasoning)

        if execution_result.output.status != AgentOutcome.SUCCESS:
            reasoning = f"AI email generation failed: {execution_result.output.error or 'unknown error'}"
            return self._degraded(context, applicable, fixed_rendered, variables, model_used, reasoning)

        parsed = execution_result.output.result or {}
        return self._assemble(
            context,
            applicable,
            fixed_rendered,
            index_blocks_by_key(parsed),
            variables,
            model_used=model_used,
            confidence=parsed.get("confidence") if parsed.get("confidence") is not None else (primary.confidence if primary else 0.2),
            overall_reasoning=parsed.get("reasoning")
            or f"Rendered {len(applicable)} block(s) from playbook '{context.outreach_playbook.name}' via {model_used}.",
            subject=parsed.get("subject"),
        )

    def _degraded(self, context, applicable, fixed_rendered, variables, model_used, reasoning) -> ChannelRenderOutcome:
        """Never raises: FIXED blocks still render correctly (they never
        needed the model); AI blocks get an honest, low-confidence
        placeholder explaining why, never fabricated content."""
        return self._assemble(
            context, applicable, fixed_rendered, {}, variables, model_used=model_used, confidence=0.0,
            overall_reasoning=reasoning, subject=None, generated_block_reasoning=reasoning,
        )

    def _assemble(
        self,
        context: OutreachContext,
        applicable: list,
        fixed_rendered: dict[str, str],
        generated_by_key: dict[str, dict],
        variables: dict,
        *,
        model_used: str,
        confidence: float | None,
        overall_reasoning: str,
        subject: str | None,
        generated_block_reasoning: str | None = None,
    ) -> ChannelRenderOutcome:
        blocks: list[RenderedBlockDraft] = []
        primary = _primary_strategy(context)
        evidence = []

        for block in applicable:
            if block.behavior == OutreachBlockBehavior.FIXED:
                blocks.append(
                    RenderedBlockDraft(
                        block_key=block.block_key, behavior=block.behavior.value, content=fixed_rendered.get(block.block_key, "")
                    )
                )
                continue

            generated = generated_by_key.get(block.block_key)
            if generated is not None:
                blocks.append(
                    RenderedBlockDraft(
                        block_key=block.block_key,
                        behavior=block.behavior.value,
                        content=generated.get("content", ""),
                        reasoning=generated.get("reasoning"),
                    )
                )
                evidence.extend(_strategy_evidence_drafts(primary, block.block_key))
            else:
                # Model omitted this block_key, or this is the degraded
                # (premium-approval/failure) path - honest empty content,
                # never fabricated, same "fail safe rather than fabricate"
                # discipline as EmailChannelProvider's own unknown-block
                # handling.
                blocks.append(
                    RenderedBlockDraft(
                        block_key=block.block_key,
                        behavior=block.behavior.value,
                        content="",
                        reasoning=generated_block_reasoning or f"Model did not return content for block '{block.block_key}'.",
                    )
                )

        resolved_subject = subject if subject else _DETERMINISTIC_SUBJECT_FALLBACK._render_subject(variables)
        body = "\n\n".join(b.content for b in blocks if b.content)

        assembled: dict[str, str] = {"subject": resolved_subject, "body": body}
        signature = context.business_email_signature
        if signature is not None and signature.is_active and signature.signature_html:
            assembled["signature_html"] = signature.signature_html

        rendered_prompt = (
            f"[OutreachEmailAgent v{PROMPT_VERSION_MARKER}] playbook={context.outreach_playbook.name} "
            f"v{context.outreach_playbook.version}; variables={variables}"
        )

        return ChannelRenderOutcome(
            model_used=model_used,
            prompt_version_marker=PROMPT_VERSION_MARKER,
            rendered_prompt=rendered_prompt,
            blocks=blocks,
            assembled=assembled,
            reasoning=overall_reasoning,
            confidence=confidence,
            evidence=evidence,
        )
