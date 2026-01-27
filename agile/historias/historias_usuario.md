# Historias de Usuario - Backend Integrador

## Sistema de Gestión de Restaurantes Multi-Tenant

**Versión:** 2.0 (Detalle Técnico para IA)
**Fecha:** 25 de Enero de 2026
**Total de Historias:** 152

---

## Convenciones de Este Documento

### Formato de Schemas
```
Campo (tipo) [constraints]: descripción
  - Validaciones específicas
  - Ejemplo: valor
```

### Códigos de Error Estándar
| Código | Significado | Cuándo se usa |
|--------|-------------|---------------|
| 200 | OK | Operación exitosa |
| 201 | Created | Recurso creado |
| 400 | Bad Request | Validación fallida |
| 401 | Unauthorized | Token inválido/expirado |
| 403 | Forbidden | Sin permisos para acción |
| 404 | Not Found | Recurso no existe |
| 409 | Conflict | Duplicado o conflicto |
| 415 | Unsupported Media Type | Content-Type inválido |
| 422 | Unprocessable Entity | Error de validación Pydantic |
| 429 | Too Many Requests | Rate limit excedido |
| 500 | Internal Server Error | Error del servidor |

### Roles del Sistema
| Rol | Código | Permisos |
|-----|--------|----------|
| ADMIN | `"ADMIN"` | Todo el tenant |
| MANAGER | `"MANAGER"` | Solo sus branch_ids |
| KITCHEN | `"KITCHEN"` | Solo lectura + actualizar tickets |
| WAITER | `"WAITER"` | Solo sus sectores asignados |
| DINER | N/A | Auth via X-Table-Token |

---

## 1. AUTENTICACIÓN Y AUTORIZACIÓN

### HU-AUTH-001: Login de Personal

```yaml
id: HU-AUTH-001
titulo: Autenticación de Personal con JWT
endpoint: POST /api/auth/login
roles_permitidos: [Público - sin autenticación]
archivo_implementacion: backend/rest_api/routers/auth/routes.py
servicio: backend/rest_api/routers/auth/routes.py::login()
```

#### Request Schema
```json
{
  "email": "string (required)",
  "password": "string (required)"
}
```

| Campo | Tipo | Requerido | Validaciones | Ejemplo |
|-------|------|-----------|--------------|---------|
| email | string | Sí | formato email válido, max 255 chars | `"admin@demo.com"` |
| password | string | Sí | min 6 chars, max 128 chars | `"admin123"` |

#### Response Schema (200 OK)
```json
{
  "access_token": "string (JWT)",
  "refresh_token": "string (JWT)",
  "token_type": "bearer",
  "user": {
    "id": "integer",
    "email": "string",
    "first_name": "string | null",
    "last_name": "string | null",
    "tenant_id": "integer",
    "branch_ids": "integer[]",
    "roles": "string[]"
  }
}
```

#### Ejemplo Response Exitoso
```json
{
  "access_token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...",
  "refresh_token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...",
  "token_type": "bearer",
  "user": {
    "id": 1,
    "email": "admin@demo.com",
    "first_name": "Admin",
    "last_name": "Demo",
    "tenant_id": 1,
    "branch_ids": [1, 2, 3],
    "roles": ["ADMIN"]
  }
}
```

#### JWT Payload Structure (access_token)
```json
{
  "sub": "1",
  "email": "admin@demo.com",
  "tenant_id": 1,
  "branch_ids": [1, 2, 3],
  "roles": ["ADMIN"],
  "exp": 1737900000,
  "iat": 1737899100,
  "jti": "uuid-único-para-revocación"
}
```

#### Errores Específicos

| Código | Condición | Response Body |
|--------|-----------|---------------|
| 400 | Credenciales inválidas | `{"detail": "Credenciales inválidas"}` |
| 400 | Usuario inactivo | `{"detail": "Usuario deshabilitado"}` |
| 415 | Content-Type no es application/json | `{"detail": "Unsupported media type"}` |
| 422 | Email no es formato válido | `{"detail": [{"loc": ["body", "email"], "msg": "value is not a valid email address"}]}` |
| 429 | Rate limit IP (5/min) | `{"detail": "Rate limit exceeded. Try again in X seconds"}` |
| 429 | Rate limit email (5/min) | `{"detail": "Too many attempts for this email"}` |

#### Lógica de Negocio

1. **Validar Content-Type** es `application/json`
2. **Verificar rate limit** por IP (5 intentos/minuto)
3. **Verificar rate limit** por email (5 intentos/minuto)
4. **Buscar usuario** por email en BD
5. **Verificar is_active** = true
6. **Verificar contraseña** con bcrypt
7. **Re-hashear** si usa algoritmo legacy (migración automática)
8. **Obtener roles** de UserBranchRole JOIN Branch
9. **Validar** todas las branches pertenecen al mismo tenant
10. **Generar JWT** access_token (exp: 15 minutos)
11. **Generar JWT** refresh_token (exp: 7 días)
12. **Registrar log** de login exitoso

#### Modelo de Datos Involucrado

```sql
-- User
id: BIGINT PRIMARY KEY
email: VARCHAR(255) UNIQUE NOT NULL
password_hash: VARCHAR(255) NOT NULL
first_name: VARCHAR(100)
last_name: VARCHAR(100)
tenant_id: BIGINT NOT NULL REFERENCES tenant(id)
is_active: BOOLEAN DEFAULT true
created_at: TIMESTAMP
updated_at: TIMESTAMP

-- UserBranchRole (M:N)
id: BIGINT PRIMARY KEY
user_id: BIGINT REFERENCES user(id)
branch_id: BIGINT REFERENCES branch(id)
role: VARCHAR(20) CHECK (role IN ('ADMIN', 'MANAGER', 'KITCHEN', 'WAITER'))
UNIQUE(user_id, branch_id, role)
```

#### Configuración
```python
# backend/shared/config/settings.py
ACCESS_TOKEN_EXPIRE_MINUTES = 15
REFRESH_TOKEN_EXPIRE_DAYS = 7
JWT_ALGORITHM = "HS256"
```

#### Seguridad
- Password hashing: bcrypt (12 rounds)
- Rate limiting: Redis + slowapi
- Fail-closed: Si Redis falla, deniega acceso

---

### HU-AUTH-002: Refresh Token

```yaml
id: HU-AUTH-002
titulo: Renovación de Token de Acceso
endpoint: POST /api/auth/refresh
roles_permitidos: [Usuario con refresh_token válido]
archivo_implementacion: backend/rest_api/routers/auth/routes.py
```

#### Request Schema
```json
{
  "refresh_token": "string (required)"
}
```

#### Response Schema (200 OK)
```json
{
  "access_token": "string (JWT nuevo)",
  "token_type": "bearer"
}
```

#### Errores Específicos

| Código | Condición | Response Body |
|--------|-----------|---------------|
| 401 | Token expirado | `{"detail": "Token expirado"}` |
| 401 | Token inválido | `{"detail": "Token inválido"}` |
| 401 | Token revocado (blacklist) | `{"detail": "Token revocado"}` |
| 401 | Usuario inactivo | `{"detail": "Usuario deshabilitado"}` |
| 429 | Rate limit (10/min) | `{"detail": "Rate limit exceeded"}` |

#### Lógica de Negocio

1. **Validar** refresh_token (firma, expiración)
2. **Verificar** token no está en blacklist (Redis)
3. **Obtener** user_id del token (claim "sub")
4. **Buscar usuario** en BD, verificar is_active
5. **Re-obtener roles** actuales de UserBranchRole (cambios en tiempo real)
6. **Generar nuevo** access_token con datos actualizados
7. **NO invalida** el refresh_token original

#### Notas de Implementación
- pwaWaiter: llama proactivamente cada 14 minutos
- Dashboard: llama reactivamente cuando recibe 401

---

### HU-AUTH-003: Información de Usuario Actual

```yaml
id: HU-AUTH-003
titulo: Obtener Datos del Usuario Autenticado
endpoint: GET /api/auth/me
roles_permitidos: [ADMIN, MANAGER, KITCHEN, WAITER]
autenticacion: Bearer Token (JWT)
```

#### Request
- Header: `Authorization: Bearer {access_token}`
- No body

#### Response Schema (200 OK)
```json
{
  "id": "integer",
  "email": "string",
  "first_name": "string | null",
  "last_name": "string | null",
  "tenant_id": "integer",
  "branch_ids": "integer[]",
  "roles": "string[]"
}
```

#### Errores Específicos

| Código | Condición | Response Body |
|--------|-----------|---------------|
| 401 | Token faltante | `{"detail": "Not authenticated"}` |
| 401 | Token expirado | `{"detail": "Token expirado"}` |
| 401 | Token inválido | `{"detail": "Token inválido"}` |

#### Lógica de Negocio
1. **Extraer** JWT del header Authorization
2. **Validar** firma y expiración
3. **Retornar** claims del token directamente

---

### HU-AUTH-004: Logout Global

```yaml
id: HU-AUTH-004
titulo: Cierre de Sesión en Todos los Dispositivos
endpoint: POST /api/auth/logout
roles_permitidos: [ADMIN, MANAGER, KITCHEN, WAITER]
autenticacion: Bearer Token (JWT)
```

#### Request
- Header: `Authorization: Bearer {access_token}`
- Body: vacío o `{}`

#### Response Schema (200 OK)
```json
{
  "message": "Sesión cerrada exitosamente"
}
```

#### Errores Específicos

| Código | Condición | Response Body |
|--------|-----------|---------------|
| 401 | Token inválido | `{"detail": "Token inválido"}` |
| 429 | Rate limit (10/min) | `{"detail": "Rate limit exceeded"}` |

#### Lógica de Negocio

1. **Extraer** user_id del JWT
2. **Llamar** `revoke_all_user_tokens(user_id)`
3. **Agregar** todos los tokens activos a blacklist en Redis
4. **TTL** de blacklist = tiempo restante de expiración del token

#### Implementación Redis Blacklist
```python
# Formato key: token_blacklist:{jti}
# TTL: segundos hasta expiración del token
await redis.setex(f"token_blacklist:{jti}", ttl_seconds, "1")
```

---

### HU-AUTH-005: Validación RBAC en Cada Request

```yaml
id: HU-AUTH-005
titulo: Control de Acceso Basado en Roles
tipo: Historia de Sistema (no endpoint)
archivo_implementacion: backend/rest_api/services/permissions/
```

#### Matriz de Permisos por Rol

| Entidad | ADMIN | MANAGER | KITCHEN | WAITER |
|---------|-------|---------|---------|--------|
| Staff | CRUD | CRU (sin ADMIN role) | - | - |
| Categories | CRUD | CRUD (sus branches) | R | R |
| Products | CRUD | CRUD (sus branches) | R | R |
| Tables | CRUD | CRUD (sus branches) | - | R (sus sectores) |
| Rounds | CRUD | CRUD | RU (estado) | RU (sus mesas) |
| KitchenTickets | CRUD | CRUD | RU (estado) | R |
| Payments | CRUD | CRUD | - | R |

#### Implementación PermissionContext
```python
from rest_api.services.permissions import PermissionContext

# En cada router
ctx = PermissionContext(user)  # user viene de current_user dependency

# Verificaciones disponibles
ctx.is_admin          # bool
ctx.is_management     # bool (ADMIN o MANAGER)
ctx.tenant_id         # int
ctx.branch_ids        # list[int]
ctx.require_management()  # Raises ForbiddenError si no es ADMIN/MANAGER
ctx.require_branch_access(branch_id)  # Raises si MANAGER sin acceso
```

