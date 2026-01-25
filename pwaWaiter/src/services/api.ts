import { apiLogger } from '../utils/logger'
import { API_CONFIG } from '../utils/constants'
import type {
  LoginResponse,
  User,
  TableCard,
  TableSessionDetail,
  Round,
  RoundStatus,
  Check,
  ServiceCall,
} from '../types'

// =============================================================================
// AUDIT FIX: SSRF Protection (copied from pwaMenu)
// =============================================================================

// Use centralized config for SSRF prevention (single source of truth)
// IMPORTANT: Only allow exactly these hosts, not subdomains
const ALLOWED_HOSTS = new Set<string>(API_CONFIG.ALLOWED_HOSTS)
const ALLOWED_PORTS = new Set<string>(API_CONFIG.ALLOWED_PORTS)

// Validate that the base URL is secure
function isValidApiBase(url: string): boolean {
  try {
    // Relative URLs are always valid (same-origin)
    if (url.startsWith('/') && !url.startsWith('//')) return true

    const parsed = new URL(url)

    // Only allow http/https
    if (!['http:', 'https:'].includes(parsed.protocol)) return false

    // SECURITY: Prevent SSRF via IP addresses (IPv4 and IPv6)
    const ipv4Regex = /^(\d{1,3}\.){3}\d{1,3}$/
    const ipv6Regex = /^([0-9a-f]{0,4}:){2,7}[0-9a-f]{0,4}$/i

    // In production, block direct IP access (except explicit localhost)
    if (import.meta.env.PROD) {
      if (ipv4Regex.test(parsed.hostname) && parsed.hostname !== '127.0.0.1') {
        apiLogger.warn('Direct IPv4 access blocked in production:', parsed.hostname)
        return false
      }
      if (ipv6Regex.test(parsed.hostname) && parsed.hostname !== '::1') {
        apiLogger.warn('Direct IPv6 access blocked in production:', parsed.hostname)
        return false
      }
    }

    // Check if hostname is in allowed list (exact match only, no subdomains)
    const isAllowedHost = ALLOWED_HOSTS.has(parsed.hostname)

    // Get port (default to standard ports if not specified)
    const normalizedPort = parsed.port || (parsed.protocol === 'https:' ? '443' : '80')
    const isAllowedPort = ALLOWED_PORTS.has(normalizedPort)

    // For allowed hosts, also check port to prevent SSRF via port
    if (isAllowedHost && !isAllowedPort) {
      apiLogger.warn(`Port ${normalizedPort} not in allowed list for ${parsed.hostname}`)
      return false
    }

    return isAllowedHost
  } catch {
    return false
  }
}

// Validate API_BASE at startup - strict in production
const API_BASE = API_CONFIG.BASE_URL
if (!isValidApiBase(API_BASE)) {
  if (import.meta.env.DEV) {
    apiLogger.warn('API_BASE is not a valid or secure URL:', API_BASE)
  } else {
    // In production, throw to prevent potential SSRF attacks
    throw new Error(`Invalid API_BASE configuration. Requests blocked for security.`)
  }
}

// =============================================================================
// End SSRF Protection
// =============================================================================

// API Error class
export class ApiError extends Error {
  constructor(
    message: string,
    public status: number,
    public code?: string
  ) {
    super(message)
    this.name = 'ApiError'
  }
}

// Token storage
let authToken: string | null = null
let refreshToken: string | null = null

// DEF-HIGH-04 FIX: Token refresh callback
let tokenRefreshCallback: ((newToken: string) => void) | null = null

// HIGH-07 FIX: Token change listeners for synchronization between api.ts and websocket.ts
type TokenChangeListener = (token: string | null) => void
const tokenChangeListeners: Set<TokenChangeListener> = new Set()

export function onTokenChange(listener: TokenChangeListener): () => void {
  tokenChangeListeners.add(listener)
  return () => tokenChangeListeners.delete(listener)
}

export function setAuthToken(token: string | null): void {
  authToken = token
  // HIGH-07 FIX: Notify all listeners when token changes
  tokenChangeListeners.forEach((listener) => listener(token))
}

export function getAuthToken(): string | null {
  return authToken
}

// DEF-HIGH-04 FIX: Refresh token management
export function setRefreshToken(token: string | null): void {
  refreshToken = token
}

export function getRefreshToken(): string | null {
  return refreshToken
}

export function setTokenRefreshCallback(callback: ((newToken: string) => void) | null): void {
  tokenRefreshCallback = callback
}

// WAITER-SVC-MED-01: Request options with optional abort signal
interface RequestOptions extends Omit<RequestInit, 'signal'> {
  /** Optional external AbortController signal for cancellation */
  signal?: AbortSignal
  /** Custom timeout in ms (overrides API_CONFIG.TIMEOUT) */
  timeout?: number
}

