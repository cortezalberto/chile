# Refactorización de Historias de Usuario

## Mapeo HU → PT con Gobernanza IA-Native

**Versión:** 1.0
**Fecha:** 25 de Enero de 2026
**Total de Historias:** 152
**Total de Policy Tickets:** 22

---

## Resumen Ejecutivo

Este documento refactoriza las 152 historias de usuario del backend, mapeándolas a sus Policy Tickets correspondientes y asignando niveles de autonomía para agentes de IA según el marco IA-Native.

### Distribución por Nivel de Riesgo

| Nivel | Autonomía IA | Policy Tickets | Historias | % |
|-------|--------------|----------------|-----------|---|
| CRÍTICO | análisis-solamente | 6 | 35 | 23% |
| ALTO | código-supervisado | 3 | 15 | 10% |
| MEDIO | código-con-review | 5 | 53 | 35% |
| BAJO | código-autónomo | 8 | 49 | 32% |
| **TOTAL** | - | **22** | **152** | **100%** |

---

## Matriz de Mapeo Completa

### Dominio CRÍTICO (35 HU)

| HU-ID | Título | PT-ID | Autonomía |
|-------|--------|-------|-----------|
| HU-AUTH-001 | Login de Personal | PT-AUTH-001 | análisis-solamente |
| HU-AUTH-002 | Refresh Token | PT-AUTH-001 | análisis-solamente |
| HU-AUTH-003 | Info Usuario Actual | PT-AUTH-001 | análisis-solamente |
| HU-AUTH-004 | Logout Global | PT-AUTH-001 | análisis-solamente |
| HU-AUTH-005 | Validación RBAC | PT-AUTH-001 | análisis-solamente |
| HU-STAFF-001 | Listar Personal | PT-STAFF-001 | análisis-solamente |
| HU-STAFF-002 | Ver Empleado | PT-STAFF-001 | análisis-solamente |
| HU-STAFF-003 | Crear Empleado | PT-STAFF-001 | análisis-solamente |
| HU-STAFF-004 | Actualizar Empleado | PT-STAFF-001 | análisis-solamente |
| HU-STAFF-005 | Eliminar Empleado | PT-STAFF-001 | análisis-solamente |
| HU-STAFF-006 | Restaurar Empleado | PT-STAFF-001 | análisis-solamente |
| HU-ALRG-001 | Listar Alérgenos | PT-ALLERGEN-001 | análisis-solamente |
| HU-ALRG-002 | Ver Alérgeno | PT-ALLERGEN-001 | análisis-solamente |
| HU-ALRG-003 | Crear Alérgeno | PT-ALLERGEN-001 | análisis-solamente |
| HU-ALRG-004 | Actualizar Alérgeno | PT-ALLERGEN-001 | análisis-solamente |
| HU-ALRG-005 | Eliminar Alérgeno | PT-ALLERGEN-001 | análisis-solamente |
| HU-ALRG-006 | Restaurar Alérgeno | PT-ALLERGEN-001 | análisis-solamente |
| HU-ALRG-007 | Cross-Reactions | PT-ALLERGEN-001 | análisis-solamente |
| HU-ALRG-008 | Productos con Alérgeno | PT-ALLERGEN-001 | análisis-solamente |
| HU-BILLING-001 | Solicitar Cuenta | PT-BILLING-001 | análisis-solamente |
| HU-BILLING-002 | Pago Efectivo | PT-BILLING-001 | análisis-solamente |
| HU-BILLING-003 | Preferencia MP | PT-BILLING-002 | análisis-solamente |
| HU-BILLING-004 | Webhook MP | PT-BILLING-002 | análisis-solamente |
| HU-BILLING-005 | Estado de Cuenta | PT-BILLING-001 | análisis-solamente |
| HU-BILLING-006 | Listar Pagos | PT-BILLING-001 | análisis-solamente |
| HU-BILLING-007 | División Cuenta | PT-BILLING-001 | análisis-solamente |
| HU-BILLING-008 | Propina | PT-BILLING-001 | análisis-solamente |
| HU-BILLING-009 | Reembolso | PT-BILLING-001 | análisis-solamente |
| HU-BILLING-010 | Reportes Ventas | PT-BILLING-001 | análisis-solamente |

### Dominio ALTO (15 HU)

