import { useState, useEffect, useCallback, useRef } from 'react'

interface OnlineStatus {
  isOnline: boolean
  wasOffline: boolean
  lastOnlineAt: Date | null
}

/**
 * Hook to track online/offline status.
 * Provides real-time updates when connection changes.
 * WAITER-HOOK-MED-01: Fixed setTimeout cleanup on unmount
 */
export function useOnlineStatus(): OnlineStatus {
  const [isOnline, setIsOnline] = useState(navigator.onLine)
  const [wasOffline, setWasOffline] = useState(false)
  const [lastOnlineAt, setLastOnlineAt] = useState<Date | null>(
    navigator.onLine ? new Date() : null
  )
  // WAITER-HOOK-MED-01: Track timeout for cleanup
  const wasOfflineTimeoutRef = useRef<ReturnType<typeof setTimeout> | null>(null)

  const handleOnline = useCallback(() => {
    setIsOnline(true)
    setLastOnlineAt(new Date())
    // WAITER-HOOK-MED-01: Clear previous timeout before setting new one
    if (wasOfflineTimeoutRef.current) {
      clearTimeout(wasOfflineTimeoutRef.current)
    }
    // Keep wasOffline true for a short period so UI can show "reconnected" message
    wasOfflineTimeoutRef.current = setTimeout(() => {
      setWasOffline(false)
      wasOfflineTimeoutRef.current = null
    }, 5000)
  }, [])

  const handleOffline = useCallback(() => {
    setIsOnline(false)
    setWasOffline(true)
  }, [])

  useEffect(() => {
    window.addEventListener('online', handleOnline)
    window.addEventListener('offline', handleOffline)

    return () => {
      window.removeEventListener('online', handleOnline)
      window.removeEventListener('offline', handleOffline)
      // WAITER-HOOK-MED-01: Clear timeout on unmount
      if (wasOfflineTimeoutRef.current) {
        clearTimeout(wasOfflineTimeoutRef.current)
        wasOfflineTimeoutRef.current = null
      }
    }
  }, [handleOnline, handleOffline])

  return { isOnline, wasOffline, lastOnlineAt }
}
