// Storage keys for localStorage persistence
export const STORAGE_KEYS = {
  AUTH: 'waiter-auth',
  TABLES: 'waiter-tables',
  SETTINGS: 'waiter-settings',
} as const

// API configuration
export const API_CONFIG = {
  BASE_URL: import.meta.env.VITE_API_URL || 'http://localhost:8000/api',
  WS_URL: import.meta.env.VITE_WS_URL || 'ws://localhost:8001',
  TIMEOUT: 30000,
  // AUDIT FIX: SSRF protection - allowed hosts and ports
  ALLOWED_HOSTS: ['localhost', '127.0.0.1'] as readonly string[],
  ALLOWED_PORTS: ['80', '443', '8000', '8001', '5176', '5177', '5178'] as readonly string[],
} as const

// Table status display configuration (matches backend: FREE, ACTIVE, PAYING, OUT_OF_SERVICE)
export const TABLE_STATUS_CONFIG = {
  FREE: {
    label: 'Libre',
    color: 'bg-green-500',
    textColor: 'text-green-500',
    borderColor: 'border-green-500',
  },
  ACTIVE: {
    label: 'Ocupada',
    color: 'bg-red-500',
    textColor: 'text-red-500',
    borderColor: 'border-red-500',
  },
  PAYING: {
    label: 'Cuenta',
    color: 'bg-purple-500',
    textColor: 'text-purple-500',
    borderColor: 'border-purple-500',
  },
  OUT_OF_SERVICE: {
    label: 'Fuera de servicio',
    color: 'bg-gray-500',
    textColor: 'text-gray-500',
    borderColor: 'border-gray-500',
  },
} as const

// Round status display configuration
// Flow: PENDING → CONFIRMED → SUBMITTED → IN_KITCHEN → READY → SERVED
export const ROUND_STATUS_CONFIG = {
  PENDING: {
    label: 'Pendiente',
    color: 'bg-yellow-400',
    textColor: 'text-yellow-600',
  },
  CONFIRMED: {
    label: 'Confirmado',
    color: 'bg-blue-400',
    textColor: 'text-blue-600',
  },
  SUBMITTED: {
    label: 'Enviado',
    color: 'bg-yellow-500',
    textColor: 'text-yellow-500',
  },
  IN_KITCHEN: {
    label: 'En cocina',
    color: 'bg-orange-500',
    textColor: 'text-orange-500',
  },
  READY: {
    label: 'Listo',
    color: 'bg-green-500',
    textColor: 'text-green-500',
  },
  SERVED: {
    label: 'Servido',
    color: 'bg-gray-500',
    textColor: 'text-gray-500',
  },
} as const

// Order status display configuration (aggregate status for table cards)
// Matches Dashboard pattern for visual consistency
// Flow: pending → confirmed → submitted → in_kitchen → ready → served
export const ORDER_STATUS_CONFIG = {
  none: { label: '', color: '', textColor: '' },
  pending: { label: 'Pendiente', color: 'bg-yellow-400', textColor: 'text-black font-bold' },
  confirmed: { label: 'Confirmado', color: 'bg-blue-400', textColor: 'text-black font-bold' },
  submitted: { label: 'En Cocina', color: 'bg-blue-400', textColor: 'text-black font-bold' },
  in_kitchen: { label: 'En Cocina', color: 'bg-blue-400', textColor: 'text-black font-bold' },
  ready_with_kitchen: { label: 'Listo + Cocina', color: 'bg-orange-400', textColor: 'text-black font-bold' },
  ready: { label: 'Listo', color: 'bg-green-400', textColor: 'text-black font-bold' },
  served: { label: 'Servido', color: 'bg-gray-400', textColor: 'text-black font-bold' },
} as const

// Animation duration configuration (milliseconds)
export const ANIMATION_DURATIONS = {
  /** Blue blink for status changes */
  STATUS_BLINK: 1500,
  /** Red blink for service calls (longer to ensure waiter notices) */
  SERVICE_CALL_BLINK: 3000,
  /** Yellow pulse for new orders */
  NEW_ORDER_PULSE: 2000,
  /** Orange blink for ready + kitchen items */
  READY_KITCHEN_BLINK: 5000,
} as const

// WebSocket reconnection config
// WS-31-LOW-01: Keep these values synchronized with Dashboard/pwaMenu
export const WS_CONFIG = {
  RECONNECT_INTERVAL: 1000, // Base delay for exponential backoff (was 3000, now matches pwaMenu/Dashboard)
  MAX_RECONNECT_DELAY: 30000, // Maximum reconnect delay
  MAX_RECONNECT_ATTEMPTS: 10,
  HEARTBEAT_INTERVAL: 30000, // 30 seconds ping interval
  HEARTBEAT_TIMEOUT: 10000, // WS-31-HIGH-01 FIX: 10 seconds to receive pong
  JITTER_FACTOR: 0.3, // Add up to 30% random jitter
} as const

// MED-08 FIX: WebSocket event type constants to avoid magic strings
// These match the WSEventType union in types/index.ts
// Flow: PENDING → CONFIRMED → SUBMITTED → IN_KITCHEN → READY → SERVED
export const WS_EVENT_TYPES = {
  // Round events
  ROUND_PENDING: 'ROUND_PENDING',
  ROUND_CONFIRMED: 'ROUND_CONFIRMED',
  ROUND_SUBMITTED: 'ROUND_SUBMITTED',
  ROUND_IN_KITCHEN: 'ROUND_IN_KITCHEN',
  ROUND_READY: 'ROUND_READY',
  ROUND_SERVED: 'ROUND_SERVED',
  ROUND_ITEM_DELETED: 'ROUND_ITEM_DELETED',
  // Service call events
  SERVICE_CALL_CREATED: 'SERVICE_CALL_CREATED',
  SERVICE_CALL_ACKED: 'SERVICE_CALL_ACKED',
  SERVICE_CALL_CLOSED: 'SERVICE_CALL_CLOSED',
  // Check/payment events
  CHECK_REQUESTED: 'CHECK_REQUESTED',
  CHECK_PAID: 'CHECK_PAID',
  // Table events
  TABLE_CLEARED: 'TABLE_CLEARED',
  TABLE_SESSION_STARTED: 'TABLE_SESSION_STARTED',
  TABLE_STATUS_CHANGED: 'TABLE_STATUS_CHANGED',
  // Payment events
  PAYMENT_APPROVED: 'PAYMENT_APPROVED',
  PAYMENT_REJECTED: 'PAYMENT_REJECTED',
} as const

// MED-08 FIX: Events that trigger urgent notifications
export const URGENT_WS_EVENTS = [
  WS_EVENT_TYPES.SERVICE_CALL_CREATED,
  WS_EVENT_TYPES.CHECK_REQUESTED,
  WS_EVENT_TYPES.ROUND_READY,
] as const

// PWAW-L003: UI Configuration constants
export const UI_CONFIG = {
  /** Threshold in pixels for pull-to-refresh activation */
  PULL_TO_REFRESH_THRESHOLD: 80,
  /** Interval for automatic table list refresh (ms) */
  TABLE_REFRESH_INTERVAL: 60000,
  /** Maximum history entries to keep */
  MAX_HISTORY_ENTRIES: 50,
  /** Token refresh margin before expiry (seconds) */
  TOKEN_REFRESH_MARGIN: 60,
  /** Alert sound volume (0-1) */
  ALERT_SOUND_VOLUME: 0.5,
} as const
