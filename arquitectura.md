# Arquitectura del Sistema Integrador

## Documento Técnico de Arquitectura - Estado Actual Febrero 2026

---

## Visión General

El sistema Integrador constituye una plataforma integral de gestión de restaurantes diseñada para orquestar la totalidad de operaciones desde el momento en que un cliente escanea un código QR hasta la finalización del pago. La arquitectura ha sido concebida con un enfoque multi-tenant que permite a múltiples restaurantes operar de forma completamente aislada sobre la misma infraestructura, maximizando la eficiencia operativa mientras garantiza la segregación absoluta de datos sensibles.

La plataforma se materializa a través de cinco componentes principales que colaboran en tiempo real mediante una combinación de APIs REST para operaciones transaccionales y WebSockets para sincronización instantánea de eventos. Esta dualidad de protocolos permite alcanzar un balance óptimo entre consistencia de datos y experiencia de usuario fluida, donde las operaciones críticas como pagos y confirmaciones de pedidos mantienen garantías ACID mientras las actualizaciones de estado fluyen instantáneamente a través del sistema.

El sistema ha sido optimizado para soportar entre cuatrocientos y seiscientos usuarios concurrentes por instancia, con capacidad de escalar horizontalmente mediante la adición de instancias del WebSocket Gateway que comparten estado a través de Redis. Esta arquitectura permite que un restaurante con múltiples sucursales pueda gestionar simultáneamente cientos de mesas activas sin degradación perceptible del rendimiento.

---

## Principios Arquitectónicos Fundamentales

La arquitectura del sistema Integrador se fundamenta en cinco principios rectores que guían todas las decisiones de diseño y que han sido refinados a través de múltiples ciclos de auditoría y optimización durante enero y febrero de dos mil veintiséis.

El principio de Separación de Responsabilidades establece que cada componente del sistema posee una responsabilidad claramente definida y acotada. El Dashboard gestiona operaciones administrativas, pwaMenu maneja la experiencia del cliente, pwaWaiter optimiza el flujo de trabajo del mesero, el REST API procesa lógica de negocio, y el WebSocket Gateway orquesta comunicación en tiempo real. Esta separación no es meramente organizativa sino que se refleja en la estructura física del código, donde cada componente reside en su propio directorio con sus propias dependencias y configuraciones.

El principio de Arquitectura Limpia se implementa estrictamente en el backend, donde los routers actúan como controladores delgados que únicamente manejan concerns HTTP, los servicios de dominio encapsulan toda la lógica de negocio, y los repositorios abstraen completamente el acceso a datos. Esta estructura garantiza que los cambios en una capa no propaguen efectos colaterales a otras, facilitando tanto el testing como la evolución del sistema.

El Diseño Reactivo permea todos los frontends mediante Zustand como gestor de estado con patrones de suscripción selectiva que previenen re-renderizados innecesarios. La arquitectura de eventos del WebSocket Gateway permite que los cambios se propaguen instantáneamente a todos los clientes conectados sin polling, manteniendo sincronización en tiempo real entre múltiples dispositivos que interactúan con la misma sesión de mesa.

La Seguridad en Profundidad implementa múltiples capas de protección incluyendo autenticación JWT con tokens de corta duración de quince minutos para access tokens, validación de origen en WebSockets, rate limiting por endpoint y por conexión, validación exhaustiva de entrada para prevenir ataques de inyección, y un patrón fail-closed donde cualquier error de seguridad resulta en denegación de acceso.

La Escalabilidad Horizontal se logra mediante sharding de locks, broadcast paralelo con batching, y pools de conexiones Redis configurables. El sistema implementa worker pools para broadcasting y circuit breakers para resiliencia ante fallos de dependencias externas.

---

## Stack Tecnológico

El stack tecnológico ha sido seleccionado para maximizar productividad de desarrollo, rendimiento en producción, y mantenibilidad a largo plazo. En la capa frontend, el Dashboard utiliza React versión diecinueve con Zustand y TailwindCSS cuatro, aprovechando el React Compiler para memoización automática y los selectores de Zustand versión cinco. La aplicación pwaMenu también emplea React diecinueve con Zustand e i18next para internacionalización completa en español, inglés y portugués, funcionando como PWA offline-first. La aplicación pwaWaiter implementa React diecinueve con Zustand y Push API para notificaciones nativas, con agrupación por sectores.

En la capa de servicios backend, el REST API está construido con FastAPI, SQLAlchemy dos punto cero y Pydantic versión dos, aprovechando async nativo, tipado fuerte y validación automática. El WebSocket Gateway utiliza FastAPI WebSocket con Redis Streams para conexiones bidireccionales y entrega garantizada de eventos.

La capa de datos emplea PostgreSQL dieciséis con la extensión pgvector para soporte vectorial necesario en RAG, proporcionando garantías ACID completas. Redis siete funciona como capa de cache y mensajería, soportando Pub/Sub, Streams, rate limiting mediante scripts Lua, y blacklist de tokens. Docker Compose orquesta todos los servicios en ambiente local de desarrollo.

---

## Topología de Componentes

La arquitectura del sistema se organiza en tres capas horizontales que comunican mediante protocolos bien definidos. La capa de presentación comprende el Dashboard operando en el puerto cinco mil ciento setenta y siete para administradores y managers, con quince stores Zustand y cien tests Vitest. La aplicación pwaMenu corre en el puerto cinco mil ciento setenta y seis para clientes, con arquitectura de store modular e internacionalización trilingüe. La aplicación pwaWaiter opera en el puerto cinco mil ciento setenta y ocho para meseros, con tres stores y agrupación por sectores. Las integraciones externas como Mercado Pago comunican mediante webhooks.

