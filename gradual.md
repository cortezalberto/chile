# Plan de Migración Gradual: De Maquetas a un Backend Real

Este documento presenta una planificación detallada para transformar las aplicaciones actuales del proyecto Integrador, que hoy funcionan con datos simulados almacenados localmente en el navegador, hacia una arquitectura de producción completa con backend, base de datos, autenticación real y comunicación en tiempo real.

---

## Introducción: Entendiendo el Punto de Partida

### El Estado Actual del Proyecto

El proyecto Integrador cuenta actualmente con dos aplicaciones web progresivas que fueron desarrolladas para demostrar funcionalidad y validar la experiencia de usuario, pero que operan de manera completamente aislada sin un servidor real detrás.

La primera aplicación es **pwaMenu**, una PWA orientada al comensal que permite unirse a una mesa escaneando un código QR, navegar por el menú del restaurante, agregar productos a un carrito compartido con otros comensales de la misma mesa, enviar pedidos organizados en "rondas", y eventualmente solicitar la cuenta y simular un pago. Toda esta funcionalidad existe gracias a un único store de Zustand llamado `tableStore`, que persiste su estado en el localStorage del navegador. Esto significa que los datos no se comparten realmente entre dispositivos: si dos personas escanean el mismo QR en sus teléfonos, cada una ve su propia versión del carrito. La sincronización entre pestañas del mismo navegador existe (mediante eventos de storage), pero no hay comunicación real entre dispositivos diferentes.

La segunda aplicación es **Dashboard**, un panel de administración completo que permite gestionar todos los aspectos de un restaurante multi-sucursal: el restaurante en sí, sus sucursales, categorías de menú, subcategorías, productos con precios diferenciados por sucursal, alérgenos, insignias, sellos de calidad, promociones temporales, mesas con un flujo de estados detallado, personal y roles. Esta aplicación cuenta con 15 stores de Zustand independientes, cada uno manejando su dominio específico, y todos persisten en localStorage. El Dashboard implementa operaciones CRUD completas con eliminación en cascada (por ejemplo, borrar una sucursal elimina automáticamente todas sus categorías, productos y mesas asociadas), pero todo ocurre localmente.

El tercer componente, el **backend**, simplemente no existe todavía. Los datos que ven los usuarios son información de ejemplo codificada directamente en el código fuente, diseñada para demostrar cómo se vería el sistema funcionando.

### El Objetivo: Un MVP Funcional en Producción

La arquitectura propuesta en el documento `proponer.txt` define un sistema completo de producción que incluye varios componentes trabajando en conjunto.

El corazón del sistema será un **backend en FastAPI** dividido en dos procesos separados: una API REST que corre en el puerto 8000 y maneja todas las operaciones de lectura y escritura de datos, y un Gateway de WebSocket en el puerto 8001 que se encarga exclusivamente de las comunicaciones en tiempo real. Esta separación no es caprichosa: permite escalar cada componente de manera independiente según la demanda, aislar fallos (si el WebSocket tiene problemas, la API REST sigue funcionando para procesar pagos), y simplifica enormemente el monitoreo y debugging.

Para almacenamiento, se utilizará **PostgreSQL con la extensión pgvector**, que permite guardar tanto datos relacionales tradicionales (mesas, pedidos, usuarios) como vectores numéricos necesarios para el sistema de búsqueda semántica del chatbot. Usar una sola base de datos para ambos propósitos simplifica la infraestructura y reduce costos operativos.

**Redis** actuará como intermediario para la comunicación en tiempo real mediante su sistema de publicación/suscripción. Cuando un comensal envía un pedido, la API REST lo guarda en PostgreSQL y luego publica un evento en Redis. El Gateway de WebSocket, que está suscrito a los canales relevantes, recibe ese evento y lo reenvía a todos los mozos y cocineros conectados que necesiten saberlo. Redis también puede usarse como caché para datos frecuentemente consultados como el menú de cada sucursal.

**Ollama** proporcionará las capacidades de inteligencia artificial para el chatbot de la carta, ejecutando modelos de lenguaje localmente sin depender de servicios externos de pago. Se usará el modelo `nomic-embed-text` para convertir texto en vectores numéricos (embeddings) y `qwen2.5:7b` para generar las respuestas conversacionales.

Finalmente, **Nginx** funcionará como punto de entrada único al sistema, terminando las conexiones HTTPS, dirigiendo el tráfico a los servicios correctos según la URL, comprimiendo respuestas, cacheando archivos estáticos, y aplicando límites de tasa para prevenir abusos.

El sistema implementará **multi-tenancy real**, lo que significa que la misma infraestructura podrá servir a múltiples restaurantes completamente aislados entre sí. Cada restaurante será un "tenant" con su propio identificador, y cada sucursal tendrá el suyo. Todas las consultas a la base de datos incluirán estos identificadores como filtros obligatorios, garantizando que nunca se mezclen datos entre restaurantes o sucursales diferentes.

La **autenticación** funcionará de dos maneras distintas según el tipo de usuario. El personal del restaurante (mozos, cocineros, gerentes) se autenticará con email y contraseña, recibiendo un token JWT que contiene su identidad, el restaurante al que pertenece, las sucursales donde puede operar, y sus roles. Los comensales, en cambio, no necesitarán crear cuentas ni recordar contraseñas: al escanear el código QR de una mesa recibirán un token especial firmado criptográficamente que les permite operar únicamente en esa mesa específica durante esa sesión.

---

## Análisis Detallado de las Brechas

Antes de planificar la migración, es fundamental entender exactamente qué diferencias existen entre el estado actual y el objetivo. Estas diferencias, o "brechas", determinan el trabajo necesario.

### Brechas en los Modelos de Datos

La primera brecha significativa está en los **identificadores**. Las aplicaciones actuales generan IDs usando `crypto.randomUUID()`, que produce cadenas de texto como `"a1b2c3d4-e5f6-7890-abcd-ef1234567890"`. El backend propuesto usa enteros grandes (`BigInteger`) como `1`, `2`, `3`. Esto requiere que el frontend pueda trabajar con ambos formatos durante la transición, y eventualmente adaptar completamente los tipos TypeScript.