// Request helper
// WAITER-SVC-MED-01: Added AbortController support for fetch requests with timeout
async function request<T>(
  endpoint: string,
  options: RequestOptions = {}
): Promise<T> {
  const url = `${API_CONFIG.BASE_URL}${endpoint}`
  const { signal: externalSignal, timeout = API_CONFIG.TIMEOUT, ...restOptions } = options

  const headers: Record<string, string> = {
    'Content-Type': 'application/json',
    ...((restOptions.headers as Record<string, string>) || {}),
  }

  if (authToken) {
    headers['Authorization'] = `Bearer ${authToken}`
  }

  // WAITER-SVC-MED-01: Create internal abort controller for timeout
  const controller = new AbortController()
  const timeoutId = setTimeout(() => controller.abort(), timeout)

  // WAITER-SVC-MED-01: Combine external signal with internal timeout signal
  const combinedSignal = externalSignal
    ? combineAbortSignals(externalSignal, controller.signal)
    : controller.signal

  try {
    const response = await fetch(url, {
      ...restOptions,
      headers,
      credentials: 'include',
      signal: combinedSignal,
    })

    clearTimeout(timeoutId)

    if (!response.ok) {
      const error = await response.json().catch(() => ({}))
      throw new ApiError(
        error.detail || `HTTP ${response.status}`,
        response.status,
        error.code
      )
    }

    if (response.status === 204) {
      return {} as T
    }

    const text = await response.text()
    if (!text) {
      return {} as T
    }

    return JSON.parse(text) as T
  } catch (error) {
    clearTimeout(timeoutId)

    if (error instanceof ApiError) {
      throw error
    }

    if (error instanceof DOMException && error.name === 'AbortError') {
      // WAITER-SVC-MED-01: Distinguish between timeout and user cancellation
      if (externalSignal?.aborted) {
        throw new ApiError('Request cancelled', 0, 'CANCELLED')
      }
      throw new ApiError('Request timeout', 0, 'TIMEOUT')
    }

    if (error instanceof TypeError) {
      throw new ApiError('Network error', 0, 'NETWORK_ERROR')
    }

    apiLogger.error('API request failed', error)
    throw new ApiError('Unknown error', 500, 'UNKNOWN')
  }
}

/**
 * WAITER-SVC-MED-01: Combine multiple abort signals into one
 * If any signal aborts, the combined signal will abort
 */
function combineAbortSignals(...signals: AbortSignal[]): AbortSignal {
  const controller = new AbortController()

  for (const signal of signals) {
    if (signal.aborted) {
      controller.abort(signal.reason)
      break
    }
    signal.addEventListener('abort', () => controller.abort(signal.reason), { once: true })
  }

  return controller.signal
}

// DEF-HIGH-04 FIX: Refresh token response type
interface RefreshResponse {
  access_token: string
  refresh_token?: string
  token_type: string
}

// Auth API
export const authAPI = {
  async login(email: string, password: string): Promise<LoginResponse> {
    const response = await request<LoginResponse & { refresh_token?: string }>('/auth/login', {
      method: 'POST',
      body: JSON.stringify({ email, password }),
    })

    // Store token after successful login
    setAuthToken(response.access_token)

    // DEF-HIGH-04 FIX: Store refresh token if provided
    if (response.refresh_token) {
      setRefreshToken(response.refresh_token)
    }

    return response
  },

  async getMe(): Promise<User> {
    return request<User>('/auth/me')
  },

  // DEF-HIGH-04 FIX: Refresh access token
  async refresh(): Promise<RefreshResponse | null> {
    const currentRefreshToken = getRefreshToken()
    if (!currentRefreshToken) {
      apiLogger.warn('No refresh token available')
      return null
    }

    try {
      const response = await request<RefreshResponse>('/auth/refresh', {
        method: 'POST',
        body: JSON.stringify({ refresh_token: currentRefreshToken }),
      })

      // Update tokens
      setAuthToken(response.access_token)
      if (response.refresh_token) {
        setRefreshToken(response.refresh_token)
      }

      // Notify callback (e.g., WebSocket service)
      if (tokenRefreshCallback) {
        tokenRefreshCallback(response.access_token)
      }

      apiLogger.info('Token refreshed successfully')
      return response
    } catch (err) {
      apiLogger.error('Token refresh failed', err)
      return null
    }
  },

  logout(): void {
    setAuthToken(null)
    setRefreshToken(null)
  },
}

