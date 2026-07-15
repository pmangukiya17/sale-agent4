"""
Plain many-to-many association table for Research (no extra columns of
its own - SignalEvidence/RecommendationEvidence DO carry extra columns
like excerpt, so those are real model classes, not plain Tables, see
signal_evidence.py / recommendation_evidence.py).
"""
from sqlalchemy import Column, ForeignKey, Table
from sqlalchemy.dialects.postgresql import UUID

from app.db.base_class import Base

ai_analysis_source_documents = Table(
    "ai_analysis_source_documents",
    Base.metadata,
    Column("ai_analysis_id", UUID(as_uuid=True), ForeignKey("ai_analyses.id", ondelete="CASCADE"), primary_key=True),
    Column("raw_document_id", UUID(as_uuid=True), ForeignKey("raw_documents.id", ondelete="CASCADE"), primary_key=True),
)
