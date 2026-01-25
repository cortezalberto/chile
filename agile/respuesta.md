# Análisis de Aplicabilidad del Marco IA-Native al Proyecto Integrador

**Documento de Evaluación Técnica**
**Fecha:** 25 de Enero de 2026
**Analista:** Claude (como líder de proyecto)

---

## Resumen Ejecutivo

Tras un análisis exhaustivo del marco de trabajo IA-Native descrito en `activia.md` y su potencial aplicación al proyecto **Integrador** (sistema de gestión de restaurantes), concluyo que **el framework es altamente aplicable y recomendable para este proyecto**, con algunas adaptaciones específicas que detallaré a continuación.

La compatibilidad es natural dado que:
1. El proyecto Integrador ya implementa una arquitectura modular y bien documentada
2. Existe clara separación de dominios con diferentes niveles de riesgo
3. La infraestructura actual (Policy Tickets → CLAUDE.md, PRs → GitHub) es directamente mapeable
4. El equipo ya trabaja con agentes de IA (Claude Code) en el desarrollo

---

## 1. Análisis de Compatibilidad Estructural

### 1.1 Mapeo de Componentes del Proyecto a Dominios de Riesgo

Aplicando la **Matriz de Overhead por Nivel de Riesgo** del framework al proyecto Integrador:

| Componente | Nivel de Riesgo | Justificación |
|------------|-----------------|---------------|
| **pwaMenu** (UI cliente) | **Bajo-Medio** | Afecta UX pero no datos críticos; errores son visibles |
| **Dashboard** (Admin) | **Medio** | Gestión de datos, pero con validaciones en backend |
| **pwaWaiter** (PWA mesero) | **Medio** | Operaciones en tiempo real, impacto en servicio |
| **REST API - Catálogo** | **Medio** | CRUD de productos, categorías, ingredientes |
| **REST API - Autenticación** | **Alto** | JWT, tokens, blacklist - seguridad crítica |
| **REST API - Pagos/Billing** | **Crítico** | Mercado Pago, transacciones financieras |
| **REST API - Datos de alérgenos** | **Alto** | Impacto directo en salud del usuario |
| **WebSocket Gateway** | **Alto** | Comunicación real-time, multi-tenant |
| **Shared Security** | **Crítico** | Auth, password hashing, rate limiting |

### 1.2 Compatibilidad con Arquitectura Existente

El proyecto Integrador ya implementa patrones que **alinean naturalmente** con el marco IA-Native:

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                    ALINEACIÓN ARQUITECTÓNICA                                 │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│  INTEGRADOR (actual)              →    MARCO IA-NATIVE                      │
│  ─────────────────────────────────     ────────────────────────────         │
│                                                                             │
│  CLAUDE.md (instrucciones)        →    Policy Tickets (gobernanza)          │
│  arqui*.md (arquitectura)         →    Documentación por capas              │
│  Clean Architecture (4 capas)     →    Separación de responsabilidades      │
│  Permission Strategy Pattern      →    Niveles de autonomía                 │
│  AuditMixin (soft delete)         →    Trazabilidad completa                │
│  Domain Services                  →    Límites cognitivos definidos         │
│  Roles (ADMIN/MANAGER/KITCHEN)    →    Responsabilidad inalienable          │
│  Tests (Vitest, pytest)           →    Evidencia sobre confianza            │
│  GitHub PRs + CI/CD               →    Control preventivo                   │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## 2. Propuesta de Implementación por Componente

### 2.1 Dashboard (React 19 + Zustand)

**Nivel de Riesgo:** Medio
**Autonomía IA Recomendada:** Con checkpoints

**Dominios de bajo riesgo (IA completa):**
- Componentes de UI/presentación
- Estilos CSS/TailwindCSS
- Tests unitarios de stores
- Documentación de componentes

**Dominios de riesgo medio (IA con revisión):**
- Lógica de stores Zustand
- Integración con API client
- Manejo de WebSocket events
- TableSessionModal y lógica de órdenes

**Dominios de riesgo alto (IA supervisada):**
- Gestión de roles y permisos
- Manejo de tokens JWT
- Lógica de soft delete

**Policy Ticket Ejemplo - Dashboard:**
```yaml
PT-ID: PT-DASH-2026-001
Dominio: dashboard/stores
Riesgo: medio
Intención: Refactorizar branchStore para implementar paginación virtual
Alcance-Permitido:
  - Modificar Dashboard/src/stores/branchStore.ts
  - Crear tests en Dashboard/src/stores/branchStore.test.ts
  - Actualizar tipos en Dashboard/src/types/
Alcance-Prohibido:
  - Modificar authStore.ts (autenticación)
  - Cambiar API endpoints
  - Tocar lógica de permisos
Autonomía: con-revisión
Evidencia-Requerida:
  - Tests pasan (npm test)
  - Patrón Zustand correcto (selectores, no destructuring)
  - Type check pasa (npx tsc --noEmit)
```

