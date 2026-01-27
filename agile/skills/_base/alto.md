# Template Base: Nivel ALTO (código-supervisado)

## Configuración de Autonomía

```yaml
nivel: ALTO
autonomia: código-supervisado
emoji: 🟠

puede:
  - Todo lo de nivel CRÍTICO (análisis)
  - Escribir código PROPUESTO
  - Generar tests
  - Crear PR en modo DRAFT

requiere:
  - Aprobación LÍNEA POR LÍNEA antes de aplicar
  - Review de Tech Lead obligatorio
  - Explicación de cada cambio

no_puede:
  - Aplicar cambios sin aprobación
  - Hacer merge
  - Ejecutar código de producción
```

## Instrucciones Generales

### Al Iniciar

1. **Confirma el contexto:**
   ```
   🟠 MODO SUPERVISADO - PROPUESTAS PARA REVISIÓN
   ─────────────────────────────────
   HU-ID:    {HU_ID}
   PT-ID:    {PT_ID}
   Dominio:  {DOMINIO}
   ─────────────────────────────────
   Generaré código PROPUESTO.
   Cada cambio requiere tu aprobación.
   ```

2. **Presenta plan de cambios:**
   ```
   📋 CAMBIOS PROPUESTOS
   ─────────────────────────────────
   1. Archivo: {path1}
      Acción:  {modificar/crear}
      Líneas:  {rango}

   2. Archivo: {path2}
      Acción:  {modificar/crear}
      Líneas:  {rango}
   ─────────────────────────────────
   ¿Procedo a mostrar el código propuesto?
   ```

### Durante la Propuesta

1. **Para cada archivo, muestra diff propuesto:**
   ```
   📄 PROPUESTA: {filepath}
   ─────────────────────────────────

   ```diff
   - código_actual_línea_1
   - código_actual_línea_2
   + código_propuesto_línea_1
   + código_propuesto_línea_2
   ```

   💡 JUSTIFICACIÓN:
   {Explicación de por qué este cambio}

   ─────────────────────────────────
   ¿Apruebas este cambio? (sí/no/modificar)
   ```

2. **Si el usuario dice "modificar":**
   ```
   🔄 MODIFICACIÓN SOLICITADA
   ─────────────────────────────────
   Feedback: {feedback_del_usuario}

   Nueva propuesta:
   ```diff
   + código_modificado
   ```

   ¿Apruebas esta versión?
   ```

3. **Tracking de aprobaciones:**
   ```
   📊 ESTADO DE PROPUESTAS
   ─────────────────────────────────
   [✅] archivo1.py - Aprobado
   [✅] archivo2.py - Aprobado
   [⏳] archivo3.py - Pendiente
   [❌] archivo4.py - Rechazado
   ─────────────────────────────────
   ```

### Flujo de Aprobación Línea por Línea

```
┌─────────────────────────────────────────────────┐
│           FLUJO SUPERVISADO (ALTO)               │
├─────────────────────────────────────────────────┤
│                                                  │
│   Analizar Requisito                             │
│         │                                        │
│         ▼                                        │
│   Generar Propuesta                              │
│         │                                        │
│         ▼                                        │
│   ┌─────────────────────────────────┐           │
│   │  Para cada archivo:             │           │
│   │                                 │           │
│   │    Mostrar diff propuesto       │           │
│   │           │                     │           │
│   │           ▼                     │           │
│   │    ┌──────────────┐             │           │
│   │    │ ¿Aprobado?   │             │           │
│   │    └──────┬───────┘             │           │
│   │     │     │     │               │           │
│   │    Sí    No  Modificar          │           │
│   │     │     │     │               │           │
│   │     │     │     ▼               │           │
│   │     │     │  Ajustar ───────────│───┐       │
│   │     │     │                     │   │       │
│   │     │     ▼                     │   │       │
│   │     │  Descartar cambio         │   │       │
│   │     │                           │   │       │
│   │     ▼                           │   │       │
│   │  Guardar aprobación ◄───────────────┘       │
│   │                                 │           │
│   └─────────────────────────────────┘           │
│         │                                        │
│         ▼                                        │
│   Aplicar SOLO cambios aprobados                │
│         │                                        │
│         ▼                                        │
│   Crear PR DRAFT                                │
│         │                                        │
│         ▼                                        │
│   Solicitar review Tech Lead                    │
│                                                  │
└─────────────────────────────────────────────────┘
```

### Al Finalizar

1. **Resumen de cambios aprobados:**
   ```
   ✅ PROPUESTA FINALIZADA
   ─────────────────────────────────
   HU-ID:    {HU_ID}

   Cambios aprobados: {N}
   Cambios rechazados: {M}

   Archivos a modificar:
   - {archivo1}: {descripción}
   - {archivo2}: {descripción}
   ─────────────────────────────────

   ¿Aplico los cambios aprobados?
   ```

2. **Si se aprueban, crear PR draft:**
   ```markdown
   ## Summary
   - Propuesta para {HU_ID}: {título}
   - Cambios revisados línea por línea

   ## Cambios Aprobados
   | Archivo | Acción | Revisión |
   |---------|--------|----------|
   | {path1} | {acción} | ✅ Aprobado por usuario |
   | {path2} | {acción} | ✅ Aprobado por usuario |

   ## Pendiente
   - [ ] Review de Tech Lead

   ---
   🟠 **Nivel ALTO** - PR Draft para revisión
   ⚠️ NO hacer merge sin aprobación de Tech Lead

   🤖 Generated with [Claude Code](https://claude.com/claude-code)
   ```

## Template de Diff Propuesto

```
📄 ARCHIVO: {filepath}
📍 UBICACIÓN: líneas {start}-{end}
🎯 OBJETIVO: {objetivo_del_cambio}

┌─ CÓDIGO ACTUAL ────────────────────────────────
│ {línea_actual_1}
│ {línea_actual_2}
│ {línea_actual_3}
└────────────────────────────────────────────────

┌─ CÓDIGO PROPUESTO ─────────────────────────────
│ {línea_propuesta_1}
│ {línea_propuesta_2}
│ {línea_propuesta_3}
└────────────────────────────────────────────────

💡 JUSTIFICACIÓN:
{Por qué este cambio es necesario}
{Qué problema resuelve}
{Cómo se alinea con la arquitectura}

🔒 IMPACTO EN SEGURIDAD:
{Ninguno / Descripción del impacto}

⏳ ¿Apruebas este cambio?
   [Sí] [No] [Modificar]
```

## Dominios que usan ALTO

- Products (PT-PRODUCT-001)
- WebSocket Events (PT-EVENTS-001)
- Token Blacklist (PT-BLACKLIST-001)

---

*Template ALTO - Sistema de Skills*
