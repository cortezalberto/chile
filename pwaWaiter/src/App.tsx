import { useEffect, useState } from 'react'
import {
  useAuthStore,
  selectIsAuthenticated,
  selectSelectedBranchId,
  selectUserBranchIds,
} from './stores/authStore'
import { useTablesStore, selectSelectedTableId } from './stores/tablesStore'
import { LoginPage } from './pages/Login'
import { BranchSelectPage } from './pages/BranchSelect'
import { TableGridPage } from './pages/TableGrid'
import { TableDetailPage } from './pages/TableDetail'
import { TakeOrderPage } from './pages/TakeOrder'
import { OfflineBanner } from './components/OfflineBanner'

// HU-WAITER-MESA: View modes for table management
type TableViewMode = 'detail' | 'order'

export function App() {
  const isAuthenticated = useAuthStore(selectIsAuthenticated)
  const selectedBranchId = useAuthStore(selectSelectedBranchId)
  const branchIds = useAuthStore(selectUserBranchIds)
  const checkAuth = useAuthStore((s) => s.checkAuth)
  const selectTable = useTablesStore((s) => s.selectTable)
  const selectedTableId = useTablesStore(selectSelectedTableId)

  const [isCheckingAuth, setIsCheckingAuth] = useState(true)
  // HU-WAITER-MESA: Track which view mode when table is selected
  const [tableViewMode, setTableViewMode] = useState<TableViewMode>('order')

  // Check auth on mount
  useEffect(() => {
    checkAuth().finally(() => setIsCheckingAuth(false))
  }, [checkAuth])

  // Show loading while checking auth
  if (isCheckingAuth) {
    return (
      <div className="min-h-screen bg-[#0a0a0a] flex items-center justify-center">
        <div className="text-center">
          <div className="animate-spin w-10 h-10 border-3 border-orange-500 border-t-transparent rounded-full mx-auto mb-4" />
          <p className="text-neutral-400">Cargando...</p>
        </div>
      </div>
    )
  }

  // HU-WAITER-MESA: Handle table selection - default to order taking view
  const handleTableSelect = (tableId: number, mode: TableViewMode = 'order') => {
    selectTable(tableId)
    setTableViewMode(mode)
  }

  // Handle back from table detail/order
  const handleBackToGrid = () => {
    selectTable(null)
    setTableViewMode('order')
  }

  // Derive view from state instead of using useEffect (React 19 best practice)
  const renderContent = () => {
    // Not authenticated -> login
    if (!isAuthenticated) {
      return <LoginPage />
    }

    // Authenticated but no branch selected and multiple branches -> branch select
    if (!selectedBranchId && branchIds.length > 1) {
      return <BranchSelectPage />
    }

    // Authenticated with branch, viewing table
    if (selectedTableId !== null) {
      // HU-WAITER-MESA: Show order page or detail page based on mode
      if (tableViewMode === 'order') {
        return <TakeOrderPage onBack={handleBackToGrid} />
      }
      return <TableDetailPage onBack={handleBackToGrid} />
    }

    // Authenticated with branch -> table grid
    return <TableGridPage onTableSelect={(tableId) => handleTableSelect(tableId, 'order')} />
  }

  return (
    <>
      <OfflineBanner />
      {renderContent()}
    </>
  )
}
