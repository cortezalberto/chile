# Plan de Implementación: Migración pwaMenu al Backend Real

## Resumen Ejecutivo

Este documento detalla el plan de actualización de **pwaMenu** para eliminar los mocks y conectar con el backend real (FastAPI + PostgreSQL). La aplicación actualmente funciona 100% con datos locales (mockData.ts + localStorage), excepto el chat RAG que ya está conectado.

---

## 1. Análisis de Estado Actual

### 1.1 Componentes Actuales de pwaMenu

| Componente | Estado | Backend Endpoint |
|------------|--------|------------------|
| Menú (categorías, productos) | MOCK (mockData.ts) | `/api/public/menu/{slug}` |
| Sesión de mesa | LOCAL (localStorage) | `/api/tables/{table_id}/session` |
| Carrito compartido | LOCAL (Zustand) | N/A (solo frontend) |
| Envío de órdenes (submitOrder) | MOCK | `/api/diner/rounds/submit` |
| Historial de rondas | LOCAL | `/api/diner/session/{id}/rounds` |
| Llamar al mozo | MOCK | `/api/diner/service-call` |
| Pedir cuenta | LOCAL | `/api/billing/check/request` |
| Ver cuenta detallada | LOCAL | `/api/diner/check` |
| Pago Mercado Pago | MOCK en DEV | `/api/billing/mercadopago/preference` |
| Chat RAG | **BACKEND** | `/api/chat` |
| WebSocket (actualizaciones) | NO IMPLEMENTADO | `ws://localhost:8001/ws/diner` |

### 1.2 Modelos de Datos: Diferencias Críticas

| Concepto | pwaMenu (Frontend) | Backend | Acción Requerida |
|----------|-------------------|---------|------------------|
| Session ID | `string` (UUID) | `int` (BigInteger) | Cambiar a `number` |
| Table ID | `string` | `int` | Cambiar a `number` |
| Precios | `number` (dólares) | `int` (centavos) | Conversión ÷100 / ×100 |
| Diner (comensal) | Modelo completo | No existe en DB | Solo frontend, enviar `diner_name` en notas |
| CartItem.id | `string` (UUID) | N/A | Solo frontend |
| Round.id | `string` | `int` | Cambiar a `number` |

### 1.3 Autenticación

**Actual:** Sin autenticación - todo es local.

**Requerido:**
- Endpoint `/api/tables/{table_id}/session` retorna `table_token` (JWT)
- Header `X-Table-Token` en todas las peticiones de diner
- WebSocket requiere `?table_token=...` en query params

---

## 2. Arquitectura Propuesta

### 2.1 Flujo de Usuario Actualizado

