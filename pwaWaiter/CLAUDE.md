# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

**pwaWaiter** is a Progressive Web App for restaurant waiters to manage their tables in real-time. It provides a mobile-first interface for:

- Viewing all assigned tables with live status updates
- Receiving notifications for new orders, service calls, and check requests
- Taking orders directly (Autogestión mode) for customers without phones
- Resolving service calls from the UI
- Processing payments and clearing tables

## Quick Commands

```bash
cd pwaWaiter && npm install      # Install dependencies
cd pwaWaiter && npm run dev      # Dev server (port 5178)
cd pwaWaiter && npm run build    # Production build
cd pwaWaiter && npm run lint     # ESLint
cd pwaWaiter && npm run test     # Vitest watch mode
cd pwaWaiter && npm run test:run # Vitest single run
```

## Architecture

### Navigation Structure

```
Login → BranchSelect (if multiple) → MainPage
                                        ├── Comensales tab (default) → TableGrid → TableDetailModal
                                        └── Autogestión tab → AutogestionModal (split-view ordering)
```

**MainPage** (`src/pages/MainPage.tsx`): Two-tab header interface
- **Comensales**: Table grid with filters (Urgentes, Activas, Libres, Fuera servicio)
- **Autogestión**: Opens modal for waiter-managed ordering flow

### Store Pattern (Zustand + React 19)

```typescript
// Correct: Use selectors
const tables = useTablesStore(selectTables)
const fetchTables = useTablesStore((s) => s.fetchTables)

// Wrong: Never destructure (causes infinite re-renders)
// const { tables } = useTablesStore()
```

### Key Files

| File | Purpose |
|------|---------|
| `stores/tablesStore.ts` | Table state with WebSocket event handlers |
| `stores/authStore.ts` | JWT auth with proactive token refresh (14 min) |
| `stores/retryQueueStore.ts` | Offline-first operation queue |
| `services/api.ts` | REST client with SSRF protection |
| `services/websocket.ts` | Auto-reconnecting WebSocket client |
| `services/notifications.ts` | Browser push notifications |
| `pages/MainPage.tsx` | Two-tab layout (Comensales/Autogestión) |
| `components/AutogestionModal.tsx` | Split-view order taking modal |
| `components/ComandaTab.tsx` | Quick order component in TableDetailModal |
| `components/TableCard.tsx` | Table card with status badges and animations |

### WebSocket Events Handled

```typescript
// Table lifecycle
TABLE_SESSION_STARTED  // QR scan (blue blink)
TABLE_STATUS_CHANGED   // Status update
TABLE_CLEARED          // Session ended, resets all state

// Round lifecycle
ROUND_PENDING          // New order (yellow pulse)
ROUND_SUBMITTED        // Sent to kitchen
ROUND_IN_KITCHEN       // Being prepared
ROUND_READY            // Ready to serve
ROUND_SERVED           // Delivered
ROUND_CANCELED         // Cancelled

// Service calls
SERVICE_CALL_CREATED   // Customer needs attention (red blink + sound)
SERVICE_CALL_ACKED     // Acknowledged
SERVICE_CALL_CLOSED    // Resolved

// Billing
CHECK_REQUESTED        // Customer wants to pay (purple pulse)
CHECK_PAID             // Payment confirmed
```

### Order Status and Animations

Tables show visual animations based on priority:

| Priority | Trigger | Animation | Duration |
|----------|---------|-----------|----------|
| 1 | `hasServiceCall` | Red blink | 3s |
| 2 | `orderStatus === 'ready_with_kitchen'` | Orange blink | 5s |
| 3 | `statusChanged` | Blue blink | 1.5s |
| 4 | `hasNewOrder` | Yellow pulse | 2s |
| 5 | `check_status === 'REQUESTED'` | Purple pulse | - |

Order status badge colors:

