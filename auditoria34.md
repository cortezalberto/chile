# Auditoría de Trazas de Ejecución - Sistema Integrador

**Fecha:** Enero 2026
**Auditor:** QA Senior
**Versión:** 1.0

---

## Resumen Ejecutivo

Esta auditoría valida la integridad del sistema mediante trazas de ejecución end-to-end, desde los frontends (Dashboard, pwaMenu, pwaWaiter) hasta la persistencia en base de datos PostgreSQL, incluyendo las notificaciones en tiempo real vía WebSocket/Redis.

**Resultado General:** ✅ **APROBADO**

| Componente | Estado | Observaciones |
|------------|--------|---------------|
| Dashboard → Backend → DB | ✅ PASS | CRUD completo con soft delete |
| pwaMenu → Backend → DB | ✅ PASS | Pedidos y rondas funcionan correctamente |
| WebSocket Notifications | ✅ PASS | 4 canales funcionando (waiters, kitchen, admin, session) |
| Flujo de Pagos | ✅ PASS | Mercado Pago integrado con webhook |

---

## 1. Traza: Dashboard → Backend → DB (CRUD Entities)

### 1.1 Flujo de Autenticación

```
Dashboard                          Backend                           DB
─────────────────────────────────────────────────────────────────────────
1. Login Form Submit
   │
   ├──POST /api/auth/login────────►authAPI.login()
   │  {email, password}            │
   │                               ├──►SELECT * FROM app_user
   │                               │   WHERE email = ? AND is_active
   │                               │
   │                               ├──►bcrypt.verify(password)
   │                               │
   │◄─{access_token, user}─────────┤
   │                               │
2. Store token in authStore        │
   │                               │
3. Fetch user branches             │
   ├──GET /api/auth/me────────────►├──►JWT decode + validate
   │  Authorization: Bearer JWT    │
   │                               ├──►SELECT branch_ids FROM
   │◄─{user, branch_ids, roles}────┤   user_branch_role
```

**Archivos involucrados:**
- Frontend: [Dashboard/src/services/api.ts](Dashboard/src/services/api.ts) líneas 88-105
- Backend: [backend/rest_api/routers/auth.py](backend/rest_api/routers/auth.py)
- Modelos: `User`, `UserBranchRole`

**Validaciones:**
- ✅ JWT firmado con clave secreta configurada en `.env`
- ✅ Contraseña hasheada con bcrypt
- ✅ Roles validados por branch

---

### 1.2 Flujo CRUD de Productos (Ejemplo Representativo)

```
Dashboard                          Backend                           DB
─────────────────────────────────────────────────────────────────────────
1. Products.tsx monta
   │
   ├──useEffect: fetchProducts()
   │  │
   │  └──GET /api/admin/products──►productAPI.list()
   │     Authorization: Bearer JWT  │
   │                               ├──►require_roles(["ADMIN","MANAGER"])
   │                               │
   │                               ├──►SELECT p.*, bp.* FROM product p
   │                               │   LEFT JOIN branch_product bp
   │                               │   WHERE p.tenant_id = ?
   │                               │   AND p.is_active = true
   │                               │
   │◄─[{id, name, branch_prices}]──┤
   │                               │
2. User clicks "Nuevo Producto"    │
   │                               │
3. Modal form submit               │
   ├──POST /api/admin/products────►productAPI.create()
   │  {name, category_id,          │
   │   branch_prices: [...]}       ├──►Pydantic validation
   │                               │
   │                               ├──►INSERT INTO product
   │                               │   VALUES (tenant_id, name, ...)
   │                               │
   │                               ├──►INSERT INTO branch_product
   │                               │   VALUES (branch_id, price_cents)
   │                               │   FOR EACH branch_price
   │                               │
   │                               ├──►db.commit()
   │                               │
   │◄─{id: 123, name: "Pizza"}─────┤
   │                               │
4. Store updates local state       │
   productStore.add(newProduct)    │
   │                               │
5. WebSocket notification          │
   │◄─ENTITY_CREATED──────────────◄├──►redis.publish("branch:{id}:admin")
```