```
┌─────────────────────────────────────────────────────────────────────────┐
│                           FLUJO ACTUALIZADO                             │
└─────────────────────────────────────────────────────────────────────────┘

1. ESCANEAR QR / INGRESAR MESA
   ┌─────────────────┐
   │ QRSimulator     │ → Extrae table_id del QR
   │ o TableNumberStep│ → Usuario ingresa número
   └────────┬────────┘
            │
            ▼
2. OBTENER SESIÓN (NUEVO - Backend)
   ┌─────────────────────────────────────────────────────────────┐
   │ POST /api/tables/{table_id}/session                        │
   │ Response: { session_id, table_token, table_code, status }  │
   │                                                             │
   │ DECISIÓN:                                                   │
   │ - Si mesa tiene sesión activa → Unirse a sesión existente  │
   │ - Si mesa está libre → Crear nueva sesión                  │
   └────────┬────────────────────────────────────────────────────┘
            │
            ▼
3. CONECTAR WEBSOCKET (NUEVO)
   ┌─────────────────────────────────────────────────────────────┐
   │ ws://localhost:8001/ws/diner?table_token={token}           │
   │                                                             │
   │ Eventos que recibirá:                                       │
   │ - ROUND_IN_KITCHEN (orden en preparación)                  │
   │ - ROUND_READY (orden lista)                                 │
   │ - ROUND_SERVED (orden servida)                              │
   │ - PAYMENT_APPROVED (pago recibido)                          │
   │ - CHECK_PAID (cuenta completamente pagada)                  │
   └────────┬────────────────────────────────────────────────────┘
            │
            ▼
4. CARGAR MENÚ (ACTUALIZAR - Backend)
   ┌─────────────────────────────────────────────────────────────┐
   │ GET /api/public/menu/{branch_slug}                         │
   │ Response: { branch_id, categories[], products[] }          │
   │                                                             │
   │ Cambios:                                                    │
   │ - Precios en centavos → Convertir a pesos para mostrar    │
   │ - IDs numéricos → Mantener como number                     │
   └────────┬────────────────────────────────────────────────────┘
            │
            ▼
5. AGREGAR AL CARRITO (Mantener LOCAL)
   ┌─────────────────────────────────────────────────────────────┐
   │ El carrito sigue siendo 100% local (Zustand + localStorage) │
   │                                                             │
   │ CartItem mantiene:                                          │
   │ - product_id: number (del backend)                         │
   │ - diner_id: string (UUID local, identifica al comensal)    │
   │ - diner_name: string (nombre del comensal)                 │
   │ - price: number (en pesos para mostrar)                    │
   │ - price_cents: number (NUEVO - en centavos para backend)   │
   └────────┬────────────────────────────────────────────────────┘
            │
            ▼
6. ENVIAR ORDEN (ACTUALIZAR - Backend)
   ┌─────────────────────────────────────────────────────────────┐
   │ POST /api/diner/rounds/submit                              │
   │ Headers: { X-Table-Token: {table_token} }                  │
   │ Body: {                                                     │
   │   items: [                                                  │
   │     { product_id: 123, qty: 2, notes: "Sin cebolla - Juan" }│
   │   ]                                                         │
   │ }                                                           │
   │                                                             │
   │ Response: { session_id, round_id, round_number, status }   │
   │                                                             │
   │ NOTA: El backend NO tiene concepto de "diner", así que     │
   │ el nombre del comensal se incluye en el campo "notes"      │
   └────────┬────────────────────────────────────────────────────┘
            │
            ▼
7. VER HISTORIAL DE RONDAS (NUEVO - Backend)
   ┌─────────────────────────────────────────────────────────────┐
   │ GET /api/diner/session/{session_id}/rounds                 │
   │ Headers: { X-Table-Token: {table_token} }                  │
   │                                                             │
   │ Mostrar en UI: "Ronda 1", "Ronda 2", etc.                  │
   └────────┬────────────────────────────────────────────────────┘
            │
            ▼
8. LLAMAR AL MOZO (ACTUALIZAR - Backend)
   ┌─────────────────────────────────────────────────────────────┐
   │ POST /api/diner/service-call                               │
   │ Headers: { X-Table-Token: {table_token} }                  │
   │ Body: { type: "WAITER_CALL" | "PAYMENT_HELP" | "OTHER" }   │
   │                                                             │
   │ El mozo recibe notificación via WebSocket                  │
   └────────┬────────────────────────────────────────────────────┘
            │
            ▼
9. PEDIR CUENTA (ACTUALIZAR - Backend)
   ┌─────────────────────────────────────────────────────────────┐
   │ POST /api/billing/check/request                            │
   │ Headers: { X-Table-Token: {table_token} }                  │
   │                                                             │
   │ Response: { check_id, total_cents, paid_cents, status }    │
   │                                                             │
   │ Esto:                                                       │
   │ - Crea el Check en la DB                                   │
   │ - Cambia Table.status a "PAYING"                           │
   │ - Notifica al mozo via WebSocket                           │
   └────────┬────────────────────────────────────────────────────┘
            │
            ▼
10. VER DETALLE DE CUENTA (NUEVO - Backend)
    ┌─────────────────────────────────────────────────────────────┐
    │ GET /api/diner/check                                       │
    │ Headers: { X-Table-Token: {table_token} }                  │
    │                                                             │
    │ Response: {                                                 │
    │   id, status, total_cents, paid_cents, remaining_cents,    │
    │   items: [{ product_name, qty, unit_price_cents, ... }],   │
    │   payments: [{ provider, amount_cents, status, ... }]      │
    │ }                                                           │
    └────────┬────────────────────────────────────────────────────┘
             │
             ▼
11. PAGAR (ACTUALIZAR - Backend)
    ┌─────────────────────────────────────────────────────────────┐
    │ OPCIÓN A - Mercado Pago (Diner lo inicia):                 │
    │ POST /api/billing/mercadopago/preference                   │
    │ Body: { check_id }                                          │
    │ Response: { init_point, sandbox_init_point }               │
    │ → Redirect a MP → Webhook actualiza estado                 │
    │                                                             │
    │ OPCIÓN B - Efectivo (Mozo lo registra):                    │
    │ El diner solo ve "Pago en efectivo pendiente"              │
    │ El mozo usa pwaWaiter para registrar el pago               │
    │                                                             │
    │ División de cuenta:                                         │
    │ - "Pago total": Un comensal paga todo                      │
    │ - "Pago por consumo": Cada uno paga lo suyo (calculado     │
    │   localmente basado en diner_id de los items)              │
    │ - "Pago dividido igual": total / número de comensales      │
    │ - "Pago parcial": Cada uno pone lo que quiere hasta        │
    │   completar la cuenta                                       │
    └────────┬────────────────────────────────────────────────────┘
             │
             ▼
12. CUENTA PAGADA (WebSocket + Backend)
    ┌─────────────────────────────────────────────────────────────┐
    │ WebSocket recibe: CHECK_PAID                               │
    │                                                             │
    │ UI muestra: "¡Gracias por tu visita!"                      │
    │ → leaveTable() limpia estado local                         │
    │ → El mozo libera la mesa desde pwaWaiter                   │
    └─────────────────────────────────────────────────────────────┘
```

