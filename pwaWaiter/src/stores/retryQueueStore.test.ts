import { describe, it, expect, vi, beforeEach } from 'vitest'
import {
  useRetryQueueStore,
  selectQueuedActions,
  selectQueueLength,
  selectIsProcessing,
} from './retryQueueStore'

// Mock dependencies
vi.mock('../services/api', () => ({
  roundsAPI: {
    markAsServed: vi.fn(),
  },
  serviceCallsAPI: {
    acknowledge: vi.fn(),
    resolve: vi.fn(),
  },
  billingAPI: {
    clearTable: vi.fn(),
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

vi.mock('../utils/logger', () => ({
  storeLogger: {
    info: vi.fn(),
    warn: vi.fn(),
    error: vi.fn(),
    debug: vi.fn(),
  },
}))

// Import mocked modules
import { roundsAPI, serviceCallsAPI, billingAPI, ApiError } from '../services/api'

// Mock navigator.onLine
const navigatorOnLine = {
  value: true,
}
Object.defineProperty(navigator, 'onLine', {
  get: () => navigatorOnLine.value,
  configurable: true,
})

describe('retryQueueStore', () => {
  beforeEach(() => {
    // Reset store to initial state
    useRetryQueueStore.setState({
      queue: [],
      isProcessing: false,
    })
    vi.clearAllMocks()
    navigatorOnLine.value = true
  })

  describe('initial state', () => {
    it('should have correct initial state', () => {
      const state = useRetryQueueStore.getState()
      expect(state.queue).toEqual([])
      expect(state.isProcessing).toBe(false)
    })
  })

  describe('enqueue', () => {
    it('should add action to queue', () => {
      // Prevent immediate processing
      navigatorOnLine.value = false

      useRetryQueueStore.getState().enqueue('MARK_ROUND_SERVED', { roundId: 123 })

      const state = useRetryQueueStore.getState()
      expect(state.queue).toHaveLength(1)
      expect(state.queue[0].type).toBe('MARK_ROUND_SERVED')
      expect(state.queue[0].payload).toEqual({ roundId: 123 })
      expect(state.queue[0].retryCount).toBe(0)
    })

    it('should not add duplicate actions', () => {
      navigatorOnLine.value = false

      useRetryQueueStore.getState().enqueue('MARK_ROUND_SERVED', { roundId: 123 })
      useRetryQueueStore.getState().enqueue('MARK_ROUND_SERVED', { roundId: 123 })

      expect(useRetryQueueStore.getState().queue).toHaveLength(1)
    })

    it('should allow same action type with different entity ID', () => {
      navigatorOnLine.value = false

      useRetryQueueStore.getState().enqueue('MARK_ROUND_SERVED', { roundId: 123 })
      useRetryQueueStore.getState().enqueue('MARK_ROUND_SERVED', { roundId: 456 })

      expect(useRetryQueueStore.getState().queue).toHaveLength(2)
    })

    it('should process queue immediately if online', async () => {
      navigatorOnLine.value = true
      vi.mocked(roundsAPI.markAsServed).mockResolvedValue(undefined)

      useRetryQueueStore.getState().enqueue('MARK_ROUND_SERVED', { roundId: 123 })

      // Wait for async processing
      await new Promise((resolve) => setTimeout(resolve, 10))

      expect(roundsAPI.markAsServed).toHaveBeenCalledWith(123)
    })
  })

  describe('processQueue', () => {
    it('should not process when offline', async () => {
      navigatorOnLine.value = false
      useRetryQueueStore.setState({
        queue: [{
          id: 'test-1',
          type: 'MARK_ROUND_SERVED',
          payload: { roundId: 123 },
          createdAt: new Date().toISOString(),
          retryCount: 0,
        }],
      })

      await useRetryQueueStore.getState().processQueue()

      expect(roundsAPI.markAsServed).not.toHaveBeenCalled()
    })

    it('should not process when queue is empty', async () => {
      await useRetryQueueStore.getState().processQueue()
      expect(roundsAPI.markAsServed).not.toHaveBeenCalled()
    })

    it('should not process when already processing', async () => {
      useRetryQueueStore.setState({
        isProcessing: true,
        queue: [{
          id: 'test-1',
          type: 'MARK_ROUND_SERVED',
          payload: { roundId: 123 },
          createdAt: new Date().toISOString(),
          retryCount: 0,
        }],
      })

      await useRetryQueueStore.getState().processQueue()
      expect(roundsAPI.markAsServed).not.toHaveBeenCalled()
    })

    it('should execute MARK_ROUND_SERVED action', async () => {
      vi.mocked(roundsAPI.markAsServed).mockResolvedValue(undefined)
      useRetryQueueStore.setState({
        queue: [{
          id: 'test-1',
          type: 'MARK_ROUND_SERVED',
          payload: { roundId: 123 },
          createdAt: new Date().toISOString(),
          retryCount: 0,
        }],
      })

      await useRetryQueueStore.getState().processQueue()

      expect(roundsAPI.markAsServed).toHaveBeenCalledWith(123)
      expect(useRetryQueueStore.getState().queue).toHaveLength(0)
    })

    it('should execute ACK_SERVICE_CALL action', async () => {
      vi.mocked(serviceCallsAPI.acknowledge).mockResolvedValue(undefined)
      useRetryQueueStore.setState({
        queue: [{
          id: 'test-1',
          type: 'ACK_SERVICE_CALL',
          payload: { serviceCallId: 50 },
          createdAt: new Date().toISOString(),
          retryCount: 0,
        }],
      })

      await useRetryQueueStore.getState().processQueue()

      expect(serviceCallsAPI.acknowledge).toHaveBeenCalledWith(50)
    })

    it('should execute RESOLVE_SERVICE_CALL action', async () => {
      vi.mocked(serviceCallsAPI.resolve).mockResolvedValue(undefined)
      useRetryQueueStore.setState({
        queue: [{
          id: 'test-1',
          type: 'RESOLVE_SERVICE_CALL',
          payload: { serviceCallId: 50 },
          createdAt: new Date().toISOString(),
          retryCount: 0,
        }],
      })

      await useRetryQueueStore.getState().processQueue()

      expect(serviceCallsAPI.resolve).toHaveBeenCalledWith(50)
    })

    it('should execute CLEAR_TABLE action', async () => {
      vi.mocked(billingAPI.clearTable).mockResolvedValue(undefined)
      useRetryQueueStore.setState({
        queue: [{
          id: 'test-1',
          type: 'CLEAR_TABLE',
          payload: { tableId: 1 },
          createdAt: new Date().toISOString(),
          retryCount: 0,
        }],
      })

      await useRetryQueueStore.getState().processQueue()

      expect(billingAPI.clearTable).toHaveBeenCalledWith(1)
    })

    it('should retry network errors up to max retries', async () => {
      const networkError = new ApiError('Network failed', 'NETWORK_ERROR')
      vi.mocked(roundsAPI.markAsServed).mockRejectedValue(networkError)
      useRetryQueueStore.setState({
        queue: [{
          id: 'test-1',
          type: 'MARK_ROUND_SERVED',
          payload: { roundId: 123 },
          createdAt: new Date().toISOString(),
          retryCount: 0,
        }],
      })

      await useRetryQueueStore.getState().processQueue()

      const state = useRetryQueueStore.getState()
      expect(state.queue).toHaveLength(1)
      expect(state.queue[0].retryCount).toBe(1)
      expect(state.queue[0].lastError).toBe('Network failed')
    })

    it('should discard action after max retries', async () => {
      const networkError = new ApiError('Network failed', 'NETWORK_ERROR')
      vi.mocked(roundsAPI.markAsServed).mockRejectedValue(networkError)
      useRetryQueueStore.setState({
        queue: [{
          id: 'test-1',
          type: 'MARK_ROUND_SERVED',
          payload: { roundId: 123 },
          createdAt: new Date().toISOString(),
          retryCount: 3, // MAX_RETRIES
        }],
      })

      await useRetryQueueStore.getState().processQueue()

      expect(useRetryQueueStore.getState().queue).toHaveLength(0)
    })

    it('should discard action on non-network errors', async () => {
      const authError = new ApiError('Not found', 'NOT_FOUND', 404)
      vi.mocked(roundsAPI.markAsServed).mockRejectedValue(authError)
      useRetryQueueStore.setState({
        queue: [{
          id: 'test-1',
          type: 'MARK_ROUND_SERVED',
          payload: { roundId: 123 },
          createdAt: new Date().toISOString(),
          retryCount: 0,
        }],
      })

      await useRetryQueueStore.getState().processQueue()

      expect(useRetryQueueStore.getState().queue).toHaveLength(0)
    })

    it('should process multiple actions', async () => {
      vi.mocked(roundsAPI.markAsServed).mockResolvedValue(undefined)
      vi.mocked(serviceCallsAPI.acknowledge).mockResolvedValue(undefined)
      useRetryQueueStore.setState({
        queue: [
          {
            id: 'test-1',
            type: 'MARK_ROUND_SERVED',
            payload: { roundId: 123 },
            createdAt: new Date().toISOString(),
            retryCount: 0,
          },
          {
            id: 'test-2',
            type: 'ACK_SERVICE_CALL',
            payload: { serviceCallId: 50 },
            createdAt: new Date().toISOString(),
            retryCount: 0,
          },
        ],
      })

      await useRetryQueueStore.getState().processQueue()

      expect(roundsAPI.markAsServed).toHaveBeenCalledWith(123)
      expect(serviceCallsAPI.acknowledge).toHaveBeenCalledWith(50)
      expect(useRetryQueueStore.getState().queue).toHaveLength(0)
    })
  })

  describe('removeAction', () => {
    it('should remove action by id', () => {
      useRetryQueueStore.setState({
        queue: [
          {
            id: 'test-1',
            type: 'MARK_ROUND_SERVED',
            payload: { roundId: 123 },
            createdAt: new Date().toISOString(),
            retryCount: 0,
          },
          {
            id: 'test-2',
            type: 'ACK_SERVICE_CALL',
            payload: { serviceCallId: 50 },
            createdAt: new Date().toISOString(),
            retryCount: 0,
          },
        ],
      })

      useRetryQueueStore.getState().removeAction('test-1')

      const state = useRetryQueueStore.getState()
      expect(state.queue).toHaveLength(1)
      expect(state.queue[0].id).toBe('test-2')
    })
  })

  describe('clearQueue', () => {
    it('should clear all actions', () => {
      useRetryQueueStore.setState({
        queue: [
          {
            id: 'test-1',
            type: 'MARK_ROUND_SERVED',
            payload: { roundId: 123 },
            createdAt: new Date().toISOString(),
            retryCount: 0,
          },
        ],
      })

      useRetryQueueStore.getState().clearQueue()

      expect(useRetryQueueStore.getState().queue).toHaveLength(0)
    })
  })

  describe('selectors', () => {
    it('selectQueuedActions should return queue', () => {
      const mockQueue = [
        {
          id: 'test-1',
          type: 'MARK_ROUND_SERVED' as const,
          payload: { roundId: 123 },
          createdAt: new Date().toISOString(),
          retryCount: 0,
        },
      ]
      useRetryQueueStore.setState({ queue: mockQueue })

      expect(selectQueuedActions(useRetryQueueStore.getState())).toEqual(mockQueue)
    })

    it('selectQueueLength should return queue length', () => {
      useRetryQueueStore.setState({
        queue: [
          {
            id: 'test-1',
            type: 'MARK_ROUND_SERVED',
            payload: { roundId: 123 },
            createdAt: new Date().toISOString(),
            retryCount: 0,
          },
          {
            id: 'test-2',
            type: 'ACK_SERVICE_CALL',
            payload: { serviceCallId: 50 },
            createdAt: new Date().toISOString(),
            retryCount: 0,
          },
        ],
      })

      expect(selectQueueLength(useRetryQueueStore.getState())).toBe(2)
    })

    it('selectIsProcessing should return processing state', () => {
      useRetryQueueStore.setState({ isProcessing: true })

      expect(selectIsProcessing(useRetryQueueStore.getState())).toBe(true)
    })
  })
})
