# Auditoría del Modelo de Base de Datos

**Fecha:** 2026-01-26
**Archivos analizados:** 19 modelos SQLAlchemy en `backend/rest_api/models/`
**Total de hallazgos:** 28 issues

---

## HALLAZGOS CRÍTICOS (4)

### 1. UniqueConstraint faltante en tablas M:N
**Archivos:** `product_profile.py` (líneas 114-198)
**Tablas afectadas:** `ProductCookingMethod`, `ProductFlavor`, `ProductTexture`

**Problema:** Estas tablas M:N tienen `tenant_id` para aislamiento pero NO tienen UniqueConstraint para prevenir entradas duplicadas.

```python
# Código actual (ProductCookingMethod línea 135-138)
__table_args__ = (
    Index("ix_product_cooking_method_product", "product_id"),
    Index("ix_product_cooking_method_method", "cooking_method_id"),
)
# ❌ Falta UniqueConstraint!
```

**Solución:**
```python
__table_args__ = (
    UniqueConstraint("product_id", "cooking_method_id", name="uq_product_cooking_method"),
    Index("ix_product_cooking_method_product", "product_id"),
    Index("ix_product_cooking_method_method", "cooking_method_id"),
)
```

---

### 2. CookingMethod, FlavorProfile, TextureProfile sin tenant_id
**Archivo:** `product_profile.py` (líneas 50-96)

**Problema:** Estas tablas catálogo son GLOBALES, no aisladas por tenant:

```python
class CookingMethod(AuditMixin, Base):
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    name: Mapped[str] = mapped_column(Text, nullable=False, unique=True)  # ❌ GLOBAL unique!
    # ❌ NO tiene tenant_id!
```

**Solución:**
```python
class CookingMethod(AuditMixin, Base):
    tenant_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("tenant.id"), nullable=False, index=True)
    name: Mapped[str] = mapped_column(Text, nullable=False)

    __table_args__ = (
        UniqueConstraint("tenant_id", "name", name="uq_cooking_method_tenant_name"),
    )
```

---

### 3. CuisineType sin tenant_id
**Archivo:** `product_profile.py` (líneas 99-112)

**Problema:** Misma falta de aislamiento multi-tenant:

```python
class CuisineType(AuditMixin, Base):
    # ❌ NO tiene tenant_id!
    name: Mapped[str] = mapped_column(Text, nullable=False, unique=True, index=True)
```

**Solución:** Agregar `tenant_id` y actualizar constraint como en el punto 2.

---

### 4. ServiceCall.acked_by_user_id sin index
**Archivo:** `kitchen.py` (líneas 127-129)

**Problema:** FK sin índice para queries frecuentes de estado:

```python
acked_by_user_id: Mapped[Optional[int]] = mapped_column(
    BigInteger, ForeignKey("app_user.id")  # ❌ Sin index!
)
```

**Solución:**
```python
acked_by_user_id: Mapped[Optional[int]] = mapped_column(
    BigInteger, ForeignKey("app_user.id"), index=True  # ✓ Agregar index
)
```

---

## HALLAZGOS ALTOS (6)

### 5. Product sin relaciones inversas a Profile tables
**Archivo:** `catalog.py`
**Tablas afectadas:** ProductCookingMethod, ProductFlavor, ProductTexture

**Problema:** No hay forma de navegar desde Product hacia estas tablas sin JOINs explícitos.

**Solución:** Agregar en Product:
```python
cooking_methods: Mapped[list["ProductCookingMethod"]] = relationship(back_populates="product")
flavors: Mapped[list["ProductFlavor"]] = relationship(back_populates="product")
textures: Mapped[list["ProductTexture"]] = relationship(back_populates="product")
```

Y en cada tabla M:N agregar:
```python
product: Mapped["Product"] = relationship(back_populates="cooking_methods")  # etc.
```

---

### 6. Category/Subcategory sin UniqueConstraint
**Archivo:** `catalog.py`

**Problema:** Pueden existir categorías duplicadas en la misma branch:

```python
# Category no tiene constraint para (branch_id, name)
# Subcategory no tiene constraint para (category_id, name)
```

**Solución:**
```python
# En Category
__table_args__ = (
    UniqueConstraint("branch_id", "name", name="uq_category_branch_name"),
    Index("ix_category_branch_active", "branch_id", "is_active"),
)

# En Subcategory
__table_args__ = (
    UniqueConstraint("category_id", "name", name="uq_subcategory_category_name"),
)
```

---

### 7. Ingredient sin UniqueConstraint por tenant
**Archivo:** `ingredient.py` (línea 49)