### 2.2 Estructura de Stores Propuesta

```typescript
// stores/sessionStore.ts (NUEVO - reemplaza parte de tableStore)
interface SessionState {
  // Backend data
  sessionId: number | null
  tableId: number | null
  tableCode: string | null
  tableToken: string | null
  branchId: number | null
  branchSlug: string | null
  status: 'OPEN' | 'PAYING' | 'CLOSED' | null

  // Check data (from backend)
  checkId: number | null
  checkStatus: 'OPEN' | 'REQUESTED' | 'IN_PAYMENT' | 'PAID' | null
  totalCents: number
  paidCents: number

  // Rounds history (from backend)
  rounds: Round[]

  // WebSocket
  wsConnected: boolean

  // Actions
  createOrJoinSession: (tableId: number) => Promise<void>
  fetchRounds: () => Promise<void>
  requestCheck: () => Promise<void>
  fetchCheckDetail: () => Promise<void>
  disconnect: () => void
}

// stores/cartStore.ts (REFACTORIZADO de tableStore)
interface CartState {
  // Local cart (shared across tabs)
  items: CartItem[]
  currentDiner: Diner | null

  // Actions
  setCurrentDiner: (name: string) => void
  addToCart: (item: AddToCartInput) => void
  updateQuantity: (itemId: string, qty: number) => void
  removeItem: (itemId: string) => void
  clearCart: () => void
  submitOrder: () => Promise<SubmitOrderResult>
}

// stores/menuStore.ts (NUEVO)
interface MenuState {
  categories: Category[]
  products: Product[]
  allergens: Allergen[]
  isLoading: boolean
  error: string | null

  // Actions
  fetchMenu: (branchSlug: string) => Promise<void>
  getProductById: (id: number) => Product | undefined
  getProductsByCategory: (categoryId: number) => Product[]
  getProductsBySubcategory: (subcategoryId: number) => Product[]
}
```

---

## 3. Plan de Implementación por Fases

### Fase 1: Servicio de API y Tipos (2-3 horas)

#### 1.1 Actualizar tipos para coincidir con backend

**Archivo:** `src/types/backend.ts` (NUEVO)

```typescript
// Tipos que coinciden exactamente con los schemas del backend

// Response de POST /api/tables/{table_id}/session
export interface TableSessionResponse {
  session_id: number
  table_id: number
  table_code: string
  table_token: string
  status: 'OPEN' | 'PAYING'
}

// Response de GET /api/public/menu/{slug}
export interface MenuResponse {
  branch_id: number
  branch_name: string
  branch_slug: string
  categories: CategoryAPI[]
}

export interface CategoryAPI {
  id: number
  name: string
  icon: string | null
  image: string | null
  order: number
  subcategories: SubcategoryAPI[]
  products: ProductAPI[]
}

export interface SubcategoryAPI {
  id: number
  name: string
  image: string | null
  order: number
}

export interface ProductAPI {
  id: number
  name: string
  description: string | null
  price_cents: number  // ¡CENTAVOS!
  image: string | null
  category_id: number
  subcategory_id: number | null
  featured: boolean
  popular: boolean
  badge: string | null
  seal: string | null
  allergen_ids: number[]
  is_available: boolean
}

// Request de POST /api/diner/rounds/submit
export interface SubmitRoundRequest {
  items: SubmitRoundItem[]
}

export interface SubmitRoundItem {
  product_id: number
  qty: number
  notes?: string  // Incluir nombre del diner aquí
}

// Response de POST /api/diner/rounds/submit
export interface SubmitRoundResponse {
  session_id: number
  round_id: number
  round_number: number
  status: 'SUBMITTED'
}

// Response de GET /api/diner/session/{id}/rounds
export interface RoundOutput {
  id: number
  round_number: number
  status: 'DRAFT' | 'SUBMITTED' | 'IN_KITCHEN' | 'READY' | 'SERVED' | 'CANCELED'
  items: RoundItemOutput[]
  created_at: string
}

export interface RoundItemOutput {
  id: number
  product_id: number
  product_name: string
  qty: number
  unit_price_cents: number
  notes: string | null
}

// Request de POST /api/diner/service-call
export interface CreateServiceCallRequest {
  type: 'WAITER_CALL' | 'PAYMENT_HELP' | 'OTHER'
}

// Response de POST /api/diner/service-call
export interface ServiceCallOutput {
  id: number
  type: string
  status: 'OPEN' | 'ACKED' | 'CLOSED'
  created_at: string
  acked_by_user_id: number | null
}

// Response de POST /api/billing/check/request
export interface RequestCheckResponse {
  check_id: number
  total_cents: number
  paid_cents: number
  status: 'REQUESTED'
}

// Response de GET /api/diner/check
export interface CheckDetailOutput {
  id: number
  status: 'OPEN' | 'REQUESTED' | 'IN_PAYMENT' | 'PAID'
  total_cents: number
  paid_cents: number
  remaining_cents: number
  items: CheckItemOutput[]
  payments: PaymentOutput[]
  created_at: string
  table_code: string | null
}

export interface CheckItemOutput {
  product_name: string
  qty: number
  unit_price_cents: number
  subtotal_cents: number
  notes: string | null
  round_number: number
}

export interface PaymentOutput {
  id: number
  provider: 'CASH' | 'MERCADO_PAGO'
  status: 'PENDING' | 'APPROVED' | 'REJECTED'
  amount_cents: number
  created_at: string
}

// Response de POST /api/billing/mercadopago/preference
export interface MercadoPagoPreferenceResponse {
  preference_id: string
  init_point: string
  sandbox_init_point: string
}

// WebSocket events
export interface WSEvent {
  type: string
  tenant_id: number
  branch_id: number
  table_id: number
  session_id: number
  entity: Record<string, unknown>
  actor: { user_id: number | null; role: string }
  ts: string
  v: number
}
```

