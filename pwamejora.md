# Plan de Mejoras - pwaMenu & Backend

## Documento de Arquitectura y Mejoras Propuestas

**Autor**: Claude (Arquitecto de Software / Sr. Developer)
**Fecha**: Enero 2026
**Versión**: 1.0

---

## 1. Resumen Ejecutivo

Este documento presenta un análisis comparativo entre la propuesta arquitectónica documentada en `pwapropu.txt` y la implementación actual del sistema (pwaMenu + Backend). Se identifican gaps, oportunidades de mejora y se propone un plan de acción priorizado.

### 1.1 Estado Actual vs Propuesta

| Aspecto | Implementación Actual | Propuesta (pwapropu.txt) | Gap |
|---------|----------------------|--------------------------|-----|
| Modelo de Diner | Anónimo (color local) | Entidad persistente con nombre | Alto |
| Pagos | Check simple | Charge/Payment/Allocation | Alto |
| División de cuenta | 3 modos básicos | FIFO allocation con flexibility | Medio |
| WebSocket | Por sesión/kitchen | Igual, bien implementado | Bajo |
| Autenticación | Table token HMAC | JWT en QR (propuesto) | Medio |
| Kitchen tickets | Básico | Sistema completo de tickets | Medio |

---

## 2. Análisis de Nomenclatura y Convenciones

### 2.1 Inconsistencias Detectadas

La normalización de nombres es crucial para la mantenibilidad. Se detectaron las siguientes inconsistencias:

#### Backend (Python/SQLAlchemy)

```python
# ACTUAL: Mezcla de convenciones
class TableSession:
    session_status: str      # Correcto: snake_case
    table_token: str         # Correcto

class Round:
    round_status: str        # OK pero podría ser solo "status"

class Check:
    check_status: str        # Redundante: "status" sería suficiente
```

**Propuesta de normalización:**

```python
# PROPUESTO: Consistencia en modelos
class Round:
    status: RoundStatus      # Enum, no string
    submitted_at: datetime   # Siempre _at para timestamps

class Check:
    status: CheckStatus      # Enum
    requested_at: datetime
    paid_at: datetime | None
```

#### Frontend (TypeScript/React)

```typescript
// ACTUAL: Inconsistencias en tableStore
interface DinerState {
  localDinerId: string      // "Id" mayúscula
  backend_session_id: number | null  // snake_case (debería ser camelCase)
}

// PROPUESTO: Consistencia camelCase
interface DinerState {
  localDinerId: string
  backendSessionId: number | null  // camelCase consistente
}
```

### 2.2 Convención Propuesta

| Contexto | Convención | Ejemplo |
|----------|------------|---------|
| Python variables/functions | snake_case | `get_session_total()` |
| Python classes | PascalCase | `TableSession` |
| Python enums | UPPER_SNAKE | `RoundStatus.IN_KITCHEN` |
| TypeScript variables | camelCase | `backendSessionId` |
| TypeScript types/interfaces | PascalCase | `DinerState` |
| TypeScript constants | UPPER_SNAKE | `MAX_DINERS` |
| API endpoints | kebab-case | `/api/diner/service-call` |
| Database columns | snake_case | `created_at` |

---

## 3. Mejoras de Arquitectura

### 3.1 Modelo de Diner (Prioridad: Alta)

#### Situación Actual

El sistema actual maneja comensales de forma completamente anónima en el frontend. Cada comensal tiene un `localDinerId` (UUID) y un color asignado, pero esta información no persiste en el backend.

```typescript
// ACTUAL: Diner es solo un concepto local
interface DinerCartItem {
  menuItemId: string
  localDinerId: string  // Solo existe en frontend
  // ...
}
```

El backend recibe items con `diner_name` como string opcional:

```python
# ACTUAL: Backend solo guarda el nombre como string
class RoundItemInput(BaseModel):
    menu_item_id: int
    quantity: int
    notes: str | None
    diner_name: str | None  # String plano, no entidad
```

#### Propuesta de Mejora

