# pwaMenu: La Mesa Digital

## Introducción: El Problema de las Cartas Tradicionales

Imagina un grupo de amigos sentados en un restaurante, pasándose una carta de mano en mano, esperando turnos para ver los platos mientras el mozo aguarda pacientemente. Uno quiere verificar ingredientes por alergias, otro busca opciones vegetarianas, y un tercero simplemente quiere ver las fotos de los postres. Este ritual, tan familiar como ineficiente, representa exactamente el problema que pwaMenu resuelve.

La aplicación de menú para clientes es una PWA (Progressive Web App) que transforma cada teléfono móvil en una extensión de la carta del restaurante. Pero a diferencia de un simple catálogo digital, pwaMenu introduce un concepto revolucionario: el carrito compartido. En lugar de que cada comensal haga pedidos individuales, todos los dispositivos en una mesa comparten el mismo espacio de trabajo virtual, creando una experiencia verdaderamente colaborativa que respeta la naturaleza social de compartir una comida.

Esta arquitectura de "sesión compartida" presenta desafíos técnicos únicos. Cuando cinco personas miran el mismo carrito desde cinco dispositivos diferentes, ¿cómo se garantiza que todos vean exactamente lo mismo? ¿Cómo se previene que dos personas modifiquen la misma cantidad simultáneamente? ¿Y cómo se maneja la confirmación grupal para enviar un pedido cuando no todos están listos al mismo tiempo? Las respuestas a estas preguntas definen la arquitectura de pwaMenu.

---

## Capítulo 1: El Viaje del Comensal

### La Llegada a la Mesa

El primer contacto del comensal con pwaMenu ocurre a través de un código QR pegado en la mesa. Este simple escaneo desencadena una orquestación compleja que el usuario nunca percibe. El código contiene un identificador alfanumérico de la mesa (como "INT-01" o "TER-02") que la aplicación utiliza para conectarse con el backend y obtener o crear una sesión activa.

El componente JoinTable maneja este flujo inicial mediante un proceso de dos pasos. Primero, el usuario ve su número de mesa pre-poblado desde el QR y lo confirma. Luego, opcionalmente, ingresa su nombre para identificarse ante los demás comensales. Esta información viaja al backend, que responde con un token de sesión único que autoriza todas las operaciones posteriores de ese comensal en esa mesa específica.

Lo notable de este diseño es su tolerancia a la ambigüedad. Los códigos de mesa no son únicos globalmente: cada sucursal puede tener su propia "INT-01". Por eso, la aplicación siempre envía el slug de la sucursal junto con el código de mesa, permitiendo al backend resolver la mesa correcta sin confusiones. Este pequeño detalle arquitectónico previene errores sutiles que serían devastadores en producción, donde un pedido enviado a la mesa equivocada destruiría la experiencia del usuario.

### El Catálogo Vivo

Una vez dentro de la sesión, el comensal accede al menú completo del restaurante. Pero este no es un simple catálogo estático. El menuStore mantiene una representación local del menú que se actualiza dinámicamente y se cachea inteligentemente para evitar peticiones redundantes. Cada producto llega con información estructurada sobre alérgenos, perfiles dietéticos, métodos de cocción y precios específicos de la sucursal.

La conversión de datos merece atención especial. El backend almacena precios en centavos (12550 representa $125.50) para evitar errores de punto flotante, pero el frontend los presenta en pesos con decimales para la comodidad del usuario. Esta transformación ocurre en el momento de la carga, garantizando que la lógica de negocio siempre trabaje con representaciones apropiadas para cada contexto.

El sistema de caché implementa una política TTL (Time To Live) de cinco minutos que balancea frescura contra eficiencia. Un menú obsoleto por más tiempo podría mostrar productos descontinuados, pero refrescar constantemente consumiría datos innecesarios. La aplicación también permite invalidación manual del caché, útil cuando el administrador actualiza precios o disponibilidad y necesita que los cambios se reflejen inmediatamente.

---

## Capítulo 2: Los Filtros como Herramientas de Inclusión

### El Desafío de las Restricciones Alimentarias

En cualquier grupo de comensales, las necesidades dietéticas varían enormemente. Uno puede ser celíaco, otro intolerante a la lactosa, y un tercero simplemente prefiere evitar frituras. Los sistemas tradicionales de filtrado ofrecen checkboxes binarios que ocultan productos, pero pwaMenu va mucho más allá con un sistema de filtrado sofisticado que reconoce la complejidad real de las restricciones alimentarias.