Todos los frontends se conectan a la capa de servicios mediante HTTP REST y WebSocket. El REST API en el puerto ocho mil contiene nueve grupos de routers con dieciséis routers administrativos, diez servicios de dominio siguiendo Clean Architecture, y repositorios TenantRepository y BranchRepository. El WebSocket Gateway en el puerto ocho mil uno comprende doce mil seiscientas cinco líneas organizadas en cincuenta y un archivos Python, implementando el Connection Manager, Redis Subscriber con sistema híbrido de Streams y Pub/Sub, Event Router con filtrado por tenant, y Worker Pool con diez workers para escalabilidad.

La capa de datos incluye PostgreSQL en el puerto cinco mil cuatrocientos treinta y dos con cincuenta y dos modelos SQLAlchemy distribuidos en dieciocho archivos de dominio, todos heredando de AuditMixin para trazabilidad universal. Redis opera en el puerto seis mil trescientos ochenta, soportando Streams para eventos críticos, Pub/Sub para eventos de tiempo real, Token Blacklist para revocación de sesiones, Rate Limiting mediante scripts Lua atómicos, y Sector Cache con TTL de sesenta segundos.

---

## Dashboard: Centro de Control Administrativo

El Dashboard constituye el centro de control administrativo del sistema, implementado como una Single Page Application con React diecinueve y el React Compiler habilitado para memoización automática. La aplicación gestiona quince stores Zustand con persistencia en localStorage, cada uno especializado en un dominio específico incluyendo autenticación, sucursales, categorías, productos, alérgenos, personal, promociones y mesas.

La arquitectura interna se organiza en diecinueve páginas funcionales que cubren todo el espectro administrativo: gestión de sucursales y sectores, catálogo completo con precios por sucursal, sistema de alérgenos con reacciones cruzadas, personal con roles por sucursal, y promociones multi-sucursal. El sistema de mesas implementa un workflow de cinco estados con animaciones visuales que reflejan el estado de cada orden en tiempo real.

Los componentes UI, organizados en veinticinco primitivos reutilizables con React.memo optimizado, logran una reducción del treinta y cinco por ciento en re-renderizados innecesarios. El patrón useFormModal y useConfirmDialog ha sido adoptado en nueve de once páginas con formularios, consolidando la gestión de estado modal en hooks reutilizables.

El Dashboard implementa sincronización multi-pestaña mediante BroadcastChannel para autenticación, garantizando que el logout en una pestaña se propague instantáneamente a todas las demás. Los cien tests Vitest cubren stores, hooks personalizados, y flujos críticos de negocio.

El sistema de mesas implementa un workflow de estados con animaciones CSS específicas. La animación animate-pulse-warning muestra pulso amarillo para órdenes pendientes, animate-pulse-urgent pulso púrpura para cuenta solicitada, animate-status-blink parpadeo azul para cambios de estado, y animate-ready-kitchen-blink parpadeo naranja para el estado combinado de listo más cocina. Los WebSocket events se manejan mediante useTableWebSocket que actualiza el store con debounce para eventos de cambio de estado de mesa, evitando llamadas API duplicadas.

---

## pwaMenu: Interfaz de Clientes

La aplicación pwaMenu representa la interfaz principal de interacción con clientes, diseñada como una Progressive Web App completamente funcional offline. La arquitectura de service workers con Workbox implementa estrategias de cache diferenciadas: CacheFirst para imágenes de productos con treinta días de retención, NetworkFirst con timeout de cinco segundos para APIs, y SPA fallback para navegación offline.

El sistema soporta internacionalización completa en español, inglés y portugués mediante i18next, con detección automática del idioma del navegador y persistencia de la preferencia del usuario. Cada error de validación y mensaje de la interfaz posee una clave i18n correspondiente en los tres archivos de traducción.

El flujo de usuario comienza cuando el cliente escanea un código QR en la mesa, lo que inicia una sesión vinculada al dispositivo mediante un UUID persistido en localStorage. Múltiples comensales pueden unirse a la misma sesión usando códigos de cuatro dígitos, habilitando ordenamiento colaborativo donde cada comensal mantiene su propio carrito pero visualiza los pedidos de todos. El sistema de confirmación grupal, implementado mediante el componente RoundConfirmationPanel, requiere que todos los comensales aprueben antes de enviar la ronda a cocina.

La arquitectura de estado utiliza un tableStore modular dividido en cuatro archivos: store.ts con la definición Zustand y acciones, selectors.ts con hooks memoizados, helpers.ts con funciones puras para cálculos, y types.ts con interfaces TypeScript. Este patrón ha probado ser altamente mantenible y testeable.

El sistema de filtrado avanzado permite a los clientes excluir productos por alérgenos con detección de reacciones cruzadas, preferencias dietéticas como vegetariano, vegano, keto y bajo en sodio, y métodos de cocción. Estas preferencias se persisten como preferencias implícitas vinculadas al device_id, permitiendo que clientes recurrentes encuentren sus filtros ya aplicados mediante el hook useImplicitPreferences que sincroniza cambios al backend con debounce de dos segundos.

El carrito colaborativo implementa React diecinueve useOptimistic para actualizaciones optimistas con rollback automático. Cuando un comensal añade un ítem, la UI se actualiza instantáneamente mientras la operación se confirma en background. La confirmación grupal mediante RoundConfirmationPanel requiere que todos los comensales en la sesión confirmen antes del envío, con timeout de cinco minutos y capacidad del proponente de cancelar.

---

## pwaWaiter: Optimización del Flujo de Meseros

La aplicación pwaWaiter optimiza el flujo de trabajo de meseros mediante una interfaz móvil diseñada para condiciones de conectividad variable. La arquitectura implementa un sistema de cola de reintentos para operaciones fallidas, garantizando que ninguna acción se pierda incluso con conectividad intermitente.

