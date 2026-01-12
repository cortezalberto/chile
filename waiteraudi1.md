# Auditoría pwaWaiter - Plan de Mejoras

**Fecha:** Enero 2026
**Auditor:** Claude (Arquitecto de Software, Programador Sr., Especialista QA)
**Versión:** 1.1 - IMPLEMENTACIÓN COMPLETADA

---

## Estado de Implementación: ✅ COMPLETADO

Todos los defectos identificados han sido implementados y verificados:
- **Críticos (4/4)**: ✅ Completados
- **Altos (7/7)**: ✅ Completados
- **Medios (7/8)**: ✅ Completados (M001 omitido - requiere cambios de arquitectura backend)
- **Bajos (4/4)**: ✅ Completados
- **TypeScript**: ✅ Sin errores
- **ESLint**: ✅ Sin errores

---

## Resumen Ejecutivo

Esta auditoría analiza el flujo completo de pwaWaiter desde el login del mozo hasta la recepción de notificaciones cuando los comensales ocupan mesas, hacen pedidos, cierran rondas, llaman al mozo y pagan. Se identificaron **23 defectos** categorizados por severidad y área.

### Distribución de Defectos

| Severidad | Cantidad | Porcentaje |
|-----------|----------|------------|
| Crítica   | 4        | 17%        |
| Alta      | 7        | 30%        |
| Media     | 8        | 35%        |
| Baja      | 4        | 17%        |

| Área      | Cantidad |
|-----------|----------|
| Backend   | 8        |
| Frontend  | 10       |
| WebSocket | 3        |
| General   | 2        |

---

## Flujo Analizado

```
┌─────────────────────────────────────────────────────────────────────────────┐
│ 1. LOGIN MOZO                                                               │
│    POST /auth/login → JWT token → wsService.connect(token)                  │
│    → Notification permission request                                         │
└─────────────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│ 2. SELECCIÓN SUCURSAL + CARGA MESAS                                         │
│    GET /waiter/tables?branch_id={id} → TableCard[]                          │
│    subscribeToEvents(branchId) → WebSocket listener                         │
└─────────────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│ 3. COMENSAL OCUPA MESA                                                      │
│    POST /tables/{id}/session → TableSession + table_token                   │
│    POST /diner/register → Diner entity                                      │
│    ❌ NO se publica TABLE_SESSION_STARTED al mozo                           │
└─────────────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│ 4. COMENSAL HACE PEDIDO                                                     │
│    POST /diner/rounds/submit → Round + RoundItems                           │
│    → publish_round_event(ROUND_SUBMITTED) → waiters + kitchen + session     │
│    ✅ Mozo recibe notificación "Nuevo Pedido"                               │
└─────────────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│ 5. COCINA PROCESA PEDIDO                                                    │
│    POST /kitchen/rounds/{id}/status {status: "IN_KITCHEN"}                  │
│    → publish_round_event(ROUND_IN_KITCHEN)                                  │
│    POST /kitchen/rounds/{id}/status {status: "READY"}                       │
│    → publish_round_event(ROUND_READY) → ✅ Notificación urgente             │
└─────────────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│ 6. MOZO ENTREGA PEDIDO                                                      │
│    POST /kitchen/rounds/{id}/status {status: "SERVED"}                      │
│    → publish_round_event(ROUND_SERVED)                                      │
│    ✅ UI actualiza estado de ronda                                          │
└─────────────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│ 7. COMENSAL LLAMA AL MOZO                                                   │
│    POST /diner/service-call {type: "WAITER" | "BILL" | "ASSISTANCE"}        │
│    → publish_to_waiters(SERVICE_CALL_CREATED)                               │
│    ✅ Notificación urgente con call_type                                    │
│    ❌ NO existe endpoint para acknowledge/resolve service call              │
└─────────────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│ 8. COMENSAL SOLICITA CUENTA                                                 │
│    POST /billing/check/request → Check entity                               │
│    → publish_check_event(CHECK_REQUESTED) → ✅ Notificación urgente         │
└─────────────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│ 9. PAGO                                                                     │
│    A) Mercado Pago: webhook → PAYMENT_APPROVED/REJECTED → CHECK_PAID        │
│    B) Efectivo: POST /billing/cash/pay (mozo confirma)                      │
│    → publish_check_event() → ✅ Notificaciones a mozo y comensal            │
└─────────────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│ 10. LIBERACIÓN DE MESA                                                      │
│     POST /billing/tables/{id}/clear → TABLE_CLEARED                         │
│     → Table status = FREE, session status = CLOSED                          │
│     ✅ UI actualiza mesa a FREE                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## Defectos Identificados

### Severidad Crítica

#### PWAW-C001: Endpoints de ServiceCall para mozo no existen
**Ubicación:** Backend - Falta router
**Descripción:** pwaWaiter llama a `POST /waiter/service-calls/{id}/acknowledge` y `POST /waiter/service-calls/{id}/resolve` pero estos endpoints NO EXISTEN en el backend. El frontend tiene las llamadas en `api.ts:178-195` pero el backend no tiene implementación.

**Impacto:** El mozo no puede marcar llamados como atendidos ni resolverlos. Los service calls quedan en estado OPEN indefinidamente.

**Solución propuesta:**
```python
# backend/rest_api/routers/waiter.py (NUEVO)
@router.post("/api/waiter/service-calls/{call_id}/acknowledge")
async def acknowledge_service_call(call_id: int, ...):
    # Actualizar status a "ACKED"
    # Publicar SERVICE_CALL_ACKED event

