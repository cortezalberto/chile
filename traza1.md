# Trazabilidad del Pedido: Del QR a la Cocina

## Introducción

Este documento explica en detalle cómo funciona el sistema de pedidos colaborativos cuando varios comensales se sientan en una mesa, escanean el código QR, y realizan sus pedidos. Se enfoca especialmente en los mecanismos de protección contra pedidos duplicados, el flujo de notificaciones hacia cocina y mozos, y cómo el gerente supervisa todo el circuito desde el Dashboard.

---

## 1. El Momento del Escaneo: Unirse a la Mesa

Cuando un comensal escanea el código QR de la mesa, ocurre lo siguiente:

### Primer Comensal
1. El sistema crea una **sesión de mesa** (`TableSession`) en el backend con estado `OPEN`
2. Se genera un **token de mesa** (JWT) que identifica esta sesión específica
3. El comensal queda registrado como **Diner** en el backend con un ID único
4. Se abre una conexión **WebSocket** para recibir actualizaciones en tiempo real
5. El token se guarda en el navegador del comensal

### Comensales Siguientes
1. Al escanear el mismo QR, el sistema detecta que ya existe una sesión activa para esa mesa
2. Se les une a la **misma sesión existente** (no se crea una nueva)
3. Cada comensal recibe su propio **Diner ID** del backend
4. Todos comparten el mismo token de mesa
5. Cada uno abre su propia conexión WebSocket vinculada a la sesión

**Punto clave:** Todos los comensales de una mesa comparten la misma sesión, pero cada uno tiene su identidad única dentro de ella.

---

## 2. El Carrito Compartido: Cómo Funciona

El carrito es **colaborativo pero con identidad**. Esto significa:

### Agregar Productos
- Cada comensal puede agregar productos al carrito compartido
- Cada ítem en el carrito tiene el **ID del comensal que lo agregó** (`dinerId`)
- El nombre del comensal aparece junto a cada producto
- Los comensales ven todos los productos de todos, pero solo pueden modificar los suyos

### Ejemplo Visual
```
Carrito Compartido de Mesa 5:
┌─────────────────────────────────────────────┐
│ 🍕 Pizza Margarita x2        [María]    $800 │
│ 🍝 Ravioles x1               [Juan]     $650 │
│ 🥗 Ensalada César x1         [Pedro]    $450 │
│ 🍺 Cerveza artesanal x3      [María]    $600 │
└─────────────────────────────────────────────┘
                              Total: $2,500
```

### Sincronización entre Dispositivos
- El carrito se sincroniza automáticamente via **localStorage** entre pestañas del mismo navegador
- Entre diferentes dispositivos, la sincronización ocurre cuando se **envía el pedido** al backend
- Cada comensal ve la última versión del carrito antes de confirmar

---

## 3. El Mecanismo Anti-Duplicación de Pedidos

Esta es la parte más crítica del sistema. ¿Cómo evitamos que dos comensales envíen el mismo pedido simultáneamente?

### Nivel 1: Bloqueo en el Frontend (pwaMenu)

Cuando un comensal presiona "Pedir", ocurre inmediatamente:

```typescript
// En submitOrder() - store.ts líneas 483-530

// 1. Verificar si ya hay un envío en proceso
if (state.isSubmitting) {
  return { success: false, error: 'An order is already being submitted' }
}

// 2. Marcar inmediatamente como "enviando"
set({ isSubmitting: true })

// 3. Marcar los ítems del carrito con flag _submitting
const itemsToSubmit = cartItems.map(item => ({ ...item, _submitting: true }))
```

**¿Qué logra esto?**
- Si María presiona "Pedir" y Juan presiona 0.5 segundos después, Juan ve `isSubmitting: true` y su intento es rechazado con el mensaje "An order is already being submitted"
- Los ítems marcados con `_submitting: true` no pueden ser modificados ni eliminados durante el envío

### Nivel 2: Sistema de Rondas en el Backend

