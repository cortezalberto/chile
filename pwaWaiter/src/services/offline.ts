import type { TableCard } from '../types'

// IndexedDB configuration
const DB_NAME = 'pwaWaiter'
const DB_VERSION = 1
const TABLES_STORE = 'tables'
const QUEUE_STORE = 'actionQueue'

// Action types that can be queued for offline processing
export type QueuedActionType = 'MARK_SERVED' | 'ACKNOWLEDGE_CALL' | 'RESOLVE_CALL'

export interface QueuedAction {
  id: string
  type: QueuedActionType
  payload: Record<string, unknown>
  timestamp: number
  retryCount: number
}

// Logger for offline service
const log = {
  info: (msg: string, data?: unknown) => {
    const formatted = `[${new Date().toISOString()}] [INFO] [Offline] ${msg}`
    console.info(formatted, data ?? '')
  },
  warn: (msg: string, data?: unknown) => {
    const formatted = `[${new Date().toISOString()}] [WARN] [Offline] ${msg}`
    console.warn(formatted, data ?? '')
  },
  error: (msg: string, data?: unknown) => {
    const formatted = `[${new Date().toISOString()}] [ERROR] [Offline] ${msg}`
    console.error(formatted, data ?? '')
  },
}

// WAITER-SVC-MED-02: Default timeout for IndexedDB operations (30 seconds)
const IDB_TIMEOUT_MS = 30000

/**
 * WAITER-SVC-MED-02: Wrap a promise with a timeout
 * Rejects with TimeoutError if the operation takes longer than the specified time
 */
function withTimeout<T>(promise: Promise<T>, timeoutMs: number = IDB_TIMEOUT_MS, operation: string = 'IndexedDB operation'): Promise<T> {
  return new Promise((resolve, reject) => {
    const timeoutId = setTimeout(() => {
      reject(new Error(`${operation} timed out after ${timeoutMs}ms`))
    }, timeoutMs)

    promise
      .then((result) => {
        clearTimeout(timeoutId)
        resolve(result)
      })
      .catch((error) => {
        clearTimeout(timeoutId)
        reject(error)
      })
  })
}

/**
 * Open IndexedDB connection
 * WAITER-SVC-MED-02: Wrapped with timeout
 */
function openDB(): Promise<IDBDatabase> {
  const openPromise = new Promise<IDBDatabase>((resolve, reject) => {
    const request = indexedDB.open(DB_NAME, DB_VERSION)

    request.onerror = () => {
      log.error('Failed to open IndexedDB', request.error)
      reject(request.error)
    }

    request.onsuccess = () => {
      resolve(request.result)
    }

    request.onupgradeneeded = (event) => {
      const db = (event.target as IDBOpenDBRequest).result

      // Create tables store
      if (!db.objectStoreNames.contains(TABLES_STORE)) {
        db.createObjectStore(TABLES_STORE, { keyPath: 'table_id' })
        log.info('Created tables store')
      }

      // Create action queue store
      if (!db.objectStoreNames.contains(QUEUE_STORE)) {
        const queueStore = db.createObjectStore(QUEUE_STORE, { keyPath: 'id' })
        queueStore.createIndex('timestamp', 'timestamp', { unique: false })
        log.info('Created action queue store')
      }
    }
  })

  // WAITER-SVC-MED-02: Apply timeout wrapper
  return withTimeout(openPromise, IDB_TIMEOUT_MS, 'openDB')
}

/**
 * Cache tables data for offline access
 * WAITER-SVC-MED-02: Wrapped with timeout
 */
export async function cacheTablesData(tables: TableCard[]): Promise<void> {
  const cachePromise = async (): Promise<void> => {
    const db = await openDB()
    const tx = db.transaction(TABLES_STORE, 'readwrite')
    const store = tx.objectStore(TABLES_STORE)

    // Clear existing data
    store.clear()

    // Add all tables
    for (const table of tables) {
      store.put(table)
    }

    return new Promise((resolve, reject) => {
      tx.oncomplete = () => {
        log.info('Cached tables data', { count: tables.length })
        db.close()
        resolve()
      }
      tx.onerror = () => {
        log.error('Failed to cache tables', tx.error)
        db.close()
        reject(tx.error)
      }
    })
  }

  try {
    // WAITER-SVC-MED-02: Apply timeout wrapper
    await withTimeout(cachePromise(), IDB_TIMEOUT_MS, 'cacheTablesData')
  } catch (error) {
    log.error('Error caching tables data', error)
    throw error
  }
}

/**
 * Retrieve cached tables data
 * WAITER-SVC-MED-02: Wrapped with timeout
 */
