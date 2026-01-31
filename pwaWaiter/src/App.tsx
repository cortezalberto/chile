import { useEffect, useState } from 'react'
import {
  useAuthStore,
  selectIsAuthenticated,
  selectPreLoginBranchId,
  selectAssignmentVerified,
  selectAuthError,
} from './stores/authStore'
import { LoginPage } from './pages/Login'
import { PreLoginBranchSelectPage } from './pages/PreLoginBranchSelect'
import { MainPage } from './pages/MainPage'
import { OfflineBanner } from './components/OfflineBanner'
import { PWAManager } from './components/PWAManager'

export function App() {
  const isAuthenticated = useAuthStore(selectIsAuthenticated)
  const preLoginBranchId = useAuthStore(selectPreLoginBranchId)
  const assignmentVerified = useAuthStore(selectAssignmentVerified)
  const authError = useAuthStore(selectAuthError)
  const checkAuth = useAuthStore((s) => s.checkAuth)
  const verifyBranchAssignment = useAuthStore((s) => s.verifyBranchAssignment)
  const logout = useAuthStore((s) => s.logout)

  const [isCheckingAuth, setIsCheckingAuth] = useState(true)
  const [isVerifyingAssignment, setIsVerifyingAssignment] = useState(false)

  // Check auth on mount
  useEffect(() => {
    checkAuth().finally(() => setIsCheckingAuth(false))
  }, [checkAuth])

  // When authenticated but not yet verified, verify branch assignment
  useEffect(() => {
    if (isAuthenticated && preLoginBranchId && !assignmentVerified && !isVerifyingAssignment) {
      setIsVerifyingAssignment(true)
      verifyBranchAssignment().finally(() => setIsVerifyingAssignment(false))
    }
  }, [isAuthenticated, preLoginBranchId, assignmentVerified, isVerifyingAssignment, verifyBranchAssignment])

  // Show loading while checking auth
  if (isCheckingAuth) {
    return (
      <div className="min-h-screen bg-white flex items-center justify-center">
        <div className="text-center">
          <div className="animate-spin w-10 h-10 border-3 border-orange-500 border-t-transparent rounded-full mx-auto mb-4" />
          <p className="text-gray-500">Cargando...</p>
        </div>
      </div>
    )
  }

  // Derive view from state (React 19 best practice)
  const renderContent = () => {
    // Step 1: No branch selected -> Pre-login branch selection
    if (!preLoginBranchId && !isAuthenticated) {
      return <PreLoginBranchSelectPage />
    }

    // Step 2: Branch selected but not authenticated -> Login
    if (!isAuthenticated) {
      return <LoginPage />
    }

    // Step 3: Authenticated but verifying assignment
    if (isVerifyingAssignment) {
      return (
        <div className="min-h-screen bg-white flex items-center justify-center">
          <div className="text-center">
            <div className="animate-spin w-10 h-10 border-3 border-orange-500 border-t-transparent rounded-full mx-auto mb-4" />
            <p className="text-gray-500">Verificando asignacion...</p>
          </div>
        </div>
      )
    }

    // Step 4: Authenticated but assignment failed -> Show error and allow retry
    if (!assignmentVerified) {
      return (
        <div className="min-h-screen bg-white flex items-center justify-center px-4">
          <div className="w-full max-w-md text-center">
            <div className="bg-red-50 border border-red-200 rounded-lg p-6 mb-6">
              <h2 className="text-xl font-bold text-red-700 mb-2">
                Acceso Denegado
              </h2>
              <p className="text-red-600">
                {authError || 'No estas asignado a esta sucursal hoy'}
              </p>
            </div>
            <div className="space-y-3">
              <button
                onClick={() => {
                  // Clear pre-login branch to allow re-selection
                  logout()
                }}
                className="w-full px-4 py-3 bg-orange-500 text-white rounded-lg hover:bg-orange-600 transition-colors font-medium"
              >
                Elegir otra sucursal
              </button>
            </div>
          </div>
        </div>
      )
    }

    // Step 5: Authenticated and verified -> Main page
    return <MainPage />
  }

  return (
    <>
      <OfflineBanner />
      <PWAManager />
      {renderContent()}
    </>
  )
}
