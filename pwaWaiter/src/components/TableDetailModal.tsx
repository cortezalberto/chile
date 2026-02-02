import { useState, useEffect, useCallback, useMemo, useRef } from 'react'
import { tablesAPI, roundsAPI, serviceCallsAPI, type DeleteRoundItemResponse } from '../services/api'
import { wsService } from '../services/websocket'
import { useTablesStore } from '../stores/tablesStore'
import { Button } from './Button'
import { ConfirmDialog } from './ConfirmDialog'
import { TableStatusBadge, RoundStatusBadge } from './StatusBadge'
import { formatTableCode, formatPrice, formatTime } from '../utils/format'
import { WS_EVENT_TYPES } from '../utils/constants'
import type { TableCard, TableSessionDetail, RoundDetail, RoundItemDetail, WSEventType, RoundStatus } from '../types'

interface TableDetailModalProps {
  table: TableCard | null
  isOpen: boolean
  onClose: () => void
}

// Round filter options
type RoundFilterStatus = RoundStatus | 'ALL' | 'PENDING'
const ROUND_FILTER_OPTIONS: { value: RoundFilterStatus; label: string }[] = [
  { value: 'ALL', label: 'Todas' },
  { value: 'PENDING', label: 'Pendientes' },
  { value: 'READY', label: 'Listas' },
  { value: 'SERVED', label: 'Servidas' },
]

// Category order: Bebidas > Entradas > Principales > Postres > Others
const CATEGORY_ORDER: Record<string, number> = {
  'bebidas': 0,
  'bebida': 0,
  'drinks': 0,
  'entradas': 1,
  'entrada': 1,
  'starters': 1,
  'appetizers': 1,
  'principales': 2,
  'principal': 2,
  'platos principales': 2,
  'main': 2,
  'mains': 2,
  'postres': 3,
  'postre': 3,
  'desserts': 3,
  'dessert': 3,
}

function getCategoryOrder(categoryName: string | null): number {
  if (!categoryName) return 99
  const lower = categoryName.toLowerCase()
  return CATEGORY_ORDER[lower] ?? 99
}

