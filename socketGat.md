# WebSocket Gateway: Arquitectura y Funcionamiento

## Introducción

El WebSocket Gateway constituye el sistema nervioso central de comunicación en tiempo real dentro del ecosistema Integrador. Ejecutándose en el puerto 8001, este servicio actúa como intermediario entre los eventos de dominio generados por la API REST y los clientes conectados que requieren notificaciones instantáneas. A diferencia del modelo tradicional de polling donde los clientes consultan repetidamente al servidor, el Gateway mantiene conexiones bidireccionales persistentes que permiten la transmisión inmediata de eventos sin latencia perceptible para el usuario final.

La arquitectura del Gateway fue diseñada desde sus cimientos para soportar operaciones de alta concurrencia. Con capacidad para manejar simultáneamente entre 400 y 1000 conexiones WebSocket, el sistema implementa patrones avanzados de gestión de recursos que incluyen locks fragmentados por sucursal y usuario, un worker pool dedicado para broadcasting paralelo, y pools de conexiones Redis optimizados. Esta infraestructura permite que un restaurante ocupado pueda operar con docenas de mozos, múltiples terminales de cocina y cientos de comensales activos, todos recibiendo actualizaciones en tiempo real sobre el estado de sus pedidos.

El proyecto experimentó una refactorización arquitectónica significativa identificada como ARCH-MODULAR, que transformó archivos monolíticos de casi 1000 líneas en orquestadores delgados que delegan responsabilidades a módulos especializados. Esta transformación no solo mejoró la mantenibilidad del código sino que habilitó testing unitario granular y evolución independiente de cada componente.

---

## Capítulo 1: Arquitectura Fundamental

### 1.1 Estructura Modular del Proyecto

El WebSocket Gateway reside en la carpeta `ws_gateway/` en la raíz del proyecto. Su organización refleja una arquitectura de componentes donde cada módulo tiene una responsabilidad única y bien definida:

```
ws_gateway/
├── main.py                    # Punto de entrada FastAPI con lifespan manager
├── connection_manager.py      # Orquestador delgado (~463 líneas, reducido de 987)
├── redis_subscriber.py        # Orquestador de suscripción (~326 líneas, reducido de 666)
├── core/                      # Módulos extraídos del connection_manager
│   ├── __init__.py            # Re-exporta todos los módulos
│   ├── connection/
│   │   ├── lifecycle.py       # ConnectionLifecycle: connect/disconnect
│   │   ├── broadcaster.py     # ConnectionBroadcaster: envío paralelo con workers
│   │   ├── cleanup.py         # ConnectionCleanup: limpieza de conexiones muertas
│   │   └── stats.py           # ConnectionStats: agregación de estadísticas
│   └── subscriber/
│       ├── drop_tracker.py    # EventDropRateTracker: alertas de eventos perdidos
│       ├── validator.py       # Validación de esquemas de eventos
│       └── processor.py       # Procesamiento en lotes de eventos
└── components/                # Componentes organizados por dominio
    ├── __init__.py            # Re-exporta símbolos públicos (backward compat)
    ├── core/
    │   ├── constants.py       # WSCloseCode, WSConstants, canales Redis
    │   ├── context.py         # WebSocketContext para logging estructurado
    │   └── dependencies.py    # Contenedor DI para testing
    ├── connection/
    │   ├── index.py           # ConnectionIndex: índices y mappings
    │   ├── locks.py           # LockManager: locks fragmentados
    │   ├── heartbeat.py       # HeartbeatTracker: detección de conexiones stale
    │   └── rate_limiter.py    # WebSocketRateLimiter: límite de mensajes
    ├── events/
    │   ├── types.py           # WebSocketEvent, VALID_EVENT_TYPES
    │   └── router.py          # EventRouter: validación y enrutamiento
    ├── broadcast/
    │   ├── router.py          # BroadcastRouter con Strategy y Observer patterns
    │   └── tenant_filter.py   # TenantFilter: aislamiento multi-tenant
    ├── auth/
    │   └── strategies.py      # JWTAuthStrategy, TableTokenAuthStrategy
    ├── endpoints/
    │   ├── base.py            # WebSocketEndpointBase, JWTWebSocketEndpoint
    │   ├── mixins.py          # Mixins de validación, heartbeat, JWT
    │   └── handlers.py        # WaiterEndpoint, KitchenEndpoint, AdminEndpoint, DinerEndpoint
    ├── resilience/
    │   ├── circuit_breaker.py # CircuitBreaker con threading.Lock unificado
    │   └── retry.py           # RetryConfig con jitter decorrelacionado
    ├── metrics/
    │   ├── collector.py       # MetricsCollector thread-safe
    │   └── prometheus.py      # PrometheusFormatter para /ws/metrics
    └── data/
        └── sector_repository.py # SectorAssignmentRepository con caché TTL
```

La separación entre `core/` y `components/` refleja dos niveles de abstracción: `core/` contiene los módulos extraídos directamente de los orquestadores monolíticos originales, mientras que `components/` organiza funcionalidad transversal por dominio de responsabilidad.

### 1.2 El Punto de Entrada: main.py

El archivo `main.py` configura la aplicación FastAPI y orquesta el ciclo de vida completo del Gateway. La función `lifespan` es el corazón de esta orquestación, iniciando y deteniendo múltiples subsistemas de forma coordinada:

```python
@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup: Inicializar todos los subsistemas
    await manager.start_broadcast_workers()  # SCALE-HIGH-01: Worker pool paralelo

    subscriber_task = asyncio.create_task(start_redis_subscriber())
    stream_task = asyncio.create_task(run_stream_consumer(handle_routed_event))
    cleanup_task = asyncio.create_task(start_heartbeat_cleanup())

    yield  # Aplicación ejecutándose

    # Shutdown: Cerrar ordenadamente
    subscriber_task.cancel()
    stream_task.cancel()
    cleanup_task.cancel()

    await manager.stop_broadcast_workers(timeout=5.0)
    await manager._lock_manager.await_pending_cleanup()
    cleanup_sector_repository()
    await close_redis_pool()
```

El startup inicializa cuatro componentes críticos en paralelo: el worker pool de broadcasting (10 workers que procesan envíos concurrentemente), el suscriptor Redis Pub/Sub (escucha eventos en canales de sucursal, sector y sesión), el consumidor de Redis Streams (para eventos críticos con entrega garantizada), y la tarea de limpieza de heartbeat (remueve conexiones inactivas cada 30 segundos).

Los endpoints WebSocket expuestos diferencian clientes por rol y método de autenticación:

| Endpoint | Autenticación | Roles Permitidos | Propósito |
|----------|---------------|------------------|-----------|
| `/ws/waiter?token=JWT` | JWT | WAITER, MANAGER, ADMIN | Notificaciones por sector asignado |
| `/ws/kitchen?token=JWT` | JWT | KITCHEN, MANAGER, ADMIN | Comandas para preparación |
| `/ws/admin?token=JWT` | JWT | MANAGER, ADMIN | Visibilidad completa de sucursal |
| `/ws/diner?table_token=TOKEN` | Table Token HMAC | N/A (sesión de mesa) | Actualizaciones de pedido personal |

