# Arquitectura del WebSocket Gateway

Este documento describe la arquitectura técnica del WebSocket Gateway de Integrador, detallando los principios de diseño, patrones implementados, estructura de componentes y flujos de datos que conforman el sistema de notificaciones en tiempo real.

---

## Principios Arquitectónicos

### Composición sobre Herencia

El WebSocket Gateway implementa un patrón de composición donde los componentes principales actúan como orquestadores delgados que delegan responsabilidades a módulos especializados. Esta decisión arquitectónica surgió de una refactorización que transformó archivos monolíticos de más de 900 líneas en orquestadores de menos de 500 líneas, extrayendo la lógica en módulos cohesivos.

```
┌─────────────────────────────────────────────────────────────────────────┐
│                    ORQUESTADORES DELGADOS                                │
│                                                                          │
│   connection_manager.py (463 líneas)    redis_subscriber.py (326 líneas)│
│              │                                    │                      │
│              │ compone                            │ compone              │
│              ▼                                    ▼                      │
│   ┌─────────────────────┐              ┌─────────────────────┐          │
│   │ ConnectionLifecycle │              │  EventDropTracker   │          │
│   │ ConnectionBroadcast │              │  EventValidator     │          │
│   │ ConnectionCleanup   │              │  EventProcessor     │          │
│   │ ConnectionStats     │              │                     │          │
│   └─────────────────────┘              └─────────────────────┘          │
└─────────────────────────────────────────────────────────────────────────┘
```

### Separación de Responsabilidades

Cada módulo tiene una única razón para cambiar. Los componentes de conexión manejan el ciclo de vida de WebSockets, los de eventos procesan mensajes de Redis, y los de broadcast distribuyen a clientes. Esta separación permite evolucionar cada aspecto independientemente.

### Inversión de Dependencias

Los componentes dependen de abstracciones (Protocols) en lugar de implementaciones concretas. Esto facilita el testing mediante inyección de mocks y permite sustituir implementaciones sin afectar al código cliente.

```python
# Protocol define el contrato
class ConnectionManagerProtocol(Protocol):
    async def send_to_branch(self, branch_id: int, payload: dict, tenant_id: int) -> int: ...
    async def send_to_sector(self, sector_id: int, payload: dict, tenant_id: int) -> int: ...

# EventRouter depende de la abstracción, no de ConnectionManager concreto
class EventRouter:
    def __init__(self, manager: ConnectionManagerProtocol):
        self._manager = manager
```

---

## Arquitectura de Capas

### Diagrama de Capas

```
                              WebSocket Connection
                                      │
                                      ▼
┌─────────────────────────────────────────────────────────────────────────┐
│                          PRESENTATION LAYER                              │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐    │
│  │   Waiter    │  │   Kitchen   │  │    Admin    │  │    Diner    │    │
│  │  Endpoint   │  │  Endpoint   │  │  Endpoint   │  │  Endpoint   │    │
│  └──────┬──────┘  └──────┬──────┘  └──────┬──────┘  └──────┬──────┘    │
│         │                │                │                │            │
│         └────────────────┴────────────────┴────────────────┘            │
│                                   │                                      │
│                    ┌──────────────▼──────────────┐                      │
│                    │   WebSocketEndpointBase     │                      │
│                    │   (Template Method)         │                      │
│                    └──────────────┬──────────────┘                      │
└───────────────────────────────────┼─────────────────────────────────────┘
                                    │
┌───────────────────────────────────▼─────────────────────────────────────┐
│                          APPLICATION LAYER                               │
│                                                                          │
│  ┌─────────────────┐  ┌─────────────────┐  ┌─────────────────┐         │
│  │   Connection    │  │     Event       │  │   Broadcast     │         │
│  │    Manager      │  │     Router      │  │    Router       │         │
│  └────────┬────────┘  └────────┬────────┘  └────────┬────────┘         │
│           │                    │                    │                   │
│           └────────────────────┴────────────────────┘                   │
└───────────────────────────────────┬─────────────────────────────────────┘
                                    │
┌───────────────────────────────────▼─────────────────────────────────────┐
│                           DOMAIN LAYER                                   │
│                                                                          │
│  ┌─────────────────┐  ┌─────────────────┐  ┌─────────────────┐         │
│  │  WebSocket      │  │    Event        │  │  Authentication │         │
│  │  Context        │  │    Types        │  │   Strategies    │         │
│  └─────────────────┘  └─────────────────┘  └─────────────────┘         │
└───────────────────────────────────┬─────────────────────────────────────┘
                                    │
┌───────────────────────────────────▼─────────────────────────────────────┐
│                        INFRASTRUCTURE LAYER                              │
│                                                                          │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐    │
│  │   Redis     │  │  Connection │  │   Sector    │  │   Metrics   │    │
│  │ Subscriber  │  │    Index    │  │ Repository  │  │  Collector  │    │
│  └─────────────┘  └─────────────┘  └─────────────┘  └─────────────┘    │
└─────────────────────────────────────────────────────────────────────────┘
```

### Presentation Layer

La capa de presentación define los endpoints WebSocket que los clientes utilizan para conectarse. Cada endpoint hereda de una clase base que implementa el patrón Template Method, proporcionando un ciclo de vida común mientras permite personalización específica.

**WebSocketEndpointBase** define el esqueleto:
1. Aceptar conexión WebSocket
2. Validar autenticación
3. Crear contexto de auditoría
4. Registrar en ConnectionManager
5. Ejecutar loop de mensajes
6. Desregistrar al cerrar

**Mixins** añaden comportamientos específicos:
- `MessageValidationMixin`: Valida tamaño y rate limit
- `OriginValidationMixin`: Verifica header Origin
- `JWTRevalidationMixin`: Revalida JWT periódicamente
- `HeartbeatMixin`: Registra heartbeats

### Application Layer

La capa de aplicación orquesta las operaciones del sistema. El `ConnectionManager` coordina el registro de conexiones, el `EventRouter` determina destinatarios de eventos, y el `BroadcastRouter` ejecuta la distribución.

### Domain Layer

Los objetos de dominio representan conceptos del negocio: `WebSocketContext` encapsula información de auditoría, `WebSocketEvent` representa eventos inmutables, y las estrategias de autenticación definen políticas de acceso.

### Infrastructure Layer

La infraestructura proporciona capacidades técnicas: `RedisSubscriber` gestiona pub/sub, `ConnectionIndex` almacena índices, `SectorRepository` accede a datos de asignaciones, y `MetricsCollector` recopila métricas.

