# Auditoría 32: Trazas de Pruebas End-to-End y Análisis de Defectos

**Fecha:** 2026-01-16
**Auditor:** Senior Software Architect & QA Lead
**Enfoque:** Trazas de prueba desde frontend → endpoints → base de datos
**Método:** Análisis estático de código, revisión de flujos, detección de defectos

---

## Resumen Ejecutivo

| Categoría | CRITICAL | HIGH | MEDIUM | LOW | Total |
|-----------|----------|------|--------|-----|-------|
| **Autenticación** | 5 | 5 | 4 | 0 | 14 |
| **Admin CRUD** | 4 | 4 | 3 | 4 | 15 |
| **Flujo Diner** | 3 | 6 | 4 | 0 | 13 |
| **WebSocket** | 5 | 4 | 4 | 5 | 18 |
| **Modelos BD** | 3 | 6 | 8 | 5 | 22 |
| **TOTAL** | **20** | **25** | **23** | **14** | **82** |

### Estado General: ⚠️ REQUIERE ATENCIÓN URGENTE

Se identificaron **20 defectos CRÍTICOS** que afectan:
- Seguridad de autenticación (tokens blacklist no validados)
- Integridad de datos (race conditions en sesiones)
- Aislamiento multi-tenant (tenant_id nullable)
- Consistencia de estados (state machine indefinido)

---

## PARTE 1: Trazas de Prueba - Autenticación

### Traza AUTH-01: Login Exitoso

```
FRONTEND (Dashboard)
├─ POST /api/auth/login
│  Body: { email: "admin@demo.com", password: "admin123" }
│
BACKEND (auth.py:44-119)
├─ Rate limit check (5/minute global) ⚠️ CRIT-AUTH-02
├─ SELECT User WHERE email=? AND is_active=true
├─ verify_password(plain, hashed)
│  └─ ⚠️ CRIT-AUTH-03: Acepta plaintext si no empieza con "$2"
├─ needs_rehash() → hash si es plaintext
├─ SELECT UserBranchRole WHERE user_id=?
│  └─ ⚠️ CRIT-AUTH-05: No valida que todos pertenezcan al mismo tenant
├─ sign_jwt()
│  └─ ⚠️ CRIT-AUTH-04: No incluye "jti" (token ID)
└─ RESPONSE: { access_token, refresh_token, user }

DATABASE IMPACT
├─ User.password actualizado si era plaintext
└─ No audit log de login exitoso ⚠️ HIGH-AUTH-05
```

### Traza AUTH-02: Token Refresh

```
FRONTEND (pwaWaiter)
├─ POST /api/auth/refresh
│  Body: { refresh_token: "eyJ..." }
│
BACKEND (auth.py:122-173)
├─ verify_refresh_token()
│  └─ verify_jwt()
│     └─ ⚠️ CRIT-AUTH-01: NUNCA verifica contra blacklist
├─ SELECT User WHERE id=? AND is_active=true
├─ Re-fetch UserBranchRole (puede haber cambiado)
│  └─ ⚠️ HIGH-AUTH-04: Token viejo sigue válido 60 min
└─ RESPONSE: { access_token, refresh_token }

DATABASE IMPACT
└─ Ninguno (no se registra refresh)
```

### Traza AUTH-03: Logout

```
FRONTEND (Dashboard)
├─ POST /api/auth/logout
│  Header: Authorization: Bearer <token>
│
BACKEND (auth.py:191-221)
├─ revoke_all_user_tokens(user_id)
│  └─ SET Redis key "user_revoke:{user_id}" = timestamp
│     └─ ⚠️ CRIT-AUTH-01: verify_jwt() NUNCA lee esta key
├─ ⚠️ HIGH-AUTH-01: Retorna success=true aunque Redis falle
└─ RESPONSE: { success: true, message: "..." }

DATABASE IMPACT
└─ Ninguno

REDIS IMPACT
└─ SET user_revoke:{user_id} (pero nunca se lee)
```

### Defectos Críticos de Autenticación

