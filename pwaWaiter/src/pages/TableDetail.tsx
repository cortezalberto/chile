import { useState, useEffect, useCallback, useMemo, useRef } from 'react'
import { useTablesStore, selectSelectedTable } from '../stores/tablesStore'
import { useAuthStore, selectUser } from '../stores/authStore'
import { tablesAPI, roundsAPI, serviceCallsAPI } from '../services/api'
import { wsService } from '../services/websocket'
import { Header } from '../components/Header'
import { Button } from '../components/Button'
import { ConfirmDialog } from '../components/ConfirmDialog'
import { ComandaTab } from '../components/ComandaTab'
import { TableStatusBadge, RoundStatusBadge } from '../components/StatusBadge'
import { formatTableCode, formatPrice, formatTime } from '../utils/format'
// MED-08 FIX: Import WS event constants to avoid magic strings
import { WS_EVENT_TYPES } from '../utils/constants'
import type { TableSessionDetail, RoundDetail, WSEventType, RoundStatus } from '../types'

interface TableDetailPageProps {
  onBack: () => void
}

// COMANDA-002: Main tab options
type MainTab = 'session' | 'comanda'

// PWAW-M003: Round filter options
type RoundFilterStatus = RoundStatus | 'ALL' | 'PENDING'
const ROUND_FILTER_OPTIONS: { value: RoundFilterStatus; label: string }[] = [
  { value: 'ALL', label: 'Todas' },
  { value: 'PENDING', label: 'Pendientes' },
  { value: 'READY', label: 'Listas' },
  { value: 'SERVED', label: 'Servidas' },
]

