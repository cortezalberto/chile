# REST API: Arquitectura y Funcionamiento

Version 3.0 - Febrero 2026

## Introducción

La REST API constituye el núcleo transaccional del ecosistema Integrador, implementando toda la lógica de negocio que sustenta las operaciones de un restaurante moderno. Este servicio, ejecutándose en el puerto 8000, actúa como guardián de los datos y orquestador de las reglas de negocio que gobiernan desde la gestión de catálogos de productos hasta el procesamiento de pagos y la coordinación de pedidos en tiempo real.

La arquitectura de la API fue diseñada siguiendo los principios de Clean Architecture, estableciendo una separación rigurosa entre las distintas capas de responsabilidad. Los routers HTTP actúan como controladores delgados que únicamente manejan preocupaciones de transporte, delegando inmediatamente a servicios de dominio que encapsulan toda la lógica de negocio. Estos servicios, a su vez, utilizan repositorios especializados para el acceso a datos, manteniendo una independencia total respecto a los detalles de persistencia.

El sistema implementa multi-tenancy completo, donde cada restaurante opera en aislamiento total de los demás, compartiendo la misma infraestructura pero con datos completamente segregados. Este aislamiento se garantiza automáticamente a través de repositorios que filtran todas las consultas por tenant_id, eliminando la posibilidad de fugas de información entre organizaciones.

La seguridad permea cada capa de la arquitectura. Desde middlewares que validan orígenes y tipos de contenido, pasando por autenticación JWT con tokens de corta duración, hasta un sistema de control de acceso basado en roles que implementa el patrón Strategy para proporcionar permisos granulares según el rol del usuario. Cada operación se audita completamente, preservando un rastro detallado de quién hizo qué y cuándo.

---

## Capítulo 1: La Estructura Modular del Proyecto

La carpeta rest_api reside dentro del directorio backend y organiza su código en subdirectorios claramente diferenciados por responsabilidad. Esta organización refleja los principios de separación de preocupaciones y facilita tanto la navegación del código como su evolución independiente.

El archivo main.py constituye el punto de entrada de la aplicación FastAPI. En este archivo se configura la secuencia de middlewares de seguridad, donde el orden es crítico ya que CORS debe registrarse último para funcionar correctamente. Se registran dieciocho routers que cubren todas las áreas funcionales del sistema. Se integra OpenTelemetry para observabilidad distribuida y se configura el rate limiting mediante slowapi. El archivo permanece deliberadamente simple, delegando la lógica compleja a módulos especializados.

El directorio core contiene la configuración fundamental de la aplicación. El archivo lifespan.py gestiona el ciclo de vida completo del servicio, orquestando la inicialización de la base de datos, la activación de la extensión pgvector para embeddings vectoriales, la ejecución de seeds iniciales, el arranque de procesadores en background como el procesador Outbox y el reintentador de webhooks, y el cierre ordenado de conexiones durante el shutdown. El archivo middlewares.py implementa los middlewares de seguridad que añaden headers protectores a todas las respuestas y validan los tipos de contenido de las peticiones entrantes, incluyendo Content-Security-Policy, Strict-Transport-Security para producción, y Permissions-Policy para deshabilitar APIs del navegador no utilizadas. El archivo cors.py centraliza la configuración de orígenes permitidos para peticiones cross-origin, distinguiendo entre desarrollo donde se permiten localhost en diversos puertos y producción donde los orígenes provienen de variables de entorno.

El directorio models organiza los modelos de SQLAlchemy en más de veinte archivos modulares, cada uno agrupando entidades relacionadas por dominio. Esta modularización permite que el modelo de datos crezca sin que ningún archivo individual se vuelva inmanejable. El archivo base.py define la clase Base de SQLAlchemy y el AuditMixin que proporciona soft delete y campos de auditoría a todas las entidades. El archivo tenant.py define Tenant representando un restaurante completo y Branch representando una sucursal física. El archivo user.py implementa User y UserBranchRole para la relación muchos a muchos entre usuarios y sucursales con roles específicos. El archivo catalog.py contiene Category, Subcategory, Product y BranchProduct para precios específicos por sucursal. El archivo allergen.py gestiona Allergen, ProductAllergen con tipos de presencia y niveles de riesgo, y AllergenCrossReaction para reacciones cruzadas entre alérgenos. El archivo ingredient.py estructura IngredientGroup, Ingredient, SubIngredient y ProductIngredient en una jerarquía de tres niveles. El archivo product_profile.py implementa doce tablas de relación para perfiles dietéticos, métodos de cocción, sabores y texturas. El archivo sector.py define BranchSector y WaiterSectorAssignment para asignaciones diarias de mozos. El archivo table.py representa Table y TableSession para el ciclo de vida de una mesa. El archivo customer.py implementa Customer con consentimiento GDPR y Diner para comensales individuales con tracking de dispositivo. El archivo cart.py define CartItem para el carrito compartido en tiempo real. El archivo order.py contiene Round y RoundItem para el ciclo de vida de pedidos. El archivo kitchen.py gestiona KitchenTicket, KitchenTicketItem y ServiceCall. El archivo billing.py implementa Check usando el nombre de tabla app_check para evitar conflictos con palabras reservadas de SQL, junto con Payment, Charge y Allocation para el modelo FIFO de pagos. El archivo promotion.py define Promotion, PromotionBranch y PromotionItem. El archivo recipe.py almacena Recipe y RecipeAllergen para fichas técnicas de cocina. El archivo knowledge.py soporta KnowledgeDocument con embeddings vectoriales y ChatLog para el sistema RAG de chatbot. El archivo audit.py proporciona AuditLog para logging estructurado de operaciones. El archivo outbox.py implementa OutboxEvent para el patrón de eventos transaccionales garantizados.

El directorio services representa el corazón de la lógica de negocio, organizado en subdirectorios especializados. El subdirectorio domain contiene los servicios de dominio principales que implementan las operaciones de negocio para cada entidad, siendo la ubicación preferida para nueva lógica de negocio bajo los principios de Clean Architecture. El subdirectorio crud proporciona utilidades para operaciones de datos como soft delete, auditoría, repositorios tipados y el CRUDFactory que está deprecado en favor de servicios de dominio. El subdirectorio permissions implementa el sistema de control de acceso basado en roles mediante el patrón Strategy. El subdirectorio events gestiona la publicación de eventos de dominio incluyendo el patrón Outbox para eventos críticos. El subdirectorio payments maneja el procesamiento de pagos con patrones de resiliencia como circuit breaker y retry con backoff exponencial.

El directorio routers organiza los endpoints HTTP en grupos funcionales. El subdirectorio auth maneja autenticación sin requerir token previo. El subdirectorio public expone endpoints accesibles sin autenticación. El subdirectorio admin contiene quince routers especializados para operaciones CRUD del dashboard de administración. El subdirectorio diner implementa operaciones para comensales autenticados mediante tokens de mesa. El subdirectorio kitchen proporciona endpoints para personal de cocina. El subdirectorio waiter implementa operaciones para mozos. El subdirectorio billing maneja pagos y facturación. El subdirectorio content gestiona contenido administrable como recetas, ingredientes, promociones y el chatbot RAG. El subdirectorio tables gestiona sesiones de mesa.

---

## Capítulo 2: El Flujo de Datos en Clean Architecture

La arquitectura sigue un flujo unidireccional donde cada capa solo conoce y depende de la capa inmediatamente inferior. Los routers HTTP reciben las peticiones y las transforman en llamadas a servicios de dominio. Los servicios de dominio orquestan la lógica de negocio y utilizan repositorios para acceder a los datos. Los repositorios encapsulan las consultas SQL y retornan entidades del modelo. Las entidades del modelo representan el estado persistido en la base de datos.

Este diseño proporciona múltiples beneficios tangibles. La testabilidad mejora dramáticamente ya que cada capa puede probarse en aislamiento mediante mocks de las capas inferiores. La mantenibilidad se incrementa porque los cambios en una capa no propagan efectos inesperados a las demás. La evolución del sistema se facilita ya que nuevas funcionalidades se añaden en la capa apropiada sin modificar las existentes.

Los routers permanecen deliberadamente delgados, conteniendo únicamente lógica de transformación HTTP. No realizan validaciones de negocio, no acceden directamente a la base de datos, y no contienen condicionales complejos. Su única responsabilidad es recibir una petición, extraer los parámetros relevantes mediante dependencias de FastAPI, invocar al servicio apropiado pasando el contexto de permisos, y formatear la respuesta.

Los servicios de dominio concentran toda la inteligencia del negocio. Validan reglas de negocio complejas como restricciones de unicidad personalizadas. Orquestan operaciones que involucran múltiples entidades manteniendo consistencia transaccional. Publican eventos para notificar cambios a otros sistemas mediante Redis o el patrón Outbox. Manejan los efectos secundarios de las operaciones como actualizar caches o sincronizar datos derivados. Cada servicio se especializa en un dominio específico como productos, categorías, pedidos o facturación.

