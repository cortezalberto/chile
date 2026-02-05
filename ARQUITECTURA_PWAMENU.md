# Arquitectura de pwaMenu: Documentación Técnica Narrativa

## Prólogo

Este documento constituye una exposición exhaustiva de la arquitectura, patrones de diseño y decisiones técnicas que conforman **pwaMenu**, la aplicación web progresiva destinada a los comensales del sistema de gestión gastronómica Integrador. A diferencia de documentación convencional basada en listas y fragmentos de código, este texto adopta un estilo narrativo profesional que permite comprender no solo el *qué* sino el *por qué* de cada decisión arquitectónica.

La aplicación representa el punto de contacto directo entre el restaurante y sus clientes, permitiendo explorar el menú digital, realizar pedidos colaborativos desde múltiples dispositivos en una misma mesa, gestionar preferencias alimentarias y procesar pagos. Su diseño prioriza la experiencia móvil, el funcionamiento offline y la sincronización en tiempo real.

---

## Capítulo I: Fundamentos Tecnológicos

### 1.1 El Ecosistema React 19

pwaMenu se construye sobre React 19.2.0, aprovechando las capacidades más recientes del framework que transforman fundamentalmente la manera de gestionar estados asíncronos y actualizaciones optimistas. Esta versión introduce hooks como `useOptimistic` y `useTransition` que permiten proporcionar retroalimentación instantánea al usuario mientras las operaciones de red se resuelven en segundo plano.

La elección de React 19 no fue casual. En una aplicación donde múltiples comensales interactúan simultáneamente con un carrito compartido, la capacidad de mostrar cambios inmediatos mientras se confirma la operación con el servidor resulta fundamental para una experiencia fluida. Cuando un comensal añade un producto al carrito, la interfaz refleja el cambio instantáneamente; si el servidor rechaza la operación, el estado se revierte automáticamente sin intervención manual.

El compilador de React, integrado mediante babel-plugin-react-compiler, automatiza la memoización de componentes. Esto elimina la necesidad de envolver manualmente cada componente en `React.memo` o cada callback en `useCallback`, reduciendo significativamente el código boilerplate y los errores humanos asociados a optimizaciones manuales incorrectas.

### 1.2 Gestión de Estado con Zustand

Para la gestión del estado global, la aplicación emplea Zustand en su versión 5.0.9. Esta biblioteca representa una alternativa minimalista a Redux que elimina la verbosidad característica de los patrones flux tradicionales. Un store de Zustand se define mediante una única función que retorna el estado inicial y las acciones que lo modifican, sin necesidad de reducers, action creators o middleware externos.

La arquitectura de stores en pwaMenu sigue un patrón modular donde cada dominio de la aplicación posee su propio store especializado. El **tableStore** gestiona toda la lógica relacionada con la sesión de mesa, el carrito compartido y los pedidos. El **menuStore** mantiene el catálogo de productos con caché temporal. El **sessionStore** maneja la conexión con el backend y la persistencia de tokens. El **serviceCallStore** rastrea las llamadas al mozo.

Cada store implementa persistencia automática mediante el middleware `persist` de Zustand, que serializa el estado a localStorage y lo rehidrata al cargar la aplicación. Esta característica permite que un comensal cierre accidentalmente el navegador y, al reabrirlo, encuentre su sesión exactamente donde la dejó.

### 1.3 Empaquetado y Optimización con Vite

Vite 7.2.4 actúa como el corazón del sistema de construcción, proporcionando un servidor de desarrollo con recarga instantánea y un proceso de build optimizado para producción. Su arquitectura basada en módulos ES nativos durante el desarrollo elimina la necesidad de empaquetar el código completo en cada cambio, resultando en tiempos de recarga medidos en milisegundos.

La configuración de producción implementa división de código estratégica mediante chunks manuales. Las dependencias de terceros se agrupan en un chunk `vendor` que cambia infrecuentemente y puede cachearse agresivamente. Las traducciones se separan en un chunk `i18n` que solo se descarga cuando el usuario cambia de idioma. Los componentes modales pesados como el chat de IA o los filtros avanzados residen en sus propios chunks, descargándose bajo demanda únicamente cuando el usuario los requiere.

El plugin vite-plugin-pwa transforma la aplicación en una Progressive Web App completa, generando automáticamente el service worker, el manifiesto de aplicación y los iconos en múltiples resoluciones. La configuración define comportamientos de caché diferenciados según el tipo de recurso: las imágenes de productos emplean estrategia CacheFirst con expiración de 30 días, mientras que las llamadas a API utilizan NetworkFirst con timeout de 5 segundos y fallback a caché.

---

## Capítulo II: Arquitectura de la Aplicación

### 2.1 Punto de Entrada y Ciclo de Vida

El archivo `main.tsx` constituye el punto de entrada de la aplicación, ejecutando las inicializaciones críticas antes de montar el árbol de componentes React. La primera acción consiste en generar el identificador único de dispositivo y su huella digital, elementos fundamentales para el sistema de fidelización que permite reconocer visitantes recurrentes sin requerir autenticación explícita.

La huella digital se computa de manera asíncrona mediante un hash SHA-256 que combina características del navegador: user agent, resolución de pantalla, zona horaria, idioma configurado, cantidad de memoria y núcleos del procesador, entre otros. Esta combinación genera un identificador suficientemente único para distinguir dispositivos sin comprometer la privacidad del usuario.

Simultáneamente, se inicializa la recolección de métricas Web Vitals, midiendo indicadores de rendimiento como el Largest Contentful Paint (tiempo hasta que el elemento visual más grande se renderiza), First Input Delay (latencia hasta que la aplicación responde a la primera interacción) y Cumulative Layout Shift (estabilidad visual de la página). Estas métricas se almacenan en sessionStorage para análisis posterior.

