# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

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
Product ←→ Allergen (M:N)
Promotion ←→ PromotionBranch (M:N with Branch)
          └── PromotionItem (products + quantities)
Branch ←→ BranchCategoryExclusion (M:N with Category - marks categories NOT sold at branch)
Branch ←→ BranchSubcategoryExclusion (M:N with Subcategory - marks subcategories NOT sold at branch)
BranchSector: Global (branch_id=NULL) or per-branch, with prefix for auto-generated table codes
Diner → RoundItem (tracks who ordered what)
Recipe: Kitchen technical sheets (fichas técnicas) linked to Branch, optionally to Product
       └── RecipeIngredient, RecipePreparationStep (structured steps with time estimates)
       └── Can be ingested into RAG chatbot via /api/admin/recipes/{id}/ingest
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

/api/admin/recipes/*           # Recipe CRUD (JWT + KITCHEN/MANAGER/ADMIN role)
  GET /                        # List recipes (filter by branch_id, category)
  POST /                       # Create recipe
  GET /{id}                    # Get recipe details
  PUT /{id}                    # Update recipe
  DELETE /{id}                 # Soft-delete recipe
  POST /{id}/ingest            # Ingest into RAG chatbot
  GET /categories              # List unique recipe categories

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
  /products, /allergens, /tables, /staff, /promotions
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

### WebSocket Heartbeat (Phase 10)

All WebSocket connections include heartbeat mechanism for connection reliability:

```typescript
// Frontend sends ping every 30s, expects pong within 10s
// Auto-reconnects on heartbeat timeout with exponential backoff

// Dashboard (JSON format):
ws.send('{"type":"ping"}')  // Server responds with '{"type":"pong"}'

// pwaMenu/pwaWaiter (plain text):
ws.send('ping')  // Server responds with 'pong'
```

**Backend WebSocket endpoints accept BOTH formats** (`ws_gateway/main.py`):
```python
# Handle heartbeat in both plain text and JSON format
if data == "ping":
    await websocket.send_text("pong")
elif data == '{"type":"ping"}':
    await websocket.send_text('{"type":"pong"}')
```

## Critical Zustand Pattern (React 19)

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

## Dashboard Store API Pattern (Phase 6)

Dashboard stores now support both local and async API operations:

```typescript
// Each store has async actions for backend integration
interface StoreState {
  items: Item[]
  isLoading: boolean
  error: string | null
  // Sync local actions (existing)
  addItem: (data: FormData) => Item
  updateItem: (id: string, data: Partial<FormData>) => void
  deleteItem: (id: string) => void
  // Async API actions (new)
  fetchItems: () => Promise<void>
  createItemAsync: (data: FormData) => Promise<Item>
  updateItemAsync: (id: string, data: Partial<FormData>) => Promise<void>
  deleteItemAsync: (id: string) => Promise<void>
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

## Test Users (Backend)

| Email | Password | Role |
|-------|----------|------|
| admin@demo.com | admin123 | ADMIN |
| manager@demo.com | manager123 | MANAGER |
| kitchen@demo.com | kitchen123 | KITCHEN |
| waiter@demo.com | waiter123 | WAITER |

## Conventions

- **UI language**: Spanish
- **Code comments**: English
- **Theme**: Dark with orange (#f97316) accent
- **TypeScript**: Strict mode, no unused variables
- **IDs**: `crypto.randomUUID()` in frontend, BigInteger in backend
- **Prices**: Stored as cents (e.g., $125.50 = 12550)
- **Logging**: Use centralized `utils/logger.ts`, never direct console.*
- **Naming**: Frontend uses camelCase (`backendSessionId`), backend uses snake_case (`backend_session_id`)

## Documentation

- [gradual.md](gradual.md): Complete migration plan with phases 0-10
- [traza1.md](traza1.md): Order flow documentation from QR scan to kitchen (Spanish prose narrative explaining the complete circuit: diners → backend → waiters/kitchen/dashboard)
- [prueba.md](prueba.md): Complete test scenario narrative for Mesa T-02 Terraza with 3 diners, waiter service, kitchen flow, and payment (includes session tokens and step-by-step instructions)
- [RESULTADOS_QA.md](RESULTADOS_QA.md): QA test results
- [auditoriapwa1.md](auditoriapwa1.md): Full audit report
- [pwaWaiter/bot/planteo.md](pwaWaiter/bot/planteo.md): Canonical dish database model (19 normalized tables for allergens, ingredients, dietary profiles, sensory profiles) - serves as data source for pwaMenu filters and RAG chatbot ingestion
- [pwaWaiter/bot/producto1.md](pwaWaiter/bot/producto1.md): Analysis of current product model (9 tables) with limitations for nutritional queries - comparison with planteo.md canonical model
- [pwaWaiter/bot/canonico.txt](pwaWaiter/bot/canonico.txt): JSON schema for canonical dish structure (original format before normalization)

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

## Docker Configuration

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
# - 8 Allergens
# - 5 Categories: Entradas, Platos Principales, Pizzas y Empanadas, Postres, Bebidas
# - 15 Subcategories (3 per category)
# - 75 Products (5 per subcategory) with pricing in all branches
```

## CORS Configuration

When adding new frontend apps, add the origin to `backend/rest_api/main.py`:

```python
allow_origins=[
    "http://localhost:5173",  # Vite default
    "http://localhost:5176",  # pwaMenu
    "http://localhost:5177",  # Dashboard
    "http://localhost:5178",  # pwaWaiter
    # Add new origins here
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

## Backend Server Notes

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

## Audit Status (January 2026)

See [auditoriapwa1.md](auditoriapwa1.md) for full audit report. All critical and high priority issues have been resolved:

### Resolved Issues
- ✅ **Backend Event Publishing**: `publish_round_event()`, `publish_service_call_event()`, and `publish_check_event()` now publish to **4 channels**: waiters, kitchen, admin (Dashboard), and session (diners). See `backend/shared/events.py`.
- ✅ **Payment Allocation**: MP webhook calls `allocate_payment_fifo()` after payment creation
- ✅ **pwaMenu Selectors**: Normalized to camelCase (`sharedCart`, `dinerId`, `backendRoundId`)
- ✅ **pwaMenu Payment Flow**: `useCloseTableFlow` calls `dinerAPI.createServiceCall({ type: 'PAYMENT_HELP' })`
- ✅ **pwaWaiter Events**: All 9 events mapped (ROUND_SUBMITTED, ROUND_IN_KITCHEN, ROUND_READY, ROUND_SERVED, SERVICE_CALL_CREATED, CHECK_REQUESTED, CHECK_PAID, TABLE_CLEARED, PAYMENT_APPROVED)
- ✅ **Dashboard WebSocket**: `tableStore.ts` has `subscribeToTableEvents()` for real-time table updates
- ✅ **Exponential Backoff**: Both pwaMenu and pwaWaiter WebSocket services use exponential backoff with jitter
- ✅ **Session Expiry**: pwaMenu API service handles 401 with `onSessionExpired()` callback
- ✅ **Rate Limiting**: Backend uses slowapi for rate limiting on public endpoints
- ✅ **Refresh Tokens**: `POST /api/auth/refresh` endpoint implemented
- ✅ **Cascade Delete Preview**: Dashboard shows affected items before deletion via `CascadePreviewList`
- ✅ **Duplicate Validation**: `validateProduct()` and `validateStaff()` check for duplicates

### Dashboard Real-time Updates

```typescript
// Dashboard/src/stores/tableStore.ts
// Subscribe to WebSocket events for table state changes
const unsubscribe = useTableStore.getState().subscribeToTableEvents()
// Call in useEffect cleanup: return () => unsubscribe()

// Events handled: TABLE_CLEARED, TABLE_STATUS_CHANGED, ROUND_SUBMITTED,
//                 ROUND_SERVED, CHECK_REQUESTED, CHECK_PAID
```

### Dashboard Admin CRUD Sync (DEF-HIGH-01 Fix)

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

// Backend publishes events from admin.py delete endpoints:
// - publish_entity_deleted() for single entity
// - publish_cascade_delete() with affected_entities list for cascades
```

### New Features (January 2026)

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

**Dashboard:**
- `Reports.tsx`: Sales reports page with charts and CSV export
- `exportCsv.ts`: Generic CSV export utility with Excel BOM support
- `useKeyboardShortcuts.ts`: Mac/Windows keyboard shortcuts hook
- `useSystemTheme.ts`: OS theme preference detection

**Dashboard (audi2das.md audit - January 2026):**
- `promotionStore.ts`: Full backend integration with `promotionAPI` (C001)
- `restaurantStore.ts`: Connected to `tenantAPI.get()` and `tenantAPI.update()` (C002)
- `staffAPI.get(id)`: New endpoint for fetching single staff member (C003)
- User model: Added `phone`, `dni`, `hire_date` fields to backend (D004)
- `promotions.py`: New router with full CRUD for Promotion, PromotionBranch, PromotionItem

**Backend:**
- `kitchen_tickets.py`: KitchenTicket CRUD endpoints (group round items by station)
- `promotions.py`: Promotion CRUD with branch and item associations

## QA Status (January 2026)

See [RESULTADOS_QA.md](RESULTADOS_QA.md) and [todaslasTraza.md](todaslasTraza.md) for full QA reports.

### Test Results
| App | Tests | Status |
|-----|-------|--------|
| Dashboard | 100 | PASSED |
| pwaMenu | 108 | PASSED |
| pwaWaiter | 0 | No tests yet |

### Running Individual Tests

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

### Resolved Defects (January 2026)

**CRITICAL (Fixed):**
- **DEF-CRIT-01**: Product validation before submitOrder (`pwaMenu/src/stores/tableStore/store.ts`)
- **DEF-CRIT-03**: WebSocket `visibilitychange` listener for reconnection after sleep (`pwaMenu/src/services/websocket.ts`)

**HIGH (Fixed):**
- **DEF-HIGH-01**: Admin CRUD WebSocket events for cascade delete (`backend/rest_api/services/admin_events.py`, `Dashboard/src/hooks/useAdminWebSocket.ts`)
- **DEF-HIGH-02**: Throttle feedback toast + reduced delay from 200ms to 100ms (`pwaMenu/src/components/ThrottleToast.tsx`)
- **DEF-HIGH-03**: retryQueueStore integrated with tablesStore (`pwaWaiter/src/stores/tablesStore.ts`)
- **DEF-HIGH-04**: Token refresh with auto-renewal interval (`pwaWaiter/src/stores/authStore.ts`)

### TypeScript Errors

Dashboard and pwaMenu have preexisting TypeScript errors (39 and 44 respectively) that don't affect production builds. Key issues:
- FormData types missing `id` property
- snake_case vs camelCase mismatches in API types
- Mock types in test files

Run `npx tsc --noEmit` from each directory to see current errors.

## Architecture Patterns (January 2026 Audit)

See [auintegral11.md](auintegral11.md) for comprehensive audit. Key patterns enforced:

### Backend - Redis Connection Pool
```python
# CORRECT: Use connection pool singleton (shared/events.py)
from shared.events import get_redis_pool

redis = await get_redis_pool()  # Returns pooled connection
await redis.publish(channel, message)
# No manual close needed - pool manages connections

# Pool closed automatically on app shutdown via close_redis_pool()
```

### Backend - Eager Loading (Avoid N+1)
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

### Backend - Database Pool Settings
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

### Frontend - useEffect Cleanup Pattern
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

### Frontend - WebSocket Listener Pattern
```typescript
// CORRECT: Use useRef to avoid listener accumulation
const handleEventRef = useRef(handleEvent)
useEffect(() => { handleEventRef.current = handleEvent })

useEffect(() => {
  const unsubscribe = ws.on('*', (e) => handleEventRef.current(e))
  return unsubscribe
}, [])  // Empty deps - subscribe once
```

### Frontend - WebSocket Singleton Pattern (Dashboard)
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
```

### Frontend - React Keys Pattern
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

### pwaWaiter - Auth Token Refresh
```typescript
// CORRECT: Max retries + auto-logout to prevent infinite loop
const MAX_REFRESH_ATTEMPTS = 3

refreshAccessToken: async () => {
  const { refreshAttempts } = get()
  if (refreshAttempts >= MAX_REFRESH_ATTEMPTS) {
    get().logout()
    return false
  }
  set({ refreshAttempts: refreshAttempts + 1 })
  // ... attempt refresh ...
}
```

### Database Indexes
Status columns have indexes for frequent queries (auto-created on startup):
- `Table.status`, `TableSession.status`, `Round.status`
- `ServiceCall.status`, `Check.status`, `Payment.status`
- `KitchenTicket.station`, `KitchenTicket.status`
- `is_active` indexed on all tables for soft delete filtering
- All foreign keys indexed for join performance

## Soft Delete Pattern (January 2026)

All 31 models support logical (soft) deletes with full audit trail tracking.

### AuditMixin

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

### Soft Delete Service

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

### API Patterns

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

### Dashboard Integration

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

### No Cascade Delete

When a parent entity is soft-deleted, child entities remain unchanged:
- Deleting a Category does NOT soft-delete its Subcategories
- Deleting a Branch does NOT soft-delete its Categories
- Child entities can still be accessed via `include_deleted=true`
- To fully remove a hierarchy, delete children first, then parent

## Role-Based Access Control (January 2026)

Dashboard enforces role-based permissions for all CRUD operations.

### Permission Rules

| Role | Create | Edit | Delete |
|------|--------|------|--------|
| **ADMIN** | All entities (any branch) | All entities (any branch) | All entities (soft delete) |
| **MANAGER** | Staff, Tables, Allergens, Promotions, Badges, Seals, PromotionTypes (own branches only) | Same as create (own branches only) | None |
| **KITCHEN** | None | None | None |
| **WAITER** | None | None | None |

**Note:** Categories, Subcategories, and Products are **ADMIN-only** for create/edit operations. All other roles can only view these entities.

### Staff Management Branch Restrictions (January 2026)

Staff management has special branch-based restrictions:

| Operation | ADMIN | MANAGER |
|-----------|-------|---------|
| **List staff** | All branches | Only their assigned branches |
| **View staff** | Any staff | Only staff in their branches |
| **Create staff** | Any branch, any role | Only their branches, cannot assign ADMIN role |
| **Edit staff** | Any staff, any role | Only staff in their branches, cannot assign ADMIN role |
| **Delete staff** | Any staff | Not allowed |

**Backend implementation** (`backend/rest_api/routers/admin.py`):
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

### Permission Utility (`Dashboard/src/utils/permissions.ts`)

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

### UI Conditional Rendering Pattern

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

### Backend Role Validation

DELETE endpoints require ADMIN role:

```python
# backend/rest_api/routers/admin.py
@router.delete("/branches/{branch_id}")
async def delete_branch(branch_id: int, user: dict = Depends(get_current_user)):
    if "ADMIN" not in user.get("roles", []):
        raise HTTPException(status_code=403, detail="Only ADMIN can delete")
    # ... soft delete logic
```

### Pages with RBAC Applied

All 16 CRUD pages enforce permissions:
- Branches, Categories, Subcategories, Products, Product Exclusions
- Staff, Tables, Allergens, Promotions
- Badges, Seals, PromotionTypes, Roles

## Branch Exclusion System (January 2026)

Allows ADMIN users to mark which categories/subcategories are NOT sold at specific branches. This enables branch-specific menu customization without duplicating products.

### Database Models

```python
# backend/rest_api/models.py
class BranchCategoryExclusion(AuditMixin, Base):
    """Marks a category as NOT sold at a specific branch."""
    __tablename__ = "branch_category_exclusion"
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    tenant_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("tenant.id"))
    branch_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("branch.id"))
    category_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("category.id"))
    # Unique constraint: one exclusion per branch-category pair

class BranchSubcategoryExclusion(AuditMixin, Base):
    """Marks a subcategory as NOT sold at a specific branch."""
    __tablename__ = "branch_subcategory_exclusion"
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    tenant_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("tenant.id"))
    branch_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("branch.id"))
    subcategory_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("subcategory.id"))
```

### API Endpoints

All endpoints require ADMIN role:

```
GET  /api/admin/exclusions
  → Returns ExclusionOverview with all category and subcategory exclusions

GET  /api/admin/exclusions/categories/{category_id}
  → Returns CategoryExclusionSummary with excluded_branch_ids

PUT  /api/admin/exclusions/categories/{category_id}
  → Body: { excluded_branch_ids: number[] }
  → Sets which branches exclude this category

GET  /api/admin/exclusions/subcategories/{subcategory_id}
  → Returns SubcategoryExclusionSummary with excluded_branch_ids

PUT  /api/admin/exclusions/subcategories/{subcategory_id}
  → Body: { excluded_branch_ids: number[] }
  → Sets which branches exclude this subcategory
```

### Dashboard Integration

**Navigation:** Gestion → Productos → Exclusiones (`/product-exclusions`)

**Store** (`Dashboard/src/stores/exclusionStore.ts`):
```typescript
interface ExclusionState {
  categoryExclusions: CategoryExclusionSummary[]
  subcategoryExclusions: SubcategoryExclusionSummary[]
  isLoading: boolean
  isUpdating: boolean
  error: string | null

  fetchExclusions: () => Promise<void>
  updateCategoryExclusions: (categoryId: number, excludedBranchIds: number[]) => Promise<void>
  updateSubcategoryExclusions: (subcategoryId: number, excludedBranchIds: number[]) => Promise<void>

  // Helper functions
  isCategoryExcludedFromBranch: (categoryId: number, branchId: number) => boolean
  isSubcategoryExcludedFromBranch: (subcategoryId: number, branchId: number) => boolean
  getExcludedBranchesForCategory: (categoryId: number) => number[]
  getExcludedBranchesForSubcategory: (subcategoryId: number) => number[]
}
```

**API Service** (`Dashboard/src/services/api.ts`):
```typescript
export const exclusionAPI = {
  getOverview: () => api.get<ExclusionOverview>('/admin/exclusions'),
  getCategoryExclusions: (categoryId: number) => ...,
  updateCategoryExclusions: (categoryId: number, excludedBranchIds: number[]) => ...,
  getSubcategoryExclusions: (subcategoryId: number) => ...,
  updateSubcategoryExclusions: (subcategoryId: number, excludedBranchIds: number[]) => ...,
}
```

**Types** (`Dashboard/src/types/index.ts`):
```typescript
export interface CategoryExclusionSummary {
  category_id: number
  category_name: string
  excluded_branch_ids: number[]
}

export interface SubcategoryExclusionSummary {
  subcategory_id: number
  subcategory_name: string
  category_id: number
  category_name: string
  excluded_branch_ids: number[]
}

export interface ExclusionOverview {
  category_exclusions: CategoryExclusionSummary[]
  subcategory_exclusions: SubcategoryExclusionSummary[]
}
```

### UI Pattern

The exclusion page uses a Table with string IDs for compatibility, storing `numericId` for API calls:

```typescript
interface CategoryRow {
  id: string           // String like "cat-123" for Table component
  numericId: number    // Original numeric ID for API calls
  name: string
  type: 'category'
  excludedBranchIds: number[]
}

// Toggle exclusion for a branch
const toggleExclusion = async (row: CategoryRow, branchId: number) => {
  const currentExclusions = row.excludedBranchIds
  const newExclusions = currentExclusions.includes(branchId)
    ? currentExclusions.filter(id => id !== branchId)  // Remove
    : [...currentExclusions, branchId]                 // Add

  await updateCategoryExclusions(row.numericId, newExclusions)
}
```

### Public Menu Filtering

When fetching menu for pwaMenu, excluded items are filtered out:
```python
# backend/rest_api/routers/public.py - GET /api/public/menu/{slug}
# Categories/subcategories excluded from the branch are not returned
excluded_cat_ids = db.scalars(
    select(BranchCategoryExclusion.category_id)
    .where(BranchCategoryExclusion.branch_id == branch.id)
).all()
# Filter out excluded categories from response
```

## Bulk Table Creation by Sector (January 2026)

Allows creating multiple tables at once by selecting sectors and specifying quantities per capacity.

### Database Model

```python
# backend/rest_api/models.py
class BranchSector(AuditMixin, Base):
    """Sector for organizing tables (e.g., Interior, Terraza, VIP)."""
    __tablename__ = "branch_sector"
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    tenant_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("tenant.id"))
    branch_id: Mapped[Optional[int]] = mapped_column(BigInteger, ForeignKey("branch.id"))  # NULL = global
    name: Mapped[str] = mapped_column(Text)        # "Interior", "Terraza", "VIP"
    prefix: Mapped[str] = mapped_column(Text)      # "INT", "TER", "VIP" for auto-codes
    display_order: Mapped[int] = mapped_column(Integer, default=0)
    # Unique constraint: (tenant_id, branch_id, prefix)
```

### API Endpoints

```
GET  /api/admin/sectors?branch_id={id}
  → Returns global sectors (branch_id=NULL) + branch-specific sectors

POST /api/admin/sectors
  → Body: { branch_id?, name, prefix, display_order? }
  → Creates custom sector (global if branch_id omitted)

DELETE /api/admin/sectors/{sector_id}
  → Soft-deletes sector

POST /api/admin/tables/batch
  → Body: { branch_id, tables: [{ sector_id, capacity, count }] }
  → Creates tables with auto-generated codes (e.g., INT-01, INT-02, TER-01)
  → Returns: { created_count, tables: [...] }
```

### Auto-generated Table Codes

Tables are named using sector prefix + sequential number:
- Sector "Interior" (prefix "INT") → INT-01, INT-02, INT-03...
- Sector "Terraza" (prefix "TER") → TER-01, TER-02...
- Sector "VIP" (prefix "VIP") → VIP-01, VIP-02...

### Dashboard Integration

**Navigation:** Gestión → Sucursales → Mesas → "Creación Masiva"

**Components:**
- `BulkTableModal.tsx`: Modal with sector checkboxes and capacity inputs
- `AddSectorDialog.tsx`: Dialog to create custom sectors
- `sectorStore.ts`: Zustand store for sector management

**Usage:**
1. Click "Creación Masiva" button on Tables page
2. Select sectors via checkboxes (Interior, Terraza, VIP, etc.)
3. Specify quantity per capacity (e.g., 5 tables for 4 people, 3 tables for 6 people)
4. Preview auto-generated codes
5. Click "Crear Mesas" to create all tables at once

### Seed Data

Global sectors created on first run:
- Interior (INT), Terraza (TER), VIP (VIP), Barra (BAR), Jardín (JAR), Salón Principal (SAL)

## Daily Waiter-Sector Assignment (January 2026)

Allows daily assignment of waiters to sectors. A waiter can be assigned to multiple sectors, and a sector can have multiple waiters.

### Database Model

```python
# backend/rest_api/models.py
class WaiterSectorAssignment(AuditMixin, Base):
    """Daily assignment of waiters to sectors."""
    __tablename__ = "waiter_sector_assignment"
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    tenant_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("tenant.id"))
    branch_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("branch.id"))
    sector_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("branch_sector.id"))
    waiter_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("app_user.id"))
    assignment_date: Mapped[date] = mapped_column(Date, nullable=False)
    shift: Mapped[Optional[str]] = mapped_column(Text)  # "MORNING", "AFTERNOON", "NIGHT" or NULL
    # Unique constraint: (tenant_id, branch_id, sector_id, waiter_id, assignment_date, shift)
```

### API Endpoints

```
GET  /api/admin/assignments?branch_id={id}&assignment_date={date}&shift={shift}
  → Returns BranchAssignmentOverview with sectors, assigned waiters, and unassigned waiters

POST /api/admin/assignments/bulk
  → Body: { branch_id, assignment_date, shift, assignments: [{ sector_id, waiter_ids: [...] }] }
  → Creates multiple assignments at once, skips duplicates

DELETE /api/admin/assignments/{assignment_id}
  → Soft-deletes single assignment

DELETE /api/admin/assignments-bulk?branch_id={id}&assignment_date={date}&shift={shift}
  → Clears all assignments for a branch on a given date
  → NOTE: Uses /assignments-bulk (not /assignments/bulk) to avoid FastAPI route conflict with {assignment_id}

POST /api/admin/assignments/copy?branch_id={id}&from_date={date}&to_date={date}&shift={shift}
  → Copies assignments from one date to another (useful for repeating yesterday's schedule)
```

### Dashboard Integration

**Navigation:** Gestión → Sucursales → Mesas → "Asignar Mozos"

**Components:**
- `WaiterAssignmentModal.tsx`: Modal for bulk waiter-sector assignments
- `waiterAssignmentStore.ts`: Zustand store for assignment management

**Store** (`Dashboard/src/stores/waiterAssignmentStore.ts`):
```typescript
interface WaiterAssignmentState {
  overview: BranchAssignmentOverview | null
  selectedDate: string
  selectedShift: string | null

  fetchAssignments: (branchId: number, date: string, shift?: string) => Promise<void>
  createBulkAssignments: (branchId, date, shift, assignments) => Promise<BulkAssignmentResult>
  clearAssignments: (branchId, date, shift?) => Promise<number>
  copyFromPreviousDay: (branchId, fromDate, toDate, shift?) => Promise<BulkAssignmentResult>
}
```

**API Service** (`Dashboard/src/services/api.ts`):
```typescript
export const assignmentAPI = {
  getOverview: (branchId, date, shift?) => ...,
  createBulk: (data: BulkAssignmentRequest) => ...,
  delete: (assignmentId) => ...,
  deleteBulk: (branchId, date, shift?) => ...,
  copy: (branchId, fromDate, toDate, shift?) => ...,
}
```

**Usage:**
1. Click "Asignar Mozos" button on Tables page
2. Select date and optionally a shift (morning/afternoon/night)
3. For each sector, click "Editar" to expand and check/uncheck waiters
4. Use "Copiar de ayer" to repeat previous day's assignments
5. Click "Guardar Asignaciones" to save

### Features:
- Date picker for assignment date
- Shift selector (all day, morning, afternoon, night)
- Visual display of assigned vs unassigned waiters
- Copy from previous day functionality
- Clear all assignments option
- Real-time validation of waiter roles (only WAITER role users shown)
- **Exclusive assignment**: A waiter can only be assigned to ONE sector at a time (assigning to a new sector removes from previous)

## Sector-Based Waiter Notifications (January 2026)

When waiters are assigned to sectors, WebSocket notifications are filtered so each waiter only receives events for their assigned sectors. This prevents notification overload and ensures waiters only see relevant alerts.

### How it Works

1. **On WebSocket Connect**: When a waiter connects to `/ws/waiter`, the gateway fetches their today's sector assignments from the database and registers the connection to those sector channels.

2. **Event Publishing**: Events include `sector_id` when available. Events with `sector_id` are published to `sector:{id}:waiters` channel instead of `branch:{id}:waiters`.

3. **Dynamic Updates**: Waiters can send `refresh_sectors` message to re-fetch their assignments if they change during a shift.

### Backend Implementation

```python
# ws_gateway/connection_manager.py
class ConnectionManager:
    by_sector: dict[int, set[WebSocket]]  # Index connections by sector

    async def connect(self, websocket, user_id, branch_ids, sector_ids=None):
        # Register by user, branch, AND sector

    async def send_to_sector(self, sector_id, payload):
        # Send only to waiters assigned to this sector

# ws_gateway/main.py
@app.websocket("/ws/waiter")
async def waiter_websocket(websocket, token):
    # Get today's sector assignments for this waiter
    sector_ids = get_waiter_sector_ids(user_id, tenant_id)
    await manager.connect(websocket, user_id, branch_ids, sector_ids)
```

### Event Schema Update

```python
# shared/events.py
@dataclass
class Event:
    type: str
    tenant_id: int
    branch_id: int
    table_id: int | None = None
    session_id: int | None = None
    sector_id: int | None = None  # NEW: For sector-based filtering
    entity: dict[str, Any] = field(default_factory=dict)
    actor: dict[str, Any] = field(default_factory=dict)

# All publish functions accept optional sector_id parameter and publish to multiple channels:
# - publish_round_event() → waiters, kitchen, admin, session (4 channels)
# - publish_service_call_event() → waiters, admin, session (3 channels)
# - publish_check_event() → waiters, admin, session (3 channels)
# - publish_table_event() → waiters, admin (2 channels)
```

### Waiter Endpoints for pwaWaiter

```
GET /api/waiter/my-assignments?assignment_date={date}&shift={shift}
  → Returns waiter's assigned sectors with sector_ids list for WebSocket filtering

GET /api/waiter/my-tables?assignment_date={date}&shift={shift}
  → Returns tables in waiter's assigned sectors
```

### pwaWaiter Integration

```typescript
// On login, fetch assigned sectors
const { sector_ids } = await waiterAPI.getMyAssignments()

// Store sector_ids for client-side filtering (backup)
// WebSocket events are already filtered server-side
```

### Fallback Behavior

- If a waiter has no sector assignments, they receive ALL branch events (like before)
- Managers and Admins always receive all branch events regardless of sector assignments
- Events without `sector_id` are broadcast to the entire branch

## Tables Display by Sector (January 2026)

The Tables page (`Dashboard/src/pages/Tables.tsx`) groups tables by sector to avoid confusion when table numbers repeat across areas.

### UI Structure

```tsx
// Tables are grouped by sector with visual headers
{tablesBySector.map(([sector, sectorTables]) => (
  <div key={sector}>
    <h3>{sector}</h3>  {/* e.g., "Interior", "Terraza" */}
    <Badge>{sectorTables.length} mesas</Badge>
    <div className="grid">
      {sectorTables.map(table => <TableCard ... />)}
    </div>
  </div>
))}
```

### Sorting Logic

1. Tables grouped by `sector` field (alphabetically sorted)
2. Within each sector, sorted by status urgency then by number:
   - `cuenta_solicitada` (most urgent)
   - `solicito_pedido`
   - `pedido_cumplido`
   - `ocupada`
   - `libre` (least urgent)

## Recipe Module (January 2026)

Technical recipe sheets ("fichas técnicas") for Kitchen staff. Recipes can be linked to products and ingested into the RAG chatbot for AI-powered customer queries.

### Access Control

- **KITCHEN, MANAGER, ADMIN**: Full CRUD access to recipes
- **Navigation**: Cocina → Recetas (`/recipes`)

### Database Model

```python
# backend/rest_api/models.py
class Recipe(AuditMixin, Base):
    __tablename__ = "recipe"
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    tenant_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("tenant.id"))
    branch_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("branch.id"))
    product_id: Mapped[Optional[int]] = mapped_column(BigInteger, ForeignKey("product.id"))
    name: Mapped[str] = mapped_column(Text)
    description: Mapped[Optional[str]] = mapped_column(Text)
    category: Mapped[Optional[str]] = mapped_column(Text)  # e.g., "Platos Principales"
    cuisine_type: Mapped[Optional[str]] = mapped_column(Text)  # e.g., "Italiana"
    difficulty: Mapped[Optional[str]] = mapped_column(Text)  # EASY, MEDIUM, HARD
    prep_time_minutes: Mapped[Optional[int]]
    cook_time_minutes: Mapped[Optional[int]]
    total_time_minutes: Mapped[Optional[int]]  # Auto-calculated
    servings: Mapped[Optional[int]]
    calories_per_serving: Mapped[Optional[int]]
    ingredients: Mapped[list] = mapped_column(JSONB)  # [{name, quantity, unit, notes}]
    preparation_steps: Mapped[list] = mapped_column(JSONB)  # [{step, instruction, time_minutes}]
    chef_notes: Mapped[Optional[str]]
    presentation_tips: Mapped[Optional[str]]
    storage_instructions: Mapped[Optional[str]]
    allergens: Mapped[list] = mapped_column(JSONB)  # ["gluten", "dairy"]
    dietary_tags: Mapped[list] = mapped_column(JSONB)  # ["vegetarian", "vegan"]
    cost_cents: Mapped[Optional[int]]
    image: Mapped[Optional[str]]
    is_ingested: Mapped[bool] = mapped_column(Boolean, default=False)
    last_ingested_at: Mapped[Optional[datetime]]