---

## Arquitectura de Componentes

### Diagrama de Componentes Principal

```
┌─────────────────────────────────────────────────────────────────────────┐
│                              main.py                                     │
│                         (FastAPI Application)                            │
│                                                                          │
│   ┌─────────────────┐                      ┌─────────────────┐          │
│   │    Lifespan     │                      │    Endpoints    │          │
│   │   Management    │                      │   /ws/waiter    │          │
│   │                 │                      │   /ws/kitchen   │          │
│   │  • Start Redis  │                      │   /ws/admin     │          │
│   │  • Start Tasks  │                      │   /ws/diner     │          │
│   │  • Shutdown     │                      │                 │          │
│   └────────┬────────┘                      └────────┬────────┘          │
└────────────┼────────────────────────────────────────┼────────────────────┘
             │                                        │
             │              ┌─────────────────────────┘
             │              │
             ▼              ▼
┌─────────────────────────────────────────────────────────────────────────┐
│                        ConnectionManager                                 │
│                     (Thin Orchestrator - 463 lines)                      │
│                                                                          │
│   Compone:                                                               │
│   ┌───────────────┐ ┌───────────────┐ ┌───────────────┐                │
│   │  LockManager  │ │MetricsCollect │ │HeartbeatTrack │                │
│   └───────────────┘ └───────────────┘ └───────────────┘                │
│   ┌───────────────┐ ┌───────────────┐ ┌───────────────┐                │
│   │  RateLimiter  │ │ConnectionIndex│ │ TenantFilter  │                │
│   └───────────────┘ └───────────────┘ └───────────────┘                │
│                                                                          │
│   Delega a:                                                              │
│   ┌───────────────┐ ┌───────────────┐ ┌───────────────┐ ┌────────────┐│
│   │  Lifecycle    │ │  Broadcaster  │ │   Cleanup     │ │   Stats    ││
│   │  (core/)      │ │  (core/)      │ │   (core/)     │ │  (core/)   ││
│   └───────────────┘ └───────────────┘ └───────────────┘ └────────────┘│
└─────────────────────────────────────────────────────────────────────────┘
             │
             │ route_event callback
             ▼
┌─────────────────────────────────────────────────────────────────────────┐
│                         RedisSubscriber                                  │
│                     (Thin Orchestrator - 326 lines)                      │
│                                                                          │
│   Compone:                                                               │
│   ┌───────────────┐ ┌───────────────┐ ┌───────────────┐                │
│   │CircuitBreaker │ │  RetryConfig  │ │ DropTracker   │                │
│   └───────────────┘ └───────────────┘ └───────────────┘                │
│                                                                          │
│   Delega a (core/subscriber/):                                           │
│   ┌───────────────┐ ┌───────────────┐ ┌───────────────┐                │
│   │  DropTracker  │ │   Validator   │ │  Processor    │                │
│   └───────────────┘ └───────────────┘ └───────────────┘                │
└─────────────────────────────────────────────────────────────────────────┘
             │
             │ Redis Pub/Sub
             ▼
┌─────────────────────────────────────────────────────────────────────────┐
│                              Redis                                       │
│                                                                          │
│   Channels:                                                              │
│   • channel:branch:{id}:waiters                                         │
│   • channel:branch:{id}:kitchen                                         │
│   • channel:branch:{id}:admin                                           │
│   • channel:sector:{branch}:{sector}:waiters                            │
│   • channel:session:{id}                                                │
└─────────────────────────────────────────────────────────────────────────┘
```

### Módulo core/connection/

Este módulo contiene la lógica de gestión de conexiones extraída del monolítico `connection_manager.py`:

```
core/connection/
│
├── lifecycle.py          # ConnectionLifecycle
│   │
│   │  Responsabilidades:
│   │  • Aceptar conexiones WebSocket con timeout
│   │  • Validar límites (por usuario, global)
│   │  • Registrar en índices bajo locks apropiados
│   │  • Desconectar y liberar recursos
│   │
│   └── Métodos principales:
│       • connect(ws, user_id, branch_ids, sector_ids, is_admin, tenant_id)
│       • disconnect(ws)
│
├── broadcaster.py        # ConnectionBroadcaster
│   │
│   │  Responsabilidades:
│   │  • Enviar a conexiones individuales
│   │  • Broadcast paralelo en lotes de 50
│   │  • Marcar conexiones muertas
│   │  • Filtrar por tenant
│   │
│   └── Métodos principales:
│       • send_to_user(user_id, payload, tenant_id)
│       • send_to_branch(branch_id, payload, tenant_id)
│       • send_to_sector(sector_id, payload, tenant_id)
│       • send_to_session(session_id, payload, tenant_id)
│       • send_to_admins(branch_id, payload, tenant_id)
│       • broadcast(payload)
│
├── cleanup.py            # ConnectionCleanup
│   │
│   │  Responsabilidades:
│   │  • Detectar conexiones stale (sin heartbeat)
│   │  • Limpiar conexiones muertas (fallaron en send)
│   │  • Limpiar locks obsoletos
│   │
│   └── Métodos principales:
│       • cleanup_stale_connections()
│       • cleanup_dead_connections()
│       • cleanup_locks()
│       • mark_dead_connection(ws)
│
└── stats.py              # ConnectionStats
    │
    │  Responsabilidades:
    │  • Agregar estadísticas de conexión
    │  • Reportar para health checks
    │  • Formato para Prometheus
    │
    └── Métodos principales:
        • get_stats() → dict
        • get_stats_sync() → dict
```

### Módulo core/subscriber/

Este módulo contiene la lógica de procesamiento de eventos extraída del monolítico `redis_subscriber.py`:

```
core/subscriber/
│
├── drop_tracker.py       # EventDropRateTracker
│   │
│   │  Responsabilidades:
│   │  • Monitorear tasa de eventos descartados
│   │  • Alertar cuando supera umbral (5%)
│   │  • Cooldown para evitar spam de logs
│   │
│   └── API:
│       • record_dropped()
│       • record_processed()
│       • get_stats() → dict
│
├── validator.py          # Funciones de validación
│   │
│   │  Responsabilidades:
│   │  • Validar esquema de eventos
│   │  • Verificar campos requeridos
│   │  • Trackear tipos desconocidos
│   │
│   └── Funciones:
│       • validate_event_schema(data) → (bool, str|None)
│       • validate_event_schema_pure(data) → (bool, str|None)
│       • track_unknown_event_type(event_type)
│       • get_unknown_event_metrics() → dict
│
└── processor.py          # Procesamiento de eventos
    │
    │  Responsabilidades:
    │  • Procesar lotes de eventos
    │  • Manejar timeouts de callback
    │  • Detectar eventos stale
    │
    └── Funciones:
        • process_event_batch(queue, callback, tracker)
        • handle_incoming_message(msg, queue, dropped, tracker)
```

