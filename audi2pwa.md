# Auditoría Exhaustiva pwaMenu - Simulación Mesa 4 Comensales

**Versión:** 1.0
**Fecha:** 2026-01-09
**Autor:** Arquitecto de Software, Programador Sr. y Especialista QA
**Proyecto:** pwaMenu - PWA de Pedidos Colaborativos para Clientes

---

## 1. Resumen Ejecutivo

Este documento presenta una auditoría exhaustiva del flujo completo de pwaMenu simulando una mesa con 4 comensales que:
- Escanean QR y se unen a la mesa
- Agregan productos al carrito compartido
- Realizan múltiples rondas de pedidos
- Llaman al mozo para consultar sobre un plato
- Solicitan la cuenta
- Pagan de forma mixta (2 en efectivo, 2 con Mercado Pago)

Se analiza la trazabilidad en cocina y los cambios de estado en cada etapa.

---

## 2. Configuración del Escenario

### 2.1 Mesa y Comensales

| Comensal | Nombre | Color | Rol en Simulación |
|----------|--------|-------|-------------------|
| D1 | Juan | #FF5733 | Primer comensal - inicia sesión |
| D2 | María | #33FF57 | Segundo comensal - consulta al mozo |
| D3 | Carlos | #3357FF | Tercer comensal - paga con MP |
| D4 | Ana | #F033FF | Cuarto comensal - paga con MP |

**Mesa:** Mesa 5 (table_id: 5, code: "A5")
**Sucursal:** Demo Branch (branch_id: 1)

### 2.2 Productos del Menú

| ID | Producto | Precio | Categoría |
|----|----------|--------|-----------|
| 10 | Hamburguesa Clásica | $1500 (150000 cents) | Platos Principales |
| 15 | Pizza Margherita | $1800 (180000 cents) | Platos Principales |
| 20 | Ensalada César | $900 (90000 cents) | Entradas |
| 25 | Cerveza Artesanal | $600 (60000 cents) | Bebidas |
| 30 | Tiramisú | $700 (70000 cents) | Postres |
| 35 | Café Espresso | $400 (40000 cents) | Bebidas |

---

## 3. Flujo Completo - Traza Detallada

### FASE 1: Unión a la Mesa

#### 3.1.1 Comensal D1 (Juan) escanea QR

**Timestamp:** T+0:00

```
ACCIÓN: Juan escanea QR code de Mesa 5
└── Frontend: JoinTable.tsx → tableStore.joinTable("5")
    └── API: POST /api/tables/5/session
        └── Backend: tables.py:create_or_get_session()
            ├── Crea TableSession (status: OPEN)
            ├── Actualiza Table.status: FREE → ACTIVE
            └── Genera table_token JWT
```

**Request:**
```http
POST /api/tables/5/session
Content-Type: application/json
```

**Response:**
```json
{
  "session_id": 101,
  "table_id": 5,
  "table_code": "A5",
  "table_token": "eyJhbGciOiJIUzI1NiIs...",
  "status": "OPEN"
}
```

**WebSocket Event Publicado:**
```json
{
  "type": "TABLE_SESSION_STARTED",
  "branch_id": 1,
  "table_id": 5,
  "session_id": 101,
  "entity": {
    "table_code": "A5",
    "session_id": 101
  },
  "actor": {"user_id": null, "role": "DINER"},
  "ts": "2026-01-09T12:00:00Z"
}
```

**Canales:** `branch:1:waiters`

**Estado Frontend (tableStore):**
```typescript
{
  session: {
    id: "101",
    tableNumber: "5",
    tableName: "A5",
    status: "active",
    backendSessionId: 101,
    backendTableId: 5,
    diners: [],
    sharedCart: []
  },
  currentDiner: null
}
```

#### 3.1.2 Juan ingresa su nombre

**Timestamp:** T+0:15

```
ACCIÓN: Juan ingresa nombre "Juan"
└── Frontend: NameStep.tsx → dinerAPI.registerDiner()
    └── API: POST /api/diner/register
        └── Backend: diner.py:register_diner()
            └── Crea Diner record
```

**Request:**
```http
POST /api/diner/register
X-Table-Token: eyJhbGciOiJIUzI1NiIs...
Content-Type: application/json

{
  "name": "Juan",
  "color": "#FF5733",
  "local_id": "uuid-d1-local"
}
```

**Response:**
```json
{
  "id": 1,
  "session_id": 101,
  "name": "Juan",
  "color": "#FF5733",
  "local_id": "uuid-d1-local",
  "joined_at": "2026-01-09T12:00:15Z"
}
```

**Estado Frontend Actualizado:**
```typescript
{
  session: {
    diners: [{
      id: "uuid-d1-local",
      name: "Juan",
      avatarColor: "#FF5733",
      isCurrentUser: true,
      backendDinerId: 1
    }],
    sharedCart: []
  },
  currentDiner: { id: "uuid-d1-local", name: "Juan", ... }
}
```

