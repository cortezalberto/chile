# Integrador: Plataforma Empresarial de Gestión Integral para Restaurantes Multi-Sucursal

## Prólogo Arquitectónico

Integrador nace como respuesta a la complejidad inherente de gestionar operaciones gastronómicas distribuidas en múltiples ubicaciones físicas, donde la sincronización en tiempo real entre comensales, meseros, cocina y administración representa el desafío técnico central. El sistema trasciende el paradigma tradicional de aplicaciones monolíticas para adoptar una arquitectura de monorepo cuidadosamente orquestada, donde cinco componentes especializados colaboran a través de protocolos bien definidos para ofrecer una experiencia unificada tanto a operadores como a clientes finales.

La filosofía de diseño que permea toda la plataforma se fundamenta en tres pilares arquitectónicos: el aislamiento multi-tenant que garantiza la segregación absoluta de datos entre restaurantes, la comunicación en tiempo real que elimina la latencia perceptible en las operaciones críticas del negocio, y la resiliencia ante fallos que asegura la continuidad operativa incluso cuando componentes individuales experimentan degradación. Estos principios no son meras aspiraciones documentales, sino restricciones arquitectónicas que se manifiestan en cada decisión de diseño, desde la estructura de las tablas de base de datos hasta los patrones de reconexión de WebSocket.

El presente documento constituye la referencia técnica definitiva del sistema, articulando no solo el "qué" de cada componente sino fundamentalmente el "por qué" de las decisiones arquitectónicas que lo conforman. A lo largo de estas páginas, el lector encontrará explicaciones detalladas de los patrones implementados, los problemas que resuelven, y las consideraciones que guiaron su selección sobre alternativas descartadas.

---

## Capítulo I: Topología del Sistema y Componentes Fundamentales

### 1.1 Visión Panorámica de la Arquitectura

El ecosistema Integrador se materializa como una constelación de cinco servicios independientes pero profundamente interconectados, cada uno ejecutándose en su propio proceso y puerto, comunicándose a través de protocolos HTTP REST para operaciones transaccionales y WebSocket para sincronización de estado en tiempo real:

| Componente | Puerto | Tecnología | Responsabilidad Arquitectónica |
|------------|--------|------------|--------------------------------|
| **Dashboard** | 5177 | React 19, Zustand, TypeScript | Panel administrativo centralizado para gestión multi-sucursal, configuración de catálogos, supervisión de operaciones en tiempo real, y control de acceso basado en roles |
| **pwaMenu** | 5176 | React 19, Zustand, i18n, Workbox | Aplicación web progresiva orientada a comensales con capacidades de pedido colaborativo, internacionalización trilingüe (español, inglés, portugués), funcionamiento offline, y sistema de fidelización sin fricción |
| **pwaWaiter** | 5178 | React 19, Zustand, Push API | Aplicación web progresiva para meseros con gestión de mesas segmentada por sectores, notificaciones push para eventos críticos, y funcionalidad de comanda rápida para clientes sin dispositivo |
| **REST API** | 8000 | FastAPI, SQLAlchemy, PostgreSQL, Redis | Backend principal implementando Clean Architecture con separación estricta de capas, autenticación JWT/HMAC, y publicación de eventos hacia el bus de mensajes Redis |
| **WS Gateway** | 8001 | FastAPI WebSocket, Redis Pub/Sub | Gateway dedicado a conexiones WebSocket de larga duración, implementando circuit breaker, broadcast paralelo optimizado, y filtrado de eventos por tenant/branch/sector |

La separación del WebSocket Gateway como servicio independiente del REST API responde a consideraciones tanto de escalabilidad como de resiliencia. Las conexiones WebSocket, por su naturaleza de larga duración y estado persistente, imponen patrones de consumo de recursos fundamentalmente diferentes a las peticiones HTTP stateless. Al aislar estas responsabilidades, el sistema puede escalar horizontalmente cada componente según sus características de carga específicas, y un fallo en el procesamiento de eventos en tiempo real no compromete la disponibilidad de las operaciones CRUD fundamentales.

### 1.2 Flujos de Comunicación Inter-Componentes

La comunicación entre componentes sigue un modelo híbrido deliberadamente diseñado para optimizar tanto la consistencia como la latencia percibida:

**Flujo Transaccional (HTTP REST):** Todas las operaciones que modifican estado persistente transitan obligatoriamente por la API REST. Un comensal agregando un producto al carrito, un administrador modificando el precio de un ítem, o un mesero marcando un pedido como servido, todas estas acciones se materializan como peticiones HTTP que el backend procesa de manera transaccional, garantizando consistencia ACID a través de PostgreSQL.

**Flujo de Sincronización (WebSocket + Redis Pub/Sub):** Una vez que el backend completa una transacción exitosa, publica un evento en el canal Redis apropiado. El WebSocket Gateway, suscrito a estos canales, recibe el evento y lo propaga a todas las conexiones WebSocket relevantes, filtradas por tenant, sucursal y, cuando aplica, sector. Este modelo de "confirmación optimista con reconciliación eventual" permite que los clientes actualicen su interfaz inmediatamente tras una acción local, mientras reciben confirmación definitiva a través del canal WebSocket.

```
┌─────────────┐     HTTP POST      ┌─────────────┐
│   pwaMenu   │ ─────────────────► │  REST API   │
│  (Comensal) │                    │  (Backend)  │
└─────────────┘                    └──────┬──────┘
                                          │
                                          │ PUBLISH event
                                          ▼
┌─────────────┐     WebSocket      ┌─────────────┐     SUBSCRIBE     ┌─────────────┐
│  Dashboard  │ ◄────────────────► │ WS Gateway  │ ◄────────────────► │    Redis    │
│   (Admin)   │                    │             │                    │   Pub/Sub   │
└─────────────┘                    └─────────────┘                    └─────────────┘
       ▲                                  │
       │                                  │
       └──── Evento propagado ────────────┘
             (ROUND_SUBMITTED)
```

Este diseño desacopla temporalmente la confirmación de la acción (respuesta HTTP inmediata) de la propagación del cambio (evento WebSocket asíncrono), permitiendo que el sistema mantenga responsividad incluso bajo carga elevada, mientras garantiza que todos los participantes eventualmente convergen al mismo estado.

### 1.3 El Principio de Aislamiento Multi-Tenant

El aislamiento multi-tenant constituye la restricción arquitectónica más fundamental del sistema, permeando absolutamente cada capa de la aplicación. En el contexto de Integrador, un "tenant" representa un restaurante como entidad empresarial, que puede operar múltiples sucursales físicas (branches) bajo una misma identidad corporativa.

**Nivel de Base de Datos:** Cada tabla relevante del esquema incluye una columna `tenant_id` que participa en todas las consultas. Los repositorios de acceso a datos automáticamente inyectan este filtro, haciendo imposible que una consulta legítima retorne datos de un tenant diferente al del usuario autenticado.

```python
class TenantRepository(Generic[ModelT]):
    """Repositorio base con aislamiento automático por tenant."""

    def find_all(self, tenant_id: int, **options) -> Sequence[ModelT]:
        query = select(self._model).where(self._model.tenant_id == tenant_id)
        # El filtro por tenant_id es OBLIGATORIO y no puede omitirse
        return self._session.scalars(query).all()
```

**Nivel de API:** Los endpoints extraen el `tenant_id` del token JWT del usuario autenticado, nunca de parámetros de la petición. Esto elimina la posibilidad de que un atacante manipule el tenant objetivo de una operación.

**Nivel de WebSocket:** El gateway mantiene índices de conexiones organizados por tenant, y el broadcast de eventos verifica que el `tenant_id` del evento coincida con el de cada conexión destinataria antes de transmitir.

```python
async def broadcast_to_branch(self, branch_id: int, event: dict, tenant_id: int):
    connections = self._connections_by_branch.get(branch_id, [])
    # Filtrado DENTRO del lock para prevenir race conditions
    safe_connections = [
        conn for conn in connections
        if conn.tenant_id == tenant_id  # Aislamiento estricto
    ]
    await self._broadcast_to_connections(safe_connections, event)
```

Este enfoque de "defensa en profundidad" garantiza que incluso si una capa individual fallara en su validación, las capas subsiguientes detectarían y bloquearían cualquier intento de acceso cross-tenant.

---

## Capítulo II: Modelo de Datos y Diseño de Dominio

### 2.1 Jerarquía de Entidades

El esquema de base de datos de Integrador comprende 47 entidades SQLAlchemy organizadas en dominios funcionales cohesivos. La estructura jerárquica refleja las relaciones de negocio del mundo real:

```
Tenant (Restaurante corporativo)
│
├── Branch (Sucursal física) [1:N]
│   │
│   ├── Catálogo de Productos
│   │   ├── Category (Categoría principal: Bebidas, Entradas, etc.)
│   │   │   └── Subcategory (Subcategoría: Cervezas, Vinos, etc.)
│   │   │       └── Product (Producto base del catálogo)
│   │   │           ├── BranchProduct (Precio específico por sucursal, en centavos)
│   │   │           ├── ProductAllergen (Alérgenos con tipo de presencia y nivel de riesgo)
│   │   │           ├── ProductIngredient → Ingredient → SubIngredient
│   │   │           └── Perfiles: DietaryProfile, CookingProfile, FlavorProfile, etc.
│   │   │
│   │   └── Recipe (Ficha técnica de cocina, opcional link a Product)
│   │       └── RecipeAllergen
│   │
│   ├── Estructura Física
│   │   ├── BranchSector (Sector: Terraza, Interior, Barra, etc.)
│   │   │   ├── Table (Mesa física con código alfanumérico único por sucursal)
│   │   │   │   └── TableSession (Sesión activa de comensales)
│   │   │   │       ├── Diner (Comensal individual con device_id)
│   │   │   │       └── Round (Ronda de pedido)
│   │   │   │           └── RoundItem (Ítem individual del pedido)
│   │   │   │               └── KitchenTicket → KitchenTicketItem
│   │   │   │
│   │   │   └── WaiterSectorAssignment (Asignación diaria de mesero a sector)
│   │   │
│   │   └── ServiceCall (Llamada de servicio desde mesa)
│   │
│   ├── Facturación
│   │   ├── Check (Cuenta de la mesa)
│   │   │   └── Charge (Cargo individual)
│   │   │       └── Allocation (Asignación de pago a cargo, FIFO)
│   │   │
│   │   └── Payment (Pago recibido)
│   │
│   └── Exclusiones
│       ├── BranchCategoryExclusion (Categorías no disponibles en sucursal)
│       └── BranchSubcategoryExclusion (Subcategorías no disponibles)
│
├── User (Usuario del sistema)
│   └── UserBranchRole (Rol por sucursal: ADMIN, MANAGER, KITCHEN, WAITER)
│
├── Customer (Cliente registrado con consentimiento GDPR)
│   └── Métricas de fidelización, preferencias AI, historial
│
├── Promotion (Promoción activa)
│   ├── PromotionBranch (Sucursales donde aplica)
│   └── PromotionItem (Productos incluidos)
│
├── Allergen (Alérgeno del catálogo global)
│   └── AllergenCrossReaction (Reacciones cruzadas entre alérgenos)
│
├── KnowledgeDocument (Documentos para RAG chatbot)
│   └── ChatLog (Historial de conversaciones)
│
└── AuditLog (Registro de auditoría inmutable)
```

### 2.2 Diseño de Precios por Sucursal

Una decisión de diseño fundamental es la separación entre `Product` (definición del producto) y `BranchProduct` (precio en una sucursal específica). Esta normalización permite que un mismo producto base exista en el catálogo corporativo mientras cada sucursal define su propia política de precios:

```python
class Product(Base, AuditMixin):
    """Producto base del catálogo corporativo."""
    __tablename__ = "products"

    id = Column(BigInteger, primary_key=True)
    tenant_id = Column(BigInteger, ForeignKey("tenants.id"), nullable=False)
    subcategory_id = Column(BigInteger, ForeignKey("subcategories.id"))
    name = Column(String(200), nullable=False)
    description = Column(Text)
    image = Column(String(500))  # URL validada contra SSRF

    # Relaciones
    branch_prices = relationship("BranchProduct", back_populates="product")
    allergens = relationship("ProductAllergen", back_populates="product")


class BranchProduct(Base, AuditMixin):
    """Precio de un producto en una sucursal específica."""
    __tablename__ = "branch_products"

    id = Column(BigInteger, primary_key=True)
    branch_id = Column(BigInteger, ForeignKey("branches.id"), nullable=False)
    product_id = Column(BigInteger, ForeignKey("products.id"), nullable=False)
    price = Column(Integer, nullable=False)  # Precio en CENTAVOS (12550 = $125.50)
    is_available = Column(Boolean, default=True)

    # Constraint único: un producto solo tiene un precio por sucursal
    __table_args__ = (
        UniqueConstraint("branch_id", "product_id", name="uq_branch_product"),
    )
```