| HU-ID | Título | PT-ID | Autonomía |
|-------|--------|-------|-----------|
| HU-PROD-001 | Listar Productos | PT-PRODUCT-001 | código-supervisado |
| HU-PROD-002 | Ver Producto | PT-PRODUCT-001 | código-supervisado |
| HU-PROD-003 | Crear Producto | PT-PRODUCT-001 | código-supervisado |
| HU-PROD-004 | Actualizar Producto | PT-PRODUCT-001 | código-supervisado |
| HU-PROD-005 | Eliminar Producto | PT-PRODUCT-001 | código-supervisado |
| HU-PROD-006 | Restaurar Producto | PT-PRODUCT-001 | código-supervisado |
| HU-PROD-007 | Disponibilidad | PT-PRODUCT-001 | código-supervisado |
| HU-PROD-008 | Precio por Sucursal | PT-PRODUCT-001 | código-supervisado |
| HU-PROD-009 | Alérgenos Producto | PT-ALLERGEN-001 | análisis-solamente |
| HU-PROD-010 | Ingredientes Producto | PT-PRODUCT-001 | código-supervisado |
| HU-PROD-011 | Flags Dietéticos | PT-PRODUCT-001 | código-supervisado |
| HU-PROD-012 | Búsqueda Avanzada | PT-PRODUCT-001 | código-supervisado |

### Dominio MEDIO (53 HU)

| HU-ID | Título | PT-ID | Autonomía |
|-------|--------|-------|-----------|
| HU-SESSION-001 | Crear Sesión por ID | PT-SESSION-001 | código-con-review |
| HU-SESSION-002 | Sesión por Código QR | PT-SESSION-001 | código-con-review |
| HU-SESSION-003 | Ver Sesión | PT-SESSION-001 | código-con-review |
| HU-SESSION-004 | Cambiar Estado | PT-SESSION-001 | código-con-review |
| HU-SESSION-005 | Cerrar Sesión | PT-SESSION-001 | código-con-review |
| HU-DINER-001 | Registrar Diner | PT-DINER-001 | código-con-review |
| HU-DINER-002 | Ver Menú | PT-DINER-001 | código-con-review |
| HU-DINER-003 | Proponer Round | PT-DINER-001 | código-con-review |
| HU-DINER-004 | Confirmar Ready | PT-DINER-001 | código-con-review |
| HU-DINER-005 | Enviar Round | PT-DINER-001 | código-con-review |
| HU-DINER-006 | Sync Preferencias | PT-DINER-001 | código-con-review |
| HU-DINER-007 | Cargar Preferencias | PT-DINER-001 | código-con-review |
| HU-DINER-008 | Historial Visitas | PT-DINER-001 | código-con-review |
| HU-DINER-009 | Solicitar Cuenta | PT-DINER-001 | código-con-review |
| HU-DINER-010 | Llamar Mesero | PT-DINER-001 | código-con-review |
| HU-DINER-011 | Registrar Customer | PT-DINER-001 | código-con-review |
| HU-DINER-012 | Reconocer Customer | PT-DINER-001 | código-con-review |
| HU-DINER-013 | Ver Perfil | PT-DINER-001 | código-con-review |
| HU-DINER-014 | Actualizar Perfil | PT-DINER-001 | código-con-review |
| HU-DINER-015 | Sugerencias | PT-DINER-001 | código-con-review |
| HU-KITCHEN-001 | Ver Rounds Pendientes | PT-KITCHEN-001 | código-con-review |
| HU-KITCHEN-002 | Avanzar Estado | PT-KITCHEN-001 | código-con-review |
| HU-KITCHEN-003 | Listar Tickets | PT-KITCHEN-001 | código-con-review |
| HU-KITCHEN-004 | Ver Ticket | PT-KITCHEN-001 | código-con-review |
| HU-KITCHEN-005 | Iniciar Preparación | PT-KITCHEN-001 | código-con-review |
| HU-KITCHEN-006 | Item Listo | PT-KITCHEN-001 | código-con-review |
| HU-KITCHEN-007 | Ticket Completo | PT-KITCHEN-001 | código-con-review |
| HU-KITCHEN-008 | Ticket Entregado | PT-KITCHEN-001 | código-con-review |
| HU-WAITER-001 | Mesas Asignadas | PT-WAITER-001 | código-con-review |
| HU-WAITER-002 | Detalle Sesión | PT-WAITER-001 | código-con-review |
| HU-WAITER-003 | Menú Compacto | PT-WAITER-001 | código-con-review |
| HU-WAITER-004 | Comanda Rápida | PT-WAITER-001 | código-con-review |
| HU-WAITER-005 | Round a Cocina | PT-WAITER-001 | código-con-review |
| HU-WAITER-006 | Round Servido | PT-WAITER-001 | código-con-review |
| HU-WAITER-007 | Atender Service Call | PT-WAITER-001 | código-con-review |
| HU-WAITER-008 | Cerrar Service Call | PT-WAITER-001 | código-con-review |
| HU-WAITER-009 | Solicitar Cuenta | PT-WAITER-001 | código-con-review |
| HU-WAITER-010 | Cerrar Mesa | PT-WAITER-001 | código-con-review |

