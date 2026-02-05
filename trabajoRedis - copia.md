# Arquitectura de Redis en Integrador

## Documento Técnico - Febrero 2026

---

## Introducción

Redis constituye el sistema nervioso central de comunicación en tiempo real de Integrador. Su implementación trasciende el uso convencional como almacén de datos en memoria para convertirse en la columna vertebral que habilita la sincronización instantánea entre todos los componentes del sistema. Sin esta infraestructura, la aplicación funcionaría como un sistema tradicional de solicitud-respuesta, obligando a cada cliente a refrescar manualmente su interfaz para visualizar actualizaciones. Con Redis, el ecosistema cobra vida: cuando un comensal realiza un pedido desde su dispositivo móvil, el mozo recibe instantáneamente una notificación, la cocina visualiza la orden en su pantalla, y el administrador observa en el Dashboard cómo la mesa cambia de estado. Este proceso se completa en milisegundos.

Este documento presenta un análisis exhaustivo de la arquitectura Redis implementada en Integrador, abarcando desde la gestión de conexiones hasta los patrones de resiliencia y seguridad que garantizan la operación continua del sistema.

---

## Capítulo 1: El Paradigma de Eventos en Tiempo Real

La arquitectura de Integrador resuelve un desafío fundamental en sistemas distribuidos: la propagación instantánea de cambios de estado a múltiples clientes heterogéneos. Consideremos un escenario típico en un restaurante con veinte mesas, cinco mozos, tres cocineros y un administrador. Sin un sistema de eventos, cuando un cliente en la mesa siete realiza un pedido, el flujo sería deficiente: el pedido se almacena en PostgreSQL, pero el mozo debe refrescar constantemente su aplicación para detectar nuevos pedidos, la cocina desconoce que existe trabajo pendiente hasta consultar manualmente, y el administrador visualiza información desactualizada.

Con la implementación de Redis Pub/Sub, el flujo se transforma radicalmente. El pedido se persiste en PostgreSQL e inmediatamente se publica un evento ROUND_PENDING en Redis. El sistema distribuye este evento a todos los suscriptores relevantes de manera selectiva. El WebSocket Gateway recibe el evento y lo transmite exclusivamente a los mozos y administradores conectados de esa sucursal específica. En menos de cien milisegundos, todos los actores relevantes visualizan el nuevo pedido.

El flujo de comunicación sigue una trayectoria bien definida desde el REST API en el puerto ocho mil hacia Redis en el puerto seis mil trescientos ochenta, y desde allí hacia el WebSocket Gateway en el puerto ocho mil uno. El REST API genera eventos cuando ocurren cambios en el sistema. Redis actúa como intermediario que distribuye mensajes a los suscriptores. El WebSocket Gateway recibe estos eventos mediante pattern subscribe y los envía a los clientes WebSocket apropiados. Los frontends Dashboard, pwaWaiter y pwaMenu reciben actualizaciones instantáneas según su rol y contexto.

---

## Capítulo 2: Arquitectura de Pools de Conexiones

La implementación de Redis en Integrador no utiliza una conexión única, sino una arquitectura de pools diferenciados que optimiza el rendimiento bajo alta concurrencia. El módulo de pools de Redis implementa dos pools independientes con responsabilidades claramente definidas, ubicados en el archivo redis_pool.py del paquete de eventos de infraestructura compartida.

El pool asíncrono está diseñado para operaciones no bloqueantes, principalmente la publicación de eventos desde el REST API. Se configura con un máximo de cincuenta conexiones simultáneas, permitiendo que hasta cincuenta operaciones de publicación ocurran en paralelo sin bloquear el servidor. Cada conexión incorpora un timeout de cinco segundos para establecimiento y operaciones de lectura y escritura. Una característica crítica es el intervalo de health check de treinta segundos, que permite detectar automáticamente conexiones muertas en el pool.

La inicialización del pool implementa el patrón Singleton con doble verificación de bloqueo. Este patrón garantiza que solo se cree una instancia del pool incluso bajo acceso concurrente de múltiples corrutinas. La primera verificación ocurre sin adquisición de lock para optimizar el caso común donde el pool ya existe. Si no existe, se adquiere un lock asíncrono y se verifica nuevamente antes de la creación, previniendo condiciones de carrera.

