import { create } from 'zustand'
import {
  tablesAPI,
  roundsAPI,
  billingAPI,
  serviceCallsAPI,
  waiterTableAPI,
  ApiError,
} from '../services/api'
import type {
  WaiterActivateTableRequest,
  WaiterActivateTableResponse,
  WaiterSubmitRoundRequest,
  WaiterSubmitRoundResponse,
  WaiterRequestCheckResponse,
  ManualPaymentRequest,
  ManualPaymentResponse,
  WaiterCloseTableResponse,
  WaiterSessionSummary,
} from '../services/api'
import { wsService } from '../services/websocket'
import { notificationService } from '../services/notifications'
import { storeLogger } from '../utils/logger'
// MED-08 FIX: Import WS event constants to avoid magic strings
import { WS_EVENT_TYPES } from '../utils/constants'
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
  // Current session being managed by waiter (for waiter-managed flow)
  activeSession: WaiterSessionSummary | null
  // Actions
  fetchTables: (branchId: number) => Promise<void>
  selectTable: (tableId: number | null) => void
  markRoundAsServed: (roundId: number) => Promise<void>
  confirmCashPayment: (checkId: number, amountCents: number) => Promise<void>
  clearTable: (tableId: number) => Promise<void>
  acknowledgeServiceCall: (serviceCallId: number) => Promise<void>
  resolveServiceCall: (serviceCallId: number) => Promise<void>
  // HU-WAITER-MESA: Waiter-managed table flow actions
  activateTable: (tableId: number, data: WaiterActivateTableRequest) => Promise<WaiterActivateTableResponse>
  submitRound: (sessionId: number, data: WaiterSubmitRoundRequest) => Promise<WaiterSubmitRoundResponse>
  requestCheck: (sessionId: number) => Promise<WaiterRequestCheckResponse>
  registerManualPayment: (data: ManualPaymentRequest) => Promise<ManualPaymentResponse>
  closeTableSession: (tableId: number, force?: boolean) => Promise<WaiterCloseTableResponse>
  fetchSessionSummary: (sessionId: number) => Promise<WaiterSessionSummary>
  clearActiveSession: () => void
  // WebSocket
  subscribeToEvents: (branchId: number) => () => void
}