#### Error de Autorización
```json
{
  "detail": "No tiene permiso para realizar esta acción"
}
```
Status: 403 Forbidden

---

## 2. GESTIÓN DE PERSONAL (STAFF)

### HU-STAFF-001: Listar Personal

```yaml
id: HU-STAFF-001
titulo: Obtener Lista de Empleados
endpoint: GET /api/admin/staff
roles_permitidos: [ADMIN, MANAGER]
autenticacion: Bearer Token (JWT)
archivo_implementacion: backend/rest_api/routers/admin/staff.py
servicio: rest_api/services/domain/staff_service.py::StaffService
```

#### Query Parameters

| Parámetro | Tipo | Requerido | Default | Validación | Descripción |
|-----------|------|-----------|---------|------------|-------------|
| branch_id | integer | No | null | > 0 | Filtrar por sucursal |
| limit | integer | No | 50 | 1-200 | Máximo resultados |
| offset | integer | No | 0 | >= 0 | Paginación |
| include_deleted | boolean | No | false | - | Incluir eliminados |

#### Response Schema (200 OK)
```json
{
  "items": [
    {
      "id": "integer",
      "email": "string",
      "first_name": "string | null",
      "last_name": "string | null",
      "is_active": "boolean",
      "branches": [
        {
          "branch_id": "integer",
          "branch_name": "string",
          "roles": ["string"]
        }
      ],
      "created_at": "datetime ISO8601",
      "updated_at": "datetime ISO8601"
    }
  ],
  "total": "integer",
  "limit": "integer",
  "offset": "integer"
}
```

#### Ejemplo Response
```json
{
  "items": [
    {
      "id": 2,
      "email": "manager@demo.com",
      "first_name": "María",
      "last_name": "García",
      "is_active": true,
      "branches": [
        {
          "branch_id": 1,
          "branch_name": "Sucursal Centro",
          "roles": ["MANAGER"]
        },
        {
          "branch_id": 2,
          "branch_name": "Sucursal Norte",
          "roles": ["MANAGER", "WAITER"]
        }
      ],
      "created_at": "2026-01-15T10:30:00Z",
      "updated_at": "2026-01-20T14:22:00Z"
    }
  ],
  "total": 15,
  "limit": 50,
  "offset": 0
}
```

#### Lógica de Negocio

1. **Validar permisos**: require_management()
2. **Si MANAGER**: filtrar solo usuarios de sus branch_ids
3. **Si branch_id**: aplicar filtro adicional
4. **Ordenar** por email ASC
5. **Aplicar paginación** (limit/offset)
6. **Eager loading**: UserBranchRole → Branch (evitar N+1)

#### SQL Generado (aproximado)
```sql
SELECT u.*, ubr.branch_id, ubr.role, b.name as branch_name
FROM user u
JOIN user_branch_role ubr ON u.id = ubr.user_id
JOIN branch b ON ubr.branch_id = b.id
WHERE u.tenant_id = :tenant_id
  AND u.is_active = true  -- unless include_deleted
  AND (:branch_id IS NULL OR ubr.branch_id = :branch_id)
  AND (:manager_branches IS NULL OR ubr.branch_id = ANY(:manager_branches))
ORDER BY u.email
LIMIT :limit OFFSET :offset
```

---

### HU-STAFF-002: Ver Detalle de Empleado

```yaml
id: HU-STAFF-002
titulo: Obtener Información Detallada de un Empleado
endpoint: GET /api/admin/staff/{staff_id}
roles_permitidos: [ADMIN, MANAGER]
autenticacion: Bearer Token (JWT)
```

#### Path Parameters

| Parámetro | Tipo | Validación | Descripción |
|-----------|------|------------|-------------|
| staff_id | integer | > 0 | ID del empleado |

#### Response Schema (200 OK)
```json
{
  "id": "integer",
  "email": "string",
  "first_name": "string | null",
  "last_name": "string | null",
  "is_active": "boolean",
  "branches": [
    {
      "branch_id": "integer",
      "branch_name": "string",
      "roles": ["string"]
    }
  ],
  "created_at": "datetime",
  "updated_at": "datetime",
  "created_by_email": "string | null",
  "updated_by_email": "string | null"
}
```

#### Errores Específicos

| Código | Condición | Response Body |
|--------|-----------|---------------|
| 403 | MANAGER sin acceso a branches del empleado | `{"detail": "No tiene permiso para ver este empleado"}` |
| 404 | staff_id no existe | `{"detail": "Empleado no encontrado", "entity": "Staff", "id": 123}` |

#### Lógica de Negocio
1. **Buscar** usuario por ID y tenant_id
2. **Si MANAGER**: verificar al menos una branch compartida
3. **Cargar** branches y roles con eager loading

---

### HU-STAFF-003: Crear Empleado

```yaml
id: HU-STAFF-003
titulo: Registrar Nuevo Empleado
endpoint: POST /api/admin/staff
roles_permitidos: [ADMIN, MANAGER]
autenticacion: Bearer Token (JWT)
websocket_event: ENTITY_CREATED
```

#### Request Schema
```json
{
  "email": "string (required)",
  "password": "string (required)",
  "first_name": "string (optional)",
  "last_name": "string (optional)",
  "branch_roles": [
    {
      "branch_id": "integer (required)",
      "roles": ["string"]
    }
  ]
}
```

#### Validaciones de Campos

| Campo | Tipo | Requerido | Validaciones |
|-------|------|-----------|--------------|
| email | string | Sí | email válido, max 255, único por tenant |
| password | string | Sí | min 6 chars, max 128 chars |
| first_name | string | No | max 100 chars |
| last_name | string | No | max 100 chars |
| branch_roles | array | Sí | min 1 elemento |
| branch_roles[].branch_id | integer | Sí | debe existir en tenant |
| branch_roles[].roles | string[] | Sí | cada uno IN ('ADMIN','MANAGER','KITCHEN','WAITER') |

#### Restricciones por Rol del Creador

| Creador | Puede Crear | Restricciones |
|---------|-------------|---------------|
| ADMIN | Cualquier rol | Sin restricciones |
| MANAGER | MANAGER, KITCHEN, WAITER | NO puede crear ADMIN, solo sus branches |

#### Response Schema (201 Created)
```json
{
  "id": "integer",
  "email": "string",
  "first_name": "string | null",
  "last_name": "string | null",
  "is_active": true,
  "branches": [...],
  "created_at": "datetime"
}
```

#### Errores Específicos

| Código | Condición | Response Body |
|--------|-----------|---------------|
| 400 | Email ya existe en tenant | `{"detail": "El email ya está registrado en este tenant"}` |
| 403 | MANAGER intenta crear ADMIN | `{"detail": "No puede asignar rol ADMIN"}` |
| 403 | MANAGER intenta crear en branch sin acceso | `{"detail": "No tiene acceso a la sucursal X"}` |
| 404 | branch_id no existe | `{"detail": "Sucursal no encontrada", "id": 99}` |

#### Lógica de Negocio

1. **Validar permisos** del creador
2. **Verificar email** único en tenant
3. **Si MANAGER**: verificar no incluye rol ADMIN
4. **Si MANAGER**: verificar todas las branches son suyas
5. **Hashear password** con bcrypt
6. **Crear User** con tenant_id del creador
7. **Crear UserBranchRole** por cada branch_role
8. **Registrar auditoría** (created_by_id, created_by_email)
9. **Publicar evento** WebSocket ENTITY_CREATED

#### WebSocket Event
```json
{
  "type": "ENTITY_CREATED",
  "entity_type": "Staff",
  "entity_id": 5,
  "tenant_id": 1,
  "branch_ids": [1, 2],
  "data": { "email": "nuevo@demo.com" }
}
```

---

### HU-STAFF-004: Actualizar Empleado

```yaml
id: HU-STAFF-004
titulo: Modificar Datos de Empleado
endpoint: PATCH /api/admin/staff/{staff_id}
roles_permitidos: [ADMIN, MANAGER]
autenticacion: Bearer Token (JWT)
websocket_event: ENTITY_UPDATED
```

#### Path Parameters
| Parámetro | Tipo | Descripción |
|-----------|------|-------------|
| staff_id | integer | ID del empleado |

#### Request Schema (Parcial - todos opcionales)
```json
{
  "email": "string (optional)",
  "password": "string (optional)",
  "first_name": "string (optional)",
  "last_name": "string (optional)",
  "is_active": "boolean (optional)",
  "branch_roles": [
    {
      "branch_id": "integer",
      "roles": ["string"]
    }
  ]
}
```

#### Comportamiento Actualización Parcial
- Solo se actualizan campos presentes en el body
- `branch_roles` si presente: **REEMPLAZA** todas las asignaciones

#### Errores Específicos

| Código | Condición | Response Body |
|--------|-----------|---------------|
| 400 | Nuevo email ya existe | `{"detail": "El email ya está registrado"}` |
| 403 | MANAGER intenta asignar ADMIN | `{"detail": "No puede asignar rol ADMIN"}` |
| 403 | MANAGER modifica empleado fuera de sus branches | `{"detail": "No tiene permiso"}` |
| 404 | staff_id no existe | `{"detail": "Empleado no encontrado"}` |

#### Lógica de Negocio

1. **Buscar** empleado por ID
2. **Validar permisos** según rol
3. **Si password**: rehashear con bcrypt
4. **Si branch_roles**:
   - Eliminar UserBranchRole existentes
   - Crear nuevos UserBranchRole
5. **Actualizar** campos presentes
6. **Registrar** updated_by_id, updated_by_email, updated_at
7. **Publicar** WebSocket ENTITY_UPDATED

---

### HU-STAFF-005: Eliminar Empleado (Soft Delete)

```yaml
id: HU-STAFF-005
titulo: Desactivar Empleado
endpoint: DELETE /api/admin/staff/{staff_id}
roles_permitidos: [ADMIN]
autenticacion: Bearer Token (JWT)
websocket_event: ENTITY_DELETED
```

#### Path Parameters
| Parámetro | Tipo | Descripción |
|-----------|------|-------------|
| staff_id | integer | ID del empleado |

#### Response Schema (200 OK)
```json
{
  "message": "Empleado eliminado exitosamente",
  "id": "integer"
}
```

#### Errores Específicos

| Código | Condición | Response Body |
|--------|-----------|---------------|
| 403 | No es ADMIN | `{"detail": "Solo ADMIN puede eliminar empleados"}` |
| 404 | staff_id no existe | `{"detail": "Empleado no encontrado"}` |

#### Lógica de Negocio

1. **Validar** rol ADMIN
2. **Buscar** empleado
3. **Soft delete**: is_active = false
4. **Registrar**: deleted_by_id, deleted_by_email, deleted_at
5. **NO elimina** UserBranchRole (preserva histórico)
6. **Publicar** WebSocket ENTITY_DELETED

---

### HU-STAFF-006: Restaurar Empleado

```yaml
id: HU-STAFF-006
titulo: Reactivar Empleado Eliminado
endpoint: POST /api/admin/staff/{staff_id}/restore
roles_permitidos: [ADMIN]
autenticacion: Bearer Token (JWT)
websocket_event: ENTITY_UPDATED
```