#### 1.2 Actualizar servicio de API

**Archivo:** `src/services/api.ts` (MODIFICAR)

```typescript
// Agregar configuración de table token
let tableToken: string | null = null

export function setTableToken(token: string | null): void {
  tableToken = token
}

export function getTableToken(): string | null {
  return tableToken
}

// Headers helper
function getHeaders(): Record<string, string> {
  const headers: Record<string, string> = {
    'Content-Type': 'application/json',
    'X-Requested-With': 'XMLHttpRequest',
  }
  if (tableToken) {
    headers['X-Table-Token'] = tableToken
  }
  return headers
}

// Session API
export const sessionAPI = {
  async createOrGet(tableId: number): Promise<TableSessionResponse> {
    const response = await fetch(`${API_BASE}/api/tables/${tableId}/session`, {
      method: 'POST',
      headers: getHeaders(),
      credentials: 'include',
    })
    if (!response.ok) throw new ApiError(response)
    return response.json()
  },
}

// Menu API (público, sin auth)
export const menuAPI = {
  async getMenu(branchSlug: string): Promise<MenuResponse> {
    const response = await fetch(`${API_BASE}/api/public/menu/${branchSlug}`, {
      headers: { 'Content-Type': 'application/json' },
    })
    if (!response.ok) throw new ApiError(response)
    return response.json()
  },
}

// Diner API (requiere table token)
export const dinerAPI = {
  async submitRound(items: SubmitRoundItem[]): Promise<SubmitRoundResponse> {
    const response = await fetch(`${API_BASE}/api/diner/rounds/submit`, {
      method: 'POST',
      headers: getHeaders(),
      credentials: 'include',
      body: JSON.stringify({ items }),
    })
    if (!response.ok) throw new ApiError(response)
    return response.json()
  },

  async getRounds(sessionId: number): Promise<RoundOutput[]> {
    const response = await fetch(`${API_BASE}/api/diner/session/${sessionId}/rounds`, {
      headers: getHeaders(),
      credentials: 'include',
    })
    if (!response.ok) throw new ApiError(response)
    return response.json()
  },

  async createServiceCall(type: string): Promise<ServiceCallOutput> {
    const response = await fetch(`${API_BASE}/api/diner/service-call`, {
      method: 'POST',
      headers: getHeaders(),
      credentials: 'include',
      body: JSON.stringify({ type }),
    })
    if (!response.ok) throw new ApiError(response)
    return response.json()
  },

  async getSessionTotal(sessionId: number): Promise<{
    session_id: number
    total_cents: number
    paid_cents: number
    check_id: number | null
    check_status: string | null
  }> {
    const response = await fetch(`${API_BASE}/api/diner/session/${sessionId}/total`, {
      headers: getHeaders(),
      credentials: 'include',
    })
    if (!response.ok) throw new ApiError(response)
    return response.json()
  },

  async getCheck(): Promise<CheckDetailOutput> {
    const response = await fetch(`${API_BASE}/api/diner/check`, {
      headers: getHeaders(),
      credentials: 'include',
    })
    if (!response.ok) throw new ApiError(response)
    return response.json()
  },
}

// Billing API (requiere table token para diners)
export const billingAPI = {
  async requestCheck(): Promise<RequestCheckResponse> {
    const response = await fetch(`${API_BASE}/api/billing/check/request`, {
      method: 'POST',
      headers: getHeaders(),
      credentials: 'include',
    })
    if (!response.ok) throw new ApiError(response)
    return response.json()
  },

  async createMercadoPagoPreference(checkId: number): Promise<MercadoPagoPreferenceResponse> {
    const response = await fetch(`${API_BASE}/api/billing/mercadopago/preference`, {
      method: 'POST',
      headers: getHeaders(),
      credentials: 'include',
      body: JSON.stringify({ check_id: checkId }),
    })
    if (!response.ok) throw new ApiError(response)
    return response.json()
  },
}
```