### Dominio BAJO (49 HU)

| HU-ID | Título | PT-ID | Autonomía |
|-------|--------|-------|-----------|
| HU-CAT-001 | Listar Categorías | PT-CATALOG-001 | código-autónomo |
| HU-CAT-002 | Ver Categoría | PT-CATALOG-001 | código-autónomo |
| HU-CAT-003 | Crear Categoría | PT-CATALOG-001 | código-autónomo |
| HU-CAT-004 | Actualizar Categoría | PT-CATALOG-001 | código-autónomo |
| HU-CAT-005 | Eliminar Categoría | PT-CATALOG-001 | código-autónomo |
| HU-CAT-006 | Restaurar Categoría | PT-CATALOG-001 | código-autónomo |
| HU-CAT-007 | Reordenar Categorías | PT-CATALOG-001 | código-autónomo |
| HU-SUBCAT-001 | Listar Subcategorías | PT-CATALOG-001 | código-autónomo |
| HU-SUBCAT-002 | Ver Subcategoría | PT-CATALOG-001 | código-autónomo |
| HU-SUBCAT-003 | Crear Subcategoría | PT-CATALOG-001 | código-autónomo |
| HU-SUBCAT-004 | Actualizar Subcategoría | PT-CATALOG-001 | código-autónomo |
| HU-SUBCAT-005 | Eliminar Subcategoría | PT-CATALOG-001 | código-autónomo |
| HU-SUBCAT-006 | Restaurar Subcategoría | PT-CATALOG-001 | código-autónomo |
| HU-SUBCAT-007 | Reordenar Subcategorías | PT-CATALOG-001 | código-autónomo |
| HU-BRANCH-001 | Listar Sucursales | PT-BRANCH-001 | código-autónomo |
| HU-BRANCH-002 | Ver Sucursal | PT-BRANCH-001 | código-autónomo |
| HU-BRANCH-003 | Crear Sucursal | PT-BRANCH-001 | código-autónomo |
| HU-BRANCH-004 | Actualizar Sucursal | PT-BRANCH-001 | código-autónomo |
| HU-BRANCH-005 | Eliminar Sucursal | PT-BRANCH-001 | código-autónomo |
| HU-BRANCH-006 | Restaurar Sucursal | PT-BRANCH-001 | código-autónomo |
| HU-SECTOR-001 | Listar Sectores | PT-SECTOR-001 | código-autónomo |
| HU-SECTOR-002 | Ver Sector | PT-SECTOR-001 | código-autónomo |
| HU-SECTOR-003 | Crear Sector | PT-SECTOR-001 | código-autónomo |
| HU-SECTOR-004 | Actualizar Sector | PT-SECTOR-001 | código-autónomo |
| HU-SECTOR-005 | Eliminar Sector | PT-SECTOR-001 | código-autónomo |
| HU-TABLE-001 | Listar Mesas | PT-TABLE-001 | código-autónomo |
| HU-TABLE-002 | Ver Mesa | PT-TABLE-001 | código-autónomo |
| HU-TABLE-003 | Crear Mesa | PT-TABLE-001 | código-autónomo |
| HU-TABLE-004 | Actualizar Mesa | PT-TABLE-001 | código-autónomo |
| HU-TABLE-005 | Eliminar Mesa | PT-TABLE-001 | código-autónomo |
| HU-TABLE-006 | Restaurar Mesa | PT-TABLE-001 | código-autónomo |
| HU-TABLE-007 | Cambiar Estado | PT-TABLE-001 | código-autónomo |
| HU-TABLE-008 | Generar QR | PT-TABLE-001 | código-autónomo |
| HU-PROMO-001 | Listar Promociones | PT-PROMO-001 | código-autónomo |
| HU-PROMO-002 | Ver Promoción | PT-PROMO-001 | código-autónomo |
| HU-PROMO-003 | Crear Promoción | PT-PROMO-001 | código-autónomo |
| HU-PROMO-004 | Actualizar Promoción | PT-PROMO-001 | código-autónomo |
| HU-PROMO-005 | Eliminar Promoción | PT-PROMO-001 | código-autónomo |
| HU-PROMO-006 | Restaurar Promoción | PT-PROMO-001 | código-autónomo |
| HU-RECIPE-001 | Listar Recetas | PT-RECIPE-001 | código-autónomo |
| HU-RECIPE-002 | Ver Receta | PT-RECIPE-001 | código-autónomo |
| HU-RECIPE-003 | Crear Receta | PT-RECIPE-001 | código-autónomo |
| HU-RECIPE-004 | Actualizar Receta | PT-RECIPE-001 | código-autónomo |
| HU-RECIPE-005 | Eliminar Receta | PT-RECIPE-001 | código-autónomo |
| HU-RECIPE-006 | Vincular Producto | PT-RECIPE-001 | código-autónomo |
| HU-RECIPE-007 | Ingestar RAG | PT-RECIPE-001 | código-autónomo |
| HU-RECIPE-008 | Sync Alérgenos | PT-RECIPE-001 | código-autónomo |
| HU-EXCL-001 | Listar Exclusiones | PT-EXCL-001 | código-autónomo |
| HU-EXCL-002 | Crear Excl. Categoría | PT-EXCL-001 | código-autónomo |
| HU-EXCL-003 | Eliminar Excl. Cat. | PT-EXCL-001 | código-autónomo |
| HU-EXCL-004 | Crear Excl. Subcat. | PT-EXCL-001 | código-autónomo |
| HU-EXCL-005 | Eliminar Excl. Subcat. | PT-EXCL-001 | código-autónomo |
| HU-ASSIGN-001 | Ver Asignaciones | PT-ASSIGN-001 | código-autónomo |
| HU-ASSIGN-002 | Crear Asignación | PT-ASSIGN-001 | código-autónomo |
| HU-ASSIGN-003 | Eliminar Asignación | PT-ASSIGN-001 | código-autónomo |
| HU-ASSIGN-004 | Asignación Masiva | PT-ASSIGN-001 | código-autónomo |
| HU-ASSIGN-005 | Copiar Asignaciones | PT-ASSIGN-001 | código-autónomo |
| HU-AUDIT-001 | Ver Logs | PT-AUDIT-001 | código-autónomo |
| HU-AUDIT-002 | Reporte Ventas | PT-AUDIT-001 | código-autónomo |
| HU-AUDIT-003 | Top Productos | PT-AUDIT-001 | código-autónomo |
| HU-AUDIT-004 | Reporte Meseros | PT-AUDIT-001 | código-autónomo |
| HU-AUDIT-005 | Tiempos Cocina | PT-AUDIT-001 | código-autónomo |
| HU-AUDIT-006 | Exportar CSV | PT-AUDIT-001 | código-autónomo |
| HU-PUBLIC-001 | Ver Catálogo | PT-PUBLIC-001 | código-autónomo |
| HU-PUBLIC-002 | Info Sucursal | PT-PUBLIC-001 | código-autónomo |
| HU-PUBLIC-003 | Detalle Producto | PT-PUBLIC-001 | código-autónomo |
| HU-PUBLIC-004 | Buscar Productos | PT-PUBLIC-001 | código-autónomo |
| HU-PUBLIC-005 | Alérgenos Públicos | PT-PUBLIC-001 | código-autónomo |
| HU-HEALTH-001 | Health Check | PT-HEALTH-001 | código-autónomo |
| HU-HEALTH-002 | Health Detallado | PT-HEALTH-001 | código-autónomo |
| HU-HEALTH-003 | Métricas Prometheus | PT-HEALTH-001 | código-autónomo |
| HU-TENANT-001 | Ver Tenant | PT-TENANT-001 | código-autónomo |
| HU-RAG-001 | Consultar Chatbot | PT-RAG-001 | código-autónomo |
| HU-RAG-002 | Ingestar Documento | PT-RAG-001 | código-autónomo |
| HU-RAG-003 | Listar Documentos | PT-RAG-001 | código-autónomo |