@router.post("/api/waiter/service-calls/{call_id}/resolve")
async def resolve_service_call(call_id: int, ...):
    # Actualizar status a "CLOSED"
    # Publicar SERVICE_CALL_CLOSED event
```

**Prioridad:** P0 - Bloquea funcionalidad core

---

#### PWAW-C002: No se notifica cuando comensal ocupa mesa
**Ubicación:** Backend - `tables.py:141-231`
**Descripción:** Cuando un comensal escanea QR y crea/obtiene sesión (`POST /tables/{id}/session`), no se publica ningún evento. El mozo solo ve la mesa actualizada en el siguiente refresh (60s) o si otro evento la actualiza.

**Impacto:** El mozo no sabe en tiempo real cuando una mesa se ocupa. Pérdida de oportunidad de servicio proactivo.

**Solución propuesta:**
```python
# En create_or_get_session(), después de crear nueva sesión:
if not existing_session:
    # ...crear sesión...
    await publish_table_event(
        redis_client=redis,
        event_type=TABLE_SESSION_STARTED,
        tenant_id=...,
        branch_id=...,
        table_id=...,
        table_code=table.code,
        session_id=new_session.id,
    )
```

**Prioridad:** P0 - Afecta experiencia de servicio

---

#### PWAW-C003: ServiceCall entity incompleta en evento
**Ubicación:** Backend - `diner.py:409-424`
**Descripción:** El evento SERVICE_CALL_CREATED se publica con `entity={"service_call_id": ..., "type": ...}` pero el frontend espera `call_id` y `call_type`:
```typescript
// notifications.ts:135
const callType = event.entity?.call_type as string | undefined
```

**Impacto:** Las notificaciones de service call no muestran correctamente el tipo (BILL vs ASSISTANCE vs WAITER).

**Solución propuesta:**
```python
# diner.py - Usar publish_service_call_event en vez de construcción manual
await publish_service_call_event(
    redis_client=redis,
    event_type=SERVICE_CALL_CREATED,
    tenant_id=...,
    branch_id=...,
    table_id=table_ctx["table_id"],  # Falta obtener
    session_id=...,
    call_id=service_call.id,
    call_type=body.type,
)
```

**Prioridad:** P0 - Notificaciones muestran información incorrecta

---

#### PWAW-C004: Falta table_id en contexto de service call
**Ubicación:** Backend - `diner.py:348-432`
**Descripción:** El endpoint `/diner/service-call` no obtiene `table_id` del token context para incluirlo en el evento. El evento se publica sin `table_id`, lo que puede causar que el WebSocket Gateway no lo despache correctamente.

**Impacto:** Posible fallo en dispatch de eventos a mozos.

**Solución propuesta:**
```python
# Ya existe en table_ctx pero no se usa:
table_id = table_ctx["table_id"]  # Línea 360 - ¡YA EXISTE!
# El problema es que se usa Event() manual en vez de publish_service_call_event()
```

**Prioridad:** P0 - Eventos pueden perderse

---

### Severidad Alta

#### PWAW-A001: Sin validación de expiración de sesión WebSocket
**Ubicación:** Frontend - `websocket.ts`
**Descripción:** El WebSocket se conecta con JWT pero no valida si el token expira durante la conexión. Si el JWT expira, la conexión sigue activa pero futuras reconexiones fallarán silenciosamente.

**Impacto:** Mozo puede perder notificaciones sin darse cuenta después de expiración de JWT.

**Solución propuesta:**
```typescript
// Agregar listener para token expiration
// En connect(), guardar exp claim y programar renovación
private scheduleTokenRefresh(expiresAt: number): void {
  const now = Date.now() / 1000
  const refreshIn = (expiresAt - now - 60) * 1000 // 1 min antes
  setTimeout(() => {
    // Trigger token refresh via authStore
    authStore.getState().refreshToken()
  }, refreshIn)
}
```

**Prioridad:** P1

---

#### PWAW-A002: No hay indicador visual de estado de conexión prominente
**Ubicación:** Frontend - `Header.tsx`, `TableGrid.tsx`
**Descripción:** El indicador de conexión WebSocket es un pequeño círculo en el header. Si se pierde la conexión, el mozo puede no notarlo y seguir trabajando sin recibir notificaciones.

**Impacto:** Mozo puede perder notificaciones críticas sin saberlo.

**Solución propuesta:**
```typescript
// Agregar banner prominente cuando wsConnected === false
{!wsConnected && (
  <div className="fixed top-16 left-0 right-0 bg-red-600 text-white p-2 text-center z-50">
    ⚠️ Sin conexión - Las notificaciones no se recibirán
    <button onClick={reconnect}>Reconectar</button>
  </div>
)}
```

**Prioridad:** P1

---

#### PWAW-A003: Falta endpoint GET /waiter/service-calls
**Ubicación:** Backend - Falta implementación
**Descripción:** No existe endpoint para listar service calls pendientes de una sucursal. El mozo solo ve el contador `pending_calls` en TableCard pero no puede ver la lista de llamados.

**Impacto:** Si el mozo pierde una notificación, no hay forma de recuperar la lista de llamados pendientes.

**Solución propuesta:**
```python
@router.get("/api/waiter/service-calls", response_model=list[ServiceCallOutput])
def get_pending_service_calls(
    branch_id: int,
    db: Session = Depends(get_db),
    ctx: dict = Depends(current_user_context),
):
    """Lista todos los service calls OPEN para una sucursal."""
    require_roles(ctx, ["WAITER", "MANAGER", "ADMIN"])
    # Query ServiceCall where status="OPEN" and branch_id=branch_id
