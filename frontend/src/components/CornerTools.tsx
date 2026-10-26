import { Link } from 'react-router-dom'
import { SettingsButton } from './SettingsButton'
import './CornerTools.css'

/** The round buttons in the corner of every page: the expression corpus, then the settings. */
export function CornerTools() {
  return (
    <nav className="corner-tools">
      <Link to="/corpus" className="corner-button" aria-label="Expression corpus" title="Expression corpus">
        <svg viewBox="0 0 24 24" width="18" height="18" aria-hidden="true">
          <g fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">
            <ellipse cx="12" cy="5.5" rx="7" ry="2.5" />
            <path d="M5 5.5v13c0 1.4 3.1 2.5 7 2.5s7-1.1 7-2.5v-13" />
            <path d="M5 12c0 1.4 3.1 2.5 7 2.5s7-1.1 7-2.5" />
          </g>
        </svg>
      </Link>
      <SettingsButton />
    </nav>
  )
}
