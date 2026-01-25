"""
RAG Knowledge Base Models: KnowledgeDocument, ChatLog.
"""

from __future__ import annotations

from typing import Optional

from sqlalchemy import BigInteger, Boolean, Float, ForeignKey, Integer, Text
from sqlalchemy.orm import Mapped, mapped_column
from pgvector.sqlalchemy import Vector

from .base import AuditMixin, Base


class KnowledgeDocument(AuditMixin, Base):
    """
    A document chunk in the RAG knowledge base.
    Stores text content with its vector embedding for semantic search.
    Inherits: is_active, created_at, updated_at, deleted_at, *_by_id/email from AuditMixin.
    """

    __tablename__ = "knowledge_document"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    tenant_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("tenant.id"), nullable=False, index=True
    )
    branch_id: Mapped[Optional[int]] = mapped_column(
        BigInteger, ForeignKey("branch.id"), index=True
    )  # NULL means applies to all branches

    # Document content
    title: Mapped[Optional[str]] = mapped_column(Text)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    source: Mapped[Optional[str]] = mapped_column(Text)  # "product", "menu", "faq", etc.
    source_id: Mapped[Optional[int]] = mapped_column(BigInteger)  # Reference to source entity

    # Vector embedding (1536 dimensions for nomic-embed-text)
    embedding: Mapped[list[float]] = mapped_column(Vector(768), nullable=True)


class ChatLog(AuditMixin, Base):
    """
    Log of chat interactions for auditing and improvement.
    Records questions, retrieved context, and generated answers.
    Inherits: is_active, created_at, updated_at, deleted_at, *_by_id/email from AuditMixin.
    """

    __tablename__ = "chat_log"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    tenant_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("tenant.id"), nullable=False, index=True
    )
    branch_id: Mapped[Optional[int]] = mapped_column(
        BigInteger, ForeignKey("branch.id"), index=True
    )

    # Session info (can be table session or admin user)
    table_session_id: Mapped[Optional[int]] = mapped_column(
        BigInteger, ForeignKey("table_session.id"), index=True
    )
    user_id: Mapped[Optional[int]] = mapped_column(
        BigInteger, ForeignKey("app_user.id"), index=True
    )

    # Chat content
    question: Mapped[str] = mapped_column(Text, nullable=False)
    answer: Mapped[str] = mapped_column(Text, nullable=False)

    # Retrieved context (JSON array of document IDs and scores)
    context_docs: Mapped[Optional[str]] = mapped_column(Text)  # JSON: [{"id": 1, "score": 0.95}, ...]

    # Quality metrics
    response_time_ms: Mapped[Optional[int]] = mapped_column(Integer)
    confidence_score: Mapped[Optional[float]] = mapped_column(Float)

    # User feedback
    feedback_helpful: Mapped[Optional[bool]] = mapped_column(Boolean)
