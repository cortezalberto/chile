# Backend REST API

Este documento describe la arquitectura, diseño y funcionamiento del backend del sistema Integrador, una plataforma de gestión de restaurantes multi-sucursal con capacidades de tiempo real.

---

## Visión General

El backend de Integrador constituye el núcleo del sistema, proporcionando una API RESTful robusta construida sobre FastAPI que gestiona todas las operaciones de negocio del restaurante. Diseñado siguiendo los principios de Clean Architecture, el sistema mantiene una separación estricta entre las capas de presentación, lógica de negocio y acceso a datos, permitiendo una evolución sostenible del código y facilitando las pruebas automatizadas.

La arquitectura soporta múltiples tenants (restaurantes) con aislamiento completo de datos, donde cada tenant puede administrar múltiples sucursales, cada una con su propia configuración de menú, mesas, sectores y personal. El sistema está optimizado para manejar 400-600 usuarios concurrentes conectados vía WebSocket, con mecanismos de backpressure y circuit breakers que garantizan la resiliencia ante fallos de componentes externos.

---

## Inicio Rápido

### Prerrequisitos

El backend requiere Docker Desktop para ejecutar PostgreSQL y Redis. Una vez instalado, puede iniciar la infraestructura con el siguiente comando desde la raíz del proyecto:

```bash
docker compose -f devOps/docker-compose.yml up -d
```

### Instalación de Dependencias

```bash
cd backend
pip install -r requirements.txt
```

### Ejecución del Servidor

```bash
# Servidor de desarrollo con hot-reload
python -m uvicorn rest_api.main:app --reload --port 8000

# Windows PowerShell (script que configura PYTHONPATH automáticamente)
..\devOps\start.ps1
```

### Ejecución de Tests

```bash
# Ejecutar todos los tests
python -m pytest tests/ -v

# Ejecutar un archivo de test específico
python -m pytest tests/test_auth.py -v

# Ejecutar un test individual
python -m pytest tests/test_admin_staff.py::test_create_staff -v
```

### Reset de Base de Datos

Para reiniciar la base de datos desde cero, elimine los volúmenes de Docker y reinicie:

```bash
docker compose -f devOps/docker-compose.yml down -v
docker compose -f devOps/docker-compose.yml up -d
# Luego reinicie el servidor REST para ejecutar seed()
```

---

## Arquitectura

### Filosofía de Diseño

El backend implementa Clean Architecture con un flujo de datos unidireccional y bien definido. Cada petición HTTP atraviesa capas claramente delimitadas, donde cada capa tiene una única responsabilidad y depende únicamente de las capas inferiores:

```
HTTP Request → Router → Service → Repository → Model
     ↓           ↓          ↓          ↓          ↓
  Validación  Control   Lógica de  Acceso a   Entidad
  de entrada   HTTP     negocio    datos      ORM
```

Esta separación proporciona beneficios tangibles: los routers permanecen delgados y enfocados en concerns HTTP, los servicios encapsulan toda la lógica de negocio de forma testeable, y los repositorios abstraen los detalles de persistencia. El resultado es un sistema donde los cambios en una capa raramente afectan a las demás.

### Estructura del Proyecto

