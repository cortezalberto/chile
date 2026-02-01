# pwaWaiter: El Corazón Móvil del Servicio de Mesa

## Introducción: El Problema que Resuelve pwaWaiter

En el ecosistema de un restaurante moderno, el personal de servicio enfrenta un desafío fundamental: mantener consciencia situacional constante de múltiples mesas simultáneamente, cada una en diferentes etapas del ciclo de servicio. Un mozo experimentado desarrolla una especie de radar mental que le permite saber cuándo una mesa necesita atención, cuándo un pedido está listo en cocina, y cuándo un cliente está esperando la cuenta. Sin embargo, este "radar" tiene limitaciones físicas evidentes: el mozo no puede estar en todas partes al mismo tiempo, y la información que percibe está limitada por su campo visual y auditivo.

pwaWaiter nace como una extensión digital de este radar natural. La aplicación transforma el dispositivo móvil del mozo en un centro de comando personal que concentra toda la información relevante de sus mesas asignadas en tiempo real. Cuando un cliente escanea un código QR y realiza un pedido desde pwaMenu, esa información viaja instantáneamente al dispositivo del mozo correspondiente. Cuando la cocina termina de preparar un plato, el mozo recibe una notificación sonora incluso si está en el extremo opuesto del salón. Cuando un comensal presiona el botón de llamado en su mesa, el mozo lo sabe de inmediato.

La aplicación está construida como una Progressive Web App, lo que significa que puede instalarse en cualquier dispositivo móvil sin necesidad de pasar por tiendas de aplicaciones. Esta decisión arquitectónica no es casual: los restaurantes rotan personal frecuentemente, y la fricción de instalación debe ser mínima. Un nuevo mozo puede comenzar a usar la aplicación en segundos, simplemente navegando a una URL y añadiendo el acceso directo a su pantalla de inicio.

---

## Capítulo 1: La Arquitectura Conceptual

### El Principio de Estado Derivado

La arquitectura de pwaWaiter se fundamenta en un principio que permea todo el diseño de la aplicación: el estado de la interfaz debe derivarse del estado de los datos, nunca sincronizarse manualmente con él. Este principio, conocido en la comunidad React como "derived state", elimina una categoría completa de bugs relacionados con inconsistencias entre lo que el usuario ve y lo que realmente está sucediendo en el sistema.

Consideremos el componente principal de la aplicación, el archivo `App.tsx`. Este componente no contiene lógica de navegación tradicional con rutas y redirects. En su lugar, implementa una función `renderContent()` que examina el estado actual de la aplicación y retorna el componente apropiado. Si el usuario no ha seleccionado una sucursal, ve la pantalla de selección de sucursal. Si ha seleccionado una sucursal pero no se ha autenticado, ve el formulario de login. Si se ha autenticado pero la verificación de asignación aún no ha completado, ve un indicador de carga. Si la verificación falló, ve un mensaje de error. Y solo si todas las condiciones previas se cumplen, ve la pantalla principal con el grid de mesas.

Esta cascada de condiciones puede parecer verbosa comparada con un router tradicional, pero ofrece garantías que ningún sistema de rutas puede proporcionar. Es imposible que el usuario vea el grid de mesas sin haber pasado por cada uno de los pasos previos. Es imposible que quede atrapado en un estado inconsistente donde la UI muestra una cosa pero los datos dicen otra. El estado de la aplicación es la única fuente de verdad, y la UI es meramente una proyección visual de ese estado.

### La Jerarquía de Stores

La gestión de estado en pwaWaiter utiliza Zustand, una biblioteca que se distingue por su simplicidad conceptual. A diferencia de Redux, que requiere acciones, reducers y middleware, Zustand permite definir el estado y sus mutaciones en un solo lugar, con tipado completo de TypeScript y sin boilerplate.

La aplicación organiza su estado en cuatro stores especializados, cada uno responsable de un dominio específico. El primero y más fundamental es el `authStore`, que gestiona todo lo relacionado con la identidad del usuario: sus credenciales, su token de acceso, la sucursal seleccionada, y el estado de verificación de su asignación. El segundo es el `tablesStore`, el verdadero corazón de la aplicación, que mantiene el estado de todas las mesas visibles para el mozo y procesa los eventos en tiempo real que llegan desde el servidor.

Los otros dos stores tienen roles más especializados. El `retryQueueStore` implementa un patrón de resiliencia crucial para aplicaciones móviles: cuando una operación falla debido a problemas de conectividad, se encola para reintento automático cuando la conexión se restablezca. El `historyStore` mantiene un registro de las últimas acciones realizadas por el mozo, útil tanto para auditoría como para debugging cuando algo sale mal.

Estos cuatro stores no operan en aislamiento. El `tablesStore` consume el token del `authStore` para autenticar sus llamadas API. Cuando una operación en `tablesStore` falla, puede delegarla al `retryQueueStore`. Cuando una acción se completa exitosamente, puede registrarla en el `historyStore`. Esta orquestación entre stores refleja la realidad de que el estado de una aplicación no es monolítico sino interconectado.

---

## Capítulo 2: El Flujo de Autenticación y la Verificación de Asignación

### Por Qué un Mozo No Puede Simplemente Hacer Login

En la mayoría de aplicaciones, el flujo de autenticación es sencillo: el usuario ingresa credenciales, el servidor las valida, y si son correctas, el usuario accede a la aplicación. pwaWaiter añade una capa adicional que puede parecer burocrática pero que resuelve un problema operativo real: garantizar que cada mozo solo vea las mesas que le corresponden.

