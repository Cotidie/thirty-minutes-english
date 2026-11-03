import { createContext, useCallback, useContext, useEffect, useMemo, useState, type ReactNode } from 'react'
import { Navigate, useLocation } from 'react-router-dom'
import { api, type ApiError } from '../api'
import type { Me } from '../types'
import { useAccountResource } from './sessionChanges'

interface Auth {
  me: Me | null
  loading: boolean
  logIn: (email: string, password: string) => Promise<void>
  signUp: (email: string, username: string, password: string) => Promise<void>
  /** A new username for this account; fails as the server refuses it. */
  rename: (username: string) => Promise<void>
  /** The account as the server just read it. */
  replaceMe: (me: Me) => void
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
  const signUp = useCallback(
    async (email: string, username: string, password: string) => setMe(await api.signup(email, username, password)),
    [],
  )
  const rename = useCallback(async (username: string) => setMe(await api.setUsername(username)), [])
  const logOut = useCallback(async () => {
    try {
      await api.logout()
    } catch (e) {
      if ((e as ApiError).status !== 401) return // the login still stands, so nobody should think it ended
    }
    setMe(null)
  }, [])

  const auth = useMemo(
    () => ({ me, loading, logIn, signUp, rename, replaceMe: setMe, logOut }),
    [me, loading, logIn, signUp, rename, logOut],
  )
  return <AuthContext.Provider value={auth}>{children}</AuthContext.Provider>
}

export function useAuth(): Auth {
  const auth = useContext(AuthContext)
  if (!auth) throw new Error('useAuth needs an AuthProvider')
  return auth
}

/** Keeps `me` as the server has it when another tab or device changes it. Only behind the login: the account's stream
 * needs one. */
export function MeKeptFresh() {
  const { replaceMe } = useAuth()
  useAccountResource('me', api.me, replaceMe)
  return null
}

/** Its children for someone logged in; anyone else goes to the login page and comes back here. */
export function RequireAuth({ children }: { children: ReactNode }) {
  const { me, loading } = useAuth()
  const { pathname, search, hash } = useLocation()
  if (loading) return null
  if (!me) return <Navigate to={`/login?next=${encodeURIComponent(pathname + search + hash)}`} replace />
  return children
}
