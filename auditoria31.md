# Auditoría 31: WebSocket - Análisis Arquitectónico Exhaustivo

**Fecha:** 2026-01-16
**Auditor:** Senior Software Architect
**Enfoque:** Análisis completo de la implementación WebSocket en todo el proyecto
**Método:** Revisión de código, patrones de arquitectura, y análisis de mejoras potenciales

---

## Resumen Ejecutivo

| Componente | Estado | Evaluación |
|------------|--------|------------|
| **Backend WS Gateway** | ✅ EXCELENTE | Arquitectura sólida, 4 endpoints bien definidos |
| **ConnectionManager** | ✅ EXCELENTE | Memory-safe después de fixes CRIT-05/06 |
| **Dashboard WebSocket** | ✅ EXCELENTE | Throttling, filtering, soft/hard disconnect |
| **pwaMenu WebSocket** | ✅ EXCELENTE | Heartbeat y visibility handling |
| **pwaWaiter WebSocket** | ✅ EXCELENTE | Token refresh + heartbeat timeout + visibility |
| **Redis Pub/Sub** | ✅ EXCELENTE | Pool singleton, 4 canales |

### Defectos Identificados y Corregidos

| Severidad | Cantidad | Estado |
|-----------|----------|--------|
| **CRITICAL** | 0 | N/A |
| **HIGH** | 2 | ✅ Corregidos |
| **MEDIUM** | 5 | ✅ Corregidos |
| **LOW** | 4 | ✅ 3 Corregidos, 1 Aceptado |
| **TOTAL** | **11** | **10 Corregidos** |

### Correcciones Aplicadas

| ID | Severidad | Descripción | Archivo | Estado |
|----|-----------|-------------|---------|--------|
| WS-31-HIGH-01 | HIGH | Heartbeat timeout detection | `pwaWaiter/websocket.ts` | ✅ |
| WS-31-HIGH-02 | HIGH | Soft/hard disconnect | `Dashboard/websocket.ts` | ✅ |
| WS-31-MED-01 | MEDIUM | Pong handling consistente | `pwaWaiter/websocket.ts` | ✅ |
| WS-31-MED-02 | MEDIUM | Visibility handler | `pwaWaiter/websocket.ts` | ✅ |
| WS-31-MED-03 | MEDIUM | Clear connectionPromise on error | `pwaWaiter/websocket.ts` | ✅ |
| WS-31-MED-04 | MEDIUM | Log mensajes desconocidos | `backend/ws_gateway/main.py` | ✅ |
| WS-31-MED-05 | MEDIUM | HMR cleanup guards | Múltiples hooks | ✅ |
| WS-31-LOW-01 | LOW | Constantes sincronizadas | `pwaWaiter/constants.ts` | ✅ |
| WS-31-LOW-02 | LOW | getLastPongAge documentado | `pwaWaiter/websocket.ts` | ✅ |
| WS-31-LOW-03 | LOW | Métricas/observabilidad | N/A | ⚠️ Futuro |
| WS-31-LOW-04 | LOW | /ws/kitchen endpoint | Documentado en CLAUDE.md | ✅ |

---

## PARTE 1: Arquitectura Actual

### 1.1 Topología de Conexiones

```
┌─────────────────────────────────────────────────────────────────────┐
│                           BACKEND                                    │
├─────────────────────────────────────────────────────────────────────┤
│  REST API (8000)                    WS Gateway (8001)               │
│  ┌─────────────┐                   ┌─────────────────────────┐      │
│  │ Routers     │──publish────────→ │ Redis Subscriber        │      │
│  │ (events.py) │                   │ (channels: branch:*,    │      │
│  └─────────────┘                   │  sector:*, session:*)   │      │
│         │                          └──────────┬──────────────┘      │
│         │                                     │                      │
│         └──────────────┬──────────────────────┤                      │
│                        ↓                      ↓                      │
│              ┌─────────────────────────────────────┐                 │
│              │       ConnectionManager             │                 │
│              │  - by_user: dict[int, set[WS]]     │                 │
│              │  - by_branch: dict[int, set[WS]]   │                 │
│              │  - by_sector: dict[int, set[WS]]   │                 │
│              │  - by_session: dict[int, set[WS]]  │                 │
│              └───────────────┬─────────────────────┘                 │
│                              │                                       │
│              ┌───────────────┼───────────────┐                       │
│              ↓               ↓               ↓                       │
│        /ws/waiter      /ws/kitchen     /ws/admin                    │
│        /ws/diner                                                     │
└─────────────────────────────────────────────────────────────────────┘
                  │               │               │
                  ↓               ↓               ↓
┌─────────────────┐ ┌─────────────────┐ ┌─────────────────┐
│   pwaWaiter     │ │   (Disponible)  │ │   Dashboard     │
│   - JWT token   │ │   para futuro   │ │   - JWT token   │
│   - Auto-refresh│ │   kitchen app   │ │   - Throttling  │
│   - Visibility  │ │                 │ │   - Soft/hard   │
│   - HB timeout  │ │                 │ │     disconnect  │
└─────────────────┘ └─────────────────┘ └─────────────────┘

┌─────────────────┐
│    pwaMenu      │
│  - Table token  │
│  - Visibility   │
│  - HB timeout   │
└─────────────────┘
```

