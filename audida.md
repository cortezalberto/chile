# Auditoría Exhaustiva del Dashboard - 4 Sucursales

**Fecha**: Enero 2026
**Versión**: 1.1 (CORREGIDA)
**Proyecto**: Dashboard - Panel de Administración Multi-Sucursal

---

## Estado de Correcciones

| Código | Problema | Estado |
|--------|----------|--------|
| C001 | selectUserBranchIds sin referencia estable | ✅ CORREGIDO |
| C002 | Staff multi-rol perdido en mapeo | ✅ CORREGIDO |
| C003 | Cascade preview usa product_ids en vez de items | ✅ CORREGIDO |
| C004 | WebSocket no filtra por sucursal | ✅ CORREGIDO |
| A004 | Estados de tabla español vs inglés | ✅ CORREGIDO |
| A005 | Cascade delete sin transacciones | ✅ CORREGIDO |
| A006 | Sin throttle en WebSocket | ✅ CORREGIDO |
| L001 | Animaciones CSS faltantes | ✅ YA EXISTÍA |

**Build**: ✅ Exitoso
**Tests**: ✅ 100/100 pasaron

---

## Resumen Ejecutivo

Se realizó una auditoría exhaustiva del Dashboard para un escenario de 4 sucursales (Centro, Norte, Sur, Este). Se identificaron **21 problemas** clasificados en 4 categorías: Críticos (C), Arquitectura (A), Mejoras (M) y Leves (L).

### Distribución de Problemas

| Categoría | Cantidad | Descripción |
|-----------|----------|-------------|
| Críticos (C) | 4 | Errores que afectan funcionalidad core |
| Arquitectura (A) | 6 | Problemas de diseño y patrones |
| Mejoras (M) | 7 | Funcionalidades incompletas |
| Leves (L) | 4 | UX/UI y detalles menores |

---

## Problemas Críticos (C)

### C001: Selector de `selectUserBranchIds` sin referencia estable

**Archivo**: `Dashboard/src/stores/authStore.ts:118`

**Problema**: El selector `selectUserBranchIds` devuelve un array vacío inline que crea una nueva referencia en cada render:

```typescript
export const selectUserBranchIds = (state: AuthState) => state.user?.branch_ids ?? []
```

**Impacto**: En React 19 con el nuevo comportamiento de `useSyncExternalStore`, esto puede causar loops infinitos de re-render en componentes que usen este selector.

**Solución**:
```typescript
const EMPTY_BRANCH_IDS: number[] = []
export const selectUserBranchIds = (state: AuthState) => state.user?.branch_ids ?? EMPTY_BRANCH_IDS
```

---

### C002: Staff no sincronizado entre API y estado local

**Archivo**: `Dashboard/src/stores/staffStore.ts:167-187`

**Problema**: La función `mapAPIStaffToFrontend` pierde información al mapear desde el backend:
- `phone`, `dni`, `hire_date` se pierden (no están en la API)
- Solo se toma el primer `branch_role`, descartando asignaciones múltiples

```typescript
function mapAPIStaffToFrontend(apiStaff: APIStaff): Staff {
  const primaryRole = apiStaff.branch_roles[0] // PROBLEMA: Ignora roles adicionales
  return {
    // ...
    phone: '', // PROBLEMA: Se pierde dato local
    dni: '',   // PROBLEMA: Se pierde dato local
  }
}
```

**Impacto**: Un empleado con roles en múltiples sucursales solo se mostrará en una. Datos locales se sobrescriben al refrescar.

**Solución**:
1. Almacenar `branch_roles[]` completo en el frontend
2. Persistir campos locales (`phone`, `dni`, `hire_date`) por separado

---

### C003: Promociones usan `product_ids` pero debería ser `items[]`

**Archivo**: `Dashboard/src/services/cascadeService.ts:497-499`

**Problema**: El servicio de cascade preview busca productos afectados usando `promo.product_ids`:

```typescript
const affectedPromotions = promotionStore.promotions.filter((promo) =>
  promo.product_ids.some((pid) => productIds.has(pid))  // ERROR: product_ids no existe
)
```

**Pero la estructura de Promotion usa `items[]`**:
```typescript
interface Promotion {
  items: { product_id: string; quantity: number }[]  // Estructura correcta
  // product_ids NO existe
}
```

**Impacto**: La preview de cascade delete no funciona para categorías y subcategorías.

**Solución**:
```typescript
const affectedPromotions = promotionStore.promotions.filter((promo) =>
  promo.items.some((item) => productIds.has(item.product_id))
)
```

---

### C004: WebSocket no filtra por sucursal