El backend organiza los pedidos en **rondas** (`Round`). Cada ronda tiene:

```python
# En diner.py - líneas 207-223

# Obtener el número de ronda siguiente para esta sesión
max_round = db.scalar(
    select(func.max(Round.round_number))
    .where(Round.table_session_id == session_id)
) or 0
next_round_number = max_round + 1

# Crear la ronda con estado SUBMITTED
new_round = Round(
    tenant_id=tenant_id,
    branch_id=branch_id,
    table_session_id=session_id,
    round_number=next_round_number,
    status="SUBMITTED",
    submitted_at=datetime.now(timezone.utc),
)
```

**¿Qué logra esto?**
- Cada envío exitoso crea una nueva ronda con número secuencial (Ronda 1, Ronda 2, etc.)
- Si María envía primero, se crea Ronda 1
- Si Juan agrega algo después y envía, se crea Ronda 2
- Nunca hay duplicación: cada ronda es única

### Nivel 3: Limpieza del Carrito Post-Envío

Después de un envío exitoso:

```typescript
// En submitOrder() - store.ts líneas 639-657

set((currentState) => {
  // Remover SOLO los ítems que fueron marcados como _submitting
  const remainingCart = currentState.session.sharedCart.filter(
    item => !item._submitting
  )

  return {
    orders: [...currentState.orders, newOrder],
    currentRound: roundNumber,
    isSubmitting: false,
    session: {
      ...currentState.session,
      sharedCart: remainingCart  // Carrito vacío o con nuevos ítems
    }
  }
})
```

**¿Qué logra esto?**
- Los ítems enviados desaparecen del carrito
- Si Pedro agregó algo MIENTRAS María enviaba, esos ítems permanecen (no tienen flag `_submitting`)
- Pedro puede entonces enviar su propia ronda

---

## 4. El Flujo Completo: Escenario Realista

Imaginemos esta situación:

**12:30** - María, Juan y Pedro se sientan en Mesa 5 y escanean el QR.

**12:32** - Los tres agregan productos:
- María: Pizza Margarita x2, Cerveza x3
- Juan: Ravioles x1
- Pedro: Ensalada César x1

**12:35** - María presiona "Pedir" primero.

### Lo que sucede en el sistema:

1. **Frontend de María:**
   - `isSubmitting = true` (bloquea nuevos envíos)
   - Los 6 ítems se marcan con `_submitting: true`
   - Se envía POST a `/api/diner/rounds/submit`

2. **Frontend de Juan y Pedro:**
   - Ven el botón "Pedir" deshabilitado o reciben error si intentan
   - Sus pantallas muestran que un envío está en proceso

3. **Backend:**
   - Valida el token de mesa
   - Verifica que la sesión está `OPEN`
   - Crea `Round #1` con los 6 ítems
   - Guarda cada `RoundItem` con precio, cantidad y notas

4. **Publicación de Evento:**
   ```python
   await publish_round_event(
       event_type=ROUND_SUBMITTED,
       tenant_id=tenant_id,
       branch_id=branch_id,
       table_id=table_id,
       session_id=session_id,
       round_id=new_round.id,
       round_number=1,
   )
   ```

5. **Redis distribuye el evento a CUATRO canales:**
   - Canal `branch:{id}:waiters` → Mozos de la sucursal
   - Canal `branch:{id}:kitchen` → Cocina de la sucursal
   - Canal `branch:{id}:admin` → **Dashboard del gerente**
   - Canal `session:{id}` → Los comensales de la mesa (confirmación)

6. **Frontend de María recibe confirmación:**
   - `isSubmitting = false`
   - Carrito se vacía
   - Aparece en historial: "Ronda #1 - Enviado"

---

## 5. El Panel de Cocina: Donde el Cocinero Recibe los Pedidos

La cocina tiene su propia pantalla dedicada a gestionar las comandas. Esta pantalla organiza los pedidos en tres columnas que representan el flujo de trabajo de una cocina profesional:

