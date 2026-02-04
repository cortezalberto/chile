# 🚀 Mejoras Recomendadas - Proyecto Integrador

**Fecha de Análisis**: Febrero 2026  
**Basado en**: Análisis completo del proyecto + Skills de Redis Best Practices + Knowledge Base

---

## 📋 Índice

1. [Mejoras Críticas (Alta Prioridad)](#1-mejoras-críticas-alta-prioridad)
2. [Mejoras de Arquitectura](#2-mejoras-de-arquitectura)
3. [Mejoras de Redis (Basado en Skill)](#3-mejoras-de-redis-basado-en-skill)
4. [Mejoras de Testing](#4-mejoras-de-testing)
5. [Mejoras de Observabilidad](#5-mejoras-de-observabilidad)
6. [Mejoras de Performance](#6-mejoras-de-performance)
7. [Mejoras de Seguridad](#7-mejoras-de-seguridad)
8. [Mejoras de Developer Experience](#8-mejoras-de-developer-experience)
9. [Roadmap de Implementación](#9-roadmap-de-implementación)

---

## 1. Mejoras Críticas (Alta Prioridad)

### 1.1 CRIT-01: Completar Migración a Thin Controllers

**Estado Actual**: Según audit report, aún hay routers con lógica de negocio:
- `waiter/routes.py`
- `diner/orders.py`
- `kitchen/rounds.py`
- `tables/routes.py`
- `billing/routes.py`
- `auth/routes.py`

**Mejora Propuesta**:
```python
# ANTES (router con lógica)
@router.post("/rounds/{round_id}/submit")
async def submit_round(round_id: int, db: Session = Depends(get_db)):
    round_obj = db.query(Round).filter(Round.id == round_id).first()
    if round_obj.status != "PENDING":
        raise HTTPException(400, "Invalid status")
    round_obj.status = "SUBMITTED"
    db.commit()
    # Redis publish inline...
    return round_obj

# DESPUÉS (thin controller + domain service)
@router.post("/rounds/{round_id}/submit")
async def submit_round(
    round_id: int,
    db: Session = Depends(get_db),
    background_tasks: BackgroundTasks = BackgroundTasks(),
):
    service = RoundService(db)
    result = service.submit(round_id, background_tasks)
    return result
```

**Archivos a crear**:
- `rest_api/services/domain/round_service.py`
- `rest_api/services/domain/billing_service.py`
- `rest_api/services/domain/table_service.py` (expandir)

**Impacto**: +1.25 puntos en Clean Architecture score (7.75 → 9.0)

---

### 1.2 CRIT-02: Resolver Mixing de Async/Sync en DB Operations

**Estado Actual**: FastAPI audit indica 7/10 en async (mixing sync DB ops en async handlers)

**Mejora Propuesta**:
```python
# ANTES: Bloquea event loop
@router.get("/products")
async def list_products(db: Session = Depends(get_db)):
    products = db.query(Product).all()  # ← SYNC operation in async context
    return products

# OPCIÓN A: Usar run_in_executor
@router.get("/products")
async def list_products(db: AsyncSession = Depends(get_async_db)):
    result = await db.execute(select(Product))
    return result.scalars().all()

# OPCIÓN B: Declarar como sync (más pragmático)
@router.get("/products")
def list_products(db: Session = Depends(get_db)):  # ← No async keyword
    return db.query(Product).all()
```

**Recomendación**: Opción B es más pragmática. FastAPI maneja sync endpoints en threadpool automáticamente.

---

### 1.3 CRIT-03: Implementar Metrics Coverage

**Estado Actual**: Prometheus endpoint existe pero sin dashboards documentados

**Mejora Propuesta**: Crear dashboards Grafana para:

```yaml
# grafana/dashboards/ws_gateway.json
panels:
  - title: "Active Connections"
    query: wsgateway_connections_total
  
  - title: "Broadcasts/min"
    query: rate(wsgateway_broadcasts_total[1m])
  
  - title: "Auth Rejections"
    query: wsgateway_connections_rejected_total{reason="auth"}
  
  - title: "Rate Limits Triggered"
    query: wsgateway_connections_rejected_total{reason="rate_limit"}

# grafana/dashboards/redis_health.json
panels:
  - title: "Circuit Breaker State"
    query: redis_circuit_breaker_state
  
  - title: "Event Publish Latency p99"
    query: histogram_quantile(0.99, redis_publish_duration_seconds_bucket)
```

---

## 2. Mejoras de Arquitectura

### 2.1 ARCH-01: Implementar CQRS para Reads de Alto Tráfico

**Caso de Uso**: Menu público consultado por todos los comensales

```python
# rest_api/services/queries/menu_query_service.py
class MenuQueryService:
    """CQRS: Read-optimized service for public menu."""
    
    def __init__(self, redis: Redis):
        self.redis = redis
        self.cache_ttl = PRODUCT_CACHE_TTL
    
    async def get_menu(self, branch_id: int, tenant_id: int) -> MenuResponse:
        cache_key = get_branch_products_cache_key(branch_id, tenant_id)
        
        # Try cache first
        cached = await self.redis.get(cache_key)
        if cached:
            return MenuResponse.model_validate_json(cached)
        
        # Cache miss - fetch from read replica
        menu = await self._fetch_from_replica(branch_id, tenant_id)
        
        # Cache with TTL
        await self.redis.setex(cache_key, self.cache_ttl, menu.model_dump_json())
        
        return menu
```

**Configuración de Read Replica**:
```python
# shared/config/settings.py
database_url: str = "postgresql://...@primary:5432/menu_ops"
database_replica_url: str = "postgresql://...@replica:5432/menu_ops"  # NEW
```

---

### 2.2 ARCH-02: Implementar Event Sourcing para Auditoría

**Estado Actual**: Audit log básico, pero sin replay capability

```python
# rest_api/models/event_store.py
class DomainEvent(Base):
    """Immutable event store for full audit trail."""
    __tablename__ = "domain_events"
    
    id = Column(BigInteger, primary_key=True)
    aggregate_type = Column(String(50), nullable=False)  # "Order", "Round", etc.
    aggregate_id = Column(BigInteger, nullable=False)
    event_type = Column(String(100), nullable=False)  # "OrderCreated", "RoundSubmitted"
    event_data = Column(JSONB, nullable=False)
    metadata = Column(JSONB)  # user_id, ip, timestamp
    sequence = Column(Integer, nullable=False)  # Per-aggregate sequence
    created_at = Column(DateTime, default=datetime.utcnow)
    
    __table_args__ = (
        Index('ix_domain_events_aggregate', 'aggregate_type', 'aggregate_id'),
    )
```

---

### 2.3 ARCH-03: Implementar Saga Pattern para Pagos

**Estado Actual**: Flujo de pago probablemente lineal

```python
# rest_api/services/sagas/payment_saga.py
class PaymentSaga:
    """Coordina transacción distribuida de pago."""
    
    steps = [
        ("validate_session", "rollback_session_validation"),
        ("reserve_inventory", "release_inventory"),
        ("process_payment", "refund_payment"),
        ("close_session", "reopen_session"),
        ("emit_receipt", "void_receipt"),
    ]
    
    async def execute(self, session_id: int, payment_data: PaymentRequest):
        completed_steps = []
        try:
            for step_name, _ in self.steps:
                await getattr(self, step_name)(session_id, payment_data)
                completed_steps.append(step_name)
        except Exception as e:
            # Compensate in reverse order
            for step_name in reversed(completed_steps):
                compensate = self.steps_dict[step_name]
                await getattr(self, compensate)(session_id)
            raise SagaFailedException(e, completed_steps)
```

---

## 3. Mejoras de Redis (Basado en Skill)

### 3.1 REDIS-01: Implementar Redis Cluster para HA

**Estado Actual**: Redis standalone (SPOF)

**Mejora Propuesta**:
```python
# shared/infrastructure/events/redis_pool.py

# ADD: Redis Cluster support
from redis.asyncio.cluster import RedisCluster

async def get_redis_cluster() -> RedisCluster:
    """For production with Redis Cluster."""
    global _redis_cluster
    if _redis_cluster is None:
        _redis_cluster = RedisCluster.from_url(
            REDIS_CLUSTER_URL,
            decode_responses=True,
        )
    return _redis_cluster
```

**docker-compose.cluster.yml**:
```yaml
services:
  redis-node-1:
    image: redis:7-alpine
    command: redis-server --cluster-enabled yes --cluster-config-file nodes.conf
    
  redis-node-2:
    image: redis:7-alpine
    command: redis-server --cluster-enabled yes --cluster-config-file nodes.conf
    
  redis-node-3:
    image: redis:7-alpine
    command: redis-server --cluster-enabled yes --cluster-config-file nodes.conf
```

---

### 3.2 REDIS-02: Implementar Cache Warming

**Estado Actual**: Cache on-demand (cold start lento)

```python
# rest_api/services/cache/warmer.py
class CacheWarmer:
    """Pre-warm caches on application startup."""
    
    async def warm_on_startup(self):
        """Called from lifespan."""
        logger.info("Starting cache warming...")
        
        async with asyncio.TaskGroup() as tg:
            # Warm product caches for active branches
            tg.create_task(self._warm_products())
            # Warm allergen caches
            tg.create_task(self._warm_allergens())
            # Warm sector assignments
            tg.create_task(self._warm_sectors())
        
        logger.info("Cache warming completed")
    
    async def _warm_products(self):
        branches = await self._get_active_branches()
        for branch in branches:
            key = get_branch_products_cache_key(branch.id, branch.tenant_id)
            menu = await self._build_menu(branch)
            await self.redis.setex(key, PRODUCT_CACHE_TTL, menu.json())
```

---

### 3.3 REDIS-03: Centralizar TTLs con Refresh Strategies

**Estado Actual**: TTLs definidos, pero sin refresh proactivo

```python
# shared/infrastructure/redis/constants.py

# ADD: TTL refresh strategies
class TTLStrategy:
    FIXED = "fixed"  # Expire after TTL, no refresh
    SLIDING = "sliding"  # Reset TTL on each access
    REFRESH_AHEAD = "refresh_ahead"  # Refresh before expiration

CACHE_STRATEGIES = {
    "product": TTLStrategy.REFRESH_AHEAD,  # Refresh 30s before expiration
    "session": TTLStrategy.SLIDING,  # Reset on each access
    "blacklist": TTLStrategy.FIXED,  # Strict expiration
}

# Implementación en CacheService
async def get_with_strategy(self, key: str, strategy: TTLStrategy):
    value = await self.redis.get(key)
    
    if strategy == TTLStrategy.SLIDING and value:
        # Reset TTL on access
        await self.redis.expire(key, self.ttl)
    
    elif strategy == TTLStrategy.REFRESH_AHEAD:
        ttl = await self.redis.ttl(key)
        if ttl < 30:  # Refresh if <30s remaining
            asyncio.create_task(self._refresh_cache(key))
    
    return value
```

---

### 3.4 REDIS-04: Implementar Dead Letter Queue Management

**Estado Actual**: DLQ definida pero sin consumidor

```python
# rest_api/services/events/dlq_processor.py
class DeadLetterProcessor:
    """Process messages from Dead Letter Queue for analysis/retry."""
    
    async def process_dlq(self, max_messages: int = 100):
        """Manual triggered DLQ processing."""
        messages = await self.redis.lrange(
            PREFIX_WEBHOOK_DEAD_LETTER, 0, max_messages - 1
        )
        
        for msg in messages:
            event = json.loads(msg)
            
            # Analyze failure reason
            if self._is_retryable(event):
                # Move back to retry queue
                await self._requeue(event)
            else:
                # Log for manual intervention
                logger.error("Unrecoverable DLQ message", event=event)
                await self._archive_to_s3(event)
        
        # Trim processed messages
        await self.redis.ltrim(PREFIX_WEBHOOK_DEAD_LETTER, max_messages, -1)
```

---

## 4. Mejoras de Testing

### 4.1 TEST-01: Implementar Property-Based Testing

**Estado Actual**: Tests unitarios y de integración

```python
# backend/tests/test_properties.py
from hypothesis import given, strategies as st

class TestProductProperties:
    @given(
        price_cents=st.integers(min_value=1, max_value=100_000_00),
        name=st.text(min_size=1, max_size=100),
    )
    def test_product_creation_properties(self, price_cents, name, db_session):
        """Property: Any valid product should serialize/deserialize correctly."""
        product = Product(
            name=name,
            price_cents=price_cents,
            tenant_id=1,
        )
        db_session.add(product)
        db_session.flush()
        
        # Property: Price should always be positive after save
        assert product.price_cents > 0
        
        # Property: Name should be preserved
        assert product.name == name.strip() or product.name == name
```

---

### 4.2 TEST-02: Implementar Contract Testing con Pact

**Para APIs entre servicios**:

```python
# backend/tests/contracts/test_pact_provider.py
from pact import Verifier

def test_websocket_gateway_contract():
    """Verify ws_gateway fulfills contract with Dashboard."""
    verifier = Verifier(provider='ws_gateway', provider_base_url='http://localhost:8001')
    
    output, _ = verifier.verify_pacts(
        './pacts/dashboard-ws_gateway.json',
        enable_pending=True,
    )
    assert output == 0
```

---

### 4.3 TEST-03: Añadir Mutation Testing

```toml
# pyproject.toml
[tool.mutmut]
paths_to_mutate = "rest_api/services/domain/"
runner = "pytest tests/"
tests_dir = "tests/"
```

**CI Integration**:
```yaml
# .github/workflows/mutation.yml
- name: Run Mutation Tests
  run: |
    mutmut run --paths-to-mutate rest_api/services/domain/
    mutmut results
```

---

### 4.4 TEST-04: Coverage Goals por Capa

| Capa | Coverage Actual | Target | Acción |
|------|-----------------|--------|--------|
| Domain Services | ~70% | 90% | Añadir edge cases |
| Repositories | ~60% | 85% | Mock database layer |
| Routers | ~50% | 70% | Integration tests |
| Utils | ~40% | 80% | Unit tests |

```yaml
# pytest.ini
[pytest]
addopts = --cov=rest_api --cov-report=html --cov-fail-under=75
```

---

## 5. Mejoras de Observabilidad

### 5.1 OBS-01: Distributed Tracing con OpenTelemetry

```python
# shared/infrastructure/telemetry.py
from opentelemetry import trace
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
from opentelemetry.instrumentation.redis import RedisInstrumentor
from opentelemetry.instrumentation.sqlalchemy import SQLAlchemyInstrumentor

def setup_telemetry(app: FastAPI):
    """Initialize distributed tracing."""
    
    # Auto-instrument FastAPI
    FastAPIInstrumentor.instrument_app(app)
    
    # Auto-instrument Redis
    RedisInstrumentor().instrument()
    
    # Auto-instrument SQLAlchemy
    SQLAlchemyInstrumentor().instrument(engine=engine)
    
    # Export to Jaeger/Tempo
    tracer_provider = TracerProvider()
    tracer_provider.add_span_processor(
        BatchSpanProcessor(JaegerExporter())
    )
    trace.set_tracer_provider(tracer_provider)
```

---

### 5.2 OBS-02: Structured Logging con Correlation IDs

```python
# shared/config/logging.py
import contextvars

request_id_var: contextvars.ContextVar[str] = contextvars.ContextVar('request_id', default='')

class CorrelationIdFilter(logging.Filter):
    def filter(self, record):
        record.request_id = request_id_var.get()
        return True

# Middleware para inyectar correlation ID
@app.middleware("http")
async def add_correlation_id(request: Request, call_next):
    request_id = request.headers.get("X-Request-ID", str(uuid4()))
    request_id_var.set(request_id)
    response = await call_next(request)
    response.headers["X-Request-ID"] = request_id
    return response
```

---

### 5.3 OBS-03: Error Tracking con Sentry

```python
# shared/config/sentry.py
import sentry_sdk
from sentry_sdk.integrations.fastapi import FastApiIntegration
from sentry_sdk.integrations.redis import RedisIntegration

def init_sentry():
    if settings.environment == "production":
        sentry_sdk.init(
            dsn=settings.sentry_dsn,
            environment=settings.environment,
            integrations=[
                FastApiIntegration(transaction_style="url"),
                RedisIntegration(),
            ],
            traces_sample_rate=0.1,  # 10% of transactions
            profiles_sample_rate=0.1,
        )
```

---

## 6. Mejoras de Performance

### 6.1 PERF-01: Database Connection Pooling Optimizado

```python
# shared/infrastructure/db.py

# MEJORA: Pool sizing basado en workers
from multiprocessing import cpu_count

def calculate_pool_size():
    """Formula: (2 * CPU cores) + disk spindles"""
    cores = cpu_count()
    return min(cores * 2 + 1, 20)  # Cap at 20

engine = create_engine(
    DATABASE_URL,
    pool_size=calculate_pool_size(),
    max_overflow=10,
    pool_pre_ping=True,  # Health check before use
    pool_recycle=3600,   # Recycle connections hourly
)
```

---

### 6.2 PERF-02: Query Optimization con Batch Loading

```python
# rest_api/services/domain/product_service.py

async def get_products_with_relations(self, ids: list[int]) -> list[ProductOutput]:
    """Batch load products with all relations in 3 queries max."""
    
    # Query 1: Products
    products = await self.repo.find_by_ids(ids)
    
    # Query 2: Allergens (batch)
    product_ids = [p.id for p in products]
    allergens_map = await self._batch_load_allergens(product_ids)
    
    # Query 3: Branch prices (batch)
    prices_map = await self._batch_load_prices(product_ids)
    
    # Assemble in memory
    return [
        self._to_output(p, allergens_map.get(p.id), prices_map.get(p.id))
        for p in products
    ]
```

---

### 6.3 PERF-03: Implementar GraphQL para Consultas Flexibles

**Para Dashboard con muchas variantes de consulta**:

```python
# rest_api/graphql/schema.py
import strawberry
from strawberry.fastapi import GraphQLRouter

@strawberry.type
class Product:
    id: int
    name: str
    price_cents: int
    
    @strawberry.field
    async def allergens(self) -> list["Allergen"]:
        # DataLoader prevents N+1
        return await allergen_loader.load(self.id)

@strawberry.type
class Query:
    @strawberry.field
    async def products(
        self, 
        branch_id: int,
        category_id: int | None = None,
        limit: int = 50,
    ) -> list[Product]:
        return await product_service.search(branch_id, category_id, limit)

schema = strawberry.Schema(query=Query)
graphql_app = GraphQLRouter(schema)
```

---

## 7. Mejoras de Seguridad

### 7.1 SEC-01: Implementar API Key Rotation

```python
# shared/security/api_keys.py
class APIKeyManager:
    """Manage API key lifecycle with rotation."""
    
    async def rotate_key(self, key_id: str) -> tuple[str, str]:
        """Rotate key, returning (new_key, transition_period_id)."""
        old_key = await self.get_key(key_id)
        new_key = secrets.token_urlsafe(32)
        
        # Both keys valid during transition (24h)
        await self.redis.setex(
            f"api_key:transition:{key_id}",
            86400,
            json.dumps({"old": old_key, "new": new_key})
        )
        
        return new_key, key_id
    
    async def validate(self, key: str) -> bool:
        """Validate key, accepting old key during transition."""
        # Check active keys
        if await self.redis.exists(f"api_key:active:{key}"):
            return True
        
        # Check transition keys
        # (implementation details)
        return False
```

---

### 7.2 SEC-02: Implementar Request Signing

```python
# shared/security/request_signing.py
import hmac
import hashlib

def sign_request(body: bytes, timestamp: int, secret: str) -> str:
    """HMAC-SHA256 request signing."""
    message = f"{timestamp}.{body.decode()}"
    return hmac.new(
        secret.encode(),
        message.encode(),
        hashlib.sha256
    ).hexdigest()

def verify_signature(
    body: bytes, 
    timestamp: int, 
    signature: str, 
    secret: str,
    max_age: int = 300,
) -> bool:
    """Verify request signature with replay protection."""
    # Check timestamp freshness
    now = int(time.time())
    if abs(now - timestamp) > max_age:
        return False
    
    expected = sign_request(body, timestamp, secret)
    return hmac.compare_digest(expected, signature)
```

---

### 7.3 SEC-03: Implementar Audit Log Seguro

```python
# shared/security/audit.py
class SecureAuditLog:
    """Tamper-evident audit logging."""
    
    async def log(self, event: AuditEvent):
        # Hash chain for tamper detection
        prev_hash = await self._get_last_hash()
        event.prev_hash = prev_hash
        event.hash = self._compute_hash(event)
        
        await self.store.append(event)
    
    def _compute_hash(self, event: AuditEvent) -> str:
        payload = f"{event.prev_hash}:{event.timestamp}:{event.action}:{event.data}"
        return hashlib.sha256(payload.encode()).hexdigest()
    
    async def verify_chain(self) -> bool:
        """Verify entire audit chain integrity."""
        events = await self.store.get_all()
        for i, event in enumerate(events[1:], 1):
            expected_prev = events[i-1].hash
            if event.prev_hash != expected_prev:
                return False
        return True
```

---

## 8. Mejoras de Developer Experience

### 8.1 DX-01: CLI para Operaciones Comunes

```python
# cli.py
import typer
from rich.console import Console

app = typer.Typer(help="Integrador CLI")
console = Console()

@app.command()
def seed(env: str = "development"):
    """Seed database with test data."""
    console.print(f"[green]Seeding {env} database...")
    # Implementation

@app.command()
def migrate(revision: str = "head"):
    """Run database migrations."""
    console.print(f"[blue]Migrating to {revision}...")
    # Implementation

@app.command()
def test_ws():
    """Test WebSocket connectivity."""
    console.print("[yellow]Testing WebSocket...")
    # Implementation

@app.command()
def cache_clear(pattern: str = "*"):
    """Clear Redis cache by pattern."""
    console.print(f"[red]Clearing cache: {pattern}")
    # Implementation

if __name__ == "__main__":
    app()
```

---

### 8.2 DX-02: Dev Container Configuration

```json
// .devcontainer/devcontainer.json
{
  "name": "Integrador Dev",
  "dockerComposeFile": ["../devOps/docker-compose.yml", "docker-compose.dev.yml"],
  "service": "devcontainer",
  "workspaceFolder": "/workspace",
  "customizations": {
    "vscode": {
      "extensions": [
        "ms-python.python",
        "ms-python.vscode-pylance",
        "bradlc.vscode-tailwindcss",
        "dbaeumer.vscode-eslint"
      ],
      "settings": {
        "python.defaultInterpreterPath": "/workspace/backend/.venv/bin/python"
      }
    }
  },
  "postCreateCommand": "pip install -r backend/requirements.txt && cd Dashboard && npm install"
}
```

---

### 8.3 DX-03: API Documentation Enhancement

```python
# rest_api/main.py

app = FastAPI(
    title="Integrador API",
    description="""
    ## Restaurant Management System API
    
    ### Modules
    - **Auth**: JWT-based authentication
    - **Admin**: Dashboard CRUD operations
    - **Kitchen**: Order processing
    - **Waiter**: Table management
    - **Diner**: Customer ordering
    
    ### Rate Limits
    - Public endpoints: 100/min
    - Authenticated: 30/min
    - Login: 5/min per email
    
    ### WebSocket Events
    See `/ws/docs` for real-time event documentation.
    """,
    version="2.0.0",
    docs_url="/api/docs",
    redoc_url="/api/redoc",
    openapi_tags=[
        {"name": "auth", "description": "Authentication operations"},
        {"name": "admin", "description": "Administrative operations"},
        {"name": "kitchen", "description": "Kitchen workflow"},
        {"name": "waiter", "description": "Waiter operations"},
        {"name": "diner", "description": "Customer ordering"},
    ],
)
```

---

## 9. Roadmap de Implementación

### Fase 1: Crítico (Febrero 2026)
| ID | Mejora | Esfuerzo | Impacto |
|----|--------|----------|---------|
| CRIT-01 | Thin Controllers Migration | 2 semanas | Alto |
| OBS-01 | Distributed Tracing | 3 días | Alto |
| TEST-04 | Coverage Goals | 1 semana | Medio |

### Fase 2: Arquitectura (Marzo 2026)
| ID | Mejora | Esfuerzo | Impacto |
|----|--------|----------|---------|
| REDIS-01 | Redis Cluster | 1 semana | Alto |
| REDIS-02 | Cache Warming | 3 días | Medio |
| ARCH-01 | CQRS for Reads | 2 semanas | Alto |

### Fase 3: Observabilidad (Abril 2026)
| ID | Mejora | Esfuerzo | Impacto |
|----|--------|----------|---------|
| OBS-02 | Correlation IDs | 2 días | Medio |
| OBS-03 | Sentry Integration | 1 día | Alto |
| CRIT-03 | Grafana Dashboards | 3 días | Alto |

### Fase 4: Performance (Mayo 2026)
| ID | Mejora | Esfuerzo | Impacto |
|----|--------|----------|---------|
| PERF-01 | Pool Optimization | 1 día | Medio |
| PERF-02 | Batch Loading | 1 semana | Alto |
| PERF-03 | GraphQL (opcional) | 2 semanas | Medio |

### Fase 5: Seguridad Avanzada (Junio 2026)
| ID | Mejora | Esfuerzo | Impacto |
|----|--------|----------|---------|
| SEC-01 | API Key Rotation | 3 días | Alto |
| SEC-02 | Request Signing | 2 días | Medio |
| SEC-03 | Audit Log | 1 semana | Alto |

---

## 📊 Métricas de Éxito

| Métrica | Actual | Target |
|---------|--------|--------|
| Clean Architecture Score | 7.75 | 9.0+ |
| FastAPI Score | 8.75 | 9.5+ |
| Test Coverage | ~65% | 85%+ |
| API Latency p99 | ~200ms | <100ms |
| WebSocket Capacity | 500 | 2000+ |
| MTTR (Mean Time To Recovery) | N/A | <5 min |
| Deployment Frequency | Manual | Daily CI/CD |

---

## 🔗 Referencias

- [Redis Best Practices Skill](.agent/skills/redis-best-practices/SKILL.md)
- [Knowledge Base Architecture Guidelines](~/.gemini/.../integrador_architecture_guidelines/)
- [Jan 2026 Audit Report](knowledge/backend/audits/jan_2026_audit_report.md)
- [CLAUDE.md](./CLAUDE.md)

---

*Documento generado: Febrero 2026*  
*Próxima revisión: Marzo 2026*