El hook useAllergenFilter representa esta sofisticación. No solo permite excluir alérgenos específicos, sino que distingue entre diferentes niveles de presencia: un producto puede "contener" un alérgeno (presente como ingrediente), "poder contenerlo" (trazas por contaminación cruzada), o estar "libre de" él (garantizado sin presencia). El usuario puede elegir un modo estricto que solo oculta productos con el alérgeno como ingrediente, o un modo muy estricto que también excluye aquellos con posibles trazas, vital para personas con alergias severas donde incluso mínimas exposiciones representan riesgos médicos.

### Las Reacciones Cruzadas: Una Dimensión Oculta

Pero la verdadera innovación del sistema de filtrado reside en su comprensión de las reacciones cruzadas entre alérgenos. El síndrome látex-fruta ilustra perfectamente este fenómeno: una persona alérgica al látex frecuentemente también reacciona a plátanos, aguacates, kiwis y castañas. Estas conexiones no son obvias para el comensal promedio, pero ignorarlas puede tener consecuencias médicas serias.

El sistema obtiene del backend un grafo de reacciones cruzadas con probabilidades asociadas (alta, media, baja) y permite al usuario configurar su sensibilidad. Alguien con alergias leves podría considerar solo reacciones de alta probabilidad, mientras que alguien con historial de anafilaxis querrá incluir todas las conexiones conocidas. El resultado es un filtrado que va más allá de lo que el usuario conscientemente sabe sobre sus alergias, protegiéndolo proactivamente.

### Preferencias Dietéticas y Métodos de Cocción

El hook useDietaryFilter complementa el sistema de alérgenos con preferencias de estilo de vida. Vegetariano, vegano, sin gluten, sin lácteos, apto para celíacos, keto, bajo en sodio: cada opción representa no solo una restricción sino una forma de relacionarse con la comida. La implementación requiere que el producto satisfaga todas las opciones seleccionadas simultáneamente, reconociendo que una persona puede ser tanto vegetariana como intolerante al gluten.

Similarmente, useCookingMethodFilter permite excluir métodos de preparación específicos. Un usuario que evita frituras por razones de salud puede configurar el filtro una vez y olvidarse, viendo solo opciones compatibles con su preferencia.

### La Persistencia Inteligente de Preferencias

Todo este sistema de filtrado sería inútil si el usuario tuviera que reconfigurarlo cada vez que visita el restaurante. El hook useImplicitPreferences resuelve este problema sincronizando las preferencias con el backend y asociándolas con el identificador del dispositivo. Cuando un comensal regresa semanas después, sus filtros se restauran automáticamente, creando una experiencia personalizada sin requerir registro explícito.

Esta sincronización utiliza debouncing de dos segundos para evitar peticiones excesivas mientras el usuario ajusta múltiples filtros, y retry con backoff exponencial para manejar errores de red transitorios. El resultado es una persistencia que el usuario apenas nota pero que mejora significativamente su experiencia en visitas sucesivas.

---

## Capítulo 3: El Carrito Compartido

### La Anatomía de una Sesión de Mesa

El corazón de pwaMenu es el tableStore, un estado Zustand que representa la sesión de mesa en su totalidad. Cada sesión contiene una lista de comensales, un carrito compartido, un historial de pedidos enviados, y metadatos de conexión con el backend. Esta estructura refleja la realidad física: una mesa con personas, sus decisiones acumuladas, y su historial de consumo.

Cuando un comensal agrega un producto al carrito, el item queda etiquetado con su identificador y nombre. Esto permite que el carrito muestre quién pidió qué, facilitando la división de cuentas al final y creando una sensación de propiedad sobre las selecciones individuales dentro del contexto colaborativo. Cada comensal puede modificar solo sus propios items, pero todos pueden ver el carrito completo.

### El Problema de la Concurrencia Optimista

Cuando cinco personas miran el mismo carrito, la consistencia visual es crítica. El sistema utiliza actualizaciones optimistas mediante el hook useOptimisticCart, que aplica cambios instantáneamente a la interfaz mientras la operación real se ejecuta en segundo plano. Si la operación falla, el sistema hace rollback automático al estado anterior, pero en la mayoría de los casos el usuario experimenta respuesta instantánea sin percibir latencia.