#### Response Schema (200 OK)
```json
{
  "message": "Empleado restaurado exitosamente",
  "id": "integer",
  "email": "string"
}
```

#### Lógica de Negocio
1. **Buscar** empleado incluyendo inactivos
2. **Validar** está inactivo
3. **Restaurar**: is_active = true, deleted_at = null
4. **Publicar** WebSocket ENTITY_UPDATED

---

## 3. GESTIÓN DE CATEGORÍAS

### HU-CAT-001: Listar Categorías

```yaml
id: HU-CAT-001
titulo: Obtener Lista de Categorías del Menú
endpoint: GET /api/admin/categories
roles_permitidos: [ADMIN, MANAGER, KITCHEN, WAITER]
autenticacion: Bearer Token (JWT)
archivo_implementacion: backend/rest_api/routers/admin/categories.py
servicio: rest_api/services/domain/category_service.py::CategoryService
```

#### Query Parameters

| Parámetro | Tipo | Requerido | Default | Validación | Descripción |
|-----------|------|-----------|---------|------------|-------------|
| branch_id | integer | No | null | > 0 | Filtrar por sucursal |
| limit | integer | No | 50 | 1-500 | Máximo resultados |
| offset | integer | No | 0 | >= 0 | Paginación |
| include_deleted | boolean | No | false | - | Incluir eliminadas |

#### Response Schema (200 OK)
```json
{
  "items": [
    {
      "id": "integer",
      "name": "string",
      "image": "string | null (URL)",
      "display_order": "integer",
      "branch_id": "integer",
      "branch_name": "string",
      "is_active": "boolean",
      "created_at": "datetime",
      "updated_at": "datetime"
    }
  ],
  "total": "integer",
  "limit": "integer",
  "offset": "integer"
}
```

#### Ejemplo Response
```json
{
  "items": [
    {
      "id": 1,
      "name": "Bebidas",
      "image": "https://cdn.example.com/bebidas.jpg",
      "display_order": 1,
      "branch_id": 1,
      "branch_name": "Sucursal Centro",
      "is_active": true,
      "created_at": "2026-01-10T08:00:00Z",
      "updated_at": "2026-01-10T08:00:00Z"
    },
    {
      "id": 2,
      "name": "Entradas",
      "image": null,
      "display_order": 2,
      "branch_id": 1,
      "branch_name": "Sucursal Centro",
      "is_active": true,
      "created_at": "2026-01-10T08:00:00Z",
      "updated_at": "2026-01-10T08:00:00Z"
    }
  ],
  "total": 8,
  "limit": 50,
  "offset": 0
}
```

#### Lógica de Negocio
1. **Aplicar filtro** tenant_id del JWT
2. **Si MANAGER/KITCHEN/WAITER**: filtrar por sus branch_ids
3. **Si branch_id**: aplicar filtro adicional
4. **Ordenar** por display_order ASC
5. **Eager loading**: Branch para branch_name

#### Modelo de Datos
```sql
-- Category
id: BIGINT PRIMARY KEY
name: VARCHAR(100) NOT NULL
image: VARCHAR(500)  -- URL validada
display_order: INTEGER DEFAULT 0
branch_id: BIGINT NOT NULL REFERENCES branch(id)
tenant_id: BIGINT NOT NULL REFERENCES tenant(id)
is_active: BOOLEAN DEFAULT true
created_at: TIMESTAMP
updated_at: TIMESTAMP
created_by_id: BIGINT
created_by_email: VARCHAR(255)
-- Índices
INDEX idx_category_branch (branch_id)
INDEX idx_category_tenant_active (tenant_id, is_active)
```

---

### HU-CAT-002: Ver Detalle de Categoría

```yaml
id: HU-CAT-002
titulo: Obtener Información de una Categoría
endpoint: GET /api/admin/categories/{category_id}
roles_permitidos: [ADMIN, MANAGER]
autenticacion: Bearer Token (JWT)
```

#### Path Parameters
| Parámetro | Tipo | Validación | Descripción |
|-----------|------|------------|-------------|
| category_id | integer | > 0 | ID de la categoría |

#### Response Schema (200 OK)
```json
{
  "id": "integer",
  "name": "string",
  "image": "string | null",
  "display_order": "integer",
  "branch_id": "integer",
  "branch_name": "string",
  "is_active": "boolean",
  "subcategories_count": "integer",
  "products_count": "integer",
  "created_at": "datetime",
  "updated_at": "datetime"
}
```

#### Errores Específicos
| Código | Condición | Response Body |
|--------|-----------|---------------|
| 403 | MANAGER sin acceso a branch | `{"detail": "No tiene acceso a esta sucursal"}` |
| 404 | category_id no existe | `{"detail": "Categoría no encontrada", "entity": "Category", "id": 99}` |

---

### HU-CAT-003: Crear Categoría

```yaml
id: HU-CAT-003
titulo: Crear Nueva Categoría
endpoint: POST /api/admin/categories
roles_permitidos: [ADMIN, MANAGER]
autenticacion: Bearer Token (JWT)
websocket_event: ENTITY_CREATED
```

#### Request Schema
```json
{
  "name": "string (required)",
  "branch_id": "integer (required)",
  "image": "string (optional, URL)",
  "display_order": "integer (optional)"
}
```

#### Validaciones de Campos

| Campo | Tipo | Requerido | Validaciones |
|-------|------|-----------|--------------|
| name | string | Sí | min 1, max 100 chars, único por branch |
| branch_id | integer | Sí | debe existir, debe pertenecer al tenant |
| image | string | No | URL válida, no localhost/IPs internas (SSRF) |
| display_order | integer | No | >= 0, si omitido: max(order)+1 en branch |

#### Validación de Image URL (SSRF Prevention)
```python
BLOCKED_HOSTS = [
    "localhost", "127.0.0.1", "0.0.0.0",
    "10.", "172.16.", "172.17.", ..., "172.31.",
    "192.168.", "169.254.169.254",  # AWS metadata
    "metadata.google"  # GCP metadata
]
# Solo permite: http://, https://
# Bloquea: file://, ftp://, data:
```

#### Response Schema (201 Created)
```json
{
  "id": "integer",
  "name": "string",
  "image": "string | null",
  "display_order": "integer",
  "branch_id": "integer",
  "branch_name": "string",
  "created_at": "datetime"
}
```

#### Errores Específicos

| Código | Condición | Response Body |
|--------|-----------|---------------|
| 400 | Nombre duplicado en branch | `{"detail": "Ya existe una categoría con ese nombre en esta sucursal"}` |
| 400 | URL imagen inválida | `{"detail": "URL de imagen no válida", "field": "image"}` |
| 403 | MANAGER sin acceso a branch | `{"detail": "No tiene acceso a esta sucursal"}` |
| 404 | branch_id no existe | `{"detail": "Sucursal no encontrada"}` |

#### Lógica de Negocio

1. **Validar permisos** del creador para branch_id
2. **Verificar branch_id** existe y pertenece al tenant
3. **Verificar nombre** único en branch
4. **Validar image URL** si presente (SSRF prevention)
5. **Calcular display_order** si no se proporciona
6. **Crear Category**
7. **Registrar auditoría**
8. **Publicar** WebSocket ENTITY_CREATED

---

### HU-CAT-004: Actualizar Categoría

```yaml
id: HU-CAT-004
titulo: Modificar Categoría
endpoint: PATCH /api/admin/categories/{category_id}
roles_permitidos: [ADMIN, MANAGER]
autenticacion: Bearer Token (JWT)
websocket_event: ENTITY_UPDATED
```

#### Request Schema (Parcial)
```json
{
  "name": "string (optional)",
  "image": "string | null (optional)",
  "display_order": "integer (optional)"
}
```

**Nota**: `branch_id` NO se puede cambiar después de creación.

#### Response Schema (200 OK)
Mismo que GET /categories/{id}

#### Errores Específicos
| Código | Condición | Response Body |
|--------|-----------|---------------|
| 400 | Nombre duplicado | `{"detail": "Ya existe una categoría con ese nombre"}` |
| 403 | Sin acceso a branch | `{"detail": "No tiene permiso"}` |
| 404 | No encontrada | `{"detail": "Categoría no encontrada"}` |

---

### HU-CAT-005: Eliminar Categoría (Soft Delete con Cascade)

```yaml
id: HU-CAT-005
titulo: Eliminar Categoría y Dependencias
endpoint: DELETE /api/admin/categories/{category_id}
roles_permitidos: [ADMIN, MANAGER]
autenticacion: Bearer Token (JWT)
websocket_events: [ENTITY_DELETED, CASCADE_DELETE]
```

#### Response Schema (200 OK)
```json
{
  "message": "Categoría eliminada exitosamente",
  "id": "integer",
  "cascade": {
    "subcategories": "integer (count)",
    "products": "integer (count)"
  }
}
```

#### Comportamiento Cascade

```
Category (soft delete)
  └── Subcategory (soft delete cascade)
        └── Product (soft delete cascade)
              └── BranchProduct (soft delete cascade)
              └── ProductAllergen (soft delete cascade)
              └── ProductIngredient (soft delete cascade)
```

#### WebSocket Events (en orden)
```json
// 1. Primero el cascade
{
  "type": "CASCADE_DELETE",
  "parent_type": "Category",
  "parent_id": 5,
  "affected": [
    {"type": "Subcategory", "ids": [10, 11, 12]},
    {"type": "Product", "ids": [100, 101, 102, 103]}
  ]
}

// 2. Luego la entidad principal
{
  "type": "ENTITY_DELETED",
  "entity_type": "Category",
  "entity_id": 5
}
```

#### Lógica de Negocio

1. **Buscar** categoría
2. **Validar permisos** para branch
3. **Identificar** todas las dependencias (subcategorías → productos)
4. **Soft delete** en orden inverso (productos → subcategorías → categoría)
5. **Registrar** deleted_by en cada entidad
6. **Publicar** CASCADE_DELETE
7. **Publicar** ENTITY_DELETED

---

### HU-CAT-006: Restaurar Categoría

```yaml
id: HU-CAT-006
titulo: Restaurar Categoría Eliminada
endpoint: POST /api/admin/categories/{category_id}/restore
roles_permitidos: [ADMIN]
autenticacion: Bearer Token (JWT)
websocket_event: ENTITY_UPDATED
```

#### Response Schema (200 OK)
```json
{
  "message": "Categoría restaurada exitosamente",
  "id": "integer",
  "cascade_restored": {
    "subcategories": "integer",
    "products": "integer"
  }
}
```

#### Lógica de Negocio
1. **Buscar** categoría incluyendo inactivas
2. **Restaurar** categoría: is_active=true, deleted_at=null
3. **Restaurar** subcategorías que fueron eliminadas con esta categoría
4. **Restaurar** productos que fueron eliminados con las subcategorías
5. **Publicar** ENTITY_UPDATED

---

### HU-CAT-007: Reordenar Categorías

```yaml
id: HU-CAT-007
titulo: Cambiar Orden de Categorías
endpoint: PATCH /api/admin/categories/reorder
roles_permitidos: [ADMIN, MANAGER]
autenticacion: Bearer Token (JWT)
websocket_event: ENTITY_UPDATED (múltiple)
```

#### Request Schema
```json
{
  "branch_id": "integer (required)",
  "order": [
    {"id": "integer", "display_order": "integer"}
  ]
}
```