Ciertas operaciones requieren ejecución síncrona, particularmente aquellas que ocurren en contextos donde no existe un event loop de asyncio disponible o donde la simplicidad del código síncrono es preferible. Para estas situaciones, el sistema implementa un pool síncrono separado con veinte conexiones máximas. Las operaciones que utilizan el pool síncrono incluyen la verificación de rate limiting durante el login, la consulta de blacklist de tokens JWT durante la validación de middleware de autenticación, y operaciones de webhook de Mercado Pago que requieren sincronía con sistemas externos.

El pool síncrono utiliza threading.Lock en lugar de asyncio.Lock, ya que opera fuera del contexto asíncrono. Esta separación es fundamental: mezclar locks asíncronos y síncronos puede causar deadlocks sutiles y difíciles de diagnosticar.

El sistema implementa funciones de limpieza coordinadas que se ejecutan durante el shutdown de la aplicación. La función de cierre de pool cierra tanto el pool asíncrono como el síncrono, liberando todas las conexiones al sistema operativo. Esta coordinación es crítica para evitar conexiones huérfanas que podrían agotar los recursos de Redis.

---

## Capítulo 3: Sistema de Canales y Enrutamiento Inteligente

Los canales en Redis siguen una convención de nombres jerárquica que permite el enrutamiento preciso de eventos según su naturaleza y audiencia objetivo. El módulo de canales define siete patrones organizados por dominio.

Los canales de nivel de sucursal incluyen el patrón branch seguido del identificador de sucursal y waiters para eventos destinados a todos los mozos de una sucursal específica, branch con identificador y kitchen para eventos del personal de cocina, y branch con identificador y admin para eventos de administradores y managers de la sucursal.

Los canales de nivel de sector utilizan el patrón sector seguido del identificador de sector y waiters para eventos filtrados por sector específico destinados a mozos asignados a ese sector particular.

Los canales de nivel de sesión emplean el patrón session seguido del identificador de sesión para eventos dirigidos a los comensales de una mesa específica activa, incluyendo actualizaciones de carrito compartido y notificaciones de estado de pedido.

Los canales de nivel de usuario siguen el patrón user con el identificador de usuario para notificaciones directas a un usuario específico. Los canales de nivel de tenant utilizan tenant con identificador y admin para eventos administrativos a nivel de restaurante completo.

El sistema no difunde todos los eventos a todos los canales indiscriminadamente. En su lugar, implementa un enrutamiento inteligente basado en el tipo de evento, su estado en el ciclo de vida, y la relevancia para cada audiencia.

Cuando se crea un nuevo pedido con estado ROUND_PENDING, el sistema publica en el canal de mozos de la sucursal para que algún mozo lo verifique físicamente en la mesa, y simultáneamente en el canal de administradores para visibilidad en el Dashboard. Notablemente, no se envía a cocina en este punto porque el pedido debe ser verificado primero por el mozo. Tampoco se notifica a los comensales, ya que ellos mismos iniciaron el pedido.

Cuando el mozo verifica el pedido y el estado avanza a ROUND_CONFIRMED, se notifica a los administradores que ahora pueden enviarlo a cocina. Solo cuando el administrador ejecuta la acción de enviar a cocina con estado ROUND_SUBMITTED, el evento se publica en el canal de cocina donde aparece en la pantalla de nuevos pedidos.

Este enrutamiento selectivo minimiza el ruido de notificaciones y garantiza que cada rol visualice exclusivamente la información relevante para su función operativa.

Una característica avanzada del sistema es el filtrado por sector para restaurantes con múltiples zonas de servicio como Interior, Terraza o Barra. El sistema permite enviar eventos únicamente a los mozos asignados al sector correspondiente de la mesa.

Cuando un evento incluye identificador de sector, el sistema publica en dos canales complementarios: el canal específico del sector para mozos asignados a ese sector, y el canal general de la sucursal como respaldo para garantizar que ningún evento se pierda.

El WebSocket Gateway mantiene un mapeo actualizado de asignaciones mozo-sector mediante el repositorio de sectores con caché TTL de sesenta segundos. Este caché reduce drásticamente las consultas a la base de datos durante períodos de alta actividad.

---

## Capítulo 4: Sistema de Publicación de Eventos

El corazón del sistema de eventos reside en la función de publicación ubicada en el módulo publisher del paquete de eventos. Esta implementación trasciende un simple wrapper de publicación de Redis para incorporar múltiples capas de protección y resiliencia.