#### 3.1.3 Comensales D2, D3, D4 se unen

**Timestamp:** T+1:00 - T+3:00

Cada comensal escanea el QR y se registra siguiendo el mismo flujo:

| Comensal | local_id | backend_id | joined_at |
|----------|----------|------------|-----------|
| María | uuid-d2-local | 2 | T+1:00 |
| Carlos | uuid-d3-local | 3 | T+2:00 |
| Ana | uuid-d4-local | 4 | T+3:00 |

**Estado Final de Diners:**
```typescript
session.diners = [
  { id: "uuid-d1-local", name: "Juan", backendDinerId: 1 },
  { id: "uuid-d2-local", name: "María", backendDinerId: 2 },
  { id: "uuid-d3-local", name: "Carlos", backendDinerId: 3 },
  { id: "uuid-d4-local", name: "Ana", backendDinerId: 4 }
]
```

---

### FASE 2: Primera Ronda de Pedidos

#### 3.2.1 Comensales agregan productos al carrito

**Timestamp:** T+5:00 - T+8:00

```
ACCIONES DE CARRITO:
├── Juan: Hamburguesa x1, Cerveza x1
├── María: Pizza x1, Cerveza x1
├── Carlos: Ensalada x1, Hamburguesa x1
└── Ana: Pizza x1, Tiramisú x1
```

**Flujo por cada addToCart:**
```
Frontend: ProductDetailModal → tableStore.addToCart(input)
├── Validación: isValidPrice(price), isValidQuantity(qty)
├── Throttle: shouldExecute('addToCart-{productId}', 200ms)
├── Si existe item del mismo diner: actualiza quantity
├── Si no existe: crea nuevo CartItem con crypto.randomUUID()
└── Actualiza session.lastActivity (SESSION TTL FIX)
```

**Estado del Carrito Compartido:**
```typescript
session.sharedCart = [
  // Juan
  { id: "ci-1", productId: "10", name: "Hamburguesa", price: 1500, qty: 1, dinerId: "uuid-d1-local", dinerName: "Juan" },
  { id: "ci-2", productId: "25", name: "Cerveza", price: 600, qty: 1, dinerId: "uuid-d1-local", dinerName: "Juan" },
  // María
  { id: "ci-3", productId: "15", name: "Pizza", price: 1800, qty: 1, dinerId: "uuid-d2-local", dinerName: "María" },
  { id: "ci-4", productId: "25", name: "Cerveza", price: 600, qty: 1, dinerId: "uuid-d2-local", dinerName: "María" },
  // Carlos
  { id: "ci-5", productId: "20", name: "Ensalada", price: 900, qty: 1, dinerId: "uuid-d3-local", dinerName: "Carlos" },
  { id: "ci-6", productId: "10", name: "Hamburguesa", price: 1500, qty: 1, dinerId: "uuid-d3-local", dinerName: "Carlos" },
  // Ana
  { id: "ci-7", productId: "15", name: "Pizza", price: 1800, qty: 1, dinerId: "uuid-d4-local", dinerName: "Ana" },
  { id: "ci-8", productId: "30", name: "Tiramisú", price: 700, qty: 1, dinerId: "uuid-d4-local", dinerName: "Ana" }
]
```

**Total Carrito:** $9,400

#### 3.2.2 Juan envía la primera ronda

**Timestamp:** T+10:00

```
ACCIÓN: Juan presiona "Enviar Pedido"
└── Frontend: SharedCart.tsx → tableStore.submitOrder()
    ├── Validación:
    │   ├── !isSubmitting (race condition)
    │   ├── session existe
    │   ├── !isSessionExpired (TTL check usando lastActivity)
    │   └── cart no vacío
    ├── Marca items con _submitting: true (rollback protection)
    ├── Construye SubmitRoundItem[] con atribución [dinerName]
    └── API: POST /api/diner/rounds/submit (con retry 3x)
```

**Request:**
```http
POST /api/diner/rounds/submit
X-Table-Token: eyJhbGciOiJIUzI1NiIs...
Content-Type: application/json

{
  "items": [
    {"product_id": 10, "qty": 1, "notes": "[Juan]"},
    {"product_id": 25, "qty": 1, "notes": "[Juan]"},
    {"product_id": 15, "qty": 1, "notes": "[María]"},
    {"product_id": 25, "qty": 1, "notes": "[María]"},
    {"product_id": 20, "qty": 1, "notes": "[Carlos]"},
    {"product_id": 10, "qty": 1, "notes": "[Carlos]"},
    {"product_id": 15, "qty": 1, "notes": "[Ana]"},
    {"product_id": 30, "qty": 1, "notes": "[Ana]"}
  ]
}
```

**Backend Processing:**
```python
# diner.py:submit_round()
1. Valida session.status == OPEN
2. Obtiene round_number = max(rounds) + 1 = 1
3. Busca precios en BranchProduct para cada product_id
4. Crea Round(status=SUBMITTED)
5. Crea RoundItem para cada item con unit_price_cents
6. Publica evento ROUND_SUBMITTED
```