Los repositorios abstraen completamente los detalles de persistencia. Encapsulan las consultas SQLAlchemy proporcionando métodos semánticos como find_by_branch o find_all_active. Configuran el eager loading de relaciones para prevenir problemas de N+1 queries que degradarían el rendimiento. Aplican filtros de tenant y branch automáticamente garantizando aislamiento multi-tenant. Manejan la paginación mediante offset y limit a nivel de base de datos. El código de los servicios nunca escribe sentencias SQL ni manipula sesiones de base de datos directamente.

---

## Capítulo 3: El Ciclo de Vida de la Aplicación

El archivo lifespan.py implementa el patrón de gestión de ciclo de vida que FastAPI proporciona mediante context managers asíncronos. Esta función se ejecuta una vez al inicio del servidor y otra al cierre, permitiendo inicialización y limpieza coordinadas de recursos.

Durante la fase de startup, el sistema ejecuta una secuencia cuidadosamente ordenada de inicializaciones. Primero valida que los secretos de producción estén correctamente configurados, rechazando arrancar si se detectan valores por defecto inseguros para JWT_SECRET o TABLE_TOKEN_SECRET en entorno de producción. Luego configura el logging estructurado para facilitar el diagnóstico en producción. A continuación habilita la extensión pgvector en PostgreSQL para soportar embeddings de inteligencia artificial necesarios para el sistema RAG. Después invoca Base.metadata.create_all para crear todas las tablas del modelo si no existen. Posteriormente ejecuta los seeds de datos iniciales para poblar configuraciones básicas como roles, categorías predeterminadas y datos de demostración. Luego registra los handlers de webhooks para procesamiento de pagos de Mercado Pago. Arranca los procesadores en background que incluyen el procesador Outbox para publicar eventos garantizados, el reintentador de webhooks fallidos, y el scheduler de refresh-ahead para renovación proactiva de tokens. Finalmente inicializa las métricas Prometheus y opcionalmente precalienta caches de Redis.

Durante la fase de shutdown, el sistema detiene ordenadamente todos los componentes activos. Cancela el scheduler de refresh-ahead esperando que finalice graciosamente. Detiene el procesador Outbox permitiendo que complete los eventos en progreso. Cierra el cliente HTTP de Ollama si estaba activo para el chatbot RAG. Libera el executor del rate limiter. Cierra el pool de conexiones Redis tanto asíncrono como síncrono. Esta secuencia ordenada previene pérdida de datos y garantiza que las operaciones en progreso completen antes del cierre.

---

## Capítulo 4: La Base Auditable de Modelos

Todos los modelos de la API heredan de una clase base AuditMixin que proporciona capacidades uniformes de auditoría y soft delete. Esta herencia garantiza que cada entidad en el sistema mantenga un rastro completo de su historia, cumpliendo con requisitos de trazabilidad y recuperación de datos.

El mixin proporciona un campo booleano is_active que implementa el patrón de soft delete. En lugar de eliminar registros físicamente de la base de datos, las operaciones de eliminación simplemente marcan este campo como falso. Todas las consultas normales filtran automáticamente por is_active verdadero mediante los repositorios, haciendo invisibles los registros eliminados sin perderlos permanentemente. Este campo está indexado para mantener el rendimiento de las consultas filtradas.

Los campos de timestamp registran el momento exacto de cada operación. El campo created_at almacena el instante de creación con zona horaria UTC, usando datetime.now con timezone.utc para evitar el problema de naive datetimes que fue corregido en el fix CRIT-01. El campo updated_at se actualiza automáticamente en cada modificación mediante onupdate de SQLAlchemy. El campo deleted_at registra el momento del soft delete, permitiendo análisis forense de cuándo se eliminaron registros.

Los campos de tracking de usuario denormalizan tanto el identificador como el email del usuario que realizó cada operación. Esta denormalización deliberada permite mostrar información de auditoría sin necesidad de joins adicionales, sacrificando normalización por rendimiento en consultas de auditoría frecuentes. Los campos incluyen created_by_id y created_by_email para creación, updated_by_id y updated_by_email para modificaciones, y deleted_by_id y deleted_by_email para eliminaciones.

El mixin también proporciona métodos de instancia para realizar las operaciones de forma consistente. El método soft_delete recibe el usuario que realiza la operación y actualiza tanto is_active como los campos de auditoría de eliminación. El método restore revierte un soft delete, reactivando la entidad. Los métodos set_created_by y set_updated_by establecen los campos de auditoría correspondientes en creación y actualización.

---

## Capítulo 5: El Sistema de Repositorios

El sistema de repositorios implementa tres niveles de abstracción que proporcionan aislamiento progresivo según las necesidades de cada entidad. Esta jerarquía permite que el código de servicios trabaje con interfaces consistentes mientras el repositorio maneja automáticamente el filtrado apropiado.

El BaseRepository proporciona operaciones fundamentales sin ningún filtrado automático. Este nivel se utiliza para entidades que no requieren aislamiento, como configuraciones globales del sistema. Ofrece métodos para buscar por identificador, listar todos los registros con paginación, contar registros, y verificar existencia. Todos los métodos aceptan opciones de eager loading para prevenir N+1.

El TenantRepository extiende el base añadiendo filtrado automático por tenant_id. Todas las operaciones heredadas ahora requieren un parámetro de tenant y lo aplican automáticamente a las consultas mediante cláusulas where inyectadas. Este nivel se utiliza para entidades que pertenecen a un tenant específico pero no están asociadas a una sucursal particular, como los ingredientes globales del restaurante o los alérgenos definidos a nivel de tenant.

El BranchRepository añade una capa adicional de filtrado por branch_id sobre el filtrado de tenant. Las operaciones a este nivel requieren tanto tenant como branch, aplicando ambos filtros a todas las consultas. Este nivel se utiliza para entidades como categorías, mesas o sectores que pertenecen a una sucursal específica. El método find_by_branch localiza entidades de una sucursal específica. El método find_by_branches acepta una lista de identificadores de sucursales para filtrar por múltiples ubicaciones, útil para managers que tienen acceso a varias sucursales.

Los repositorios encapsulan toda la lógica de consultas SQLAlchemy, manteniendo el código de servicios limpio de detalles de persistencia. Un servicio simplemente invoca métodos del repositorio con parámetros de negocio, sin construir queries ni manejar sesiones. El método find_by_id localiza una entidad por su identificador primario, retornando None si no existe o no pertenece al tenant especificado. El método find_all lista entidades aplicando filtros opcionales, ordenamiento, y paginación eficiente a nivel de base de datos. El método find_by_ids recupera múltiples entidades por una lista de identificadores en una sola consulta, evitando el antipatrón de N consultas para N identificadores. El método count retorna el número de registros que cumplen los criterios especificados. El método exists verifica eficientemente si existe al menos un registro que cumpla los criterios.

Los repositorios configuran estrategias de eager loading para prevenir el problema de N+1 queries. La estrategia selectinload ejecuta una segunda consulta para cargar las relaciones, resultando en exactamente dos queries independientemente del número de registros, siendo óptima para relaciones uno a muchos. La estrategia joinedload utiliza un JOIN SQL para cargar las relaciones en una sola consulta, siendo óptima para relaciones uno a uno o muchos a uno. La combinación de ambas estrategias permite cargar grafos complejos de entidades eficientemente, como productos con sus precios por sucursal mediante selectinload y su receta asociada mediante joinedload.

Un detalle técnico importante es el uso correcto de comparaciones booleanas en SQLAlchemy. El fix HIGH-DEEP-04 establece que se debe usar is_(True) en lugar de doble igual True, ya que este último genera SQL incorrecto. Lo mismo aplica para comparaciones con None, donde se usa is_(None) o is_not(None).

---

## Capítulo 6: Los Servicios de Dominio

Los servicios de dominio residen en el subdirectorio services/domain y representan el corazón de la lógica de negocio. Cada servicio se especializa en un dominio específico del negocio, encapsulando todas las reglas, validaciones, y operaciones relacionadas con ese dominio. Esta es la ubicación preferida para nueva lógica de negocio, reemplazando el patrón CRUDFactory que está deprecado.

La clase base BaseCRUDService proporciona operaciones estándar de creación, lectura, actualización, y eliminación que los servicios especializados heredan y pueden sobrescribir. Esta herencia reduce la duplicación de código mientras permite personalización donde sea necesaria. El constructor recibe la sesión de base de datos siguiendo el patrón de inyección de dependencias, junto con el modelo SQLAlchemy, el schema Pydantic de salida, el nombre de la entidad en español para mensajes de error, y configuraciones opcionales como si la entidad tiene branch_id o si soporta soft delete.