**Narrativa**: La propuesta de `pwapropu.txt` introduce un modelo `Diner` como entidad persistente. Esto permite:

1. **Trazabilidad**: Saber qué pidió cada persona específica
2. **Historial**: Un comensal puede ver su historial de pedidos en la sesión
3. **Pagos precisos**: Asignar pagos a consumos específicos de cada diner
4. **Analytics**: Métricas por tipo de comensal

**Implementación técnica:**

```python
# PROPUESTO: Nuevo modelo Diner en backend
class Diner(Base):
    __tablename__ = "diner"

    id: Mapped[int] = mapped_column(primary_key=True)
    session_id: Mapped[int] = mapped_column(ForeignKey("table_session.id"))
    name: Mapped[str] = mapped_column(String(50))
    color: Mapped[str] = mapped_column(String(7))  # #RRGGBB
    joined_at: Mapped[datetime] = mapped_column(default=func.now())

    # Relations
    session: Mapped["TableSession"] = relationship(back_populates="diners")
    round_items: Mapped[list["RoundItem"]] = relationship(back_populates="diner")
```

```typescript
// PROPUESTO: Frontend sincroniza diner con backend
interface BackendDiner {
  id: number
  sessionId: number
  name: string
  color: string
  joinedAt: string
}

// En tableStore
async function joinTable(tableId: number, dinerName: string): Promise<void> {
  // 1. Crear/obtener sesión
  const session = await sessionAPI.createOrGetSession(tableId)

  // 2. Registrar diner en backend (NUEVO)
  const diner = await dinerAPI.registerDiner({
    session_id: session.session_id,
    name: dinerName,
    color: getNextAvailableColor()
  })

  // 3. Guardar en estado local
  set({
    backendDinerId: diner.id,
    localDinerId: diner.id.toString()
  })
}
```

**Migración gradual:**

1. Crear tabla `diner` con FK a `table_session`
2. Agregar endpoint `POST /api/diner/register`
3. Modificar `RoundItem` para tener FK a `diner` (nullable inicialmente)
4. Actualizar frontend para registrar diner al unirse
5. Deprecar `diner_name` string en favor de `diner_id`

### 3.2 Sistema de Pagos Avanzado (Prioridad: Alta)

#### Situación Actual

El sistema actual tiene un modelo de pago simplificado:

```python
# ACTUAL
class Check(Base):
    total_cents: int
    paid_cents: int
    status: str  # PENDING, PARTIAL, PAID

class Payment(Base):
    check_id: int
    amount_cents: int
    method: str
    # No hay allocation a items específicos
```

El frontend maneja división de cuenta con tres modos:
- `equal`: División equitativa
- `by_consumption`: Cada quien paga lo suyo
- `custom`: Porcentajes personalizados

Pero NO hay persistencia de esta asignación en backend.

#### Propuesta de Mejora

**Narrativa**: La propuesta introduce un modelo de tres capas para pagos:

1. **Charge**: Cada item consumido genera un "cargo" asignado a un diner
2. **Payment**: Dinero que entra (efectivo, MP, etc.)
3. **Allocation**: Vincula payments con charges específicos

Esto permite escenarios complejos como:
- "Juan paga su hamburguesa y la mitad de las papas compartidas"
- "María paga con MP su parte y le sobran $500 que van al propósito general"
- Propinas asignadas proporcionalmente

