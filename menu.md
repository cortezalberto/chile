# pwaMenu: La Mesa Digital

## Introducción: El Problema de las Cartas Tradicionales

Imagina un grupo de amigos sentados en un restaurante, pasándose una carta de mano en mano, esperando turnos para ver los platos mientras el mozo aguarda pacientemente. Uno quiere verificar ingredientes por alergias, otro busca opciones vegetarianas, y un tercero simplemente quiere ver las fotos de los postres. Este ritual, tan familiar como ineficiente, representa exactamente el problema que pwaMenu resuelve.

La aplicación de menú para clientes es una PWA (Progressive Web App) que transforma cada teléfono móvil en una extensión de la carta del restaurante. Pero a diferencia de un simple catálogo digital, pwaMenu introduce un concepto revolucionario: el carrito compartido. En lugar de que cada comensal haga pedidos individuales, todos los dispositivos en una mesa comparten el mismo espacio de trabajo virtual, creando una experiencia verdaderamente colaborativa que respeta la naturaleza social de compartir una comida.

Esta arquitectura de "sesión compartida" presenta desafíos técnicos únicos. Cuando cinco personas miran el mismo carrito desde cinco dispositivos diferentes, ¿cómo se garantiza que todos vean exactamente lo mismo? ¿Cómo se previene que dos personas modifiquen la misma cantidad simultáneamente? ¿Y cómo se maneja la confirmación grupal para enviar un pedido cuando no todos están listos al mismo tiempo? Las respuestas a estas preguntas definen la arquitectura de pwaMenu, una aplicación construida sobre React 19, Zustand 5 y Vite 7, aprovechando las capacidades más recientes del ecosistema JavaScript para crear experiencias fluidas y resilientes.

---

## Capítulo 1: Fundamentos Tecnológicos

### React 19 y el Paradigma de Actualizaciones Optimistas

pwaMenu se construye sobre React 19.2.0, la versión más reciente del framework que introduce cambios paradigmáticos en el manejo de estados asíncronos. El hook `useOptimistic` permite mostrar cambios instantáneamente en la interfaz mientras las operaciones de red se resuelven en segundo plano. Cuando un comensal añade una hamburguesa al carrito, no espera confirmación del servidor: el item aparece inmediatamente. Si el servidor eventualmente rechaza la operación, el sistema revierte automáticamente al estado anterior sin intervención manual.

El hook `useTransition` complementa esta arquitectura permitiendo marcar actualizaciones como "no urgentes", evitando que cálculos costosos bloqueen la interacción del usuario. Cuando el menú carga cientos de productos, las operaciones de filtrado y ordenamiento se ejecutan sin congelar el scroll ni los botones táctiles.

El hook `useActionState`, introducido en React 19, transforma el manejo de formularios. En lugar de múltiples estados para loading, error y data, el hook encapsula todo el ciclo de vida de una acción asíncrona. Los componentes `ProductDetailModal`, `CallWaiterModal` y `JoinTable` utilizan este patrón para manejar envíos de formularios con feedback automático de estado pendiente.

El compilador de React, integrado mediante babel-plugin-react-compiler, automatiza la memoización de componentes y callbacks. Esta optimización elimina la necesidad de envolver manualmente cada componente en `React.memo` o cada callback en `useCallback`, reduciendo significativamente el código boilerplate y los errores humanos asociados a optimizaciones manuales incorrectas.

### Zustand 5 y la Gestión de Estado Modular

Para la gestión del estado global, la aplicación emplea Zustand en su versión 5.0.9. Esta biblioteca representa una alternativa minimalista a Redux que elimina la verbosidad característica de los patrones flux tradicionales. Un store de Zustand se define mediante una única función que retorna el estado inicial y las acciones que lo modifican, sin necesidad de reducers, action creators o middleware externos.

La arquitectura de stores en pwaMenu sigue un patrón modular riguroso. El **tableStore** gestiona toda la lógica relacionada con la sesión de mesa, el carrito compartido y los pedidos, organizado en cuatro archivos especializados: `store.ts` para las acciones principales, `types.ts` para las interfaces TypeScript, `selectors.ts` para los selectores optimizados, y `helpers.ts` para funciones puras de utilidad. El **menuStore** mantiene el catálogo de productos con caché temporal de cinco minutos. El **sessionStore** maneja la conexión con el backend y la persistencia de tokens. El **serviceCallStore** rastrea las llamadas al mozo con selectores memoizados.

Cada store implementa persistencia automática mediante el middleware `persist` de Zustand, que serializa el estado a localStorage y lo rehidrata al cargar la aplicación. Esta característica permite que un comensal cierre accidentalmente el navegador y, al reabrirlo, encuentre su sesión exactamente donde la dejó, con su carrito intacto y su identidad preservada.

### Vite 7 y la Arquitectura de Empaquetado

Vite 7.2.4 actúa como el corazón del sistema de construcción, proporcionando un servidor de desarrollo con recarga instantánea y un proceso de build optimizado para producción. Su arquitectura basada en módulos ES nativos durante el desarrollo elimina la necesidad de empaquetar el código completo en cada cambio, resultando en tiempos de recarga medidos en milisegundos.

La configuración de producción implementa división de código estratégica mediante chunks manuales. Las dependencias de terceros se agrupan en un chunk `vendor` que cambia infrecuentemente y puede cachearse agresivamente. Las traducciones se separan en un chunk `i18n` que solo se descarga cuando el usuario cambia de idioma. Los componentes modales pesados como el chat de IA o los filtros avanzados residen en sus propios chunks, descargándose bajo demanda únicamente cuando el usuario los requiere.

El plugin vite-plugin-pwa transforma la aplicación en una Progressive Web App completa, generando automáticamente el service worker, el manifiesto de aplicación y los iconos en múltiples resoluciones. La configuración define comportamientos de caché diferenciados según el tipo de recurso: las imágenes de productos emplean estrategia CacheFirst con expiración de 30 días, mientras que las llamadas a API utilizan NetworkFirst con timeout de 5 segundos y fallback a caché.

---

## Capítulo 2: El Viaje del Comensal

### La Llegada a la Mesa

El primer contacto del comensal con pwaMenu ocurre a través de un código QR pegado en la mesa. Este simple escaneo desencadena una orquestación compleja que el usuario nunca percibe. El código contiene un identificador alfanumérico de la mesa (como "INT-01" o "TER-02") que la aplicación utiliza para conectarse con el backend y obtener o crear una sesión activa.

El componente `JoinTable` maneja este flujo inicial mediante un proceso de dos pasos implementado como wizard modular. El subdirectorio `JoinTable/` contiene `TableNumberStep.tsx` para la confirmación del número de mesa y `NameStep.tsx` para el ingreso opcional del nombre del comensal. Esta arquitectura modular facilita extensiones futuras como verificación de edad para locales nocturnos o selección de idioma preferido.

Primero, el usuario ve su número de mesa pre-poblado desde el QR y lo confirma. Luego, opcionalmente, ingresa su nombre para identificarse ante los demás comensales. Esta información viaja al backend a través del endpoint `/api/tables/code/{code}/session?branch_slug={slug}`, que responde con un **table token**, un JWT especializado con tiempo de vida de tres horas que autoriza todas las operaciones posteriores de ese comensal en esa mesa específica.

Lo notable de este diseño es su tolerancia a la ambigüedad. Los códigos de mesa no son únicos globalmente: cada sucursal puede tener su propia "INT-01". Por eso, la aplicación siempre envía el slug de la sucursal junto con el código de mesa, permitiendo al backend resolver la mesa correcta sin confusiones. Este pequeño detalle arquitectónico previene errores sutiles que serían devastadores en producción, donde un pedido enviado a la mesa equivocada destruiría la experiencia del usuario.

### El Sistema de Identificación de Dispositivo

Antes de que el árbol de componentes React se monte, el archivo `main.tsx` ejecuta una inicialización crítica: la generación del identificador único de dispositivo. Este proceso ocurre de manera asíncrona para no bloquear el renderizado inicial, pero establece las bases para el sistema de fidelización que operará durante toda la sesión.

El módulo `deviceId.ts` genera dos identificadores complementarios. El `deviceId` es un UUID v4 simple generado mediante `crypto.randomUUID()` y almacenado en localStorage. Persiste entre sesiones del navegador mientras el usuario no limpie sus datos de navegación. Su simplicidad lo hace robusto pero vulnerable a pérdida si el usuario cambia de dispositivo o limpia datos.

