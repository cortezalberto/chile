type LogLevel = 'debug' | 'info' | 'warn' | 'error'

interface LogEntry {
  level: LogLevel
  context: string
  message: string
  data?: unknown
  timestamp: string
}

const isDev = import.meta.env.DEV

function formatLog(entry: LogEntry): string {
  const { level, context, message, timestamp } = entry
  return `[${timestamp}] [${level.toUpperCase()}] [${context}] ${message}`
}

function createLogger(context: string) {
  const log = (level: LogLevel, message: string, data?: unknown) => {
    const entry: LogEntry = {
      level,
      context,
      message,
      data,
      timestamp: new Date().toISOString(),
    }

    const formatted = formatLog(entry)

    switch (level) {
      case 'debug':
        if (isDev) console.debug(formatted, data ?? '')
        break
      case 'info':
        console.info(formatted, data ?? '')
        break
      case 'warn':
        console.warn(formatted, data ?? '')
        break
      case 'error':
        console.error(formatted, data ?? '')
        break
    }
  }

  return {
    debug: (message: string, data?: unknown) => log('debug', message, data),
    info: (message: string, data?: unknown) => log('info', message, data),
    warn: (message: string, data?: unknown) => log('warn', message, data),
    error: (message: string, data?: unknown) => log('error', message, data),
  }
}

// Pre-configured loggers
export const apiLogger = createLogger('API')
export const wsLogger = createLogger('WebSocket')
export const authLogger = createLogger('Auth')
export const storeLogger = createLogger('Store')
export const notificationLogger = createLogger('Notification')