**Response:**
```json
{
  "session_id": 101,
  "round_id": 201,
  "round_number": 1,
  "status": "SUBMITTED"
}
```

**WebSocket Event:**
```json
{
  "type": "ROUND_SUBMITTED",
  "branch_id": 1,
  "table_id": 5,
  "session_id": 101,
  "entity": {
    "round_id": 201,
    "round_number": 1
  },
  "actor": {"user_id": null, "role": "DINER"},
  "ts": "2026-01-09T12:10:00Z"
}
```

**Canales:** `branch:1:waiters`, `branch:1:kitchen`, `session:101`

**Estado Frontend Post-Submit:**
```typescript
{
  session: {
    sharedCart: [], // Vaciado
    lastActivity: "2026-01-09T12:10:00Z"
  },
  orders: [{
    id: "201",
    roundNumber: 1,
    items: [...8 items...],
    subtotal: 9400,
    status: "submitted",
    submittedBy: "uuid-d1-local",
    submittedByName: "Juan",
    submittedAt: "2026-01-09T12:10:00Z",
    backendRoundId: 201
  }],
  currentRound: 1
}
```

---

### FASE 3: Trazabilidad en Cocina - Ronda 1

#### 3.3.1 Cocina recibe pedido

**Timestamp:** T+10:05

```
pwaKitchen (o Dashboard Kitchen View):
└── GET /api/kitchen/rounds
    └── Retorna rounds con status IN ["SUBMITTED", "IN_KITCHEN"]
```

**Response Kitchen Queue:**
```json
[
  {
    "id": 201,
    "round_number": 1,
    "status": "SUBMITTED",
    "table_id": 5,
    "table_code": "A5",
    "created_at": "2026-01-09T12:10:00Z",
    "items": [
      {"product_name": "Hamburguesa", "qty": 2, "notes": "[Juan], [Carlos]"},
      {"product_name": "Pizza", "qty": 2, "notes": "[María], [Ana]"},
      {"product_name": "Cerveza", "qty": 2, "notes": "[Juan], [María]"},
      {"product_name": "Ensalada", "qty": 1, "notes": "[Carlos]"},
      {"product_name": "Tiramisú", "qty": 1, "notes": "[Ana]"}
    ]
  }
]
```

#### 3.3.2 Cocina marca "En Preparación"

**Timestamp:** T+12:00

```
ACCIÓN: Cocinero marca ronda como EN_COCINA
└── API: POST /api/kitchen/rounds/201/status
    └── Backend: kitchen.py:update_round_status()
        ├── Valida transición SUBMITTED → IN_KITCHEN
        ├── Actualiza Round.status
        └── Publica ROUND_IN_KITCHEN
```

**Request:**
```http
POST /api/kitchen/rounds/201/status
Authorization: Bearer <kitchen_jwt>
Content-Type: application/json

{"status": "IN_KITCHEN"}
```

**Response:**
```json
{
  "id": 201,
  "round_number": 1,
  "status": "IN_KITCHEN",
  "items": [...],
  "updated_at": "2026-01-09T12:12:00Z"
}
```

**WebSocket Event:**
```json
{
  "type": "ROUND_IN_KITCHEN",
  "branch_id": 1,
  "table_id": 5,
  "session_id": 101,
  "entity": {"round_id": 201, "round_number": 1},
  "actor": {"user_id": 50, "role": "KITCHEN"},
  "ts": "2026-01-09T12:12:00Z"
}
```

**Canales:** `branch:1:waiters`, `branch:1:kitchen`, `session:101`

**Frontend Update (useOrderUpdates hook):**
```typescript
// pwaMenu recibe evento via dinerWS
dinerWS.on('ROUND_IN_KITCHEN', handleRoundEvent)
↓
// Mapea status
mapRoundStatusToOrderStatus('IN_KITCHEN') → 'confirmed'
↓
// Actualiza orden
tableStore.updateOrderStatus("201", "confirmed")
↓
// Estado actualizado
orders[0].status = "confirmed"
orders[0].confirmedAt = "2026-01-09T12:12:00Z"
```

#### 3.3.3 Cocina marca "Listo"

**Timestamp:** T+25:00

```
ACCIÓN: Cocinero marca ronda como LISTA
└── API: POST /api/kitchen/rounds/201/status
    └── {"status": "READY"}
```

**WebSocket Event:**
```json
{
  "type": "ROUND_READY",
  "entity": {"round_id": 201, "round_number": 1},
  "actor": {"user_id": 50, "role": "KITCHEN"}
}
```

**Frontend Update:**
```typescript
orders[0].status = "ready"
orders[0].readyAt = "2026-01-09T12:25:00Z"
```

#### 3.3.4 Mozo marca "Servido"

**Timestamp:** T+27:00

