# Reporte de Trazabilidad y Operabilidad del Sistema

**Fecha:** Enero 2026
**Autor:** Arquitecto de Software
**Alcance:** Dashboard, pwaMenu, pwaWaiter, Backend

---

## Resumen Ejecutivo

Este reporte documenta la trazabilidad completa del sistema desde las interfaces de usuario hasta la base de datos, identificando anomalias criticas y proponiendo soluciones.

### Hallazgos Criticos

| Severidad | Cantidad | Descripcion |
|-----------|----------|-------------|
| CRITICA | 1 | Bug de cierre de conexiones Redis pooled |
| ALTA | 2 | Stores Dashboard sin integracion backend |
| MEDIA | 3 | Endpoints no consumidos |

---

## 1. Arquitectura del Sistema

```
                    ┌─────────────────────────────────────────────────────────────┐
                    │                     FRONTENDS                                │
                    │                                                              │
    ┌───────────────┼───────────────┬───────────────────┬───────────────────────┐ │
    │   Dashboard   │   pwaMenu     │   pwaWaiter       │                       │ │
    │   (5177)      │   (5176)      │   (5178)          │                       │ │
    │   26 pages    │   3 pages     │   4 pages         │                       │ │
    │   18 stores   │   6 stores    │   5 stores        │                       │ │
    └───────┬───────┴───────┬───────┴───────┬───────────┘                       │ │
            │               │               │                                    │ │
            │ JWT Auth      │ Table Token   │ JWT Auth                          │ │
            ▼               ▼               ▼                                    │ │
    ┌───────────────────────────────────────────────────────────────────────────┘ │
    │                         BACKEND                                              │
    │                                                                              │
    │  ┌─────────────────┐          ┌─────────────────┐                           │
    │  │   REST API      │          │   WS Gateway    │                           │
    │  │   (8000)        │          │   (8001)        │                           │
    │  │   14 routers    │◄────────►│   4 endpoints   │                           │
    │  │   134+ endpoints│   Redis  │   pub/sub       │                           │
    │  └────────┬────────┘   ▲      └─────────────────┘                           │
    │           │            │                                                     │
    │           ▼            │                                                     │
    │  ┌─────────────────┐   │      ┌─────────────────┐                           │
    │  │   PostgreSQL    │   └──────│   Redis         │                           │
    │  │   (5432)        │          │   (6380)        │                           │
    │  │   31 tables     │          │   pub/sub       │                           │
    │  └─────────────────┘          └─────────────────┘                           │
    └──────────────────────────────────────────────────────────────────────────────┘
```

---

## 2. Trazas de Prueba por Pagina

### 2.1 Dashboard (26 paginas)

#### 2.1.1 Paginas con Integracion Backend Completa

| Pagina | API Endpoints | Tablas DB | Estado |
|--------|---------------|-----------|--------|
| Branches | `GET/POST/PUT/DELETE /api/admin/branches` | `branch`, `tenant` | OK |
| Staff | `GET/POST/PUT/DELETE /api/admin/staff` | `app_user`, `user_branch_role` | OK |
| Tables | `GET/POST/PUT/DELETE /api/admin/tables` | `restaurant_table`, `branch_sector` | OK |
| Recipes | `GET/POST/PUT/DELETE /api/admin/recipes` | `recipe` | OK |
| Ingredients | `GET/POST/DELETE /api/admin/ingredients` | `ingredient`, `ingredient_group`, `sub_ingredient` | OK |
| ProductExclusions | `GET/PUT /api/admin/exclusions` | `branch_category_exclusion`, `branch_subcategory_exclusion` | OK |

**Traza de Prueba - Branches:**
```
1. Usuario: Click "Nueva Sucursal"
2. Frontend: branchStore.createBranchAsync(data)
3. API: POST /api/admin/branches
4. Backend: Insert into branch (tenant_id, name, slug, address)
5. DB: branch.id = 1234
6. WebSocket: ENTITY_CREATED -> tenant:{id}:admin
7. Frontend: Store actualizado, toast "Sucursal creada"
```

#### 2.1.2 Paginas con Operacion Local (Sin Backend)

| Pagina | Store | Estado | Impacto |
|--------|-------|--------|---------|
| Categories | categoryStore | SOLO LOCAL | ALTO - datos perdidos al refrescar |
| Subcategories | subcategoryStore | SOLO LOCAL | ALTO - datos perdidos al refrescar |
| Allergens | allergenStore | SOLO LOCAL | MEDIO - catalogos globales |
| Badges | badgeStore | SOLO LOCAL | BAJO - solo UI |
| Seals | sealStore | SOLO LOCAL | BAJO - solo UI |
| Roles | roleStore | SOLO LOCAL | BAJO - roles fijos |
| Promotions | promotionStore | PARCIAL | MEDIO - POST existe, GET falta consumir |

