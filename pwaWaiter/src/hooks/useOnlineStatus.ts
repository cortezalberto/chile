import { useState, useEffect, useCallback } from 'react'

interface OnlineStatus {
  isOnline: boolean
  wasOffline: boolean
  lastOnlineAt: Date | null
}

/**
 * Hook to track online/offline status.
 * Provides real-time updates when connection changes.
 */
export function useOnlineStatus(): OnlineStatus {
  const [isOnline, setIsOnline] = useState(navigator.onLine)
  const [wasOffline, setWasOffline] = useState(false)
  const [lastOnlineAt, setLastOnlineAt] = useState<Date | null>(
    navigator.onLine ? new Date() : null
  )

  const handleOnline = useCallback(() => {
    setIsOnline(true)
    setLastOnlineAt(new Date())
    // Keep wasOffline true for a short period so UI can show "reconnected" message
    setTimeout(() => setWasOffline(false), 5000)
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
    }
  }, [handleOnline, handleOffline])

  return { isOnline, wasOffline, lastOnlineAt }
}