El componente `App.tsx` orquesta el flujo principal de la aplicación. Al montarse, registra el service worker y configura un listener para actualizaciones disponibles. Cuando se detecta una nueva versión del service worker, se presenta al usuario un prompt discreto invitándolo a recargar la página. Este patrón evita interrupciones bruscas mientras garantiza que los usuarios eventualmente reciban actualizaciones críticas.

### 2.2 Flujo de Usuario y Navegación

El recorrido típico de un comensal comienza cuando escanea un código QR ubicado en la mesa del restaurante. Este código contiene información que identifica tanto la sucursal como la mesa específica. En entornos de desarrollo, un componente `QRSimulator` permite simular este escaneo ingresando manualmente el código de mesa.

Tras el escaneo, el componente `JoinTable` guía al usuario a través de un wizard de dos pasos. Primero, confirma el número de mesa detectado, permitiendo corrección manual si el código se leyó incorrectamente. Segundo, solicita opcionalmente el nombre del comensal, que se utilizará para identificar qué items del carrito pertenecen a cada persona cuando múltiples dispositivos comparten la misma mesa.

Una vez confirmada la unión a la mesa, se crea o recupera una sesión de mesa en el backend. El servidor responde con un table token, un token JWT especializado con tiempo de vida reducido (3 horas) que autoriza todas las operaciones posteriores del comensal. Este token se almacena localmente y se adjunta automáticamente a cada petición API relacionada con operaciones de comensal.

La página principal `Home.tsx` presenta el menú organizado en categorías y subcategorías. Un carrusel destacado muestra productos promocionados. Pestañas horizontales permiten filtrar por categoría (Comidas, Bebidas, Postres). Dentro de cada categoría, los productos se agrupan por subcategoría (Hamburguesas, Pastas, Ensaladas) en una grilla responsiva.

### 2.3 Arquitectura de Componentes

La jerarquía de componentes sigue principios de separación de responsabilidades y carga diferida. Los componentes críticos para el renderizado inicial —Header, BottomNav, CategoryTabs— se importan directamente y forman parte del bundle principal. Los componentes secundarios —modales de detalle de producto, carrito compartido, filtros avanzados, chat de IA— se cargan mediante `React.lazy` solo cuando el usuario los requiere.

El componente `Header` presenta el título de la aplicación, un selector de idioma y, condicionalmente, un menú hamburguesa que aparece únicamente cuando existe una sesión activa. El selector de idioma muestra banderas de los países correspondientes a los tres idiomas soportados: español, inglés y portugués.

El componente `BottomNav` proporciona navegación táctil optimizada para dispositivos móviles. Un botón central prominente abre el chat de asistencia con inteligencia artificial. Tres botones inferiores permiten llamar al mozo, acceder al historial de pedidos y solicitar la cuenta. Cada botón se deshabilita apropiadamente cuando no existe sesión activa.

El sistema de modales implementa un patrón de portal que renderiza el contenido modal fuera del árbol DOM principal, evitando problemas de z-index y overflow. El componente base `Modal` gestiona el foco trap para accesibilidad, el cierre mediante tecla Escape y la prevención de scroll del body mientras el modal está abierto.

---

## Capítulo III: Gestión de Estado en Profundidad

### 3.1 El tableStore: Corazón de la Aplicación

El tableStore representa el componente más complejo del sistema de estado, abarcando más de mil líneas de código organizadas en módulos cohesivos. Su estructura modular separa la definición del store (`store.ts`), los tipos (`types.ts`), los selectores (`selectors.ts`) y las funciones auxiliares (`helpers.ts`).

El estado gestionado incluye la sesión de mesa actual, el comensal actual del dispositivo, el carrito compartido con todos los items de todos los comensales, el historial de pedidos (rounds) enviados, el estado de confirmación grupal pendiente y el registro de pagos realizados por cada comensal.

Las acciones del store se organizan en categorías funcionales. Las acciones de sesión (`joinTable`, `leaveTable`, `updateMyName`) gestionan el ciclo de vida de la participación en una mesa. Las acciones de carrito (`addToCart`, `updateQuantity`, `removeItem`, `clearCart`) modifican los items del pedido actual. Las acciones de sincronización remota (`syncCartFromRemote`, `addRemoteCartItem`) procesan eventos WebSocket de otros comensales. Las acciones de pedido (`submitOrder`, `updateOrderStatus`) gestionan el envío y seguimiento de rounds.

Un aspecto crítico del diseño es la prevención de condiciones de carrera durante operaciones asíncronas. Cuando un comensal envía un pedido, múltiples actualizaciones de estado pueden ocurrir en rápida sucesión. El store implementa flags de control (`isSubmitting`) y validación de timestamp de sesión para garantizar que operaciones iniciadas antes de una expiración de sesión no corrompan el estado.

### 3.2 Selectores y Prevención de Re-renders Infinitos

React 19 junto con Zustand presentan un desafío particular: los selectores que retornan nuevas referencias de objeto o array en cada invocación provocan bucles infinitos de re-renderizado. Este problema, sutil pero devastador, requiere patrones específicos de mitigación.

La solución implementada emplea constantes de referencia estable para arrays vacíos. En lugar de retornar `[]` directamente, los selectores retornan una constante `EMPTY_ARRAY` definida a nivel de módulo. Dado que la misma referencia de objeto se retorna en cada invocación, React detecta correctamente que no hay cambios y omite el re-render.