```
backend/
├── rest_api/                    # API FastAPI
│   ├── core/                    # Configuración de la aplicación
│   │   ├── lifespan.py          # Ciclo de vida (startup/shutdown)
│   │   ├── middlewares.py       # Security headers, validación
│   │   └── cors.py              # Configuración CORS
│   │
│   ├── models/                  # Modelos SQLAlchemy (18 archivos por dominio)
│   │   ├── base.py              # AuditMixin (soft delete, auditoría)
│   │   ├── tenant.py            # Tenant, Branch
│   │   ├── user.py              # User, UserBranchRole
│   │   ├── catalog.py           # Category, Subcategory, Product
│   │   ├── table.py             # Table, TableSession
│   │   ├── order.py             # Round, RoundItem
│   │   ├── kitchen.py           # KitchenTicket, ServiceCall
│   │   └── ...                  # allergen, billing, promotion, etc.
│   │
│   ├── repositories/            # Capa de acceso a datos
│   │   ├── base.py              # BaseRepository, RepositoryFilters
│   │   ├── product.py           # ProductRepository
│   │   └── ...                  # category, round, kitchen_ticket
│   │
│   ├── routers/                 # Endpoints HTTP (controladores delgados)
│   │   ├── _common/             # Utilidades compartidas
│   │   ├── admin/               # CRUD administrativo (15 sub-routers)
│   │   ├── auth/                # Login, logout, refresh
│   │   ├── public/              # Menú público, health check
│   │   ├── diner/               # Operaciones de comensal
│   │   ├── kitchen/             # Operaciones de cocina
│   │   ├── waiter/              # Operaciones de mesero
│   │   └── billing/             # Pagos y facturación
│   │
│   ├── services/                # Lógica de negocio
│   │   ├── domain/              # Servicios de dominio (Clean Architecture)
│   │   ├── crud/                # Repository, soft delete, auditoría
│   │   ├── permissions/         # Sistema de permisos (Strategy Pattern)
│   │   ├── events/              # Publicación de eventos en tiempo real
│   │   └── payments/            # Procesamiento de pagos
│   │
│   ├── main.py                  # Punto de entrada FastAPI
│   └── seed.py                  # Datos iniciales de desarrollo
│
├── shared/                      # Módulos compartidos (API + WS Gateway)
│   ├── config/                  # Configuración
│   │   ├── settings.py          # Variables de entorno (Pydantic)
│   │   ├── logging.py           # Logging estructurado
│   │   └── constants.py         # Roles, estados, enums
│   │
│   ├── security/                # Autenticación y autorización
│   │   ├── auth.py              # Verificación JWT/HMAC
│   │   ├── password.py          # Hashing bcrypt
│   │   ├── token_blacklist.py   # Revocación en Redis
│   │   └── rate_limit.py        # Throttling de login
│   │
│   ├── infrastructure/          # Infraestructura
│   │   ├── db.py                # SQLAlchemy sessions
│   │   └── events/              # Redis pub/sub (paquete modular)
│   │
│   └── utils/                   # Utilidades
│       ├── exceptions.py        # Excepciones HTTP con auto-logging
│       ├── validators.py        # Validación de entrada, prevención SSRF
│       └── admin_schemas.py     # Schemas Pydantic para admin API
│
└── tests/                       # Suite de tests pytest
```

---

## Modelo de Datos

### Multi-tenancy y Aislamiento

El sistema implementa multi-tenancy a nivel de base de datos, donde cada registro está asociado a un `tenant_id` que representa un restaurante. Este diseño permite que múltiples restaurantes operen en la misma instancia mientras mantienen sus datos completamente aislados. Todas las consultas filtran automáticamente por tenant, y los repositorios incorporan esta restricción de forma transparente.

Dentro de cada tenant, las sucursales (Branch) actúan como unidades operativas independientes. Cada sucursal posee su propio menú, configuración de mesas, sectores de servicio y asignaciones de personal. Los productos pueden tener precios diferentes por sucursal mediante la tabla `BranchProduct`, y las exclusiones de categorías permiten personalizar el menú disponible en cada ubicación.

### Jerarquía de Entidades

La estructura de datos sigue una jerarquía lógica que refleja la organización física y operativa del restaurante:

**Organización:** Un Tenant contiene múltiples Branches, cada Branch tiene múltiples BranchSectors, y cada sector agrupa Tables físicas.

**Catálogo:** El menú se organiza en Categories que contienen Subcategories, las cuales agrupan Products. Cada producto puede tener múltiples Allergens asociados con niveles de riesgo, y los precios se definen por sucursal en BranchProduct.

**Servicio:** Cuando un comensal escanea el QR de una mesa, se crea una TableSession que agrupa a todos los Diners de esa sesión. Los pedidos se organizan en Rounds (rondas), cada una conteniendo múltiples RoundItems. Una ronda progresa a través de estados: PENDING → IN_KITCHEN → READY → SERVED.

**Facturación:** Al solicitar la cuenta, se crea un Check que consolida todos los cargos (Charges) de la sesión. Los pagos (Payments) se asignan a cargos específicos mediante Allocations siguiendo lógica FIFO.