Un restaurante típico tiene múltiples sucursales, y cada sucursal tiene múltiples sectores (terraza, salón principal, salón privado, barra). Los mozos son asignados a sectores específicos en días específicos. Un mismo mozo puede trabajar el lunes en la terraza de la sucursal centro, el martes en el salón de la sucursal norte, y el miércoles tener franco. Si la aplicación simplemente mostrara todas las mesas de todas las sucursales, el mozo estaría abrumado con información irrelevante y podría cometer errores graves, como intentar atender una mesa en una sucursal donde ni siquiera está trabajando ese día.

Para resolver esto, pwaWaiter implementa un flujo de tres etapas. En la primera etapa, antes siquiera de pedir credenciales, la aplicación presenta una lista de sucursales activas. Esta lista se obtiene de un endpoint público que no requiere autenticación, permitiendo que el mozo seleccione dónde trabajará hoy. Esta selección se almacena en el store y persiste en localStorage, de modo que un mozo que trabaja siempre en la misma sucursal no necesita seleccionarla cada vez.

En la segunda etapa, con la sucursal ya seleccionada, aparece el formulario tradicional de login. El mozo ingresa su email y contraseña, y el servidor valida las credenciales de la manera habitual, retornando un token JWT si son correctas. Pero aquí viene el giro: el login exitoso no otorga acceso inmediato a la aplicación.

En la tercera etapa, la aplicación realiza una verificación de asignación llamando al endpoint `/api/waiter/verify-branch-assignment?branch_id={id}`. Este endpoint consulta la tabla de asignaciones y verifica que el mozo autenticado tenga una asignación activa para la sucursal seleccionada en la fecha actual. Si la tiene, retorna los detalles de los sectores asignados. Si no la tiene, retorna un error que la aplicación muestra al usuario, explicando que no tiene asignación para esa sucursal hoy.

Este diseño tiene una consecuencia importante: un mozo con credenciales válidas puede ser rechazado si intenta acceder a una sucursal donde no está asignado. Esto no es un bug sino una característica. Garantiza que el administrador del restaurante mantiene control total sobre quién ve qué mesas, y que ese control se refleja en tiempo real en la aplicación.

### La Gestión Segura de Tokens

Una vez que el mozo ha pasado las tres etapas de autenticación, la aplicación recibe un token JWT que debe gestionar con cuidado. Este token tiene una vida útil corta de quince minutos, una decisión de seguridad que limita el daño potencial si un token es comprometido. Pero quince minutos es muy poco tiempo para un turno de trabajo que puede durar ocho horas, así que la aplicación necesita renovar el token periódicamente.

La renovación se implementa mediante un mecanismo proactivo: cada catorce minutos, un minuto antes de que el token expire, la aplicación solicita automáticamente un nuevo token al servidor. Esta renovación ocurre en segundo plano, invisible para el mozo, que puede continuar trabajando sin interrupciones. El nuevo token reemplaza al anterior en memoria, y la conexión WebSocket se reconecta automáticamente con las nuevas credenciales.

Lo que hace particularmente elegante esta implementación es el manejo del refresh token. En versiones anteriores del sistema, el refresh token se almacenaba en localStorage, exponiéndolo a potenciales ataques de Cross-Site Scripting. La implementación actual, siguiendo la especificación SEC-09 del proyecto, almacena el refresh token en una cookie HttpOnly configurada por el backend. Esta cookie no es accesible desde JavaScript, lo que significa que incluso si un atacante logra inyectar código malicioso en la página, no puede robar el refresh token.

Desde la perspectiva del código frontend, esto simplifica las cosas: la aplicación simplemente incluye `credentials: 'include'` en las solicitudes de refresh, y el navegador se encarga de enviar la cookie automáticamente. El servidor valida la cookie, emite un nuevo access token, y opcionalmente rota también el refresh token enviando una nueva cookie.

### Sincronización Entre Pestañas

Un escenario que puede parecer menor pero que causa problemas reales es cuando un mozo tiene la aplicación abierta en múltiples pestañas o dispositivos. Si el historial de acciones solo existiera en memoria, cada pestaña tendría su propia versión de la historia, potencialmente contradictoria. Si el mozo marca un pedido como servido en una pestaña, esa acción debería reflejarse inmediatamente en todas las demás.

Para resolver esto, el `historyStore` utiliza la API BroadcastChannel del navegador. Esta API permite que diferentes contextos de navegación del mismo origen se comuniquen entre sí. Cuando el historyStore añade una nueva entrada, no solo la guarda en su estado local sino que también la transmite a través del canal. Cualquier otra pestaña que esté escuchando en el mismo canal recibe el mensaje y actualiza su estado correspondiente.

La implementación incluye varias salvaguardas para evitar problemas. Antes de crear el canal, verifica que la API esté disponible en el navegador. Cuando el store se desmonta o el usuario hace logout, el canal se cierra explícitamente para evitar fugas de memoria. Si el canal se cierra inesperadamente, el código lo detecta y resetea su estado interno. Estas precauciones pueden parecer excesivas, pero son el tipo de detalles que marcan la diferencia entre una aplicación que "funciona la mayoría del tiempo" y una que funciona de manera confiable en producción.

---

## Capítulo 3: El Store de Mesas y el Procesamiento de Eventos en Tiempo Real

### La Representación del Estado de una Mesa

Cada mesa en el sistema tiene una representación dual: existe en la base de datos del servidor con todos sus detalles, y existe en el store del cliente como una versión optimizada para visualización rápida. El tipo `TableCard` captura esta representación optimizada, incluyendo solo la información necesaria para mostrar la tarjeta de mesa en el grid y decidir su prioridad visual.