La segunda brecha es la ausencia del concepto de **tenant** (inquilino/restaurante). Actualmente, las aplicaciones asumen que existe un único restaurante. El backend requiere que absolutamente toda entidad tenga un `tenant_id` que identifique a qué restaurante pertenece. Esto debe agregarse a todos los tipos y considerarse en todas las operaciones.

La tercera brecha está en las **sesiones de mesa**. El pwaMenu actual maneja sesiones localmente en el navegador de cada usuario. El backend centraliza las sesiones en la base de datos, permitiendo que múltiples dispositivos vean y modifiquen la misma sesión real. La estructura es similar pero no idéntica: hay campos nuevos como `assigned_waiter_id` para saber qué mozo atiende la mesa.

La cuarta brecha involucra las **rondas de pedido**. Actualmente, pwaMenu tiene un tipo `OrderRecord` que contiene una lista de items directamente. El backend separa esto en dos entidades: `Round` (la ronda en sí, con su número y estado) y `RoundItem` (cada producto pedido, con cantidad, precio al momento del pedido, y notas). Esta separación permite consultas más eficientes y mejor trazabilidad.

La quinta brecha son los **estados de mesa**. El Dashboard actual maneja cinco estados en español (`libre`, `ocupada`, `solicito_pedido`, `pedido_cumplido`, `cuenta_solicitada`), mientras que el backend propone cuatro estados en inglés (`FREE`, `ACTIVE`, `PAYING`, `OUT_OF_SERVICE`). Será necesario crear un mapeo entre ambos sistemas y decidir cómo manejar los estados que no tienen equivalente directo.

La sexta brecha es el manejo de **precios**. Aunque ambos sistemas soportan precios por sucursal, el backend es explícito sobre usar centavos (`price_cents`) para evitar problemas de precisión con decimales. Un producto de $125.50 se almacena como `12550`. El frontend deberá convertir entre la representación interna y la visualización al usuario.

Finalmente, hay **entidades completamente nuevas** que no existen en el frontend actual: `Check` (la cuenta de una mesa, con total y monto pagado), `Payment` (cada pago individual, ya sea efectivo o Mercado Pago), y `ServiceCall` (cuando un comensal llama al mozo o pide ayuda). Estas entidades deberán agregarse a los tipos TypeScript y crear la lógica de UI correspondiente.

### Brechas en Autenticación y Autorización

Actualmente, ninguna de las dos aplicaciones tiene sistema de autenticación. Cualquier persona puede abrir el Dashboard y modificar datos, o unirse a cualquier mesa en pwaMenu. El backend requiere autenticación completa.

Para el **personal**, esto implica crear un flujo de login con email/contraseña, almacenar el token JWT recibido, enviarlo en cada petición al backend, y manejar la expiración y renovación del token. También requiere implementar protección de rutas: un usuario no autenticado no debería poder acceder al Dashboard, y un mozo no debería poder acceder a funciones de gerente.

Para los **comensales**, el sistema es diferente. Al escanear un QR o ingresar un número de mesa, el frontend solicitará un token de mesa al backend. Este token, firmado con HMAC, contiene el ID del restaurante, sucursal, mesa, y sesión, más una fecha de expiración. El frontend debe almacenar este token y enviarlo en cada operación relacionada con esa mesa.

El backend implementa **RBAC (Role-Based Access Control) con contexto de sucursal**. Esto significa que los permisos no son solo "es mozo" sino "es mozo en la sucursal Centro". Un mozo autorizado en una sucursal no puede ver ni modificar datos de otra. Los frontends deberán respetar estas restricciones tanto en las llamadas al API como en la interfaz (ocultando opciones que el usuario no puede usar).

### Brechas en Comunicación

La brecha más significativa es la ausencia total de **comunicación con servidor**. Actualmente todo es local. La migración requiere:

Primero, crear una **capa de servicios API** en cada frontend que encapsule todas las llamadas HTTP al backend. Esta capa debe manejar la construcción de URLs, el envío de headers de autenticación, la serialización de datos, el manejo de errores HTTP, y la deserialización de respuestas.

Segundo, implementar **conexiones WebSocket** para las interfaces que requieren actualizaciones en tiempo real. El mozo necesita saber inmediatamente cuando llega un nuevo pedido. La cocina necesita ver las rondas entrantes sin refrescar la página. Esto requiere establecer la conexión al iniciar la aplicación, manejar reconexiones automáticas si se pierde la conexión, y procesar los eventos recibidos para actualizar el estado local.

Tercero, adaptar los **stores de Zustand** para que, en lugar de modificar directamente el estado local, llamen al API y actualicen el estado local solo cuando el servidor confirme la operación. Esto es un cambio fundamental en la arquitectura de las aplicaciones.

### Brechas Funcionales

Hay funcionalidades que existen parcialmente o simuladas que deben conectarse al backend real:

La **gestión de mesas** existe en ambos frontends pero de formas diferentes. Dashboard permite CRUD completo de mesas. pwaMenu permite unirse a una mesa y ver su estado. El backend unifica esto: las mesas se crean en Dashboard, y pwaMenu las consume creando sesiones cuando un comensal se une.

Las **rondas de pedido** se crean en pwaMenu pero actualmente solo se almacenan localmente. Deben enviarse al backend, que las persiste, asigna IDs reales, y notifica a mozos y cocina.

El **flujo de cocina** no existe en ningún frontend actualmente. El backend define estados de ronda (`SUBMITTED`, `IN_KITCHEN`, `READY`, `SERVED`) y endpoints para cambiarlos. Debe crearse una interfaz para que la cocina vea pedidos pendientes y marque cuando están listos.

El **flujo de mozo** tampoco existe. El backend define un tablero de mesas con indicadores de estado, notificaciones de nuevos pedidos, llamados de mesa, y solicitudes de cuenta. Debe crearse una nueva PWA o adaptar el Dashboard.

El **sistema de pagos** está simulado en pwaMenu. Debe conectarse a los endpoints reales de billing que crean checks, procesan pagos en efectivo, generan preferencias de Mercado Pago, y liberan mesas solo cuando están completamente pagadas.