La decisión de almacenar precios en centavos como enteros (en lugar de decimales) elimina los problemas de precisión de punto flotante en cálculos financieros, una práctica estándar en sistemas de procesamiento de pagos.

### 2.3 Sistema de Alérgenos con Reacciones Cruzadas

El manejo de alérgenos implementa un modelo sofisticado que va más allá de la simple presencia/ausencia:

```python
class ProductAllergen(Base):
    """Relación M:N entre productos y alérgenos con metadatos."""
    __tablename__ = "product_allergens"

    product_id = Column(BigInteger, ForeignKey("products.id"), primary_key=True)
    allergen_id = Column(BigInteger, ForeignKey("allergens.id"), primary_key=True)

    # Tipo de presencia: CONTAINS, MAY_CONTAIN, TRACES
    presence_type = Column(String(20), nullable=False, default="CONTAINS")

    # Nivel de riesgo: HIGH, MEDIUM, LOW
    risk_level = Column(String(10), nullable=False, default="HIGH")


class AllergenCrossReaction(Base):
    """Reacciones cruzadas entre alérgenos (relación M:N self-referential)."""
    __tablename__ = "allergen_cross_reactions"

    allergen_id = Column(BigInteger, ForeignKey("allergens.id"), primary_key=True)
    cross_reacts_with_id = Column(BigInteger, ForeignKey("allergens.id"), primary_key=True)

    # Severidad de la reacción cruzada
    severity = Column(String(10), nullable=False)  # HIGH, MEDIUM, LOW
```

El frontend pwaMenu utiliza esta información para expandir automáticamente los filtros de alérgenos cuando el usuario selecciona modo estricto, incluyendo todos los alérgenos que presentan reacciones cruzadas conocidas con los seleccionados.

### 2.4 Auditoría y Soft Delete

Todas las entidades heredan de `AuditMixin`, proporcionando trazabilidad completa de cambios:

```python
class AuditMixin:
    """Mixin que proporciona campos de auditoría a todas las entidades."""

    # Soft delete
    is_active = Column(Boolean, default=True, index=True)

    # Timestamps
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, onupdate=datetime.utcnow)
    deleted_at = Column(DateTime, nullable=True)

    # Trazabilidad de usuario
    created_by_id = Column(BigInteger)
    created_by_email = Column(String(255))
    updated_by_id = Column(BigInteger)
    updated_by_email = Column(String(255))
    deleted_by_id = Column(BigInteger)
    deleted_by_email = Column(String(255))
```

El patrón de soft delete (marcar `is_active=False` en lugar de eliminar físicamente) preserva la integridad referencial y permite auditoría histórica completa. La función `cascade_soft_delete` propaga la eliminación lógica a todas las entidades dependientes:

```python
def cascade_soft_delete(db: Session, entity: Any, user_id: int, user_email: str) -> list[dict]:
    """
    Elimina lógicamente una entidad y todas sus dependencias en cascade.
    Retorna lista de entidades afectadas para auditoría.
    """
    affected = []

    # Obtener relaciones definidas en CASCADE_RELATIONSHIPS
    relationships = CASCADE_RELATIONSHIPS.get(type(entity).__name__, [])

    for rel_config in relationships:
        children = getattr(entity, rel_config["relation_name"], [])
        for child in children:
            child.is_active = False
            child.deleted_at = datetime.utcnow()
            child.deleted_by_id = user_id
            child.deleted_by_email = user_email
            affected.append({"type": type(child).__name__, "id": child.id})

    # Finalmente, eliminar la entidad principal
    entity.is_active = False
    entity.deleted_at = datetime.utcnow()
    entity.deleted_by_id = user_id
    entity.deleted_by_email = user_email

    db.flush()
    return affected
```

---

## Capítulo III: Backend - Implementación de Clean Architecture

### 3.1 Principios de Estratificación

El backend de Integrador implementa Clean Architecture con cuatro capas claramente delimitadas, donde las dependencias fluyen exclusivamente hacia adentro (de capas externas a internas):

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                              CAPA DE ROUTERS                                 │
│                                                                              │
│  Responsabilidad: Concerns HTTP exclusivamente                               │
│  - Deserialización de requests                                               │
│  - Validación de parámetros de ruta y query                                 │
│  - Invocación de servicios de dominio                                        │
│  - Serialización de responses                                                │
│  - Manejo de códigos HTTP                                                    │
│                                                                              │
│  Prohibido: Lógica de negocio, acceso directo a base de datos               │
└─────────────────────────────────┬───────────────────────────────────────────┘
                                  │
                                  ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                          CAPA DE SERVICIOS DE DOMINIO                        │
│                                                                              │
│  Responsabilidad: Lógica de negocio y orquestación                          │
│  - Validación de reglas de negocio                                          │
│  - Coordinación entre múltiples repositorios                                │
│  - Transformación de entidades a DTOs de salida                             │
│  - Publicación de eventos de dominio                                        │
│  - Aplicación de políticas de permisos                                      │
│                                                                              │
│  Prohibido: Concerns HTTP, SQL directo                                      │
└─────────────────────────────────┬───────────────────────────────────────────┘
                                  │
                                  ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                            CAPA DE REPOSITORIOS                              │
│                                                                              │
│  Responsabilidad: Acceso a datos exclusivamente                             │
│  - Consultas SQL a través de SQLAlchemy                                     │
│  - Eager loading de relaciones                                               │
│  - Filtrado por tenant_id (automático)                                      │
│  - Paginación y ordenamiento                                                │
│                                                                              │
│  Prohibido: Lógica de negocio, validaciones complejas                       │
└─────────────────────────────────┬───────────────────────────────────────────┘
                                  │
                                  ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                              CAPA DE MODELOS                                 │
│                                                                              │
│  Responsabilidad: Definición de entidades                                   │
│  - Mapeo objeto-relacional (SQLAlchemy)                                     │
│  - Constraints de base de datos                                              │
│  - Relaciones entre entidades                                                │
│  - Mixins de auditoría                                                       │
│                                                                              │
│  Prohibido: Lógica de aplicación                                            │
└─────────────────────────────────────────────────────────────────────────────┘
```

### 3.2 Anatomía de un Endpoint

Para ilustrar cómo las capas colaboran, examinemos el flujo completo de un endpoint típico:

```python
# ═══════════════════════════════════════════════════════════════════════════
# CAPA 1: ROUTER (rest_api/routers/admin/categories.py)
# ═══════════════════════════════════════════════════════════════════════════

@router.get("", response_model=list[CategoryOutput])
def list_categories(
    branch_id: int = Query(..., description="ID de la sucursal"),
    db: Session = Depends(get_db),
    user: dict = Depends(current_user),
):
    """
    Lista categorías de una sucursal.

    El router es DELGADO: solo extrae parámetros y delega al servicio.
    No contiene lógica de negocio ni acceso directo a la base de datos.
    """
    # Crear contexto de permisos desde el usuario autenticado
    ctx = PermissionContext(user)

    # Verificar acceso a la sucursal solicitada
    ctx.require_branch_access(branch_id)

    # Instanciar servicio e invocar operación
    service = CategoryService(db)
    return service.list_by_branch(ctx.tenant_id, branch_id)


@router.post("", response_model=CategoryOutput, status_code=201)
def create_category(
    body: CategoryCreate,
    db: Session = Depends(get_db),
    user: dict = Depends(current_user),
):
    """Crea una nueva categoría."""
    ctx = PermissionContext(user)
    ctx.require_management()  # Solo ADMIN/MANAGER pueden crear

    service = CategoryService(db)
    return service.create(
        data=body.model_dump(),
        tenant_id=ctx.tenant_id,
        user_id=ctx.user_id,
        user_email=user.get("email", ""),
    )
```

```python
# ═══════════════════════════════════════════════════════════════════════════
# CAPA 2: SERVICIO DE DOMINIO (rest_api/services/domain/category_service.py)
# ═══════════════════════════════════════════════════════════════════════════

class CategoryService(BranchScopedService[Category, CategoryOutput]):
    """
    Servicio de dominio para gestión de categorías.

    Hereda de BranchScopedService que proporciona operaciones CRUD genéricas
    con hooks extensibles para validación y efectos secundarios.
    """

    def __init__(self, db: Session):
        super().__init__(
            db=db,
            model=Category,
            output_schema=CategoryOutput,
            entity_name="Categoría",  # Para mensajes de error en español
        )

    def list_by_branch(self, tenant_id: int, branch_id: int) -> list[CategoryOutput]:
        """
        Obtiene categorías de una sucursal con sus subcategorías.

        El servicio orquesta la consulta y transforma entidades a DTOs.
        """
        # Usar repositorio para acceso a datos
        entities = self._repo.find_by_branch(
            branch_id=branch_id,
            tenant_id=tenant_id,
            options=[selectinload(Category.subcategories)],  # Eager loading
        )

        # Transformar entidades a esquemas de salida
        return [self.to_output(entity) for entity in entities]

    def _validate_create(self, data: dict, tenant_id: int) -> None:
        """
        Hook de validación pre-creación.

        Implementa reglas de negocio específicas de la entidad.
        """
        if not data.get("name") or len(data["name"].strip()) < 2:
            raise ValidationError(
                "El nombre de la categoría debe tener al menos 2 caracteres",
                field="name",
            )

        # Verificar unicidad del nombre en la sucursal
        existing = self._repo.find_by_name(
            name=data["name"],
            branch_id=data["branch_id"],
            tenant_id=tenant_id,
        )
        if existing:
            raise ValidationError(
                f"Ya existe una categoría con el nombre '{data['name']}'",
                field="name",
            )

    def _after_create(self, entity: Category, user_id: int, user_email: str) -> None:
        """
        Hook post-creación para efectos secundarios.

        Publica evento de dominio para notificación en tiempo real.
        """
        publish_entity_created(
            entity_type="Category",
            entity_id=entity.id,
            tenant_id=entity.tenant_id,
            branch_id=entity.branch_id,
            user_id=user_id,
        )
```

```python
# ═══════════════════════════════════════════════════════════════════════════
# CAPA 3: REPOSITORIO (rest_api/services/crud/repository.py)
# ═══════════════════════════════════════════════════════════════════════════

class BranchRepository(TenantRepository[ModelT]):
    """
    Repositorio para entidades con scope de sucursal.

    Extiende TenantRepository añadiendo filtrado automático por branch_id.
    """

    def find_by_branch(
        self,
        branch_id: int,
        tenant_id: int,
        options: list = None,
    ) -> Sequence[ModelT]:
        """
        Consulta entidades de una sucursal específica.

        El repositorio SOLO accede a datos. No contiene lógica de negocio.
        """
        query = (
            select(self._model)
            .where(self._model.tenant_id == tenant_id)  # Aislamiento multi-tenant
            .where(self._model.branch_id == branch_id)
            .where(self._model.is_active.is_(True))  # Solo registros activos
        )

        # Aplicar eager loading si se especifica
        if options:
            for option in options:
                query = query.options(option)

        return self._session.scalars(query).all()

    def find_by_name(
        self,
        name: str,
        branch_id: int,
        tenant_id: int,
    ) -> Optional[ModelT]:
        """Busca entidad por nombre exacto en una sucursal."""
        return self._session.scalar(
            select(self._model)
            .where(self._model.tenant_id == tenant_id)
            .where(self._model.branch_id == branch_id)
            .where(self._model.name == name)
            .where(self._model.is_active.is_(True))
        )
```

### 3.3 Sistema de Permisos: Strategy Pattern con Interface Segregation

El control de acceso implementa el patrón Strategy combinado con el principio de Interface Segregation (ISP), permitiendo que cada rol defina únicamente las capacidades que necesita sin heredar métodos innecesarios:

```python
# ═══════════════════════════════════════════════════════════════════════════
# PROTOCOLOS SEGREGADOS (Interface Segregation Principle)
# ═══════════════════════════════════════════════════════════════════════════

class CanRead(Protocol):
    """Protocolo para estrategias que pueden leer entidades."""
    def can_read(self, user: dict, entity: Any) -> bool: ...

class CanCreate(Protocol):
    """Protocolo para estrategias que pueden crear entidades."""
    def can_create(self, user: dict, entity_type: str, context: dict) -> bool: ...