### Estructura Visual de la Pantalla de Cocina

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                        COCINA - Centro                                       │
├─────────────────────────┬─────────────────────────┬─────────────────────────┤
│      🔴 NUEVOS (2)      │    🟡 EN COCINA (3)     │     🟢 LISTOS (1)       │
├─────────────────────────┼─────────────────────────┼─────────────────────────┤
│ Mesa 5 - Ronda #1       │ Mesa 3 - Ronda #1       │ Mesa 8 - Ronda #2       │
│ 12:35 (hace 2min)       │ 12:28 (hace 9min)       │ 12:20 (hace 17min)      │
│ ─────────────────       │ ─────────────────       │ ─────────────────       │
│ • Pizza Margarita x2    │ • Bife de chorizo x2    │ • Tiramisú x2           │
│ • Ravioles x1           │ • Papas fritas x2       │   [MARCAR SERVIDO]      │
│ • Ensalada César x1     │   [MARCAR LISTO]        │                         │
│   [EMPEZAR]             │                         │                         │
├─────────────────────────┤ Mesa 7 - Ronda #1       │                         │
│ Mesa 12 - Ronda #1      │ 12:30 (hace 7min)       │                         │
│ 12:36 (hace 1min)       │ ─────────────────       │                         │
│ ─────────────────       │ • Milanesa napol. x1    │                         │
│ • Empanadas x6          │ • Ensalada mixta x1     │                         │
│   [EMPEZAR]             │   [MARCAR LISTO]        │                         │
│                         │                         │                         │
│                         │ Mesa 2 - Ronda #2       │                         │
│                         │ 12:33 (hace 4min)       │                         │
│                         │ ─────────────────       │                         │
│                         │ • Postre del día x3     │                         │
│                         │   [MARCAR LISTO]        │                         │
└─────────────────────────┴─────────────────────────┴─────────────────────────┘
```

### El Flujo de Trabajo del Cocinero

1. **Columna "Nuevos"**: Aquí llegan los pedidos recién enviados por los comensales. El cocinero ve la mesa, el número de ronda, hace cuánto llegó, y el detalle de productos. Al presionar **[EMPEZAR]**, el pedido pasa a "En Cocina".

2. **Columna "En Cocina"**: Pedidos que están siendo preparados activamente. El color amarillo indica trabajo en progreso. Al terminar de preparar, el cocinero presiona **[MARCAR LISTO]**.

3. **Columna "Listos"**: Pedidos terminados esperando que el mozo los retire. El color verde indica que están esperando delivery. Cuando el mozo los lleva a la mesa, puede marcarlos como **[SERVIDO]**.

### Notificaciones en Tiempo Real

La pantalla de cocina recibe eventos WebSocket instantáneos:

- **ROUND_SUBMITTED**: Aparece nueva tarjeta en columna "Nuevos" con animación de entrada
- **ROUND_IN_KITCHEN**: Tarjeta se mueve a columna "En Cocina" (si fue marcado desde otra terminal)
- **ROUND_READY**: Tarjeta se mueve a columna "Listos"
- **ROUND_SERVED**: Tarjeta desaparece de la pantalla (pedido completado)

**Punto clave:** El cocinero nunca necesita refrescar la página. Los pedidos aparecen automáticamente apenas el comensal presiona "Pedir".

---

## 6. El Dashboard del Gerente: Control Total del Circuito

Además de la pantalla de cocina física (pwaKitchen) y la aplicación del mozo (pwaWaiter), existe una tercera interfaz crucial: el **Dashboard**. Esta es la herramienta del gerente o administrador del restaurante para supervisar todo el circuito operativo.

### Acceso a la Vista de Cocina desde el Dashboard

En el menú lateral del Dashboard, el ítem **"Cocina"** permite al gerente ver exactamente la misma información que el cocinero:

```
┌────────────────────┐
│ 🍽️ Dashboard       │
├────────────────────┤
│ 📊 Reportes        │
│ 🏪 Sucursales      │
│ 📋 Categorías      │
│ 🍕 Productos       │
│ 👥 Personal        │
│ 🎫 Promociones     │
│ 👨‍🍳 Cocina  ←←←←←← │ ← Acceso al monitor de cocina
│ ⚙️ Configuración   │
└────────────────────┘
```

### ¿Por Qué el Gerente Necesita Esta Vista?

El gerente del restaurante tiene responsabilidades que van más allá de la cocina:

1. **Supervisión del Tiempo de Servicio**: Puede detectar si una ronda lleva demasiado tiempo en "En Cocina" y actuar (reforzar personal, hablar con el chef).

2. **Balanceo de Carga**: Ve cuántos pedidos hay en cada columna. Si hay muchos "Nuevos" y pocos "En Cocina", quizás faltan cocineros.

3. **Atención a Incidentes**: Si una mesa lleva esperando 20 minutos, el gerente puede intervenir proactivamente antes de que el cliente se queje.

4. **Visión Holística**: El gerente ve TODO el restaurante, no solo un sector. Puede comparar tiempos entre sucursales si gestiona varias.

### Conexión WebSocket del Dashboard

El Dashboard se conecta al canal de cocina de la misma forma que la aplicación de cocina:

```typescript
// Dashboard/src/services/websocket.ts
export const dashboardWS = {
  connect: (role: 'kitchen' | 'admin' | 'waiter') => {
    // Se conecta a ws://localhost:8001/ws/{role}?token=JWT
    // Recibe los mismos eventos que el rol especificado
  }
}
```

Cuando el gerente abre la página de Cocina en el Dashboard:
1. Se establece conexión WebSocket con rol `kitchen`
2. Se suscriben a eventos: `ROUND_SUBMITTED`, `ROUND_IN_KITCHEN`, `ROUND_READY`, `ROUND_SERVED`
3. La interfaz se actualiza automáticamente igual que en la cocina física

### El Gerente como Observador Silencioso

A diferencia del cocinero, el gerente típicamente **observa sin intervenir** en el flujo de pedidos. Su rol es monitorear y detectar problemas. Sin embargo, en caso de emergencia, podría:

- Marcar un pedido como "Listo" si el cocinero olvidó hacerlo
- Identificar pedidos atascados y comunicarse con el personal
- Ver patrones (horas pico, productos más pedidos)

---

## 7. El Circuito Completo de Notificaciones

Este diagrama muestra cómo fluyen los eventos a todos los actores del sistema:

```
                              ┌─────────────────────┐
                              │    REDIS PUB/SUB    │
                              │   (Distribuidor)    │
                              └──────────┬──────────┘
                                         │
        ┌────────────────────────────────┼────────────────────────────────┐
        │                                │                                │
        ▼                                ▼                                ▼
