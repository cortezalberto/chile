import { useState, useEffect, useCallback, useMemo } from 'react'
import { useAuthStore, selectSelectedBranchId, selectUser, selectSelectedBranchName } from '../stores/authStore'
import {
  useTablesStore,
  selectTables,
  selectIsLoading,
  selectError,
  selectWsConnected,
} from '../stores/tablesStore'
import { useRetryQueueStore, selectQueueLength } from '../stores/retryQueueStore'
import { TableCard } from '../components/TableCard'
import { TableDetailModal } from '../components/TableDetailModal'
import { AutogestionModal } from '../components/AutogestionModal'
import { Button } from '../components/Button'
import { PullToRefreshIndicator } from '../components/PullToRefreshIndicator'
import { usePullToRefresh } from '../hooks/usePullToRefresh'
import { usePersistedFilter, type TableFilterStatus } from '../hooks/usePersistedFilter'
import { UI_CONFIG } from '../utils/constants'

// Tab modes for the main navigation
type MainTab = 'comensales' | 'autogestion'

// Filter options for table grid
const FILTER_OPTIONS: { value: TableFilterStatus; label: string }[] = [
  { value: 'ALL', label: 'Todas' },
  { value: 'URGENT', label: 'Urgentes' },
  { value: 'ACTIVE', label: 'Activas' },
  { value: 'FREE', label: 'Libres' },
  { value: 'OUT_OF_SERVICE', label: 'Fuera servicio' },
]

