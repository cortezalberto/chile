import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
// LOW-01 FIX: Removed unused selector imports (selectUser, selectIsAuthenticated, selectIsLoading, selectAuthError, selectSelectedBranchId)
import {
  useAuthStore,
  selectUserBranchIds,
} from './authStore'

// Mock all dependencies
vi.mock('../services/api', () => ({
  authAPI: {
    login: vi.fn(),
    logout: vi.fn(),
    getMe: vi.fn(),
    refresh: vi.fn(),
  },
  setAuthToken: vi.fn(),
  setRefreshToken: vi.fn(),
  setTokenRefreshCallback: vi.fn(),
}))

vi.mock('../services/websocket', () => ({
  wsService: {
    connect: vi.fn().mockResolvedValue(undefined),
    disconnect: vi.fn(),
    updateToken: vi.fn(),
  },
}))

vi.mock('../services/notifications', () => ({
  notificationService: {
    requestPermission: vi.fn(),
  },
}))

vi.mock('../utils/logger', () => ({
  authLogger: {
    info: vi.fn(),
    warn: vi.fn(),
    error: vi.fn(),
  },
}))

// Import mocked modules
import { authAPI, setAuthToken, setRefreshToken } from '../services/api'
import { wsService } from '../services/websocket'
import { notificationService } from '../services/notifications'

const mockUser = {
  id: 1,
  email: 'waiter@test.com',
  name: 'Test Waiter',
  roles: ['WAITER'],
  branch_ids: [1, 2],
}