┌───────────────┐              ┌───────────────┐              ┌───────────────┐
│branch:1:waiter│              │branch:1:kitchen│             │branch:1:admin │
│   (Mozos)     │              │   (Cocina)     │             │  (Dashboard)  │
└───────┬───────┘              └───────┬───────┘              └───────┬───────┘
        │                              │                              │
        ▼                              ▼                              ▼
┌───────────────┐              ┌───────────────┐              ┌───────────────┐
│   pwaWaiter   │              │   Pantalla    │              │   Dashboard   │
│ (Mozo móvil)  │              │   Cocina      │              │   (Gerente)   │
└───────────────┘              └───────────────┘              └───────────────┘

        │                              │                              │
        │                              │                              │
        ▼                              ▼                              ▼
   Notificación               Tarjeta nueva               Mismo monitor
   en el celular              en columna                  que cocina
   del mozo                   "Nuevos"                    para supervisión
```

### Eventos y Sus Destinatarios

| Evento | Mozos | Cocina | Dashboard | Comensales |
|--------|-------|--------|-----------|------------|
| ROUND_SUBMITTED | ✅ | ✅ | ✅ | - |
| ROUND_IN_KITCHEN | ✅ | ✅ | ✅ | ✅ |
| ROUND_READY | ✅ | ✅ | ✅ | ✅ |
| ROUND_SERVED | ✅ | ✅ | ✅ | ✅ |
| SERVICE_CALL_CREATED | ✅ | - | ✅ | - |
| CHECK_REQUESTED | ✅ | - | ✅ | - |
| CHECK_PAID | ✅ | - | ✅ | ✅ |

**Punto clave:** El gerente en el Dashboard recibe TODO lo que reciben mozos y cocina, permitiéndole tener una visión 360° del restaurante.

---

## 8. Notificaciones al Personal

### A. Notificación a la Cocina

La cocina tiene una pantalla con todos los pedidos pendientes:

```
GET /api/kitchen/rounds
→ Retorna rondas con status SUBMITTED o IN_KITCHEN
```

Cuando la cocina actualiza el estado:

```python
# POST /api/kitchen/rounds/{round_id}/status
# Body: { "status": "IN_KITCHEN" }