Adicionalmente, el Gateway expone endpoints de observabilidad:

- `/ws/health` - Verificación básica de disponibilidad
- `/ws/health/detailed` - Estado de Redis, pools, conexiones activas
- `/ws/metrics` - Métricas en formato Prometheus para scraping

---

## Capítulo 2: Gestión de Conexiones

### 2.1 El Connection Manager como Orquestador

El `ConnectionManager` representa la fachada principal para todas las operaciones de conexión. Tras la refactorización ARCH-MODULAR-08, este archivo se transformó de una clase monolítica de 987 líneas a un orquestador delgado de 463 líneas que compone módulos especializados:

```python
class ConnectionManager:
    def __init__(self) -> None:
        # Componentes core
        self._lock_manager = LockManager()
        self._metrics = MetricsCollector()
        self._heartbeat_tracker = HeartbeatTracker(timeout_seconds=self.HEARTBEAT_TIMEOUT)
        self._rate_limiter = WebSocketRateLimiter(
            max_messages=settings.ws_message_rate_limit,  # 20/segundo
            window_seconds=settings.ws_message_rate_window,
        )
        self._index = ConnectionIndex()

        # Composición de módulos especializados
        self._lifecycle = ConnectionLifecycle(...)  # Connect/disconnect
        self._cleanup = ConnectionCleanup(...)      # Limpieza de stale/dead
        self._broadcaster = ConnectionBroadcaster(...)  # Envío paralelo
        self._stats = ConnectionStats(...)          # Agregación de estadísticas
```

Esta composición permite que cada aspecto de la gestión de conexiones sea probado, mantenido y evolucionado independientemente. Los métodos públicos del manager simplemente delegan al módulo apropiado:

```python
async def connect(self, websocket, user_id, branch_ids, ...):
    await self._lifecycle.connect(websocket, user_id, branch_ids, ...)

async def send_to_branch(self, branch_id, payload, tenant_id=None):
    return await self._broadcaster.send_to_branch(branch_id, payload, tenant_id)
```

### 2.2 ConnectionIndex: Índices de Alta Velocidad

El sistema mantiene múltiples índices para localizar conexiones en tiempo O(1) según diferentes criterios. El `ConnectionIndex` encapsula estas estructuras junto con operaciones de registro y búsqueda:

```python
class ConnectionIndex:
    # Índices primarios
    by_user: dict[int, set[WebSocket]]        # user_id → conexiones
    by_branch: dict[int, set[WebSocket]]      # branch_id → conexiones
    by_sector: dict[int, set[WebSocket]]      # sector_id → conexiones (waiters)
    by_session: dict[int, set[WebSocket]]     # session_id → conexiones (diners)

    # Índices por rol
    admins_by_branch: dict[int, set[WebSocket]]   # Admins/managers por sucursal
    kitchen_by_branch: dict[int, set[WebSocket]]  # Personal de cocina por sucursal

    # Mappings inversos
    _ws_to_user: dict[WebSocket, int]         # Conexión → user_id
    _ws_to_tenant: dict[WebSocket, int | None] # Conexión → tenant_id
    _ws_to_branches: dict[WebSocket, list[int]] # Conexión → branch_ids
```

El diseño de índices múltiples permite broadcasts selectivos sin iterar sobre todas las conexiones activas. Cuando un evento debe llegar solo a mozos del sector "Terraza", el sistema consulta directamente `by_sector[terraza_id]` y obtiene el conjunto exacto de conexiones destinatarias.

### 2.3 Sistema de Locks Fragmentados

Para manejar alta concurrencia sin contención excesiva, el Gateway implementa locks fragmentados (sharded locks) en el `LockManager`:

```python
class LockManager:
    connection_counter_lock: asyncio.Lock     # Contador global de conexiones
    _branch_locks: dict[int, asyncio.Lock]    # Un lock por sucursal
    _user_locks: dict[int, asyncio.Lock]      # Un lock por usuario
    sector_lock: asyncio.Lock                  # Operaciones de sector
    session_lock: asyncio.Lock                 # Operaciones de sesión
    dead_connections_lock: asyncio.Lock        # Limpieza de conexiones muertas
```

Cuando un mozo se conecta a la sucursal 5, solo se adquiere el lock de esa sucursal específica, permitiendo que conexiones a otras sucursales procedan en paralelo. Esta estrategia reduce la contención en aproximadamente un 90% comparado con un lock global único.

El orden de adquisición de locks está estrictamente definido para prevenir deadlocks:

1. `connection_counter_lock` (global, primero siempre)
2. `user_lock` (por usuario, en orden ascendente de user_id)
3. `branch_locks` (por sucursal, en orden ascendente de branch_id)
4. Locks secundarios (`sector_lock`, `session_lock`, `dead_connections_lock`)

El `LockManager` incluye lógica de cleanup automático para evitar acumulación infinita de locks:

```python
# WSConstants define límites
MAX_CACHED_LOCKS = 500           # Máximo de locks cacheados
LOCK_CLEANUP_THRESHOLD = 400     # Umbral para trigger de limpieza (80%)
LOCK_CLEANUP_HYSTERESIS_RATIO = 0.8  # Reduce a 80% del threshold (previene thrashing)
```

### 2.4 ConnectionLifecycle: Registro y Desregistro

El módulo `ConnectionLifecycle` encapsula toda la lógica de aceptación y limpieza de conexiones:

```python
async def connect(
    self,
    websocket: WebSocket,
    user_id: int,
    branch_ids: list[int],
    sector_ids: list[int] | None = None,
    is_admin: bool = False,
    is_kitchen: bool = False,
    timeout: float = WSConstants.WS_ACCEPT_TIMEOUT,
    tenant_id: int | None = None,
) -> None:
    # 1. Verificar shutdown
    if self._shutdown:
        raise ConnectionError("Server is shutting down")

    # 2. Validar parámetros
    self._validate_branch_ids(branch_ids, user_id)
    if sector_ids:
        self._validate_sector_ids(sector_ids, user_id, tenant_id)

    # 3. Verificar límite global (atómico)
    async with self._lock_manager.connection_counter_lock:
        if self._total_connections >= self._max_total_connections:
            self._metrics.increment_connection_rejected_limit_sync()
            raise ConnectionError(f"Server at capacity ({self._max_total_connections})")
        self._total_connections += 1

    # 4. Aceptar WebSocket
    try:
        await asyncio.wait_for(websocket.accept(), timeout=timeout)
    except (asyncio.TimeoutError, Exception):
        await self._decrement_connection_count()
        raise

    # 5. Registrar en índices
    await self._register_connection(websocket, user_id, branch_ids, ...)
```

La validación incluye advertencias para patrones sospechosos como mozos con más de `MAX_SECTORS_PER_WAITER` (10) sectores asignados o IDs de sector duplicados, que podrían indicar configuración incorrecta.

