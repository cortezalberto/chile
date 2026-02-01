# La Capa Compartida: Corazón del Backend

## Introducción y Visión Arquitectónica

La carpeta `backend/shared/` constituye el núcleo fundacional del sistema Integrador. Esta capa representa un componente crítico de la arquitectura, diseñada para albergar todos aquellos módulos, utilidades y servicios que trascienden los límites de una única aplicación y deben ser accesibles tanto por la REST API (`rest_api/`) como por el WebSocket Gateway (`ws_gateway/`). Su existencia responde a un principio arquitectónico fundamental: la centralización de responsabilidades transversales evita la duplicación de código y garantiza comportamiento consistente en todo el ecosistema.

El diseño de esta capa sigue los principios de Clean Architecture, donde los módulos compartidos representan el círculo más interno de la aplicación. Las capas externas (routers, endpoints WebSocket) dependen de esta capa, pero nunca al revés. Esta dirección unidireccional de dependencias permite que los cambios en la lógica de presentación no afecten a los servicios fundamentales del sistema.

La estructura actual refleja una organización por responsabilidad funcional:

```
backend/shared/
├── config/              # Configuración centralizada
│   ├── settings.py      # Variables de entorno y constantes configurables
│   ├── logging.py       # Sistema de logging estructurado
│   └── constants.py     # Constantes de dominio y validación de estados
├── security/            # Autenticación y autorización
│   ├── auth.py          # JWT y tokens de mesa
│   ├── password.py      # Hashing con bcrypt
│   ├── token_blacklist.py  # Revocación de tokens via Redis
│   └── rate_limit.py    # Protección contra abuso
├── infrastructure/      # Conexiones a servicios externos
│   ├── db.py            # SQLAlchemy y gestión de sesiones
│   ├── events/          # Sistema de eventos Redis pub/sub y streams
│   │   ├── circuit_breaker.py
│   │   ├── event_schema.py
│   │   ├── channels.py
│   │   ├── redis_pool.py
│   │   ├── publisher.py
│   │   ├── routing.py
│   │   ├── domain_publishers.py
│   │   └── health_checks.py
│   └── redis/
│       └── constants.py  # Prefijos y TTLs centralizados
└── utils/               # Utilidades de propósito general
    ├── exceptions.py    # Excepciones HTTP centralizadas
    ├── validators.py    # Validación de entrada y seguridad
    ├── health.py        # Decoradores para health checks
    ├── schemas.py       # Schemas Pydantic compartidos
    └── admin_schemas.py # Schemas específicos de admin API
```

---

## Capítulo 1: Configuración Centralizada

### El Sistema de Settings

El archivo `settings.py` implementa el patrón de configuración mediante Pydantic BaseSettings, una aproximación moderna que combina la flexibilidad de variables de entorno con la seguridad de tipos de Python. La clase `Settings` actúa como el único punto de verdad para todas las configuraciones del sistema, eliminando la dispersión de valores hardcodeados y facilitando la configuración por ambiente.

La arquitectura de configuración contempla múltiples dominios funcionales. En primer lugar, la conectividad a bases de datos queda definida mediante `database_url`, cuyo valor por defecto apunta a PostgreSQL local pero puede ser sobreescrito via la variable de entorno `DATABASE_URL`. De manera similar, `redis_url` establece la conexión al broker de mensajería, con el puerto 6380 como valor por defecto que coincide con la configuración de Docker Compose del proyecto.

El subsistema de autenticación JWT recibe especial atención en la configuración. Los tokens de acceso mantienen una vida útil deliberadamente corta de 15 minutos (`jwt_access_token_expire_minutes`), una decisión de diseño documentada como SEC-01 que reduce la ventana de exposición en caso de compromiso. Los tokens de refresco extienden esta duración a 7 días, permitiendo sesiones prolongadas sin intervención del usuario. El artefacto CRIT-04 documenta la reducción del tiempo de vida de tokens de mesa de 8 a 3 horas, una medida de hardening para limitar la exposición de tokens compartidos en contextos públicos.

