# El Dashboard: Centro de Comando del Ecosistema Gastronómico

Versión 3.0 - Febrero 2026

## Prólogo: La Naturaleza del Panel de Administración

El Dashboard constituye el cerebro operativo de todo el sistema de gestión gastronómica. No se trata simplemente de una interfaz gráfica que permite visualizar datos, sino de un organismo digital vivo que respira al ritmo de las operaciones del restaurante. Cada click del administrador, cada actualización en tiempo real, cada decisión tomada desde este panel repercute instantáneamente en la cocina, en las mesas de los comensales y en los dispositivos de los mozos que recorren el salón.

Para comprender verdaderamente la magnitud de esta aplicación, debemos pensar en ella como el puente entre dos mundos: el mundo físico del restaurante con sus ollas humeantes, sus mozos apresurados y sus comensales hambrientos, y el mundo digital donde toda esa información se traduce en bits que viajan a la velocidad de la luz entre servidores, bases de datos y dispositivos móviles.

El Dashboard está construido sobre React 19, la versión más reciente del framework que introduce cambios paradigmáticos en la forma de manejar formularios mediante useActionState y el React Compiler que proporciona memoización automática. Utiliza Zustand 5 como gestor de estado, una biblioteca minimalista pero tremendamente poderosa que evita la complejidad ceremonial de Redux mientras mantiene la predictibilidad que las aplicaciones empresariales demandan. Y todo esto se orquesta sobre TypeScript en modo estricto, convirtiendo errores de tiempo de ejecución en errores de compilación que se detectan antes de que el código llegue a producción.

---

## Capítulo 1: La Estructura Modular del Proyecto

La carpeta Dashboard organiza su código fuente en subdirectorios claramente diferenciados por responsabilidad. Esta organización refleja los principios de separación de preocupaciones y permite que diferentes aspectos de la aplicación evolucionen independientemente sin interferir entre sí.

El directorio components contiene más de cuarenta componentes reutilizables organizados en subdirectorios temáticos. El subdirectorio auth contiene ProtectedRoute, un wrapper que verifica autenticación antes de renderizar rutas protegidas. El subdirectorio layout contiene Layout como contenedor principal con skip link para accesibilidad, Sidebar con navegación jerárquica colapsable, Header con información del usuario, y PageContainer como wrapper reutilizable para páginas. El subdirectorio tables contiene componentes especializados para gestión de mesas incluyendo TableSessionModal para ver detalles de sesiones activas, BulkTableModal para creación masiva, WaiterAssignmentModal para asignar mozos a sectores, y AddSectorDialog para agregar nuevos sectores. El subdirectorio ui contiene la biblioteca de componentes de interfaz: Modal con focus trap y soporte para modales anidados, Button con estados de carga y aria-busy, Input con validación y generación automática de identificadores, Select con opciones tipadas, Textarea para texto multilinea, Table con navegación por teclado, Badge y Card memoizados explícitamente para alto rendimiento, Toggle como switch, AllergenSelect y AllergenPresenceEditor para edición de alérgenos con tipos de presencia, BranchPriceInput para precios por sucursal, ProductSelect para selección múltiple de productos, ImageUpload con preview, Pagination con goto directo a página, ConfirmDialog con callback, HelpButton para ayuda contextual, ErrorBoundary para manejo de errores de UI, Toast para notificaciones temporales, LazyModal con imports dinámicos, CascadePreviewList para preview de eliminaciones en cascada, y TableSkeleton como placeholder de carga.

El directorio pages contiene diecinueve páginas con rutas definidas en el router, de las cuales dieciséis son completamente funcionales y tres son placeholders para funcionalidad futura. Dashboard sirve como landing con selector de sucursal. Restaurant permite configurar el restaurante. Branches gestiona sucursales. Tables implementa el grid de mesas con cinco estados y workflow completo. Staff administra personal con roles. Roles define roles disponibles. Orders es placeholder para órdenes detalladas. Kitchen presenta la vista de cocina con dos columnas para nuevos y en preparación. Recipes gestiona fichas técnicas. Ingredients administra el catálogo de ingredientes. Categories y Subcategories manejan la jerarquía del catálogo scoped por sucursal. Products es la página más compleja con gestión de productos incluyendo precios por rama, alérgenos con presencia, y múltiples relaciones. Prices permite actualización masiva de precios. Allergens administra alérgenos globales. Badges gestiona insignias promocionales. Seals administra sellos de certificación. PromotionTypes define tipos de promoción. Promotions gestiona promociones multi-sucursal. ProductExclusions configura exclusiones de categorías y subcategorías. Settings ofrece configuración de la aplicación con exportación e importación de datos. Sales y las páginas de historial son placeholders para estadísticas.

El directorio stores contiene veintiún stores de Zustand con middleware de persistencia, cada uno responsable de un dominio específico de la lógica de negocio. authStore maneja tokens JWT, scheduling de refresh, y sincronización entre pestañas via BroadcastChannel. branchStore mantiene sucursales con mapeo entre formato API y frontend. categoryStore y subcategoryStore gestionan la jerarquía del catálogo scoped por sucursal. productStore es el más complejo, manejando productos con alérgenos, precios por rama, y múltiples perfiles. allergenStore mantiene alérgenos globales. badgeStore y sealStore gestionan insignias y sellos predefinidos. tableStore rastrea mesas con estados de orden y sincronización WebSocket. staffStore administra personal con roles por sucursal. roleStore define roles globales. promotionStore y promotionTypeStore manejan promociones. orderHistoryStore mantiene historial de mesas archivadas. toastStore gestiona notificaciones temporales con máximo de cinco simultáneas. restaurantStore mantiene configuración del tenant. sectorStore define sectores de mesas. waiterAssignmentStore rastrea asignaciones diarias de mozos a sectores. recipeStore e ingredientStore gestionan recetas y el catálogo de ingredientes. exclusionStore maneja exclusiones de categorías. resetAllStores es una función helper que limpia todos los stores durante logout.

El directorio hooks contiene doce hooks personalizados que encapsulan lógica reutilizable. useFormModal elimina tres useState repetitivos gestionando estado de modal más formulario en una sola abstracción. useConfirmDialog elimina dos useState para diálogos de confirmación de eliminación. useAdminWebSocket escucha eventos ENTITY_CREATED, ENTITY_UPDATED, ENTITY_DELETED del backend para sincronizar stores. useTableWebSocket escucha eventos TABLE_*, ROUND_*, CHECK_* para actualizar mesas en tiempo real. useWebSocketConnection gestiona la conexión global al WebSocket. usePagination implementa paginación estándar con diez items por página. useInitializeData dispara fetch inicial de todos los stores cuando Layout monta. useInitializeStaffRoles carga roles durante startup. useDocumentTitle actualiza el título de la página. useFocusTrap implementa focus trap para modales usando AbortController para cleanup. useOptimisticMutation facilita mutaciones optimistas. useKeyboardShortcuts gestiona atajos de teclado globales.

