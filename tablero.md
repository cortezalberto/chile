# El Dashboard: Centro de Comando del Ecosistema Gastronómico

## Prólogo: La Naturaleza del Panel de Administración

El Dashboard constituye el cerebro operativo de todo el sistema de gestión gastronómica. No se trata simplemente de una interfaz gráfica que permite visualizar datos, sino de un organismo digital vivo que respira al ritmo de las operaciones del restaurante. Cada click del administrador, cada actualización en tiempo real, cada decisión tomada desde este panel repercute instantáneamente en la cocina, en las mesas de los comensales y en los dispositivos de los mozos que recorren el salón.

Para comprender verdaderamente la magnitud de esta aplicación, debemos pensar en ella como el puente entre dos mundos: el mundo físico del restaurante con sus ollas humeantes, sus mozos apresurados y sus comensales hambrientos, y el mundo digital donde toda esa información se traduce en bits que viajan a la velocidad de la luz entre servidores, bases de datos y dispositivos móviles.

El Dashboard está construido sobre React 19, la versión más reciente del framework de Facebook que introduce cambios paradigmáticos en la forma de manejar formularios y efectos. Utiliza Zustand 5 como gestor de estado, una biblioteca minimalista pero tremendamente poderosa que evita la complejidad ceremonial de Redux mientras mantiene la predictibilidad que las aplicaciones empresariales demandan. Y todo esto se orquesta sobre TypeScript, el superset de JavaScript que añade tipos estáticos, convirtiendo errores de tiempo de ejecución en errores de compilación que se detectan antes de que el código llegue a producción.

---

## Capítulo I: La Arquitectura del Estado Global

### El Corazón que Bombea Datos

Imagina por un momento que el Dashboard es un organismo vivo. Si las páginas son los órganos que realizan funciones específicas, entonces los stores de Zustand son el sistema circulatorio que bombea datos hacia todos los rincones de la aplicación. Sin estos stores, cada componente sería una isla aislada, incapaz de comunicarse con los demás, repitiendo información que ya existe en otro lugar.

El sistema implementa veintidós stores especializados, cada uno responsable de un dominio específico de la lógica de negocio. No es casualidad que sean tantos; este número refleja la complejidad inherente de gestionar un restaurante moderno con múltiples sucursales, cientos de productos, decenas de empleados y miles de transacciones diarias.

El authStore, por ejemplo, no solo almacena si el usuario está autenticado o no. Guarda el token JWT que expira cada quince minutos, el refresh token que permite obtener nuevos tokens de acceso, la información del usuario incluyendo sus roles y las sucursales a las que tiene acceso, y además implementa un sistema de refresco proactivo con jitter aleatorio para evitar que todos los usuarios del sistema intenten refrescar sus tokens exactamente al mismo momento, lo cual podría sobrecargar el servidor.

El productStore maneja el catálogo completo de productos con todas sus características: nombre, descripción, precio base, precios diferenciados por sucursal expresados en centavos para evitar errores de punto flotante, imágenes validadas contra ataques SSRF, alérgenos con diferentes niveles de presencia, perfiles dietéticos, métodos de cocción, tiempos de preparación, perfiles de sabor y textura. Cada producto es un microcosmos de información que debe sincronizarse con el backend y mostrarse correctamente en todas las interfaces.

El tableStore es particularmente complejo porque debe rastrear no solo el estado estático de cada mesa sino también su estado dinámico en tiempo real. Una mesa puede estar libre, ocupada, con pedido solicitado, con pedido cumplido o con la cuenta solicitada. Pero además debe saber cuántas rondas de pedidos tiene, en qué estado está cada ronda, si hay pedidos listos que necesitan entregarse mientras otros siguen cocinándose. Todo esto cambia constantemente a través de eventos WebSocket que llegan desde el gateway.

### El Patrón de los Selectores Estables

Aquí es donde la ingeniería se encuentra con la sutileza. React 19 introdujo mejoras en la detección de cambios que, paradójicamente, pueden causar problemas si no se manejan correctamente. Cuando un componente usa un store de Zustand, React necesita saber si el valor devuelto ha cambiado para decidir si debe re-renderizar el componente. Si el store devuelve un array vacío nuevo cada vez que se llama al selector, React interpreta esto como un cambio, aunque semánticamente el valor sea el mismo: un array sin elementos.

La solución implementada es elegante en su simplicidad. En lugar de crear un array vacío nuevo cada vez, el sistema define constantes inmutables como EMPTY_PRODUCTS, EMPTY_TABLES, EMPTY_ROLES que se reutilizan. De esta manera, cuando no hay productos, el selector siempre devuelve exactamente la misma referencia en memoria, y React puede determinar que no hay cambio sin necesidad de comparar el contenido.

Este patrón se extiende a selectores más complejos. Cuando se necesita filtrar o transformar datos, se implementan cachés manuales que recuerdan el resultado anterior y solo recalculan cuando los datos de entrada realmente han cambiado. Es una forma de memoización manual que complementa los hooks nativos de React y garantiza rendimiento óptimo incluso con miles de entidades en el estado.

### Los Veintidós Stores en Detalle

El ecosistema de stores forma una red interconectada donde cada nodo cumple una función específica pero depende de otros para contexto. El authStore almacena la identidad del usuario, sus tokens de autenticación, sus roles y las sucursales a las que tiene acceso. Cuando el usuario hace login, este store recibe la respuesta del servidor y la procesa, extrayendo el access token que vivirá en memoria por quince minutos, notando que el refresh token ahora vive en una cookie HttpOnly que JavaScript no puede tocar, y guardando los datos del usuario para que otros componentes sepan qué mostrar.

El branchStore mantiene la lista de sucursales del restaurante y rastrea cuál está actualmente seleccionada. Esta selección es fundamental porque casi todas las operaciones están scoped a una sucursal: los productos que se muestran, las mesas que se ven, el personal que aparece. Cuando el usuario cambia de sucursal, este store actualiza su estado y todos los componentes que dependen de él se re-renderizan automáticamente con los datos de la nueva sucursal.

El categoryStore y el subcategoryStore trabajan en tándem para mantener la jerarquía del catálogo. Las categorías pertenecen a sucursales y las subcategorías pertenecen a categorías. Cuando se elimina una categoría, el subcategoryStore debe limpiar las subcategorías huérfanas, y el productStore debe limpiar los productos que pertenecían a esas subcategorías. Esta cascada de limpieza se orquesta desde servicios de cascada que coordinan múltiples stores.

El productStore es quizás el más complejo de todos. Un producto tiene nombre, descripción, imagen, categoría, subcategoría, precio base, precios por sucursal, lista de alérgenos con tipos de presencia, perfil dietético con siete flags booleanos, métodos de cocción con tiempos de preparación, perfiles de sabor y textura, badges promocionales, sellos de certificación, vinculación opcional con recetas, y estado activo o inactivo. El store debe mapear entre el formato de la API que usa identificadores numéricos y centavos, y el formato del frontend que usa strings y valores decimales.

El tableStore rastrea mesas con toda su complejidad operativa. Cada mesa tiene un identificador, un número visible, una capacidad, un sector al que pertenece, un estado que puede ser libre, ocupada, solicitó pedido, pedido cumplido, o cuenta solicitada. Pero además tiene un estado de orden agregado que resume todas las rondas de pedidos activas, un diccionario que mapea cada ronda a su estado individual, flags para animaciones de UI como statusChanged y hasNewOrder, y opcionalmente el nombre del mozo que confirmó el último pedido.

El staffStore mantiene la lista de empleados con sus datos personales y laborales: nombre, apellido, email, teléfono, DNI, fecha de ingreso, estado activo, y crucialmente su rol y las sucursales donde trabaja. Un empleado puede tener diferentes roles en diferentes sucursales, o el mismo rol en varias sucursales, lo que se modela a través de branch_roles.

El allergenStore, badgeStore, sealStore, ingredientStore, recipeStore, promotionStore y promotionTypeStore mantienen los diferentes catálogos de configuración que enriquecen los productos y permiten filtrado avanzado en el menú público.

El waiterAssignmentStore rastrea qué mozos están asignados a qué sectores cada día, información crítica para el ruteo de notificaciones WebSocket y para que cada mozo vea solo las mesas de sus sectores.

El orderHistoryStore mantiene el historial de órdenes archivadas para reportes y análisis. El roleStore define los roles disponibles aunque en la práctica usa valores hardcodeados del backend. El restaurantStore mantiene la configuración del tenant raíz.

El toastStore es especial porque no persiste datos de negocio sino que gestiona las notificaciones temporales que informan al usuario sobre el resultado de sus acciones, manteniendo una cola de hasta cinco mensajes simultáneos que se auto-eliminan después de unos segundos.

---

## Capítulo II: El Sistema de Autenticación y Seguridad

### La Danza de los Tokens

La seguridad en el Dashboard no es un añadido superficial sino un pilar fundamental que permea cada capa de la aplicación. El sistema utiliza JSON Web Tokens para autenticar usuarios, pero la implementación va mucho más allá de simplemente almacenar un token y enviarlo con cada petición.

Cuando un usuario ingresa sus credenciales, el servidor devuelve dos tokens: un access token de corta vida que expira en quince minutos, diseñado para minimizar el daño si es interceptado. El refresh token ya no viaja en el cuerpo de la respuesta; el backend lo establece como una cookie HttpOnly, lo que significa que JavaScript no puede accederla, protegiéndola de ataques XSS. El access token se guarda en memoria y en localStorage, pero el refresh token permanece exclusivamente en la cookie segura donde ningún script malicioso puede tocarlo.

