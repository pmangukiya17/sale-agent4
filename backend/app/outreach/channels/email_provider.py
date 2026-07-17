"""
EmailChannelProvider: the ONLY ChannelProvider implementation in M4, per
the same explicit "deterministic stub only, no real model calls yet"
convention as M2's/M3's engines. Renders an OutreachPlaybook's blocks into
an email {subject, body}, respecting each block's behavior (FIXED content
copied verbatim, AI_ASSISTED lightly personalized, AI_GENERATED written
from ai_guidance + the buyer's PersonalizationSnapshot context) - never
inventing facts beyond what personalization_variables/strategies provide.

This exists to prove the schema/pipeline/evidence machinery end to end for
outreach, not to be good sales copy. Swapping this out later for a real
LLM-backed provider requires only a new class honoring the same
ChannelRenderOutcome/RenderedBlockDraft/OutreachEvidenceDraft shapes.
"""
import re

from app.models.enums import OutreachBlockBehavior, PersonalizationStrategyRank
from app.outreach.channels.base import (
    ChannelProvider,
    ChannelRenderOutcome,
    OutreachEvidenceDraft,
    RenderedBlockDraft,
)
from app.outreach.context import OutreachContext

MODEL_USED = "deterministic-email-render-stub"
PROMPT_VERSION_MARKER = "v1"

_VARIABLE_PATTERN = re.compile(r"\{\{(\w+)\}\}")
# Recommendation titles from M2's deterministic stub follow a fixed,
# predictable shape - `Consider pitching '{product.name}'` (see
# app/research/analysis/deterministic_stub.py::_sales_intelligence) - so a
# product phrase can be extracted deterministically via the quoted
# substring, with no new field, no new model, no LLM call.
_QUOTED_PHRASE_PATTERN = re.compile(r"'([^']+)'")


def _substitute(text: str | None, variables: dict) -> str:
    if not text:
        return ""

    def _replace(match: re.Match) -> str:
        key = match.group(1)
        value = variables.get(key)
        return str(value) if value else ""

    return _VARIABLE_PATTERN.sub(_replace, text)


def _flatten_variables(context: OutreachContext) -> dict:
    """
    Four identities exist in every outreach email, and this is the one
    place they get resolved - never conflate them:
      - business ({{company}})          the SELLER - always company_profile.name.
      - recipient ({{buyer}})           the PERSON being addressed - always
                                          the ProspectContact's own name.
      - prospect_company ({{prospect_company}})
                                          the BUYER'S COMPANY - always the
                                          Prospect's own name, distinct from
                                          the recipient's personal name.

    M3's personalization_variables["buyer"] holds the *account-level* buyer
    concept (historically the Prospect's name, since M3 predates per-contact
    addressing) - it is deliberately NOT read for the recipient slot here,
    since that was the exact source of "Hello {{buyer}}," rendering a
    company name instead of a person's name. M4 always has a real
    ProspectContact (outreach is addressed per-contact by design - see
    OutreachRequest's docstring), so that row is the sole source of truth
    for who this email is actually addressed to.

    There is currently no separate "sender person" identity modeled
    anywhere (no CompanyProfile contact-person field, no triggered_by_user
    on OutreachContext) - signatures deterministically sign as the business
    itself ({{company}}), which is correct given the data that actually
    exists rather than fabricating a human sender the schema doesn't track.
    """
    snapshot = context.personalization_snapshot
    pv = (snapshot.personalization_variables or {}) if snapshot else {}
    strategies = pv.get("strategies", {})
    primary = strategies.get("primary", {}) if isinstance(strategies, dict) else {}

    return {
        "company": context.company_profile.name,
        "prospect_company": context.prospect.name,
        "industry": pv.get("industry") or context.prospect.industry_raw,
        "country": pv.get("country") or context.prospect.country,
        "buyer": context.prospect_contact.name or "there",
        "position": pv.get("position") or context.prospect_contact.role,
        "signal": primary.get("signal"),
        "pain_point": primary.get("pain_point"),
        "recommendation": primary.get("recommendation"),
        "cta": primary.get("cta"),
        "buyer_readiness": pv.get("buyer_readiness"),
    }