### 2.5 HeartbeatTracker y Limpieza de Conexiones

El `HeartbeatTracker` mantiene un registro preciso de la última actividad de cada conexión:

```python
class HeartbeatTracker:
    def __init__(self, timeout_seconds: float = 60.0):
        self._last_heartbeat: dict[WebSocket, float] = {}
        self._timeout = timeout_seconds
        self._lock = threading.Lock()  # Thread-safe para sync operations

    def record(self, ws: WebSocket) -> None:
        with self._lock:
            self._last_heartbeat[ws] = time.time()

    def get_stale_connections(self) -> list[WebSocket]:
        threshold = time.time() - self._timeout
        with self._lock:
            return [ws for ws, t in self._last_heartbeat.items() if t < threshold]
```

El protocolo de heartbeat funciona así:
1. Cliente envía `{"type": "ping"}` cada 30 segundos
2. Servidor responde `{"type": "pong"}` y actualiza timestamp
3. Tarea de limpieza ejecuta cada 30 segundos
4. Conexiones sin heartbeat en 60 segundos se marcan como stale
5. Conexiones stale se cierran con código 1001 (GOING_AWAY)

El `ConnectionCleanup` implementa un patrón de dos fases para evitar errores de "dictionary changed size during iteration":

```python
async def cleanup_stale_connections(self) -> int:
    # Fase 1: Tomar snapshot bajo lock
    stale = await self.get_stale_connections()

    # Fase 2: Cerrar fuera del lock (operaciones I/O)
    for ws in stale:
        try:
            await ws.close(code=WSCloseCode.GOING_AWAY, reason="Heartbeat timeout")
        except Exception:
            pass

    # Fase 3: Desregistrar con double-check
    for ws in stale:
        await self._disconnect_callback(ws)

    return len(stale)
```

---

## Capítulo 3: Broadcasting Paralelo

### 3.1 ConnectionBroadcaster con Worker Pool

El módulo `ConnectionBroadcaster` representa una de las optimizaciones más significativas del Gateway. Para broadcasts a muchas conexiones, utiliza un worker pool que procesa envíos en paralelo verdadero:

```python
class ConnectionBroadcaster:
    DEFAULT_WORKER_COUNT = 10  # Workers paralelos
    QUEUE_MAX_SIZE = 5000      # Backpressure: max tareas pendientes

    async def start_workers(self) -> None:
        """Inicia el pool en lifespan startup."""
        self._queue = asyncio.Queue(maxsize=self.QUEUE_MAX_SIZE)
        self._running = True

        for i in range(self._worker_count):
            worker = asyncio.create_task(
                self._worker_loop(i),
                name=f"broadcast_worker_{i}"
            )
            self._workers.append(worker)
```

Cada worker ejecuta un loop que consume tareas de la cola:

```python
async def _worker_loop(self, worker_id: int) -> None:
    while self._running:
        try:
            task = await asyncio.wait_for(self._queue.get(), timeout=1.0)
            ws, payload, result_future = task

            success = await self._send_to_connection_internal(ws, payload)
            if result_future and not result_future.done():
                result_future.set_result(success)
        except asyncio.TimeoutError:
            continue  # No hay tareas, seguir esperando
        finally:
            self._queue.task_done()
```

### 3.2 Estrategia Híbrida de Broadcasting

El broadcaster utiliza una estrategia híbrida que selecciona el método óptimo según el tamaño del broadcast:

```python
async def _broadcast_to_connections(
    self,
    connections: list[WebSocket],
    payload: dict[str, Any],
    context: str = "broadcast",
) -> int:
    if not connections:
        return 0

    # Broadcasts grandes (>50 conexiones): usa worker pool
    if self._running and self._queue and len(connections) > self._batch_size:
        return await self._broadcast_via_workers(connections, payload, context)

    # Broadcasts pequeños: modo legacy (lotes secuenciales)
    return await self._broadcast_legacy(connections, payload, context)
```

**Modo Worker Pool** (>50 conexiones):
- Cada envío se encola como tupla `(ws, payload, future)`
- 10 workers procesan en paralelo verdadero
- Futures rastrean resultados para conteo de éxito/fallo
- Tiempo de broadcast reducido de ~4 segundos a ~160ms para 400 conexiones

**Modo Legacy** (≤50 conexiones):
```python
async def _broadcast_legacy(self, connections, payload, context):
    for i in range(0, len(connections), self._batch_size):
        batch = connections[i:i + self._batch_size]
        results = await asyncio.gather(
            *[self._send_to_connection(ws, payload) for ws in batch],
            return_exceptions=True
        )
```

### 3.3 Filtrado Multi-Tenant

El `TenantFilter` garantiza aislamiento estricto entre restaurantes (tenants):

```python
def filter_by_tenant(
    self,
    connections: list[WebSocket],
    tenant_id: int | None,
) -> list[WebSocket]:
    if tenant_id is None:
        return connections  # Sin filtro si no se especifica tenant
    return self._index.filter_by_tenant(connections, tenant_id)
```

Cada conexión almacena su `tenant_id` durante el registro. Antes de cualquier broadcast, el filtro verifica que solo conexiones del mismo tenant reciban el mensaje. Crucialmente, esta verificación ocurre **dentro del lock de rama** para prevenir condiciones de carrera:

```python
async def send_to_branch(self, branch_id, payload, tenant_id=None):
    branch_lock = await self._lock_manager.get_branch_lock(branch_id)
    async with branch_lock:
        connections = list(self._index.get_branch_connections(branch_id))
        connections = self.filter_by_tenant(connections, tenant_id)  # DENTRO del lock
    return await self._broadcast_to_connections(connections, payload, ...)
```

### 3.4 Rate Limiting de Broadcasts

El broadcaster implementa rate limiting para broadcasts globales usando una deque con timestamps:

```python
async def broadcast(self, payload: dict[str, Any]) -> int:
    now = time.time()
    window_start = now - 1.0

    # Contar broadcasts recientes en ventana de 1 segundo
    recent_count = sum(1 for ts in self._broadcast_timestamps if ts > window_start)

    if recent_count >= self._broadcast_rate_limit:
        logger.warning("Broadcast rate limit exceeded, dropping message")
        self._metrics.increment_broadcast_rate_limited_sync()
        return 0

    # O(1) append debido a deque con maxlen
    self._broadcast_timestamps.append(now)

    all_connections = self._index.get_all_connections()
    return await self._broadcast_to_connections(list(all_connections), payload, "global")
```

El límite por defecto es `MAX_BROADCASTS_PER_SECOND = 100` broadcasts globales por segundo.

---

## Capítulo 4: Suscripción a Eventos Redis

### 4.1 Arquitectura del Suscriptor

El `RedisSubscriber` establece una conexión persistente con Redis y escucha eventos publicados por la API REST. Tras la refactorización ARCH-MODULAR-09, se transformó en un orquestador delgado que delega a módulos especializados:

```python
# Global drop rate tracker (singleton)
_drop_rate_tracker = get_drop_tracker(
    window_seconds=60.0,
    alert_threshold_percent=5.0,
    alert_cooldown_seconds=300.0,
)

async def run_subscriber(
    channels: list[str],
    on_message: Callable[[dict], Awaitable[None]],
) -> None:
    redis_pool = await get_redis_pool()
    pubsub = redis_pool.pubsub()
    await pubsub.psubscribe(*channels)

    event_queue: deque[dict] = deque(maxlen=MAX_EVENT_QUEUE_SIZE)  # 5000

    while True:
        msg = await pubsub.get_message(ignore_subscribe_messages=True, timeout=1.0)

        if msg is None:
            # Procesar cola durante tiempo idle
            if event_queue:
                await process_event_batch(event_queue, on_message, _drop_rate_tracker)
            continue

        # Delegar a módulo de procesamiento
        handle_incoming_message(msg, event_queue, events_dropped, _drop_rate_tracker)
```

### 4.2 Canales de Suscripción

Los canales están definidos en `WSConstants` para evitar discrepancias entre publicador y suscriptor:

```python
class WSConstants:
    # Canales Redis Pub/Sub
    REDIS_CHANNEL_BRANCH_WAITERS = "branch:*:waiters"   # Eventos para mozos
    REDIS_CHANNEL_BRANCH_KITCHEN = "branch:*:kitchen"  # Eventos para cocina
    REDIS_CHANNEL_BRANCH_ADMIN = "branch:*:admin"      # Eventos para admin
    REDIS_CHANNEL_SECTOR_WAITERS = "sector:*:waiters"  # Eventos por sector específico
    REDIS_CHANNEL_SESSION = "session:*"                # Eventos de sesión (diners)

    REDIS_SUBSCRIPTION_CHANNELS = (
        REDIS_CHANNEL_BRANCH_WAITERS,
        REDIS_CHANNEL_BRANCH_KITCHEN,
        REDIS_CHANNEL_BRANCH_ADMIN,
        REDIS_CHANNEL_SECTOR_WAITERS,
        REDIS_CHANNEL_SESSION,
    )
```

Los patrones con wildcard (`*`) permiten suscribirse dinámicamente a todas las sucursales y sectores sin conocerlos de antemano. La estructura `<entidad>:<id>:<destinatario>` permite routing granular donde el backend publica a canales específicos según el tipo de evento.

### 4.3 EventDropRateTracker

El `EventDropRateTracker` monitorea eventos que no pueden ser procesados y genera alertas cuando la tasa de pérdida supera umbrales configurados:

```python
class EventDropRateTracker:
    def __init__(
        self,
        window_seconds: float = 60.0,       # Ventana deslizante
        alert_threshold_percent: float = 5.0,  # Alertar si >5% se pierden
        alert_cooldown_seconds: float = 300.0, # 5 min entre alertas
    ):
        max_entries = int(window_seconds * 1000)  # Bounded memory
        self._window: deque[tuple[float, int, int]] = deque(maxlen=max_entries)

    def record_dropped(self) -> None:
        now = time.time()
        with self._lock:
            self._cleanup_window(now)
            self._window.append((now, 0, 1))  # (timestamp, processed, dropped)
            self._total_dropped += 1
            self._check_alert(now)

    def _check_alert(self, now: float) -> None:
        if now - self._last_alert_time < self._alert_cooldown:
            return

        window_total = sum(p + d for _, p, d in self._window)
        if window_total == 0:
            return

        drop_rate = sum(d for _, _, d in self._window) / window_total
        if drop_rate > self._alert_threshold:
            self._last_alert_time = now
            logger.error(
                "CRITICAL: Event drop rate exceeds threshold!",
                drop_rate_percent=round(drop_rate * 100, 2),
                threshold_percent=round(self._alert_threshold * 100, 2),
            )
```

### 4.4 Validación de Esquema de Eventos

El módulo `validator.py` verifica que los eventos contengan los campos requeridos antes del procesamiento:

```python
REQUIRED_EVENT_FIELDS = frozenset({"type", "tenant_id", "branch_id"})
OPTIONAL_EVENT_FIELDS = frozenset({"session_id", "sector_id", "table_id", "entity", ...})
VALID_EVENT_TYPES = frozenset({
    "ROUND_PENDING", "ROUND_CONFIRMED", "ROUND_SUBMITTED",
    "ROUND_IN_KITCHEN", "ROUND_READY", "ROUND_SERVED", "ROUND_CANCELED",
    "SERVICE_CALL_CREATED", "SERVICE_CALL_ACKED", "SERVICE_CALL_CLOSED",
    "TABLE_SESSION_STARTED", "TABLE_CLEARED", "TABLE_STATUS_CHANGED",
    "TICKET_IN_PROGRESS", "TICKET_READY", "TICKET_DELIVERED",
    "ENTITY_CREATED", "ENTITY_UPDATED", "ENTITY_DELETED",
    ...
})

def validate_event_schema_pure(data: dict) -> tuple[bool, str]:
    """Validación pura sin efectos secundarios."""
    if not isinstance(data, dict):
        return False, "not_dict"

    missing = REQUIRED_EVENT_FIELDS - set(data.keys())
    if missing:
        return False, f"missing_fields:{','.join(missing)}"

    event_type = data.get("type")
    if event_type not in VALID_EVENT_TYPES:
        return False, f"unknown_type:{event_type}"

    return True, ""
```

### 4.5 Circuit Breaker para Redis

El `CircuitBreaker` ubicado en `ws_gateway/components/resilience/circuit_breaker.py` protege al Gateway contra cascadas de fallos cuando Redis experimenta problemas:

```python
class CircuitState(Enum):
    CLOSED = "closed"      # Normal: requests pasan
    OPEN = "open"          # Fallo: requests rechazados
    HALF_OPEN = "half_open"  # Recuperación: prueba limitada

class CircuitBreaker:
    def __init__(
        self,
        name: str,
        failure_threshold: int = 5,      # Fallos antes de abrir
        recovery_timeout: float = 30.0,   # Segundos en OPEN antes de probar
        half_open_max_calls: int = 3,    # Pruebas permitidas en HALF_OPEN
    ):
        # CRIT-AUD-01 FIX: Lock unificado para sync y async
        self._lock = threading.Lock()  # Thread-safe en cualquier contexto

    def record_failure(self, error: BaseException | None = None) -> None:
        with self._lock:
            self._failed_calls += 1
            self._failure_count += 1
            self._last_failure_time = time.time()

            if self._state == CircuitState.HALF_OPEN:
                self._transition_to(CircuitState.OPEN)
            elif self._state == CircuitState.CLOSED:
                if self._failure_count >= self._failure_threshold:
                    self._transition_to(CircuitState.OPEN)

    def record_success(self) -> None:
        with self._lock:
            self._successful_calls += 1
            if self._state == CircuitState.HALF_OPEN:
                self._transition_to(CircuitState.CLOSED)
            elif self._state == CircuitState.CLOSED:
                self._failure_count = 0  # Reset en éxito
```