La deduplicación de items merece mención especial. Cuando el mismo producto aparece dos veces con IDs diferentes (uno temporal, otro real), el sistema fusiona estas entradas preferiendo el ID permanente. Este comportamiento previene glitches visuales durante la reconciliación entre estado optimista y estado real.

### La Confirmación Grupal: Un Protocolo de Consenso

El momento más delicado del flujo es enviar el pedido a cocina. A diferencia de una aplicación individual donde el usuario simplemente presiona "enviar", en una mesa compartida surge la pregunta: ¿están todos listos? ¿Alguien quiere agregar algo más? El sistema de confirmación grupal (RoundConfirmation) implementa un protocolo de consenso inspirado en sistemas distribuidos.

Cuando un comensal propone enviar el pedido, todos los demás reciben una notificación visual mostrando quién propuso y quiénes han confirmado su acuerdo. Cada comensal puede marcar "estoy listo" o esperar, y el sistema muestra el conteo en tiempo real. Solo cuando todos los comensales han confirmado, el pedido se envía automáticamente a cocina. Este proceso tiene un timeout de cinco minutos para evitar bloqueos indefinidos, y el proponente original puede cancelar la propuesta si cambian los planes.

El diseño reconoce que el envío de un pedido es un momento social, no solo técnico. Forzar el envío cuando alguien aún está decidiendo sería tan molesto como que un comensal gritara al mozo sin consultar a los demás. El protocolo de consenso digitaliza la cortesía natural de preguntar "¿pedimos ya?".

---

## Capítulo 4: La Conexión en Tiempo Real

### El WebSocket del Comensal

Mientras el mozo y la cocina tienen sus propios canales WebSocket con autenticación JWT, el comensal utiliza un canal diferente autenticado mediante el token de mesa. La clase DinerWebSocket encapsula esta conexión, manejando la complejidad de mantener un vínculo persistente en el entorno hostil de los navegadores móviles.

La reconexión automática utiliza backoff exponencial con jitter aleatorio. Cuando la conexión se pierde (algo frecuente en móviles que entran y salen de cobertura WiFi), el sistema espera un segundo antes del primer intento, luego dos, luego cuatro, hasta un máximo de treinta segundos. El jitter del 30% evita la "estampida de reconexiones" donde muchos dispositivos intentan reconectarse simultáneamente después de una interrupción del servidor.

### El Heartbeat y la Detección de Conexiones Zombi

El protocolo de heartbeat envía un ping cada treinta segundos y espera un pong dentro de diez. Si el pong no llega, el sistema cierra la conexión proactivamente y comienza el proceso de reconexión. Este mecanismo detecta conexiones "zombi": aquellas que parecen abiertas pero han perdido comunicación real, común cuando un dispositivo móvil entra en modo suspensión sin cerrar apropiadamente las conexiones.

La reactivación por visibilidad complementa este sistema. Cuando el usuario cambia de pestaña y luego regresa, o cuando desbloquea el teléfono después de un período de suspensión, el listener de visibilidad verifica el estado de la conexión y la restablece si es necesario. Este comportamiento asegura que el comensal siempre tenga información actualizada cuando activamente mira la aplicación.

### Eventos de Estado del Pedido

A través del WebSocket, el comensal recibe actualizaciones sobre el progreso de sus pedidos. ROUND_SUBMITTED indica que el pedido llegó a cocina, ROUND_IN_KITCHEN que la preparación comenzó, ROUND_READY que está listo para servir. Cada evento actualiza el estado local, permitiendo que el comensal sepa exactamente dónde está su comida sin necesidad de preguntar al mozo.

El evento ROUND_ITEM_DELETED merece atención especial. Cuando un mozo elimina un item de un pedido activo (porque el producto no está disponible, por ejemplo), todos los comensales en la mesa ven su carrito actualizarse en tiempo real. Este flujo bidireccional mantiene la consistencia entre la realidad operativa y la visión del cliente.

---

## Capítulo 5: El Reconocimiento del Cliente Recurrente

### La Identificación Sin Registro

La mayoría de las aplicaciones de fidelización requieren creación de cuenta, ingreso de email, verificación, y todo un ritual que interrumpe la experiencia. pwaMenu invierte esta lógica: primero reconoce, después ofrece. El sistema genera un identificador único de dispositivo que persiste en localStorage, y opcionalmente calcula una huella digital del navegador como respaldo.