El campo más importante de una TableCard es su `status`, que puede tomar uno de cuatro valores. Una mesa `FREE` está disponible para nuevos clientes. Una mesa `ACTIVE` tiene una sesión en curso, significando que hay comensales sentados que pueden estar ordenando, comiendo, o esperando la cuenta. Una mesa `PAYING` ha solicitado la cuenta pero aún no ha sido cerrada. Y una mesa `OUT_OF_SERVICE` está temporalmente inhabilitada, quizás por limpieza o por un evento privado.

Además del status básico, la TableCard incluye contadores que determinan la urgencia de atención. El campo `open_rounds` indica cuántas rondas de pedidos están pendientes de ser servidas. El campo `pending_calls` cuenta cuántos llamados de servicio activos tiene la mesa. El campo `check_status` indica el estado de la cuenta. Estos tres campos, combinados con el status, determinan si una mesa aparece en la sección de "urgentes" del grid.

Hay también campos que no vienen del servidor sino que son calculados localmente para propósitos de UI. El campo `orderStatus` es una versión agregada del estado de todas las rondas de la mesa, calculada para mostrar un solo badge representativo. Los campos booleanos `statusChanged`, `hasNewOrder`, y `hasServiceCall` controlan las animaciones visuales que alertan al mozo de cambios recientes.

### El Patrón de Animaciones Temporales

Cuando llega un evento de nuevo pedido, la aplicación no solo actualiza el estado de la mesa correspondiente sino que también activa una animación visual que dura un par de segundos. Esta animación sirve para captar la atención del mozo, indicando que algo ha cambiado recientemente. Pero implementar este comportamiento aparentemente simple requiere gestión cuidadosa de timeouts.

El problema surge porque múltiples eventos pueden llegar para la misma mesa en rápida sucesión. Si cada evento programa un timeout para desactivar la animación, y esos timeouts no se coordinan, podemos terminar con animaciones que se cancelan prematuramente o, peor aún, con timeouts huérfanos que intentan actualizar estado que ya no existe.

La solución implementada utiliza Maps para rastrear los timeouts activos por mesa. Cuando llega un evento para la mesa 15 y necesita activar la animación de nuevo pedido, el código primero verifica si ya existe un timeout activo para esa mesa. Si existe, lo cancela. Luego programa un nuevo timeout y lo almacena en el Map con la mesa como clave. Cuando el timeout expira, elimina su entrada del Map y actualiza el estado de la mesa para desactivar la animación.

Este patrón tiene tres Maps separados: uno para las animaciones de cambio de estado (blink azul), otro para las animaciones de nuevo pedido (pulse amarillo), y otro para las animaciones de llamado de servicio (blink rojo). Cada tipo de animación tiene su propia duración configurada en constantes, reflejando diferentes niveles de urgencia. Un llamado de servicio parpadea por tres segundos porque el mozo necesita tiempo para notar el cambio, mientras que un simple cambio de estado parpadea por solo un segundo y medio.

### El Cálculo del Estado Agregado de Pedidos

Una mesa puede tener múltiples rondas de pedidos simultáneamente, cada una en un estado diferente del ciclo de vida. La primera ronda podría estar siendo servida mientras la segunda aún está en cocina y la tercera acaba de ser confirmada por el mozo. Mostrar el estado de cada ronda individualmente en la tarjeta de mesa sería confuso, así que la aplicación calcula un estado agregado que representa la situación general.

La lógica de este cálculo prioriza la información más accionable para el mozo. Si hay rondas listas para servir (`READY`) al mismo tiempo que rondas aún en proceso, el estado agregado es `ready_with_kitchen`, indicando al mozo que tiene items para recoger de cocina pero que habrá más por venir. Si todas las rondas están pendientes de confirmación, el estado es `pending`, indicando que el mozo debe ir a verificar los pedidos. Si todas están confirmadas esperando ser enviadas a cocina, el estado es `confirmed`.

El cálculo considera también casos especiales. Si solo hay una ronda y está servida, esa información se muestra para que el mozo sepa que esa mesa ya fue atendida completamente. Si no hay rondas activas, el estado es `none` y no se muestra ningún badge. La prioridad de estados garantiza que el mozo siempre vea la información más importante primero.

### El Procesamiento de Eventos WebSocket

Cuando un evento llega a través del WebSocket, el store debe decidir qué hacer con él. No todos los eventos son iguales: algunos requieren actualización inmediata del estado, otros disparan animaciones, otros generan notificaciones. El handler de eventos implementa una lógica ramificada que procesa cada tipo de evento de manera apropiada.

Para eventos de ronda como `ROUND_PENDING`, el store primero verifica que el evento corresponda a una mesa que el mozo tiene en su lista. Esta verificación es crucial porque el WebSocket recibe eventos de toda la sucursal, pero el mozo solo debe reaccionar a eventos de sus sectores asignados. Si el evento es relevante, el store actualiza el estado de la mesa, recalcula el estado agregado de pedidos, activa la animación correspondiente, y potencialmente dispara una notificación.

Para eventos de llamado de servicio, el store implementa deduplicación usando un Set que rastrea los IDs de llamados ya procesados. Esto es necesario porque el mismo llamado puede llegar múltiples veces si hay problemas de red. Sin deduplicación, el mozo podría recibir notificaciones repetidas que lo confundirían haciéndole pensar que hay múltiples llamados cuando solo hay uno.

Para eventos de sesión como `TABLE_SESSION_STARTED` o `TABLE_CLEARED`, el store actualiza el status de la mesa pero también puede necesitar refrescar la lista completa de mesas desde el servidor. Esto es porque el inicio o fin de una sesión puede cambiar múltiples campos de la mesa que el evento simple no incluye.

---

## Capítulo 4: La Capa de Servicios y la Comunicación con el Servidor

### El Cliente API y sus Protecciones

