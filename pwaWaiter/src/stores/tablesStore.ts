import { create } from 'zustand'
import { tablesAPI, roundsAPI, billingAPI, serviceCallsAPI, ApiError } from '../services/api'
import { wsService } from '../services/websocket'
import { notificationService } from '../services/notifications'
import { storeLogger } from '../utils/logger'
import { useRetryQueueStore } from './retryQueueStore'
import { useAuthStore } from './authStore'
import type { TableCard, WSEvent } from '../types'

// DEF-HIGH-03 FIX: Helper to check if error is retriable
function isRetriableError(err: unknown): boolean {
  if (err instanceof ApiError) {
    return err.code === 'NETWORK_ERROR' || err.code === 'TIMEOUT'
  }
  return !navigator.onLine
}

// WAITER-CRIT-03 FIX: Helper to handle 401 authentication errors
function handleAuthError(err: unknown): boolean {
  if (err instanceof ApiError && err.status === 401) {
    storeLogger.warn('Authentication error detected, logging out')
    useAuthStore.getState().logout()
    return true
  }
  return false
}

interface TablesState {
  tables: TableCard[]
  selectedTableId: number | null
  isLoading: boolean
  error: string | null
  wsConnected: boolean
  // Actions
  fetchTables: (branchId: number) => Promise<void>
  selectTable: (tableId: number | null) => void
  markRoundAsServed: (roundId: number) => Promise<void>
  confirmCashPayment: (checkId: number, amountCents: number) => Promise<void>
  clearTable: (tableId: number) => Promise<void>
  acknowledgeServiceCall: (serviceCallId: number) => Promise<void>
  resolveServiceCall: (serviceCallId: number) => Promise<void>
  // WebSocket
  subscribeToEvents: (branchId: number) => () => void
}

export const useTablesStore = create<TablesState>()((set, get) => ({
  tables: [],
  selectedTableId: null,
  isLoading: false,
  error: null,
  wsConnected: false,

  fetchTables: async (branchId: number) => {
    set({ isLoading: true, error: null })
    try {
      const tables = await tablesAPI.getTables(branchId)
      set({ tables, isLoading: false })
      storeLogger.info('Tables fetched', { count: tables.length })
    } catch (err) {
      // WAITER-CRIT-03 FIX: Handle 401 authentication errors
      if (handleAuthError(err)) {
        set({ isLoading: false })
        throw new Error('Session expired')
      }
      const message = err instanceof Error ? err.message : 'Error al cargar mesas'
      storeLogger.error('Failed to fetch tables', err)
      set({ error: message, isLoading: false })
    }
  },

  selectTable: (tableId: number | null) => {
    set({ selectedTableId: tableId })
  },

  markRoundAsServed: async (roundId: number) => {
    try {
      await roundsAPI.markAsServed(roundId)
      storeLogger.info('Round marked as served', { roundId })
      // The WebSocket event will update the state
    } catch (err) {
      // WAITER-CRIT-03 FIX: Handle 401 authentication errors
      if (handleAuthError(err)) {
        throw new Error('Session expired')
      }
      storeLogger.error('Failed to mark round as served', err)
      // DEF-HIGH-03 FIX: Queue for retry if network error
      if (isRetriableError(err)) {
        useRetryQueueStore.getState().enqueue('MARK_ROUND_SERVED', { roundId })
        storeLogger.info('Action queued for retry', { type: 'MARK_ROUND_SERVED', roundId })
      }
      throw err
    }
  },

  confirmCashPayment: async (checkId: number, amountCents: number) => {
    try {
      await billingAPI.confirmCashPayment(checkId, amountCents)
      storeLogger.info('Cash payment confirmed', { checkId, amountCents })
    } catch (err) {
      // WAITER-CRIT-03 FIX: Handle 401 authentication errors
      if (handleAuthError(err)) {
        throw new Error('Session expired')
      }
      storeLogger.error('Failed to confirm cash payment', err)
      throw err
    }
  },

  clearTable: async (tableId: number) => {
    try {
      await billingAPI.clearTable(tableId)
      storeLogger.info('Table cleared', { tableId })
    } catch (err) {
      // WAITER-CRIT-03 FIX: Handle 401 authentication errors
      if (handleAuthError(err)) {
        throw new Error('Session expired')
      }
      storeLogger.error('Failed to clear table', err)
      // DEF-HIGH-03 FIX: Queue for retry if network error
      if (isRetriableError(err)) {
        useRetryQueueStore.getState().enqueue('CLEAR_TABLE', { tableId })
        storeLogger.info('Action queued for retry', { type: 'CLEAR_TABLE', tableId })
      }
      throw err
    }
  },

  acknowledgeServiceCall: async (serviceCallId: number) => {
    try {
      await serviceCallsAPI.acknowledge(serviceCallId)
      storeLogger.info('Service call acknowledged', { serviceCallId })
    } catch (err) {
      // WAITER-CRIT-03 FIX: Handle 401 authentication errors
      if (handleAuthError(err)) {
        throw new Error('Session expired')
      }
      storeLogger.error('Failed to acknowledge service call', err)
      // DEF-HIGH-03 FIX: Queue for retry if network error
      if (isRetriableError(err)) {
        useRetryQueueStore.getState().enqueue('ACK_SERVICE_CALL', { serviceCallId })
        storeLogger.info('Action queued for retry', { type: 'ACK_SERVICE_CALL', serviceCallId })
      }
      throw err
    }
  },

  resolveServiceCall: async (serviceCallId: number) => {
    try {
      await serviceCallsAPI.resolve(serviceCallId)
      storeLogger.info('Service call resolved', { serviceCallId })
    } catch (err) {
      // WAITER-CRIT-03 FIX: Handle 401 authentication errors
      if (handleAuthError(err)) {
        throw new Error('Session expired')
      }
      storeLogger.error('Failed to resolve service call', err)
      // DEF-HIGH-03 FIX: Queue for retry if network error
      if (isRetriableError(err)) {
        useRetryQueueStore.getState().enqueue('RESOLVE_SERVICE_CALL', { serviceCallId })
        storeLogger.info('Action queued for retry', { type: 'RESOLVE_SERVICE_CALL', serviceCallId })
      }
      throw err
    }
  },

  subscribeToEvents: (branchId: number) => {
    // Subscribe to connection state changes
    const unsubscribeConnection = wsService.onConnectionChange((isConnected) => {
      set({ wsConnected: isConnected })
      storeLogger.info('WebSocket connection state changed', { isConnected })
    })

    // Subscribe to all events
    const unsubscribeEvents = wsService.on('*', (event: WSEvent) => {
      handleWSEvent(event, branchId, get, set)
      notificationService.notifyEvent(event)
    })

    storeLogger.info('Subscribed to WebSocket events')

    return () => {
      unsubscribeEvents()
      unsubscribeConnection()
      storeLogger.info('Unsubscribed from WebSocket events')
    }
  },
}))