El sistema implementa refresco proactivo, lo que significa que no espera a que el token expire para intentar renovarlo. Aproximadamente catorce minutos después del último refresco, el cliente inicia una solicitud de renovación. Pero aquí viene un detalle sutil: si todos los usuarios refrescaran exactamente a los catorce minutos, podrían crear picos de carga en el servidor. Por eso se añade jitter, una variación aleatoria de más o menos dos minutos, distribuyendo las solicitudes de refresco en el tiempo.

La implementación del jitter es matemáticamente simple pero conceptualmente importante. La función getRefreshIntervalWithJitter toma el intervalo base de catorce minutos, genera un número aleatorio entre menos uno y uno, lo multiplica por el rango de jitter de dos minutos, y suma el resultado al intervalo base. El resultado es un valor entre doce y dieciséis minutos, diferente para cada usuario y para cada ciclo de refresco.

Cuando el refresco falla, el sistema no se rinde inmediatamente. Tiene hasta tres intentos antes de decidir que la sesión debe terminar. Esto maneja casos donde una interrupción momentánea de red podría causar un fallo temporal. Solo después de agotar los reintentos el sistema cierra la sesión y redirige al usuario a la página de login.

### La Sincronización entre Pestañas

Un usuario moderno frecuentemente tiene múltiples pestañas del mismo sitio abiertas simultáneamente. Esto crea desafíos interesantes: si el usuario cierra sesión en una pestaña, las otras deberían cerrar sesión también. Si se refresca el token en una pestaña, las otras no deberían intentar refrescar innecesariamente.

El Dashboard implementa esta coordinación mediante la API BroadcastChannel, un mecanismo del navegador que permite que diferentes contextos de la misma aplicación se comuniquen entre sí. El canal se llama dashboard-auth-sync y transporta tres tipos de mensajes: TOKEN_REFRESHED cuando una pestaña completó un refresco exitoso, LOGOUT cuando una pestaña cerró sesión, y LOGIN cuando una pestaña inició sesión.

Cuando una pestaña realiza login, transmite un mensaje LOGIN que otras pestañas reciben y actúan en consecuencia, recargando la página para sincronizar el estado. Cuando una pestaña cierra sesión, transmite LOGOUT y todas las demás pestañas ejecutan su propia limpieza local sin hacer llamadas adicionales al servidor. Esta sincronización ocurre en milisegundos, mucho más rápido que cualquier enfoque basado en polling de localStorage.

La función performLocalLogout existe específicamente para este escenario. Cuando una pestaña recibe el mensaje LOGOUT de otra pestaña, no debe volver a transmitir LOGOUT porque eso crearía un loop infinito. En su lugar, llama performLocalLogout que limpia el estado local, desconecta el WebSocket, y redirige al login sin transmitir nada.

### El Mutex que Previene Caos

Un problema sutil pero crítico puede ocurrir cuando múltiples peticiones fallan con 401 simultáneamente. Imaginemos que el usuario tiene la página abierta y hace una acción que dispara tres peticiones paralelas. Si el token acaba de expirar, las tres recibirán 401. Sin coordinación, las tres intentarían refrescar el token al mismo tiempo, causando tres peticiones de refresh que probablemente dos fallarían porque el token ya fue refrescado y el viejo refresh token fue invalidado.

La solución es un mutex implementado con una Promise compartida. Una variable global refreshPromise comienza como null. Cuando la primera petición detecta que necesita refresh, verifica si refreshPromise es null. Si lo es, crea una nueva Promise que representa la operación de refresh, la asigna a refreshPromise, y comienza el trabajo real de refrescar. Las otras peticiones, cuando detectan que necesitan refresh, ven que refreshPromise ya existe y simplemente esperan esa misma Promise en lugar de iniciar su propio refresh. Cuando el refresh completa, se asigna null a refreshPromise y todas las peticiones en espera obtienen el resultado y proceden.

El detalle crucial es que refreshPromise se asigna síncronamente antes de cualquier operación asíncrona. Si se asignara después del await que inicia el fetch de refresh, habría una ventana de tiempo donde otra petición podría ver refreshPromise como null e iniciar su propio refresh. Al asignar síncronamente primero, garantizamos que todas las peticiones subsecuentes la verán inmediatamente.

### El Bug Silencioso del Loop Infinito de Logout

Un bug potencial merece mención especial por su sutileza. El cliente API tiene lógica automática para manejar errores 401: cuando una petición retorna 401, intenta refrescar el token y reintentar la petición original. Esto funciona perfectamente para operaciones normales que fallan porque el token expiró.

Pero consideremos qué sucede durante el logout. Si el token ya expiró cuando el usuario hace click en "Cerrar Sesión", la petición a /api/auth/logout retornará 401. La lógica de retry detecta el 401, intenta refrescar el token, y reintenta el logout. Este nuevo intento también puede fallar con 401 si el refresh token fue blacklisteado, causando otro intento de refresh, y así ad infinitum.

La solución está en el tercer parámetro de fetchAPI. Normalmente es true, indicando que debe reintentar en caso de 401. Pero authAPI.logout pasa false como tercer parámetro, indicando que no debe reintentar. El código simplemente intenta hacer logout, ignora cualquier error porque el usuario ya quiere desconectarse y no importa si el backend acepta o no, y limpia el estado local de todos modos.

---

## Capítulo III: La Comunicación en Tiempo Real

### El WebSocket como Sistema Nervioso

Si los stores son el sistema circulatorio del Dashboard, el WebSocket es su sistema nervioso. Los datos pueden fluir lentamente a través de peticiones HTTP, pero las señales de tiempo real necesitan velocidad instantánea. Cuando un comensal escanea un código QR y se sienta en una mesa, el administrador debe ver ese cambio reflejado inmediatamente, no después de refrescar la página o esperar una sincronización periódica.

La conexión WebSocket se establece hacia el gateway en el puerto 8001, autenticándose con el mismo token JWT que se usa para las peticiones HTTP. El servicio websocket.ts encapsula toda la complejidad de mantener esta conexión viva, manejar reconexiones, y distribuir eventos a los listeners registrados.

El servicio expone métodos simples: connect para establecer conexión, disconnect para cerrarla limpiamente, softDisconnect para cerrarla temporalmente preservando listeners, on para registrar un callback para un tipo de evento específico, y updateToken para reconectar con un token nuevo después de un refresh. Internamente, maneja un WebSocket nativo del navegador, un sistema de heartbeat, lógica de reconexión con backoff exponencial, y un registro de listeners por tipo de evento.

### El Heartbeat Bidireccional

Las conexiones WebSocket pueden cerrarse silenciosamente por timeouts de red, proxies intermedios, o simplemente inactividad. Para detectar estas desconexiones fantasma, el servicio implementa un heartbeat bidireccional. Cada treinta segundos, el cliente envía un mensaje ping y espera un pong de respuesta del servidor.

El heartbeat se implementa con dos partes. Un setInterval que cada treinta segundos verifica si la conexión está abierta y si lo está envía el mensaje ping. Un timeout que se inicia cuando se envía el ping y se cancela cuando llega el pong. Si el pong no llega en diez segundos, el timeout expira y asume que la conexión está muerta.

Cuando se detecta una conexión muerta, el servicio cierra el WebSocket forzosamente y programa una reconexión. Esto es diferente a cuando el servidor cierra la conexión limpiamente: en ese caso llega el evento onclose con un código de cierre. El heartbeat detecta el caso donde ni siquiera llega un evento de cierre porque la conexión simplemente dejó de funcionar sin notificarlo.

### El Backoff Exponencial con Jitter

Cuando la conexión se cierra inesperadamente, el servicio no intenta reconectar inmediatamente. Si hay un problema de red o el servidor está sobrecargado, reconexiones inmediatas empeorarían la situación. En su lugar, implementa backoff exponencial: espera un segundo para el primer intento, dos segundos para el segundo, cuatro para el tercero, ocho para el cuarto, y así sucesivamente hasta un máximo de treinta segundos.

El jitter añade variación aleatoria a cada intervalo de espera. En lugar de esperar exactamente cuatro segundos, espera entre tres y cinco segundos por ejemplo. Esto evita el efecto manada donde miles de clientes reconectan exactamente al mismo momento después de una caída del servidor, potencialmente causando otra caída por la carga súbita.

El servicio intenta hasta cincuenta reconexiones antes de rendirse y notificar que la conexión no puede restablecerse. Con backoff exponencial, cincuenta intentos cubren un período considerable de tiempo, suficiente para sobrevivir a la mayoría de interrupciones temporales.

### Códigos de Cierre que Significan No Insistas

No todos los cierres de conexión deben resultar en reconexión. El protocolo WebSocket define códigos de cierre que el servidor puede usar para indicar la razón del cierre. El servicio mantiene un Set de códigos no recuperables: 4001 indica AUTH_FAILED y significa que el token es inválido, 4003 indica FORBIDDEN y significa que el usuario no tiene permisos para este endpoint, 4029 indica RATE_LIMITED y significa que el cliente envió demasiados mensajes.

Cuando el servidor cierra con uno de estos códigos, el servicio no programa reconexión. En su lugar, notifica al callback onMaxReconnectReached si existe uno registrado, permitiendo que el código que usa el servicio tome una acción apropiada como mostrar un mensaje al usuario o redirigir al login.

### El Sistema de Eventos Tipado