describe('authStore', () => {
  beforeEach(() => {
    // Reset store to initial state
    useAuthStore.setState({
      user: null,
      token: null,
      refreshToken: null,
      selectedBranchId: null,
      isAuthenticated: false,
      isLoading: false,
      error: null,
      refreshAttempts: 0,
    })
    vi.clearAllMocks()
  })

  afterEach(() => {
    vi.clearAllTimers()
  })

  describe('initial state', () => {
    it('should have correct initial state', () => {
      const state = useAuthStore.getState()
      expect(state.user).toBeNull()
      expect(state.token).toBeNull()
      expect(state.refreshToken).toBeNull()
      expect(state.selectedBranchId).toBeNull()
      expect(state.isAuthenticated).toBe(false)
      expect(state.isLoading).toBe(false)
      expect(state.error).toBeNull()
      expect(state.refreshAttempts).toBe(0)
    })
  })

  describe('login', () => {
    it('should login successfully with WAITER role', async () => {
      vi.mocked(authAPI.login).mockResolvedValue({
        access_token: 'test-token',
        refresh_token: 'refresh-token',
        user: mockUser,
      })

      const result = await useAuthStore.getState().login('waiter@test.com', 'password')

      expect(result).toBe(true)
      const state = useAuthStore.getState()
      expect(state.isAuthenticated).toBe(true)
      expect(state.user).toEqual(mockUser)
      expect(state.token).toBe('test-token')
      expect(state.refreshToken).toBe('refresh-token')
      expect(state.error).toBeNull()
      expect(state.refreshAttempts).toBe(0)
      expect(wsService.connect).toHaveBeenCalledWith('test-token')
      expect(notificationService.requestPermission).toHaveBeenCalled()
    })

    it('should login successfully with ADMIN role', async () => {
      const adminUser = { ...mockUser, roles: ['ADMIN'] }
      vi.mocked(authAPI.login).mockResolvedValue({
        access_token: 'test-token',
        user: adminUser,
      })

      const result = await useAuthStore.getState().login('admin@test.com', 'password')

      expect(result).toBe(true)
      expect(useAuthStore.getState().isAuthenticated).toBe(true)
    })

    it('should reject login without WAITER or ADMIN role', async () => {
      const kitchenUser = { ...mockUser, roles: ['KITCHEN'] }
      vi.mocked(authAPI.login).mockResolvedValue({
        access_token: 'test-token',
        user: kitchenUser,
      })

      const result = await useAuthStore.getState().login('kitchen@test.com', 'password')

      expect(result).toBe(false)
      const state = useAuthStore.getState()
      expect(state.isAuthenticated).toBe(false)
      expect(state.error).toBe('No tienes permisos de mozo')
    })

    it('should auto-select branch when user has only one branch', async () => {
      const singleBranchUser = { ...mockUser, branch_ids: [1] }
      vi.mocked(authAPI.login).mockResolvedValue({
        access_token: 'test-token',
        user: singleBranchUser,
      })

      await useAuthStore.getState().login('waiter@test.com', 'password')

      expect(useAuthStore.getState().selectedBranchId).toBe(1)
    })

    it('should not auto-select branch when user has multiple branches', async () => {
      vi.mocked(authAPI.login).mockResolvedValue({
        access_token: 'test-token',
        user: mockUser, // has branch_ids: [1, 2]
      })

      await useAuthStore.getState().login('waiter@test.com', 'password')

      expect(useAuthStore.getState().selectedBranchId).toBeNull()
    })

    it('should handle login error', async () => {
      vi.mocked(authAPI.login).mockRejectedValue(new Error('Invalid credentials'))

      const result = await useAuthStore.getState().login('bad@test.com', 'wrong')

      expect(result).toBe(false)
      const state = useAuthStore.getState()
      expect(state.isAuthenticated).toBe(false)
      expect(state.error).toBe('Invalid credentials')
      expect(state.user).toBeNull()
      expect(state.token).toBeNull()
    })

    it('should set isLoading during login', async () => {
      let resolveLogin: (value: unknown) => void
      vi.mocked(authAPI.login).mockImplementation(
        () => new Promise((resolve) => { resolveLogin = resolve })
      )

      const loginPromise = useAuthStore.getState().login('waiter@test.com', 'password')

      expect(useAuthStore.getState().isLoading).toBe(true)

      resolveLogin!({
        access_token: 'test-token',
        user: mockUser,
      })

      await loginPromise
      expect(useAuthStore.getState().isLoading).toBe(false)
    })
  })

  describe('logout', () => {
    it('should clear state on logout', async () => {
      // First login
      vi.mocked(authAPI.login).mockResolvedValue({
        access_token: 'test-token',
        refresh_token: 'refresh-token',
        user: mockUser,
      })
      await useAuthStore.getState().login('waiter@test.com', 'password')

      // Then logout
      useAuthStore.getState().logout()

      const state = useAuthStore.getState()
      expect(state.user).toBeNull()
      expect(state.token).toBeNull()
      expect(state.refreshToken).toBeNull()
      expect(state.selectedBranchId).toBeNull()
      expect(state.isAuthenticated).toBe(false)
      expect(state.error).toBeNull()
      expect(authAPI.logout).toHaveBeenCalled()
      expect(wsService.disconnect).toHaveBeenCalled()
    })
  })

  describe('checkAuth', () => {
    it('should return false when no token', async () => {
      const result = await useAuthStore.getState().checkAuth()

      expect(result).toBe(false)
      expect(useAuthStore.getState().isAuthenticated).toBe(false)
    })

    it('should verify token and authenticate', async () => {
      useAuthStore.setState({ token: 'existing-token', refreshToken: 'existing-refresh' })
      vi.mocked(authAPI.getMe).mockResolvedValue(mockUser)

      const result = await useAuthStore.getState().checkAuth()

      expect(result).toBe(true)
      expect(setAuthToken).toHaveBeenCalledWith('existing-token')
      expect(setRefreshToken).toHaveBeenCalledWith('existing-refresh')
      expect(useAuthStore.getState().isAuthenticated).toBe(true)
      expect(useAuthStore.getState().user).toEqual(mockUser)
    })

    it('should reject user without WAITER role on checkAuth', async () => {
      useAuthStore.setState({ token: 'existing-token' })
      vi.mocked(authAPI.getMe).mockResolvedValue({ ...mockUser, roles: ['KITCHEN'] })

      const result = await useAuthStore.getState().checkAuth()

      expect(result).toBe(false)
      expect(useAuthStore.getState().isAuthenticated).toBe(false)
    })

    it('should try refresh when auth check fails', async () => {
      useAuthStore.setState({ token: 'expired-token', refreshToken: 'refresh-token' })
      vi.mocked(authAPI.getMe)
        .mockRejectedValueOnce(new Error('Token expired'))
        .mockResolvedValueOnce(mockUser)
      vi.mocked(authAPI.refresh).mockResolvedValue({
        access_token: 'new-token',
        refresh_token: 'new-refresh',
      })

      const result = await useAuthStore.getState().checkAuth()

      expect(result).toBe(true)
      expect(authAPI.refresh).toHaveBeenCalled()
    })
  })

  describe('selectBranch', () => {
    it('should select branch when user has access', async () => {
      vi.mocked(authAPI.login).mockResolvedValue({
        access_token: 'test-token',
        user: mockUser,
      })
      await useAuthStore.getState().login('waiter@test.com', 'password')

      useAuthStore.getState().selectBranch(1)

      expect(useAuthStore.getState().selectedBranchId).toBe(1)
    })

    it('should not select branch when user does not have access', async () => {
      vi.mocked(authAPI.login).mockResolvedValue({
        access_token: 'test-token',
        user: mockUser, // has branch_ids: [1, 2]
      })
      await useAuthStore.getState().login('waiter@test.com', 'password')

      useAuthStore.getState().selectBranch(999)

      expect(useAuthStore.getState().selectedBranchId).toBeNull()
    })
  })

  describe('refreshAccessToken', () => {
    it('should return false when no refresh token', async () => {
      const result = await useAuthStore.getState().refreshAccessToken()
      expect(result).toBe(false)
    })

    it('should refresh token successfully', async () => {
      useAuthStore.setState({ refreshToken: 'refresh-token' })
      vi.mocked(authAPI.refresh).mockResolvedValue({
        access_token: 'new-access-token',
        refresh_token: 'new-refresh-token',
      })

      const result = await useAuthStore.getState().refreshAccessToken()

      expect(result).toBe(true)
      expect(useAuthStore.getState().token).toBe('new-access-token')
      expect(useAuthStore.getState().refreshToken).toBe('new-refresh-token')
      expect(useAuthStore.getState().refreshAttempts).toBe(0)
    })

    it('should increment attempt counter on failure', async () => {
      useAuthStore.setState({ refreshToken: 'refresh-token' })
      vi.mocked(authAPI.refresh).mockRejectedValue(new Error('Refresh failed'))

      const result = await useAuthStore.getState().refreshAccessToken()

      expect(result).toBe(false)
      expect(useAuthStore.getState().refreshAttempts).toBe(1)
    })

    it('should logout after max refresh attempts', async () => {
      useAuthStore.setState({
        refreshToken: 'refresh-token',
        refreshAttempts: 3, // MAX_REFRESH_ATTEMPTS
        isAuthenticated: true,
        user: mockUser,
      })

      const result = await useAuthStore.getState().refreshAccessToken()

      expect(result).toBe(false)
      expect(useAuthStore.getState().isAuthenticated).toBe(false)
      expect(useAuthStore.getState().user).toBeNull()
    })
  })

  describe('clearError', () => {
    it('should clear error', () => {
      useAuthStore.setState({ error: 'Some error' })

      useAuthStore.getState().clearError()

      expect(useAuthStore.getState().error).toBeNull()
    })
  })

  describe('selectors', () => {
    it('should return empty branch ids array when no user', () => {
      const result = selectUserBranchIds(useAuthStore.getState())
      expect(result).toEqual([])
    })

    it('should return user branch ids when logged in', async () => {
      vi.mocked(authAPI.login).mockResolvedValue({
        access_token: 'test-token',
        user: mockUser,
      })
      await useAuthStore.getState().login('waiter@test.com', 'password')

      const result = selectUserBranchIds(useAuthStore.getState())
      expect(result).toEqual([1, 2])
    })

    it('should return stable empty array reference for branch ids', () => {
      const state = useAuthStore.getState()
      const result1 = selectUserBranchIds(state)
      const result2 = selectUserBranchIds(state)
      expect(result1).toBe(result2) // Same reference
    })
  })
})
