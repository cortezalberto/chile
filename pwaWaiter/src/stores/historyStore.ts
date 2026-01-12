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
let broadcastChannel: BroadcastChannel | null = null

function initBroadcastChannel(store: { setState: (state: Partial<HistoryState>) => void }) {
  if (typeof BroadcastChannel === 'undefined') return

  try {
    broadcastChannel = new BroadcastChannel(BROADCAST_CHANNEL_NAME)
    broadcastChannel.onmessage = (event) => {
      if (event.data?.type === 'HISTORY_UPDATE') {
        store.setState({ entries: event.data.entries })
        storeLogger.debug('History synced from another tab')
      }
    }
  } catch (error) {
    storeLogger.warn('BroadcastChannel not available', error)
  }
}

function broadcastHistoryUpdate(entries: HistoryEntry[]) {
  if (broadcastChannel) {
    try {
      broadcastChannel.postMessage({ type: 'HISTORY_UPDATE', entries })
    } catch (error) {
      storeLogger.debug('Failed to broadcast history update', error)
    }
  }
}

export const useHistoryStore = create<HistoryState>()(
  persist(
    (set, _get) => {
      // Initialize broadcast channel after store is created
      setTimeout(() => initBroadcastChannel({ setState: set }), 0)

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
