"""
RAG (Retrieval-Augmented Generation) service for the menu chatbot.
Uses Ollama for embeddings and chat completion, pgvector for similarity search.
"""

import asyncio
import json
import time
from typing import Optional

import httpx
from sqlalchemy import select, text
from sqlalchemy.orm import Session, selectinload

from rest_api.models import KnowledgeDocument, ChatLog, Product, BranchProduct, ProductRAGConfig, Recipe, RecipeAllergen, Allergen
from rest_api.services.catalog.product_view import (
    get_product_complete,
    generate_product_text_for_rag,
    generate_recipe_text_for_rag,
)
from shared.config.settings import OLLAMA_URL, EMBED_MODEL, CHAT_MODEL


# =============================================================================
# Ollama Client
# =============================================================================


class OllamaClient:
    """
    HTTP client for Ollama API.

    SVC-HIGH-04 FIX: Uses connection pooling instead of creating
    a new HTTP client for every request.
    SVC-RACE-01 FIX: Added asyncio.Lock to prevent race condition during
    client initialization.
    """

    def __init__(self, base_url: str = OLLAMA_URL):
        self.base_url = base_url.rstrip("/")
        self.timeout = 60.0  # Longer timeout for LLM responses
        # SVC-HIGH-04 FIX: Reusable HTTP client with connection pooling
        self._client: Optional[httpx.AsyncClient] = None
        # SVC-RACE-01 FIX: Lock to prevent race condition during initialization
        self._client_lock: Optional[asyncio.Lock] = None

    def _get_lock(self) -> asyncio.Lock:
        """
        SVC-RACE-01 FIX: Get or create the asyncio lock.
        Uses double-check pattern with threading lock for event loop safety.
        """
        if self._client_lock is None:
            import threading
            _init_lock = threading.Lock()
            with _init_lock:
                if self._client_lock is None:
                    self._client_lock = asyncio.Lock()
        return self._client_lock

    async def _get_client(self) -> httpx.AsyncClient:
        """
        SVC-HIGH-04 FIX: Get or create the shared HTTP client.
        SVC-RACE-01 FIX: Protected with asyncio.Lock to prevent race condition.
        Lazy initialization for proper async context.
        """
        # Fast path: client already initialized
        if self._client is not None and not self._client.is_closed:
            return self._client

        # Slow path: acquire lock and initialize
        async with self._get_lock():
            # Double-check after acquiring lock
            if self._client is None or self._client.is_closed:
                self._client = httpx.AsyncClient(
                    timeout=self.timeout,
                    limits=httpx.Limits(max_connections=10, max_keepalive_connections=5),
                )
        return self._client

    async def close(self) -> None:
        """
        SVC-HIGH-04 FIX: Close the HTTP client properly.
        Should be called on application shutdown.
        """
        if self._client is not None and not self._client.is_closed:
            await self._client.aclose()
            self._client = None

    async def get_embedding(self, text: str, model: str = EMBED_MODEL) -> list[float]:
        """
        Generate embedding vector for text using Ollama.
        Returns a list of floats representing the semantic meaning.
        """
        client = await self._get_client()
        response = await client.post(
            f"{self.base_url}/api/embeddings",
            json={"model": model, "prompt": text},
        )
        response.raise_for_status()
        data = response.json()
        return data["embedding"]

    async def chat(
        self,
        prompt: str,
        system_prompt: Optional[str] = None,
        model: str = CHAT_MODEL,
    ) -> str:
        """
        Generate chat response using Ollama.
        Returns the generated text.
        """
        messages = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": prompt})

        client = await self._get_client()
        response = await client.post(
            f"{self.base_url}/api/chat",
            json={
                "model": model,
                "messages": messages,
                "stream": False,
            },
        )
        response.raise_for_status()
        data = response.json()
        return data["message"]["content"]

    async def is_available(self) -> bool:
        """Check if Ollama server is available."""
        try:
            client = await self._get_client()
            response = await client.get(f"{self.base_url}/api/tags")
            return response.status_code == 200
        except Exception:
            return False