---

## Tickets Refactorizados (Formato Plantilla)

A continuación se presentan los tickets refactorizados con el formato completo de la plantilla, organizados por nivel de riesgo.

---

# DOMINIO CRÍTICO

## PT-AUTH-001: Sistema de Autenticación JWT

### HU-AUTH-001: Login de Personal

```yaml
# ============================================================================
# METADATOS
# ============================================================================
id: HU-AUTH-001
titulo: Autenticación de Personal con JWT
endpoint: POST /api/auth/login
roles_permitidos: [Público - sin autenticación]
autenticacion: Ninguna
archivo_implementacion: backend/rest_api/routers/auth/routes.py
servicio: backend/rest_api/routers/auth/routes.py::login()
websocket_event: null
rate_limit: 5/minuto por IP + 5/minuto por email

# GOBERNANZA
policy_ticket: PT-AUTH-001
nivel_riesgo: CRÍTICO
autonomia_ia: análisis-solamente
responsable_principal: "@tech.lead"
responsable_seguridad: "@security.lead"
```

#### Request

##### Headers
| Header | Requerido | Descripción |
|--------|-----------|-------------|
| Content-Type | Sí | application/json |

##### Body Schema
```json
{
  "email": "string (required)",
  "password": "string (required)"
}
```

##### Validaciones
| Campo | Tipo | Requerido | Validaciones | Ejemplo |
|-------|------|-----------|--------------|---------|
| email | string | Sí | formato email, max 255 chars | "admin@demo.com" |
| password | string | Sí | min 6, max 128 chars | "admin123" |