### Patrón de Auditoría

Todos los modelos heredan de `AuditMixin`, un mixin que proporciona campos estandarizados para el seguimiento de cambios:

```python
class AuditMixin:
    is_active: bool = True                    # Soft delete flag
    created_at: datetime                      # Timestamp de creación
    updated_at: datetime                      # Timestamp de última modificación
    deleted_at: datetime | None               # Timestamp de eliminación (soft)
    created_by_id: int | None                 # Usuario que creó
    created_by_email: str | None              # Email para auditoría
    updated_by_id: int | None                 # Usuario que modificó
    updated_by_email: str | None
    deleted_by_id: int | None                 # Usuario que eliminó
    deleted_by_email: str | None
```

Este patrón permite mantener un historial completo de cambios sin perder datos, facilitando auditorías y la restauración de registros eliminados accidentalmente.

---

## Capa de Servicios

### Servicios de Dominio

La lógica de negocio reside en servicios de dominio ubicados en `rest_api/services/domain/`. Estos servicios implementan el patrón Template Method mediante clases base que proporcionan operaciones CRUD estándar con hooks extensibles:

```python
class CategoryService(BranchScopedService[Category, CategoryOutput]):
    def __init__(self, db: Session):
        super().__init__(
            db=db,
            model=Category,
            output_schema=CategoryOutput,
            entity_name="Categoría",  # Para mensajes de error en español
        )

    def _validate_create(self, data: dict, tenant_id: int) -> None:
        # Validación de negocio antes de crear
        if self._exists_name_in_branch(data["name"], data["branch_id"]):
            raise ValidationError("Ya existe una categoría con ese nombre")

    def _after_delete(self, entity_info: dict, user_id: int, user_email: str) -> None:
        # Efectos secundarios después de eliminar
        publish_entity_deleted("Category", entity_info, tenant_id)
```

La jerarquía de clases base proporciona funcionalidad incremental:

- **BaseService[ModelT]**: Acceso básico al repositorio
- **BaseCRUDService[ModelT, OutputT]**: Operaciones CRUD completas con auditoría
- **BranchScopedService[ModelT, OutputT]**: CRUD + filtrado por sucursal

### Sistema de Permisos

El control de acceso implementa el patrón Strategy, donde cada rol tiene una estrategia de permisos específica. El punto de entrada es `PermissionContext`, que encapsula el usuario actual y proporciona métodos de verificación:

```python
from rest_api.services.permissions import PermissionContext, Action

@router.post("/categories")
def create_category(body: CategoryCreate, db: Session, user: dict):
    ctx = PermissionContext(user)

    # Verificar que es ADMIN o MANAGER
    ctx.require_management()

    # Verificar acceso a la sucursal específica
    ctx.require_branch_access(body.branch_id)

    # Verificar capacidad específica
    if not ctx.can(Action.CREATE, "Category", branch_id=body.branch_id):
        raise ForbiddenError("crear categorías")

    service = CategoryService(db)
    return service.create(body.model_dump(), ctx.tenant_id, ctx.user_id, ctx.user_email)
```

Los roles disponibles y sus capacidades son:

| Rol | Crear | Editar | Eliminar | Alcance |
|-----|-------|--------|----------|---------|
| ADMIN | Todo | Todo | Todo | Global |
| MANAGER | Staff, Mesas, Alérgenos | Igual | No | Sus sucursales |
| KITCHEN | No | Rounds, Tickets | No | Su sucursal |
| WAITER | No | No | No | Sus sectores |

---

## Capa de Repositorios

### Patrón Repository

Los repositorios abstraen el acceso a datos proporcionando una interfaz consistente y type-safe. El sistema define dos tipos principales según el alcance de los datos:

**TenantRepository** se utiliza para entidades que existen a nivel de tenant, como productos o categorías:

```python
repo = TenantRepository(Product, db)
products = repo.find_all(tenant_id=1, options=[selectinload(Product.allergens)])
product = repo.find_by_id(42, tenant_id=1)
```

**BranchRepository** extiende la funcionalidad para entidades que pertenecen a sucursales específicas:

```python
repo = BranchRepository(Table, db)
tables = repo.find_by_branch(branch_id=5, tenant_id=1)
tables = repo.find_by_branches([1, 2, 3], tenant_id=1)
```

### Eager Loading

Un aspecto crítico de los repositorios es la carga eager de relaciones para prevenir el problema N+1. Cada repositorio especializado define las estrategias de carga apropiadas:

```python
class RoundRepository(BranchRepository[Round]):
    def find_with_items(self, round_id: int, tenant_id: int) -> Round | None:
        return self.find_by_id(
            round_id,
            tenant_id,
            options=[
                selectinload(Round.items).joinedload(RoundItem.product),
                joinedload(Round.session).joinedload(TableSession.table),
            ]
        )
```

---

## API REST

### Estructura de Endpoints

Los endpoints se organizan por responsabilidad funcional, con cada grupo manejando un aspecto específico del sistema:

```
/api/auth/*           # Autenticación (login, logout, refresh)
/api/public/*         # Endpoints públicos sin autenticación
/api/admin/*          # Panel administrativo (CRUD completo)
/api/tables/*         # Gestión de sesiones de mesa
/api/diner/*          # Operaciones de comensal (pwaMenu)
/api/kitchen/*        # Operaciones de cocina
/api/waiter/*         # Operaciones de mesero
/api/billing/*        # Pagos y facturación
```

### Routers Administrativos

El módulo `/api/admin/` concentra 15 sub-routers para gestión completa del restaurante:

- **tenant.py**: Configuración organizacional
- **branches.py**: Gestión de sucursales
- **categories.py**, **subcategories.py**, **products.py**: Catálogo
- **allergens.py**: Alérgenos y reacciones cruzadas
- **staff.py**: Usuarios y roles por sucursal
- **tables.py**, **sectors.py**: Configuración física
- **assignments.py**: Asignaciones diarias mesero-sector
- **orders.py**: Vista de pedidos activos
- **exclusions.py**: Personalización de menú por sucursal
- **audit.py**: Consulta de logs de auditoría
- **restore.py**: Restauración de registros eliminados
- **reports.py**: Reportes y analíticas

### Paginación

Los endpoints que retornan listas soportan paginación mediante query parameters:

```
GET /api/admin/products?limit=50&offset=0
```

La implementación utiliza un dependency de FastAPI que valida y aplica límites:

```python
@router.get("/products", response_model=list[ProductOutput])
def list_products(
    pagination: Pagination = Depends(get_pagination),
    db: Session = Depends(get_db),
):
    # pagination.limit está acotado a max 500
    # pagination.offset validado como >= 0
    return service.list_all(limit=pagination.limit, offset=pagination.offset)
```

---

## Sistema de Eventos

### Arquitectura Pub/Sub

El backend publica eventos a Redis para notificación en tiempo real. El WebSocket Gateway (puerto 8001) se suscribe a estos canales y distribuye los eventos a los clientes conectados. Esta arquitectura desacopla la generación de eventos de su distribución, permitiendo escalabilidad horizontal.

Los canales siguen convenciones de nombrado que facilitan el enrutamiento:

```python
# Canales por alcance
channel_branch_all(branch_id)           # Todos en la sucursal
channel_branch_waiters(branch_id)       # Meseros de la sucursal
channel_branch_kitchen(branch_id)       # Cocina de la sucursal
channel_sector_waiters(branch_id, sector_id)  # Meseros del sector
channel_session(session_id)             # Comensales de la sesión
```

### Publicación de Eventos

Los servicios publican eventos mediante funciones de alto nivel que encapsulan la lógica de enrutamiento:

```python
from shared.infrastructure.events import publish_round_event, ROUND_SUBMITTED

# Después de crear una ronda
await publish_round_event(
    event_type=ROUND_SUBMITTED,
    round_id=round.id,
    session_id=session.id,
    branch_id=branch_id,
    sector_id=sector_id,
    tenant_id=tenant_id,
)
```

### Resiliencia

