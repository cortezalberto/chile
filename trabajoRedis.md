# Arquitectura de Redis en Integrador

## Introducción

Redis constituye el sistema nervioso central de comunicación en tiempo real de Integrador. Su implementación trasciende el uso convencional como almacén de datos en memoria para convertirse en la columna vertebral que habilita la sincronización instantánea entre todos los componentes del sistema. Sin esta infraestructura, la aplicación funcionaría como un sistema tradicional de solicitud-respuesta, obligando a cada cliente a refrescar manualmente su interfaz para visualizar actualizaciones. Con Redis, el ecosistema cobra vida: cuando un comensal realiza un pedido desde su dispositivo móvil, el mozo recibe instantáneamente una notificación, la cocina visualiza la orden en su pantalla, y el administrador observa en el Dashboard cómo la mesa cambia de estado. Este proceso se completa en milisegundos.

Este documento presenta un análisis exhaustivo de la arquitectura Redis implementada en Integrador, abarcando desde la gestión de conexiones hasta los patrones de resiliencia y seguridad que garantizan la operación continua del sistema.

---

## Capítulo 1: Arquitectura de Comunicación Pub/Sub

### El Paradigma de Eventos en Tiempo Real

La arquitectura de Integrador resuelve un desafío fundamental en sistemas distribuidos: la propagación instantánea de cambios de estado a múltiples clientes heterogéneos. Consideremos un escenario típico en un restaurante con 20 mesas, 5 mozos, 3 cocineros y un administrador. Sin un sistema de eventos, cuando un cliente en la mesa 7 realiza un pedido, el flujo sería deficiente: el pedido se almacena en PostgreSQL, pero el mozo debe refrescar constantemente su aplicación para detectar nuevos pedidos, la cocina desconoce que existe trabajo pendiente hasta consultar manualmente, y el administrador visualiza información desactualizada.

Con la implementación de Redis Pub/Sub, el flujo se transforma radicalmente. El pedido se persiste en PostgreSQL e inmediatamente se publica un evento `ROUND_PENDING` en Redis. El sistema distribuye este evento a todos los suscriptores relevantes de manera selectiva. El WebSocket Gateway recibe el evento y lo transmite exclusivamente a los mozos y administradores conectados de esa sucursal específica. En menos de 100 milisegundos, todos los actores relevantes visualizan el nuevo pedido.

```
┌─────────────────┐         ┌─────────────────┐         ┌─────────────────┐
│   REST API      │         │     REDIS       │         │  WS Gateway     │
│   (Puerto 8000) │────────▶│  (Puerto 6380)  │────────▶│  (Puerto 8001)  │
│                 │ publish │                 │ psubscribe                │
│  Genera eventos │         │  Distribuye     │         │  Recibe y envía │
│  cuando ocurren │         │  a suscriptores │         │  a clientes WS  │
└─────────────────┘         └─────────────────┘         └─────────────────┘
                                                               │
                            ┌──────────────────────────────────┼───────────────────┐
                            │                                  │                   │
                            ▼                                  ▼                   ▼
                    ┌─────────────┐                    ┌─────────────┐     ┌─────────────┐
                    │  Dashboard  │                    │  pwaWaiter  │     │   pwaMenu   │
                    │  (Admin)    │                    │   (Mozos)   │     │ (Comensales)│
                    └─────────────┘                    └─────────────┘     └─────────────┘
```

---

## Capítulo 2: Gestión Avanzada de Conexiones

### Arquitectura de Pools de Conexiones

La implementación de Redis en Integrador no utiliza una conexión única, sino una arquitectura de pools diferenciados que optimiza el rendimiento bajo alta concurrencia. El archivo `backend/shared/infrastructure/events/redis_pool.py` implementa dos pools independientes con responsabilidades claramente definidas.

El **pool asíncrono** está diseñado para operaciones no bloqueantes, principalmente la publicación de eventos desde el REST API. Se configura con un máximo de 50 conexiones simultáneas, permitiendo que hasta 50 operaciones de publicación ocurran en paralelo sin bloquear el servidor. Cada conexión incorpora un timeout de 5 segundos para establecimiento y operaciones de lectura/escritura. Una característica crítica es el `health_check_interval` de 30 segundos, que permite detectar automáticamente conexiones muertas en el pool.

