interface PullToRefreshIndicatorProps {
  pullDistance: number
  isRefreshing: boolean
  progress: number
  threshold?: number
  // WAITER-HOOK-MED-02: Accessibility status message
  statusMessage?: string
}

/**
 * PWAW-008: Visual indicator for pull-to-refresh gesture
 */
export function PullToRefreshIndicator({
  pullDistance,
  isRefreshing,
  progress,
  threshold = 80,
  statusMessage,
}: PullToRefreshIndicatorProps) {
  // WAITER-HOOK-MED-02: Always render aria-live region for screen readers
  // but visually show indicator only when pulling
  const showVisual = pullDistance > 0 || isRefreshing

  const rotation = Math.min(progress * 360, 360)
  const scale = Math.min(0.5 + progress * 0.5, 1)

  return (
    <>
      {/* WAITER-HOOK-MED-02: Hidden aria-live region for accessibility */}
      <div
        role="status"
        aria-live="polite"
        aria-atomic="true"
        className="sr-only"
      >
        {statusMessage}
      </div>

      {showVisual && (
        <div
          className="flex justify-center items-center transition-all duration-200 overflow-hidden"
          style={{
            height: Math.min(pullDistance, threshold),
            opacity: Math.min(progress * 1.5, 1),
          }}
          aria-hidden="true"
        >
          <div
            className={`w-8 h-8 rounded-full border-2 border-orange-500 border-t-transparent ${
              isRefreshing ? 'animate-spin' : ''
            }`}
            style={{
              transform: isRefreshing
                ? 'scale(1)'
                : `rotate(${rotation}deg) scale(${scale})`,
              transition: isRefreshing ? 'none' : 'transform 0.1s ease-out',
            }}
          />
        </div>
      )}
    </>
  )
}
