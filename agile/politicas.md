# Backlog de Policy Tickets - Proyecto Integrador

## Marco IA-Native: De User Stories a Policy Tickets

**Documento de Gobernanza de Desarrollo**
**Versión:** 1.0
**Fecha:** 25 de Enero de 2026

---

## Índice

1. [Introducción](#introducción)
2. [Clasificación de Dominios](#clasificación-de-dominios)
3. [Policy Tickets - Dominio CRÍTICO](#policy-tickets---dominio-crítico)
4. [Policy Tickets - Dominio ALTO](#policy-tickets---dominio-alto)
5. [Policy Tickets - Dominio MEDIO](#policy-tickets---dominio-medio)
6. [Policy Tickets - Dominio BAJO](#policy-tickets---dominio-bajo)
7. [Matriz de Aprobaciones](#matriz-de-aprobaciones)
8. [Flujos de Trabajo Gobernados](#flujos-de-trabajo-gobernados)

---

## Introducción

Este documento transforma las funcionalidades del backend del proyecto Integrador en **Policy Tickets** según el marco IA-Native. Cada Policy Ticket define:

- **Qué está autorizado** hacer (no qué resultado se desea)
- **Qué está prohibido** explícitamente
- **Nivel de autonomía** para agentes de IA
- **Evidencias requeridas** para validación
- **Responsable humano** identificado
- **Referencias técnicas** para saber CÓMO implementar

> **Principio Fundamental:** "Delegar ejecución no transfiere responsabilidad. La IA ejecuta; el humano responde."

### Separación de Responsabilidades

| Capa | Propósito | Fuente |
|------|-----------|--------|
| **Gobernanza** | QUÉ está permitido/prohibido | Este documento (Policy Tickets) |
| **Arquitectura** | CÓMO está estructurado el sistema | [arquiBackend.md](../backend/arquiBackend.md), [arquitectura.md](../arquitectura.md) |
| **Implementación** | CÓMO escribir código | [CLAUDE.md](../CLAUDE.md), código existente |

Los Policy Tickets gobiernan la **autorización**. La documentación técnica provee el **conocimiento de implementación**.

---

## Clasificación de Dominios

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                    MAPA DE DOMINIOS DE RIESGO - BACKEND                      │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                              │
│  🔴 CRÍTICO (IA solo análisis)                                              │
│  ├── Autenticación y JWT (auth/)                                            │
│  ├── Gestión de Staff/Usuarios (admin/staff.py)                             │
│  ├── Sistema de Alérgenos (admin/allergens.py, models/allergen.py)          │
│  ├── Pagos y Billing (billing/, services/payments/)                         │
│  └── Seguridad compartida (shared/security/)                                │
│                                                                              │
│  🟠 ALTO (IA supervisada)                                                   │
│  ├── Gestión de Productos (admin/products.py)                               │
│  ├── WebSocket Events (shared/infrastructure/events/)                       │
│  ├── Rate Limiting (shared/security/rate_limit.py)                          │
│  └── Token Blacklist (shared/security/token_blacklist.py)                   │
│                                                                              │
│  🟡 MEDIO (IA con checkpoints)                                              │
│  ├── Órdenes/Rounds (admin/orders.py, kitchen/)                             │
│  ├── Operaciones de Mesero (waiter/)                                        │
│  ├── Operaciones de Diner (diner/)                                          │
│  ├── Sesiones de Mesa (tables/)                                             │
│  └── Customer Loyalty (diner/customer.py)                                   │
│                                                                              │
│  🟢 BAJO (IA completa con auto-merge)                                       │
│  ├── Categorías y Subcategorías (admin/categories.py)                       │
│  ├── Sectores y Mesas (admin/sectors.py, admin/tables.py)                   │
│  ├── Recetas e Ingredientes (content/recipes.py, ingredients.py)            │
│  ├── Promociones (content/promotions.py)                                    │
│  ├── Catálogos públicos (public/catalog.py)                                 │
│  ├── Health checks (public/health.py)                                       │
│  └── Auditoría (admin/audit.py)                                             │
│                                                                              │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## Policy Tickets - Dominio CRÍTICO

### PT-AUTH-001: Sistema de Autenticación JWT

```yaml
PT-ID: PT-AUTH-001
Dominio: backend/rest_api/routers/auth
Nivel-Riesgo: CRÍTICO
Responsable-Principal: @tech.lead
Responsable-Seguridad: @security.lead

Intención: |
  Mantener y evolucionar el sistema de autenticación JWT para personal
  del restaurante (ADMIN, MANAGER, KITCHEN, WAITER).

Contexto-Técnico: |
  - Endpoints: /api/auth/login, /api/auth/refresh, /api/auth/me, /api/auth/logout
  - JWT con jti para revocación individual
  - Access Token TTL: 15 minutos
  - Refresh Token TTL: 7 días
  - Rate limiting dual: IP (5/min) + Email (5/min via Redis)

Archivos-Involucrados:
  - backend/rest_api/routers/auth/routes.py
  - backend/shared/security/auth.py
  - backend/shared/security/password.py
  - backend/shared/security/token_blacklist.py
  - backend/shared/security/rate_limit.py

Referencias-Técnicas:
  CLAUDE.md:
    - "Security Configuration (JWT Token Lifetimes)"
    - "Authentication Methods (JWT vs Table Token)"
    - "Token Blacklist - fail-closed pattern"
    - "Backend Patterns - current_user dependency"
  Arquitectura:
    - "[arquiBackend.md](../backend/arquiBackend.md) - Security layer"
    - "[shared/README.md](../backend/shared/README.md) - Security modules"
  Patrones-en-Código:
    - "backend/rest_api/routers/auth/ - Estructura de routers auth"
    - "backend/tests/test_auth.py - Tests de autenticación existentes"
  Convenciones:
    - "JWT: Access 15min, Refresh 7 días"
    - "Password: bcrypt hashing"
    - "Fail-closed: Redis error = deny access"

Alcance-Permitido-IA:
  - Analizar código existente y documentar flujos
  - Generar tests unitarios para auth.py
  - Sugerir mejoras de seguridad (no implementar)
  - Crear documentación técnica
  - Identificar vulnerabilidades potenciales

Alcance-Explícitamente-Prohibido:
  - Modificar lógica de signing/verification de JWT
  - Cambiar TTL de tokens sin aprobación
  - Modificar algoritmo de hashing de passwords
  - Alterar rate limiting sin análisis de impacto
  - Tocar token_blacklist.py (fail-closed critical)
  - Generar PRs automáticamente

Autonomía: análisis-solamente
  IA puede: Analizar, documentar, generar tests, sugerir
  IA NO puede: Escribir código de producción, generar PRs

Aprobación-Requerida:
  - Tech Lead (obligatorio)
  - Security Lead (obligatorio)
  - Code review por 2 seniors

Evidencia-Requerida:
  Pre-Cualquier-Cambio:
    - [ ] Threat model actualizado
    - [ ] Análisis de impacto en seguridad
    - [ ] Tests de penetration planning
  Pre-Merge:
    - [ ] Tests unitarios >95% cobertura
    - [ ] SAST sin vulnerabilidades
    - [ ] OWASP Top 10 checklist
    - [ ] Security review completado

Criterios-Rechazo-Absolutos:
  - Cualquier vulnerabilidad de seguridad identificada
  - Reducción de TTL de tokens sin justificación
  - Cambios que rompan backward compatibility
  - Ausencia de tests de seguridad
```

---

### PT-AUTH-002: Rate Limiting y Protección contra Ataques

```yaml
PT-ID: PT-AUTH-002
Dominio: backend/shared/security/rate_limit.py
Nivel-Riesgo: CRÍTICO
Responsable-Principal: @tech.lead
Responsable-Seguridad: @security.lead

Intención: |
  Proteger endpoints públicos contra credential stuffing, brute force
  y denial of service mediante rate limiting dual (IP + Email).

Contexto-Técnico: |
  - Implementación: slowapi + Redis Lua scripts
  - Límites actuales:
    * /api/auth/login: 5/min IP + 5/min email
    * /api/auth/refresh: 10/min
    * /api/billing/check/request: 10/min
    * /api/billing/mercadopago/*: 5/min
  - Patrón fail-closed: Error Redis = deny access

Archivos-Involucrados:
  - backend/shared/security/rate_limit.py
  - backend/rest_api/routers/auth/routes.py (decorators)
  - backend/rest_api/routers/billing/routes.py (decorators)

Referencias-Técnicas:
  CLAUDE.md:
    - "Rate Limiting (CRIT-05 FIX)"
    - "Security Middlewares - Rate Limiting section"
    - "Sync Redis pool for blocking operations"
  Arquitectura:
    - "[shared/README.md](../backend/shared/README.md) - Rate limiting module"
  Patrones-en-Código:
    - "backend/shared/security/rate_limit.py - Implementación slowapi + Redis Lua"
    - "backend/rest_api/routers/billing/ - Ejemplo de decorators de rate limit"
  Convenciones:
    - "slowapi + Redis Lua scripts para atomicidad"
    - "Patrón fail-closed obligatorio"
    - "Thread-safe singleton para sync client"

Alcance-Permitido-IA:
  - Analizar efectividad de límites actuales
  - Generar tests de carga para validar límites
  - Documentar comportamiento bajo ataque
  - Sugerir ajustes de límites (no implementar)

Alcance-Explícitamente-Prohibido:
  - Modificar Lua scripts de Redis (atomicidad crítica)
  - Cambiar patrón fail-closed
  - Reducir límites sin análisis de impacto en UX
  - Aumentar límites sin análisis de seguridad
  - Tocar ThreadPoolExecutor singleton

Autonomía: análisis-solamente

Aprobación-Requerida:
  - Security Lead (obligatorio)
  - DevOps (para cambios de límites)

Evidencia-Requerida:
  - [ ] Load tests con límites propuestos
  - [ ] Análisis de falsos positivos
  - [ ] Métricas de requests legítimos bloqueados
```

---

### PT-STAFF-001: Gestión de Personal y Roles

```yaml
PT-ID: PT-STAFF-001
Dominio: backend/rest_api/routers/admin/staff.py
Nivel-Riesgo: CRÍTICO
Responsable-Principal: @tech.lead
Responsable-Producto: @product.owner

Intención: |
  Gestionar usuarios del sistema (staff) con roles por sucursal
  manteniendo restricciones de seguridad para MANAGER.

Contexto-Técnico: |
  - Endpoints: CRUD en /api/admin/staff
  - Roles: ADMIN, MANAGER, KITCHEN, WAITER
  - Restricción MANAGER: No puede crear ADMIN, solo editar staff de sus ramas
  - Password hashing: bcrypt con migration support
  - Modelo: User + UserBranchRole (M:N)

Archivos-Involucrados:
  - backend/rest_api/routers/admin/staff.py
  - backend/rest_api/services/domain/staff_service.py
  - backend/rest_api/models/user.py
  - backend/shared/security/password.py

Referencias-Técnicas:
  CLAUDE.md:
    - "Role-Based Access Control - Tabla de permisos"
    - "Clean Architecture (Backend) - Domain Services"
    - "Permission Strategy Pattern"
    - "Test Users - Usuarios de prueba"
  Arquitectura:
    - "[arquiBackend.md](../backend/arquiBackend.md) - User model, roles"
  Patrones-en-Código:
    - "backend/rest_api/services/domain/staff_service.py - StaffService (MANAGER restrictions)"
    - "backend/rest_api/services/permissions/ - PermissionContext pattern"
    - "backend/tests/test_admin_staff.py - Tests de restricciones"
  Convenciones:
    - "Roles: ADMIN, MANAGER, KITCHEN, WAITER"
    - "MANAGER no puede crear ADMIN"
    - "UserBranchRole para M:N user↔branch"

Alcance-Permitido-IA:
  - Analizar lógica de restricciones MANAGER
  - Generar tests para validar restricciones
  - Documentar flujos de permisos
  - Sugerir mejoras en validaciones

Alcance-Explícitamente-Prohibido:
  - Modificar restricciones de rol MANAGER
  - Cambiar lógica de password hashing
  - Alterar validaciones de tenant isolation
  - Crear nuevos roles sin aprobación
  - Modificar UserBranchRole sin análisis

Autonomía: supervisada
  IA propone cambios, humano revisa línea por línea antes de implementar

Aprobación-Requerida:
  - Tech Lead (obligatorio)
  - Product Owner (para cambios de reglas de negocio)
  - Security review si toca passwords

Evidencia-Requerida:
  - [ ] Tests de restricción MANAGER (no puede crear ADMIN)
  - [ ] Tests de tenant isolation
  - [ ] Tests de branch isolation para MANAGER
  - [ ] Validación de no-regresión en permisos
```

---

### PT-ALLERGEN-001: Sistema de Alérgenos

```yaml
PT-ID: PT-ALLERGEN-001
Dominio: backend/rest_api/routers/admin/allergens.py
Nivel-Riesgo: CRÍTICO
Responsable-Principal: @product.owner
Responsable-Técnico: @tech.lead

Intención: |
  Gestionar información de alérgenos con precisión absoluta.
  IMPACTO DIRECTO EN SALUD DEL CLIENTE.

Contexto-Técnico: |
  - Endpoints: CRUD en /api/admin/allergens
  - Modelos: Allergen, ProductAllergen, AllergenCrossReaction
  - Cross-reactions: M:M entre alérgenos (ej: cacahuete ↔ frutos secos)
  - presence_type: CONTAINS, MAY_CONTAIN, TRACE
  - risk_level: HIGH, MEDIUM, LOW

Archivos-Involucrados:
  - backend/rest_api/routers/admin/allergens.py
  - backend/rest_api/services/domain/allergen_service.py
  - backend/rest_api/models/allergen.py
  - pwaMenu/src/hooks/useAllergenFilter.ts (frontend relacionado)

Referencias-Técnicas:
  CLAUDE.md:
    - "Data Model - Allergen, ProductAllergen, AllergenCrossReaction"
    - "pwaMenu Advanced Filters - useAllergenFilter"
  Arquitectura:
    - "[arquiBackend.md](../backend/arquiBackend.md) - Allergen model"
    - "[pwaMenu/README.md](../pwaMenu/README.md) - Filtros de alérgenos"
  Patrones-en-Código:
    - "backend/rest_api/services/domain/allergen_service.py - AllergenService con cross-reactions"
    - "backend/rest_api/models/allergen.py - Modelos Allergen, ProductAllergen"
    - "pwaMenu/src/hooks/useAllergenFilter.ts - Lógica de filtrado frontend"
  Convenciones:
    - "presence_type: CONTAINS, MAY_CONTAIN, TRACE"
    - "risk_level: HIGH, MEDIUM, LOW"
    - "Cross-reactions: M:M self-referential"
    - "⚠️ IMPACTO EN SALUD - Solo humanos modifican datos"

Alcance-Permitido-IA:
  - Analizar consistencia de datos de alérgenos
  - Generar tests de validación de cross-reactions
  - Crear documentación de flujos
  - Generar reports de coverage de alérgenos por producto

Alcance-Explícitamente-Prohibido:
  - Modificar datos de alérgenos en base de datos
  - Cambiar lógica de cross-reactions
  - Inferir o completar información faltante
  - Alterar presence_type o risk_level sin validación humana
  - Generar código que modifique alérgenos automáticamente

Autonomía: análisis-solamente
  IA puede SOLO analizar y reportar, NUNCA modificar datos de salud

Aprobación-Requerida:
  - Product Owner (obligatorio - responsabilidad legal)
  - Tech Lead (obligatorio)
  - Validación manual de datos por experto en alimentos

Evidencia-Requerida:
  - [ ] Validación de que NO se modificaron datos fuente
  - [ ] Tests de consistencia allergen ↔ product
  - [ ] Tests de cross-reactions (no ciclos)
  - [ ] Audit trail de cualquier cambio

Criterios-Rechazo-Absolutos:
  - Cualquier modificación automática de datos de alérgenos
  - Inferencia de información no verificada
  - Ausencia de validación humana
```

---

### PT-BILLING-001: Procesamiento de Pagos

```yaml
PT-ID: PT-BILLING-001
Dominio: backend/rest_api/routers/billing
Nivel-Riesgo: CRÍTICO
Responsable-Principal: @tech.lead
Responsable-Seguridad: @security.lead
Responsable-Producto: @product.owner

Intención: |
  Procesar pagos (cash y Mercado Pago) con integridad financiera
  garantizada mediante algoritmo FIFO de asignación.

Contexto-Técnico: |
  - Endpoints: /api/billing/*
  - Flujo: Check → Charges (por item) → Allocations (FIFO)
  - Mercado Pago: Circuit breaker + webhook retry queue
  - Race condition prevention: SELECT FOR UPDATE
  - Rate limits: 10/min check request, 5/min MP

Archivos-Involucrados:
  - backend/rest_api/routers/billing/routes.py
  - backend/rest_api/services/payments/allocation.py
  - backend/rest_api/services/payments/circuit_breaker.py
  - backend/rest_api/services/payments/mp_webhook.py
  - backend/rest_api/services/payments/webhook_retry.py
  - backend/rest_api/models/billing.py

Referencias-Técnicas:
  CLAUDE.md:
    - "Data Model - Check, Payment, Charge, Allocation (FIFO)"
    - "Backend Patterns - Race condition prevention (SELECT FOR UPDATE)"
    - "Rate Limiting - billing endpoints"
    - "Production Security Checklist - MERCADOPAGO_WEBHOOK_SECRET"
  Arquitectura:
    - "[arquiBackend.md](../backend/arquiBackend.md) - Billing flow, FIFO allocation"
  Patrones-en-Código:
    - "backend/rest_api/services/payments/allocation.py - Algoritmo FIFO"
    - "backend/rest_api/services/payments/circuit_breaker.py - Circuit breaker pattern"
    - "backend/rest_api/models/billing.py - Check, Payment, Charge, Allocation"
  Convenciones:
    - "FIFO allocation: pagos se asignan en orden de cargo"
    - "Circuit breaker: 5 fallos → OPEN 30s → HALF_OPEN"
    - "Webhook: HMAC-SHA256 verification"
    - "Race condition: SELECT FOR UPDATE obligatorio"
    - "⚠️ IMPACTO FINANCIERO - Solo análisis permitido"

Alcance-Permitido-IA:
  - Analizar documentación de Mercado Pago
  - Generar tests de integración con sandbox
  - Documentar flujo FIFO de allocation
  - Identificar edge cases en pagos parciales
  - Sugerir mejoras de resiliencia

Alcance-Explícitamente-Prohibido:
  - Escribir código de producción en billing/
  - Modificar allocation.py (algoritmo FIFO crítico)
  - Cambiar circuit_breaker.py sin análisis
  - Tocar webhook signature verification
  - Acceder a credenciales de Mercado Pago
  - Modificar SELECT FOR UPDATE locks
  - Generar PRs automáticamente

Autonomía: análisis-solamente
  IA puede: Analizar, documentar, generar tests en sandbox
  IA NO puede: Escribir código de producción, tocar dinero real

Aprobación-Requerida:
  Fase-Diseño:
    - Tech Lead (obligatorio)
    - Security Lead (obligatorio)
  Fase-Implementación:
    - Code review por 2 seniors
    - Security review
  Fase-Deploy:
    - Product Owner (obligatorio)
    - Tech Lead (obligatorio)
    - CTO (notificación)

Evidencia-Requerida:
  Pre-Desarrollo:
    - [ ] Threat model de flujo de pagos
    - [ ] Diseño técnico aprobado
    - [ ] Análisis de compliance (si aplica)
  Pre-Merge:
    - [ ] Tests con Mercado Pago sandbox
    - [ ] Tests de race condition
    - [ ] Tests de FIFO allocation
    - [ ] SAST sin vulnerabilidades
  Pre-Producción:
    - [ ] Reconciliation tests
    - [ ] Runbook de rollback
    - [ ] Alertas configuradas

Criterios-Rechazo-Absolutos:
  - Cualquier vulnerabilidad de seguridad
  - Falla en tests de integridad financiera
  - Ausencia de circuit breaker
  - Race conditions detectadas
```

---

### PT-BILLING-002: Integración Mercado Pago

```yaml
PT-ID: PT-BILLING-002
Dominio: backend/rest_api/services/payments
Nivel-Riesgo: CRÍTICO
Responsable-Principal: @tech.lead
Responsable-Seguridad: @security.lead

Intención: |
  Mantener integración resiliente con Mercado Pago mediante
  circuit breaker, webhook verification y retry queue.

Contexto-Técnico: |
  - Circuit breaker: 5 fallos → OPEN 30s → HALF_OPEN
  - Webhook HMAC-SHA256 verification
  - Retry queue en Redis para webhooks fallidos
  - Rate limit: 5 req/min

Archivos-Involucrados:
  - backend/rest_api/services/payments/circuit_breaker.py
  - backend/rest_api/services/payments/mp_webhook.py
  - backend/rest_api/services/payments/webhook_retry.py

Referencias-Técnicas:
  CLAUDE.md:
    - "Backend Patterns - Circuit breaker pattern"
    - "Thread-safe state transitions (CRIT-DEEP-01 FIX)"
    - "Retry with Jitter (Redis reconnection)"
  Arquitectura:
    - "[arquiBackend.md](../backend/arquiBackend.md) - Payments resilience"
  Patrones-en-Código:
    - "backend/rest_api/services/payments/circuit_breaker.py - CircuitBreaker class"
    - "backend/rest_api/services/payments/webhook_retry.py - Exponential backoff"
    - "ws_gateway/components/resilience/retry.py - RetryConfig pattern"
  Convenciones:
    - "Circuit states: CLOSED → OPEN → HALF_OPEN"
    - "Threshold: 5 failures to open"
    - "Timeout: 30s before half-open"
    - "Webhook signature: HMAC-SHA256"
    - "Retry: exponential backoff with jitter"

Alcance-Permitido-IA:
  - Analizar patrones de fallo en logs
  - Sugerir ajustes de thresholds (no implementar)
  - Generar tests de resiliencia
  - Documentar comportamiento bajo carga

Alcance-Explícitamente-Prohibido:
  - Modificar verificación HMAC-SHA256
  - Cambiar thresholds sin análisis
  - Tocar retry queue sin validación
  - Acceder a secrets de MP

Autonomía: análisis-solamente

Evidencia-Requerida:
  - [ ] Tests de circuit breaker states
  - [ ] Tests de webhook signature verification
  - [ ] Tests de retry con exponential backoff
```

---

## Policy Tickets - Dominio ALTO

### PT-PRODUCT-001: Gestión de Productos

```yaml
PT-ID: PT-PRODUCT-001
Dominio: backend/rest_api/routers/admin/products.py
Nivel-Riesgo: ALTO
Responsable-Principal: @tech.lead
Responsable-Producto: @product.owner

Intención: |
  Gestionar catálogo de productos con precios por sucursal,
  alérgenos y perfiles canónicos.

Contexto-Técnico: |
  - Endpoints: CRUD en /api/admin/products
  - Modelos: Product, BranchProduct, ProductAllergen, ProductIngredient
  - Eager loading para evitar N+1
  - Validación SSRF en URLs de imagen
  - Paginación: limit=100, max=500

Archivos-Involucrados:
  - backend/rest_api/routers/admin/products.py
  - backend/rest_api/services/domain/product_service.py
  - backend/rest_api/models/catalog.py
  - backend/shared/utils/validators.py (SSRF prevention)

Referencias-Técnicas:
  CLAUDE.md:
    - "Data Model - Product, BranchProduct, ProductAllergen, ProductIngredient"
    - "Clean Architecture - ProductService"
    - "Input Validation - validate_image_url (SSRF prevention)"
    - "Backend Patterns - Eager loading (selectinload, joinedload)"
  Arquitectura:
    - "[arquiBackend.md](../backend/arquiBackend.md) - Catalog models"
  Patrones-en-Código:
    - "backend/rest_api/services/domain/product_service.py - ProductService completo"
    - "backend/rest_api/models/catalog.py - Product, BranchProduct"
    - "backend/shared/utils/validators.py - validate_image_url"
  Convenciones:
    - "Precios en centavos (ej: $125.50 = 12550)"
    - "Eager loading obligatorio para evitar N+1"
    - "Paginación: limit=100, max=500"
    - "SSRF: Validar URLs de imagen"

Alcance-Permitido-IA:
  - Refactorizar queries para mejor performance
  - Generar tests de eager loading
  - Mejorar validaciones de input
  - Optimizar paginación

Alcance-Prohibido:
  - Modificar lógica de alérgenos (ver PT-ALLERGEN-001)
  - Cambiar validación SSRF sin review
  - Alterar estructura de BranchProduct
  - Tocar soft delete cascade

Autonomía: supervisada
  IA propone, humano valida línea por línea

Aprobación-Requerida:
  - Tech Lead (obligatorio)
  - Domain expert si toca alérgenos

Evidencia-Requerida:
  - [ ] Tests de performance (no N+1)
  - [ ] Tests de SSRF prevention
  - [ ] Tests de paginación
  - [ ] Type check pasa
```

---

### PT-EVENTS-001: Sistema de Eventos WebSocket

```yaml
PT-ID: PT-EVENTS-001
Dominio: backend/shared/infrastructure/events
Nivel-Riesgo: ALTO
Responsable-Principal: @tech.lead

Intención: |
  Publicar eventos en tiempo real a través de Redis pub/sub
  para sincronización entre frontend y backend.

Contexto-Técnico: |
  - Eventos: ROUND_*, SERVICE_CALL_*, CHECK_*, TABLE_*, TICKET_*, ENTITY_*
  - Canales: branch_waiters, branch_kitchen, sector_waiters, table_session, branch_admin
  - Redis pools: async (50 conn) + sync (20 conn)
  - Patrón fail-closed en errores

Archivos-Involucrados:
  - backend/shared/infrastructure/events/__init__.py
  - backend/shared/infrastructure/events/publisher.py
  - backend/shared/infrastructure/events/event_types.py
  - backend/shared/infrastructure/events/channels.py
  - backend/shared/infrastructure/events/redis_pool.py

Referencias-Técnicas:
  CLAUDE.md:
    - "WebSocket Events (port 8001) - Lista de eventos"
    - "Backend Patterns - Async Redis pool"
    - "Load Optimization - redis_pool_max_connections"
  Arquitectura:
    - "[ws_gateway/README.md](../ws_gateway/README.md) - WebSocket Gateway"
    - "[ws_gateway/arquiws_gateway.md](../ws_gateway/arquiws_gateway.md) - Event flow"
  Patrones-en-Código:
    - "backend/shared/infrastructure/events/publisher.py - publish_event()"
    - "backend/shared/infrastructure/events/event_types.py - ROUND_*, SERVICE_CALL_*, etc."
    - "backend/shared/infrastructure/events/channels.py - channel_branch_waiters(), etc."
  Convenciones:
    - "Eventos: ROUND_SUBMITTED, ROUND_IN_KITCHEN, ROUND_READY, etc."
    - "Canales: branch_waiters, branch_kitchen, sector_waiters"
    - "Redis pools: async (50 conn) + sync (20 conn)"
    - "Tenant isolation obligatorio en canales"

Alcance-Permitido-IA:
  - Agregar nuevos tipos de eventos
  - Documentar flujo de eventos
  - Generar tests de publicación
  - Optimizar batching

Alcance-Prohibido:
  - Modificar redis_pool.py (connection management)
  - Cambiar patrón fail-closed
  - Alterar tenant isolation en canales

Autonomía: supervisada

Evidencia-Requerida:
  - [ ] Tests de publicación por canal
  - [ ] Tests de tenant isolation
  - [ ] Documentación de eventos
```

---

### PT-BLACKLIST-001: Token Blacklist

```yaml
PT-ID: PT-BLACKLIST-001
Dominio: backend/shared/security/token_blacklist.py
Nivel-Riesgo: ALTO
Responsable-Principal: @security.lead
Responsable-Técnico: @tech.lead

Intención: |
  Revocar tokens JWT (logout, password change) mediante
  Redis store con TTL.

Contexto-Técnico: |
  - Redis key: token_blacklist:{jti}
  - TTL = token expiration time
  - Fail-closed: Error Redis = token blacklisted (deny access)
  - revoke_all_user_tokens(): Logout de todas las sesiones

Archivos-Involucrados:
  - backend/shared/security/token_blacklist.py
  - backend/shared/infrastructure/events/redis_pool.py

Referencias-Técnicas:
  CLAUDE.md:
    - "Token Blacklist - fail-closed pattern"
    - "Backend Patterns - Fail-closed security pattern (CRIT-02 FIX)"
    - "Sync Redis pool for blocking operations"
  Arquitectura:
    - "[shared/README.md](../backend/shared/README.md) - Token blacklist module"
  Patrones-en-Código:
    - "backend/shared/security/token_blacklist.py - is_token_blacklisted(), revoke_all_user_tokens()"
    - "backend/shared/infrastructure/events/redis_pool.py - get_redis_sync_client()"
  Convenciones:
    - "Redis key: token_blacklist:{jti}"
    - "TTL = token expiration time"
    - "⚠️ FAIL-CLOSED OBLIGATORIO: Error Redis = deny access"
    - "revoke_all_user_tokens() en logout"

Alcance-Permitido-IA:
  - Generar tests de revocación
  - Documentar comportamiento fail-closed
  - Analizar TTL management

Alcance-Prohibido:
  - Modificar patrón fail-closed (CRÍTICO)
  - Cambiar estructura de keys en Redis
  - Alterar revoke_all_user_tokens sin review

Autonomía: supervisada

Evidencia-Requerida:
  - [ ] Tests de fail-closed behavior
  - [ ] Tests de TTL expiration
  - [ ] Tests de revoke_all
```

---

## Policy Tickets - Dominio MEDIO

### PT-ORDERS-001: Gestión de Órdenes (Rounds)

```yaml
PT-ID: PT-ORDERS-001
Dominio: backend/rest_api/routers/admin/orders.py
Nivel-Riesgo: MEDIO
Responsable-Principal: @tech.lead

Intención: |
  Gestionar ciclo de vida de órdenes (Rounds) desde
  PENDING hasta SERVED.

Contexto-Técnico: |
  - Estados: PENDING → IN_KITCHEN → READY → SERVED
  - Eventos: ROUND_SUBMITTED, ROUND_IN_KITCHEN, ROUND_READY, ROUND_SERVED
  - Restricción: KITCHEN solo puede IN_KITCHEN→READY
  - Eager loading: Round → Items → Products

Archivos-Involucrados:
  - backend/rest_api/routers/admin/orders.py
  - backend/rest_api/routers/kitchen/rounds.py
  - backend/rest_api/models/order.py

Referencias-Técnicas:
  CLAUDE.md:
    - "Round Status Flow (Role-Restricted) - Tabla de estados"
    - "Table Status Animation (Dashboard) - hasNewOrder flag"
    - "Backend Patterns - Eager loading (CRIT-02 FIX)"
    - "Centralized constants - RoundStatus"
  Arquitectura:
    - "[arquiBackend.md](../backend/arquiBackend.md) - Order flow"
    - "[Dashboard/arquiDashboard.md](../Dashboard/arquiDashboard.md) - TableSessionModal"
  Patrones-en-Código:
    - "backend/rest_api/routers/kitchen/rounds.py - Transiciones de estado"
    - "backend/rest_api/models/order.py - Round, RoundItem"
    - "Dashboard/src/components/tables/TableSessionModal.tsx - UI de estados"
  Convenciones:
    - "Estados: PENDING → IN_KITCHEN → READY → SERVED"
    - "KITCHEN solo puede: IN_KITCHEN → READY"
    - "Eager loading obligatorio: Round.items.product"

Alcance-Permitido-IA:
  - Optimizar queries con eager loading
  - Generar tests de transición de estados
  - Mejorar validaciones de rol
  - Agregar filtros de búsqueda

Alcance-Prohibido:
  - Cambiar máquina de estados sin aprobación
  - Modificar restricciones de rol KITCHEN
  - Alterar publicación de eventos

Autonomía: con_checkpoints
  Checkpoint cada feature completado

Aprobación-Requerida:
  - Tech Lead (obligatorio)
  - 1 peer reviewer

Evidencia-Requerida:
  - [ ] Tests de transición de estados
  - [ ] Tests de restricción KITCHEN
  - [ ] Tests de eager loading (no N+1)
```

---

### PT-KITCHEN-001: Operaciones de Cocina

```yaml
PT-ID: PT-KITCHEN-001
Dominio: backend/rest_api/routers/kitchen
Nivel-Riesgo: MEDIO
Responsable-Principal: @tech.lead

Intención: |
  Proveer operaciones para personal de cocina: ver órdenes
  pendientes y actualizar estados de tickets.

Contexto-Técnico: |
  - Endpoints: /api/kitchen/rounds, /api/kitchen/tickets
  - Auth: JWT con roles KITCHEN/MANAGER/ADMIN
  - Estaciones: BAR, HOT_KITCHEN, COLD_KITCHEN, GRILL, PASTRY
  - Ticket states: PENDING → IN_PROGRESS → READY → DELIVERED

Archivos-Involucrados:
  - backend/rest_api/routers/kitchen/rounds.py
  - backend/rest_api/routers/kitchen/tickets.py
  - backend/rest_api/models/kitchen.py

Referencias-Técnicas:
  CLAUDE.md:
    - "Backend API Structure - /api/kitchen/*"
    - "Round Status Flow - KITCHEN restrictions"
    - "Backend Patterns - Kitchen tickets eager loading (CRIT-02)"
  Arquitectura:
    - "[arquiBackend.md](../backend/arquiBackend.md) - Kitchen flow"
  Patrones-en-Código:
    - "backend/rest_api/routers/kitchen/rounds.py - Kitchen role validation"
    - "backend/rest_api/routers/kitchen/tickets.py - Ticket state transitions"
    - "backend/rest_api/models/kitchen.py - KitchenTicket, KitchenTicketItem"
  Convenciones:
    - "Estaciones: BAR, HOT_KITCHEN, COLD_KITCHEN, GRILL, PASTRY"
    - "Ticket states: PENDING → IN_PROGRESS → READY → DELIVERED"
    - "Roles: KITCHEN, MANAGER, ADMIN pueden acceder"

Alcance-Permitido-IA:
  - Mejorar filtros por estación
  - Optimizar queries
  - Generar tests
  - Agregar métricas de tiempo

Alcance-Prohibido:
  - Modificar validaciones de rol
  - Cambiar estados sin análisis

Autonomía: con_checkpoints

Evidencia-Requerida:
  - [ ] Tests por estación
  - [ ] Tests de permisos por rol
```

---

### PT-WAITER-001: Operaciones de Mesero

```yaml
PT-ID: PT-WAITER-001
Dominio: backend/rest_api/routers/waiter
Nivel-Riesgo: MEDIO
Responsable-Principal: @tech.lead

Intención: |
  Proveer operaciones para meseros: ver mesas asignadas,
  gestionar service calls, Comanda Rápida.

Contexto-Técnico: |
  - Endpoints: /api/waiter/*
  - SECTOR-FILTER: WAITER solo ve mesas de sus sectores (hoy)
  - Comanda Rápida: Menú compacto + submit round
  - Service Calls: CREATED → ACKED → CLOSED

Archivos-Involucrados:
  - backend/rest_api/routers/waiter/routes.py
  - backend/rest_api/models/sector.py (WaiterSectorAssignment)

Referencias-Técnicas:
  CLAUDE.md:
    - "Backend API Structure - /api/waiter/*"
    - "Waiter Sector Filtering - WaiterSectorAssignment"
    - "Comanda Rápida (pwaWaiter) - Compact menu endpoint"
  Arquitectura:
    - "[arquiBackend.md](../backend/arquiBackend.md) - Waiter flow"
    - "[pwaWaiter/CLAUDE.md](../pwaWaiter/CLAUDE.md) - pwaWaiter architecture"
  Patrones-en-Código:
    - "backend/rest_api/routers/waiter/routes.py - Sector filtering"
    - "backend/rest_api/models/sector.py - WaiterSectorAssignment"
    - "pwaWaiter/src/components/ComandaTab.tsx - Comanda UI"
  Convenciones:
    - "WAITER solo ve mesas de sus sectores asignados (hoy)"
    - "ADMIN/MANAGER ven todas las mesas"
    - "Comanda Rápida: menú sin imágenes"
    - "Service Calls: CREATED → ACKED → CLOSED"

Alcance-Permitido-IA:
  - Mejorar filtrado por sector
  - Optimizar menú compacto
  - Generar tests de asignación
  - Mejorar UX de Comanda Rápida

Alcance-Prohibido:
  - Cambiar lógica de sector filtering sin review
  - Modificar asignaciones automáticamente

Autonomía: con_checkpoints

Evidencia-Requerida:
  - [ ] Tests de sector filtering
  - [ ] Tests de Comanda Rápida flow
  - [ ] Tests de service calls lifecycle
```

---

### PT-DINER-001: Operaciones de Cliente

```yaml
PT-ID: PT-DINER-001
Dominio: backend/rest_api/routers/diner
Nivel-Riesgo: MEDIO
Responsable-Principal: @tech.lead
Responsable-Producto: @product.owner

Intención: |
  Gestionar operaciones del cliente en mesa: registro,
  envío de órdenes, preferencias implícitas, service calls.

Contexto-Técnico: |
  - Auth: Table Token (HMAC, 3h TTL)
  - Device tracking: device_id + device_fingerprint
  - Implicit preferences: alérgenos, dieta, cocción
  - Round confirmation: confirmación grupal antes de submit

Archivos-Involucrados:
  - backend/rest_api/routers/diner/orders.py
  - backend/rest_api/routers/diner/customer.py
  - backend/rest_api/models/customer.py

Referencias-Técnicas:
  CLAUDE.md:
    - "Backend API Structure - /api/diner/*"
    - "Customer Loyalty System (Fidelización) - 4 fases"
    - "Authentication Methods - Table Token (HMAC)"
    - "Round Confirmation - Confirmación Grupal"
  Arquitectura:
    - "[pwaMenu/README.md](../pwaMenu/README.md) - pwaMenu flows"
  Patrones-en-Código:
    - "backend/rest_api/routers/diner/orders.py - Round submission"
    - "backend/rest_api/models/customer.py - Customer, Diner"
    - "pwaMenu/src/hooks/useImplicitPreferences.ts - Preferences sync"
    - "pwaMenu/src/stores/tableStore/store.ts - Round confirmation"
  Convenciones:
    - "Auth: Table Token (HMAC, 3h TTL)"
    - "device_id + device_fingerprint para tracking"
    - "implicit_preferences: alérgenos, dieta, cocción"
    - "Round confirmation: confirmación grupal antes de submit"

Alcance-Permitido-IA:
  - Mejorar flow de preferencias
  - Optimizar round confirmation
  - Generar tests de device tracking
  - Documentar flujo de customer loyalty

Alcance-Prohibido:
  - Modificar Table Token generation (ver PT-AUTH-001)
  - Cambiar device fingerprinting sin análisis de privacidad
  - Alterar consent management

Autonomía: con_checkpoints

Evidencia-Requerida:
  - [ ] Tests de device tracking
  - [ ] Tests de implicit preferences sync
  - [ ] Tests de round confirmation flow
```

---

### PT-TABLES-001: Gestión de Sesiones de Mesa

```yaml
PT-ID: PT-TABLES-001
Dominio: backend/rest_api/routers/tables
Nivel-Riesgo: MEDIO
Responsable-Principal: @tech.lead

Intención: |
  Gestionar sesiones de mesa desde QR scan hasta liberación,
  incluyendo generación de Table Token.

Contexto-Técnico: |
  - Endpoints: /api/tables/code/{code}/session, /api/tables/{id}/session
  - Table codes: alfanuméricos (ej: "INT-01")
  - Requiere branch_slug para identificar mesa
  - Genera Table Token HMAC
  - Session states: OPEN → PAYING → CLOSED

Archivos-Involucrados:
  - backend/rest_api/routers/tables/routes.py
  - backend/rest_api/models/table.py

Referencias-Técnicas:
  CLAUDE.md:
    - "Backend API Structure - /api/tables/*"
    - "Table Session Lifecycle - OPEN, PAYING, CLOSED"
    - "Table Codes vs IDs - alfanuméricos vs numéricos"
    - "Common Issues - Table status not updating"
  Arquitectura:
    - "[arquiBackend.md](../backend/arquiBackend.md) - Table session flow"
  Patrones-en-Código:
    - "backend/rest_api/routers/tables/routes.py - Session creation"
    - "backend/rest_api/models/table.py - Table, TableSession"
    - "backend/rest_api/services/domain/table_service.py - TableService"
  Convenciones:
    - "Table codes: alfanuméricos (ej: INT-01, TER-02)"
    - "branch_slug requerido para identificar mesa"
    - "Session states: OPEN → PAYING → CLOSED"
    - "Table Token generado en session creation"

Alcance-Permitido-IA:
  - Mejorar lookup por código
  - Generar tests de sesión lifecycle
  - Optimizar eager loading

Alcance-Prohibido:
  - Modificar Table Token generation
  - Cambiar branch_slug requirement sin análisis

Autonomía: con_checkpoints

Evidencia-Requerida:
  - [ ] Tests de session creation
  - [ ] Tests de Table Token generation
  - [ ] Tests de session states
```

---

### PT-CUSTOMER-001: Sistema de Fidelización

```yaml
PT-ID: PT-CUSTOMER-001
Dominio: backend/rest_api/routers/diner/customer.py
Nivel-Riesgo: MEDIO
Responsable-Principal: @product.owner
Responsable-Técnico: @tech.lead

Intención: |
  Gestionar registro de clientes con opt-in consent,
  métricas de visitas y recomendaciones personalizadas.

Contexto-Técnico: |
  - Link: device_id → Customer
  - Consent flags: consent_remember, consent_marketing
  - Métricas: first_visit, last_visit, total_visits, total_spent
  - Segmentación: loyal, regular, occasional
  - GDPR compliance requerido

Archivos-Involucrados:
  - backend/rest_api/routers/diner/customer.py
  - backend/rest_api/models/customer.py

Referencias-Técnicas:
  CLAUDE.md:
    - "Customer Loyalty System - Fase 4: Customer Opt-in"
    - "Data Model - Customer, Diner (customer_id link)"
    - "Backend API Structure - /api/customer/*"
  Arquitectura:
    - "[pwaMenu/README.md](../pwaMenu/README.md) - Customer loyalty"
  Patrones-en-Código:
    - "backend/rest_api/routers/diner/customer.py - Customer registration, recognition"
    - "backend/rest_api/models/customer.py - Customer model with GDPR fields"
    - "pwaMenu/src/hooks/useCustomerRecognition.ts - Customer detection"
    - "pwaMenu/src/components/OptInModal.tsx - Consent UI"
  Convenciones:
    - "Consent flags: consent_remember, consent_marketing"
    - "Métricas: first_visit, last_visit, total_visits, total_spent"
    - "Segmentación: loyal, regular, occasional"
    - "⚠️ GDPR compliance obligatorio"

Alcance-Permitido-IA:
  - Mejorar algoritmo de recomendaciones
  - Generar tests de consent flow
  - Optimizar queries de métricas
  - Documentar GDPR compliance

Alcance-Prohibido:
  - Cambiar consent management sin legal review
  - Modificar link device → customer sin análisis
  - Almacenar datos sin consent explícito

Autonomía: con_checkpoints

Aprobación-Requerida:
  - Product Owner (obligatorio para cambios de consent)
  - Legal/Compliance si toca GDPR

Evidencia-Requerida:
  - [ ] Tests de consent flow
  - [ ] Tests de métricas calculation
  - [ ] Documentación GDPR
```

---

## Policy Tickets - Dominio BAJO

### PT-CATEGORY-001: Gestión de Categorías

```yaml
PT-ID: PT-CATEGORY-001
Dominio: backend/rest_api/routers/admin/categories.py
Nivel-Riesgo: BAJO
Responsable-Principal: @tech.lead

Intención: |
  Gestionar categorías y subcategorías del menú con
  ordenamiento y exclusiones por rama.

Contexto-Técnico: |
  - Endpoints: CRUD en /api/admin/categories, /api/admin/subcategories
  - Exclusiones: BranchCategoryExclusion, BranchSubcategoryExclusion
  - Ordenamiento: display_order

Archivos-Involucrados:
  - backend/rest_api/routers/admin/categories.py
  - backend/rest_api/routers/admin/subcategories.py
  - backend/rest_api/services/domain/category_service.py
  - backend/rest_api/models/catalog.py

Referencias-Técnicas:
  CLAUDE.md:
    - "Clean Architecture - CategoryService, SubcategoryService"
    - "Data Model - Category, Subcategory"
    - "Backend Directory Structure - admin routers"
  Patrones-en-Código:
    - "backend/rest_api/services/domain/category_service.py - CategoryService"
    - "backend/rest_api/services/domain/subcategory_service.py - SubcategoryService"
    - "backend/rest_api/models/catalog.py - Category, Subcategory"
  Convenciones:
    - "display_order para ordenamiento"
    - "BranchCategoryExclusion, BranchSubcategoryExclusion"
    - "Soft delete con AuditMixin"

Alcance-Permitido-IA:
  - CRUD completo
  - Mejorar ordenamiento
  - Optimizar queries
  - Generar tests

Alcance-Prohibido:
  - Cambiar estructura de exclusiones sin review

Autonomía: completa
  Auto-merge si checks pasan

Aprobación-Requerida:
  - Self-approval si tests pasan

Evidencia-Requerida:
  - [ ] Tests CRUD
  - [ ] Tests de exclusiones
  - [ ] Type check pasa
```

---

### PT-SECTOR-001: Gestión de Sectores y Mesas

```yaml
PT-ID: PT-SECTOR-001
Dominio: backend/rest_api/routers/admin/sectors.py, tables.py
Nivel-Riesgo: BAJO
Responsable-Principal: @tech.lead

Intención: |
  Gestionar sectores (globales y por rama) y mesas
  con generación de códigos.

Archivos-Involucrados:
  - backend/rest_api/routers/admin/sectors.py
  - backend/rest_api/routers/admin/tables.py
  - backend/rest_api/services/domain/sector_service.py
  - backend/rest_api/services/domain/table_service.py

Referencias-Técnicas:
  CLAUDE.md:
    - "Clean Architecture - SectorService, TableService"
    - "Data Model - BranchSector, Table, WaiterSectorAssignment"
    - "Table Codes vs IDs"
  Patrones-en-Código:
    - "backend/rest_api/services/domain/sector_service.py - SectorService"
    - "backend/rest_api/services/domain/table_service.py - TableService"
    - "backend/rest_api/models/sector.py - BranchSector, WaiterSectorAssignment"
  Convenciones:
    - "Sectores globales y por rama"
    - "Table codes: alfanuméricos generados"
    - "WaiterSectorAssignment para asignaciones diarias"

Alcance-Permitido-IA:
  - CRUD completo
  - Mejorar generación de códigos
  - Optimizar queries

Autonomía: completa

Evidencia-Requerida:
  - [ ] Tests CRUD
  - [ ] Tests de código generation
```

---

### PT-RECIPE-001: Gestión de Recetas

```yaml
PT-ID: PT-RECIPE-001
Dominio: backend/rest_api/routers/content/recipes.py
Nivel-Riesgo: BAJO
Responsable-Principal: @tech.lead

Intención: |
  Gestionar fichas técnicas de cocina con ingredientes,
  pasos, alérgenos y ingestión RAG.

Archivos-Involucrados:
  - backend/rest_api/routers/content/recipes.py
  - backend/rest_api/models/recipe.py

Referencias-Técnicas:
  CLAUDE.md:
    - "Recipe Module - Fichas técnicas de cocina"
    - "Data Model - Recipe, RecipeAllergen"
    - "Backend API Structure - /api/recipes/*"
  Patrones-en-Código:
    - "backend/rest_api/routers/content/recipes.py - Recipe CRUD + RAG ingest"
    - "backend/rest_api/models/recipe.py - Recipe, RecipeAllergen"
    - "backend/rest_api/services/rag/service.py - RAG service"
  Convenciones:
    - "Fichas técnicas: ingredientes, pasos, alérgenos"
    - "RAG ingest via /api/recipes/{id}/ingest"
    - "Puede linkearse a Products"

Alcance-Permitido-IA:
  - CRUD completo
  - Mejorar ingestión RAG
  - Generar tests

Alcance-Prohibido:
  - Modificar alérgenos de receta sin review (ver PT-ALLERGEN-001)

Autonomía: completa

Evidencia-Requerida:
  - [ ] Tests CRUD
  - [ ] Tests de RAG ingestión
```

---

### PT-INGREDIENT-001: Gestión de Ingredientes

```yaml
PT-ID: PT-INGREDIENT-001
Dominio: backend/rest_api/routers/content/ingredients.py
Nivel-Riesgo: BAJO
Responsable-Principal: @tech.lead

Intención: |
  Gestionar ingredientes jerárquicos: grupos,
  ingredientes y sub-ingredientes.

Archivos-Involucrados:
  - backend/rest_api/routers/content/ingredients.py
  - backend/rest_api/models/ingredient.py

Referencias-Técnicas:
  CLAUDE.md:
    - "Data Model - IngredientGroup, Ingredient, SubIngredient, ProductIngredient"
  Patrones-en-Código:
    - "backend/rest_api/routers/content/ingredients.py - Ingredient CRUD"
    - "backend/rest_api/models/ingredient.py - Hierarchical ingredients"
  Convenciones:
    - "Jerarquía: Group → Ingredient → SubIngredient"
    - "ProductIngredient para M:N con productos"

Alcance-Permitido-IA:
  - CRUD completo
  - Mejorar jerarquía
  - Optimizar queries

Autonomía: completa

Evidencia-Requerida:
  - [ ] Tests CRUD
  - [ ] Tests de jerarquía
```

---

### PT-PROMOTION-001: Gestión de Promociones

```yaml
PT-ID: PT-PROMOTION-001
Dominio: backend/rest_api/routers/content/promotions.py
Nivel-Riesgo: BAJO
Responsable-Principal: @product.owner

Intención: |
  Gestionar promociones multi-rama con productos asociados.

Archivos-Involucrados:
  - backend/rest_api/routers/content/promotions.py
  - backend/rest_api/services/domain/promotion_service.py
  - backend/rest_api/models/promotion.py

Referencias-Técnicas:
  CLAUDE.md:
    - "Clean Architecture - PromotionService"
    - "Data Model - Promotion, PromotionBranch, PromotionItem"
    - "Backend Patterns - Promotions eager loading (PERF-01)"
  Patrones-en-Código:
    - "backend/rest_api/services/domain/promotion_service.py - PromotionService"
    - "backend/rest_api/models/promotion.py - Promotion, PromotionBranch, PromotionItem"
  Convenciones:
    - "Multi-rama: PromotionBranch M:N"
    - "Items: PromotionItem M:N con productos"
    - "Eager loading para evitar 2*N queries"

Alcance-Permitido-IA:
  - CRUD completo
  - Mejorar validación de fechas
  - Optimizar eager loading

Autonomía: completa

Evidencia-Requerida:
  - [ ] Tests CRUD
  - [ ] Tests de fecha/hora validation
```

---

### PT-PUBLIC-001: Endpoints Públicos

```yaml
PT-ID: PT-PUBLIC-001
Dominio: backend/rest_api/routers/public
Nivel-Riesgo: BAJO
Responsable-Principal: @tech.lead

Intención: |
  Proveer menú público y health checks sin autenticación.

Archivos-Involucrados:
  - backend/rest_api/routers/public/catalog.py
  - backend/rest_api/routers/public/health.py

Referencias-Técnicas:
  CLAUDE.md:
    - "Backend API Structure - /api/public/*"
    - "Health Check Endpoints"
    - "Health Check Decorator (ARCH-OPP-03)"
  Patrones-en-Código:
    - "backend/rest_api/routers/public/catalog.py - Public menu endpoint"
    - "backend/rest_api/routers/public/health.py - Health checks"
    - "backend/shared/utils/health.py - health_check_with_timeout decorator"
  Convenciones:
    - "No auth requerido"
    - "Rate limiting en endpoints públicos"
    - "No exponer datos sensibles"

Alcance-Permitido-IA:
  - Optimizar queries de menú
  - Mejorar health checks
  - Agregar caching

Alcance-Prohibido:
  - Exponer datos sensibles
  - Remover rate limiting

Autonomía: completa

Evidencia-Requerida:
  - [ ] Tests de rate limiting
  - [ ] Tests de response structure
  - [ ] No data leakage verification
```

---

### PT-AUDIT-001: Sistema de Auditoría

```yaml
PT-ID: PT-AUDIT-001
Dominio: backend/rest_api/routers/admin/audit.py
Nivel-Riesgo: BAJO
Responsable-Principal: @tech.lead

Intención: |
  Proveer acceso de solo lectura a logs de auditoría
  para trazabilidad.

Archivos-Involucrados:
  - backend/rest_api/routers/admin/audit.py
  - backend/rest_api/models/audit.py

Referencias-Técnicas:
  CLAUDE.md:
    - "Data Model - AuditLog"
    - "Soft Delete Pattern - AuditMixin (created_by, updated_by, deleted_by)"
  Patrones-en-Código:
    - "backend/rest_api/routers/admin/audit.py - Audit log read-only access"
    - "backend/rest_api/models/audit.py - AuditLog model"
    - "backend/rest_api/services/crud/audit.py - Audit service"
  Convenciones:
    - "Solo lectura - no modificar logs"
    - "Paginación para grandes volúmenes"
    - "Filtros por fecha, entidad, usuario"

Alcance-Permitido-IA:
  - Mejorar filtros de búsqueda
  - Optimizar paginación
  - Generar tests

Alcance-Prohibido:
  - Permitir modificación de logs
  - Exponer logs sin autorización

Autonomía: completa

Evidencia-Requerida:
  - [ ] Tests de solo lectura
  - [ ] Tests de filtros
```

---

## Matriz de Aprobaciones

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                    MATRIZ DE APROBACIONES POR NIVEL                          │
├──────────┬───────────────┬─────────────────────────────────────────────────┤
│ NIVEL    │ TIEMPO MAX    │ APROBADORES REQUERIDOS                          │
├──────────┼───────────────┼─────────────────────────────────────────────────┤
│ BAJO     │ 10 min        │ Self-approval + CI checks pasan                 │
│          │               │ Auto-merge habilitado                           │
├──────────┼───────────────┼─────────────────────────────────────────────────┤
│ MEDIO    │ 30 min        │ 1 peer reviewer                                 │
│          │               │ Tech Lead notificado                            │
├──────────┼───────────────┼─────────────────────────────────────────────────┤
│ ALTO     │ 60 min        │ Tech Lead (obligatorio)                         │
│          │               │ Domain expert (si aplica)                       │
│          │               │ Security review (si toca auth)                  │
├──────────┼───────────────┼─────────────────────────────────────────────────┤
│ CRÍTICO  │ 2+ horas      │ Tech Lead (obligatorio)                         │
│          │               │ Security Lead (obligatorio)                     │
│          │               │ Product Owner (obligatorio)                     │
│          │               │ Code review por 2 seniors                       │
│          │               │ Penetration test (si pagos/auth)                │
└──────────┴───────────────┴─────────────────────────────────────────────────┘
```

---

## Flujos de Trabajo Gobernados

### Flujo 1: Orden Completa (Mesa a Pago)

```yaml
Flujo-ID: FLOW-ORDER-001
Nombre: "Orden Completa - Mesa a Pago"
Policy-Tickets-Involucrados:
  - PT-TABLES-001 (Session creation)
  - PT-DINER-001 (Order submission)
  - PT-ORDERS-001 (Round management)
  - PT-KITCHEN-001 (Preparation)
  - PT-WAITER-001 (Service)
  - PT-BILLING-001 (Payment)

Secuencia:
  1. Diner escanea QR → PT-TABLES-001
     - Crea TableSession + Table Token
     - Evento: TABLE_SESSION_STARTED

  2. Diner registra y ordena → PT-DINER-001
     - Crea Diner + Round + RoundItems
     - Evento: ROUND_SUBMITTED

  3. Admin envía a cocina → PT-ORDERS-001
     - Round: PENDING → IN_KITCHEN
     - Evento: ROUND_IN_KITCHEN

  4. Cocina prepara → PT-KITCHEN-001
     - Round: IN_KITCHEN → READY
     - Evento: ROUND_READY

  5. Mesero sirve → PT-WAITER-001
     - Round: READY → SERVED
     - Evento: ROUND_SERVED

  6. Diner paga → PT-BILLING-001
     - Check + Charges + Payment + Allocations
     - Evento: CHECK_PAID

Controles-de-Gobernanza:
  - Cada paso tiene Policy Ticket asociado
  - Eventos trazables en Redis pub/sub
  - Audit log en cada transición
```

### Flujo 2: Autenticación y Sesión

```yaml
Flujo-ID: FLOW-AUTH-001
Nombre: "Autenticación de Personal"
Policy-Tickets-Involucrados:
  - PT-AUTH-001 (Login/Logout)
  - PT-AUTH-002 (Rate Limiting)
  - PT-BLACKLIST-001 (Token Revocation)

Secuencia:
  1. Usuario intenta login → PT-AUTH-002
     - Rate limit check (IP + Email)
     - Si excede: 429 Too Many Requests

  2. Credenciales válidas → PT-AUTH-001
     - Genera JWT + Refresh Token
     - Registra jti para revocación

  3. Durante sesión → PT-AUTH-001
     - Valida JWT en cada request
     - Verifica contra blacklist

  4. Logout → PT-BLACKLIST-001
     - revoke_all_user_tokens()
     - Cierra todas las sesiones

Controles-de-Gobernanza:
  - Rate limiting en entrada
  - Token blacklist fail-closed
  - Audit de login/logout
```

---

## Apéndice: Template de Policy Ticket

```yaml
# TEMPLATE DE POLICY TICKET
PT-ID: PT-{DOMINIO}-{NNN}
Dominio: backend/rest_api/routers/{path}
Nivel-Riesgo: {BAJO|MEDIO|ALTO|CRÍTICO}
Responsable-Principal: @{username}
Responsable-Secundario: @{username}  # Si aplica

Intención: |
  Descripción clara de lo que se busca lograr.
  Máximo 3 líneas.

Contexto-Técnico: |
  - Endpoints involucrados
  - Modelos/tablas afectadas
  - Dependencias técnicas
  - Rate limits si aplica

Archivos-Involucrados:
  - path/to/file1.py
  - path/to/file2.py

# ============================================
# REFERENCIAS TÉCNICAS (CÓMO IMPLEMENTAR)
# ============================================
# Esta sección conecta la GOBERNANZA con el CONOCIMIENTO TÉCNICO
# La IA consulta estas fuentes para saber CÓMO hacer lo permitido

Referencias-Técnicas:
  CLAUDE.md:
    - "Sección: Nombre de sección relevante"
    - "Líneas: NNN-NNN (descripción breve)"
  Arquitectura:
    - "[arquiBackend.md](../backend/arquiBackend.md) - Sección relevante"
  Patrones-en-Código:
    - "path/to/ejemplo.py - Patrón a seguir"
  Skills-Gobernanza:
    - "{skill-name} - Si aplica un skill específico"

Alcance-Permitido-IA:
  - Lista de acciones autorizadas
  - Ser específico

Alcance-Explícitamente-Prohibido:
  - Lista de acciones prohibidas
  - Todo lo no listado en "permitido" está prohibido

Autonomía: {análisis-solamente|supervisada|con_checkpoints|completa}
  Descripción de qué puede hacer la IA

Aprobación-Requerida:
  - Rol (obligatorio/opcional)
  - Condiciones especiales

Evidencia-Requerida:
  Pre-Desarrollo:
    - [ ] Checklist items
  Pre-Merge:
    - [ ] Tests requeridos
    - [ ] Reviews requeridos
  Pre-Producción:  # Solo para CRÍTICO
    - [ ] Validaciones adicionales

Criterios-Rechazo-Absolutos:
  - Condiciones que causan rechazo automático
```

---

*Documento generado siguiendo el Marco IA-Native para Desarrollo de Software.*
*Versión 1.0 - Enero 2026*