La clase BranchScopedService extiende la base para entidades que pertenecen a una sucursal específica, añadiendo automáticamente el uso de BranchRepository y métodos de listado por branch. Los servicios para categorías, mesas, sectores y tablas heredan de esta clase.

Los servicios implementan hooks que se invocan en momentos específicos del ciclo de vida de las operaciones, permitiendo personalización sin sobrescribir completamente los métodos base. Este patrón de Template Method mantiene la estructura común mientras habilita comportamiento específico por entidad.

El hook _validate_create se invoca antes de crear una entidad, recibiendo los datos propuestos y el tenant_id. Aquí el servicio puede validar reglas de negocio complejas como verificar que la categoría padre existe, verificar unicidad personalizada más allá de constraints de base de datos, o rechazar la operación con una excepción descriptiva si los datos no cumplen invariantes del negocio.

El hook _validate_update se invoca antes de actualizar una entidad, recibiendo la entidad existente y los datos propuestos. Puede validar que los cambios son permitidos según el estado actual de la entidad, verificar invariantes del negocio que dependen de valores anteriores, o prevenir modificaciones de campos protegidos como identificadores o claves foráneas críticas.

El hook _validate_delete se invoca antes de eliminar una entidad, verificando que la eliminación es permitida. Puede verificar que no existan dependencias que impedirían la eliminación sin cascada, o que el usuario tenga permisos específicos para eliminar esta entidad particular más allá del permiso genérico de rol.

El hook _after_create se invoca después de crear exitosamente una entidad, útil para efectos secundarios como publicar eventos de dominio ENTITY_CREATED a través de Redis, actualizar caches invalidando entradas relacionadas, o notificar a sistemas externos mediante webhooks.

El hook _after_update se invoca después de actualizar exitosamente, permitiendo publicar eventos de cambio ENTITY_UPDATED o sincronizar datos derivados que dependen de los valores modificados.

El hook _after_delete se invoca después de eliminar exitosamente, permitiendo publicar eventos de eliminación ENTITY_DELETED, limpiar datos relacionados en sistemas externos, o registrar la eliminación en logs de auditoría adicionales.

Entre los servicios especializados más importantes, el CategoryService gestiona categorías de productos con ordenamiento automático, calculando el siguiente orden disponible cuando se crea una categoría sin especificar orden y permitiendo reorganizar múltiples categorías en una sola operación transaccional mediante reorder_categories.

El ProductService maneja la complejidad de productos con múltiples relaciones. La creación de un producto puede incluir precios por sucursal mediante BranchProduct, asociaciones con alérgenos incluyendo tipos de presencia y niveles de riesgo, vinculación con ingredientes en la jerarquía de tres niveles, perfiles dietéticos, información de cocción con métodos y tiempos, perfiles sensoriales con sabores y texturas, modificaciones permitidas, advertencias, configuración RAG, y opcionalmente sincronización con una receta vinculada. El servicio orquesta todas estas operaciones relacionadas manteniendo consistencia transaccional.

El AllergenService gestiona alérgenos incluyendo sus reacciones cruzadas. Cuando se asocia un alérgeno a un producto, el servicio puede advertir sobre otros alérgenos con reacciones cruzadas conocidas que deberían considerarse para la seguridad alimentaria del comensal.

El StaffService implementa reglas especiales para gestión de personal. Los managers solo pueden crear staff con roles iguales o menores a su propio rol. Las modificaciones de roles requieren verificar que el usuario tiene permiso para asignar ese rol específico. La eliminación de un usuario verifica que no sea el último administrador del tenant.

El RoundService gestiona el ciclo de vida completo de pedidos desde su creación hasta su entrega. Implementa las transiciones de estado PENDING a CONFIRMED cuando el mozo verifica, CONFIRMED a SUBMITTED cuando el admin envía a cocina, SUBMITTED a IN_KITCHEN cuando la cocina comienza preparación, IN_KITCHEN a READY cuando termina, y READY a SERVED cuando se entrega. Cada transición valida que el estado anterior sea correcto, actualiza los timestamps correspondientes, y publica el evento apropiado.

El BillingService maneja la complejidad de facturación y pagos. Implementa el modelo de asignación FIFO donde los pagos se distribuyen a cargos en orden cronológico. Integra con Mercado Pago para pagos electrónicos con manejo de webhooks. Utiliza circuit breaker para resiliencia ante fallos del proveedor de pagos.

---

## Capítulo 7: El Sistema de Routers

Los routers HTTP se organizan en grupos funcionales que reflejan las diferentes audiencias y casos de uso de la API. Esta organización facilita la aplicación de políticas de seguridad diferentes por grupo y permite que los equipos trabajen independientemente en diferentes áreas.

El grupo auth maneja autenticación sin requerir token previo. Incluye el endpoint de login que valida credenciales mediante bcrypt, genera tokens JWT de acceso con duración de quince minutos y tokens de refresh con duración de siete días, y establece el token de refresh como cookie HttpOnly para prevenir acceso desde JavaScript siguiendo el fix SEC-09. El endpoint de refresh lee el token desde la cookie HttpOnly o el cuerpo como fallback, verifica contra la blacklist de Redis, genera nuevos tokens, y rota el refresh token para invalidar el anterior siguiendo SEC-06. El endpoint de logout invoca revoke_all_user_tokens para invalidar todos los tokens del usuario en todos los dispositivos agregándolos a la blacklist de Redis, y limpia la cookie HttpOnly. El endpoint me retorna información del usuario autenticado extraída del token JWT.

El grupo public expone endpoints accesibles sin autenticación. Incluye el catálogo público de productos para mostrar el menú en pwaMenu, la lista de sucursales para selección pre-login en pwaWaiter, y los endpoints de health check básico y detallado que incluye estado de Redis y métricas de conexiones.

El grupo tables gestiona sesiones de mesa mediante tokens de mesa en lugar de tokens de usuario. Incluye la creación de sesiones cuando un comensal escanea el código QR de la mesa, verificando que la mesa no tenga ya una sesión activa, creando el primer Diner con el device_id del header para tracking, y generando un table token firmado con HMAC que contiene session_id, branch_id y tenant_id. La obtención de estado de sesión permite sincronización entre dispositivos que comparten la misma mesa.

El grupo diner implementa operaciones para comensales autenticados mediante tokens de mesa validados en el header X-Table-Token. Incluye el registro de comensales adicionales en una sesión existente. La gestión del carrito compartido mediante endpoints para agregar, actualizar, eliminar y listar items, donde cada operación publica eventos CART_ITEM_ADDED, CART_ITEM_UPDATED o CART_ITEM_REMOVED a través de Redis para sincronización en tiempo real entre dispositivos. La creación de pedidos que combina items de todos los comensales en un Round con estado PENDING. Las operaciones de fidelización de clientes incluyendo registro con consentimiento GDPR, reconocimiento de dispositivo vinculado a customer, y sugerencias personalizadas basadas en historial.

El grupo kitchen proporciona endpoints para personal de cocina autenticado con JWT y rol KITCHEN o superior. Incluye el listado de rondas con estado SUBMITTED para la vista de nuevos pedidos y estado IN_KITCHEN para pedidos en preparación. La actualización de estado de preparación permite transiciones de SUBMITTED a IN_KITCHEN cuando la cocina comienza y de IN_KITCHEN a READY cuando termina. La gestión de tickets de cocina agrupa items de pedido para organización interna.

El grupo waiter implementa operaciones para mozos autenticados con JWT y rol WAITER o superior. Incluye la verificación de asignación de sucursal para el día actual mediante verify-branch-assignment. El listado de mesas filtradas por sectores asignados mediante WaiterSectorAssignment, donde ADMIN y MANAGER ven todas las mesas. El menú compacto para comanda rápida que retorna productos sin imágenes para reducir payload. La creación de rondas en nombre de clientes para el flujo de comanda rápida donde el mozo toma el pedido verbalmente. La confirmación de rondas que transiciona de PENDING a CONFIRMED cuando el mozo verifica el pedido en la mesa.

El grupo billing maneja pagos y facturación. Incluye la solicitud de cuenta que crea un Check y publica CHECK_REQUESTED mediante el patrón Outbox para garantía de entrega. El registro de pagos en efectivo que crea Payment y ejecuta el algoritmo de asignación FIFO a Charges pendientes. La integración con Mercado Pago para pagos electrónicos incluyendo creación de preferencias de pago y recepción de webhooks de confirmación con verificación de firma HMAC. El procesamiento de webhooks actualiza el estado del pago y publica PAYMENT_APPROVED o PAYMENT_REJECTED mediante Outbox.

