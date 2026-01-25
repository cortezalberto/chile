# Arquitectura del Backend

Este documento describe la arquitectura técnica del backend de Integrador, detallando los principios de diseño, patrones implementados, estructura de capas y flujos de datos que conforman el sistema.

---

## Principios Arquitectónicos

### Clean Architecture

El backend implementa Clean Architecture, un enfoque que organiza el código en capas concéntricas donde las dependencias fluyen hacia adentro. Las capas externas conocen a las internas, pero nunca al revés. Este principio fundamental permite que la lógica de negocio permanezca aislada de los detalles de infraestructura.

```
┌─────────────────────────────────────────────────────────────────┐
│                         FRAMEWORKS                               │
│                    FastAPI, SQLAlchemy, Redis                    │
└─────────────────────────────┬───────────────────────────────────┘
                              │
┌─────────────────────────────▼───────────────────────────────────┐
│                     INTERFACE ADAPTERS                           │
│               Routers, Repositories, Event Publishers            │
└─────────────────────────────┬───────────────────────────────────┘
                              │
┌─────────────────────────────▼───────────────────────────────────┐
│                     APPLICATION LAYER                            │
│                    Domain Services, Use Cases                    │
└─────────────────────────────┬───────────────────────────────────┘
                              │
┌─────────────────────────────▼───────────────────────────────────┐
│                       DOMAIN LAYER                               │
│                   Entities, Value Objects                        │
└─────────────────────────────────────────────────────────────────┘
```

### Principios SOLID

**Single Responsibility**: Cada clase tiene una única razón para cambiar. Los routers manejan HTTP, los servicios contienen lógica de negocio, los repositorios acceden a datos.

**Open/Closed**: Las clases base de servicios están abiertas para extensión mediante hooks (`_validate_create`, `_after_delete`) pero cerradas para modificación.

**Liskov Substitution**: Cualquier servicio de dominio puede sustituirse por otro que herede de la misma base sin romper el sistema.

**Interface Segregation**: Los protocolos de permisos (`CanRead`, `CanCreate`, `CanUpdate`, `CanDelete`) permiten implementar solo las capacidades necesarias.

**Dependency Inversion**: Los servicios dependen de abstracciones (Repository Protocol) no de implementaciones concretas.

---

## Arquitectura de Capas

### Diagrama de Capas

```
                              HTTP Request
                                   │
                                   ▼
┌──────────────────────────────────────────────────────────────────┐
│                        PRESENTATION LAYER                         │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐               │
│  │   Routers   │  │ Middlewares │  │   Schemas   │               │
│  │  (FastAPI)  │  │  (Security) │  │ (Pydantic)  │               │
│  └──────┬──────┘  └─────────────┘  └─────────────┘               │
└─────────┼────────────────────────────────────────────────────────┘
          │
          ▼
┌──────────────────────────────────────────────────────────────────┐
│                       APPLICATION LAYER                           │
│  ┌─────────────────┐  ┌─────────────────┐  ┌─────────────────┐   │
│  │ Domain Services │  │   Permission    │  │ Event Publishers │   │
│  │  (Use Cases)    │  │    Context      │  │                  │   │
│  └────────┬────────┘  └─────────────────┘  └─────────────────┘   │
└───────────┼──────────────────────────────────────────────────────┘
            │
            ▼
┌──────────────────────────────────────────────────────────────────┐
│                         DOMAIN LAYER                              │
│  ┌─────────────────┐  ┌─────────────────┐  ┌─────────────────┐   │
│  │     Models      │  │  Value Objects  │  │  Domain Events  │   │
│  │  (SQLAlchemy)   │  │   (Dataclass)   │  │                  │   │
│  └────────┬────────┘  └─────────────────┘  └─────────────────┘   │
└───────────┼──────────────────────────────────────────────────────┘
            │
            ▼
┌──────────────────────────────────────────────────────────────────┐
│                     INFRASTRUCTURE LAYER                          │
│  ┌─────────────────┐  ┌─────────────────┐  ┌─────────────────┐   │
│  │  Repositories   │  │   Redis Pool    │  │   DB Session    │   │
│  │                 │  │   (Pub/Sub)     │  │  (PostgreSQL)   │   │
│  └─────────────────┘  └─────────────────┘  └─────────────────┘   │
└──────────────────────────────────────────────────────────────────┘
```