Los meseros visualizan únicamente las mesas de los sectores asignados para el día actual, con la vista organizada en grupos por sector. Cada grupo muestra un encabezado con el nombre del sector, conteo de mesas, e indicadores de urgencia cuando hay órdenes pendientes o llamadas de servicio activas.

La funcionalidad Comanda Rápida permite a meseros tomar pedidos para clientes sin smartphone, utilizando un menú compacto sin imágenes optimizado para rendimiento. El componente AutogestionModal implementa una vista dividida con el catálogo a la izquierda y el carrito a la derecha, facilitando la selección rápida de productos.

El sistema de notificaciones push utiliza Web Push API para alertar a meseros cuando una ronda está lista para servir o cuando un cliente solicita atención. El servicio de notificaciones gestiona permisos, suscripción a push, y reproducción de sonidos de alerta.

La verificación de asignación de sucursal ocurre en dos fases: selección pre-login de sucursal desde el endpoint público de branches, seguida de verificación post-login mediante el endpoint de verificación de asignación. Este flujo garantiza que los meseros solo puedan acceder a sucursales donde están asignados para el día actual.

---

## REST API: Núcleo de Lógica de Negocio

El REST API constituye el núcleo de procesamiento de lógica de negocio del sistema. Implementado con FastAPI, la arquitectura sigue estrictamente el patrón Clean Architecture con cuatro capas bien definidas que han sido refinadas a través de múltiples ciclos de refactorización.

Los routers se organizan en nueve grupos funcionales con dieciséis routers administrativos dedicados. Cada router actúa como controlador delgado que únicamente maneja concerns HTTP: parsing de parámetros mediante Pydantic, inyección de dependencias para autenticación, y construcción de respuestas. La lógica de negocio se delega íntegramente a servicios de dominio.

Los servicios de dominio, implementados en el directorio services/domain, encapsulan todas las reglas de negocio. Los diez servicios activos comprenden CategoryService, SubcategoryService, ProductService, AllergenService, BranchService, SectorService, TableService, StaffService, PromotionService y TicketService. Todos heredan de clases base que proporcionan operaciones CRUD estándar con hooks de extensión para validación en creación, validación en actualización, acciones post-creación y acciones post-eliminación.

Los repositorios TenantRepository y BranchRepository abstraen completamente el acceso a datos, proporcionando métodos tipados con eager loading preconfigurado que previene el problema N+1. Los repositorios implementan filtrado automático por tenant_id y branch_id según corresponda, garantizando aislamiento multi-tenant a nivel de infraestructura.

Los modelos SQLAlchemy, organizados en veinte archivos por dominio, definen cincuenta y cuatro clases que heredan de AuditMixin para trazabilidad automática. Cada entidad registra quién la creó, modificó o eliminó, junto con timestamps precisos.

La estructura de routers se organiza por dominio de responsabilidad con separación clara entre operaciones públicas, autenticadas y administrativas. El directorio common contiene utilidades compartidas como dependencias comunes y paginación estandarizada. El directorio admin contiene dieciséis routers para operaciones CRUD administrativas. Los demás directorios incluyen auth para autenticación JWT con refresh HttpOnly, public para endpoints sin autenticación, tables para sesiones de mesa y flujo QR, content para catálogos, ingredientes, recetas y RAG, diner para operaciones de comensal con X-Table-Token, waiter para operaciones de mesero con filtrado por sector, kitchen para rounds y tickets de cocina, y billing para pagos y webhooks de Mercado Pago.

---

## Servicios de Dominio y Sistema de Permisos

El sistema implementa diez servicios de dominio que heredan de clases base especializadas. BaseCRUDService proporciona operaciones CRUD estándar con hooks de extensión, mientras BranchScopedService añade filtrado automático por branch_id. Cada servicio recibe en su constructor la sesión de base de datos, el modelo a gestionar, el schema de salida y el nombre de entidad para mensajes de error en español.

Los servicios implementados cubren todos los dominios principales. CategoryService gestiona categorías con validación de unicidad de nombre por branch. SubcategoryService maneja subcategorías validando que la categoría padre exista. ProductService implementa gestión completa de BranchProduct, alérgenos, ingredientes y perfiles dietéticos. AllergenService administra alérgenos con manejo de reacciones cruzadas M:N. BranchService gestiona configuración de sucursal. SectorService valida pertenencia a branch. TableService genera códigos únicos alfanuméricos para mesas. StaffService maneja usuarios con roles por sucursal y restricciones de MANAGER. PromotionService gestiona branches e items asociados con validación de fechas. TicketService valida transiciones de estado de tickets de cocina.

El sistema de permisos utiliza Strategy Pattern con Interface Segregation Principle para manejar las diferencias entre roles de forma extensible. La clase PermissionContext actúa como facade que simplifica el acceso a permisos, exponiendo propiedades como is_admin, is_management, tenant_id y branch_ids, junto con métodos para requerir acceso de gestión y verificar capacidades según acción, tipo de entidad y contexto.

Las estrategias implementadas cubren cada rol con sus permisos específicos. AdminStrategy proporciona acceso total sin restricciones. ManagerStrategy permite CRUD limitado a Staff, Tables, Allergens y Promotions en branches asignadas, pero sin capacidad de eliminación. KitchenStrategy solo permite lectura de productos y actualización de tickets y rounds. WaiterStrategy permite lectura de mesas del sector asignado y actualización de rounds.

Los mixins NoCreateMixin, NoDeleteMixin, NoUpdateMixin y BranchFilterMixin permiten composición flexible de comportamientos, siguiendo el principio de segregación de interfaces.