class CanUpdate(Protocol):
    """Protocolo para estrategias que pueden actualizar entidades."""
    def can_update(self, user: dict, entity: Any) -> bool: ...

class CanDelete(Protocol):
    """Protocolo para estrategias que pueden eliminar entidades."""
    def can_delete(self, user: dict, entity: Any) -> bool: ...

class QueryFilter(Protocol):
    """Protocolo para estrategias que filtran consultas."""
    def filter_query(self, query: Select, user: dict) -> Select: ...


# ═══════════════════════════════════════════════════════════════════════════
# MIXINS DE DENEGACIÓN (Reutilizables entre estrategias)
# ═══════════════════════════════════════════════════════════════════════════

class NoCreateMixin:
    """Mixin que deniega creación. Elimina código duplicado."""
    def can_create(self, user: dict, entity_type: str, context: dict) -> bool:
        return False

class NoDeleteMixin:
    """Mixin que deniega eliminación."""
    def can_delete(self, user: dict, entity: Any) -> bool:
        return False

class NoUpdateMixin:
    """Mixin que deniega actualización."""
    def can_update(self, user: dict, entity: Any) -> bool:
        return False


# ═══════════════════════════════════════════════════════════════════════════
# MIXINS DE ACCESO A SUCURSAL
# ═══════════════════════════════════════════════════════════════════════════

class BranchAccessMixin:
    """Mixin con utilidades para verificación de acceso a sucursales."""

    def _user_has_branch_access(self, user: dict, branch_id: int) -> bool:
        """Verifica si el usuario tiene acceso a una sucursal específica."""
        user_branch_ids = user.get("branch_ids", [])
        return branch_id in user_branch_ids

    def _get_entity_branch_id(self, entity: Any) -> Optional[int]:
        """Extrae branch_id de una entidad si existe."""
        return getattr(entity, "branch_id", None)


class BranchFilterMixin:
    """Mixin que filtra consultas por sucursales del usuario."""

    def filter_query(self, query: Select, user: dict) -> Select:
        """Añade filtro WHERE branch_id IN (sucursales del usuario)."""
        branch_ids = user.get("branch_ids", [])
        if not branch_ids:
            # Sin sucursales asignadas = sin resultados
            return query.where(False)
        return query.where(self._model.branch_id.in_(branch_ids))


# ═══════════════════════════════════════════════════════════════════════════
# ESTRATEGIAS DE ROL
# ═══════════════════════════════════════════════════════════════════════════

class AdminStrategy(PermissionStrategy):
    """
    Estrategia para rol ADMIN: acceso total dentro del tenant.

    ADMIN puede crear, leer, actualizar y eliminar cualquier entidad
    de su tenant, sin restricciones por sucursal.
    """

    def can_read(self, user: dict, entity: Any) -> bool:
        return self._same_tenant(user, entity)

    def can_create(self, user: dict, entity_type: str, context: dict) -> bool:
        return True  # ADMIN puede crear cualquier entidad

    def can_update(self, user: dict, entity: Any) -> bool:
        return self._same_tenant(user, entity)

    def can_delete(self, user: dict, entity: Any) -> bool:
        return self._same_tenant(user, entity)

    def filter_query(self, query: Select, user: dict) -> Select:
        # ADMIN ve todo su tenant, sin filtro por sucursal
        return query.where(self._model.tenant_id == user["tenant_id"])


class ManagerStrategy(BranchAccessMixin, BranchFilterMixin, PermissionStrategy):
    """
    Estrategia para rol MANAGER: gestión de sucursales asignadas.

    MANAGER puede gestionar staff, mesas, alérgenos y promociones
    pero SOLO en las sucursales donde tiene asignación.
    NO puede eliminar entidades (soft delete reservado para ADMIN).
    """

    MANAGEABLE_ENTITIES = frozenset({
        "Table", "BranchSector", "WaiterSectorAssignment",
        "Allergen", "Promotion", "UserBranchRole",
    })

    def can_read(self, user: dict, entity: Any) -> bool:
        if not self._same_tenant(user, entity):
            return False
        branch_id = self._get_entity_branch_id(entity)
        if branch_id is None:
            return True  # Entidades sin branch_id son visibles
        return self._user_has_branch_access(user, branch_id)

    def can_create(self, user: dict, entity_type: str, context: dict) -> bool:
        if entity_type not in self.MANAGEABLE_ENTITIES:
            return False
        branch_id = context.get("branch_id")
        if branch_id is None:
            return False
        return self._user_has_branch_access(user, branch_id)

    def can_update(self, user: dict, entity: Any) -> bool:
        entity_type = type(entity).__name__
        if entity_type not in self.MANAGEABLE_ENTITIES:
            return False
        branch_id = self._get_entity_branch_id(entity)
        if branch_id is None:
            return False
        return self._user_has_branch_access(user, branch_id)

    def can_delete(self, user: dict, entity: Any) -> bool:
        return False  # MANAGER no puede eliminar


class KitchenStrategy(NoCreateMixin, NoDeleteMixin, BranchAccessMixin, BranchFilterMixin, PermissionStrategy):
    """
    Estrategia para rol KITCHEN: operaciones de cocina.

    KITCHEN solo puede leer productos/recetas y actualizar
    estados de tickets y rondas en su sucursal.
    Usa mixins para heredar denegación de create/delete.
    """

    READABLE_ENTITIES = frozenset({
        "Round", "RoundItem", "KitchenTicket", "KitchenTicketItem",
        "Product", "Recipe", "Ingredient",
    })

    UPDATABLE_ENTITIES = frozenset({
        "Round", "KitchenTicket",
    })

    def can_read(self, user: dict, entity: Any) -> bool:
        entity_type = type(entity).__name__
        if entity_type not in self.READABLE_ENTITIES:
            return False
        if not self._same_tenant(user, entity):
            return False
        branch_id = self._get_entity_branch_id(entity)
        if branch_id is None:
            return True
        return self._user_has_branch_access(user, branch_id)

    def can_update(self, user: dict, entity: Any) -> bool:
        entity_type = type(entity).__name__
        if entity_type not in self.UPDATABLE_ENTITIES:
            return False
        branch_id = self._get_entity_branch_id(entity)
        return self._user_has_branch_access(user, branch_id)

    # can_create y can_delete heredados de NoCreateMixin y NoDeleteMixin


class WaiterStrategy(NoCreateMixin, NoDeleteMixin, BranchAccessMixin, BranchFilterMixin, PermissionStrategy):
    """
    Estrategia para rol WAITER: operaciones de servicio.

    WAITER puede leer mesas/productos de sus sectores asignados
    y actualizar estados de rondas (marcar como servidas).
    """

    READABLE_ENTITIES = frozenset({
        "Table", "TableSession", "Round", "RoundItem",
        "Product", "Category", "ServiceCall",
    })

    UPDATABLE_ENTITIES = frozenset({
        "Round", "ServiceCall",
    })

    def can_read(self, user: dict, entity: Any) -> bool:
        entity_type = type(entity).__name__
        if entity_type not in self.READABLE_ENTITIES:
            return False
        # Lógica adicional para filtrado por sector si aplica
        return self._check_sector_access(user, entity)

    def can_update(self, user: dict, entity: Any) -> bool:
        entity_type = type(entity).__name__
        if entity_type not in self.UPDATABLE_ENTITIES:
            return False
        return self._check_sector_access(user, entity)
```

### 3.4 Selección de Estrategia por Privilegio

El sistema selecciona automáticamente la estrategia de mayor privilegio cuando un usuario tiene múltiples roles:

```python
# Orden de privilegio (mayor a menor)
ROLE_HIERARCHY = {
    "ADMIN": 4,
    "MANAGER": 3,
    "KITCHEN": 2,
    "WAITER": 1,
}

STRATEGY_MAP = {
    "ADMIN": AdminStrategy,
    "MANAGER": ManagerStrategy,
    "KITCHEN": KitchenStrategy,
    "WAITER": WaiterStrategy,
}


def get_highest_privilege_strategy(roles: list[str]) -> PermissionStrategy:
    """
    Retorna la estrategia correspondiente al rol de mayor privilegio.

    Un usuario con roles ["WAITER", "MANAGER"] obtiene ManagerStrategy.
    """
    if not roles:
        raise ForbiddenError("Usuario sin roles asignados")

    highest_role = max(roles, key=lambda r: ROLE_HIERARCHY.get(r, 0))
    strategy_class = STRATEGY_MAP.get(highest_role)

    if not strategy_class:
        raise ForbiddenError(f"Rol no reconocido: {highest_role}")

    return strategy_class()
```

### 3.5 PermissionContext: Fachada Simplificada

Para simplificar el uso de permisos en routers, `PermissionContext` actúa como fachada:

```python
class PermissionContext:
    """
    Fachada que encapsula el contexto de permisos del usuario.

    Simplifica las verificaciones comunes en routers sin exponer
    la complejidad del sistema de estrategias.
    """

    def __init__(self, user: dict):
        self._user = user
        self._strategy = get_highest_privilege_strategy(user.get("roles", []))

    @property
    def user_id(self) -> int:
        return int(self._user["sub"])

    @property
    def tenant_id(self) -> int:
        return self._user["tenant_id"]

    @property
    def branch_ids(self) -> list[int]:
        return self._user.get("branch_ids", [])

    @property
    def is_admin(self) -> bool:
        return "ADMIN" in self._user.get("roles", [])

    @property
    def is_management(self) -> bool:
        roles = set(self._user.get("roles", []))
        return bool(roles & {"ADMIN", "MANAGER"})

    def require_management(self) -> None:
        """Lanza ForbiddenError si el usuario no es ADMIN ni MANAGER."""
        if not self.is_management:
            raise ForbiddenError("Operación requiere rol ADMIN o MANAGER")

    def require_branch_access(self, branch_id: int) -> None:
        """Lanza ForbiddenError si el usuario no tiene acceso a la sucursal."""
        if self.is_admin:
            return  # ADMIN tiene acceso a todas las sucursales del tenant
        if branch_id not in self.branch_ids:
            raise ForbiddenError(
                f"Sin acceso a sucursal {branch_id}",
                branch_id=branch_id,
            )

    def can(self, action: Action, entity_type: str, **context) -> bool:
        """Verifica si el usuario puede realizar una acción."""
        if action == Action.CREATE:
            return self._strategy.can_create(self._user, entity_type, context)
        # ... otras acciones
