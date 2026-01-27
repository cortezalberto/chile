# Guía de Operaciones Multi-Agente con Skills

## Introducción

Este documento explica cómo Claude Code puede orquestar múltiples agentes especializados para implementar features complejos que cruzan varios dominios.

---

## Arquitectura Multi-Agente

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                      ORQUESTACIÓN MULTI-AGENTE                               │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                              │
│   Usuario: "Implementar feature X que toca auth, products y kitchen"        │
│                           │                                                  │
│                           ▼                                                  │
│   ┌───────────────────────────────────────────┐                             │
│   │           ORCHESTRATOR (Claude)            │                             │
│   │  - Analiza el request                      │                             │
│   │  - Descompone en tareas                    │                             │
│   │  - Identifica skills necesarios            │                             │
│   │  - Determina orden de ejecución            │                             │
│   │  - Coordina resultados                     │                             │
│   └───────────────────────────────────────────┘                             │
│          │              │              │                                     │
│          │              │              │                                     │
│          ▼              ▼              ▼                                     │
│   ┌───────────┐  ┌───────────┐  ┌───────────┐                              │
│   │  Agent 1  │  │  Agent 2  │  │  Agent 3  │                              │
│   │  CRÍTICO  │  │   ALTO    │  │   MEDIO   │                              │
│   │  (auth)   │  │ (product) │  │ (kitchen) │                              │
│   └─────┬─────┘  └─────┬─────┘  └─────┬─────┘                              │
│         │              │              │                                     │
│         ▼              ▼              ▼                                     │
│   ┌───────────┐  ┌───────────┐  ┌───────────┐                              │
│   │  Output:  │  │  Output:  │  │  Output:  │                              │
│   │  Análisis │  │  Propuesta│  │  Código + │                              │
│   │  + Docs   │  │  Review   │  │  Tests    │                              │
│   └───────────┘  └───────────┘  └───────────┘                              │
│         │              │              │                                     │
│         └──────────────┴──────────────┘                                     │
│                        │                                                     │
│                        ▼                                                     │
│   ┌───────────────────────────────────────────┐                             │
│   │           ORCHESTRATOR (Claude)            │                             │
│   │  - Consolida resultados                    │                             │
│   │  - Verifica consistencia                   │                             │
│   │  - Presenta resumen al usuario             │                             │
│   └───────────────────────────────────────────┘                             │
│                                                                              │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## Patrones de Coordinación

### Patrón 1: Secuencial (Pipeline)

Cuando los agentes dependen del output del anterior.

```
┌─────────┐     ┌─────────┐     ┌─────────┐
│ Agent A │────►│ Agent B │────►│ Agent C │
│ (input) │     │(A→input)│     │(B→input)│
└─────────┘     └─────────┘     └─────────┘
```

**Ejemplo:** Implementar endpoint que requiere nuevo modelo
1. `catalog-dev` → Crea modelo en DB
2. `product-dev` → Crea servicio que usa el modelo
3. `kitchen-dev` → Integra con flujo de cocina

**Implementación con Task tool:**

```typescript
// Paso 1: Crear modelo (BAJO - autónomo)
const modelResult = await Task({
  prompt: `
    Skill: agile/skills/bajo/catalog-dev.md
    Tarea: Crear modelo SpecialOrder en models/order.py

    Genera el modelo SQLAlchemy siguiendo patrones de CLAUDE.md.
    Retorna el código generado.
  `,
  subagent_type: "general-purpose",
  description: "Create data model"
});

// Paso 2: Crear servicio (ALTO - supervisado)
// Solo si paso 1 fue exitoso
const serviceResult = await Task({
  prompt: `
    Skill: agile/skills/alto/product-dev.md
    Contexto: Se creó el modelo SpecialOrder: ${modelResult}
    Tarea: Crear SpecialOrderService que use este modelo

    IMPORTANTE: Nivel ALTO - Proponer código para revisión.
  `,
  subagent_type: "general-purpose",
  description: "Propose service code"
});

// Paso 3: Integrar (MEDIO - con review)
const integrationResult = await Task({
  prompt: `
    Skill: agile/skills/medio/kitchen-dev.md
    Contexto:
    - Modelo: ${modelResult}
    - Servicio: ${serviceResult}
    Tarea: Integrar SpecialOrder en flujo de tickets de cocina

    IMPORTANTE: Nivel MEDIO - Checkpoints requeridos.
  `,
  subagent_type: "general-purpose",
  description: "Integrate with kitchen"
});
```

