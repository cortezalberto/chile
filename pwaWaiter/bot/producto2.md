# Informe de Evolución del Modelo de Datos: De producto1.md a la Implementación Actual

## Resumen Ejecutivo

Este documento analiza el estado actual del modelo de datos del sistema Integrador en relación con las deficiencias identificadas en `producto1.md` y las recomendaciones del modelo canónico de `planteo.md`. Como arquitecto de software senior, presento una evaluación técnica comparativa entre lo propuesto, lo implementado y lo pendiente de implementación.

**Hallazgo principal:** Se ha completado una modernización significativa del modelo de alérgenos que aborda las tres deficiencias más críticas identificadas en `producto1.md`, pero el sistema aún carece de las capacidades completas del modelo canónico de 19 tablas para responder consultas nutricionales complejas.

---

## Análisis del Diagnóstico Original (producto1.md)

El documento `producto1.md` identificó las siguientes limitaciones fundamentales del modelo de 9 tablas:

### Deficiencias Categorizadas por Criticidad

| Criticidad | Deficiencia | Impacto en el Sistema |
|------------|-------------|----------------------|
| **CRÍTICA** | Alérgenos como JSON string (`allergen_ids`) | Violación de 1NF, sin integridad referencial, consultas ineficientes |
| **CRÍTICA** | Sin distinción de presencia (contiene/trazas/libre) | Riesgo de seguridad alimentaria para celíacos y alérgicos severos |
| **CRÍTICA** | Sin modelo de ingredientes | Imposible responder "¿la mayonesa tiene huevo?" |
| **ALTA** | Sin 14 alérgenos obligatorios EU | Incumplimiento normativo EU 1169/2011 |
| **ALTA** | Sin reacciones cruzadas | Riesgo para síndrome látex-frutas y similares |
| **ALTA** | Sin niveles de severidad | No se puede priorizar alertas según riesgo |
| **MEDIA** | Campo `seal` como texto libre | Inconsistencia en perfiles dietéticos |
| **MEDIA** | Sin métodos de cocción | No se puede filtrar "sin fritos" |
| **MEDIA** | Sin perfil sensorial | No se puede recomendar "algo crocante y salado" |
| **BAJA** | Sin modificaciones documentadas | No se sabe si "sin cebolla" es posible |
| **BAJA** | Sin advertencias por plato | Información como "contiene huesos" no se captura |
| **BAJA** | Sin configuración RAG | No hay calibración de confianza en respuestas del chatbot |

---

## Lo Que Se Ha Implementado

### 1. Normalización de la Relación Producto-Alérgeno (Fase 0 Completa)

**Antes (producto1.md líneas 256-284):**
```python
# Campo problemático - violaba 1NF
allergen_ids: Mapped[Optional[str]] = mapped_column(Text)  # JSON array: "[1, 2, 3]"
```

**Después (implementación actual):**
```python
class ProductAllergen(AuditMixin, Base):
    """
    Normalized many-to-many relationship between products and allergens.
    Replaces the allergen_ids JSON field with proper relational structure.
    """
    __tablename__ = "product_allergen"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    tenant_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("tenant.id"))
    product_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("product.id", ondelete="CASCADE"))
    allergen_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("allergen.id", ondelete="RESTRICT"))
    presence_type: Mapped[str] = mapped_column(Text, default="contains")
    risk_level: Mapped[str] = mapped_column(Text, default="standard")
```

**Análisis arquitectónico:**

Esta implementación resuelve completamente las críticas de normalización de `producto1.md`:

1. **Cumplimiento de 1NF:** Cada celda contiene un valor atómico. La relación M:N se modela correctamente con tabla pivote.

2. **Integridad referencial:** Las foreign keys garantizan que no pueden existir referencias huérfanas. El `ondelete="RESTRICT"` impide eliminar alérgenos en uso.

3. **Tres niveles de presencia:** El campo `presence_type` acepta:
   - `contains`: El producto definitivamente contiene el alérgeno
   - `may_contain`: Posibles trazas por contaminación cruzada
   - `free_from`: Garantía de ausencia (certificación activa)

