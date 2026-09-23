import { useEffect, useMemo, useRef, useState } from 'react'
import { api } from '../api'
import type { KeyTestResult, SettingField, SettingGroup, SettingsUpdate } from '../types'
import './SettingsModal.css'

interface Props {
  open: boolean
  onClose: () => void
}

/** A field that follows another shows that value's default; a secret shows its masked value. */
function placeholderFor(f: SettingField, draft: Record<string, string>): string {
  if (f.follows) return f.variants[draft[f.follows]]?.default ?? ''
  return f.secret ? f.value || 'not set' : f.default
}

/**
 * Every runtime setting on one card. What is saved here is kept in the
 * backend's database and wins over the environment from then on; the backend
 * rebuilds its services on save, so a new provider or model is live for the
 * next round without a restart.
 */
export function SettingsModal({ open, onClose }: Props) {
  const dialogRef = useRef<HTMLDialogElement>(null)
  const [fields, setFields] = useState<SettingField[] | null>(null)
  const [groups, setGroups] = useState<SettingGroup[]>([])
  const [draft, setDraft] = useState<Record<string, string>>({})
  const [saving, setSaving] = useState(false)
  const [keyTests, setKeyTests] = useState<Record<string, KeyTestResult | 'testing'>>({})
  const [notice, setNotice] = useState<{ kind: 'ok' | 'error'; text: string } | null>(null)

  useEffect(() => {
    const dialog = dialogRef.current
    if (!dialog) return
    if (open && !dialog.open) showDialog(dialog)
    else if (!open && dialog.open) dialog.close()
  }, [open])

  useEffect(() => {
    if (!open) return
    let live = true
    setNotice(null)
    setKeyTests({})
    api.getSettings().then(
      ({ groups, fields }) => {
        if (!live) return
        setGroups(groups)
        setFields(fields)
        setDraft(Object.fromEntries(fields.map((f) => [f.key, f.secret ? '' : f.value])))
      },
      (e: unknown) => live && setNotice({ kind: 'error', text: e instanceof Error ? e.message : String(e) }),
    )
    return () => {
      live = false
    }
  }, [open])

  const changes = useMemo<SettingsUpdate>(() => {
    const update: SettingsUpdate = {}
    for (const f of fields ?? []) {
      if (f.secret ? draft[f.key] !== '' : draft[f.key] !== f.value) update[f.key] = draft[f.key]
    }
    return update
  }, [draft, fields])

  const edit = (key: string, value: string) => {
    setDraft((d) => ({ ...d, [key]: value }))
    setKeyTests((t) => (key in t ? { ...t, [key]: undefined } as Record<string, KeyTestResult | 'testing'> : t))
  }

  /** Tries the typed key, or the saved one when the field is blank. */
  const testKey = async (key: string) => {
    setKeyTests((t) => ({ ...t, [key]: 'testing' }))
    try {
      const result = await api.testKey(key, draft[key] ?? '')
      setKeyTests((t) => ({ ...t, [key]: result }))
    } catch (e) {
      setKeyTests((t) => ({ ...t, [key]: { ok: false, message: e instanceof Error ? e.message : String(e) } }))
    }
  }

  const save = async () => {
    setSaving(true)
    setNotice(null)
    try {
      const { fields } = await api.putSettings(changes)
      setFields(fields)
      setDraft(Object.fromEntries(fields.map((f) => [f.key, f.secret ? '' : f.value])))
      setNotice({ kind: 'ok', text: 'Saved. The next round uses these.' })
    } catch (e) {
      setNotice({ kind: 'error', text: e instanceof Error ? e.message : String(e) })
    } finally {
      setSaving(false)
    }
  }

  const visible = (f: SettingField): boolean => !f.shown_when || draft[f.shown_when[0]] === f.shown_when[1]
  const suggestionsFor = (f: SettingField): string[] =>
    f.follows ? (f.variants[draft[f.follows]]?.suggestions ?? []) : f.suggestions

  return (
    <dialog ref={dialogRef} className="settings" aria-label="Settings" onClose={onClose}>
      <form
        method="dialog"
        className="settings-form"
        onSubmit={(e) => {
          e.preventDefault()
          void save()
        }}
      >
        <header className="settings-head">
          <h2>Settings</h2>
          <p className="settings-lede">Saved values apply to the next round. No restart.</p>
        </header>
        {fields === null ? (
          <p className="settings-loading">{notice?.kind === 'error' ? notice.text : 'Loading…'}</p>
        ) : (
          groups.map((group) => (
            <fieldset key={group.id} className="settings-group">
              <legend>{group.title}</legend>
              {fields.filter((f) => f.group === group.id && visible(f)).map((f) => (
                <div key={f.key} className="settings-row">
                  <label htmlFor={`setting-${f.key}`}>
                    <code>{f.key}</code>
                  </label>
                  <Control
                    field={f}
                    value={draft[f.key] ?? ''}
                    suggestions={suggestionsFor(f)}
                    placeholder={placeholderFor(f, draft)}
                    onChange={(v) => edit(f.key, v)}
                  />
                  {f.testable && <KeyTest state={keyTests[f.key]} onTest={() => void testKey(f.key)} />}
                </div>
              ))}
            </fieldset>
          ))
        )}
        <footer className="settings-foot">
          {notice && <p className={`settings-notice is-${notice.kind}`} role="status">{notice.text}</p>}
          <button type="button" className="btn" onClick={onClose}>
            Close
          </button>
          <button type="submit" className="btn btn-primary" disabled={saving || Object.keys(changes).length === 0}>
            {saving ? 'Saving…' : 'Save'}
          </button>
        </footer>
      </form>
    </dialog>
  )
}

function KeyTest({ state, onTest }: { state: KeyTestResult | 'testing' | undefined; onTest: () => void }) {
  return (
    <div className="settings-keytest">
      <button type="button" className="settings-test" onClick={onTest} disabled={state === 'testing'}>
        {state === 'testing' ? 'Testing…' : 'Test'}
      </button>
      {state && state !== 'testing' && (
        <span className={`settings-keytest-result is-${state.ok ? 'ok' : 'error'}`} role="status">
          {state.ok ? '✓ ' : '✗ '}
          {state.message}
        </span>
      )}
    </div>
  )
}

interface ControlProps {
  field: SettingField
  value: string
  suggestions: string[]
  placeholder: string
  onChange: (value: string) => void
}

function Control({ field, value, suggestions, placeholder, onChange }: ControlProps) {
  const id = `setting-${field.key}`
  if (field.choices) {
    return (
      <select id={id} value={value} onChange={(e) => onChange(e.target.value)}>
        {field.choices.map((c) => (
          <option key={c} value={c}>
            {field.labels[c] ? `${c} · ${field.labels[c]}` : c}
          </option>
        ))}
      </select>
    )
  }
  const listId = suggestions.length > 0 ? `${id}-options` : undefined
  return (
    <>
      <input
        id={id}
        type={field.secret ? 'password' : 'text'}
        autoComplete="off"
        list={listId}
        value={value}
        placeholder={placeholder}
        onChange={(e) => onChange(e.target.value)}
      />
      {listId && (
        <datalist id={listId}>
          {suggestions.map((s) => (
            <option key={s} value={s} />
          ))}
        </datalist>
      )}
    </>
  )
}

/** jsdom has no showModal; the attribute keeps the tests honest. */
function showDialog(dialog: HTMLDialogElement) {
  if (typeof dialog.showModal === 'function') dialog.showModal()
  else dialog.setAttribute('open', '')
}