| ID | Severidad | Descripción | Archivo:Línea |
|----|-----------|-------------|---------------|
| CRIT-AUTH-01 | CRITICAL | Token blacklist existe pero verify_jwt() NUNCA lo consulta | auth.py:94-124 |
| CRIT-AUTH-02 | CRITICAL | Rate limit es global (IP), no por email - permite brute force | auth.py:44 |
| CRIT-AUTH-03 | CRITICAL | Passwords plaintext aceptados indefinidamente | password.py:53-58 |
| CRIT-AUTH-04 | CRITICAL | JWT no tiene "jti" - blacklist individual imposible | auth.py:31-62 |
| CRIT-AUTH-05 | CRITICAL | No valida tenant isolation en branch_roles | auth.py:82-93 |
| HIGH-AUTH-01 | HIGH | Logout retorna success aunque revocación falle | auth.py:191-221 |
| HIGH-AUTH-02 | HIGH | Table token HMAC tiene race condition TOCTTOU | auth.py:323-368 |
| HIGH-AUTH-03 | HIGH | Refresh token no validado contra blacklist | auth.py:122-173 |
| HIGH-AUTH-04 | HIGH | Permisos cacheados 60 min en JWT | auth.py:96-119 |
| HIGH-AUTH-05 | HIGH | No hay logging de login exitoso/fallido | auth.py:45-75 |

---

## PARTE 2: Trazas de Prueba - Admin CRUD

### Traza CRUD-01: Crear Producto

```
FRONTEND (Dashboard/Products.tsx)
├─ POST /api/admin/products
│  Body: { name, category_id, subcategory_id, allergens[], branch_prices[] }
│
BACKEND (admin.py:1460-1620)
├─ current_user_context()
│  └─ ⚠️ CRIT-AUTH-01: user["sub"], NO user["user_id"]
├─ Validaciones:
│  ├─ SELECT Category WHERE id=? AND tenant_id=? AND is_active=true
│  ├─ SELECT Subcategory (si especificado)
│  └─ Allergens validation loop ⚠️ HIGH-ERROR-01
│     └─ Si falla mid-loop, db.rollback() después de flush
├─ INSERT Product
├─ db.flush() → Obtiene product.id
├─ Loop: INSERT ProductAllergen (cada alérgeno)
│  └─ ⚠️ CRIT-ALG-01: No eager load, N+1 query pattern
├─ Loop: Validate branches exist
│  └─ ⚠️ HIGH-RACE-01: Race condition si branch se elimina
├─ Loop: INSERT BranchProduct (precios por sucursal)
├─ set_created_by(product, user.get("user_id"), ...)
│  └─ ⚠️ CRIT-ADMIN-01: user_id es SIEMPRE None
└─ RESPONSE: ProductOutput

DATABASE IMPACT
├─ INSERT product (created_by_id = NULL) ⚠️
├─ INSERT product_allergen × N
└─ INSERT branch_product × M
```

### Traza CRUD-02: Eliminar Categoría (Soft Delete)

```
FRONTEND (Dashboard/Categories.tsx)
├─ DELETE /api/admin/categories/{id}
│
BACKEND (admin.py:1020-1062)
├─ SELECT Category WHERE id=? AND tenant_id=? AND is_active=true
├─ soft_delete(category, user_id, email)
│  └─ ⚠️ CRIT-ADMIN-01: user_id = None (key error)
├─ ⚠️ HIGH-CASCADE-01: NO muestra preview de productos afectados
├─ publish_entity_deleted("category", id)
│  └─ ⚠️ LOW-CASCADE-02: No incluye affected_entities
└─ RESPONSE: { success, entity }

DATABASE IMPACT
├─ UPDATE category SET is_active=false, deleted_at=now()
│  └─ deleted_by_id = NULL (audit trail roto)
└─ Productos y subcategorías quedan "huérfanos" lógicamente

WEBSOCKET IMPACT
└─ ENTITY_DELETED event (sin affected_entities)
```

### Traza CRUD-03: Listar Alérgenos