---

### Fase 2: Servicio WebSocket (1-2 horas)

**Archivo:** `src/services/websocket.ts` (NUEVO)

```typescript
import { getTableToken } from './api'

type EventHandler = (event: WSEvent) => void

class WebSocketService {
  private ws: WebSocket | null = null
  private handlers: Map<string, Set<EventHandler>> = new Map()
  private reconnectAttempts = 0
  private maxReconnectAttempts = 10
  private reconnectDelay = 3000

  connect(): Promise<void> {
    return new Promise((resolve, reject) => {
      const token = getTableToken()
      if (!token) {
        reject(new Error('No table token available'))
        return
      }

      const wsUrl = `${WS_BASE}/ws/diner?table_token=${encodeURIComponent(token)}`
      this.ws = new WebSocket(wsUrl)

      this.ws.onopen = () => {
        this.reconnectAttempts = 0
        resolve()
      }

      this.ws.onmessage = (event) => {
        try {
          const data = JSON.parse(event.data) as WSEvent
          this.emit(data.type, data)
          this.emit('*', data) // Wildcard handler
        } catch (e) {
          console.error('Failed to parse WS message:', e)
        }
      }

      this.ws.onclose = () => {
        this.attemptReconnect()
      }

      this.ws.onerror = (error) => {
        console.error('WebSocket error:', error)
        reject(error)
      }
    })
  }

  private attemptReconnect() {
    if (this.reconnectAttempts >= this.maxReconnectAttempts) {
      console.error('Max reconnect attempts reached')
      return
    }

    this.reconnectAttempts++
    setTimeout(() => {
      this.connect().catch(console.error)
    }, this.reconnectDelay)
  }

  on(eventType: string, handler: EventHandler): () => void {
    if (!this.handlers.has(eventType)) {
      this.handlers.set(eventType, new Set())
    }
    this.handlers.get(eventType)!.add(handler)

    // Return unsubscribe function
    return () => {
      this.handlers.get(eventType)?.delete(handler)
    }
  }

  private emit(eventType: string, event: WSEvent) {
    this.handlers.get(eventType)?.forEach(handler => handler(event))
  }

  disconnect() {
    this.ws?.close()
    this.ws = null
    this.handlers.clear()
  }

  isConnected(): boolean {
    return this.ws?.readyState === WebSocket.OPEN
  }
}

export const wsService = new WebSocketService()
```

---

### Fase 3: Refactorizar tableStore (3-4 horas)

El tableStore actual (677 líneas) se dividirá en:

1. **sessionStore.ts** - Manejo de sesión con backend
2. **cartStore.ts** - Carrito local (simplificado de tableStore)
3. **menuStore.ts** - Datos del menú desde backend

#### 3.1 sessionStore.ts

