# Sistema de Gestión de Stock e Inventario

## Documento de Arquitectura y Diseño

**Versión:** 1.0
**Fecha:** Febrero 2026
**Autor:** Equipo de Desarrollo Integrador

---

## Tabla de Contenidos

1. [Introducción](#introducción)
2. [Visión General del Sistema](#visión-general-del-sistema)
3. [Arquitectura de Datos](#arquitectura-de-datos)
4. [Modelo de Proveedores](#modelo-de-proveedores)
5. [Gestión de Movimientos](#gestión-de-movimientos)
6. [Integración con el Menú Digital](#integración-con-el-menú-digital)
7. [Integración con Recetas](#integración-con-recetas)
8. [Eventos en Tiempo Real](#eventos-en-tiempo-real)
9. [Interfaz de Usuario](#interfaz-de-usuario)
10. [Ventajas y Desventajas](#ventajas-y-desventajas)
11. [Fases de Implementación](#fases-de-implementación)
12. [Consideraciones Técnicas](#consideraciones-técnicas)
13. [Conclusión](#conclusión)

---

## Introducción

El sistema de gestión de restaurantes que hemos desarrollado hasta ahora permite a los comensales realizar pedidos desde sus dispositivos móviles, a los meseros gestionar las mesas de sus sectores asignados, y a la cocina recibir las comandas en tiempo real. Sin embargo, existe una pieza fundamental que aún no hemos abordado: el control de inventario.

En la industria gastronómica, el control de stock no es simplemente una cuestión de saber cuántas unidades de un producto quedan disponibles. Se trata de un ecosistema complejo que involucra la relación con proveedores, la trazabilidad de insumos, el cálculo de costos por porción, la prevención de mermas, y la capacidad de tomar decisiones basadas en datos históricos. Un restaurante que no controla su inventario está, en esencia, navegando a ciegas.

Este documento describe la arquitectura e implementación de un sistema de stock completo que se integra de manera orgánica con los módulos existentes: el menú digital (pwaMenu), las recetas de cocina, el dashboard administrativo, y el sistema de pedidos. La filosofía de diseño prioriza la trazabilidad, la automatización, y la experiencia de usuario tanto para el personal del restaurante como para los comensales.

---

## Visión General del Sistema

### El Problema que Resolvemos

Imaginemos un escenario típico en un restaurante sin control de stock: un cliente ordena una milanesa napolitana desde su teléfono. El pedido llega a la cocina, pero resulta que no hay mozzarella suficiente para prepararla. El mesero debe acercarse a la mesa a informar que el plato no está disponible. El cliente, frustrado, debe elegir otra opción. Esta situación daña la experiencia del cliente y genera ineficiencias operativas.

Con un sistema de stock integrado, este escenario se previene completamente. Cuando el stock de mozzarella cae por debajo del umbral necesario para preparar una porción de milanesa napolitana, el sistema automáticamente marca el producto como "agotado" en el menú digital. El cliente ni siquiera ve la opción de pedirlo, evitando la frustración y optimizando el flujo de trabajo de la cocina.

### Principios de Diseño

El sistema de stock se construye sobre tres principios fundamentales:

**Trazabilidad Completa.** Cada movimiento de inventario queda registrado con información detallada: quién realizó el movimiento, cuándo, por qué motivo, y qué documentación lo respalda. Esto permite auditorías, análisis de pérdidas, y cumplimiento de normativas fiscales.

**Automatización Inteligente.** El sistema no requiere intervención manual para las operaciones rutinarias. Cuando se confirma un pedido como servido, el stock se decrementa automáticamente. Cuando el stock alcanza el punto de reorden, se genera una alerta o incluso una orden de compra sugerida.

**Integración Bidireccional.** El inventario no es un módulo aislado, sino que fluye información hacia y desde todos los componentes del sistema. Las recetas definen cuánto stock consume cada producto. El menú digital refleja la disponibilidad en tiempo real. Los reportes financieros incluyen el costo de insumos por plato vendido.

---

## Arquitectura de Datos

### Modelo Conceptual

El sistema de inventario se estructura en capas que separan las preocupaciones y permiten evolución independiente:

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                           CAPA DE PRESENTACIÓN                               │
│                                                                              │
│   Dashboard Admin          pwaMenu              pwaWaiter                    │
│   ┌─────────────┐         ┌─────────┐          ┌─────────┐                  │
│   │ Gestión     │         │ Badge   │          │ Alertas │                  │
│   │ Inventario  │         │ Agotado │          │ Stock   │                  │
│   │ Proveedores │         │         │          │ Bajo    │                  │
│   │ Reportes    │         │         │          │         │                  │
│   └─────────────┘         └─────────┘          └─────────┘                  │
└─────────────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                            CAPA DE SERVICIOS                                 │
│                                                                              │
│   InventoryService    SupplierService    RecipeStockService                 │
│   ┌──────────────┐   ┌───────────────┐   ┌─────────────────┐               │
│   │ Movimientos  │   │ Órdenes de    │   │ Cálculo de      │               │
│   │ Alertas      │   │ Compra        │   │ disponibilidad  │               │
│   │ Ajustes      │   │ Recepción     │   │ por receta      │               │
│   └──────────────┘   └───────────────┘   └─────────────────┘               │
└─────────────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                           CAPA DE DOMINIO                                    │
│                                                                              │
│   Inventory         InventoryMovement      Supplier        PurchaseOrder    │
│   ┌───────────┐    ┌─────────────────┐    ┌──────────┐   ┌──────────────┐  │
│   │ Cantidad  │    │ Tipo            │    │ CUIT     │   │ Estado       │  │
│   │ Umbral    │    │ Cantidad        │    │ Contacto │   │ Items        │  │
│   │ Ubicación │    │ Costo           │    │ Lead Time│   │ Fecha        │  │
│   └───────────┘    │ Referencia      │    └──────────┘   └──────────────┘  │
│                    └─────────────────┘                                      │
└─────────────────────────────────────────────────────────────────────────────┘
```

### Entidades Principales

#### Inventory (Inventario)

La entidad `Inventory` representa el estado actual del stock de un insumo en una sucursal específica. Es importante distinguir entre "producto" (lo que vende el restaurante al cliente) e "insumo" (la materia prima que se utiliza para preparar los productos). Un producto como "Hamburguesa Completa" consume múltiples insumos: pan, carne, lechuga, tomate, queso, etc.

```python
class Inventory(AuditMixin, Base):
    """
    Representa el stock actual de un insumo en una sucursal.

    La relación con BranchProduct es opcional porque no todos los insumos
    son productos vendibles. Por ejemplo, el aceite para freír es un insumo
    pero no aparece en el menú como producto individual.
    """
    __tablename__ = "inventory"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    tenant_id: Mapped[int] = mapped_column(ForeignKey("tenant.id"), index=True)
    branch_id: Mapped[int] = mapped_column(ForeignKey("branch.id"), index=True)

    # Identificación del insumo
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    sku: Mapped[Optional[str]] = mapped_column(String(50), unique=True)
    barcode: Mapped[Optional[str]] = mapped_column(String(50))

    # Unidad de medida base (kg, litros, unidades, etc.)
    unit: Mapped[str] = mapped_column(String(20), nullable=False)

    # Estado del stock
    quantity: Mapped[Decimal] = mapped_column(Numeric(12, 3), default=0)
    reserved_quantity: Mapped[Decimal] = mapped_column(Numeric(12, 3), default=0)

    # Umbrales para alertas
    min_stock: Mapped[Decimal] = mapped_column(Numeric(12, 3), default=0)
    reorder_point: Mapped[Decimal] = mapped_column(Numeric(12, 3), default=0)
    max_stock: Mapped[Optional[Decimal]] = mapped_column(Numeric(12, 3))

    # Información de almacenamiento
    storage_location: Mapped[Optional[str]] = mapped_column(String(100))
    requires_refrigeration: Mapped[bool] = mapped_column(Boolean, default=False)

    # Vínculo opcional con producto vendible
    branch_product_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("branch_product.id")
    )

    # Proveedor preferido para reorden automático
    preferred_supplier_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("supplier.id")
    )

    # Costo promedio ponderado (actualizado con cada compra)
    average_cost_cents: Mapped[int] = mapped_column(Integer, default=0)
    last_cost_cents: Mapped[int] = mapped_column(Integer, default=0)

    # Fechas relevantes
    last_restock_at: Mapped[Optional[datetime]] = mapped_column(DateTime)
    last_count_at: Mapped[Optional[datetime]] = mapped_column(DateTime)
```

La decisión de usar `Decimal` para las cantidades en lugar de `Integer` es deliberada. En un restaurante, muchos insumos se miden en fracciones: 0.5 kg de carne, 0.25 litros de aceite, etc. Usar enteros forzaría a trabajar con unidades artificialmente pequeñas (gramos en lugar de kilogramos), lo cual complica la interfaz de usuario y los cálculos.

El campo `reserved_quantity` merece una explicación especial. Cuando un cliente realiza un pedido, el stock no se decrementa inmediatamente. Primero se "reserva" la cantidad necesaria, evitando que otro cliente pueda pedir lo mismo si no hay suficiente. Solo cuando el pedido se marca como "SERVED" (servido), la reserva se convierte en consumo real. Si el pedido se cancela, la reserva se libera.

#### InventoryMovement (Movimiento de Inventario)

Cada cambio en el inventario genera un registro de movimiento. Esta es la base de la trazabilidad completa del sistema:

```python
class InventoryMovement(AuditMixin, Base):
    """
    Registro inmutable de cada movimiento de inventario.

    Los movimientos nunca se eliminan ni modifican. Si hay un error,
    se crea un movimiento de ajuste que lo compensa.
    """
    __tablename__ = "inventory_movement"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    inventory_id: Mapped[int] = mapped_column(ForeignKey("inventory.id"), index=True)

    # Tipo de movimiento
    movement_type: Mapped[str] = mapped_column(
        String(20),
        nullable=False
        # Valores: PURCHASE, SALE, ADJUSTMENT, WASTE, TRANSFER_IN,
        #          TRANSFER_OUT, RETURN, PRODUCTION, INITIAL
    )

    # Cantidad (positiva para entradas, negativa para salidas)
    quantity_change: Mapped[Decimal] = mapped_column(Numeric(12, 3), nullable=False)
    quantity_before: Mapped[Decimal] = mapped_column(Numeric(12, 3), nullable=False)
    quantity_after: Mapped[Decimal] = mapped_column(Numeric(12, 3), nullable=False)

    # Costo unitario en este movimiento (centavos)
    unit_cost_cents: Mapped[Optional[int]] = mapped_column(Integer)
    total_cost_cents: Mapped[Optional[int]] = mapped_column(Integer)

    # Referencias opcionales según el tipo de movimiento
    purchase_order_id: Mapped[Optional[int]] = mapped_column(ForeignKey("purchase_order.id"))
    round_id: Mapped[Optional[int]] = mapped_column(ForeignKey("round.id"))
    round_item_id: Mapped[Optional[int]] = mapped_column(ForeignKey("round_item.id"))
    transfer_id: Mapped[Optional[int]] = mapped_column(ForeignKey("inventory_transfer.id"))

    # Documentación
    reason: Mapped[Optional[str]] = mapped_column(Text)
    reference_document: Mapped[Optional[str]] = mapped_column(String(100))

    # Para ajustes de inventario físico
    physical_count: Mapped[Optional[Decimal]] = mapped_column(Numeric(12, 3))
    variance: Mapped[Optional[Decimal]] = mapped_column(Numeric(12, 3))
```

Los tipos de movimiento cubren todos los escenarios posibles en la operación de un restaurante:

- **PURCHASE**: Ingreso por compra a proveedor
- **SALE**: Egreso por venta/consumo en pedido
- **ADJUSTMENT**: Corrección por conteo físico
- **WASTE**: Merma por producto dañado, vencido, o desperdicio
- **TRANSFER_IN/OUT**: Movimiento entre sucursales
- **RETURN**: Devolución a proveedor
- **PRODUCTION**: Transformación (ej: pan crudo → pan horneado)
- **INITIAL**: Carga inicial de inventario

---

## Modelo de Proveedores

### La Cadena de Suministro

Un restaurante no existe en aislamiento; depende de una red de proveedores que suministran los insumos necesarios para operar. El sistema de proveedores no solo almacena información de contacto, sino que modela la relación comercial completa: condiciones de pago, tiempos de entrega, histórico de precios, y evaluación de desempeño.

```python
class Supplier(AuditMixin, Base):
    """
    Proveedor de insumos para el restaurante.

    Un proveedor puede suministrar múltiples insumos, y un insumo
    puede tener múltiples proveedores (para comparar precios o
    como respaldo si el principal no puede entregar).
    """
    __tablename__ = "supplier"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    tenant_id: Mapped[int] = mapped_column(ForeignKey("tenant.id"), index=True)

    # Información básica
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    legal_name: Mapped[Optional[str]] = mapped_column(String(200))
    cuit: Mapped[Optional[str]] = mapped_column(String(13))  # XX-XXXXXXXX-X

    # Categoría de proveedor
    category: Mapped[str] = mapped_column(
        String(50),
        default="GENERAL"
        # Valores: MEAT, DAIRY, PRODUCE, BEVERAGES, DRY_GOODS,
        #          CLEANING, PACKAGING, EQUIPMENT, GENERAL
    )

    # Contacto principal
    contact_name: Mapped[Optional[str]] = mapped_column(String(100))
    contact_phone: Mapped[Optional[str]] = mapped_column(String(20))
    contact_email: Mapped[Optional[str]] = mapped_column(String(100))
    contact_whatsapp: Mapped[Optional[str]] = mapped_column(String(20))

    # Dirección
    address: Mapped[Optional[str]] = mapped_column(Text)
    city: Mapped[Optional[str]] = mapped_column(String(100))
    province: Mapped[Optional[str]] = mapped_column(String(100))

    # Condiciones comerciales
    payment_terms: Mapped[str] = mapped_column(
        String(20),
        default="CASH"
        # Valores: CASH, NET_15, NET_30, NET_60, COD (contra entrega)
    )
    credit_limit_cents: Mapped[Optional[int]] = mapped_column(Integer)
    current_balance_cents: Mapped[int] = mapped_column(Integer, default=0)

    # Logística
    lead_time_days: Mapped[int] = mapped_column(Integer, default=1)
    minimum_order_cents: Mapped[Optional[int]] = mapped_column(Integer)
    delivery_fee_cents: Mapped[int] = mapped_column(Integer, default=0)
    delivers_on_weekends: Mapped[bool] = mapped_column(Boolean, default=False)

    # Evaluación
    rating: Mapped[Optional[Decimal]] = mapped_column(Numeric(2, 1))  # 1.0 - 5.0
    total_orders: Mapped[int] = mapped_column(Integer, default=0)
    on_time_delivery_rate: Mapped[Optional[Decimal]] = mapped_column(Numeric(5, 2))

    # Estado
    status: Mapped[str] = mapped_column(
        String(20),
        default="ACTIVE"
        # Valores: ACTIVE, INACTIVE, BLOCKED, PENDING_APPROVAL
    )

    notes: Mapped[Optional[str]] = mapped_column(Text)
```

### Catálogo de Precios por Proveedor

Cada proveedor tiene su propio catálogo de precios para los insumos que ofrece. Esto permite comparar proveedores y elegir la mejor opción para cada compra:

```python
class SupplierProduct(AuditMixin, Base):
    """
    Relación entre proveedor e insumo con información de precio.

    Un mismo insumo puede tener diferentes precios según el proveedor,
    y un proveedor puede ofrecer el mismo insumo en diferentes
    presentaciones (ej: carne en bolsas de 5kg o 10kg).
    """
    __tablename__ = "supplier_product"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    supplier_id: Mapped[int] = mapped_column(ForeignKey("supplier.id"), index=True)
    inventory_id: Mapped[int] = mapped_column(ForeignKey("inventory.id"), index=True)

    # Código del proveedor para este producto
    supplier_sku: Mapped[Optional[str]] = mapped_column(String(50))
    supplier_name: Mapped[Optional[str]] = mapped_column(String(200))

    # Presentación
    package_size: Mapped[Decimal] = mapped_column(Numeric(12, 3), default=1)
    package_unit: Mapped[str] = mapped_column(String(20))  # "kg", "unidad", "caja"
    units_per_package: Mapped[int] = mapped_column(Integer, default=1)

    # Precio (por paquete, no por unidad base)
    price_cents: Mapped[int] = mapped_column(Integer, nullable=False)
    currency: Mapped[str] = mapped_column(String(3), default="ARS")

    # Historial de precios
    last_price_update: Mapped[Optional[datetime]] = mapped_column(DateTime)
    price_valid_until: Mapped[Optional[date]] = mapped_column(Date)

    # Disponibilidad
    is_available: Mapped[bool] = mapped_column(Boolean, default=True)
    is_preferred: Mapped[bool] = mapped_column(Boolean, default=False)

    __table_args__ = (
        UniqueConstraint("supplier_id", "inventory_id", "package_size"),
    )
```

### Órdenes de Compra

El flujo de compras sigue un proceso estructurado que garantiza control y trazabilidad:

```python
class PurchaseOrder(AuditMixin, Base):
    """
    Orden de compra a un proveedor.

    Estados:
    - DRAFT: En elaboración, puede modificarse
    - SENT: Enviada al proveedor, esperando confirmación
    - CONFIRMED: Proveedor confirmó, esperando entrega
    - PARTIAL: Recibido parcialmente
    - RECEIVED: Completamente recibido
    - CANCELLED: Cancelada
    """
    __tablename__ = "purchase_order"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    tenant_id: Mapped[int] = mapped_column(ForeignKey("tenant.id"), index=True)
    branch_id: Mapped[int] = mapped_column(ForeignKey("branch.id"), index=True)
    supplier_id: Mapped[int] = mapped_column(ForeignKey("supplier.id"), index=True)

    # Identificación
    order_number: Mapped[str] = mapped_column(String(20), unique=True)

    # Estado
    status: Mapped[str] = mapped_column(String(20), default="DRAFT")

    # Fechas
    order_date: Mapped[date] = mapped_column(Date, nullable=False)
    expected_delivery_date: Mapped[Optional[date]] = mapped_column(Date)
    actual_delivery_date: Mapped[Optional[date]] = mapped_column(Date)

    # Totales
    subtotal_cents: Mapped[int] = mapped_column(Integer, default=0)
    tax_cents: Mapped[int] = mapped_column(Integer, default=0)
    discount_cents: Mapped[int] = mapped_column(Integer, default=0)
    delivery_fee_cents: Mapped[int] = mapped_column(Integer, default=0)
    total_cents: Mapped[int] = mapped_column(Integer, default=0)

    # Condiciones
    payment_terms: Mapped[str] = mapped_column(String(20))
    payment_due_date: Mapped[Optional[date]] = mapped_column(Date)

    # Documentación
    notes: Mapped[Optional[str]] = mapped_column(Text)
    internal_notes: Mapped[Optional[str]] = mapped_column(Text)

    # Referencias a documentos externos
    supplier_invoice_number: Mapped[Optional[str]] = mapped_column(String(50))
    delivery_note_number: Mapped[Optional[str]] = mapped_column(String(50))


class PurchaseOrderItem(AuditMixin, Base):
    """
    Línea de una orden de compra.
    """
    __tablename__ = "purchase_order_item"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    purchase_order_id: Mapped[int] = mapped_column(
        ForeignKey("purchase_order.id"), index=True
    )
    inventory_id: Mapped[int] = mapped_column(ForeignKey("inventory.id"))
    supplier_product_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("supplier_product.id")
    )

    # Cantidades
    quantity_ordered: Mapped[Decimal] = mapped_column(Numeric(12, 3), nullable=False)
    quantity_received: Mapped[Decimal] = mapped_column(Numeric(12, 3), default=0)
    unit: Mapped[str] = mapped_column(String(20))

    # Precios
    unit_price_cents: Mapped[int] = mapped_column(Integer, nullable=False)
    discount_percent: Mapped[Decimal] = mapped_column(Numeric(5, 2), default=0)
    tax_percent: Mapped[Decimal] = mapped_column(Numeric(5, 2), default=21)  # IVA
    line_total_cents: Mapped[int] = mapped_column(Integer, nullable=False)

    # Estado de recepción
    is_fully_received: Mapped[bool] = mapped_column(Boolean, default=False)
    notes: Mapped[Optional[str]] = mapped_column(Text)
```

---

## Gestión de Movimientos

### Flujo de Venta (Consumo por Pedido)

Cuando un cliente realiza un pedido desde el menú digital, se desencadena una secuencia de eventos que afecta el inventario de manera controlada:

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                        FLUJO DE CONSUMO POR PEDIDO                          │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│  1. PEDIDO CREADO (PENDING)                                                │
│     │                                                                       │
│     ▼                                                                       │
│  ┌─────────────────────────────────────────────────────────────────────┐   │
│  │ RecipeStockService.check_availability(product_id, quantity)         │   │
│  │                                                                      │   │
│  │ Para cada ingrediente en la receta:                                 │   │
│  │   - Calcula cantidad necesaria = receta.cantidad × pedido.cantidad  │   │
│  │   - Verifica: inventory.quantity - inventory.reserved >= necesaria  │   │
│  │                                                                      │   │
│  │ Si algún ingrediente insuficiente → Rechazar pedido                 │   │
│  └─────────────────────────────────────────────────────────────────────┘   │
│     │                                                                       │
│     ▼                                                                       │
│  2. PEDIDO CONFIRMADO (CONFIRMED)                                          │
│     │                                                                       │
│     ▼                                                                       │
│  ┌─────────────────────────────────────────────────────────────────────┐   │
│  │ InventoryService.reserve_stock(round_id, items)                     │   │
│  │                                                                      │   │
│  │ Para cada ingrediente:                                              │   │
│  │   inventory.reserved_quantity += cantidad_necesaria                 │   │
│  │                                                                      │   │
│  │ No crea movimiento aún (es solo una reserva)                        │   │
│  └─────────────────────────────────────────────────────────────────────┘   │
│     │                                                                       │
│     ▼                                                                       │
│  3. PEDIDO EN COCINA (IN_KITCHEN)                                          │
│     │                                                                       │
│     │  (No hay cambios en inventario, solo estado)                         │
│     │                                                                       │
│     ▼                                                                       │
│  4. PEDIDO LISTO (READY)                                                   │
│     │                                                                       │
│     │  (No hay cambios en inventario)                                      │
│     │                                                                       │
│     ▼                                                                       │
│  5. PEDIDO SERVIDO (SERVED)                                                │
│     │                                                                       │
│     ▼                                                                       │
│  ┌─────────────────────────────────────────────────────────────────────┐   │
│  │ InventoryService.confirm_consumption(round_id)                      │   │
│  │                                                                      │   │
│  │ Para cada ingrediente reservado:                                    │   │
│  │   1. inventory.reserved_quantity -= cantidad                        │   │
│  │   2. inventory.quantity -= cantidad                                 │   │
│  │   3. Crear InventoryMovement(type='SALE', round_id=...)            │   │
│  │   4. Si inventory.quantity <= reorder_point → Alertar              │   │
│  │   5. Si inventory.quantity <= min_stock → Marcar agotado           │   │
│  └─────────────────────────────────────────────────────────────────────┘   │
│     │                                                                       │
│     ▼                                                                       │
│  6. EVENTOS PUBLICADOS                                                     │
│                                                                             │
│     Si stock cayó a 0:                                                     │
│       → STOCK_DEPLETED → pwaMenu muestra "AGOTADO"                        │
│                                                                             │
│     Si stock bajo mínimo:                                                  │
│       → STOCK_LOW → Dashboard muestra alerta                              │
│                                                                             │
│     Si alcanzó punto de reorden:                                           │
│       → STOCK_REORDER → Sugerir orden de compra                           │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

### Flujo de Compra (Reposición)

El proceso de reposición de stock sigue un flujo estructurado que garantiza control y trazabilidad:

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                         FLUJO DE REPOSICIÓN                                  │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│  1. DETECCIÓN DE NECESIDAD                                                 │
│     │                                                                       │
│     ├── Manual: Manager crea orden desde Dashboard                         │
│     │                                                                       │
│     └── Automática: Sistema detecta stock <= reorder_point                 │
│         │                                                                   │
│         ▼                                                                   │
│     ┌─────────────────────────────────────────────────────────────┐        │
│     │ PurchaseOrderService.suggest_order(inventory_id)            │        │
│     │                                                              │        │
│     │ - Calcula cantidad sugerida basada en:                      │        │
│     │   · Promedio de consumo últimos 30 días                     │        │
│     │   · Lead time del proveedor                                 │        │
│     │   · Stock de seguridad deseado                              │        │
│     │                                                              │        │
│     │ - Selecciona proveedor preferido o el de mejor precio       │        │
│     │ - Crea PurchaseOrder en estado DRAFT                        │        │
│     └─────────────────────────────────────────────────────────────┘        │
│     │                                                                       │
│     ▼                                                                       │
│  2. ORDEN EN BORRADOR (DRAFT)                                              │
│     │                                                                       │
│     │  Manager revisa, ajusta cantidades, aprueba                          │
│     │                                                                       │
│     ▼                                                                       │
│  3. ORDEN ENVIADA (SENT)                                                   │
│     │                                                                       │
│     │  Sistema puede enviar email/WhatsApp al proveedor                    │
│     │                                                                       │
│     ▼                                                                       │
│  4. ORDEN CONFIRMADA (CONFIRMED)                                           │
│     │                                                                       │
│     │  Proveedor confirma disponibilidad y fecha de entrega               │
│     │                                                                       │
│     ▼                                                                       │
│  5. RECEPCIÓN DE MERCADERÍA                                                │
│     │                                                                       │
│     ▼                                                                       │
│  ┌─────────────────────────────────────────────────────────────────────┐   │
│  │ PurchaseOrderService.receive_items(order_id, received_items)        │   │
│  │                                                                      │   │
│  │ Para cada item recibido:                                            │   │
│  │   1. Validar cantidad vs ordenada                                   │   │
│  │   2. inventory.quantity += cantidad_recibida                        │   │
│  │   3. Actualizar average_cost_cents (promedio ponderado)            │   │
│  │   4. Crear InventoryMovement(type='PURCHASE', po_id=...)           │   │
│  │   5. purchase_order_item.quantity_received += cantidad             │   │
│  │                                                                      │   │
│  │ Si todo recibido → order.status = 'RECEIVED'                       │   │
│  │ Si parcial → order.status = 'PARTIAL'                              │   │
│  └─────────────────────────────────────────────────────────────────────┘   │
│     │                                                                       │
│     ▼                                                                       │
│  6. EVENTOS PUBLICADOS                                                     │
│                                                                             │
│     → STOCK_RESTOCKED → pwaMenu quita badge "AGOTADO" si corresponde      │
│     → STOCK_UPDATED → Dashboard actualiza vista                           │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## Integración con el Menú Digital

### El Desafío de la Disponibilidad en Tiempo Real

El menú digital (pwaMenu) debe reflejar la disponibilidad real de productos en todo momento. Cuando un insumo se agota, todos los productos que lo utilizan deben marcarse como no disponibles, y esto debe propagarse instantáneamente a todos los dispositivos que estén viendo el menú.

Esta integración se implementa en múltiples capas:

#### Capa de Datos: Cálculo de Disponibilidad

```python
# backend/rest_api/services/domain/recipe_stock_service.py

class RecipeStockService:
    """
    Servicio que vincula recetas con inventario para calcular disponibilidad.
    """

    def __init__(self, db: Session):
        self.db = db

    def get_product_availability(
        self,
        branch_id: int,
        product_id: int
    ) -> ProductAvailability:
        """
        Calcula si un producto está disponible basándose en el stock
        de todos sus ingredientes.

        Returns:
            ProductAvailability con:
            - is_available: bool
            - max_portions: int (cuántas porciones se pueden preparar)
            - limiting_ingredient: str | None (qué ingrediente limita)
        """
        # Obtener receta del producto
        recipe = self.db.scalar(
            select(Recipe)
            .where(Recipe.product_id == product_id)
            .where(Recipe.is_active == True)
        )

        if not recipe or not recipe.ingredients:
            # Sin receta, asumir disponible si branch_product.is_available
            branch_product = self._get_branch_product(branch_id, product_id)
            return ProductAvailability(
                is_available=branch_product.is_available if branch_product else False,
                max_portions=None,
                limiting_ingredient=None
            )

        # Parsear ingredientes de la receta
        ingredients = json.loads(recipe.ingredients)

        min_portions = float('inf')
        limiting = None

        for ingredient in ingredients:
            inventory = self._find_inventory_by_name(
                branch_id,
                ingredient['name']
            )

            if not inventory:
                # Ingrediente no existe en inventario
                return ProductAvailability(
                    is_available=False,
                    max_portions=0,
                    limiting_ingredient=ingredient['name']
                )

            # Calcular cuántas porciones permite este ingrediente
            available = inventory.quantity - inventory.reserved_quantity
            needed_per_portion = Decimal(ingredient['quantity'])

            if needed_per_portion > 0:
                possible_portions = int(available / needed_per_portion)

                if possible_portions < min_portions:
                    min_portions = possible_portions
                    limiting = ingredient['name']

        return ProductAvailability(
            is_available=min_portions > 0,
            max_portions=min_portions if min_portions != float('inf') else None,
            limiting_ingredient=limiting if min_portions == 0 else None
        )

    def get_menu_availability(
        self,
        branch_id: int
    ) -> dict[int, ProductAvailability]:
        """
        Calcula disponibilidad de todos los productos del menú.
        Optimizado para evitar N+1 queries.
        """
        # Obtener todos los productos activos de la sucursal
        products = self.db.execute(
            select(BranchProduct.product_id)
            .where(BranchProduct.branch_id == branch_id)
            .where(BranchProduct.is_active == True)
            .where(BranchProduct.is_available == True)
        ).scalars().all()

        # Precargar todos los inventarios e ingredientes
        self._preload_inventory(branch_id)
        self._preload_recipes([p for p in products])

        # Calcular disponibilidad de cada producto
        result = {}
        for product_id in products:
            result[product_id] = self.get_product_availability(
                branch_id,
                product_id
            )

        return result
```

#### Capa de API: Endpoint del Menú con Stock

El endpoint público del menú incluye información de disponibilidad:

```python
# backend/rest_api/routers/public/catalog.py

@router.get("/menu/{slug}")
def get_public_menu(
    slug: str,
    db: Session = Depends(get_db),
) -> MenuResponse:
    """
    Retorna el menú público de una sucursal.
    Incluye información de disponibilidad basada en stock.
    """
    branch = get_branch_by_slug(db, slug)

    # Obtener disponibilidad de todos los productos
    stock_service = RecipeStockService(db)
    availability = stock_service.get_menu_availability(branch.id)

    # Construir respuesta con categorías y productos
    categories = get_categories_with_products(db, branch.id)

    for category in categories:
        for product in category.products:
            product_availability = availability.get(product.id)

            # Agregar información de stock al producto
            product.is_available = (
                product_availability.is_available
                if product_availability
                else True
            )
            product.stock_status = (
                "OUT_OF_STOCK" if not product.is_available
                else "LOW_STOCK" if (
                    product_availability and
                    product_availability.max_portions and
                    product_availability.max_portions < 5
                )
                else "IN_STOCK"
            )

    return MenuResponse(
        branch=branch,
        categories=categories,
        last_updated=datetime.utcnow()
    )
```

#### Capa de Frontend: Visualización en pwaMenu

```typescript
// pwaMenu/src/components/ProductCard.tsx

interface ProductCardProps {
  product: Product
  onAddToCart: (product: Product) => void
}

export function ProductCard({ product, onAddToCart }: ProductCardProps) {
  const { t } = useTranslation()

  const isOutOfStock = product.stock_status === 'OUT_OF_STOCK'
  const isLowStock = product.stock_status === 'LOW_STOCK'

  return (
    <div
      className={cn(
        "bg-dark-card rounded-xl overflow-hidden transition-all",
        isOutOfStock && "opacity-60 grayscale"
      )}
    >
      {/* Imagen con badges de estado */}
      <div className="relative aspect-[4/3]">
        <img
          src={product.image}
          alt={product.name}
          className="w-full h-full object-cover"
        />

        {isOutOfStock && (
          <div className="absolute inset-0 flex items-center justify-center bg-black/50">
            <span className="bg-red-500 text-white text-sm font-bold px-3 py-1 rounded-full">
              {t('product.outOfStock')}
            </span>
          </div>
        )}

        {isLowStock && !isOutOfStock && (
          <span className="absolute top-2 right-2 bg-orange-500 text-white text-xs px-2 py-1 rounded-full">
            {t('product.lastUnits')}
          </span>
        )}
      </div>

      {/* Información del producto */}
      <div className="p-4">
        <h3 className="text-white font-semibold">{product.name}</h3>
        <p className="text-dark-muted text-sm line-clamp-2">
          {product.description}
        </p>

        <div className="mt-3 flex items-center justify-between">
          <span className="text-primary text-lg font-bold">
            ${product.price.toFixed(2)}
          </span>

          <button
            onClick={() => onAddToCart(product)}
            disabled={isOutOfStock}
            className={cn(
              "px-4 py-2 rounded-lg font-medium transition-colors",
              isOutOfStock
                ? "bg-dark-elevated text-dark-muted cursor-not-allowed"
                : "bg-primary text-white hover:bg-primary/90"
            )}
          >
            {isOutOfStock ? t('product.unavailable') : t('product.add')}
          </button>
        </div>
      </div>
    </div>
  )
}
```

#### Capa de Tiempo Real: WebSocket para Stock

Cuando el stock cambia, se notifica a todos los clientes:

```python
# backend/shared/infrastructure/events/domain_publishers.py

async def publish_stock_event(
    redis_client: redis.Redis,
    event_type: str,  # STOCK_UPDATED, STOCK_DEPLETED, STOCK_RESTOCKED
    tenant_id: int,
    branch_id: int,
    inventory_id: int,
    product_id: int | None,
    quantity: Decimal,
    stock_status: str,  # IN_STOCK, LOW_STOCK, OUT_OF_STOCK
) -> None:
    """
    Publica eventos de stock para actualización en tiempo real del menú.
    """
    event = Event(
        type=event_type,
        tenant_id=tenant_id,
        branch_id=branch_id,
        entity={
            "inventory_id": inventory_id,
            "product_id": product_id,
            "quantity": str(quantity),
            "stock_status": stock_status,
        },
    )

    # Publicar a canal de la sucursal para que pwaMenu actualice
    await publish_to_branch_menu(redis_client, branch_id, event)

    # Publicar a admin para dashboard
    await publish_to_admin(redis_client, branch_id, event)
```

```typescript
// pwaMenu/src/hooks/useStockUpdates.ts

export function useStockUpdates() {
  const updateProductStock = useMenuStore((state) => state.updateProductStock)

  useEffect(() => {
    // Escuchar eventos de stock
    const unsubscribeDepleted = dinerWS.on('STOCK_DEPLETED', (event) => {
      updateProductStock(event.entity.product_id, 'OUT_OF_STOCK')
    })

    const unsubscribeRestocked = dinerWS.on('STOCK_RESTOCKED', (event) => {
      updateProductStock(event.entity.product_id, event.entity.stock_status)
    })

    const unsubscribeUpdated = dinerWS.on('STOCK_UPDATED', (event) => {
      updateProductStock(event.entity.product_id, event.entity.stock_status)
    })

    return () => {
      unsubscribeDepleted()
      unsubscribeRestocked()
      unsubscribeUpdated()
    }
  }, [updateProductStock])
}
```

---

## Integración con Recetas

### El Puente entre Menú e Inventario

Las recetas son el elemento que conecta los productos del menú con los insumos del inventario. Cada receta define qué ingredientes se necesitan para preparar una porción del producto, en qué cantidades, y cómo deben prepararse.

El modelo de recetas ya existe en el sistema (`Recipe`, `RecipeAllergen`). La integración con inventario agrega una capa de vinculación:

```python
# backend/rest_api/models/recipe.py (modificación)

class RecipeIngredient(AuditMixin, Base):
    """
    Ingrediente de una receta vinculado al inventario.

    Esta tabla reemplaza el campo JSON 'ingredients' de Recipe
    para permitir vinculación directa con el inventario.
    """
    __tablename__ = "recipe_ingredient"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    recipe_id: Mapped[int] = mapped_column(ForeignKey("recipe.id"), index=True)
    inventory_id: Mapped[int] = mapped_column(ForeignKey("inventory.id"), index=True)

    # Cantidad necesaria por porción
    quantity: Mapped[Decimal] = mapped_column(Numeric(12, 3), nullable=False)
    unit: Mapped[str] = mapped_column(String(20), nullable=False)

    # Para ingredientes opcionales o sustitutos
    is_optional: Mapped[bool] = mapped_column(Boolean, default=False)
    substitute_group: Mapped[Optional[str]] = mapped_column(String(50))

    # Notas de preparación
    preparation_notes: Mapped[Optional[str]] = mapped_column(Text)

    # Orden de uso en la receta
    sort_order: Mapped[int] = mapped_column(Integer, default=0)

    # Relaciones
    recipe: Mapped["Recipe"] = relationship(back_populates="recipe_ingredients")
    inventory: Mapped["Inventory"] = relationship()
```

### Cálculo de Costo por Porción

Una de las ventajas más importantes de vincular recetas con inventario es poder calcular el costo real de cada plato:

```python
# backend/rest_api/services/domain/recipe_cost_service.py

class RecipeCostService:
    """
    Calcula costos de recetas basándose en costos de inventario.
    """

    def calculate_portion_cost(
        self,
        recipe_id: int
    ) -> RecipeCostBreakdown:
        """
        Calcula el costo de una porción de la receta.

        Usa el costo promedio ponderado de cada ingrediente
        para mayor precisión.
        """
        recipe = self._get_recipe_with_ingredients(recipe_id)

        ingredients_cost = []
        total_cost_cents = 0

        for ri in recipe.recipe_ingredients:
            inventory = ri.inventory

            # Convertir unidades si es necesario
            quantity_in_base_unit = self._convert_unit(
                ri.quantity,
                ri.unit,
                inventory.unit
            )

            # Calcular costo de este ingrediente
            ingredient_cost_cents = int(
                quantity_in_base_unit * inventory.average_cost_cents
            )

            ingredients_cost.append(IngredientCost(
                name=inventory.name,
                quantity=ri.quantity,
                unit=ri.unit,
                unit_cost_cents=inventory.average_cost_cents,
                total_cost_cents=ingredient_cost_cents
            ))

            total_cost_cents += ingredient_cost_cents

        # Agregar margen por merma estimada (configurable por receta)
        waste_margin = recipe.estimated_waste_percent or Decimal('5')
        waste_cost_cents = int(total_cost_cents * waste_margin / 100)

        return RecipeCostBreakdown(
            recipe_id=recipe_id,
            ingredients=ingredients_cost,
            subtotal_cents=total_cost_cents,
            waste_margin_percent=waste_margin,
            waste_cost_cents=waste_cost_cents,
            total_cost_cents=total_cost_cents + waste_cost_cents,
            last_calculated=datetime.utcnow()
        )

    def calculate_profit_margin(
        self,
        recipe_id: int,
        selling_price_cents: int
    ) -> ProfitMargin:
        """
        Calcula el margen de ganancia de un plato.
        """
        cost = self.calculate_portion_cost(recipe_id)

        profit_cents = selling_price_cents - cost.total_cost_cents
        margin_percent = (profit_cents / selling_price_cents) * 100

        return ProfitMargin(
            recipe_id=recipe_id,
            cost_cents=cost.total_cost_cents,
            price_cents=selling_price_cents,
            profit_cents=profit_cents,
            margin_percent=margin_percent,
            is_healthy=margin_percent >= 65  # Margen saludable en gastronomía
        )
```

### Sincronización Bidireccional

Cuando se actualiza una receta, el sistema recalcula automáticamente la disponibilidad de los productos afectados:

```python
# backend/rest_api/services/events/recipe_events.py

async def on_recipe_updated(recipe_id: int, db: Session):
    """
    Handler para cuando se actualiza una receta.
    Recalcula disponibilidad y costos.
    """
    recipe = db.scalar(select(Recipe).where(Recipe.id == recipe_id))

    if not recipe or not recipe.product_id:
        return

    # Recalcular disponibilidad del producto
    stock_service = RecipeStockService(db)
    availability = stock_service.get_product_availability(
        recipe.branch_id,
        recipe.product_id
    )

    # Si cambió la disponibilidad, publicar evento
    branch_product = db.scalar(
        select(BranchProduct)
        .where(BranchProduct.product_id == recipe.product_id)
        .where(BranchProduct.branch_id == recipe.branch_id)
    )

    if branch_product:
        new_status = (
            "OUT_OF_STOCK" if not availability.is_available
            else "LOW_STOCK" if availability.max_portions < 5
            else "IN_STOCK"
        )

        # Solo publicar si hubo cambio
        if branch_product.stock_status != new_status:
            redis = await get_redis_pool()
            await publish_stock_event(
                redis,
                "STOCK_UPDATED",
                recipe.tenant_id,
                recipe.branch_id,
                None,  # inventory_id no aplica aquí
                recipe.product_id,
                Decimal(availability.max_portions or 0),
                new_status
            )
```

---

## Eventos en Tiempo Real

### Arquitectura de Eventos de Stock

El sistema utiliza Redis Pub/Sub (y Streams para eventos críticos) para propagar cambios de stock en tiempo real:

```python
# backend/shared/infrastructure/events/event_types.py (adiciones)

# Stock Events
STOCK_UPDATED = "STOCK_UPDATED"         # Cambio general de stock
STOCK_DEPLETED = "STOCK_DEPLETED"       # Stock llegó a 0
STOCK_RESTOCKED = "STOCK_RESTOCKED"     # Stock repuesto (era 0, ahora > 0)
STOCK_LOW = "STOCK_LOW"                 # Stock bajo mínimo
STOCK_REORDER = "STOCK_REORDER"         # Stock en punto de reorden

# Purchase Order Events
PO_CREATED = "PO_CREATED"               # Orden de compra creada
PO_SENT = "PO_SENT"                     # Orden enviada a proveedor
PO_RECEIVED = "PO_RECEIVED"             # Mercadería recibida
PO_PARTIAL = "PO_PARTIAL"               # Recepción parcial
```

### Canales de Distribución

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                      DISTRIBUCIÓN DE EVENTOS DE STOCK                        │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│  Evento: STOCK_DEPLETED (Producto agotado)                                 │
│                                                                             │
│  ┌─────────────────┐                                                       │
│  │ Redis Pub/Sub   │                                                       │
│  └────────┬────────┘                                                       │
│           │                                                                 │
│           ├────────────────┬────────────────┬────────────────┐             │
│           ▼                ▼                ▼                ▼             │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐       │
│  │ branch:menu │  │ branch:admin│  │ branch:wait │  │ branch:kitch│       │
│  │    :1       │  │    :1       │  │ ers:1       │  │ en:1        │       │
│  └──────┬──────┘  └──────┬──────┘  └──────┬──────┘  └──────┬──────┘       │
│         │                │                │                │               │
│         ▼                ▼                ▼                ▼               │
│    ┌─────────┐     ┌─────────┐     ┌─────────┐     ┌─────────┐           │
│    │ pwaMenu │     │Dashboard│     │pwaWaiter│     │ Kitchen │           │
│    │         │     │         │     │         │     │ Display │           │
│    │ Muestra │     │ Alerta  │     │ Alerta  │     │ Alerta  │           │
│    │ AGOTADO │     │ en lista│     │ push    │     │ visual  │           │
│    └─────────┘     └─────────┘     └─────────┘     └─────────┘           │
│                                                                             │
│  ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ │
│                                                                             │
│  Evento: STOCK_REORDER (Punto de reorden alcanzado)                        │
│                                                                             │
│  Solo se envía a:                                                          │
│  - branch:admin → Dashboard (para que Manager cree orden de compra)        │
│  - No se envía a pwaMenu ni meseros (no relevante para operación)          │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## Interfaz de Usuario

### Dashboard: Módulo de Inventario

El dashboard administrativo incluye un módulo completo de gestión de inventario:

#### Vista de Lista de Inventario

```typescript
// Dashboard/src/pages/Inventory.tsx

export default function Inventory() {
  const { t } = useTranslation()
  const [filter, setFilter] = useState<StockFilter>('all')
  const [search, setSearch] = useState('')

  const { data: inventory, isLoading } = useInventory(filter, search)

  return (
    <div className="space-y-6">
      {/* Header con acciones */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-gray-900">
            {t('inventory.title')}
          </h1>
          <p className="text-gray-500">
            {t('inventory.subtitle')}
          </p>
        </div>

        <div className="flex gap-3">
          <Button variant="outline" onClick={openCountModal}>
            <ClipboardList className="w-4 h-4 mr-2" />
            {t('inventory.physicalCount')}
          </Button>
          <Button onClick={openCreateModal}>
            <Plus className="w-4 h-4 mr-2" />
            {t('inventory.addItem')}
          </Button>
        </div>
      </div>

      {/* Filtros y búsqueda */}
      <div className="flex gap-4">
        <Input
          placeholder={t('inventory.search')}
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          className="max-w-sm"
        />

        <ToggleGroup value={filter} onValueChange={setFilter}>
          <ToggleGroupItem value="all">
            {t('inventory.filter.all')}
          </ToggleGroupItem>
          <ToggleGroupItem value="low">
            <AlertTriangle className="w-4 h-4 mr-1 text-orange-500" />
            {t('inventory.filter.lowStock')}
          </ToggleGroupItem>
          <ToggleGroupItem value="out">
            <XCircle className="w-4 h-4 mr-1 text-red-500" />
            {t('inventory.filter.outOfStock')}
          </ToggleGroupItem>
        </ToggleGroup>
      </div>

      {/* Alertas de stock */}
      <StockAlerts />

      {/* Tabla de inventario */}
      <InventoryTable
        items={inventory}
        isLoading={isLoading}
        onEdit={openEditModal}
        onAdjust={openAdjustModal}
        onViewHistory={openHistoryModal}
      />
    </div>
  )
}
```

#### Componente de Alertas de Stock

```typescript
// Dashboard/src/components/inventory/StockAlerts.tsx

export function StockAlerts() {
  const { data: alerts } = useStockAlerts()

  if (!alerts?.length) return null

  return (
    <div className="space-y-2">
      {alerts.map((alert) => (
        <Alert
          key={alert.id}
          variant={alert.severity === 'critical' ? 'destructive' : 'warning'}
        >
          <AlertTriangle className="h-4 w-4" />
          <AlertTitle>
            {alert.inventory_name}
          </AlertTitle>
          <AlertDescription className="flex items-center justify-between">
            <span>
              {alert.severity === 'critical'
                ? t('inventory.alert.outOfStock')
                : t('inventory.alert.lowStock', {
                    current: alert.quantity,
                    minimum: alert.min_stock
                  })
              }
            </span>
            <Button size="sm" variant="outline" asChild>
              <Link to={`/inventory/purchase-order/new?item=${alert.inventory_id}`}>
                {t('inventory.createOrder')}
              </Link>
            </Button>
          </AlertDescription>
        </Alert>
      ))}
    </div>
  )
}
```

### Dashboard: Módulo de Proveedores

```typescript
// Dashboard/src/pages/Suppliers.tsx

export default function Suppliers() {
  const { data: suppliers } = useSuppliers()

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-bold">{t('suppliers.title')}</h1>
        <Button onClick={openCreateModal}>
          <Plus className="w-4 h-4 mr-2" />
          {t('suppliers.add')}
        </Button>
      </div>

      <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-3">
        {suppliers?.map((supplier) => (
          <SupplierCard
            key={supplier.id}
            supplier={supplier}
            onEdit={() => openEditModal(supplier)}
            onCreateOrder={() => openOrderModal(supplier)}
          />
        ))}
      </div>
    </div>
  )
}

function SupplierCard({ supplier, onEdit, onCreateOrder }) {
  return (
    <Card>
      <CardHeader className="flex flex-row items-center justify-between">
        <div>
          <CardTitle>{supplier.name}</CardTitle>
          <CardDescription>
            {supplier.category} · {supplier.payment_terms}
          </CardDescription>
        </div>
        <Badge variant={supplier.status === 'ACTIVE' ? 'default' : 'secondary'}>
          {supplier.status}
        </Badge>
      </CardHeader>

      <CardContent>
        <div className="space-y-2 text-sm">
          <div className="flex items-center gap-2">
            <Phone className="w-4 h-4 text-gray-400" />
            <span>{supplier.contact_phone}</span>
          </div>
          <div className="flex items-center gap-2">
            <Mail className="w-4 h-4 text-gray-400" />
            <span>{supplier.contact_email}</span>
          </div>
          <div className="flex items-center gap-2">
            <Clock className="w-4 h-4 text-gray-400" />
            <span>{t('suppliers.leadTime', { days: supplier.lead_time_days })}</span>
          </div>
        </div>

        {/* Rating */}
        {supplier.rating && (
          <div className="mt-4 flex items-center gap-1">
            {[1, 2, 3, 4, 5].map((star) => (
              <Star
                key={star}
                className={cn(
                  "w-4 h-4",
                  star <= supplier.rating
                    ? "text-yellow-400 fill-yellow-400"
                    : "text-gray-300"
                )}
              />
            ))}
            <span className="ml-2 text-sm text-gray-500">
              ({supplier.total_orders} {t('suppliers.orders')})
            </span>
          </div>
        )}
      </CardContent>

      <CardFooter className="flex gap-2">
        <Button variant="outline" size="sm" onClick={onEdit}>
          {t('common.edit')}
        </Button>
        <Button size="sm" onClick={onCreateOrder}>
          {t('suppliers.createOrder')}
        </Button>
      </CardFooter>
    </Card>
  )
}
```

---

## Ventajas y Desventajas

### Ventajas

#### 1. Trazabilidad Completa

Cada unidad de inventario tiene un historial completo desde su ingreso hasta su consumo. Esto permite:

- **Auditorías fiscales**: Cumplimiento con regulaciones de AFIP que exigen justificar movimientos de mercadería.
- **Análisis de pérdidas**: Identificar dónde se produce merma (desperdicio en cocina, productos vencidos, hurto).
- **Costos reales**: Saber exactamente cuánto costó preparar cada plato, no un estimado.

#### 2. Experiencia de Cliente Superior

El cliente nunca pide algo que no está disponible:

- **Menú dinámico**: Los productos agotados se muestran claramente o se ocultan automáticamente.
- **Sin decepciones**: El mesero no tiene que volver a la mesa a decir "no hay".
- **Confianza**: El cliente aprende que lo que ve en el menú, puede pedirlo.

#### 3. Eficiencia Operativa

Automatización de tareas repetitivas:

- **Alertas automáticas**: El sistema avisa cuando hay que reponer, no el empleado que nota que algo falta.
- **Órdenes de compra sugeridas**: Basadas en historial de consumo y lead times de proveedores.
- **Reducción de sobre-stock**: Evita comprar de más, que resulta en merma por vencimiento.

#### 4. Inteligencia de Negocio

Datos para tomar mejores decisiones:

- **Productos más rentables**: Ver margen de ganancia real de cada plato.
- **Proveedores más convenientes**: Comparar precios y tiempos de entrega.
- **Patrones de consumo**: Saber qué días se consume más de qué insumos.

#### 5. Escalabilidad Multi-Sucursal

El modelo soporta operaciones complejas:

- **Stock por sucursal**: Cada local tiene su propio inventario.
- **Transferencias**: Mover mercadería entre sucursales con trazabilidad.
- **Consolidación**: Ver inventario global del tenant para compras centralizadas.

### Desventajas

#### 1. Complejidad de Implementación

Es un módulo complejo que toca múltiples partes del sistema:

- **Tiempo de desarrollo**: Estimación de 3-4 semanas para implementación completa.
- **Migración de datos**: Si ya hay productos, hay que vincularlos con inventario.
- **Capacitación**: El personal debe aprender a usar el nuevo módulo.

#### 2. Overhead Operativo Inicial

Requiere trabajo de setup:

- **Carga inicial**: Alguien debe cargar todos los insumos y cantidades actuales.
- **Vinculación de recetas**: Cada producto debe tener su receta con ingredientes vinculados.
- **Mantenimiento**: Las recetas deben actualizarse cuando cambian las preparaciones.

#### 3. Dependencia de Datos Precisos

El sistema es tan bueno como los datos que recibe:

- **Conteos físicos**: Requiere conteos periódicos para corregir desviaciones.
- **Disciplina**: Si la cocina no sigue las recetas exactas, los cálculos serán incorrectos.
- **Merma no registrada**: Si alguien tira algo sin registrarlo, el sistema no lo sabe.

#### 4. Complejidad en Recetas Variables

No todos los platos se preparan igual siempre:

- **Variaciones**: Un plato puede llevar más o menos de un ingrediente según el cocinero.
- **Sustituciones**: Si falta un ingrediente, se puede sustituir por otro similar.
- **Porciones**: El tamaño de las porciones puede variar.

#### 5. Costo de Infraestructura

Más datos significa más almacenamiento y procesamiento:

- **Base de datos**: Las tablas de movimientos crecen rápidamente.
- **Cálculos**: Verificar disponibilidad de todo el menú tiene costo computacional.
- **Backups**: Más datos críticos que respaldar.

### Mitigaciones

| Desventaja | Mitigación |
|------------|------------|
| Complejidad de implementación | Implementar en fases, empezar solo con stock básico |
| Overhead operativo | Proveer asistente de carga inicial, importación desde Excel |
| Dependencia de datos precisos | Alertas de desviación, conteos obligatorios periódicos |
| Recetas variables | Permitir rangos en cantidades, margen de tolerancia |
| Costo de infraestructura | Archivar movimientos antiguos, cálculos en cache |

---

## Fases de Implementación

### Fase 1: Fundamentos (Semana 1-2)

**Objetivo**: Establecer la estructura de datos y operaciones básicas.

Entregables:
- Modelos `Inventory`, `InventoryMovement`
- API CRUD de inventario (`/api/admin/inventory/*`)
- Vista básica en Dashboard
- Movimientos manuales (ajustes)

### Fase 2: Integración con Pedidos (Semana 2-3)

**Objetivo**: Vincular consumo de inventario con pedidos.

Entregables:
- Modelo `RecipeIngredient` para vincular recetas con inventario
- Servicio de cálculo de disponibilidad
- Decrementar stock automático al servir pedido
- Eventos WebSocket de stock (`STOCK_DEPLETED`, `STOCK_LOW`)

### Fase 3: Integración con Menú Digital (Semana 3)

**Objetivo**: Reflejar disponibilidad en pwaMenu.

Entregables:
- Endpoint `/api/public/menu` incluye `stock_status`
- Componente `ProductCard` muestra estado de stock
- Hook `useStockUpdates` para tiempo real
- Badge "AGOTADO" y "Últimas unidades"

### Fase 4: Proveedores y Compras (Semana 4-5)

**Objetivo**: Gestión completa de proveedores y órdenes de compra.

Entregables:
- Modelos `Supplier`, `SupplierProduct`, `PurchaseOrder`, `PurchaseOrderItem`
- API de proveedores y órdenes
- Flujo de recepción de mercadería
- Vista de proveedores en Dashboard

### Fase 5: Automatización y Reportes (Semana 5-6)

**Objetivo**: Inteligencia de negocio y automatizaciones.

Entregables:
- Sugerencia automática de órdenes de compra
- Alertas configurables (email, push)
- Reportes de consumo, merma, costos
- Dashboard de KPIs de inventario

---

## Consideraciones Técnicas

### Performance

El cálculo de disponibilidad del menú completo puede ser costoso. Estrategias de optimización:

```python
# Caching de disponibilidad con invalidación selectiva
class MenuAvailabilityCache:
    """
    Cache de disponibilidad del menú con TTL corto.
    Se invalida cuando hay movimientos de inventario.
    """

    CACHE_KEY = "menu_availability:{branch_id}"
    TTL_SECONDS = 30  # Máximo 30 segundos de datos stale

    async def get(self, branch_id: int) -> dict | None:
        redis = await get_redis_pool()
        cached = await redis.get(self.CACHE_KEY.format(branch_id=branch_id))
        return json.loads(cached) if cached else None

    async def set(self, branch_id: int, availability: dict) -> None:
        redis = await get_redis_pool()
        await redis.setex(
            self.CACHE_KEY.format(branch_id=branch_id),
            self.TTL_SECONDS,
            json.dumps(availability)
        )

    async def invalidate(self, branch_id: int) -> None:
        redis = await get_redis_pool()
        await redis.delete(self.CACHE_KEY.format(branch_id=branch_id))
```

### Concurrencia

Múltiples pedidos pueden intentar reservar el mismo stock simultáneamente:

```python
# Reserva de stock con bloqueo optimista
async def reserve_stock(
    db: Session,
    inventory_id: int,
    quantity: Decimal
) -> bool:
    """
    Intenta reservar stock con bloqueo optimista.
    Reintenta automáticamente en caso de conflicto.
    """
    for attempt in range(3):
        inventory = db.scalar(
            select(Inventory)
            .where(Inventory.id == inventory_id)
            .with_for_update(skip_locked=True)
        )

        if not inventory:
            return False

        available = inventory.quantity - inventory.reserved_quantity

        if available < quantity:
            return False

        inventory.reserved_quantity += quantity

        try:
            db.commit()
            return True
        except IntegrityError:
            db.rollback()
            continue

    return False
```

### Precisión Decimal

Los cálculos financieros requieren precisión:

```python
# Usar Decimal para todos los cálculos monetarios
from decimal import Decimal, ROUND_HALF_UP

def calculate_line_total(
    quantity: Decimal,
    unit_price_cents: int,
    discount_percent: Decimal,
    tax_percent: Decimal
) -> int:
    """
    Calcula el total de una línea con precisión.
    Retorna centavos como entero.
    """
    subtotal = quantity * Decimal(unit_price_cents)
    discount = subtotal * discount_percent / 100
    net = subtotal - discount
    tax = net * tax_percent / 100
    total = net + tax

    # Redondear a centavos
    return int(total.quantize(Decimal('1'), rounding=ROUND_HALF_UP))
```

---

## Conclusión

El sistema de gestión de stock que hemos diseñado representa una evolución significativa en las capacidades del sistema de restaurantes. No se trata simplemente de saber cuántas unidades quedan de cada insumo, sino de crear un ecosistema integrado donde la información fluye bidireccionalmente entre el inventario, el menú digital, las recetas, los proveedores, y los reportes de negocio.

La inversión en tiempo de desarrollo se justifica por los beneficios tangibles: reducción de situaciones incómodas con clientes, optimización de compras, control de costos, y datos para tomar mejores decisiones. Un restaurante que controla su inventario de manera precisa y automatizada tiene una ventaja competitiva significativa.

El diseño modular permite una implementación por fases, comenzando con funcionalidades básicas y expandiendo gradualmente. Esto reduce el riesgo y permite validar el sistema con usuarios reales antes de invertir en las funcionalidades más avanzadas.

La clave del éxito no está solo en la tecnología, sino en la adopción por parte del equipo del restaurante. Por eso es fundamental que la interfaz sea intuitiva, que el sistema requiera el mínimo de entrada manual posible, y que los beneficios sean visibles desde el primer día de uso.

---

## Anexo: Estructura de Archivos Propuesta

```
backend/
├── rest_api/
│   ├── models/
│   │   ├── inventory.py          # Inventory, InventoryMovement
│   │   ├── supplier.py           # Supplier, SupplierProduct
│   │   └── purchase.py           # PurchaseOrder, PurchaseOrderItem
│   ├── routers/
│   │   └── admin/
│   │       ├── inventory.py      # CRUD inventario
│   │       ├── suppliers.py      # CRUD proveedores
│   │       └── purchases.py      # Órdenes de compra
│   └── services/
│       └── domain/
│           ├── inventory_service.py
│           ├── supplier_service.py
│           ├── purchase_service.py
│           └── recipe_stock_service.py
├── shared/
│   └── infrastructure/
│       └── events/
│           └── event_types.py    # Nuevos eventos STOCK_*

Dashboard/
├── src/
│   ├── pages/
│   │   ├── Inventory.tsx
│   │   ├── Suppliers.tsx
│   │   └── PurchaseOrders.tsx
│   ├── components/
│   │   └── inventory/
│   │       ├── InventoryTable.tsx
│   │       ├── StockAlerts.tsx
│   │       ├── AdjustmentModal.tsx
│   │       └── MovementHistory.tsx
│   └── stores/
│       └── inventoryStore.ts

pwaMenu/
├── src/
│   ├── hooks/
│   │   └── useStockUpdates.ts
│   └── components/
│       └── ProductCard.tsx       # Modificado para mostrar stock
```

---

*Documento preparado para el equipo de desarrollo del proyecto Integrador.*