El grupo admin expone operaciones CRUD completas para el panel de administración. Contiene quince routers especializados para diferentes entidades organizados por dominio. El router products gestiona productos con todas sus relaciones. El router categories maneja categorías con ordenamiento. El router subcategories gestiona subcategorías anidadas. El router allergens administra alérgenos y reacciones cruzadas. El router ingredients maneja la jerarquía de ingredientes. El router staff gestiona usuarios y roles con restricciones por rol del operador. El router branches administra sucursales. El router tables gestiona mesas físicas. El router sectors define sectores del restaurante. El router assignments maneja asignaciones diarias de mozos a sectores. El router promotions gestiona promociones con validación de fechas. El router audit proporciona acceso a logs de auditoría. El router restore permite recuperar entidades eliminadas. El router reports genera reportes operacionales. El router tenant administra configuración del restaurante.

El grupo content gestiona contenido administrable que no encaja en otras categorías. Incluye catálogos de métodos de cocción, perfiles de sabor, texturas y tipos de cocina. La gestión de recetas con fichas técnicas de cocina incluyendo ingredientes, instrucciones, tiempos y rendimientos. La administración de promociones con branches y productos asociados. El chatbot RAG con inteligencia artificial que utiliza embeddings vectoriales en pgvector para búsqueda semántica de documentos de conocimiento.

El grupo metrics expone un endpoint para scraping de Prometheus que retorna métricas del sistema en formato text/plain, incluyendo conexiones activas, eventos procesados, errores, y latencias.

Todos los routers siguen un patrón consistente que mantiene la lógica HTTP separada de la lógica de negocio. El primer paso extrae los parámetros de la petición HTTP mediante argumentos tipados y Query con valores por defecto. El segundo paso obtiene las dependencias inyectadas incluyendo la sesión de base de datos mediante get_db y el usuario autenticado mediante current_user que valida el token JWT y extrae los claims. El tercer paso crea un PermissionContext a partir del usuario autenticado que selecciona automáticamente la estrategia de permisos apropiada según los roles. El cuarto paso valida permisos invocando métodos del contexto como require_management o require_branch_access que lanzan excepciones HTTP si el usuario no tiene los permisos necesarios. El quinto paso instancia el servicio de dominio apropiado y delega la operación, retornando el resultado que FastAPI serializa automáticamente a JSON.

---

## Capítulo 8: El Sistema de Autenticación

La autenticación utiliza JSON Web Tokens firmados que contienen toda la información necesaria para autorizar peticiones sin consultar la base de datos en cada request. Este diseño stateless permite escalabilidad horizontal del servicio.

El token de acceso tiene una duración corta de quince minutos, limitando la ventana de exposición si un token es comprometido. Contiene claims con el identificador del usuario en el campo sub, el email para logging, el tenant_id al que pertenece, los branch_ids de sucursales a las que tiene acceso, y los roles asignados como ADMIN, MANAGER, KITCHEN o WAITER. La firma HMAC-SHA256 con JWT_SECRET garantiza que el token no ha sido modificado.

El token de refresh tiene una duración más larga de siete días, permitiendo renovar el acceso sin requerir credenciales frecuentemente. Este token se almacena como cookie HttpOnly para prevenir acceso desde JavaScript y mitigar ataques XSS. La cookie se configura con secure verdadero en producción para requerir HTTPS, samesite lax para protección CSRF, y path restringido a /api/auth. Cuando se utiliza para obtener nuevos tokens, se verifica contra una lista de tokens revocados almacenada en Redis con TTL igual a la duración del token, soportando logout efectivo. El fix SEC-06 implementa rotación del refresh token donde cada uso invalida el token anterior, previniendo reuso si es interceptado.

El token de mesa tiene una duración de tres horas, reducida desde ocho horas en el fix CRIT-04 para limitar la ventana de exposición. Contiene el session_id de la sesión de mesa, el branch_id de la sucursal, y el tenant_id del restaurante. Este token permite a los comensales operar sin cuentas de usuario, autenticándose únicamente mediante el código QR de la mesa que se codifica con el código de mesa y el slug de sucursal. La firma utiliza TABLE_TOKEN_SECRET independiente del secreto JWT.

El flujo de autenticación de usuarios comienza cuando el cliente envía credenciales al endpoint de login. El servidor verifica que el usuario existe y está activo. Valida la contraseña mediante bcrypt que incluye salt automático y es resistente a timing attacks. Genera el token de acceso con los claims del usuario. Genera el token de refresh con un identificador único JTI. Establece la cookie HttpOnly con el refresh token. Retorna el access token en el cuerpo de la respuesta junto con información básica del usuario.

Para peticiones autenticadas, el cliente incluye el access token en el header Authorization con formato Bearer seguido del token. La dependencia current_user de FastAPI extrae el token, verifica la firma con JWT_SECRET, comprueba que no haya expirado, consulta la blacklist de Redis para tokens revocados, y retorna un diccionario con los claims del usuario que incluye sub, email, tenant_id, branch_ids, y roles.

Cuando el access token expira, el cliente llama al endpoint de refresh. El servidor lee el refresh token desde la cookie HttpOnly que el navegador envía automáticamente con credentials include. Verifica la firma y expiración del refresh token. Consulta la blacklist para verificar que no ha sido revocado. Genera nuevos tokens de acceso y refresh. Revoca el refresh token anterior agregándolo a la blacklist. Establece la nueva cookie con el refresh token rotado. Retorna el nuevo access token.

El logout revoca todos los tokens del usuario invocando revoke_all_user_tokens que lista todos los JTI activos del usuario y los agrega a la blacklist de Redis con TTL de siete días. Limpia la cookie HttpOnly. Esto invalida la sesión en todos los dispositivos inmediatamente.

La autenticación de comensales por mesa funciona diferente. Cuando un comensal escanea el código QR, el frontend decodifica el código de mesa y slug de sucursal. Envía una petición al endpoint de creación de sesión sin autenticación previa. El servidor busca la mesa por código dentro de la sucursal identificada por slug. Verifica que la mesa no tenga sesión activa. Crea una nueva TableSession con timestamp de inicio. Crea el primer Diner capturando el device_id del header X-Device-Id para tracking cross-session. Genera el table token firmado con HMAC-SHA256 usando TABLE_TOKEN_SECRET. Retorna el token que el frontend almacena y usa en peticiones subsecuentes mediante el header X-Table-Token.

---

## Capítulo 9: El Sistema de Permisos

El PermissionContext actúa como fachada para todo el sistema de autorización, proporcionando una interfaz consistente independientemente del rol del usuario. Su constructor analiza los claims del token JWT y selecciona automáticamente la estrategia de permisos apropiada basándose en los roles, eligiendo la de mayor privilegio si el usuario tiene múltiples roles.

Las propiedades del contexto exponen información extraída del token de manera tipada. La propiedad user_id retorna el identificador numérico del usuario parseado del claim sub. La propiedad tenant_id retorna el identificador del restaurante. La propiedad branch_ids retorna la lista de sucursales accesibles. La propiedad roles retorna la lista de roles asignados. Las propiedades booleanas is_admin e is_management simplifican verificaciones comunes donde is_management es verdadero si el usuario es ADMIN o MANAGER.

Los métodos de verificación de capacidad consultan la estrategia para determinar si una acción está permitida. El método can recibe una acción del enum Action que puede ser CREATE, READ, UPDATE o DELETE, junto con la entidad o tipo de entidad y opcionalmente un branch_id. Retorna un booleano permitiendo lógica condicional en el código del servicio. Los métodos can_create, can_read, can_update y can_delete son atajos convenientes para acciones específicas.

Los métodos de requerimiento lanzan excepciones si la condición no se cumple, cortocircuitando la ejecución. El método require_admin lanza ForbiddenError si el usuario no tiene rol ADMIN. El método require_management acepta administradores o managers, lanzando excepción para otros roles. El método require_branch_access verifica acceso a una sucursal específica comprobando que branch_id esté en la lista branch_ids del usuario o que sea ADMIN que tiene acceso implícito a todo.

El sistema implementa el patrón Strategy con cinco estrategias especializadas para diferentes roles. Las estrategias siguen además el Principio de Segregación de Interfaces mediante mixins que permiten componer comportamientos sin duplicación de código.

La estrategia de administrador implementada en AdminStrategy otorga acceso total a todas las operaciones del tenant. Puede crear, leer, actualizar, y eliminar cualquier entidad. No tiene restricciones de sucursal. El método filter_query retorna la query sin modificaciones adicionales más allá del filtro de tenant que ya aplican los repositorios.

La estrategia de manager implementada en ManagerStrategy permite operaciones limitadas a sus sucursales asignadas. Puede crear personal con roles iguales o menores, mesas, alérgenos, y promociones dentro de sus branches. Puede leer y actualizar la mayoría de entidades de sus sucursales. No puede eliminar entidades, delegando esa responsabilidad a administradores. El método filter_query añade una cláusula where que filtra por branch_id en la lista de branch_ids del usuario.

