# Skill: Catalog Developer (BAJO)

## Configuración

```yaml
skill_id: catalog-dev
nivel: BAJO
autonomia: código-autónomo
emoji: 🟢

policy_tickets:
  - PT-CATEGORY-001

historias_usuario:
  - HU-CAT-001 a HU-CAT-007 (Categorías)
  - HU-SUBCAT-001 a HU-SUBCAT-007 (Subcategorías)
  - HU-BRANCH-001 a HU-BRANCH-006 (Sucursales)
  - HU-EXCL-001 a HU-EXCL-005 (Exclusiones)

archivos_permitidos:
  - backend/rest_api/routers/admin/categories.py
  - backend/rest_api/routers/admin/subcategories.py
  - backend/rest_api/routers/admin/branches.py
  - backend/rest_api/services/domain/category_service.py
  - backend/rest_api/services/domain/subcategory_service.py
  - backend/rest_api/services/domain/branch_service.py
  - backend/rest_api/models/catalog.py
  - backend/rest_api/models/exclusion.py
  - backend/tests/test_categories.py
  - backend/tests/test_subcategories.py
  - backend/tests/test_branches.py

archivos_prohibidos:
  - backend/shared/security/*
  - backend/rest_api/routers/auth/*
  - backend/rest_api/routers/billing/*
  - "**/.env*"
```

## Contexto del Dominio

Gestión de catálogo de menú:
- **Categorías**: Agrupaciones principales (Bebidas, Entradas, Principales, Postres)
- **Subcategorías**: Subdivisiones (Vinos Tintos, Vinos Blancos)
- **Sucursales**: Multi-tenant por branch
- **Exclusiones**: Ocultar categorías/subcategorías por branch

### Modelo de Datos

```sql
-- Category
id: BIGINT PRIMARY KEY
name: VARCHAR(100) NOT NULL
image: VARCHAR(500)
display_order: INTEGER DEFAULT 0
tenant_id: BIGINT NOT NULL REFERENCES tenant(id)
-- AuditMixin: is_active, created_at, created_by_id, etc.

-- Subcategory
id: BIGINT PRIMARY KEY
name: VARCHAR(100) NOT NULL
category_id: BIGINT NOT NULL REFERENCES category(id)
display_order: INTEGER DEFAULT 0
tenant_id: BIGINT NOT NULL REFERENCES tenant(id)

-- BranchCategoryExclusion
branch_id: BIGINT REFERENCES branch(id)
category_id: BIGINT REFERENCES category(id)
PRIMARY KEY (branch_id, category_id)

-- BranchSubcategoryExclusion
branch_id: BIGINT REFERENCES branch(id)
subcategory_id: BIGINT REFERENCES subcategory(id)
PRIMARY KEY (branch_id, subcategory_id)
```

## Instrucciones de Implementación

### Paso 1: Identificar la HU

```
¿Qué historia de usuario debo implementar?

HU-CAT-001: Listar Categorías      → GET /api/admin/categories
HU-CAT-002: Ver Categoría          → GET /api/admin/categories/{id}
HU-CAT-003: Crear Categoría        → POST /api/admin/categories
HU-CAT-004: Actualizar Categoría   → PATCH /api/admin/categories/{id}
HU-CAT-005: Eliminar Categoría     → DELETE /api/admin/categories/{id}
HU-CAT-006: Restaurar Categoría    → POST /api/admin/categories/{id}/restore
HU-CAT-007: Reordenar Categorías   → PATCH /api/admin/categories/reorder

(Similar para SUBCAT, BRANCH, EXCL)
```

### Paso 2: Leer Especificación

Lee de `agile/historias/historias_usuario.md` la sección correspondiente.

Ejemplo para HU-CAT-003:

```yaml
endpoint: POST /api/admin/categories
roles_permitidos: [ADMIN, MANAGER]
autenticacion: Bearer Token (JWT)
websocket_event: ENTITY_CREATED
```

**Request:**
```json
{
  "name": "string (required, max 100)",
  "image": "string (optional, URL válida)",
  "display_order": "integer (optional, default 0)"
}
```

**Response (201 Created):**
```json
{
  "id": 1,
  "name": "Bebidas",
  "image": "https://...",
  "display_order": 0,
  "is_active": true,
  "tenant_id": 1
}
```

**Errores:**
```
400: Nombre vacío
400: URL de imagen inválida (SSRF check)
401: No autenticado
403: Rol insuficiente
409: Nombre duplicado en tenant
```

### Paso 3: Implementar

**Router (thin controller):**
```python
# backend/rest_api/routers/admin/categories.py

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from shared.infrastructure.db import get_db
from shared.security.auth import current_user
from rest_api.services.permissions import PermissionContext
from rest_api.services.domain import CategoryService
from shared.utils.admin_schemas import CategoryOutput, CategoryCreate

router = APIRouter(prefix="/categories", tags=["admin-categories"])

@router.post("", response_model=CategoryOutput, status_code=201)
def create_category(
    body: CategoryCreate,
    db: Session = Depends(get_db),
    user: dict = Depends(current_user),
):
    """HU-CAT-003: Crear Nueva Categoría"""
    ctx = PermissionContext(user)
    ctx.require_management()  # Solo ADMIN/MANAGER

    service = CategoryService(db)
    return service.create(
        tenant_id=ctx.tenant_id,
        data=body,
        user_id=ctx.user_id,
        user_email=user.get("email", ""),
    )
```