```
ACCIÓN: Mozo entrega pedido y marca como SERVIDO
└── API: POST /api/kitchen/rounds/201/status
    └── {"status": "SERVED"}
```

**WebSocket Event:**
```json
{
  "type": "ROUND_SERVED",
  "entity": {"round_id": 201, "round_number": 1},
  "actor": {"user_id": 30, "role": "WAITER"}
}
```

**Frontend Update:**
```typescript
orders[0].status = "delivered"
orders[0].deliveredAt = "2026-01-09T12:27:00Z"
```

---

### FASE 4: Llamada al Mozo (Service Call)

#### 3.4.1 María llama al mozo para preguntar sobre un plato

**Timestamp:** T+15:00 (durante preparación de Ronda 1)

```
ACCIÓN: María presiona ícono de campana
└── Frontend: CallWaiterModal.tsx → formAction (useActionState)
    └── NOTA: Actualmente MOCK - simula 500ms delay
    └── TODO Backend: dinerAPI.createServiceCall({type: 'WAITER_CALL'})
```

**Estado Actual (MOCK):**
```typescript
// CallWaiterModal.tsx línea 32-37
const [formState, formAction, isPending] = useActionState(
  async (_prevState: CallWaiterState): Promise<CallWaiterState> => {
    // Simulate API call - NO HAY LLAMADA REAL AL BACKEND
    await new Promise((resolve) => setTimeout(resolve, ANIMATION.API_SIMULATION_MS))
    return { status: 'success', error: null }
  },
  { status: 'idle', error: null }
)
```

**⚠️ DEFECTO DETECTADO: M001 - Service Call Mock**

El CallWaiterModal no está conectado al backend. Debería llamar a:

```http
POST /api/diner/service-call
X-Table-Token: eyJhbGciOiJIUzI1NiIs...
Content-Type: application/json

{"type": "WAITER_CALL"}
```

**Response Esperada:**
```json
{
  "id": 301,
  "type": "WAITER_CALL",
  "status": "OPEN",
  "created_at": "2026-01-09T12:15:00Z",
  "acked_by_user_id": null
}
```

**WebSocket Event Esperado:**
```json
{
  "type": "SERVICE_CALL_CREATED",
  "branch_id": 1,
  "table_id": 5,
  "session_id": 101,
  "entity": {"call_id": 301, "call_type": "WAITER_CALL"},
  "actor": {"user_id": null, "role": "DINER"}
}
```

**Canal:** `branch:1:waiters`

#### 3.4.2 Flujo completo del Service Call (si estuviera implementado)

```
1. Diner llama → SERVICE_CALL_CREATED
2. Mozo ve notificación en pwaWaiter
3. Mozo acknowledge → SERVICE_CALL_ACKED
   └── POST /api/waiter/service-calls/301/acknowledge
4. Mozo atiende consulta
5. Mozo resuelve → SERVICE_CALL_CLOSED
   └── POST /api/waiter/service-calls/301/resolve
```

---

### FASE 5: Segunda Ronda de Pedidos

#### 3.5.1 Comensales agregan más productos

**Timestamp:** T+35:00

Después de comer la primera ronda, piden más:

```
CARRITO RONDA 2:
├── Juan: Café x1
├── María: Tiramisú x1
├── Carlos: Café x1, Cerveza x1
└── Ana: Café x1
```

**Estado del Carrito:**
```typescript
session.sharedCart = [
  { productId: "35", name: "Café", price: 400, qty: 1, dinerName: "Juan" },
  { productId: "30", name: "Tiramisú", price: 700, qty: 1, dinerName: "María" },
  { productId: "35", name: "Café", price: 400, qty: 1, dinerName: "Carlos" },
  { productId: "25", name: "Cerveza", price: 600, qty: 1, dinerName: "Carlos" },
  { productId: "35", name: "Café", price: 400, qty: 1, dinerName: "Ana" }
]
```

**Total Carrito Ronda 2:** $2,500

#### 3.5.2 María envía la segunda ronda

**Timestamp:** T+38:00

**Request:**
```json
{
  "items": [
    {"product_id": 35, "qty": 1, "notes": "[Juan]"},
    {"product_id": 30, "qty": 1, "notes": "[María]"},
    {"product_id": 35, "qty": 1, "notes": "[Carlos]"},
    {"product_id": 25, "qty": 1, "notes": "[Carlos]"},
    {"product_id": 35, "qty": 1, "notes": "[Ana]"}
  ]
}
```

**Response:**
```json
{
  "session_id": 101,
  "round_id": 202,
  "round_number": 2,
  "status": "SUBMITTED"
}
```

**Estado Frontend:**
```typescript
orders = [
  { id: "201", roundNumber: 1, status: "delivered", subtotal: 9400 },
  { id: "202", roundNumber: 2, status: "submitted", subtotal: 2500 }
]
currentRound = 2
```

#### 3.5.3 Trazabilidad Ronda 2 en Cocina