**Archivos involucrados:**
- Frontend: [Dashboard/src/pages/Products.tsx](Dashboard/src/pages/Products.tsx)
- Store: [Dashboard/src/stores/productStore.ts](Dashboard/src/stores/productStore.ts)
- API: [Dashboard/src/services/api.ts](Dashboard/src/services/api.ts) líneas 490-520
- Backend: [backend/rest_api/routers/admin.py](backend/rest_api/routers/admin.py)
- Modelos: `Product`, `BranchProduct`, `ProductAllergen`

**Validaciones:**
- ✅ Validación Pydantic de campos requeridos
- ✅ Tenant isolation (tenant_id del JWT)
- ✅ Soft delete con `is_active` flag
- ✅ Audit trail (created_by_id, created_by_email)

---

### 1.3 Flujo Soft Delete con Cascade Preview

```
Dashboard                          Backend                           DB
─────────────────────────────────────────────────────────────────────────
1. User clicks Delete on Category
   │
   ├──GET /api/admin/categories───►Fetch cascade preview
   │  /{id}/cascade-preview        │
   │                               ├──►SELECT * FROM subcategory
   │                               │   WHERE category_id = ?
   │                               │
   │                               ├──►SELECT * FROM product
   │                               │   WHERE category_id = ?
   │                               │
   │◄─{subcategories: [...],       │
   │   products: [...]}────────────┤
   │                               │
2. Show CascadePreviewList modal   │
   │                               │
3. User confirms delete            │
   ├──DELETE /api/admin/categories►
   │  /{id}                        │
   │                               ├──►require_roles(["ADMIN"])
   │                               │
   │                               ├──►soft_delete(category)
   │                               │   UPDATE category SET
   │                               │   is_active = false,
   │                               │   deleted_at = NOW(),
   │                               │   deleted_by_id = ?,
   │                               │   deleted_by_email = ?
   │                               │
   │                               ├──►CASCADE soft_delete children
   │                               │
   │◄─{success: true}──────────────┤
   │                               │
4. WebSocket: CASCADE_DELETE       │
   │◄─{entity_type, affected}─────◄├──►redis.publish("branch:{id}:admin")
```

**Validaciones:**
- ✅ Solo ADMIN puede eliminar
- ✅ Soft delete preserva datos (no DELETE físico)
- ✅ Cascade preview antes de confirmar
- ✅ WebSocket notifica a otros Dashboards

---

## 2. Traza: pwaMenu → Backend → DB (Pedidos y Rondas)

### 2.1 Flujo de Escaneo QR y Creación de Sesión

```
pwaMenu                            Backend                           DB
─────────────────────────────────────────────────────────────────────────
1. Diner scans QR code
   URL: /table/5/join
   │
   ├──POST /api/tables/5/session──►create_or_get_session()
   │  (no auth required)           │
   │                               ├──►SELECT * FROM restaurant_table
   │                               │   WHERE id = 5 AND is_active
   │                               │   FOR UPDATE  ◄── Race condition fix
   │                               │
   │                               ├──►Check existing session
   │                               │   SELECT * FROM table_session
   │                               │   WHERE table_id = 5
   │                               │   AND status IN ('OPEN','PAYING')
   │                               │
   │                               ├──►IF no session:
   │                               │   INSERT INTO table_session
   │                               │   (tenant_id, branch_id, table_id,
   │                               │    status='OPEN')
   │                               │
   │                               ├──►UPDATE restaurant_table
   │                               │   SET status = 'ACTIVE'
   │                               │
   │                               ├──►sign_table_token(JWT)
   │                               │
   │◄─{session_id, table_token}────┤
   │                               │
2. Store token in sessionStore     │
   setTableToken(token)            │
   │                               │
3. WebSocket: TABLE_SESSION_STARTED│
   │                               ├──►redis.publish("branch:{id}:waiters")
   │                               ├──►redis.publish("branch:{id}:admin")
```