El **chatbot RAG** tiene una interfaz básica en pwaMenu pero genera respuestas simuladas. Debe conectarse al endpoint real que consulta la base de conocimiento vectorial y genera respuestas basadas en evidencia del menú real.

---

## Plan de Migración Organizado en Fases

La migración se organiza en ocho fases que pueden ejecutarse mayormente en secuencia, aunque algunas pueden paralelizarse. Cada fase tiene un objetivo claro, entregables específicos, y criterios de validación.

### Fase 0: Preparación de la Infraestructura

Esta fase sienta las bases técnicas sobre las que se construirá todo lo demás. Sin una infraestructura funcionando correctamente, no tiene sentido avanzar con el código.

El primer paso es crear el directorio `backend/` en la raíz del proyecto y configurar **Docker Compose** para orquestar todos los servicios necesarios. El archivo `docker-compose.yml` definirá tres servicios: una base de datos PostgreSQL con la extensión pgvector preinstalada (usando la imagen `pgvector/pgvector:pg16`), un servidor Redis para pub/sub y caché, y opcionalmente Ollama para las capacidades de IA. Cada servicio tendrá sus puertos expuestos y volúmenes para persistir datos entre reinicios.

El segundo paso es crear el archivo `.env.example` que documenta todas las variables de entorno necesarias: la URL de conexión a PostgreSQL, la URL de Redis, el secreto para firmar tokens JWT, el emisor y audiencia de los tokens, y las URLs de Ollama con los nombres de los modelos a usar. Este archivo sirve como plantilla; cada desarrollador creará su propio `.env` basándose en él.

El tercer paso es crear `requirements.txt` con todas las dependencias Python: FastAPI como framework web, Uvicorn como servidor ASGI, SQLAlchemy para el ORM, psycopg3 como driver de PostgreSQL, redis para la conexión a Redis, PyJWT para tokens, pgvector para embeddings, Pydantic para validación de datos, y httpx para llamadas HTTP salientes.

El cuarto paso es establecer la **estructura de directorios** del backend. Se crearán tres subdirectorios principales: `shared/` contendrá código compartido entre servicios (configuración, autenticación, esquemas de eventos), `rest_api/` contendrá la API REST con sus modelos, rutas y lógica de negocio, y `ws_gateway/` contendrá el gateway de WebSocket.

Dentro de `shared/`, el archivo `settings.py` leerá todas las variables de entorno y las expondrá como constantes tipadas. El archivo `auth.py` contendrá funciones para firmar y verificar tokens JWT, extraer tokens de headers HTTP, y decoradores para requerir roles específicos. El archivo `events.py` definirá la estructura de los eventos que se publican en Redis y funciones helper para publicarlos. El archivo `schemas.py` contendrá modelos Pydantic compartidos.

Dentro de `rest_api/`, el archivo `main.py` configurará la aplicación FastAPI, registrará todos los routers, y ejecutará la creación de tablas y seed de datos al iniciar. El archivo `db.py` configurará la conexión a PostgreSQL usando SQLAlchemy. El archivo `models.py` definirá todos los modelos ORM. El archivo `seed.py` contendrá datos iniciales para desarrollo.

Dentro de `ws_gateway/`, el archivo `main.py` configurará la aplicación FastAPI dedicada a WebSocket. El archivo `connection_manager.py` gestionará las conexiones activas organizadas por usuario y sucursal. El archivo `redis_subscriber.py` se suscribirá a canales Redis y despachará eventos a las conexiones correspondientes.

La fase se considera completa cuando ejecutar `docker compose up -d` levanta todos los servicios, PostgreSQL acepta conexiones en el puerto 5432, Redis responde en el puerto 6379, y la estructura de directorios está creada con los archivos base.

### Fase 1: Modelos de Datos y Autenticación Básica

Con la infraestructura lista, esta fase implementa los cimientos de datos y seguridad.

El trabajo principal es crear los **modelos SQLAlchemy** en `rest_api/models.py`. Cada modelo representa una tabla en la base de datos con sus columnas, tipos, y relaciones.

El modelo `Tenant` representa un restaurante o marca. Tiene un ID numérico, un nombre legible, y un slug único para URLs amigables. Todo lo demás en el sistema pertenece a un tenant.

El modelo `Branch` representa una sucursal física. Pertenece a un tenant, tiene nombre, slug, zona horaria, y puede tener información adicional como dirección y horarios.

El modelo `User` representa una persona que trabaja en el restaurante. Tiene email único, contraseña (en el MVP almacenada en texto plano, en producción hasheada), y un flag de activo/inactivo. Pertenece a un tenant.

El modelo `UserBranchRole` conecta usuarios con sucursales y roles. Un usuario puede ser mozo en una sucursal y gerente en otra. Cada registro indica: este usuario, en este tenant, en esta sucursal, tiene este rol. Los roles son strings predefinidos: `WAITER`, `KITCHEN`, `MANAGER`, `ADMIN`.

El modelo `Product` representa un producto del menú a nivel global del tenant. Tiene nombre, descripción, y otros atributos. No tiene precio porque el precio puede variar por sucursal.

El modelo `BranchProduct` conecta productos con sucursales, indicando si el producto está disponible en esa sucursal y a qué precio (en centavos). Un producto puede no existir en alguna sucursal simplemente no teniendo un registro `BranchProduct` para esa combinación.

El modelo `Table` representa una mesa física. Pertenece a una sucursal, tiene un código identificador (como "M-07" o "Terraza-3"), y un estado actual (`FREE`, `ACTIVE`, `PAYING`, `OUT_OF_SERVICE`).

El modelo `TableSession` representa una sesión activa en una mesa: un grupo de comensales que se sentó, va a pedir, y eventualmente pagará e irá. Tiene referencia a la mesa, estado (`OPEN`, `PAYING`, `CLOSED`), opcionalmente el mozo asignado, y timestamps de apertura y cierre.