#### Ejemplo Request
```json
{
  "branch_id": 1,
  "order": [
    {"id": 2, "display_order": 1},
    {"id": 1, "display_order": 2},
    {"id": 3, "display_order": 3}
  ]
}
```

#### Response Schema (200 OK)
```json
{
  "message": "Orden actualizado",
  "updated": 3
}
```

#### Errores Específicos
| Código | Condición | Response Body |
|--------|-----------|---------------|
| 400 | IDs no pertenecen a branch | `{"detail": "Categoría X no pertenece a esta sucursal"}` |
| 403 | Sin acceso a branch | `{"detail": "No tiene permiso"}` |

---

## 4. GESTIÓN DE SUBCATEGORÍAS

### HU-SUBCAT-001: Listar Subcategorías

```yaml
id: HU-SUBCAT-001
titulo: Obtener Subcategorías
endpoint: GET /api/admin/subcategories
roles_permitidos: [ADMIN, MANAGER, KITCHEN, WAITER]
autenticacion: Bearer Token (JWT)
servicio: rest_api/services/domain/subcategory_service.py
```

#### Query Parameters

| Parámetro | Tipo | Requerido | Default | Descripción |
|-----------|------|-----------|---------|-------------|
| category_id | integer | No | null | Filtrar por categoría padre |
| branch_id | integer | No | null | Filtrar por sucursal |
| limit | integer | No | 50 | Máximo 500 |
| offset | integer | No | 0 | Paginación |

#### Response Schema (200 OK)
```json
{
  "items": [
    {
      "id": "integer",
      "name": "string",
      "image": "string | null",
      "display_order": "integer",
      "category_id": "integer",
      "category_name": "string",
      "branch_id": "integer",
      "branch_name": "string",
      "is_active": "boolean"
    }
  ],
  "total": "integer"
}
```

#### Modelo de Datos
```sql
-- Subcategory
id: BIGINT PRIMARY KEY
name: VARCHAR(100) NOT NULL
image: VARCHAR(500)
display_order: INTEGER DEFAULT 0
category_id: BIGINT NOT NULL REFERENCES category(id)
tenant_id: BIGINT NOT NULL REFERENCES tenant(id)
is_active: BOOLEAN DEFAULT true
-- Heredada de category: branch_id
```

---

### HU-SUBCAT-002 a HU-SUBCAT-007

Siguen el mismo patrón que Categorías:
- **HU-SUBCAT-002**: GET /{id} - Ver detalle
- **HU-SUBCAT-003**: POST - Crear (requiere category_id válido)
- **HU-SUBCAT-004**: PATCH /{id} - Actualizar
- **HU-SUBCAT-005**: DELETE /{id} - Soft delete (cascade a Products)
- **HU-SUBCAT-006**: POST /{id}/restore - Restaurar
- **HU-SUBCAT-007**: PATCH /reorder - Reordenar

---

## 5. GESTIÓN DE PRODUCTOS

### HU-PROD-001: Listar Productos

```yaml
id: HU-PROD-001
titulo: Obtener Lista de Productos
endpoint: GET /api/admin/products
roles_permitidos: [ADMIN, MANAGER, KITCHEN, WAITER]
autenticacion: Bearer Token (JWT)
servicio: rest_api/services/domain/product_service.py::ProductService
```

#### Query Parameters

| Parámetro | Tipo | Requerido | Default | Descripción |
|-----------|------|-----------|---------|-------------|
| branch_id | integer | No | null | Filtrar por sucursal |
| category_id | integer | No | null | Filtrar por categoría |
| subcategory_id | integer | No | null | Filtrar por subcategoría |
| search | string | No | null | Buscar en nombre/descripción |
| limit | integer | No | 100 | Máximo 500 |
| offset | integer | No | 0 | Paginación |
| include_deleted | boolean | No | false | Incluir eliminados |

#### Response Schema (200 OK)
```json
{
  "items": [
    {
      "id": "integer",
      "name": "string",
      "description": "string | null",
      "image": "string | null",
      "base_price_cents": "integer",
      "subcategory_id": "integer",
      "subcategory_name": "string",
      "category_id": "integer",
      "category_name": "string",
      "branch_prices": [
        {
          "branch_id": "integer",
          "branch_name": "string",
          "price_cents": "integer",
          "is_available": "boolean"
        }
      ],
      "allergens": [
        {
          "allergen_id": "integer",
          "allergen_name": "string",
          "presence_type": "string",
          "risk_level": "string"
        }
      ],
      "is_active": "boolean"
    }
  ],
  "total": "integer"
}
```

#### Ejemplo Response
```json
{
  "items": [
    {
      "id": 1,
      "name": "Pizza Margarita",
      "description": "Tomate, mozzarella, albahaca",
      "image": "https://cdn.example.com/pizza.jpg",
      "base_price_cents": 1500,
      "subcategory_id": 5,
      "subcategory_name": "Pizzas Clásicas",
      "category_id": 3,
      "category_name": "Principales",
      "branch_prices": [
        {
          "branch_id": 1,
          "branch_name": "Centro",
          "price_cents": 1500,
          "is_available": true
        },
        {
          "branch_id": 2,
          "branch_name": "Norte",
          "price_cents": 1600,
          "is_available": true
        }
      ],
      "allergens": [
        {
          "allergen_id": 1,
          "allergen_name": "Gluten",
          "presence_type": "CONTAINS",
          "risk_level": "HIGH"
        },
        {
          "allergen_id": 2,
          "allergen_name": "Lácteos",
          "presence_type": "CONTAINS",
          "risk_level": "HIGH"
        }
      ],
      "is_active": true
    }
  ],
  "total": 150
}
```

#### Modelo de Datos

```sql
-- Product
id: BIGINT PRIMARY KEY
name: VARCHAR(200) NOT NULL
description: TEXT
image: VARCHAR(500)
base_price_cents: INTEGER NOT NULL  -- Precio base en centavos
subcategory_id: BIGINT NOT NULL REFERENCES subcategory(id)
tenant_id: BIGINT NOT NULL REFERENCES tenant(id)
is_active: BOOLEAN DEFAULT true

-- BranchProduct (precio por sucursal)
id: BIGINT PRIMARY KEY
product_id: BIGINT REFERENCES product(id)
branch_id: BIGINT REFERENCES branch(id)
price_cents: INTEGER NOT NULL  -- Puede diferir de base_price
is_available: BOOLEAN DEFAULT true
UNIQUE(product_id, branch_id)

-- ProductAllergen (M:N)
id: BIGINT PRIMARY KEY
product_id: BIGINT REFERENCES product(id)
allergen_id: BIGINT REFERENCES allergen(id)
presence_type: VARCHAR(20)  -- 'CONTAINS', 'MAY_CONTAIN', 'TRACE'
risk_level: VARCHAR(20)     -- 'HIGH', 'MEDIUM', 'LOW'
UNIQUE(product_id, allergen_id)
```

#### Lógica de Negocio
1. **Filtrar** por tenant_id
2. **Si MANAGER**: filtrar por sus branch_ids
3. **Aplicar filtros** opcionales
4. **Eager loading**:
   - Subcategory → Category
   - BranchProduct → Branch
   - ProductAllergen → Allergen
5. **Evitar N+1** con selectinload/joinedload

---

### HU-PROD-002: Ver Detalle de Producto

```yaml
id: HU-PROD-002
titulo: Obtener Información Completa de Producto
endpoint: GET /api/admin/products/{product_id}
roles_permitidos: [ADMIN, MANAGER]
```

#### Response Schema (200 OK)
```json
{
  "id": "integer",
  "name": "string",
  "description": "string | null",
  "image": "string | null",
  "base_price_cents": "integer",
  "subcategory_id": "integer",
  "subcategory_name": "string",
  "category_id": "integer",
  "category_name": "string",
  "branch_prices": [...],
  "allergens": [...],
  "ingredients": [
    {
      "ingredient_id": "integer",
      "ingredient_name": "string",
      "quantity": "string | null",
      "is_optional": "boolean"
    }
  ],
  "dietary_flags": {
    "is_vegetarian": "boolean",
    "is_vegan": "boolean",
    "is_gluten_free": "boolean",
    "is_keto": "boolean",
    "is_low_sodium": "boolean"
  },
  "preparation_time_minutes": "integer | null",
  "calories": "integer | null",
  "is_active": "boolean",
  "created_at": "datetime",
  "updated_at": "datetime"
}
```

---

### HU-PROD-003: Crear Producto

```yaml
id: HU-PROD-003
titulo: Crear Nuevo Producto
endpoint: POST /api/admin/products
roles_permitidos: [ADMIN, MANAGER]
websocket_event: ENTITY_CREATED
```

#### Request Schema
```json
{
  "name": "string (required)",
  "description": "string (optional)",
  "image": "string (optional, URL)",
  "base_price_cents": "integer (required)",
  "subcategory_id": "integer (required)",
  "branch_prices": [
    {
      "branch_id": "integer (required)",
      "price_cents": "integer (optional, default=base_price)",
      "is_available": "boolean (optional, default=true)"
    }
  ],
  "allergen_ids": ["integer"],
  "allergens_detailed": [
    {
      "allergen_id": "integer",
      "presence_type": "string (CONTAINS|MAY_CONTAIN|TRACE)",
      "risk_level": "string (HIGH|MEDIUM|LOW)"
    }
  ],
  "ingredient_ids": ["integer"],
  "dietary_flags": {
    "is_vegetarian": "boolean",
    "is_vegan": "boolean",
    "is_gluten_free": "boolean"
  }
}
```

#### Validaciones

| Campo | Validación |
|-------|------------|
| name | min 1, max 200, único por subcategoría |
| base_price_cents | > 0, max 99999999 (999,999.99) |
| subcategory_id | debe existir en tenant |
| branch_prices[].branch_id | debe pertenecer al tenant |
| image | URL válida, SSRF prevention |
| allergen_ids | todos deben existir en tenant |

#### Response Schema (201 Created)
Mismo que GET /{product_id}

#### Errores Específicos
| Código | Condición | Response |
|--------|-----------|----------|
| 400 | Nombre duplicado en subcategoría | `{"detail": "Ya existe un producto con ese nombre"}` |
| 400 | Precio <= 0 | `{"detail": "El precio debe ser mayor a 0"}` |
| 403 | MANAGER sin acceso a branch | `{"detail": "No tiene acceso a la sucursal X"}` |
| 404 | subcategory_id no existe | `{"detail": "Subcategoría no encontrada"}` |
| 404 | allergen_id no existe | `{"detail": "Alérgeno no encontrado", "id": 99}` |

---

### HU-PROD-004: Actualizar Producto

```yaml
id: HU-PROD-004
titulo: Modificar Producto
endpoint: PATCH /api/admin/products/{product_id}
roles_permitidos: [ADMIN, MANAGER]
websocket_event: ENTITY_UPDATED
```

#### Request Schema (Parcial)
```json
{
  "name": "string (optional)",
  "description": "string | null (optional)",
  "image": "string | null (optional)",
  "base_price_cents": "integer (optional)",
  "branch_prices": [...],
  "allergen_ids": [...],
  "allergens_detailed": [...]
}
```

**Nota**: `subcategory_id` NO se puede cambiar.

#### Comportamiento de branch_prices
- Si se proporciona: **MERGE** con existentes
- Para eliminar un precio: omitir del array
- Para agregar: incluir nuevo branch_id