El archivo `api.ts` es más que un simple wrapper alrededor de fetch. Es una capa de abstracción que implementa múltiples patrones de seguridad y resiliencia que serían tediosos de repetir en cada llamada individual.

La primera protección es contra ataques SSRF (Server-Side Request Forgery). Aunque SSRF es típicamente un problema de servidores, un cliente web maliciosamente manipulado podría intentar hacer que el navegador del mozo realice requests a URLs internas. La función `isValidApiBase` verifica que la URL base de la API apunte solo a hosts explícitamente permitidos. En desarrollo, esto incluye localhost y 127.0.0.1. En producción, debería incluir solo el dominio del servidor real. Las URLs que apuntan a rangos de IP privados, servicios de metadata de cloud, o cualquier otro destino no autorizado son rechazadas antes de que el request siquiera se intente.

La segunda protección es el manejo de timeouts con AbortController. Cada request tiene un timeout configurable (por defecto treinta segundos) después del cual es abortado automáticamente. Esto previene que la aplicación quede colgada indefinidamente esperando respuesta de un servidor que no responde. El AbortController también permite que código externo cancele requests en vuelo, útil cuando el usuario navega fuera de una vista antes de que su request complete.

La tercera protección es el manejo inteligente de errores. Cuando un request falla, el cliente no simplemente propaga el error sino que lo analiza y lo clasifica. Errores de red reciben un código especial `NETWORK_ERROR` que indica que el problema es de conectividad, no del servidor. Timeouts reciben el código `TIMEOUT`. Errores HTTP son parseados para extraer el mensaje de detalle del cuerpo de la respuesta. Esta clasificación permite que el código que llama al API tome decisiones informadas sobre cómo manejar cada tipo de fallo.

### Las APIs Especializadas

El archivo exporta múltiples objetos API, cada uno agrupando los endpoints relacionados con un dominio específico. Esta organización no es solo estética: refleja los diferentes permisos y patrones de uso de cada grupo de endpoints.

El objeto `authAPI` agrupa las operaciones de autenticación: login, obtener información del usuario actual, refrescar el token, y logout. Estas operaciones son fundamentales para el funcionamiento de la aplicación pero se usan infrecuentemente después del login inicial.

El objeto `tablesAPI` agrupa las operaciones de consulta de mesas. El endpoint principal obtiene la lista de mesas para una sucursal, filtrada automáticamente por el servidor para mostrar solo los sectores asignados al mozo. Otro endpoint obtiene el detalle de la sesión activa de una mesa específica, incluyendo todos sus pedidos, comensales y estado de cuenta.

El objeto `roundsAPI` agrupa las operaciones sobre pedidos. Aquí están las acciones que el mozo realiza frecuentemente: confirmar que verificó un pedido en la mesa, marcar un pedido como servido, eliminar un item de un pedido que aún no fue enviado a cocina. Cada una de estas acciones dispara eventos WebSocket que actualizan la UI de todos los usuarios relevantes.

El objeto `waiterTableAPI` es especialmente interesante porque agrupa las operaciones del flujo de mesa gestionada por mozo. Cuando un cliente no puede o no quiere usar el sistema de autoservicio con QR, el mozo puede activar la mesa manualmente, tomar el pedido, solicitar la cuenta, registrar pagos manuales, y cerrar la mesa. Este flujo alternativo garantiza que el sistema funciona incluso para clientes que prefieren el servicio tradicional.

El objeto `comandaAPI` proporciona un endpoint optimizado para la toma de pedidos rápida. En lugar de cargar el menú completo con todas sus imágenes y descripciones, este endpoint retorna una versión compacta que incluye solo nombre, precio y categoría de cada producto. Esta optimización reduce el tiempo de carga y el consumo de datos, importante cuando el mozo necesita tomar un pedido rápidamente.

### El Servicio WebSocket y su Resiliencia

La clase `WebSocketService` encapsula toda la complejidad de mantener una conexión WebSocket confiable. Esta complejidad es considerable porque las conexiones WebSocket son inherentemente frágiles: pueden cerrarse por timeouts de red, por cambios de conectividad del dispositivo, por el dispositivo entrando en modo sleep, o por problemas del servidor.

La primera línea de defensa es el mecanismo de heartbeat. Cada treinta segundos, el servicio envía un mensaje de tipo "ping" al servidor, que responde con un "pong". Si el pong no llega en diez segundos, el servicio asume que la conexión está muerta y la cierra explícitamente. Esta detección proactiva es necesaria porque los WebSockets no siempre detectan automáticamente cuando la conexión se ha perdido, especialmente en redes móviles donde el dispositivo puede mantener una conexión aparentemente abierta que en realidad ya no funciona.

Cuando la conexión se cierra, el servicio intenta reconectarse automáticamente. Pero no lo hace inmediatamente ni con un intervalo fijo. En lugar de eso, implementa un algoritmo de backoff exponencial con jitter. El primer reintento espera un segundo. El segundo espera dos segundos más un componente aleatorio. El tercero espera cuatro segundos más jitter. Y así sucesivamente hasta un máximo de treinta segundos. Este patrón tiene dos propósitos: evitar que múltiples clientes reconectando simultáneamente abrumen al servidor, y dar tiempo para que problemas transitorios de red se resuelvan antes de reintentar.

El jitter (componente aleatorio) es particularmente importante en escenarios de producción. Si el servidor se reinicia y cien clientes intentan reconectarse exactamente al mismo tiempo, el servidor puede sobrecargarse y fallar nuevamente. Con jitter, los reintentos se distribuyen en el tiempo, reduciendo la carga pico.