**Archivos involucrados:**
- Frontend: [pwaMenu/src/services/api.ts](pwaMenu/src/services/api.ts) líneas 446-457
- Backend: [backend/rest_api/routers/tables.py](backend/rest_api/routers/tables.py) líneas 152-269
- Modelo: `Table`, `TableSession`

**Validaciones:**
- ✅ `SELECT FOR UPDATE` previene race condition
- ✅ Rate limiting (30/minute)
- ✅ Table token es JWT firmado
- ✅ Evento WebSocket notifica a mozos

---

### 2.2 Flujo de Registro de Diner

```
pwaMenu                            Backend                           DB
─────────────────────────────────────────────────────────────────────────
1. Diner enters name/color
   │
   ├──POST /api/diner/register────►register_diner()
   │  X-Table-Token: JWT           │
   │  {name, color, local_id}      ├──►verify_table_token(JWT)
   │                               │   → extracts session_id
   │                               │
   │                               ├──►SELECT * FROM diner
   │                               │   WHERE session_id = ?
   │                               │   AND local_id = ?
   │                               │   ◄── Idempotency check
   │                               │
   │                               ├──►IF exists: return existing
   │                               │   ELSE:
   │                               │   INSERT INTO diner
   │                               │   (session_id, name, color, local_id)
   │                               │
   │◄─{id: 42, name, color}────────┤
   │                               │
2. Store backendDinerId in         │
   tableStore                      │
```

**Archivos involucrados:**
- Frontend: [pwaMenu/src/services/api.ts](pwaMenu/src/services/api.ts) líneas 489-496
- Backend: [backend/rest_api/routers/diner.py](backend/rest_api/routers/diner.py)
- Modelo: `Diner`

**Validaciones:**
- ✅ Idempotencia vía `local_id` (UUID del frontend)
- ✅ Token valida session_id
- ✅ Re-registro retorna diner existente

---

### 2.3 Flujo de Envío de Ronda (Pedido)

```
pwaMenu                            Backend                           DB
─────────────────────────────────────────────────────────────────────────
1. Diners add items to shared cart │
   │                               │
2. Submit round                    │
   ├──POST /api/diner/rounds/submit►submit_round()
   │  X-Table-Token: JWT           │
   │  X-Idempotency-Key: uuid      ├──►verify_table_token(JWT)
   │  {items: [{product_id,        │
   │    qty, diner_id, notes}]}    ├──►Check idempotency key
   │                               │   SELECT * FROM round
   │                               │   WHERE idempotency_key = ?
   │                               │
   │                               ├──►SELECT * FROM table_session
   │                               │   WHERE id = ?
   │                               │   FOR UPDATE  ◄── Lock session
   │                               │
   │                               ├──►Get next round_number
   │                               │   SELECT MAX(round_number)+1
   │                               │   FROM round WHERE session_id = ?
   │                               │
   │                               ├──►INSERT INTO round
   │                               │   (session_id, round_number,
   │                               │    status='SUBMITTED',
   │                               │    idempotency_key)
   │                               │
   │                               ├──►FOR EACH item:
   │                               │   SELECT price_cents FROM
   │                               │   branch_product WHERE product_id=?
   │                               │
   │                               │   INSERT INTO round_item
   │                               │   (round_id, product_id, qty,
   │                               │    unit_price_cents, diner_id)
   │                               │
   │                               ├──►db.commit()
   │                               │
   │◄─{round_id, round_number}─────┤
   │                               │
3. WebSocket: ROUND_SUBMITTED      │
   │                               ├──►publish_round_event(redis)
   │                               │   → branch:{id}:waiters
   │                               │   → branch:{id}:kitchen
   │                               │   → branch:{id}:admin
   │                               │   → session:{id}
```

