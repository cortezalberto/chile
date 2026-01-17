import { describe, it, expect, vi, beforeEach } from 'vitest'
import {
  useTablesStore,
  selectTables,
  selectSelectedTableId,
  selectSelectedTable,
  selectTablesWithPendingRounds,
  selectTablesWithServiceCalls,
  selectTablesWithCheckRequested,
  selectIsLoading,
  selectError,
  selectWsConnected,
} from './tablesStore'

// Mock enqueue function
const mockEnqueue = vi.fn()

// Mock dependencies
vi.mock('../services/api', () => ({
  tablesAPI: {
    getTables: vi.fn(),
    getTable: vi.fn(),
  },
  roundsAPI: {
    markAsServed: vi.fn(),
  },
  billingAPI: {
    confirmCashPayment: vi.fn(),
    clearTable: vi.fn(),
  },
  serviceCallsAPI: {
    acknowledge: vi.fn(),
    resolve: vi.fn(),
  },
  ApiError: class ApiError extends Error {
    code: string
    status: number
    constructor(message: string, code: string, status = 500) {
      super(message)
      this.code = code
      this.status = status
    }
  },
}))

vi.mock('../services/websocket', () => ({
  wsService: {
    on: vi.fn().mockReturnValue(() => {}),
    onConnectionChange: vi.fn().mockReturnValue(() => {}),
  },
}))

vi.mock('../services/notifications', () => ({
  notificationService: {
    notifyEvent: vi.fn(),
  },
}))

vi.mock('../utils/logger', () => ({
  storeLogger: {
    info: vi.fn(),
    warn: vi.fn(),
    error: vi.fn(),
    debug: vi.fn(),
  },
}))

vi.mock('./retryQueueStore', () => ({
  useRetryQueueStore: {
    getState: () => ({
      enqueue: mockEnqueue,
    }),
  },
}))

vi.mock('./authStore', () => ({
  useAuthStore: {
    getState: () => ({
      logout: vi.fn(),
    }),
  },
}))

// Import mocked modules
import { tablesAPI, roundsAPI, billingAPI, serviceCallsAPI, ApiError } from '../services/api'
import { wsService } from '../services/websocket'

const mockTables = [
  {
    table_id: 1,
    table_code: 'T-01',
    capacity: 4,
    status: 'ACTIVE',
    session_id: 100,
    diner_count: 2,
    open_rounds: 1,
    pending_calls: 0,
    check_status: null,
  },
  {
    table_id: 2,
    table_code: 'T-02',
    capacity: 6,
    status: 'FREE',
    session_id: null,
    diner_count: 0,
    open_rounds: 0,
    pending_calls: 0,
    check_status: null,
  },
  {
    table_id: 3,
    table_code: 'T-03',
    capacity: 4,
    status: 'PAYING',
    session_id: 101,
    diner_count: 3,
    open_rounds: 0,
    pending_calls: 1,
    check_status: 'REQUESTED',
  },
]