# Global client instance
ollama_client = OllamaClient()


async def close_ollama_client() -> None:
    """
    SVC-HIGH-04 FIX: Helper to close the global Ollama client.
    Should be called in application lifespan shutdown.
    """
    await ollama_client.close()


# =============================================================================
# RAG Service
# =============================================================================


class RAGService:
    """Service for RAG operations: ingestion, retrieval, and generation."""

    # System prompt for the menu chatbot - anti-hallucination policy
    # Phase 5: Enhanced prompt with allergen risk levels and dietary filters
    SYSTEM_PROMPT = """Eres un asistente virtual amigable para un restaurante. Tu rol es ayudar a los clientes con preguntas sobre el menu, ingredientes, alergenos, informacion dietaria y recomendaciones.

REGLAS IMPORTANTES:
1. SOLO responde basandote en la informacion proporcionada en el contexto.
2. Si la informacion no menciona alergenos especificos, di "No tengo informacion confirmada sobre alergenos para este plato. Por favor consulta con el personal."
3. Si no encuentras informacion relevante, di "No tengo esa informacion. Por favor consulta con nuestro personal."
4. NUNCA inventes precios, ingredientes o informacion que no este en el contexto.
5. Responde en espanol, de manera concisa y amigable.
6. Si te preguntan sobre alergias, siempre recomienda verificar con el personal como medida de seguridad adicional.

MANEJO DE ALERGENOS Y RESTRICCIONES DIETARIAS:
- Presta especial atencion a las lineas que dicen "CONTIENE ALERGENOS" - son criticas para la seguridad.
- "PUEDE CONTENER TRAZAS DE" indica posible contaminacion cruzada - advierte al cliente.
- "Libre de" indica certificacion de ausencia del alergeno.
- Para preguntas de dietas (vegano, vegetariano, sin gluten, celiaco, keto, etc.), usa el "Perfil dietetico" del producto.
- Si un producto tiene "Advertencia", mencionala siempre en tu respuesta.

FILTROS COMUNES:
- Pregunta por vegano/vegetariano: busca productos con esas etiquetas en "Perfil dietetico".
- Pregunta por celiaco/sin gluten: busca "Sin Gluten" o "Apto Celiacos" - estos son diferentes niveles de restriccion.
- Pregunta por alergias especificas: revisa "CONTIENE ALERGENOS" y "PUEDE CONTENER TRAZAS".

Contexto del menu:
{context}"""

    def __init__(self, db: Session):
        self.db = db

    async def ingest_text(
        self,
        tenant_id: int,
        content: str,
        title: Optional[str] = None,
        source: Optional[str] = None,
        source_id: Optional[int] = None,
        branch_id: Optional[int] = None,
    ) -> KnowledgeDocument:
        """
        Ingest a text document into the knowledge base.
        Generates embedding and stores in database.
        """
        # Generate embedding
        embedding = await ollama_client.get_embedding(content)

        # Create document
        doc = KnowledgeDocument(
            tenant_id=tenant_id,
            branch_id=branch_id,
            title=title,
            content=content,
            source=source,
            source_id=source_id,
            embedding=embedding,
        )

        # SVC-HIGH-02 FIX: Add try-except with rollback for commit errors
        try:
            self.db.add(doc)
            self.db.commit()
            self.db.refresh(doc)
        except Exception as e:
            self.db.rollback()
            raise RuntimeError(f"Failed to ingest document: {str(e)}") from e

        return doc

    async def ingest_product(
        self,
        tenant_id: int,
        product: Product,
        branch_prices: list[BranchProduct],
    ) -> KnowledgeDocument:
        """
        Ingest a product into the knowledge base.
        Creates a rich text description using the canonical model data.

        Phase 5 improvement: Uses get_product_complete() and generate_product_text_for_rag()
        to include allergens, dietary profile, ingredients, cooking methods, and warnings.

        CRIT-RAG-01 FIX: Added tenant validation to prevent cross-tenant data access.
        """
        # CRIT-RAG-01 FIX: Validate product belongs to specified tenant
        if product.tenant_id != tenant_id:
            raise ValueError(f"Product {product.id} does not belong to tenant {tenant_id}")

        # Get complete product view with all canonical data
        complete_view = get_product_complete(self.db, product.id)

        if complete_view:
            # Use first available price (or average if multiple branches)
            price_cents = branch_prices[0].price_cents if branch_prices else None

            # Generate enriched text for RAG
            content = generate_product_text_for_rag(complete_view, price_cents)
        else:
            # Fallback to basic description if view fails
            lines = [f"Producto: {product.name}"]
            if product.description:
                lines.append(f"Descripcion: {product.description}")
            for bp in branch_prices:
                price_str = f"${bp.price_cents / 100:.2f}"
                lines.append(f"Precio: {price_str}")
            content = "\n".join(lines)

        return await self.ingest_text(
            tenant_id=tenant_id,
            content=content,
            title=product.name,
            source="product",
            source_id=product.id,
        )

    async def ingest_recipe(
        self,
        tenant_id: int,
        recipe: Recipe,
    ) -> KnowledgeDocument:
        """
        Ingest a recipe into the knowledge base.
        Creates a rich text description using the canonical recipe model data.

        This enables the chatbot to answer questions like:
        - "¿Cómo se prepara la milanesa napolitana?"
        - "¿Qué ingredientes tiene el tiramisú?"
        - "¿Cuánto tiempo tarda el risotto?"
        - "¿Es apto para celíacos?"

        The function fetches allergen data from RecipeAllergen relationship
        and generates enriched text using generate_recipe_text_for_rag().

        CRIT-RAG-02 FIX: Added tenant validation and transaction consistency.
        """
        # CRIT-RAG-02 FIX: Validate recipe belongs to specified tenant
        if recipe.tenant_id != tenant_id:
            raise ValueError(f"Recipe {recipe.id} does not belong to tenant {tenant_id}")

        # Fetch allergens for this recipe with full details
        allergen_data = self.db.execute(
            select(Allergen, RecipeAllergen.risk_level)
            .join(RecipeAllergen, Allergen.id == RecipeAllergen.allergen_id)
            .where(
                RecipeAllergen.recipe_id == recipe.id,
                RecipeAllergen.is_active.is_(True),
                Allergen.is_active.is_(True),
            )
        ).all()

        allergens = [
            {
                "id": allergen.id,
                "name": allergen.name,
                "icon": allergen.icon,
                "risk_level": risk_level,
            }
            for allergen, risk_level in allergen_data
        ]

        # Generate enriched text for RAG
        content = generate_recipe_text_for_rag(recipe, allergens if allergens else None)

        # Check if document already exists for this recipe
        existing = self.db.execute(
            select(KnowledgeDocument).where(
                KnowledgeDocument.tenant_id == tenant_id,
                KnowledgeDocument.source == "recipe",
                KnowledgeDocument.source_id == recipe.id,
            )
        ).scalar_one_or_none()

        if existing:
            # CRIT-RAG-02 FIX: Delete existing without separate commit
            # The ingest_text will commit both operations in one transaction
            self.db.delete(existing)
            self.db.flush()  # Flush instead of commit to stay in same transaction

        return await self.ingest_text(
            tenant_id=tenant_id,
            content=content,
            title=recipe.name,
            source="recipe",
            source_id=recipe.id,
            branch_id=recipe.branch_id,
        )

    async def ingest_all_recipes(self, tenant_id: int, branch_id: Optional[int] = None) -> tuple[int, list[str]]:
        """
        Ingest all active recipes for a tenant (optionally filtered by branch) into the knowledge base.
        Returns tuple of (count of successful ingestions, list of errors).
        """
        # Build query for active recipes
        query = select(Recipe).where(
            Recipe.tenant_id == tenant_id,
            Recipe.is_active.is_(True),
        )

        if branch_id is not None:
            query = query.where(Recipe.branch_id == branch_id)

        recipes = self.db.execute(query).scalars().all()

        count = 0
        errors: list[str] = []

        for recipe in recipes:
            try:
                await self.ingest_recipe(tenant_id, recipe)
                count += 1
            except Exception as e:
                error_msg = f"Failed to ingest recipe {recipe.id} ({recipe.name}): {str(e)}"
                errors.append(error_msg)
                # Ensure session is clean for next iteration
                self.db.rollback()

        return count, errors

    async def search_similar(
        self,
        query: str,
        tenant_id: int,
        branch_id: Optional[int] = None,
        limit: int = 5,
        min_score: float = 0.3,
    ) -> list[tuple[KnowledgeDocument, float]]:
        """
        Search for documents similar to the query.
        Returns list of (document, similarity_score) tuples.
        """
        # Generate query embedding
        query_embedding = await ollama_client.get_embedding(query)

        # Build the similarity search query using pgvector
        # cosine_distance returns 0 for identical vectors, so we convert to similarity
        embedding_str = "[" + ",".join(map(str, query_embedding)) + "]"

        sql = text("""
            SELECT
                id,
                1 - (embedding <=> :embedding::vector) as similarity
            FROM knowledge_document
            WHERE tenant_id = :tenant_id
              AND is_active = true
              AND embedding IS NOT NULL
              AND (:branch_id IS NULL OR branch_id IS NULL OR branch_id = :branch_id)
            ORDER BY embedding <=> :embedding::vector
            LIMIT :limit
        """)

        result = self.db.execute(
            sql,
            {
                "embedding": embedding_str,
                "tenant_id": tenant_id,
                "branch_id": branch_id,
                "limit": limit,
            },
        )

        # Fetch full documents for matching IDs
        docs_with_scores = []
        for row in result:
            doc_id, similarity = row
            if similarity >= min_score:
                doc = self.db.get(KnowledgeDocument, doc_id)
                if doc:
                    docs_with_scores.append((doc, float(similarity)))

        return docs_with_scores

    def _get_risk_disclaimer(self, risk_level: str) -> str:
        """Get appropriate disclaimer based on product risk level."""
        disclaimers = {
            "high": "⚠️ IMPORTANTE: Este producto requiere verificación especial con el personal por posibles riesgos para personas con alergias o restricciones dietarias.",
            "medium": "ℹ️ Nota: Por favor verifica con el personal si tienes alergias o restricciones dietarias específicas.",
            "low": "",  # No disclaimer for low risk
        }
        return disclaimers.get(risk_level, "")

    async def generate_answer(
        self,
        question: str,
        tenant_id: int,
        branch_id: Optional[int] = None,
        table_session_id: Optional[int] = None,
        user_id: Optional[int] = None,
    ) -> tuple[str, list[dict]]:
        """
        Generate an answer to a question using RAG.
        Returns (answer, sources) where sources is a list of referenced documents.

        Phase 5 enhancement: Respects ProductRAGConfig risk_level for each product
        and adds appropriate disclaimers to the response.
        """
        start_time = time.time()

        # Search for relevant context
        similar_docs = await self.search_similar(
            query=question,
            tenant_id=tenant_id,
            branch_id=branch_id,
            limit=5,
        )

        # Build context from retrieved documents and track high-risk products
        high_risk_products = []
        medium_risk_products = []
        if similar_docs:
            context_parts = []
            sources = []
            for doc, score in similar_docs:
                context_parts.append(f"- {doc.content}")
                sources.append({
                    "id": doc.id,
                    "title": doc.title,
                    "score": round(score, 3),
                    "source": doc.source,
                    "source_id": doc.source_id,
                })

                # Check risk level for product sources
                if doc.source == "product" and doc.source_id:
                    rag_config = self.db.scalar(
                        select(ProductRAGConfig).where(
                            ProductRAGConfig.product_id == doc.source_id,
                            ProductRAGConfig.is_active.is_(True),
                        )
                    )
                    if rag_config:
                        if rag_config.risk_level == "high":
                            high_risk_products.append(doc.title)
                        elif rag_config.risk_level == "medium":
                            medium_risk_products.append(doc.title)

            context = "\n".join(context_parts)
        else:
            context = "No se encontro informacion relevante en la base de conocimiento."
            sources = []

        # Build the prompt with context
        system_prompt = self.SYSTEM_PROMPT.format(context=context)

        # Generate answer
        try:
            answer = await ollama_client.chat(
                prompt=question,
                system_prompt=system_prompt,
            )

            # Append risk disclaimers if any high/medium risk products were referenced
            if high_risk_products:
                answer += f"\n\n{self._get_risk_disclaimer('high')}"
            elif medium_risk_products:
                answer += f"\n\n{self._get_risk_disclaimer('medium')}"

        except Exception as e:
            answer = f"Lo siento, no puedo procesar tu pregunta en este momento. Error: {str(e)}"

        # Calculate response time
        response_time_ms = int((time.time() - start_time) * 1000)

        # Calculate confidence score (average of top 3 similarity scores)
        if sources:
            top_scores = [s["score"] for s in sources[:3]]
            confidence = sum(top_scores) / len(top_scores)
        else:
            confidence = 0.0

        # Log the interaction
        chat_log = ChatLog(
            tenant_id=tenant_id,
            branch_id=branch_id,
            table_session_id=table_session_id,
            user_id=user_id,
            question=question,
            answer=answer,
            context_docs=json.dumps(sources) if sources else None,
            response_time_ms=response_time_ms,
            confidence_score=confidence,
        )
        self.db.add(chat_log)
        self.db.commit()

        return answer, sources

    async def ingest_all_products(self, tenant_id: int) -> tuple[int, list[str]]:
        """
        Ingest all active products for a tenant into the knowledge base.
        Returns tuple of (count of successful ingestions, list of errors).

        HIGH-09 FIX: Uses eager loading to avoid N+1 queries.
        SVC-HIGH-01 FIX: Added error handling to continue on individual failures
        and report all errors at the end.
        SVC-MED-02 FIX: Only ingests products that have at least one branch
        with is_available=True.
        """
        # HIGH-09 FIX: Get all active products with their branch prices in a single query
        products = self.db.execute(
            select(Product)
            .options(selectinload(Product.branch_prices))
            .where(
                Product.tenant_id == tenant_id,
                Product.is_active.is_(True),
            )
        ).scalars().all()

        count = 0
        errors: list[str] = []

        for product in products:
            try:
                # HIGH-09 FIX: Use eager-loaded relationship instead of N+1 query
                branch_prices = [bp for bp in product.branch_prices if bp.is_available]

                if branch_prices:
                    # Check if document already exists
                    existing = self.db.execute(
                        select(KnowledgeDocument).where(
                            KnowledgeDocument.tenant_id == tenant_id,
                            KnowledgeDocument.source == "product",
                            KnowledgeDocument.source_id == product.id,
                        )
                    ).scalar_one_or_none()

                    if existing:
                        # Update existing document
                        self.db.delete(existing)
                        self.db.commit()

                    await self.ingest_product(tenant_id, product, list(branch_prices))
                    count += 1

            except Exception as e:
                # SVC-HIGH-01 FIX: Log error and continue with next product
                error_msg = f"Failed to ingest product {product.id} ({product.name}): {str(e)}"
                errors.append(error_msg)
                # Ensure session is clean for next iteration
                self.db.rollback()

        return count, errors