**Archivos involucrados:**
- Frontend: [pwaMenu/src/services/api.ts](pwaMenu/src/services/api.ts) líneas 510-517
- Backend: [backend/rest_api/routers/diner.py](backend/rest_api/routers/diner.py)
- Modelo: `Round`, `RoundItem`

**Validaciones:**
- ✅ Idempotencia vía `X-Idempotency-Key`
- ✅ `SELECT FOR UPDATE` previene race condition en session
- ✅ Precio capturado al momento del pedido (unit_price_cents)
- ✅ Eventos publicados a 4 canales WebSocket

---

## 3. Traza: WebSocket Notifications (Mozo/Cocina)

### 3.1 Arquitectura de Canales Redis

```
┌─────────────────────────────────────────────────────────────────────┐
│                      Redis Pub/Sub Channels                         │
├─────────────────────────────────────────────────────────────────────┤
│                                                                     │
│  branch:{id}:waiters  ──────► pwaWaiter (mozos de la sucursal)     │
│                               - ROUND_SUBMITTED                     │
│                               - ROUND_READY                         │
│                               - SERVICE_CALL_CREATED                │
│                               - CHECK_REQUESTED                     │
│                                                                     │
│  branch:{id}:kitchen  ──────► Kitchen displays                      │
│                               - ROUND_SUBMITTED                     │
│                               - ROUND_IN_KITCHEN                    │
│                                                                     │
│  branch:{id}:admin    ──────► Dashboard                             │
│                               - All events                          │
│                               - ENTITY_CREATED/UPDATED/DELETED      │
│                                                                     │
│  session:{id}         ──────► pwaMenu (diners de esa mesa)         │
│                               - ROUND_IN_KITCHEN                    │
│                               - ROUND_READY                         │
│                               - ROUND_SERVED                        │
│                               - CHECK_PAID                          │
│                                                                     │
│  sector:{id}:waiters  ──────► pwaWaiter (mozos del sector)         │
│                               - Events filtered by sector           │
│                                                                     │
└─────────────────────────────────────────────────────────────────────┘
```

### 3.2 Flujo de Notificación al Mozo (Ronda Lista)

```
Kitchen                            Backend                         pwaWaiter
─────────────────────────────────────────────────────────────────────────────
1. Kitchen marks round READY
   │
   ├──POST /api/kitchen/rounds/{id}►update_round_status()
   │  /status                      │
   │  {status: "READY"}            ├──►Validate transition
   │                               │   IN_KITCHEN → READY ✓
   │                               │
   │                               ├──►UPDATE round SET status='READY'
   │                               │
   │                               ├──►db.commit()
   │                               │
   │                               ├──►publish_round_event(
   │                               │     ROUND_READY,
   │                               │     branch_id, table_id,
   │                               │     round_id, round_number)
   │                               │
   │                               │   redis.publish("branch:{id}:waiters")
   │                               │   redis.publish("branch:{id}:kitchen")
   │                               │   redis.publish("branch:{id}:admin")
   │                               │   redis.publish("session:{id}")
   │                               │                               │
   │◄─{id, status: "READY"}────────┤                               │
                                                                   │
                                   ws_gateway/main.py              │
                                   │                               │
                                   ├──►Redis subscriber receives   │
                                   │   message on channel          │
                                   │                               │
                                   ├──►FOR EACH waiter connection: │
                                   │   websocket.send_json(event) ─┼──────►
                                   │                               │
                                                                   │
                                                                   │
                                                        3. WS Event received
                                                           │
                                                           ├──►tablesStore.handleEvent()
                                                           │   Update table status
                                                           │
                                                           ├──►Play notification sound
                                                           │
                                                           └──►Show toast "Ronda #2
                                                               lista para Mesa T-05"
```