El uso de un único `threading.Lock` (CRIT-AUD-01 FIX) resuelve race conditions que ocurrían cuando `asyncio.Lock` y operaciones sync modificaban el mismo estado desde diferentes contextos.

### 4.6 Redis Streams para Eventos Críticos

Además de Pub/Sub, el Gateway implementa un consumidor de Redis Streams para eventos críticos que requieren entrega garantizada:

```python
# Constantes de Streams
REDIS_STREAM_EVENTS = "events:critical"
REDIS_STREAM_DLQ = "events:dlq"
REDIS_CONSUMER_GROUP = "ws_gateway_group"
STREAM_MAX_RETRIES = 3

async def run_stream_consumer(on_event: Callable[[dict], Awaitable[None]]):
    """
    Consumer Group pattern para entrega garantizada:
    1. Crea Consumer Group si no existe (MKSTREAM)
    2. Lee mensajes nuevos con XREADGROUP
    3. Procesa y ACK cada mensaje exitoso
    4. XAUTOCLAIM para mensajes pendientes huérfanos
    5. Mensajes con 3+ fallos van a DLQ
    """
    redis = await get_redis_pool()

    # Crear grupo si no existe
    try:
        await redis.xgroup_create(STREAM_EVENTS, CONSUMER_GROUP, mkstream=True)
    except Exception:
        pass  # Grupo ya existe

    while True:
        # Leer mensajes nuevos
        messages = await redis.xreadgroup(
            CONSUMER_GROUP, consumer_name,
            {STREAM_EVENTS: ">"},
            count=100, block=5000
        )

        for stream, entries in messages:
            for msg_id, fields in entries:
                try:
                    await on_event(fields)
                    await redis.xack(STREAM_EVENTS, CONSUMER_GROUP, msg_id)
                except Exception as e:
                    # Incrementar retry count
                    retry_count = int(fields.get("_retry_count", 0)) + 1
                    if retry_count >= STREAM_MAX_RETRIES:
                        await redis.xadd(STREAM_DLQ, {
                            "original_id": msg_id,
                            "error": str(e),
                            "retry_count": retry_count,
                            "original_data": json.dumps(fields),
                        })
                        await redis.xack(STREAM_EVENTS, CONSUMER_GROUP, msg_id)
```

---

## Capítulo 5: Autenticación y Autorización

### 5.1 Estrategias de Autenticación

El Gateway implementa el patrón Strategy para soportar diferentes métodos de autenticación a través de clases en `components/auth/strategies.py`:

```python
@dataclass(frozen=True, slots=True)
class AuthResult:
    """Resultado inmutable de autenticación."""
    success: bool
    data: dict[str, Any] | None = None
    error_message: str | None = None
    close_code: int = WSCloseCode.AUTH_FAILED
    audit_reason: str | None = None

    @classmethod
    def ok(cls, data: dict[str, Any]) -> "AuthResult":
        return cls(success=True, data=data)

    @classmethod
    def fail(cls, message: str, close_code: int = WSCloseCode.AUTH_FAILED,
             audit_reason: str = "auth_failed") -> "AuthResult":
        return cls(success=False, error_message=message,
                   close_code=close_code, audit_reason=audit_reason)

    @classmethod
    def forbidden(cls, message: str, audit_reason: str = "forbidden") -> "AuthResult":
        return cls(success=False, error_message=message,
                   close_code=WSCloseCode.FORBIDDEN, audit_reason=audit_reason)
```

La clase `JWTAuthStrategy` valida tokens JWT con verificación de roles:

```python
class JWTAuthStrategy(AuthStrategy, OriginValidationMixin):
    def __init__(self, required_roles: list[str], reject_refresh_tokens: bool = True):
        self._required_roles = required_roles
        self._reject_refresh_tokens = reject_refresh_tokens

    async def authenticate(self, websocket: WebSocket, token: str) -> AuthResult:
        # 1. Validar origen
        if not self.validate_origin(websocket):
            return AuthResult.forbidden("Origin not allowed", audit_reason="invalid_origin")

        # 2. Verificar JWT
        try:
            claims = verify_jwt(token)
        except HTTPException:
            return AuthResult.fail("Authentication failed", audit_reason="jwt_validation_failed")

        # 3. Rechazar refresh tokens
        if self._reject_refresh_tokens and claims.get("type") == "refresh":
            return AuthResult.fail("Authentication failed", audit_reason="refresh_token_used")

        # 4. Verificar roles
        roles = claims.get("roles", [])
        if not roles:
            return AuthResult.forbidden("Access denied - no roles", audit_reason="empty_roles")

        if not any(role in roles for role in self._required_roles):
            return AuthResult.forbidden("Access denied", audit_reason="insufficient_role")

        return AuthResult.ok(claims)
```

La estrategia `TableTokenAuthStrategy` valida tokens HMAC de sesión de mesa para comensales:

```python
class TableTokenAuthStrategy(AuthStrategy, OriginValidationMixin):
    async def authenticate(self, websocket: WebSocket, token: str) -> AuthResult:
        if not self.validate_origin(websocket):
            return AuthResult.forbidden("Origin not allowed", audit_reason="invalid_origin")

        try:
            token_data = verify_table_token(token)
            return AuthResult.ok(token_data)
        except HTTPException:
            return AuthResult.fail("Authentication failed",
                                   audit_reason="table_token_validation_failed")
```

### 5.2 Revalidación Periódica de Tokens

Las conexiones WebSocket son de larga duración, pero los tokens expiran. El Gateway implementa revalidación periódica diferenciada:

```python
# WSConstants
JWT_REVALIDATION_INTERVAL = 300.0           # 5 minutos para staff
TABLE_TOKEN_REVALIDATION_INTERVAL = 1800.0  # 30 minutos para diners
```

**JWT Revalidation** (endpoints staff - WaiterEndpoint, KitchenEndpoint, AdminEndpoint):

La clase base `JWTWebSocketEndpoint` implementa revalidación en su loop de mensajes:

```python
async def _message_loop(self) -> None:
    while True:
        # Revalidar JWT periódicamente
        if not await self._jwt_revalidation_check():
            break  # Token expirado/revocado, cerrar conexión

        # Procesar mensaje...
```

**Table Token Revalidation** (DinerEndpoint - SEC-HIGH-01 FIX):

```python
class DinerEndpoint(WebSocketEndpointBase):
    async def _pre_message_hook(self) -> bool:
        """Revalida table tokens para sesiones largas (2+ horas)."""
        current_time = time.time()
        time_since_revalidation = current_time - self._last_token_revalidation

        if time_since_revalidation < WSConstants.TABLE_TOKEN_REVALIDATION_INTERVAL:
            return True  # No es tiempo de revalidar

        try:
            token_data = verify_table_token(self.table_token)

            # Verificar session_id sigue coincidiendo
            if token_data.get("session_id") != self._session_id:
                await self.websocket.close(
                    code=WSCloseCode.AUTH_FAILED,
                    reason="Session mismatch"
                )
                return False

            self._last_token_revalidation = current_time
            return True

        except Exception:
            await self.websocket.close(
                code=WSCloseCode.AUTH_FAILED,
                reason="Token expired"
            )
            return False
```