### Módulo components/

El directorio `components/` organiza componentes reutilizables por dominio:

```
components/
│
├── core/                           # Fundamentales
│   ├── constants.py               # WSCloseCode, WSConstants
│   │   └── Centraliza constantes documentadas:
│   │       • Timeouts (accept, receive, revalidation)
│   │       • Límites (locks, rate, batch size)
│   │       • Circuit breaker (threshold, recovery)
│   │
│   ├── context.py                 # WebSocketContext
│   │   └── Encapsula información de auditoría:
│   │       • user_id, tenant_id, branch_ids
│   │       • sector_ids, origin, endpoint
│   │       • Sanitización de datos para logs
│   │
│   └── dependencies.py            # FastAPI DI
│       └── Singletons testeables:
│           • MetricsCollector
│           • RateLimiter
│           • HeartbeatTracker
│           • reset_singletons() para tests
│
├── connection/                     # Gestión de conexiones
│   ├── index.py                   # ConnectionIndex
│   │   └── Índices multi-dimensionales:
│   │       • by_user, by_branch, by_sector
│   │       • by_session, admins_by_branch
│   │       • Reverse mappings (ws → user, etc.)
│   │       • MappingProxyType para inmutabilidad
│   │
│   ├── locks.py                   # LockManager
│   │   └── Locks fragmentados:
│   │       • _branch_locks[branch_id]
│   │       • _user_locks[user_id]
│   │       • Locks globales (sector, session, dead)
│   │       • Limpieza diferida de locks
│   │
│   ├── lock_sequence.py           # LockSequence
│   │   └── Ordenamiento de locks:
│   │       • Previene deadlocks
│   │       • Valida orden de adquisición
│   │       • Helpers: with_user_and_branches()
│   │
│   ├── heartbeat.py               # HeartbeatTracker
│   │   └── Detección de stale:
│   │       • record(ws) actualiza timestamp
│   │       • get_stale() retorna conexiones sin HB
│   │       • Timeout configurable (60s default)
│   │
│   └── rate_limiter.py            # WebSocketRateLimiter
│       └── Ventana deslizante:
│           • 20 mensajes/segundo
│           • Evicción 10% más antiguos
│           • Tracking hasta 2000 conexiones
│
├── events/                         # Manejo de eventos
│   ├── types.py                   # WebSocketEvent, EventType
│   │   └── Tipos de eventos:
│   │       • ROUND_* (submitted, in_kitchen, ready, served)
│   │       • SERVICE_CALL_* (created, acked, closed)
│   │       • PAYMENT_* (approved, rejected, failed)
│   │       • TABLE_* (session_started, cleared)
│   │       • ENTITY_* (created, updated, deleted)
│   │
│   └── router.py                  # EventRouter
│       └── Enrutamiento de eventos:
│           • Por tenant_id (siempre)
│           • Por branch_id → admins + waiters
│           • Por sector_id → waiters específicos
│           • Por session_id → diners
│
├── broadcast/                      # Broadcasting
│   ├── router.py                  # BroadcastRouter
│   │   └── Estrategias de broadcast:
│   │       • BatchBroadcastStrategy (lotes fijos)
│   │       • AdaptiveBatchStrategy (dinámico)
│   │       • Observer pattern para métricas
│   │
│   └── tenant_filter.py           # TenantFilter
│       └── Aislamiento multi-tenant:
│           • Filtra conexiones por tenant_id
│           • Logging de mismatches
│           • Stateless (thread-safe)
│
├── auth/                           # Autenticación
│   └── strategies.py              # Auth Strategies
│       └── Strategy pattern:
│           • JWTAuthStrategy (usuarios)
│           • TableTokenAuthStrategy (diners)
│           • CompositeAuthStrategy (múltiples)
│           • NullAuthStrategy (testing)
│
├── endpoints/                      # Endpoints WebSocket
│   ├── base.py                    # WebSocketEndpointBase
│   │   └── Template Method:
│   │       • run() define el ciclo de vida
│   │       • Métodos abstractos para subclases
│   │       • JWTWebSocketEndpoint añade JWT
│   │
│   ├── mixins.py                  # Mixins de funcionalidad
│   │   └── SRP via Mixins:
│   │       • MessageValidationMixin
│   │       • OriginValidationMixin
│   │       • JWTRevalidationMixin
│   │       • HeartbeatMixin
│   │
│   └── handlers.py                # Implementaciones concretas
│       └── Endpoints específicos:
│           • WaiterEndpoint (refresh_sectors)
│           • KitchenEndpoint (rounds)
│           • AdminEndpoint (full access)
│           • DinerEndpoint (table token)
│
├── resilience/                     # Tolerancia a fallos
│   ├── circuit_breaker.py         # CircuitBreaker
│   │   └── Estados: CLOSED → OPEN → HALF_OPEN
│   │       • failure_threshold: 5
│   │       • recovery_timeout: 30s
│   │       • half_open_max_calls: 3
│   │
│   └── retry.py                   # RetryConfig
│       └── Backoff con jitter:
│           • DecorrelatedJitter
│           • Previene thundering herd
│           • max_attempts configurable
│
├── metrics/                        # Observabilidad
│   ├── collector.py               # MetricsCollector
│   │   └── Contadores thread-safe:
│   │       • broadcasts_total
│   │       • connections_total
│   │       • events_processed
│   │       • Versiones sync/async
│   │
│   └── prometheus.py              # PrometheusFormatter
│       └── Formato Prometheus:
│           • wsgateway_* métricas
│           • Labels para dimensiones
│           • Endpoint /ws/metrics
│
└── data/                           # Acceso a datos
    └── sector_repository.py       # SectorAssignmentRepository
        └── Asignaciones de sector:
            • Query a backend DB
            • Cache con TTL (5 min)
            • Timeout protection (2s)
            • Fallback a todos los eventos
```

---

## Patrones de Diseño

