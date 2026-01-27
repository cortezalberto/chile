# Sistema de Skills para Agentes de Código

## Arquitectura

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                         FLUJO DE AGENTES DE CÓDIGO                           │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                              │
│   Usuario                                                                    │
│      │                                                                       │
│      ▼                                                                       │
│   ┌──────────────────┐                                                      │
│   │  Router Agent    │  ← Identifica HU-ID → PT-ID → Nivel de riesgo       │
│   │  (dispatcher)    │                                                      │
│   └────────┬─────────┘                                                      │
│            │                                                                 │
│            ├─────────────────┬─────────────────┬─────────────────┐          │
│            ▼                 ▼                 ▼                 ▼          │
│   ┌────────────────┐ ┌────────────────┐ ┌────────────────┐ ┌────────────┐  │
│   │ 🔴 CRÍTICO     │ │ 🟠 ALTO        │ │ 🟡 MEDIO       │ │ 🟢 BAJO    │  │
│   │ análisis-only  │ │ supervisado    │ │ con-review     │ │ autónomo   │  │
│   ├────────────────┤ ├────────────────┤ ├────────────────┤ ├────────────┤  │
│   │ • auth-analyst │ │ • product-dev  │ │ • kitchen-dev  │ │ • catalog  │  │
│   │ • billing-     │ │ • events-dev   │ │ • waiter-dev   │ │ • sector   │  │
│   │   analyst      │ │ • blacklist-   │ │ • diner-dev    │ │ • recipe   │  │
│   │ • allergen-    │ │   dev          │ │ • session-dev  │ │ • promo    │  │
│   │   analyst      │ │                │ │                │ │ • public   │  │
│   │ • staff-       │ │                │ │                │ │ • health   │  │
│   │   analyst      │ │                │ │                │ │ • audit    │  │
│   └────────────────┘ └────────────────┘ └────────────────┘ └────────────┘  │
│            │                 │                 │                 │          │
│            ▼                 ▼                 ▼                 ▼          │
│   ┌────────────────┐ ┌────────────────┐ ┌────────────────┐ ┌────────────┐  │
│   │ OUTPUT:        │ │ OUTPUT:        │ │ OUTPUT:        │ │ OUTPUT:    │  │
│   │ • Análisis     │ │ • PR Draft     │ │ • Código +     │ │ • Código + │  │
│   │ • Tests suger. │ │ • Review req.  │ │   checkpoint   │ │   tests +  │  │
│   │ • Docs         │ │ • Line-by-line │ │ • Peer review  │ │   PR auto  │  │
│   └────────────────┘ └────────────────┘ └────────────────┘ └────────────┘  │
│                                                                              │
└─────────────────────────────────────────────────────────────────────────────┘
```

## Estructura de Archivos

```
agile/skills/
├── README.md                    # Este archivo
├── _base/
│   ├── critico.md               # Template base para skills CRÍTICO
│   ├── alto.md                  # Template base para skills ALTO
│   ├── medio.md                 # Template base para skills MEDIO
│   └── bajo.md                  # Template base para skills BAJO
├── dispatcher.md                # Router agent que distribuye tareas
├── critico/
│   ├── auth-analyst.md          # PT-AUTH-001, PT-AUTH-002
│   ├── staff-analyst.md         # PT-STAFF-001
│   ├── allergen-analyst.md      # PT-ALLERGEN-001
│   └── billing-analyst.md       # PT-BILLING-001, PT-BILLING-002
├── alto/
│   ├── product-dev.md           # PT-PRODUCT-001
│   ├── events-dev.md            # PT-EVENTS-001
│   └── blacklist-dev.md         # PT-BLACKLIST-001
├── medio/
│   ├── kitchen-dev.md           # PT-KITCHEN-001
│   ├── waiter-dev.md            # PT-WAITER-001
│   ├── diner-dev.md             # PT-DINER-001
│   ├── session-dev.md           # PT-TABLES-001
│   └── customer-dev.md          # PT-CUSTOMER-001
└── bajo/
    ├── catalog-dev.md           # PT-CATEGORY-001 (categorías, subcategorías)
    ├── sector-dev.md            # PT-SECTOR-001 (sectores, mesas)
    ├── recipe-dev.md            # PT-RECIPE-001, PT-INGREDIENT-001
    ├── promo-dev.md             # PT-PROMOTION-001
    ├── public-dev.md            # PT-PUBLIC-001
    ├── health-dev.md            # PT-HEALTH-001
    └── audit-dev.md             # PT-AUDIT-001
```

## Uso con Claude Code

### Invocación Manual

```bash
# Cargar skill específico
claude --skill agile/skills/bajo/catalog-dev.md

