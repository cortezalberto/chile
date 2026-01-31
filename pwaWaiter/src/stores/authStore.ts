import { create } from 'zustand'
import { persist } from 'zustand/middleware'
import { authAPI, branchAPI, waiterAssignmentAPI, setAuthToken, setRefreshToken, setTokenRefreshCallback } from '../services/api'
import { wsService } from '../services/websocket'
import { notificationService } from '../services/notifications'
import { STORAGE_KEYS } from '../utils/constants'
import { authLogger } from '../utils/logger'
import type { User } from '../types'
// QA-WAITER-HIGH-01 FIX: Import BroadcastChannel cleanup function
import { closeBroadcastChannel } from './historyStore'

// Branch info for display (fetched from backend)
export interface BranchOption {
  id: number
  name: string
}

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
  selectedBranchName: string | null  // Branch name for display
  availableBranches: BranchOption[]  // Cached branch names for selection
  isAuthenticated: boolean
  isLoading: boolean
  error: string | null
  refreshAttempts: number  // WAITER-CRIT-01 FIX: Track refresh retry attempts
  isRefreshing: boolean  // HIGH-29-18 FIX: Flag to prevent concurrent refresh attempts
  // Pre-login branch selection (for assignment verification)
  preLoginBranchId: number | null
  preLoginBranchName: string | null
  assignmentVerified: boolean  // True if waiter is verified to work at selected branch today
  // Actions
  login: (email: string, password: string) => Promise<boolean>
  logout: () => void
  checkAuth: () => Promise<boolean>
  selectBranch: (branchId: number, branchName?: string) => void
  setPreLoginBranchId: (branchId: number, branchName?: string) => void  // Set branch before login
  clearPreLoginBranch: () => void  // Clear pre-login branch selection
  verifyBranchAssignment: () => Promise<boolean>  // Verify assignment after login
  fetchBranchNames: () => Promise<void>  // Fetch branch names for selection screen
  clearError: () => void
  refreshAccessToken: () => Promise<boolean>  // DEF-HIGH-04 FIX
}