### Presentation Layer

La capa de presentación actúa como frontera del sistema, traduciendo peticiones HTTP a llamadas de servicios y respuestas de dominio a JSON. Sus componentes son deliberadamente delgados.

**Routers** reciben peticiones, validan entrada mediante Pydantic, verifican permisos y delegan a servicios. No contienen lógica de negocio:

```python
@router.post("/categories")
def create_category(body: CategoryCreate, db: Session, user: dict):
    ctx = PermissionContext(user)
    ctx.require_management()
    service = CategoryService(db)
    return service.create(body.model_dump(), ctx.tenant_id, ctx.user_id, ctx.user_email)
```

**Middlewares** implementan concerns transversales: seguridad, logging, rate limiting. Se ejecutan antes/después de cada request.

**Schemas** (Pydantic) definen contratos de entrada/salida, validando automáticamente tipos y constraints.

### Application Layer

La capa de aplicación orquesta los casos de uso del sistema. Aquí reside la lógica que coordina múltiples operaciones de dominio.

**Domain Services** encapsulan casos de uso completos. Heredan de clases base que proporcionan CRUD estándar:

```python
class ProductService(BranchScopedService[Product, ProductOutput]):
    def create_with_branch_prices(self, data: dict, branch_prices: list[dict], ...):
        # Caso de uso: crear producto con precios por sucursal
        product = self._create_entity(data)
        for price_data in branch_prices:
            self._create_branch_price(product.id, price_data)
        self._publish_created_event(product)
        return self.to_output(product)
```

**Permission Context** centraliza la lógica de autorización, determinando qué acciones puede realizar cada usuario según su rol y sucursales asignadas.

**Event Publishers** notifican cambios al sistema de tiempo real, desacoplando la mutación de datos de su propagación.

### Domain Layer

El núcleo del sistema contiene las entidades de negocio y sus reglas inherentes. Esta capa no tiene dependencias externas.

**Models** representan entidades del dominio con sus relaciones y validaciones:

```python
class Round(Base, AuditMixin):
    __tablename__ = "rounds"

    id: Mapped[int] = mapped_column(primary_key=True)
    session_id: Mapped[int] = mapped_column(ForeignKey("table_sessions.id"))
    status: Mapped[str] = mapped_column(String(20), default="PENDING")

    # Relaciones
    session: Mapped["TableSession"] = relationship(back_populates="rounds")
    items: Mapped[list["RoundItem"]] = relationship(back_populates="round")

    # Invariante de dominio
    @validates("status")
    def validate_status(self, key, value):
        if value not in VALID_ROUND_STATUSES:
            raise ValueError(f"Invalid status: {value}")
        return value
```

**Value Objects** encapsulan conceptos inmutables como Event, que representa un evento de dominio:

```python
@dataclass(frozen=True)
class Event:
    type: str
    tenant_id: int
    branch_id: int
    payload: dict
    timestamp: float = field(default_factory=time.time)
```

### Infrastructure Layer

La capa de infraestructura implementa los detalles técnicos de persistencia y comunicación.

**Repositories** abstraen el acceso a datos con interfaces consistentes:

```python
class TenantRepository(Generic[ModelT]):
    def find_all(self, tenant_id: int, options: list = None) -> list[ModelT]:
        query = select(self._model).where(
            self._model.tenant_id == tenant_id,
            self._model.is_active.is_(True),
        )
        if options:
            query = query.options(*options)
        return self._session.scalars(query).all()
```

**Redis Pool** gestiona conexiones para pub/sub y caching:

```python
# Pool async para eventos (non-blocking)
async def get_redis_pool() -> Redis:
    return await aioredis.from_url(settings.redis_url, max_connections=50)

# Pool sync para rate limiting (blocking OK)
def get_redis_sync_client() -> Redis:
    return ConnectionPool(max_connections=20).get_connection()
```

---

## Patrones de Diseño

### Repository Pattern

El patrón Repository abstrae la persistencia, permitiendo que los servicios trabajen con colecciones de objetos sin conocer los detalles de almacenamiento.

