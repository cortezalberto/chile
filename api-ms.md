# REST API: Arquitectura y Documentación Técnica

Este documento describe en profundidad la arquitectura, diseño e implementación del módulo `rest_api` del sistema Integrador, un microservicio construido con FastAPI que sirve como el corazón del backend de gestión de restaurantes multi-sucursal.

---

## Introducción y Visión General

El módulo `rest_api` constituye la capa de servicios REST del sistema Integrador, una plataforma integral de gestión de restaurantes diseñada para operar en escenarios de alta concurrencia con múltiples sucursales, roles de usuario diferenciados y operaciones en tiempo real. Esta API ha sido construida siguiendo los principios de Clean Architecture, lo que garantiza una separación clara de responsabilidades entre las capas de presentación, dominio e infraestructura.

La API expone aproximadamente cien endpoints organizados en quince dominios funcionales, desde la autenticación de usuarios hasta el procesamiento de pagos con Mercado Pago, pasando por la gestión del catálogo de productos, la operativa de cocina y la fidelización de clientes. Cada endpoint ha sido diseñado con un enfoque en la seguridad, implementando autenticación JWT, validación de permisos basada en roles y protección contra las vulnerabilidades más comunes del OWASP Top 10.

El sistema maneja un modelo de datos complejo que comprende cincuenta y dos entidades de SQLAlchemy distribuidas en dieciocho módulos de dominio, desde la jerarquía multi-tenant de Tenant y Branch hasta los complejos flujos de pedidos que involucran Rounds, KitchenTickets y sistemas de pago con asignación FIFO.

---

## El Ciclo de Vida de la Aplicación

Cuando el servidor FastAPI inicia, el módulo `lifespan.py` orquesta una secuencia de inicialización meticulosamente diseñada que prepara el sistema para recibir solicitudes. Este proceso comienza con la configuración del sistema de logging estructurado, que permite trazabilidad completa de las operaciones en producción.

Inmediatamente después, el sistema ejecuta una validación de secretos de producción. Esta validación actúa como un guardián de seguridad: si la aplicación detecta que está ejecutándose en modo producción con secretos por defecto o inseguros, se niega a iniciar. Este patrón de "fail fast" garantiza que ningún sistema llegue a producción con configuraciones vulnerables. En entornos de desarrollo, el sistema emite advertencias pero permite la ejecución para facilitar la iteración rápida.

La siguiente fase habilita la extensión pgvector en PostgreSQL, un requisito fundamental para las capacidades de inteligencia artificial del sistema. Esta extensión permite almacenar y consultar embeddings vectoriales, habilitando el chatbot RAG que puede responder preguntas sobre recetas e ingredientes basándose en similitud semántica.

Una vez preparada la base de datos, SQLAlchemy crea o verifica las tablas necesarias basándose en los modelos definidos. Si la base de datos está vacía, el módulo `seed.py` la puebla con datos iniciales que incluyen un tenant de demostración, usuarios de prueba con diferentes roles, y un catálogo básico de categorías y productos.

El sistema también registra manejadores para reintentos de webhooks de Mercado Pago y lanza un procesador en background que periódicamente intenta reenviar webhooks fallidos, garantizando la consistencia eventual del sistema de pagos.

Durante el shutdown, el sistema cierra ordenadamente el cliente HTTP de Ollama utilizado por el chatbot RAG, libera los recursos del ejecutor de rate limiting, y cierra el pool de conexiones Redis que maneja la comunicación con el WebSocket Gateway.

---

## La Capa de Configuración del Núcleo

El directorio `core/` contiene tres módulos fundamentales que configuran aspectos transversales de la aplicación: el ciclo de vida descrito anteriormente, la configuración de middlewares de seguridad, y la gestión de CORS.

### Middlewares de Seguridad

El módulo `middlewares.py` implementa dos middlewares que se ejecutan en cada request. El primero, SecurityHeadersMiddleware, inyecta cabeceras de seguridad en todas las respuestas HTTP. Estas cabeceras incluyen `X-Content-Type-Options: nosniff` para prevenir ataques de MIME sniffing, `X-Frame-Options: DENY` para bloquear clickjacking, y una Content-Security-Policy estricta que solo permite recursos del mismo origen. En producción, también se añade Strict-Transport-Security para forzar conexiones HTTPS.