Para selectores que filtran o transforman datos, se implementa un patrón de caché manual. El selector mantiene una referencia al input previo y su resultado correspondiente. Si el input no ha cambiado (comparación por referencia), se retorna el resultado cacheado. Este patrón, aunque verbose, garantiza estabilidad referencial sin depender de bibliotecas externas de memoización.

```
const pendingRoundsCache = { tables: null, result: EMPTY_TABLES }
export const selectTablesWithPendingRounds = (state) => {
  if (state.tables === pendingRoundsCache.tables) return pendingRoundsCache.result
  const filtered = state.tables.filter(t => t.open_rounds > 0)
  pendingRoundsCache.tables = state.tables
  pendingRoundsCache.result = filtered.length > 0 ? filtered : EMPTY_TABLES
  return pendingRoundsCache.result
}
```

### 3.3 Persistencia y Sincronización Multi-pestaña

El middleware persist de Zustand serializa automáticamente el estado a localStorage después de cada modificación. La configuración especifica qué propiedades persistir (excluyendo flags transitorios como `isLoading`) y define funciones de migración para evolucionar el esquema de datos entre versiones.

La sincronización entre pestañas del mismo navegador se logra mediante listeners de eventos de storage. Cuando una pestaña modifica localStorage, las demás pestañas reciben un evento `storage` con el nuevo valor. El store deserializa este valor y actualiza su estado interno, logrando sincronización eventual sin comunicación directa entre pestañas.

Este mecanismo presenta consideraciones de diseño importantes. Cada pestaña mantiene su propia identidad de comensal (`currentDiner`), pero comparte el carrito y los pedidos. Cuando una pestaña detecta que otra ha abandonado la sesión (el valor de sesión en localStorage es null), limpia su propio estado de sesión.

La estrategia de merge para items del carrito prioriza la pestaña que realiza el cambio como fuente de verdad. Los items se deduplicam por combinación de `product_id` y `diner_id`, evitando duplicados visuales durante la reconciliación.

---

## Capítulo IV: Comunicación con el Backend

### 4.1 Cliente API y Seguridad

El módulo `api.ts` implementa un cliente HTTP robusto con múltiples capas de validación y manejo de errores. Antes de realizar cualquier petición, la URL destino se somete a validación de seguridad que previene ataques SSRF (Server-Side Request Forgery).

La validación de URL verifica que el hostname corresponda exactamente a los hosts permitidos configurados, rechazando variantes con subdominios o dominios similares. Los puertos se restringen a un conjunto conocido (80, 443, 8000, 8080). Las direcciones IP privadas (127.x.x.x, 10.x.x.x, 192.168.x.x, 172.16-31.x.x) y localhost se bloquean explícitamente para prevenir acceso a servicios internos.

El sistema de tokens diferencia entre autenticación JWT estándar (para el Dashboard y pwaWaiter) y tokens de mesa (para pwaMenu). El table token se almacena tanto en memoria como en localStorage, con la memoria sirviendo como caché de acceso rápido y localStorage proporcionando persistencia entre recargas.

Cada petición autenticada incluye el header `X-Table-Token` con el token de mesa actual. Adicionalmente, se añade `X-Requested-With: XMLHttpRequest` como medida de protección CSRF básica que el backend puede validar.

### 4.2 Manejo de Errores y Reintentos

El cliente API implementa clasificación de errores para determinar si una operación fallida puede reintentarse. Los errores de servidor (5xx), timeouts y errores de red se consideran transitorios y candidatos a reintento. Los errores de cliente (4xx) indican problemas con la petición misma y no se reintentan.

La función `withRetry` del módulo helpers implementa reintentos con backoff exponencial y jitter. El jitter (variación aleatoria) evita el problema del "thundering herd" donde múltiples clientes que fallaron simultáneamente reintentarían exactamente al mismo tiempo, potencialmente sobrecargando el servidor nuevamente.

```
delay = min(maxDelay, baseDelay * 2^attempt) * random(0.5, 1.5)
```

Los errores se encapsulan en clases especializadas (`ApiError`, `AuthError`, `ValidationError`) que incluyen código de error, clave de internacionalización para mensaje al usuario y flag indicando si el error permite reintento. Esta estructura permite que la capa de UI presente mensajes localizados apropiados sin conocer detalles de implementación.

### 4.3 WebSocket y Tiempo Real

La clase `DinerWebSocket` gestiona la conexión WebSocket con el gateway de tiempo real. La conexión se establece con el table token como query parameter, autenticando al comensal para recibir eventos de su mesa específica.

El sistema de reconexión implementa backoff exponencial con límite máximo de 50 intentos. Cada intento fallido duplica el tiempo de espera hasta un máximo de 30 segundos. Tras agotar los intentos, la conexión se considera permanentemente fallida y se notifica al usuario.

Los códigos de cierre WebSocket determinan el comportamiento de reconexión. Los códigos 4001 (autenticación fallida), 4003 (acceso prohibido) y 4029 (rate limited) indican problemas que no se resolverán con reintentos y provocan abandono inmediato de la reconexión.

El protocolo de heartbeat mantiene la conexión activa enviando mensajes ping cada 30 segundos. Si el servidor no responde con pong en 10 segundos, se asume conexión muerta y se inicia reconexión. Este mecanismo detecta conexiones zombie que aparecen activas pero no pueden transmitir datos.

Los eventos WebSocket recibidos se distribuyen a listeners registrados mediante un patrón pub/sub interno. El método `on` registra callbacks para tipos de eventos específicos y retorna una función de unsubscribe para limpieza. Los hooks de React como `useCartSync` y `useOrderUpdates` utilizan este mecanismo para actualizar el estado de la aplicación en respuesta a eventos del servidor.

---