**Archivos involucrados:**
- Backend Kitchen: [backend/rest_api/routers/kitchen.py](backend/rest_api/routers/kitchen.py) líneas 109-253
- Events: [backend/shared/events.py](backend/shared/events.py)
- WS Gateway: [backend/ws_gateway/main.py](backend/ws_gateway/main.py)
- Frontend: [pwaWaiter/src/services/websocket.ts](pwaWaiter/src/services/websocket.ts)

**Validaciones:**
- ✅ Transiciones de estado validadas (SUBMITTED→IN_KITCHEN→READY→SERVED)
- ✅ Eventos publicados a múltiples canales
- ✅ WS Gateway filtra por branch_id del mozo
- ✅ Heartbeat cada 30s mantiene conexión viva

---

### 3.3 Flujo de Service Call (Llamar Mozo)

```
pwaMenu                            Backend                         pwaWaiter
─────────────────────────────────────────────────────────────────────────────
1. Diner presses "Llamar Mozo"
   │
   ├──POST /api/diner/service-call►create_service_call()
   │  X-Table-Token: JWT           │
   │  {type: "WAITER_CALL"}        ├──►verify_table_token()
   │                               │
   │                               ├──►INSERT INTO service_call
   │                               │   (session_id, type='WAITER_CALL',
   │                               │    status='OPEN')
   │                               │
   │                               ├──►publish_service_call_event(
   │                               │     SERVICE_CALL_CREATED)
   │                               │   → branch:{id}:waiters
   │                               │   → branch:{id}:admin
   │                               │   → session:{id}
   │                               │                               │
   │◄─{id, type, status}───────────┤                               │
   │                                                               │
2. Show "Mozo notificado"                                          │
                                                                   │
                                   ws_gateway/main.py              │
                                   │                               │
                                   ├──►Send to waiters in sector  ─┼──────►
                                   │   (filtered by sector_id)     │
                                                                   │
                                                        3. WS Event received
                                                           │
                                                           ├──►Show urgent banner
                                                           │   "Mesa T-05 llama"
                                                           │
                                                           └──►Play alert sound
                                                                   │
4. Waiter acknowledges             │                               │
   │◄──────────────────────────────┼───POST /api/waiter/service────┤
   │                               │   -calls/{id}/acknowledge     │
   │                               │                               │
   │                               ├──►UPDATE service_call         │
   │                               │   SET status='ACKED',         │
   │                               │   acked_by_user_id=?          │
   │                               │                               │
   │  SERVICE_CALL_ACKED event     │                               │
   │◄──────────────────────────────┼───publish to session:{id}─────┤
   │                               │                               │
5. pwaMenu shows                   │                               │
   "Mozo en camino"                │                               │
```

**Archivos involucrados:**
- pwaMenu: [pwaMenu/src/services/api.ts](pwaMenu/src/services/api.ts) líneas 549-556
- Backend: [backend/rest_api/routers/diner.py](backend/rest_api/routers/diner.py)
- Waiter: [backend/rest_api/routers/waiter.py](backend/rest_api/routers/waiter.py) líneas 119-212
- Modelo: `ServiceCall`

**Validaciones:**
- ✅ Eventos filtrados por sector del mozo
- ✅ Acknowledge previene múltiples mozos respondiendo
- ✅ Feedback visual en pwaMenu cuando mozo acepta

---

## 4. Traza: Flujo de Pagos (Mercado Pago)

### 4.1 Flujo Completo de Pago

