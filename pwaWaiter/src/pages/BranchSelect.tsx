import { useEffect } from 'react'
import { useAuthStore, selectUser, selectAvailableBranches } from '../stores/authStore'
import { Button } from '../components/Button'

export function BranchSelectPage() {
  const user = useAuthStore(selectUser)
  const availableBranches = useAuthStore(selectAvailableBranches)
  const selectBranch = useAuthStore((s) => s.selectBranch)
  const fetchBranchNames = useAuthStore((s) => s.fetchBranchNames)
  const logout = useAuthStore((s) => s.logout)

  // Fetch branch names on mount
  useEffect(() => {
    fetchBranchNames()
  }, [fetchBranchNames])

  return (
    <div className="min-h-screen flex items-center justify-center bg-[#0a0a0a] px-4">
      <div className="w-full max-w-md">
        {/* Header */}
        <div className="text-center mb-8">
          <h1 className="text-3xl font-bold text-white mb-2">
            Hola, {user?.email.split('@')[0]}
          </h1>
          <p className="text-neutral-400">Selecciona tu sucursal</p>
        </div>

        {/* Branch selection */}
        <div className="bg-neutral-900 rounded-2xl p-6 border border-neutral-800">
          <div className="space-y-3">
            {availableBranches.map((branch) => (
              <button
                key={branch.id}
                onClick={() => selectBranch(branch.id, branch.name)}
                className="
                  w-full p-4 rounded-xl
                  bg-neutral-800 hover:bg-neutral-700
                  border border-neutral-700 hover:border-orange-500
                  text-left transition-all
                  focus:outline-none focus:ring-2 focus:ring-orange-500
                "
              >
                <span className="text-lg font-medium text-white">
                  {branch.name}
                </span>
              </button>
            ))}
          </div>

          {availableBranches.length === 0 && (
            <div className="text-center py-8">
              <p className="text-neutral-400">
                Cargando sucursales...
              </p>
            </div>
          )}
        </div>

        {/* Logout button */}
        <div className="mt-6 text-center">
          <Button variant="ghost" onClick={logout}>
            Cerrar sesion
          </Button>
        </div>
      </div>
    </div>
  )
}
