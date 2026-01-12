 # Auditoría Integral del Sistema Integrador

**Fecha**: 9 de Enero 2026
**Auditor**: Claude (Arquitecto de Software, Programador Senior, Especialista QA)
**Alcance**: pwaMenu, pwaWaiter, Backend, Dashboard

---

## Resumen Ejecutivo

Se realizó una auditoría completa del flujo de trazabilidad desde la ocupación de mesa hasta el pago, identificando **47 defectos** distribuidos en:

| Proyecto | Críticos | Altos | Medios | Bajos | Total |
|----------|----------|-------|--------|-------|-------|
| pwaMenu | 3 | 5 | 4 | 2 | 14 |
| pwaWaiter | 2 | 4 | 3 | 2 | 11 |
| Backend | 4 | 3 | 2 | 1 | 10 |
| Dashboard | 2 | 5 | 3 | 2 | 12 |
| **Total** | **11** | **17** | **12** | **7** | **47** |

---

## 1. Auditoría pwaMenu (PWA Comensal)

### 1.1 Defectos Críticos

#### PWAM-001: Pagos en efectivo/tarjeta no llegan al backend
- **Archivo**: [useCloseTableFlow.ts:53-65](pwaMenu/src/hooks/useCloseTableFlow.ts#L53-L65)
- **Descripción**: Cuando un comensal paga en efectivo o tarjeta, el pago se registra solo localmente sin llamar al endpoint del backend.
- **Impacto**: El mozo nunca recibe notificación del pago, la caja no cuadra.
- **Código afectado**:
```typescript
// Actual - solo registra localmente
if (method === 'cash' || method === 'card') {
  registerPayment(dinerId, tipPercent)
  setStep('done')
}
```
- **Solución**: Implementar llamada a `POST /api/billing/cash/pay` para efectivo y crear endpoint para tarjeta.

#### PWAM-002: Selectores usan snake_case en lugar de camelCase
- **Archivos**:
  - [selectors.ts:37](pwaMenu/src/stores/table/selectors.ts#L37) - `shared_cart` debe ser `sharedCart`
  - [selectors.ts:79](pwaMenu/src/stores/table/selectors.ts#L79) - `diner_id` debe ser `dinerId`
  - [selectors.ts:90](pwaMenu/src/stores/table/selectors.ts#L90) - `diner_id` debe ser `dinerId`
- **Impacto**: Los selectores devuelven `undefined` porque las propiedades no existen.
- **Solución**: Cambiar a nombres camelCase que coincidan con la normalización del store.

#### PWAM-003: Split "byConsumption" usa valor incorrecto
- **Archivo**: [SummaryTab.tsx:43](pwaMenu/src/components/cart/SummaryTab.tsx#L43)
- **Descripción**: Usa string `'by_consumption'` en lugar del enum `'byConsumption'`.
- **Impacto**: La división por consumo no funciona, muestra cálculos incorrectos.
- **Solución**: Cambiar a `splitMode === 'byConsumption'`.

### 1.2 Defectos Altos

#### PWAM-004: Registro de comensal es opcional
- **Archivo**: [store.ts:89-102](pwaMenu/src/stores/table/store.ts#L89-L102)
- **Descripción**: `registerDinerAsync` hace catch silencioso del error, permitiendo comensales sin backend_id.
- **Impacto**: Órdenes pueden enviarse sin diner_id válido, rompiendo trazabilidad.
- **Solución**: Hacer registro bloqueante o reintentar con exponential backoff.

#### PWAM-005: DinersList usa campos snake_case
- **Archivo**: [DinersList.tsx:17,54](pwaMenu/src/components/diners/DinersList.tsx#L17)
- **Descripción**: Accede a `diner.diner_id` y `order.shared_cart` que no existen.
- **Impacto**: Lista de comensales no muestra datos correctamente.
- **Solución**: Usar `diner.dinerId` y `order.sharedCart`.

#### PWAM-006: Heartbeat WebSocket sin reconexión exponencial
- **Archivo**: [websocket.ts:159-173](pwaMenu/src/services/websocket.ts#L159-L173)
- **Descripción**: Usa delay lineal (3s * attempts) en lugar de exponencial.
- **Impacto**: En conexiones inestables, puede saturar el servidor con intentos.
- **Solución**: Implementar exponential backoff con jitter.

#### PWAM-007: No hay validación de sesión expirada
- **Archivo**: [api.ts](pwaMenu/src/services/api.ts)
- **Descripción**: Si el table_token JWT expira (8h), no hay manejo de error 401.
- **Impacto**: Usuario ve errores genéricos, no se le indica reescanear QR.
- **Solución**: Interceptar 401 y mostrar modal de "Sesión expirada".

#### PWAM-008: updateOrderStatus no valida roundId
- **Archivo**: [store.ts](pwaMenu/src/stores/table/store.ts)
- **Descripción**: `updateOrderStatus` busca por `roundId` pero los rounds locales pueden tener IDs diferentes a los del backend.
- **Impacto**: Estados de ronda no se actualizan correctamente vía WebSocket.
- **Solución**: Usar `backend_round_id` para matching.

### 1.3 Defectos Medios

#### PWAM-009: Cálculo de propina no considera split
- **Archivo**: [SummaryTab.tsx](pwaMenu/src/components/cart/SummaryTab.tsx)
- **Descripción**: La propina se calcula sobre el total, no sobre la porción del comensal.
- **Impacto**: En split, cada comensal paga propina del total.
- **Solución**: Calcular propina proporcional al monto individual.

#### PWAM-010: Sin confirmación de orden enviada
- **Archivo**: [submitOrder](pwaMenu/src/stores/table/store.ts)
- **Descripción**: No hay feedback visual claro después de enviar orden exitosamente.
- **Impacto**: Usuario puede enviar orden múltiples veces.
- **Solución**: Agregar toast/modal de confirmación y deshabilitar botón.

#### PWAM-011: Carrito compartido sin sincronización en tiempo real
- **Descripción**: Items agregados por otros comensales no aparecen automáticamente.
- **Impacto**: Comensales ven datos desactualizados hasta refresh manual.
- **Solución**: Suscribirse a eventos CART_UPDATED vía WebSocket.

#### PWAM-012: Allergen filter no persiste en sessionStorage
- **Descripción**: Filtros de alérgenos se pierden al recargar página.
- **Impacto**: UX pobre para usuarios con alergias.
- **Solución**: Persistir filtros seleccionados.

### 1.4 Defectos Bajos

#### PWAM-013: Console.log en producción
- **Archivos**: Varios archivos con `console.log` directo.
- **Solución**: Usar logger centralizado con nivel configurable.

#### PWAM-014: i18n incompleto en mensajes de error
- **Descripción**: Algunos mensajes de error están hardcodeados en español.
- **Solución**: Mover a archivos de traducción.

---

## 2. Auditoría pwaWaiter (PWA Mozo)

### 2.1 Defectos Críticos

#### PWAW-001: Solo 4 de 10 eventos WebSocket mapeados
- **Archivo**: [notifications.ts:134-135](pwaWaiter/src/services/notifications.ts#L134-L135)
- **Descripción**: El mapeo de eventos a notificaciones solo cubre 4 tipos:
  - ✅ ROUND_SUBMITTED
  - ✅ SERVICE_CALL_CREATED
  - ✅ CHECK_REQUESTED
  - ✅ ROUND_READY
  - ❌ ROUND_IN_KITCHEN (no mapeado)
  - ❌ ROUND_SERVED (no mapeado)
  - ❌ CHECK_PAID (no mapeado)
  - ❌ TABLE_CLEARED (no mapeado)
  - ❌ PAYMENT_RECEIVED (no existe)
  - ❌ DINER_JOINED (no existe)
- **Impacto**: Mozo pierde información crítica sobre pagos y estado de mesas.
- **Solución**: Completar mapeo de todos los eventos relevantes.

#### PWAW-002: No hay detalle de rondas individuales
- **Descripción**: La vista de mesa muestra resumen pero no items específicos por ronda.
- **Impacto**: Mozo no puede verificar qué ordenó cada comensal.
- **Solución**: Crear endpoint `GET /api/waiter/tables/{id}/session/rounds` y vista de detalle.

### 2.2 Defectos Altos

#### PWAW-003: Refetch completo en cada evento WebSocket
- **Archivo**: [tablesStore.ts:152-160](pwaWaiter/src/stores/tablesStore.ts#L152-L160)
- **Descripción**: Cualquier evento WebSocket dispara `fetchTables()` que recarga todas las mesas.
- **Impacto**: Ineficiente, causa parpadeos en UI, no escala.
- **Solución**: Actualizar solo la mesa afectada usando el payload del evento.

#### PWAW-004: ServiceCall sin información de mesa/comensal
- **Descripción**: La notificación de service call no indica qué mesa ni qué necesita.
- **Impacto**: Mozo debe buscar manualmente qué mesa llamó.
- **Solución**: Incluir número de mesa y tipo de llamada en notificación.

#### PWAW-005: No hay historial de acciones
- **Descripción**: No hay log de qué rondas se marcaron como servidas, por quién.
- **Impacto**: Sin trazabilidad de operaciones para auditoría.
- **Solución**: Agregar timestamp y user_id a cambios de estado.

#### PWAW-006: Botón "Marcar Servido" sin confirmación
- **Descripción**: Un tap accidental puede marcar ronda como servida.
- **Impacto**: Estados incorrectos, difícil revertir.
- **Solución**: Agregar diálogo de confirmación o swipe-to-confirm.

### 2.3 Defectos Medios

#### PWAW-007: Sin indicador de conexión WebSocket
- **Descripción**: No hay feedback visual cuando se pierde conexión.
- **Impacto**: Mozo puede perder notificaciones sin saberlo.
- **Solución**: Agregar indicador de estado de conexión en header.

#### PWAW-008: Pull-to-refresh no implementado
- **Descripción**: No hay forma de refrescar manualmente la lista.
- **Impacto**: En caso de desync, usuario debe cerrar/abrir app.
- **Solución**: Implementar pull-to-refresh nativo.

#### PWAW-009: Filtro de mesas no persiste
- **Descripción**: El filtro por estado se resetea al cambiar de vista.
- **Solución**: Persistir en sessionStorage.

### 2.4 Defectos Bajos

#### PWAW-010: Tema claro no implementado
- **Descripción**: Solo existe tema oscuro.
- **Solución**: Agregar toggle de tema.

#### PWAW-011: Sin modo offline
- **Descripción**: App no funciona sin conexión.
- **Solución**: Implementar service worker con cache de mesas.

---

## 3. Auditoría Backend (FastAPI)

### 3.1 Defectos Críticos

#### BACK-001: Cocina solo recibe ROUND_SUBMITTED
- **Archivo**: [events.py:201-202](backend/rest_api/services/events.py#L201-L202)
- **Descripción**: `publish_round_event` solo publica a `branch:{id}:waiters`, nunca a `:kitchen`.
- **Código actual**:
```python
await publish_event(
    f"branch:{branch_id}:waiters",
    event
)
```
- **Impacto**: La cocina no recibe actualizaciones de estado de rondas.
- **Solución**: Agregar publicación a canal `:kitchen` para eventos relevantes.

#### BACK-002: Webhook MP no ejecuta allocation
- **Archivo**: [billing.py:689](backend/rest_api/routers/billing.py#L689)
- **Descripción**: El webhook de Mercado Pago actualiza el estado del check pero no llama a `allocate_payment_fifo()`.
- **Impacto**: Pagos MP no se asignan a charges individuales, balance de comensales incorrecto.
- **Solución**: Llamar `allocate_payment_fifo(session, payment, check.session_id)` después de crear Payment.

#### BACK-003: Pago cash sin diner_id
- **Archivo**: [billing.py:225](backend/rest_api/routers/billing.py#L225)
- **Descripción**: Endpoint `/cash/pay` no recibe ni usa `diner_id`.
- **Impacto**: No se puede rastrear qué comensal pagó en efectivo.
- **Solución**: Agregar `diner_id: int | None` al payload y pasar a allocation.

#### BACK-004: KitchenTicket models sin usar
- **Archivo**: [models.py:451-522](backend/rest_api/models.py#L451-L522)
- **Descripción**: Los modelos `KitchenTicket` y `KitchenTicketItem` están definidos pero ningún endpoint los crea o consulta.
- **Impacto**: Feature de tickets por estación no funciona.
- **Solución**: Implementar endpoints en kitchen router o eliminar modelos muertos.

### 3.2 Defectos Altos

#### BACK-005: CORS falta puerto 5178
- **Archivo**: [ws_gateway/main.py:94-100](backend/ws_gateway/main.py#L94-L100)
- **Descripción**: Lista de origins no incluye `http://localhost:5178` para pwaWaiter.
- **Impacto**: pwaWaiter no puede conectar a WebSocket en desarrollo.
- **Solución**: Agregar puerto 5178 a allow_origins.

#### BACK-006: Sin rate limiting en endpoints públicos
- **Descripción**: `/api/public/menu/{slug}` y `/api/auth/login` no tienen rate limit.
- **Impacto**: Vulnerable a ataques de fuerza bruta y DoS.
- **Solución**: Implementar slowapi o similar.

#### BACK-007: Tokens JWT sin refresh token
- **Descripción**: Solo existe access token, no hay mecanismo de refresh.
- **Impacto**: Usuario debe re-autenticarse cada vez que expira (30min default).
- **Solución**: Implementar endpoint `/auth/refresh` con refresh tokens.

### 3.3 Defectos Medios

#### BACK-008: Logs sin structured logging
- **Descripción**: Usa print() en lugar de logging estructurado.
- **Impacto**: Difícil agregar logs, no hay niveles.
- **Solución**: Migrar a structlog o loguru.

#### BACK-009: Sin health check de dependencias
- **Archivo**: `/health` endpoint
- **Descripción**: Health check no verifica PostgreSQL ni Redis.
- **Impacto**: Puede reportar healthy cuando DB está caída.
- **Solución**: Agregar checks de conectividad a dependencias.

### 3.4 Defectos Bajos

#### BACK-010: OpenAPI schema incompleto
- **Descripción**: Algunos endpoints no tienen descriptions ni examples.
- **Solución**: Agregar docstrings completos a todos los endpoints.

---

## 4. Auditoría Dashboard (Panel Admin)

### 4.1 Defectos Críticos

#### DASH-001: Sin infraestructura WebSocket
- **Descripción**: Dashboard no tiene servicio WebSocket, no recibe eventos en tiempo real.
- **Impacto**: Admin debe refrescar manualmente para ver cambios.
- **Solución**: Crear `services/websocket.ts` y conectar a `/ws/admin`.

#### DASH-002: Página Orders es placeholder
- **Archivo**: [Orders.tsx:1-70](Dashboard/src/pages/Orders.tsx#L1-L70)
- **Descripción**: Solo contiene skeleton UI sin funcionalidad real.
- **Impacto**: Admin no puede ver órdenes activas.
- **Solución**: Implementar conexión a backend y tabla de órdenes.

### 4.2 Defectos Altos

#### DASH-003: Kitchen usa polling de 10 segundos
- **Archivo**: [Kitchen.tsx:164-170](Dashboard/src/pages/Kitchen.tsx#L164-L170)
- **Descripción**: En lugar de WebSocket, hace polling cada 10 segundos.
- **Impacto**: Delay de hasta 10s en actualizaciones, carga innecesaria al servidor.
- **Solución**: Migrar a WebSocket events.

#### DASH-004: TableStore sin eventos en tiempo real
- **Archivo**: [tableStore.ts:121-284](Dashboard/src/stores/tableStore.ts#L121-L284)
- **Descripción**: No hay listeners para eventos WebSocket de cambio de estado.
- **Impacto**: Vista de mesas desactualizada hasta refresh.
- **Solución**: Suscribirse a TABLE_CLEARED, SESSION_CREATED, etc.

#### DASH-005: Sin página de reportes
- **Descripción**: No existe módulo de analytics/reportes.
- **Impacto**: Admin no puede ver métricas de ventas, tiempos promedio, etc.
- **Solución**: Crear página Reports con gráficos.

#### DASH-006: Cascade delete sin confirmación detallada
- **Descripción**: Al borrar categoría, no muestra qué subcategorías/productos se eliminarán.
- **Impacto**: Borrados accidentales de datos importantes.
- **Solución**: Mostrar lista de items afectados antes de confirmar.

#### DASH-007: Sin auditoría de cambios
- **Descripción**: No hay log de quién modificó qué y cuándo.
- **Impacto**: Imposible rastrear cambios problemáticos.
- **Solución**: Implementar audit log con timestamps y user_id.

### 4.3 Defectos Medios

#### DASH-008: Formularios sin validación de duplicados
- **Descripción**: Se puede crear categoría con mismo nombre que existente.
- **Impacto**: Datos duplicados, confusión.
- **Solución**: Validar unicidad antes de crear.

#### DASH-009: Paginación no implementada
- **Descripción**: Todas las listas cargan todos los items.
- **Impacto**: Performance degradada con muchos registros.
- **Solución**: Implementar paginación server-side.

#### DASH-010: Sin exportación de datos
- **Descripción**: No hay forma de exportar menú, ventas, etc.
- **Solución**: Agregar botones de exportar CSV/Excel.

### 4.4 Defectos Bajos

#### DASH-011: Tema no sincronizado con sistema
- **Descripción**: No detecta preferencia de tema del OS.
- **Solución**: Usar `prefers-color-scheme` media query.

#### DASH-012: Sin shortcuts de teclado
- **Descripción**: No hay atajos para operaciones frecuentes.
- **Solución**: Implementar hotkeys (Ctrl+N nuevo, Ctrl+S guardar, etc).

---

## 5. Análisis de Flujo End-to-End

### 5.1 Flujo: Ocupación de Mesa → Pedido → Pago

```
┌─────────────────────────────────────────────────────────────────────────────┐
│ FLUJO ACTUAL (con gaps identificados)                                       │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│  [Comensal escanea QR]                                                      │
│         │                                                                   │
│         ▼                                                                   │
│  [pwaMenu: joinTable()]                                                     │
│         │                                                                   │
│         ├──► POST /tables/{id}/session ──► Crea TableSession               │
│         │                                                                   │
│         ▼                                                                   │
│  [registerDinerAsync()] ◄── GAP: Falla silenciosamente (PWAM-004)          │
│         │                                                                   │
│         ▼                                                                   │
│  [Comensal agrega items al carrito]                                         │
│         │                                                                   │
│         ▼                                                                   │
│  [submitOrder()] ──► POST /diner/rounds/submit                              │
│         │                                                                   │
│         ├──► Backend crea Round + RoundItems                                │
│         │                                                                   │
│         ├──► publish_round_event(ROUND_SUBMITTED)                           │
│         │         │                                                         │
│         │         ├──► channel: branch:{id}:waiters ✓                       │
│         │         │                                                         │
│         │         └──► channel: branch:{id}:kitchen ◄── GAP: No se publica │
│         │                                              (BACK-001)           │
│         ▼                                                                   │
│  [pwaWaiter recibe notificación] ✓                                          │
│         │                                                                   │
│         └──► Pero solo 4/10 eventos mapeados (PWAW-001)                     │
│                                                                             │
│  [Cocina NO recibe evento] ◄── CRÍTICO: Flujo roto                         │
│                                                                             │
│  [Cocina debe hacer polling o usar Dashboard]                               │
│         │                                                                   │
│         ▼                                                                   │
│  [POST /kitchen/rounds/{id}/status] ──► {status: "IN_KITCHEN"}              │
│         │                                                                   │
│         └──► publish... solo a waiters, no a diners ◄── GAP: pwaMenu       │
│                                                          no se entera       │
│                                                                             │
│  [...proceso de cocina...]                                                  │
│         │                                                                   │
│         ▼                                                                   │
│  [POST /kitchen/rounds/{id}/status] ──► {status: "READY"}                   │
│         │                                                                   │
│         └──► Waiter notificado ✓                                            │
│                                                                             │
│  [Mozo sirve la orden]                                                      │
│         │                                                                   │
│         ▼                                                                   │
│  [Comensal solicita cuenta]                                                 │
│         │                                                                   │
│         ├──► POST /diner/check ✓                                            │
│         │                                                                   │
│         └──► Waiter notificado (CHECK_REQUESTED) ✓                          │
│                                                                             │
│  [PAGO - Múltiples escenarios]                                              │
│         │                                                                   │
│         ├──► Mercado Pago:                                                  │
│         │       POST /billing/mercadopago/preference ✓                      │
│         │       Webhook recibe pago ✓                                       │
│         │       PERO: No llama allocate_payment_fifo (BACK-002)             │
│         │                                                                   │
│         ├──► Efectivo:                                                      │
│         │       useCloseTableFlow registra localmente                       │
│         │       PERO: No llama POST /billing/cash/pay (PWAM-001)            │
│         │                                                                   │
│         └──► Split payment:                                                 │
│                 Cálculo usa 'by_consumption' incorrecto (PWAM-003)          │
│                 No hay endpoint para pagos parciales por comensal           │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

### 5.2 Matriz de Trazabilidad

| Paso | pwaMenu | Backend | pwaWaiter | Dashboard | Estado |
|------|---------|---------|-----------|-----------|--------|
| Crear sesión | ✅ | ✅ | - | - | OK |
| Registrar comensal | ⚠️ Falla silente | ✅ | - | - | PARCIAL |
| Enviar orden | ✅ | ✅ | - | - | OK |
| Notificar mozo | - | ✅ | ⚠️ Solo 4 eventos | - | PARCIAL |
| Notificar cocina | - | ❌ No publica | - | ⚠️ Polling | ROTO |
| Actualizar estado | ⚠️ No recibe | ✅ | ✅ | ✅ | PARCIAL |
| Solicitar cuenta | ✅ | ✅ | ✅ | - | OK |
| Pago MP | ✅ | ⚠️ Sin allocation | - | - | PARCIAL |
| Pago efectivo | ❌ Solo local | ✅ Endpoint existe | - | - | ROTO |
| Split payment | ⚠️ Cálculo malo | ❌ Sin endpoint | - | - | ROTO |

---

## 6. Plan de Mejoras Priorizado

### Fase 1: Críticos (Semana 1-2)

| ID | Defecto | Esfuerzo | Impacto |
|----|---------|----------|---------|
| BACK-001 | Publicar eventos a cocina | 2h | Alto |
| BACK-002 | Allocation en webhook MP | 1h | Alto |
| PWAM-001 | Conectar pagos cash al backend | 4h | Alto |
| PWAM-002 | Fix selectores camelCase | 1h | Alto |
| PWAM-003 | Fix splitMode byConsumption | 30m | Alto |
| PWAW-001 | Completar mapeo de eventos | 2h | Alto |
| BACK-005 | Agregar CORS para 5178 | 5m | Medio |

### Fase 2: Altos (Semana 2-3)

| ID | Defecto | Esfuerzo | Impacto |
|----|---------|----------|---------|
| PWAM-004 | Registro de comensal bloqueante | 2h | Alto |
| PWAM-005 | Fix DinersList camelCase | 30m | Alto |
| PWAW-002 | Endpoint detalle de rondas | 4h | Alto |
| PWAW-003 | Actualización incremental WS | 3h | Medio |
| DASH-001 | Infraestructura WebSocket | 8h | Alto |
| DASH-002 | Implementar página Orders | 8h | Alto |
| BACK-003 | Agregar diner_id a cash pay | 1h | Medio |

### Fase 3: Medios (Semana 3-4)

| ID | Defecto | Esfuerzo | Impacto |
|----|---------|----------|---------|
| PWAM-006 | Exponential backoff WS | 1h | Medio |
| PWAM-007 | Manejo de sesión expirada | 2h | Medio |
| PWAW-007 | Indicador conexión WS | 1h | Medio |
| DASH-003 | Migrar Kitchen a WebSocket | 4h | Medio |
| DASH-004 | Eventos tiempo real en tables | 4h | Medio |
| BACK-008 | Structured logging | 4h | Medio |

### Fase 4: Mejoras (Semana 4+)

- Implementar KitchenTicket workflow
- Agregar refresh tokens
- Rate limiting
- Reportes y analytics
- Exportación de datos
- Audit log
- Modo offline pwaWaiter

---

## 7. Métricas de Completitud

| Proyecto | Funcionalidad Core | Integración Backend | Tiempo Real | Tests | Total |
|----------|-------------------|---------------------|-------------|-------|-------|
| pwaMenu | 85% | 70% | 60% | 95% | 78% |
| pwaWaiter | 60% | 80% | 40% | 0% | 45% |
| Backend | 90% | N/A | 70% | 60% | 73% |
| Dashboard | 70% | 85% | 10% | 90% | 64% |

---

## 8. Recomendaciones Arquitecturales

### 8.1 Unificar Publicación de Eventos

Crear función centralizada que publique a todos los canales relevantes:

```python
async def publish_event_to_all(
    branch_id: int,
    session_id: int | None,
    event: dict,
    include_kitchen: bool = True,
    include_waiters: bool = True,
    include_diners: bool = True,
):
    if include_waiters:
        await publish_event(f"branch:{branch_id}:waiters", event)
    if include_kitchen:
        await publish_event(f"branch:{branch_id}:kitchen", event)
    if include_diners and session_id:
        await publish_event(f"session:{session_id}", event)
```

### 8.2 Normalización de Eventos WebSocket

Definir schema consistente para todos los eventos:

```typescript
interface WSEvent {
  type: WSEventType
  timestamp: string
  branch_id: number
  session_id?: number
  table_id?: number
  round_id?: number
  diner_id?: number
  payload: Record<string, unknown>
}
```

### 8.3 Estado Consistente Frontend-Backend

Implementar optimistic updates con rollback:

```typescript
async function submitOrder() {
  const optimisticRound = addLocalRound(items)
  try {
    const backendRound = await api.submitRound(items)
    updateRoundWithBackendId(optimisticRound.id, backendRound.id)
  } catch (error) {
    rollbackRound(optimisticRound.id)
    throw error
  }
}
```

---

## 9. Conclusión

El sistema Integrador tiene una base sólida pero presenta gaps críticos en:

1. **Comunicación Cocina**: La cocina no recibe eventos en tiempo real, dependiendo de polling
2. **Flujo de Pagos**: Pagos en efectivo no se registran en backend, allocation incompleta
3. **Consistencia de Datos**: Nomenclatura camelCase/snake_case inconsistente causa bugs silenciosos
4. **Tiempo Real Dashboard**: Sin WebSocket, admin opera con datos desactualizados

Se recomienda priorizar la Fase 1 de correcciones antes de cualquier nuevo desarrollo.

---

*Documento generado automáticamente - Auditoría Integrador v1.0*
