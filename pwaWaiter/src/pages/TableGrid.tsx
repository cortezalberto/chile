import { useEffect, useCallback, useMemo } from 'react'
import { useAuthStore, selectSelectedBranchId } from '../stores/authStore'
import {
  useTablesStore,
  selectTables,
  selectIsLoading,
  selectError,
} from '../stores/tablesStore'
import { Header } from '../components/Header'
import { TableCard } from '../components/TableCard'
import { Button } from '../components/Button'
import { PullToRefreshIndicator } from '../components/PullToRefreshIndicator'
import { usePullToRefresh } from '../hooks/usePullToRefresh'
import { usePersistedFilter, type TableFilterStatus } from '../hooks/usePersistedFilter'
import { UI_CONFIG } from '../utils/constants'

interface TableGridPageProps {
  onTableSelect: (tableId: number) => void
}

// PWAW-009: Filter button configuration
const FILTER_OPTIONS: { value: TableFilterStatus; label: string }[] = [
  { value: 'ALL', label: 'Todas' },
  { value: 'URGENT', label: 'Urgentes' },
  { value: 'ACTIVE', label: 'Activas' },
  { value: 'FREE', label: 'Libres' },
  { value: 'OUT_OF_SERVICE', label: 'Fuera servicio' },
]

export function TableGridPage({ onTableSelect }: TableGridPageProps) {
  const branchId = useAuthStore(selectSelectedBranchId)
  const tables = useTablesStore(selectTables)
  const isLoading = useTablesStore(selectIsLoading)
  const error = useTablesStore(selectError)
  const fetchTables = useTablesStore((s) => s.fetchTables)
  const subscribeToEvents = useTablesStore((s) => s.subscribeToEvents)

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

  // Group tables by status using TableCard fields
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
  const showUrgent = filter === 'ALL' || filter === 'URGENT'
  const showActive = filter === 'ALL' || filter === 'ACTIVE'
  const showFree = filter === 'ALL' || filter === 'FREE'
  const showOutOfService = filter === 'ALL' || filter === 'OUT_OF_SERVICE'

  // Count for filter badges
  const filterCounts: Record<TableFilterStatus, number> = {
    ALL: tables.length,
    URGENT: urgentTables.length,
    ACTIVE: activeTables.length,
    FREE: availableTables.length,
    OUT_OF_SERVICE: outOfServiceTables.length,
  }

  return (
    <div className="min-h-screen bg-[#0a0a0a] flex flex-col">
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
      <div className="px-4 py-2 bg-neutral-900 border-b border-neutral-800">
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
                    : 'bg-neutral-800 text-neutral-400 hover:bg-neutral-700'
                }`}
              >
                {option.label}
                {count > 0 && (
                  <span
                    className={`ml-1.5 px-1.5 py-0.5 rounded-full text-xs ${
                      isActive ? 'bg-orange-600' : 'bg-neutral-700'
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
              <p className="text-neutral-400">Cargando mesas...</p>
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
            {/* Urgent tables */}
            {showUrgent && urgentTables.length > 0 && (
              <section>
                <h2 className="text-lg font-semibold text-red-500 mb-3 flex items-center gap-2">
                  <span className="w-2 h-2 rounded-full bg-red-500 animate-pulse" />
                  Requieren atencion ({urgentTables.length})
                </h2>
                <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-4 xl:grid-cols-5 gap-3">
                  {urgentTables.map((table) => (
                    <TableCard
                      key={table.table_id}
                      table={table}
                      onClick={() => onTableSelect(table.table_id)}
                    />
                  ))}
                </div>
              </section>
            )}

            {/* Active tables */}
            {showActive && activeTables.length > 0 && (
              <section>
                <h2 className="text-lg font-semibold text-neutral-300 mb-3">
                  Mesas activas ({activeTables.length})
                </h2>
                <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-4 xl:grid-cols-5 gap-3">
                  {activeTables.map((table) => (
                    <TableCard
                      key={table.table_id}
                      table={table}
                      onClick={() => onTableSelect(table.table_id)}
                    />
                  ))}
                </div>
              </section>
            )}

            {/* Available tables */}
            {showFree && availableTables.length > 0 && (
              <section>
                <h2 className="text-lg font-semibold text-neutral-300 mb-3">
                  Mesas libres ({availableTables.length})
                </h2>
                <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-4 xl:grid-cols-5 gap-3">
                  {availableTables.map((table) => (
                    <TableCard
                      key={table.table_id}
                      table={table}
                      onClick={() => onTableSelect(table.table_id)}
                    />
                  ))}
                </div>
              </section>
            )}

            {/* Out of service tables */}
            {showOutOfService && outOfServiceTables.length > 0 && (
              <section>
                <h2 className="text-lg font-semibold text-neutral-500 mb-3">
                  Fuera de servicio ({outOfServiceTables.length})
                </h2>
                <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-4 xl:grid-cols-5 gap-3">
                  {outOfServiceTables.map((table) => (
                    <TableCard
                      key={table.table_id}
                      table={table}
                      onClick={() => onTableSelect(table.table_id)}
                    />
                  ))}
                </div>
              </section>
            )}

            {/* WAITER-PAGE-MED-03: Empty state when filter returns no results */}
            {tables.length > 0 &&
             !showUrgent && !showActive && !showFree && !showOutOfService && (
              <div className="flex flex-col items-center justify-center h-64">
                <p className="text-neutral-400 mb-2">No hay mesas con este filtro</p>
                <Button
                  variant="secondary"
                  onClick={() => setFilter('ALL')}
                >
                  Mostrar todas
                </Button>
              </div>
            )}

            {/* WAITER-PAGE-MED-03: Empty state when filter shows sections but all are empty */}
            {tables.length > 0 &&
             ((showUrgent && urgentTables.length === 0) ||
              (showActive && activeTables.length === 0) ||
              (showFree && availableTables.length === 0) ||
              (showOutOfService && outOfServiceTables.length === 0)) &&
             filter !== 'ALL' &&
             filterCounts[filter] === 0 && (
              <div className="flex flex-col items-center justify-center h-64">
                <p className="text-neutral-400 mb-2">
                  No hay mesas {filter === 'URGENT' ? 'urgentes' :
                               filter === 'ACTIVE' ? 'activas' :
                               filter === 'FREE' ? 'libres' :
                               filter === 'OUT_OF_SERVICE' ? 'fuera de servicio' : ''}
                </p>
                <Button
                  variant="secondary"
                  onClick={() => setFilter('ALL')}
                >
                  Mostrar todas
                </Button>
              </div>
            )}

            {/* Empty state when no tables configured */}
            {tables.length === 0 && (
              <div className="flex flex-col items-center justify-center h-64">
                <p className="text-neutral-400 mb-2">No hay mesas configuradas</p>
                <p className="text-neutral-500 text-sm">
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
    </div>
  )
}