Los eventos que llegan por WebSocket tienen tipos definidos: TABLE_SESSION_STARTED, TABLE_STATUS_CHANGED, TABLE_CLEARED para eventos de mesas; ROUND_PENDING, ROUND_CONFIRMED, ROUND_SUBMITTED, ROUND_IN_KITCHEN, ROUND_READY, ROUND_SERVED, ROUND_CANCELED, ROUND_ITEM_DELETED para eventos de pedidos; SERVICE_CALL_CREATED, SERVICE_CALL_ACKED, SERVICE_CALL_CLOSED para llamados de servicio; CHECK_REQUESTED, CHECK_PAID para eventos de cuenta.

Cada tipo de evento tiene una estructura esperada en su payload. Un evento de mesa incluye table_id y opcionalmente branch_id. Un evento de ronda incluye round_id, table_id, y opcionalmente datos del pedido. El servicio no valida estrictamente esta estructura porque el backend es la fuente de verdad, pero los tipos TypeScript documentan la estructura esperada para que los consumidores sepan qué datos pueden acceder.

Los listeners se registran para tipos específicos de eventos o para el tipo especial asterisco que recibe todos los eventos. Cuando llega un evento, el servicio primero notifica a los listeners del asterisco y luego a los listeners del tipo específico. Cada listener es una función que recibe el evento completo como parámetro.

### La Prevención de Memory Leaks

Un problema común con sistemas de eventos es la acumulación de listeners que nunca se limpian. Si un componente se monta, registra un listener, se desmonta sin cancelar el registro, y se vuelve a montar, hay dos listeners para el mismo evento. Con el tiempo, esto puede causar memory leaks y comportamiento duplicado.

El método on retorna una función de cleanup que remueve el listener registrado. Es responsabilidad del componente llamar esta función en su cleanup del useEffect. Pero como protección adicional, cuando el último listener de un tipo de evento se remueve, el servicio también elimina el Set vacío del mapa de listeners, previniendo acumulación de Sets vacíos.

El patrón de ref resuelve otro problema sutil. Si el callback del listener captura estado del componente en su closure, ese estado queda congelado al momento del registro. Cuando el estado cambia, el callback sigue usando el valor viejo. La solución es mantener el handler actual en un ref, registrar una función que llama handlerRef.current, y actualizar el ref en cada render. El listener siempre llama al handler más reciente sin necesidad de re-registrarse.

---

## Capítulo IV: El Formulario Moderno con React 19

### useActionState: La Revolución de los Formularios

React 19 introdujo useActionState, un hook que cambia fundamentalmente cómo se manejan los formularios. En versiones anteriores, manejar un formulario requería múltiples estados: uno para los datos, otro para los errores, otro para indicar si se está enviando, otro para el resultado. Cada uno de estos estados debía actualizarse manualmente en diferentes momentos del ciclo de vida del formulario.

Con useActionState, el formulario se trata como una máquina de estados finitos. El hook recibe una función de acción y un estado inicial, y devuelve tres cosas: el estado actual que contiene errores y flag de éxito, una función de acción para pasar al form element, y un booleano isPending que indica si la acción está en progreso.

La función de acción recibe dos parámetros: el estado previo que permite implementar lógica acumulativa, y un objeto FormData que contiene todos los valores del formulario. FormData es una API nativa del navegador que el form element construye automáticamente al hacer submit, incluyendo todos los inputs con name dentro del formulario.

En el Dashboard, cada página CRUD implementa este patrón. La función submitAction es un useCallback que extrae los campos del FormData, los valida según las reglas de negocio, y retorna un nuevo estado. Si hay errores de validación, retorna un objeto con la propiedad errors mapeando nombres de campo a mensajes de error y isSuccess en false. Si la validación pasa, intenta crear o actualizar la entidad en el backend. Si tiene éxito, retorna un objeto con isSuccess en true. Si falla, captura el error, lo registra con el logger, y retorna un objeto con un mensaje de error general.

El componente observa el estado retornado por useActionState. Cuando isSuccess se vuelve verdadero y el modal está abierto, ejecuta código para cerrar el modal, resetear el formulario, y limpiar cualquier estado relacionado. Los errores se muestran junto a cada campo correspondiente mediante la prop error que cada Input y Select acepta.

### El Manejo de Campos Complejos

FormData es excelente para campos simples como strings y números, pero tiene limitaciones con estructuras complejas. Un array de alérgenos con sus tipos de presencia, una lista de precios por sucursal, o los productos de una promoción no pueden representarse directamente en FormData.

La solución es híbrida. Los campos simples se leen directamente de FormData usando formData.get. Los campos complejos se mantienen en estado local del componente usando useState, y la función submitAction los lee de ese estado en lugar de FormData. Para que el formulario funcione correctamente con ambos tipos de campos, se incluyen inputs hidden con los valores simples y se confía en el estado del componente para los valores complejos.

Por ejemplo, en el formulario de productos, name, description, price, category_id se leen de FormData. Pero allergens es un array de objetos con allergen_id y presence_type, branch_prices es un array de objetos con branch_id, price, y is_active, y estos se leen del estado formData del componente. La función submitAction tiene acceso a ambos porque el estado del componente está en scope cuando se define el useCallback.

### El Hook useFormModal

Manejar un modal con un formulario implica coordinar múltiples piezas de estado: si el modal está abierto, los datos del formulario, si estamos creando o editando, y cuál es el elemento siendo editado. Repetir esta lógica en cada una de las dieciséis páginas CRUD sería tedioso y propenso a errores.

El hook useFormModal encapsula toda esta lógica en una abstracción reutilizable de ciento treinta líneas. Acepta los datos iniciales del formulario como parámetro y retorna un objeto con todas las piezas necesarias: isOpen indica si el modal está abierto, formData contiene los datos actuales del formulario, selectedItem es el elemento siendo editado o null si estamos creando, setFormData permite actualizar campos individuales, openCreate abre el modal en modo creación con los datos iniciales, openEdit abre el modal en modo edición con los datos del elemento existente, close cierra el modal y resetea el estado después de la animación de cierre, y reset restaura los datos iniciales sin cerrar el modal.

Las funciones openCreate y openEdit aceptan opcionalmente datos custom. openCreate puede recibir un objeto parcial que se mergeará con los datos iniciales, útil cuando queremos pre-seleccionar una categoría basándonos en el filtro actual. openEdit puede recibir datos de formulario custom en lugar de usar el elemento directamente, útil cuando el formato del elemento no coincide exactamente con el formato del formulario.

La función close implementa un detalle sutil pero importante. Primero setea isOpen a false, lo que hace que el modal comience su animación de cierre. Luego programa un setTimeout de doscientos milisegundos, el tiempo típico de una animación de fade out, y solo entonces resetea formData y selectedItem. Si reseteáramos inmediatamente, el usuario vería el contenido del modal cambiar durante la animación de cierre, lo cual es visualmente disruptivo.

---

## Capítulo V: La Gestión de Productos en Profundidad

### El Producto como Entidad Multifacética

Un producto en el sistema gastronómico no es simplemente un nombre con un precio. Es una entidad rica que encapsula información nutricional, dietética, alérgenos, métodos de preparación, costos, márgenes, y disponibilidad que puede variar entre sucursales. La página de Productos refleja esta complejidad mientras mantiene una interfaz manejable.

El formulario de producto tiene más de cuarenta campos organizados en secciones lógicas. La sección básica incluye nombre obligatorio, descripción opcional, imagen validada contra SSRF, categoría y subcategoría que definen dónde aparece en el menú. La sección de precio permite configurar un precio base o precios diferenciados por sucursal. La sección de atributos incluye badges promocionales y sellos de certificación. La sección de alérgenos permite seleccionar múltiples alérgenos con diferentes tipos de presencia.

Debajo de todo esto hay una sección colapsable de campos avanzados que la mayoría de productos no necesita pero que productos especializados aprovechan. El perfil dietético permite marcar si el producto es vegetariano, vegano, sin gluten, sin lácteos, apto para celíacos, keto, o bajo en sodio. Estas no son meras etiquetas; alimentan los filtros que los comensales usan en el menú público para encontrar opciones compatibles con sus restricciones.

Los ingredientes se seleccionan de un catálogo centralizado y pueden marcarse como principales o secundarios. Un plato puede tener pollo como ingrediente principal y especias como secundario. Esta distinción afecta cómo se muestra la información y cómo se calculan alérgenos heredados de ingredientes.

Los métodos de cocción se seleccionan de otro catálogo: horneado, frito, a la parrilla, crudo, hervido, al vapor, salteado, braseado. Cada método puede afectar cómo se presenta el producto a comensales con preferencias específicas. Alguien que evita alimentos fritos puede filtrar productos por método de cocción y ver solo opciones horneadas o a la parrilla. También se puede indicar si el producto usa aceite en su preparación, relevante para ciertos regímenes dietéticos.

Los tiempos de preparación y cocción se expresan en minutos. Esta información puede usarse para estimaciones de espera en el menú digital o para planificación de cocina durante servicios de alto volumen.

Los perfiles de sabor y textura describen características sensoriales: suave, intenso, dulce, salado, ácido, amargo, umami, picante para sabores; crocante, cremoso, tierno, firme, esponjoso, gelatinoso, granular para texturas. Estos perfiles permiten recomendaciones personalizadas y búsquedas por características.

### Los Precios Diferenciados por Sucursal

Un restaurante con múltiples sucursales frecuentemente necesita precios diferentes en cada ubicación. El alquiler en una zona céntrica es más caro que en un barrio residencial. Los costos de personal varían. La competencia local dicta lo que el mercado acepta pagar. Un producto que es loss leader en una sucursal puede tener margen normal en otra.