El modelo `Round` representa una ronda de pedido dentro de una sesión. Una mesa puede hacer múltiples rondas: piden entradas, luego principales, luego postres. Cada ronda tiene su número secuencial y estado (`DRAFT`, `SUBMITTED`, `IN_KITCHEN`, `READY`, `SERVED`, `CANCELED`).

El modelo `RoundItem` representa cada línea dentro de una ronda: producto, cantidad, precio al momento del pedido (importante porque los precios pueden cambiar), y notas especiales como "sin cebolla".

El modelo `ServiceCall` representa cuando un comensal presiona el botón de llamar al mozo o pedir ayuda. Tiene tipo (`WAITER_CALL`, `PAYMENT_HELP`, `OTHER`), estado (`OPEN`, `ACKED`, `CLOSED`), y quién lo atendió.

El modelo `Check` representa la cuenta de una sesión. Tiene el total calculado, cuánto se ha pagado, y estado (`OPEN`, `REQUESTED`, `IN_PAYMENT`, `PAID`, `FAILED`).

El modelo `Payment` representa cada pago individual hacia un check. Puede haber múltiples pagos si la mesa paga en partes. Tiene proveedor (`CASH`, `MERCADO_PAGO`), estado (`PENDING`, `APPROVED`, `REJECTED`), y monto.

Todos estos modelos incluyen `tenant_id` y, donde corresponde, `branch_id`. Estas columnas son obligatorias y tienen foreign keys. Toda consulta en el sistema debe filtrar por estos campos.

Una vez definidos los modelos, se configura `Base.metadata.create_all(engine)` en el startup de la aplicación para crear las tablas automáticamente.

El siguiente paso es implementar la **autenticación JWT** en `shared/auth.py`. La función `sign_jwt` toma un diccionario de claims (datos a incluir en el token) y un tiempo de vida, y retorna un token firmado. La función `verify_jwt` toma un token, verifica la firma y expiración, y retorna los claims. La función `current_user_context` es un "Depends" de FastAPI que extrae el token del header Authorization, lo verifica, y retorna el contexto del usuario para usar en el endpoint. Las funciones `require_roles` y `require_branch` verifican que el usuario tenga los permisos necesarios y lanzan excepciones HTTP si no.

El endpoint `POST /api/auth/login` recibe email y contraseña, busca el usuario en la base de datos, verifica la contraseña, carga los roles del usuario desde `UserBranchRole`, y retorna un token JWT que contiene el ID del usuario, el tenant, las sucursales donde tiene acceso, y sus roles.

Finalmente, se crea el **script de seed** en `rest_api/seed.py`. Este script verifica si la base de datos está vacía y, si lo está, inserta datos de demostración: un tenant llamado "Demo Restaurant", una sucursal "Centro", tres usuarios (mozo, cocina, gerente) con sus roles asignados, cinco mesas, y algunos productos con sus precios por sucursal. El script es idempotente: si ya hay datos, no hace nada.

La fase se considera completa cuando las tablas existen en PostgreSQL (verificable con `\dt` en psql), el endpoint de login retorna un token JWT válido, el token contiene la información correcta del usuario, y los datos de seed están presentes.

### Fase 2: API REST para Operaciones Core

Esta fase expone los endpoints necesarios para las operaciones básicas del negocio: consultar el menú, gestionar mesas, y enviar pedidos.

El **router de catálogo** (`routers/catalog.py`) expone el menú al público. El endpoint `GET /api/public/menu/{branch_slug}` no requiere autenticación. Recibe el slug de una sucursal, busca la sucursal, y retorna todas las categorías, subcategorías, y productos disponibles en esa sucursal con sus precios. Este endpoint es el que usará pwaMenu para mostrar el menú. El endpoint `GET /api/public/menu/{branch_slug}/products/{product_id}` retorna el detalle de un producto específico incluyendo alérgenos.

El **router de mesas** (`routers/tables.py`) maneja las operaciones de mesa. El endpoint `GET /api/waiter/tables` requiere autenticación y roles de mozo o superior. Retorna todas las mesas de la sucursal del usuario con información resumida: estado, ID de sesión activa si la hay, cantidad de rondas pendientes, cantidad de llamados sin atender, y estado de la cuenta si existe. El endpoint `POST /api/tables/{table_id}/session` crea una nueva sesión en una mesa libre. Si la mesa ya tiene sesión activa, la retorna. Este endpoint genera y retorna un token de mesa que los comensales usarán para autenticarse.

El **router de comensal** (`routers/diner.py`) maneja las operaciones que realizan los comensales. El endpoint `POST /api/diner/rounds/submit` recibe el ID de la mesa y una lista de items a pedir. Valida el token de mesa, busca o crea la sesión, crea un nuevo registro Round con el siguiente número secuencial, crea los RoundItems correspondientes consultando los precios actuales de BranchProduct, y persiste todo en la base de datos. Después de persistir, publica un evento `ROUND_SUBMITTED` en Redis para notificar a mozos y cocina. Retorna el ID de la sesión, el ID de la ronda, y el número de ronda. El endpoint `GET /api/diner/session/{session_id}` retorna el estado actual de una sesión: comensales, rondas con sus items y estados, y carrito borrador si existe. El endpoint `POST /api/diner/service-call` crea un llamado de servicio, lo persiste, y publica el evento correspondiente.

Esta fase también requiere **cambios en pwaMenu**. El archivo `src/services/api.ts` debe actualizarse para que las funciones existentes llamen a los endpoints reales en lugar de retornar datos mock. La función `api.getMenu(branchSlug)` debe hacer `GET /api/public/menu/{slug}` y transformar la respuesta al formato que espera el frontend. El `tableStore` debe modificarse: `joinTable()` debe llamar a `POST /api/tables/{id}/session` y almacenar el token de mesa recibido, `submitOrder()` debe llamar a `POST /api/diner/rounds/submit` y actualizar el estado local con la respuesta del servidor. Todas las llamadas del comensal deben incluir el header `X-Table-Token` con el token de mesa.

La fase se considera completa cuando pwaMenu puede mostrar el menú obtenido del backend real, puede enviar un pedido y recibir confirmación con ID de ronda, y los datos persisten en PostgreSQL (verificable consultando la tabla `round`).

