# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

---

## Table of Contents

- [Project Overview](#project-overview)
- [Quick Start Commands](#quick-start-commands)
- [Architecture](#architecture)
- [Core Patterns](#core-patterns)
- [Test Users](#test-users)
- [Conventions](#conventions)
- [Security Configuration](#security-configuration)
- [Load Optimization](#load-optimization-400-users)
- [Infrastructure](#infrastructure)
- [Key Features](#key-features)
- [Documentation](#documentation)
- [IA-Native Governance Framework](#ia-native-governance-framework)
- [Common Issues](#common-issues)
- [QA Status](#qa-status-january-2026)
- [Key Architecture Modules](#key-architecture-modules)
- [WebSocket Gateway Utilities](#websocket-gateway-utilities)

---

## Project Overview

**Integrador** is a restaurant management system monorepo with four main components:

| Component | Port | Description |
|-----------|------|-------------|
| **Dashboard** | 5177 | Admin panel for multi-branch restaurant management (React 19 + Zustand) |
| **pwaMenu** | 5176 | Customer-facing shared menu PWA with collaborative ordering, i18n (es/en/pt) |
| **pwaWaiter** | 5178 | Waiter PWA for real-time table management with push notifications |
| **backend** | 8000 | FastAPI REST API (PostgreSQL, Redis, JWT) |
| **ws_gateway** | 8001 | WebSocket Gateway for real-time events (at project root) |

Each project has its own documentation:
- [Dashboard/README.md](Dashboard/README.md) - Dashboard admin panel
- [Dashboard/arquiDashboard.md](Dashboard/arquiDashboard.md) - Dashboard architecture
- [Dashboard/CLAUDE.md](Dashboard/CLAUDE.md)
- [pwaMenu/README.md](pwaMenu/README.md) - Customer menu PWA
- [pwaMenu/CLAUDE.md](pwaMenu/CLAUDE.md)
- [pwaWaiter/CLAUDE.md](pwaWaiter/CLAUDE.md)
- [backend/README.md](backend/README.md) - Backend REST API
- [backend/arquiBackend.md](backend/arquiBackend.md) - Backend architecture
- [backend/shared/README.md](backend/shared/README.md) - Shared modules
- [ws_gateway/README.md](ws_gateway/README.md) - WebSocket Gateway
- [ws_gateway/arquiws_gateway.md](ws_gateway/arquiws_gateway.md) - WebSocket Gateway architecture
- [devOps/README.md](devOps/README.md) - Infrastructure and startup scripts

---

## Quick Start Commands

```bash
# =============================================================================
# First-time setup (copy .env.example files)
# =============================================================================
cp backend/.env.example backend/.env                  # Backend config
cp Dashboard/.env.example Dashboard/.env              # Dashboard config
cp pwaMenu/.env.example pwaMenu/.env                  # pwaMenu config

# =============================================================================
# Backend (requires Docker Desktop running)
# =============================================================================
docker compose -f devOps/docker-compose.yml up -d    # Start PostgreSQL + Redis
cd backend && pip install -r requirements.txt         # Install Python deps
cd backend && python -m uvicorn rest_api.main:app --reload --port 8000      # REST API

# WS Gateway (from project root, requires PYTHONPATH)
export PYTHONPATH="$(pwd)/backend"                    # Unix/Mac
$env:PYTHONPATH = "$PWD\backend"                      # Windows PowerShell
python -m uvicorn ws_gateway.main:app --reload --port 8001

# Windows PowerShell: Start everything (run from backend directory)
cd backend && ..\devOps\start.ps1

# Unix/Mac: Start everything (run from backend directory)
cd backend && ../devOps/start.sh

# =============================================================================
# Frontend Development
# =============================================================================
# Dashboard
cd Dashboard && npm install      # Install deps (first time)
cd Dashboard && npm run dev      # Dev server (port 5177)
cd Dashboard && npm run lint     # ESLint
cd Dashboard && npm run build    # Production build

# pwaMenu
cd pwaMenu && npm install        # Install deps (first time)
cd pwaMenu && npm run dev        # Dev server (port 5176)
cd pwaMenu && npm run lint       # ESLint
cd pwaMenu && npm run build      # Production build

# pwaWaiter
cd pwaWaiter && npm install      # Install deps (first time)
cd pwaWaiter && npm run dev      # Dev server (port 5178)
cd pwaWaiter && npm run lint     # ESLint
cd pwaWaiter && npm run build    # Production build

# =============================================================================
# Testing
# =============================================================================
# Dashboard tests
cd Dashboard && npm run test                                  # Watch mode
cd Dashboard && npm test -- src/stores/branchStore.test.ts    # Single file
cd Dashboard && npm run test:coverage                         # Coverage report

# pwaMenu tests
cd pwaMenu && npm run test                                    # Watch mode
cd pwaMenu && npm test -- src/hooks/useDebounce.test.ts       # Single file
cd pwaMenu && npm run test:coverage                           # Coverage report

# pwaWaiter tests
cd pwaWaiter && npm run test                                  # Watch mode
cd pwaWaiter && npm run test:run                              # Single run

# Backend tests
cd backend && python -m pytest tests/ -v                      # All tests
cd backend && python -m pytest tests/test_auth.py -v          # Single file

# Type checking (all frontends)
npx tsc --noEmit
```

---

## Architecture

### Data Model

```
Tenant (Restaurant)
  ├── CookingMethod, FlavorProfile, TextureProfile, CuisineType (tenant-scoped catalogs)
  ├── IngredientGroup → Ingredient → SubIngredient (tenant-scoped)
  └── Branch (N)
        ├── Category (N) → Subcategory (N) → Product (N)
        ├── BranchSector (N) → Table (N) → TableSession → Diner (N)
        │                   → WaiterSectorAssignment (daily waiter assignments)
        │                   → Round → RoundItem → KitchenTicket
        ├── Check (table: app_check) → Charge → Allocation (FIFO) ← Payment
        └── ServiceCall

User ←→ UserBranchRole (M:N with Branch, roles: WAITER/KITCHEN/MANAGER/ADMIN)
Product ←→ BranchProduct (per-branch pricing in cents)
Product ←→ ProductAllergen (M:N with presence_type + risk_level)
Product ←→ ProductCookingMethod, ProductFlavor, ProductTexture (M:N with back_populates + AuditMixin)
Product ←→ RoundItem (1:N via round_items back_populates)
RoundItem ←→ KitchenTicketItem (1:N via kitchen_ticket_items back_populates)
Recipe ←→ RecipeAllergen (M:N) - Kitchen technical sheets, can link to Products
Allergen ←→ AllergenCrossReaction (self-referential M:N for cross-reactions)

Customer ←→ Diner (1:N via customer_id - links visits to registered customer)
         └── device_ids[], preferences, metrics, GDPR consent, AI personalization
Diner: device_id, device_fingerprint (cross-session tracking)
     └── implicit_preferences (JSON: allergens, dietary, cooking filters)

Key Constraints (Jan 2026 Refactoring):
  - UniqueConstraint: Category(branch_id, name), Subcategory(category_id, name)
  - UniqueConstraint: Ingredient(tenant_id, name), IngredientGroup(tenant_id, name)
  - UniqueConstraint: CookingMethod/FlavorProfile/TextureProfile/CuisineType(tenant_id, name)
  - UniqueConstraint: Round(table_session_id, idempotency_key)
  - CheckConstraint: Promotion(start_date <= end_date), price_cents >= 0
  - CheckConstraint: Payment/Allocation(amount_cents > 0), PromotionItem(quantity > 0)
  - Composite Indexes: Diner(session_id, customer_id), AuditLog(tenant_id, entity_type)
```

### Clean Architecture (Backend)

```
┌─────────────────────────────────────────────────────────┐
│                      ROUTERS                             │
│         (Thin controllers - HTTP concerns only)          │
└─────────────────────┬───────────────────────────────────┘
                      │
┌─────────────────────▼───────────────────────────────────┐
│                DOMAIN SERVICES                           │
│      (Business logic, orchestration, validation)         │
│      rest_api/services/domain/                           │
└─────────────────────┬───────────────────────────────────┘
                      │
┌─────────────────────▼───────────────────────────────────┐
│                  REPOSITORIES                            │
│         (Data access ONLY - no business logic)           │
│         rest_api/services/crud/repository.py             │
└─────────────────────┬───────────────────────────────────┘
                      │
┌─────────────────────▼───────────────────────────────────┐
│                    MODELS                                │
│              (SQLAlchemy entities)                       │
└─────────────────────────────────────────────────────────┘
```

**Usage:**
```python
# Router (thin - delegates to service)
@router.get("/categories")
def list_categories(db: Session = Depends(get_db), user: dict = Depends(current_user)):
    ctx = PermissionContext(user)
    service = CategoryService(db)
    return service.list_by_branch(ctx.tenant_id, branch_id)

# Service (business logic - uses repository)
class CategoryService(BranchScopedService[Category, CategoryOutput]):
    def list_by_branch(self, tenant_id: int, branch_id: int) -> list[CategoryOutput]:
        entities = self._repo.find_by_branch(branch_id, tenant_id)
        return [self.to_output(e) for e in entities]

# Repository (data access only)
class TenantRepository:
    def find_all(self, tenant_id: int, ...) -> Sequence[ModelT]:
        return self._session.scalars(query).all()
```

**Available Domain Services:**
- `CategoryService`, `SubcategoryService` - Catalog management
- `BranchService`, `SectorService`, `TableService` - Branch/table management
- `ProductService` - Full product CRUD with branch prices, allergens, ingredients
- `AllergenService` - Allergen CRUD with cross-reactions
- `StaffService` - User CRUD with branch roles (MANAGER restrictions)
- `PromotionService` - Promotion CRUD with branches and items

**Base Classes for New Services:**
- `BaseCRUDService[Model, Output]` - Standard CRUD with Repository
- `BranchScopedService[Model, Output]` - For branch-scoped entities

**Creating a New Domain Service:**
```python
# 1. Create service in rest_api/services/domain/my_entity_service.py
from rest_api.services.base_service import BranchScopedService
from rest_api.models import MyEntity
from shared.utils.admin_schemas import MyEntityOutput  # Clean Architecture: schemas in shared layer

class MyEntityService(BranchScopedService[MyEntity, MyEntityOutput]):
    def __init__(self, db: Session):
        super().__init__(
            db=db,
            model=MyEntity,
            output_schema=MyEntityOutput,
            entity_name="Mi Entidad",  # Spanish for error messages
        )

    # Override hooks for custom validation
    def _validate_create(self, data: dict, tenant_id: int) -> None:
        if not data.get("required_field"):
            raise ValidationError("Campo requerido", field="required_field")

    # Override for post-action side effects
    def _after_delete(self, entity_info: dict, user_id: int, user_email: str) -> None:
        publish_entity_deleted(...)

# 2. Export in rest_api/services/domain/__init__.py
# 3. Use in router (keep router thin!)
```

### Backend API Structure

```
/api/auth/login, /me, /refresh   # JWT authentication
/api/public/menu/{slug}          # Public menu (no auth)
/api/tables/{id}/session         # Create/get table session (numeric ID)
/api/tables/code/{code}/session  # Create/get session by table code (alphanumeric, e.g., "INT-01")

/api/diner/*                     # Diner operations (X-Table-Token auth)
  /register                      # Register diner with device_id
  /preferences                   # PATCH: Sync implicit preferences (Fase 2)
  /device/{id}/history           # GET: Visit history for device (Fase 1)
  /device/{id}/preferences       # GET: Saved preferences for device (Fase 2)
/api/customer/*                  # Customer loyalty (X-Table-Token auth, Fase 4)
  /register                      # POST: Create customer with opt-in consent
  /recognize                     # GET: Check if device linked to customer
  /me                            # GET/PATCH: Customer profile
  /suggestions                   # GET: Personalized favorites and recommendations
/api/kitchen/*                   # Kitchen operations (JWT + KITCHEN role)
/api/recipes/*                   # Recipe CRUD (JWT + KITCHEN/MANAGER/ADMIN)
/api/billing/*                   # Payment operations
/api/waiter/*                    # Waiter operations (JWT + WAITER role)
  /tables?branch_id={id}         # Tables filtered by branch AND assigned sectors
  /branches/{id}/menu            # Compact menu for Comanda Rápida (no images)
  /sessions/{id}/rounds          # Submit round from waiter (Comanda Rápida)
/api/admin/*                     # Dashboard CRUD (JWT + role-based)
  # List endpoints support pagination: ?limit=50&offset=0
  /products?limit=100&offset=0   # Products (max 500)
  /staff?limit=50&offset=0       # Staff (max 200)
  /ingredients?limit=100&offset=0 # Ingredients (max 500)
  /promotions?limit=50&offset=0  # Promotions (max 200)
```

### WebSocket Events (port 8001)

```
/ws/waiter?token=JWT    # Waiter notifications (sector-targeted)
/ws/kitchen?token=JWT   # Kitchen notifications
/ws/diner?table_token=  # Diner real-time updates
/ws/admin?token=JWT     # Dashboard admin notifications

Events:
  # Round lifecycle
  ROUND_PENDING, ROUND_SUBMITTED, ROUND_IN_KITCHEN, ROUND_READY, ROUND_SERVED, ROUND_CANCELED
  # Service calls
  SERVICE_CALL_CREATED, SERVICE_CALL_ACKED, SERVICE_CALL_CLOSED
  # Billing
  CHECK_REQUESTED, CHECK_PAID, PAYMENT_APPROVED, PAYMENT_REJECTED, PAYMENT_FAILED
  # Tables
  TABLE_SESSION_STARTED, TABLE_CLEARED, TABLE_STATUS_CHANGED
  # Kitchen tickets
  TICKET_IN_PROGRESS, TICKET_READY, TICKET_DELIVERED
  # Admin CRUD
  ENTITY_CREATED, ENTITY_UPDATED, ENTITY_DELETED, CASCADE_DELETE

Heartbeat: {"type":"ping"} → {"type":"pong"} (30s interval, 10s timeout)

Close codes:
  1000 - Normal closure
  1001 - Going away
  1008 - Policy violation
  1009 - Message too large (>64KB)
  4001 - Authentication failed (invalid/expired token)
  4003 - Forbidden (invalid origin or insufficient role)
  4029 - Rate limited (LOAD-LEVEL2: too many messages per second)
```

**Sector-Based Waiter Notifications:**
- Events with `sector_id` → sent only to waiters assigned to that sector
- Events without `sector_id` → sent to all waiters in branch
- ADMIN/MANAGER always receive all branch events

**Round Event Routing:**
| Event | Admin | Kitchen | Waiters | Diners |
|-------|-------|---------|---------|--------|
| `ROUND_PENDING` | ✅ | ❌ | ✅ | ❌ |
| `ROUND_SUBMITTED` | ✅ | ✅ | ✅ | ❌ |
| `ROUND_IN_KITCHEN` | ✅ | ✅ | ✅ | ✅ |
| `ROUND_READY` | ✅ | ✅ | ✅ | ✅ |
| `ROUND_SERVED` | ✅ | ✅ | ✅ | ✅ |
| `ROUND_CANCELED` | ✅ | ✅ | ✅ | ✅ |

### WebSocket Gateway Architecture

The ws_gateway uses a component-based architecture organized by domain responsibility:

```
ws_gateway/
├── main.py                    # FastAPI app, lifespan, endpoints
├── connection_manager.py      # Thin orchestrator (composes core/connection modules)
├── redis_subscriber.py        # Thin orchestrator (composes core/subscriber modules)
├── core/                      # ARCH-MODULAR: Extracted from monolithic files
│   ├── __init__.py            # Re-exports all modules
│   ├── connection/            # Connection management (from connection_manager.py)
│   │   ├── lifecycle.py       # ConnectionLifecycle: connect/disconnect
│   │   ├── broadcaster.py     # ConnectionBroadcaster: send/broadcast methods
│   │   ├── cleanup.py         # ConnectionCleanup: stale/dead cleanup
│   │   └── stats.py           # ConnectionStats: statistics aggregation
│   └── subscriber/            # Redis subscriber (from redis_subscriber.py)
│       ├── drop_tracker.py    # EventDropRateTracker: drop rate alerts
│       ├── validator.py       # Event schema validation
│       └── processor.py       # Event batch processing
└── components/                # ARCH-REFACTOR-01: Modular organization
    ├── __init__.py            # Re-exports all public symbols (backward compat)
    ├── core/                  # Foundational components
    │   ├── constants.py       # WSCloseCode, WSConstants, message constants
    │   ├── context.py         # WebSocketContext for audit logging
    │   └── dependencies.py    # FastAPI DI container (singletons)
    ├── connection/            # Connection lifecycle management
    │   ├── index.py           # ConnectionIndex (indices + mappings)
    │   ├── locks.py           # LockManager (sharded locks)
    │   ├── lock_sequence.py   # LockSequence (deadlock prevention)
    │   ├── heartbeat.py       # HeartbeatTracker
    │   └── rate_limiter.py    # WebSocketRateLimiter
    ├── events/                # Event handling
    │   ├── types.py           # WebSocketEvent, EventType
    │   └── router.py          # EventRouter (validation + routing)
    ├── broadcast/             # Message broadcasting
    │   ├── router.py          # BroadcastRouter (Strategy + Observer)
    │   └── tenant_filter.py   # TenantFilter (multi-tenant isolation)
    ├── auth/                  # Authentication
    │   └── strategies.py      # JWT, TableToken, Composite strategies
    ├── endpoints/             # WebSocket endpoints
    │   ├── base.py            # WebSocketEndpointBase, JWTWebSocketEndpoint
    │   ├── mixins.py          # SRP mixins (validation, heartbeat, etc.)
    │   └── handlers.py        # Waiter, Kitchen, Admin, Diner endpoints
    ├── resilience/            # Fault tolerance
    │   ├── circuit_breaker.py # CircuitBreaker for Redis
    │   └── retry.py           # RetryConfig with jitter
    ├── metrics/               # Observability
    │   ├── collector.py       # MetricsCollector
    │   └── prometheus.py      # PrometheusFormatter
    └── data/                  # Data access
        └── sector_repository.py # SectorAssignmentRepository + cache
```

**Modular Architecture (ARCH-MODULAR):**
- `connection_manager.py` (987→463 lines): Thin orchestrator using composition
- `redis_subscriber.py` (666→326 lines): Thin orchestrator using composition
- `core/connection/`: Extracted lifecycle, broadcaster, cleanup, stats
- `core/subscriber/`: Extracted drop tracker, validator, processor

**Import Paths (both work for backward compatibility):**
```python
# NEW (recommended - explicit module)
from ws_gateway.components.core.constants import WSCloseCode
from ws_gateway.components.broadcast.router import BroadcastRouter

# OLD (still works via re-exports)
from ws_gateway.components import WSCloseCode, BroadcastRouter
```

**Key Components:**

| Component | Pattern | Purpose |
|-----------|---------|---------|
| `ConnectionIndex` | Value Object | Manages all connection indices and reverse mappings |
| `LockSequence` | Guard | Enforces lock acquisition order to prevent deadlocks |
| `EventRouter` | Router/Strategy | Separates event validation from routing logic |
| `WebSocketEndpointBase` | Template Method | Base class with lifecycle, uses mixins |
| `BroadcastRouter` | Strategy + Observer | Configurable batch/adaptive broadcast with Observer for metrics |
| `TenantFilter` | Service | Centralized multi-tenant connection filtering |
| `AuthStrategy` | Protocol | Pluggable JWT/TableToken authentication |
| `SectorCache` | Cache | TTL-based caching for sector assignments |
| `RetryConfig` | Config | Exponential backoff with jitter (DecorrelatedJitter) |
| `ConnectionManagerDependencies` | DI | Testable dependency injection container |

**Mixins for WebSocket Endpoints (ARCH-AUDIT-04):**
| Mixin | Purpose |
|-------|---------|
| `MessageValidationMixin` | Message size and rate limit validation |
| `OriginValidationMixin` | WebSocket origin header validation |
| `JWTRevalidationMixin` | Periodic JWT token revalidation |
| `HeartbeatMixin` | Heartbeat recording |
| `ConnectionLifecycleMixin` | Connection lifecycle logging |

**Prometheus Metrics Endpoint:**
```bash
# Scrape metrics for monitoring
curl http://localhost:8001/ws/metrics

# Example metrics:
wsgateway_connections_total 42
wsgateway_broadcasts_total 1234
wsgateway_connections_rejected_total{reason="auth"} 5
```

**Authentication Strategies:**
```python
# Pluggable auth via Strategy pattern
from ws_gateway.components.auth_strategies import (
    JWTAuthStrategy,
    TableTokenAuthStrategy,
    CompositeAuthStrategy,
)

# Waiter/Kitchen/Admin use JWT
waiter_auth = JWTAuthStrategy(required_roles=["WAITER", "MANAGER", "ADMIN"])

# Diners use table tokens
diner_auth = TableTokenAuthStrategy()

# Test with NullAuthStrategy (always succeeds)
from ws_gateway.components.auth_strategies import NullAuthStrategy
test_auth = NullAuthStrategy(mock_data={"sub": "1", "tenant_id": 1})
```

**Observer Pattern for Broadcast Metrics (MED-02 FIX):**
```python
# BroadcastRouter supports Observer pattern for decoupled metrics collection
from ws_gateway.components.broadcast_router import (
    BroadcastRouter,
    BroadcastObserver,
    MetricsObserverAdapter,
)

# Implement custom observer
class MyMetricsObserver:
    def on_broadcast_complete(self, sent: int, failed: int, context: str) -> None:
        statsd.increment("broadcasts.total")
        statsd.increment("broadcasts.failed", failed)

    def on_broadcast_rate_limited(self, context: str) -> None:
        statsd.increment("broadcasts.rate_limited")

# Register observer
router = BroadcastRouter(metrics_collector=metrics)
router.add_observer(MyMetricsObserver())

# Or use built-in adapter for MetricsCollector
adapter = MetricsObserverAdapter(metrics_collector)
router.add_observer(adapter)

# Observers are notified after each broadcast without coupling
```

**Dependency Injection for Testing:**
```python
from ws_gateway.components.dependencies import (
    ConnectionManagerDependencies,
    reset_singletons,
)

# Production: uses singleton instances
deps = ConnectionManagerDependencies()
manager = ConnectionManager(deps=deps)

# Testing: inject mocks
mock_deps = ConnectionManagerDependencies(
    metrics=MockMetricsCollector(),
    rate_limiter=MockRateLimiter(),
)
manager = ConnectionManager(deps=mock_deps)

# Test cleanup
reset_singletons()  # Clear all cached singletons
```

**Retry with Jitter (Redis reconnection):**
```python
from ws_gateway.components.retry_utils import (
    calculate_delay_with_jitter,
    create_redis_retry_config,
    DecorrelatedJitter,
)

# Prevents thundering herd on Redis reconnection
config = create_redis_retry_config()  # base=1s, max=60s, max_attempts=10
delay = calculate_delay_with_jitter(attempt=3, config=config)
# Returns: ~8s ± jitter (not exactly 8s like naive exponential)
```

---

## Core Patterns

### Critical Zustand Pattern (React 19)

All frontends enforce this pattern to avoid infinite re-renders:

```typescript
// CORRECT: Use selectors
const items = useStore(selectItems)
const addItem = useStore((s) => s.addItem)

// WRONG: Never destructure (causes infinite loops)
// const { items } = useStore()

// CRITICAL: Stable references for fallback arrays
const EMPTY_ARRAY: number[] = []
export const selectBranchIds = (state: State) => state.user?.branch_ids ?? EMPTY_ARRAY

// CRITICAL: Memoize filtered selectors
const pendingRoundsCache = { tables: null, result: EMPTY_TABLES }
export const selectTablesWithPendingRounds = (state: TablesState) => {
  if (state.tables === pendingRoundsCache.tables) return pendingRoundsCache.result
  const filtered = state.tables.filter((t) => t.open_rounds > 0)
  pendingRoundsCache.tables = state.tables
  pendingRoundsCache.result = filtered.length > 0 ? filtered : EMPTY_TABLES
  return pendingRoundsCache.result
}
```

### Backend Patterns

> **CLEAN ARCHITECTURE**: For new features, use Domain Services (`rest_api/services/domain/`).
> See the "Clean Architecture (Backend)" section above for the recommended pattern.
> CRUDFactory is deprecated - use `CategoryService`, `BranchService`, etc. instead.

```python
# PREFERRED: Domain Services (Clean Architecture)
from rest_api.services.domain import CategoryService
service = CategoryService(db)
categories = service.list_by_branch(tenant_id, branch_id)

# User context from JWT (current_user dependency)
user_id = int(user["sub"])       # CORRECT: "sub" contains user ID
user_email = user.get("email", "")
tenant_id = user["tenant_id"]
branch_ids = user["branch_ids"]
roles = user["roles"]

# Safe commit with automatic rollback
from shared.infrastructure.db import safe_commit
db.add(entity)
safe_commit(db)

# ARCH-OPP-03: Health Check Decorator with timeout protection
from shared.utils.health import health_check_with_timeout, aggregate_health_checks
@health_check_with_timeout(timeout=3.0, component="redis")
async def check_redis_health():
    await redis.ping()
    return {"pool_size": 10}  # Optional details
# Returns: HealthCheckResult(status=HEALTHY, component="redis", latency_ms=5.2)
# On timeout: HealthCheckResult(status=UNHEALTHY, error="timeout after 3.0s")

# ARCH-OPP-06: Repository Pattern for type-safe data access
from rest_api.services.crud import TenantRepository, BranchRepository, Specification
# Tenant-scoped repository (auto-filters by tenant_id)
product_repo = TenantRepository(Product, db)
products = product_repo.find_all(tenant_id=1, options=[selectinload(Product.allergens)])
product = product_repo.find_by_id(42, tenant_id=1)
# Branch-scoped repository (auto-filters by branch_id + tenant_id)
table_repo = BranchRepository(Table, db)
tables = table_repo.find_by_branch(branch_id=5, tenant_id=1)

# Async Redis pool (singleton, don't close manually)
# Events package is modular - import from package
from shared.infrastructure.events import get_redis_pool, publish_event, Event
# Or import specific modules:
from shared.infrastructure.events.redis_pool import get_redis_pool
from shared.infrastructure.events.publisher import publish_event
redis = await get_redis_pool()
await publish_event(redis, channel, Event(type="TEST", tenant_id=1, branch_id=1))

# Sync Redis pool for blocking operations (rate limiting, token blacklist)
from shared.infrastructure.events import get_redis_sync_client
client = get_redis_sync_client()  # Returns client from pool, thread-safe

# Eager loading to avoid N+1 (CRIT-02 FIX)
from sqlalchemy.orm import selectinload, joinedload
rounds = db.execute(
    select(Round).options(
        selectinload(Round.items).joinedload(RoundItem.product)
    )
).scalars().unique().all()

# CRIT-02: Kitchen tickets with full eager loading chain
ticket = db.scalar(
    select(KitchenTicket)
    .options(
        selectinload(KitchenTicket.items)
        .joinedload(KitchenTicketItem.round_item)
        .joinedload(RoundItem.product),
    )
    .where(KitchenTicket.id == ticket_id)
)

# PERF-01: Promotions with eager loading (prevents 2*N queries)
promotions = db.execute(
    select(Promotion).options(
        selectinload(Promotion.branches),
        selectinload(Promotion.items),
    ).where(Promotion.tenant_id == tenant_id)
).scalars().all()

# Race condition prevention
locked = db.scalar(select(Entity).where(...).with_for_update())

# SQLAlchemy boolean comparison (HIGH-DEEP-04 FIX)
# Use .is_(True) instead of == True for proper SQL generation
# WRONG: .where(Model.is_active == True)  # Creates "= 1" not "IS TRUE"
# CORRECT:
.where(Model.is_active.is_(True))
.where(Model.is_active.is_(False))
.where(Model.is_active.is_not(None))

# Fail-closed security pattern (CRIT-02 FIX)
# On Redis errors, deny access rather than allow
async def is_token_blacklisted(token_jti: str) -> bool:
    try:
        redis = await get_redis_pool()
        return await redis.exists(f"token_blacklist:{token_jti}") > 0
    except Exception:
        logger.error("Redis error - failing closed")
        return True  # Treat as blacklisted (fail closed)

# Thread-safe singleton initialization (CRIT-03, CRIT-WS-02 FIX)
import threading
_client = None
_lock = threading.Lock()

def _get_sync_client():
    global _client
    if _client is None:
        with _lock:
            if _client is None:  # Double-check inside lock
                _client = create_client()
    return _client

# Thread-safe state transitions (CRIT-DEEP-01 FIX)
# Internal methods that modify state must document lock requirements
class CircuitBreaker:
    def _transition_to_internal(self, new_state: CircuitState) -> None:
        """MUST be called with lock held - internal method only."""
        self._state = new_state  # Modifies state
        # ... other state changes

    def record_failure(self, exception: Exception) -> None:
        with self._sync_lock:  # Caller holds lock
            self._failure_count += 1
            if self._failure_count >= self._threshold:
                self._transition_to_internal(CircuitState.OPEN)  # Safe: lock held

    def get_stats(self) -> dict:
        """MED-DEEP-01 FIX: Stats must also use lock for consistent snapshot."""
        with self._sync_lock:
            return {"state": self._state.value, "failures": self._failure_count}

# Two-phase dict cleanup pattern (HIGH-WS-04, MED-DEEP-06 FIX)
# Prevents "dictionary changed size during iteration" errors
async def cleanup_stale(self) -> int:
    # Phase 1: Take snapshot for safe iteration
    async with self._lock:
        items_snapshot = list(self._data.items())
    # Phase 2: Identify entries to clean from snapshot
    to_remove = [key for key, value in items_snapshot if should_remove(value)]
    # Phase 3: Apply changes with double-check (under lock)
    async with self._lock:
        for key in to_remove:
            if key in self._data:  # Double-check before delete
                del self._data[key]
    return len(to_remove)

# Race-safe tenant filtering (CRIT-DEEP-02 FIX)
# Filter INSIDE lock to prevent race condition where connections change mid-filter
async def send_to_branch(self, branch_id, payload, tenant_id=None):
    branch_lock = await self._lock_manager.get_branch_lock(branch_id)
    async with branch_lock:
        connections = list(self._by_branch.get(branch_id, []))
        # Filter INSIDE lock - connections may change after lock release
        connections = self._filter_by_tenant(connections, tenant_id)
    return await self._broadcast_to_connections(connections, payload)

# Immutable value objects with deep copy (CRIT-DEEP-03 FIX)
# Protects nested dicts from external mutation
import copy
from dataclasses import dataclass, field
@dataclass(frozen=True, slots=True)
class WebSocketEvent:
    raw_data: dict = field(default_factory=dict, repr=False)

    @classmethod
    def from_dict(cls, data: dict):
        return cls(
            # Deep copy ALL nested dicts to ensure true immutability
            entity=copy.deepcopy(data.get("entity")),
            raw_data=copy.deepcopy(data),
        )

    def to_dict(self):
        return copy.deepcopy(self.raw_data)  # Return copy, not reference

# O(1) bounded collections with deque (HIGH-DEEP-02 FIX)
# Auto-evicts oldest when full, no manual cleanup needed
from collections import deque
MAX_TIMESTAMPS = 20  # bounded size
timestamps: deque[float] = deque(maxlen=MAX_TIMESTAMPS)
timestamps.append(time.time())  # O(1), auto-evicts if at maxlen

# Public methods for internal metrics (HIGH-DEEP-01 FIX)
# Never expose _private attributes; provide public methods instead
class ConnectionManager:
    def __init__(self):
        self._metrics = MetricsCollector()  # Private

    def record_rate_limit_rejection(self) -> None:
        """Public method - don't let callers access _metrics directly."""
        self._metrics.increment_connection_rejected_rate_limit_sync()

# Sync wrapper for async in running loop (CRIT-01 FIX)
def sync_wrapper():
    import concurrent.futures
    loop = asyncio.get_event_loop()
    if loop.is_running():
        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
            future = pool.submit(asyncio.run, async_func())
            return future.result(timeout=5.0)
    return loop.run_until_complete(async_func())

# Input validation utilities
from shared.utils.validators import validate_image_url, escape_like_pattern, validate_quantity
validate_image_url(url)           # SSRF/XSS prevention for image URLs
escape_like_pattern(search_term)  # Escape % and _ in LIKE patterns
validate_quantity(qty, min=1, max=99)  # Range validation

# Centralized exceptions with auto-logging
from shared.utils.exceptions import NotFoundError, ForbiddenError, ValidationError
raise NotFoundError("Producto", product_id, tenant_id=tenant_id)  # 404 + logs context
raise ForbiddenError("acceder a esta sucursal", branch_id=branch_id)  # 403
raise ValidationError("El precio debe ser positivo", field="price")  # 400

# Centralized constants
from shared.config.constants import Roles, RoundStatus, MANAGEMENT_ROLES
if Roles.ADMIN in user["roles"] or any(r in MANAGEMENT_ROLES for r in user["roles"]):
    ...
if round.status == RoundStatus.PENDING:
    ...

# HIGH-07 FIX: Status validation functions
from shared.config.constants import (
    TicketStatus, TicketItemStatus, ServiceCallStatus,
    validate_round_status, validate_ticket_status,
    validate_round_transition, get_allowed_round_transitions,
)
if not validate_ticket_status(new_status):
    raise HTTPException(status_code=400, detail=f"Invalid status: {new_status}")
allowed = get_allowed_round_transitions(current_status, user["roles"])
```

### Design Patterns (Backend Architecture Jan-23)

**6 new design patterns implemented to reduce code duplication and improve maintainability:**

```python
# =============================================================================
# 1. Permission Strategy Pattern - Eliminates 40+ role checking if/elif blocks
# =============================================================================
from rest_api.services.permissions import PermissionContext, Action

# Use in routers
ctx = PermissionContext(user)
ctx.require_management()  # Raises ForbiddenError if not ADMIN/MANAGER
ctx.require_branch_access(branch_id)  # Checks branch access
if ctx.can(Action.CREATE, "Product", branch_id=5):
    ...

# Available checks
ctx.is_admin          # bool
ctx.is_management     # bool (ADMIN or MANAGER)
ctx.user_id           # int
ctx.tenant_id         # int
ctx.branch_ids        # list[int]
ctx.can_create(entity_type, branch_id)
ctx.can_update(entity)
ctx.can_delete(entity)

# =============================================================================
# 2. Repository Pattern - Centralizes queries with eager loading
# =============================================================================
from rest_api.repositories import ProductRepository, get_product_repository

repo = get_product_repository(db)
products = repo.find_all(tenant_id, filters=ProductFilters(category_id=5))
product = repo.find_by_id(123, tenant_id)
# Guaranteed eager loading - no N+1 queries

# =============================================================================
# 4. Cascade Delete Service - Preserves audit trail on delete (CRIT-01 FIX)
# =============================================================================
from rest_api.services.crud import cascade_soft_delete, cascade_restore

# CRIT-01 FIX: Cascade relationships defined in CASCADE_RELATIONSHIPS dict
affected = cascade_soft_delete(db, product, user_id, user_email)
# Returns: [{"type": "ProductAllergen", "ids": [1,2,3]}, ...]
# Soft-deletes all children to preserve audit trail

# Restore with cascade
cascade_restore(db, product, user_id, user_email)
# Restores product + all previously deleted children

# =============================================================================
# Standardized Pagination
# =============================================================================
from rest_api.routers._common.pagination import Pagination, get_pagination

@router.get("/products")
def list_products(pagination: Pagination = Depends(get_pagination)):
    query = query.offset(pagination.offset).limit(pagination.limit)
    return {"items": items, "pagination": pagination.to_dict(total=count)}
```

### Frontend WebSocket Pattern

```typescript
// Use ref pattern to avoid listener accumulation
const handleEventRef = useRef(handleEvent)
useEffect(() => { handleEventRef.current = handleEvent })

useEffect(() => {
  const unsubscribe = ws.on('*', (e) => handleEventRef.current(e))
  return unsubscribe
}, [])  // Empty deps - subscribe once
```

### Dashboard WebSocket Resilience (QA-AUDIT Jan 2026)

**Non-Recoverable Close Codes:**
```typescript
// websocket.ts - Don't retry on permanent auth errors
const NON_RECOVERABLE_CLOSE_CODES = new Set([
  4001, // AUTH_FAILED - needs re-login
  4003, // FORBIDDEN - insufficient role
])

// In onclose handler:
if (NON_RECOVERABLE_CLOSE_CODES.has(event.code)) {
  this.onMaxReconnectReached?.()  // Notify UI
  return  // Don't schedule reconnect
}
```

**Memory Leak Prevention:**
```typescript
// Clean up empty Sets when unsubscribing
return () => {
  const listeners = this.listeners.get(eventType)
  listeners?.delete(callback)
  if (listeners?.size === 0) {
    this.listeners.delete(eventType)  // Prevent memory leak
  }
}
```

### TableStore Event Handling (QA-AUDIT Jan 2026)

**Timeout Tracking Pattern:**
```typescript
// Track timeouts per entity to prevent multiple pending timeouts
const blinkTimeouts = new Map<string, ReturnType<typeof setTimeout>>()

const scheduleBinkClear = (tableId: string) => {
  // Clear existing timeout for this table
  const existing = blinkTimeouts.get(tableId)
  if (existing) clearTimeout(existing)

  // Schedule new timeout
  const timeoutId = setTimeout(() => {
    blinkTimeouts.delete(tableId)
    // ... update state
  }, 1500)
  blinkTimeouts.set(tableId, timeoutId)
}
```

**Debounce API Calls:**
```typescript
// Prevent duplicate API calls with debounce
const pendingFetches = new Map<string, ReturnType<typeof setTimeout>>()

case 'TABLE_STATUS_CHANGED':
  const existing = pendingFetches.get(tableId)
  if (existing) clearTimeout(existing)

  const timeout = setTimeout(() => {
    pendingFetches.delete(tableId)
    tableAPI.get(event.table_id).then(/* update state */)
  }, 100)  // 100ms debounce
  pendingFetches.set(tableId, timeout)
```

**Event Validation:**
```typescript
// Validate table_id before processing
if (event.table_id === undefined || event.table_id === null) {
  return  // Skip events without table_id
}
const tableId = String(event.table_id)
if (tableId === 'undefined' || tableId === 'null' || tableId === '') {
  return  // Skip invalid string conversions
}
```

### Kitchen/Orders Role Verification

```typescript
// Kitchen.tsx - Verify role access
const userRoles = useAuthStore(selectUserRoles)
const canAccessKitchen = userRoles.includes('KITCHEN') ||
                         userRoles.includes('ADMIN') ||
                         userRoles.includes('MANAGER')

if (!canAccessKitchen) {
  return <AccessDeniedPage />
}
```

### Logout Infinite Loop Prevention (CRIT-FIX)

**When this happens:** If user's JWT is expired and the logout endpoint returns 401, the API client's automatic retry-on-401 logic (which calls `onTokenExpired` → `logout()`) triggers another logout request, creating an infinite loop.

**Affected frontends:** Dashboard (`api.ts`), pwaWaiter (`api.ts`)

```typescript
// In api.ts - authAPI.logout() must disable retry on 401
// Otherwise: expired token → 401 → onTokenExpired → logout() → 401 → infinite loop
async logout(): Promise<void> {
  try {
    // Pass false to disable retry on 401
    await fetchAPI('/api/auth/logout', { method: 'POST' }, false)
  } catch {
    // Ignore errors - token might already be invalid
  } finally {
    setAuthToken(null)
  }
}
```

### Backend WebSocket Patterns

```python
# LOAD-LEVEL2: Sharded locks reduce contention for high concurrency
class ConnectionManager:
    def __init__(self):
        self._global_lock = asyncio.Lock()
        self._branch_locks: dict[int, asyncio.Lock] = defaultdict(asyncio.Lock)
        self._user_locks: dict[int, asyncio.Lock] = defaultdict(asyncio.Lock)
        self._rate_limiter = WebSocketRateLimiter(
            max_messages=settings.ws_message_rate_limit,  # 20/s
            window_seconds=settings.ws_message_rate_window,
        )
        self._total_connections = 0  # Global connection counter

    # LOAD-LEVEL2: Use branch-specific lock to reduce contention
    async def register_waiter(self, ws, user_id, branch_id, ...):
        branch_lock = self._branch_locks[branch_id]
        async with branch_lock:
            # Only locks this branch, other branches unblocked
            ...

    # LOAD-LEVEL2: Parallel broadcast with batching
    async def _broadcast_to_connections(self, connections, payload, context):
        batch_size = settings.ws_broadcast_batch_size  # 50
        for i in range(0, len(connections), batch_size):
            batch = connections[i:i + batch_size]
            await asyncio.gather(
                *[self._send_to_connection(ws, payload) for ws in batch],
                return_exceptions=True,
            )

# CRIT-WS-01 FIX: Periodic JWT revalidation for long-lived connections
JWT_REVALIDATION_INTERVAL = 300.0  # 5 minutes
is_valid, last_jwt_revalidation = await revalidate_jwt_if_needed(token, last_jwt_revalidation)
if not is_valid:
    await websocket.close(code=4001, reason="Token expired or revoked")
    break

# LOAD-LEVEL2: Rate limiting per connection
if not await manager._rate_limiter.is_allowed(websocket):
    await websocket.close(code=4029, reason="Rate limit exceeded")
    break
```

### Async Hook Mount Guard (auditoria36 MENU-HOOK-CRIT-01)

```typescript
// Prevent setState after unmount in async operations
useEffect(() => {
  let isMounted = true

  fetchData().then(data => {
    if (!isMounted) return  // Skip if unmounted
    setData(data)
  })

  return () => { isMounted = false }
}, [])
```

### IndexedDB Timeout Pattern (auditoria36 WAITER-SVC-MED-02)

```typescript
// Wrap IndexedDB operations with timeout (30s) to prevent hangs
const IDB_TIMEOUT_MS = 30000

function withTimeout<T>(promise: Promise<T>, ms: number, op: string): Promise<T> {
  return new Promise((resolve, reject) => {
    const timeoutId = setTimeout(() => reject(new Error(`${op} timed out`)), ms)
    promise
      .then((r) => { clearTimeout(timeoutId); resolve(r) })
      .catch((e) => { clearTimeout(timeoutId); reject(e) })
  })
}
```

### Memory Leak Prevention in Sets (auditoria36 WAITER-SVC-CRIT-03)

```typescript
// Add maximum size limit for caching Sets to prevent unbounded growth
const MAX_RECENT = 100
const recentNotifications = new Set<string>()

if (recentNotifications.size >= MAX_RECENT) {
  recentNotifications.clear()  // Prevent unbounded growth
}
recentNotifications.add(key)
setTimeout(() => recentNotifications.delete(key), 5000)
```

### BroadcastChannel Lifecycle (auditoria36 CRIT-29-04)

```typescript
// Export cleanup function for proper shutdown
let isChannelInitialized = false
let broadcastChannel: BroadcastChannel | null = null

export function closeBroadcastChannel(): void {
  if (broadcastChannel) {
    broadcastChannel.close()
    broadcastChannel = null
    isChannelInitialized = false
  }
}
// Call on logout/app unmount
```

---

## Test Users

| Email | Password | Role |
|-------|----------|------|
| admin@demo.com | admin123 | ADMIN |
| manager@demo.com | manager123 | MANAGER |
| kitchen@demo.com | kitchen123 | KITCHEN |
| waiter@demo.com | waiter123 | WAITER |
| ana@demo.com | ana123 | WAITER |
| alberto.cortez@demo.com | waiter123 | WAITER |

---

## Conventions

- **UI language**: Spanish
- **Code comments**: English
- **Theme**: Finexy Dashboard with orange (#f97316) accent
- **IDs**: `crypto.randomUUID()` in frontend, BigInteger in backend
- **Prices**: Stored as cents (e.g., $125.50 = 12550)
- **Logging**: Use centralized `utils/logger.ts`, never direct console.*
- **Naming**: Frontend camelCase, backend snake_case
- **SQL Reserved Words**: Avoid SQL reserved keywords for table names. Example: `Check` model uses `__tablename__ = "app_check"` (not "check")

---

## Security Configuration

### JWT Token Lifetimes

- **Access token**: 15 minutes (short-lived to reduce exposure window)
- **Refresh token**: 7 days
- **Table token**: 3 hours (CRIT-04 FIX: reduced from 8h to limit exposure)
- Configured in `backend/shared/config/settings.py`

### Token Refresh Strategy

| Frontend | Strategy | Interval |
|----------|----------|----------|
| pwaWaiter | Proactive | Every 14 min (`authStore.ts:19`) |
| Dashboard | Reactive | On 401 response (`api.ts:109-121`) |

### Token Blacklist

- Logout calls `revoke_all_user_tokens()` to invalidate all user sessions
- Blacklist stored in Redis with TTL matching token expiration
- Fail-closed pattern: Redis errors treat token as blacklisted

### Authentication Methods

| Context | Method | Header/Param |
|---------|--------|--------------|
| User auth (Dashboard, pwaWaiter) | JWT | `Authorization: Bearer {token}` |
| Table auth (pwaMenu diners) | Table Token (HMAC) | `X-Table-Token: {token}` |
| WebSocket | JWT/Table Token | Query param `?token=` or `?table_token=` |

### Security Middlewares (ataque1.md remediations)

The backend implements multiple security layers:

**1. CORS Middleware (CRIT-03 FIX)**
```python
# Production: Set ALLOWED_ORIGINS env var (comma-separated)
# Development: Uses default localhost ports
ALLOWED_METHODS = ["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"]
ALLOWED_HEADERS = ["Authorization", "Content-Type", "X-Table-Token", "X-Request-ID", ...]
```

**2. Security Headers Middleware (LOW-02, HIGH-MID-01 FIX)**
```python
# Added to all responses:
X-Content-Type-Options: nosniff      # Prevent MIME sniffing
X-Frame-Options: DENY                 # Prevent clickjacking
X-XSS-Protection: 1; mode=block       # Legacy XSS protection
Referrer-Policy: strict-origin-when-cross-origin
Permissions-Policy: geolocation=(), microphone=(), camera=()
Content-Security-Policy: default-src 'self'; script-src 'self'; ...  # HIGH-MID-01: CSP
Strict-Transport-Security: max-age=31536000; includeSubDomains  # HIGH-MID-01: HSTS (prod only)
```

**3. Content-Type Validation Middleware (HIGH-04 FIX)**
```python
# POST/PUT/PATCH requests must use application/json or form-urlencoded
# Exempt paths: /api/billing/webhook, /api/health
# Returns 415 Unsupported Media Type if invalid
```

**4. WebSocket Origin Validation (HIGH-05 FIX)**
```python
# All WS connections validate Origin header against allowed origins
# Development allows missing Origin header
# Invalid origin returns close code 4003
```

**5. Rate Limiting (CRIT-05 FIX)**
```python
# Billing endpoints protected:
/api/billing/check/request    # 10/minute
/api/billing/cash/pay         # 20/minute
/api/billing/mercadopago/*    # 5/minute
```

### Input Validation (CRIT-02, HIGH-04 FIX)

Image URLs are validated to prevent XSS/SSRF attacks:
```python
# backend/shared/utils/validators.py
validate_image_url(url)  # Validates scheme, blocks internal IPs

# HIGH-04 FIX: CRUDFactory auto-validates image URLs
# Configure in CRUDConfig:
crud = CRUDFactory(CRUDConfig(
    model=Product,
    image_url_fields={"image"},  # Fields to validate (default: {"image"})
    ...
))
# Validation runs automatically in create() and update()

# Blocked hosts (SSRF prevention):
BLOCKED_HOSTS = ["localhost", "127.0.0.1", "10.", "172.16-31.", "192.168.",
                 "169.254.169.254", "metadata.google"]  # Cloud metadata endpoints
```

### Production Security Checklist

Settings in `backend/.env` for production:
```bash
# REQUIRED: Generate with: openssl rand -base64 32
JWT_SECRET=<32+ char random string>
TABLE_TOKEN_SECRET=<32+ char random string>

# REQUIRED: Comma-separated allowed origins
ALLOWED_ORIGINS=https://yourdomain.com,https://admin.yourdomain.com

# REQUIRED: Disable debug mode
DEBUG=false
ENVIRONMENT=production

# If using Mercado Pago payments:
MERCADOPAGO_WEBHOOK_SECRET=<your-webhook-secret>
```

The server validates these on startup and refuses to start with insecure defaults in production.

---

## Load Optimization (400+ Users)

The system is optimized for 400-600 concurrent WebSocket users with the following configurations:

### Level 1: Configuration (settings.py)

| Setting | Default | Purpose |
|---------|---------|---------|
| `ws_max_connections_per_user` | 3 | Limit duplicate connections |
| `ws_max_total_connections` | 1000 | Global connection limit |
| `ws_message_rate_limit` | 20/s | Per-connection message rate |
| `ws_broadcast_batch_size` | 50 | Parallel broadcast batch |
| `redis_pool_max_connections` | 50 | Async pool size |
| `redis_sync_pool_max_connections` | 20 | Sync pool (blocking ops) |
| `redis_event_queue_size` | 5000 | Backpressure buffer |
| `redis_event_batch_size` | 50 | Event processing batch |

### Level 2: Code Optimizations

**Parallel Broadcast** ([connection_manager.py](ws_gateway/connection_manager.py)):
- Uses `asyncio.gather()` with batches of 50 connections
- 10x faster broadcast to 400 users (~160ms vs ~4000ms)

**Sharded Locks**:
- `_branch_locks`: Per-branch locks reduce contention 90%
- `_user_locks`: Per-user locks for connection management
- Global lock only for cross-cutting operations

**Sync Redis Pool** ([events.py](backend/shared/infrastructure/events.py)):
- Connection pool instead of singleton for sync operations
- Supports concurrent rate limiting and token blacklist checks
- Thread-safe with double-check locking

**WebSocket Rate Limiting**:
- `WebSocketRateLimiter` class with sliding window algorithm
- Custom close code 4029 for rate-limited connections

### Health Check Endpoints

```bash
# Basic health (sync)
GET /ws/health

# Detailed health with Redis pool status (async)
GET /ws/health/detailed
# Returns: redis_async status, redis_sync pool info, connection stats
```

---

## Infrastructure

### Project Root Structure

```
integrador/
├── Dashboard/         # Admin panel (React 19 + Zustand)
├── pwaMenu/           # Customer PWA (collaborative ordering)
├── pwaWaiter/         # Waiter PWA (table management)
├── backend/           # FastAPI REST API + shared modules
├── ws_gateway/        # WebSocket Gateway (real-time events)
└── devOps/            # Infrastructure & startup scripts
    ├── docker-compose.yml  # PostgreSQL + Redis
    ├── start.ps1           # Windows startup (sets PYTHONPATH)
    └── start.sh            # Unix startup
```

### Backend Directory Structure

```
backend/
├── rest_api/              # FastAPI REST API
│   ├── core/              # App configuration
│   │   ├── lifespan.py    # Startup/shutdown logic
│   │   ├── middlewares.py # Security middlewares
│   │   └── cors.py        # CORS configuration
│   ├── models/            # SQLAlchemy ORM models (modular by domain)
│   │   ├── __init__.py    # Re-exports all 52 models (47 entities + 5 M:N tables)
│   │   ├── base.py        # Base, AuditMixin
│   │   ├── tenant.py      # Tenant, Branch
│   │   ├── user.py        # User, UserBranchRole
│   │   ├── catalog.py     # Category, Subcategory, Product, BranchProduct
│   │   ├── allergen.py    # Allergen, ProductAllergen, AllergenCrossReaction
│   │   ├── ingredient.py  # IngredientGroup, Ingredient, SubIngredient, ProductIngredient
│   │   ├── product_profile.py  # 12 dietary/cooking/flavor profile models (M:N tables have AuditMixin)
│   │   ├── sector.py      # BranchSector, WaiterSectorAssignment
│   │   ├── table.py       # Table, TableSession
│   │   ├── customer.py    # Customer, Diner
│   │   ├── order.py       # Round, RoundItem
│   │   ├── kitchen.py     # KitchenTicket, KitchenTicketItem, ServiceCall
│   │   ├── billing.py     # Check (table: app_check), Payment, Charge, Allocation
│   │   ├── knowledge.py   # KnowledgeDocument, ChatLog (RAG)
│   │   ├── promotion.py   # Promotion, PromotionBranch, PromotionItem
│   │   ├── exclusion.py   # BranchCategoryExclusion, BranchSubcategoryExclusion
│   │   ├── audit.py       # AuditLog
│   │   └── recipe.py      # Recipe, RecipeAllergen
│   ├── routers/           # API endpoints (organized by responsibility)
│   │   ├── _common/       # Shared utilities (base.py, pagination.py)
│   │   ├── admin/         # Admin CRUD routers (15 entity routers)
│   │   ├── auth/          # Authentication (login, logout, refresh)
│   │   ├── billing/       # Payment processing (checks, Mercado Pago)
│   │   ├── content/       # Content management (catalogs, ingredients, promotions, rag, recipes)
│   │   ├── diner/         # Diner operations (orders.py, customer.py)
│   │   ├── kitchen/       # Kitchen staff (rounds.py, tickets.py)
│   │   ├── public/        # Public endpoints (catalog.py, health.py)
│   │   ├── tables/        # Table management and sessions
│   │   └── waiter/        # Waiter operations
│   └── services/          # Business logic (organized by responsibility)
│       ├── domain/        # **PREFERRED** Clean Architecture services (category_service.py, etc.)
│       ├── crud/          # Repository pattern, soft delete, audit (repository.py, soft_delete.py, audit.py)
│       ├── payments/      # Payment processing (allocation.py, circuit_breaker.py, mp_webhook.py)
│       ├── catalog/       # Product catalog (product_view.py, recipe_sync.py)
│       ├── rag/           # AI/RAG chatbot (service.py)
│       ├── events/        # Real-time events (admin_events.py, domain_event.py, publisher.py)
│       ├── permissions/   # Strategy pattern for RBAC (context.py, strategies.py)
│       └── base_service.py # Base classes for domain services
├── shared/                # Shared modules (API + WS Gateway)
│   ├── security/          # Authentication & authorization
│   │   ├── auth.py        # JWT/HMAC token verification
│   │   ├── password.py    # Bcrypt hashing
│   │   ├── token_blacklist.py # Redis-based revocation
│   │   └── rate_limit.py  # Login rate limiting
│   ├── infrastructure/    # Database & messaging
│   │   ├── db.py          # SQLAlchemy sessions, safe_commit()
│   │   ├── events/        # Redis pub/sub (modular package)
│   │   │   ├── circuit_breaker.py  # EventCircuitBreaker, jitter utilities
│   │   │   ├── event_types.py      # ROUND_SUBMITTED, etc.
│   │   │   ├── event_schema.py     # Event dataclass with validation
│   │   │   ├── channels.py         # channel_branch_waiters(), etc.
│   │   │   ├── redis_pool.py       # get_redis_pool(), async/sync pools
│   │   │   ├── health_checks.py    # check_redis_async_health()
│   │   │   ├── publisher.py        # publish_event() with retry
│   │   │   ├── routing.py          # publish_to_waiters(), etc.
│   │   │   └── domain_publishers.py # publish_round_event(), etc.
│   │   └── __init__.py    # Re-exports from events/ submodules
│   ├── config/            # Configuration
│   │   ├── settings.py    # Environment config (Pydantic)
│   │   ├── logging.py     # Structured logging
│   │   └── constants.py   # Roles, RoundStatus, enums
│   ├── utils/             # Utilities
│   │   ├── exceptions.py  # HTTP exceptions with auto-logging
│   │   ├── validators.py  # Input validation, SSRF prevention
│   │   ├── health.py      # Health check decorators + HealthCheckResult
│   │   ├── schemas.py     # Shared Pydantic schemas (base types)
│   │   └── admin_schemas.py # Admin API schemas (CategoryOutput, ProductOutput, etc.)
│   └── __init__.py        # Package exports
└── tests/                 # pytest tests

ws_gateway/                # WebSocket Gateway (at project root)
├── main.py                # FastAPI WebSocket app, /ws/metrics endpoint
├── connection_manager.py  # Thin orchestrator (composes core/connection/)
├── redis_subscriber.py    # Thin orchestrator (composes core/subscriber/)
├── core/                  # ARCH-MODULAR: Extracted modules for maintainability
│   ├── connection/        # From connection_manager.py (987→463 lines)
│   │   ├── lifecycle.py   # ConnectionLifecycle: connect/disconnect
│   │   ├── broadcaster.py # ConnectionBroadcaster: send/broadcast methods
│   │   ├── cleanup.py     # ConnectionCleanup: stale/dead cleanup
│   │   └── stats.py       # ConnectionStats: statistics aggregation
│   └── subscriber/        # From redis_subscriber.py (666→326 lines)
│       ├── drop_tracker.py # EventDropRateTracker: drop rate alerts
│       ├── validator.py   # Event schema validation
│       └── processor.py   # Event batch processing
└── components/            # Modular architecture with design patterns
    ├── __init__.py        # Re-exports all components
    ├── core/              # Constants, context, DI
    ├── connection/        # Index, locks, heartbeat, rate limiter
    ├── events/            # WebSocketEvent, EventRouter
    ├── broadcast/         # BroadcastRouter, TenantFilter
    ├── auth/              # JWT/TableToken strategies
    ├── endpoints/         # Base, mixins, handlers
    ├── resilience/        # CircuitBreaker, retry with jitter
    ├── metrics/           # MetricsCollector, Prometheus
    └── data/              # SectorRepository + cache
```

### Docker Configuration

```yaml
# devOps/docker-compose.yml services:
PostgreSQL: localhost:5432 (pgvector/pgvector:pg16)
Redis: localhost:6380 (NOTE: port 6380, not 6379)
```

**Database Reset:**
```bash
cd backend
docker compose -f devOps/docker-compose.yml down -v && docker compose -f devOps/docker-compose.yml up -d
# Then restart REST API to re-run seed()
```

### CORS Configuration

**Development:** Uses default localhost ports automatically:
```python
DEFAULT_CORS_ORIGINS = [
    "http://localhost:5173",  # Vite default
    "http://localhost:5176",  # pwaMenu
    "http://localhost:5177",  # Dashboard
    "http://localhost:5178",  # pwaWaiter
    # ... and 127.0.0.1 equivalents
]
```

**Production:** Set `ALLOWED_ORIGINS` environment variable (comma-separated):
```bash
ALLOWED_ORIGINS=https://menu.restaurant.com,https://admin.restaurant.com,https://waiter.restaurant.com
```

When adding new origins in development, update `DEFAULT_CORS_ORIGINS` in `backend/rest_api/main.py`.

### Frontend Environment Variables

Each frontend requires specific environment variables in their `.env` file:

| Frontend | Variable | Default | Description |
|----------|----------|---------|-------------|
| All | `VITE_API_URL` | `http://localhost:8000` | Backend REST API URL |
| All | `VITE_WS_URL` | `ws://localhost:8001` | WebSocket Gateway URL |
| pwaMenu | `VITE_BRANCH_SLUG` | - | Branch identifier for QR code flow (required) |
| pwaWaiter | `VITE_VAPID_PUBLIC_KEY` | - | Push notification VAPID key |

**Important:** `VITE_BRANCH_SLUG` must match a valid `slug` in the `branch` table for pwaMenu to work with table sessions.

---

## Key Features

### Generic CRUD Factory (admin routers) - DEPRECATED

> **Note:** CRUDFactory is deprecated. Use Domain Services (see "Clean Architecture" section).
> New code should use `CategoryService`, `BranchService`, etc.

For legacy code using standardized CRUD operations:

```python
# rest_api/services/crud/factory.py
from rest_api.services.crud import CRUDFactory, CRUDConfig

# Configure once per entity type
crud = CRUDFactory(CRUDConfig(
    model=Category,
    output_schema=CategoryOutput,
    create_schema=CategoryCreate,
    update_schema=CategoryUpdate,
    entity_name="Categoría",  # For Spanish error messages
    has_branch_id=False,
    supports_soft_delete=True,
))

# Use in router endpoints
@router.get("", response_model=list[CategoryOutput])
def list_categories(db: Session, user: dict):
    return crud.list_all(db, user["tenant_id"], limit=50, offset=0)

@router.post("", response_model=CategoryOutput)
def create_category(body: CategoryCreate, db: Session, user: dict):
    return crud.create(db, body, user["tenant_id"], get_user_id(user), get_user_email(user))
```

### Entity Output Builder

For reducing duplicate `build_*_output` functions:

```python
# rest_api/services/crud/entity_builder.py
from rest_api.services.crud import EntityOutputBuilder, build_output

# Create builder for an output schema
builder = EntityOutputBuilder(ProductOutput)

# Use in router
def get_product(product_id: int, db: Session):
    product = db.scalar(select(Product).where(...))
    return builder.build(product, branch_name=product.branch.name)  # With overrides
```

### Soft Delete Pattern

All models inherit from `AuditMixin`:
- `is_active` flag (default True, indexed)
- Timestamps: `created_at`, `updated_at`, `deleted_at`
- User tracking: `created_by_id/email`, `updated_by_id/email`, `deleted_by_id/email`

**Note:** M:N junction tables (`ProductCookingMethod`, `ProductFlavor`, `ProductTexture`) also have `AuditMixin` for audit trail consistency.

```python
# rest_api/services/crud/soft_delete.py
from rest_api.services.crud import soft_delete, restore_entity, set_created_by, set_updated_by
soft_delete(db, entity, user_id, user_email)
```

### Role-Based Access Control

| Role | Create | Edit | Delete |
|------|--------|------|--------|
| ADMIN | All entities | All entities | All entities |
| MANAGER | Staff, Tables, Allergens, Promotions (own branches) | Same | None |
| KITCHEN | None | None | None |
| WAITER | None | None | None |

**Permission Strategy Pattern (LOW-02 ISP FIX):**

The permission system uses Strategy pattern with Interface Segregation Principle (ISP).
Strategies can implement only the capabilities they need via focused protocols and mixins:

```python
# Segregated protocols (implement only what you need)
from rest_api.services.permissions.strategies import (
    CanRead, CanCreate, CanUpdate, CanDelete, QueryFilter,  # Protocols
    NoCreateMixin, NoDeleteMixin, NoUpdateMixin,  # Deny mixins
    BranchFilterMixin, BranchAccessMixin,  # Branch access mixins
    PermissionStrategy,  # Full interface (backward compatible)
)

# Example: Kitchen strategy uses mixins for cleaner implementation
class KitchenStrategy(NoCreateMixin, NoDeleteMixin, BranchFilterMixin, PermissionStrategy):
    """Kitchen can only read/update tickets and rounds in their branch."""
    READABLE_ENTITIES = frozenset({"Round", "KitchenTicket", "Product", ...})
    UPDATABLE_ENTITIES = frozenset({"Round", "KitchenTicket"})

    def can_read(self, user: dict, entity: Any) -> bool:
        if type(entity).__name__ not in self.READABLE_ENTITIES:
            return False
        return self._user_has_branch_access(user, self._get_entity_branch_id(entity))

    def can_update(self, user: dict, entity: Any) -> bool:
        if type(entity).__name__ not in self.UPDATABLE_ENTITIES:
            return False
        return self._user_has_branch_access(user, self._get_entity_branch_id(entity))

    # can_create() and can_delete() inherited from mixins (always False)
    # filter_query() inherited from BranchFilterMixin (filters by branch_ids)

# Get strategy for user role
from rest_api.services.permissions.strategies import get_highest_privilege_strategy
strategy = get_highest_privilege_strategy(user["roles"])
if strategy.can_update(user, entity):
    # proceed with update
```

Available Mixins:
| Mixin | Purpose |
|-------|---------|
| `NoCreateMixin` | Returns False for can_create() |
| `NoDeleteMixin` | Returns False for can_delete() |
| `NoUpdateMixin` | Returns False for can_update() |
| `BranchFilterMixin` | Filters queries by user's branch_ids |
| `BranchAccessMixin` | Helper methods for branch access checks |

### Waiter Sector Filtering

Waiters only see tables from their assigned sectors for the current day:
- Assignments stored in `WaiterSectorAssignment` table
- `/api/waiter/tables?branch_id={id}` filters by assigned sectors
- ADMIN/MANAGER see all tables in branch
- Multi-sector support: waiters can be assigned to multiple sectors

### Table Session Lifecycle

Sessions allow flexible ordering even during payment:
- `OPEN`: Normal ordering state
- `PAYING`: Check requested, but customers can still order additional items
- `CLOSED`: Session ended, table available
- New orders during PAYING are added to future payment cycles

**Table Codes vs IDs:**
- Tables use alphanumeric codes (e.g., "INT-01", "TER-02") for QR codes and user-facing display
- QR codes encode table codes, not numeric IDs
- Use `/api/tables/code/{code}/session?branch_slug={slug}` for alphanumeric codes (pwaMenu QR flow)
- Use `/api/tables/{id}/session` for numeric IDs (internal/admin use)

**Important:** Table codes are NOT unique across branches (each branch has its own "INT-01").
The `branch_slug` query parameter is required to identify the correct table.
pwaMenu automatically passes `branchSlug` from menuStore when creating sessions via `tableStore.joinTable()`.

### Recipe Module

Kitchen technical sheets ("fichas técnicas") with:
- Ingredients, preparation steps, allergens
- RAG chatbot ingestion via `/api/recipes/{id}/ingest`
- Optional link to Products (Recipe → Product derivation)

### pwaMenu Advanced Filters

Filter hooks for dietary preferences:
- `useAllergenFilter`: Filter by allergens with strictness levels and cross-reactions
- `useDietaryFilter`: Vegetarian, vegan, gluten-free, celiac-safe, keto, low-sodium
- `useCookingMethodFilter`: Exclude fried, require grilled, etc.

### Customer Loyalty System (Fidelización)

Cross-session customer recognition without requiring explicit registration:

**Phase 1: Device Tracking** (implemented)
- `device_id` and `device_fingerprint` fields on `Diner` model
- `pwaMenu/src/utils/deviceId.ts`: Generate and persist UUID in localStorage
- `GET /api/diner/device/{device_id}/history`: Visit history for returning devices

**Phase 2: Implicit Preferences** (implemented)
- `implicit_preferences` JSON field on `Diner` model stores filter settings
- `PATCH /api/diner/preferences`: Sync allergen/dietary/cooking filters to backend
- `GET /api/diner/device/{device_id}/preferences`: Load saved preferences on return visits
- `pwaMenu/src/hooks/useImplicitPreferences.ts`: Auto-sync with debounce, pre-load on mount

**Phase 4: Customer Opt-in** (implemented)
- `Customer` model with GDPR consent fields, metrics, AI personalization
- `customer_id` field on `Diner` links visits to registered customer
- `POST /api/customer/register`: Create customer with opt-in consent
- `GET /api/customer/recognize`: Check if device is linked to customer
- `GET /api/customer/suggestions`: Personalized favorites and recommendations
- `pwaMenu/src/hooks/useCustomerRecognition.ts`: Detect returning customers
- `pwaMenu/src/components/OptInModal.tsx`: Registration modal with consent checkboxes

```typescript
// Implicit preferences flow
const { loadPreferences, syncPreferences } = useImplicitPreferences(branchSlug)
// Auto-syncs filter changes after 2s debounce
// Loads saved preferences on app startup for returning devices

// Customer recognition flow
const { isRecognized, customer, suggestions } = useCustomerRecognition()
// Check on mount if device is linked to customer
// Load personalized suggestions if recognized
```

### Round Confirmation (Confirmación Grupal - pwaMenu)

Group confirmation before submitting orders to prevent accidental submissions:

1. Diner proposes to send order → `proposeRound()`
2. All diners see confirmation panel with ready/waiting status
3. Each diner confirms → `confirmReady()`
4. When all confirm → auto-submit after 1.5s delay
5. Proposal expires after 5 minutes or proposer cancels

Key files:
- `pwaMenu/src/types/session.ts`: `RoundConfirmation`, `DinerReadyStatus` types
- `pwaMenu/src/stores/tableStore/store.ts`: Confirmation actions and getters
- `pwaMenu/src/components/cart/RoundConfirmationPanel.tsx`: UI component
- i18n keys in `roundConfirmation` namespace

### Comanda Rápida (pwaWaiter)

For customers without phones using paper menus:
- Waiter takes orders via `ComandaTab` component in TableDetail
- Compact menu endpoint (`GET /api/waiter/branches/{id}/menu`) returns products without images
- Local cart state with quantity controls
- Submits via `waiterTableAPI.submitRound()` - same backend as diner orders
- Round created with `PENDING` status (same flow as pwaMenu)

### Round Status Flow (Role-Restricted)

Orders go through Dashboard before reaching kitchen:

| Status | Description | Who can advance? | Next status |
|--------|-------------|------------------|-------------|
| `PENDING` | New order from pwaMenu/waiter | ADMIN/MANAGER | `SUBMITTED` |
| `SUBMITTED` | Manager sent to kitchen | ADMIN/MANAGER | `IN_KITCHEN` |
| `IN_KITCHEN` | Kitchen working on order | **KITCHEN only** | `READY` |
| `READY` | Kitchen finished | ADMIN/MANAGER/WAITER | `SERVED` |
| `SERVED` | Delivered to table | - | - |

**Key behavior:**
- `ROUND_PENDING` event: Client creates order → only to admin channel (Tables view)
- `ROUND_SUBMITTED` event: Manager sends to kitchen → to admin AND kitchen channels
- Only `ROUND_IN_KITCHEN`, `ROUND_READY`, `ROUND_SERVED` notify diners (session channel)
- Dashboard cannot change `IN_KITCHEN` → `READY` (must wait for kitchen)
- Files: `kitchen/rounds.py` (status transitions), `TableSessionModal.tsx` (UI buttons)

**Kitchen View (2 columns):**
- Only shows "Nuevos" (SUBMITTED) and "En Cocina" (IN_KITCHEN) columns
- READY rounds are removed from kitchen view and handled by Dashboard/waiters
- File: `Kitchen.tsx`

### Table Status Animation (Dashboard)

Tables show visual feedback for order states:

| Event | Table Status | Order Status | Animation |
|-------|--------------|--------------|-----------|
| `TABLE_SESSION_STARTED` (QR scan) | `ocupada` (red) | `none` | Blue blink |
| `ROUND_PENDING` (client order) | `ocupada` (red) | `pending` | Yellow pulse |
| `ROUND_SUBMITTED` (sent to kitchen) | `ocupada` (red) | `submitted` | Blue blink |
| `ROUND_IN_KITCHEN` (kitchen working) | `ocupada` (red) | `in_kitchen` | Blue blink |
| `ROUND_READY` (kitchen finished) | `ocupada` (red) | `ready` | Blue blink |
| `ROUND_SERVED` (delivered) | `pedido_cumplido` | `served` | Blue blink |
| `TABLE_CLEARED` (session ended) | `libre` (green) | `none` | Blue blink |

**Order Status Badge Colors:**
| Status | Badge Color | Label |
|--------|-------------|-------|
| `pending` | Yellow | "Pendiente" |
| `submitted` | Blue | "En Cocina" |
| `in_kitchen` | Blue | "En Cocina" |
| `ready` | Green | "Listo" |
| `served` | Gray | "Servido" |

**Badge Contrast:** All order status badges use solid backgrounds (`bg-*-400`) with black bold text for accessibility.

**Order Status Priority (Multi-Round):**
When a table has multiple rounds, the aggregate status is calculated with these rules:

1. **Ready + Not Ready = Combined:** If ANY round is `ready` AND any is NOT ready (pending/submitted/in_kitchen),
   show "Listo + Cocina" to alert waiter that items are ready for pickup
2. **All Pending:** If ALL rounds are `pending` (none ready), show "Pendiente"
3. **Otherwise:** Show the "worst" (lowest priority) status from remaining rounds

| Priority | Statuses | Display | Badge Color |
|----------|----------|---------|-------------|
| 0 (highest) | `ready` + any not ready | "Listo + Cocina" | Black |
| 1 | `pending` (all) | "Pendiente" | Yellow |
| 2 | `submitted`, `in_kitchen` | "En Cocina" | Blue |
| 3 | `ready` (all) | "Listo" | Green |
| 4 | `served` | "Servido" | Gray |
| 5 | `none` | No badge | - |

**Example Scenarios:**
| Rounds | Aggregate Status | Reason |
|--------|------------------|--------|
| 1 ready + 1 pending | Listo + Cocina | Ready items + more coming |
| 1 ready + 1 in_kitchen | Listo + Cocina | Ready items + more in kitchen |
| 2 pending | Pendiente | All pending |
| 1 pending + 1 submitted | Pendiente | None ready yet |
| 2 submitted | En Cocina | All in kitchen |
| 2 ready | Listo | All ready |

**Combined Status:** When a table has at least one round `ready` AND at least one round NOT ready
(pending/submitted/in_kitchen), the status shows "Listo + Cocina" with a black badge (`bg-gray-800`, white text).
This alerts the waiter that some items are ready for pickup while more orders are still pending.

**State Persistence on Navigation:**
When `fetchTables` is called, it preserves WebSocket-updated state (`orderStatus`, `roundStatuses`,
`hasNewOrder`, `statusChanged`) from existing tables. This prevents losing order status when
navigating between Dashboard views.

**Animation Classes:**
- `animate-pulse-warning`: Yellow pulse for new orders (`hasNewOrder`)
- `animate-pulse-urgent`: Purple pulse for check requested
- `animate-status-blink`: Blue blink for status changes (auto-clears after 1.5s)

**Key Fields on `RestaurantTable`:**
- `orderStatus`: Current order/round status (`'none' | 'pending' | 'submitted' | 'in_kitchen' | 'ready_with_kitchen' | 'ready' | 'served'`)
- `statusChanged`: Triggers blink animation on status change
- `hasNewOrder`: Triggers persistent warning pulse for new orders

**Files:**
- `tableStore.ts`: WebSocket event handlers that update `orderStatus` and trigger `statusChanged`
- `Tables.tsx`: `TableCard` component displays order status badge below capacity
- `index.css`: CSS animations (`pulse-warning`, `pulse-urgent`, `status-blink`)

### Table Session Modal (Dashboard)

View active order/session details when clicking on a table in `/branches/tables`:
- `Dashboard/src/components/tables/TableSessionModal.tsx`: Modal component
- Shows diners, rounds with items grouped by category (Bebidas → Entradas → Principales → Postres)
- Endpoint: `GET /api/waiter/tables/{tableId}/session` returns `TableSessionDetail`
- `RoundItemDetail` includes `category_name` for grouping (JOIN with Category table)
- Handles error states (no active session) gracefully
- Types: `DinerOutput`, `RoundDetail`, `RoundItemDetail`, `TableSessionDetail` in `api.ts`

**Category Send Icons:**
- Each category section has a send icon (red → green on click)
- Tracks which categories have been dispatched visually
- Local state per round (`sentCategories` Set)
- Click to toggle: red = pending, green = sent

---

## Documentation

### Component Documentation
- [Dashboard/README.md](Dashboard/README.md): Dashboard admin panel documentation (React 19, Zustand, patterns)
- [Dashboard/arquiDashboard.md](Dashboard/arquiDashboard.md): Dashboard architecture deep-dive (state management, API client, WebSocket)
- [pwaMenu/README.md](pwaMenu/README.md): Customer menu PWA documentation (collaborative ordering, payments, i18n)
- [backend/README.md](backend/README.md): Backend REST API documentation (architecture, commands, patterns)
- [backend/arquiBackend.md](backend/arquiBackend.md): Backend architecture deep-dive (layers, patterns, flows)
- [backend/shared/README.md](backend/shared/README.md): Shared modules documentation
- [ws_gateway/README.md](ws_gateway/README.md): WebSocket Gateway documentation (events, endpoints, resilience)
- [ws_gateway/arquiws_gateway.md](ws_gateway/arquiws_gateway.md): WebSocket Gateway architecture deep-dive (components, patterns, flows)
- [devOps/README.md](devOps/README.md): Infrastructure and startup scripts (Docker, PostgreSQL, Redis)

### QA Reports
- [REPORTE_TRAZABILIDAD.md](REPORTE_TRAZABILIDAD.md): Complete traceability report with test traces
- [RESULTADOS_QA.md](RESULTADOS_QA.md): QA test results
- [QA_TRAZA_WEBSOCKET_2026-01-18.md](QA_TRAZA_WEBSOCKET_2026-01-18.md): WebSocket QA trace (sector filtering, notifications)

### Agile Documentation (IA-Native)
- [agile/politicas.md](agile/politicas.md): **Policy Tickets governance** - 22 tickets defining AI autonomy levels
- [agile/historias/historias_usuario.md](agile/historias/historias_usuario.md): **152 user stories** with technical specifications
- [agile/historias/plantilla.md](agile/historias/plantilla.md): User story template with governance integration
- [agile/historias/refactorizacion.md](agile/historias/refactorizacion.md): HU→PT mapping matrix

### Multi-Agent Skills System
- [agile/skills/README.md](agile/skills/README.md): **Skills architecture** - Agent system design
- [agile/skills/MULTIAGENT_GUIDE.md](agile/skills/MULTIAGENT_GUIDE.md): **Multi-agent operations** - Coordination patterns
- [agile/skills/dispatcher.md](agile/skills/dispatcher.md): Router agent for task distribution

**Available Skills by Autonomy Level:**
| Level | Skills | Purpose |
|-------|--------|---------|
| 🔴 CRÍTICO | `critico/auth-analyst.md` | Analysis only, no code modification |
| 🟠 ALTO | `_base/alto.md` (template) | Supervised code proposals |
| 🟡 MEDIO | `medio/kitchen-dev.md` | Implementation with checkpoints |
| 🟢 BAJO | `bajo/catalog-dev.md` | Autonomous implementation |

---

## IA-Native Governance Framework

This project uses the **IA-Native Framework** with Policy Tickets to govern AI-assisted development.

### Principle

> "Delegar ejecución no transfiere responsabilidad. La IA ejecuta; el humano responde."

### Autonomy Levels

| Level | Autonomy | AI Can | AI Cannot |
|-------|----------|--------|-----------|
| 🔴 **CRÍTICO** | análisis-solamente | Analyze, document, suggest, generate tests | Write production code, create PRs |
| 🟠 **ALTO** | código-supervisado | Propose changes (human reviews line-by-line) | Auto-commit or merge |
| 🟡 **MEDIO** | código-con-review | Write code with checkpoints per feature | Skip peer review |
| 🟢 **BAJO** | código-autónomo | Full implementation, auto-merge if CI passes | Skip tests |

### Domain Risk Classification

```
🔴 CRÍTICO (35 HU - 23%): Auth, Staff, Allergens, Billing, Security
🟠 ALTO (15 HU - 10%): Products, WebSocket Events, Rate Limiting, Token Blacklist
🟡 MEDIO (53 HU - 35%): Orders, Kitchen, Waiter, Diner, Tables, Customer Loyalty
🟢 BAJO (49 HU - 32%): Categories, Sectors, Recipes, Ingredients, Promotions, Public, Audit
```

### Policy Ticket Reference

Before working on any feature, consult the corresponding Policy Ticket in [agile/politicas.md](agile/politicas.md):

| Domain | Policy Ticket | Risk Level |
|--------|---------------|------------|
| Auth/JWT | PT-AUTH-001 | CRÍTICO |
| Rate Limiting | PT-AUTH-002 | CRÍTICO |
| Staff Management | PT-STAFF-001 | CRÍTICO |
| Allergens | PT-ALLERGEN-001 | CRÍTICO |
| Billing/Payments | PT-BILLING-001, PT-BILLING-002 | CRÍTICO |
| Products | PT-PRODUCT-001 | ALTO |
| WebSocket Events | PT-EVENTS-001 | ALTO |
| Token Blacklist | PT-BLACKLIST-001 | ALTO |
| Orders/Rounds | PT-ORDERS-001 | MEDIO |
| Kitchen | PT-KITCHEN-001 | MEDIO |
| Waiter | PT-WAITER-001 | MEDIO |
| Diner | PT-DINER-001 | MEDIO |
| Tables | PT-TABLES-001 | MEDIO |
| Customer Loyalty | PT-CUSTOMER-001 | MEDIO |
| Categories | PT-CATEGORY-001 | BAJO |
| Sectors/Tables | PT-SECTOR-001 | BAJO |
| Recipes | PT-RECIPE-001 | BAJO |
| Ingredients | PT-INGREDIENT-001 | BAJO |
| Promotions | PT-PROMOTION-001 | BAJO |
| Public Endpoints | PT-PUBLIC-001 | BAJO |
| Audit | PT-AUDIT-001 | BAJO |

### AI Behavior Guidelines

**For CRÍTICO domains:**
- Read and analyze only
- Generate tests in sandbox/test environments
- Document findings and suggestions
- NEVER modify production code directly

**For ALTO domains:**
- Propose changes with full context
- Wait for human line-by-line review
- Include rationale for each change

**For MEDIO domains:**
- Implement with checkpoints
- Request review after each feature completion
- Document all decisions made

**For BAJO domains:**
- Full autonomy with passing CI
- Self-approve if tests pass
- Follow existing patterns in codebase

### User Story Reference

For detailed technical specifications of any endpoint, consult [agile/historias/historias_usuario.md](agile/historias/historias_usuario.md). Each story includes:
- YAML metadata with endpoint, roles, implementation file
- Request/Response JSON schemas
- Validation tables with error codes
- Business logic steps
- SQL data models
- WebSocket events (if applicable)

### Multi-Agent Operations

Use the **Task tool** with specialized skills for complex implementations:

```typescript
// Single agent - Use skill directly
Task({
  prompt: `
    Skill: agile/skills/bajo/catalog-dev.md
    Tarea: Implementar HU-CAT-003 (Crear Categoría)
  `,
  subagent_type: "general-purpose"
})

// Parallel agents - Multiple Task calls in ONE message
const [result1, result2] = await Promise.all([
  Task({ prompt: "Skill: catalog-dev...", run_in_background: true }),
  Task({ prompt: "Skill: kitchen-dev...", run_in_background: true })
])

// Sequential with context passing
const modelResult = await Task({ prompt: "Create model..." });
const serviceResult = await Task({
  prompt: `Context: ${modelResult}\nCreate service using the model...`
});
```

**Coordination Patterns:**
| Pattern | When to Use | Example |
|---------|-------------|---------|
| Sequential | Dependencies between tasks | Model → Service → Router |
| Parallel | Independent tasks | Document multiple modules |
| Hierarchical | Complex features | Supervisor + workers |
| Cross-review | Quality/Security | Developer → Security review |

See [MULTIAGENT_GUIDE.md](agile/skills/MULTIAGENT_GUIDE.md) for detailed examples.

---

## Common Issues

### Backend not reloading changes (Windows)
Windows uses StatReload by default which may fail to detect file changes. The project uses `watchfiles`:
```bash
# watchfiles is installed via requirements.txt
# If hot-reload detects changes but doesn't apply them (especially new routes),
# restart the backend manually:
# Ctrl+C to stop, then:
uvicorn rest_api.main:app --reload --port 8000
```
**Note:** WatchFiles may detect changes but fail to reload new routes. A manual restart ensures all routes are registered.

### TypeScript errors
Dashboard and pwaMenu have preexisting TS errors that don't affect production builds.
Run `npx tsc --noEmit` to see current errors.

### WebSocket connection issues
- Check Redis is running: `docker compose -f devOps/docker-compose.yml ps`
- Verify CORS origins include your frontend port
- Backend accepts both `"ping"` and `{"type":"ping"}` formats

### WebSocket disconnects every ~30 seconds
If Dashboard WebSocket connections disconnect repeatedly after ~30 seconds with "stale connection cleanup":
1. **Check JWT token expiration** - access tokens last 15 minutes
2. **Refresh the Dashboard page** to get a new JWT token
3. The WebSocket reconnects with the same (possibly expired) token, causing auth failure
4. Heartbeat mechanism: client sends ping every 30s, server has 60s timeout, cleanup runs every 30s
5. Check WS Gateway logs for `tracked_connections=0` which indicates no valid connections

### uvicorn not in PATH (Windows PowerShell)
If `uvicorn` is not recognized in PowerShell, use `python -m uvicorn` instead:
```bash
# REST API (from backend folder)
cd backend
python -m uvicorn rest_api.main:app --reload --port 8000

# WS Gateway (from project root - requires PYTHONPATH)
cd ..  # go to project root
$env:PYTHONPATH = "$PWD\backend"  # Windows PowerShell
# export PYTHONPATH="$(pwd)/backend"  # Unix/Mac
python -m uvicorn ws_gateway.main:app --reload --port 8001
```
This happens when Python scripts are not in the system PATH. Using `python -m` ensures the module is found correctly. The ws_gateway requires PYTHONPATH to include the backend folder because it imports from `shared` and `rest_api` modules.

### Table status not updating on QR scan
If the table doesn't change to "ocupada" when a diner scans QR in pwaMenu:
1. Verify `VITE_BRANCH_SLUG` in `pwaMenu/.env` matches the branch slug in database
2. Check that `branch_slug` is being passed to `/api/tables/code/{code}/session`
3. Verify WebSocket Gateway is running on port 8001
4. Check WS Gateway logs for `TABLE_SESSION_STARTED` event dispatch
5. Verify Dashboard is connected to WebSocket (check browser console for connection status)

---

## QA Status (January 2026)

All builds verified passing:
- **Dashboard**: 100 Vitest tests ✅
- **pwaMenu**: 108 Vitest tests ✅
- **pwaWaiter**: Build passes ✅

**980+ defects fixed** across 23 audits. See [AUDIT_HISTORY.md](AUDIT_HISTORY.md) for complete details.

**WebSocket Integration Audit (Jan 28, 2026):**
- CRIT-01: Fixed race condition on WS reconnection (duplicate connections)
- CRIT-02: Fixed multiple setTimeout tracking with Maps
- HIGH-06: Added branch filtering in Kitchen page
- HIGH-07: Added ROUND_CANCELED event handler
- HIGH-09: Added role verification in Kitchen page
- MED-01: Fixed memory leak from empty listener Sets
- MED-04: Limited roundStatuses growth (cleanup when all served)
- MED-06: Added table_id validation in events
- MED-08: Added debounce for TABLE_STATUS_CHANGED API calls

**Database Model Refactoring (Jan 26, 2026):**
- 28 model inconsistencies fixed across 11 files
- Added `tenant_id` to 5 catalog tables for multi-tenant isolation
- Added 8 UniqueConstraints for data integrity
- Added 7 missing relationships for FK navigation
- Added 10+ composite indexes for query performance
- See [terrible.md](terrible.md) for detailed audit report

---

## Key Architecture Modules

| Module | Purpose |
|--------|---------|
| `backend/shared/security/` | Auth, password hashing, token blacklist, rate limiting |
| `backend/shared/infrastructure/` | Database (db.py), Redis pub/sub (events/ package) |
| `backend/shared/config/` | Settings, structured logging, centralized constants |
| `backend/shared/utils/` | HTTP exceptions, input validators, health check decorators (health.py) |
| `backend/shared/utils/admin_schemas.py` | **All admin API Pydantic schemas** (CategoryOutput, ProductOutput, StaffOutput, etc.) |
| `backend/rest_api/models/` | SQLAlchemy ORM models (18 domain-specific files: base, tenant, user, catalog, allergen, etc.) |
| `backend/rest_api/core/` | App config: lifespan.py, middlewares.py, cors.py |
| `backend/rest_api/routers/` | API endpoints organized by responsibility (auth, billing, content, diner, kitchen, etc.) |
| `backend/rest_api/services/domain/` | **Clean Architecture services** (CategoryService, BranchService, TableService, ProductService, AllergenService, SectorService, SubcategoryService) |
| `backend/rest_api/services/crud/` | Repository pattern (repository.py), soft delete, audit, CRUDFactory (deprecated) |
| `backend/rest_api/services/permissions/` | Permission Strategy pattern (context.py, strategies.py, decorators.py) |
| `backend/rest_api/services/events/` | Domain events (domain_event.py, publisher.py, admin_events.py) |
| `backend/rest_api/services/payments/` | Payment processing (allocation.py, circuit_breaker.py, mp_webhook.py) |
| `backend/rest_api/services/catalog/` | Product catalog views (product_view.py, recipe_sync.py) |
| `ws_gateway/core/connection/` | Connection management (lifecycle, broadcaster, cleanup, stats) |
| `ws_gateway/core/subscriber/` | Redis subscriber (drop_tracker, validator, processor) |
| `ws_gateway/components/` | WebSocket Gateway modular architecture |

**Canonical Import Paths (Clean Architecture):**
- `from shared.infrastructure.db import get_db, SessionLocal, safe_commit`
- `from shared.config.settings import settings`
- `from shared.config.logging import get_logger, rest_api_logger`
- `from shared.security.auth import current_user_context, verify_jwt`
- `from shared.infrastructure.events import get_redis_pool, publish_event`
- `from rest_api.services.crud.soft_delete import soft_delete`
- `from shared.utils.admin_schemas import CategoryOutput, ProductOutput`  # Admin schemas
- `from rest_api.models import Product`
- `from rest_api.services.domain import ProductService, CategoryService`  # Domain services
- `from ws_gateway.core.connection import ConnectionLifecycle, ConnectionBroadcaster`  # WS modules
- `from ws_gateway.core.subscriber import EventDropRateTracker, validate_event_schema`  # WS modules

---

## WebSocket Gateway Utilities

```python
# Close codes enum (components/constants.py)
from ws_gateway.components.constants import WSCloseCode
await websocket.close(code=WSCloseCode.AUTH_FAILED, reason="Token expired")
# Available: NORMAL, GOING_AWAY, POLICY_VIOLATION, MESSAGE_TOO_BIG, SERVER_OVERLOADED, AUTH_FAILED, FORBIDDEN, RATE_LIMITED

# WSConstants for documented operational values (no magic numbers)
from ws_gateway.components.constants import WSConstants
timeout = WSConstants.WS_RECEIVE_TIMEOUT  # 90.0s - 3x heartbeat interval
max_locks = WSConstants.MAX_CACHED_LOCKS  # 500 - allows 10x growth
cleanup_threshold = WSConstants.LOCK_CLEANUP_THRESHOLD  # 400 (80% of max)
# LOW-01 FIX: Hysteresis ratio prevents "cleanup thrashing"
hysteresis = WSConstants.LOCK_CLEANUP_HYSTERESIS_RATIO  # 0.8 - reduce to 80% of threshold

# Log sanitization for user data (prevents log injection)
from ws_gateway.components.ws_context import sanitize_log_data
logger.debug("User message", data=sanitize_log_data(raw_data))

# Circuit breaker for Redis resilience
from ws_gateway.redis_subscriber import get_circuit_breaker
breaker = get_circuit_breaker()
breaker.record_failure(exception)
breaker.record_success()

# Thread-safe heartbeat tracker
from ws_gateway.components.heartbeat_tracker import HeartbeatTracker
tracker = HeartbeatTracker(timeout_seconds=60.0)
tracker.record(websocket)
stale = tracker.cleanup_stale()

# MED-WS-11 FIX: get_last_heartbeat_time default is now time.time(), not 0.0
# This prevents unknown connections from appearing "oldest" in eviction
hb_time = tracker.get_last_heartbeat_time(ws)  # Returns current time if unknown

# Subscriber metrics for monitoring
from ws_gateway.redis_subscriber import get_subscriber_metrics
metrics = get_subscriber_metrics()

# Graceful shutdown for sector repository
from ws_gateway.components import cleanup_sector_repository, reset_sector_repository
cleanup_sector_repository()  # In lifespan shutdown
reset_sector_repository()    # In tests

# Lock ordering to prevent deadlocks (MUST acquire in this order):
# 1. connection_counter_lock (global)
# 2. user_lock (per-user, ascending user_id)
# 3. branch_locks (per-branch, ascending branch_id)
# 4. sector_lock, session_lock, dead_connections_lock (global)

# ARCH-MODULAR: Modular components (from ws_gateway/core/)
from ws_gateway.core.connection import (
    ConnectionLifecycle,   # connect/disconnect logic
    ConnectionBroadcaster, # send/broadcast methods
    ConnectionCleanup,     # stale/dead connection cleanup
    ConnectionStats,       # statistics aggregation
    is_ws_connected,       # check WebSocket state
)
from ws_gateway.core.subscriber import (
    EventDropRateTracker,  # drop rate tracking with alerts
    get_drop_tracker,      # singleton tracker instance
    validate_event_schema, # event validation
    process_event_batch,   # batch processing
    handle_incoming_message, # message handling
)
```

---

## WebSocket Gateway Endpoint Classes

The ws_gateway uses a component-based architecture eliminating ~300 lines of duplicated code:

```python
# Endpoint class hierarchy
WebSocketEndpointBase (abstract)
├── JWTWebSocketEndpoint (JWT auth, periodic revalidation)
│   ├── WaiterEndpoint    # +refresh_sectors command
│   ├── KitchenEndpoint   # Receive round events
│   └── AdminEndpoint     # Full branch access
└── DinerEndpoint         # Table token auth (not JWT)

# Usage in main.py (simplified endpoints)
@app.websocket("/ws/waiter")
async def waiter_websocket(websocket: WebSocket, token: str = Query(...)):
    endpoint = WaiterEndpoint(websocket, manager, token)
    await endpoint.run()  # Handles entire lifecycle

# Creating custom endpoints
from ws_gateway.components.ws_endpoint_base import JWTWebSocketEndpoint

class CustomEndpoint(JWTWebSocketEndpoint):
    def __init__(self, websocket, manager, token):
        super().__init__(websocket, manager, "/ws/custom", token, required_roles=["ADMIN"])

    async def create_context(self, auth_data): ...
    async def register_connection(self, context): ...
    async def unregister_connection(self, context): ...
    async def handle_message(self, data): ...  # Override for custom messages

# Hook pattern for extensible message loops
class CustomJWTEndpoint(JWTWebSocketEndpoint):
    async def _pre_message_hook(self) -> bool:
        """Called before each message - return False to close connection."""
        if not self.custom_check():
            await self.websocket.close(code=WSCloseCode.FORBIDDEN)
            return False
        return True
```