La configuración de WebSocket incorpora límites operacionales críticos para la estabilidad del sistema bajo carga. El parámetro `ws_max_connections_per_user` limita a 3 las conexiones simultáneas por usuario, previniendo el agotamiento de recursos por clientes problemáticos. El límite global `ws_max_total_connections` de 500 conexiones establece un techo de capacidad que protege al servidor de colapso por sobrecarga. El rate limiting por conexión (`ws_message_rate_limit` de 30 mensajes por segundo) previene ataques de denegación de servicio a nivel de protocolo.

Los pools de Redis reciben configuración diferenciada para operaciones síncronas y asíncronas. El pool asíncrono (`redis_pool_max_connections`: 50) soporta las operaciones de pub/sub y eventos en tiempo real, mientras que el pool síncrono (`redis_sync_pool_max_connections`: 20) atiende operaciones bloqueantes como verificación de tokens y rate limiting. Esta separación, documentada como LOAD-LEVEL2, evita que operaciones de bloqueo afecten la latencia del sistema de eventos.

El método `validate_production_secrets()` implementa una validación de arranque que previene despliegues inseguros. En ambiente de producción, el sistema rechaza iniciar si detecta secretos débiles o por defecto, garantizando que JWT_SECRET y TABLE_TOKEN_SECRET cumplan requisitos mínimos de 32 caracteres y no coincidan con valores conocidos como inseguros.

### Configuración de Cookies HttpOnly (SEC-09)

La implementación de SEC-09 introduce cookies HttpOnly para tokens de refresco, una medida crítica contra ataques XSS. Los parámetros `cookie_secure`, `cookie_samesite` y `cookie_domain` controlan el comportamiento de estas cookies. En desarrollo, `cookie_secure` permanece en False para permitir HTTP local, pero en producción debe activarse para requerir HTTPS. El valor "lax" de `samesite` ofrece un balance entre seguridad CSRF y usabilidad, permitiendo navegación top-level mientras bloquea requests cross-site automáticos.

### El Sistema de Logging Estructurado

El módulo `logging.py` implementa un sistema de logging dual que adapta su formato según el ambiente de ejecución. La clase `StructuredFormatter` produce logs en formato JSON para producción, facilitando la ingestión por herramientas de observabilidad como ELK Stack o CloudWatch. La clase `DevelopmentFormatter` genera logs coloreados y legibles para desarrollo local, mejorando la experiencia del desarrollador durante debugging.

La clase `StructuredLogger` extiende el logger estándar de Python para soportar contexto adicional mediante keyword arguments. Esta capacidad permite adjuntar metadata estructurada a cada entrada de log:

```python
logger.info("User logged in", user_id=123, branch_id=5, role="WAITER")
```

El sistema incluye funciones de enmascaramiento para protección de PII (Personally Identifiable Information). La función `mask_email()` transforma direcciones como "user@example.com" en "us***@example.com", preservando suficiente información para debugging mientras protege la identidad del usuario. De manera similar, `mask_jti()` trunca identificadores JWT para logs de seguridad, y `mask_user_id()` oculta parcialmente IDs de usuario en contextos sensibles.

Las funciones de auditoría de seguridad (`audit_ws_connection()`, `audit_auth_event()`, `audit_rate_limit_event()`, `audit_token_event()`) proporcionan un trail de auditoría estructurado para eventos críticos de seguridad. Estas funciones utilizan un logger dedicado `security.audit` que puede configurarse para persistencia especializada o alertas en tiempo real.

### Constantes de Dominio

El archivo `constants.py` centraliza todas las constantes de dominio del sistema, eliminando "magic strings" dispersos en el código. La clase `Roles` define los cuatro roles del sistema (ADMIN, MANAGER, KITCHEN, WAITER) junto con agrupaciones semánticas como `MANAGEMENT_ROLES` (ADMIN, MANAGER) y `STAFF_ROLES` que simplifican las verificaciones de permisos.