El directorio services contiene tres servicios críticos. api.ts con cincuenta y seis kilobytes implementa el cliente REST completo con manejo de JWT, mutex para refresh de tokens que previene race conditions, AbortController para timeouts, y retry automático con backoff. websocket.ts con dieciocho kilobytes gestiona la conexión WebSocket con reconexión exponencial, heartbeat bidireccional, y throttling de eventos. cascadeService.ts con veintiocho kilobytes implementa eliminación en cascada con patrón snapshot/restore que permite rollback si algo falla.

El directorio types define contratos TypeScript para entidades, formularios, staff y roles. El directorio utils contiene utilidades: constants.ts con nombres de categorías especiales, claves de storage, y versiones de stores para migraciones; validation.ts con veintiocho kilobytes de validadores centralizados para números, teléfonos, emails y todas las entidades; sanitization.ts con funciones de prevención XSS para URLs, HTML y nombres de archivo; permissions.ts con helpers RBAC como isAdmin, canDelete, canCreateBranch; logger.ts para logging centralizado reemplazando console directos; helpContent.tsx con contenido de ayuda contextual en ReactNode; form.ts con utilidades de formularios; webVitals.ts para métricas Core Web Vitals; icons.ts con mapeo de iconos por categoría.

El directorio config contiene env.ts que valida variables de entorno. El directorio test contiene setup.ts con configuración de Vitest incluyendo mocks para matchMedia e IntersectionObserver.

---

## Capítulo 2: La Arquitectura del Estado Global

Los stores de Zustand forman el sistema circulatorio del Dashboard, bombeando datos hacia todos los rincones de la aplicación. Sin estos stores, cada componente sería una isla aislada, incapaz de comunicarse con los demás, repitiendo información que ya existe en otro lugar.

El sistema implementa veintiún stores especializados. Este número refleja la complejidad inherente de gestionar un restaurante moderno con múltiples sucursales, cientos de productos, decenas de empleados y miles de transacciones diarias.

Cada store sigue un patrón arquitectónico consistente. El estado incluye un array de items tipados, un booleano isLoading para indicar operaciones en progreso, un string error para mensajes de fallo, y un flag _isSubscribed para prevenir suscripciones duplicadas a WebSocket. Las acciones síncronas incluyen setItems para reemplazar el array completo, addItem para agregar un elemento, updateItem para modificar, y deleteItem para eliminar. Las acciones asíncronas incluyen fetchItems que obtiene datos del backend, createItemAsync, updateItemAsync, y deleteItemAsync que comunican con la API. Los handlers WebSocket incluyen handleWSEvent que procesa eventos entrantes y subscribeToEvents que retorna una función de cleanup para cancelar la suscripción. Finalmente, reset limpia el store durante logout.

El authStore merece atención especial por su complejidad. No solo almacena si el usuario está autenticado. Guarda el token JWT de acceso que expira cada quince minutos, la información del usuario incluyendo sus roles y las sucursales a las que tiene acceso, e implementa un sistema de refresco proactivo con jitter aleatorio para evitar que todos los usuarios del sistema intenten refrescar sus tokens exactamente al mismo momento. El refresh token ya no vive en el store; desde el fix SEC-09, se almacena exclusivamente como cookie HttpOnly que JavaScript no puede acceder, protegiéndolo de ataques XSS.

El productStore maneja el catálogo completo de productos con todas sus características. Cada producto tiene nombre, descripción, precio base, precios diferenciados por sucursal expresados en centavos para evitar errores de punto flotante, imágenes validadas contra ataques SSRF, alérgenos con diferentes niveles de presencia siguiendo el estándar EU 1169/2011, perfiles dietéticos con flags para vegetariano, vegano, sin gluten, sin lácteos, apto para celíacos, keto, y bajo en sodio, métodos de cocción con tiempos de preparación, perfiles de sabor y textura. El store debe mapear entre el formato de la API que usa identificadores numéricos y centavos, y el formato del frontend que usa strings y valores decimales para display.

El tableStore es particularmente complejo porque debe rastrear no solo el estado estático de cada mesa sino también su estado dinámico en tiempo real. Una mesa puede estar libre mostrada en verde, ocupada en rojo, con pedido solicitado, con pedido cumplido, o con la cuenta solicitada en morado. Pero además debe saber cuántas rondas de pedidos tiene, en qué estado está cada ronda desde pending hasta served, si hay pedidos listos que necesitan entregarse mientras otros siguen cocinándose. Todo esto cambia constantemente a través de eventos WebSocket que llegan desde el gateway.

---

## Capítulo 3: El Patrón de Selectores Estables

React 19 introdujo mejoras en la detección de cambios que, paradójicamente, pueden causar problemas si no se manejan correctamente. Cuando un componente usa un store de Zustand, React necesita saber si el valor devuelto ha cambiado para decidir si debe re-renderizar el componente. Si el store devuelve un array vacío nuevo cada vez que se llama al selector, React interpreta esto como un cambio, aunque semánticamente el valor sea el mismo.

La solución implementada es elegante en su simplicidad. En lugar de crear un array vacío nuevo cada vez, el sistema define constantes inmutables como EMPTY_PRODUCTS, EMPTY_TABLES, EMPTY_ROLES que se reutilizan. De esta manera, cuando no hay productos, el selector siempre devuelve exactamente la misma referencia en memoria, y React puede determinar que no hay cambio sin necesidad de comparar el contenido.

Este patrón se extiende a selectores más complejos. Cuando se necesita filtrar o transformar datos, se implementan cachés manuales que recuerdan el resultado anterior y solo recalculan cuando los datos de entrada realmente han cambiado. Los selectores parametrizados como selectById usan un Map para cachear funciones selectoras por parámetro, evitando crear nuevas funciones en cada render. Los selectores filtrados como selectByBranch retornan funciones que React puede optimizar con useShallow cuando es necesario prevenir re-renders por nuevas referencias de array.

La regla cardinal que todo el código respeta es nunca destructurar el resultado de useStore. En lugar de escribir destructuración directa del store, siempre se usan selectores explícitos que extraen exactamente los datos necesarios. Esto garantiza que el componente solo re-renderice cuando los datos específicos que usa realmente cambian.

---

## Capítulo 4: Persistencia y Migraciones de Stores

Los stores críticos implementan persistencia en localStorage mediante el middleware persist de Zustand. Esto permite que el usuario cierre la pestaña y al volver encuentre sus datos locales intactos, mejorando la experiencia especialmente en conexiones inestables.

El sistema de migraciones maneja la evolución del schema de datos entre versiones. Cada store tiene una versión numérica definida en STORE_VERSIONS. Cuando el código evoluciona y necesita un nuevo campo o cambio de estructura, se incrementa la versión. La función migrate recibe el estado persistido y la versión anterior, aplicando transformaciones necesarias para actualizar al formato actual.