---

### HU-PROD-005: Eliminar Producto

```yaml
id: HU-PROD-005
titulo: Eliminar Producto (Soft Delete)
endpoint: DELETE /api/admin/products/{product_id}
roles_permitidos: [ADMIN, MANAGER]
websocket_event: ENTITY_DELETED
```

#### Comportamiento Cascade
```
Product (soft delete)
  └── BranchProduct (soft delete)
  └── ProductAllergen (soft delete)
  └── ProductIngredient (soft delete)
```

---

### HU-PROD-006: Restaurar Producto

```yaml
id: HU-PROD-006
titulo: Restaurar Producto Eliminado
endpoint: POST /api/admin/products/{product_id}/restore
roles_permitidos: [ADMIN]
websocket_event: ENTITY_UPDATED
```

---

### HU-PROD-007: Actualizar Disponibilidad por Sucursal

```yaml
id: HU-PROD-007
titulo: Cambiar Disponibilidad de Producto en Sucursal
endpoint: PATCH /api/admin/products/{product_id}/availability
roles_permitidos: [ADMIN, MANAGER, KITCHEN]
websocket_event: ENTITY_UPDATED
```

#### Request Schema
```json
{
  "branch_id": "integer (required)",
  "is_available": "boolean (required)"
}
```

#### Caso de Uso
- Cocina puede marcar un producto como "agotado" temporalmente
- No requiere permisos de edición completa

---

### HU-PROD-008: Actualizar Precio por Sucursal

```yaml
id: HU-PROD-008
titulo: Modificar Precio de Producto en Sucursal
endpoint: PATCH /api/admin/products/{product_id}/price
roles_permitidos: [ADMIN, MANAGER]
websocket_event: ENTITY_UPDATED
```

#### Request Schema
```json
{
  "branch_id": "integer (required)",
  "price_cents": "integer (required, > 0)"
}
```

---

### HU-PROD-009: Gestión de Alérgenos de Producto

```yaml
id: HU-PROD-009
titulo: Asignar Alérgenos a Producto
endpoint: PUT /api/admin/products/{product_id}/allergens
roles_permitidos: [ADMIN, MANAGER]
websocket_event: ENTITY_UPDATED
```

#### Request Schema
```json
{
  "allergens": [
    {
      "allergen_id": "integer",
      "presence_type": "CONTAINS | MAY_CONTAIN | TRACE",
      "risk_level": "HIGH | MEDIUM | LOW"
    }
  ]
}
```

#### Presencia y Riesgo

| presence_type | Significado |
|---------------|-------------|
| CONTAINS | Contiene directamente el alérgeno |
| MAY_CONTAIN | Puede contener por contaminación cruzada |
| TRACE | Trazas mínimas posibles |

| risk_level | Significado |
|------------|-------------|
| HIGH | Cantidad significativa |
| MEDIUM | Cantidad moderada |
| LOW | Cantidad mínima |

---

### HU-PROD-010 a HU-PROD-012

- **HU-PROD-010**: PUT /{id}/ingredients - Gestión de ingredientes
- **HU-PROD-011**: PUT /{id}/dietary-flags - Banderas dietéticas
- **HU-PROD-012**: GET /search - Búsqueda avanzada con filtros

---

## 6. GESTIÓN DE ALÉRGENOS

### HU-ALRG-001: Listar Alérgenos

```yaml
id: HU-ALRG-001
titulo: Obtener Lista de Alérgenos
endpoint: GET /api/admin/allergens
roles_permitidos: [ADMIN, MANAGER, KITCHEN, WAITER, DINER]
servicio: rest_api/services/domain/allergen_service.py::AllergenService
```

#### Response Schema (200 OK)
```json
{
  "items": [
    {
      "id": "integer",
      "name": "string",
      "icon": "string | null",
      "description": "string | null",
      "severity_default": "HIGH | MEDIUM | LOW",
      "cross_reactions": [
        {
          "related_allergen_id": "integer",
          "related_allergen_name": "string",
          "reaction_probability": "HIGH | MEDIUM | LOW"
        }
      ],
      "is_active": "boolean"
    }
  ],
  "total": "integer"
}
```

#### Modelo de Datos
```sql
-- Allergen
id: BIGINT PRIMARY KEY
name: VARCHAR(100) NOT NULL UNIQUE
icon: VARCHAR(100)  -- Emoji o URL
description: TEXT
severity_default: VARCHAR(20) DEFAULT 'HIGH'
tenant_id: BIGINT REFERENCES tenant(id)  -- NULL = global
is_active: BOOLEAN DEFAULT true

-- AllergenCrossReaction (self-referential M:N)
id: BIGINT PRIMARY KEY
allergen_id: BIGINT REFERENCES allergen(id)
related_allergen_id: BIGINT REFERENCES allergen(id)
reaction_probability: VARCHAR(20)  -- HIGH, MEDIUM, LOW
CHECK(allergen_id != related_allergen_id)
UNIQUE(allergen_id, related_allergen_id)
```

#### Alérgenos Predefinidos (Seed)
| ID | Nombre | Icono |
|----|--------|-------|
| 1 | Gluten | 🌾 |
| 2 | Lácteos | 🥛 |
| 3 | Huevo | 🥚 |
| 4 | Maní | 🥜 |
| 5 | Frutos Secos | 🌰 |
| 6 | Soja | 🫘 |
| 7 | Pescado | 🐟 |
| 8 | Mariscos | 🦐 |
| 9 | Sésamo | 🫛 |
| 10 | Mostaza | 🌿 |
| 11 | Apio | 🥬 |
| 12 | Sulfitos | 🍷 |
| 13 | Moluscos | 🦪 |
| 14 | Lupino | 🌱 |

---

### HU-ALRG-002 a HU-ALRG-008

- **HU-ALRG-002**: GET /{id} - Ver detalle con cross-reactions
- **HU-ALRG-003**: POST - Crear alérgeno custom
- **HU-ALRG-004**: PATCH /{id} - Actualizar
- **HU-ALRG-005**: DELETE /{id} - Soft delete
- **HU-ALRG-006**: POST /{id}/restore - Restaurar
- **HU-ALRG-007**: PUT /{id}/cross-reactions - Definir reacciones cruzadas
- **HU-ALRG-008**: GET /products-containing/{id} - Productos que contienen

---

## 7. GESTIÓN DE SUCURSALES

### HU-BRANCH-001: Listar Sucursales

```yaml
id: HU-BRANCH-001
titulo: Obtener Lista de Sucursales
endpoint: GET /api/admin/branches
roles_permitidos: [ADMIN, MANAGER]
servicio: rest_api/services/domain/branch_service.py::BranchService
```

#### Response Schema (200 OK)
```json
{
  "items": [
    {
      "id": "integer",
      "name": "string",
      "slug": "string (unique, URL-safe)",
      "address": "string | null",
      "phone": "string | null",
      "timezone": "string (default: America/Santiago)",
      "is_active": "boolean",
      "sectors_count": "integer",
      "tables_count": "integer"
    }
  ],
  "total": "integer"
}
```

#### Modelo de Datos
```sql
-- Branch
id: BIGINT PRIMARY KEY
name: VARCHAR(100) NOT NULL
slug: VARCHAR(100) NOT NULL  -- Para URLs: "sucursal-centro"
address: VARCHAR(500)
phone: VARCHAR(50)
timezone: VARCHAR(50) DEFAULT 'America/Santiago'
tenant_id: BIGINT NOT NULL REFERENCES tenant(id)
is_active: BOOLEAN DEFAULT true
UNIQUE(tenant_id, slug)
```

### HU-BRANCH-002 a HU-BRANCH-006
- **HU-BRANCH-002**: GET /{id} - Ver detalle con sectores y mesas
- **HU-BRANCH-003**: POST - Crear sucursal (ADMIN only)
- **HU-BRANCH-004**: PATCH /{id} - Actualizar
- **HU-BRANCH-005**: DELETE /{id} - Soft delete (cascade sectores→mesas)
- **HU-BRANCH-006**: POST /{id}/restore - Restaurar

---

## 8. GESTIÓN DE SECTORES

### HU-SECTOR-001: Listar Sectores

```yaml
id: HU-SECTOR-001
titulo: Obtener Sectores de Sucursal
endpoint: GET /api/admin/sectors
roles_permitidos: [ADMIN, MANAGER]
servicio: rest_api/services/domain/sector_service.py::SectorService
```

#### Query Parameters
| Parámetro | Tipo | Descripción |
|-----------|------|-------------|
| branch_id | integer | Filtrar por sucursal (requerido para MANAGER) |

#### Response Schema (200 OK)
```json
{
  "items": [
    {
      "id": "integer",
      "name": "string",
      "branch_id": "integer",
      "branch_name": "string",
      "tables_count": "integer",
      "assigned_waiters": [
        {
          "user_id": "integer",
          "user_name": "string",
          "assignment_date": "date"
        }
      ],
      "is_active": "boolean"
    }
  ]
}
```

#### Modelo de Datos
```sql
-- BranchSector
id: BIGINT PRIMARY KEY
name: VARCHAR(100) NOT NULL
branch_id: BIGINT NOT NULL REFERENCES branch(id)
tenant_id: BIGINT NOT NULL REFERENCES tenant(id)
is_active: BOOLEAN DEFAULT true
UNIQUE(branch_id, name)

-- WaiterSectorAssignment (asignaciones diarias)
id: BIGINT PRIMARY KEY
user_id: BIGINT REFERENCES user(id)
sector_id: BIGINT REFERENCES branch_sector(id)
assignment_date: DATE NOT NULL
tenant_id: BIGINT NOT NULL
UNIQUE(user_id, sector_id, assignment_date)
```

### HU-SECTOR-002 a HU-SECTOR-005
- **HU-SECTOR-002**: GET /{id} - Ver detalle
- **HU-SECTOR-003**: POST - Crear sector
- **HU-SECTOR-004**: PATCH /{id} - Actualizar
- **HU-SECTOR-005**: DELETE /{id} - Soft delete (cascade mesas)

---

## 9. GESTIÓN DE MESAS

### HU-TABLE-001: Listar Mesas

```yaml
id: HU-TABLE-001
titulo: Obtener Mesas de Sucursal
endpoint: GET /api/admin/tables
roles_permitidos: [ADMIN, MANAGER, WAITER]
servicio: rest_api/services/domain/table_service.py::TableService
```

#### Query Parameters
| Parámetro | Tipo | Descripción |
|-----------|------|-------------|
| branch_id | integer | Filtrar por sucursal |
| sector_id | integer | Filtrar por sector |
| status | string | libre, ocupada, reservada |

#### Response Schema (200 OK)
```json
{
  "items": [
    {
      "id": "integer",
      "code": "string (alphanumeric, e.g. INT-01)",
      "capacity": "integer",
      "sector_id": "integer",
      "sector_name": "string",
      "branch_id": "integer",
      "branch_name": "string",
      "status": "libre | ocupada | reservada",
      "current_session_id": "integer | null",
      "diners_count": "integer",
      "has_pending_rounds": "boolean",
      "is_active": "boolean"
    }
  ]
}
```

