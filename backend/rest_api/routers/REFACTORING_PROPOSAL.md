# Propuesta de Refactorización: admin.py

**Fecha:** Enero 2026
**Archivo actual:** `admin.py` - **4,829 líneas**, **67 endpoints**, **55 clases Pydantic**

---

## Problema

El archivo `admin.py` viola el principio de Single Responsibility (SRP) al contener:
- CRUD de 14 entidades diferentes
- 55 schemas Pydantic
- Lógica de negocio compleja (exclusiones, asignaciones, reportes)

### Métricas de Complejidad

| Dominio | Endpoints | Líneas Aprox. | Schemas |
|---------|-----------|---------------|---------|
| Tenant | 2 | 50 | 2 |
| Branch | 5 | 150 | 3 |
| Category | 5 | 180 | 3 |
| Subcategory | 5 | 180 | 3 |
| **Product** | 4 | **900** | 15 |
| Allergen | 5 | 160 | 4 |
| CrossReaction | 4 | 200 | 3 |
| Table | 5 | 120 | 3 |
| Sector | 3 | 200 | 4 |
| TableBulk | 1 | 180 | 3 |
| Staff | 5 | 400 | 3 |
| Orders | 2 | 200 | 4 |
| Reports | 3 | 180 | 5 |
| Restore | 1 | 80 | 1 |
| Exclusions | 4 | 400 | 6 |
| AuditLog | 1 | 80 | 1 |
| Assignments | 5 | 400 | 5 |

---

## Propuesta de Estructura

### Estructura de Carpetas Propuesta

```
backend/rest_api/routers/
├── admin/                      # Paquete de routers admin
│   ├── __init__.py            # Exporta router combinado
│   ├── _base.py               # Dependencias, helpers compartidos
│   ├── tenant.py              # ~60 líneas
│   ├── branches.py            # ~180 líneas
│   ├── categories.py          # ~200 líneas
│   ├── subcategories.py       # ~200 líneas
│   ├── products.py            # ~950 líneas (el más grande)
│   ├── allergens.py           # ~400 líneas (incluye cross-reactions)
│   ├── tables.py              # ~500 líneas (incluye sectores, bulk)
│   ├── staff.py               # ~450 líneas
│   ├── orders.py              # ~250 líneas
│   ├── reports.py             # ~200 líneas
│   ├── exclusions.py          # ~450 líneas
│   ├── assignments.py         # ~450 líneas
│   ├── audit.py               # ~100 líneas
│   └── restore.py             # ~100 líneas
├── admin_schemas.py           # TODOS los schemas Pydantic (~700 líneas)
└── admin.py                   # DEPRECATED - importa de admin/ para compatibilidad
```

### Alternativa Simplificada (6 Archivos)

Si se prefiere menos fragmentación:

```
backend/rest_api/routers/
├── admin/
│   ├── __init__.py            # Router combinado
│   ├── catalog.py             # Tenant, Branch, Category, Subcategory, Product (~1500 líneas)
│   ├── inventory.py           # Allergen, CrossReaction (~400 líneas)
│   ├── operations.py          # Table, Sector, TableBulk, Staff, Assignments (~1200 líneas)
│   ├── analytics.py           # Orders, Reports, AuditLog (~400 líneas)
│   └── management.py          # Exclusions, Restore (~600 líneas)
└── admin_schemas.py           # Todos los schemas
```

---

## Implementación Detallada

### 1. Crear `admin_schemas.py` (Schemas Centralizados)

```python
# backend/rest_api/routers/admin_schemas.py
"""
Pydantic schemas for admin API endpoints.
Centralized to avoid circular imports and improve maintainability.
"""

from datetime import datetime, date
from pydantic import BaseModel

# =============================================================================
# Tenant Schemas
# =============================================================================

class TenantOutput(BaseModel):
    id: int
    name: str
    slug: str
    # ... resto de campos

class TenantUpdate(BaseModel):
    name: str | None = None
    # ...

# =============================================================================
# Branch Schemas
# =============================================================================

class BranchOutput(BaseModel):
    # ...

# ... (todos los 55 schemas actuales)
```

### 2. Crear `admin/_base.py` (Dependencias Compartidas)