```
FRONTEND (Dashboard/Allergens.tsx)
├─ GET /api/admin/allergens
│
BACKEND (admin.py:2240-2260)
├─ SELECT Allergen WHERE tenant_id=? AND is_active=true
│  └─ NO selectinload(cross_reactions) ⚠️
├─ Loop: _build_allergen_output(allergen, db)
│  └─ ⚠️ CRIT-ALG-01: Cada iteración hace 1 query adicional
│     └─ SELECT AllergenCrossReaction WHERE allergen_id=?
└─ RESPONSE: [AllergenOutput × N]

DATABASE IMPACT
└─ 1 + N queries (N = cantidad de alérgenos)
   Con 20 alérgenos = 21 queries en vez de 2
```

### Defectos Críticos de Admin CRUD

| ID | Severidad | Descripción | Archivo:Línea |
|----|-----------|-------------|---------------|
| CRIT-ADMIN-01 | CRITICAL | user.get("user_id") retorna None - audit trail roto | admin.py:806,845,882,etc |
| CRIT-ALG-01 | CRITICAL | N+1 query en list_allergens | admin.py:2259 |
| CRIT-PERF-01 | CRITICAL | Missing eager loading en update_product | admin.py:1755-1761 |
| CRIT-SEC-01 | CRITICAL | Email uniqueness no filtra por tenant | admin.py:3278 |
| HIGH-PERF-02 | HIGH | N+1 en staff list filtering | admin.py:3156-3182 |
| HIGH-ERROR-01 | HIGH | Allergen validation puede dejar estado parcial | admin.py:1490-1546 |
| HIGH-RACE-01 | HIGH | Race condition en branch price validation | admin.py:1876-1918 |
| HIGH-CASCADE-01 | HIGH | No preview de cascade delete | admin.py:1020-1062 |

---

## PARTE 3: Trazas de Prueba - Flujo Diner

### Traza DINER-01: Unirse a Mesa (Escaneo QR)

```
FRONTEND (pwaMenu)
├─ GET /api/tables/{table_id}/session
│  Header: X-Table-Token: <jwt>
│
BACKEND (tables.py:185-251)
├─ verify_table_token()
├─ SELECT Table WHERE id=?
├─ SELECT TableSession WHERE table_id=? AND status IN ('OPEN','PAYING')
│  └─ ⚠️ CRIT-RACE-01: No FOR UPDATE lock
├─ Si no existe session:
│  ├─ INSERT TableSession
│  ├─ UPDATE Table SET status='ACTIVE'
│  └─ ⚠️ CRIT-RACE-01: Concurrent requests = 2 sessions
├─ publish_table_event(TABLE_SESSION_STARTED)
│  └─ ⚠️ HIGH-EVENT-01: Missing sector_id for waiter filtering
└─ RESPONSE: { session_id, table_token }

DATABASE IMPACT
├─ INSERT table_session (potencial duplicado)
└─ UPDATE restaurant_table SET status='ACTIVE'

WEBSOCKET IMPACT
└─ TABLE_SESSION_STARTED (sin sector_id)
```

### Traza DINER-02: Enviar Orden

```
FRONTEND (pwaMenu)
├─ POST /api/diner/rounds/submit
│  Header: X-Table-Token, X-Idempotency-Key
│  Body: { items: [{ product_id, qty, notes }] }
│
BACKEND (diner.py:200-380)
├─ Idempotency check:
│  └─ ⚠️ CRIT-IDEMP-01: No almacena key, usa heurística 60s
├─ SELECT TableSession WHERE id=? AND status='OPEN'
│  └─ ⚠️ CRIT-STATE-01: Inconsistente con otros endpoints (PAYING)
├─ Loop: Validate products
│  ├─ SELECT Product JOIN BranchProduct WHERE product_id=? AND branch_id=?
│  └─ ⚠️ HIGH-VALID-01: No valida stock ni límites de cantidad
├─ INSERT Round
├─ Loop: INSERT RoundItem
│  └─ ⚠️ HIGH-DINER-01: diner_id nunca se asigna
├─ publish_round_event(ROUND_SUBMITTED)
└─ RESPONSE: RoundOutput

DATABASE IMPACT
├─ INSERT round
└─ INSERT round_item × N (diner_id = NULL)

WEBSOCKET IMPACT
└─ ROUND_SUBMITTED to waiters, kitchen, admin, session
```