Las clases de estado (`RoundStatus`, `TableStatus`, `SessionStatus`, `CheckStatus`, etc.) definen no solo los valores posibles sino también agrupaciones semánticas. Por ejemplo, `RoundStatus.ACTIVE` lista todos los estados donde un pedido está en proceso, mientras que `RoundStatus.KITCHEN_VISIBLE` indica qué estados son visibles en la pantalla de cocina.

El diccionario `ROUND_TRANSITIONS` codifica la máquina de estados de pedidos, definiendo transiciones válidas:

```
PENDING → CONFIRMED → SUBMITTED → IN_KITCHEN → READY → SERVED
```

El diccionario `ROUND_TRANSITION_ROLES` agrega restricciones de rol a cada transición, implementando un control de acceso basado en el flujo de trabajo. Solo meseros pueden confirmar pedidos pendientes, solo management puede enviar a cocina, y solo cocina puede marcar como listo.

Las funciones de validación (`validate_round_status()`, `validate_round_transition()`, `get_allowed_round_transitions()`) proporcionan una API declarativa para verificar estados y transiciones, evitando lógica de validación dispersa en múltiples routers.

La clase `ErrorMessages` centraliza mensajes de error en español, garantizando consistencia lingüística en toda la API. Mensajes como "Categoría no encontrada" o "Permisos insuficientes" se definen una sola vez y se referencian en todo el código.

---

## Capítulo 2: El Sistema de Seguridad

### Autenticación JWT y Tokens de Mesa

El archivo `auth.py` implementa un sistema de autenticación dual que soporta tanto personal del restaurante (via JWT) como comensales en mesa (via tokens de mesa). Esta dualidad refleja los dos flujos de autenticación fundamentales del sistema: empleados que inician sesión con credenciales, y clientes que escanean códigos QR.

La función `sign_jwt()` genera tokens firmados con HS256, incluyendo claims estándar (iss, aud, iat, exp) más claims personalizados del dominio (sub, tenant_id, branch_ids, roles). El artefacto CRIT-AUTH-04 documenta la adición de `jti` (JWT ID) a cada token, un identificador único que habilita la revocación individual de tokens sin invalidar toda la sesión del usuario.

La verificación de tokens (`verify_jwt()`) implementa múltiples capas de validación. Primero, la librería PyJWT valida firma, expiración, issuer y audience. Luego, validaciones adicionales (SHARED-HIGH-03) verifican la presencia y formato de claims requeridos: `sub` debe ser un string numérico válido, `tenant_id` debe ser un entero positivo, y `type` debe ser "access" o "refresh". Finalmente, la función consulta la blacklist de Redis para verificar revocación.

El patrón fail-closed (SHARED-HIGH-01) gobierna el manejo de errores durante la verificación. Si Redis no está disponible para verificar la blacklist, el sistema deniega acceso en lugar de asumirlo. Esta decisión prioriza seguridad sobre disponibilidad, evitando que una falla de Redis permita el uso de tokens potencialmente revocados.

Los tokens de mesa evolucionaron de un formato HMAC propietario a JWT estándar en la Fase 5 del proyecto. La función `sign_table_token()` genera tokens JWT con issuer y audience específicos (`integrador:table`, `integrador:diner`) que los distinguen de tokens de staff. La función `verify_table_token()` mantiene retrocompatibilidad, detectando el formato del token (JWT tiene 3 partes separadas por puntos) y delegando a la función apropiada.

### Hashing de Contraseñas

El módulo `password.py` implementa hashing seguro mediante bcrypt directo, evitando la librería passlib que presentaba problemas de compatibilidad con Python 3.14. La función `hash_password()` genera hashes con 12 rondas de bcrypt, un balance entre seguridad y rendimiento que produce hashes verificables en aproximadamente 250ms.