### Fase 3: Gateway de WebSocket para Tiempo Real

Esta fase implementa la comunicación en tiempo real necesaria para que mozos y cocina reciban notificaciones instantáneas.

El **WebSocket Gateway** es una aplicación FastAPI separada que corre en el puerto 8001. Su única responsabilidad es mantener conexiones WebSocket abiertas con clientes y reenviarles eventos relevantes.

El archivo `connection_manager.py` implementa una clase que mantiene registro de todas las conexiones activas. Internamente usa dos diccionarios: uno indexado por ID de usuario y otro por ID de sucursal. Cuando un cliente se conecta, se registra en ambos índices según corresponda. Cuando se desconecta, se elimina de ambos. Tiene métodos para enviar un mensaje a todas las conexiones de un usuario específico o a todas las conexiones de una sucursal.

El archivo `redis_subscriber.py` implementa la suscripción a canales Redis. Al iniciar, se suscribe a canales con patrones como `branch:*:waiters` y `branch:*:kitchen`. Cuando llega un mensaje a cualquiera de estos canales, lo parsea como JSON y lo pasa a una función callback.

El archivo `main.py` configura la aplicación. Al iniciar, lanza una tarea asíncrona que ejecuta el subscriber de Redis. El callback de mensajes extrae el `branch_id` del evento y usa el connection manager para reenviarlo a todas las conexiones de esa sucursal.

Los endpoints WebSocket son `GET /ws/waiter?token={jwt}` y `GET /ws/kitchen?token={jwt}`. Ambos verifican el token JWT en el query parameter, extraen el ID de usuario y las sucursales permitidas, registran la conexión en el manager, y mantienen la conexión abierta en un loop infinito esperando mensajes del cliente (que pueden ignorarse o usarse para heartbeat). Cuando la conexión se cierra (el cliente se va o hay error de red), se elimina del manager.

Los **canales Redis** siguen una convención clara. `branch:{id}:waiters` recibe eventos relevantes para mozos de esa sucursal: nuevas rondas, rondas listas, llamados de mesa, solicitudes de cuenta. `branch:{id}:kitchen` recibe eventos relevantes para cocina: nuevas rondas. `user:{id}` puede usarse para eventos directos a un usuario específico.

El **esquema de eventos** es uniforme para todos los tipos. Cada evento es un objeto JSON con: `type` (el tipo de evento como `ROUND_SUBMITTED`), `tenant_id` y `branch_id` (para filtrado y auditoría), `table_id` y `session_id` (para contexto), `entity` (un objeto con IDs relevantes como `round_id`), `actor` (quién causó el evento, con `user_id` y `role`), `ts` (timestamp ISO 8601), y `v` (versión del esquema para compatibilidad futura).

Los tipos de eventos que el sistema maneja son: `ROUND_SUBMITTED` (comensal envió pedido), `ROUND_IN_KITCHEN` (cocina tomó el pedido), `ROUND_READY` (cocina terminó el pedido), `ROUND_SERVED` (mozo entregó el pedido), `SERVICE_CALL_CREATED` (comensal llamó al mozo), `SERVICE_CALL_ACKED` (mozo atendió el llamado), `CHECK_REQUESTED` (comensal pidió la cuenta), `PAYMENT_APPROVED` (se confirmó un pago), `CHECK_PAID` (cuenta completamente pagada), y `TABLE_CLEARED` (mesa liberada).

La **integración** entre REST y WebSocket ocurre en los endpoints REST. Cada endpoint que modifica estado sigue el patrón: primero persistir en la base de datos, luego publicar evento en Redis. El WebSocket Gateway se encarga del resto.

La fase se considera completa cuando se puede conectar al WebSocket usando `wscat -c "ws://localhost:8001/ws/waiter?token=..."`, cuando un pedido enviado por REST causa que llegue un evento `ROUND_SUBMITTED` a las conexiones WebSocket abiertas, y cuando múltiples conexiones simultáneas reciben el mismo evento.

### Fase 4: Flujo de Cocina

Esta fase implementa la funcionalidad necesaria para que la cocina vea pedidos y actualice su estado.

El **router de cocina** (`routers/kitchen.py`) expone dos endpoints. El endpoint `GET /api/kitchen/rounds` requiere autenticación con rol de cocina o superior. Retorna todas las rondas de la sucursal del usuario que están en estado `SUBMITTED` o `IN_KITCHEN`, ordenadas por antigüedad. Para cada ronda incluye los items con nombre de producto, cantidad, y notas. El endpoint `POST /api/kitchen/rounds/{round_id}/status` permite cambiar el estado de una ronda. Acepta los estados `IN_KITCHEN` (la cocina está preparando), `READY` (está listo para servir), o `SERVED` (ya se entregó, aunque esto normalmente lo marca el mozo). Después de actualizar el estado, publica el evento correspondiente (`ROUND_IN_KITCHEN`, `ROUND_READY`, o `ROUND_SERVED`) para que los mozos se enteren.

Para la **interfaz de cocina**, hay dos opciones según los recursos disponibles. La opción más simple es agregar una nueva página en el Dashboard existente, accesible en `/kitchen`, que muestre las rondas pendientes y permita cambiar estados. Esto aprovecha la infraestructura existente del Dashboard. La opción más robusta es crear una nueva PWA dedicada (`pwaKitchen`) optimizada para el ambiente de cocina: pantalla grande de tableta, gestos simples, interfaz de alto contraste visible a distancia. Para el MVP, la primera opción es suficiente.

La fase se considera completa cuando la cocina puede ver una lista de pedidos pendientes obtenidos del backend, puede marcar un pedido como "en preparación" o "listo", y los mozos conectados por WebSocket reciben las notificaciones correspondientes.

### Fase 5: Sistema de Facturación y Pagos

Esta fase implementa el flujo completo desde que el comensal pide la cuenta hasta que la mesa queda liberada.

El **router de billing** (`routers/billing.py`) es el más extenso porque maneja un flujo con múltiples pasos.

