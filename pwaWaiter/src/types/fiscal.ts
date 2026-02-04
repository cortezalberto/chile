/**
 * Types for Argentine Fiscal Invoice (AFIP format)
 */

// Invoice type per AFIP regulations
export type InvoiceType = 'A' | 'B' | 'C'

// Tax condition of the issuer
export type TaxCondition =
  | 'RESPONSABLE_INSCRIPTO'
  | 'MONOTRIBUTO'
  | 'EXENTO'
  | 'CONSUMIDOR_FINAL'

// Payment method
export type PaymentMethod =
  | 'EFECTIVO'
  | 'TARJETA_DEBITO'
  | 'TARJETA_CREDITO'
  | 'TRANSFERENCIA'
  | 'MERCADO_PAGO'
  | 'OTROS'

// Invoice item
export interface InvoiceItem {
  quantity: number
  description: string
  unitPrice: number // in cents
  total: number // in cents
}

// Business/issuer data
export interface BusinessData {
  name: string
  fantasyName?: string
  cuit: string
  taxCondition: TaxCondition
  grossIncome: string // Ingresos Brutos number
  activityStartDate: string // Inicio de actividades
  address: string
  city: string
  province: string
  postalCode: string
  phone?: string
  email?: string
}

// Invoice data
export interface FiscalInvoiceData {
  // Header
  invoiceType: InvoiceType
  pointOfSale: number // Punto de venta (4 digits)
  invoiceNumber: number // Número de comprobante (8 digits)
  issueDate: Date

  // Business data
  business: BusinessData

  // Customer data (for type A invoices)
  customer?: {
    name: string
    cuit?: string
    taxCondition: TaxCondition
    address?: string
  }

  // Items
  items: InvoiceItem[]

  // Totals
  subtotal: number // in cents
  ivaAmount: number // in cents (21% default)
  ivaRate: number // 21, 10.5, 27, etc.
  otherTaxes?: number // in cents
  total: number // in cents

  // Payment
  paymentMethod: PaymentMethod
  paymentDetails?: string

  // AFIP validation
  cae?: string // Código de Autorización Electrónico
  caeExpiration?: Date

  // QR code data (AFIP format)
  qrData?: string

  // Additional info
  tableCode?: string
  sessionId?: number
  waiterName?: string
}

// Helper to format CUIT: XX-XXXXXXXX-X
export function formatCuit(cuit: string): string {
  const clean = cuit.replace(/\D/g, '')
  if (clean.length !== 11) return cuit
  return `${clean.slice(0, 2)}-${clean.slice(2, 10)}-${clean.slice(10)}`
}

// Helper to format invoice number: 0001-00000001
export function formatInvoiceNumber(pointOfSale: number, invoiceNumber: number): string {
  const pos = pointOfSale.toString().padStart(4, '0')
  const num = invoiceNumber.toString().padStart(8, '0')
  return `${pos}-${num}`
}

// Helper to get invoice type description
export function getInvoiceTypeDescription(type: InvoiceType): string {
  const descriptions: Record<InvoiceType, string> = {
    A: 'FACTURA A',
    B: 'FACTURA B',
    C: 'FACTURA C',
  }
  return descriptions[type]
}

// Helper to get tax condition description
export function getTaxConditionDescription(condition: TaxCondition): string {
  const descriptions: Record<TaxCondition, string> = {
    RESPONSABLE_INSCRIPTO: 'IVA Responsable Inscripto',
    MONOTRIBUTO: 'Responsable Monotributo',
    EXENTO: 'IVA Exento',
    CONSUMIDOR_FINAL: 'Consumidor Final',
  }
  return descriptions[condition]
}

// Helper to get payment method description
export function getPaymentMethodDescription(method: PaymentMethod): string {
  const descriptions: Record<PaymentMethod, string> = {
    EFECTIVO: 'Efectivo',
    TARJETA_DEBITO: 'Tarjeta de Débito',
    TARJETA_CREDITO: 'Tarjeta de Crédito',
    TRANSFERENCIA: 'Transferencia Bancaria',
    MERCADO_PAGO: 'Mercado Pago',
    OTROS: 'Otros',
  }
  return descriptions[method]
}

// Generate mock CAE for simulation
export function generateMockCAE(): string {
  const random = Math.floor(Math.random() * 10000000000000000)
  return random.toString().padStart(14, '0')
}

// Generate AFIP QR data (simplified simulation)
export function generateAFIPQRData(invoice: FiscalInvoiceData): string {
  const data = {
    ver: 1,
    fecha: invoice.issueDate.toISOString().split('T')[0],
    cuit: invoice.business.cuit.replace(/\D/g, ''),
    ptoVta: invoice.pointOfSale,
    tipoCmp: invoice.invoiceType === 'A' ? 1 : invoice.invoiceType === 'B' ? 6 : 11,
    nroCmp: invoice.invoiceNumber,
    importe: invoice.total / 100,
    moneda: 'PES',
    ctz: 1,
    tipoDocRec: 99, // Sin identificar
    nroDocRec: 0,
    tipoCodAut: 'E',
    codAut: invoice.cae || generateMockCAE(),
  }

  // In real implementation, this would be base64 encoded
  return `https://www.afip.gob.ar/fe/qr/?p=${btoa(JSON.stringify(data))}`
}