Cuando un dispositivo que ya ha visitado antes se conecta a una sesión, el backend puede correlacionar las visitas anteriores y ofrecer información contextual: "Bienvenido de nuevo, la última vez pediste la Milanesa Napolitana" o "Basado en tus preferencias, te recomendamos evitar los platos con maní". Todo esto sin requerir login ni formularios.

### El Opt-in de Fidelización

Para usuarios que desean funcionalidades adicionales (acumulación de puntos, ofertas personalizadas, historial detallado), el sistema ofrece un registro opt-in que vincula el dispositivo a un perfil de cliente. El hook useCustomerRecognition detecta si el dispositivo actual está vinculado a un cliente registrado y, de ser así, carga sugerencias personalizadas y productos favoritos.

Este diseño respeta la privacidad por defecto mientras ofrece beneficios tangibles a quienes eligen participar. La diferencia con sistemas tradicionales es sutil pero significativa: el restaurante reconoce al cliente antes de pedirle que se registre, demostrando valor antes de solicitar compromiso.

---

## Capítulo 6: El Cierre de Mesa y el Pago

### El Flujo de Solicitud de Cuenta

Cuando el grupo termina de comer, cualquier comensal puede solicitar la cuenta. Esta acción cambia el estado de la sesión a "paying" y notifica al sistema de facturación. El sistema valida que no queden items pendientes en el carrito (productos agregados pero no enviados), previniendo el escenario donde un comensal olvida que había seleccionado un postre que nunca se pidió.

La solicitud de cuenta no cierra la sesión inmediatamente. El diseño reconoce que los comensales frecuentemente agregan "una última cosa" mientras esperan la cuenta, o que alguien puede pedir un café adicional. La sesión permanece activa para nuevos pedidos, que simplemente se agregarán al total final.

### La División de Cuentas

El cálculo de shares de pago soporta múltiples estrategias: división igualitaria, división por consumo individual, o división personalizada. La implementación calcula los montos correspondientes a cada comensal y los presenta claramente, facilitando ese momento social frecuentemente incómodo de decidir quién paga qué.

El registro de pagos individuales permite escenarios mixtos donde algunos pagan en efectivo, otros con tarjeta, y quizás uno transfiere su parte. El sistema trackea cada contribución hasta que el total queda cubierto.

---

## Capítulo 7: La Arquitectura de Estado

### El Patrón de Selectores Estables

React 19 con Zustand 5 introduce requisitos estrictos para evitar re-renders infinitos. Cada selector debe retornar exactamente la misma referencia cuando los datos subyacentes no han cambiado. Las constantes EMPTY_CART_ITEMS y EMPTY_DINERS proporcionan arrays estables que los selectores retornan cuando no hay datos, evitando la creación de nuevas instancias vacías en cada llamada.

Los selectores derivados como selectFeaturedProducts o selectPendingCalls implementan caches manuales que recuerdan el último resultado y lo retornan si el array fuente no ha cambiado. Este patrón, aparentemente verboso, es esencial para la estabilidad del rendimiento en aplicaciones React modernas.

### La Persistencia de Sesión

El middleware persist de Zustand serializa automáticamente partes del estado a localStorage, permitiendo que la sesión sobreviva recargas de página y cierres accidentales. La función partialize define exactamente qué se persiste, excluyendo estado transitorio como flags de loading o errores temporales.

La rehidratación incluye validaciones de expiración. Una sesión almacenada de hace ocho horas probablemente corresponde a una comida que ya terminó; el sistema la descarta automáticamente en lugar de intentar reconectar a una mesa que probablemente tiene otros ocupantes.

### La Coordinación Multi-Tab

Un mismo comensal puede tener la aplicación abierta en múltiples pestañas del navegador. El sistema detecta cambios en localStorage desde otras pestañas y sincroniza el estado, fusionando carritos cuando es necesario y priorizando la última versión como fuente de verdad. Este comportamiento previene situaciones donde un comensal ve estados diferentes según qué pestaña esté mirando.

---

## Capítulo 8: El Cliente API Defensivo

### La Protección SSRF

El cliente API valida rigurosamente que las URLs de destino correspondan a hosts permitidos, previniendo ataques SSRF donde un input malicioso podría redirigir peticiones a servicios internos. Las direcciones IP directas están bloqueadas, los puertos están restringidos a un conjunto conocido, y las URLs con credenciales embebidas se rechazan inmediatamente.