**ANOMALIA DETECTADA - Categories/Subcategories:**
```
Problema: categoryStore y subcategoryStore usan operaciones locales
          Los datos se pierden al refrescar la pagina

Archivo: Dashboard/src/stores/categoryStore.ts
Linea: addCategory() - Solo agrega a estado local

Solucion: Implementar async actions conectadas al backend
          Endpoints ya existen: GET/POST/PUT/DELETE /api/admin/categories
```

---

### 2.2 pwaMenu (3 paginas)

#### 2.2.1 Home.tsx - Menu Principal

**Traza Completa:**
```
FASE 1: Carga del Menu
┌─────────────────────────────────────────────────────────────────────┐
│ 1. Usuario escanea QR -> /{branchSlug}/table/{tableCode}            │
│ 2. Home.tsx monta -> useMenu(branchSlug)                            │
│ 3. menuStore.fetchMenu() -> GET /api/public/menu/{slug}             │
│ 4. Backend: catalog.py:54-277                                       │
│    - Query: branch WHERE slug = X AND is_active = true              │
│    - Query: category WHERE branch_id = X (con selectinload)         │
│    - Query: product JOIN branch_product                             │
│    - Query: product_allergen, product_dietary_profile               │
│ 5. Response: MenuOutput con categories[], products[], allergens     │
│ 6. Store: menuStore.menu = data, sessionStorage cache               │
└─────────────────────────────────────────────────────────────────────┘

FASE 2: Join a Mesa
┌─────────────────────────────────────────────────────────────────────┐
│ 1. Usuario ingresa nombre -> JoinTableModal                         │
│ 2. tableStore.joinTable(tableCode, branchSlug, name)                │
│ 3. API: POST /api/tables/{id}/session (crear sesion)                │
│ 4. Backend: tables.py - Insert into table_session                   │
│ 5. API: POST /api/diner/register (registrar comensal)               │
│ 6. Backend: diner.py:59-129 - Insert into diner                     │
│ 7. Store: backendSessionId, backendDinerId guardados                │
│ 8. WebSocket: Conecta a ws://localhost:8001/ws/diner?table_token=X  │
└─────────────────────────────────────────────────────────────────────┘

FASE 3: Envio de Pedido
┌─────────────────────────────────────────────────────────────────────┐
│ 1. Usuario: Click "Enviar Pedido"                                   │
│ 2. tableStore.submitOrder(items)                                    │
│ 3. API: POST /api/diner/rounds/submit                               │
│ 4. Backend: diner.py:174-289                                        │
│    - Insert into round (session_id, round_number, status=SUBMITTED) │
│    - Insert into round_item (product_id, qty, price)                │
│    - Redis: publish_round_event(ROUND_SUBMITTED)                    │
│ 5. WebSocket Events enviados a:                                     │
│    - branch:{id}:waiters (mozos)                                    │
│    - branch:{id}:kitchen (cocina)                                   │
│    - branch:{id}:admin (dashboard)                                  │
│ 6. Response: {round_id, round_number, status}                       │
│ 7. Store: orders[] actualizado con nuevo round                      │
└─────────────────────────────────────────────────────────────────────┘
```

**Tablas Impactadas:**
- `branch` (read)
- `category`, `subcategory` (read)
- `product`, `branch_product` (read)
- `product_allergen`, `allergen` (read)
- `product_dietary_profile` (read)
- `restaurant_table` (read/write status)
- `table_session` (write)
- `diner` (write)
- `round`, `round_item` (write)

#### 2.2.2 CloseTable.tsx - Cierre y Pago

