"""
RAG (Retrieval-Augmented Generation) router for menu chatbot.
Provides endpoints for knowledge base management and chat.
"""

from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException, Header, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from shared.infrastructure.db import get_db
from rest_api.services.rag.service import RAGService, ollama_client
from shared.security.auth import current_user_context, require_roles, verify_jwt


router = APIRouter(prefix="/api", tags=["rag"])


# Type alias for user context
UserContext = dict[str, Any]


def get_admin_user(
    authorization: str | None = Header(default=None, alias="Authorization"),
) -> UserContext:
    """
    FastAPI dependency to get admin/manager user context.
    Validates JWT and checks for ADMIN or MANAGER role.
    """
    ctx = current_user_context(authorization)
    require_roles(ctx, ["ADMIN", "MANAGER"])
    return ctx


def get_optional_user(
    authorization: str | None = Header(default=None, alias="Authorization"),
) -> Optional[UserContext]:
    """
    FastAPI dependency for optional user authentication.
    Returns None if no auth header, or validated context if present.
    """
    if not authorization:
        return None
    try:
        if not authorization.startswith("Bearer "):
            return None
        token = authorization.split(" ", 1)[1].strip()
        return verify_jwt(token)
    except Exception:
        return None


# =============================================================================
# Request/Response Schemas
# =============================================================================


class IngestTextRequest(BaseModel):
    """Request to ingest a text document."""
    content: str = Field(..., min_length=10, max_length=10000)
    title: Optional[str] = Field(None, max_length=200)
    source: Optional[str] = Field(None, max_length=50)
    branch_id: Optional[int] = None


class IngestResponse(BaseModel):
    """Response after ingestion."""
    id: int
    title: Optional[str]
    content_preview: str
    source: Optional[str]


class IngestProductsRequest(BaseModel):
    """Request to ingest all products."""
    pass  # No parameters needed, uses tenant from auth


class IngestProductsResponse(BaseModel):
    """Response after bulk product ingestion."""
    documents_created: int
    message: str


class ChatRequest(BaseModel):
    """Request for chat completion."""
    question: str = Field(..., min_length=2, max_length=500)
    branch_id: Optional[int] = None


class ChatSource(BaseModel):
    """A source document referenced in the answer."""
    id: int
    title: Optional[str]
    score: float
    source: Optional[str]


class ChatResponse(BaseModel):
    """Response from chat endpoint."""
    answer: str
    sources: list[ChatSource]
    confidence: float


class HealthResponse(BaseModel):
    """RAG service health status."""
    status: str
    ollama_available: bool
    embed_model: str
    chat_model: str


# =============================================================================
# Admin Endpoints (require authentication)
# =============================================================================


@router.post(
    "/admin/rag/ingest",
    response_model=IngestResponse,
    status_code=status.HTTP_201_CREATED,
)
async def ingest_text(
    request: IngestTextRequest,
    db: Session = Depends(get_db),
    user: UserContext = Depends(get_admin_user),
):
    """
    Ingest a text document into the knowledge base.

    Requires ADMIN or MANAGER role.
    The document will be embedded and stored for semantic search.
    """
    # HIGH-RAG-01 FIX: Validate branch_id belongs to user's tenant
    if request.branch_id:
        user_branch_ids = user.get("branch_ids", [])
        if request.branch_id not in user_branch_ids:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="No tiene acceso a esta sucursal",
            )

    service = RAGService(db)

    try:
        doc = await service.ingest_text(
            tenant_id=user["tenant_id"],
            content=request.content,
            title=request.title,
            source=request.source,
            branch_id=request.branch_id,
        )

        return IngestResponse(
            id=doc.id,
            title=doc.title,
            content_preview=doc.content[:100] + "..." if len(doc.content) > 100 else doc.content,
            source=doc.source,
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error al procesar documento: {str(e)}",
        )


@router.post(
    "/admin/rag/ingest-products",
    response_model=IngestProductsResponse,
)
async def ingest_all_products(
    db: Session = Depends(get_db),
    user: UserContext = Depends(get_admin_user),
):
    """
    Ingest all active products into the knowledge base.

    Requires ADMIN or MANAGER role.
    Creates or updates knowledge documents for all products with their
    descriptions, prices, and allergen information.
    """
    service = RAGService(db)

    try:
        count = await service.ingest_all_products(tenant_id=user["tenant_id"])

        return IngestProductsResponse(
            documents_created=count,
            message=f"Se ingresaron {count} productos al base de conocimiento.",
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error al ingestar productos: {str(e)}",
        )


# =============================================================================
# Public Chat Endpoint (for diners)
# =============================================================================


@router.post("/chat", response_model=ChatResponse)
async def chat(
    request: ChatRequest,
    db: Session = Depends(get_db),
    user: Optional[UserContext] = Depends(get_optional_user),
    x_table_token: str | None = Header(default=None, alias="X-Table-Token"),
):
    """
    Ask a question about the menu.

    This endpoint can be used by:
    - Authenticated staff (JWT token)
    - Diners with a table token (X-Table-Token header)

    RTR-CRIT-01 FIX: Removed hardcoded tenant_id=1 fallback.
    Authentication is now required (either JWT or table token).

    The response includes the answer and source documents used.
    """
    from shared.security.auth import verify_table_token

    # RTR-CRIT-01 FIX: Require authentication - no more hardcoded tenant_id
    tenant_id: int | None = None
    user_id: int | None = None

    if user:
        # Authenticated staff with JWT
        tenant_id = user["tenant_id"]
        user_id = int(user["sub"])
    elif x_table_token:
        # Diner with table token
        try:
            table_ctx = verify_table_token(x_table_token)
            tenant_id = table_ctx["tenant_id"]
        except Exception:
            pass  # Will be caught below

    if tenant_id is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required. Use JWT token or X-Table-Token header.",
        )

    # QA-MED-03 FIX: Ensure branch_id is included in chat log
    # Use request.branch_id if provided, otherwise try user's first branch
    branch_id = request.branch_id
    if branch_id is None and user:
        user_branches = user.get("branch_ids", [])
        if user_branches:
            branch_id = user_branches[0]  # Use first assigned branch

    service = RAGService(db)

    try:
        answer, sources = await service.generate_answer(
            question=request.question,
            tenant_id=tenant_id,
            branch_id=branch_id,
            user_id=user_id,
        )

        # Calculate overall confidence
        if sources:
            confidence = sum(s["score"] for s in sources) / len(sources)
        else:
            confidence = 0.0

        return ChatResponse(
            answer=answer,
            sources=[ChatSource(**s) for s in sources],
            confidence=round(confidence, 3),
        )
    except Exception as e:
        # Return a fallback response instead of failing
        return ChatResponse(
            answer="Lo siento, no puedo procesar tu pregunta en este momento. Por favor intenta de nuevo o consulta con nuestro personal.",
            sources=[],
            confidence=0.0,
        )


# =============================================================================
# Health Check
# =============================================================================


@router.get("/rag/health", response_model=HealthResponse)
async def rag_health():
    """
    Check the health of the RAG service.

    Returns the status of Ollama connection and configured models.
    """
    from shared.config.settings import EMBED_MODEL, CHAT_MODEL

    ollama_available = await ollama_client.is_available()

    return HealthResponse(
        status="healthy" if ollama_available else "degraded",
        ollama_available=ollama_available,
        embed_model=EMBED_MODEL,
        chat_model=CHAT_MODEL,
    )