La validación de tamaño ocurre antes de cualquier publicación, verificando que el mensaje no exceda sesenta y cuatro kilobytes. Este límite previene problemas de memoria en los suscriptores y latencia excesiva en la red. Si un evento supera este umbral, se registra un warning y la publicación se rechaza con una excepción de valor inválido.

La serialización compacta convierte el evento a JSON sin espacios innecesarios para minimizar el tamaño de transmisión. La serialización incluye manejo especial para objetos datetime y otros tipos no serializables nativamente.

Si la publicación falla por una desconexión temporal de Redis, el sistema implementa reintentos con backoff exponencial decorrelacionado. El delay exponencial base comienza en medio segundo y se duplica en cada intento hasta un máximo de diez segundos. El jitter decorrelacionado previene el problema de thundering herd donde múltiples clientes que fallaron simultáneamente reintentan al mismo instante y sobrecargan Redis nuevamente. Con jitter, los reintentos se distribuyen aleatoriamente en el tiempo.

El sistema implementa el patrón Circuit Breaker en el módulo de circuit breaker para prevenir cascadas de fallos cuando Redis no está disponible. El circuit breaker opera en tres estados. El estado CLOSED representa operación normal donde las publicaciones proceden normalmente y se mantiene un conteo de fallos consecutivos. El estado OPEN representa fallo rápido: después de cinco fallos consecutivos, el circuit breaker se abre y las publicaciones fallan inmediatamente sin intentar contactar a Redis, retornando cero suscriptores. Esto previene que la aplicación se bloquee esperando timeouts de un Redis que claramente no está respondiendo. El estado HALF_OPEN representa recuperación: después de treinta segundos en estado OPEN, el circuit breaker permite un número limitado de pruebas de tres llamadas. Si estas pruebas tienen éxito, el circuit breaker retorna a CLOSED. Si fallan, vuelve a OPEN.

La implementación es thread-safe mediante threading.Lock, permitiendo su uso seguro desde múltiples corrutinas o hilos concurrentes.

Además del Pub/Sub tradicional, el sistema soporta publicación a Redis Streams mediante la función de publicación a stream. Los Streams proporcionan persistencia y garantía de entrega para eventos críticos que no deben perderse. El límite de cincuenta mil entradas proporciona aproximadamente dieciséis horas de buffer a carga máxima, utilizando trimming aproximado para prevenir crecimiento ilimitado.

---

## Capítulo 5: Publicadores de Dominio Especializados

El módulo de publicadores de dominio implementa funciones especializadas para cada tipo de evento del sistema, encapsulando la lógica de routing compleja en interfaces simples.

La función de publicación de eventos de ronda maneja el ciclo completo de vida de pedidos. Cuando el tipo es ROUND_PENDING, publica al canal de mozos del sector si existe sector_id, al canal de mozos de la sucursal como respaldo, y al canal de administradores. Para ROUND_CONFIRMED publica solo a administradores ya que el mozo ya verificó. Para ROUND_SUBMITTED publica a administradores y cocina. Los estados posteriores IN_KITCHEN, READY y SERVED publican a administradores, cocina, mozos y sesión de diners.

La función de publicación de eventos de llamada de servicio maneja solicitudes de atención de clientes. El evento SERVICE_CALL_CREATED publica al canal de mozos del sector y administradores. SERVICE_CALL_ACKED notifica a la sesión que un mozo reconoció la solicitud. SERVICE_CALL_CLOSED indica que la solicitud fue atendida.

La función de publicación de eventos de facturación maneja el flujo de pagos. CHECK_REQUESTED publica a mozos y administradores. PAYMENT_APPROVED y PAYMENT_REJECTED publican a la sesión de diners para actualizar su interfaz. CHECK_PAID cierra el ciclo de pago.

La función de publicación de eventos de mesa maneja cambios de estado. TABLE_SESSION_STARTED publica a mozos del sector, mozos de la sucursal y administradores cuando un cliente escanea el código QR. TABLE_CLEARED indica que la sesión terminó y la mesa está disponible. TABLE_STATUS_CHANGED notifica cambios de estado intermedios.

