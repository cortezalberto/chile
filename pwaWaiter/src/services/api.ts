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

export function setAuthToken(token: string | null): void {
  authToken = token
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

// Request helper
async function request<T>(
  endpoint: string,
  options: RequestInit = {}
): Promise<T> {
  const url = `${API_CONFIG.BASE_URL}${endpoint}`

  const headers: Record<string, string> = {
    'Content-Type': 'application/json',
    ...((options.headers as Record<string, string>) || {}),
  }

  if (authToken) {
    headers['Authorization'] = `Bearer ${authToken}`
  }

  const controller = new AbortController()
  const timeoutId = setTimeout(() => controller.abort(), API_CONFIG.TIMEOUT)

  try {
    const response = await fetch(url, {
      ...options,
      headers,
      credentials: 'include',
      signal: controller.signal,
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
      throw new ApiError('Request timeout', 0, 'TIMEOUT')
    }

    if (error instanceof TypeError) {
      throw new ApiError('Network error', 0, 'NETWORK_ERROR')
    }

    apiLogger.error('API request failed', error)
    throw new ApiError('Unknown error', 500, 'UNKNOWN')
  }
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
