# Ficha Técnica: Modelo de Datos Canónico para Gestión de Platos

## Introducción y Propósito

Este documento constituye la ficha técnica completa del modelo de base de datos diseñado para gestionar la información nutricional, alérgenos y características sensoriales de los platos del restaurante. El modelo surge de la necesidad de estructurar datos complejos que originalmente se representaban en formato JSON (ver `canonico.txt`) hacia un esquema relacional normalizado en PostgreSQL.

### Objetivo Principal

El modelo tiene un doble propósito fundamental dentro del ecosistema Integrador:

1. **Alimentar la aplicación pwaMenu**: Los clientes que acceden al menú digital necesitan información precisa sobre cada plato. Cuando un comensal tiene restricciones alimentarias (celiaquía, veganismo, alergias), el sistema debe poder filtrar y mostrar únicamente los platos seguros para esa persona. Este modelo permite consultas eficientes como "mostrar todos los platos veganos sin frutos secos" o "listar entradas aptas para celíacos".

2. **Servir como fuente de ingesta para el sistema RAG**: El chatbot de inteligencia artificial del restaurante necesita conocer en profundidad cada plato para responder preguntas de los comensales. Cuando alguien pregunta "¿la milanesa tiene gluten?" o "¿qué postres puedo comer si soy alérgico a los frutos secos?", el RAG debe tener acceso estructurado a esta información. El campo `nivel_riesgo_base` permite al sistema priorizar la precisión en respuestas sobre platos potencialmente peligrosos para personas con alergias severas.

### Flujo de Datos en el Sistema

El ciclo de vida de los datos sigue este recorrido:

```
Dashboard (KITCHEN/MANAGER) → Base de Datos PostgreSQL → pwaMenu (visualización)
                                       ↓
                              Endpoint de Ingesta RAG
                                       ↓
                              knowledge_document (pgvector)
                                       ↓
                              Chatbot AI (respuestas a comensales)
```

El personal de cocina o gerencia carga la información de cada plato desde el Dashboard. Esta información se almacena en las 19 tablas normalizadas. Cuando el plato se marca como listo para publicar, pwaMenu puede mostrarlo a los clientes con todos sus filtros de alérgenos y preferencias dietéticas. Paralelamente, el endpoint `/api/admin/recipes/{id}/ingest` puede convertir esta información estructurada en texto enriquecido para el sistema RAG, permitiendo que el chatbot responda consultas en lenguaje natural.

---

## Arquitectura del Modelo

### Filosofía de Diseño

El modelo sigue los principios de normalización hasta la Forma Normal de Boyce-Codd (BCNF), lo que significa que no existe redundancia de datos y cada pieza de información se almacena en un único lugar. Esta decisión tiene implicaciones prácticas importantes:

- **Consistencia**: Si cambia el nombre de un alérgeno (por ejemplo, de "cacahuetes" a "maní"), solo se modifica en la tabla `alergeno` y todos los platos reflejan automáticamente el cambio.
- **Integridad**: Las restricciones de clave foránea garantizan que no puedan existir referencias huérfanas. Un plato no puede referenciar un alérgeno inexistente.
- **Eficiencia en consultas complejas**: Los índices estratégicamente ubicados permiten filtrados rápidos incluso con miles de platos.

### Diagrama de Entidades y Relaciones

El siguiente diagrama muestra cómo se conectan todas las entidades del modelo. La tabla `plato` actúa como núcleo central desde el cual irradian todas las demás tablas:

```
plato (1) ─────┬───── (N) plato_ingrediente ───── (N) ingrediente (1)
              │                                          │
              │                                          └── (N) sub_ingrediente
              │
              ├───── (1) plato_descripcion
              │
              ├───── (1) plato_alergenos
              │
              ├───── (N) plato_alergeno_contiene ───── alergeno
              ├───── (N) plato_alergeno_trazas ─────── alergeno
              ├───── (N) plato_alergeno_libre ──────── alergeno
              │
              ├───── (1) plato_perfil_alimentario
              │
              ├───── (1) plato_coccion
              ├───── (N) plato_metodo_coccion ───── metodo_coccion
              │
              ├───── (N) plato_sabor ───── sabor
              ├───── (N) plato_textura ───── textura
              │
              ├───── (N) plato_modificacion
              │
              ├───── (N) plato_advertencia
              │
              └───── (1) plato_rag
```

Las relaciones se leen de la siguiente manera:
- **(1) a (1)**: Relación uno a uno. Cada plato tiene exactamente una descripción, un perfil alimentario, una configuración de cocción y una configuración RAG.
- **(1) a (N)**: Relación uno a muchos. Un plato puede tener múltiples ingredientes, alérgenos, sabores, texturas, modificaciones y advertencias.
- **Tablas catálogo**: Las tablas `alergeno`, `ingrediente`, `metodo_coccion`, `sabor` y `textura` son catálogos maestros que se reutilizan entre todos los platos.

---

## Tablas del Modelo

### 1. Tabla Principal: `plato`

Esta es la tabla central del modelo. Cada registro representa un plato único del menú del restaurante. El diseño utiliza UUID como identificador primario para garantizar unicidad global y facilitar la sincronización entre sistemas distribuidos.

**Propósito en pwaMenu**: Esta tabla proporciona la información básica que se muestra en las tarjetas del menú: nombre del plato y su categoría (entrada, plato principal, postre, bebida). El filtro por categoría permite a los comensales navegar el menú de forma organizada.

**Propósito en RAG**: El nombre y categoría son los primeros datos que el chatbot utiliza para identificar sobre qué plato está preguntando el usuario. Cuando alguien dice "cuéntame sobre la ensalada César", el sistema busca primero por nombre en esta tabla.

```sql
CREATE TABLE plato (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    nombre VARCHAR(255) NOT NULL,
    categoria VARCHAR(50) NOT NULL CHECK (categoria IN ('entrada', 'plato_principal', 'postre', 'bebida')),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    is_active BOOLEAN DEFAULT TRUE
);

CREATE INDEX idx_plato_categoria ON plato(categoria);
CREATE INDEX idx_plato_nombre ON plato(nombre);
```

**Campos explicados**:
- `id`: Identificador único universal. Se genera automáticamente con `gen_random_uuid()`. Permite referencias externas sin colisiones.
- `nombre`: Nombre comercial del plato tal como aparece en el menú. Ejemplo: "Milanesa napolitana con papas fritas".
- `categoria`: Clasificación del plato dentro del menú. El constraint CHECK garantiza que solo se puedan usar los cuatro valores permitidos.
- `created_at` / `updated_at`: Timestamps de auditoría para saber cuándo se creó y modificó por última vez el registro.
- `is_active`: Soft delete. Cuando un plato se discontinúa, no se borra físicamente sino que se marca como inactivo. Esto preserva el historial y las referencias desde pedidos anteriores.

---

### 2. Descripciones: `plato_descripcion`

Cada plato necesita dos tipos de descripción con propósitos distintos. Esta separación permite optimizar el contenido para diferentes contextos de uso.

**Propósito en pwaMenu**: La descripción `corta` aparece en las tarjetas del menú durante la navegación (máximo 100-150 caracteres). La descripción `menu` aparece cuando el usuario toca un plato para ver más detalles, permitiendo texto más extenso con información sobre preparación, origen de ingredientes o historia del plato.