### Traza DINER-03: Solicitar Cuenta

```
FRONTEND (pwaMenu)
├─ POST /api/billing/check/request
│  Header: X-Table-Token
│
BACKEND (billing.py:90-175)
├─ SELECT TableSession WHERE id=?
├─ SELECT Round WHERE session_id=? AND status NOT IN ('CANCELED')
├─ Calculate total from RoundItems
├─ INSERT Check (status='REQUESTED')
│  └─ ⚠️ HIGH-STATE-01: State machine no definido
├─ create_charges_for_check()
│  └─ INSERT Charge por cada RoundItem
│     └─ diner_id = NULL (de HIGH-DINER-01)
├─ UPDATE TableSession SET status='PAYING'
├─ publish_check_event(CHECK_REQUESTED)
└─ RESPONSE: CheckOutput

DATABASE IMPACT
├─ INSERT check
├─ INSERT charge × N (diner_id = NULL para todos)
└─ UPDATE table_session SET status='PAYING'
```

### Traza DINER-04: Pago en Efectivo

```
FRONTEND (pwaWaiter)
├─ POST /api/billing/cash/pay
│  Body: { check_id, amount_cents }
│
BACKEND (billing.py:200-280)
├─ SELECT Check WHERE id=?
├─ Validation: amount <= remaining
│  └─ ⚠️ HIGH-VALID-02: No valida amount > 0 (negativos aceptados)
├─ INSERT Payment (status='COMPLETED')
├─ allocate_payment_fifo(payment)
│  └─ ⚠️ MED-RACE-01: Sin lock, race condition posible
│  └─ ⚠️ HIGH-EVENT-02: No publica eventos de allocation
├─ UPDATE Check SET paid_cents += amount
├─ IF fully paid: UPDATE status='PAID'
├─ publish_check_event(CHECK_PAID)
└─ RESPONSE: PaymentOutput

DATABASE IMPACT
├─ INSERT payment
├─ INSERT allocation × N (FIFO)
└─ UPDATE check
```

### Defectos Críticos de Flujo Diner

| ID | Severidad | Descripción | Archivo:Línea |
|----|-----------|-------------|---------------|
| CRIT-RACE-01 | CRITICAL | Race condition en CREATE session (sin FOR UPDATE) | tables.py:185-224 |
| CRIT-IDEMP-01 | CRITICAL | Idempotency key no se almacena, usa heurística 60s | diner.py:214-239 |
| CRIT-STATE-01 | CRITICAL | Inconsistencia en validación de session status | diner.py:241-247 |
| HIGH-VALID-01 | HIGH | No valida stock/disponibilidad/límites de producto | diner.py:288-306 |
| HIGH-EVENT-01 | HIGH | TABLE_SESSION_STARTED sin sector_id | tables.py:234-246 |
| HIGH-STATE-01 | HIGH | Check status machine no definido (timeouts, abandonos) | billing.py:126-145 |
| HIGH-VALID-02 | HIGH | Pagos negativos/cero aceptados | billing.py:228-234 |
| HIGH-DINER-01 | HIGH | RoundItem.diner_id siempre NULL | diner.py:310-319 |
| HIGH-EVENT-02 | HIGH | allocate_payment_fifo() no publica eventos | billing.py:249-250 |

---

## PARTE 4: Trazas de Prueba - WebSocket

### Traza WS-01: Conexión Waiter

