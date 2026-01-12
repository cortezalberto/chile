import { create } from 'zustand'
import { persist } from 'zustand/middleware'
import { authAPI, setAuthToken, setRefreshToken, setTokenRefreshCallback } from '../services/api'
import { wsService } from '../services/websocket'
import { notificationService } from '../services/notifications'
import { STORAGE_KEYS } from '../utils/constants'
import { authLogger } from '../utils/logger'
import type { User } from '../types'

// DEF-HIGH-04 FIX: Token refresh interval (refresh 1 minute before expiry, assuming 15 min tokens)
const TOKEN_REFRESH_INTERVAL_MS = 14 * 60 * 1000 // 14 minutes
let refreshIntervalId: ReturnType<typeof setInterval> | null = null

// WAITER-CRIT-01 FIX: Max retry attempts before auto-logout
const MAX_REFRESH_ATTEMPTS = 3

interface AuthState {
  user: User | null
  token: string | null
  refreshToken: string | null  // DEF-HIGH-04 FIX
  selectedBranchId: number | null
  isAuthenticated: boolean
  isLoading: boolean
  error: string | null
  refreshAttempts: number  // WAITER-CRIT-01 FIX: Track refresh retry attempts
  // Actions
  login: (email: string, password: string) => Promise<boolean>
  logout: () => void
  checkAuth: () => Promise<boolean>
  selectBranch: (branchId: number) => void
  clearError: () => void
  refreshAccessToken: () => Promise<boolean>  // DEF-HIGH-04 FIX
}

// DEF-HIGH-04 FIX: Helper to start token refresh interval
function startTokenRefreshInterval(refreshFn: () => Promise<boolean>): void {
  stopTokenRefreshInterval()
  refreshIntervalId = setInterval(() => {
    refreshFn().catch((err) => {
      authLogger.error('Scheduled token refresh failed', err)
    })
  }, TOKEN_REFRESH_INTERVAL_MS)
  authLogger.info('Token refresh interval started')
}

function stopTokenRefreshInterval(): void {
  if (refreshIntervalId) {
    clearInterval(refreshIntervalId)
    refreshIntervalId = null
    authLogger.info('Token refresh interval stopped')
  }
}