| Timestamp | Evento | Estado | Actor |
|-----------|--------|--------|-------|
| T+38:00 | ROUND_SUBMITTED | submitted | DINER (María) |
| T+40:00 | ROUND_IN_KITCHEN | confirmed | KITCHEN |
| T+45:00 | ROUND_READY | ready | KITCHEN |
| T+47:00 | ROUND_SERVED | delivered | WAITER |

---

### FASE 6: Solicitud de Cuenta

#### 3.6.1 Juan solicita la cuenta

**Timestamp:** T+60:00

```
ACCIÓN: Juan va a CloseTable y presiona "Pedir Cuenta"
└── Frontend: CloseTable.tsx → useCloseTableFlow.startCloseFlow()
    └── tableStore.closeTable()
        └── API: POST /api/billing/check/request
```

**Validaciones Pre-Request:**
```typescript
// CloseTable.tsx línea 72-78
if (session.sharedCart.length > 0) {
  setError(t('closeTable.cartErrorPending'))
  return
}
// Debe vaciar carrito antes de pedir cuenta
```

**Request:**
```http
POST /api/billing/check/request
X-Table-Token: eyJhbGciOiJIUzI1NiIs...
```

**Backend Processing:**
```python
# billing.py:request_check()
1. Calcula total de todas las rondas no canceladas
   total_cents = sum(item.unit_price_cents * item.qty for round in rounds for item in round.items)
   total_cents = 9400 + 2500 = 11900 pesos = 1190000 cents
2. Crea Check(status=REQUESTED, total_cents=1190000, paid_cents=0)
3. Crea Charge para cada RoundItem (Phase 3)
4. Actualiza TableSession.status → PAYING
5. Actualiza Table.status → PAYING
6. Publica CHECK_REQUESTED
```

**Response:**
```json
{
  "check_id": 401,
  "total_cents": 1190000,
  "paid_cents": 0,
  "status": "REQUESTED"
}
```

**WebSocket Event:**
```json
{
  "type": "CHECK_REQUESTED",
  "branch_id": 1,
  "table_id": 5,
  "session_id": 101,
  "entity": {"check_id": 401, "total_cents": 1190000},
  "actor": {"user_id": null, "role": "DINER"}
}
```

**Canal:** `branch:1:waiters`

**Estado Frontend:**
```typescript
{
  session: {
    status: "paying",
    backendCheckId: 401
  },
  closeStatus: "bill_ready"
}
```

---

### FASE 7: Pago Mixto - 2 Efectivo + 2 Mercado Pago

#### 3.7.1 Resumen de Consumo por Comensal

| Comensal | Items | Subtotal |
|----------|-------|----------|
| Juan | Hamburguesa, Cerveza, Café | $2,500 |
| María | Pizza, Cerveza, Tiramisú | $3,100 |
| Carlos | Ensalada, Hamburguesa, Café, Cerveza | $3,400 |
| Ana | Pizza, Tiramisú, Café | $2,900 |
| **TOTAL** | | **$11,900** |

#### 3.7.2 Pago 1: Juan paga en efectivo

**Timestamp:** T+62:00

```
ACCIÓN: Juan elige "Efectivo" en BillReadyState
└── Frontend: CloseStatusView.tsx → onConfirmPayment('cash')
    └── useCloseTableFlow.confirmPayment('cash')
        └── dinerAPI.createServiceCall({type: 'PAYMENT_HELP'})
```

**Request Service Call:**
```http
POST /api/diner/service-call
X-Table-Token: eyJhbGciOiJIUzI1NiIs...
Content-Type: application/json

{"type": "PAYMENT_HELP"}
```

**Response:**
```json
{
  "id": 302,
  "type": "PAYMENT_HELP",
  "status": "OPEN",
  "created_at": "2026-01-09T13:02:00Z"
}
```

**WebSocket Event:**
```json
{
  "type": "SERVICE_CALL_CREATED",
  "entity": {"call_id": 302, "call_type": "PAYMENT_HELP"}
}
```

**Estado Frontend:**
```typescript
closeStatus = "waiting_waiter"
// Muestra: "Esperando al mozo..."
```

#### 3.7.3 Mozo procesa pago en efectivo de Juan

**Timestamp:** T+65:00

```
ACCIÓN: Mozo recibe $2,500 de Juan y registra pago
└── pwaWaiter: POST /api/billing/cash/pay
```

**Request:**
```http
POST /api/billing/cash/pay
Authorization: Bearer <waiter_jwt>
Content-Type: application/json

{
  "check_id": 401,
  "amount_cents": 250000,
  "diner_id": 1
}
```

**Backend Processing:**
```python
# billing.py:record_cash_payment()
1. Crea Payment(provider=CASH, status=APPROVED, amount_cents=250000)
2. Asigna pago a Charges de diner_id=1 (Juan) usando FIFO
3. Actualiza Check.paid_cents = 250000
4. Check.status = IN_PAYMENT (no fully paid yet)
5. Publica PAYMENT_APPROVED
```