// DEF-HIGH-04 FIX: Helper to start token refresh interval
// MED-29-22 FIX: Always stop existing interval before creating new one, with debug logging
function startTokenRefreshInterval(refreshFn: () => Promise<boolean>): void {
  if (refreshIntervalId !== null) {
    authLogger.debug('Token refresh interval already active, stopping before restart')
  }
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
      selectedBranchName: null,
      availableBranches: [],
      isAuthenticated: false,
      isLoading: false,
      error: null,
      refreshAttempts: 0,  // WAITER-CRIT-01 FIX
      isRefreshing: false,  // HIGH-29-18 FIX: Initial state
      // Pre-login branch selection
      preLoginBranchId: null,
      preLoginBranchName: null,
      assignmentVerified: false,

      // Set pre-login branch (before authentication)
      setPreLoginBranchId: (branchId: number, branchName?: string) => {
        set({ preLoginBranchId: branchId, preLoginBranchName: branchName || null })
        authLogger.info('Pre-login branch selected', { branchId, branchName })
      },

      // Clear pre-login branch to go back to branch selection
      clearPreLoginBranch: () => {
        set({ preLoginBranchId: null, preLoginBranchName: null, error: null })
        authLogger.info('Pre-login branch cleared')
      },

      // Verify branch assignment after login
      verifyBranchAssignment: async (): Promise<boolean> => {
        const { preLoginBranchId, preLoginBranchName } = get()
        if (!preLoginBranchId) {
          set({ error: 'Debes seleccionar una sucursal primero' })
          return false
        }

        try {
          const result = await waiterAssignmentAPI.verifyBranchAssignment(preLoginBranchId)

          if (!result.is_assigned) {
            set({
              error: result.message,
              assignmentVerified: false,
            })
            authLogger.warn('Branch assignment verification failed', { branchId: preLoginBranchId, message: result.message })
            return false
          }

          // Assignment verified - set as selected branch
          set({
            selectedBranchId: preLoginBranchId,
            selectedBranchName: preLoginBranchName || result.branch_name,
            assignmentVerified: true,
            error: null,
          })
          authLogger.info('Branch assignment verified', { branchId: preLoginBranchId, sectors: result.sectors.length })
          return true
        } catch (err) {
          const message = err instanceof Error ? err.message : 'Error al verificar asignación'
          set({ error: message, assignmentVerified: false })
          authLogger.error('Branch assignment verification error', err)
          return false
        }
      },

      login: async (email: string, password: string): Promise<boolean> => {
        set({ isLoading: true, error: null })
        try {
          const response = await authAPI.login(email, password)

          // Check if user has WAITER role
          if (!response.user.roles.includes('WAITER') && !response.user.roles.includes('ADMIN')) {
            throw new Error('No tienes permisos de mozo')
          }

          // DEF-HIGH-04 FIX: Extract refresh token if provided
          const refreshTokenValue = (response as { refresh_token?: string }).refresh_token || null

          // Don't auto-select branch - will be verified with preLoginBranchId
          set({
            user: response.user,
            token: response.access_token,
            refreshToken: refreshTokenValue,  // DEF-HIGH-04 FIX
            selectedBranchId: null,  // Will be set after verification
            isAuthenticated: true,
            isLoading: false,
            error: null,
            refreshAttempts: 0,  // WAITER-CRIT-01 FIX: Reset on login
            assignmentVerified: false,  // Reset - needs verification
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

          // Fetch branch names (needed for BranchSelect screen or auto-select with name)
          get().fetchBranchNames()

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
            selectedBranchName: null,
            availableBranches: [],
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
        // QA-WAITER-HIGH-01 FIX: Clean up BroadcastChannel on logout
        closeBroadcastChannel()
        set({
          user: null,
          token: null,
          refreshToken: null,  // DEF-HIGH-04 FIX
          selectedBranchId: null,
          selectedBranchName: null,
          availableBranches: [],
          isAuthenticated: false,
          error: null,
          // Clear pre-login state
          preLoginBranchId: null,
          preLoginBranchName: null,
          assignmentVerified: false,
        })
      },

      // DEF-HIGH-04 FIX: Refresh access token
      // WAITER-CRIT-01 FIX: Added retry counter and auto-logout after max retries
      // HIGH-29-18 FIX: Added isRefreshing flag to prevent race condition
      // SEC-09: Refresh token is now in HttpOnly cookie, no need to check in memory
      refreshAccessToken: async (): Promise<boolean> => {
        const { refreshAttempts, isRefreshing } = get()

        // HIGH-29-18 FIX: Check if refresh is already in progress
        if (isRefreshing) {
          authLogger.debug('Token refresh already in progress, skipping')
          return false
        }

        // WAITER-CRIT-01 FIX: Check max retries before attempting
        if (refreshAttempts >= MAX_REFRESH_ATTEMPTS) {
          authLogger.warn('Max refresh attempts reached, logging out', { attempts: refreshAttempts })
          get().logout()
          return false
        }

        // SEC-09: Don't check for refreshToken in memory - it's in HttpOnly cookie
        // The server will reject the request if no valid cookie is present

        // HIGH-29-18 FIX: Set isRefreshing flag at the start
        // WAITER-CRIT-01 FIX: Increment attempt counter before trying
        set({ isRefreshing: true, refreshAttempts: refreshAttempts + 1 })

        try {
          const result = await authAPI.refresh()
          if (result) {
            set({
              token: result.access_token,
              // SEC-09: Keep refreshToken in state for backward compatibility
              // (actual token is managed via HttpOnly cookie)
              refreshToken: result.refresh_token || get().refreshToken,
              refreshAttempts: 0,  // WAITER-CRIT-01 FIX: Reset on success
              isRefreshing: false,  // HIGH-29-18 FIX: Reset flag on success
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
        } finally {
          // HIGH-29-18 FIX: Always reset isRefreshing flag in finally block
          set({ isRefreshing: false })
        }
      },

      // LOOP-FIX: Internal helper with retry tracking to prevent infinite recursion
      checkAuth: async (): Promise<boolean> => {
        // LOOP-FIX: Use a flag to track if we've already tried refreshing in this auth check
        let hasTriedRefresh = false

        const doCheckAuth = async (): Promise<boolean> => {
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

            // Fetch branch names if not already cached (for BranchSelect or Header display)
            if (get().availableBranches.length === 0) {
              get().fetchBranchNames()
            }

            return true
          } catch (err) {
            authLogger.warn('Auth check failed', err)
            // Token is invalid or expired - try refresh ONLY ONCE
            if (storedRefreshToken && !hasTriedRefresh) {
              hasTriedRefresh = true  // LOOP-FIX: Mark that we've tried refresh
              authLogger.info('Attempting token refresh after auth check failure')
              const refreshed = await get().refreshAccessToken()
              if (refreshed) {
                // Retry auth check with new token (only once due to hasTriedRefresh flag)
                return doCheckAuth()
              }
            }
            // Refresh failed, already tried, or no refresh token
            set({
              user: null,
              token: null,
              refreshToken: null,
              selectedBranchId: null,
              selectedBranchName: null,
              availableBranches: [],
              isAuthenticated: false,
            })
            return false
          }
        }

        return doCheckAuth()
      },

      selectBranch: (branchId: number, branchName?: string) => {
        const { user, availableBranches } = get()
        if (user?.branch_ids.includes(branchId)) {
          // Use provided name or look up from cached branches
          const name = branchName || availableBranches.find(b => b.id === branchId)?.name || null
          set({ selectedBranchId: branchId, selectedBranchName: name })
          authLogger.info('Branch selected', { branchId, branchName: name })
        }
      },

      // Fetch branch names for the selection screen
      fetchBranchNames: async () => {
        const { user } = get()
        if (!user?.branch_ids.length) return

        try {
          // Fetch branch info for each branch the user has access to
          const branches = await Promise.all(
            user.branch_ids.map(async (id) => {
              try {
                const branch = await branchAPI.getBranch(id)
                return { id: branch.id, name: branch.name }
              } catch (err) {
                authLogger.warn('Failed to fetch branch info', { branchId: id, error: err })
                return { id, name: `Sucursal ${id}` }  // Fallback to ID
              }
            })
          )
          set({ availableBranches: branches })

          // If only one branch, auto-select it with name
          if (branches.length === 1) {
            set({
              selectedBranchId: branches[0].id,
              selectedBranchName: branches[0].name,
            })
          }
        } catch (err) {
          authLogger.error('Failed to fetch branch names', err)
        }
      },

      clearError: () => set({ error: null }),
    }),
    {
      name: STORAGE_KEYS.AUTH,
      version: 4,  // SEC-09: Bump version - refreshToken now in HttpOnly cookie
      partialize: (state) => ({
        // Only persist access token and user, not loading/error states
        // SEC-09: refreshToken is now in HttpOnly cookie, not localStorage
        token: state.token,
        user: state.user,
        selectedBranchId: state.selectedBranchId,
        selectedBranchName: state.selectedBranchName,
        availableBranches: state.availableBranches,
        isAuthenticated: state.isAuthenticated,
      }),
      onRehydrateStorage: () => (state) => {
        // After rehydration, restore access token to API client
        if (state?.token) {
          setAuthToken(state.token)
          // HIGH-07 FIX: Sync token with WebSocket service on rehydration
          // This ensures the WebSocket uses the same token as the API client
          // The actual connection is deferred to checkAuth() to avoid premature connects
          authLogger.debug('Token restored from storage, API client synced')
        }
        // SEC-09: refreshToken is in HttpOnly cookie, no need to restore
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
export const selectSelectedBranchName = (state: AuthState) => state.selectedBranchName
const EMPTY_BRANCH_IDS: number[] = []
export const selectUserBranchIds = (state: AuthState) => state.user?.branch_ids ?? EMPTY_BRANCH_IDS
const EMPTY_BRANCHES: BranchOption[] = []
export const selectAvailableBranches = (state: AuthState) => state.availableBranches.length > 0 ? state.availableBranches : EMPTY_BRANCHES
// Pre-login branch selection selectors
export const selectPreLoginBranchId = (state: AuthState) => state.preLoginBranchId
export const selectPreLoginBranchName = (state: AuthState) => state.preLoginBranchName
export const selectAssignmentVerified = (state: AuthState) => state.assignmentVerified
