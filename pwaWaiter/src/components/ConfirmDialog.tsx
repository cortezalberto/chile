import { useEffect, useRef, useCallback } from 'react'
import { Button } from './Button'

interface ConfirmDialogProps {
  isOpen: boolean
  title: string
  message: string
  confirmLabel?: string
  cancelLabel?: string
  variant?: 'primary' | 'danger'
  onConfirm: () => void
  onCancel: () => void
  // WAITER-PAGE-MED-02: Loading state for async confirm actions
  isLoading?: boolean
}

/**
 * PWAW-006: Confirmation dialog component
 * Used for destructive or important actions like marking rounds as served
 */
export function ConfirmDialog({
  isOpen,
  title,
  message,
  confirmLabel = 'Confirmar',
  cancelLabel = 'Cancelar',
  variant = 'primary',
  onConfirm,
  onCancel,
  isLoading = false,
}: ConfirmDialogProps) {
  const confirmButtonRef = useRef<HTMLButtonElement>(null)
  const cancelButtonRef = useRef<HTMLButtonElement>(null)
  const dialogRef = useRef<HTMLDivElement>(null)
  // WAITER-COMP-CRIT-01: Track previously focused element to restore on close
  const previousActiveElement = useRef<HTMLElement | null>(null)

  // Focus confirm button when dialog opens and restore focus on close
  useEffect(() => {
    if (isOpen) {
      // Store the currently focused element to restore later
      previousActiveElement.current = document.activeElement as HTMLElement | null
      // Focus confirm button after a short delay for animation
      const timer = setTimeout(() => {
        confirmButtonRef.current?.focus()
      }, 50)
      return () => clearTimeout(timer)
    } else {
      // Restore focus when dialog closes
      if (previousActiveElement.current && typeof previousActiveElement.current.focus === 'function') {
        previousActiveElement.current.focus()
        previousActiveElement.current = null
      }
    }
  }, [isOpen])

  // WAITER-COMP-CRIT-02 FIX: Focus trap within modal
  const handleKeyDown = useCallback((e: KeyboardEvent) => {
    if (e.key === 'Escape') {
      onCancel()
      return
    }

    // Focus trap: Tab should cycle through dialog buttons only
    if (e.key === 'Tab') {
      const focusableElements = [cancelButtonRef.current, confirmButtonRef.current].filter(Boolean) as HTMLElement[]
      if (focusableElements.length === 0) return

      const firstElement = focusableElements[0]
      const lastElement = focusableElements[focusableElements.length - 1]

      if (e.shiftKey) {
        // Shift+Tab: if on first element, go to last
        if (document.activeElement === firstElement) {
          e.preventDefault()
          lastElement.focus()
        }
      } else {
        // Tab: if on last element, go to first
        if (document.activeElement === lastElement) {
          e.preventDefault()
          firstElement.focus()
        }
      }
    }
  }, [onCancel])

  // Handle keyboard events
  useEffect(() => {
    if (!isOpen) return

    window.addEventListener('keydown', handleKeyDown)
    return () => window.removeEventListener('keydown', handleKeyDown)
  }, [isOpen, handleKeyDown])

  if (!isOpen) return null

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4">
      {/* Backdrop */}
      <div
        className="absolute inset-0 bg-black/60 backdrop-blur-sm"
        onClick={onCancel}
        aria-hidden="true"
      />

      {/* Dialog */}
      <div
        ref={dialogRef}
        className="relative bg-neutral-900 rounded-xl border border-neutral-800 p-6 max-w-sm w-full shadow-xl animate-slide-up"
        role="dialog"
        aria-modal="true"
        aria-labelledby="confirm-dialog-title"
      >
        <h2
          id="confirm-dialog-title"
          className="text-xl font-bold text-white mb-2"
        >
          {title}
        </h2>
        <p className="text-neutral-400 mb-6">{message}</p>

        <div className="flex gap-3">
          <Button
            ref={cancelButtonRef}
            variant="secondary"
            className="flex-1"
            onClick={onCancel}
            disabled={isLoading}
          >
            {cancelLabel}
          </Button>
          <Button
            ref={confirmButtonRef}
            variant={variant}
            className="flex-1"
            onClick={onConfirm}
            disabled={isLoading}
          >
            {isLoading ? 'Procesando...' : confirmLabel}
          </Button>
        </div>
      </div>
    </div>
  )
}