**Propósito en RAG**: Ambas descripciones se concatenan para crear el contexto textual que el chatbot utiliza al responder preguntas. La descripción de menú es especialmente valiosa porque suele contener información cualitativa que no está estructurada en otras tablas.

```sql
CREATE TABLE plato_descripcion (
    id SERIAL PRIMARY KEY,
    plato_id UUID NOT NULL UNIQUE REFERENCES plato(id) ON DELETE CASCADE,
    corta TEXT,
    menu TEXT
);
```

**Campos explicados**:
- `plato_id`: Referencia al plato padre. La restricción UNIQUE garantiza que cada plato tenga como máximo una fila de descripción (relación 1:1).
- `corta`: Texto breve para previsualizaciones. Ejemplo: "Clásica milanesa de ternera con salsa de tomate y mozzarella gratinada".
- `menu`: Texto extenso para la vista detallada. Ejemplo: "Nuestra milanesa napolitana está preparada con carne de ternera de primera calidad, empanizada artesanalmente y coronada con salsa de tomates San Marzano y mozzarella importada de Italia. Se sirve acompañada de papas fritas caseras cortadas a mano."

---

### 3. Sistema de Ingredientes

El sistema de ingredientes está diseñado para manejar la complejidad real de los alimentos. Un ingrediente puede ser simple (tomate, sal) o procesado (mayonesa, que contiene huevo, aceite, limón). Esta jerarquía permite responder preguntas como "¿este plato contiene huevo?" incluso cuando el huevo está oculto dentro de la mayonesa.

#### 3.1 Catálogo de Grupos: `grupo_ingrediente`

Los ingredientes se clasifican en grupos nutricionales. Esta clasificación es fundamental para personas que siguen dietas específicas y para el análisis nutricional.

**Propósito en pwaMenu**: Permite filtros avanzados como "platos altos en proteína" o "platos sin lácteos". También facilita la visualización agrupada de ingredientes en la ficha del plato.

**Propósito en RAG**: Cuando un usuario pregunta "¿qué platos tienen buena proteína?", el chatbot puede consultar todos los platos que contengan ingredientes del grupo "proteina".

```sql
CREATE TABLE grupo_ingrediente (
    id SERIAL PRIMARY KEY,
    nombre VARCHAR(50) NOT NULL UNIQUE CHECK (nombre IN ('proteina', 'vegetal', 'lacteo', 'cereal', 'otro'))
);
```

**Valores del catálogo**:
- `proteina`: Carnes, pescados, huevos, legumbres
- `vegetal`: Verduras, frutas, hortalizas
- `lacteo`: Leche, quesos, cremas, yogures
- `cereal`: Harinas, panes, pastas, arroz
- `otro`: Especias, aceites, condimentos, edulcorantes

#### 3.2 Catálogo Maestro: `ingrediente`

Esta tabla almacena todos los ingredientes conocidos por el sistema. Es un catálogo compartido: si dos platos usan "tomate", ambos referencian el mismo registro de ingrediente.

```sql
CREATE TABLE ingrediente (
    id SERIAL PRIMARY KEY,
    nombre VARCHAR(255) NOT NULL,
    grupo_id INTEGER REFERENCES grupo_ingrediente(id),
    es_procesado BOOLEAN DEFAULT FALSE,
    UNIQUE(nombre, grupo_id)
);

CREATE INDEX idx_ingrediente_nombre ON ingrediente(nombre);
CREATE INDEX idx_ingrediente_grupo ON ingrediente(grupo_id);
```

**Campos explicados**:
- `nombre`: Nombre del ingrediente. Ejemplo: "Pechuga de pollo", "Mayonesa casera", "Tomate cherry".
- `grupo_id`: Clasificación nutricional del ingrediente.
- `es_procesado`: Indica si el ingrediente es compuesto y tiene sub-ingredientes. Cuando es TRUE, se deben consultar los sub-ingredientes para conocer la composición completa.

#### 3.3 Sub-ingredientes: `sub_ingrediente`

Los ingredientes procesados (es_procesado = TRUE) tienen componentes que deben declararse para cumplir con normativas de alérgenos y para informar correctamente a los comensales.

**Propósito en pwaMenu**: Cuando un usuario toca un ingrediente marcado como procesado, puede expandir para ver sus componentes. Ejemplo: tocar "Mayonesa" muestra "huevo, aceite de girasol, jugo de limón, sal".

**Propósito en RAG**: Permite respuestas precisas como "La ensalada César contiene huevo porque la mayonesa del aderezo está hecha con huevo".

```sql
CREATE TABLE sub_ingrediente (
    id SERIAL PRIMARY KEY,
    ingrediente_id INTEGER NOT NULL REFERENCES ingrediente(id) ON DELETE CASCADE,
    nombre VARCHAR(255) NOT NULL
);

CREATE INDEX idx_sub_ingrediente_padre ON sub_ingrediente(ingrediente_id);
```

#### 3.4 Relación Plato-Ingrediente: `plato_ingrediente`

Esta tabla de unión implementa la relación muchos-a-muchos entre platos e ingredientes. Un plato tiene múltiples ingredientes, y un ingrediente puede aparecer en múltiples platos.

```sql
CREATE TABLE plato_ingrediente (
    id SERIAL PRIMARY KEY,
    plato_id UUID NOT NULL REFERENCES plato(id) ON DELETE CASCADE,
    ingrediente_id INTEGER NOT NULL REFERENCES ingrediente(id) ON DELETE RESTRICT,
    UNIQUE(plato_id, ingrediente_id)
);

CREATE INDEX idx_plato_ingrediente_plato ON plato_ingrediente(plato_id);
CREATE INDEX idx_plato_ingrediente_ingrediente ON plato_ingrediente(ingrediente_id);
```

**Nota sobre ON DELETE**: El plato usa CASCADE (si se borra el plato, se borran sus relaciones), pero el ingrediente usa RESTRICT (no se puede borrar un ingrediente que esté en uso por algún plato). Esto previene la pérdida accidental de información del catálogo.

---

### 4. Sistema de Alérgenos

El manejo de alérgenos es crítico para la seguridad alimentaria. El modelo distingue tres niveles de presencia de alérgenos, siguiendo las normativas europeas y argentinas de etiquetado alimentario.

**Importancia para la seguridad**: Una persona con alergia severa a los frutos secos puede sufrir anafilaxia con cantidades mínimas. Por eso es fundamental distinguir entre "contiene" (presencia segura), "puede contener trazas" (contaminación cruzada posible) y "libre de" (garantía de ausencia).

#### 4.1 Catálogo de Alérgenos: `alergeno`

Lista los 14 alérgenos de declaración obligatoria según la normativa alimentaria internacional.

```sql
CREATE TABLE alergeno (
    id SERIAL PRIMARY KEY,
    nombre VARCHAR(100) NOT NULL UNIQUE
);

INSERT INTO alergeno (nombre) VALUES
    ('gluten'), ('leche'), ('huevo'), ('pescado'),
    ('frutos_secos'), ('soja'), ('crustaceos'),
    ('moluscos'), ('cacahuetes'), ('apio'),
    ('mostaza'), ('sesamo'), ('sulfitos'), ('altramuces');
```