```
┌─────────────────┐         ┌─────────────────┐
│     Service     │────────▶│   Repository    │
│                 │         │   (Protocol)    │
└─────────────────┘         └────────┬────────┘
                                     │
                    ┌────────────────┼────────────────┐
                    │                │                │
                    ▼                ▼                ▼
           ┌──────────────┐ ┌──────────────┐ ┌──────────────┐
           │   Tenant     │ │   Branch     │ │   Product    │
           │  Repository  │ │  Repository  │ │  Repository  │
           └──────────────┘ └──────────────┘ └──────────────┘
```

**Beneficios:**
- Centraliza queries y eager loading
- Facilita testing con mocks
- Encapsula detalles de SQLAlchemy

### Strategy Pattern (Permisos)

El sistema de permisos implementa Strategy para manejar diferentes políticas por rol.

```
┌─────────────────────┐
│  PermissionContext  │
│  ─────────────────  │
│  + require_admin()  │
│  + can(action)      │
└──────────┬──────────┘
           │ usa
           ▼
┌─────────────────────┐
│ PermissionStrategy  │◀─────────────────────────────────────┐
│     (Protocol)      │                                      │
│  ─────────────────  │                                      │
│  + can_create()     │                                      │
│  + can_update()     │                                      │
│  + can_delete()     │                                      │
└──────────┬──────────┘                                      │
           │                                                 │
           │ implementa                                      │
           │                                                 │
     ┌─────┴─────┬─────────────┬─────────────┐              │
     ▼           ▼             ▼             ▼              │
┌─────────┐ ┌─────────┐ ┌─────────┐ ┌─────────┐            │
│  Admin  │ │ Manager │ │ Kitchen │ │ Waiter  │            │
│Strategy │ │Strategy │ │Strategy │ │Strategy │────────────┘
└─────────┘ └─────────┘ └─────────┘ └─────────┘
```

### Template Method (Servicios)

Los servicios de dominio usan Template Method para definir el esqueleto de operaciones CRUD con hooks extensibles.

```
┌───────────────────────────────────────────────────────┐
│                   BaseCRUDService                      │
│  ─────────────────────────────────────────────────    │
│  + create(data, tenant_id, user_id, user_email)       │
│      1. _validate_create(data, tenant_id)    ←──────── hook
│      2. _build_entity(data)                           │
│      3. _save_entity(entity)                          │
│      4. _after_create(entity, user_id)       ←──────── hook
│      5. return to_output(entity)                      │
└───────────────────────────────────────────────────────┘
                          △
                          │ hereda
          ┌───────────────┼───────────────┐
          │               │               │
          ▼               ▼               ▼
   ┌─────────────┐ ┌─────────────┐ ┌─────────────┐
   │  Category   │ │   Product   │ │    Table    │
   │   Service   │ │   Service   │ │   Service   │
   │ ─────────── │ │ ─────────── │ │ ─────────── │
   │ _validate_  │ │ _validate_  │ │ _validate_  │
   │   create()  │ │   create()  │ │   create()  │
   │ _after_     │ │ _after_     │ │ _after_     │
   │   create()  │ │   create()  │ │   create()  │
   └─────────────┘ └─────────────┘ └─────────────┘
```

### Observer Pattern (Eventos)

El sistema de eventos implementa Observer para notificar cambios sin acoplar emisor y receptores.

```
┌─────────────────┐         ┌─────────────────┐
│     Service     │────────▶│ EventPublisher  │
│  (Subject)      │ publica │                 │
└─────────────────┘         └────────┬────────┘
                                     │
                              Redis Pub/Sub
                                     │
                    ┌────────────────┼────────────────┐
                    │                │                │
                    ▼                ▼                ▼
           ┌──────────────┐ ┌──────────────┐ ┌──────────────┐
           │  WS Gateway  │ │   Webhook    │ │    Audit     │
           │  (Observer)  │ │   Handler    │ │    Logger    │
           └──────────────┘ └──────────────┘ └──────────────┘
```

### Circuit Breaker (Resiliencia)

Para proteger contra fallos en cascada, el sistema implementa Circuit Breaker en las integraciones con Redis y servicios externos.