El servicio también implementa detección de visibilidad de página. Cuando el usuario cambia a otra aplicación o la pantalla se apaga, el navegador puede suspender la ejecución de JavaScript. Cuando el usuario vuelve, el servicio verifica si la conexión sigue activa. Si no, inicia el proceso de reconexión. Este comportamiento garantiza que el mozo que revisó su teléfono brevemente para algo personal puede volver a la aplicación y encontrarla funcionando sin necesidad de recargar manualmente.

Para ciertos códigos de cierre, el servicio no intenta reconexión. El código 4001 indica fallo de autenticación, significando que el token expiró o fue revocado. El código 4003 indica que el usuario no tiene permiso para conectarse. El código 4029 indica que el usuario excedió el rate limit. En todos estos casos, reintentar la conexión sería inútil hasta que el usuario tome alguna acción correctiva, así que el servicio notifica a la aplicación mediante un callback y no programa más reintentos.

---

## Capítulo 5: El Sistema de Notificaciones

### La Dualidad de Notificaciones Web y Sonido

El mozo no puede estar mirando su pantalla constantemente. Está en movimiento, llevando platos, recogiendo pedidos, interactuando con clientes. Las notificaciones deben ser capaces de captar su atención incluso cuando el teléfono está en su bolsillo o sobre una bandeja.

La implementación distingue entre dos mecanismos complementarios. Las notificaciones web son visuales: aparecen en la pantalla del dispositivo, incluso si la aplicación está en segundo plano. Pero requieren que el usuario haya otorgado permiso explícito, y ese permiso puede ser negado o revocado. El sonido de alerta, por otro lado, se reproduce a través de un elemento de audio HTML y no requiere permisos especiales, aunque puede fallar si el usuario no ha interactuado con la página recientemente debido a las políticas de autoplay de los navegadores.

La estrategia implementada combina ambos mecanismos. Para eventos urgentes, como un llamado de servicio o un pedido listo para recoger de cocina, la aplicación reproduce el sonido de alerta independientemente del estado de permisos de notificación. Luego, si el permiso está otorgado, también muestra la notificación visual. Para eventos menos urgentes, como un nuevo pedido que acaba de ser enviado por un cliente, solo se muestra la notificación visual si el permiso está disponible.

El sonido de alerta se precarga de manera lazy: el elemento de audio se crea solo cuando se necesita por primera vez, y el archivo de audio se configura para no precargarse hasta que sea necesario. Esto evita consumir ancho de banda cargando un archivo de audio que podría nunca usarse.

### Deduplicación y Throttling de Notificaciones

Un problema sutil pero importante es que el mismo evento puede llegar múltiples veces. Esto puede suceder por reconexiones del WebSocket, por bugs en el servidor, o por condiciones de red que causan duplicación de mensajes. Si cada evento generara su propia notificación, el mozo podría verse bombardeado con notificaciones repetidas.

Para evitar esto, el servicio de notificaciones mantiene un Set de identificadores de notificaciones recientes. Cada notificación tiene un tag que la identifica de manera única, típicamente derivado del tipo de evento y el ID de la entidad involucrada. Antes de mostrar una notificación, el servicio verifica si ese tag ya está en el Set. Si lo está, la notificación se descarta silenciosamente. Si no lo está, se añade al Set y se programa su eliminación después de cinco segundos.

El tamaño del Set está limitado a cien entradas para evitar fugas de memoria. Cuando se alcanza el límite, el Set se vacía completamente. Este approach es más simple que implementar una cola FIFO y funciona bien en la práctica porque el escenario de cien notificaciones en cinco segundos es extremadamente improbable.

### Contenido Contextual de las Notificaciones

Las notificaciones no son genéricas. Incluyen información específica que permite al mozo tomar decisiones sin necesidad de abrir la aplicación. Un llamado de servicio indica si el cliente quiere la cuenta, necesita asistencia, o tiene otra solicitud. Un pago aprobado incluye el monto. Un pedido listo incluye el número de mesa.

Esta información se extrae del payload del evento WebSocket. Cada tipo de evento tiene una estructura ligeramente diferente, así que el código de generación de notificaciones es un switch extenso que maneja cada caso. El patrón puede parecer verboso, pero la verbosidad es intencional: cada tipo de evento recibe exactamente el tratamiento que necesita, sin intentar generalizar de maneras que oscurecerían la lógica.

---

## Capítulo 6: Capacidades Offline y Resiliencia

### El Problema de la Conectividad Intermitente

Los restaurantes no son data centers. La señal WiFi puede ser débil en ciertas áreas del salón. Las paredes gruesas de edificios antiguos pueden bloquear señales. Los dispositivos móviles de gama baja pueden tener receptores WiFi deficientes. Y durante horas pico, la congestión de red puede causar timeouts y paquetes perdidos.

Una aplicación que simplemente fallara cuando pierde conectividad sería inutilizable en este ambiente. El mozo no puede quedarse paralizado esperando que la red funcione mientras los clientes esperan. Necesita poder continuar trabajando con información que puede no estar perfectamente actualizada, y necesita poder registrar acciones que se sincronizarán cuando la conectividad se restablezca.

pwaWaiter implementa dos estrategias complementarias para manejar esta realidad. La primera es el cache de estado: cuando la aplicación carga la lista de mesas desde el servidor, también la guarda en IndexedDB. Si en el próximo refresh el servidor no responde, la aplicación puede mostrar los datos cacheados con un indicador visual de que son potencialmente obsoletos. Esta estrategia mantiene la aplicación funcional incluso cuando no puede comunicarse con el servidor.

