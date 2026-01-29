// User types
export interface User {
  id: number
  email: string
  tenant_id: number
  branch_ids: number[]
  roles: UserRole[]
}

export type UserRole = 'ADMIN' | 'MANAGER' | 'WAITER' | 'KITCHEN'

// Table types - matches backend TableStatus
export type TableStatus = 'FREE' | 'ACTIVE' | 'PAYING' | 'OUT_OF_SERVICE'

// Order status for visual display (aggregate status of all rounds)
export type OrderStatus = 'none' | 'pending' | 'submitted' | 'in_kitchen' | 'ready' | 'ready_with_kitchen' | 'served'

// TableCard from /api/waiter/tables endpoint
export interface TableCard {
  table_id: number
  code: string
  status: TableStatus
  session_id: number | null
  open_rounds: number
  pending_calls: number
  check_status: CheckStatus | null
  // Animation and order status tracking
  orderStatus?: OrderStatus                    // Aggregate order status for badge display
  roundStatuses?: Record<string, OrderStatus>  // Per-round status tracking
  statusChanged?: boolean                      // Triggers blue blink animation
  hasNewOrder?: boolean                        // Triggers yellow pulse animation
  hasServiceCall?: boolean                     // Triggers red blink animation (service call)
  // QA-FIX: Track active service call IDs for resolution from UI
  activeServiceCallIds?: number[]              // IDs of active (OPEN) service calls
}

// Check status
export type CheckStatus = 'OPEN' | 'REQUESTED' | 'IN_PAYMENT' | 'PAID' | 'FAILED'

// Round types
export type RoundStatus = 'PENDING' | 'SUBMITTED' | 'IN_KITCHEN' | 'READY' | 'SERVED'

export interface Round {
  id: number
  session_id: number
  round_number: number
  status: RoundStatus
  submitted_at: string
  items: RoundItem[]
}

export interface RoundItem {
  id: number
  round_id: number
  product_id: number
  product_name: string
  quantity: number
  unit_price_cents: number
  notes: string | null
}

// Detailed types for session view
export interface Diner {
  id: number
  session_id: number
  name: string
  color: string
  local_id: string | null
  joined_at: string
}

export interface RoundItemDetail {
  id: number
  product_id: number
  product_name: string
  category_name: string | null
  qty: number
  unit_price_cents: number
  notes: string | null
  diner_id: number | null
  diner_name: string | null
  diner_color: string | null
}

export interface RoundDetail {
  id: number
  round_number: number
  status: RoundStatus
  created_at: string
  submitted_at: string | null
  items: RoundItemDetail[]
}

export type SessionStatus = 'OPEN' | 'PAYING' | 'CLOSED'

export interface TableSessionDetail {
  session_id: number
  table_id: number
  table_code: string
  status: SessionStatus
  opened_at: string
  diners: Diner[]
  rounds: RoundDetail[]
  check_status: CheckStatus | null
  total_cents: number
  paid_cents: number
}

// Billing types
export interface Check {
  id: number
  session_id: number
  total_cents: number
  paid_cents: number
  requested_at: string
  closed_at: string | null
  payments: Payment[]
}

export interface Payment {
  id: number
  check_id: number
  amount_cents: number
  method: 'CASH' | 'MERCADOPAGO'
  reference: string | null
  created_at: string
}

// Service call types - matches backend ServiceCallType/Status
export type ServiceCallType = 'WAITER_CALL' | 'PAYMENT_HELP' | 'OTHER'
export type ServiceCallStatus = 'OPEN' | 'ACKED' | 'CLOSED'

export interface ServiceCall {
  id: number
  type: ServiceCallType
  status: ServiceCallStatus
  created_at: string
  acked_by_user_id: number | null
}

/**
 * PWAW-L002: WebSocket Event Types
 *
 * Events received from the WebSocket Gateway for real-time updates.
 * These events are published by the backend when state changes occur.
 */
export type WSEventType =
  /** New order round created by diner (pending manager approval) */
  | 'ROUND_PENDING'
  /** New order round submitted by diner */
  | 'ROUND_SUBMITTED'
  /** Round acknowledged by kitchen and being prepared */
  | 'ROUND_IN_KITCHEN'
  /** Round is ready to be served */
  | 'ROUND_READY'
  /** Round has been served to the table */
  | 'ROUND_SERVED'
  /** Diner pressed the "call waiter" button */
  | 'SERVICE_CALL_CREATED'
  /** Waiter acknowledged the service call */
  | 'SERVICE_CALL_ACKED'
  /** Service call has been resolved/closed */
  | 'SERVICE_CALL_CLOSED'
  /** Diner requested the bill/check */
  | 'CHECK_REQUESTED'
  /** Payment completed, check is fully paid */
  | 'CHECK_PAID'
  /** Table session closed and table is free */
  | 'TABLE_CLEARED'
  /** New session started (diner scanned QR) */
  | 'TABLE_SESSION_STARTED'
  /** Table status changed (for any reason) */
  | 'TABLE_STATUS_CHANGED'
  /** Payment was approved (for partial payments) */
  | 'PAYMENT_APPROVED'
  /** Payment was rejected */
  | 'PAYMENT_REJECTED'

/**
 * PWAW-L002: WebSocket Event Structure
 *
 * Standard format for all events from the WebSocket Gateway.
 * The `entity` field contains event-specific data.
 */
export interface WSEvent {
  /** Event type identifier - determines how to process the event */
  type: WSEventType
  /** Branch where the event occurred - for multi-branch filtering
   * QA-WAITER-HIGH-02 FIX: Made optional as some events (like broadcast) may not have branch_id
   */
  branch_id?: number
  /** Table that triggered the event
   * QA-WAITER-HIGH-02 FIX: Made optional as some events may not have table_id
   */
  table_id?: number
  /** Session ID, present for session-related events */
  session_id?: number
  /** Event-specific payload - structure varies by event type */
  entity?: {
    /** Round ID - for ROUND_* events */
    round_id?: number
    /** Round number within session - for ROUND_* events */
    round_number?: number
    /** Service call ID - for SERVICE_CALL_* events */
    call_id?: number
    /** Type of service call (WAITER_CALL, PAYMENT_HELP, OTHER) */
    call_type?: string
    /** Check ID - for CHECK_* and PAYMENT_* events */
    check_id?: number
    /** Total amount in cents - for CHECK_* events */
    total_cents?: number
    /** Amount already paid in cents - for CHECK_* events */
    paid_cents?: number
    /** Payment ID - for PAYMENT_* events */
    payment_id?: number
    /** Payment amount in cents - for PAYMENT_* events */
    amount_cents?: number
    /** Payment provider (CASH, MERCADOPAGO) - for PAYMENT_* events */
    provider?: string
    /** Table display code - for TABLE_* events */
    table_code?: string
  }
  /** @deprecated Use entity.round_id instead */
  round_id?: number
  /** @deprecated Use entity.call_id instead */
  service_call_id?: number
  /** @deprecated Legacy data field */
  data?: unknown
  /** @deprecated Use timestamp instead */
  ts?: string
  /** ISO timestamp when event was created */
  timestamp?: string
}

// API response types
export interface LoginResponse {
  access_token: string
  token_type: string
  expires_in: number
  user: User
}
