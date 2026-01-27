# Plantilla de Historia de Usuario - Proyecto Integrador

## Guía para IA y Desarrolladores

**Versión:** 1.0
**Fecha:** 25 de Enero de 2026

Este documento define la plantilla estándar para documentar historias de usuario con el nivel de detalle requerido para que un agente de IA pueda interpretarlas sin ambigüedades y ejecutar implementaciones de forma autónoma dentro de los límites de gobernanza.

---

## Estructura de la Plantilla

### Sección 1: Metadatos (YAML)

```yaml
# ============================================================================
# METADATOS DE LA HISTORIA DE USUARIO
# ============================================================================

id: HU-{MODULO}-{NNN}
# Formato: HU-AUTH-001, HU-PROD-015, HU-BILLING-003
# Módulos: AUTH, STAFF, CAT, SUBCAT, PROD, ALRG, BRANCH, SECTOR, TABLE,
#          SESSION, DINER, KITCHEN, WAITER, BILLING, PROMO, RECIPE,
#          EXCL, ASSIGN, AUDIT, PUBLIC, HEALTH, TENANT, RAG

titulo: {Título descriptivo en español}
# Ejemplo: "Autenticación de Personal con JWT"
# Convención: Verbo en infinitivo + objeto

endpoint: {MÉTODO} /api/{ruta}
# Ejemplo: POST /api/auth/login
# Métodos: GET, POST, PUT, PATCH, DELETE

roles_permitidos: [{lista de roles}]
# Valores: ADMIN, MANAGER, KITCHEN, WAITER, DINER, Público
# Ejemplo: [ADMIN, MANAGER]

autenticacion: {tipo}
# Valores:
#   - "Bearer Token (JWT)" - para staff
#   - "X-Table-Token" - para diners
#   - "Ninguna" - endpoints públicos

archivo_implementacion: {ruta relativa}
# Ejemplo: backend/rest_api/routers/auth/routes.py

servicio: {ruta::clase o función}
# Ejemplo: rest_api/services/domain/category_service.py::CategoryService

websocket_event: {EVENTO o null}
# Eventos: ENTITY_CREATED, ENTITY_UPDATED, ENTITY_DELETED, CASCADE_DELETE,
#          ROUND_SUBMITTED, ROUND_IN_KITCHEN, ROUND_READY, ROUND_SERVED,
#          TABLE_SESSION_STARTED, CHECK_REQUESTED, PAYMENT_APPROVED, etc.

rate_limit: {límite o null}
# Formato: "{N}/{unidad}" - Ejemplo: "10/minuto", "5/segundo"

# ----------------------------------------------------------------------------
# VINCULACIÓN CON GOBERNANZA (Policy Ticket)
# ----------------------------------------------------------------------------

policy_ticket: PT-{DOMINIO}-{NNN}
# Referencia al Policy Ticket que gobierna esta funcionalidad
# Ejemplo: PT-AUTH-001

nivel_riesgo: {CRÍTICO | ALTO | MEDIO | BAJO}
# Determina el nivel de autonomía de IA:
#   - CRÍTICO: IA solo análisis, no puede escribir código
#   - ALTO: IA supervisada, requiere aprobación antes de cada cambio
#   - MEDIO: IA con checkpoints, puede implementar pero requiere review
#   - BAJO: IA completa, puede implementar y auto-merge

autonomia_ia: {nivel}
# Valores:
#   - "análisis-solamente" - Solo puede leer y documentar
#   - "código-supervisado" - Puede escribir código con aprobación previa
#   - "código-con-review" - Puede escribir código, requiere review post
#   - "código-autónomo" - Puede implementar y hacer PR automático
```

---

### Sección 2: Request Schema

```markdown
## Request

### Headers
| Header | Requerido | Descripción |
|--------|-----------|-------------|
| Authorization | {Sí/No} | Bearer {access_token} |
| X-Table-Token | {Sí/No} | Token HMAC de sesión de mesa |
| Content-Type | {Sí/No} | application/json |

### Path Parameters
| Parámetro | Tipo | Requerido | Validación | Descripción |
|-----------|------|-----------|------------|-------------|
| {nombre} | {tipo} | {Sí/No} | {reglas} | {descripción} |

### Query Parameters
| Parámetro | Tipo | Requerido | Default | Validación | Descripción |
|-----------|------|-----------|---------|------------|-------------|
| {nombre} | {tipo} | {Sí/No} | {valor} | {reglas} | {descripción} |

### Body Schema
```json
{
  "campo_requerido": "{tipo} (required)",
  "campo_opcional": "{tipo} (optional)",
  "campo_con_default": "{tipo} (optional, default={valor})",
  "array_campo": ["{tipo}"],
  "objeto_anidado": {
    "sub_campo": "{tipo}"
  }
}
```

### Validaciones de Campos
| Campo | Tipo | Requerido | Validaciones | Ejemplo |
|-------|------|-----------|--------------|---------|
| {nombre} | {tipo} | {Sí/No} | {reglas detalladas} | {valor ejemplo} |
```