```typescript
// src/stores/sessionStore.ts
import { create } from 'zustand'
import { persist } from 'zustand/middleware'
import { sessionAPI, dinerAPI, billingAPI, setTableToken } from '../services/api'
import { wsService } from '../services/websocket'
import type { TableSessionResponse, RoundOutput, CheckDetailOutput } from '../types/backend'

interface SessionState {
  // Session data from backend
  sessionId: number | null
  tableId: number | null
  tableCode: string | null
  tableToken: string | null
  branchId: number | null
  status: 'OPEN' | 'PAYING' | 'CLOSED' | null

  // Check data
  check: CheckDetailOutput | null

  // Rounds
  rounds: RoundOutput[]

  // Loading states
  isLoading: boolean
  error: string | null
  wsConnected: boolean

  // Actions
  createOrJoinSession: (tableId: number) => Promise<boolean>
  fetchRounds: () => Promise<void>
  requestCheck: () => Promise<void>
  fetchCheck: () => Promise<void>
  callWaiter: (type: 'WAITER_CALL' | 'PAYMENT_HELP') => Promise<void>
  leaveSession: () => void

  // Internal
  _subscribeToEvents: () => () => void
}

const EMPTY_ROUNDS: RoundOutput[] = []

export const useSessionStore = create<SessionState>()(
  persist(
    (set, get) => ({
      sessionId: null,
      tableId: null,
      tableCode: null,
      tableToken: null,
      branchId: null,
      status: null,
      check: null,
      rounds: EMPTY_ROUNDS,
      isLoading: false,
      error: null,
      wsConnected: false,

      createOrJoinSession: async (tableId: number): Promise<boolean> => {
        set({ isLoading: true, error: null })
        try {
          const response = await sessionAPI.createOrGet(tableId)

          // Store token for API calls
          setTableToken(response.table_token)

          set({
            sessionId: response.session_id,
            tableId: response.table_id,
            tableCode: response.table_code,
            tableToken: response.table_token,
            status: response.status,
            isLoading: false,
          })

          // Connect WebSocket
          try {
            await wsService.connect()
            set({ wsConnected: true })
            get()._subscribeToEvents()
          } catch (wsError) {
            console.error('WebSocket connection failed:', wsError)
            // Continue without WebSocket - will use polling
          }

          // Fetch existing rounds if joining existing session
          await get().fetchRounds()

          return true
        } catch (error) {
          const message = error instanceof Error ? error.message : 'Error al conectar'
          set({ isLoading: false, error: message })
          return false
        }
      },

      fetchRounds: async () => {
        const { sessionId } = get()
        if (!sessionId) return

        try {
          const rounds = await dinerAPI.getRounds(sessionId)
          set({ rounds })
        } catch (error) {
          console.error('Failed to fetch rounds:', error)
        }
      },

      requestCheck: async () => {
        set({ isLoading: true, error: null })
        try {
          await billingAPI.requestCheck()
          set({ status: 'PAYING', isLoading: false })
          await get().fetchCheck()
        } catch (error) {
          const message = error instanceof Error ? error.message : 'Error al pedir cuenta'
          set({ isLoading: false, error: message })
        }
      },

      fetchCheck: async () => {
        try {
          const check = await dinerAPI.getCheck()
          set({ check })
        } catch (error) {
          // No check exists yet - this is normal
          console.debug('No check found')
        }
      },

      callWaiter: async (type) => {
        try {
          await dinerAPI.createServiceCall(type)
        } catch (error) {
          console.error('Failed to call waiter:', error)
          throw error
        }
      },

      leaveSession: () => {
        wsService.disconnect()
        setTableToken(null)
        set({
          sessionId: null,
          tableId: null,
          tableCode: null,
          tableToken: null,
          branchId: null,
          status: null,
          check: null,
          rounds: EMPTY_ROUNDS,
          wsConnected: false,
        })
      },

      _subscribeToEvents: () => {
        const unsubscribe = wsService.on('*', (event) => {
          switch (event.type) {
            case 'ROUND_IN_KITCHEN':
            case 'ROUND_READY':
            case 'ROUND_SERVED':
              // Refetch rounds to get updated status
              get().fetchRounds()
              break
            case 'PAYMENT_APPROVED':
            case 'CHECK_PAID':
              // Refetch check to get updated amounts
              get().fetchCheck()
              if (event.type === 'CHECK_PAID') {
                set({ status: 'PAID' as any })
              }
              break
          }
        })
        return unsubscribe
      },
    }),
    {
      name: 'pwamenu-session',
      partialize: (state) => ({
        sessionId: state.sessionId,
        tableId: state.tableId,
        tableCode: state.tableCode,
        tableToken: state.tableToken,
        status: state.status,
      }),
      onRehydrateStorage: () => (state) => {
        // Restore token on rehydration
        if (state?.tableToken) {
          setTableToken(state.tableToken)
        }
      },
    }
  )
)

// Selectors
export const selectSessionId = (s: SessionState) => s.sessionId
export const selectTableCode = (s: SessionState) => s.tableCode
export const selectSessionStatus = (s: SessionState) => s.status
export const selectRounds = (s: SessionState) => s.rounds
export const selectCheck = (s: SessionState) => s.check
export const selectIsLoading = (s: SessionState) => s.isLoading
export const selectWsConnected = (s: SessionState) => s.wsConnected
```

---

### Fase 4: Actualizar Componentes (4-5 horas)

#### 4.1 JoinTable - Usar backend para crear sesión

```typescript
// src/components/JoinTable/NameStep.tsx
// Cambiar: joinTable() local → createOrJoinSession() del sessionStore

const createOrJoinSession = useSessionStore(s => s.createOrJoinSession)
const setCurrentDiner = useCartStore(s => s.setCurrentDiner)

const handleJoin = async () => {
  // 1. Create/join backend session
  const success = await createOrJoinSession(parseInt(tableNumber, 10))
  if (!success) {
    // Show error
    return
  }

  // 2. Set local diner name (carrito sigue siendo local)
  setCurrentDiner(dinerName || `Comensal ${Date.now()}`)
}
```

