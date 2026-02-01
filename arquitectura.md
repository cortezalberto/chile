# Arquitectura del Sistema Integrador

## Documento Técnico de Arquitectura - Estado Actual Enero 2026

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
13. [Métricas y Observabilidad](#13-métricas-y-observabilidad)
14. [Decisiones Arquitectónicas](#14-decisiones-arquitectónicas)

---

## 1. Visión General del Sistema

### 1.1 Propósito y Alcance

El sistema **Integrador** constituye una plataforma integral de gestión de restaurantes diseñada para orquestar la totalidad de operaciones desde el momento en que un cliente escanea un código QR hasta la finalización del pago. La arquitectura ha sido concebida con un enfoque multi-tenant que permite a múltiples restaurantes operar de forma completamente aislada sobre la misma infraestructura, maximizando la eficiencia operativa mientras garantiza la segregación absoluta de datos sensibles.

La plataforma se materializa a través de cinco componentes principales que colaboran en tiempo real mediante una combinación de APIs REST para operaciones transaccionales y WebSockets para sincronización instantánea de eventos. Esta dualidad de protocolos permite alcanzar un balance óptimo entre consistencia de datos y experiencia de usuario fluida, donde las operaciones críticas como pagos y confirmaciones de pedidos mantienen garantías ACID mientras las actualizaciones de estado fluyen instantáneamente a través del sistema.

El sistema ha sido optimizado para soportar entre 400 y 600 usuarios concurrentes por instancia, con capacidad de escalar horizontalmente mediante la adición de instancias del WebSocket Gateway que comparten estado a través de Redis. Esta arquitectura permite que un restaurante con múltiples sucursales pueda gestionar simultáneamente cientos de mesas activas sin degradación perceptible del rendimiento.

### 1.2 Principios Arquitectónicos Fundamentales

La arquitectura del sistema Integrador se fundamenta en cinco principios rectores que guían todas las decisiones de diseño y que han sido refinados a través de múltiples ciclos de auditoría y optimización durante enero de 2026.

El principio de **Separación de Responsabilidades (SoC)** establece que cada componente del sistema posee una responsabilidad claramente definida y acotada. El Dashboard gestiona operaciones administrativas, pwaMenu maneja la experiencia del cliente, pwaWaiter optimiza el flujo de trabajo del mesero, el REST API procesa lógica de negocio, y el WebSocket Gateway orquesta comunicación en tiempo real. Esta separación no es meramente organizativa sino que se refleja en la estructura física del código, donde cada componente reside en su propio directorio con sus propias dependencias y configuraciones.

El principio de **Arquitectura Limpia (Clean Architecture)** se implementa estrictamente en el backend, donde los routers actúan como controladores delgados que únicamente manejan concerns HTTP, los servicios de dominio encapsulan toda la lógica de negocio, y los repositorios abstraen completamente el acceso a datos. Esta estructura garantiza que los cambios en una capa no propaguen efectos colaterales a otras, facilitando tanto el testing como la evolución del sistema.

El **Diseño Reactivo** permea todos los frontends mediante Zustand como gestor de estado con patrones de suscripción selectiva que previenen re-renderizados innecesarios. La arquitectura de eventos del WebSocket Gateway permite que los cambios se propaguen instantáneamente a todos los clientes conectados sin polling, manteniendo sincronización en tiempo real entre múltiples dispositivos que interactúan con la misma sesión de mesa.

La **Seguridad en Profundidad** implementa múltiples capas de protección incluyendo autenticación JWT con tokens de corta duración (15 minutos para access tokens), validación de origen en WebSockets, rate limiting por endpoint y por conexión, validación exhaustiva de entrada para prevenir ataques de inyección, y un patrón fail-closed donde cualquier error de seguridad resulta en denegación de acceso.

La **Escalabilidad Horizontal** se logra mediante sharding de locks, broadcast paralelo con batching, y pools de conexiones Redis configurables. El sistema implementa worker pools para broadcasting y circuit breakers para resiliencia ante fallos de dependencias externas.

### 1.3 Stack Tecnológico

El stack tecnológico ha sido seleccionado para maximizar productividad de desarrollo, rendimiento en producción, y mantenibilidad a largo plazo:

| Capa | Tecnología | Versión | Justificación |
|------|------------|---------|---------------|
| **Frontend Dashboard** | React 19, Zustand, TailwindCSS 4 | 19.2.0, 5.0.9, 4.1.18 | React Compiler para memoización automática, Zustand v5 con selectores |
| **Frontend pwaMenu** | React 19, Zustand, i18next | 19.2.0, 5.0.9, 25.7.3 | PWA offline-first, internacionalización es/en/pt |
| **Frontend pwaWaiter** | React 19, Zustand, Push API | 19.2.0, 5.0.9 | Notificaciones push nativas, sector grouping |
| **REST API** | FastAPI, SQLAlchemy 2.0, Pydantic v2 | 0.109+, 2.0+, 2.0+ | Async nativo, tipado fuerte, validación automática |
| **WebSocket Gateway** | FastAPI WebSocket, Redis Streams | 0.109+ | Conexiones bidireccionales, entrega garantizada |
| **Base de Datos** | PostgreSQL 16 + pgvector | 16.x | ACID, soporte vectorial para RAG |
| **Cache/Mensajería** | Redis 7 | 7.x | Pub/Sub, Streams, rate limiting, token blacklist |
| **Containerización** | Docker Compose | 2.x | Orquestación local de servicios |

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
│   15 stores     │  Modular store  │   3 stores      │                       │
│   100 tests     │  i18n es/en/pt  │  Sector groups  │                       │
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
│  │  (9 grupos, 16 admin)   │    │    │  (12,605 líneas, 51 archivos)   │    │
│  └───────────┬─────────────┘    │    └─────────────────────────────────┘    │
│              │                  │    ┌─────────────────────────────────┐    │
│  ┌───────────▼─────────────┐    │    │      Redis Subscriber           │    │
│  │    Domain Services      │    │    │  (Streams + Pub/Sub híbrido)    │    │
│  │  (10 servicios Clean    │◄───┼────►└─────────────────────────────────┘   │
│  │   Architecture)         │    │    ┌─────────────────────────────────┐    │
│  └───────────┬─────────────┘    │    │        Event Router             │    │
│              │                  │    │   (tenant filter, broadcast)    │    │
│  ┌───────────▼─────────────┐    │    └─────────────────────────────────┘    │
│  │     Repositories        │    │    ┌─────────────────────────────────┐    │
│  │  (TenantRepository,     │    │    │      Worker Pool                │    │
│  │   BranchRepository)     │    │    │  (SCALE-HIGH-01: 10 workers)    │    │
│  └───────────┬─────────────┘    │    └─────────────────────────────────┘    │
└──────────────┼──────────────────┴───────────────────────────────────────────┘
               │
┌──────────────▼──────────────────────────────────────────────────────────────┐
│                              CAPA DE DATOS                                   │
├─────────────────────────────────┬───────────────────────────────────────────┤
│     PostgreSQL (:5432)          │           Redis (:6380)                   │
│  ┌─────────────────────────┐    │    ┌─────────────────────────────────┐    │
│  │   52 Modelos SQLAlchemy │    │    │   Streams (eventos críticos)    │    │
│  │   18 archivos dominio   │    │    │   Pub/Sub (eventos tiempo real) │    │
│  │   AuditMixin universal  │    │    │   Token Blacklist               │    │
│  └─────────────────────────┘    │    │   Rate Limiting (Lua scripts)   │    │
│                                 │    │   Sector Cache (TTL 60s)        │    │
│                                 │    └─────────────────────────────────┘    │
└─────────────────────────────────┴───────────────────────────────────────────┘
```

### 2.2 Componentes y Responsabilidades

#### Dashboard (Puerto 5177)

El Dashboard constituye el centro de control administrativo del sistema, implementado como una Single Page Application con React 19 y el React Compiler habilitado para memoización automática. La aplicación gestiona 15 stores Zustand con persistencia en localStorage, cada uno especializado en un dominio específico: autenticación, sucursales, categorías, productos, alérgenos, personal, promociones, y mesas.

La arquitectura interna se organiza en 19 páginas funcionales que cubren todo el espectro administrativo: gestión de sucursales y sectores, catálogo completo con precios por sucursal, sistema de alérgenos con reacciones cruzadas, personal con roles por sucursal, y promociones multi-sucursal. El sistema de mesas implementa un workflow de 5 estados con animaciones visuales que reflejan el estado de cada orden en tiempo real.

Los componentes UI, organizados en 25 primitivos reutilizables con React.memo optimizado, logran una reducción del 35% en re-renderizados innecesarios. El patrón useFormModal y useConfirmDialog ha sido adoptado en 9 de 11 páginas con formularios, consolidando la gestión de estado modal en hooks reutilizables.

El Dashboard implementa sincronización multi-pestaña mediante BroadcastChannel para autenticación, garantizando que el logout en una pestaña se propague instantáneamente a todas las demás. Los 100 tests Vitest cubren stores, hooks personalizados, y flujos críticos de negocio.

#### pwaMenu (Puerto 5176)

pwaMenu representa la interfaz principal de interacción con clientes, diseñada como una Progressive Web App completamente funcional offline. La arquitectura de service workers con Workbox implementa estrategias de cache diferenciadas: CacheFirst para imágenes de productos (30 días de retención), NetworkFirst con timeout de 5 segundos para APIs, y SPA fallback para navegación offline.

El sistema soporta internacionalización completa en español, inglés y portugués mediante i18next, con detección automática del idioma del navegador y persistencia de la preferencia del usuario. Cada error de validación y mensaje de la interfaz posee una clave i18n correspondiente en los tres archivos de traducción.

El flujo de usuario comienza cuando el cliente escanea un código QR en la mesa, lo que inicia una sesión vinculada al dispositivo mediante un UUID persistido en localStorage. Múltiples comensales pueden unirse a la misma sesión usando códigos de 4 dígitos, habilitando ordenamiento colaborativo donde cada comensal mantiene su propio carrito pero visualiza los pedidos de todos. El sistema de confirmación grupal, implementado mediante el componente RoundConfirmationPanel, requiere que todos los comensales aprueben antes de enviar la ronda a cocina.

La arquitectura de estado utiliza un tableStore modular dividido en cuatro archivos: store.ts con la definición Zustand y acciones, selectors.ts con hooks memoizados, helpers.ts con funciones puras para cálculos, y types.ts con interfaces TypeScript. Este patrón ha probado ser altamente mantenible y testeable.

El sistema de filtrado avanzado permite a los clientes excluir productos por alérgenos (con detección de reacciones cruzadas), preferencias dietéticas (vegetariano, vegano, keto, bajo en sodio), y métodos de cocción. Estas preferencias se persisten como "preferencias implícitas" vinculadas al device_id, permitiendo que clientes recurrentes encuentren sus filtros ya aplicados mediante el hook useImplicitPreferences.

#### pwaWaiter (Puerto 5178)

pwaWaiter optimiza el flujo de trabajo de meseros mediante una interfaz móvil diseñada para condiciones de conectividad variable. La arquitectura implementa un sistema de cola de reintentos para operaciones fallidas, garantizando que ninguna acción se pierda incluso con conectividad intermitente.

Los meseros visualizan únicamente las mesas de los sectores asignados para el día actual, con la vista organizada en grupos por sector. Cada grupo muestra un encabezado con el nombre del sector, conteo de mesas, e indicadores de urgencia cuando hay órdenes pendientes o llamadas de servicio activas.

La funcionalidad "Comanda Rápida" permite a meseros tomar pedidos para clientes sin smartphone, utilizando un menú compacto sin imágenes optimizado para rendimiento. El componente AutogestionModal implementa una vista dividida con el catálogo a la izquierda y el carrito a la derecha, facilitando la selección rápida de productos.

El sistema de notificaciones push utiliza Web Push API para alertar a meseros cuando una ronda está lista para servir o cuando un cliente solicita atención. El servicio de notificaciones gestiona permisos, suscripción a push, y reproducción de sonidos de alerta.

La verificación de asignación de sucursal ocurre en dos fases: selección pre-login de sucursal desde el endpoint público `/api/public/branches`, seguida de verificación post-login mediante `/api/waiter/verify-branch-assignment`. Este flujo garantiza que los meseros solo puedan acceder a sucursales donde están asignados para el día actual.

#### REST API (Puerto 8000)

El REST API constituye el núcleo de procesamiento de lógica de negocio del sistema. Implementado con FastAPI, la arquitectura sigue estrictamente el patrón Clean Architecture con cuatro capas bien definidas que han sido refinadas a través de múltiples ciclos de refactorización.

Los **routers** se organizan en 9 grupos funcionales con 16 routers administrativos dedicados. Cada router actúa como controlador delgado que únicamente maneja concerns HTTP: parsing de parámetros mediante Pydantic, inyección de dependencias para autenticación, y construcción de respuestas. La lógica de negocio se delega íntegramente a servicios de dominio.

Los **servicios de dominio**, implementados en el directorio `rest_api/services/domain/`, encapsulan todas las reglas de negocio. Los 10 servicios activos (CategoryService, SubcategoryService, ProductService, AllergenService, BranchService, SectorService, TableService, StaffService, PromotionService, TicketService) heredan de clases base que proporcionan operaciones CRUD estándar con hooks de extensión: `_validate_create`, `_validate_update`, `_after_create`, `_after_delete`.

Los **repositorios** `TenantRepository` y `BranchRepository` abstraen completamente el acceso a datos, proporcionando métodos tipados con eager loading preconfigurado que previene el problema N+1. Los repositorios implementan filtrado automático por tenant_id y branch_id según corresponda, garantizando aislamiento multi-tenant a nivel de infraestructura.

Los **modelos** SQLAlchemy, organizados en 18 archivos por dominio, definen 52 clases que heredan de AuditMixin para trazabilidad automática. Cada entidad registra quién la creó, modificó o eliminó, junto con timestamps precisos.

#### WebSocket Gateway (Puerto 8001)

El WebSocket Gateway proporciona comunicación bidireccional en tiempo real entre el servidor y todos los clientes conectados. Con 12,605 líneas de código organizadas en 51 archivos Python, representa el componente más complejo del sistema desde la perspectiva de concurrencia y resiliencia.

La arquitectura modular se organiza en dos capas principales: `core/` contiene los módulos extraídos de los archivos monolíticos originales (connection_manager.py pasó de 987 a 495 líneas, redis_subscriber.py de 666 a 326 líneas), mientras que `components/` implementa la arquitectura de dominios con 12 subdirectorios especializados.

El **ConnectionManager** orquesta el ciclo de vida de conexiones utilizando composición de módulos especializados: `ConnectionLifecycle` maneja registro y desregistro con locks apropiados, `ConnectionBroadcaster` implementa envío paralelo con worker pool de 10 workers (SCALE-HIGH-01), `ConnectionCleanup` elimina conexiones muertas y stale, y `ConnectionStats` agrega métricas.

El **RedisSubscriber** procesa eventos mediante un sistema híbrido de Pub/Sub para eventos de tiempo real y Redis Streams para eventos críticos que requieren entrega garantizada. El `EventDropRateTracker` monitorea tasas de descarte y emite alertas cuando superan el 5%. El `StreamConsumer` (ARCH-STREAM-01) implementa consumer groups con capacidad de rewind y dead letter queue para mensajes irrecuperables.

El sistema de **endpoints** WebSocket implementa una jerarquía de clases con WebSocketEndpointBase como clase abstracta que define hooks de ciclo de vida, JWTWebSocketEndpoint que añade revalidación periódica de tokens cada 5 minutos, y endpoints concretos (WaiterEndpoint, KitchenEndpoint, AdminEndpoint, DinerEndpoint) que implementan la lógica específica de cada rol.

---

## 3. Modelo de Datos y Dominio

### 3.1 Organización por Dominios

El sistema define 52 modelos SQLAlchemy organizados en 18 archivos por dominio coherente, cada uno encapsulado en su propio archivo dentro de `rest_api/models/`:

```
rest_api/models/
├── __init__.py          # Re-exporta los 52 modelos
├── base.py              # Base declarativa, AuditMixin (2 clases)
├── tenant.py            # Tenant, Branch (2 modelos)
├── user.py              # User, UserBranchRole (2 modelos)
├── catalog.py           # Category, Subcategory, Product, BranchProduct (4 modelos)
├── allergen.py          # Allergen, ProductAllergen, AllergenCrossReaction (3 modelos)
├── ingredient.py        # IngredientGroup, Ingredient, SubIngredient, ProductIngredient (4 modelos)
├── product_profile.py   # 12 modelos de perfiles dietéticos/cocción/sabor/M:N
├── sector.py            # BranchSector, WaiterSectorAssignment (2 modelos)
├── table.py             # Table, TableSession (2 modelos)
├── customer.py          # Customer, Diner (2 modelos)
├── order.py             # Round, RoundItem (2 modelos)
├── kitchen.py           # KitchenTicket, KitchenTicketItem, ServiceCall (3 modelos)
├── billing.py           # Check, Payment, Charge, Allocation (4 modelos)
├── knowledge.py         # KnowledgeDocument, ChatLog (2 modelos para RAG)
├── promotion.py         # Promotion, PromotionBranch, PromotionItem (3 modelos)
├── exclusion.py         # BranchCategoryExclusion, BranchSubcategoryExclusion (2 modelos)
├── recipe.py            # Recipe, RecipeAllergen (2 modelos)
└── audit.py             # AuditLog (1 modelo)
```

### 3.2 Jerarquía de Entidades Principal

La jerarquía de entidades refleja la estructura organizativa de un restaurante multi-sucursal:

```
Tenant (Restaurante)
│
├── Branch (Sucursal) [1:N]
│   │
│   ├── Category (Categoría) [1:N]
│   │   └── Subcategory (Subcategoría) [1:N]
│   │       └── Product (Producto) [1:N]
│   │           ├── BranchProduct (Precio por sucursal) [1:N]
│   │           ├── ProductAllergen (Alérgenos) [M:N con presence_type y risk_level]
│   │           ├── ProductIngredient (Ingredientes) [M:N]
│   │           └── ProductCookingMethod, ProductFlavor, ProductTexture [M:N con AuditMixin]
│   │
│   ├── BranchSector (Sector) [1:N]
│   │   ├── Table (Mesa) [1:N]
│   │   │   └── TableSession (Sesión activa) [0:1]
│   │   │       └── Diner (Comensal con device_id) [1:N]
│   │   │           └── Round (Ronda con confirmed_by_user_id) [1:N]
│   │   │               └── RoundItem (Ítem de ronda) [1:N]
│   │   │                   └── KitchenTicketItem [1:N]
│   │   │
│   │   └── WaiterSectorAssignment (Asignación diaria) [1:N]
│   │
│   ├── Check (table: app_check) [1:N por sesión]
│   │   ├── Charge (Cargo) [1:N]
│   │   ├── Payment (Pago) [1:N]
│   │   └── Allocation (Asignación FIFO) [1:N]
│   │
│   ├── KitchenTicket [1:N]
│   │
│   └── ServiceCall (Llamada de servicio) [1:N]
│
├── User (Usuario) [M:N via UserBranchRole]
│   └── UserBranchRole (Rol por sucursal)
│       roles: ADMIN | MANAGER | KITCHEN | WAITER
│
├── CookingMethod, FlavorProfile, TextureProfile, CuisineType [Catálogos tenant-scoped]
│
└── IngredientGroup → Ingredient → SubIngredient [Jerarquía de ingredientes]
```

### 3.3 AuditMixin Universal

Todos los modelos heredan de `AuditMixin`, proporcionando trazabilidad completa de todas las operaciones:

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

Este diseño permite soft delete universal donde ningún dato se elimina físicamente, auditoría completa de quién y cuándo realizó cada operación, y restauración de entidades eliminadas con cascade a sus dependientes.

### 3.4 Relaciones Clave y Constraints

**Productos y Precios por Sucursal**: El modelo Product actúa como maestro global mientras BranchProduct contiene el precio específico por sucursal en centavos (12550 = $125.50) junto con disponibilidad.

**Sistema de Alérgenos con Reacciones Cruzadas**: ProductAllergen registra presencia con tres niveles (CONTAINS, MAY_CONTAIN, TRACE) y riesgo (HIGH, MEDIUM, LOW). AllergenCrossReaction implementa una relación auto-referencial M:N para modelar reacciones cruzadas entre alérgenos.

**Flujo de Órdenes**: La cadena TableSession → Diner → Round → RoundItem → KitchenTicketItem representa el flujo completo desde que un comensal se sienta hasta que su orden llega a cocina. Round ahora incluye `confirmed_by_user_id` para trackear qué mesero verificó el pedido.

**Constraints de Integridad**: El sistema implementa UniqueConstraint en Category(branch_id, name), Subcategory(category_id, name), todos los catálogos tenant-scoped (CookingMethod, etc.), y Round(table_session_id, idempotency_key). CheckConstraints validan que precios sean no negativos y que cantidades sean positivas.

---

## 4. Arquitectura del Backend REST API

### 4.1 Clean Architecture en Detalle

La implementación de Clean Architecture en el backend garantiza que las dependencias fluyen únicamente hacia adentro, desde capas externas hacia el núcleo de dominio:

```
┌─────────────────────────────────────────────────────────────────┐
│                         ROUTERS                                  │
│   • 9 grupos: auth, public, tables, content, diner, waiter,     │
│     kitchen, billing, admin (16 sub-routers)                    │
│   • Parsing de requests HTTP                                     │
│   • Validación de schemas Pydantic                               │
│   • Inyección de dependencias (current_user, get_db)            │
│   • NUNCA contienen lógica de negocio                            │
└─────────────────────────────┬───────────────────────────────────┘
                              │ Delega a
┌─────────────────────────────▼───────────────────────────────────┐
│                     DOMAIN SERVICES                              │
│   • 10 servicios: Category, Subcategory, Product, Allergen,     │
│     Branch, Sector, Table, Staff, Promotion, Ticket             │
│   • Heredan de BaseCRUDService o BranchScopedService            │
│   • Hooks: _validate_create, _validate_update, _after_*         │
│   • Transformación entidad → output schema                       │
│   • Publicación de eventos de dominio                            │
└─────────────────────────────┬───────────────────────────────────┘
                              │ Usa
┌─────────────────────────────▼───────────────────────────────────┐
│                      REPOSITORIES                                │
│   • TenantRepository: auto-filtra por tenant_id                 │
│   • BranchRepository: auto-filtra por branch_id + tenant_id     │
│   • Eager loading preconfigurado (selectinload, joinedload)     │
│   • Métodos tipados: find_by_id, find_all, find_by_branch       │
│   • NUNCA contienen lógica de negocio                            │
└─────────────────────────────┬───────────────────────────────────┘
                              │ Opera sobre
┌─────────────────────────────▼───────────────────────────────────┐
│                        MODELS                                    │
│   • 52 entidades SQLAlchemy en 18 archivos de dominio           │
│   • AuditMixin universal para trazabilidad                      │
│   • Relaciones con back_populates explícitos                    │
│   • Constraints e índices para integridad y rendimiento         │
└─────────────────────────────────────────────────────────────────┘
```

### 4.2 Servicios de Dominio

El sistema implementa 10 servicios de dominio que heredan de clases base especializadas. `BaseCRUDService[Model, Output]` proporciona operaciones CRUD estándar con hooks de extensión, mientras `BranchScopedService[Model, Output]` añade filtrado automático por branch_id.

```python
class BaseCRUDService[Model, Output](ABC):
    def __init__(self, db: Session, model: type[Model], output_schema: type[Output], entity_name: str):
        self._db = db
        self._repo = TenantRepository(model, db)
        self._output_schema = output_schema
        self._entity_name = entity_name

    def create(self, data: dict, tenant_id: int, user_id: int, user_email: str) -> Output:
        self._validate_create(data, tenant_id)  # Hook de validación
        entity = self._model(**data, tenant_id=tenant_id)
        set_created_by(entity, user_id, user_email)
        self._db.add(entity)
        safe_commit(self._db)
        self._after_create(entity, user_id, user_email)  # Hook post-creación
        return self.to_output(entity)

    # Hooks para sobreescribir en subclases
    def _validate_create(self, data: dict, tenant_id: int) -> None: ...
    def _after_create(self, entity: Model, user_id: int, user_email: str) -> None: ...
```

Los servicios implementados cubren todos los dominios principales:

| Servicio | Entidad | Características Especiales |
|----------|---------|----------------------------|
| `CategoryService` | Category | Validación de unicidad de nombre por branch |
| `SubcategoryService` | Subcategory | Validación de categoría padre existe |
| `ProductService` | Product | Gestión de BranchProduct, alérgenos, ingredientes, perfiles |
| `AllergenService` | Allergen | Manejo de reacciones cruzadas M:N |
| `BranchService` | Branch | Gestión de configuración de sucursal |
| `SectorService` | BranchSector | Validación de branch_id |
| `TableService` | Table | Generación de códigos únicos alfanuméricos |
| `StaffService` | User + UserBranchRole | Restricciones MANAGER, multi-branch roles |
| `PromotionService` | Promotion | Branches e items asociados, validación de fechas |
| `TicketService` | KitchenTicket | Transiciones de estado validadas |

### 4.3 Sistema de Permisos (Strategy Pattern)

El sistema de permisos utiliza Strategy Pattern con Interface Segregation Principle para manejar las diferencias entre roles de forma extensible:

```python
class PermissionContext:
    """Facade que simplifica el acceso a permisos."""
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
        if not self.is_management:
            raise ForbiddenError("acceso de gestión requerido")

    def can(self, action: Action, entity_type: str, **context) -> bool:
        return self._strategy.can(action, entity_type, self._user, **context)
```

Las estrategias implementadas cubren cada rol con sus permisos específicos:

- **AdminStrategy**: Acceso total sin restricciones
- **ManagerStrategy**: CRUD limitado a Staff, Tables, Allergens, Promotions en branches asignadas; sin delete
- **KitchenStrategy**: Solo lectura de productos y actualización de tickets/rounds
- **WaiterStrategy**: Lectura de mesas del sector asignado, actualización de rounds

Los mixins `NoCreateMixin`, `NoDeleteMixin`, `BranchFilterMixin` permiten composición flexible de comportamientos.

### 4.4 Estructura de Routers

Los routers se organizan por dominio de responsabilidad, con separación clara entre operaciones públicas, autenticadas, y administrativas:

```
rest_api/routers/
├── _common/              # Utilidades compartidas
│   ├── base.py           # Dependencias comunes (get_db, current_user)
│   └── pagination.py     # Pagination con limit/offset estandarizado
├── admin/                # CRUD administrativo (16 routers)
│   ├── __init__.py       # Monta todos los sub-routers bajo /api/admin
│   ├── products.py       # GET/POST/PUT/DELETE /api/admin/products
│   ├── categories.py     # Categorías con validación branch
│   ├── staff.py          # Personal con roles por sucursal
│   ├── allergens.py      # Alérgenos con cross-reactions
│   └── ...               # 11 routers adicionales
├── auth/                 # Autenticación JWT + refresh HttpOnly
├── public/               # Sin autenticación (menú, health)
├── tables/               # Sesiones de mesa (QR flow)
├── content/              # Catálogos, ingredientes, recetas, RAG
├── diner/                # Operaciones de comensal (X-Table-Token)
├── waiter/               # Operaciones de mesero (sector filtering)
├── kitchen/              # Rounds y tickets de cocina
└── billing/              # Pagos y webhooks Mercado Pago
```

---

## 5. Arquitectura del WebSocket Gateway

### 5.1 Arquitectura Modular

El WebSocket Gateway implementa una arquitectura modular que reduce la complejidad mediante composición de componentes especializados. La refactorización ARCH-MODULAR redujo los archivos monolíticos originales a la mitad de líneas mediante extracción de responsabilidades:

```
ws_gateway/
├── main.py                    # 415 líneas - App FastAPI, lifespan, endpoints
├── connection_manager.py      # 495 líneas - Orquestador delgado
├── redis_subscriber.py        # 326 líneas - Orquestador delgado
│
├── core/                      # Módulos extraídos de los monolitos
│   ├── connection/            # 1,203 líneas total
│   │   ├── lifecycle.py       # Connect/disconnect con locks apropiados
│   │   ├── broadcaster.py     # Worker pool + batch broadcasting
│   │   ├── cleanup.py         # Limpieza de conexiones stale/dead
│   │   └── stats.py           # Agregación de estadísticas
│   │
│   └── subscriber/            # 924 líneas total
│       ├── drop_tracker.py    # Monitoreo de tasas de descarte
│       ├── validator.py       # Validación de schema de eventos
│       ├── processor.py       # Procesamiento batch
│       └── stream_consumer.py # Redis Streams con rewind
│
└── components/                # Arquitectura de dominios
    ├── core/                  # Constants, context, DI container
    ├── connection/            # Index, locks, heartbeat, rate limiter
    ├── events/                # WebSocketEvent, EventRouter
    ├── broadcast/             # BroadcastRouter, TenantFilter
    ├── auth/                  # JWT/TableToken strategies
    ├── endpoints/             # Base, mixins, handlers
    ├── resilience/            # Circuit breaker, retry with jitter
    ├── metrics/               # MetricsCollector, Prometheus
    ├── data/                  # SectorRepository + cache TTL
    └── redis/                 # Lua scripts para atomicidad
```

### 5.2 Componentes Clave

**ConnectionIndex** actúa como Value Object que mantiene todos los índices de conexiones y mappings inversos. Los índices principales incluyen `by_user`, `by_branch`, `by_session`, `by_sector`, `admins_by_branch`, y `kitchen_by_branch`. Los mappings inversos (`ws_to_user`, `ws_to_tenant`, etc.) permiten O(1) cleanup en disconnect.

**LockManager** implementa locks sharded para reducir contención en escenarios de alta concurrencia. El orden de adquisición de locks está estrictamente definido para prevenir deadlocks: connection_counter_lock → user_lock → branch_locks → sector_lock → session_lock → dead_connections_lock. El componente LockSequence valida que este orden se respete y lanza `DeadlockRiskError` ante violaciones.

**BroadcastRouter** implementa Strategy Pattern con dos estrategias intercambiables: `BatchBroadcastStrategy` para batches de tamaño fijo, y `AdaptiveBatchStrategy` que ajusta el tamaño según latencia observada. El patrón Observer permite registrar observadores de métricas sin acoplar la lógica de broadcast, implementado mediante `MetricsObserverAdapter`.

**ConnectionBroadcaster** (SCALE-HIGH-01) implementa un worker pool de 10 workers asincrónicos que procesan tareas de envío desde una cola. Para broadcasts grandes (>50 conexiones), los envíos se distribuyen entre workers para procesamiento verdaderamente paralelo. Los futures permiten trackear completitud y agregar métricas.

### 5.3 Endpoints WebSocket

La jerarquía de clases de endpoints implementa Template Method para el ciclo de vida y composición mediante mixins para comportamientos reutilizables:

```python
class WebSocketEndpointBase(ABC):
    """Clase base abstracta que define el ciclo de vida."""

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

class JWTWebSocketEndpoint(WebSocketEndpointBase):
    """Añade revalidación periódica de JWT cada 5 minutos."""
    # Hereda y extiende con mixins: JWTRevalidationMixin, HeartbeatMixin

class WaiterEndpoint(JWTWebSocketEndpoint):
    """Endpoint específico para meseros con sector filtering."""
    # Comando especial: refresh_sectors para actualizar asignaciones
```

Los mixins disponibles proporcionan comportamientos composables:
- `MessageValidationMixin`: Validación de tamaño y rate limit
- `OriginValidationMixin`: Validación de header Origin
- `JWTRevalidationMixin`: Revalidación cada 5 minutos (CRIT-WS-01)
- `HeartbeatMixin`: Recording de heartbeats
- `ConnectionLifecycleMixin`: Logging estructurado de conexión

### 5.4 Eventos WebSocket

El sistema define eventos tipados para cada flujo de negocio:

```python
# Ciclo de vida de rondas (PENDING → CONFIRMED → SUBMITTED → IN_KITCHEN → READY → SERVED)
ROUND_PENDING      # Diner crea orden → admin + waiters
ROUND_CONFIRMED    # Waiter verifica → admin (puede enviar a cocina)
ROUND_SUBMITTED    # Admin envía a cocina → admin + kitchen
ROUND_IN_KITCHEN   # Cocina comienza → admin + kitchen + waiters + diners
ROUND_READY        # Cocina termina → admin + kitchen + waiters + diners
ROUND_SERVED       # Entregado → all
ROUND_CANCELED     # Cancelado → all
ROUND_ITEM_DELETED # Ítem eliminado → admin + waiters + diners

# Llamadas de servicio
SERVICE_CALL_CREATED, SERVICE_CALL_ACKED, SERVICE_CALL_CLOSED

# Facturación
CHECK_REQUESTED, CHECK_PAID, PAYMENT_APPROVED, PAYMENT_REJECTED, PAYMENT_FAILED

# Mesas
TABLE_SESSION_STARTED, TABLE_CLEARED, TABLE_STATUS_CHANGED

# Tickets de cocina
TICKET_IN_PROGRESS, TICKET_READY, TICKET_DELIVERED

# CRUD Admin
ENTITY_CREATED, ENTITY_UPDATED, ENTITY_DELETED, CASCADE_DELETE
```

El **EventRouter** determina destinatarios basándose en tipo de evento, branch_id, sector_id, y session_id. Los eventos con sector_id se filtran para enviar solo a meseros asignados a ese sector. ADMIN/MANAGER siempre reciben todos los eventos de su branch.

### 5.5 Resiliencia

**CircuitBreaker** implementa el patrón homónimo con tres estados (CLOSED → OPEN → HALF_OPEN) para proteger contra fallos de Redis. Después de 5 fallos consecutivos, el circuit se abre por 30 segundos. En HALF_OPEN permite hasta 3 requests de prueba antes de decidir si cerrar o reabrir.

**Retry con Jitter Decorrelacionado** previene thundering herd en reconexiones masivas. En lugar de exponential backoff puro (que sincroniza retries), usa jitter decorrelacionado: `sleep(random(prev_sleep, min(max_delay, prev_sleep * 3)))`.

**Stream Consumer** (ARCH-STREAM-01) implementa Redis Streams para eventos críticos que requieren entrega garantizada. Consumer groups permiten que múltiples instancias del gateway compartan carga. PEL (Pending Entries List) recovery reclama mensajes pendientes después de 30 segundos de idle. Dead letter queue retiene mensajes irrecuperables después de 3 intentos.

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

// ✅ CRÍTICO: Memoización con cache para selectores filtrados
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

### 6.2 Dashboard

El Dashboard implementa 15 stores Zustand con persistencia localStorage, organizados por dominio. El React Compiler está habilitado para memoización automática, reduciendo la necesidad de React.memo manual (aunque se mantiene en componentes críticos por compatibilidad).

La arquitectura de componentes incluye 25 primitivos UI con React.memo optimizado (Button, Modal, Input, Table, Card, Badge, etc.), que logran 35% menos re-renderizados. Los hooks personalizados `useFormModal` y `useConfirmDialog` han sido adoptados en 9/11 páginas con formularios.

El sistema de mesas implementa un workflow de 5 estados con animaciones CSS específicas:
- `animate-pulse-warning`: Amarillo para órdenes pendientes
- `animate-pulse-urgent`: Púrpura para cuenta solicitada
- `animate-status-blink`: Azul para cambios de estado
- `animate-ready-kitchen-blink`: Naranja para estado "Listo + Cocina"

Los WebSocket events se manejan mediante `useTableWebSocket` que actualiza el store con debounce para TABLE_STATUS_CHANGED (evita llamadas API duplicadas).

### 6.3 pwaMenu

pwaMenu implementa una arquitectura de store modular donde `tableStore/` se divide en 4 archivos: store.ts (definición Zustand), selectors.ts (hooks memoizados), helpers.ts (funciones puras), y types.ts (interfaces TypeScript).

El sistema de preferencias implícitas permite que clientes recurrentes encuentren sus filtros ya aplicados. El hook `useImplicitPreferences` sincroniza cambios de filtros al backend con debounce de 2 segundos, y carga preferencias guardadas al iniciar la app.

El carrito colaborativo implementa React 19 `useOptimistic` para actualizaciones optimistas con rollback automático. Cuando un comensal añade un ítem, la UI se actualiza instantáneamente mientras la operación se confirma en background.

La confirmación grupal mediante `RoundConfirmationPanel` requiere que todos los comensales en la sesión confirmen antes del envío. El estado de confirmación incluye timeout de 5 minutos y capacidad del proposer de cancelar.

### 6.4 pwaWaiter

pwaWaiter implementa agrupación de mesas por sector en `TableGrid`, donde cada grupo muestra header con nombre, conteo, e indicadores de urgencia. El componente `TableCard` muestra badges de estado con animaciones correspondientes.

El flujo de autenticación en dos fases incluye:
1. Pre-login: Selección de sucursal desde `/api/public/branches`
2. Post-login: Verificación de asignación mediante `/api/waiter/verify-branch-assignment`

La Comanda Rápida se implementa en `ComandaTab` y `AutogestionModal`, permitiendo a meseros crear órdenes para clientes sin smartphone. El menú compacto (sin imágenes) se obtiene desde un endpoint optimizado.

El sistema de notificaciones push utiliza Web Push API con service worker dedicado. Los sonidos de alerta se reproducen para eventos críticos (round ready, service call).

### 6.5 Características Comunes

**Sincronización Multi-Tab**: Dashboard y pwaWaiter usan BroadcastChannel para sincronizar autenticación. pwaMenu usa storage events con merge strategy para carritos.

**Token Refresh**: Todas las apps implementan refresh proactivo 1 minuto antes de expiración (14 min para tokens de 15 min).

**Offline Support**: Service workers con Workbox implementan estrategias diferenciadas (CacheFirst para assets, NetworkFirst para APIs).

**Logging Seguro**: Todas usan logger centralizado (`utils/logger.ts`), nunca console.* directo.

**Accesibilidad**: WCAG compliance con focus trap en modales, ARIA labels en español, keyboard navigation.

---

## 7. Patrones de Diseño Implementados

### 7.1 Catálogo de Patrones

| Patrón | Ubicación | Propósito |
|--------|-----------|-----------|
| **Strategy** | `permissions/strategies.py`, `auth/strategies.py`, `broadcast/router.py` | Comportamiento intercambiable |
| **Template Method** | `base_service.py`, `endpoints/base.py` | Hooks de extensión en flujos fijos |
| **Repository** | `crud/repository.py` | Abstracción de acceso a datos |
| **Observer** | `broadcast/router.py` | Notificación de métricas desacoplada |
| **Composite** | `auth/strategies.py` | Autenticación combinada JWT+TableToken |
| **Facade** | `PermissionContext` | Interfaz simplificada para permisos |
| **Value Object** | `WebSocketEvent`, `AuthResult` | Inmutabilidad de datos |
| **Mixin** | `endpoints/mixins.py`, `permission strategies` | Composición de comportamientos |
| **Circuit Breaker** | `resilience/circuit_breaker.py` | Protección ante fallos externos |
| **Singleton** | `core/dependencies.py` | Instancias compartidas (metrics, locks) |
| **Worker Pool** | `core/connection/broadcaster.py` | Paralelismo en broadcasting |

### 7.2 Strategy Pattern - Permisos y Autenticación

El sistema de permisos implementa 4 estrategias (Admin, Manager, Kitchen, Waiter) con selección automática basada en el rol de mayor privilegio del usuario. Cada estrategia define `can_create`, `can_read`, `can_update`, `can_delete`, y `filter_query`.

La autenticación implementa JWTAuthStrategy y TableTokenAuthStrategy con CompositeAuthStrategy para fallback. NullAuthStrategy facilita testing.

### 7.3 Template Method - Servicios y Endpoints

Los servicios de dominio usan Template Method con hooks `_validate_create`, `_validate_update`, `_after_create`, `_after_delete` que las subclases sobreescriben para lógica específica.

Los endpoints WebSocket definen `run()` como template method con hooks abstractos `create_context`, `register_connection`, `unregister_connection`, `handle_message`.

### 7.4 Observer Pattern - Métricas de Broadcast

BroadcastRouter notifica observadores después de cada broadcast sin acoplar la lógica de métricas:

```python
class BroadcastObserver(Protocol):
    def on_broadcast_complete(self, sent: int, failed: int, context: str) -> None: ...
    def on_broadcast_rate_limited(self, context: str) -> None: ...

router.add_observer(MetricsObserverAdapter(metrics_collector))
```

---

## 8. Sistema de Seguridad

### 8.1 Autenticación Dual

El sistema implementa dos mecanismos de autenticación para diferentes contextos:

**JWT para Staff** (Dashboard, pwaWaiter):
- Access token: 15 minutos de vida
- Refresh token: 7 días, almacenado en HttpOnly cookie (SEC-09)
- Claims: sub (user_id), tenant_id, branch_ids, roles, email

**Table Token para Diners** (pwaMenu):
- HMAC-SHA256 firmado
- 3 horas de vida (reducido de 8h en CRIT-04)
- Claims: table_id, branch_id, session_id

### 8.2 Revalidación de Tokens

**CRIT-WS-01**: Las conexiones WebSocket revalidan JWT cada 5 minutos verificando contra la blacklist de Redis. Si el token fue revocado, la conexión se cierra con código 4001.

**SEC-HIGH-01**: Table tokens se revalidan cada 30 minutos en conexiones WebSocket de diners.

### 8.3 Token Blacklist

La revocación de tokens se implementa mediante Redis con TTL igual al tiempo restante del token:

```python
# Fail-closed pattern: errores de Redis tratan token como blacklisted
async def is_token_blacklisted(token_jti: str) -> bool:
    try:
        redis = await get_redis_pool()
        return await redis.exists(f"auth:token:blacklist:{token_jti}") > 0
    except Exception:
        logger.error("Redis error - failing closed")
        return True  # Treat as blacklisted
```

### 8.4 Rate Limiting

**Endpoints REST**:
- Login: 5 intentos / 60 segundos por email (Lua script atómico)
- Billing endpoints: 10-20 / minuto

**WebSocket**:
- 20 mensajes / segundo por conexión (LOAD-LEVEL2)
- 10 broadcasts globales / segundo
- Close code 4029 para rate limited

### 8.5 Validación de Entrada

**SSRF Prevention** en URLs de imagen:
- Solo esquemas http/https permitidos
- Hosts bloqueados: localhost, 127.0.0.1, rangos privados, metadata endpoints cloud

**SQL Injection Prevention**:
- Parámetros siempre via bindings SQLAlchemy
- `escape_like_pattern` para caracteres especiales en LIKE

**XSS Prevention**:
- Sanitización de HTML en inputs de usuario
- CSP headers en producción

### 8.6 Security Headers

Middleware añade headers de seguridad a todas las respuestas:
- `X-Content-Type-Options: nosniff`
- `X-Frame-Options: DENY`
- `Content-Security-Policy: default-src 'self'...`
- `Strict-Transport-Security: max-age=31536000` (producción)

---

## 9. Aislamiento Multi-Tenant

### 9.1 Modelo de Tenancy

Cada restaurante constituye un tenant con aislamiento completo de datos. El `tenant_id` se propaga a través de todas las capas:

1. **JWT Claims**: Token contiene `tenant_id` del usuario
2. **Repository Filtering**: TenantRepository auto-filtra por tenant_id
3. **WebSocket Index**: Conexiones indexadas por tenant_id
4. **Broadcast Filtering**: TenantFilter valida tenant antes de enviar

### 9.2 Validación en WebSocket

El WebSocket Gateway implementa validación de tenant_id en múltiples puntos:

```python
# HIGH-AUD-02 FIX: tenant_id puede ser None (vs 0 que es ambiguo)
if context.get("tenant_id") is None:
    logger.warning("Connection without tenant_id")
    # Sector fetch solo si tenant_id válido
```

### 9.3 Prevención de Data Leakage

- Eventos nunca se envían a conexiones de otros tenants
- Queries siempre incluyen filtro por tenant_id
- Logs sanitizan PII antes de escritura

---

## 10. Optimizaciones de Rendimiento

### 10.1 Configuración para 400-600 Usuarios

| Setting | Valor | Propósito |
|---------|-------|-----------|
| `ws_max_connections_per_user` | 3 | Limita conexiones duplicadas |
| `ws_max_total_connections` | 1000 | Límite global |
| `ws_message_rate_limit` | 20/s | Rate limit por conexión |
| `ws_broadcast_batch_size` | 50 | Batch para broadcast paralelo |
| `redis_pool_max_connections` | 50 | Pool async |
| `redis_sync_pool_max_connections` | 20 | Pool sync (rate limit, blacklist) |
| `redis_event_queue_size` | 500 | Buffer de backpressure |

### 10.2 Broadcast Paralelo con Worker Pool

SCALE-HIGH-01 implementa un pool de 10 workers asincrónicos:

```python
class ConnectionBroadcaster:
    async def _broadcast_via_workers(self, connections, payload, context):
        futures = []
        for ws in connections:
            future = asyncio.get_event_loop().create_future()
            await self._queue.put((ws, payload, future))
            futures.append(future)

        results = await asyncio.gather(*futures, return_exceptions=True)
        return sum(1 for r in results if r is True)
```

Este approach logra ~160ms para broadcast a 400 usuarios vs ~4000ms con envío secuencial.

### 10.3 Sharded Locks

Los locks se dividen por granularidad para reducir contención:

- `branch_locks`: Dict de locks por branch_id (90% reducción de contención)
- `user_locks`: Dict de locks por user_id
- `sector_lock`, `session_lock`: Locks globales para operaciones específicas

### 10.4 Sector Cache con TTL

El `SectorAssignmentRepository` cachea asignaciones de sectores con TTL de 60 segundos:

```python
class SectorCache:
    _cache: dict[int, CacheEntry]  # user_id → (sector_ids, timestamp)
    _ttl_seconds: float = 60.0
    _max_entries: int = 1000

    def get(self, user_id: int) -> set[int] | None:
        entry = self._cache.get(user_id)
        if entry and time.time() - entry.timestamp < self._ttl_seconds:
            return entry.sector_ids
        return None
```

Esto reduce queries de asignación de sectores en ~80%.

### 10.5 Eager Loading Preconfigurado

Los repositorios usan eager loading por defecto para prevenir N+1:

```python
# Rounds con items, productos, y tickets
rounds = db.execute(
    select(Round).options(
        selectinload(Round.items)
        .joinedload(RoundItem.product),
        selectinload(Round.items)
        .selectinload(RoundItem.kitchen_ticket_items)
    )
).scalars().unique().all()
```

---

## 11. Flujos de Integración

### 11.1 Flujo de Orden Completo

```
┌──────────┐     ┌──────────┐     ┌──────────┐     ┌──────────┐
│  pwaMenu │────►│ REST API │────►│  Redis   │────►│WS Gateway│
│ (Diner)  │     │(validate)│     │(publish) │     │(broadcast)│
└──────────┘     └──────────┘     └──────────┘     └────┬─────┘
                                                        │
    ┌───────────────────────────────────────────────────┘
    │
    ▼
┌──────────┐     ┌──────────┐     ┌──────────┐
│Dashboard │     │pwaWaiter │     │ pwaMenu  │
│(Admin)   │     │(Confirm) │     │(Status)  │
└──────────┘     └──────────┘     └──────────┘
```

1. Diner añade ítems al carrito en pwaMenu
2. Confirmación grupal: todos los diners aprueban
3. POST `/api/diner/session/{id}/rounds` crea Round con status PENDING
4. REST API publica ROUND_PENDING a Redis
5. WS Gateway broadcast a admin + waiters del branch
6. Waiter verifica en mesa, confirma → ROUND_CONFIRMED
7. Admin envía a cocina → ROUND_SUBMITTED
8. Kitchen comienza → ROUND_IN_KITCHEN (broadcast incluye diners)
9. Kitchen termina → ROUND_READY
10. Staff entrega → ROUND_SERVED

### 11.2 Flujo de Pago Mercado Pago

```
┌──────────┐     ┌──────────┐     ┌──────────┐
│  pwaMenu │────►│ REST API │────►│Mercado   │
│(Checkout)│     │(create)  │     │Pago API  │
└──────────┘     └──────────┘     └────┬─────┘
                                       │
    ┌──────────────────────────────────┘ (webhook)
    │
    ▼
┌──────────┐     ┌──────────┐     ┌──────────┐
│ REST API │────►│  Redis   │────►│WS Gateway│
│(webhook) │     │(publish) │     │(notify)  │
└──────────┘     └──────────┘     └──────────┘
```

1. Diner inicia pago en pwaMenu
2. REST API crea preferencia en Mercado Pago
3. Redirect a checkout de MP
4. MP procesa pago y envía webhook
5. REST API valida firma, actualiza Check
6. Publica PAYMENT_APPROVED o PAYMENT_REJECTED
7. WS Gateway notifica a diners de la sesión

### 11.3 Flujo de Service Call

1. Diner toca "Llamar Mozo" en pwaMenu
2. POST `/api/diner/session/{id}/service-calls` crea ServiceCall
3. Publica SERVICE_CALL_CREATED
4. WS Gateway notifica a waiters del sector (o branch si no hay sector)
5. pwaWaiter muestra alerta con sonido
6. Waiter toca para reconocer → SERVICE_CALL_ACKED
7. Diner ve confirmación en pwaMenu
8. Waiter atiende y cierra → SERVICE_CALL_CLOSED

---

## 12. Infraestructura y DevOps

### 12.1 Docker Compose

El archivo `devOps/docker-compose.yml` orquesta 5 servicios:

```yaml
services:
  db:
    image: pgvector/pgvector:pg16
    ports: ["5432:5432"]
    volumes: [pgdata:/var/lib/postgresql/data]
    healthcheck: pg_isready -U postgres -d menu_ops

  redis:
    image: redis:7-alpine
    ports: ["6380:6379"]  # Puerto 6380 para evitar conflictos
    command: redis-server --appendonly yes --maxmemory 256mb --maxmemory-policy allkeys-lru
    healthcheck: redis-cli ping

  backend:
    build: ..
    ports: ["8000:8000"]
    depends_on: [db, redis]
    volumes: [../backend:/app/backend:ro]  # Hot reload
    command: uvicorn rest_api.main:app --reload

  ws_gateway:
    build: ..
    ports: ["8001:8001"]
    depends_on: [db, redis, backend]
    volumes:
      - ../backend:/app/backend:ro
      - ../ws_gateway:/app/ws_gateway:ro

  pgadmin:
    image: dpage/pgadmin4
    ports: ["5050:80"]
```

### 12.2 Health Checks

**REST API**: `/api/health` (sync), `/api/health/detailed` (async con Redis)

**WS Gateway**: `/ws/health` (sync), `/ws/health/detailed` (async)

Health checks detallados incluyen:
- Estado de pool Redis async
- Estado de pool Redis sync
- Conexiones activas
- Subscriber metrics

### 12.3 Scripts de Inicio

**Windows (PowerShell)**: `devOps/start.ps1`
```powershell
$env:PYTHONPATH = "$PWD\backend"
Start-Process python -ArgumentList "-m", "uvicorn", "rest_api.main:app", ...
Start-Process python -ArgumentList "-m", "uvicorn", "ws_gateway.main:app", ...
```

**Unix/Mac**: `devOps/start.sh`
```bash
export PYTHONPATH="$(pwd)/backend"
uvicorn rest_api.main:app --reload --port 8000 &
uvicorn ws_gateway.main:app --reload --port 8001 &
```

---

## 13. Métricas y Observabilidad

### 13.1 Prometheus Endpoint

El WS Gateway expone métricas en `/ws/metrics`:

```
# Conexiones
wsgateway_connections_total 42
wsgateway_connections_rejected_total{reason="auth"} 5
wsgateway_connections_rejected_total{reason="rate_limit"} 2

# Broadcasts
wsgateway_broadcasts_total 1234
wsgateway_broadcasts_failed_total 12
wsgateway_broadcast_latency_seconds_bucket{le="0.1"} 1000

# Redis
wsgateway_redis_reconnects_total 3
wsgateway_event_drops_total 5
```

### 13.2 Structured Logging

El sistema usa logging estructurado con formato JSON en producción y coloreado en desarrollo:

```python
# Production: JSON
{"timestamp": "2026-01-31T12:00:00Z", "level": "INFO", "message": "Connection registered", "user_id": 123, "branch_id": 5}

# Development: Colored
2026-01-31 12:00:00 [INFO] Connection registered user_id=123 branch_id=5
```

PII se sanitiza antes de logging: emails parcialmente ocultos, JTI truncados, user_ids hasheados.

### 13.3 Event Drop Tracking

`EventDropRateTracker` monitorea tasas de descarte de eventos:

```python
class EventDropRateTracker:
    _window_seconds: float = 60.0
    _alert_threshold: float = 0.05  # 5%
    _alert_cooldown: float = 300.0  # 5 min

    def record_drop(self) -> None:
        self._drops.append(time.time())
        if self._should_alert():
            logger.warning("Event drop rate exceeded threshold",
                          rate=self._calculate_rate())
```

---

## 14. Decisiones Arquitectónicas

### 14.1 Clean Architecture vs Rapid Development

La adopción de Clean Architecture con servicios de dominio separados añade complejidad inicial pero ha demostrado valor en:
- Testing unitario de lógica de negocio sin dependencias de infraestructura
- Evolución independiente de capas
- Onboarding más rápido de nuevos desarrolladores

El trade-off es aceptado dado el tamaño y complejidad del sistema.

### 14.2 Redis Streams vs Pub/Sub

El sistema usa híbrido:
- **Pub/Sub**: Eventos de tiempo real que pueden perderse sin consecuencias graves (TABLE_STATUS_CHANGED)
- **Streams**: Eventos críticos que requieren entrega garantizada (ROUND_*, PAYMENT_*)

Streams permiten rewind si el gateway reinicia, previniendo pérdida de órdenes.

### 14.3 Worker Pool vs asyncio.gather

Para broadcasts grandes, el worker pool ofrece:
- Backpressure mediante queue con límite
- Métricas granulares de latencia
- Graceful shutdown con drain timeout

asyncio.gather se mantiene para broadcasts pequeños (<50 conexiones) por simplicidad.

### 14.4 React 19 + React Compiler

La adopción de React 19 con Compiler en Dashboard elimina la mayoría de React.memo manuales. Sin embargo, se mantienen en componentes críticos para:
- Compatibilidad si el compilador se desactiva
- Explicitación de intención de optimización

### 14.5 Zustand con localStorage vs Server State

La persistencia en localStorage permite:
- Funcionamiento offline
- Sesiones que sobreviven refrescos de página
- Menor carga al servidor

El trade-off es sincronización más compleja entre tabs (resuelto con BroadcastChannel).

---

## Apéndice A: Estadísticas del Código

| Componente | Archivos | Líneas de Código |
|------------|----------|------------------|
| Backend (rest_api) | 81 | ~15,000 |
| Backend (shared) | 30 | ~4,500 |
| WebSocket Gateway | 51 | 12,605 |
| Dashboard | 85+ | ~12,000 |
| pwaMenu | 70+ | ~10,000 |
| pwaWaiter | 40+ | ~6,000 |
| **Total** | **360+** | **~60,000** |

## Apéndice B: Modelos SQLAlchemy

52 modelos organizados en 18 archivos:

| Archivo | Modelos | Total |
|---------|---------|-------|
| base.py | Base, AuditMixin | 2 |
| tenant.py | Tenant, Branch | 2 |
| user.py | User, UserBranchRole | 2 |
| catalog.py | Category, Subcategory, Product, BranchProduct | 4 |
| allergen.py | Allergen, ProductAllergen, AllergenCrossReaction | 3 |
| ingredient.py | IngredientGroup, Ingredient, SubIngredient, ProductIngredient | 4 |
| product_profile.py | (12 modelos de perfiles y M:N) | 12 |
| sector.py | BranchSector, WaiterSectorAssignment | 2 |
| table.py | Table, TableSession | 2 |
| customer.py | Customer, Diner | 2 |
| order.py | Round, RoundItem | 2 |
| kitchen.py | KitchenTicket, KitchenTicketItem, ServiceCall | 3 |
| billing.py | Check, Payment, Charge, Allocation | 4 |
| knowledge.py | KnowledgeDocument, ChatLog | 2 |
| promotion.py | Promotion, PromotionBranch, PromotionItem | 3 |
| exclusion.py | BranchCategoryExclusion, BranchSubcategoryExclusion | 2 |
| recipe.py | Recipe, RecipeAllergen | 2 |
| audit.py | AuditLog | 1 |
| **Total** | | **52** |

## Apéndice C: Eventos WebSocket

| Evento | Destinatarios | Trigger |
|--------|---------------|---------|
| ROUND_PENDING | admin, waiters | Diner envía orden |
| ROUND_CONFIRMED | admin | Waiter verifica |
| ROUND_SUBMITTED | admin, kitchen | Admin envía a cocina |
| ROUND_IN_KITCHEN | all | Kitchen comienza |
| ROUND_READY | all | Kitchen termina |
| ROUND_SERVED | all | Staff entrega |
| ROUND_CANCELED | all | Cancelación |
| ROUND_ITEM_DELETED | admin, waiters, diners | Waiter elimina ítem |
| SERVICE_CALL_CREATED | waiters (sector) | Diner llama |
| SERVICE_CALL_ACKED | diners | Waiter reconoce |
| SERVICE_CALL_CLOSED | all | Waiter cierra |
| CHECK_REQUESTED | waiters, admin | Diner pide cuenta |
| CHECK_PAID | all | Pago completado |
| PAYMENT_APPROVED | diners | MP aprueba |
| PAYMENT_REJECTED | diners | MP rechaza |
| TABLE_SESSION_STARTED | admin, waiters | QR escaneado |
| TABLE_CLEARED | admin | Sesión cerrada |
| TABLE_STATUS_CHANGED | admin | Cambio de estado |
| ENTITY_* | admin | CRUD administrativo |

---

*Documento generado: Febrero 2026*
*Versión: 2.0 - Actualización completa reflejando estado actual del sistema*
