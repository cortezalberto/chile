# WebSocket Gateway

Este documento describe la arquitectura, diseño y funcionamiento del WebSocket Gateway de Integrador, el sistema de notificaciones en tiempo real que conecta las aplicaciones cliente con los eventos del backend.

---

## Visión General

El WebSocket Gateway constituye el componente de comunicación en tiempo real del sistema Integrador, proporcionando una capa de distribución de eventos que conecta el backend REST API con las aplicaciones cliente. Diseñado como un servicio independiente que escucha en el puerto 8001, el gateway se suscribe a canales Redis donde el backend publica eventos, y los redistribuye a los clientes WebSocket conectados según su rol, sucursal y sector.

La arquitectura enfatiza la modularidad mediante un patrón de composición que descompone las responsabilidades en componentes especializados. Esta aproximación permite que el sistema maneje entre 400 y 600 usuarios concurrentes con latencias de broadcast inferiores a 200ms, manteniendo el código organizado en módulos que pueden evolucionar independientemente.

El gateway implementa aislamiento multi-tenant estricto, asegurando que los eventos de un restaurante nunca lleguen a clientes de otro. Cada conexión WebSocket se registra con su tenant_id, y todos los broadcasts filtran por este identificador antes de enviar.

---

## Inicio Rápido

### Prerrequisitos

El WebSocket Gateway requiere que el backend esté configurado y que Redis esté ejecutándose. Desde la raíz del proyecto:

```bash
# Iniciar infraestructura (PostgreSQL + Redis)
docker compose -f devOps/docker-compose.yml up -d
```

### Ejecución

El gateway necesita acceso a los módulos del backend, por lo que debe configurarse PYTHONPATH:

```bash
# Unix/Mac
export PYTHONPATH="$(pwd)/backend"
python -m uvicorn ws_gateway.main:app --reload --port 8001

# Windows PowerShell
$env:PYTHONPATH = "$PWD\backend"
python -m uvicorn ws_gateway.main:app --reload --port 8001

# O usar el script de inicio que configura todo automáticamente
.\devOps\start.ps1
```

### Verificación

```bash
# Health check básico
curl http://localhost:8001/ws/health

# Health check detallado (incluye estado de Redis)
curl http://localhost:8001/ws/health/detailed

# Métricas Prometheus
curl http://localhost:8001/ws/metrics
```

### Conexión WebSocket

```javascript
// Mesero (requiere JWT)
const ws = new WebSocket('ws://localhost:8001/ws/waiter?token=JWT_TOKEN');

// Cocina (requiere JWT)
const ws = new WebSocket('ws://localhost:8001/ws/kitchen?token=JWT_TOKEN');

// Admin (requiere JWT)
const ws = new WebSocket('ws://localhost:8001/ws/admin?token=JWT_TOKEN');

// Comensal (requiere Table Token)
const ws = new WebSocket('ws://localhost:8001/ws/diner?table_token=TABLE_TOKEN');
```

---

## Arquitectura

### Filosofía de Diseño

El gateway implementa un patrón de composición donde los componentes principales actúan como orquestadores delgados que delegan a módulos especializados. Esta aproximación surgió de una refactorización que redujo archivos monolíticos de 900+ líneas a orquestadores de menos de 500 líneas, extrayendo la lógica en módulos cohesivos con responsabilidades únicas.