### 2.2 pwaMenu (PWA Cliente)

**Nivel de Riesgo:** Bajo-Medio
**Autonomía IA Recomendada:** Completa para UI, supervisada para filtros críticos

**Dominios de bajo riesgo (IA completa):**
- Componentes de presentación de menú
- Internacionalización (i18n)
- Service Worker y PWA config
- Cart UI components
- Estilos y animaciones

**Dominios de riesgo medio (IA con checkpoints):**
- Lógica de collaborative ordering
- Round confirmation flow
- WebSocket integration
- Customer loyalty hooks

**Dominios de riesgo alto (IA supervisada):**
- **useAllergenFilter** - Impacto directo en salud
- **useDietaryFilter** - Restricciones alimentarias
- Cross-reactions de alérgenos
- Implicit preferences sync

**Policy Ticket Ejemplo - pwaMenu Alérgenos:**
```yaml
PT-ID: PT-MENU-2026-042
Dominio: pwamenu/filters/allergens
Riesgo: ALTO
Responsable: @product.owner
Intención: Mejorar visualización de advertencias de alérgenos
Alcance-Permitido:
  - Crear componentes en pwaMenu/src/components/allergens/
  - Modificar estilos de advertencias
  - Agregar tests de visualización
Alcance-Explícitamente-Prohibido:
  - Modificar lógica de useAllergenFilter.ts
  - Cambiar datos de ProductAllergen
  - Alterar cross-reactions logic
  - Inferir o completar datos de alérgenos faltantes
Autonomía: supervisada (solo propuestas, humano implementa)
Evidencia-Requerida:
  - Validación de que NO se modificó lógica de filtrado
  - Tests de accesibilidad (WCAG AA)
  - Review de UX por Product Owner
  - Screenshot comparativo antes/después
```

### 2.3 pwaWaiter (PWA Mesero)

**Nivel de Riesgo:** Medio
**Autonomía IA Recomendada:** Con checkpoints

**Dominios de bajo riesgo:**
- UI de TableCard, TableGrid
- Estilos y responsive design
- IndexedDB para offline storage
- Push notification UI

**Dominios de riesgo medio:**
- Comanda Rápida flow
- Sector filtering logic
- Real-time table sync
- Auth store con refresh proactivo

**Policy Ticket Ejemplo:**
```yaml
PT-ID: PT-WAITER-2026-015
Dominio: pwawaiter/comanda
Riesgo: medio
Intención: Optimizar ComandaTab para mejor UX en dispositivos móviles
Alcance-Permitido:
  - Modificar pwaWaiter/src/components/ComandaTab.tsx
  - Agregar gestos touch
  - Mejorar accesibilidad
Alcance-Prohibido:
  - Cambiar lógica de submitRound
  - Modificar waiterTableAPI
  - Tocar authStore
Autonomía: con-checkpoints (cada 2 horas)
```

### 2.4 Backend REST API (FastAPI)

**Nivel de Riesgo:** Variable por módulo
**Autonomía IA Recomendada:** Graduada según dominio

#### Clasificación Detallada de Routers:

| Router | Riesgo | Autonomía IA |
|--------|--------|--------------|
| `/api/public/` | Bajo | Completa |
| `/api/content/` | Bajo-Medio | Con revisión |
| `/api/admin/categories` | Medio | Con checkpoints |
| `/api/admin/products` | Medio | Con checkpoints |
| `/api/diner/` | Medio | Con checkpoints |
| `/api/waiter/` | Medio | Con checkpoints |
| `/api/kitchen/` | Medio-Alto | Supervisada |
| `/api/auth/` | **Alto** | Solo propuestas |
| `/api/billing/` | **Crítico** | Solo análisis |
| `/api/admin/staff` | **Alto** | Solo propuestas |

