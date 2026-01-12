import { useAuthStore, selectUser, selectSelectedBranchId } from '../stores/authStore'
import { useTablesStore, selectWsConnected } from '../stores/tablesStore'
import { useRetryQueueStore, selectQueueLength } from '../stores/retryQueueStore'
import { Button } from './Button'

export function Header() {
  const user = useAuthStore(selectUser)
  const selectedBranchId = useAuthStore(selectSelectedBranchId)
  const logout = useAuthStore((s) => s.logout)
  const wsConnected = useTablesStore(selectWsConnected)
  // WAITER-HIGH-04 FIX: Show pending queue count
  const pendingCount = useRetryQueueStore(selectQueueLength)

  return (
    <header className="sticky top-0 z-50 bg-neutral-900/95 backdrop-blur border-b border-neutral-800">
      <div className="px-4 py-3 flex items-center justify-between">
        <div className="flex items-center gap-3">
          <h1 className="text-xl font-bold text-orange-500">Mozo</h1>
          {selectedBranchId && (
            <span className="text-sm text-neutral-400">
              Sucursal {selectedBranchId}
            </span>
          )}
        </div>

        <div className="flex items-center gap-4">
          {/* WAITER-HIGH-04 FIX: Pending operations indicator */}
          {pendingCount > 0 && (
            <div
              className="flex items-center gap-1.5 bg-yellow-500/20 text-yellow-400 px-2 py-1 rounded-full text-xs font-medium"
              title={`${pendingCount} operacion${pendingCount > 1 ? 'es' : ''} pendiente${pendingCount > 1 ? 's' : ''}`}
            >
              <svg
                className="w-3.5 h-3.5 animate-spin"
                fill="none"
                viewBox="0 0 24 24"
              >
                <circle
                  className="opacity-25"
                  cx="12"
                  cy="12"
                  r="10"
                  stroke="currentColor"
                  strokeWidth="4"
                />
                <path
                  className="opacity-75"
                  fill="currentColor"
                  d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"
                />
              </svg>
              <span>{pendingCount} pendiente{pendingCount > 1 ? 's' : ''}</span>
            </div>
          )}

          {/* Connection status indicator */}
          <div className="flex items-center gap-2">
            <span
              className={`w-2 h-2 rounded-full ${
                wsConnected ? 'bg-green-500' : 'bg-red-500'
              }`}
              title={wsConnected ? 'Conectado' : 'Desconectado'}
            />
            <span className="text-sm text-neutral-400 hidden sm:inline">
              {wsConnected ? 'En linea' : 'Sin conexion'}
            </span>
          </div>

          {/* User info */}
          {user && (
            <div className="flex items-center gap-3">
              <span className="text-sm text-neutral-300 hidden sm:inline">
                {user.email.split('@')[0]}
              </span>
              <Button variant="ghost" size="sm" onClick={logout}>
                Salir
              </Button>
            </div>
          )}
        </div>
      </div>
    </header>
  )
}
