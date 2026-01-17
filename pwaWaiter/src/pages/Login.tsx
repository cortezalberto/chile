import { useState, type FormEvent } from 'react'
import { useAuthStore, selectIsLoading, selectAuthError } from '../stores/authStore'
import { Button } from '../components/Button'
import { Input } from '../components/Input'

// WAITER-PAGE-MED-01: Simple email validation
const isValidEmail = (email: string): boolean => {
  return /^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email)
}

export function LoginPage() {
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  // WAITER-PAGE-MED-01: Track touched fields for validation
  const [touched, setTouched] = useState({ email: false, password: false })

  const login = useAuthStore((s) => s.login)
  const isLoading = useAuthStore(selectIsLoading)
  const error = useAuthStore(selectAuthError)
  const clearError = useAuthStore((s) => s.clearError)

  // WAITER-PAGE-MED-01: Compute field-level validation errors
  const emailError = touched.email && !email ? 'El email es requerido' :
                     touched.email && !isValidEmail(email) ? 'Email invalido' : undefined
  const passwordError = touched.password && !password ? 'La contrasena es requerida' : undefined

  const handleSubmit = async (e: FormEvent) => {
    e.preventDefault()
    clearError()
    await login(email, password)
  }

  return (
    <div className="min-h-screen flex items-center justify-center bg-[#0a0a0a] px-4">
      <div className="w-full max-w-md">
        {/* Logo/Title */}
        <div className="text-center mb-8">
          <h1 className="text-4xl font-bold text-orange-500 mb-2">Mozo</h1>
          <p className="text-neutral-400">Panel de control</p>
        </div>

        {/* Login form */}
        <form
          onSubmit={handleSubmit}
          className="bg-neutral-900 rounded-2xl p-6 border border-neutral-800"
        >
          <div className="space-y-4">
            <Input
              label="Email"
              type="email"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              onBlur={() => setTouched((t) => ({ ...t, email: true }))}
              placeholder="tu@email.com"
              autoComplete="email"
              required
              disabled={isLoading}
              error={emailError}
            />

            <Input
              label="Contrasena"
              type="password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              onBlur={() => setTouched((t) => ({ ...t, password: true }))}
              placeholder="••••••••"
              autoComplete="current-password"
              required
              disabled={isLoading}
              error={passwordError}
            />
          </div>

          {error && (
            <div
              className="mt-4 p-3 rounded-lg bg-red-500/10 border border-red-500/20"
              role="alert"
              aria-live="assertive"
            >
              <p className="text-sm text-red-500">{error}</p>
            </div>
          )}

          <Button
            type="submit"
            variant="primary"
            size="lg"
            className="w-full mt-6"
            isLoading={isLoading}
          >
            Iniciar Sesion
          </Button>
        </form>

        {/* Test credentials hint */}
        <div className="mt-6 p-4 rounded-lg bg-neutral-900/50 border border-neutral-800">
          <p className="text-sm text-neutral-500 text-center">
            Credenciales de prueba:
            <br />
            <span className="text-neutral-400">waiter@demo.com / waiter123</span>
          </p>
        </div>
      </div>
    </div>
  )
}