El segundo middleware, ContentTypeValidationMiddleware, actúa como guardián de los tipos de contenido. Cualquier request POST, PUT o PATCH que no declare `Content-Type: application/json` o `application/x-www-form-urlencoded` es rechazado con un error 415 Unsupported Media Type. Esta validación previene vectores de ataque que explotan la interpretación ambigua de tipos de contenido. Ciertos endpoints críticos como el webhook de Mercado Pago están exentos de esta validación para permitir payloads externos.

### Configuración de CORS

El módulo `cors.py` implementa una estrategia de CORS dinámica que se adapta al entorno de ejecución. En desarrollo, el sistema acepta requests desde una lista predefinida de orígenes localhost que incluye todos los puertos utilizados por los frontends del monorepo: 5176 para pwaMenu, 5177 para Dashboard, y 5178 para pwaWaiter. En producción, los orígenes permitidos se configuran exclusivamente a través de la variable de entorno ALLOWED_ORIGINS.

Un detalle técnico importante es el orden de registro de middlewares. CORS se registra último en la cadena, lo que significa que se ejecuta primero debido a la naturaleza de pila de los middlewares FastAPI. Esto garantiza que los requests de preflight OPTIONS sean manejados antes de que otros middlewares puedan interferir.

---

## El Modelo de Datos: Cincuenta y Dos Entidades de Dominio

El corazón del sistema reside en los modelos SQLAlchemy distribuidos en dieciocho módulos dentro del directorio `models/`. Cada módulo agrupa entidades relacionadas conceptualmente, facilitando la navegación y el mantenimiento del código.

### El Patrón AuditMixin

Todas las entidades del sistema heredan de un mixin de auditoría que proporciona soft delete y trazabilidad completa. Este patrón evita la pérdida de datos al marcar registros como inactivos en lugar de eliminarlos físicamente. Cada entidad mantiene campos para rastrear quién y cuándo la creó, modificó o eliminó, permitiendo reconstruir el historial completo de cambios.

El campo `is_active` actúa como filtro por defecto en todas las consultas: los repositorios automáticamente excluyen registros eliminados a menos que se solicite explícitamente incluirlos. Este diseño simplifica el código de negocio al tiempo que preserva la integridad referencial del sistema.

### La Jerarquía Multi-Tenant

El modelo de datos sigue una jerarquía estricta que comienza con Tenant, la entidad raíz que representa un restaurante o cadena de restaurantes. Cada Tenant puede tener múltiples Branch, que representan ubicaciones físicas con sus propios horarios, mesas y personal. Esta separación permite que una cadena de restaurantes opere múltiples sucursales con configuraciones independientes pero catálogos compartidos.

### El Catálogo de Productos

La estructura del menú sigue una jerarquía de tres niveles: Category agrupa productos en secciones como "Bebidas" o "Entradas", Subcategory permite subdivisiones más finas como "Cervezas" o "Ensaladas", y Product representa los ítems individuales del menú.

El modelo Product es particularmente sofisticado, con relaciones many-to-many hacia alérgenos, ingredientes, métodos de cocción, perfiles de sabor y textura. Estas relaciones permiten filtrado avanzado: un comensal celíaco puede filtrar productos seguros, mientras que un vegetariano puede excluir productos con carne.

La entidad BranchProduct permite precios diferenciados por sucursal. Un mismo producto puede costar diferente en el centro de la ciudad que en las afueras, sin duplicar el registro del producto.

### El Sistema de Alérgenos

La gestión de alérgenos va más allá de una simple lista. ProductAllergen incluye campos para tipo de presencia (contiene, puede contener, trazas) y nivel de riesgo, permitiendo comunicar con precisión el peligro para comensales con alergias. Además, AllergenCrossReaction modela las relaciones entre alérgenos que pueden desencadenar reacciones cruzadas, como la relación entre látex y ciertos frutos tropicales.