---

### Patrón 2: Paralelo (Fan-out/Fan-in)

Cuando los agentes pueden trabajar independientemente.

```
              ┌─────────┐
         ┌───►│ Agent A │───┐
         │    └─────────┘   │
┌────────┤    ┌─────────┐   ├────────┐
│Dispatch│───►│ Agent B │───►│Collect │
└────────┤    └─────────┘   ├────────┘
         │    ┌─────────┐   │
         └───►│ Agent C │───┘
              └─────────┘
```

**Ejemplo:** Actualizar documentación en múltiples módulos
1. `catalog-dev` → Documenta categorías (paralelo)
2. `kitchen-dev` → Documenta cocina (paralelo)
3. `waiter-dev` → Documenta meseros (paralelo)

**Implementación con Task tool (paralelo):**

```typescript
// IMPORTANTE: Enviar múltiples Task en UN SOLO mensaje para ejecución paralela

// Todos en paralelo (mismo mensaje, múltiples tool calls)
const [catalogDocs, kitchenDocs, waiterDocs] = await Promise.all([
  Task({
    prompt: `
      Skill: agile/skills/bajo/catalog-dev.md
      Tarea: Generar documentación de endpoints de categorías
    `,
    subagent_type: "general-purpose",
    description: "Document catalog",
    run_in_background: true  // Ejecutar en background
  }),

  Task({
    prompt: `
      Skill: agile/skills/medio/kitchen-dev.md
      Tarea: Generar documentación de endpoints de cocina
    `,
    subagent_type: "general-purpose",
    description: "Document kitchen",
    run_in_background: true
  }),

  Task({
    prompt: `
      Skill: agile/skills/medio/waiter-dev.md
      Tarea: Generar documentación de endpoints de mesero
    `,
    subagent_type: "general-purpose",
    description: "Document waiter",
    run_in_background: true
  })
]);

// Consolidar resultados
const finalDocs = consolidate(catalogDocs, kitchenDocs, waiterDocs);
```

---

### Patrón 3: Jerárquico (Supervisor)

Un agente supervisor coordina agentes especializados.

```
              ┌─────────────────┐
              │   SUPERVISOR    │
              │  (Orchestrator) │
              └────────┬────────┘
                       │
        ┌──────────────┼──────────────┐
        │              │              │
        ▼              ▼              ▼
   ┌─────────┐   ┌─────────┐   ┌─────────┐
   │ Worker  │   │ Worker  │   │ Worker  │
   │  BAJO   │   │  MEDIO  │   │  ALTO   │
   └─────────┘   └─────────┘   └─────────┘
```

**Implementación:**

```typescript
// Supervisor Agent
const supervisorPrompt = `
Eres el SUPERVISOR de una tarea multi-agente.

TAREA PRINCIPAL: ${userRequest}

Tu trabajo es:
1. Descomponer la tarea en subtareas
2. Identificar el skill apropiado para cada subtarea
3. Determinar el orden (secuencial vs paralelo)
4. Invocar agentes workers
5. Consolidar resultados
6. Manejar errores y reintentos

SKILLS DISPONIBLES:
- agile/skills/bajo/catalog-dev.md (BAJO - autónomo)
- agile/skills/bajo/sector-dev.md (BAJO - autónomo)
- agile/skills/medio/kitchen-dev.md (MEDIO - checkpoints)
- agile/skills/medio/waiter-dev.md (MEDIO - checkpoints)
- agile/skills/alto/product-dev.md (ALTO - supervisado)
- agile/skills/critico/auth-analyst.md (CRÍTICO - solo análisis)

REGLAS:
- Respeta el nivel de autonomía de cada skill
- Si un worker CRÍTICO encuentra problemas, DETENTE y reporta
- Si un worker ALTO propone cambios, solicita aprobación
- Para workers MEDIO, implementa checkpoints
- Solo workers BAJO pueden auto-completar

Comienza analizando la tarea y creando el plan de ejecución.
`;

await Task({
  prompt: supervisorPrompt,
  subagent_type: "general-purpose",
  description: "Supervisor orchestration"
});
```

---

### Patrón 4: Revisión Cruzada