```
                     Redis Pub/Sub
                          │
                          ▼
┌─────────────────────────────────────────────────────────────────┐
│                    Redis Subscriber                              │
│              (Thin Orchestrator - 326 lines)                     │
│                          │                                       │
│         ┌────────────────┼────────────────┐                     │
│         ▼                ▼                ▼                     │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐             │
│  │DropTracker  │  │  Validator  │  │  Processor  │             │
│  │             │  │             │  │             │             │
│  │ Drop rate   │  │ Schema      │  │ Batch       │             │
│  │ monitoring  │  │ validation  │  │ processing  │             │
│  └─────────────┘  └─────────────┘  └─────────────┘             │
└─────────────────────────────────────────────────────────────────┘
                          │
                          ▼
┌─────────────────────────────────────────────────────────────────┐
│                   Connection Manager                             │
│              (Thin Orchestrator - 463 lines)                     │
│                          │                                       │
│    ┌──────────┬──────────┼──────────┬──────────┐               │
│    ▼          ▼          ▼          ▼          ▼               │
│ ┌──────┐ ┌──────┐ ┌──────────┐ ┌──────┐ ┌──────────┐          │
│ │Life- │ │Broad-│ │Connection│ │Clean-│ │  Stats   │          │
│ │cycle │ │caster│ │  Index   │ │  up  │ │          │          │
│ └──────┘ └──────┘ └──────────┘ └──────┘ └──────────┘          │
└─────────────────────────────────────────────────────────────────┘
                          │
                          ▼
                  WebSocket Clients
           (Waiter, Kitchen, Admin, Diner)
```

### Estructura del Proyecto

```
ws_gateway/
├── main.py                         # Punto de entrada FastAPI
├── connection_manager.py           # Orquestador de conexiones
├── redis_subscriber.py             # Orquestador de suscripción Redis
│
├── core/                           # Módulos extraídos (ARCH-MODULAR)
│   ├── connection/                 # Gestión de conexiones
│   │   ├── lifecycle.py            # Aceptar/desconectar
│   │   ├── broadcaster.py          # Envío a conexiones
│   │   ├── cleanup.py              # Limpieza de conexiones
│   │   └── stats.py                # Estadísticas
│   │
│   └── subscriber/                 # Procesamiento de eventos
│       ├── drop_tracker.py         # Monitoreo de drops
│       ├── validator.py            # Validación de esquema
│       └── processor.py            # Procesamiento por lotes
│
└── components/                     # Componentes modulares
    ├── core/                       # Fundamentales
    │   ├── constants.py            # WSCloseCode, WSConstants
    │   ├── context.py              # WebSocketContext
    │   └── dependencies.py         # Inyección de dependencias
    │
    ├── connection/                 # Lifecycle de conexiones
    │   ├── index.py                # Índices multi-dimensionales
    │   ├── locks.py                # Locks fragmentados
    │   ├── heartbeat.py            # Detección de stale
    │   └── rate_limiter.py         # Rate limiting
    │
    ├── events/                     # Manejo de eventos
    │   ├── types.py                # WebSocketEvent, EventType
    │   └── router.py               # Enrutamiento de eventos
    │
    ├── broadcast/                  # Broadcasting
    │   ├── router.py               # Estrategias de broadcast
    │   └── tenant_filter.py        # Filtrado multi-tenant
    │
    ├── auth/                       # Autenticación
    │   └── strategies.py           # JWT, TableToken, Composite
    │
    ├── endpoints/                  # Endpoints WebSocket
    │   ├── base.py                 # Clase base abstracta
    │   ├── mixins.py               # Mixins de funcionalidad
    │   └── handlers.py             # Implementaciones concretas
    │
    ├── resilience/                 # Tolerancia a fallos
    │   ├── circuit_breaker.py      # Circuit breaker
    │   └── retry.py                # Retry con jitter
    │
    ├── metrics/                    # Observabilidad
    │   ├── collector.py            # Colector de métricas
    │   └── prometheus.py           # Formato Prometheus
    │
    └── data/                       # Acceso a datos
        └── sector_repository.py    # Asignaciones de sector
```

---

## Componentes Principales

### Connection Manager

El Connection Manager actúa como fachada principal para la gestión de conexiones WebSocket. Implementa el patrón de composición, delegando cada responsabilidad a un componente especializado mientras expone una API unificada.

**ConnectionLifecycle** maneja la aceptación y desconexión de conexiones. Al aceptar una conexión, valida límites (máximo 3 conexiones por usuario, 1000 totales), registra en los índices correspondientes y configura el tracking de heartbeat. La desconexión libera todos los recursos asociados de forma atómica.