### Template Method (Endpoints)

El patrón Template Method define el esqueleto del ciclo de vida de conexión en la clase base, permitiendo que las subclases personalicen pasos específicos sin modificar la estructura general.

```
┌─────────────────────────────────────────────────────────────────────────┐
│                       WebSocketEndpointBase                              │
│  ─────────────────────────────────────────────────────────────────────  │
│                                                                          │
│   async def run(self):                                                   │
│       # 1. Aceptar conexión                                             │
│       await self.websocket.accept()                                      │
│                                                                          │
│       # 2. Validar autenticación (ABSTRACT)                             │
│       auth_result = await self.validate_auth()  ◄─────── Subclass      │
│       if not auth_result.success:                                        │
│           await self.close_with_error(...)                              │
│           return                                                         │
│                                                                          │
│       # 3. Crear contexto (ABSTRACT)                                    │
│       context = await self.get_context(auth_result.claims)  ◄── Subclass│
│                                                                          │
│       # 4. Registrar conexión (ABSTRACT)                                │
│       await self.register_connection(context)  ◄─────────── Subclass    │
│                                                                          │
│       try:                                                               │
│           # 5. Loop de mensajes (usa hooks)                             │
│           await self.message_loop()                                      │
│       finally:                                                           │
│           # 6. Desregistrar (ABSTRACT)                                  │
│           await self.unregister_connection(context)  ◄────── Subclass   │
│                                                                          │
└─────────────────────────────────────────────────────────────────────────┘
                                   △
                                   │ hereda
                                   │
            ┌──────────────────────┼──────────────────────┐
            │                      │                      │
            ▼                      ▼                      ▼
   ┌─────────────────┐   ┌─────────────────┐   ┌─────────────────┐
   │ JWTWebSocket    │   │  DinerEndpoint  │   │     ...         │
   │    Endpoint     │   │                 │   │                 │
   │ ───────────────│   │ ─────────────── │   │                 │
   │ + JWT auth      │   │ + Table token   │   │                 │
   │ + Origin valid  │   │ + No origin     │   │                 │
   │ + Revalidation  │   │   validation    │   │                 │
   └────────┬────────┘   └─────────────────┘   └─────────────────┘
            │
            │ hereda
            │
    ┌───────┴───────┬───────────────┐
    ▼               ▼               ▼
┌────────┐    ┌────────┐    ┌────────┐
│ Waiter │    │Kitchen │    │ Admin  │
│Endpoint│    │Endpoint│    │Endpoint│
└────────┘    └────────┘    └────────┘
```

### Strategy Pattern (Autenticación)

El patrón Strategy permite intercambiar algoritmos de autenticación sin modificar el código que los utiliza.

```
┌─────────────────────────────────────────────────────────────────────────┐
│                          AuthStrategy                                    │
│                          (Protocol)                                      │
│  ─────────────────────────────────────────────────────────────────────  │
│   + authenticate(token: str) -> AuthResult                              │
└─────────────────────────────────────────────────────────────────────────┘
                                   △
                                   │ implementa
          ┌────────────────────────┼────────────────────────┐
          │                        │                        │
          ▼                        ▼                        ▼
┌──────────────────┐    ┌──────────────────┐    ┌──────────────────┐
│  JWTAuthStrategy │    │TableTokenAuth    │    │ NullAuthStrategy │
│                  │    │    Strategy      │    │    (Testing)     │
│ ──────────────── │    │ ──────────────── │    │ ──────────────── │
│ • Verifica JWT   │    │ • Verifica HMAC  │    │ • Siempre OK     │
│ • Extrae claims  │    │ • Extrae session │    │ • Mock data      │
│ • Valida roles   │    │ • Sin roles      │    │                  │
│ • Revalidación   │    │                  │    │                  │
└──────────────────┘    └──────────────────┘    └──────────────────┘

┌──────────────────┐
│CompositeAuth     │
│   Strategy       │
│ ──────────────── │
│ • Lista de strats│
│ • Primer éxito   │
│ • Short-circuit  │
└──────────────────┘
```

### Observer Pattern (Métricas)

El patrón Observer desacopla la recolección de métricas del código de broadcasting.

```
┌─────────────────────────────────────────────────────────────────────────┐
│                        BroadcastRouter                                   │
│  ─────────────────────────────────────────────────────────────────────  │
│   - _observers: list[BroadcastObserver]                                 │
│                                                                          │
│   + add_observer(observer)                                              │
│   + remove_observer(observer)                                           │
│                                                                          │
│   async def broadcast(...):                                              │
│       result = await self._do_broadcast(...)                            │
│       # Notifica a todos los observers                                  │
│       for observer in self._observers:                                  │
│           observer.on_broadcast_complete(sent, failed, context)         │
└─────────────────────────────────────────────────────────────────────────┘
                                   │
                                   │ notifica
                                   ▼
                    ┌──────────────────────────┐
                    │    BroadcastObserver     │
                    │       (Protocol)         │
                    │ ──────────────────────── │
                    │ + on_broadcast_complete()│
                    │ + on_broadcast_rate_     │
                    │     limited()            │
                    └──────────────────────────┘
                                   △
                                   │ implementa
                    ┌──────────────┴──────────────┐
                    │                             │
                    ▼                             ▼
         ┌──────────────────┐          ┌──────────────────┐
         │MetricsObserver   │          │LoggingObserver   │
         │    Adapter       │          │   (Custom)       │
         │ ──────────────── │          │ ──────────────── │
         │ Incrementa       │          │ Logea cada       │
         │ contadores       │          │ broadcast        │
         └──────────────────┘          └──────────────────┘
```

### Circuit Breaker (Resiliencia)

El patrón Circuit Breaker previene cascadas de fallos cuando Redis no está disponible.

```
                          ┌─────────────────┐
                          │     CLOSED      │
                          │    (normal)     │
                          │                 │
                          │ Operación OK    │
                          └────────┬────────┘
                                   │
                          5 fallos consecutivos
                                   │
                                   ▼
                          ┌─────────────────┐
                          │      OPEN       │
                          │  (falla rápido) │
                          │                 │
                          │ Rechaza todas   │
                          │ las operaciones │
                          └────────┬────────┘
                                   │
                          30 segundos timeout
                                   │
                                   ▼
                          ┌─────────────────┐
                          │   HALF_OPEN     │
                          │   (prueba)      │
                          │                 │
                          │ Permite max 3   │
                          │ operaciones     │
                          └────────┬────────┘
                                   │
                    ┌──────────────┴──────────────┐
                    │                             │
               Todas OK                      Alguna falla
                    │                             │
                    ▼                             ▼
           ┌─────────────┐               ┌─────────────┐
           │   CLOSED    │               │    OPEN     │
           │  (normal)   │               │(falla rápido│
           └─────────────┘               └─────────────┘
```