Un agente revisa el trabajo de otro.

```
┌─────────┐     ┌─────────┐
│Developer│────►│Reviewer │
│ Agent   │◄────│ Agent   │
└─────────┘     └─────────┘
```

**Ejemplo:** Desarrollo con revisión de seguridad

```typescript
// Paso 1: Developer implementa
const code = await Task({
  prompt: `
    Skill: agile/skills/medio/diner-dev.md
    Tarea: Implementar endpoint de preferencias del diner
  `,
  subagent_type: "general-purpose",
  description: "Implement feature"
});

// Paso 2: Security analyst revisa
const securityReview = await Task({
  prompt: `
    Skill: agile/skills/critico/auth-analyst.md
    Tarea: Revisar el siguiente código por vulnerabilidades:

    ${code}

    IMPORTANTE: Solo análisis, no modificar.
    Reportar hallazgos de seguridad.
  `,
  subagent_type: "general-purpose",
  description: "Security review"
});

// Paso 3: Si hay issues, developer corrige
if (securityReview.hasIssues) {
  const fixedCode = await Task({
    prompt: `
      Skill: agile/skills/medio/diner-dev.md
      Contexto: Security review encontró estos issues:
      ${securityReview.issues}

      Tarea: Corregir los issues de seguridad
    `,
    subagent_type: "general-purpose",
    description: "Fix security issues"
  });
}
```

---

## Ejemplo Completo: Implementar Feature Multi-Dominio

### Escenario

> "Quiero agregar un sistema de alertas para alérgenos que notifique a cocina cuando un diner con alergias hace un pedido"

### Análisis del Orchestrator

```yaml
Feature: Sistema de Alertas de Alérgenos
Dominios involucrados:
  - Allergens (CRÍTICO) - Solo análisis, no modificar datos
  - Diner (MEDIO) - Capturar preferencias de alérgenos
  - Kitchen (MEDIO) - Mostrar alertas en tickets
  - WebSocket Events (ALTO) - Nuevo evento ALLERGEN_ALERT

Plan de ejecución:
  1. [CRÍTICO] Analizar sistema actual de alérgenos
  2. [MEDIO] Implementar captura de alérgenos en diner (parallel)
  3. [ALTO] Proponer nuevo evento WebSocket (parallel)
  4. [MEDIO] Implementar alertas en kitchen tickets (depends on 2,3)
  5. [BAJO] Actualizar documentación
```

### Implementación Paso a Paso