**Response:**
```json
{
  "payment_id": 501,
  "check_id": 401,
  "amount_cents": 250000,
  "provider": "CASH",
  "status": "APPROVED",
  "check_status": "IN_PAYMENT",
  "check_paid_cents": 250000,
  "check_total_cents": 1190000
}
```

**WebSocket Event:**
```json
{
  "type": "PAYMENT_APPROVED",
  "entity": {
    "payment_id": 501,
    "check_id": 401,
    "amount_cents": 250000,
    "provider": "CASH"
  },
  "actor": {"user_id": 30, "role": "WAITER"}
}
```

#### 3.7.4 Pago 2: María paga en efectivo

**Timestamp:** T+67:00

**Request:**
```json
{
  "check_id": 401,
  "amount_cents": 310000,
  "diner_id": 2
}
```

**Response:**
```json
{
  "payment_id": 502,
  "check_status": "IN_PAYMENT",
  "check_paid_cents": 560000
}
```

**Estado Check:**
- Total: $11,900
- Pagado: $5,600 (Juan $2,500 + María $3,100)
- Restante: $6,300

#### 3.7.5 Pago 3: Carlos paga con Mercado Pago

**Timestamp:** T+70:00

```
ACCIÓN: Carlos elige "Mercado Pago" en BillReadyState
└── Frontend: CloseStatusView.tsx → handleMercadoPagoPayment()
    └── billingAPI.createMercadoPagoPreference({check_id: 401})
```

**⚠️ NOTA:** En el flujo actual de pwaMenu, Mercado Pago paga el total restante, no el monto individual. Sin embargo, para esta simulación asumimos que se puede hacer pago parcial.

**Request:**
```http
POST /api/billing/mercadopago/preference
X-Table-Token: eyJhbGciOiJIUzI1NiIs...
Content-Type: application/json

{"check_id": 401}
```

**Backend Processing:**
```python
# billing.py:create_mp_preference()
1. remaining = total_cents - paid_cents = 1190000 - 560000 = 630000
2. Crea preferencia MP con amount = 6300.00 ARS
3. Crea Payment(provider=MERCADO_PAGO, status=PENDING)
```

**Response:**
```json
{
  "preference_id": "mp-pref-123",
  "init_point": "https://www.mercadopago.com/checkout/v1/...",
  "sandbox_init_point": "https://sandbox.mercadopago.com/checkout/v1/..."
}
```

**Frontend Redirect:**
```typescript
// CloseStatusView.tsx línea 148-149
const checkoutUrl = isTestMode() ? preference.sandbox_init_point : preference.init_point
window.location.href = checkoutUrl
// Usuario sale de pwaMenu → MP Checkout
```

#### 3.7.6 Carlos completa pago en MP (webhook)

**Timestamp:** T+72:00

```
ACCIÓN: Carlos paga $3,400 en MP checkout
└── MP notifica webhook
    └── POST /api/billing/mercadopago/webhook
```

**Webhook Request (from Mercado Pago):**
```json
{
  "type": "payment",
  "data": {"id": "mp-payment-456"}
}
```

**Backend Processing:**
```python
# billing.py:mercadopago_webhook()
1. Fetch payment details from MP API
2. payment_status = "approved"
3. Encuentra Payment por external_id
4. Actualiza Payment.status = APPROVED
5. Asigna 340000 cents a charges
6. Check.paid_cents = 560000 + 340000 = 900000
7. Check.status = IN_PAYMENT
8. Publica PAYMENT_APPROVED
```

**WebSocket Event:**
```json
{
  "type": "PAYMENT_APPROVED",
  "entity": {
    "payment_id": 503,
    "check_id": 401,
    "amount_cents": 340000,
    "provider": "MERCADO_PAGO"
  },
  "actor": {"user_id": null, "role": "SYSTEM"}
}
```

**Estado Check:**
- Pagado: $9,000 (Juan + María + Carlos)
- Restante: $2,900 (Ana)

#### 3.7.7 Pago 4: Ana paga con Mercado Pago

**Timestamp:** T+75:00

Ana sigue el mismo flujo que Carlos y paga $2,900.

**Después del webhook:**
```python
Check.paid_cents = 1190000
Check.status = PAID  # Fully paid!
```

**WebSocket Events:**
```json
{
  "type": "PAYMENT_APPROVED",
  "entity": {"payment_id": 504, "amount_cents": 290000, "provider": "MERCADO_PAGO"}
}
```

```json
{
  "type": "CHECK_PAID",
  "entity": {"check_id": 401, "total_cents": 1190000}
}
```

**Canal:** `branch:1:waiters`, `session:101`

**Frontend Update (CloseTable.tsx):**
```typescript
// línea 59-67
useEffect(() => {
  if (closeStatus !== 'waiting_waiter') return

  const unsubscribe = dinerWS.on('CHECK_PAID', () => {
    setCloseStatus('paid')
  })

  return unsubscribe
}, [closeStatus, setCloseStatus])
```