```python
# PROPUESTO: Modelo de pagos completo

class Charge(Base):
    """Un cargo específico asignado a un diner"""
    __tablename__ = "charge"

    id: Mapped[int] = mapped_column(primary_key=True)
    check_id: Mapped[int] = mapped_column(ForeignKey("check.id"))
    diner_id: Mapped[int | None] = mapped_column(ForeignKey("diner.id"))
    round_item_id: Mapped[int] = mapped_column(ForeignKey("round_item.id"))
    amount_cents: Mapped[int]
    description: Mapped[str]

    # Relations
    allocations: Mapped[list["Allocation"]] = relationship()


class Payment(Base):
    """Un pago realizado"""
    __tablename__ = "payment"

    id: Mapped[int] = mapped_column(primary_key=True)
    check_id: Mapped[int] = mapped_column(ForeignKey("check.id"))
    payer_diner_id: Mapped[int | None] = mapped_column(ForeignKey("diner.id"))
    amount_cents: Mapped[int]
    method: Mapped[PaymentMethod]  # CASH, MERCADOPAGO, CARD
    external_id: Mapped[str | None]  # MP payment_id, etc.
    status: Mapped[PaymentStatus]  # PENDING, APPROVED, REJECTED
    created_at: Mapped[datetime]


class Allocation(Base):
    """Vincula un payment con charges específicos (FIFO o manual)"""
    __tablename__ = "allocation"

    id: Mapped[int] = mapped_column(primary_key=True)
    payment_id: Mapped[int] = mapped_column(ForeignKey("payment.id"))
    charge_id: Mapped[int] = mapped_column(ForeignKey("charge.id"))
    amount_cents: Mapped[int]  # Puede ser parcial
```

**Algoritmo FIFO para allocation:**

```python
async def allocate_payment_fifo(
    payment: Payment,
    charges: list[Charge]
) -> list[Allocation]:
    """
    Asigna el monto del pago a los cargos pendientes en orden FIFO.

    Ejemplo:
    - Payment: $1000
    - Charges: [$300 (burger), $500 (pizza), $400 (drink)]
    - Result: Allocation cubre burger completo, pizza completo,
              y $200 parcial del drink
    """
    remaining = payment.amount_cents
    allocations = []

    for charge in sorted(charges, key=lambda c: c.id):  # FIFO por ID
        if remaining <= 0:
            break

        unpaid = charge.amount_cents - sum(
            a.amount_cents for a in charge.allocations
        )

        if unpaid > 0:
            to_allocate = min(remaining, unpaid)
            allocations.append(Allocation(
                payment_id=payment.id,
                charge_id=charge.id,
                amount_cents=to_allocate
            ))
            remaining -= to_allocate

    return allocations
```

### 3.3 Patrones React 19 (Prioridad: Media)

#### Situación Actual

El proyecto ya usa algunos patrones de React 19:
- `useActionState` para formularios
- `useOptimistic` para UI optimista
- Zustand con selectors para evitar re-renders

Sin embargo, hay oportunidades de mejora:

#### 3.3.1 Uso de `use()` para data fetching

```typescript
// ACTUAL: useEffect para cargar datos
function MenuPage() {
  const [menu, setMenu] = useState<Menu | null>(null)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    menuAPI.getMenu(slug).then(setMenu).finally(() => setLoading(false))
  }, [slug])

  if (loading) return <Skeleton />
  // ...
}

// PROPUESTO: use() con Suspense (React 19)
function MenuPage() {
  const menuPromise = useMemo(
    () => menuAPI.getMenu(slug),
    [slug]
  )

  return (
    <Suspense fallback={<Skeleton />}>
      <MenuContent menuPromise={menuPromise} />
    </Suspense>
  )
}

function MenuContent({ menuPromise }: { menuPromise: Promise<Menu> }) {
  const menu = use(menuPromise)  // React 19 use() hook
  // Render menu directly, no loading state needed
}
```

#### 3.3.2 Optimistic Updates Mejorados

```typescript
// ACTUAL: Optimistic update básico
const [optimisticCart, addOptimistic] = useOptimistic(
  cart,
  (state, newItem: CartItem) => [...state, newItem]
)

// PROPUESTO: Con rollback automático
function useOptimisticCart() {
  const cart = useTableStore(selectCart)
  const addToCart = useTableStore(s => s.addToCart)

  const [optimisticCart, updateOptimistic] = useOptimistic(
    cart,
    (state, action: CartAction) => {
      switch (action.type) {
        case 'add':
          return [...state, { ...action.item, _pending: true }]
        case 'remove':
          return state.filter(i => i.id !== action.id)
        case 'confirm':
          return state.map(i =>
            i.id === action.id ? { ...i, _pending: false } : i
          )
        case 'rollback':
          return state.filter(i => i.id !== action.id || !i._pending)
      }
    }
  )

  async function addItemOptimistic(item: CartItem) {
    const tempId = crypto.randomUUID()
    updateOptimistic({ type: 'add', item: { ...item, id: tempId } })

    try {
      const confirmedItem = await addToCart(item)
      updateOptimistic({ type: 'confirm', id: tempId })
    } catch (error) {
      updateOptimistic({ type: 'rollback', id: tempId })
      throw error
    }
  }

  return { cart: optimisticCart, addItem: addItemOptimistic }
}
```

