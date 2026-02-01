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
      // Format today's date in Spanish
      const today = new Date()
      const dateStr = today.toLocaleDateString('es-AR', {
        weekday: 'long',
        day: 'numeric',
        month: 'long',
      })

      return (
        <div className="min-h-screen bg-white flex items-center justify-center px-4">
          <div className="w-full max-w-md text-center">
            {/* Error icon */}
            <div className="w-16 h-16 bg-red-100 rounded-full flex items-center justify-center mx-auto mb-4">
              <svg className="w-8 h-8 text-red-500" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z" />
              </svg>
            </div>

            <div className="bg-red-50 border border-red-200 rounded-lg p-6 mb-6">
              <h2 className="text-xl font-bold text-red-700 mb-3">
                Sin Asignación para Hoy
              </h2>
              <p className="text-red-600 mb-4">
                {authError || 'No estás asignado a esta sucursal hoy'}
              </p>
              <p className="text-sm text-gray-600 mb-2">
                <strong>Fecha:</strong> {dateStr}
              </p>
              <div className="mt-4 p-3 bg-amber-50 border border-amber-200 rounded-lg">
                <p className="text-sm text-amber-800">
                  <strong>¿Necesitas trabajar hoy?</strong>
                  <br />
                  Contacta al Manager o Admin para que te asigne a un sector en esta sucursal.
                </p>
              </div>
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