```

---

## Capítulo IV: WebSocket Gateway - Arquitectura de Tiempo Real

### 4.1 Fundamentos del Diseño

El WebSocket Gateway existe como servicio separado del REST API por razones arquitectónicas fundamentales. Las conexiones WebSocket, por su naturaleza stateful y de larga duración, imponen patrones de consumo de recursos radicalmente diferentes a las peticiones HTTP stateless. Mientras una instancia del REST API puede procesar miles de peticiones por segundo sin mantener estado entre ellas, cada conexión WebSocket consume memoria de forma continua y requiere tracking activo.

Esta separación permite:

1. **Escalamiento independiente:** El gateway puede escalarse horizontalmente basándose en el número de conexiones activas, mientras el REST API escala según throughput de peticiones.

2. **Aislamiento de fallos:** Un problema en el procesamiento de eventos en tiempo real no compromete la disponibilidad de operaciones CRUD.

3. **Optimización especializada:** El gateway implementa patrones específicos para WebSocket (heartbeat, reconnection, broadcast paralelo) sin complicar el código del REST API.

### 4.2 Arquitectura Modular por Componentes

La refactorización del gateway extrajo responsabilidades cohesivas a módulos especializados, reduciendo el tamaño de los archivos principales y mejorando la testeabilidad:

```
ws_gateway/
│
├── main.py                         # App FastAPI, endpoints, /ws/metrics
│   └── Lifespan: startup/shutdown hooks
│
├── connection_manager.py           # Orquestador DELGADO (463 líneas, antes 987)
│   └── Compone y coordina módulos de core/connection/
│
├── redis_subscriber.py             # Orquestador DELGADO (326 líneas, antes 666)
│   └── Compone y coordina módulos de core/subscriber/
│
├── core/                           # Módulos extraídos para alta cohesión
│   │
│   ├── connection/                 # Gestión de conexiones (extraído de connection_manager)
│   │   ├── lifecycle.py            # ConnectionLifecycle: connect/disconnect
│   │   │   └── Registra conexión en índices, valida límites
│   │   │
│   │   ├── broadcaster.py          # ConnectionBroadcaster: send/broadcast
│   │   │   └── Broadcast paralelo con batching de 50 conexiones
│   │   │
│   │   ├── cleanup.py              # ConnectionCleanup: limpieza periódica
│   │   │   └── Detecta conexiones stale/dead, libera recursos
│   │   │
│   │   └── stats.py                # ConnectionStats: métricas agregadas
│   │       └── Contadores por tipo, branch, tenant
│   │
│   └── subscriber/                 # Suscripción Redis (extraído de redis_subscriber)
│       ├── drop_tracker.py         # EventDropRateTracker: alertas de descarte
│       │   └── Detecta si se pierden eventos por backpressure
│       │
│       ├── validator.py            # Validación de esquema de eventos
│       │   └── Rechaza eventos malformados antes de broadcast
│       │
│       └── processor.py            # Procesamiento batch de eventos
│           └── Agrupa eventos para eficiencia
│
└── components/                     # Componentes modulares con patrones de diseño
    │
    ├── core/
    │   ├── constants.py            # WSCloseCode enum, WSConstants
    │   ├── context.py              # WebSocketContext para logging estructurado
    │   └── dependencies.py         # Contenedor DI para testing
    │
    ├── connection/
    │   ├── index.py                # ConnectionIndex: índices y mappings inversos
    │   ├── locks.py                # LockManager: locks fragmentados por branch/user
    │   ├── lock_sequence.py        # LockSequence: prevención de deadlocks
    │   ├── heartbeat.py            # HeartbeatTracker: detección de conexiones muertas
    │   └── rate_limiter.py         # WebSocketRateLimiter: sliding window
    │
    ├── events/
    │   ├── types.py                # WebSocketEvent dataclass inmutable
    │   └── router.py               # EventRouter: validación + routing
    │
    ├── broadcast/
    │   ├── router.py               # BroadcastRouter: Strategy + Observer
    │   └── tenant_filter.py        # TenantFilter: aislamiento multi-tenant
    │
    ├── auth/
    │   └── strategies.py           # JWT, TableToken, Composite auth strategies
    │
    ├── endpoints/
    │   ├── base.py                 # WebSocketEndpointBase, JWTWebSocketEndpoint
    │   ├── mixins.py               # Mixins SRP: validation, heartbeat, lifecycle
    │   └── handlers.py             # Waiter, Kitchen, Admin, Diner handlers
    │
    ├── resilience/
    │   ├── circuit_breaker.py      # CircuitBreaker para Redis
    │   └── retry.py                # RetryConfig con jitter decorrelacionado
    │
    └── metrics/
        ├── collector.py            # MetricsCollector: contadores thread-safe
        └── prometheus.py           # PrometheusFormatter: exportación /metrics
```

### 4.3 Broadcast Paralelo con Batching

El patrón de broadcast paralelo representa una de las optimizaciones más críticas para escenarios de alta concurrencia. Sin esta optimización, enviar un mensaje a 400 usuarios requeriría ~4 segundos (10ms por conexión × 400); con batching paralelo, el mismo broadcast completa en ~160ms:

```python
class ConnectionBroadcaster:
    """
    Componente responsable de envío y broadcast de mensajes.

    Implementa broadcast paralelo con batching para optimizar
    escenarios de alta concurrencia (400-600 usuarios).
    """

    def __init__(self, batch_size: int = 50):
        self._batch_size = batch_size
        self._metrics = MetricsCollector()

    async def broadcast_to_connections(
        self,
        connections: list[WebSocket],
        payload: dict,
        context: str = "",
    ) -> BroadcastResult:
        """
        Envía payload a múltiples conexiones en paralelo con batching.

        El batching previene sobrecarga del event loop al limitar
        el número de corutinas concurrentes.
        """
        if not connections:
            return BroadcastResult(sent=0, failed=0)

        total_sent = 0
        total_failed = 0
        payload_json = json.dumps(payload)

        # Procesar en batches de 50 conexiones
        for i in range(0, len(connections), self._batch_size):
            batch = connections[i : i + self._batch_size]

            # Ejecutar batch en paralelo con gather
            results = await asyncio.gather(
                *[self._send_to_single(ws, payload_json) for ws in batch],
                return_exceptions=True,  # No propagar excepciones individuales
            )

            # Contabilizar resultados
            for result in results:
                if result is True:
                    total_sent += 1
                else:
                    total_failed += 1

        # Registrar métricas
        self._metrics.record_broadcast(total_sent, total_failed, context)

        return BroadcastResult(sent=total_sent, failed=total_failed)

    async def _send_to_single(self, ws: WebSocket, payload_json: str) -> bool:
        """
        Envía mensaje a una conexión individual con manejo de errores.

        Retorna True si el envío fue exitoso, False en caso contrario.
        """
        try:
            # Verificar estado de conexión antes de enviar
            if not is_ws_connected(ws):
                return False

            await asyncio.wait_for(
                ws.send_text(payload_json),
                timeout=5.0,  # Timeout de 5 segundos por envío
            )
            return True

        except asyncio.TimeoutError:
            logger.warning("WebSocket send timeout", ws_id=id(ws))
            return False

        except WebSocketDisconnect:
            # Conexión cerrada, se limpiará en cleanup periódico
            return False

        except Exception as e:
            logger.error("WebSocket send error", error=str(e), ws_id=id(ws))
            return False
```

### 4.4 Sistema de Locks Fragmentados

Para reducir la contención en escenarios de alta concurrencia, el sistema implementa locks fragmentados (sharded locks) por branch y usuario. Esta estrategia permite que operaciones en diferentes sucursales procedan en paralelo sin bloquearse mutuamente:

```python
class LockManager:
    """
    Gestor de locks fragmentados para reducir contención.

    En lugar de un único lock global, mantiene locks separados por:
    - Branch: operaciones en sucursales diferentes no se bloquean
    - Usuario: conexiones del mismo usuario se serializan
    """

    def __init__(self, max_cached_locks: int = 500):
        self._global_lock = asyncio.Lock()
        self._branch_locks: dict[int, asyncio.Lock] = {}
        self._user_locks: dict[int, asyncio.Lock] = {}
        self._lock_access_times: dict[str, float] = {}
        self._max_cached = max_cached_locks
        self._cleanup_threshold = int(max_cached_locks * 0.8)  # 80%

    async def get_branch_lock(self, branch_id: int) -> asyncio.Lock:
        """
        Obtiene lock específico para una sucursal.

        Los locks se crean lazily y se cachean para reutilización.
        """
        async with self._global_lock:
            if branch_id not in self._branch_locks:
                # Verificar si necesitamos limpiar locks antiguos
                await self._maybe_cleanup_locks()
                self._branch_locks[branch_id] = asyncio.Lock()

            # Registrar acceso para LRU cleanup
            self._lock_access_times[f"branch:{branch_id}"] = time.time()
            return self._branch_locks[branch_id]

    async def get_user_lock(self, user_id: int) -> asyncio.Lock:
        """Obtiene lock específico para un usuario."""
        async with self._global_lock:
            if user_id not in self._user_locks:
                await self._maybe_cleanup_locks()
                self._user_locks[user_id] = asyncio.Lock()

            self._lock_access_times[f"user:{user_id}"] = time.time()
            return self._user_locks[user_id]

    async def _maybe_cleanup_locks(self) -> None:
        """
        Limpia locks no utilizados cuando se excede el umbral.

        Usa estrategia LRU: elimina los locks menos recientemente accedidos.
        Implementa histéresis para evitar "cleanup thrashing".
        """
        total_locks = len(self._branch_locks) + len(self._user_locks)

        if total_locks < self._cleanup_threshold:
            return

        # Ordenar por tiempo de acceso (más antiguos primero)
        sorted_keys = sorted(
            self._lock_access_times.items(),
            key=lambda x: x[1],
        )

        # Eliminar 20% de los locks más antiguos
        to_remove = int(total_locks * 0.2)

        for key, _ in sorted_keys[:to_remove]:
            lock_type, lock_id = key.split(":")
            lock_id = int(lock_id)

            if lock_type == "branch":
                # Solo eliminar si el lock no está held
                lock = self._branch_locks.get(lock_id)
                if lock and not lock.locked():
                    del self._branch_locks[lock_id]
                    del self._lock_access_times[key]

            elif lock_type == "user":
                lock = self._user_locks.get(lock_id)
                if lock and not lock.locked():
                    del self._user_locks[lock_id]
                    del self._lock_access_times[key]
```

### 4.5 Prevención de Deadlocks: Lock Ordering

El sistema define un orden estricto de adquisición de locks para prevenir deadlocks. Cualquier código que necesite múltiples locks debe adquirirlos en este orden:

```python
class LockSequence:
    """
    Guard que enforza el orden correcto de adquisición de locks.

    Orden definido (siempre adquirir de menor a mayor):
    1. connection_counter_lock (global)
    2. user_locks (por user_id ascendente)
    3. branch_locks (por branch_id ascendente)
    4. sector_lock, session_lock, dead_connections_lock (globales)

    Violaciones del orden causan assertion error en desarrollo.
    """

    LOCK_ORDER = {
        "connection_counter": 1,
        "user": 2,
        "branch": 3,
        "sector": 4,
        "session": 4,
        "dead_connections": 4,
    }

    def __init__(self):
        self._held_locks: list[tuple[str, int]] = []

    def acquire(self, lock_type: str, lock_id: int = 0) -> "LockSequence":
        """
        Registra adquisición de lock y valida orden.

        Args:
            lock_type: Tipo de lock (branch, user, etc.)
            lock_id: ID numérico para locks fragmentados

        Returns:
            Self para encadenamiento

        Raises:
            AssertionError si se viola el orden de adquisición
        """
        order = self.LOCK_ORDER.get(lock_type, 99)

        if self._held_locks:
            last_type, last_id = self._held_locks[-1]
            last_order = self.LOCK_ORDER.get(last_type, 99)

            # Verificar orden de tipo
            assert order >= last_order, (
                f"Lock order violation: {lock_type} after {last_type}"
            )

            # Si mismo tipo, verificar orden de ID
            if order == last_order and lock_type in ("user", "branch"):
                assert lock_id > last_id, (
                    f"Lock ID order violation: {lock_type}:{lock_id} after {lock_type}:{last_id}"
                )

        self._held_locks.append((lock_type, lock_id))
        return self

    def release(self, lock_type: str, lock_id: int = 0) -> None:
        """Registra liberación de lock (debe ser en orden inverso)."""
        if self._held_locks and self._held_locks[-1] == (lock_type, lock_id):
            self._held_locks.pop()
```

### 4.6 Circuit Breaker para Redis

El circuit breaker protege al sistema de cascadas de fallos cuando Redis experimenta problemas:

```python
class CircuitBreaker:
    """
    Implementación del patrón Circuit Breaker para Redis.

    Estados:
    - CLOSED: Operación normal, los errores incrementan contador
    - OPEN: Circuito abierto, todas las operaciones fallan inmediatamente
    - HALF_OPEN: Permite una operación de prueba para verificar recuperación

    El circuit breaker previene que fallos de Redis saturen
    el sistema con reintentos y timeouts.
    """

    def __init__(
        self,
        failure_threshold: int = 5,
        recovery_timeout: float = 30.0,
        half_open_max_calls: int = 1,
    ):
        self._failure_threshold = failure_threshold
        self._recovery_timeout = recovery_timeout
        self._half_open_max_calls = half_open_max_calls

        self._state = CircuitState.CLOSED
        self._failure_count = 0
        self._last_failure_time: Optional[float] = None
        self._half_open_calls = 0

        self._sync_lock = threading.Lock()

    @property
    def is_open(self) -> bool:
        """Verifica si el circuito está abierto (rechazando llamadas)."""
        with self._sync_lock:
            if self._state == CircuitState.OPEN:
                # Verificar si es tiempo de intentar recuperación
                if self._should_attempt_reset():
                    self._transition_to_internal(CircuitState.HALF_OPEN)
                    return False
                return True
            return False

    @property
    def time_until_recovery(self) -> float:
        """Segundos restantes hasta intento de recuperación."""
        with self._sync_lock:
            if self._state != CircuitState.OPEN or self._last_failure_time is None:
                return 0.0
            elapsed = time.time() - self._last_failure_time
            remaining = self._recovery_timeout - elapsed
            return max(0.0, remaining)

    def record_success(self) -> None:
        """Registra operación exitosa."""
        with self._sync_lock:
            if self._state == CircuitState.HALF_OPEN:
                # Recuperación exitosa, cerrar circuito
                self._transition_to_internal(CircuitState.CLOSED)
            self._failure_count = 0

    def record_failure(self, exception: Exception) -> None:
        """Registra fallo de operación."""
        with self._sync_lock:
            self._failure_count += 1
            self._last_failure_time = time.time()

            logger.warning(
                "Circuit breaker recorded failure",
                failure_count=self._failure_count,
                threshold=self._failure_threshold,
                error=str(exception),
            )

            if self._state == CircuitState.HALF_OPEN:
                # Fallo durante prueba, reabrir circuito
                self._transition_to_internal(CircuitState.OPEN)

            elif self._failure_count >= self._failure_threshold:
                # Umbral alcanzado, abrir circuito
                self._transition_to_internal(CircuitState.OPEN)

    def _should_attempt_reset(self) -> bool:
        """Determina si debe intentar recuperación."""
        if self._last_failure_time is None:
            return True
        elapsed = time.time() - self._last_failure_time
        return elapsed >= self._recovery_timeout

    def _transition_to_internal(self, new_state: CircuitState) -> None:
        """
        Transiciona a nuevo estado (DEBE llamarse con lock held).

        Este método modifica estado interno y debe ser llamado
        únicamente desde métodos que ya posean el lock.
        """
        old_state = self._state
        self._state = new_state

        if new_state == CircuitState.CLOSED:
            self._failure_count = 0
            self._half_open_calls = 0

        elif new_state == CircuitState.HALF_OPEN:
            self._half_open_calls = 0

        logger.info(
            "Circuit breaker state transition",
            old_state=old_state.value,
            new_state=new_state.value,
        )

    def get_stats(self) -> dict:
        """Retorna estadísticas del circuit breaker (thread-safe)."""
        with self._sync_lock:
            return {
                "state": self._state.value,
                "failure_count": self._failure_count,
                "failure_threshold": self._failure_threshold,
                "time_until_recovery": self.time_until_recovery,
            }