def _primary_strategy(context: OutreachContext):
    for strategy in context.strategies:
        if strategy.strategy_rank == PersonalizationStrategyRank.PRIMARY:
            return strategy
    return context.strategies[0] if context.strategies else None


def _fallback_strategy(context: OutreachContext):
    for strategy in context.strategies:
        if strategy.strategy_rank == PersonalizationStrategyRank.FALLBACK:
            return strategy
    return None


def _strategy_evidence_drafts(strategy, block_key: str) -> list[OutreachEvidenceDraft]:
    if strategy is None:
        return []
    drafts = [
        OutreachEvidenceDraft(
            block_key=block_key,
            personalization_strategy_id=strategy.id,
            excerpt=strategy.title,
            confidence_score=strategy.confidence,
        )
    ]
    for ev in strategy.evidence:
        drafts.append(
            OutreachEvidenceDraft(
                block_key=block_key,
                signal_id=ev.signal_id,
                recommendation_id=ev.recommendation_id,
                intelligence_snapshot_id=ev.intelligence_snapshot_id,
                excerpt=ev.excerpt,
                confidence_score=strategy.confidence,
            )
        )
    return drafts


class EmailChannelProvider(ChannelProvider):
    key = "email"

    def render(self, context: OutreachContext) -> ChannelRenderOutcome:
        variables = _flatten_variables(context)
        primary = _primary_strategy(context)
        fallback = _fallback_strategy(context)

        blocks: list[RenderedBlockDraft] = []
        evidence: list[OutreachEvidenceDraft] = []

        applicable_blocks = [
            b
            for b in context.outreach_playbook.blocks
            if not b.applicable_channels or self.key in b.applicable_channels
        ]

        for block in applicable_blocks:
            rendered, reasoning, block_evidence = self._render_block(block, variables, primary, fallback, context)
            blocks.append(
                RenderedBlockDraft(
                    block_key=block.block_key,
                    behavior=block.behavior.value,
                    content=rendered,
                    reasoning=reasoning,
                )
            )
            evidence.extend(block_evidence)

        subject = self._render_subject(variables)
        body = "\n\n".join(b.content for b in blocks if b.content)

        # Business Branding: the signature is appended as a THIRD, SEPARATE
        # key in `assembled` - never concatenated into `body`. This keeps
        # presentation cleaner (frontend renders "Body" then "Signature" as
        # two distinct blocks), makes future rendering easier, and lets
        # future channels ignore signature_html entirely without parsing or
        # modifying body. Omitted altogether (not even as an empty string)
        # when the business has no active signature configured, so the key's
        # mere presence is itself meaningful.
        assembled: dict[str, str] = {"subject": subject, "body": body}
        signature = context.business_email_signature
        if signature is not None and signature.is_active and signature.signature_html:
            assembled["signature_html"] = signature.signature_html

        overall_reasoning = (
            f"Rendered {len(blocks)} block(s) from playbook '{context.outreach_playbook.name}' "
            f"v{context.outreach_playbook.version}. Primary strategy used: "
            f"{primary.title if primary else 'none (no strategies available)'}."
        )
        confidence = primary.confidence if primary else 0.2

        rendered_prompt = (
            f"{context.prompt_version.prompt_text}\n\n"
            f"--- Playbook: {context.outreach_playbook.name} (v{context.outreach_playbook.version}) ---\n"
            f"--- Variables: {variables} ---"
        )

        return ChannelRenderOutcome(
            model_used=MODEL_USED,
            prompt_version_marker=PROMPT_VERSION_MARKER,
            rendered_prompt=rendered_prompt,
            blocks=blocks,
            assembled=assembled,
            reasoning=overall_reasoning,
            confidence=confidence,
            evidence=evidence,
        )

    def _render_subject(self, variables: dict) -> str:
        """
        Deterministic B2B subject generation - no randomness, no LLM,
        entirely a priority-ordered composition over variables already
        available in this render (never a person's name; the recipient is
        addressed in the greeting, not the subject line - matching normal
        B2B email convention). Priority: product + prospect's company is
        the sharpest, most specific line available; falls back through
        progressively more generic-but-still-real combinations, ending on
        a safe generic partnership line when nothing else is known.
        """
        business = variables.get("company") or "Us"
        prospect_company = variables.get("prospect_company")
        product_phrase = self._extract_product_phrase(variables.get("recommendation"))
        country = variables.get("country")

        if product_phrase and prospect_company:
            subject = f"{product_phrase} for {prospect_company}"
        elif product_phrase:
            subject = f"{product_phrase} - {business}"
        elif prospect_company:
            subject = f"{business} <> {prospect_company}: Partnership Opportunity"
        elif country:
            subject = f"{business}: Manufacturing Partner from {country}"
        else:
            subject = "Manufacturing Partnership Opportunity"

        return subject[:120]

    def _extract_product_phrase(self, recommendation: str | None) -> str | None:
        if not recommendation:
            return None
        match = _QUOTED_PHRASE_PATTERN.search(recommendation)
        if not match:
            return None
        return f"{match.group(1)} Supply"

    def _render_block(self, block, variables: dict, primary, fallback, context: OutreachContext):
        if block.behavior == OutreachBlockBehavior.FIXED:
            return _substitute(block.fixed_content, variables), None, []

        if block.behavior == OutreachBlockBehavior.AI_ASSISTED:
            base = _substitute(block.fixed_content, variables)
            industry = variables.get("industry")
            if industry:
                base = f"{base} We work with several {industry} exporters facing similar sourcing needs."
                reasoning = "Lightly personalized fixed content using {{industry}}."
            else:
                reasoning = "No industry available to personalize with - used fixed content as-is."
            return base, reasoning, []

        # AI_GENERATED - behavior varies by block_key, always evidence-anchored
        # to the primary strategy when one exists (never invents facts).
        if block.block_key == "opening_paragraph":
            if primary and variables.get("signal"):
                # The signal was observed at the PROSPECT's company, never
                # at our own - {{company}} here would have been the seller,
                # which is exactly the sender/prospect-company confusion
                # this render logic must never produce.
                content = f"I noticed {variables['signal']} at {variables.get('prospect_company') or 'your organization'} - that stood out to us."
                reasoning = f"Anchored to primary strategy's evidenced signal ({variables['signal']})."
            elif primary:
                content = f"{primary.narrative}"
                reasoning = "No specific signal available - used the primary strategy's narrative directly."
            else:
                content = "I wanted to reach out and introduce our work in your industry."
                reasoning = "No strategies available - generic, discovery-oriented opening."
            return content, reasoning, _strategy_evidence_drafts(primary, block.block_key)

        if block.block_key == "prospect_relevance":
            pain_point = variables.get("pain_point")
            if pain_point:
                content = f"Based on what we've seen, this often connects to {pain_point} - something we help address directly."
                reasoning = f"Connected the opening signal to the primary strategy's pain_point slot ({pain_point})."
                return content, reasoning, _strategy_evidence_drafts(primary, block.block_key)
            return "", "No pain_point slot available for this strategy - block omitted.", []

        if block.block_key == "cta":
            cta = variables.get("cta")
            if cta:
                content = f"Would it make sense to {cta}?"
                reasoning = f"Used the primary strategy's assigned CTA slot ({cta})."
                return content, reasoning, _strategy_evidence_drafts(primary, block.block_key)
            if fallback:
                content = fallback.narrative
                reasoning = "No primary CTA slot available - used the fallback strategy's narrative instead."
                return content, reasoning, _strategy_evidence_drafts(fallback, block.block_key)
            content = "Would you be open to a short introductory call?"
            reasoning = "No strategies available - generic, low-commitment CTA."
            return content, reasoning, []

        if block.block_key == "closing_sentence":
            comm = context.communication_strategy
            if comm is not None:
                content = "Looking forward to hearing from you." if comm.warmth.value == "high" else "Please let me know your thoughts."
                reasoning = f"Tone selected from communication_strategy.warmth={comm.warmth.value}."
            else:
                content = "Thank you for your time."
                reasoning = "No communication strategy available - neutral default closing."
            return content, reasoning, []

        # Unknown AI_GENERATED block_key - fail safe rather than fabricate.
        return "", f"No rendering rule defined for AI_GENERATED block '{block.block_key}'.", []
