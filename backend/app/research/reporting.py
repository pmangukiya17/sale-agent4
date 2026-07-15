"""
Research Report generation - per the approved M2 adjustment, a report is
ALWAYS generated FROM an already-stored IntelligenceSnapshot (+ its
Signals/Recommendations), never an independent source of truth. Calling
this twice for the same snapshot creates two ResearchReport rows -
regenerating never edits an old one, same never-overwrite philosophy as
everything else in this domain.
"""
from datetime import datetime, timezone

from sqlalchemy.orm import Session

from app.models.intelligence_snapshot import IntelligenceSnapshot
from app.models.recommendation import Recommendation
from app.models.research_report import ResearchReport
from app.models.signal import Signal


def _now() -> datetime:
    return datetime.now(timezone.utc)


def generate_research_report(db: Session, snapshot: IntelligenceSnapshot) -> ResearchReport:
    signals = list(snapshot.signals)
    recommendations = list(snapshot.recommendations)

    content = {
        "company": {
            "business_model": snapshot.business_model,
            "products_offered": snapshot.products_offered,
            "markets_served": snapshot.markets_served,
            "certifications": snapshot.certifications,
            "manufacturing_or_trading": snapshot.manufacturing_or_trading,
            "sustainability_notes": snapshot.sustainability_notes,
            "import_export_activity": snapshot.import_export_activity,
        },
        "buyer": {
            "buyer_notes": snapshot.buyer_notes,
            "procurement_structure": snapshot.procurement_structure,
            "purchasing_process": snapshot.purchasing_process,
        },
        "signals": [
            {
                "signal_type": s.signal_type,
                "title": s.title,
                "description": s.description,
                "importance": s.importance.value if hasattr(s.importance, "value") else s.importance,
                "urgency": s.urgency.value if hasattr(s.urgency, "value") else s.urgency,
                "confidence": s.confidence,
            }
            for s in signals
        ],
        "recommendations": [
            {
                "recommendation_type": r.recommendation_type.value if hasattr(r.recommendation_type, "value") else r.recommendation_type,
                "title": r.title,
                "rationale": r.rationale,
                "confidence": r.confidence,
            }
            for r in recommendations
        ],
    }

    report = ResearchReport(
        prospect_id=snapshot.prospect_id,
        intelligence_snapshot_id=snapshot.id,
        research_job_id=snapshot.research_job_id,
        title=f"Research Report - v{snapshot.version}",
        summary=snapshot.signals_summary,
        content=content,
        generated_at=_now(),
        generated_by="system",
    )
    db.add(report)
    db.commit()
    db.refresh(report)
    return report