La estrategia de cocina implementada en KitchenStrategy es más restrictiva, enfocada en operaciones de preparación de alimentos. Define conjuntos explícitos de entidades legibles como Round, KitchenTicket, Product, Category y Recipe, y actualizables como Round y KitchenTicket. Puede leer estas entidades de sus sucursales asignadas. Puede actualizar el estado de rondas y tickets. No puede crear ni eliminar entidades, heredando NoCreateMixin y NoDeleteMixin que retornan falso para esas operaciones. El filtrado de consultas excluye automáticamente entidades de sucursales no asignadas.

La estrategia de mozo implementada en WaiterStrategy soporta operaciones de servicio al cliente. Puede crear llamadas de servicio ServiceCall, rondas Round, y registrar comensales Diner. Puede leer mesas, sesiones, rondas, productos y cuentas de sus sucursales. Puede actualizar rondas para confirmar pedidos y llamadas de servicio para marcar atención. No puede eliminar entidades. El filtrado considera tanto sucursales como potencialmente sectores asignados para el día actual mediante WaiterSectorAssignment.

La estrategia de solo lectura implementada en ReadOnlyStrategy proporciona acceso mínimo para roles especiales o no reconocidos. Solo puede leer entidades básicas, sin capacidad de crear, actualizar, o eliminar. Se utiliza como fallback cuando el usuario no tiene ningún rol reconocido.

Los mixins permiten componer comportamientos comunes entre estrategias sin duplicación. El mixin NoCreateMixin implementa can_create retornando siempre falso. El mixin NoDeleteMixin implementa can_delete retornando siempre falso. El mixin NoUpdateMixin implementa can_update retornando siempre falso. El mixin BranchFilterMixin implementa el filtrado automático de consultas por branch_ids del usuario, verificando que la entidad tenga atributo branch_id y añadiendo el filtro correspondiente. El mixin BranchAccessMixin proporciona helpers para verificar acceso a branches específicos incluyendo _user_has_branch_access y _get_entity_branch_id.

La función get_highest_privilege_strategy recibe la lista de roles del usuario y retorna la instancia de estrategia con mayor privilegio. El orden de precedencia es ADMIN primero, luego MANAGER, KITCHEN, WAITER, y finalmente ReadOnly como fallback. Si un usuario tiene roles WAITER y MANAGER, obtiene ManagerStrategy que tiene más permisos.

---

## Capítulo 10: El Sistema de Eventos de Dominio

El sistema de eventos permite que diferentes partes de la aplicación reaccionen a cambios sin acoplamiento directo. Cuando un servicio modifica datos, publica un evento que describe el cambio. Otros sistemas suscritos a ese tipo de evento pueden reaccionar apropiadamente, desde actualizar interfaces en tiempo real hasta sincronizar sistemas externos.

Los tipos de eventos están definidos en un módulo centralizado. Los eventos de entidad incluyen ENTITY_CREATED cuando se crea una nueva entidad, ENTITY_UPDATED cuando se modifica, ENTITY_DELETED cuando se elimina, y CASCADE_DELETE cuando la eliminación afecta entidades relacionadas. Los eventos de pedido siguen el ciclo de vida con ROUND_PENDING para nuevos pedidos, ROUND_CONFIRMED cuando el mozo verifica, ROUND_SUBMITTED cuando se envía a cocina, ROUND_IN_KITCHEN cuando la cocina comienza preparación, ROUND_READY cuando está listo, ROUND_SERVED cuando se entrega, y ROUND_CANCELED para cancelaciones. Los eventos de carrito incluyen CART_ITEM_ADDED, CART_ITEM_UPDATED, CART_ITEM_REMOVED y CART_CLEARED. Los eventos de servicio incluyen SERVICE_CALL_CREATED cuando el comensal solicita atención y SERVICE_CALL_ACKED cuando el mozo responde. Los eventos de pago incluyen CHECK_REQUESTED cuando se solicita la cuenta, CHECK_PAID cuando se completa el pago, PAYMENT_APPROVED para confirmación de pago electrónico, PAYMENT_REJECTED cuando el pago es rechazado, y PAYMENT_FAILED para errores de procesamiento.

La publicación de eventos se realiza mediante funciones especializadas del módulo events. La función publish_event recibe el pool de Redis, el canal destino, y el evento serializado. El routing de eventos a canales Redis se determina automáticamente según el tipo. Los eventos de administración van al canal admin de la sucursal siguiendo el patrón admin:branch:id. Los eventos de cocina van al canal kitchen:branch:id. Los eventos de mozo van al canal waiters:branch:id. Los eventos de sesión van al canal session:session_id para los comensales específicos de esa mesa. Los eventos con sector_id específico se enrutan solo a mozos asignados a ese sector.

Para eventos no críticos donde cierta pérdida es aceptable, la publicación se realiza directamente a Redis de manera asíncrona. Esto incluye eventos de carrito CART_*, eventos de estado intermedio de pedido como ROUND_CONFIRMED o ROUND_IN_KITCHEN, eventos de sesión de mesa, y eventos de entidad ENTITY_*.

Para eventos críticos donde la pérdida es inaceptable, el sistema implementa el patrón Outbox que garantiza consistencia entre datos y eventos mediante transacciones de base de datos. Esto incluye eventos financieros como CHECK_REQUESTED, CHECK_PAID, PAYMENT_APPROVED y PAYMENT_REJECTED. Eventos de flujo crítico como ROUND_SUBMITTED y ROUND_READY. Eventos de servicio como SERVICE_CALL_CREATED donde hay SLA de respuesta.

Cuando un servicio necesita publicar un evento garantizado, en lugar de publicar directamente a Redis, invoca write_outbox_event o sus variantes especializadas write_billing_outbox_event, write_round_outbox_event, o write_service_call_outbox_event. Esta función inserta un registro en la tabla OutboxEvent dentro de la misma transacción que modifica los datos de negocio. El registro incluye tenant_id para aislamiento multi-tenant, event_type como ROUND_SUBMITTED, aggregate_type como round o check, aggregate_id con el identificador de la entidad, payload con los datos del evento en JSON, status como PENDING, y retry_count inicializado en cero. Si la transacción de negocio falla, tanto los datos como el evento se revierten. Si la transacción tiene éxito, el evento queda persistido junto con los datos, garantizando consistencia.

Un procesador en background implementado en outbox_processor.py consulta periódicamente la tabla de outbox buscando eventos con status PENDING ordenados por created_at. Para cada evento encontrado, actualiza el status a PROCESSING para evitar procesamiento duplicado por otras instancias. Intenta publicarlo a Redis mediante el canal apropiado según el tipo de evento. Si la publicación tiene éxito, marca el registro con status PUBLISHED y registra processed_at. Si falla, incrementa retry_count, registra el error en last_error, y vuelve a status PENDING para reintento. El reintento usa backoff exponencial comenzando en un segundo y duplicando hasta un máximo de treinta segundos. Después de cinco intentos fallidos, el evento se marca como FAILED y se registra para intervención manual.

El procesador se inicia durante el startup de la aplicación en lifespan.py como una tarea asíncrona. Se configura con un intervalo de polling de un segundo y un tamaño de lote de cincuenta eventos por ciclo. Durante el shutdown, se cancela la tarea esperando que complete el lote actual.

Este diseño garantiza que los eventos eventualmente se publican si los datos se persistieron, eliminando la posibilidad de inconsistencias donde los datos cambian pero el evento se pierde. El trade-off es mayor latencia en la entrega del evento, típicamente entre uno y dos segundos adicionales, y complejidad del procesador. Para eventos donde la latencia sub-segundo es crítica y cierta pérdida es aceptable, se usa publicación directa.

---

## Capítulo 11: Middlewares de Seguridad

El middleware de headers de seguridad implementado en SecurityHeadersMiddleware añade headers protectores a todas las respuestas HTTP, implementando defensas en profundidad contra diversos vectores de ataque web.

El header X-Content-Type-Options con valor nosniff previene que navegadores intenten adivinar el tipo de contenido, mitigando ataques de sniffing MIME que podrían ejecutar scripts disfrazados como otros tipos de archivo.

El header X-Frame-Options con valor DENY previene que la página sea embebida en frames de otros sitios, mitigando ataques de clickjacking donde un atacante superpone una interfaz maliciosa sobre la aplicación.

El header Content-Security-Policy define una política restrictiva de fuentes de contenido siguiendo el fix HIGH-MID-01. Establece default-src como self para permitir solo recursos del mismo origen. Configura script-src como self sin unsafe-inline para prevenir scripts inyectados. Restringe style-src, img-src, font-src y connect-src a fuentes conocidas. Esta política mitiga ataques XSS al impedir la ejecución de código no autorizado.

El header Strict-Transport-Security se añade solo en producción e indica a navegadores que siempre deben usar HTTPS para este dominio. Incluye includeSubDomains y especifica max-age de un año en segundos, previniendo downgrades a HTTP donde un atacante podría interceptar tráfico.