Las migraciones típicas incluyen limpiar datos mock que tenían IDs con cierto patrón, agregar nuevos campos con valores por defecto a entidades existentes, y transformar estructuras cuando el modelo cambia. Por ejemplo, cuando se agregó el sistema de presencia de alérgenos, la migración convirtió el array simple de allergen_ids al nuevo formato con objetos que incluyen allergen_id y presence_type.

Las versiones actuales reflejan la madurez de cada store. branchStore está en versión 5, categoryStore y subcategoryStore en versión 4, productStore en versión 6 siendo el más evolucionado por su complejidad, tableStore en versión 7 por los múltiples refinamientos del sistema de estados, mientras stores más simples como badgeStore y sealStore permanecen en versión 1 por su estabilidad.

---

## Capítulo 5: El Sistema de Autenticación

La seguridad en el Dashboard no es un añadido superficial sino un pilar fundamental que permea cada capa de la aplicación. El sistema utiliza JSON Web Tokens para autenticar usuarios, pero la implementación va mucho más allá de simplemente almacenar un token y enviarlo con cada petición.

Cuando un usuario ingresa sus credenciales, el servidor devuelve un access token de corta vida que expira en quince minutos, diseñado para minimizar el daño si es interceptado. El refresh token ya no viaja en el cuerpo de la respuesta; siguiendo el fix SEC-09, el backend lo establece como una cookie HttpOnly, lo que significa que JavaScript no puede accederla, protegiéndola de ataques XSS. El access token se guarda en memoria para peticiones, pero el refresh token permanece exclusivamente en la cookie segura donde ningún script malicioso puede tocarlo.

El sistema implementa refresco proactivo, lo que significa que no espera a que el token expire para intentar renovarlo. Aproximadamente catorce minutos después del último refresco, el cliente inicia una solicitud de renovación. Pero si todos los usuarios refrescaran exactamente a los catorce minutos, podrían crear picos de carga en el servidor. Por eso se añade jitter, una variación aleatoria de más o menos dos minutos, distribuyendo las solicitudes de refresco en el tiempo. La función getRefreshIntervalWithJitter calcula este intervalo tomando el base de catorce minutos, generando un número aleatorio, y sumando la variación para obtener un valor entre doce y dieciséis minutos diferente para cada usuario y cada ciclo.

Cuando el refresco falla, el sistema tiene hasta tres intentos antes de decidir que la sesión debe terminar. Esto maneja casos donde una interrupción momentánea de red podría causar un fallo temporal. Solo después de agotar los reintentos el sistema cierra la sesión y redirige al usuario a la página de login.

---

## Capítulo 6: La Sincronización entre Pestañas

Un usuario moderno frecuentemente tiene múltiples pestañas del mismo sitio abiertas simultáneamente. Esto crea desafíos: si el usuario cierra sesión en una pestaña, las otras deberían cerrar sesión también. Si se refresca el token en una pestaña, las otras no deberían intentar refrescar innecesariamente.

El Dashboard implementa esta coordinación mediante la API BroadcastChannel, un mecanismo del navegador que permite que diferentes contextos de la misma aplicación se comuniquen entre sí. El canal se llama dashboard-auth-sync y transporta tres tipos de mensajes: TOKEN_REFRESHED cuando una pestaña completó un refresco exitoso, LOGOUT cuando una pestaña cerró sesión, y LOGIN cuando una pestaña inició sesión.

Cuando una pestaña realiza login, transmite un mensaje LOGIN que otras pestañas reciben y actúan en consecuencia, sincronizando el estado. Cuando una pestaña cierra sesión, transmite LOGOUT y todas las demás pestañas ejecutan su propia limpieza local sin hacer llamadas adicionales al servidor.

La función performLocalLogout existe específicamente para este escenario. Cuando una pestaña recibe el mensaje LOGOUT de otra pestaña, no debe volver a transmitir LOGOUT porque eso crearía un loop infinito. En su lugar, llama performLocalLogout que limpia el estado local, desconecta el WebSocket, y redirige al login sin transmitir nada.

El mutex de refresh previene caos cuando múltiples peticiones fallan con 401 simultáneamente. Una variable global refreshPromise comienza como null. Cuando la primera petición detecta que necesita refresh, verifica si refreshPromise es null. Si lo es, crea una nueva Promise que representa la operación de refresh, la asigna a refreshPromise, y comienza el trabajo real. Las otras peticiones, cuando detectan que necesitan refresh, ven que refreshPromise ya existe y simplemente esperan esa misma Promise en lugar de iniciar su propio refresh. El detalle crucial es que refreshPromise se asigna síncronamente antes de cualquier operación asíncrona.

---

## Capítulo 7: La Comunicación en Tiempo Real

Si los stores son el sistema circulatorio del Dashboard, el WebSocket es su sistema nervioso. Los datos pueden fluir lentamente a través de peticiones HTTP, pero las señales de tiempo real necesitan velocidad instantánea. Cuando un comensal escanea un código QR y se sienta en una mesa, el administrador debe ver ese cambio reflejado inmediatamente.

La conexión WebSocket se establece hacia el gateway en el puerto 8001, autenticándose con el mismo token JWT que se usa para las peticiones HTTP. El servicio websocket.ts encapsula toda la complejidad de mantener esta conexión viva. Expone métodos simples: connect para establecer conexión, disconnect para cerrarla limpiamente, softDisconnect para cerrarla temporalmente preservando listeners, on para registrar un callback para un tipo de evento específico, y updateToken para reconectar con un token nuevo después de un refresh.

El heartbeat bidireccional detecta conexiones muertas. Cada treinta segundos, el cliente envía un mensaje ping y espera un pong de respuesta del servidor dentro de diez segundos. Si el pong no llega, asume que la conexión está muerta, cierra el WebSocket forzosamente, y programa una reconexión. Esto detecta el caso donde ni siquiera llega un evento de cierre porque la conexión simplemente dejó de funcionar sin notificarlo.

Cuando la conexión se cierra inesperadamente, el servicio no intenta reconectar inmediatamente. Implementa backoff exponencial: espera un segundo para el primer intento, dos para el segundo, cuatro para el tercero, ocho para el cuarto, hasta un máximo de treinta segundos. El jitter añade variación aleatoria a cada intervalo, evitando el efecto manada donde miles de clientes reconectan exactamente al mismo momento después de una caída del servidor.

No todos los cierres deben resultar en reconexión. El protocolo WebSocket define códigos de cierre que el servidor puede usar para indicar la razón. El servicio mantiene un Set de códigos no recuperables: 4001 indica AUTH_FAILED y significa token inválido, 4003 indica FORBIDDEN y significa permisos insuficientes, 4029 indica RATE_LIMITED. Cuando el servidor cierra con uno de estos códigos, el servicio no programa reconexión.

