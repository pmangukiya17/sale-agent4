"""
DeterministicPersonalizationEngine: the ONLY PersonalizationEngine
implementation in M3, per explicit instruction. Rule-based scoring and
templated narrative assembly over already-stored Research (M2) output -
no network calls, no model weights, fully reproducible. model_used is a
literal marker string (not a real model name) so a future real engine is
unambiguously distinguishable in stored data, same convention as M2's
deterministic-keyword-stub.

This exists to prove the schema/pipeline/evidence machinery end to end,
not to be a good sales strategist. Swapping this out later for a real
LLM-backed engine requires only a new class honoring the same
PersonalizationOutcome/StrategyDraft/CommunicationStrategyDraft shapes -
no other change.
"""
from app.models.enums import (
    BuyerReadinessLevel,
    CommunicationFormality,
    CommunicationIntensityLevel,
    CommunicationLength,
    PersonalizationStrategyRank,
    RecommendationStatus,
    RelationshipStage,
    SignalImportance,
    SignalStatus,
    SignalUrgency,
)
from app.personalization.context import PersonalizationContext
from app.personalization.engine.base import (
    CommunicationStrategyDraft,
    EvidenceDraft,
    PersonalizationEngine,
    PersonalizationOutcome,
    StrategyDraft,
)

MODEL_USED = "deterministic-strategy-stub"
PROMPT_VERSION = "v1"

_IMPORTANCE_POINTS = {
    SignalImportance.LOW: 0,
    SignalImportance.MEDIUM: 1,
    SignalImportance.HIGH: 2,
    SignalImportance.CRITICAL: 3,
}
_URGENCY_POINTS = {
    SignalUrgency.LOW: 0,
    SignalUrgency.MEDIUM: 0,
    SignalUrgency.HIGH: 1,
    SignalUrgency.IMMEDIATE: 2,
}


def _score_signals(signals: list) -> int:
    score = 0
    for s in signals:
        if s.status == SignalStatus.DISMISSED:
            continue
        score += _IMPORTANCE_POINTS.get(s.importance, 0)
        score += _URGENCY_POINTS.get(s.urgency, 0)
    return score


def _readiness_from_score(score: int, has_snapshot: bool) -> BuyerReadinessLevel:
    if not has_snapshot:
        return BuyerReadinessLevel.UNKNOWN
    if score >= 5:
        return BuyerReadinessLevel.READY_TO_ENGAGE
    if score >= 3:
        return BuyerReadinessLevel.HIGH
    if score >= 1:
        return BuyerReadinessLevel.MEDIUM
    return BuyerReadinessLevel.LOW


