# Auditoría de Aislamiento de Tenant (Multi-Tenancy)

**Fecha:** Enero 2026
**Auditor:** Senior QA
**Alcance:** Backend REST API, WebSocket Gateway, Dashboard, pwaWaiter, pwaMenu

---

## Resumen Ejecutivo

Se realizó un análisis exhaustivo del aislamiento de tenant en todas las aplicaciones del sistema. El proyecto implementa un modelo multi-tenant donde cada restaurante (`Tenant`) tiene sus propias sucursales (`Branch`), usuarios, productos, mesas, etc.

### Resultado General: ✅ **ARQUITECTURA SEGURA** (con mejoras menores sugeridas)

El sistema implementa correctamente el aislamiento de tenant a través de:
1. **JWT con tenant_id embebido** - Cada token contiene el `tenant_id` del usuario
2. **Validación en Backend** - Todos los endpoints filtran por `tenant_id` del JWT
3. **Table Token con tenant_id** - Los tokens de mesa incluyen `tenant_id`, `branch_id`, `session_id`
4. **WebSocket con autenticación** - Validación de JWT/Table Token antes de aceptar conexiones

---

## Análisis por Componente

### 1. Backend REST API ✅ SEGURO

#### 1.1 Autenticación (`shared/auth.py`)

**Patrón Correcto Implementado:**
```python
def verify_jwt(token: str) -> dict:
    # Valida: iss, aud, exp, token blacklist
    # Retorna: sub, tenant_id, branch_ids, roles, email

def current_user_context():
    # Dependency que extrae y valida el JWT
    # Retorna contexto con tenant_id garantizado
```

**Validación de Claims:**
- ✅ `tenant_id` es validado como campo requerido (línea 140-144)
- ✅ `sub` (user_id) validado como entero (línea 155-161)
- ✅ Token blacklist verificado (línea 170-173)

#### 1.2 Router Admin (`routers/admin.py`)

**Todos los endpoints filtran por tenant_id:**

```python
# Ejemplo: list_branches (línea 758)
query = select(Branch).where(Branch.tenant_id == user["tenant_id"])

# Ejemplo: get_branch (línea 774-778)
branch = db.scalar(
    select(Branch).where(
        Branch.id == branch_id,
        Branch.tenant_id == user["tenant_id"],  # ✅ Filtro tenant
        Branch.is_active == True,
    )
)

# Ejemplo: create_branch (línea 802-803)
branch = Branch(
    tenant_id=user["tenant_id"],  # ✅ Asigna tenant del usuario
    **body.model_dump(),
)
```

**Endpoints Auditados (TODOS CORRECTOS):**
- ✅ `/api/admin/tenant` - Filtra por `user["tenant_id"]`
- ✅ `/api/admin/branches` - Filtra por `user["tenant_id"]`
- ✅ `/api/admin/categories` - Filtra vía branch que pertenece al tenant
- ✅ `/api/admin/subcategories` - Filtra vía category/branch
- ✅ `/api/admin/products` - Filtra vía category que pertenece al tenant
- ✅ `/api/admin/allergens` - Filtra por `user["tenant_id"]`
- ✅ `/api/admin/tables` - Filtra vía branch que pertenece al tenant
- ✅ `/api/admin/staff` - Filtra por `user["tenant_id"]`
- ✅ `/api/admin/promotions` - Filtra por `user["tenant_id"]`
- ✅ `/api/admin/sectors` - Filtra por `user["tenant_id"]`
- ✅ `/api/admin/assignments` - Filtra por `user["tenant_id"]`
- ✅ `/api/admin/exclusions` - Filtra vía branch que pertenece al tenant

#### 1.3 Router Diner (`routers/diner.py`)

**Aislamiento via Table Token:**
```python
@router.post("/register")
def register_diner(
    table_ctx: dict[str, int] = Depends(current_table_context),
):
    tenant_id = table_ctx["tenant_id"]  # ✅ Extraído del token
    branch_id = table_ctx["branch_id"]
    session_id = table_ctx["session_id"]

    new_diner = Diner(
        tenant_id=tenant_id,  # ✅ Asignado del token
        branch_id=branch_id,
        session_id=session_id,
        ...
    )
```