El header Referrer-Policy controla cuánta información se envía en el header Referer cuando el usuario navega desde la aplicación a otros sitios. El valor strict-origin-when-cross-origin envía solo el origen para navegación cross-origin, protegiendo paths sensibles de ser filtrados a terceros.

El header Permissions-Policy deshabilita APIs de navegador que no son necesarias para la aplicación, incluyendo geolocation, microphone, y camera. Esto reduce la superficie de ataque y previene que código malicioso abuse de estas APIs.

El middleware de validación de Content-Type implementado en ContentTypeValidationMiddleware verifica que las peticiones con cuerpo utilicen tipos de contenido válidos, previniendo ataques que explotan parsing inesperado de formatos siguiendo el fix HIGH-04.

Para peticiones POST, PUT, y PATCH que modifican datos, el middleware verifica que el header Content-Type sea application/json o application/x-www-form-urlencoded. Otros tipos de contenido resultan en una respuesta 415 Unsupported Media Type sin procesar el cuerpo, previniendo que payloads maliciosos en formatos inesperados lleguen a los handlers.

Ciertos paths están exentos de esta validación y se mantienen en una lista explícita. Los endpoints de webhook de Mercado Pago aceptan el formato específico del proveedor que puede diferir. Los endpoints de health check no tienen cuerpo que validar. Esta lista de excepciones se mantiene mínima y documentada.

La configuración de CORS se centraliza en cors.py y controla qué orígenes pueden realizar peticiones a la API desde navegadores web, previniendo que sitios maliciosos realicen peticiones en nombre de usuarios autenticados.

En desarrollo, la configuración permite orígenes localhost en los puertos utilizados por las aplicaciones frontend. Esto incluye el puerto 5176 para pwaMenu, 5177 para Dashboard, 5178 y 5179 para pwaWaiter, junto con sus equivalentes usando la dirección IP 127.0.0.1 en lugar del hostname.

En producción, los orígenes permitidos se configuran mediante la variable de entorno ALLOWED_ORIGINS como lista separada por comas. Solo los orígenes explícitamente listados pueden realizar peticiones, rechazando cualquier otro origen con un error CORS que el navegador interpreta bloqueando la respuesta.

Los métodos HTTP permitidos incluyen GET para lecturas, POST para creaciones, PUT y PATCH para actualizaciones, DELETE para eliminaciones, y OPTIONS para preflight requests. Los headers permitidos incluyen Authorization para tokens JWT, Content-Type para especificar el tipo de cuerpo, X-Table-Token para autenticación de mesa, X-Request-ID para trazabilidad de peticiones, y X-Device-Id para identificación de dispositivo en tracking cross-session.

El middleware se registra último en la cadena porque debe procesar la respuesta después de todos los demás middlewares pero su verificación de origen ocurre primero.

---

## Capítulo 12: Rate Limiting

El sistema implementa rate limiting para proteger contra abuso y ataques de denegación de servicio. La implementación utiliza slowapi que integra con FastAPI y almacena contadores en Redis para compartir estado entre múltiples instancias del servicio.

Los endpoints de login tienen límites estrictos para prevenir ataques de fuerza bruta contra credenciales. Se aplica un límite de cinco intentos por minuto por dirección IP. También se aplica un límite por email para prevenir que un atacante distribuido apunte a una cuenta específica. Después de exceder el límite, las peticiones reciben respuesta 429 Too Many Requests con un header Retry-After indicando cuántos segundos esperar.

