import { useEffect, useCallback, useMemo, useState } from 'react'
import { useAuthStore, selectSelectedBranchId } from '../stores/authStore'
import {
  useTablesStore,
  selectTables,
  selectIsLoading,
  selectError,
} from '../stores/tablesStore'
import { Header } from '../components/Header'
import { TableCard } from '../components/TableCard'
import { TableDetailModal } from '../components/TableDetailModal'
import { Button } from '../components/Button'
import { PullToRefreshIndicator } from '../components/PullToRefreshIndicator'
import { usePullToRefresh } from '../hooks/usePullToRefresh'
import { usePersistedFilter, type TableFilterStatus } from '../hooks/usePersistedFilter'
import { UI_CONFIG } from '../utils/constants'
import type { TableCard as TableCardType } from '../types'

interface TableGridPageProps {
  onTableSelect?: (tableId: number) => void
}

// PWAW-009: Filter button configuration
const FILTER_OPTIONS: { value: TableFilterStatus; label: string }[] = [
  { value: 'ALL', label: 'Todas' },
  { value: 'URGENT', label: 'Urgentes' },
  { value: 'ACTIVE', label: 'Activas' },
  { value: 'FREE', label: 'Libres' },
  { value: 'OUT_OF_SERVICE', label: 'Fuera servicio' },
]