```python
# backend/rest_api/routers/admin/_base.py
"""
Shared dependencies and helpers for admin routers.
"""

from fastapi import Depends, HTTPException, status
from sqlalchemy.orm import Session

from rest_api.db import get_db
from rest_api.services.soft_delete_service import (
    soft_delete, set_created_by, set_updated_by,
    get_user_id, get_user_email
)
from rest_api.services.admin_events import (
    publish_entity_deleted, publish_cascade_delete
)
from shared.auth import current_user

# Re-export for convenience
__all__ = [
    'get_db', 'current_user', 'Depends', 'HTTPException', 'status', 'Session',
    'soft_delete', 'set_created_by', 'set_updated_by',
    'get_user_id', 'get_user_email',
    'publish_entity_deleted', 'publish_cascade_delete',
]

def require_admin(user: dict = Depends(current_user)):
    """Dependency that requires ADMIN role."""
    if "ADMIN" not in user.get("roles", []):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin role required",
        )
    return user

def require_admin_or_manager(user: dict = Depends(current_user)):
    """Dependency that requires ADMIN or MANAGER role."""
    roles = user.get("roles", [])
    if "ADMIN" not in roles and "MANAGER" not in roles:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin or Manager role required",
        )
    return user
```

### 3. Ejemplo: `admin/branches.py`

```python
# backend/rest_api/routers/admin/branches.py
"""
Branch management endpoints.
"""

from fastapi import APIRouter
from sqlalchemy import select

from rest_api.models import Branch
from rest_api.routers.admin_schemas import (
    BranchOutput, BranchCreate, BranchUpdate
)
from rest_api.routers.admin._base import (
    get_db, current_user, Depends, HTTPException, status, Session,
    soft_delete, set_created_by, set_updated_by,
    get_user_id, get_user_email, publish_entity_deleted,
    require_admin,
)

router = APIRouter(prefix="/branches", tags=["admin-branches"])


@router.get("", response_model=list[BranchOutput])
def list_branches(
    include_deleted: bool = False,
    db: Session = Depends(get_db),
    user: dict = Depends(current_user),
) -> list[BranchOutput]:
    """List all branches for the user's tenant."""
    query = select(Branch).where(Branch.tenant_id == user["tenant_id"])
    if not include_deleted:
        query = query.where(Branch.is_active == True)
    branches = db.execute(query.order_by(Branch.name)).scalars().all()
    return [BranchOutput.model_validate(b) for b in branches]


@router.get("/{branch_id}", response_model=BranchOutput)
def get_branch(
    branch_id: int,
    db: Session = Depends(get_db),
    user: dict = Depends(current_user),
) -> BranchOutput:
    """Get a specific branch."""
    branch = db.scalar(
        select(Branch).where(
            Branch.id == branch_id,
            Branch.tenant_id == user["tenant_id"],
            Branch.is_active == True,
        )
    )
    if not branch:
        raise HTTPException(status_code=404, detail="Branch not found")
    return BranchOutput.model_validate(branch)


@router.post("", response_model=BranchOutput, status_code=201)
def create_branch(
    body: BranchCreate,
    db: Session = Depends(get_db),
    user: dict = Depends(require_admin),
) -> BranchOutput:
    """Create a new branch. Requires ADMIN role."""
    branch = Branch(tenant_id=user["tenant_id"], **body.model_dump())
    set_created_by(branch, get_user_id(user), get_user_email(user))
    db.add(branch)
    db.commit()
    db.refresh(branch)
    return BranchOutput.model_validate(branch)


@router.patch("/{branch_id}", response_model=BranchOutput)
def update_branch(
    branch_id: int,
    body: BranchUpdate,
    db: Session = Depends(get_db),
    user: dict = Depends(require_admin_or_manager),
) -> BranchOutput:
    """Update a branch. Requires ADMIN or MANAGER role."""
    branch = db.scalar(
        select(Branch).where(
            Branch.id == branch_id,
            Branch.tenant_id == user["tenant_id"],
            Branch.is_active == True,
        )
    )
    if not branch:
        raise HTTPException(status_code=404, detail="Branch not found")

    for key, value in body.model_dump(exclude_unset=True).items():
        setattr(branch, key, value)
    set_updated_by(branch, get_user_id(user), get_user_email(user))
    db.commit()
    db.refresh(branch)
    return BranchOutput.model_validate(branch)


@router.delete("/{branch_id}", status_code=204)
def delete_branch(
    branch_id: int,
    db: Session = Depends(get_db),
    user: dict = Depends(require_admin),
) -> None:
    """Soft delete a branch. Requires ADMIN role."""
    branch = db.scalar(
        select(Branch).where(
            Branch.id == branch_id,
            Branch.tenant_id == user["tenant_id"],
            Branch.is_active == True,
        )
    )
    if not branch:
        raise HTTPException(status_code=404, detail="Branch not found")

    soft_delete(db, branch, get_user_id(user), get_user_email(user))
    publish_entity_deleted(
        tenant_id=branch.tenant_id,
        entity_type="branch",
        entity_id=branch_id,
        entity_name=branch.name,
        actor_user_id=get_user_id(user),
    )
```