Los endpoints de pago tienen límites moderados para prevenir abuso mientras permiten operaciones legítimas. La solicitud de cuenta check/request permite diez peticiones por minuto por sesión de mesa. Los pagos en efectivo cash/pay permiten veinte por minuto. Las operaciones de Mercado Pago mercadopago/* permiten cinco por minuto por sesión, siendo más restrictivas debido al costo de integración externa.

El registro de comensales diner/register tiene un límite de veinte por minuto por dirección IP para prevenir creación masiva de diners falsos que podrían saturar las mesas.

Los endpoints administrativos tienen límites más generosos de cien peticiones por minuto ya que requieren autenticación JWT y los usuarios legítimos pueden necesitar realizar múltiples operaciones en secuencia durante la gestión del restaurante.

El rate limiting utiliza Redis para mantener contadores compartidos entre instancias del servicio mediante una clave que combina el identificador del límite con el identificador del cliente. Esto garantiza que los límites se apliquen correctamente incluso con múltiples réplicas de la API detrás de un balanceador de carga. Los contadores expiran automáticamente después de la ventana de tiempo, liberando memoria de Redis.

---

## Capítulo 13: Flujo de Creación de Producto

Cuando un administrador crea un nuevo producto desde el panel de administración, el sistema orquesta una secuencia completa que valida permisos, persiste datos con todas sus relaciones, y notifica a sistemas conectados.

El navegador envía una petición POST al endpoint admin/products con el cuerpo JSON conteniendo los datos del producto incluyendo nombre, descripción, categoría, subcategoría opcional, imagen, precios por sucursal, alérgenos con tipos de presencia, ingredientes, perfiles dietéticos, información de cocción, y configuración RAG opcional.

El middleware de CORS verifica que el origen del navegador esté en la lista de permitidos. El middleware de Content-Type valida que sea application/json. El middleware de seguridad prepara los headers protectores para la eventual respuesta.

El router de productos extrae el cuerpo y lo valida contra el schema Pydantic de creación de producto. Los campos obligatorios como nombre y category_id deben estar presentes. Los tipos deben coincidir con las especificaciones. Las validaciones de formato como longitud máxima de nombre, formato de URL de imagen, y rangos de precios se verifican automáticamente lanzando 422 Unprocessable Entity si fallan.

El router obtiene el usuario autenticado del token JWT mediante la dependencia current_user que verifica firma, expiración, y blacklist. Crea un PermissionContext que analiza los roles del usuario y selecciona la estrategia correspondiente. Invoca require_management que verifica que el usuario tenga rol ADMIN o MANAGER, lanzando 403 Forbidden si no cumple. Si el usuario es MANAGER, verifica además mediante require_branch_access que tenga acceso a todas las sucursales especificadas en los precios del producto.

El router instancia ProductService pasando la sesión de base de datos y delega la creación invocando create_full. El servicio invoca su hook de validación _validate_create que verifica que la categoría existe en el tenant, que la subcategoría si se especifica pertenece a esa categoría, que el nombre no esté duplicado dentro de la categoría, y que las URLs de imagen pasen validación SSRF previniendo acceso a IPs internas.

El servicio crea la instancia del modelo Product con los datos proporcionados, estableciendo el tenant_id del contexto del usuario. Invoca helpers de auditoría para registrar created_by_id y created_by_email con los datos del usuario actual. Añade la entidad a la sesión de SQLAlchemy.

El servicio procesa las relaciones del producto. Crea registros BranchProduct para cada precio por sucursal especificado. Crea registros ProductAllergen para cada alérgeno con su tipo de presencia y nivel de riesgo. Crea registros ProductIngredient vinculando con ingredientes de la jerarquía. Crea o actualiza el DietaryProfile asociado. Crea registros ProductCookingMethod con tiempos de preparación. Crea registros ProductFlavor y ProductTexture para el perfil sensorial. Crea registros de modificaciones permitidas y advertencias. Configura RAGConfig si se especifica.

Si el producto especifica inherits_from_recipe con una receta vinculada, el servicio invoca _sync_from_recipe que copia los alérgenos de la receta al producto, manteniendo sincronización automática.

El servicio realiza un solo commit transaccional que persiste el producto y todas sus relaciones atómicamente. Si cualquier operación falla, todo se revierte.

Después del commit exitoso, el hook _after_create publica un evento ENTITY_CREATED a Redis mediante el canal admin de la sucursal. El WebSocket Gateway recibe el evento mediante su suscripción Redis. Lo distribuye a las conexiones administrativas de esa sucursal. Los dashboards conectados reciben el evento via WebSocket y actualizan su interfaz mostrando el nuevo producto sin necesidad de refresh manual.

El servicio transforma la entidad persistida en el schema de salida Pydantic ProductOutput y retorna al router. El router retorna este schema que FastAPI serializa a JSON con código 200 OK. Los headers de seguridad añadidos por el middleware acompañan la respuesta al navegador.

---

## Capítulo 14: Flujo de Pedido desde Escaneo QR hasta Entrega

El ciclo de vida completo de un pedido atraviesa múltiples estados, involucra diferentes actores, y genera eventos que sincronizan todas las interfaces en tiempo real.

Cuando un comensal escanea el código QR de la mesa con su dispositivo móvil, el navegador decodifica la información embebida que incluye el código de mesa como INT-01 y el slug de sucursal. El frontend de pwaMenu envía una petición POST al endpoint tables/code/INT-01/session con el query parameter branch_slug. No se requiere autenticación para este endpoint inicial.

El router busca la sucursal por su slug único. Busca la mesa por su código dentro de esa sucursal específica, ya que los códigos de mesa no son únicos globalmente sino solo dentro de cada sucursal. Verifica que la mesa no tenga ya una sesión activa.

El servicio de mesas crea una nueva instancia de TableSession con el timestamp de inicio. Crea un primer Diner asociado a la sesión, capturando el device_id del header X-Device-Id para tracking cross-session que permitirá reconocer al comensal en visitas futuras. Genera un table token firmado con HMAC-SHA256 usando TABLE_TOKEN_SECRET que contiene session_id, branch_id, y tenant_id con expiración de tres horas.

El servicio publica un evento TABLE_SESSION_STARTED a Redis. El WebSocket Gateway lo distribuye a todos los mozos de esa sucursal mediante el canal waiters:branch:id. En pwaWaiter, los mozos asignados al sector de esa mesa ven la mesa cambiar de estado libre a ocupada con animación de blink azul. En el Dashboard, la mesa muestra estado ocupada en rojo.

El router retorna el table token y la información de sesión al frontend de pwaMenu. El frontend almacena el token en memoria y lo incluye en todas las peticiones subsecuentes mediante el header X-Table-Token.

El comensal navega el menú, aplica filtros de alérgenos o preferencias dietéticas, y agrega items al carrito. Cada operación de agregar invoca POST diner/cart/add con el producto y cantidad. El servicio crea un CartItem vinculado a la sesión y al diner específico. Publica CART_ITEM_ADDED al canal de sesión. Otros dispositivos en la misma mesa reciben el evento y actualizan su vista del carrito compartido, mostrando quién agregó cada item con su nombre y color identificador.

Cuando los comensales están listos, uno de ellos inicia el proceso de confirmación grupal. El sistema muestra un panel de confirmación donde cada comensal indica que está listo. Cuando todos confirman, el frontend envía POST diner/orders con el carrito completo.

El servicio de pedidos verifica idempotencia mediante un idempotency_key único para prevenir duplicados si hay reintento. Crea un Round con todos los items del carrito combinando los de todos los comensales. Establece status PENDING. Captura el precio de cada producto al momento del pedido en RoundItem para preservar el precio histórico. Limpia los CartItems de la sesión. Publica CART_CLEARED para sincronizar que el carrito está vacío en todos los dispositivos.

Publica ROUND_PENDING al canal de waiters y admin. En pwaWaiter, los mozos asignados al sector ven una notificación de nuevo pedido con la mesa parpadeando en amarillo. En el Dashboard, la mesa muestra badge Pendiente en amarillo. La cocina NO recibe este evento ya que primero debe verificarlo un mozo.

Un mozo se acerca a la mesa, verifica verbalmente que el pedido coincide con lo solicitado por los comensales, y confirma desde pwaWaiter. Invoca PATCH waiter/rounds/id/confirm. El servicio valida que el round está en PENDING. Actualiza a CONFIRMED registrando confirmed_by_user_id con el mozo que verificó. Publica ROUND_CONFIRMED al canal admin.

En el Dashboard, la mesa muestra badge Confirmado en azul. El administrador o manager ve el pedido verificado y puede enviarlo a cocina mediante el botón correspondiente. Invoca PATCH admin/rounds/id/submit. El servicio valida que el round está en CONFIRMED. Actualiza a SUBMITTED registrando submitted_at con el timestamp. Invoca write_round_outbox_event para garantizar entrega del evento crítico. Realiza commit que persiste tanto el cambio de estado como el OutboxEvent atómicamente.

El procesador Outbox detecta el nuevo evento pendiente, lo marca como procesando, y publica ROUND_SUBMITTED a los canales kitchen, admin, y waiters. Las terminales de cocina reciben el evento y muestran el pedido en la columna Nuevos. El Dashboard actualiza el badge a En Cocina en azul.

El personal de cocina comienza preparación y actualiza desde la interfaz de cocina invocando PATCH kitchen/rounds/id/in_progress. El servicio valida SUBMITTED, actualiza a IN_KITCHEN. Publica ROUND_IN_KITCHEN a todos los canales incluyendo el de sesión. Los comensales en pwaMenu ven que su pedido está siendo preparado.

Cuando la cocina termina, marca el pedido como listo invocando PATCH kitchen/rounds/id/ready. El servicio valida IN_KITCHEN, actualiza a READY. Invoca write_round_outbox_event por ser evento crítico. Publica ROUND_READY a todos los canales incluyendo sesión. Los comensales reciben notificación de que su pedido está listo. El Dashboard muestra badge Listo en verde. Si hay otros pedidos de la misma mesa aún en cocina, muestra badge combinado Listo + Cocina en naranja con animación continua para alertar al mozo.

El mozo asignado al sector recibe notificación prominente, recoge el pedido de la cocina, y lo entrega a la mesa. Confirma entrega desde pwaWaiter invocando PATCH waiter/rounds/id/served. El servicio actualiza a SERVED. Publica ROUND_SERVED. Las interfaces muestran el pedido como completado. Las métricas de tiempo de servicio se calculan comparando timestamps y almacenan para reportes operacionales.

---

## Capítulo 15: El Sistema de Pagos

El procesamiento de pagos implementa patrones de resiliencia para manejar las complejidades de operaciones financieras donde los fallos deben manejarse cuidadosamente y la pérdida de eventos es inaceptable.

El modelo de asignación FIFO implementado en allocation.py distribuye pagos a cargos en orden cronológico. Cuando llega un pago, el sistema obtiene los cargos de la cuenta que tienen saldo pendiente, ordenados por fecha de creación. Itera asignando el monto del pago al cargo más antiguo primero, creando un registro Allocation que vincula el pago con el cargo por el monto asignado. Si queda excedente después de saldar el primer cargo, continúa con el siguiente. El proceso repite hasta agotar el monto del pago o saldar todos los cargos. Si queda saldo de pago sin asignar, se registra como crédito a favor.

El circuit breaker implementado en circuit_breaker.py protege contra fallos en cascada cuando el proveedor de pagos o Redis experimentan problemas. Mantiene un contador de fallos consecutivos. Cuando se alcanzan cinco fallos, el breaker transiciona de estado CLOSED a OPEN. En estado abierto, rechaza nuevas operaciones inmediatamente retornando error sin intentar la operación, evitando acumular timeouts que degradarían el sistema completo. Después de treinta segundos en estado abierto, transiciona a HALF_OPEN y permite una operación de prueba. Si tiene éxito, vuelve a CLOSED y resume operación normal. Si falla, vuelve a OPEN reiniciando el timer.

La integración con Mercado Pago maneja el flujo completo de pagos electrónicos. Cuando el comensal solicita pagar con tarjeta, el frontend invoca el endpoint para crear una preferencia de pago. El servicio construye la preferencia con los items de la cuenta, URLs de retorno para éxito y fallo, y configuración de webhooks. Invoca la API de Mercado Pago con el access token configurado. Retorna la URL de checkout donde el comensal completa el pago en la interfaz de Mercado Pago.

Cuando el pago se procesa, Mercado Pago envía un webhook POST al endpoint configurado. El middleware permite este path específico sin validación de Content-Type ya que el formato lo determina Mercado Pago. El handler verifica la autenticidad del webhook mediante la firma HMAC incluida en headers, comparando con el secreto configurado en MERCADOPAGO_WEBHOOK_SECRET. Si la firma no coincide, rechaza el webhook con 401.

El handler obtiene los detalles completos del pago invocando la API de Mercado Pago con el payment_id incluido en el webhook. Determina el estado: approved, rejected, o pending. Localiza el pago interno mediante el external_reference que vincula con la cuenta. Actualiza el estado del Payment y registra los detalles de la transacción.

Si el pago está aprobado, invoca el algoritmo FIFO para asignar a cargos pendientes. Invoca write_billing_outbox_event con tipo PAYMENT_APPROVED para garantizar que el evento de confirmación llegue a todas las interfaces. Si el pago es rechazado, registra el motivo de rechazo e invoca write_billing_outbox_event con PAYMENT_REJECTED.

Si el webhook falla temporalmente por problemas de red o base de datos, el reintentador de webhooks lo procesará nuevamente. Mantiene una cola de webhooks pendientes con backoff exponencial entre intentos, comenzando en un segundo y duplicando hasta treinta segundos máximo, con jitter aleatorio para evitar thundering herd. Después de cinco reintentos fallidos, marca el webhook para intervención manual y genera alerta.

---

## Capítulo 16: El Sistema RAG de Chatbot

El sistema de Retrieval-Augmented Generation proporciona un chatbot inteligente que responde consultas sobre el menú utilizando documentos ingresados y búsqueda semántica mediante embeddings vectoriales.

Los documentos de conocimiento se almacenan en KnowledgeDocument con su contenido textual y su embedding vectorial generado por un modelo de lenguaje. El embedding es un vector de alta dimensionalidad que captura el significado semántico del texto, permitiendo búsqueda por similitud conceptual en lugar de coincidencia exacta de palabras clave. La extensión pgvector de PostgreSQL almacena estos vectores y proporciona operadores de similitud eficientes.

Las recetas pueden ingresarse automáticamente al sistema de conocimiento mediante el endpoint recipes/id/ingest. El sistema extrae el contenido relevante incluyendo nombre, descripción, ingredientes con cantidades, instrucciones de preparación, tiempos de cocción, y rendimientos. Genera el embedding de este texto concatenado. Crea o actualiza el KnowledgeDocument asociado. Esto permite que el chatbot responda preguntas sobre preparación de platos basándose en las fichas técnicas de cocina.

Cuando un usuario hace una pregunta al chatbot mediante el endpoint de chat, el sistema genera un embedding de la consulta usando el mismo modelo. Ejecuta una búsqueda de similitud en pgvector para encontrar los documentos más cercanos semánticamente, típicamente los cinco más relevantes. La distancia coseno entre vectores determina la similitud donde menor distancia indica mayor relevancia.

El sistema construye un prompt que incluye los documentos recuperados como contexto, instrucciones sobre el rol del asistente como experto en el menú del restaurante, y la pregunta del usuario. Envía este prompt al modelo de lenguaje configurado, que puede ser Ollama corriendo localmente o un servicio cloud.

El modelo genera una respuesta informada por el contexto de los documentos recuperados. Esta respuesta se registra en ChatLog junto con la pregunta original para análisis posterior y mejora del sistema. Se retorna al usuario como respuesta del endpoint.

Este enfoque RAG combina las ventajas de búsqueda semántica que encuentra información relevante aunque las palabras exactas no coincidan, con las capacidades de generación de lenguaje natural que produce respuestas coherentes y contextuales en lugar de simplemente retornar fragmentos de documentos.

---

## Capítulo 17: Paginación y Consultas Optimizadas

La API implementa paginación consistente mediante un modelo Pagination y una dependencia get_pagination que los routers utilizan uniformemente para endpoints de listado.

El modelo de paginación define parámetros offset y limit con valores por defecto razonables y máximos configurados. El offset por defecto es cero, iniciando desde el primer registro. El límite por defecto varía según la entidad, típicamente cincuenta para entidades ligeras como categorías y veinte para entidades con muchas relaciones cargadas como productos con precios y alérgenos. Los límites máximos previenen que clientes soliciten conjuntos de datos excesivamente grandes que sobrecargarían memoria y red. Para productos el máximo es quinientos, para staff doscientos.

La respuesta de endpoints paginados incluye los items solicitados junto con metadatos de paginación. Los metadatos indican el offset actual desde donde se inició, el limit aplicado que puede diferir del solicitado si excedía el máximo, y el total de registros disponibles que cumplen los filtros independientemente de la paginación. Esta información permite a los clientes implementar navegación por páginas mostrando número de página y total, o scroll infinito cargando más registros al llegar al final.

La paginación se aplica a nivel de base de datos mediante cláusulas OFFSET y LIMIT en las consultas SQL, no filtrando resultados en memoria después de cargarlos. Esto es crucial para rendimiento con grandes volúmenes de datos ya que solo se transfieren de la base de datos los registros que se retornarán.

El conteo total se obtiene con una consulta COUNT separada y optimizada que no carga los datos de los registros. Algunos endpoints omiten el conteo total cuando no es necesario para la interfaz, evitando esta consulta adicional.

Los índices de base de datos optimizan las consultas más frecuentes. Un índice sobre tenant_id e is_active acelera los listados filtrados por tenant que son prácticamente todas las consultas. Un índice sobre branch_id e is_active optimiza listados por sucursal. Un índice sobre status en Round acelera las consultas de cocina por estado. Un índice sobre submitted_at permite ordenamiento eficiente de la cola de cocina. Un índice compuesto sobre branch_id y status optimiza las consultas de rondas pendientes por sucursal que son muy frecuentes.

---

## Capítulo 18: Soft Delete y Restauración

El sistema de soft delete preserva datos eliminados para auditoría y potencial recuperación, marcando registros como inactivos en lugar de eliminarlos físicamente. Esto cumple con requisitos de retención de datos, permite recuperación ante errores, y mantiene integridad referencial histórica.

La función soft_delete recibe la entidad a eliminar junto con el identificador y email del usuario que realiza la operación. Establece is_active en falso haciendo la entidad invisible para consultas normales. Registra el timestamp actual en deleted_at para saber cuándo se eliminó. Almacena el usuario en deleted_by_id y deleted_by_email para saber quién lo eliminó. No realiza commit, permitiendo que la operación sea parte de una transacción mayor que podría incluir otras operaciones relacionadas.

La función cascade_soft_delete extiende esto para manejar entidades relacionadas manteniendo consistencia referencial. El sistema mantiene un diccionario de relaciones de cascada que define qué entidades deben eliminarse junto con cada tipo de entidad. Cuando se elimina una categoría, también se eliminan sus subcategorías. Cuando se elimina una subcategoría, se eliminan sus productos. Cuando se elimina un producto, se eliminan sus precios por sucursal, asociaciones con alérgenos, y otras relaciones dependientes. La función retorna un diccionario describiendo todas las entidades afectadas por tipo y sus identificadores para logging de auditoría.

La función restore_entity revierte un soft delete, reactivando una entidad previamente eliminada. Establece is_active en verdadero haciéndola visible nuevamente. Limpia deleted_at, deleted_by_id, y deleted_by_email. Registra la restauración actualizando updated_at, updated_by_id, y updated_by_email con el usuario que restaura. Para entidades con cascada, ofrece la opción de restaurar también las entidades relacionadas que fueron eliminadas en la misma operación de cascada, verificando el timestamp de deleted_at para identificar cuáles fueron eliminadas juntas.

El endpoint administrativo admin/restore permite a administradores recuperar entidades eliminadas. El listado GET admin/restore muestra entidades eliminadas con sus metadatos incluyendo quién las eliminó, cuándo, y el tipo de entidad. Los filtros permiten buscar por tipo de entidad, rango de fechas de eliminación, y usuario que eliminó. La restauración POST admin/restore/type/id ejecuta la restauración con opción de incluir cascada. Solo usuarios con rol ADMIN pueden acceder a este endpoint ya que la restauración puede tener implicaciones significativas en el estado del sistema.

---

## Conclusión

La REST API del ecosistema Integrador representa una implementación madura de principios de arquitectura limpia adaptados a las necesidades específicas de la industria de restauración. Su diseño en capas separa responsabilidades de manera que cada componente puede evolucionar, testearse, y mantenerse independientemente.

El sistema de modelos con AuditMixin proporciona capacidades uniformes de auditoría y soft delete que cumplen con requisitos de trazabilidad empresarial. Más de cincuenta modelos organizados en veinte archivos modulares mantienen el código navegable mientras soportan la complejidad de relaciones entre entidades de un restaurante moderno.

Los repositorios encapsulan consultas con aislamiento multi-tenant automático mediante TenantRepository y BranchRepository, eliminando la posibilidad de fugas de datos entre restaurantes. La jerarquía de tres niveles proporciona el grado apropiado de filtrado para cada tipo de entidad.

Los servicios de dominio concentran la lógica de negocio con hooks de ciclo de vida que permiten personalización sin duplicación. Cada servicio mantiene las invariantes de su dominio, valida reglas complejas, y orquesta operaciones que involucran múltiples entidades y la publicación de eventos.

Los routers permanecen delgados delegando toda la lógica a servicios, facilitando el testing y manteniendo clara la separación entre preocupaciones HTTP y lógica de negocio. La organización por grupos funcionales permite que diferentes audiencias de la API tengan endpoints dedicados con políticas de seguridad apropiadas.

El sistema de permisos basado en estrategias proporciona control de acceso granular que se adapta automáticamente al rol del usuario. Los mixins permiten componer comportamientos comunes evitando duplicación mientras mantienen flexibilidad para casos especiales de cada rol.

El sistema de eventos de dominio desacopla la notificación de cambios de la lógica que los produce. El patrón Outbox garantiza consistencia para eventos críticos financieros y de workflow donde la pérdida sería inaceptable, mientras eventos no críticos usan publicación directa para menor latencia.

Los middlewares de seguridad implementan defensa en profundidad con headers que mitigan vectores de ataque comunes. La validación de Content-Type, el rate limiting, la configuración restrictiva de CORS, y las cookies HttpOnly para refresh tokens completan una postura de seguridad robusta.

Esta arquitectura sustenta las operaciones diarias de restaurantes, procesando desde la gestión de catálogos de productos hasta el flujo completo de pedidos desde el escaneo del QR por el comensal hasta la entrega en mesa, con trazabilidad completa de cada operación y notificaciones en tiempo real a todos los actores involucrados mediante la integración con el WebSocket Gateway.