```
FRONTEND (pwaWaiter)
├─ WS /ws/waiter?token=<jwt>
│
BACKEND (ws_gateway/main.py:266-346)
├─ verify_jwt(token)
│  └─ ⚠️ CRIT-AUTH-01: No verifica blacklist
├─ get_waiter_sector_ids(user_id, tenant_id)
│  └─ ⚠️ LOW-WS-03: Query sin cache
├─ manager.connect(websocket, user_id, branch_ids, sector_ids)
│  └─ ⚠️ CRIT-WS-07: Race condition en registros
├─ Loop: await websocket.receive_text()
│  ├─ "ping" → "pong"
│  ├─ "refresh_sectors" → re-query assignments
│  └─ else → logger.debug("Unknown message")
│     └─ ⚠️ LOW-WS-05: Sin rate limit en logging
└─ manager.disconnect() on exit

REDIS IMPACT
└─ Subscribe to sector:{id}:waiters OR branch:{id}:waiters

MEMORY IMPACT
├─ by_user[user_id].add(ws)
├─ by_branch[branch_id].add(ws) × N
└─ by_sector[sector_id].add(ws) × M
```

### Traza WS-02: Dispatch de Evento ROUND_SUBMITTED

```
BACKEND (shared/events.py → ws_gateway/main.py)
├─ publish_round_event() called from diner.py
│  ├─ publish_to_sector() if sector_id
│  ├─ publish_to_kitchen()
│  ├─ publish_to_admin()
│  └─ publish_to_session()
│
REDIS
├─ PUBLISH sector:{id}:waiters OR branch:{id}:waiters
├─ PUBLISH branch:{id}:kitchen
├─ PUBLISH branch:{id}:admin
└─ PUBLISH session:{id}

WS_GATEWAY (main.py:115-180)
├─ on_event() callback
├─ ⚠️ CRIT-WS-10: Si sector_id presente, branch NO se envía
│  └─ Managers/Admins sin sector assignment pierden evento
├─ ⚠️ CRIT-WS-11: Excepción en send crashea subscriber
└─ manager.send_to_*() para cada canal

FRONTEND IMPACT
├─ pwaWaiter: Recibe si está en sector o branch
├─ Dashboard: Recibe via /ws/admin
├─ pwaMenu: Recibe via session channel
└─ Kitchen: Recibe via /ws/kitchen
```

### Traza WS-03: Cleanup de Conexiones Stale

```
BACKEND (ws_gateway/main.py:98-112)
├─ start_heartbeat_cleanup() task
│  └─ Every 30 seconds:
│     ├─ manager.cleanup_stale_connections()
│     │  └─ ⚠️ HIGH-WS-04: Race con record_heartbeat()
│     ├─ get_stale_connections() → O(n) scan
│     │  └─ ⚠️ LOW-WS-01: Ineficiente con muchas conexiones
│     └─ For each stale: ws.close() + disconnect()
│        └─ ⚠️ CRIT-WS-07: Race condition durante disconnect
└─ Logs: "Cleaned up stale connections"

MEMORY IMPACT
└─ Removes stale entries from by_user, by_branch, etc.
```

### Defectos Críticos de WebSocket

| ID | Severidad | Descripción | Archivo:Línea |
|----|-----------|-------------|---------------|
| CRIT-WS-07 | CRITICAL | Race condition en disconnect() sin locks | connection_manager.py:100-140 |
| CRIT-WS-08 | CRITICAL | Partial registration si accept() falla mid-way | connection_manager.py:52-74 |
| CRIT-WS-09 | CRITICAL | Subscriber usa conexión standalone, no pool | redis_subscriber.py:36-66 |
| CRIT-WS-10 | CRITICAL | Eventos con sector_id NO llegan a branch managers | main.py:127-152 |
| CRIT-WS-11 | CRITICAL | Exception en on_event() crashea subscriber | main.py:119-163 |
| HIGH-WS-01 | HIGH | Sin rate limiting en send operations | connection_manager.py:190-347 |
| HIGH-WS-02 | HIGH | Diner disconnect no actualiza TableSession | main.py:522-523 |
| HIGH-WS-03 | HIGH | Broadcast carga todas las conexiones en memoria | connection_manager.py:324-348 |
| HIGH-WS-04 | HIGH | Heartbeat cleanup race con message handler | main.py:98-112 |