# Transiciones válidas:
# SUBMITTED → IN_KITCHEN (cocina empieza a preparar)
# IN_KITCHEN → READY (cocina terminó)
# READY → SERVED (mozo entregó)
```

### B. Notificación a los Mozos

Los mozos reciben notificaciones en tiempo real via WebSocket:

**Eventos que reciben:**
- `ROUND_SUBMITTED` - Nueva ronda para su sector
- `ROUND_READY` - Pedido listo para llevar a la mesa
- `SERVICE_CALL_CREATED` - Cliente llamó al mozo
- `CHECK_REQUESTED` - Cliente pidió la cuenta

**Si el mozo está asignado a un sector específico:**
- Solo recibe eventos de mesas en SU sector
- Evita sobrecarga de notificaciones irrelevantes

### C. Notificación a los Comensales

Los comensales en pwaMenu reciben actualizaciones via WebSocket:

```
┌─────────────────────────────────────────────────────┐
│ Tu Pedido - Mesa 5                                  │
├─────────────────────────────────────────────────────┤
│ Ronda #1                                            │
│ ⏳ Pizza Margarita x2 .......... En preparación    │
│ ✅ Ravioles x1 ................. ¡Listo!           │
│ ⏳ Ensalada César x1 ........... En preparación    │
│ 🍺 Cerveza artesanal x3 ........ Entregado         │
└─────────────────────────────────────────────────────┘
```

---

## 9. La Segunda Ronda: Cuando Pedro Quiere Más

**12:50** - Pedro quiere pedir un postre.

1. Pedro agrega "Tiramisú x1" al carrito
2. El carrito ahora tiene solo 1 ítem (los anteriores ya fueron enviados)
3. Pedro presiona "Pedir"
4. Se crea `Ronda #2` solo con el tiramisú
5. Cocina recibe notificación de nueva ronda
6. El mozo ve que Mesa 5 tiene un nuevo pedido
7. **El gerente en el Dashboard también ve la nueva ronda aparecer**

**Punto clave:** Cada ronda es independiente. Pedro no duplica lo que María ya envió.

---

## 10. Cierre de Mesa: Pedir la Cuenta

Cuando los comensales terminan:

1. Alguien presiona "Pedir Cuenta"
2. El sistema verifica:
   - ¿Hay ítems en el carrito sin enviar? → Error, primero deben enviarse
   - ¿Hay rondas registradas? → Sí, proceder
3. Se crea un `Check` (cuenta) con el total de todas las rondas
4. La sesión pasa a estado `PAYING`
5. El mozo recibe notificación `CHECK_REQUESTED`
6. **El gerente ve el cambio de estado de la mesa en el Dashboard**

---

## 11. Flujo Visual Completo