```python
_redis_pool = redis.from_url(
    REDIS_URL,
    max_connections=settings.redis_pool_max_connections,  # 50
    decode_responses=True,
    socket_connect_timeout=settings.redis_socket_timeout,  # 5s
    socket_timeout=settings.redis_socket_timeout,
    health_check_interval=30,  # Auto-detecta conexiones muertas
)
```

La inicialización del pool implementa el patrón **Singleton con doble verificación de bloqueo** (double-check locking). Este patrón garantiza que solo se cree una instancia del pool incluso bajo acceso concurrente de múltiples corrutinas. La primera verificación ocurre sin adquisición de lock para optimizar el caso común donde el pool ya existe. Si no existe, se adquiere un lock asíncrono y se verifica nuevamente antes de la creación, previniendo condiciones de carrera.

```python
async def get_redis_pool() -> redis.Redis:
    global _redis_pool
    if _redis_pool is not None:  # Fast path: no lock needed
        return _redis_pool
    async with _get_pool_lock():
        if _redis_pool is None:  # Double-check after lock
            _redis_pool = await _create_pool()
    return _redis_pool
```

### Pool Síncrono para Operaciones Bloqueantes

Ciertas operaciones requieren ejecución síncrona, particularmente aquellas que ocurren en contextos donde no existe un event loop de asyncio disponible o donde la simplicidad del código síncrono es preferible. Para estas situaciones, el sistema implementa un **pool síncrono** separado con 20 conexiones máximas.

Las operaciones que utilizan el pool síncrono incluyen la verificación de rate limiting durante el login, la consulta de blacklist de tokens JWT durante la validación de middleware de autenticación, y operaciones de webhook de Mercado Pago que requieren sincronía con sistemas externos.

```python
def _get_redis_sync_pool() -> "redis_sync.ConnectionPool":
    global _redis_sync_pool
    if _redis_sync_pool is None:
        with _sync_pool_lock:  # threading.Lock para contexto síncrono
            if _redis_sync_pool is None:
                _redis_sync_pool = redis_sync.ConnectionPool.from_url(
                    REDIS_URL,
                    max_connections=settings.redis_sync_pool_max_connections,  # 20
                    decode_responses=True,
                    socket_connect_timeout=settings.redis_socket_timeout,
                    socket_timeout=settings.redis_socket_timeout,
                    health_check_interval=30,
                )
    return _redis_sync_pool
```

El pool síncrono utiliza `threading.Lock` en lugar de `asyncio.Lock`, ya que opera fuera del contexto asíncrono. Esta separación es fundamental: mezclar locks asíncronos y síncronos puede causar deadlocks sutiles y difíciles de diagnosticar.

### Ciclo de Vida y Limpieza de Conexiones

El sistema implementa funciones de limpieza coordinadas que se ejecutan durante el shutdown de la aplicación. La función `close_redis_pool()` cierra tanto el pool asíncrono como el síncrono, liberando todas las conexiones al sistema operativo. Esta coordinación es crítica para evitar conexiones huérfanas que podrían agotar los recursos de Redis.

```python
async def close_redis_pool() -> None:
    global _redis_pool, _redis_pool_lock
    if _redis_pool is not None:
        await _redis_pool.close()
        _redis_pool = None
        logger.info("Redis async pool closed")
    _redis_pool_lock = None
    close_redis_sync_client()  # También cierra el pool síncrono
```

La operación de cierre del pool síncrono utiliza un patrón thread-safe con bloque `finally` para garantizar que la referencia global se establezca a `None` incluso si ocurre una excepción durante el cierre.

---

## Capítulo 3: Sistema de Canales y Enrutamiento Inteligente

### Taxonomía de Canales

Los canales en Redis siguen una convención de nombres jerárquica que permite el enrutamiento preciso de eventos según su naturaleza y audiencia objetivo. El archivo `backend/shared/infrastructure/events/channels.py` define siete patrones de canales organizados por dominio.