4. **Nivel de riesgo por combinación:** El campo `risk_level` permite indicar si el alérgeno es ingrediente principal (`high`), presencia normal (`standard`) o mínima (`low`).

**Impacto en consultas:**

Ahora es posible ejecutar:
```sql
-- Productos aptos para celíacos (sin gluten Y sin trazas)
SELECT p.name FROM product p
WHERE NOT EXISTS (
    SELECT 1 FROM product_allergen pa
    JOIN allergen a ON a.id = pa.allergen_id
    WHERE pa.product_id = p.id
      AND a.name = 'Gluten'
      AND pa.presence_type IN ('contains', 'may_contain')
);
```

Esto era imposible con el modelo anterior basado en JSON.

---

### 2. Distinción de Alérgenos Obligatorios vs Opcionales (Mejora EU 1169/2011)

**Deficiencia identificada (producto1.md líneas 365-367):**
> "No hay distinción entre los 14 alérgenos de declaración obligatoria y otros alérgenos opcionales."

**Implementación:**
```python
class Allergen(AuditMixin, Base):
    # ... campos existentes ...

    # EU 1169/2011 - 14 mandatory allergens vs optional ones
    is_mandatory: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False, index=True)

    # Severity level for the allergen
    # Values: "mild", "moderate", "severe", "life_threatening"
    severity: Mapped[str] = mapped_column(Text, default="moderate", nullable=False)
```

**Datos sembrados:**

El sistema ahora incluye los 14 alérgenos obligatorios de la UE más 6 opcionales con sus niveles de severidad correctos:

| Categoría | Alérgeno | Severidad |
|-----------|----------|-----------|
| **Obligatorio** | Gluten | severe |
| **Obligatorio** | Crustáceos | life_threatening |
| **Obligatorio** | Huevo | severe |
| **Obligatorio** | Pescado | severe |
| **Obligatorio** | Cacahuete | life_threatening |
| **Obligatorio** | Soja | moderate |
| **Obligatorio** | Lácteos | moderate |
| **Obligatorio** | Frutos de cáscara | life_threatening |
| **Obligatorio** | Apio | moderate |
| **Obligatorio** | Mostaza | moderate |
| **Obligatorio** | Sésamo | severe |
| **Obligatorio** | Sulfitos | moderate |
| **Obligatorio** | Altramuces | moderate |
| **Obligatorio** | Moluscos | severe |
| *Opcional* | Látex | severe |
| *Opcional* | Aguacate | moderate |
| *Opcional* | Kiwi | moderate |
| *Opcional* | Plátano | moderate |
| *Opcional* | Castaña | moderate |
| *Opcional* | Maíz | mild |

**Valor agregado:**

1. El Dashboard puede mostrar los 14 alérgenos obligatorios destacados visualmente
2. El RAG puede priorizar advertencias según severidad
3. Las consultas de filtrado pueden separar "alérgenos críticos" de "sensibilidades menores"

---

### 3. Sistema de Reacciones Cruzadas (Implementación Completa)

**Deficiencia identificada (producto1.md línea 366):**
> "No hay información sobre reacciones cruzadas (por ejemplo, personas alérgicas al látex pueden reaccionar al aguacate)."

**Implementación:**
```python
class AllergenCrossReaction(AuditMixin, Base):
    """
    Cross-reaction information between allergens.
    Example: People allergic to latex may react to avocado, banana, kiwi.
    """
    __tablename__ = "allergen_cross_reaction"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    tenant_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("tenant.id"))
    allergen_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("allergen.id", ondelete="CASCADE"))
    cross_reacts_with_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("allergen.id", ondelete="CASCADE"))
    probability: Mapped[str] = mapped_column(Text, default="medium")  # high, medium, low
    notes: Mapped[Optional[str]] = mapped_column(Text)
```

**Reacciones cruzadas sembradas:**