El endpoint `POST /api/billing/check/request` es llamado cuando el comensal presiona "Pedir cuenta" en pwaMenu. Recibe el ID de la mesa, busca la sesión activa, calcula el total sumando todos los items de todas las rondas (precio unitario × cantidad), crea un registro `Check` con ese total y monto pagado en cero, cambia el estado de la mesa a `PAYING`, y publica el evento `CHECK_REQUESTED` para que el mozo sepa que debe acercarse.

El endpoint `POST /api/billing/cash/pay` es usado por el mozo cuando el cliente paga en efectivo. Recibe el ID del check y el monto pagado. Crea un registro `Payment` con proveedor `CASH` y estado `APPROVED`. Suma el monto al campo `paid_cents` del check. Si el total pagado iguala o supera el total de la cuenta, cambia el estado del check a `PAID` y publica el evento `CHECK_PAID`.

El endpoint `POST /api/billing/mercadopago/preference` crea una preferencia de pago en Mercado Pago. Recibe el ID del check, consulta el total pendiente, llama al API de Mercado Pago para crear una preferencia con ese monto, y retorna la URL de checkout (`init_point`). El comensal será redirigido a esta URL para completar el pago.

El endpoint `POST /api/billing/mercadopago/webhook` recibe notificaciones de Mercado Pago cuando un pago cambia de estado. Verifica la autenticidad de la notificación, busca el payment correspondiente, actualiza su estado según lo que reporta Mercado Pago, y si fue aprobado, actualiza el check y publica los eventos necesarios.

El endpoint `POST /api/billing/tables/clear` es la operación final que libera una mesa. Solo puede ejecutarse si el check está completamente pagado. Cambia el estado de la sesión a `CLOSED`, el estado de la mesa a `FREE`, y publica `TABLE_CLEARED`. La mesa está lista para el siguiente grupo de comensales.

Los **cambios en pwaMenu** involucran conectar el flujo existente de cierre de mesa a estos endpoints reales. La función `closeTable()` en el store debe llamar a `POST /api/billing/check/request` en lugar de simular. El componente `CloseTable` debe mostrar el total real recibido del servidor. La integración con Mercado Pago debe usar la URL de preferencia real. Se debe agregar al estado el ID del check activo para poder consultarlo y actualizarlo.

La fase se considera completa cuando el flujo completo funciona end-to-end: comensal pide cuenta, mozo ve notificación, mozo confirma pago efectivo, mesa se libera automáticamente cuando está pagada, y los datos persisten correctamente en la base de datos.

### Fase 6: Conexión del Dashboard al Backend

Esta fase es la más extensa porque implica modificar significativamente una aplicación existente con mucha funcionalidad.

El primer paso es crear una **capa de servicios API** en `Dashboard/src/services/api.ts`. Este archivo exportará un objeto con métodos para todas las operaciones que el Dashboard necesita realizar: login, logout, CRUD de sucursales, CRUD de categorías, CRUD de productos, etc. Cada método será una función async que hace el fetch correspondiente, maneja errores, y retorna los datos tipados.

El segundo paso es crear un **store de autenticación** (`authStore.ts`) que no existía antes. Este store manejará el estado del usuario logueado (si hay uno), el token JWT, y un flag de carga. Expondrá acciones para login y logout. El login llamará al API, almacenará el token, y decodificará los datos del usuario. El logout limpiará el estado. El token se persistirá en localStorage para sobrevivir recargas de página.

El tercer paso es crear una **página de login** (`LoginPage.tsx`) que se muestre cuando no hay usuario autenticado. Un formulario simple con email y contraseña que al submit llame a la acción de login del store. Si es exitoso, redirige al Dashboard. Si falla, muestra el error.

El cuarto paso es implementar **protección de rutas**. Un componente wrapper que verifique si hay usuario autenticado antes de renderizar las rutas protegidas. Si no hay usuario, redirige a login. Esto se integra en `App.tsx` envolviendo las rutas del Dashboard.

El quinto paso, y el más laborioso, es **migrar cada store** para que use el API en lugar de localStorage. La migración sigue un patrón repetitivo.

Tomemos `branchStore` como ejemplo. Actualmente tiene acciones como `addBranch` que reciben datos, generan un ID local, y actualizan el estado inmediatamente. La versión migrada de `addBranch` será una función async que primero llama a `api.createBranch(data)`, espera la respuesta del servidor que incluye el ID real asignado por la base de datos, y entonces actualiza el estado local con los datos confirmados. Si el API falla, el estado local no se modifica y se propaga el error para que la UI lo maneje.

Este patrón se repite para todas las operaciones CRUD de todos los stores: branches, categories, subcategories, products, allergens, badges, seals, promotions, tables, staff, roles. Cada store tendrá aproximadamente el mismo patrón de cambios.

Un aspecto importante es decidir qué hacer con la **persistencia local**. Una opción es eliminarla completamente: el estado se carga del servidor al iniciar y se descarta al cerrar. Esto es simple pero significa que la app no funciona offline. Otra opción es mantener localStorage como caché: al iniciar se muestra lo que hay en caché inmediatamente mientras se hace fetch al servidor, y cuando llega la respuesta del servidor se actualiza tanto el estado como el caché. Esto da mejor UX pero es más complejo. Para el MVP, la primera opción es recomendable.

El **orden de migración** sugerido prioriza las entidades más fundamentales primero. Empezar con autenticación (sin esto nada más funciona). Luego sucursales (muchas otras entidades dependen de tener sucursales). Luego categorías y subcategorías. Luego productos. Luego el resto en cualquier orden.

La fase se considera completa cuando un usuario puede loguearse en el Dashboard con credenciales válidas, las operaciones CRUD funcionan contra el backend (crear una sucursal y recargar la página muestra la sucursal persistida), y los datos ya no dependen de localStorage.

### Fase 7: Chatbot RAG

Esta fase implementa el chatbot inteligente de la carta que puede responder preguntas de los comensales basándose en la información real del menú.

El fundamento del RAG (Retrieval-Augmented Generation) es que el modelo de lenguaje no "sabe" nada sobre el menú del restaurante desde su entrenamiento. En cambio, antes de generar cada respuesta, el sistema busca información relevante en una base de conocimiento y la incluye en el prompt para que el modelo la use. Esto tiene dos ventajas enormes: las respuestas están basadas en información real y actual del restaurante, y se puede auditar exactamente qué información usó el modelo para cada respuesta.