#### Modelo de Datos
```sql
-- Table
id: BIGINT PRIMARY KEY
code: VARCHAR(20) NOT NULL  -- "INT-01", "TER-02"
capacity: INTEGER DEFAULT 4
sector_id: BIGINT NOT NULL REFERENCES branch_sector(id)
tenant_id: BIGINT NOT NULL REFERENCES tenant(id)
is_active: BOOLEAN DEFAULT true
-- code NO es único globalmente, solo por branch
UNIQUE(sector_id, code)  -- via sector → branch
```

#### Notas Importantes
- **code** es alfanumérico para QR codes (e.g., "INT-01", "TER-02")
- **code NO es único globalmente** - cada branch puede tener "INT-01"
- Para obtener mesa por código: `/api/tables/code/{code}/session?branch_slug={slug}`

### HU-TABLE-002 a HU-TABLE-008
- **HU-TABLE-002**: GET /{id} - Ver detalle con sesión activa
- **HU-TABLE-003**: POST - Crear mesa
- **HU-TABLE-004**: PATCH /{id} - Actualizar
- **HU-TABLE-005**: DELETE /{id} - Soft delete
- **HU-TABLE-006**: POST /{id}/restore - Restaurar
- **HU-TABLE-007**: PATCH /{id}/status - Cambiar estado
- **HU-TABLE-008**: GET /{id}/qr - Generar código QR

---

## 10. SESIONES DE MESA

### HU-SESSION-001: Crear/Obtener Sesión por ID

```yaml
id: HU-SESSION-001
titulo: Iniciar o Obtener Sesión de Mesa
endpoint: POST /api/tables/{table_id}/session
roles_permitidos: [ADMIN, MANAGER, WAITER, DINER (con X-Table-Token)]
```

#### Response Schema (200/201)
```json
{
  "session_id": "integer",
  "table_id": "integer",
  "table_code": "string",
  "branch_id": "integer",
  "branch_slug": "string",
  "status": "OPEN | PAYING | CLOSED",
  "started_at": "datetime",
  "table_token": "string (HMAC token for diners)",
  "diners": [
    {
      "id": "integer",
      "device_id": "string | null",
      "name": "string | null",
      "joined_at": "datetime"
    }
  ]
}
```

#### Modelo de Datos
```sql
-- TableSession
id: BIGINT PRIMARY KEY
table_id: BIGINT NOT NULL REFERENCES table(id)
status: VARCHAR(20) DEFAULT 'OPEN'  -- OPEN, PAYING, CLOSED
started_at: TIMESTAMP DEFAULT now()
closed_at: TIMESTAMP
tenant_id: BIGINT NOT NULL

-- Diner (comensales en sesión)
id: BIGINT PRIMARY KEY
session_id: BIGINT NOT NULL REFERENCES table_session(id)
device_id: VARCHAR(100)  -- UUID from localStorage
device_fingerprint: VARCHAR(255)
name: VARCHAR(100)
customer_id: BIGINT REFERENCES customer(id)  -- opcional, para fidelización
joined_at: TIMESTAMP DEFAULT now()
tenant_id: BIGINT NOT NULL
```

### HU-SESSION-002: Crear/Obtener Sesión por Código

```yaml
id: HU-SESSION-002
titulo: Iniciar Sesión por Código de Mesa (QR)
endpoint: POST /api/tables/code/{code}/session
roles_permitidos: [Público con branch_slug]
```

#### Query Parameters
| Parámetro | Tipo | Requerido | Descripción |
|-----------|------|-----------|-------------|
| branch_slug | string | Sí | Slug de la sucursal (e.g., "sucursal-centro") |

#### Lógica de Negocio
1. **Buscar branch** por slug
2. **Buscar table** por code + branch_id
3. **Si sesión OPEN existe**: retornarla
4. **Si no**: crear nueva sesión
5. **Generar table_token** HMAC para autenticación de diners
6. **Publicar** WebSocket TABLE_SESSION_STARTED

### HU-SESSION-003 a HU-SESSION-005
- **HU-SESSION-003**: GET /{session_id} - Ver detalle completo con rounds
- **HU-SESSION-004**: PATCH /{session_id}/status - Cambiar estado (OPEN→PAYING→CLOSED)
- **HU-SESSION-005**: POST /{session_id}/close - Cerrar sesión

---

## 11. OPERACIONES DE CLIENTE (DINER)

### HU-DINER-001: Registrar Diner en Sesión

```yaml
id: HU-DINER-001
titulo: Unirse a Mesa como Comensal
endpoint: POST /api/diner/register
autenticacion: X-Table-Token header
```

#### Request Schema
```json
{
  "device_id": "string (required, UUID)",
  "device_fingerprint": "string (optional)",
  "name": "string (optional)"
}
```

#### Response Schema (201 Created)
```json
{
  "diner_id": "integer",
  "session_id": "integer",
  "table_code": "string",
  "branch_name": "string",
  "name": "string | null",
  "joined_at": "datetime"
}
```

### HU-DINER-002: Ver Menú de Sucursal

```yaml
id: HU-DINER-002
titulo: Obtener Menú Público
endpoint: GET /api/public/menu/{branch_slug}
autenticacion: Ninguna (público)
```

#### Response Schema (200 OK)
```json
{
  "branch": {
    "id": "integer",
    "name": "string",
    "slug": "string"
  },
  "categories": [
    {
      "id": "integer",
      "name": "string",
      "image": "string | null",
      "subcategories": [
        {
          "id": "integer",
          "name": "string",
          "products": [
            {
              "id": "integer",
              "name": "string",
              "description": "string | null",
              "image": "string | null",
              "price_cents": "integer",
              "is_available": "boolean",
              "allergens": [...]
            }
          ]
        }
      ]
    }
  ]
}
```

### HU-DINER-003: Proponer Round (Pedido)

```yaml
id: HU-DINER-003
titulo: Proponer Envío de Pedido (Confirmación Grupal)
endpoint: POST /api/diner/rounds/propose
autenticacion: X-Table-Token
```

#### Request Schema
```json
{
  "session_id": "integer",
  "items": [
    {
      "product_id": "integer",
      "quantity": "integer (1-99)",
      "notes": "string | null",
      "diner_id": "integer (quien ordena)"
    }
  ]
}
```

#### Lógica de Confirmación Grupal
1. **Diner propone** envío de pedido
2. **Todos los diners** reciben notificación WebSocket
3. **Cada diner confirma** vía HU-DINER-004
4. **Cuando todos confirman**: round se envía automáticamente
5. **Timeout 5 minutos**: propuesta expira

### HU-DINER-004: Confirmar Ready para Round

```yaml
id: HU-DINER-004
titulo: Confirmar Listo para Enviar Pedido
endpoint: POST /api/diner/rounds/{round_id}/confirm
autenticacion: X-Table-Token
```

### HU-DINER-005: Enviar Round (sin confirmación grupal)

```yaml
id: HU-DINER-005
titulo: Enviar Pedido Directamente
endpoint: POST /api/diner/rounds
autenticacion: X-Table-Token
websocket_event: ROUND_SUBMITTED
```

### HU-DINER-006 a HU-DINER-010: Preferencias Implícitas

```yaml
# HU-DINER-006: Sincronizar preferencias de filtros
endpoint: PATCH /api/diner/preferences
autenticacion: X-Table-Token

# HU-DINER-007: Cargar preferencias guardadas
endpoint: GET /api/diner/device/{device_id}/preferences

# HU-DINER-008: Historial de visitas
endpoint: GET /api/diner/device/{device_id}/history

# HU-DINER-009: Solicitar cuenta
endpoint: POST /api/diner/check/request
websocket_event: CHECK_REQUESTED

# HU-DINER-010: Llamar mesero
endpoint: POST /api/diner/service-call
websocket_event: SERVICE_CALL_CREATED
```

### HU-DINER-011 a HU-DINER-015: Fidelización (Customer)

```yaml
# HU-DINER-011: Registrar cliente con consentimiento
endpoint: POST /api/customer/register
# Requiere: email, consentimiento GDPR explícito

# HU-DINER-012: Reconocer cliente por device
endpoint: GET /api/customer/recognize

# HU-DINER-013: Ver perfil de cliente
endpoint: GET /api/customer/me

# HU-DINER-014: Actualizar perfil
endpoint: PATCH /api/customer/me

# HU-DINER-015: Obtener sugerencias personalizadas
endpoint: GET /api/customer/suggestions
```

---

## 12. OPERACIONES DE COCINA

### HU-KITCHEN-001: Ver Rounds Pendientes

```yaml
id: HU-KITCHEN-001
titulo: Listar Rounds en Cocina
endpoint: GET /api/kitchen/rounds
roles_permitidos: [KITCHEN, ADMIN, MANAGER]
autenticacion: Bearer Token (JWT)
```

#### Query Parameters
| Parámetro | Tipo | Descripción |
|-----------|------|-------------|
| branch_id | integer | Sucursal (requerido) |
| status | string | IN_KITCHEN, READY |

#### Response Schema (200 OK)
```json
{
  "items": [
    {
      "id": "integer",
      "session_id": "integer",
      "table_code": "string",
      "sector_name": "string",
      "status": "IN_KITCHEN | READY",
      "created_at": "datetime",
      "items": [
        {
          "id": "integer",
          "product_name": "string",
          "quantity": "integer",
          "notes": "string | null",
          "diner_name": "string | null"
        }
      ]
    }
  ]
}
```

### HU-KITCHEN-002: Avanzar Estado de Round

```yaml
id: HU-KITCHEN-002
titulo: Marcar Round como Listo
endpoint: PATCH /api/kitchen/rounds/{round_id}/status
roles_permitidos: [KITCHEN]
websocket_event: ROUND_READY
```

#### Request Schema
```json
{
  "status": "READY"
}
```

#### Flujo de Estados (Restricciones por Rol)
```
PENDING → IN_KITCHEN  (ADMIN/MANAGER only)
IN_KITCHEN → READY    (KITCHEN only)
READY → SERVED        (ADMIN/MANAGER/WAITER)
```

### HU-KITCHEN-003 a HU-KITCHEN-008: Tickets de Cocina

```yaml
# HU-KITCHEN-003: Listar tickets
endpoint: GET /api/kitchen/tickets

# HU-KITCHEN-004: Ver ticket detallado
endpoint: GET /api/kitchen/tickets/{ticket_id}

# HU-KITCHEN-005: Iniciar preparación
endpoint: PATCH /api/kitchen/tickets/{ticket_id}/start
websocket_event: TICKET_IN_PROGRESS

# HU-KITCHEN-006: Marcar item como listo
endpoint: PATCH /api/kitchen/tickets/{ticket_id}/items/{item_id}/ready

# HU-KITCHEN-007: Marcar ticket completo
endpoint: PATCH /api/kitchen/tickets/{ticket_id}/complete
websocket_event: TICKET_READY

# HU-KITCHEN-008: Marcar entregado
endpoint: PATCH /api/kitchen/tickets/{ticket_id}/delivered
websocket_event: TICKET_DELIVERED
```

---

## 13. OPERACIONES DE MESERO

### HU-WAITER-001: Ver Mesas Asignadas

```yaml
id: HU-WAITER-001
titulo: Listar Mesas del Mesero
endpoint: GET /api/waiter/tables
roles_permitidos: [WAITER, ADMIN, MANAGER]
autenticacion: Bearer Token (JWT)
```

#### Query Parameters
| Parámetro | Tipo | Descripción |
|-----------|------|-------------|
| branch_id | integer | Sucursal (requerido) |