---

## WebSocket Gateway: Comunicación en Tiempo Real

El WebSocket Gateway proporciona comunicación bidireccional en tiempo real entre el servidor y todos los clientes conectados. Con doce mil seiscientas cinco líneas de código organizadas en cincuenta y un archivos Python, representa el componente más complejo del sistema desde la perspectiva de concurrencia y resiliencia.

La arquitectura modular se organiza en dos capas principales. El directorio core contiene los módulos extraídos de los archivos monolíticos originales mediante la refactorización ARCH-MODULAR, donde connection_manager.py pasó de novecientas ochenta y siete a cuatrocientas noventa y cinco líneas, y redis_subscriber.py de seiscientas sesenta y seis a trescientas veintiséis líneas. El directorio components implementa la arquitectura de dominios con doce subdirectorios especializados.

El ConnectionManager orquesta el ciclo de vida de conexiones utilizando composición de módulos especializados. ConnectionLifecycle maneja registro y desregistro con locks apropiados. ConnectionBroadcaster implementa envío paralelo con worker pool de diez workers. ConnectionCleanup elimina conexiones muertas y stale. ConnectionStats agrega métricas de operación.

El RedisSubscriber procesa eventos mediante un sistema híbrido de Pub/Sub para eventos de tiempo real y Redis Streams para eventos críticos que requieren entrega garantizada. EventDropRateTracker monitorea tasas de descarte y emite alertas cuando superan el cinco por ciento. StreamConsumer implementa consumer groups con capacidad de rewind y dead letter queue para mensajes irrecuperables.

---

## ConnectionIndex y Sistema de Locks

ConnectionIndex actúa como Value Object que mantiene todos los índices de conexiones y mappings inversos. Los índices principales incluyen by_user, by_branch, by_session, by_sector, admins_by_branch y kitchen_by_branch. Los mappings inversos como ws_to_user, ws_to_tenant y demás permiten O(1) cleanup durante desconexiones.

LockManager implementa locks sharded para reducir contención en escenarios de alta concurrencia. El orden de adquisición de locks está estrictamente definido para prevenir deadlocks: primero connection_counter_lock como lock global, luego user_lock por usuario en orden ascendente de user_id, seguido de branch_locks por branch en orden ascendente de branch_id, y finalmente sector_lock, session_lock y dead_connections_lock como locks globales para operaciones específicas.

El componente LockSequence valida que este orden se respete y lanza DeadlockRiskError ante violaciones. Este context manager garantiza que los locks se adquieren siempre en el mismo orden, liberándose automáticamente en orden inverso al salir del contexto. Este patrón garantiza que dos coroutines que necesitan los mismos locks nunca se bloqueen mutuamente, ya que siempre los adquieren en el mismo orden.

---

## Broadcast y Worker Pool

BroadcastRouter implementa Strategy Pattern con dos estrategias intercambiables. BatchBroadcastStrategy utiliza batches de tamaño fijo configurado típicamente en cincuenta conexiones. AdaptiveBatchStrategy ajusta el tamaño según latencia observada, aumentando cuando la latencia es baja y reduciendo cuando aumenta. El patrón Observer permite registrar observadores de métricas sin acoplar la lógica de broadcast, implementado mediante MetricsObserverAdapter que notifica después de cada broadcast completado o cuando se aplica rate limiting.

ConnectionBroadcaster implementa un worker pool de diez workers asincrónicos que procesan tareas de envío desde una cola. Para broadcasts grandes con más de cincuenta conexiones, los envíos se distribuyen entre workers para procesamiento verdaderamente paralelo. Los futures permiten trackear completitud y agregar métricas. Este enfoque logra aproximadamente ciento sesenta milisegundos para broadcast a cuatrocientos usuarios versus cuatro mil milisegundos con envío secuencial.

---

## Endpoints WebSocket y Mixins

La jerarquía de clases de endpoints implementa Template Method para el ciclo de vida y composición mediante mixins para comportamientos reutilizables. WebSocketEndpointBase es la clase abstracta que define el ciclo de vida mediante el método run() que orquesta autenticación, creación de contexto, registro de conexión, loop de mensajes y desregistro. Los métodos abstractos create_context, register_connection y handle_message deben ser implementados por subclases.

JWTWebSocketEndpoint hereda de la base y añade revalidación periódica de JWT cada cinco minutos para conexiones de larga duración. WaiterEndpoint extiende JWTWebSocketEndpoint con el comando especial refresh_sectors para actualizar asignaciones de sector. KitchenEndpoint recibe eventos de rounds y tickets. AdminEndpoint tiene acceso completo a todos los eventos de branch. DinerEndpoint usa TableToken en lugar de JWT para autenticación.

Los mixins disponibles proporcionan comportamientos composables. MessageValidationMixin valida tamaño de mensaje y rate limit. OriginValidationMixin valida el header Origin de la conexión. JWTRevalidationMixin implementa revalidación cada cinco minutos. HeartbeatMixin registra heartbeats para detección de conexiones stale. ConnectionLifecycleMixin proporciona logging estructurado del ciclo de vida de conexión.

---

## Sistema de Eventos

El sistema define eventos tipados para cada flujo de negocio. El ciclo de vida de rondas progresa desde PENDING cuando el diner crea la orden hacia admin y waiters, a CONFIRMED cuando el waiter verifica hacia admin para que pueda enviar a cocina, a SUBMITTED cuando admin envía a cocina hacia admin y kitchen, a IN_KITCHEN cuando cocina comienza hacia todos incluyendo diners, a READY cuando cocina termina hacia todos, y finalmente SERVED cuando se entrega hacia todos. Los eventos CANCELED y ROUND_ITEM_DELETED manejan cancelaciones y eliminación de items respectivamente.