```

### Frontend Types

```typescript
// Dashboard/src/types/index.ts
export type RecipeDifficulty = 'EASY' | 'MEDIUM' | 'HARD'

export interface RecipeIngredient {
  name: string
  quantity: string
  unit: string
  notes?: string
}

export interface RecipePreparationStep {
  step: number       // 1, 2, 3...
  instruction: string
  time_minutes?: number
}

export interface RecipeFormData {
  branch_id: string
  product_id?: string
  name: string
  description?: string
  category?: string
  cuisine_type?: string
  difficulty?: RecipeDifficulty
  prep_time_minutes?: number
  cook_time_minutes?: number
  servings?: number
  calories_per_serving?: number
  ingredients: RecipeIngredient[]
  preparation_steps: RecipePreparationStep[]
  chef_notes?: string
  presentation_tips?: string
  storage_instructions?: string
  allergens: string[]
  dietary_tags: string[]
  cost_cents?: number
  image?: string
  is_active: boolean
}
```

### Store (`Dashboard/src/stores/recipeStore.ts`)

```typescript
interface RecipeState {
  recipes: Recipe[]
  categories: string[]
  isLoading: boolean
  error: string | null

  // Sync local actions
  addRecipe: (data: RecipeFormData) => Recipe
  updateRecipe: (id: string, data: Partial<RecipeFormData>) => void
  deleteRecipe: (id: string) => void