Los eventos se distribuyen mediante un sistema de listeners tipado. Los tipos incluyen TABLE_SESSION_STARTED, TABLE_STATUS_CHANGED, TABLE_CLEARED para mesas; ROUND_PENDING, ROUND_CONFIRMED, ROUND_SUBMITTED, ROUND_IN_KITCHEN, ROUND_READY, ROUND_SERVED, ROUND_CANCELED, ROUND_ITEM_DELETED para pedidos; SERVICE_CALL_CREATED, SERVICE_CALL_ACKED, SERVICE_CALL_CLOSED para llamados de servicio; CHECK_REQUESTED, CHECK_PAID para cuenta.

El patrón de ref resuelve un problema sutil de closures. Si el callback del listener captura estado del componente, ese estado queda congelado al momento del registro. La solución es mantener el handler actual en un ref, registrar una función que llama handlerRef.current, y actualizar el ref en cada render. El listener siempre llama al handler más reciente sin necesidad de re-registrarse.

---

## Capítulo 8: Los Formularios con React 19

React 19 introdujo useActionState, un hook que cambia fundamentalmente cómo se manejan los formularios. En versiones anteriores, manejar un formulario requería múltiples estados separados. Con useActionState, el formulario se trata como una máquina de estados finitos.

El hook recibe una función de acción y un estado inicial, y devuelve tres cosas: el estado actual que contiene errores y flag de éxito, una función de acción para pasar al elemento form, y un booleano isPending que indica si la acción está en progreso.

La función de acción recibe dos parámetros: el estado previo que permite implementar lógica acumulativa, y un objeto FormData que contiene todos los valores del formulario. FormData es una API nativa del navegador que el form element construye automáticamente al hacer submit, incluyendo todos los inputs con atributo name.

En el Dashboard, cada página CRUD implementa este patrón. La función submitAction es un useCallback que extrae los campos del FormData, los valida según las reglas de negocio usando los validadores centralizados, y retorna un nuevo estado. Si hay errores de validación, retorna un objeto con la propiedad errors mapeando nombres de campo a mensajes de error y isSuccess en false. Si la validación pasa, intenta crear o actualizar la entidad en el backend. Si tiene éxito, retorna isSuccess en true. Si falla, captura el error, lo registra con el logger centralizado, y retorna un mensaje de error general.

El componente observa el estado retornado. Cuando isSuccess se vuelve verdadero y el modal está abierto, ejecuta código para cerrar el modal. Los errores se muestran junto a cada campo correspondiente mediante la prop error que cada Input y Select acepta.

FormData es excelente para campos simples pero tiene limitaciones con estructuras complejas. La solución es híbrida. Los campos simples se leen directamente de FormData usando formData.get. Los campos complejos como arrays de alérgenos con presencia o listas de precios por sucursal se mantienen en estado local del componente usando useState, y la función submitAction los lee de ese estado.

---

## Capítulo 9: El Hook useFormModal

Manejar un modal con un formulario implica coordinar múltiples piezas de estado: si el modal está abierto, los datos del formulario, si estamos creando o editando, y cuál es el elemento siendo editado. Repetir esta lógica en cada una de las dieciséis páginas CRUD sería tedioso y propenso a errores.

El hook useFormModal encapsula toda esta lógica en una abstracción reutilizable de ciento treinta líneas. Acepta los datos iniciales del formulario como parámetro y retorna un objeto con todas las piezas necesarias: isOpen indica si el modal está abierto, formData contiene los datos actuales del formulario, selectedItem es el elemento siendo editado o null si estamos creando, setFormData permite actualizar campos individuales, openCreate abre el modal en modo creación con los datos iniciales, openEdit abre el modal en modo edición con los datos del elemento existente, close cierra el modal y resetea el estado después de la animación de cierre, y reset restaura los datos iniciales sin cerrar el modal.

Las funciones openCreate y openEdit aceptan opcionalmente datos custom. openCreate puede recibir un objeto parcial que se mergeará con los datos iniciales, útil cuando queremos pre-seleccionar una categoría basándonos en el filtro actual. openEdit puede recibir datos de formulario custom en lugar de usar el elemento directamente, útil cuando el formato del elemento no coincide exactamente con el formato del formulario.

La función close implementa un detalle sutil pero importante. Primero setea isOpen a false, lo que hace que el modal comience su animación de cierre. Luego programa un setTimeout de doscientos milisegundos, el tiempo típico de una animación de fade out, y solo entonces resetea formData y selectedItem. Si reseteáramos inmediatamente, el usuario vería el contenido del modal cambiar durante la animación de cierre.

El hook useConfirmDialog sigue un patrón similar más simple para diálogos de confirmación de eliminación, eliminando dos useState por cada página que lo usa.

---

## Capítulo 10: La Gestión de Productos

Un producto en el sistema gastronómico no es simplemente un nombre con un precio. Es una entidad rica que encapsula información nutricional, dietética, alérgenos, métodos de preparación, costos, márgenes, y disponibilidad que puede variar entre sucursales. La página de Productos refleja esta complejidad mientras mantiene una interfaz manejable.

El formulario de producto tiene más de cuarenta campos organizados en secciones lógicas. La sección básica incluye nombre obligatorio, descripción opcional, imagen validada contra SSRF, categoría y subcategoría que definen dónde aparece en el menú. La sección de precio permite configurar un precio base único o precios diferenciados por sucursal mediante el toggle use_branch_prices. La sección de atributos incluye badges promocionales y sellos de certificación. La sección de alérgenos permite seleccionar múltiples alérgenos con diferentes tipos de presencia: contains indica que definitivamente contiene el alérgeno, may_contain indica posibilidad de contaminación cruzada, free_from certifica ausencia con precauciones.

Debajo hay una sección colapsable de campos avanzados. El perfil dietético permite marcar vegetariano, vegano, sin gluten, sin lácteos, apto para celíacos, keto, o bajo en sodio. Los ingredientes se seleccionan del catálogo centralizado y pueden marcarse como principales o secundarios. Los métodos de cocción incluyen horneado, frito, a la parrilla, crudo, hervido, al vapor, salteado, braseado. Los tiempos de preparación y cocción se expresan en minutos. Los perfiles de sabor describen suave, intenso, dulce, salado, ácido, amargo, umami, picante. Los perfiles de textura describen crocante, cremoso, tierno, firme, esponjoso, gelatinoso, granular.

El componente BranchPriceInput maneja precios por sucursal. Por defecto, el producto tiene un precio base único. Al activar el toggle aparece una lista de todas las sucursales activas donde el administrador puede establecer precios individuales y marcar disponibilidad. Los precios se almacenan en centavos para evitar errores de punto flotante. La conversión ocurre en la frontera entre frontend y backend, multiplicando por cien al enviar y dividiendo al recibir.