export function TableDetailPage({ onBack }: TableDetailPageProps) {
  const table = useTablesStore(selectSelectedTable)
  const clearTable = useTablesStore((s) => s.clearTable)
  const user = useAuthStore(selectUser)
  const [sessionDetail, setSessionDetail] = useState<TableSessionDetail | null>(null)
  const [isLoading, setIsLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)

  // COMANDA-002: Main tab state
  const [mainTab, setMainTab] = useState<MainTab>('session')

  // PWAW-006: Confirmation dialog state
  const [confirmRoundId, setConfirmRoundId] = useState<number | null>(null)
  const [confirmRoundNumber, setConfirmRoundNumber] = useState<number | null>(null)

  // WAITER-PAGE-MED-02: Loading state for actions
  const [isMarkingServed, setIsMarkingServed] = useState(false)
  const [isClearingTable, setIsClearingTable] = useState(false)
  // QA-FIX: Loading state for resolving service calls
  const [isResolvingCall, setIsResolvingCall] = useState(false)

  // PWAW-M003: Round filter state
  const [roundFilter, setRoundFilter] = useState<RoundFilterStatus>('ALL')

  // WS-HIGH-05 FIX: Use refs to avoid re-subscription when callbacks change
  const tableIdRef = useRef(table?.table_id)
  const loadSessionDetailRef = useRef<(() => Promise<void>) | undefined>(undefined)

  // Load session detail when table is selected
  const loadSessionDetail = useCallback(async () => {
    if (!table?.session_id) return

    setIsLoading(true)
    setError(null)
    try {
      const detail = await tablesAPI.getTableSessionDetail(table.table_id)
      setSessionDetail(detail)
    } catch (err) {
      setError('Error al cargar detalles de la sesion')
      console.error('Failed to load session detail:', err)
    } finally {
      setIsLoading(false)
    }
  }, [table?.table_id, table?.session_id])

  // WS-HIGH-05 FIX: Keep refs updated with latest values
  useEffect(() => {
    tableIdRef.current = table?.table_id
  }, [table?.table_id])

  useEffect(() => {
    loadSessionDetailRef.current = loadSessionDetail
  }, [loadSessionDetail])

  useEffect(() => {
    loadSessionDetail()
  }, [loadSessionDetail])

  // PWAW-A006: WebSocket listener to refresh on relevant events
  // WS-HIGH-05 FIX: Subscribe once using refs to avoid re-subscription when callbacks change
  useEffect(() => {
    // MED-08 FIX: Use WS event constants instead of magic strings
    // Events that should trigger a refresh for this table
    const relevantEvents: WSEventType[] = [
      WS_EVENT_TYPES.ROUND_PENDING,  // New round created by customer
      WS_EVENT_TYPES.ROUND_SUBMITTED,
      WS_EVENT_TYPES.ROUND_IN_KITCHEN,
      WS_EVENT_TYPES.ROUND_READY,
      WS_EVENT_TYPES.ROUND_SERVED,
      WS_EVENT_TYPES.SERVICE_CALL_CREATED,
      WS_EVENT_TYPES.SERVICE_CALL_ACKED,
      WS_EVENT_TYPES.SERVICE_CALL_CLOSED,
      WS_EVENT_TYPES.CHECK_REQUESTED,
      WS_EVENT_TYPES.CHECK_PAID,
    ]

    // WS-HIGH-05 FIX: Use refs to access latest values without causing re-subscription
    const unsubscribers = relevantEvents.map((eventType) =>
      wsService.on(eventType, (event) => {
        // Only refresh if event is for this table (using ref for latest table_id)
        if (tableIdRef.current && event.table_id === tableIdRef.current) {
          loadSessionDetailRef.current?.()
        }
      })
    )

    return () => {
      unsubscribers.forEach((unsub) => unsub())
    }
  }, []) // WS-HIGH-05 FIX: Empty deps - subscribe once, use refs for latest values

  // PWAW-006: Show confirmation dialog before marking as served
  const promptMarkServed = (roundId: number, roundNumber: number) => {
    setConfirmRoundId(roundId)
    setConfirmRoundNumber(roundNumber)
  }

  // Mark round as served (after confirmation)
  // WAITER-PAGE-MED-02: Added loading state for better UX
  const handleMarkServed = async () => {
    if (!confirmRoundId) return

    setIsMarkingServed(true)
    try {
      await roundsAPI.markAsServed(confirmRoundId)
      // Reload session detail to update UI
      await loadSessionDetail()
    } catch (err) {
      console.error('Failed to mark round as served:', err)
    } finally {
      setIsMarkingServed(false)
      setConfirmRoundId(null)
      setConfirmRoundNumber(null)
    }
  }

  const cancelConfirm = () => {
    setConfirmRoundId(null)
    setConfirmRoundNumber(null)
  }

  // QA-FIX: Handle resolving a service call
  const handleResolveServiceCall = async (callId: number) => {
    setIsResolvingCall(true)
    try {
      await serviceCallsAPI.resolve(callId)
      // The WebSocket event SERVICE_CALL_CLOSED will update the state
      // and reload session detail automatically
    } catch (err) {
      console.error('Failed to resolve service call:', err)
    } finally {
      setIsResolvingCall(false)
    }
  }

  // Calculate round subtotal
  const getRoundSubtotal = (round: RoundDetail): number => {
    return round.items.reduce((sum, item) => sum + item.unit_price_cents * item.qty, 0)
  }

  // PWAW-M003: Filter rounds based on selected filter
  // Must be before early return to satisfy React hooks rules
  const filteredRounds = useMemo(() => {
    if (!sessionDetail?.rounds) return []

    switch (roundFilter) {
      case 'PENDING':
        // Include PENDING (new from customer), SUBMITTED, and IN_KITCHEN
        return sessionDetail.rounds.filter(
          (r) => r.status === 'PENDING' || r.status === 'SUBMITTED' || r.status === 'IN_KITCHEN'
        )
      case 'READY':
        return sessionDetail.rounds.filter((r) => r.status === 'READY')
      case 'SERVED':
        return sessionDetail.rounds.filter((r) => r.status === 'SERVED')
      default:
        return sessionDetail.rounds
    }
  }, [sessionDetail?.rounds, roundFilter])

  // PWAW-M003: Count rounds by filter for badges
  const roundFilterCounts = useMemo(() => {
    if (!sessionDetail?.rounds) return { ALL: 0, PENDING: 0, READY: 0, SERVED: 0 }

    const rounds = sessionDetail.rounds
    return {
      ALL: rounds.length,
      // Include PENDING status in the count
      PENDING: rounds.filter((r) => r.status === 'PENDING' || r.status === 'SUBMITTED' || r.status === 'IN_KITCHEN').length,
      READY: rounds.filter((r) => r.status === 'READY').length,
      SERVED: rounds.filter((r) => r.status === 'SERVED').length,
    }
  }, [sessionDetail?.rounds])

  // Check if there are rounds ready to pickup
  const hasReadyRounds = useMemo(() => {
    return sessionDetail?.rounds.some((r) => r.status === 'READY') ?? false
  }, [sessionDetail?.rounds])

  if (!table) {
    return (
      <div className="min-h-screen bg-white flex flex-col">
        <Header />
        <main className="flex-1 flex items-center justify-center">
          <div className="text-center">
            <p className="text-gray-500 mb-4">Mesa no encontrada</p>
            <Button onClick={onBack}>Volver</Button>
          </div>
        </main>
      </div>
    )
  }

  const hasActiveSession = table.session_id !== null

  // WAITER-PAGE-MED-02: Added loading state for better UX
  const handleClearTable = async () => {
    setIsClearingTable(true)
    try {
      await clearTable(table.table_id)
      onBack()
    } catch {
      // Error handled in store
    } finally {
      setIsClearingTable(false)
    }
  }

  return (
    <div className="min-h-screen bg-white flex flex-col">
      <Header />

      <main className="flex-1 p-4 overflow-auto">
        {/* Back button and table header */}
        <div className="mb-6">
          <button
            onClick={onBack}
            className="flex items-center gap-2 text-gray-500 hover:text-gray-900 mb-4"
          >
            <svg
              className="w-5 h-5"
              fill="none"
              stroke="currentColor"
              viewBox="0 0 24 24"
            >
              <path
                strokeLinecap="round"
                strokeLinejoin="round"
                strokeWidth={2}
                d="M15 19l-7-7 7-7"
              />
            </svg>
            Volver
          </button>

          <div className="flex items-center justify-between">
            <h1 className="text-3xl font-bold text-gray-900">
              Mesa {formatTableCode(table.code)}
            </h1>
            <TableStatusBadge status={table.status} />
          </div>

          {/* COMANDA-002: Main tabs (Session / Comanda) */}
          {hasActiveSession && (
            <div className="flex gap-2 mt-4">
              <button
                onClick={() => setMainTab('session')}
                className={`flex-1 py-2 px-4 rounded-lg font-medium transition-colors ${
                  mainTab === 'session'
                    ? 'bg-orange-500 text-gray-900'
                    : 'bg-white text-gray-500 hover:bg-gray-100'
                }`}
              >
                Sesión
              </button>
              <button
                onClick={() => setMainTab('comanda')}
                className={`flex-1 py-2 px-4 rounded-lg font-medium transition-colors ${
                  mainTab === 'comanda'
                    ? 'bg-orange-500 text-gray-900'
                    : 'bg-white text-gray-500 hover:bg-gray-100'
                }`}
              >
                🍽️ Comanda
              </button>
            </div>
          )}
        </div>

        {hasActiveSession ? (
          mainTab === 'comanda' && table.session_id && user?.branch_ids?.[0] ? (
            // COMANDA-002: Comanda tab content
            <div className="flex-1 overflow-hidden">
              <ComandaTab
                branchId={user.branch_ids[0]}
                sessionId={table.session_id}
                onRoundSubmitted={loadSessionDetail}
              />
            </div>
          ) : (
          <div className="space-y-6">
            {/* Session summary */}
            <section className="bg-gray-50 rounded-xl p-4 border border-gray-200">
              <h2 className="text-lg font-semibold text-gray-700 mb-3">
                Resumen de sesion
              </h2>
              <div className="grid grid-cols-2 gap-4">
                <div className="bg-white rounded-lg p-3">
                  <p className="text-sm text-gray-500">Rondas pendientes</p>
                  <p className="text-2xl font-bold text-orange-500">
                    {table.open_rounds}
                  </p>
                </div>
                <div className="bg-white rounded-lg p-3">
                  <p className="text-sm text-gray-500">Llamados pendientes</p>
                  <p className="text-2xl font-bold text-red-500">
                    {table.pending_calls}
                  </p>
                </div>
              </div>
              {/* Total from session detail */}
              {sessionDetail && (
                <div className="mt-4 pt-4 border-t border-gray-200">
                  <div className="flex justify-between items-center">
                    <span className="text-gray-500">Total consumido</span>
                    <span className="text-xl font-bold text-gray-900">
                      {formatPrice(sessionDetail.total_cents)}
                    </span>
                  </div>
                </div>
              )}
            </section>

            {/* Service calls alert - QA-FIX: Made interactive for resolution */}
            {table.pending_calls > 0 && (
              <section className="bg-red-500/10 rounded-xl p-4 border border-red-500/30">
                <h2 className="text-lg font-semibold text-red-500 mb-2 flex items-center gap-2">
                  <span className="w-2 h-2 rounded-full bg-red-500 animate-pulse" />
                  Llamados pendientes
                </h2>
                <p className="text-gray-700 mb-3">
                  Esta mesa tiene {table.pending_calls} llamado{table.pending_calls !== 1 ? 's' : ''} sin atender.
                </p>
                {/* Show resolve button for each active service call */}
                {table.activeServiceCallIds && table.activeServiceCallIds.length > 0 ? (
                  <div className="space-y-2">
                    {table.activeServiceCallIds.map((callId) => (
                      <button
                        key={callId}
                        onClick={() => handleResolveServiceCall(callId)}
                        disabled={isResolvingCall}
                        className="w-full py-2 px-4 bg-red-500 text-white rounded-lg font-medium hover:bg-red-600 disabled:opacity-50 disabled:cursor-not-allowed transition-colors flex items-center justify-center gap-2"
                      >
                        {isResolvingCall ? (
                          <>
                            <div className="animate-spin w-4 h-4 border-2 border-white border-t-transparent rounded-full" />
                            Marcando...
                          </>
                        ) : (
                          <>
                            <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M5 13l4 4L19 7" />
                            </svg>
                            Marcar como atendido
                          </>
                        )}
                      </button>
                    ))}
                  </div>
                ) : (
                  // Fallback when we don't have call IDs (e.g., page loaded before WS events)
                  <p className="text-gray-500 text-sm italic">
                    Las llamadas se actualizarán automáticamente.
                  </p>
                )}
              </section>
            )}

            {/* Ready rounds alert - Go to kitchen to pickup */}
            {hasReadyRounds && (
              <section className="bg-green-500/10 rounded-xl p-4 border border-green-500/30 animate-pulse">
                <div className="flex items-center gap-2 text-green-600">
                  <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M5 13l4 4L19 7" />
                  </svg>
                  <span className="font-medium">
                    ¡Pedido listo! Recoger en cocina
                  </span>
                </div>
              </section>
            )}

            {/* PWAW-002: Rounds detail */}
            {isLoading ? (
              <section className="bg-gray-50 rounded-xl p-4 border border-gray-200">
                <div className="flex justify-center py-8">
                  <div className="animate-spin w-8 h-8 border-2 border-orange-500 border-t-transparent rounded-full" />
                </div>
              </section>
            ) : error ? (
              <section className="bg-red-500/10 rounded-xl p-4 border border-red-500/30">
                <p className="text-red-400 text-center">{error}</p>
                <Button
                  variant="secondary"
                  className="w-full mt-3"
                  onClick={loadSessionDetail}
                >
                  Reintentar
                </Button>
              </section>
            ) : sessionDetail && sessionDetail.rounds.length > 0 ? (
              <section className="bg-gray-50 rounded-xl p-4 border border-gray-200">
                <h2 className="text-lg font-semibold text-gray-700 mb-3">
                  Detalle de rondas ({sessionDetail.rounds.length})
                </h2>

                {/* PWAW-M003: Round filter tabs */}
                <div className="flex gap-2 overflow-x-auto pb-3 mb-3 scrollbar-hide">
                  {ROUND_FILTER_OPTIONS.map((option) => {
                    const count = roundFilterCounts[option.value as keyof typeof roundFilterCounts]
                    const isActive = roundFilter === option.value
                    return (
                      <button
                        key={option.value}
                        onClick={() => setRoundFilter(option.value)}
                        className={`flex-shrink-0 px-3 py-1 rounded-full text-xs font-medium transition-colors ${
                          isActive
                            ? 'bg-orange-500 text-gray-900'
                            : 'bg-white text-gray-500 hover:bg-gray-100'
                        }`}
                      >
                        {option.label}
                        {count > 0 && (
                          <span
                            className={`ml-1 px-1.5 py-0.5 rounded-full text-xs ${
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

                <div className="space-y-4">
                  {filteredRounds.length === 0 ? (
                    <p className="text-gray-400 text-center py-4">
                      No hay rondas con este filtro
                    </p>
                  ) : filteredRounds.map((round) => (
                    <div
                      key={round.id}
                      className="bg-white rounded-lg p-3 border border-gray-200"
                    >
                      {/* Round header */}
                      <div className="flex items-center justify-between mb-3">
                        <div className="flex items-center gap-2">
                          <span className="text-gray-900 font-medium">
                            Ronda {round.round_number}
                          </span>
                          <RoundStatusBadge status={round.status} size="sm" />
                        </div>
                        <span className="text-gray-500 text-sm">
                          {round.submitted_at ? formatTime(round.submitted_at) : ''}
                        </span>
                      </div>

                      {/* Round items */}
                      <div className="space-y-2 mb-3">
                        {round.items.map((item) => (
                          <div
                            key={item.id}
                            className="flex items-start justify-between text-sm"
                          >
                            <div className="flex-1">
                              <div className="flex items-center gap-2">
                                <span className="text-gray-900">
                                  {item.qty}x {item.product_name}
                                </span>
                                {item.diner_name && (
                                  <span
                                    className="text-xs px-1.5 py-0.5 rounded-full"
                                    style={{
                                      backgroundColor: item.diner_color
                                        ? `${item.diner_color}33`
                                        : '#52525233',
                                      color: item.diner_color || '#a3a3a3',
                                    }}
                                  >
                                    {item.diner_name}
                                  </span>
                                )}
                              </div>
                              {item.notes && (
                                <p className="text-gray-400 text-xs mt-0.5">
                                  {item.notes}
                                </p>
                              )}
                            </div>
                            <span className="text-gray-500 ml-2">
                              {formatPrice(item.unit_price_cents * item.qty)}
                            </span>
                          </div>
                        ))}
                      </div>

                      {/* Round footer */}
                      <div className="flex items-center justify-between pt-2 border-t border-gray-200">
                        <span className="text-gray-500 text-sm">
                          Subtotal: {formatPrice(getRoundSubtotal(round))}
                        </span>
                        {round.status === 'READY' && (
                          <Button
                            variant="primary"
                            size="sm"
                            onClick={() => promptMarkServed(round.id, round.round_number)}
                          >
                            Marcar servido
                          </Button>
                        )}
                      </div>
                    </div>
                  ))}
                </div>
              </section>
            ) : sessionDetail ? (
              <section className="bg-gray-50 rounded-xl p-4 border border-gray-200">
                <p className="text-gray-400 text-center">
                  No hay rondas en esta sesion
                </p>
              </section>
            ) : null}

            {/* Diners */}
            {sessionDetail && sessionDetail.diners.length > 0 && (
              <section className="bg-gray-50 rounded-xl p-4 border border-gray-200">
                <h2 className="text-lg font-semibold text-gray-700 mb-3">
                  Comensales ({sessionDetail.diners.length})
                </h2>
                <div className="flex flex-wrap gap-2">
                  {sessionDetail.diners.map((diner) => (
                    <span
                      key={diner.id}
                      className="inline-flex items-center gap-2 px-3 py-1.5 rounded-full text-sm"
                      style={{
                        backgroundColor: `${diner.color}22`,
                        color: diner.color,
                      }}
                    >
                      <span
                        className="w-2 h-2 rounded-full"
                        style={{ backgroundColor: diner.color }}
                      />
                      {diner.name}
                    </span>
                  ))}
                </div>
              </section>
            )}

            {/* Check status */}
            {table.check_status && (
              <section className="bg-purple-500/10 rounded-xl p-4 border border-purple-500/30">
                <h2 className="text-lg font-semibold text-purple-500 mb-2">
                  Estado de cuenta
                </h2>
                <p className="text-gray-700">
                  Estado: <span className="font-medium">{table.check_status}</span>
                </p>
                {sessionDetail && (
                  <div className="mt-2 text-gray-700">
                    <p>
                      Total: <span className="font-medium">{formatPrice(sessionDetail.total_cents)}</span>
                    </p>
                    {sessionDetail.paid_cents > 0 && (
                      <p>
                        Pagado: <span className="font-medium text-green-400">{formatPrice(sessionDetail.paid_cents)}</span>
                      </p>
                    )}
                  </div>
                )}
                {table.check_status === 'PAID' && (
                  <Button
                    variant="primary"
                    className="w-full mt-4"
                    onClick={handleClearTable}
                    disabled={isClearingTable}
                  >
                    {isClearingTable ? 'Liberando...' : 'Liberar Mesa'}
                  </Button>
                )}
              </section>
            )}
          </div>
          )
        ) : (
          <div className="flex flex-col items-center justify-center h-64">
            <p className="text-gray-500">Sin sesion activa</p>
            <p className="text-gray-400 text-sm mt-2">
              La mesa esta disponible
            </p>
          </div>
        )}
      </main>

      {/* PWAW-006: Confirmation dialog for marking round as served */}
      {/* WAITER-PAGE-MED-02: Added loading state */}
      <ConfirmDialog
        isOpen={confirmRoundId !== null}
        title="Marcar como servido"
        message={`¿Confirmar que la ronda ${confirmRoundNumber} fue entregada a la mesa?`}
        confirmLabel="Confirmar"
        cancelLabel="Cancelar"
        onConfirm={handleMarkServed}
        onCancel={cancelConfirm}
        isLoading={isMarkingServed}
      />
    </div>
  )
}
