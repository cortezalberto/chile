import { useState, useEffect, useCallback, useMemo, useRef } from 'react'
import { useTablesStore, selectSelectedTable } from '../stores/tablesStore'
import { tablesAPI, roundsAPI } from '../services/api'
import { wsService } from '../services/websocket'
import { Header } from '../components/Header'
import { Button } from '../components/Button'
import { ConfirmDialog } from '../components/ConfirmDialog'
import { TableStatusBadge, RoundStatusBadge } from '../components/StatusBadge'
import { formatTableCode, formatPrice, formatTime } from '../utils/format'
// MED-08 FIX: Import WS event constants to avoid magic strings
import { WS_EVENT_TYPES } from '../utils/constants'
import type { TableSessionDetail, RoundDetail, WSEventType, RoundStatus } from '../types'

interface TableDetailPageProps {
  onBack: () => void
}

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
  const [sessionDetail, setSessionDetail] = useState<TableSessionDetail | null>(null)
  const [isLoading, setIsLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)

  // PWAW-006: Confirmation dialog state
  const [confirmRoundId, setConfirmRoundId] = useState<number | null>(null)
  const [confirmRoundNumber, setConfirmRoundNumber] = useState<number | null>(null)

  // WAITER-PAGE-MED-02: Loading state for actions
  const [isMarkingServed, setIsMarkingServed] = useState(false)
  const [isClearingTable, setIsClearingTable] = useState(false)

  // PWAW-M003: Round filter state
  const [roundFilter, setRoundFilter] = useState<RoundFilterStatus>('ALL')

  // WS-HIGH-05 FIX: Use refs to avoid re-subscription when callbacks change
  const tableIdRef = useRef(table?.table_id)
  const loadSessionDetailRef = useRef<() => Promise<void>>()

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
        // Pending includes SUBMITTED and IN_KITCHEN
        return sessionDetail.rounds.filter(
          (r) => r.status === 'SUBMITTED' || r.status === 'IN_KITCHEN'
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
      PENDING: rounds.filter((r) => r.status === 'SUBMITTED' || r.status === 'IN_KITCHEN').length,
      READY: rounds.filter((r) => r.status === 'READY').length,
      SERVED: rounds.filter((r) => r.status === 'SERVED').length,
    }
  }, [sessionDetail?.rounds])

  if (!table) {
    return (
      <div className="min-h-screen bg-[#0a0a0a] flex flex-col">
        <Header />
        <main className="flex-1 flex items-center justify-center">
          <div className="text-center">
            <p className="text-neutral-400 mb-4">Mesa no encontrada</p>
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
    <div className="min-h-screen bg-[#0a0a0a] flex flex-col">
      <Header />

      <main className="flex-1 p-4 overflow-auto">
        {/* Back button and table header */}
        <div className="mb-6">
          <button
            onClick={onBack}
            className="flex items-center gap-2 text-neutral-400 hover:text-white mb-4"
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
            <h1 className="text-3xl font-bold text-white">
              Mesa {formatTableCode(table.code)}
            </h1>
            <TableStatusBadge status={table.status} />
          </div>
        </div>

        {hasActiveSession ? (
          <div className="space-y-6">
            {/* Session summary */}
            <section className="bg-neutral-900 rounded-xl p-4 border border-neutral-800">
              <h2 className="text-lg font-semibold text-neutral-300 mb-3">
                Resumen de sesion
              </h2>
              <div className="grid grid-cols-2 gap-4">
                <div className="bg-neutral-800 rounded-lg p-3">
                  <p className="text-sm text-neutral-400">Rondas pendientes</p>
                  <p className="text-2xl font-bold text-orange-500">
                    {table.open_rounds}
                  </p>
                </div>
                <div className="bg-neutral-800 rounded-lg p-3">
                  <p className="text-sm text-neutral-400">Llamados pendientes</p>
                  <p className="text-2xl font-bold text-red-500">
                    {table.pending_calls}
                  </p>
                </div>
              </div>
              {/* Total from session detail */}
              {sessionDetail && (
                <div className="mt-4 pt-4 border-t border-neutral-800">
                  <div className="flex justify-between items-center">
                    <span className="text-neutral-400">Total consumido</span>
                    <span className="text-xl font-bold text-white">
                      {formatPrice(sessionDetail.total_cents)}
                    </span>
                  </div>
                </div>
              )}
            </section>

            {/* Service calls alert */}
            {table.pending_calls > 0 && (
              <section className="bg-red-500/10 rounded-xl p-4 border border-red-500/30">
                <h2 className="text-lg font-semibold text-red-500 mb-2 flex items-center gap-2">
                  <span className="w-2 h-2 rounded-full bg-red-500 animate-pulse" />
                  Llamados pendientes
                </h2>
                <p className="text-neutral-300">
                  Esta mesa tiene {table.pending_calls} llamado{table.pending_calls !== 1 ? 's' : ''} sin atender.
                </p>
              </section>
            )}

            {/* PWAW-002: Rounds detail */}
            {isLoading ? (
              <section className="bg-neutral-900 rounded-xl p-4 border border-neutral-800">
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
              <section className="bg-neutral-900 rounded-xl p-4 border border-neutral-800">
                <h2 className="text-lg font-semibold text-neutral-300 mb-3">
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
                            ? 'bg-orange-500 text-white'
                            : 'bg-neutral-800 text-neutral-400 hover:bg-neutral-700'
                        }`}
                      >
                        {option.label}
                        {count > 0 && (
                          <span
                            className={`ml-1 px-1.5 py-0.5 rounded-full text-xs ${
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

                <div className="space-y-4">
                  {filteredRounds.length === 0 ? (
                    <p className="text-neutral-500 text-center py-4">
                      No hay rondas con este filtro
                    </p>
                  ) : filteredRounds.map((round) => (
                    <div
                      key={round.id}
                      className="bg-neutral-800 rounded-lg p-3 border border-neutral-700"
                    >
                      {/* Round header */}
                      <div className="flex items-center justify-between mb-3">
                        <div className="flex items-center gap-2">
                          <span className="text-white font-medium">
                            Ronda {round.round_number}
                          </span>
                          <RoundStatusBadge status={round.status} size="sm" />
                        </div>
                        <span className="text-neutral-400 text-sm">
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
                                <span className="text-white">
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
                                <p className="text-neutral-500 text-xs mt-0.5">
                                  {item.notes}
                                </p>
                              )}
                            </div>
                            <span className="text-neutral-400 ml-2">
                              {formatPrice(item.unit_price_cents * item.qty)}
                            </span>
                          </div>
                        ))}
                      </div>

                      {/* Round footer */}
                      <div className="flex items-center justify-between pt-2 border-t border-neutral-700">
                        <span className="text-neutral-400 text-sm">
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
              <section className="bg-neutral-900 rounded-xl p-4 border border-neutral-800">
                <p className="text-neutral-500 text-center">
                  No hay rondas en esta sesion
                </p>
              </section>
            ) : null}

            {/* Diners */}
            {sessionDetail && sessionDetail.diners.length > 0 && (
              <section className="bg-neutral-900 rounded-xl p-4 border border-neutral-800">
                <h2 className="text-lg font-semibold text-neutral-300 mb-3">
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
                <p className="text-neutral-300">
                  Estado: <span className="font-medium">{table.check_status}</span>
                </p>
                {sessionDetail && (
                  <div className="mt-2 text-neutral-300">
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
        ) : (
          <div className="flex flex-col items-center justify-center h-64">
            <p className="text-neutral-400">Sin sesion activa</p>
            <p className="text-neutral-500 text-sm mt-2">
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