**Traza Completa:**
```
FASE 1: Solicitar Cuenta
┌─────────────────────────────────────────────────────────────────────┐
│ 1. Usuario: Click "Pedir Cuenta"                                    │
│ 2. tableStore.closeTable()                                          │
│ 3. API: POST /api/billing/check/request                             │
│ 4. Backend: billing.py:67-166                                       │
│    - Validate session status = OPEN                                 │
│    - Calculate total from round_item                                │
│    - Insert into check (session_id, total_cents, status=REQUESTED)  │
│    - create_charges_for_check() - Insert into charge                │
│    - Update table_session.status = PAYING                           │
│    - Redis: publish_check_event(CHECK_REQUESTED)                    │
│ 5. WebSocket Events:                                                │
│    - waiters, admin, session channels                               │
│ 6. Store: tableState = 'bill_ready', backendCheckId guardado        │
└─────────────────────────────────────────────────────────────────────┘

FASE 2: Pago con Mercado Pago
┌─────────────────────────────────────────────────────────────────────┐
│ 1. Usuario: Click "Pagar con MP"                                    │
│ 2. billingAPI.createMercadoPagoPreference({check_id})               │
│ 3. API: POST /api/billing/mercadopago/preference                    │
│ 4. Backend: billing.py - Mercado Pago SDK                           │
│    - Insert into payment (check_id, provider=MP, status=PENDING)    │
│    - Create MP preference via SDK                                   │
│ 5. Response: {preference_id, init_point, sandbox_init_point}        │
│ 6. Redirect: window.location = init_point                           │
└─────────────────────────────────────────────────────────────────────┘

FASE 3: Webhook MP (Backend)
┌─────────────────────────────────────────────────────────────────────┐
│ 1. Mercado Pago: POST /api/billing/mercadopago/webhook              │
│ 2. Backend: billing.py:750-842                                      │
│    - Verify signature                                               │
│    - Update payment.status = APPROVED/REJECTED                      │
│    - allocate_payment_fifo() - Insert into allocation               │
│    - If fully paid: check.status = PAID                             │
│    - Redis: publish_check_event(CHECK_PAID)                         │
│ 3. WebSocket: CHECK_PAID -> session:{id}                            │
│ 4. pwaMenu: useOrderUpdates() recibe evento                         │
│ 5. Store: tableState = 'paid'                                       │
└─────────────────────────────────────────────────────────────────────┘
```

**Tablas Impactadas:**
- `check` (write)
- `charge` (write)
- `payment` (write)
- `allocation` (write)
- `table_session` (update status)
- `restaurant_table` (update status)

#### 2.2.3 PaymentResult.tsx

**Traza:**
```
1. Mercado Pago redirect: /payment/result?status=approved&...
2. Component parsea query params
3. Muestra resultado (no API calls)
4. Usuario: Click "Volver" -> navigate home
```

---

### 2.3 pwaWaiter (4 paginas principales)

#### 2.3.1 TableGrid.tsx - Vista de Mesas

**Traza:**
```
1. Login: POST /api/auth/login -> JWT token
2. WebSocket: ws://localhost:8001/ws/waiter?token=JWT
3. API: GET /api/waiter/my-tables
4. Backend: waiter.py - Query tables en sectores asignados
5. WebSocket Events escuchados:
   - ROUND_SUBMITTED, ROUND_READY, ROUND_SERVED
   - SERVICE_CALL_CREATED, SERVICE_CALL_ACKED
   - CHECK_REQUESTED, TABLE_CLEARED
6. Store actualiza estado de mesas en tiempo real
```

#### 2.3.2 TableDetail.tsx - Detalle de Mesa

**Traza:**
```
1. Click en TableCard -> navigate(/table/{id})
2. API: GET /api/waiter/tables/{id}/session
3. API: GET /api/diner/session/{id}/rounds
4. Muestra: diners, rounds, status
5. Actions: Marcar ready, servido, etc.
```

---

## 3. ANOMALIA CRITICA: Redis Connection Pool Bug

### 3.1 Descripcion del Problema

**Severidad:** CRITICA
**Impacto:** Degrada rendimiento progresivamente, puede causar connection exhaustion
**Archivos Afectados:** 6 routers, 11 ocurrencias

```python
# Patron INCORRECTO encontrado en todos los routers:

async def submit_round(...):
    redis = None
    try:
        redis = await get_redis_client()  # Obtiene conexion del POOL
        await publish_round_event(...)
    finally:
        if redis:
            await redis.close()  # ERROR: Cierra conexion del POOL!
```

### 3.2 Analisis Tecnico

El archivo `shared/events.py` define un pool de conexiones Redis:

```python
# Linea 142-159: Pool singleton
_redis_pool: redis.Redis | None = None

async def get_redis_pool() -> redis.Redis:
    global _redis_pool
    if _redis_pool is None:
        _redis_pool = redis.from_url(
            REDIS_URL,
            max_connections=20,  # Pool con 20 conexiones
            decode_responses=True,
        )
    return _redis_pool

# Linea 175-182: get_redis_client retorna el pool
async def get_redis_client() -> redis.Redis:
    return await get_redis_pool()  # Retorna la misma instancia del pool
```

**El problema:** Cuando los routers llaman `await redis.close()`, estan cerrando la unica instancia del pool, no una conexion individual.

### 3.3 Ubicacion de las Ocurrencias