El primer componente es la **base de conocimiento vectorial**. Se agrega un nuevo modelo `KnowledgeDocument` que almacena fragmentos de información: fichas técnicas de productos, descripciones del menú, guías de alérgenos, notas del chef. Cada documento tiene su texto original y un embedding (vector numérico de 1536 dimensiones) que captura el significado semántico del texto. Los embeddings se almacenan usando pgvector.

El segundo componente es el **endpoint de ingesta** `POST /api/admin/rag/ingest`. Este endpoint, accesible solo para administradores, recibe texto a ingresar en la base de conocimiento. El texto se divide en chunks de tamaño manejable (por ejemplo, párrafos o secciones), cada chunk se envía a Ollama con el modelo `nomic-embed-text` para obtener su embedding, y se guardan tanto el texto como el embedding en la base de datos. El endpoint acepta un `branch_id` opcional: si se especifica, ese conocimiento solo aplica a esa sucursal; si no, aplica a todo el tenant.

El tercer componente es el **endpoint de chat** `POST /api/chat`. Este endpoint acepta preguntas de comensales (autenticados con token de mesa) o administradores (autenticados con JWT). El flujo es:

1. Recibir la pregunta del usuario
2. Generar el embedding de la pregunta usando Ollama
3. Buscar en pgvector los chunks más similares semánticamente, filtrando por tenant y opcionalmente por branch
4. Construir un prompt que incluye la pregunta original más los chunks encontrados como contexto
5. Enviar el prompt a Ollama con el modelo `qwen2.5:7b` para generar la respuesta
6. Registrar en logs la pregunta, los chunks usados, sus scores de similitud, y la respuesta generada
7. Retornar la respuesta junto con referencias a las fuentes usadas

Un aspecto crítico es la **política anti-alucinación**. El prompt debe instruir al modelo explícitamente: "Responde SOLO basándote en la información proporcionada. Si la información no menciona alérgenos específicos, di que no puedes confirmar. Si no encuentras información relevante, di que no tienes esa información." Esto es especialmente importante para alérgenos donde una respuesta incorrecta puede tener consecuencias graves.

Los **cambios en pwaMenu** implican conectar el componente `AIChat` al endpoint real. El componente actual simula respuestas; debe modificarse para enviar la pregunta al backend y mostrar la respuesta recibida. También debe mostrar las fuentes/referencias cuando las haya, para que el usuario sepa de dónde viene la información. Se debe implementar rate limiting en el cliente (por ejemplo, deshabilitar el input por 2 segundos después de cada pregunta) para evitar abusos.

La fase se considera completa cuando se puede ingestar documentos en la base de conocimiento, el chat responde preguntas usando información de esos documentos, las respuestas incluyen referencias a las fuentes, y el sistema se abstiene de inventar información cuando no la tiene.

### Fase 8: PWA para Mozos

Esta fase crea una nueva aplicación dedicada para los mozos, optimizada para su flujo de trabajo específico.

La **arquitectura** de esta PWA será similar a pwaMenu: React, TypeScript, Zustand, Tailwind, y vite-plugin-pwa para capacidades offline. Correrá en un directorio separado `pwaWaiter/`.

El **flujo de login** es el punto de entrada. El mozo abre la aplicación, ingresa sus credenciales, el sistema verifica contra el backend y almacena el token JWT. El token incluye las sucursales donde el mozo tiene asignación.

La **pantalla principal** es un grid de mesas de su sucursal. Cada mesa se muestra como una card con: número/código de mesa, estado actual con color distintivo (verde para libre, rojo para ocupada, amarillo para pedido pendiente, morado para cuenta solicitada), indicadores de rondas pendientes y llamados sin atender, y tiempo desde el último evento importante.

La **conexión WebSocket** se establece inmediatamente después del login. La aplicación se suscribe a eventos de la sucursal del mozo. Cuando llega un evento, actualiza el estado local correspondiente: una nueva ronda hace que la mesa parpadee o muestre un badge, una ronda lista muestra un indicador diferente, un llamado de mesa es prioritario y puede mostrar notificación del sistema.

Las **acciones disponibles** al tocar una mesa dependen de su estado. Para mesas con pedidos listos: marcar como servido. Para mesas con cuenta solicitada: ver detalle de la cuenta, confirmar pago en efectivo, imprimir ticket. Para mesas pagadas: liberar mesa. Para cualquier mesa activa: ver detalle de sesión con todas las rondas y su estado.

Las **notificaciones push** pueden implementarse usando la API de Notifications del navegador. Cuando llega un evento importante y la aplicación está en segundo plano, mostrar una notificación del sistema operativo. Esto es especialmente útil para llamados de mesa urgentes.

La **pantalla de detalle de mesa** muestra toda la información de la sesión: lista de comensales (si el sistema los trackea), historial de rondas con sus items y estados, cuenta actual con pagos realizados, y botones de acción contextual.

La fase se considera completa cuando el mozo puede loguearse, ver sus mesas en tiempo real, recibir notificaciones de nuevos pedidos y llamados, y completar las acciones principales de su trabajo sin usar otras aplicaciones.

---

## Dependencias entre Fases y Paralelización

Las fases no son completamente secuenciales. Entender sus dependencias permite optimizar el cronograma.

La **Fase 0** (infraestructura) es prerequisito de todo lo demás. Sin Docker Compose funcionando y la estructura de backend creada, no se puede avanzar.

La **Fase 1** (modelos y auth) depende de la Fase 0. Es el siguiente paso obligatorio porque todo lo demás requiere modelos de datos y autenticación.

A partir de la Fase 1, hay tres líneas de trabajo que pueden avanzar en paralelo:

La **Fase 2** (API REST) puede comenzar inmediatamente después de la Fase 1. Se enfoca en endpoints REST sin WebSocket.

La **Fase 3** (WebSocket) también puede comenzar después de la Fase 1. Es independiente de los endpoints REST específicos; solo necesita que exista el sistema de eventos.