**Archivo**: `Dashboard/src/services/websocket.ts`

**Problema**: El WebSocket recibe eventos de TODAS las sucursales pero no hay filtro por `branch_id`:

```typescript
this.ws.onmessage = (event) => {
  const data = JSON.parse(event.data)
  this.notifyListeners(data as WSEvent)  // Notifica sin filtrar
}
```

**Impacto**: Un Dashboard filtrado para ver solo "Sucursal Norte" recibirá actualizaciones de todas las sucursales, causando confusión y posible inconsistencia visual.

**Solución**: Agregar método de filtro por sucursal:
```typescript
onFiltered(branchId: number, eventType: WSEventType, callback: EventCallback): () => void {
  return this.on(eventType, (event) => {
    if (event.branch_id === branchId) callback(event)
  })
}
```

---

## Problemas de Arquitectura (A)

### A001: Datos mock hardcodeados en stores

**Archivos**:
- `branchStore.ts:27-67`
- `categoryStore.ts:41-112`
- `productStore.ts:68-247`
- `staffStore.ts:25-148`
- `promotionStore.ts:26-65`

**Problema**: Los stores inicializan con datos mock hardcodeados que mezclan IDs de formato `branch-1` con IDs numéricos del backend:

```typescript
const initialBranches: Branch[] = [
  { id: 'branch-1', name: 'Buen Sabor Centro', ... },  // ID string local
]
```

Pero el backend devuelve:
```typescript
{ id: 1, name: 'Buen Sabor Centro', ... }  // ID numérico
```

**Impacto**:
- Inconsistencia de IDs entre localStorage y backend
- Al cambiar entre modo desarrollo/producción, los datos se corrompen
- Relaciones entre entidades (category_id, branch_id) pueden romperse

**Solución**:
1. Separar datos mock en archivo `mockData.ts`
2. Flag `USE_MOCK_DATA` en env
3. IDs mock con prefijo claro (`mock-branch-1`)

---

### A002: Migración de versión potencialmente destructiva

**Archivo**: `Dashboard/src/stores/promotionStore.ts:159-166`

**Problema**: La migración de versión 3 puede duplicar promociones:

```typescript
if (version < 3) {
  const existingIds = new Set(promotions.map(p => p.id))
  const missingPromotions = initialPromotions.filter(p => !existingIds.has(p.id))
  promotions = [...promotions, ...missingPromotions]  // Puede duplicar si IDs cambiaron
}
```

**Impacto**: Si el usuario editó una promoción inicial cambiando su ID, se agregará una duplicada.

**Solución**: Usar `name` + `promotion_type_id` como clave de deduplicación adicional.

---

### A003: Falta validación de integridad referencial

**Problema**: Al crear productos/subcategorías no se valida que `category_id` exista:

```typescript
// productStore.ts - addProduct
addProduct: (data) => {
  const newProduct: Product = {
    ...data,
    category_id: data.category_id,  // No valida si existe
  }
}
```

**Impacto**: Posible creación de productos "huérfanos" con categoría inexistente.

**Solución**: Agregar validación en stores:
```typescript
addProduct: (data) => {
  const categoryExists = useCategoryStore.getState().categories.some(c => c.id === data.category_id)
  if (!categoryExists) throw new Error('Categoría no encontrada')
  // ...
}
```

---

### A004: tableStore.ts usa status en español pero API usa inglés

**Archivo**: `Dashboard/src/stores/tableStore.ts` vs `Dashboard/src/services/api.ts:325`

**Problema**: El frontend usa estados en español:
```typescript
type TableStatus = 'libre' | 'ocupada' | 'solicito_pedido' | 'pedido_cumplido' | 'cuenta_solicitada'
```

Pero la API usa estados en inglés:
```typescript
status: 'FREE' | 'ACTIVE' | 'PAYING' | 'OUT_OF_SERVICE'
```

**Impacto**: Al sincronizar con backend, el estado se sobrescribe incorrectamente.

**Solución**: Crear mapper bidireccional:
```typescript
const statusMap = {
  FREE: 'libre',
  ACTIVE: 'ocupada',
  PAYING: 'cuenta_solicitada',
  // ...
}
```

---

### A005: Cascade delete no usa transacciones

**Archivo**: `Dashboard/src/services/cascadeService.ts`

**Problema**: Las operaciones de cascade delete ejecutan múltiples acciones sin garantía de atomicidad:

```typescript
export function cascadeDeleteBranch(branchId, stores) {
  // 1. promotionStore.removeProductFromPromotions
  // 2. productStore.deleteByCategories
  // 3. subcategoryStore.deleteByCategories
  // ... (9 operaciones independientes)
}
```