Los eventos de carrito compartido incluyen CART_ITEM_ADDED cuando un diner agrega producto, CART_ITEM_UPDATED cuando cambia cantidad o notas, CART_ITEM_REMOVED cuando elimina item, CART_CLEARED cuando se envía la ronda, y CART_SYNC para reconexión con estado completo.

Los eventos de llamadas de servicio comprenden SERVICE_CALL_CREATED cuando el diner llama, SERVICE_CALL_ACKED cuando el waiter reconoce, y SERVICE_CALL_CLOSED cuando se atiende y cierra.

Los eventos de facturación incluyen CHECK_REQUESTED cuando el diner pide cuenta, CHECK_PAID cuando se completa el pago, PAYMENT_APPROVED cuando Mercado Pago aprueba, PAYMENT_REJECTED cuando rechaza, y PAYMENT_FAILED cuando hay error.

Los eventos de mesas son TABLE_SESSION_STARTED cuando se escanea QR, TABLE_CLEARED cuando se cierra sesión, y TABLE_STATUS_CHANGED para cambios de estado. Los eventos de cocina incluyen TICKET_IN_PROGRESS, TICKET_READY y TICKET_DELIVERED. Los eventos administrativos ENTITY_CREATED, ENTITY_UPDATED, ENTITY_DELETED y CASCADE_DELETE notifican operaciones CRUD a administradores.

El EventRouter determina destinatarios basándose en tipo de evento, branch_id, sector_id y session_id. Los eventos con sector_id se filtran para enviar solo a meseros asignados a ese sector. Los roles ADMIN y MANAGER siempre reciben todos los eventos de su branch.

---

## Resiliencia del WebSocket Gateway

CircuitBreaker implementa el patrón homónimo con tres estados para proteger contra fallos de Redis. En estado CLOSED el circuito opera normalmente. Después de cinco fallos consecutivos, transiciona a OPEN donde todas las llamadas fallan inmediatamente por treinta segundos. Luego pasa a HALF_OPEN donde permite hasta tres requests de prueba antes de decidir si cerrar completamente o reabrir.

El sistema de retry con jitter decorrelacionado previene thundering herd en reconexiones masivas. En lugar de exponential backoff puro que sincroniza retries, usa jitter decorrelacionado donde el delay es aleatorio entre el delay previo y el mínimo entre el delay máximo y tres veces el delay previo. Esto distribuye los reintentos en el tiempo evitando picos de carga.

StreamConsumer implementa Redis Streams para eventos críticos que requieren entrega garantizada. Consumer groups permiten que múltiples instancias del gateway compartan carga. PEL (Pending Entries List) recovery reclama mensajes pendientes después de treinta segundos de idle. Dead letter queue retiene mensajes irrecuperables después de tres intentos, almacenándolos en un stream dedicado con metadata del mensaje original, stream de origen, payload, conteo de reintentos, timestamp de fallo y nombre del consumidor.

---

## Scripts Lua para Operaciones Atómicas

El WebSocket Gateway utiliza Lua scripts ejecutados en Redis para garantizar atomicidad en operaciones críticas como rate limiting. El script de rate limiting recibe la clave de rate limit, máximo de mensajes permitidos, tamaño de ventana en segundos y timestamp actual, retornando si está permitido, conteo actual y TTL restante.

La implementación en Lua primero obtiene el conteo actual, verifica si excede el límite retornando cero si lo hace, incrementa el contador si está permitido, establece el TTL atómicamente si es el primer incremento de la ventana, y retorna uno con el nuevo conteo y TTL.

Las ventajas sobre implementación en Python son significativas. No hay race conditions entre GET e INCR ya que todo ocurre atómicamente en Redis. Solo se requiere un round-trip a Redis en lugar de múltiples. El TTL se establece atómicamente con el primer incremento. El script SHA se cachea para ejecución eficiente con EVALSHA en llamadas subsecuentes.

---

## Modelo de Datos

El sistema define cincuenta y cuatro modelos SQLAlchemy organizados en veinte archivos por dominio coherente. El archivo base.py contiene Base y AuditMixin. El archivo tenant.py define Tenant y Branch. El archivo user.py contiene User y UserBranchRole. El archivo catalog.py define Category, Subcategory, Product y BranchProduct. El archivo allergen.py contiene Allergen, ProductAllergen y AllergenCrossReaction. El archivo ingredient.py define IngredientGroup, Ingredient, SubIngredient y ProductIngredient. El archivo product_profile.py contiene doce modelos de perfiles dietéticos, cocción, sabor y relaciones M:N.

El archivo sector.py define BranchSector y WaiterSectorAssignment. El archivo table.py contiene Table y TableSession. El archivo cart.py define CartItem para el carrito compartido. El archivo customer.py contiene Customer y Diner. El archivo order.py define Round y RoundItem. El archivo kitchen.py contiene KitchenTicket, KitchenTicketItem y ServiceCall. El archivo billing.py define Check usando la tabla app_check para evitar conflicto con palabra reservada SQL, junto con Payment, Charge y Allocation. El archivo knowledge.py contiene KnowledgeDocument y ChatLog para RAG. El archivo promotion.py define Promotion, PromotionBranch y PromotionItem. El archivo exclusion.py contiene BranchCategoryExclusion y BranchSubcategoryExclusion. El archivo recipe.py define Recipe y RecipeAllergen. El archivo audit.py contiene AuditLog. El archivo outbox.py define OutboxEvent para entrega garantizada de eventos.

---

## Jerarquía de Entidades

