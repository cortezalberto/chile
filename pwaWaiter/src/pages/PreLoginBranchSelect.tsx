import { useEffect, useState } from 'react'
import { useAuthStore } from '../stores/authStore'
import { publicAPI, BranchPublicInfo } from '../services/api'
import { authLogger } from '../utils/logger'

export function PreLoginBranchSelectPage() {
  const setPreLoginBranchId = useAuthStore((s) => s.setPreLoginBranchId)

  const [branches, setBranches] = useState<BranchPublicInfo[]>([])
  const [isLoading, setIsLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  // Fetch branches on mount
  useEffect(() => {
    let isMounted = true

    publicAPI
      .getBranches()
      .then((data) => {
        if (isMounted) {
          setBranches(data)
          setIsLoading(false)
        }
      })
      .catch((err) => {
        if (isMounted) {
          authLogger.error('Failed to fetch branches', err)
          setError('Error al cargar sucursales. Intente nuevamente.')
          setIsLoading(false)
        }
      })

    return () => {
      isMounted = false
    }
  }, [])

  const handleBranchSelect = (branch: BranchPublicInfo) => {
    setPreLoginBranchId(branch.id, branch.name)
    authLogger.info('Pre-login branch selected', { branchId: branch.id, branchName: branch.name })
  }

  if (isLoading) {
    return (
      <div className="min-h-screen bg-white flex items-center justify-center">
        <div className="text-center">
          <div className="animate-spin w-10 h-10 border-3 border-orange-500 border-t-transparent rounded-full mx-auto mb-4" />
          <p className="text-gray-500">Cargando sucursales...</p>
        </div>
      </div>
    )
  }

  if (error) {
    return (
      <div className="min-h-screen bg-white flex items-center justify-center px-4">
        <div className="text-center">
          <p className="text-red-500 mb-4">{error}</p>
          <button
            onClick={() => window.location.reload()}
            className="px-4 py-2 bg-orange-500 text-white rounded-lg hover:bg-orange-600 transition-colors"
          >
            Reintentar
          </button>
        </div>
      </div>
    )
  }

  return (
    <div className="min-h-screen flex items-center justify-center bg-white px-4">
      <div className="w-full max-w-md">
        {/* Header */}
        <div className="text-center mb-8">
          <h1 className="text-3xl font-bold text-gray-900 mb-2">
            Buen Sabor
          </h1>
          <p className="text-gray-500">Selecciona tu sucursal para continuar</p>
        </div>

        {/* Branch selection */}
        <div className="bg-gray-50 p-6 border border-gray-200">
          <div className="space-y-3">
            {branches.map((branch) => (
              <button
                key={branch.id}
                onClick={() => handleBranchSelect(branch)}
                className="
                  w-full p-4
                  bg-white hover:bg-gray-50
                  border border-gray-200 hover:border-orange-500
                  text-left transition-all shadow-sm
                  focus:outline-none focus:ring-2 focus:ring-orange-500
                "
              >
                <span className="text-lg font-medium text-gray-900 block">
                  {branch.name}
                </span>
                {branch.address && (
                  <span className="text-sm text-gray-500 block mt-1">
                    {branch.address}
                  </span>
                )}
              </button>
            ))}
          </div>

          {branches.length === 0 && (
            <div className="text-center py-8">
              <p className="text-gray-500">
                No hay sucursales disponibles
              </p>
            </div>
          )}
        </div>
      </div>
    </div>
  )
}