```typescript
// ============================================================
// PASO 1: Análisis de alérgenos (CRÍTICO - solo lectura)
// ============================================================
const allergenAnalysis = await Task({
  prompt: `
    # Skill: agile/skills/critico/allergen-analyst.md

    ## Tarea
    Analizar el sistema actual de alérgenos para entender:
    1. Estructura de datos de ProductAllergen
    2. Cómo se almacenan cross-reactions
    3. Cómo se relacionan con RoundItems

    ## Output esperado
    - Diagrama de relaciones
    - Lista de campos relevantes
    - Consideraciones para alertas

    ⚠️ MODO CRÍTICO: Solo análisis, NO modificar código.
  `,
  subagent_type: "general-purpose",
  description: "Analyze allergen system"
});

console.log("📊 Análisis completado:", allergenAnalysis);

// ============================================================
// PASO 2 y 3: En paralelo (diferentes dominios, sin dependencias)
// ============================================================

// 2A: Diner preferences (MEDIO)
const dinerTask = Task({
  prompt: `
    # Skill: agile/skills/medio/diner-dev.md

    ## Contexto
    ${allergenAnalysis}

    ## Tarea
    Implementar endpoint para que diner guarde sus alérgenos:
    PATCH /api/diner/allergens

    ## Checkpoints
    1. Endpoint implementado
    2. Validación de allergen_ids
    3. Tests

    Solicitar aprobación en cada checkpoint.
  `,
  subagent_type: "general-purpose",
  description: "Implement diner allergens",
  run_in_background: true
});

// 3A: WebSocket event (ALTO - supervisado)
const wsEventTask = Task({
  prompt: `
    # Skill: agile/skills/alto/events-dev.md

    ## Tarea
    Proponer nuevo evento WebSocket: ALLERGEN_ALERT

    ## Especificación
    - Canal: branch_kitchen
    - Payload: { round_id, table_id, allergens: [...] }
    - Trigger: Cuando round contiene items con alérgenos del diner

    ## IMPORTANTE
    Nivel ALTO: Mostrar código propuesto para revisión línea por línea.
    NO implementar hasta aprobación.
  `,
  subagent_type: "general-purpose",
  description: "Propose WS event",
  run_in_background: true
});

// Esperar ambos
const [dinerResult, wsEventResult] = await Promise.all([
  TaskOutput({ task_id: dinerTask.id }),
  TaskOutput({ task_id: wsEventTask.id })
]);

// ============================================================
// PASO 4: Kitchen integration (MEDIO - depende de 2 y 3)
// ============================================================
const kitchenResult = await Task({
  prompt: `
    # Skill: agile/skills/medio/kitchen-dev.md

    ## Contexto previo
    - Diner allergens: ${dinerResult}
    - WS Event: ${wsEventResult}

    ## Tarea
    Integrar alertas de alérgenos en tickets de cocina:
    1. Al crear KitchenTicket, verificar alérgenos del diner
    2. Si hay match, agregar flag y publicar ALLERGEN_ALERT
    3. Mostrar alerta visual en endpoint GET /api/kitchen/tickets

    ## Checkpoints
    1. Lógica de detección
    2. Publicación de evento
    3. Response con alertas
    4. Tests
  `,
  subagent_type: "general-purpose",
  description: "Kitchen allergen alerts"
});

// ============================================================
// PASO 5: Documentación (BAJO - autónomo)
// ============================================================
const docsResult = await Task({
  prompt: `
    # Skill: agile/skills/bajo/catalog-dev.md

    ## Tarea
    Actualizar documentación con el nuevo feature:
    1. Agregar sección en CLAUDE.md sobre alertas de alérgenos
    2. Documentar nuevo evento ALLERGEN_ALERT
    3. Actualizar diagrama de flujo

    Nivel BAJO: Implementar y commit automático.
  `,
  subagent_type: "general-purpose",
  description: "Update documentation"
});

// ============================================================
// CONSOLIDACIÓN FINAL
// ============================================================
console.log(`
✅ FEATURE COMPLETADO: Sistema de Alertas de Alérgenos
─────────────────────────────────────────────────────────

📊 Análisis (CRÍTICO):
${allergenAnalysis.summary}

👤 Diner Preferences (MEDIO):
${dinerResult.summary}
Status: ${dinerResult.status}

📡 WebSocket Event (ALTO):
${wsEventResult.summary}
Status: ${wsEventResult.status}
⚠️ Requiere aprobación de Tech Lead

🍳 Kitchen Integration (MEDIO):
${kitchenResult.summary}
Status: ${kitchenResult.status}

📚 Documentación (BAJO):
${docsResult.summary}
Status: ✅ Auto-merged

─────────────────────────────────────────────────────────
Próximos pasos:
1. Aprobar propuesta de WS Event (ALTO)
2. Merge de PRs pendientes
3. Testing E2E
`);
```

---

## Manejo de Errores en Multi-Agente

### Estrategia de Rollback

```typescript
const completedTasks: string[] = [];

try {
  // Paso 1
  const result1 = await Task({ ... });
  completedTasks.push("step1");

  // Paso 2
  const result2 = await Task({ ... });
  completedTasks.push("step2");

  // Paso 3
  const result3 = await Task({ ... });
  completedTasks.push("step3");

} catch (error) {
  console.error("Error en multi-agente:", error);

  // Rollback de pasos completados
  for (const task of completedTasks.reverse()) {
    await Task({
      prompt: `
        Rollback del paso: ${task}
        Revertir cambios realizados.
      `,
      subagent_type: "general-purpose"
    });
  }
}
```

### Reintentos con Backoff

```typescript
async function executeWithRetry(taskConfig, maxRetries = 3) {
  for (let attempt = 1; attempt <= maxRetries; attempt++) {
    try {
      return await Task(taskConfig);
    } catch (error) {
      if (attempt === maxRetries) throw error;

      const delay = Math.pow(2, attempt) * 1000; // Exponential backoff
      console.log(`Reintento ${attempt}/${maxRetries} en ${delay}ms...`);
      await sleep(delay);
    }
  }
}
```

---

## Comunicación Entre Agentes

### Pasar Contexto

