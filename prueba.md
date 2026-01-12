# Prueba de Flujo Completo: Mesa T-02 Terraza - Sucursal Centro

## Escenario

Es un sábado al mediodía en el restaurante "El Buen Sabor", sucursal Centro. Tres amigos —Martín, Lucía y Pedro— llegan al local y son ubicados en la mesa T-02 de la Terraza. Juan, el mozo asignado al sector Terraza para el turno del día, será quien los atienda.

---

## Preparación del Sistema

Antes de que los comensales lleguen, el sistema ya tiene configurado:

- **Sucursal**: Centro (id=1, slug="centro")
- **Sector**: Terraza (id=2, prefijo="TER")
- **Mesa**: T-02 (id=7, capacidad 6 personas)
- **Mozo asignado**: Juan Mozo (id=1, waiter@demo.com) está asignado al sector Terraza para hoy
- **Sesión de mesa**: Se creó la sesión #1 con su token JWT correspondiente

Las aplicaciones están corriendo en:
- **pwaMenu** (comensales): http://localhost:5176
- **pwaWaiter** (mozo Juan): http://localhost:5178
- **Dashboard/Cocina**: http://localhost:5177
- **Backend REST API**: http://localhost:8000
- **WebSocket Gateway**: http://localhost:8001

---

## Acto 1: Llegada de los Comensales

### Escena 1.1: Escaneo del QR

Los tres amigos se sientan en la mesa T-02. En el centro de la mesa hay un código QR que los lleva a la URL:

```
http://localhost:5176/centro/7
```

Cada uno saca su celular y escanea el código. Al abrir la aplicación pwaMenu, ven una pantalla de bienvenida que les pide ingresar su nombre.

### Escena 1.2: Registro de Comensales

