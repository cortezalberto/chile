import { TABLE_STATUS_CONFIG, ROUND_STATUS_CONFIG } from '../utils/constants'
import type { TableStatus, RoundStatus } from '../types'

interface TableStatusBadgeProps {
  status: TableStatus
  size?: 'sm' | 'md'
}

export function TableStatusBadge({ status, size = 'md' }: TableStatusBadgeProps) {
  const config = TABLE_STATUS_CONFIG[status]
  const sizeClasses = size === 'sm' ? 'px-2 py-0.5 text-xs' : 'px-3 py-1 text-sm'

  return (
    <span
      className={`inline-flex items-center font-medium ${config.color} text-white ${sizeClasses}`}
    >
      {config.label}
    </span>
  )
}

interface RoundStatusBadgeProps {
  status: RoundStatus
  size?: 'sm' | 'md'
}

export function RoundStatusBadge({ status, size = 'md' }: RoundStatusBadgeProps) {
  const config = ROUND_STATUS_CONFIG[status]
  const sizeClasses = size === 'sm' ? 'px-2 py-0.5 text-xs' : 'px-3 py-1 text-sm'

  return (
    <span
      className={`inline-flex items-center font-medium ${config.color} text-white ${sizeClasses}`}
    >
      {config.label}
    </span>
  )
}

interface CountBadgeProps {
  count: number
  variant?: 'orange' | 'red' | 'yellow' | 'green'
  pulse?: boolean
}

export function CountBadge({ count, variant = 'orange', pulse = false }: CountBadgeProps) {
  if (count <= 0) return null

  const variantClasses = {
    orange: 'bg-orange-500',
    red: 'bg-red-500',
    yellow: 'bg-yellow-500',
    green: 'bg-green-500',
  }

  return (
    <span
      // WAITER-COMP-HIGH-02 FIX: aria-live for dynamic count updates
      aria-live="polite"
      aria-atomic="true"
      className={`
        inline-flex items-center justify-center min-w-[1.25rem] h-5 px-1.5
        text-xs font-bold text-white
        ${variantClasses[variant]}
        ${pulse ? 'animate-pulse-dot' : ''}
      `}
    >
      {count > 99 ? '99+' : count}
    </span>
  )
}