La función de publicación de eventos CRUD administrativos notifica cambios en entidades del sistema. ENTITY_CREATED, ENTITY_UPDATED, ENTITY_DELETED y CASCADE_DELETE publican al canal de administradores de la sucursal y opcionalmente al canal de administradores del tenant.

La función de publicación de eventos de carrito maneja la sincronización del carrito compartido entre dispositivos. CART_ITEM_ADDED, CART_ITEM_UPDATED, CART_ITEM_REMOVED y CART_CLEARED publican exclusivamente al canal de sesión, ya que solo afectan a los comensales de esa mesa específica. CART_SYNC proporciona el estado completo del carrito para reconexiones.

---

## Capítulo 6: Suscripción y Procesamiento de Eventos

El WebSocket Gateway implementa el lado receptor del sistema Pub/Sub en el módulo de subscriber. Esta implementación sigue un patrón de orquestador delgado que delega la lógica específica a módulos especializados extraídos durante la refactorización arquitectónica.

El suscriptor utiliza pattern subscribe para escuchar múltiples canales con patrones glob. Los patrones incluyen branch asterisco waiters para todos los canales de mozos, branch asterisco kitchen para todos los canales de cocina, branch asterisco admin para todos los canales de administración, sector asterisco waiters para todos los canales de sector, y session asterisco para todas las sesiones de mesa.

Los eventos pueden llegar más rápido de lo que el sistema puede procesarlos, especialmente durante picos de actividad. Para manejar esta situación, el suscriptor implementa una cola de backpressure con capacidad configurable de quinientos eventos, optimizado para sucursales de aproximadamente cien mesas.

Si la cola alcanza su capacidad máxima, los eventos más antiguos se descartan automáticamente gracias al límite máximo del deque. El sistema monitorea activamente la tasa de descarte mediante el tracker de drop rate.

El módulo de tracking de drop rate implementa un tracker con ventana deslizante de sesenta segundos. Si más del cinco por ciento de los eventos están siendo descartados en la ventana, se genera una alerta crítica indicando que el sistema está sobrecargado y requiere atención inmediata. El cooldown de cinco minutos entre alertas previene tormentas de notificaciones.

Para optimizar el rendimiento, los eventos no se procesan individualmente sino en lotes de hasta cincuenta eventos. Este enfoque reduce la sobrecarga de cambios de contexto y mejora el throughput general del sistema.

El procesamiento de cada lote incluye validación del esquema del evento contra tipos conocidos, determinación de destinatarios identificando qué conexiones WebSocket deben recibir el evento, envío paralelo a todas las conexiones relevantes mediante asyncio.gather, y registro de métricas de éxito y fallo para monitoreo.

Si la conexión con Redis se pierde, el suscriptor implementa reconexión automática con backoff exponencial y jitter decorrelacionado. El proceso de reconexión incluye limpieza del pubsub anterior con timeouts de cinco segundos para unsubscribe y close, creación de un nuevo objeto pubsub, y re-suscripción a todos los canales. Después de veinte intentos fallidos, el suscriptor reporta un error fatal pero continúa intentando indefinidamente.

---

## Capítulo 7: Seguridad con Redis

Cuando un usuario cierra sesión, su token JWT sigue siendo técnicamente válido hasta su expiración natural de quince minutos para access tokens. Para invalidar estos tokens inmediatamente, el sistema mantiene una blacklist en Redis implementada en el módulo de blacklist de tokens.

Para agregar a blacklist, cuando un usuario ejecuta logout, el identificador único JWT del token se almacena en Redis con clave compuesta del prefijo de blacklist de autenticación seguido del identificador. El TTL se calcula dinámicamente para coincidir con el tiempo restante de validez del token, permitiendo que Redis limpie automáticamente las entradas expiradas.

Para verificación, el sistema consulta si la clave existe en Redis. La optimización utiliza Redis Pipeline para combinar múltiples consultas en un solo round-trip, verificando simultáneamente la blacklist individual y la revocación a nivel de usuario.

La política de fallo cerrado es crítica: si Redis no está disponible durante la verificación de blacklist, el sistema asume que el token está en la blacklist y rechaza la solicitud. Esta política sigue el principio de seguridad de denegar acceso cuando hay duda.

Además de la blacklist individual, el sistema permite revocar todos los tokens de un usuario mediante un timestamp de revocación almacenado con el prefijo de revocación de usuario seguido del identificador de usuario. Cualquier token emitido antes de este timestamp se considera inválido, incluso si no está explícitamente en la blacklist.

