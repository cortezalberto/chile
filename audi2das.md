# Auditoría de Integración Dashboard-Backend

**Fecha:** Enero 2026
**Autor:** Arquitectura de Software
**Proyecto:** Integrador - Sistema de Gestión de Restaurantes

---

## Resumen Ejecutivo

Este documento presenta un análisis exhaustivo de la integración entre el Dashboard (panel de administración) y el Backend (API REST + WebSocket). Se identifican brechas críticas, inconsistencias de datos, y se propone un plan de refactorización priorizado.

**Estado Actual:**
- 16 stores Zustand en Dashboard
- 8 stores con integración API completa
- 5 stores con datos predefinidos locales (sin API)
- 3 stores sin integración backend (brechas críticas)

---

## I. Matriz de Trazabilidad: Acciones Dashboard → Backend

### 1.1 Stores con Integración Completa ✅

| Store | Acción Frontend | Endpoint Backend | Método | Estado |
|-------|-----------------|------------------|--------|--------|
| **authStore** | `login()` | `/api/auth/login` | POST | ✅ |
| | `checkAuth()` | `/api/auth/me` | GET | ✅ |
| | `logout()` | (local only) | - | ✅ |
| **branchStore** | `fetchBranches()` | `/api/admin/branches` | GET | ✅ |
| | `createBranchAsync()` | `/api/admin/branches` | POST | ✅ |
| | `updateBranchAsync()` | `/api/admin/branches/{id}` | PATCH | ✅ |
| | `deleteBranchAsync()` | `/api/admin/branches/{id}` | DELETE | ✅ |
| **categoryStore** | `fetchCategories()` | `/api/admin/categories?branch_id=X` | GET | ✅ |
| | `createCategoryAsync()` | `/api/admin/categories` | POST | ✅ |
| | `updateCategoryAsync()` | `/api/admin/categories/{id}` | PATCH | ✅ |
| | `deleteCategoryAsync()` | `/api/admin/categories/{id}` | DELETE | ✅ |
| **subcategoryStore** | `fetchSubcategories()` | `/api/admin/subcategories?category_id=X` | GET | ✅ |
| | `createSubcategoryAsync()` | `/api/admin/subcategories` | POST | ✅ |
| | `updateSubcategoryAsync()` | `/api/admin/subcategories/{id}` | PATCH | ✅ |
| | `deleteSubcategoryAsync()` | `/api/admin/subcategories/{id}` | DELETE | ✅ |
| **productStore** | `fetchProducts()` | `/api/admin/products?category_id=X&branch_id=Y` | GET | ✅ |
| | `createProductAsync()` | `/api/admin/products` | POST | ✅ |
| | `updateProductAsync()` | `/api/admin/products/{id}` | PATCH | ✅ |
| | `deleteProductAsync()` | `/api/admin/products/{id}` | DELETE | ✅ |
| **tableStore** | `fetchTables()` | `/api/admin/tables?branch_id=X` | GET | ✅ |
| | `createTableAsync()` | `/api/admin/tables` | POST | ✅ |
| | `updateTableAsync()` | `/api/admin/tables/{id}` | PATCH | ✅ |
| | `deleteTableAsync()` | `/api/admin/tables/{id}` | DELETE | ✅ |
| | `subscribeToTableEvents()` | WebSocket `/ws/waiter` | WS | ✅ |
| **staffStore** | `fetchStaff()` | `/api/admin/staff?branch_id=X` | GET | ✅ |
| | `createStaffAsync()` | `/api/admin/staff` | POST | ✅ |
| | `updateStaffAsync()` | `/api/admin/staff/{id}` | PATCH | ✅ |
| | `deleteStaffAsync()` | `/api/admin/staff/{id}` | DELETE | ✅ |
| **allergenStore** | `fetchAllergens()` | `/api/admin/allergens` | GET | ✅ |
| | `createAllergenAsync()` | `/api/admin/allergens` | POST | ✅ |
| | `updateAllergenAsync()` | `/api/admin/allergens/{id}` | PATCH | ✅ |
| | `deleteAllergenAsync()` | `/api/admin/allergens/{id}` | DELETE | ✅ |

