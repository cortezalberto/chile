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
export const ROUND_STATUS_CONFIG = {
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

// WebSocket reconnection config
export const WS_CONFIG = {
  RECONNECT_INTERVAL: 3000,
  MAX_RECONNECT_ATTEMPTS: 10,
  HEARTBEAT_INTERVAL: 30000,
} as const

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