La segunda estrategia es la cola de acciones. Cuando el mozo intenta realizar una acción como marcar un pedido como servido y la llamada API falla por problemas de red, la acción se encola para reintento posterior. La cola se persiste en localStorage, así que sobrevive incluso si el mozo cierra la aplicación. Cuando el dispositivo detecta que ha vuelto a estar online, procesa la cola automáticamente, ejecutando las acciones en el orden en que fueron encoladas.

### IndexedDB y sus Peculiaridades

IndexedDB es la API estándar del navegador para almacenamiento persistente de grandes cantidades de datos estructurados. A diferencia de localStorage, que solo puede almacenar strings con un límite de varios megabytes, IndexedDB puede almacenar cualquier tipo de dato serializable con límites que pueden alcanzar cientos de megabytes o más dependiendo del navegador y el dispositivo.

Pero IndexedDB tiene una peculiaridad que puede causar problemas: es completamente asíncrona y basada en callbacks. Cada operación abre una transacción, ejecuta uno o más statements, y debe cerrar la transacción explícitamente. Si algo sale mal en el medio, la transacción puede quedar en un estado indeterminado. Y en algunos dispositivos, particularmente iOS con poca memoria disponible, las operaciones pueden bloquearse indefinidamente.

Para mitigar estos riesgos, todas las operaciones de IndexedDB en la aplicación están envueltas en una función `withTimeout` que rechaza la promesa si la operación no completa en treinta segundos. Este timeout es generoso para operaciones normales pero previene que la aplicación quede colgada indefinidamente esperando una base de datos que nunca responderá.

El código también maneja cuidadosamente el cierre de conexiones. Cada operación abre su propia conexión, la usa, y la cierra. No se mantienen conexiones abiertas entre operaciones. Este patrón es menos eficiente que reutilizar conexiones, pero es más robusto ante los diversos modos de fallo de IndexedDB.

### La Cola de Reintentos

El `retryQueueStore` implementa un patrón que aparece frecuentemente en aplicaciones móviles: la cola de trabajo persistente. Las acciones encoladas tienen una estructura que incluye un identificador único, el tipo de acción, el payload de datos, un timestamp de creación, y un contador de reintentos.

Cuando la aplicación detecta que está online nuevamente, procesa la cola en orden FIFO. Cada acción se intenta ejecutar contra el servidor. Si tiene éxito, se elimina de la cola. Si falla con un error de red, se incrementa su contador de reintentos y se mantiene en la cola para el próximo intento. Si falla con un error de negocio como "entidad no encontrada" o "permiso denegado", se elimina de la cola porque reintentar sería inútil.

El contador de reintentos tiene un límite de tres intentos. Una acción que falla tres veces consecutivas se elimina de la cola bajo la asunción de que algo está fundamentalmente mal y no se resolverá con más reintentos. Esto previene que la cola crezca indefinidamente con acciones imposibles de completar.

La cola también implementa deduplicación. Antes de encolar una nueva acción, verifica si ya existe una acción del mismo tipo para la misma entidad. Si existe, la nueva acción se descarta. Esto previene duplicación de acciones cuando el mozo, frustrado por la falta de respuesta, pulsa el mismo botón varias veces.

---

## Capítulo 7: La Interfaz de Usuario

### Diseño para Uso en Movimiento

La interfaz de pwaWaiter está diseñada para ser usada con una sola mano mientras el mozo está de pie y potencialmente cargando bandejas. Los elementos táctiles son grandes, con áreas de toque mínimas de 48 píxeles como recomienda Google. Los colores son de alto contraste, visibles incluso bajo la luz brillante del salón de un restaurante. Las animaciones son breves pero distintivas, capturando la atención periférica del mozo sin distraerlo de su trabajo.

El grid de mesas ocupa la mayor parte de la pantalla, mostrando la información más importante de un vistazo. Cada tarjeta de mesa es un rectángulo con el código de mesa prominente (INT-01, TER-03), un indicador de color para el estado (verde para libre, rojo para ocupada, morado para pagando, gris para fuera de servicio), y badges para condiciones especiales como pedidos pendientes o llamados activos.

Las tarjetas se agrupan automáticamente por urgencia. Las mesas que requieren atención inmediata aparecen primero, en una sección con fondo sutilmente diferente y un indicador pulsante. Dentro de cada grupo, las mesas se ordenan por sector y luego por código, facilitando la localización de una mesa específica.

La barra de filtros en la parte superior permite al mozo enfocarse en un subconjunto de mesas. Puede ver solo las urgentes cuando está en modo de apagar fuegos. Puede ver solo las libres cuando quiere asignar nuevos clientes. Puede ver todas para tener una visión completa. El filtro seleccionado persiste en sessionStorage, así que si el mozo actualiza la página, mantiene su contexto.

### El Modal de Detalle de Mesa

Cuando el mozo toca una tarjeta de mesa, se abre un modal que ocupa la mayor parte de la pantalla y presenta información detallada sobre la sesión activa. Este modal no es una navegación a otra página sino una superposición sobre el grid, permitiendo que el mozo cierre el modal con un gesto o el botón Escape y vuelva exactamente donde estaba.

El modal comienza con un resumen de la situación: cuántas rondas pendientes hay, cuántos llamados activos, y el total consumido hasta el momento. Si hay llamados de servicio, aparece una alerta prominente con un botón para atenderlos. Si hay pedidos listos para servir, aparece otra alerta indicando que hay que ir a cocina.

La sección principal lista las rondas de pedidos, cada una con su estado y contenido. Los items dentro de cada ronda se ordenan por categoría siguiendo el orden natural del servicio: bebidas primero, luego entradas, luego principales, luego postres. Cada item muestra cantidad, nombre, precio, y si corresponde, el nombre del comensal que lo ordenó y cualquier nota especial.

