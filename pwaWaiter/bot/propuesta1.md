# Propuesta Arquitectónica: Relación entre Receta y Producto

## El Dilema Planteado

El sistema Integrador enfrenta una decisión de diseño fundamental que merece un análisis profundo. La pregunta central es: ¿debe existir una relación obligatoria entre Recipe y Product, donde primero se crea la receta técnica y luego se deriva el producto vendible?

Para responder con rigor técnico, debo primero diseccionar qué representa cada entidad en el modelo de dominio actual y qué necesidades del negocio están en tensión.

---

## Análisis del Modelo Actual

### Product: La Entidad Comercial

El modelo `Product` en su estado actual representa la **unidad mínima vendible** en el restaurante. Contiene:

```
Product
├── name, description, image     → Identidad visual para el cliente
├── category_id, subcategory_id  → Clasificación en el menú
├── featured, popular, badge     → Marketing y promoción
├── seal (deprecated)            → Perfil dietético simple
├── allergen_ids (deprecated)    → Alérgenos como JSON
└── Relaciones del modelo canónico:
    ├── ProductAllergen[]        → Alérgenos normalizados con presence_type
    ├── ProductIngredient[]      → Ingredientes
    ├── ProductDietaryProfile    → Perfil dietético estructurado
    ├── ProductCooking           → Info de cocción
    ├── ProductModification[]    → Modificaciones permitidas
    ├── ProductWarning[]         → Advertencias
    └── ProductRAGConfig         → Configuración para el chatbot
```

El Product es consumido por `pwaMenu` para mostrar el menú al cliente, y su precio se define por sucursal en `BranchProduct`.

### Recipe: La Ficha Técnica de Cocina

El modelo `Recipe` representa el **conocimiento técnico** de cómo preparar un plato:

```
Recipe
├── name, description, image     → Identificación
├── branch_id                    → Sucursal específica
├── product_id (opcional)        → Enlace al producto
├── subcategory_id               → Clasificación
├── cuisine_type, difficulty     → Metadata culinaria
├── prep_time_minutes            → Tiempo de preparación
├── cook_time_minutes            → Tiempo de cocción
├── servings                     → Porciones
├── calories_per_serving         → Información nutricional
├── ingredients (JSONB)          → Lista de ingredientes con cantidades
├── preparation_steps (JSONB)    → Pasos de preparación
├── chef_notes                   → Notas del chef
├── presentation_tips            → Tips de emplatado
├── storage_instructions         → Instrucciones de almacenamiento
├── dietary_tags (JSONB)         → Etiquetas dietéticas
├── cost_cents                   → Costo de producción
├── is_ingested                  → Flag de ingesta al RAG
└── RecipeAllergen[]             → Alérgenos normalizados
```

La Recipe es creada por el personal de cocina y puede ser ingestada al chatbot RAG para responder consultas de clientes.

---

## La Propuesta: "Recipe First"

Tu propuesta plantea un flujo donde:

1. **Primero** se crea la Recipe con toda la información técnica detallada
2. **Luego** se crea el Product derivado de esa receta, con datos simplificados para venta

Este enfoque tiene mérito conceptual: la receta es el "blueprint" y el producto es su "manifestación comercial". Sin embargo, antes de adoptarlo, debo señalar varios aspectos críticos.

---

## Argumentos a Favor del Enfoque "Recipe First"

### 1. Coherencia Semántica del Dominio

Desde una perspectiva de Domain-Driven Design, tiene sentido que el conocimiento técnico (cómo se hace algo) preceda a su representación comercial (cómo se vende). Un chef no puede vender lo que no sabe preparar.

### 2. Single Source of Truth para Información Nutricional

Si la receta contiene los ingredientes, alérgenos y valores nutricionales, y el producto los hereda, se elimina la duplicación de datos. Actualmente, tanto Product como Recipe tienen campos similares (alérgenos, perfil dietético), lo que viola el principio DRY.

### 3. Facilitación del RAG

El chatbot necesita información detallada para responder preguntas como "¿la milanesa tiene huevo?". Si esa información vive en Recipe y Product la hereda, la fuente de verdad es clara.

### 4. Trazabilidad de Cambios

Si cambia una receta (nuevo ingrediente, diferente método de cocción), el producto asociado puede ser notificado o actualizado automáticamente.

---

## Argumentos en Contra del Enfoque "Recipe First" Obligatorio

### 1. No Todo Producto Vendible Tiene Receta

Consideremos estos casos del mundo real:

- **Bebidas embotelladas**: Una Coca-Cola no tiene receta; es un producto que se compra y revende.
- **Productos externos**: Pan de proveedores, postres de terceros, agua mineral.
- **Productos simples**: Una porción de papas fritas congeladas no necesita ficha técnica elaborada.
- **Servicios**: Cubierto, servicio de mesa, descorche.

Forzar una Recipe para estos ítems genera trabajo burocrático sin valor agregado.

### 2. Diferentes Ciclos de Vida

El Product tiene un ciclo de vida comercial (se activa/desactiva según disponibilidad, temporada, promociones). La Recipe tiene un ciclo de vida técnico (se perfecciona, se documenta, se entrena al personal). Acoplarlos tightly puede generar fricción operativa.

Por ejemplo: el chef actualiza la receta para mejorar la técnica, pero esto no debería afectar el precio o la disponibilidad del producto en el menú.

### 3. Diferentes Propietarios

En un restaurante real:

- El **Product** es gestionado por el manager/administrador (precios, disponibilidad, marketing)
- La **Recipe** es gestionada por el chef/cocina (técnica, ingredientes, costos)

Un modelo que obliga a crear Recipe primero puede invertir la cadena de responsabilidades naturales.

### 4. Complejidad de Onboarding

Un restaurante nuevo que quiere cargar su menú rápidamente se vería obligado a escribir fichas técnicas detalladas antes de poder vender. Esto es una barrera de entrada significativa.

---

## Mi Recomendación Arquitectónica

Propongo un enfoque híbrido que respeta ambas realidades del negocio:

### Modelo: Recipe Opcional pero Enriquecedora

```
Product (entidad principal, siempre requerida para vender)
├── Datos comerciales mínimos (nombre, precio, categoría, imagen)
├── Alérgenos simplificados (ProductAllergen) → obligatorios
├── recipe_id: Optional[int] → FK a Recipe (opcional)
└── hereda_de_receta: bool → flag para indicar herencia

Recipe (entidad técnica, opcional)
├── Datos técnicos completos (ingredientes, pasos, tiempos)
├── Alérgenos detallados (RecipeAllergen)
├── products: list[Product] → Relación inversa (1:N)
└── Una receta puede dar origen a múltiples productos
```

### Flujo Operativo Recomendado

**Caso A: Producto Simple (sin receta)**
1. Admin crea Product directamente con datos mínimos
2. Asigna alérgenos manualmente (ProductAllergen)
3. Producto disponible para venta

**Caso B: Producto con Receta (flujo completo)**
1. Chef crea Recipe con toda la información técnica
2. Al guardar, sistema ofrece: "¿Crear producto vendible basado en esta receta?"
3. Si acepta, se crea Product con:
   - `recipe_id` = Recipe.id
   - Alérgenos heredados de RecipeAllergen → ProductAllergen
   - Descripción derivada de Recipe.description
   - `hereda_de_receta` = true
4. Cambios en Recipe pueden propagarse a Product (configurable)

**Caso C: Receta standalone (documentación interna)**
1. Chef crea Recipe sin producto asociado
2. Útil para: mise en place, preparaciones base, procedimientos
3. No aparece en menú pero está disponible para RAG

### Implementación Técnica

```python
# En models.py
class Product(AuditMixin, Base):
    # ... campos existentes ...

    # Relación opcional con Recipe
    recipe_id: Mapped[Optional[int]] = mapped_column(
        BigInteger, ForeignKey("recipe.id"), index=True
    )
    inherits_from_recipe: Mapped[bool] = mapped_column(Boolean, default=False)

    # Relación
    recipe: Mapped[Optional["Recipe"]] = relationship(back_populates="products")

class Recipe(AuditMixin, Base):
    # ... campos existentes ...

    # Relación inversa: una receta puede tener múltiples productos
    # (ej: "Receta de Milanesa" → "Milanesa Napolitana", "Milanesa a Caballo", "Milanesa Simple")
    products: Mapped[list["Product"]] = relationship(back_populates="recipe")
```

### Servicio de Sincronización

```python
# En services/recipe_product_sync.py
def sync_product_from_recipe(db: Session, product: Product) -> None:
    """
    Sincroniza datos de Recipe a Product si hereda de receta.
    Llamar cuando Recipe es actualizada.
    """
    if not product.inherits_from_recipe or not product.recipe_id:
        return

    recipe = product.recipe

    # Sincronizar alérgenos: RecipeAllergen → ProductAllergen
    current_allergen_ids = {pa.allergen_id for pa in product.product_allergens}
    recipe_allergen_ids = {ra.allergen_id for ra in recipe.recipe_allergens if ra.is_active}

    # Agregar nuevos
    for allergen_id in recipe_allergen_ids - current_allergen_ids:
        db.add(ProductAllergen(
            tenant_id=product.tenant_id,
            product_id=product.id,
            allergen_id=allergen_id,
            presence_type="contains",
        ))

    # Marcar para revisión los que ya no están en receta
    # (No eliminar automáticamente - puede haber alérgenos adicionales)
```

