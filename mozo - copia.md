# pwaWaiter: El Corazón Móvil del Servicio de Mesa

## Introducción: El Problema que Resuelve pwaWaiter

En el ecosistema de un restaurante moderno, el personal de servicio enfrenta un desafío fundamental: mantener consciencia situacional constante de múltiples mesas simultáneamente, cada una en diferentes etapas del ciclo de servicio. Un mozo experimentado desarrolla una especie de radar mental que le permite saber cuándo una mesa necesita atención, cuándo un pedido está listo en cocina, y cuándo un cliente está esperando la cuenta. Sin embargo, este "radar" tiene limitaciones físicas evidentes: el mozo no puede estar en todas partes al mismo tiempo, y la información que percibe está limitada por su campo visual y auditivo.

pwaWaiter nace como una extensión digital de este radar natural. La aplicación transforma el dispositivo móvil del mozo en un centro de comando personal que concentra toda la información relevante de sus mesas asignadas en tiempo real. Cuando un cliente escanea un código QR y realiza un pedido desde pwaMenu, esa información viaja instantáneamente al dispositivo del mozo correspondiente. Cuando la cocina termina de preparar un plato, el mozo recibe una notificación sonora incluso si está en el extremo opuesto del salón. Cuando un comensal presiona el botón de llamado en su mesa, el mozo lo sabe de inmediato.

La aplicación está construida como una Progressive Web App utilizando React 19.2.0, Zustand 5 para gestión de estado, TypeScript estricto, y Vite 7 como bundler. Esta arquitectura permite que la aplicación se instale en cualquier dispositivo móvil sin necesidad de pasar por tiendas de aplicaciones. Un nuevo mozo puede comenzar a usar la aplicación en segundos, simplemente navegando a una URL y añadiendo el acceso directo a su pantalla de inicio. La decisión de construir una PWA no es casual: los restaurantes rotan personal frecuentemente, y la fricción de instalación debe ser mínima.