**Canales de Sucursal (Branch-Level):**
- `branch:{branch_id}:waiters` — Eventos destinados a todos los mozos de una sucursal específica
- `branch:{branch_id}:kitchen` — Eventos para el personal de cocina de la sucursal
- `branch:{branch_id}:admin` — Eventos para administradores y managers de la sucursal

**Canales de Sector (Sector-Level):**
- `sector:{sector_id}:waiters` — Eventos filtrados por sector específico para mozos asignados

**Canales de Sesión (Session-Level):**
- `session:{session_id}` — Eventos para los comensales de una mesa específica activa

**Canales de Usuario (User-Level):**
- `user:{user_id}` — Notificaciones directas a un usuario específico

**Canales de Tenant (Tenant-Level):**
- `tenant:{tenant_id}:admin` — Eventos administrativos a nivel de restaurante completo

### Enrutamiento Selectivo de Eventos

El sistema no difunde todos los eventos a todos los canales indiscriminadamente. En su lugar, implementa un enrutamiento inteligente basado en el tipo de evento, su estado en el ciclo de vida, y la relevancia para cada audiencia.

Cuando se crea un nuevo pedido (`ROUND_PENDING`), el sistema publica en el canal de mozos de la sucursal para que algún mozo lo verifique físicamente en la mesa, y simultáneamente en el canal de administradores para visibilidad en el Dashboard. Notablemente, **no se envía** a cocina en este punto porque el pedido debe ser verificado primero por el mozo. Tampoco se notifica a los comensales, ya que ellos mismos iniciaron el pedido.

Cuando el mozo verifica el pedido y el estado avanza a `ROUND_CONFIRMED`, se notifica a los administradores que ahora pueden enviarlo a cocina. Solo cuando el administrador ejecuta la acción "Enviar a Cocina" (`ROUND_SUBMITTED`), el evento se publica en el canal de cocina donde aparece en la pantalla de "Nuevos Pedidos".

Este enrutamiento selectivo minimiza el ruido de notificaciones y garantiza que cada rol visualice exclusivamente la información relevante para su función operativa.

### Filtrado por Sector

Una característica avanzada del sistema es el filtrado por sector para restaurantes con múltiples zonas de servicio (Interior, Terraza, Barra). El sistema permite enviar eventos únicamente a los mozos asignados al sector correspondiente de la mesa.

Cuando un evento incluye `sector_id`, el sistema publica en dos canales complementarios: el canal específico del sector (`sector:{sector_id}:waiters`) para mozos asignados a ese sector, y el canal general de la sucursal (`branch:{branch_id}:waiters`) como respaldo para garantizar que ningún evento se pierda.

El WebSocket Gateway mantiene un mapeo actualizado de asignaciones mozo-sector mediante el `SectorRepository` con caché TTL de 60 segundos. Este caché reduce drásticamente las consultas a la base de datos durante períodos de alta actividad.

---

## Capítulo 4: Sistema de Publicación de Eventos

### Función Central de Publicación

El corazón del sistema de eventos reside en la función `publish_event()` ubicada en `backend/shared/infrastructure/events/publisher.py`. Esta implementación trasciende un simple wrapper de `redis.publish()` para incorporar múltiples capas de protección y resiliencia.

**Validación de Tamaño:** Antes de cualquier publicación, el sistema verifica que el mensaje no exceda 64KB. Este límite previene problemas de memoria en los suscriptores y latencia excesiva en la red. Si un evento supera este umbral, se registra un warning y la publicación se rechaza con una excepción `ValueError`.

```python
def _validate_event_size(event_json: str, event_type: str) -> bool:
    size = len(event_json.encode('utf-8'))
    if size > MAX_EVENT_SIZE:  # 64KB
        raise ValueError(
            f"Event {event_type} exceeds max size: {size} > {MAX_EVENT_SIZE} bytes"
        )
    return True
```

