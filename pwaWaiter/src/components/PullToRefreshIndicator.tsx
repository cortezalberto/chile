interface PullToRefreshIndicatorProps {
  pullDistance: number
  isRefreshing: boolean
  progress: number
  threshold?: number
}

/**
 * PWAW-008: Visual indicator for pull-to-refresh gesture
 */
export function PullToRefreshIndicator({
  pullDistance,
  isRefreshing,
  progress,
  threshold = 80,
}: PullToRefreshIndicatorProps) {
  if (pullDistance === 0 && !isRefreshing) return null

  const rotation = Math.min(progress * 360, 360)
  const scale = Math.min(0.5 + progress * 0.5, 1)

  return (
    <div
      className="flex justify-center items-center transition-all duration-200 overflow-hidden"
      style={{
        height: Math.min(pullDistance, threshold),
        opacity: Math.min(progress * 1.5, 1),
      }}
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
  )
}
