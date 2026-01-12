import { useOnlineStatus } from '../hooks/useOnlineStatus'

// Inline SVG icons to avoid lucide-react dependency
function WifiIcon({ className }: { className?: string }) {
  return (
    <svg className={className} fill="none" viewBox="0 0 24 24" stroke="currentColor">
      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M8.111 16.404a5.5 5.5 0 017.778 0M12 20h.01m-7.08-7.071c3.904-3.905 10.236-3.905 14.141 0M1.394 9.393c5.857-5.857 15.355-5.857 21.213 0" />
    </svg>
  )
}

function WifiOffIcon({ className }: { className?: string }) {
  return (
    <svg className={className} fill="none" viewBox="0 0 24 24" stroke="currentColor">
      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M18.364 5.636a9 9 0 010 12.728m0 0l-2.829-2.829m2.829 2.829L21 21M15.536 8.464a5 5 0 010 7.072m0 0l-2.829-2.829m-4.243 2.829a4.978 4.978 0 01-1.414-2.83m-1.414 5.658a9 9 0 01-2.167-9.238m7.824 2.167a1 1 0 111.414 1.414m-1.414-1.414L3 3m8.293 8.293l1.414 1.414" />
    </svg>
  )
}

/**
 * Banner component that shows offline/reconnected status.
 * Appears at the top of the screen when connection changes.
 */
export function OfflineBanner() {
  const { isOnline, wasOffline } = useOnlineStatus()

  // Don't show anything if online and wasn't recently offline
  if (isOnline && !wasOffline) {
    return null
  }

  // Show reconnected message briefly
  if (isOnline && wasOffline) {
    return (
      <div className="fixed top-0 left-0 right-0 z-50 bg-green-600 text-white py-2 px-4 flex items-center justify-center gap-2 animate-slide-down">
        <WifiIcon className="w-4 h-4" />
        <span className="text-sm font-medium">Conexion restablecida</span>
      </div>
    )
  }

  // Show offline message
  return (
    <div className="fixed top-0 left-0 right-0 z-50 bg-red-600 text-white py-2 px-4 flex items-center justify-center gap-2">
      <WifiOffIcon className="w-4 h-4" />
      <span className="text-sm font-medium">Sin conexion - Modo offline</span>
    </div>
  )
}