**Serialización Compacta:** El evento se convierte a JSON sin espacios innecesarios para minimizar el tamaño de transmisión. La serialización incluye manejo especial para objetos `datetime` y otros tipos no serializables nativamente.

**Reintentos con Backoff Exponencial y Jitter:** Si la publicación falla por una desconexión temporal de Redis, el sistema implementa reintentos con backoff exponencial decorrelacionado:

```python
def calculate_retry_delay_with_jitter(attempt: int, base_delay: float = 0.5) -> float:
    exp_delay = base_delay * (2 ** attempt)  # Exponencial
    max_delay = 10.0
    exp_delay = min(exp_delay, max_delay)
    jitter_delay = random.uniform(base_delay, exp_delay)  # Jitter decorrelacionado
    return jitter_delay
```

El **jitter decorrelacionado** previene el problema de "thundering herd" donde múltiples clientes que fallaron simultáneamente reintentan al mismo instante y sobrecargan Redis nuevamente. Con jitter, los reintentos se distribuyen aleatoriamente en el tiempo.

### Circuit Breaker para Resiliencia

El sistema implementa el patrón **Circuit Breaker** en `backend/shared/infrastructure/events/circuit_breaker.py` para prevenir cascadas de fallos cuando Redis no está disponible. El circuit breaker opera en tres estados:

**CLOSED (Normal):** Las publicaciones proceden normalmente. Se mantiene un conteo de fallos consecutivos.

**OPEN (Fallo Rápido):** Después de 5 fallos consecutivos, el circuit breaker se "abre". En este estado, las publicaciones fallan inmediatamente sin intentar contactar a Redis, retornando 0 suscriptores. Esto previene que la aplicación se bloquee esperando timeouts de un Redis que claramente no está respondiendo.

**HALF-OPEN (Recuperación):** Después de 30 segundos en estado OPEN, el circuit breaker permite un número limitado de pruebas (3 llamadas). Si estas pruebas tienen éxito, el circuit breaker retorna a CLOSED. Si fallan, vuelve a OPEN.

```
         5 fallos                    30 segundos
CLOSED ──────────▶ OPEN ──────────────▶ HALF-OPEN
   ▲                                      │
   │         1 éxito                      │ 3 fallos
   └──────────────────────────────────────┘
```

La implementación es thread-safe mediante `threading.Lock`, permitiendo su uso seguro desde múltiples corrutinas o hilos concurrentes:

```python
class EventCircuitBreaker:
    def __init__(
        self,
        failure_threshold: int = 5,
        recovery_timeout: float = 30.0,
        half_open_max_calls: int = 3,
    ):
        self._state = CircuitState.CLOSED
        self._failure_count = 0
        self._lock = threading.Lock()
```

### Publicación a Redis Streams

Además del Pub/Sub tradicional, el sistema soporta publicación a **Redis Streams** mediante `publish_to_stream()`. Los Streams proporcionan persistencia y garantía de entrega para eventos críticos que no deben perderse.

```python
async def publish_to_stream(
    redis_client: redis.Redis,
    stream: str,
    event: Event,
    maxlen: int = 50000,  # ~16 horas a carga pico
) -> str:
```

Los Streams utilizan `XADD` con `maxlen` aproximado para prevenir crecimiento ilimitado. El límite de 50,000 entradas proporciona aproximadamente 16 horas de buffer a carga máxima.

---

## Capítulo 5: Suscripción y Procesamiento de Eventos

### Arquitectura del Suscriptor Redis

El WebSocket Gateway implementa el lado receptor del sistema Pub/Sub en `ws_gateway/redis_subscriber.py`. Esta implementación sigue un patrón de **orquestador delgado** que delega la lógica específica a módulos especializados extraídos durante la refactorización ARCH-MODULAR-09.

El suscriptor utiliza `psubscribe` (pattern subscribe) para escuchar múltiples canales con patrones glob:

```python
channels = [
    "branch:*:waiters",   # Todos los canales de mozos
    "branch:*:kitchen",   # Todos los canales de cocina
    "branch:*:admin",     # Todos los canales de administración
    "sector:*:waiters",   # Todos los canales de sector
    "session:*",          # Todas las sesiones de mesa
]
await pubsub.psubscribe(*channels)
```