La tabla de productos muestra columnas optimizadas para escaneo visual rápido. La columna de imagen muestra un thumbnail o placeholder. La columna de producto muestra nombre en negrita con descripción truncada e íconos de estrella y trending si está destacado o es popular. La columna de precio es inteligente: si usa precio único muestra ese valor, si usa precios por sucursal calcula y muestra el rango mínimo-máximo evitando redundancia cuando todos son iguales. La columna de categoría muestra badge con categoría y subcategoría. La columna de alérgenos muestra hasta tres íconos emoji con indicador de más si hay adicionales. Las columnas de acciones muestran botones condicionales según permisos.

---

## Capítulo 11: La Gestión de Mesas en Tiempo Real

Una mesa transita por múltiples estados durante su jornada de servicio. Comienza libre disponible para nuevos comensales mostrada en verde. Cuando alguien escanea el código QR y abre una sesión pasa a ocupada mostrada en rojo. Cuando los comensales ordenan, el estado de pedido indica si hay pendiente, en cocina, o listo. Finalmente, cuando piden la cuenta entra en cuenta_solicitada mostrada en morado.

Pero el estado de la mesa es solo parte de la historia. Una mesa ocupada puede tener múltiples rondas de pedidos en diferentes estados. La primera ronda puede estar lista mientras la segunda sigue cocinándose y la tercera acaba de enviarse. El sistema necesita un estado agregado que resuma la situación para que el mozo sepa qué acción tomar.

El cálculo de estado agregado en tableStore sigue reglas de prioridad cuidadosamente diseñadas. La prioridad más alta es el estado combinado ready_with_kitchen: si hay alguna ronda lista y alguna que no está lista, se muestra este estado especial con badge naranja que indica al mozo que hay items para llevar pero que debe volver por más. La siguiente prioridad es pending si todas las rondas están pendientes de confirmación. Luego confirmed si todas están confirmadas pero no enviadas. Luego submitted o in_kitchen que se tratan igual como en cocina. Finalmente ready si todas están listas, y served si todas fueron servidas.

La página de Mesas agrupa las mesas por sector usando encabezados visuales. Cada sector tiene un header que muestra nombre, cantidad de mesas, nombres de mozos asignados hoy, y un indicador de urgencia si alguna mesa necesita atención. Las tarjetas de mesa son compactas pero informativas. El número domina visualmente porque es el identificador que todos usan. El color de fondo indica estado base. Un badge superpuesto indica estado del pedido con colores específicos: amarillo para pendiente, azul para confirmado o en cocina, naranja para listo más cocina, verde para todo listo.

Las animaciones comunican cambios y urgencia. Una mesa que acaba de recibir un nuevo pedido pulsa en amarillo con animate-pulse-warning. Una mesa que pidió la cuenta pulsa en morado con animate-pulse-urgent. Una mesa cuyo estado acaba de cambiar destella brevemente en azul con animate-status-blink que dura 1.5 segundos. El estado combinado ready_with_kitchen tiene su propia animación naranja de 5 segundos llamada animate-ready-kitchen-blink que asegura que esta situación operativamente importante no pase desapercibida.

Al clickear una mesa ocupada se abre el TableSessionModal que muestra los detalles completos de la sesión activa. El header muestra número de mesa, sector, y estado. La primera sección muestra los comensales registrados. La sección principal muestra las rondas de pedidos con header por ronda incluyendo número, estado con badge, y tiempo transcurrido. Los items se agrupan por categoría siguiendo el orden natural: primero bebidas, luego entradas, luego principales, finalmente postres. Cada categoría tiene un header colapsable y un ícono de despacho para tracking visual. Cada item muestra cantidad, nombre, precio, y comensal que lo ordenó con notas especiales en texto pequeño.

---

## Capítulo 12: El Personal y Sus Roles

El sistema de personal implementa un modelo de control de acceso basado en roles que determina qué puede ver y hacer cada usuario. Cuatro roles forman la jerarquía: WAITER para mozos, KITCHEN para personal de cocina, MANAGER para gerentes de sucursal, y ADMIN para administradores del sistema.

Un ADMIN tiene acceso total. Puede crear, editar y eliminar cualquier entidad en cualquier sucursal. Puede asignar cualquier rol a cualquier empleado, incluyendo crear otros administradores. Ve todas las estadísticas, todas las sucursales, todos los empleados.

Un MANAGER tiene acceso amplio pero restringido a sus sucursales asignadas. Puede crear y editar empleados, productos, categorías, mesas, pero solo en las sucursales donde tiene rol de gerente. Crucialmente, no puede asignar el rol ADMIN a nadie, preservando la jerarquía de que solo administradores crean administradores. Tampoco puede eliminar entidades, una restricción que previene pérdida accidental de datos valiosos.

Un KITCHEN puede acceder a la página de cocina donde ve los pedidos que debe preparar. Puede gestionar recetas porque ese es conocimiento de su dominio. Pero no tiene acceso a gestión de personal, mesas, ventas, ni otras áreas administrativas.

Un WAITER tiene acceso mínimo al Dashboard porque su herramienta principal es pwaWaiter. Si accede al Dashboard, puede ver información básica pero no modificar configuraciones.

La página de Personal muestra una tabla con empleados de la sucursal seleccionada. La tabla muestra nombre completo, rol traducido al español, email, teléfono, DNI, fecha de ingreso formateada según locale argentina, y estado con badge de color. El campo de búsqueda implementa debounce usando useDeferredValue de React 19. La búsqueda filtra por nombre, apellido, email, o DNI.

El formulario incluye campos para nombre, apellido, email, teléfono, DNI, fecha de ingreso, estado activo, sucursal, y rol. El selector de sucursal muestra diferentes opciones según quien lo usa: para administradores todas las sucursales, para gerentes solo las sucursales donde tienen acceso. El selector de rol no muestra ADMIN si el usuario actual es gerente.

Las restricciones de seguridad real están en el backend. Si un gerente intentara asignar rol ADMIN manipulando el request HTTP, el backend lo rechazaría. El frontend oculta opciones que el usuario no debería usar mejorando experiencia, pero confiar solo en el frontend sería inseguro.

---

## Capítulo 13: La Vista de Cocina

La página de Cocina presenta un diseño de dos columnas que refleja el flujo de trabajo real de una cocina profesional. La columna izquierda titulada Nuevos muestra pedidos en estado SUBMITTED que son pedidos que el administrador envió a cocina y están esperando que un cocinero los tome. La columna derecha titulada En Cocina muestra pedidos en estado IN_KITCHEN que son pedidos que algún cocinero ya está preparando.

Un detalle importante es que la cocina no ve todos los estados del pedido. Los estados PENDING y CONFIRMED son invisibles para la cocina. Esto es intencional: esos estados representan pedidos que aún no deberían prepararse porque no fueron autorizados para envío a cocina.