// Handle WebSocket events
// Fetch only the affected table to avoid full refetch on every event
function handleWSEvent(
  event: WSEvent,
  branchId: number,
  get: () => TablesState,
  set: (state: Partial<TablesState>) => void
) {
  const { tables } = get()
  const tableIndex = tables.findIndex((t) => t.table_id === event.table_id)

  storeLogger.debug('Processing WS event', { type: event.type, tableId: event.table_id })

  // Events that require updating the table data
  const eventsRequiringUpdate = [
    'ROUND_SUBMITTED',
    'ROUND_IN_KITCHEN',
    'ROUND_READY',
    'ROUND_SERVED',
    'SERVICE_CALL_CREATED',
    'SERVICE_CALL_ACKNOWLEDGED',
    'CHECK_REQUESTED',
    'CHECK_PAID',
    'TABLE_CLEARED',
    'TABLE_STATUS_CHANGED',
    'PAYMENT_APPROVED',
    'PAYMENT_REJECTED',
  ]

  if (!eventsRequiringUpdate.includes(event.type)) {
    return
  }

  // TABLE_CLEARED may remove the table from active list, handle specially
  if (event.type === 'TABLE_CLEARED') {
    if (tableIndex !== -1) {
      // Update the table to FREE status locally first for immediate feedback
      const updatedTables = [...tables]
      updatedTables[tableIndex] = {
        ...updatedTables[tableIndex],
        status: 'FREE',
        session_id: null,
        open_rounds: 0,
        pending_calls: 0,
        check_status: null,
      }
      set({ tables: updatedTables })
      storeLogger.debug('Table cleared locally', { tableId: event.table_id })
    }
    return
  }

  // For other events, fetch only the affected table
  if (tableIndex === -1) {
    // Table not in our list yet, might be newly activated - do a full refresh
    tablesAPI.getTables(branchId).then((updatedTables) => {
      set({ tables: updatedTables })
      storeLogger.debug('Tables refreshed for new table', { tableId: event.table_id })
    }).catch((err) => {
      storeLogger.error('Failed to refresh tables', err)
    })
    return
  }

  // Fetch only the affected table and update it in place
  tablesAPI.getTable(event.table_id).then((updatedTable) => {
    const currentTables = get().tables
    const currentIndex = currentTables.findIndex((t) => t.table_id === event.table_id)

    if (currentIndex !== -1) {
      const newTables = [...currentTables]
      newTables[currentIndex] = updatedTable
      set({ tables: newTables })
      storeLogger.debug('Table updated incrementally', {
        type: event.type,
        tableId: event.table_id,
        status: updatedTable.status
      })
    }
  }).catch((err) => {
    storeLogger.error('Failed to fetch updated table', { tableId: event.table_id, error: err })
    // Fallback to full refresh on error
    tablesAPI.getTables(branchId).then((updatedTables) => {
      set({ tables: updatedTables })
    }).catch(() => {
      // Silently fail - we already logged the original error
    })
  })
}

// Selectors
export const selectTables = (state: TablesState) => state.tables
export const selectSelectedTableId = (state: TablesState) => state.selectedTableId
export const selectSelectedTable = (state: TablesState) =>
  state.tables.find((t) => t.table_id === state.selectedTableId) ?? null
export const selectIsLoading = (state: TablesState) => state.isLoading
export const selectError = (state: TablesState) => state.error
export const selectWsConnected = (state: TablesState) => state.wsConnected

// Derived selectors using TableCard fields
export const selectTablesWithPendingRounds = (state: TablesState) =>
  state.tables.filter((t) => t.open_rounds > 0)

export const selectTablesWithServiceCalls = (state: TablesState) =>
  state.tables.filter((t) => t.pending_calls > 0)

export const selectTablesWithCheckRequested = (state: TablesState) =>
  state.tables.filter((t) => t.status === 'PAYING' || t.check_status === 'REQUESTED')
