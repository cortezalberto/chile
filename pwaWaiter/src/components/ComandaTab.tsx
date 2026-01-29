import { useState, useEffect, useCallback, useMemo } from 'react'
import { comandaAPI, waiterTableAPI } from '../services/api'
import type { MenuCompact, ProductCompact, WaiterRoundItem } from '../services/api'
import { Button } from './Button'
import { formatPrice } from '../utils/format'

interface ComandaTabProps {
  branchId: number
  sessionId: number
  onRoundSubmitted: () => void
}

interface CartItem extends ProductCompact {
  qty: number
  notes?: string
}

// COMANDA-001: ComandaTab component for waiter quick ordering
export function ComandaTab({ branchId, sessionId, onRoundSubmitted }: ComandaTabProps) {
  const [menu, setMenu] = useState<MenuCompact | null>(null)
  const [isLoadingMenu, setIsLoadingMenu] = useState(true)
  const [menuError, setMenuError] = useState<string | null>(null)

  // Cart state
  const [cart, setCart] = useState<CartItem[]>([])

  // Submission state
  const [isSubmitting, setIsSubmitting] = useState(false)

  // Category filter
  const [selectedCategory, setSelectedCategory] = useState<number | null>(null)

  // Search filter
  const [searchQuery, setSearchQuery] = useState('')

  // Load compact menu
  useEffect(() => {
    let isMounted = true

    async function loadMenu() {
      setIsLoadingMenu(true)
      setMenuError(null)
      try {
        const data = await comandaAPI.getMenuCompact(branchId)
        if (isMounted) {
          setMenu(data)
          // Auto-select first category
          if (data.categories.length > 0 && !selectedCategory) {
            setSelectedCategory(data.categories[0].id)
          }
        }
      } catch (err) {
        if (isMounted) {
          setMenuError('Error al cargar el menú')
          console.error('Failed to load compact menu:', err)
        }
      } finally {
        if (isMounted) {
          setIsLoadingMenu(false)
        }
      }
    }

    loadMenu()

    return () => {
      isMounted = false
    }
  }, [branchId])

  // Filter products by category and search
  const filteredProducts = useMemo(() => {
    if (!menu) return []

    let products: ProductCompact[] = []

    if (selectedCategory === null) {
      // Show all products
      products = menu.categories.flatMap((cat) => cat.products)
    } else {
      const category = menu.categories.find((cat) => cat.id === selectedCategory)
      products = category?.products || []
    }

    // Apply search filter
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

  // Add product to cart
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

  // Update item quantity
  const updateQuantity = useCallback((productId: number, delta: number) => {
    setCart((prev) => {
      return prev
        .map((item) => {
          if (item.id === productId) {
            const newQty = item.qty + delta
            return newQty > 0 ? { ...item, qty: newQty } : null
          }
          return item
        })
        .filter((item): item is CartItem => item !== null)
    })
  }, [])

  // Remove item from cart
  const removeFromCart = useCallback((productId: number) => {
    setCart((prev) => prev.filter((item) => item.id !== productId))
  }, [])

  // Clear cart
  const clearCart = useCallback(() => {
    setCart([])
  }, [])

  // Calculate cart total
  const cartTotal = useMemo(() => {
    return cart.reduce((sum, item) => sum + item.price_cents * item.qty, 0)
  }, [cart])

  // Submit round
  const handleSubmitRound = async () => {
    if (cart.length === 0) return

    setIsSubmitting(true)
    try {
      const items: WaiterRoundItem[] = cart.map((item) => ({
        product_id: item.id,
        qty: item.qty,
        notes: item.notes,
      }))

      await waiterTableAPI.submitRound(sessionId, { items })
      clearCart()
      onRoundSubmitted()
    } catch (err) {
      console.error('Failed to submit round:', err)
      // Could show error toast here
    } finally {
      setIsSubmitting(false)
    }
  }

  // Loading state
  if (isLoadingMenu) {
    return (
      <div className="flex justify-center py-12">
        <div className="animate-spin w-8 h-8 border-2 border-orange-500 border-t-transparent rounded-full" />
      </div>
    )
  }

  // Error state
  if (menuError || !menu) {
    return (
      <div className="text-center py-8">
        <p className="text-red-400 mb-4">{menuError || 'Error al cargar menú'}</p>
        <Button
          variant="secondary"
          onClick={() => window.location.reload()}
        >
          Reintentar
        </Button>
      </div>
    )
  }

  return (
    <div className="flex flex-col h-full">
      {/* Search bar */}
      <div className="mb-3">
        <input
          type="text"
          placeholder="Buscar producto..."
          value={searchQuery}
          onChange={(e) => setSearchQuery(e.target.value)}
          className="w-full bg-gray-100 border border-gray-200 px-3 py-2 text-gray-900 placeholder-gray-400 focus:outline-none focus:ring-2 focus:ring-orange-500"
        />
      </div>

      {/* Category tabs */}
      <div className="flex gap-2 overflow-x-auto pb-2 mb-3 scrollbar-hide">
        <button
          onClick={() => setSelectedCategory(null)}
          className={`flex-shrink-0 px-3 py-1.5 text-sm font-medium transition-colors ${
            selectedCategory === null
              ? 'bg-orange-500 text-gray-900'
              : 'bg-gray-100 text-gray-500 hover:bg-gray-200'
          }`}
        >
          Todos
        </button>
        {menu.categories.map((category) => (
          <button
            key={category.id}
            onClick={() => setSelectedCategory(category.id)}
            className={`flex-shrink-0 px-3 py-1.5 text-sm font-medium transition-colors ${
              selectedCategory === category.id
                ? 'bg-orange-500 text-gray-900'
                : 'bg-gray-100 text-gray-500 hover:bg-gray-200'
            }`}
          >
            {category.name}
            <span className="ml-1 text-xs opacity-70">
              ({category.products.length})
            </span>
          </button>
        ))}
      </div>

      {/* Product list */}
      <div className="flex-1 overflow-y-auto space-y-2 pb-2">
        {filteredProducts.length === 0 ? (
          <p className="text-gray-400 text-center py-8">
            No hay productos
          </p>
        ) : (
          filteredProducts.map((product) => {
            const cartItem = cart.find((c) => c.id === product.id)
            const qtyInCart = cartItem?.qty || 0

            return (
              <div
                key={product.id}
                className={`bg-gray-100 p-3 border transition-colors ${
                  qtyInCart > 0
                    ? 'border-orange-500/50'
                    : 'border-gray-200'
                } ${!product.is_available ? 'opacity-50' : ''}`}
              >
                <div className="flex items-start justify-between">
                  <div className="flex-1 min-w-0">
                    <div className="flex items-center gap-2">
                      <span className="text-gray-900 font-medium truncate">
                        {product.name}
                      </span>
                      {/* Allergen icons */}
                      {product.allergen_icons.length > 0 && (
                        <span className="text-sm">
                          {product.allergen_icons.slice(0, 3).join('')}
                          {product.allergen_icons.length > 3 && '...'}
                        </span>
                      )}
                    </div>
                    {product.description && (
                      <p className="text-gray-500 text-xs mt-0.5 line-clamp-1">
                        {product.description}
                      </p>
                    )}
                    <p className="text-orange-500 font-medium text-sm mt-1">
                      {formatPrice(product.price_cents)}
                    </p>
                  </div>

                  {/* Add/quantity controls */}
                  <div className="flex items-center gap-2 ml-2">
                    {qtyInCart > 0 ? (
                      <div className="flex items-center gap-1 bg-gray-200">
                        <button
                          onClick={() => updateQuantity(product.id, -1)}
                          className="px-2 py-1 text-gray-900 hover:bg-gray-300 transition-colors"
                        >
                          −
                        </button>
                        <span className="px-2 text-gray-900 font-medium min-w-[24px] text-center">
                          {qtyInCart}
                        </span>
                        <button
                          onClick={() => updateQuantity(product.id, 1)}
                          className="px-2 py-1 text-gray-900 hover:bg-gray-300 transition-colors"
                          disabled={!product.is_available}
                        >
                          +
                        </button>
                      </div>
                    ) : (
                      <button
                        onClick={() => addToCart(product)}
                        disabled={!product.is_available}
                        className="bg-orange-500 hover:bg-orange-600 disabled:bg-gray-200 disabled:text-gray-400 text-gray-900 px-3 py-1 font-medium transition-colors"
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

      {/* Cart summary and submit button (sticky bottom) */}
      {cart.length > 0 && (
        <div className="sticky bottom-0 bg-white border-t border-gray-200 pt-3 -mx-4 px-4 pb-4">
          {/* Cart items preview */}
          <div className="mb-3 max-h-24 overflow-y-auto">
            {cart.map((item) => (
              <div
                key={item.id}
                className="flex items-center justify-between text-sm py-1"
              >
                <div className="flex items-center gap-2 flex-1 min-w-0">
                  <span className="text-orange-500 font-medium">
                    {item.qty}x
                  </span>
                  <span className="text-gray-900 truncate">{item.name}</span>
                </div>
                <div className="flex items-center gap-2">
                  <span className="text-gray-500">
                    {formatPrice(item.price_cents * item.qty)}
                  </span>
                  <button
                    onClick={() => removeFromCart(item.id)}
                    className="text-gray-400 hover:text-red-500 transition-colors"
                    aria-label={`Eliminar ${item.name}`}
                  >
                    ×
                  </button>
                </div>
              </div>
            ))}
          </div>

          {/* Total and submit */}
          <div className="flex items-center justify-between mb-3">
            <span className="text-gray-500">
              {cart.reduce((sum, item) => sum + item.qty, 0)} items
            </span>
            <span className="text-xl font-bold text-gray-900">
              {formatPrice(cartTotal)}
            </span>
          </div>

          <div className="flex gap-2">
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
              disabled={isSubmitting || cart.length === 0}
              className="flex-1"
            >
              {isSubmitting ? 'Enviando...' : 'Enviar Comanda'}
            </Button>
          </div>
        </div>
      )}
    </div>
  )
}