```
pwaMenu                            Backend                           MP/DB
─────────────────────────────────────────────────────────────────────────────
1. Diner requests bill
   │
   ├──POST /api/billing/check/─────►request_check()
   │  request                      │
   │  X-Table-Token: JWT           ├──►SELECT * FROM check
   │                               │   WHERE session_id = ?
   │                               │   ◄── Idempotency: return existing
   │                               │
   │                               ├──►IF no check:
   │                               │   - Calculate total from rounds
   │                               │   - INSERT INTO check
   │                               │   - create_charges_for_check()
   │                               │     → INSERT INTO charge
   │                               │     FOR EACH round_item
   │                               │
   │                               ├──►UPDATE table_session
   │                               │   SET status = 'PAYING'
   │                               │
   │                               ├──►UPDATE restaurant_table
   │                               │   SET status = 'PAYING'
   │                               │
   │                               ├──►publish_check_event(CHECK_REQUESTED)
   │                               │
   │◄─{check_id, total_cents}──────┤
   │                               │
2. User selects Mercado Pago       │
   │                               │
   ├──POST /api/billing/mercadopago►create_mp_preference()
   │  /preference                  │
   │  {check_id}                   ├──►Validate check belongs to session
   │                               │
   │                               ├──►Build MP preference
   │                               │   - title, quantity, unit_price
   │                               │   - back_urls (success, failure)
   │                               │   - webhook notification_url
   │                               │
   │                               ├──►POST mercadopago.com/checkout──────►
   │                               │   /preferences                       │
   │                               │                                      │
   │                               │◄─{id, init_point}────────────────────┤
   │                               │
   │◄─{preference_id, init_point}──┤
   │                               │
3. Redirect to MP checkout         │
   window.location = init_point ──────────────────────────────────────────►
                                                                          │
                                   │◄──User completes payment─────────────┤
                                   │                                      │
4. MP Webhook notification         │                                      │
   │                               │◄─POST /api/billing/mercadopago/──────┤
   │                               │  webhook                             │
   │                               │  {type: "payment", data: {id}}       │
   │                               │                                      │
   │                               ├──►GET mercadopago.com/v1/payments/{id}
   │                               │   → Verify payment status            │
   │                               │                                      │
   │                               ├──►IF status == "approved":           │
   │                               │   INSERT INTO payment                │
   │                               │   (check_id, amount_cents,           │
   │                               │    method='MERCADOPAGO',             │
   │                               │    external_id=mp_payment_id)        │
   │                               │                                      │
   │                               ├──►allocate_payment_fifo()            │
   │                               │   UPDATE charge SET                  │
   │                               │   status='PAID' (oldest first)       │
   │                               │                                      │
   │                               ├──►UPDATE check                       │
   │                               │   SET paid_cents += amount           │
   │                               │   IF paid_cents >= total:            │
   │                               │     status = 'PAID'                  │
   │                               │                                      │
   │                               ├──►publish_check_event(CHECK_PAID)    │
   │                               │   → branch:{id}:waiters              │
   │                               │   → branch:{id}:admin                │
   │                               │   → session:{id}                     │
   │                               │                                      │
5. pwaMenu receives CHECK_PAID     │                                      │
   via WebSocket                   │                                      │
   │◄─────────────────────────────┤                                      │
   │                               │                                      │
   Show "Pago confirmado"          │                                      │
```

**Archivos involucrados:**
- pwaMenu: [pwaMenu/src/services/api.ts](pwaMenu/src/services/api.ts) líneas 563-587
- Backend: [backend/rest_api/routers/billing.py](backend/rest_api/routers/billing.py)
- Allocation: [backend/rest_api/services/allocation.py](backend/rest_api/services/allocation.py)
- Modelos: `Check`, `Payment`, `Charge`, `Allocation`

**Validaciones:**
- ✅ Idempotencia en request_check (no crea checks duplicados)
- ✅ Webhook verifica pago con API de MP antes de confirmar
- ✅ FIFO allocation para pagos parciales
- ✅ Evento CHECK_PAID notifica a todos los canales

---

## 5. Resumen de Integridad del Sistema

### 5.1 Patrones de Seguridad Verificados