### Cola de Backpressure

Los eventos pueden llegar más rápido de lo que el sistema puede procesarlos, especialmente durante picos de actividad. Para manejar esta situación, el suscriptor implementa una cola de backpressure con `collections.deque` y capacidad configurable de 500 eventos (optimizado para sucursales de ~100 mesas).

```python
event_queue: deque[dict] = deque(maxlen=MAX_EVENT_QUEUE_SIZE)  # 500
```

Si la cola alcanza su capacidad máxima, los eventos más antiguos se descartan automáticamente gracias al `maxlen` del deque. El sistema monitorea activamente la **tasa de descarte** mediante `EventDropRateTracker`.

### Monitoreo de Drop Rate

El módulo `ws_gateway/core/subscriber/drop_tracker.py` implementa un tracker de tasa de descarte con ventana deslizante:

```python
class EventDropRateTracker:
    def __init__(
        self,
        window_seconds: float = 60.0,         # Ventana de 60 segundos
        alert_threshold_percent: float = 5.0,  # Alerta si >5% descartados
        alert_cooldown_seconds: float = 300.0, # Cooldown de 5 minutos entre alertas
    ):
```

Si más del 5% de los eventos están siendo descartados en la ventana de 60 segundos, se genera una alerta CRITICAL indicando que el sistema está sobrecargado y requiere atención inmediata. El cooldown de 5 minutos previene tormentas de alertas.

### Procesamiento por Lotes

Para optimizar el rendimiento, los eventos no se procesan individualmente sino en lotes de hasta 50 eventos. Este enfoque reduce la sobrecarga de cambios de contexto y mejora el throughput general del sistema.

El procesamiento de cada lote incluye:
1. Validación del esquema del evento contra tipos conocidos
2. Determinación de destinatarios (qué conexiones WebSocket deben recibir el evento)
3. Envío paralelo a todas las conexiones relevantes mediante `asyncio.gather()`
4. Registro de métricas de éxito/fallo para monitoreo

### Reconexión Automática con Jitter

Si la conexión con Redis se pierde, el suscriptor implementa reconexión automática con backoff exponencial y jitter decorrelacionado:

```python
delay = calculate_delay_with_jitter(reconnect_attempts - 1, _retry_config)
await asyncio.sleep(delay)
pubsub = await _reconnect_pubsub(pubsub, channels)
```

El proceso de reconexión incluye limpieza del pubsub anterior con timeouts de 5 segundos para `unsubscribe` y `close`, creación de un nuevo objeto pubsub, y re-suscripción a todos los canales. Después de 20 intentos fallidos, el suscriptor reporta un error fatal pero continúa intentando indefinidamente.

---

## Capítulo 6: Seguridad con Redis

### Blacklist de Tokens JWT

Cuando un usuario cierra sesión, su token JWT sigue siendo técnicamente válido hasta su expiración natural (15 minutos para access tokens). Para invalidar estos tokens inmediatamente, el sistema mantiene una **blacklist** en Redis implementada en `backend/shared/security/token_blacklist.py`.

**Agregar a Blacklist:** Cuando un usuario ejecuta logout, el `jti` (JWT ID único) de su token se almacena en Redis con clave `auth:token:blacklist:{jti}`. El TTL se calcula dinámicamente para coincidir con el tiempo restante de validez del token, permitiendo que Redis limpie automáticamente las entradas expiradas.

```python
async def blacklist_token(token_jti: str, expires_at: datetime) -> bool:
    ttl_seconds = int((expires_at - now).total_seconds())
    if ttl_seconds <= 0:
        return True  # Token ya expirado, no necesita blacklist
    key = f"{BLACKLIST_PREFIX}{token_jti}"
    await redis.setex(key, ttl_seconds, "1")
```

**Verificación con Pipeline:** Para optimizar la verificación de tokens, el sistema utiliza Redis Pipeline para combinar múltiples consultas en un solo round-trip:

```python
async def check_token_validity(token_jti: str, user_id: int, token_iat: datetime) -> bool:
    async with redis.pipeline(transaction=False) as pipe:
        pipe.exists(f"{BLACKLIST_PREFIX}{token_jti}")
        pipe.get(f"{USER_REVOKE_PREFIX}{user_id}")
        results = await pipe.execute()
    # Procesar ambos resultados con un solo viaje a Redis
```

**Política de Fallo Cerrado (Fail-Closed):** Si Redis no está disponible durante la verificación de blacklist, el sistema asume que el token **está** en la blacklist y rechaza la solicitud. Esta política sigue el principio de seguridad "cuando hay duda, denegar acceso":

```python
except Exception as e:
    logger.error("Failed to check token blacklist - failing closed", ...)
    return True  # Tratar como blacklisted (fail closed)
```

### Revocación Masiva de Tokens

Además de la blacklist individual, el sistema permite revocar **todos** los tokens de un usuario mediante un timestamp de revocación almacenado en `auth:user:revoked:{user_id}`. Cualquier token emitido antes de este timestamp se considera inválido, incluso si no está explícitamente en la blacklist.

Esta funcionalidad es esencial cuando se detecta actividad sospechosa en la cuenta, cuando el usuario cambia su contraseña, o cuando un administrador fuerza el cierre de todas las sesiones de un usuario.

### Rate Limiting con Script Lua Atómico

El sistema protege contra ataques de fuerza bruta limitando los intentos de login a 5 por minuto por dirección de email. La implementación en `backend/shared/security/rate_limit.py` utiliza un **script Lua** para garantizar atomicidad de la operación INCR + EXPIRE:

```lua
local key = KEYS[1]
local limit = tonumber(ARGV[1])
local window = tonumber(ARGV[2])

local count = redis.call('INCR', key)
if count == 1 then
    redis.call('EXPIRE', key, window)
end

local ttl = redis.call('TTL', key)
if ttl == -1 then
    redis.call('EXPIRE', key, window)
    ttl = window
end

return {count, ttl}
```

Este script previene una condición de carrera sutil: sin atomicidad, si el servidor fallara entre INCR y EXPIRE, la clave quedaría sin TTL y el contador nunca se resetearía. El script también maneja el caso donde el TTL se perdió por alguna razón, re-estableciéndolo.

El SHA del script se cachea en memoria para evitar re-transmitirlo en cada llamada. Si Redis reinicia y pierde los scripts cargados, el sistema detecta el error `NOSCRIPT` y recarga automáticamente.

Cuando el límite se excede, el sistema responde con HTTP 429 (Too Many Requests) e incluye el header `Retry-After` con el tiempo restante en segundos.

---

## Capítulo 7: Configuración y Parámetros de Tuning

### Parámetros de Configuración

El archivo `backend/shared/config/settings.py` centraliza toda la configuración de Redis con valores optimizados para el caso de uso de restaurantes:

**Conexión Base:**
| Parámetro | Valor | Descripción |
|-----------|-------|-------------|
| `redis_url` | `redis://localhost:6380` | URL de conexión (puerto 6380 en desarrollo) |
| `redis_socket_timeout` | 5 segundos | Timeout para conexión y operaciones I/O |

**Pools de Conexión:**
| Parámetro | Valor | Descripción |
|-----------|-------|-------------|
| `redis_pool_max_connections` | 50 | Conexiones asíncronas máximas |
| `redis_sync_pool_max_connections` | 20 | Conexiones síncronas máximas |

**Procesamiento de Eventos:**
| Parámetro | Valor | Descripción |
|-----------|-------|-------------|
| `redis_event_queue_size` | 500 | Tamaño de cola de backpressure |
| `redis_event_batch_size` | 50 | Eventos procesados por lote |
| `redis_publish_max_retries` | 3 | Reintentos de publicación |
| `redis_publish_retry_delay` | 0.1s | Delay base para reintentos |