Cada pedido se representa como una tarjeta compacta diseñada para escaneo rápido en el ambiente de alta presión. El código de mesa domina visualmente porque es el identificador que el cocinero usa para saber dónde irá el pedido. Debajo aparece la cantidad de items y el tiempo transcurrido. Un badge indica estado. Un anillo rojo envuelve la tarjeta si el pedido es urgente: más de quince minutos en SUBMITTED o más de veinte en IN_KITCHEN.

Las tarjetas son clickeables y accesibles por teclado. Al hacer click se abre un modal con el detalle completo. El modal muestra código de mesa, estado, tiempo, y cada item con cantidad, nombre, y crucialmente las notas especiales que aparecen prominentemente en rojo para que no se pasen por alto.

Al pie del modal hay un botón de acción que depende del estado. Si está SUBMITTED dice Marcar como En Cocina. Si está IN_KITCHEN dice Marcar como Listo. Después de transicionar a READY el pedido desaparece de la vista porque ya no es responsabilidad del cocinero.

Antes de renderizar cualquier contenido, la página verifica que el usuario tenga rol apropiado. La verificación usa los selectores del authStore: el usuario debe tener rol KITCHEN, MANAGER, o ADMIN. Si tiene solo WAITER se muestra una página de acceso denegado.

---

## Capítulo 14: Las Promociones y el Tiempo

Las promociones añaden una dimensión temporal a los productos. Un Happy Hour no es simplemente un descuento; es un descuento que aplica solo entre las 17:00 y las 20:00, solo en ciertos días, solo hasta cierta fecha. El sistema debe capturar estas restricciones y aplicarlas correctamente.

Cada promoción tiene fecha de inicio y fecha de fin que delimitan su vigencia en días calendario. Pero además tiene hora de inicio y hora de fin que delimitan las horas del día en que aplica. Una promoción puede estar configurada del 1 al 31 de enero, pero solo de 18:00 a 21:00 cada día.

El estado de una promoción se calcula dinámicamente. Si is_active es false, está desactivada manualmente independientemente de fechas y horas. Si la fecha actual está fuera del rango, está inactiva por tiempo. Si la fecha está dentro pero la hora está fuera, también está inactiva. Solo cuando todas las condiciones se cumplen la promoción está activa.

Una promoción agrupa varios productos en un combo con precio especial. El componente ProductSelect permite seleccionar productos del catálogo y especificar la cantidad de cada uno. El precio de la promoción es independiente de la suma de precios de los productos individuales, permitiendo tanto ofertas donde el combo es más barato como bundles premium.

Las promociones pueden aplicar a todas las sucursales o solo a algunas. El componente BranchCheckboxes muestra todas las sucursales activas como checkboxes individuales. Esta flexibilidad permite estrategias de marketing diferenciadas por ubicación.

La validación incluye reglas temporales especiales. Al crear una promoción nueva, la fecha de inicio debe ser hoy o futura. La fecha de fin debe ser igual o posterior a la de inicio. Si inicio y fin son el mismo día, la hora de fin debe ser posterior a la de inicio. Al editar una promoción existente, las validaciones son más permisivas.

---

## Capítulo 15: El Catálogo Jerárquico

El menú se organiza en una jerarquía de tres niveles. Las categorías son agrupaciones amplias: Bebidas, Entradas, Platos Principales, Postres. Las subcategorías son divisiones más finas dentro de cada categoría: dentro de Bebidas podríamos tener Gaseosas, Cervezas Nacionales, Cervezas Importadas, Vinos Tintos. Los productos son los items individuales que los comensales pueden ordenar.

Las categorías pertenecen a sucursales. Esto significa que cada sucursal puede tener su propia estructura de menú si es necesario, aunque en la práctica la mayoría usa la misma estructura con variaciones solo en disponibilidad de productos.

Existe una categoría especial llamada HOME que el menú público usa internamente para productos destacados en la página principal, pero que no debe aparecer en las listas administrativas. Los selectores y filtros excluyen HOME_CATEGORY_NAME de todas las vistas.

Las páginas de Categorías y Subcategorías siguen el patrón CRUD establecido. Una tabla lista las entidades existentes. Un botón Nueva abre el modal de creación. Íconos de editar y eliminar en cada fila permiten modificar o borrar. Cada categoría tiene nombre obligatorio, orden numérico, ícono emoji opcional, imagen opcional, y estado activo o inactivo.

Eliminar una categoría tiene efectos en cascada. Si tiene subcategorías, eliminarla dejaría esas subcategorías huérfanas. Si esas subcategorías tienen productos, los productos también quedarían huérfanos. Antes de proceder, el componente CascadePreviewList analiza qué se eliminará y muestra un resumen al usuario. La eliminación es soft, marcando is_active como false en lugar de borrar físicamente los registros.

---

## Capítulo 16: Ingredientes y Recetas

El sistema de ingredientes implementa una estructura de dos niveles. Los ingredientes principales son componentes directos como Tomate, Pollo, Harina. Pero algunos ingredientes marcados como procesados contienen sub-ingredientes. Salsa BBQ es un ingrediente procesado que contiene Tomate, Vinagre, Azúcar Morena, Especias, Salsa de Soja. Esta descomposición es crucial para trazabilidad de alérgenos: la soja en la salsa BBQ debe propagarse a cualquier producto que use esa salsa.

Los ingredientes se organizan en grupos para facilitar navegación: Carnes, Verduras, Condimentos, Lácteos, Granos. La página de Ingredientes muestra una lista donde cada ingrediente principal puede expandirse para revelar sus sub-ingredientes.

Las recetas van más allá de listar ingredientes. Son documentos estructurados que capturan todo el conocimiento necesario para preparar un plato consistentemente: ingredientes con cantidades exactas, pasos de preparación con instrucciones detalladas, tiempos de preparación y cocción, porciones esperadas, notas del chef con tips profesionales, información de almacenamiento, sugerencias de presentación.

Una receta tiene más de cuarenta campos opcionales organizados en secciones. La sección de información básica incluye nombre, descripción, sucursal, categoría, subcategoría, tipo de cocina, nivel de dificultad, tiempos, y porciones. La sección de ingredientes permite agregar componentes del catálogo o escribir ingredientes ad-hoc con cantidad, unidad, y notas. La sección de preparación contiene los pasos como lista ordenada que se puede reordenar. Las notas del chef son texto libre para trucos del oficio.

Una receta puede derivarse a un producto del catálogo. Este proceso crea un producto nuevo vinculado a la receta original. El producto hereda automáticamente los alérgenos calculados de los ingredientes de la receta. Las recetas también pueden ingerirse al sistema RAG para alimentar el chatbot inteligente, generando embeddings vectoriales que permiten búsqueda semántica.

---

## Capítulo 17: La Validación Centralizada

