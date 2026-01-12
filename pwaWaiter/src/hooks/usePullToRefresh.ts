import { useState, useRef, useCallback, useEffect } from 'react'
import { UI_CONFIG } from '../utils/constants'

interface PullToRefreshOptions {
  onRefresh: () => Promise<void>
  // PWAW-L003: Using UI_CONFIG default
  threshold?: number // Distance to pull before refresh triggers
  resistance?: number // Pull resistance factor (default: 2.5)
}

interface PullToRefreshState {
  isPulling: boolean
  pullDistance: number
  isRefreshing: boolean
}

/**
 * PWAW-008: Hook for implementing pull-to-refresh gesture
 * Returns props to spread on container and state for UI feedback
 */
export function usePullToRefresh({
  onRefresh,
  threshold = UI_CONFIG.PULL_TO_REFRESH_THRESHOLD, // PWAW-L003
  resistance = 2.5,
}: PullToRefreshOptions) {
  const [state, setState] = useState<PullToRefreshState>({
    isPulling: false,
    pullDistance: 0,
    isRefreshing: false,
  })

  const touchStartY = useRef(0)
  const containerRef = useRef<HTMLDivElement>(null)

  const handleTouchStart = useCallback((e: TouchEvent) => {
    // Only enable pull-to-refresh at top of scroll
    const container = containerRef.current
    if (!container || container.scrollTop > 0) return

    touchStartY.current = e.touches[0].clientY
    setState((s) => ({ ...s, isPulling: true }))
  }, [])

  const handleTouchMove = useCallback(
    (e: TouchEvent) => {
      if (!state.isPulling || state.isRefreshing) return

      const container = containerRef.current
      if (!container || container.scrollTop > 0) {
        setState((s) => ({ ...s, isPulling: false, pullDistance: 0 }))
        return
      }

      const touchY = e.touches[0].clientY
      const diff = touchY - touchStartY.current

      // Only allow pulling down
      if (diff <= 0) {
        setState((s) => ({ ...s, pullDistance: 0 }))
        return
      }

      // Apply resistance to make pull feel natural
      const pullDistance = Math.min(diff / resistance, threshold * 1.5)
      setState((s) => ({ ...s, pullDistance }))

      // Prevent default scrolling when pulling
      if (pullDistance > 0) {
        e.preventDefault()
      }
    },
    [state.isPulling, state.isRefreshing, resistance, threshold]
  )

  const handleTouchEnd = useCallback(async () => {
    if (!state.isPulling) return

    if (state.pullDistance >= threshold && !state.isRefreshing) {
      setState((s) => ({ ...s, isRefreshing: true, pullDistance: threshold }))

      try {
        await onRefresh()
      } finally {
        setState({
          isPulling: false,
          pullDistance: 0,
          isRefreshing: false,
        })
      }
    } else {
      setState({
        isPulling: false,
        pullDistance: 0,
        isRefreshing: false,
      })
    }
  }, [state.isPulling, state.pullDistance, state.isRefreshing, threshold, onRefresh])

  // Attach event listeners
  useEffect(() => {
    const container = containerRef.current
    if (!container) return

    container.addEventListener('touchstart', handleTouchStart, { passive: true })
    container.addEventListener('touchmove', handleTouchMove, { passive: false })
    container.addEventListener('touchend', handleTouchEnd)

    return () => {
      container.removeEventListener('touchstart', handleTouchStart)
      container.removeEventListener('touchmove', handleTouchMove)
      container.removeEventListener('touchend', handleTouchEnd)
    }
  }, [handleTouchStart, handleTouchMove, handleTouchEnd])

  return {
    containerRef,
    ...state,
    // Progress from 0 to 1 for UI feedback
    progress: Math.min(state.pullDistance / threshold, 1),
  }
}