#### 4.2 SharedCart - submitOrder al backend

```typescript
// src/components/SharedCart.tsx
// Cambiar: submitOrder() mock → dinerAPI.submitRound()

const submitOrder = async () => {
  const items = cartItems.map(item => ({
    product_id: item.product_id,
    qty: item.quantity,
    notes: item.notes ? `${item.diner_name}: ${item.notes}` : item.diner_name,
  }))

  try {
    const response = await dinerAPI.submitRound(items)
    // Clear local cart
    clearCart()
    // Fetch updated rounds
    fetchRounds()
    // Show success
    setOrderSuccess({ roundNumber: response.round_number })
  } catch (error) {
    setError('Error al enviar pedido')
  }
}
```

#### 4.3 CloseTable - Usar check del backend

```typescript
// src/pages/CloseTable.tsx
// Cambiar: cálculos locales → datos del backend check

const check = useSessionStore(selectCheck)
const requestCheck = useSessionStore(s => s.requestCheck)

// Si no hay check, pedirlo
useEffect(() => {
  if (!check) {
    requestCheck()
  }
}, [])

// Mostrar datos del check
const totalPesos = check ? check.total_cents / 100 : 0
const paidPesos = check ? check.paid_cents / 100 : 0
const remainingPesos = check ? check.remaining_cents / 100 : 0
```

#### 4.4 Home - Cargar menú desde backend

```typescript
// src/pages/Home.tsx
// Cambiar: mockData → menuStore

const fetchMenu = useMenuStore(s => s.fetchMenu)
const categories = useMenuStore(s => s.categories)
const branchSlug = useSessionStore(selectBranchSlug) || 'centro'

useEffect(() => {
  fetchMenu(branchSlug)
}, [branchSlug])
```

---

### Fase 5: Manejo de División de Cuenta (2-3 horas)

El backend NO tiene concepto de "diner" - solo sabe de `RoundItem` con `notes`. La división de cuenta se calcula localmente basándose en los `notes` que contienen el nombre del comensal.

```typescript
// src/utils/billSplit.ts

interface DinerConsumption {
  dinerName: string
  items: { name: string; qty: number; subtotalCents: number }[]
  totalCents: number
}

export function calculateByConsumption(
  checkItems: CheckItemOutput[],
  diners: string[]
): Map<string, DinerConsumption> {
  const consumption = new Map<string, DinerConsumption>()

  // Initialize for each diner
  diners.forEach(name => {
    consumption.set(name, { dinerName: name, items: [], totalCents: 0 })
  })

  // Parse notes to extract diner name
  checkItems.forEach(item => {
    // Notes format: "DinerName: actual note" or just "DinerName"
    const dinerName = item.notes?.split(':')[0]?.trim() || 'Desconocido'

    const dinerData = consumption.get(dinerName) || {
      dinerName,
      items: [],
      totalCents: 0,
    }

    dinerData.items.push({
      name: item.product_name,
      qty: item.qty,
      subtotalCents: item.subtotal_cents,
    })
    dinerData.totalCents += item.subtotal_cents

    consumption.set(dinerName, dinerData)
  })

  return consumption
}

export function calculateEqualSplit(
  totalCents: number,
  numberOfDiners: number
): number {
  return Math.ceil(totalCents / numberOfDiners)
}
```

---

## 4. Mapeo de Variables: Frontend ↔ Backend

### 4.1 Nombres que DEBEN coincidir con backend

| Frontend Variable | Backend Field | Notas |
|-------------------|---------------|-------|
| `sessionId` | `session_id` | Usar `number`, no `string` |
| `tableId` | `table_id` | Usar `number` |
| `tableCode` | `table_code` o `code` | String del código de mesa (ej: "M-01") |
| `tableToken` | `table_token` | JWT para X-Table-Token header |
| `branchId` | `branch_id` | Usar `number` |
| `branchSlug` | `branch_slug` | String URL-safe (ej: "centro") |
| `productId` | `product_id` | Usar `number` |
| `categoryId` | `category_id` | Usar `number` |
| `subcategoryId` | `subcategory_id` | Usar `number` |
| `priceCents` | `price_cents` | Siempre en centavos |
| `roundNumber` | `round_number` | Número secuencial de ronda |
| `checkId` | `check_id` | ID del check/cuenta |
| `checkStatus` | `status` en Check | OPEN/REQUESTED/IN_PAYMENT/PAID |
| `roundStatus` | `status` en Round | DRAFT/SUBMITTED/IN_KITCHEN/READY/SERVED/CANCELED |
| `paymentProvider` | `provider` | CASH o MERCADO_PAGO |