| Status | Badge | Label |
|--------|-------|-------|
| `pending` | Yellow | "Pendiente" |
| `submitted` / `in_kitchen` | Blue | "En Cocina" |
| `ready_with_kitchen` | Orange | "Listo + Cocina" |
| `ready` | Green | "Listo" |
| `served` | Gray | "Servido" |

### Service Call Resolution

Service calls track IDs for UI resolution:
```typescript
// In TableCard type (types/index.ts)
activeServiceCallIds?: number[]  // IDs of OPEN service calls

// Resolution flow in TableDetailModal
serviceCallsAPI.resolve(callId)  // POST /waiter/service-calls/{id}/resolve
// → SERVICE_CALL_CLOSED event removes ID from activeServiceCallIds
```

### API Structure

```typescript
// Core APIs
authAPI       // login, getMe, refresh, logout
tablesAPI     // getTables (maps active_service_call_ids → activeServiceCallIds), getTable, getTableSessionDetail
roundsAPI     // getRound, updateStatus, markAsServed
billingAPI    // confirmCashPayment, clearTable
serviceCallsAPI // acknowledge, resolve

// Waiter-managed ordering (Autogestión)
waiterTableAPI.activateTable(tableId, { diner_count })  // Start session for free table
waiterTableAPI.submitRound(sessionId, { items })        // Submit order
waiterTableAPI.requestCheck(sessionId)                  // Request bill
waiterTableAPI.registerManualPayment({ check_id, amount_cents, manual_method })
waiterTableAPI.closeTable(tableId)                      // End session

// Compact menu for quick ordering (no images)
comandaAPI.getMenuCompact(branchId)
```

### Autogestión Flow

1. Waiter clicks "Autogestión" tab → `AutogestionModal` opens
2. Selects table from list (shows FREE and ACTIVE tables)
3. For FREE tables: enters diner count → `waiterTableAPI.activateTable()` creates session
4. For ACTIVE tables: uses existing session
5. Left panel: search/browse products by category, add to cart
6. Right panel: cart with quantity controls, total display
7. Submit: `waiterTableAPI.submitRound()` → ROUND_PENDING event
8. Round appears in Dashboard for manager approval

### Table Status Colors

| Status | Color | Description |
|--------|-------|-------------|
| FREE | Green | Available |
| ACTIVE | Red | Active session |
| PAYING | Purple | Check requested |
| OUT_OF_SERVICE | Gray | Not in use |

## Backend Integration

Required services (via Docker):
- REST API: `http://localhost:8000`
- WebSocket: `ws://localhost:8001`

Test credentials:
```
Email: waiter@demo.com
Password: waiter123
```

Alternative waiters: `ana@demo.com` / `ana123`, `alberto.cortez@demo.com` / `waiter123`

## PWA Features

- **Installable**: Add to home screen on mobile
- **Offline-capable**: RetryQueueStore queues failed operations for retry
- **Push notifications**: Sound alerts for service calls and check requests
- **Auto-reconnecting**: WebSocket reconnects with exponential backoff

## Key Features

**ComandaTab (in TableDetailModal):**
For customers without phones using paper menus:
- Compact menu endpoint returns products without images
- Local cart state with quantity controls
- Submits via `waiterTableAPI.submitRound()`

**Round Filter Tabs:**
In TableDetailModal, rounds can be filtered:
- "Todos" - All rounds
- "Pendientes" - PENDING, SUBMITTED, IN_KITCHEN
- "Listos" - READY rounds
- "Servidos" - SERVED rounds

**Ready Rounds Pickup Alert:**
Green pulsing alert when rounds reach READY: "¡Pedido listo! Recoger en cocina"

## Conventions

- **UI language**: Spanish
- **Code comments**: English
- **Theme**: Light with orange (#f97316) accent
- **UI style**: Rectangular buttons and UI elements (no rounded corners)
- **Logging**: Use `utils/logger.ts`, never direct `console.*`
- **Prices**: Stored as cents (e.g., $12.50 = 1250)
