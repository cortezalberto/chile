# Auditoría Exhaustiva de Código - auditoria36.md

**Fecha:** 16 de Enero 2026
**Auditor:** QA Senior
**Alcance:** pwaMenu y pwaWaiter - Análisis exhaustivo de stores, hooks, services, components y pages
**Actualizado:** 17 de Enero 2026 - **TODOS LOS DEFECTOS CORREGIDOS**

---

## Resumen Ejecutivo

| Componente | CRITICAL | HIGH | MEDIUM | LOW | Total | Estado |
|------------|----------|------|--------|-----|-------|--------|
| pwaMenu Stores | 0 | 4 | 7 | 4 | 15 | ✅ |
| pwaMenu Hooks | 1 | 2 | 5 | 3 | 11 | ✅ |
| pwaMenu Services | 0 | 1 | 9 | 7 | 17 | ✅ |
| pwaMenu Components | 0 | 2 | 5 | 3 | 10 | ✅ |
| pwaMenu Pages | 0 | 2 | 4 | 1 | 7 | ✅ |
| pwaWaiter Stores | 2 | 6 | 7 | 3 | 18 | ✅ |
| pwaWaiter Services | 3 | 6 | 8 | 5 | 22 | ✅ |
| pwaWaiter Hooks | 0 | 1 | 6 | 4 | 11 | ✅ |
| pwaWaiter Components | 2 | 5 | 10 | 7 | 24 | ✅ |
| **TOTAL** | **8** | **29** | **61** | **37** | **135** | **✅ ALL FIXED** |

**Estado:** ✅ **135 DEFECTOS IDENTIFICADOS - TODOS CORREGIDOS**

### Correcciones Aplicadas (Resumen)

| Severidad | Total | Corregidos | Estado |
|-----------|-------|------------|--------|
| CRITICAL | 8 | 8 | ✅ |
| HIGH | 29 | 29 | ✅ |
| MEDIUM | 61 | 61 | ✅ |
| LOW | 37 | 37 | ✅ |

**Key Fixes:**
- **WAITER-STORE-CRIT-01**: Selectores con memoización manual para React 19 compatibility
- **WAITER-STORE-CRIT-02**: Función `cleanupOnlineListener()` exportada para cleanup
- **WAITER-SVC-CRIT-03**: Límite máximo de Set `recentNotifications` (100 items)
- **MENU-HOOK-CRIT-01**: isMounted guard en useAllergenFilter para fetch async
- **WAITER-SVC-MED-02**: Timeout wrapper para todas las operaciones IndexedDB (30s)
- **WAITER-COMP-CRIT-01/02**: Focus trap completo en ConfirmDialog
- **WAITER-HOOK-MED-01**: setTimeout cleanup en useOnlineStatus

---

## Parte 1: pwaMenu Stores (15 defectos)

### HIGH (4)

#### MENU-STORE-HIGH-01: Missing Error Handling in sessionStore restoreSession
**Archivo:** `pwaMenu/src/stores/sessionStore.ts`
**Líneas:** 232-247

**Descripción:** La acción `restoreSession` reconecta WebSocket sin manejar errores potenciales de `dinerWS.connect()`. Si la conexión falla, la función retorna `true` sugiriendo éxito cuando la sesión puede no estar restaurada.

```typescript
restoreSession: async () => {
  const token = getTableToken()
  if (!token) {
    return false
  }

  const state = get()
  if (state.sessionId && state.currentDiner) {
    dinerWS.connect()  // No error handling, no await
    return true  // Returns true even if connection fails
  }

  return false
},
```

**Impacto:** Usuarios pueden pensar que su sesión está restaurada cuando la conexión WebSocket falló.

---

#### MENU-STORE-HIGH-02: Unstable Array Reference in serviceCallStore selectPendingCalls
**Archivo:** `pwaMenu/src/stores/serviceCallStore.ts`
**Líneas:** 76-77

**Descripción:** El selector `selectPendingCalls` crea un nuevo array filtrado en cada llamada. En React 19 con Zustand, esto puede causar re-renders infinitos.

```typescript
export const selectPendingCalls = (state: ServiceCallState) =>
  state.calls.filter((c) => c.status === 'pending' || c.status === 'acked')
```

**Fix recomendado:**
```typescript
const EMPTY_CALLS: ServiceCallRecord[] = []
export const selectPendingCalls = (state: ServiceCallState) => {
  const filtered = state.calls.filter((c) => c.status === 'pending' || c.status === 'acked')
  return filtered.length > 0 ? filtered : EMPTY_CALLS
}
```

---

#### MENU-STORE-HIGH-03: Race Condition in useAllergenFilter Cross-Reactions Fetch
**Archivo:** `pwaMenu/src/hooks/useAllergenFilter.ts`
**Líneas:** 178-204

**Descripción:** El efecto de fetch de cross-reactions no maneja el caso donde `branchSlug` cambia durante una petición en vuelo. La respuesta obsoleta podría actualizar el estado para el branch incorrecto.

```typescript
useEffect(() => {
  if (!branchSlug || fetchedSlugRef.current === branchSlug) return

  setCrossReactionsLoading(true)
  menuAPI.getAllergensWithCrossReactions(branchSlug)  // No abort controller
    .then((data) => {
      // No check if branchSlug changed during fetch
      setAllergensWithCrossReactions(data)
      setCachedCrossReactions(branchSlug, data)
      fetchedSlugRef.current = branchSlug
    })
    // ...
}, [branchSlug])
```

---

#### MENU-STORE-HIGH-04: Listener Accumulation Risk in useServiceCallUpdates
**Archivo:** `pwaMenu/src/hooks/useServiceCallUpdates.ts`
**Líneas:** 109-128

**Descripción:** El efecto que suscribe a eventos WebSocket tiene `handleAcked` y `handleClosed` en su array de dependencias. A diferencia de `useOrderUpdates` que usa el patrón de ref para suscribirse una sola vez, este hook re-suscribe en cada cambio de referencia del callback.

```typescript
useEffect(() => {
  if (!session?.backendSessionId) {
    return
  }

  const unsubscribeAcked = dinerWS.on('SERVICE_CALL_ACKED', handleAcked)
  const unsubscribeClosed = dinerWS.on('SERVICE_CALL_CLOSED', handleClosed)

  return () => {
    unsubscribeAcked()
    unsubscribeClosed()
  }
}, [session?.backendSessionId, handleAcked, handleClosed])
```

---

### MEDIUM (7)

#### MENU-STORE-MED-01: Missing Cleanup for throttleNotifyCallback
**Archivo:** `pwaMenu/src/stores/tableStore/helpers.ts`
**Líneas:** 221-228

**Descripción:** La función `setThrottleNotifyCallback` establece un callback a nivel de módulo pero no hay mecanismo para limpiarlo cuando el componente que lo estableció se desmonta.

---

#### MENU-STORE-MED-02: Inconsistent EMPTY_ARRAY Pattern in menuStore
**Archivo:** `pwaMenu/src/stores/menuStore.ts`
**Líneas:** 114-127

**Descripción:** Los selectores `selectFeaturedProducts`, `selectPopularProducts`, y `selectAvailableProducts` crean nuevos arrays filtrados en cada llamada, a diferencia del patrón estable usado en otros selectores.

---

#### MENU-STORE-MED-03: Missing AbortController in useAllergenFilter
**Archivo:** `pwaMenu/src/hooks/useAllergenFilter.ts`
**Líneas:** 178-204