El `deviceFingerprint` complementa al deviceId con una huella digital más sofisticada. Se computa un hash SHA-256 combinando características del navegador: user agent completo, resolución de pantalla y profundidad de color, zona horaria del sistema y preferencia de idioma, plataforma del sistema operativo, cantidad de memoria RAM disponible y núcleos de CPU, número máximo de puntos táctiles soportados. Esta combinación genera un identificador relativamente único que puede ayudar a reconocer el mismo dispositivo incluso si el localStorage se limpia.

La función `getDeviceInfo()` retorna ambos identificadores empaquetados, listos para enviarse al backend cuando el comensal se registra en una mesa. La función `isReturningDevice()` verifica si el dispositivo actual ha visitado anteriormente, permitiendo personalización desde el primer momento de la sesión.

### El Catálogo Vivo

Una vez dentro de la sesión, el comensal accede al menú completo del restaurante a través de la página `Home.tsx`. Pero este no es un simple catálogo estático. El `menuStore` mantiene una representación local del menú que se actualiza dinámicamente y se cachea inteligentemente para evitar peticiones redundantes.

El menú se obtiene del endpoint `/api/public/menu/{slug}` que retorna la estructura completa de categorías, subcategorías, productos y alérgenos de la sucursal. Cada producto llega con información estructurada: nombre y descripción en múltiples idiomas, imagen, alérgenos asociados con nivel de presencia, perfiles dietéticos (vegano, vegetariano, sin gluten), métodos de cocción, y precios específicos de la sucursal.

La conversión de datos merece atención especial. El backend almacena precios en centavos (12550 representa $125.50) para evitar errores de punto flotante inherentes a la representación binaria de decimales, pero el frontend los presenta en pesos con decimales para la comodidad del usuario. Las funciones de conversión en `Home.tsx` (`convertBackendProduct`, `convertBackendCategory`, `convertBackendSubcategory`) transforman los tipos del backend (snake_case, IDs numéricos, precios en centavos) a los tipos del frontend (camelCase, IDs string, precios decimales).

El sistema de caché implementa una política TTL (Time To Live) de cinco minutos que balancea frescura contra eficiencia. Un menú obsoleto por más tiempo podría mostrar productos descontinuados, pero refrescar constantemente consumiría datos innecesarios. El flag `lastFetch` registra el timestamp de la última obtención, y el método `fetchMenu` con parámetro `forceRefresh` permite invalidación manual del caché cuando es necesario.

---

## Capítulo 3: Los Filtros como Herramientas de Inclusión

### El Desafío de las Restricciones Alimentarias

En cualquier grupo de comensales, las necesidades dietéticas varían enormemente. Uno puede ser celíaco, otro intolerante a la lactosa, y un tercero simplemente prefiere evitar frituras. Los sistemas tradicionales de filtrado ofrecen checkboxes binarios que ocultan productos, pero pwaMenu va mucho más allá con un sistema de filtrado sofisticado que reconoce la complejidad real de las restricciones alimentarias.

El hook `useAllergenFilter` representa esta sofisticación. No solo permite excluir alérgenos específicos, sino que distingue entre diferentes niveles de presencia. Un producto puede "contener" un alérgeno (presente como ingrediente declarado), "poder contenerlo" (trazas por contaminación cruzada en la cocina), o estar "libre de" él (garantizado sin presencia, procesado en ambiente controlado).

El usuario puede elegir entre tres niveles de restricción: modo **permisivo** que solo marca pero no excluye productos con el alérgeno, modo **moderado** que oculta productos donde el alérgeno es ingrediente pero permite aquellos con posibles trazas mostrando advertencia, y modo **estricto** que excluye cualquier producto con presencia confirmada o posible del alérgeno. Esta última opción es vital para personas con alergias severas donde incluso mínimas exposiciones representan riesgos médicos de anafilaxis.

### Las Reacciones Cruzadas: Una Dimensión Oculta

La verdadera innovación del sistema de filtrado reside en su comprensión de las reacciones cruzadas entre alérgenos. El síndrome látex-fruta ilustra perfectamente este fenómeno: una persona alérgica al látex frecuentemente también reacciona a plátanos, aguacates, kiwis y castañas debido a proteínas estructuralmente similares. El síndrome de alergia oral relaciona el polen de abedul con manzanas, peras y cerezas. Estas conexiones no son obvias para el comensal promedio, pero ignorarlas puede tener consecuencias médicas serias.

El sistema obtiene del backend un grafo de reacciones cruzadas almacenado en el modelo `AllergenCrossReaction`, una relación self-referencial many-to-many que conecta alérgenos relacionados con probabilidades asociadas (alta, media, baja) y descripción de la relación. El hook `useAllergenFilter` permite al usuario configurar su sensibilidad a estas conexiones. Alguien con alergias leves podría considerar solo reacciones de alta probabilidad, mientras que alguien con historial de anafilaxis querrá incluir todas las conexiones conocidas.

El resultado es un filtrado que va más allá de lo que el usuario conscientemente sabe sobre sus alergias. Cuando un comensal marca "alergia al maní", el sistema puede advertirle sobre productos con otros frutos secos que frecuentemente causan reacciones cruzadas, protegiéndolo proactivamente.

### Preferencias Dietéticas y Métodos de Cocción

El hook `useDietaryFilter` complementa el sistema de alérgenos con preferencias de estilo de vida. Las opciones incluyen vegetariano (sin carne pero permite lácteos y huevos), vegano (sin ningún producto animal), sin gluten (excluye trigo, cebada, centeno), apto para celíacos (sin gluten más garantía de no contaminación cruzada), keto (bajo en carbohidratos), y bajo en sodio. Cada opción representa no solo una restricción sino una forma de relacionarse con la comida.

La implementación requiere que el producto satisfaga todas las opciones seleccionadas simultáneamente mediante operador lógico AND, reconociendo que una persona puede ser tanto vegetariana como intolerante al gluten. Los productos se filtran contra los atributos booleanos correspondientes almacenados en el modelo de producto.

Similarmente, `useCookingMethodFilter` permite excluir métodos de preparación específicos. Un usuario que evita frituras por razones de salud puede configurar el filtro una vez y olvidarse, viendo solo opciones compatibles con su preferencia. Las opciones incluyen frito, a la parrilla, al horno, hervido, al vapor, crudo, salteado, entre otros métodos registrados en el catálogo de `CookingMethod` del tenant.

El hook `useAdvancedFilters` combina los tres sistemas de filtrado (alérgenos, dietético, método de cocción) aplicándolos secuencialmente y proporcionando una lista final de productos que cumplen todos los criterios seleccionados.

### La Persistencia Inteligente de Preferencias

Todo este sistema de filtrado sería inútil si el usuario tuviera que reconfigurarlo cada vez que visita el restaurante. El hook `useImplicitPreferences` resuelve este problema sincronizando las preferencias con el backend a través del endpoint `PATCH /api/diner/preferences` y asociándolas con el identificador del dispositivo.

La sincronización utiliza debouncing de dos segundos para evitar peticiones excesivas mientras el usuario ajusta múltiples filtros en rápida sucesión. El hook `useDebounce` implementa este comportamiento con protección contra race conditions, separando cuidadosamente el efecto de montaje/desmontaje del efecto de actualización de valor.

Cuando un comensal regresa semanas después con el mismo dispositivo, el endpoint `GET /api/diner/device/{device_id}/preferences` recupera sus preferencias guardadas y el hook las aplica automáticamente al cargar la aplicación. El comensal encuentra el menú ya filtrado según sus restricciones habituales sin configuración manual, creando una experiencia personalizada sin requerir registro explícito.

---

## Capítulo 4: El Carrito Compartido

### La Anatomía de una Sesión de Mesa

El corazón de pwaMenu es el `tableStore`, un estado Zustand que representa la sesión de mesa en su totalidad. La interface `TableState` define más de veinte propiedades organizadas en categorías funcionales: información de sesión (`session`, `currentDiner`), estado del carrito (`cart` implícito en session), control de operaciones (`isLoading`, `isSubmitting`, `submitSuccess`, `_submitting`), historial de pedidos (`orders`, `currentRound`, `lastOrderId`), estado de confirmación grupal (`roundConfirmation`), y registro de pagos (`dinerPayments`).

Cuando un comensal agrega un producto al carrito mediante la acción `addToCart`, el item queda etiquetado con su `diner_id` y nombre. Esto permite que el carrito muestre quién pidió qué mediante códigos de color consistentes generados por `getColorForIndex`, facilitando la división de cuentas al final y creando una sensación de propiedad sobre las selecciones individuales dentro del contexto colaborativo. Cada comensal puede modificar solo sus propios items comparando `diner_id` con `currentDiner.id`, pero todos pueden ver el carrito completo.