| Alergia Primaria | Reacciona Con | Probabilidad | Nota Clínica |
|------------------|---------------|--------------|--------------|
| Látex | Aguacate | high | Síndrome látex-frutas: 35-50% reaccionan |
| Látex | Plátano | high | Síndrome látex-frutas: 35-50% reaccionan |
| Látex | Kiwi | high | Síndrome látex-frutas: 35-50% reaccionan |
| Látex | Castaña | medium | Síndrome látex-frutas |
| Crustáceos | Moluscos | medium | Tropomiosina común |
| Cacahuete | Frutos de cáscara | medium | Algunas proteínas similares |
| Frutos de cáscara | Sésamo | low | Posible reactividad |
| Gluten | Maíz | low | Algunos celíacos reaccionan a prolaminas |

**API implementada:**

```
GET  /api/admin/allergens/cross-reactions           # Listar todas
GET  /api/admin/allergens/cross-reactions?allergen_id=X  # Por alérgeno
POST /api/admin/allergens/cross-reactions           # Crear nueva
PATCH /api/admin/allergens/cross-reactions/{id}     # Actualizar
DELETE /api/admin/allergens/cross-reactions/{id}    # Soft delete
```

**Caso de uso habilitado:**

Cuando un usuario indica "soy alérgico al látex", el sistema puede automáticamente advertir sobre productos con aguacate, plátano, kiwi o castaña, incluso si estos no están marcados como alérgenos del producto.

---

### 4. Infraestructura del Modelo Canónico (Fases 1-4 Parcialmente Implementadas)

Aunque no todas las funcionalidades están conectadas al frontend, los modelos de base de datos están creados:

**Fase 1 - Sistema de Ingredientes (Modelos creados):**
```python
class IngredientGroup  # Grupos: proteina, vegetal, lacteo, cereal, condimento, otro
class Ingredient       # Catálogo de ingredientes con flag es_procesado
class SubIngredient    # Sub-ingredientes de procesados (mayonesa → huevo, aceite)
class ProductIngredient  # M:N producto-ingrediente con is_main y notes
```

**Fase 2 - Perfil Dietético (Modelo creado):**
```python
class ProductDietaryProfile  # 7 flags: vegetariano, vegano, sin_gluten, sin_lacteos, celiaco_safe, keto, low_sodium
```

**Fase 3 - Cocción y Sensorial (Modelos creados):**
```python
class CookingMethod    # 8 métodos: horneado, frito, grillado, crudo, hervido, vapor, salteado, braseado
class FlavorProfile    # 8 sabores: suave, intenso, dulce, salado, acido, amargo, umami, picante
class TextureProfile   # 7 texturas: crocante, cremoso, tierno, firme, esponjoso, gelatinoso, granulado
class ProductCookingMethod, ProductFlavor, ProductTexture  # Tablas M:N
class ProductCooking   # 1:1 con uses_oil, prep_time_minutes, cook_time_minutes
```

**Fase 4 - Funcionalidades Avanzadas (Modelos creados):**
```python
class ProductModification  # retirar/sustituir + is_allowed + extra_cost_cents
class ProductWarning       # Advertencias con severity (info/warning/danger)
class ProductRAGConfig     # risk_level (low/medium/high), custom_disclaimer, highlight_allergens
```

**Catálogos sembrados:**

El seed crea automáticamente:
- 8 grupos de ingredientes
- 8 métodos de cocción
- 8 perfiles de sabor
- 7 perfiles de textura

---

## Lo Que Falta Implementar

### Brecha 1: UI de Dashboard para Ingredientes y Perfiles

**Estado:** Los modelos existen en `models.py` pero no hay páginas de Dashboard que los usen.

**Requerido:**
- Página `/ingredients` con CRUD de ingredientes y sub-ingredientes
- Sección de tabs en formulario de Productos para:
  - Perfil dietético (7 checkboxes)
  - Ingredientes (multi-select con búsqueda)
  - Métodos de cocción (multi-select)
  - Perfil sensorial (sabores + texturas)
  - Modificaciones permitidas
  - Advertencias