### 1.2 Stores SIN Integración Backend ❌

| Store | Acción Frontend | Endpoint Requerido | Estado | Prioridad |
|-------|-----------------|-------------------|--------|-----------|
| **promotionStore** | `addPromotion()` | `/api/admin/promotions` POST | ❌ FALTA | **CRÍTICA** |
| | `updatePromotion()` | `/api/admin/promotions/{id}` PATCH | ❌ FALTA | **CRÍTICA** |
| | `deletePromotion()` | `/api/admin/promotions/{id}` DELETE | ❌ FALTA | **CRÍTICA** |
| | `getByBranch()` | `/api/admin/promotions?branch_id=X` GET | ❌ FALTA | **CRÍTICA** |
| **restaurantStore** | `updateRestaurant()` | `/api/admin/tenant` PATCH | ⚠️ API existe, no integrada | **ALTA** |
| | `createRestaurant()` | `/api/admin/tenant` POST | ⚠️ API existe, no integrada | **ALTA** |
| **badgeStore** | `addBadge()` | No existe en backend | ❌ FALTA | MEDIA |
| | `updateBadge()` | No existe en backend | ❌ FALTA | MEDIA |
| | `deleteBadge()` | No existe en backend | ❌ FALTA | MEDIA |
| **sealStore** | `addSeal()` | No existe en backend | ❌ FALTA | MEDIA |
| | `updateSeal()` | No existe en backend | ❌ FALTA | MEDIA |
| | `deleteSeal()` | No existe en backend | ❌ FALTA | MEDIA |
| **roleStore** | `addRole()` | No existe en backend | ❌ FALTA | BAJA |
| | `updateRole()` | No existe en backend | ❌ FALTA | BAJA |
| | `deleteRole()` | No existe en backend | ❌ FALTA | BAJA |
| **promotionTypeStore** | `addPromotionType()` | No existe en backend | ❌ FALTA | BAJA |
| | `updatePromotionType()` | No existe en backend | ❌ FALTA | BAJA |
| | `deletePromotionType()` | No existe en backend | ❌ FALTA | BAJA |
| **orderHistoryStore** | Todas las acciones | No existe en backend | ❌ FALTA | BAJA |

---

## II. Brechas Críticas Identificadas

### 2.1 [C001] Promotions Store - Sin Backend

**Severidad:** CRÍTICA
**Ubicación:** `Dashboard/src/stores/promotionStore.ts`

**Problema:**
```typescript
// promotionStore.ts - Solo métodos locales
interface PromotionState {
  addPromotion: (data) => Promotion      // ❌ Solo localStorage
  updatePromotion: (id, data) => void    // ❌ Solo localStorage
  deletePromotion: (id) => void          // ❌ Solo localStorage
  // NO HAY: fetchPromotions, createPromotionAsync, etc.
}
```

**Impacto:**
- Las promociones NO persisten en base de datos
- NO se sincronizan entre usuarios/dispositivos
- Se pierden al limpiar localStorage
- Inconsistencia en sistema multi-tenant

**Solución Requerida:**

**Backend - Crear router de promociones:**
```python
# backend/rest_api/routers/promotions.py (NUEVO)

@router.get("/api/admin/promotions")
async def list_promotions(
    branch_id: Optional[int] = None,
    current_user: User = Depends(get_current_user)
):
    """Lista promociones filtradas por branch_id"""

@router.post("/api/admin/promotions")
async def create_promotion(
    data: PromotionCreate,
    current_user: User = Depends(get_current_admin)
):
    """Crea nueva promoción"""

@router.patch("/api/admin/promotions/{id}")
async def update_promotion(...)

@router.delete("/api/admin/promotions/{id}")
async def delete_promotion(...)
```