#### Response

##### Success (200 OK)
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

##### Errores
| Código | Condición | Response |
|--------|-----------|----------|
| 400 | Credenciales inválidas | `{"detail": "Credenciales inválidas"}` |
| 400 | Usuario inactivo | `{"detail": "Usuario deshabilitado"}` |
| 415 | Content-Type inválido | `{"detail": "Unsupported media type"}` |
| 429 | Rate limit IP | `{"detail": "Rate limit exceeded"}` |
| 429 | Rate limit email | `{"detail": "Too many attempts for this email"}` |

#### Lógica de Negocio

1. **Validar Content-Type** = application/json
2. **Verificar rate limit** por IP (5/min)
3. **Verificar rate limit** por email (5/min)
4. **Buscar usuario** por email en BD
5. **Verificar is_active** = true
6. **Verificar contraseña** con bcrypt.verify()
7. **Re-hashear** si usa algoritmo legacy
8. **Obtener roles** de UserBranchRole JOIN Branch
9. **Validar** branches pertenecen al mismo tenant
10. **Generar JWT** access_token (exp: 15 min)
11. **Generar JWT** refresh_token (exp: 7 días)
12. **Registrar log** de login exitoso

#### Modelo de Datos
```sql
-- User
id: BIGINT PRIMARY KEY
email: VARCHAR(255) UNIQUE NOT NULL
password_hash: VARCHAR(255) NOT NULL
tenant_id: BIGINT NOT NULL REFERENCES tenant(id)
is_active: BOOLEAN DEFAULT true

-- UserBranchRole (M:N)
user_id: BIGINT REFERENCES user(id)
branch_id: BIGINT REFERENCES branch(id)
role: VARCHAR(20) CHECK (role IN ('ADMIN','MANAGER','KITCHEN','WAITER'))
```

#### Restricciones IA (CRÍTICO)
- **PERMITIDO**: Analizar código, documentar, generar tests, sugerir mejoras
- **PROHIBIDO**: Modificar lógica JWT, cambiar TTL, alterar hashing, tocar rate limiting

---

### HU-AUTH-002: Refresh Token

```yaml
id: HU-AUTH-002
titulo: Renovación de Token de Acceso
endpoint: POST /api/auth/refresh
roles_permitidos: [Usuario con refresh_token válido]
autenticacion: Ninguna (token en body)
websocket_event: null
rate_limit: 10/minuto
policy_ticket: PT-AUTH-001
nivel_riesgo: CRÍTICO
autonomia_ia: análisis-solamente
```

#### Request
```json
{
  "refresh_token": "string (required)"
}
```

#### Response (200 OK)
```json
{
  "access_token": "string",
  "token_type": "bearer"
}
```

#### Errores
| Código | Condición | Response |
|--------|-----------|----------|
| 401 | Token expirado | `{"detail": "Token expirado"}` |
| 401 | Token inválido | `{"detail": "Token inválido"}` |
| 401 | Token en blacklist | `{"detail": "Token revocado"}` |
| 401 | Usuario inactivo | `{"detail": "Usuario deshabilitado"}` |