El componente BranchPriceInput maneja esta complejidad elegantemente. Por defecto, el producto tiene un precio base único que aplica a todas las sucursales. Pero al activar el toggle "usar precios por sucursal", aparece una lista de todas las sucursales activas donde el administrador puede establecer precios individuales y marcar si el producto está disponible en cada una.

Los precios se almacenan en centavos para evitar errores de punto flotante. JavaScript, como muchos lenguajes, no puede representar exactamente ciertos valores decimales. El valor 0.1 no existe exactamente en punto flotante IEEE 754; existe una aproximación muy cercana pero no exacta. Cuando se suman muchos valores con estas pequeñas imprecisiones, los errores se acumulan. Almacenando en centavos como enteros, un precio de ciento veinticinco pesos con cincuenta centavos es simplemente el número 12550, exacto sin ambigüedad.

La conversión ocurre en la frontera entre frontend y backend. Cuando el usuario ingresa 125.50 en el campo de precio, el frontend lo multiplica por cien y lo redondea antes de enviarlo a la API. Cuando los datos vuelven de la API, el frontend divide por cien para mostrar el valor legible. Esta conversión es invisible para el usuario pero crucial para la integridad de los datos.

### El Sistema de Alérgenos con Niveles de Presencia

Los alérgenos no son simplemente presente o ausente. Siguiendo el estándar europeo EU 1169/2011, el sistema modela diferentes niveles de presencia. "contains" significa que el producto definitivamente contiene el alérgeno como ingrediente directo. "may_contain" indica posibilidad de contaminación cruzada porque se prepara en equipos compartidos o en la misma cocina que productos con ese alérgeno. "free_from" certifica que el producto está libre del alérgeno y se prepara con precauciones para evitar contaminación.

El componente AllergenPresenceEditor permite no solo seleccionar qué alérgenos aplican sino especificar el tipo de presencia para cada uno. La interfaz muestra todos los alérgenos activos del sistema, cada uno con un selector de presencia que puede ser ninguno, contiene, puede contener, o libre de.

Esta granularidad permite a los comensales tomar decisiones informadas. Alguien con intolerancia leve a la lactosa podría aceptar productos "may_contain" pero evitar productos que "contains". Alguien con alergia severa al maní evitaría cualquier producto que siquiera "may_contain" maní. El menú digital puede filtrar según las preferencias del cliente usando esta información detallada.

El sistema también soporta un formato legacy donde los alérgenos eran simplemente una lista de IDs sin información de presencia. Para compatibilidad hacia atrás, la función convertLegacyAllergenIds transforma este formato antiguo al nuevo formato asumiendo "contains" como presencia por defecto.

### La Tabla de Productos con Información Densa

La tabla de productos muestra múltiples columnas optimizadas para escaneo visual rápido. La columna de imagen muestra un thumbnail de cuarenta y ocho por cuarenta y ocho píxeles o un placeholder si no hay imagen. La columna de producto muestra el nombre en negrita con la descripción truncada debajo, y íconos de estrella y trending si el producto está marcado como destacado o popular.

La columna de precio es particularmente inteligente. Si el producto usa precio único, muestra ese valor formateado con signo de pesos y dos decimales. Si usa precios por sucursal, calcula el mínimo y máximo de los precios activos y muestra el rango. Si todos los precios son iguales aunque sean técnicamente precios separados, muestra solo ese valor para evitar redundancia como "$125.00 - $125.00". También muestra cuántas sucursales tienen el producto activo.

La columna de categoría muestra un badge con el nombre de la categoría y el nombre de la subcategoría debajo en texto más pequeño. La columna de alérgenos muestra hasta tres íconos emoji de los alérgenos asignados, con un indicador "+N" si hay más, y un tooltip al hover revela la lista completa.

Las columnas de badge y estado muestran badges condicionales: el badge promocional si existe, y un badge verde para activo o rojo para inactivo. La columna de acciones muestra botones de editar y eliminar condicionalmente según los permisos del usuario actual.

### El Filtrado y Paginación

La página incluye controles de filtrado por categoría y subcategoría. Al seleccionar una categoría, el selector de subcategoría se actualiza para mostrar solo las subcategorías de esa categoría. Estos filtros reducen el conjunto de productos mostrados, y un indicador muestra cuántos productos pasan el filtro del total.

La paginación usa el hook usePagination que mantiene el estado de página actual y calcula qué items mostrar. Por defecto muestra diez items por página. Cuando los filtros cambian, la página se resetea a uno para evitar quedar en una página vacía.

La ordenación por defecto es alfabética por nombre. La tabla no implementa ordenación por click en headers, pero los productos llegan del backend en un orden específico y se re-ordenan en el frontend para garantizar consistencia.

---

## Capítulo VI: El Personal y Sus Roles

### La Jerarquía de Permisos

El sistema de personal no solo registra empleados; implementa un modelo de control de acceso basado en roles que determina qué puede ver y hacer cada usuario en el sistema. Cuatro roles forman la jerarquía: WAITER para mozos, KITCHEN para personal de cocina, MANAGER para gerentes de sucursal, y ADMIN para administradores del sistema.

Un ADMIN tiene acceso total. Puede crear, editar y eliminar cualquier entidad en cualquier sucursal. Puede asignar cualquier rol a cualquier empleado, incluyendo crear otros administradores. Ve todas las estadísticas, todas las sucursales, todos los empleados. Es el superusuario del sistema.

Un MANAGER tiene acceso amplio pero restringido a sus sucursales asignadas. Puede crear y editar empleados, productos, categorías, mesas, pero solo en las sucursales donde tiene rol de gerente. Crucialmente, no puede asignar el rol ADMIN a nadie, preservando la jerarquía de que solo administradores crean administradores. Tampoco puede eliminar entidades, una restricción que previene pérdida accidental de datos valiosos.

Un KITCHEN puede acceder a la página de cocina donde ve los pedidos que debe preparar. Puede gestionar recetas porque ese es conocimiento de su dominio. Pero no tiene acceso a la gestión de personal, mesas, ventas, ni otras áreas administrativas. Su visión del sistema está enfocada en lo que necesita para trabajar.

Un WAITER tiene acceso mínimo al Dashboard porque su herramienta principal es pwaWaiter. Si accede al Dashboard, puede ver información básica pero no modificar configuraciones. En la práctica, rara vez necesita el Dashboard.

### La Página de Personal

Cuando el administrador o gerente accede a la página de Personal, ve una tabla con los empleados de la sucursal seleccionada. La tabla muestra nombre completo, rol traducido al español (Mozo, Cocinero, Gerente, Administrador), email, teléfono, DNI, fecha de ingreso formateada según locale argentina, y estado activo o inactivo con badge de color.

El campo de búsqueda implementa debounce usando useDeferredValue, un hook de React 19. Mientras el usuario escribe, la interfaz permanece responsiva porque React prioriza actualizaciones de input sobre actualizaciones de filtrado. La búsqueda filtra por nombre, apellido, email, o DNI, permitiendo encontrar empleados rápidamente en listas largas.

El formulario de creación y edición incluye campos para nombre, apellido, email, teléfono, DNI, fecha de ingreso, estado activo, sucursal, y rol. El selector de sucursal muestra diferentes opciones según quien lo usa: para administradores, todas las sucursales activas; para gerentes, solo las sucursales donde tienen acceso. Similarmente, el selector de rol no muestra la opción ADMIN si el usuario actual es gerente.

La validación verifica que no existan empleados duplicados con el mismo email o DNI. Cuando se edita un empleado existente, la validación excluye ese empleado de la verificación de duplicados para permitir actualizar otros campos sin falso positivo.

### Las Restricciones de Negocio en el Backend

Aunque el frontend implementa restricciones visuales, la seguridad real está en el backend. Si un gerente intentara asignar rol ADMIN manipulando el request HTTP, el backend lo rechazaría. El backend verifica que el usuario tenga permisos para la operación que intenta realizar, que tenga acceso a la sucursal involucrada, y que no viole reglas de negocio como gerentes creando administradores.

Esta defensa en profundidad es esencial. El frontend oculta opciones que el usuario no debería usar, mejorando la experiencia al no mostrar cosas que no puede hacer. Pero confiar solo en el frontend sería inseguro porque un atacante puede enviar requests directamente al backend. El backend debe ser la fuente de verdad para autorización.

---

## Capítulo VII: Las Promociones y el Tiempo

### La Temporalidad de las Ofertas

Las promociones añaden una dimensión temporal a los productos. Un "Happy Hour" no es simplemente un descuento; es un descuento que aplica solo entre las 17:00 y las 20:00, solo en ciertos días, solo hasta cierta fecha. El sistema debe capturar estas restricciones y aplicarlas correctamente tanto en el Dashboard para configuración como en pwaMenu para mostrar solo promociones vigentes.

Cada promoción tiene fecha de inicio y fecha de fin que delimitan su vigencia en días calendario. Pero además tiene hora de inicio y hora de fin que delimitan las horas del día en que aplica. Una promoción puede estar configurada del 1 al 31 de enero, pero solo de 18:00 a 21:00 cada día. Fuera de esas horas, no aparece en el menú aunque la fecha esté dentro del rango.

El estado de una promoción se calcula dinámicamente. Si is_active es false, la promoción está desactivada manualmente independientemente de fechas y horas. Si la fecha actual está fuera del rango de fechas, está inactiva por tiempo. Si la fecha está dentro pero la hora está fuera, también está inactiva. Solo cuando todas las condiciones se cumplen la promoción está activa.