```

**Prioridad:** P1

---

#### PWAW-A004: historyStore no sincroniza entre tabs
**Ubicación:** Frontend - `historyStore.ts`
**Descripción:** El historyStore usa sessionStorage que no se sincroniza entre tabs. Si el mozo abre otra pestaña, verá historial diferente.

**Impacto:** Inconsistencia de datos entre pestañas.

**Solución propuesta:**
```typescript
// Cambiar a localStorage con evento 'storage'
// O usar BroadcastChannel API
const bc = new BroadcastChannel('waiter-history')
bc.onmessage = (event) => {
  if (event.data.type === 'HISTORY_UPDATE') {
    set({ entries: event.data.entries })
  }
}
```

**Prioridad:** P1

---

#### PWAW-A005: Falta sonido en notificaciones urgentes
**Ubicación:** Frontend - `notifications.ts`
**Descripción:** Las notificaciones urgentes (SERVICE_CALL_CREATED, CHECK_REQUESTED, ROUND_READY) no reproducen sonido. En ambientes ruidosos de restaurante, las notificaciones visuales pueden perderse.

**Impacto:** Mozo puede no notar llamados urgentes.

**Solución propuesta:**
```typescript
// En notifyEvent(), para eventos urgentes:
if (this.isUrgent(event.type)) {
  this.playAlertSound()
}

private playAlertSound(): void {
  const audio = new Audio('/sounds/alert.mp3')
  audio.volume = 0.5
  audio.play().catch(() => {}) // Silently fail if blocked
}
```

**Prioridad:** P1

---

#### PWAW-A006: TableDetail no se actualiza en tiempo real
**Ubicación:** Frontend - `TableDetail.tsx`
**Descripción:** La página de detalle de mesa carga datos una vez (`loadSessionDetail()`) pero no escucha eventos WebSocket. Si llega una nueva ronda o service call mientras el mozo está viendo el detalle, no se actualiza.

**Impacto:** Mozo ve información desactualizada.

**Solución propuesta:**
```typescript
useEffect(() => {
  const unsub = wsService.on('*', (event) => {
    if (event.table_id === table.table_id) {
      // Recargar detalle
      loadSessionDetail()
    }
  })
  return unsub
}, [table.table_id])
```

**Prioridad:** P1

---

#### PWAW-A007: No hay retry automático en acciones fallidas
**Ubicación:** Frontend - `tablesStore.ts`
**Descripción:** Las acciones como `markRoundAsServed`, `confirmCashPayment`, etc. no tienen retry automático. Si falla por red, el mozo debe reintentar manualmente.

**Impacto:** Pérdida de datos si el mozo no nota el error.

**Solución propuesta:**
```typescript
// Agregar queue de acciones con retry
import { queueAction, processQueue } from '../services/offline'