**ConnectionBroadcaster** implementa el envío de mensajes con optimizaciones para alto volumen. Los broadcasts se ejecutan en lotes paralelos de 50 conexiones usando `asyncio.gather()`, lo que reduce el tiempo de broadcast a 400 usuarios de ~4 segundos a ~160ms. Las conexiones que fallan durante el envío se marcan como "muertas" para limpieza asíncrona posterior.

**ConnectionIndex** mantiene índices multi-dimensionales que permiten búsquedas O(1) por usuario, sucursal, sector, sesión y rol admin. Utiliza `MappingProxyType` para exponer vistas inmutables que previenen modificaciones accidentales desde código externo.

**ConnectionCleanup** detecta y elimina conexiones problemáticas. Las conexiones "stale" (sin heartbeat por 60 segundos) y "dead" (fallaron durante envío) se limpian en ciclos periódicos usando un patrón de dos fases que previene errores de "dictionary changed size during iteration".

**ConnectionStats** agrega estadísticas de conexión para health checks y métricas Prometheus, incluyendo conteos por usuario, sucursal y sector, así como estado de locks y rate limiters.

### Redis Subscriber

El Redis Subscriber gestiona la suscripción a canales Redis y el procesamiento de eventos entrantes. La arquitectura incorpora múltiples mecanismos de resiliencia para manejar fallos de Redis y backpressure.

**Event Queue** implementa un buffer de backpressure con capacidad configurable (5000 eventos por defecto). Cuando la cola alcanza capacidad, los eventos más antiguos se descartan automáticamente mediante un deque con maxlen, manteniendo los eventos más recientes.

**Drop Tracker** monitorea la tasa de eventos descartados usando una ventana deslizante de 60 segundos. Cuando la tasa supera el 5%, emite alertas con cooldown de 5 minutos para evitar spam de logs mientras mantiene visibilidad del problema.

**Validator** verifica el esquema de cada evento antes de encolarlo. Valida campos requeridos (type, tenant_id, branch_id) y opcionales, rechazando eventos malformados con logging para diagnóstico.

**Processor** consume eventos de la cola en lotes de 50, invocando el callback de routing para cada uno. Implementa timeout de 30 segundos por callback y retry con re-encolado para eventos que fallan temporalmente.

**Circuit Breaker** protege contra cascadas de fallos cuando Redis no está disponible. Después de 5 fallos consecutivos, el circuito se abre y las operaciones fallan inmediatamente durante 30 segundos. Un estado half-open permite probar la recuperación gradualmente.

---

## Patrones de Diseño

### Strategy Pattern (Autenticación)

El sistema de autenticación implementa Strategy para soportar múltiples mecanismos de forma pluggable:

```python
# Estrategias disponibles
JWTAuthStrategy       # Para usuarios autenticados (Dashboard, pwaWaiter)
TableTokenAuthStrategy # Para comensales (pwaMenu)
CompositeAuthStrategy  # Combina múltiples estrategias
NullAuthStrategy       # Para testing (siempre exitoso)
```

Cada estrategia implementa un método `authenticate()` que retorna un `AuthResult` con los claims extraídos o un mensaje de error. Los endpoints seleccionan la estrategia apropiada según su tipo de cliente.

### Template Method (Endpoints)

Los endpoints WebSocket heredan de `WebSocketEndpointBase`, que define el esqueleto del ciclo de vida de conexión:

```python
class WebSocketEndpointBase:
    async def run(self):
        # 1. Validar autenticación
        auth_result = await self.validate_auth()
        if not auth_result.success:
            await self.close_with_error(auth_result.error)
            return

        # 2. Crear contexto
        context = await self.get_context(auth_result.claims)

        # 3. Registrar conexión
        await self.register_connection(context)

        try:
            # 4. Loop de mensajes
            await self.message_loop()
        finally:
            # 5. Desregistrar conexión
            await self.unregister_connection(context)
```