### 5.3 Validación de Origen

Todos los endpoints validan el header `Origin` para prevenir ataques CSRF a través de la función compartida:

```python
def validate_websocket_origin(origin: str | None, settings) -> bool:
    """
    HIGH-NEW-03 FIX: Validación centralizada de origen.

    En desarrollo: permite origen ausente.
    En producción: requiere origen en lista permitida.
    """
    if not origin:
        return settings.environment == "development"
    return origin in settings.allowed_origins
```

Conexiones con origen inválido reciben código de cierre 4003 (FORBIDDEN).

---

## Capítulo 6: Endpoints WebSocket

### 6.1 Jerarquía de Clases

Los endpoints WebSocket heredan de clases base que encapsulan comportamiento común, eliminando aproximadamente 300 líneas de código duplicado:

```python
class WebSocketEndpointBase(ABC):
    """Base abstracta con ciclo de vida completo."""

    def __init__(
        self,
        websocket: WebSocket,
        manager: ConnectionManager,
        endpoint_name: str,
    ):
        self.websocket = websocket
        self.manager = manager
        self.endpoint_name = endpoint_name

    async def run(self) -> None:
        """Ejecuta el ciclo de vida completo del endpoint."""
        auth_data = await self.validate_auth()
        if auth_data is None:
            return  # Auth falló, conexión ya cerrada

        context = await self.create_context(auth_data)
        await self.register_connection(context)

        try:
            await self._message_loop()
        finally:
            await self.unregister_connection(context)

    @abstractmethod
    async def validate_auth(self) -> dict[str, Any] | None: ...
    @abstractmethod
    async def create_context(self, auth_data: dict) -> WebSocketContext: ...
    @abstractmethod
    async def register_connection(self, context: WebSocketContext) -> None: ...
    @abstractmethod
    async def unregister_connection(self, context: WebSocketContext) -> None: ...


class JWTWebSocketEndpoint(WebSocketEndpointBase):
    """Añade autenticación JWT y revalidación periódica."""

    def __init__(self, ..., token: str, required_roles: list[str]):
        super().__init__(...)
        self.token = token
        self._auth_strategy = JWTAuthStrategy(required_roles)
        self._last_jwt_revalidation = time.time()

    async def validate_auth(self) -> dict[str, Any] | None:
        result = await self._auth_strategy.authenticate(self.websocket, self.token)
        if not result.success:
            await self.websocket.close(
                code=result.close_code,
                reason=result.error_message or "Authentication failed"
            )
            return None
        return result.data
```

### 6.2 WaiterEndpoint

El endpoint de mozos incluye funcionalidad específica como el comando `refresh_sectors`:

```python
class WaiterEndpoint(JWTWebSocketEndpoint):
    def __init__(self, websocket: WebSocket, manager: ConnectionManager, token: str):
        super().__init__(
            websocket=websocket,
            manager=manager,
            endpoint_name="/ws/waiter",
            token=token,
            required_roles=["WAITER", "MANAGER", "ADMIN"],
        )
        self._sector_ids: list[int] = []

    async def create_context(self, auth_data: dict[str, Any]) -> WebSocketContext:
        self._user_id = int(auth_data["sub"])
        raw_tenant_id = auth_data.get("tenant_id")
        self._tenant_id = int(raw_tenant_id) if raw_tenant_id is not None else None
        self._branch_ids = list(auth_data.get("branch_ids", []))
        roles = auth_data.get("roles", [])

        # Obtener asignaciones de sector para waiters
        if "WAITER" in roles and self._tenant_id is not None:
            self._sector_ids = await get_waiter_sector_ids(self._user_id, self._tenant_id)

        self._is_admin_or_manager = any(role in roles for role in ["MANAGER", "ADMIN"])

        return WebSocketContext.from_jwt_claims(
            self.websocket, auth_data, self.endpoint_name,
            sector_ids=self._sector_ids, is_admin=self._is_admin_or_manager,
        )

    async def handle_message(self, data: str) -> None:
        if data == MSG_REFRESH_SECTORS:
            # Revalidar JWT primero
            if not await self.revalidate_jwt(self.token):
                await self.websocket.close(code=WSCloseCode.AUTH_FAILED)
                return

            # Refrescar asignaciones de sector
            new_sector_ids = await get_waiter_sector_ids(self._user_id, self._tenant_id)
            await self.manager.update_sectors(self.websocket, new_sector_ids)
            await self.websocket.send_text(f"sectors_updated:{','.join(map(str, new_sector_ids))}")
            self._sector_ids = new_sector_ids
```

Los mozos reciben eventos filtrados por sector. Un mozo asignado a "Terraza" solo recibe notificaciones de mesas en terraza, no del interior. Los eventos `ROUND_PENDING` y `TABLE_SESSION_STARTED` son excepciones que se envían a todos los mozos de la sucursal para asegurar visibilidad.

### 6.3 KitchenEndpoint

El endpoint de cocina es más simple, recibiendo eventos de rondas desde SUBMITTED hasta SERVED:

```python
class KitchenEndpoint(JWTWebSocketEndpoint):
    def __init__(self, websocket: WebSocket, manager: ConnectionManager, token: str):
        super().__init__(
            websocket=websocket,
            manager=manager,
            endpoint_name="/ws/kitchen",
            token=token,
            required_roles=["KITCHEN", "MANAGER", "ADMIN"],
        )

    async def register_connection(self, context: WebSocketContext) -> None:
        await self.manager.connect(
            self.websocket,
            self._user_id,
            self._branch_ids,
            is_admin=self._is_admin_or_manager,
            is_kitchen=True,  # Marca como conexión de cocina
            tenant_id=self._tenant_id,
        )
```

Los eventos PENDING y CONFIRMED no llegan a cocina ya que representan estados previos a la aprobación por el mozo y administrador. Solo cuando el round pasa a SUBMITTED aparece en las terminales de cocina.

### 6.4 DinerEndpoint

El endpoint de comensales usa autenticación por table token en lugar de JWT:

```python
class DinerEndpoint(WebSocketEndpointBase):
    def __init__(
        self,
        websocket: WebSocket,
        manager: ConnectionManager,
        table_token: str,
    ):
        super().__init__(websocket, manager, "/ws/diner")
        self.table_token = table_token
        self._last_token_revalidation = time.time()

    async def validate_auth(self) -> dict[str, Any] | None:
        if not self._validate_origin():
            await self.websocket.close(code=WSCloseCode.FORBIDDEN)
            return None

        try:
            token_data = verify_table_token(self.table_token)
            return token_data
        except HTTPException:
            await self.websocket.close(code=WSCloseCode.AUTH_FAILED)
            return None

    async def register_connection(self, context: WebSocketContext) -> None:
        # user_id negativo para evitar colisión con IDs de usuario reales
        self._pseudo_user_id = -self._session_id

        await self.manager.connect(
            self.websocket,
            self._pseudo_user_id,
            [self._branch_id],
            tenant_id=self._tenant_id,
        )
        await self.manager.register_session(self.websocket, self._session_id)
```