Para rondas en estado PENDING, aparece un botón "Confirmar Pedido" que el mozo pulsa después de verificar el pedido en la mesa. Para rondas en estado READY, aparece un botón "Servido" que el mozo pulsa después de entregar los platos. Para rondas que aún no se han enviado a cocina, los items individuales tienen un botón de eliminación por si el cliente cambió de opinión.

El modal se actualiza en tiempo real. Si mientras el mozo está revisando el detalle de la mesa, llega un nuevo pedido o cocina marca algo como listo, el modal refleja ese cambio inmediatamente sin necesidad de cerrarlo y reabrirlo.

### Pull-to-Refresh y Feedback Táctil

El gesto de pull-to-refresh es familiar para cualquier usuario de smartphones: arrastrar hacia abajo desde el inicio de una lista para refrescar su contenido. La implementación en pwaWaiter sigue este patrón con algunas mejoras de accesibilidad y feedback.

Cuando el mozo comienza a arrastrar, un indicador visual aparece mostrando el progreso hacia el umbral de activación. El arrastre tiene resistencia, haciéndose más difícil cuanto más se arrastra, lo que proporciona feedback físico de que el gesto está siendo reconocido. Cuando se alcanza el umbral, el indicador cambia visualmente para señalar que soltar activará el refresh.

Durante el refresh, el indicador muestra una animación de carga y el estado se anuncia a lectores de pantalla mediante un región aria-live. Esto es importante para accesibilidad: un usuario con discapacidad visual necesita saber que algo está sucediendo aunque no pueda ver la animación.

El hook `usePullToRefresh` encapsula toda esta lógica, exponiendo una API simple que la página consume. El hook maneja los eventos táctiles, calcula las distancias, gestiona los estados, y limpia los listeners cuando el componente se desmonta. Las páginas solo necesitan proporcionar una función de refresh y recibir el estado para renderizar el indicador apropiado.

---

## Capítulo 8: El Flujo de Pedidos y el Rol del Mozo

### La Verificación Como Paso Crítico

El sistema de pedidos de Integrador implementa un flujo deliberadamente conservador donde los pedidos de clientes no llegan directamente a cocina. En lugar de eso, pasan primero por una verificación del mozo. Esta decisión de diseño responde a varios problemas reales observados en restaurantes.

El primero es el error del cliente. Un comensal puede agregar items al carrito por curiosidad sin intención real de ordenarlos. Puede agregar algo para un acompañante que nunca llegó. Puede cambiar de opinión después de enviar el pedido. Si estos pedidos fueran directamente a cocina, el restaurante desperdiciaría ingredientes y tiempo preparando platos que nunca serán consumidos.

El segundo es el error técnico. Los niños que juegan con el teléfono de sus padres pueden enviar pedidos accidentalmente. Una conexión inestable puede causar que el mismo pedido se envíe múltiples veces. Un bug en la aplicación del cliente podría enviar datos malformados. La verificación del mozo actúa como un firewall humano que detecta y previene estos problemas.

El tercero es la coordinación. El mozo conoce el contexto que la aplicación no puede conocer. Sabe que la mesa 5 está por irse y probablemente no debería ordenar un postre que tarda veinte minutos. Sabe que el horno está sobrecargado y que sería mejor sugerir alternativas a platos horneados. Sabe que el cliente habitual de la mesa 3 tiene una alergia que no está en el sistema. La verificación le da oportunidad de intervenir.

Cuando un cliente envía un pedido desde pwaMenu, este llega con estado PENDING. El evento se propaga a través del WebSocket y aparece en el dispositivo del mozo como una alerta de nuevo pedido. El mozo ve qué mesa tiene el pedido y va a verificarlo. En la mesa, puede confirmar que el pedido es correcto, ajustar cantidades si el cliente cambió de opinión, o eliminar items. Una vez satisfecho, pulsa "Confirmar Pedido" y el estado cambia a CONFIRMED.

Solo después de esta confirmación, el administrador o manager puede enviar el pedido a cocina, cambiando el estado a SUBMITTED. Este segundo paso existe para dar control adicional al management sobre cuándo se liberan pedidos a cocina, permitiendo por ejemplo agrupar pedidos de varias mesas para optimizar la producción.

### La Comanda Rápida para Servicio Tradicional

No todos los clientes quieren usar su teléfono para ordenar. Algunos prefieren el servicio tradicional donde el mozo toma nota de su pedido. Para estos casos, pwaWaiter incluye una funcionalidad de "Comanda Rápida" que permite al mozo crear pedidos directamente desde su dispositivo.

El flujo comienza cuando el mozo activa manualmente una mesa que estaba libre. Esto crea una sesión sin comensales digitales, bajo el control exclusivo del mozo. Luego, el mozo navega a la interfaz de comanda rápida que presenta el menú en un formato optimizado para velocidad: sin imágenes, con búsqueda rápida, organizado por categorías.

El mozo va agregando productos al carrito local mientras toma el pedido verbalmente del cliente. Puede ajustar cantidades, agregar notas por item, y asignar items a diferentes comensales si la mesa quiere dividir la cuenta después. Cuando termina, envía el pedido y este entra al flujo normal con estado PENDING, listo para ser confirmado y enviado a cocina.

Esta dualidad entre autoservicio y servicio tradicional garantiza que el sistema no excluye a ningún tipo de cliente. Un restaurante puede tener mesas con códigos QR para clientes que prefieren la tecnología, y mesas tradicionales atendidas completamente por mozos. El backend maneja ambos flujos de manera unificada.

### Marcar Como Servido y Cerrar Ciclos

Cuando cocina termina de preparar un pedido, lo marca como READY. Este evento genera una notificación en el dispositivo del mozo indicando que tiene platos para recoger. El mozo va a cocina, recoge los platos, los lleva a la mesa, y pulsa "Servido" para cambiar el estado a SERVED.