Las subclases implementan los métodos abstractos específicos para cada tipo de endpoint mientras reutilizan el flujo común.

### Observer Pattern (Métricas)

El sistema de broadcasting notifica a observadores sobre el resultado de cada operación, desacoplando la recolección de métricas de la lógica de envío:

```python
class BroadcastObserver(Protocol):
    def on_broadcast_complete(self, sent: int, failed: int, context: str) -> None: ...
    def on_broadcast_rate_limited(self, context: str) -> None: ...

# Uso
router = BroadcastRouter()
router.add_observer(MetricsObserverAdapter(metrics_collector))
```

### Circuit Breaker (Resiliencia)

El circuit breaker implementa tres estados para manejar fallos de Redis:

```
┌─────────┐     5 fallos     ┌─────────┐     30s timeout    ┌───────────┐
│ CLOSED  │─────────────────▶│  OPEN   │──────────────────▶│ HALF_OPEN │
│ (normal)│                  │ (falla  │                    │ (prueba)  │
│         │◀─────────────────│ rápido) │◀───────────────────│           │
└─────────┘    éxito         └─────────┘    fallo           └───────────┘
```

Durante el estado OPEN, las operaciones fallan inmediatamente sin intentar conectar a Redis, previniendo acumulación de timeouts. El estado HALF_OPEN permite un número limitado de operaciones de prueba para detectar recuperación.

### Sharded Locks (Concurrencia)

Los locks fragmentados por sucursal reducen la contención en escenarios de alta concurrencia:

```python
class LockManager:
    # Lock global solo para operaciones cross-cutting
    _connection_counter_lock: asyncio.Lock

    # Locks por entidad reducen contención 90%
    _branch_locks: dict[int, asyncio.Lock]
    _user_locks: dict[int, asyncio.Lock]

    # Locks globales para índices compartidos
    _sector_lock: asyncio.Lock
    _session_lock: asyncio.Lock
```

Cuando un broadcast va a la sucursal 1, solo adquiere el lock de esa sucursal. Otras sucursales pueden operar en paralelo sin bloqueo.

---

## Endpoints WebSocket

### Waiter Endpoint (`/ws/waiter`)

El endpoint de meseros implementa filtrado por sector, asegurando que cada mesero solo reciba eventos de las mesas que tiene asignadas para el día actual.

**Autenticación**: JWT con roles WAITER, MANAGER o ADMIN.

**Eventos recibidos**:
- `ROUND_SUBMITTED`: Nueva ronda de pedidos (si sector_id coincide o es manager/admin)
- `SERVICE_CALL_CREATED`: Llamada de servicio de mesa
- `TABLE_SESSION_STARTED`: Nueva sesión en mesa asignada
- Eventos de administración para managers/admins

**Comando especial**: `refresh_sectors` recarga las asignaciones de sector desde la base de datos.

### Kitchen Endpoint (`/ws/kitchen`)

El endpoint de cocina recibe eventos relacionados con la preparación de pedidos.

**Autenticación**: JWT con roles KITCHEN, MANAGER o ADMIN.

**Eventos recibidos**:
- `ROUND_IN_KITCHEN`: Ronda enviada a cocina para preparación
- `ROUND_READY`: Ronda lista (confirmación)
- `TICKET_*`: Eventos de tickets de cocina

**Nota importante**: `ROUND_SUBMITTED` NO se envía a cocina. Los pedidos primero pasan por Dashboard donde un admin los aprueba y envía a cocina.

### Admin Endpoint (`/ws/admin`)

El endpoint administrativo recibe todos los eventos de las sucursales asignadas al usuario.

**Autenticación**: JWT con roles MANAGER o ADMIN.