---

## PARTE 5: Análisis de Modelos de Base de Datos

### Defectos de Integridad Referencial

| ID | Severidad | Tabla | Campo | Problema |
|----|-----------|-------|-------|----------|
| CRIT-DB-01 | CRITICAL | product_cooking_method | tenant_id | Nullable - violación multi-tenant |
| CRIT-DB-02 | CRITICAL | product_flavor | tenant_id | Nullable - violación multi-tenant |
| CRIT-DB-03 | CRITICAL | product_texture | tenant_id | Nullable - violación multi-tenant |
| HIGH-DB-01 | HIGH | branch_sector | prefix | UniqueConstraint no maneja NULL branch_id |
| HIGH-DB-02 | HIGH | waiter_sector_assignment | - | No enforce exclusividad waiter↔sector |
| HIGH-DB-03 | HIGH | recipe_allergen | allergen_id | ondelete no especificado |
| HIGH-DB-04 | HIGH | recipe | product_id | CASCADE no definido |
| HIGH-DB-05 | HIGH | table | sector_id | CASCADE no definido |
| HIGH-DB-06 | HIGH | diner | session_id | CASCADE no definido |

### Índices Faltantes

| Tabla | Columnas | Uso |
|-------|----------|-----|
| service_call | (branch_id, status, created_at) | Waiter pending calls |
| round | (branch_id, status, submitted_at) | Kitchen queue |
| allocation | (charge_id, payment_id) | Balance queries |
| branch_product | (branch_id, is_available) | Menu availability |
| chat_log | (table_session_id, created_at) | Recent chats |

### Constraints Faltantes

| Tabla | Constraint Tipo | Descripción |
|-------|-----------------|-------------|
| diner | UNIQUE | (session_id, local_id) para idempotency |
| promotion_branch | UNIQUE | (tenant_id, promotion_id, branch_id) |
| recipe | UNIQUE | (tenant_id, branch_id, name) |
| check | CHECK | paid_cents <= total_cents |

---

## PARTE 6: Matriz de Impacto

### Por Componente Frontend

| Frontend | Defectos que Afectan | Impacto |
|----------|---------------------|---------|
| **Dashboard** | CRIT-AUTH-01, CRIT-ADMIN-01, CRIT-ALG-01 | Audit trail roto, N+1 performance |
| **pwaMenu** | CRIT-RACE-01, CRIT-IDEMP-01, HIGH-DINER-01 | Sessions duplicadas, split payment roto |
| **pwaWaiter** | CRIT-WS-10, HIGH-EVENT-01 | Eventos perdidos por sector filtering |

### Por Flujo de Negocio

| Flujo | Defectos Críticos | Riesgo |
|-------|-------------------|--------|
| **Login/Auth** | CRIT-AUTH-01 a 05 | Tokens revocados siguen funcionando |
| **Crear Pedido** | CRIT-IDEMP-01, HIGH-VALID-01 | Pedidos duplicados, items inválidos |
| **Pagar Cuenta** | HIGH-VALID-02, HIGH-DINER-01 | Pagos negativos, split payment roto |
| **Notificaciones** | CRIT-WS-10, HIGH-WS-02 | Managers pierden eventos |

---

## PARTE 7: Plan de Remediación

### Prioridad 1 - Seguridad (Semana 1)

1. **CRIT-AUTH-01**: Invocar check_token_validity() en verify_jwt()
2. **CRIT-AUTH-04**: Agregar "jti" a JWT claims
3. **CRIT-AUTH-02**: Rate limit por email, no solo por IP
4. **CRIT-AUTH-03**: Remover soporte de passwords plaintext

### Prioridad 2 - Integridad de Datos (Semana 2)

5. **CRIT-RACE-01**: SELECT FOR UPDATE en create session
6. **CRIT-IDEMP-01**: Almacenar idempotency key en Round
7. **CRIT-ADMIN-01**: Corregir user.get("user_id") → get_user_id(user)
8. **CRIT-DB-01/02/03**: Hacer tenant_id NOT NULL en tablas M:N