#### 3.3.3 Server Actions Pattern (para SSR futuro)

```typescript
// PROPUESTO: Preparación para Server Components
// actions/submitRound.ts
'use server'

import { dinerAPI } from '@/services/api'
import { revalidatePath } from 'next/cache'

export async function submitRoundAction(
  prevState: SubmitState,
  formData: FormData
): Promise<SubmitState> {
  const items = JSON.parse(formData.get('items') as string)

  try {
    const result = await dinerAPI.submitRound({ items })
    revalidatePath('/orders')
    return { success: true, roundId: result.round_id }
  } catch (error) {
    return { success: false, error: getErrorMessage(error) }
  }
}

// En componente
function SubmitButton() {
  const [state, action, isPending] = useActionState(submitRoundAction, {})

  return (
    <form action={action}>
      <input type="hidden" name="items" value={JSON.stringify(items)} />
      <button disabled={isPending}>
        {isPending ? 'Enviando...' : 'Enviar Pedido'}
      </button>
    </form>
  )
}
```

### 3.4 Mejoras en WebSocket (Prioridad: Media)

#### Situación Actual

El WebSocket funciona correctamente pero tiene oportunidades:

```typescript
// ACTUAL: Reconexión básica
class WebSocketService {
  private reconnectAttempts = 0
  private maxReconnectAttempts = 5

  private handleClose() {
    if (this.reconnectAttempts < this.maxReconnectAttempts) {
      setTimeout(() => this.connect(), 1000 * Math.pow(2, this.reconnectAttempts))
      this.reconnectAttempts++
    }
  }
}
```

#### Propuesta: Heartbeat y Estado de Conexión

```typescript
// PROPUESTO: WebSocket robusto con heartbeat
interface WebSocketState {
  status: 'connecting' | 'connected' | 'disconnected' | 'reconnecting'
  lastHeartbeat: number | null
  latency: number | null
}

class RobustWebSocketService {
  private heartbeatInterval: number | null = null
  private readonly HEARTBEAT_INTERVAL = 30000  // 30 segundos
  private readonly HEARTBEAT_TIMEOUT = 5000    // 5 segundos para respuesta

  private state: WebSocketState = {
    status: 'disconnected',
    lastHeartbeat: null,
    latency: null
  }

  private startHeartbeat() {
    this.heartbeatInterval = window.setInterval(() => {
      if (this.ws?.readyState === WebSocket.OPEN) {
        const pingTime = Date.now()
        this.ws.send(JSON.stringify({ type: 'ping', timestamp: pingTime }))

        // Timeout si no responde
        setTimeout(() => {
          if (this.state.lastHeartbeat && this.state.lastHeartbeat < pingTime) {
            this.handleStaleConnection()
          }
        }, this.HEARTBEAT_TIMEOUT)
      }
    }, this.HEARTBEAT_INTERVAL)
  }

  private handleMessage(event: MessageEvent) {
    const data = JSON.parse(event.data)

    if (data.type === 'pong') {
      const latency = Date.now() - data.timestamp
      this.state = {
        ...this.state,
        lastHeartbeat: Date.now(),
        latency
      }
      return
    }

    // Procesar otros eventos...
  }

  private handleStaleConnection() {
    console.warn('WebSocket connection stale, reconnecting...')
    this.ws?.close()
    this.connect()
  }
}
```