La sesión incluye un campo `last_activity` que se actualiza con cada interacción del usuario: agregar item, modificar cantidad, eliminar producto. El sistema de expiración verifica este timestamp en lugar del tiempo de creación, permitiendo que sesiones con actividad continua persistan indefinidamente mientras que sesiones abandonadas expiran después de ocho horas de inactividad.

### El Flujo de Sincronización en Tiempo Real

Cuando cinco personas miran el mismo carrito desde cinco dispositivos diferentes, la consistencia visual es crítica. El flujo de sincronización opera en múltiples capas coordinadas.

Cuando un comensal añade un producto al carrito, la operación sigue un flujo preciso orquestado entre el store local, el backend REST y el gateway WebSocket:

1. La acción `addToCart` del store valida los datos de entrada: el producto existe en el menú, la cantidad está en rango válido (1-10), la sesión permanece activa y no expirada.
2. Se genera un ID temporal optimista mediante `generateId()` y se añade al estado local inmediatamente, proporcionando feedback visual instantáneo.
3. Se envía petición POST a `/api/diner/cart/add` con los datos del item: `product_id`, `quantity`, `notes`, `diner_id`.
4. El backend persiste el item en la tabla `cart_item` y emite evento `CART_ITEM_ADDED` al canal Redis de la sesión.
5. El gateway WebSocket distribuye el evento a todos los comensales conectados a esa mesa.
6. El hook `useCartSync` en cada dispositivo procesa el evento mediante el callback registrado con `dinerWS.on('CART_ITEM_ADDED', ...)`.
7. En el dispositivo originador, la función `isFromCurrentDiner()` detecta que el evento corresponde a la operación local y omite actualizaciones duplicadas.
8. En otros dispositivos, el item se añade al estado local mediante `addRemoteCartItem`, apareciendo instantáneamente en sus interfaces.

Si el paso 3 falla por error de red o validación del servidor, el item optimista se elimina del estado local mediante rollback automático, revirtiendo el cambio visual. El usuario ve el item desaparecer y recibe notificación del error vía toast.

### Optimizaciones del Hook useCartSync

El hook `useCartSync` representa una pieza crítica de la arquitectura, responsable de mantener sincronizado el carrito local con los cambios de otros comensales. Su implementación incorpora múltiples optimizaciones identificadas durante auditorías de rendimiento (PERF-01, PERF-02, PERF-03).

Un caché LRU (Least Recently Used) almacena conversiones de items del backend al formato frontend, evitando reconstruir objetos idénticos repetidamente cuando el mismo producto se añade múltiples veces. La deduplicación de eventos mediante un Set con límite de 100 entradas y TTL de 5 segundos previene procesamiento duplicado de eventos que podrían llegar por múltiples caminos en condiciones de red inestables.

El debounce en reconexión agrupa actualizaciones que llegan en ráfaga cuando la conexión WebSocket se restablece tras una desconexión. En lugar de aplicar cada cambio individualmente provocando múltiples re-renders, se acumulan durante un segundo y se aplican en batch, mejorando significativamente la percepción de rendimiento.

### El Problema de la Concurrencia Optimista

El sistema utiliza actualizaciones optimistas mediante el hook `useOptimisticCart` de React 19. Este hook envuelve el estado real del carrito con una capa de actualizaciones pendientes que se aplican instantáneamente a la interfaz mientras la operación real se ejecuta en segundo plano.

La generación de IDs temporales incluye un contador incremental además del UUID para garantizar unicidad incluso en escenarios de double-click rápido donde `Date.now()` podría retornar el mismo valor. Esta protección, implementada tras identificar colisiones en auditoría, asegura que cada item optimista tenga un identificador único.

La deduplicación de items durante reconciliación merece mención especial. Cuando el mismo producto aparece dos veces con IDs diferentes (uno temporal, otro real), el sistema en `SharedCart.tsx` fusiona estas entradas preferiendo el ID permanente del backend. Un Map con clave compuesta `${product_id}-${diner_id}` detecta duplicados y los elimina antes del renderizado, previniendo glitches visuales durante la reconciliación entre estado optimista y estado confirmado.

### La Confirmación Grupal: Un Protocolo de Consenso

El momento más delicado del flujo es enviar el pedido a cocina. A diferencia de una aplicación individual donde el usuario simplemente presiona "enviar", en una mesa compartida surge la pregunta: ¿están todos listos? ¿Alguien quiere agregar algo más?

El sistema de confirmación grupal implementa un protocolo de consenso inspirado en sistemas distribuidos. La interface `RoundConfirmation` define la estructura del estado de propuesta:

```typescript
interface RoundConfirmation {
  proposer_id: string           // Quién inició la propuesta
  proposed_at: number           // Timestamp de inicio
  status: 'pending' | 'confirmed' | 'cancelled' | 'expired'
  diner_statuses: Map<string, DinerReadyStatus>  // Estado por comensal
}

interface DinerReadyStatus {
  diner_id: string
  is_ready: boolean
  confirmed_at?: number
}
```

Cuando un comensal ejecuta `proposeRound()`, todos los demás reciben actualización visual mostrando quién propuso y el estado de cada participante. El componente `RoundConfirmationPanel` renderiza esta información con indicadores de color: verde para confirmados, gris para esperando.

Cada comensal puede ejecutar `confirmReady()` para marcar su disposición. El selector `useRoundConfirmationData` calcula derivados: `confirmationCount` (cuántos confirmaron), `allReady` (si todos confirmaron), `hasCurrentDinerConfirmed` (si el usuario actual ya confirmó), `isProposer` (si el usuario actual inició la propuesta).

Cuando `allReady` se vuelve true, un temporizador de 1.5 segundos inicia la cuenta regresiva visible. Este delay permite cancelación de último momento si alguien cambió de opinión. Al expirar el temporizador, `submitOrder()` se ejecuta automáticamente enviando el pedido a cocina.

La propuesta tiene un timeout de cinco minutos implementado mediante verificación de `proposed_at` contra `Date.now()`. Si expira sin confirmación unánime, el estado cambia a 'expired' y se limpia la propuesta. El proponente puede ejecutar `cancelRoundProposal()` en cualquier momento, y cualquier comensal puede revocar su confirmación mediante `cancelReady()` antes del envío final.

El diseño reconoce que el envío de un pedido es un momento social, no solo técnico. Forzar el envío cuando alguien aún está decidiendo sería tan molesto como que un comensal gritara al mozo sin consultar a los demás. El protocolo de consenso digitaliza la cortesía natural de preguntar "¿pedimos ya?".

---

## Capítulo 5: La Conexión en Tiempo Real

### El WebSocket del Comensal

Mientras el mozo y la cocina tienen sus propios canales WebSocket con autenticación JWT tradicional, el comensal utiliza un canal diferente autenticado mediante el token de mesa. La clase `DinerWebSocket` en `services/websocket.ts` encapsula esta conexión, manejando la complejidad de mantener un vínculo persistente en el entorno hostil de los navegadores móviles.

La conexión se establece hacia `${WS_URL}/ws/diner?table_token=${token}` donde el gateway WebSocket valida el token y extrae la información de sesión. Una vez autenticado, el comensal queda suscrito al canal de su mesa específica, recibiendo todos los eventos relevantes para esa sesión.

El patrón pub/sub interno de la clase permite registrar múltiples listeners para diferentes tipos de eventos. El método `on(eventType, callback)` registra un callback y retorna una función de cleanup para desregistro. Los hooks de React utilizan este mecanismo en sus efectos:

```typescript
useEffect(() => {
  const unsubscribe = dinerWS.on('CART_ITEM_ADDED', handleCartAdd)
  return unsubscribe  // Cleanup al desmontar
}, [])
```

### Reconexión con Backoff Exponencial y Jitter

La reconexión automática utiliza backoff exponencial con jitter aleatorio, patrón crítico para aplicaciones móviles donde las conexiones se pierden frecuentemente. Cuando la conexión se pierde, el sistema espera un segundo antes del primer intento, luego dos, luego cuatro, hasta un máximo de treinta segundos entre intentos.

El jitter del 50% evita la "estampida de reconexiones" (thundering herd) donde muchos dispositivos que perdieron conexión simultáneamente (por caída momentánea del servidor) intentarían reconectarse exactamente al mismo tiempo, potencialmente sobrecargando el servidor nuevamente. El delay efectivo se calcula como:

```
delay = baseDelay * 2^attempt * random(0.5, 1.5)
```

El límite de 50 intentos máximos (CLIENT-MED-01 FIX) previene loops infinitos de reconexión cuando el problema es permanente (servidor caído indefinidamente, token expirado). Tras agotar los intentos, la conexión se marca como permanentemente fallida y se notifica al usuario sugiriendo recargar la página.