```
                    ┌─────────────────────────────┐
                    │      Circuit Breaker        │
                    │  ─────────────────────────  │
                    │  failure_threshold: 5       │
                    │  recovery_timeout: 30s      │
                    └─────────────┬───────────────┘
                                  │
         ┌────────────────────────┼────────────────────────┐
         │                        │                        │
         ▼                        ▼                        ▼
   ┌───────────┐           ┌───────────┐           ┌───────────┐
   │  CLOSED   │──fallos──▶│   OPEN    │──timeout─▶│HALF-OPEN  │
   │           │           │           │           │           │
   │ Operación │           │  Falla    │           │  Prueba   │
   │  normal   │           │  rápido   │           │  parcial  │
   └───────────┘           └───────────┘           └─────┬─────┘
         △                                               │
         │                                               │
         └───────────────────éxito───────────────────────┘
```

---

## Flujos de Datos

### Flujo de Creación (Create)

```
POST /api/admin/products
         │
         ▼
┌─────────────────────────────────────────────────────────────────┐
│ Router: products.py                                              │
│  1. Validar ProductCreate (Pydantic)                            │
│  2. ctx = PermissionContext(user)                               │
│  3. ctx.require_management()                                    │
│  4. ctx.require_branch_access(body.branch_id)                   │
└─────────────────────────────────────────────────────────────────┘
         │
         ▼
┌─────────────────────────────────────────────────────────────────┐
│ Service: ProductService                                          │
│  1. _validate_create(data, tenant_id)                           │
│     - Verificar nombre único en sucursal                        │
│     - Validar URL de imagen (SSRF prevention)                   │
│  2. product = Product(**data, tenant_id=tenant_id)              │
│  3. set_created_by(product, user_id, user_email)                │
│  4. db.add(product)                                             │
│  5. safe_commit(db)                                             │
│  6. _after_create(product_info, user_id, user_email)            │
│     - publish_entity_created("Product", product_info)           │
└─────────────────────────────────────────────────────────────────┘
         │
         ▼
┌─────────────────────────────────────────────────────────────────┐
│ Infrastructure                                                   │
│  1. PostgreSQL: INSERT INTO products ...                        │
│  2. Redis: PUBLISH channel:branch:5:all {event}                 │
└─────────────────────────────────────────────────────────────────┘
         │
         ▼
    ProductOutput (JSON)
```

### Flujo de Pedido (Round)

```
POST /api/diner/rounds (desde pwaMenu)
         │
         ▼
┌─────────────────────────────────────────────────────────────────┐
│ Router: diner/orders.py                                          │
│  1. Validar X-Table-Token                                       │
│  2. Verificar sesión activa                                     │
│  3. Validar items del pedido                                    │
└─────────────────────────────────────────────────────────────────┘
         │
         ▼
┌─────────────────────────────────────────────────────────────────┐
│ Service: RoundService                                            │
│  1. Crear Round con status=PENDING                              │
│  2. Crear RoundItems con precios actuales                       │
│  3. Calcular totales                                            │
│  4. Commit transacción                                          │
│  5. Publicar ROUND_SUBMITTED                                    │
└─────────────────────────────────────────────────────────────────┘
         │
         ▼
┌─────────────────────────────────────────────────────────────────┐
│ Event Flow                                                       │
│                                                                  │
│  Redis ──▶ WS Gateway ──▶ Dashboard (admin)                     │
│                       ──▶ pwaWaiter (meseros del sector)        │
│                                                                  │
│  [ROUND_SUBMITTED NO va a cocina - solo admin/waiters]          │
└─────────────────────────────────────────────────────────────────┘
         │
         ▼
   (Admin aprueba y cambia a IN_KITCHEN)
         │
         ▼
┌─────────────────────────────────────────────────────────────────┐
│ Event Flow (IN_KITCHEN)                                          │
│                                                                  │
│  Redis ──▶ WS Gateway ──▶ Kitchen (cocina de la sucursal)       │
│                       ──▶ Dashboard (admin)                     │
└─────────────────────────────────────────────────────────────────┘
```

### Flujo de Autenticación