**Validación de Sesión:**
```python
# Los diners solo pueden interactuar con SU sesión
if table_ctx["session_id"] != session_id:
    raise HTTPException(status_code=403, detail="Session does not match token")
```

#### 1.4 Router Billing (`routers/billing.py`)

**Aislamiento Correcto:**
```python
# request_check - usa table_ctx para tenant_id
tenant_id = table_ctx["tenant_id"]
check = Check(
    tenant_id=tenant_id,  # ✅ Desde token
    branch_id=branch_id,
    ...
)

# record_cash_payment - valida acceso a branch
branch_ids = ctx.get("branch_ids", [])
if check.branch_id not in branch_ids:
    raise HTTPException(status_code=403, detail="No access to this branch")
```

#### 1.5 Router Kitchen (`routers/kitchen.py`)

**Filtrado por Branch (Indirecto por Tenant):**
```python
def get_pending_rounds():
    branch_ids = ctx.get("branch_ids", [])  # Branches del usuario
    rounds = db.execute(
        select(Round).where(
            Round.branch_id.in_(branch_ids),  # ✅ Solo rounds de sus branches
            Round.status.in_(["SUBMITTED", "IN_KITCHEN"]),
        )
    )
```

**Validación de Acceso:**
```python
# Antes de actualizar round
branch_ids = ctx.get("branch_ids", [])
if round_obj.branch_id not in branch_ids:
    raise HTTPException(status_code=403, detail="No access to this branch")
```

#### 1.6 Router Catalog (Público) (`routers/catalog.py`)

**Endpoint Público con Aislamiento Natural:**
```python
@router.get("/menu/{branch_slug}")
def get_menu(branch_slug: str):
    # Busca branch por slug - naturalmente aislado
    branch = db.scalar(
        select(Branch).where(
            Branch.slug == branch_slug,  # Slug único por tenant
            Branch.is_active == True,
        )
    )
    # Todos los productos son filtrados por branch.id
```

⚠️ **Nota:** Los endpoints públicos (`/api/public/*`) no requieren autenticación pero están naturalmente aislados porque:
- El `branch_slug` es único por tenant
- Todas las queries filtran por `branch_id`
- No se exponen datos de otros tenants

---

### 2. WebSocket Gateway ✅ SEGURO

#### 2.1 Autenticación de Conexiones (`ws_gateway/main.py`)

**Staff (Waiter/Kitchen/Admin):**
```python
@app.websocket("/ws/waiter")
async def waiter_websocket(websocket: WebSocket, token: str):
    claims = verify_jwt(token)  # ✅ Valida JWT completo

    # Extrae datos del token
    user_id = int(claims["sub"])
    tenant_id = int(claims.get("tenant_id", 0))  # ✅ Tenant del token
    branch_ids = list(claims.get("branch_ids", []))
    roles = claims.get("roles", [])

    # Registra conexión con branches específicos
    await manager.connect(websocket, user_id, branch_ids, sector_ids)
```

**Diners:**
```python
@app.websocket("/ws/diner")
async def diner_websocket(websocket: WebSocket, table_token: str):
    token_data = verify_table_token(table_token)  # ✅ Valida table token

    session_id = token_data["session_id"]
    table_id = token_data["table_id"]
    branch_id = token_data["branch_id"]

    # Registra solo para SU sesión
    await manager.register_session(websocket, session_id)
```

#### 2.2 Dispatch de Eventos

**Eventos filtrados por Branch/Session:**
```python
async def on_event(event: dict):
    branch_id = event.get("branch_id")
    session_id = event.get("session_id")

    if branch_id is not None:
        # Solo envía a conexiones de ESE branch
        await manager.send_to_branch(int(branch_id), event)

    if session_id is not None:
        # Solo envía a diners de ESA sesión
        await manager.send_to_session(int(session_id), event)
```