**Eventos recibidos**: Todos los eventos de sus sucursales:
- Eventos de rondas (SUBMITTED, IN_KITCHEN, READY, SERVED)
- Eventos de servicio (SERVICE_CALL_*)
- Eventos de sesión (TABLE_SESSION_*, TABLE_CLEARED)
- Eventos CRUD (ENTITY_CREATED, ENTITY_UPDATED, ENTITY_DELETED)

### Diner Endpoint (`/ws/diner`)

El endpoint de comensales permite a los clientes del restaurante recibir actualizaciones de su sesión de mesa.

**Autenticación**: Table Token (HMAC) sin validación de origen (soporta apps móviles).

**Eventos recibidos**:
- `ROUND_*`: Estado de sus pedidos
- `CHECK_REQUESTED`: Cuenta solicitada
- `PAYMENT_*`: Estado de pagos

---

## Sistema de Eventos

### Tipos de Eventos

El gateway reconoce y enruta los siguientes tipos de eventos:

**Ciclo de Ronda**:
- `ROUND_SUBMITTED`: Pedido creado desde pwaMenu/waiter
- `ROUND_IN_KITCHEN`: Pedido aprobado y enviado a cocina
- `ROUND_READY`: Cocina terminó preparación
- `ROUND_SERVED`: Pedido entregado a mesa
- `ROUND_CANCELED`: Pedido cancelado

**Llamadas de Servicio**:
- `SERVICE_CALL_CREATED`: Cliente solicita atención
- `SERVICE_CALL_ACKED`: Mesero en camino
- `SERVICE_CALL_CLOSED`: Atención completada

**Facturación**:
- `CHECK_REQUESTED`: Cliente solicita cuenta
- `CHECK_PAID`: Cuenta pagada completamente
- `PAYMENT_APPROVED`: Pago individual aprobado
- `PAYMENT_REJECTED`: Pago rechazado
- `PAYMENT_FAILED`: Error en procesamiento

**Mesas**:
- `TABLE_SESSION_STARTED`: QR escaneado, sesión creada
- `TABLE_CLEARED`: Mesa liberada
- `TABLE_STATUS_CHANGED`: Cambio de estado

**Tickets de Cocina**:
- `TICKET_IN_PROGRESS`: Cocina preparando
- `TICKET_READY`: Listo para servir
- `TICKET_DELIVERED`: Entregado

**CRUD Administrativo**:
- `ENTITY_CREATED`: Entidad creada
- `ENTITY_UPDATED`: Entidad modificada
- `ENTITY_DELETED`: Entidad eliminada
- `CASCADE_DELETE`: Eliminación en cascada

### Enrutamiento de Eventos

El `EventRouter` determina a qué conexiones enviar cada evento basándose en sus campos:

```python
async def route_event(self, event: dict) -> None:
    tenant_id = event.get("tenant_id")
    branch_id = event.get("branch_id")
    sector_id = event.get("sector_id")
    session_id = event.get("session_id")

    # Siempre filtrar por tenant
    if tenant_id is None:
        return

    # Evento de sesión → comensales de esa mesa
    if session_id:
        await self.manager.send_to_session(session_id, event, tenant_id)

    # Evento con sector → solo meseros de ese sector
    if sector_id:
        await self.manager.send_to_sector(sector_id, event, tenant_id)
    else:
        # Sin sector → todos los meseros de la sucursal
        await self.manager.send_to_branch(branch_id, event, tenant_id)

    # Siempre notificar a admins
    await self.manager.send_to_admins(branch_id, event, tenant_id)
```

### Canales Redis

El gateway se suscribe a patrones de canales que el backend utiliza para publicar:

```
channel:branch:{branch_id}:waiters   # Eventos para meseros
channel:branch:{branch_id}:kitchen   # Eventos para cocina
channel:branch:{branch_id}:admin     # Eventos para dashboard
channel:sector:{branch_id}:{sector_id}:waiters  # Eventos específicos de sector
channel:session:{session_id}         # Eventos para comensales
```

---

## Seguridad

### Autenticación JWT

Las conexiones de usuarios autenticados (meseros, cocina, admins) utilizan JWT con los siguientes claims:

```json
{
  "sub": "123",                    // user_id
  "email": "waiter@demo.com",
  "tenant_id": 1,
  "branch_ids": [1, 2, 3],
  "roles": ["WAITER"],
  "sector_ids": [5, 6]             // Solo para meseros
}
```

**Revalidación periódica**: Cada 5 minutos, el gateway verifica que el token no esté en la blacklist de Redis. Esto detecta logouts y revocaciones sin esperar a la expiración natural del token.

### Autenticación Table Token

Los comensales utilizan tokens HMAC que identifican su sesión de mesa:

```json
{
  "session_id": 456,
  "table_id": 10,
  "branch_id": 1,
  "tenant_id": 1
}
```

Estos tokens tienen validez de 3 horas y no requieren validación de origen para soportar apps móviles que no envían headers de origen consistentes.

### Validación de Origen

Los endpoints JWT validan el header `Origin` contra una lista de orígenes permitidos para prevenir ataques CSRF sobre WebSocket. Los orígenes se configuran via `ALLOWED_ORIGINS` en el entorno.

### Códigos de Cierre

El gateway utiliza códigos de cierre específicos para comunicar la razón de desconexión:

| Código | Constante | Significado |
|--------|-----------|-------------|
| 1000 | NORMAL | Cierre normal |
| 1001 | GOING_AWAY | Servidor apagándose |
| 1008 | POLICY_VIOLATION | Origen no permitido |
| 1009 | MESSAGE_TOO_BIG | Mensaje excede 64KB |
| 1013 | SERVER_OVERLOADED | Límite de conexiones alcanzado |
| 4001 | AUTH_FAILED | Token inválido o expirado |
| 4003 | FORBIDDEN | Rol insuficiente u origen inválido |
| 4029 | RATE_LIMITED | Exceso de mensajes por segundo |

---

## Heartbeat y Detección de Stale

### Protocolo de Heartbeat

El cliente debe enviar pings periódicos para mantener la conexión activa:

```javascript
// Cliente envía cada 30 segundos
ws.send(JSON.stringify({ type: "ping" }));

// Gateway responde
// { "type": "pong" }
```

El gateway también acepta el formato string simple:
```javascript
ws.send("ping");
```

### Detección de Conexiones Stale

Las conexiones que no envían heartbeat durante 60 segundos se consideran stale y se cierran automáticamente. Un task periódico cada 30 segundos identifica y limpia estas conexiones.

### Detección de Conexiones Dead

Durante el envío de mensajes, si una conexión falla (WebSocketDisconnect, ConnectionClosed), se marca como "dead" en lugar de interrumpir el broadcast. Un proceso separado limpia estas conexiones periódicamente sin bloquear operaciones activas.

---

## Rate Limiting

### Límites por Conexión

Cada conexión WebSocket tiene un límite de 20 mensajes por segundo implementado con un algoritmo de ventana deslizante. Exceder este límite resulta en cierre con código 4029.

```python
class WebSocketRateLimiter:
    max_messages: int = 20      # Mensajes permitidos
    window_seconds: float = 1.0  # Ventana de tiempo
```

### Límites de Broadcast

El broadcaster implementa rate limiting global para prevenir tormentas de eventos:

```python
MAX_BROADCASTS_PER_SECOND = 10  # Broadcasts globales
BROADCAST_RATE_LIMIT_WINDOW = 1.0
```

### Evicción de Tracking

El rate limiter mantiene tracking para hasta 2000 conexiones. Al alcanzar capacidad, evicta el 10% de las entradas más antiguas para mantener operación fluida sin pausas de limpieza completa.

---

## Optimización de Rendimiento

### Broadcast Paralelo

Los broadcasts utilizan `asyncio.gather()` con lotes de 50 conexiones:

```python
async def _broadcast_to_connections(self, connections, payload):
    batch_size = 50
    for i in range(0, len(connections), batch_size):
        batch = connections[i:i + batch_size]
        await asyncio.gather(
            *[self._send_to_connection(ws, payload) for ws in batch],
            return_exceptions=True,
        )
```

Esta optimización reduce el tiempo de broadcast a 400 usuarios de ~4s a ~160ms.

### Locks Fragmentados

La contención de locks se reduce 90% mediante fragmentación:

- **Sin fragmentación**: Un lock global serializa todas las operaciones
- **Con fragmentación**: Locks por sucursal permiten operaciones paralelas en diferentes sucursales

### Índices de Conexión

Los índices permiten búsquedas O(1) por cualquier dimensión:

```python
class ConnectionIndex:
    by_user: dict[int, set[WebSocket]]
    by_branch: dict[int, set[WebSocket]]
    by_sector: dict[int, set[WebSocket]]
    by_session: dict[int, set[WebSocket]]
    admins_by_branch: dict[int, set[WebSocket]]
    kitchen_by_branch: dict[int, set[WebSocket]]

```

### Cache de Sectores

Las asignaciones de sector (qué mesero atiende qué sector) se cachean con TTL de 5 minutos para evitar queries repetidas a la base de datos durante el routing de eventos.

---

## Monitoreo y Observabilidad

### Health Checks

**Básico** (`/ws/health`):
```json
{
  "status": "healthy",
  "connections": {
    "total": 42,
    "by_endpoint": {
      "waiter": 20,
      "kitchen": 5,
      "admin": 2,
      "diner": 15
    }
  }
}
```

**Detallado** (`/ws/health/detailed`):
```json
{
  "status": "healthy",
  "redis_async": { "status": "connected", "pool_size": 50 },
  "redis_sync": { "status": "connected", "pool_size": 20 },
  "circuit_breaker": { "state": "CLOSED", "failures": 0 },
  "connections": { ... },
  "rate_limiter": { "tracked_connections": 42 }
}
```

### Métricas Prometheus

El endpoint `/ws/metrics` expone métricas en formato Prometheus:

```
# Conexiones
wsgateway_connections_total 42
wsgateway_connections_by_endpoint{endpoint="waiter"} 20
wsgateway_connections_rejected_total{reason="auth"} 5
wsgateway_connections_rejected_total{reason="rate_limit"} 2

# Broadcasts
wsgateway_broadcasts_total 1234
wsgateway_broadcasts_failed_total 12
wsgateway_broadcast_duration_seconds_sum 45.2

# Eventos
wsgateway_events_processed_total 5678
wsgateway_events_dropped_total 23

# Circuit Breaker
wsgateway_circuit_breaker_state{name="redis"} 0
```

### Logging

El gateway utiliza logging estructurado con contexto de auditoría:

```python
logger.info(
    "Connection established",
    user_id=context.user_id,
    tenant_id=context.tenant_id,
    branch_ids=context.branch_ids,
    endpoint="/ws/waiter",
)
```

---

## Integración con Backend

### Publicación de Eventos

El backend publica eventos usando el módulo `shared.infrastructure.events`:

```python
from shared.infrastructure.events import publish_event, ROUND_SUBMITTED

await publish_event(
    redis_pool,
    f"channel:branch:{branch_id}:waiters",
    {
        "type": ROUND_SUBMITTED,
        "tenant_id": tenant_id,
        "branch_id": branch_id,
        "sector_id": sector_id,
        "round_id": round.id,
        "data": {...}
    }
)
```

### Módulos Compartidos

El gateway importa módulos del backend para funcionalidad común:

```python
# Configuración
from shared.config.settings import settings
from shared.config.logging import get_logger

# Seguridad
from shared.security.auth import verify_jwt, verify_table_token

# Infraestructura
from shared.infrastructure.events import get_redis_pool
from shared.infrastructure.db import get_db
```

### Base de Datos

El gateway accede a la base de datos solo para consultar asignaciones de sector (qué mesero está asignado a qué sector hoy). Esta información se cachea para minimizar queries.