### 3.5 Sistema de Kitchen Tickets (Prioridad: Media)

#### Situación Actual

La cocina recibe rounds pero no tiene un sistema de tickets estructurado.

#### Propuesta

**Narrativa**: Un ticket de cocina agrupa items de un round por estación de preparación. Permite:
- Asignar items a diferentes estaciones (parrilla, freidora, bebidas)
- Tracking de tiempo por ticket
- Métricas de performance de cocina

```python
# PROPUESTO: Modelo KitchenTicket
class KitchenStation(str, Enum):
    GRILL = "grill"
    FRYER = "fryer"
    COLD = "cold"
    DRINKS = "drinks"
    DESSERTS = "desserts"

class KitchenTicket(Base):
    __tablename__ = "kitchen_ticket"

    id: Mapped[int] = mapped_column(primary_key=True)
    round_id: Mapped[int] = mapped_column(ForeignKey("round.id"))
    station: Mapped[KitchenStation]
    status: Mapped[TicketStatus]  # PENDING, IN_PROGRESS, DONE
    printed_at: Mapped[datetime]
    started_at: Mapped[datetime | None]
    completed_at: Mapped[datetime | None]

    # Calculated
    @property
    def prep_time_seconds(self) -> int | None:
        if self.started_at and self.completed_at:
            return (self.completed_at - self.started_at).seconds
        return None
```

```typescript
// Frontend: KitchenTicketCard component
interface KitchenTicket {
  id: number
  roundId: number
  station: KitchenStation
  status: TicketStatus
  items: TicketItem[]
  printedAt: string
  elapsedSeconds: number
}

function KitchenTicketCard({ ticket }: { ticket: KitchenTicket }) {
  const urgencyClass = getUrgencyClass(ticket.elapsedSeconds)

  return (
    <Card className={cn("kitchen-ticket", urgencyClass)}>
      <CardHeader>
        <div className="flex justify-between">
          <Badge>{ticket.station}</Badge>
          <Timer startTime={ticket.printedAt} />
        </div>
        <span className="text-sm text-muted">
          Mesa {ticket.tableNumber} - Round #{ticket.roundId}
        </span>
      </CardHeader>
      <CardContent>
        <ul className="space-y-2">
          {ticket.items.map(item => (
            <TicketItemRow key={item.id} item={item} />
          ))}
        </ul>
      </CardContent>
      <CardFooter>
        <TicketActions ticket={ticket} />
      </CardFooter>
    </Card>
  )
}

function getUrgencyClass(seconds: number): string {
  if (seconds > 900) return "border-red-500 bg-red-50"    // > 15 min
  if (seconds > 600) return "border-yellow-500 bg-yellow-50"  // > 10 min
  return "border-green-500"
}
```

---

## 4. Mejoras de Seguridad

### 4.1 JWT para QR Tokens

#### Situación Actual

Los table tokens son HMAC-signed pero no son JWT:

```python
# ACTUAL
def generate_table_token(table_id: int, session_id: int) -> str:
    payload = f"{table_id}:{session_id}:{timestamp}"
    signature = hmac.new(SECRET_KEY, payload.encode(), hashlib.sha256).hexdigest()
    return base64.urlsafe_b64encode(f"{payload}:{signature}").decode()
```

#### Propuesta: Migrar a JWT

**Narrativa**: JWT proporciona:
- Expiración automática (`exp` claim)
- Información verificable sin DB lookup
- Estándar bien documentado
- Rotación de tokens más fácil

