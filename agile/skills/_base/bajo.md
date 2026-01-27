# Template Base: Nivel BAJO (código-autónomo)

## Configuración de Autonomía

```yaml
nivel: BAJO
autonomia: código-autónomo
emoji: 🟢

puede:
  - Leer archivos de código
  - Crear archivos nuevos
  - Modificar archivos existentes
  - Ejecutar tests
  - Crear commits
  - Crear PRs
  - Auto-merge si CI pasa

restricciones:
  - Solo archivos dentro del dominio permitido
  - Seguir patrones existentes en CLAUDE.md
  - No tocar archivos de dominios superiores
  - No modificar configuración de seguridad
```

## Instrucciones Generales

### Al Iniciar

1. **Confirma el contexto:**
   ```
   🟢 MODO AUTÓNOMO - IMPLEMENTACIÓN COMPLETA
   ─────────────────────────────────
   HU-ID:    {HU_ID}
   PT-ID:    {PT_ID}
   Endpoint: {ENDPOINT}
   ─────────────────────────────────
   Procederé a implementar completamente.
   ```

2. **Lee la especificación completa:**
   - `agile/historias/historias_usuario.md` → Busca sección del HU-ID
   - `CLAUDE.md` → Patrones y convenciones
   - Código existente similar → Patrones a seguir

### Durante la Implementación

1. **Sigue el flujo estándar:**
   ```
   1. Leer especificación técnica
   2. Identificar archivos a modificar/crear
   3. Implementar siguiendo patrones existentes
   4. Crear/actualizar tests
   5. Ejecutar tests localmente
   6. Crear commit con mensaje descriptivo
   ```

2. **Patrones a seguir (de CLAUDE.md):**

   **Router (thin controller):**
   ```python
   @router.post("", response_model=OutputSchema)
   def create_entity(
       body: CreateSchema,
       db: Session = Depends(get_db),
       user: dict = Depends(current_user),
   ):
       ctx = PermissionContext(user)
       service = EntityService(db)
       return service.create(
           ctx.tenant_id,
           body,
           ctx.user_id,
           user.get("email", ""),
       )
   ```

   **Service (business logic):**
   ```python
   class EntityService(BranchScopedService[Entity, EntityOutput]):
       def __init__(self, db: Session):
           super().__init__(
               db=db,
               model=Entity,
               output_schema=EntityOutput,
               entity_name="Entidad",
           )
   ```

   **Test pattern:**
   ```python
   def test_create_entity_success(client, auth_headers, db):
       # Arrange
       payload = {"name": "Test"}

       # Act
       response = client.post("/api/admin/entities", json=payload, headers=auth_headers)

       # Assert
       assert response.status_code == 200
       data = response.json()
       assert data["name"] == "Test"
   ```

### Al Finalizar

1. **Ejecuta validaciones:**
   ```bash
   # Tests
   cd backend && python -m pytest tests/test_{module}.py -v

   # Type check (si frontend)
   npx tsc --noEmit
   ```

2. **Crea commit:**
   ```bash
   git add {archivos_modificados}
   git commit -m "$(cat <<'EOF'
   feat({dominio}): {descripción breve}

   - Implementa {HU_ID}: {título}
   - Agrega tests para {funcionalidad}

   Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>
   EOF
   )"
   ```

3. **Reporta resultado:**
   ```
   ✅ IMPLEMENTACIÓN COMPLETADA
   ─────────────────────────────────
   HU-ID:      {HU_ID}
   Archivos:   {lista}
   Tests:      ✅ {N} pasando
   Commit:     {hash}
   ─────────────────────────────────

   Listo para PR / merge.
   ```

## Validaciones Obligatorias

```python
# Verificar que solo tocamos archivos permitidos
ALLOWED_PATHS = [
    "backend/rest_api/routers/admin/categories.py",
    "backend/rest_api/routers/admin/subcategories.py",
    "backend/rest_api/services/domain/category_service.py",
    "backend/rest_api/services/domain/subcategory_service.py",
    "backend/rest_api/models/catalog.py",
    "backend/tests/test_categories.py",
    # ... paths del dominio
]

FORBIDDEN_PATHS = [
    "backend/shared/security/*",
    "backend/rest_api/routers/auth/*",
    "backend/rest_api/routers/billing/*",
    ".env*",
    "**/secrets*",
]

def validate_file_access(filepath):
    if any(fnmatch(filepath, pattern) for pattern in FORBIDDEN_PATHS):
        raise PermissionError(f"Archivo prohibido: {filepath}")
    if not any(fnmatch(filepath, pattern) for pattern in ALLOWED_PATHS):
        raise PermissionError(f"Archivo fuera de scope: {filepath}")
```

## Checklist Pre-Commit

- [ ] Código sigue patrones de CLAUDE.md
- [ ] Tests escritos y pasando
- [ ] No hay console.log / print de debug
- [ ] No hay secrets hardcodeados
- [ ] Type hints (Python) / Types (TypeScript)
- [ ] Imports organizados
- [ ] No hay archivos fuera del dominio modificados

## Template de Commit

```
feat({dominio}): {acción} {entidad}

- Implementa {HU_ID}: {título}
- {Detalle 1}
- {Detalle 2}

Refs: PT-{XXX}-{NNN}

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>
```

---

*Template BAJO - Sistema de Skills*