**Backend - Modelo SQLAlchemy:**
```python
# backend/rest_api/models.py (AGREGAR)

class Promotion(Base):
    __tablename__ = "promotions"

    id = Column(BigInteger, primary_key=True)
    tenant_id = Column(BigInteger, ForeignKey("tenants.id"), nullable=False)
    name = Column(String(255), nullable=False)
    description = Column(Text)
    price_cents = Column(Integer, nullable=False)
    start_date = Column(Date, nullable=False)
    end_date = Column(Date, nullable=False)
    start_time = Column(Time, default="00:00")
    end_time = Column(Time, default="23:59")
    promotion_type_id = Column(String(50))
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, onupdate=func.now())

class PromotionBranch(Base):
    """Tabla intermedia para M:N promoción-sucursal"""
    __tablename__ = "promotion_branches"

    promotion_id = Column(BigInteger, ForeignKey("promotions.id"), primary_key=True)
    branch_id = Column(BigInteger, ForeignKey("branches.id"), primary_key=True)

class PromotionItem(Base):
    """Items incluidos en la promoción"""
    __tablename__ = "promotion_items"

    id = Column(BigInteger, primary_key=True)
    promotion_id = Column(BigInteger, ForeignKey("promotions.id"), nullable=False)
    product_id = Column(BigInteger, ForeignKey("products.id"), nullable=False)
    quantity = Column(Integer, default=1)
```

**Frontend - Actualizar promotionStore:**
```typescript
// Dashboard/src/stores/promotionStore.ts (ACTUALIZAR)

interface PromotionState {
  promotions: Promotion[]
  isLoading: boolean
  error: string | null

  // Métodos locales existentes (mantener para fallback)
  addPromotion: (data: PromotionFormData) => Promotion
  updatePromotion: (id: string, data: Partial<PromotionFormData>) => void
  deletePromotion: (id: string) => void

  // NUEVOS: Métodos async API
  fetchPromotions: (branchId?: number) => Promise<void>
  createPromotionAsync: (data: PromotionFormData) => Promise<Promotion>
  updatePromotionAsync: (id: string, data: Partial<PromotionFormData>) => Promise<void>
  deletePromotionAsync: (id: string) => Promise<void>
}
```

**API Service:**
```typescript
// Dashboard/src/services/api.ts (AGREGAR)

export const promotionAPI = {
  list: async (branchId?: number): Promise<APIPromotion[]> => {
    const params = branchId ? `?branch_id=${branchId}` : ''
    return apiRequest(`/api/admin/promotions${params}`)
  },

  create: async (data: CreatePromotionRequest): Promise<APIPromotion> => {
    return apiRequest('/api/admin/promotions', {
      method: 'POST',
      body: JSON.stringify(data)
    })
  },

  update: async (id: number, data: UpdatePromotionRequest): Promise<APIPromotion> => {
    return apiRequest(`/api/admin/promotions/${id}`, {
      method: 'PATCH',
      body: JSON.stringify(data)
    })
  },

  delete: async (id: number): Promise<void> => {
    return apiRequest(`/api/admin/promotions/${id}`, { method: 'DELETE' })
  }
}
```

---

### 2.2 [C002] Restaurant Store - API Existe pero No Integrada

**Severidad:** ALTA
**Ubicación:** `Dashboard/src/stores/restaurantStore.ts`

**Problema:**
```typescript
// restaurantStore.ts - Hardcoded mock data
const initialRestaurant: Restaurant = {
  id: 'restaurant-1',
  name: 'Buen Sabor',
  slug: 'buen-sabor',
  // ... datos mock fijos
}

// Solo métodos locales
updateRestaurant: (data) => set(...)  // No llama API
```

**API Backend Existente (NO utilizada):**
```typescript
// api.ts - Ya definido pero no usado
export const tenantAPI = {
  get: async (): Promise<Tenant> => apiRequest('/api/admin/tenant'),
  update: async (data: UpdateTenantRequest): Promise<Tenant> =>
    apiRequest('/api/admin/tenant', { method: 'PATCH', body: JSON.stringify(data) })
}
```

