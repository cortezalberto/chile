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
import { WS_EVENT_TYPES, ANIMATION_DURATIONS } from '../utils/constants'
import { useRetryQueueStore } from './retryQueueStore'
import { useAuthStore } from './authStore'
import type { TableCard, WSEvent, OrderStatus } from '../types'

// =============================================================================
// Animation Timeout Tracking (prevents memory leaks with Maps)
// =============================================================================
const statusBlinkTimeouts = new Map<number, ReturnType<typeof setTimeout>>()
const newOrderTimeouts = new Map<number, ReturnType<typeof setTimeout>>()
const serviceCallTimeouts = new Map<number, ReturnType<typeof setTimeout>>()

// QA-FIX: Track seen service call IDs to avoid incrementing counter for reminder events
// When a diner calls multiple times for the same open call, we only increment once
const seenServiceCallIds = new Set<number>()
const MAX_SEEN_SERVICE_CALLS = 100 // Prevent unbounded growth

// Clear all timeouts on store reset (e.g., logout)
function clearAllAnimationTimeouts(): void {
  statusBlinkTimeouts.forEach((timeout) => clearTimeout(timeout))
  statusBlinkTimeouts.clear()
  newOrderTimeouts.forEach((timeout) => clearTimeout(timeout))
  newOrderTimeouts.clear()
  serviceCallTimeouts.forEach((timeout) => clearTimeout(timeout))
  serviceCallTimeouts.clear()
}

// =============================================================================
// Order Status Calculation (matches Dashboard pattern)
// =============================================================================

/**
 * Calculate aggregate order status from per-round statuses.
 * Priority logic:
 * 1. If ANY round is 'ready' AND ANY is NOT ready → 'ready_with_kitchen'
 * 2. If ALL rounds are 'pending' → 'pending'
 * 3. Otherwise show worst status from remaining rounds
 */
function calculateAggregateOrderStatus(
  roundStatuses: Record<string, OrderStatus>
): OrderStatus {
  const statuses = Object.values(roundStatuses)
  if (statuses.length === 0) return 'none'

  const hasReady = statuses.some((s) => s === 'ready')
  const hasNotReady = statuses.some(
    (s) => s === 'pending' || s === 'submitted' || s === 'in_kitchen'
  )

  // Rule 1: Ready + not ready = combined status
  if (hasReady && hasNotReady) {
    return 'ready_with_kitchen'
  }

  // Rule 2: All pending
  const allPending = statuses.every((s) => s === 'pending')
  if (allPending) return 'pending'

  // Rule 3: Return worst status (priority order)
  const priorityOrder: OrderStatus[] = [
    'pending',
    'submitted',
    'in_kitchen',
    'ready',
    'served',
    'none',
  ]

  for (const status of priorityOrder) {
    if (statuses.includes(status)) return status
  }

  return 'none'
}

/**
 * Map backend RoundStatus to frontend OrderStatus
 */