#### Filtrado por Sectores Asignados
- **WAITER**: Solo ve mesas de sectores asignados para HOY
- **ADMIN/MANAGER**: Ve todas las mesas de la sucursal

#### Response Schema (200 OK)
```json
{
  "items": [
    {
      "id": "integer",
      "code": "string",
      "sector_name": "string",
      "status": "libre | ocupada",
      "session_id": "integer | null",
      "diners_count": "integer",
      "open_rounds": "integer",
      "has_new_order": "boolean",
      "has_pending_call": "boolean"
    }
  ]
}
```

### HU-WAITER-002: Ver Detalle de Sesión

```yaml
id: HU-WAITER-002
titulo: Obtener Detalle de Sesión de Mesa
endpoint: GET /api/waiter/tables/{table_id}/session
roles_permitidos: [WAITER, ADMIN, MANAGER]
```

#### Response Schema (200 OK)
```json
{
  "session_id": "integer",
  "table_code": "string",
  "status": "OPEN | PAYING",
  "started_at": "datetime",
  "diners": [...],
  "rounds": [
    {
      "id": "integer",
      "status": "PENDING | IN_KITCHEN | READY | SERVED",
      "created_at": "datetime",
      "items": [
        {
          "product_name": "string",
          "quantity": "integer",
          "category_name": "string",
          "price_cents": "integer"
        }
      ]
    }
  ],
  "total_cents": "integer"
}
```

### HU-WAITER-003: Menú Compacto para Comanda

```yaml
id: HU-WAITER-003
titulo: Obtener Menú sin Imágenes (Comanda Rápida)
endpoint: GET /api/waiter/branches/{branch_id}/menu
roles_permitidos: [WAITER, ADMIN, MANAGER]
```

#### Response Schema
- Igual que menú público pero SIN campo image
- Optimizado para carga rápida en dispositivo móvil

### HU-WAITER-004: Enviar Round (Comanda Rápida)

```yaml
id: HU-WAITER-004
titulo: Crear Pedido desde Mesero
endpoint: POST /api/waiter/sessions/{session_id}/rounds
roles_permitidos: [WAITER, ADMIN, MANAGER]
websocket_event: ROUND_SUBMITTED
```

#### Request Schema
```json
{
  "items": [
    {
      "product_id": "integer",
      "quantity": "integer",
      "notes": "string | null"
    }
  ]
}
```

### HU-WAITER-005 a HU-WAITER-010

```yaml
# HU-WAITER-005: Avanzar round a cocina
endpoint: PATCH /api/waiter/rounds/{round_id}/to-kitchen
websocket_event: ROUND_IN_KITCHEN

# HU-WAITER-006: Marcar round como servido
endpoint: PATCH /api/waiter/rounds/{round_id}/served
websocket_event: ROUND_SERVED

# HU-WAITER-007: Atender service call
endpoint: PATCH /api/waiter/service-calls/{call_id}/ack
websocket_event: SERVICE_CALL_ACKED

# HU-WAITER-008: Cerrar service call
endpoint: PATCH /api/waiter/service-calls/{call_id}/close
websocket_event: SERVICE_CALL_CLOSED

# HU-WAITER-009: Solicitar cuenta para mesa
endpoint: POST /api/waiter/tables/{table_id}/request-check

# HU-WAITER-010: Cerrar mesa
endpoint: POST /api/waiter/tables/{table_id}/close
websocket_event: TABLE_CLEARED
```

---

## 14. PAGOS Y FACTURACIÓN

### HU-BILLING-001: Solicitar Cuenta

```yaml
id: HU-BILLING-001
titulo: Solicitar Cuenta de Mesa
endpoint: POST /api/billing/check/request
roles_permitidos: [DINER, WAITER, ADMIN, MANAGER]
autenticacion: X-Table-Token o Bearer Token
websocket_event: CHECK_REQUESTED
rate_limit: 10/minuto
```

#### Request Schema
```json
{
  "session_id": "integer"
}
```

#### Response Schema (201 Created)
```json
{
  "check_id": "integer",
  "session_id": "integer",
  "total_cents": "integer",
  "items": [
    {
      "product_name": "string",
      "quantity": "integer",
      "unit_price_cents": "integer",
      "subtotal_cents": "integer"
    }
  ],
  "status": "PENDING"
}
```

### HU-BILLING-002: Pago en Efectivo

```yaml
id: HU-BILLING-002
titulo: Registrar Pago en Efectivo
endpoint: POST /api/billing/cash/pay
roles_permitidos: [WAITER, ADMIN, MANAGER]
websocket_event: PAYMENT_APPROVED
rate_limit: 20/minuto
```

#### Request Schema
```json
{
  "check_id": "integer",
  "amount_cents": "integer",
  "payment_method": "CASH"
}
```

### HU-BILLING-003: Crear Preferencia Mercado Pago

```yaml
id: HU-BILLING-003
titulo: Generar Link de Pago MP
endpoint: POST /api/billing/mercadopago/preference
roles_permitidos: [DINER]
autenticacion: X-Table-Token
rate_limit: 5/minuto
```

#### Response Schema (201 Created)
```json
{
  "preference_id": "string",
  "init_point": "string (URL para pagar)",
  "sandbox_init_point": "string"
}
```

### HU-BILLING-004: Webhook Mercado Pago

```yaml
id: HU-BILLING-004
titulo: Recibir Notificación de Pago MP
endpoint: POST /api/billing/webhook
autenticacion: HMAC signature validation
```

#### Lógica de Negocio
1. **Validar firma** HMAC del webhook
2. **Obtener payment** de MP API
3. **Si approved**: crear Payment, Allocation FIFO
4. **Publicar** PAYMENT_APPROVED o PAYMENT_FAILED
5. **Circuit Breaker**: protege contra fallos de MP API

### HU-BILLING-005 a HU-BILLING-010

```yaml
# HU-BILLING-005: Ver estado de cuenta
endpoint: GET /api/billing/check/{check_id}

# HU-BILLING-006: Listar pagos de sesión
endpoint: GET /api/billing/session/{session_id}/payments

# HU-BILLING-007: División de cuenta
endpoint: POST /api/billing/check/{check_id}/split

# HU-BILLING-008: Propina
endpoint: POST /api/billing/tip

# HU-BILLING-009: Reembolso
endpoint: POST /api/billing/refund

# HU-BILLING-010: Reportes de ventas
endpoint: GET /api/billing/reports
```

---

## 15. GESTIÓN DE PROMOCIONES

### HU-PROMO-001: Listar Promociones

```yaml
id: HU-PROMO-001
titulo: Obtener Promociones Activas
endpoint: GET /api/admin/promotions
roles_permitidos: [ADMIN, MANAGER]
servicio: rest_api/services/domain/promotion_service.py
```

#### Response Schema (200 OK)
```json
{
  "items": [
    {
      "id": "integer",
      "name": "string",
      "description": "string | null",
      "discount_type": "PERCENTAGE | FIXED_AMOUNT",
      "discount_value": "integer",
      "start_date": "date",
      "end_date": "date | null",
      "branches": [
        {"branch_id": "integer", "branch_name": "string"}
      ],
      "items": [
        {"product_id": "integer", "product_name": "string"}
      ],
      "is_active": "boolean"
    }
  ]
}
```

#### Modelo de Datos
```sql
-- Promotion
id: BIGINT PRIMARY KEY
name: VARCHAR(200) NOT NULL
description: TEXT
discount_type: VARCHAR(20)  -- PERCENTAGE, FIXED_AMOUNT
discount_value: INTEGER NOT NULL
start_date: DATE NOT NULL
end_date: DATE
tenant_id: BIGINT NOT NULL
is_active: BOOLEAN DEFAULT true

-- PromotionBranch (M:N)
promotion_id: BIGINT REFERENCES promotion(id)
branch_id: BIGINT REFERENCES branch(id)

-- PromotionItem (M:N)
promotion_id: BIGINT REFERENCES promotion(id)
product_id: BIGINT REFERENCES product(id)
```

### HU-PROMO-002 a HU-PROMO-006
- **HU-PROMO-002**: GET /{id} - Ver detalle
- **HU-PROMO-003**: POST - Crear promoción
- **HU-PROMO-004**: PATCH /{id} - Actualizar
- **HU-PROMO-005**: DELETE /{id} - Soft delete
- **HU-PROMO-006**: POST /{id}/restore - Restaurar

---

## 16. CONTENIDO Y RECETAS

### HU-RECIPE-001: Listar Recetas

```yaml
id: HU-RECIPE-001
titulo: Obtener Fichas Técnicas de Cocina
endpoint: GET /api/recipes
roles_permitidos: [KITCHEN, ADMIN, MANAGER]
```

#### Response Schema (200 OK)
```json
{
  "items": [
    {
      "id": "integer",
      "name": "string",
      "description": "string | null",
      "preparation_steps": "string[]",
      "cooking_time_minutes": "integer | null",
      "servings": "integer | null",
      "linked_product_id": "integer | null",
      "allergens": [...],
      "is_active": "boolean"
    }
  ]
}
```

### HU-RECIPE-002 a HU-RECIPE-008

```yaml
# HU-RECIPE-002: Ver detalle de receta
endpoint: GET /api/recipes/{recipe_id}

# HU-RECIPE-003: Crear receta
endpoint: POST /api/recipes

# HU-RECIPE-004: Actualizar receta
endpoint: PATCH /api/recipes/{recipe_id}

# HU-RECIPE-005: Eliminar receta
endpoint: DELETE /api/recipes/{recipe_id}

# HU-RECIPE-006: Vincular receta a producto
endpoint: POST /api/recipes/{recipe_id}/link-product

# HU-RECIPE-007: Ingestar receta en RAG
endpoint: POST /api/recipes/{recipe_id}/ingest

# HU-RECIPE-008: Sincronizar alérgenos producto→receta
endpoint: POST /api/recipes/{recipe_id}/sync-allergens
```

---

## 17. EXCLUSIONES DE CATEGORÍA

### HU-EXCL-001: Listar Exclusiones

```yaml
id: HU-EXCL-001
titulo: Obtener Exclusiones por Sucursal
endpoint: GET /api/admin/exclusions
roles_permitidos: [ADMIN, MANAGER]
```

#### Descripción
Permite ocultar categorías/subcategorías específicas en sucursales.
Ejemplo: "Sucursal Norte no muestra Bebidas Alcohólicas"

#### Response Schema (200 OK)
```json
{
  "category_exclusions": [
    {
      "branch_id": "integer",
      "branch_name": "string",
      "category_id": "integer",
      "category_name": "string"
    }
  ],
  "subcategory_exclusions": [...]
}
```

### HU-EXCL-002 a HU-EXCL-005
- **HU-EXCL-002**: POST /categories - Crear exclusión de categoría
- **HU-EXCL-003**: DELETE /categories/{id} - Eliminar exclusión
- **HU-EXCL-004**: POST /subcategories - Crear exclusión de subcategoría
- **HU-EXCL-005**: DELETE /subcategories/{id} - Eliminar exclusión

---

## 18. ASIGNACIONES DE MESERO

### HU-ASSIGN-001: Ver Asignaciones del Día

```yaml
id: HU-ASSIGN-001
titulo: Obtener Asignaciones de Sectores
endpoint: GET /api/admin/assignments
roles_permitidos: [ADMIN, MANAGER]
```