describe('tablesStore', () => {
  beforeEach(() => {
    // Reset store to initial state
    useTablesStore.setState({
      tables: [],
      selectedTableId: null,
      isLoading: false,
      error: null,
      wsConnected: false,
    })
    vi.clearAllMocks()
  })

  describe('initial state', () => {
    it('should have correct initial state', () => {
      const state = useTablesStore.getState()
      expect(state.tables).toEqual([])
      expect(state.selectedTableId).toBeNull()
      expect(state.isLoading).toBe(false)
      expect(state.error).toBeNull()
      expect(state.wsConnected).toBe(false)
    })
  })

  describe('fetchTables', () => {
    it('should fetch tables successfully', async () => {
      vi.mocked(tablesAPI.getTables).mockResolvedValue(mockTables)

      await useTablesStore.getState().fetchTables(1)

      const state = useTablesStore.getState()
      expect(state.tables).toEqual(mockTables)
      expect(state.isLoading).toBe(false)
      expect(state.error).toBeNull()
      expect(tablesAPI.getTables).toHaveBeenCalledWith(1)
    })

    it('should handle fetch error', async () => {
      vi.mocked(tablesAPI.getTables).mockRejectedValue(new Error('Network error'))

      await useTablesStore.getState().fetchTables(1)

      const state = useTablesStore.getState()
      expect(state.tables).toEqual([])
      expect(state.error).toBe('Network error')
      expect(state.isLoading).toBe(false)
    })

    it('should set isLoading during fetch', async () => {
      let resolveFetch: (value: unknown) => void
      vi.mocked(tablesAPI.getTables).mockImplementation(
        () => new Promise((resolve) => { resolveFetch = resolve })
      )

      const fetchPromise = useTablesStore.getState().fetchTables(1)
      expect(useTablesStore.getState().isLoading).toBe(true)

      resolveFetch!(mockTables)
      await fetchPromise
      expect(useTablesStore.getState().isLoading).toBe(false)
    })

    it('should handle 401 authentication error and logout', async () => {
      const authError = new ApiError('Unauthorized', 'AUTH_ERROR', 401)
      vi.mocked(tablesAPI.getTables).mockRejectedValue(authError)

      await expect(useTablesStore.getState().fetchTables(1)).rejects.toThrow('Session expired')
      expect(useTablesStore.getState().isLoading).toBe(false)
    })
  })

  describe('selectTable', () => {
    it('should select a table', () => {
      useTablesStore.getState().selectTable(1)
      expect(useTablesStore.getState().selectedTableId).toBe(1)
    })

    it('should deselect a table', () => {
      useTablesStore.setState({ selectedTableId: 1 })
      useTablesStore.getState().selectTable(null)
      expect(useTablesStore.getState().selectedTableId).toBeNull()
    })
  })

  describe('markRoundAsServed', () => {
    it('should mark round as served successfully', async () => {
      vi.mocked(roundsAPI.markAsServed).mockResolvedValue(undefined)

      await useTablesStore.getState().markRoundAsServed(123)

      expect(roundsAPI.markAsServed).toHaveBeenCalledWith(123)
    })

    it('should queue action on network error', async () => {
      const networkError = new ApiError('Network failed', 'NETWORK_ERROR')
      vi.mocked(roundsAPI.markAsServed).mockRejectedValue(networkError)

      await expect(useTablesStore.getState().markRoundAsServed(123)).rejects.toThrow()
      expect(mockEnqueue).toHaveBeenCalledWith('MARK_ROUND_SERVED', { roundId: 123 })
    })

    it('should logout on 401 error', async () => {
      const authError = new ApiError('Unauthorized', 'AUTH_ERROR', 401)
      vi.mocked(roundsAPI.markAsServed).mockRejectedValue(authError)

      await expect(useTablesStore.getState().markRoundAsServed(123)).rejects.toThrow('Session expired')
    })
  })

  describe('confirmCashPayment', () => {
    it('should confirm cash payment successfully', async () => {
      vi.mocked(billingAPI.confirmCashPayment).mockResolvedValue(undefined)

      await useTablesStore.getState().confirmCashPayment(100, 5000)

      expect(billingAPI.confirmCashPayment).toHaveBeenCalledWith(100, 5000)
    })

    it('should throw on error', async () => {
      vi.mocked(billingAPI.confirmCashPayment).mockRejectedValue(new Error('Payment failed'))

      await expect(useTablesStore.getState().confirmCashPayment(100, 5000)).rejects.toThrow('Payment failed')
    })
  })

  describe('clearTable', () => {
    it('should clear table successfully', async () => {
      vi.mocked(billingAPI.clearTable).mockResolvedValue(undefined)

      await useTablesStore.getState().clearTable(1)

      expect(billingAPI.clearTable).toHaveBeenCalledWith(1)
    })

    it('should queue action on network error', async () => {
      const networkError = new ApiError('Network failed', 'NETWORK_ERROR')
      vi.mocked(billingAPI.clearTable).mockRejectedValue(networkError)

      await expect(useTablesStore.getState().clearTable(1)).rejects.toThrow()
      expect(mockEnqueue).toHaveBeenCalledWith('CLEAR_TABLE', { tableId: 1 })
    })
  })

  describe('acknowledgeServiceCall', () => {
    it('should acknowledge service call successfully', async () => {
      vi.mocked(serviceCallsAPI.acknowledge).mockResolvedValue(undefined)

      await useTablesStore.getState().acknowledgeServiceCall(50)

      expect(serviceCallsAPI.acknowledge).toHaveBeenCalledWith(50)
    })

    it('should queue action on network error', async () => {
      const networkError = new ApiError('Network failed', 'TIMEOUT')
      vi.mocked(serviceCallsAPI.acknowledge).mockRejectedValue(networkError)

      await expect(useTablesStore.getState().acknowledgeServiceCall(50)).rejects.toThrow()
      expect(mockEnqueue).toHaveBeenCalledWith('ACK_SERVICE_CALL', { serviceCallId: 50 })
    })
  })

  describe('resolveServiceCall', () => {
    it('should resolve service call successfully', async () => {
      vi.mocked(serviceCallsAPI.resolve).mockResolvedValue(undefined)

      await useTablesStore.getState().resolveServiceCall(50)

      expect(serviceCallsAPI.resolve).toHaveBeenCalledWith(50)
    })

    it('should queue action on network error', async () => {
      const networkError = new ApiError('Network failed', 'NETWORK_ERROR')
      vi.mocked(serviceCallsAPI.resolve).mockRejectedValue(networkError)

      await expect(useTablesStore.getState().resolveServiceCall(50)).rejects.toThrow()
      expect(mockEnqueue).toHaveBeenCalledWith('RESOLVE_SERVICE_CALL', { serviceCallId: 50 })
    })
  })

  describe('subscribeToEvents', () => {
    it('should subscribe to WebSocket events', () => {
      const unsubscribe = useTablesStore.getState().subscribeToEvents(1)

      expect(wsService.onConnectionChange).toHaveBeenCalled()
      expect(wsService.on).toHaveBeenCalledWith('*', expect.any(Function))
      expect(typeof unsubscribe).toBe('function')
    })

    it('should return cleanup function', () => {
      const mockUnsubscribeConnection = vi.fn()
      const mockUnsubscribeEvents = vi.fn()
      vi.mocked(wsService.onConnectionChange).mockReturnValue(mockUnsubscribeConnection)
      vi.mocked(wsService.on).mockReturnValue(mockUnsubscribeEvents)

      const unsubscribe = useTablesStore.getState().subscribeToEvents(1)
      unsubscribe()

      expect(mockUnsubscribeConnection).toHaveBeenCalled()
      expect(mockUnsubscribeEvents).toHaveBeenCalled()
    })
  })

  describe('selectors', () => {
    beforeEach(() => {
      useTablesStore.setState({ tables: mockTables })
    })

    it('selectTables should return all tables', () => {
      expect(selectTables(useTablesStore.getState())).toEqual(mockTables)
    })

    it('selectSelectedTableId should return selected table id', () => {
      useTablesStore.setState({ selectedTableId: 2 })
      expect(selectSelectedTableId(useTablesStore.getState())).toBe(2)
    })

    it('selectSelectedTable should return selected table', () => {
      useTablesStore.setState({ selectedTableId: 1 })
      expect(selectSelectedTable(useTablesStore.getState())).toEqual(mockTables[0])
    })

    it('selectSelectedTable should return null when no table selected', () => {
      expect(selectSelectedTable(useTablesStore.getState())).toBeNull()
    })

    it('selectTablesWithPendingRounds should return tables with open rounds', () => {
      const result = selectTablesWithPendingRounds(useTablesStore.getState())
      expect(result).toHaveLength(1)
      expect(result[0].table_id).toBe(1)
    })

    it('selectTablesWithServiceCalls should return tables with pending calls', () => {
      const result = selectTablesWithServiceCalls(useTablesStore.getState())
      expect(result).toHaveLength(1)
      expect(result[0].table_id).toBe(3)
    })

    it('selectTablesWithCheckRequested should return tables in PAYING status or check requested', () => {
      const result = selectTablesWithCheckRequested(useTablesStore.getState())
      expect(result).toHaveLength(1)
      expect(result[0].table_id).toBe(3)
    })

    it('selectIsLoading should return loading state', () => {
      useTablesStore.setState({ isLoading: true })
      expect(selectIsLoading(useTablesStore.getState())).toBe(true)
    })

    it('selectError should return error state', () => {
      useTablesStore.setState({ error: 'Test error' })
      expect(selectError(useTablesStore.getState())).toBe('Test error')
    })

    it('selectWsConnected should return WebSocket connection state', () => {
      useTablesStore.setState({ wsConnected: true })
      expect(selectWsConnected(useTablesStore.getState())).toBe(true)
    })
  })
})