**Impacto**: Si falla en el paso 5, los pasos 1-4 ya se ejecutaron dejando datos inconsistentes.

**Solución**: Implementar patrón transaccional:
```typescript
function cascadeDeleteBranch(branchId, stores) {
  const snapshot = captureSnapshot(stores)
  try {
    // operaciones...
  } catch (error) {
    restoreSnapshot(stores, snapshot)
    throw error
  }
}
```

---

### A006: No hay throttle en actualizaciones WebSocket

**Archivo**: `Dashboard/src/services/websocket.ts`

**Problema**: Cada evento WebSocket dispara actualizaciones inmediatas sin throttle:

```typescript
this.ws.onmessage = (event) => {
  this.notifyListeners(data as WSEvent)  // Cada mensaje = re-render
}
```

**Impacto**: En horario pico con muchos pedidos, puede haber miles de re-renders por minuto causando lag.

**Solución**: Agregar debounce/throttle por tipo de evento:
```typescript
const throttledNotify = throttle(this.notifyListeners, 100)
```

---

## Mejoras (M)

### M001: Falta indicador de sincronización con backend

**Problema**: No hay forma visual de saber si los datos están sincronizados con el backend o son locales.

**Solución**: Agregar badge "Sincronizado" / "Pendiente" en header.

---

### M002: Filtros no persisten entre navegación

**Archivos**: `Products.tsx`, `Tables.tsx`, `Promotions.tsx`

**Problema**: Al cambiar de página y volver, los filtros se resetean.

**Solución**: Persistir filtros en URL (query params) o sessionStorage.

---

### M003: Paginación no muestra total real con filtros

**Archivo**: Todas las páginas con `usePagination`

**Problema**: El contador muestra items filtrados pero no el total global:
```
"14 de 14 productos" (cuando hay 24 en total)
```

**Solución**: Mostrar "14 resultados (24 totales)".

---

### M004: Falta bulk actions para eliminar/editar múltiples items

**Problema**: Para eliminar 10 productos hay que hacer 10 clicks individuales.

**Solución**: Agregar checkboxes de selección múltiple con acciones bulk.

---

### M005: Promociones no validan que productos existan en sucursales seleccionadas

**Archivo**: `Dashboard/src/pages/Promotions.tsx`

**Problema**: Se puede crear promoción para "Sucursal Norte" con productos que solo existen en "Sucursal Centro".

**Solución**: Filtrar `ProductSelect` por sucursales seleccionadas en `branch_ids`.

---

### M006: No hay exportación de datos

**Problema**: No se puede exportar lista de productos, staff, mesas a CSV/Excel.

**Solución**: Agregar botón "Exportar" usando la utilidad `exportCsv.ts` existente.

---

### M007: Falta búsqueda global

**Problema**: Para encontrar un producto hay que navegar a Productos y usar filtros.

**Solución**: Agregar barra de búsqueda global en header (Cmd+K).

---

## Problemas Leves (L)

### L001: Animaciones pulse en Tables.tsx no tienen CSS definido

**Archivo**: `Dashboard/src/pages/Tables.tsx:117-120`

**Problema**: Se referencian clases CSS que no existen:
```typescript
const pulseClass = table.status === 'solicito_pedido'
  ? 'animate-pulse-warning'   // No existe en tailwind.config.js
  : table.status === 'cuenta_solicitada'
  ? 'animate-pulse-urgent'    // No existe en tailwind.config.js
  : ''
```

**Solución**: Agregar animaciones en `tailwind.config.js`:
```javascript
animation: {
  'pulse-warning': 'pulse 2s ease-in-out infinite',
  'pulse-urgent': 'pulse 1s ease-in-out infinite',
}
```

---

### L002: Tooltips sin aria-describedby

**Problema**: Algunos elementos con tooltip no tienen accesibilidad completa:
```typescript
<span title="Información adicional">...</span>  // Sin aria
```

**Solución**: Usar componente Tooltip con aria-describedby.

---

### L003: Formato de precio inconsistente

**Archivos**: Varios

**Problema**: Algunos lugares usan `$125.50`, otros `125,50 $`, otros `$125`.

**Solución**: Usar exclusivamente `formatPrice()` de constants.ts.

---

### L004: Branch selector en Dashboard no muestra sucursal activa

**Problema**: Al seleccionar sucursal desde Dashboard, no hay indicador visual de cuál está activa en el sidebar.

**Solución**: Agregar badge o highlight en item de sidebar correspondiente.

---

## Trazas de Ejemplo - 4 Sucursales

### Escenario 1: Crear producto en Sucursal Norte