| Archivo | Linea | Endpoint |
|---------|-------|----------|
| diner.py | 282 | POST /api/diner/rounds/submit |
| diner.py | 432 | POST /api/diner/service-call |
| billing.py | 165 | POST /api/billing/check/request |
| billing.py | 287 | POST /api/billing/cash/pay |
| billing.py | 388 | POST /api/billing/mercadopago/preference |
| billing.py | 841 | POST /api/billing/mercadopago/webhook |
| kitchen.py | 208 | POST /api/kitchen/rounds/{id}/status |
| kitchen_tickets.py | 472 | POST /api/kitchen/tickets/{id}/status |
| tables.py | 250 | POST /api/tables/{id}/clear |
| waiter.py | 198 | POST /api/waiter/service-calls/{id}/acknowledge |
| waiter.py | 292 | POST /api/waiter/service-calls/{id}/resolve |

### 3.4 Solucion Propuesta

**Opcion A: Eliminar el close() (RECOMENDADA)**

```python
# CORRECTO: No cerrar conexiones del pool
async def submit_round(...):
    try:
        redis = await get_redis_client()
        await publish_round_event(...)
    except Exception as e:
        logger.error("Failed to publish event", error=str(e))
    # Sin finally/close - el pool maneja las conexiones
```

**Opcion B: Usar context manager personalizado**

```python
# En shared/events.py agregar:
from contextlib import asynccontextmanager

@asynccontextmanager
async def get_redis_connection():
    """Context manager que NO cierra conexiones del pool."""
    redis = await get_redis_pool()
    try:
        yield redis
    except Exception:
        raise
    # No close() - el pool se cierra en shutdown

# Uso en routers:
async with get_redis_connection() as redis:
    await publish_round_event(...)
```

### 3.5 Impacto del Bug

1. **Primera request:** Pool se crea, conexion funciona, luego se cierra
2. **Segunda request:** Pool ya cerrado, nueva conexion falla o se crea pool nuevo
3. **Requests subsecuentes:** Comportamiento impredecible
   - Conexiones huerfanas
   - Timeouts intermitentes
   - Eventos no publicados (lost events)
   - Memory leaks potenciales

---

## 4. Otras Anomalias Detectadas

### 4.1 ANOMALIA ALTA: Categories/Subcategories sin Backend

**Estado:** Stores operan solo localmente
**Impacto:** Datos perdidos al refrescar
**Solucion:** Ya existen endpoints, falta conectar stores

```typescript
// Dashboard/src/stores/categoryStore.ts - Actual
addCategory: (data) => {
  const newCategory = { ...data, id: crypto.randomUUID() }
  set((state) => ({ categories: [...state.categories, newCategory] }))
  return newCategory
}

// Dashboard/src/stores/categoryStore.ts - Propuesto
createCategoryAsync: async (data) => {
  const apiCategory = await categoryAPI.create(data)
  const category = mapAPICategoryToFrontend(apiCategory)
  set((state) => ({ categories: [...state.categories, category] }))
  return category
}
```

### 4.2 ANOMALIA MEDIA: Endpoints No Consumidos

| Endpoint | Router | Estado |
|----------|--------|--------|
| GET /api/admin/audit-log | admin.py | No consumido por Dashboard |
| GET /api/admin/kitchen-tickets | kitchen_tickets.py | Parcialmente consumido |
| GET /api/rag/health | rag.py | No consumido |

### 4.3 ANOMALIA BAJA: TypeScript Types Desincronizados

Algunos tipos en `Dashboard/src/types/index.ts` no coinciden con schemas del backend:
- `RecipeModification` tiene propiedades diferentes
- `RecipePreparationStep` usa `step_number` vs `step`

---

## 5. Analisis de Rendimiento

### 5.1 Database Queries

**Optimizaciones Implementadas:**
- Eager loading con `selectinload`/`joinedload` en kitchen.py, catalog.py
- Indices en columnas de status (`Table.status`, `Round.status`, etc.)
- Connection pool con `pool_pre_ping=True`

**Posibles Mejoras:**
```sql
-- Indice compuesto para queries frecuentes
CREATE INDEX idx_round_branch_status ON round(branch_id, status);
CREATE INDEX idx_table_session_branch_status ON table_session(branch_id, status);
```

### 5.2 Redis Performance

**Configuracion Actual:**
```python
max_connections=20
socket_connect_timeout=5
socket_timeout=5
```

**Recomendaciones:**
1. Monitorear conexiones activas: `INFO clients`
2. Implementar health check periodico
3. Considerar Redis Cluster para alta disponibilidad