El sistema de eventos incorpora un circuit breaker que protege contra fallos de Redis. Cuando Redis no está disponible, el circuit breaker abre el circuito y las operaciones fallan rápidamente en lugar de bloquear. Después de un período de recuperación, el circuito se cierra gradualmente:

```python
from shared.infrastructure.events import EventCircuitBreaker

breaker = EventCircuitBreaker(
    failure_threshold=5,      # Fallos antes de abrir
    recovery_timeout=30.0,    # Segundos antes de intentar recuperar
)
```

---

## Seguridad

### Autenticación

El sistema soporta dos mecanismos de autenticación según el contexto:

**JWT (JSON Web Tokens)** se utiliza para usuarios autenticados (Dashboard, pwaWaiter). Los tokens de acceso tienen 15 minutos de validez, mientras que los refresh tokens duran 7 días. La revocación se implementa mediante una blacklist en Redis que persiste hasta la expiración natural del token.

**Table Tokens (HMAC)** autentican a los comensales que escanean el QR de una mesa. Estos tokens contienen el ID de sesión y tienen 3 horas de validez. No requieren login previo y permiten acceso limitado a las operaciones de pedido.

```python
# JWT para usuarios autenticados
user = Depends(current_user)  # Extrae claims del token

# Table token para comensales
table_token = Header(alias="X-Table-Token")
session = verify_table_token(table_token)
```

### Middlewares de Seguridad

Múltiples capas de protección se aplican a todas las peticiones:

**SecurityHeadersMiddleware** añade cabeceras de seguridad estándar:
- `Content-Security-Policy`: Previene XSS
- `Strict-Transport-Security`: Fuerza HTTPS en producción
- `X-Frame-Options: DENY`: Previene clickjacking
- `X-Content-Type-Options: nosniff`: Previene MIME sniffing

**ContentTypeValidationMiddleware** valida que las peticiones POST/PUT/PATCH usen `application/json`, rechazando otros content types con 415 Unsupported Media Type.

**Rate Limiting** protege endpoints sensibles:
- Login: 5 intentos por minuto
- WebSocket: 20 mensajes por segundo
- Billing: 10-20 operaciones por minuto

### Validación de Entrada

Las URLs de imágenes se validan para prevenir ataques SSRF y XSS:

```python
from shared.utils.validators import validate_image_url

# Valida esquema (http/https), bloquea IPs internas
validate_image_url(product.image)
```

Hosts bloqueados incluyen: localhost, 127.0.0.1, rangos privados (10.x, 172.16-31.x, 192.168.x), y endpoints de metadata de cloud (169.254.169.254).

---

## Configuración

### Variables de Entorno

La configuración se gestiona mediante Pydantic Settings en `shared/config/settings.py`. Las variables críticas incluyen:

```bash
# Base de datos
DATABASE_URL=postgresql://user:pass@localhost:5432/integrador

# Redis
REDIS_URL=redis://localhost:6380

# Seguridad (CAMBIAR EN PRODUCCIÓN)
JWT_SECRET=<string aleatorio de 32+ caracteres>
TABLE_TOKEN_SECRET=<string aleatorio de 32+ caracteres>

# CORS (producción)
ALLOWED_ORIGINS=https://menu.restaurant.com,https://admin.restaurant.com

# Modo
ENVIRONMENT=production
DEBUG=false
```

### Validación de Producción

El servidor valida los secretos al iniciar y rechaza arrancar si detecta valores por defecto en modo producción:

```python
# En rest_api/core/lifespan.py
if settings.environment == "production":
    if settings.jwt_secret == "change-me-in-production":
        raise RuntimeError("JWT_SECRET must be changed in production")
```

---

## Pruebas

### Estructura de Tests

Los tests residen en `backend/tests/` y utilizan pytest con fixtures para configuración:

```python
# tests/conftest.py
@pytest.fixture
def db_session():
    """Sesión de base de datos con rollback automático."""
    ...

@pytest.fixture
def auth_headers(db_session):
    """Headers con JWT de usuario admin."""
    ...

@pytest.fixture
def test_branch(db_session):
    """Branch de prueba con datos mínimos."""
    ...
```

### Ejecución