```

### 4.7 Retry con Jitter Decorrelacionado

Para reconexiones a Redis, el sistema implementa backoff exponencial con jitter decorrelacionado, previniendo el problema de "thundering herd" donde múltiples clientes reconectan simultáneamente:

```python
class DecorrelatedJitter:
    """
    Implementación de jitter decorrelacionado para backoff exponencial.

    A diferencia del jitter simple (random entre 0 y delay calculado),
    el jitter decorrelacionado produce distribuciones más uniformes
    que previenen mejor la sincronización accidental de reintentos.

    Algoritmo: delay = min(max_delay, random(base_delay, prev_delay * 3))
    """

    def __init__(self, base_delay: float = 1.0, max_delay: float = 60.0):
        self._base = base_delay
        self._max = max_delay
        self._prev_delay = base_delay

    def next_delay(self) -> float:
        """Calcula el próximo delay con jitter decorrelacionado."""
        # Rango: [base, prev * 3]
        delay = random.uniform(self._base, self._prev_delay * 3)

        # Limitar al máximo
        delay = min(delay, self._max)

        # Guardar para próxima iteración
        self._prev_delay = delay

        return delay

    def reset(self) -> None:
        """Reinicia el estado tras conexión exitosa."""
        self._prev_delay = self._base


def calculate_delay_with_jitter(
    attempt: int,
    config: RetryConfig,
) -> float:
    """
    Calcula delay para un intento específico con jitter.

    Args:
        attempt: Número de intento (0-indexed)
        config: Configuración de retry

    Returns:
        Delay en segundos con jitter aplicado
    """
    # Backoff exponencial base: base * 2^attempt
    base_delay = config.base_delay * (2 ** attempt)

    # Limitar al máximo
    capped_delay = min(base_delay, config.max_delay)

    # Aplicar jitter: random entre 0.5 y 1.0 del delay
    jitter_factor = random.uniform(0.5, 1.0)

    return capped_delay * jitter_factor
```

### 4.8 Filtrado por Sectores para Meseros

Los meseros solo reciben eventos de las mesas asignadas a sus sectores para el día actual. Esta funcionalidad reduce significativamente el ruido de notificaciones y mejora la experiencia del usuario:

```python
class SectorAssignmentRepository:
    """
    Repositorio para consultar asignaciones de meseros a sectores.

    Implementa caché con TTL para reducir consultas a base de datos.
    """

    def __init__(self, db_url: str, cache_ttl: int = 300):
        self._db_url = db_url
        self._cache: dict[int, SectorCache] = {}
        self._cache_ttl = cache_ttl
        self._lock = asyncio.Lock()

    async def get_assigned_sector_ids(self, user_id: int, branch_id: int) -> set[int]:
        """
        Obtiene IDs de sectores asignados a un mesero para hoy.

        Usa caché para evitar consultas repetidas durante la sesión.
        """
        cache_key = (user_id, branch_id)

        async with self._lock:
            cached = self._cache.get(cache_key)
            if cached and not cached.is_expired:
                return cached.sector_ids

        # Consultar base de datos
        sector_ids = await self._query_assignments(user_id, branch_id)

        # Actualizar caché
        async with self._lock:
            self._cache[cache_key] = SectorCache(
                sector_ids=sector_ids,
                expires_at=time.time() + self._cache_ttl,
            )

        return sector_ids

    async def _query_assignments(self, user_id: int, branch_id: int) -> set[int]:
        """Consulta asignaciones en base de datos."""
        async with self._get_session() as session:
            result = await session.execute(
                select(WaiterSectorAssignment.sector_id)
                .where(WaiterSectorAssignment.user_id == user_id)
                .where(WaiterSectorAssignment.branch_id == branch_id)
                .where(WaiterSectorAssignment.date == date.today())
                .where(WaiterSectorAssignment.is_active.is_(True))
            )
            return set(result.scalars().all())


async def filter_connections_by_sector(
    connections: list[WaiterConnection],
    sector_id: int,
    repo: SectorAssignmentRepository,
) -> list[WaiterConnection]:
    """
    Filtra conexiones de meseros por sector asignado.

    ADMIN y MANAGER siempre reciben todos los eventos de la sucursal.
    """
    filtered = []

    for conn in connections:
        # ADMIN/MANAGER siempre reciben todo
        if conn.is_management:
            filtered.append(conn)
            continue

        # Verificar asignación de sector
        assigned_sectors = await repo.get_assigned_sector_ids(
            user_id=conn.user_id,
            branch_id=conn.branch_id,
        )

        if sector_id in assigned_sectors:
            filtered.append(conn)

    return filtered
```

---

## Capítulo V: Frontend - Arquitectura React 19 con Zustand

### 5.1 El Problema de los Re-renders Infinitos

React 19, con su modelo de renderizado más agresivo y el nuevo compilador, expone con mayor frecuencia un problema latente en aplicaciones que usan Zustand: los re-renders infinitos causados por referencias de objetos inestables. Cada vez que un selector retorna un nuevo objeto (incluso si es estructuralmente idéntico), React considera que el estado cambió y re-renderiza el componente.

El patrón anti-patrón más común es la desestructuración directa del store:

```typescript
// ⛔ INCORRECTO: Causa re-renders infinitos en React 19
function ProductList() {
  // Cada render crea nueva referencia de objeto
  const { products, addProduct } = useProductStore()

  return (
    <ul>
      {products.map(p => <ProductItem key={p.id} product={p} />)}
    </ul>
  )
}
```

El problema ocurre porque `useProductStore()` sin selector retorna todo el estado del store, creando un nuevo objeto en cada llamada. React detecta este "cambio" y re-renderiza, lo que vuelve a llamar al hook, creando un ciclo infinito.

### 5.2 Selectores Atómicos y Referencias Estables

La solución consiste en usar selectores atómicos que extraen exactamente lo que el componente necesita:

```typescript
// ✅ CORRECTO: Selectores atómicos previenen re-renders innecesarios

// Definir selectores fuera del componente
const selectProducts = (state: ProductState) => state.products
const selectAddProduct = (state: ProductState) => state.addProduct

function ProductList() {
  // Cada selector retorna la misma referencia si el valor no cambió
  const products = useProductStore(selectProducts)
  const addProduct = useProductStore(selectAddProduct)

  return (
    <ul>
      {products.map(p => <ProductItem key={p.id} product={p} />)}
    </ul>
  )
}
```

Para arrays vacíos, es crítico usar una referencia estable compartida:

```typescript
// ✅ Referencia estable para array vacío
const EMPTY_PRODUCTS: Product[] = []

export const selectProducts = (state: ProductState) =>
  state.products.length > 0 ? state.products : EMPTY_PRODUCTS
```

Sin esta optimización, cada vez que `products` está vacío, el selector retornaría un nuevo array `[]`, causando re-renders.

### 5.3 Selectores Derivados con Caché Externa

Cuando los selectores necesitan filtrar o transformar datos, se requiere caché externa para mantener referencias estables:

```typescript
// Caché externa al componente
const pendingOrdersCache = {
  source: null as Table[] | null,
  result: [] as Table[],
}

export const selectTablesWithPendingOrders = (state: TablesState): Table[] => {
  // Si la fuente no cambió, retornar resultado cacheado
  if (state.tables === pendingOrdersCache.source) {
    return pendingOrdersCache.result
  }

  // Recalcular
  const filtered = state.tables.filter(t => t.pending_rounds > 0)

  // Actualizar caché
  pendingOrdersCache.source = state.tables
  pendingOrdersCache.result = filtered.length > 0 ? filtered : EMPTY_TABLES

  return pendingOrdersCache.result
}
```

Este patrón garantiza que el selector retorna la misma referencia mientras los datos fuente no cambien, eliminando re-renders innecesarios.

### 5.4 Sincronización Multi-Tab

pwaMenu implementa sincronización entre tabs del mismo navegador para el carrito compartido. Cuando un comensal agrega un producto en una tab, el cambio se refleja instantáneamente en todas las tabs abiertas del mismo dispositivo:

```typescript
// En la definición del store
export const createTableStore = () => {
  const store = create<TableState>()(
    persist(
      (set, get) => ({
        // ... estado inicial

        syncFromStorage: () => {
          // Obtener estado de localStorage (actualizado por otra tab)
          const storageData = localStorage.getItem('table-store')
          if (!storageData) return

          const storageState = JSON.parse(storageData)
          const currentCart = get().session?.sharedCart ?? []
          const storageCart = storageState?.session?.sharedCart ?? []

          // Merge inteligente: mantener items locales, agregar remotos
          const mergedCartMap = new Map<string, CartItem>()

          // Items locales primero
          currentCart.forEach((item: CartItem) => {
            mergedCartMap.set(item.id, item)
          })

          // Items de storage (sobrescriben si hay conflicto por ID)
          storageCart.forEach((item: CartItem) => {
            mergedCartMap.set(item.id, item)
          })

          set({
            session: {
              ...storageState.session,
              sharedCart: Array.from(mergedCartMap.values()),
            },
          })
        },
      }),
      {
        name: 'table-store',
        storage: createJSONStorage(() => localStorage),
      }
    )
  )

  // Escuchar cambios de storage desde otras tabs
  if (typeof window !== 'undefined') {
    window.addEventListener('storage', (event) => {
      if (event.key === 'table-store' && event.newValue) {
        store.getState().syncFromStorage()
      }
    })
  }

  return store
}
```

### 5.5 Integración WebSocket con Ref Pattern

Para evitar acumulación de listeners en hooks de WebSocket, se usa el patrón ref:

```typescript
function useWebSocketEvents(ws: WebSocketClient) {
  const [tables, setTables] = useState<Table[]>([])

  // Ref que siempre apunta al handler actual
  const handleEventRef = useRef<(event: WSEvent) => void>(() => {})

  // Actualizar ref cuando cambian dependencias
  useEffect(() => {
    handleEventRef.current = (event: WSEvent) => {
      if (event.type === 'TABLE_STATUS_CHANGED') {
        setTables(prev =>
          prev.map(t => t.id === event.table_id
            ? { ...t, status: event.status }
            : t
          )
        )
      }
    }
  }, []) // Sin dependencias: el ref se actualiza arriba

  // Suscripción única que delega al ref
  useEffect(() => {
    const unsubscribe = ws.on('*', (event) => {
      handleEventRef.current(event)
    })

    return unsubscribe
  }, [ws]) // Solo resuscribirse si cambia la instancia de WS
}
```

Este patrón garantiza que solo existe una suscripción activa, mientras el handler puede acceder al estado más reciente a través del ref.

---

## Capítulo VI: pwaMenu - Sistema de Pedido Colaborativo

### 6.1 Arquitectura del Carrito Compartido

El carrito compartido permite que múltiples comensales en la misma mesa contribuyan productos desde sus dispositivos individuales. Cada ítem mantiene atribución al comensal que lo agregó:

```typescript
interface CartItem {
  id: string                    // UUID generado localmente
  productId: number             // Referencia al producto
  productName: string           // Cache del nombre para offline
  quantity: number              // Cantidad solicitada
  unitPrice: number             // Precio unitario en centavos
  dinerId: string               // ID del comensal que agregó
  dinerName: string             // Nombre del comensal
  modifiers: ProductModifier[]  // Modificaciones (sin cebolla, etc.)
  notes: string                 // Notas especiales
  addedAt: Date                 // Timestamp de adición
}