### 5.3 WebSocket Performance

**Metricas Clave:**
- Heartbeat: 30s interval, 10s timeout
- Reconexion: Exponential backoff con jitter
- Canales: Por branch, sector, sesion

**Optimizacion Propuesta:**
```python
# Batch events para reducir mensajes
async def publish_batch_events(events: list[Event]):
    async with get_redis_connection() as redis:
        pipeline = redis.pipeline()
        for event in events:
            pipeline.publish(event.channel, event.to_json())
        await pipeline.execute()
```

---

## 6. Matriz de Trazabilidad Completa

### 6.1 Dashboard Pages -> Backend -> Database

| Page | API Endpoint | HTTP Method | Router | DB Tables | Status |
|------|-------------|-------------|--------|-----------|--------|
| Branches | /api/admin/branches | CRUD | admin.py | branch | OK |
| Categories | /api/admin/categories | CRUD | admin.py | category | LOCAL ONLY |
| Subcategories | /api/admin/subcategories | CRUD | admin.py | subcategory | LOCAL ONLY |
| Products | /api/admin/products | CRUD | admin.py | product, branch_product | OK |
| Staff | /api/admin/staff | CRUD | admin.py | app_user, user_branch_role | OK |
| Tables | /api/admin/tables | CRUD | admin.py | restaurant_table | OK |
| Allergens | /api/admin/allergens | CRUD | admin.py | allergen | LOCAL ONLY |
| Promotions | /api/admin/promotions | CRUD | promotions.py | promotion, promotion_branch, promotion_item | PARTIAL |
| Recipes | /api/admin/recipes | CRUD | recipes.py | recipe | OK |
| Ingredients | /api/admin/ingredients | CRUD | ingredients.py | ingredient, ingredient_group | OK |
| Exclusions | /api/admin/exclusions | GET/PUT | admin.py | branch_*_exclusion | OK |
| Kitchen | /api/kitchen/rounds | GET/POST | kitchen.py | round, round_item | OK |
| Reports | N/A | N/A | N/A | N/A | LOCAL ONLY |

### 6.2 pwaMenu Pages -> Backend -> Database

| Page | API Endpoints | DB Tables | WebSocket Events |
|------|--------------|-----------|------------------|
| Home | GET /api/public/menu/{slug}, POST /api/diner/* | branch, category, product, diner, round | ROUND_* |
| CloseTable | POST /api/billing/* | check, charge, payment, allocation | CHECK_*, PAYMENT_* |
| PaymentResult | None | None | None |

### 6.3 pwaWaiter Pages -> Backend -> Database

| Page | API Endpoints | DB Tables | WebSocket Events |
|------|--------------|-----------|------------------|
| Login | POST /api/auth/login | app_user | None |
| TableGrid | GET /api/waiter/my-tables | restaurant_table, table_session | All events |
| TableDetail | GET /api/waiter/tables/{id}/* | round, round_item, diner | ROUND_*, SERVICE_CALL_* |
| ServiceCalls | GET/POST /api/waiter/service-calls | service_call | SERVICE_CALL_* |

---

## 7. Plan de Accion

### 7.1 Prioridad CRITICA (Inmediato)

1. **Corregir bug de Redis connection pool**
   - Eliminar `await redis.close()` de todos los routers
   - Verificar que solo `close_redis_pool()` se llame en shutdown

### 7.2 Prioridad ALTA (1-2 semanas)

2. **Conectar categoryStore y subcategoryStore al backend**
   - Implementar `fetchCategories()`, `createCategoryAsync()`, etc.
   - Migrar datos existentes locales

3. **Completar integracion de promotionStore**
   - Implementar `fetchPromotions()` consumiendo `/api/admin/promotions`

### 7.3 Prioridad MEDIA (2-4 semanas)

4. **Sincronizar TypeScript types con backend schemas**
5. **Implementar consumo de /api/admin/audit-log en Dashboard**
6. **Agregar indices compuestos para queries frecuentes**

---

## 8. Conclusion

El sistema presenta una arquitectura solida con trazabilidad clara en la mayoria de los flujos. Sin embargo, se identifico un **bug critico en el manejo de conexiones Redis** que debe corregirse inmediatamente para evitar degradacion de rendimiento y perdida de eventos en tiempo real.

Las anomalias secundarias (stores sin backend) representan deuda tecnica que debe abordarse para garantizar persistencia de datos y consistencia entre sesiones.

**Acciones inmediatas requeridas:**
1. Fix Redis connection pool (11 archivos)
2. Conectar stores locales al backend (3 stores)
3. Agregar tests de integracion para validar trazas