```python
# PROPUESTO: JWT para table tokens
from jose import jwt
from datetime import datetime, timedelta

class TableTokenService:
    def __init__(self, secret_key: str, algorithm: str = "HS256"):
        self.secret_key = secret_key
        self.algorithm = algorithm

    def create_token(
        self,
        table_id: int,
        session_id: int,
        branch_id: int,
        expires_delta: timedelta = timedelta(hours=8)
    ) -> str:
        """Crear JWT token para mesa"""
        expire = datetime.utcnow() + expires_delta

        payload = {
            "sub": f"table:{table_id}",
            "table_id": table_id,
            "session_id": session_id,
            "branch_id": branch_id,
            "type": "table_token",
            "exp": expire,
            "iat": datetime.utcnow(),
        }

        return jwt.encode(payload, self.secret_key, algorithm=self.algorithm)

    def verify_token(self, token: str) -> TableTokenPayload:
        """Verificar y decodificar token"""
        try:
            payload = jwt.decode(
                token,
                self.secret_key,
                algorithms=[self.algorithm]
            )

            if payload.get("type") != "table_token":
                raise InvalidTokenError("Invalid token type")

            return TableTokenPayload(**payload)

        except jwt.ExpiredSignatureError:
            raise TokenExpiredError("Table token expired")
        except jwt.JWTError as e:
            raise InvalidTokenError(f"Invalid token: {e}")
```

### 4.2 Rate Limiting

```python
# PROPUESTO: Rate limiting por mesa
from slowapi import Limiter
from slowapi.util import get_remote_address

limiter = Limiter(key_func=get_remote_address)

@router.post("/diner/rounds/submit")
@limiter.limit("10/minute")  # Máximo 10 rounds por minuto por IP
async def submit_round(
    request: Request,
    data: SubmitRoundRequest,
    session: TableSession = Depends(get_current_session)
):
    # También limitar por session_id
    await check_session_rate_limit(session.id, max_rounds=5, window_minutes=1)
    # ...
```

---

## 5. Plan de Implementación

### Fase 1: Normalización y Cleanup (1-2 sprints)

**Objetivo**: Establecer base sólida antes de features nuevos.

| Tarea | Prioridad | Esfuerzo |
|-------|-----------|----------|
| Normalizar nombres en backend (snake_case consistente) | Alta | Bajo |
| Normalizar nombres en frontend (camelCase consistente) | Alta | Bajo |
| Migrar `backend_session_id` a `backendSessionId` | Alta | Bajo |
| Agregar enums TypeScript para estados | Media | Bajo |
| Documentar convenciones en CLAUDE.md | Alta | Bajo |

### Fase 2: Modelo Diner (2-3 sprints)

**Objetivo**: Persistir comensales en backend.

| Tarea | Prioridad | Esfuerzo |
|-------|-----------|----------|
| Crear tabla `diner` con migración Alembic | Alta | Medio |
| Endpoint POST /api/diner/register | Alta | Bajo |
| Modificar RoundItem con FK a diner (nullable) | Alta | Medio |
| Actualizar tableStore.joinTable() | Alta | Medio |
| Sincronizar colores con backend | Media | Bajo |
| Tests de integración | Alta | Medio |

### Fase 3: Sistema de Pagos Avanzado (3-4 sprints)

**Objetivo**: Implementar Charge/Payment/Allocation.

| Tarea | Prioridad | Esfuerzo |
|-------|-----------|----------|
| Crear tablas charge, allocation | Alta | Medio |
| Generar charges automáticamente al cerrar check | Alta | Medio |
| Implementar allocation FIFO | Alta | Alto |
| UI para ver desglose de cuenta por diner | Alta | Alto |
| Endpoint para allocation manual | Media | Medio |
| Integrar con Mercado Pago real | Alta | Alto |

### Fase 4: Kitchen Tickets (2 sprints)

**Objetivo**: Sistema de tickets para cocina.

| Tarea | Prioridad | Esfuerzo |
|-------|-----------|----------|
| Crear tabla kitchen_ticket | Media | Bajo |
| Agrupar items por station al crear round | Media | Medio |
| UI de tickets en pwaWaiter/kitchen | Media | Alto |
| Timer y urgency indicators | Media | Medio |
| Métricas de tiempo de preparación | Baja | Medio |

### Fase 5: React 19 Patterns (Ongoing)

**Objetivo**: Adoptar patrones modernos gradualmente.