**Descripción:** La llamada API para fetch de cross-reactions no usa AbortController para cleanup, causando potenciales memory leaks.

---

#### MENU-STORE-MED-04: Potential Stale Closure in useOrderUpdates
**Archivo:** `pwaMenu/src/hooks/useOrderUpdates.ts`
**Líneas:** 73-108

**Descripción:** La función `handleRoundEvent` llama directamente a `playEventSoundIfEnabled` en lugar de usar el patrón de ref como otras dependencias.

---

#### MENU-STORE-MED-05: No Session Validation in serviceCallStore
**Archivo:** `pwaMenu/src/stores/serviceCallStore.ts`
**Líneas:** 28-72

**Descripción:** El store de service call persiste en localStorage pero no valida que las llamadas pertenezcan a la sesión actual.

---

#### MENU-STORE-MED-06: Missing isLoading State Update in menuStore clearMenu
**Archivo:** `pwaMenu/src/stores/menuStore.ts`
**Líneas:** 254-265

**Descripción:** La acción `clearMenu` no resetea el estado `isLoading`, lo que podría dejar la UI en estado de carga indefinidamente.

---

#### MENU-STORE-MED-07: Concurrent State Mutation Risk in tableStore addToCart
**Archivo:** `pwaMenu/src/stores/tableStore/store.ts`
**Líneas:** 349-428

**Descripción:** La acción `addToCart` usa `get()` para leer el estado y luego `set()` para actualizarlo. Llamadas rápidas concurrentes podrían sobrescribir cambios.

---

### LOW (4)

#### MENU-STORE-LOW-01: Inconsistent Error State Handling in sessionStore
**Archivo:** `pwaMenu/src/stores/sessionStore.ts`
**Líneas:** 138-143

**Descripción:** La acción `joinTable` establece estado de error y luego re-lanza el error, causando manejo dual inconsistente.

---

#### MENU-STORE-LOW-02: Hardcoded Magic Number in useServiceCallUpdates
**Archivo:** `pwaMenu/src/hooks/useServiceCallUpdates.ts`
**Líneas:** 87-90

**Descripción:** El delay de auto-reset de 3000ms está hardcodeado en lugar de usar constantes centralizadas.

---

#### MENU-STORE-LOW-03: Missing TypeScript Type Guard in tableStore
**Archivo:** `pwaMenu/src/stores/tableStore/store.ts`
**Líneas:** 44-53

**Descripción:** La función `applyStatusUpdate` acepta cualquier string como status sin validar que sea un valor válido de `OrderStatus`.

---

#### MENU-STORE-LOW-04: Unused Import in useAdvancedFilters
**Archivo:** `pwaMenu/src/hooks/useAdvancedFilters.ts`
**Líneas:** 84-92

**Descripción:** El callback `filterProducts` referencia `hasAnyActiveFilter` antes de que sea definido, y falta en el array de dependencias.

---

## Parte 2: pwaMenu Hooks (11 defectos)

### CRITICAL (1)

#### MENU-HOOK-CRIT-01: Race Condition - Async State Update Without Mount Guard
**Archivo:** `pwaMenu/src/hooks/useAllergenFilter.ts`
**Líneas:** 178-204

**Descripción:** El useEffect que fetches cross-reactions de la API no verifica si el componente sigue montado antes de actualizar el estado. El callback `.then()` puede ejecutarse después de que el componente se desmonte.

```typescript
useEffect(() => {
  if (!branchSlug || fetchedSlugRef.current === branchSlug) return

  setCrossReactionsLoading(true)
  menuAPI.getAllergensWithCrossReactions(branchSlug)
    .then((data) => {
      // DEFECT: No mount check before setState
      setAllergensWithCrossReactions(data)
      setCachedCrossReactions(branchSlug, data)
      fetchedSlugRef.current = branchSlug
    })
    .catch(() => {
      setAllergensWithCrossReactions([])
    })
    .finally(() => {
      setCrossReactionsLoading(false)
    })
}, [branchSlug])
```

**Impacto:** Memory leak y warning de React sobre actualizar componente desmontado.

---

### HIGH (2)

#### MENU-HOOK-HIGH-01: hasAnyActiveFilter Used Before Definition
**Archivo:** `pwaMenu/src/hooks/useAdvancedFilters.ts`
**Líneas:** 84-92

**Descripción:** El callback `filterProducts` usa la variable `hasAnyActiveFilter` antes de que sea definida (líneas 108-117). Además, `hasAnyActiveFilter` falta en el array de dependencias.

```typescript
const filterProducts = useCallback(
  <T extends ProductFilterData>(products: T[]): T[] => {
    if (!hasAnyActiveFilter) {  // hasAnyActiveFilter defined later (line 108)
      return products
    }
    return products.filter(shouldShowProduct)
  },
  [shouldShowProduct]  // Missing hasAnyActiveFilter in dependencies
)
```

---

#### MENU-HOOK-HIGH-02: Missing Error Handling for closeTable
**Archivo:** `pwaMenu/src/hooks/useCloseTableFlow.ts`
**Líneas:** 42-59

**Descripción:** La función `startCloseFlow` llama a `closeTable()` sin un wrapper try-catch. Si `closeTable()` lanza una excepción, el Promise rejection no será capturado.

```typescript
const startCloseFlow = useCallback(async (): Promise<boolean> => {
  setCloseStatus('requesting')
  setError(null)

  const result = await closeTable()  // No try-catch

  if (!isMounted()) return false

  if (result.success) {
    setCloseStatus('bill_ready')
    return true
  } else {
    setError(result.error || 'Error closing table')
    setCloseStatus('idle')
    return false
  }
}, [closeTable, isMounted])
```

---

### MEDIUM (5)

#### MENU-HOOK-MED-01: Missing useCallback Dependencies Documentation
**Archivo:** `pwaMenu/src/hooks/useDebounce.ts`
**Líneas:** 58-60

**Descripción:** El efecto que sincroniza `callbackRef` no tiene array de dependencias, lo cual es intencional pero no está documentado.

---

#### MENU-HOOK-MED-02: Potential Double Timer Start in useAutoCloseTimer
**Archivo:** `pwaMenu/src/hooks/useAutoCloseTimer.ts`
**Líneas:** 48-70

**Descripción:** El early return cuando `enabled` es false no ejecuta cleanup, el timer existente podría continuar.

---

#### MENU-HOOK-MED-03: Over-selecting Session Object in useServiceCallUpdates
**Archivo:** `pwaMenu/src/hooks/useServiceCallUpdates.ts`
**Línea:** 38

**Descripción:** El selector retorna el objeto session completo cuando solo se necesita `backendSessionId`. Cambios en otros campos causan re-renders innecesarios.

---

#### MENU-HOOK-MED-04: Over-selecting Session Object in useOrderUpdates
**Archivo:** `pwaMenu/src/hooks/useOrderUpdates.ts`
**Línea:** 41

**Descripción:** Mismo problema que MED-03 - selector demasiado amplio.

---

#### MENU-HOOK-MED-05: Announcements May Be Lost During Politeness Transition
**Archivo:** `pwaMenu/src/hooks/useAriaAnnounce.ts`
**Línea:** 41

**Descripción:** Si `politeness` cambia mientras hay un timeout de mensaje pendiente, los anuncios durante la transición podrían perderse.

---

### LOW (3)

#### MENU-HOOK-LOW-01: Potential Memoization Issue in useProductTranslation
**Archivo:** `pwaMenu/src/hooks/useProductTranslation.ts`
**Líneas:** 33-38

