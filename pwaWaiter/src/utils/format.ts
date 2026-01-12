/**
 * Format cents to currency string
 */
export function formatPrice(cents: number): string {
  return `$${(cents / 100).toFixed(2)}`
}

/**
 * Format date to relative time (e.g., "hace 5 min")
 */
export function formatRelativeTime(dateStr: string): string {
  const date = new Date(dateStr)
  const now = new Date()
  const diffMs = now.getTime() - date.getTime()
  const diffMins = Math.floor(diffMs / 60000)
  const diffHours = Math.floor(diffMs / 3600000)

  if (diffMins < 1) return 'ahora'
  if (diffMins < 60) return `hace ${diffMins} min`
  if (diffHours < 24) return `hace ${diffHours}h`

  return date.toLocaleDateString('es-AR', {
    day: '2-digit',
    month: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
  })
}

/**
 * Format date to time string (HH:MM)
 */
export function formatTime(dateStr: string): string {
  return new Date(dateStr).toLocaleTimeString('es-AR', {
    hour: '2-digit',
    minute: '2-digit',
  })
}

/**
 * Format table code for display
 */
export function formatTableCode(code: string): string {
  return code.toUpperCase()
}