Esta funcionalidad es esencial cuando se detecta actividad sospechosa en la cuenta, cuando el usuario cambia su contraseña, o cuando un administrador fuerza el cierre de todas las sesiones de un usuario.

El sistema protege contra ataques de fuerza bruta limitando los intentos de login a cinco por minuto por dirección de email. La implementación utiliza un script Lua para garantizar atomicidad de la operación INCR más EXPIRE. El script incrementa el contador, establece el TTL si es el primer intento de la ventana, maneja el caso donde el TTL se perdió por alguna razón re-estableciéndolo, y retorna el conteo actual junto con el TTL restante.

Este script previene una condición de carrera sutil: sin atomicidad, si el servidor fallara entre INCR y EXPIRE, la clave quedaría sin TTL y el contador nunca se resetearía.

El SHA del script se cachea en memoria para evitar re-transmitirlo en cada llamada. Si Redis reinicia y pierde los scripts cargados, el sistema detecta el error NOSCRIPT y recarga automáticamente.

Cuando el límite se excede, el sistema responde con HTTP cuatrocientos veintinueve e incluye el header Retry-After con el tiempo restante en segundos.

---

## Capítulo 8: Rate Limiting en WebSocket

El rate limiting de conexiones WebSocket se implementa en el módulo de rate limiter del Gateway. La clase WebSocketRateLimiter implementa un algoritmo de ventana deslizante con contador.

El algoritmo mantiene una lista de timestamps por conexión. En cada verificación, elimina los timestamps fuera de la ventana configurada y rechaza si el conteo excede el máximo de mensajes permitidos. La configuración por defecto permite veinte mensajes por segundo por conexión.

El sistema implementa límites de memoria con un máximo de cinco mil conexiones tracked. Cuando se alcanza este límite, se ejecuta evicción de las entradas más antiguas eliminando el diez por ciento para hacer espacio.

Una característica avanzada es el tracking de penalizaciones para conexiones eviccionadas. Esto previene que usuarios maliciosos evadan el rate limit simplemente reconectando. La penalización persiste por una hora después de la evicción.

Las métricas del rate limiter incluyen conteos de mensajes permitidos, mensajes rechazados y eviciones, proporcionando visibilidad sobre el comportamiento del sistema bajo carga.

---

## Capítulo 9: Caché de Sectores

El WebSocket Gateway implementa caché de asignaciones de sectores para reducir consultas a la base de datos. La clase SectorCache en el repositorio de sectores mantiene un caché en memoria con TTL configurable.

El caché utiliza una tupla de identificador de usuario e identificador de tenant como clave, almacenando una lista de identificadores de sectores asignados. El TTL por defecto es de sesenta segundos, permitiendo que cambios de asignación se reflejen en un minuto máximo.

El límite máximo de mil entradas previene crecimiento descontrolado de memoria. Cuando se alcanza el límite, el sistema ejecuta evicción de las entradas más antiguas por timestamp de creación siguiendo el patrón LRU.

La implementación es thread-safe mediante threading.Lock, permitiendo acceso seguro desde múltiples corrutinas del event loop. Las métricas incluyen hits, misses y ratio de aciertos para monitorear la efectividad del caché.

El método de limpieza de expirados elimina entradas cuyo TTL ha vencido. El método de invalidación permite remover entradas específicas cuando se actualiza una asignación en la base de datos.

---

## Capítulo 10: Patrón Outbox para Entrega Garantizada

Un desafío crítico en sistemas basados en eventos es garantizar que los datos de negocio y los eventos se guarden de forma atómica. Consideremos un escenario problemático: el backend guarda un pago en PostgreSQL, intenta publicar PAYMENT_APPROVED a Redis, pero Redis está temporalmente indisponible. El pago existe en la base de datos pero el evento nunca se publicó. El Dashboard y pwaWaiter nunca reciben la notificación.

El Patrón Outbox resuelve este problema escribiendo eventos a una tabla de la base de datos dentro de la misma transacción que los datos de negocio.

