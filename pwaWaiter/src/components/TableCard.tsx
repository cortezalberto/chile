import { TABLE_STATUS_CONFIG, ORDER_STATUS_CONFIG } from '../utils/constants'
import { formatTableCode } from '../utils/format'
import { TableStatusBadge, CountBadge } from './StatusBadge'
import type { TableCard as TableCardType } from '../types'

interface TableCardProps {
  table: TableCardType
  onClick: () => void
}

/**
 * Get the animation class based on table state (priority-based).
 * Priority order (highest to lowest):
 * 1. hasServiceCall → red blink (waiter call)
 * 2. orderStatus === 'ready_with_kitchen' → orange blink
 * 3. statusChanged → blue blink
 * 4. hasNewOrder → yellow pulse
 * 5. check_status === 'REQUESTED' → purple pulse
 */
function getAnimationClass(table: TableCardType): string {
  // Priority 1: Service call (highest urgency)
  if (table.hasServiceCall) {
    return 'animate-service-call-blink'
  }

  // Priority 2: Ready + kitchen items
  if (table.orderStatus === 'ready_with_kitchen') {
    return 'animate-ready-kitchen-blink'
  }

  // Priority 3: Status changed (brief blink)
  if (table.statusChanged) {
    return 'animate-status-blink'
  }

  // Priority 4: New order
  if (table.hasNewOrder) {
    return 'animate-pulse-warning'
  }

  // Priority 5: Check requested
  if (table.check_status === 'REQUESTED') {
    return 'animate-pulse-urgent'
  }

  return ''
}

export function TableCard({ table, onClick }: TableCardProps) {
  const statusConfig = TABLE_STATUS_CONFIG[table.status]
  const orderStatusConfig = table.orderStatus
    ? ORDER_STATUS_CONFIG[table.orderStatus]
    : ORDER_STATUS_CONFIG.none

  // Use TableCard fields directly
  const hasOpenRounds = table.open_rounds > 0
  const hasPendingCalls = table.pending_calls > 0
  const hasCheckRequested = table.status === 'PAYING' || table.check_status === 'REQUESTED'
  const hasActiveSession = table.session_id !== null

  // Get animation class based on priority
  const animationClass = getAnimationClass(table)

  // WAITER-COMP-HIGH-01 FIX: Build aria-label describing table status
  const statusLabel = statusConfig.label
  const orderStatusLabel = orderStatusConfig.label
  const urgencyInfo = hasPendingCalls || table.hasServiceCall ? ', requiere atención urgente' : ''
  const sessionInfo = hasActiveSession
    ? `, ${table.open_rounds} ronda${table.open_rounds !== 1 ? 's' : ''}, ${table.pending_calls} llamado${table.pending_calls !== 1 ? 's' : ''}`
    : ', sin sesión activa'
  const orderInfo = orderStatusLabel ? `, pedido: ${orderStatusLabel}` : ''
  const ariaLabel = `Mesa ${formatTableCode(table.code)}, estado: ${statusLabel}${orderInfo}${sessionInfo}${urgencyInfo}`

  return (
    <button
      onClick={onClick}
      aria-label={ariaLabel}
      className={`
        relative w-full p-4 border-2 text-left
        bg-white hover:bg-gray-50 shadow-sm
        transition-all duration-200
        focus:outline-none focus:ring-2 focus:ring-orange-500
        ${statusConfig.borderColor}
        ${animationClass}
      `}
    >
      {/* Table number and order status badge */}
      <div className="flex items-start justify-between mb-3">
        <div className="flex flex-col">
          <span className="text-2xl font-bold text-gray-900">
            {formatTableCode(table.code)}
          </span>
          {/* Order status badge */}
          {orderStatusConfig.label && (
            <span
              className={`
                mt-1 px-2 py-0.5 text-xs font-bold
                ${orderStatusConfig.color} ${orderStatusConfig.textColor}
              `}
            >
              {orderStatusConfig.label}
            </span>
          )}
        </div>
        <TableStatusBadge status={table.status} size="sm" />
      </div>

      {/* Session info */}
      {hasActiveSession ? (
        <div className="space-y-2">
          {/* Summary counts */}
          <div className="flex items-center gap-3 text-sm">
            {table.open_rounds > 0 && (
              <span className="text-gray-500">
                {table.open_rounds} {table.open_rounds === 1 ? 'ronda' : 'rondas'}
              </span>
            )}
            {table.pending_calls > 0 && (
              <span className="text-red-500 font-medium">
                {table.pending_calls} llamado{table.pending_calls !== 1 ? 's' : ''}
              </span>
            )}
          </div>

          {/* Check status */}
          {table.check_status && (
            <div className="text-sm text-purple-600">
              Cuenta: {table.check_status}
            </div>
          )}
        </div>
      ) : (
        <div className="text-sm text-gray-400">Sin sesion activa</div>
      )}

      {/* Notification badges */}
      <div className="absolute top-2 right-2 flex gap-1">
        {hasOpenRounds && (
          <CountBadge count={table.open_rounds} variant="green" pulse />
        )}
        {hasPendingCalls && (
          <CountBadge count={table.pending_calls} variant="red" pulse />
        )}
        {hasCheckRequested && (
          <span className="px-2 py-0.5 text-xs font-medium bg-purple-500 text-white">
            Cuenta
          </span>
        )}
      </div>
    </button>
  )
}