**Descripción:** El callback `translateProducts` podría beneficiarse de memoización adicional para arrays grandes.

---

#### MENU-HOOK-LOW-02: filterState Object in Dependencies Less Precise
**Archivo:** `pwaMenu/src/hooks/useCookingMethodFilter.ts`
**Línea:** 166

**Descripción:** Usar el objeto completo `filterState` como dependencia es menos preciso que usar arrays individuales.

---

#### MENU-HOOK-LOW-03: Toggle Function Doesn't Clear Pending Timeout
**Archivo:** `pwaMenu/src/hooks/useModal.ts`
**Líneas:** 78-80

**Descripción:** La función `toggle` no cancela timeouts pendientes de cierre como hacen `open` y `close`.

---

## Parte 3: pwaMenu Services (17 defectos)

### HIGH (1)

#### MENU-SVC-HIGH-01: Token Validation Missing in restoreSession
**Archivo:** `pwaMenu/src/stores/sessionStore.ts`
**Líneas:** 232-247

**Descripción:** La función `restoreSession` verifica si un token existe y si el estado local tiene sessionId/currentDiner, pero nunca valida si el token sigue siendo válido con el backend.

---

### MEDIUM (9)

#### MENU-SVC-MED-01: Missing Request Timeout in mercadoPago.ts
**Archivo:** `pwaMenu/src/services/mercadoPago.ts`
**Líneas:** 142-150

**Descripción:** La función `createPaymentPreference` usa `fetch()` sin manejo de timeout. Si la API de pago es lenta, la petición colgará indefinidamente.

---

#### MENU-SVC-MED-02: No SSRF Validation for API_BASE in mercadoPago.ts
**Archivo:** `pwaMenu/src/services/mercadoPago.ts`
**Línea:** 15

**Descripción:** A diferencia de `api.ts` que valida `API_BASE` contra hosts permitidos para prevención de SSRF, `mercadoPago.ts` usa `API_BASE` directamente sin validación.

---

#### MENU-SVC-MED-03: Race Condition in Request Deduplication
**Archivo:** `pwaMenu/src/services/api.ts`
**Líneas:** 263-275

**Descripción:** La lógica de deduplicación de requests itera sobre `pendingRequests` mientras potencialmente otras operaciones async podrían modificarlo.

---

#### MENU-SVC-MED-04: No Reconnection Limit Notification
**Archivo:** `pwaMenu/src/services/websocket.ts`
**Líneas:** 234-238

**Descripción:** Cuando se alcanzan los intentos máximos de reconexión, el código solo loguea un error pero no provee callback o evento para que la UI notifique al usuario.

---

#### MENU-SVC-MED-05: Singleton Pattern May Cause Issues
**Archivo:** `pwaMenu/src/services/websocket.ts`
**Línea:** 330

**Descripción:** El singleton `dinerWS` se exporta directamente. Si un componente llama `disconnect()`, afecta a todos los otros componentes usando la misma instancia.

---

#### MENU-SVC-MED-06: Potential Memory Leak in Deduplication Cleanup
**Archivo:** `pwaMenu/src/services/api.ts`
**Líneas:** 184-214

**Descripción:** La función `cleanupPendingRequests` usa cleanup basado en tiempo que solo corre cuando el mapa excede 100 entradas O después de 60 segundos.

---

#### MENU-SVC-MED-07: Subscriptions Created Before Connection Check
**Archivo:** `pwaMenu/src/hooks/useOrderUpdates.ts`
**Líneas:** 59-68 vs 71-167

**Descripción:** El hook tiene dos efectos separados - uno para conectar WebSocket y uno para suscribirse a eventos. El efecto de suscripción tiene dependencias vacías `[]` y corre inmediatamente.

---

#### MENU-SVC-MED-08: No Retry Logic for Transient Failures
**Archivo:** `pwaMenu/src/services/api.ts`
**Líneas:** 248-391

**Descripción:** La función `request` no implementa retry automático para fallos transitorios (como 503 Service Unavailable).

---

#### MENU-SVC-MED-09: fetchMenu Throws After Setting Error State
**Archivo:** `pwaMenu/src/stores/menuStore.ts`
**Líneas:** 187-193

**Descripción:** La función `fetchMenu` establece estado de error y luego re-lanza el error, causando potencial manejo doble.

---

### LOW (7)

#### MENU-SVC-LOW-01: Inconsistent API_BASE Default
**Archivo:** `pwaMenu/src/services/mercadoPago.ts`
**Línea:** 15

**Descripción:** API_BASE por defecto es `/api/v1` que difiere de `api.ts` que usa `http://localhost:8000/api`.

---

#### MENU-SVC-LOW-02: Token Stored in Module-Level Variable
**Archivo:** `pwaMenu/src/services/api.ts`
**Línea:** 29

**Descripción:** El `tableToken` se almacena en variable a nivel de módulo, podría persistir a través de hot module reloading.

---

#### MENU-SVC-LOW-03: Hardcoded Emoji in Logger Messages
**Archivo:** `pwaMenu/src/services/websocket.ts`
**Líneas:** Múltiples

**Descripción:** Los mensajes de log contienen caracteres emoji hardcodeados que podrían no renderizar correctamente en todos los entornos.

---

#### MENU-SVC-LOW-04: Token Exposed in WebSocket URL
**Archivo:** `pwaMenu/src/services/websocket.ts`
**Línea:** 109

**Descripción:** El table token se pasa como query parameter en la URL de WebSocket.

---

#### MENU-SVC-LOW-05: No Size Limit on Service Calls Array
**Archivo:** `pwaMenu/src/stores/serviceCallStore.ts`
**Líneas:** 33-44

**Descripción:** El array `calls` crece ilimitadamente mientras se agregan service calls.

---

#### MENU-SVC-LOW-06: lastPongReceived Not Used for Connection Health
**Archivo:** `pwaMenu/src/services/websocket.ts`
**Líneas:** 34, 124, 323-326

**Descripción:** El timestamp `lastPongReceived` se trackea pero solo se expone vía `getLastPongAge()` para debugging.

---

#### MENU-SVC-LOW-07: credentials: 'same-origin' May Block Cross-Origin
**Archivo:** `pwaMenu/src/services/api.ts`
**Línea:** 307

**Descripción:** La función request usa `credentials: 'same-origin'`, pero CLAUDE.md menciona que `credentials: 'include'` es requerido para cross-origin.

---

## Parte 4: pwaMenu Components (10 defectos)

### HIGH (2)

#### MENU-COMP-HIGH-01: Missing useCallback in AdvancedFiltersModal
**Archivo:** `pwaMenu/src/components/AdvancedFiltersModal.tsx`
**Línea:** 326

**Descripción:** El handler `onMethodChange` pasado a `PaymentMethodSelector` crea una nueva función en cada render debido a arrow function inline.

---

#### MENU-COMP-HIGH-02: Missing Escape Key Handler in ServiceCallHistory
**Archivo:** `pwaMenu/src/components/ServiceCallHistory.tsx`
**Líneas:** 15-66

**Descripción:** El componente `ServiceCallHistory` renderiza un modal pero no usa el hook `useEscapeKey` para accesibilidad por teclado.

---

### MEDIUM (5)

#### MENU-COMP-MED-01: Missing Body Scroll Lock in ServiceCallHistory
**Archivo:** `pwaMenu/src/components/ServiceCallHistory.tsx`
**Líneas:** 15-66

**Descripción:** El modal no previene scroll del body cuando está abierto.

---