La jerarquía de entidades refleja la estructura organizativa de un restaurante multi-sucursal. El Tenant representa el restaurante como entidad raíz. Cada Tenant tiene múltiples Branch que a su vez contienen Category con Subcategory y Product. Los productos tienen BranchProduct para precios por sucursal, ProductAllergen para alérgenos con tipo de presencia y nivel de riesgo, ProductIngredient para ingredientes, y relaciones M:N para métodos de cocción, sabores y texturas.

Cada Branch contiene BranchSector que agrupa Table. Las mesas tienen TableSession como sesión activa que contiene CartItem para el carrito compartido y Diner para comensales identificados por device_id. Cada Diner tiene CartItem propios y Round con confirmed_by_user_id para trackear verificación. Los Round contienen RoundItem que a su vez generan KitchenTicketItem.

Los sectores tienen WaiterSectorAssignment para asignaciones diarias de meseros. Las sesiones generan Check que contienen Charge, Payment y Allocation siguiendo el patrón FIFO. Las branches tienen KitchenTicket, ServiceCall y OutboxEvent para eventos pendientes.

Los User se relacionan M:N con Branch mediante UserBranchRole que define roles ADMIN, MANAGER, KITCHEN o WAITER. El Tenant también tiene catálogos scoped como CookingMethod, FlavorProfile, TextureProfile y CuisineType, además de la jerarquía IngredientGroup, Ingredient y SubIngredient.

---

## AuditMixin Universal

Todos los modelos heredan de AuditMixin, proporcionando trazabilidad completa de todas las operaciones. El mixin incluye is_active como flag de soft delete con índice para filtrado eficiente, deleted_at como timestamp de eliminación, y deleted_by_id junto con deleted_by_email para identificar quién eliminó.

Los timestamps created_at y updated_at se establecen automáticamente en inserción y actualización respectivamente. La trazabilidad de usuario se completa con created_by_id y created_by_email para el creador, y updated_by_id junto con updated_by_email para el último modificador.

Este diseño permite soft delete universal donde ningún dato se elimina físicamente, auditoría completa de quién y cuándo realizó cada operación, y restauración de entidades eliminadas con cascade a sus dependientes.

---

## Relaciones y Constraints

El sistema de productos y precios por sucursal utiliza Product como maestro global mientras BranchProduct contiene el precio específico por sucursal en centavos donde doce mil quinientos cincuenta representa ciento veinticinco dólares con cincuenta centavos, junto con disponibilidad.

El sistema de alérgenos con reacciones cruzadas usa ProductAllergen para registrar presencia con tres niveles CONTAINS, MAY_CONTAIN y TRACE, junto con riesgo HIGH, MEDIUM o LOW. AllergenCrossReaction implementa una relación auto-referencial M:N para modelar reacciones cruzadas entre alérgenos.

El flujo de órdenes sigue la cadena TableSession hacia Diner hacia Round hacia RoundItem hacia KitchenTicketItem, representando el flujo completo desde que un comensal se sienta hasta que su orden llega a cocina. Round ahora incluye confirmed_by_user_id para trackear qué mesero verificó el pedido.

Los constraints de integridad implementan UniqueConstraint en Category por branch_id y name, Subcategory por category_id y name, todos los catálogos tenant-scoped, y Round por table_session_id e idempotency_key. Los CheckConstraints validan que precios sean no negativos y que cantidades sean positivas.

---

## Patrón Zustand Crítico para React 19

Todos los frontends implementan un patrón estricto de Zustand para evitar loops infinitos de re-renderizado causados por la detección de cambios más agresiva de React diecinueve. El destructuring directo del store causa loops infinitos porque cada llamada retorna un nuevo objeto. El patrón correcto usa selectores individuales para cada valor o acción necesaria.

Es crítico utilizar referencias estables para arrays fallback, declarando una constante vacía del tipo correcto fuera del selector y usándola en lugar de crear un array vacío inline. Para selectores filtrados, se implementa memoización con cache simple que compara si el source cambió antes de recalcular el filtro.

Para selectores que reciben parámetros dinámicos como filtrado por ID, se usa un cache Map que almacena resultados por cada valor de parámetro. El hook useShallow de Zustand se usa para objetos pero no para arrays, permitiendo extraer múltiples propiedades sin causar re-renders innecesarios.

Los beneficios medidos incluyen reducción de más del noventa por ciento en re-renders de componentes con listas filtradas, eliminación de loops infinitos en React diecinueve strict mode, y estabilidad de referencias para useMemo y useCallback dependientes.

---

## Sistema de Seguridad

El sistema implementa autenticación dual para diferentes contextos. JWT se usa para staff en Dashboard y pwaWaiter con access token de quince minutos de vida, refresh token de siete días almacenado en HttpOnly cookie siguiendo SEC-09, y claims que incluyen sub como user_id, tenant_id, branch_ids, roles y email. Table Token se usa para diners en pwaMenu, firmado con HMAC-SHA256, con tres horas de vida reducido de ocho horas en CRIT-04, y claims que incluyen table_id, branch_id y session_id.

La revalidación de tokens en conexiones WebSocket verifica JWT cada cinco minutos contra la blacklist de Redis mediante CRIT-WS-01. Si el token fue revocado, la conexión se cierra con código cuatro mil uno. Los table tokens se revalidan cada treinta minutos en conexiones de diners mediante SEC-HIGH-01.

La revocación de tokens se implementa mediante Redis con TTL igual al tiempo restante del token. El patrón fail-closed trata errores de Redis como token blacklisted, garantizando que fallos de infraestructura no resulten en acceso no autorizado.

El rate limiting protege endpoints REST con cinco intentos por sesenta segundos para login implementado mediante script Lua atómico, y diez a veinte por minuto para endpoints de billing. WebSocket tiene límite de veinte mensajes por segundo por conexión y diez broadcasts globales por segundo, cerrando conexiones con código cuatro mil veintinueve cuando se excede.