**Problema:** Nombres de ingredientes pueden duplicarse:

```python
name: Mapped[str] = mapped_column(Text, nullable=False)  # ❌ Sin unicidad
```

**Solución:**
```python
__table_args__ = (
    UniqueConstraint("tenant_id", "name", name="uq_ingredient_tenant_name"),
)
```

---

### 8. Diner falta index compuesto
**Archivo:** `customer.py` (líneas 152-154)

**Problema:** Queries comunes como "obtener diners en sesión para reconocimiento de cliente" no tienen índice optimizado.

**Solución:**
```python
__table_args__ = (
    UniqueConstraint("session_id", "local_id", name="uq_diner_session_local_id"),
    Index("ix_diner_session_local_id", "session_id", "local_id"),
    Index("ix_diner_session_customer", "session_id", "customer_id"),  # ✓ Agregar
    Index("ix_diner_customer_device", "customer_id", "device_id"),    # ✓ Agregar
)
```

---

### 9. Recipe relaciones sin back_populates
**Archivo:** `recipe.py` (líneas 134-136)

**Problema:** Relaciones definidas sin back_populates:

```python
tenant: Mapped["Tenant"] = relationship()      # ❌ Sin back_populates
branch: Mapped["Branch"] = relationship()      # ❌ Sin back_populates
subcategory: Mapped[Optional["Subcategory"]] = relationship()  # ❌ Sin back_populates
```

**Solución:** Agregar back_populates o verificar que las entidades inversas tengan las relaciones definidas.

---

### 10. Subcategory sin tenant_id directo
**Archivo:** `catalog.py` (líneas 61-90)

**Problema:** Requiere JOIN extra a través de Category para filtrar por tenant:

```python
class Subcategory(AuditMixin, Base):
    # ❌ Sin tenant_id - debe hacer JOIN con Category
    category_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("category.id"), nullable=False, index=True
    )
```

**Solución:**
```python
tenant_id: Mapped[int] = mapped_column(
    BigInteger, ForeignKey("tenant.id"), nullable=False, index=True
)
```

---

## HALLAZGOS MEDIOS (9)

### 11. Payment.payer_diner_id sin relationship
**Archivo:** `billing.py` (línea 93)

```python
payer_diner_id: Mapped[Optional[int]] = mapped_column(
    BigInteger, ForeignKey("diner.id"), index=True
)  # ❌ Sin relationship!
```

**Solución:** `payer_diner: Mapped[Optional["Diner"]] = relationship()`

---

### 12. Payment.registered_by_waiter_id sin relationship
**Archivo:** `billing.py` (línea 110)

```python
registered_by_waiter_id: Mapped[Optional[int]] = mapped_column(
    BigInteger, ForeignKey("app_user.id"), index=True
)  # ❌ Sin relationship!
```

**Solución:** `registered_by_waiter: Mapped[Optional["User"]] = relationship()`

---

### 13. ServiceCall.acked_by_user_id sin relationship
**Archivo:** `kitchen.py` (línea 127)

**Solución:** `acked_by: Mapped[Optional["User"]] = relationship()`

---

### 14. TableSession.assigned_waiter_id sin relationship
**Archivo:** `table.py` (línea 92)

**Solución:**
```python
assigned_waiter: Mapped[Optional["User"]] = relationship("User", foreign_keys=[assigned_waiter_id])
```

---

### 15. TableSession.opened_by_waiter_id sin relationship
**Archivo:** `table.py` (línea 104)

**Solución:**
```python
opened_by_waiter: Mapped[Optional["User"]] = relationship("User", foreign_keys=[opened_by_waiter_id])
```

---

### 16. Round.submitted_by_waiter_id sin relationship
**Archivo:** `order.py` (línea 59)

**Solución:** `submitted_by_waiter: Mapped[Optional["User"]] = relationship()`

---

### 17. Round.idempotency_key falta UniqueConstraint compuesto
**Archivo:** `order.py` (línea 53)

**Problema:** El idempotency_key está indexado pero debería ser único por sesión.

**Solución:**
```python
__table_args__ = (
    UniqueConstraint("table_session_id", "idempotency_key", name="uq_round_session_idempotency"),
    Index("ix_round_branch_status", "branch_id", "status"),
    Index("ix_round_status_submitted", "status", "submitted_at"),
)
```

---

### 18. AuditLog falta index compuesto
**Archivo:** `audit.py` (línea 36)

**Problema:** Queries típicas filtran por (tenant_id, entity_type, action) pero solo hay índices individuales.

