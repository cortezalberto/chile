# Arquitectura del Sistema Integrador

## Documento Técnico de Arquitectura - Visión de Liderazgo de Proyecto

---

## Tabla de Contenidos

1. [Visión General del Sistema](#1-visión-general-del-sistema)
2. [Topología de Componentes](#2-topología-de-componentes)
3. [Modelo de Datos y Dominio](#3-modelo-de-datos-y-dominio)
4. [Arquitectura del Backend REST API](#4-arquitectura-del-backend-rest-api)
5. [Arquitectura del WebSocket Gateway](#5-arquitectura-del-websocket-gateway)
6. [Arquitectura de Frontends](#6-arquitectura-de-frontends)
7. [Patrones de Diseño Implementados](#7-patrones-de-diseño-implementados)
8. [Sistema de Seguridad](#8-sistema-de-seguridad)
9. [Aislamiento Multi-Tenant](#9-aislamiento-multi-tenant)
10. [Optimizaciones de Rendimiento](#10-optimizaciones-de-rendimiento)
11. [Flujos de Integración](#11-flujos-de-integración)
12. [Infraestructura y DevOps](#12-infraestructura-y-devops)
13. [Decisiones Arquitectónicas](#13-decisiones-arquitectónicas)

---

## 1. Visión General del Sistema

### 1.1 Propósito y Alcance

El sistema **Integrador** constituye una plataforma integral de gestión de restaurantes diseñada para orquestar la totalidad de operaciones desde el momento en que un cliente escanea un código QR hasta la finalización del pago. La arquitectura ha sido concebida con un enfoque multi-tenant que permite a múltiples restaurantes operar de forma completamente aislada sobre la misma infraestructura, maximizando la eficiencia operativa mientras garantiza la segregación absoluta de datos sensibles.

La plataforma integra cinco componentes principales que colaboran en tiempo real mediante una combinación de APIs REST para operaciones transaccionales y WebSockets para sincronización instantánea de eventos. Esta dualidad de protocolos permite alcanzar un balance óptimo entre consistencia de datos y experiencia de usuario fluida.

### 1.2 Principios Arquitectónicos Fundamentales

La arquitectura del sistema Integrador se fundamenta en cinco principios rectores que guían todas las decisiones de diseño:

**Separación de Responsabilidades (SoC)**: Cada componente del sistema tiene una responsabilidad claramente definida y acotada. El Dashboard gestiona operaciones administrativas, pwaMenu maneja la experiencia del cliente, pwaWaiter optimiza el flujo de trabajo del mesero, el REST API procesa lógica de negocio, y el WebSocket Gateway orquesta comunicación en tiempo real.

**Arquitectura Limpia (Clean Architecture)**: El backend implementa una separación estricta en capas donde los routers actúan como controladores delgados, los servicios de dominio encapsulan lógica de negocio, y los repositorios abstraen el acceso a datos. Esta estructura garantiza que los cambios en una capa no propaguen efectos colaterales a otras.

**Diseño Reactivo**: Los frontends utilizan Zustand como gestor de estado con patrones de suscripción selectiva que previenen re-renderizados innecesarios. La arquitectura de eventos del WebSocket Gateway permite que los cambios se propaguen instantáneamente a todos los clientes conectados sin polling.

**Seguridad en Profundidad**: El sistema implementa múltiples capas de seguridad incluyendo autenticación JWT con tokens de corta duración, validación de origen en WebSockets, rate limiting por endpoint, y validación de entrada para prevenir ataques de inyección.

**Escalabilidad Horizontal**: La arquitectura soporta escalado horizontal mediante sharding de locks, broadcast paralelo con batching, y pools de conexiones Redis configurables para manejar cargas de 400-600 usuarios concurrentes.

### 1.3 Stack Tecnológico

| Capa | Tecnología | Justificación |
|------|------------|---------------|
| **Frontend Dashboard** | React 19, Zustand, TailwindCSS | Hooks modernos (useActionState, useOptimistic), gestión de estado predecible |
| **Frontend pwaMenu** | React 19, Zustand, i18next, Workbox | PWA offline-first, internacionalización, service workers |
| **Frontend pwaWaiter** | React 19, Zustand, Push API | Notificaciones push nativas, funcionamiento offline |
| **REST API** | FastAPI, SQLAlchemy 2.0, Pydantic v2 | Async nativo, tipado fuerte, validación automática |
| **WebSocket Gateway** | FastAPI WebSocket, Redis Pub/Sub | Conexiones bidireccionales, escalado via Redis |
| **Base de Datos** | PostgreSQL 16 + pgvector | ACID, soporte vectorial para RAG futuro |
| **Cache/Mensajería** | Redis 7 | Pub/Sub, rate limiting, token blacklist |
| **Containerización** | Docker Compose | Orquestación local de servicios |

---

## 2. Topología de Componentes

### 2.1 Diagrama de Alto Nivel

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                              CAPA DE PRESENTACIÓN                            │
├─────────────────┬─────────────────┬─────────────────┬───────────────────────┤
│    Dashboard    │    pwaMenu      │   pwaWaiter     │      Externos         │
│   (Admin/Mgr)   │   (Clientes)    │   (Meseros)     │   (Mercado Pago)      │
│    :5177        │    :5176        │    :5178        │                       │
└────────┬────────┴────────┬────────┴────────┬────────┴───────────┬───────────┘
         │                 │                 │                     │
         │ HTTP/REST       │ HTTP/REST       │ HTTP/REST           │ Webhooks
         │ WebSocket       │ WebSocket       │ WebSocket           │
         ▼                 ▼                 ▼                     ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                              CAPA DE SERVICIOS                               │
├─────────────────────────────────┬───────────────────────────────────────────┤
│         REST API (:8000)        │        WebSocket Gateway (:8001)          │
│  ┌─────────────────────────┐    │    ┌─────────────────────────────────┐    │
│  │       Routers           │    │    │     Connection Manager          │    │
│  │  (auth, admin, diner,   │    │    │  (lifecycle, broadcast, stats)  │    │
│  │   kitchen, waiter...)   │    │    └─────────────────────────────────┘    │
│  └───────────┬─────────────┘    │    ┌─────────────────────────────────┐    │
│              │                  │    │      Redis Subscriber           │    │
│  ┌───────────▼─────────────┐    │    │  (validation, batch process)    │    │
│  │    Domain Services      │    │    └─────────────────────────────────┘    │
│  │  (CategoryService,      │◄───┼────►┌─────────────────────────────────┐   │
│  │   ProductService...)    │    │    │        Event Router             │    │
│  └───────────┬─────────────┘    │    │   (tenant filter, broadcast)    │    │
│              │                  │    └─────────────────────────────────┘    │
│  ┌───────────▼─────────────┐    │                                           │
│  │     Repositories        │    │                                           │
│  │  (TenantRepository,     │    │                                           │
│  │   BranchRepository)     │    │                                           │
│  └───────────┬─────────────┘    │                                           │
└──────────────┼──────────────────┴───────────────────────────────────────────┘
               │
┌──────────────▼──────────────────────────────────────────────────────────────┐
│                              CAPA DE DATOS                                   │
├─────────────────────────────────┬───────────────────────────────────────────┤
│     PostgreSQL (:5432)          │           Redis (:6380)                   │
│  ┌─────────────────────────┐    │    ┌─────────────────────────────────┐    │
│  │   47 Modelos SQLAlchemy │    │    │   Pub/Sub (eventos real-time)  │    │
│  │   11 Dominios           │    │    │   Token Blacklist              │    │
│  │   AuditMixin universal  │    │    │   Rate Limiting                │    │
│  └─────────────────────────┘    │    │   Session Cache                │    │
│                                 │    └─────────────────────────────────┘    │
└─────────────────────────────────┴───────────────────────────────────────────┘
```

### 2.2 Componentes y Responsabilidades

#### Dashboard (Puerto 5177)
El Dashboard constituye el centro de control administrativo del sistema. Implementado como una Single Page Application con React 19, proporciona interfaces para la gestión completa de sucursales, productos, personal, y monitoreo de operaciones en tiempo real. Los usuarios con roles ADMIN y MANAGER acceden a este componente para configurar el catálogo de productos, asignar meseros a sectores, visualizar el estado de mesas, y procesar órdenes pendientes.

La arquitectura interna del Dashboard se organiza alrededor de stores Zustand especializados: `authStore` gestiona autenticación y tokens, `branchStore` mantiene el estado de sucursales, `productStore` maneja el catálogo con paginación virtual, y `tableStore` sincroniza el estado de mesas en tiempo real via WebSocket. Cada store implementa selectores memoizados para evitar re-renderizados innecesarios, un patrón crítico para la estabilidad con React 19.

#### pwaMenu (Puerto 5176)
pwaMenu representa la interfaz principal de interacción con clientes. Como Progressive Web App, funciona tanto online como offline mediante service workers Workbox que implementan estrategias de cache diferenciadas: CacheFirst para assets estáticos y NetworkFirst para datos del menú. La aplicación soporta internacionalización completa en español, inglés y portugués mediante i18next.

El flujo de usuario comienza cuando el cliente escanea un código QR en la mesa, lo que inicia una sesión de mesa vinculada al dispositivo. Múltiples comensales pueden unirse a la misma sesión usando códigos de 4 dígitos, permitiendo ordenamiento colaborativo donde cada comensal mantiene su propio carrito pero visualiza los pedidos de todos. El sistema de confirmación grupal requiere que todos los comensales aprueben antes de enviar la ronda a cocina.

El sistema de filtrado avanzado permite a los clientes excluir productos por alérgenos (con detección de reacciones cruzadas), preferencias dietéticas (vegetariano, vegano, keto, bajo en sodio), y métodos de cocción. Estas preferencias se persisten como "preferencias implícitas" vinculadas al device_id, permitiendo que clientes recurrentes encuentren sus filtros ya aplicados.

#### pwaWaiter (Puerto 5178)
pwaWaiter optimiza el flujo de trabajo de meseros mediante una interfaz móvil diseñada para condiciones de conectividad variable. Los meseros visualizan únicamente las mesas de los sectores asignados para el día actual, reduciendo la carga cognitiva y evitando interferencias entre personal.

La funcionalidad "Comanda Rápida" permite a meseros tomar pedidos para clientes sin smartphone, utilizando menús físicos tradicionales. El mesero selecciona productos de un menú compacto (sin imágenes para optimizar rendimiento) y la orden se procesa exactamente igual que si el cliente hubiera ordenado desde pwaMenu.

El sistema de notificaciones push utiliza Web Push API para alertar a meseros cuando una ronda está lista para servir o cuando un cliente solicita atención. IndexedDB proporciona almacenamiento offline para órdenes pendientes que se sincronizan automáticamente al recuperar conectividad.

#### REST API (Puerto 8000)
El REST API constituye el núcleo de procesamiento de lógica de negocio del sistema. Implementado con FastAPI, aprovecha el soporte nativo de async/await para manejar múltiples conexiones concurrentes eficientemente. La arquitectura sigue estrictamente el patrón Clean Architecture con cuatro capas bien definidas.

Los **routers** actúan como controladores delgados que únicamente manejan concerns HTTP: parseo de parámetros, validación de schemas Pydantic, y construcción de respuestas. Toda lógica de negocio se delega a servicios de dominio.

Los **servicios de dominio** encapsulan reglas de negocio y orquestación. `CategoryService`, `ProductService`, `StaffService` y otros 8 servicios implementan operaciones CRUD enriquecidas con validaciones específicas del dominio, transformaciones de datos, y efectos secundarios como publicación de eventos.

Los **repositorios** abstraen completamente el acceso a datos. `TenantRepository` y `BranchRepository` proporcionan métodos tipados para consultas comunes con eager loading preconfigurado que previene el problema N+1. Los repositorios jamás contienen lógica de negocio.

Los **modelos** SQLAlchemy definen el esquema de base de datos con mixins para auditoría automática (created_at, updated_at, deleted_at, created_by_id, etc.).

#### WebSocket Gateway (Puerto 8001)
El WebSocket Gateway proporciona comunicación bidireccional en tiempo real entre el servidor y todos los clientes conectados. Su arquitectura modular se organiza en componentes especializados bajo el directorio `ws_gateway/components/`.

El **ConnectionManager** orquesta el ciclo de vida de conexiones utilizando composición de módulos especializados: `ConnectionLifecycle` maneja registro/desregistro, `ConnectionBroadcaster` implementa envío paralelo con batching, `ConnectionCleanup` elimina conexiones muertas, y `ConnectionStats` agrega métricas.

El **RedisSubscriber** procesa eventos del canal Pub/Sub de Redis. `EventDropRateTracker` monitorea tasas de descarte para alertar sobre sobrecarga, `validate_event_schema` valida estructura de eventos, y `process_event_batch` maneja eventos en lotes para eficiencia.

El **BroadcastRouter** implementa Strategy Pattern para routing configurable de mensajes. El patrón Observer permite registrar observadores de métricas sin acoplar la lógica de broadcast.

Los **endpoints** WebSocket (`WaiterEndpoint`, `KitchenEndpoint`, `AdminEndpoint`, `DinerEndpoint`) heredan de clases base con mixins para validación de mensajes, heartbeat, y revalidación periódica de JWT.

---

## 3. Modelo de Datos y Dominio

### 3.1 Organización por Dominios

El sistema define 47 modelos SQLAlchemy organizados en 11 dominios coherentes, cada uno encapsulado en su propio archivo dentro de `rest_api/models/`:

```
rest_api/models/
├── __init__.py          # Re-exporta los 47 modelos
├── base.py              # Base declarativa, AuditMixin
├── tenant.py            # Tenant, Branch (2 modelos)
├── user.py              # User, UserBranchRole (2 modelos)
├── catalog.py           # Category, Subcategory, Product, BranchProduct (4 modelos)
├── allergen.py          # Allergen, ProductAllergen, AllergenCrossReaction (3 modelos)
├── ingredient.py        # IngredientGroup, Ingredient, SubIngredient, ProductIngredient (4 modelos)
├── product_profile.py   # 12 modelos de perfiles dietéticos/cocción/sabor
├── sector.py            # BranchSector, WaiterSectorAssignment (2 modelos)
├── table.py             # Table, TableSession (2 modelos)
├── customer.py          # Customer, Diner (2 modelos)
├── order.py             # Round, RoundItem (2 modelos)
├── kitchen.py           # KitchenTicket, KitchenTicketItem, ServiceCall (3 modelos)
├── billing.py           # Check, Payment, Charge, Allocation (4 modelos)
├── knowledge.py         # KnowledgeDocument, ChatLog (2 modelos para RAG)
├── promotion.py         # Promotion, PromotionBranch, PromotionItem (3 modelos)
├── exclusion.py         # BranchCategoryExclusion, BranchSubcategoryExclusion (2 modelos)
├── audit.py             # AuditLog (1 modelo)
└── recipe.py            # Recipe, RecipeAllergen (2 modelos)
```

### 3.2 Jerarquía de Entidades Principal

```
Tenant (Restaurante)
│
├── Branch (Sucursal) [1:N]
│   │
│   ├── Category (Categoría) [1:N]
│   │   └── Subcategory (Subcategoría) [1:N]
│   │       └── Product (Producto) [1:N]
│   │           ├── BranchProduct (Precio por sucursal) [1:N]
│   │           ├── ProductAllergen (Alérgenos) [M:N]
│   │           └── ProductIngredient (Ingredientes) [M:N]
│   │
│   ├── BranchSector (Sector) [1:N]
│   │   ├── Table (Mesa) [1:N]
│   │   │   └── TableSession (Sesión activa) [0:1]
│   │   │       └── Diner (Comensal) [1:N]
│   │   │           └── Round (Ronda) [1:N]
│   │   │               └── RoundItem (Ítem de ronda) [1:N]
│   │   │                   └── KitchenTicket (Ticket cocina) [1:N]
│   │   │
│   │   └── WaiterSectorAssignment (Asignación diaria) [1:N]
│   │
│   ├── Check (Cuenta) [1:N por sesión]
│   │   ├── Charge (Cargo) [1:N]
│   │   ├── Payment (Pago) [1:N]
│   │   └── Allocation (Asignación FIFO) [1:N]
│   │
│   └── ServiceCall (Llamada de servicio) [1:N]
│
└── User (Usuario) [M:N via UserBranchRole]
    └── UserBranchRole (Rol por sucursal)
        roles: ADMIN | MANAGER | KITCHEN | WAITER
```

### 3.3 AuditMixin Universal

Todos los modelos heredan de `AuditMixin`, proporcionando trazabilidad completa:

```python
class AuditMixin:
    # Soft delete
    is_active: bool = True  # Indexado para filtrado eficiente
    deleted_at: datetime | None = None
    deleted_by_id: int | None = None
    deleted_by_email: str | None = None

    # Timestamps automáticos
    created_at: datetime  # auto-set on insert
    updated_at: datetime  # auto-set on update

    # Trazabilidad de usuario
    created_by_id: int | None = None
    created_by_email: str | None = None
    updated_by_id: int | None = None
    updated_by_email: str | None = None
```

Este diseño permite:
- **Soft delete universal**: Ningún dato se elimina físicamente; se marca `is_active=False`
- **Auditoría completa**: Quién creó, modificó o eliminó cada registro y cuándo
- **Restauración**: Entidades eliminadas pueden restaurarse con cascade a sus dependientes

### 3.4 Relaciones Clave

**Productos y Precios por Sucursal**:
```
Product (maestro global)
    └── BranchProduct (precio específico por sucursal)
        - branch_id: FK → Branch
        - price_cents: int (12550 = $125.50)
        - is_available: bool
```

**Sistema de Alérgenos con Reacciones Cruzadas**:
```
Allergen
    ├── ProductAllergen (presencia en producto)
    │   - presence_type: CONTAINS | MAY_CONTAIN | TRACE
    │   - risk_level: HIGH | MEDIUM | LOW
    │
    └── AllergenCrossReaction (auto-referencial M:N)
        - allergen_id → Allergen
        - cross_reacts_with_id → Allergen
        - severity: HIGH | MEDIUM | LOW
```

**Flujo de Órdenes**:
```
TableSession (sesión de mesa activa)
    └── Diner (comensal identificado por device_id)
        └── Round (ronda de pedidos)
            └── RoundItem (producto + cantidad + modificaciones)
                └── KitchenTicket (agrupación para cocina)
                    └── KitchenTicketItem (ítem individual)
```

---

## 4. Arquitectura del Backend REST API

### 4.1 Clean Architecture en Detalle

La implementación de Clean Architecture en el backend garantiza que las dependencias fluyen únicamente hacia adentro, desde capas externas hacia el núcleo de dominio:

```
┌─────────────────────────────────────────────────────────────────┐
│                         ROUTERS                                  │
│   • Parsing de requests HTTP                                     │
│   • Validación de schemas Pydantic                               │
│   • Manejo de autenticación (current_user dependency)            │
│   • Construcción de responses                                    │
│   • NUNCA contienen lógica de negocio                            │
└─────────────────────────────┬───────────────────────────────────┘
                              │ Delega a
┌─────────────────────────────▼───────────────────────────────────┐
│                     DOMAIN SERVICES                              │
│   • CategoryService, ProductService, StaffService...             │
│   • Encapsulan TODA la lógica de negocio                         │
│   • Validaciones de dominio (_validate_create, _validate_update) │
│   • Orquestación de operaciones complejas                        │
│   • Transformación entidad → output schema                       │
│   • Publicación de eventos de dominio                            │
└─────────────────────────────┬───────────────────────────────────┘
                              │ Usa
┌─────────────────────────────▼───────────────────────────────────┐
│                      REPOSITORIES                                │
│   • TenantRepository, BranchRepository                           │
│   • Acceso a datos ÚNICAMENTE                                    │
│   • Eager loading preconfigurado (selectinload, joinedload)      │
│   • Filtrado automático por tenant_id / branch_id                │
│   • Métodos tipados: find_by_id, find_all, find_by_branch        │
│   • NUNCA contienen lógica de negocio                            │
└─────────────────────────────┬───────────────────────────────────┘
                              │ Opera sobre
┌─────────────────────────────▼───────────────────────────────────┐
│                        MODELS                                    │
│   • Entidades SQLAlchemy                                         │
│   • Definición de schema de base de datos                        │
│   • Relaciones y constraints                                     │
│   • AuditMixin para trazabilidad                                 │
└─────────────────────────────────────────────────────────────────┘
```

### 4.2 Servicios de Dominio

El sistema implementa 11 servicios de dominio que heredan de clases base especializadas:

```python
# Clase base para entidades con scope de tenant
class BaseCRUDService[Model, Output](ABC):
    def __init__(self, db: Session, model: type[Model], output_schema: type[Output], entity_name: str):
        self._db = db
        self._repo = TenantRepository(model, db)
        self._output_schema = output_schema
        self._entity_name = entity_name

    # Template Method: hooks para validación personalizada
    def _validate_create(self, data: dict, tenant_id: int) -> None: ...
    def _validate_update(self, entity: Model, data: dict) -> None: ...
    def _after_create(self, entity: Model, user_id: int, user_email: str) -> None: ...
    def _after_delete(self, entity_info: dict, user_id: int, user_email: str) -> None: ...

# Clase base para entidades con scope de branch
class BranchScopedService[Model, Output](BaseCRUDService[Model, Output]):
    def __init__(self, ...):
        super().__init__(...)
        self._branch_repo = BranchRepository(model, db)

    def list_by_branch(self, tenant_id: int, branch_id: int) -> list[Output]: ...
```

**Servicios Implementados**:

| Servicio | Entidad | Características Especiales |
|----------|---------|----------------------------|
| `CategoryService` | Category | Validación de unicidad de nombre por branch |
| `SubcategoryService` | Subcategory | Validación de categoría padre existe |
| `ProductService` | Product | Gestión de BranchProduct, alérgenos, ingredientes |
| `AllergenService` | Allergen | Manejo de reacciones cruzadas M:N |
| `BranchService` | Branch | Gestión de configuración de sucursal |
| `SectorService` | BranchSector | Validación de branch_id |
| `TableService` | Table | Generación de códigos únicos |
| `StaffService` | User + UserBranchRole | Restricciones MANAGER, multi-branch roles |
| `PromotionService` | Promotion | Branches e items asociados |
| `AssignmentService` | WaiterSectorAssignment | Asignaciones diarias de sectores |
| `ExclusionService` | BranchCategoryExclusion | Exclusiones de catálogo por branch |

### 4.3 Sistema de Permisos (Strategy Pattern)

El sistema de permisos utiliza Strategy Pattern con Interface Segregation Principle para manejar las diferencias entre roles:

```python
# Contexto de permisos (Facade para estrategias)
class PermissionContext:
    def __init__(self, user: dict):
        self._user = user
        self._strategy = get_highest_privilege_strategy(user["roles"])

    @property
    def is_admin(self) -> bool: ...
    @property
    def is_management(self) -> bool: ...  # ADMIN or MANAGER
    @property
    def tenant_id(self) -> int: ...
    @property
    def branch_ids(self) -> list[int]: ...

    def require_management(self) -> None:
        """Raise ForbiddenError if not ADMIN/MANAGER."""

    def require_branch_access(self, branch_id: int) -> None:
        """Raise ForbiddenError if no access to branch."""

    def can(self, action: Action, entity_type: str, **context) -> bool:
        """Delegate to strategy for fine-grained permission check."""

# Estrategia para rol ADMIN (acceso total)
class AdminStrategy(PermissionStrategy):
    def can_create(self, user, entity_type, **ctx) -> bool: return True
    def can_read(self, user, entity) -> bool: return True
    def can_update(self, user, entity) -> bool: return True
    def can_delete(self, user, entity) -> bool: return True
    def filter_query(self, query, user) -> Query: return query  # Sin filtrado

# Estrategia para rol KITCHEN (solo lectura + actualización de tickets)
class KitchenStrategy(NoCreateMixin, NoDeleteMixin, BranchFilterMixin, PermissionStrategy):
    READABLE_ENTITIES = frozenset({"Round", "KitchenTicket", "Product", ...})
    UPDATABLE_ENTITIES = frozenset({"Round", "KitchenTicket"})

    def can_read(self, user, entity) -> bool:
        if type(entity).__name__ not in self.READABLE_ENTITIES:
            return False
        return self._user_has_branch_access(user, entity.branch_id)
```

**Mixins Disponibles**:
- `NoCreateMixin`: Retorna False para can_create()
- `NoDeleteMixin`: Retorna False para can_delete()
- `NoUpdateMixin`: Retorna False para can_update()
- `BranchFilterMixin`: Filtra queries por branch_ids del usuario
- `BranchAccessMixin`: Helpers para validar acceso a branches

### 4.4 Estructura de Routers

Los routers se organizan por dominio de responsabilidad:

```
rest_api/routers/
├── _common/              # Utilidades compartidas
│   ├── base.py           # Dependencias comunes, helpers
│   └── pagination.py     # Paginación estandarizada
├── admin/                # CRUD administrativo (15 routers)
│   ├── __init__.py       # Monta todos los sub-routers
│   ├── _base.py          # Dependencias admin comunes
│   ├── products.py       # GET/POST/PUT/DELETE /api/admin/products
│   ├── categories.py     # Categorías
│   ├── staff.py          # Personal
│   └── ...               # 12 routers más
├── auth/                 # Autenticación
│   └── auth.py           # login, logout, refresh, /me
├── billing/              # Pagos
│   └── billing.py        # checks, payments, Mercado Pago webhooks
├── content/              # Contenido público
│   ├── catalogs.py       # Catálogo completo para pwaMenu
│   ├── ingredients.py    # Ingredientes
│   ├── promotions.py     # Promociones activas
│   ├── rag.py            # Chatbot RAG
│   └── recipes.py        # Recetas/fichas técnicas
├── diner/                # Operaciones de comensal
│   ├── orders.py         # Envío de rondas
│   └── customer.py       # Fidelización
├── kitchen/              # Operaciones de cocina
│   ├── rounds.py         # Estado de rondas
│   └── tickets.py        # Tickets de cocina
├── public/               # Sin autenticación
│   ├── catalog.py        # Menú público por slug
│   └── health.py         # Health checks
├── tables/               # Gestión de mesas
│   └── sessions.py       # Crear/obtener sesiones
└── waiter/               # Operaciones de mesero
    ├── tables.py         # Mesas por sector asignado
    └── menu.py           # Menú compacto para Comanda Rápida
```

---

## 5. Arquitectura del WebSocket Gateway

### 5.1 Arquitectura Modular

El WebSocket Gateway implementa una arquitectura modular que reduce la complejidad mediante composición de componentes especializados:

```
ws_gateway/
├── main.py                    # App FastAPI, endpoints, /ws/metrics
├── connection_manager.py      # Orquestador delgado (compose core/connection/)
├── redis_subscriber.py        # Orquestador delgado (compose core/subscriber/)
│
├── core/                      # Módulos extraídos para mantenibilidad
│   ├── connection/            # Extraído de connection_manager.py (987→463 líneas)
│   │   ├── lifecycle.py       # ConnectionLifecycle: connect/disconnect
│   │   ├── broadcaster.py     # ConnectionBroadcaster: send/broadcast
│   │   ├── cleanup.py         # ConnectionCleanup: limpieza de conexiones
│   │   └── stats.py           # ConnectionStats: agregación de métricas
│   │
│   └── subscriber/            # Extraído de redis_subscriber.py (666→326 líneas)
│       ├── drop_tracker.py    # EventDropRateTracker: alertas de descarte
│       ├── validator.py       # Validación de schema de eventos
│       └── processor.py       # Procesamiento batch de eventos
│
└── components/                # Arquitectura modular por responsabilidad
    ├── __init__.py            # Re-exports para backward compatibility
    │
    ├── core/                  # Fundacionales
    │   ├── constants.py       # WSCloseCode, WSConstants
    │   ├── context.py         # WebSocketContext para logging
    │   └── dependencies.py    # Contenedor DI (singletons)
    │
    ├── connection/            # Gestión de conexiones
    │   ├── index.py           # ConnectionIndex (índices + mappings)
    │   ├── locks.py           # LockManager (locks sharded)
    │   ├── lock_sequence.py   # LockSequence (prevención deadlock)
    │   ├── heartbeat.py       # HeartbeatTracker
    │   └── rate_limiter.py    # WebSocketRateLimiter
    │
    ├── events/                # Manejo de eventos
    │   ├── types.py           # WebSocketEvent, EventType
    │   └── router.py          # EventRouter (validación + routing)
    │
    ├── broadcast/             # Broadcasting
    │   ├── router.py          # BroadcastRouter (Strategy + Observer)
    │   └── tenant_filter.py   # TenantFilter (aislamiento multi-tenant)
    │
    ├── auth/                  # Autenticación
    │   └── strategies.py      # JWT, TableToken, Composite strategies
    │
    ├── endpoints/             # Endpoints WebSocket
    │   ├── base.py            # WebSocketEndpointBase, JWTWebSocketEndpoint
    │   ├── mixins.py          # Mixins SRP (validation, heartbeat, etc.)
    │   └── handlers.py        # Waiter, Kitchen, Admin, Diner endpoints
    │
    ├── resilience/            # Tolerancia a fallos
    │   ├── circuit_breaker.py # CircuitBreaker para Redis
    │   └── retry.py           # RetryConfig con jitter
    │
    ├── metrics/               # Observabilidad
    │   ├── collector.py       # MetricsCollector
    │   └── prometheus.py      # PrometheusFormatter
    │
    └── data/                  # Acceso a datos
        └── sector_repository.py # SectorAssignmentRepository + cache TTL
```

### 5.2 Componentes Clave

**ConnectionIndex** (Value Object):
Mantiene todos los índices de conexiones y mappings inversos en una estructura coherente:
```python
class ConnectionIndex:
    _by_branch: dict[int, set[WebSocket]]      # branch_id → conexiones
    _by_user: dict[int, set[WebSocket]]        # user_id → conexiones
    _by_session: dict[int, set[WebSocket]]     # session_id → conexiones
    _ws_to_context: dict[WebSocket, dict]      # conexión → metadata

    def add(self, ws: WebSocket, context: dict) -> None: ...
    def remove(self, ws: WebSocket) -> dict | None: ...
    def get_by_branch(self, branch_id: int) -> set[WebSocket]: ...
```

**LockManager** (Sharded Locks):
Implementa locks por granularidad para reducir contención:
```python
class LockManager:
    _global_lock: asyncio.Lock          # Operaciones cross-cutting
    _branch_locks: dict[int, asyncio.Lock]  # Por branch
    _user_locks: dict[int, asyncio.Lock]    # Por usuario

    async def get_branch_lock(self, branch_id: int) -> asyncio.Lock:
        """Retorna lock específico para branch, creándolo si no existe."""
```

**BroadcastRouter** (Strategy + Observer):
Configura estrategias de broadcast y notifica observadores:
```python
class BroadcastRouter:
    _strategy: BroadcastStrategy  # BATCH o ADAPTIVE
    _observers: list[BroadcastObserver]

    async def broadcast(self, connections: set[WebSocket], payload: dict) -> BroadcastResult:
        result = await self._strategy.execute(connections, payload)
        for observer in self._observers:
            observer.on_broadcast_complete(result.sent, result.failed, payload.get("type"))
        return result
```

**WebSocketEndpointBase** (Template Method):
Clase base abstracta que define el ciclo de vida de un endpoint:
```python
class WebSocketEndpointBase(ABC):
    async def run(self) -> None:
        """Template method que orquesta el ciclo de vida completo."""
        try:
            auth_data = await self._authenticate()
            if not auth_data:
                return
            context = await self.create_context(auth_data)
            await self.register_connection(context)
            await self._message_loop(context)
        finally:
            await self.unregister_connection(context)

    @abstractmethod
    async def create_context(self, auth_data: dict) -> dict: ...
    @abstractmethod
    async def register_connection(self, context: dict) -> None: ...
    @abstractmethod
    async def handle_message(self, data: dict) -> None: ...
```

### 5.3 Eventos WebSocket

**Tipos de Eventos**:
```python
# Ciclo de vida de rondas
ROUND_SUBMITTED      # Nueva ronda enviada (→ admin, waiters)
ROUND_IN_KITCHEN     # Ronda enviada a cocina (→ kitchen)
ROUND_READY          # Ronda lista (→ waiters)
ROUND_SERVED         # Ronda servida (→ diners)
ROUND_CANCELED       # Ronda cancelada (→ all)

# Llamadas de servicio
SERVICE_CALL_CREATED # Cliente solicita atención (→ waiters)
SERVICE_CALL_ACKED   # Mesero reconoce llamada (→ diners)
SERVICE_CALL_CLOSED  # Llamada completada (→ all)

# Facturación
CHECK_REQUESTED      # Cuenta solicitada (→ waiters, admin)
CHECK_PAID           # Cuenta pagada (→ all)
PAYMENT_APPROVED     # Pago aprobado (→ diners)
PAYMENT_REJECTED     # Pago rechazado (→ diners)
PAYMENT_FAILED       # Error de pago (→ diners)

# Mesas
TABLE_SESSION_STARTED # QR escaneado (→ admin, waiters)
TABLE_CLEARED        # Mesa liberada (→ admin)
TABLE_STATUS_CHANGED # Cambio de estado (→ admin)

# Tickets de cocina
TICKET_IN_PROGRESS   # Ticket en preparación (→ kitchen)
TICKET_READY         # Ticket listo (→ waiters)
TICKET_DELIVERED     # Ticket entregado (→ kitchen)

# CRUD Admin
ENTITY_CREATED       # Entidad creada (→ admin)
ENTITY_UPDATED       # Entidad actualizada (→ admin, potentially others)
ENTITY_DELETED       # Entidad eliminada (→ admin)
CASCADE_DELETE       # Eliminación en cascada (→ admin)
```

**Routing por Sector**:
Los eventos con `sector_id` se envían únicamente a meseros asignados a ese sector para el día actual:
```python
async def send_to_waiters(self, branch_id: int, payload: dict, sector_id: int | None = None):
    if sector_id:
        # Solo meseros asignados a este sector
        assigned_user_ids = await self._sector_repo.get_assigned_waiters(sector_id)
        connections = self._filter_by_users(branch_connections, assigned_user_ids)
    else:
        # Todos los meseros del branch
        connections = self._get_waiter_connections(branch_id)

    # ADMIN/MANAGER siempre reciben todos los eventos
    connections |= self._get_management_connections(branch_id)

    await self._broadcaster.broadcast(connections, payload)
```

### 5.4 Resiliencia

**Circuit Breaker** para conexión Redis:
```python
class CircuitBreaker:
    _state: CircuitState  # CLOSED | OPEN | HALF_OPEN
    _failure_count: int
    _failure_threshold: int = 5
    _recovery_timeout: float = 30.0

    def record_failure(self, exception: Exception) -> None:
        with self._lock:
            self._failure_count += 1
            if self._failure_count >= self._failure_threshold:
                self._transition_to(CircuitState.OPEN)

    def record_success(self) -> None:
        with self._lock:
            if self._state == CircuitState.HALF_OPEN:
                self._transition_to(CircuitState.CLOSED)
            self._failure_count = 0

    def should_allow_request(self) -> bool:
        if self._state == CircuitState.CLOSED:
            return True
        if self._state == CircuitState.OPEN:
            if time.time() - self._opened_at > self._recovery_timeout:
                self._transition_to(CircuitState.HALF_OPEN)
                return True
            return False
        return True  # HALF_OPEN allows one request
```

**Retry con Jitter Decorrelacionado**:
Previene thundering herd en reconexiones:
```python
def calculate_delay_with_jitter(attempt: int, config: RetryConfig) -> float:
    """Calcula delay con jitter decorrelacionado."""
    base_delay = config.base_delay * (2 ** attempt)
    capped_delay = min(base_delay, config.max_delay)
    # Jitter decorrelacionado: random entre base y capped
    return random.uniform(config.base_delay, capped_delay)
```

---

## 6. Arquitectura de Frontends

### 6.1 Patrón Zustand Crítico (React 19)

Todos los frontends implementan un patrón estricto de Zustand para evitar loops infinitos de re-renderizado causados por la detección de cambios más agresiva de React 19:

```typescript
// ❌ INCORRECTO: Destructuring causa loops infinitos
const { items, addItem } = useStore()

// ✅ CORRECTO: Selectores individuales
const items = useStore(selectItems)
const addItem = useStore((s) => s.addItem)

// ✅ CRÍTICO: Referencias estables para arrays fallback
const EMPTY_ARRAY: Product[] = []
export const selectProducts = (state: State) =>
  state.products ?? EMPTY_ARRAY

// ✅ CRÍTICO: Memoización para selectores filtrados
const pendingCache = { tables: null as Table[] | null, result: [] as Table[] }
export const selectTablesWithPendingRounds = (state: TablesState) => {
  if (state.tables === pendingCache.tables) {
    return pendingCache.result
  }
  const filtered = state.tables.filter((t) => t.open_rounds > 0)
  pendingCache.tables = state.tables
  pendingCache.result = filtered.length > 0 ? filtered : EMPTY_TABLES
  return pendingCache.result
}

// ✅ useShallow para objetos (no para arrays)
import { useShallow } from 'zustand/react/shallow'
const { user, isLoggedIn } = useStore(useShallow((s) => ({
  user: s.user,
  isLoggedIn: s.isLoggedIn
})))
```

### 6.2 Estructura del Dashboard

```
Dashboard/src/
├── components/           # Componentes UI
│   ├── layout/           # Header, Sidebar, Layout
│   ├── tables/           # TableGrid, TableSessionModal
│   ├── products/         # ProductForm, ProductList
│   └── common/           # Button, Modal, Input
│
├── pages/                # Páginas/rutas
│   ├── Login.tsx
│   ├── Branches.tsx
│   ├── Tables.tsx
│   ├── Products.tsx
│   └── Staff.tsx
│
├── stores/               # Estado Zustand
│   ├── authStore.ts      # Autenticación + refresh token
│   ├── branchStore.ts    # Sucursales seleccionada
│   ├── productStore.ts   # Catálogo con paginación
│   └── tableStore.ts     # Mesas + WebSocket sync
│
├── services/
│   └── api.ts            # Cliente Axios con interceptors
│
├── hooks/
│   ├── useWebSocket.ts   # Conexión y reconexión WS
│   └── usePermissions.ts # Hook de permisos por rol
│
└── utils/
    ├── logger.ts         # Logger centralizado
    └── formatters.ts     # Formateo de precios, fechas
```

### 6.3 Estructura de pwaMenu

```
pwaMenu/src/
├── components/
│   ├── menu/             # ProductCard, CategoryTabs
│   ├── cart/             # CartDrawer, CartItem, RoundConfirmationPanel
│   ├── filters/          # AllergenFilter, DietaryFilter, CookingFilter
│   └── customer/         # OptInModal, WelcomeBackBanner
│
├── pages/
│   ├── Home.tsx          # Landing con QR scan
│   ├── Menu.tsx          # Menú con filtros
│   ├── Cart.tsx          # Carrito del comensal
│   └── Session.tsx       # Estado de sesión/mesa
│
├── stores/
│   ├── menuStore.ts      # Productos, categorías, filtros
│   ├── cartStore.ts      # Carrito local del comensal
│   ├── tableStore.ts     # Sesión de mesa, diners, rounds
│   └── filterStore.ts    # Estado de filtros activos
│
├── hooks/
│   ├── useAllergenFilter.ts    # Filtrado por alérgenos + cross-reactions
│   ├── useDietaryFilter.ts     # Filtrado dietético
│   ├── useCookingMethodFilter.ts # Filtrado por método de cocción
│   ├── useImplicitPreferences.ts # Sync de preferencias al backend
│   └── useCustomerRecognition.ts # Detección de cliente recurrente
│
├── services/
│   ├── api.ts            # Cliente API con X-Table-Token
│   └── websocket.ts      # WebSocket para diner
│
├── i18n/
│   ├── es.json           # Español
│   ├── en.json           # Inglés
│   └── pt.json           # Portugués
│
└── utils/
    ├── deviceId.ts       # Generación y persistencia de device UUID
    └── serviceWorker.ts  # Registro de Workbox SW
```

### 6.4 Estructura de pwaWaiter

```
pwaWaiter/src/
├── components/
│   ├── tables/           # TableCard, TableGrid
│   ├── orders/           # RoundCard, RoundItemList
│   └── comanda/          # ComandaTab, CompactProductList
│
├── pages/
│   ├── Login.tsx
│   ├── BranchSelect.tsx  # Selección de sucursal
│   ├── Tables.tsx        # Lista de mesas asignadas
│   └── TableDetail.tsx   # Detalle + Comanda Rápida
│
├── stores/
│   ├── authStore.ts      # Auth + refresh proactivo (14min)
│   └── tablesStore.ts    # Mesas del sector asignado
│
├── services/
│   ├── api.ts            # Cliente API con JWT
│   ├── websocket.ts      # WebSocket waiter
│   └── notifications.ts  # Push notifications + service worker
│
└── hooks/
    └── useSectorTables.ts # Filtrado por sector asignado
```

### 6.5 Patrón WebSocket en Frontends

```typescript
// Patrón ref para evitar acumulación de listeners
const handleEventRef = useRef(handleEvent)
useEffect(() => { handleEventRef.current = handleEvent })

useEffect(() => {
  // Suscripción única con ref
  const unsubscribe = ws.on('*', (e) => handleEventRef.current(e))
  return () => unsubscribe()
}, [])  // Deps vacías - suscribir una sola vez

// Reconexión automática con backoff exponencial
useEffect(() => {
  let retryCount = 0
  const maxRetries = 5

  const connect = () => {
    ws.connect()
      .catch(() => {
        if (retryCount < maxRetries) {
          const delay = Math.min(1000 * (2 ** retryCount), 30000)
          retryCount++
          setTimeout(connect, delay)
        }
      })
  }

  connect()
  return () => ws.disconnect()
}, [])
```

---

## 7. Patrones de Diseño Implementados

### 7.1 Catálogo de Patrones

| Patrón | Ubicación | Propósito |
|--------|-----------|-----------|
| **Strategy** | `permissions/strategies.py` | Comportamiento de permisos por rol |
| **Template Method** | `base_service.py` | Hooks de validación en servicios CRUD |
| **Repository** | `crud/repository.py` | Abstracción de acceso a datos |
| **Factory** | `crud/factory.py` (deprecated) | Creación de operaciones CRUD |
| **Observer** | `broadcast/router.py` | Notificación de métricas en broadcast |
| **Composite** | `auth/strategies.py` | Autenticación combinada JWT+TableToken |
| **Facade** | `PermissionContext` | Interfaz simplificada para permisos |
| **Value Object** | `WebSocketEvent` | Inmutabilidad de eventos |
| **Mixin** | `endpoints/mixins.py` | Composición de comportamientos en endpoints |
| **Circuit Breaker** | `resilience/circuit_breaker.py` | Protección ante fallos de Redis |
| **Retry with Jitter** | `resilience/retry.py` | Reconexiones sin thundering herd |

### 7.2 Strategy Pattern - Sistema de Permisos

```python
# Protocolo base
class PermissionStrategy(Protocol):
    def can_create(self, user: dict, entity_type: str, **ctx) -> bool: ...
    def can_read(self, user: dict, entity: Any) -> bool: ...
    def can_update(self, user: dict, entity: Any) -> bool: ...
    def can_delete(self, user: dict, entity: Any) -> bool: ...
    def filter_query(self, query: Query, user: dict) -> Query: ...

# Estrategia ADMIN
class AdminStrategy(PermissionStrategy):
    """Acceso total a todo."""
    def can_create(self, user, entity_type, **ctx) -> bool: return True
    def can_read(self, user, entity) -> bool: return True
    def can_update(self, user, entity) -> bool: return True
    def can_delete(self, user, entity) -> bool: return True
    def filter_query(self, query, user) -> Query: return query

# Estrategia MANAGER (con restricciones de branch)
class ManagerStrategy(BranchFilterMixin, BranchAccessMixin, PermissionStrategy):
    CREATABLE = frozenset({"Staff", "Table", "Allergen", "Promotion"})

    def can_create(self, user, entity_type, **ctx) -> bool:
        if entity_type not in self.CREATABLE:
            return False
        branch_id = ctx.get("branch_id")
        return branch_id in user.get("branch_ids", [])

# Selección de estrategia
def get_highest_privilege_strategy(roles: list[str]) -> PermissionStrategy:
    if Roles.ADMIN in roles:
        return AdminStrategy()
    if Roles.MANAGER in roles:
        return ManagerStrategy()
    if Roles.KITCHEN in roles:
        return KitchenStrategy()
    if Roles.WAITER in roles:
        return WaiterStrategy()
    return NullStrategy()  # Sin permisos
```

### 7.3 Template Method - Servicios de Dominio

```python
class BaseCRUDService[Model, Output]:
    def create(self, data: dict, tenant_id: int, user_id: int, user_email: str) -> Output:
        """Template method con hooks de extensión."""
        # Hook 1: Validación pre-creación
        self._validate_create(data, tenant_id)

        # Lógica común
        entity = self._model(**data, tenant_id=tenant_id)
        set_created_by(entity, user_id, user_email)
        self._db.add(entity)
        safe_commit(self._db)

        # Hook 2: Acciones post-creación
        self._after_create(entity, user_id, user_email)

        return self.to_output(entity)

    # Hooks para sobreescribir en subclases
    def _validate_create(self, data: dict, tenant_id: int) -> None:
        """Override para validaciones específicas."""
        pass

    def _after_create(self, entity: Model, user_id: int, user_email: str) -> None:
        """Override para side effects (eventos, notificaciones)."""
        pass

# Uso en servicio concreto
class ProductService(BranchScopedService[Product, ProductOutput]):
    def _validate_create(self, data: dict, tenant_id: int) -> None:
        if not data.get("name"):
            raise ValidationError("El nombre es requerido", field="name")
        if data.get("price_cents", 0) < 0:
            raise ValidationError("El precio no puede ser negativo", field="price_cents")

    def _after_create(self, entity: Product, user_id: int, user_email: str) -> None:
        publish_event(
            EventType.ENTITY_CREATED,
            entity_type="Product",
            entity_id=entity.id,
            tenant_id=entity.tenant_id
        )
```

### 7.4 Observer Pattern - Broadcast Metrics

```python
class BroadcastObserver(Protocol):
    def on_broadcast_complete(self, sent: int, failed: int, context: str) -> None: ...
    def on_broadcast_rate_limited(self, context: str) -> None: ...

class MetricsObserverAdapter(BroadcastObserver):
    """Adapter que conecta Observer con MetricsCollector."""
    def __init__(self, metrics: MetricsCollector):
        self._metrics = metrics

    def on_broadcast_complete(self, sent: int, failed: int, context: str) -> None:
        self._metrics.record_broadcast(sent, failed)

    def on_broadcast_rate_limited(self, context: str) -> None:
        self._metrics.increment_rate_limited()

class BroadcastRouter:
    def __init__(self):
        self._observers: list[BroadcastObserver] = []

    def add_observer(self, observer: BroadcastObserver) -> None:
        self._observers.append(observer)

    async def broadcast(self, connections: set[WebSocket], payload: dict) -> BroadcastResult:
        result = await self._execute_broadcast(connections, payload)

        # Notificar a todos los observadores
        for observer in self._observers:
            observer.on_broadcast_complete(result.sent, result.failed, payload.get("type", ""))

        return result
```

---

## 8. Sistema de Seguridad

### 8.1 Autenticación

**JWT para Usuarios (Dashboard, pwaWaiter)**:
```python
# Lifetimes configurados en settings.py
ACCESS_TOKEN_EXPIRE_MINUTES = 15      # Token corto para reducir exposición
REFRESH_TOKEN_EXPIRE_DAYS = 7         # Refresh de mayor duración

# Payload del token
{
    "sub": "123",                       # user_id como string
    "email": "user@example.com",
    "tenant_id": 1,
    "branch_ids": [1, 2, 3],
    "roles": ["ADMIN", "MANAGER"],
    "exp": 1706000000,
    "jti": "unique-token-id"            # Para blacklisting
}

# Verificación en dependencia
async def current_user(
    authorization: str = Header(...),
    db: Session = Depends(get_db)
) -> dict:
    token = authorization.replace("Bearer ", "")
    payload = verify_jwt(token)

    # Verificar blacklist (fail-closed)
    if await is_token_blacklisted(payload["jti"]):
        raise HTTPException(401, "Token revocado")

    return payload
```

**Table Token para Comensales (pwaMenu)**:
```python
# Token HMAC de corta duración (3 horas)
TABLE_TOKEN_EXPIRE_HOURS = 3

# Generación
def create_table_token(session_id: int, table_id: int, tenant_id: int) -> str:
    payload = {
        "session_id": session_id,
        "table_id": table_id,
        "tenant_id": tenant_id,
        "exp": datetime.utcnow() + timedelta(hours=TABLE_TOKEN_EXPIRE_HOURS)
    }
    return hmac.new(
        settings.TABLE_TOKEN_SECRET.encode(),
        json.dumps(payload).encode(),
        hashlib.sha256
    ).hexdigest() + "." + base64.b64encode(json.dumps(payload).encode()).decode()

# Verificación via header X-Table-Token
async def current_table_session(
    x_table_token: str = Header(...),
    db: Session = Depends(get_db)
) -> TableSession:
    payload = verify_table_token(x_table_token)
    session = db.scalar(
        select(TableSession).where(TableSession.id == payload["session_id"])
    )
    if not session or not session.is_active:
        raise HTTPException(401, "Sesión inválida")
    return session
```

### 8.2 Token Blacklist

```python
# Revocación en logout
async def revoke_all_user_tokens(user_id: int) -> None:
    """Revoca TODOS los tokens del usuario (logout global)."""
    redis = await get_redis_pool()

    # Obtener JTIs activos del usuario
    active_jtis = await redis.smembers(f"user_tokens:{user_id}")

    for jti in active_jtis:
        # Agregar a blacklist con TTL igual a expiración del token
        await redis.setex(
            f"token_blacklist:{jti}",
            settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60,
            "revoked"
        )

    # Limpiar set de tokens activos
    await redis.delete(f"user_tokens:{user_id}")

# Verificación fail-closed
async def is_token_blacklisted(jti: str) -> bool:
    try:
        redis = await get_redis_pool()
        return await redis.exists(f"token_blacklist:{jti}") > 0
    except Exception:
        logger.error("Redis error - failing closed")
        return True  # Tratar como blacklisted ante errores
```

### 8.3 Middlewares de Seguridad

```python
# rest_api/core/middlewares.py

# 1. Security Headers Middleware
async def security_headers_middleware(request: Request, call_next):
    response = await call_next(request)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["X-XSS-Protection"] = "1; mode=block"
    response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
    response.headers["Permissions-Policy"] = "geolocation=(), microphone=(), camera=()"
    response.headers["Content-Security-Policy"] = (
        "default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; "
        "img-src 'self' data: https:; font-src 'self'"
    )
    if settings.ENVIRONMENT == "production":
        response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
    return response

# 2. Content-Type Validation Middleware
async def content_type_middleware(request: Request, call_next):
    if request.method in ("POST", "PUT", "PATCH"):
        content_type = request.headers.get("content-type", "")
        if not (
            content_type.startswith("application/json") or
            content_type.startswith("application/x-www-form-urlencoded") or
            request.url.path in EXEMPT_PATHS
        ):
            raise HTTPException(415, "Unsupported Media Type")
    return await call_next(request)

# 3. Rate Limiting (por endpoint)
RATE_LIMITS = {
    "/api/billing/check/request": (10, 60),   # 10 req/min
    "/api/billing/cash/pay": (20, 60),        # 20 req/min
    "/api/billing/mercadopago": (5, 60),      # 5 req/min
    "/api/auth/login": (5, 60),               # 5 req/min
}
```

### 8.4 Validación de Input

```python
# shared/utils/validators.py

# Prevención SSRF en URLs de imágenes
BLOCKED_HOSTS = [
    "localhost", "127.0.0.1", "0.0.0.0",
    "10.", "172.16.", "172.17.", "172.18.", "172.19.",
    "172.20.", "172.21.", "172.22.", "172.23.",
    "172.24.", "172.25.", "172.26.", "172.27.",
    "172.28.", "172.29.", "172.30.", "172.31.",
    "192.168.",
    "169.254.169.254",  # AWS metadata
    "metadata.google",   # GCP metadata
]

def validate_image_url(url: str | None) -> None:
    if not url:
        return

    parsed = urlparse(url)

    # Solo HTTPS en producción
    if parsed.scheme not in ("http", "https"):
        raise ValidationError("URL debe usar HTTP/HTTPS", field="image")

    # Bloquear hosts internos
    host = parsed.hostname or ""
    for blocked in BLOCKED_HOSTS:
        if host.startswith(blocked) or host == blocked:
            raise ValidationError("URL de imagen no permitida", field="image")

# Escape para patrones LIKE
def escape_like_pattern(search_term: str) -> str:
    """Escapa % y _ para prevenir inyección en LIKE."""
    return search_term.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
```

---

## 9. Aislamiento Multi-Tenant

### 9.1 Capas de Aislamiento

El sistema implementa aislamiento multi-tenant en cuatro capas independientes:

```
┌─────────────────────────────────────────────────────────────────┐
│                    CAPA 1: BASE DE DATOS                         │
│  • Todas las entidades tienen tenant_id FK                       │
│  • Índices compuestos (tenant_id, branch_id, ...)               │
│  • Queries SIEMPRE incluyen WHERE tenant_id = ?                  │
└─────────────────────────────────────────────────────────────────┘
                              │
┌─────────────────────────────▼───────────────────────────────────┐
│                    CAPA 2: REPOSITORIO                           │
│  • TenantRepository auto-filtra por tenant_id                    │
│  • BranchRepository auto-filtra por branch_id + tenant_id        │
│  • Imposible consultar datos de otro tenant                      │
└─────────────────────────────────────────────────────────────────┘
                              │
┌─────────────────────────────▼───────────────────────────────────┐
│                    CAPA 3: API                                   │
│  • JWT contiene tenant_id del usuario                            │
│  • Servicios validan tenant_id en cada operación                 │
│  • Requests cross-tenant retornan 403 Forbidden                  │
└─────────────────────────────────────────────────────────────────┘
                              │
┌─────────────────────────────▼───────────────────────────────────┐
│                    CAPA 4: WEBSOCKET                             │
│  • TenantFilter valida tenant_id en cada evento                  │
│  • Broadcast filtra conexiones por tenant DENTRO del lock        │
│  • Eventos nunca cruzan fronteras de tenant                      │
└─────────────────────────────────────────────────────────────────┘
```

### 9.2 Implementación en Repositorios

```python
class TenantRepository[ModelT]:
    """Repositorio que auto-filtra por tenant_id."""

    def __init__(self, model: type[ModelT], session: Session):
        self._model = model
        self._session = session

    def find_all(
        self,
        tenant_id: int,
        filters: dict | None = None,
        options: list | None = None,
        limit: int = 100,
        offset: int = 0
    ) -> Sequence[ModelT]:
        query = (
            select(self._model)
            .where(self._model.tenant_id == tenant_id)  # SIEMPRE filtra
            .where(self._model.is_active.is_(True))
        )

        if filters:
            for key, value in filters.items():
                query = query.where(getattr(self._model, key) == value)

        if options:
            query = query.options(*options)

        return self._session.scalars(
            query.offset(offset).limit(limit)
        ).all()

    def find_by_id(
        self,
        entity_id: int,
        tenant_id: int,
        options: list | None = None
    ) -> ModelT | None:
        query = (
            select(self._model)
            .where(self._model.id == entity_id)
            .where(self._model.tenant_id == tenant_id)  # Valida ownership
            .where(self._model.is_active.is_(True))
        )

        if options:
            query = query.options(*options)

        return self._session.scalar(query)
```

### 9.3 Filtrado en WebSocket Gateway

```python
class TenantFilter:
    """Filtrado centralizado por tenant para broadcast."""

    def filter_connections(
        self,
        connections: set[WebSocket],
        tenant_id: int | None,
        context_map: dict[WebSocket, dict]
    ) -> set[WebSocket]:
        """Filtra conexiones por tenant_id."""
        if tenant_id is None:
            return connections

        return {
            ws for ws in connections
            if context_map.get(ws, {}).get("tenant_id") == tenant_id
        }

# Uso en broadcast
async def send_to_branch(
    self,
    branch_id: int,
    payload: dict,
    tenant_id: int | None = None
):
    branch_lock = await self._lock_manager.get_branch_lock(branch_id)

    async with branch_lock:
        # Obtener conexiones del branch
        connections = set(self._index.get_by_branch(branch_id))

        # Filtrar por tenant DENTRO del lock (CRÍTICO para evitar race conditions)
        connections = self._tenant_filter.filter_connections(
            connections,
            tenant_id,
            self._index._ws_to_context
        )

    # Broadcast fuera del lock
    return await self._broadcaster.broadcast(connections, payload)
```

---

## 10. Optimizaciones de Rendimiento

### 10.1 Configuración para Alta Carga

El sistema está optimizado para 400-600 usuarios WebSocket concurrentes:

| Setting | Valor | Propósito |
|---------|-------|-----------|
| `ws_max_connections_per_user` | 3 | Limita duplicados |
| `ws_max_total_connections` | 1000 | Límite global |
| `ws_message_rate_limit` | 20/s | Rate limit por conexión |
| `ws_broadcast_batch_size` | 50 | Tamaño de batch para broadcast |
| `redis_pool_max_connections` | 50 | Pool async |
| `redis_sync_pool_max_connections` | 20 | Pool sync |
| `redis_event_queue_size` | 5000 | Buffer de backpressure |
| `redis_event_batch_size` | 50 | Batch de procesamiento |

### 10.2 Broadcast Paralelo con Batching

```python
async def _broadcast_to_connections(
    self,
    connections: set[WebSocket],
    payload: dict,
    context: str = ""
) -> BroadcastResult:
    """Broadcast paralelo con batching para eficiencia."""
    batch_size = settings.ws_broadcast_batch_size  # 50
    sent = 0
    failed = 0

    connections_list = list(connections)

    for i in range(0, len(connections_list), batch_size):
        batch = connections_list[i:i + batch_size]

        # Procesar batch en paralelo
        results = await asyncio.gather(
            *[self._send_to_connection(ws, payload) for ws in batch],
            return_exceptions=True
        )

        for result in results:
            if isinstance(result, Exception):
                failed += 1
            else:
                sent += 1

    return BroadcastResult(sent=sent, failed=failed)

# Rendimiento: 400 usuarios en ~160ms vs ~4000ms secuencial (25x mejora)
```

### 10.3 Sharded Locks

```python
class LockManager:
    """Locks sharded para reducir contención."""

    def __init__(self):
        self._global_lock = asyncio.Lock()        # Solo operaciones cross-cutting
        self._branch_locks: dict[int, asyncio.Lock] = {}
        self._user_locks: dict[int, asyncio.Lock] = {}
        self._branch_locks_lock = asyncio.Lock()  # Meta-lock para crear branch locks

    async def get_branch_lock(self, branch_id: int) -> asyncio.Lock:
        """Obtiene o crea lock para un branch específico."""
        if branch_id not in self._branch_locks:
            async with self._branch_locks_lock:
                if branch_id not in self._branch_locks:  # Double-check
                    self._branch_locks[branch_id] = asyncio.Lock()
        return self._branch_locks[branch_id]

# Operaciones de un branch no bloquean otros branches
# Reduce contención ~90% vs lock global único
```

### 10.4 Eager Loading para N+1

```python
# ❌ N+1 Problem: 1 + N queries
products = db.scalars(select(Product)).all()
for p in products:
    print(p.allergens)  # Query adicional por cada producto!

# ✅ Eager loading: 1-2 queries total
from sqlalchemy.orm import selectinload, joinedload

products = db.scalars(
    select(Product)
    .options(
        selectinload(Product.allergens),        # Carga en batch
        selectinload(Product.branch_products),
        joinedload(Product.subcategory)         # JOIN para 1:1
            .joinedload(Subcategory.category)
    )
    .where(Product.tenant_id == tenant_id)
).unique().all()

# Patrones de eager loading por entidad están preconfigurados en repositorios
```

### 10.5 Pool de Conexiones Redis

```python
# Async pool para operaciones no-bloqueantes
_async_pool: redis.asyncio.Redis | None = None
_async_pool_lock = asyncio.Lock()

async def get_redis_pool() -> redis.asyncio.Redis:
    global _async_pool
    if _async_pool is None:
        async with _async_pool_lock:
            if _async_pool is None:
                _async_pool = redis.asyncio.Redis(
                    host=settings.REDIS_HOST,
                    port=settings.REDIS_PORT,
                    max_connections=settings.redis_pool_max_connections,  # 50
                    decode_responses=True
                )
    return _async_pool

# Sync pool para operaciones bloqueantes (rate limiting, blacklist)
_sync_pool: redis.ConnectionPool | None = None
_sync_pool_lock = threading.Lock()

def get_redis_sync_client() -> redis.Redis:
    global _sync_pool
    if _sync_pool is None:
        with _sync_pool_lock:
            if _sync_pool is None:
                _sync_pool = redis.ConnectionPool(
                    host=settings.REDIS_HOST,
                    port=settings.REDIS_PORT,
                    max_connections=settings.redis_sync_pool_max_connections,  # 20
                    decode_responses=True
                )
    return redis.Redis(connection_pool=_sync_pool)
```

---

## 11. Flujos de Integración

### 11.1 Flujo de Orden Completo

```
┌─────────────────────────────────────────────────────────────────────────────┐
│ FASE 1: INICIO DE SESIÓN                                                     │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                              │
│  Cliente escanea QR → pwaMenu                                               │
│       │                                                                      │
│       ▼                                                                      │
│  POST /api/tables/code/{code}/session?branch_slug={slug}                    │
│       │                                                                      │
│       ├── Crea TableSession (status=OPEN)                                   │
│       ├── Crea Diner (device_id desde localStorage)                         │
│       └── Retorna table_token (HMAC, 3h TTL)                                │
│       │                                                                      │
│       ▼                                                                      │
│  WS Gateway publica TABLE_SESSION_STARTED                                   │
│       │                                                                      │
│       ├── → Dashboard (tableStore actualiza estado mesa)                    │
│       └── → pwaWaiter (si sector asignado)                                  │
│                                                                              │
└───────────────────────────────────────────────────────────────────────��─────┘
                              │
┌─────────────────────────────▼───────────────────────────────────────────────┐
│ FASE 2: ORDENAMIENTO COLABORATIVO                                            │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                              │
│  Comensales agregan productos a carritos individuales (cartStore local)     │
│       │                                                                      │
│       ▼                                                                      │
│  Comensal propone enviar ronda → proposeRound()                             │
│       │                                                                      │
│       ├── WS: ROUND_PROPOSAL → todos los diners de la sesión                │
│       └── UI: RoundConfirmationPanel aparece para todos                     │
│       │                                                                      │
│       ▼                                                                      │
│  Cada comensal confirma → confirmReady()                                    │
│       │                                                                      │
│       └── WS: DINER_READY → actualiza estado de confirmación                │
│       │                                                                      │
│       ▼                                                                      │
│  Todos confirmados → auto-submit (1.5s delay)                               │
│       │                                                                      │
│       ▼                                                                      │
│  POST /api/diner/rounds (X-Table-Token auth)                                │
│       │                                                                      │
│       ├── Crea Round (status=PENDING)                                       │
│       ├── Crea RoundItems con productos y cantidades                        │
│       └── Publica ROUND_SUBMITTED                                           │
│       │                                                                      │
│       ├── → Dashboard (tableStore.handleRoundSubmitted)                     │
│       │      └── Activa blink animation en mesa                             │
│       └── → pwaWaiter (si sector asignado)                                  │
│                                                                              │
└─────────────────────────────────────────────────────────────────────────────┘
                              │
┌─────────────────────────────▼───────────────────────────────────────────────┐
│ FASE 3: PROCESAMIENTO EN DASHBOARD                                           │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                              │
│  Admin/Manager ve ronda pendiente en TableSessionModal                      │
│       │                                                                      │
│       ▼                                                                      │
│  Click "Enviar a Cocina" → PATCH /api/admin/rounds/{id}/status              │
│       │                                                                      │
│       ├── Round.status = IN_KITCHEN                                         │
│       ├── Crea KitchenTickets agrupados por estación                        │
│       └── Publica ROUND_IN_KITCHEN                                          │
│       │                                                                      │
│       └── → Kitchen WebSocket channel (staff con rol KITCHEN)               │
│              └── pwaKitchen muestra tickets a preparar                      │
│                                                                              │
└─────────────────────────────────────────────────────────────────────────────┘
                              │
┌─────────────────────────────▼───────────────────────────────────────────────┐
│ FASE 4: PREPARACIÓN EN COCINA                                                │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                              │
│  Kitchen staff marca ítems como en progreso / listos                        │
│       │                                                                      │
│       ▼                                                                      │
│  PATCH /api/kitchen/tickets/{id}/status (KITCHEN role required)             │
│       │                                                                      │
│       ├── KitchenTicket.status = READY                                      │
│       ├── Si todos los tickets de la ronda listos:                          │
│       │      Round.status = READY                                           │
│       └── Publica TICKET_READY y/o ROUND_READY                              │
│       │                                                                      │
│       ├── → Dashboard (actualiza estado visual)                             │
│       ├── → pwaWaiter (push notification: "Mesa X lista")                   │
│       └── → pwaMenu diners (actualiza estado de su orden)                   │
│                                                                              │
└─────────────────────────────────────────────────────────────────────────────┘
                              │
┌─────────────────────────────▼───────────────────────────────────────────────┐
│ FASE 5: SERVICIO Y CIERRE                                                    │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                              │
│  Mesero entrega orden → PATCH /api/waiter/rounds/{id}/served                │
│       │                                                                      │
│       ├── Round.status = SERVED                                             │
│       └── Publica ROUND_SERVED                                              │
│       │                                                                      │
│       ▼                                                                      │
│  Cliente solicita cuenta → POST /api/billing/check/request                  │
│       │                                                                      │
│       ├── TableSession.status = PAYING                                      │
│       ├── Crea Check con Charges de todos los RoundItems                    │
│       └── Publica CHECK_REQUESTED                                           │
│       │                                                                      │
│       ▼                                                                      │
│  Pago procesado (efectivo o Mercado Pago)                                   │
│       │                                                                      │
│       ├── Crea Payment + Allocations (FIFO a Charges)                       │
│       ├── TableSession.status = CLOSED si pagado completo                   │
│       └── Publica CHECK_PAID + TABLE_CLEARED                                │
│                                                                              │
└─────────────────────────────────────────────────────────────────────────────┘
```

### 11.2 Flujo de Pagos con Mercado Pago

```
┌─────────────────────────────────────────────────────────────────────────────┐
│ FLUJO DE PAGO MERCADO PAGO                                                   │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                              │
│  pwaMenu                                                                    │
│       │                                                                      │
│       ▼                                                                      │
│  POST /api/billing/mercadopago/preference                                   │
│       │                                                                      │
│       ├── Calcula monto pendiente del Check                                 │
│       ├── Crea preferencia en MP API                                        │
│       └── Retorna preference_id + init_point URL                            │
│       │                                                                      │
│       ▼                                                                      │
│  Redirect a checkout.mercadopago.com                                        │
│       │                                                                      │
│       ▼                                                                      │
│  Usuario completa pago en MP                                                │
│       │                                                                      │
│       ▼                                                                      │
│  MP envía webhook → POST /api/billing/webhook                               │
│       │                                                                      │
│       ├── Verifica firma HMAC del webhook                                   │
│       ├── Obtiene detalles del pago via MP API                              │
│       ├── Circuit Breaker protege contra fallos de MP                       │
│       │                                                                      │
│       ├── Si status=approved:                                               │
│       │      ├── Crea Payment con external_id                               │
│       │      ├── Crea Allocations (FIFO a Charges pendientes)               │
│       │      └── Publica PAYMENT_APPROVED → diner WebSocket                 │
│       │                                                                      │
│       ├── Si status=rejected:                                               │
│       │      └── Publica PAYMENT_REJECTED → diner WebSocket                 │
│       │                                                                      │
│       └── Si status=pending/in_process:                                     │
│              └── Encola para retry (webhook_retry queue)                    │
│                                                                              │
└─────────────────────────────────────────────────────────────────────────────┘

Protecciones:
• Rate limit: 5 req/min en endpoints MP
• Circuit breaker: 5 fallos → OPEN por 30s
• Retry con jitter: Previene thundering herd
• Webhook signature: HMAC-SHA256 validation
• Idempotency: external_id previene duplicados
```

### 11.3 Flujo de Sincronización Real-Time

```
┌─────────────────────────────────────────────────────────────────────────────┐
│ FLUJO DE EVENTO REAL-TIME                                                    │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                              │
│  REST API (después de operación exitosa)                                    │
│       │                                                                      │
│       ▼                                                                      │
│  publish_event(redis, channel, Event(...))                                  │
│       │                                                                      │
│       ├── Serializa Event a JSON                                            │
│       ├── PUBLISH al canal Redis apropiado                                  │
│       │      • branch:{id}:waiters                                          │
│       │      • branch:{id}:kitchen                                          │
│       │      • branch:{id}:admin                                            │
│       │      • session:{id}:diners                                          │
│       └── Circuit breaker protege ante fallos Redis                         │
│                                                                              │
│  Redis Pub/Sub                                                              │
│       │                                                                      │
│       ▼                                                                      │
│  WS Gateway RedisSubscriber                                                 │
│       │                                                                      │
│       ├── Recibe mensaje del canal suscrito                                 │
│       ├── validate_event_schema() - Valida estructura                       │
│       ├── EventDropRateTracker - Monitorea tasa de descarte                 │
│       └── Encola en buffer de procesamiento                                 │
│       │                                                                      │
│       ▼                                                                      │
│  process_event_batch() (batch de 50 eventos)                                │
│       │                                                                      │
│       ├── EventRouter determina destinatarios                               │
│       │      ├── Por branch_id                                              │
│       │      ├── Por sector_id (para waiters)                               │
│       │      └── Por session_id (para diners)                               │
│       │                                                                      │
│       ├── TenantFilter asegura aislamiento                                  │
│       │                                                                      │
│       └── BroadcastRouter envía a conexiones                                │
│              ├── Batching de 50 conexiones                                  │
│              ├── asyncio.gather() paralelo                                  │
│              └── Observer notifica métricas                                 │
│                                                                              │
│  Frontend WebSocket Client                                                  │
│       │                                                                      │
│       ▼                                                                      │
│  ws.on(eventType, handler)                                                  │
│       │                                                                      │
│       └── Zustand store.handleEvent()                                       │
│              └── Actualiza estado → React re-render                         │
│                                                                              │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## 12. Infraestructura y DevOps

### 12.1 Estructura de Directorios

```
integrador/
├── Dashboard/              # Panel administrativo
│   ├── src/
│   ├── public/
│   ├── package.json
│   └── vite.config.ts
│
├── pwaMenu/                # PWA cliente
│   ├── src/
│   ├── public/
│   ├── package.json
│   └── vite.config.ts
│
├── pwaWaiter/              # PWA mesero
│   ├── src/
│   ├── public/
│   ├── package.json
│   └── vite.config.ts
│
├── backend/                # REST API + shared modules
│   ├── rest_api/           # FastAPI app
│   │   ├── core/           # Configuración de app
│   │   ├── models/         # SQLAlchemy models
│   │   ├── routers/        # API endpoints
│   │   └── services/       # Lógica de negocio
│   │
│   ├── shared/             # Módulos compartidos (API + WS)
│   │   ├── security/       # Auth, passwords, tokens
│   │   ├── infrastructure/ # DB, Redis
│   │   ├── config/         # Settings, logging
│   │   └── utils/          # Helpers, validators
│   │
│   ├── tests/              # pytest tests
│   ├── requirements.txt
│   └── .env.example
│
├── ws_gateway/             # WebSocket Gateway
│   ├── main.py
│   ├── connection_manager.py
│   ├── redis_subscriber.py
│   ├── core/               # Módulos extraídos
│   └── components/         # Arquitectura modular
│
├── devOps/                 # Infraestructura
│   ├── docker-compose.yml  # PostgreSQL + Redis
│   ├── start.ps1           # Windows startup script
│   └── start.sh            # Unix startup script
│
├── CLAUDE.md               # Instrucciones para Claude Code
├── README.md               # Documentación principal
└── arquitectura.md         # Este documento
```

### 12.2 Docker Compose

```yaml
# devOps/docker-compose.yml
version: "3.8"

services:
  postgres:
    image: pgvector/pgvector:pg16
    ports:
      - "5432:5432"
    environment:
      POSTGRES_USER: integrador
      POSTGRES_PASSWORD: integrador
      POSTGRES_DB: integrador
    volumes:
      - postgres_data:/var/lib/postgresql/data
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U integrador"]
      interval: 5s
      timeout: 5s
      retries: 5

  redis:
    image: redis:7-alpine
    ports:
      - "6380:6379"  # Puerto 6380 externamente
    volumes:
      - redis_data:/data
    healthcheck:
      test: ["CMD", "redis-cli", "ping"]
      interval: 5s
      timeout: 5s
      retries: 5

volumes:
  postgres_data:
  redis_data:
```

### 12.3 Scripts de Inicio

**Windows (devOps/start.ps1)**:
```powershell
# Inicia todos los servicios para desarrollo
Write-Host "Starting Integrador Development Environment..."

# 1. Verificar Docker
if (-not (Get-Process -Name "Docker Desktop" -ErrorAction SilentlyContinue)) {
    Write-Host "Please start Docker Desktop first"
    exit 1
}

# 2. Iniciar PostgreSQL + Redis
docker compose -f ../devOps/docker-compose.yml up -d

# 3. Esperar a que los servicios estén listos
Start-Sleep -Seconds 5

# 4. Configurar PYTHONPATH para ws_gateway
$env:PYTHONPATH = (Get-Location).Path

# 5. Iniciar REST API (nueva terminal)
Start-Process powershell -ArgumentList "-NoExit", "-Command", "cd backend; python -m uvicorn rest_api.main:app --reload --port 8000"

# 6. Iniciar WS Gateway (nueva terminal)
Start-Process powershell -ArgumentList "-NoExit", "-Command", "cd ..; `$env:PYTHONPATH='$PWD\backend'; python -m uvicorn ws_gateway.main:app --reload --port 8001"

Write-Host "Services starting..."
Write-Host "  REST API: http://localhost:8000"
Write-Host "  WS Gateway: ws://localhost:8001"
Write-Host "  PostgreSQL: localhost:5432"
Write-Host "  Redis: localhost:6380"
```

**Unix (devOps/start.sh)**:
```bash
#!/bin/bash

echo "Starting Integrador Development Environment..."

# 1. Iniciar PostgreSQL + Redis
docker compose -f devOps/docker-compose.yml up -d

# 2. Esperar a servicios
sleep 5

# 3. Configurar PYTHONPATH
export PYTHONPATH="$(pwd)/backend"

# 4. Iniciar REST API (background)
cd backend
python -m uvicorn rest_api.main:app --reload --port 8000 &
REST_PID=$!
cd ..

# 5. Iniciar WS Gateway (background)
python -m uvicorn ws_gateway.main:app --reload --port 8001 &
WS_PID=$!

echo "Services started:"
echo "  REST API (PID $REST_PID): http://localhost:8000"
echo "  WS Gateway (PID $WS_PID): ws://localhost:8001"

# Trap para cleanup
trap "kill $REST_PID $WS_PID 2>/dev/null" EXIT

wait
```

### 12.4 Variables de Entorno

```bash
# backend/.env.example

# Database
DATABASE_URL=postgresql://integrador:integrador@localhost:5432/integrador

# Redis
REDIS_HOST=localhost
REDIS_PORT=6380

# JWT (CAMBIAR EN PRODUCCIÓN)
JWT_SECRET=your-super-secret-jwt-key-minimum-32-characters
TABLE_TOKEN_SECRET=your-table-token-secret-minimum-32-characters

# CORS (producción: lista separada por comas)
ALLOWED_ORIGINS=http://localhost:5176,http://localhost:5177,http://localhost:5178

# Environment
ENVIRONMENT=development  # development | production
DEBUG=true

# Mercado Pago (opcional)
MERCADOPAGO_ACCESS_TOKEN=
MERCADOPAGO_WEBHOOK_SECRET=

# WebSocket tuning
WS_MAX_CONNECTIONS_PER_USER=3
WS_MAX_TOTAL_CONNECTIONS=1000
WS_MESSAGE_RATE_LIMIT=20
WS_BROADCAST_BATCH_SIZE=50

# Redis pools
REDIS_POOL_MAX_CONNECTIONS=50
REDIS_SYNC_POOL_MAX_CONNECTIONS=20
```

---

## 13. Decisiones Arquitectónicas

### 13.1 ADR-001: Separación REST API y WebSocket Gateway

**Contexto**: El sistema requiere tanto operaciones transaccionales (CRUD) como comunicación en tiempo real.

**Decisión**: Implementar REST API y WebSocket Gateway como servicios separados en puertos distintos (8000 y 8001).

**Justificación**:
- Separación de concerns: HTTP request/response vs conexiones persistentes
- Escalado independiente: WS Gateway puede escalar horizontalmente
- Resiliencia: Fallo de WS no afecta operaciones críticas de negocio
- Testing: Cada servicio se prueba de forma aislada

**Consecuencias**:
- (+) Modularidad y mantenibilidad mejoradas
- (+) Escalado granular por tipo de carga
- (-) Complejidad de deployment aumentada
- (-) Requiere Redis para comunicación entre servicios

### 13.2 ADR-002: Zustand sobre Redux

**Contexto**: Selección de librería de estado global para 3 frontends React 19.

**Decisión**: Usar Zustand con patrón de selectores estricto.

**Justificación**:
- API minimalista reduce boilerplate
- Compatibilidad nativa con React 19 hooks
- No requiere providers envolventes
- Selectores permiten optimización granular de re-renders

**Consecuencias**:
- (+) Código más conciso y legible
- (+) Mejor rendimiento con selectores adecuados
- (-) Requiere disciplina en patrones (no destructuring)
- (-) Menos herramientas de debugging que Redux DevTools

### 13.3 ADR-003: Soft Delete Universal

**Contexto**: Requerimiento de auditoría completa y capacidad de restauración.

**Decisión**: Implementar AuditMixin en todos los modelos con soft delete via `is_active` flag.

**Justificación**:
- Preserva historial completo para auditorías
- Permite restauración de datos eliminados accidentalmente
- Cascade soft delete mantiene integridad referencial
- Queries filtran automáticamente por `is_active=True`

**Consecuencias**:
- (+) Trazabilidad completa de cambios
- (+) Recuperación ante errores humanos
- (-) Crecimiento de base de datos con datos "eliminados"
- (-) Complejidad adicional en queries (siempre filtrar is_active)

### 13.4 ADR-004: Clean Architecture en Backend

**Contexto**: Necesidad de código mantenible y testeable a largo plazo.

**Decisión**: Implementar Clean Architecture con 4 capas: Routers → Services → Repositories → Models.

**Justificación**:
- Inversión de dependencias facilita testing
- Lógica de negocio aislada de concerns de infraestructura
- Cambios en una capa no propagan a otras
- Domain Services encapsulan reglas de negocio complejas

**Consecuencias**:
- (+) Alta cohesión, bajo acoplamiento
- (+) Testing unitario simplificado con mocks
- (-) Más archivos y estructura inicial
- (-) Curva de aprendizaje para nuevos desarrolladores

### 13.5 ADR-005: Strategy Pattern para Permisos

**Contexto**: 4 roles (ADMIN, MANAGER, KITCHEN, WAITER) con permisos muy diferentes.

**Decisión**: Implementar Strategy Pattern con Interface Segregation Principle.

**Justificación**:
- Elimina cascadas if/elif para verificación de roles
- Cada estrategia encapsula reglas de un rol
- Mixins permiten composición flexible
- Extensible para nuevos roles sin modificar código existente

**Consecuencias**:
- (+) Open/Closed principle respetado
- (+) Código de permisos testeable aisladamente
- (-) Más clases que enfoque procedural
- (-) Requiere entender el patrón para modificar

### 13.6 ADR-006: Sharded Locks en WebSocket Gateway

**Contexto**: Contención de lock global limitaba throughput a ~100 broadcasts/segundo.

**Decisión**: Implementar locks sharded por branch_id y user_id.

**Justificación**:
- Operaciones de un branch no bloquean otros branches
- Reduce contención ~90%
- Lock global solo para operaciones cross-cutting
- Permite escalar a 400-600 usuarios concurrentes

**Consecuencias**:
- (+) Throughput aumentado 10x
- (+) Latencia de broadcast reducida
- (-) Complejidad de manejo de locks
- (-) Riesgo de deadlock si no se respeta orden de adquisición

---

## Apéndice A: Glosario

| Término | Definición |
|---------|------------|
| **Tenant** | Restaurante/organización que usa el sistema |
| **Branch** | Sucursal física de un tenant |
| **Diner** | Comensal individual identificado por device_id |
| **Round** | Ronda de pedidos de una mesa |
| **Check** | Cuenta/factura de una sesión |
| **Sector** | Zona del restaurante asignada a meseros |
| **Table Token** | Token HMAC para autenticar comensales |
| **Soft Delete** | Eliminación lógica marcando is_active=False |
| **Eager Loading** | Carga anticipada de relaciones en SQLAlchemy |
| **Circuit Breaker** | Patrón que previene cascada de fallos |

---

## Apéndice B: Referencias

- [Dashboard/README.md](Dashboard/README.md) - Documentación del Dashboard
- [Dashboard/arquiDashboard.md](Dashboard/arquiDashboard.md) - Arquitectura del Dashboard
- [pwaMenu/README.md](pwaMenu/README.md) - Documentación de pwaMenu
- [pwaMenu/arquiPwaMenu.md](pwaMenu/arquiPwaMenu.md) - Arquitectura de pwaMenu
- [backend/README.md](backend/README.md) - Documentación del Backend
- [backend/arquiBackend.md](backend/arquiBackend.md) - Arquitectura del Backend
- [ws_gateway/README.md](ws_gateway/README.md) - Documentación del WebSocket Gateway
- [ws_gateway/arquiws_gateway.md](ws_gateway/arquiws_gateway.md) - Arquitectura del WebSocket Gateway
- [devOps/README.md](devOps/README.md) - Documentación de infraestructura
- [CLAUDE.md](CLAUDE.md) - Instrucciones para Claude Code

---

*Documento generado como visión de liderazgo de proyecto del sistema Integrador.*
*Última actualización: Enero 2026*