**Solución:**
```typescript
// Dashboard/src/stores/restaurantStore.ts (REFACTORIZAR)

interface RestaurantState {
  restaurant: Restaurant | null
  isLoading: boolean
  error: string | null

  // NUEVOS métodos async
  fetchRestaurant: () => Promise<void>
  updateRestaurantAsync: (data: Partial<Restaurant>) => Promise<void>
}

export const useRestaurantStore = create<RestaurantState>()(
  persist(
    (set, get) => ({
      restaurant: null,  // Iniciar vacío, no mock
      isLoading: false,
      error: null,

      fetchRestaurant: async () => {
        set({ isLoading: true, error: null })
        try {
          const tenant = await tenantAPI.get()
          set({
            restaurant: mapTenantToRestaurant(tenant),
            isLoading: false
          })
        } catch (err) {
          set({ error: err.message, isLoading: false })
        }
      },

      updateRestaurantAsync: async (data) => {
        set({ isLoading: true, error: null })
        try {
          const updated = await tenantAPI.update({
            name: data.name,
            slug: data.slug,
            // ... mapear campos
          })
          set({
            restaurant: mapTenantToRestaurant(updated),
            isLoading: false
          })
        } catch (err) {
          set({ error: err.message, isLoading: false })
          throw err
        }
      }
    }),
    { name: STORAGE_KEYS.RESTAURANT, version: 2 }
  )
)
```

---

### 2.3 [C003] Falta Endpoint staffAPI.get(id)

**Severidad:** MEDIA
**Ubicación:** `Dashboard/src/services/api.ts`

**Problema:**
```typescript
// api.ts - staffAPI no tiene método get individual
export const staffAPI = {
  list: async (branchId?: number) => {...},
  create: async (data) => {...},
  update: async (id, data) => {...},
  delete: async (id) => {...},
  // FALTA: get: async (id: number) => {...}
}
```

**Solución:**
```typescript
// Dashboard/src/services/api.ts (AGREGAR)
export const staffAPI = {
  // ... métodos existentes

  get: async (id: number): Promise<APIStaff> => {
    return apiRequest(`/api/admin/staff/${id}`)
  }
}
```

**Backend:** Verificar que existe `GET /api/admin/staff/{id}` o agregarlo.

---

### 2.4 [C004] Sistema de Badges/Seals/Roles - Solo Local

**Severidad:** MEDIA
**Ubicación:** `Dashboard/src/stores/badgeStore.ts`, `sealStore.ts`, `roleStore.ts`

**Problema:**
Estos stores contienen datos "del sistema" predefinidos que:
- No se sincronizan entre instancias
- No pueden ser personalizados por tenant
- Se resetean con migraciones de versión

**Análisis de Decisión:**

| Opción | Descripción | Pros | Contras |
|--------|-------------|------|---------|
| A) Backend API | CRUD completo en backend | Consistencia multi-tenant | Más desarrollo |
| B) Seed en backend | Datos iniciales en DB, readonly en frontend | Simple, consistente | No editable |
| C) Mantener local | Predefinidos, igual para todos | Ya funciona | Sin personalización |

**Recomendación:** Opción B para MVP, migrar a A si se requiere personalización por tenant.

**Implementación Opción B:**

```python
# backend/rest_api/routers/system.py (NUEVO)

@router.get("/api/system/badges")
async def list_badges():
    """Retorna badges predefinidos del sistema"""
    return [
        {"id": "nuevo", "name": "Nuevo", "color": "#22c55e"},
        {"id": "popular", "name": "Popular", "color": "#f97316"},
        # ...
    ]

@router.get("/api/system/seals")
async def list_seals():
    """Retorna sellos predefinidos del sistema"""

@router.get("/api/system/roles")
async def list_roles():
    """Retorna roles predefinidos del sistema"""
```