El artefacto CRIT-AUTH-03 eliminó el soporte para contraseñas en texto plano que existía para compatibilidad legacy. La función `verify_password()` ahora rechaza explícitamente cualquier hash que no comience con los prefijos bcrypt estándar ($2a$, $2b$, $2y$), generando un log de seguridad si detecta intentos de autenticación con formatos no soportados.

### Revocación de Tokens

El servicio `token_blacklist.py` proporciona dos mecanismos de revocación complementarios. La revocación individual agrega el `jti` del token a una clave Redis con TTL igual al tiempo restante de validez del token. La revocación por usuario almacena un timestamp, invalidando todos los tokens emitidos antes de ese momento.

La función `blacklist_token()` calcula el TTL correcto antes de almacenar, evitando entries innecesarios para tokens ya expirados. La función `is_token_blacklisted()` implementa el patrón fail-closed: si Redis no responde, asume que el token está blacklisteado y deniega acceso.

La función `revoke_all_user_tokens()` se utiliza durante logout y cambio de contraseña. Almacena el timestamp actual con TTL igual a la vida máxima de tokens de refresco (7 días), garantizando que cualquier token emitido previamente sea rechazado.

La función optimizada `check_token_validity()` utiliza Redis PIPELINE (PERF-CRIT-01) para verificar tanto blacklist individual como revocación por usuario en un solo round-trip, reduciendo la latencia de verificación a la mitad.

Las variantes síncronas (`*_sync`) utilizan el pool de conexiones síncronas de Redis, evitando problemas de event loop cuando se llaman desde contextos síncronos como middleware de autenticación.

### Rate Limiting

El módulo `rate_limit.py` implementa protección contra abuso combinando la librería slowapi con lógica personalizada basada en Redis. Slowapi proporciona rate limiting por IP para endpoints REST estándar, mientras que la lógica Redis maneja casos especiales como limitación por email en intentos de login.

El rate limiting por email utiliza un script Lua atómico (REDIS-HIGH-06) que garantiza la atomicidad de INCR y EXPIRE. Sin esta atomicidad, una race condition podría dejar keys sin TTL, causando bloqueos permanentes.

```lua
local count = redis.call('INCR', key)
if count == 1 then
    redis.call('EXPIRE', key, window)
end
```

El patrón fail-closed (REDIS-CRIT-01) gobierna el comportamiento ante errores de Redis: si no es posible verificar el rate limit, el sistema deniega la request con HTTP 503 en lugar de permitirla. Este comportamiento, aunque impacta disponibilidad, previene ataques de fuerza bruta cuando el sistema de rate limiting está comprometido.

La función `check_email_rate_limit_sync()` (CRIT-LOCK-03) fue completamente reescrita para usar el cliente Redis síncrono directamente, evitando conflictos de event loop que ocurrían al usar `asyncio.run()` con pools creados en loops diferentes.

---

## Capítulo 3: Infraestructura de Datos y Mensajería

### Gestión de Base de Datos

El módulo `db.py` configura SQLAlchemy para operación eficiente en producción. El engine utiliza connection pooling con parámetros cuidadosamente seleccionados:

- `pool_pre_ping=True`: Verifica conexiones antes de usar, detectando conexiones muertas
- `pool_size=5`: Conexiones permanentes en el pool
- `max_overflow=10`: Conexiones adicionales bajo carga
- `pool_timeout=30`: Tiempo máximo de espera por conexión
- `pool_recycle=1800`: Recicla conexiones cada 30 minutos, evitando timeouts de servidor

La función `get_db()` proporciona un generador para FastAPI Depends, garantizando que cada request reciba una sesión limpia y que ésta se cierre correctamente incluso ante excepciones. El context manager `get_db_context()` ofrece la misma funcionalidad para código fuera de endpoints FastAPI.

La función `safe_commit()` (HIGH-01) encapsula el patrón de commit con rollback automático ante fallos. Esta simple abstracción previene estados inconsistentes cuando una operación de base de datos falla parcialmente.

### El Sistema de Eventos