### Sharded Locks (Concurrencia)

Los locks fragmentados reducen la contención permitiendo operaciones paralelas en diferentes sucursales.

```
┌─────────────────────────────────────────────────────────────────────────┐
│                           LockManager                                    │
│  ─────────────────────────────────────────────────────────────────────  │
│                                                                          │
│   Global Locks (contención alta):                                       │
│   ┌─────────────────────────────────────────────────────────────────┐   │
│   │  _connection_counter_lock   (modificar contador total)          │   │
│   │  _sector_lock               (modificar índice de sectores)      │   │
│   │  _session_lock              (modificar índice de sesiones)      │   │
│   │  _dead_connections_lock     (modificar set de muertos)          │   │
│   └─────────────────────────────────────────────────────────────────┘   │
│                                                                          │
│   Sharded Locks (contención reducida 90%):                              │
│   ┌─────────────────────────────────────────────────────────────────┐   │
│   │                                                                  │   │
│   │   _branch_locks: dict[int, asyncio.Lock]                        │   │
│   │   ┌─────┐ ┌─────┐ ┌─────┐ ┌─────┐                              │   │
│   │   │ B:1 │ │ B:2 │ │ B:3 │ │ B:N │  ← Cada sucursal tiene      │   │
│   │   │Lock │ │Lock │ │Lock │ │Lock │    su propio lock            │   │
│   │   └─────┘ └─────┘ └─────┘ └─────┘                              │   │
│   │                                                                  │   │
│   │   _user_locks: dict[int, asyncio.Lock]                          │   │
│   │   ┌─────┐ ┌─────┐ ┌─────┐ ┌─────┐                              │   │
│   │   │ U:1 │ │ U:2 │ │ U:3 │ │ U:N │  ← Cada usuario tiene       │   │
│   │   │Lock │ │Lock │ │Lock │ │Lock │    su propio lock            │   │
│   │   └─────┘ └─────┘ └─────┘ └─────┘                              │   │
│   │                                                                  │   │
│   └─────────────────────────────────────────────────────────────────┘   │
│                                                                          │
│   Lock Ordering (previene deadlocks):                                   │
│   1. connection_counter_lock                                            │
│   2. user_lock (por user_id ascendente)                                 │
│   3. branch_locks (por branch_id ascendente)                            │
│   4. sector_lock                                                        │
│   5. session_lock                                                       │
│   6. dead_connections_lock                                              │
│                                                                          │
└─────────────────────────────────────────────────────────────────────────┘
```

---

## Flujos de Datos

### Flujo de Conexión WebSocket

```
Cliente                    Gateway                     Redis/DB
   │                          │                           │
   │  WS Connect /ws/waiter   │                           │
   │  token=JWT               │                           │
   │─────────────────────────▶│                           │
   │                          │                           │
   │                          │  Validar JWT              │
   │                          │───────────────────────────▶
   │                          │  ◀─── claims ─────────────│
   │                          │                           │
   │                          │  Crear WebSocketContext   │
   │                          │  (user_id, tenant_id,     │
   │                          │   branch_ids, roles)      │
   │                          │                           │
   │                          │  Validar límites          │
   │                          │  • max_per_user (3)       │
   │                          │  • max_total (1000)       │
   │                          │                           │
   │                          │  Adquirir locks           │
   │                          │  (counter → user → branch)│
   │                          │                           │
   │                          │  Registrar en índices     │
   │                          │  • by_user[user_id]       │
   │                          │  • by_branch[branch_id]   │
   │                          │  • by_sector[sector_id]   │
   │                          │                           │
   │                          │  Consultar sectores       │
   │                          │───────────────────────────▶
   │                          │  ◀─── sector_ids ─────────│
   │                          │                           │
   │  ◀── WS Accepted ────────│                           │
   │                          │                           │
   │                          │  Iniciar message loop     │
   │                          │                           │
```

### Flujo de Evento (Backend → Cliente)

```
Backend                    Redis                    Gateway                  Cliente
   │                         │                         │                        │
   │  publish_event()        │                         │                        │
   │  ROUND_SUBMITTED        │                         │                        │
   │  tenant_id=1            │                         │                        │
   │  branch_id=5            │                         │                        │
   │  sector_id=10           │                         │                        │
   │────────────────────────▶│                         │                        │
   │                         │                         │                        │
   │                         │  PUBLISH                │                        │
   │                         │  channel:branch:5:      │                        │
   │                         │  waiters                │                        │
   │                         │────────────────────────▶│                        │
   │                         │                         │                        │
   │                         │                         │  RedisSubscriber       │
   │                         │                         │  get_message()         │
   │                         │                         │                        │
   │                         │                         │  Validar esquema       │
   │                         │                         │  • type ✓              │
   │                         │                         │  • tenant_id ✓         │
   │                         │                         │  • branch_id ✓         │
   │                         │                         │                        │
   │                         │                         │  Encolar evento        │
   │                         │                         │  (backpressure)        │
   │                         │                         │                        │
   │                         │                         │  process_event_batch() │
   │                         │                         │                        │
   │                         │                         │  EventRouter           │
   │                         │                         │  .route_event()        │
   │                         │                         │                        │
   │                         │                         │  Determinar destinos:  │
   │                         │                         │  • sector_id=10 →      │
   │                         │                         │    waiters del sector  │
   │                         │                         │  • admins de branch=5  │
   │                         │                         │                        │
   │                         │                         │  TenantFilter          │
   │                         │                         │  .filter(tenant_id=1)  │
   │                         │                         │                        │
   │                         │                         │  Broadcaster           │
   │                         │                         │  .send_to_sector(10)   │
   │                         │                         │────────────────────────▶
   │                         │                         │         WS message     │
   │                         │                         │                        │
   │                         │                         │  Broadcaster           │
   │                         │                         │  .send_to_admins(5)    │
   │                         │                         │────────────────────────▶
   │                         │                         │         WS message     │
```

### Flujo de Heartbeat

