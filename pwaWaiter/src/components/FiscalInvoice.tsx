/**
 * FiscalInvoice - Argentine AFIP Fiscal Invoice Simulation
 *
 * Displays a fiscal invoice in AFIP format with:
 * - Business header with CUIT, tax condition
 * - Invoice type (A/B/C) and number
 * - Items with quantities and prices
 * - IVA breakdown
 * - CAE and QR code (simulated)
 */

import { forwardRef } from 'react'
import type {
  FiscalInvoiceData,
  InvoiceType,
} from '../types/fiscal'
import {
  formatCuit,
  formatInvoiceNumber,
  getInvoiceTypeDescription,
  getTaxConditionDescription,
  getPaymentMethodDescription,
} from '../types/fiscal'

interface FiscalInvoiceProps {
  data: FiscalInvoiceData
  showQR?: boolean
}

// Format date as DD/MM/YYYY
function formatDate(date: Date): string {
  return date.toLocaleDateString('es-AR', {
    day: '2-digit',
    month: '2-digit',
    year: 'numeric',
  })
}

// Format currency
function formatCurrency(cents: number): string {
  return (cents / 100).toLocaleString('es-AR', {
    style: 'currency',
    currency: 'ARS',
  })
}

// Invoice type letter badge
function InvoiceTypeBadge({ type }: { type: InvoiceType }) {
  return (
    <div className="w-16 h-16 border-2 border-black flex items-center justify-center">
      <span className="text-4xl font-bold">{type}</span>
    </div>
  )
}

// QR Code placeholder (in real app, use a QR library)
function QRCodePlaceholder({ data }: { data: string }) {
  return (
    <div className="w-24 h-24 border border-gray-400 flex items-center justify-center bg-white">
      <div className="text-center">
        <svg
          className="w-16 h-16 mx-auto text-gray-600"
          fill="currentColor"
          viewBox="0 0 24 24"
        >
          <path d="M3 3h6v6H3V3zm2 2v2h2V5H5zm8-2h6v6h-6V3zm2 2v2h2V5h-2zM3 13h6v6H3v-6zm2 2v2h2v-2H5zm13-2h1v1h-1v-1zm-2 0h1v1h-1v-1zm-2 0h1v1h-1v-1zm4 2h1v1h-1v-1zm-2 0h1v1h-1v-1zm-2 0h1v1h-1v-1zm4 2h1v1h-1v-1zm-2 0h1v1h-1v-1zm-2 0h1v1h-1v-1zm4 2h1v1h-1v-1zm-2 0h1v1h-1v-1zm-2 0h1v1h-1v-1z" />
        </svg>
        <span className="text-xs text-gray-500">QR AFIP</span>
      </div>
    </div>
  )
}