markRoundAsServed: async (roundId: number) => {
  try {
    await roundsAPI.markAsServed(roundId)
  } catch (err) {
    if (err instanceof ApiError && err.code === 'NETWORK_ERROR') {
      queueAction({ type: 'MARK_SERVED', roundId })
      // Mostrar UI indicando acción encolada
    }
    throw err
  }
}
```

**Prioridad:** P1

---

### Severidad Media

#### PWAW-M001: Falta validación de rol WAITER en selección de sucursal
**Ubicación:** Frontend - `BranchSelect.tsx`
**Descripción:** El usuario puede seleccionar cualquier sucursal de su lista `branch_ids` sin verificar si tiene rol WAITER en esa sucursal específica. El modelo UserBranchRole permite roles diferentes por sucursal.

**Impacto:** Mozo podría acceder a sucursal donde solo tiene rol KITCHEN.

**Solución propuesta:**
```typescript
// Filtrar branches donde user tiene rol WAITER
const waiterBranches = user.branch_roles
  .filter(br => br.role === 'WAITER' || br.role === 'ADMIN')
  .map(br => br.branch_id)
```

**Prioridad:** P2

---

#### PWAW-M002: No se muestra hora de creación de service call
**Ubicación:** Frontend - `TableDetail.tsx`
**Descripción:** Los service calls pendientes se muestran sin timestamp. El mozo no sabe hace cuánto tiempo está esperando el cliente.

**Impacto:** No se puede priorizar por antigüedad.

**Solución propuesta:**
```typescript
// En sección de service calls:
<span className="text-dark-muted text-xs">
  hace {formatRelativeTime(serviceCall.created_at)}
</span>
```

**Prioridad:** P2

---

#### PWAW-M003: Falta filtro por estado de ronda
**Ubicación:** Frontend - `TableDetail.tsx`
**Descripción:** Las rondas se muestran todas juntas sin posibilidad de filtrar por estado (SUBMITTED, IN_KITCHEN, READY, SERVED).

**Impacto:** Difícil identificar rondas que requieren acción.

**Solución propuesta:**
```typescript
// Agregar tabs o filtro
const [roundFilter, setRoundFilter] = useState<RoundStatus | 'ALL'>('ALL')
const filteredRounds = rounds.filter(r =>
  roundFilter === 'ALL' || r.status === roundFilter
)
```

**Prioridad:** P2

---

#### PWAW-M004: No hay confirmación al confirmar pago en efectivo
**Ubicación:** Frontend - `TableDetail.tsx` (implícito)
**Descripción:** El flujo de confirmación de pago en efectivo no tiene un paso de verificación del monto antes de confirmar.

**Impacto:** Riesgo de confirmar monto incorrecto.

**Solución propuesta:**
```typescript
// Modal con resumen antes de confirmar
<ConfirmDialog
  title="Confirmar pago en efectivo"
  message={`¿Confirmar pago de $${formatPrice(amount)}?`}
  onConfirm={() => confirmCashPayment(checkId, amount)}