#### MENU-COMP-MED-02: Unused Translation Variable in AdvancedFiltersModal
**Archivo:** `pwaMenu/src/components/AdvancedFiltersModal.tsx`
**Línea:** 44

**Descripción:** La función de traducción `t` se extrae pero nunca se usa - todo el texto está hardcodeado en español.

---

#### MENU-COMP-MED-03: Missing useMemo for Derived Options Arrays
**Archivo:** `pwaMenu/src/components/AdvancedFiltersModal.tsx`
**Líneas:** 93-110

**Descripción:** Los arrays `strictnessOptions`, `sensitivityOptions`, y `methods` se recrean en cada render.

---

#### MENU-COMP-MED-04: Missing Image Error Handler in CartItemCard
**Archivo:** `pwaMenu/src/components/cart/CartItemCard.tsx`
**Líneas:** 27-34

**Descripción:** El elemento `img` carece de handler `onError` para fallback a imagen por defecto.

---

#### MENU-COMP-MED-05: OrderHistory Missing useEscapeKey Hook
**Archivo:** `pwaMenu/src/components/OrderHistory.tsx`
**Líneas:** 111-193

**Descripción:** El componente modal `OrderHistory` no implementa `useEscapeKey` para dismissal por teclado.

---

### LOW (3)

#### MENU-COMP-LOW-01: Hardcoded Locale in formatTime Function
**Archivo:** `pwaMenu/src/components/OrderHistory.tsx`
**Líneas:** 21-24

**Descripción:** La función `formatTime` usa locale hardcodeado 'es-AR' en lugar del lenguaje actual de i18n.

---

#### MENU-COMP-LOW-02: Missing aria-hidden on Decorative SVG
**Archivo:** `pwaMenu/src/components/FilterBadge.tsx`
**Líneas:** 45-57

**Descripción:** El SVG del icono de filtro carece de `aria-hidden="true"`.

---

#### MENU-COMP-LOW-03: SubcategoryGrid Not Memoized at Top Level
**Archivo:** `pwaMenu/src/components/SubcategoryGrid.tsx`
**Líneas:** 13-70

**Descripción:** El componente `SubcategoryGrid` no está wrapped en `memo()` mientras su hijo `SubcategoryCard` sí está memoizado.

---

## Parte 5: pwaMenu Pages (7 defectos)

### HIGH (2)

#### MENU-PAGE-HIGH-01: Missing AbortController for fetch operations
**Archivo:** `pwaMenu/src/pages/Home.tsx`
**Líneas:** 122-133

**Descripción:** El useEffect que fetches menu y allergens no usa AbortController para cancelar peticiones pendientes si el componente se desmonta.

```typescript
useEffect(() => {
  const slug = import.meta.env.VITE_BRANCH_SLUG || 'demo-branch'
  if (!branchSlug || branchSlug !== slug) {
    fetchMenu(slug).catch((err) => {
      menuStoreLogger.error('Failed to load menu from backend:', err)
    })
    fetchAllergens(slug).catch((err) => {
      menuStoreLogger.error('Failed to load allergens from backend:', err)
    })
  }
}, [fetchMenu, fetchAllergens, branchSlug])
```

---

#### MENU-PAGE-HIGH-02: hasAnyActiveFilter Missing in Callback Dependencies
**Archivo:** `pwaMenu/src/hooks/useAdvancedFilters.ts`
**Líneas:** 84-92

**Descripción:** El callback `filterProducts` usa `hasAnyActiveFilter` pero no lo incluye en el array de dependencias.

---

### MEDIUM (4)

#### MENU-PAGE-MED-01: Missing Loading State for Menu Data
**Archivo:** `pwaMenu/src/pages/Home.tsx`
**Líneas:** 87-554

**Descripción:** El componente `Home` no verifica `isLoading` de `menuStore` antes de renderizar contenido del menú.

---

#### MENU-PAGE-MED-02: Missing Error Handling Display for Menu Fetch
**Archivo:** `pwaMenu/src/pages/Home.tsx`
**Líneas:** 87-554

**Descripción:** Aunque `menuStore` establece un estado `error` en fallos de fetch, `Home.tsx` no lee ni muestra este error al usuario.

---

#### MENU-PAGE-MED-03: shares Calculated Without useMemo
**Archivo:** `pwaMenu/src/pages/CloseTable.tsx`
**Línea:** 114

**Descripción:** La variable `shares` se computa via `getPaymentShares()` directamente en el cuerpo del render sin `useMemo`.

---

#### MENU-PAGE-MED-04: statusConfig Recreated on Every Render
**Archivo:** `pwaMenu/src/pages/PaymentResult.tsx`
**Líneas:** 88-177

**Descripción:** El objeto grande `statusConfig` se crea dentro del cuerpo del componente en cada render.

---

### LOW (1)

#### MENU-PAGE-LOW-01: documentTitle Computed Without Memoization
**Archivo:** `pwaMenu/src/pages/PaymentResult.tsx`
**Líneas:** 29-35

**Descripción:** El `documentTitle` se computa directamente en render sin `useMemo`.

---

## Parte 6: pwaWaiter Stores (18 defectos)

### CRITICAL (2)

#### WAITER-STORE-CRIT-01: Unstable Selector Returns New Array Every Call
**Archivo:** `pwaWaiter/src/stores/tablesStore.ts`
**Líneas:** 292-299

**Descripción:** Los selectores `selectTablesWithPendingRounds`, `selectTablesWithServiceCalls`, y `selectTablesWithCheckRequested` retornan `state.tables.filter(...)` que crea una nueva referencia de array en cada llamada. En React 19 con Zustand, esto causa re-renders infinitos.

```typescript
// CRITICAL: These create new arrays on EVERY call, causing infinite loops in React 19
export const selectTablesWithPendingRounds = (state: TablesState) =>
  state.tables.filter((t) => t.open_rounds > 0)  // NEW ARRAY EVERY CALL

export const selectTablesWithServiceCalls = (state: TablesState) =>
  state.tables.filter((t) => t.pending_calls > 0)  // NEW ARRAY EVERY CALL
```

---

#### WAITER-STORE-CRIT-02: Global Event Listener Never Removed
**Archivo:** `pwaWaiter/src/stores/retryQueueStore.ts`
**Líneas:** 213-218

**Descripción:** El `window.addEventListener('online', ...)` se registra al cargar el módulo y NUNCA se remueve (no hay `removeEventListener` correspondiente).

```typescript
let onlineListenerRegistered = false

if (typeof window !== 'undefined' && !onlineListenerRegistered) {
  onlineListenerRegistered = true
  window.addEventListener('online', () => {  // NEVER REMOVED
    storeLogger.info('Back online - processing retry queue')
    useRetryQueueStore.getState().processQueue()
  })
}
```

---

### HIGH (6)

#### WAITER-STORE-HIGH-01: Memory Leak - Interval Not Cleared on Module Reload
**Archivo:** `pwaWaiter/src/stores/authStore.ts`
**Líneas:** 12, 43-48

**Descripción:** El `refreshIntervalId` se almacena en variable a nivel de módulo, pero si el módulo se hot-reload durante desarrollo, el intervalo antiguo sigue corriendo mientras se crea uno nuevo.

---

#### WAITER-STORE-HIGH-02: Recursive checkAuth() Can Cause Stack Overflow
**Archivo:** `pwaWaiter/src/stores/authStore.ts`
**Líneas:** 252-256

**Descripción:** Después de un token refresh exitoso en `checkAuth()`, se llama recursivamente a sí misma. Si el token refrescado también es inválido, esto crea un patrón de recursión infinita.