## Capítulo V: Sistema de Hooks Personalizados

### 5.1 Hooks de Sincronización en Tiempo Real

El hook `useCartSync` representa una pieza crítica de la arquitectura, responsable de mantener sincronizado el carrito local con los cambios de otros comensales. Su implementación incorpora múltiples optimizaciones para manejar ráfagas de eventos sin degradar el rendimiento.

Un caché LRU (Least Recently Used) almacena conversiones de items del backend al formato frontend, evitando reconstruir objetos idénticos repetidamente. La deduplicación de eventos mediante un Set con límite de 100 entradas y TTL de 5 segundos previene procesamiento duplicado de eventos que podrían llegar por múltiples caminos.

El debounce en reconexión agrupa actualizaciones que llegan en ráfaga cuando la conexión WebSocket se restablece tras una desconexión. En lugar de aplicar cada cambio individualmente, se acumulan durante un segundo y se aplican en batch, reduciendo re-renders y mejorando la percepción de rendimiento.

El hook `useOrderUpdates` escucha eventos del ciclo de vida de pedidos: ROUND_SUBMITTED cuando el pedido se envía a cocina, ROUND_IN_KITCHEN cuando cocina lo acepta, ROUND_READY cuando está listo para servir, ROUND_SERVED cuando el mozo lo entrega. Cada transición actualiza el estado local y puede disparar notificaciones al usuario.

### 5.2 Hooks de Filtrado de Productos

El sistema de filtrado de productos permite a los comensales personalizar la vista del menú según sus restricciones alimentarias. Tres hooks especializados gestionan diferentes aspectos del filtrado.

El hook `useAllergenFilter` filtra productos según alergenos seleccionados. Soporta tres niveles de restricción: estricto (excluye productos que contienen el alergeno), moderado (incluye productos con trazas pero advierte) y permisivo (solo marca pero no excluye). Adicionalmente, detecta reacciones cruzadas: si un usuario es alérgico al maní, el sistema puede advertir sobre productos con otros frutos secos que frecuentemente causan reacciones cruzadas.

El hook `useDietaryFilter` maneja preferencias dietéticas predefinidas: vegetariano, vegano, sin gluten, apto celíacos, keto y bajo en sodio. Cada preferencia define reglas de inclusión/exclusión basadas en los atributos del producto.

El hook `useCookingMethodFilter` permite excluir productos según su método de cocción. Un usuario que evita frituras puede configurar el filtro para ocultar productos fritos, mostrando alternativas a la parrilla o al horno.

El hook `useAdvancedFilters` combina los tres filtros anteriores, aplicándolos secuencialmente y proporcionando una lista final de productos que cumplen todos los criterios seleccionados.

### 5.3 Hooks de Utilidad

El hook `useOptimisticCart` aprovecha `useOptimistic` de React 19 para proporcionar feedback instantáneo en operaciones de carrito. Cuando el usuario añade un producto, el item aparece inmediatamente en el carrito con un estado "pendiente". Si la operación de servidor falla, el item desaparece automáticamente; si tiene éxito, transiciona a estado confirmado sin parpadeo visible.

El hook `useAsync` encapsula el patrón de operaciones asíncronas con AbortController, exponiendo estados de loading, error y data. Al desmontarse el componente, cancela automáticamente peticiones pendientes, previniendo el error común de actualizar estado en componentes desmontados.

El hook `useIsMounted` proporciona una referencia booleana que indica si el componente continúa montado. Los callbacks asíncronos pueden verificar esta referencia antes de actualizar estado, evitando warnings de React sobre actualizaciones en componentes desmontados.

El hook `useDebounce` retorna un valor debounced que solo se actualiza después de que el valor de entrada permanezca estable durante el período especificado. Su implementación separa cuidadosamente el efecto de montaje/desmontaje del efecto de actualización de valor, previniendo condiciones de carrera sutiles.

---

## Capítulo VI: Internacionalización

### 6.1 Arquitectura de i18next

La aplicación soporta tres idiomas: español (es), inglés (en) y portugués (pt). El español actúa como idioma de referencia y fallback; las traducciones a inglés y portugués heredan claves faltantes del español, garantizando que ningún texto quede sin traducción aunque algunas traducciones estén incompletas.

El detector de idioma personalizado extiende el detector estándar de i18next con validación adicional. Antes de cachear un idioma detectado, verifica que sea uno de los tres soportados. Antes de retornar un idioma cacheado, revalida que siga siendo válido. Esta defensa previene corrupción de localStorage que podría dejar la aplicación en un estado de idioma inválido.

Los archivos de traducción organizan las claves en namespaces semánticos: general para textos comunes, menu para el catálogo de productos, cart para el carrito, payment para el flujo de pago, errors para mensajes de error, filters para los filtros de productos, loyalty para el sistema de fidelización. Esta organización facilita la búsqueda y mantenimiento de traducciones.

### 6.2 Patrones de Uso

Los componentes acceden a las traducciones mediante el hook `useTranslation`. Este hook retorna una función `t` que recibe la clave de traducción y opcionalmente parámetros de interpolación.

```typescript
const { t } = useTranslation()
const message = t('cart.itemAdded', { name: product.name })
// Resultado: "Hamburguesa añadida al carrito"
```

Los mensajes de error almacenan claves de internacionalización en lugar de texto literal. Cuando se presenta el error al usuario, la capa de UI traduce la clave al idioma actual. Este patrón permite que la lógica de negocio permanezca agnóstica al idioma mientras el usuario siempre ve mensajes en su idioma preferido.

Los selectores de idioma en el Header presentan banderas de países como indicadores visuales universales. Un tooltip accesible describe cada opción para usuarios de lectores de pantalla: "Cambiar a español", "Switch to English", "Mudar para português".