---

## Capítulo 7: Rate Limiting y Protección

### 7.1 Límite de Mensajes por Conexión

El `WebSocketRateLimiter` previene abuso de conexiones individuales:

```python
class WebSocketRateLimiter:
    def __init__(
        self,
        max_messages: int = 20,      # 20 mensajes
        window_seconds: float = 1.0,  # por segundo
    ):
        self._limits: dict[WebSocket, deque[float]] = {}
        self._max_messages = max_messages
        self._window_seconds = window_seconds

    async def is_allowed(self, ws: WebSocket) -> bool:
        now = time.time()
        timestamps = self._limits.setdefault(ws, deque(maxlen=self._max_messages * 2))

        # Limpiar timestamps fuera de ventana
        while timestamps and timestamps[0] < now - self._window_seconds:
            timestamps.popleft()

        if len(timestamps) >= self._max_messages:
            return False

        timestamps.append(now)
        return True
```

Conexiones que exceden 20 mensajes/segundo reciben código de cierre 4029 (RATE_LIMITED).

### 7.2 Límites de Conexiones

El Gateway implementa límites a múltiples niveles:

```python
# Configuración desde settings.py
MAX_TOTAL_CONNECTIONS = 1000      # Límite global
MAX_CONNECTIONS_PER_USER = 3      # Por usuario

async def connect(self, websocket, user_id, ...):
    # 1. Verificar límite global
    async with self._lock_manager.connection_counter_lock:
        if self._total_connections >= self._max_total_connections:
            self._metrics.increment_connection_rejected_limit_sync()
            raise ConnectionError(f"Server at capacity ({self._max_total_connections})")
        self._total_connections += 1

    # 2. Verificar límite por usuario (dentro de user_lock)
    user_lock = await self._lock_manager.get_user_lock(user_id)
    async with user_lock:
        user_connections = self._index.get_user_connections(user_id)
        if len(user_connections) >= self._max_connections_per_user:
            await self._decrement_connection_count()
            raise ConnectionError(f"User {user_id} exceeded max connections")
```

### 7.3 Códigos de Cierre WebSocket

El Gateway define códigos de cierre semánticos en `WSCloseCode`:

```python
class WSCloseCode(IntEnum):
    NORMAL = 1000              # Cierre normal solicitado
    GOING_AWAY = 1001          # Servidor apagándose o cliente navegando
    POLICY_VIOLATION = 1008    # Mensaje viola política (formato, contenido)
    MESSAGE_TOO_BIG = 1009     # Mensaje excede 64KB
    SERVER_OVERLOADED = 1013   # Servidor sobrecargado
    AUTH_FAILED = 4001         # Token inválido, expirado o revocado
    FORBIDDEN = 4003           # Origen inválido o rol insuficiente
    RATE_LIMITED = 4029        # Demasiados mensajes por segundo
```

---

## Capítulo 8: Métricas y Monitoreo

### 8.1 MetricsCollector Thread-Safe

El `MetricsCollector` centraliza estadísticas del Gateway con operaciones thread-safe:

```python
class MetricsCollector:
    def __init__(self):
        self._lock = asyncio.Lock()
        self._sync_lock = threading.Lock()  # CRIT-WS-08 FIX
        self._broadcast = BroadcastMetrics()
        self._connection = ConnectionMetrics()
        self._event = EventMetrics()

    # Métodos async para uso normal
    async def increment_broadcast_total(self) -> None:
        async with self._lock:
            self._broadcast.total += 1

    # Métodos sync para hot paths (CRIT-WS-08 FIX)
    def increment_broadcast_total_sync(self) -> None:
        with self._sync_lock:
            self._broadcast.total += 1

    def get_snapshot_sync(self) -> dict[str, Any]:
        """Snapshot para health checks (sync)."""
        with self._sync_lock:
            return {
                "broadcasts_total": self._broadcast.total,
                "broadcasts_failed": self._broadcast.failed,
                "broadcasts_rate_limited": self._broadcast.rate_limited,
                "connections_rejected_limit": self._connection.rejected_limit,
                "connections_rejected_rate_limit": self._connection.rejected_rate_limit,
                "events_processed": self._event.processed,
                "events_dropped": self._event.dropped,
                ...
            }
```

El uso de `threading.Lock` separado para métodos sync (CRIT-WS-08 FIX) garantiza thread safety incluso en implementaciones de Python sin GIL.

### 8.2 Endpoint Prometheus

El endpoint `/ws/metrics` expone métricas en formato Prometheus para scraping:

```
# HELP wsgateway_connections_total Total connections since startup
# TYPE wsgateway_connections_total counter
wsgateway_connections_total 1542

# HELP wsgateway_connections_active Current active connections
# TYPE wsgateway_connections_active gauge
wsgateway_connections_active 42

# HELP wsgateway_broadcasts_total Total broadcasts sent
# TYPE wsgateway_broadcasts_total counter
wsgateway_broadcasts_total 8234

# HELP wsgateway_broadcasts_failed Broadcasts with failures
# TYPE wsgateway_broadcasts_failed counter
wsgateway_broadcasts_failed 12

# HELP wsgateway_events_dropped_total Events dropped
# TYPE wsgateway_events_dropped_total counter
wsgateway_events_dropped_total{reason="invalid_schema"} 3
wsgateway_events_dropped_total{reason="no_recipients"} 45
wsgateway_events_dropped_total{reason="circuit_open"} 0

# HELP wsgateway_circuit_breaker_state Circuit breaker current state
# TYPE wsgateway_circuit_breaker_state gauge
wsgateway_circuit_breaker_state{name="redis_subscriber"} 0
```

### 8.3 Health Checks

El endpoint `/ws/health/detailed` reporta estado detallado de componentes:

```json
{
    "status": "healthy",
    "timestamp": "2026-01-31T15:30:00Z",
    "components": {
        "redis_async": {
            "status": "healthy",
            "latency_ms": 2.3,
            "pool_size": 50
        },
        "redis_sync": {
            "status": "healthy",
            "pool_size": 20
        },
        "connections": {
            "active": 42,
            "max": 1000,
            "by_type": {
                "waiter": 12,
                "kitchen": 5,
                "admin": 3,
                "diner": 22
            }
        },
        "circuit_breaker": {
            "state": "closed",
            "failure_count": 0,
            "rejected_calls": 0
        },
        "broadcast_workers": {
            "running": true,
            "worker_count": 10,
            "queue_size": 0
        }
    }
}
```

---

## Capítulo 9: Resiliencia y Recuperación

### 9.1 Reintentos con Jitter Decorrelacionado

Las reconexiones a Redis utilizan backoff exponencial con jitter decorrelacionado para prevenir el "thundering herd":

