import { wsLogger } from '../utils/logger'
import { API_CONFIG, WS_CONFIG } from '../utils/constants'
import type { WSEvent, WSEventType } from '../types'

type EventCallback = (event: WSEvent) => void
type ConnectionStateCallback = (isConnected: boolean) => void
type TokenRefreshCallback = () => Promise<string | null>

class WebSocketService {
  private ws: WebSocket | null = null
  private token: string | null = null
  private tokenExp: number | null = null // PWAW-A001: Token expiration timestamp
  private tokenRefreshTimeout: ReturnType<typeof setTimeout> | null = null
  private tokenRefreshCallback: TokenRefreshCallback | null = null
  private reconnectAttempts = 0
  private reconnectTimeout: ReturnType<typeof setTimeout> | null = null
  private heartbeatInterval: ReturnType<typeof setInterval> | null = null
  private listeners: Map<WSEventType | '*', Set<EventCallback>> = new Map()
  private connectionStateListeners: Set<ConnectionStateCallback> = new Set()
  private connectionPromise: Promise<void> | null = null
  private isIntentionalClose = false

  /**
   * PWAW-A001: Set callback for token refresh
   */
  setTokenRefreshCallback(callback: TokenRefreshCallback): void {
    this.tokenRefreshCallback = callback
  }

  /**
   * Connect to WebSocket server
   */
  connect(token: string): Promise<void> {
    if (this.connectionPromise && this.token === token) {
      return this.connectionPromise
    }

    this.token = token
    this.isIntentionalClose = false

    // PWAW-A001: Parse token to get expiration
    this.parseTokenExpiration(token)

    this.connectionPromise = new Promise((resolve, reject) => {
      const wsUrl = `${API_CONFIG.WS_URL}/ws/waiter?token=${token}`

      wsLogger.info('Connecting to WebSocket', { url: API_CONFIG.WS_URL })

      try {
        this.ws = new WebSocket(wsUrl)

        this.ws.onopen = () => {
          wsLogger.info('WebSocket connected')
          this.reconnectAttempts = 0
          this.startHeartbeat()
          this.scheduleTokenRefresh() // PWAW-A001
          this.notifyConnectionState(true)
          resolve()
        }

        this.ws.onmessage = (event) => {
          this.handleMessage(event)
        }

        this.ws.onerror = (error) => {
          wsLogger.error('WebSocket error', error)
          reject(new Error('WebSocket connection failed'))
        }

        this.ws.onclose = (event) => {
          wsLogger.info('WebSocket closed', { code: event.code, reason: event.reason })
          this.stopHeartbeat()
          this.notifyConnectionState(false)

          if (!this.isIntentionalClose) {
            this.scheduleReconnect()
          }
        }
      } catch (error) {
        wsLogger.error('Failed to create WebSocket', error)
        reject(error)
      }
    })

    return this.connectionPromise
  }

  /**
   * Disconnect from WebSocket server
   */
  disconnect(): void {
    this.isIntentionalClose = true
    this.stopHeartbeat()
    this.clearTokenRefreshTimeout() // PWAW-A001

    if (this.reconnectTimeout) {
      clearTimeout(this.reconnectTimeout)
      this.reconnectTimeout = null
    }

    if (this.ws) {
      this.ws.close(1000, 'Client disconnect')
      this.ws = null
    }

    this.token = null
    this.tokenExp = null
    this.connectionPromise = null
    this.reconnectAttempts = 0

    wsLogger.info('Disconnected from WebSocket')
  }

  /**
   * Subscribe to specific event type or all events ('*')
   */
  on(eventType: WSEventType | '*', callback: EventCallback): () => void {
    if (!this.listeners.has(eventType)) {
      this.listeners.set(eventType, new Set())
    }

    this.listeners.get(eventType)!.add(callback)

    // Return unsubscribe function
    return () => {
      this.listeners.get(eventType)?.delete(callback)
    }
  }

  /**
   * Check if connected
   */
  isConnected(): boolean {
    return this.ws?.readyState === WebSocket.OPEN
  }

  /**
   * DEF-HIGH-04 FIX: Update token and reconnect with new token
   */
  updateToken(newToken: string): void {
    wsLogger.info('Updating WebSocket token')
    this.token = newToken
    this.parseTokenExpiration(newToken)

    // Reconnect with new token
    if (this.isConnected()) {
      this.isIntentionalClose = true
      this.ws?.close(1000, 'Token refresh')
      this.isIntentionalClose = false
      this.connect(newToken).catch((err) => {
        wsLogger.error('Failed to reconnect with new token', err)
      })
    }
  }

