"""
DeterministicMailboxBriefEngine: the ONLY MailboxBriefEngine
implementation in this initial slice. Rule-based summary assembly over
already-stored Conversation/Recommendation/Opportunity data - no network
calls, no model weights, fully reproducible. ai_model is a literal
marker string (not a real model name) so a future real engine is
unambiguously distinguishable in stored data, the same convention M2's/
M3's own deterministic stubs already established.

This exists to prove the schema/service/API machinery end to end, not to
be a good copywriter. Swapping this out later for a real LLM-backed
engine (via app.ai_gateway/app.prompt_builder, the same infrastructure
this project's M7.2/M7.3 Agent layer already uses) requires only a new
class honoring the same BriefOutcome/BriefRecommendation shapes - no
other change, per MailboxBriefEngine's own docstring.
"""
from app.mailbox_brief.context import MailboxBriefContext
from app.mailbox_brief.engine.base import BriefOutcome, BriefRecommendation, MailboxBriefEngine
from app.models.enums import OpportunityStage

AI_PROVIDER = "internal"
AI_MODEL = "deterministic-brief-stub-v1"

_CLOSED_STAGES = {OpportunityStage.CLOSED_WON.value, OpportunityStage.CLOSED_LOST.value}


class DeterministicMailboxBriefEngine(MailboxBriefEngine):
    def synthesize(self, context: MailboxBriefContext) -> BriefOutcome:
        open_opportunity_count = sum(row["count"] for row in context.funnel if row["stage"] not in _CLOSED_STAGES)
        closed_won_count = next(
            (row["count"] for row in context.funnel if row["stage"] == OpportunityStage.CLOSED_WON.value), 0
        )
        closed_lost_count = next(
            (row["count"] for row in context.funnel if row["stage"] == OpportunityStage.CLOSED_LOST.value), 0
        )
        needs_review_count = len(context.needs_review_conversations)

        summary = self._summary(
            context,
            open_opportunity_count=open_opportunity_count,
            closed_won_count=closed_won_count,
            closed_lost_count=closed_lost_count,
            needs_review_count=needs_review_count,
        )
        recommendations = self._recommendations(context, needs_review_count=needs_review_count)
        statistics = {
            "open_conversations_count": context.open_conversations_count,
            "conversations_needing_review": needs_review_count,
            "recommendation_count": len(context.top_recommendations),
            "open_opportunity_count": open_opportunity_count,
            "closed_won_count": closed_won_count,
            "closed_lost_count": closed_lost_count,
            "pipeline_value_breakdown": [dict(row) for row in context.pipeline_value],
        }

        return BriefOutcome(
            ai_provider=AI_PROVIDER,
            ai_model=AI_MODEL,
            summary=summary,
            recommendations=recommendations,
            statistics=statistics,
        )

    def _summary(
        self,
        context: MailboxBriefContext,
        *,
        open_opportunity_count: int,
        closed_won_count: int,
        closed_lost_count: int,
        needs_review_count: int,
    ) -> str:
        business_name = context.company_profile.name
        sentences = [f"Executive brief for {business_name}."]

        if context.open_conversations_count == 0:
            sentences.append("No open conversations right now.")
        else:
            sentences.append(
                f"{context.open_conversations_count} open conversation(s), "
                f"{needs_review_count} flagged for human review."
            )

        if open_opportunity_count == 0 and closed_won_count == 0 and closed_lost_count == 0:
            sentences.append("No opportunities have been created yet.")
        else:
            sentences.append(
                f"{open_opportunity_count} open opportunit{'y' if open_opportunity_count == 1 else 'ies'} in the "
                f"pipeline, {closed_won_count} won and {closed_lost_count} lost to date."
            )
            if context.pipeline_value:
                primary = max(context.pipeline_value, key=lambda row: row["open_pipeline_value"])
                currency_label = primary["currency"] or "unspecified currency"
                sentences.append(
                    f"Open pipeline value: {primary['open_pipeline_value']:,.2f} {currency_label}"
                    + (
                        f" (plus {len(context.pipeline_value) - 1} other currenc"
                        f"{'y' if len(context.pipeline_value) - 1 == 1 else 'ies'})."
                        if len(context.pipeline_value) > 1
                        else "."
                    )
                )

        if context.top_recommendations:
            sentences.append(f"{len(context.top_recommendations)} AI recommendation(s) awaiting action.")

        return " ".join(sentences)

    def _recommendations(self, context: MailboxBriefContext, *, needs_review_count: int) -> list[BriefRecommendation]:
        recommendations: list[BriefRecommendation] = []

        if needs_review_count > 0:
            first = context.needs_review_conversations[0]
            recommendations.append(
                BriefRecommendation(
                    title=f"Review {needs_review_count} conversation(s) flagged for human review",
                    rationale="Reply Intelligence flagged these as needing a human decision, not a confident "
                    "automatic classification.",
                    source_type="conversation",
                    source_id=first.id,
                )
            )

        for rec in context.top_recommendations:
            recommendations.append(
                BriefRecommendation(
                    title=rec.title,
                    rationale=f"AI recommendation ({rec.recommendation_type}) for {rec.prospect_name}.",
                    source_type="recommendation",
                    source_id=rec.id,
                )
            )

        return recommendations