**Estado Final:**
```typescript
closeStatus = "paid"
// Muestra PaidView: "¡Listo! Gracias por tu visita"
```

---

### FASE 8: Cierre de Mesa

#### 3.8.1 Mozo limpia la mesa

**Timestamp:** T+80:00

```
ACCIÓN: Mozo marca mesa como libre en pwaWaiter
└── API: POST /api/billing/tables/5/clear
```

**Request:**
```http
POST /api/billing/tables/5/clear
Authorization: Bearer <waiter_jwt>
```

**Backend Processing:**
```python
# billing.py:clear_table()
1. Verifica Check.status == PAID
2. TableSession.status → CLOSED
3. Table.status → FREE
4. Publica TABLE_CLEARED
```

**Response:**
```json
{
  "table_id": 5,
  "status": "FREE"
}
```

**WebSocket Event:**
```json
{
  "type": "TABLE_CLEARED",
  "branch_id": 1,
  "table_id": 5,
  "entity": {"table_code": "A5"},
  "actor": {"user_id": 30, "role": "WAITER"}
}
```

#### 3.8.2 Comensales dejan la mesa

**Frontend:**
```typescript
// CloseTable.tsx → handleLeaveTable()
leaveTable()  // Limpia session, diners, orders
onBack()      // Navega a home
```

**tableStore.leaveTable():**
```typescript
leaveTable: () => {
  dinerWS.disconnect()       // Desconecta WebSocket
  setTableToken(null)        // Limpia token
  set({
    session: null,
    currentDiner: null,
    orders: [],
    currentRound: 0
  })
}
```

---

## 4. Diagrama de Estados

### 4.1 Estados de Ronda (Round)

```
┌──────────┐    submit    ┌───────────┐   kitchen    ┌────────────┐
│  DRAFT   │─────────────▶│ SUBMITTED │──────────────▶│ IN_KITCHEN │
└──────────┘              └───────────┘              └────────────┘
                                                            │
                                                            │ kitchen ready
                                                            ▼
┌──────────┐    waiter    ┌───────────┐              ┌─────────┐
│  SERVED  │◀─────────────│   READY   │◀─────────────│         │
└──────────┘              └───────────┘              └─────────┘
```

### 4.2 Estados de Mesa (Table)

```
┌──────┐   QR scan    ┌────────┐   request check   ┌────────┐   clear   ┌──────┐
│ FREE │──────────────▶│ ACTIVE │──────────────────▶│ PAYING │──────────▶│ FREE │
└──────┘              └────────┘                   └────────┘          └──────┘
```

### 4.3 Estados de Check

```
┌──────┐   request   ┌───────────┐   partial pay   ┌────────────┐   full pay   ┌──────┐
│ OPEN │────────────▶│ REQUESTED │────────────────▶│ IN_PAYMENT │─────────────▶│ PAID │
└──────┘            └───────────┘                 └────────────┘             └──────┘
```

---

## 5. Matriz de Eventos WebSocket

| Evento | Origen | Canales | Receptor Principal |
|--------|--------|---------|-------------------|
| TABLE_SESSION_STARTED | tables.py | branch:waiters | pwaWaiter |
| ROUND_SUBMITTED | diner.py | branch:waiters, branch:kitchen, session | pwaWaiter, Kitchen, pwaMenu |
| ROUND_IN_KITCHEN | kitchen.py | branch:waiters, branch:kitchen, session | pwaWaiter, Kitchen, pwaMenu |
| ROUND_READY | kitchen.py | branch:waiters, branch:kitchen, session | pwaWaiter, Kitchen, pwaMenu |
| ROUND_SERVED | kitchen.py | branch:waiters, branch:kitchen, session | pwaWaiter, Kitchen, pwaMenu |
| SERVICE_CALL_CREATED | diner.py | branch:waiters | pwaWaiter |
| SERVICE_CALL_ACKED | waiter.py | branch:waiters, session | pwaWaiter, pwaMenu |
| SERVICE_CALL_CLOSED | waiter.py | branch:waiters, session | pwaWaiter, pwaMenu |
| CHECK_REQUESTED | billing.py | branch:waiters | pwaWaiter |
| PAYMENT_APPROVED | billing.py | branch:waiters, session | pwaWaiter, pwaMenu |
| PAYMENT_REJECTED | billing.py | session | pwaMenu |
| CHECK_PAID | billing.py | branch:waiters, session | pwaWaiter, pwaMenu |
| TABLE_CLEARED | billing.py | branch:waiters | pwaWaiter |

---

## 6. Defectos Identificados

### Críticos (C)

| ID | Descripción | Archivo | Línea | Impacto |
|----|-------------|---------|-------|---------|
| C001 | CallWaiterModal no llama al backend | CallWaiterModal.tsx | 32-37 | Service calls no llegan al mozo |