---

### Sección 3: Response Schema

```markdown
## Response

### Success Response ({código} {estado})
```json
{
  "campo": "{tipo}",
  "campo_nullable": "{tipo} | null",
  "array": ["{tipo}"],
  "timestamps": "datetime ISO8601"
}
```

### Ejemplo Response Exitoso
```json
{
  // JSON completo con valores reales de ejemplo
}
```

### Errores Específicos
| Código | Condición | Response Body |
|--------|-----------|---------------|
| {código} | {cuándo ocurre} | `{JSON del error}` |
```

---

### Sección 4: Lógica de Negocio

```markdown
## Lógica de Negocio

### Flujo Principal
1. **{Acción 1}**: {descripción detallada}
2. **{Acción 2}**: {descripción detallada}
3. **{Acción N}**: {descripción detallada}

### Reglas de Negocio
- **RN-001**: {descripción de regla}
- **RN-002**: {descripción de regla}

### Validaciones de Seguridad
- [ ] {validación 1}
- [ ] {validación 2}

### Comportamiento Especial
- **Si {condición}**: {entonces}
- **Edge case**: {descripción}
```

---

### Sección 5: Modelo de Datos

```markdown
## Modelo de Datos

### Entidad Principal
```sql
-- {NombreTabla}
id: BIGINT PRIMARY KEY
{campo}: {TIPO SQL} {CONSTRAINTS}
tenant_id: BIGINT NOT NULL REFERENCES tenant(id)
is_active: BOOLEAN DEFAULT true
created_at: TIMESTAMP DEFAULT now()
updated_at: TIMESTAMP
-- Índices
INDEX idx_{tabla}_{campo} ({campo})
-- Constraints
UNIQUE({campo1}, {campo2})
CHECK({condición})
```

### Relaciones
```
{EntidadA} (1) ─── (N) {EntidadB}
{EntidadC} (M) ─── (N) {EntidadD} via {TablaIntermedia}
```

### Eager Loading Requerido
```python
# Evitar N+1 queries
query.options(
    selectinload({Modelo}.{relación}),
    joinedload({Modelo}.{relación}.{sub_relación}),
)
```
```

---

### Sección 6: WebSocket Events

```markdown
## WebSocket Events

### Evento Emitido
```json
{
  "type": "{TIPO_EVENTO}",
  "tenant_id": "{integer}",
  "branch_id": "{integer}",
  "sector_id": "{integer | null}",
  "entity_type": "{string}",
  "entity_id": "{integer}",
  "data": {
    // datos específicos del evento
  },
  "timestamp": "{datetime ISO8601}"
}
```

### Destinatarios
| Canal | Condición |
|-------|-----------|
| Admin | Siempre |
| Waiters | Si sector_id presente, solo del sector; sino todos |
| Kitchen | Si evento de round/ticket |
| Diners | Si evento de su sesión |
```

---

### Sección 7: Implementación Técnica

```markdown
## Implementación Técnica

### Archivos a Modificar/Crear
| Archivo | Acción | Descripción |
|---------|--------|-------------|
| {ruta} | {Crear/Modificar} | {qué hacer} |

### Patrones a Seguir
- **Patrón 1**: Referencia a CLAUDE.md sección "{nombre}"
- **Patrón 2**: Ver implementación existente en {archivo}

### Dependencias
- **Servicios**: {lista de servicios requeridos}
- **Repositorios**: {lista de repositorios}
- **Utilities**: {funciones de utilidad}

### Configuración
```python
# backend/shared/config/settings.py
{SETTING_NAME} = {valor}  # {descripción}
```

### Tests Requeridos
| Tipo | Archivo | Casos |
|------|---------|-------|
| Unit | tests/test_{módulo}.py | {lista de casos} |
| Integration | tests/integration/test_{flujo}.py | {lista de casos} |
```

---

## Plantilla Completa - Ejemplo

```yaml
# ============================================================================
# HU-EJEMPLO-001: Crear Categoría de Menú
# ============================================================================

id: HU-CAT-003
titulo: Crear Nueva Categoría de Menú
endpoint: POST /api/admin/categories
roles_permitidos: [ADMIN, MANAGER]
autenticacion: Bearer Token (JWT)
archivo_implementacion: backend/rest_api/routers/admin/categories.py
servicio: rest_api/services/domain/category_service.py::CategoryService
websocket_event: ENTITY_CREATED
rate_limit: null
policy_ticket: PT-CATALOG-001
nivel_riesgo: BAJO
autonomia_ia: código-autónomo
```