---

## Capítulo VII: Progressive Web App

### 7.1 Service Worker y Estrategias de Caché

El service worker generado por Workbox implementa estrategias de caché diferenciadas según el tipo de recurso y su volatilidad. Los recursos estáticos de la aplicación (JavaScript, CSS, HTML) utilizan precaching, descargándose durante la instalación del service worker y sirviéndose instantáneamente desde caché en visitas posteriores.

Las imágenes de productos provenientes de servicios externos (Unsplash en desarrollo, CDN en producción) emplean estrategia CacheFirst con expiración de 30 días. Esta estrategia prioriza velocidad sobre frescura, apropiada para imágenes que raramente cambian. El límite de 60 entradas en caché previene crecimiento descontrolado del almacenamiento.

Las fuentes de Google Fonts utilizan CacheFirst con expiración de un año. Las URLs de fuentes incluyen hashes de versión que cambian cuando la fuente se actualiza, haciendo seguro cachear indefinidamente ya que URLs diferentes representan versiones diferentes.

Las llamadas a API utilizan estrategia NetworkFirst con timeout de 5 segundos. El service worker intenta obtener datos frescos del servidor; si la red falla o tarda demasiado, sirve la última versión cacheada. Esta estrategia equilibra frescura de datos con disponibilidad offline.

### 7.2 Instalación y Actualización

El manifiesto de aplicación define los metadatos para instalación en dispositivos móviles: nombre ("Sabor - Menú Digital"), iconos en múltiples resoluciones, colores de tema, orientación preferida y modo de visualización standalone que oculta la barra de navegación del navegador.

Los shortcuts del manifiesto proporcionan accesos directos desde el icono de la app instalada: "Ver Menú", "Productos Destacados", "Bebidas", "Mi Carrito". Estos shortcuts permiten a usuarios frecuentes acceder directamente a secciones específicas sin navegar desde la página principal.

El flujo de actualización respeta la experiencia del usuario. Cuando se detecta una nueva versión del service worker, se muestra un banner discreto invitando a actualizar. El usuario puede continuar usando la versión actual o aceptar la actualización, que recarga la página con el nuevo código. Este patrón evita interrupciones forzadas que podrían ocurrir en medio de una orden.

### 7.3 Funcionamiento Offline

El componente `NetworkStatus` monitorea la conectividad y muestra un indicador visual cuando el dispositivo pierde conexión. El hook `useOnlineStatus` expone este estado a cualquier componente que necesite adaptar su comportamiento.

Las operaciones de carrito que fallan por falta de conectividad se encolan en el `OfflineQueue`. Cuando la conectividad se restaura, la cola reproduce las operaciones en orden, reconciliando el estado local con el servidor. Este patrón permite que usuarios en zonas con conectividad intermitente continúen interactuando con la aplicación.

La página `offline.html` servida cuando la navegación falla completamente presenta un mensaje amigable indicando la falta de conexión y sugiriendo verificar la red. Esta página se precachea durante la instalación del service worker para garantizar su disponibilidad incluso sin ninguna conectividad.

---

## Capítulo VIII: Sistema de Fidelización

### 8.1 Fase 1: Identificación de Dispositivo

El sistema de fidelización permite reconocer visitantes recurrentes sin requerir registro explícito. La primera fase implementa identificación de dispositivo mediante dos mecanismos complementarios.

El `deviceId` es un UUID v4 generado en la primera visita y almacenado en localStorage. Este identificador persiste entre sesiones del navegador mientras el usuario no limpie sus datos de navegación. Su simplicidad lo hace robusto pero vulnerable a pérdida si el usuario cambia de dispositivo o limpia datos.

El `deviceFingerprint` complementa al deviceId con una huella basada en características del navegador. Se computa un hash SHA-256 combinando: user agent, resolución y profundidad de color de pantalla, zona horaria y preferencia de idioma, plataforma del sistema operativo, cantidad de memoria RAM y núcleos de CPU, número máximo de puntos táctiles soportados. Esta combinación genera un identificador relativamente único que puede ayudar a reconocer el mismo dispositivo incluso si el localStorage se limpia.

Al registrar un comensal en una mesa, se envían ambos identificadores al backend. El endpoint `/api/diner/device/{device_id}/history` permite consultar el historial de visitas de un dispositivo, mostrando fechas, mesas visitadas y productos ordenados previamente.

### 8.2 Fase 2: Preferencias Implícitas

La segunda fase captura automáticamente las preferencias de filtrado del usuario. Cuando un comensal configura filtros de alergenos o preferencias dietéticas, el hook `useImplicitPreferences` sincroniza estos ajustes con el backend después de un debounce de 2 segundos.

El endpoint `PATCH /api/diner/preferences` almacena las preferencias asociadas al deviceId. En visitas posteriores, `GET /api/diner/device/{device_id}/preferences` recupera estas preferencias, aplicándolas automáticamente al cargar la aplicación. El usuario encuentra el menú ya filtrado según sus restricciones habituales sin configuración manual.

### 8.3 Fase 4: Registro Opt-in de Cliente

La fase cuatro introduce registro voluntario para usuarios que desean beneficios de fidelización. El `OptInModal` aparece cuando se detecta un dispositivo con historial de visitas previas, invitando al usuario a registrarse.

El registro solicita consentimiento explícito para: almacenamiento de preferencias, análisis de historial de compras, comunicaciones promocionales y personalización mediante IA. El formulario cumple requisitos GDPR permitiendo consentimiento granular por categoría.