La **Fase 6** (Dashboard) puede comenzar después de la Fase 1 en lo que respecta a autenticación, pero para migrar stores específicos necesita que existan los endpoints correspondientes de la Fase 2.

La **Fase 4** (cocina) necesita la Fase 2 (endpoints de rondas) y la Fase 3 (para recibir notificaciones).

La **Fase 5** (billing) necesita la Fase 2 (endpoints de sesiones y rondas existentes) pero es mayormente independiente.

La **Fase 7** (RAG) puede desarrollarse mayormente en paralelo, ya que es un módulo relativamente aislado. Solo necesita la infraestructura base de la Fase 0 y 1.

La **Fase 8** (PWA mozo) necesita las Fases 2, 3 y 5 completas, porque el mozo usa endpoints REST, WebSocket, y funcionalidad de billing.

---

## Criterios de Validación Consolidados

Para cada fase se han definido criterios específicos de completitud. Aquí se consolidan para facilitar el seguimiento:

**Infraestructura**: Docker Compose levanta todos los servicios, PostgreSQL accesible en 5432, Redis en 6379, Ollama en 11434.

**Modelos y Auth**: Tablas creadas en PostgreSQL, login retorna JWT válido con claims correctos, seed data presente.

**API REST**: pwaMenu puede obtener menú del backend, puede enviar pedido y recibir confirmación con ID.

**WebSocket**: Conexión exitosa con wscat, eventos de REST llegan a conexiones WS, broadcast funciona.

**Cocina**: Puede ver pedidos pendientes, cambiar estados, mozos reciben notificaciones.

**Billing**: Flujo completo de cuenta funciona, pago efectivo actualiza check, mesa se libera solo si pagada.

**Dashboard**: Login funciona, CRUD opera contra backend, datos persisten entre recargas.

**RAG**: Ingesta funciona, chat usa documentos ingestados, respuestas incluyen sources.

**PWA Mozo**: Login funciona, grid actualiza en tiempo real, notificaciones WS llegan.

---

## Gestión de Riesgos

Todo proyecto tiene riesgos. Identificarlos temprano permite preparar mitigaciones.

El **cambio de formato de IDs** (de strings UUID a integers) tiene impacto alto porque afecta muchos archivos. La mitigación es crear una capa de adaptación en el cliente que convierta IDs según necesidad, y hacer el cambio gradualmente por entidad.

La **sincronización multi-pestaña** actual de pwaMenu depende de eventos de localStorage. Con backend real, la fuente de verdad cambia. La mitigación es mantener localStorage como caché optimista pero siempre confirmar con el servidor, y usar WebSocket para sincronización real entre dispositivos diferentes.

La **latencia de WebSocket** puede ser problemática en conexiones inestables. La mitigación es implementar heartbeat para detectar desconexiones rápidamente, reconexión automática con backoff exponencial, y mostrar indicador de estado de conexión al usuario.

Las **alucinaciones del RAG** son un riesgo de seguridad alimentaria. La mitigación es una política estricta de fallback: si la confianza de los resultados de búsqueda es baja, decir explícitamente "no tengo esa información" en lugar de inventar. También mantener logs de cada interacción para auditoría.

La **migración de datos existentes** tiene riesgo bajo porque actualmente solo hay datos mock de desarrollo. No hay datos de producción que preservar. Sin embargo, el sistema debe diseñarse pensando en que eventualmente habrá datos reales que no pueden perderse.

---

## Estimación de Esfuerzo

Las estimaciones son aproximadas y dependen de factores como experiencia del equipo, disponibilidad, y complejidad no anticipada.

La Fase 0 requiere aproximadamente una a dos semanas. Es mayormente configuración y setup, pero requiere atención al detalle para que todo funcione correctamente.

La Fase 1 requiere una a dos semanas. Los modelos son numerosos pero siguen patrones repetitivos. La autenticación JWT es relativamente estándar.

La Fase 2 requiere una a dos semanas. Los endpoints son directos pero la integración con pwaMenu puede revelar ajustes necesarios.

La Fase 3 requiere una a dos semanas. WebSocket es conceptualmente simple pero la integración con Redis y el manejo de conexiones tiene sutilezas.

La Fase 4 requiere aproximadamente una semana. Es el flujo más simple, con pocos endpoints y UI básica.

La Fase 5 requiere una a dos semanas. La integración con Mercado Pago agrega complejidad y requiere pruebas cuidadosas.

La Fase 6 requiere dos a tres semanas. Es la fase más extensa porque involucra modificar una aplicación existente con mucha funcionalidad.

La Fase 7 requiere dos a tres semanas. RAG tiene complejidad conceptual y requiere tuning para lograr respuestas de calidad.

La Fase 8 requiere dos a tres semanas. Es una aplicación nueva completa, aunque más simple que las existentes.

El total estimado es de doce a veinte semanas de trabajo, aproximadamente tres a cinco meses dependiendo de si hay trabajo paralelo y de la dedicación disponible.

---

## Pasos Inmediatos para Comenzar

Con este plan definido, los pasos concretos para arrancar son:

Primero, crear el directorio `backend/` y el archivo `docker-compose.yml` con los servicios PostgreSQL, Redis, y Ollama. Ejecutar `docker compose up -d` y verificar que todo levante.

Segundo, crear la estructura de directorios dentro de `backend/`: `shared/`, `rest_api/`, `ws_gateway/` con sus archivos iniciales.

Tercero, implementar los modelos SQLAlchemy y ejecutar la creación de tablas.

Cuarto, implementar el endpoint de login y probarlo con curl o Postman.

Quinto, implementar el primer endpoint público (catálogo) y modificar pwaMenu para consumirlo.

Cada uno de estos pasos es pequeño y verificable. Completar los cinco significa tener el ciclo básico funcionando: infraestructura, modelos, autenticación, un endpoint, y un cliente consumiéndolo. A partir de ahí, es cuestión de expandir siguiendo el plan.

---

*Este documento representa el análisis y planificación realizados en enero de 2026 como guía para la migración del proyecto Integrador de maquetas funcionales a un sistema de producción completo.*