El paquete `events/` representa la evolución más significativa de la arquitectura, habiendo sido refactorizado desde un archivo monolítico de 1087 líneas a una estructura modular de 9 archivos especializados. Esta refactorización, documentada como ARCHITECTURE, mejora la mantenibilidad y testabilidad del sistema.

#### Circuit Breaker

El módulo `circuit_breaker.py` implementa el patrón Circuit Breaker para proteger el sistema de cascading failures cuando Redis no está disponible. El breaker mantiene tres estados:

- **CLOSED**: Operación normal, las llamadas proceden
- **OPEN**: Fallo detectado, las llamadas se rechazan inmediatamente (fail-fast)
- **HALF_OPEN**: Período de prueba, se permiten llamadas limitadas para detectar recuperación

El breaker se abre después de 5 fallos consecutivos y permanece abierto por 30 segundos antes de transicionar a half-open. En half-open, se permiten máximo 3 llamadas de prueba; si alguna falla, vuelve a OPEN, si todas tienen éxito, transiciona a CLOSED.

La función `calculate_retry_delay_with_jitter()` implementa backoff exponencial con jitter decorrelacionado, previniendo el problema de "thundering herd" donde múltiples clientes reconectan simultáneamente.

#### Schema de Eventos

El dataclass `Event` define la estructura unificada para todos los eventos del sistema:

```python
@dataclass
class Event:
    type: str           # Tipo de evento (ROUND_SUBMITTED, etc.)
    tenant_id: int      # ID del tenant (multi-tenancy)
    branch_id: int      # ID de sucursal
    table_id: int | None
    session_id: int | None
    sector_id: int | None  # Para notificaciones filtradas por sector
    entity: dict        # Datos específicos del evento
    actor: dict         # Quién generó el evento
    ts: str            # Timestamp ISO
    v: int = 1         # Versión del schema
```

El método `__post_init__()` (SHARED-HIGH-06) valida todos los campos al momento de creación, rechazando eventos malformados antes de que lleguen a Redis. Validaciones incluyen: type no vacío, tenant_id positivo, branch_id no negativo (0 es válido para entidades tenant-wide).

#### Channels

El módulo `channels.py` centraliza la nomenclatura de canales Redis:

- `branch:{id}:waiters` - Notificaciones a meseros de una sucursal
- `branch:{id}:kitchen` - Notificaciones a cocina
- `branch:{id}:admin` - Notificaciones al dashboard
- `sector:{id}:waiters` - Notificaciones filtradas por sector
- `session:{id}` - Notificaciones a comensales de una sesión
- `user:{id}` - Notificaciones directas a un usuario
- `tenant:{id}:admin` - Notificaciones tenant-wide para admin

Cada función de canal valida que los IDs sean enteros positivos antes de construir el nombre, previniendo channels inválidos.

#### Redis Pool Management

El módulo `redis_pool.py` gestiona dos pools de conexiones Redis: uno asíncrono para operaciones de pub/sub y eventos, otro síncrono para operaciones bloqueantes como verificación de tokens.

El pool asíncrono utiliza el patrón singleton con double-check locking para thread safety. La inicialización lazy evita crear conexiones hasta que sean necesarias, mientras que el lock garantiza que sólo se cree una instancia incluso bajo carga concurrente.

El pool síncrono (LOAD-LEVEL2) utiliza `redis.ConnectionPool` que permite múltiples clientes compartir un pool de conexiones. Cada llamada a `get_redis_sync_client()` obtiene un cliente que automáticamente adquiere y libera conexiones del pool, soportando operaciones concurrentes sin contención.

Ambos pools configuran `health_check_interval=30` (PERF-MED-02) para auto-detectar conexiones muertas y reciclarlas antes de que causen errores.

#### Publishing

El módulo `publisher.py` implementa la publicación de eventos con resiliencia:

1. Valida tamaño del evento (máximo 64KB para prevenir mensajes enormes)
2. Consulta circuit breaker antes de intentar
3. Ejecuta publish con retry configurable (default 3 intentos)
4. Aplica backoff exponencial con jitter entre reintentos
5. Registra éxito o fallo en el circuit breaker