Una vez registrado, el endpoint `/api/customer/suggestions` proporciona recomendaciones personalizadas basadas en el historial: "Productos que podrían gustarte", "Tus favoritos de visitas anteriores", "Popular entre clientes similares".

---

## Capítulo IX: Carrito Compartido y Pedidos

### 9.1 Modelo de Carrito Compartido

El carrito en pwaMenu es inherentemente colaborativo: múltiples comensales en la misma mesa pueden añadir productos desde sus propios dispositivos, visualizando en tiempo real las adiciones de los demás. Cada item del carrito incluye el identificador y nombre del comensal que lo añadió, permitiendo identificar "quién pidió qué" para división de cuenta posterior.

La interfaz visual distingue items propios de items de otros comensales mediante colores de avatar. El comensal actual puede modificar cantidad o eliminar únicamente sus propios items; los items de otros aparecen en modo solo lectura. Esta restricción previene conflictos donde múltiples personas intentan modificar el mismo item simultáneamente.

### 9.2 Flujo de Sincronización

Cuando un comensal añade un producto al carrito, la operación sigue un flujo preciso:

1. La acción `addToCart` del store valida los datos de entrada (producto existe, cantidad válida, sesión activa).
2. Se genera un ID temporal optimista para el item y se añade al estado local inmediatamente.
3. Se envía petición POST a `/api/diner/cart/add` con los datos del item.
4. El backend persiste el item y emite evento `CART_ITEM_ADDED` via WebSocket.
5. El gateway WebSocket distribuye el evento a todos los comensales de la mesa.
6. El hook `useCartSync` en cada dispositivo procesa el evento.
7. En el dispositivo originador, el item optimista se reconcilia con el item confirmado.
8. En otros dispositivos, el item se añade al estado local.

Si el paso 3 falla, el item optimista se elimina del estado local, revirtiendo el cambio visual. El usuario ve el item desaparecer y recibe notificación del error.

### 9.3 Confirmación Grupal de Pedido

Para prevenir envíos accidentales de pedidos incompletos, pwaMenu implementa un sistema de confirmación grupal denominado "Round Confirmation". Cuando un comensal está listo para enviar el pedido, no lo envía directamente sino que propone enviarlo.

La propuesta crea un objeto `RoundConfirmation` que incluye el ID del proponente y un mapa de estado por comensal, todos inicialmente en estado "esperando". El componente `RoundConfirmationPanel` muestra a cada comensal el estado de confirmación de todos los participantes.

Cada comensal confirma su disposición tocando "Estoy listo". Cuando todos los comensales de la mesa han confirmado, un temporizador de 1.5 segundos inicia la cuenta regresiva visible para dar oportunidad de última cancelación. Al expirar el temporizador, el pedido se envía automáticamente.

La propuesta expira automáticamente después de 5 minutos si no alcanza confirmación unánime. El proponente puede cancelar la propuesta en cualquier momento. Cualquier comensal puede revocar su confirmación antes del envío final.

### 9.4 Estados del Pedido

Los pedidos (rounds) transitan por estados bien definidos que reflejan su progreso en el flujo de servicio del restaurante:

- **PENDING**: El pedido se creó desde pwaMenu pero aguarda verificación del mozo en la mesa física.
- **CONFIRMED**: El mozo verificó el pedido presencialmente y confirmó que coincide con lo que la mesa desea.
- **SUBMITTED**: Un administrador o gerente envió el pedido a cocina para preparación.
- **IN_KITCHEN**: El personal de cocina aceptó el pedido y comenzó su preparación.
- **READY**: Cocina terminó de preparar los items y están listos para servir.
- **SERVED**: El mozo entregó el pedido a la mesa.
- **CANCELED**: El pedido fue cancelado antes de completarse.

Cada transición genera un evento WebSocket que actualiza el estado en todos los dispositivos de la mesa. Los comensales pueden ver el progreso de su pedido en tiempo real.

---

## Capítulo X: Sistema de Pagos

### 10.1 Flujo de Solicitud de Cuenta

Cuando los comensales finalizan su consumo, cualquiera puede solicitar la cuenta tocando el botón correspondiente en BottomNav. Esta acción invoca el endpoint `/api/billing/check/request` que crea un registro de cuenta (Check) en el backend y notifica al mozo asignado.

El backend calcula el total sumando los precios de todos los items de todos los rounds de la sesión, aplicando promociones vigentes si corresponde. El Check incluye desglose por item, subtotal, impuestos si aplican y total final.

La página `CloseTable` presenta el resumen de consumo y opciones de división. Tres métodos de división están disponibles:

- **División igualitaria**: El total se divide equitativamente entre los comensales presentes.
- **División por consumo**: Cada comensal paga exactamente lo que ordenó, calculado a partir del campo `diner_id` de cada item.
- **División personalizada**: Los comensales acuerdan montos arbitrarios, útil cuando alguien quiere invitar o cuando el cálculo exacto no coincide con el deseo social.

### 10.2 Integración con Mercado Pago

Para pagos electrónicos, pwaMenu integra con Mercado Pago mediante el modelo de Checkout Pro. El flujo comienza cuando un comensal selecciona "Pagar con Mercado Pago" en la interfaz de pago.

El servicio `mercadoPago.ts` solicita al backend la creación de una preferencia de pago con el monto correspondiente a la porción del comensal. El backend, utilizando el SDK de Mercado Pago, genera una preferencia que incluye URLs de retorno para éxito, fallo y estado pendiente.

El comensal es redirigido al checkout de Mercado Pago donde puede pagar con tarjeta, saldo de cuenta o métodos alternativos según su país. Una vez completado (o fallado) el pago, Mercado Pago redirige al usuario de vuelta a pwaMenu a la página `PaymentResult`.