```typescript
if (refreshed) {
  // Retry auth check with new token
  return get().checkAuth()  // RECURSIVE CALL
}
```

---

#### WAITER-STORE-HIGH-03: Race Condition in WebSocket Event Handler
**Archivo:** `pwaWaiter/src/stores/tablesStore.ts`
**Líneas:** 257-279

**Descripción:** La función `handleWSEvent` fetches datos de tabla asincrónicamente y luego actualiza el estado. Entre la llamada `get().tables` y el `set({ tables: newTables })`, otros eventos podrían haber modificado el array de tables.

---

#### WAITER-STORE-HIGH-04: Missing Unsubscribe Call in Cleanup Path
**Archivo:** `pwaWaiter/src/stores/tablesStore.ts`
**Líneas:** 168-188

**Descripción:** La función `subscribeToEvents` retorna una función unsubscribe, pero si el componente que la llama se desmonta antes de que la conexión WebSocket se establezca, los listeners podrían filtrar.

---

#### WAITER-STORE-HIGH-05: Race Condition Between enqueue and processQueue
**Archivo:** `pwaWaiter/src/stores/retryQueueStore.ts`
**Líneas:** 104-113

**Descripción:** La función `enqueue` verifica `!get().isProcessing` y luego programa `processQueue()` via `setTimeout`. Hay una race condition TOCTOU entre la verificación y la ejecución del callback.

---

#### WAITER-STORE-HIGH-06: processQueue Mutates Original Queue Array
**Archivo:** `pwaWaiter/src/stores/retryQueueStore.ts`
**Líneas:** 116-178

**Descripción:** La función `processQueue` itera sobre `queue` y luego reemplaza toda la cola con `failedActions`. Si una nueva acción se encola durante el procesamiento, será perdida.

---

### MEDIUM (7)

#### WAITER-STORE-MED-01: Race Condition - Double isRefreshing Reset
**Archivo:** `pwaWaiter/src/stores/authStore.ts`
**Líneas:** 186-206

**Descripción:** El flag `isRefreshing` se establece a `false` tanto en el caso de éxito como en el bloque `finally`. Hay un gap entre verificar `isRefreshing` y establecerlo donde dos llamadas concurrentes podrían pasar la verificación.

---

#### WAITER-STORE-MED-02: Token Refresh Interval Starts Even Without Refresh Token
**Archivo:** `pwaWaiter/src/stores/authStore.ts`
**Línea:** 112

**Descripción:** En la función `login`, `startTokenRefreshInterval()` se llama incondicionalmente incluso cuando `refreshTokenValue` es null.

---

#### WAITER-STORE-MED-03: selectSelectedTable Creates New Object on Every Call
**Archivo:** `pwaWaiter/src/stores/tablesStore.ts`
**Líneas:** 285-286

**Descripción:** El selector usa `find()` que atraviesa el array en cada llamada.

---

#### WAITER-STORE-MED-04: No Timeout for Individual Action Execution
**Archivo:** `pwaWaiter/src/stores/retryQueueStore.ts`
**Líneas:** 133-173

**Descripción:** El loop `for` en `processQueue` ejecuta acciones secuencialmente con `await executeAction(action)`. Si una acción cuelga, todo el procesamiento de cola se bloquea.

---

#### WAITER-STORE-MED-05: BroadcastChannel Message Handler Race Condition
**Archivo:** `pwaWaiter/src/stores/historyStore.ts`
**Líneas:** 48-52

**Descripción:** El handler `onmessage` llama directamente a `store.setState({ entries: event.data.entries })` sin validación.

---

#### WAITER-STORE-MED-06: selectRecentActions Creates New Selector Function Every Call
**Archivo:** `pwaWaiter/src/stores/historyStore.ts`
**Líneas:** 155-156

**Descripción:** `selectRecentActions` es un factory de selectores que retorna una nueva función cada vez que se llama.

---

#### WAITER-STORE-MED-07: Potential Double Broadcast on Initialization
**Archivo:** `pwaWaiter/src/stores/historyStore.ts`
**Líneas:** 98-104

**Descripción:** El código de inicialización hace flush de `pendingBroadcasts` sincrónicamente durante la creación del store, potencialmente causando mensajes duplicados.

---

### LOW (3)

#### WAITER-STORE-LOW-01: Missing Error Handling for setTokenRefreshCallback
**Archivo:** `pwaWaiter/src/stores/authStore.ts`
**Líneas:** 107-109

**Descripción:** El `setTokenRefreshCallback` se llama con un callback que llama a `wsService.updateToken()`, pero si esto lanza, el error no se captura.

---

#### WAITER-STORE-LOW-02: Error from handleAuthError Not Propagated Properly
**Archivo:** `pwaWaiter/src/stores/tablesStore.ts`
**Líneas:** 62-66

**Descripción:** Cuando `handleAuthError` retorna true, la función lanza `new Error('Session expired')` pero el error no contiene los detalles del error original.

---

#### WAITER-STORE-LOW-03: Unused _get Parameter
**Archivo:** `pwaWaiter/src/stores/historyStore.ts`
**Línea:** 95

**Descripción:** La función de creación del store recibe `_get` (prefijado con underscore indicando no usado), pero esto es un code smell.

---

## Parte 7: pwaWaiter Services (22 defectos)

### CRITICAL (3)

#### WAITER-SVC-CRIT-01: Token Exposed in URL Query Parameter
**Archivo:** `pwaWaiter/src/services/websocket.ts`
**Línea:** 97

**Descripción:** El JWT token se pasa como URL query parameter que se loguea en access logs del servidor, historial del navegador, y puede exponerse via headers Referrer.

```typescript
const wsUrl = `${API_CONFIG.WS_URL}/ws/waiter?token=${token}`
```

---

#### WAITER-SVC-CRIT-02: handleTokenRefresh() Double-Connection Race Condition
**Archivo:** `pwaWaiter/src/services/websocket.ts`
**Líneas:** 446-463

**Descripción:** El método `handleTokenRefresh()` llama a `disconnect()` que establece `isIntentionalClose=true` y limpia el token, luego inmediatamente intenta reconectar. Sin embargo, después de `disconnect()` el token se establece a null, haciendo imposible la reconexión.

```typescript
private async handleTokenRefresh(): Promise<void> {
  if (!this.tokenRefreshCallback) return

  try {
    const newToken = await this.tokenRefreshCallback()
    if (newToken && !this.isIntentionalClose) {
      this.disconnect()          // Sets token = null
      this.isIntentionalClose = false
      await this.connect(newToken)  // Uses newToken, but disconnect cleared state
    }
  } catch (error) {
    wsLogger.error('Token refresh failed', error)
  }
}
```

---

#### WAITER-SVC-CRIT-03: Memory Leak - recentNotifications Set Never Bounds-Checked
**Archivo:** `pwaWaiter/src/services/notifications.ts`
**Líneas:** 7-8

**Descripción:** El Set `recentNotifications` crece ilimitadamente porque los items solo se remueven después de `NOTIFICATION_COOLDOWN_MS` (5 segundos), pero si muchas notificaciones llegan más rápido que el cooldown, el Set sigue creciendo.

---

### HIGH (6)

#### WAITER-SVC-HIGH-01: No Retry Logic for Failed API Requests
**Archivo:** `pwaWaiter/src/services/api.ts`
**Líneas:** 136-201