## Request

### Headers
| Header | Requerido | Descripción |
|--------|-----------|-------------|
| Authorization | Sí | Bearer {access_token} |
| Content-Type | Sí | application/json |

### Body Schema
```json
{
  "name": "string (required)",
  "branch_id": "integer (required)",
  "image": "string (optional, URL)",
  "display_order": "integer (optional)"
}
```

### Validaciones de Campos
| Campo | Tipo | Requerido | Validaciones | Ejemplo |
|-------|------|-----------|--------------|---------|
| name | string | Sí | min 1, max 100 chars, único por branch | "Bebidas" |
| branch_id | integer | Sí | > 0, debe existir en tenant | 1 |
| image | string | No | URL válida, no localhost/IPs internas (SSRF) | "https://cdn.example.com/img.jpg" |
| display_order | integer | No | >= 0, si omitido: max(order)+1 | 5 |

## Response

### Success Response (201 Created)
```json
{
  "id": "integer",
  "name": "string",
  "image": "string | null",
  "display_order": "integer",
  "branch_id": "integer",
  "branch_name": "string",
  "is_active": true,
  "created_at": "datetime ISO8601"
}
```

### Ejemplo Response Exitoso
```json
{
  "id": 15,
  "name": "Bebidas",
  "image": "https://cdn.example.com/bebidas.jpg",
  "display_order": 1,
  "branch_id": 1,
  "branch_name": "Sucursal Centro",
  "is_active": true,
  "created_at": "2026-01-25T14:30:00Z"
}
```

### Errores Específicos
| Código | Condición | Response Body |
|--------|-----------|---------------|
| 400 | Nombre duplicado en branch | `{"detail": "Ya existe una categoría con ese nombre en esta sucursal"}` |
| 400 | URL imagen inválida | `{"detail": "URL de imagen no válida", "field": "image"}` |
| 401 | Token faltante/inválido | `{"detail": "Not authenticated"}` |
| 403 | MANAGER sin acceso a branch | `{"detail": "No tiene acceso a esta sucursal"}` |
| 404 | branch_id no existe | `{"detail": "Sucursal no encontrada"}` |
| 422 | Validación Pydantic falla | `{"detail": [{"loc": ["body", "name"], "msg": "..."}]}` |

## Lógica de Negocio

### Flujo Principal
1. **Validar autenticación**: Extraer y validar JWT del header
2. **Validar permisos**: ctx.require_branch_access(branch_id)
3. **Verificar branch_id**: Debe existir y pertenecer al tenant
4. **Verificar unicidad**: Nombre único en branch
5. **Validar image URL**: Si presente, aplicar SSRF prevention
6. **Calcular display_order**: Si omitido, max(order)+1 en branch
7. **Crear entidad**: Category con tenant_id del JWT
8. **Registrar auditoría**: created_by_id, created_by_email
9. **Publicar evento**: WebSocket ENTITY_CREATED

### Reglas de Negocio
- **RN-001**: MANAGER solo puede crear en sus branch_ids
- **RN-002**: display_order auto-calculado si no se proporciona
- **RN-003**: image URL debe pasar validación SSRF

### Validaciones de Seguridad
- [ ] Validar tenant isolation (tenant_id del JWT)
- [ ] Validar branch access para MANAGER
- [ ] Sanitizar image URL contra SSRF

## Modelo de Datos

### Entidad Principal
```sql
-- Category
id: BIGINT PRIMARY KEY
name: VARCHAR(100) NOT NULL
image: VARCHAR(500)
display_order: INTEGER DEFAULT 0
branch_id: BIGINT NOT NULL REFERENCES branch(id)
tenant_id: BIGINT NOT NULL REFERENCES tenant(id)
is_active: BOOLEAN DEFAULT true
created_at: TIMESTAMP DEFAULT now()
updated_at: TIMESTAMP
created_by_id: BIGINT
created_by_email: VARCHAR(255)
-- Índices
INDEX idx_category_branch (branch_id)
INDEX idx_category_tenant_active (tenant_id, is_active)
-- Constraints
UNIQUE(branch_id, name) WHERE is_active = true
```

### Eager Loading Requerido
```python
query.options(
    joinedload(Category.branch),  # Para branch_name en response
)
```

## WebSocket Events