```
1. Usuario selecciona "Buen Sabor Norte" en Dashboard
2. Navega a Productos → Click "Nuevo Producto"
3. PROBLEMA (M005): Lista de categorías muestra TODAS las categorías de TODAS las sucursales
   - Esperado: Solo categorías de "Norte" (Comidas, Bebidas)
   - Actual: Muestra 12 categorías de las 4 sucursales
4. Usuario selecciona categoría de Sucursal Centro
5. PROBLEMA: Producto se guarda asociado a categoría incorrecta
```

### Escenario 2: Eliminar Sucursal Centro con productos

```
1. Usuario va a Sucursales → Click eliminar "Buen Sabor Centro"
2. Modal de confirmación muestra preview de cascade
3. PROBLEMA (C003): Preview no muestra promociones afectadas
   - Esperado: "2 promociones serán eliminadas"
   - Actual: "0 promociones" (bug en búsqueda por product_ids)
4. Usuario confirma eliminación
5. Cascade ejecuta correctamente pero si falla a mitad...
6. PROBLEMA (A005): Datos quedan parcialmente eliminados
```

### Escenario 3: Staff con múltiples roles

```
1. Admin crea empleado "Juan" con rol WAITER en Norte
2. Admin añade rol KITCHEN en Centro desde backend directamente
3. Usuario refresca Dashboard
4. PROBLEMA (C002): Juan solo aparece en una sucursal
   - Backend tiene: branch_roles: [{Norte, WAITER}, {Centro, KITCHEN}]
   - Frontend muestra: Solo {Norte, WAITER}
5. Al editar Juan, solo se muestra primer rol
```

### Escenario 4: Actualizaciones real-time entre sucursales

```
1. Usuario A ve Dashboard filtrado por "Sucursal Norte"
2. Usuario B hace pedido en "Sucursal Sur"
3. WebSocket envía ROUND_SUBMITTED con branch_id: 3 (Sur)
4. PROBLEMA (C004): Dashboard de usuario A se actualiza
   - Contador de pedidos incrementa aunque está viendo Norte
   - Toast muestra "Nuevo pedido" aunque no es de su sucursal
5. Confusión del usuario sobre origen del pedido
```

### Escenario 5: Promoción multi-sucursal

```
1. Usuario crea promoción "Combo Familiar" para Centro y Norte
2. Agrega producto "Hamburguesa Clásica" (solo existe en Centro)
3. PROBLEMA (M005): No hay validación
4. Promoción se guarda correctamente
5. Al mostrar en pwaMenu de Norte:
   - Promoción aparece pero producto no existe
   - Error al intentar agregarlo al carrito
```

---

## Plan de Corrección Priorizado

### Fase 1: Críticos (Inmediato)
1. **C001**: Agregar referencia estable a selectUserBranchIds (30 min)
2. **C003**: Corregir búsqueda de promociones afectadas (1h)
3. **C004**: Agregar filtro de branch_id en WebSocket (2h)
4. **C002**: Rediseñar mapeo de staff multi-rol (4h)

### Fase 2: Arquitectura (Corto plazo)
1. **A004**: Crear mapper de estados tabla API↔Frontend (2h)
2. **A001**: Separar datos mock en archivo dedicado (3h)
3. **A003**: Agregar validación de integridad referencial (3h)
4. **A006**: Implementar throttle en WebSocket (2h)

### Fase 3: Mejoras (Mediano plazo)
1. **M005**: Validar productos vs sucursales en promociones (2h)
2. **M002**: Persistir filtros en URL (3h)
3. **M006**: Agregar exportación CSV (2h)
4. **M001**, **M003**, **M004**, **M007**: Mejoras UX (8h total)

### Fase 4: Leves (Bajo prioridad)
1. **L001**: Agregar animaciones CSS (30 min)
2. **L002**, **L003**, **L004**: Consistencia UI (2h total)

---

## Métricas de Cobertura

| Área | Archivos Revisados | Tests Existentes | Cobertura |
|------|-------------------|------------------|-----------|
| Stores | 16/16 | 94 tests | ~85% |
| Pages | 23/23 | 0 tests | 0% |
| Services | 3/3 | 0 tests | 0% |
| Hooks | 13/13 | 0 tests | 0% |

**Recomendación**: Agregar tests de integración para páginas críticas (Products, Promotions, Tables).

---

## Conclusión

El Dashboard está funcionalmente completo pero presenta problemas de sincronización multi-sucursal que deben corregirse antes de producción. Los problemas críticos C001-C004 pueden causar comportamiento incorrecto visible al usuario. Se recomienda abordar la Fase 1 de correcciones antes del próximo release.