Los códigos de cierre WebSocket determinan el comportamiento de reconexión. Los códigos estándar 1000 (cierre normal) y 1001 (navegando fuera) no disparan reconexión. Los códigos de error recuperables (1006 conexión perdida, 1013 servidor sobrecargado) disparan el proceso de backoff. Los códigos especiales 4001 (autenticación fallida), 4003 (acceso prohibido) y 4029 (rate limited) indican problemas que no se resolverán con reintentos y provocan abandono inmediato.

### El Heartbeat y la Detección de Conexiones Zombi

El protocolo de heartbeat envía un mensaje `{"type":"ping"}` cada treinta segundos y espera un `{"type":"pong"}` dentro de diez segundos. Si el pong no llega, el sistema cierra la conexión proactivamente y comienza el proceso de reconexión.

Este mecanismo detecta conexiones "zombi": aquellas que parecen abiertas según el estado del WebSocket pero han perdido comunicación real. Este escenario es común cuando un dispositivo móvil entra en modo suspensión sin cerrar apropiadamente las conexiones TCP subyacentes, o cuando un proxy intermediario cierra silenciosamente conexiones inactivas.

El listener de visibilidad complementa el sistema de heartbeat. El evento `visibilitychange` del documento detecta cuando el usuario cambia de pestaña o desbloquea el teléfono después de un período de suspensión. Al retornar a la aplicación, el sistema verifica inmediatamente el estado de la conexión: si el heartbeat está vencido o la conexión parece muerta, se restablece proactivamente en lugar de esperar al próximo ciclo de heartbeat. Este comportamiento asegura que el comensal siempre tenga información actualizada cuando activamente mira la aplicación.

### Eventos del Ciclo de Vida del Pedido

A través del WebSocket, el comensal recibe actualizaciones sobre el progreso de sus pedidos. El ciclo de vida completo de un round atraviesa seis estados:

| Estado | Evento WebSocket | Significado |
|--------|-----------------|-------------|
| PENDING | ROUND_PENDING | Pedido creado, aguarda verificación del mozo |
| CONFIRMED | ROUND_CONFIRMED | Mozo verificó presencialmente en la mesa |
| SUBMITTED | ROUND_SUBMITTED | Admin/Manager envió a cocina |
| IN_KITCHEN | ROUND_IN_KITCHEN | Cocina comenzó preparación |
| READY | ROUND_READY | Cocina terminó, listo para servir |
| SERVED | ROUND_SERVED | Mozo entregó a la mesa |

El hook `useOrderUpdates` escucha estos eventos y actualiza el estado local mediante `updateOrderStatus`. Cada transición permite que el comensal sepa exactamente dónde está su comida sin necesidad de preguntar al mozo. El componente `OrderHistory` muestra esta información con indicadores visuales de progreso.

El evento `ROUND_ITEM_DELETED` merece atención especial. Cuando un mozo elimina un item de un pedido pendiente o confirmado (porque el producto no está disponible, por ejemplo), el evento se emite a todos los comensales de la mesa. El handler actualiza el carrito local removiendo el item correspondiente, manteniendo consistencia entre la realidad operativa del restaurante y la visión del cliente.

Los eventos de carrito (`CART_ITEM_ADDED`, `CART_ITEM_UPDATED`, `CART_ITEM_REMOVED`, `CART_CLEARED`, `CART_SYNC`) mantienen sincronizado el carrito compartido según se describió anteriormente.

---

## Capítulo 6: El Reconocimiento del Cliente Recurrente

### La Identificación Sin Registro

La mayoría de las aplicaciones de fidelización requieren creación de cuenta, ingreso de email, verificación por código, y todo un ritual que interrumpe la experiencia. pwaMenu invierte esta lógica: primero reconoce, después ofrece.

El sistema de identificación opera en cuatro fases evolutivas, cada una construyendo sobre la anterior:

**Fase 1 - Device Tracking**: El identificador único de dispositivo (`deviceId`) y la huella digital (`deviceFingerprint`) se generan en la primera visita y persisten en localStorage. Al registrar un comensal en una mesa, ambos identificadores se envían al backend en el payload de `POST /api/diner/register`. El endpoint `GET /api/diner/device/{device_id}/history` permite consultar el historial de visitas de un dispositivo, retornando fechas, mesas visitadas y productos ordenados previamente.

**Fase 2 - Preferencias Implícitas**: Como se describió en el capítulo de filtros, el hook `useImplicitPreferences` sincroniza automáticamente las configuraciones de filtrado con el backend. En visitas posteriores, estas preferencias se cargan y aplican sin intervención del usuario.

**Fase 3 - Recomendaciones Contextuales**: Cuando un dispositivo conocido se conecta, el backend puede ofrecer información contextual: "Bienvenido de nuevo, la última vez pediste la Milanesa Napolitana" o "Basado en tus preferencias, te recomendamos evitar los platos con maní". El endpoint de menú puede incluir un campo `returning_device_suggestions` con esta información.

**Fase 4 - Opt-in de Fidelización**: Para usuarios que desean funcionalidades adicionales (acumulación de puntos, ofertas personalizadas, historial detallado), el sistema ofrece un registro voluntario que vincula el dispositivo a un perfil de cliente.

### El Sistema de Opt-in

El hook `useCustomerRecognition` detecta cuando el dispositivo actual corresponde a un visitante frecuente sin cuenta registrada. Mediante el endpoint `GET /api/customer/recognize`, el sistema verifica si el `deviceId` está asociado a un cliente existente. Si no lo está pero el dispositivo tiene historial significativo (múltiples visitas), se presenta el `OptInModal` invitando al usuario a registrarse.

El formulario de registro implementa consentimiento granular cumpliendo requisitos GDPR. El usuario puede aceptar o rechazar independientemente:
- Almacenamiento de preferencias dietéticas
- Análisis de historial de compras para recomendaciones
- Comunicaciones promocionales por email/SMS
- Personalización mediante inteligencia artificial

El endpoint `POST /api/customer/register` crea el perfil de cliente con los consentimientos especificados. El campo `customer_id` en la tabla `Diner` vincula visitas posteriores al perfil registrado.

Una vez registrado, `GET /api/customer/suggestions` proporciona recomendaciones personalizadas: productos favoritos basados en historial, items populares entre clientes con preferencias similares, ofertas exclusivas para clientes fidelizados.

Este diseño respeta la privacidad por defecto mientras ofrece beneficios tangibles a quienes eligen participar. La diferencia con sistemas tradicionales es sutil pero significativa: el restaurante reconoce al cliente antes de pedirle que se registre, demostrando valor antes de solicitar compromiso.

---

## Capítulo 7: El Cierre de Mesa y el Pago

### El Flujo de Solicitud de Cuenta

Cuando el grupo termina de comer, cualquier comensal puede solicitar la cuenta tocando el botón correspondiente en `BottomNav`. Esta acción ejecuta `closeTable()` en el store, que internamente llama al endpoint `POST /api/billing/check/request` para crear un registro de cuenta (Check) en el backend.

El sistema valida que no queden items pendientes en el carrito (productos agregados pero no enviados), mostrando advertencia si existen. Esta validación previene el escenario donde un comensal olvida que había seleccionado un postre que nunca se pidió, evitando sorpresas desagradables al ver la cuenta.

El backend calcula el total sumando los precios de todos los items de todos los rounds de la sesión, aplicando promociones vigentes si corresponde. El modelo `Check` (con tabla `app_check` para evitar palabra reservada SQL) incluye desglose por item con `Charge`, subtotal, impuestos si aplican, y total final. El estado de la sesión cambia a `PAYING` y se emite evento `CHECK_REQUESTED` al canal del mozo asignado.

La solicitud de cuenta no cierra la sesión inmediatamente. El diseño reconoce que los comensales frecuentemente agregan "una última cosa" mientras esperan la cuenta, o que alguien puede pedir un café adicional. La sesión permanece activa para nuevos pedidos mientras está en estado `PAYING`, que simplemente se agregarán al total final en ciclos de pago subsecuentes.

### La División de Cuentas

La página `CloseTable.tsx` presenta el resumen de consumo y opciones de división organizadas en componentes modulares: `CloseTableHeader`, `TotalCard`, `SummaryTab`, `OrdersList`, cada uno en el subdirectorio `close-table/`.

El helper `calculatePaymentShares()` en `tableStore/helpers.ts` soporta tres estrategias de división definidas por el tipo `SplitMethod`:

**División igualitaria (`equal`)**: El total se divide equitativamente entre los comensales presentes. El cálculo `total / dinerCount` se redondea apropiadamente manejando centavos residuales asignándolos al último comensal.

**División por consumo (`byConsumption`)**: Cada comensal paga exactamente lo que ordenó, calculado a partir del campo `diner_id` de cada item. La función itera sobre todos los items agrupando por comensal y sumando subtotales.