### 4.2 Conversiones Obligatorias

```typescript
// Precios: Backend (cents) ↔ Frontend (pesos)
const pricePesos = priceCents / 100
const priceCents = Math.round(pricePesos * 100)

// IDs: Backend (number) ↔ Frontend display (string)
const displayId = String(backendId)
const backendId = parseInt(frontendId, 10)

// Timestamps: Backend (ISO string) ↔ Frontend (Date)
const date = new Date(backendTimestamp)
const isoString = date.toISOString()
```

### 4.3 Campos que NO existen en backend

| Frontend Only | Propósito | Manejo |
|---------------|-----------|--------|
| `diner_id` | Identificar comensal local | UUID generado en frontend |
| `diner_name` | Nombre del comensal | Se incluye en `notes` del RoundItem |
| `avatar_color` | Color para UI | Solo frontend |
| `CartItem.id` | Identificar item en carrito | UUID local |
| `optimisticId` | Para optimistic updates | Solo React state |

---

## 5. Checklist de Migración

### Fase 1: Tipos y API
- [ ] Crear `src/types/backend.ts` con todos los tipos del backend
- [ ] Actualizar `src/services/api.ts` con nuevos endpoints
- [ ] Agregar manejo de `X-Table-Token` header
- [ ] Agregar funciones de conversión cents ↔ pesos

### Fase 2: WebSocket
- [ ] Crear `src/services/websocket.ts`
- [ ] Implementar reconexión automática
- [ ] Implementar handlers para eventos del backend

### Fase 3: Stores
- [ ] Crear `src/stores/sessionStore.ts`
- [ ] Crear `src/stores/menuStore.ts`
- [ ] Refactorizar `src/stores/tableStore/` → `src/stores/cartStore.ts`
- [ ] Mantener compatibilidad con multi-tab sync

### Fase 4: Componentes
- [ ] Actualizar `JoinTable` para crear sesión en backend
- [ ] Actualizar `Home` para cargar menú desde backend
- [ ] Actualizar `SharedCart` para enviar órdenes al backend
- [ ] Actualizar `ProductDetailModal` para usar precios en centavos
- [ ] Actualizar `CloseTable` para usar check del backend
- [ ] Actualizar `CallWaiterModal` para usar service-call API

### Fase 5: División de cuenta
- [ ] Implementar `calculateByConsumption` basado en notes
- [ ] Implementar UI de selección de método de pago
- [ ] Integrar Mercado Pago real (no mock)

### Fase 6: Testing
- [ ] Probar flujo completo: QR → orden → cuenta → pago
- [ ] Probar multi-diner en misma mesa
- [ ] Probar WebSocket events
- [ ] Probar reconexión después de desconexión
- [ ] Probar pago con Mercado Pago (sandbox)

---

## 6. Riesgos y Mitigaciones

| Riesgo | Impacto | Mitigación |
|--------|---------|------------|
| WebSocket no disponible | Alto | Implementar polling como fallback |
| Backend offline | Alto | Mostrar error claro, permitir reintentos |
| Token expirado | Medio | Detectar 401 y pedir nueva sesión |
| Conflicto multi-tab | Medio | Mantener localStorage sync para carrito |
| Mercado Pago falla | Medio | Ofrecer opción de pago en efectivo |
| Precios desincronizados | Alto | Siempre usar precio del backend al enviar orden |

---

## 7. Orden de Implementación Recomendado

1. **Primero**: Tipos + API (no rompe nada existente)
2. **Segundo**: menuStore (reemplaza mockData gradualmente)
3. **Tercero**: sessionStore (el cambio más grande)
4. **Cuarto**: WebSocket (mejora UX)
5. **Quinto**: Actualizar componentes uno por uno
6. **Último**: Remover mockData.ts y código legacy

---

## 8. Variables de Entorno Requeridas

```env
# .env.local para pwaMenu
VITE_API_URL=http://localhost:8000
VITE_WS_URL=ws://localhost:8001
VITE_DEFAULT_BRANCH_SLUG=centro
```

---

## Conclusión

La migración de pwaMenu de mocks a backend real es un proceso de **6 fases** que puede completarse en aproximadamente **15-20 horas de desarrollo**. El mayor riesgo está en la fase 3 (refactorización de stores) donde se debe mantener compatibilidad con el carrito local mientras se integra la sesión del backend.

La clave del éxito es mantener el carrito como concepto puramente local (multi-diner UX) mientras se sincroniza la sesión y las órdenes con el backend. El campo `notes` de RoundItem es el puente para asociar items con comensales específicos.