La función `publish_to_stream()` utiliza Redis Streams (XADD) en lugar de pub/sub para eventos críticos. Streams proporcionan persistencia y la capacidad de "catch-up" si el Gateway se reinicia, garantizando que ningún evento crítico se pierda.

#### Domain Publishers

El módulo `domain_publishers.py` proporciona funciones de alto nivel para publicar eventos de dominio:

- `publish_round_event()`: Eventos del ciclo de vida de pedidos
- `publish_service_call_event()`: Llamadas de servicio (mesero, ayuda de pago)
- `publish_check_event()`: Eventos de cuenta y pago
- `publish_table_event()`: Eventos de sesión de mesa
- `publish_admin_crud_event()`: Cambios de entidades para sync del Dashboard

Estas funciones encapsulan la lógica de routing, determinando a qué canales enviar según el tipo de evento. Por ejemplo, eventos de pedido se envían a waiters, kitchen (para ciertos estados), admin, y session (para estados visibles al comensal).

La migración a Redis Streams (CRIT-ARCH-01) para eventos críticos garantiza entrega confiable. Los eventos se publican al stream `events:critical` que el Gateway consume mediante Consumer Groups, permitiendo procesamiento distribuido y recovery ante fallos.

#### Constantes Redis

El archivo `redis/constants.py` centraliza prefijos de keys y TTLs:

```python
PREFIX_AUTH_BLACKLIST = "auth:token:blacklist:"
PREFIX_AUTH_USER_REVOKE = "auth:user:revoked:"
PREFIX_CACHE_PRODUCT = "cache:product:"
PREFIX_RATELIMIT_LOGIN = "ratelimit:login:"
STREAM_EVENTS_CRITICAL = "events:critical"
CONSUMER_GROUP_WS_GATEWAY = "ws_gateway_group"
```

Esta centralización previene typos en nombres de keys y facilita auditoría de uso de Redis.

---

## Capítulo 4: Utilidades y Schemas

### Excepciones Centralizadas

El módulo `exceptions.py` define una jerarquía de excepciones HTTP que combina logging automático con respuestas estandarizadas. La clase base `AppException` extiende `HTTPException` de FastAPI, agregando logging estructurado al momento de creación.

Las excepciones específicas proporcionan constructores semánticos:

```python
raise NotFoundError("Producto", product_id, tenant_id=tenant_id)
# Produce: 404 "Producto con ID 123 no encontrado"
# Log: {"level": "WARNING", "entity": "Producto", "entity_id": 123, ...}
```

Las clases `ForbiddenError`, `BranchAccessError`, e `InsufficientRoleError` manejan errores de autorización con mensajes apropiados. La clase `ValidationError` y sus derivadas (`InvalidStateError`, `InvalidTransitionError`, `DuplicateEntityError`) cubren errores de validación de negocio.

La clase `ExternalServiceError` distingue entre servicios no disponibles (503) y errores de gateway (502), incluyendo el header `Retry-After` cuando es aplicable.

### Validadores de Seguridad

El módulo `validators.py` implementa validaciones críticas de seguridad, particularmente para prevención de XSS y SSRF.

La función `validate_image_url()` implementa múltiples capas de defensa:

1. **Scheme validation**: Rechaza javascript:, data:, file:, y otros schemes peligrosos
2. **SSRF prevention**: Bloquea hosts internos (localhost, 127.0.0.1, rangos privados 10.x, 172.16-31.x, 192.168.x) y endpoints de metadata cloud (169.254.169.254)
3. **Domain whitelist** (modo estricto): En producción puede limitarse a CDNs autorizados
4. **Length limit**: Rechaza URLs mayores a 2048 caracteres

La función `escape_like_pattern()` (HIGH-01) escapa caracteres especiales de SQL LIKE (% y _) previniendo ataques de pattern injection que podrían causar full table scans.