Este paso de marcar como servido no es solo burocrático. Tiene consecuencias reales en el sistema. Afecta las métricas de tiempo de servicio que el management usa para evaluar eficiencia. Libera capacidad en cocina para nuevos pedidos. Y actualiza la vista del cliente en pwaMenu para que sepa que su pedido está en camino o ya llegó.

Si el mozo olvida marcar como servido, el sistema no colapsa, pero las métricas se distorsionan. Por eso la interfaz hace prominente este botón y el modal de detalle de mesa muestra claramente qué pedidos están listos esperando ser servidos.

---

## Capítulo 9: La Configuración PWA

### El Service Worker y el Caching

Como Progressive Web App, pwaWaiter puede funcionar parcialmente sin conexión y puede instalarse en el dispositivo como si fuera una aplicación nativa. Estas capacidades dependen del Service Worker, un script que el navegador ejecuta en segundo plano y que puede interceptar requests de red.

El proyecto utiliza vite-plugin-pwa para generar automáticamente el Service Worker basado en la configuración del build. Durante el proceso de construcción, el plugin analiza los assets generados y crea una lista de precache que el Service Worker descargará y almacenará localmente. Esto incluye el HTML, CSS, JavaScript, y assets estáticos como iconos e imágenes.

Cuando el usuario carga la aplicación por primera vez, el Service Worker se registra y comienza a descargar todos los assets al cache. En visitas subsiguientes, el Service Worker sirve los assets desde el cache local, resultando en tiempos de carga casi instantáneos. Los assets solo se descargan nuevamente cuando hay una nueva versión del Service Worker con una lista de precache actualizada.

El manifest.webmanifest, también generado por el plugin, describe la aplicación para el sistema operativo. Incluye el nombre, colores de tema, iconos en varios tamaños, y la URL de inicio. Cuando el usuario elige "Agregar a pantalla de inicio", el sistema operativo usa esta información para crear un acceso directo que lanza la aplicación en modo standalone, sin barra de navegación del navegador.

### Detección y Aplicación de Actualizaciones

Cuando se despliega una nueva versión de la aplicación, los usuarios existentes necesitan enterarse y actualizar. El hook `usePWA` expone el estado `needRefresh` que indica si hay una nueva versión disponible. La aplicación puede usar este estado para mostrar un banner invitando al usuario a actualizar.

El proceso de actualización funciona así: cuando el navegador detecta que el Service Worker ha cambiado, descarga el nuevo Service Worker pero no lo activa inmediatamente. En lugar de eso, el nuevo Service Worker espera en estado "waiting" hasta que todas las pestañas de la aplicación se cierren. El hook expone una función `updateServiceWorker` que fuerza la activación inmediata del nuevo Service Worker y recarga la página.

Este flujo controlado previene situaciones donde diferentes pestañas de la misma aplicación están ejecutando diferentes versiones del código, lo que podría causar inconsistencias. El usuario siempre tiene control sobre cuándo ocurre la actualización, y siempre termina con todas sus pestañas en la misma versión.

### La Experiencia de Instalación

La instalación de una PWA es opcional pero recomendada para uso regular. Una aplicación instalada tiene acceso a más capacidades del sistema operativo, aparece en el launcher junto a otras aplicaciones, y puede recibir notificaciones más confiablemente.

El hook `usePWA` detecta el evento `beforeinstallprompt` que el navegador emite cuando la aplicación cumple los criterios para ser instalable. Este evento se captura y almacena, permitiendo que la aplicación muestre su propio botón de instalación cuando lo considere apropiado, en lugar de depender del prompt automático del navegador que puede aparecer en momentos inoportunos.

Cuando el usuario pulsa el botón de instalación, la aplicación invoca el método `prompt()` del evento almacenado, que muestra el diálogo nativo de instalación. El usuario puede aceptar o rechazar. Si acepta, el evento `appinstalled` se emite y la aplicación actualiza su estado para reflejar que ya está instalada.

---

## Conclusión: Una Herramienta que Extiende al Profesional

pwaWaiter no pretende reemplazar al mozo humano sino potenciarlo. El juicio del profesional sobre cómo atender a cada cliente, cuándo ofrecer recomendaciones, cómo manejar situaciones difíciles: eso sigue siendo insustituiblemente humano. Lo que la aplicación hace es liberar ancho de banda mental, permitiendo que el mozo dedique su atención a lo que realmente importa en lugar de gastarla en recordar qué mesas tienen pedidos pendientes.

La arquitectura técnica refleja esta filosofía. El estado derivado garantiza que la información mostrada siempre es coherente con la realidad. Los eventos en tiempo real mantienen al mozo informado sin requerir que constantemente refresque la pantalla. Las capacidades offline garantizan que un problema de red no paraliza el servicio. La verificación de pedidos pone al mozo en control del flujo hacia cocina.

El código está diseñado para ser mantenible y extensible. Los stores de Zustand encapsulan la lógica de dominio de manera clara. Los servicios de comunicación implementan patrones robustos de resiliencia. Los hooks personalizados extraen comportamiento reutilizable. Los componentes de UI son pequeños y enfocados. Nuevas funcionalidades pueden agregarse sin desestabilizar las existentes.

Y sobre todo, la aplicación está diseñada para desaparecer. El mejor software de productividad es el que se vuelve invisible, que el usuario opera sin pensar porque sus controles son intuitivos y sus respuestas predecibles. pwaWaiter aspira a ser ese tipo de herramienta: algo que el mozo usa naturalmente como extensión de sí mismo, que amplifica sus capacidades sin interponerse en su trabajo.
