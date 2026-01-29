import { usePWA } from '../hooks/usePWA'

export function PWAManager() {
    const { needRefresh, updateServiceWorker, canInstall, isInstalled, installApp } = usePWA()

    // Don't show anything if installed and updated
    if (!needRefresh && (!canInstall || isInstalled)) {
        return null
    }

    return (
        <div className="fixed bottom-4 right-4 z-50 flex flex-col gap-2 pointer-events-none">
            {/* Update Available Toast */}
            {needRefresh && (
                <div className="bg-slate-800 text-white p-4 rounded-lg shadow-xl border border-slate-700 pointer-events-auto animate-slide-up flex flex-col gap-3 w-80">
                    <div className="flex items-start gap-3">
                        <div className="text-blue-400 mt-1">
                            <svg xmlns="http://www.w3.org/2000/svg" width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4" /><polyline points="7 10 12 15 17 10" /><line x1="12" y1="15" x2="12" y2="3" /></svg>
                        </div>
                        <div>
                            <h4 className="font-semibold text-sm">Actualización disponible</h4>
                            <p className="text-xs text-slate-400 mt-1">Una nueva versión del panel de mozo está lista.</p>
                        </div>
                    </div>
                    <button
                        onClick={() => updateServiceWorker(true)}
                        className="w-full bg-blue-600 hover:bg-blue-700 text-white text-sm font-medium py-2 rounded transition-colors"
                    >
                        Actualizar ahora
                    </button>
                </div>
            )}

            {/* Install Prompt - Only show if not installed and browser supports it */}
            {canInstall && !isInstalled && !needRefresh && (
                <div className="bg-slate-800 text-white p-4 rounded-lg shadow-xl border border-slate-700 pointer-events-auto animate-slide-up flex items-center justify-between gap-4 w-auto max-w-sm">
                    <div className="flex items-center gap-3">
                        <div className="text-orange-500 bg-orange-500/10 p-2 rounded-full">
                            <svg xmlns="http://www.w3.org/2000/svg" width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><rect width="18" height="18" x="3" y="3" rx="2" ry="2" /><line x1="12" y1="8" x2="12" y2="16" /><line x1="8" y1="12" x2="16" y2="12" /></svg>
                        </div>
                        <div className="text-sm">
                            <span className="font-medium block">Instalar App</span>
                            <span className="text-xs text-slate-400">Acceso más rápido</span>
                        </div>
                    </div>
                    <button
                        onClick={installApp}
                        className="text-orange-500 hover:text-orange-400 text-sm font-semibold px-3 py-1.5 border border-orange-500/30 rounded hover:bg-orange-500/10 transition-colors"
                    >
                        Instalar
                    </button>
                </div>
            )}
        </div>
    )
}
