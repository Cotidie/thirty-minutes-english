import { Link } from 'react-router-dom'
import { useAuth } from '../lib/auth'
import { SettingsButton } from './SettingsButton'
import './CornerTools.css'

/** The round buttons in the corner of every page: the database and the settings for the admin, and the way out. */
export function CornerTools() {
  const { me, logOut } = useAuth()
  return (
    <nav className="corner-tools">
      {me?.is_admin && <AdminTools />}
      <button type="button" className="corner-button" aria-label="Log out" title="Log out" onClick={() => void logOut()}>
        <svg viewBox="0 0 24 24" width="18" height="18" aria-hidden="true">
          <path
            fill="none"
            stroke="currentColor"
            strokeWidth="1.8"
            strokeLinecap="round"
            strokeLinejoin="round"
            d="M9 4H6a2 2 0 0 0-2 2v12a2 2 0 0 0 2 2h3M15 8l4 4-4 4M19 12H9"
          />
        </svg>
      </button>
    </nav>
  )
}

function AdminTools() {
  return (
    <>
      <Link to="/database" className="corner-button" aria-label="Database" title="Database">
        <svg viewBox="0 0 24 24" width="18" height="18" aria-hidden="true">
          <g fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">
            <ellipse cx="12" cy="5.5" rx="7" ry="2.5" />
            <path d="M5 5.5v13c0 1.4 3.1 2.5 7 2.5s7-1.1 7-2.5v-13" />
            <path d="M5 12c0 1.4 3.1 2.5 7 2.5s7-1.1 7-2.5" />
          </g>
        </svg>
      </Link>
      <SettingsButton />
    </>
  )
}
