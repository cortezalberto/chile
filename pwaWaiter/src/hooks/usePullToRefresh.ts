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

// WAITER-HOOK-MED-02: Status messages for aria-live announcements
type RefreshStatus = 'idle' | 'pulling' | 'ready' | 'refreshing' | 'done'
const STATUS_MESSAGES: Record<RefreshStatus, string> = {
  idle: '',
  pulling: 'Desliza hacia abajo para actualizar',
  ready: 'Suelta para actualizar',
  refreshing: 'Actualizando...',
  done: 'Actualizacion completada',
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

  // WAITER-HOOK-MED-02: Track status for aria-live announcements
  const [status, setStatus] = useState<RefreshStatus>('idle')

  const touchStartY = useRef(0)
  const containerRef = useRef<HTMLDivElement>(null)

  // WAITER-HOOK-MED-03: Use refs to avoid stale closures in callbacks
  const onRefreshRef = useRef(onRefresh)
  const thresholdRef = useRef(threshold)
  const resistanceRef = useRef(resistance)

  // Keep refs updated with latest values
  useEffect(() => {
    onRefreshRef.current = onRefresh
    thresholdRef.current = threshold
    resistanceRef.current = resistance
  }, [onRefresh, threshold, resistance])

  const handleTouchStart = useCallback((e: TouchEvent) => {
    // Only enable pull-to-refresh at top of scroll
    const container = containerRef.current
    if (!container || container.scrollTop > 0) return

    touchStartY.current = e.touches[0].clientY
    setState((s) => ({ ...s, isPulling: true }))
    setStatus('pulling')
  }, [])

  // WAITER-HOOK-MED-03: Using refs to avoid stale closures
  const handleTouchMove = useCallback(
    (e: TouchEvent) => {
      setState((currentState) => {
        if (!currentState.isPulling || currentState.isRefreshing) return currentState

        const container = containerRef.current
        if (!container || container.scrollTop > 0) {
          setStatus('idle')
          return { ...currentState, isPulling: false, pullDistance: 0 }
        }

        const touchY = e.touches[0].clientY
        const diff = touchY - touchStartY.current

        // Only allow pulling down
        if (diff <= 0) {
          return { ...currentState, pullDistance: 0 }
        }

        // Apply resistance to make pull feel natural (using ref for latest value)
        const currentThreshold = thresholdRef.current
        const currentResistance = resistanceRef.current
        const pullDistance = Math.min(diff / currentResistance, currentThreshold * 1.5)

        // WAITER-HOOK-MED-02: Update status for accessibility announcement
        setStatus(pullDistance >= currentThreshold ? 'ready' : 'pulling')

        // Prevent default scrolling when pulling
        if (pullDistance > 0) {
          e.preventDefault()
        }

        return { ...currentState, pullDistance }
      })
    },
    [] // WAITER-HOOK-MED-03: Empty deps - using refs for latest values
  )

  // WAITER-HOOK-MED-03: Using refs to avoid stale closures
  const handleTouchEnd = useCallback(async () => {
    // Get current state synchronously to avoid stale closure
    let shouldRefresh = false
    let currentThreshold = thresholdRef.current

    setState((currentState) => {
      if (!currentState.isPulling) return currentState

      if (currentState.pullDistance >= currentThreshold && !currentState.isRefreshing) {
        shouldRefresh = true
        return { ...currentState, isRefreshing: true, pullDistance: currentThreshold }
      } else {
        setStatus('idle')
        return { isPulling: false, pullDistance: 0, isRefreshing: false }
      }
    })

    if (shouldRefresh) {
      setStatus('refreshing')
      try {
        await onRefreshRef.current()
      } finally {
        setStatus('done')
        setState({
          isPulling: false,
          pullDistance: 0,
          isRefreshing: false,
        })
        // Reset status after brief delay to allow screen readers to announce
        setTimeout(() => setStatus('idle'), 1000)
      }
    }
  }, []) // WAITER-HOOK-MED-03: Empty deps - using refs for latest values

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
    // WAITER-HOOK-MED-02: Accessibility props for aria-live region
    a11yProps: {
      role: 'status' as const,
      'aria-live': 'polite' as const,
      'aria-atomic': true,
      children: STATUS_MESSAGES[status],
    },
    statusMessage: STATUS_MESSAGES[status],
  }
}