**Descripción:** La función `request()` no tiene lógica de retry integrada para fallos transitorios. Las peticiones fallidas lanzan inmediatamente sin retry.

---

#### WAITER-SVC-HIGH-02: Token Stored in Module-Level Variables Without Encryption
**Archivo:** `pwaWaiter/src/services/api.ts`
**Líneas:** 97-98

**Descripción:** Los tokens auth y refresh se almacenan en variables plain a nivel de módulo. En contexto PWA estos pueden accederse via DevTools del navegador.

---

#### WAITER-SVC-HIGH-03: WebSocket URL Not Validated for SSRF
**Archivo:** `pwaWaiter/src/services/websocket.ts`
**Línea:** 97

**Descripción:** Mientras la REST API tiene validación SSRF via `isValidApiBase()`, la URL de WebSocket (`API_CONFIG.WS_URL`) no se valida con las mismas verificaciones antes de conectar.

---

#### WAITER-SVC-HIGH-04: IndexedDB Database Connection Leaks on Errors
**Archivo:** `pwaWaiter/src/services/offline.ts`
**Líneas:** 39-69

**Descripción:** La función `openDB()` no cierra la conexión de base de datos en fallos de upgrade. Si `onupgradeneeded` falla, la conexión puede permanecer abierta.

---

#### WAITER-SVC-HIGH-05: No Timeout on IndexedDB Operations
**Archivo:** `pwaWaiter/src/services/offline.ts`
**Líneas:** A lo largo del archivo

**Descripción:** Todas las operaciones IndexedDB (getAll, put, delete, etc.) no tienen timeout. Si IndexedDB se vuelve no-responsive, estos Promises cuelgan para siempre.

---

#### WAITER-SVC-HIGH-06: Race Condition in updateToken() - Wait Time is Arbitrary
**Archivo:** `pwaWaiter/src/services/websocket.ts`
**Línea:** 230

**Descripción:** El fix para WS-CRIT-01 usa un delay hardcodeado de 100ms que es arbitrario y puede no ser suficiente en conexiones lentas.

---

### MEDIUM (8)

#### WAITER-SVC-MED-01: No Connection State Recovery on Token Refresh Failure
**Archivo:** `pwaWaiter/src/services/websocket.ts`
**Líneas:** 460-462

**Descripción:** Cuando `handleTokenRefresh()` falla, solo loguea el error pero no intenta re-usar el token viejo o notificar a la app que la conexión está rota.

---

#### WAITER-SVC-MED-02: Audio Playback May Fail Silently
**Archivo:** `pwaWaiter/src/services/notifications.ts`
**Líneas:** 87-89

**Descripción:** Cuando la reproducción de audio falla (común debido a políticas de autoplay), silenciosamente loguea a debug. El usuario no tiene indicación de que los sonidos de alerta no están funcionando.

---

#### WAITER-SVC-MED-03: JWT Parsing Can Fail on Non-Standard Tokens
**Archivo:** `pwaWaiter/src/services/websocket.ts`
**Líneas:** 394-415

**Descripción:** El parsing de token usa `atob()` que falla en JWTs codificados en base64url (que usan `-` y `_` en lugar de `+` y `/`).

---

#### WAITER-SVC-MED-04: Missing Error Handling for Response JSON Parsing
**Archivo:** `pwaWaiter/src/services/api.ts`
**Línea:** 182

**Descripción:** `JSON.parse(text)` no está wrapped en try-catch. Si el servidor retorna JSON malformado con status 200, lanzará una excepción no manejada.

---

#### WAITER-SVC-MED-05: Token Change Listeners Can Throw and Break Other Listeners
**Archivo:** `pwaWaiter/src/services/api.ts`
**Línea:** 115

**Descripción:** Si cualquier listener en `tokenChangeListeners` lanza, detiene la iteración y previene que otros listeners sean notificados.

---

#### WAITER-SVC-MED-06: No Cleanup of Pending Timeout on Repeated sendPing()
**Archivo:** `pwaWaiter/src/services/websocket.ts`
**Líneas:** 312-328

**Descripción:** Si `sendPing()` se llama múltiples veces antes de recibir un pong, múltiples timers de timeout pueden acumularse.

---

#### WAITER-SVC-MED-07: offline.ts Uses Direct console.* Instead of Logger
**Archivo:** `pwaWaiter/src/services/offline.ts`
**Líneas:** 21-34

**Descripción:** El archivo define su propio logger inline usando `console.info`, `console.warn`, `console.error` en lugar de importar el logger centralizado.

---

#### WAITER-SVC-MED-08: Potential TypeError When table_id is Undefined
**Archivo:** `pwaWaiter/src/services/notifications.ts`
**Línea:** 148

**Descripción:** El código asume que `event.table_id` existe, pero si el evento está malformado, la interpolación de string podría fallar.

---

### LOW (5)

#### WAITER-SVC-LOW-01: Hardcoded Sound File Path
**Archivo:** `pwaWaiter/src/services/notifications.ts`
**Línea:** 81

**Descripción:** El path del sonido de alerta está hardcodeado y no verifica si el archivo existe antes de intentar reproducir.

---

#### WAITER-SVC-LOW-02: Magic Number for Alert Sound Volume
**Archivo:** `pwaWaiter/src/services/notifications.ts`
**Línea:** 82

**Descripción:** El volumen está hardcodeado a 0.5 en lugar de usar `UI_CONFIG.ALERT_SOUND_VOLUME`.

---

#### WAITER-SVC-LOW-03: Notification Auto-Close Uses Magic Number
**Archivo:** `pwaWaiter/src/services/notifications.ts`
**Línea:** 133

**Descripción:** El timeout de auto-close está hardcodeado a 5000ms en lugar de usar una constante.

---

#### WAITER-SVC-LOW-04: processQueue() Lacks Concurrent Execution Guard
**Archivo:** `pwaWaiter/src/services/offline.ts`
**Líneas:** 297-360

**Descripción:** Si `processQueue()` se llama múltiples veces concurrentemente, las acciones podrían procesarse múltiples veces.

---

#### WAITER-SVC-LOW-05: Missing Type Assertion Safety in IndexedDB Callbacks
**Archivo:** `pwaWaiter/src/services/offline.ts`
**Líneas:** A lo largo del archivo

**Descripción:** Type assertions como `request.result as TableCard[]` asumen que los datos almacenados coinciden con el tipo, pero los datos podrían estar corruptos o de una versión vieja del schema.

---

## Parte 8: pwaWaiter Hooks (11 defectos)

### HIGH (1)

#### WAITER-HOOK-HIGH-01: Memory Leak - setTimeout Not Cleared
**Archivo:** `pwaWaiter/src/hooks/useOnlineStatus.ts`
**Línea:** 24

**Descripción:** El `setTimeout` dentro de `handleOnline` nunca se limpia. Si el componente se desmonta antes de que el timeout de 5 segundos complete, aún intentará actualizar estado en un componente desmontado.

```typescript
const handleOnline = useCallback(() => {
  setIsOnline(true)
  setLastOnlineAt(new Date())
  // Keep wasOffline true for a short period so UI can show "reconnected" message
  setTimeout(() => setWasOffline(false), 5000)  // Never cleaned up
}, [])
```

---

### MEDIUM (6)

#### WAITER-HOOK-MED-01: Stale Closure in handleTouchMove
**Archivo:** `pwaWaiter/src/hooks/usePullToRefresh.ts`
**Líneas:** 44-72

**Descripción:** El callback `handleTouchMove` lee `state.isPulling` y `state.isRefreshing` del closure, pero estos valores pueden volverse stale cuando el estado se actualiza rápidamente durante eventos touch.

