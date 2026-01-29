/**
 * HU-WAITER-MESA: TakeOrder Page
 *
 * This page allows waiters to manage the complete table flow:
 * - Activate a free table (CA-01)
 * - Browse menu and add items to cart (CA-02)
 * - Submit rounds to kitchen (CA-03)
 * - Request check (CA-05)
 * - Register manual payments - NO Mercado Pago (CA-06)
 * - Close table (CA-07)
 *
 * CRITICAL: This flow does NOT use any digital payment provider.
 * All payments are registered manually by the waiter after
 * physically receiving cash, card swipe, or transfer confirmation.
 */

import { useState, useEffect, useCallback, useMemo } from 'react'
import { useAuthStore, selectSelectedBranchId } from '../stores/authStore'
import {
  useTablesStore,
  selectSelectedTable,
  selectActiveSession,
} from '../stores/tablesStore'
import {
  branchAPI,
  menuAPI,
  type MenuOutput,
  type MenuProduct,
  type WaiterRoundItem,
  type ManualPaymentMethod,
} from '../services/api'
import { Header } from '../components/Header'
import { Button } from '../components/Button'
import { ConfirmDialog } from '../components/ConfirmDialog'
import { formatPrice } from '../utils/format'

interface TakeOrderPageProps {
  onBack: () => void
}

// Cart item with quantity
interface CartItem {
  product: MenuProduct
  qty: number
  notes: string
}

// Manual payment method labels
const PAYMENT_METHOD_LABELS: Record<ManualPaymentMethod, string> = {
  CASH: 'Efectivo',
  CARD_PHYSICAL: 'Tarjeta (POS)',
  TRANSFER_EXTERNAL: 'Transferencia',
  OTHER_MANUAL: 'Otro',
}