export function MainPage() {
  const branchId = useAuthStore(selectSelectedBranchId)
  const user = useAuthStore(selectUser)
  const selectedBranchName = useAuthStore(selectSelectedBranchName)
  const logout = useAuthStore((s) => s.logout)
  const wsConnected = useTablesStore(selectWsConnected)
  const pendingCount = useRetryQueueStore(selectQueueLength)

  const tables = useTablesStore(selectTables)
  const isLoading = useTablesStore(selectIsLoading)
  const error = useTablesStore(selectError)
  const fetchTables = useTablesStore((s) => s.fetchTables)
  const subscribeToEvents = useTablesStore((s) => s.subscribeToEvents)

  // Main tab state
  const [mainTab, setMainTab] = useState<MainTab>('comensales')

  // Modal states
  const [selectedTableId, setSelectedTableId] = useState<number | null>(null)
  const [isAutogestionOpen, setIsAutogestionOpen] = useState(false)

  // Get updated table from store (reacts to WebSocket updates)
  const selectedTableForModal = selectedTableId !== null
    ? tables.find(t => t.table_id === selectedTableId) ?? null
    : null

  // Filter state
  const { filter, setFilter } = usePersistedFilter()

  // Pull-to-refresh
  const handleRefresh = useCallback(async () => {
    if (branchId) {
      await fetchTables(branchId)
    }
  }, [branchId, fetchTables])

  const { containerRef, pullDistance, isRefreshing, progress } = usePullToRefresh({
    onRefresh: handleRefresh,
    threshold: 80,
  })

  // Fetch tables on mount
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

  // Periodic refresh
  useEffect(() => {
    if (!branchId) return
    const interval = setInterval(() => {
      fetchTables(branchId)
    }, UI_CONFIG.TABLE_REFRESH_INTERVAL)
    return () => clearInterval(interval)
  }, [branchId, fetchTables])

  // Handle Autogestión tab click - opens modal
  const handleAutogestionClick = () => {
    setMainTab('autogestion')
    setIsAutogestionOpen(true)
  }

  // Handle modal close
  const handleAutogestionClose = () => {
    setIsAutogestionOpen(false)
    setMainTab('comensales')
  }

  // Group tables by status
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

  // Filter visibility
  const showUrgent = filter === 'ALL' || filter === 'URGENT'
  const showActive = filter === 'ALL' || filter === 'ACTIVE'
  const showFree = filter === 'ALL' || filter === 'FREE'
  const showOutOfService = filter === 'ALL' || filter === 'OUT_OF_SERVICE'

  // Filter counts
  const filterCounts: Record<TableFilterStatus, number> = {
    ALL: tables.length,
    URGENT: urgentTables.length,
    ACTIVE: activeTables.length,
    FREE: availableTables.length,
    OUT_OF_SERVICE: outOfServiceTables.length,
  }

  return (
    <div className="min-h-screen bg-white flex flex-col">
      {/* Custom Header with main navigation tabs */}
      <header role="banner" className="sticky top-0 z-50 bg-white border-b border-gray-200 shadow-sm">
        {/* Top bar with logo and user info */}
        <div className="px-4 py-2 flex items-center justify-between border-b border-gray-100">
          <div className="flex items-center gap-3">
            <h1 className="text-xl font-bold text-orange-500">Mozo</h1>
            {selectedBranchName && (
              <span className="text-sm text-gray-500">{selectedBranchName}</span>
            )}
          </div>

          <div className="flex items-center gap-3">
            {/* Pending operations */}
            {pendingCount > 0 && (
              <div className="flex items-center gap-1.5 bg-yellow-100 text-yellow-700 px-2 py-1 rounded-full text-xs font-medium">
                <svg className="w-3.5 h-3.5 animate-spin" fill="none" viewBox="0 0 24 24">
                  <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
                  <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z" />
                </svg>
                <span>{pendingCount}</span>
              </div>
            )}

            {/* Connection status */}
            <div className="flex items-center gap-1.5">
              <span className={`w-2 h-2 rounded-full ${wsConnected ? 'bg-green-500' : 'bg-red-500'}`} />
              <span className="text-xs text-gray-500 hidden sm:inline">
                {wsConnected ? 'En línea' : 'Sin conexión'}
              </span>
            </div>

            {/* User info */}
            {user && (
              <div className="flex items-center gap-2">
                <span className="text-sm text-gray-600 hidden sm:inline">
                  {user.email.split('@')[0]}
                </span>
                <Button variant="ghost" size="sm" onClick={logout}>
                  Salir
                </Button>
              </div>
            )}
          </div>
        </div>

        {/* Spacer between header and nav */}
        <div className="h-8 bg-white" />

        {/* Main navigation tabs */}
        <nav className="px-4 py-4 flex gap-3" aria-label="Navegación principal">
          <button
            onClick={() => setMainTab('comensales')}
            className={`flex-1 py-3 px-6 font-semibold text-base transition-all duration-200 ${
              mainTab === 'comensales'
                ? 'bg-orange-500 text-white shadow-md shadow-orange-200'
                : 'bg-gray-100 text-gray-600 hover:bg-gray-200'
            }`}
          >
            <div className="flex items-center justify-center gap-2">
              <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M17 20h5v-2a3 3 0 00-5.356-1.857M17 20H7m10 0v-2c0-.656-.126-1.283-.356-1.857M7 20H2v-2a3 3 0 015.356-1.857M7 20v-2c0-.656.126-1.283.356-1.857m0 0a5.002 5.002 0 019.288 0M15 7a3 3 0 11-6 0 3 3 0 016 0zm6 3a2 2 0 11-4 0 2 2 0 014 0zM7 10a2 2 0 11-4 0 2 2 0 014 0z" />
              </svg>
              Comensales
            </div>
          </button>
          <button
            onClick={handleAutogestionClick}
            className={`flex-1 py-3 px-6 font-semibold text-base transition-all duration-200 ${
              mainTab === 'autogestion'
                ? 'bg-orange-500 text-white shadow-md shadow-orange-200'
                : 'bg-gray-100 text-gray-600 hover:bg-gray-200'
            }`}
          >
            <div className="flex items-center justify-center gap-2">
              <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 5H7a2 2 0 00-2 2v12a2 2 0 002 2h10a2 2 0 002-2V7a2 2 0 00-2-2h-2M9 5a2 2 0 002 2h2a2 2 0 002-2M9 5a2 2 0 012-2h2a2 2 0 012 2m-3 7h3m-3 4h3m-6-4h.01M9 16h.01" />
              </svg>
              Autogestión
            </div>
          </button>
        </nav>

        {/* Spacer between nav and filter */}
        <div className="h-6 bg-white" />
      </header>

      {/* Pull-to-refresh indicator */}
      <PullToRefreshIndicator
        pullDistance={pullDistance}
        isRefreshing={isRefreshing}
        progress={progress}
      />

      {/* Loading bar */}
      {(isRefreshing || isLoading) && (
        <div className="absolute top-32 left-0 right-0 h-1 bg-orange-500/30 z-40">
          <div className="h-full bg-orange-500 animate-pulse" style={{ width: '100%' }} />
        </div>
      )}

      {/* Filter bar */}
      <div className="px-4 py-6 bg-gray-50 border-b border-gray-200">
        <div className="flex gap-2 overflow-x-auto pb-1 scrollbar-hide">
          {FILTER_OPTIONS.map((option) => {
            const count = filterCounts[option.value]
            const isActive = filter === option.value
            return (
              <button
                key={option.value}
                onClick={() => setFilter(option.value)}
                className={`flex-shrink-0 px-3 py-1.5 text-sm font-medium transition-colors ${
                  isActive
                    ? 'bg-orange-500 text-white'
                    : 'bg-gray-200 text-gray-600 hover:bg-gray-300'
                }`}
              >
                {option.label}
                {option.value !== 'ALL' && count > 0 && (
                  <span className={`ml-2 px-1.5 py-0.5 text-xs ${isActive ? 'bg-orange-600' : 'bg-gray-300'}`}>
                    {count}
                  </span>
                )}
              </button>
            )
          })}
        </div>
      </div>

      {/* Main content - Table grid */}
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
            <Button onClick={() => branchId && fetchTables(branchId)}>Reintentar</Button>
          </div>
        ) : (
          <div className="space-y-6">
            {/* Urgent tables */}
            {showUrgent && urgentTables.length > 0 && (
              <section>
                <h2 className="text-lg font-semibold text-red-500 mb-3 flex items-center gap-2">
                  <span className="w-2 h-2 rounded-full bg-red-500 animate-pulse" />
                  Requieren atención ({urgentTables.length})
                </h2>
                <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-4 xl:grid-cols-5 gap-3">
                  {urgentTables.map((table) => (
                    <TableCard key={table.table_id} table={table} onClick={() => setSelectedTableId(table.table_id)} />
                  ))}
                </div>
              </section>
            )}

            {/* Active tables */}
            {showActive && activeTables.length > 0 && (
              <section>
                <h2 className="text-lg font-semibold text-gray-700 mb-3">Mesas activas ({activeTables.length})</h2>
                <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-4 xl:grid-cols-5 gap-3">
                  {activeTables.map((table) => (
                    <TableCard key={table.table_id} table={table} onClick={() => setSelectedTableId(table.table_id)} />
                  ))}
                </div>
              </section>
            )}

            {/* Available tables */}
            {showFree && availableTables.length > 0 && (
              <section>
                <h2 className="text-lg font-semibold text-gray-700 mb-3">Mesas libres ({availableTables.length})</h2>
                <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-4 xl:grid-cols-5 gap-3">
                  {availableTables.map((table) => (
                    <TableCard key={table.table_id} table={table} onClick={() => setSelectedTableId(table.table_id)} />
                  ))}
                </div>
              </section>
            )}

            {/* Out of service tables */}
            {showOutOfService && outOfServiceTables.length > 0 && (
              <section>
                <h2 className="text-lg font-semibold text-gray-400 mb-3">Fuera de servicio ({outOfServiceTables.length})</h2>
                <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-4 xl:grid-cols-5 gap-3">
                  {outOfServiceTables.map((table) => (
                    <TableCard key={table.table_id} table={table} onClick={() => setSelectedTableId(table.table_id)} />
                  ))}
                </div>
              </section>
            )}

            {/* Empty states */}
            {tables.length === 0 && (
              <div className="flex flex-col items-center justify-center h-64">
                <p className="text-gray-500 mb-2">No hay mesas configuradas</p>
                <p className="text-gray-400 text-sm">Agrega mesas desde el Dashboard</p>
              </div>
            )}

            {tables.length > 0 && filter !== 'ALL' && filterCounts[filter] === 0 && (
              <div className="flex flex-col items-center justify-center h-64">
                <p className="text-gray-500 mb-2">No hay mesas con este filtro</p>
                <Button variant="secondary" onClick={() => setFilter('ALL')}>Mostrar todas</Button>
              </div>
            )}
          </div>
        )}
      </main>

      {/* Refresh button */}
      <div className="fixed bottom-4 right-4 z-40">
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
        onClose={() => setSelectedTableId(null)}
      />

      {/* Autogestión modal */}
      {branchId && (
        <AutogestionModal
          isOpen={isAutogestionOpen}
          onClose={handleAutogestionClose}
          branchId={branchId}
        />
      )}
    </div>
  )
}