### El Flujo de Pedidos

El sistema de pedidos gira en torno a dos entidades principales: TableSession y Round. Cuando un comensal escanea un QR, se crea una TableSession que representa la ocupación de una mesa. Dentro de esa sesión, los comensales crean Rounds, que agrupan ítems pedidos juntos.

Un Round atraviesa un ciclo de vida de seis estados: PENDING cuando el comensal lo crea, CONFIRMED cuando el mesero lo valida en la mesa, SUBMITTED cuando administración lo envía a cocina, IN_KITCHEN mientras se prepara, READY cuando está listo para servir, y SERVED cuando se entrega. Este flujo estructurado garantiza que ningún pedido se pierda y que todas las partes involucradas tengan visibilidad del progreso.

### El Sistema de Facturación

El modelo de facturación implementa un sistema de pagos divididos con asignación FIFO. Cuando una mesa solicita la cuenta, se crea un Check que representa el total a pagar. Este total se distribuye en Charges, uno por cada comensal participante. Cuando llega un Payment, el sistema asigna automáticamente el monto a los Charges pendientes siguiendo el orden de creación, creando registros de Allocation que documentan cómo cada peso fue asignado.

---

## La Capa de Repositorios: Acceso a Datos Type-Safe

Entre los servicios de dominio y los modelos de SQLAlchemy existe una capa de repositorios que encapsula toda la lógica de acceso a datos. Este patrón, implementado en el directorio `repositories/`, proporciona varias garantías arquitecturales fundamentales.

### TenantRepository y BranchRepository

El sistema ofrece dos repositorios base que automatizan el filtrado multi-tenant. TenantRepository añade automáticamente la condición `tenant_id = ?` a todas las consultas, haciendo imposible que un tenant acceda accidentalmente a datos de otro. BranchRepository extiende esta protección con filtrado por branch, garantizando que operaciones sobre mesas, categorías o productos respeten la jerarquía organizacional.

Estos repositorios también encapsulan el patrón de eager loading para prevenir el infame problema N+1. Cuando el servicio de productos solicita una lista, el repositorio automáticamente carga las relaciones con alérgenos, ingredientes y perfiles de sabor en una sola consulta, evitando decenas de queries adicionales que degradarían el rendimiento.

### Repositorios Especializados

Para entidades con requisitos de consulta complejos, el sistema proporciona repositorios especializados. ProductRepository implementa filtros avanzados por categoría, precio, alérgenos y disponibilidad. RoundRepository optimiza la carga de pedidos con sus ítems y productos asociados. KitchenTicketRepository maneja la complejidad de los tickets de cocina con sus múltiples niveles de relaciones.

---

## Servicios de Dominio: El Corazón de la Lógica de Negocio

La capa más importante de la arquitectura Clean reside en el directorio `services/domain/`, donde diez servicios de dominio implementan la lógica de negocio del sistema. Estos servicios representan la evolución del sistema desde el patrón CRUDFactory original hacia una arquitectura más expresiva y mantenible.

### La Clase Base: BaseCRUDService

Todos los servicios de dominio heredan de BaseCRUDService, una clase genérica que proporciona operaciones CRUD estándar con hooks para personalización. Esta clase base maneja la transformación de entidades a DTOs, la validación de URLs de imágenes para prevenir SSRF, la integración con el sistema de auditoría, y la publicación de eventos de dominio.

El diseño utiliza el patrón Template Method: los métodos `create()`, `update()` y `delete()` definen el flujo general de la operación, pero delegan la validación y los efectos secundarios a hooks que las subclases pueden override. Por ejemplo, `_validate_create()` permite que ProductService verifique que la categoría existe antes de crear un producto, mientras que `_after_delete()` permite publicar eventos para sincronización en tiempo real.

### ProductService: Un Ejemplo de Complejidad Gestionada

El servicio de productos ejemplifica cómo la arquitectura maneja operaciones complejas. Crear un producto no es simplemente insertar un registro: implica validar que la categoría y subcategoría existen, procesar las relaciones con alérgenos (creando, actualizando o eliminando según corresponda), sincronizar ingredientes, establecer precios por sucursal, y publicar eventos para que el Dashboard se actualice en tiempo real.

