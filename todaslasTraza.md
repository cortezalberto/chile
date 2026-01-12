# Plan de Pruebas Exhaustivo - Trazabilidad Completa

**Fecha:** Enero 2026
**Autor:** QA - Arquitectura de Software
**Proyecto:** Integrador - Sistema de Gestión de Restaurantes

---

## Índice

1. [Resumen Ejecutivo](#i-resumen-ejecutivo)
2. [Matriz de Trazabilidad Cruzada](#ii-matriz-de-trazabilidad-cruzada)
3. [Plan de Pruebas Dashboard](#iii-plan-de-pruebas-dashboard)
4. [Plan de Pruebas pwaMenu](#iv-plan-de-pruebas-pwamenu)
5. [Plan de Pruebas pwaWaiter](#v-plan-de-pruebas-pwawaiter)
6. [Pruebas de Integración Multi-App](#vi-pruebas-de-integración-multi-app)
7. [Pruebas de WebSocket en Tiempo Real](#vii-pruebas-de-websocket-en-tiempo-real)
8. [Casos de Error y Edge Cases](#viii-casos-de-error-y-edge-cases)
9. [Checklist de Defectos Potenciales](#ix-checklist-de-defectos-potenciales)
10. [Matriz de Riesgos](#x-matriz-de-riesgos)

---

## I. Resumen Ejecutivo

### Aplicaciones en Scope

| App | Propósito | Usuarios | Acciones Identificadas |
|-----|-----------|----------|------------------------|
| **Dashboard** | Panel administración | Admin, Manager | 120+ sync, 50+ async |
| **pwaMenu** | Menú cliente | Comensales | 26 tableStore, 12 API |
| **pwaWaiter** | Panel mozo | Waiters | 20+ acciones, 14 eventos WS |

### Flujo Principal del Sistema

```
Dashboard (Admin)          pwaMenu (Comensal)           pwaWaiter (Mozo)
     │                           │                            │
     ├─ Crear menú ──────────────┼────────────────────────────┤
     ├─ Crear mesas ─────────────┼────────────────────────────┤
     │                           │                            │
     │                      Escanear QR                       │
     │                           │                            │
     │                      joinTable() ──────────────────────┼─ TABLE_SESSION_STARTED
     │                           │                            │
     │                      addToCart()                       │
     │                      submitOrder() ────────────────────┼─ ROUND_SUBMITTED
     │                           │                            │
     │                           │     ┌─────────────────────>│─ fetchTables()
     │                           │     │                      │
     │                           │<────┼─ ROUND_IN_KITCHEN ───┤
     │                           │<────┼─ ROUND_READY ────────┤
     │                           │     │                      │─ markRoundAsServed()
     │                           │<────┼─ ROUND_SERVED ───────┤
     │                           │                            │
     │                      CallWaiter ───────────────────────┼─ SERVICE_CALL_CREATED
     │                           │<────┼─ SERVICE_CALL_ACKED ─┤─ acknowledgeServiceCall()
     │                           │                            │
     │                      closeTable() ─────────────────────┼─ CHECK_REQUESTED
     │                           │                            │─ confirmCashPayment()
     │                           │<────┼─ CHECK_PAID ─────────┤
     │                           │                            │─ clearTable()
     │                           │<────┼─ TABLE_CLEARED ──────┤
     │                           │                            │
     └─ Ver reportes ────────────┴────────────────────────────┘
```

---

## II. Matriz de Trazabilidad Cruzada

### 2.1 Acciones Dashboard → Impacto en otras Apps

| Acción Dashboard | Endpoint Backend | Impacto pwaMenu | Impacto pwaWaiter |
|------------------|------------------|-----------------|-------------------|
| Crear sucursal | POST /api/admin/branches | ❌ Ninguno (fetch dinámico) | ❌ Ninguno |
| Editar sucursal | PATCH /api/admin/branches/{id} | ⚠️ Recarga menú si slug cambia | ⚠️ Recarga si branch activa |
| Eliminar sucursal | DELETE /api/admin/branches/{id} | ❌ Error 404 si activa | ❌ Logout forzado |
| Crear categoría | POST /api/admin/categories | ✅ Visible en fetchMenu() | ❌ N/A |
| Editar categoría | PATCH /api/admin/categories/{id} | ✅ Actualiza en próximo fetch | ❌ N/A |
| Eliminar categoría | DELETE /api/admin/categories/{id} | ⚠️ Productos huérfanos | ❌ N/A |
| Crear producto | POST /api/admin/products | ✅ Visible en menú | ❌ N/A |
| Editar producto | PATCH /api/admin/products/{id} | ✅ Precio/disponibilidad | ❌ N/A |
| Eliminar producto | DELETE /api/admin/products/{id} | ⚠️ Error si en carrito | ⚠️ Error en detalle ronda |
| Crear mesa | POST /api/admin/tables | ❌ N/A (QR específico) | ✅ Nueva en fetchTables() |
| Editar mesa | PATCH /api/admin/tables/{id} | ⚠️ Si status cambia | ✅ Actualización UI |
| Desactivar mesa | PATCH /tables/{id} is_active=false | ⚠️ Error al escanear QR | ✅ OUT_OF_SERVICE |
| Crear staff | POST /api/admin/staff | ❌ N/A | ✅ Nuevo login disponible |
| Editar staff | PATCH /api/admin/staff/{id} | ❌ N/A | ⚠️ Si rol cambia |
| Eliminar staff | DELETE /api/admin/staff/{id} | ❌ N/A | ⚠️ Sesión inválida |
| Crear promoción | POST /api/admin/promotions | ✅ Visible en menú | ❌ N/A |
| Editar promoción | PATCH /api/admin/promotions/{id} | ✅ Precio/fechas | ❌ N/A |
| Eliminar promoción | DELETE /api/admin/promotions/{id} | ⚠️ Error si en carrito | ❌ N/A |

### 2.2 Acciones pwaMenu → Impacto en otras Apps

| Acción pwaMenu | Endpoint Backend | Impacto Dashboard | Impacto pwaWaiter |
|----------------|------------------|-------------------|-------------------|
| joinTable() | POST /tables/{id}/session | ⚠️ TABLE_STATUS_CHANGED | ✅ TABLE_SESSION_STARTED |
| addToCart() | (Local only) | ❌ Ninguno | ❌ Ninguno |
| submitOrder() | POST /diner/rounds/submit | ✅ Visible en Kitchen | ✅ ROUND_SUBMITTED |
| CallWaiter() | POST /diner/service-call | ❌ N/A | ✅ SERVICE_CALL_CREATED |
| closeTable() | POST /billing/check/request | ❌ N/A | ✅ CHECK_REQUESTED |
| MP preference | POST /billing/mercadopago/preference | ❌ N/A | ⚠️ Pendiente pago |
| leaveTable() | (Local only) | ❌ Ninguno | ❌ Ninguno |

### 2.3 Acciones pwaWaiter → Impacto en otras Apps

| Acción pwaWaiter | Endpoint Backend | Impacto Dashboard | Impacto pwaMenu |
|------------------|------------------|-------------------|-----------------|
| markRoundAsServed() | PUT /kitchen/rounds/{id}/status | ✅ Kitchen actualiza | ✅ ROUND_SERVED |
| acknowledgeServiceCall() | POST /waiter/service-calls/{id}/ack | ❌ N/A | ✅ SERVICE_CALL_ACKED |
| resolveServiceCall() | POST /waiter/service-calls/{id}/resolve | ❌ N/A | ✅ SERVICE_CALL_CLOSED |
| confirmCashPayment() | POST /billing/cash/pay | ❌ N/A | ✅ CHECK_PAID |
| clearTable() | POST /billing/tables/{id}/clear | ✅ TABLE_CLEARED | ✅ TABLE_CLEARED |

---

## III. Plan de Pruebas Dashboard

### 3.1 Módulo: Autenticación

| ID | Caso de Prueba | Pasos | Resultado Esperado | Prioridad |
|----|----------------|-------|--------------------| --------- |
| D-AUTH-01 | Login exitoso ADMIN | 1. Ir a /login, 2. Ingresar admin@demo.com/admin123, 3. Submit | Redirect a /dashboard | CRÍTICA |
| D-AUTH-02 | Login exitoso MANAGER | 1. Login manager@demo.com/manager123 | Redirect, menú limitado | CRÍTICA |
| D-AUTH-03 | Login fallido | 1. Email incorrecto/password incorrecto | Error "Credenciales inválidas" | ALTA |
| D-AUTH-04 | Sesión expirada | 1. Esperar expiración token, 2. Hacer request | Redirect a /login | ALTA |
| D-AUTH-05 | Logout | 1. Click logout | Limpiar token, redirect login | ALTA |
| D-AUTH-06 | Refresh token | 1. Token cerca de expirar | Renovación automática | MEDIA |
| D-AUTH-07 | Acceso sin auth | 1. Ir a /dashboard sin login | Redirect a /login | CRÍTICA |

### 3.2 Módulo: Sucursales (Branches)

| ID | Caso de Prueba | Pasos | Resultado Esperado | Prioridad |
|----|----------------|-------|--------------------| --------- |
| D-BRANCH-01 | Crear sucursal | 1. Click "Nueva", 2. Llenar form, 3. Guardar | Sucursal en lista + API | CRÍTICA |
| D-BRANCH-02 | Crear sucursal - slug duplicado | 1. Crear con slug existente | Error "Slug ya existe" | ALTA |
| D-BRANCH-03 | Editar sucursal | 1. Click editar, 2. Modificar, 3. Guardar | Actualización local + API | ALTA |
| D-BRANCH-04 | Eliminar sucursal vacía | 1. Click eliminar sucursal sin datos | Eliminación exitosa | MEDIA |
| D-BRANCH-05 | Eliminar sucursal con datos | 1. Click eliminar sucursal con categorías | Preview cascade, confirmar | CRÍTICA |
| D-BRANCH-06 | Validar horarios | 1. opening_time > closing_time | Error de validación | MEDIA |

### 3.3 Módulo: Categorías

| ID | Caso de Prueba | Pasos | Resultado Esperado | Prioridad |
|----|----------------|-------|--------------------| --------- |
| D-CAT-01 | Crear categoría | 1. Seleccionar sucursal, 2. Nueva categoría | Crear en sucursal correcta | CRÍTICA |
| D-CAT-02 | Crear sin sucursal | 1. Sin sucursal seleccionada | Error "Seleccione sucursal" | ALTA |
| D-CAT-03 | Reordenar categorías | 1. Drag & drop | Nuevo orden persistido | MEDIA |
| D-CAT-04 | Eliminar con subcategorías | 1. Delete categoría con hijos | Preview cascade | ALTA |
| D-CAT-05 | Eliminar con productos | 1. Delete categoría con productos | Preview cascade completo | ALTA |

### 3.4 Módulo: Productos

| ID | Caso de Prueba | Pasos | Resultado Esperado | Prioridad |
|----|----------------|-------|--------------------| --------- |
| D-PROD-01 | Crear producto | 1. Llenar form completo, 2. Asignar precios por sucursal | Producto creado con BranchProduct | CRÍTICA |
| D-PROD-02 | Crear sin categoría | 1. No seleccionar categoría | Error validación | ALTA |
| D-PROD-03 | Precio negativo | 1. Ingresar precio < 0 | Error "Precio inválido" | ALTA |
| D-PROD-04 | Asignar alérgenos | 1. Seleccionar múltiples alérgenos | Relación M:N creada | ALTA |
| D-PROD-05 | Filtrar por categoría | 1. Seleccionar filtro categoría | Solo productos de categoría | MEDIA |
| D-PROD-06 | Eliminar producto | 1. Delete producto | Limpiar refs en promociones | ALTA |
| D-PROD-07 | Producto duplicado | 1. Mismo nombre en misma categoría | Error "Producto ya existe" | MEDIA |

### 3.5 Módulo: Mesas

| ID | Caso de Prueba | Pasos | Resultado Esperado | Prioridad |
|----|----------------|-------|--------------------| --------- |
| D-TABLE-01 | Crear mesa | 1. Nueva mesa con número único | Mesa creada | CRÍTICA |
| D-TABLE-02 | Número duplicado | 1. Crear con número existente en sucursal | Error "Número ya existe" | ALTA |
| D-TABLE-03 | Cambiar estado | 1. Modificar status | Update + WebSocket event | ALTA |
| D-TABLE-04 | WebSocket sync | 1. Otro usuario cambia mesa | UI actualiza en tiempo real | ALTA |
| D-TABLE-05 | Desactivar mesa ocupada | 1. is_active=false con sesión activa | ⚠️ Verificar comportamiento | ALTA |

### 3.6 Módulo: Personal (Staff)

| ID | Caso de Prueba | Pasos | Resultado Esperado | Prioridad |
|----|----------------|-------|--------------------| --------- |
| D-STAFF-01 | Crear staff | 1. Nuevo staff con email, rol, sucursal | Usuario creado con UserBranchRole | CRÍTICA |
| D-STAFF-02 | Email duplicado | 1. Crear con email existente | Error "Email ya registrado" | ALTA |
| D-STAFF-03 | Múltiples roles | 1. Asignar roles en múltiples sucursales | branch_roles array correcto | ALTA |
| D-STAFF-04 | Editar phone/dni/hire_date | 1. Actualizar campos nuevos | Persistencia en backend | ALTA |
| D-STAFF-05 | Eliminar staff activo | 1. Delete staff con sesión activa | ⚠️ Verificar impacto | MEDIA |

### 3.7 Módulo: Promociones

| ID | Caso de Prueba | Pasos | Resultado Esperado | Prioridad |
|----|----------------|-------|--------------------| --------- |
| D-PROMO-01 | Crear promoción | 1. Nombre, precio, fechas, sucursales, productos | Promotion + PromotionBranch + PromotionItem | CRÍTICA |
| D-PROMO-02 | Fechas inválidas | 1. end_date < start_date | Error validación | ALTA |
| D-PROMO-03 | Horarios inválidos | 1. end_time < start_time | Error validación | ALTA |
| D-PROMO-04 | Sin sucursales | 1. No seleccionar sucursales | Error "Seleccione al menos una" | ALTA |
| D-PROMO-05 | Sin productos | 1. No agregar productos | Error "Agregue productos" | ALTA |
| D-PROMO-06 | Conversión precio | 1. Precio $125.50 | Backend: 12550 cents | ALTA |

### 3.8 Módulo: Restaurante

| ID | Caso de Prueba | Pasos | Resultado Esperado | Prioridad |
|----|----------------|-------|--------------------| --------- |
| D-REST-01 | Cargar restaurante | 1. Ir a /restaurant | fetchRestaurant() desde tenantAPI | ALTA |
| D-REST-02 | Editar restaurante | 1. Modificar nombre, descripción | updateRestaurantAsync() | ALTA |
| D-REST-03 | Campos frontend-only | 1. Editar address, phone, email | Persistir en localStorage | MEDIA |

### 3.9 Módulo: Cocina (Kitchen)

| ID | Caso de Prueba | Pasos | Resultado Esperado | Prioridad |
|----|----------------|-------|--------------------| --------- |
| D-KITCHEN-01 | Ver pedidos pendientes | 1. Ir a /kitchen | Lista de rounds SUBMITTED | CRÍTICA |
| D-KITCHEN-02 | Cambiar a IN_KITCHEN | 1. Click en round | Status → IN_KITCHEN + WS event | CRÍTICA |
| D-KITCHEN-03 | Cambiar a READY | 1. Click "Listo" | Status → READY + WS event | CRÍTICA |
| D-KITCHEN-04 | WebSocket real-time | 1. Nuevo pedido desde pwaMenu | Aparece sin refresh | CRÍTICA |

---

## IV. Plan de Pruebas pwaMenu

### 4.1 Módulo: Entrada Mesa (JoinTable)

| ID | Caso de Prueba | Pasos | Resultado Esperado | Prioridad |
|----|----------------|-------|--------------------| --------- |
| M-JOIN-01 | Escanear QR válido | 1. Escanear QR mesa activa | Ir a paso nombre | CRÍTICA |
| M-JOIN-02 | Mesa inválida | 1. Número mesa inexistente | Error "Mesa no encontrada" | ALTA |
| M-JOIN-03 | Mesa desactivada | 1. Mesa con is_active=false | Error "Mesa no disponible" | ALTA |
| M-JOIN-04 | Ingresar nombre | 1. Nombre comensal (opcional) | joinTable() exitoso | CRÍTICA |
| M-JOIN-05 | Registro comensal retry | 1. Error en POST /diner/register | Retry exponencial 3x | ALTA |
| M-JOIN-06 | Multi-tab sync | 1. Abrir otra pestaña | Storage sync, misma sesión | MEDIA |
| M-JOIN-07 | Idempotencia registro | 1. Refresh durante registro | No duplicar comensal (local_id) | ALTA |

### 4.2 Módulo: Menú y Navegación

| ID | Caso de Prueba | Pasos | Resultado Esperado | Prioridad |
|----|----------------|-------|--------------------| --------- |
| M-MENU-01 | Cargar menú | 1. joinTable() exitoso | fetchMenu() con cache 5min | CRÍTICA |
| M-MENU-02 | Categorías y productos | 1. Ver menú | Mostrar por categoría | CRÍTICA |
| M-MENU-03 | Búsqueda productos | 1. Escribir en search | Filtrado debounced 300ms | ALTA |
| M-MENU-04 | Filtro alérgenos | 1. Seleccionar alérgenos | Ocultar productos con ese alérgeno | ALTA |
| M-MENU-05 | Producto sin precio | 1. Producto sin BranchProduct | No mostrar o "Consultar" | MEDIA |
| M-MENU-06 | Producto no disponible | 1. is_available=false | Mostrar deshabilitado | ALTA |

### 4.3 Módulo: Carrito Compartido

| ID | Caso de Prueba | Pasos | Resultado Esperado | Prioridad |
|----|----------------|-------|--------------------| --------- |
| M-CART-01 | Agregar producto | 1. Click producto, 2. Seleccionar cantidad, 3. Agregar | addToCart() con throttle | CRÍTICA |
| M-CART-02 | Cantidad límite | 1. Cantidad > 99 | Límite a 99 | ALTA |
| M-CART-03 | Notas producto | 1. Agregar notas especiales | Sanitizar HTML, max chars | ALTA |
| M-CART-04 | Modificar cantidad | 1. +/- en carrito | updateQuantity() | ALTA |
| M-CART-05 | Eliminar item | 1. Click eliminar | removeItem() | ALTA |
| M-CART-06 | Ver items otros comensales | 1. Carrito compartido | Mostrar por color comensal | ALTA |
| M-CART-07 | No modificar item ajeno | 1. Intentar editar item otro | canModifyItem() = false | ALTA |
| M-CART-08 | Throttle clicks rápidos | 1. Click agregar múltiples veces | Solo 1 por 100-200ms | MEDIA |

### 4.4 Módulo: Envío de Pedido

| ID | Caso de Prueba | Pasos | Resultado Esperado | Prioridad |
|----|----------------|-------|--------------------| --------- |
| M-ORDER-01 | Enviar pedido | 1. Revisar carrito, 2. Confirmar | submitOrder() → POST /diner/rounds/submit | CRÍTICA |
| M-ORDER-02 | Carrito vacío | 1. Submit sin items | Error "Carrito vacío" | ALTA |
| M-ORDER-03 | Retry en error | 1. Error de red | Retry exponencial 3x | ALTA |
| M-ORDER-04 | Optimistic update | 1. Enviar pedido | UI actualiza inmediato, rollback si error | ALTA |
| M-ORDER-05 | Historial pedidos | 1. Ver pedidos anteriores | getOrderHistory() correcto | ALTA |

### 4.5 Módulo: Estados de Pedido (WebSocket)

| ID | Caso de Prueba | Pasos | Resultado Esperado | Prioridad |
|----|----------------|-------|--------------------| --------- |
| M-WS-01 | ROUND_SUBMITTED | 1. Después de submitOrder() | Estado → 'submitted' | CRÍTICA |
| M-WS-02 | ROUND_IN_KITCHEN | 1. Cocina acepta | Estado → 'confirmed' + sonido | CRÍTICA |
| M-WS-03 | ROUND_READY | 1. Cocina termina | Estado → 'ready' + sonido order_ready | CRÍTICA |
| M-WS-04 | ROUND_SERVED | 1. Mozo entrega | Estado → 'delivered' | CRÍTICA |
| M-WS-05 | Heartbeat timeout | 1. Sin pong en 10s | Reconexión automática | ALTA |
| M-WS-06 | Reconexión backoff | 1. Múltiples desconexiones | Exponential backoff + jitter | ALTA |

### 4.6 Módulo: Llamar Mozo

| ID | Caso de Prueba | Pasos | Resultado Esperado | Prioridad |
|----|----------------|-------|--------------------| --------- |
| M-CALL-01 | Llamar mozo | 1. Click botón mozo, 2. Confirmar | POST /diner/service-call type=WAITER_CALL | CRÍTICA |
| M-CALL-02 | SERVICE_CALL_ACKED | 1. Mozo acepta | Estado → 'acked' + sonido waiter_coming | ALTA |
| M-CALL-03 | SERVICE_CALL_CLOSED | 1. Mozo resuelve | Auto-reset 3s | ALTA |
| M-CALL-04 | Historial llamadas | 1. Ver historial | serviceCallStore persistido | MEDIA |

### 4.7 Módulo: Cierre de Cuenta

| ID | Caso de Prueba | Pasos | Resultado Esperado | Prioridad |
|----|----------------|-------|--------------------| --------- |
| M-CLOSE-01 | Solicitar cuenta | 1. Click "Cuenta", 2. Revisar total | closeTable() → POST /billing/check/request | CRÍTICA |
| M-CLOSE-02 | División igual | 1. Seleccionar "Dividir igual" | getPaymentShares() correcto | ALTA |
| M-CLOSE-03 | División por consumo | 1. Seleccionar "Por consumo" | getTotalByDiner() correcto | ALTA |
| M-CLOSE-04 | Agregar propina | 1. Seleccionar 10%, 15%, 20% | Calcular total + propina | ALTA |
| M-CLOSE-05 | Pago Mercado Pago | 1. Seleccionar MP | createMercadoPagoPreference(), redirect | CRÍTICA |
| M-CLOSE-06 | Pago efectivo | 1. Seleccionar efectivo | createServiceCall type=PAYMENT_HELP | ALTA |
| M-CLOSE-07 | CHECK_PAID | 1. Mozo confirma pago | Estado → 'paid' | CRÍTICA |
| M-CLOSE-08 | TABLE_CLEARED | 1. Mozo libera mesa | leaveTable() automático | ALTA |

### 4.8 Módulo: Sesión y Persistencia

| ID | Caso de Prueba | Pasos | Resultado Esperado | Prioridad |
|----|----------------|-------|--------------------| --------- |
| M-SESS-01 | Sesión expirada (8h) | 1. lastActivity > 8h | Auto-clear, redirect entrada | ALTA |
| M-SESS-02 | 401 desde API | 1. Token inválido | onSessionExpired(), clear sesión | ALTA |
| M-SESS-03 | Refresh página | 1. F5 durante sesión activa | syncFromStorage(), mantener estado | ALTA |
| M-SESS-04 | Cerrar pestaña | 1. Cerrar y reabrir | Recuperar de localStorage | ALTA |

---

## V. Plan de Pruebas pwaWaiter

### 5.1 Módulo: Autenticación

| ID | Caso de Prueba | Pasos | Resultado Esperado | Prioridad |
|----|----------------|-------|--------------------| --------- |
| W-AUTH-01 | Login WAITER | 1. waiter@demo.com/waiter123 | Login exitoso, selección sucursal | CRÍTICA |
| W-AUTH-02 | Login sin rol WAITER | 1. kitchen@demo.com/kitchen123 | Error "Rol WAITER requerido" | ALTA |
| W-AUTH-03 | Seleccionar sucursal | 1. Elegir de lista branch_ids | selectBranch(), ir a TableGrid | CRÍTICA |
| W-AUTH-04 | Token refresh | 1. Token cerca de expirar | scheduleTokenRefresh() | ALTA |
| W-AUTH-05 | Logout | 1. Click logout | Clear tokens, disconnect WS | ALTA |

### 5.2 Módulo: Vista de Mesas (TableGrid)

| ID | Caso de Prueba | Pasos | Resultado Esperado | Prioridad |
|----|----------------|-------|--------------------| --------- |
| W-GRID-01 | Cargar mesas | 1. fetchTables() | Lista con counters | CRÍTICA |
| W-GRID-02 | Filtrar urgentes | 1. Filter "Urgentes" | Mesas con pending_calls > 0 | ALTA |
| W-GRID-03 | Filtrar activas | 1. Filter "Activas" | status = ACTIVE | ALTA |
| W-GRID-04 | Pull to refresh | 1. Deslizar hacia abajo | fetchTables() | ALTA |
| W-GRID-05 | Auto refresh | 1. Esperar 60s | Refresh automático | ALTA |
| W-GRID-06 | WebSocket updates | 1. Nuevo evento | UI actualiza sin refresh | CRÍTICA |
| W-GRID-07 | Badge ronda lista | 1. ROUND_READY | Badge verde visible | ALTA |
| W-GRID-08 | Badge llamada | 1. SERVICE_CALL_CREATED | Badge rojo + sonido | CRÍTICA |

### 5.3 Módulo: Detalle de Mesa (TableDetail)

| ID | Caso de Prueba | Pasos | Resultado Esperado | Prioridad |
|----|----------------|-------|--------------------| --------- |
| W-DETAIL-01 | Ver detalle | 1. Click en mesa | getTableSessionDetail() | CRÍTICA |
| W-DETAIL-02 | Ver rondas | 1. Lista de rounds | Status badges correctos | ALTA |
| W-DETAIL-03 | Filtrar rondas | 1. Tab "Listas" | Solo READY | ALTA |
| W-DETAIL-04 | Marcar servida | 1. Click "Entregar" | markRoundAsServed() → SERVED | CRÍTICA |
| W-DETAIL-05 | Confirmar acción | 1. Diálogo confirmación | ConfirmDialog aparece | ALTA |
| W-DETAIL-06 | Ver comensales | 1. Lista diners | Nombres y totales | ALTA |

### 5.4 Módulo: Llamadas de Servicio

| ID | Caso de Prueba | Pasos | Resultado Esperado | Prioridad |
|----|----------------|-------|--------------------| --------- |
| W-CALL-01 | Recibir llamada | 1. SERVICE_CALL_CREATED | Notificación + sonido | CRÍTICA |
| W-CALL-02 | Aceptar llamada | 1. acknowledgeServiceCall() | SERVICE_CALL_ACKED enviado | CRÍTICA |
| W-CALL-03 | Resolver llamada | 1. resolveServiceCall() | SERVICE_CALL_CLOSED enviado | CRÍTICA |
| W-CALL-04 | Push notification | 1. App en background | Notification API | ALTA |

### 5.5 Módulo: Pagos y Cierre

| ID | Caso de Prueba | Pasos | Resultado Esperado | Prioridad |
|----|----------------|-------|--------------------| --------- |
| W-PAY-01 | Recibir CHECK_REQUESTED | 1. Cliente solicita cuenta | Badge "Cuenta" visible | CRÍTICA |
| W-PAY-02 | Confirmar pago efectivo | 1. confirmCashPayment() | CHECK_PAID enviado | CRÍTICA |
| W-PAY-03 | Liberar mesa | 1. clearTable() | TABLE_CLEARED, status FREE | CRÍTICA |
| W-PAY-04 | Mesa ya liberada | 1. clearTable() duplicado | Error manejado | MEDIA |

### 5.6 Módulo: Offline Support

| ID | Caso de Prueba | Pasos | Resultado Esperado | Prioridad |
|----|----------------|-------|--------------------| --------- |
| W-OFF-01 | Detectar offline | 1. Desconectar red | OfflineBanner visible | ALTA |
| W-OFF-02 | Acción offline | 1. markRoundAsServed() sin red | Encolar en retryQueueStore | ALTA |
| W-OFF-03 | Reconectar | 1. Restaurar red | processQueue() automático | ALTA |
| W-OFF-04 | Cache IndexedDB | 1. Offline, ver mesas | getCachedTables() | ALTA |
| W-OFF-05 | WS desconectado | 1. WebSocket fail | ConnectionBanner visible | ALTA |

### 5.7 Módulo: Historial

| ID | Caso de Prueba | Pasos | Resultado Esperado | Prioridad |
|----|----------------|-------|--------------------| --------- |
| W-HIST-01 | Registrar acción | 1. markRoundAsServed() | addHistoryEntry() | MEDIA |
| W-HIST-02 | Sync entre tabs | 1. Acción en otra pestaña | BroadcastChannel sync | MEDIA |
| W-HIST-03 | Persistencia | 1. Cerrar y reabrir | Historial en localStorage | MEDIA |

---

## VI. Pruebas de Integración Multi-App

### 6.1 Flujo Completo: Pedido

| Paso | App | Acción | Verificar en | Resultado |
|------|-----|--------|--------------|-----------|
| 1 | Dashboard | Crear categoría + producto | Backend | Datos creados |
| 2 | pwaMenu | joinTable() | pwaWaiter | TABLE_SESSION_STARTED |
| 3 | pwaMenu | addToCart() + submitOrder() | pwaWaiter | ROUND_SUBMITTED visible |
| 4 | Dashboard | Kitchen: IN_KITCHEN | pwaMenu | Estado 'confirmed' |
| 5 | Dashboard | Kitchen: READY | pwaMenu + pwaWaiter | Sonido + badge |
| 6 | pwaWaiter | markRoundAsServed() | pwaMenu | Estado 'delivered' |

### 6.2 Flujo Completo: Servicio

| Paso | App | Acción | Verificar en | Resultado |
|------|-----|--------|--------------|-----------|
| 1 | pwaMenu | CallWaiter() | pwaWaiter | SERVICE_CALL_CREATED |
| 2 | pwaWaiter | acknowledgeServiceCall() | pwaMenu | SERVICE_CALL_ACKED |
| 3 | pwaWaiter | resolveServiceCall() | pwaMenu | SERVICE_CALL_CLOSED |

### 6.3 Flujo Completo: Pago

| Paso | App | Acción | Verificar en | Resultado |
|------|-----|--------|--------------|-----------|
| 1 | pwaMenu | closeTable() | pwaWaiter | CHECK_REQUESTED badge |
| 2 | pwaMenu | MP preference / efectivo | pwaWaiter | Estado pendiente |
| 3 | pwaWaiter | confirmCashPayment() | pwaMenu | CHECK_PAID |
| 4 | pwaWaiter | clearTable() | pwaMenu + Dashboard | TABLE_CLEARED, mesa libre |

### 6.4 Flujo: Eliminación en Cascada

| Paso | App | Acción | Verificar | Resultado |
|------|-----|--------|-----------|-----------|
| 1 | Dashboard | Eliminar sucursal | pwaMenu | Error 404 en fetchMenu() |
| 2 | Dashboard | Eliminar categoría | pwaMenu | Productos desaparecen |
| 3 | Dashboard | Eliminar producto en carrito | pwaMenu | ⚠️ Error o limpiar item |
| 4 | Dashboard | Desactivar mesa ocupada | pwaMenu | ⚠️ Sesión inválida |

---

## VII. Pruebas de WebSocket en Tiempo Real

### 7.1 Eventos y Suscriptores

| Evento | Publisher | Suscriptores | Canal Redis |
|--------|-----------|--------------|-------------|
| ROUND_SUBMITTED | pwaMenu | pwaWaiter, Dashboard Kitchen | kitchen:{branch_id} |
| ROUND_IN_KITCHEN | Dashboard Kitchen | pwaMenu | session:{id} |
| ROUND_READY | Dashboard Kitchen | pwaMenu, pwaWaiter | session:{id}, waiter:{branch_id} |
| ROUND_SERVED | pwaWaiter | pwaMenu | session:{id} |
| SERVICE_CALL_CREATED | pwaMenu | pwaWaiter | waiter:{branch_id} |
| SERVICE_CALL_ACKED | pwaWaiter | pwaMenu | session:{id} |
| SERVICE_CALL_CLOSED | pwaWaiter | pwaMenu | session:{id} |
| CHECK_REQUESTED | pwaMenu | pwaWaiter | waiter:{branch_id} |
| CHECK_PAID | pwaWaiter / MP webhook | pwaMenu | session:{id} |
| TABLE_CLEARED | pwaWaiter | pwaMenu, Dashboard | session:{id}, dashboard:{branch_id} |
| TABLE_SESSION_STARTED | pwaMenu | pwaWaiter | waiter:{branch_id} |
| TABLE_STATUS_CHANGED | Dashboard | pwaWaiter | waiter:{branch_id} |

### 7.2 Casos de Prueba WebSocket

| ID | Caso | Pasos | Resultado |
|----|------|-------|-----------|
| WS-01 | Conexión inicial | 1. Connect con JWT | Handshake exitoso |
| WS-02 | Token inválido | 1. Connect con token expirado | Error 401, redirect login |
| WS-03 | Heartbeat | 1. Esperar 30s | Ping enviado, pong recibido |
| WS-04 | Heartbeat timeout | 1. No recibir pong | Reconexión automática |
| WS-05 | Múltiples eventos | 1. Enviar 10 eventos rápidos | Todos procesados en orden |
| WS-06 | Reconexión | 1. Desconectar servidor | Backoff exponencial |
| WS-07 | Token refresh | 1. Token a 1min de expirar | scheduleTokenRefresh() |

---

## VIII. Casos de Error y Edge Cases

### 8.1 Errores de Red

| ID | Escenario | App | Comportamiento Esperado |
|----|-----------|-----|------------------------|
| ERR-NET-01 | Pérdida conexión durante submitOrder() | pwaMenu | Retry 3x, mostrar error |
| ERR-NET-02 | Pérdida conexión durante login | Dashboard | Mostrar error, permitir retry |
| ERR-NET-03 | Timeout API (30s) | Todas | AbortSignal, mensaje usuario |
| ERR-NET-04 | 500 Internal Server Error | Todas | Error genérico, log detallado |
| ERR-NET-05 | CORS error | Todas | Error descriptivo en dev |

### 8.2 Errores de Estado

| ID | Escenario | App | Comportamiento Esperado |
|----|-----------|-----|------------------------|
| ERR-STATE-01 | Sesión expirada 401 | pwaMenu | onSessionExpired(), clear, redirect |
| ERR-STATE-02 | Mesa ya cerrada | pwaMenu | Error, no permitir submitOrder() |
| ERR-STATE-03 | Round ya SERVED | pwaWaiter | Error, no permitir markAsServed() |
| ERR-STATE-04 | Producto eliminado en carrito | pwaMenu | ⚠️ VERIFICAR: Limpiar o error |
| ERR-STATE-05 | Sucursal eliminada | pwaWaiter | Logout forzado |

### 8.3 Edge Cases

| ID | Escenario | App | Comportamiento Esperado |
|----|-----------|-----|------------------------|
| EDGE-01 | 2 comensales agregan mismo producto | pwaMenu | Merge correcto, 2 items separados |
| EDGE-02 | Refresh durante submitOrder() | pwaMenu | No duplicar pedido |
| EDGE-03 | Multi-tab con diferentes mesas | pwaMenu | Conflicto detectado, limpiar |
| EDGE-04 | Mozo acepta llamada ya cerrada | pwaWaiter | Error 409 Conflict |
| EDGE-05 | Admin elimina mesa durante sesión | pwaMenu | ⚠️ VERIFICAR: Error 404 |
| EDGE-06 | Precio cambia después de agregar | pwaMenu | ⚠️ VERIFICAR: Precio viejo o nuevo |
| EDGE-07 | Promoción expira durante pedido | pwaMenu | ⚠️ VERIFICAR: Permitir o rechazar |

---

## IX. Checklist de Defectos Potenciales

### 9.1 Defectos Críticos (Bloqueantes)

| ID | Descripción | Ubicación | Severidad |
|----|-------------|-----------|-----------|
| DEF-CRIT-01 | Producto eliminado causa crash si está en carrito | pwaMenu/tableStore | CRÍTICA |
| DEF-CRIT-02 | Sesión expira sin notificar al usuario | pwaMenu/api.ts | CRÍTICA |
| DEF-CRIT-03 | WebSocket no reconecta después de sleep | pwaMenu/websocket.ts | CRÍTICA |
| DEF-CRIT-04 | Pago MP sin CHECK_PAID event | backend/billing | CRÍTICA |
| DEF-CRIT-05 | Race condition en submitOrder() | pwaMenu/store.ts | CRÍTICA |

### 9.2 Defectos Altos

| ID | Descripción | Ubicación | Severidad |
|----|-------------|-----------|-----------|
| DEF-HIGH-01 | Cascade delete no actualiza UI en tiempo real | Dashboard/cascadeService | ALTA |
| DEF-HIGH-02 | Throttle muy agresivo impide operación | pwaMenu/store.ts | ALTA |
| DEF-HIGH-03 | Retry queue no procesa al reconectar | pwaWaiter/retryQueueStore | ALTA |
| DEF-HIGH-04 | Token refresh falla silenciosamente | pwaWaiter/websocket.ts | ALTA |
| DEF-HIGH-05 | Precio cents/dollars inconsistente | promotionStore | ALTA |

### 9.3 Defectos Medios

| ID | Descripción | Ubicación | Severidad |
|----|-------------|-----------|-----------|
| DEF-MED-01 | Sonido no reproduce en iOS | pwaMenu/notificationSound | MEDIA |
| DEF-MED-02 | Pull-to-refresh no funciona en desktop | pwaWaiter/usePullToRefresh | MEDIA |
| DEF-MED-03 | Historial no sincroniza entre tabs | pwaWaiter/historyStore | MEDIA |
| DEF-MED-04 | Cache menú no invalida al editar | pwaMenu/menuStore | MEDIA |

---

## X. Matriz de Riesgos

### 10.1 Riesgos por Probabilidad e Impacto

| Riesgo | Probabilidad | Impacto | Mitigación |
|--------|--------------|---------|------------|
| Pérdida de pedido | BAJA | CRÍTICO | Retry, persistencia local |
| Sesión zombie | MEDIA | ALTO | TTL 8h, triple validación |
| WebSocket desconexión | ALTA | ALTO | Heartbeat, backoff, offline queue |
| Datos inconsistentes multi-tab | MEDIA | MEDIO | Storage events, sync |
| Race conditions | BAJA | CRÍTICO | Functional updates, deduplication |
| XSS en notas producto | BAJA | ALTO | Sanitización HTML |
| SSRF en URLs imagen | BAJA | CRÍTICO | Validación estricta URLs |

### 10.2 Cobertura de Pruebas Recomendada

| Módulo | Cobertura Actual | Objetivo | Notas |
|--------|------------------|----------|-------|
| Dashboard stores | ~80% | 90% | 100 tests existentes |
| pwaMenu tableStore | ~75% | 90% | 108 tests existentes |
| pwaWaiter | ~60% | 80% | Agregar tests offline |
| Backend endpoints | ~70% | 85% | Agregar integration tests |
| WebSocket events | ~50% | 80% | Test e2e necesarios |

---

## Apéndice A: Comandos de Ejecución de Tests

```bash
# Dashboard
cd Dashboard && npm run test              # Vitest (100 tests)
cd Dashboard && npm run test -- --coverage

# pwaMenu
cd pwaMenu && npm run test               # Vitest (108 tests)
cd pwaMenu && npm run test:run           # Single run

# pwaWaiter
cd pwaWaiter && npm run test             # Agregar tests

# Backend
cd backend && pytest                      # Python tests
cd backend && pytest --cov=rest_api

# E2E (futuro)
npx playwright test                       # Pruebas e2e
```

---

## Apéndice B: Usuarios de Prueba

| Email | Password | Rol | Uso |
|-------|----------|-----|-----|
| admin@demo.com | admin123 | ADMIN | Dashboard completo |
| manager@demo.com | manager123 | MANAGER | Dashboard limitado |
| kitchen@demo.com | kitchen123 | KITCHEN | Solo cocina |
| waiter@demo.com | waiter123 | WAITER | pwaWaiter |

---

*Documento generado: Enero 2026*
*Próxima revisión: Después de ejecución de pruebas*