class DeterministicPersonalizationEngine(PersonalizationEngine):
    def synthesize(self, context: PersonalizationContext) -> PersonalizationOutcome:
        snapshot = context.intelligence_snapshot
        active_signals = [s for s in context.signals if s.status != SignalStatus.DISMISSED]
        active_recommendations = [r for r in context.recommendations if r.status != RecommendationStatus.DISMISSED]

        score = _score_signals(active_signals)
        readiness = _readiness_from_score(score, snapshot is not None)
        readiness_reasoning = (
            f"Scored {score} point(s) across {len(active_signals)} active signal(s) "
            f"(importance+urgency weighted)."
            if snapshot is not None
            else "No Intelligence Snapshot exists yet for this prospect - readiness cannot be inferred."
        )

        buyer_persona = self._buyer_persona(context, snapshot)
        communication_strategy = self._communication_strategy(context, readiness)
        strategies = self._strategies(context, active_signals, active_recommendations, readiness)

        return PersonalizationOutcome(
            model_used=MODEL_USED,
            prompt_version=PROMPT_VERSION,
            buyer_persona=buyer_persona,
            buyer_readiness=readiness,
            buyer_readiness_reasoning=readiness_reasoning,
            communication_strategy=communication_strategy,
            strategies=strategies,
        )

    def _buyer_persona(self, context: PersonalizationContext, snapshot) -> dict:
        prospect = context.prospect
        business_model = snapshot.business_model if snapshot else None
        procurement_structure = snapshot.procurement_structure if snapshot else None

        archetype = f"{prospect.company_size_range or 'unknown-size'} {business_model or 'business'} buyer"
        priorities = []
        if snapshot and snapshot.certifications:
            priorities.append("compliance / certifications")
        if snapshot and snapshot.sustainability_notes:
            priorities.append("sustainability")
        if not priorities:
            priorities.append("price and reliability (default - insufficient signal for a sharper read)")

        decision_style = (
            f"structured procurement ({procurement_structure})"
            if procurement_structure
            else "no clear procurement structure observed - likely informal/ad hoc decision-making"
        )

        return {
            "archetype": archetype,
            "priorities": priorities,
            "decision_style": decision_style,
        }

    def _communication_strategy(self, context: PersonalizationContext, readiness: BuyerReadinessLevel) -> CommunicationStrategyDraft:
        snapshot = context.intelligence_snapshot
        prospect = context.prospect

        formality = (
            CommunicationFormality.FORMAL
            if (snapshot and (snapshot.business_model == "manufacturer" or snapshot.procurement_structure))
            else CommunicationFormality.NEUTRAL
        )
        directness = (
            CommunicationIntensityLevel.HIGH
            if readiness in (BuyerReadinessLevel.HIGH, BuyerReadinessLevel.READY_TO_ENGAGE)
            else CommunicationIntensityLevel.MEDIUM
        )
        warmth = (
            CommunicationIntensityLevel.HIGH
            if prospect.relationship_stage in (RelationshipStage.ENGAGED, RelationshipStage.QUALIFIED, RelationshipStage.NEGOTIATION)
            else CommunicationIntensityLevel.MEDIUM
        )
        technical_depth = (
            CommunicationIntensityLevel.HIGH
            if snapshot and snapshot.certifications
            else CommunicationIntensityLevel.MEDIUM
        )
        authority = (
            CommunicationIntensityLevel.HIGH
            if context.company_profile.export_certifications
            else CommunicationIntensityLevel.MEDIUM
        )
        consultative_level = (
            CommunicationIntensityLevel.HIGH
            if readiness in (BuyerReadinessLevel.UNKNOWN, BuyerReadinessLevel.LOW)
            else CommunicationIntensityLevel.MEDIUM
        )
        urgency = {
            BuyerReadinessLevel.READY_TO_ENGAGE: CommunicationIntensityLevel.HIGH,
            BuyerReadinessLevel.HIGH: CommunicationIntensityLevel.MEDIUM,
        }.get(readiness, CommunicationIntensityLevel.LOW)
        message_length = (
            CommunicationLength.SHORT
            if readiness == BuyerReadinessLevel.READY_TO_ENGAGE
            else CommunicationLength.LONG
            if consultative_level == CommunicationIntensityLevel.HIGH
            else CommunicationLength.MEDIUM
        )

        return CommunicationStrategyDraft(
            formality=formality,
            directness=directness,
            warmth=warmth,
            technical_depth=technical_depth,
            authority=authority,
            consultative_level=consultative_level,
            urgency=urgency,
            message_length=message_length,
            rationale=(
                f"Derived from buyer_readiness={readiness.value}, relationship_stage={prospect.relationship_stage.value}, "
                f"and whether a procurement structure / certifications were observed."
            ),
        )

    def _strategies(self, context, active_signals, active_recommendations, readiness) -> list[StrategyDraft]:
        strategies: list[StrategyDraft] = []

        # Sort recommendations by confidence (None treated as lowest) so the
        # strongest available idea becomes the primary strategy.
        ranked_recommendations = sorted(
            active_recommendations, key=lambda r: (r.confidence or 0.0), reverse=True
        )
        top_signal = max(active_signals, key=lambda s: (_IMPORTANCE_POINTS.get(s.importance, 0) + _URGENCY_POINTS.get(s.urgency, 0)), default=None)

        # --- PRIMARY -----------------------------------------------------
        if ranked_recommendations:
            primary_rec = ranked_recommendations[0]
            evidence = [EvidenceDraft(recommendation_id=primary_rec.id, excerpt=primary_rec.title)]
            if top_signal is not None:
                evidence.append(EvidenceDraft(signal_id=top_signal.id, excerpt=top_signal.title))
            strategies.append(StrategyDraft(
                strategy_rank=PersonalizationStrategyRank.PRIMARY,
                title=primary_rec.title,
                narrative=(
                    f"Lead with: {primary_rec.title}. {primary_rec.rationale or ''} "
                    f"Buyer readiness is currently {readiness.value}."
                ).strip(),
                confidence=primary_rec.confidence,
                reasoning=f"Highest-confidence non-dismissed recommendation ({primary_rec.recommendation_type.value}).",
                evidence=evidence,
            ))
        else:
            strategies.append(StrategyDraft(
                strategy_rank=PersonalizationStrategyRank.PRIMARY,
                title="Open with a discovery-oriented approach",
                narrative=(
                    "No AI recommendations exist yet for this prospect - lead with an "
                    "open, discovery-oriented first contact rather than a specific pitch."
                ),
                confidence=0.0,
                reasoning="No non-dismissed Recommendation rows available to anchor a sharper strategy.",
                evidence=[],
            ))

        # --- SECONDARY (only if a second, distinct-type recommendation exists) --
        if len(ranked_recommendations) > 1:
            secondary_rec = next(
                (r for r in ranked_recommendations[1:] if r.recommendation_type != ranked_recommendations[0].recommendation_type),
                ranked_recommendations[1],
            )
            strategies.append(StrategyDraft(
                strategy_rank=PersonalizationStrategyRank.SECONDARY,
                title=secondary_rec.title,
                narrative=f"If the primary angle doesn't land, pivot to: {secondary_rec.title}. {secondary_rec.rationale or ''}".strip(),
                confidence=secondary_rec.confidence,
                reasoning=f"Second-highest-confidence recommendation ({secondary_rec.recommendation_type.value}).",
                evidence=[EvidenceDraft(recommendation_id=secondary_rec.id, excerpt=secondary_rec.title)],
            ))

        # --- FALLBACK (always produced - a safe, low-risk approach) ------
        fallback_evidence = []
        if context.intelligence_snapshot is not None:
            fallback_evidence.append(EvidenceDraft(intelligence_snapshot_id=context.intelligence_snapshot.id))
        strategies.append(StrategyDraft(
            strategy_rank=PersonalizationStrategyRank.FALLBACK,
            title="Request a sample / share credentials",
            narrative=(
                "If neither the primary nor secondary angle gets traction, fall back to a "
                "low-commitment ask - offering a product sample or sharing company "
                "certifications/track record - to keep the door open without pressure."
            ),
            confidence=0.2,
            reasoning="Always-available, low-risk fallback - does not depend on any specific Recommendation existing.",
            evidence=fallback_evidence,
        ))

        return strategies