En producción, cualquier intento de conexión a un host no autorizado causa un error fatal. En desarrollo, el sistema advierte pero permite la operación, facilitando configuraciones locales no estándar sin comprometer la seguridad en ambientes reales.

### La Deduplicación de Peticiones

El sistema de deduplicación previene race conditions donde clicks rápidos podrían enviar múltiples veces la misma petición. Cada petición en vuelo se registra con su método, endpoint, y body; peticiones idénticas subsecuentes reciben la misma promesa que la original. Cuando la petición completa, se remueve del registro automáticamente.

Un mecanismo de timeout limpia peticiones que exceden el tiempo máximo esperado, previniendo situaciones donde una petición trabada bloquearía indefinidamente peticiones futuras idénticas. El límite de cien peticiones concurrentes previene crecimiento descontrolado del mapa de deduplicación en escenarios patológicos.

### El Manejo de Expiración de Sesión

Cuando el backend responde con 401 (no autorizado), el cliente API detecta si la petición usaba autenticación de mesa y, de ser así, dispara un callback que marca la sesión como expirada. Este callback está conectado al sessionStore, que presenta un modal informativo sugiriendo al usuario escanear nuevamente el QR para obtener una nueva sesión.

Este flujo reconoce que los tokens de mesa tienen vida limitada (típicamente tres horas) y que el usuario puede simplemente haber dejado la aplicación abierta demasiado tiempo. La experiencia guía al usuario hacia la resolución en lugar de mostrar errores técnicos confusos.

---

## Capítulo 9: La Internacionalización

### Tres Idiomas, Una Experiencia

pwaMenu soporta español, inglés y portugués, reflejando la realidad multilingüe de restaurantes que reciben turistas internacionales. El sistema i18next carga los recursos de traducción apropiados según la preferencia del navegador, con español como fallback predeterminado.

El selector de idioma, ubicado discretamente en la pantalla de inicio, permite cambiar la preferencia manualmente. Esta configuración persiste en localStorage, asegurando que un turista anglófono no tenga que reconfigurar el idioma cada vez que escanea un nuevo QR.

### La Traducción de Productos

Más allá de la interfaz, el sistema soporta productos con nombres y descripciones traducidos. El hook useProductTranslation selecciona la versión apropiada según el idioma activo, cayendo al idioma predeterminado del restaurante si la traducción específica no existe.

---

## Capítulo 10: Las PWA Features

### La Instalabilidad

Como Progressive Web App, pwaMenu puede instalarse en la pantalla de inicio del dispositivo, proporcionando acceso rápido y experiencia de aplicación nativa. El hook usePWA detecta si la aplicación es instalable (el navegador ofrece el prompt de instalación) y si ya está instalada (ejecutándose en modo standalone).

La estrategia del service worker precachea recursos estáticos y utiliza cache-first para assets inmutables, garantizando cargas instantáneas incluso con conectividad limitada. La página offline proporciona un mensaje apropiado cuando el dispositivo está completamente desconectado.

### Las Actualizaciones Transparentes

Cuando el administrador despliega una nueva versión, el service worker la detecta y presenta una notificación sutil al usuario ofreciendo actualizar. El hook needRefresh indica cuándo una actualización está disponible, y updateServiceWorker aplica la actualización cuando el usuario lo aprueba.

---

## Reflexión Final: La Digitalización de lo Social

pwaMenu no es simplemente un catálogo digital ni una aplicación de pedidos. Es una herramienta que respeta y amplifica la naturaleza inherentemente social de compartir una comida. El carrito compartido no es una limitación técnica sino una decisión de diseño que refleja cómo las personas realmente comen en grupo: viendo lo que otros piden, sugiriendo opciones, decidiendo juntos cuándo enviar el pedido.

Las protecciones de alérgenos van más allá de los checkboxes típicos porque una alergia severa no es un "preferencia": es una cuestión de seguridad que merece consideración seria. El reconocimiento de dispositivos ofrece personalización sin exigir registro porque la hospitalidad genuina no comienza con formularios.

Cada decisión arquitectónica en pwaMenu responde a una pregunta fundamental: ¿cómo hace esto que la experiencia del comensal sea más agradable, más segura, o más conveniente? Cuando la tecnología desaparece y solo queda la experiencia fluida de elegir y compartir comida con personas queridas, el software ha cumplido su propósito.
