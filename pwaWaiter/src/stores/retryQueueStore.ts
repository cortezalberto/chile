import { create } from 'zustand'
import { persist, createJSONStorage } from 'zustand/middleware'
import { storeLogger } from '../utils/logger'
import { roundsAPI, serviceCallsAPI, billingAPI } from '../services/api'
import { ApiError } from '../services/api'

/**
 * PWAW-A007: Retry queue for offline actions
 *
 * Queues failed API actions when offline and retries them when online.
 * Actions are persisted in localStorage to survive app restarts.
 */

// Action types that can be queued
export type QueuedActionType =
  | 'MARK_ROUND_SERVED'
  | 'ACK_SERVICE_CALL'
  | 'RESOLVE_SERVICE_CALL'
  | 'CLEAR_TABLE'

export interface QueuedAction {
  id: string
  type: QueuedActionType
  payload: Record<string, unknown>
  createdAt: string
  retryCount: number
  lastError?: string
}

interface RetryQueueState {
  queue: QueuedAction[]
  isProcessing: boolean
  // Actions
  enqueue: (type: QueuedActionType, payload: Record<string, unknown>) => void
  processQueue: () => Promise<void>
  removeAction: (id: string) => void
  clearQueue: () => void
}

const STORAGE_KEY = 'waiter-retry-queue'
const MAX_RETRIES = 3

// Execute a queued action
async function executeAction(action: QueuedAction): Promise<void> {
  switch (action.type) {
    case 'MARK_ROUND_SERVED':
      await roundsAPI.markAsServed(action.payload.roundId as number)
      break
    case 'ACK_SERVICE_CALL':
      await serviceCallsAPI.acknowledge(action.payload.serviceCallId as number)
      break
    case 'RESOLVE_SERVICE_CALL':
      await serviceCallsAPI.resolve(action.payload.serviceCallId as number)
      break
    case 'CLEAR_TABLE':
      await billingAPI.clearTable(action.payload.tableId as number)
      break
    default:
      throw new Error(`Unknown action type: ${action.type}`)
  }
}

export const useRetryQueueStore = create<RetryQueueState>()(
  persist(
    (set, get) => ({
      queue: [],
      isProcessing: false,

      enqueue: (type: QueuedActionType, payload: Record<string, unknown>) => {
        // WAITER-HIGH-01 FIX: Deduplicate by type + entity ID
        const entityId = payload.id || payload.roundId || payload.tableId || payload.serviceCallId
        const key = `${type}_${entityId}`

        const { queue } = get()
        const exists = queue.some((item) => {
          const itemEntityId =
            item.payload.id ||
            item.payload.roundId ||
            item.payload.tableId ||
            item.payload.serviceCallId
          const itemKey = `${item.type}_${itemEntityId}`
          return itemKey === key
        })

        if (exists) {
          storeLogger.info('Action already queued, skipping duplicate', { type, key })
          return
        }

        const action: QueuedAction = {
          id: crypto.randomUUID(),
          type,
          payload,
          createdAt: new Date().toISOString(),
          retryCount: 0,
        }

        set((state) => ({
          queue: [...state.queue, action],
        }))

        storeLogger.info('Action enqueued for retry', { type, payload })

        // CRIT-11 FIX: Use debounced processing to prevent race conditions
        // Only process if online and not already processing
        if (navigator.onLine && !get().isProcessing) {
          // Use setTimeout to batch multiple enqueues
          setTimeout(() => {
            if (!get().isProcessing) {
              get().processQueue()
            }
          }, 100)
        }
      },

      processQueue: async () => {
        const { queue, isProcessing } = get()

        // Skip if already processing or queue is empty
        if (isProcessing || queue.length === 0) return

        // Skip if offline
        if (!navigator.onLine) {
          storeLogger.debug('Offline - skipping queue processing')
          return
        }

        set({ isProcessing: true })
        storeLogger.info('Processing retry queue', { queueLength: queue.length })

        const failedActions: QueuedAction[] = []

        for (const action of queue) {
          try {
            await executeAction(action)
            storeLogger.info('Queued action executed successfully', {
              type: action.type,
              id: action.id,
            })
          } catch (error) {
            const errorMessage =
              error instanceof ApiError ? error.message : 'Unknown error'

            // Network errors should be retried
            if (
              error instanceof ApiError &&
              (error.code === 'NETWORK_ERROR' || error.code === 'TIMEOUT')
            ) {
              if (action.retryCount < MAX_RETRIES) {
                failedActions.push({
                  ...action,
                  retryCount: action.retryCount + 1,
                  lastError: errorMessage,
                })
                storeLogger.warn('Action will be retried', {
                  type: action.type,
                  retryCount: action.retryCount + 1,
                })
              } else {
                storeLogger.error('Action exceeded max retries, discarding', {
                  type: action.type,
                  id: action.id,
                })
              }
            } else {
              // Non-network errors (e.g., 404, 403) should be discarded
              storeLogger.error('Action failed permanently', {
                type: action.type,
                error: errorMessage,
              })
            }
          }
        }

        set({
          queue: failedActions,
          isProcessing: false,
        })
      },

      removeAction: (id: string) => {
        set((state) => ({
          queue: state.queue.filter((a) => a.id !== id),
        }))
      },

      clearQueue: () => {
        set({ queue: [] })
        storeLogger.info('Retry queue cleared')
      },
    }),
    {
      name: STORAGE_KEY,
      version: 1,
      storage: createJSONStorage(() => localStorage),
      partialize: (state) => ({
        queue: state.queue,
      }),
    }
  )
)

// Selectors
export const selectQueuedActions = (state: RetryQueueState) => state.queue
export const selectQueueLength = (state: RetryQueueState) => state.queue.length
export const selectIsProcessing = (state: RetryQueueState) => state.isProcessing

// CRIT-29-02 FIX: Guard against duplicate listener registration
// Track whether listener is already registered to prevent memory leaks on HMR/re-initialization
let onlineListenerRegistered = false
// WAITER-STORE-CRIT-02 FIX: Store reference to cleanup function for testability
let onlineListenerCleanup: (() => void) | null = null

// Process queue when coming back online
if (typeof window !== 'undefined' && !onlineListenerRegistered) {
  onlineListenerRegistered = true

  const handleOnline = () => {
    storeLogger.info('Back online - processing retry queue')
    useRetryQueueStore.getState().processQueue()
  }

  window.addEventListener('online', handleOnline)

  // WAITER-STORE-CRIT-02 FIX: Export cleanup function
  onlineListenerCleanup = () => {
    window.removeEventListener('online', handleOnline)
    onlineListenerRegistered = false
    onlineListenerCleanup = null
    storeLogger.debug('Online listener removed')
  }
}

/**
 * WAITER-STORE-CRIT-02 FIX: Cleanup function to remove the global online listener.
 * Call this in test teardown or when unmounting the app.
 */
export function cleanupOnlineListener(): void {
  if (onlineListenerCleanup) {
    onlineListenerCleanup()
  }
}