### Evento Emitido
```json
{
  "type": "ENTITY_CREATED",
  "tenant_id": 1,
  "branch_id": 1,
  "entity_type": "Category",
  "entity_id": 15,
  "data": {
    "name": "Bebidas",
    "branch_name": "Sucursal Centro"
  },
  "timestamp": "2026-01-25T14:30:00Z"
}
```

### Destinatarios
| Canal | Condición |
|-------|-----------|
| Admin | Siempre |

## Implementación Técnica

### Archivos a Modificar/Crear
| Archivo | Acción | Descripción |
|---------|--------|-------------|
| rest_api/services/domain/category_service.py | Modificar | Agregar método create() |
| rest_api/routers/admin/categories.py | Modificar | Agregar endpoint POST |

### Patrones a Seguir
- **Domain Service**: Ver CLAUDE.md sección "Clean Architecture (Backend)"
- **Soft Delete**: Ver implementación en rest_api/services/crud/soft_delete.py
- **SSRF Prevention**: Ver shared/utils/validators.py::validate_image_url

### Tests Requeridos
| Tipo | Archivo | Casos |
|------|---------|-------|
| Unit | tests/test_categories.py | create_success, create_duplicate_name, create_invalid_branch |
| Integration | tests/integration/test_catalog.py | full_category_lifecycle |

---

## Checklist de Completitud

Antes de considerar una historia de usuario como completa, verificar:

### Metadatos
- [ ] ID único y correcto (HU-{MODULO}-{NNN})
- [ ] Endpoint con método HTTP correcto
- [ ] Roles permitidos definidos
- [ ] Tipo de autenticación especificado
- [ ] Archivo de implementación identificado
- [ ] Policy Ticket vinculado
- [ ] Nivel de riesgo asignado

### Request
- [ ] Todos los headers documentados
- [ ] Path parameters con validaciones
- [ ] Query parameters con defaults
- [ ] Body schema completo en JSON
- [ ] Tabla de validaciones por campo
- [ ] Ejemplos de valores válidos

### Response
- [ ] Schema de éxito con tipos
- [ ] Ejemplo completo con valores reales
- [ ] Todos los códigos de error documentados
- [ ] Response body exacto para cada error

### Lógica
- [ ] Flujo paso a paso numerado
- [ ] Reglas de negocio identificadas
- [ ] Validaciones de seguridad listadas
- [ ] Edge cases documentados

### Datos
- [ ] Schema SQL completo
- [ ] Índices definidos
- [ ] Constraints documentados
- [ ] Relaciones mapeadas
- [ ] Eager loading especificado

### WebSocket
- [ ] Evento(s) emitido(s) documentado(s)
- [ ] Payload completo
- [ ] Destinatarios identificados

### Implementación
- [ ] Archivos a modificar listados
- [ ] Patrones referenciados
- [ ] Tests requeridos especificados

---

## Anexo: Tipos de Datos Estándar

### Tipos SQL → JSON
| SQL | JSON | Ejemplo |
|-----|------|---------|
| BIGINT | integer | 123 |
| VARCHAR(N) | string | "texto" |
| TEXT | string | "texto largo" |
| BOOLEAN | boolean | true |
| INTEGER | integer | 42 |
| TIMESTAMP | datetime ISO8601 | "2026-01-25T14:30:00Z" |
| DATE | date ISO8601 | "2026-01-25" |
| JSONB | object | {"key": "value"} |
| NUMERIC(P,S) | number | 123.45 |

### Validaciones Comunes
| Validación | Descripción | Ejemplo |
|------------|-------------|---------|
| min N | Mínimo N caracteres | min 1 |
| max N | Máximo N caracteres | max 100 |
| email | Formato email válido | email |
| url | URL válida http(s) | url |
| uuid | UUID v4 | uuid |
| > N | Mayor que N | > 0 |
| >= N | Mayor o igual que N | >= 0 |
| enum | Valor de lista | IN ('A', 'B', 'C') |
| unique | Único en contexto | único por branch |
| exists | Debe existir en BD | debe existir en tenant |

### Códigos de Error HTTP
| Código | Uso |
|--------|-----|
| 200 | Operación exitosa (GET, PATCH, DELETE) |
| 201 | Recurso creado (POST) |
| 204 | Sin contenido (DELETE exitoso sin body) |
| 400 | Validación de negocio fallida |
| 401 | No autenticado |
| 403 | Sin permisos |
| 404 | Recurso no encontrado |
| 409 | Conflicto (duplicado) |
| 415 | Content-Type inválido |
| 422 | Validación Pydantic fallida |
| 429 | Rate limit excedido |
| 500 | Error interno |

---

**Fin de la Plantilla**
