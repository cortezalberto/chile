/**
 * FiscalInvoiceModal - Modal to preview and export fiscal invoice
 */

import { useState, useRef, useCallback, useMemo } from 'react'
import { FiscalInvoice } from './FiscalInvoice'
import { Button } from './Button'
import { exportInvoiceToPDF } from '../utils/pdfExport'
import type { FiscalInvoiceData, InvoiceItem, PaymentMethod } from '../types/fiscal'
import { generateMockCAE, generateAFIPQRData } from '../types/fiscal'
import type { TableSessionDetail, RoundItemDetail } from '../types'

interface FiscalInvoiceModalProps {
  isOpen: boolean
  onClose: () => void
  sessionDetail: TableSessionDetail | null
  tableCode: string
  waiterName?: string
}

// Default business data (simulation)
const DEFAULT_BUSINESS = {
  name: 'RESTAURANTE DEMO S.R.L.',
  fantasyName: 'El Buen Sabor',
  cuit: '30123456789',
  taxCondition: 'RESPONSABLE_INSCRIPTO' as const,
  grossIncome: '901-123456-7',
  activityStartDate: '01/01/2020',
  address: 'Av. Corrientes 1234, Piso 1',
  city: 'Ciudad Autónoma de Buenos Aires',
  province: 'Buenos Aires',
  postalCode: '1043',
  phone: '(011) 4123-4567',
  email: 'contacto@elbuensabor.com.ar',
}

// Convert session items to invoice items
function sessionToInvoiceItems(sessionDetail: TableSessionDetail): InvoiceItem[] {
  const items: InvoiceItem[] = []
  const itemMap = new Map<string, InvoiceItem>()

  // Aggregate items across all rounds
  for (const round of sessionDetail.rounds) {
    for (const item of round.items) {
      const key = `${item.product_id}-${item.unit_price_cents}`
      const existing = itemMap.get(key)

      if (existing) {
        existing.quantity += item.qty
        existing.total += item.unit_price_cents * item.qty
      } else {
        itemMap.set(key, {
          quantity: item.qty,
          description: item.product_name,
          unitPrice: item.unit_price_cents,
          total: item.unit_price_cents * item.qty,
        })
      }
    }
  }

  // Convert map to array and sort by description
  items.push(...itemMap.values())
  items.sort((a, b) => a.description.localeCompare(b.description))

  return items
}

// Determine payment method from session (simplified)
function getPaymentMethod(): PaymentMethod {
  // In a real implementation, this would come from the payment data
  return 'EFECTIVO'
}

export function FiscalInvoiceModal({
  isOpen,
  onClose,
  sessionDetail,
  tableCode,
  waiterName,
}: FiscalInvoiceModalProps) {
  const invoiceRef = useRef<HTMLDivElement>(null)
  const [isExporting, setIsExporting] = useState(false)
  const [exportError, setExportError] = useState<string | null>(null)

  // Generate invoice data from session
  const invoiceData: FiscalInvoiceData | null = useMemo(() => {
    if (!sessionDetail) return null

    const items = sessionToInvoiceItems(sessionDetail)
    const subtotal = items.reduce((sum, item) => sum + item.total, 0)
    const ivaRate = 21
    // For Factura B to consumidor final, IVA is included in price
    const ivaAmount = Math.round(subtotal * (ivaRate / (100 + ivaRate)))
    const total = subtotal

    const cae = generateMockCAE()
    const caeExpiration = new Date(Date.now() + 10 * 24 * 60 * 60 * 1000) // 10 days

    const data: FiscalInvoiceData = {
      invoiceType: 'B', // Factura B for consumidor final
      pointOfSale: 1,
      invoiceNumber: sessionDetail.session_id,
      issueDate: new Date(),
      business: DEFAULT_BUSINESS,
      customer: {
        name: 'CONSUMIDOR FINAL',
        taxCondition: 'CONSUMIDOR_FINAL',
      },
      items,
      subtotal,
      ivaAmount,
      ivaRate,
      total,
      paymentMethod: getPaymentMethod(),
      cae,
      caeExpiration,
      tableCode,
      waiterName,
      sessionId: sessionDetail.session_id,
    }

    // Generate QR data
    data.qrData = generateAFIPQRData(data)

    return data
  }, [sessionDetail, tableCode, waiterName])

  // Handle PDF export
  const handleExportPDF = useCallback(async () => {
    if (!invoiceRef.current || !invoiceData) return

    setIsExporting(true)
    setExportError(null)

    try {
      await exportInvoiceToPDF(invoiceRef.current, invoiceData)
    } catch (error) {
      console.error('Export error:', error)
      setExportError('Error al exportar PDF. Intente nuevamente.')
    } finally {
      setIsExporting(false)
    }
  }, [invoiceData])

  if (!isOpen) return null

  return (
    <div className="fixed inset-0 z-[60] flex items-center justify-center p-4">
      {/* Backdrop */}
      <div
        className="absolute inset-0 bg-black/80 backdrop-blur-sm"
        onClick={onClose}
        aria-hidden="true"
      />

      {/* Modal */}
      <div className="relative bg-gray-100 w-full max-w-4xl max-h-[95vh] overflow-hidden shadow-2xl flex flex-col">
        {/* Header */}
        <div className="flex items-center justify-between p-4 bg-white border-b border-gray-200">
          <div>
            <h2 className="text-xl font-bold text-gray-900">
              Factura Fiscal (Simulación)
            </h2>
            <p className="text-sm text-gray-500">
              Vista previa - Formato AFIP Argentina
            </p>
          </div>
          <button
            onClick={onClose}
            className="p-2 text-gray-400 hover:text-gray-900 hover:bg-gray-100 transition-colors rounded"
            aria-label="Cerrar"
          >
            <svg className="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
            </svg>
          </button>
        </div>

        {/* Content - scrollable invoice preview */}
        <div className="flex-1 overflow-y-auto p-4">
          {invoiceData ? (
            <div className="shadow-lg">
              <FiscalInvoice ref={invoiceRef} data={invoiceData} showQR={true} />
            </div>
          ) : (
            <div className="flex items-center justify-center py-12">
              <p className="text-gray-500">No hay datos para generar la factura</p>
            </div>
          )}
        </div>

        {/* Footer with actions */}
        <div className="p-4 bg-white border-t border-gray-200 space-y-3">
          {exportError && (
            <div className="p-3 bg-red-50 border border-red-200 rounded text-red-700 text-sm">
              {exportError}
            </div>
          )}

          <div className="flex gap-3">
            <Button
              variant="secondary"
              className="flex-1"
              onClick={onClose}
            >
              Cerrar
            </Button>
            <Button
              variant="primary"
              className="flex-1"
              onClick={handleExportPDF}
              disabled={isExporting || !invoiceData}
            >
              {isExporting ? (
                <span className="flex items-center justify-center gap-2">
                  <svg className="animate-spin w-5 h-5" fill="none" viewBox="0 0 24 24">
                    <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
                    <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z" />
                  </svg>
                  Generando...
                </span>
              ) : (
                <span className="flex items-center justify-center gap-2">
                  <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 10v6m0 0l-3-3m3 3l3-3m2 8H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z" />
                  </svg>
                  Exportar PDF
                </span>
              )}
            </Button>
          </div>

          <p className="text-xs text-center text-gray-400">
            Este documento es una simulación y no tiene validez fiscal
          </p>
        </div>
      </div>
    </div>
  )
}