### 1.2 Patrón de Eventos (4 Canales)

```python
# backend/shared/events.py - Sistema de 4 canales
async def publish_round_event(...):
    # 1. Waiters (sector o branch)
    if sector_id:
        await publish_to_sector(redis, sector_id, event)
    else:
        await publish_to_waiters(redis, branch_id, event)

    # 2. Kitchen
    await publish_to_kitchen(redis, branch_id, event)

    # 3. Admin/Dashboard
    await publish_to_admin(redis, branch_id, event)

    # 4. Session/Diners
    await publish_to_session(redis, session_id, event)
```

### 1.3 Heartbeat Configuration (Sincronizada)

| App | Intervalo | Timeout | Formato |
|-----|-----------|---------|---------|
| Dashboard | 30s | 10s | JSON `{"type":"ping"}` |
| pwaMenu | 30s | 10s | JSON `{"type":"ping"}` |
| pwaWaiter | 30s | 10s | JSON `{"type":"ping"}` |
| Backend | Acepta ambos | 60s (stale) | texto o JSON |

---

## PARTE 2: Correcciones Implementadas

### WS-31-HIGH-01: ✅ pwaWaiter Heartbeat Timeout Detection

**Archivo:** `pwaWaiter/src/services/websocket.ts`
**Estado:** CORREGIDO

**Cambios aplicados:**
```typescript
// Nuevas propiedades
private heartbeatTimeout: ReturnType<typeof setTimeout> | null = null
private lastPongReceived: number = 0

// Método sendPing con timeout
private sendPing(): void {
  if (!this.ws || this.ws.readyState !== WebSocket.OPEN) return

  this.ws.send(JSON.stringify({ type: 'ping' }))

  // WS-31-HIGH-01 FIX: Set timeout for pong response (10s default)
  const HEARTBEAT_TIMEOUT = WS_CONFIG.HEARTBEAT_TIMEOUT || 10000
  this.heartbeatTimeout = setTimeout(() => {
    wsLogger.warn('Heartbeat timeout - no pong received')
    this.ws?.close(4000, 'Heartbeat timeout')
  }, HEARTBEAT_TIMEOUT)
}

// En handleMessage - captura pong
if (data.type === 'pong') {
  this.lastPongReceived = Date.now()
  this.clearHeartbeatTimeout()
  return // No propaga a listeners
}
```

---

### WS-31-HIGH-02: ✅ Dashboard Soft/Hard Disconnect

**Archivo:** `Dashboard/src/services/websocket.ts`
**Estado:** CORREGIDO

**Cambios aplicados:**
```typescript
/**
 * WS-31-HIGH-02 FIX: Soft disconnect - close socket but preserve listeners
 * Use this when temporarily disconnecting
 */
softDisconnect(): void {
  this.isIntentionallyClosed = true
  this.stopHeartbeat()
  if (this.ws) {
    this.ws.close()
    this.ws = null
  }
  this.reconnectAttempts = 0
  this.notifyConnectionState(false)
}

/**
 * WS-31-HIGH-02 FIX: Hard disconnect - close socket AND clear all listeners
 * Use this ONLY when logging out
 */
disconnect(): void {
  this.softDisconnect()
  this.listeners.clear()
  this.connectionStateListeners.clear()
}

/**
 * Full cleanup (alias for disconnect)
 */
destroy(): void {
  this.disconnect()
}
```

---

### WS-31-MED-01: ✅ Pong Handling Consistente

**Archivo:** `pwaWaiter/src/services/websocket.ts`
**Estado:** CORREGIDO