```
Cliente                    Gateway
   │                          │
   │  {"type": "ping"}        │
   │─────────────────────────▶│
   │                          │
   │                          │  MessageValidationMixin
   │                          │  • Verificar tamaño
   │                          │  • Verificar rate limit
   │                          │
   │                          │  HeartbeatMixin
   │                          │  • heartbeat_tracker.record(ws)
   │                          │
   │  {"type": "pong"}        │
   │◀─────────────────────────│
   │                          │
   │      ... 30s ...         │
   │                          │
   │  {"type": "ping"}        │
   │─────────────────────────▶│
   │                          │

─────────── Mientras tanto (cada 30s) ───────────

                           Gateway
                              │
                              │  cleanup_stale_connections()
                              │
                              │  HeartbeatTracker
                              │  .get_stale_connections()
                              │
                              │  Para cada stale:
                              │  • ws.close(code=1001)
                              │  • ConnectionLifecycle.disconnect(ws)
```

### Flujo de Desconexión

```
Cliente                    Gateway
   │                          │
   │  WS Close / Error        │
   │─────────────────────────▶│
   │                          │
   │                          │  ConnectionLifecycle
   │                          │  .disconnect(ws)
   │                          │
   │                          │  Adquirir locks
   │                          │  (user → branches)
   │                          │
   │                          │  Remover de índices:
   │                          │  • by_user[user_id].remove(ws)
   │                          │  • by_branch[branch_id].remove(ws)
   │                          │  • by_sector[sector_id].remove(ws)
   │                          │  • admins_by_branch si is_admin
   │                          │
   │                          │  Limpiar reverse mappings:
   │                          │  • ws_to_user.pop(ws)
   │                          │  • ws_to_branches.pop(ws)
   │                          │  • ws_to_sectors.pop(ws)
   │                          │
   │                          │  HeartbeatTracker
   │                          │  .remove(ws)
   │                          │
   │                          │  RateLimiter
   │                          │  .remove(ws)
   │                          │
   │                          │  Decrementar total_connections
   │                          │
   │                          │  Log: "Connection closed"
```

---

## Multi-tenancy

### Arquitectura de Aislamiento

El gateway implementa aislamiento multi-tenant estricto a través de múltiples capas de defensa:

```
┌─────────────────────────────────────────────────────────────────────────┐
│                     MULTI-TENANT ISOLATION                               │
│                                                                          │
│   Layer 1: Autenticación                                                │
│   ┌─────────────────────────────────────────────────────────────────┐   │
│   │  JWT/TableToken contiene tenant_id                              │   │
│   │  → Rechaza tokens sin tenant_id                                 │   │
│   │  → Almacena tenant_id en WebSocketContext                       │   │
│   └─────────────────────────────────────────────────────────────────┘   │
│                                                                          │
│   Layer 2: Registro de Conexión                                         │
│   ┌─────────────────────────────────────────────────────────────────┐   │
│   │  ConnectionIndex almacena ws_to_tenant[ws] = tenant_id          │   │
│   │  → Cada conexión tiene tenant asociado                          │   │
│   └─────────────────────────────────────────────────────────────────┘   │
│                                                                          │
│   Layer 3: Filtrado de Eventos                                          │
│   ┌─────────────────────────────────────────────────────────────────┐   │
│   │  EventRouter verifica tenant_id del evento                      │   │
│   │  → Rechaza eventos sin tenant_id                                │   │
│   │  → Solo enruta a conexiones del mismo tenant                    │   │
│   └─────────────────────────────────────────────────────────────────┘   │
│                                                                          │
│   Layer 4: TenantFilter                                                 │
│   ┌─────────────────────────────────────────────────────────────────┐   │
│   │  Antes de cada broadcast:                                       │   │
│   │  connections = filter(                                          │   │
│   │      lambda ws: ws_to_tenant[ws] == event_tenant_id,           │   │
│   │      connections                                                │   │
│   │  )                                                              │   │
│   │  → Log de mismatches para auditoría                            │   │
│   └─────────────────────────────────────────────────────────────────┘   │
│                                                                          │
└─────────────────────────────────────────────────────────────────────────┘
```

### Flujo de Verificación

```
Evento llega                   EventRouter                    TenantFilter
     │                              │                              │
     │  {                           │                              │
     │    type: "ROUND_SUBMITTED",  │                              │
     │    tenant_id: 1,             │                              │
     │    branch_id: 5              │                              │
     │  }                           │                              │
     │─────────────────────────────▶│                              │
     │                              │                              │
     │                              │  tenant_id presente?         │
     │                              │  ✓ Sí: continuar             │
     │                              │  ✗ No: rechazar              │
     │                              │                              │
     │                              │  Obtener conexiones          │
     │                              │  de branch_id=5              │
     │                              │─────────────────────────────▶│
     │                              │                              │
     │                              │                              │  Para cada ws:
     │                              │                              │  ws_to_tenant[ws] == 1?
     │                              │                              │  ✓ Incluir
     │                              │                              │  ✗ Excluir + log
     │                              │                              │
     │                              │  ◀─── conexiones filtradas ──│
     │                              │                              │
     │                              │  Broadcast solo a            │
     │                              │  conexiones de tenant=1      │
```

---

## Resiliencia y Recuperación

### Manejo de Fallos de Redis

```
┌─────────────────────────────────────────────────────────────────────────┐
│                        REDIS FAILURE HANDLING                            │
│                                                                          │
│   1. ConnectionError detectado                                          │
│      └─▶ CircuitBreaker.record_failure()                                │
│                                                                          │
│   2. Si failures < threshold (5):                                       │
│      └─▶ Calcular delay con jitter                                      │
│          delay = min(max_delay, base * e^attempt + random())            │
│      └─▶ await asyncio.sleep(delay)                                     │
│      └─▶ Reconectar pubsub                                              │
│                                                                          │
│   3. Si failures >= threshold:                                          │
│      └─▶ CircuitBreaker abre (state=OPEN)                               │
│      └─▶ Todas las operaciones fallan inmediatamente                    │
│      └─▶ Después de recovery_timeout (30s):                             │
│          └─▶ state=HALF_OPEN                                            │
│          └─▶ Permite 3 operaciones de prueba                            │
│          └─▶ Si todas OK: state=CLOSED                                  │
│          └─▶ Si alguna falla: state=OPEN (reinicia)                     │
│                                                                          │
│   4. Durante OPEN/HALF_OPEN:                                            │
│      └─▶ Eventos no se procesan                                         │
│      └─▶ DropTracker registra pérdidas                                  │
│      └─▶ Métricas actualizadas                                          │
│                                                                          │
└─────────────────────────────────────────────────────────────────────────┘
```