---

## III. Inconsistencias de Datos

### 3.1 [D001] Conversión de IDs: String vs Integer

**Problema:** Backend usa `BigInteger`, frontend usa `string (UUID)`

**Patrón Actual (Correcto):**
```typescript
// Todas las conversiones siguen este patrón
function mapAPIToFrontend(api: APIEntity): Entity {
  return {
    id: String(api.id),  // int → string
    // ...
  }
}

// En métodos async
const numericId = parseInt(id, 10)
if (isNaN(numericId)) {
  // Entidad local, usar método sync
  return get().localMethod(id, data)
}
// Entidad de API, llamar endpoint
await api.update(numericId, data)
```

**Estado:** ✅ Implementado correctamente en todos los stores

---

### 3.2 [D002] Conversión de Precios: Cents vs Dollars

**Problema:** Backend almacena en centavos, frontend en dólares

**Patrón Actual:**
```typescript
// productStore.ts
function mapAPIProductToFrontend(api: APIProduct): Product {
  const branchPrices = api.branch_prices.map(bp => ({
    branch_id: String(bp.branch_id),
    price: bp.price_cents / 100,  // cents → dollars
    is_active: bp.is_available
  }))
  // ...
}

// Al enviar a API
const apiBranchPrices = data.branch_prices.map(bp => ({
  branch_id: parseInt(bp.branch_id, 10),
  price_cents: Math.round(bp.price * 100),  // dollars → cents
  is_available: bp.is_active
}))
```

**Estado:** ✅ Implementado correctamente

---

### 3.3 [D003] Status de Mesas: Español vs Inglés

**Problema:** Backend usa estados en inglés, frontend en español

**Mapeo Actual:**
```typescript
// tableStore.ts
const API_STATUS_TO_FRONTEND = {
  'FREE': 'libre',
  'ACTIVE': 'ocupada',
  'PAYING': 'cuenta_solicitada',
  'OUT_OF_SERVICE': 'libre'  // Tratado como libre pero is_active=false
}

const FRONTEND_STATUS_TO_API = {
  'libre': 'FREE',
  'ocupada': 'ACTIVE',
  'solicito_pedido': 'ACTIVE',
  'pedido_cumplido': 'ACTIVE',
  'cuenta_solicitada': 'PAYING'
}
```

**Problema Potencial:** Estados `solicito_pedido` y `pedido_cumplido` del frontend se pierden al mapear a `ACTIVE` en backend.

**Recomendación:**
```python
# Agregar estados granulares en backend
class TableStatus(str, Enum):
    FREE = "FREE"
    OCCUPIED = "OCCUPIED"      # Diner sentado
    ORDERING = "ORDERING"      # Pidiendo
    SERVED = "SERVED"          # Pedido entregado
    PAYING = "PAYING"          # Solicitó cuenta
    OUT_OF_SERVICE = "OUT_OF_SERVICE"
```

---

### 3.4 [D004] Campos Solo-Frontend en Staff

**Problema:** `phone`, `dni`, `hire_date` existen en frontend pero no en modelo backend

**Código Actual:**
```typescript
// staffStore.ts - Preserva campos frontend
function mapAPIStaffToFrontend(api: APIStaff, existing?: Staff): Staff {
  return {
    // ... campos de API
    phone: existing?.phone ?? '',      // ⚠️ Solo frontend
    dni: existing?.dni ?? '',          // ⚠️ Solo frontend
    hire_date: existing?.hire_date ?? '' // ⚠️ Solo frontend
  }
}
```

**Impacto:**
- Datos se pierden si localStorage se limpia
- No se sincronizan entre dispositivos
- Inconsistencia con otros usuarios

**Solución Backend:**
```python
# backend/rest_api/models.py - User model (AGREGAR)
class User(Base):
    # ... campos existentes
    phone = Column(String(50))
    dni = Column(String(20))
    hire_date = Column(Date)
```

---

