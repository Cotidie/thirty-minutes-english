import { Link, NavLink } from 'react-router-dom'
import { AccountsPanel } from '../components/AccountsPanel'
import { CorpusPanel } from '../components/CorpusPanel'
import { TopicsPanel } from '../components/TopicsPanel'
import './DatabasePage.css'

const TABS = [
  { to: '/database', label: 'Expressions' },
  { to: '/database/topics', label: 'Topics' },
  { to: '/database/accounts', label: 'Accounts' },
]

const PANELS = { expressions: CorpusPanel, topics: TopicsPanel, accounts: AccountsPanel }

/** What the database holds, to read through: the expression corpus, the topics, and the accounts. */
export function DatabasePage({ tab }: { tab: keyof typeof PANELS }) {
  const Panel = PANELS[tab]
  return (
    <main className="database">
      <header>
        <Link to="/" className="database-back">
          ← Sessions
        </Link>
        <h1 className="database-title">Database</h1>
        <nav className="database-tabs" aria-label="Tables">
          {TABS.map((t) => (
            <NavLink key={t.to} to={t.to} end className={({ isActive }) => `database-tab${isActive ? ' is-active' : ''}`}>
              {t.label}
            </NavLink>
          ))}
        </nav>
      </header>
      <Panel />
    </main>
  )
}
