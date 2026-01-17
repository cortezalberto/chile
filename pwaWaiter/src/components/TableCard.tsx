import { TABLE_STATUS_CONFIG } from '../utils/constants'
import { formatTableCode } from '../utils/format'
import { TableStatusBadge, CountBadge } from './StatusBadge'
import type { TableCard as TableCardType } from '../types'

interface TableCardProps {
  table: TableCardType
  onClick: () => void
}

export function TableCard({ table, onClick }: TableCardProps) {
  const statusConfig = TABLE_STATUS_CONFIG[table.status]

  // Use TableCard fields directly
  const hasOpenRounds = table.open_rounds > 0
  const hasPendingCalls = table.pending_calls > 0
  const hasCheckRequested = table.status === 'PAYING' || table.check_status === 'REQUESTED'
  const hasActiveSession = table.session_id !== null

  // Determine if table needs urgent attention
  const isUrgent = hasPendingCalls || hasCheckRequested

  // WAITER-COMP-HIGH-01 FIX: Build aria-label describing table status
  const statusLabel = statusConfig.label
  const urgencyInfo = isUrgent ? ', requiere atención urgente' : ''
  const sessionInfo = hasActiveSession
    ? `, ${table.open_rounds} ronda${table.open_rounds !== 1 ? 's' : ''} pendiente${table.open_rounds !== 1 ? 's' : ''}, ${table.pending_calls} llamado${table.pending_calls !== 1 ? 's' : ''}`
    : ', sin sesión activa'
  const ariaLabel = `Mesa ${formatTableCode(table.code)}, estado: ${statusLabel}${sessionInfo}${urgencyInfo}`

  return (
    <button
      onClick={onClick}
      aria-label={ariaLabel}
      className={`
        relative w-full p-4 rounded-xl border-2 text-left
        bg-neutral-900 hover:bg-neutral-800
        transition-all duration-200
        focus:outline-none focus:ring-2 focus:ring-orange-500
        ${statusConfig.borderColor}
        ${isUrgent ? 'animate-glow' : ''}
      `}
    >
      {/* Table number */}
      <div className="flex items-start justify-between mb-3">
        <span className="text-2xl font-bold text-white">
          {formatTableCode(table.code)}
        </span>
        <TableStatusBadge status={table.status} size="sm" />
      </div>

      {/* Session info */}
      {hasActiveSession ? (
        <div className="space-y-2">
          {/* Summary counts */}
          <div className="flex items-center gap-3 text-sm">
            {table.open_rounds > 0 && (
              <span className="text-neutral-400">
                {table.open_rounds} {table.open_rounds === 1 ? 'ronda' : 'rondas'} pendiente{table.open_rounds !== 1 ? 's' : ''}
              </span>
            )}
            {table.pending_calls > 0 && (
              <span className="text-red-400">
                {table.pending_calls} llamado{table.pending_calls !== 1 ? 's' : ''}
              </span>
            )}
          </div>

          {/* Check status */}
          {table.check_status && (
            <div className="text-sm text-purple-400">
              Cuenta: {table.check_status}
            </div>
          )}
        </div>
      ) : (
        <div className="text-sm text-neutral-500">Sin sesion activa</div>
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
          <span className="px-2 py-0.5 text-xs font-medium rounded-full bg-purple-500 text-white">
            Cuenta
          </span>
        )}
      </div>
    </button>
  )
}