---

## Testing

### Inyección de Dependencias

El sistema soporta inyección de mocks para testing:

```python
from ws_gateway.components import reset_singletons, ConnectionManagerDependencies

# Inyectar mocks
mock_deps = ConnectionManagerDependencies(
    metrics=MockMetricsCollector(),
    rate_limiter=MockRateLimiter(),
)
manager = ConnectionManager(deps=mock_deps)

# Limpiar singletons entre tests
reset_singletons()
```

### NullAuthStrategy

Para testing sin backend:

```python
from ws_gateway.components.auth import NullAuthStrategy

# Siempre autentica exitosamente con datos mock
auth = NullAuthStrategy(mock_data={
    "sub": "1",
    "tenant_id": 1,
    "branch_ids": [1],
    "roles": ["ADMIN"]
})
```

---

## Ciclo de Vida

### Startup

```python
@asynccontextmanager
async def lifespan(app: FastAPI):
    # 1. Configurar logging
    setup_logging()

    # 2. Iniciar suscriptor Redis
    subscriber_task = asyncio.create_task(
        run_subscriber(channels, manager.route_event)
    )

    # 3. Iniciar limpieza de heartbeat
    cleanup_task = asyncio.create_task(
        periodic_cleanup(manager)
    )

    yield  # Aplicación corriendo

    # Shutdown (ver abajo)
```

### Shutdown

```python
    # 4. Cancelar tasks
    subscriber_task.cancel()
    cleanup_task.cancel()

    # 5. Esperar limpieza de locks
    await manager._lock_manager.cleanup_locks()

    # 6. Limpiar repositorio de sectores
    cleanup_sector_repository()

    # 7. Cerrar pools de Redis
    redis_pool = await get_redis_pool()
    await redis_pool.close()

    # 8. Cerrar conexiones con código GOING_AWAY
    await manager.shutdown()
```

---

## Configuración

### Variables de Entorno

El gateway hereda configuración del módulo `shared.config.settings`:

```bash
# WebSocket
WS_MAX_CONNECTIONS_PER_USER=3
WS_MAX_TOTAL_CONNECTIONS=1000
WS_MESSAGE_RATE_LIMIT=20
WS_BROADCAST_BATCH_SIZE=50
WS_HEARTBEAT_TIMEOUT=60
WS_MAX_MESSAGE_SIZE=65536

# Redis
REDIS_URL=redis://localhost:6380
REDIS_POOL_MAX_CONNECTIONS=50
REDIS_EVENT_QUEUE_SIZE=5000
REDIS_EVENT_BATCH_SIZE=50

# Seguridad
ALLOWED_ORIGINS=http://localhost:5176,http://localhost:5177,http://localhost:5178
```

### Constantes Documentadas

El archivo `components/core/constants.py` centraliza todas las constantes con documentación:

```python
class WSConstants:
    # Timeouts
    WS_ACCEPT_TIMEOUT = 5.0       # Segundos para aceptar conexión
    WS_RECEIVE_TIMEOUT = 90.0     # 3x heartbeat interval
    JWT_REVALIDATION_INTERVAL = 300.0  # 5 minutos

    # Locks
    MAX_CACHED_LOCKS = 500        # Permite 10x crecimiento
    LOCK_CLEANUP_THRESHOLD = 400  # 80% de max
    LOCK_CLEANUP_HYSTERESIS = 0.8 # Previene thrashing

    # Circuit Breaker
    CIRCUIT_FAILURE_THRESHOLD = 5
    CIRCUIT_RECOVERY_TIMEOUT = 30.0
```

---

## Referencias

- [CLAUDE.md](../CLAUDE.md): Documentación completa del proyecto
- [Backend README](../backend/README.md): Documentación del REST API
- [FastAPI WebSockets](https://fastapi.tiangolo.com/advanced/websockets/)
- [Redis Pub/Sub](https://redis.io/docs/manual/pubsub/)