| Patrón | Implementación | Estado |
|--------|----------------|--------|
| Race Condition Prevention | `SELECT FOR UPDATE` en sessions | ✅ |
| Idempotency | `local_id`, `X-Idempotency-Key`, check existente | ✅ |
| SSRF Protection | Validación de hosts/ports permitidos | ✅ |
| SQL Injection | SQLAlchemy ORM con parámetros | ✅ |
| JWT Validation | Firma verificada, expiración controlada | ✅ |
| Tenant Isolation | `tenant_id` extraído de JWT en todas las queries | ✅ |
| Soft Delete | `is_active` flag + audit trail | ✅ |
| Rate Limiting | slowapi en endpoints públicos | ✅ |

### 5.2 Patrones de Persistencia Verificados

| Patrón | Implementación | Estado |
|--------|----------------|--------|
| Transacciones | `db.commit()` con rollback en error | ✅ |
| Eager Loading | `selectinload`, `joinedload` para evitar N+1 | ✅ |
| Índices | Status columns, FKs, composite indexes | ✅ |
| Audit Trail | `AuditMixin` con created/updated/deleted_by | ✅ |
| Connection Pool | `pool_pre_ping`, `pool_recycle=1800` | ✅ |

### 5.3 Patrones de Real-time Verificados

| Patrón | Implementación | Estado |
|--------|----------------|--------|
| Redis Pub/Sub | 4 canales (waiters, kitchen, admin, session) | ✅ |
| WebSocket Heartbeat | Ping/pong cada 30s, cleanup de stale | ✅ |
| Event Schema | Dataclass con validación de tipos | ✅ |
| Reconnection | Exponential backoff con jitter | ✅ |
| Connection Pool | Redis pooled (sin close manual) | ✅ |

---

## 6. Conclusiones

### 6.1 Fortalezas del Sistema

1. **Arquitectura robusta**: Separación clara entre REST API (8000) y WS Gateway (8001)
2. **Idempotencia completa**: Todas las operaciones críticas son idempotentes
3. **Real-time confiable**: 4 canales WebSocket cubren todos los casos de uso
4. **Audit trail completo**: Soft delete con tracking de usuario/timestamp
5. **FIFO allocation**: Pagos parciales se asignan correctamente

### 6.2 Recomendaciones Implementadas

| ID | Recomendación | Estado | Archivos |
|----|---------------|--------|----------|
| REC-01 | Circuit breaker para Mercado Pago | ✅ IMPLEMENTADO | [circuit_breaker.py](backend/rest_api/services/circuit_breaker.py) |
| REC-02 | Retry queue para webhooks fallidos | ✅ IMPLEMENTADO | [webhook_retry.py](backend/rest_api/services/webhook_retry.py) |
| REC-03 | Batch inserts para round_items | ✅ IMPLEMENTADO | [diner.py](backend/rest_api/routers/diner.py) |

#### REC-01: Circuit Breaker para Mercado Pago

**Implementación:** Patrón circuit breaker con 3 estados (CLOSED, OPEN, HALF-OPEN)

```python
# Uso en billing.py
from rest_api.services.circuit_breaker import mercadopago_breaker, CircuitBreakerError

async with mercadopago_breaker.call():
    response = await client.post("https://api.mercadopago.com/...")

# Si el circuito está abierto, lanza CircuitBreakerError con retry_after
```

**Configuración:**
- `failure_threshold`: 5 fallos antes de abrir
- `success_threshold`: 2 éxitos en half-open para cerrar
- `timeout_seconds`: 30s antes de intentar half-open

**Monitoreo:** Endpoint `/api/health/detailed` incluye estadísticas de circuit breakers.

#### REC-02: Retry Queue para Webhooks Fallidos

**Implementación:** Cola Redis con exponential backoff

```python
# Cuando falla un webhook, se encola para retry
await webhook_retry_queue.enqueue(
    webhook_type="mercadopago",
    payload=body,
    error="Connection timeout",
)

# Background task procesa retries cada 30s
asyncio.create_task(start_retry_processor(interval_seconds=30.0))
```