export function TableGridPage(_props: TableGridPageProps) {
  const branchId = useAuthStore(selectSelectedBranchId)
  const tables = useTablesStore(selectTables)
  const isLoading = useTablesStore(selectIsLoading)
  const error = useTablesStore(selectError)
  const fetchTables = useTablesStore((s) => s.fetchTables)
  const subscribeToEvents = useTablesStore((s) => s.subscribeToEvents)

  // Modal state for table detail
  const [selectedTableForModal, setSelectedTableForModal] = useState<TableCardType | null>(null)

  // PWAW-009: Persisted filter state
  const { filter, setFilter } = usePersistedFilter()

  // PWAW-008: Pull-to-refresh handler
  const handleRefresh = useCallback(async () => {
    if (branchId) {
      await fetchTables(branchId)
    }
  }, [branchId, fetchTables])

  // WAITER-HOOK-MED-02: Added statusMessage for accessibility
  const { containerRef, pullDistance, isRefreshing, progress, statusMessage } = usePullToRefresh({
    onRefresh: handleRefresh,
    threshold: 80,
  })

  // Fetch tables on mount and when branch changes
  useEffect(() => {
    if (branchId) {
      fetchTables(branchId)
    }
  }, [branchId, fetchTables])

  // Subscribe to WebSocket events
  useEffect(() => {
    if (!branchId) return
    const unsubscribe = subscribeToEvents(branchId)
    return unsubscribe
  }, [branchId, subscribeToEvents])

  // PWAW-L003: Refresh tables periodically (backup for missed WS events)
  useEffect(() => {
    if (!branchId) return

    const interval = setInterval(() => {
      fetchTables(branchId)
    }, UI_CONFIG.TABLE_REFRESH_INTERVAL)

    return () => clearInterval(interval)
  }, [branchId, fetchTables])

  // PWAW-009: Filter tables by status
  const urgentTables = useMemo(
    () => tables.filter(
      (t) => t.status === 'PAYING' || t.pending_calls > 0 || t.check_status === 'REQUESTED'
    ),
    [tables]
  )
  const activeTables = useMemo(
    () => tables.filter(
      (t) => t.status === 'ACTIVE' && !urgentTables.includes(t)
    ),
    [tables, urgentTables]
  )
  const availableTables = useMemo(
    () => tables.filter((t) => t.status === 'FREE'),
    [tables]
  )
  const outOfServiceTables = useMemo(
    () => tables.filter((t) => t.status === 'OUT_OF_SERVICE'),
    [tables]
  )

  // PWAW-009: Apply filter to show only selected category
  const filteredTables = useMemo(() => {
    switch (filter) {
      case 'URGENT':
        return urgentTables
      case 'ACTIVE':
        return activeTables
      case 'FREE':
        return availableTables
      case 'OUT_OF_SERVICE':
        return outOfServiceTables
      case 'ALL':
      default:
        return tables
    }
  }, [filter, tables, urgentTables, activeTables, availableTables, outOfServiceTables])

  // Group filtered tables by sector (like Dashboard)
  const tablesBySector = useMemo(() => {
    // Priority order for sorting tables within each sector
    const statusOrder: Record<string, number> = {
      PAYING: 1,      // Most urgent
      ACTIVE: 2,
      FREE: 3,
      OUT_OF_SERVICE: 4,
    }

    // Group by sector
    const grouped: Record<string, TableCardType[]> = {}
    filteredTables.forEach((table) => {
      const sector = table.sector_name || 'Sin sector'
      if (!grouped[sector]) {
        grouped[sector] = []
      }
      grouped[sector].push(table)
    })

    // Sort tables within each sector by status (urgent first) and code
    Object.keys(grouped).forEach((sector) => {
      grouped[sector].sort((a, b) => {
        // Urgent tables first (pending calls or check requested)
        const aIsUrgent = a.pending_calls > 0 || a.check_status === 'REQUESTED'
        const bIsUrgent = b.pending_calls > 0 || b.check_status === 'REQUESTED'
        if (aIsUrgent && !bIsUrgent) return -1
        if (!aIsUrgent && bIsUrgent) return 1
        // Then by status
        const statusDiff = (statusOrder[a.status] || 99) - (statusOrder[b.status] || 99)
        if (statusDiff !== 0) return statusDiff
        // Finally by code
        return a.code.localeCompare(b.code)
      })
    })

    // Convert to array of [sector, tables] sorted by sector name
    return Object.entries(grouped).sort(([a], [b]) => a.localeCompare(b))
  }, [filteredTables])

  // Count for filter badges
  const filterCounts: Record<TableFilterStatus, number> = {
    ALL: tables.length,
    URGENT: urgentTables.length,
    ACTIVE: activeTables.length,
    FREE: availableTables.length,
    OUT_OF_SERVICE: outOfServiceTables.length,
  }

  return (
    <div className="min-h-screen bg-white flex flex-col">
      <Header />

      {/* PWAW-008: Pull-to-refresh indicator */}
      <PullToRefreshIndicator
        pullDistance={pullDistance}
        isRefreshing={isRefreshing}
        progress={progress}
      />

      {/* PWAW-M006: Visual loading indicator during refresh */}
      {(isRefreshing || isLoading) && (
        <div className="absolute top-16 left-0 right-0 h-1 bg-orange-500/30">
          <div className="h-full bg-orange-500 animate-pulse" style={{ width: '100%' }} />
        </div>
      )}

      {/* PWAW-009: Filter bar */}
      <div className="px-4 py-2 bg-gray-50 border-b border-gray-200">
        <div className="flex gap-2 overflow-x-auto pb-1 scrollbar-hide">
          {FILTER_OPTIONS.map((option) => {
            const count = filterCounts[option.value]
            const isActive = filter === option.value
            return (
              <button
                key={option.value}
                onClick={() => setFilter(option.value)}
                className={`flex-shrink-0 px-3 py-1.5 rounded-full text-sm font-medium transition-colors ${
                  isActive
                    ? 'bg-orange-500 text-white'
                    : 'bg-gray-200 text-gray-600 hover:bg-gray-300'
                }`}
              >
                {option.label}
                {count > 0 && (
                  <span
                    className={`ml-1.5 px-1.5 py-0.5 rounded-full text-xs ${
                      isActive ? 'bg-orange-600' : 'bg-gray-300'
                    }`}
                  >
                    {count}
                  </span>
                )}
              </button>
            )
          })}
        </div>
      </div>

      <main ref={containerRef} className="flex-1 p-4 overflow-auto">
        {isLoading && tables.length === 0 ? (
          <div className="flex items-center justify-center h-64">
            <div className="text-center">
              <div className="animate-spin w-8 h-8 border-2 border-orange-500 border-t-transparent rounded-full mx-auto mb-4" />
              <p className="text-gray-500">Cargando mesas...</p>
            </div>
          </div>
        ) : error ? (
          <div className="flex flex-col items-center justify-center h-64">
            <p className="text-red-500 mb-4">{error}</p>
            <Button onClick={() => branchId && fetchTables(branchId)}>
              Reintentar
            </Button>
          </div>
        ) : (
          <div className="space-y-6">
            {/* Tables grouped by sector */}
            {tablesBySector.length > 0 ? (
              tablesBySector.map(([sectorName, sectorTables]) => {
                // Check if this sector has urgent tables
                const urgentCount = sectorTables.filter(
                  (t) => t.pending_calls > 0 || t.check_status === 'REQUESTED' || t.status === 'PAYING'
                ).length

                return (
                  <section key={sectorName}>
                    {/* Sector header */}
                    <div className="flex items-center gap-2 mb-3">
                      <h2 className="text-lg font-semibold text-gray-700">
                        {sectorName}
                      </h2>
                      <span className="px-2 py-0.5 bg-gray-200 text-gray-600 text-sm rounded-full">
                        {sectorTables.length}
                      </span>
                      {urgentCount > 0 && (
                        <span className="flex items-center gap-1 px-2 py-0.5 bg-red-100 text-red-600 text-sm rounded-full">
                          <span className="w-2 h-2 rounded-full bg-red-500 animate-pulse" />
                          {urgentCount} urgente{urgentCount > 1 ? 's' : ''}
                        </span>
                      )}
                    </div>
                    {/* Tables grid */}
                    <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-4 xl:grid-cols-5 gap-3">
                      {sectorTables.map((table) => (
                        <TableCard
                          key={table.table_id}
                          table={table}
                          onClick={() => setSelectedTableForModal(table)}
                        />
                      ))}
                    </div>
                  </section>
                )
              })
            ) : tables.length > 0 && filteredTables.length === 0 ? (
              /* Empty state when filter returns no results */
              <div className="flex flex-col items-center justify-center h-64">
                <p className="text-gray-500 mb-2">
                  No hay mesas {filter === 'URGENT' ? 'urgentes' :
                               filter === 'ACTIVE' ? 'activas' :
                               filter === 'FREE' ? 'libres' :
                               filter === 'OUT_OF_SERVICE' ? 'fuera de servicio' : 'con este filtro'}
                </p>
                <Button
                  variant="secondary"
                  onClick={() => setFilter('ALL')}
                >
                  Mostrar todas
                </Button>
              </div>
            ) : (
              /* Empty state when no tables configured */
              <div className="flex flex-col items-center justify-center h-64">
                <p className="text-gray-500 mb-2">No hay mesas configuradas</p>
                <p className="text-gray-400 text-sm">
                  Agrega mesas desde el Dashboard
                </p>
              </div>
            )}
          </div>
        )}
      </main>

      {/* Refresh button */}
      <div className="fixed bottom-4 right-4">
        <Button
          variant="secondary"
          size="sm"
          onClick={() => branchId && fetchTables(branchId)}
          disabled={isLoading || isRefreshing}
          className="shadow-lg"
        >
          {isLoading || isRefreshing ? 'Actualizando...' : 'Actualizar'}
        </Button>
      </div>

      {/* Table detail modal */}
      <TableDetailModal
        table={selectedTableForModal}
        isOpen={selectedTableForModal !== null}
        onClose={() => setSelectedTableForModal(null)}
      />
    </div>
  )
}