## IV. Plan de Refactorización

### Fase 1: Críticas (Sprint 1-2)

| ID | Tarea | Esfuerzo | Archivos |
|----|-------|----------|----------|
| C001-BE | Crear modelo Promotion en backend | 4h | `models.py`, `schemas.py` |
| C001-RT | Crear router promotions.py | 6h | `routers/promotions.py` |
| C001-FE | Actualizar promotionStore con async | 4h | `promotionStore.ts`, `api.ts` |
| C001-UI | Actualizar página Promotions | 2h | `Promotions.tsx` |
| C002 | Conectar restaurantStore a tenantAPI | 3h | `restaurantStore.ts` |

**Total Fase 1:** ~19 horas

### Fase 2: Altas (Sprint 3)

| ID | Tarea | Esfuerzo | Archivos |
|----|-------|----------|----------|
| C003 | Agregar staffAPI.get() | 1h | `api.ts` |
| D003 | Expandir TableStatus en backend | 3h | `models.py`, mapeos |
| D004 | Agregar phone/dni/hire_date a User | 2h | `models.py`, `staff.py` |

**Total Fase 2:** ~6 horas

### Fase 3: Medias (Sprint 4)

| ID | Tarea | Esfuerzo | Archivos |
|----|-------|----------|----------|
| C004-A | Crear endpoint /api/system/badges | 2h | `routers/system.py` |
| C004-B | Crear endpoint /api/system/seals | 2h | `routers/system.py` |
| C004-C | Crear endpoint /api/system/roles | 2h | `routers/system.py` |
| C004-FE | Actualizar stores para fetch inicial | 3h | `badgeStore.ts`, etc. |

**Total Fase 3:** ~9 horas

### Fase 4: Bajas (Backlog)

| ID | Tarea | Esfuerzo |
|----|-------|----------|
| L001 | Backend para promotionTypes | 4h |
| L002 | Backend para orderHistory | 8h |
| L003 | CRUD completo badges/seals/roles | 12h |

---

## V. Trazabilidad de Eventos WebSocket

### 5.1 Eventos Actualmente Manejados

| Evento | tableStore | Acción |
|--------|------------|--------|
| `TABLE_CLEARED` | ✅ | Status → `libre`, reset times |
| `TABLE_STATUS_CHANGED` | ✅ | Refetch table from API |
| `ROUND_SUBMITTED` | ✅ | Status `ocupada` → `solicito_pedido` |
| `ROUND_SERVED` | ✅ | Status `solicito_pedido` → `pedido_cumplido` |
| `CHECK_REQUESTED` | ✅ | Status → `cuenta_solicitada` |
| `CHECK_PAID` | ✅ | Mantiene `cuenta_solicitada` |

### 5.2 Eventos NO Manejados (Oportunidades)

| Evento | Store Sugerido | Acción Propuesta |
|--------|----------------|------------------|
| `SERVICE_CALL_CREATED` | Nuevo: serviceCallStore | Mostrar notificación en Dashboard |
| `PAYMENT_APPROVED` | tableStore/orderStore | Actualizar totales en tiempo real |
| `TABLE_SESSION_STARTED` | tableStore | Cambiar status `libre` → `ocupada` |

---

## VI. Validación y Consistencia

### 6.1 Validadores Frontend vs Backend

| Entidad | Frontend (`validation.ts`) | Backend (Pydantic) | Consistencia |
|---------|---------------------------|-------------------|--------------|
| Branch | ✅ `validateBranch()` | ✅ `BranchCreate` | ✅ Alineados |
| Category | ✅ `validateCategory()` | ✅ `CategoryCreate` | ✅ Alineados |
| Product | ✅ `validateProduct()` | ✅ `ProductCreate` | ✅ Alineados |
| Staff | ✅ `validateStaff()` | ✅ `UserCreate` | ⚠️ Campos extra FE |
| Table | ✅ `validateTable()` | ✅ `TableCreate` | ✅ Alineados |
| Promotion | ✅ `validatePromotion()` | ❌ No existe | ❌ Falta backend |