export const useTablesStore = create<TablesState>()((set, get) => ({
  tables: [],
  selectedTableId: null,
  isLoading: false,
  error: null,
  wsConnected: false,
  activeSession: null,

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

  // ==========================================================================
  // HU-WAITER-MESA: Waiter-Managed Table Flow Actions
  // ==========================================================================

  activateTable: async (tableId: number, data: WaiterActivateTableRequest) => {
    try {
      const response = await waiterTableAPI.activateTable(tableId, data)
      storeLogger.info('Table activated by waiter', {
        tableId,
        sessionId: response.session_id,
        dinerCount: data.diner_count,
      })

      // Fetch session summary to populate activeSession
      const sessionSummary = await waiterTableAPI.getSessionSummary(response.session_id)
      set({ activeSession: sessionSummary })

      return response
    } catch (err) {
      if (handleAuthError(err)) {
        throw new Error('Session expired')
      }
      storeLogger.error('Failed to activate table', err)
      throw err
    }
  },

  submitRound: async (sessionId: number, data: WaiterSubmitRoundRequest) => {
    try {
      const response = await waiterTableAPI.submitRound(sessionId, data)
      storeLogger.info('Round submitted by waiter', {
        sessionId,
        roundId: response.round_id,
        roundNumber: response.round_number,
        itemsCount: response.items_count,
        totalCents: response.total_cents,
      })

      // Refresh session summary
      const sessionSummary = await waiterTableAPI.getSessionSummary(sessionId)
      set({ activeSession: sessionSummary })

      return response
    } catch (err) {
      if (handleAuthError(err)) {
        throw new Error('Session expired')
      }
      storeLogger.error('Failed to submit round', err)
      // Queue for retry if network error
      if (isRetriableError(err)) {
        useRetryQueueStore.getState().enqueue('SUBMIT_ROUND', { sessionId, data })
        storeLogger.info('Action queued for retry', { type: 'SUBMIT_ROUND', sessionId })
      }
      throw err
    }
  },

  requestCheck: async (sessionId: number) => {
    try {
      const response = await waiterTableAPI.requestCheck(sessionId)
      storeLogger.info('Check requested by waiter', {
        sessionId,
        checkId: response.check_id,
        totalCents: response.total_cents,
      })

      // Refresh session summary
      const sessionSummary = await waiterTableAPI.getSessionSummary(sessionId)
      set({ activeSession: sessionSummary })

      return response
    } catch (err) {
      if (handleAuthError(err)) {
        throw new Error('Session expired')
      }
      storeLogger.error('Failed to request check', err)
      throw err
    }
  },

  registerManualPayment: async (data: ManualPaymentRequest) => {
    try {
      const response = await waiterTableAPI.registerManualPayment(data)
      storeLogger.info('Manual payment registered', {
        checkId: data.check_id,
        paymentId: response.payment_id,
        amountCents: data.amount_cents,
        method: data.manual_method,
        checkStatus: response.check_status,
      })

      // Refresh session summary if we have an active session
      const { activeSession } = get()
      if (activeSession) {
        const sessionSummary = await waiterTableAPI.getSessionSummary(activeSession.session_id)
        set({ activeSession: sessionSummary })
      }

      return response
    } catch (err) {
      if (handleAuthError(err)) {
        throw new Error('Session expired')
      }
      storeLogger.error('Failed to register manual payment', err)
      throw err
    }
  },

  closeTableSession: async (tableId: number, force = false) => {
    try {
      const response = await waiterTableAPI.closeTable(tableId, { force })
      storeLogger.info('Table closed by waiter', {
        tableId,
        sessionId: response.session_id,
        totalCents: response.total_cents,
        paidCents: response.paid_cents,
      })

      // Clear active session
      set({ activeSession: null })

      return response
    } catch (err) {
      if (handleAuthError(err)) {
        throw new Error('Session expired')
      }
      storeLogger.error('Failed to close table', err)
      throw err
    }
  },

  fetchSessionSummary: async (sessionId: number) => {
    try {
      const sessionSummary = await waiterTableAPI.getSessionSummary(sessionId)
      set({ activeSession: sessionSummary })
      storeLogger.info('Session summary fetched', { sessionId })
      return sessionSummary
    } catch (err) {
      if (handleAuthError(err)) {
        throw new Error('Session expired')
      }
      storeLogger.error('Failed to fetch session summary', err)
      throw err
    }
  },

  clearActiveSession: () => {
    set({ activeSession: null })
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

  // MED-08 FIX: Use WS event constants instead of magic strings
  // Events that require updating the table data
  const eventsRequiringUpdate = [
    WS_EVENT_TYPES.ROUND_SUBMITTED,
    WS_EVENT_TYPES.ROUND_IN_KITCHEN,
    WS_EVENT_TYPES.ROUND_READY,
    WS_EVENT_TYPES.ROUND_SERVED,
    WS_EVENT_TYPES.SERVICE_CALL_CREATED,
    WS_EVENT_TYPES.SERVICE_CALL_ACKED,
    WS_EVENT_TYPES.CHECK_REQUESTED,
    WS_EVENT_TYPES.CHECK_PAID,
    WS_EVENT_TYPES.TABLE_CLEARED,
    WS_EVENT_TYPES.TABLE_STATUS_CHANGED,
    WS_EVENT_TYPES.TABLE_SESSION_STARTED,  // FIX: Handle new table sessions (diner scanned QR)
    WS_EVENT_TYPES.PAYMENT_APPROVED,
    WS_EVENT_TYPES.PAYMENT_REJECTED,
  ]

  if (!eventsRequiringUpdate.includes(event.type)) {
    return
  }

  // TABLE_CLEARED may remove the table from active list, handle specially
  if (event.type === WS_EVENT_TYPES.TABLE_CLEARED) {
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

// WAITER-STORE-CRIT-01 FIX: Stable empty arrays for React 19 getSnapshot compatibility
const EMPTY_TABLES: TableCard[] = []

// Selectors
export const selectTables = (state: TablesState) => state.tables.length > 0 ? state.tables : EMPTY_TABLES
export const selectSelectedTableId = (state: TablesState) => state.selectedTableId
export const selectSelectedTable = (state: TablesState) =>
  state.tables.find((t) => t.table_id === state.selectedTableId) ?? null
export const selectIsLoading = (state: TablesState) => state.isLoading
export const selectError = (state: TablesState) => state.error
export const selectWsConnected = (state: TablesState) => state.wsConnected
// HU-WAITER-MESA: Active session selector for waiter-managed flow
export const selectActiveSession = (state: TablesState) => state.activeSession

// WAITER-STORE-CRIT-01 FIX: Derived selectors with stable array references
// Uses memoization pattern to avoid creating new arrays on every call
const pendingRoundsCache = { tables: null as TableCard[] | null, result: EMPTY_TABLES }
const serviceCallsCache = { tables: null as TableCard[] | null, result: EMPTY_TABLES }
const checkRequestedCache = { tables: null as TableCard[] | null, result: EMPTY_TABLES }

export const selectTablesWithPendingRounds = (state: TablesState): TableCard[] => {
  if (state.tables === pendingRoundsCache.tables) {
    return pendingRoundsCache.result
  }
  const filtered = state.tables.filter((t) => t.open_rounds > 0)
  pendingRoundsCache.tables = state.tables
  pendingRoundsCache.result = filtered.length > 0 ? filtered : EMPTY_TABLES
  return pendingRoundsCache.result
}

export const selectTablesWithServiceCalls = (state: TablesState): TableCard[] => {
  if (state.tables === serviceCallsCache.tables) {
    return serviceCallsCache.result
  }
  const filtered = state.tables.filter((t) => t.pending_calls > 0)
  serviceCallsCache.tables = state.tables
  serviceCallsCache.result = filtered.length > 0 ? filtered : EMPTY_TABLES
  return serviceCallsCache.result
}

export const selectTablesWithCheckRequested = (state: TablesState): TableCard[] => {
  if (state.tables === checkRequestedCache.tables) {
    return checkRequestedCache.result
  }
  const filtered = state.tables.filter((t) => t.status === 'PAYING' || t.check_status === 'REQUESTED')
  checkRequestedCache.tables = state.tables
  checkRequestedCache.result = filtered.length > 0 ? filtered : EMPTY_TABLES
  return checkRequestedCache.result
}
