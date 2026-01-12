# Ficha Técnica: Modelo de Datos de Productos del Sistema Integrador

## Introducción y Contexto

Este documento constituye un análisis exhaustivo del modelo de base de datos actual del sistema Integrador para la gestión de productos, categorías, subcategorías y sucursales. El propósito de este análisis es doble: por un lado, documentar cómo funciona el sistema actual para que futuros desarrolladores comprendan su arquitectura; por otro lado, identificar las limitaciones estructurales que impiden responder a consultas nutricionales complejas que los comensales modernos esperan poder realizar.

### El Problema que Enfrentamos

En la era actual de la gastronomía, los comensales llegan a los restaurantes con necesidades de información cada vez más sofisticadas. Ya no basta con saber el nombre del plato y su precio. Una persona con enfermedad celíaca necesita saber no solo si un plato contiene gluten, sino si fue preparado en una cocina que garantiza ausencia de contaminación cruzada. Una persona vegana quiere saber si la mayonesa de la hamburguesa contiene huevo, aunque el huevo no sea un ingrediente visible del plato. Un padre preocupado por la alergia de su hijo a los frutos secos necesita saber si el postre "puede contener trazas" aunque no los tenga como ingrediente directo.

El modelo de datos actual del sistema Integrador fue diseñado con un enfoque comercial y operativo: gestionar productos, precios por sucursal, disponibilidad y categorización para el menú. Este enfoque resuelve eficientemente los problemas de un restaurante multi-sucursal que necesita administrar su catálogo. Sin embargo, cuando intentamos responder preguntas nutricionales detalladas, el modelo muestra sus limitaciones fundamentales.

### Contexto del Sistema Integrador

El sistema Integrador es un monorepo de gestión de restaurantes que opera bajo un modelo multi-tenant. Esto significa que una única instalación del sistema puede servir a múltiples restaurantes independientes, cada uno con sus propias sucursales, productos y configuraciones. Esta arquitectura multi-tenant influye profundamente en cómo se estructuran los datos.

El modelo de productos está diseñado para resolver cuatro problemas operativos fundamentales:

1. **Aislamiento de datos entre restaurantes (multi-tenancy)**: Cada restaurante (tenant) tiene sus propias categorías, productos y precios, completamente aislados de otros restaurantes en el sistema. Un restaurante de comida italiana no ve ni interfiere con los datos de una pizzería vecina, aunque ambos usen el mismo sistema.

2. **Flexibilidad de precios por sucursal**: Un mismo producto puede tener diferentes precios en diferentes ubicaciones. Una hamburguesa puede costar $1500 en la sucursal del centro y $1300 en la sucursal del barrio, reflejando diferencias en costos operativos o estrategias de mercado.

3. **Control de disponibilidad por sucursal**: No todas las sucursales venden todos los productos. La sucursal del aeropuerto puede no ofrecer el menú completo de postres que tiene la sucursal principal, ya sea por limitaciones de cocina o por decisiones comerciales.

4. **Exclusiones granulares de menú**: Categorías o subcategorías completas pueden excluirse de sucursales específicas. Si una sucursal no tiene parrilla, toda la categoría "Carnes a la Parrilla" puede excluirse sin tener que desactivar producto por producto.

Estos cuatro problemas están bien resueltos por el modelo actual. El problema surge cuando queremos ir más allá de la gestión operativa y entrar en el terreno de la información nutricional detallada.

---

## Arquitectura del Modelo Actual

### Filosofía de Diseño

El modelo actual sigue una filosofía de "productos como unidades comerciales". Un producto es algo que se vende, tiene un nombre, un precio, y pertenece a una categoría para facilitar la navegación del menú. Esta visión es perfectamente válida para la operación diaria de un restaurante, pero trata al producto como una "caja negra" cuyo contenido interno (ingredientes, métodos de preparación, perfiles nutricionales) no se modela explícitamente.

La decisión de diseño más significativa fue hacer que los productos sean entidades globales al tenant (restaurante) mientras que las categorías son específicas de cada sucursal. Esto significa que el producto "Milanesa Napolitana" existe una sola vez en el sistema para todo el restaurante, pero cada sucursal puede tener su propia estructura de categorías donde ubicarlo y su propio precio para venderlo.

Esta decisión tiene implicaciones profundas. Por un lado, simplifica la gestión del catálogo: si cambio la descripción de la Milanesa Napolitana, el cambio se refleja en todas las sucursales automáticamente. Por otro lado, crea una tensión arquitectónica: el producto referencia una categoría que pertenece a una sucursal específica, lo que puede generar inconsistencias si no se maneja cuidadosamente.

### Diagrama de Entidades y Relaciones

El siguiente diagrama muestra cómo se conectan las entidades principales del modelo de productos:

```
Tenant (1)
    │
    ├──── (N) Branch
    │         │
    │         ├──── (N) BranchProduct ────┐
    │         │                           │
    │         ├──── (N) BranchCategoryExclusion ──── Category
    │         │                                         │
    │         └──── (N) BranchSubcategoryExclusion ──── Subcategory
    │                                                      │
    ├──── (N) Category ─────────────────────────────────┘
    │         │
    │         └──── (N) Subcategory
    │                    │
    ├──── (N) Product ───┴─────────────────────────────── BranchProduct
    │         │
    │         └──── allergen_ids (JSON string) ──── Allergen (referencia lógica)
    │
    └──── (N) Allergen
```

Este diagrama revela inmediatamente una de las debilidades del modelo: la relación entre productos y alérgenos no está normalizada. En lugar de una tabla de relación muchos-a-muchos, los alérgenos se almacenan como un string JSON dentro del producto. Esta decisión, probablemente tomada para simplificar el desarrollo inicial, tiene consecuencias significativas para las consultas nutricionales.

---

## Tablas del Modelo

### 1. Tenant (Restaurante): La Raíz del Árbol

