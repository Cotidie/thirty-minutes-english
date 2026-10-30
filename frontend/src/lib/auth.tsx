import { createContext, useCallback, useContext, useEffect, useMemo, useState, type ReactNode } from 'react'
import { Navigate, useLocation } from 'react-router-dom'
import { api } from '../api'
import type { Me } from '../types'

interface Auth {
  me: Me | null
  loading: boolean
  logIn: (email: string, password: string) => Promise<void>
  signUp: (email: string, password: string) => Promise<void>
  logOut: () => Promise<void>
}

const AuthContext = createContext<Auth | null>(null)

/** Who is logged in, asked once when the app opens; the login cookie itself is out of the page's reach. */
export function AuthProvider({ children }: { children: ReactNode }) {
  const [me, setMe] = useState<Me | null>(null)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    let live = true
    api
      .me()
      .then((user) => live && setMe(user))
      .catch(() => live && setMe(null))
      .finally(() => live && setLoading(false))
    return () => {
      live = false
    }
  }, [])

  const logIn = useCallback(async (email: string, password: string) => setMe(await api.login(email, password)), [])
  const signUp = useCallback(async (email: string, password: string) => setMe(await api.signup(email, password)), [])
  const logOut = useCallback(async () => {
    await api.logout()
    setMe(null)
  }, [])

  const auth = useMemo(() => ({ me, loading, logIn, signUp, logOut }), [me, loading, logIn, signUp, logOut])
  return <AuthContext.Provider value={auth}>{children}</AuthContext.Provider>
}

export function useAuth(): Auth {
  const auth = useContext(AuthContext)
  if (!auth) throw new Error('useAuth needs an AuthProvider')
  return auth
}

/** Its children for someone logged in; anyone else goes to the login page and comes back here. */
export function RequireAuth({ children }: { children: ReactNode }) {
  const { me, loading } = useAuth()
  const { pathname, search, hash } = useLocation()
  if (loading) return null
  if (!me) return <Navigate to={`/login?next=${encodeURIComponent(pathname + search + hash)}`} replace />
  return children
}