| Tarea | Prioridad | Esfuerzo |
|-------|-----------|----------|
| Migrar fetching a use() + Suspense | Media | Medio |
| Implementar useOptimistic con rollback | Media | Medio |
| Preparar estructura para Server Components | Baja | Alto |
| Documentar patrones en CLAUDE.md | Alta | Bajo |

---

## 6. Métricas de Éxito

### 6.1 Técnicas

- **Test coverage**: Mantener >80% en stores críticos
- **Type safety**: 0 errores de TypeScript en build
- **Bundle size**: <500KB gzipped para pwaMenu
- **Lighthouse PWA**: Score >90

### 6.2 Funcionales

- **Tiempo de order**: <30 segundos desde agregar al carrito hasta confirmación
- **Tiempo de pago**: <2 minutos para completar pago dividido
- **Uptime WebSocket**: >99.5% de conexiones exitosas

### 6.3 UX

- **Error rate**: <1% de órdenes fallidas
- **Abandono**: <5% de sesiones sin orden completada

---

## 7. Riesgos y Mitigaciones

| Riesgo | Impacto | Probabilidad | Mitigación |
|--------|---------|--------------|------------|
| Migración de datos en producción | Alto | Media | Scripts de migración idempotentes, backups |
| Breaking changes en API | Alto | Media | Versionado de API, deprecation gradual |
| Performance con muchos diners | Medio | Baja | Índices en diner_id, paginación |
| Complejidad de allocation | Medio | Media | Tests exhaustivos, UI clara |

---

## 8. Conclusiones

La implementación actual es funcional y sigue buenas prácticas. Las mejoras propuestas en este documento se enfocan en:

1. **Consistencia**: Normalización de nombres y convenciones
2. **Trazabilidad**: Modelo Diner persistente
3. **Flexibilidad**: Sistema de pagos con allocation
4. **Modernización**: Patrones React 19
5. **Operaciones**: Kitchen tickets

La priorización sugiere comenzar con cleanup y normalización (bajo riesgo, alto valor), seguido del modelo Diner (habilita las demás features), y luego el sistema de pagos avanzado (mayor complejidad pero alto valor de negocio).

---

## Apéndice A: Mapeo de Tipos Backend ↔ Frontend

```typescript
// types/mappings.ts

// ID Conversion
export const toFrontendId = (backendId: number): string => String(backendId)
export const toBackendId = (frontendId: string): number => parseInt(frontendId, 10)

// Price Conversion (backend: cents, frontend: dollars)
export const toFrontendPrice = (cents: number): number => cents / 100
export const toBackendPrice = (dollars: number): number => Math.round(dollars * 100)

// Status Mapping
export const tableStatusMap = {
  FREE: 'libre',
  ACTIVE: 'ocupada',
  PAYING: 'pagando',
  OUT_OF_SERVICE: 'fuera_servicio'
} as const

export const roundStatusMap = {
  PENDING: 'pendiente',
  IN_KITCHEN: 'en_cocina',
  READY: 'listo',
  SERVED: 'servido',
  CANCELLED: 'cancelado'
} as const
```

## Apéndice B: Checklist de Code Review

```markdown
## PR Checklist - pwaMenu/Backend

### Nomenclatura
- [ ] Variables Python en snake_case
- [ ] Variables TypeScript en camelCase
- [ ] Tipos/Interfaces en PascalCase
- [ ] Constantes en UPPER_SNAKE_CASE
- [ ] Endpoints en kebab-case

### React 19
- [ ] Zustand con selectores (no destructuring)
- [ ] useShallow para arrays filtrados
- [ ] useOptimistic para mutations
- [ ] Manejo de errores con ErrorBoundary

### Seguridad
- [ ] Sin console.log en producción (usar logger)
- [ ] Validación de inputs en backend
- [ ] Table token verificado en endpoints diner
- [ ] Sin secrets hardcodeados

### Tests
- [ ] Tests unitarios para lógica nueva
- [ ] Tests de integración para API
- [ ] Mocks apropiados (no fetch real en tests)
```

---

*Documento generado como parte del análisis arquitectónico del proyecto Integrador.*