// Tables API
export const tablesAPI = {
  async getTables(branchId: number): Promise<TableCard[]> {
    // The endpoint returns an array directly, not wrapped in { tables: ... }
    return request<TableCard[]>(`/waiter/tables?branch_id=${branchId}`)
  },

  async getTable(tableId: number): Promise<TableCard> {
    return request<TableCard>(`/tables/${tableId}`)
  },

  async getTableSessionDetail(tableId: number): Promise<TableSessionDetail> {
    return request<TableSessionDetail>(`/waiter/tables/${tableId}/session`)
  },
}

// Rounds API
export const roundsAPI = {
  async getRound(roundId: number): Promise<Round> {
    return request<Round>(`/kitchen/rounds/${roundId}`)
  },

  async updateStatus(roundId: number, status: RoundStatus): Promise<Round> {
    return request<Round>(`/kitchen/rounds/${roundId}/status`, {
      method: 'PUT',
      body: JSON.stringify({ status }),
    })
  },

  async markAsServed(roundId: number): Promise<Round> {
    return request<Round>(`/kitchen/rounds/${roundId}/status`, {
      method: 'PUT',
      body: JSON.stringify({ status: 'SERVED' }),
    })
  },
}

// Billing API
export const billingAPI = {
  async confirmCashPayment(checkId: number, amountCents: number): Promise<Check> {
    return request<Check>('/billing/cash/pay', {
      method: 'POST',
      body: JSON.stringify({ check_id: checkId, amount_cents: amountCents }),
    })
  },

  async clearTable(tableId: number): Promise<void> {
    await request(`/billing/tables/${tableId}/clear`, {
      method: 'POST',
    })
  },
}

// Service calls API
export const serviceCallsAPI = {
  async acknowledge(serviceCallId: number): Promise<ServiceCall> {
    return request<ServiceCall>(
      `/waiter/service-calls/${serviceCallId}/acknowledge`,
      {
        method: 'POST',
      }
    )
  },

  async resolve(serviceCallId: number): Promise<ServiceCall> {
    return request<ServiceCall>(
      `/waiter/service-calls/${serviceCallId}/resolve`,
      {
        method: 'POST',
      }
    )
  },
}

// =============================================================================
// HU-WAITER-MESA: Waiter-Managed Table Flow API
// =============================================================================

// Types for waiter-managed flow
export interface WaiterActivateTableRequest {
  diner_count: number
  notes?: string
}

export interface WaiterActivateTableResponse {
  session_id: number
  table_id: number
  table_code: string
  status: string
  opened_at: string
  opened_by: 'DINER' | 'WAITER'
  opened_by_waiter_id: number
  diner_count: number
}

export interface WaiterRoundItem {
  product_id: number
  qty: number
  notes?: string
  diner_index?: number
}

export interface WaiterSubmitRoundRequest {
  items: WaiterRoundItem[]
  notes?: string
}

export interface WaiterSubmitRoundResponse {
  session_id: number
  round_id: number
  round_number: number
  status: string
  submitted_by: 'DINER' | 'WAITER'
  submitted_by_waiter_id: number
  items_count: number
  total_cents: number
}

export interface WaiterRequestCheckResponse {
  check_id: number
  session_id: number
  total_cents: number
  paid_cents: number
  status: string
  items_count: number
}

export type ManualPaymentMethod = 'CASH' | 'CARD_PHYSICAL' | 'TRANSFER_EXTERNAL' | 'OTHER_MANUAL'

export interface ManualPaymentRequest {
  check_id: number
  amount_cents: number
  manual_method: ManualPaymentMethod
  notes?: string
}

export interface ManualPaymentResponse {
  payment_id: number
  check_id: number
  amount_cents: number
  manual_method: ManualPaymentMethod
  status: string
  payment_category: 'DIGITAL' | 'MANUAL'
  registered_by: 'SYSTEM' | 'DINER' | 'WAITER'
  registered_by_waiter_id: number
  check_status: string
  check_total_cents: number
  check_paid_cents: number
  check_remaining_cents: number
}

export interface WaiterCloseTableRequest {
  force?: boolean
}

export interface WaiterCloseTableResponse {
  table_id: number
  table_code: string
  table_status: string
  session_id: number
  session_status: string
  total_cents: number
  paid_cents: number
  closed_at: string
}

export interface WaiterSessionSummary {
  session_id: number
  table_id: number
  table_code: string
  status: string
  opened_at: string
  opened_by: 'DINER' | 'WAITER'
  opened_by_waiter_id?: number
  assigned_waiter_id?: number
  diner_count: number
  rounds_count: number
  total_cents: number
  paid_cents: number
  check_status?: string
  is_hybrid: boolean
}