**Los 14 alérgenos regulados**:
1. **Gluten**: Presente en trigo, cebada, centeno, avena
2. **Leche**: Incluye lactosa y proteínas lácteas
3. **Huevo**: Tanto clara como yema
4. **Pescado**: Todas las especies
5. **Frutos secos**: Almendras, avellanas, nueces, anacardos, etc.
6. **Soja**: Incluye lecitina de soja
7. **Crustáceos**: Camarones, langostinos, cangrejos
8. **Moluscos**: Mejillones, calamares, pulpo
9. **Cacahuetes**: Se separa de frutos secos por su alta alergenicidad
10. **Apio**: Incluye sal de apio
11. **Mostaza**: Semillas y preparados
12. **Sésamo**: Semillas y aceite
13. **Sulfitos**: Conservantes en vinos y frutas secas
14. **Altramuces**: Legumbre usada en harinas alternativas

#### 4.2 Información General de Alérgenos: `plato_alergenos`

Almacena la información booleana y las notas generales sobre alérgenos del plato.

```sql
CREATE TABLE plato_alergenos (
    id SERIAL PRIMARY KEY,
    plato_id UUID NOT NULL UNIQUE REFERENCES plato(id) ON DELETE CASCADE,
    apto_celiaco BOOLEAN DEFAULT FALSE,
    notas TEXT
);
```

**Campos explicados**:
- `apto_celiaco`: Certificación especial. Un plato sin gluten no es automáticamente apto para celíacos; debe cumplir protocolos de manipulación específicos para evitar contaminación cruzada.
- `notas`: Información adicional como "Preparado en cocina que también procesa frutos secos" o "Puede adaptarse sin gluten bajo pedido previo".

#### 4.3 Alérgenos que Contiene: `plato_alergeno_contiene`

Lista los alérgenos que definitivamente están presentes en el plato como parte de su receta.

**Propósito en pwaMenu**: Estos alérgenos se muestran con iconos destacados en rojo en la ficha del plato. El filtro de búsqueda excluye automáticamente platos que contengan alérgenos seleccionados por el usuario.

**Propósito en RAG**: Respuestas directas como "Sí, la pizza cuatro quesos contiene gluten y lácteos".

```sql
CREATE TABLE plato_alergeno_contiene (
    id SERIAL PRIMARY KEY,
    plato_id UUID NOT NULL REFERENCES plato(id) ON DELETE CASCADE,
    alergeno_id INTEGER NOT NULL REFERENCES alergeno(id) ON DELETE RESTRICT,
    UNIQUE(plato_id, alergeno_id)
);

CREATE INDEX idx_plato_alergeno_contiene_plato ON plato_alergeno_contiene(plato_id);
```

#### 4.4 Posibles Trazas: `plato_alergeno_trazas`

Lista los alérgenos que podrían estar presentes por contaminación cruzada durante la preparación, aunque no sean ingredientes del plato.

**Propósito en pwaMenu**: Estos alérgenos se muestran con iconos en amarillo/naranja con texto "puede contener trazas de...". Personas con alergias leves pueden ignorarlos, pero personas con alergias severas deben evitar estos platos.

**Propósito en RAG**: Respuestas matizadas como "La ensalada de frutas no contiene frutos secos en su receta, pero se prepara en una cocina donde también se procesan frutos secos, por lo que podría contener trazas".

```sql
CREATE TABLE plato_alergeno_trazas (
    id SERIAL PRIMARY KEY,
    plato_id UUID NOT NULL REFERENCES plato(id) ON DELETE CASCADE,
    alergeno_id INTEGER NOT NULL REFERENCES alergeno(id) ON DELETE RESTRICT,
    UNIQUE(plato_id, alergeno_id)
);

CREATE INDEX idx_plato_alergeno_trazas_plato ON plato_alergeno_trazas(plato_id);
```

#### 4.5 Libre de Alérgenos: `plato_alergeno_libre`

Lista los alérgenos de los cuales el restaurante garantiza ausencia total. Esto es más fuerte que simplemente no estar en "contiene": implica protocolos activos para evitar contaminación.

**Propósito en pwaMenu**: Estos alérgenos se muestran con iconos en verde con un check. Permite búsquedas positivas como "mostrar platos garantizados libres de gluten".

**Propósito en RAG**: Respuestas con confianza alta como "El risotto de hongos está certificado libre de gluten y se prepara en una estación exclusiva para platos sin TACC".

```sql
CREATE TABLE plato_alergeno_libre (
    id SERIAL PRIMARY KEY,
    plato_id UUID NOT NULL REFERENCES plato(id) ON DELETE CASCADE,
    alergeno_id INTEGER NOT NULL REFERENCES alergeno(id) ON DELETE RESTRICT,
    UNIQUE(plato_id, alergeno_id)
);

CREATE INDEX idx_plato_alergeno_libre_plato ON plato_alergeno_libre(plato_id);
```

---

### 5. Perfil Alimentario: `plato_perfil_alimentario`

Esta tabla almacena las clasificaciones dietéticas del plato. A diferencia de los alérgenos (que son sobre seguridad), el perfil alimentario es sobre preferencias y estilos de vida.

**Propósito en pwaMenu**: Filtros rápidos en la parte superior del menú: "Vegetariano", "Vegano", "Sin Gluten", "Sin Lácteos". Un toggle que el comensal activa una vez y se aplica a toda su navegación.

**Propósito en RAG**: Respuestas a preguntas como "¿qué opciones veganas tienen?" o "Soy vegetariano, ¿qué me recomiendas de entrada?".

```sql
CREATE TABLE plato_perfil_alimentario (
    id SERIAL PRIMARY KEY,
    plato_id UUID NOT NULL UNIQUE REFERENCES plato(id) ON DELETE CASCADE,
    vegetariano BOOLEAN DEFAULT FALSE,
    vegano BOOLEAN DEFAULT FALSE,
    sin_gluten BOOLEAN DEFAULT FALSE,
    sin_lacteos BOOLEAN DEFAULT FALSE
);

CREATE INDEX idx_perfil_vegetariano ON plato_perfil_alimentario(vegetariano) WHERE vegetariano = TRUE;
CREATE INDEX idx_perfil_vegano ON plato_perfil_alimentario(vegano) WHERE vegano = TRUE;
CREATE INDEX idx_perfil_sin_gluten ON plato_perfil_alimentario(sin_gluten) WHERE sin_gluten = TRUE;
```

**Definiciones precisas**:
- `vegetariano`: No contiene carne ni pescado, pero puede contener huevo, lácteos y miel.
- `vegano`: No contiene ningún producto de origen animal. Implica vegetariano=TRUE.
- `sin_gluten`: No contiene trigo, cebada, centeno ni avena contaminada. No implica apto_celiaco.
- `sin_lacteos`: No contiene leche ni derivados lácteos. Útil para intolerantes a la lactosa.

**Nota sobre índices parciales**: Los índices `WHERE columna = TRUE` son índices parciales que solo indexan las filas donde el valor es verdadero. Esto es extremadamente eficiente porque típicamente solo el 10-20% de los platos serán veganos o sin gluten, haciendo que el índice sea muy pequeño y las búsquedas muy rápidas.

---

### 6. Sistema de Cocción

La información sobre métodos de cocción es relevante tanto para preferencias personales como para restricciones de salud. Algunas personas evitan fritos por razones cardiovasculares; otras buscan específicamente alimentos crudos.