**Martín** (primer comensal en entrar):
- Abre la primera pestaña del navegador
- Ingresa "Martín" como su nombre
- El sistema le asigna el color azul (#3B82F6) para identificar sus pedidos
- Se registra en el backend como Diner con `local_id` único

**Lucía** (segunda comensal):
- Abre otra pestaña (simulando otro celular)
- Ingresa "Lucía" como su nombre
- El sistema le asigna el color verde (#22C55E)
- Se registra como segundo Diner en la misma sesión

**Pedro** (tercer comensal):
- Abre la tercera pestaña
- Ingresa "Pedro" como su nombre
- El sistema le asigna el color naranja (#F97316)
- Se registra como tercer Diner

En este momento, el backend tiene:
- 1 TableSession (id=1) con estado "OPEN"
- 3 Diners registrados, cada uno con su `backend_diner_id`
- La mesa T-02 pasó de estado "FREE" a "ACTIVE"

---

## Acto 2: Exploración del Menú

### Escena 2.1: Navegación por Categorías

Los tres amigos exploran el menú digital. Ven cuatro categorías principales:

1. **Entradas** (icono: 🥗)
   - Entradas Frías: Burrata con Tomates Cherry ($12,500)
   - Entradas Calientes: Provoleta a la Parrilla ($9,800), Empanadas x3 ($7,500)

2. **Principales** (icono: 🍽️)
   - Carnes: Bife de Chorizo ($24,500), Ojo de Bife ($26,800)
   - Pescados: Trucha Cítrica ($19,800), Salmón Rosado ($21,500)
   - Pastas: Sorrentinos ($14,500), Ñoquis de Papa ($12,800)

3. **Postres** (icono: 🍰)
   - Brownie con Helado ($8,500), Flan Casero ($6,800), Tiramisú ($9,200)

4. **Bebidas** (icono: 🍷)
   - Agua Mineral ($3,500), Gaseosa ($4,500), Copa de Vino Malbec ($6,800)

### Escena 2.2: Selección de Productos

Cada comensal va agregando productos a su carrito individual:

**Martín decide pedir:**
- 1x Empanadas (x3) - $7,500
- 1x Bife de Chorizo - $24,500
- 1x Copa de Vino Malbec - $6,800
- **Subtotal Martín: $38,800**

**Lucía elige:**
- 1x Provoleta a la Parrilla - $9,800
- 1x Ñoquis de Papa - $12,800
- 1x Agua Mineral - $3,500
- **Subtotal Lucía: $26,100**

**Pedro selecciona:**
- 1x Burrata con Tomates Cherry - $12,500
- 1x Salmón Rosado - $21,500
- 1x Flan Casero - $6,800
- 1x Gaseosa - $4,500
- **Subtotal Pedro: $45,300**

El carrito compartido muestra en tiempo real los productos de los tres, diferenciados por color:
- Items azules → Martín
- Items verdes → Lucía
- Items naranjas → Pedro

**Total de la ronda: $110,200**

---

## Acto 3: Envío del Pedido

### Escena 3.1: Confirmación de la Ronda

Martín, que tiene su celular más a mano, toca el botón "Enviar Pedido". El sistema muestra un resumen:

```
Ronda #1
---------
Martín (azul):
  • 1x Empanadas (x3)
  • 1x Bife de Chorizo
  • 1x Copa de Vino Malbec

Lucía (verde):
  • 1x Provoleta a la Parrilla
  • 1x Ñoquis de Papa
  • 1x Agua Mineral

Pedro (naranja):
  • 1x Burrata con Tomates Cherry
  • 1x Salmón Rosado
  • 1x Flan Casero
  • 1x Gaseosa

Total: $110,200
```

Martín confirma. El sistema:

1. Crea un `Round` (id=1) con estado "SUBMITTED"
2. Crea 10 `RoundItem` (uno por cada producto, vinculado al Diner correspondiente)
3. Publica evento `ROUND_SUBMITTED` a 4 canales Redis:
   - `sector:2:waiters` → Juan (mozo del sector Terraza)
   - `branch:1:kitchen` → Cocina
   - `branch:1:admin` → Dashboard de administración
   - `session:1` → Los tres comensales

### Escena 3.2: Notificaciones en Tiempo Real

**En los celulares de Lucía y Pedro:**
- Ven que el carrito se vacía
- Aparece la ronda #1 en el historial de pedidos con estado "Enviado" (amarillo)

**En el celular de Juan (pwaWaiter):**
- Suena una notificación
- Aparece un badge en la mesa T-02
- Ve el detalle: "Nueva ronda - Mesa T-02 Terraza"

**En la pantalla de Cocina (Dashboard):**
- Aparece una nueva tarjeta en la columna "Nuevos"
- Muestra: "T-02" con los 10 items a preparar
- Indicador de tiempo: "0 min"

---

## Acto 4: Preparación en Cocina

### Escena 4.1: Recepción del Pedido

María, la cocinera (kitchen@demo.com), ve el pedido en su pantalla. Los items se agrupan visualmente:

```
┌─────────────────────────────────────┐
│ T-02                    Nuevo  0min │
├─────────────────────────────────────┤
│ 1x Empanadas (x3)                   │
│ 1x Provoleta a la Parrilla          │
│ 1x Burrata con Tomates Cherry       │
│ 1x Bife de Chorizo                  │
│ 1x Ñoquis de Papa                   │
│ 1x Salmón Rosado                    │
│ 1x Flan Casero                      │
│ 1x Agua Mineral                     │
│ 1x Copa de Vino Malbec              │
│ 1x Gaseosa                          │
├─────────────────────────────────────┤
│ [Marcar como En Cocina]             │
└─────────────────────────────────────┘
```

María toca "Marcar como En Cocina". El sistema:

1. Actualiza `Round.status` a "IN_KITCHEN"
2. Registra `Round.in_kitchen_at` con timestamp actual
3. Publica evento `ROUND_IN_KITCHEN` a los 4 canales

### Escena 4.2: Actualización en Tiempo Real

**En los celulares de los comensales:**
- El estado de la ronda cambia a "En cocina" (azul)
- Suena un sonido sutil de confirmación

**En el celular de Juan:**
- La mesa T-02 muestra indicador "En preparación"

La tarjeta en cocina se mueve a la columna "En Cocina":

```
Nuevos (0)     En Cocina (1)     Listos (0)
               ┌─────────────┐
               │ T-02   3min │
               │ 10 items    │
               │ [Listo]     │
               └─────────────┘
```

### Escena 4.3: Pedido Listo

Después de 15 minutos, María termina de preparar todos los platos. Toca "Marcar como Listo". El sistema:

1. Actualiza `Round.status` a "READY"
2. Registra `Round.ready_at`
3. Publica evento `ROUND_READY`

**En los celulares de los comensales:**
- El estado cambia a "Listo para servir" (verde)
- Suena una notificación más prominente
- Mensaje: "¡Tu pedido está listo!"

**En el celular de Juan:**
- Notificación urgente: "Ronda lista - Mesa T-02"
- La mesa parpadea con indicador verde

---

## Acto 5: Servicio de la Ronda

### Escena 5.1: Juan Sirve los Platos

Juan se acerca a la mesa T-02 con los platos. Mientras sirve, los comensales ven en sus celulares exactamente qué ordenó cada uno gracias a los colores.

Una vez que todos los platos están en la mesa, Juan abre su app y marca la ronda como "Servida". El sistema:

1. Actualiza `Round.status` a "SERVED"
2. Registra `Round.served_at`
3. Publica evento `ROUND_SERVED`

**En los celulares de los comensales:**
- El estado cambia a "Servido" (gris/completado)
- La ronda se mueve al historial

**En la pantalla de cocina:**
- La tarjeta desaparece (no hay más pedidos pendientes)

---

## Acto 6: Segunda Ronda (Opcional)

### Escena 6.1: Pedido Adicional

Después de comer, los amigos deciden pedir postre. Esta vez Lucía toma la iniciativa:

**Lucía agrega:**
- 1x Tiramisú - $9,200

**Pedro agrega:**
- 1x Brownie con Helado - $8,500

Martín decide no pedir postre pero sí otra copa de vino:
- 1x Copa de Vino Malbec - $6,800

**Total segunda ronda: $24,500**

Lucía envía la ronda #2. El flujo se repite exactamente igual.

---

## Acto 7: Solicitud de Cuenta

### Escena 7.1: Pedir la Cuenta

Terminado el postre, Martín toca "Pedir cuenta" en el menú de la app. El sistema:

1. Crea un registro `Check` con estado "REQUESTED"
2. Calcula los cargos individuales (`Charge`) basados en los `RoundItem` de cada Diner
3. Publica evento `CHECK_REQUESTED` a 3 canales

**Balance por comensal:**
- Martín: $38,800 (ronda 1) + $6,800 (ronda 2) = **$45,600**
- Lucía: $26,100 (ronda 1) + $9,200 (ronda 2) = **$35,300**
- Pedro: $45,300 (ronda 1) + $8,500 (ronda 2) = **$53,800**
- **Total mesa: $134,700**

### Escena 7.2: Notificación al Mozo

Juan recibe la notificación "Cuenta solicitada - Mesa T-02". En su app ve:
- El detalle de consumo por comensal
- El total de la mesa
- Opciones: Efectivo / Mercado Pago

---

## Acto 8: Pago

### Escena 8.1: Opción A - Pago en Efectivo

Si los amigos deciden pagar en efectivo:

1. Juan registra el pago en su app
2. El sistema crea un `Payment` con `method="CASH"`
3. El algoritmo FIFO (`allocate_payment_fifo`) asigna el pago a los cargos más antiguos primero
4. Se publica evento `CHECK_PAID`

### Escena 8.2: Opción B - Pago con Mercado Pago

Si prefieren pagar con tarjeta vía Mercado Pago:

1. Cada comensal puede pagar su parte individualmente
2. El sistema genera una preferencia de pago con el monto correspondiente
3. Se redirige al checkout de Mercado Pago
4. Tras el pago exitoso, el webhook notifica al backend
5. Se publica evento `CHECK_PAID`

---

## Acto 9: Cierre de Mesa

### Escena 9.1: Mesa Libre

Una vez pagada la cuenta completa:

1. El `Check` cambia a estado "PAID"
2. La `TableSession` cambia a estado "CLOSED"
3. La mesa `Table` vuelve a estado "FREE"
4. Se publica evento `TABLE_CLEARED`

**En el celular de Juan:**
- La mesa T-02 desaparece de su lista de mesas activas
- Queda disponible para nuevos comensales

**En el Dashboard:**
- La mesa T-02 se muestra en verde (libre)
- Las estadísticas se actualizan con la venta del día

---

## Resumen Técnico

### Endpoints Utilizados

| Momento | Endpoint | Método |
|---------|----------|--------|
| Crear sesión | `/api/tables/7/session` | POST |
| Registrar comensal | `/api/diner/register` | POST |
| Obtener menú | `/api/public/menu/centro` | GET |
| Enviar ronda | `/api/diner/rounds/submit` | POST |
| Actualizar estado (cocina) | `/api/kitchen/rounds/{id}/status` | PUT |
| Solicitar cuenta | `/api/billing/check/request` | POST |
| Registrar pago | `/api/billing/cash/pay` | POST |

### Eventos WebSocket Publicados

| Evento | Canales |
|--------|---------|
| `ROUND_SUBMITTED` | waiters, kitchen, admin, session |
| `ROUND_IN_KITCHEN` | waiters, kitchen, admin, session |
| `ROUND_READY` | waiters, kitchen, admin, session |
| `ROUND_SERVED` | waiters, kitchen, admin, session |
| `CHECK_REQUESTED` | waiters, admin, session |
| `CHECK_PAID` | waiters, admin, session |
| `TABLE_CLEARED` | waiters, admin |

### Conexiones WebSocket

| Cliente | Endpoint | Autenticación |
|---------|----------|---------------|
| Comensales | `/ws/diner?table_token=...` | Token JWT de mesa |
| Mozo Juan | `/ws/waiter?token=...` | JWT de usuario WAITER |
| Cocina | `/ws/kitchen?token=...` | JWT de usuario KITCHEN |
| Dashboard | `/ws/admin?token=...` | JWT de usuario ADMIN/MANAGER |

---

## URLs para Ejecutar la Prueba

### Comensales (abrir 3 pestañas)
```
http://localhost:5176/centro/7
```

### Mozo Juan
```
http://localhost:5178
Credenciales: waiter@demo.com / waiter123
```

### Cocina
```
http://localhost:5177/kitchen
Credenciales: kitchen@demo.com / kitchen123
```

### Dashboard Admin
```
http://localhost:5177
Credenciales: admin@demo.com / admin123
```

---

## Datos de la Sesión Actual

- **Session ID**: 1
- **Table Token**: `eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJ0ZW5hbnRfaWQiOjEsImJyYW5jaF9pZCI6MSwidGFibGVfaWQiOjcsInNlc3Npb25faWQiOjEsInR5cGUiOiJ0YWJsZSIsImlzcyI6ImludGVncmFkb3I6dGFibGUiLCJhdWQiOiJpbnRlZ3JhZG9yOmRpbmVyIiwiaWF0IjoxNzY4MTQxODk0LCJleHAiOjE3NjgxNzA2OTR9.eb7SqYr1J5vo1EFLSCmZ2Puy8_7-NK5YmcxOO4CDVuI`
- **Mesa**: T-02 (id=7)
- **Sucursal**: Centro (id=1)
- **Sector**: Terraza (id=2)
- **Mozo**: Juan (id=1)