Ahora pwaWaiter maneja pong igual que Dashboard y pwaMenu:
```typescript
private handleMessage(event: MessageEvent): void {
  const data = JSON.parse(event.data)

  // WS-31-MED-01 FIX: Handle pong response (consistent with pwaMenu/Dashboard)
  if (data.type === 'pong') {
    this.lastPongReceived = Date.now()
    this.clearHeartbeatTimeout()
    return // Don't propagate to listeners
  }
  // ... rest of handling
}
```

---

### WS-31-MED-02: ✅ Visibility Handler en pwaWaiter

**Archivo:** `pwaWaiter/src/services/websocket.ts`
**Estado:** CORREGIDO

**Cambios aplicados:**
```typescript
private visibilityHandler: (() => void) | null = null

constructor() {
  // WS-31-MED-02 FIX: Set up visibility change listener
  this.setupVisibilityListener()
}

private setupVisibilityListener(): void {
  if (typeof document === 'undefined') return
  this.cleanupVisibilityListener()

  this.visibilityHandler = () => {
    if (document.visibilityState === 'visible') {
      if (!this.isIntentionalClose && this.token && !this.isConnected()) {
        this.reconnectAttempts = 0
        this.connectionPromise = null
        this.connect(this.token)
      } else if (this.isConnected()) {
        this.sendPing() // Verify connection is still alive
      }
    }
  }
  document.addEventListener('visibilitychange', this.visibilityHandler)
}
```

---

### WS-31-MED-03: ✅ Clear connectionPromise on Error

**Archivo:** `pwaWaiter/src/services/websocket.ts`
**Estado:** CORREGIDO

```typescript
this.ws.onerror = (error) => {
  // WS-31-MED-03 FIX: Clear connectionPromise on error
  this.connectionPromise = null
  reject(new Error('WebSocket connection failed'))
}

this.ws.onclose = (event) => {
  // WS-31-MED-03 FIX: Clear connectionPromise on close
  this.connectionPromise = null
  // ...
}
```

---

### WS-31-MED-04: ✅ Log Mensajes Desconocidos en Backend

**Archivo:** `backend/ws_gateway/main.py`
**Estado:** CORREGIDO

Ahora todos los endpoints WebSocket loguean mensajes desconocidos:
```python
# En waiter, kitchen, admin, y diner endpoints
else:
    # WS-31-MED-04 FIX: Log unknown messages for debugging
    logger.debug(
        "Unknown message from waiter",
        user_id=user_id,
        message=data[:100] if len(data) > 100 else data,
    )
```

---

### WS-31-MED-05: ✅ HMR Cleanup Guards

**Archivos:**
- `Dashboard/src/hooks/useAdminWebSocket.ts`
- `Dashboard/src/hooks/useTableWebSocket.ts`
- `Dashboard/src/hooks/useWebSocketConnection.ts`
- `pwaMenu/src/hooks/useOrderUpdates.ts`

**Estado:** CORREGIDO

```typescript
useEffect(() => {
  const unsubscribe = dashboardWS.on('*', handler)

  // WS-31-MED-05 FIX: HMR cleanup guard for development
  if (import.meta.hot) {
    import.meta.hot.dispose(() => {
      unsubscribe()
    })
  }

  return unsubscribe
}, [])
```

---

### WS-31-LOW-01: ✅ Constantes Sincronizadas

**Archivo:** `pwaWaiter/src/utils/constants.ts`
**Estado:** CORREGIDO

```typescript
// WS-31-LOW-01: Keep these values synchronized with Dashboard/pwaMenu
export const WS_CONFIG = {
  RECONNECT_INTERVAL: 1000,      // Base delay (was 3000, now matches others)
  MAX_RECONNECT_DELAY: 30000,    // Maximum reconnect delay
  MAX_RECONNECT_ATTEMPTS: 10,
  HEARTBEAT_INTERVAL: 30000,     // 30 seconds ping interval
  HEARTBEAT_TIMEOUT: 10000,      // WS-31-HIGH-01 FIX: 10 seconds to receive pong
  JITTER_FACTOR: 0.3,            // Add up to 30% random jitter
} as const
```

---

### WS-31-LOW-02: ✅ getLastPongAge Documentado

**Archivo:** `pwaWaiter/src/services/websocket.ts`
**Estado:** CORREGIDO (añadido para debugging)