### 6.2 Duplicados y Unicidad

| Entidad | Campo Único | Validación FE | Validación BE |
|---------|-------------|---------------|---------------|
| Branch | `slug` por tenant | ✅ | ✅ DB constraint |
| Category | `name` por branch | ✅ | ✅ DB constraint |
| Subcategory | `name` por category | ✅ | ✅ DB constraint |
| Product | `name` por subcategory | ✅ | ✅ DB constraint |
| Table | `code` por branch | ✅ | ✅ DB constraint |
| Staff | `email` global | ✅ | ✅ DB constraint |
| Staff | `dni` por tenant | ✅ | ❌ Falta en BE |

---

## VII. Recomendaciones de Arquitectura

### 7.1 Patrón de Store Híbrido (Adoptar en todos)

```typescript
interface EntityState {
  items: Entity[]
  isLoading: boolean
  error: string | null

  // Acciones locales (fallback/offline)
  addItem: (data: FormData) => Entity
  updateItem: (id: string, data: Partial<FormData>) => void
  deleteItem: (id: string) => void

  // Acciones async (primarias)
  fetchItems: (filters?: Filters) => Promise<void>
  createItemAsync: (data: FormData) => Promise<Entity>
  updateItemAsync: (id: string, data: Partial<FormData>) => Promise<void>
  deleteItemAsync: (id: string) => Promise<void>
}
```

### 7.2 Flujo de Datos Recomendado

```
┌─────────────────────────────────────────────────────────────┐
│                      DASHBOARD                               │
├─────────────────────────────────────────────────────────────┤
│  Página (React)                                             │
│     │                                                        │
│     ▼                                                        │
│  Store (Zustand) ──────────────────────┐                    │
│     │                                   │                    │
│     │ isLoading=true                    │ Optimistic update  │
│     ▼                                   ▼                    │
│  API Service ─────────► Backend ◄───── localStorage         │
│     │                      │                                 │
│     │                      ▼                                 │
│     │               PostgreSQL                               │
│     │                      │                                 │
│     │                      ▼                                 │
│     │               Redis pub/sub                            │
│     │                      │                                 │
│     ▼                      ▼                                 │
│  Response ◄─────────── WebSocket                            │
│     │                                                        │
│     ▼                                                        │
│  Store update (isLoading=false)                             │
│     │                                                        │
│     ▼                                                        │
│  UI re-render                                                │
└─────────────────────────────────────────────────────────────┘
```

### 7.3 Manejo de Errores Estandarizado

```typescript
// Patrón recomendado para todos los stores
createItemAsync: async (data) => {
  set({ isLoading: true, error: null })

  try {
    // Validación local primero
    const validation = validateItem(data)
    if (!validation.isValid) {
      throw new Error(validation.errors.join(', '))
    }

    // Intento API
    const numericId = parseInt(data.related_id, 10)
    if (isNaN(numericId)) {
      // Entidad relacionada es local, usar fallback
      const newItem = get().addItem(data)
      set({ isLoading: false })
      return newItem
    }

    // Llamada API
    const apiItem = await itemAPI.create(mapToAPI(data))
    const newItem = mapFromAPI(apiItem)

    set((state) => ({
      items: [...state.items, newItem],
      isLoading: false
    }))

    return newItem

  } catch (err) {
    const message = err instanceof Error
      ? err.message
      : 'Error desconocido'

    set({ error: message, isLoading: false })

    // Re-throw para que UI pueda manejar
    throw err
  }
}
```

---

## VIII. Checklist de Implementación

### Pre-requisitos
- [ ] Revisar esquema de base de datos actual
- [ ] Verificar migraciones Alembic pendientes
- [ ] Backup de datos de producción (si aplica)