El flujo del patrón Outbox comienza en el endpoint REST API donde se crea el Payment y se escribe el OutboxEvent en la misma transacción. Al ejecutar commit, ambos se guardan atómicamente. El Outbox Processor, que corre como tarea de background cada segundo, selecciona eventos con estado PENDING ordenados por timestamp de creación. Actualiza el estado a PROCESSING para prevenir doble publicación. Publica a Redis. Actualiza el estado a PUBLISHED o incrementa el contador de reintentos si falla. Después de cinco reintentos fallidos, marca el evento como FAILED.

El modelo OutboxEvent incluye campos para identificador de tenant, tipo de evento, tipo de agregado como round o check o service_call, identificador de agregado, payload serializado como JSON, estado con valores posibles PENDING, PROCESSING, PUBLISHED o FAILED, contador de reintentos, último error, timestamp de creación y timestamp de procesamiento.

Los índices optimizados para polling eficiente incluyen un índice compuesto en estado y timestamp de creación para la query principal del processor, y un índice en tenant y estado para filtrado por tenant.

Los eventos cubiertos por Outbox incluyen CHECK_REQUESTED de alta criticidad porque el cliente espera confirmación de cuenta, PAYMENT_APPROVED de criticidad máxima porque afecta dinero y el Dashboard debe actualizar, PAYMENT_REJECTED de alta criticidad porque el cliente debe reintentar pago, CHECK_PAID de criticidad máxima porque cierra el flujo de pago, ROUND_SUBMITTED de alta criticidad porque cocina debe recibir pedido, ROUND_READY de alta criticidad porque el mozo debe servir plato listo, y SERVICE_CALL_CREATED de criticidad media porque representa una llamada de servicio al mozo.

Los eventos de menor criticidad como ROUND_CONFIRMED, ROUND_IN_KITCHEN y ROUND_SERVED usan publicación directa a Redis por eficiencia.

---

## Capítulo 11: Redis Streams Consumer con Recuperación

Mientras Redis Pub/Sub es eficiente para notificaciones en tiempo real, no garantiza entrega. Si el WebSocket Gateway está reiniciando cuando llega un evento, el mensaje se pierde. Para eventos críticos, el sistema implementa un Consumer Group sobre Redis Streams.

El módulo de stream consumer implementa un consumidor completo con recuperación de mensajes pendientes mediante PEL (Pending Entries List), Dead Letter Queue para mensajes fallidos, y backoff exponencial con jitter para errores.

La configuración del Stream Consumer utiliza la clave events:critical como nombre del stream, ws_gateway_group como nombre del consumer group, y gateway-primary como nombre del consumidor. La verificación de PEL ocurre cada treinta ciclos, aproximadamente cada minuto. Los mensajes pendientes por más de treinta segundos se consideran para recuperación. Después de tres reintentos, los mensajes se mueven a la Dead Letter Queue.

El flujo del consumer comienza creando el Consumer Group si no existe. Luego recupera mensajes pendientes de sesiones anteriores. El loop principal lee mensajes nuevos con XREADGROUP bloqueando por dos segundos, procesa cada mensaje y ejecuta ACK en éxito. Cada treinta ciclos verifica la PEL para mensajes abandonados.

La recuperación de PEL utiliza XAUTOCLAIM para reclamar mensajes idle automáticamente. Obtiene mensajes pendientes por más de treinta segundos. Para cada mensaje, obtiene el conteo de reintentos del metadata. Si excede el máximo de reintentos, mueve el mensaje a la Dead Letter Queue con metadata completo incluyendo identificador original, stream de origen, datos, conteo de reintentos, timestamp de fallo y nombre del consumidor. Si no excede el máximo, reintenta el procesamiento.

El manejo del error NOGROUP ocurre si el Consumer Group se elimina externamente, por ejemplo cuando Redis reinicia sin persistencia. El consumer detecta el error y recrea el grupo automáticamente.

---

## Capítulo 12: Scripts Lua para Atomicidad

El módulo de scripts Lua del WebSocket Gateway implementa rate limiting atómico para conexiones WebSocket. El script de rate limiting recibe la clave de rate limit, el máximo de mensajes permitidos, el tamaño de ventana en segundos y el timestamp actual. Retorna una tupla indicando si está permitido, el conteo actual y el TTL restante.

El script primero obtiene el contador actual. Verifica si excede el límite y retorna cero si lo hace, indicando rechazo. Si está permitido, incrementa el contador. Establece el TTL solo en el primer request de la ventana. Retorna uno con el nuevo conteo y TTL, indicando que la operación está permitida.