// Waiter-managed table flow API
export const waiterTableAPI = {
  /**
   * HU-WAITER-MESA CA-01: Activate a table manually
   */
  async activateTable(
    tableId: number,
    data: WaiterActivateTableRequest
  ): Promise<WaiterActivateTableResponse> {
    return request<WaiterActivateTableResponse>(
      `/waiter/tables/${tableId}/activate`,
      {
        method: 'POST',
        body: JSON.stringify(data),
      }
    )
  },

  /**
   * HU-WAITER-MESA CA-03: Submit a round of orders
   */
  async submitRound(
    sessionId: number,
    data: WaiterSubmitRoundRequest
  ): Promise<WaiterSubmitRoundResponse> {
    return request<WaiterSubmitRoundResponse>(
      `/waiter/sessions/${sessionId}/rounds`,
      {
        method: 'POST',
        body: JSON.stringify(data),
      }
    )
  },

  /**
   * HU-WAITER-MESA CA-05: Request the check for a session
   */
  async requestCheck(sessionId: number): Promise<WaiterRequestCheckResponse> {
    return request<WaiterRequestCheckResponse>(
      `/waiter/sessions/${sessionId}/check`,
      {
        method: 'POST',
      }
    )
  },

  /**
   * HU-WAITER-MESA CA-06: Register a manual payment (NO Mercado Pago)
   */
  async registerManualPayment(
    data: ManualPaymentRequest
  ): Promise<ManualPaymentResponse> {
    return request<ManualPaymentResponse>('/waiter/payments/manual', {
      method: 'POST',
      body: JSON.stringify(data),
    })
  },

  /**
   * HU-WAITER-MESA CA-07: Close a table after payment
   */
  async closeTable(
    tableId: number,
    data?: WaiterCloseTableRequest
  ): Promise<WaiterCloseTableResponse> {
    return request<WaiterCloseTableResponse>(`/waiter/tables/${tableId}/close`, {
      method: 'POST',
      body: JSON.stringify(data || {}),
    })
  },

  /**
   * HU-WAITER-MESA CA-09: Get session summary
   */
  async getSessionSummary(sessionId: number): Promise<WaiterSessionSummary> {
    return request<WaiterSessionSummary>(
      `/waiter/sessions/${sessionId}/summary`
    )
  },
}

// =============================================================================
// HU-WAITER-MESA: Menu/Catalog types for waiter order taking
// =============================================================================

export interface MenuProduct {
  id: number
  name: string
  description: string | null
  price_cents: number
  image: string | null
  category_id: number
  subcategory_id: number | null
  featured: boolean
  popular: boolean
  badge: string | null
  seal: string | null
  is_available: boolean
}

export interface MenuSubcategory {
  id: number
  name: string
  image: string | null
  order: number
}

export interface MenuCategory {
  id: number
  name: string
  icon: string | null
  image: string | null
  order: number
  subcategories: MenuSubcategory[]
  products: MenuProduct[]
}

export interface MenuOutput {
  branch_id: number
  branch_name: string
  branch_slug: string
  categories: MenuCategory[]
}

// HU-WAITER-MESA: Branch info type
export interface BranchInfo {
  id: number
  tenant_id: number
  name: string
  slug: string
  address: string | null
  phone: string | null
  timezone: string
  opening_time: string | null
  closing_time: string | null
  is_active: boolean
}

// HU-WAITER-MESA: Menu API for waiter to browse products
export const menuAPI = {
  /**
   * Get the complete menu for a branch by slug.
   * Uses the public catalog endpoint.
   */
  async getMenuBySlug(branchSlug: string): Promise<MenuOutput> {
    return request<MenuOutput>(`/public/menu/${branchSlug}`)
  },
}

// HU-WAITER-MESA: Branch API to get branch details (including slug)
export const branchAPI = {
  /**
   * Get branch details by ID.
   * Used to get the slug for fetching the menu.
   */
  async getBranch(branchId: number): Promise<BranchInfo> {
    return request<BranchInfo>(`/admin/branches/${branchId}`)
  },
}

// =============================================================================
// COMANDA RÁPIDA: Compact menu types for waiter quick ordering
// =============================================================================

export interface ProductCompact {
  id: number
  name: string
  description: string | null
  price_cents: number
  category_id: number
  category_name: string
  subcategory_id: number | null
  subcategory_name: string | null
  allergen_icons: string[]
  is_available: boolean
}

export interface CategoryCompact {
  id: number
  name: string
  products: ProductCompact[]
}

export interface MenuCompact {
  branch_id: number
  branch_name: string
  categories: CategoryCompact[]
  total_products: number
}

// COMANDA RÁPIDA: API for waiter quick ordering without images
export const comandaAPI = {
  /**
   * Get compact menu for quick order taking (no images).
   * Optimized for speed and low bandwidth.
   */
  async getMenuCompact(branchId: number): Promise<MenuCompact> {
    return request<MenuCompact>(`/waiter/branches/${branchId}/menu`)
  },
}
