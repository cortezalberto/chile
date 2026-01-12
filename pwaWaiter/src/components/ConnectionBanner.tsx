/**
 * PWAW-A002: Prominent connection status banner
 *
 * Shows a full-width banner when WebSocket is disconnected
 * to ensure waiter notices lost notifications.
 */

interface ConnectionBannerProps {
  isConnected: boolean
}

export function ConnectionBanner({ isConnected }: ConnectionBannerProps) {
  if (isConnected) return null

  const handleReconnect = () => {
    // Trigger reconnect by getting current token and reconnecting
    // The actual token is managed by authStore
    window.location.reload()
  }

  return (
    <div className="fixed top-16 left-0 right-0 bg-red-600 text-white p-3 z-50 flex items-center justify-center gap-4 shadow-lg animate-pulse">
      <svg
        className="w-5 h-5"
        fill="none"
        stroke="currentColor"
        viewBox="0 0 24 24"
      >
        <path
          strokeLinecap="round"
          strokeLinejoin="round"
          strokeWidth={2}
          d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z"
        />
      </svg>
      <span className="font-medium">
        Sin conexión - No recibirás notificaciones
      </span>
      <button
        onClick={handleReconnect}
        className="bg-white text-red-600 px-3 py-1 rounded text-sm font-medium hover:bg-red-100 transition-colors"
      >
        Reconectar
      </button>
    </div>
  )
}