El badge en la tabla refleja este cálculo usando la función isPromotionActive que compara la fecha y hora actuales contra la configuración de la promoción. Un badge verde indica activa, rojo indica inactiva. El administrador puede ver de un vistazo qué promociones están corriendo ahora.

### Los Productos del Combo

Una promoción típicamente agrupa varios productos en un combo con precio especial. El componente ProductSelect permite seleccionar productos del catálogo y especificar la cantidad de cada uno. Un "Combo Familiar" podría incluir cuatro hamburguesas, cuatro papas fritas, y cuatro bebidas, cada una seleccionada individualmente.

El precio de la promoción es independiente de la suma de precios de los productos individuales. Esto permite tanto ofertas donde el combo es más barato que comprar por separado, incentivando la compra del combo, como bundles premium donde el precio del combo puede superar la suma de partes porque incluye algún valor agregado como presentación especial o extras exclusivos.

Los productos se almacenan como items con product_id y quantity. El backend valida que los productos existan y estén activos. Si un producto se desactiva después de agregarlo a una promoción, la promoción sigue funcionando pero el administrador debería revisar si tiene sentido mantenerla.

### La Distribución entre Sucursales

Las promociones pueden aplicar a todas las sucursales o solo a algunas. El componente BranchCheckboxes muestra todas las sucursales activas como checkboxes individuales con sus nombres. Por defecto, al crear una promoción nueva, todas las sucursales vienen seleccionadas. El administrador puede desmarcar las que no aplican.

Esta flexibilidad permite estrategias de marketing diferenciadas. Una sucursal en zona turística podría tener promociones de temporada alta. Una sucursal en zona de oficinas podría tener promociones de almuerzo ejecutivo. Una sucursal nueva podría tener descuentos de lanzamiento mientras las establecidas mantienen precios normales.

La validación de promociones incluye reglas temporales especiales. Al crear una promoción nueva, la fecha de inicio debe ser hoy o futura, no se pueden crear promociones retroactivas. La fecha de fin debe ser igual o posterior a la de inicio. Si inicio y fin son el mismo día, la hora de fin debe ser posterior a la de inicio. Al editar una promoción existente, estas validaciones son más permisivas para permitir ajustes a promociones en curso.

---

## Capítulo VIII: La Gestión de Mesas en Tiempo Real

### El Ciclo de Vida de una Mesa

Una mesa transita por múltiples estados durante su jornada de servicio. Comienza "libre", disponible para nuevos comensales, mostrada en verde en el Dashboard. Cuando alguien escanea el código QR de la mesa y abre una sesión, pasa a "ocupada", mostrada en rojo. Cuando los comensales ordenan, el estado de pedido indica si hay pendiente, en cocina, o listo. Finalmente, cuando los comensales piden la cuenta, entra en estado "cuenta_solicitada", mostrada en morado.

Pero el estado de la mesa es solo parte de la historia. Una mesa ocupada puede tener múltiples rondas de pedidos en diferentes estados. La primera ronda puede estar lista mientras la segunda sigue cocinándose y la tercera acaba de enviarse. El sistema necesita un estado agregado que resuma la situación para que el mozo sepa qué acción tomar.

El cálculo de estado agregado en tableStore sigue reglas de prioridad cuidadosamente diseñadas. La prioridad más alta es el estado combinado "ready_with_kitchen": si hay alguna ronda lista y alguna que no está lista (pendiente, confirmada, enviada, o en cocina), se muestra este estado especial que indica al mozo que hay items para llevar pero que debe volver por más. La siguiente prioridad es "pending" si todas las rondas están pendientes de confirmación del mozo. Luego "confirmed" si todas están confirmadas pero no enviadas. Luego "submitted" o "in_kitchen" que se tratan igual como "en cocina". Finalmente "ready" si todas están listas, y "served" si todas fueron servidas.

### El Grid de Mesas con Sectores

La página de Mesas agrupa las mesas por sector usando encabezados visuales. Un restaurante típico tiene sectores como Interior, Terraza, Barra, Salón VIP. Cada sector tiene su propio grupo con un header que muestra el nombre del sector, la cantidad de mesas, los nombres de los mozos asignados hoy, y un indicador de urgencia si alguna mesa en ese sector necesita atención.

Las tarjetas de mesa son compactas pero informativas. El número de mesa domina visualmente porque es el identificador que mozos y comensales usan. El color de fondo indica el estado: verde para libre, rojo para ocupada, morado para cuenta solicitada. Un badge superpuesto indica el estado del pedido con colores específicos: amarillo para pendiente que necesita confirmación del mozo, azul para confirmado o en cocina, naranja para el estado combinado de listo más cocina, verde para todo listo.

Las animaciones comunican cambios y urgencia. Una mesa que acaba de recibir un nuevo pedido pulsa en amarillo con la animación animate-pulse-warning. Una mesa que pidió la cuenta pulsa en morado con animate-pulse-urgent. Una mesa cuyo estado acaba de cambiar destella brevemente en azul con animate-status-blink, un destello de 1.5 segundos que llama atención sin ser molesto. El estado combinado ready_with_kitchen tiene su propia animación de 5 segundos llamada animate-ready-kitchen-blink.

Dentro de cada sector, las mesas se ordenan implícitamente para que las que necesitan atención estén visibles. Las mesas con estados urgentes tienden a estar prominentes visualmente por sus animaciones, aunque la posición en el grid sigue el orden numérico de las mesas.

### El Modal de Sesión

Al clickear una mesa ocupada se abre el TableSessionModal que muestra los detalles completos de la sesión activa. El header muestra el número de mesa, el sector, y el estado actual. La primera sección muestra los comensales registrados en la sesión, cada uno con su nombre si lo proporcionaron.

La sección principal muestra las rondas de pedidos. Cada ronda tiene un header con su número, estado con badge de color, y tiempo transcurrido desde que se creó. Los items de cada ronda se agrupan por categoría siguiendo el orden natural de un servicio: primero bebidas, luego entradas, luego platos principales, finalmente postres. Cada categoría tiene un header colapsable y un ícono que el administrador puede clickear para marcar visualmente que esa categoría fue despachada, útil para tracking interno aunque no afecta el estado real en backend.

Cada item muestra cantidad, nombre del producto, precio unitario, y el nombre del comensal que lo ordenó si está disponible. Notas especiales como "sin cebolla" o "bien cocido" aparecen en texto más pequeño. El total de cada ronda se muestra al final.

Si hay una ronda en estado CONFIRMED que aún no fue enviada a cocina, aparece un botón "Enviar a Cocina" que dispara la transición de estado. Esta funcionalidad permite al administrador controlar el flujo de pedidos hacia la cocina, útil cuando la cocina está saturada y hay que dosificar los pedidos.

### Las Asignaciones de Mozos a Sectores

Los mozos no atienden todas las mesas del restaurante; se les asignan sectores específicos cada día. Un modal de asignación de sectores muestra todos los sectores de la sucursal actual, cada uno con un checkbox list de mozos disponibles. El administrador marca qué mozos trabajan en qué sectores para la fecha seleccionada.

Esta asignación tiene impacto real en el sistema. En pwaWaiter, el mozo solo ve mesas de los sectores a los que está asignado hoy. Si Alberto está asignado a Interior y Terraza, ve mesas de ambos sectores. Si solo está asignado a Interior, no ve Terraza. Si no tiene ninguna asignación para hoy, no ve ninguna mesa.

En el WebSocket Gateway, los eventos de mesas se rutean según asignación de sector. Cuando un comensal hace un pedido en una mesa del sector Terraza, solo los mozos asignados a Terraza reciben la notificación ROUND_PENDING. Los mozos de Interior no reciben notificaciones de Terraza porque no es su responsabilidad. Sin embargo, eventos como TABLE_SESSION_STARTED se envían a todos los mozos de la sucursal porque cualquiera podría necesitar saber que llegaron comensales.

---

## Capítulo IX: La Vista de Cocina

### Dos Columnas para Dos Estados

La página de Cocina presenta un diseño de dos columnas que refleja el flujo de trabajo real de una cocina profesional. La columna izquierda titulada "Nuevos" muestra pedidos en estado SUBMITTED, que son pedidos que el administrador acaba de enviar a cocina y están esperando que un cocinero los tome. La columna derecha titulada "En Cocina" muestra pedidos en estado IN_KITCHEN, que son pedidos que algún cocinero ya está preparando activamente.

Este diseño de dos estados es deliberado. En una cocina real, hay una distinción clara entre "pedidos que llegaron" y "pedidos que estoy cocinando". Un cocinero puede mirar la columna de Nuevos para decidir qué tomar a continuación, y mirar la columna de En Cocina para recordar qué tiene en proceso. La interfaz digital replica esta separación mental.

Un detalle importante es que la cocina no ve todos los estados del pedido. Los estados PENDING (comensal envió pero mozo no confirmó) y CONFIRMED (mozo confirmó pero admin no envió a cocina) son invisibles para la cocina. Esto es intencional: esos estados representan pedidos que aún no deberían prepararse porque no fueron autorizados para envío a cocina. Si la cocina viera pedidos PENDING, podría empezar a prepararlos prematuramente, arriesgando preparar algo que el comensal cambió de idea o que el mozo corrigió.

### Las Tarjetas Compactas

Cada pedido se representa como una tarjeta compacta diseñada para escaneo rápido en el ambiente de alta presión de una cocina. El código de mesa domina visualmente en grande porque es el identificador que el cocinero usa para saber dónde irá el pedido. Debajo, en texto más pequeño, aparece la cantidad de items y el tiempo transcurrido desde que llegó a su estado actual.

