# Template Base: Nivel MEDIO (código-con-review)

## Configuración de Autonomía

```yaml
nivel: MEDIO
autonomia: código-con-review
emoji: 🟡

puede:
  - Todo lo de nivel BAJO
  - Implementar features completos
  - Ejecutar tests
  - Crear PRs

requiere:
  - Checkpoint después de cada feature/archivo
  - 1 peer review antes de merge
  - Confirmación del usuario para continuar

no_puede:
  - Auto-merge
  - Continuar sin checkpoint
```

## Instrucciones Generales

### Al Iniciar

1. **Confirma el contexto:**
   ```
   🟡 MODO CON REVIEW - CHECKPOINTS REQUERIDOS
   ─────────────────────────────────
   HU-ID:    {HU_ID}
   PT-ID:    {PT_ID}
   Endpoint: {ENDPOINT}
   ─────────────────────────────────
   Implementaré con pausas para revisión.
   ```

2. **Planifica los checkpoints:**
   ```
   📋 PLAN DE IMPLEMENTACIÓN
   ─────────────────────────────────
   Checkpoint 1: {Descripción}
   Checkpoint 2: {Descripción}
   Checkpoint 3: {Descripción}
   ─────────────────────────────────
   ¿Procedo con Checkpoint 1?
   ```

### Durante la Implementación

1. **Antes de cada checkpoint:**
   ```
   ⏸️ CHECKPOINT {N}: {DESCRIPCIÓN}
   ─────────────────────────────────
   Archivos modificados:
   - {archivo1}
   - {archivo2}

   Cambios realizados:
   - {cambio1}
   - {cambio2}

   Tests:
   - {test1}: ✅
   - {test2}: ✅
   ─────────────────────────────────
   ¿Continúo con el siguiente checkpoint?
   ```

2. **Espera confirmación** antes de continuar.

3. **Si hay rechazo:**
   ```
   🔄 REVISIÓN SOLICITADA
   ─────────────────────────────────
   Feedback: {feedback_del_usuario}

   Acciones:
   - [ ] Corregir {punto1}
   - [ ] Revisar {punto2}
   ─────────────────────────────────
   Aplicando correcciones...
   ```

### Flujo de Checkpoints

```
┌─────────────────────────────────────────────────┐
│                FLUJO CHECKPOINT                  │
├─────────────────────────────────────────────────┤
│                                                  │
│   Implementar Feature                            │
│         │                                        │
│         ▼                                        │
│   ┌─────────────┐                               │
│   │ Checkpoint  │◄────────────────────┐         │
│   │   Pause     │                     │         │
│   └──────┬──────┘                     │         │
│          │                            │         │
│    ┌─────┴─────┐                      │         │
│    ▼           ▼                      │         │
│ Aprobado    Rechazado                 │         │
│    │           │                      │         │
│    │           ▼                      │         │
│    │     Corregir ─────────────────────         │
│    │                                            │
│    ▼                                            │
│ Siguiente Feature                               │
│         │                                        │
│         ▼                                        │
│   ┌─────────────┐                               │
│   │    ...      │                               │
│   └─────────────┘                               │
│         │                                        │
│         ▼                                        │
│   Crear PR (requiere review)                    │
│                                                  │
└─────────────────────────────────────────────────┘
```

### Al Finalizar

1. **Resumen final:**
   ```
   ✅ IMPLEMENTACIÓN COMPLETADA
   ─────────────────────────────────
   HU-ID:       {HU_ID}
   Checkpoints: {N} completados
   Archivos:    {lista}
   Tests:       ✅ {N} pasando
   ─────────────────────────────────

   📝 PR PENDIENTE DE REVIEW
   Requiere aprobación de 1 peer reviewer.
   ```

2. **Crear PR con template:**
   ```markdown
   ## Summary
   - Implementa {HU_ID}: {título}
   - {Bullet points de cambios}

   ## Checkpoints Completados
   - [x] Checkpoint 1: {desc}
   - [x] Checkpoint 2: {desc}

   ## Test plan
   - [ ] Ejecutar tests: `pytest tests/test_{module}.py`
   - [ ] Verificar endpoint: `curl -X POST /api/...`

   ---
   🟡 **Nivel MEDIO** - Requiere 1 peer review

   🤖 Generated with [Claude Code](https://claude.com/claude-code)
   ```

## Validaciones de Checkpoint

```python
def checkpoint(number: int, description: str, files: list, changes: list):
    """
    Pausa la ejecución y solicita confirmación.
    """
    print(f"""
    ⏸️ CHECKPOINT {number}: {description}
    ─────────────────────────────────
    Archivos: {files}
    Cambios:  {changes}
    ─────────────────────────────────
    """)

    # En Claude Code, esto se traduce a preguntar al usuario
    response = ask_user("¿Continúo con el siguiente checkpoint?")

    if response == "no":
        feedback = ask_user("¿Qué debo corregir?")
        apply_corrections(feedback)
        return checkpoint(number, description, files, changes)  # Retry

    return True
```

## Dominios que usan MEDIO

- Kitchen (PT-KITCHEN-001)
- Waiter (PT-WAITER-001)
- Diner (PT-DINER-001)
- Sessions/Tables (PT-TABLES-001)
- Customer Loyalty (PT-CUSTOMER-001)

---

*Template MEDIO - Sistema de Skills*
