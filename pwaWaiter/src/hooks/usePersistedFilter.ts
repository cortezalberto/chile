import { useState, useCallback, useEffect } from 'react'

const STORAGE_KEY = 'pwawaiter_table_filter'

export type TableFilterStatus = 'ALL' | 'URGENT' | 'ACTIVE' | 'FREE' | 'OUT_OF_SERVICE'

interface PersistedFilterState {
  status: TableFilterStatus
}

const DEFAULT_STATE: PersistedFilterState = {
  status: 'ALL',
}

/**
 * PWAW-009: Hook to persist table filter preferences
 * PWAW-M007: Changed to localStorage for persistence across sessions
 */
export function usePersistedFilter() {
  const [filter, setFilterState] = useState<PersistedFilterState>(() => {
    try {
      const stored = localStorage.getItem(STORAGE_KEY)
      if (stored) {
        return JSON.parse(stored) as PersistedFilterState
      }
    } catch {
      // Ignore parse errors
    }
    return DEFAULT_STATE
  })

  // PWAW-M007: Persist to localStorage when filter changes
  useEffect(() => {
    try {
      localStorage.setItem(STORAGE_KEY, JSON.stringify(filter))
    } catch {
      // Ignore storage errors
    }
  }, [filter])

  const setFilter = useCallback((status: TableFilterStatus) => {
    setFilterState({ status })
  }, [])

  const clearFilter = useCallback(() => {
    setFilterState(DEFAULT_STATE)
  }, [])

  return {
    filter: filter.status,
    setFilter,
    clearFilter,
  }
}