```typescript
// Agent 1 produce contexto
const agent1Result = await Task({
  prompt: "Analizar estructura de datos...",
  subagent_type: "general-purpose"
});

// Agent 2 recibe contexto
const agent2Result = await Task({
  prompt: `
    ## Contexto del Agent 1
    ${agent1Result}

    ## Tu tarea
    Basándote en el análisis anterior, implementar...
  `,
  subagent_type: "general-purpose"
});
```

### Formato de Contexto Estructurado

```typescript
interface AgentContext {
  taskId: string;
  skill: string;
  level: "CRÍTICO" | "ALTO" | "MEDIO" | "BAJO";
  input: any;
  output: any;
  status: "success" | "pending_review" | "failed";
  artifacts: {
    files?: string[];
    code?: string;
    analysis?: string;
    tests?: string;
  };
}

// Pasar contexto estructurado
const context: AgentContext = {
  taskId: "task-001",
  skill: "catalog-dev",
  level: "BAJO",
  input: { hu_id: "HU-CAT-003" },
  output: { ... },
  status: "success",
  artifacts: {
    files: ["categories.py", "test_categories.py"],
    code: "..."
  }
};

await Task({
  prompt: `
    ## Contexto Previo
    \`\`\`json
    ${JSON.stringify(context, null, 2)}
    \`\`\`

    ## Tu tarea
    ...
  `,
  subagent_type: "general-purpose"
});
```

---

## Comandos Útiles para Multi-Agente

### En Claude Code CLI

```bash
# Ver tareas en background
/tasks

# Ver output de tarea específica
/task-output <task_id>

# Cancelar tarea
/task-stop <task_id>
```

### Monitoreo de Progreso

```typescript
// Ejecutar en background y monitorear
const taskId = await Task({
  prompt: "...",
  run_in_background: true
}).id;

// Polling de status
while (true) {
  const output = await TaskOutput({
    task_id: taskId,
    block: false,
    timeout: 1000
  });

  if (output.status === "completed") {
    console.log("✅ Completado:", output.result);
    break;
  }

  console.log("⏳ En progreso...");
  await sleep(5000);
}
```

---

## Mejores Prácticas

### 1. Respetar Niveles de Autonomía

```typescript
// ❌ MAL: Ignorar nivel del skill
await Task({
  prompt: "Implementa cambios en auth (usa auth-analyst skill)"
  // auth-analyst es CRÍTICO, no puede implementar!
});

// ✅ BIEN: Respetar autonomía
await Task({
  prompt: `
    Skill: auth-analyst (CRÍTICO)
    Solo analiza, no implementes.
    Si se necesitan cambios, reporta para asignar a humano.
  `
});
```

### 2. Validar Dependencias

```typescript
// Verificar que paso anterior fue exitoso antes de continuar
if (previousResult.status !== "success") {
  throw new Error(`Dependencia fallida: ${previousResult.error}`);
}
```

### 3. Checkpoints en Operaciones Largas

```typescript
// Para operaciones multi-paso, confirmar con usuario
const shouldContinue = await AskUserQuestion({
  questions: [{
    question: "¿Continúo con el siguiente paso?",
    header: "Checkpoint",
    options: [
      { label: "Sí, continuar", description: "Proceder al siguiente paso" },
      { label: "No, pausar", description: "Detener y revisar" }
    ]
  }]
});
```

### 4. Logging Estructurado

```typescript
function logAgentAction(agent: string, action: string, details: any) {
  console.log(JSON.stringify({
    timestamp: new Date().toISOString(),
    agent,
    action,
    details
  }));
}

logAgentAction("catalog-dev", "start", { hu_id: "HU-CAT-003" });
logAgentAction("catalog-dev", "complete", { files: [...], tests: "passed" });
```

---

## Resumen de Patrones

| Patrón | Cuándo Usar | Ejemplo |
|--------|-------------|---------|
| **Secuencial** | Dependencias entre tareas | Modelo → Servicio → Router |
| **Paralelo** | Tareas independientes | Documentar múltiples módulos |
| **Jerárquico** | Coordinación compleja | Feature multi-dominio |
| **Revisión Cruzada** | Calidad/Seguridad | Dev → Security Review |

---

*Guía Multi-Agente - Sistema de Skills*
*Versión 1.0 - Enero 2026*