interface SharedCart {
  items: CartItem[]
  lastModified: Date
  version: number  // Para detección de conflictos
}
```

La sincronización entre dispositivos de diferentes comensales ocurre a través del backend y WebSocket:

1. Comensal A agrega producto → `POST /api/diner/cart/items`
2. Backend persiste y publica evento → Redis pub/sub
3. WebSocket Gateway recibe evento → broadcast a sesión de mesa
4. Dispositivo de Comensal B recibe evento → actualiza store local

### 6.2 Protocolo de Confirmación Grupal

Para prevenir envíos accidentales, el sistema implementa un protocolo de confirmación grupal antes de enviar una ronda a cocina:

```typescript
interface RoundConfirmation {
  proposerId: string          // Comensal que inició la propuesta
  proposerName: string        // Nombre para mostrar
  proposedAt: Date            // Timestamp de propuesta
  expiresAt: Date             // Expiración (5 minutos)
  readyDiners: Set<string>    // Comensales que confirmaron
  totalDiners: number         // Total de comensales en mesa
}

// Flujo de confirmación
const confirmationFlow = {
  // 1. Comensal propone enviar
  proposeRound: () => {
    set({
      roundConfirmation: {
        proposerId: get().currentDiner.id,
        proposerName: get().currentDiner.name,
        proposedAt: new Date(),
        expiresAt: addMinutes(new Date(), 5),
        readyDiners: new Set([get().currentDiner.id]), // Proposer auto-confirma
        totalDiners: get().session.diners.length,
      },
    })

    // Notificar a otros comensales via WebSocket
    api.proposeRound(get().session.id)
  },

  // 2. Otros comensales confirman
  confirmReady: () => {
    const confirmation = get().roundConfirmation
    if (!confirmation) return

    const newReady = new Set(confirmation.readyDiners)
    newReady.add(get().currentDiner.id)

    set({
      roundConfirmation: {
        ...confirmation,
        readyDiners: newReady,
      },
    })

    // Notificar confirmación
    api.confirmReady(get().session.id, get().currentDiner.id)

    // Verificar si todos confirmaron
    if (newReady.size >= confirmation.totalDiners) {
      // Auto-enviar tras delay
      setTimeout(() => {
        get().submitRound()
      }, 1500)
    }
  },

  // 3. Cancelar propuesta (solo el proposer)
  cancelProposal: () => {
    if (get().roundConfirmation?.proposerId !== get().currentDiner.id) {
      return // Solo el proposer puede cancelar
    }

    set({ roundConfirmation: null })
    api.cancelProposal(get().session.id)
  },
}
```

### 6.3 Sistema de Filtrado Avanzado

El sistema de filtrado permite a los comensales personalizar el menú según sus restricciones dietéticas:

```typescript
// Hook para filtrado por alérgenos con reacciones cruzadas
function useAllergenFilter() {
  const allergens = useMenuStore(selectAllergens)
  const crossReactions = useMenuStore(selectCrossReactions)

  const filterProducts = useCallback((
    products: Product[],
    selectedAllergenIds: number[],
    strictness: 'strict' | 'moderate' | 'lenient',
  ): Product[] => {
    if (selectedAllergenIds.length === 0) {
      return products
    }

    // Expandir con reacciones cruzadas si modo estricto
    let allergenIdsToFilter = new Set(selectedAllergenIds)

    if (strictness === 'strict') {
      selectedAllergenIds.forEach(id => {
        const reactions = crossReactions.get(id) ?? []
        reactions.forEach(r => allergenIdsToFilter.add(r.crossReactsWithId))
      })
    }

    return products.filter(product => {
      const productAllergens = product.allergens ?? []

      return !productAllergens.some(pa => {
        // Verificar si el alérgeno está en la lista a filtrar
        if (!allergenIdsToFilter.has(pa.allergenId)) {
          return false
        }

        // Aplicar lógica según nivel de presencia
        switch (strictness) {
          case 'strict':
            // Cualquier presencia (CONTAINS, MAY_CONTAIN, TRACES) excluye
            return true

          case 'moderate':
            // Solo CONTAINS y MAY_CONTAIN excluyen
            return pa.presenceType !== 'TRACES'

          case 'lenient':
            // Solo CONTAINS excluye
            return pa.presenceType === 'CONTAINS'
        }
      })
    })
  }, [crossReactions])

  return { filterProducts }
}


// Hook para filtros dietéticos
function useDietaryFilter() {
  const filterProducts = useCallback((
    products: Product[],
    filters: DietaryFilter[],
  ): Product[] => {
    if (filters.length === 0) {
      return products
    }

    return products.filter(product => {
      const profile = product.dietaryProfile
      if (!profile) return false

      return filters.every(filter => {
        switch (filter) {
          case 'vegetarian':
            return profile.isVegetarian
          case 'vegan':
            return profile.isVegan
          case 'gluten_free':
            return profile.isGlutenFree
          case 'celiac_safe':
            return profile.isCeliacSafe && profile.isGlutenFree
          case 'keto':
            return profile.isKeto
          case 'low_sodium':
            return profile.isLowSodium
          default:
            return true
        }
      })
    })
  }, [])

  return { filterProducts }
}


// Hook para filtros de método de cocción
function useCookingMethodFilter() {
  const filterProducts = useCallback((
    products: Product[],
    excludedMethods: CookingMethod[],
    requiredMethods: CookingMethod[],
  ): Product[] => {
    return products.filter(product => {
      const methods = product.cookingMethods ?? []

      // Verificar exclusiones
      const hasExcluded = excludedMethods.some(m => methods.includes(m))
      if (hasExcluded) return false

      // Verificar requeridos (si hay alguno)
      if (requiredMethods.length > 0) {
        const hasRequired = requiredMethods.some(m => methods.includes(m))
        if (!hasRequired) return false
      }

      return true
    })
  }, [])

  return { filterProducts }
}
```

### 6.4 Configuración PWA con Workbox

La aplicación utiliza estrategias de caché diferenciadas para optimizar la experiencia offline:

```typescript
// vite.config.ts
export default defineConfig({
  plugins: [
    react(),
    VitePWA({
      registerType: 'autoUpdate',
      includeAssets: ['favicon.ico', 'apple-touch-icon.png', 'masked-icon.svg'],

      manifest: {
        name: 'Menu Digital',
        short_name: 'Menu',
        description: 'Menú digital con pedido colaborativo',
        theme_color: '#0078d4',
        background_color: '#ffffff',
        display: 'standalone',
        orientation: 'portrait',
        start_url: '/',
        icons: [
          { src: 'pwa-192x192.png', sizes: '192x192', type: 'image/png' },
          { src: 'pwa-512x512.png', sizes: '512x512', type: 'image/png' },
        ],
      },

      workbox: {
        // Archivos a pre-cachear (shell de la aplicación)
        globPatterns: ['**/*.{js,css,html,ico,png,svg,woff2}'],

        // Estrategias de runtime caching
        runtimeCaching: [
          // Menú: Network First con fallback a cache
          {
            urlPattern: /^https:\/\/api\..*\/public\/menu/,
            handler: 'NetworkFirst',
            options: {
              cacheName: 'menu-cache',
              networkTimeoutSeconds: 3, // Timeout corto para UX
              expiration: {
                maxEntries: 50,
                maxAgeSeconds: 86400, // 24 horas
              },
              cacheableResponse: {
                statuses: [0, 200],
              },
            },
          },

          // Imágenes de productos: Cache First
          {
            urlPattern: /\.(png|jpg|jpeg|webp|avif)$/,
            handler: 'CacheFirst',
            options: {
              cacheName: 'images-cache',
              expiration: {
                maxEntries: 200,
                maxAgeSeconds: 604800, // 7 días
              },
              cacheableResponse: {
                statuses: [0, 200],
              },
            },
          },

          // API transaccional: Network Only (no cachear)
          {
            urlPattern: /^https:\/\/api\..*\/(diner|billing)/,
            handler: 'NetworkOnly',
          },

          // Traducciones: Stale While Revalidate
          {
            urlPattern: /\/locales\/.*\.json$/,
            handler: 'StaleWhileRevalidate',
            options: {
              cacheName: 'i18n-cache',
              expiration: {
                maxEntries: 10,
                maxAgeSeconds: 86400,
              },
            },
          },
        ],

        // Página de fallback offline
        navigateFallback: '/offline.html',
        navigateFallbackDenylist: [/^\/api/],
      },
    }),
  ],
})
```

### 6.5 Sistema de Fidelización sin Fricción

El sistema de fidelización opera en cuatro fases progresivas, cada una añadiendo capacidades sin requerir registro explícito hasta la fase final:

**Fase 1: Tracking por Dispositivo**

```typescript
// utils/deviceId.ts
const DEVICE_ID_KEY = 'integrador_device_id'

export function getOrCreateDeviceId(): string {
  let deviceId = localStorage.getItem(DEVICE_ID_KEY)

  if (!deviceId) {
    deviceId = crypto.randomUUID()
    localStorage.setItem(DEVICE_ID_KEY, deviceId)
  }

  return deviceId
}

// El device_id se envía con cada petición de diner
// Permite identificar visitas recurrentes sin login
```

**Fase 2: Preferencias Implícitas**

```typescript
// hooks/useImplicitPreferences.ts
function useImplicitPreferences(branchSlug: string) {
  const deviceId = getOrCreateDeviceId()
  const [filters, setFilters] = useState<ImplicitPreferences | null>(null)

  // Cargar preferencias guardadas al montar
  useEffect(() => {
    async function loadPreferences() {
      try {
        const response = await api.get(`/diner/device/${deviceId}/preferences`)
        if (response.data) {
          setFilters(response.data)
          // Aplicar filtros automáticamente
          applyFiltersToMenuStore(response.data)
        }
      } catch (error) {
        // Sin preferencias guardadas, usar defaults
      }
    }

    loadPreferences()
  }, [deviceId])

  // Sincronizar cambios de filtros con debounce
  const syncPreferences = useDebouncedCallback(
    async (newFilters: ImplicitPreferences) => {
      await api.patch('/diner/preferences', {
        device_id: deviceId,
        allergens: newFilters.allergenIds,
        dietary: newFilters.dietaryFilters,
        cooking_excluded: newFilters.excludedCookingMethods,
      })
    },
    2000, // 2 segundos de debounce
  )

  return { filters, setFilters: (f) => { setFilters(f); syncPreferences(f) } }
}
```

**Fase 4: Registro Opt-in con Consentimiento GDPR**

```typescript
// components/OptInModal.tsx
function OptInModal({ isOpen, onClose }: OptInModalProps) {
  const [formData, setFormData] = useState({
    name: '',
    email: '',
    phone: '',
    consentMarketing: false,
    consentAnalytics: false,
    consentPersonalization: true, // Default on
  })

  const handleSubmit = async () => {
    const response = await api.post('/customer/register', {
      ...formData,
      device_id: getOrCreateDeviceId(),
    })

    if (response.data.customer_id) {
      // Vincular dispositivo a cliente
      // Futuras visitas reconocerán automáticamente
      onClose()
    }
  }

  return (
    <Modal isOpen={isOpen} onClose={onClose}>
      <h2>Únete a nuestro programa de fidelización</h2>

      <Input
        label="Nombre"
        value={formData.name}
        onChange={e => setFormData({ ...formData, name: e.target.value })}
      />

      <Input
        label="Email"
        type="email"
        value={formData.email}
        onChange={e => setFormData({ ...formData, email: e.target.value })}
      />

      <Divider />

      <h3>Consentimientos (GDPR)</h3>

      <Checkbox
        checked={formData.consentMarketing}
        onChange={e => setFormData({ ...formData, consentMarketing: e.target.checked })}
        label="Recibir ofertas y promociones por email"
      />

      <Checkbox
        checked={formData.consentAnalytics}
        onChange={e => setFormData({ ...formData, consentAnalytics: e.target.checked })}
        label="Permitir análisis de mis pedidos para estadísticas"
      />

      <Checkbox
        checked={formData.consentPersonalization}
        onChange={e => setFormData({ ...formData, consentPersonalization: e.target.checked })}
        label="Recibir recomendaciones personalizadas basadas en mi historial"
      />

      <Button onClick={handleSubmit}>Registrarme</Button>
    </Modal>
  )
}
```

---

## Capítulo VII: Seguridad y Autenticación

### 7.1 Estrategias de Autenticación

El sistema implementa dos mecanismos de autenticación diferenciados según el tipo de usuario:

**JWT para Usuarios del Sistema (Dashboard, pwaWaiter)**

```python
# shared/security/auth.py
def create_access_token(user: User, branches: list[Branch]) -> str:
    """
    Genera JWT de acceso con claims de usuario.

    El token incluye toda la información necesaria para autorización,
    evitando consultas a base de datos en cada petición.
    """
    now = datetime.utcnow()

    payload = {
        "sub": str(user.id),          # Subject: ID de usuario
        "email": user.email,
        "tenant_id": user.tenant_id,
        "branch_ids": [b.id for b in branches],
        "roles": [ubr.role for ubr in user.branch_roles],
        "iat": now,                    # Issued At
        "exp": now + timedelta(minutes=15),  # Expiration
        "jti": str(uuid.uuid4()),      # JWT ID para blacklist
    }

    return jwt.encode(payload, settings.jwt_secret, algorithm="HS256")