### Backpressure y Drop Rate

```
┌─────────────────────────────────────────────────────────────────────────┐
│                         BACKPRESSURE HANDLING                            │
│                                                                          │
│   Event Queue (deque maxlen=5000)                                       │
│   ┌───┬───┬───┬───┬───┬───┬───┬───┬───┬───┐                           │
│   │ E │ E │ E │ E │ E │...│ E │ E │ E │ E │                           │
│   │ 1 │ 2 │ 3 │ 4 │ 5 │   │4996│4997│4998│4999│◀── Nuevo evento        │
│   └───┴───┴───┴───┴───┴───┴───┴───┴───┴───┘                           │
│     │                                                                    │
│     └─▶ Evento 1 descartado automáticamente (deque rotación)            │
│                                                                          │
│   DropTracker:                                                          │
│   • Registra cada descarte                                              │
│   • Calcula tasa en ventana de 60s                                      │
│   • Si tasa > 5%:                                                       │
│     └─▶ Emite alerta (con cooldown 5 min)                               │
│     └─▶ Log: "High drop rate detected: X%"                              │
│                                                                          │
│   Métricas:                                                             │
│   • wsgateway_events_dropped_total                                      │
│   • wsgateway_event_drop_rate                                           │
│                                                                          │
└─────────────────────────────────────────────────────────────────────────┘
```

---

## Optimización de Rendimiento

### Broadcast Paralelo

```
┌─────────────────────────────────────────────────────────────────────────┐
│                       PARALLEL BROADCAST                                 │
│                                                                          │
│   Sin optimización (secuencial):                                        │
│   ────────────────────────────────────────────────────────────────      │
│   for ws in connections:           # 400 conexiones                     │
│       await ws.send_json(payload)  # ~10ms cada una                     │
│   # Total: 400 × 10ms = 4000ms = 4 segundos                            │
│                                                                          │
│   Con optimización (paralelo en lotes):                                 │
│   ────────────────────────────────────────────────────────────────      │
│   batch_size = 50                                                       │
│   for i in range(0, len(connections), batch_size):                      │
│       batch = connections[i:i+batch_size]                               │
│       await asyncio.gather(*[                                           │
│           self._send(ws, payload) for ws in batch                       │
│       ])                                                                │
│   # Total: (400/50) × 10ms = 8 × 10ms = 80ms                           │
│   # Con overhead: ~160ms                                                │
│                                                                          │
│   Mejora: 4000ms → 160ms = 25x más rápido                              │
│                                                                          │
└─────────────────────────────────────────────────────────────────────────┘
```

### Índices O(1)

```
┌─────────────────────────────────────────────────────────────────────────┐
│                        CONNECTION INDEX                                  │
│                                                                          │
│   Sin índices (búsqueda lineal):                                        │
│   ────────────────────────────────────────────────────────────────      │
│   def get_connections_for_branch(branch_id):                            │
│       return [ws for ws in all_connections                              │
│               if ws.branch_id == branch_id]  # O(n)                     │
│                                                                          │
│   Con índices (lookup directo):                                         │
│   ────────────────────────────────────────────────────────────────      │
│   by_branch: dict[int, set[WebSocket]]                                  │
│                                                                          │
│   def get_connections_for_branch(branch_id):                            │
│       return by_branch.get(branch_id, set())  # O(1)                    │
│                                                                          │
│   Índices disponibles:                                                  │
│   • by_user[user_id] → set[WebSocket]                                   │
│   • by_branch[branch_id] → set[WebSocket]                               │
│   • by_sector[sector_id] → set[WebSocket]                               │
│   • by_session[session_id] → set[WebSocket]                             │
│   • admins_by_branch[branch_id] → set[WebSocket]                        │
│                                                                          │
│   Reverse mappings (para cleanup):                                      │
│   • ws_to_user[ws] → int                                                │
│   • ws_to_branches[ws] → set[int]                                       │
│   • ws_to_sectors[ws] → set[int]                                        │
│   • ws_to_tenant[ws] → int                                              │
│                                                                          │
└─────────────────────────────────────────────────────────────────────────┘
```

### Cache de Sectores

```
┌─────────────────────────────────────────────────────────────────────────┐
│                         SECTOR CACHE                                     │
│                                                                          │
│   SectorAssignmentRepository:                                           │
│   ┌─────────────────────────────────────────────────────────────────┐   │
│   │                                                                  │   │
│   │   _cache: dict[tuple[int, int], CacheEntry]                     │   │
│   │                                                                  │   │
│   │   CacheEntry:                                                   │   │
│   │   • sector_ids: list[int]                                       │   │
│   │   • expires_at: float (timestamp)                               │   │
│   │                                                                  │   │
│   │   async def get_sectors(user_id, branch_id):                    │   │
│   │       key = (user_id, branch_id)                                │   │
│   │       if key in _cache and not _is_expired(_cache[key]):        │   │
│   │           return _cache[key].sector_ids  # Cache hit            │   │
│   │                                                                  │   │
│   │       # Cache miss - query DB with timeout                      │   │
│   │       try:                                                      │   │
│   │           async with timeout(2.0):                              │   │
│   │               sectors = await _query_db(user_id, branch_id)     │   │
│   │       except TimeoutError:                                      │   │
│   │           return None  # Fallback: send to all                  │   │
│   │                                                                  │   │
│   │       _cache[key] = CacheEntry(sectors, time() + TTL)           │   │
│   │       return sectors                                            │   │
│   │                                                                  │   │
│   │   TTL = 300 seconds (5 minutes)                                 │   │
│   │                                                                  │   │
│   └─────────────────────────────────────────────────────────────────┘   │
│                                                                          │
└─────────────────────────────────────────────────────────────────────────┘
```

---

## Monitoreo

### Métricas Prometheus