ProductService encapsula toda esta complejidad en métodos cohesivos, mientras que el router correspondiente permanece como un controlador delgado que solo maneja aspectos HTTP: parseo de requests, validación de schemas Pydantic, y formateo de responses.

### StaffService: Lógica de Permisos Embebida

El servicio de personal ilustra cómo los servicios pueden encapsular reglas de negocio complejas relacionadas con permisos. Un Manager puede crear y editar usuarios, pero solo puede asignarles roles en las sucursales que él mismo administra, y nunca puede otorgar el rol Admin. Estas restricciones están codificadas en los hooks de validación del servicio, no dispersas por los routers.

---

## El Sistema de Permisos: Strategy Pattern en Acción

El directorio `services/permissions/` implementa un sistema de control de acceso basado en roles utilizando el patrón Strategy. Este diseño reemplazó más de cuarenta bloques if/elif dispersos por el código con una jerarquía de clases cohesiva y extensible.

### PermissionContext: El Guardián de Acceso

Cada request autenticado genera un PermissionContext que envuelve los claims del JWT con métodos de verificación. Este contexto expone propiedades como `is_admin` y `is_management`, y métodos como `require_branch_access(branch_id)` que lanzan ForbiddenError si el usuario no tiene los permisos necesarios.

El contexto también selecciona automáticamente la estrategia de permisos apropiada basándose en los roles del usuario. Un usuario con roles WAITER y KITCHEN recibe la estrategia de mayor privilegio entre ambos.

### Las Cinco Estrategias

El sistema define cinco estrategias de permisos en orden descendente de privilegio:

AdminStrategy otorga acceso completo a todas las operaciones y entidades. Es la única estrategia que permite eliminar staff o modificar configuraciones de tenant.

ManagerStrategy permite CRUD completo sobre la mayoría de entidades, pero restringe la eliminación de personal y limita las operaciones a las sucursales asignadas al manager.

KitchenStrategy proporciona acceso de lectura a productos, rounds y tickets de cocina, con capacidad de actualizar el estado de preparación pero sin permisos de creación o eliminación.

WaiterStrategy es similar a Kitchen pero orientada a las operaciones de servicio: puede ver mesas, actualizar estados de rounds, pero no acceder a la operativa de cocina.

ReadOnlyStrategy proporciona acceso de solo lectura, útil para dashboards de visualización sin capacidad de modificación.

### Interface Segregation con Mixins

El sistema implementa el principio ISP mediante mixins reutilizables. NoCreateMixin, NoDeleteMixin y NoUpdateMixin proporcionan implementaciones que siempre retornan False, permitiendo que estrategias como KitchenStrategy declaren explícitamente qué operaciones prohiben sin código duplicado.

---

## Los Routers: La Capa de Presentación HTTP

El directorio `routers/` organiza los endpoints en quince módulos de dominio, cada uno con su propio prefijo de URL y conjunto de responsabilidades. La filosofía de diseño mantiene estos routers deliberadamente delgados: su única responsabilidad es traducir entre el protocolo HTTP y los servicios de dominio.

### El Router de Autenticación

El módulo `auth/routes.py` expone cuatro endpoints fundamentales. El endpoint de login valida credenciales, genera tokens JWT de acceso y refresh, y almacena el refresh token en una cookie HttpOnly para prevenir ataques XSS. El endpoint de refresh lee el token de la cookie y emite nuevos tokens, implementando rotación de refresh tokens para mayor seguridad. Logout revoca todos los tokens del usuario mediante una blacklist en Redis, y el endpoint /me retorna el perfil del usuario autenticado.

### Los Routers de Admin

El módulo `admin/` es el más extenso, con quince sub-routers que exponen operaciones CRUD sobre todas las entidades administrativas. Cada router sigue el mismo patrón: lista paginada, obtener por ID, crear, actualizar y eliminar. La paginación se implementa mediante un dependency inyectable que parsea los parámetros limit y offset de la query string.