#### 6.1 Catálogo de Métodos: `metodo_coccion`

```sql
CREATE TABLE metodo_coccion (
    id SERIAL PRIMARY KEY,
    nombre VARCHAR(50) NOT NULL UNIQUE
);

INSERT INTO metodo_coccion (nombre) VALUES
    ('horneado'), ('frito'), ('grillado'), ('crudo'),
    ('hervido'), ('al_vapor'), ('salteado'), ('braseado');
```

**Métodos disponibles**:
- `horneado`: Cocción en horno, típicamente con calor seco
- `frito`: Inmersión en aceite caliente
- `grillado`: Cocción a la parrilla o plancha con contacto directo
- `crudo`: Sin aplicación de calor (ceviches, tartares, ensaladas)
- `hervido`: Cocción en agua o caldo
- `al_vapor`: Cocción con vapor de agua, sin inmersión
- `salteado`: Cocción rápida en sartén con poco aceite
- `braseado`: Cocción lenta con líquido en recipiente cerrado

#### 6.2 Información de Cocción: `plato_coccion`

```sql
CREATE TABLE plato_coccion (
    id SERIAL PRIMARY KEY,
    plato_id UUID NOT NULL UNIQUE REFERENCES plato(id) ON DELETE CASCADE,
    usa_aceite BOOLEAN DEFAULT FALSE
);
```

**Campo `usa_aceite`**: Indica si el plato utiliza aceite en su preparación. Relevante para personas que siguen dietas bajas en grasas o que tienen restricciones médicas específicas.

#### 6.3 Relación Plato-Método: `plato_metodo_coccion`

Un plato puede combinar múltiples métodos de cocción. Por ejemplo, una milanesa es primero empanizada y luego frita; un pollo puede ser primero hervido y luego grillado.

**Propósito en pwaMenu**: Iconos de método de cocción en la ficha del plato. Filtro "Sin fritos" para personas que los evitan.

**Propósito en RAG**: Respuestas como "El salmón se prepara grillado a la plancha, sin fritura".

```sql
CREATE TABLE plato_metodo_coccion (
    id SERIAL PRIMARY KEY,
    plato_id UUID NOT NULL REFERENCES plato(id) ON DELETE CASCADE,
    metodo_coccion_id INTEGER NOT NULL REFERENCES metodo_coccion(id) ON DELETE RESTRICT,
    UNIQUE(plato_id, metodo_coccion_id)
);

CREATE INDEX idx_plato_metodo_coccion_plato ON plato_metodo_coccion(plato_id);
```

---

### 7. Perfil Sensorial

El perfil sensorial describe la experiencia gustativa y táctil del plato. Esta información ayuda a los comensales a elegir platos acordes a sus preferencias y permite al chatbot hacer recomendaciones personalizadas.

#### 7.1 Catálogo de Sabores: `sabor`

```sql
CREATE TABLE sabor (
    id SERIAL PRIMARY KEY,
    nombre VARCHAR(50) NOT NULL UNIQUE
);

INSERT INTO sabor (nombre) VALUES
    ('suave'), ('intenso'), ('dulce'), ('salado'),
    ('acido'), ('amargo'), ('umami'), ('picante');
```

**Perfiles de sabor**:
- `suave`: Sabores delicados, no dominantes
- `intenso`: Sabores pronunciados y memorables
- `dulce`: Presencia de azúcares o edulcorantes
- `salado`: Presencia notable de sal o ingredientes salados
- `acido`: Notas cítricas o avinagradas
- `amargo`: Presente en cafés, chocolates oscuros, algunas verduras
- `umami`: El quinto sabor, presente en carnes, quesos curados, tomates
- `picante`: Presencia de chiles, pimienta u otros irritantes

#### 7.2 Catálogo de Texturas: `textura`

```sql
CREATE TABLE textura (
    id SERIAL PRIMARY KEY,
    nombre VARCHAR(50) NOT NULL UNIQUE
);

INSERT INTO textura (nombre) VALUES
    ('crocante'), ('cremoso'), ('tierno'), ('firme'),
    ('esponjoso'), ('gelatinoso'), ('granulado');
```

**Perfiles de textura**:
- `crocante`: Resistencia al morder que produce sonido (chips, empanados)
- `cremoso`: Suave y untuoso (purés, salsas, helados)
- `tierno`: Cede fácilmente al corte (carnes bien cocidas, vegetales al vapor)
- `firme`: Resistencia moderada, mantiene forma (carnes a punto, vegetales al dente)
- `esponjoso`: Lleno de aire, ligero (panes, bizcochos, soufflés)
- `gelatinoso`: Consistencia elástica (gelatinas, algunos postres)
- `granulado`: Partículas distinguibles (couscous, quinoa, algunos helados artesanales)

#### 7.3 Relaciones Plato-Sabor y Plato-Textura

**Propósito en pwaMenu**: Filtros secundarios y badges descriptivos. Un comensal puede buscar "platos cremosos y suaves" para una cena tranquila.

**Propósito en RAG**: Recomendaciones contextuales como "Si buscas algo crocante y salado, te recomiendo las empanadas fritas" o "Para un postre intenso y cremoso, prueba el tiramisú".

```sql
CREATE TABLE plato_sabor (
    id SERIAL PRIMARY KEY,
    plato_id UUID NOT NULL REFERENCES plato(id) ON DELETE CASCADE,
    sabor_id INTEGER NOT NULL REFERENCES sabor(id) ON DELETE RESTRICT,
    UNIQUE(plato_id, sabor_id)
);

CREATE TABLE plato_textura (
    id SERIAL PRIMARY KEY,
    plato_id UUID NOT NULL REFERENCES plato(id) ON DELETE CASCADE,
    textura_id INTEGER NOT NULL REFERENCES textura(id) ON DELETE RESTRICT,
    UNIQUE(plato_id, textura_id)
);

CREATE INDEX idx_plato_sabor_plato ON plato_sabor(plato_id);
CREATE INDEX idx_plato_textura_plato ON plato_textura(plato_id);
```

---

### 8. Modificaciones Permitidas: `plato_modificacion`

Esta tabla documenta qué cambios puede solicitar un comensal sobre el plato estándar. Es fundamental para la operación del restaurante porque no todas las modificaciones son posibles (por receta, por disponibilidad de ingredientes, o por impacto en la calidad del plato).

**Propósito en pwaMenu**: Cuando un comensal agrega un plato al carrito, puede ver las modificaciones disponibles como opciones seleccionables. Ejemplo: "Sin cebolla", "Sustituir papas fritas por ensalada".

**Propósito en RAG**: Respuestas a preguntas como "¿Puedo pedir la hamburguesa sin pepinillos?" → "Sí, puedes solicitar la hamburguesa sin pepinillos" o "¿Puedo cambiar el pan por pan sin gluten?" → "Lo siento, actualmente no ofrecemos sustitución de pan en las hamburguesas".

```sql
CREATE TABLE plato_modificacion (
    id SERIAL PRIMARY KEY,
    plato_id UUID NOT NULL REFERENCES plato(id) ON DELETE CASCADE,
    accion VARCHAR(20) NOT NULL CHECK (accion IN ('retirar', 'sustituir')),
    item VARCHAR(255) NOT NULL,
    permitido BOOLEAN DEFAULT TRUE
);

CREATE INDEX idx_plato_modificacion_plato ON plato_modificacion(plato_id);
CREATE INDEX idx_plato_modificacion_permitido ON plato_modificacion(plato_id, permitido) WHERE permitido = TRUE;
```