def verify_jwt(token: str) -> dict:
    """
    Verifica y decodifica JWT.

    Implementa verificación de blacklist para tokens revocados.
    """
    try:
        payload = jwt.decode(
            token,
            settings.jwt_secret,
            algorithms=["HS256"],
        )

        # Verificar blacklist (logout, cambio de contraseña)
        if is_token_blacklisted(payload["jti"]):
            raise HTTPException(
                status_code=401,
                detail="Token revocado",
            )

        return payload

    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="Token expirado")
    except jwt.InvalidTokenError:
        raise HTTPException(status_code=401, detail="Token inválido")
```

**Table Token para Comensales (pwaMenu)**

```python
def create_table_token(table_session: TableSession) -> str:
    """
    Genera token HMAC para sesión de mesa.

    Este token tiene menor duración (3 horas) y permisos limitados.
    No contiene información sensible del usuario.
    """
    payload = {
        "session_id": table_session.id,
        "table_id": table_session.table_id,
        "branch_id": table_session.table.branch_id,
        "tenant_id": table_session.table.branch.tenant_id,
        "exp": datetime.utcnow() + timedelta(hours=3),
    }

    # Serializar y firmar con HMAC-SHA256
    payload_bytes = json.dumps(payload, sort_keys=True).encode()
    signature = hmac.new(
        settings.table_token_secret.encode(),
        payload_bytes,
        hashlib.sha256,
    ).hexdigest()

    token_data = base64.urlsafe_b64encode(payload_bytes).decode()
    return f"{token_data}.{signature}"


def verify_table_token(token: str) -> dict:
    """Verifica token de mesa."""
    try:
        token_data, signature = token.rsplit(".", 1)
        payload_bytes = base64.urlsafe_b64decode(token_data)

        # Verificar firma
        expected_sig = hmac.new(
            settings.table_token_secret.encode(),
            payload_bytes,
            hashlib.sha256,
        ).hexdigest()

        if not hmac.compare_digest(signature, expected_sig):
            raise HTTPException(status_code=401, detail="Token inválido")

        payload = json.loads(payload_bytes)

        # Verificar expiración
        exp = datetime.fromisoformat(payload["exp"])
        if datetime.utcnow() > exp:
            raise HTTPException(status_code=401, detail="Token expirado")

        return payload

    except (ValueError, KeyError):
        raise HTTPException(status_code=401, detail="Token malformado")
```

### 7.2 Token Blacklist con Fail-Closed

El sistema de blacklist utiliza Redis para invalidar tokens antes de su expiración natural:

```python
async def revoke_token(token_jti: str, expires_at: datetime) -> None:
    """
    Añade token a blacklist.

    El TTL de Redis coincide con la expiración del token,
    evitando crecimiento indefinido de la blacklist.
    """
    redis = await get_redis_pool()
    ttl = int((expires_at - datetime.utcnow()).total_seconds())

    if ttl > 0:
        await redis.setex(
            f"token_blacklist:{token_jti}",
            ttl,
            "1",
        )


async def revoke_all_user_tokens(user_id: int) -> None:
    """
    Revoca todos los tokens de un usuario.

    Usado en logout, cambio de contraseña, o detección de compromiso.
    """
    redis = await get_redis_pool()

    # Incrementar versión de tokens del usuario
    # Todos los tokens anteriores se invalidan
    await redis.incr(f"user_token_version:{user_id}")


async def is_token_blacklisted(token_jti: str) -> bool:
    """
    Verifica si token está en blacklist.

    IMPORTANTE: Implementa patrón fail-closed.
    Si Redis falla, asumimos que el token está revocado.
    """
    try:
        redis = await get_redis_pool()
        exists = await redis.exists(f"token_blacklist:{token_jti}")
        return exists > 0

    except Exception as e:
        logger.error(
            "Redis error checking blacklist - failing closed",
            error=str(e),
            token_jti=token_jti,
        )
        # FAIL CLOSED: en caso de error, tratar como revocado
        return True
```

### 7.3 Middlewares de Seguridad

El backend implementa múltiples capas de seguridad:

```python
# rest_api/core/middlewares.py

class SecurityHeadersMiddleware:
    """
    Añade headers de seguridad a todas las respuestas.
    """

    async def __call__(self, request: Request, call_next):
        response = await call_next(request)

        # Prevenir MIME sniffing
        response.headers["X-Content-Type-Options"] = "nosniff"

        # Prevenir clickjacking
        response.headers["X-Frame-Options"] = "DENY"

        # Protección XSS legacy
        response.headers["X-XSS-Protection"] = "1; mode=block"

        # Control de referrer
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"

        # Política de permisos
        response.headers["Permissions-Policy"] = (
            "geolocation=(), microphone=(), camera=()"
        )

        # Content Security Policy
        response.headers["Content-Security-Policy"] = (
            "default-src 'self'; "
            "script-src 'self'; "
            "style-src 'self' 'unsafe-inline'; "
            "img-src 'self' https: data:; "
            "font-src 'self'; "
            "connect-src 'self' wss: https:; "
            "frame-ancestors 'none';"
        )

        # HSTS (solo en producción)
        if settings.environment == "production":
            response.headers["Strict-Transport-Security"] = (
                "max-age=31536000; includeSubDomains"
            )

        return response


class ContentTypeValidationMiddleware:
    """
    Valida Content-Type en peticiones con body.

    Previene ataques que explotan parsing incorrecto de content types.
    """

    EXEMPT_PATHS = {"/api/billing/webhook", "/api/health"}
    ALLOWED_TYPES = {"application/json", "application/x-www-form-urlencoded"}

    async def __call__(self, request: Request, call_next):
        if request.method in ("POST", "PUT", "PATCH"):
            if request.url.path not in self.EXEMPT_PATHS:
                content_type = request.headers.get("content-type", "")
                base_type = content_type.split(";")[0].strip().lower()

                if base_type and base_type not in self.ALLOWED_TYPES:
                    return JSONResponse(
                        status_code=415,
                        content={"detail": "Unsupported Media Type"},
                    )

        return await call_next(request)
```

### 7.4 Validación de URLs de Imagen (Prevención SSRF)

```python
# shared/utils/validators.py

BLOCKED_HOSTS = frozenset({
    "localhost",
    "127.0.0.1",
    "0.0.0.0",
    "::1",
    "169.254.169.254",     # AWS metadata
    "metadata.google",      # GCP metadata
    "metadata.azure.com",   # Azure metadata
})

BLOCKED_PREFIXES = (
    "10.",
    "172.16.", "172.17.", "172.18.", "172.19.",
    "172.20.", "172.21.", "172.22.", "172.23.",
    "172.24.", "172.25.", "172.26.", "172.27.",
    "172.28.", "172.29.", "172.30.", "172.31.",
    "192.168.",
)


def validate_image_url(url: str) -> None:
    """
    Valida URL de imagen para prevenir SSRF y XSS.

    Args:
        url: URL a validar

    Raises:
        ValidationError: Si la URL es inválida o apunta a host bloqueado
    """
    if not url:
        return  # URLs vacías son válidas (sin imagen)

    try:
        parsed = urlparse(url)
    except Exception:
        raise ValidationError("URL malformada", field="image")

    # Validar esquema
    if parsed.scheme not in ("http", "https"):
        raise ValidationError(
            "Solo se permiten URLs HTTP/HTTPS",
            field="image",
        )

    # Validar host
    host = parsed.hostname
    if not host:
        raise ValidationError("URL sin host", field="image")

    host_lower = host.lower()

    # Verificar hosts bloqueados exactos
    if host_lower in BLOCKED_HOSTS:
        raise ValidationError(
            "URL apunta a host interno no permitido",
            field="image",
        )

    # Verificar prefijos de redes privadas
    if any(host_lower.startswith(prefix) for prefix in BLOCKED_PREFIXES):
        raise ValidationError(
            "URL apunta a red privada no permitida",
            field="image",
        )

    # Verificar longitud máxima
    if len(url) > 500:
        raise ValidationError(
            "URL excede longitud máxima de 500 caracteres",
            field="image",
        )
```

---

## Capítulo VIII: Infraestructura y Operaciones

### 8.1 Configuración Docker para Desarrollo

```yaml
# devOps/docker-compose.yml
version: '3.8'

services:
  postgres:
    image: pgvector/pgvector:pg16
    container_name: integrador-postgres
    ports:
      - "5432:5432"
    environment:
      POSTGRES_DB: integrador
      POSTGRES_USER: postgres
      POSTGRES_PASSWORD: postgres
    volumes:
      - pgdata:/var/lib/postgresql/data
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U postgres"]
      interval: 10s
      timeout: 5s
      retries: 5

  redis:
    image: redis:7-alpine
    container_name: integrador-redis
    ports:
      - "6380:6379"  # Puerto 6380 para evitar conflictos
    command: redis-server --appendonly yes
    volumes:
      - redisdata:/data
    healthcheck:
      test: ["CMD", "redis-cli", "ping"]
      interval: 10s
      timeout: 5s
      retries: 5

volumes:
  pgdata:
  redisdata:
```

### 8.2 Scripts de Inicio

**Windows (PowerShell):**

```powershell
# devOps/start.ps1
# Script de inicio para desarrollo en Windows

# Verificar Docker
if (-not (Get-Process -Name "Docker Desktop" -ErrorAction SilentlyContinue)) {
    Write-Error "Docker Desktop no está corriendo. Inicielo primero."
    exit 1
}

# Iniciar contenedores
Write-Host "Iniciando PostgreSQL y Redis..." -ForegroundColor Green
docker compose -f "$PSScriptRoot/docker-compose.yml" up -d

# Esperar a que los servicios estén listos
Start-Sleep -Seconds 5

# Configurar PYTHONPATH
$env:PYTHONPATH = (Get-Item "$PSScriptRoot/..").FullName + "\backend"
Write-Host "PYTHONPATH = $env:PYTHONPATH" -ForegroundColor Cyan

# Iniciar REST API
Write-Host "Iniciando REST API en puerto 8000..." -ForegroundColor Green
Start-Process -NoNewWindow powershell -ArgumentList @(
    "-Command",
    "cd '$PSScriptRoot/../backend'; python -m uvicorn rest_api.main:app --reload --port 8000"
)

# Iniciar WS Gateway
Write-Host "Iniciando WebSocket Gateway en puerto 8001..." -ForegroundColor Green
Start-Process -NoNewWindow powershell -ArgumentList @(
    "-Command",
    "cd '$PSScriptRoot/..'; `$env:PYTHONPATH='$env:PYTHONPATH'; python -m uvicorn ws_gateway.main:app --reload --port 8001"
)

Write-Host "`nServicios iniciados:" -ForegroundColor Yellow
Write-Host "  - REST API: http://localhost:8000"
Write-Host "  - WS Gateway: ws://localhost:8001"
Write-Host "  - PostgreSQL: localhost:5432"
Write-Host "  - Redis: localhost:6380"
```

**Unix/Mac:**

```bash
#!/bin/bash
# devOps/start.sh
# Script de inicio para desarrollo en Unix/Mac

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"

# Colores
GREEN='\033[0;32m'
CYAN='\033[0;36m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Verificar Docker
if ! docker info > /dev/null 2>&1; then
    echo "Error: Docker no está corriendo. Inicielo primero."
    exit 1
fi