**Canales Redis:**
- `branch:{id}:waiters` - Waiters de un branch específico
- `branch:{id}:kitchen` - Kitchen de un branch específico
- `branch:{id}:admin` - Admins de un branch específico
- `sector:{id}:waiters` - Waiters asignados a un sector
- `session:{id}` - Diners de una sesión

---

### 3. Dashboard ✅ SEGURO

#### 3.1 Autenticación (`Dashboard/src/services/api.ts`)

**Token Management:**
```typescript
// Token en memoria
let authToken: string | null = null

export function setAuthToken(token: string | null) {
  authToken = token
}

// Todas las requests incluyen el token
async function fetchAPI<T>(endpoint: string, options: RequestInit = {}): Promise<T> {
  if (authToken) {
    headers['Authorization'] = `Bearer ${authToken}`
  }
}
```

**Login Response:**
```typescript
export interface AuthUser {
  id: number
  email: string
  tenant_id: number      // ✅ Tenant del usuario
  branch_ids: number[]   // ✅ Branches autorizados
  roles: string[]
}
```

#### 3.2 Flujo de Datos

El Dashboard NO almacena `tenant_id` localmente para filtros - el **backend se encarga de todo el filtrado**:

1. Usuario hace login → recibe JWT con `tenant_id` embebido
2. Dashboard llama a `/api/admin/branches` con JWT en header
3. Backend extrae `tenant_id` del JWT y filtra
4. Dashboard recibe SOLO branches de su tenant

**Esto es correcto y seguro** porque:
- El frontend no puede manipular el `tenant_id`
- Toda la lógica de aislamiento está en backend
- El JWT es firmado y verificado

---

### 4. pwaWaiter ✅ SEGURO

#### 4.1 Autenticación (`pwaWaiter/src/services/api.ts`)

**Mismo patrón que Dashboard:**
```typescript
let authToken: string | null = null

export function setAuthToken(token: string | null): void {
  authToken = token
  // Notifica a listeners (WebSocket)
  tokenChangeListeners.forEach((listener) => listener(token))
}

async function request<T>(endpoint: string, options: RequestOptions = {}): Promise<T> {
  if (authToken) {
    headers['Authorization'] = `Bearer ${authToken}`
  }
}
```

**Protección SSRF:**
```typescript
// Valida que API_BASE sea un host permitido
const ALLOWED_HOSTS = new Set<string>(API_CONFIG.ALLOWED_HOSTS)
if (!isValidApiBase(API_BASE)) {
  throw new Error(`Invalid API_BASE configuration.`)
}
```

#### 4.2 Operaciones Restringidas

Todas las llamadas incluyen JWT, y el backend filtra:
```typescript
// Solo obtiene mesas de SU branch
export const tablesAPI = {
  async getTables(branchId: number): Promise<TableCard[]> {
    return request<TableCard[]>(`/waiter/tables?branch_id=${branchId}`)
  },
}
```

---

### 5. pwaMenu ✅ SEGURO

#### 5.1 Autenticación de Diners (`pwaMenu/src/services/api.ts`)

**Table Token:**
```typescript
let tableToken: string | null = null

export function setTableToken(token: string | null): void {
  tableToken = token
  localStorage.setItem('table_token', token)
}

// Requests autenticadas con X-Table-Token
if (tableAuth) {
  const token = getTableToken()
  if (token) {
    headers['X-Table-Token'] = token
  }
}
```

#### 5.2 Endpoints Usados

**Públicos (sin auth):**
- `/api/public/menu/{slug}` - Menú por branch slug (naturalmente aislado)

**Con Table Token:**
- `/api/diner/*` - Operaciones de diner (session_id del token)
- `/api/billing/*` - Operaciones de pago (session_id del token)

---

## Defectos Identificados

### CRÍTICOS: 0

No se encontraron defectos críticos de aislamiento de tenant.

### ALTOS: 0

No se encontraron defectos de alta severidad.

### MEDIOS: 0

