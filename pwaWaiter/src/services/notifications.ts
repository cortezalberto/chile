import { notificationLogger } from '../utils/logger'
import type { WSEvent } from '../types'

// WAITER-HIGH-02 FIX: Track recent notifications to prevent duplicates
const recentNotifications = new Set<string>()
const NOTIFICATION_COOLDOWN_MS = 5000

class NotificationService {
  private permission: NotificationPermission = 'default'
  private alertSound: HTMLAudioElement | null = null // PWAW-A005

  /**
   * Request notification permission
   */
  async requestPermission(): Promise<boolean> {
    if (!('Notification' in window)) {
      notificationLogger.warn('Notifications not supported')
      return false
    }

    if (Notification.permission === 'granted') {
      this.permission = 'granted'
      return true
    }

    if (Notification.permission === 'denied') {
      notificationLogger.info('Notifications denied by user')
      this.permission = 'denied'
      return false
    }

    try {
      const result = await Notification.requestPermission()
      this.permission = result
      notificationLogger.info('Notification permission', { result })
      return result === 'granted'
    } catch (error) {
      notificationLogger.error('Failed to request permission', error)
      return false
    }
  }

  /**
   * Check if notifications are enabled
   */
  isEnabled(): boolean {
    return this.permission === 'granted'
  }

  /**
   * Show notification for WebSocket event
   */
  notifyEvent(event: WSEvent): void {
    if (!this.isEnabled()) return

    const { title, body, tag } = this.getNotificationContent(event)

    if (!title) return

    // PWAW-A005: Play sound for urgent events
    if (this.isUrgent(event.type)) {
      this.playAlertSound()
    }

    this.show(title, body, {
      tag,
      requireInteraction: this.isUrgent(event.type),
      data: event,
    })
  }

  /**
   * PWAW-A005: Play alert sound for urgent notifications
   */
  private playAlertSound(): void {
    try {
      // Create audio element if not exists
      if (!this.alertSound) {
        this.alertSound = new Audio('/sounds/alert.mp3')
        this.alertSound.volume = 0.5
      }

      // Reset and play
      this.alertSound.currentTime = 0
      this.alertSound.play().catch((error) => {
        // Silently fail if audio play is blocked (user hasn't interacted)
        notificationLogger.debug('Could not play alert sound', error)
      })
    } catch (error) {
      notificationLogger.debug('Alert sound not available', error)
    }
  }

  /**
   * Show a notification
   */
  private show(
    title: string,
    body: string,
    options: NotificationOptions = {}
  ): void {
    if (!this.isEnabled()) return

    // WAITER-HIGH-02 FIX: Skip if recently shown (deduplicate)
    const tag = options.tag as string | undefined
    const key = tag || `${title}_${body}`

    if (recentNotifications.has(key)) {
      notificationLogger.debug('Notification recently shown, skipping', { key })
      return
    }

    recentNotifications.add(key)
    setTimeout(() => recentNotifications.delete(key), NOTIFICATION_COOLDOWN_MS)

    try {
      const notification = new Notification(title, {
        body,
        icon: '/pwa-192x192.png',
        badge: '/pwa-192x192.png',
        ...options,
      })

      notification.onclick = () => {
        window.focus()
        notification.close()
      }

      // Auto-close non-urgent notifications after 5 seconds
      if (!options.requireInteraction) {
        setTimeout(() => notification.close(), 5000)
      }
    } catch (error) {
      notificationLogger.error('Failed to show notification', error)
    }
  }

  /**
   * Get notification content based on event type
   */
  private getNotificationContent(event: WSEvent): {
    title: string
    body: string
    tag: string
  } {
    const tableInfo = `Mesa ${event.table_id}`

    switch (event.type) {
      case 'ROUND_SUBMITTED':
        return {
          title: 'Nuevo Pedido',
          body: `${tableInfo} envió un nuevo pedido`,
          tag: `round-${event.entity?.round_id}`,
        }

      case 'ROUND_IN_KITCHEN':
        return {
          title: 'Pedido en Cocina',
          body: `${tableInfo} - Pedido #${event.entity?.round_number} en preparación`,
          tag: `round-kitchen-${event.entity?.round_id}`,
        }

      case 'ROUND_READY':
        return {
          title: 'Pedido Listo',
          body: `${tableInfo} tiene un pedido listo para servir`,
          tag: `round-ready-${event.entity?.round_id}`,
        }

      case 'ROUND_SERVED':
        return {
          title: 'Pedido Servido',
          body: `${tableInfo} - Pedido #${event.entity?.round_number} entregado`,
          tag: `round-served-${event.entity?.round_id}`,
        }

      case 'SERVICE_CALL_CREATED': {
        // PWAW-004: Include call_type in notification
        const callType = event.entity?.call_type as string | undefined
        const callTypeText = callType === 'BILL'
          ? 'solicita la cuenta'
          : callType === 'ASSISTANCE'
            ? 'necesita asistencia'
            : 'necesita atención'
        return {
          title: 'Llamado de Mesa',
          body: `${tableInfo} ${callTypeText}`,
          tag: `service-call-${event.entity?.call_id}`,
        }
      }

      case 'CHECK_REQUESTED':
        return {
          title: 'Cuenta Solicitada',
          body: `${tableInfo} solicitó la cuenta`,
          tag: `check-${event.session_id}`,
        }

      case 'CHECK_PAID':
        return {
          title: 'Cuenta Pagada',
          body: `${tableInfo} completó el pago`,
          tag: `check-paid-${event.entity?.check_id}`,
        }

      case 'TABLE_CLEARED':
        return {
          title: 'Mesa Liberada',
          body: `${tableInfo} ha sido liberada`,
          tag: `table-cleared-${event.table_id}`,
        }

      case 'PAYMENT_APPROVED':
        return {
          title: 'Pago Aprobado',
          body: `${tableInfo} - Pago de $${((event.entity?.amount_cents || 0) / 100).toFixed(2)} aprobado`,
          tag: `payment-${event.entity?.payment_id}`,
        }

      default:
        return { title: '', body: '', tag: '' }
    }
  }

  /**
   * Check if event type is urgent (requires user interaction)
   */
  private isUrgent(type: WSEvent['type']): boolean {
    return ['SERVICE_CALL_CREATED', 'CHECK_REQUESTED', 'ROUND_READY'].includes(type)
  }
}

// Singleton instance
export const notificationService = new NotificationService()