**Policy Ticket Ejemplo - Backend Crítico:**
```yaml
PT-ID: PT-API-2026-088
Dominio: backend/billing
Riesgo: CRÍTICO
Responsable-Principal: @tech.lead
Responsable-Seguridad: @security.lead
Responsable-Producto: @product.owner

Intención: Agregar soporte para propinas en pagos con Mercado Pago

Análisis-de-Riesgo:
  Probabilidad-Error: Media
  Impacto-Error: Crítico (pérdida financiera)
  Regulaciones: PCI-DSS aplicable

Alcance-Permitido:
  - SOLO análisis de documentación de MP
  - Sugerir estructura de código
  - Generar tests unitarios en sandbox
  - Identificar edge cases

Alcance-Explícitamente-Prohibido:
  - Escribir código de producción en billing/
  - Modificar allocation.py o mp_webhook.py
  - Acceder a credenciales de MP
  - Generar PRs automáticamente

Autonomía: análisis-solamente
  IA puede: analizar, sugerir, generar tests
  IA NO puede: escribir código de producción

Aprobación-Requerida:
  - Tech Lead (obligatorio)
  - Security Lead (obligatorio)
  - Product Owner (obligatorio)

Evidencia-Requerida:
  Pre-Desarrollo:
    - [ ] Threat model documentado
    - [ ] Diseño técnico aprobado
  Pre-Merge:
    - [ ] Tests >95% cobertura
    - [ ] SAST sin vulnerabilidades
    - [ ] Security review completado
```

### 2.5 WebSocket Gateway

**Nivel de Riesgo:** Alto
**Autonomía IA Recomendada:** Supervisada

El WebSocket Gateway maneja comunicación real-time y multi-tenant, lo que implica riesgos de:
- Fuga de información entre tenants
- Race conditions en broadcast
- Denial of service por mala gestión de conexiones

**Dominios donde IA puede operar con checkpoints:**
- Componentes de métricas/observabilidad
- Tests de integración
- Documentación de eventos
- Refactoring de código modular existente

**Dominios donde IA requiere supervisión estricta:**
- TenantFilter (aislamiento multi-tenant)
- ConnectionManager (lifecycle de conexiones)
- Rate limiting y circuit breaker
- Autenticación de WebSocket

**Policy Ticket Ejemplo:**
```yaml
PT-ID: PT-WS-2026-023
Dominio: ws_gateway/broadcast
Riesgo: alto
Intención: Optimizar batch size para broadcast paralelo
Alcance-Permitido:
  - Modificar ws_gateway/core/connection/broadcaster.py
  - Ajustar constantes en components/core/constants.py
  - Agregar tests de performance
Alcance-Prohibido:
  - Modificar TenantFilter
  - Cambiar lógica de autenticación
  - Alterar sharded locks
Autonomía: supervisada
Aprobación: Tech Lead + Security Champion
Evidencia:
  - Benchmark antes/después
  - Tests de race conditions
  - Validación de aislamiento tenant
```

---

## 3. Mapa de Dominios de Riesgo Completo