| ID | Descripción | Archivo | Estado |
|----|-------------|---------|--------|
| ~~MED-ISO-01~~ | ~~El endpoint `/api/admin/allergens` permite listar alérgenos de otros tenants~~ | `routers/admin.py` | ✅ CERRADO - Verificado: línea 2296 filtra por `tenant_id == user["tenant_id"]` |
| ~~MED-ISO-02~~ | ~~Los endpoints de catalog público no validan tenant activo~~ | `routers/catalog.py` | ✅ ACEPTABLE - El branch slug es único y el filtro `is_active` lo cubre |

### BAJOS: 3

| ID | Descripción | Archivo | Recomendación |
|----|-------------|---------|---------------|
| LOW-ISO-01 | El `tenant_id` se incluye en respuestas API aunque no es necesario para el frontend | Múltiples | Considerar omitir en respuestas públicas |
| LOW-ISO-02 | Logs de debug incluyen `tenant_id` lo cual podría ser útil para auditoría | Múltiples | OK - útil para debugging |
| LOW-ISO-03 | El WebSocket no valida que el `tenant_id` del JWT coincida con el tenant del branch_id | `ws_gateway/main.py` | Mejora menor - branches ya están validados por el backend |

---

## Verificación de Patrones

### Patrón 1: Creación de Entidades ✅

Todas las entidades se crean con `tenant_id` del contexto:
```python
# Correcto
branch = Branch(tenant_id=user["tenant_id"], ...)
category = Category(tenant_id=tenant_id, ...)
product = Product(tenant_id=tenant_id, ...)
```

### Patrón 2: Queries de Lectura ✅

Todas las queries filtran por tenant (directo o indirecto via branch):
```python
# Directo
select(Branch).where(Branch.tenant_id == user["tenant_id"])

# Indirecto via branch
select(Category).where(
    Category.branch_id == branch.id,  # branch ya validado por tenant
)
```

### Patrón 3: Updates/Deletes ✅

Todas las operaciones validan propiedad:
```python
branch = db.scalar(
    select(Branch).where(
        Branch.id == branch_id,
        Branch.tenant_id == user["tenant_id"],  # ✅ Validación
    )
)
if not branch:
    raise HTTPException(404, "Not found")
```

### Patrón 4: Cross-Reference ✅

Cuando se referencia otra entidad, se valida pertenencia:
```python
# Al asignar category a product
category = db.scalar(
    select(Category).where(
        Category.id == body.category_id,
        Category.tenant_id == tenant_id,  # ✅ Misma tenant
    )
)
```

---

## Conclusiones

### Fortalezas del Sistema

1. **JWT con tenant_id obligatorio** - El token siempre contiene el tenant y es validado
2. **Backend-first filtering** - Toda la lógica de aislamiento está en backend, no en frontend
3. **Table Tokens seguros** - Incluyen tenant_id, branch_id, session_id firmados
4. **WebSocket autenticado** - No hay conexiones anónimas
5. **Canales Redis por branch** - Los eventos solo llegan a subscriptores autorizados

### Recomendaciones Menores

1. **Agregar índice compuesto** en tablas críticas para queries por `(tenant_id, is_active)` - ya implementado según CLAUDE.md
2. **Log de auditoría** para operaciones cross-tenant fallidas (intentos de acceso)
3. **Rate limiting por tenant** adicional al existente por IP/email

### Estado Final

| Componente | Estado | Notas |
|------------|--------|-------|
| Backend REST API | ✅ SEGURO | Todos los endpoints filtran correctamente |
| WebSocket Gateway | ✅ SEGURO | Autenticación requerida, canales por branch |
| Dashboard | ✅ SEGURO | Depende de backend para filtrado |
| pwaWaiter | ✅ SEGURO | JWT auth, SSRF protection |
| pwaMenu | ✅ SEGURO | Table token auth, endpoints públicos naturalmente aislados |

---

**Conclusión:** El sistema implementa correctamente el aislamiento multi-tenant. Las aplicaciones solo pueden interactuar con datos de su propio tenant. No se requieren refactorizaciones críticas.