function mapRoundStatusToOrderStatus(roundStatus: string): OrderStatus {
  switch (roundStatus) {
    case 'PENDING':
      return 'pending'
    case 'SUBMITTED':
      return 'submitted'
    case 'IN_KITCHEN':
      return 'in_kitchen'
    case 'READY':
      return 'ready'
    case 'SERVED':
      return 'served'
    default:
      return 'none'
  }
}

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
      const apiTables = await tablesAPI.getTables(branchId)
      // QA-FIX: Initialize orderStatus when loading tables from API
      // If a table has open_rounds > 0 but no orderStatus, default to 'pending'
      // This ensures the UI shows the correct state before WebSocket events arrive
      const tables = apiTables.map((table) => ({
        ...table,
        // Initialize orderStatus if there are open rounds and it's not already set
        orderStatus: table.orderStatus ?? (table.open_rounds > 0 ? 'pending' : 'none'),
        // Initialize roundStatuses as empty if not set
        roundStatuses: table.roundStatuses ?? {},
      })) as TableCard[]
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
  const tableId = event.table_id
  const tableIndex = tables.findIndex((t) => t.table_id === tableId)

  storeLogger.debug('Processing WS event', { type: event.type, tableId })

  // MED-08 FIX: Use WS event constants instead of magic strings
  // Events that require updating the table data
  const eventsRequiringUpdate = [
    WS_EVENT_TYPES.ROUND_PENDING,
    WS_EVENT_TYPES.ROUND_SUBMITTED,
    WS_EVENT_TYPES.ROUND_IN_KITCHEN,
    WS_EVENT_TYPES.ROUND_READY,
    WS_EVENT_TYPES.ROUND_SERVED,
    WS_EVENT_TYPES.SERVICE_CALL_CREATED,
    WS_EVENT_TYPES.SERVICE_CALL_ACKED,
    WS_EVENT_TYPES.SERVICE_CALL_CLOSED,
    WS_EVENT_TYPES.CHECK_REQUESTED,
    WS_EVENT_TYPES.CHECK_PAID,
    WS_EVENT_TYPES.TABLE_CLEARED,
    WS_EVENT_TYPES.TABLE_STATUS_CHANGED,
    WS_EVENT_TYPES.TABLE_SESSION_STARTED,
    WS_EVENT_TYPES.PAYMENT_APPROVED,
    WS_EVENT_TYPES.PAYMENT_REJECTED,
  ]

  if (!eventsRequiringUpdate.includes(event.type)) {
    return
  }

  // ==========================================================================
  // Handle ROUND_* events - update orderStatus and roundStatuses locally
  // ==========================================================================
  const roundEvents = [
    WS_EVENT_TYPES.ROUND_PENDING,
    WS_EVENT_TYPES.ROUND_SUBMITTED,
    WS_EVENT_TYPES.ROUND_IN_KITCHEN,
    WS_EVENT_TYPES.ROUND_READY,
    WS_EVENT_TYPES.ROUND_SERVED,
  ]

  if (roundEvents.includes(event.type) && tableIndex !== -1 && tableId !== undefined) {
    const roundId = event.entity?.round_id ?? event.round_id
    if (roundId !== undefined) {
      const roundKey = String(roundId)
      const newStatus = mapRoundStatusToOrderStatus(
        event.type.replace('ROUND_', '')
      )

      const currentTable = tables[tableIndex]
      const updatedRoundStatuses = {
        ...(currentTable.roundStatuses ?? {}),
        [roundKey]: newStatus,
      }

      // Clean up served rounds to prevent unbounded growth
      if (newStatus === 'served') {
        delete updatedRoundStatuses[roundKey]
      }

      const aggregateStatus = calculateAggregateOrderStatus(updatedRoundStatuses)

      // Determine if this is a new order (trigger yellow pulse)
      const isNewOrder = event.type === WS_EVENT_TYPES.ROUND_PENDING

      // Trigger status blink animation
      const existingBlinkTimeout = statusBlinkTimeouts.get(tableId)
      if (existingBlinkTimeout) clearTimeout(existingBlinkTimeout)

      // Calculate open_rounds delta based on event type
      // ROUND_PENDING: +1 (new round created)
      // ROUND_SERVED: -1 (round completed)
      let openRoundsDelta = 0
      if (event.type === WS_EVENT_TYPES.ROUND_PENDING) {
        openRoundsDelta = 1
      } else if (event.type === WS_EVENT_TYPES.ROUND_SERVED) {
        openRoundsDelta = -1
      }

      const updatedTables = [...tables]
      updatedTables[tableIndex] = {
        ...currentTable,
        roundStatuses: updatedRoundStatuses,
        orderStatus: aggregateStatus,
        statusChanged: true,
        hasNewOrder: isNewOrder ? true : currentTable.hasNewOrder,
        open_rounds: Math.max(0, (currentTable.open_rounds ?? 0) + openRoundsDelta),
      }
      set({ tables: updatedTables })

      // Auto-clear statusChanged after animation duration
      const blinkTimeout = setTimeout(() => {
        statusBlinkTimeouts.delete(tableId)
        const currentTables = get().tables
        const idx = currentTables.findIndex((t) => t.table_id === tableId)
        if (idx !== -1) {
          const newTables = [...currentTables]
          newTables[idx] = { ...newTables[idx], statusChanged: false }
          set({ tables: newTables })
        }
      }, ANIMATION_DURATIONS.STATUS_BLINK)
      statusBlinkTimeouts.set(tableId, blinkTimeout)

      // Auto-clear hasNewOrder after animation duration
      if (isNewOrder) {
        const existingNewOrderTimeout = newOrderTimeouts.get(tableId)
        if (existingNewOrderTimeout) clearTimeout(existingNewOrderTimeout)

        const newOrderTimeout = setTimeout(() => {
          newOrderTimeouts.delete(tableId)
          const currentTables = get().tables
          const idx = currentTables.findIndex((t) => t.table_id === tableId)
          if (idx !== -1) {
            const newTables = [...currentTables]
            newTables[idx] = { ...newTables[idx], hasNewOrder: false }
            set({ tables: newTables })
          }
        }, ANIMATION_DURATIONS.NEW_ORDER_PULSE)
        newOrderTimeouts.set(tableId, newOrderTimeout)
      }

      storeLogger.debug('Round status updated locally', {
        tableId,
        roundId,
        newStatus,
        aggregateStatus,
      })
    }
  }

  // ==========================================================================
  // Handle SERVICE_CALL_CREATED - trigger red blink animation with sound
  // ==========================================================================
  if (event.type === WS_EVENT_TYPES.SERVICE_CALL_CREATED && tableIndex !== -1 && tableId !== undefined) {
    const callId = event.entity?.call_id
    const existingTimeout = serviceCallTimeouts.get(tableId)
    if (existingTimeout) clearTimeout(existingTimeout)

    // QA-FIX: Only increment pending_calls for NEW call_ids (not reminders)
    // This prevents the counter from incrementing when diner calls multiple times
    // for the same open service call
    const isNewCall = callId !== undefined && !seenServiceCallIds.has(callId)

    if (isNewCall) {
      // Prevent unbounded growth of seen IDs
      if (seenServiceCallIds.size >= MAX_SEEN_SERVICE_CALLS) {
        seenServiceCallIds.clear()
      }
      seenServiceCallIds.add(callId)
    }

    // QA-FIX: Track active service call IDs for UI resolution
    const currentActiveIds = tables[tableIndex].activeServiceCallIds ?? []
    const updatedActiveIds = callId !== undefined && isNewCall
      ? [...currentActiveIds, callId]
      : currentActiveIds

    const updatedTables = [...tables]
    updatedTables[tableIndex] = {
      ...tables[tableIndex],
      hasServiceCall: true,
      // Only increment for new calls, not reminders
      pending_calls: isNewCall
        ? (tables[tableIndex].pending_calls ?? 0) + 1
        : tables[tableIndex].pending_calls ?? 1,
      activeServiceCallIds: updatedActiveIds,
    }
    set({ tables: updatedTables })

    // Auto-clear hasServiceCall after animation duration
    const timeout = setTimeout(() => {
      serviceCallTimeouts.delete(tableId)
      const currentTables = get().tables
      const idx = currentTables.findIndex((t) => t.table_id === tableId)
      if (idx !== -1) {
        const newTables = [...currentTables]
        newTables[idx] = { ...newTables[idx], hasServiceCall: false }
        set({ tables: newTables })
      }
    }, ANIMATION_DURATIONS.SERVICE_CALL_BLINK)
    serviceCallTimeouts.set(tableId, timeout)

    storeLogger.debug('Service call animation triggered', { tableId, callId, isNewCall, activeIds: updatedActiveIds })
    return // Don't need to fetch table, we updated locally
  }

  // ==========================================================================
  // Handle SERVICE_CALL_ACKED/CLOSED - clear service call state
  // ==========================================================================
  if (
    (event.type === WS_EVENT_TYPES.SERVICE_CALL_ACKED ||
      event.type === WS_EVENT_TYPES.SERVICE_CALL_CLOSED) &&
    tableIndex !== -1 && tableId !== undefined
  ) {
    const callId = event.entity?.call_id
    const existingTimeout = serviceCallTimeouts.get(tableId)
    if (existingTimeout) {
      clearTimeout(existingTimeout)
      serviceCallTimeouts.delete(tableId)
    }

    // QA-FIX: Remove call_id from seen set so a new call can be created
    if (callId !== undefined) {
      seenServiceCallIds.delete(callId)
    }

    // QA-FIX: Remove call_id from activeServiceCallIds
    const currentActiveIds = tables[tableIndex].activeServiceCallIds ?? []
    const updatedActiveIds = callId !== undefined
      ? currentActiveIds.filter((id) => id !== callId)
      : currentActiveIds

    const updatedTables = [...tables]
    const currentCalls = tables[tableIndex].pending_calls ?? 0
    updatedTables[tableIndex] = {
      ...tables[tableIndex],
      hasServiceCall: false,
      pending_calls: Math.max(0, currentCalls - 1),
      activeServiceCallIds: updatedActiveIds,
    }
    set({ tables: updatedTables })
    storeLogger.debug('Service call cleared', { tableId, callId, remainingIds: updatedActiveIds })
    return
  }

  // ==========================================================================
  // Handle TABLE_CLEARED - reset all table state
  // ==========================================================================
  if (event.type === WS_EVENT_TYPES.TABLE_CLEARED && tableId !== undefined) {
    // Clear any pending animation timeouts for this table
    const blinkTimeout = statusBlinkTimeouts.get(tableId)
    if (blinkTimeout) {
      clearTimeout(blinkTimeout)
      statusBlinkTimeouts.delete(tableId)
    }
    const newOrderTimeout = newOrderTimeouts.get(tableId)
    if (newOrderTimeout) {
      clearTimeout(newOrderTimeout)
      newOrderTimeouts.delete(tableId)
    }
    const serviceTimeout = serviceCallTimeouts.get(tableId)
    if (serviceTimeout) {
      clearTimeout(serviceTimeout)
      serviceCallTimeouts.delete(tableId)
    }

    if (tableIndex !== -1) {
      const updatedTables = [...tables]
      updatedTables[tableIndex] = {
        ...updatedTables[tableIndex],
        status: 'FREE',
        session_id: null,
        open_rounds: 0,
        pending_calls: 0,
        check_status: null,
        orderStatus: 'none',
        roundStatuses: {},
        statusChanged: false,
        hasNewOrder: false,
        hasServiceCall: false,
        activeServiceCallIds: [], // Clear active service call IDs
      }
      set({ tables: updatedTables })
      storeLogger.debug('Table cleared locally', { tableId })
    }
    return
  }

  // ==========================================================================
  // For other events, fetch the affected table from API
  // ==========================================================================
  if (tableIndex === -1) {
    // Table not in our list yet, might be newly activated - do a full refresh
    tablesAPI.getTables(branchId).then((updatedTables) => {
      set({ tables: updatedTables })
      storeLogger.debug('Tables refreshed for new table', { tableId })
    }).catch((err) => {
      storeLogger.error('Failed to refresh tables', err)
    })
    return
  }

  // Fetch only the affected table and update it in place
  // Preserve local animation state when updating from API
  if (tableId === undefined) return

  tablesAPI.getTable(tableId).then((updatedTable) => {
    const currentTables = get().tables
    const currentIndex = currentTables.findIndex((t) => t.table_id === tableId)

    if (currentIndex !== -1) {
      const currentTable = currentTables[currentIndex]
      const newTables = [...currentTables]
      // Preserve animation state from local updates
      newTables[currentIndex] = {
        ...updatedTable,
        orderStatus: currentTable.orderStatus,
        roundStatuses: currentTable.roundStatuses,
        statusChanged: currentTable.statusChanged,
        hasNewOrder: currentTable.hasNewOrder,
        hasServiceCall: currentTable.hasServiceCall,
      }
      set({ tables: newTables })
      storeLogger.debug('Table updated incrementally', {
        type: event.type,
        tableId,
        status: updatedTable.status
      })
    }
  }).catch((err) => {
    storeLogger.error('Failed to fetch updated table', { tableId, error: err })
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