export function TableDetailModal({ table, isOpen, onClose }: TableDetailModalProps) {
  const [sessionDetail, setSessionDetail] = useState<TableSessionDetail | null>(null)
  const [isLoading, setIsLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)

  // Confirmation dialog state
  const [confirmRoundId, setConfirmRoundId] = useState<number | null>(null)
  const [confirmRoundNumber, setConfirmRoundNumber] = useState<number | null>(null)
  const [isMarkingServed, setIsMarkingServed] = useState(false)

  // Round filter state
  const [roundFilter, setRoundFilter] = useState<RoundFilterStatus>('ALL')

  // Service call resolve state
  const [isResolvingCall, setIsResolvingCall] = useState(false)

  // Round confirmation state (PENDING → CONFIRMED)
  const [isConfirmingRound, setIsConfirmingRound] = useState<number | null>(null)

  // Delete item state
  const [deletingItemId, setDeletingItemId] = useState<number | null>(null)
  const [deleteConfirm, setDeleteConfirm] = useState<{ roundId: number; item: RoundItemDetail } | null>(null)

  // Refs for WS event handling
  const tableIdRef = useRef(table?.table_id)
  const loadSessionDetailRef = useRef<(() => Promise<void>) | undefined>(undefined)

  // Track previously focused element to restore on close
  const previousActiveElement = useRef<HTMLElement | null>(null)

  // Load session detail
  const loadSessionDetail = useCallback(async () => {
    if (!table?.session_id) {
      setSessionDetail(null)
      return
    }

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

  // Keep refs updated
  useEffect(() => {
    tableIdRef.current = table?.table_id
  }, [table?.table_id])

  useEffect(() => {
    loadSessionDetailRef.current = loadSessionDetail
  }, [loadSessionDetail])

  // Load detail when modal opens
  useEffect(() => {
    if (isOpen && table) {
      loadSessionDetail()
      // Store the currently focused element
      previousActiveElement.current = document.activeElement as HTMLElement | null
    }
  }, [isOpen, table, loadSessionDetail])

  // Restore focus on close
  useEffect(() => {
    if (!isOpen && previousActiveElement.current) {
      previousActiveElement.current.focus()
      previousActiveElement.current = null
    }
  }, [isOpen])

  // Reset resolving state when pending_calls becomes 0 or modal closes
  useEffect(() => {
    if (!isOpen || (table?.pending_calls ?? 0) === 0) {
      setIsResolvingCall(false)
    }
  }, [isOpen, table?.pending_calls])

  // WebSocket listener to refresh on relevant events
  useEffect(() => {
    if (!isOpen) return

    const relevantEvents: WSEventType[] = [
      WS_EVENT_TYPES.ROUND_PENDING,    // New round created by customer
      WS_EVENT_TYPES.ROUND_CONFIRMED,  // Waiter confirmed order at table
      WS_EVENT_TYPES.ROUND_SUBMITTED,
      WS_EVENT_TYPES.ROUND_IN_KITCHEN,
      WS_EVENT_TYPES.ROUND_READY,
      WS_EVENT_TYPES.ROUND_SERVED,
      WS_EVENT_TYPES.ROUND_ITEM_DELETED, // Item deleted from round
      WS_EVENT_TYPES.SERVICE_CALL_CREATED,
      WS_EVENT_TYPES.SERVICE_CALL_ACKED,
      WS_EVENT_TYPES.SERVICE_CALL_CLOSED,
      WS_EVENT_TYPES.CHECK_REQUESTED,
      WS_EVENT_TYPES.CHECK_PAID,
    ]

    const unsubscribers = relevantEvents.map((eventType) =>
      wsService.on(eventType, (event) => {
        if (tableIdRef.current && event.table_id === tableIdRef.current) {
          loadSessionDetailRef.current?.()
        }
      })
    )

    return () => {
      unsubscribers.forEach((unsub) => unsub())
    }
  }, [isOpen])

  // Handle keyboard events (Escape to close)
  useEffect(() => {
    if (!isOpen) return

    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === 'Escape') {
        onClose()
      }
    }

    window.addEventListener('keydown', handleKeyDown)
    return () => window.removeEventListener('keydown', handleKeyDown)
  }, [isOpen, onClose])

  // Show confirmation dialog before marking as served
  const promptMarkServed = (roundId: number, roundNumber: number) => {
    setConfirmRoundId(roundId)
    setConfirmRoundNumber(roundNumber)
  }

  // Mark round as served (after confirmation)
  const handleMarkServed = async () => {
    if (!confirmRoundId) return

    setIsMarkingServed(true)
    try {
      await roundsAPI.markAsServed(confirmRoundId)
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

  // Handle resolve service call
  const handleResolveServiceCall = async () => {
    const callId = table?.activeServiceCallIds?.[0]
    if (!callId || isResolvingCall) return

    setIsResolvingCall(true)
    try {
      await serviceCallsAPI.resolve(callId)
      // Keep button green - WS event will update pending_calls and hide the section
    } catch (err) {
      console.error('Failed to resolve service call:', err)
      // Only reset on error so user can retry
      setIsResolvingCall(false)
    }
  }

  // Handle confirm round (PENDING → CONFIRMED)
  // Waiter verifies order at table before admin sends to kitchen
  const handleConfirmRound = async (roundId: number) => {
    if (isConfirmingRound === roundId) return

    setIsConfirmingRound(roundId)
    try {
      await roundsAPI.confirmRound(roundId)
      await loadSessionDetail()
    } catch (err) {
      console.error('Failed to confirm round:', err)
    } finally {
      setIsConfirmingRound(null)
    }
  }

  // Prompt to delete an item from a round
  const promptDeleteItem = (roundId: number, item: RoundItemDetail) => {
    setDeleteConfirm({ roundId, item })
  }

  // Get decrementOpenRounds from store
  const decrementOpenRounds = useTablesStore((state) => state.decrementOpenRounds)

  // Handle delete item (after confirmation)
  const handleDeleteItem = async () => {
    if (!deleteConfirm || !table) return

    const { roundId, item } = deleteConfirm
    setDeletingItemId(item.id)
    try {
      const result: DeleteRoundItemResponse = await roundsAPI.deleteItem(roundId, item.id)
      if (result.success) {
        // QA-FIX: If round was deleted (no items left), decrement open_rounds counter
        if (result.round_deleted) {
          decrementOpenRounds(table.table_id)
        }
        // Reload session detail to reflect changes
        await loadSessionDetail()
      }
    } catch (err) {
      console.error('Failed to delete item:', err)
    } finally {
      setDeletingItemId(null)
      setDeleteConfirm(null)
    }
  }

  const cancelDeleteConfirm = () => {
    setDeleteConfirm(null)
  }

  // Check if round allows item deletion (only PENDING or CONFIRMED)
  const canDeleteItems = (round: RoundDetail): boolean => {
    return round.status === 'PENDING' || round.status === 'CONFIRMED'
  }

  // Calculate round subtotal
  const getRoundSubtotal = (round: RoundDetail): number => {
    return round.items.reduce((sum, item) => sum + item.unit_price_cents * item.qty, 0)
  }

  // Filter rounds based on selected filter
  const filteredRounds = useMemo(() => {
    if (!sessionDetail?.rounds) return []

    switch (roundFilter) {
      case 'PENDING':
        // Include PENDING (new from customer), CONFIRMED (verified by waiter),
        // SUBMITTED, and IN_KITCHEN
        return sessionDetail.rounds.filter(
          (r) => r.status === 'PENDING' || r.status === 'CONFIRMED' || r.status === 'SUBMITTED' || r.status === 'IN_KITCHEN'
        )
      case 'READY':
        return sessionDetail.rounds.filter((r) => r.status === 'READY')
      case 'SERVED':
        return sessionDetail.rounds.filter((r) => r.status === 'SERVED')
      default:
        return sessionDetail.rounds
    }
  }, [sessionDetail?.rounds, roundFilter])

  // Check if there are rounds ready to pickup
  const hasReadyRounds = useMemo(() => {
    return sessionDetail?.rounds.some((r) => r.status === 'READY') ?? false
  }, [sessionDetail?.rounds])

  if (!isOpen || !table) return null

  const hasActiveSession = table.session_id !== null

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4">
      {/* Backdrop */}
      <div
        className="absolute inset-0 bg-black/70 backdrop-blur-sm"
        onClick={onClose}
        aria-hidden="true"
      />

      {/* Modal */}
      <div
        className="relative bg-white border border-gray-200 w-full max-w-lg max-h-[90vh] overflow-hidden shadow-xl animate-slide-up flex flex-col"
        role="dialog"
        aria-modal="true"
        aria-labelledby="table-detail-modal-title"
      >
        {/* Header */}
        <div className="flex items-center justify-between p-4 border-b border-gray-200">
          <div className="flex items-center gap-3">
            <h2
              id="table-detail-modal-title"
              className="text-xl font-bold text-gray-900"
            >
              Mesa {formatTableCode(table.code)}
            </h2>
            <TableStatusBadge status={table.status} size="sm" />
          </div>
          <button
            onClick={onClose}
            className="p-2 text-gray-400 hover:text-gray-900 hover:bg-gray-100 transition-colors"
            aria-label="Cerrar"
          >
            <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
            </svg>
          </button>
        </div>

        {/* Content */}
        <div className="flex-1 overflow-y-auto p-4 space-y-4">
          {hasActiveSession ? (
            <>
              {/* Session summary */}
              <section className="bg-gray-100 p-3">
                <div className="grid grid-cols-2 gap-3">
                  <div className="bg-white p-2 shadow-sm">
                    <p className="text-xs text-gray-500">Rondas pendientes</p>
                    <p className="text-xl font-bold text-orange-500">
                      {table.open_rounds}
                    </p>
                  </div>
                  <div className="bg-white p-2 shadow-sm">
                    <p className="text-xs text-gray-500">Llamados</p>
                    <p className="text-xl font-bold text-red-500">
                      {table.pending_calls}
                    </p>
                  </div>
                </div>
                {sessionDetail && (
                  <div className="mt-3 pt-3 border-t border-gray-200">
                    <div className="flex justify-between items-center">
                      <span className="text-gray-500 text-sm">Total consumido</span>
                      <span className="text-lg font-bold text-gray-900">
                        {formatPrice(sessionDetail.total_cents)}
                      </span>
                    </div>
                  </div>
                )}
              </section>

              {/* Service calls alert */}
              {table.pending_calls > 0 && (
                <section className="bg-red-500/10 p-3 border border-red-500/30">
                  <div className="flex items-center justify-between">
                    <div className="flex items-center gap-2 text-red-500">
                      <span className="w-2 h-2 rounded-full bg-red-500 animate-pulse" />
                      <span className="font-medium">
                        {table.pending_calls} llamado{table.pending_calls !== 1 ? 's' : ''} pendiente{table.pending_calls !== 1 ? 's' : ''}
                      </span>
                    </div>
                    <button
                      onClick={handleResolveServiceCall}
                      disabled={isResolvingCall || !table.activeServiceCallIds?.length}
                      className={`
                        px-3 py-1.5 text-sm font-medium rounded
                        ${isResolvingCall
                          ? 'bg-green-500 text-white cursor-wait'
                          : 'bg-red-500 text-white hover:bg-red-600 active:bg-red-700'}
                        transition-colors
                      `}
                    >
                      {isResolvingCall ? 'Atendido ✓' : 'Atender'}
                    </button>
                  </div>
                </section>
              )}

              {/* Ready rounds alert - Go to kitchen to pickup */}
              {hasReadyRounds && (
                <section className="bg-green-500/10 p-3 border border-green-500/30 animate-pulse">
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

              {/* Rounds detail */}
              {isLoading ? (
                <div className="flex justify-center py-8">
                  <div className="animate-spin w-8 h-8 border-2 border-orange-500 border-t-transparent rounded-full" />
                </div>
              ) : error ? (
                <div className="bg-red-500/10 p-3 border border-red-500/30">
                  <p className="text-red-400 text-center text-sm">{error}</p>
                  <Button
                    variant="secondary"
                    size="sm"
                    className="w-full mt-2"
                    onClick={loadSessionDetail}
                  >
                    Reintentar
                  </Button>
                </div>
              ) : sessionDetail && sessionDetail.rounds.length > 0 ? (
                <section>
                  <h3 className="text-sm font-semibold text-gray-700 mb-2">
                    Rondas ({sessionDetail.rounds.length})
                  </h3>

                  {/* Round filter tabs */}
                  <div className="flex gap-1 overflow-x-auto pb-2 mb-2 scrollbar-hide">
                    {ROUND_FILTER_OPTIONS.map((option) => {
                      const isActive = roundFilter === option.value
                      return (
                        <button
                          key={option.value}
                          onClick={() => setRoundFilter(option.value)}
                          className={`flex-shrink-0 px-2 py-1 text-xs font-medium transition-colors ${
                            isActive
                              ? 'bg-orange-500 text-white'
                              : 'bg-gray-200 text-gray-600 hover:bg-gray-300'
                          }`}
                        >
                          {option.label}
                        </button>
                      )
                    })}
                  </div>

                  <div className="space-y-3">
                    {filteredRounds.length === 0 ? (
                      <p className="text-gray-400 text-center py-4 text-sm">
                        No hay rondas con este filtro
                      </p>
                    ) : filteredRounds.map((round) => (
                      <div
                        key={round.id}
                        className="bg-gray-50 p-3 border border-gray-200"
                      >
                        {/* Round header */}
                        <div className="flex items-center justify-between mb-2">
                          <div className="flex items-center gap-2">
                            <span className="text-gray-900 font-medium text-sm">
                              Ronda {round.round_number}
                            </span>
                            <RoundStatusBadge status={round.status} size="sm" />
                          </div>
                          <span className="text-gray-500 text-xs">
                            {round.submitted_at ? formatTime(round.submitted_at) : ''}
                          </span>
                        </div>

                        {/* Round items - sorted by category */}
                        <div className="space-y-1 mb-2">
                          {[...round.items].sort((a, b) => getCategoryOrder(a.category_name) - getCategoryOrder(b.category_name)).map((item) => (
                            <div key={item.id} className="text-xs group">
                              <div className="flex items-center justify-between whitespace-nowrap">
                                <span className="text-gray-900 flex items-center gap-1">
                                  {/* Delete button - only for PENDING or CONFIRMED rounds */}
                                  {canDeleteItems(round) && (
                                    <button
                                      onClick={() => promptDeleteItem(round.id, item)}
                                      disabled={deletingItemId === item.id}
                                      className={`
                                        w-5 h-5 flex items-center justify-center
                                        text-red-400 hover:text-red-600 hover:bg-red-50
                                        transition-colors rounded
                                        ${deletingItemId === item.id ? 'opacity-50 cursor-wait' : ''}
                                      `}
                                      title="Eliminar item"
                                      aria-label={`Eliminar ${item.product_name}`}
                                    >
                                      <svg className="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                                        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16" />
                                      </svg>
                                    </button>
                                  )}
                                  {item.qty}x {item.product_name}
                                  {item.diner_name && (
                                    <span
                                      className="ml-2 px-1.5 py-0.5 rounded"
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
                                </span>
                                <span className="text-gray-500 ml-4">
                                  {formatPrice(item.unit_price_cents * item.qty)}
                                </span>
                              </div>
                              {item.notes && (
                                <p className="text-gray-400 text-xs pl-4 whitespace-normal">
                                  Nota: {item.notes}
                                </p>
                              )}
                            </div>
                          ))}
                        </div>

                        {/* Round footer */}
                        <div className="flex items-center justify-between pt-2 border-t border-gray-200">
                          <span className="text-gray-500 text-xs">
                            Subtotal: {formatPrice(getRoundSubtotal(round))}
                          </span>
                          <div className="flex gap-2">
                            {/* Confirm button for PENDING rounds - waiter verifies at table */}
                            {round.status === 'PENDING' && (
                              <Button
                                variant="primary"
                                size="sm"
                                onClick={() => handleConfirmRound(round.id)}
                                disabled={isConfirmingRound === round.id}
                              >
                                {isConfirmingRound === round.id ? 'Confirmando...' : 'Confirmar Pedido'}
                              </Button>
                            )}
                            {/* Served button for READY rounds */}
                            {round.status === 'READY' && (
                              <Button
                                variant="primary"
                                size="sm"
                                onClick={() => promptMarkServed(round.id, round.round_number)}
                              >
                                Servido
                              </Button>
                            )}
                          </div>
                        </div>
                      </div>
                    ))}
                  </div>
                </section>
              ) : sessionDetail ? (
                <p className="text-gray-400 text-center py-4 text-sm">
                  No hay rondas en esta sesion
                </p>
              ) : null}

              {/* Diners */}
              {sessionDetail && sessionDetail.diners.length > 0 && (
                <section>
                  <h3 className="text-sm font-semibold text-gray-700 mb-2">
                    Comensales ({sessionDetail.diners.length})
                  </h3>
                  <div className="flex flex-wrap gap-1">
                    {sessionDetail.diners.map((diner) => (
                      <span
                        key={diner.id}
                        className="inline-flex items-center gap-1 px-2 py-1 rounded-full text-xs"
                        style={{
                          backgroundColor: `${diner.color}22`,
                          color: diner.color,
                        }}
                      >
                        <span
                          className="w-1.5 h-1.5 rounded-full"
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
                <section className="bg-purple-500/10 p-3 border border-purple-500/30">
                  <div className="flex items-center justify-between">
                    <span className="text-purple-600 text-sm font-medium">
                      Cuenta: {table.check_status}
                    </span>
                    {sessionDetail && (
                      <span className="text-gray-900 font-bold">
                        {formatPrice(sessionDetail.total_cents)}
                      </span>
                    )}
                  </div>
                </section>
              )}
            </>
          ) : (
            <div className="flex flex-col items-center justify-center py-8">
              <p className="text-gray-500">Sin sesion activa</p>
              <p className="text-gray-400 text-sm mt-1">
                La mesa esta disponible
              </p>
            </div>
          )}
        </div>

        {/* Footer */}
        <div className="p-4 border-t border-gray-200">
          <Button
            variant="secondary"
            className="w-full"
            onClick={onClose}
          >
            Cerrar
          </Button>
        </div>
      </div>

      {/* Confirmation dialog - Mark as served */}
      <ConfirmDialog
        isOpen={confirmRoundId !== null}
        title="Marcar como servido"
        message={`Confirmar que la ronda ${confirmRoundNumber} fue entregada a la mesa?`}
        confirmLabel="Confirmar"
        cancelLabel="Cancelar"
        onConfirm={handleMarkServed}
        onCancel={cancelConfirm}
        isLoading={isMarkingServed}
      />

      {/* Confirmation dialog - Delete item */}
      <ConfirmDialog
        isOpen={deleteConfirm !== null}
        title="Eliminar item"
        message={deleteConfirm ? `¿Eliminar ${deleteConfirm.item.qty}x ${deleteConfirm.item.product_name} de la ronda?` : ''}
        confirmLabel="Eliminar"
        cancelLabel="Cancelar"
        onConfirm={handleDeleteItem}
        onCancel={cancelDeleteConfirm}
        isLoading={deletingItemId !== null}
        variant="danger"
      />
    </div>
  )
}