**División personalizada (`custom`)**: Los comensales acuerdan montos arbitrarios, útil cuando alguien quiere invitar o cuando el cálculo exacto no coincide con el deseo social. La interfaz permite ingresar montos manuales por comensal.

El registro de pagos individuales mediante `dinerPayments` permite escenarios mixtos donde algunos pagan en efectivo, otros con tarjeta, y quizás uno transfiere su parte. El sistema trackea cada contribución mediante `recordDinerPayment()` hasta que el total queda cubierto.

### Integración con Mercado Pago

Para pagos electrónicos, pwaMenu integra con Mercado Pago mediante el modelo de Checkout Pro. El servicio `mercadoPago.ts` orquesta el flujo completo.

Cuando un comensal selecciona "Pagar con Mercado Pago", la función `initiatePayment()` solicita al backend la creación de una preferencia de pago vía `POST /api/billing/mercadopago/preference`. El backend, utilizando el SDK de Mercado Pago, genera una preferencia que incluye: items con nombre y precio, datos del pagador, URLs de retorno para éxito (`/payment/success`), fallo (`/payment/failure`) y estado pendiente (`/payment/pending`).

El comensal es redirigido a `sandbox_init_point` (ambiente de prueba) o `init_point` (producción) donde Mercado Pago presenta su checkout. El usuario puede pagar con tarjeta de crédito/débito, saldo de cuenta Mercado Pago, transferencia bancaria, o métodos alternativos según su país y configuración del comercio.

Una vez completado el pago, Mercado Pago redirige al usuario de vuelta a pwaMenu a la página `PaymentResult.tsx`. Los query parameters de la URL (`status`, `payment_id`, `external_reference`) permiten determinar el resultado: aprobado, rechazado, o pendiente de confirmación.

La página `PaymentResult` interpreta estos parámetros y muestra feedback apropiado: celebración visual para pagos aprobados, mensaje de error con opción de reintento para rechazados, explicación de estado pendiente para pagos que requieren confirmación adicional (transferencias, pagos en efectivo en puntos de pago).

El backend recibe notificación independiente del resultado mediante webhook de Mercado Pago en `POST /api/billing/mercadopago/webhook`. Este webhook garantiza que el registro de pago se actualice incluso si el usuario cierra el navegador antes de retornar a la aplicación. El `MERCADOPAGO_WEBHOOK_SECRET` valida la autenticidad de la notificación.

### Pagos en Efectivo y Tarjeta Física

Para pagos que no atraviesan Mercado Pago (efectivo entregado al mozo o tarjeta física procesada en terminal del restaurante), la aplicación registra la intención de pago pero la confirmación ocurre desde pwaWaiter.

El comensal selecciona el método de pago (efectivo o tarjeta) y el monto correspondiente a su porción. Esta información se registra localmente y se muestra al mozo en su aplicación. El mozo procesa el pago físicamente, verifica el monto, y confirma la recepción en pwaWaiter mediante `POST /api/waiter/payments/{id}/confirm`.

La confirmación del mozo emite evento `PAYMENT_APPROVED` que actualiza el estado del Check en todos los dispositivos de la mesa. Cuando todos los pagos parciales suman el total, el Check se marca como pagado completamente y la sesión puede cerrarse.

---

## Capítulo 8: La Arquitectura de Estado

### El Patrón de Selectores Estables

React 19 con Zustand 5 introduce requisitos estrictos para evitar re-renders infinitos. El problema surge cuando un selector retorna una nueva referencia de objeto o array en cada invocación: React detecta "cambio" y re-renderiza, lo que invoca el selector nuevamente, creando un loop infinito.

La solución implementada en `tableStore/selectors.ts` emplea constantes de referencia estable para valores vacíos. En lugar de retornar `[]` directamente, los selectores retornan constantes definidas a nivel de módulo:

```typescript
const EMPTY_CART_ITEMS: CartItem[] = []
const EMPTY_DINERS: Diner[] = []
const EMPTY_ORDERS: OrderRecord[] = []

export const selectCartItems = (state: TableState) =>
  state.session?.cart_items ?? EMPTY_CART_ITEMS
```

Dado que la misma referencia de objeto se retorna en cada invocación cuando no hay datos, React detecta correctamente que no hay cambios y omite el re-render.

Para selectores que filtran o transforman datos, se implementa un patrón de caché manual. El selector mantiene una referencia al input previo y su resultado correspondiente en un objeto de caché a nivel de módulo:

```typescript
const myItemsCache = {
  items: null as CartItem[] | null,
  dinerId: null as string | null,
  result: EMPTY_CART_ITEMS
}

export const selectMyItems = (state: TableState) => {
  const items = state.session?.cart_items ?? EMPTY_CART_ITEMS
  const dinerId = state.currentDiner?.id ?? null

  if (items === myItemsCache.items && dinerId === myItemsCache.dinerId) {
    return myItemsCache.result
  }

  const filtered = items.filter(i => i.diner_id === dinerId)
  myItemsCache.items = items
  myItemsCache.dinerId = dinerId
  myItemsCache.result = filtered.length > 0 ? filtered : EMPTY_CART_ITEMS
  return myItemsCache.result
}
```

Este patrón, aunque verbose, garantiza estabilidad referencial sin depender de bibliotecas externas de memoización y sin introducir hooks adicionales que complicarían el uso de los selectores.

### La Persistencia de Sesión con Validación

El middleware `persist` de Zustand serializa automáticamente partes del estado a localStorage después de cada modificación. La configuración `partialize` define exactamente qué se persiste, excluyendo estado transitorio:

```typescript
persist(
  (set, get) => ({ /* estado y acciones */ }),
  {
    name: 'table-session',
    partialize: (state) => ({
      session: state.session,
      currentDiner: state.currentDiner,
      orders: state.orders,
      currentRound: state.currentRound,
      // Excluidos: isLoading, isSubmitting, submitSuccess, errors
    }),
    onRehydrateStorage: () => (state, error) => {
      if (error) {
        console.error('Rehydration failed:', error)
        // MED-02 FIX: Limpiar estado corrupto
        localStorage.removeItem('table-session')
        return
      }
    }
  }
)
```

La rehidratación incluye validaciones de expiración. El helper `isSessionExpired()` verifica `session.last_activity` contra `Date.now()` considerando el umbral de 8 horas definido en `SESSION.EXPIRY_HOURS`. Una sesión almacenada de hace ocho horas sin actividad probablemente corresponde a una comida que ya terminó; el sistema la descarta automáticamente en lugar de intentar reconectar a una mesa que probablemente tiene otros ocupantes.

### La Coordinación Multi-Tab

Un mismo comensal puede tener la aplicación abierta en múltiples pestañas del navegador. El sistema detecta cambios en localStorage desde otras pestañas mediante el evento `storage` del objeto `window`, configurado en `App.tsx`:

```typescript
useEffect(() => {
  const handleStorageChange = (e: StorageEvent) => {
    if (e.key === 'table-session' && e.newValue) {
      const newState = JSON.parse(e.newValue)
      // Sincronizar estado desde otra pestaña
      syncFromStorage(newState)
    } else if (e.key === 'table-session' && !e.newValue) {
      // Otra pestaña cerró sesión
      clearSession()
    }
  }

  window.addEventListener('storage', handleStorageChange)
  return () => window.removeEventListener('storage', handleStorageChange)
}, [])
```

La estrategia de merge para items del carrito utiliza un Map con clave compuesta para deduplicación. La pestaña que detecta el cambio es receptora, considerando a la otra pestaña como fuente de verdad. Cada pestaña mantiene su propia identidad de comensal (`currentDiner`), pero comparte el carrito y los pedidos. Si una pestaña detecta que otra abandonó la sesión (el valor es null), limpia su propio estado.

---

## Capítulo 9: El Cliente API Defensivo

### La Protección SSRF

El cliente API en `services/api.ts` valida rigurosamente que las URLs de destino correspondan a hosts permitidos, previniendo ataques SSRF (Server-Side Request Forgery) donde un input malicioso podría redirigir peticiones a servicios internos de la infraestructura.

La validación de seguridad opera en múltiples capas. Primero, la URL se parsea y normaliza:

```typescript
const url = new URL(endpoint, API_BASE_URL)

// Bloquear credenciales embebidas en URL
if (url.username || url.password) {
  throw new ApiError('URL credentials not allowed', 400)
}
```

Las direcciones IP directas están bloqueadas para prevenir acceso a servicios internos:

```typescript
const BLOCKED_IP_PATTERNS = [
  /^127\./,           // Localhost IPv4
  /^10\./,            // Private class A
  /^172\.(1[6-9]|2\d|3[01])\./,  // Private class B
  /^192\.168\./,      // Private class C
  /^169\.254\./,      // Link-local
  /^0\./,             // Current network
  /^\[::1\]/,         // Localhost IPv6
  /^\[fc/i,           // IPv6 unique local
  /^\[fd/i,           // IPv6 unique local
  /^\[fe80:/i,        // IPv6 link-local
]

if (BLOCKED_IP_PATTERNS.some(p => p.test(url.hostname))) {
  throw new ApiError('IP addresses not allowed', 400)
}
```

Los puertos están restringidos a un conjunto conocido de puertos HTTP válidos:

```typescript
const ALLOWED_PORTS = ['', '80', '443', '8000', '8080', '8443', '3000', '5000']
const normalizedPort = url.port || (url.protocol === 'https:' ? '443' : '80')

if (!ALLOWED_PORTS.includes(normalizedPort)) {
  throw new ApiError(`Port ${url.port} not allowed`, 400)
}
```

El hostname debe coincidir exactamente con los hosts permitidos configurados en `API_CONFIG.ALLOWED_HOSTS`, sin permitir subdominios ni variantes:

```typescript
if (!ALLOWED_HOSTS.includes(url.hostname)) {
  throw new ApiError(`Host ${url.hostname} not allowed`, 400)
}
```

### La Deduplicación de Peticiones

El sistema de deduplicación previene race conditions donde clicks rápidos podrían enviar múltiples veces la misma petición. Un Map `pendingRequests` registra cada petición en vuelo con una clave compuesta de método y endpoint:

```typescript
const pendingRequests = new Map<string, Promise<unknown>>()
const MAX_PENDING = 100
const CLEANUP_INTERVAL = 60000  // 1 minuto

function getRequestKey(method: string, url: string, body?: unknown): string {
  return `${method}:${url}:${JSON.stringify(body ?? '')}`
}

async function fetchWithDedup<T>(url: string, options: RequestInit): Promise<T> {
  const key = getRequestKey(options.method ?? 'GET', url, options.body)

  // Si existe petición idéntica en vuelo, reutilizar su promesa
  if (pendingRequests.has(key)) {
    return pendingRequests.get(key) as Promise<T>
  }

  // Límite de peticiones pendientes (HIGH-02 FIX)
  if (pendingRequests.size >= MAX_PENDING) {
    cleanupOldestPending()
  }

  const promise = fetch(url, options).then(/* ... */).finally(() => {
    pendingRequests.delete(key)
  })

  pendingRequests.set(key, promise)
  return promise
}
```

La comparación de body utiliza serialización JSON directa en lugar de hashing simple, evitando colisiones donde bodies diferentes produjeran el mismo hash (HIGH-05 FIX). El límite de 100 peticiones concurrentes y la limpieza periódica previenen crecimiento descontrolado del Map en escenarios patológicos.

### El Manejo de Expiración de Sesión

Cuando el backend responde con 401 (no autorizado), el cliente API detecta si la petición usaba autenticación de mesa y dispara el flujo de manejo de sesión expirada:

```typescript
if (response.status === 401 && options.tableAuth) {
  // Token de mesa expirado o inválido
  onTokenExpired?.()
  throw new AuthError('Session expired', 'errors.sessionExpired')
}
```

El callback `onTokenExpired` está conectado al store, que presenta un `SessionExpiredModal` informativo. El modal explica que la sesión expiró (los tokens de mesa tienen vida de 3 horas) y sugiere al usuario escanear nuevamente el QR para obtener una nueva sesión.

Este flujo reconoce que el usuario puede simplemente haber dejado la aplicación abierta demasiado tiempo. La experiencia guía al usuario hacia la resolución en lugar de mostrar errores técnicos confusos.

---

## Capítulo 10: La Internacionalización

### Tres Idiomas, Una Experiencia

pwaMenu soporta español, inglés y portugués, reflejando la realidad multilingüe de restaurantes que reciben turistas internacionales. El sistema i18next se configura en `i18n/index.ts` con recursos de traducción en archivos JSON separados: `es.json`, `en.json`, `pt.json`.

El detector de idioma personalizado extiende el detector estándar de i18next con validación adicional:

```typescript
const validatedLanguageDetector = new LanguageDetector()

validatedLanguageDetector.addDetector({
  name: 'validatedLocalStorage',
  lookup() {
    const cached = localStorage.getItem('i18nextLng')
    // Solo retornar si es idioma válido
    return SUPPORTED_LANGUAGES.includes(cached) ? cached : null
  },
  cacheUserLanguage(lng) {
    // Solo cachear si es idioma válido
    if (SUPPORTED_LANGUAGES.includes(lng)) {
      localStorage.setItem('i18nextLng', lng)
    }
  }
})
```

Esta defensa previene corrupción de localStorage que podría dejar la aplicación en un estado de idioma inválido (por ejemplo, si un script malicioso o un bug escribiera un valor incorrecto).

La configuración de fallback establece español como idioma de respaldo universal:

```typescript
i18n.init({
  fallbackLng: {
    en: ['es'],      // Inglés fallback a español
    pt: ['es'],      // Portugués fallback a español
    default: ['es']  // Cualquier otro fallback a español
  },
  interpolation: {
    escapeValue: false  // React ya escapa
  }
})
```

### Namespaces de Traducción

Los archivos de traducción organizan las claves en namespaces semánticos que facilitan la búsqueda y mantenimiento:

| Namespace | Contenido |
|-----------|-----------|
| `general` | Textos comunes: botones, títulos, estados |
| `menu` | Catálogo: categorías, productos, descripciones |
| `cart` | Carrito: items, cantidades, totales |
| `payment` | Pago: métodos, división, confirmación |
| `errors` | Mensajes de error: validación, red, sesión |
| `filters` | Filtros: alérgenos, dietas, preferencias |
| `loyalty` | Fidelización: reconocimiento, registro, puntos |
| `roundConfirmation` | Confirmación grupal: propuesta, estados, acciones |
| `accessibility` | Accesibilidad: labels, announcements, hints |
| `bottomNav` | Navegación inferior: mozo, pedidos, cuenta |

### La Traducción de Productos

Más allá de la interfaz, el sistema soporta productos con nombres y descripciones traducidos. El modelo `Product` en el backend puede incluir campos localizados, y el hook `useProductTranslation` selecciona la versión apropiada según el idioma activo:

```typescript
const { t, i18n } = useTranslation()

const getLocalizedProduct = (product: Product) => ({
  ...product,
  name: product[`name_${i18n.language}`] ?? product.name,
  description: product[`description_${i18n.language}`] ?? product.description
})
```

El selector de idioma, ubicado discretamente en el Header, permite cambiar la preferencia manualmente mediante componentes `LanguageSelector` (dropdown) y `LanguageFlagSelector` (banderas). Esta configuración persiste en localStorage, asegurando que un turista anglófono no tenga que reconfigurar el idioma cada vez que escanea un nuevo QR en otra visita.

---

## Capítulo 11: La Progressive Web App

### La Instalabilidad

Como Progressive Web App, pwaMenu puede instalarse en la pantalla de inicio del dispositivo, proporcionando acceso rápido y experiencia de aplicación nativa sin barras de navegador. El hook `useInstallPrompt` detecta la disponibilidad del prompt de instalación:

```typescript
const [installPrompt, setInstallPrompt] = useState<BeforeInstallPromptEvent | null>(null)

useEffect(() => {
  const handler = (e: BeforeInstallPromptEvent) => {
    e.preventDefault()  // Prevenir prompt automático
    setInstallPrompt(e) // Guardarlo para uso controlado
  }

  window.addEventListener('beforeinstallprompt', handler)
  return () => window.removeEventListener('beforeinstallprompt', handler)
}, [])

const promptInstall = () => {
  installPrompt?.prompt()
}
```

El componente `InstallBanner` presenta un banner discreto invitando a instalar la aplicación cuando el prompt está disponible. Al tocar "Instalar", se invoca el prompt nativo del navegador.

El manifiesto de aplicación en `manifest.webmanifest` (generado por vite-plugin-pwa) define los metadatos de instalación:

```json
{
  "name": "Sabor - Menú Digital",
  "short_name": "Sabor",
  "description": "Menú digital colaborativo",
  "theme_color": "#f97316",
  "background_color": "#0a0a0a",
  "display": "standalone",
  "orientation": "portrait",
  "icons": [
    { "src": "pwa-192x192.png", "sizes": "192x192", "type": "image/png" },
    { "src": "pwa-512x512.png", "sizes": "512x512", "type": "image/png", "purpose": "maskable" }
  ],
  "shortcuts": [
    { "name": "Ver Menú", "url": "/", "icons": [...] },
    { "name": "Productos Destacados", "url": "/?section=featured", "icons": [...] },
    { "name": "Bebidas", "url": "/?category=drinks", "icons": [...] },
    { "name": "Mi Carrito", "url": "/?cart=open", "icons": [...] }
  ]
}
```