La función `sanitize_search_term()` normaliza términos de búsqueda, removiendo caracteres de control y limitando longitud.

### Health Checks

El módulo `health.py` (ARCH-OPP-03) proporciona decoradores para implementar health checks con timeout consistente:

```python
@health_check_with_timeout(timeout=3.0, component="redis")
async def check_redis_health():
    await redis.ping()
    return {"pool_size": 10}
```

El decorador envuelve la función en timeout protection, captura excepciones, mide latencia, y retorna un `HealthCheckResult` estructurado que incluye status, componente, latencia_ms, error (si aplica), y details opcionales.

La función `aggregate_health_checks()` ejecuta múltiples checks en paralelo y agrega resultados, determinando el status global (healthy si todos healthy, degraded si alguno falla).

### Schemas Pydantic

El archivo `schemas.py` contiene los schemas Pydantic utilizados por la API pública y endpoints de operación. Incluye:

- **Autenticación**: `LoginRequest`, `LoginResponse`, `UserInfo`, `RefreshTokenRequest`
- **Mesa y Sesión**: `TableCard`, `TableSessionResponse`, `TableSessionDetail`
- **Pedidos**: `SubmitRoundRequest`, `RoundOutput`, `RoundItemOutput`, `UpdateRoundStatusRequest`
- **Facturación**: `RequestCheckResponse`, `CashPaymentRequest`, `PaymentResponse`, `CheckDetailOutput`
- **Catálogo**: `ProductOutput`, `CategoryOutput`, `MenuOutput`, y schemas de perfil dietético/alérgenos
- **Fidelización**: `DeviceHistoryOutput`, `ImplicitPreferencesData`, `CustomerOutput`, `CustomerSuggestionsOutput`
- **Flujo Mesero**: `WaiterActivateTableRequest`, `WaiterSubmitRoundRequest`, `ManualPaymentRequest`

El archivo `admin_schemas.py` contiene schemas específicos para el Dashboard administrativo, separados por Clean Architecture (los servicios no deben importar de la capa de routers):

- **Entidades**: `TenantOutput`, `BranchOutput`, `CategoryOutput`, `ProductOutput`, `AllergenOutput`, `TableOutput`, `StaffOutput`
- **Creación/Actualización**: Schemas `*Create` y `*Update` para cada entidad con validadores Pydantic
- **Operaciones Bulk**: `TableBulkCreate`, `WaiterSectorBulkAssignment`
- **Reportes**: `DailySalesOutput`, `TopProductOutput`, `SalesReportOutput`

Los schemas de creación y actualización incluyen validadores de imagen (`@field_validator("image")`) que invocan `validate_image_url()` para prevenir XSS/SSRF en datos ingresados por usuarios.

---

## Capítulo 5: Patrones de Integración

### Imports Canónicos

El sistema establece paths de importación estándar que deben usarse consistentemente:

```python
# Configuración
from shared.config.settings import settings, REDIS_URL, DATABASE_URL
from shared.config.logging import get_logger, mask_email, security_audit_logger
from shared.config.constants import Roles, RoundStatus, MANAGEMENT_ROLES

# Seguridad
from shared.security.auth import current_user_context, verify_jwt, sign_table_token
from shared.security.password import hash_password, verify_password
from shared.security.token_blacklist import revoke_all_user_tokens, is_token_blacklisted_sync
from shared.security.rate_limit import check_email_rate_limit_sync

# Infraestructura
from shared.infrastructure.db import get_db, safe_commit
from shared.infrastructure.events import (
    get_redis_pool, publish_event, Event,
    channel_branch_waiters, publish_round_event
)

# Utilidades
from shared.utils.exceptions import NotFoundError, ForbiddenError, ValidationError
from shared.utils.validators import validate_image_url, escape_like_pattern
from shared.utils.health import health_check_with_timeout, HealthCheckResult
from shared.utils.schemas import LoginResponse, TableCard, RoundOutput
from shared.utils.admin_schemas import ProductOutput, CategoryCreate
```