  // Async API actions
  fetchRecipes: (branchId?: number, category?: string) => Promise<void>
  fetchCategories: () => Promise<void>
  createRecipeAsync: (data: RecipeFormData) => Promise<Recipe>
  updateRecipeAsync: (id: string, data: Partial<RecipeFormData>) => Promise<void>
  deleteRecipeAsync: (id: string) => Promise<void>
  ingestRecipeAsync: (id: string) => Promise<{ success: boolean; message: string }>
}

// Selectors
export const selectRecipes = (state: RecipeState) => state.recipes
export const selectRecipeCategories = (state: RecipeState) => state.categories
export const selectRecipesByBranch = (branchId: string) => (state: RecipeState) =>
  state.recipes.filter(r => r.branch_id === branchId)
```

### RAG Ingestion

Recipes can be ingested into the RAG chatbot knowledge base for AI-powered customer queries:

```typescript
// Ingest button in Recipes page
const handleIngest = async (recipeId: string) => {
  const result = await ingestRecipeAsync(recipeId)
  if (result.success) {
    toast.success('Receta ingested al chatbot')
  }
}
```

Backend endpoint converts recipe to structured text and stores in `knowledge_document` table with pgvector embeddings.

### Field Name Mapping (Frontend ↔ Backend)

| Frontend (RecipeFormData) | Backend (Recipe model) |
|---------------------------|------------------------|
| `servings` | `servings` |
| `prep_time_minutes` | `prep_time_minutes` |
| `cook_time_minutes` | `cook_time_minutes` |
| `presentation_tips` | `presentation_tips` |
| `cost_cents` | `cost_cents` |
| `preparation_steps[].step` | `preparation_steps[].step` |
| `preparation_steps[].instruction` | `preparation_steps[].instruction` |
| `preparation_steps[].time_minutes` | `preparation_steps[].time_minutes` |

## Canonical Product Model (January 2026)

The system uses a normalized 19-table model for products to support advanced nutritional queries, dietary filtering, and RAG chatbot responses. This replaces the original 9-table model.

### Migration Phases (All Complete)

- **Phase 0**: Normalized allergens with presence types (contains, may_contain, free_from)
- **Phase 1**: Ingredient system with groups and sub-ingredients
- **Phase 2**: Dietary profile (vegan, vegetarian, gluten-free, celiac-safe, keto, low-sodium)
- **Phase 3**: Cooking methods and sensory profiles (flavors, textures)
- **Phase 4**: Advanced features (modifications, warnings, RAG config)
- **Phase 5**: Consolidated product view and RAG integration

### Key Models

```python
# Product Allergen (Phase 0) - Replaces allergen_ids JSON
ProductAllergen(product_id, allergen_id, presence_type)  # "contains", "may_contain", "free_from"