### Fase 1: Promotions
- [ ] Crear modelo `Promotion`, `PromotionBranch`, `PromotionItem`
- [ ] Crear migración Alembic
- [ ] Crear schemas Pydantic
- [ ] Crear router `/api/admin/promotions`
- [ ] Agregar tests backend
- [ ] Agregar `promotionAPI` en `api.ts`
- [ ] Refactorizar `promotionStore.ts`
- [ ] Actualizar `Promotions.tsx`
- [ ] Agregar tests frontend

### Fase 2: Restaurant/Tenant
- [ ] Verificar endpoint `/api/admin/tenant` funciona
- [ ] Refactorizar `restaurantStore.ts`
- [ ] Actualizar `Restaurant.tsx`

### Fase 3: Staff Fields
- [ ] Agregar campos a modelo `User`
- [ ] Crear migración
- [ ] Actualizar schemas
- [ ] Actualizar mapeos en `staffStore.ts`

### Fase 4: System Data
- [ ] Crear `/api/system/*` endpoints
- [ ] Actualizar stores para fetch inicial

---

## IX. Métricas de Éxito

| Métrica | Actual | Objetivo |
|---------|--------|----------|
| Stores con API completa | 8/16 (50%) | 14/16 (87.5%) |
| Endpoints no utilizados | 2 (tenant) | 0 |
| Campos solo-frontend | 3 (staff) | 0 |
| Cobertura tests backend | ? | >80% |
| Cobertura tests frontend | 100 tests | +20 tests |

---

## X. Referencias

- **Dashboard stores:** `Dashboard/src/stores/*.ts`
- **API service:** `Dashboard/src/services/api.ts`
- **Validation:** `Dashboard/src/utils/validation.ts`
- **Backend routers:** `backend/rest_api/routers/*.py`
- **Backend models:** `backend/rest_api/models.py`
- **WebSocket events:** `backend/ws_gateway/`

---

## XI. Registro de Ejecución

### Fase 1 - Completada ✅ (Enero 2026)

**C001: Promotions Backend Integration**
- [x] Crear modelos `Promotion`, `PromotionBranch`, `PromotionItem` en `backend/rest_api/models.py`
- [x] Crear router `backend/rest_api/routers/promotions.py` con CRUD completo
- [x] Registrar router en `backend/rest_api/main.py`
- [x] Agregar `promotionAPI` en `Dashboard/src/services/api.ts`
- [x] Actualizar `promotionStore.ts` con métodos async (`fetchPromotions`, `createPromotionAsync`, etc.)

**C002: Restaurant Store - tenantAPI Integration**
- [x] Actualizar `restaurantStore.ts` para usar `tenantAPI.get()` y `tenantAPI.update()`
- [x] Eliminar mock data hardcodeado
- [x] Agregar métodos `fetchRestaurant()` y `updateRestaurantAsync()`
- [x] Bump `STORE_VERSIONS.RESTAURANT` a v2 en `constants.ts`

**C003: Staff API.get()**
- [x] Agregar endpoint `GET /api/admin/staff/{staff_id}` en `backend/rest_api/routers/admin.py`
- [x] Agregar `staffAPI.get(id)` en `Dashboard/src/services/api.ts`

**D004: Staff Fields (phone/dni/hire_date)**
- [x] Agregar campos `phone`, `dni`, `hire_date` al modelo `User` en `backend/rest_api/models.py`
- [x] Actualizar schemas `StaffOutput`, `StaffCreate`, `StaffUpdate` en `admin.py`
- [x] Actualizar `_build_staff_output()` y `create_staff()` para incluir nuevos campos
- [x] Actualizar `Staff`, `StaffCreate`, `StaffUpdate` interfaces en `api.ts`
- [x] Actualizar `staffStore.ts`: `mapAPIStaffToFrontend()`, `createStaffAsync()`, `updateStaffAsync()`

**Build Status:** Dashboard compila sin errores (100 tests + PWA build)

---

*Documento generado: Enero 2026*
*Última actualización: Enero 2026 - Fase 1 completada*