La tabla `tenant` es el punto de partida de todo el modelo. Representa un restaurante o marca gastronómica como entidad de negocio independiente. Todo lo demás en el sistema existe dentro del contexto de un tenant.

**¿Por qué es importante?** El tenant proporciona el aislamiento de datos que permite que múltiples restaurantes usen el mismo sistema sin interferir entre sí. Cuando un usuario del Dashboard inicia sesión, el sistema identifica a qué tenant pertenece y filtra automáticamente todos los datos para mostrar solo los de ese restaurante.

| Campo | Tipo | Nullable | Descripción |
|-------|------|----------|-------------|
| `id` | BigInteger | NO | PK, identificador único |
| `name` | Text | NO | Nombre del restaurante |
| `slug` | Text | NO | URL-friendly identifier, UNIQUE |
| `description` | Text | SI | Descripción del restaurante |
| `logo` | Text | SI | URL del logo |
| `theme_color` | Text | NO | Color del tema (default: #f97316) |

El campo `slug` merece atención especial. Es un identificador amigable para URLs que permite acceder al menú público de un restaurante mediante una dirección como `/menu/el-buen-sabor`. Este slug debe ser único en todo el sistema, no solo dentro de un tenant, porque las URLs de menú público son globales.

El `theme_color` permite que cada restaurante personalice la apariencia de su menú digital, manteniendo coherencia con su identidad de marca.

**Campos de Auditoría:** Todas las tablas del sistema heredan campos de auditoría de `AuditMixin`:
- `is_active`: Flag de soft delete (FALSE = eliminado lógicamente)
- `created_at`, `updated_at`, `deleted_at`: Timestamps de ciclo de vida
- `created_by_id/email`, `updated_by_id/email`, `deleted_by_id/email`: Trazabilidad de quién hizo qué

```sql
CREATE TABLE tenant (
    id BIGSERIAL PRIMARY KEY,
    name TEXT NOT NULL,
    slug TEXT NOT NULL UNIQUE,
    description TEXT,
    logo TEXT,
    theme_color TEXT NOT NULL DEFAULT '#f97316',
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ,
    deleted_at TIMESTAMPTZ,
    created_by_id BIGINT,
    created_by_email VARCHAR(255),
    updated_by_id BIGINT,
    updated_by_email VARCHAR(255),
    deleted_by_id BIGINT,
    deleted_by_email VARCHAR(255)
);
```

---

### 2. Branch (Sucursal): La Presencia Física

Una sucursal representa una ubicación física donde el restaurante opera. Un restaurante puede tener una única sucursal (un pequeño café de barrio) o decenas de sucursales distribuidas geográficamente (una cadena de comida rápida).

**¿Por qué las sucursales son entidades separadas?** Porque cada ubicación física tiene características propias: dirección, horarios de operación, zona horaria, y potencialmente precios y disponibilidad de productos diferentes. La sucursal del aeropuerto puede tener horarios extendidos y precios premium, mientras que la sucursal del centro comercial puede cerrar más temprano y ofrecer promociones de almuerzo.

| Campo | Tipo | Nullable | Descripción |
|-------|------|----------|-------------|
| `id` | BigInteger | NO | PK |
| `tenant_id` | BigInteger | NO | FK → tenant.id |
| `name` | Text | NO | Nombre de la sucursal |
| `slug` | Text | NO | URL identifier |
| `address` | Text | SI | Dirección física |
| `phone` | Text | SI | Teléfono de contacto |
| `timezone` | Text | NO | Zona horaria (default: America/Argentina/Mendoza) |
| `opening_time` | Text | SI | Hora de apertura ("09:00") |
| `closing_time` | Text | SI | Hora de cierre ("23:00") |

El campo `timezone` es crucial para restaurantes que operan en múltiples zonas horarias. Si una cadena tiene sucursales en Buenos Aires y Mendoza, cada una debe mostrar los horarios correctos según su zona local. El sistema usa este campo para calcular si una sucursal está abierta o cerrada en tiempo real.

Los campos `opening_time` y `closing_time` se almacenan como strings en formato "HH:MM" por simplicidad. Una implementación más robusta podría usar tipos de tiempo nativos de PostgreSQL, pero el formato string es suficiente para el caso de uso actual y más fácil de manejar en el frontend.

```sql
CREATE TABLE branch (
    id BIGSERIAL PRIMARY KEY,
    tenant_id BIGINT NOT NULL REFERENCES tenant(id),
    name TEXT NOT NULL,
    slug TEXT NOT NULL,
    address TEXT,
    phone TEXT,
    timezone TEXT NOT NULL DEFAULT 'America/Argentina/Mendoza',
    opening_time TEXT,
    closing_time TEXT,
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    -- ... audit fields
);

CREATE INDEX idx_branch_tenant ON branch(tenant_id);
```

---

### 3. Category (Categoría): La Organización del Menú

Las categorías organizan los productos del menú en grupos lógicos que facilitan la navegación del comensal. "Entradas", "Platos Principales", "Postres", "Bebidas" son ejemplos típicos de categorías.

**Decisión de diseño crítica:** En el modelo actual, las categorías pertenecen a una sucursal específica (`branch_id`), no al tenant global. Esta decisión tiene consecuencias importantes que vale la pena analizar en profundidad.

**¿Por qué categorías por sucursal?** La justificación original fue permitir que diferentes sucursales tengan diferentes estructuras de menú. Una sucursal con bar podría tener una categoría "Cócteles" que no existe en una sucursal sin bar. Una sucursal de aeropuerto podría reorganizar su menú en "Comida Rápida" y "Para Llevar" en lugar de las categorías tradicionales.

**El problema que esto genera:** Si un restaurante quiere la misma estructura de categorías en todas sus sucursales (el caso más común), debe crear las mismas categorías múltiples veces, una por cada sucursal. Esto genera duplicación de datos y riesgo de inconsistencias. Si renombro "Platos Principales" a "Platos de Fondo" en una sucursal, debo recordar hacerlo en todas las demás manualmente.

| Campo | Tipo | Nullable | Descripción |
|-------|------|----------|-------------|
| `id` | BigInteger | NO | PK |
| `tenant_id` | BigInteger | NO | FK → tenant.id |
| `branch_id` | BigInteger | NO | FK → branch.id |
| `name` | Text | NO | Nombre de la categoría |
| `icon` | Text | SI | Icono representativo (emoji o nombre de icono) |
| `image` | Text | SI | URL de imagen de la categoría |
| `order` | Integer | NO | Orden de visualización (default: 0) |

El campo `order` permite controlar en qué secuencia aparecen las categorías en el menú. Típicamente queremos que "Entradas" aparezca antes que "Postres", siguiendo el orden natural de una comida.

```sql
CREATE TABLE category (
    id BIGSERIAL PRIMARY KEY,
    tenant_id BIGINT NOT NULL REFERENCES tenant(id),
    branch_id BIGINT NOT NULL REFERENCES branch(id),
    name TEXT NOT NULL,
    icon TEXT,
    image TEXT,
    "order" INTEGER NOT NULL DEFAULT 0,
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    -- ... audit fields
);

CREATE INDEX idx_category_tenant ON category(tenant_id);
CREATE INDEX idx_category_branch ON category(branch_id);
```

---

### 4. Subcategory (Subcategoría): Refinando la Organización

Las subcategorías permiten un nivel adicional de organización dentro de las categorías. Dentro de "Pizzas" podemos tener "Pizzas Clásicas", "Pizzas Especiales", "Pizzas Veganas". Esto ayuda a los comensales a encontrar lo que buscan más rápidamente en menús extensos.

**¿Es obligatoria la subcategoría?** No. Un producto puede pertenecer directamente a una categoría sin subcategoría. Esto es útil para categorías simples como "Bebidas" donde no tiene sentido subdividir, o para restaurantes pequeños con menús compactos.

| Campo | Tipo | Nullable | Descripción |
|-------|------|----------|-------------|
| `id` | BigInteger | NO | PK |
| `tenant_id` | BigInteger | NO | FK → tenant.id |
| `category_id` | BigInteger | NO | FK → category.id |
| `name` | Text | NO | Nombre de la subcategoría |
| `image` | Text | SI | URL de imagen |
| `order` | Integer | NO | Orden de visualización (default: 0) |

Nótese que la subcategoría hereda implícitamente el `branch_id` a través de su categoría padre. No tiene un `branch_id` propio, lo que mantiene la consistencia del modelo jerárquico.

```sql
CREATE TABLE subcategory (
    id BIGSERIAL PRIMARY KEY,
    tenant_id BIGINT NOT NULL REFERENCES tenant(id),
    category_id BIGINT NOT NULL REFERENCES category(id),
    name TEXT NOT NULL,
    image TEXT,
    "order" INTEGER NOT NULL DEFAULT 0,
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    -- ... audit fields
);

CREATE INDEX idx_subcategory_tenant ON subcategory(tenant_id);
CREATE INDEX idx_subcategory_category ON subcategory(category_id);
```

---

### 5. Product (Producto): El Corazón del Catálogo

La tabla `product` define los productos que el restaurante vende. Es, junto con `branch_product`, el núcleo del modelo comercial del sistema.

**Filosofía del producto global:** A diferencia de las categorías, los productos existen a nivel tenant (global al restaurante). Esto significa que la "Milanesa Napolitana" se define una sola vez, y luego cada sucursal decide si la vende y a qué precio. Este diseño facilita la gestión del catálogo: si actualizo la descripción o imagen de un producto, el cambio se refleja automáticamente en todas las sucursales.

| Campo | Tipo | Nullable | Descripción |
|-------|------|----------|-------------|
| `id` | BigInteger | NO | PK |
| `tenant_id` | BigInteger | NO | FK → tenant.id |
| `name` | Text | NO | Nombre del producto |
| `description` | Text | SI | Descripción del producto |
| `image` | Text | SI | URL de imagen |
| `category_id` | BigInteger | NO | FK → category.id |
| `subcategory_id` | BigInteger | SI | FK → subcategory.id (opcional) |
| `featured` | Boolean | NO | Destacado en el menú (default: false) |
| `popular` | Boolean | NO | Marcado como popular (default: false) |
| `badge` | Text | SI | Etiqueta visual ("Nuevo", "Popular", etc.) |
| `seal` | Text | SI | Sello dietético ("Vegano", "Sin Gluten", etc.) |
| `allergen_ids` | Text | SI | JSON array de IDs de alérgenos |

**Los campos problemáticos para consultas nutricionales:**

El campo `seal` almacena un único string con un sello dietético. Esto presenta varios problemas:
- Solo permite UN sello por producto. ¿Qué pasa si un plato es "Vegano" Y "Sin Gluten"?
- Es un campo de texto libre, lo que permite inconsistencias ("Vegano", "vegano", "VEGANO", "Apto Vegano").
- No distingue niveles de certificación o confianza.

El campo `allergen_ids` es quizás el más problemático desde el punto de vista de normalización de datos. Almacena los alérgenos como un string JSON:

```json
"[1, 3, 5]"
```

Esto significa que el producto contiene los alérgenos con IDs 1, 3 y 5. Los problemas de este enfoque son múltiples:

1. **Viola la Primera Forma Normal (1NF)**: Un campo debe contener valores atómicos. Un array JSON dentro de un campo de texto no es atómico.

2. **No hay integridad referencial**: Nada impide que el JSON contenga un ID que no existe en la tabla `allergen`. Si elimino un alérgeno, los productos que lo referencian quedan con datos huérfanos.

3. **Consultas ineficientes**: Para buscar "todos los productos que contienen gluten (ID=1)", necesito hacer búsquedas de texto en el JSON, lo cual es lento y propenso a errores:
   ```sql
   WHERE allergen_ids LIKE '%"1"%' OR allergen_ids LIKE '%[1,%' ...
   ```

4. **No distingue niveles de presencia**: El modelo actual solo dice "contiene". No puede expresar "puede contener trazas de" ni "garantizado libre de".

5. **Joins imposibles**: No puedo hacer un JOIN directo entre productos y alérgenos para obtener los nombres de los alérgenos de un producto.

```sql
CREATE TABLE product (
    id BIGSERIAL PRIMARY KEY,
    tenant_id BIGINT NOT NULL REFERENCES tenant(id),
    name TEXT NOT NULL,
    description TEXT,
    image TEXT,
    category_id BIGINT NOT NULL REFERENCES category(id),
    subcategory_id BIGINT REFERENCES subcategory(id),
    featured BOOLEAN NOT NULL DEFAULT FALSE,
    popular BOOLEAN NOT NULL DEFAULT FALSE,
    badge TEXT,
    seal TEXT,
    allergen_ids TEXT,  -- JSON array: "[1, 2, 3]"
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    -- ... audit fields
);

CREATE INDEX idx_product_tenant ON product(tenant_id);
CREATE INDEX idx_product_category ON product(category_id);
CREATE INDEX idx_product_subcategory ON product(subcategory_id);
```

---

### 6. BranchProduct (Producto por Sucursal): El Puente Comercial

Esta tabla pivote es donde se materializa la relación entre productos globales y sucursales específicas. Define qué productos están disponibles en cada sucursal y a qué precio.

**¿Por qué una tabla separada?** Podríamos haber puesto el precio directamente en la tabla `product`, pero eso impediría tener precios diferentes por sucursal. La arquitectura de tabla pivote proporciona máxima flexibilidad: cada combinación producto-sucursal puede tener su propio precio y estado de disponibilidad.

| Campo | Tipo | Nullable | Descripción |
|-------|------|----------|-------------|
| `id` | BigInteger | NO | PK |
| `tenant_id` | BigInteger | NO | FK → tenant.id |
| `branch_id` | BigInteger | NO | FK → branch.id |
| `product_id` | BigInteger | NO | FK → product.id |
| `price_cents` | Integer | NO | Precio en centavos |
| `is_available` | Boolean | NO | Disponible para venta (default: true) |

**El precio en centavos:** Siguiendo las mejores prácticas para manejo de dinero en software, los precios se almacenan como enteros en centavos, no como decimales. $15.50 se almacena como 1550. Esto evita problemas de precisión de punto flotante que pueden causar errores de redondeo en cálculos financieros.

**La semántica de la existencia del registro:** Si no existe un registro `BranchProduct` para una combinación producto-sucursal, significa que ese producto NO está disponible en esa sucursal. Esto es diferente de tener un registro con `is_available = FALSE`, que indica que el producto existe en la sucursal pero está temporalmente no disponible (quizás se agotó el stock).

```sql
CREATE TABLE branch_product (
    id BIGSERIAL PRIMARY KEY,
    tenant_id BIGINT NOT NULL REFERENCES tenant(id),
    branch_id BIGINT NOT NULL REFERENCES branch(id),
    product_id BIGINT NOT NULL REFERENCES product(id),
    price_cents INTEGER NOT NULL,
    is_available BOOLEAN NOT NULL DEFAULT TRUE,
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    -- ... audit fields
);

CREATE INDEX idx_branch_product_tenant ON branch_product(tenant_id);
CREATE INDEX idx_branch_product_branch ON branch_product(branch_id);
CREATE INDEX idx_branch_product_product ON branch_product(product_id);
```

---

### 7. Allergen (Alérgeno): El Catálogo Incompleto

La tabla `allergen` almacena el catálogo de alérgenos que el restaurante reconoce. En teoría, esto debería permitir una gestión adecuada de información de alérgenos. En la práctica, su utilidad está severamente limitada por cómo se relaciona con los productos.

**Alérgenos por tenant, no globales:** Cada restaurante define sus propios alérgenos. Esto tiene sentido desde la perspectiva de flexibilidad (diferentes restaurantes pueden tener diferentes necesidades), pero también significa que no hay un catálogo estándar garantizado. Un restaurante podría no incluir "sulfitos" en su catálogo simplemente por desconocimiento.

| Campo | Tipo | Nullable | Descripción |
|-------|------|----------|-------------|
| `id` | BigInteger | NO | PK |
| `tenant_id` | BigInteger | NO | FK → tenant.id |
| `name` | Text | NO | Nombre del alérgeno |
| `icon` | Text | SI | Icono representativo |
| `description` | Text | SI | Descripción del alérgeno |

**Lo que falta en este modelo:**
- No hay distinción entre los 14 alérgenos de declaración obligatoria y otros alérgenos opcionales.
- No hay información sobre reacciones cruzadas (por ejemplo, personas alérgicas al látex pueden reaccionar al aguacate).
- No hay severidad o nivel de riesgo asociado al alérgeno.

```sql
CREATE TABLE allergen (
    id BIGSERIAL PRIMARY KEY,
    tenant_id BIGINT NOT NULL REFERENCES tenant(id),
    name TEXT NOT NULL,
    icon TEXT,
    description TEXT,
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    -- ... audit fields
);

CREATE INDEX idx_allergen_tenant ON allergen(tenant_id);
```

---

### 8. BranchCategoryExclusion: Control de Menú por Sucursal

Esta tabla permite excluir categorías completas de una sucursal. Es un mecanismo de control negativo: en lugar de decir "esta sucursal tiene estas categorías", decimos "esta sucursal NO tiene estas categorías".

**Caso de uso típico:** Un restaurante tiene tres sucursales. Dos tienen parrilla y una no. En lugar de crear estructuras de categorías diferentes para cada sucursal, creamos las categorías una vez y luego excluimos "Carnes a la Parrilla" de la sucursal sin parrilla.

| Campo | Tipo | Nullable | Descripción |
|-------|------|----------|-------------|
| `id` | BigInteger | NO | PK |
| `tenant_id` | BigInteger | NO | FK → tenant.id |
| `branch_id` | BigInteger | NO | FK → branch.id |
| `category_id` | BigInteger | NO | FK → category.id |

**Semántica:** La existencia de un registro `(branch_id=1, category_id=5)` significa que la categoría 5 está EXCLUIDA de la sucursal 1. Todos los productos de esa categoría quedan automáticamente no disponibles en esa sucursal, sin necesidad de modificar sus registros `BranchProduct`.

```sql
CREATE TABLE branch_category_exclusion (
    id BIGSERIAL PRIMARY KEY,
    tenant_id BIGINT NOT NULL REFERENCES tenant(id),
    branch_id BIGINT NOT NULL REFERENCES branch(id),
    category_id BIGINT NOT NULL REFERENCES category(id),
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    -- ... audit fields
);

CREATE INDEX idx_branch_cat_excl_branch ON branch_category_exclusion(branch_id);
CREATE INDEX idx_branch_cat_excl_category ON branch_category_exclusion(category_id);
```

---

### 9. BranchSubcategoryExclusion: Control Granular

Similar a la exclusión de categorías, pero a nivel de subcategoría. Permite un control más fino cuando no queremos excluir toda una categoría, solo parte de ella.

**Caso de uso:** La categoría "Pizzas" tiene subcategorías "Clásicas", "Especiales" y "Veganas". Una sucursal pequeña decide no ofrecer pizzas veganas por falta de ingredientes especiales. En lugar de excluir toda la categoría "Pizzas", excluimos solo la subcategoría "Veganas".

| Campo | Tipo | Nullable | Descripción |
|-------|------|----------|-------------|
| `id` | BigInteger | NO | PK |
| `tenant_id` | BigInteger | NO | FK → tenant.id |
| `branch_id` | BigInteger | NO | FK → branch.id |
| `subcategory_id` | BigInteger | NO | FK → subcategory.id |

```sql
CREATE TABLE branch_subcategory_exclusion (
    id BIGSERIAL PRIMARY KEY,
    tenant_id BIGINT NOT NULL REFERENCES tenant(id),
    branch_id BIGINT NOT NULL REFERENCES branch(id),
    subcategory_id BIGINT NOT NULL REFERENCES subcategory(id),
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    -- ... audit fields
);

CREATE INDEX idx_branch_subcat_excl_branch ON branch_subcategory_exclusion(branch_id);
CREATE INDEX idx_branch_subcat_excl_subcategory ON branch_subcategory_exclusion(subcategory_id);
```

---

## Consultas Comunes y Sus Limitaciones

### Obtener el Menú Completo de una Sucursal

Esta es la consulta más importante del sistema desde el punto de vista del comensal. Cuando alguien abre el menú digital, necesitamos obtener todos los productos disponibles organizados por categoría y subcategoría.

```sql
SELECT
    c.id AS category_id,
    c.name AS category_name,
    c."order" AS category_order,
    sc.id AS subcategory_id,
    sc.name AS subcategory_name,
    sc."order" AS subcategory_order,
    p.id AS product_id,
    p.name AS product_name,
    p.description,
    p.image,
    p.badge,
    p.seal,
    p.allergen_ids,
    bp.price_cents,
    bp.is_available
FROM product p
JOIN branch_product bp ON bp.product_id = p.id
JOIN category c ON c.id = p.category_id
LEFT JOIN subcategory sc ON sc.id = p.subcategory_id
WHERE bp.branch_id = :branch_id
  AND bp.is_available = TRUE
  AND p.is_active = TRUE
  AND c.is_active = TRUE
  AND (sc.is_active = TRUE OR sc.id IS NULL)
  -- Excluir categorías excluidas
  AND NOT EXISTS (
      SELECT 1 FROM branch_category_exclusion bce
      WHERE bce.branch_id = :branch_id AND bce.category_id = c.id AND bce.is_active = TRUE
  )
  -- Excluir subcategorías excluidas
  AND NOT EXISTS (
      SELECT 1 FROM branch_subcategory_exclusion bse
      WHERE bse.branch_id = :branch_id AND bse.subcategory_id = sc.id AND bse.is_active = TRUE
  )
ORDER BY c."order", sc."order", p.name;
```

Esta consulta funciona bien para su propósito: obtener el menú. Sin embargo, devuelve `allergen_ids` como un string JSON que el frontend debe parsear. No hay forma de filtrar productos por alérgeno eficientemente a nivel de base de datos.

### Intentar Buscar Productos por Alérgeno

Aquí es donde el modelo muestra sus limitaciones más graves. Supongamos que un comensal celíaco quiere ver solo productos sin gluten (asumiendo que gluten tiene ID=1).

**El problema:** No podemos hacer un JOIN porque `allergen_ids` es un string, no una relación.

**Intento de solución con búsqueda de texto:**

```sql
-- Buscar productos que NO contengan gluten (ID=1)
-- ADVERTENCIA: Esta consulta es frágil y puede dar falsos positivos/negativos
SELECT p.id, p.name
FROM product p
WHERE p.allergen_ids IS NULL
   OR (
       p.allergen_ids NOT LIKE '%[1]%'
       AND p.allergen_ids NOT LIKE '%[1,%'
       AND p.allergen_ids NOT LIKE '%,1,%'
       AND p.allergen_ids NOT LIKE '%,1]%'
   );
```

Esta consulta es problemática por varias razones:
- Es lenta porque no puede usar índices.
- Es frágil porque depende del formato exacto del JSON.
- Puede dar falsos positivos si hay un alérgeno con ID 10, 11, 21, etc. (contienen "1").
- No distingue entre "no contiene" y "puede contener trazas de".

**Si el campo fuera JSONB (mejora parcial):**

```sql
-- Asumiendo que allergen_ids fuera tipo JSONB
SELECT p.id, p.name
FROM product p
WHERE NOT (p.allergen_ids::jsonb @> '[1]'::jsonb);
```

Esto sería más eficiente y menos frágil, pero sigue sin resolver el problema de la falta de normalización y la ausencia de niveles de presencia de alérgenos.

### La Consulta Imposible: "¿La Mayonesa Tiene Huevo?"

Un comensal mira la hamburguesa y pregunta: "¿La mayonesa tiene huevo? Soy alérgico."

**El modelo actual no puede responder esta pregunta.**

No existe ninguna tabla que modele los ingredientes de un producto, ni mucho menos los sub-ingredientes de ingredientes compuestos. La hamburguesa es una "caja negra". Sabemos su nombre, descripción y precio, pero no sabemos qué contiene a nivel de componentes.

Para responder esta pregunta necesitaríamos:
1. Una tabla `ingrediente` que liste la mayonesa como ingrediente de la hamburguesa.
2. Una tabla `sub_ingrediente` que liste huevo como componente de la mayonesa.
3. Una relación entre sub-ingredientes y alérgenos.

Nada de esto existe en el modelo actual.

---

## Análisis de Normalización

### Evaluación por Forma Normal

| Forma Normal | Cumplimiento | Explicación Detallada |
|--------------|--------------|----------------------|
| **1NF** | ⚠️ PARCIAL | El campo `allergen_ids` almacena un array JSON, violando la atomicidad requerida por 1NF. Cada celda debe contener un único valor indivisible. |
| **2NF** | ✅ CUMPLE | No hay dependencias parciales. Todos los atributos no-clave dependen completamente de la clave primaria. |
| **3NF** | ✅ CUMPLE | No hay dependencias transitivas evidentes entre atributos no-clave. |
| **BCNF** | ✅ CUMPLE | Cada determinante en el modelo es una clave candidata. |

### El Problema Central: allergen_ids

El campo `allergen_ids` en la tabla `Product` es la violación de normalización más significativa del modelo. Analicemos por qué esto es problemático desde múltiples perspectivas:

**Perspectiva de integridad de datos:**
```json
// Contenido actual de allergen_ids
"[1, 3, 999]"
```

El valor 999 podría ser un alérgeno que fue eliminado, o un error de entrada de datos. La base de datos no tiene forma de validar que estos IDs referencian alérgenos existentes. No hay integridad referencial.

**Perspectiva de consultas:**
Para obtener el nombre de los alérgenos de un producto, el código de aplicación debe:
1. Obtener el producto con su `allergen_ids`.
2. Parsear el JSON para extraer los IDs.
3. Hacer una segunda consulta para obtener los nombres de esos alérgenos.
4. Combinar los resultados en memoria.

Con una tabla de relación normalizada, sería un simple JOIN:
```sql
SELECT p.name, a.name AS allergen_name
FROM product p
JOIN product_allergen pa ON pa.product_id = p.id
JOIN allergen a ON a.id = pa.allergen_id
WHERE p.id = :product_id;
```

**Perspectiva de mantenimiento:**
Si necesito cambiar el ID de un alérgeno (por ejemplo, al migrar datos), debo actualizar no solo la tabla `allergen` sino también el JSON dentro de todos los productos que lo referencian. Esto es propenso a errores y requiere lógica de aplicación compleja.

### La Solución Normalizada (No Implementada)

El modelo debería tener una tabla de relación muchos-a-muchos:

```sql
CREATE TABLE product_allergen (
    id BIGSERIAL PRIMARY KEY,
    product_id BIGINT NOT NULL REFERENCES product(id) ON DELETE CASCADE,
    allergen_id BIGINT NOT NULL REFERENCES allergen(id) ON DELETE RESTRICT,
    presence_type VARCHAR(20) NOT NULL DEFAULT 'contains',  -- 'contains', 'may_contain_traces', 'free_from'
    UNIQUE(product_id, allergen_id, presence_type)
);

CREATE INDEX idx_product_allergen_product ON product_allergen(product_id);
CREATE INDEX idx_product_allergen_allergen ON product_allergen(allergen_id);
```

Con este diseño podríamos expresar:
- "La pizza CONTIENE gluten"
- "La pizza PUEDE CONTENER TRAZAS DE frutos secos"
- "El helado está LIBRE DE gluten"

El modelo actual solo puede expresar el primer caso, y de manera deficiente.

---

## Comparación con el Modelo Canónico (planteo.md)

El modelo canónico propuesto en `planteo.md` fue diseñado específicamente para responder consultas nutricionales complejas. La siguiente tabla compara ambos enfoques:

| Aspecto | Modelo Actual (Integrador) | Modelo Canónico (planteo.md) |
|---------|---------------------------|------------------------------|
| **Alérgenos** | JSON string en campo de producto | 3 tablas M:N normalizadas (contiene, trazas, libre_de) |
| **Niveles de alérgeno** | Solo "contiene" implícito | Tres niveles: contiene, puede contener trazas, libre de |
| **Certificación celíaca** | No distingue | Campo `apto_celiaco` separado de `sin_gluten` |
| **Perfil dietético** | Campo `seal` (string único) | 4 campos booleanos: vegetariano, vegano, sin_gluten, sin_lacteos |
| **Ingredientes** | NO EXISTE | Tabla normalizada con catálogo maestro |
| **Sub-ingredientes** | NO EXISTE | Tabla para componentes de ingredientes procesados |
| **Grupos de ingredientes** | NO EXISTE | Clasificación: proteína, vegetal, lácteo, cereal, otro |
| **Métodos de cocción** | NO EXISTE | Tabla con 8 métodos + flag `usa_aceite` |
| **Perfil sensorial** | NO EXISTE | Tablas de sabor (8 tipos) y textura (7 tipos) |
| **Modificaciones** | NO EXISTE | Tabla de modificaciones permitidas/prohibidas |
| **Advertencias** | NO EXISTE | Tabla de advertencias por plato |
| **Config RAG** | NO EXISTE | Campo `nivel_riesgo_base` para comportamiento del chatbot |
| **Descripción** | Campo único | Dos campos: descripción corta y descripción de menú |

### Implicaciones Prácticas de las Diferencias

**Escenario 1: "¿Qué postres puedo comer si soy celíaco?"**

- **Modelo Actual:** Puede buscar `seal = 'Sin Gluten'`, pero esto no garantiza que sea apto para celíacos. No hay forma de distinguir.
- **Modelo Canónico:** Consulta directa `WHERE apto_celiaco = TRUE`.

**Escenario 2: "¿La ensalada César tiene huevo?"**

- **Modelo Actual:** Imposible responder. No hay modelo de ingredientes.
- **Modelo Canónico:** Busca en ingredientes → encuentra "aderezo César" → busca en sub-ingredientes → encuentra "huevo, aceite, anchoas, limón".

**Escenario 3: "Quiero algo crocante y salado"**

- **Modelo Actual:** Imposible. No hay perfil sensorial.
- **Modelo Canónico:** Consulta en `plato_sabor` y `plato_textura` para encontrar platos que combinen ambas características.

**Escenario 4: "¿Puedo pedir la hamburguesa sin cebolla?"**

- **Modelo Actual:** El sistema no sabe si es posible. Requiere preguntar al mozo.
- **Modelo Canónico:** Consulta en `plato_modificacion` para ver si "retirar cebolla" está permitido.

**Escenario 5: "Tengo alergia severa al maní. ¿Es seguro el pad thai?"**

- **Modelo Actual:** Si el pad thai tiene maní en su `allergen_ids`, podemos advertir. Pero no podemos decir si hay riesgo de trazas por contaminación cruzada.
- **Modelo Canónico:** Consultamos `plato_alergeno_contiene` (presencia directa) y `plato_alergeno_trazas` (riesgo de contaminación). El campo `nivel_riesgo_base = 'alto'` indica al chatbot que debe derivar al personal del restaurante.

---

## El Vacío Conceptual: Lo Que No Existe

Es importante enumerar explícitamente qué información nutricional NO puede almacenar el modelo actual:

### Información de Ingredientes
- Lista de ingredientes de cada producto
- Componentes de ingredientes procesados (¿qué tiene la mayonesa?)
- Origen de los ingredientes (¿de dónde viene la carne?)
- Cantidad o proporción de ingredientes

### Información de Preparación
- Método de cocción (¿es frito, al horno, a la parrilla?)
- Uso de aceite y tipo de aceite
- Temperatura de cocción
- Tiempo de preparación

### Información Nutricional Detallada
- Calorías por porción
- Macronutrientes (proteínas, carbohidratos, grasas)
- Micronutrientes (vitaminas, minerales)
- Información de porciones y tamaños

### Información Sensorial
- Perfil de sabor (dulce, salado, ácido, amargo, umami, picante)
- Perfil de textura (crocante, cremoso, tierno, firme)
- Intensidad del sabor
- Temperatura de servicio

### Información de Personalización
- Modificaciones permitidas (sin cebolla, sin salsa)
- Modificaciones prohibidas (no se puede hacer sin el pan)
- Sustituciones posibles (papas fritas por ensalada)
- Impacto nutricional de modificaciones

### Información de Seguridad
- Nivel de riesgo para personas con alergias
- Advertencias especiales (contiene huesos, muy picante, contiene alcohol)
- Indicaciones para grupos sensibles (embarazadas, niños, adultos mayores)

---

## Limitaciones para el Sistema RAG

El sistema Integrador incluye un chatbot basado en RAG (Retrieval-Augmented Generation) que permite a los comensales hacer preguntas en lenguaje natural sobre el menú. Las limitaciones del modelo de datos impactan directamente en la capacidad del chatbot para responder preguntas.

### Preguntas que el RAG NO Puede Responder Correctamente

1. **"¿Este plato contiene gluten?"**
   - El RAG puede intentar responder basándose en `allergen_ids`, pero la respuesta será poco confiable por las limitaciones del campo JSON.

2. **"¿Qué platos son seguros para mi hijo con alergia a los frutos secos?"**
   - El RAG no puede distinguir entre "no contiene frutos secos" y "puede contener trazas". Para alergias severas, esta distinción es vital.

3. **"¿Qué ingredientes tiene la salsa del plato?"**
   - Imposible. No hay modelo de ingredientes.

4. **"¿Puedo pedir este plato sin el queso?"**
   - El RAG no tiene información sobre modificaciones permitidas.

5. **"Quiero algo ligero y bajo en calorías"**
   - No hay información calórica en el modelo.

6. **"¿Qué platos son aptos para embarazadas?"**
   - No hay advertencias para grupos sensibles.

### El Riesgo de Respuestas Incorrectas

El mayor riesgo del modelo actual no es que el RAG no pueda responder, sino que responda incorrectamente. Si un comensal pregunta "¿La milanesa tiene gluten?" y el campo `allergen_ids` tiene un error o está desactualizado, el RAG podría dar una respuesta que ponga en riesgo la salud del comensal.

El modelo canónico aborda esto con el campo `nivel_riesgo_base`:
- Platos de riesgo bajo: El RAG responde con confianza.
- Platos de riesgo medio: El RAG incluye advertencias de verificar con el personal.
- Platos de riesgo alto: El RAG siempre deriva al personal del restaurante.

El modelo actual no tiene esta capacidad de calibrar la confianza de las respuestas.

---

## Inventario de Tablas

**Total de tablas relacionadas a productos:** 9

| Tabla | Tipo | Registros Típicos | Propósito |
|-------|------|-------------------|-----------|
| `tenant` | Principal | 1-10 | Restaurante/marca |
| `branch` | Principal | 1-50 | Sucursal física |
| `category` | Catálogo | 5-20 por branch | Agrupación de productos |
| `subcategory` | Catálogo | 0-30 por category | Sub-agrupación |
| `product` | Principal | 50-500 por tenant | Definición de producto |
| `branch_product` | Pivote | products × branches | Precio/disponibilidad |
| `allergen` | Catálogo | 10-20 por tenant | Definición de alérgenos |
| `branch_category_exclusion` | Exclusión | 0-20 | Categorías excluidas |
| `branch_subcategory_exclusion` | Exclusión | 0-50 | Subcategorías excluidas |

---

## Recomendaciones de Evolución

### Fase 1: Mejoras Sin Cambio de Esquema (Corto Plazo)

Estas mejoras pueden implementarse sin modificar la estructura de las tablas existentes:

1. **Migrar `allergen_ids` de Text a JSONB**
   - Permite consultas más eficientes con operadores JSON de PostgreSQL.
   - No rompe compatibilidad con código existente que espera un string.
   - Habilita índices GIN para búsquedas en el JSON.

2. **Crear vistas materializadas para el menú**
   - Pre-calcular el menú completo de cada sucursal.
   - Refrescar periódicamente o con triggers.
   - Mejora dramática en tiempo de respuesta.

3. **Documentar valores estándar para `seal`**
   - Crear constantes en el código: "Vegano", "Vegetariano", "Sin Gluten", etc.
   - Validar en la aplicación que solo se usen valores estándar.
   - Migrar datos existentes a valores normalizados.

### Fase 2: Normalización de Alérgenos (Mediano Plazo)

1. **Crear tabla `product_allergen`**
   ```sql
   CREATE TABLE product_allergen (
       product_id BIGINT NOT NULL REFERENCES product(id),
       allergen_id BIGINT NOT NULL REFERENCES allergen(id),
       presence_type VARCHAR(20) NOT NULL, -- 'contains', 'may_contain', 'free_from'
       PRIMARY KEY (product_id, allergen_id, presence_type)
   );
   ```

2. **Migrar datos de `allergen_ids` a la nueva tabla**
   - Script de migración que parsea el JSON y crea registros.
   - Asumir `presence_type = 'contains'` para datos existentes.

3. **Deprecar el campo `allergen_ids`**
   - Mantener el campo por compatibilidad pero dejar de usarlo.
   - Eliminar en una versión futura.

4. **Expandir `seal` a campos booleanos**
   ```sql
   ALTER TABLE product
   ADD COLUMN is_vegetarian BOOLEAN DEFAULT FALSE,
   ADD COLUMN is_vegan BOOLEAN DEFAULT FALSE,
   ADD COLUMN is_gluten_free BOOLEAN DEFAULT FALSE,
   ADD COLUMN is_celiac_safe BOOLEAN DEFAULT FALSE;
   ```

### Fase 3: Integración con Modelo Canónico (Largo Plazo)

1. **Crear relación `Product.canonical_dish_id`**
   ```sql
   ALTER TABLE product
   ADD COLUMN canonical_dish_id UUID REFERENCES plato(id);
   ```

2. **Productos con plato canónico heredan información nutricional**
   - Si `canonical_dish_id` no es NULL, la información detallada viene del plato.
   - Si es NULL, se usan los campos básicos del producto (compatibilidad hacia atrás).

3. **Crear vistas que combinen ambos modelos**
   ```sql
   CREATE VIEW v_product_complete AS
   SELECT
       p.*,
       CASE WHEN p.canonical_dish_id IS NOT NULL
            THEN (SELECT perfil_alimentario FROM v_plato_completo WHERE id = p.canonical_dish_id)
            ELSE jsonb_build_object('vegetariano', p.is_vegetarian, ...)
       END AS perfil_alimentario,
       ...
   FROM product p;
   ```

4. **Interfaz de Dashboard para vincular productos a platos canónicos**
   - Nueva pantalla en Cocina → "Vincular Productos a Fichas Técnicas".
   - Permite asociar productos existentes con platos del modelo canónico.
   - Los productos vinculados heredan automáticamente toda la información nutricional.

---

## Conclusión

El modelo de datos actual del sistema Integrador resuelve eficientemente los problemas de gestión comercial de un restaurante multi-sucursal: catálogo de productos, precios diferenciados, disponibilidad por ubicación y exclusiones de menú. Sin embargo, fue diseñado como un sistema de gestión operativa, no como un sistema de información nutricional.

Las limitaciones más significativas son:

1. **Alérgenos como JSON string**: Viola normalización, impide consultas eficientes, no distingue niveles de presencia.

2. **Ausencia de modelo de ingredientes**: Imposibilita responder preguntas sobre componentes de platos.

3. **Perfil dietético simplificado**: Un solo campo de texto no puede expresar la complejidad de restricciones alimentarias reales.

4. **Sin información sensorial ni de preparación**: El sistema no conoce cómo se cocina ni cómo sabe cada plato.

5. **Sin modelo de modificaciones**: No se puede informar al comensal qué cambios son posibles.

El modelo canónico propuesto en `planteo.md` aborda todas estas limitaciones con un diseño de 19 tablas normalizadas. La estrategia de integración recomendada es gradual: primero normalizar alérgenos, luego expandir perfiles dietéticos, y finalmente vincular productos con platos canónicos para aquellos que requieran información nutricional detallada.

El objetivo final es un sistema donde cada producto pueda responder tanto a preguntas comerciales ("¿cuánto cuesta en esta sucursal?") como a preguntas nutricionales ("¿es seguro para un celíaco con alergia a frutos secos que busca algo crocante y no frito?").

---

*Documento generado para el proyecto Integrador - Sistema de Gestión de Restaurantes*
*Última actualización: Enero 2026*