**Campos explicados**:
- `accion`: Tipo de modificación. `retirar` significa quitar un ingrediente; `sustituir` significa reemplazar un componente por otro.
- `item`: Descripción de la modificación. Ejemplos: "cebolla", "papas fritas por ensalada", "salsa picante".
- `permitido`: Si es TRUE, la modificación está disponible. Si es FALSE, se documenta explícitamente que NO se puede hacer (útil para el RAG al responder negativamente con certeza).

**Ejemplo de datos**:
| accion | item | permitido |
|--------|------|-----------|
| retirar | cebolla | TRUE |
| retirar | queso | TRUE |
| sustituir | papas fritas por ensalada | TRUE |
| sustituir | pan común por pan sin gluten | FALSE |
| retirar | salsa del plato | FALSE |

---

### 9. Advertencias: `plato_advertencia`

Esta tabla almacena mensajes de advertencia importantes que deben comunicarse al comensal. Son avisos que no encajan en otras categorías pero que son relevantes para la experiencia o seguridad.

**Propósito en pwaMenu**: Estas advertencias aparecen destacadas en la ficha del plato, típicamente con un icono de alerta. Son de lectura obligatoria antes de agregar al carrito.

**Propósito en RAG**: El chatbot incluye estas advertencias en sus respuestas cuando son relevantes. Si alguien pregunta por un plato que tiene advertencias, el bot las menciona proactivamente.

```sql
CREATE TABLE plato_advertencia (
    id SERIAL PRIMARY KEY,
    plato_id UUID NOT NULL REFERENCES plato(id) ON DELETE CASCADE,
    texto TEXT NOT NULL
);

CREATE INDEX idx_plato_advertencia_plato ON plato_advertencia(plato_id);
```

**Ejemplos de advertencias**:
- "Este plato contiene huesos pequeños"
- "Preparación con alcohol (no se evapora completamente)"
- "Servido muy caliente, esperar antes de consumir"
- "Porción diseñada para compartir entre 2 personas"
- "Tiempo de preparación: 25-30 minutos"
- "Contiene cafeína"
- "No apto para embarazadas (queso sin pasteurizar)"

---

### 10. Configuración RAG: `plato_rag`

Esta tabla es específica para el sistema de inteligencia artificial. Configura cómo el chatbot debe manejar las consultas relacionadas con este plato.

**Propósito exclusivo para RAG**: El campo `nivel_riesgo_base` indica al sistema cuánta precaución debe tener al responder preguntas sobre este plato. Un plato de alto riesgo requiere respuestas más conservadoras y disclaimers adicionales.

```sql
CREATE TABLE plato_rag (
    id SERIAL PRIMARY KEY,
    plato_id UUID NOT NULL UNIQUE REFERENCES plato(id) ON DELETE CASCADE,
    nivel_riesgo_base VARCHAR(10) NOT NULL DEFAULT 'bajo' CHECK (nivel_riesgo_base IN ('bajo', 'medio', 'alto'))
);

CREATE INDEX idx_plato_rag_riesgo ON plato_rag(nivel_riesgo_base);
```

**Niveles de riesgo**:

- **`bajo`**: Platos simples sin alérgenos relevantes. El chatbot puede responder con confianza y sin disclaimers especiales. Ejemplo: ensalada de frutas frescas.

- **`medio`**: Platos que contienen alérgenos comunes o tienen preparaciones que podrían generar dudas. El chatbot incluye recordatorios de verificar con el personal. Ejemplo: platos con lácteos o gluten.

- **`alto`**: Platos con múltiples alérgenos, posibles trazas, o ingredientes que pueden causar reacciones severas (frutos secos, mariscos). El chatbot siempre deriva a consultar con personal del restaurante y nunca hace afirmaciones absolutas. Ejemplo: plato thai con maní y salsa de pescado.

**Comportamiento del RAG según nivel**:
```
Nivel bajo:  "Sí, la ensalada de frutas es vegana y no contiene alérgenos."
Nivel medio: "La pasta carbonara contiene gluten, huevo y lácteos. Si tienes dudas sobre alguna restricción específica, nuestro personal puede asistirte."
Nivel alto:  "El pad thai contiene cacahuetes, salsa de pescado y huevo. Debido a la naturaleza de estos alérgenos, te recomiendo confirmar directamente con nuestro personal de cocina antes de ordenar, especialmente si tienes alergias severas."
```

---

## Vista Consolidada: `v_plato_completo`

Esta vista materializa toda la información dispersa en las 19 tablas en un único objeto JSON por plato. Es la interfaz principal para consumir los datos tanto desde pwaMenu como para el proceso de ingesta al RAG.

**Propósito en pwaMenu**: El endpoint `/api/public/menu/{slug}` utiliza esta vista (o una consulta equivalente) para obtener toda la información del plato en una sola llamada a la base de datos, evitando múltiples round-trips.

**Propósito en RAG**: El proceso de ingesta convierte este JSON en texto estructurado que se almacena como embedding vectorial en la tabla `knowledge_document`.

```sql
CREATE VIEW v_plato_completo AS
SELECT
    p.id,
    p.nombre,
    p.categoria,
    jsonb_build_object(
        'corta', pd.corta,
        'menu', pd.menu
    ) AS descripcion,
    (
        SELECT jsonb_agg(jsonb_build_object(
            'nombre', i.nombre,
            'grupo', gi.nombre,
            'es_procesado', i.es_procesado,
            'sub_ingredientes', COALESCE(
                (SELECT jsonb_agg(si.nombre) FROM sub_ingrediente si WHERE si.ingrediente_id = i.id),
                '[]'::jsonb
            )
        ))
        FROM plato_ingrediente pi
        JOIN ingrediente i ON i.id = pi.ingrediente_id
        LEFT JOIN grupo_ingrediente gi ON gi.id = i.grupo_id
        WHERE pi.plato_id = p.id
    ) AS ingredientes,
    jsonb_build_object(
        'contiene', COALESCE((SELECT jsonb_agg(a.nombre) FROM plato_alergeno_contiene pac JOIN alergeno a ON a.id = pac.alergeno_id WHERE pac.plato_id = p.id), '[]'::jsonb),
        'puede_contener_trazas_de', COALESCE((SELECT jsonb_agg(a.nombre) FROM plato_alergeno_trazas pat JOIN alergeno a ON a.id = pat.alergeno_id WHERE pat.plato_id = p.id), '[]'::jsonb),
        'libre_de', COALESCE((SELECT jsonb_agg(a.nombre) FROM plato_alergeno_libre pal JOIN alergeno a ON a.id = pal.alergeno_id WHERE pal.plato_id = p.id), '[]'::jsonb),
        'apto_celiaco', COALESCE(pa.apto_celiaco, FALSE),
        'notas', pa.notas
    ) AS alergenos,
    jsonb_build_object(
        'vegetariano', COALESCE(ppa.vegetariano, FALSE),
        'vegano', COALESCE(ppa.vegano, FALSE),
        'sin_gluten', COALESCE(ppa.sin_gluten, FALSE),
        'sin_lacteos', COALESCE(ppa.sin_lacteos, FALSE)
    ) AS perfil_alimentario,
    jsonb_build_object(
        'metodos', COALESCE((SELECT jsonb_agg(mc.nombre) FROM plato_metodo_coccion pmc JOIN metodo_coccion mc ON mc.id = pmc.metodo_coccion_id WHERE pmc.plato_id = p.id), '[]'::jsonb),
        'usa_aceite', COALESCE(pc.usa_aceite, FALSE)
    ) AS coccion,
    jsonb_build_object(
        'sabor', COALESCE((SELECT jsonb_agg(s.nombre) FROM plato_sabor ps JOIN sabor s ON s.id = ps.sabor_id WHERE ps.plato_id = p.id), '[]'::jsonb),
        'textura', COALESCE((SELECT jsonb_agg(t.nombre) FROM plato_textura pt JOIN textura t ON t.id = pt.textura_id WHERE pt.plato_id = p.id), '[]'::jsonb)
    ) AS sensorial,
    COALESCE((
        SELECT jsonb_agg(jsonb_build_object(
            'accion', pm.accion,
            'item', pm.item,
            'permitido', pm.permitido
        ))
        FROM plato_modificacion pm WHERE pm.plato_id = p.id
    ), '[]'::jsonb) AS modificaciones,
    COALESCE((SELECT jsonb_agg(pav.texto) FROM plato_advertencia pav WHERE pav.plato_id = p.id), '[]'::jsonb) AS advertencias,
    jsonb_build_object(
        'nivel_riesgo_base', COALESCE(pr.nivel_riesgo_base, 'bajo')
    ) AS rag
FROM plato p
LEFT JOIN plato_descripcion pd ON pd.plato_id = p.id
LEFT JOIN plato_alergenos pa ON pa.plato_id = p.id
LEFT JOIN plato_perfil_alimentario ppa ON ppa.plato_id = p.id
LEFT JOIN plato_coccion pc ON pc.plato_id = p.id
LEFT JOIN plato_rag pr ON pr.plato_id = p.id
WHERE p.is_active = TRUE;
```