### Patrones de Uso Común

**Autenticación en Routers:**
```python
@router.get("/protected")
def protected_endpoint(
    db: Session = Depends(get_db),
    ctx: dict = Depends(current_user_context)
):
    user_id = int(ctx["sub"])
    tenant_id = ctx["tenant_id"]
    roles = ctx["roles"]
```

**Publicación de Eventos:**
```python
redis = await get_redis_pool()
await publish_round_event(
    redis_client=redis,
    event_type=ROUND_SUBMITTED,
    tenant_id=tenant_id,
    branch_id=branch_id,
    table_id=table_id,
    session_id=session_id,
    round_id=round.id,
    round_number=round.round_number,
    actor_user_id=user_id,
    actor_role="WAITER",
    sector_id=table.sector_id,
)
```

**Manejo de Errores:**
```python
# Búsqueda con 404
product = db.scalar(select(Product).where(Product.id == product_id))
if not product:
    raise NotFoundError("Producto", product_id, tenant_id=tenant_id)

# Validación de permisos
if user["branch_ids"] and branch_id not in ctx["branch_ids"]:
    raise BranchAccessError(branch_id=branch_id, user_id=user_id)

# Validación de transición
if not validate_round_transition(round.status, new_status):
    raise InvalidTransitionError("Round", round.status, new_status)
```

---

## Capítulo 6: Consideraciones de Producción

### Checklist de Seguridad

Antes de desplegar a producción, verificar:

1. **Secretos**: `JWT_SECRET` y `TABLE_TOKEN_SECRET` deben ser strings aleatorios de al menos 32 caracteres
2. **CORS**: `ALLOWED_ORIGINS` debe listar explícitamente los dominios permitidos
3. **Cookies**: `COOKIE_SECURE=true` para requerir HTTPS
4. **Debug**: `DEBUG=false` y `ENVIRONMENT=production`
5. **Rate Limiting**: Verificar que los límites son apropiados para el tráfico esperado

### Observabilidad

El sistema produce logs estructurados en JSON que pueden ser ingestados por:
- ELK Stack (Elasticsearch, Logstash, Kibana)
- CloudWatch Logs
- Datadog
- Cualquier sistema que soporte JSON logs

Los logs de seguridad (`security.audit`) deben configurarse para retención extendida y alertas en patrones sospechosos.

### Escalabilidad

La configuración de pools Redis soporta hasta ~500 conexiones WebSocket concurrentes con la configuración por defecto. Para escalar más allá:

1. Aumentar `redis_pool_max_connections` y `redis_sync_pool_max_connections`
2. Considerar Redis Cluster para sharding
3. Implementar múltiples instancias del Gateway con load balancing

### Resiliencia

El circuit breaker previene cascading failures, pero requiere monitoreo:
- Alertar cuando el breaker se abre (indica problemas de conectividad Redis)
- Monitorear métricas de `rejected_count` para detectar degradación prolongada

---

## Conclusión

La capa `shared/` representa más que una simple colección de utilidades compartidas. Es el corazón arquitectónico del sistema Integrador, donde convergen las decisiones fundamentales de seguridad, configuración, y comunicación. Su diseño modular, documentado mediante artefactos de auditoría (CRIT-*, HIGH-*, etc.), refleja una evolución continua hacia mayor robustez y mantenibilidad.

La separación clara de responsabilidades (config, security, infrastructure, utils) permite que equipos trabajen independientemente en diferentes aspectos del sistema. Los patrones establecidos (fail-closed, circuit breaker, structured logging) garantizan comportamiento predecible incluso en condiciones de fallo.

Para cualquier desarrollador trabajando en el proyecto, comprender esta capa es fundamental. Aquí se definen los contratos que todas las demás capas deben respetar, desde cómo se validan tokens hasta cómo se publican eventos. Es, en el sentido más literal, el fundamento sobre el cual se construye todo lo demás.