export async function getCachedTables(): Promise<TableCard[]> {
  const getPromise = async (): Promise<TableCard[]> => {
    const db = await openDB()
    const tx = db.transaction(TABLES_STORE, 'readonly')
    const store = tx.objectStore(TABLES_STORE)
    const request = store.getAll()

    return new Promise((resolve, reject) => {
      request.onsuccess = () => {
        const tables = request.result as TableCard[]
        log.info('Retrieved cached tables', { count: tables.length })
        db.close()
        resolve(tables)
      }
      request.onerror = () => {
        log.error('Failed to get cached tables', request.error)
        db.close()
        reject(request.error)
      }
    })
  }

  try {
    // WAITER-SVC-MED-02: Apply timeout wrapper
    return await withTimeout(getPromise(), IDB_TIMEOUT_MS, 'getCachedTables')
  } catch (error) {
    log.error('Error retrieving cached tables', error)
    return []
  }
}

/**
 * Check if app is in offline mode
 */
export function isOfflineMode(): boolean {
  return !navigator.onLine
}

/**
 * Queue an action for processing when back online
 * WAITER-SVC-MED-02: Wrapped with timeout
 */
export async function queueAction(
  type: QueuedActionType,
  payload: Record<string, unknown>
): Promise<string> {
  const action: QueuedAction = {
    id: crypto.randomUUID(),
    type,
    payload,
    timestamp: Date.now(),
    retryCount: 0,
  }

  const queuePromise = async (): Promise<string> => {
    const db = await openDB()
    const tx = db.transaction(QUEUE_STORE, 'readwrite')
    const store = tx.objectStore(QUEUE_STORE)
    store.add(action)

    return new Promise((resolve, reject) => {
      tx.oncomplete = () => {
        log.info('Queued action', { type, id: action.id })
        db.close()
        resolve(action.id)
      }
      tx.onerror = () => {
        log.error('Failed to queue action', tx.error)
        db.close()
        reject(tx.error)
      }
    })
  }

  try {
    // WAITER-SVC-MED-02: Apply timeout wrapper
    return await withTimeout(queuePromise(), IDB_TIMEOUT_MS, 'queueAction')
  } catch (error) {
    log.error('Error queuing action', error)
    throw error
  }
}

/**
 * Get all queued actions
 * WAITER-SVC-MED-02: Wrapped with timeout
 */
export async function getQueuedActions(): Promise<QueuedAction[]> {
  const getPromise = async (): Promise<QueuedAction[]> => {
    const db = await openDB()
    const tx = db.transaction(QUEUE_STORE, 'readonly')
    const store = tx.objectStore(QUEUE_STORE)
    const index = store.index('timestamp')
    const request = index.getAll()

    return new Promise((resolve, reject) => {
      request.onsuccess = () => {
        const actions = request.result as QueuedAction[]
        db.close()
        resolve(actions)
      }
      request.onerror = () => {
        log.error('Failed to get queued actions', request.error)
        db.close()
        reject(request.error)
      }
    })
  }

  try {
    // WAITER-SVC-MED-02: Apply timeout wrapper
    return await withTimeout(getPromise(), IDB_TIMEOUT_MS, 'getQueuedActions')
  } catch (error) {
    log.error('Error retrieving queued actions', error)
    return []
  }
}

/**
 * Remove an action from the queue (after successful processing)
 * WAITER-SVC-MED-02: Wrapped with timeout
 */
async function removeQueuedAction(actionId: string): Promise<void> {
  const removePromise = async (): Promise<void> => {
    const db = await openDB()
    const tx = db.transaction(QUEUE_STORE, 'readwrite')
    const store = tx.objectStore(QUEUE_STORE)
    store.delete(actionId)

    return new Promise((resolve, reject) => {
      tx.oncomplete = () => {
        log.info('Removed queued action', { id: actionId })
        db.close()
        resolve()
      }
      tx.onerror = () => {
        log.error('Failed to remove queued action', tx.error)
        db.close()
        reject(tx.error)
      }
    })
  }

  try {
    // WAITER-SVC-MED-02: Apply timeout wrapper
    await withTimeout(removePromise(), IDB_TIMEOUT_MS, 'removeQueuedAction')
  } catch (error) {
    log.error('Error removing queued action', error)
    throw error
  }
}

/**
 * Update retry count for a failed action
 * WAITER-SVC-MED-02: Wrapped with timeout
 */
async function updateActionRetryCount(
  actionId: string,
  retryCount: number
): Promise<void> {
  const updatePromise = async (): Promise<void> => {
    const db = await openDB()
    const tx = db.transaction(QUEUE_STORE, 'readwrite')
    const store = tx.objectStore(QUEUE_STORE)
    const request = store.get(actionId)

    request.onsuccess = () => {
      const action = request.result as QueuedAction | undefined
      if (action) {
        action.retryCount = retryCount
        store.put(action)
      }
    }

    return new Promise((resolve, reject) => {
      tx.oncomplete = () => {
        db.close()
        resolve()
      }
      tx.onerror = () => {
        db.close()
        reject(tx.error)
      }
    })
  }

  try {
    // WAITER-SVC-MED-02: Apply timeout wrapper
    await withTimeout(updatePromise(), IDB_TIMEOUT_MS, 'updateActionRetryCount')
  } catch (error) {
    log.error('Error updating action retry count', error)
    throw error
  }
}

