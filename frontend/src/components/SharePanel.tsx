import { useState } from 'react'
import { ComboBox, Input, type Key, Label, ListBox, ListBoxItem, Popover } from 'react-aria-components'
import { api } from '../api'
import { type PeopleNamed, usePeopleNamed } from '../lib/usePeopleNamed'
import { useSessionResource } from '../lib/sessionChanges'
import type { PersonMatch, ShareEntry } from '../types'
import './SharePanel.css'

interface Props {
  sessionId: number
}

/** Whom the maker of a session has shared it with, and a search by username for whom to add. */
export function SharePanel({ sessionId }: Props) {
  const [shares, setShares] = useState<ShareEntry[]>([])
  const [typed, setTyped] = useState('')
  const [readError, setReadError] = useState<string | null>(null)
  const [writeError, setWriteError] = useState<string | null>(null)
  const found = usePeopleNamed(typed)
  const offered = found.people.filter((person) => !shares.some((share) => share.user_id === person.id))
  const error = writeError ?? readError

  useSessionResource(
    sessionId,
    'shares',
    () => api.listShares(sessionId),
    (list) => {
      setShares(list)
      setReadError(null)
    },
    (e) => setReadError(e.message),
  )

  /** The box clears at once: that closes the menu, which would otherwise cover whatever goes wrong. Two picks in quick
   * succession both go; the shares event reads the list again after each. */
  async function add(person: PersonMatch) {
    setTyped('')
    setWriteError(null)
    try {
      setShares(await api.addShare(sessionId, person.id))
    } catch (e) {
      setWriteError((e as Error).message)
    }
  }

  async function remove(entry: ShareEntry) {
    setWriteError(null)
    try {
      await api.removeShare(sessionId, entry.user_id)
      setShares((all) => all.filter((s) => s.user_id !== entry.user_id))
    } catch (e) {
      setWriteError((e as Error).message)
    }
  }

  function pick(key: Key | null) {
    const person = offered.find((p) => p.id === key)
    if (person) void add(person)
  }

  return (
    <section className="share" aria-label="Sharing" data-presence-anchor="shares">
      <ComboBox
        className="share-form"
        inputValue={typed}
        onInputChange={setTyped}
        selectedKey={null}
        onSelectionChange={pick}
        items={offered}
        menuTrigger="input"
        allowsEmptyCollection={typed.trim() !== ''} // open while the answer is on its way, and to say there is nobody
        defaultFilter={() => true} // the server already matched the names
      >
        <Label className="share-label">Share with</Label>
        <Input className="share-input" autoCapitalize="none" spellCheck={false} placeholder="their username" />
        <Popover className="share-popover" placement="bottom start">
          <ListBox<PersonMatch>
            className="share-matches"
            renderEmptyState={() => <p className="share-none">{emptySaying(found)}</p>}
          >
            {(person) => (
              <ListBoxItem id={person.id} textValue={person.username} className="share-match">
                {person.username}
              </ListBoxItem>
            )}
          </ListBox>
        </Popover>
      </ComboBox>
      {error && (
        <p role="alert" className="share-error">
          {error}
        </p>
      )}
      {shares.length > 0 && (
        <ul className="share-list">
          {shares.map((entry) => (
            <li key={entry.user_id} className="share-item">
              <span className="share-name" title={entry.username}>
                {entry.username}
              </span>
              <button
                type="button"
                className="btn-link share-stop"
                aria-label={`Stop sharing with ${entry.username}`}
                onClick={() => void remove(entry)}
              >
                Stop
              </button>
            </li>
          ))}
        </ul>
      )}
    </section>
  )
}

/** What the menu says when it lists nobody. */
function emptySaying(found: PeopleNamed): string {
  if (found.settled) return 'No one goes by a name like that.'
  return found.failed ? 'The search did not go through. Type again to retry.' : 'Looking…'
}