**Reconexión y Timeouts:**
| Parámetro | Valor | Descripción |
|-----------|-------|-------------|
| `redis_max_reconnect_attempts` | 20 | Intentos máximos de reconexión |
| `redis_pubsub_cleanup_timeout` | 5.0s | Timeout para limpieza de pubsub |
| `redis_pubsub_reconnect_total_timeout` | 15.0s | Timeout total de reconexión |

**Control de Calidad:**
| Parámetro | Valor | Descripción |
|-----------|-------|-------------|
| `redis_event_strict_ordering` | false | Si true, eventos reintentados van al frente |
| `redis_event_staleness_threshold` | 5.0s | Advertencia si evento espera >N segundos |

### Recomendaciones de Escalamiento

Para un **restaurante pequeño** (5-10 mesas, ~50 conexiones WebSocket concurrentes), la configuración por defecto es adecuada.

Para **restaurantes medianos** (20-50 mesas, ~200 conexiones concurrentes), se recomienda:
- Aumentar `redis_pool_max_connections` a 100
- Aumentar `redis_event_queue_size` a 2000
- Considerar Redis en hardware dedicado si comparte servidor con PostgreSQL

Para **cadenas con múltiples sucursales** (100+ mesas totales, ~500+ conexiones concurrentes):
- Implementar Redis Cluster o Redis Sentinel para alta disponibilidad
- Aumentar `redis_pool_max_connections` a 200
- Aumentar `redis_sync_pool_max_connections` a 50
- Servidor Redis dedicado con réplica para failover
- Monitoreo activo de métricas de latencia y memoria

---

## Capítulo 8: Monitoreo y Diagnóstico

### Métricas Disponibles

El sistema expone múltiples métricas para monitorear la salud de la infraestructura Redis.

**Estado del Circuit Breaker:**
```python
circuit_breaker.get_stats()
# {
#   "state": "closed",           # closed/open/half_open
#   "failure_count": 0,          # Fallos consecutivos actuales
#   "rejected_count": 234,       # Total de llamadas rechazadas (histórico)
#   "last_failure_time": 1706XXX # Timestamp del último fallo
# }
```

**Drop Rate del Suscriptor:**
```python
_drop_rate_tracker.get_stats()
# {
#   "total_processed": 15000,         # Total de eventos procesados
#   "total_dropped": 12,              # Total de eventos descartados
#   "window_processed": 500,          # Procesados en ventana actual
#   "window_dropped": 0,              # Descartados en ventana actual
#   "window_drop_rate_percent": 0.0,  # Tasa de descarte actual
#   "alert_threshold_percent": 5.0,   # Umbral de alerta
#   "alert_count": 0,                 # Alertas emitidas
#   "window_seconds": 60.0            # Tamaño de ventana
# }
```

**Endpoint de Métricas del WebSocket Gateway:**
```bash
GET /ws/health/detailed
# Retorna: estado de redis_async, info del pool síncrono, estadísticas de conexiones
```

### Diagnóstico de Problemas Comunes

**Problema: Eventos no llegan a los clientes**

1. Verificar que Redis está corriendo: `docker exec integrador_redis redis-cli ping`
2. Verificar suscripción del WebSocket Gateway en logs: "Redis subscriber started"
3. Verificar publicación de eventos en logs del REST API: "Event published to channel"
4. Verificar conexión WebSocket del cliente en consola del navegador
5. Verificar que el cliente está suscrito a los canales correctos

**Problema: Alta latencia en eventos**

1. Verificar tamaño de la cola de eventos (si cerca de maxlen, sistema sobrecargado)
2. Revisar drop rate (si >5%, hay problemas de capacidad)
3. Verificar latencia de Redis: `redis-cli --latency`
4. Verificar si el circuit breaker está en estado OPEN
5. Revisar CPU y memoria del servidor Redis

**Problema: Conexión a Redis falla intermitentemente**

1. Verificar estado del circuit breaker en métricas
2. Buscar en logs: "Redis connection error"
3. Verificar recursos del servidor Redis (memoria, CPU, conexiones)
4. Verificar límite de conexiones de Redis (`maxclients`)
5. Considerar aumentar timeouts si la red tiene latencia variable