### El Service Worker y las Estrategias de Caché

El service worker generado por Workbox implementa estrategias de caché diferenciadas según el tipo de recurso y su volatilidad:

**Precache (recursos de la aplicación)**: JavaScript, CSS, HTML de la aplicación se descargan durante la instalación del service worker. En visitas posteriores, se sirven instantáneamente desde caché mientras el service worker verifica actualizaciones en segundo plano.

**CacheFirst (imágenes de productos)**: Las imágenes de productos provenientes de CDN externos utilizan estrategia que prioriza velocidad sobre frescura. Expiración de 30 días, límite de 60 entradas:

```typescript
{
  urlPattern: /^https:\/\/images\.unsplash\.com\//,
  handler: 'CacheFirst',
  options: {
    cacheName: 'product-images',
    expiration: { maxEntries: 60, maxAgeSeconds: 30 * 24 * 60 * 60 }
  }
}
```

**CacheFirst (Google Fonts)**: Fuentes tipográficas con expiración de un año. Las URLs de fuentes incluyen hashes de versión que cambian cuando la fuente se actualiza:

```typescript
{
  urlPattern: /^https:\/\/fonts\.googleapis\.com\//,
  handler: 'CacheFirst',
  options: {
    cacheName: 'google-fonts',
    expiration: { maxAgeSeconds: 365 * 24 * 60 * 60 }
  }
}
```

**NetworkFirst (APIs)**: Llamadas a la API del backend intentan obtener datos frescos del servidor con timeout de 5 segundos. Si la red falla o tarda demasiado, se sirve la última versión cacheada:

```typescript
{
  urlPattern: /^https:\/\/api\..*\/api\//,
  handler: 'NetworkFirst',
  options: {
    cacheName: 'api-cache',
    networkTimeoutSeconds: 5,
    expiration: { maxAgeSeconds: 60 * 60 }  // 1 hora
  }
}
```

### Las Actualizaciones Transparentes

Cuando el administrador despliega una nueva versión de la aplicación, el service worker la detecta durante su ciclo de actualización. La configuración `registerType: 'prompt'` presenta una notificación al usuario en lugar de actualizar silenciosamente:

```typescript
// App.tsx
const { needRefresh, updateServiceWorker } = useRegisterSW({
  onNeedRefresh() {
    // Mostrar banner de actualización disponible
    setShowUpdateBanner(true)
  },
  onOfflineReady() {
    toast.info(t('general.offlineReady'))
  }
})

const handleUpdate = () => {
  updateServiceWorker(true)  // true = reload after update
}
```

Este patrón respeta la experiencia del usuario. Si está en medio de configurar un pedido, puede continuar con la versión actual y actualizar cuando termine. Si prefiere tener la última versión inmediatamente, puede aceptar la actualización que recargará la página con el nuevo código.

### El Funcionamiento Offline

El componente `NetworkStatus` monitorea la conectividad mediante el evento `online`/`offline` del navegador:

```typescript
const [isOnline, setIsOnline] = useState(navigator.onLine)

useEffect(() => {
  const handleOnline = () => setIsOnline(true)
  const handleOffline = () => setIsOnline(false)

  window.addEventListener('online', handleOnline)
  window.addEventListener('offline', handleOffline)

  return () => {
    window.removeEventListener('online', handleOnline)
    window.removeEventListener('offline', handleOffline)
  }
}, [])
```

Cuando el dispositivo pierde conexión, un indicador visual informa al usuario. El hook `useOnlineStatus` expone este estado a cualquier componente que necesite adaptar su comportamiento.

Las operaciones de carrito que fallan por falta de conectividad se encolan en el `OfflineQueue`. Cuando la conectividad se restaura, la cola reproduce las operaciones en orden FIFO, reconciliando el estado local con el servidor. Este patrón permite que usuarios en zonas con conectividad intermitente continúen interactuando con la aplicación.

La página `offline.html` servida cuando la navegación falla completamente presenta un mensaje amigable indicando la falta de conexión y sugiriendo verificar la red WiFi o datos móviles. Esta página se precachea durante la instalación del service worker para garantizar su disponibilidad incluso sin ninguna conectividad.

---

## Capítulo 12: Accesibilidad y Experiencia de Usuario

### Estándares de Accesibilidad

La aplicación implementa estándares WCAG 2.1 nivel AA. Todos los elementos interactivos poseen labels accesibles mediante texto visible, atributo `aria-label`, o `aria-labelledby` apuntando a un elemento descriptivo.

Los modales implementan focus trap mediante el hook `useFocusTrap`: al abrirse, el foco se mueve al primer elemento focusable del modal; la navegación con Tab cicla dentro del modal sin escapar a elementos detrás del backdrop; al cerrarse, el foco retorna al elemento que abrió el modal.

```typescript
const useFocusTrap = (isOpen: boolean, containerRef: RefObject<HTMLElement>) => {
  useEffect(() => {
    if (!isOpen || !containerRef.current) return

    const focusableElements = containerRef.current.querySelectorAll(
      'button, [href], input, select, textarea, [tabindex]:not([tabindex="-1"])'
    )
    const firstElement = focusableElements[0] as HTMLElement
    const lastElement = focusableElements[focusableElements.length - 1] as HTMLElement

    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key !== 'Tab') return

      if (e.shiftKey && document.activeElement === firstElement) {
        e.preventDefault()
        lastElement.focus()
      } else if (!e.shiftKey && document.activeElement === lastElement) {
        e.preventDefault()
        firstElement.focus()
      }
    }

    firstElement?.focus()
    document.addEventListener('keydown', handleKeyDown)
    return () => document.removeEventListener('keydown', handleKeyDown)
  }, [isOpen, containerRef])
}
```

El hook `useEscapeKey` permite cerrar modales con la tecla Escape, soportando un estado `disabled` para prevenir cierre durante operaciones asíncronas pendientes.

### Anuncios para Lectores de Pantalla

El hook `useAriaAnnounce` permite anunciar cambios de estado a lectores de pantalla mediante una región ARIA live que se crea dinámicamente:

```typescript
const useAriaAnnounce = () => {
  const regionRef = useRef<HTMLDivElement | null>(null)

  useEffect(() => {
    // Crear región live al montar
    const region = document.createElement('div')
    region.setAttribute('role', 'status')
    region.setAttribute('aria-live', 'polite')
    region.setAttribute('aria-atomic', 'true')
    region.className = 'sr-only'  // Visualmente oculto
    document.body.appendChild(region)
    regionRef.current = region

    return () => region.remove()
  }, [])

  const announce = useCallback((message: string) => {
    if (regionRef.current) {
      regionRef.current.textContent = ''  // Reset
      requestAnimationFrame(() => {
        if (regionRef.current) {
          regionRef.current.textContent = message
        }
      })
    }
  }, [])

  return announce
}
```

Cuando un producto se añade al carrito, se anuncia "Hamburguesa añadida al carrito". Cuando un pedido cambia de estado, se anuncia "Tu pedido está siendo preparado". Estos anuncios proporcionan feedback a usuarios que no pueden percibir cambios visuales.

Los iconos decorativos incluyen `aria-hidden="true"` para que lectores de pantalla los ignoren. Los iconos significativos (como el badge de cantidad en el carrito) incluyen texto alternativo mediante spans con clase `sr-only`.

### Diseño Táctil y Viewport Móvil

Los componentes táctiles respetan tamaños mínimos de 44x44 píxeles según guías de accesibilidad de Apple y Google, garantizando objetivos de toque cómodos en dispositivos móviles.

Las clases de safe area de Tailwind (`safe-area-top`, `safe-area-bottom`) garantizan que el contenido no quede oculto tras notches de iPhone o barras de navegación de Android:

```css
.safe-area-bottom {
  padding-bottom: env(safe-area-inset-bottom, 0);
}
```

Todos los contenedores de página incluyen `overflow-x-hidden w-full max-w-full` para prevenir scroll horizontal accidental en móviles, un problema común cuando elementos con ancho fijo exceden el viewport.

---

## Capítulo 13: El Asistente con Inteligencia Artificial

### La Arquitectura del Chat

El directorio `AIChat/` contiene el chatbot de asistencia que permite a los comensales hacer preguntas sobre el menú, pedir recomendaciones o solicitar información nutricional. El componente principal `index.tsx` presenta una interfaz de chat con historial de mensajes, campo de entrada y sugerencias de preguntas frecuentes.

