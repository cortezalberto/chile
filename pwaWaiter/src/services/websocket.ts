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
  // WS-31-HIGH-01 FIX: Add heartbeat timeout detection
  private heartbeatTimeout: ReturnType<typeof setTimeout> | null = null
  private lastPongReceived: number = 0
  private listeners: Map<WSEventType | '*', Set<EventCallback>> = new Map()
  private connectionStateListeners: Set<ConnectionStateCallback> = new Set()
  private connectionPromise: Promise<void> | null = null
  private isIntentionalClose = false
  // WS-31-MED-02 FIX: Visibility change handler for reconnection after sleep
  private visibilityHandler: (() => void) | null = null

  constructor() {
    // WS-31-MED-02 FIX: Set up visibility change listener
    this.setupVisibilityListener()
  }

  /**
   * WS-31-MED-02 FIX: Listen for page visibility changes to reconnect after sleep/background
   */
  private setupVisibilityListener(): void {
    if (typeof document === 'undefined') return

    // Clean up any existing listener first
    this.cleanupVisibilityListener()

    this.visibilityHandler = () => {
      if (document.visibilityState === 'visible') {
        wsLogger.info('Page became visible, checking connection...')

        // If we were connected but connection is now stale, reconnect
        if (!this.isIntentionalClose && this.token && !this.isConnected()) {
          wsLogger.info('Connection lost during sleep, reconnecting...')
          this.reconnectAttempts = 0 // Reset attempts for fresh start
          this.connectionPromise = null
          this.connect(this.token).catch((err) => {
            wsLogger.error('Failed to reconnect after visibility change', err)
          })
        } else if (this.isConnected()) {
          // Connection still open, but may be stale - send ping to verify
          this.sendPing()
        }
      }
    }

    document.addEventListener('visibilitychange', this.visibilityHandler)
    wsLogger.info('Visibility listener set up for reconnection after sleep')
  }

  /**
   * WS-31-MED-02 FIX: Clean up visibility listener
   */
  private cleanupVisibilityListener(): void {
    if (this.visibilityHandler && typeof document !== 'undefined') {
      document.removeEventListener('visibilitychange', this.visibilityHandler)
      this.visibilityHandler = null
    }
  }

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
          // WS-31-MED-03 FIX: Clear connectionPromise on error so next connect() creates new one
          this.connectionPromise = null
          reject(new Error('WebSocket connection failed'))
        }

        this.ws.onclose = (event) => {
          wsLogger.info('WebSocket closed', { code: event.code, reason: event.reason })
          this.stopHeartbeat()
          // WS-31-MED-03 FIX: Clear connectionPromise on close
          this.connectionPromise = null
          this.notifyConnectionState(false)

          if (!this.isIntentionalClose) {
            this.scheduleReconnect()
          }
        }
      } catch (error) {
        wsLogger.error('Failed to create WebSocket', error)
        // WS-31-MED-03 FIX: Clear connectionPromise on catch
        this.connectionPromise = null
        reject(error)
      }
    })

    return this.connectionPromise
  }

  /**
   * Disconnect from WebSocket server
   * WS-31-MED-02 FIX: Also cleans up visibility listener
   */
  disconnect(): void {
    this.isIntentionalClose = true
    this.stopHeartbeat()
    this.clearTokenRefreshTimeout() // PWAW-A001
    // WS-31-MED-02 FIX: Clean up visibility listener on disconnect
    this.cleanupVisibilityListener()

    if (this.reconnectTimeout) {
      clearTimeout(this.reconnectTimeout)
      this.reconnectTimeout = null
    }

    if (this.ws) {
      this.ws.close(1000, 'Client disconnect')
      this.ws = null
    }

    // WAITER-SVC-HIGH-01: Clear all token-related state properly
    this.token = null
    this.tokenExp = null
    this.tokenRefreshCallback = null
    this.connectionPromise = null
    this.reconnectAttempts = 0
    this.lastPongReceived = 0

    wsLogger.info('Disconnected from WebSocket')
  }

  /**
   * Full cleanup including visibility listener (call when unloading)
   */
  destroy(): void {
    this.disconnect()
    this.cleanupVisibilityListener()
    this.listeners.clear()
    this.connectionStateListeners.clear()
    wsLogger.info('WebSocket service destroyed')
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
   * CRIT-02 FIX: Use async/await to prevent race condition
   * HIGH-29-19 FIX: Set isIntentionalClose=false BEFORE connect() resolves to avoid race
   * WS-CRIT-01 FIX: Wait for onclose to process before resetting flag and reconnecting
   */
  async updateToken(newToken: string): Promise<void> {
    wsLogger.info('Updating WebSocket token')
    this.token = newToken
    this.parseTokenExpiration(newToken)

    // Reconnect with new token
    if (this.isConnected()) {
      this.isIntentionalClose = true
      this.ws?.close(1000, 'Token refresh')
      this.connectionPromise = null  // Clear old promise so connect() creates new one

      try {
        // WS-CRIT-01 FIX: Wait for onclose handler to process before reconnecting
        // This prevents the race condition where onclose sees isIntentionalClose=false
        // and triggers scheduleReconnect() while we're also calling connect()
        await new Promise((resolve) => setTimeout(resolve, 100))

        // NOW safe to reset flag and reconnect
        this.isIntentionalClose = false
        await this.connect(newToken)
        wsLogger.info('WebSocket reconnected with refreshed token')
      } catch (err) {
        this.isIntentionalClose = false
        wsLogger.error('Failed to reconnect with new token', err)
      }
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
      const data = JSON.parse(event.data)

      // WS-31-MED-01 FIX: Handle pong response (consistent with pwaMenu/Dashboard)
      if (data.type === 'pong') {
        this.lastPongReceived = Date.now()
        this.clearHeartbeatTimeout()
        return // Don't propagate pong to listeners
      }

      const wsEvent = data as WSEvent
      wsLogger.debug('Received event', { type: wsEvent.type, table_id: wsEvent.table_id })

      // Notify specific listeners
      this.listeners.get(wsEvent.type)?.forEach((cb) => cb(wsEvent))

      // Notify wildcard listeners
      this.listeners.get('*')?.forEach((cb) => cb(wsEvent))
    } catch (error) {
      wsLogger.error('Failed to parse WebSocket message', error)
    }
  }

  /**
   * WS-31-HIGH-01 FIX: Refactored to use sendPing() with timeout detection
   */
  private startHeartbeat(): void {
    this.stopHeartbeat()

    this.heartbeatInterval = setInterval(() => {
      if (this.ws?.readyState === WebSocket.OPEN) {
        this.sendPing()
      }
    }, WS_CONFIG.HEARTBEAT_INTERVAL)

    wsLogger.debug('Heartbeat started')
  }

  private stopHeartbeat(): void {
    if (this.heartbeatInterval) {
      clearInterval(this.heartbeatInterval)
      this.heartbeatInterval = null
    }
    this.clearHeartbeatTimeout()
  }

  /**
   * WS-31-HIGH-01 FIX: Send ping and set timeout for pong response
   */
  private sendPing(): void {
    if (!this.ws || this.ws.readyState !== WebSocket.OPEN) return

    try {
      this.ws.send(JSON.stringify({ type: 'ping' }))

      // WS-31-HIGH-01 FIX: Set timeout for pong response (10s default)
      const HEARTBEAT_TIMEOUT = WS_CONFIG.HEARTBEAT_TIMEOUT || 10000
      this.heartbeatTimeout = setTimeout(() => {
        wsLogger.warn('Heartbeat timeout - no pong received')
        // Close connection to trigger reconnect
        this.ws?.close(4000, 'Heartbeat timeout')
      }, HEARTBEAT_TIMEOUT)
    } catch (err) {
      wsLogger.error('Failed to send ping', err)
    }
  }

  /**
   * WS-31-HIGH-01 FIX: Clear the heartbeat timeout (called when pong is received)
   */
  private clearHeartbeatTimeout(): void {
    if (this.heartbeatTimeout) {
      clearTimeout(this.heartbeatTimeout)
      this.heartbeatTimeout = null
    }
  }

  /**
   * Get the time since last pong (for debugging)
   */
  getLastPongAge(): number {
    if (this.lastPongReceived === 0) return -1
    return Date.now() - this.lastPongReceived
  }

  /**
   * WS-HIGH-02 FIX: Changed from linear to exponential backoff with jitter
   * Matches Dashboard/pwaMenu implementation for consistency
   */
  private scheduleReconnect(): void {
    if (this.reconnectAttempts >= WS_CONFIG.MAX_RECONNECT_ATTEMPTS) {
      wsLogger.warn('Max reconnect attempts reached')
      return
    }

    this.reconnectAttempts++

    // WS-HIGH-02 FIX: Exponential backoff with jitter instead of linear
    const BASE_DELAY = WS_CONFIG.RECONNECT_INTERVAL
    const MAX_DELAY = 30000 // 30 seconds max
    const JITTER_FACTOR = 0.3

    const exponentialDelay = Math.min(
      BASE_DELAY * Math.pow(2, this.reconnectAttempts - 1),
      MAX_DELAY
    )
    const jitter = exponentialDelay * JITTER_FACTOR * Math.random()
    const delay = Math.round(exponentialDelay + jitter)

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
   * WS-HIGH-03 FIX: Explicitly clear tokenExp on parse errors to prevent stale values
   */
  private parseTokenExpiration(token: string): void {
    try {
      const parts = token.split('.')
      if (parts.length !== 3) {
        wsLogger.warn('Invalid token format (not 3 parts)')
        this.tokenExp = null // WS-HIGH-03 FIX: Clear stale value
        return
      }

      const payload = JSON.parse(atob(parts[1]))
      if (payload.exp && typeof payload.exp === 'number' && payload.exp > 0) {
        this.tokenExp = payload.exp
        wsLogger.debug('Token expires at', { exp: new Date(payload.exp * 1000).toISOString() })
      } else {
        wsLogger.warn('Token missing or invalid exp field')
        this.tokenExp = null // WS-HIGH-03 FIX: Clear stale value
      }
    } catch (error) {
      wsLogger.warn('Failed to parse token expiration', error)
      this.tokenExp = null // WS-HIGH-03 FIX: Clear stale value on error
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