**Esfuerzo estimado:** 3-5 días de desarrollo frontend

---

### Brecha 2: Endpoints de API para Catálogos

**Estado:** Los modelos existen pero faltan routers.

**Endpoints necesarios:**
```
GET/POST/DELETE /api/admin/ingredients
GET/POST/DELETE /api/admin/ingredients/{id}/sub
GET /api/admin/ingredient-groups
GET /api/admin/cooking-methods
GET /api/admin/flavor-profiles
GET /api/admin/texture-profiles
```

**Esfuerzo estimado:** 1-2 días de desarrollo backend

---

### Brecha 3: Conexión de Productos a Modelos Canónicos

**Estado:** La relación `Product → ProductIngredient` existe pero no se usa en la creación/edición de productos.

**Requerido:**
- Extender `ProductCreate` y `ProductUpdate` para aceptar:
  - `ingredients: list[ProductIngredientInput]`
  - `dietary_profile: DietaryProfileInput`
  - `cooking_methods: list[int]`
  - `flavors: list[int]`
  - `textures: list[int]`
  - `modifications: list[ModificationInput]`
  - `warnings: list[WarningInput]`
  - `rag_config: RAGConfigInput`

**Esfuerzo estimado:** 2-3 días de desarrollo backend

---

### Brecha 4: Vista Consolidada para RAG

**Estado:** No existe un servicio que agregue toda la información canónica de un producto.

**Requerido (como en planteo.md):**
```python
def get_product_complete(db, product_id) -> dict:
    """Retorna producto con toda la info canónica para RAG/pwaMenu"""
    return {
        "id": ...,
        "name": ...,
        "allergens": {
            "contains": [...],
            "may_contain": [...],
            "free_from": [...]
        },
        "dietary": {...},
        "ingredients": [...],
        "cooking_methods": [...],
        "flavors": [...],
        "textures": [...],
        "warnings": [...],
        "rag_config": {...}
    }
```

**Esfuerzo estimado:** 1 día de desarrollo backend

---

### Brecha 5: Mejora del RAG Service

**Estado:** El RAG actual ingesta texto simple de productos/recetas.

**Requerido:**
- Usar la vista consolidada para generar texto enriquecido
- Respetar `risk_level` en las respuestas:
  - `low`: Respuesta directa sin disclaimers
  - `medium`: Incluir "verifica con el personal"
  - `high`: Siempre derivar a consulta presencial

**Esfuerzo estimado:** 1-2 días de desarrollo

---

### Brecha 6: Filtros Avanzados en pwaMenu

**Estado:** pwaMenu tiene filtro básico de alérgenos por IDs.

**Requerido:**
- Soportar `presence_type` (excluir `contains` Y `may_contain` para alergias severas)
- Filtros por perfil dietético (vegano, vegetariano, sin gluten)
- Filtros por método de cocción (sin fritos)
- Filtros por textura/sabor (opcional, baja prioridad)

**Esfuerzo estimado:** 2-3 días de desarrollo frontend

---

## Comparativa: Modelo Canónico vs Implementación Actual

| Aspecto | Canónico (planteo.md) | Implementado | % Completado |
|---------|----------------------|--------------|--------------|
| Tabla principal de platos | `plato` | `product` | 100% (equivalente) |
| Descripciones | `plato_descripcion` | Campo `description` | 50% (falta descripción larga) |
| **Alérgenos normalizados** | 3 tablas M:N | `ProductAllergen` con `presence_type` | **100%** |
| **14 alérgenos obligatorios** | Listados | Sembrados con `is_mandatory=True` | **100%** |
| **Severidad** | No especificado | Campo `severity` implementado | **100%** (mejora adicional) |
| **Reacciones cruzadas** | No especificado | `AllergenCrossReaction` | **100%** (mejora adicional) |
| Sistema de ingredientes | 4 tablas | Modelos creados, sin UI | 50% |
| Perfil dietético | `plato_perfil_alimentario` | `ProductDietaryProfile` | 50% (modelo sin UI) |
| Métodos de cocción | 3 tablas | Modelos y catálogo sembrado | 50% (sin UI) |
| Perfil sensorial | 4 tablas | Modelos y catálogos sembrados | 50% (sin UI) |
| Modificaciones | `plato_modificacion` | `ProductModification` | 50% (modelo sin UI) |
| Advertencias | `plato_advertencia` | `ProductWarning` | 50% (modelo sin UI) |
| Config RAG | `plato_rag` | `ProductRAGConfig` | 50% (modelo sin UI) |