Las ventajas sobre implementación en Python son significativas. La atomicidad garantiza que todo ejecuta como operación atómica en Redis, eliminando race conditions. Un único round-trip reduce la latencia comparado con operaciones separadas de GET, INCR y EXPIRE. La imposibilidad de que dos requests incrementen simultáneamente elimina inconsistencias.

El caché de SHA almacena el identificador del script después de la primera carga para evitar re-transmitirlo en cada llamada. Si Redis reinicia y pierde los scripts cargados, el sistema detecta el error NOSCRIPT y recarga automáticamente.

El ACK en lote con Pipeline agrupa acknowledgments para alto throughput. Procesa en lotes de cien para evitar pipelines excesivamente grandes. Reduce significativamente la latencia cuando el Gateway procesa lotes grandes de mensajes.

---

## Capítulo 13: Schema de Eventos

El dataclass Event define la estructura de todos los eventos del sistema. Los campos requeridos incluyen type como tipo de evento, tenant_id como identificador de tenant que debe ser positivo, y branch_id como identificador de sucursal que debe ser mayor o igual a cero, donde cero indica eventos a nivel de tenant.

Los campos opcionales incluyen table_id para identificador de mesa, session_id para identificador de sesión de mesa, sector_id para routing específico de sector, entity como diccionario con datos específicos del evento, actor como diccionario identificando quién disparó el evento con user_id y role, ts como timestamp en formato ISO que se genera automáticamente, y v como versión del schema con valor por defecto de uno.

La validación en post-init verifica que todos los campos requeridos estén presentes, que los tipos sean correctos verificando strings, enteros y diccionarios, y que los identificadores sean positivos. Lanza ValueError si la validación falla.

La serialización a JSON convierte el evento a string JSON con timestamp ISO. La deserialización desde JSON reconstruye el objeto Event desde un string JSON.

---

## Capítulo 14: Monitoreo y Diagnóstico

El sistema expone múltiples métricas para monitorear la salud de la infraestructura Redis.

El estado del Circuit Breaker incluye el estado actual que puede ser closed, open o half_open, el conteo de fallos consecutivos actuales, el total de llamadas rechazadas históricamente, y el timestamp del último fallo.

El Drop Rate del Suscriptor incluye el total de eventos procesados, el total de eventos descartados, los procesados en la ventana actual, los descartados en la ventana actual, la tasa de descarte porcentual actual, el umbral de alerta configurado, el conteo de alertas emitidas, y el tamaño de ventana en segundos.

El endpoint de health detallado del WebSocket Gateway retorna estado de redis_async, información del pool síncrono, y estadísticas de conexiones activas.

Para diagnosticar el problema de eventos que no llegan a clientes, se debe verificar que Redis esté corriendo, verificar suscripción del WebSocket Gateway en logs buscando el mensaje de inicio del subscriber, verificar publicación de eventos en logs del REST API buscando el mensaje de evento publicado a canal, verificar conexión WebSocket del cliente en consola del navegador, y verificar que el cliente está suscrito a los canales correctos.

Para diagnosticar alta latencia en eventos, se debe verificar el tamaño de la cola de eventos ya que si está cerca del máximo indica sistema sobrecargado, revisar drop rate ya que más del cinco por ciento indica problemas de capacidad, verificar latencia de Redis, verificar si el circuit breaker está en estado OPEN, y revisar CPU y memoria del servidor Redis.

Para diagnosticar conexión a Redis que falla intermitentemente, se debe verificar estado del circuit breaker en métricas, buscar errores de conexión en logs, verificar recursos del servidor Redis incluyendo memoria, CPU y conexiones, verificar el límite de conexiones de Redis en maxclients, y considerar aumentar timeouts si la red tiene latencia variable.

Para diagnosticar rate limiting que no funciona, se debe verificar que Redis esté accesible desde el backend, verificar que el script Lua esté cargado buscando el mensaje de cache miss en logs, y verificar que las claves de rate limit tengan TTL correcto consultando Redis directamente.

---

## Capítulo 15: Configuración y Parámetros

La configuración centralizada en el módulo de settings define todos los parámetros de Redis con valores optimizados para restaurantes.

