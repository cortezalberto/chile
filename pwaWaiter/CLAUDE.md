# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

**pwaWaiter** is a Progressive Web App for restaurant waiters to manage their tables in real-time. It provides a mobile-first interface for:

- Viewing all assigned tables with live status updates
- Receiving notifications for new orders, service calls, and check requests
- Marking rounds as served
- Processing cash payments
- Clearing tables after payment

## Quick Commands

```bash
cd pwaWaiter && npm install    # Install dependencies
cd pwaWaiter && npm run dev    # Dev server (port 5178)
cd pwaWaiter && npm run build  # Production build
cd pwaWaiter && npm run lint   # ESLint
```

## Architecture

### Store Pattern (Zustand + React 19)

Uses the same selector pattern as Dashboard and pwaMenu:

```typescript
// Correct: Use selectors
const tables = useTablesStore(selectTables)
const fetchTables = useTablesStore((s) => s.fetchTables)

// Wrong: Never destructure
// const { tables } = useTablesStore()
```

### Key Files

- `src/stores/authStore.ts` - JWT authentication with WAITER role validation
- `src/stores/tablesStore.ts` - Table state with real-time WebSocket updates
- `src/services/api.ts` - REST API client for backend communication
- `src/services/websocket.ts` - WebSocket client with auto-reconnection
- `src/services/notifications.ts` - Browser push notifications

### WebSocket Events Handled

```typescript
// Events that update table state:
ROUND_SUBMITTED      // New order from customer
ROUND_IN_KITCHEN     // Order being prepared
ROUND_READY          // Order ready to serve
ROUND_SERVED         // Order delivered
SERVICE_CALL_CREATED // Customer needs attention
CHECK_REQUESTED      // Customer wants to pay
CHECK_PAID           // Payment confirmed
TABLE_CLEARED        // Table released
```

### Page Flow

1. **Login** - Email/password authentication (requires WAITER role)
2. **BranchSelect** - Choose working branch (if user has multiple)
3. **TableGrid** - Main view showing all tables grouped by urgency
4. **TableDetail** - Session info, rounds, service calls, billing

### Table Status Colors

| Status | Color | Description |
|--------|-------|-------------|
| FREE | Green | Table is free |
| ACTIVE | Red | Active session |
| PAYING | Purple | Check requested |
| OUT_OF_SERVICE | Gray | Not in use |

## Backend Integration

Requires backend running on:
- REST API: `http://localhost:8000`
- WebSocket: `ws://localhost:8001`

Test with waiter credentials:
```
Email: waiter@demo.com
Password: waiter123
```

## PWA Features

- Installable on mobile devices
- Offline-capable (caches static assets)
- Push notifications for urgent events (service calls, check requests)
- Auto-reconnecting WebSocket connection

## Conventions

- **UI language**: Spanish
- **Code comments**: English
- **Theme**: Dark with orange (#f97316) accent
- **Logging**: Use `utils/logger.ts` loggers, never direct console.*