# Ingredient System (Phase 1)
IngredientGroup(name)  # proteina, vegetal, lacteo, cereal, condimento, otro
Ingredient(tenant_id, name, group_id, is_processed)
SubIngredient(ingredient_id, name)  # For processed ingredients (e.g., mayonnaise → eggs, oil, lemon)
ProductIngredient(product_id, ingredient_id, is_main, notes)

# Dietary Profile (Phase 2)
ProductDietaryProfile(product_id, is_vegetarian, is_vegan, is_gluten_free, is_dairy_free, is_celiac_safe, is_keto, is_low_sodium)

# Cooking/Sensory (Phase 3)
CookingMethod(name)  # horneado, frito, grillado, crudo, hervido, vapor, salteado, braseado
FlavorProfile(name)  # suave, intenso, dulce, salado, acido, amargo, umami, picante
TextureProfile(name)  # crocante, cremoso, tierno, firme, esponjoso, gelatinoso, granulado
ProductCookingMethod(product_id, cooking_method_id)
ProductFlavor(product_id, flavor_profile_id)
ProductTexture(product_id, texture_profile_id)
ProductCooking(product_id, uses_oil, prep_time_minutes, cook_time_minutes)

# Advanced Features (Phase 4)
ProductModification(product_id, action, item, is_allowed, extra_cost_cents)  # action: "remove" or "substitute"
ProductWarning(product_id, text, severity)  # severity: "info", "warning", "danger"
ProductRAGConfig(product_id, risk_level, custom_disclaimer, highlight_allergens)  # risk_level: "low", "medium", "high"
```

### Dashboard - Ingredients Page

**Navigation:** Cocina → Ingredientes (`/ingredients`)

**Store** (`Dashboard/src/stores/ingredientStore.ts`):
```typescript
interface IngredientState {
  ingredients: Ingredient[]
  groups: IngredientGroup[]
  isLoading: boolean
  error: string | null

