/**
 * PDF Export utility for Fiscal Invoice
 * Uses jspdf and html2canvas to generate PDF from HTML element
 */

import jsPDF from 'jspdf'
import html2canvas from 'html2canvas'
import type { FiscalInvoiceData } from '../types/fiscal'
import { formatInvoiceNumber } from '../types/fiscal'

export interface ExportPDFOptions {
  filename?: string
  quality?: number // 0-1, default 0.95
  scale?: number // default 2 for better quality
}

/**
 * Export an HTML element to PDF
 */
export async function exportElementToPDF(
  element: HTMLElement,
  options: ExportPDFOptions = {}
): Promise<void> {
  const { filename = 'documento.pdf', quality = 0.95, scale = 2 } = options

  try {
    // Capture element as canvas
    const canvas = await html2canvas(element, {
      scale,
      useCORS: true,
      logging: false,
      backgroundColor: '#ffffff',
    })

    // Calculate dimensions for A4
    const imgWidth = 210 // A4 width in mm
    const pageHeight = 297 // A4 height in mm
    const imgHeight = (canvas.height * imgWidth) / canvas.width

    // Create PDF
    const pdf = new jsPDF({
      orientation: imgHeight > pageHeight ? 'portrait' : 'portrait',
      unit: 'mm',
      format: 'a4',
    })

    // Add image to PDF
    const imgData = canvas.toDataURL('image/jpeg', quality)

    // If content is longer than one page, split it
    let heightLeft = imgHeight
    let position = 0

    pdf.addImage(imgData, 'JPEG', 0, position, imgWidth, imgHeight)
    heightLeft -= pageHeight

    while (heightLeft > 0) {
      position = heightLeft - imgHeight
      pdf.addPage()
      pdf.addImage(imgData, 'JPEG', 0, position, imgWidth, imgHeight)
      heightLeft -= pageHeight
    }

    // Save the PDF
    pdf.save(filename)
  } catch (error) {
    console.error('Error generating PDF:', error)
    throw new Error('No se pudo generar el PDF')
  }
}

/**
 * Generate filename for fiscal invoice
 */
export function generateInvoiceFilename(data: FiscalInvoiceData): string {
  const invoiceNum = formatInvoiceNumber(data.pointOfSale, data.invoiceNumber)
  const dateStr = data.issueDate.toISOString().split('T')[0]
  return `Factura_${data.invoiceType}_${invoiceNum}_${dateStr}.pdf`
}

/**
 * Export fiscal invoice data to PDF
 * This is a convenience wrapper that creates a temporary element
 */
export async function exportInvoiceToPDF(
  invoiceElement: HTMLElement,
  data: FiscalInvoiceData
): Promise<void> {
  const filename = generateInvoiceFilename(data)
  await exportElementToPDF(invoiceElement, { filename })
}