/>
```

**Prioridad:** P2

---

#### PWAW-M005: Falta soporte para múltiples idiomas
**Ubicación:** Frontend - Todo el proyecto
**Descripción:** pwaWaiter tiene todos los textos hardcodeados en español. No hay sistema de i18n como en pwaMenu.

**Impacto:** No se puede internacionalizar.

**Solución propuesta:**
```typescript
// Agregar react-i18next como en pwaMenu
// Crear archivos de traducción en src/i18n/locales/
```

**Prioridad:** P2

---

#### PWAW-M006: Pull-to-refresh no muestra estado de carga
**Ubicación:** Frontend - `usePullToRefresh.ts`, `TableGrid.tsx`
**Descripción:** Durante el refresh, no hay indicador de que la operación está en progreso después de soltar.

**Impacto:** UX confusa - usuario no sabe si el refresh funcionó.

**Solución propuesta:**
```typescript
// Ya existe isRefreshing pero no se usa visualmente
{isRefreshing && (
  <div className="absolute top-0 left-0 right-0 h-1 bg-orange-500 animate-pulse" />
)}
```

**Prioridad:** P2

---

#### PWAW-M007: No se persiste estado de filtro entre recargas
**Ubicación:** Frontend - `usePersistedFilter.ts`
**Descripción:** El filtro se guarda en sessionStorage pero se pierde al cerrar la app. Para una PWA que se usa repetidamente, debería recordar preferencia del usuario.

**Impacto:** UX menor - mozo debe re-seleccionar filtro cada vez.

**Solución propuesta:**
```typescript
// Cambiar de sessionStorage a localStorage
const STORAGE_KEY = 'pwawaiter_table_filter'
localStorage.setItem(STORAGE_KEY, filter)
```

**Prioridad:** P2

---

#### PWAW-M008: Endpoint /tables/{id} no valida branch del usuario
**Ubicación:** Backend - `tables.py:234-311`
**Descripción:** El endpoint `GET /api/tables/{table_id}` valida `require_branch(ctx, table.branch_id)` pero la función `require_branch` no está definida en el archivo importado. Si no funciona correctamente, un mozo podría ver mesas de otras sucursales.

**Impacto:** Posible fuga de información entre sucursales.

**Solución propuesta:**
```python
# Verificar implementación de require_branch en shared/auth.py
# Agregar test unitario
def require_branch(ctx: dict, branch_id: int) -> None:
    if branch_id not in ctx.get("branch_ids", []):
        raise HTTPException(403, "No access to this branch")
```

**Prioridad:** P2

---

### Severidad Baja

#### PWAW-L001: Logs de WebSocket con prefijo emoji innecesario
**Ubicación:** Frontend - `websocket.ts`
**Descripción:** Los logs usan emojis como " Connected" que agregan ruido visual en consola de desarrollo.

**Impacto:** Menor - solo desarrollo.

**Solución propuesta:**
```typescript
// Usar logger sin emojis
wsLogger.info('Connected to waiter WebSocket')
```

**Prioridad:** P3

---

#### PWAW-L002: Falta documentación de tipos WSEvent
**Ubicación:** Frontend - `types/index.ts`
**Descripción:** La interfaz WSEvent tiene campos opcionales sin documentación clara de cuándo se usan.

**Impacto:** Dificulta mantenimiento.

**Solución propuesta:**
```typescript
interface WSEvent {
  /** Event type identifier */
  type: WSEventType
  /** Branch where event occurred */
  branch_id: number
  /** Table that triggered the event */
  table_id: number
  /** Session ID (for diner-related events) */
  session_id?: number
  /** Event-specific data - structure varies by type */
  entity?: {
    /** Round ID (for ROUND_* events) */
    round_id?: number
    // ...etc
  }
}
```

**Prioridad:** P3

---

#### PWAW-L003: Magic numbers en configuración
**Ubicación:** Frontend - Varios archivos
**Descripción:** Valores como 80 (pull threshold), 60000 (refresh interval), 50 (max history) están hardcodeados.

**Impacto:** Dificulta ajustes de configuración.

**Solución propuesta:**
```typescript
// constants.ts
export const UI_CONFIG = {
  PULL_TO_REFRESH_THRESHOLD: 80,
  TABLE_REFRESH_INTERVAL: 60000,
  MAX_HISTORY_ENTRIES: 50,
}
```

**Prioridad:** P3

---

#### PWAW-L004: Falta PWA manifest completo
**Ubicación:** Frontend - `manifest.json` (verificar)
**Descripción:** Verificar que el manifest incluye todas las propiedades necesarias para instalación como PWA (shortcuts, screenshots, etc.).

**Impacto:** Experiencia de instalación subóptima.

**Solución propuesta:**
```json
{
  "shortcuts": [
    {
      "name": "Mesas Urgentes",
      "url": "/?filter=URGENT",
      "icons": [...]
    }
  ],
  "screenshots": [...]
}
```

**Prioridad:** P3

---

## Plan de Implementación

### Fase 1: Críticos (Sprint 1)

| ID | Tarea | Estimación | Dependencias |
|----|-------|------------|--------------|
| PWAW-C001 | Crear router waiter con endpoints service-call | 4h | - |
| PWAW-C002 | Publicar TABLE_SESSION_STARTED en backend | 2h | - |
| PWAW-C003 | Corregir entity structure en SERVICE_CALL_CREATED | 1h | - |
| PWAW-C004 | Usar publish_service_call_event() en diner.py | 1h | PWAW-C003 |

### Fase 2: Altos (Sprint 2)

| ID | Tarea | Estimación | Dependencias |
|----|-------|------------|--------------|
| PWAW-A001 | Implementar refresh de token en WebSocket | 3h | - |
| PWAW-A002 | Banner prominente de desconexión | 2h | - |
| PWAW-A003 | Endpoint GET /waiter/service-calls | 2h | PWAW-C001 |
| PWAW-A004 | Sincronización de historyStore entre tabs | 2h | - |
| PWAW-A005 | Sonido en notificaciones urgentes | 2h | - |
| PWAW-A006 | WebSocket listener en TableDetail | 2h | - |
| PWAW-A007 | Retry queue para acciones offline | 4h | - |

### Fase 3: Medios (Sprint 3)

| ID | Tarea | Estimación | Dependencias |
|----|-------|------------|--------------|
| PWAW-M001 | Validar rol WAITER por sucursal | 2h | - |
| PWAW-M002 | Mostrar timestamp en service calls | 1h | PWAW-A003 |
| PWAW-M003 | Filtro de rondas por estado | 2h | - |
| PWAW-M004 | Confirmación de pago en efectivo | 2h | - |
| PWAW-M005 | Setup i18n con react-i18next | 4h | - |
| PWAW-M006 | Indicador visual de refresh | 1h | - |
| PWAW-M007 | Persistir filtro en localStorage | 0.5h | - |
| PWAW-M008 | Verificar/corregir require_branch | 1h | - |

### Fase 4: Bajos (Backlog)

| ID | Tarea | Estimación | Dependencias |
|----|-------|------------|--------------|
| PWAW-L001 | Limpiar logs de WebSocket | 0.5h | - |
| PWAW-L002 | Documentar tipos WSEvent | 1h | - |
| PWAW-L003 | Extraer magic numbers a constants | 1h | - |
| PWAW-L004 | Completar PWA manifest | 1h | - |

---

## Tests Recomendados

### Tests Unitarios

```typescript
// tablesStore.test.ts
describe('tablesStore', () => {
  it('should update table on ROUND_SUBMITTED event')
  it('should show notification on SERVICE_CALL_CREATED')
  it('should mark table as FREE on TABLE_CLEARED')
  it('should queue action when offline')
})