Los routers de admin también exponen endpoints especializados como restauración de entidades eliminadas, exportación de reportes de ventas, y visualización de logs de auditoría con filtros por tipo de entidad y rango de fechas.

### El Router de Cocina

Los endpoints de cocina permiten al personal actualizar el estado de rounds y visualizar tickets. Un aspecto crucial es la restricción de transiciones: solo el personal de cocina puede marcar un round como IN_KITCHEN o READY, y el sistema valida que las transiciones sigan el flujo definido. No es posible saltar de PENDING a READY sin pasar por los estados intermedios.

### El Router de Meseros

El router de waiters implementa filtrado por sector: cuando un mesero solicita la lista de mesas, el sistema consulta sus asignaciones del día actual y retorna solo las mesas de los sectores asignados. Administradores y managers, en cambio, ven todas las mesas de sus sucursales. Este filtrado ocurre en la capa de servicio, no en el router, garantizando consistencia independientemente de cómo se acceda a los datos.

### El Router Público

Algunos endpoints no requieren autenticación. El endpoint de menú público permite que el QR de una mesa cargue el catálogo sin login. El endpoint de salud permite que orquestadores como Kubernetes verifiquen que el servicio está operativo.

---

## El Sistema de Eventos: Comunicación en Tiempo Real

El directorio `services/events/` implementa un sistema de eventos de dominio que permite sincronización en tiempo real entre la API y los frontends conectados vía WebSocket.

Cuando un administrador crea una categoría, el servicio no solo persiste el registro en la base de datos: también publica un evento ENTITY_CREATED en un canal Redis. El WebSocket Gateway, suscrito a estos canales, recibe el evento y lo difunde a todos los dashboards conectados a ese tenant. El resultado es que la nueva categoría aparece instantáneamente en todos los navegadores sin necesidad de refresh.

El sistema soporta eventos para las operaciones CRUD básicas (created, updated, deleted) y para operaciones especiales como cascade delete, que notifica qué entidades fueron afectadas cuando se elimina una entidad padre.

Los eventos de dominio como ROUND_SUBMITTED siguen un flujo más complejo, con routing específico hacia los canales de cocina, meseros o comensales según la semántica del evento.

---

## El Sistema de Pagos: Resiliencia y Consistencia

El módulo `services/payments/` implementa la integración con Mercado Pago con especial énfasis en resiliencia ante fallos.

### Circuit Breaker para APIs Externas

La clase CircuitBreaker protege al sistema de cascadas de fallos cuando Mercado Pago experimenta problemas. El breaker mantiene tres estados: CLOSED durante operación normal, OPEN cuando detecta fallos consecutivos, y HALF_OPEN cuando intenta recuperarse.

En estado OPEN, el sistema no intenta llamar a Mercado Pago, retornando inmediatamente un error controlado. Esto previene acumulación de requests en cola y permite degradación graceful. Después de un timeout configurable, el breaker pasa a HALF_OPEN y permite un request de prueba. Si tiene éxito, retorna a CLOSED; si falla, vuelve a OPEN.

### Webhook Retry Queue

Los webhooks de Mercado Pago notifican pagos completados, pero la naturaleza de los webhooks es at-least-once: pueden fallar por timeouts de red o errores transitorios. El sistema mantiene una cola en memoria de webhooks fallidos y un procesador background que los reintenta con backoff exponencial.

### Asignación FIFO de Pagos

Cuando un pago llega, el sistema debe decidir qué deudas cubre. La función allocate_payment_fifo implementa una asignación estricta por orden de creación: el primer Charge pendiente recibe fondos primero, luego el segundo, y así sucesivamente. Este algoritmo garantiza fairness y evita ambigüedad en escenarios de pagos parciales.

---

## El Servicio RAG: Inteligencia Artificial Integrada

El módulo `services/rag/` implementa un chatbot de retrieval-augmented generation que puede responder preguntas sobre el menú basándose en documentos ingeridos.

El flujo comienza con la ingestión: cuando un administrador crea o modifica una receta, el sistema extrae el texto, lo divide en chunks, genera embeddings usando un modelo de lenguaje local via Ollama, y almacena estos vectores en PostgreSQL usando la extensión pgvector.