Un badge de color indica el estado: azul para SUBMITTED (nuevo), azul más oscuro para IN_KITCHEN. Un anillo rojo envuelve la tarjeta si el pedido es urgente: más de quince minutos en SUBMITTED o más de veinte minutos en IN_KITCHEN. La animación de pulso rojo llama atención visual a pedidos que están tardando demasiado.

Las tarjetas son clickeables y accesibles por teclado. Al hacer click o presionar Enter con una tarjeta enfocada, se abre un modal con el detalle completo del pedido. Esto permite una vista resumida para escaneo rápido, con la opción de profundizar en los detalles cuando sea necesario.

### El Modal de Detalle

El modal de detalle de pedido muestra toda la información que el cocinero necesita para preparar. El header repite el código de mesa, el estado actual, y el tiempo transcurrido. El cuerpo lista cada item con cantidad, nombre del producto, y crucialmente las notas especiales si existen.

Las notas especiales son críticas en una cocina. "Sin cebolla" significa omitir un ingrediente. "Bien cocido" significa ajustar el tiempo de cocción. "Alergia a maní" es una advertencia de seguridad alimentaria. Estas notas aparecen prominentemente en rojo para que no se pasen por alto.

Al pie del modal hay un botón de acción que depende del estado actual. Si el pedido está SUBMITTED, el botón dice "Marcar como En Cocina" y al clickearlo transiciona el pedido a IN_KITCHEN. Si está IN_KITCHEN, dice "Marcar como Listo" y transiciona a READY. Después de transicionar a READY, el pedido desaparece de la vista de cocina porque ya no es responsabilidad del cocinero sino del mozo que debe llevarlo a la mesa.

### La Verificación de Roles

Antes de renderizar cualquier contenido, la página verifica que el usuario tenga un rol apropiado para cocina. La verificación usa los selectores del authStore: el usuario debe tener rol KITCHEN, MANAGER, o ADMIN. Si tiene solo WAITER, se muestra una página de acceso denegado con un mensaje claro y un botón para volver al dashboard principal.

Esta verificación en frontend mejora la experiencia del usuario al no mostrar una interfaz que no puede usar. Pero la seguridad real está en el backend: si alguien manipulara el código JavaScript para saltear esta verificación, las llamadas a la API de cocina fallarían con 403 Forbidden porque el backend también verifica roles.

---

## Capítulo X: El Catálogo Jerárquico

### Categorías, Subcategorías, y Productos

El menú se organiza en una jerarquía de tres niveles que refleja cómo los restaurantes estructuran sus ofertas. Las categorías son agrupaciones amplias y visualmente prominentes: Bebidas, Entradas, Platos Principales, Postres. Las subcategorías son divisiones más finas dentro de cada categoría: dentro de Bebidas podríamos tener Gaseosas, Cervezas Nacionales, Cervezas Importadas, Vinos Tintos, Vinos Blancos. Los productos son los items individuales que los comensales pueden ordenar.

Esta jerarquía de tres niveles proporciona flexibilidad sin excesiva complejidad. Un restaurante pequeño podría tener cuatro categorías sin subcategorías, poniendo productos directamente bajo las categorías. Un restaurante grande podría tener diez categorías con cincuenta subcategorías en total, organizando cientos de productos de manera navegable.

Las categorías pertenecen a sucursales. Esto significa que cada sucursal puede tener su propia estructura de menú si es necesario, aunque en la práctica la mayoría de los restaurantes usan la misma estructura en todas las sucursales con variaciones solo en disponibilidad de productos. Una sucursal pequeña podría omitir la categoría de Postres Elaborados si no tiene capacidad para prepararlos.

Existe una categoría especial llamada HOME que el menú público usa internamente para productos destacados en la página principal, pero que no debe aparecer en las listas administrativas. Los selectores y filtros excluyen HOME_CATEGORY_NAME de todas las vistas para evitar confusión.

### Las Páginas de Categorías y Subcategorías

Las páginas de Categorías y Subcategorías siguen el mismo patrón CRUD establecido en todo el Dashboard. Una tabla lista las entidades existentes con sus atributos principales. Un botón "Nueva" abre el modal de creación. Íconos de editar y eliminar en cada fila permiten modificar o borrar entidades existentes.

Cada categoría tiene nombre obligatorio, orden numérico que determina la secuencia de aparición en el menú, ícono emoji opcional para identificación visual, imagen opcional para mostrar en el menú, y estado activo o inactivo. Las subcategorías tienen los mismos campos más una referencia a la categoría padre.

La tabla de categorías muestra una columna adicional con el conteo de subcategorías que contiene cada una. Este conteo ayuda al administrador a evaluar la estructura del menú de un vistazo. Una categoría con muchas subcategorías podría necesitar reorganización.

### La Cascada de Eliminaciones

Eliminar una categoría no es trivial porque tiene efectos en cascada. Si la categoría tiene subcategorías, eliminarla dejaría esas subcategorías huérfanas. Si esas subcategorías tienen productos, los productos también quedarían huérfanos. El sistema debe manejar esta cascada de manera controlada.

Antes de proceder con la eliminación, un componente CascadePreviewList analiza qué se eliminará y muestra un resumen al usuario: cuántas subcategorías se eliminarán, cuántos productos, y potencialmente cuántas promociones se verán afectadas si incluían esos productos. El usuario debe confirmar conscientemente que desea eliminar todo antes de que la operación proceda.

La eliminación es "soft", marcando is_active como false en lugar de borrar físicamente los registros. Esto preserva el historial para auditoría, permite análisis retrospectivo de datos, y hace posible recuperar datos eliminados accidentalmente aunque esa funcionalidad no está expuesta actualmente en la interfaz. El cascade service orquesta las eliminaciones en todos los stores afectados para mantener consistencia.

---

## Capítulo XI: Los Alérgenos y la Seguridad Alimentaria

### Un Sistema de Alertas Vitales

Los alérgenos no son una característica secundaria del sistema; para comensales con alergias severas, son información que puede salvar vidas. Una persona con alergia al maní puede sufrir anafilaxia por cantidades ínfimas del alérgeno. El sistema trata los alérgenos con la seriedad que merecen, implementando múltiples niveles de presencia, validaciones estrictas, y trazabilidad completa.

La página de Alérgenos permite definir los alérgenos que el restaurante rastrea. Los catorce alérgenos obligatorios según regulación EU 1169/2011 típicamente están predefinidos: cereales con gluten, crustáceos, huevos, pescado, maní, soja, lácteos, frutos secos, apio, mostaza, sésamo, sulfitos, altramuces, moluscos. El administrador puede agregar alérgenos adicionales relevantes para su menú.

Cada alérgeno tiene nombre, ícono emoji para identificación visual rápida en el menú, y descripción que puede incluir información sobre síntomas, gravedad, y alimentos relacionados. La tabla muestra además cuántos productos tienen cada alérgeno asignado, permitiendo evaluar el impacto de modificar o eliminar un alérgeno.

### Las Reacciones Cruzadas

El sistema modela reacciones cruzadas entre alérgenos, un concepto crucial para la seguridad alimentaria. Alguien alérgico al maní frecuentemente también reacciona a otros frutos secos aunque no sean el mismo alérgeno técnicamente. Alguien alérgico a crustáceos puede reaccionar a moluscos. Estas relaciones de cross-reactivity se almacenan en el modelo AllergenCrossReaction y se usan para advertencias expandidas en el menú público.

Cuando un comensal indica alergia al maní en pwaMenu, el sistema puede advertir no solo sobre productos que contienen maní sino también sobre productos que contienen alérgenos con reacción cruzada conocida. Esto va más allá de lo que regulaciones exigen pero proporciona una capa adicional de seguridad.

### La Eliminación con Impacto

Al intentar eliminar un alérgeno que está asignado a productos, el sistema advierte sobre el impacto. Un toast muestra cuántos productos perderán la referencia a ese alérgeno. Si el administrador confirma, la eliminación procede y el método removeAllergenFromProducts del productStore limpia las referencias en todos los productos afectados.

Esta limpieza en cascada es necesaria para mantener integridad referencial. Si simplemente se eliminara el alérgeno sin limpiar referencias, los productos tendrían IDs de alérgenos que ya no existen, causando errores cuando se intenten mostrar o procesar esos datos.

---

## Capítulo XII: Insignias y Sellos

### Las Insignias Promocionales

Las insignias son etiquetas visuales que destacan productos especiales para captar atención del comensal. "Nuevo" indica productos recientemente agregados. "Popular" señala bestsellers. "Recomendado" es una sugerencia del chef. "Especial del Chef" destaca creaciones únicas. "Oferta" indica descuento temporal.

La página de Badges permite definir estas insignias con total flexibilidad. Cada badge tiene nombre y color personalizable. El selector de color ofrece colores predefinidos de la paleta Tailwind CSS pero también permite ingresar valores hexadecimales custom. Una vista previa en tiempo real muestra cómo lucirá el badge con el color seleccionado.

Un producto puede tener máximo una insignia activa. Esta restricción de diseño previene que los productos se sobrecarguen con múltiples etiquetas que compiten por atención y diluyen el mensaje. Si un producto es nuevo y popular, el administrador debe elegir qué característica es más relevante destacar en este momento.

La tabla de badges muestra cuántos productos usan cada badge. Si un badge tiene productos asignados, el botón de eliminar se deshabilita y un tooltip explica que debe remover el badge de esos productos primero. Esta protección previene eliminaciones accidentales que dejarían productos con referencias huérfanas.

### Los Sellos de Certificación