La página `PaymentResult` interpreta los query parameters de la URL de retorno para determinar el resultado: aprobado, rechazado o pendiente. Muestra un mensaje apropiado y ofrece opciones para reintentar (si falló) o volver al menú (si tuvo éxito).

El backend recibe notificación independiente del resultado mediante webhook de Mercado Pago, garantizando que el registro de pago se actualice incluso si el usuario cierra el navegador antes de retornar.

### 10.3 Pagos en Efectivo y Tarjeta Física

Para pagos que no atraviesan Mercado Pago (efectivo o tarjeta física procesada por el mozo), la aplicación registra la intención de pago pero la confirmación ocurre desde pwaWaiter.

El comensal indica qué método utilizará y el monto. Esta información se transmite al mozo, quien procesa el pago físicamente y confirma la recepción en su aplicación. La confirmación del mozo actualiza el estado del Check y notifica a todos los dispositivos de la mesa.

---

## Capítulo XI: Componentes de Interfaz

### 11.1 Sistema de Diseño

La interfaz visual de pwaMenu sigue un sistema de diseño consistente basado en Tailwind CSS 4. El tema oscuro predomina, con fondo `#0a0a0a` (zinc-950) proporcionando alto contraste para los elementos de contenido. El color de acento naranja `#f97316` (orange-500) destaca acciones primarias y elementos interactivos.

Las clases utilitarias personalizadas en `index.css` definen tokens semánticos: `dark-bg` para fondos principales, `dark-card` para tarjetas elevadas, `dark-muted` para texto secundario, `dark-border` para bordes sutiles. Esta abstracción permite ajustar el tema globalmente modificando pocas definiciones.

Los componentes táctiles respetan tamaños mínimos de 44x44 píxeles según guías de accesibilidad, garantizando objetivos de toque cómodos en dispositivos móviles. El espaciado consistente mediante escala de Tailwind (4px, 8px, 12px, 16px, 24px, 32px) crea ritmo visual predecible.

### 11.2 Componentes de Producto

El `ProductCard` presenta un producto en formato de tarjeta con imagen prominente, nombre, descripción truncada, precio y badges de características (vegano, sin gluten, etc.). Un botón de acción rápida permite añadir al carrito sin abrir el detalle completo.

El `ProductListItem` ofrece una variante compacta para listados densos, mostrando thumbnail pequeño, nombre, precio y botón de añadir en una sola fila horizontal. Este formato es útil cuando el espacio es limitado o cuando se listan muchos productos.

El `ProductDetailModal` presenta la información completa del producto: imagen a tamaño completo, nombre, descripción extendida, información nutricional, alergenos, métodos de cocción, selector de cantidad y notas especiales. Dos botones de acción permiten añadir al carrito o llamar al mozo para consultas.

### 11.3 Componentes de Carrito

El `SharedCart` muestra el carrito compartido de la mesa actual. Un header indica el total de items y el monto acumulado. El listado agrupa items por comensal, mostrando el nombre y avatar de color de cada uno. Items propios incluyen controles de cantidad; items ajenos son solo lectura.

El `CartItemCard` representa un item individual con imagen del producto, nombre, modificaciones solicitadas, cantidad y precio. Los controles permiten incrementar, decrementar o eliminar el item. Animaciones suaves acompañan los cambios de cantidad.

El `OrderSuccess` aparece tras enviar exitosamente un pedido, mostrando un resumen de lo ordenado y el número de round asignado. Botones permiten ver el historial de pedidos o continuar navegando el menú.

El `RoundConfirmationPanel` presenta el estado de la confirmación grupal: quién propuso enviar, qué comensales confirmaron, cuáles faltan, y el tiempo restante si aplica. Botones contextuales permiten confirmar, cancelar o revocar según el estado actual.

### 11.4 Componentes de Filtrado

El `AdvancedFiltersModal` organiza las opciones de filtrado en secciones colapsables: alergenos (con checkboxes para cada uno y selector de severidad), preferencias dietéticas (botones toggle para cada dieta), métodos de cocción (checkboxes de exclusión).

El `FilterBadge` aparece en el header cuando hay filtros activos, mostrando un contador de filtros aplicados. Tocar el badge abre el modal de filtros para ajustarlos. Un botón de limpieza permite resetear todos los filtros con un toque.

El `AllergenSelect` permite selección múltiple de alergenos con indicadores visuales de severidad de reacción. Cada alergeno muestra un icono representativo y nombre en el idioma actual.

### 11.5 Componentes de Asistencia

El directorio `AIChat/` contiene el chatbot de asistencia con inteligencia artificial. El componente principal presenta una interfaz de chat con historial de mensajes, campo de entrada y sugerencias de preguntas frecuentes.

El módulo `responseHandlers.ts` implementa un patrón de estrategia para procesar diferentes tipos de respuesta del modelo de IA: recomendaciones de productos (renderizadas como cards interactivos), información nutricional (tablas formateadas), respuestas de texto plano (párrafos estilizados).

El `CallWaiterModal` proporciona interfaz para llamar al mozo, permitiendo seleccionar el motivo (consulta general, solicitar algo, reportar problema) y añadir una nota opcional. La llamada se registra y notifica al mozo asignado al sector de la mesa.

---

## Capítulo XII: Accesibilidad y Rendimiento

### 12.1 Estándares de Accesibilidad

La aplicación implementa estándares WCAG 2.1 nivel AA. Todos los elementos interactivos poseen labels accesibles, ya sea mediante texto visible, atributo `aria-label` o `aria-labelledby` apuntando a un elemento descriptivo.