```
POST /api/auth/login
         │
         ▼
┌─────────────────────────────────────────────────────────────────┐
│ Router: auth/routes.py                                           │
│  1. Rate limit check (5/60s por IP)                             │
│  2. Validar LoginRequest                                        │
└─────────────────────────────────────────────────────────────────┘
         │
         ▼
┌─────────────────────────────────────────────────────────────────┐
│ Security: auth.py                                                │
│  1. Buscar usuario por email                                    │
│  2. Verificar password (bcrypt)                                 │
│  3. Verificar usuario activo                                    │
│  4. Cargar roles y sucursales                                   │
│  5. Generar access_token (15 min)                               │
│  6. Generar refresh_token (7 días)                              │
└─────────────────────────────────────────────────────────────────┘
         │
         ▼
┌─────────────────────────────────────────────────────────────────┐
│ JWT Payload                                                      │
│  {                                                               │
│    "sub": "123",           // user_id                           │
│    "email": "user@demo.com",                                    │
│    "tenant_id": 1,                                              │
│    "branch_ids": [1, 2],                                        │
│    "roles": ["MANAGER"],                                        │
│    "exp": 1706234567       // 15 min from now                   │
│  }                                                               │
└─────────────────────────────────────────────────────────────────┘
```

---

## Arquitectura de Módulos

### Módulo rest_api

```
rest_api/
│
├── core/                          # Configuración de aplicación
│   ├── lifespan.py               # Startup: DB init, Redis pool
│   │                             # Shutdown: close connections
│   ├── middlewares.py            # SecurityHeaders, ContentType
│   └── cors.py                   # CORS origins configuration
│
├── models/                        # Entidades de dominio
│   ├── base.py                   # AuditMixin (is_active, timestamps, audit fields)
│   ├── tenant.py                 # Tenant, Branch
│   ├── user.py                   # User, UserBranchRole
│   ├── catalog.py                # Category, Subcategory, Product, BranchProduct
│   ├── allergen.py               # Allergen, ProductAllergen, AllergenCrossReaction
│   ├── ingredient.py             # IngredientGroup, Ingredient, SubIngredient
│   ├── product_profile.py        # 12 perfiles: dietary, cooking, flavor...
│   ├── sector.py                 # BranchSector, WaiterSectorAssignment
│   ├── table.py                  # Table, TableSession
│   ├── customer.py               # Customer, Diner (loyalty)
│   ├── order.py                  # Round, RoundItem
│   ├── kitchen.py                # KitchenTicket, KitchenTicketItem, ServiceCall
│   ├── billing.py                # Check, Payment, Charge, Allocation
│   ├── promotion.py              # Promotion, PromotionBranch, PromotionItem
│   ├── exclusion.py              # BranchCategoryExclusion
│   ├── audit.py                  # AuditLog
│   ├── recipe.py                 # Recipe, RecipeAllergen
│   └── knowledge.py              # KnowledgeDocument, ChatLog (RAG)
│
├── repositories/                  # Acceso a datos
│   ├── base.py                   # BaseRepository, RepositoryFilters
│   ├── product.py                # ProductRepository (eager loading)
│   ├── category.py               # CategoryRepository
│   ├── round.py                  # RoundRepository
│   └── kitchen_ticket.py         # KitchenTicketRepository
│
├── routers/                       # Endpoints HTTP
│   ├── _common/                  # Utilidades compartidas
│   │   ├── base.py               # Helpers comunes
│   │   └── pagination.py         # Pagination dependency
│   │
│   ├── admin/                    # /api/admin/* (15 sub-routers)
│   │   ├── __init__.py           # Router maestro
│   │   ├── _base.py              # Utilidades admin
│   │   ├── tenant.py             # Configuración org
│   │   ├── branches.py           # Sucursales
│   │   ├── categories.py         # Categorías
│   │   ├── subcategories.py      # Subcategorías
│   │   ├── products.py           # Productos
│   │   ├── allergens.py          # Alérgenos
│   │   ├── staff.py              # Personal
│   │   ├── tables.py             # Mesas
│   │   ├── sectors.py            # Sectores
│   │   ├── assignments.py        # Asignaciones
│   │   ├── orders.py             # Pedidos activos
│   │   ├── exclusions.py         # Exclusiones
│   │   ├── audit.py              # Logs
│   │   ├── restore.py            # Restaurar eliminados
│   │   └── reports.py            # Reportes
│   │
│   ├── auth/                     # /api/auth/*
│   ├── public/                   # /api/public/* (sin auth)
│   ├── tables/                   # /api/tables/*
│   ├── diner/                    # /api/diner/*
│   ├── kitchen/                  # /api/kitchen/*
│   ├── waiter/                   # /api/waiter/*
│   ├── billing/                  # /api/billing/*
│   └── content/                  # /api/content/*
│
└── services/                      # Lógica de negocio
    ├── base_service.py           # BaseCRUDService, BranchScopedService
    │
    ├── domain/                   # Servicios de dominio
    │   ├── category_service.py
    │   ├── subcategory_service.py
    │   ├── product_service.py
    │   ├── branch_service.py
    │   ├── table_service.py
    │   ├── sector_service.py
    │   ├── allergen_service.py
    │   ├── staff_service.py
    │   └── promotion_service.py
    │
    ├── crud/                     # Utilidades CRUD
    │   ├── repository.py         # TenantRepository, BranchRepository
    │   ├── soft_delete.py        # soft_delete(), restore_entity()
    │   ├── cascade_delete.py     # CascadeDeleteService
    │   ├── entity_builder.py     # EntityOutputBuilder
    │   └── audit.py              # log_create/update/delete()
    │
    ├── permissions/              # Sistema de permisos
    │   ├── context.py            # PermissionContext
    │   ├── strategies.py         # Admin/Manager/Kitchen/WaiterStrategy
    │   └── decorators.py         # @require_admin, @require_management
    │
    ├── events/                   # Publicación de eventos
    │   ├── admin_events.py       # publish_entity_created/updated/deleted()
    │   ├── domain_event.py       # Event dataclass
    │   └── publisher.py          # publish_event()
    │
    ├── payments/                 # Procesamiento de pagos
    │   ├── allocation.py         # Lógica FIFO
    │   ├── circuit_breaker.py    # Resiliencia
    │   ├── mp_webhook.py         # Mercado Pago
    │   └── webhook_retry.py      # Reintentos
    │
    ├── catalog/                  # Vistas de catálogo
    │   ├── product_view.py       # get_product_complete()
    │   └── recipe_sync.py        # Sincronización Recipe→Product
    │
    └── rag/                      # AI/RAG
        └── service.py            # RAGService (Ollama)
```