# Iniciar contenedores
echo -e "${GREEN}Iniciando PostgreSQL y Redis...${NC}"
docker compose -f "$SCRIPT_DIR/docker-compose.yml" up -d

# Esperar a que los servicios estén listos
sleep 5

# Configurar PYTHONPATH
export PYTHONPATH="$PROJECT_ROOT/backend"
echo -e "${CYAN}PYTHONPATH = $PYTHONPATH${NC}"

# Iniciar REST API en background
echo -e "${GREEN}Iniciando REST API en puerto 8000...${NC}"
cd "$PROJECT_ROOT/backend"
uvicorn rest_api.main:app --reload --port 8000 &
REST_PID=$!

# Iniciar WS Gateway en background
echo -e "${GREEN}Iniciando WebSocket Gateway en puerto 8001...${NC}"
cd "$PROJECT_ROOT"
uvicorn ws_gateway.main:app --reload --port 8001 &
WS_PID=$!

echo -e "\n${YELLOW}Servicios iniciados:${NC}"
echo "  - REST API: http://localhost:8000 (PID: $REST_PID)"
echo "  - WS Gateway: ws://localhost:8001 (PID: $WS_PID)"
echo "  - PostgreSQL: localhost:5432"
echo "  - Redis: localhost:6380"

# Trap para cleanup
cleanup() {
    echo -e "\n${YELLOW}Deteniendo servicios...${NC}"
    kill $REST_PID $WS_PID 2>/dev/null
}
trap cleanup EXIT

# Mantener script corriendo
wait
```

### 8.3 Variables de Entorno para Producción

```bash
# backend/.env.production

# ═══════════════════════════════════════════════════════════════════════════
# SEGURIDAD (OBLIGATORIO - Generar con: openssl rand -base64 32)
# ═══════════════════════════════════════════════════════════════════════════
JWT_SECRET=<32+ caracteres aleatorios - NUNCA compartir>
TABLE_TOKEN_SECRET=<32+ caracteres aleatorios - NUNCA compartir>

# ═══════════════════════════════════════════════════════════════════════════
# CORS (OBLIGATORIO - Lista de orígenes permitidos separados por coma)
# ═══════════════════════════════════════════════════════════════════════════
ALLOWED_ORIGINS=https://menu.turestaurante.com,https://admin.turestaurante.com,https://waiter.turestaurante.com

# ═══════════════════════════════════════════════════════════════════════════
# BASE DE DATOS
# ═══════════════════════════════════════════════════════════════════════════
DATABASE_URL=postgresql://usuario:contraseña@host:5432/integrador
DATABASE_POOL_SIZE=20
DATABASE_MAX_OVERFLOW=10

# ═══════════════════════════════════════════════════════════════════════════
# REDIS
# ═══════════════════════════════════════════════════════════════════════════
REDIS_URL=redis://host:6379/0
REDIS_POOL_MAX_CONNECTIONS=50
REDIS_SYNC_POOL_MAX_CONNECTIONS=20

# ═══════════════════════════════════════════════════════════════════════════
# MERCADO PAGO (Opcional - Solo si se usa para pagos)
# ═══════════════════════════════════════════════════════════════════════════
MERCADOPAGO_ACCESS_TOKEN=<token de acceso de MP>
MERCADOPAGO_WEBHOOK_SECRET=<secreto para validar webhooks>

# ═══════════════════════════════════════════════════════════════════════════
# CONFIGURACIÓN DE APLICACIÓN
# ═══════════════════════════════════════════════════════════════════════════
ENVIRONMENT=production
DEBUG=false
LOG_LEVEL=INFO

# ═══════════════════════════════════════════════════════════════════════════
# WEBSOCKET GATEWAY
# ═══════════════════════════════════════════════════════════════════════════
WS_MAX_CONNECTIONS_PER_USER=3
WS_MAX_TOTAL_CONNECTIONS=1000
WS_MESSAGE_RATE_LIMIT=20
WS_BROADCAST_BATCH_SIZE=50
```

### 8.4 Health Checks y Monitoreo

```python
# rest_api/routers/public/health.py

@router.get("/health")
def health_check():
    """
    Health check básico (síncrono, rápido).

    Usado por load balancers y orquestadores de contenedores.
    """
    return {"status": "healthy", "timestamp": datetime.utcnow().isoformat()}


@router.get("/health/detailed")
async def detailed_health_check():
    """
    Health check detallado con verificación de dependencias.

    Incluye estado de PostgreSQL, Redis async y Redis sync.
    """
    checks = {}
    overall_healthy = True

    # Check PostgreSQL
    try:
        with get_db_session() as db:
            db.execute(text("SELECT 1"))
        checks["postgres"] = {"status": "healthy"}
    except Exception as e:
        checks["postgres"] = {"status": "unhealthy", "error": str(e)}
        overall_healthy = False

    # Check Redis Async
    try:
        redis = await get_redis_pool()
        await redis.ping()
        pool_info = redis.connection_pool
        checks["redis_async"] = {
            "status": "healthy",
            "pool_size": pool_info.max_connections,
            "in_use": pool_info._in_use_connections,
        }
    except Exception as e:
        checks["redis_async"] = {"status": "unhealthy", "error": str(e)}
        overall_healthy = False

    # Check Redis Sync
    try:
        client = get_redis_sync_client()
        client.ping()
        checks["redis_sync"] = {"status": "healthy"}
    except Exception as e:
        checks["redis_sync"] = {"status": "unhealthy", "error": str(e)}
        overall_healthy = False

    return {
        "status": "healthy" if overall_healthy else "degraded",
        "timestamp": datetime.utcnow().isoformat(),
        "checks": checks,
    }
```

```python
# ws_gateway/main.py

@app.get("/ws/health")
def ws_health():
    """Health check del gateway."""
    return {
        "status": "healthy",
        "connections": manager.get_connection_count(),
    }


@app.get("/ws/metrics")
def ws_metrics():
    """
    Endpoint de métricas en formato Prometheus.

    Incluye contadores de conexiones, broadcasts, errores, etc.
    """
    metrics = manager.get_metrics()

    return Response(
        content=format_prometheus(metrics),
        media_type="text/plain",
    )
```

---

## Capítulo IX: Testing y Calidad

### 9.1 Estrategia de Testing

El sistema implementa una pirámide de testing con énfasis en tests de integración:

| Nivel | Framework | Cobertura | Propósito |
|-------|-----------|-----------|-----------|
| Unit Tests | pytest / Vitest | Servicios, utilidades | Lógica de negocio aislada |
| Integration Tests | pytest / Vitest | Routers, stores | Flujos completos |
| E2E Tests | Playwright | Flujos críticos | Validación de usuario |

### 9.2 Ejecución de Tests

```bash
# ═══════════════════════════════════════════════════════════════════════════
# FRONTEND TESTS
# ═══════════════════════════════════════════════════════════════════════════

# Dashboard (100 tests)
cd Dashboard
npm run test              # Ejecución interactiva
npm run test -- --run     # Ejecución CI

# pwaMenu (108 tests)
cd pwaMenu
npm run test
npm run test -- --coverage  # Con cobertura

# Test individual
npm test -- src/stores/tableStore.test.ts

# Type checking
npx tsc --noEmit

# ═══════════════════════════════════════════════════════════════════════════
# BACKEND TESTS
# ═══════════════════════════════════════════════════════════════════════════

cd backend

# Todos los tests
python -m pytest tests/ -v

# Test individual
python -m pytest tests/test_auth.py -v

# Con cobertura
python -m pytest tests/ --cov=rest_api --cov-report=html

# Solo tests rápidos (sin I/O)
python -m pytest tests/ -m "not slow"
```

### 9.3 Fixtures de Testing

```python
# backend/tests/conftest.py

@pytest.fixture
def db_session():
    """
    Proporciona sesión de base de datos aislada por test.

    Cada test corre en su propia transacción que se revierte al final.
    """
    engine = create_engine(settings.test_database_url)
    connection = engine.connect()
    transaction = connection.begin()
    session = Session(bind=connection)

    yield session

    session.close()
    transaction.rollback()
    connection.close()


@pytest.fixture
def test_tenant(db_session):
    """Crea tenant de prueba."""
    tenant = Tenant(name="Test Restaurant")
    db_session.add(tenant)
    db_session.flush()
    return tenant


@pytest.fixture
def test_admin(db_session, test_tenant):
    """Crea usuario admin de prueba."""
    user = User(
        email="admin@test.com",
        password_hash=hash_password("admin123"),
        tenant_id=test_tenant.id,
    )
    db_session.add(user)
    db_session.flush()

    # Crear rol
    role = UserBranchRole(
        user_id=user.id,
        branch_id=None,
        role="ADMIN",
    )
    db_session.add(role)
    db_session.flush()

    return user


@pytest.fixture
def auth_headers(test_admin):
    """Headers de autenticación para peticiones."""
    token = create_access_token(test_admin, [])
    return {"Authorization": f"Bearer {token}"}
```

---

## Capítulo X: Documentación y Referencias

### 10.1 Estructura de Documentación

Cada componente mantiene su propia documentación especializada:

| Archivo | Contenido |
|---------|-----------|
| [Dashboard/README.md](Dashboard/README.md) | Guía de desarrollo del Dashboard, patrones React 19, Zustand |
| [Dashboard/arquiDashboard.md](Dashboard/arquiDashboard.md) | Arquitectura profunda: stores, API client, WebSocket |
| [pwaMenu/README.md](pwaMenu/README.md) | Sistema colaborativo, filtros, PWA, fidelización |
| [pwaMenu/CLAUDE.md](pwaMenu/CLAUDE.md) | Guía específica para desarrollo en pwaMenu |
| [pwaWaiter/CLAUDE.md](pwaWaiter/CLAUDE.md) | Guía específica para desarrollo en pwaWaiter |
| [backend/README.md](backend/README.md) | API REST, comandos, patrones de backend |
| [backend/arquiBackend.md](backend/arquiBackend.md) | Clean Architecture, capas, flujos de datos |
| [backend/shared/README.md](backend/shared/README.md) | Módulos compartidos entre API y WS Gateway |
| [ws_gateway/README.md](ws_gateway/README.md) | Gateway WebSocket, eventos, resiliencia |
| [ws_gateway/arquiws_gateway.md](ws_gateway/arquiws_gateway.md) | Componentes, patrones, broadcast paralelo |
| [devOps/README.md](devOps/README.md) | Docker, scripts, configuración de infraestructura |

### 10.2 Usuarios de Prueba

El seed de desarrollo crea los siguientes usuarios:

| Email | Contraseña | Rol | Descripción |
|-------|------------|-----|-------------|
| admin@demo.com | admin123 | ADMIN | Acceso total al tenant |
| manager@demo.com | manager123 | MANAGER | Gestión de sucursales asignadas |
| kitchen@demo.com | kitchen123 | KITCHEN | Operaciones de cocina |
| waiter@demo.com | waiter123 | WAITER | Servicio de mesas |
| ana@demo.com | ana123 | WAITER | Mesera adicional |
| alberto.cortez@demo.com | waiter123 | WAITER | Mesero adicional |

### 10.3 Convenciones del Proyecto

| Aspecto | Convención |
|---------|------------|
| Idioma UI | Español |
| Idioma código | Inglés (comentarios, variables) |
| IDs frontend | `crypto.randomUUID()` |
| IDs backend | BigInteger autoincremental |
| Precios | Centavos (12550 = $125.50) |
| Logging | Logger centralizado, nunca console.* directo |
| Naming frontend | camelCase |
| Naming backend | snake_case |
| Tema visual | VS Code Light con acento azul (#0078d4) |

---

## Epílogo: Estado del Proyecto

Integrador representa el resultado de múltiples iteraciones de desarrollo y 22 auditorías de calidad que identificaron y corrigieron **977+ defectos** a lo largo del ciclo de vida del proyecto. El sistema actualmente opera en producción, soportando operaciones multi-sucursal en tiempo real con aislamiento completo de datos por tenant.

La arquitectura ha sido diseñada para escalar horizontalmente, con el WebSocket Gateway probado para mantener 400-600 conexiones simultáneas con latencias de broadcast inferiores a 200ms. Los patrones implementados (Clean Architecture, Strategy Pattern, Repository Pattern, Circuit Breaker) proporcionan una base sólida para evolución futura sin acumulación de deuda técnica.

El código fuente está organizado como monorepo, facilitando la coordinación de cambios que afectan múltiples componentes mientras mantiene la independencia de despliegue de cada servicio.

---

*Documentación técnica de Integrador — Versión 2026.01*

*Última actualización: Enero 2026*
