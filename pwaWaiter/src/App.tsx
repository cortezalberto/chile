import { useEffect, useState } from 'react'
import {
  useAuthStore,
  selectIsAuthenticated,
  selectSelectedBranchId,
  selectUserBranchIds,
} from './stores/authStore'
import { LoginPage } from './pages/Login'
import { BranchSelectPage } from './pages/BranchSelect'
import { MainPage } from './pages/MainPage'
import { OfflineBanner } from './components/OfflineBanner'
import { PWAManager } from './components/PWAManager'

export function App() {
  const isAuthenticated = useAuthStore(selectIsAuthenticated)
  const selectedBranchId = useAuthStore(selectSelectedBranchId)
  const branchIds = useAuthStore(selectUserBranchIds)
  const checkAuth = useAuthStore((s) => s.checkAuth)

  const [isCheckingAuth, setIsCheckingAuth] = useState(true)

  // Check auth on mount
  useEffect(() => {
    checkAuth().finally(() => setIsCheckingAuth(false))
  }, [checkAuth])

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
    // Not authenticated -> login
    if (!isAuthenticated) {
      return <LoginPage />
    }

    // Authenticated but no branch selected and multiple branches -> branch select
    if (!selectedBranchId && branchIds.length > 1) {
      return <BranchSelectPage />
    }

    // Authenticated with branch -> Main page with Comensales/Autogestión tabs
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