**Características:**
- Exponential backoff: 10s, 20s, 40s, 80s, 160s (máx 1 hora)
- Máximo 5 intentos antes de dead letter queue
- Persistencia en Redis (sobrevive reinicios)

**Monitoreo:** Endpoint `/api/health/detailed` incluye stats de retry queue.

#### REC-03: Batch Inserts para Round Items

**Implementación:** Consulta única para validar productos + batch add

```python
# ANTES: N queries (1 por item)
for item in body.items:
    result = db.execute(select(Product, BranchProduct)...).first()
    db.add(RoundItem(...))

# DESPUÉS: 1 query + batch add
products_query = db.execute(
    select(Product, BranchProduct)
    .where(Product.id.in_(product_ids), ...)
).all()

product_lookup = {p.id: (p, bp) for p, bp in products_query}
round_items_to_add = [RoundItem(...) for item in body.items]
db.add_all(round_items_to_add)
```

**Mejora de rendimiento:** Reduce de N+1 queries a 1 query para cualquier número de items.

### 6.3 Veredicto Final

El sistema **APRUEBA** la auditoría de trazas de ejecución. Todas las trazas verificadas demuestran:

- ✅ Integridad de datos desde frontend hasta DB
- ✅ Correcta propagación de eventos en tiempo real
- ✅ Manejo adecuado de race conditions
- ✅ Flujo de pagos completo y verificable

**Firma Digital:** QA Senior - Enero 2026

---

## 7. Archivos Creados/Modificados

### 7.1 Nuevos Archivos

| Archivo | Descripción |
|---------|-------------|
| [circuit_breaker.py](backend/rest_api/services/circuit_breaker.py) | Circuit breaker genérico con estados CLOSED/OPEN/HALF-OPEN |
| [webhook_retry.py](backend/rest_api/services/webhook_retry.py) | Cola de retry con exponential backoff en Redis |
| [mp_webhook_handler.py](backend/rest_api/services/mp_webhook_handler.py) | Handler de retry para webhooks de Mercado Pago |

### 7.2 Archivos Modificados

| Archivo | Cambios |
|---------|---------|
| [billing.py](backend/rest_api/routers/billing.py) | Integración de circuit breaker y retry queue en MP endpoints |
| [diner.py](backend/rest_api/routers/diner.py) | Batch inserts para round items |
| [main.py](backend/rest_api/main.py) | Registro de handlers y task de retry; stats en health check |

---

## Anexo: Comandos de Verificación

```bash
# Verificar conexión a PostgreSQL
docker exec integrador_db psql -U postgres -d menu_ops -c "SELECT COUNT(*) FROM round;"

# Verificar Redis pub/sub
redis-cli -p 6380 MONITOR

# Verificar endpoints activos
curl http://localhost:8000/openapi.json | jq '.paths | keys | length'

# Test de health
curl http://localhost:8000/api/health/detailed

# Logs del WS Gateway
docker logs integrador_ws_gateway --tail 100

# Query de sesiones activas
docker exec integrador_db psql -U postgres -d menu_ops -c "
  SELECT ts.id, t.code, ts.status, COUNT(r.id) as rounds
  FROM table_session ts
  JOIN restaurant_table t ON ts.table_id = t.id
  LEFT JOIN round r ON r.table_session_id = ts.id
  WHERE ts.status IN ('OPEN', 'PAYING')
  GROUP BY ts.id, t.code, ts.status;
"

# Verificar circuit breakers y retry queue
curl http://localhost:8000/api/health/detailed | jq '.circuit_breakers, .webhook_retry'

# Ver webhooks en dead letter queue
redis-cli -p 6380 LRANGE webhook_retry:dead_letter 0 10

# Ver webhooks pendientes de retry
redis-cli -p 6380 ZRANGE webhook_retry:pending 0 -1 WITHSCORES
```