El puerto de desarrollo es el 5178, la interfaz está completamente en español, y el tema visual utiliza naranja (#f97316) como color de acento sobre un fondo claro, con botones rectangulares que evitan deliberadamente las esquinas redondeadas para proyectar una estética profesional y directa.

---

## Capítulo 1: La Cascada de Autenticación en Cinco Pasos

### El Paradigma de Estado Derivado

La arquitectura de pwaWaiter se fundamenta en un principio que permea todo el diseño de la aplicación: el estado de la interfaz debe derivarse del estado de los datos, nunca sincronizarse manualmente con él. Este principio, conocido en la comunidad React como "derived state", elimina una categoría completa de bugs relacionados con inconsistencias entre lo que el usuario ve y lo que realmente está sucediendo en el sistema.

El archivo `App.tsx` no contiene lógica de navegación tradicional con rutas y redirects. En su lugar, implementa una función `renderContent()` que examina el estado actual de la aplicación y retorna el componente apropiado. Esta cascada de condiciones puede parecer verbosa comparada con un router tradicional, pero ofrece garantías que ningún sistema de rutas puede proporcionar. Es imposible que el usuario vea el grid de mesas sin haber pasado por cada uno de los pasos previos. Es imposible que quede atrapado en un estado inconsistente donde la UI muestra una cosa pero los datos dicen otra.

### Paso 1: Selección de Sucursal Previa al Login

El flujo de autenticación comienza antes siquiera de pedir credenciales. El componente `PreLoginBranchSelect.tsx` presenta una lista de sucursales activas obtenida del endpoint público `/api/public/branches`, que no requiere autenticación. Esta decisión arquitectónica permite que el mozo seleccione dónde trabajará hoy sin necesidad de identificarse primero.

La lista de sucursales se carga al montar el componente mediante un efecto que maneja estados de carga y error con indicadores visuales apropiados. Cada sucursal se presenta como un botón grande con el nombre prominente, optimizado para selección táctil con una sola mano. Al seleccionar una sucursal, el sistema almacena tanto el ID como el nombre en el `authStore` mediante las propiedades `preLoginBranchId` y `preLoginBranchName`, y la interfaz transiciona automáticamente al paso siguiente.

Un botón "Cambiar" permanece visible durante todo el flujo posterior, permitiendo que el mozo que seleccionó la sucursal equivocada pueda corregir sin necesidad de cerrar sesión. Este botón limpia las propiedades de sucursal pre-login y retorna al paso inicial.

### Paso 2: Autenticación con Credenciales

Con la sucursal ya seleccionada, aparece el componente `Login.tsx` con el formulario tradicional de email y contraseña. La pantalla muestra prominentemente el nombre de la sucursal seleccionada para que el mozo confirme que está ingresando al lugar correcto.

El envío del formulario invoca `authAPI.login()`, que realiza una petición POST al endpoint `/api/auth/login`. Si las credenciales son válidas, el servidor retorna un token JWT de acceso con quince minutos de vida útil. El refresh token, siguiendo la especificación SEC-09 del proyecto, ya no se almacena en localStorage como en versiones anteriores, sino que el servidor lo configura automáticamente como una cookie HttpOnly con el atributo `secure` en producción y `samesite=lax` para protección contra CSRF.

Esta migración a cookies HttpOnly representa una mejora significativa de seguridad. Las cookies HttpOnly no son accesibles desde JavaScript, lo que significa que incluso si un atacante logra inyectar código malicioso en la página mediante un ataque XSS, no puede robar el refresh token. Desde la perspectiva del código frontend, esto simplifica las cosas: la aplicación simplemente incluye `credentials: 'include'` en las solicitudes de refresh, y el navegador se encarga de enviar la cookie automáticamente.

Tras el login exitoso, el store verifica que el usuario tenga el rol WAITER o ADMIN. Un usuario con solo rol KITCHEN, por ejemplo, sería rechazado con un mensaje explicativo. Simultáneamente, se inicia el intervalo de renovación de token y se establece la conexión WebSocket con el servidor.

### Paso 3: Verificación de Asignación Diaria

El login exitoso no otorga acceso inmediato a la aplicación. En el código de `App.tsx`, después de confirmar que existe un token válido y una sucursal seleccionada, el sistema realiza una verificación de asignación llamando al endpoint `/api/waiter/verify-branch-assignment?branch_id={id}`.

Este endpoint consulta la tabla de asignaciones y verifica que el mozo autenticado tenga una asignación activa para la sucursal seleccionada en la fecha actual. La respuesta incluye un booleano `is_assigned`, un mensaje descriptivo, el nombre de la sucursal, y la lista de sectores asignados si corresponde.

Si el mozo no tiene asignación para esa sucursal hoy, la aplicación muestra una pantalla de "Sin Asignación para Hoy" con el mensaje del servidor y un botón "Elegir otra sucursal" que retorna al paso 1. Este diseño tiene una consecuencia importante: un mozo con credenciales válidas puede ser rechazado si intenta acceder a una sucursal donde no está asignado. Esto no es un bug sino una característica. Garantiza que el administrador del restaurante mantiene control total sobre quién ve qué mesas, y que ese control se refleja en tiempo real en la aplicación.

Si la verificación es exitosa, el sistema establece `assignmentVerified: true` en el store y copia el ID de sucursal pre-login a `selectedBranchId`, que es el campo canónico usado por el resto de la aplicación.

### Pasos 4 y 5: La Interfaz Principal con Dos Pestañas

Una vez verificada la asignación, el componente `MainPage.tsx` toma el control. Esta página presenta una interfaz con dos pestañas en el header: "Comensales" (la vista por defecto) y "Autogestión".

La pestaña Comensales renderiza el componente `TableGrid.tsx`, que muestra todas las mesas asignadas al mozo organizadas por sector. La pestaña Autogestión abre el componente `AutogestionModal.tsx`, un modal de pantalla completa para el flujo de toma de pedidos gestionados directamente por el mozo, útil para clientes que prefieren no usar sus teléfonos.

La página principal también inicializa varios sistemas críticos: el listener de eventos WebSocket mediante `subscribeToEvents()`, el intervalo de actualización periódica de mesas configurado en `UI_CONFIG.TABLE_REFRESH_INTERVAL`, y el gesto de pull-to-refresh para actualización manual. Un banner de conexión en la parte superior indica el estado del WebSocket, y un banner de offline aparece cuando el dispositivo pierde conectividad de red.

---

## Capítulo 2: La Jerarquía de Stores y el Patrón de Selectores

### La Gestión de Estado con Zustand 5

La gestión de estado en pwaWaiter utiliza Zustand en su versión 5.0.9, una biblioteca que se distingue por su simplicidad conceptual. A diferencia de Redux, que requiere acciones, reducers y middleware, Zustand permite definir el estado y sus mutaciones en un solo lugar, con tipado completo de TypeScript y sin boilerplate.

La aplicación organiza su estado en cuatro stores especializados, cada uno responsable de un dominio específico y con su propio archivo de tests en Vitest. Estos stores no operan en aislamiento: el `tablesStore` consume el token del `authStore` para autenticar sus llamadas API, cuando una operación falla puede delegarla al `retryQueueStore`, y cuando una acción se completa exitosamente puede registrarla en el `historyStore`. Esta orquestación refleja la realidad de que el estado de una aplicación no es monolítico sino interconectado.

### El Patrón Crítico de Selectores en React 19

El patrón de selectores es fundamental y su violación constituye uno de los errores más comunes que causan loops infinitos de re-renderizado. La regla es simple pero inflexible: nunca desestructurar el store, siempre usar selectores.

```typescript
// CORRECTO: Usar selectores
const user = useAuthStore(selectUser)
const tables = useTablesStore(selectTables)
const fetchTables = useTablesStore((s) => s.fetchTables)

// INCORRECTO: Nunca desestructurar (causa re-renders infinitos)
// const { user } = useAuthStore()
// const { tables } = useTablesStore()
```

Esta restricción existe porque la desestructuración crea nuevas referencias en cada render, lo que Zustand interpreta como un cambio de estado, disparando un nuevo render, que crea nuevas referencias, ad infinitum. Los selectores, en cambio, retornan referencias estables que solo cambian cuando el dato subyacente realmente cambia.

Para selectores que retornan arrays potencialmente vacíos, el código implementa un patrón adicional de arrays estables. En lugar de retornar un nuevo array vacío cada vez (que sería una nueva referencia), los selectores mantienen una constante `EMPTY_TABLES` o `EMPTY_ARRAY` definida fuera del store que se retorna siempre que el resultado estaría vacío. Este detalle aparentemente menor previene cientos de re-renders innecesarios en aplicaciones con listas dinámicas.

Los selectores que filtran datos implementan además un patrón de caché manual. El selector `selectTablesWithPendingRounds`, por ejemplo, mantiene una variable de caché en el scope del módulo que almacena tanto el array de entrada como el resultado filtrado. Si el array de entrada no ha cambiado (comparación por referencia), retorna el resultado cacheado sin recalcular. Este patrón, documentado como fix WAITER-STORE-CRIT-01, eliminó una fuente significativa de problemas de rendimiento.

### El authStore: Identidad y Seguridad

El `authStore.ts` con sus más de 450 líneas gestiona todo lo relacionado con la identidad del usuario: credenciales, tokens de acceso, sucursal seleccionada, y estado de verificación de asignación. Su estado incluye `user`, `token`, `selectedBranchId`, `selectedBranchName`, las variantes `preLogin` de sucursal, `assignmentVerified`, y flags de control como `isLoading`, `error`, `isRefreshing`, y `refreshAttempts`.

La renovación de tokens implementa un mecanismo proactivo: cada catorce minutos, un minuto antes de que el token expire, la aplicación solicita automáticamente un nuevo token al servidor. Esta renovación ocurre en segundo plano, invisible para el mozo, que puede continuar trabajando sin interrupciones. El flag `isRefreshing`, introducido como fix HIGH-29-18, previene una condición de carrera donde múltiples componentes podrían disparar refresh simultáneos. Si un refresh ya está en progreso, las solicitudes subsiguientes esperan su resultado en lugar de iniciar nuevos intentos.

El contador `refreshAttempts` implementa el fix WAITER-CRIT-01: después de tres intentos fallidos consecutivos de refresh, el sistema ejecuta logout automático bajo la premisa de que algo está fundamentalmente mal con la sesión y continuar reintentando sería inútil. Este límite previene loops infinitos de refresh que consumirían recursos y confundirían al usuario.

El store también expone `setTokenRefreshCallback()`, un mecanismo para que el servicio WebSocket pueda registrar un callback que será invocado cuando el token se renueve. Esto permite que la conexión WebSocket actualice su token sin necesidad de reconexión completa.

La persistencia utiliza el middleware `persist` de Zustand con localStorage y un campo `partialize` que selecciona explícitamente qué campos persistir: `token`, `user`, `selectedBranchId`, y `availableBranches`. El refresh token ya no se persiste en localStorage siguiendo SEC-09.

### El tablesStore: El Corazón de la Aplicación

El `tablesStore.ts` con más de 900 líneas es el verdadero centro neurálgico de la aplicación. Mantiene el estado de todas las mesas visibles para el mozo y procesa los eventos en tiempo real que llegan desde el servidor.

El estado principal es el array `tables` de tipo `TableCard[]`, obtenido del endpoint `/api/waiter/tables?branch_id={id}`. Cada `TableCard` contiene información esencial: `table_id`, `code` (el identificador alfanumérico como "INT-01"), `status` (FREE, ACTIVE, PAYING, OUT_OF_SERVICE), `session_id` si hay sesión activa, `open_rounds` contando rondas pendientes de servir, `pending_calls` contando llamados de servicio activos, `check_status` para el estado de la cuenta, y campos de sector (`sector_id`, `sector_name`) para agrupación visual.

Además de los campos que vienen del servidor, cada tabla mantiene estado local para animaciones: `orderStatus` (el estado agregado de todas las rondas), `roundStatuses` (un Record que mapea IDs de ronda a sus estados individuales), y flags booleanos `statusChanged`, `hasNewOrder`, y `hasServiceCall` que controlan las animaciones visuales.

El store también gestiona `activeSession` de tipo `WaiterSessionSummary`, que almacena el resumen de la sesión activa cuando el mozo está en modo de gestión directa (Autogestión). Este campo se puebla mediante `fetchSessionSummary()` y se usa para mostrar información en el modal de pedidos.

### El Cálculo del Estado Agregado de Pedidos

Una mesa puede tener múltiples rondas de pedidos simultáneamente, cada una en un estado diferente del ciclo de vida. La primera ronda podría estar siendo servida mientras la segunda aún está en cocina y la tercera acaba de ser confirmada. Mostrar el estado de cada ronda individualmente en la tarjeta de mesa sería confuso, así que el store calcula un estado agregado mediante una lógica de priorización específica.

El estado `ready_with_kitchen` es particularmente importante. Aparece cuando al menos una ronda está lista para servir (`READY`) pero otras rondas aún están en proceso (pendientes, confirmadas, o en cocina). Este estado combinado, renderizado con un badge naranja y una animación de blink de cinco segundos, alerta al mozo de que hay items para recoger de cocina pero que habrá más por venir.

La prioridad completa de estados es: `ready_with_kitchen` (naranja) > `pending` (amarillo, requiere confirmación del mozo) > `confirmed` (azul, verificado pero no enviado a cocina) > `submitted`/`in_kitchen` (azul, en preparación) > `ready` (verde, todo listo) > `served` (gris, completado). El estado `none` indica ausencia de rondas activas.

### El retryQueueStore: Resiliencia Offline

El `retryQueueStore.ts` con aproximadamente 200 líneas implementa un patrón crucial para aplicaciones móviles: la cola de trabajo persistente. Cuando una operación falla debido a problemas de conectividad, se encola para reintento automático cuando la conexión se restablezca.

La cola soporta acciones específicas: `MARK_ROUND_SERVED`, `ACK_SERVICE_CALL`, `RESOLVE_SERVICE_CALL`, `CLEAR_TABLE`, y `SUBMIT_ROUND`. Cada acción encolada tiene un identificador único, el tipo de acción, el payload de datos, un timestamp de creación, y un contador de reintentos.

La deduplicación opera por combinación de tipo y ID de entidad. Si el mozo, frustrado por la falta de respuesta, pulsa el mismo botón varias veces, solo la primera acción se encola. Las subsiguientes se descartan silenciosamente al detectar que ya existe una acción del mismo tipo para la misma entidad.

El procesamiento de la cola ocurre automáticamente cuando el dispositivo detecta reconexión mediante el evento `online` del navegador. Las acciones se procesan en orden FIFO con un debounce de 100ms para evitar ráfagas. Si una acción falla con error de red, se incrementa su contador de reintentos y se mantiene para el próximo intento. Si falla con error de negocio (404, 403), se elimina porque reintentar sería inútil. Después de tres reintentos fallidos, la acción se descarta bajo la premisa de que algo está fundamentalmente mal.

El fix WAITER-STORE-CRIT-02 asegura que el listener del evento `online` se limpie correctamente cuando el store se desmonta, exportando una función `cleanupOnlineListener()` que los tests pueden invocar para evitar listeners huérfanos.

### El historyStore: Auditoría y Sincronización

El `historyStore.ts` con aproximadamente 190 líneas mantiene un registro de las últimas acciones realizadas por el mozo, útil tanto para auditoría como para debugging. Las entradas incluyen tipos como `ROUND_MARKED_SERVED`, `SERVICE_CALL_ACCEPTED`, y `SERVICE_CALL_COMPLETED`, junto con timestamps y metadatos relevantes.

La característica distintiva de este store es su sincronización entre pestañas mediante la API BroadcastChannel. Cuando el mozo tiene la aplicación abierta en múltiples pestañas o dispositivos, cada acción registrada se transmite a través del canal. Cualquier otra pestaña escuchando en el mismo canal recibe el mensaje y actualiza su estado.

El nombre del canal está definido en la constante `BROADCAST_CHANNEL_NAME = 'waiter-history-sync'`. La implementación incluye salvaguardas: verifica disponibilidad de la API antes de crear el canal, cierra el canal explícitamente en logout mediante `closeBroadcastChannel()` (fix CRIT-10 y QA-WAITER-HIGH-01), y mantiene la referencia al canal si el cierre falla para poder reintentar después (fix LOW-29-15). Un mount guard previene actualizaciones de estado después de que el componente se desmonta (fix WAITER-STORE-HIGH-02).

El historial está limitado a 100 entradas en modo FIFO para prevenir crecimiento ilimitado de memoria.

---

## Capítulo 3: La Capa de Servicios y sus Protecciones

### El Cliente API y la Defensa contra SSRF

El archivo `api.ts` con más de 400 líneas es mucho más que un simple wrapper alrededor de fetch. Es una capa de abstracción que implementa múltiples patrones de seguridad y resiliencia.

La primera línea de defensa es contra ataques SSRF (Server-Side Request Forgery). Aunque SSRF es típicamente un problema de servidores, un cliente web maliciosamente manipulado podría intentar hacer que el navegador del mozo realice requests a URLs internas. La configuración `API_CONFIG` define `ALLOWED_HOSTS` (localhost, 127.0.0.1) y `ALLOWED_PORTS` (80, 443, 8000, 8001, 5176, 5177, 5178), y toda URL base es validada contra estos valores antes de ejecutar cualquier request.

En producción, la validación es más estricta: bloquea acceso directo a direcciones IP (tanto IPv4 como IPv6), requiere match exacto de hostname sin wildcards de subdominios, y rechaza cualquier intento de alcanzar rangos de IP privados o servicios de metadata de cloud como 169.254.169.254. Si la validación falla, el sistema lanza una excepción inmediatamente, antes de que el request siquiera se intente.

### Timeouts y Control de Señales

El fix WAITER-SVC-MED-01 introdujo un sistema de timeout robusto basado en AbortController. Cada request tiene un timeout configurable (por defecto 30 segundos en `API_CONFIG.TIMEOUT`) después del cual es abortado automáticamente. La implementación es sofisticada: combina una señal externa opcional (para que el código que llama pueda cancelar) con una señal interna de timeout, usando `AbortSignal.any()` cuando está disponible o una implementación manual de fallback.

Esto previene que la aplicación quede colgada indefinidamente esperando respuesta de un servidor que no responde, y también permite que navegación o desmontaje de componentes cancelen requests en vuelo que ya no son necesarios.

### Las APIs Especializadas por Dominio

El archivo exporta múltiples objetos API agrupados por responsabilidad. El objeto `authAPI` agrupa login, getMe, refresh, y logout. Notablemente, el método `logout` pasa `false` como tercer argumento a `fetchAPI`, deshabilitando el retry automático en 401. Este detalle es crucial: si el token ya expiró y logout retorna 401, reintentar dispararía el callback de token expirado que llamaría logout nuevamente, creando un loop infinito. El fix está documentado como patrón anti-loop de logout.

El objeto `tablesAPI` agrupa las operaciones de consulta: `getTables(branchId)` retorna todas las mesas filtradas por los sectores asignados al mozo, `getTable(id)` retorna una mesa específica, y `getTableSessionDetail(id)` retorna el detalle completo de la sesión activa incluyendo diners, rondas con items, y estado de cuenta.

El objeto `roundsAPI` agrupa las operaciones sobre pedidos: `confirmRound(roundId)` para verificación del mozo, `markAsServed(roundId)` para marcar como entregado, `deleteItem(roundId, itemId)` para eliminar items de rondas no enviadas a cocina.

El objeto `serviceCallsAPI` proporciona `acknowledge(callId)` para indicar que el mozo vio el llamado, y `resolve(callId)` para marcarlo como atendido.

El objeto `waiterTableAPI` agrupa el flujo de mesa gestionada: `activateTable(tableId, {diner_count})` crea una sesión para una mesa libre, `submitRound(sessionId, {items})` envía un pedido, `requestCheck(sessionId)` solicita la cuenta, `registerManualPayment({check_id, amount_cents, manual_method})` registra pagos en efectivo u otros métodos, y `closeTable(tableId)` cierra la sesión.

El objeto `comandaAPI` proporciona `getMenuCompact(branchId)`, un endpoint optimizado que retorna el menú sin imágenes para la toma rápida de pedidos. Esta optimización reduce significativamente el tiempo de carga y el consumo de datos.

El objeto `billingAPI` agrupa `confirmCashPayment(checkId, amount)` y `clearTable(tableId)`.

Finalmente, `publicAPI.getBranches()` obtiene la lista de sucursales sin requerir autenticación, usado en el paso 1 del flujo de login.

### El Servicio WebSocket y su Resiliencia

La clase `WebSocketService` en `websocket.ts` con más de 400 líneas encapsula toda la complejidad de mantener una conexión WebSocket confiable. La URL de conexión es `/ws/waiter?token={token}` en el servidor de WebSocket (por defecto `ws://localhost:8001`).

El mecanismo de heartbeat envía un mensaje `{"type":"ping"}` cada 30 segundos (configurable en `WS_CONFIG.HEARTBEAT_INTERVAL`). Si el pong no llega en 10 segundos (`HEARTBEAT_TIMEOUT`), el servicio asume que la conexión está muerta y la cierra explícitamente. Esta detección proactiva es necesaria porque los WebSockets no siempre detectan automáticamente cuando la conexión se ha perdido, especialmente en redes móviles donde el dispositivo puede mantener una conexión aparentemente abierta que en realidad ya no funciona.

La reconexión automática implementa backoff exponencial con jitter. El primer reintento espera 1 segundo (`RECONNECT_INTERVAL`), el segundo espera 2 segundos más un componente aleatorio, el tercero espera 4 segundos más jitter, hasta un máximo de 30 segundos (`MAX_DELAY`). El jitter es crucial en producción: si el servidor se reinicia y cien clientes intentan reconectarse exactamente al mismo tiempo, el servidor puede sobrecargarse. Con jitter, los reintentos se distribuyen en el tiempo.

El límite de intentos está configurado en 50 (`MAX_RECONNECT_ATTEMPTS`). El fix RES-MED-01 agregó un callback `setOnMaxReconnectReached()` que notifica a la aplicación cuando se alcanza este límite, permitiendo mostrar un mensaje al usuario sugiriendo recargar la página.

Ciertos códigos de cierre indican errores no recuperables que no ameritan reintento. El código 4001 indica fallo de autenticación (token expirado o revocado), 4003 indica permisos insuficientes, y 4029 indica que se excedió el rate limit. Para estos códigos, definidos en `WS_CONFIG.NON_RECOVERABLE_CLOSE_CODES`, el servicio no programa más reintentos y notifica a la aplicación.

El fix WS-31-MED-02 agregó detección de cambio de visibilidad. Cuando el usuario cambia a otra aplicación o la pantalla se apaga, el navegador puede suspender la ejecución de JavaScript. Cuando el usuario vuelve y la página se hace visible nuevamente, el servicio verifica si la conexión sigue activa y, si no, inicia reconexión. Esto garantiza que el mozo que revisó su teléfono brevemente para algo personal puede volver a la aplicación y encontrarla funcionando.

El fix PWAW-A001 agregó tracking de expiración del JWT y scheduling de refresh. El servicio detecta cuándo el token está por expirar y puede invocar el callback de refresh proactivamente antes de que la conexión sea rechazada por token inválido.

---

## Capítulo 4: El Procesamiento de Eventos en Tiempo Real

### La Taxonomía de Eventos WebSocket

Los eventos WebSocket llegan como objetos JSON con una estructura consistente: `type` indica el tipo de evento, `branch_id` la sucursal, `table_id` la mesa afectada, `session_id` la sesión si aplica, y `entity` contiene datos específicos del evento como `round_id`, `call_id`, `check_id`, etc.

Los eventos del ciclo de vida de mesas incluyen `TABLE_SESSION_STARTED` (disparado cuando un comensal escanea el QR), `TABLE_STATUS_CHANGED` (cambios de estado de la mesa), y `TABLE_CLEARED` (sesión finalizada, mesa liberada).

Los eventos del ciclo de vida de rondas siguen el flujo completo: `ROUND_PENDING` (pedido nuevo esperando confirmación del mozo), `ROUND_CONFIRMED` (mozo verificó el pedido en la mesa), `ROUND_SUBMITTED` (enviado a cocina por admin/manager), `ROUND_IN_KITCHEN` (cocina comenzó preparación), `ROUND_READY` (cocina terminó), `ROUND_SERVED` (mozo entregó a la mesa), y `ROUND_CANCELED` (cancelado). El evento `ROUND_ITEM_DELETED` indica que el mozo eliminó un item de una ronda pendiente o confirmada.

Los eventos de llamados de servicio incluyen `SERVICE_CALL_CREATED` (cliente presionó el botón de llamado), `SERVICE_CALL_ACKED` (mozo indicó que vio el llamado), y `SERVICE_CALL_CLOSED` (mozo atendió y resolvió el llamado).

Los eventos de facturación incluyen `CHECK_REQUESTED` (cliente solicitó la cuenta), `CHECK_PAID` (pago confirmado), `PAYMENT_APPROVED` (pago específico aprobado), y `PAYMENT_REJECTED` (pago rechazado).

### El Handler de Eventos en el tablesStore

Cuando un evento llega a través del WebSocket, el store debe decidir qué hacer con él. El handler implementa una lógica ramificada extensa que procesa cada tipo de evento de manera apropiada.

Para eventos de ronda, el store primero verifica que el evento corresponda a una mesa en su lista. Esta verificación es crucial porque el WebSocket recibe eventos de toda la sucursal, pero el mozo solo debe reaccionar a eventos de sus sectores asignados. Si el evento es relevante, el store actualiza el campo `roundStatuses` con el nuevo estado de esa ronda específica, recalcula el `orderStatus` agregado de la mesa, actualiza contadores como `open_rounds`, y activa las animaciones correspondientes.

Para el evento `SERVICE_CALL_CREATED`, el store implementa deduplicación mediante un Set `seenServiceCallIds` que rastrea los IDs de llamados ya procesados. Esto es necesario porque el mismo llamado puede llegar múltiples veces si hay problemas de red o reconexiones. Sin deduplicación, el mozo podría recibir notificaciones repetidas. Además, el ID del llamado se agrega al array `activeServiceCallIds` de la mesa correspondiente, permitiendo que el UI muestre cuántos llamados activos hay y ofrezca botones individuales de resolución.

Para `SERVICE_CALL_ACKED` y `SERVICE_CALL_CLOSED`, el store remueve el ID del array `activeServiceCallIds` y decrementa el contador `pending_calls`.

Para `TABLE_CLEARED`, el store ejecuta un reset completo del estado de la mesa: establece status a FREE, limpia `session_id`, resetea todos los contadores a cero, limpia el array de llamados activos, y resetea el estado de órdenes. También limpia todos los timeouts de animación pendientes para esa mesa, previniendo que animaciones huérfanas intenten actualizar estado inexistente.

Para eventos que no modifican campos específicos conocidos, el store realiza un fetch de la mesa actualizada desde el servidor mediante `tablesAPI.getTable(tableId)`. Antes de aplicar los datos del servidor, preserva el estado de animación local (`statusChanged`, `hasNewOrder`, etc.) para que el feedback visual continúe hasta su timeout natural.

### El Sistema de Animaciones Temporales

Las animaciones visuales que alertan al mozo de cambios recientes requieren gestión cuidadosa de timeouts. El problema surge porque múltiples eventos pueden llegar para la misma mesa en rápida sucesión. Si cada evento programa un timeout independiente, pueden acumularse timeouts que se cancelan prematuramente o, peor, timeouts huérfanos que intentan actualizar estado después de que la mesa fue limpiada.

La solución implementada utiliza tres Maps separados: `statusBlinkTimeouts` para animaciones de cambio de estado (blink azul de 1.5 segundos), `newOrderTimeouts` para animaciones de nuevo pedido (pulse amarillo de 2 segundos), y `serviceCallTimeouts` para animaciones de llamado de servicio (blink rojo de 3 segundos). El estado `ready_with_kitchen` tiene su propia animación de blink naranja que dura 5 segundos.

Cuando llega un evento que requiere animación, el código primero verifica si ya existe un timeout activo para esa mesa en el Map correspondiente. Si existe, lo cancela mediante `clearTimeout()`. Luego programa un nuevo timeout con la duración configurada en `ANIMATION_DURATIONS`, almacena el ID del timeout en el Map con la mesa como clave, y activa el flag booleano correspondiente en el estado de la mesa. Cuando el timeout expira, el callback elimina la entrada del Map y desactiva el flag mediante una actualización de estado.

Este patrón garantiza que solo existe un timeout activo por mesa por tipo de animación, y que eventos rápidos sucesivos extienden la animación en lugar de crear múltiples instancias conflictivas.

---

## Capítulo 5: El Sistema de Notificaciones

### La Dualidad de Canales: Visual y Sonoro

El mozo no puede estar mirando su pantalla constantemente. Está en movimiento, llevando platos, recogiendo pedidos, interactuando con clientes. Las notificaciones deben ser capaces de captar su atención incluso cuando el teléfono está en su bolsillo o sobre una bandeja.

El servicio de notificaciones en `notifications.ts` con aproximadamente 250 líneas implementa dos mecanismos complementarios. Las notificaciones web utilizan la API de Notification del navegador para mostrar mensajes visuales incluso cuando la aplicación está en segundo plano. El sonido de alerta utiliza un elemento de audio HTML para reproducir `/sounds/alert.mp3`.

La estrategia combina ambos canales según la urgencia del evento. Los eventos definidos como urgentes en `URGENT_WS_EVENTS` (SERVICE_CALL_CREATED, CHECK_REQUESTED, PAYMENT_APPROVED, etc.) reproducen el sonido independientemente del estado de permisos de notificación. Este comportamiento, documentado como QA-FIX, garantiza que el mozo sea alertado audiblemente incluso si no ha otorgado permisos de notificación. Luego, si el permiso está disponible, también se muestra la notificación visual.

El sonido de alerta se carga de manera lazy: el elemento de audio se crea solo cuando se necesita por primera vez, con `preload='none'` para no consumir ancho de banda cargando un archivo que podría nunca usarse.

### Deduplicación y Control de Memoria

El fix WAITER-HIGH-02 introdujo un sistema de deduplicación basado en un Set `recentNotifications` que almacena tags de notificaciones recientes. Cada notificación tiene un tag derivado del tipo de evento y el ID de la entidad involucrada (por ejemplo, `SERVICE_CALL_CREATED:123`). Antes de mostrar una notificación, el servicio verifica si ese tag ya está en el Set. Si lo está, la notificación se descarta silenciosamente. Si no lo está, se añade al Set con un timeout de 5 segundos para su eliminación automática.

El fix WAITER-SVC-CRIT-03 abordó un problema de memory leak: el Set podía crecer indefinidamente si llegaban muchos eventos únicos. La solución implementa un límite de `MAX_RECENT_NOTIFICATIONS = 100` entradas. Cuando se alcanza el límite, el Set se vacía completamente mediante `clear()`. Este approach es más simple que implementar una cola FIFO y funciona bien en práctica porque el escenario de 100 notificaciones únicas en 5 segundos es extremadamente improbable.

### Contenido Contextual de las Notificaciones

Las notificaciones incluyen información específica que permite al mozo tomar decisiones sin necesidad de abrir la aplicación. El mapping de eventos a contenido es:

- `ROUND_SUBMITTED`: título "Nuevo Pedido", cuerpo con número de mesa
- `SERVICE_CALL_CREATED`: título "Llamado de Mesa", cuerpo incluye el tipo de llamado (BILL para cuenta, ASSISTANCE para asistencia, OTHER para otros)
- `CHECK_REQUESTED`: título "Cuenta Solicitada", cuerpo con número de mesa
- `ROUND_READY`: título "Pedido Listo", cuerpo indicando que hay items para recoger de cocina

Las notificaciones urgentes requieren interacción del usuario para cerrarse, mientras que las no urgentes se cierran automáticamente después de 5 segundos.

---

## Capítulo 6: La Interfaz de Usuario y sus Componentes

### El Grid de Mesas con Agrupación por Sector

El componente `TableGrid.tsx` ocupa la mayor parte de la pantalla principal, mostrando todas las mesas asignadas al mozo organizadas por sector. La agrupación visual presenta un header con el nombre del sector (por ejemplo, "Interior", "Terraza"), un badge con el conteo de mesas en ese sector, y un indicador pulsante rojo si alguna mesa del sector tiene urgencias (llamados activos o pedidos pendientes de confirmar).

Los filtros en la parte superior permiten enfocarse en subconjuntos de mesas: ALL muestra todas, URGENT muestra solo las que tienen llamados o pedidos pendientes, ACTIVE muestra solo las ocupadas, FREE muestra solo las disponibles, y OUT_OF_SERVICE muestra las inhabilitadas. El filtro seleccionado persiste en sessionStorage mediante el hook `usePersistedFilter`, así que si el mozo actualiza la página mantiene su contexto.

Dentro de cada sector, las mesas se ordenan por código alfanumérico. El componente `TableCard.tsx` renderiza cada mesa individual.

### Las Tarjetas de Mesa y sus Animaciones

Cada `TableCard` es un rectángulo compacto diseñado para uso táctil con una sola mano. El código de mesa (INT-01, TER-03) aparece prominentemente en el centro. El color de fondo indica el estado: verde para FREE, rojo para ACTIVE, morado para PAYING, gris para OUT_OF_SERVICE.

Los badges en la esquina superior derecha proporcionan información crítica de un vistazo: un badge verde muestra el conteo de `open_rounds` (rondas pendientes de servir), un badge rojo muestra `pending_calls` (llamados activos), y un badge morado con el texto "Cuenta" aparece si `check_status === 'REQUESTED'`.

Las clases de animación se determinan por prioridad. La función `getAnimationClass()` evalúa en orden:

1. Si `hasServiceCall` es true → clase `animate-service-call-blink` (blink rojo, 3 segundos)
2. Si `orderStatus === 'ready_with_kitchen'` → clase `animate-ready-kitchen-blink` (blink naranja, 5 segundos)
3. Si `statusChanged` es true → clase `animate-status-blink` (blink azul, 1.5 segundos)
4. Si `hasNewOrder` es true → clase `animate-new-order-pulse` (pulse amarillo, 2 segundos)
5. Si `check_status === 'REQUESTED'` → clase `animate-check-pulse` (pulse morado, continuo)

El badge de estado de pedido debajo del código de mesa muestra el `orderStatus` agregado con colores distintivos: amarillo para pending, azul para confirmed/submitted/in_kitchen, naranja para ready_with_kitchen, verde para ready, gris para served.

El fix WAITER-COMP-HIGH-01 agregó un aria-label descriptivo para accesibilidad, describiendo el estado completo de la mesa para lectores de pantalla.

### El Modal de Detalle de Mesa

Cuando el mozo toca una tarjeta de mesa, se abre `TableDetailModal.tsx` con más de 500 líneas de código. Este modal ocupa la mayor parte de la pantalla y presenta información detallada sobre la sesión activa.

Las pestañas de filtro en la parte superior permiten ver diferentes subconjuntos de rondas: "Todos" muestra todas las rondas, "Pendientes" filtra las que están en estado PENDING, CONFIRMED, SUBMITTED, o IN_KITCHEN, "Listos" muestra solo las READY, y "Servidas" muestra las SERVED.

La información de sesión incluye el listado de diners (comensales), las rondas agrupadas por categoría (Bebidas → Entradas → Principales → Postres), y el estado de cuenta con totales.

Las acciones disponibles dependen del estado de cada ronda:

- Para rondas en estado `PENDING`: aparece un botón prominente "Confirmar Pedido" que el mozo pulsa después de verificar físicamente el pedido en la mesa. Esta verificación es un paso crítico del flujo que previene que pedidos erróneos lleguen a cocina.

- Para rondas en estado `PENDING` o `CONFIRMED` (no enviadas a cocina): cada item individual tiene un ícono de papelera que permite eliminarlo. Un diálogo de confirmación previene eliminaciones accidentales. Si la eliminación deja la ronda vacía, la ronda completa se elimina automáticamente.

- Para rondas en estado `READY`: aparece un botón "Marcar como servido" que el mozo pulsa después de entregar los platos a la mesa.

La sección de llamados de servicio muestra los IDs de llamados activos almacenados en `activeServiceCallIds`, con un botón "Resolver" para cada uno que invoca `serviceCallsAPI.resolve()`.

El modal también incluye la pestaña `ComandaTab` para toma de pedidos rápida y un botón para abrir `FiscalInvoiceModal` si hay items consumidos.

El modal se actualiza en tiempo real mediante listeners de eventos WebSocket que recargan los datos cuando llegan eventos relevantes (ROUND_*, SERVICE_CALL_*, CHECK_*, PAYMENT_*). La gestión de foco restaura el elemento anteriormente enfocado al cerrar el modal, y la tecla Escape lo cierra.

### El Modal de Autogestión

El componente `AutogestionModal.tsx` con aproximadamente 300 líneas implementa el flujo de toma de pedidos gestionado directamente por el mozo. Este flujo es esencial para clientes que prefieren no usar sus teléfonos.

El modal opera en dos pasos. El primer paso presenta una lista de mesas FREE y ACTIVE. Para mesas FREE, el mozo ingresa la cantidad de comensales y el sistema crea una sesión mediante `waiterTableAPI.activateTable()`. Para mesas ACTIVE, simplemente usa la sesión existente.

El segundo paso presenta una interfaz split-view optimizada para velocidad. El panel izquierdo muestra el menú compacto obtenido de `comandaAPI.getMenuCompact()` (sin imágenes), organizado por categorías con un campo de búsqueda rápida. El mozo navega las categorías, busca productos por nombre, y los agrega al carrito con un toque.

El panel derecho muestra el carrito actual con controles de cantidad (+/-), el total acumulado, y un botón de envío. Al enviar, el sistema invoca `waiterTableAPI.submitRound()` y el pedido entra al flujo normal con estado PENDING.

### El Tab de Comanda Rápida

El componente `ComandaTab.tsx` con aproximadamente 250 líneas proporciona la misma funcionalidad de toma de pedidos pero integrado dentro del `TableDetailModal`. Esto permite que el mozo que ya está viendo el detalle de una mesa pueda agregar items sin necesidad de abrir otro modal.

La implementación incluye un mount guard (`isMounted` flag) que previene actualizaciones de estado después de que el componente se desmonta, evitando el warning de React sobre memory leaks en efectos asíncronos.

### Los Componentes de Factura Fiscal

Los componentes `FiscalInvoice.tsx` y `FiscalInvoiceModal.tsx` implementan la generación de facturas fiscales en formato argentino AFIP. Esta funcionalidad es una simulación para demostración; la integración real con AFIP requeriría certificados y comunicación con los servidores de la autoridad fiscal.

El componente `FiscalInvoice` renderiza una factura A4 (210mm × 297mm) con todos los elementos requeridos: header del negocio con nombre, CUIT, condición tributaria, y datos de contacto; badge del tipo de factura (A, B, o C según el tipo de cliente); tabla de items con cantidad, descripción, precio unitario, y total por línea; subtotal, tasa de IVA, monto de IVA, y total; número de CAE (simulado) y código QR placeholder; y método de pago utilizado.

El modal `FiscalInvoiceModal` envuelve la factura con un preview y un botón "Descargar PDF". La exportación a PDF utiliza las bibliotecas `jspdf` y `html2canvas`: primero convierte el elemento DOM de la factura a canvas, luego lo embebe en un documento PDF que se descarga automáticamente.

Los tipos están definidos en `types/fiscal.ts`, incluyendo enums para `InvoiceType` (A, B, C) y `TaxCondition` (RESPONSABLE_INSCRIPTO, MONOTRIBUTO, CONSUMIDOR_FINAL, etc.), junto con helpers como `formatCuit()` para formatear el número de identificación tributaria.

---

## Capítulo 7: Los Hooks Personalizados

### usePullToRefresh: Gestos Táctiles

El hook `usePullToRefresh.ts` encapsula toda la lógica del gesto de arrastrar hacia abajo para refrescar. El mozo arrastra desde el inicio de la lista, un indicador visual muestra el progreso hacia el umbral de activación, y al soltar después del umbral se dispara la función de refresh.

El hook maneja los eventos táctiles (`touchstart`, `touchmove`, `touchend`), calcula las distancias considerando el scroll actual del contenedor, gestiona la resistencia del arrastre (se hace más difícil cuanto más se arrastra), y proporciona estados para que el componente renderice feedback apropiado.

El indicador de pull-to-refresh anuncia su estado a lectores de pantalla mediante una región aria-live, garantizando accesibilidad para usuarios con discapacidad visual.

### usePWA: Instalación de la Aplicación

El hook `usePWA.ts` gestiona el ciclo de vida de la PWA. Detecta el evento `beforeinstallprompt` que el navegador emite cuando la aplicación cumple los criterios para ser instalable, almacena el evento para invocarlo cuando el usuario esté listo, y expone funciones para mostrar el prompt de instalación y verificar si la aplicación ya está instalada.

También expone el estado `needRefresh` que indica cuando hay una nueva versión disponible del Service Worker, y la función `updateServiceWorker()` que fuerza la activación inmediata y recarga la página.

### usePersistedFilter: Estado Persistente de Filtros

El hook `usePersistedFilter.ts` gestiona filtros que deben sobrevivir recargas de página. Utiliza sessionStorage para persistencia dentro de la sesión del navegador, permitiendo que el mozo que actualiza la página mantenga su filtro de mesas seleccionado.

### useOnlineStatus: Detección de Conectividad

El hook `useOnlineStatus.ts` expone un booleano que indica si el dispositivo tiene conexión de red. Escucha los eventos `online` y `offline` del navegador y actualiza el estado reactivamente, permitiendo que la UI muestre banners de advertencia cuando se pierde conectividad.

---

## Capítulo 8: La Configuración PWA y el Service Worker

### El Manifiesto de Aplicación

El archivo `manifest.json` generado por vite-plugin-pwa describe la aplicación para el sistema operativo. Define el nombre completo "Sabor - Panel de Mozo" y el nombre corto "Mozo", el modo de visualización standalone (sin barra de navegación del navegador), la orientación portrait preferida, el color de tema naranja #f97316, y los íconos en resoluciones 192x192 y 512x512 para diferentes contextos de uso.

Los shortcuts permiten acciones rápidas desde el ícono en la pantalla de inicio: "Ver Mesas" navega a la raíz, y "Mesas Urgentes" navega con el filtro de urgentes preseleccionado.

Las screenshots proporcionan previews para el diálogo de instalación en dispositivos compatibles, con versiones wide y narrow para diferentes orientaciones.

### Las Estrategias de Caché de Workbox

El Service Worker generado implementa múltiples estrategias de caché según el tipo de recurso.

Los assets estáticos (HTML, CSS, JavaScript, imágenes del bundle) se pre-cachean durante la instalación del Service Worker. Esto significa que se descargan todos de una vez y se sirven desde caché en visitas subsiguientes, resultando en tiempos de carga casi instantáneos.

Las fuentes de Google utilizan estrategia CacheFirst con expiración de 365 días. Una vez descargada una fuente, se sirve desde caché indefinidamente.

Las llamadas a `/api/waiter/tables*` utilizan estrategia NetworkFirst con timeout de 5 segundos y caché de respaldo de 1 hora. Esto prioriza datos frescos pero permite funcionalidad degradada si la red falla.

Las imágenes de productos utilizan estrategia CacheFirst con expiración de 7 días. Las imágenes se descargan una vez y se sirven rápidamente desde caché, refrescándose semanalmente.

El fallback de navegación está configurado en `/index.html` con una denylist para rutas que comienzan con `/api`, asegurando que las rutas de API no sean interceptadas por el Service Worker.

### Detección y Aplicación de Actualizaciones

Cuando se despliega una nueva versión de la aplicación, el Service Worker nuevo se descarga pero permanece en estado "waiting" hasta que todas las pestañas de la aplicación se cierren. El hook `usePWA` expone `needRefresh: true` cuando esto ocurre, permitiendo que la UI muestre un banner invitando al usuario a actualizar.

La función `updateServiceWorker()` fuerza la activación inmediata del nuevo Service Worker mediante `skipWaiting()` y recarga todas las pestañas. Esto garantiza que el usuario siempre termina con todas sus pestañas en la misma versión del código, evitando inconsistencias.

---

## Capítulo 9: El Sistema de Logging y Observabilidad

### Loggers Contextuales

El archivo `logger.ts` implementa un sistema de logging estructurado con contextos. La función `createLogger(context)` retorna un objeto con métodos `debug`, `info`, `warn`, y `error`, cada uno prefijando los mensajes con timestamp, nivel, y contexto.

Los contextos definidos incluyen:

- `apiLogger = createLogger('API')` para mensajes relacionados con llamadas REST
- `wsLogger = createLogger('WebSocket')` para mensajes de conexión y eventos
- `authLogger = createLogger('Auth')` para flujo de autenticación y tokens
- `storeLogger = createLogger('Store')` para cambios de estado en Zustand
- `notificationLogger = createLogger('Notification')` para el sistema de alertas

El nivel `debug` solo produce output en desarrollo (`import.meta.env.DEV`), permitiendo logging verboso durante desarrollo sin contaminar la consola de producción.

El formato de salida es `[timestamp] [LEVEL] [context] message data`, donde data es el objeto opcional serializado como JSON para facilitar inspección.

---

## Capítulo 10: Testing y Calidad de Código

### Configuración de Vitest

La configuración de testing utiliza Vitest integrado con Vite. El archivo `vite.config.ts` incluye la sección de test que especifica `globals: true` para acceso global a funciones de test, `environment: 'jsdom'` para simular un DOM de navegador, y `setupFiles: ['./src/test/setup.ts']` para configuración inicial.

El archivo `setup.ts` configura mocks globales para APIs del navegador no disponibles en jsdom, como `localStorage`, `sessionStorage`, `BroadcastChannel`, y la API de Notification.

### Archivos de Test Existentes

El proyecto incluye tests para los tres stores principales:

- `authStore.test.ts` verifica el flujo de login, la verificación de asignación, el refresh de tokens, y el logout correcto.

- `tablesStore.test.ts` verifica el procesamiento de eventos WebSocket, el cálculo del estado agregado de pedidos, y la gestión de animaciones.

- `retryQueueStore.test.ts` verifica la deduplicación de acciones, el procesamiento de la cola, y la limpieza de listeners.

Los tests utilizan React Testing Library para renderizado de componentes y `vi.fn()` para mocking de funciones.

---

## Capítulo 11: El Flujo Completo de Pedidos

### La Verificación como Paso Crítico

El sistema de pedidos implementa un flujo deliberadamente conservador donde los pedidos de clientes no llegan directamente a cocina. En lugar de eso, pasan primero por verificación del mozo, luego por aprobación del manager o admin. Esta cascada de validaciones responde a problemas reales observados en restaurantes.

Cuando un cliente envía un pedido desde pwaMenu, este llega con estado PENDING. El evento `ROUND_PENDING` se propaga a través del WebSocket y aparece en el dispositivo del mozo como una alerta de nuevo pedido (pulse amarillo). El mozo ve qué mesa tiene el pedido, va a verificarlo físicamente, y puede ajustar cantidades o eliminar items si el cliente cambió de opinión. Una vez satisfecho, pulsa "Confirmar Pedido" en el `TableDetailModal` y el estado cambia a CONFIRMED.

Solo después de esta confirmación, el administrador o manager puede ver el pedido en el Dashboard y enviarlo a cocina, cambiando el estado a SUBMITTED. Este segundo paso existe para dar control adicional al management sobre cuándo se liberan pedidos a cocina, permitiendo por ejemplo agrupar pedidos de varias mesas para optimizar la producción.

Cuando cocina comienza la preparación, el estado cambia a IN_KITCHEN. Cuando termina, cambia a READY. El mozo recibe notificación sonora de que hay items listos para recoger. Después de entregar los platos, marca el pedido como SERVED.

### El Flujo Alternativo de Autogestión

Para clientes que prefieren servicio tradicional, el mozo utiliza el modal de Autogestión. Activa una mesa libre ingresando la cantidad de comensales, navega el menú compacto agregando items al carrito, y envía el pedido. Este pedido entra al mismo flujo con estado PENDING, pero todo el proceso ocurre desde el dispositivo del mozo sin intervención del cliente.

Esta dualidad garantiza que el sistema no excluye a ningún tipo de cliente. Un restaurante puede tener mesas con códigos QR para clientes tech-savvy, y mesas tradicionales atendidas completamente por mozos. El backend maneja ambos flujos de manera unificada, y las métricas de tiempo de servicio capturan ambas modalidades.

---

## Capítulo 12: Capacidades Offline y Resiliencia

### El Problema de la Conectividad Intermitente

Los restaurantes no son data centers. La señal WiFi puede ser débil en ciertas áreas del salón. Las paredes gruesas de edificios antiguos pueden bloquear señales. Los dispositivos móviles de gama baja pueden tener receptores WiFi deficientes. Y durante horas pico, la congestión de red puede causar timeouts y paquetes perdidos.

Una aplicación que simplemente fallara cuando pierde conectividad sería inutilizable en este ambiente. El mozo no puede quedarse paralizado esperando que la red funcione mientras los clientes esperan.

### La Estrategia de Caché y Cola

pwaWaiter implementa dos estrategias complementarias. La primera es el caché de estado: el Service Worker con estrategia NetworkFirst permite que la lista de mesas se sirva desde caché cuando el servidor no responde, con un indicador visual de que los datos pueden estar desactualizados.

La segunda estrategia es la cola de reintentos del `retryQueueStore`. Cuando el mozo intenta realizar una acción como marcar un pedido como servido y la llamada API falla por problemas de red, la acción se encola automáticamente. La cola se persiste en localStorage, así que sobrevive incluso si el mozo cierra la aplicación. Cuando el dispositivo detecta reconexión mediante el evento `online`, procesa la cola automáticamente, ejecutando las acciones en el orden en que fueron encoladas.

### Limitaciones del Modo Offline

Es importante notar que el modo offline tiene limitaciones. La aplicación no proporciona una experiencia completa offline de solo lectura; el caché de Workbox ayuda con assets estáticos y algunas respuestas de API, pero no hay sincronización completa de datos para visualización offline. Las acciones se encolan para retry pero no se ejecutan localmente con sincronización posterior.

Tampoco hay un diálogo de solicitud de permisos de notificación; el sistema simplemente solicita permisos en el momento del login, lo cual puede fallar silenciosamente si el navegador rechaza la solicitud.

---

## Capítulo 13: Seguridad y Validaciones

### Protección SSRF en el Cliente

El cliente API implementa validación estricta de URLs para prevenir que código malicioso pueda redirigir requests a servidores no autorizados. La configuración `API_CONFIG` define explícitamente los hosts permitidos (localhost, 127.0.0.1 en desarrollo) y los puertos permitidos (80, 443, 8000, 8001, y los puertos de las aplicaciones frontend).

En producción, la validación es más estricta: bloquea acceso directo a direcciones IP para forzar el uso de hostnames verificados, rechaza cualquier intento de alcanzar rangos de IP privados (10.x, 172.16-31.x, 192.168.x), y previene acceso a endpoints de metadata de cloud como 169.254.169.254 que podrían exponer credenciales.

### Manejo Seguro de Tokens

Los tokens JWT de acceso tienen vida corta de 15 minutos para limitar el daño potencial si son comprometidos. El refresh token, con vida de 7 días, se almacena en una cookie HttpOnly que el JavaScript no puede leer, protegiéndolo de ataques XSS.

El mecanismo de refresh proactivo renueva el token un minuto antes de su expiración, evitando interrupciones de servicio. El flag `isRefreshing` previene race conditions donde múltiples componentes podrían disparar refreshes simultáneos. El contador de intentos fallidos limita a 3 retries antes de forzar logout, previniendo loops infinitos.

### Headers de Seguridad

Aunque los headers de seguridad son responsabilidad del backend, vale la pena mencionar que el servidor responde con X-Content-Type-Options: nosniff para prevenir sniffing de MIME types, X-Frame-Options: DENY para prevenir clickjacking, Content-Security-Policy restrictivo, y HSTS en producción para forzar HTTPS.

---

## Conclusión: Una Herramienta que Extiende al Profesional

pwaWaiter no pretende reemplazar al mozo humano sino potenciarlo. El juicio del profesional sobre cómo atender a cada cliente, cuándo ofrecer recomendaciones, cómo manejar situaciones difíciles: eso sigue siendo insustituiblemente humano. Lo que la aplicación hace es liberar ancho de banda mental, permitiendo que el mozo dedique su atención a lo que realmente importa en lugar de gastarla en recordar qué mesas tienen pedidos pendientes.

La arquitectura técnica refleja esta filosofía. El estado derivado garantiza que la información mostrada siempre es coherente con la realidad. Los eventos en tiempo real mantienen al mozo informado sin requerir que constantemente refresque la pantalla. Las capacidades offline garantizan que un problema de red no paraliza el servicio. La verificación de pedidos pone al mozo en control del flujo hacia cocina. Las facturas fiscales permiten cumplimiento tributario sin hardware adicional.

El código está diseñado para ser mantenible y extensible. Los stores de Zustand con selectores estables encapsulan la lógica de dominio de manera clara. Los servicios de comunicación implementan patrones robustos de resiliencia con timeouts, retries, y deduplicación. Los hooks personalizados extraen comportamiento reutilizable. Los componentes de UI son pequeños y enfocados. Los tests de Vitest verifican el comportamiento crítico. El sistema de logging proporciona observabilidad para debugging en producción.

React 19 con sus hooks de optimismo y transiciones permite interfaces que responden instantáneamente a las acciones del usuario mientras las operaciones de red se resuelven en segundo plano. Zustand 5 con persist middleware mantiene el estado entre sesiones sin la complejidad de Redux. Vite 7 con PWA plugin genera una aplicación instalable que carga en milisegundos.

Y sobre todo, la aplicación está diseñada para desaparecer. El mejor software de productividad es el que se vuelve invisible, que el usuario opera sin pensar porque sus controles son intuitivos y sus respuestas predecibles. pwaWaiter aspira a ser ese tipo de herramienta: algo que el mozo usa naturalmente como extensión de sí mismo, que amplifica sus capacidades sin interponerse en su trabajo.

---

*Documento técnico narrativo del proyecto pwaWaiter. Última actualización: Febrero 2026.*