**Problema: Rate limiting no funciona**

1. Verificar que Redis está accesible desde el backend
2. Verificar que el script Lua está cargado (buscar "Lua script cache miss" en logs)
3. Verificar que las claves de rate limit tienen TTL correcto: `redis-cli TTL ratelimit:login:email@example.com`

---

## Capítulo 9: Flujos Operativos Detallados

### Flujo: Cliente Realiza un Pedido

1. **pwaMenu** envía POST a `/api/diner/rounds` con los items del pedido
2. **REST API** persiste el pedido en PostgreSQL con estado PENDING
3. **REST API** invoca `publish_round_event(event_type=ROUND_PENDING, ...)`
4. El publicador obtiene conexión del pool asíncrono
5. Se verifica que el circuit breaker permite la operación
6. El evento se serializa a JSON y se valida tamaño (<64KB)
7. Se publica en `branch:5:waiters` y `branch:5:admin`
8. **Redis** recibe los mensajes y los distribuye a los suscriptores
9. **WebSocket Gateway** recibe el evento vía `psubscribe`
10. El evento entra en la cola de backpressure
11. El procesador de lotes toma el evento
12. Se determinan destinatarios: mozos de branch 5, admins de branch 5
13. Se envía el evento por WebSocket a cada cliente conectado relevante
14. **pwaWaiter** recibe el evento y actualiza su UI mostrando el nuevo pedido
15. **Dashboard** recibe el evento y la tarjeta de la mesa parpadea en amarillo

### Flujo: Usuario Ejecuta Logout

1. **Dashboard** envía POST a `/api/auth/logout`
2. **REST API** extrae el `jti` del token JWT del header Authorization
3. **REST API** calcula la expiración del token desde el claim `exp`
4. **REST API** invoca `blacklist_token(jti, expires_at)`
5. Se calcula TTL: `expires_at - now` (tiempo restante de validez)
6. Se almacena en Redis: `SETEX auth:token:blacklist:{jti} {ttl} "1"`
7. El token queda inmediatamente invalidado
8. Cualquier intento de usar ese token será rechazado con 401
9. Después de `ttl` segundos, Redis elimina automáticamente la entrada

### Flujo: Intento de Login con Rate Limiting

1. **Usuario** envía credenciales a `/api/auth/login`
2. **REST API** invoca `check_email_rate_limit(email)`
3. Se ejecuta el script Lua atómico en Redis
4. El contador se incrementa: `INCR ratelimit:login:{email}`
5. Si es el primer intento, se establece TTL de 60 segundos
6. Se verifica si el contador excede 5 (límite configurado)
7. **Si excede**: HTTPException 429 con mensaje "Demasiados intentos"
8. **Si no excede**: el login continúa con verificación de credenciales
9. Después de 60 segundos, Redis elimina la clave automáticamente

---

## Conclusión

Redis en Integrador representa una implementación enterprise-grade que trasciende el uso convencional de almacén de datos en memoria. La arquitectura implementa múltiples capas de resiliencia, desde circuit breakers que previenen cascadas de fallos, hasta reconexión automática con jitter que evita problemas de thundering herd. La separación de pools asíncrono y síncrono optimiza el rendimiento para diferentes patrones de acceso, mientras que el sistema de canales permite enrutamiento inteligente de eventos según rol y contexto.

Las políticas de seguridad siguen el principio fundamental de **fail-closed**: ante cualquier duda o error, el sistema deniega acceso en lugar de permitirlo. El rate limiting atómico mediante Lua previene ataques de fuerza bruta, y la blacklist de tokens proporciona revocación instantánea de sesiones.

El monitoreo integral mediante métricas de circuit breaker, drop rate, y estadísticas de conexión permite identificar problemas antes de que afecten a los usuarios. La configuración flexible soporta desde pequeños restaurantes hasta cadenas con múltiples sucursales.

Esta arquitectura representa las mejores prácticas de la industria para sistemas de eventos en tiempo real, proporcionando la base sólida sobre la cual Integrador construye su experiencia de usuario diferenciada.