```
┌─────────────────────────────────────────────────────────────────────────┐
│                       PROMETHEUS METRICS                                 │
│                       GET /ws/metrics                                    │
│                                                                          │
│   # Conexiones                                                          │
│   wsgateway_connections_total 42                                        │
│   wsgateway_connections_by_endpoint{endpoint="waiter"} 20               │
│   wsgateway_connections_by_endpoint{endpoint="kitchen"} 5               │
│   wsgateway_connections_by_endpoint{endpoint="admin"} 2                 │
│   wsgateway_connections_by_endpoint{endpoint="diner"} 15                │
│                                                                          │
│   # Rechazos                                                            │
│   wsgateway_connections_rejected_total{reason="auth"} 5                 │
│   wsgateway_connections_rejected_total{reason="rate_limit"} 2           │
│   wsgateway_connections_rejected_total{reason="max_per_user"} 1         │
│   wsgateway_connections_rejected_total{reason="max_total"} 0            │
│                                                                          │
│   # Broadcasts                                                          │
│   wsgateway_broadcasts_total 1234                                       │
│   wsgateway_broadcasts_failed_total 12                                  │
│   wsgateway_broadcast_rate_limited_total 3                              │
│                                                                          │
│   # Eventos                                                             │
│   wsgateway_events_processed_total 5678                                 │
│   wsgateway_events_dropped_total 23                                     │
│   wsgateway_event_drop_rate 0.004                                       │
│                                                                          │
│   # Circuit Breaker                                                     │
│   wsgateway_circuit_breaker_state{name="redis"} 0  # 0=closed, 1=open  │
│   wsgateway_circuit_breaker_failures{name="redis"} 0                    │
│                                                                          │
│   # Locks                                                               │
│   wsgateway_locks_branch_count 15                                       │
│   wsgateway_locks_user_count 42                                         │
│                                                                          │
└─────────────────────────────────────────────────────────────────────────┘
```

### Health Checks

```
┌─────────────────────────────────────────────────────────────────────────┐
│                        HEALTH CHECKS                                     │
│                                                                          │
│   GET /ws/health (sync, rápido):                                        │
│   ────────────────────────────────────────────────────────────────      │
│   {                                                                      │
│     "status": "healthy",                                                │
│     "connections": {                                                    │
│       "total": 42,                                                      │
│       "by_endpoint": { "waiter": 20, "kitchen": 5, ... }               │
│     }                                                                   │
│   }                                                                      │
│                                                                          │
│   GET /ws/health/detailed (async, completo):                            │
│   ────────────────────────────────────────────────────────────────      │
│   {                                                                      │
│     "status": "healthy",                                                │
│     "redis_async": {                                                    │
│       "status": "connected",                                            │
│       "pool_size": 50,                                                  │
│       "active_connections": 12                                          │
│     },                                                                  │
│     "redis_sync": {                                                     │
│       "status": "connected",                                            │
│       "pool_size": 20                                                   │
│     },                                                                  │
│     "circuit_breaker": {                                                │
│       "redis": { "state": "CLOSED", "failures": 0 }                    │
│     },                                                                  │
│     "connections": { ... },                                             │
│     "rate_limiter": {                                                   │
│       "tracked_connections": 42,                                        │
│       "capacity": 2000                                                  │
│     },                                                                  │
│     "event_processing": {                                               │
│       "queue_size": 123,                                                │
│       "drop_rate": 0.001                                                │
│     }                                                                   │
│   }                                                                      │
│                                                                          │
└─────────────────────────────────────────────────────────────────────────┘
```

---

## Ciclo de Vida de la Aplicación

### Startup

```
┌─────────────────────────────────────────────────────────────────────────┐
│                           STARTUP SEQUENCE                               │
│                                                                          │
│   1. Configurar logging                                                 │
│      └─▶ setup_logging()                                                │
│                                                                          │
│   2. Crear ConnectionManager global                                     │
│      └─▶ manager = ConnectionManager()                                  │
│      └─▶ Inicializa: LockManager, MetricsCollector, HeartbeatTracker,  │
│          RateLimiter, ConnectionIndex, Lifecycle, Broadcaster,          │
│          Cleanup, Stats                                                 │
│                                                                          │
│   3. Iniciar task de suscriptor Redis                                   │
│      └─▶ subscriber_task = asyncio.create_task(                         │
│              run_subscriber(channels, manager.route_event)              │
│          )                                                              │
│      └─▶ Suscribe a: branch:*:waiters, branch:*:kitchen,               │
│          branch:*:admin, sector:*:waiters, session:*                    │
│                                                                          │
│   4. Iniciar task de limpieza periódica                                 │
│      └─▶ cleanup_task = asyncio.create_task(                            │
│              periodic_cleanup(manager, interval=30)                     │
│          )                                                              │
│      └─▶ Cada 30s: cleanup_stale, cleanup_dead                         │
│      └─▶ Cada 5 ciclos: cleanup_locks                                  │
│                                                                          │
│   5. Yield (aplicación corriendo)                                       │
│                                                                          │
└─────────────────────────────────────────────────────────────────────────┘
```

### Shutdown

```
┌─────────────────────────────────────────────────────────────────────────┐
│                          SHUTDOWN SEQUENCE                               │
│                                                                          │
│   1. Cancelar task de suscriptor                                        │
│      └─▶ subscriber_task.cancel()                                       │
│      └─▶ try: await subscriber_task except CancelledError: pass         │
│                                                                          │
│   2. Cancelar task de limpieza                                          │
│      └─▶ cleanup_task.cancel()                                          │
│      └─▶ try: await cleanup_task except CancelledError: pass            │
│                                                                          │
│   3. Esperar limpieza de locks (HIGH-WS-09)                             │
│      └─▶ await manager._lock_manager.cleanup_locks()                    │
│                                                                          │
│   4. Limpiar repositorio de sectores (HIGH-WS-10)                       │
│      └─▶ cleanup_sector_repository()                                    │
│                                                                          │
│   5. Cerrar pools de Redis                                              │
│      └─▶ redis_pool = await get_redis_pool()                            │
│      └─▶ await redis_pool.close()                                       │
│                                                                          │
│   6. Cerrar todas las conexiones WebSocket                              │
│      └─▶ await manager.shutdown()                                       │
│      └─▶ Envía close code=1001 (GOING_AWAY) a todos                     │
│                                                                          │
│   7. Log: "WebSocket Gateway shutdown complete"                         │
│                                                                          │
└─────────────────────────────────────────────────────────────────────────┘
```

---

## Referencias

- [README.md](README.md): Documentación general del WebSocket Gateway
- [CLAUDE.md](../CLAUDE.md): Documentación completa del proyecto
- [Backend README](../backend/README.md): Documentación del REST API
- [Backend Architecture](../backend/arquiBackend.md): Arquitectura del backend