### Módulo shared

```
shared/
│
├── config/                        # Configuración
│   ├── settings.py               # Pydantic Settings (env vars)
│   ├── logging.py                # Structured logging
│   └── constants.py              # Roles, RoundStatus, event types
│
├── security/                      # Seguridad
│   ├── auth.py                   # JWT/HMAC verification, current_user
│   ├── password.py               # Bcrypt hashing
│   ├── token_blacklist.py        # Redis-based revocation
│   └── rate_limit.py             # Login throttling
│
├── infrastructure/                # Infraestructura
│   ├── db.py                     # SessionLocal, get_db(), safe_commit()
│   │
│   └── events/                   # Redis Pub/Sub (paquete modular)
│       ├── redis_pool.py         # get_redis_pool(), sync client
│       ├── event_schema.py       # Event dataclass
│       ├── event_types.py        # ROUND_SUBMITTED, etc.
│       ├── channels.py           # channel_branch_waiters(), etc.
│       ├── publisher.py          # publish_event() con retry
│       ├── routing.py            # publish_to_waiters(), publish_to_kitchen()
│       ├── domain_publishers.py  # publish_round_event(), etc.
│       ├── circuit_breaker.py    # EventCircuitBreaker
│       ├── health_checks.py      # check_redis_async_health()
│       └── __init__.py           # Re-exports
│
└── utils/                         # Utilidades
    ├── exceptions.py             # NotFoundError, ForbiddenError, ValidationError
    ├── validators.py             # validate_image_url (SSRF prevention)
    ├── health.py                 # Health check decorators
    ├── schemas.py                # Shared Pydantic models
    └── admin_schemas.py          # CategoryOutput, ProductOutput, etc.
```

---

## Integraciones

### Base de Datos (PostgreSQL)