**Promedio de completitud:** ~65%

---

## Recomendaciones Técnicas

### Prioridad 1: Completar la Integración de Alérgenos en Frontend

El backend tiene todo implementado. El Dashboard necesita:

1. Actualizar el formulario de productos para usar el nuevo `AllergenPresenceEditor`
2. Mostrar `is_mandatory` y `severity` en la lista de alérgenos
3. Permitir gestión de reacciones cruzadas desde la página de alérgenos

**Riesgo si no se hace:** Los usuarios seguirán usando el sistema viejo de JSON, perdiendo las nuevas capacidades.

### Prioridad 2: Implementar Página de Ingredientes

El modelo de ingredientes es la base para responder "¿la mayonesa tiene huevo?". Sin esta página:

1. Los productos no tendrán ingredientes asociados
2. El RAG no podrá informar sobre composición
3. Los sub-ingredientes de procesados quedarán sin uso

### Prioridad 3: Vista Consolidada + Mejora RAG

Crear el servicio `get_product_complete()` y actualizar `rag_service.py` para:

1. Generar texto enriquecido con toda la información canónica
2. Respetar niveles de riesgo en respuestas
3. Incluir advertencias automáticamente

### Prioridad 4: Filtros Avanzados en pwaMenu

Actualizar `useAllergenFilter` y crear `useDietaryFilter` para:

1. Soportar exclusión por `contains` + `may_contain`
2. Filtrar por perfil dietético
3. Filtrar por método de cocción (al menos "sin fritos")

---

## Conclusión

El sistema Integrador ha dado un paso significativo hacia el modelo canónico de `planteo.md`. Las tres mejoras críticas del modelo de alérgenos están completamente implementadas en el backend:

1. ✅ **Normalización M:N con tipos de presencia**
2. ✅ **14 alérgenos obligatorios EU + severidad**
3. ✅ **Sistema de reacciones cruzadas**

Sin embargo, el sistema aún opera en un estado de "dualidad": el backend soporta el modelo nuevo, pero el frontend y el RAG no lo aprovechan completamente. La infraestructura de ingredientes, perfiles dietéticos y sensoriales existe en la base de datos pero carece de interfaces de usuario.

El camino restante es principalmente trabajo de frontend (Dashboard y pwaMenu) y la integración del servicio RAG con los nuevos modelos. No hay cambios estructurales pendientes en el backend; las tablas, relaciones e índices están correctamente implementados.

**Pregunta clave que el sistema puede responder ahora:**
- "¿Este producto contiene gluten?" → ✅ Sí, con `ProductAllergen.presence_type = 'contains'`
- "¿Puede tener trazas de frutos secos?" → ✅ Sí, con `presence_type = 'may_contain'`
- "¿Es apto para alérgicos al látex?" → ✅ Sí, consultando `AllergenCrossReaction`

**Pregunta que todavía NO puede responder:**
- "¿La ensalada César tiene huevo?" → ❌ No hay ingredientes asociados al producto
- "¿Qué platos son veganos y crocantes?" → ❌ No hay perfil sensorial conectado
- "¿Puedo pedir la hamburguesa sin cebolla?" → ❌ No hay modificaciones registradas

El objetivo final —un sistema que responda tanto preguntas comerciales como nutricionales complejas— está a 35% de distancia, y el trabajo restante es predecible y acotado.

---

*Documento generado para el proyecto Integrador - Sistema de Gestión de Restaurantes*
*Análisis técnico: Enero 2026*
*Versión: 1.0*
