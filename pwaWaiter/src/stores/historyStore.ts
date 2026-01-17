import { create } from 'zustand'
import { persist, createJSONStorage } from 'zustand/middleware'
import { storeLogger } from '../utils/logger'
import { UI_CONFIG } from '../utils/constants'

// Action types that can be tracked
export type HistoryActionType =
  | 'ROUND_MARKED_IN_KITCHEN'
  | 'ROUND_MARKED_READY'
  | 'ROUND_MARKED_SERVED'
  | 'SERVICE_CALL_ACCEPTED'
  | 'SERVICE_CALL_COMPLETED'

export interface HistoryEntry {
  id: string
  action: HistoryActionType
  table_id: number
  table_code: string
  timestamp: string
  details?: string
}

export type HistoryEntryInput = Omit<HistoryEntry, 'id' | 'timestamp'>

interface HistoryState {
  entries: HistoryEntry[]
  // Actions
  addHistoryEntry: (entry: HistoryEntryInput) => void
  clearHistory: () => void
}

// PWAW-L003: Using UI_CONFIG constant
const MAX_ENTRIES = UI_CONFIG.MAX_HISTORY_ENTRIES
const STORAGE_KEY = 'waiter-history'
const BROADCAST_CHANNEL_NAME = 'waiter-history-sync' // PWAW-A004

// PWAW-A004: BroadcastChannel for cross-tab sync
// CRIT-10 FIX: Track channel for proper cleanup
let broadcastChannel: BroadcastChannel | null = null
let isChannelInitialized = false
// WAITER-STORE-HIGH-01: Track mount state for async operations
let isMounted = true

function initBroadcastChannel(store: { setState: (state: Partial<HistoryState>) => void }) {
  // CRIT-10 FIX: Prevent multiple initializations
  if (isChannelInitialized || typeof BroadcastChannel === 'undefined') return

  // WAITER-STORE-HIGH-02: Wrap BroadcastChannel operations in try-catch
  try {
    broadcastChannel = new BroadcastChannel(BROADCAST_CHANNEL_NAME)
    broadcastChannel.onmessage = (event) => {
      // WAITER-STORE-HIGH-01: Add mount guard before setState
      if (!isMounted) {
        storeLogger.debug('Ignoring broadcast message - store unmounted')
        return
      }
      try {
        if (event.data?.type === 'HISTORY_UPDATE') {
          store.setState({ entries: event.data.entries })
          storeLogger.debug('History synced from another tab')
        }
      } catch (error) {
        // WAITER-STORE-HIGH-02: Handle message processing errors
        storeLogger.warn('Error processing broadcast message', error)
      }
    }
    // WAITER-STORE-HIGH-02: Handle BroadcastChannel errors
    broadcastChannel.onmessageerror = (event) => {
      storeLogger.warn('BroadcastChannel message error', event)
    }
    isChannelInitialized = true
  } catch (error) {
    storeLogger.warn('BroadcastChannel not available', error)
  }
}

/**
 * CRIT-10 FIX: Close BroadcastChannel to prevent memory leaks.
 * Should be called on app shutdown/logout.
 * LOW-29-15 FIX: Only reset flags if close() succeeds
 */
export function closeBroadcastChannel(): void {
  // WAITER-STORE-HIGH-01: Mark as unmounted to prevent async setState calls
  isMounted = false
  if (broadcastChannel) {
    try {
      broadcastChannel.close()
      // LOW-29-15 FIX: Only reset flags after successful close
      broadcastChannel = null
      isChannelInitialized = false
      storeLogger.debug('BroadcastChannel closed successfully')
    } catch (error) {
      // LOW-29-15 FIX: Keep references if close fails, channel may still be usable
      storeLogger.warn('Failed to close BroadcastChannel, keeping reference', error)
    }
  }
}

/**
 * WAITER-STORE-HIGH-01: Re-enable mount state (call when re-initializing)
 */
export function enableHistoryStore(): void {
  isMounted = true
}

function broadcastHistoryUpdate(entries: HistoryEntry[]) {
  // WAITER-STORE-HIGH-02: Wrap BroadcastChannel operations in try-catch
  if (broadcastChannel) {
    try {
      broadcastChannel.postMessage({ type: 'HISTORY_UPDATE', entries })
    } catch (error) {
      // Handle InvalidStateError if channel was closed unexpectedly
      if (error instanceof DOMException && error.name === 'InvalidStateError') {
        storeLogger.warn('BroadcastChannel closed unexpectedly, resetting state')
        broadcastChannel = null
        isChannelInitialized = false
      } else {
        storeLogger.debug('Failed to broadcast history update', error)
      }
    }
  }
}

// CRIT-29-04 FIX: Queue for messages that arrive before BroadcastChannel is ready
let pendingBroadcasts: HistoryEntry[][] = []

export const useHistoryStore = create<HistoryState>()(
  persist(
    (set, _get) => {
      // CRIT-29-04 FIX: Initialize broadcast channel synchronously to avoid race condition
      // If BroadcastChannel is available, initialize immediately instead of using setTimeout
      if (typeof BroadcastChannel !== 'undefined' && !isChannelInitialized) {
        initBroadcastChannel({ setState: set })
        // Flush any pending broadcasts
        if (pendingBroadcasts.length > 0) {
          pendingBroadcasts.forEach(entries => broadcastHistoryUpdate(entries))
          pendingBroadcasts = []
        }
      }

      return {
        entries: [],

        addHistoryEntry: (entry: HistoryEntryInput) => {
          const newEntry: HistoryEntry = {
            ...entry,
            id: crypto.randomUUID(),
            timestamp: new Date().toISOString(),
          }

          set((state) => {
            // FIFO: Add new entry at the beginning, keep only last MAX_ENTRIES
            const updatedEntries = [newEntry, ...state.entries].slice(0, MAX_ENTRIES)
            // PWAW-A004: Broadcast to other tabs
            broadcastHistoryUpdate(updatedEntries)
            return { entries: updatedEntries }
          })

          storeLogger.info('History entry added', {
            action: newEntry.action,
            tableCode: newEntry.table_code,
          })
        },

        clearHistory: () => {
          set({ entries: [] })
          // PWAW-A004: Broadcast clear to other tabs
          broadcastHistoryUpdate([])
          storeLogger.info('History cleared')
        },
      }
    },
    {
      name: STORAGE_KEY,
      version: 1,
      // PWAW-A004: Use localStorage instead of sessionStorage for persistence across tabs
      storage: createJSONStorage(() => localStorage),
      partialize: (state) => ({
        entries: state.entries,
      }),
    }
  )
)

// Selectors
export const selectHistory = (state: HistoryState) => state.entries

// Selector factory for recent actions with limit
export const selectRecentActions = (limit: number) => (state: HistoryState) =>
  state.entries.slice(0, limit)

// Pre-defined selector for common use case
export const selectLast10Actions = (state: HistoryState) => state.entries.slice(0, 10)
export const selectLast5Actions = (state: HistoryState) => state.entries.slice(0, 5)