Cuando un cliente hace una pregunta como "¿qué platos tienen mariscos?", el sistema genera un embedding de la pregunta, busca los chunks más similares en la base vectorial, y construye un prompt que incluye estos fragmentos como contexto. El modelo de lenguaje entonces genera una respuesta fundamentada en los documentos del restaurante.

---

## La Inicialización de Datos

El módulo `seed.py` garantiza que un sistema recién desplegado tenga datos suficientes para ser operativo. El seeding es idempotente: verifica si los datos ya existen antes de crearlos, permitiendo ejecutarse múltiples veces sin duplicar registros.

El seed crea un tenant de demostración con dos sucursales, usuarios con cada uno de los cuatro roles (admin, manager, kitchen, waiter), categorías y subcategorías de ejemplo, productos con precios y relaciones de alérgenos, y mesas con códigos QR predefinidos.

---

## El Punto de Entrada: main.py

El archivo `main.py` es intencionalmente conciso: crea la aplicación FastAPI, configura rate limiting con slowapi, registra middlewares en el orden correcto, configura CORS, y monta los quince routers. Cada router se monta con su prefijo correspondiente, creando la estructura de URLs que los frontends consumen.

El orden de registro de middlewares merece atención especial. Los middlewares de seguridad se registran antes de CORS porque se ejecutan en orden inverso al registro. CORS debe ejecutarse primero para manejar preflight OPTIONS antes de que otros middlewares puedan interferir.

Para desarrollo local, el archivo incluye un bloque `if __name__ == "__main__"` que lanza uvicorn con hot reload, permitiendo iteración rápida sin necesidad de comandos externos.

---

## Patrones Arquitecturales Implementados

A lo largo del código, varios patrones de diseño emergen consistentemente:

**Repository Pattern** abstrae el acceso a datos detrás de interfaces type-safe, facilitando testing y previendo vendor lock-in con SQLAlchemy.

**Strategy Pattern** en el sistema de permisos permite agregar nuevos roles sin modificar código existente, solo añadiendo nuevas estrategias.

**Template Method** en los servicios base define el esqueleto de las operaciones CRUD mientras permite que subclases personalicen pasos específicos.

**Observer Pattern** en el sistema de eventos desacopla los servicios de dominio del mecanismo de notificación, permitiendo agregar nuevos suscriptores sin modificar los publicadores.

**Circuit Breaker** protege al sistema de fallos cascada cuando servicios externos como Mercado Pago experimentan problemas.

**Soft Delete** preserva integridad referencial y permite auditoría forense sin perder datos.

---

## Métricas del Sistema

El módulo rest_api comprende aproximadamente cien archivos Python organizados en una estructura que refleja la arquitectura Clean. Los modelos definen cincuenta y dos entidades ORM en dieciocho módulos de dominio. Los routers exponen quince dominios funcionales con aproximadamente veinte sub-routers. Los servicios de dominio suman diez implementaciones que encapsulan la lógica de negocio principal.

Esta estructura ha demostrado ser mantenible a través de múltiples ciclos de desarrollo, con más de novecientos ochenta defectos identificados y corregidos durante veintitrés auditorías de calidad, resultando en un sistema robusto y battle-tested.

---

## Conclusión

El módulo rest_api del sistema Integrador representa una implementación madura de arquitectura Clean en el ecosistema Python/FastAPI. Su diseño prioriza la separación de responsabilidades, la seguridad en profundidad, y la resiliencia ante fallos. Los patrones utilizados —Repository, Strategy, Template Method, Observer, Circuit Breaker— no son aplicaciones académicas sino soluciones pragmáticas a problemas reales de un sistema de gestión de restaurantes en producción.

La evolución desde CRUDFactory hacia Domain Services, la implementación de soft delete con auditoría completa, y la integración de sistemas externos con circuit breakers, demuestran un enfoque maduro hacia el desarrollo de software empresarial. El resultado es una API que no solo cumple con sus requisitos funcionales, sino que lo hace de manera segura, mantenible y escalable.