### 4. `admin/__init__.py` (Router Combinado)

```python
# backend/rest_api/routers/admin/__init__.py
"""
Admin router package.
Combines all admin sub-routers into a single router.
"""

from fastapi import APIRouter

from . import (
    tenant,
    branches,
    categories,
    subcategories,
    products,
    allergens,
    tables,
    staff,
    orders,
    reports,
    exclusions,
    assignments,
    audit,
    restore,
)

router = APIRouter(prefix="/api/admin", tags=["admin"])

# Include all sub-routers
router.include_router(tenant.router)
router.include_router(branches.router)
router.include_router(categories.router)
router.include_router(subcategories.router)
router.include_router(products.router)
router.include_router(allergens.router)
router.include_router(tables.router)
router.include_router(staff.router)
router.include_router(orders.router)
router.include_router(reports.router)
router.include_router(exclusions.router)
router.include_router(assignments.router)
router.include_router(audit.router)
router.include_router(restore.router)
```

### 5. Actualizar `main.py`

```python
# backend/rest_api/main.py

# ANTES:
from rest_api.routers.admin import router as admin_router

# DESPUÉS:
from rest_api.routers.admin import router as admin_router  # Same import, different source!
```

---

## Plan de Migración (Sin Downtime)

### Fase 1: Preparación (~2h)
1. Crear `admin_schemas.py` con todos los schemas
2. Crear `admin/_base.py` con dependencias
3. Verificar que imports funcionan

### Fase 2: Migración Incremental (~4h)
1. Empezar por módulos simples: `tenant.py`, `audit.py`, `restore.py`
2. Continuar con: `branches.py`, `categories.py`, `subcategories.py`
3. Módulos complejos: `products.py`, `staff.py`, `allergens.py`
4. Finalizar: `tables.py`, `assignments.py`, `exclusions.py`, `reports.py`

### Fase 3: Verificación (~1h)
1. Ejecutar tests existentes
2. Verificar OpenAPI spec (`/docs`)
3. Probar endpoints manualmente

### Fase 4: Limpieza
1. Eliminar `admin.py` original
2. Actualizar documentación

---

## Beneficios

| Aspecto | Antes | Después |
|---------|-------|---------|
| **Archivo más grande** | 4,829 líneas | ~950 líneas (products.py) |
| **Archivos** | 1 monolítico | 16 modulares |
| **Navegación** | Difícil | Por dominio |
| **Code Review** | Conflictos frecuentes | Paralelo |
| **Testing** | Complejo | Por módulo |
| **Onboarding** | Intimidante | Gradual |

---

## Riesgos y Mitigación

| Riesgo | Probabilidad | Mitigación |
|--------|-------------|------------|
| Circular imports | Media | Schemas centralizados en `admin_schemas.py` |
| Breaking changes en API | Baja | Mismos paths, solo reorganización interna |
| Tests fallando | Baja | Misma lógica, diferentes archivos |
| Conflictos git | Baja | Migrar en rama feature separada |

---

## Archivos a Crear (Orden Sugerido)

```bash
# 1. Schemas centralizados
touch backend/rest_api/routers/admin_schemas.py

# 2. Paquete admin
mkdir -p backend/rest_api/routers/admin
touch backend/rest_api/routers/admin/__init__.py
touch backend/rest_api/routers/admin/_base.py

# 3. Módulos simples primero
touch backend/rest_api/routers/admin/tenant.py
touch backend/rest_api/routers/admin/audit.py
touch backend/rest_api/routers/admin/restore.py

# 4. CRUD estándar
touch backend/rest_api/routers/admin/branches.py
touch backend/rest_api/routers/admin/categories.py
touch backend/rest_api/routers/admin/subcategories.py

# 5. Módulos complejos
touch backend/rest_api/routers/admin/products.py
touch backend/rest_api/routers/admin/allergens.py
touch backend/rest_api/routers/admin/staff.py
touch backend/rest_api/routers/admin/tables.py

# 6. Funcionalidades específicas
touch backend/rest_api/routers/admin/orders.py
touch backend/rest_api/routers/admin/reports.py
touch backend/rest_api/routers/admin/exclusions.py
touch backend/rest_api/routers/admin/assignments.py
```

---

## ¿Proceder con la Refactorización?

Esta propuesta mantiene:
- ✅ 100% compatibilidad de API (mismos paths)
- ✅ Misma lógica de negocio
- ✅ Mismos schemas Pydantic
- ✅ Mismas validaciones de seguridad

Si deseas proceder, puedo implementar la refactorización fase por fase.