Los sellos funcionan similarmente a las insignias pero representan certificaciones más permanentes y formales. "Vegano" certifica que el producto no contiene ingredientes de origen animal. "Vegetariano" permite lácteos y huevos pero no carne. "Sin Gluten" indica ausencia de gluten. "Orgánico" señala ingredientes de cultivo orgánico. "Sin Lactosa" indica ausencia de lactosa.

La distinción entre badges y seals es conceptual y visual. Los badges son promocionales y temporales; un producto eventualmente deja de ser "Nuevo". Los seals son certificaciones permanentes; un plato vegano sigue siendo vegano indefinidamente. En el menú público, badges y seals se muestran en posiciones diferentes y con estilos distintos para comunicar esta diferencia.

Un producto puede tener tanto un badge como un seal simultáneamente. "Nuevo" (badge) junto a "Vegano" (seal) comunica que es una adición reciente al menú que además es apta para veganos. Esta combinación permite comunicación rica sin sobrecargar visualmente.

---

## Capítulo XIII: Ingredientes y Recetas

### La Jerarquía de Ingredientes

El sistema de ingredientes implementa una estructura de dos niveles que modela la realidad de una cocina profesional. Los ingredientes principales son componentes directos como "Tomate", "Pollo", "Harina". Pero algunos ingredientes principales son a su vez preparaciones compuestas que tienen sus propios sub-ingredientes.

Un ingrediente marcado como "procesado" puede contener sub-ingredientes. "Salsa BBQ" es un ingrediente procesado que contiene "Tomate", "Vinagre", "Azúcar Morena", "Especias", "Salsa de Soja". Esta descomposición es crucial para trazabilidad de alérgenos: la soja en la salsa BBQ debe propagarse como alérgeno a cualquier producto que use esa salsa.

Los ingredientes se organizan en grupos para facilitar navegación: "Carnes", "Verduras", "Condimentos", "Lácteos", "Granos", etc. Estos grupos no afectan la lógica del sistema pero mejoran la usabilidad cuando hay cientos de ingredientes.

La página de Ingredientes muestra una lista donde cada ingrediente principal puede expandirse para revelar sus sub-ingredientes. Los íconos de expandir y colapsar permiten navegar la estructura sin abrumar visualmente. Crear sub-ingredientes abre un modal específico que aparece sobre el modal de edición del ingrediente principal.

### Las Recetas como Fichas Técnicas

Las recetas van mucho más allá de simplemente listar ingredientes. Son documentos estructurados que capturan todo el conocimiento necesario para preparar un plato consistentemente: ingredientes con cantidades exactas, pasos de preparación con instrucciones detalladas, tiempos de preparación y cocción, porciones esperadas, notas del chef con tips profesionales, información de almacenamiento, sugerencias de presentación.

Una receta en el sistema tiene más de cuarenta campos opcionales organizados en secciones. La sección de información básica incluye nombre, descripción, sucursal, categoría y subcategoría para clasificación, tipo de cocina (italiana, japonesa, argentina, etc.), nivel de dificultad (fácil, medio, difícil), tiempo de preparación en minutos, tiempo de cocción en minutos, número de porciones.

La sección de ingredientes permite agregar componentes del catálogo de ingredientes o escribir ingredientes ad-hoc. Cada entrada tiene cantidad, unidad de medida, y notas opcionales. Se puede marcar qué ingredientes son principales para destacarlos visualmente.

La sección de preparación contiene los pasos como una lista ordenada. Cada paso tiene descripción textual y opcionalmente tiempo estimado. Los pasos se pueden reordenar arrastrando.

Las notas del chef son texto libre donde el cocinero experimentado puede documentar trucos del oficio: "dejar reposar la masa 30 minutos para mejor textura", "el punto exacto es cuando burbujea pero no hierve", "presentar con perejil fresco nunca seco".

### El Costing y la Vinculación con Productos

Cada receta puede incluir información de costos: el costo total de los ingredientes calculado a partir de costos unitarios, y un precio sugerido de venta basado en el margen deseado. Esta información permite análisis de rentabilidad: ¿el precio del menú cubre los costos con margen suficiente?

Una receta puede "derivarse" a un producto del catálogo. Este proceso crea un producto nuevo vinculado a la receta original. El producto hereda automáticamente los alérgenos calculados de los ingredientes de la receta, garantizando que si un ingrediente contiene gluten, el producto derivado mostrará gluten como alérgeno sin necesidad de asignarlo manualmente.

La vinculación es bidireccional: desde una receta se puede ver qué producto la usa, y desde un producto se puede navegar a su receta origen. Esto facilita trazabilidad y mantenimiento cuando las recetas evolucionan.

### La Ingestión para Inteligencia Artificial

Las recetas pueden "ingerirse" al sistema RAG (Retrieval-Augmented Generation) para alimentar un chatbot inteligente. El botón "Ingestar" en la página de recetas dispara un proceso que extrae el contenido textual de la receta, lo convierte en embeddings vectoriales mediante un modelo de lenguaje, y los almacena en una base de datos vectorial.

Posteriormente, cuando un cliente o empleado pregunta algo como "¿cómo se prepara la milanesa napolitana?" o "¿qué platos tienen queso azul?", el sistema busca en los embeddings, encuentra recetas relevantes, y genera una respuesta basada en su contenido. Este flujo permite que el conocimiento culinario encapsulado en las recetas sea accesible conversacionalmente.

---

## Capítulo XIV: El Flujo de un Pedido Completo

### De la Mesa a la Cocina y de Vuelta

Para entender cómo todas las piezas del Dashboard encajan, sigamos el viaje completo de un pedido desde que el comensal se sienta hasta que paga y se va. Este recorrido atraviesa múltiples componentes, múltiples aplicaciones, y múltiples actores humanos.

Un grupo de cuatro amigos llega al restaurante a las 20:30 y el hostess les asigna la mesa 5 del sector Interior. Uno de ellos, Ana, saca su teléfono y escanea el código QR adherido a la mesa. El código contiene una URL que abre pwaMenu con parámetros que identifican la mesa y la sucursal.

pwaMenu envía una petición al backend para crear o unirse a la sesión de la mesa 5. El backend crea un registro de TableSession, genera un table token para autenticar las operaciones de esta sesión, y publica el evento TABLE_SESSION_STARTED al canal de WebSocket de la sucursal.

El Dashboard, conectado vía WebSocket al endpoint /ws/admin, recibe el evento. El handler en tableStore procesa el evento, encuentra la mesa 5 en su estado, y actualiza su status a "ocupada". El componente de mesas detecta el cambio de estado y re-renderiza la tarjeta de la mesa 5 con fondo rojo y una animación de destello azul que indica cambio reciente.

El gerente, mirando el Dashboard, nota el destello y ve que la mesa 5 ahora está ocupada. Sabe que acaban de llegar comensales aunque no se levantó de su escritorio.

### El Pedido y la Confirmación

Los cuatro amigos exploran el menú en sus teléfonos, cada uno con su propia instancia de pwaMenu pero todos conectados a la misma sesión. Añaden items a sus carritos individuales: Ana pide una hamburguesa clásica y una cerveza, Bruno pide una hamburguesa vegana y agua mineral, Carlos pide alitas de pollo y dos cervezas, Diana pide ensalada césar y limonada.

Los carritos se sincronizan en tiempo real para que todos vean qué está pidiendo cada uno. Cuando están listos, Ana propone enviar el pedido. Los otros tres ven la propuesta en sus pantallas y cada uno confirma. Cuando todos confirmaron, el pedido se envía al backend.

El backend crea un Round con estado PENDING, registrando qué items pidió cada comensal. Publica el evento ROUND_PENDING a los canales de admin y waiters de la sucursal.

El Dashboard recibe ROUND_PENDING. El tableStore actualiza la mesa 5: agrega una entrada al diccionario roundStatuses con el nuevo round_id mapeando a "pending", recalcula orderStatus como "pending" porque es la única ronda, setea hasNewOrder a true. El componente de mesas re-renderiza la tarjeta de la mesa 5 con un pulso amarillo indicando nuevo pedido pendiente de confirmación.

El mozo Alberto, que tiene asignado el sector Interior hoy, recibe la notificación en pwaWaiter. Se acerca a la mesa 5 y verifica el pedido con los comensales: "¿Entonces son dos hamburguesas, una clásica y una vegana, alitas, ensalada césar, dos cervezas, un agua y una limonada?". Los comensales confirman.

Alberto marca el pedido como confirmado en pwaWaiter. El backend transiciona el estado del Round a CONFIRMED y publica ROUND_CONFIRMED.

El Dashboard recibe ROUND_CONFIRMED. El tableStore actualiza roundStatuses para esa ronda a "confirmed", recalcula orderStatus a "confirmed", setea hasNewOrder a false porque el mozo ya verificó. La tarjeta deja de pulsar amarillo y muestra badge azul "Confirmado".

### El Envío a Cocina

El gerente, viendo que la mesa 5 tiene un pedido confirmado, decide enviarlo a cocina. Hace click en la tarjeta de la mesa 5, se abre el TableSessionModal mostrando los detalles del pedido. Hace click en "Enviar a Cocina".

El Dashboard envía una petición POST al backend para transicionar el Round a SUBMITTED. El backend actualiza el estado y publica ROUND_SUBMITTED a los canales de admin, waiters, y kitchen de la sucursal.

El Dashboard recibe ROUND_SUBMITTED. El tableStore actualiza roundStatuses a "submitted", recalcula orderStatus a "submitted". La tarjeta muestra badge azul "En Cocina".