#### Lógica de Negocio
1. Validar refresh_token (firma, exp)
2. Verificar no está en blacklist (Redis)
3. Obtener user_id del claim "sub"
4. Buscar usuario, verificar is_active
5. Re-obtener roles actuales (cambios en tiempo real)
6. Generar nuevo access_token

---

### HU-AUTH-003: Información de Usuario Actual

```yaml
id: HU-AUTH-003
titulo: Obtener Datos del Usuario Autenticado
endpoint: GET /api/auth/me
roles_permitidos: [ADMIN, MANAGER, KITCHEN, WAITER]
autenticacion: Bearer Token (JWT)
websocket_event: null
policy_ticket: PT-AUTH-001
nivel_riesgo: CRÍTICO
autonomia_ia: análisis-solamente
```

#### Response (200 OK)
```json
{
  "id": 1,
  "email": "admin@demo.com",
  "first_name": "Admin",
  "last_name": "Demo",
  "tenant_id": 1,
  "branch_ids": [1, 2, 3],
  "roles": ["ADMIN"]
}
```

---

### HU-AUTH-004: Logout Global

```yaml
id: HU-AUTH-004
titulo: Cierre de Sesión en Todos los Dispositivos
endpoint: POST /api/auth/logout
roles_permitidos: [ADMIN, MANAGER, KITCHEN, WAITER]
autenticacion: Bearer Token (JWT)
websocket_event: null
rate_limit: 10/minuto
policy_ticket: PT-AUTH-001
nivel_riesgo: CRÍTICO
autonomia_ia: análisis-solamente
```

#### Lógica de Negocio
1. Extraer user_id del JWT
2. Llamar revoke_all_user_tokens(user_id)
3. Agregar tokens a blacklist en Redis
4. TTL = tiempo restante de expiración

#### Implementación Redis
```python
# Formato: token_blacklist:{jti}
await redis.setex(f"token_blacklist:{jti}", ttl_seconds, "1")
```

---

### HU-AUTH-005: Validación RBAC

```yaml
id: HU-AUTH-005
titulo: Control de Acceso Basado en Roles
tipo: Historia de Sistema (no endpoint)
policy_ticket: PT-AUTH-001
nivel_riesgo: CRÍTICO
autonomia_ia: análisis-solamente
```

#### Matriz de Permisos
| Entidad | ADMIN | MANAGER | KITCHEN | WAITER |
|---------|-------|---------|---------|--------|
| Staff | CRUD | CRU (sin ADMIN) | - | - |
| Products | CRUD | CRUD (sus branches) | R | R |
| Rounds | CRUD | CRUD | RU (estado) | RU (sus mesas) |

#### Implementación
```python
from rest_api.services.permissions import PermissionContext

ctx = PermissionContext(user)
ctx.require_management()  # Raises 403 si no es ADMIN/MANAGER
ctx.require_branch_access(branch_id)  # Verifica acceso
```

---

## PT-STAFF-001: Gestión de Personal

### HU-STAFF-001 a HU-STAFF-006

```yaml
# Tickets de Staff comparten configuración
policy_ticket: PT-STAFF-001
nivel_riesgo: CRÍTICO
autonomia_ia: análisis-solamente
responsable_principal: "@tech.lead"

# HU individuales
HU-STAFF-001: GET /api/admin/staff (Listar)
HU-STAFF-002: GET /api/admin/staff/{id} (Ver)
HU-STAFF-003: POST /api/admin/staff (Crear)
HU-STAFF-004: PATCH /api/admin/staff/{id} (Actualizar)
HU-STAFF-005: DELETE /api/admin/staff/{id} (Eliminar)
HU-STAFF-006: POST /api/admin/staff/{id}/restore (Restaurar)
```

#### Restricción CRÍTICA: MANAGER
```python
# MANAGER NO puede crear rol ADMIN
if "ADMIN" in requested_roles and not ctx.is_admin:
    raise ForbiddenError("No puede asignar rol ADMIN")

# MANAGER solo puede gestionar staff de sus branches
if not ctx.is_admin:
    for br in branch_roles:
        ctx.require_branch_access(br.branch_id)
```

#### Restricciones IA
- **PERMITIDO**: Analizar restricciones, generar tests
- **PROHIBIDO**: Modificar restricciones MANAGER, cambiar hashing

---

## PT-ALLERGEN-001: Sistema de Alérgenos

### HU-ALRG-001 a HU-ALRG-008

