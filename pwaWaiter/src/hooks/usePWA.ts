import { useState, useEffect, useCallback } from 'react'
// @ts-ignore - virtual module
import { useRegisterSW } from 'virtual:pwa-register/react'

interface PWAState {
    needRefresh: boolean
    offlineReady: boolean
    updateServiceWorker: (reloadPage?: boolean) => Promise<void>
    canInstall: boolean
    isInstalled: boolean
    installApp: () => Promise<void>
}

export function usePWA(): PWAState {
    const [canInstall, setCanInstall] = useState(false)
    const [isInstalled, setIsInstalled] = useState(false)
    const [deferredPrompt, setDeferredPrompt] = useState<any>(null)

    // Use vite-plugin-pwa hook for updates
    const {
        offlineReady: [offlineReady],
        needRefresh: [needRefresh],
        updateServiceWorker,
    } = useRegisterSW({
        onRegisterError(error: any) {
            console.error('SW registration error', error)
        },
    })

    // Check installation status
    useEffect(() => {
        const isStandalone =
            window.matchMedia('(display-mode: standalone)').matches ||
            (window.navigator as any).standalone === true

        setIsInstalled(isStandalone)

        const mediaQuery = window.matchMedia('(display-mode: standalone)')
        const handleChange = (e: MediaQueryListEvent) => setIsInstalled(e.matches)
        mediaQuery.addEventListener('change', handleChange)

        return () => mediaQuery.removeEventListener('change', handleChange)
    }, [])

    // Handle install prompt
    useEffect(() => {
        const handleBeforeInstallPrompt = (e: Event) => {
            e.preventDefault()
            setDeferredPrompt(e)
            setCanInstall(true)
        }

        const handleAppInstalled = () => {
            setCanInstall(false)
            setIsInstalled(true)
            setDeferredPrompt(null)
        }

        window.addEventListener('beforeinstallprompt', handleBeforeInstallPrompt)
        window.addEventListener('appinstalled', handleAppInstalled)

        return () => {
            window.removeEventListener('beforeinstallprompt', handleBeforeInstallPrompt)
            window.removeEventListener('appinstalled', handleAppInstalled)
        }
    }, [])

    const installApp = useCallback(async () => {
        if (!deferredPrompt) return

        deferredPrompt.prompt()
        const { outcome } = await deferredPrompt.userChoice

        if (outcome === 'accepted') {
            setDeferredPrompt(null)
            // install state will be updated by appinstalled event
        }
    }, [deferredPrompt])

    return {
        needRefresh,
        offlineReady,
        updateServiceWorker,
        canInstall,
        isInstalled,
        installApp
    }
}