La página de Cocina, que escucha eventos en /ws/kitchen, recibe ROUND_SUBMITTED. El pedido aparece en la columna "Nuevos" como una tarjeta con "Mesa 5", "8 items", y un timer que empieza a contar.

María, la cocinera, ve el nuevo pedido. Hace click en la tarjeta, ve el detalle: 1× Hamburguesa Clásica, 1× Hamburguesa Vegana, 1× Alitas de Pollo, 1× Ensalada César (nota: sin crutones), 2× Cerveza Artesanal, 1× Agua Mineral, 1× Limonada. Hace click en "Marcar como En Cocina".

El backend transiciona a IN_KITCHEN y publica ROUND_IN_KITCHEN.

El Dashboard recibe el evento y actualiza. La tarjeta de la mesa 5 sigue con badge azul "En Cocina". La página de Cocina mueve el pedido de la columna "Nuevos" a la columna "En Cocina".

María prepara los platos. Quince minutos después, todo está listo. Hace click en "Marcar como Listo".

El backend transiciona a READY y publica ROUND_READY a admin, waiters, y session (para que los comensales sepan que viene su comida).

El Dashboard recibe ROUND_READY. El tableStore actualiza roundStatuses a "ready", recalcula orderStatus a "ready". La tarjeta de la mesa 5 muestra badge verde "Listo". En la página de Cocina, el pedido desaparece porque ya no es responsabilidad de la cocina.

Alberto el mozo recibe la notificación en pwaWaiter de que el pedido de la mesa 5 está listo. Va a la cocina, recoge los platos, y los lleva a la mesa.

### La Cuenta y el Cierre

Después de disfrutar su comida, los amigos piden la cuenta. Ana, desde pwaMenu, presiona "Pedir Cuenta". El backend publica CHECK_REQUESTED.

El Dashboard recibe el evento. La tarjeta de la mesa 5 cambia a fondo morado y empieza a pulsar con animate-pulse-urgent, señalando alta urgencia. El mozo es notificado.

Alberto lleva la cuenta a la mesa. Los amigos pagan en efectivo. Alberto marca el pago como recibido. El backend procesa el pago, genera el Check con los Charges y Allocations correspondientes, y eventualmente publica TABLE_CLEARED cuando la sesión se cierra.

El Dashboard recibe TABLE_CLEARED. El tableStore limpia el estado de la mesa 5: status vuelve a "libre", roundStatuses se vacía, orderStatus vuelve a "none", hasNewOrder a false. La tarjeta de la mesa 5 vuelve a verde, disponible para los próximos comensales.

El ciclo completo, desde que escanearon el QR hasta que pagaron y se fueron, fue visible en tiempo real en el Dashboard. El gerente pudo monitorear el progreso sin moverse de su escritorio, interviniendo cuando fue necesario para enviar a cocina.

---

## Capítulo XV: La Experiencia de Usuario Optimizada

### Lazy Loading y Code Splitting

Una aplicación con más de veinte páginas diferentes no debería cargar todo su código cuando el usuario accede a la primera página. El Dashboard implementa lazy loading usando React.lazy() y Suspense para cada una de sus veintitrés páginas.

El archivo App.tsx define cada página como un import dinámico: const DashboardPage = lazy(() => import('./pages/Dashboard')). Esta sintaxis le indica al bundler Vite que cree un chunk separado para cada página. El resultado son múltiples archivos JavaScript pequeños en lugar de uno gigante.

Cuando el usuario navega a una ruta, React detecta que la página correspondiente aún no está cargada, muestra el fallback de Suspense mientras descarga el chunk, y una vez descargado renderiza la página. Todo esto es transparente para el usuario excepto por un breve indicador de carga.

El componente PageLoader sirve como fallback consistente para todos los Suspense boundaries. Muestra un spinner centrado con el texto "Cargando..." y texto oculto para lectores de pantalla que anuncia "Cargando página". Esta consistencia es importante: el usuario siempre ve el mismo indicador independientemente de qué página esté cargando.

### La Optimización LCP

Largest Contentful Paint es una métrica de Core Web Vitals que mide cuánto tarda en renderizarse el elemento más grande visible. En el Dashboard, las tarjetas de sucursales con sus imágenes son típicamente el LCP de la página principal.

Para optimizar esta métrica, la primera imagen de sucursal recibe tratamiento especial. El atributo loading="eager" indica al navegador que debe descargarla inmediatamente sin esperar a que esté cerca del viewport. El atributo fetchPriority="high" le da prioridad sobre otros recursos. El atributo decoding="async" permite que la decodificación de imagen ocurra fuera del thread principal.

Las imágenes subsecuentes reciben tratamiento opuesto: loading="lazy" para que no se descarguen hasta que estén cerca del viewport, y decoding="async" para no bloquear. Esta distinción entre primera imagen crítica y demás imágenes diferibles optimiza el LCP sin desperdiciar bandwidth.

Adicionalmente, preconnect hints en el HTML establecen conexiones tempranas a los dominios de imágenes externas, eliminando la latencia de DNS lookup, TCP handshake, y TLS negotiation del tiempo percibido de carga.

### Las Animaciones con Propósito Comunicativo

Cada animación en el Dashboard tiene un propósito comunicativo específico. No son decoración; son lenguaje visual que transmite información sin requerir lectura de texto.

El pulso amarillo animate-pulse-warning indica urgencia moderada: hay algo nuevo que necesita atención pero no es emergencia. Se usa para pedidos pendientes de confirmación del mozo. La animación es un cambio de opacidad cíclico que captura atención periférica sin ser agresivo.

El pulso morado animate-pulse-urgent indica urgencia alta: hay algo que necesita atención inmediata. Se usa para mesas que pidieron la cuenta. La animación es más pronunciada que el pulso amarillo para escalar la urgencia visualmente.

El destello azul animate-status-blink indica cambio reciente: algo acaba de pasar y el usuario debería notarlo. Dura 1.5 segundos y luego desaparece. Se usa cuando cualquier transición de estado ocurre para llamar atención momentánea.

El destello naranja prolongado animate-ready-kitchen-blink indica el estado combinado de items listos más items aún en cocina. Dura 5 segundos para asegurar que esta situación operativamente importante no pase desapercibida.

Las animaciones se implementan en CSS puro para máximo rendimiento. Los componentes React solo manipulan clases CSS; la animación real corre en el compositor del navegador sin involucrar JavaScript en cada frame.

---

## Capítulo XVI: Los Permisos en Detalle

### Las Funciones de Verificación

El archivo permissions.ts exporta funciones declarativas que encapsulan la lógica de autorización. En lugar de esparcir condicionales if (roles.includes('ADMIN')) por toda la aplicación, los componentes llaman funciones semánticas que describen la intención.

Las funciones genéricas verifican roles: isAdmin retorna true si el array de roles incluye 'ADMIN', isManager verifica 'MANAGER', isAdminOrManager verifica cualquiera de los dos, canDelete retorna true solo si isAdmin porque los managers no pueden eliminar.

Las funciones específicas a entidades verifican permisos para operaciones concretas: canCreateProduct, canEditProduct verifican que sea admin o manager; canCreateStaff, canEditStaff igual; canCreateBranch requiere admin porque crear sucursales es operación de alto nivel.

Las funciones de acceso a páginas verifican si el usuario debería poder ver ciertas secciones: canAccessKitchenPage retorna true si tiene rol KITCHEN, MANAGER, o ADMIN; canAccessCrudPage es más permisiva para managers.

Esta centralización tiene beneficios multiplicativos. Si las reglas de negocio cambian y los managers adquieren permiso de eliminar, solo hay que modificar canDelete. Si se agrega un nuevo rol, las funciones se actualizan en un solo lugar. Si se necesita auditar qué permisos tiene cada rol, el archivo permissions.ts documenta todo.

### La Restricción de Sucursales

Los permisos de rol se combinan con permisos de sucursal. Un manager puede editar productos, pero solo en las sucursales donde tiene rol de manager. El array branch_ids en el perfil del usuario lista las sucursales a las que tiene acceso.

Los componentes filtran datos según estas sucursales. El selector de sucursales en la barra lateral solo muestra sucursales del branch_ids del usuario. La tabla de productos de una sucursal no mostraría datos de una sucursal sin acceso porque ni siquiera puede seleccionarse.

El backend refuerza estas restricciones. Si un manager manipulara una petición HTTP para intentar modificar un producto de una sucursal sin acceso, el backend verificaría branch_ids y rechazaría con 403 Forbidden. La defensa es doble: el frontend no muestra lo que no debería, y el backend no permite lo que no debería.

### La Aplicación en Componentes

Los componentes usan permisos de dos formas principales. Primero, renderizado condicional: un botón "Nueva Mesa" solo aparece si canCreateTable() retorna true; su ausencia comunica visualmente que el usuario no tiene ese permiso.

Segundo, control de habilitación: un campo podría mostrarse pero estar deshabilitado si el usuario puede ver pero no editar. Esto es menos común en el Dashboard porque generalmente si no puedes hacer algo, el elemento no aparece.

El patrón típico en un componente es obtener roles del authStore, calcular los permisos relevantes en variables locales, y usar esas variables en el JSX para condicionales y props. Las variables se calculan una vez por render y se reusan múltiples veces:

```
const userRoles = useAuthStore(selectUserRoles)
const canCreate = canCreateTable(userRoles)
const canEdit = canEditTable(userRoles)
```

Si los roles cambiaran durante la sesión (poco común pero posible si se refrescan del backend), el componente re-renderizaría y recalcularía los permisos automáticamente gracias a la reactividad de Zustand.

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