**Notas técnicas sobre la vista**:
- Usa `LEFT JOIN` para todas las tablas secundarias, asegurando que un plato aparezca incluso si no tiene datos en alguna tabla relacionada.
- Los `COALESCE` garantizan valores por defecto sensatos (FALSE para booleanos, arrays vacíos para listas).
- Las subconsultas con `jsonb_agg` construyen arrays JSON de forma dinámica.
- El filtro `WHERE p.is_active = TRUE` excluye platos dados de baja.

---

## Consultas de Referencia para pwaMenu

Las siguientes consultas representan los casos de uso más comunes desde la aplicación pwaMenu.

### Buscar Platos Aptos para Celíacos

Esta consulta es crítica para personas con enfermedad celíaca. El flag `apto_celiaco` es más restrictivo que simplemente `sin_gluten` porque implica protocolos de preparación seguros.

```sql
SELECT p.id, p.nombre, p.categoria
FROM plato p
JOIN plato_alergenos pa ON pa.plato_id = p.id
WHERE pa.apto_celiaco = TRUE
  AND p.is_active = TRUE;
```

### Buscar Platos Veganos sin Frutos Secos

Combina un filtro de perfil alimentario (vegano) con una exclusión de alérgeno (frutos secos). Útil para personas veganas con alergias.

```sql
SELECT p.id, p.nombre
FROM plato p
JOIN plato_perfil_alimentario ppa ON ppa.plato_id = p.id
WHERE ppa.vegano = TRUE
  AND p.is_active = TRUE
  AND NOT EXISTS (
    SELECT 1 FROM plato_alergeno_contiene pac
    JOIN alergeno a ON a.id = pac.alergeno_id
    WHERE pac.plato_id = p.id AND a.nombre = 'frutos_secos'
  );
```

### Buscar Platos por Ingrediente

Permite encontrar todos los platos que contienen un ingrediente específico. Útil tanto para búsquedas positivas ("quiero algo con pollo") como negativas ("evitar platos con mariscos").

```sql
SELECT DISTINCT p.id, p.nombre
FROM plato p
JOIN plato_ingrediente pi ON pi.plato_id = p.id
JOIN ingrediente i ON i.id = pi.ingrediente_id
WHERE i.nombre ILIKE '%pollo%'
  AND p.is_active = TRUE;
```

### Filtro Compuesto: Vegetariano, Sin Gluten, No Frito

Ejemplo de consulta compleja que combina múltiples criterios de filtrado.

```sql
SELECT p.id, p.nombre, p.categoria
FROM plato p
JOIN plato_perfil_alimentario ppa ON ppa.plato_id = p.id
WHERE ppa.vegetariano = TRUE
  AND ppa.sin_gluten = TRUE
  AND p.is_active = TRUE
  AND NOT EXISTS (
    SELECT 1 FROM plato_metodo_coccion pmc
    JOIN metodo_coccion mc ON mc.id = pmc.metodo_coccion_id
    WHERE pmc.plato_id = p.id AND mc.nombre = 'frito'
  );
```

---

## Consultas de Referencia para RAG

Las siguientes consultas son utilizadas por el sistema de ingesta y por el servicio RAG para responder consultas.

### Platos de Alto Riesgo

El RAG necesita identificar platos de alto riesgo para aplicar disclaimers adicionales y derivar al personal del restaurante.

```sql
SELECT p.id, p.nombre, pr.nivel_riesgo_base
FROM plato p
JOIN plato_rag pr ON pr.plato_id = p.id
WHERE pr.nivel_riesgo_base = 'alto'
ORDER BY p.nombre;
```

### Generar Texto para Ingesta RAG

Esta consulta genera un texto estructurado optimizado para embedding vectorial. El formato facilita la búsqueda semántica.

```sql
SELECT
    p.id,
    p.nombre,
    concat_ws(E'\n',
        'PLATO: ' || p.nombre,
        'CATEGORÍA: ' || p.categoria,
        'DESCRIPCIÓN: ' || COALESCE(pd.menu, pd.corta, ''),
        CASE WHEN ppa.vegano THEN 'APTO VEGANO' ELSE NULL END,
        CASE WHEN ppa.vegetariano AND NOT ppa.vegano THEN 'APTO VEGETARIANO' ELSE NULL END,
        CASE WHEN ppa.sin_gluten THEN 'SIN GLUTEN' ELSE NULL END,
        CASE WHEN pa.apto_celiaco THEN 'APTO CELÍACO' ELSE NULL END,
        'ALÉRGENOS: ' || COALESCE(
            (SELECT string_agg(a.nombre, ', ')
             FROM plato_alergeno_contiene pac
             JOIN alergeno a ON a.id = pac.alergeno_id
             WHERE pac.plato_id = p.id),
            'ninguno'
        ),
        CASE WHEN EXISTS (SELECT 1 FROM plato_alergeno_trazas pat WHERE pat.plato_id = p.id)
            THEN 'TRAZAS POSIBLES: ' || (
                SELECT string_agg(a.nombre, ', ')
                FROM plato_alergeno_trazas pat
                JOIN alergeno a ON a.id = pat.alergeno_id
                WHERE pat.plato_id = p.id
            )
            ELSE NULL
        END,
        'NIVEL DE RIESGO: ' || COALESCE(pr.nivel_riesgo_base, 'bajo')
    ) AS texto_rag
FROM plato p
LEFT JOIN plato_descripcion pd ON pd.plato_id = p.id
LEFT JOIN plato_perfil_alimentario ppa ON ppa.plato_id = p.id
LEFT JOIN plato_alergenos pa ON pa.plato_id = p.id
LEFT JOIN plato_rag pr ON pr.plato_id = p.id
WHERE p.is_active = TRUE;
```