  /**
   * Subscribe to connection state changes
   * Returns unsubscribe function
   */
  onConnectionChange(callback: ConnectionStateCallback): () => void {
    this.connectionStateListeners.add(callback)

    // Immediately notify current state
    callback(this.isConnected())

    return () => {
      this.connectionStateListeners.delete(callback)
    }
  }

  private notifyConnectionState(isConnected: boolean): void {
    this.connectionStateListeners.forEach((cb) => cb(isConnected))
  }

  private handleMessage(event: MessageEvent): void {
    try {
      const data = JSON.parse(event.data) as WSEvent
      wsLogger.debug('Received event', { type: data.type, table_id: data.table_id })

      // Notify specific listeners
      this.listeners.get(data.type)?.forEach((cb) => cb(data))

      // Notify wildcard listeners
      this.listeners.get('*')?.forEach((cb) => cb(data))
    } catch (error) {
      wsLogger.error('Failed to parse WebSocket message', error)
    }
  }

  private startHeartbeat(): void {
    this.stopHeartbeat()

    this.heartbeatInterval = setInterval(() => {
      if (this.ws?.readyState === WebSocket.OPEN) {
        this.ws.send(JSON.stringify({ type: 'ping' }))
      }
    }, WS_CONFIG.HEARTBEAT_INTERVAL)
  }

  private stopHeartbeat(): void {
    if (this.heartbeatInterval) {
      clearInterval(this.heartbeatInterval)
      this.heartbeatInterval = null
    }
  }

  private scheduleReconnect(): void {
    if (this.reconnectAttempts >= WS_CONFIG.MAX_RECONNECT_ATTEMPTS) {
      wsLogger.warn('Max reconnect attempts reached')
      return
    }

    this.reconnectAttempts++
    const delay = WS_CONFIG.RECONNECT_INTERVAL * this.reconnectAttempts

    wsLogger.info(`Scheduling reconnect in ${delay}ms`, {
      attempt: this.reconnectAttempts,
    })

    this.reconnectTimeout = setTimeout(() => {
      if (this.token && !this.isIntentionalClose) {
        this.connectionPromise = null
        this.connect(this.token).catch((error) => {
          wsLogger.error('Reconnect failed', error)
        })
      }
    }, delay)
  }

  // =============================================================================
  // PWAW-A001: Token Refresh Mechanism
  // =============================================================================

  /**
   * Parse JWT token to extract expiration time
   */
  private parseTokenExpiration(token: string): void {
    try {
      const parts = token.split('.')
      if (parts.length !== 3) return

      const payload = JSON.parse(atob(parts[1]))
      if (payload.exp) {
        this.tokenExp = payload.exp
        wsLogger.debug('Token expires at', { exp: new Date(payload.exp * 1000).toISOString() })
      }
    } catch (error) {
      wsLogger.warn('Failed to parse token expiration', error)
    }
  }

  /**
   * Schedule token refresh before expiration
   */
  private scheduleTokenRefresh(): void {
    this.clearTokenRefreshTimeout()

    if (!this.tokenExp || !this.tokenRefreshCallback) return

    const now = Date.now() / 1000
    const expiresIn = this.tokenExp - now
    const refreshIn = Math.max(0, (expiresIn - 60) * 1000) // Refresh 1 minute before expiry

    if (refreshIn <= 0) {
      // Token already expired or about to expire
      wsLogger.warn('Token expired or expiring soon, triggering refresh')
      this.handleTokenRefresh()
      return
    }

    wsLogger.debug(`Scheduling token refresh in ${Math.round(refreshIn / 1000)}s`)

    this.tokenRefreshTimeout = setTimeout(() => {
      this.handleTokenRefresh()
    }, refreshIn)
  }

  /**
   * Handle token refresh
   */
  private async handleTokenRefresh(): Promise<void> {
    if (!this.tokenRefreshCallback) return

    wsLogger.info('Refreshing WebSocket token')

    try {
      const newToken = await this.tokenRefreshCallback()
      if (newToken && !this.isIntentionalClose) {
        // Reconnect with new token
        this.disconnect()
        this.isIntentionalClose = false
        await this.connect(newToken)
        wsLogger.info('WebSocket reconnected with refreshed token')
      }
    } catch (error) {
      wsLogger.error('Token refresh failed', error)
    }
  }

  /**
   * Clear token refresh timeout
   */
  private clearTokenRefreshTimeout(): void {
    if (this.tokenRefreshTimeout) {
      clearTimeout(this.tokenRefreshTimeout)
      this.tokenRefreshTimeout = null
    }
  }
}

// Singleton instance
export const wsService = new WebSocketService()