El sistema utiliza el endpoint de RAG (Retrieval-Augmented Generation) del backend que combina búsqueda semántica sobre la base de conocimiento del restaurante con generación de respuestas mediante modelo de lenguaje. Las preguntas del usuario se envían a `/api/public/rag/chat` junto con el contexto de la sesión actual.

### Handlers de Respuesta Especializados

El módulo `responseHandlers.ts` implementa un patrón de estrategia para procesar diferentes tipos de respuesta del modelo de IA:

```typescript
interface ResponseHandler {
  canHandle(response: AIResponse): boolean
  render(response: AIResponse): ReactNode
}

const productRecommendationHandler: ResponseHandler = {
  canHandle: (r) => r.type === 'product_recommendation',
  render: (r) => <ProductCards products={r.products} />
}

const nutritionalInfoHandler: ResponseHandler = {
  canHandle: (r) => r.type === 'nutritional_info',
  render: (r) => <NutritionTable data={r.nutrition} />
}

const textResponseHandler: ResponseHandler = {
  canHandle: () => true,  // Fallback
  render: (r) => <TextMessage text={r.text} />
}

const handlers = [productRecommendationHandler, nutritionalInfoHandler, textResponseHandler]

const renderResponse = (response: AIResponse) => {
  const handler = handlers.find(h => h.canHandle(response))
  return handler?.render(response)
}
```

Las recomendaciones de productos se renderizan como cards interactivos que permiten agregar directamente al carrito. La información nutricional se presenta en tablas formateadas. Las respuestas de texto plano se muestran como párrafos estilizados con soporte para markdown básico.

### Gestión de Estado del Chat

El contador de IDs de mensaje implementa un reset periódico cada 60 segundos para prevenir crecimiento indefinido en conversaciones largas (LOW-01 FIX):

```typescript
const messageIdCounter = useRef(0)
const lastResetTime = useRef(Date.now())

const getNextMessageId = () => {
  const now = Date.now()
  if (now - lastResetTime.current > 60000) {
    messageIdCounter.current = 0
    lastResetTime.current = now
  }
  return `msg-${++messageIdCounter.current}`
}
```

El historial de mensajes se mantiene en estado local del componente. Al cerrar y reabrir el chat, el historial se preserva durante la sesión pero no persiste en localStorage, reconociendo que las conversaciones con IA son típicamente efímeras.

---

## Capítulo 14: Testing y Calidad de Código

### Infraestructura de Testing

El framework de testing combina Vitest como test runner y Testing Library para renderizado de componentes React. La configuración en `vite.config.ts` habilita entorno jsdom para simular APIs del navegador en Node.js.

Los tests se ubican junto al código fuente con extensión `.test.ts`:

```
src/
├── hooks/
│   ├── useCartSync.ts
│   └── useCartSync.test.ts
├── stores/
│   └── tableStore/
│       ├── store.ts
│       ├── store.test.ts
│       ├── helpers.ts
│       └── helpers.test.ts
└── services/
    ├── api.ts
    └── api.test.ts
```

### Patrones de Testing

Los tests unitarios verifican funciones puras como los helpers del tableStore:

```typescript
describe('calculateCartTotal', () => {
  it('should sum prices correctly', () => {
    const items = [
      { price: 100, quantity: 2 },
      { price: 50, quantity: 1 }
    ]
    expect(calculateCartTotal(items)).toBe(250)
  })

  it('should return 0 for empty cart', () => {
    expect(calculateCartTotal([])).toBe(0)
  })
})
```

Los tests de hooks utilizan `renderHook` de Testing Library:

```typescript
describe('useCartSync', () => {
  it('should add item when receiving CART_ITEM_ADDED', async () => {
    const mockWS = createMockWebSocket()
    const { result } = renderHook(() => useCartSync())

    // Simular evento WebSocket
    mockWS.emit('CART_ITEM_ADDED', { item: mockItem })

    await waitFor(() => {
      expect(result.current.items).toContainEqual(mockItem)
    })
  })
})
```

Los tests de servicios mockean fetch para simular respuestas de API:

```typescript
describe('api.fetchMenu', () => {
  beforeEach(() => {
    global.fetch = jest.fn()
  })

  it('should handle network errors gracefully', async () => {
    global.fetch.mockRejectedValue(new Error('Network error'))

    await expect(menuAPI.fetchMenu('test-slug'))
      .rejects.toThrow('errors.network')
  })
})
```

### Scripts de Ejecución

```bash
npm test              # Watch mode - re-ejecuta tests afectados al modificar archivos
npm run test:run      # Ejecución única para CI/CD pipelines
npm run test:coverage # Genera reporte de cobertura de código
```

La cobertura actual se enfoca en las áreas más críticas: lógica de carrito, sincronización de estado, manejo de errores, validación de seguridad. Los componentes visuales tienen menor cobertura dado que su corrección se verifica más efectivamente mediante testing manual y visual.

---

## Capítulo 15: Métricas de Rendimiento

### Web Vitals

El módulo `utils/webVitals.ts` recolecta métricas de rendimiento real de usuarios mediante la biblioteca web-vitals:

```typescript
import { onLCP, onFID, onCLS, onFCP, onTTFB } from 'web-vitals'

const metrics: Record<string, number> = {}

export const initWebVitals = () => {
  onLCP((metric) => { metrics.lcp = metric.value })
  onFID((metric) => { metrics.fid = metric.value })
  onCLS((metric) => { metrics.cls = metric.value })
  onFCP((metric) => { metrics.fcp = metric.value })
  onTTFB((metric) => { metrics.ttfb = metric.value })
}

export const getMetrics = () => ({ ...metrics })
```

Las métricas se almacenan en sessionStorage durante la visita. Los targets de rendimiento establecidos son:

| Métrica | Target | Descripción |
|---------|--------|-------------|
| LCP | < 2.5s | Largest Contentful Paint - tiempo hasta elemento visual principal |
| FID | < 100ms | First Input Delay - latencia de primera interacción |
| CLS | < 0.1 | Cumulative Layout Shift - estabilidad visual |
| FCP | < 1.8s | First Contentful Paint - primer contenido visible |
| TTFB | < 600ms | Time to First Byte - respuesta inicial del servidor |

### Optimizaciones Implementadas

**Lazy Loading de Componentes**: Los modales, el chat de IA, los filtros avanzados y otros componentes secundarios se cargan mediante `React.lazy()` solo cuando el usuario los requiere:

```typescript
const ProductDetailModal = lazy(() => import('./ProductDetailModal'))
const AdvancedFiltersModal = lazy(() => import('./AdvancedFiltersModal'))
const AIChat = lazy(() => import('./AIChat'))
```

**Lazy Loading de Imágenes**: Las imágenes de productos implementan lazy loading nativo:

```typescript
<img
  src={product.image}
  loading="lazy"
  decoding="async"
  alt={product.name}
/>
```

**Selectores Memoizados**: Como se describió anteriormente, los selectores de Zustand con caches manuales previenen re-cálculos innecesarios.

**Throttling de Operaciones**: Las operaciones de carrito utilizan throttling de 100-200ms (definido en `constants/timing.ts`) para prevenir ráfagas de peticiones por clicks rápidos.

---

## Reflexión Final: La Digitalización de lo Social

pwaMenu no es simplemente un catálogo digital ni una aplicación de pedidos. Es una herramienta que respeta y amplifica la naturaleza inherentemente social de compartir una comida. El carrito compartido no es una limitación técnica sino una decisión de diseño que refleja cómo las personas realmente comen en grupo: viendo lo que otros piden, sugiriendo opciones, decidiendo juntos cuándo enviar el pedido.

Las protecciones de alérgenos van más allá de los checkboxes típicos porque una alergia severa no es una "preferencia": es una cuestión de seguridad que merece consideración seria. El reconocimiento de dispositivos ofrece personalización sin exigir registro porque la hospitalidad genuina no comienza con formularios.

La arquitectura técnica —React 19 con actualizaciones optimistas, Zustand con selectores estables, WebSocket con reconexión resiliente, Service Worker con estrategias de caché inteligentes— no existe por amor a la tecnología. Cada decisión responde a una pregunta fundamental: ¿cómo hace esto que la experiencia del comensal sea más agradable, más segura, o más conveniente?

Cuando la tecnología desaparece y solo queda la experiencia fluida de elegir y compartir comida con personas queridas, el software ha cumplido su propósito. pwaMenu aspira a ese ideal: ser tan invisible como una buena carta de restaurante, pero infinitamente más capaz.

---

*Documento técnico narrativo del proyecto pwaMenu. Última actualización: Febrero 2026.*