  fetchIngredients: (groupId?: number) => Promise<void>
  fetchGroups: () => Promise<void>
  createIngredientAsync: (data: IngredientFormData) => Promise<Ingredient>
  updateIngredientAsync: (id: string, data: Partial<IngredientFormData>) => Promise<void>
  deleteIngredientAsync: (id: string) => Promise<void>
  createGroupAsync: (name: string, description?: string, icon?: string) => Promise<IngredientGroup>
  createSubIngredientAsync: (ingredientId: string, data: SubIngredientFormData) => Promise<void>
  deleteSubIngredientAsync: (ingredientId: string, subIngredientId: number) => Promise<void>
}
```

### API Endpoints

```
# Ingredients (Phase 1)
GET  /api/admin/ingredients?group_id={id}  # List ingredients, optionally by group
POST /api/admin/ingredients                 # Create ingredient
GET  /api/admin/ingredients/{id}            # Get with sub-ingredients
PUT  /api/admin/ingredients/{id}            # Update
DELETE /api/admin/ingredients/{id}          # Soft delete
POST /api/admin/ingredients/{id}/sub        # Add sub-ingredient
DELETE /api/admin/ingredients/{id}/sub/{subId}  # Delete sub-ingredient
GET  /api/admin/ingredient-groups           # List groups
POST /api/admin/ingredient-groups           # Create group