```
┌──────────────┐     ┌──────────────┐     ┌──────────────┐     ┌──────────────┐
│   COMENSAL   │     │   BACKEND    │     │   PERSONAL   │     │   GERENTE    │
│   (pwaMenu)  │     │   (FastAPI)  │     │   (pwaWaiter)│     │  (Dashboard) │
└──────┬───────┘     └──────┬───────┘     └──────┬───────┘     └──────┬───────┘
       │                    │                    │                    │
       │ Escanea QR         │                    │                    │
       │───────────────────>│                    │                    │
       │                    │                    │                    │
       │   Token + Session  │                    │                    │
       │<───────────────────│                    │                    │
       │                    │                    │                    │
       │ Agrega al carrito  │                    │                    │
       │ (local)            │                    │                    │
       │                    │                    │                    │
       │ Presiona PEDIR     │                    │                    │
       │───────────────────>│                    │                    │
       │  isSubmitting=true │                    │                    │
       │                    │ Crear Round        │                    │
       │                    │                    │                    │
       │                    │ Publicar evento    │                    │
       │                    │────────────────────>────────────────────>
       │                    │   ROUND_SUBMITTED  │   ROUND_SUBMITTED  │
       │                    │                    │                    │
       │  Ronda confirmada  │                    │ Notificación       │ Tarjeta nueva
       │<───────────────────│                    │ en pantalla        │ en monitor
       │  isSubmitting=false│                    │                    │
       │  Carrito vacío     │                    │                    │
       │                    │                    │                    │
       │                    │                    │ Cocina cambia      │
       │                    │<────────────────────  status            │
       │                    │                    │                    │
       │  ROUND_IN_KITCHEN  │                    │                    │ Actualiza
       │<───────────────────│────────────────────>────────────────────> columna
       │  "En preparación"  │                    │                    │
       │                    │                    │                    │
       │  ROUND_READY       │                    │                    │
       │<───────────────────│────────────────────>────────────────────>
       │  "¡Listo!"         │                    │ Notif: retirar     │ Columna
       │                    │                    │ pedido de cocina   │ "Listos"
       │                    │                    │                    │
       │                    │                    │ Mozo entrega       │
       │  ROUND_SERVED      │<────────────────────  marca SERVED      │
       │<───────────────────│────────────────────>────────────────────>
       │  "Entregado"       │                    │                    │ Tarjeta
       │                    │                    │                    │ desaparece
       │                    │                    │                    │
```

---

## 12. Resumen de Protecciones

| Problema | Solución |
|----------|----------|
| Dos comensales presionan "Pedir" al mismo tiempo | Flag `isSubmitting` bloquea el segundo intento |
| Ítems se pierden durante el envío | Flag `_submitting` los protege hasta confirmación |
| Alguien agrega mientras otro envía | Nuevos ítems no tienen flag, quedan para siguiente ronda |
| Pedido duplicado al backend | Rondas numeradas secuencialmente, cada una única |
| Enviar carrito vacío | Validación previa: "Cart is empty" |
| Productos ya no disponibles | Validación contra menú antes de enviar |
| Gerente no ve lo que pasa | Dashboard recibe mismos eventos que cocina y mozos |

---

## 13. Conclusión

El sistema está diseñado para que:

1. **Múltiples comensales puedan agregar al mismo carrito** sin pisarse
2. **Solo uno pueda enviar a la vez**, evitando duplicaciones
3. **Cada envío crea una ronda nueva**, manteniendo trazabilidad completa
4. **Cocina y mozos reciben notificaciones instantáneas** via WebSocket
5. **Los comensales ven el progreso** de su pedido en tiempo real
6. **El gerente supervisa todo el circuito** desde el Dashboard, pudiendo intervenir si detecta problemas

El flujo respeta el modelo mental de un restaurante real: las personas agregan lo que quieren, alguien "cierra la comanda" enviándola a cocina, y todos ven cuando está lista para servir. El gerente, como director de orquesta, observa el flujo completo desde su panel de control, asegurando que el servicio fluya sin contratiempos.