**Ejemplo de salida**:
```
PLATO: Milanesa Napolitana
CATEGORÍA: plato_principal
DESCRIPCIÓN: Milanesa de ternera con salsa de tomate, jamón y mozzarella gratinada
ALÉRGENOS: gluten, huevo, leche
TRAZAS POSIBLES: frutos_secos
NIVEL DE RIESGO: medio
```

---

## Resumen de Normalización

El modelo cumple con todas las formas normales hasta BCNF, lo que garantiza:

| Forma Normal | Cumplimiento | Significado Práctico |
|--------------|--------------|----------------------|
| 1NF | ✅ | Cada celda contiene un único valor atómico. No hay arrays ni grupos repetidos dentro de una columna. |
| 2NF | ✅ | Todos los atributos no clave dependen completamente de la clave primaria, no de una parte de ella. |
| 3NF | ✅ | No existen dependencias transitivas. Un atributo no clave no depende de otro atributo no clave. |
| BCNF | ✅ | Cada determinante (conjunto de atributos que determina otros) es una clave candidata. |

---

## Inventario de Tablas

**Total de tablas**: 19

### Tablas Principales (1)
| Tabla | Propósito |
|-------|-----------|
| `plato` | Entidad central del modelo |

### Tablas Catálogo (6)
| Tabla | Propósito |
|-------|-----------|
| `alergeno` | 14 alérgenos de declaración obligatoria |
| `ingrediente` | Catálogo maestro de ingredientes |
| `grupo_ingrediente` | Clasificación nutricional de ingredientes |
| `metodo_coccion` | 8 métodos de preparación |
| `sabor` | 8 perfiles de sabor |
| `textura` | 7 perfiles de textura |

### Tablas de Detalle 1:1 (5)
| Tabla | Propósito |
|-------|-----------|
| `plato_descripcion` | Textos descriptivos del plato |
| `plato_alergenos` | Flags y notas de alérgenos |
| `plato_perfil_alimentario` | Clasificación dietética |
| `plato_coccion` | Información de cocción |
| `plato_rag` | Configuración para IA |

### Tablas de Relación M:N (7)
| Tabla | Propósito |
|-------|-----------|
| `plato_ingrediente` | Ingredientes del plato |
| `sub_ingrediente` | Componentes de ingredientes procesados |
| `plato_alergeno_contiene` | Alérgenos presentes |
| `plato_alergeno_trazas` | Posibles trazas |
| `plato_alergeno_libre` | Garantía de ausencia |
| `plato_metodo_coccion` | Métodos usados |
| `plato_sabor` | Perfiles de sabor |
| `plato_textura` | Perfiles de textura |
| `plato_modificacion` | Cambios permitidos |
| `plato_advertencia` | Avisos importantes |

---

## Integración con el Sistema Integrador

### Relación con Modelos Existentes

Este modelo de platos canónicos complementa el modelo `Product` existente en el backend. La relación propuesta es:

```
Product (modelo existente)
    ├── id, name, price, category_id, subcategory_id
    └── canonical_dish_id (FK) → plato.id (nuevo)
```

De esta forma, un `Product` del menú puede opcionalmente vincularse a un registro `plato` para heredar toda su información nutricional y de alérgenos.

### Endpoints Sugeridos

```
GET  /api/public/dishes                    # Lista platos con filtros
GET  /api/public/dishes/{id}               # Detalle completo de un plato
GET  /api/public/dishes/filters            # Valores disponibles para filtros

POST /api/admin/dishes                     # Crear plato (KITCHEN+)
PUT  /api/admin/dishes/{id}                # Actualizar plato
DELETE /api/admin/dishes/{id}              # Soft delete

POST /api/admin/dishes/{id}/ingest         # Ingestar al RAG
```

### Permisos por Rol

| Operación | WAITER | KITCHEN | MANAGER | ADMIN |
|-----------|--------|---------|---------|-------|
| Ver platos | ✅ | ✅ | ✅ | ✅ |
| Crear/Editar | ❌ | ✅ | ✅ | ✅ |
| Eliminar | ❌ | ❌ | ✅ | ✅ |
| Ingestar RAG | ❌ | ✅ | ✅ | ✅ |

---

## Apéndice: Script de Creación Completo

Para conveniencia de implementación, aquí está el script SQL completo que crea todas las tablas en el orden correcto de dependencias:

```sql
-- 1. Tabla principal
CREATE TABLE plato (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    nombre VARCHAR(255) NOT NULL,
    categoria VARCHAR(50) NOT NULL CHECK (categoria IN ('entrada', 'plato_principal', 'postre', 'bebida')),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    is_active BOOLEAN DEFAULT TRUE
);
CREATE INDEX idx_plato_categoria ON plato(categoria);
CREATE INDEX idx_plato_nombre ON plato(nombre);

-- 2. Descripciones
CREATE TABLE plato_descripcion (
    id SERIAL PRIMARY KEY,
    plato_id UUID NOT NULL UNIQUE REFERENCES plato(id) ON DELETE CASCADE,
    corta TEXT,
    menu TEXT
);

-- 3. Sistema de ingredientes
CREATE TABLE grupo_ingrediente (
    id SERIAL PRIMARY KEY,
    nombre VARCHAR(50) NOT NULL UNIQUE CHECK (nombre IN ('proteina', 'vegetal', 'lacteo', 'cereal', 'otro'))
);

CREATE TABLE ingrediente (
    id SERIAL PRIMARY KEY,
    nombre VARCHAR(255) NOT NULL,
    grupo_id INTEGER REFERENCES grupo_ingrediente(id),
    es_procesado BOOLEAN DEFAULT FALSE,
    UNIQUE(nombre, grupo_id)
);
CREATE INDEX idx_ingrediente_nombre ON ingrediente(nombre);
CREATE INDEX idx_ingrediente_grupo ON ingrediente(grupo_id);

CREATE TABLE sub_ingrediente (
    id SERIAL PRIMARY KEY,
    ingrediente_id INTEGER NOT NULL REFERENCES ingrediente(id) ON DELETE CASCADE,
    nombre VARCHAR(255) NOT NULL
);
CREATE INDEX idx_sub_ingrediente_padre ON sub_ingrediente(ingrediente_id);

CREATE TABLE plato_ingrediente (
    id SERIAL PRIMARY KEY,
    plato_id UUID NOT NULL REFERENCES plato(id) ON DELETE CASCADE,
    ingrediente_id INTEGER NOT NULL REFERENCES ingrediente(id) ON DELETE RESTRICT,
    UNIQUE(plato_id, ingrediente_id)
);
CREATE INDEX idx_plato_ingrediente_plato ON plato_ingrediente(plato_id);
CREATE INDEX idx_plato_ingrediente_ingrediente ON plato_ingrediente(ingrediente_id);

-- 4. Sistema de alérgenos
CREATE TABLE alergeno (
    id SERIAL PRIMARY KEY,
    nombre VARCHAR(100) NOT NULL UNIQUE
);
INSERT INTO alergeno (nombre) VALUES
    ('gluten'), ('leche'), ('huevo'), ('pescado'),
    ('frutos_secos'), ('soja'), ('crustaceos'),
    ('moluscos'), ('cacahuetes'), ('apio'),
    ('mostaza'), ('sesamo'), ('sulfitos'), ('altramuces');

CREATE TABLE plato_alergenos (
    id SERIAL PRIMARY KEY,
    plato_id UUID NOT NULL UNIQUE REFERENCES plato(id) ON DELETE CASCADE,
    apto_celiaco BOOLEAN DEFAULT FALSE,
    notas TEXT
);

CREATE TABLE plato_alergeno_contiene (
    id SERIAL PRIMARY KEY,
    plato_id UUID NOT NULL REFERENCES plato(id) ON DELETE CASCADE,
    alergeno_id INTEGER NOT NULL REFERENCES alergeno(id) ON DELETE RESTRICT,
    UNIQUE(plato_id, alergeno_id)
);
CREATE INDEX idx_plato_alergeno_contiene_plato ON plato_alergeno_contiene(plato_id);

CREATE TABLE plato_alergeno_trazas (
    id SERIAL PRIMARY KEY,
    plato_id UUID NOT NULL REFERENCES plato(id) ON DELETE CASCADE,
    alergeno_id INTEGER NOT NULL REFERENCES alergeno(id) ON DELETE RESTRICT,
    UNIQUE(plato_id, alergeno_id)
);
CREATE INDEX idx_plato_alergeno_trazas_plato ON plato_alergeno_trazas(plato_id);

CREATE TABLE plato_alergeno_libre (
    id SERIAL PRIMARY KEY,
    plato_id UUID NOT NULL REFERENCES plato(id) ON DELETE CASCADE,
    alergeno_id INTEGER NOT NULL REFERENCES alergeno(id) ON DELETE RESTRICT,
    UNIQUE(plato_id, alergeno_id)
);
CREATE INDEX idx_plato_alergeno_libre_plato ON plato_alergeno_libre(plato_id);

-- 5. Perfil alimentario
CREATE TABLE plato_perfil_alimentario (
    id SERIAL PRIMARY KEY,
    plato_id UUID NOT NULL UNIQUE REFERENCES plato(id) ON DELETE CASCADE,
    vegetariano BOOLEAN DEFAULT FALSE,
    vegano BOOLEAN DEFAULT FALSE,
    sin_gluten BOOLEAN DEFAULT FALSE,
    sin_lacteos BOOLEAN DEFAULT FALSE
);
CREATE INDEX idx_perfil_vegetariano ON plato_perfil_alimentario(vegetariano) WHERE vegetariano = TRUE;
CREATE INDEX idx_perfil_vegano ON plato_perfil_alimentario(vegano) WHERE vegano = TRUE;
CREATE INDEX idx_perfil_sin_gluten ON plato_perfil_alimentario(sin_gluten) WHERE sin_gluten = TRUE;

-- 6. Sistema de cocción
CREATE TABLE metodo_coccion (
    id SERIAL PRIMARY KEY,
    nombre VARCHAR(50) NOT NULL UNIQUE
);
INSERT INTO metodo_coccion (nombre) VALUES
    ('horneado'), ('frito'), ('grillado'), ('crudo'),
    ('hervido'), ('al_vapor'), ('salteado'), ('braseado');

CREATE TABLE plato_coccion (
    id SERIAL PRIMARY KEY,
    plato_id UUID NOT NULL UNIQUE REFERENCES plato(id) ON DELETE CASCADE,
    usa_aceite BOOLEAN DEFAULT FALSE
);

CREATE TABLE plato_metodo_coccion (
    id SERIAL PRIMARY KEY,
    plato_id UUID NOT NULL REFERENCES plato(id) ON DELETE CASCADE,
    metodo_coccion_id INTEGER NOT NULL REFERENCES metodo_coccion(id) ON DELETE RESTRICT,
    UNIQUE(plato_id, metodo_coccion_id)
);
CREATE INDEX idx_plato_metodo_coccion_plato ON plato_metodo_coccion(plato_id);

-- 7. Perfil sensorial
CREATE TABLE sabor (
    id SERIAL PRIMARY KEY,
    nombre VARCHAR(50) NOT NULL UNIQUE
);
INSERT INTO sabor (nombre) VALUES
    ('suave'), ('intenso'), ('dulce'), ('salado'),
    ('acido'), ('amargo'), ('umami'), ('picante');

CREATE TABLE textura (
    id SERIAL PRIMARY KEY,
    nombre VARCHAR(50) NOT NULL UNIQUE
);
INSERT INTO textura (nombre) VALUES
    ('crocante'), ('cremoso'), ('tierno'), ('firme'),
    ('esponjoso'), ('gelatinoso'), ('granulado');

CREATE TABLE plato_sabor (
    id SERIAL PRIMARY KEY,
    plato_id UUID NOT NULL REFERENCES plato(id) ON DELETE CASCADE,
    sabor_id INTEGER NOT NULL REFERENCES sabor(id) ON DELETE RESTRICT,
    UNIQUE(plato_id, sabor_id)
);
CREATE INDEX idx_plato_sabor_plato ON plato_sabor(plato_id);

CREATE TABLE plato_textura (
    id SERIAL PRIMARY KEY,
    plato_id UUID NOT NULL REFERENCES plato(id) ON DELETE CASCADE,
    textura_id INTEGER NOT NULL REFERENCES textura(id) ON DELETE RESTRICT,
    UNIQUE(plato_id, textura_id)
);
CREATE INDEX idx_plato_textura_plato ON plato_textura(plato_id);

-- 8. Modificaciones
CREATE TABLE plato_modificacion (
    id SERIAL PRIMARY KEY,
    plato_id UUID NOT NULL REFERENCES plato(id) ON DELETE CASCADE,
    accion VARCHAR(20) NOT NULL CHECK (accion IN ('retirar', 'sustituir')),
    item VARCHAR(255) NOT NULL,
    permitido BOOLEAN DEFAULT TRUE
);
CREATE INDEX idx_plato_modificacion_plato ON plato_modificacion(plato_id);
CREATE INDEX idx_plato_modificacion_permitido ON plato_modificacion(plato_id, permitido) WHERE permitido = TRUE;

-- 9. Advertencias
CREATE TABLE plato_advertencia (
    id SERIAL PRIMARY KEY,
    plato_id UUID NOT NULL REFERENCES plato(id) ON DELETE CASCADE,
    texto TEXT NOT NULL
);
CREATE INDEX idx_plato_advertencia_plato ON plato_advertencia(plato_id);

-- 10. Configuración RAG
CREATE TABLE plato_rag (
    id SERIAL PRIMARY KEY,
    plato_id UUID NOT NULL UNIQUE REFERENCES plato(id) ON DELETE CASCADE,
    nivel_riesgo_base VARCHAR(10) NOT NULL DEFAULT 'bajo' CHECK (nivel_riesgo_base IN ('bajo', 'medio', 'alto'))
);
CREATE INDEX idx_plato_rag_riesgo ON plato_rag(nivel_riesgo_base);
```

---

*Documento generado para el proyecto Integrador - Sistema de Gestión de Restaurantes*
*Última actualización: Enero 2026*