# O usar el dispatcher
claude --skill agile/skills/dispatcher.md
```

### Invocación Programática (Task tool)

```typescript
// Desde Claude Code, usar Task tool con el skill como contexto
Task({
  prompt: `
    Carga el skill: agile/skills/bajo/catalog-dev.md

    Implementa: HU-CAT-003 (Crear Categoría)

    Sigue las instrucciones del skill para nivel BAJO.
  `,
  subagent_type: "general-purpose"
})
```

### Flujo Recomendado

1. **Usuario pide implementar HU-XXX-NNN**
2. **Dispatcher identifica:**
   - PT asociado (de refactorizacion.md)
   - Nivel de riesgo
   - Skill correspondiente
3. **Dispatcher delega** al skill correcto
4. **Skill ejecuta** según su nivel de autonomía
5. **Output** apropiado al nivel

## Comportamiento por Nivel

### 🔴 CRÍTICO (análisis-solamente)

```yaml
puede:
  - Leer código fuente
  - Analizar patrones
  - Generar documentación
  - Proponer tests (sin ejecutar)
  - Identificar vulnerabilidades
  - Crear diagramas de flujo

no_puede:
  - Modificar archivos
  - Ejecutar código
  - Crear PRs
  - Hacer commits

output:
  - Documento de análisis en markdown
  - Sugerencias de mejora
  - Tests propuestos (texto)
```

### 🟠 ALTO (código-supervisado)

```yaml
puede:
  - Todo lo de CRÍTICO
  - Escribir código propuesto
  - Crear PR en modo draft
  - Generar tests

no_puede:
  - Hacer merge
  - Ejecutar sin aprobación

requiere:
  - Aprobación línea por línea
  - Review de Tech Lead

output:
  - Código propuesto con comentarios
  - PR draft para review
  - Explicación de cada cambio
```

### 🟡 MEDIO (código-con-review)

```yaml
puede:
  - Todo lo de ALTO
  - Implementar features completos
  - Ejecutar tests
  - Crear PR real

requiere:
  - Checkpoint después de cada feature
  - 1 peer review

output:
  - Código implementado
  - Tests ejecutados
  - PR listo para review
  - Solicitud de checkpoint
```

### 🟢 BAJO (código-autónomo)

```yaml
puede:
  - Implementar completo
  - Ejecutar tests
  - Crear PR
  - Auto-merge si CI pasa

restricciones:
  - Solo archivos de su dominio
  - Seguir patrones existentes
  - No tocar dominios superiores

output:
  - Código implementado
  - Tests pasando
  - PR merged (o listo para merge)
```

## Variables de Contexto

Cada skill recibe estas variables:

```yaml
# Contexto del proyecto
PROJECT_ROOT: c:\Users\Admin\Desktop\integrador
CLAUDE_MD: ${PROJECT_ROOT}/CLAUDE.md
HISTORIAS_MD: ${PROJECT_ROOT}/agile/historias/historias_usuario.md
POLITICAS_MD: ${PROJECT_ROOT}/agile/politicas.md

# Contexto del skill
SKILL_LEVEL: BAJO | MEDIO | ALTO | CRÍTICO
POLICY_TICKET: PT-XXX-NNN
ALLOWED_PATHS: [lista de paths permitidos]
FORBIDDEN_PATHS: [lista de paths prohibidos]

# Contexto de la tarea
HU_ID: HU-XXX-NNN
ENDPOINT: /api/xxx/yyy
ROLES: [ADMIN, MANAGER, ...]
```

## Validación de Boundaries

Cada skill valida antes de actuar:

```python
def validate_action(skill_level, target_file):
    # 1. Verificar que el archivo está en ALLOWED_PATHS
    if not is_in_allowed_paths(target_file):
        raise PermissionError(f"Archivo fuera de scope: {target_file}")

    # 2. Verificar que no está en FORBIDDEN_PATHS
    if is_in_forbidden_paths(target_file):
        raise PermissionError(f"Archivo prohibido: {target_file}")

    # 3. Verificar nivel de autonomía permite la acción
    if skill_level == "CRÍTICO" and is_write_action():
        raise PermissionError("CRÍTICO: Solo análisis permitido")
```

## Integración con CI/CD

```yaml
# .github/workflows/agent-pr.yml
name: Agent PR Validation

on:
  pull_request:
    labels: [agent-generated]

jobs:
  validate:
    runs-on: ubuntu-latest
    steps:
      - name: Check skill level
        run: |
          LEVEL=$(grep "skill_level:" .agent-metadata.yml | cut -d: -f2)
          if [ "$LEVEL" == "CRÍTICO" ]; then
            echo "ERROR: CRÍTICO level cannot create PRs"
            exit 1
          fi

      - name: Require reviews based on level
        run: |
          if [ "$LEVEL" == "ALTO" ]; then
            gh pr edit $PR --add-reviewer @tech-lead
          elif [ "$LEVEL" == "MEDIO" ]; then
            gh pr edit $PR --add-reviewer @team
          fi
```

---

*Sistema de Skills para Agentes - Proyecto Integrador*
*Versión 1.0 - Enero 2026*