```python
# En ws_gateway/components/resilience/retry.py
class DecorrelatedJitter:
    """Jitter que previene sincronización de reintentos."""

    def calculate(self, attempt: int, config: RetryConfig) -> float:
        if attempt == 0:
            return config.base_delay

        # Exponential backoff
        exp_delay = config.base_delay * (2 ** attempt)
        capped_delay = min(exp_delay, config.max_delay)

        # Decorrelated jitter: random entre base y delay calculado
        return random.uniform(config.base_delay, capped_delay)

def create_redis_retry_config(
    max_delay: float = 60.0,
    max_attempts: int = 10,
) -> RetryConfig:
    return RetryConfig(
        base_delay=1.0,
        max_delay=max_delay,
        max_attempts=max_attempts,
        jitter_strategy=DecorrelatedJitter(),
    )
```

### 9.2 Limpieza de Conexiones Muertas

El `ConnectionCleanup` implementa un patrón de dos fases para evitar race conditions:

```python
async def cleanup_dead_connections(self) -> int:
    # Fase 1: Obtener lista de conexiones marcadas como muertas
    async with self._lock_manager.dead_connections_lock:
        dead_snapshot = list(self._dead_connections)
        self._dead_connections.clear()

    if not dead_snapshot:
        return 0

    # Fase 2: Desregistrar cada una (puede adquirir otros locks)
    cleaned = 0
    for ws in dead_snapshot:
        try:
            await self._disconnect_callback(ws)
            cleaned += 1
        except Exception as e:
            logger.debug("Error cleaning dead connection: %s", str(e))

    return cleaned
```

Las conexiones se marcan como "muertas" cuando un envío falla. El cleanup real ocurre de forma asíncrona para no bloquear broadcasts.

### 9.3 Caché de Sectores con TTL

El `SectorAssignmentRepository` cachea asignaciones de mozos a sectores para reducir queries a la base de datos:

```python
class SectorCache:
    def __init__(self, ttl_seconds: float = 300.0):  # 5 minutos
        self._cache: dict[int, tuple[list[int], float]] = {}
        self._lock = threading.Lock()

    def get(self, user_id: int) -> list[int] | None:
        with self._lock:
            if user_id not in self._cache:
                return None
            sectors, timestamp = self._cache[user_id]
            if time.time() - timestamp > self._ttl:
                del self._cache[user_id]
                return None
            return sectors

    def set(self, user_id: int, sectors: list[int]) -> None:
        with self._lock:
            self._cache[user_id] = (sectors, time.time())
```

El TTL de 5 minutos balancea entre reducir queries y permitir actualizaciones razonablemente frecuentes cuando se reasignan mozos a diferentes sectores.

---

## Capítulo 10: Flujo Completo de Eventos

### 10.1 Ejemplo: Nuevo Pedido (ROUND_PENDING)

Cuando un comensal envía un pedido desde pwaMenu:

1. **API REST** crea la ronda en PostgreSQL con status `PENDING`
2. **API REST** publica evento a Redis usando `publish_round_event`:
   ```python
   await publish_event(redis, f"branch:{branch_id}:waiters", {
       "type": "ROUND_PENDING",
       "tenant_id": 1,
       "branch_id": 5,
       "round_id": 123,
       "table_id": 42,
       "table_code": "INT-05",
       "diner_count": 3
   })
   # También a admin channel
   await publish_event(redis, f"branch:{branch_id}:admin", {...})
   ```

3. **RedisSubscriber** recibe ambos mensajes via `psubscribe`
4. **validate_event_schema** verifica campos requeridos y tipo válido
5. **EventRouter** determina destinatarios:
   - Canal `branch:5:waiters` → todos los mozos de sucursal 5
   - Canal `branch:5:admin` → admins/managers de sucursal 5
6. **TenantFilter** filtra conexiones por `tenant_id=1`
7. **ConnectionBroadcaster** envía a conexiones:
   - 3 admins conectados al Dashboard
   - 8 mozos de la sucursal en pwaWaiter
8. **Dashboard** muestra alerta visual con animación amarilla
9. **pwaWaiter** muestra notificación de nuevo pedido pendiente

### 10.2 Ejemplo: Round Confirmado y Enviado a Cocina

Flujo cuando mozo confirma y admin envía a cocina:

1. **Mozo confirma** en pwaWaiter → `PATCH /api/kitchen/rounds/{id}` con `status=CONFIRMED`
2. **Evento ROUND_CONFIRMED** publicado a `branch:{id}:admin`
3. **Dashboard** recibe evento, muestra botón "Enviar a Cocina"
4. **Admin envía** → `PATCH /api/kitchen/rounds/{id}` con `status=SUBMITTED`
5. **Evento ROUND_SUBMITTED** publicado a:
   - `branch:{id}:kitchen` → terminales de cocina
   - `branch:{id}:admin` → dashboard
   - `branch:{id}:waiters` → mozos
6. **KitchenEndpoint** recibe evento, muestra comanda en columna "Nuevos"

### 10.3 Ejemplo: Plato Listo (ROUND_READY)

Cuando cocina marca un plato como listo:

1. **API REST** actualiza estado a `READY`
2. **Eventos publicados** a múltiples canales:
   - `branch:{id}:kitchen` → otras terminales de cocina
   - `branch:{id}:admin` → dashboard
   - `branch:{id}:waiters` → mozos para servir
   - `session:{id}` → comensales de la mesa
3. **Dashboard** muestra alerta visual, badge verde en mesa
4. **pwaWaiter** notifica al mozo responsable para servir
5. **pwaMenu** actualiza estado del pedido del comensal con feedback visual

---

## Conclusión

El WebSocket Gateway representa el sistema nervioso central del ecosistema Integrador, transmitiendo información en tiempo real entre todos los actores del restaurante. Su arquitectura modular, resultado de la refactorización ARCH-MODULAR, separó responsabilidades en componentes especializados que pueden evolucionar independientemente.

Los patrones implementados reflejan decisiones arquitectónicas orientadas tanto a la mantenibilidad como al rendimiento:

- **Locks fragmentados** reducen contención 90% en operaciones concurrentes
- **Worker pool** para broadcasting reduce tiempo de entrega de 4s a 160ms
- **Circuit breaker** con lock unificado previene cascadas de fallos
- **Strategy pattern** para autenticación permite extensibilidad sin modificar código existente
- **Observer pattern** en broadcaster desacopla métricas de lógica de negocio
- **Dos fases de cleanup** previenen race conditions en limpieza de conexiones

La separación entre `connection_manager.py` (orquestador) y los módulos de `core/` (implementación) facilita testing unitario con mocks inyectados vía `ConnectionManagerDependencies`. Nuevos endpoints heredan de clases base existentes, nuevos tipos de eventos se integran definiendo su enrutamiento, y las métricas se extienden simplemente añadiendo observers al broadcaster.

Esta arquitectura sustenta la experiencia fluida que usuarios finales perciben al ver actualizaciones instantáneas en sus dispositivos: desde el momento que un comensal confirma su pedido hasta que el plato aparece marcado como "listo" en todas las pantallas relevantes, el Gateway garantiza que la información fluya en milisegundos.