### Altos (A)

| ID | Descripción | Archivo | Línea | Impacto |
|----|-------------|---------|-------|---------|
| A001 | Sin feedback de SERVICE_CALL_ACKED al diner | useOrderUpdates.ts | - | Diner no sabe si mozo recibió llamada |
| A002 | MP paga total restante, no monto individual | CloseStatusView.tsx | 140 | No permite split payment real con MP |

### Medios (M)

| ID | Descripción | Archivo | Línea | Impacto |
|----|-------------|---------|-------|---------|
| M001 | No hay vista de historial de llamadas al mozo | - | - | UX incompleto |
| M002 | Falta indicador visual de pago parcial completado | CloseTable.tsx | - | Confusión en pagos mixtos |
| M003 | No se muestra balance individual por comensal | CloseStatusView.tsx | - | Difícil saber cuánto debe cada uno |

### Bajos (L)

| ID | Descripción | Archivo | Línea | Impacto |
|----|-------------|---------|-------|---------|
| L001 | Falta animación de transición entre estados de pago | CloseStatusView.tsx | - | UX menos fluido |
| L002 | No hay sonido de notificación para eventos WS | useOrderUpdates.ts | - | Usuario puede perder actualizaciones |

---

## 7. Cobertura de Tests Requerida

### 7.1 Tests de Integración Necesarios

```typescript
describe('Mesa 4 Comensales - Flujo Completo', () => {
  it('should allow 4 diners to join same session', async () => {
    // Test union secuencial de 4 comensales
  })

  it('should aggregate cart items from all diners', async () => {
    // Test carrito compartido
  })

  it('should submit round with diner attribution', async () => {
    // Test que notes incluye [dinerName]
  })

  it('should update order status via WebSocket', async () => {
    // Test recepción de eventos ROUND_*
  })

  it('should handle mixed payment (cash + MP)', async () => {
    // Test pagos parciales
  })

  it('should trigger CHECK_PAID when fully paid', async () => {
    // Test evento final
  })
})
```

### 7.2 Tests de Componente

```typescript
describe('CallWaiterModal', () => {
  it('should call dinerAPI.createServiceCall on confirm', async () => {
    // TODO: Implementar cuando se conecte al backend
  })
})

describe('CloseStatusView', () => {
  it('should show WaitingWaiterState after cash selection', async () => {})
  it('should redirect to MP on mercadopago selection', async () => {})
  it('should transition to paid on CHECK_PAID event', async () => {})
})
```

---

## 8. Recomendaciones

### 8.1 Correcciones Críticas

1. **Conectar CallWaiterModal al backend**
   ```typescript
   // CallWaiterModal.tsx
   const [formState, formAction, isPending] = useActionState(
     async (_prevState: CallWaiterState): Promise<CallWaiterState> => {
       try {
         await dinerAPI.createServiceCall({ type: 'WAITER_CALL' })
         return { status: 'success', error: null }
       } catch (error) {
         return { status: 'idle', error: 'Error al llamar al mozo' }
       }
     },
     { status: 'idle', error: null }
   )
   ```

2. **Implementar split payment individual con MP**
   - Permitir especificar monto a pagar
   - Crear múltiples preferencias MP

### 8.2 Mejoras de UX

1. **Agregar feedback de SERVICE_CALL_ACKED**
   ```typescript
   dinerWS.on('SERVICE_CALL_ACKED', (event) => {
     showToast('El mozo viene en camino')
   })
   ```

2. **Mostrar balance por comensal en CloseTable**
   - Usar endpoint GET /api/billing/check/{id}/balances
   - Mostrar quién pagó y cuánto falta

3. **Agregar sonidos de notificación**
   - ROUND_READY → sonido de campana
   - CHECK_PAID → sonido de éxito

---

## 9. Conclusiones

La auditoría revela que pwaMenu tiene una arquitectura sólida para el flujo colaborativo de pedidos, con:

**Fortalezas:**
- ✅ Manejo robusto de sesiones con TTL y lastActivity
- ✅ Protección contra race conditions con _submitting flag
- ✅ Retry automático con exponential backoff
- ✅ WebSocket con heartbeat y reconexión automática
- ✅ Atribución de items por comensal en notas
- ✅ Soporte de pagos mixtos (cash + MP)

**Áreas de Mejora:**
- ⚠️ CallWaiterModal desconectado del backend
- ⚠️ Sin feedback visual de service call acknowledgment
- ⚠️ Split payment con MP no permite montos individuales
- ⚠️ Falta vista de balances por comensal

**Próximos Pasos:**
1. Implementar C001 (CallWaiterModal → backend)
2. Agregar evento SERVICE_CALL_ACKED al frontend
3. Diseñar UI de split payment mejorado
4. Agregar tests de integración para flujo completo

---

**Documento preparado por:**
Arquitecto de Software, Programador Sr. y Especialista QA
Versión 1.0 - 2026-01-09