**Solución:**
```python
__table_args__ = (
    Index("ix_audit_log_tenant_entity_type", "tenant_id", "entity_type"),
    Index("ix_audit_log_tenant_entity_id", "tenant_id", "entity_id"),
)
```

---

### 19. KnowledgeDocument comentario erróneo
**Archivo:** `knowledge.py` (línea 40)

**Problema:** Comentario dice 1536 dimensiones (OpenAI ada) pero código usa 768 (nomic-embed-text):

```python
# Vector embedding (1536 dimensions for nomic-embed-text)  # ❌ Comentario incorrecto
embedding: Mapped[list[float]] = mapped_column(Vector(768), nullable=True)
```

**Solución:** Corregir comentario a "768 dimensions".

---

## HALLAZGOS BAJOS (4)

### 20. Product.featured sin index
**Archivo:** `catalog.py` (línea 115)

```python
featured: Mapped[bool] = mapped_column(Boolean, default=False)  # ❌ Sin index
```

**Solución:** `featured: Mapped[bool] = mapped_column(Boolean, default=False, index=True)`

---

### 21. BranchProduct.is_available sin index
**Archivo:** `catalog.py` (línea 201)

```python
is_available: Mapped[bool] = mapped_column(Boolean, default=True)  # ❌ Sin index
```

**Solución:** Agregar `index=True`

---

### 22. Customer.segment sin index
**Archivo:** `customer.py` (línea 70)

```python
segment: Mapped[Optional[str]] = mapped_column(Text, default="new")  # ❌ Sin index
```

**Solución:** Agregar `index=True`

---

### 23. Promotion dates como Text
**Archivo:** `promotion.py`

**Problema:** Fechas almacenadas como strings pueden tener valores inválidos:

```python
start_date: Mapped[str] = mapped_column(Text, nullable=False)  # "2024-01-01"
end_date: Mapped[str] = mapped_column(Text, nullable=False)    # "2024-12-31"
```

**Solución:** Usar tipo Date o agregar CHECK constraint:
```python
from sqlalchemy import Date
start_date: Mapped[date] = mapped_column(Date, nullable=False)
```

---

## RESUMEN

| Categoría | Cantidad | Severidad |
|-----------|----------|-----------|
| Missing Unique Constraints | 5 | CRÍTICO/ALTO |
| Missing Relationships | 8 | MEDIO |
| Missing Indexes | 6 | MEDIO/BAJO |
| Multi-Tenant Isolation | 4 | CRÍTICO/ALTO |
| Missing FK Indexes | 3 | ALTO |
| Documentation Issues | 2 | BAJO |
| **TOTAL** | **28** | - |

---

## PLAN DE IMPLEMENTACIÓN

### Fase 1 - CRÍTICOS (Prioridad Máxima)
1. Agregar UniqueConstraints a ProductCookingMethod, ProductFlavor, ProductTexture
2. Agregar tenant_id a CookingMethod, FlavorProfile, TextureProfile, CuisineType
3. Agregar index a ServiceCall.acked_by_user_id

### Fase 2 - ALTOS
1. Agregar relaciones inversas en Product para profile tables
2. Agregar UniqueConstraints a Category y Subcategory
3. Agregar UniqueConstraint a Ingredient
4. Agregar indexes compuestos a Diner
5. Agregar tenant_id a Subcategory

### Fase 3 - MEDIOS
1. Agregar 8 relationships faltantes (Payment, ServiceCall, TableSession, Round)
2. Agregar UniqueConstraint compuesto a Round.idempotency_key
3. Agregar indexes compuestos a AuditLog
4. Corregir comentario en KnowledgeDocument

### Fase 4 - BAJOS
1. Agregar indexes a Product.featured, BranchProduct.is_available, Customer.segment
2. Cambiar Promotion dates de Text a Date

---

## NOTAS ADICIONALES

### Política de Cascade Delete
Se detectó inconsistencia en políticas de ondelete:
- ProductAllergen: CASCADE para product, RESTRICT para allergen
- ProductIngredient: CASCADE para product, RESTRICT para ingredient
- RecipeAllergen: CASCADE para ambos

**Recomendación:** Documentar y aplicar consistentemente:
- Product FK: CASCADE (eliminar M:N cuando se elimina producto)
- Reference FK (Allergen, Ingredient): RESTRICT (proteger datos de referencia)

### Campos JSON vs Relaciones
Varios modelos usan JSON en lugar de relaciones:
- Recipe.ingredients, Recipe.preparation_steps, Recipe.modifications
- Customer.device_ids, Customer.favorite_product_ids

**Recomendación:** Mantener como JSON si son solo lectura, normalizar si se filtran/unen frecuentemente.