```yaml
policy_ticket: PT-ALLERGEN-001
nivel_riesgo: CRÍTICO
autonomia_ia: análisis-solamente
responsable_principal: "@product.owner"
warning: "⚠️ IMPACTO DIRECTO EN SALUD - IA NO puede modificar datos"
```

#### Restricciones IA (ABSOLUTO)
- **PERMITIDO**: Analizar, generar tests, documentar
- **PROHIBIDO**:
  - Modificar datos de alérgenos
  - Cambiar cross-reactions
  - Inferir información faltante
  - Generar código que modifique alérgenos

---

## PT-BILLING-001 & PT-BILLING-002: Pagos

### HU-BILLING-001 a HU-BILLING-010

```yaml
policy_ticket: PT-BILLING-001 | PT-BILLING-002
nivel_riesgo: CRÍTICO
autonomia_ia: análisis-solamente
responsable_principal: "@tech.lead"
responsable_seguridad: "@security.lead"
warning: "⚠️ IMPACTO FINANCIERO - Solo análisis permitido"
```

#### Restricciones IA (ABSOLUTO)
- **PERMITIDO**: Analizar, documentar, tests en sandbox
- **PROHIBIDO**:
  - Escribir código de producción en billing/
  - Modificar algoritmo FIFO
  - Tocar circuit breaker
  - Cambiar webhook verification
  - Acceder a credenciales MP

---

# DOMINIO ALTO

## PT-PRODUCT-001: Gestión de Productos

### HU-PROD-001 a HU-PROD-012

```yaml
policy_ticket: PT-PRODUCT-001
nivel_riesgo: ALTO
autonomia_ia: código-supervisado
responsable_principal: "@tech.lead"
```

#### Ejemplo: HU-PROD-003 Crear Producto

```yaml
id: HU-PROD-003
titulo: Crear Nuevo Producto
endpoint: POST /api/admin/products
roles_permitidos: [ADMIN, MANAGER]
autenticacion: Bearer Token (JWT)
websocket_event: ENTITY_CREATED
policy_ticket: PT-PRODUCT-001
nivel_riesgo: ALTO
autonomia_ia: código-supervisado
```

##### Request
```json
{
  "name": "string (required)",
  "description": "string (optional)",
  "image": "string (optional, URL)",
  "base_price_cents": "integer (required, > 0)",
  "subcategory_id": "integer (required)",
  "branch_prices": [
    {
      "branch_id": "integer",
      "price_cents": "integer",
      "is_available": "boolean"
    }
  ],
  "allergen_ids": ["integer"],
  "dietary_flags": {
    "is_vegetarian": "boolean",
    "is_vegan": "boolean"
  }
}
```

##### Restricciones IA
- **PERMITIDO**: Refactorizar queries, generar tests, mejorar validaciones
- **PROHIBIDO**: Modificar lógica de alérgenos, cambiar SSRF validation
- **REQUIERE**: Aprobación Tech Lead antes de implementar

---

# DOMINIO MEDIO

## PT-KITCHEN-001: Operaciones de Cocina

### HU-KITCHEN-001 a HU-KITCHEN-008

```yaml
policy_ticket: PT-KITCHEN-001
nivel_riesgo: MEDIO
autonomia_ia: código-con-review
responsable_principal: "@tech.lead"
```

#### Ejemplo: HU-KITCHEN-002 Avanzar Estado

```yaml
id: HU-KITCHEN-002
titulo: Marcar Round como Listo
endpoint: PATCH /api/kitchen/rounds/{round_id}/status
roles_permitidos: [KITCHEN]
websocket_event: ROUND_READY
policy_ticket: PT-KITCHEN-001
nivel_riesgo: MEDIO
autonomia_ia: código-con-review
```

##### Request
```json
{
  "status": "READY"
}
```

##### Restricción por Rol
```
PENDING → IN_KITCHEN   (ADMIN/MANAGER only)
IN_KITCHEN → READY     (KITCHEN only) ← Este endpoint
READY → SERVED         (ADMIN/MANAGER/WAITER)
```

##### Restricciones IA
- **PERMITIDO**: Optimizar queries, generar tests, agregar métricas
- **PROHIBIDO**: Cambiar máquina de estados, modificar restricciones de rol
- **CHECKPOINT**: Review después de cada feature

---

## PT-WAITER-001: Operaciones de Mesero

### HU-WAITER-001 a HU-WAITER-010