```
┌─────────────────────────────────────────────────────────────────┐
│                        PostgreSQL 16                             │
│                      (pgvector extension)                        │
├─────────────────────────────────────────────────────────────────┤
│  ┌─────────────┐                                                │
│  │   Tables    │  47 tablas organizadas por dominio             │
│  └─────────────┘                                                │
│                                                                  │
│  ┌─────────────┐                                                │
│  │   Indexes   │  Índices en tenant_id, branch_id, is_active    │
│  └─────────────┘                                                │
│                                                                  │
│  ┌─────────────┐                                                │
│  │  pgvector   │  Embeddings para RAG (knowledge documents)     │
│  └─────────────┘                                                │
└─────────────────────────────────────────────────────────────────┘
         │
         │ SQLAlchemy 2.0
         │ Connection Pool
         │
         ▼
┌─────────────────────────────────────────────────────────────────┐
│                      Backend REST API                            │
│                                                                  │
│  SessionLocal ──▶ get_db() dependency ──▶ Repositories          │
└─────────────────────────────────────────────────────────────────┘
```

### Redis

```
┌─────────────────────────────────────────────────────────────────┐
│                          Redis 7                                 │
│                       (Port 6380)                                │
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│  ┌─────────────────┐  ┌─────────────────┐  ┌─────────────────┐  │
│  │    Pub/Sub      │  │  Token Blacklist │  │   Rate Limit   │  │
│  │   (Events)      │  │   (Revocation)   │  │   (Throttle)   │  │
│  └─────────────────┘  └─────────────────┘  └─────────────────┘  │
│                                                                  │
│  Channels:                                                       │
│  • channel:branch:{id}:all                                      │
│  • channel:branch:{id}:waiters                                  │
│  • channel:branch:{id}:kitchen                                  │
│  • channel:sector:{branch_id}:{sector_id}                       │
│  • channel:session:{id}                                         │
│                                                                  │
└─────────────────────────────────────────────────────────────────┘
         │                    │                    │
         │ Async Pool         │ Sync Pool          │
         │ (50 conn)          │ (20 conn)          │
         │                    │                    │
         ▼                    ▼                    ▼
┌──────────────┐     ┌──────────────┐     ┌──────────────┐
│  Event       │     │   Auth       │     │  Rate        │
│  Publishing  │     │  Service     │     │  Limiter     │
└──────────────┘     └──────────────┘     └──────────────┘
```

### WebSocket Gateway

```
┌─────────────────────────────────────────────────────────────────┐
│                    Backend REST API (:8000)                      │
│                                                                  │
│  Service ──▶ publish_event() ──▶ Redis Pub/Sub                  │
└─────────────────────────────────────────────────────────────────┘
                                      │
                               Redis Channel
                                      │
                                      ▼
┌─────────────────────────────────────────────────────────────────┐
│                    WS Gateway (:8001)                            │
│                                                                  │
│  RedisSubscriber ◀── Subscribe to channels                      │
│         │                                                        │
│         ▼                                                        │
│  ConnectionManager ──▶ Broadcast to WebSocket clients           │
│         │                                                        │
│         ▼                                                        │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐              │
│  │  /ws/admin  │  │ /ws/waiter  │  │ /ws/kitchen │              │
│  │             │  │             │  │             │              │
│  │  Dashboard  │  │  pwaWaiter  │  │  Kitchen    │              │
│  └─────────────┘  └─────────────┘  └─────────────┘              │
└─────────────────────────────────────────────────────────────────┘
```

---

## Consideraciones de Escalabilidad

### Horizontal Scaling

El backend está diseñado para escalar horizontalmente:

**Stateless Design**: Cada instancia del API es independiente. El estado se almacena en PostgreSQL y Redis, permitiendo agregar instancias detrás de un load balancer.

**Connection Pooling**: Los pools de conexiones a PostgreSQL y Redis están configurados para soportar múltiples workers.

**Event-Driven**: La comunicación asíncrona vía Redis desacopla los componentes, permitiendo que escalen independientemente.

### Optimizaciones Implementadas

**Query Optimization**:
- Eager loading obligatorio en repositorios
- Índices en campos de filtro frecuente (tenant_id, branch_id, is_active)
- Paginación con límites máximos

**Caching Strategy**:
- Redis pool singleton reutilizado
- Sector assignment cache en WS Gateway
- Token blacklist con TTL

**Rate Limiting**:
- Por IP en login (5/60s)
- Por conexión en WebSocket (20/s)
- Por endpoint en billing (10-20/min)

---

## Referencias

- [README.md](README.md): Documentación general del backend
- [shared/README.md](shared/README.md): Documentación de módulos compartidos
- [CLAUDE.md](../CLAUDE.md): Documentación completa del proyecto