// Maximum retry attempts for queued actions
const MAX_RETRIES = 3

// Action processor type
type ActionProcessor = (
  action: QueuedAction
) => Promise<{ success: boolean; error?: string }>

// Default processor that does nothing (to be replaced by actual implementation)
let actionProcessor: ActionProcessor | null = null

/**
 * Set the action processor for handling queued actions
 * This should be called during app initialization with actual API calls
 */
export function setActionProcessor(processor: ActionProcessor): void {
  actionProcessor = processor
}

/**
 * Process all queued actions when back online
 */
export async function processQueue(): Promise<{
  processed: number
  failed: number
}> {
  if (isOfflineMode()) {
    log.warn('Cannot process queue while offline')
    return { processed: 0, failed: 0 }
  }

  if (!actionProcessor) {
    log.warn('No action processor set, skipping queue processing')
    return { processed: 0, failed: 0 }
  }

  const actions = await getQueuedActions()

  if (actions.length === 0) {
    log.info('No queued actions to process')
    return { processed: 0, failed: 0 }
  }

  log.info('Processing queued actions', { count: actions.length })

  let processed = 0
  let failed = 0

  for (const action of actions) {
    try {
      const result = await actionProcessor(action)

      if (result.success) {
        await removeQueuedAction(action.id)
        processed++
        log.info('Processed queued action', { type: action.type, id: action.id })
      } else {
        // Increment retry count or remove if max retries exceeded
        const newRetryCount = action.retryCount + 1
        if (newRetryCount >= MAX_RETRIES) {
          await removeQueuedAction(action.id)
          failed++
          log.warn('Action removed after max retries', {
            type: action.type,
            id: action.id,
            error: result.error,
          })
        } else {
          await updateActionRetryCount(action.id, newRetryCount)
          log.warn('Action failed, will retry', {
            type: action.type,
            id: action.id,
            retryCount: newRetryCount,
            error: result.error,
          })
        }
      }
    } catch (error) {
      log.error('Error processing action', { type: action.type, error })
      failed++
    }
  }

  log.info('Queue processing complete', { processed, failed })
  return { processed, failed }
}

/**
 * Clear all cached data (tables and action queue)
 * WAITER-SVC-MED-02: Wrapped with timeout
 */
export async function clearCache(): Promise<void> {
  const clearPromise = async (): Promise<void> => {
    const db = await openDB()
    const tx = db.transaction([TABLES_STORE, QUEUE_STORE], 'readwrite')

    tx.objectStore(TABLES_STORE).clear()
    tx.objectStore(QUEUE_STORE).clear()

    return new Promise((resolve, reject) => {
      tx.oncomplete = () => {
        log.info('Cleared all cached data')
        db.close()
        resolve()
      }
      tx.onerror = () => {
        log.error('Failed to clear cache', tx.error)
        db.close()
        reject(tx.error)
      }
    })
  }

  try {
    // WAITER-SVC-MED-02: Apply timeout wrapper
    await withTimeout(clearPromise(), IDB_TIMEOUT_MS, 'clearCache')
  } catch (error) {
    log.error('Error clearing cache', error)
    throw error
  }
}

/**
 * Get the count of pending queued actions
 * WAITER-SVC-MED-02: Wrapped with timeout
 */
export async function getQueuedActionCount(): Promise<number> {
  const countPromise = async (): Promise<number> => {
    const db = await openDB()
    const tx = db.transaction(QUEUE_STORE, 'readonly')
    const store = tx.objectStore(QUEUE_STORE)
    const request = store.count()

    return new Promise((resolve, reject) => {
      request.onsuccess = () => {
        db.close()
        resolve(request.result)
      }
      request.onerror = () => {
        db.close()
        reject(request.error)
      }
    })
  }

  try {
    // WAITER-SVC-MED-02: Apply timeout wrapper
    return await withTimeout(countPromise(), IDB_TIMEOUT_MS, 'getQueuedActionCount')
  } catch (error) {
    log.error('Error getting queued action count', error)
    return 0
  }
}

// CRIT-29-03 FIX: Guard against duplicate listener registration
// Track whether listeners are already registered to prevent memory leaks on HMR/re-initialization
let offlineListenersRegistered = false

// Listen for online/offline events
if (typeof window !== 'undefined' && !offlineListenersRegistered) {
  offlineListenersRegistered = true

  window.addEventListener('online', () => {
    log.info('App is back online')
    // Automatically process queue when back online
    processQueue().catch((error) => {
      log.error('Failed to process queue on reconnect', error)
    })
  })

  window.addEventListener('offline', () => {
    log.info('App is now offline')
  })
}