```yaml
# MAPA DE DOMINIOS DE RIESGO - Proyecto Integrador
# Fecha: 2026-01-25
# Versión: 1.0

dominios:

  # ═══════════════════════════════════════════════════════════════
  # RIESGO BAJO (🟢) - Autonomía IA Completa
  # ═══════════════════════════════════════════════════════════════

  documentacion:
    archivos:
      - "*.md (README, arquitectura, CLAUDE.md)"
      - "Comentarios de código"
    autonomia: completa
    evidencia: "Markdown válido, links funcionando"

  tests_unitarios:
    archivos:
      - "Dashboard/src/**/*.test.ts"
      - "pwaMenu/src/**/*.test.ts"
      - "backend/tests/test_*.py"
    autonomia: completa
    evidencia: "npm test / pytest pasan"

  estilos_ui:
    archivos:
      - "*/src/**/*.css"
      - "*/tailwind.config.*"
      - "Componentes puramente visuales"
    autonomia: completa
    evidencia: "Build pasa, screenshots OK"

  # ═══════════════════════════════════════════════════════════════
  # RIESGO MEDIO (🟡) - Autonomía con Checkpoints
  # ═══════════════════════════════════════════════════════════════

  logica_frontend:
    archivos:
      - "Dashboard/src/stores/*.ts (excepto authStore)"
      - "pwaMenu/src/stores/*.ts (excepto tableStore crítico)"
      - "pwaWaiter/src/stores/tablesStore.ts"
    autonomia: con_checkpoints
    frecuencia: "Cada 2 horas o feature completo"
    evidencia: "Tests + type check + review"

  api_no_critica:
    archivos:
      - "backend/rest_api/routers/content/"
      - "backend/rest_api/routers/public/"
      - "backend/rest_api/routers/admin/categories.py"
      - "backend/rest_api/routers/admin/products.py"
    autonomia: con_checkpoints
    evidencia: "pytest + SAST limpio"

  servicios_dominio:
    archivos:
      - "backend/rest_api/services/domain/*.py"
      - "backend/rest_api/services/catalog/"
    autonomia: con_checkpoints
    evidencia: "Tests de integración + review"

  # ═══════════════════════════════════════════════════════════════
  # RIESGO ALTO (🟠) - Autonomía Supervisada
  # ═══════════════════════════════════════════════════════════════

  autenticacion:
    archivos:
      - "backend/shared/security/*.py"
      - "Dashboard/src/stores/authStore.ts"
      - "pwaWaiter/src/stores/authStore.ts"
      - "backend/rest_api/routers/auth/"
    autonomia: supervisada
    restricciones:
      - "IA solo propone, humano implementa"
      - "Review obligatorio de Security Champion"
    evidencia: "SAST + DAST + security review"

  alergenos:
    archivos:
      - "pwaMenu/src/hooks/useAllergenFilter.ts"
      - "backend/rest_api/routers/admin/allergens.py"
      - "backend/rest_api/models/allergen.py"
    autonomia: supervisada
    restricciones:
      - "IA NO puede modificar datos de alérgenos"
      - "IA NO puede inferir información faltante"
    evidencia: "Validación de no-modificación + review PO"

  websocket_core:
    archivos:
      - "ws_gateway/connection_manager.py"
      - "ws_gateway/components/broadcast/"
      - "ws_gateway/components/auth/"
    autonomia: supervisada
    evidencia: "Tests de race conditions + tenant isolation"

  # ═══════════════════════════════════════════════════════════════
  # RIESGO CRÍTICO (🔴) - IA Solo Análisis
  # ═══════════════════════════════════════════════════════════════

  pagos_billing:
    archivos:
      - "backend/rest_api/routers/billing/"
      - "backend/rest_api/services/payments/"
      - "backend/rest_api/models/billing.py"
    autonomia: analisis_solamente
    restricciones:
      - "IA puede analizar y sugerir"
      - "IA NO puede escribir código de producción"
      - "IA NO puede generar PRs"
    aprobacion: "Tech Lead + Security + PO"
    evidencia: "Threat model + pentest + audit trail"

  datos_personales:
    archivos:
      - "backend/rest_api/models/customer.py"
      - "backend/rest_api/routers/diner/customer.py"
      - "Cualquier manejo de PII/GDPR"
    autonomia: analisis_solamente
    regulaciones: "GDPR, LGPD"
    evidencia: "Compliance review + legal approval"
```

---

## 4. Transformación de Roles del Equipo

Aplicando el marco IA-Native, los roles del equipo Integrador se transforman:

### 4.1 Product Owner

**Antes:** Priorizador de features
**Después:** Gobernador de riesgo + Priorizador

Nuevas responsabilidades:
- Clasificar cada feature por nivel de riesgo
- Definir autonomía IA por dominio
- Aprobar Policy Tickets de nivel Alto y Crítico
- Responsabilidad explícita sobre decisiones de delegación

### 4.2 Tech Lead

**Antes:** Revisor de código
**Después:** Diseñador de límites cognitivos

Nuevas responsabilidades:
- Definir guardrails en CLAUDE.md
- Configurar branch protection rules
- Diseñar evidencias requeridas por dominio
- Aprobar cambios en dominios de riesgo alto

### 4.3 Desarrolladores

**Antes:** Escritores de código
**Después:** Supervisores cognitivos + Arquitectos de decisiones

Nuevas responsabilidades:
- Crear Policy Tickets antes de usar IA
- Validar outputs de agentes
- Producir evidencias requeridas
- Asumir responsabilidad por código integrado

### 4.4 QA Lead

**Antes:** Detector de bugs
**Después:** Diseñador de sistemas de verificación

Nuevas responsabilidades:
- Diseñar gates automáticos por nivel de riesgo
- Configurar SAST/DAST en CI/CD
- Definir métricas de calidad de código IA-generado
- Monitorear "deuda de comprensión"

---

## 5. Integración con Infraestructura Existente

### 5.1 GitHub como Sistema Nervioso

El proyecto ya usa GitHub. El marco IA-Native se integra así:

```yaml
# .github/workflows/policy-ticket-validation.yml
name: Validate Policy Ticket Compliance

on:
  pull_request:
    types: [opened, synchronize]

jobs:
  validate-policy:
    runs-on: ubuntu-latest
    steps:
      - name: Check Policy Ticket Link
        run: |
          # Verificar que PR tiene Policy Ticket vinculado
          BODY="${{ github.event.pull_request.body }}"
          if ! echo "$BODY" | grep -qE "PT-[A-Z]+-[0-9]+-[0-9]+"; then
            echo "❌ Error: PR debe vincular Policy Ticket (PT-XXX-YYYY-NNN)"
            exit 1
          fi
          echo "✅ Policy Ticket encontrado"

      - name: Classify Risk Level
        id: risk
        run: |
          MODIFIED=$(gh pr view ${{ github.event.pull_request.number }} --json files -q '.files[].path')

          # Detectar dominios críticos
          if echo "$MODIFIED" | grep -qE "billing|payments|security"; then
            echo "level=critical" >> $GITHUB_OUTPUT
          elif echo "$MODIFIED" | grep -qE "auth|allergen|websocket"; then
            echo "level=high" >> $GITHUB_OUTPUT
          elif echo "$MODIFIED" | grep -qE "stores|services|routers"; then
            echo "level=medium" >> $GITHUB_OUTPUT
          else
            echo "level=low" >> $GITHUB_OUTPUT
          fi

      - name: Enforce Approvals by Risk
        run: |
          RISK="${{ steps.risk.outputs.level }}"
          case $RISK in
            critical)
              echo "🔴 CRÍTICO: Requiere Tech Lead + Security + PO"
              # Bloquear merge hasta aprobaciones
              ;;
            high)
              echo "🟠 ALTO: Requiere Tech Lead + Domain Expert"
              ;;
            medium)
              echo "🟡 MEDIO: Requiere 1 peer reviewer"
              ;;
            low)
              echo "🟢 BAJO: Auto-approve si checks pasan"
              ;;
          esac
```

### 5.2 Actualización de CLAUDE.md

El archivo CLAUDE.md existente ya funciona como Policy Ticket global. Se recomienda agregar:

```markdown
## Niveles de Autonomía IA por Dominio

### Autonomía Completa (auto-merge si checks pasan)
- Archivos *.md, *.css
- Tests unitarios
- Componentes de UI sin lógica

### Autonomía con Checkpoints (requiere review)
- Stores Zustand (excepto authStore)
- Domain Services
- Routers no-críticos

### Autonomía Supervisada (IA propone, humano implementa)
- Autenticación y seguridad
- Datos de alérgenos
- WebSocket core

### Solo Análisis (IA NO escribe código de producción)
- Módulo de pagos/billing
- Datos personales (GDPR)
- Infraestructura de seguridad
```

---

## 6. Métricas de Adopción Recomendadas

Para medir el éxito de la implementación del marco:

| Métrica | Target | Alarma |
|---------|--------|--------|
| % PRs con Policy Ticket vinculado | >95% | <80% |
| Tiempo promedio PT bajo riesgo | <10 min | >15 min |
| Tiempo promedio PT alto riesgo | <60 min | >90 min |
| % bugs en código IA-generado vs humano | Similar o menor | >20% mayor |
| Deuda de comprensión (archivos sin owner claro) | <10% | >25% |
| Incidentes en dominios críticos | 0 | >0 |

---

## 7. Plan de Rollout Sugerido

### Fase 1: Semanas 1-2 (Piloto en bajo riesgo)
- Aplicar framework solo a documentación y tests
- Crear primeros Policy Tickets
- Entrenar equipo en nueva terminología

### Fase 2: Semanas 3-4 (Expansión a riesgo medio)
- Extender a UI components y stores no-críticos
- Implementar workflow de GitHub
- Establecer métricas base

### Fase 3: Semanas 5-8 (Dominios sensibles)
- Incluir API routers de riesgo medio
- Refinar clasificación de riesgos
- Ajustar autonomías según resultados

### Fase 4: Semana 9+ (Gobernanza completa)
- Aplicar a todos los dominios
- Auditar compliance
- Optimizar overhead operativo

---

## 8. Conclusión

El marco IA-Native descrito en `activia.md` **es completamente aplicable** al proyecto Integrador. La compatibilidad es natural porque:

1. **Arquitectura alineada**: Clean Architecture, separación de concerns, y patrones de diseño existentes facilitan la clasificación de dominios.

2. **Infraestructura lista**: GitHub, CI/CD, y testing ya en lugar permiten implementar controles graduados.

3. **Documentación robusta**: CLAUDE.md y arqui*.md proporcionan base para Policy Tickets.

4. **Dominios claros**: Billing/pagos, autenticación, y alérgenos ya están identificados como críticos.

5. **Equipo preparado**: Ya trabajan con Claude Code, entienden los riesgos de IA generativa.

**Recomendación final:** Iniciar adopción gradual comenzando con dominios de bajo riesgo (tests, documentación, UI), expandiendo progresivamente mientras el equipo desarrolla fluency en el nuevo marco de gobernanza.

---

*Documento generado como análisis de aplicabilidad del Marco IA-Native al proyecto Integrador.*