---

## Sobre la "Doble Carga" Inicial

Tu preocupación sobre la doble carga es válida pero tiene matices:

### Escenario 1: Restaurant Nuevo con Chef Dedicado

En este caso, el flujo Recipe First es natural:
- El chef documenta sus recetas (trabajo que ya haría para entrenar personal)
- El sistema genera productos automáticamente
- La "carga" es en realidad **documentación valiosa** que el negocio necesita

### Escenario 2: Restaurant en Migración o Fast Food

En este caso, Recipe First sería una barrera:
- Ya tienen menú definido con precios
- No necesitan fichas técnicas elaboradas
- Quieren estar operativos rápidamente

### Solución: Onboarding Progresivo

El sistema debería soportar ambos flujos:

```
Modo Rápido (sin recetas):
┌─────────────────────────────────────────┐
│  Crear Producto Rápido                  │
│  ─────────────────────                  │
│  Nombre: [Milanesa Napolitana        ]  │
│  Precio: [$15.500                    ]  │
│  Categoría: [Platos Principales      ]  │
│  Alérgenos: [🌾 Gluten] [🥛 Lácteos] [🥚 Huevo]  │
│                                         │
│  [Crear Producto]                       │
│                                         │
│  ¿Agregar ficha técnica después? [Sí]  │
└─────────────────────────────────────────┘

Modo Completo (con receta):
┌─────────────────────────────────────────┐
│  Crear Receta Técnica                   │
│  ─────────────────────                  │
│  [Paso 1: Información básica       ]    │
│  [Paso 2: Ingredientes             ]    │
│  [Paso 3: Preparación              ]    │
│  [Paso 4: Alérgenos y restricciones]    │
│  [Paso 5: Crear producto vendible  ]    │
│                                         │
│  [✓] Generar producto automáticamente   │
│  [  ] Solo guardar receta (interno)     │
└─────────────────────────────────────────┘
```

---

## Conclusión

**No recomiendo hacer obligatoria la creación de Recipe antes de Product.**

Recomiendo en cambio:

1. **Mantener Product como entidad independiente** para flexibilidad operativa
2. **Agregar `recipe_id` opcional a Product** para enlazar cuando corresponda
3. **Crear herramienta de "derivación" de Product desde Recipe** para el flujo completo
4. **Implementar sincronización configurable** de alérgenos e información nutricional
5. **Permitir Recipe standalone** para documentación interna que no se vende

Este enfoque respeta la realidad operativa de diferentes tipos de restaurantes (desde fast food hasta fine dining), permite el onboarding progresivo, y mantiene la coherencia de datos cuando la relación existe.

La "doble carga" que mencionas se convierte en **carga opcional con beneficios**: quienes la hacen obtienen datos enriquecidos para el RAG y mejor información nutricional; quienes no la necesitan pueden operar con productos simples.

---

## Diagrama de Flujo Propuesto

```
                    ┌─────────────────┐
                    │   Restaurant    │
                    │    Onboarding   │
                    └────────┬────────┘
                             │
              ┌──────────────┼──────────────┐
              │              │              │
              ▼              ▼              ▼
        ┌──────────┐  ┌──────────┐  ┌──────────┐
        │  Modo    │  │  Modo    │  │  Modo    │
        │  Rápido  │  │ Híbrido  │  │ Completo │
        └────┬─────┘  └────┬─────┘  └────┬─────┘
             │             │             │
             ▼             │             ▼
        ┌─────────┐        │        ┌─────────┐
        │ Product │        │        │ Recipe  │
        │ (solo)  │        │        │ (first) │
        └────┬────┘        │        └────┬────┘
             │             │             │
             │             ▼             ▼
             │        ┌─────────┐   ┌─────────┐
             │        │ Product │   │ Product │
             │        │    +    │   │ (auto)  │
             │        │ Recipe  │   └────┬────┘
             │        │ (link)  │        │
             │        └────┬────┘        │
             │             │             │
             └─────────────┼─────────────┘
                           │
                           ▼
                    ┌─────────────┐
                    │   pwaMenu   │
                    │ (consume    │
                    │  Product)   │
                    └─────────────┘
```

---

*Documento técnico: Enero 2026*
*Proyecto Integrador - Sistema de Gestión de Restaurantes*