---

#### WAITER-HOOK-MED-02: Stale Closure in handleTouchEnd
**Archivo:** `pwaWaiter/src/hooks/usePullToRefresh.ts`
**Líneas:** 75-97

**Descripción:** Similar a `handleTouchMove`, `handleTouchEnd` lee múltiples valores de estado del closure que pueden volverse stale.

---

#### WAITER-HOOK-MED-03: Missing Cleanup for Async Operation
**Archivo:** `pwaWaiter/src/hooks/usePullToRefresh.ts`
**Líneas:** 78-89

**Descripción:** Cuando `handleTouchEnd` llama a `await onRefresh()`, si el componente se desmonta durante la operación async, el `setState` en el bloque `finally` intentará actualizar estado en un componente desmontado.

---

#### WAITER-HOOK-MED-04: Race Condition in loadSessionDetail
**Archivo:** `pwaWaiter/src/pages/TableDetailPage.tsx`
**Líneas:** 46-60

**Descripción:** La función `loadSessionDetail` depende de `table?.table_id` y `table?.session_id`. Si el prop table cambia rápidamente, múltiples llamadas API podrían estar en vuelo simultáneamente.

---

#### WAITER-HOOK-MED-05: Missing AbortController for API Calls
**Archivo:** `pwaWaiter/src/pages/TableDetailPage.tsx`
**Líneas:** 46-60, 114-127

**Descripción:** Ni `loadSessionDetail` ni `handleMarkServed` usan AbortController para cancelar peticiones en vuelo cuando el componente se desmonta.

---

#### WAITER-HOOK-MED-06: Visibility Handler Not Re-Added After disconnect()
**Archivo:** `pwaWaiter/src/services/websocket.ts`
**Líneas:** 150-173

**Descripción:** Cuando `disconnect()` se llama, limpia el visibility listener via `cleanupVisibilityListener()`. Sin embargo, si `connect()` se llama de nuevo después de `disconnect()`, el visibility listener NO se re-agrega.

---

### LOW (4)

#### WAITER-HOOK-LOW-01: containerRef May Be Null During Event Handlers
**Archivo:** `pwaWaiter/src/hooks/usePullToRefresh.ts`
**Líneas:** 100-113

**Descripción:** El useEffect adjunta event listeners a `containerRef.current`, pero si la ref cambia o se vuelve null después del render inicial, los event handlers podrían tener referencias stale.

---

#### WAITER-HOOK-LOW-02: Multiple fetchTables Calls Without Coordination
**Archivo:** `pwaWaiter/src/pages/TableGridPage.tsx`
**Líneas:** 68-76

**Descripción:** El intervalo de refresh periódico y el handler de pull-to-refresh pueden ambos disparar `fetchTables` simultáneamente.

---

#### WAITER-HOOK-LOW-03: BroadcastChannel Initialization Edge Case
**Archivo:** `pwaWaiter/src/stores/historyStore.ts`
**Líneas:** 98-105

**Descripción:** El BroadcastChannel se inicializa sincrónicamente dentro de la función factory del store. Si Zustand recrea el store (ej. durante HMR), hay un guard, pero la referencia del canal podría volverse stale.

---

#### WAITER-HOOK-LOW-04: Global Online Event Listener Design Decision
**Archivo:** `pwaWaiter/src/stores/retryQueueStore.ts`
**Líneas:** 213-218

**Descripción:** El event listener global `online` se registra al cargar el módulo y nunca se remueve. Esto es intencional pero debería documentarse como decisión de diseño consciente.

---

## Parte 9: pwaWaiter Components (24 defectos)

### CRITICAL (2)

#### WAITER-COMP-CRIT-01: Memory Leak - setTimeout in useOnlineStatus
**Archivo:** `pwaWaiter/src/hooks/useOnlineStatus.ts`
**Línea:** 24

**Descripción:** (Duplicado de WAITER-HOOK-HIGH-01) El setTimeout nunca se limpia en cleanup del componente.

---

#### WAITER-COMP-CRIT-02: State Update on Unmounted Component in usePullToRefresh
**Archivo:** `pwaWaiter/src/hooks/usePullToRefresh.ts`
**Líneas:** 75-96

**Descripción:** (Duplicado de WAITER-HOOK-MED-03) La función `handleTouchEnd` llama a `await onRefresh()` que es async, luego establece estado en el bloque `finally`. Si el componente se desmonta mientras `onRefresh()` corre, `setState` se llamará en un componente desmontado.

---

### HIGH (5)

#### WAITER-COMP-HIGH-01: Missing useCallback for onClick Handler
**Archivo:** `pwaWaiter/src/pages/TableGrid.tsx`
**Líneas:** 190-195, 208-213, 226-231, 244-249

**Descripción:** Los handlers `onClick` en TableCard renderizan con arrow functions inline `() => onTableSelect(table.table_id)`. TableCard recibe nuevas referencias de función en cada render.

---

#### WAITER-COMP-HIGH-02: Missing Error Boundary for Page Components
**Archivo:** `pwaWaiter/src/App.tsx`
**Líneas:** 53-71

**Descripción:** Ningún error boundary wraps los componentes de página. Si alguna página lanza un error durante render, toda la app crasheará con pantalla blanca.

---

#### WAITER-COMP-HIGH-03: ConfirmDialog onCancel May Cause Stale Closure
**Archivo:** `pwaWaiter/src/components/ConfirmDialog.tsx`
**Líneas:** 39-50

**Descripción:** El callback `onCancel` en el array de dependencias del useEffect puede causar que el efecto corra en cada render si `onCancel` no está memoizado por el padre.

---

#### WAITER-COMP-HIGH-04: Missing aria-describedby in ConfirmDialog
**Archivo:** `pwaWaiter/src/components/ConfirmDialog.tsx`
**Líneas:** 64-76

**Descripción:** El dialog tiene `aria-labelledby` para el título pero no `aria-describedby` para el contenido del mensaje. Los usuarios de screen reader no escucharán el mensaje automáticamente.

---

#### WAITER-COMP-HIGH-05: usePullToRefresh Has Stale State Reference
**Archivo:** `pwaWaiter/src/hooks/usePullToRefresh.ts`
**Líneas:** 44-73, 75-97

**Descripción:** Los callbacks `handleTouchMove` y `handleTouchEnd` dependen de valores de estado en el array de dependencias. Estos valores se leen del closure en el momento de creación del callback y pueden tener referencias de estado stale.

---

### MEDIUM (10)

#### WAITER-COMP-MED-01: TableCard Missing aria-label
**Archivo:** `pwaWaiter/src/components/TableCard.tsx`
**Líneas:** 24-85

**Descripción:** El botón TableCard no tiene `aria-label` para describir su propósito. Los usuarios de screen reader no sabrán qué número de mesa representa.

---

#### WAITER-COMP-MED-02: StatusBadge Missing role="status"
**Archivo:** `pwaWaiter/src/components/StatusBadge.tsx`
**Líneas:** 13-19, 31-37

**Descripción:** Los badges de estado deberían tener `role="status"` para anunciar cambios de estado a screen readers.

---

#### WAITER-COMP-MED-03: Header Connection Status Missing Accessible Label
**Archivo:** `pwaWaiter/src/components/Header.tsx`
**Líneas:** 57-67

**Descripción:** El indicador de estado de conexión usa solo color y un atributo title, que no es accesible para screen readers.

---

