import { BrowserRouter, Outlet, Route, Routes } from 'react-router-dom'
import { CornerTools } from './components/CornerTools'
import { AuthProvider, RequireAuth } from './lib/auth'
import { DatabasePage } from './pages/DatabasePage'
import { HomePage } from './pages/HomePage'
import { LoginPage } from './pages/LoginPage'
import { SessionPage } from './pages/SessionPage'
import { SignupPage } from './pages/SignupPage'

/** Every page but the two that let someone in. */
function SignedIn() {
  return (
    <RequireAuth>
      <Outlet />
      <CornerTools />
    </RequireAuth>
  )
}

export default function App() {
  return (
    <BrowserRouter>
      <AuthProvider>
        <Routes>
          <Route path="/login" element={<LoginPage />} />
          <Route path="/signup" element={<SignupPage />} />
          <Route element={<SignedIn />}>
            <Route path="/" element={<HomePage />} />
            <Route path="/s/:id" element={<SessionPage />} />
            <Route path="/database" element={<DatabasePage tab="expressions" />} />
            <Route path="/database/topics" element={<DatabasePage tab="topics" />} />
          </Route>
        </Routes>
      </AuthProvider>
    </BrowserRouter>
  )
}