**Service (business logic):**
```python
# backend/rest_api/services/domain/category_service.py

from rest_api.services.base_service import BaseCRUDService
from rest_api.models import Category
from shared.utils.admin_schemas import CategoryOutput
from shared.utils.validators import validate_image_url
from shared.utils.exceptions import ValidationError

class CategoryService(BaseCRUDService[Category, CategoryOutput]):
    def __init__(self, db: Session):
        super().__init__(
            db=db,
            model=Category,
            output_schema=CategoryOutput,
            entity_name="Categoría",
        )

    def _validate_create(self, data: dict, tenant_id: int) -> None:
        # Validar nombre no vacío
        if not data.get("name") or not data["name"].strip():
            raise ValidationError("El nombre es requerido", field="name")

        # Validar URL de imagen (SSRF prevention)
        if data.get("image"):
            validate_image_url(data["image"])

        # Validar nombre único en tenant
        existing = self._repo.find_one_by(
            tenant_id=tenant_id,
            name=data["name"],
        )
        if existing:
            raise ValidationError("Ya existe una categoría con ese nombre", field="name")
```

### Paso 4: Crear Tests

```python
# backend/tests/test_categories.py

import pytest
from fastapi.testclient import TestClient

def test_create_category_success(client: TestClient, admin_headers: dict):
    """HU-CAT-003: Crear categoría exitosamente"""
    # Arrange
    payload = {
        "name": "Nueva Categoría",
        "image": "https://example.com/image.jpg",
        "display_order": 1,
    }

    # Act
    response = client.post(
        "/api/admin/categories",
        json=payload,
        headers=admin_headers,
    )

    # Assert
    assert response.status_code == 201
    data = response.json()
    assert data["name"] == "Nueva Categoría"
    assert data["display_order"] == 1
    assert data["is_active"] is True


def test_create_category_duplicate_name(client: TestClient, admin_headers: dict, category):
    """HU-CAT-003: Error si nombre duplicado"""
    payload = {"name": category.name}

    response = client.post(
        "/api/admin/categories",
        json=payload,
        headers=admin_headers,
    )

    assert response.status_code == 400
    assert "existe" in response.json()["detail"].lower()


def test_create_category_invalid_image_url(client: TestClient, admin_headers: dict):
    """HU-CAT-003: Error si URL de imagen inválida (SSRF)"""
    payload = {
        "name": "Test",
        "image": "http://localhost:8000/internal",  # SSRF attempt
    }

    response = client.post(
        "/api/admin/categories",
        json=payload,
        headers=admin_headers,
    )

    assert response.status_code == 400


def test_create_category_unauthorized(client: TestClient):
    """HU-CAT-003: Error si no autenticado"""
    response = client.post("/api/admin/categories", json={"name": "Test"})
    assert response.status_code == 401


def test_create_category_waiter_forbidden(client: TestClient, waiter_headers: dict):
    """HU-CAT-003: Error si rol WAITER intenta crear"""
    response = client.post(
        "/api/admin/categories",
        json={"name": "Test"},
        headers=waiter_headers,
    )
    assert response.status_code == 403
```

### Paso 5: Ejecutar y Validar

```bash
# Ejecutar tests
cd backend && python -m pytest tests/test_categories.py -v

# Type check
cd backend && python -m mypy rest_api/routers/admin/categories.py
```

### Paso 6: Commit

```bash
git add backend/rest_api/routers/admin/categories.py \
        backend/rest_api/services/domain/category_service.py \
        backend/tests/test_categories.py

git commit -m "$(cat <<'EOF'
feat(catalog): implement create category endpoint

- Implements HU-CAT-003: Create new category
- Adds validation for duplicate names
- Adds SSRF prevention for image URLs
- Adds tests for success and error cases

Refs: PT-CATEGORY-001

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>
EOF
)"
```

## Checklist Final

- [ ] Router implementado (thin controller)
- [ ] Service implementado (business logic)
- [ ] Validaciones incluidas (nombre, URL, duplicados)
- [ ] Tests escritos y pasando
- [ ] Type hints completos
- [ ] WebSocket event publicado (si aplica)
- [ ] Commit con mensaje descriptivo

## Output Esperado

```
✅ IMPLEMENTACIÓN COMPLETADA
─────────────────────────────────
HU-ID:      HU-CAT-003
Endpoint:   POST /api/admin/categories
Archivos:
  - backend/rest_api/routers/admin/categories.py
  - backend/rest_api/services/domain/category_service.py
  - backend/tests/test_categories.py
Tests:      ✅ 5 pasando
Commit:     abc1234
─────────────────────────────────

🟢 Nivel BAJO - Listo para merge automático
```

---

*Skill catalog-dev - Sistema de Skills*