```typescript
/**
 * Get the time since last pong (for debugging)
 */
getLastPongAge(): number {
  if (this.lastPongReceived === 0) return -1
  return Date.now() - this.lastPongReceived
}
```

---

### WS-31-LOW-04: ✅ /ws/kitchen Endpoint Documentado

**Estado:** DOCUMENTADO

El endpoint `/ws/kitchen` está implementado y funcional en el backend. Actualmente:
- Dashboard usa `/ws/admin` para todos los roles (ADMIN, MANAGER, KITCHEN)
- Kitchen staff recibe todos los eventos de admin

**Decisión:** Mantener como está. El endpoint `/ws/kitchen` está disponible para:
1. Una futura app dedicada de cocina (pwaKitchen)
2. Optimización si se necesita reducir tráfico a cocina

---

## PARTE 3: Fortalezas Arquitectónicas

### ✅ Patrón Singleton Consistente

Todas las apps usan singleton para WebSocket:
```typescript
export const dashboardWS = new DashboardWebSocket()
export const dinerWS = new DinerWebSocket()
export const wsService = new WebSocketService()
```

### ✅ Exponential Backoff con Jitter

Implementado consistentemente en las 3 apps:
```typescript
const exponentialDelay = Math.min(
  BASE_DELAY * Math.pow(2, this.reconnectAttempts - 1),
  MAX_DELAY
)
const jitter = exponentialDelay * JITTER_FACTOR * Math.random()
```

### ✅ Memory-Safe ConnectionManager

Después de CRIT-05/06 fixes:
- Regular dict en vez de defaultdict
- Cleanup de sets vacíos
- Heartbeat tracking para stale connections

### ✅ 4-Channel Event System

Separación clara de canales:
- Waiters: `branch:{id}:waiters` o `sector:{id}:waiters`
- Kitchen: `branch:{id}:kitchen`
- Admin: `branch:{id}:admin`
- Diners: `session:{id}`

### ✅ Throttling en Dashboard

Previene re-renders excesivos:
```typescript
onThrottled(eventType, callback, delay = 100)
onFilteredThrottled(branchId, eventType, callback, delay)
```

### ✅ Token Refresh en pwaWaiter

Auto-refresh antes de expiración:
```typescript
scheduleTokenRefresh()  // 1 min antes de expiración
handleTokenRefresh()    // Reconnect con nuevo token
```

### ✅ Visibility Handlers (Todas las Apps)

Reconexión automática después de sleep/background:
- Dashboard: `useWebSocketConnection.ts`
- pwaMenu: `websocket.ts`
- pwaWaiter: `websocket.ts` (WS-31-MED-02 FIX)

### ✅ Heartbeat Timeout (Todas las Apps)

Detección de conexiones muertas:
- Dashboard: ✅ Implementado
- pwaMenu: ✅ Implementado
- pwaWaiter: ✅ Implementado (WS-31-HIGH-01 FIX)

---

## PARTE 4: Verificación

```bash
# Build verification
cd Dashboard && npm run build && npm run test
cd pwaMenu && npm run build && npm run test
cd pwaWaiter && npm run build

# Backend
cd backend && python -m pytest

# TypeScript
cd Dashboard && npx tsc --noEmit
cd pwaMenu && npx tsc --noEmit
cd pwaWaiter && npx tsc --noEmit
```

---

## Conclusión

### Evaluación General: ✅ ARQUITECTURA EXCELENTE

La implementación WebSocket del proyecto está ahora **completamente optimizada** con las siguientes características:

**Fortalezas:**
- ✅ Patrón singleton consistente en todas las apps
- ✅ Exponential backoff con jitter para reconexión
- ✅ Sistema de 4 canales para routing eficiente
- ✅ Memory-safe después de auditorías previas
- ✅ Heartbeat con timeout en TODAS las apps
- ✅ Visibility handlers en TODAS las apps
- ✅ Token refresh automático en pwaWaiter
- ✅ Soft/hard disconnect en Dashboard
- ✅ HMR cleanup guards en desarrollo
- ✅ Logging de mensajes desconocidos en backend

**Issues Pendientes (Futuros):**
- WS-31-LOW-03: Métricas/observabilidad (opcional, para producción avanzada)

---

**Estado Final:** 11 mejoras identificadas, **10 corregidas**, 1 diferida (métricas futuras)
**Resultado:** ✅ Arquitectura WebSocket production-ready y completamente optimizada
**Fecha:** 2026-01-16