El archivo validation.ts con veintiocho kilobytes contiene validadores centralizados para todas las entidades del sistema. Esta centralización tiene beneficios multiplicativos: la lógica de validación está en un solo lugar, los errores se formatean consistentemente, y las reglas de negocio se documentan implícitamente.

Los validadores de números verifican diferentes condiciones: isValidNumber verifica que sea número válido no NaN, isPositiveNumber verifica que sea mayor que cero, isNonNegativeNumber verifica que sea cero o positivo. Estos helpers se usan extensivamente en validadores de entidades.

Cada validador de entidad retorna un objeto con isValid booleano y errors como mapa de campo a mensaje de error. validateProduct por ejemplo verifica que nombre tenga longitud entre 2 y 100 caracteres, que descripción no exceda 500 caracteres, que precio sea positivo si no usa precios por sucursal, que cada precio por sucursal sea positivo, que category_id exista, que URLs de imagen pasen validación SSRF.

Los límites de validación están definidos en VALIDATION_LIMITS: MIN_NAME_LENGTH es 2, MAX_NAME_LENGTH es 100, MAX_DESCRIPTION_LENGTH es 500, MAX_ADDRESS_LENGTH es 200, MAX_ORDER_VALUE es 9999, MAX_CAPACITY es 999, MAX_PRICE es 999999999, MAX_TOASTS es 5.

Los validadores de tiempo verifican formato HH:mm mediante expresión regular. Los validadores de email verifican formato básico. Los validadores de teléfono permiten varios formatos argentinos. Los validadores de DNI verifican longitud y que contenga solo dígitos.

---

## Capítulo 18: Seguridad y Sanitización

El archivo sanitization.ts contiene funciones de prevención XSS y SSRF. sanitizeImageUrl valida URLs de imagen verificando protocolo https o http, bloqueando IPs internas y rangos reservados como localhost, 127.0.0.1, 10.x.x.x, 172.16-31.x.x, 192.168.x.x, y el endpoint de metadata de cloud 169.254.169.254. Si la URL es inválida, retorna un fallback proporcionado.

sanitizeHtml escapa caracteres especiales HTML como menor que, mayor que, ampersand, comillas simples y dobles. Esto previene inyección de HTML en cualquier lugar donde se muestre contenido del usuario.

isSafeFilename verifica que nombres de archivo no contengan caracteres peligrosos como barras o puntos dobles que podrían permitir directory traversal. stripDangerousChars limpia caracteres que podrían ser problemáticos en diferentes contextos.

La validación de importación JSON implementa múltiples capas. MAX_IMPORT_FILE_SIZE limita a 5MB. Se verifica que la extensión sea .json. El contenido parseado pasa por validateImportData que verifica la estructura esperada recursivamente.

El archivo permissions.ts exporta funciones declarativas que encapsulan la lógica de autorización. isAdmin verifica rol ADMIN, isManager verifica MANAGER, isAdminOrManager verifica cualquiera, canDelete retorna true solo si isAdmin porque managers no pueden eliminar. Las funciones específicas verifican permisos para operaciones concretas: canCreateProduct, canEditProduct, canCreateStaff, canEditStaff verifican admin o manager; canCreateBranch requiere admin. Las funciones de acceso a páginas verifican si el usuario debería poder ver ciertas secciones: canAccessKitchenPage retorna true si tiene rol KITCHEN, MANAGER, o ADMIN.

---

## Capítulo 19: Optimización de Rendimiento

El Dashboard implementa lazy loading usando React.lazy y Suspense para cada una de sus diecinueve páginas. El archivo App.tsx define cada página como un import dinámico. Esta sintaxis indica al bundler Vite que cree un chunk separado para cada página. El resultado son múltiples archivos JavaScript pequeños en lugar de uno gigante. Cuando el usuario navega a una ruta, React detecta que la página no está cargada, muestra el fallback de Suspense mientras descarga el chunk, y una vez descargado renderiza.

El React Compiler está habilitado en vite.config.ts mediante el plugin babel-plugin-react-compiler con target 19. Esto proporciona memoización automática de componentes y callbacks, reduciendo la necesidad de useMemo y useCallback explícitos. Sin embargo, componentes de alto re-render como Modal usado dieciséis veces, Card usado más de cien veces, Badge usado más de cien veces, y Table usado veinte veces mantienen memoización explícita con React.memo logrando reducciones de treinta a treinta y cinco por ciento en renders.

La optimización LCP trata la primera imagen de sucursal con atributos loading eager, fetchPriority high, y decoding async para que se descargue inmediatamente con alta prioridad. Las imágenes subsecuentes reciben loading lazy para que no se descarguen hasta que estén cerca del viewport.

La configuración PWA con VitePWA implementa service worker con autoUpdate, manifest para instalación, y workbox con patrones de caché. Los fonts de Google se cachean con estrategia CacheFirst por un año. El build final resulta en aproximadamente 246 kilobytes totales que se comprimen a 77.6 kilobytes gzipped.

Los chunks manuales en rollupOptions separan react-vendor con React, ReactDOM y React Router; icons con lucide-react; y state con Zustand. Esto permite caché de navegador más efectivo cuando se actualizan partes del código sin invalidar todo.

---

## Capítulo 20: El Flujo Completo de un Pedido

Para entender cómo todas las piezas del Dashboard encajan, sigamos el viaje completo de un pedido desde que el comensal se sienta hasta que paga.

Un grupo de cuatro amigos llega al restaurante y el hostess les asigna la mesa 5 del sector Interior. Uno de ellos saca su teléfono y escanea el código QR. El código contiene una URL que abre pwaMenu con parámetros que identifican la mesa y sucursal.

pwaMenu envía una petición al backend para crear sesión. El backend crea un registro de TableSession, genera un table token, y publica el evento TABLE_SESSION_STARTED al canal WebSocket de la sucursal.

El Dashboard, conectado vía WebSocket al endpoint /ws/admin, recibe el evento. El handler en tableStore procesa el evento, encuentra la mesa 5, y actualiza su status a ocupada. El componente de mesas detecta el cambio y re-renderiza la tarjeta con fondo rojo y animación de destello azul.

Los cuatro amigos exploran el menú en sus teléfonos, cada uno conectado a la misma sesión. Añaden items a sus carritos que se sincronizan en tiempo real. Cuando están listos, uno propone enviar el pedido. Los otros confirman. El pedido se envía al backend.

El backend crea un Round con estado PENDING registrando qué items pidió cada comensal. Publica ROUND_PENDING a los canales de admin y waiters.

El Dashboard recibe ROUND_PENDING. El tableStore actualiza la mesa 5 agregando la ronda al diccionario roundStatuses con estado pending, recalcula orderStatus como pending, setea hasNewOrder a true. La tarjeta re-renderiza con pulso amarillo indicando nuevo pedido pendiente.