export function TakeOrderPage({ onBack }: TakeOrderPageProps) {
  const branchId = useAuthStore(selectSelectedBranchId)
  const table = useTablesStore(selectSelectedTable)
  const activeSession = useTablesStore(selectActiveSession)

  // Store actions
  const activateTable = useTablesStore((s) => s.activateTable)
  const submitRound = useTablesStore((s) => s.submitRound)
  const requestCheck = useTablesStore((s) => s.requestCheck)
  const registerManualPayment = useTablesStore((s) => s.registerManualPayment)
  const closeTableSession = useTablesStore((s) => s.closeTableSession)
  const fetchSessionSummary = useTablesStore((s) => s.fetchSessionSummary)
  const clearActiveSession = useTablesStore((s) => s.clearActiveSession)

  // Menu state
  const [menu, setMenu] = useState<MenuOutput | null>(null)
  const [isLoadingMenu, setIsLoadingMenu] = useState(true)
  const [menuError, setMenuError] = useState<string | null>(null)

  // Category/product navigation
  const [selectedCategoryId, setSelectedCategoryId] = useState<number | null>(null)

  // Cart state
  const [cart, setCart] = useState<CartItem[]>([])
  const [showCart, setShowCart] = useState(false)

  // Activation modal
  const [showActivateModal, setShowActivateModal] = useState(false)
  const [dinerCount, setDinerCount] = useState(2)
  const [isActivating, setIsActivating] = useState(false)

  // Payment modal state
  const [showPaymentModal, setShowPaymentModal] = useState(false)
  const [paymentMethod, setPaymentMethod] = useState<ManualPaymentMethod>('CASH')
  const [paymentAmount, setPaymentAmount] = useState('')
  const [paymentNotes, setPaymentNotes] = useState('')
  const [isProcessingPayment, setIsProcessingPayment] = useState(false)

  // Action states
  const [isSubmittingRound, setIsSubmittingRound] = useState(false)
  const [isRequestingCheck, setIsRequestingCheck] = useState(false)
  const [isClosingTable, setIsClosingTable] = useState(false)

  // Confirm dialog
  const [confirmAction, setConfirmAction] = useState<{
    title: string
    message: string
    onConfirm: () => void
  } | null>(null)

  // Load menu on mount
  useEffect(() => {
    async function loadMenu() {
      if (!branchId) return

      setIsLoadingMenu(true)
      setMenuError(null)

      try {
        // First get branch slug
        const branch = await branchAPI.getBranch(branchId)
        // Then get menu using slug
        const menuData = await menuAPI.getMenuBySlug(branch.slug)
        setMenu(menuData)

        // Select first category by default
        if (menuData.categories.length > 0) {
          setSelectedCategoryId(menuData.categories[0].id)
        }
      } catch (err) {
        console.error('Failed to load menu:', err)
        setMenuError('Error al cargar el menu')
      } finally {
        setIsLoadingMenu(false)
      }
    }

    loadMenu()
  }, [branchId])

  // Load session when table has active session
  useEffect(() => {
    if (table?.session_id) {
      fetchSessionSummary(table.session_id).catch(console.error)
    } else {
      clearActiveSession()
    }
  }, [table?.session_id, fetchSessionSummary, clearActiveSession])

  // Derived state
  const selectedCategory = useMemo(() => {
    if (!menu || !selectedCategoryId) return null
    return menu.categories.find((c) => c.id === selectedCategoryId) || null
  }, [menu, selectedCategoryId])

  const cartTotal = useMemo(() => {
    return cart.reduce((sum, item) => sum + item.product.price_cents * item.qty, 0)
  }, [cart])

  const cartItemCount = useMemo(() => {
    return cart.reduce((sum, item) => sum + item.qty, 0)
  }, [cart])

  // Check if table needs activation
  const needsActivation = table?.status === 'FREE' && !table?.session_id

  // Check if check was requested
  const checkRequested = activeSession?.check_status === 'REQUESTED' || activeSession?.check_status === 'IN_PAYMENT'

  // Check if fully paid
  const isFullyPaid = activeSession?.check_status === 'PAID' ||
    (activeSession && activeSession.paid_cents >= activeSession.total_cents && activeSession.total_cents > 0)

  // Remaining amount to pay
  const remainingToPay = activeSession
    ? Math.max(0, activeSession.total_cents - activeSession.paid_cents)
    : 0

  // Cart operations
  const addToCart = useCallback((product: MenuProduct) => {
    setCart((prev) => {
      const existing = prev.find((item) => item.product.id === product.id)
      if (existing) {
        return prev.map((item) =>
          item.product.id === product.id
            ? { ...item, qty: item.qty + 1 }
            : item
        )
      }
      return [...prev, { product, qty: 1, notes: '' }]
    })
  }, [])

  const removeFromCart = useCallback((productId: number) => {
    setCart((prev) => prev.filter((item) => item.product.id !== productId))
  }, [])

  const updateCartItemQty = useCallback((productId: number, delta: number) => {
    setCart((prev) =>
      prev
        .map((item) =>
          item.product.id === productId
            ? { ...item, qty: Math.max(0, item.qty + delta) }
            : item
        )
        .filter((item) => item.qty > 0)
    )
  }, [])

  const updateCartItemNotes = useCallback((productId: number, notes: string) => {
    setCart((prev) =>
      prev.map((item) =>
        item.product.id === productId ? { ...item, notes } : item
      )
    )
  }, [])

  const clearCart = useCallback(() => {
    setCart([])
  }, [])

  // Activate table
  const handleActivateTable = async () => {
    if (!table) return

    setIsActivating(true)
    try {
      await activateTable(table.table_id, { diner_count: dinerCount })
      setShowActivateModal(false)
      setDinerCount(2)
    } catch (err) {
      console.error('Failed to activate table:', err)
    } finally {
      setIsActivating(false)
    }
  }

  // Submit round
  const handleSubmitRound = async () => {
    if (!activeSession || cart.length === 0) return

    setIsSubmittingRound(true)
    try {
      const items: WaiterRoundItem[] = cart.map((item) => ({
        product_id: item.product.id,
        qty: item.qty,
        notes: item.notes || undefined,
      }))

      await submitRound(activeSession.session_id, { items })
      clearCart()
      setShowCart(false)

      // Refresh session summary
      await fetchSessionSummary(activeSession.session_id)
    } catch (err) {
      console.error('Failed to submit round:', err)
    } finally {
      setIsSubmittingRound(false)
    }
  }

  // Request check
  const handleRequestCheck = async () => {
    if (!activeSession) return

    setIsRequestingCheck(true)
    try {
      await requestCheck(activeSession.session_id)
      await fetchSessionSummary(activeSession.session_id)
    } catch (err) {
      console.error('Failed to request check:', err)
    } finally {
      setIsRequestingCheck(false)
    }
  }

  // Open payment modal
  const openPaymentModal = () => {
    // Pre-fill with remaining amount
    setPaymentAmount(String(remainingToPay / 100))
    setPaymentMethod('CASH')
    setPaymentNotes('')
    setShowPaymentModal(true)
  }

  // Register manual payment
  const handleRegisterPayment = async () => {
    if (!activeSession) return

    const amountCents = Math.round(parseFloat(paymentAmount) * 100)
    if (isNaN(amountCents) || amountCents <= 0) {
      return
    }

    setIsProcessingPayment(true)
    try {
      // Get check_id from session - we need to request check first if not done
      let checkId = activeSession.check_status ?
        // Assume we have check_id when check_status is set
        // We need to get this from the API response
        0 : 0

      // If no check requested yet, request it first
      if (!activeSession.check_status || activeSession.check_status === 'OPEN') {
        const checkResult = await requestCheck(activeSession.session_id)
        checkId = checkResult.check_id
      } else {
        // Re-fetch session to get check_id (it should be in the response)
        // For now, we'll call requestCheck which is idempotent and returns the check_id
        const checkResult = await requestCheck(activeSession.session_id)
        checkId = checkResult.check_id
      }

      await registerManualPayment({
        check_id: checkId,
        amount_cents: amountCents,
        manual_method: paymentMethod,
        notes: paymentNotes || undefined,
      })

      setShowPaymentModal(false)
      setPaymentAmount('')
      setPaymentNotes('')

      // Refresh session
      await fetchSessionSummary(activeSession.session_id)
    } catch (err) {
      console.error('Failed to register payment:', err)
    } finally {
      setIsProcessingPayment(false)
    }
  }

  // Close table
  const handleCloseTable = async () => {
    if (!table) return

    setIsClosingTable(true)
    try {
      await closeTableSession(table.table_id)
      clearCart()
      onBack()
    } catch (err) {
      console.error('Failed to close table:', err)
    } finally {
      setIsClosingTable(false)
    }
  }

  // Loading state
  if (!table) {
    return (
      <div className="min-h-screen bg-white flex flex-col">
        <Header />
        <main className="flex-1 flex items-center justify-center">
          <div className="text-center">
            <p className="text-gray-500 mb-4">Mesa no encontrada</p>
            <Button onClick={onBack}>Volver</Button>
          </div>
        </main>
      </div>
    )
  }

  return (
    <div className="min-h-screen bg-white flex flex-col">
      <Header />

      <main className="flex-1 flex flex-col overflow-hidden">
        {/* Top bar with table info and back button */}
        <div className="flex-shrink-0 p-4 border-b border-gray-200">
          <div className="flex items-center justify-between">
            <button
              onClick={onBack}
              className="flex items-center gap-2 text-gray-500 hover:text-gray-900"
            >
              <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M15 19l-7-7 7-7" />
              </svg>
              Volver
            </button>

            <div className="text-center">
              <h1 className="text-xl font-bold text-gray-900">Mesa {table.code}</h1>
              <span className={`text-xs px-2 py-0.5 rounded-full ${
                table.status === 'FREE' ? 'bg-green-500/20 text-green-400' :
                table.status === 'ACTIVE' ? 'bg-orange-500/20 text-orange-400' :
                table.status === 'PAYING' ? 'bg-purple-500/20 text-purple-400' :
                'bg-gray-200 text-gray-500'
              }`}>
                {table.status === 'FREE' ? 'Libre' :
                 table.status === 'ACTIVE' ? 'Ocupada' :
                 table.status === 'PAYING' ? 'Pagando' : 'Fuera de servicio'}
              </span>
            </div>

            {/* Cart button */}
            <button
              onClick={() => setShowCart(true)}
              className="relative p-2 bg-gray-100 rounded-lg hover:bg-gray-200"
              disabled={cart.length === 0}
            >
              <svg className="w-6 h-6 text-gray-900" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M3 3h2l.4 2M7 13h10l4-8H5.4M7 13L5.4 5M7 13l-2.293 2.293c-.63.63-.184 1.707.707 1.707H17m0 0a2 2 0 100 4 2 2 0 000-4zm-8 2a2 2 0 11-4 0 2 2 0 014 0z" />
              </svg>
              {cartItemCount > 0 && (
                <span className="absolute -top-1 -right-1 bg-orange-500 text-gray-900 text-xs w-5 h-5 rounded-full flex items-center justify-center">
                  {cartItemCount}
                </span>
              )}
            </button>
          </div>

          {/* Session summary bar */}
          {activeSession && (
            <div className="mt-3 p-3 bg-gray-50 rounded-lg">
              <div className="flex items-center justify-between text-sm">
                <span className="text-gray-500">
                  {activeSession.diner_count} comensales | {activeSession.rounds_count} rondas
                </span>
                <div className="text-right">
                  <span className="text-gray-900 font-medium">{formatPrice(activeSession.total_cents)}</span>
                  {activeSession.paid_cents > 0 && (
                    <span className="text-green-400 ml-2">
                      (Pagado: {formatPrice(activeSession.paid_cents)})
                    </span>
                  )}
                </div>
              </div>
              {activeSession.check_status && (
                <div className="mt-2 text-xs">
                  <span className={`px-2 py-0.5 rounded-full ${
                    activeSession.check_status === 'PAID' ? 'bg-green-500/20 text-green-400' :
                    activeSession.check_status === 'REQUESTED' ? 'bg-purple-500/20 text-purple-400' :
                    'bg-gray-200 text-gray-500'
                  }`}>
                    Cuenta: {activeSession.check_status}
                  </span>
                </div>
              )}
            </div>
          )}
        </div>

        {/* Main content area */}
        <div className="flex-1 overflow-hidden flex flex-col">
          {/* If table needs activation */}
          {needsActivation ? (
            <div className="flex-1 flex items-center justify-center p-4">
              <div className="text-center">
                <div className="w-20 h-20 mx-auto mb-4 bg-gray-100 rounded-full flex items-center justify-center">
                  <svg className="w-10 h-10 text-gray-500" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 4v16m8-8H4" />
                  </svg>
                </div>
                <h2 className="text-xl font-semibold text-gray-900 mb-2">Mesa libre</h2>
                <p className="text-gray-500 mb-6">Activa la mesa para comenzar a tomar pedidos</p>
                <Button
                  variant="primary"
                  size="lg"
                  onClick={() => setShowActivateModal(true)}
                >
                  Activar Mesa
                </Button>
              </div>
            </div>
          ) : isLoadingMenu ? (
            <div className="flex-1 flex items-center justify-center">
              <div className="animate-spin w-8 h-8 border-2 border-orange-500 border-t-transparent rounded-full" />
            </div>
          ) : menuError ? (
            <div className="flex-1 flex items-center justify-center p-4">
              <div className="text-center">
                <p className="text-red-400 mb-4">{menuError}</p>
                <Button onClick={() => window.location.reload()}>Reintentar</Button>
              </div>
            </div>
          ) : menu ? (
            <>
              {/* Category tabs */}
              <div className="flex-shrink-0 border-b border-gray-200">
                <div className="flex overflow-x-auto p-2 gap-2 scrollbar-hide">
                  {menu.categories.map((category) => (
                    <button
                      key={category.id}
                      onClick={() => setSelectedCategoryId(category.id)}
                      className={`flex-shrink-0 px-4 py-2 rounded-lg text-sm font-medium transition-colors ${
                        selectedCategoryId === category.id
                          ? 'bg-orange-500 text-gray-900'
                          : 'bg-gray-100 text-gray-500 hover:bg-gray-200'
                      }`}
                    >
                      {category.icon && <span className="mr-1">{category.icon}</span>}
                      {category.name}
                    </button>
                  ))}
                </div>
              </div>

              {/* Products grid */}
              <div className="flex-1 overflow-y-auto p-4">
                {selectedCategory && (
                  <div className="grid grid-cols-2 gap-3">
                    {selectedCategory.products
                      .filter((p) => p.is_available)
                      .map((product) => {
                        const inCart = cart.find((item) => item.product.id === product.id)
                        return (
                          <button
                            key={product.id}
                            onClick={() => addToCart(product)}
                            className={`relative p-3 rounded-xl text-left transition-all ${
                              inCart
                                ? 'bg-orange-500/20 border-2 border-orange-500'
                                : 'bg-gray-50 border border-gray-200 hover:border-gray-200'
                            }`}
                          >
                            {inCart && (
                              <span className="absolute -top-2 -right-2 bg-orange-500 text-gray-900 text-xs w-6 h-6 rounded-full flex items-center justify-center font-bold">
                                {inCart.qty}
                              </span>
                            )}
                            <h3 className="text-gray-900 font-medium text-sm line-clamp-2 mb-1">
                              {product.name}
                            </h3>
                            <p className="text-orange-500 font-bold text-sm">
                              {formatPrice(product.price_cents)}
                            </p>
                            {product.badge && (
                              <span className="absolute top-2 right-2 text-xs bg-orange-500/20 text-orange-400 px-1.5 py-0.5 rounded">
                                {product.badge}
                              </span>
                            )}
                          </button>
                        )
                      })}
                  </div>
                )}
              </div>

              {/* Bottom action bar */}
              <div className="flex-shrink-0 p-4 border-t border-gray-200 bg-white/80 backdrop-blur shadow-sm">
                <div className="flex gap-2">
                  {/* Actions based on state */}
                  {!checkRequested && (
                    <>
                      <Button
                        variant="secondary"
                        className="flex-1"
                        onClick={handleRequestCheck}
                        disabled={!activeSession || activeSession.total_cents === 0 || isRequestingCheck}
                        isLoading={isRequestingCheck}
                      >
                        Pedir Cuenta
                      </Button>
                    </>
                  )}

                  {checkRequested && !isFullyPaid && (
                    <Button
                      variant="primary"
                      className="flex-1"
                      onClick={openPaymentModal}
                    >
                      Registrar Pago ({formatPrice(remainingToPay)})
                    </Button>
                  )}

                  {isFullyPaid && (
                    <Button
                      variant="primary"
                      className="flex-1"
                      onClick={() => setConfirmAction({
                        title: 'Cerrar Mesa',
                        message: 'La cuenta esta pagada. Confirmar cierre de mesa?',
                        onConfirm: handleCloseTable,
                      })}
                      disabled={isClosingTable}
                      isLoading={isClosingTable}
                    >
                      Cerrar Mesa
                    </Button>
                  )}
                </div>
              </div>
            </>
          ) : null}
        </div>
      </main>

      {/* Cart Sidebar */}
      {showCart && (
        <div className="fixed inset-0 z-50 flex">
          {/* Backdrop */}
          <div
            className="absolute inset-0 bg-black/60"
            onClick={() => setShowCart(false)}
          />

          {/* Cart panel */}
          <div className="absolute right-0 top-0 bottom-0 w-full max-w-sm bg-white border-l border-gray-200 flex flex-col">
            {/* Cart header */}
            <div className="flex items-center justify-between p-4 border-b border-gray-200">
              <h2 className="text-lg font-semibold text-gray-900">Pedido</h2>
              <button
                onClick={() => setShowCart(false)}
                className="p-2 text-gray-500 hover:text-gray-900"
              >
                <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
                </svg>
              </button>
            </div>

            {/* Cart items */}
            <div className="flex-1 overflow-y-auto p-4">
              {cart.length === 0 ? (
                <p className="text-gray-400 text-center py-8">El carrito esta vacio</p>
              ) : (
                <div className="space-y-4">
                  {cart.map((item) => (
                    <div key={item.product.id} className="bg-gray-50 rounded-lg p-3">
                      <div className="flex items-start justify-between mb-2">
                        <div className="flex-1">
                          <h3 className="text-gray-900 font-medium text-sm">{item.product.name}</h3>
                          <p className="text-orange-500 text-sm">{formatPrice(item.product.price_cents)}</p>
                        </div>
                        <button
                          onClick={() => removeFromCart(item.product.id)}
                          className="p-1 text-gray-400 hover:text-red-500"
                        >
                          <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16" />
                          </svg>
                        </button>
                      </div>

                      {/* Quantity controls */}
                      <div className="flex items-center gap-2 mb-2">
                        <button
                          onClick={() => updateCartItemQty(item.product.id, -1)}
                          className="w-8 h-8 rounded-full bg-gray-100 text-gray-900 flex items-center justify-center hover:bg-gray-200"
                        >
                          -
                        </button>
                        <span className="text-gray-900 font-medium w-8 text-center">{item.qty}</span>
                        <button
                          onClick={() => updateCartItemQty(item.product.id, 1)}
                          className="w-8 h-8 rounded-full bg-gray-100 text-gray-900 flex items-center justify-center hover:bg-gray-200"
                        >
                          +
                        </button>
                        <span className="text-gray-500 text-sm ml-auto">
                          {formatPrice(item.product.price_cents * item.qty)}
                        </span>
                      </div>

                      {/* Notes input */}
                      <input
                        type="text"
                        value={item.notes}
                        onChange={(e) => updateCartItemNotes(item.product.id, e.target.value)}
                        placeholder="Notas (sin sal, termino, etc.)"
                        className="w-full px-3 py-1.5 bg-gray-100 border border-gray-200 rounded text-gray-900 text-sm placeholder:text-gray-400"
                      />
                    </div>
                  ))}
                </div>
              )}
            </div>

            {/* Cart footer */}
            <div className="p-4 border-t border-gray-200">
              <div className="flex items-center justify-between mb-4">
                <span className="text-gray-500">Total</span>
                <span className="text-xl font-bold text-gray-900">{formatPrice(cartTotal)}</span>
              </div>
              <div className="flex gap-2">
                <Button
                  variant="secondary"
                  className="flex-1"
                  onClick={clearCart}
                  disabled={cart.length === 0}
                >
                  Limpiar
                </Button>
                <Button
                  variant="primary"
                  className="flex-1"
                  onClick={handleSubmitRound}
                  disabled={cart.length === 0 || isSubmittingRound}
                  isLoading={isSubmittingRound}
                >
                  Enviar a Cocina
                </Button>
              </div>
            </div>
          </div>
        </div>
      )}

      {/* Activate Table Modal */}
      {showActivateModal && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4">
          <div className="absolute inset-0 bg-black/60" onClick={() => setShowActivateModal(false)} />
          <div className="relative bg-gray-50 rounded-xl p-6 w-full max-w-sm">
            <h2 className="text-xl font-semibold text-gray-900 mb-4">Activar Mesa {table.code}</h2>

            <div className="mb-6">
              <label className="block text-sm text-gray-500 mb-2">Cantidad de comensales</label>
              <div className="flex items-center gap-4">
                <button
                  onClick={() => setDinerCount((prev) => Math.max(1, prev - 1))}
                  className="w-12 h-12 rounded-full bg-gray-100 text-gray-900 text-xl flex items-center justify-center hover:bg-gray-200"
                >
                  -
                </button>
                <span className="text-3xl font-bold text-gray-900 w-12 text-center">{dinerCount}</span>
                <button
                  onClick={() => setDinerCount((prev) => Math.min(20, prev + 1))}
                  className="w-12 h-12 rounded-full bg-gray-100 text-gray-900 text-xl flex items-center justify-center hover:bg-gray-200"
                >
                  +
                </button>
              </div>
            </div>

            <div className="flex gap-2">
              <Button
                variant="secondary"
                className="flex-1"
                onClick={() => setShowActivateModal(false)}
              >
                Cancelar
              </Button>
              <Button
                variant="primary"
                className="flex-1"
                onClick={handleActivateTable}
                disabled={isActivating}
                isLoading={isActivating}
              >
                Activar
              </Button>
            </div>
          </div>
        </div>
      )}

      {/* Manual Payment Modal */}
      {showPaymentModal && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4">
          <div className="absolute inset-0 bg-black/60" onClick={() => setShowPaymentModal(false)} />
          <div className="relative bg-gray-50 rounded-xl p-6 w-full max-w-sm">
            <h2 className="text-xl font-semibold text-gray-900 mb-2">Registrar Pago</h2>
            <p className="text-sm text-gray-500 mb-4">
              Restante: <span className="text-orange-500 font-medium">{formatPrice(remainingToPay)}</span>
            </p>

            {/* Payment method selection */}
            <div className="mb-4">
              <label className="block text-sm text-gray-500 mb-2">Metodo de pago</label>
              <div className="grid grid-cols-2 gap-2">
                {(Object.keys(PAYMENT_METHOD_LABELS) as ManualPaymentMethod[]).map((method) => (
                  <button
                    key={method}
                    onClick={() => setPaymentMethod(method)}
                    className={`px-3 py-2 rounded-lg text-sm font-medium transition-colors ${
                      paymentMethod === method
                        ? 'bg-orange-500 text-gray-900'
                        : 'bg-gray-100 text-gray-500 hover:bg-gray-200'
                    }`}
                  >
                    {PAYMENT_METHOD_LABELS[method]}
                  </button>
                ))}
              </div>
            </div>

            {/* Amount input */}
            <div className="mb-4">
              <label className="block text-sm text-gray-500 mb-2">Monto ($)</label>
              <input
                type="number"
                step="0.01"
                min="0"
                value={paymentAmount}
                onChange={(e) => setPaymentAmount(e.target.value)}
                className="w-full px-4 py-3 bg-gray-100 border border-gray-200 rounded-lg text-gray-900 text-lg"
                placeholder="0.00"
              />
            </div>

            {/* Notes input */}
            <div className="mb-6">
              <label className="block text-sm text-gray-500 mb-2">Notas (opcional)</label>
              <input
                type="text"
                value={paymentNotes}
                onChange={(e) => setPaymentNotes(e.target.value)}
                className="w-full px-4 py-2 bg-gray-100 border border-gray-200 rounded-lg text-gray-900 text-sm"
                placeholder="Referencia, observaciones..."
              />
            </div>

            <div className="flex gap-2">
              <Button
                variant="secondary"
                className="flex-1"
                onClick={() => setShowPaymentModal(false)}
              >
                Cancelar
              </Button>
              <Button
                variant="primary"
                className="flex-1"
                onClick={handleRegisterPayment}
                disabled={!paymentAmount || parseFloat(paymentAmount) <= 0 || isProcessingPayment}
                isLoading={isProcessingPayment}
              >
                Confirmar
              </Button>
            </div>
          </div>
        </div>
      )}

      {/* Confirm Dialog */}
      <ConfirmDialog
        isOpen={confirmAction !== null}
        title={confirmAction?.title || ''}
        message={confirmAction?.message || ''}
        confirmLabel="Confirmar"
        cancelLabel="Cancelar"
        onConfirm={() => {
          confirmAction?.onConfirm()
          setConfirmAction(null)
        }}
        onCancel={() => setConfirmAction(null)}
        isLoading={isClosingTable}
      />
    </div>
  )
}