```bash
# Todos los tests con output verbose
python -m pytest tests/ -v

# Tests de un módulo específico
python -m pytest tests/test_auth.py -v

# Un test individual
python -m pytest tests/test_admin_staff.py::test_create_staff -v

# Con coverage
python -m pytest tests/ --cov=rest_api --cov-report=html
```

---

## Imports Canónicos

Para mantener consistencia, utilice las siguientes rutas de importación:

```python
# Configuración e infraestructura
from shared.config.settings import settings
from shared.config.logging import get_logger
from shared.config.constants import Roles, RoundStatus
from shared.infrastructure.db import get_db, safe_commit

# Seguridad
from shared.security.auth import current_user, verify_jwt
from rest_api.services.permissions import PermissionContext

# Eventos
from shared.infrastructure.events import (
    get_redis_pool,
    publish_event,
    publish_round_event,
    ROUND_SUBMITTED,
)

# Utilidades
from shared.utils.exceptions import NotFoundError, ForbiddenError, ValidationError
from shared.utils.validators import validate_image_url
from shared.utils.admin_schemas import CategoryOutput, ProductOutput

# Modelos
from rest_api.models import Product, Category, Round, Table

# Servicios de dominio (PREFERIDO para código nuevo)
from rest_api.services.domain import (
    ProductService,
    CategoryService,
    TableService,
    BranchService,
)
```

---

## Optimización de Rendimiento

### Carga Eager

Todas las consultas que retornan entidades con relaciones utilizan carga eager para evitar N+1:

```python
# CORRECTO: Eager loading explícito
rounds = db.execute(
    select(Round).options(
        selectinload(Round.items).joinedload(RoundItem.product),
        joinedload(Round.session).joinedload(TableSession.table),
    )
).scalars().all()

# INCORRECTO: Lazy loading causa N+1
rounds = db.query(Round).all()
for r in rounds:
    print(r.items)  # Query adicional por cada round
```

### Connection Pooling

Tanto SQLAlchemy como Redis utilizan pools de conexiones configurables:

```python
# settings.py
redis_pool_max_connections: int = 50      # Pool async
redis_sync_pool_max_connections: int = 20 # Pool sync (rate limiting)
```

### Paginación Limitada

Los endpoints de lista tienen límites máximos para prevenir queries excesivas:

```python
# Límites por endpoint
products: max 500
staff: max 200
orders: max 100
```

---

## Extensibilidad

### Crear un Nuevo Servicio de Dominio

Para añadir una nueva entidad al sistema:

1. **Crear el modelo** en `rest_api/models/`:

```python
# rest_api/models/my_entity.py
class MyEntity(Base, AuditMixin):
    __tablename__ = "my_entities"
    id: Mapped[int] = mapped_column(primary_key=True)
    tenant_id: Mapped[int] = mapped_column(ForeignKey("tenants.id"))
    name: Mapped[str] = mapped_column(String(100))
```

2. **Crear el schema** en `shared/utils/admin_schemas.py`:

```python
class MyEntityOutput(BaseModel):
    id: int
    name: str
    created_at: datetime
```

3. **Crear el servicio** en `rest_api/services/domain/`:

```python
class MyEntityService(BaseCRUDService[MyEntity, MyEntityOutput]):
    def __init__(self, db: Session):
        super().__init__(
            db=db,
            model=MyEntity,
            output_schema=MyEntityOutput,
            entity_name="Mi Entidad",
        )
```

4. **Crear el router** en `rest_api/routers/admin/`:

```python
@router.get("/my-entities", response_model=list[MyEntityOutput])
def list_my_entities(db: Session = Depends(get_db), user: dict = Depends(current_user)):
    ctx = PermissionContext(user)
    service = MyEntityService(db)
    return service.list_all(ctx.tenant_id)
```

5. **Registrar el router** en `rest_api/routers/admin/__init__.py`.

---

## Referencias

- [CLAUDE.md](../CLAUDE.md): Documentación completa del proyecto
- [shared/README.md](shared/README.md): Documentación de módulos compartidos
- [FastAPI Documentation](https://fastapi.tiangolo.com/)
- [SQLAlchemy 2.0 Documentation](https://docs.sqlalchemy.org/)
