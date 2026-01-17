# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

---

## Table of Contents

1. [Project Overview](#project-overview)
2. [Quick Start Commands](#quick-start-commands)
3. [Architecture](#architecture)
   - [Data Model](#data-model)
   - [Backend API Structure](#backend-api-structure)
   - [WebSocket Events](#websocket-events-port-8001)
   - [Real-time Order Updates](#real-time-order-updates-pwamenu)
   - [WebSocket Heartbeat](#websocket-heartbeat-phase-10)
4. [Core Patterns](#core-patterns)
   - [Critical Zustand Pattern (React 19)](#critical-zustand-pattern-react-19)
   - [Dashboard Store API Pattern](#dashboard-store-api-pattern-phase-6)
5. [Test Users (Backend)](#test-users-backend)
6. [Conventions](#conventions)
7. [Documentation](#documentation)
8. [Migration Status](#migration-status)
   - [Payment Allocation](#payment-allocation-phase-10)
   - [Payment Flow (Mercado Pago)](#payment-flow-mercado-pago)
9. [Infrastructure](#infrastructure)
   - [Docker Configuration](#docker-configuration)
   - [CORS Configuration](#cors-configuration)
   - [Backend Server Notes](#backend-server-notes)
10. [January 2026 Updates](#january-2026-updates)
    - [Audit Status](#audit-status)
    - [QA Status](#qa-status)
    - [Architecture Patterns](#architecture-patterns)
    - [Soft Delete Pattern](#soft-delete-pattern)
    - [Role-Based Access Control](#role-based-access-control)
    - [Branch Management Features](#branch-management-features)
    - [Recipe Module](#recipe-module)
      - [Recipe-Product Relationship](#recipe-product-relationship-propuesta1md)
      - [Recipe Frontend Types](#recipe-frontend-types-dashboard)
    - [Canonical Product Model](#canonical-product-model)
      - [Dashboard Ingredients Page](#dashboard-ingredients-page)
    - [pwaMenu Advanced Filters](#pwamenu-advanced-filters)
    - [Enhanced Allergen Model](#enhanced-allergen-model)

---

## Project Overview

**Integrador** is a restaurant management system monorepo with four main components:

- **Dashboard** (port 5177): Admin panel for multi-branch restaurant management with 18 Zustand stores, CRUD operations with cascade delete, and 100 Vitest tests
- **pwaMenu** (port 5176): Customer-facing shared menu PWA for collaborative ordering with offline support, i18n (es/en/pt), and session-based table management
- **pwaWaiter** (port 5178): Waiter PWA for real-time table management with WebSocket updates and push notifications
- **Backend** (ports 8000/8001): FastAPI REST API + WebSocket Gateway with PostgreSQL, Redis pub/sub, and JWT authentication (table tokens migrated to JWT in Phase 10)

Each project has its own `CLAUDE.md` with detailed implementation guidance:
- [Dashboard/CLAUDE.md](Dashboard/CLAUDE.md): Store patterns, custom hooks (useFormModal, useConfirmDialog), cascade delete service, accessibility
- [pwaMenu/CLAUDE.md](pwaMenu/CLAUDE.md): Modular tableStore, React 19 patterns (useActionState, useOptimistic), PWA caching, multi-tab sync
- [pwaWaiter/CLAUDE.md](pwaWaiter/CLAUDE.md): JWT auth with WAITER role, WebSocket events, TableCard summary pattern
- [backend/README.md](backend/README.md): API endpoints, WebSocket events, test users

---

## Quick Start Commands

```bash
# Backend (requires Docker Desktop running)
# Option 1: Manual start
cd backend && docker compose up -d                    # Start PostgreSQL + Redis
cd backend && pip install -r requirements.txt         # Install Python deps
cd backend && uvicorn rest_api.main:app --reload      # REST API (port 8000)
cd backend && uvicorn ws_gateway.main:app --reload --port 8001  # WS Gateway

# Option 2: Using startup scripts (recommended)
cd backend && ./start.sh                              # Unix/Mac: starts everything
cd backend && .\start.ps1                             # Windows PowerShell: starts everything
cd backend && .\start.ps1 -ApiOnly                    # Windows: REST API only
cd backend && .\start.ps1 -SkipDocker                 # Windows: skip Docker (already running)

# Dashboard (admin panel)
cd Dashboard && npm run dev      # Dev server (port 5177)
cd Dashboard && npm run build    # Production build
cd Dashboard && npm run lint     # ESLint
cd Dashboard && npm run test     # Vitest (100 tests)

# pwaMenu (customer menu)
cd pwaMenu && npm run dev        # Dev server (port 5176)
cd pwaMenu && npm run build      # Production build
cd pwaMenu && npm run lint       # ESLint
cd pwaMenu && npm run test       # Vitest (108 tests)
cd pwaMenu && npm run test:run   # Run tests once

# pwaWaiter (waiter panel)
cd pwaWaiter && npm run dev      # Dev server (port 5178)
cd pwaWaiter && npm run build    # Production build
cd pwaWaiter && npm run lint     # ESLint

# Type checking (all frontends)
npx tsc --noEmit
```

---

## Architecture

### Data Model

```
Tenant (Restaurant)
  └── Branch (N)
        ├── Category (N) → Subcategory (N) → Product (N)
        ├── BranchSector (N) → Table (N) → TableSession → Diner (N)
        │                   → WaiterSectorAssignment (daily waiter assignments)
        │                                              → Round → RoundItem → KitchenTicketItem
        │                                                      → KitchenTicket (by station)
        ├── Check → Charge (per item/diner) → Allocation (FIFO)
        │        → Payment
        └── ServiceCall

User ←→ UserBranchRole (M:N with Branch, roles: WAITER/KITCHEN/MANAGER/ADMIN)
       └── phone, dni, hire_date (staff profile fields)
User ←→ WaiterSectorAssignment (daily sector assignments for WAITER role)
Product ←→ BranchProduct (per-branch pricing in cents)
Product ←→ ProductAllergen (M:N with presence_type + risk_level)
Recipe ←→ RecipeAllergen (M:N with risk_level)
Allergen ←→ AllergenCrossReaction (self-referential M:N for cross-reactions)
         └── is_mandatory, severity (EU 1169/2011 compliance)
Promotion ←→ PromotionBranch (M:N with Branch)
          └── PromotionItem (products + quantities)
Branch ←→ BranchCategoryExclusion (M:N with Category - marks categories NOT sold at branch)
Branch ←→ BranchSubcategoryExclusion (M:N with Subcategory - marks subcategories NOT sold at branch)
BranchSector: Global (branch_id=NULL) or per-branch, with prefix for auto-generated table codes
Diner → RoundItem (tracks who ordered what)
Recipe: Kitchen technical sheets (fichas técnicas) linked to Branch
       └── RecipeAllergen (M:N with Allergen)
       └── products[] (1:N) - Products derived from this recipe (propuesta1.md)
       └── Can be ingested into RAG chatbot via /api/recipes/{id}/ingest
Product ←→ Recipe (optional, via recipe_id + inherits_from_recipe for allergen sync)
```

### Backend API Structure

```
/api/auth/login, /me           # JWT authentication
/api/public/menu/{slug}        # Public menu (no auth)
/api/tables/{id}/session       # Create/get table session

/api/diner/*                   # Diner operations (table token auth via X-Table-Token)
  /register, /rounds/submit, /check, /service-call

/api/kitchen/*                 # Kitchen operations (JWT + KITCHEN role)
  /rounds, /rounds/{id}/status
  /tickets                       # List pending kitchen tickets by station
  /tickets/{id}                  # Get ticket details
  /tickets/{id}/status           # Update ticket status (PATCH)
  /rounds/{id}/tickets           # Generate tickets from round (POST)

/api/recipes/*                 # Recipe CRUD (JWT + KITCHEN/MANAGER/ADMIN role)
  GET /                        # List recipes (filter by branch_id, category)
  POST /                       # Create recipe
  GET /{id}                    # Get recipe details
  PATCH /{id}                  # Update recipe
  DELETE /{id}                 # Soft-delete recipe
  POST /{id}/ingest            # Ingest into RAG chatbot
  GET /categories/list         # List unique recipe categories
  POST /{id}/derive-product    # Create Product from Recipe (propuesta1.md)
  GET /{id}/products           # List products derived from recipe

/api/billing/*                 # Payment operations
  /check/request, /check/{id}/balances, /cash/pay, /mercadopago/*

/api/waiter/*                  # Waiter operations (JWT + WAITER/MANAGER/ADMIN role)
  /service-calls               # GET pending service calls for branch
  /service-calls/{id}/acknowledge  # POST acknowledge call
  /service-calls/{id}/resolve  # POST resolve/close call
  /my-assignments              # GET waiter's sector assignments for today
  /my-tables                   # GET tables in waiter's assigned sectors

/api/admin/*                   # Dashboard CRUD (JWT + role-based)
  /tenant, /branches, /categories, /subcategories
  /products, /allergens, /tables/{id}, /staff, /promotions
  /exclusions                    # Branch exclusion management (ADMIN only)
  /sectors                       # Sector management (GET, POST, DELETE)
  /tables/batch                  # Bulk table creation by sector
  /assignments                   # Daily waiter-sector assignments (GET, POST, DELETE)
  /assignments/bulk              # Bulk create/delete assignments
  /assignments/copy              # Copy assignments from one date to another
```

### WebSocket Events (port 8001)

```
/ws/waiter?token=JWT           # Waiter notifications
/ws/kitchen?token=JWT          # Kitchen notifications
/ws/diner?table_token=...      # Diner real-time updates
/ws/admin?token=JWT            # Dashboard admin notifications

Order Events: ROUND_SUBMITTED, ROUND_IN_KITCHEN, ROUND_READY, ROUND_SERVED,
              SERVICE_CALL_CREATED, CHECK_REQUESTED, CHECK_PAID, TABLE_CLEARED

Admin CRUD Events: ENTITY_CREATED, ENTITY_UPDATED, ENTITY_DELETED, CASCADE_DELETE
                   (entity_type: branch, category, subcategory, product, allergen, table, staff, promotion)

Heartbeat: Backend accepts BOTH formats for all endpoints:
  - Plain text: "ping" → responds "pong"
  - JSON: {"type":"ping"} → responds {"type":"pong"}
```

### Real-time Order Updates (pwaMenu)

pwaMenu listens for WebSocket events to update order status in real-time:

```typescript
// useOrderUpdates hook (pwaMenu/src/hooks/useOrderUpdates.ts)
// Automatically subscribed when session has backendSessionId
useOrderUpdates()

// Event flow:
// 1. Kitchen updates round status via POST /api/kitchen/rounds/{id}/status
// 2. Backend publishes event to Redis channel session:{id}
// 3. WebSocket Gateway forwards to connected diners
// 4. useOrderUpdates receives event and calls updateOrderStatus()
```

### WebSocket Heartbeat (Phase 10 + auditoria31.md)

All WebSocket connections include heartbeat mechanism with timeout detection:

```typescript
// All 3 apps: Send ping every 30s, expect pong within 10s
// Auto-reconnects on heartbeat timeout with exponential backoff

// All apps use JSON format:
ws.send('{"type":"ping"}')  // Server responds with '{"type":"pong"}'
```

**Backend WebSocket endpoints accept BOTH formats** (`ws_gateway/main.py`):
```python
# Handle heartbeat in both plain text and JSON format
if data == "ping":
    await websocket.send_text("pong")
elif data == '{"type":"ping"}':
    await websocket.send_text('{"type":"pong"}')
```

**Heartbeat Timeout Detection** (WS-31-HIGH-01):
```typescript
// All 3 apps now have timeout detection (pwaWaiter was missing, now fixed)
private sendPing(): void {
  this.ws.send(JSON.stringify({ type: 'ping' }))
  this.heartbeatTimeout = setTimeout(() => {
    this.ws?.close(4000, 'Heartbeat timeout')  // Triggers reconnect
  }, 10000)  // 10s timeout
}

// On pong received:
if (data.type === 'pong') {
  this.clearHeartbeatTimeout()
  return
}
```

**Visibility Change Handlers** (WS-31-MED-02):
All 3 apps reconnect automatically when tab becomes visible after sleep:
- Dashboard: `useWebSocketConnection.ts`
- pwaMenu: `websocket.ts`
- pwaWaiter: `websocket.ts`

---

## Core Patterns

### Critical Zustand Pattern (React 19)

All frontends enforce this pattern to avoid infinite re-renders:

```typescript
// Store definition with selectors
export const useStore = create<State>()(
  persist((set, get) => ({ ... }), { name: STORAGE_KEY })
)
export const selectItems = (state: State) => state.items

// Correct: Use selectors
const items = useStore(selectItems)
const addItem = useStore((s) => s.addItem)

// Wrong: Never destructure
// const { items } = useStore()

// For filtered arrays, use useShallow (pwaMenu) or useMemo (Dashboard)
const filtered = useMemo(() => items.filter(i => i.active), [items])
```

**CRITICAL: Avoid infinite loops in selectors (React 19 getSnapshot issue)**

```typescript
// WRONG: Creates new array on each call, causes infinite loop
export const selectBranchIds = (state: State) => state.user?.branch_ids ?? []

// CORRECT: Use stable reference for fallback
const EMPTY_ARRAY: number[] = []
export const selectBranchIds = (state: State) => state.user?.branch_ids ?? EMPTY_ARRAY
```

**CRITICAL: Memoize filtered selectors (auditoria36 WAITER-STORE-CRIT-01)**

Filtered selectors that return `.filter()` results must use manual memoization:

```typescript
// WRONG: Creates new array on EVERY call, causes infinite re-renders
export const selectTablesWithPendingRounds = (state: TablesState) =>
  state.tables.filter((t) => t.open_rounds > 0)  // NEW ARRAY EVERY CALL!

// CORRECT: Manual memoization with cache
const EMPTY_TABLES: TableCard[] = []
const pendingRoundsCache = { tables: null as TableCard[] | null, result: EMPTY_TABLES }

export const selectTablesWithPendingRounds = (state: TablesState): TableCard[] => {
  if (state.tables === pendingRoundsCache.tables) {
    return pendingRoundsCache.result  // Return cached result
  }
  const filtered = state.tables.filter((t) => t.open_rounds > 0)
  pendingRoundsCache.tables = state.tables
  pendingRoundsCache.result = filtered.length > 0 ? filtered : EMPTY_TABLES
  return pendingRoundsCache.result
}
```

### Dashboard Store API Pattern (Phase 6)

Dashboard stores support both local and async API operations. **Pages should always use the async functions** for backend integration:

```typescript
// Each store has async actions for backend integration
interface StoreState {
  items: Item[]
  isLoading: boolean
  error: string | null
  // Sync local actions (deprecated - for backwards compatibility only)
  addItem: (data: FormData) => Item
  updateItem: (id: string, data: Partial<FormData>) => void
  deleteItem: (id: string) => void
  // Async API actions (USE THESE in pages)
  fetchItems: () => Promise<void>
  createItemAsync: (data: FormData) => Promise<Item>
  updateItemAsync: (id: string, data: Partial<FormData>) => Promise<void>
  deleteItemAsync: (id: string) => Promise<void>
}

// CORRECT: Page component using async functions
function ItemsPage() {
  const fetchItems = useItemStore((s) => s.fetchItems)
  const createItemAsync = useItemStore((s) => s.createItemAsync)

  useEffect(() => {
    fetchItems()  // Fetch from backend on mount
  }, [fetchItems])

  const handleSubmit = async (data) => {
    await createItemAsync(data)  // Use async function
    toast.success('Item created')
  }
}

// Helper to convert API response to frontend format
function mapAPIItemToFrontend(apiItem: APIItem): Item {
  return {
    id: String(apiItem.id),  // API uses int, frontend uses string
    // ... map other fields
  }
}

// Fallback to local operations for non-API entities
const numericId = parseInt(id, 10)
if (isNaN(numericId)) {
  get().updateItem(id, data)  // Local-only entity
  return
}
```

**Key conversions:**
- IDs: Backend uses integers, frontend uses strings → `String(apiId)` / `parseInt(id, 10)`
- Prices: Backend uses cents, frontend uses dollars → `price_cents / 100` / `Math.round(price * 100)`
- Table status: Backend uses `FREE`/`ACTIVE`/`PAYING`/`OUT_OF_SERVICE`, Dashboard uses `libre`/`ocupada`

**User context in backend routers:**
```python
# The current_user dependency returns a dict with:
# - "sub": user ID as string (use int(user["sub"]) for integer)
# - "tenant_id": tenant ID as integer
# - "roles": list of role strings
# - "email": user email (optional, use user.get("email", ""))
# - "branch_ids": list of branch IDs

# CORRECT:
user_id = int(user["sub"])
user_email = user.get("email", "")

# WRONG (KeyError):
user_id = user["user_id"]  # ❌ Key doesn't exist
```

---

## Test Users (Backend)

| Email | Password | Role |
|-------|----------|------|
| admin@demo.com | admin123 | ADMIN |
| manager@demo.com | manager123 | MANAGER |
| kitchen@demo.com | kitchen123 | KITCHEN |
| waiter@demo.com | waiter123 | WAITER |

---

## Conventions

- **UI language**: Spanish
- **Code comments**: English
- **Theme**: Dark with orange (#f97316) accent
- **TypeScript**: Strict mode, no unused variables
- **IDs**: `crypto.randomUUID()` in frontend, BigInteger in backend
- **Prices**: Stored as cents (e.g., $125.50 = 12550)
- **Logging**: Use centralized `utils/logger.ts`, never direct console.*
- **Naming**: Frontend uses camelCase (`backendSessionId`), backend uses snake_case (`backend_session_id`)

---

## Documentation

- [gradual.md](gradual.md): Complete migration plan with phases 0-10
- [traza1.md](traza1.md): Order flow documentation from QR scan to kitchen (Spanish prose narrative explaining the complete circuit: diners → backend → waiters/kitchen/dashboard)
- [prueba.md](prueba.md): Complete test scenario narrative for Mesa T-02 Terraza with 3 diners, waiter service, kitchen flow, and payment (includes session tokens and step-by-step instructions)
- [RESULTADOS_QA.md](RESULTADOS_QA.md): QA test results
- [auditoriapwa1.md](auditoriapwa1.md): Full audit report
- [pwaWaiter/bot/planteo.md](pwaWaiter/bot/planteo.md): Canonical dish database model (19 normalized tables for allergens, ingredients, dietary profiles, sensory profiles) - serves as data source for pwaMenu filters and RAG chatbot ingestion
- [pwaWaiter/bot/producto1.md](pwaWaiter/bot/producto1.md): Analysis of current product model (9 tables) with limitations for nutritional queries - comparison with planteo.md canonical model
- [pwaWaiter/bot/producto2.md](pwaWaiter/bot/producto2.md): Technical report comparing producto1.md requirements with actual implementation - identifies completed features (65%) and remaining gaps
- [pwaWaiter/bot/producto3.md](pwaWaiter/bot/producto3.md): Final audit confirming 100% completion of canonical model - all 6 gaps from producto2.md closed, comprehensive implementation verification
- [pwaWaiter/bot/propuesta1.md](pwaWaiter/bot/propuesta1.md): Architectural proposal for Recipe-Product relationship - recommends optional linking instead of mandatory "Recipe First" approach
- [pwaWaiter/bot/canonico.txt](pwaWaiter/bot/canonico.txt): JSON schema for canonical dish structure (original format before normalization)
- [REPORTE_TRAZABILIDAD.md](REPORTE_TRAZABILIDAD.md): Complete traceability report (January 2026) with test traces for all frontend pages, Redis anomaly fix, and performance analysis
- [ARQUITECTURA_AUDIT_2026.md](ARQUITECTURA_AUDIT_2026.md): Comprehensive architectural audit (47 defects: 3 critical, 20 high, 19 medium, 5 low) with fixes for N+1 queries, WebSocket patterns, SSRF protection, race conditions
- [auditoria27.md](auditoria27.md): Complete architectural audit (76 defects: 14 critical, 23 high, 31 medium, 8 low) - **ALL FIXED** - Redis connection management, memory leaks, N+1 queries, safe_commit pattern, unused imports cleanup
- [auditoria28.md](auditoria28.md): Complete architectural audit (95 defects: 18 critical, 27 high, 31 medium, 19 low) - **ALL FIXED** - Race conditions, N+1 queries, memory leaks, event publishing, token synchronization, component memoization
- [auditoria29.md](auditoria29.md): Exhaustive architectural audit (65 defects: 7 critical, 20 high, 22 medium, 16 low) - **ALL FIXED** - Race conditions, memory leaks, Zustand anti-patterns, BroadcastChannel sync, token refresh concurrency
- [auditoria30.md](auditoria30.md): Redis and WebSocket architectural audit (20 defects: 2 critical, 5 high, 8 medium, 5 low) - **15/20 FIXED, 5 ACCEPTED** - Token refresh race conditions, simultaneous connections, exponential backoff, ref patterns for WebSocket subscriptions
- [auditoria31.md](auditoria31.md): WebSocket architectural analysis (11 improvements: 0 critical, 2 high, 5 medium, 4 low) - **10/11 FIXED, 1 DEFERRED** - Heartbeat timeout detection, soft/hard disconnect, visibility handlers, HMR cleanup guards, connectionPromise cleanup
- [auditoria32.md](auditoria32.md): End-to-end test traces and defect analysis (82 defects: 20 critical, 25 high, 23 medium, 14 low) - **ALL FIXED** - Token blacklist verification, email-based rate limiting, bcrypt-only passwords, tenant isolation, race conditions fixed, audit trail with proper user_id extraction, N+1 queries resolved
- [auditoria35.md](auditoria35.md): Exhaustive code audit (121 defects: 31 critical, 37 high, 31 medium, 22 low) - **ALL FIXED** - Dashboard stores/hooks, Backend routers/services, WebSocket Gateway - comprehensive audit with verified fixes (CRIT-XX FIX, HIGH-XX FIX, WS-CRIT-XX FIX patterns)
- [auditoria36.md](auditoria36.md): Exhaustive pwaMenu/pwaWaiter audit (135 defects: 8 critical, 29 high, 61 medium, 37 low) - **ALL FIXED** - Stores, hooks, services, components, pages - React 19 selector patterns, IndexedDB timeouts, focus trap modals, isMounted guards
- [auditoria34.md](auditoria34.md): Execution traces audit (4 main traces) - **APPROVED** - Circuit breaker for Mercado Pago, webhook retry queue, batch inserts for round items

---

## Migration Status

See [gradual.md](gradual.md) for the complete migration plan. Current status:
- **Phase 0-5**: Complete (infrastructure, models, REST API, WebSocket, kitchen, billing)
- **Phase 6**: Complete (Dashboard backend connection)
  - ✅ API service layer (`Dashboard/src/services/api.ts`)
  - ✅ Auth store (`Dashboard/src/stores/authStore.ts`)
  - ✅ Login page + ProtectedRoute
  - ✅ All stores migrated: branch, category, subcategory, product, table, staff, allergen, promotion, restaurant
  - ✅ All mock data removed - stores start empty and fetch from backend API
  - ✅ Staff fields: phone, dni, hire_date now persisted in backend User model
- **Phase 7**: Complete (RAG Chatbot)
  - ✅ KnowledgeDocument + ChatLog models with pgvector (`backend/rest_api/models.py`)
  - ✅ RAG service with Ollama integration (`backend/rest_api/services/rag_service.py`)
  - ✅ RAG endpoints: POST /api/chat, POST /api/admin/rag/ingest, GET /api/rag/health
  - ✅ pwaMenu AIChat connected to backend with mock fallback
- **Phase 8**: Complete (PWA for waiters)
  - ✅ pwaWaiter project structure (port 5178)
  - ✅ Auth store with JWT login (WAITER role validation)
  - ✅ Tables store with real-time WebSocket updates
  - ✅ TableGrid main screen with status grouping
  - ✅ TableDetail page with session summary
  - ✅ Push notifications for service calls and check requests
- **Phase 9**: Complete (pwaMenu backend integration)
  - ✅ Backend types (`pwaMenu/src/types/backend.ts`)
  - ✅ Table token authentication (`X-Table-Token` header in API service)
  - ✅ WebSocket service for diners (`pwaMenu/src/services/websocket.ts`)
  - ✅ Session store with backend integration (`pwaMenu/src/stores/sessionStore.ts`)
  - ✅ Menu store with caching (`pwaMenu/src/stores/menuStore.ts`)
  - ✅ tableStore updated: `joinTable()`, `submitOrder()`, `closeTable()` now async with backend calls
  - ✅ Real-time order updates via `useOrderUpdates` hook
  - ✅ Vitest tests (108 tests: helpers, menuStore, api service, tableStore)
  - ✅ All mock data removed - pwaMenu consumes backend only (no MOCK_TABLES, MOCK_WAITERS, simulated delays)
  - ✅ Mercado Pago integration via `billingAPI.createMercadoPagoPreference({check_id})`
  - ✅ Simplified close table flow: `requesting` → `bill_ready` (no simulated waiter states)
- **Phase 10**: Complete (Architecture improvements from pwamejora.md)
  - ✅ Frontend naming normalized to camelCase (`pwaMenu/src/types/session.ts`)
  - ✅ Persistent `Diner` model with backend registration (`backend/rest_api/models.py`)
  - ✅ Diner API: `POST /api/diner/register` with idempotency via `local_id`
  - ✅ `joinTable()` now registers diner with backend (`backendDinerId` stored)
  - ✅ `Charge` and `Allocation` models for FIFO payment allocation
  - ✅ `GET /api/billing/check/{id}/balances` for per-diner payment breakdown
  - ✅ `KitchenTicket` and `KitchenTicketItem` models for station-based kitchen workflow
  - ✅ WebSocket heartbeat (30s ping/pong with 10s timeout)
  - ✅ Table tokens migrated from HMAC to JWT (backward compatible)

### Payment Allocation (Phase 10)

The billing system uses FIFO allocation for split payments:

```python
# backend/rest_api/services/allocation.py
# When check is requested:
create_charges_for_check(db, check)  # Creates Charge per RoundItem

# When payment is made:
allocate_payment_fifo(db, payment)  # Allocates to oldest unpaid charges first

# Query diner balances:
get_all_diner_balances(db, check_id)  # Returns per-diner totals/paid/remaining
```

### Payment Flow (Mercado Pago)

```typescript
// 1. User requests bill → closeTable() stores checkId
const result = await closeTable()  // Returns { success, checkId }
// Session now has backendCheckId
// Note: billingAPI.requestCheck() requires no params - session_id extracted from X-Table-Token

// 2. User selects Mercado Pago → creates preference via backend
const preference = await billingAPI.createMercadoPagoPreference({ check_id: checkId })

// 3. Redirect to MP checkout
window.location.href = isTestMode() ? preference.sandbox_init_point : preference.init_point

// 4. MP webhook notifies backend (POST /api/billing/mercadopago/webhook)
// Backend updates Payment status and publishes CHECK_PAID event
```

**Environment variables for Mercado Pago:**
- `VITE_MP_PUBLIC_KEY`: Test credentials start with `TEST-`, production with `APP_USR-`
- Backend `MP_ACCESS_TOKEN`: Never expose in frontend

---

## Infrastructure

### Docker Configuration

The backend uses Docker for PostgreSQL and Redis. Configuration details:

```yaml
# docker-compose.yml services:
PostgreSQL: localhost:5432 (pgvector/pgvector:pg16)
  - Database: menu_ops
  - User: postgres / postgres
  - Includes pgvector extension for RAG

Redis: localhost:6380 (redis:7-alpine)
  - NOTE: Exposed on port 6380 (not 6379) to avoid conflicts
  - Application .env must have: REDIS_URL=redis://localhost:6380
```

**Startup order:**
1. Start Docker Desktop (required)
2. Run `docker compose up -d` in backend/
3. Start REST API: `uvicorn rest_api.main:app --reload`
4. Start WS Gateway: `uvicorn ws_gateway.main:app --reload --port 8001`

**Health checks:**
```bash
# Check containers
docker compose ps

# Check all dependencies
curl http://localhost:8000/api/health/detailed
```

**Database indexes:** All indexes are created automatically on startup via `Base.metadata.create_all()`. No manual migrations needed.

**Database Reset/Cleanup:**
```bash
# Option 1: Full reset (removes all data, recreates containers)
docker compose down -v && docker compose up -d
# Then restart REST API to run seed()

# Option 2: Truncate all tables (keeps schema, removes data)
docker exec integrador_db psql -U postgres -d menu_ops -c "
TRUNCATE allocation, kitchen_ticket_item, charge, kitchen_ticket, payment,
\"check\", round_item, service_call, \"round\", diner, table_session, chat_log,
restaurant_table, promotion_item, promotion_branch, promotion, branch_product,
knowledge_document, user_branch_role, product, subcategory, category,
app_user, branch, allergen, tenant, audit_log CASCADE;
"

# Option 3: Query database directly
docker exec integrador_db psql -U postgres -d menu_ops -c "SELECT COUNT(*) FROM branch;"
```

**Note:** After truncating, restart the REST API to re-run `seed()` and create demo data (tenant, users, branches, etc.).

**Seed Modelo Script:**
```bash
# Create full model restaurant with categories, subcategories, and products
cd backend && python seed_modelo.py

# Creates:
# - Tenant: "El Buen Sabor"
# - 4 Branches: Centro, Godoy Cruz, Guaymallén, Las Heras
# - 4 Users with roles in all branches (admin, manager, kitchen, waiter)
# - 32 Tables (8 per branch: 5 in main area, 3 in terrace)
# - 20 Allergens (14 mandatory EU + 6 optional) with cross-reactions
# - 5 Categories: Entradas, Platos Principales, Pizzas y Empanadas, Postres, Bebidas
# - 15 Subcategories (3 per category)
# - 75 Products (5 per subcategory) with pricing in all branches
```

### CORS Configuration

When adding new frontend apps, add the origin to `backend/rest_api/main.py`:

```python
allow_origins=[
    "http://localhost:5173",  # Vite default
    "http://localhost:5176",  # pwaMenu
    "http://localhost:5177",  # Dashboard
    "http://localhost:5178",  # pwaWaiter
    "http://localhost:5179",  # Dashboard alternate port
    "http://localhost:5180",  # Future use
],
allow_credentials=True,
allow_methods=["*"],
allow_headers=["*"],
expose_headers=["*"],  # Required for frontend to read response headers
```

**Frontend fetch configuration** (`Dashboard/src/services/api.ts`):
```typescript
// Include credentials for CORS requests with cookies/auth
const response = await fetch(url, {
  ...options,
  headers,
  credentials: 'include',  // Required for cross-origin requests
})
```

After modifying CORS, restart the backend server (changes require full restart, not just reload).

### Backend Server Notes

After modifying backend routers, restart the uvicorn server to load new routes:

```bash
# Stop existing server (Ctrl+C), then:
cd backend
uvicorn rest_api.main:app --reload --port 8000
```

Verify routes are loaded:
```bash
curl http://localhost:8000/openapi.json | grep "/api/admin"
```

---

## January 2026 Updates

This section consolidates all features and fixes implemented in January 2026.

### Audit Status

See [auditoriapwa1.md](auditoriapwa1.md) for full audit report. All critical and high priority issues have been resolved, including the 82 defects identified in auditoria32.md.

#### Exhaustive Code Audit (auditoria35.md) - COMPLETED

See [auditoria35.md](auditoria35.md) for the exhaustive code audit covering Dashboard stores/hooks, Backend routers/services, and WebSocket Gateway. **121 defects identified and ALL 121 fixed:**

#### Exhaustive pwaMenu/pwaWaiter Audit (auditoria36.md) - COMPLETED

See [auditoria36.md](auditoria36.md) for the exhaustive audit of pwaMenu and pwaWaiter applications. **135 defects identified and ALL 135 fixed:**

| Severity | Count | Status |
|----------|-------|--------|
| CRITICAL | 8 | ✅ Fixed |
| HIGH | 29 | ✅ Fixed |
| MEDIUM | 61 | ✅ Fixed |
| LOW | 37 | ✅ Fixed |

**Key Fixes:**
- **WAITER-STORE-CRIT-01**: React 19 selector memoization for stable array references
- **WAITER-SVC-CRIT-03**: Memory leak prevention in recentNotifications Set (100 item limit)
- **MENU-HOOK-CRIT-01**: isMounted guard for async fetch in useAllergenFilter
- **WAITER-SVC-MED-02**: IndexedDB timeout wrapper (30s) for all operations
- **WAITER-COMP-CRIT-01/02**: Focus trap and focus restoration in ConfirmDialog

| Severity | Count | Status |
|----------|-------|--------|
| CRITICAL | 31 | ✅ Fixed |
| HIGH | 37 | ✅ Fixed |
| MEDIUM | 31 | ✅ Fixed |
| LOW | 22 | ✅ Fixed |

**Components Audited:**
- Dashboard Stores (37 defects): branchStore, tableStore, authStore, productStore, promotionStore, allergenStore, categoryStore, subcategoryStore, ingredientStore, restaurantStore
- Dashboard Hooks (13 defects): usePagination, useWebSocketConnection, useAdminWebSocket
- Backend Routers (21 defects): admin/ (modular), catalog.py, tables.py, billing.py, diner.py
- Backend Services (26 defects): allocation.py, rag_service.py, product_view.py, circuit_breaker.py, webhook_retry.py
- WebSocket Gateway (24 defects): connection_manager.py, main.py, redis_subscriber.py

**Key Fixes Verified:**
- `CRIT-XX FIX:` comments in all affected files
- `HIGH-XX FIX:` for high priority defects
- `WS-CRIT-XX FIX:` / `WS-HIGH-XX FIX:` for WebSocket issues
- `SVC-CRIT-XX FIX:` for service layer issues
- `MED-XX FIX:` for medium priority improvements

#### Comprehensive Audit (auditoria27.md) - COMPLETED

See [auditoria27.md](auditoria27.md) for the comprehensive architectural audit. **76 defects identified and ALL 76 fixed:**

| Severity | Count | Status |
|----------|-------|--------|
| CRITICAL | 14 | ✅ Fixed |
| HIGH | 23 | ✅ Fixed |
| MEDIUM | 31 | ✅ Fixed |
| LOW | 8 | ✅ Fixed |

#### Additional Audit (auditoria29.md) - COMPLETED

See [auditoria29.md](auditoria29.md) for exhaustive audit. **65 defects identified and ALL 65 fixed:**

| Severity | Count | Status |
|----------|-------|--------|
| CRITICAL | 7 | ✅ Fixed |
| HIGH | 20 | ✅ Fixed |
| MEDIUM | 22 | ✅ Fixed |
| LOW | 16 | ✅ Fixed |

**Key Fixes:**
- **CRIT-29-01**: Race condition in diner.py - Added SELECT FOR UPDATE for round submission
- **CRIT-29-02**: Memory leak in retryQueueStore - Added listener registration guard
- **CRIT-29-03**: Memory leak in offline.ts - Added listener registration guard
- **CRIT-29-04**: Race condition in historyStore - Synchronous BroadcastChannel init
- **CRIT-29-05**: Cyclic dependencies in useAdvancedFilters - Extracted stable references
- **CRIT-29-06**: Redis string handling in token_blacklist - Removed unnecessary decode
- **CRIT-29-07**: Async context handling in blacklist_token_sync - Used ensure_future
- **HIGH-29-18**: Token refresh race condition - Added isRefreshing flag
- **HIGH-29-19**: WebSocket reconnect race - Reset isIntentionalClose before connect

#### Redis & WebSocket Audit (auditoria30.md) - COMPLETED

See [auditoria30.md](auditoria30.md) for exhaustive Redis and WebSocket analysis. **20 defects identified, 15 fixed, 5 accepted:**

| Severity | Count | Status |
|----------|-------|--------|
| CRITICAL | 2 | ✅ Fixed |
| HIGH | 5 | ✅ Fixed |
| MEDIUM | 8 | ✅ Fixed |
| LOW | 5 | ⚠️ Accepted |

**Backend Redis Architecture: ✅ PRODUCTION-READY**
- Singleton pool pattern with proper lifecycle
- 4-channel pub/sub system (waiters, kitchen, admin, diners)
- Cache with TTL auto-cleanup
- Token blacklist with automatic expiration

**Frontend WebSocket: ✅ PRODUCTION-READY**
- **WS-CRIT-01**: Token refresh race condition in pwaWaiter - Added delay before reconnect
- **WS-CRIT-02**: Simultaneous connections in Dashboard - Changed ref to useState
- **WS-HIGH-02**: Exponential backoff now in all 3 apps (was linear in pwaWaiter)
- **WS-HIGH-05**: TableDetail re-subscription - Applied ref pattern
- **WS-MED-01**: useTableWebSocket re-renders - Applied ref pattern for stable callbacks
- **WS-MED-02**: Wildcard listener duplicates in pwaMenu - Added event type filter
- **WS-MED-03**: WSEvent types incomplete - Made branch_id/table_id optional
- **WS-MED-04**: Visibility listener memory leak - Cleanup before setup

#### WebSocket Architectural Analysis (auditoria31.md) - COMPLETED

See [auditoria31.md](auditoria31.md) for comprehensive WebSocket analysis. **11 improvements identified, 10 implemented:**

| Severity | Count | Status |
|----------|-------|--------|
| CRITICAL | 0 | N/A |
| HIGH | 2 | ✅ Fixed |
| MEDIUM | 5 | ✅ Fixed |
| LOW | 4 | ✅ 3 Fixed, 1 Deferred |

**WebSocket Architecture: ✅ PRODUCTION-READY AND FULLY OPTIMIZED**

**Key Fixes:**
- **WS-31-HIGH-01**: pwaWaiter heartbeat timeout detection - Added sendPing with 10s timeout
- **WS-31-HIGH-02**: Dashboard soft/hard disconnect - Added softDisconnect() preserving listeners
- **WS-31-MED-01**: Consistent pong handling - pwaWaiter now handles pong like other apps
- **WS-31-MED-02**: pwaWaiter visibility handler - Reconnects after sleep/background
- **WS-31-MED-03**: connectionPromise cleanup - Clear on error/close for proper reconnect
- **WS-31-MED-04**: Backend logs unknown messages - All 4 endpoints log with debug level
- **WS-31-MED-05**: HMR cleanup guards - All WebSocket hooks clean up on hot reload
- **WS-31-LOW-01**: Synchronized constants - All apps use same reconnect/heartbeat values
- **WS-31-LOW-02**: getLastPongAge() - Debugging helper for connection health
- **WS-31-LOW-03**: Metrics/observability - DEFERRED (future production enhancement)

#### End-to-End Test Traces (auditoria32.md) - ✅ COMPLETED

See [auditoria32.md](auditoria32.md) for comprehensive end-to-end test traces. **82 defects identified and ALL FIXED:**

| Severity | Count | Status |
|----------|-------|--------|
| CRITICAL | 20 | ✅ Fixed |
| HIGH | 25 | ✅ Fixed |
| MEDIUM | 23 | ✅ Fixed |
| LOW | 14 | ✅ Fixed |

**Key Security Fixes (CRITICAL):**

| ID | Fix Applied | File |
|----|-------------|------|
| CRIT-AUTH-01 | `verify_jwt()` now checks token blacklist via `is_token_revoked(jti)` | `shared/auth.py` |
| CRIT-AUTH-02 | Added email-based rate limiting (`@email_limiter.limit("5/minute")`) | `routers/auth.py` |
| CRIT-AUTH-03 | Removed plaintext password support, bcrypt-only | `shared/password.py` |
| CRIT-AUTH-04 | JWT now includes "jti" claim for individual token revocation | `shared/auth.py` |
| CRIT-AUTH-05 | Tenant isolation validation - all branches must belong to user's tenant | `routers/auth.py` |
| CRIT-ADMIN-01 | Fixed audit trail with `get_user_id(ctx)` helper using `int(ctx["sub"])` | `routers/admin_base.py` |
| CRIT-RACE-01 | Added `SELECT FOR UPDATE` in session creation | `routers/tables.py` |
| CRIT-IDEMP-01 | Idempotency keys stored in Redis with configurable TTL | `routers/diner.py` |
| CRIT-DB-01/02/03 | Made tenant_id NOT NULL in all M:N tables | `models.py` |
| CRIT-WS-07/10/11 | Events with sector_id now dispatch to both sector AND branch channels | `shared/events.py` |
| CRIT-WS-09 | Redis subscriber uses connection pool instead of standalone | `ws_gateway/redis_subscriber.py` |
| CRIT-ALG-01 | FIFO allocation algorithm fixed with proper charge ordering | `services/allocation.py` |

**Key Database Integrity Fixes (HIGH/MEDIUM):**

| ID | Fix Applied | File |
|----|-------------|------|
| HIGH-DB-01 | Partial unique index for global sectors (branch_id IS NULL) | `models.py` |
| HIGH-DB-02 | Exclusive waiter assignment constraint (one sector per waiter per shift) | `models.py` |
| HIGH-AUTH-05 | Login/logout events logged with structured logging | `routers/auth.py` |
| HIGH-VALID-02 | Check constraints for total_cents, paid_cents validation | `models.py` |
| HIGH-EVENT-01 | N+1 queries fixed with selectinload/joinedload | `routers/recipes.py`, `routers/diner.py` |
| MED-IDX-01 | Composite index on Allocation(charge_id, payment_id) | `models.py` |
| MED-CONS-01/02/03 | Check constraints: paid ≤ total, non-negative amounts | `models.py` |

**Authentication Security Pattern:**
```python
# shared/auth.py - Token blacklist verification
def verify_jwt(token: str) -> dict:
    payload = jwt.decode(token, settings.jwt_secret, algorithms=[settings.jwt_algorithm])
    jti = payload.get("jti")
    if jti and is_token_revoked(jti):
        raise HTTPException(status_code=401, detail="Token has been revoked")
    return payload

# shared/password.py - Bcrypt-only (no plaintext)
def verify_password(plain_password: str, hashed_password: str) -> bool:
    if not hashed_password.startswith(("$2a$", "$2b$", "$2y$")):
        logger.warning("SECURITY: Non-bcrypt password hash detected")
        return False
    return pwd_context.verify(plain_password, hashed_password)
```

**Email-based Rate Limiting Pattern:**
```python
# routers/auth.py - Prevents credential stuffing from distributed IPs
@router.post("/login")
@limiter.limit("5/minute")           # IP-based
@email_limiter.limit("5/minute")     # Email-based
def login(request: Request, body: LoginRequest):
    set_rate_limit_email(request, body.email)  # Set email for rate limit key
    # ... authentication logic ...
```

**Audit Trail Pattern:**
```python
# routers/admin_base.py - Proper user_id extraction from JWT
def get_user_id(ctx: dict) -> int:
    return int(ctx["sub"])  # NOT ctx.get("user_id") which returns None

def get_user_email(ctx: dict) -> str:
    return ctx.get("email", "")
```

#### Comprehensive Audit (auditoria28.md) - COMPLETED

See [auditoria28.md](auditoria28.md) for the full architectural audit. **95 defects identified and ALL 95 fixed:**

| Severity | Count | Status |
|----------|-------|--------|
| CRITICAL | 18 | ✅ Fixed |
| HIGH | 27 | ✅ Fixed |
| MEDIUM | 31 | ✅ Fixed |
| LOW | 19 | ✅ Fixed |

**Key Fixes:**
- **CRIT-01**: Race condition in MP webhook - Added `SELECT FOR UPDATE`
- **CRIT-03**: N+1 queries in kitchen_tickets.py - Batch fetching with eager loading
- **CRIT-05**: Race condition in cleanup - Used `list()` snapshot
- **CRIT-10**: Memory leak in Dashboard WebSocket - Clear listeners in `disconnect()`
- **CRIT-12**: Zustand selector anti-pattern - Stable empty array references
- **HIGH-01**: Branch validation in product update
- **HIGH-02**: Consistent event publishing to all channels
- **HIGH-07**: Token sync between api.ts and websocket.ts
- **MED-08**: WebSocket event type constants in pwaWaiter

#### Architectural Audit (ARQUITECTURA_AUDIT_2026.md)

See [ARQUITECTURA_AUDIT_2026.md](ARQUITECTURA_AUDIT_2026.md) for comprehensive architectural audit. **47 defects identified and 12 critical/high fixed:**

**CRITICAL (Fixed):**
- N+1 queries in `recipes.py` and `diner.py` - Added eager loading with `selectinload`/`joinedload`
- Dashboard WebSocket not connected globally - Added `useWebSocketConnection` hook in Layout

**HIGH (Fixed):**
- Backend commit error handling - Added try-except with rollback in billing.py, diner.py
- Backend race condition - Added `SELECT FOR UPDATE` in billing.py
- Backend tenant validation - Added branch_id change validation in recipes.py
- Dashboard listener accumulation - Refactored `useAdminWebSocket` with useRef pattern
- pwaWaiter SSRF protection - Added `isValidApiBase()` validation
- Backend async/sync mismatch - Fixed event publishing patterns

**Files Modified:**
- `Dashboard/src/hooks/useWebSocketConnection.ts` (created)
- `Dashboard/src/hooks/useAdminWebSocket.ts`
- `Dashboard/src/components/layout/Layout.tsx`
- `backend/rest_api/routers/billing.py`
- `backend/rest_api/routers/diner.py`
- `backend/rest_api/routers/recipes.py`
- `pwaWaiter/src/services/api.ts`
- `pwaWaiter/src/utils/constants.ts`

#### Resolved Issues
- ✅ **Backend Event Publishing**: `publish_round_event()`, `publish_service_call_event()`, and `publish_check_event()` now publish to **4 channels**: waiters, kitchen, admin (Dashboard), and session (diners). See `backend/shared/events.py`.
- ✅ **Payment Allocation**: MP webhook calls `allocate_payment_fifo()` after payment creation
- ✅ **pwaMenu Selectors**: Normalized to camelCase (`sharedCart`, `dinerId`, `backendRoundId`)
- ✅ **pwaMenu Payment Flow**: `useCloseTableFlow` calls `dinerAPI.createServiceCall({ type: 'PAYMENT_HELP' })`
- ✅ **pwaWaiter Events**: All 9 events mapped (ROUND_SUBMITTED, ROUND_IN_KITCHEN, ROUND_READY, ROUND_SERVED, SERVICE_CALL_CREATED, CHECK_REQUESTED, CHECK_PAID, TABLE_CLEARED, PAYMENT_APPROVED)
- ✅ **Dashboard WebSocket**: `tableStore.ts` has `subscribeToTableEvents()` for real-time table updates
- ✅ **Exponential Backoff**: All 3 apps (Dashboard, pwaMenu, pwaWaiter) use exponential backoff with jitter
- ✅ **Heartbeat Timeout**: All 3 apps detect stale connections via 10s pong timeout (WS-31-HIGH-01)
- ✅ **Visibility Handlers**: All 3 apps reconnect when tab becomes visible after sleep (WS-31-MED-02)
- ✅ **HMR Cleanup**: All WebSocket hooks have HMR cleanup guards for development (WS-31-MED-05)
- ✅ **Session Expiry**: pwaMenu API service handles 401 with `onSessionExpired()` callback
- ✅ **Rate Limiting**: Backend uses slowapi for rate limiting on public endpoints
- ✅ **Refresh Tokens**: `POST /api/auth/refresh` endpoint implemented
- ✅ **Cascade Delete Preview**: Dashboard shows affected items before deletion via `CascadePreviewList`
- ✅ **Duplicate Validation**: `validateProduct()` and `validateStaff()` check for duplicates

#### Dashboard Real-time Updates

```typescript
// Dashboard/src/stores/tableStore.ts
// Subscribe to WebSocket events for table state changes
const unsubscribe = useTableStore.getState().subscribeToTableEvents()
// Call in useEffect cleanup: return () => unsubscribe()

// Events handled: TABLE_CLEARED, TABLE_STATUS_CHANGED, ROUND_SUBMITTED,
//                 ROUND_SERVED, CHECK_REQUESTED, CHECK_PAID
```

#### Dashboard Admin CRUD Sync (DEF-HIGH-01 Fix)

```typescript
// Dashboard/src/hooks/useAdminWebSocket.ts
// Auto-sync stores when other users create/update/delete entities
import { useAdminWebSocket } from '../hooks/useAdminWebSocket'

function AdminPage() {
  useAdminWebSocket({
    onEntityDeleted: (type, id) => console.log(`${type} ${id} deleted by another user`)
  })
  // Stores auto-refresh on ENTITY_CREATED/UPDATED
  // Entities auto-removed on ENTITY_DELETED/CASCADE_DELETE
}

// Backend publishes events from admin/ delete endpoints:
// - publish_entity_deleted() for single entity
// - publish_cascade_delete() with affected_entities list for cascades
```

#### New Features by App

**pwaMenu (audi2pwa.md audit):**
- `CallWaiterModal.tsx`: Connected to backend via `dinerAPI.createServiceCall()` (C001)
- `useServiceCallUpdates.ts`: Real-time service call status updates via WebSocket (A001)
- `MercadoPagoPayment.tsx`: Split payment support with per-diner amounts (A002)
- `serviceCallHistoryStore.ts`: Persistent service call history with timestamps (M001)
- `CloseStatusView.tsx`: Paid amount indicator with green badge (M002)
- `tableStore/types.ts`: `DinerPayment` interface for per-diner balance tracking (M003)
- `tableStore/store.ts`: `recordDinerPayment()`, `getDinerPaidAmount()` for payment tracking
- `DinersList.tsx`: Balance display per diner (paid/remaining amounts)
- `index.css`: CSS animations for payment states (`pulse-ring`, `status-enter`, `icon-pop`, `checkmark-draw`) (L001)
- `notificationSound.ts`: Web Audio API notification sounds for order ready, waiter coming (L002)
- `useOrderUpdates.ts`: Plays notification sound on `ROUND_READY` and `ROUND_IN_KITCHEN` events

**pwaWaiter (waiteraudi1.md audit):**
- `backend/rest_api/routers/waiter.py`: Service call endpoints (GET list, POST acknowledge, POST resolve)
- `TABLE_SESSION_STARTED` event published when diner scans QR
- `retryQueueStore.ts`: Offline action queue with automatic retry on reconnect
- `ConnectionBanner.tsx`: Prominent disconnection warning banner
- WebSocket token refresh mechanism (1 minute before expiry)
- `historyStore.ts`: BroadcastChannel sync between tabs, localStorage persistence
- Alert sound for urgent notifications (SERVICE_CALL_CREATED, CHECK_REQUESTED, ROUND_READY)
- TableDetail real-time updates via WebSocket listener
- Round filter tabs (All/Pending/Ready/Served)
- `UI_CONFIG` constants for magic numbers (pull threshold, refresh interval, etc.)
- PWA manifest enhanced with shortcuts and screenshots

**Dashboard (audi2das.md audit):**
- `Reports.tsx`: Sales reports page with charts and CSV export
- `exportCsv.ts`: Generic CSV export utility with Excel BOM support
- `useKeyboardShortcuts.ts`: Mac/Windows keyboard shortcuts hook
- `useSystemTheme.ts`: OS theme preference detection
- `promotionStore.ts`: Full backend integration with `promotionAPI` (C001)
- `restaurantStore.ts`: Connected to `tenantAPI.get()` and `tenantAPI.update()` (C002)
- `staffAPI.get(id)`: New endpoint for fetching single staff member (C003)
- User model: Added `phone`, `dni`, `hire_date` fields to backend (D004)
- `promotions.py`: New router with full CRUD for Promotion, PromotionBranch, PromotionItem

**Backend:**
- `kitchen_tickets.py`: KitchenTicket CRUD endpoints (group round items by station)
- `promotions.py`: Promotion CRUD with branch and item associations

### Dashboard-Backend Consistency

When adding new endpoints, ensure consistency between:
- `Dashboard/src/services/api.ts` (frontend API calls)
- `backend/rest_api/routers/*.py` (backend endpoints)
- `backend/rest_api/main.py` (router registration)

**Common inconsistencies to check:**
1. **Missing endpoints**: Dashboard calls an endpoint that doesn't exist in backend
2. **Response type mismatch**: Frontend expects different structure than backend returns
3. **Router not registered**: Router file exists but not included in `main.py`

**Verification commands:**
```bash
# List all Dashboard API endpoints
grep -E "async \w+\(" Dashboard/src/services/api.ts | head -50

# List all backend routes
curl http://localhost:8000/openapi.json | jq '.paths | keys'

# Check router registrations
grep "include_router" backend/rest_api/main.py
```

**Recent fixes (January 2026):**
- Added `GET /api/admin/tables/{table_id}` (was missing, Dashboard called it)
- Registered `kitchen_tickets_router` in `main.py` (file existed but wasn't registered)
- Fixed recipe ingest response type (backend returns `RecipeOutput`, not `{success, message}`)
- **CRITICAL FIX**: Removed `await redis.close()` from all routers (was closing pooled connections)
  - Affected files: diner.py, billing.py, kitchen.py, tables.py, waiter.py, kitchen_tickets.py
  - 11 occurrences fixed - pool now manages connection lifecycle correctly
- **auditoria34.md improvements** (execution traces audit):
  - Added circuit breaker for Mercado Pago API (`rest_api/services/circuit_breaker.py`)
  - Added webhook retry queue with exponential backoff (`rest_api/services/webhook_retry.py`)
  - Added batch inserts for round_items in `diner.py` (prevents N+1 queries)
  - Health check now includes circuit breaker stats and retry queue stats

### QA Status

See [RESULTADOS_QA.md](RESULTADOS_QA.md) and [todaslasTraza.md](todaslasTraza.md) for full QA reports.

#### Test Results (January 2026)
| App | Tests | Status |
|-----|-------|--------|
| Dashboard | 100 | ✅ PASSED |
| pwaMenu | 108 | ✅ PASSED |
| pwaWaiter | 74 | ✅ PASSED |
| Backend (pytest) | 25+ | ✅ PASSED |

All builds verified after auditoria29.md fixes.

#### Running Individual Tests

```bash
# Dashboard - run single test file
cd Dashboard && npm run test -- src/utils/validation.test.ts

# Dashboard - run tests matching pattern
cd Dashboard && npm run test -- --grep "validates email"

# pwaMenu - run single test file
cd pwaMenu && npm run test -- src/stores/tableStore/store.test.ts

# pwaMenu - run tests once (no watch)
cd pwaMenu && npm run test:run

# pwaMenu - run with coverage
cd pwaMenu && npm run test -- --coverage
```

#### Resolved Defects

**CRITICAL (Fixed):**
- **DEF-CRIT-01**: Product validation before submitOrder (`pwaMenu/src/stores/tableStore/store.ts`)
- **DEF-CRIT-03**: WebSocket `visibilitychange` listener for reconnection after sleep (`pwaMenu/src/services/websocket.ts`)

**HIGH (Fixed):**
- **DEF-HIGH-01**: Admin CRUD WebSocket events for cascade delete (`backend/rest_api/services/admin_events.py`, `Dashboard/src/hooks/useAdminWebSocket.ts`)
- **DEF-HIGH-02**: Throttle feedback toast + reduced delay from 200ms to 100ms (`pwaMenu/src/components/ThrottleToast.tsx`)
- **DEF-HIGH-03**: retryQueueStore integrated with tablesStore (`pwaWaiter/src/stores/tablesStore.ts`)
- **DEF-HIGH-04**: Token refresh with auto-renewal interval (`pwaWaiter/src/stores/authStore.ts`)

#### TypeScript Errors

Dashboard and pwaMenu have preexisting TypeScript errors (39 and 44 respectively) that don't affect production builds. Key issues:
- FormData types missing `id` property
- snake_case vs camelCase mismatches in API types
- Mock types in test files

Run `npx tsc --noEmit` from each directory to see current errors.

### Architecture Patterns

See [auintegral11.md](auintegral11.md) for comprehensive audit. Key patterns enforced:

#### Backend - Modular Admin Router (January 2026 Refactoring)

The admin router has been refactored from a single 4,829-line file into 15 focused modules:

```
backend/rest_api/routers/admin/
├── __init__.py          # Combined router (imports all sub-routers)
├── _base.py             # Shared dependencies, models, auth helpers
├── tenant.py            # Tenant info and settings (2 endpoints)
├── branches.py          # Branch CRUD (5 endpoints)
├── categories.py        # Category CRUD (5 endpoints)
├── subcategories.py     # Subcategory CRUD (5 endpoints)
├── products.py          # Product CRUD with canonical model (5 endpoints)
├── allergens.py         # Allergen CRUD + cross-reactions (9 endpoints)
├── staff.py             # Staff management with branch access control (5 endpoints)
├── tables.py            # Table CRUD + batch creation (6 endpoints)
├── sectors.py           # Sector management (3 endpoints)
├── orders.py            # Active orders and stats (2 endpoints)
├── exclusions.py        # Branch exclusions for categories/subcategories (5 endpoints)
├── assignments.py       # Daily waiter-sector assignments (5 endpoints)
├── reports.py           # Sales analytics (3 endpoints)
├── audit.py             # Audit log viewing (1 endpoint)
└── restore.py           # Entity restoration (1 endpoint)

Supporting files:
├── admin_schemas.py     # All Pydantic schemas for admin endpoints
└── admin_base.py        # Legacy helpers (get_user_id, get_user_email)
```

**Import pattern for sub-modules:**
```python
# Each module imports from _base.py for shared dependencies
from rest_api.routers.admin._base import (
    Depends, HTTPException, status, Session, select,
    get_db, current_user, Branch, Category, Product,
    soft_delete, set_created_by, get_user_id, get_user_email,
    require_admin, require_admin_or_manager,
)
from rest_api.routers.admin_schemas import BranchOutput, BranchCreate
```

**main.py import unchanged:**
```python
# The __init__.py exports the combined router
from rest_api.routers.admin import router as admin_router
app.include_router(admin_router, prefix="/api/admin")
```

**Total: 62 endpoints across 15 modules** (100% API compatible with original)

#### Backend - Redis Connection Pool
```python
# CORRECT: Use connection pool singleton (shared/events.py)
from shared.events import get_redis_pool

redis = await get_redis_pool()  # Returns pooled connection
await redis.publish(channel, message)
# No manual close needed - pool manages connections

# Pool closed automatically on app shutdown via close_redis_pool()
```

#### Backend - Eager Loading (Avoid N+1)
```python
# CORRECT: Use selectinload for collections, joinedload for single relations
from sqlalchemy.orm import selectinload, joinedload

rounds = db.execute(
    select(Round).options(
        selectinload(Round.items).joinedload(RoundItem.product),
        joinedload(Round.session).joinedload(TableSession.table),
    ).where(...)
).scalars().unique().all()
```

#### Backend - Database Pool Settings
```python
# rest_api/db.py - Connection pool configured for reliability
engine = create_engine(
    DATABASE_URL,
    pool_pre_ping=True,      # Verify connections before use
    pool_size=5,
    max_overflow=10,
    pool_timeout=30,         # Max wait for connection
    pool_recycle=1800,       # Recycle after 30 min
    connect_args={"connect_timeout": 10},
)
```

#### Backend - Safe Commit Pattern (HIGH-01 Fix)
```python
# CORRECT: Use safe_commit() for automatic rollback on failure
from rest_api.db import safe_commit

# In router:
db.add(new_entity)
safe_commit(db)  # Rolls back and re-raises on failure

# Implementation (rest_api/db.py):
def safe_commit(db: Session) -> None:
    try:
        db.commit()
    except Exception:
        db.rollback()
        raise
```

#### Backend - Circuit Breaker Pattern (auditoria34.md REC-01)
```python
# Use circuit breaker to prevent cascading failures with external APIs
from rest_api.services.circuit_breaker import mercadopago_breaker, CircuitBreakerError

# In router (e.g., billing.py):
try:
    async with mercadopago_breaker.call():
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post("https://api.mercadopago.com/...")
except CircuitBreakerError as e:
    # Circuit is open - return 503 with Retry-After header
    raise HTTPException(
        status_code=503,
        detail=f"Service temporarily unavailable. Retry in {int(e.retry_after)}s",
        headers={"Retry-After": str(int(e.retry_after))},
    )

# Configuration (rest_api/services/circuit_breaker.py):
# - failure_threshold: 5 failures before opening circuit
# - success_threshold: 2 successes in half-open to close
# - timeout_seconds: 30s before attempting half-open
# - States: CLOSED (normal) → OPEN (failing) → HALF-OPEN (testing)

# Monitor via health check:
curl http://localhost:8000/api/health/detailed | jq '.circuit_breakers'
```

#### Backend - Webhook Retry Queue Pattern (auditoria34.md REC-02)
```python
# Queue failed webhooks for retry with exponential backoff
from rest_api.services.webhook_retry import webhook_retry_queue

# Enqueue failed webhook (e.g., in billing.py):
await webhook_retry_queue.enqueue(
    webhook_type="mercadopago",
    payload=body,
    error="Connection timeout",
)

# Register handler (in main.py lifespan):
from rest_api.services.mp_webhook_handler import register_mp_webhook_handler
register_mp_webhook_handler()

# Start background processor (in main.py lifespan):
import asyncio
asyncio.create_task(start_retry_processor(interval_seconds=30.0))

# Configuration:
# - Exponential backoff: 10s, 20s, 40s, 80s, 160s (max 1 hour)
# - Max 5 attempts before dead letter queue
# - Persisted in Redis (survives restarts)

# Monitor via health check and Redis:
curl http://localhost:8000/api/health/detailed | jq '.webhook_retry'
redis-cli -p 6380 ZRANGE webhook_retry:pending 0 -1 WITHSCORES
redis-cli -p 6380 LRANGE webhook_retry:dead_letter 0 10
```

#### Backend - Batch Insert Pattern (auditoria34.md REC-03)
```python
# WRONG: N+1 queries - one query per item
for item in body.items:
    result = db.execute(select(Product, BranchProduct)...).first()
    db.add(RoundItem(...))

# CORRECT: Single batch query + batch add
# 1. Collect all IDs first
product_ids = [item.product_id for item in body.items]

# 2. Single query to fetch all products with their branch prices
products_query = db.execute(
    select(Product, BranchProduct)
    .join(BranchProduct, Product.id == BranchProduct.product_id)
    .where(
        Product.id.in_(product_ids),
        Product.is_active == True,
        BranchProduct.branch_id == branch_id,
    )
).all()

# 3. Build lookup dict
product_lookup = {p.id: (p, bp) for p, bp in products_query}

# 4. Validate all products exist
for item in body.items:
    if item.product_id not in product_lookup:
        raise HTTPException(400, f"Product {item.product_id} not available")

# 5. Batch create items
round_items = [RoundItem(product_id=item.product_id, ...) for item in body.items]
db.add_all(round_items)
db.commit()
```

#### Frontend - useEffect Cleanup Pattern
```typescript
// CORRECT: Clean up setTimeout to prevent memory leaks
const timeoutRef = useRef<number | null>(null)

const closeModal = useCallback(() => {
  timeoutRef.current = window.setTimeout(() => { ... }, 300)
}, [])

useEffect(() => {
  return () => {
    if (timeoutRef.current) clearTimeout(timeoutRef.current)
  }
}, [])
```

#### Frontend - WebSocket Listener Pattern
```typescript
// CORRECT: Use useRef to avoid listener accumulation
const handleEventRef = useRef(handleEvent)
useEffect(() => { handleEventRef.current = handleEvent })

useEffect(() => {
  const unsubscribe = ws.on('*', (e) => handleEventRef.current(e))

  // WS-31-MED-05 FIX: HMR cleanup guard for development
  if (import.meta.hot) {
    import.meta.hot.dispose(() => {
      unsubscribe()
    })
  }

  return unsubscribe
}, [])  // Empty deps - subscribe once
```

#### Frontend - WebSocket Singleton Pattern (Dashboard)
```typescript
// Dashboard uses a singleton WebSocket (dashboardWS) shared across components.
// Components should NOT disconnect on cleanup - only unsubscribe listeners.

// WRONG: Calling disconnect() in component cleanup breaks other components
useEffect(() => {
  dashboardWS.connect('kitchen')
  return () => {
    dashboardWS.disconnect()  // ❌ Breaks other components using the singleton
  }
}, [])

// CORRECT: Only unsubscribe listeners, disconnect on logout
useEffect(() => {
  dashboardWS.connect('kitchen')
  const unsubscribeConnection = dashboardWS.onConnectionChange(setIsWsConnected)
  const unsubscribeEvents = dashboardWS.on('*', (e) => handleEventRef.current(e))
  return () => {
    unsubscribeConnection()  // ✅ Only remove this component's listeners
    unsubscribeEvents()
    // NOTE: Don't disconnect here - singleton shared across app
  }
}, [isAuthenticated])

// Disconnect should be called ONLY on logout (in authStore.ts):
logout: () => {
  dashboardWS.disconnect()  // ✅ Disconnect when user logs out
  // ... clear auth state
}

// WS-31-HIGH-02 FIX: Dashboard now has soft/hard disconnect methods
softDisconnect()  // Close socket, preserve listeners (for temporary disconnect)
disconnect()      // Close socket AND clear all listeners (for logout)
destroy()         // Alias for disconnect (API consistency)
```

#### Frontend - React Keys Pattern
```typescript
// WRONG: Using name as key causes duplicates when same name appears in multiple groups
<NavLink key={item.name} ... />  // "Sucursales" duplicated in Gestión and Estadísticas

// CORRECT: Use href (unique) for NavLinks
<NavLink key={item.href} ... />

// CORRECT: Use hierarchical keys for nested items (Dashboard/src/components/layout/Sidebar.tsx)
const renderSubItem = (child: NavItem, depth: number, parentKey: string = '') => {
  const itemKey = parentKey ? `${parentKey}-${child.name}` : child.name
  return <div key={itemKey}>...</div>
}
// Call: renderSubItem(child, 0, parentItem.name) → "Gestión-Sucursales", "Historial-Sucursales"

// WRONG: Duplicate column keys in Table component
const columns = [
  { key: 'name', label: 'Preview', render: ... },  // ❌ 'name' duplicated
  { key: 'name', label: 'Nombre', sortable: true },
]
// Causes: "Encountered two children with the same key, `badge-2-name`"

// CORRECT: Use unique keys for each column
const columns = [
  { key: 'preview', label: 'Preview', render: ... },  // ✅ Unique key
  { key: 'name', label: 'Nombre', sortable: true },
]
```

#### WebSocket Configuration Constants (WS-31-LOW-01)

Keep WebSocket constants synchronized across all 3 apps:

```typescript
// pwaWaiter/src/utils/constants.ts (reference implementation)
export const WS_CONFIG = {
  RECONNECT_INTERVAL: 1000,      // Base delay for exponential backoff
  MAX_RECONNECT_DELAY: 30000,    // Maximum reconnect delay
  MAX_RECONNECT_ATTEMPTS: 10,
  HEARTBEAT_INTERVAL: 30000,     // 30 seconds ping interval
  HEARTBEAT_TIMEOUT: 10000,      // 10 seconds to receive pong
  JITTER_FACTOR: 0.3,            // Add up to 30% random jitter
} as const

// Dashboard/pwaMenu use same values (defined locally in websocket.ts)
const BASE_RECONNECT_DELAY = 1000
const MAX_RECONNECT_DELAY = 30000
const MAX_RECONNECT_ATTEMPTS = 10
const HEARTBEAT_INTERVAL = 30000
const HEARTBEAT_TIMEOUT = 10000
const JITTER_FACTOR = 0.3
```

#### pwaWaiter - Auth Token Refresh
```typescript
// CORRECT: Max retries + auto-logout to prevent infinite loop
const MAX_REFRESH_ATTEMPTS = 3

refreshAccessToken: async () => {
  const { refreshAttempts, isRefreshing } = get()

  // HIGH-29-18 FIX: Prevent concurrent refresh attempts
  if (isRefreshing) {
    authLogger.debug('Token refresh already in progress, skipping')
    return false
  }

  if (refreshAttempts >= MAX_REFRESH_ATTEMPTS) {
    get().logout()
    return false
  }

  set({ isRefreshing: true, refreshAttempts: refreshAttempts + 1 })
  try {
    // ... attempt refresh ...
  } finally {
    set({ isRefreshing: false })  // Always reset in finally
  }
}
```

#### Global Event Listener Guard Pattern (CRIT-29-02, CRIT-29-03)
```typescript
// WRONG: Listener registered multiple times on HMR/re-initialization
window.addEventListener('online', handleOnline)  // Accumulates on each module reload

// CORRECT: Guard against duplicate registration + export cleanup (auditoria36 WAITER-STORE-CRIT-02)
let listenerRegistered = false
let listenerCleanup: (() => void) | null = null

if (typeof window !== 'undefined' && !listenerRegistered) {
  listenerRegistered = true
  const handleOnline = () => { /* ... */ }
  window.addEventListener('online', handleOnline)

  // Export cleanup function for tests and app unmount
  listenerCleanup = () => {
    window.removeEventListener('online', handleOnline)
    listenerRegistered = false
    listenerCleanup = null
  }
}

export function cleanupOnlineListener(): void {
  if (listenerCleanup) listenerCleanup()
}
```

#### IndexedDB Timeout Pattern (auditoria36 WAITER-SVC-MED-02)
```typescript
// WRONG: IndexedDB operations can hang indefinitely
const db = await openDB()  // May never resolve on corrupt/locked DB

// CORRECT: Wrap with timeout (30s default)
const IDB_TIMEOUT_MS = 30000

function withTimeout<T>(promise: Promise<T>, ms: number, op: string): Promise<T> {
  return new Promise((resolve, reject) => {
    const timeoutId = setTimeout(() => {
      reject(new Error(`${op} timed out after ${ms}ms`))
    }, ms)
    promise
      .then((r) => { clearTimeout(timeoutId); resolve(r) })
      .catch((e) => { clearTimeout(timeoutId); reject(e) })
  })
}

// Usage
return withTimeout(openPromise, IDB_TIMEOUT_MS, 'openDB')
```

#### Memory Leak Prevention in Set/Map (auditoria36 WAITER-SVC-CRIT-03)
```typescript
// WRONG: Set grows unbounded over time
const recentNotifications = new Set<string>()
recentNotifications.add(key)  // Never cleaned up if setTimeout fails

// CORRECT: Add maximum size limit
const MAX_RECENT = 100
if (recentNotifications.size >= MAX_RECENT) {
  recentNotifications.clear()  // Prevent unbounded growth
}
recentNotifications.add(key)
setTimeout(() => recentNotifications.delete(key), 5000)
```

#### Async Hook Mount Guard Pattern (auditoria36 MENU-HOOK-CRIT-01)
```typescript
// WRONG: setState after unmount causes memory leak warning
useEffect(() => {
  fetchData().then(data => setData(data))  // May run after unmount
}, [])

// CORRECT: Track mount state and check before setState
useEffect(() => {
  let isMounted = true

  fetchData().then(data => {
    if (!isMounted) return  // Skip if unmounted
    setData(data)
  })

  return () => { isMounted = false }
}, [])
```

#### Focus Trap Pattern for Modals (auditoria36 WAITER-COMP-CRIT-01/02)
```typescript
// In ConfirmDialog or any modal:
const previousActiveElement = useRef<HTMLElement | null>(null)

useEffect(() => {
  if (isOpen) {
    // Store focus to restore on close
    previousActiveElement.current = document.activeElement as HTMLElement
    setTimeout(() => firstFocusableRef.current?.focus(), 50)
  } else if (previousActiveElement.current) {
    previousActiveElement.current.focus()
    previousActiveElement.current = null
  }
}, [isOpen])

// Focus trap on Tab key
const handleKeyDown = (e: KeyboardEvent) => {
  if (e.key === 'Tab') {
    const focusables = [cancelBtn, confirmBtn].filter(Boolean)
    if (e.shiftKey && document.activeElement === focusables[0]) {
      e.preventDefault()
      focusables[focusables.length - 1].focus()
    } else if (!e.shiftKey && document.activeElement === focusables[focusables.length - 1]) {
      e.preventDefault()
      focusables[0].focus()
    }
  }
}
```

#### BroadcastChannel Synchronous Initialization (CRIT-29-04)
```typescript
// WRONG: Async initialization causes race condition
useEffect(() => {
  initBroadcastChannel()  // Messages received before init are lost
}, [])

// CORRECT: Synchronous initialization in store creation
let isChannelInitialized = false
const pendingBroadcasts: HistoryEntry[] = []

// In store persist config onRehydrateStorage:
if (typeof BroadcastChannel !== 'undefined' && !isChannelInitialized) {
  initBroadcastChannel({ setState: set })
  // Flush any pending broadcasts
  pendingBroadcasts.forEach((entry) => broadcastHistoryEntry(entry))
  pendingBroadcasts.length = 0
}
```

#### Zustand useCallback Dependency Pattern (CRIT-29-05)
```typescript
// WRONG: Depending on entire filter object causes infinite loop
const shouldShowProduct = useCallback(
  (product) => {
    if (allergenFilter.hasActiveFilter) { ... }  // allergenFilter changes on each render
  },
  [allergenFilter]  // Cyclic dependency!
)

// CORRECT: Extract stable references before useCallback
const allergenHasActive = allergenFilter.hasActiveFilter
const allergenShouldHide = allergenFilter.shouldHideProductAdvanced

const shouldShowProduct = useCallback(
  (product) => {
    if (allergenHasActive) {
      if (allergenShouldHide(product.allergens)) return false
    }
    return true
  },
  [allergenHasActive, allergenShouldHide]  // Stable primitives/functions
)
```

#### Backend Race Condition Prevention (CRIT-29-01)
```python
# WRONG: Read-then-write without locking allows concurrent modifications
session = db.scalar(select(TableSession).where(TableSession.id == id))
session.total_rounds += 1  # Race condition if concurrent requests

# CORRECT: Use SELECT FOR UPDATE to lock the row
locked_session = db.scalar(
    select(TableSession)
    .where(TableSession.id == session_id)
    .with_for_update()  # Locks row until transaction commits
)
locked_session.total_rounds += 1
```

#### Async Context Detection in Sync Wrappers (CRIT-29-07)
```python
# WRONG: loop.run_until_complete() fails in async context
def sync_wrapper():
    loop = asyncio.get_event_loop()
    return loop.run_until_complete(async_func())  # RuntimeError if loop running

# CORRECT: Detect async context and schedule appropriately
def sync_wrapper():
    try:
        loop = asyncio.get_event_loop()
        if loop.is_running():
            # Already in async context - schedule and return optimistically
            asyncio.ensure_future(async_func())
            return True  # Operation will complete asynchronously
        return loop.run_until_complete(async_func())
    except RuntimeError:
        return asyncio.run(async_func())
```

#### Backend - Authentication Security (auditoria32.md Fixes)

**Token Blacklist Verification (CRIT-AUTH-01):**
```python
# shared/auth.py - verify_jwt() MUST check blacklist
def verify_jwt(token: str) -> dict:
    payload = jwt.decode(token, settings.jwt_secret, algorithms=[settings.jwt_algorithm])
    jti = payload.get("jti")
    if jti and is_token_revoked(jti):
        raise HTTPException(status_code=401, detail="Token has been revoked")
    return payload

# JWT claims MUST include "jti" for revocation (CRIT-AUTH-04)
def sign_jwt(payload: dict) -> str:
    payload["jti"] = str(uuid.uuid4())  # Unique token identifier
    return jwt.encode(payload, settings.jwt_secret, algorithm=settings.jwt_algorithm)
```

**Email-based Rate Limiting (CRIT-AUTH-02):**
```python
# routers/auth.py - Prevents credential stuffing attacks
from shared.rate_limit import limiter, email_limiter, set_rate_limit_email

@router.post("/login")
@limiter.limit("5/minute")           # IP-based rate limit
@email_limiter.limit("5/minute")     # Email-based rate limit (CRITICAL)
def login(request: Request, body: LoginRequest):
    set_rate_limit_email(request, body.email)  # MUST be called first
    # ... authentication logic ...
```

**Bcrypt-only Password Verification (CRIT-AUTH-03):**
```python
# shared/password.py - NO plaintext password support
def verify_password(plain_password: str, hashed_password: str) -> bool:
    # SECURITY: Reject non-bcrypt hashes (no plaintext fallback)
    if not hashed_password.startswith(("$2a$", "$2b$", "$2y$")):
        logger.warning("SECURITY: Non-bcrypt password hash detected")
        return False  # Fail closed, don't allow login
    return pwd_context.verify(plain_password, hashed_password)
```

**Tenant Isolation Validation (CRIT-AUTH-05):**
```python
# routers/auth.py - All branches MUST belong to user's tenant
branches = db.execute(select(Branch).where(Branch.id.in_(branch_ids))).scalars().all()
for branch in branches:
    if branch.tenant_id != user.tenant_id:
        logger.error("SECURITY: Tenant isolation violation", user_id=user.id)
        raise HTTPException(status_code=403, detail="Security error: tenant isolation violation")
```

**Audit Trail User ID Extraction (CRIT-ADMIN-01):**
```python
# routers/admin_base.py - CORRECT way to get user_id from JWT context
def get_user_id(ctx: dict) -> int:
    return int(ctx["sub"])  # JWT "sub" claim contains user ID as string

def get_user_email(ctx: dict) -> str:
    return ctx.get("email", "")

# WRONG: This returns None because "user_id" key doesn't exist
user_id = ctx.get("user_id")  # ❌ Always None
```

**Security Logging Pattern (HIGH-AUTH-05):**
```python
# routers/auth.py - Log all auth events for security monitoring
logger.warning("LOGIN_FAILED: User not found", email=body.email)
logger.warning("LOGIN_FAILED: Invalid password", email=body.email, user_id=user.id)
logger.warning("LOGIN_FAILED: No branch assignments", email=body.email, user_id=user.id)
logger.info("LOGIN_SUCCESS", email=user.email, user_id=user.id, roles=roles)
logger.info("LOGOUT_SUCCESS", email=user_email, user_id=user_id)
```

#### Backend - Redis Subscriber Pool Pattern (CRIT-WS-09)
```python
# ws_gateway/redis_subscriber.py - Use pooled connection, NOT standalone
from shared.events import get_redis_pool

async def run_subscriber(channels: list[str], on_message: Callable) -> None:
    # CORRECT: Use the global pool
    redis_pool = await get_redis_pool()
    pubsub = redis_pool.pubsub()
    await pubsub.psubscribe(*channels)

    try:
        async for msg in pubsub.listen():
            # ... handle messages ...
    finally:
        await pubsub.punsubscribe(*channels)
        # DON'T close the pool connection - pool manages lifecycle
```

#### Database Indexes
Status columns have indexes for frequent queries (auto-created on startup):
- `Table.status`, `TableSession.status`, `Round.status`
- `ServiceCall.status`, `Check.status`, `Payment.status`
- `KitchenTicket.station`, `KitchenTicket.status`
- `is_active` indexed on all tables for soft delete filtering
- All foreign keys indexed for join performance

**Composite Indexes** (optimized for common query patterns):
- `ix_round_branch_status` on `Round(branch_id, status)` - kitchen pending rounds query
- `ix_service_call_branch_status` on `ServiceCall(branch_id, status)` - waiter pending calls query
- `ix_table_session_branch_status` on `TableSession(branch_id, status)` - tables by status query
- `ix_category_branch_active` on `Category(branch_id, is_active)` - catalog queries
- `ix_subcategory_category_active` on `Subcategory(category_id, is_active)` - subcategory queries
- `ix_allocation_charge_payment` on `Allocation(charge_id, payment_id)` - FIFO allocation queries (MED-IDX-01)

**Partial Indexes** (for nullable unique constraints):
- `uq_sector_prefix_global` on `BranchSector(tenant_id, prefix)` WHERE `branch_id IS NULL` - global sectors (HIGH-DB-01)

**Check Constraints** (data integrity):
- `Check.chk_paid_not_exceed_total`: `paid_cents <= total_cents`
- `Check.chk_total_non_negative`: `total_cents >= 0`
- `Check.chk_paid_non_negative`: `paid_cents >= 0`
- `Diner.uq_diner_session_local_id`: Unique constraint on `(session_id, local_id)` for idempotency

**Exclusive Assignment Constraint** (HIGH-DB-02):
- `WaiterSectorAssignment.uq_waiter_exclusive_assignment`: One sector per waiter per tenant/branch/date/shift

### Soft Delete Pattern

All 31 models support logical (soft) deletes with full audit trail tracking.

#### AuditMixin

All models inherit from `AuditMixin` which provides:

```python
# backend/rest_api/models.py
class AuditMixin:
    # Soft delete flag
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, index=True)

    # Timestamps
    created_at: Mapped[datetime]      # Auto-set on create
    updated_at: Mapped[datetime|None] # Auto-set on update
    deleted_at: Mapped[datetime|None] # Set on soft delete

    # User tracking (ID + email for denormalization)
    created_by_id: Mapped[int|None]
    created_by_email: Mapped[str|None]
    updated_by_id: Mapped[int|None]
    updated_by_email: Mapped[str|None]
    deleted_by_id: Mapped[int|None]
    deleted_by_email: Mapped[str|None]

    def soft_delete(self, user_id: int, user_email: str) -> None:
        """Mark entity as deleted with audit trail."""
        self.is_active = False
        self.deleted_at = datetime.utcnow()
        self.deleted_by_id = user_id
        self.deleted_by_email = user_email

    def restore(self, user_id: int, user_email: str) -> None:
        """Restore soft-deleted entity."""
        self.is_active = True
        self.deleted_at = None
        self.deleted_by_id = None
        self.deleted_by_email = None
```

#### Soft Delete Service

```python
# backend/rest_api/services/soft_delete_service.py
from rest_api.services.soft_delete_service import (
    soft_delete,        # Soft delete with audit trail
    restore_entity,     # Restore deleted entity
    set_created_by,     # Set created_by on new entity
    set_updated_by,     # Set updated_by on update
    get_model_class,    # Get model from entity type string
    find_active_entity, # Find entity where is_active=True
    find_deleted_entity,# Find entity where is_active=False
)

# Example usage in router:
@router.delete("/branches/{branch_id}")
def delete_branch(branch_id: int, db: Session, user: dict):
    branch = find_active_entity(db, Branch, branch_id)
    soft_delete(db, branch, user["user_id"], user["email"])
```

#### API Patterns

**List endpoints** accept `include_deleted` query parameter:
```python
@router.get("/branches")
def list_branches(include_deleted: bool = False):
    query = select(Branch).where(Branch.tenant_id == tenant_id)
    if not include_deleted:
        query = query.where(Branch.is_active == True)
    return db.execute(query).scalars().all()
```

**Get/Update/Delete endpoints** filter by `is_active=True`:
```python
@router.get("/branches/{id}")
def get_branch(id: int):
    branch = db.scalar(
        select(Branch).where(
            Branch.id == id,
            Branch.tenant_id == tenant_id,
            Branch.is_active == True,  # Only active entities
        )
    )
```

**Restore endpoint** for recovering deleted entities:
```python
# POST /api/admin/{entity_type}/{entity_id}/restore
@router.post("/{entity_type}/{entity_id}/restore")
def restore_deleted_entity(entity_type: str, entity_id: int):
    model_class = get_model_class(entity_type)
    entity = find_deleted_entity(db, model_class, entity_id)
    restore_entity(db, entity, user["user_id"], user["email"])
```

#### Dashboard Integration

**AuditFields interface** (`Dashboard/src/types/index.ts`):
```typescript
export interface AuditFields {
  is_active: boolean
  created_at?: string
  updated_at?: string | null
  deleted_at?: string | null
  created_by_id?: number | null
  created_by_email?: string | null
  updated_by_id?: number | null
  updated_by_email?: string | null
  deleted_by_id?: number | null
  deleted_by_email?: string | null
}
```

**API service** (`Dashboard/src/services/api.ts`):
```typescript
// All list methods accept includeDeleted parameter
branchAPI.list(includeDeleted: boolean = false)

// All entities have restore method
branchAPI.restore(id: number): Promise<RestoreResponse>

// Generic restore API
restoreAPI.restore(entityType: EntityType, entityId: number)
```

**Entity types for restore:**
- `branches`, `categories`, `subcategories`, `products`
- `allergens`, `tables`, `staff`, `promotions`

#### No Cascade Delete

When a parent entity is soft-deleted, child entities remain unchanged:
- Deleting a Category does NOT soft-delete its Subcategories
- Deleting a Branch does NOT soft-delete its Categories
- Child entities can still be accessed via `include_deleted=true`
- To fully remove a hierarchy, delete children first, then parent

### Role-Based Access Control

Dashboard enforces role-based permissions for all CRUD operations.

#### Permission Rules

| Role | Create | Edit | Delete |
|------|--------|------|--------|
| **ADMIN** | All entities (any branch) | All entities (any branch) | All entities (soft delete) |
| **MANAGER** | Staff, Tables, Allergens, Promotions, Badges, Seals, PromotionTypes (own branches only) | Same as create (own branches only) | None |
| **KITCHEN** | None | None | None |
| **WAITER** | None | None | None |

**Note:** Categories, Subcategories, and Products are **ADMIN-only** for create/edit operations. All other roles can only view these entities.

#### Staff Management Branch Restrictions

Staff management has special branch-based restrictions:

| Operation | ADMIN | MANAGER |
|-----------|-------|---------|
| **List staff** | All branches | Only their assigned branches |
| **View staff** | Any staff | Only staff in their branches |
| **Create staff** | Any branch, any role | Only their branches, cannot assign ADMIN role |
| **Edit staff** | Any staff, any role | Only staff in their branches, cannot assign ADMIN role |
| **Delete staff** | Any staff | Not allowed |

**Backend implementation** (`backend/rest_api/routers/admin/staff.py`):
```python
# MANAGER branch validation for staff operations
if is_manager and not is_admin:
    user_branch_ids = set(user.get("branch_ids", []))

    # Check if staff belongs to manager's branches
    staff_branch_ids = {br.branch_id for br in staff.branch_roles}
    if not user_branch_ids.intersection(staff_branch_ids):
        raise HTTPException(status_code=403, detail="No tienes acceso a este empleado")

    # MANAGER cannot assign ADMIN role
    if role_name == "ADMIN":
        raise HTTPException(status_code=403, detail="Solo un administrador puede asignar el rol de ADMIN")
```

**Frontend implementation** (`Dashboard/src/pages/Staff.tsx`):
```typescript
// Filter branches available for the current user
const availableBranches = useMemo(() => {
  if (userIsAdmin) return allBranches.filter((b) => b.is_active)
  // MANAGER: only branches they have access to
  return allBranches.filter(
    (b) => b.is_active && userBranchIds.includes(Number(b.id))
  )
}, [allBranches, userIsAdmin, userBranchIds])

// Filter roles (MANAGER cannot assign ADMIN)
const availableRoles = useMemo(() => {
  if (userIsAdmin) return BACKEND_ROLES
  return BACKEND_ROLES.filter((r) => r.id !== 'ADMIN')
}, [userIsAdmin])
```

#### Permission Utility (`Dashboard/src/utils/permissions.ts`)

```typescript
import { canCreateBranch, canEditBranch, canDelete } from '../utils/permissions'
import { useAuthStore, selectUserRoles } from '../stores/authStore'

// In component:
const userRoles = useAuthStore(selectUserRoles)
const canCreate = canCreateBranch(userRoles)  // ADMIN only
const canEdit = canEditBranch(userRoles)      // ADMIN + MANAGER
const canDeleteBranch = canDelete(userRoles)  // ADMIN only
```

**Key functions:**
- `isAdmin(roles)` / `isManager(roles)` - Check specific role
- `isAdminOrManager(roles)` - Check either role
- `canDelete(roles)` - ADMIN only (used for all entities)
- `canCreateBranch(roles)` - ADMIN only
- `canCreateRole(roles)` / `canEditRole(roles)` - ADMIN only
- `canCreateCategory(roles)` / `canEditCategory(roles)` - ADMIN only
- `canCreateSubcategory(roles)` / `canEditSubcategory(roles)` - ADMIN only
- `canCreateProduct(roles)` / `canEditProduct(roles)` - ADMIN only
- Similar functions for Staff, Table, Allergen, Promotion, Badge, Seal, PromotionType (ADMIN + MANAGER)

#### UI Conditional Rendering Pattern

All CRUD pages apply this pattern:

```tsx
// PageContainer actions prop - conditionally show "New" button
<PageContainer
  title="Productos"
  actions={
    canCreate ? (
      <Button onClick={openCreateModal}>Nuevo Producto</Button>
    ) : undefined
  }
>

// Table action column - conditionally show Edit/Delete buttons
{canEdit && (
  <Button onClick={() => openEditModal(item)}>
    <Pencil className="w-4 h-4" />
  </Button>
)}
{canDeleteProduct && (
  <Button onClick={() => deleteDialog.open(item)}>
    <Trash2 className="w-4 h-4" />
  </Button>
)}
```

#### Backend Role Validation

DELETE endpoints require ADMIN role:

```python
# backend/rest_api/routers/admin/branches.py
@router.delete("/branches/{branch_id}")
async def delete_branch(branch_id: int, user: dict = Depends(get_current_user)):
    if "ADMIN" not in user.get("roles", []):
        raise HTTPException(status_code=403, detail="Only ADMIN can delete")
    # ... soft delete logic
```

#### Pages with RBAC Applied

All 16 CRUD pages enforce permissions:
- Branches, Categories, Subcategories, Products, Product Exclusions
- Staff, Tables, Allergens, Promotions
- Badges, Seals, PromotionTypes, Roles

### Branch Management Features

#### Branch Exclusion System

Allows ADMIN users to mark which categories/subcategories are NOT sold at specific branches. This enables branch-specific menu customization without duplicating products.

**Database Models:**
```python
# backend/rest_api/models.py
class BranchCategoryExclusion(AuditMixin, Base):
    """Marks a category as NOT sold at a specific branch."""
    __tablename__ = "branch_category_exclusion"
    branch_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("branch.id"))
    category_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("category.id"))

class BranchSubcategoryExclusion(AuditMixin, Base):
    """Marks a subcategory as NOT sold at a specific branch."""
    __tablename__ = "branch_subcategory_exclusion"
    branch_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("branch.id"))
    subcategory_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("subcategory.id"))
```

**API Endpoints (ADMIN only):**
```
GET  /api/admin/exclusions                              # Overview
PUT  /api/admin/exclusions/categories/{category_id}     # Set excluded branches
PUT  /api/admin/exclusions/subcategories/{subcategory_id}
```

**Navigation:** Gestión → Productos → Exclusiones (`/product-exclusions`)

#### Bulk Table Creation by Sector

Allows creating multiple tables at once by selecting sectors and specifying quantities per capacity.

**Database Model:**
```python
class BranchSector(AuditMixin, Base):
    """Sector for organizing tables (e.g., Interior, Terraza, VIP)."""
    name: Mapped[str]      # "Interior", "Terraza", "VIP"
    prefix: Mapped[str]    # "INT", "TER", "VIP" for auto-codes
```

**Auto-generated Table Codes:**
- Sector "Interior" (prefix "INT") → INT-01, INT-02, INT-03...
- Sector "Terraza" (prefix "TER") → TER-01, TER-02...

**API Endpoints:**
```
GET  /api/admin/sectors?branch_id={id}
POST /api/admin/sectors
POST /api/admin/tables/batch  # Body: { branch_id, tables: [{ sector_id, capacity, count }] }
```

**Navigation:** Gestión → Sucursales → Mesas → "Creación Masiva"

**Seed Data (Global Sectors):**
Interior (INT), Terraza (TER), VIP (VIP), Barra (BAR), Jardín (JAR), Salón Principal (SAL)

#### Daily Waiter-Sector Assignment

Allows daily assignment of waiters to sectors. A waiter can be assigned to multiple sectors, and a sector can have multiple waiters.

**Database Model:**
```python
class WaiterSectorAssignment(AuditMixin, Base):
    """Daily assignment of waiters to sectors."""
    sector_id: Mapped[int]
    waiter_id: Mapped[int]
    assignment_date: Mapped[date]
    shift: Mapped[Optional[str]]  # "MORNING", "AFTERNOON", "NIGHT" or NULL
```

**API Endpoints:**
```
GET  /api/admin/assignments?branch_id={id}&assignment_date={date}&shift={shift}
POST /api/admin/assignments/bulk
DELETE /api/admin/assignments-bulk?branch_id={id}&assignment_date={date}&shift={shift}
POST /api/admin/assignments/copy?branch_id={id}&from_date={date}&to_date={date}
```

**Navigation:** Gestión → Sucursales → Mesas → "Asignar Mozos"

**Features:**
- Date picker for assignment date
- Shift selector (all day, morning, afternoon, night)
- Copy from previous day functionality
- **Exclusive assignment**: A waiter can only be assigned to ONE sector at a time

#### Sector-Based Waiter Notifications

When waiters are assigned to sectors, WebSocket notifications are filtered so each waiter only receives events for their assigned sectors.

**How it Works:**
1. **On WebSocket Connect**: Gateway fetches waiter's sector assignments and registers connection to those channels
2. **Event Publishing**: Events with `sector_id` published to `sector:{id}:waiters` channel
3. **Dynamic Updates**: Waiters can send `refresh_sectors` message to re-fetch assignments

**Fallback Behavior:**
- If a waiter has no sector assignments, they receive ALL branch events
- Managers and Admins always receive all branch events

#### Tables Display by Sector

The Tables page groups tables by sector to avoid confusion when table numbers repeat across areas. Tables are sorted by status urgency within each sector.

### Recipe Module

Technical recipe sheets ("fichas técnicas") for Kitchen staff. Recipes can be linked to products and ingested into the RAG chatbot.

**Access Control:** KITCHEN, MANAGER, ADMIN have full CRUD access
**Navigation:** Cocina → Recetas (`/recipes`)

**Database Model:**
```python
class Recipe(AuditMixin, Base):
    # Basic info
    branch_id: Mapped[int]
    product_id: Mapped[Optional[int]]  # Optional link to Product
    subcategory_id: Mapped[Optional[int]]  # Normalized category via FK
    name, description, short_description, image  # short_description for previews
    cuisine_type, difficulty  # EASY, MEDIUM, HARD

    # Time and servings
    prep_time_minutes, cook_time_minutes, servings, calories_per_serving

    # Structured data (JSONB fields)
    ingredients: JSONB  # [{ingredient_id?, name, quantity, unit, notes}]
    preparation_steps: JSONB  # [{step, instruction, time_minutes?}]

    # Sensory profile (Phase 3 - planteo.md)
    flavors: JSONB  # ["suave", "intenso", "dulce", "salado", "acido", "amargo", "umami", "picante"]
    textures: JSONB  # ["crocante", "cremoso", "tierno", "firme", "esponjoso", "gelatinoso", "granulado"]

    # Cooking info
    cooking_methods: JSONB  # ["horneado", "frito", "grillado", "crudo", "hervido", "vapor", "salteado", "braseado"]
    uses_oil: bool  # For filtering "sin frito"

    # Allergens (M:N via RecipeAllergen)
    # allergen_ids: list[int] in API, actual storage via RecipeAllergen table
    is_celiac_safe: bool  # Specific celiac certification
    allergen_notes: Optional[str]  # Additional allergen notes

    # Modifications and warnings (Phase 4 - planteo.md)
    modifications: JSONB  # [{action: "remove"|"substitute", item: str, allowed: bool}]
    warnings: JSONB  # [str] - e.g., "Contiene huesos pequeños"

    # Cost and yield
    cost_cents: Optional[int]
    suggested_price_cents: Optional[int]
    yield_quantity, yield_unit  # e.g., "2kg", "24 unidades"
    portion_size: Optional[str]  # e.g., "200g", "1 unidad"

    # RAG config (Phase 5 - planteo.md)
    risk_level: str  # "low", "medium", "high" - affects RAG disclaimers
    custom_rag_disclaimer: Optional[str]

    # Status
    is_ingested: bool  # RAG chatbot flag
    last_ingested_at: Optional[datetime]

class RecipeAllergen(AuditMixin, Base):
    """M:N relationship between Recipe and Allergen."""
    recipe_id: Mapped[int]
    allergen_id: Mapped[int]
    tenant_id: Mapped[int]
    risk_level: Mapped[str]  # "low", "standard", "high" for this recipe-allergen combo
```

**Features:**
- Cascading category → subcategory selection (normalized via `subcategory_id`)
- Ingredient selection from normalized Ingredient database (combo-box with group names)
- Allergen selection via visual multi-select grid with emoji icons
- RAG ingestion button converts recipe to structured text with pgvector embeddings
- Risk-level based disclaimers in RAG responses
- Sensory profile (flavors, textures) for recommendation queries
- Cooking method filtering ("sin frito", "solo grillado")
- Modifications tracking (what can/cannot be removed or substituted)
- Cost analysis and yield calculations

#### Recipe-Product Relationship (propuesta1.md)

The system supports optional linkage between Recipes and Products. This "Recipe opcional pero enriquecedora" approach allows:

1. **Recipe First**: Chef creates recipe → derives Product (inherits allergens)
2. **Product Only**: Quick product creation without recipe (fast onboarding)
3. **Recipe Standalone**: Internal documentation not sold (mise en place, procedures)

**Database Model:**
```python
class Product(AuditMixin, Base):
    # Recipe linkage (propuesta1.md)
    recipe_id: Mapped[Optional[int]] = mapped_column(BigInteger, ForeignKey("recipe.id"))
    inherits_from_recipe: Mapped[bool] = mapped_column(Boolean, default=False)
    # Relationship
    recipe: Mapped[Optional["Recipe"]] = relationship(back_populates="products")

class Recipe(AuditMixin, Base):
    # 1:N relationship - one recipe can derive multiple products
    # e.g., "Milanesa" recipe → "Milanesa Simple", "Milanesa Napolitana", "Milanesa a Caballo"
    products: Mapped[list["Product"]] = relationship(back_populates="recipe")
```

**Sync Service** (`backend/rest_api/services/recipe_product_sync.py`):
```python
from rest_api.services.recipe_product_sync import (
    sync_product_from_recipe,      # Sync allergens from recipe to product
    derive_product_from_recipe,    # Create product from recipe
    sync_all_products_for_recipe,  # Bulk sync when recipe updates
    get_recipe_product_summary,    # Summary helper
)
```

**API Endpoints:**
```
POST /api/recipes/{id}/derive-product  # Create Product from Recipe
  Body: { name, category_id, subcategory_id?, branch_prices?: [{branch_id, price_cents}] }
  Returns: { id, name, recipe_id, recipe_name, inherits_from_recipe, message }

GET  /api/recipes/{id}/products  # List all products derived from recipe
  Returns: [{ id, name, description, category_id, inherits_from_recipe }]
```

**When `inherits_from_recipe=True`:**
- Product allergens auto-sync from Recipe allergens (RecipeAllergen → ProductAllergen)
- Changes to recipe allergens propagate to linked products on update
- Product's `recipe_name` field displays linked recipe name

**Frontend Types:**
```typescript
// Product interface (when linked to Recipe)
recipe_id?: number | null        // Optional reference to Recipe
inherits_from_recipe?: boolean   // When true, inherits allergens from recipe
recipe_name?: string | null      // Display name of linked recipe
```

#### Recipe Frontend Types (Dashboard)

```typescript
// Dashboard/src/types/index.ts
export interface RecipeIngredient {
  ingredient_id?: number | null  // Optional reference to Ingredient table (null for manual entry)
  name: string                   // Display name (from selected ingredient or manual)
  quantity: string
  unit: string
  notes?: string
}

export interface RecipePreparationStep {
  step: number       // 1, 2, 3...
  instruction: string
  time_minutes?: number
}

export interface RecipeModification {
  action: 'remove' | 'substitute'  // Type of modification
  item: string                     // What can be removed/substituted
  allowed: boolean                 // Whether this modification is allowed
}

export interface RecipeAllergenInfo {
  id: number
  name: string
  icon?: string | null
}

export interface RecipeFormData {
  branch_id: string
  category_id?: string           // For UI filtering (cascading select)
  subcategory_id?: string        // Sent to API for normalized category
  product_id?: string
  name: string
  description?: string
  short_description?: string     // Preview text (100-150 chars)
  image?: string
  cuisine_type?: string
  difficulty?: 'EASY' | 'MEDIUM' | 'HARD'
  prep_time_minutes?: number
  cook_time_minutes?: number
  servings?: number
  calories_per_serving?: number
  ingredients: RecipeIngredient[]
  preparation_steps: RecipePreparationStep[]
  chef_notes?: string
  presentation_tips?: string
  storage_instructions?: string
  allergen_ids: number[]         // M:N via RecipeAllergen (backend manages relationship)
  dietary_tags: string[]
  // Sensory profile
  flavors: string[]              // From catalog
  textures: string[]             // From catalog
  // Cooking info
  cooking_methods: string[]      // From catalog
  uses_oil: boolean
  // Celiac safety
  is_celiac_safe: boolean
  allergen_notes?: string
  // Modifications and warnings
  modifications: RecipeModification[]
  warnings: string[]
  // Cost and yield
  cost_cents?: number
  suggested_price_cents?: number
  yield_quantity?: string
  yield_unit?: string
  portion_size?: string
  // RAG config
  risk_level: 'low' | 'medium' | 'high'
  custom_rag_disclaimer?: string
  // Status
  is_active: boolean
}
```

**API Schema (Pydantic):**
```python
# backend/rest_api/routers/recipes.py
class RecipeCreate(BaseModel):
    branch_id: int
    name: str
    description: str | None = None
    short_description: str | None = None
    allergen_ids: list[int] | None = None  # M:N via RecipeAllergen
    flavors: list[str] | None = None
    textures: list[str] | None = None
    cooking_methods: list[str] | None = None
    uses_oil: bool = False
    is_celiac_safe: bool = False
    modifications: list[ModificationItem] | None = None
    warnings: list[str] | None = None
    risk_level: str = "low"
    custom_rag_disclaimer: str | None = None
    # ... other fields

class RecipeOutput(BaseModel):
    # Returns both allergen_ids (for form binding) and allergens (for display)
    allergen_ids: list[int] | None = None
    allergens: list[AllergenInfo] | None = None  # Full allergen info with icons
```

### Canonical Product Model

The system uses a normalized 19-table model for products to support advanced nutritional queries, dietary filtering, and RAG chatbot responses.

**Migration Phases (All Complete):**
- **Phase 0**: Normalized allergens with presence types (contains, may_contain, free_from)
- **Phase 1**: Ingredient system with groups and sub-ingredients
- **Phase 2**: Dietary profile (vegan, vegetarian, gluten-free, celiac-safe, keto, low-sodium)
- **Phase 3**: Cooking methods and sensory profiles (flavors, textures)
- **Phase 4**: Advanced features (modifications, warnings, RAG config)
- **Phase 5**: Consolidated product view and RAG integration

**Key Models:**
```python
# Allergens (Phase 0)
ProductAllergen(product_id, allergen_id, presence_type, risk_level)

# Ingredients (Phase 1)
IngredientGroup(name)  # proteina, vegetal, lacteo, cereal, condimento, otro
Ingredient(tenant_id, name, group_id, is_processed)
SubIngredient(ingredient_id, name)  # For processed ingredients
ProductIngredient(product_id, ingredient_id, is_main, notes)

# Dietary Profile (Phase 2)
ProductDietaryProfile(product_id, is_vegetarian, is_vegan, is_gluten_free, is_dairy_free, is_celiac_safe, is_keto, is_low_sodium)

# Cooking/Sensory (Phase 3)
CookingMethod, FlavorProfile, TextureProfile  # Catalogs
ProductCookingMethod, ProductFlavor, ProductTexture  # M:N
ProductCooking(product_id, uses_oil, prep_time_minutes, cook_time_minutes)

# Advanced (Phase 4)
ProductModification(product_id, action, item, is_allowed, extra_cost_cents)
ProductWarning(product_id, text, severity)
ProductRAGConfig(product_id, risk_level, custom_disclaimer, highlight_allergens)
```

**Consolidated Product View Service:**
```python
# backend/rest_api/services/product_view.py
view = get_product_complete(db, product_id)
text = generate_product_text_for_rag(view, price_cents=12500)

# Batch function with Redis caching for branch menus
products = get_products_complete_for_branch(db, branch_id)  # Uses cache
products = get_products_complete_for_branch(db, branch_id, use_cache=False)  # Skip cache
invalidate_branch_products_cache(branch_id)  # Clear cache on product update
```

**Redis Caching for Product Views:**
- Cache key: `products_complete:branch:{branch_id}`
- TTL: 5 minutes (300 seconds)
- Automatically invalidated on product create/update/delete
- Reduces database load for menu fetching in pwaMenu
- Located in `backend/rest_api/services/product_view.py`

**Catalog API Endpoints** (`backend/rest_api/routers/catalogs.py`):
```
GET /api/admin/cooking-methods      # List all cooking methods
GET /api/admin/flavor-profiles      # List all flavor profiles
GET /api/admin/texture-profiles     # List all texture profiles
```

**Dashboard catalogsAPI** (`Dashboard/src/services/api.ts`):
```typescript
export const catalogsAPI = {
  listCookingMethods: () => api.get<CookingMethod[]>('/admin/cooking-methods'),
  listFlavorProfiles: () => api.get<FlavorProfile[]>('/admin/flavor-profiles'),
  listTextureProfiles: () => api.get<TextureProfile[]>('/admin/texture-profiles'),
}
```

**RAG Service Risk Disclaimers** (`backend/rest_api/services/rag_service.py`):
```python
# RAG responses include risk-based disclaimers for allergen safety
# High-risk products: "IMPORTANTE: Los productos mencionados contienen alérgenos de alto riesgo..."
# Medium-risk products: "Nota: Algunos productos mencionados pueden contener trazas de alérgenos..."
```

#### Dashboard Ingredients Page

**Navigation:** Cocina → Ingredientes (`/ingredients`)

**Components:**
- `Dashboard/src/pages/Ingredients.tsx` (614 lines) - Full CRUD page
- `Dashboard/src/stores/ingredientStore.ts` (272 lines) - Zustand store

**Features:**
- Group-based ingredient organization (collapsible rows by IngredientGroup)
- Sub-ingredient management for processed ingredients (e.g., mayonesa → huevo, aceite, limón)
- `is_processed` flag indicates ingredient has sub-components
- Role-based permissions: ADMIN can delete, MANAGER can create/edit
- Pagination and sorting

**API Endpoints:**
```
GET  /api/admin/ingredients?group_id={id}     # List by group
POST /api/admin/ingredients                    # Create
GET  /api/admin/ingredients/{id}               # Detail with sub-ingredients
PUT  /api/admin/ingredients/{id}               # Update
DELETE /api/admin/ingredients/{id}             # Soft delete
POST /api/admin/ingredients/{id}/sub           # Add sub-ingredient
DELETE /api/admin/ingredients/{id}/sub/{subId} # Remove sub-ingredient
GET  /api/admin/ingredient-groups              # List groups
POST /api/admin/ingredient-groups              # Create custom group
```

**Store** (`Dashboard/src/stores/ingredientStore.ts`):
```typescript
interface IngredientState {
  ingredients: Ingredient[]
  groups: IngredientGroup[]
  isLoading: boolean
  fetchIngredients: (groupId?: number) => Promise<void>
  fetchGroups: () => Promise<void>
  createIngredientAsync: (data: IngredientFormData) => Promise<Ingredient>
  createSubIngredientAsync: (ingredientId: string, data: SubIngredientFormData) => Promise<void>
  deleteSubIngredientAsync: (ingredientId: string, subIngredientId: number) => Promise<void>
}
```

**Seed Data (Ingredient Groups):**
Proteína, Vegetal, Lácteo, Cereal, Condimento, Otro

### pwaMenu Advanced Filters

The pwaMenu app provides advanced filtering hooks for dietary preferences and cooking methods.

**Filter Hooks** (`pwaMenu/src/hooks/`):

| Hook | Purpose |
|------|---------|
| `useAllergenFilter` | Filter by allergens with presence types (contains, may_contain, free_from) and strictness levels |
| `useDietaryFilter` | Filter by dietary profile (vegetarian, vegan, gluten_free, dairy_free, celiac_safe, keto, low_sodium) |
| `useCookingMethodFilter` | Filter by cooking methods (exclude fried, require grilled) and oil usage |
| `useAdvancedFilters` | Combined hook aggregating all filters |

**useAllergenFilter** (enhanced with cross-reactions):
```typescript
// Pass branchSlug to enable cross-reaction filtering
const allergenFilter = useAllergenFilter(branchSlug)

// Strictness levels
allergenFilter.setStrictness('strict')      // Only hide products that CONTAIN allergen
allergenFilter.setStrictness('very_strict') // Also hide products that MAY_CONTAIN (traces)

// Cross-reaction support (latex-fruit syndrome, etc.)
allergenFilter.toggleCrossReactions()       // Enable/disable cross-reaction filtering
allergenFilter.setCrossReactionSensitivity('high_only')   // Only high probability
allergenFilter.setCrossReactionSensitivity('high_medium') // High + medium (default)
allergenFilter.setCrossReactionSensitivity('all')         // All cross-reactions

// Cross-reaction state
allergenFilter.crossReactionsEnabled        // Boolean
allergenFilter.crossReactedAllergenIds      // IDs derived from excluded allergens
allergenFilter.allFilteredAllergenIds       // Combined: excluded + cross-reacted
allergenFilter.crossReactionWarnings        // Human-readable warnings for display
allergenFilter.hasCrossReactions            // Boolean - any cross-reactions detected

// Advanced filtering with presence types
allergenFilter.shouldHideProductAdvanced({
  contains: [{ id: 1, name: 'Gluten' }],
  may_contain: [{ id: 2, name: 'Lácteos' }],
  free_from: [{ id: 3, name: 'Soja' }]
})
```

**Cross-Reaction API** (`pwaMenu/src/services/api.ts`):
```typescript
// Fetch allergens with cross-reaction data for a branch
menuAPI.getAllergensWithCrossReactions(branchSlug)
// Returns: AllergenWithCrossReactionsAPI[] with cross_reactions array

// Backend endpoint
GET /api/public/menu/{slug}/allergens  // Returns allergens + cross_reactions
```

**useDietaryFilter**:
```typescript
const dietaryFilter = useDietaryFilter()
dietaryFilter.toggleOption('vegan')
dietaryFilter.toggleOption('gluten_free')
dietaryFilter.matchesFilter(product.dietary) // Returns boolean

// Constants exported
DIETARY_LABELS: { vegan: 'Vegano', vegetarian: 'Vegetariano', ... }
DIETARY_ICONS: { vegan: '🌱', vegetarian: '🥬', ... }
```

**useCookingMethodFilter**:
```typescript
const cookingFilter = useCookingMethodFilter()
cookingFilter.toggleExcludedMethod('frito')    // Exclude fried foods
cookingFilter.toggleRequiredMethod('grillado') // Require grilled foods
cookingFilter.toggleExcludeOil()               // Exclude foods that use oil
cookingFilter.matchesFilter(methods, usesOil)  // Returns boolean

// Cooking methods: horneado, frito, grillado, crudo, hervido, vapor, salteado, braseado
COOKING_METHOD_LABELS: { frito: 'Frito', grillado: 'Grillado/Parrilla', ... }
COOKING_METHOD_ICONS: { frito: '🍳', grillado: '♨️', ... }
```

**useAdvancedFilters** (combined):
```typescript
const filters = useAdvancedFilters()

// Filter a single product
if (filters.shouldShowProduct(product)) { ... }

// Filter an array of products
const visibleProducts = filters.filterProducts(allProducts)

// Clear all filters at once
filters.clearAllFilters()

// Computed state
filters.totalActiveFilters  // Number of active filters across all types
filters.hasAnyActiveFilter  // Boolean

// Access individual filters
filters.allergen.toggleAllergen(1)
filters.dietary.toggleOption('vegan')
filters.cooking.toggleExcludedMethod('frito')
```

**ProductFilterData Interface**:
```typescript
interface ProductFilterData {
  id: number
  name: string
  allergens?: {
    contains: Array<{ id: number; name: string; icon?: string | null }>
    may_contain: Array<{ id: number; name: string; icon?: string | null }>
    free_from: Array<{ id: number; name: string; icon?: string | null }>
  } | null
  dietary?: {
    is_vegetarian: boolean
    is_vegan: boolean
    is_gluten_free: boolean
    is_dairy_free: boolean
    is_celiac_safe: boolean
    is_keto: boolean
    is_low_sodium: boolean
  } | null
  cooking?: {
    methods: string[]
    uses_oil: boolean
    prep_time_minutes?: number | null
    cook_time_minutes?: number | null
  } | null
}
```

**Advanced Filters UI Components** (`pwaMenu/src/components/`):

| Component | Purpose |
|-----------|---------|
| `FilterBadge` | Button showing active filter count, opens AdvancedFiltersModal |
| `AdvancedFiltersModal` | Full-screen modal with allergen, dietary, and cooking method filters |

```tsx
// FilterBadge usage (next to search bar)
<FilterBadge
  onClick={() => setFiltersModalOpen(true)}
  branchSlug={branchSlug}  // Enables cross-reaction count
/>
// Shows orange badge with count when filters active

// AdvancedFiltersModal usage
<AdvancedFiltersModal
  isOpen={filtersModalOpen}
  onClose={() => setFiltersModalOpen(false)}
  branchSlug={branchSlug}
  allergens={branchAllergens}  // From menuStore
/>
```

**AdvancedFiltersModal sections:**
1. **Alergenos a evitar**: Clickable allergen chips with strictness selector (strict/very_strict)
2. **Reacciones cruzadas**: Toggle + sensitivity selector (high_only/high_medium/all) with warnings
3. **Preferencias dietéticas**: Grid of dietary options (vegetarian, vegan, gluten_free, etc.)
4. **Métodos de cocción a evitar**: Cooking method chips (frito, horneado, vapor, etc.)

### Enhanced Allergen Model

The allergen system supports EU 1169/2011 mandatory allergens, severity levels, and cross-reactions.

**Database Models:**
```python
class Allergen(AuditMixin, Base):
    name: Mapped[str]
    icon: Mapped[Optional[str]]
    is_mandatory: Mapped[bool]  # EU 1169/2011
    severity: Mapped[str]  # mild, moderate, severe, life_threatening

class AllergenCrossReaction(AuditMixin, Base):
    """Cross-reaction information (e.g., latex → avocado)."""
    allergen_id: Mapped[int]        # Primary allergen
    cross_reacts_with_id: Mapped[int]  # Related allergen
    probability: Mapped[str]  # low, medium, high
    notes: Mapped[Optional[str]]

# ProductAllergen and RecipeAllergen now include risk_level
class ProductAllergen(AuditMixin, Base):
    presence_type: Mapped[str]  # "contains", "may_contain", "free_from"
    risk_level: Mapped[str]     # low, standard, high
```

**14 Mandatory EU Allergens (EU 1169/2011):**
1. Gluten (🌾) - severe
2. Crustáceos (🦐) - life_threatening
3. Huevo (🥚) - severe
4. Pescado (🐟) - severe
5. Cacahuete (🥜) - life_threatening
6. Soja (🫘) - moderate
7. Lácteos (🥛) - moderate
8. Frutos de cáscara (🌰) - life_threatening
9. Apio (🥬) - moderate
10. Mostaza (🟡) - moderate
11. Sésamo (⚪) - severe
12. Sulfitos (🧪) - moderate
13. Altramuces (🫛) - moderate
14. Moluscos (🦪) - severe

Optional allergens: Látex, Aguacate, Kiwi, Plátano, Castaña, Maíz

**Cross-Reactions (Seeded):**
- **Latex-Fruit Syndrome**: Látex → Aguacate (high), Plátano (high), Kiwi (high), Castaña (medium)
- **Crustáceos → Moluscos** (medium) - Tropomyosin
- **Cacahuete → Frutos de cáscara** (medium)
- **Frutos de cáscara → Sésamo** (low)
- **Gluten → Maíz** (low) - Some celiacs

**API Endpoints:**
```
GET  /api/admin/allergens?mandatory_only=true
GET  /api/admin/allergens/{id}  # Includes cross_reactions[]
GET  /api/admin/allergens/cross-reactions?allergen_id={id}
POST /api/admin/allergens/cross-reactions
```

**Frontend Usage:**
```typescript
function CrossReactionWarning({ allergen }: { allergen: Allergen }) {
  if (!allergen.cross_reactions?.length) return null
  return (
    <div className="bg-amber-500/10 border border-amber-500 rounded p-2">
      <p className="text-amber-300 text-sm">
        ⚠️ Si es alérgico a {allergen.name}, puede reaccionar a:
      </p>
      <ul className="text-xs text-amber-200">
        {allergen.cross_reactions.map((cr) => (
          <li key={cr.id}>
            {cr.cross_reacts_with_name} ({cr.probability === 'high' ? 'Alta' : cr.probability === 'medium' ? 'Media' : 'Baja'} probabilidad)
          </li>
        ))}
      </ul>
    </div>
  )
}
```