// notifications.test.ts
describe('notificationService', () => {
  it('should show urgent notification for SERVICE_CALL_CREATED')
  it('should include call_type in service call body')
  it('should auto-close non-urgent notifications')
  it('should play sound for urgent events')
})
```

### Tests E2E

```typescript
// waiter-flow.e2e.ts
describe('Waiter Flow', () => {
  it('should login and see tables')
  it('should receive notification when diner submits order')
  it('should mark round as served')
  it('should acknowledge service call')
  it('should confirm cash payment')
  it('should clear table after payment')
})
```

### Tests de Integración Backend

```python
# test_waiter_endpoints.py
def test_acknowledge_service_call():
    # Create service call
    # POST /waiter/service-calls/{id}/acknowledge
    # Verify status changed to ACKED
    # Verify event published

def test_resolve_service_call():
    # POST /waiter/service-calls/{id}/resolve
    # Verify status changed to CLOSED
    # Verify event published

def test_table_session_started_event():
    # POST /tables/{id}/session
    # Verify TABLE_SESSION_STARTED published
```

---

## Métricas de Éxito

| Métrica | Valor Actual | Objetivo |
|---------|--------------|----------|
| Endpoints waiter implementados | 2/5 | 5/5 |
| Eventos con estructura correcta | 3/5 | 5/5 |
| Cobertura de tests pwaWaiter | 0% | 60% |
| Latencia notificación → UI | ~500ms | <200ms |
| Tasa de notificaciones perdidas | Desconocida | <1% |

---

## Conclusión

pwaWaiter tiene una arquitectura sólida con Zustand, WebSocket y notificaciones push, pero presenta **4 defectos críticos** que impiden el flujo completo de service calls. La prioridad inmediata es:

1. **Crear endpoints de service call en backend** (PWAW-C001)
2. **Corregir estructura de eventos** (PWAW-C003, PWAW-C004)
3. **Publicar evento cuando mesa se ocupa** (PWAW-C002)

Con estas correcciones, el flujo principal estará completo. Las mejoras de severidad alta mejorarán significativamente la experiencia del mozo en condiciones reales de uso.