export const useAuthStore = create<AuthState>()(
  persist(
    (set, get) => ({
      user: null,
      token: null,
      refreshToken: null,  // DEF-HIGH-04 FIX
      selectedBranchId: null,
      isAuthenticated: false,
      isLoading: false,
      error: null,
      refreshAttempts: 0,  // WAITER-CRIT-01 FIX

      login: async (email: string, password: string): Promise<boolean> => {
        set({ isLoading: true, error: null })
        try {
          const response = await authAPI.login(email, password)

          // Check if user has WAITER role
          if (!response.user.roles.includes('WAITER') && !response.user.roles.includes('ADMIN')) {
            throw new Error('No tienes permisos de mozo')
          }

          // Auto-select first branch if only one
          const selectedBranchId = response.user.branch_ids.length === 1
            ? response.user.branch_ids[0]
            : null

          // DEF-HIGH-04 FIX: Extract refresh token if provided
          const refreshTokenValue = (response as { refresh_token?: string }).refresh_token || null

          set({
            user: response.user,
            token: response.access_token,
            refreshToken: refreshTokenValue,  // DEF-HIGH-04 FIX
            selectedBranchId,
            isAuthenticated: true,
            isLoading: false,
            error: null,
            refreshAttempts: 0,  // WAITER-CRIT-01 FIX: Reset on login
          })

          // Connect to WebSocket
          wsService.connect(response.access_token).catch((err) => {
            authLogger.error('Failed to connect WebSocket after login', err)
          })

          // DEF-HIGH-04 FIX: Set up token refresh callback for WebSocket
          setTokenRefreshCallback((newToken: string) => {
            wsService.updateToken(newToken)
          })

          // DEF-HIGH-04 FIX: Start token refresh interval
          startTokenRefreshInterval(() => get().refreshAccessToken())

          // Request notification permission
          notificationService.requestPermission()

          authLogger.info('Login successful', { userId: response.user.id })
          return true
        } catch (err) {
          const message = err instanceof Error ? err.message : 'Error de autenticacion'
          authLogger.error('Login failed', err)
          set({
            user: null,
            token: null,
            refreshToken: null,
            selectedBranchId: null,
            isAuthenticated: false,
            isLoading: false,
            error: message,
          })
          return false
        }
      },

      logout: () => {
        authLogger.info('Logging out')
        // DEF-HIGH-04 FIX: Stop token refresh interval
        stopTokenRefreshInterval()
        setTokenRefreshCallback(null)
        authAPI.logout()
        wsService.disconnect()
        set({
          user: null,
          token: null,
          refreshToken: null,  // DEF-HIGH-04 FIX
          selectedBranchId: null,
          isAuthenticated: false,
          error: null,
        })
      },

      // DEF-HIGH-04 FIX: Refresh access token
      // WAITER-CRIT-01 FIX: Added retry counter and auto-logout after max retries
      refreshAccessToken: async (): Promise<boolean> => {
        const { refreshToken: currentRefreshToken, refreshAttempts } = get()

        // WAITER-CRIT-01 FIX: Check max retries before attempting
        if (refreshAttempts >= MAX_REFRESH_ATTEMPTS) {
          authLogger.warn('Max refresh attempts reached, logging out', { attempts: refreshAttempts })
          get().logout()
          return false
        }

        if (!currentRefreshToken) {
          authLogger.warn('No refresh token available for refresh')
          return false
        }

        // WAITER-CRIT-01 FIX: Increment attempt counter before trying
        set({ refreshAttempts: refreshAttempts + 1 })

        // Restore refresh token to API client
        setRefreshToken(currentRefreshToken)

        try {
          const result = await authAPI.refresh()
          if (result) {
            set({
              token: result.access_token,
              refreshToken: result.refresh_token || currentRefreshToken,
              refreshAttempts: 0,  // WAITER-CRIT-01 FIX: Reset on success
            })
            authLogger.info('Token refreshed and stored')
            return true
          }

          // Refresh returned null/undefined - don't logout immediately, let interval retry
          authLogger.warn('Token refresh returned empty result', { attempt: refreshAttempts + 1 })
          return false
        } catch (err) {
          // WAITER-CRIT-01 FIX: Don't logout immediately on error, let interval retry
          authLogger.error('Token refresh failed', { attempt: refreshAttempts + 1, error: err })
          return false
        }
      },

      checkAuth: async (): Promise<boolean> => {
        const { token, refreshToken: storedRefreshToken } = get()
        if (!token) {
          set({ isAuthenticated: false })
          return false
        }

        // Restore tokens to API client
        setAuthToken(token)
        if (storedRefreshToken) {
          setRefreshToken(storedRefreshToken)
        }

        try {
          const user = await authAPI.getMe()

          // Check if user has WAITER role
          if (!user.roles.includes('WAITER') && !user.roles.includes('ADMIN')) {
            throw new Error('No tienes permisos de mozo')
          }

          set({
            user,
            isAuthenticated: true,
          })

          // Connect to WebSocket
          wsService.connect(token).catch((err) => {
            authLogger.error('Failed to connect WebSocket on auth check', err)
          })

          // DEF-HIGH-04 FIX: Set up token refresh callback and start interval
          setTokenRefreshCallback((newToken: string) => {
            wsService.updateToken(newToken)
          })
          startTokenRefreshInterval(() => get().refreshAccessToken())

          return true
        } catch (err) {
          authLogger.warn('Auth check failed', err)
          // Token is invalid or expired - try refresh
          if (storedRefreshToken) {
            authLogger.info('Attempting token refresh after auth check failure')
            const refreshed = await get().refreshAccessToken()
            if (refreshed) {
              // Retry auth check with new token
              return get().checkAuth()
            }
          }
          // Refresh failed or no refresh token
          set({
            user: null,
            token: null,
            refreshToken: null,
            selectedBranchId: null,
            isAuthenticated: false,
          })
          return false
        }
      },

      selectBranch: (branchId: number) => {
        const { user } = get()
        if (user?.branch_ids.includes(branchId)) {
          set({ selectedBranchId: branchId })
          authLogger.info('Branch selected', { branchId })
        }
      },

      clearError: () => set({ error: null }),
    }),
    {
      name: STORAGE_KEYS.AUTH,
      version: 2,  // DEF-HIGH-04 FIX: Bump version for new field
      partialize: (state) => ({
        token: state.token,
        refreshToken: state.refreshToken,  // DEF-HIGH-04 FIX
        user: state.user,
        selectedBranchId: state.selectedBranchId,
        isAuthenticated: state.isAuthenticated,
      }),
      onRehydrateStorage: () => (state) => {
        // After rehydration, restore tokens to API client
        if (state?.token) {
          setAuthToken(state.token)
        }
        // DEF-HIGH-04 FIX: Restore refresh token
        if (state?.refreshToken) {
          setRefreshToken(state.refreshToken)
        }
      },
    }
  )
)

// Selectors
export const selectUser = (state: AuthState) => state.user
export const selectIsAuthenticated = (state: AuthState) => state.isAuthenticated
export const selectIsLoading = (state: AuthState) => state.isLoading
export const selectAuthError = (state: AuthState) => state.error
export const selectSelectedBranchId = (state: AuthState) => state.selectedBranchId
const EMPTY_BRANCH_IDS: number[] = []
export const selectUserBranchIds = (state: AuthState) => state.user?.branch_ids ?? EMPTY_BRANCH_IDS