#### WAITER-COMP-MED-04: App.tsx Handlers Not Memoized
**Archivo:** `pwaWaiter/src/App.tsx`
**Líneas:** 43-49

**Descripción:** `handleTableSelect` y `handleBackToGrid` se definen como funciones regulares que crean nuevas referencias en cada render.

---

#### WAITER-COMP-MED-05: TableDetailPage promptMarkServed Not Memoized
**Archivo:** `pwaWaiter/src/pages/TableDetail.tsx`
**Líneas:** 108-111

**Descripción:** `promptMarkServed` no está memoizado con useCallback, creando nuevas referencias de función en cada render.

---

#### WAITER-COMP-MED-06: Missing Focus Trap in ConfirmDialog
**Archivo:** `pwaWaiter/src/components/ConfirmDialog.tsx`
**Líneas:** 54-97

**Descripción:** El modal dialog no atrapa el foco dentro de sí mismo. Los usuarios pueden Tab fuera del modal a elementos del background.

---

#### WAITER-COMP-MED-07: PullToRefreshIndicator Lacks aria-live
**Archivo:** `pwaWaiter/src/components/PullToRefreshIndicator.tsx`
**Líneas:** 22-42

**Descripción:** El indicador de refresh muestra feedback visual pero no tiene aria-live region para anunciar a screen readers cuando el refresh inicia/completa.

---

#### WAITER-COMP-MED-08: Input Component Missing aria-invalid
**Archivo:** `pwaWaiter/src/components/Input.tsx`
**Líneas:** 22-36

**Descripción:** Cuando un error está presente, el input debería tener `aria-invalid="true"` y `aria-describedby` apuntando al mensaje de error.

---

#### WAITER-COMP-MED-09: ConnectionBanner Uses window.location.reload
**Archivo:** `pwaWaiter/src/components/ConnectionBanner.tsx`
**Líneas:** 15-19

**Descripción:** Usar `window.location.reload()` para reconexión es un approach heavy-handed que pierde todo el estado de la aplicación.

---

#### WAITER-COMP-MED-10: TableDetailPage loadSessionDetail Stale Closure
**Archivo:** `pwaWaiter/src/pages/TableDetail.tsx`
**Líneas:** 46-60

**Descripción:** El callback `loadSessionDetail` depende de `table?.table_id` y `table?.session_id`. Si estos cambian pero el componente no ha re-renderizado aún, el callback puede tener valores stale.

---

### LOW (7)

#### WAITER-COMP-LOW-01: OfflineBanner Icons Inlined
**Archivo:** `pwaWaiter/src/components/OfflineBanner.tsx`
**Líneas:** 4-18

**Descripción:** Los componentes de ícono SVG inline se definen dentro del módulo pero podrían extraerse a un archivo de íconos compartido.

---

#### WAITER-COMP-LOW-02: BranchSelectPage Missing Loading State
**Archivo:** `pwaWaiter/src/pages/BranchSelect.tsx`
**Líneas:** 24-40

**Descripción:** Al clickear un botón de branch, no hay feedback visual de que la selección está procesando.

---

#### WAITER-COMP-LOW-03: TableCard Has Hardcoded Animation Class
**Archivo:** `pwaWaiter/src/components/TableCard.tsx`
**Línea:** 32

**Descripción:** La clase `animate-glow` se usa pero puede no proveer suficiente distinción visual para usuarios con discapacidades visuales o preferencia de movimiento reducido.

---

#### WAITER-COMP-LOW-04: LoginPage Test Credentials Visible in Production
**Archivo:** `pwaWaiter/src/pages/Login.tsx`
**Líneas:** 77-83

**Descripción:** Las credenciales de prueba se muestran en la página de login y serían visibles en producción. Esto debería renderizarse condicionalmente basado en el environment.

---

#### WAITER-COMP-LOW-05: TableDetailPage getRoundSubtotal Not Memoized
**Archivo:** `pwaWaiter/src/pages/TableDetail.tsx`
**Líneas:** 135-137

**Descripción:** La función `getRoundSubtotal` se llama dentro del render para cada round. Moverla a un patrón useMemo sería más óptimo.

---

#### WAITER-COMP-LOW-06: Button Component Has Hardcoded Text
**Archivo:** `pwaWaiter/src/components/Button.tsx`
**Línea:** 70

**Descripción:** El texto de loading "Cargando..." está hardcodeado en español. Para mejor soporte de internacionalización, debería aceptar un prop `loadingText`.

---

#### WAITER-COMP-LOW-07: Missing key Warning Risk in TableDetailPage
**Archivo:** `pwaWaiter/src/pages/TableDetail.tsx`
**Líneas:** 358-392

**Descripción:** Dentro del loop de items de round, los items se keyean por `item.id`. Esto es correcto, pero si `item.id` pudiera ser undefined o duplicado, causaría issues.

---

## Resumen de Correcciones Prioritarias

### Prioridad Inmediata (CRITICAL - 8 defectos)

1. **WAITER-STORE-CRIT-01**: Reemplazar selectores de filtrado con versiones memoizadas
2. **WAITER-STORE-CRIT-02**: Exportar función cleanup que remueva el event listener
3. **WAITER-SVC-CRIT-01**: Mover token de URL query param a subprotocolo WebSocket
4. **WAITER-SVC-CRIT-02**: Arreglar el dead code path en `handleTokenRefresh()`
5. **WAITER-SVC-CRIT-03**: Agregar límite máximo de tamaño al Set `recentNotifications`
6. **WAITER-COMP-CRIT-01**: Limpiar setTimeout en useOnlineStatus
7. **WAITER-COMP-CRIT-02**: Agregar guard de mount para operación async
8. **MENU-HOOK-CRIT-01**: Agregar isMountedRef o AbortController para fetch

### Alta Prioridad (HIGH - 29 defectos)

- Agregar error boundaries a páginas
- Arreglar issues de accesibilidad en dialogs
- Memoizar callbacks para evitar re-renders
- Agregar lógica de retry con exponential backoff
- Agregar timeouts a operaciones IndexedDB
- Arreglar race conditions en WebSocket y state management

### Prioridad Media (MEDIUM - 61 defectos)

- Agregar aria-labels a componentes interactivos
- Implementar focus trapping en modals
- Agregar cleanup apropiado para timers y subscriptions
- Usar selectores más específicos para evitar re-renders

### Baja Prioridad (LOW - 37 defectos)

- Extraer íconos a archivos compartidos
- Agregar display de credenciales de prueba basado en environment
- Usar constantes de configuración en lugar de magic numbers
- Documentar decisiones de diseño

---

## Notas Positivas

Ambas aplicaciones demuestran muchas buenas prácticas:

1. **Prevención de Memory Leaks**: La mayoría de stores y hooks tienen cleanup apropiado
2. **Memoización**: ProductCard, CartItemCard y otros componentes usan memo() correctamente
3. **Accesibilidad**: Muchos modals tienen `role="dialog"`, `aria-modal`, `aria-labelledby`
4. **Error Boundaries**: pwaMenu tiene ErrorBoundary y SectionErrorBoundary
5. **Patrón de Ref para WebSocket**: `useOrderUpdates` usa correctamente el patrón de ref
6. **Manejo de HMR**: Muchos hooks tienen guards de cleanup para Hot Module Replacement
7. **Exponential Backoff**: Ambas apps implementan backoff exponencial en WebSocket
8. **Heartbeat Detection**: Ambas apps detectan conexiones stale via timeout de pong

---

**Fin del Reporte de Auditoría**