```yaml
policy_ticket: PT-WAITER-001
nivel_riesgo: MEDIO
autonomia_ia: código-con-review
```

#### Filtrado por Sectores Asignados
```python
# WAITER solo ve mesas de sus sectores HOY
if Roles.WAITER in user["roles"]:
    today = date.today()
    assigned_sectors = db.query(WaiterSectorAssignment).filter(
        WaiterSectorAssignment.user_id == user_id,
        WaiterSectorAssignment.assignment_date == today
    ).all()
    sector_ids = [a.sector_id for a in assigned_sectors]
    tables = tables.filter(Table.sector_id.in_(sector_ids))
```

---

# DOMINIO BAJO

## PT-CATALOG-001: Categorías y Subcategorías

### HU-CAT-001 a HU-CAT-007, HU-SUBCAT-001 a HU-SUBCAT-007

```yaml
policy_ticket: PT-CATALOG-001
nivel_riesgo: BAJO
autonomia_ia: código-autónomo
```

#### Ejemplo: HU-CAT-003 Crear Categoría

```yaml
id: HU-CAT-003
titulo: Crear Nueva Categoría
endpoint: POST /api/admin/categories
roles_permitidos: [ADMIN, MANAGER]
autenticacion: Bearer Token (JWT)
websocket_event: ENTITY_CREATED
policy_ticket: PT-CATALOG-001
nivel_riesgo: BAJO
autonomia_ia: código-autónomo
```

##### Request
```json
{
  "name": "string (required)",
  "branch_id": "integer (required)",
  "image": "string (optional)",
  "display_order": "integer (optional)"
}
```

##### Restricciones IA
- **PERMITIDO**: Implementar completo, crear tests, hacer PR automático
- **PROHIBIDO**: Solo SSRF validation (referir a shared/utils/validators.py)
- **AUTO-MERGE**: Permitido si tests pasan

---

## PT-HEALTH-001: Health Checks

### HU-HEALTH-001 a HU-HEALTH-003

```yaml
policy_ticket: PT-HEALTH-001
nivel_riesgo: BAJO
autonomia_ia: código-autónomo
```

#### Endpoints
```
GET /api/health           → {"status": "healthy"}
GET /api/health/detailed  → {database, redis_async, redis_sync}
GET /ws/metrics           → Prometheus text format
```

---

## Anexo: Reglas de Autonomía por Nivel

### análisis-solamente (CRÍTICO)
```yaml
ia_puede:
  - Leer y analizar código
  - Generar documentación
  - Crear tests unitarios
  - Sugerir mejoras
  - Identificar vulnerabilidades

ia_no_puede:
  - Escribir código de producción
  - Modificar archivos
  - Generar PRs
  - Ejecutar comandos destructivos
```

### código-supervisado (ALTO)
```yaml
ia_puede:
  - Todo lo de análisis-solamente
  - Proponer cambios de código
  - Generar código en PR draft

ia_no_puede:
  - Hacer merge sin aprobación
  - Modificar sin review previo

requiere:
  - Aprobación línea por línea
  - Review de Tech Lead
```

### código-con-review (MEDIO)
```yaml
ia_puede:
  - Todo lo de código-supervisado
  - Implementar features completos
  - Crear PRs para review

requiere:
  - Checkpoint después de cada feature
  - 1 peer review antes de merge
```

### código-autónomo (BAJO)
```yaml
ia_puede:
  - Implementar completo
  - Crear tests
  - Hacer PR y merge si tests pasan

restricciones:
  - Respetar patrones existentes
  - No modificar archivos fuera de scope
  - No tocar archivos de dominios superiores
```

---

## Anexo: Checklist de Implementación IA

### Antes de Implementar
- [ ] Identificar HU-ID del ticket
- [ ] Verificar PT-ID asociado
- [ ] Confirmar nivel_riesgo
- [ ] Verificar autonomia_ia permitida
- [ ] Leer restricciones específicas

### Durante Implementación
- [ ] Seguir formato de plantilla.md
- [ ] Respetar patrones de CLAUDE.md
- [ ] No modificar archivos fuera de scope
- [ ] Generar tests según nivel

### Después de Implementación
- [ ] Verificar tests pasan
- [ ] Type check pasa
- [ ] Documentar cambios
- [ ] Solicitar review según nivel

---

**Fin del Documento de Refactorización**

*152 Historias de Usuario mapeadas a 22 Policy Tickets*
*Fecha: 25 de Enero de 2026*