La validación de entrada previene SSRF en URLs de imagen permitiendo solo esquemas HTTP y HTTPS, bloqueando hosts localhost, rangos IP privados y endpoints de metadata cloud. Previene SQL injection usando siempre bindings de SQLAlchemy y escapando caracteres especiales en patrones LIKE. Previene XSS mediante sanitización de HTML en inputs y headers CSP en producción.

El middleware de security headers añade X-Content-Type-Options nosniff, X-Frame-Options DENY, Content-Security-Policy restrictivo, y Strict-Transport-Security en producción.

---

## Aislamiento Multi-Tenant

Cada restaurante constituye un tenant con aislamiento completo de datos. El tenant_id se propaga a través de todas las capas. En JWT claims el token contiene tenant_id del usuario. En repositorios TenantRepository auto-filtra por tenant_id en todas las queries. En el WebSocket Index las conexiones se indexan por tenant_id. En broadcast TenantFilter valida tenant antes de enviar cualquier evento.

El WebSocket Gateway implementa validación de tenant_id en múltiples puntos. El contexto puede tener tenant_id como None, distinto de cero que es ambiguo. Las conexiones sin tenant_id válido se registran con warning y no reciben eventos de sectores específicos.

La prevención de data leakage garantiza que eventos nunca se envíen a conexiones de otros tenants, queries siempre incluyan filtro por tenant_id, y logs saniticen PII antes de escritura.

---

## Optimizaciones de Rendimiento

La configuración para cuatrocientos a seiscientos usuarios incluye ws_max_connections_per_user en tres para limitar conexiones duplicadas, ws_max_total_connections en mil como límite global, ws_message_rate_limit de veinte por segundo por conexión, ws_broadcast_batch_size de cincuenta para broadcast paralelo, redis_pool_max_connections de cincuenta para el pool async, redis_sync_pool_max_connections de veinte para rate limit y blacklist, y redis_event_queue_size de quinientos como buffer de backpressure.

El broadcast paralelo con worker pool logra aproximadamente ciento sesenta milisegundos para broadcast a cuatrocientos usuarios versus cuatro mil milisegundos con envío secuencial. Los sharded locks reducen contención en noventa por ciento mediante dicts de locks por branch_id y user_id, con locks globales solo para operaciones específicas.

El sector cache con TTL de sesenta segundos almacena asignaciones de sectores por user_id con límite de mil entradas, reduciendo queries de asignación en aproximadamente ochenta por ciento. El eager loading preconfigurado en repositorios usa selectinload y joinedload para prevenir queries N+1 en cadenas de relaciones.

---

## Flujo de Orden Completo

El flujo comienza cuando el diner añade ítems al carrito en pwaMenu. La confirmación grupal requiere que todos los diners aprueben. El POST a la API crea Round con status PENDING. El REST API publica ROUND_PENDING a Redis. El WS Gateway broadcast a admin y waiters del branch. El waiter verifica en mesa y confirma, transicionando a ROUND_CONFIRMED. El admin envía a cocina, transicionando a ROUND_SUBMITTED. Kitchen comienza y transiciona a ROUND_IN_KITCHEN, broadcast que ahora incluye diners. Kitchen termina y transiciona a ROUND_READY. Staff entrega y transiciona a ROUND_SERVED.

---

## Flujo de Pago con Mercado Pago

El diner inicia pago en pwaMenu. El REST API crea preferencia en Mercado Pago y obtiene URL de checkout. El usuario es redirigido al checkout de MP donde procesa el pago. MP envía webhook al REST API que valida firma y actualiza Check. Se publica PAYMENT_APPROVED o PAYMENT_REJECTED. El WS Gateway notifica a diners de la sesión el resultado.

---

## Flujo de Carrito Compartido

El sistema implementa sincronización en tiempo real del carrito entre múltiples dispositivos de comensales en la misma mesa. Cuando un diner en Chrome agrega Coca-Cola, el diner en Firefox lo ve instantáneamente.

El frontend ejecuta POST a la API de carrito con el item. El REST API valida producto y diner, ejecuta UPSERT en CartItem, incrementa cart_version en la sesión, y usa BackgroundTask para publicar a Redis. El evento CART_ITEM_ADDED se publica al canal de la sesión. El WS Gateway rutea a diners de esa sesión mediante EventRouter. En cada frontend, el hook useCartSync recibe el evento, compara diner_id con el diner actual, y actualiza estado local si es de otro comensal, ignorando eventos propios ya actualizados optimistamente.

El modelo CartItem incluye tenant_id, branch_id, session_id como FK a TableSession, diner_id como FK a Diner identificando quién agregó, product_id como FK a Product, quantity validado entre uno y noventa y nueve, y notes opcional. El UniqueConstraint en session_id, diner_id y product_id permite UPSERT limpio.

Los eventos de carrito incluyen CART_ITEM_ADDED con payload completo de item_id, product_id, product_name, price_cents, quantity, diner_id, diner_name y diner_color. CART_ITEM_UPDATED tiene el mismo payload. CART_ITEM_REMOVED incluye item_id, product_id y diner_id. CART_CLEARED indica que la ronda fue enviada. CART_SYNC proporciona estado completo para reconexión.

---

## Outbox Pattern para Entrega Garantizada

El sistema implementa el patrón Transactional Outbox para eventos críticos que no pueden perderse incluyendo billing, rounds y service calls. Los eventos se escriben atómicamente con los datos de negocio en la misma transacción de base de datos.