# Complete Product View (Phase 5)
GET  /api/public/menu/{branch_slug}/products/{product_id}/complete
  → Returns ProductCompleteOutput with all canonical data
```

### Consolidated Product View Service

```python
# backend/rest_api/services/product_view.py
from rest_api.services.product_view import get_product_complete, generate_product_text_for_rag

# Get complete product with all canonical data
view = get_product_complete(db, product_id)
# Returns: {
#   id, name, description, image, category_id, subcategory_id, featured, popular, badge,
#   allergens: { contains: [...], may_contain: [...], free_from: [...] },
#   dietary: { is_vegetarian, is_vegan, is_gluten_free, is_dairy_free, is_celiac_safe, is_keto, is_low_sodium },
#   ingredients: [{ id, name, group_name, is_processed, is_main, notes, sub_ingredients: [...] }],
#   cooking: { methods: [...], uses_oil, prep_time_minutes, cook_time_minutes },
#   sensory: { flavors: [...], textures: [...] },
#   modifications: [{ id, action, item, is_allowed, extra_cost_cents }],
#   warnings: [{ id, text, severity }],
#   rag_config: { risk_level, custom_disclaimer, highlight_allergens } | null
# }

# Generate text for RAG ingestion
text = generate_product_text_for_rag(view, price_cents=12500)
# Returns enriched text with allergens, dietary profile, ingredients, etc.
```

### RAG Integration (Phase 5)

The RAG service uses the consolidated view for enriched product ingestion:

```python
# backend/rest_api/services/rag_service.py
# ingest_product() now uses get_product_complete() and generate_product_text_for_rag()
# Generates text like:
# PRODUCTO: Milanesa Napolitana
# Descripción: Milanesa de ternera con salsa de tomate y queso
# Precio: $125.00
# CONTIENE ALÉRGENOS: Gluten, Lácteos, Huevo
# PUEDE CONTENER TRAZAS DE: Frutos Secos
# Perfil dietético: Sin restricciones
# Ingredientes principales: Carne de ternera, Pan rallado
# Otros ingredientes: Huevo, Queso, Tomate
# Métodos de cocción: frito
# ⚠️ Advertencia: Contiene huesos pequeños
```

### Frontend Types

```typescript
// Dashboard/src/types/index.ts
export interface IngredientGroup {
  id: string
  name: string
  description?: string
  icon?: string
  is_active: boolean
}

export interface SubIngredient {
  id: number
  ingredient_id: number
  name: string
  description?: string
  is_active: boolean
}

export interface Ingredient {
  id: string
  tenant_id: number
  name: string
  description?: string
  group_id?: number
  group_name?: string
  is_processed: boolean
  is_active: boolean
  created_at: string
  sub_ingredients: SubIngredient[]
}

export interface IngredientFormData {
  name: string
  description?: string
  group_id?: number
  is_processed: boolean
}

export interface SubIngredientFormData {
  name: string
  description?: string
}
```

### Seed Data (Catalogs)

On first run, the backend seeds cooking methods, flavor profiles, texture profiles, and ingredient groups:

```python
# Cooking methods: horneado, frito, grillado, crudo, hervido, vapor, salteado, braseado
# Flavor profiles: suave, intenso, dulce, salado, acido, amargo, umami, picante
# Texture profiles: crocante, cremoso, tierno, firme, esponjoso, gelatinoso, granulado
# Ingredient groups: Proteína, Vegetal, Lácteo, Cereal, Condimento, Otro
```