export const FiscalInvoice = forwardRef<HTMLDivElement, FiscalInvoiceProps>(
  function FiscalInvoice({ data, showQR = true }, ref) {
    const {
      invoiceType,
      pointOfSale,
      invoiceNumber,
      issueDate,
      business,
      customer,
      items,
      subtotal,
      ivaAmount,
      ivaRate,
      total,
      paymentMethod,
      cae,
      caeExpiration,
      qrData,
      tableCode,
      waiterName,
    } = data

    return (
      <div
        ref={ref}
        className="bg-white text-black p-6 max-w-[210mm] mx-auto font-mono text-sm"
        style={{ minHeight: '297mm' }}
      >
        {/* Header with logo area and invoice type */}
        <div className="border-2 border-black">
          {/* Top section: Business info and Invoice type */}
          <div className="flex">
            {/* Left: Business info */}
            <div className="flex-1 p-4 border-r-2 border-black">
              <h1 className="text-xl font-bold">{business.name}</h1>
              {business.fantasyName && (
                <p className="text-lg">{business.fantasyName}</p>
              )}
              <p className="mt-2">{business.address}</p>
              <p>
                {business.city}, {business.province} ({business.postalCode})
              </p>
              {business.phone && <p>Tel: {business.phone}</p>}
              {business.email && <p>Email: {business.email}</p>}
            </div>

            {/* Center: Invoice type */}
            <div className="flex flex-col items-center justify-center px-6 border-r-2 border-black">
              <InvoiceTypeBadge type={invoiceType} />
              <p className="text-xs mt-1 text-center">
                COD. {invoiceType === 'A' ? '01' : invoiceType === 'B' ? '06' : '11'}
              </p>
            </div>

            {/* Right: Invoice details */}
            <div className="flex-1 p-4">
              <h2 className="text-lg font-bold">
                {getInvoiceTypeDescription(invoiceType)}
              </h2>
              <p className="text-xl font-bold mt-2">
                Nº {formatInvoiceNumber(pointOfSale, invoiceNumber)}
              </p>
              <p className="mt-2">
                <span className="font-semibold">Fecha:</span> {formatDate(issueDate)}
              </p>
              <p>
                <span className="font-semibold">CUIT:</span> {formatCuit(business.cuit)}
              </p>
              <p>
                <span className="font-semibold">IIBB:</span> {business.grossIncome}
              </p>
              <p className="text-xs mt-1">
                Inicio Act.: {business.activityStartDate}
              </p>
            </div>
          </div>

          {/* Tax condition row */}
          <div className="border-t-2 border-black p-2 text-center bg-gray-100">
            <p className="font-semibold">
              {getTaxConditionDescription(business.taxCondition)}
            </p>
          </div>
        </div>

        {/* Customer info (for type A invoices) */}
        <div className="border-x-2 border-b-2 border-black p-3">
          <div className="grid grid-cols-2 gap-4">
            <div>
              <p>
                <span className="font-semibold">CLIENTE:</span>{' '}
                {customer?.name || 'CONSUMIDOR FINAL'}
              </p>
              {customer?.cuit && (
                <p>
                  <span className="font-semibold">CUIT:</span>{' '}
                  {formatCuit(customer.cuit)}
                </p>
              )}
            </div>
            <div>
              <p>
                <span className="font-semibold">Condición IVA:</span>{' '}
                {customer
                  ? getTaxConditionDescription(customer.taxCondition)
                  : 'Consumidor Final'}
              </p>
              {customer?.address && (
                <p>
                  <span className="font-semibold">Domicilio:</span>{' '}
                  {customer.address}
                </p>
              )}
            </div>
          </div>
          {tableCode && (
            <p className="mt-2 text-gray-600">
              <span className="font-semibold">Mesa:</span> {tableCode}
              {waiterName && <span> | Atendido por: {waiterName}</span>}
            </p>
          )}
        </div>

        {/* Items table */}
        <div className="border-x-2 border-b-2 border-black">
          <table className="w-full">
            <thead>
              <tr className="bg-gray-200 border-b-2 border-black">
                <th className="text-left p-2 border-r border-black w-16">Cant.</th>
                <th className="text-left p-2 border-r border-black">Descripción</th>
                <th className="text-right p-2 border-r border-black w-28">P. Unit.</th>
                <th className="text-right p-2 w-28">Subtotal</th>
              </tr>
            </thead>
            <tbody>
              {items.map((item, index) => (
                <tr key={index} className="border-b border-gray-300">
                  <td className="p-2 border-r border-gray-300 text-center">
                    {item.quantity}
                  </td>
                  <td className="p-2 border-r border-gray-300">{item.description}</td>
                  <td className="p-2 border-r border-gray-300 text-right">
                    {formatCurrency(item.unitPrice)}
                  </td>
                  <td className="p-2 text-right">{formatCurrency(item.total)}</td>
                </tr>
              ))}
              {/* Empty rows to fill space */}
              {items.length < 5 &&
                Array.from({ length: 5 - items.length }).map((_, i) => (
                  <tr key={`empty-${i}`} className="border-b border-gray-300">
                    <td className="p-2 border-r border-gray-300">&nbsp;</td>
                    <td className="p-2 border-r border-gray-300">&nbsp;</td>
                    <td className="p-2 border-r border-gray-300">&nbsp;</td>
                    <td className="p-2">&nbsp;</td>
                  </tr>
                ))}
            </tbody>
          </table>
        </div>

        {/* Totals */}
        <div className="border-x-2 border-b-2 border-black">
          <div className="flex">
            {/* Payment info */}
            <div className="flex-1 p-3 border-r-2 border-black">
              <p>
                <span className="font-semibold">Forma de Pago:</span>{' '}
                {getPaymentMethodDescription(paymentMethod)}
              </p>
            </div>

            {/* Totals column */}
            <div className="w-64 p-3">
              <div className="space-y-1">
                <div className="flex justify-between">
                  <span>Subtotal:</span>
                  <span>{formatCurrency(subtotal)}</span>
                </div>
                {invoiceType !== 'C' && (
                  <div className="flex justify-between">
                    <span>IVA ({ivaRate}%):</span>
                    <span>{formatCurrency(ivaAmount)}</span>
                  </div>
                )}
                <div className="flex justify-between font-bold text-lg border-t border-black pt-2 mt-2">
                  <span>TOTAL:</span>
                  <span>{formatCurrency(total)}</span>
                </div>
              </div>
            </div>
          </div>
        </div>

        {/* CAE and QR section */}
        <div className="border-x-2 border-b-2 border-black p-4">
          <div className="flex items-start justify-between">
            <div>
              <p className="font-semibold">CAE Nº: {cae || '00000000000000'}</p>
              <p>
                Vto. CAE:{' '}
                {caeExpiration
                  ? formatDate(caeExpiration)
                  : formatDate(new Date(Date.now() + 10 * 24 * 60 * 60 * 1000))}
              </p>
            </div>
            {showQR && <QRCodePlaceholder data={qrData || ''} />}
          </div>
        </div>

        {/* Footer */}
        <div className="mt-4 text-center text-xs text-gray-500">
          <p>Este documento es una simulación de factura fiscal</p>
          <p>No tiene validez tributaria</p>
          <p className="mt-2">
            Comprobante generado por Sistema de Gestión de Restaurante
          </p>
        </div>
      </div>
    )
  }
)