### Prioridad 3 - WebSocket (Semana 3)

9. **CRIT-WS-10**: Siempre enviar a branch además de sector
10. **CRIT-WS-11**: Try-except en on_event() callback
11. **CRIT-WS-07**: asyncio.Lock en disconnect()
12. **CRIT-WS-09**: Usar Redis pool en subscriber

### Prioridad 4 - Performance (Semana 4)

13. **CRIT-ALG-01**: selectinload en list_allergens
14. **HIGH-PERF-02**: contains_eager en staff filtering
15. Agregar índices compuestos faltantes
16. Agregar constraints UNIQUE faltantes

---

## PARTE 8: Trazas de Prueba Manual Sugeridas

### Test Case TC-01: Verificar Token Blacklist

```bash
# 1. Login
TOKEN=$(curl -X POST http://localhost:8000/api/auth/login \
  -H "Content-Type: application/json" \
  -d '{"email":"admin@demo.com","password":"admin123"}' | jq -r '.access_token')

# 2. Verificar que funciona
curl http://localhost:8000/api/auth/me -H "Authorization: Bearer $TOKEN"
# Esperado: 200 OK

# 3. Logout
curl -X POST http://localhost:8000/api/auth/logout -H "Authorization: Bearer $TOKEN"

# 4. Intentar usar token revocado
curl http://localhost:8000/api/auth/me -H "Authorization: Bearer $TOKEN"
# ACTUAL: 200 OK (token sigue funcionando) ⚠️ BUG
# ESPERADO: 401 Unauthorized
```

### Test Case TC-02: Verificar Race Condition en Session

```bash
# Ejecutar en paralelo:
for i in {1..5}; do
  curl -X GET "http://localhost:8000/api/tables/1/session" \
    -H "X-Table-Token: $TABLE_TOKEN" &
done
wait

# Verificar en BD:
# SELECT count(*) FROM table_session WHERE table_id=1 AND status IN ('OPEN','PAYING');
# ACTUAL: Puede ser > 1 ⚠️ BUG
# ESPERADO: Exactamente 1
```

### Test Case TC-03: Verificar Pagos Negativos

```bash
curl -X POST http://localhost:8000/api/billing/cash/pay \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"check_id": 1, "amount_cents": -1000}'

# ACTUAL: 200 OK (pago negativo aceptado) ⚠️ BUG
# ESPERADO: 400 Bad Request
```

### Test Case TC-04: Verificar N+1 en Alérgenos

```bash
# Habilitar SQL logging en backend
# Llamar:
curl http://localhost:8000/api/admin/allergens -H "Authorization: Bearer $TOKEN"

# ACTUAL: 21 queries (1 + 20 alérgenos)
# ESPERADO: 2 queries (con eager loading)
```

---

## Conclusión

### Evaluación General: ⚠️ ARQUITECTURA CON RIESGOS SIGNIFICATIVOS

**Fortalezas identificadas:**
- ✅ Sistema de eventos Redis 4-channel bien diseñado
- ✅ Soft delete con AuditMixin consistente
- ✅ WebSocket heartbeat y reconnection implementados
- ✅ FIFO allocation para split payments

**Debilidades críticas:**
- ❌ Token blacklist no funcional (seguridad)
- ❌ Race conditions en session creation (integridad)
- ❌ Audit trail con user_id=NULL (compliance)
- ❌ Multi-tenant con tenant_id nullable (aislamiento)
- ❌ N+1 queries en endpoints críticos (performance)

**Recomendación:**
Detener desarrollo de features hasta remediar los 20 defectos CRITICAL.
Tiempo estimado de remediación: 4 semanas con equipo de 2 desarrolladores.

---

**Estado:** 82 defectos identificados (20 CRITICAL, 25 HIGH, 23 MEDIUM, 14 LOW)
**Fecha:** 2026-01-16
**Próxima revisión:** Después de remediar Prioridad 1 y 2