#### Query Parameters
| Parámetro | Tipo | Default | Descripción |
|-----------|------|---------|-------------|
| branch_id | integer | requerido | Sucursal |
| date | date | hoy | Fecha de asignación |

#### Response Schema (200 OK)
```json
{
  "date": "date",
  "branch_id": "integer",
  "assignments": [
    {
      "sector_id": "integer",
      "sector_name": "string",
      "waiters": [
        {
          "user_id": "integer",
          "user_name": "string",
          "email": "string"
        }
      ]
    }
  ]
}
```

### HU-ASSIGN-002 a HU-ASSIGN-005

```yaml
# HU-ASSIGN-002: Crear asignación
endpoint: POST /api/admin/assignments
# Request: { user_id, sector_id, date }

# HU-ASSIGN-003: Eliminar asignación
endpoint: DELETE /api/admin/assignments/{assignment_id}

# HU-ASSIGN-004: Asignación masiva
endpoint: POST /api/admin/assignments/bulk
# Request: { sector_id, user_ids: [], date }

# HU-ASSIGN-005: Copiar asignaciones de otro día
endpoint: POST /api/admin/assignments/copy
# Request: { from_date, to_date, branch_id }
```

---

## 19. AUDITORÍA Y REPORTES

### HU-AUDIT-001: Ver Logs de Auditoría

```yaml
id: HU-AUDIT-001
titulo: Consultar Historial de Cambios
endpoint: GET /api/admin/audit
roles_permitidos: [ADMIN]
```

#### Query Parameters
| Parámetro | Tipo | Descripción |
|-----------|------|-------------|
| entity_type | string | User, Product, Category, etc. |
| entity_id | integer | ID específico |
| user_id | integer | Filtrar por quien hizo el cambio |
| action | string | CREATE, UPDATE, DELETE, RESTORE |
| from_date | datetime | Desde |
| to_date | datetime | Hasta |
| limit | integer | Max 500 |

#### Response Schema (200 OK)
```json
{
  "items": [
    {
      "id": "integer",
      "entity_type": "string",
      "entity_id": "integer",
      "action": "CREATE | UPDATE | DELETE | RESTORE",
      "user_id": "integer",
      "user_email": "string",
      "changes": {
        "field_name": {
          "old": "valor anterior",
          "new": "valor nuevo"
        }
      },
      "created_at": "datetime"
    }
  ],
  "total": "integer"
}
```

#### Modelo de Datos
```sql
-- AuditLog
id: BIGINT PRIMARY KEY
entity_type: VARCHAR(100) NOT NULL
entity_id: BIGINT NOT NULL
action: VARCHAR(20) NOT NULL
user_id: BIGINT
user_email: VARCHAR(255)
changes: JSONB
ip_address: VARCHAR(45)
user_agent: TEXT
created_at: TIMESTAMP DEFAULT now()
tenant_id: BIGINT NOT NULL
INDEX idx_audit_entity (entity_type, entity_id)
INDEX idx_audit_tenant_date (tenant_id, created_at)
```

### HU-AUDIT-002 a HU-AUDIT-006

```yaml
# HU-AUDIT-002: Reporte de ventas
endpoint: GET /api/admin/reports/sales

# HU-AUDIT-003: Reporte de productos más vendidos
endpoint: GET /api/admin/reports/top-products

# HU-AUDIT-004: Reporte de meseros
endpoint: GET /api/admin/reports/waiters

# HU-AUDIT-005: Reporte de tiempos de cocina
endpoint: GET /api/admin/reports/kitchen-times

# HU-AUDIT-006: Exportar a CSV/Excel
endpoint: GET /api/admin/reports/export
```

---

## 20. MENÚ PÚBLICO

### HU-PUBLIC-001: Ver Catálogo Público

```yaml
id: HU-PUBLIC-001
titulo: Obtener Menú sin Autenticación
endpoint: GET /api/public/menu/{branch_slug}
autenticacion: Ninguna
```

(Documentado en HU-DINER-002)

### HU-PUBLIC-002 a HU-PUBLIC-005

```yaml
# HU-PUBLIC-002: Información de sucursal
endpoint: GET /api/public/branch/{branch_slug}

# HU-PUBLIC-003: Detalle de producto
endpoint: GET /api/public/products/{product_id}

# HU-PUBLIC-004: Buscar productos
endpoint: GET /api/public/search
# Query: q (término), branch_slug

# HU-PUBLIC-005: Alérgenos disponibles
endpoint: GET /api/public/allergens
```

---

## 21. SALUD Y MÉTRICAS

### HU-HEALTH-001: Health Check Básico

```yaml
id: HU-HEALTH-001
titulo: Verificar Estado del Servidor
endpoint: GET /api/health
autenticacion: Ninguna
```

#### Response Schema (200 OK)
```json
{
  "status": "healthy",
  "timestamp": "datetime"
}
```

### HU-HEALTH-002: Health Check Detallado

```yaml
id: HU-HEALTH-002
titulo: Estado Detallado con Dependencias
endpoint: GET /api/health/detailed
autenticacion: Ninguna (pero puede requerir en producción)
```

#### Response Schema (200 OK)
```json
{
  "status": "healthy | degraded | unhealthy",
  "timestamp": "datetime",
  "components": {
    "database": {
      "status": "healthy",
      "latency_ms": 5.2
    },
    "redis_async": {
      "status": "healthy",
      "latency_ms": 1.3,
      "pool_size": 50
    },
    "redis_sync": {
      "status": "healthy",
      "latency_ms": 0.8
    }
  }
}
```

### HU-HEALTH-003: Métricas Prometheus (WebSocket Gateway)

```yaml
id: HU-HEALTH-003
titulo: Métricas para Monitoreo
endpoint: GET /ws/metrics
servidor: ws_gateway (port 8001)
```

#### Response (text/plain)
```
# HELP wsgateway_connections_total Total WebSocket connections
wsgateway_connections_total 42
# HELP wsgateway_broadcasts_total Total broadcasts sent
wsgateway_broadcasts_total 1234
# HELP wsgateway_connections_rejected_total Rejected connections by reason
wsgateway_connections_rejected_total{reason="auth"} 5
wsgateway_connections_rejected_total{reason="rate_limit"} 2
```

---

## 22. GESTIÓN DE TENANT

### HU-TENANT-001: Ver Información del Tenant

```yaml
id: HU-TENANT-001
titulo: Obtener Configuración del Tenant
endpoint: GET /api/admin/tenant
roles_permitidos: [ADMIN]
```

#### Response Schema (200 OK)
```json
{
  "id": "integer",
  "name": "string",
  "slug": "string",
  "logo_url": "string | null",
  "primary_color": "string | null (hex)",
  "timezone": "string",
  "currency": "string (default: CLP)",
  "branches_count": "integer",
  "users_count": "integer",
  "created_at": "datetime"
}
```

---

## 23. RAG / CHATBOT

### HU-RAG-001: Consultar Chatbot

```yaml
id: HU-RAG-001
titulo: Hacer Pregunta al Asistente IA
endpoint: POST /api/rag/chat
roles_permitidos: [KITCHEN, ADMIN, MANAGER]
servicio: rest_api/services/rag/service.py
```

#### Request Schema
```json
{
  "question": "string (required)",
  "session_id": "string (optional, para contexto)"
}
```

#### Response Schema (200 OK)
```json
{
  "answer": "string",
  "sources": [
    {
      "document_id": "integer",
      "document_name": "string",
      "relevance_score": "float"
    }
  ],
  "session_id": "string"
}
```

### HU-RAG-002: Ingestar Documento

```yaml
id: HU-RAG-002
titulo: Agregar Documento a Base de Conocimiento
endpoint: POST /api/rag/documents
roles_permitidos: [ADMIN]
```

#### Request Schema
```json
{
  "title": "string",
  "content": "string",
  "document_type": "RECIPE | POLICY | FAQ | TRAINING"
}
```

### HU-RAG-003: Listar Documentos

```yaml
id: HU-RAG-003
titulo: Ver Documentos en Base de Conocimiento
endpoint: GET /api/rag/documents
roles_permitidos: [ADMIN]
```

---

## Anexo A: Eventos WebSocket

### Eventos de Rounds
| Evento | Trigger | Destinatarios |
|--------|---------|---------------|
| ROUND_SUBMITTED | Diner/Waiter envía pedido | Admin, Waiters (del sector) |
| ROUND_IN_KITCHEN | Admin avanza estado | Kitchen, Admin, Waiters |
| ROUND_READY | Kitchen marca listo | Waiters (del sector), Admin |
| ROUND_SERVED | Waiter entrega | Admin |
| ROUND_CANCELED | Admin cancela | Kitchen, Waiters, Diners |

### Eventos de Mesa
| Evento | Trigger | Destinatarios |
|--------|---------|---------------|
| TABLE_SESSION_STARTED | QR scan / nueva sesión | Admin, Waiters (del sector) |
| TABLE_STATUS_CHANGED | Cambio de estado | Admin, Waiters |
| TABLE_CLEARED | Mesa cerrada | Admin, Waiters |

### Eventos de Servicio
| Evento | Trigger | Destinatarios |
|--------|---------|---------------|
| SERVICE_CALL_CREATED | Diner llama mesero | Waiters (del sector) |
| SERVICE_CALL_ACKED | Waiter atiende | Diners (de la mesa) |
| SERVICE_CALL_CLOSED | Servicio completado | Admin |

### Eventos de Pago
| Evento | Trigger | Destinatarios |
|--------|---------|---------------|
| CHECK_REQUESTED | Solicitud de cuenta | Waiters, Admin |
| PAYMENT_APPROVED | Pago exitoso | Diners, Waiters, Admin |
| PAYMENT_REJECTED | Pago rechazado | Diners |
| PAYMENT_FAILED | Error en pago | Diners, Admin |

### Eventos de Admin
| Evento | Trigger | Destinatarios |
|--------|---------|---------------|
| ENTITY_CREATED | CRUD create | Admin channel |
| ENTITY_UPDATED | CRUD update | Admin channel |
| ENTITY_DELETED | CRUD delete | Admin channel |
| CASCADE_DELETE | Delete con dependencias | Admin channel |

---

## Anexo B: Estructura de Event Payload

```json
{
  "type": "ROUND_SUBMITTED",
  "tenant_id": 1,
  "branch_id": 1,
  "sector_id": 5,
  "entity_type": "Round",
  "entity_id": 123,
  "data": {
    "table_code": "INT-01",
    "items_count": 3,
    "total_cents": 4500
  },
  "timestamp": "2026-01-25T14:30:00Z"
}
```

---

## Anexo C: Códigos de Cierre WebSocket

| Código | Constante | Significado |
|--------|-----------|-------------|
| 1000 | NORMAL | Cierre normal |
| 1001 | GOING_AWAY | Servidor reiniciando |
| 1008 | POLICY_VIOLATION | Violación de política |
| 1009 | MESSAGE_TOO_BIG | Mensaje > 64KB |
| 4001 | AUTH_FAILED | Token inválido/expirado |
| 4003 | FORBIDDEN | Sin permisos o origin inválido |
| 4029 | RATE_LIMITED | Excedió límite de mensajes |

---

**Fin del Documento**

*Total: 152 Historias de Usuario*
*Versión: 2.0 - Detalle Técnico para IA*
*Fecha: 25 de Enero de 2026*