El mozo Alberto recibe la notificación en pwaWaiter. Se acerca a la mesa 5 y verifica el pedido con los comensales. Confirma desde pwaWaiter. El backend transiciona a CONFIRMED y publica ROUND_CONFIRMED.

El Dashboard recibe ROUND_CONFIRMED. El tableStore actualiza roundStatuses a confirmed, setea hasNewOrder a false. La tarjeta deja de pulsar amarillo y muestra badge azul Confirmado.

El gerente ve que la mesa 5 tiene pedido confirmado. Hace click en la tarjeta, se abre TableSessionModal. Hace click en Enviar a Cocina. El Dashboard envía petición POST al backend para transicionar a SUBMITTED. El backend actualiza y publica ROUND_SUBMITTED a los canales de admin, waiters, y kitchen.

El Dashboard recibe ROUND_SUBMITTED. La tarjeta muestra badge azul En Cocina. La página de Cocina recibe el evento y el pedido aparece en la columna Nuevos.

María la cocinera ve el nuevo pedido. Hace click, ve el detalle con todos los items y notas especiales. Hace click en Marcar como En Cocina. El backend transiciona a IN_KITCHEN y publica ROUND_IN_KITCHEN.

El Dashboard actualiza. La página de Cocina mueve el pedido a la columna En Cocina. Quince minutos después María hace click en Marcar como Listo. El backend transiciona a READY y publica ROUND_READY.

El Dashboard recibe ROUND_READY. La tarjeta de mesa 5 muestra badge verde Listo. En la página de Cocina el pedido desaparece. Alberto recibe notificación, recoge los platos, y los lleva a la mesa.

Después de disfrutar su comida, los amigos piden la cuenta desde pwaMenu. El backend publica CHECK_REQUESTED. El Dashboard recibe el evento. La tarjeta cambia a fondo morado y empieza a pulsar con animate-pulse-urgent.

Alberto lleva la cuenta. Los amigos pagan en efectivo. Alberto marca el pago como recibido. El backend procesa el pago y eventualmente publica TABLE_CLEARED.

El Dashboard recibe TABLE_CLEARED. El tableStore limpia el estado de la mesa 5: status vuelve a libre, roundStatuses se vacía, orderStatus vuelve a none. La tarjeta vuelve a verde, disponible para los próximos comensales.

El ciclo completo fue visible en tiempo real en el Dashboard. El gerente pudo monitorear el progreso sin moverse de su escritorio.

---

## Capítulo 21: Testing y Calidad

La configuración de Vitest en vitest.config.ts establece el entorno de pruebas. El plugin de React con Babel incluye el React Compiler. El entorno es jsdom para simular browser. Los archivos de setup en test/setup.ts configuran mocks necesarios.

El setup extiende expect con matchers de jest-dom. Mockea window.matchMedia para componentes que usan media queries. Mockea IntersectionObserver para lazy loading. Ejecuta cleanup después de cada test para limpiar el DOM.

Los tests verifican funcionamiento de hooks personalizados. useFormModal tiene doce tests que verifican inicialización con valores por defecto, apertura en modo creación, apertura en modo edición con datos del item, cierre con reset diferido, y manejo de datos custom. usePagination tiene tests que verifican cálculo correcto de páginas, reset a página uno cuando los datos cambian, y que items paginados sean el subset correcto.

Los tests de stores verifican que las acciones modifiquen el estado correctamente, que los selectores retornen datos esperados, y que las migraciones transformen estados viejos al formato actual.

El coverage reporta en texto, JSON y HTML. Excluye node_modules, directorio test, archivos de definición de tipos, archivos de configuración, mockData, y dist. El proyecto tiene cien tests con tiempo de ejecución de aproximadamente 3.5 segundos.

---

## Epílogo: El Dashboard como Espejo del Negocio

Habiendo recorrido cada rincón del Dashboard con el nivel de detalle que merece, podemos apreciar cómo esta aplicación no es simplemente código que muestra datos. Es un modelo digital del restaurante físico, diseñado para que los operadores puedan gestionar su negocio efectivamente desde cualquier lugar con conexión a internet.

El catálogo de productos modela la oferta culinaria con toda su complejidad: precios diferenciados por sucursal que reflejan realidades económicas distintas, alérgenos con niveles de presencia que protegen la salud de los comensales, perfiles dietéticos que permiten filtrado avanzado, vinculación con recetas que preserva conocimiento institucional.

El sistema de mesas modela el servicio de salón con estados que reflejan el flujo real de una comida: mesa libre esperando comensales, ocupada cuando llegan, múltiples rondas de pedidos que pueden estar en distintos estados simultáneamente, cuenta solicitada cuando terminan. Las animaciones comunican urgencia sin requerir atención constante.

El sistema de personal modela la organización humana con roles que reflejan jerarquías reales y permisos que implementan políticas de acceso coherentes. La asignación de mozos a sectores permite que cada empleado se enfoque en su zona sin ruido de otras áreas.

La comunicación en tiempo real modela la inmediatez que el servicio de restaurante requiere. Cuando algo cambia, todos los actores relevantes lo saben instantáneamente. El mozo sabe que llegó un pedido. La cocina sabe qué preparar. El gerente tiene visibilidad total.

La autenticación y los permisos modelan la confianza y responsabilidad que una organización deposita en sus empleados. Un mozo tiene las herramientas que necesita pero no acceso a configuraciones que no le corresponden. Un gerente puede operar su sucursal pero no afectar otras. Un administrador tiene poder total pero con la responsabilidad correspondiente.

Y quizás esa es la lección más importante de esta exploración: el mejor software no es el que tiene la arquitectura más elegante o el código más conciso, sino el que modela fielmente el dominio para el que fue creado y sirve genuinamente a las personas que lo usan. El Dashboard del sistema Integrador es software bien hecho no porque use React 19 o Zustand 5, sino porque entiende profundamente qué es un restaurante, cómo funciona, y qué necesitan las personas que lo operan.

Cada store existe porque hay un aspecto del negocio que necesita rastrearse. Cada página existe porque hay una tarea que necesita realizarse. Cada evento WebSocket existe porque hay información que necesita fluir en tiempo real. Cada permiso existe porque hay decisiones sobre quién puede hacer qué. La tecnología está al servicio del negocio, no al revés.

En última instancia, cuando el gerente mira el Dashboard y ve un mosaico de mesas verdes, rojas, y moradas, está viendo el pulso de su restaurante traducido a luz. Cuando hace click para enviar un pedido a cocina, está moviendo átomos en el mundo físico a través de bits en el mundo digital. Cuando revisa las ventas del día, está convirtiendo miles de transacciones individuales en entendimiento accionable.

El Dashboard es, en el sentido más profundo, un puente entre mundos. Y construir puentes que soporten el peso del uso real, día tras día, es de lo que se trata la ingeniería de software profesional.