Los modales implementan foco trampa: al abrirse, el foco se mueve al primer elemento focusable del modal; la navegación con Tab cicla dentro del modal sin escapar; al cerrarse, el foco retorna al elemento que abrió el modal. El hook `useFocusTrap` encapsula esta lógica.

Los iconos decorativos incluyen `aria-hidden="true"` para que lectores de pantalla los ignoren. Los iconos significativos (como el icono de carrito con badge de cantidad) incluyen texto alternativo descriptivo mediante `aria-label`.

El hook `useAriaAnnounce` permite anunciar cambios de estado a lectores de pantalla mediante regiones ARIA live. Cuando un producto se añade al carrito, se anuncia "Hamburguesa añadida al carrito". Cuando un pedido cambia de estado, se anuncia "Tu pedido está siendo preparado".

### 12.2 Optimización de Rendimiento

La carga inicial se optimiza mediante code splitting agresivo. Solo el código necesario para renderizar la pantalla inicial se incluye en el bundle principal. Los modales, el chat de IA, los filtros avanzados y otros componentes secundarios se cargan bajo demanda cuando el usuario los requiere.

Las imágenes de productos implementan lazy loading nativo mediante el atributo `loading="lazy"`. Las imágenes fuera del viewport no se descargan hasta que el usuario hace scroll hacia ellas, reduciendo significativamente el tiempo de carga inicial en menús extensos.

Los selectores de Zustand con caches manuales previenen re-cálculos innecesarios. Cuando el estado no cambia (comparación por referencia), el selector retorna el mismo resultado cacheado, evitando que React re-renderice componentes cuyos props efectivamente no cambiaron.

Las listas largas de productos podrían beneficiarse de virtualización en futuras iteraciones, renderizando solo los items visibles en el viewport. Actualmente, la paginación del backend limita las respuestas a cantidades manejables.

### 12.3 Métricas y Monitoreo

El módulo `webVitals.ts` recolecta métricas de rendimiento real de usuarios. Las métricas se almacenan en sessionStorage durante la visita y podrían enviarse a un servicio de análisis al finalizar la sesión.

Los targets de rendimiento establecidos son:
- **LCP (Largest Contentful Paint)**: < 2.5 segundos
- **FID (First Input Delay)**: < 100 milisegundos
- **CLS (Cumulative Layout Shift)**: < 0.1

El service worker reporta tiempos de respuesta de caché vs red, permitiendo validar que las estrategias de caché efectivamente mejoran los tiempos de carga percibidos.

---

## Capítulo XIII: Testing y Calidad

### 13.1 Infraestructura de Testing

El framework de testing combina Vitest como test runner y Testing Library para renderizado de componentes React. La configuración en `vite.config.ts` habilita entorno jsdom para simular APIs del navegador en Node.js.

Los tests unitarios verifican funciones puras como los helpers del tableStore: cálculo de totales, generación de IDs, validación de cantidades. Estos tests ejecutan rápidamente y proporcionan alta confianza en la lógica de negocio core.

Los tests de integración verifican hooks y stores: que `useCartSync` procese correctamente eventos WebSocket, que el tableStore persista y rehidrate estado correctamente, que las operaciones asíncronas manejen errores apropiadamente.

### 13.2 Cobertura y Ejecución

Los scripts de npm proporcionan múltiples modos de ejecución:
- `npm test`: Modo watch que re-ejecuta tests afectados al modificar archivos
- `npm run test:run`: Ejecución única para CI/CD pipelines
- `npm run test:coverage`: Genera reporte de cobertura de código

La cobertura actual se enfoca en las áreas más críticas: lógica de carrito, sincronización de estado, manejo de errores. Los componentes visuales tienen menor cobertura dado que su corrección se verifica más efectivamente mediante testing manual y visual.

### 13.3 Patrones de Testing

Los tests de hooks utilizan `renderHook` de Testing Library para montar hooks en aislamiento. Los mocks de Zustand reemplazan stores reales con versiones controladas que permiten verificar interacciones.

```typescript
describe('useCartSync', () => {
  it('debería añadir item cuando recibe CART_ITEM_ADDED', () => {
    const { result } = renderHook(() => useCartSync())
    // Simular evento WebSocket
    // Verificar que el item aparece en el estado
  })
})
```

Los tests de servicios mockean fetch para simular respuestas de API. Los tests de error verifican que errores de red, timeouts y respuestas de error se manejen gracefully sin crashear la aplicación.

---

## Epílogo: Consideraciones Futuras

La arquitectura de pwaMenu establece fundamentos sólidos para evolución futura. Algunas direcciones potenciales de desarrollo incluyen:

**Virtualización de listas**: Para restaurantes con catálogos muy extensos, implementar virtualización de scroll renderizaría solo productos visibles, mejorando rendimiento en dispositivos modestos.

**Sync offline completo**: Actualmente el queue offline maneja operaciones de carrito; expandirlo para sincronizar pedidos completos permitiría funcionalidad offline más robusta.

**Notificaciones push**: Integrar con la API de Push Notifications del navegador permitiría notificar a comensales sobre el estado de su pedido incluso cuando la app está en segundo plano.

**Modo multi-restaurante**: La arquitectura actual asume un único restaurante por instancia; abstraer el tenant ID permitiría marketplaces de restaurantes.

**Analítica avanzada**: Las métricas Web Vitals recolectadas podrían alimentar dashboards de rendimiento y detección de regresiones.

La modularidad del código, la separación clara de responsabilidades y los patrones establecidos facilitan que futuras iteraciones extiendan la funcionalidad sin requerir reescrituras fundamentales.

---

*Documento generado como referencia arquitectónica para el equipo de desarrollo. Última actualización: Febrero 2026.*