Los parámetros de conexión base incluyen redis_url con valor por defecto de redis://localhost:6380 usando puerto seis mil trescientos ochenta en desarrollo, y redis_socket_timeout de cinco segundos para timeout de conexión y operaciones I/O.

Los parámetros de pools de conexión incluyen redis_pool_max_connections de cincuenta para conexiones asíncronas máximas, y redis_sync_pool_max_connections de veinte para conexiones síncronas máximas utilizadas en rate limiting y blacklist.

Los parámetros de procesamiento de eventos incluyen redis_event_queue_size de quinientos como tamaño de cola de backpressure, redis_event_batch_size de cincuenta como eventos procesados por lote, redis_publish_max_retries de tres como reintentos de publicación, y redis_publish_retry_delay de cero punto uno segundos como delay base para reintentos.

Los parámetros de reconexión y timeouts incluyen redis_max_reconnect_attempts de veinte como intentos máximos de reconexión, redis_pubsub_cleanup_timeout de cinco segundos como timeout para limpieza de pubsub, y redis_pubsub_reconnect_total_timeout de quince segundos como timeout total de reconexión.

Los parámetros de control de calidad incluyen redis_event_strict_ordering como false por defecto indicando si eventos reintentados van al frente de la cola, y redis_event_staleness_threshold de cinco segundos para advertencia si un evento espera más de ese tiempo.

---

## Capítulo 16: Recomendaciones de Escalamiento

Para un restaurante pequeño con cinco a diez mesas y aproximadamente cincuenta conexiones WebSocket concurrentes, la configuración por defecto es adecuada.

Para restaurantes medianos con veinte a cincuenta mesas y aproximadamente doscientas conexiones concurrentes, se recomienda aumentar redis_pool_max_connections a cien, aumentar redis_event_queue_size a dos mil, y considerar Redis en hardware dedicado si comparte servidor con PostgreSQL.

Para cadenas con múltiples sucursales con más de cien mesas totales y más de quinientas conexiones concurrentes, se recomienda implementar Redis Cluster o Redis Sentinel para alta disponibilidad, aumentar redis_pool_max_connections a doscientos, aumentar redis_sync_pool_max_connections a cincuenta, utilizar servidor Redis dedicado con réplica para failover, y establecer monitoreo activo de métricas de latencia y memoria.

---

## Conclusión

Redis en Integrador representa una implementación enterprise-grade que trasciende el uso convencional de almacén de datos en memoria. La arquitectura implementa múltiples capas de resiliencia y patrones avanzados que garantizan operación continua incluso bajo condiciones adversas.

Los patrones de resiliencia implementados incluyen Circuit Breaker que previene cascadas de fallos cuando Redis no responde, backoff exponencial con jitter que evita thundering herd en reconexiones, patrón Outbox que garantiza consistencia transaccional entre PostgreSQL y Redis, Consumer Groups con recuperación de PEL que aseguran entrega de eventos críticos, y Dead Letter Queue que preserva mensajes fallidos para análisis posterior.

Las optimizaciones de rendimiento incluyen pools separados async y sync que optimizan diferentes patrones de acceso, scripts Lua atómicos que eliminan race conditions en rate limiting, pipeline batching que reduce latencia en ACKs masivos, y constantes centralizadas que garantizan consistencia entre publisher y consumer.

Las políticas de seguridad siguen el principio fundamental de fail-closed: ante cualquier duda o error, el sistema deniega acceso en lugar de permitirlo. El rate limiting atómico mediante Lua previene ataques de fuerza bruta, y la blacklist de tokens proporciona revocación instantánea de sesiones.

La arquitectura dual de Pub/Sub más Streams proporciona el balance óptimo. Pub/Sub maneja eventos de baja latencia donde pérdida ocasional es aceptable. Streams maneja eventos críticos como pagos y pedidos a cocina que requieren entrega garantizada.

El monitoreo integral mediante métricas de circuit breaker, drop rate y estadísticas de conexión permite identificar problemas antes de que afecten a los usuarios. La configuración flexible soporta desde pequeños restaurantes hasta cadenas con múltiples sucursales.

Esta arquitectura representa las mejores prácticas de la industria para sistemas de eventos en tiempo real, proporcionando la base sólida sobre la cual Integrador construye su experiencia de usuario diferenciada.

---

*Documento generado: Febrero 2026*
*Versión: 2.0 - Reescrito en prosa narrativa*