El endpoint ejecuta lógica de negocio como crear Round o Payment, llama a write_outbox_event con los parámetros del evento, y ejecuta db.commit() que guarda atómicamente los datos de negocio junto con el OutboxEvent en estado PENDING.

El Outbox Processor corre como loop que hace poll cada segundo. Selecciona eventos WHERE status = PENDING ORDER BY created_at. Actualiza status a PROCESSING usando FOR UPDATE SKIP LOCKED para evitar procesamiento duplicado. Publica a Redis. Actualiza status a PUBLISHED con processed_at. Si falla, incrementa retry_count hasta MAX_RETRIES de cinco, luego marca como FAILED.

El modelo OutboxEvent incluye tenant_id, event_type como ROUND_SUBMITTED o CHECK_PAID, aggregate_type como round o check o service_call, aggregate_id, payload como JSON serializado, status que puede ser PENDING, PROCESSING, PUBLISHED o FAILED, retry_count, last_error opcional, created_at y processed_at opcional.

Los eventos que usan Outbox por ser críticos incluyen ROUND_SUBMITTED y ROUND_READY para rounds, CHECK_REQUESTED, PAYMENT_APPROVED, PAYMENT_REJECTED y CHECK_PAID para checks, y SERVICE_CALL_CREATED para service calls. Los eventos no críticos como CART_*, TABLE_* y ENTITY_* usan publicación directa con BackgroundTasks.

---

## Infraestructura Docker

El archivo docker-compose.yml orquesta cinco servicios. El servicio db usa la imagen pgvector/pgvector:pg16 en el puerto cinco mil cuatrocientos treinta y dos con volumen persistente pgdata y healthcheck mediante pg_isready.

El servicio redis usa la imagen redis:7-alpine en el puerto seis mil trescientos ochenta mapeado desde seis mil trescientos setenta y nueve para evitar conflictos, ejecutando redis-server con appendonly yes, maxmemory de doscientos cincuenta y seis megabytes y política allkeys-lru, con healthcheck mediante redis-cli ping.

El servicio backend construye desde el directorio padre, expone el puerto ocho mil, depende de db y redis, monta el directorio backend como volumen de solo lectura para hot reload, y ejecuta uvicorn con reload habilitado.

El servicio ws_gateway similar al backend expone el puerto ocho mil uno, depende de db, redis y backend, y monta tanto backend como ws_gateway como volúmenes de solo lectura.

El servicio pgadmin usa la imagen dpage/pgadmin4 en el puerto cinco mil cincuenta para administración web de la base de datos.

---

## Health Checks y Métricas

El REST API expone health en modo sync y health/detailed en modo async con estado de Redis. El WS Gateway expone ws/health en modo sync y ws/health/detailed en modo async. Los health checks detallados incluyen estado de pool Redis async, estado de pool Redis sync, conexiones activas y métricas del subscriber.

El endpoint de métricas Prometheus en ws/metrics expone wsgateway_connections_total para conexiones activas, wsgateway_connections_rejected_total con etiqueta reason para auth o rate_limit, wsgateway_broadcasts_total y wsgateway_broadcasts_failed_total para estadísticas de broadcast, y wsgateway_redis_reconnects_total junto con wsgateway_event_drops_total para monitoreo de Redis.

El sistema usa logging estructurado con formato JSON en producción y coloreado en desarrollo. PII se sanitiza antes de logging con emails parcialmente ocultos, JTI truncados y user_ids hasheados.

EventDropRateTracker monitorea tasas de descarte con ventana de sesenta segundos, umbral de alerta del cinco por ciento y cooldown de alerta de cinco minutos para evitar spam de logs.

---

## Decisiones Arquitectónicas

La adopción de Clean Architecture con servicios de dominio separados añade complejidad inicial pero ha demostrado valor en testing unitario de lógica de negocio sin dependencias de infraestructura, evolución independiente de capas, y onboarding más rápido de nuevos desarrolladores. El trade-off es aceptado dado el tamaño y complejidad del sistema.

El sistema usa híbrido de Redis Streams y Pub/Sub. Pub/Sub maneja eventos de tiempo real que pueden perderse sin consecuencias graves como TABLE_STATUS_CHANGED. Streams manejan eventos críticos que requieren entrega garantizada como ROUND_* y PAYMENT_*. Streams permiten rewind si el gateway reinicia, previniendo pérdida de órdenes.

Para broadcasts grandes el worker pool ofrece backpressure mediante queue con límite, métricas granulares de latencia, y graceful shutdown con drain timeout. asyncio.gather se mantiene para broadcasts pequeños por simplicidad.

La adopción de React diecinueve con Compiler en Dashboard elimina la mayoría de React.memo manuales. Sin embargo se mantienen en componentes críticos para compatibilidad si el compilador se desactiva y explicitación de intención de optimización.

La persistencia en localStorage permite funcionamiento offline, sesiones que sobreviven refrescos de página, y menor carga al servidor. El trade-off es sincronización más compleja entre tabs, resuelto con BroadcastChannel.

---

## Estadísticas del Código

El componente Backend rest_api comprende ochenta y un archivos con aproximadamente quince mil líneas. El componente Backend shared tiene treinta archivos con aproximadamente cuatro mil quinientas líneas. El WebSocket Gateway tiene cincuenta y un archivos con doce mil seiscientas cinco líneas. El Dashboard tiene más de ochenta y cinco archivos con aproximadamente doce mil líneas. El componente pwaMenu tiene más de setenta archivos con aproximadamente diez mil líneas. El componente pwaWaiter tiene más de cuarenta archivos con aproximadamente seis mil líneas. El total supera trescientos sesenta archivos con aproximadamente sesenta mil líneas de código.

---

*Documento generado: Febrero 2026*
*Versión: 3.0 - Reescrito en prosa narrativa*
