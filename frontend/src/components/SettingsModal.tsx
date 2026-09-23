import { useEffect, useMemo, useRef, useState } from 'react'
import { api } from '../api'
import type { KeyTestResult, SettingField, SettingGroup, SettingsUpdate } from '../types'
import './SettingsModal.css'

interface Props {
  open: boolean
  onClose: () => void
}

type KeyTestState = KeyTestResult | 'testing'

/** A field that follows another shows that value's default; a secret shows its masked value. */
function placeholderFor(f: SettingField, draft: Record<string, string>): string {
  if (f.follows) return f.variants[draft[f.follows]]?.default ?? ''
  if (f.secret) return f.value ? `Saved: ${f.value}. Type to replace.` : 'Not set'
  return f.default
}

function draftOf(fields: SettingField[]): Record<string, string> {
  return Object.fromEntries(fields.map((f) => [f.key, f.secret ? '' : f.value]))
}

/**
 * Every runtime setting, one group at a time. What is saved here is kept in the
 * backend's database and wins over the environment from then on; the backend
 * rebuilds its services on save, so a new provider or model is live for the
 * next round without a restart. Closing with unsaved edits asks first.
 */
export function SettingsModal({ open, onClose }: Props) {
  const dialogRef = useRef<HTMLDialogElement>(null)
  const [fields, setFields] = useState<SettingField[] | null>(null)
  const [groups, setGroups] = useState<SettingGroup[]>([])
  const [tab, setTab] = useState('')
  const [draft, setDraft] = useState<Record<string, string>>({})
  const [saving, setSaving] = useState(false)
  const [keyTests, setKeyTests] = useState<Record<string, KeyTestState>>({})
  const [notice, setNotice] = useState<{ kind: 'ok' | 'error'; text: string } | null>(null)
  const [confirming, setConfirming] = useState(false)

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
    setConfirming(false)
    api.getSettings().then(
      ({ groups, fields }) => {
        if (!live) return
        setGroups(groups)
        setTab((t) => (groups.some((g) => g.id === t) ? t : (groups[0]?.id ?? '')))
        setFields(fields)
        setDraft(draftOf(fields))
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
  const changed = Object.keys(changes).length

  const edit = (key: string, value: string) => {
    setNotice(null)
    setDraft((d) => ({ ...d, [key]: value }))
    setKeyTests(({ [key]: _, ...rest }) => rest)
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
      setDraft(draftOf(fields))
      setNotice({ kind: 'ok', text: 'Saved. The next round uses these.' })
    } catch (e) {
      setNotice({ kind: 'error', text: e instanceof Error ? e.message : String(e) })
    } finally {
      setSaving(false)
    }
  }

  const discard = () => {
    if (fields) setDraft(draftOf(fields))
    setKeyTests({})
    setNotice(null)
  }

  const requestClose = () => (changed > 0 ? setConfirming(true) : onClose())

  const visible = (f: SettingField): boolean => !f.shown_when || draft[f.shown_when[0]] === f.shown_when[1]
  const inGroup = (id: string) => (fields ?? []).filter((f) => f.group === id && visible(f))
  const current = groups.find((g) => g.id === tab)

  return (
    <dialog
      ref={dialogRef}
      className="settings"
      aria-label="Settings"
      onClose={onClose}
      onCancel={(e) => {
        e.preventDefault()
        requestClose()
      }}
    >
      <form
        method="dialog"
        className="settings-form"
        onSubmit={(e) => {
          e.preventDefault()
          void save()
        }}
      >
        <header className="settings-head">
          <div>
            <h2>Settings</h2>
            <p className="settings-lede">Saved values apply to the next round. No restart.</p>
          </div>
          <button type="button" className="settings-close" aria-label="Close settings" title="Close (Esc)" onClick={requestClose}>
            <svg width="20" height="20" viewBox="0 0 20 20" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" aria-hidden="true">
              <path d="M5 5l10 10M15 5L5 15" />
            </svg>
          </button>
        </header>

        {fields === null ? (
          <p className="settings-loading">{notice?.kind === 'error' ? notice.text : 'Loading…'}</p>
        ) : (
          <div className="settings-body">
            <div className="settings-nav" role="tablist" aria-label="Setting groups" aria-orientation="vertical">
              {groups.map((g) => {
                const keys = inGroup(g.id).map((f) => f.key)
                const edited = keys.some((k) => k in changes)
                const refused = keys.filter((k) => {
                  const t = keyTests[k]
                  return t && t !== 'testing' && !t.ok
                }).length
                return (
                  <button
                    key={g.id}
                    type="button"
                    role="tab"
                    id={`settings-tab-${g.id}`}
                    aria-selected={g.id === tab}
                    aria-controls="settings-panel"
                    className="settings-tab"
                    onClick={() => setTab(g.id)}
                  >
                    <span className="settings-tab-title">{g.title}</span>
                    {(edited || refused > 0) && (
                      <span className="settings-tab-note">
                        {[edited && 'edited', refused > 0 && `${refused} refused`].filter(Boolean).join(' · ')}
                      </span>
                    )}
                  </button>
                )
              })}
            </div>
            <section className="settings-panel" id="settings-panel" role="tabpanel" aria-labelledby={`settings-tab-${tab}`}>
              {current && <h3 className="settings-panel-title">{current.title}</h3>}
              {inGroup(tab).map((f) => (
                <Row
                  key={f.key}
                  field={f}
                  value={draft[f.key] ?? ''}
                  placeholder={placeholderFor(f, draft)}
                  suggestions={f.follows ? (f.variants[draft[f.follows]]?.suggestions ?? []) : f.suggestions}
                  idle={!!f.used_when && draft[f.used_when[0]] !== f.used_when[1]}
                  test={keyTests[f.key]}
                  onChange={(v) => edit(f.key, v)}
                  onTest={() => void testKey(f.key)}
                />
              ))}
            </section>
          </div>
        )}

        <footer className="settings-foot">
          <p className={`settings-notice${notice ? ` is-${notice.kind}` : ''}`} role="status">
            {notice ? notice.text : changed > 0 ? `${changed} unsaved ${changed === 1 ? 'change' : 'changes'}` : 'No changes'}
          </p>
          <button type="button" className="btn" onClick={discard} disabled={changed === 0}>
            Discard
          </button>
          <button type="submit" className="btn btn-primary" disabled={saving || changed === 0}>
            {saving ? 'Saving…' : 'Save'}
          </button>
        </footer>

        {confirming && (
          <div className="settings-confirm">
            <div role="alertdialog" aria-labelledby="settings-confirm-title" className="settings-confirm-card">
              <h3 id="settings-confirm-title">Close without saving?</h3>
              <p>
                {changed} unsaved {changed === 1 ? 'change' : 'changes'} will be dropped.
              </p>
              <div className="settings-confirm-actions">
                <button type="button" className="btn" onClick={() => setConfirming(false)} autoFocus>
                  Keep editing
                </button>
                <button
                  type="button"
                  className="btn btn-danger"
                  onClick={() => {
                    setConfirming(false)
                    discard()
                    onClose()
                  }}
                >
                  Discard and close
                </button>
              </div>
            </div>
          </div>
        )}
      </form>
    </dialog>
  )
}

interface RowProps {
  field: SettingField
  value: string
  placeholder: string
  suggestions: string[]
  /** A key whose provider is not selected: kept, but nothing calls it now. */
  idle: boolean
  test: KeyTestState | undefined
  onChange: (value: string) => void
  onTest: () => void
}

function Row({ field, value, placeholder, suggestions, idle, test, onChange, onTest }: RowProps) {
  return (
    <div className={`settings-row${field.testable ? ' is-key' : ''}`}>
      <div className="settings-row-head">
        <label htmlFor={`setting-${field.key}`}>
          <code>{field.key}</code>
        </label>
        {field.help && <InfoTip id={`setting-${field.key}-help`} name={field.key} text={field.help} />}
        <span className="settings-row-gap" />
        <KeyStatus test={test} idle={idle} testable={field.testable} />
      </div>
      <div className="settings-row-control">
        <Control field={field} value={value} suggestions={suggestions} placeholder={placeholder} onChange={onChange} />
        {field.testable && (
          <button type="button" className="settings-test" onClick={onTest} disabled={test === 'testing'}>
            {test === 'testing' ? 'Testing…' : 'Test'}
          </button>
        )}
      </div>
    </div>
  )
}

/** An ⓘ that shows what the setting does on hover or keyboard focus. */
function InfoTip({ id, name, text }: { id: string; name: string; text: string }) {
  return (
    <span className="settings-info">
      <button type="button" className="settings-info-button" aria-label={`About ${name}`} aria-describedby={id}>
        <svg width="16" height="16" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.4" aria-hidden="true">
          <circle cx="8" cy="8" r="6.5" />
          <path d="M8 7.2v4" strokeLinecap="round" />
          <circle cx="8" cy="4.9" r="0.4" fill="currentColor" />
        </svg>
      </button>
      <span role="tooltip" id={id} className="settings-tip">
        {text}
      </span>
    </span>
  )
}

function KeyStatus({ test, idle, testable }: { test: KeyTestState | undefined; idle: boolean; testable: boolean }) {
  if (test === 'testing') return <span className="settings-chip is-testing">Checking…</span>
  if (test)
    return (
      <span className={`settings-chip is-${test.ok ? 'ok' : 'error'}`} role="status">
        {test.ok ? '✓ ' : '✗ '}
        {test.message}
      </span>
    )
  if (idle) return <span className="settings-chip">Not in use now</span>
  return testable ? <span className="settings-chip">Not checked</span> : null
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
