import { useState, useEffect, useCallback, useMemo } from 'react'
import { comandaAPI, waiterTableAPI } from '../services/api'
import { useTablesStore, selectTables } from '../stores/tablesStore'
import type { MenuCompact, ProductCompact, WaiterRoundItem } from '../services/api'
import type { TableCard } from '../types'
import { Button } from './Button'
import { formatPrice, formatTableCode } from '../utils/format'

interface AutogestionModalProps {
  isOpen: boolean
  onClose: () => void
  branchId: number
}

interface CartItem extends ProductCompact {
  qty: number
  notes?: string
}

// Steps in the autogestión flow
type AutogestionStep = 'select-table' | 'take-order'

export function AutogestionModal({ isOpen, onClose, branchId }: AutogestionModalProps) {
  // Step management
  const [step, setStep] = useState<AutogestionStep>('select-table')

  // Table selection
  const tables = useTablesStore(selectTables)
  const [selectedTable, setSelectedTable] = useState<TableCard | null>(null)
  const [sessionId, setSessionId] = useState<number | null>(null)
  const [isActivating, setIsActivating] = useState(false)
  const [dinerCount, setDinerCount] = useState(1)

  // Menu state
  const [menu, setMenu] = useState<MenuCompact | null>(null)
  const [isLoadingMenu, setIsLoadingMenu] = useState(false)
  const [menuError, setMenuError] = useState<string | null>(null)

  // Cart state
  const [cart, setCart] = useState<CartItem[]>([])

  // Search and filter
  const [searchQuery, setSearchQuery] = useState('')
  const [selectedCategory, setSelectedCategory] = useState<number | null>(null)

  // Submission state
  const [isSubmitting, setIsSubmitting] = useState(false)
  const [submitSuccess, setSubmitSuccess] = useState(false)

  // Reset state when modal closes
  useEffect(() => {
    if (!isOpen) {
      setStep('select-table')
      setSelectedTable(null)
      setSessionId(null)
      setDinerCount(1)
      setMenu(null)
      setCart([])
      setSearchQuery('')
      setSelectedCategory(null)
      setSubmitSuccess(false)
    }
  }, [isOpen])

  // Load menu when entering take-order step
  useEffect(() => {
    if (step === 'take-order' && !menu) {
      loadMenu()
    }
  }, [step])

  const loadMenu = async () => {
    setIsLoadingMenu(true)
    setMenuError(null)
    try {
      const data = await comandaAPI.getMenuCompact(branchId)
      setMenu(data)
      if (data.categories.length > 0) {
        setSelectedCategory(data.categories[0].id)
      }
    } catch (err) {
      setMenuError('Error al cargar el menú')
      console.error('Failed to load menu:', err)
    } finally {
      setIsLoadingMenu(false)
    }
  }

  // Handle table selection and activation
  const handleTableSelect = async (table: TableCard) => {
    setSelectedTable(table)

    // If table already has a session, use it
    if (table.session_id) {
      setSessionId(table.session_id)
      setStep('take-order')
      return
    }
  }

  // Activate table (create session) for free tables
  const handleActivateTable = async () => {
    if (!selectedTable) return

    setIsActivating(true)
    try {
      const response = await waiterTableAPI.activateTable(selectedTable.table_id, {
        diner_count: dinerCount,
      })
      setSessionId(response.session_id)
      setStep('take-order')
    } catch (err) {
      console.error('Failed to activate table:', err)
    } finally {
      setIsActivating(false)
    }
  }

  // Filter products
  const filteredProducts = useMemo(() => {
    if (!menu) return []

    let products: ProductCompact[] = []

    if (selectedCategory === null) {
      products = menu.categories.flatMap((cat) => cat.products)
    } else {
      const category = menu.categories.find((cat) => cat.id === selectedCategory)
      products = category?.products || []
    }

    if (searchQuery.trim()) {
      const query = searchQuery.toLowerCase().trim()
      products = products.filter(
        (p) =>
          p.name.toLowerCase().includes(query) ||
          p.description?.toLowerCase().includes(query)
      )
    }

    return products
  }, [menu, selectedCategory, searchQuery])

  // Cart operations
  const addToCart = useCallback((product: ProductCompact) => {
    setCart((prev) => {
      const existing = prev.find((item) => item.id === product.id)
      if (existing) {
        return prev.map((item) =>
          item.id === product.id ? { ...item, qty: item.qty + 1 } : item
        )
      }
      return [...prev, { ...product, qty: 1 }]
    })
  }, [])

  const updateQuantity = useCallback((productId: number, delta: number) => {
    setCart((prev) =>
      prev
        .map((item) => {
          if (item.id === productId) {
            const newQty = item.qty + delta
            return newQty > 0 ? { ...item, qty: newQty } : null
          }
          return item
        })
        .filter((item): item is CartItem => item !== null)
    )
  }, [])

  const removeFromCart = useCallback((productId: number) => {
    setCart((prev) => prev.filter((item) => item.id !== productId))
  }, [])

  const clearCart = useCallback(() => {
    setCart([])
  }, [])

  const cartTotal = useMemo(() => {
    return cart.reduce((sum, item) => sum + item.price_cents * item.qty, 0)
  }, [cart])

  const cartItemCount = useMemo(() => {
    return cart.reduce((sum, item) => sum + item.qty, 0)
  }, [cart])

  // Submit round
  const handleSubmitRound = async () => {
    if (cart.length === 0 || !sessionId) return

    setIsSubmitting(true)
    try {
      const items: WaiterRoundItem[] = cart.map((item) => ({
        product_id: item.id,
        qty: item.qty,
        notes: item.notes,
      }))

      await waiterTableAPI.submitRound(sessionId, { items })
      setSubmitSuccess(true)
      setCart([])

      // Show success and close after delay
      setTimeout(() => {
        onClose()
      }, 1500)
    } catch (err) {
      console.error('Failed to submit round:', err)
    } finally {
      setIsSubmitting(false)
    }
  }

  // Filter tables - show FREE and ACTIVE tables
  const availableTables = useMemo(() => {
    return tables.filter((t) => t.status === 'FREE' || t.status === 'ACTIVE')
  }, [tables])

  if (!isOpen) return null

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center">
      {/* Backdrop */}
      <div
        className="absolute inset-0 bg-black/50 backdrop-blur-sm"
        onClick={onClose}
      />

      {/* Modal content */}
      <div className="relative w-full h-full max-w-6xl max-h-[90vh] bg-white shadow-2xl flex flex-col m-4 overflow-hidden">
        {/* Header */}
        <header className="flex items-center justify-between px-6 py-4 border-b border-gray-200 bg-gray-50">
          <div className="flex items-center gap-3">
            <h2 className="text-xl font-bold text-gray-900">Autogestión</h2>
            {selectedTable && (
              <span className="bg-orange-100 text-orange-600 px-3 py-1 text-sm font-medium">
                Mesa {formatTableCode(selectedTable.code)}
              </span>
            )}
          </div>
          <button
            onClick={onClose}
            className="p-2 hover:bg-gray-200 transition-colors"
            aria-label="Cerrar"
          >
            <svg className="w-6 h-6 text-gray-500" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
            </svg>
          </button>
        </header>

        {/* Step 1: Table Selection */}
        {step === 'select-table' && (
          <div className="flex-1 overflow-auto p-6">
            <h3 className="text-lg font-semibold text-gray-700 mb-4">
              Selecciona una mesa para tomar el pedido
            </h3>

            {/* Table grid */}
            <div className="grid grid-cols-3 sm:grid-cols-4 md:grid-cols-5 lg:grid-cols-6 gap-3 mb-6">
              {availableTables.map((table) => (
                <button
                  key={table.table_id}
                  onClick={() => handleTableSelect(table)}
                  className={`p-4 border-2 transition-all ${
                    selectedTable?.table_id === table.table_id
                      ? 'border-orange-500 bg-orange-50'
                      : table.status === 'ACTIVE'
                      ? 'border-blue-200 bg-blue-50 hover:border-blue-400'
                      : 'border-gray-200 bg-white hover:border-gray-400'
                  }`}
                >
                  <div className="text-center">
                    <span className="block text-lg font-bold text-gray-900">
                      {formatTableCode(table.code)}
                    </span>
                    <span className={`text-xs font-medium ${
                      table.status === 'ACTIVE' ? 'text-blue-600' : 'text-green-600'
                    }`}>
                      {table.status === 'ACTIVE' ? 'Activa' : 'Libre'}
                    </span>
                  </div>
                </button>
              ))}
            </div>

            {/* Selected table info and activation */}
            {selectedTable && selectedTable.status === 'FREE' && (
              <div className="bg-gray-50 p-6 border border-gray-200">
                <h4 className="font-semibold text-gray-700 mb-4">
                  Activar Mesa {formatTableCode(selectedTable.code)}
                </h4>
                <div className="flex items-center gap-4 mb-4">
                  <label className="text-gray-600">Cantidad de comensales:</label>
                  <div className="flex items-center gap-2">
                    <button
                      onClick={() => setDinerCount(Math.max(1, dinerCount - 1))}
                      className="w-10 h-10 bg-gray-200 hover:bg-gray-300 flex items-center justify-center font-bold text-lg"
                    >
                      −
                    </button>
                    <span className="w-12 text-center text-xl font-bold">{dinerCount}</span>
                    <button
                      onClick={() => setDinerCount(dinerCount + 1)}
                      className="w-10 h-10 bg-gray-200 hover:bg-gray-300 flex items-center justify-center font-bold text-lg"
                    >
                      +
                    </button>
                  </div>
                </div>
                <Button
                  variant="primary"
                  onClick={handleActivateTable}
                  disabled={isActivating}
                  className="w-full"
                >
                  {isActivating ? 'Activando...' : 'Activar y Tomar Pedido'}
                </Button>
              </div>
            )}

            {/* For active tables, just proceed */}
            {selectedTable && selectedTable.status === 'ACTIVE' && (
              <div className="bg-blue-50 p-6 border border-blue-200">
                <h4 className="font-semibold text-blue-700 mb-4">
                  Mesa {formatTableCode(selectedTable.code)} ya tiene sesión activa
                </h4>
                <p className="text-blue-600 mb-4">
                  Puedes agregar más productos a esta mesa.
                </p>
                <Button
                  variant="primary"
                  onClick={() => {
                    setSessionId(selectedTable.session_id)
                    setStep('take-order')
                  }}
                  className="w-full"
                >
                  Tomar Pedido
                </Button>
              </div>
            )}
          </div>
        )}

        {/* Step 2: Take Order - Split View */}
        {step === 'take-order' && (
          <div className="flex-1 flex overflow-hidden">
            {/* Left side - Search and Products */}
            <div className="w-1/2 border-r border-gray-200 flex flex-col">
              {/* Search header */}
              <div className="p-4 border-b border-gray-100">
                <div className="relative">
                  <svg
                    className="absolute left-3 top-1/2 -translate-y-1/2 w-5 h-5 text-gray-400"
                    fill="none"
                    stroke="currentColor"
                    viewBox="0 0 24 24"
                  >
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0z" />
                  </svg>
                  <input
                    type="text"
                    placeholder="Buscar categorías y platos..."
                    value={searchQuery}
                    onChange={(e) => setSearchQuery(e.target.value)}
                    className="w-full pl-10 pr-4 py-3 bg-gray-100 border border-gray-200 text-gray-900 placeholder-gray-400 focus:outline-none focus:ring-2 focus:ring-orange-500 focus:border-transparent"
                  />
                </div>
              </div>

              {/* Category tabs */}
              <div className="flex gap-2 px-4 py-3 overflow-x-auto border-b border-gray-100 scrollbar-hide">
                <button
                  onClick={() => setSelectedCategory(null)}
                  className={`flex-shrink-0 px-4 py-2 text-sm font-medium transition-colors ${
                    selectedCategory === null
                      ? 'bg-orange-500 text-white'
                      : 'bg-gray-100 text-gray-600 hover:bg-gray-200'
                  }`}
                >
                  Todos
                </button>
                {menu?.categories.map((category) => (
                  <button
                    key={category.id}
                    onClick={() => setSelectedCategory(category.id)}
                    className={`flex-shrink-0 px-4 py-2 text-sm font-medium transition-colors ${
                      selectedCategory === category.id
                        ? 'bg-orange-500 text-white'
                        : 'bg-gray-100 text-gray-600 hover:bg-gray-200'
                    }`}
                  >
                    {category.name}
                  </button>
                ))}
              </div>

              {/* Product list */}
              <div className="flex-1 overflow-y-auto p-4 space-y-2">
                {isLoadingMenu ? (
                  <div className="flex justify-center py-12">
                    <div className="animate-spin w-8 h-8 border-2 border-orange-500 border-t-transparent rounded-full" />
                  </div>
                ) : menuError ? (
                  <div className="text-center py-8">
                    <p className="text-red-500 mb-4">{menuError}</p>
                    <Button variant="secondary" onClick={loadMenu}>Reintentar</Button>
                  </div>
                ) : filteredProducts.length === 0 ? (
                  <p className="text-gray-400 text-center py-8">No hay productos</p>
                ) : (
                  filteredProducts.map((product) => {
                    const cartItem = cart.find((c) => c.id === product.id)
                    const qtyInCart = cartItem?.qty || 0

                    return (
                      <div
                        key={product.id}
                        className={`bg-white p-4 border-2 transition-all ${
                          qtyInCart > 0 ? 'border-orange-500 bg-orange-50' : 'border-gray-200 hover:border-gray-300'
                        } ${!product.is_available ? 'opacity-50' : ''}`}
                      >
                        <div className="flex items-center justify-between">
                          <div className="flex-1 min-w-0">
                            <div className="flex items-center gap-2">
                              <span className="font-medium text-gray-900 truncate">{product.name}</span>
                              {product.allergen_icons.length > 0 && (
                                <span className="text-sm">{product.allergen_icons.slice(0, 3).join('')}</span>
                              )}
                            </div>
                            {product.description && (
                              <p className="text-gray-500 text-sm mt-1 line-clamp-1">{product.description}</p>
                            )}
                            <p className="text-orange-600 font-semibold mt-1">{formatPrice(product.price_cents)}</p>
                          </div>

                          <div className="flex items-center gap-2 ml-4">
                            {qtyInCart > 0 ? (
                              <div className="flex items-center gap-1 bg-gray-100">
                                <button
                                  onClick={() => updateQuantity(product.id, -1)}
                                  className="w-10 h-10 flex items-center justify-center text-lg font-bold text-gray-700 hover:bg-gray-200"
                                >
                                  −
                                </button>
                                <span className="w-8 text-center font-bold text-gray-900">{qtyInCart}</span>
                                <button
                                  onClick={() => updateQuantity(product.id, 1)}
                                  className="w-10 h-10 flex items-center justify-center text-lg font-bold text-gray-700 hover:bg-gray-200"
                                  disabled={!product.is_available}
                                >
                                  +
                                </button>
                              </div>
                            ) : (
                              <button
                                onClick={() => addToCart(product)}
                                disabled={!product.is_available}
                                className="w-12 h-12 bg-orange-500 hover:bg-orange-600 disabled:bg-gray-200 text-white flex items-center justify-center text-2xl font-bold transition-colors"
                              >
                                +
                              </button>
                            )}
                          </div>
                        </div>
                      </div>
                    )
                  })
                )}
              </div>
            </div>

            {/* Right side - Cart */}
            <div className="w-1/2 flex flex-col bg-gray-50">
              {/* Cart header */}
              <div className="p-4 border-b border-gray-200 bg-white">
                <h3 className="font-semibold text-gray-900 flex items-center gap-2">
                  <svg className="w-5 h-5 text-orange-500" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M3 3h2l.4 2M7 13h10l4-8H5.4M7 13L5.4 5M7 13l-2.293 2.293c-.63.63-.184 1.707.707 1.707H17m0 0a2 2 0 100 4 2 2 0 000-4zm-8 2a2 2 0 11-4 0 2 2 0 014 0z" />
                  </svg>
                  Ronda Actual
                  {cartItemCount > 0 && (
                    <span className="bg-orange-500 text-white px-2 py-0.5 text-sm">
                      {cartItemCount}
                    </span>
                  )}
                </h3>
              </div>

              {/* Cart items */}
              <div className="flex-1 overflow-y-auto p-4">
                {submitSuccess ? (
                  <div className="flex flex-col items-center justify-center h-full">
                    <div className="w-16 h-16 bg-green-100 rounded-full flex items-center justify-center mb-4">
                      <svg className="w-8 h-8 text-green-500" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M5 13l4 4L19 7" />
                      </svg>
                    </div>
                    <p className="text-lg font-semibold text-green-600">¡Pedido enviado!</p>
                    <p className="text-gray-500">La ronda fue enviada al Dashboard</p>
                  </div>
                ) : cart.length === 0 ? (
                  <div className="flex flex-col items-center justify-center h-full text-gray-400">
                    <svg className="w-16 h-16 mb-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M3 3h2l.4 2M7 13h10l4-8H5.4M7 13L5.4 5M7 13l-2.293 2.293c-.63.63-.184 1.707.707 1.707H17m0 0a2 2 0 100 4 2 2 0 000-4zm-8 2a2 2 0 11-4 0 2 2 0 014 0z" />
                    </svg>
                    <p>Selecciona productos de la izquierda</p>
                  </div>
                ) : (
                  <div className="space-y-3">
                    {cart.map((item) => (
                      <div
                        key={item.id}
                        className="bg-white p-4 border border-gray-200"
                      >
                        <div className="flex items-start justify-between">
                          <div className="flex-1">
                            <div className="flex items-center gap-2">
                              <span className="bg-orange-500 text-white text-sm font-bold px-2 py-0.5">
                                {item.qty}x
                              </span>
                              <span className="font-medium text-gray-900">{item.name}</span>
                            </div>
                            <p className="text-orange-600 font-semibold mt-1">
                              {formatPrice(item.price_cents * item.qty)}
                            </p>
                          </div>
                          <button
                            onClick={() => removeFromCart(item.id)}
                            className="p-2 text-gray-400 hover:text-red-500 hover:bg-red-50 transition-colors"
                          >
                            <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16" />
                            </svg>
                          </button>
                        </div>
                        {/* Quantity controls inline */}
                        <div className="flex items-center gap-2 mt-3">
                          <button
                            onClick={() => updateQuantity(item.id, -1)}
                            className="w-8 h-8 bg-gray-100 hover:bg-gray-200 flex items-center justify-center font-bold"
                          >
                            −
                          </button>
                          <span className="w-8 text-center font-medium">{item.qty}</span>
                          <button
                            onClick={() => updateQuantity(item.id, 1)}
                            className="w-8 h-8 bg-gray-100 hover:bg-gray-200 flex items-center justify-center font-bold"
                          >
                            +
                          </button>
                        </div>
                      </div>
                    ))}
                  </div>
                )}
              </div>

              {/* Cart footer with total and submit */}
              {cart.length > 0 && !submitSuccess && (
                <div className="p-4 border-t border-gray-200 bg-white">
                  <div className="flex justify-between items-center mb-4">
                    <span className="text-gray-600">Total</span>
                    <span className="text-2xl font-bold text-gray-900">{formatPrice(cartTotal)}</span>
                  </div>
                  <div className="flex gap-3">
                    <Button
                      variant="secondary"
                      onClick={clearCart}
                      className="flex-shrink-0"
                    >
                      Vaciar
                    </Button>
                    <Button
                      variant="primary"
                      onClick={handleSubmitRound}
                      disabled={isSubmitting}
                      className="flex-1"
                    >
                      {isSubmitting ? (
                        <span className="flex items-center justify-center gap-2">
                          <div className="animate-spin w-4 h-4 border-2 border-white border-t-transparent rounded-full" />
                          Enviando...
                        </span>
                      ) : (
                        'Cerrar Ronda'
                      )}
                    </Button>
                  </div>
                </div>
              )}
            </div>
          </div>
        )}
      </div>
    </div>
  )
}
