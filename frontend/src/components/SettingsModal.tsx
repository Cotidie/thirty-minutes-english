import { useEffect, useMemo, useRef, useState } from 'react'
import { api } from '../api'
import type { SettingField, SettingGroup, SettingsUpdate } from '../types'

interface Props {
  open: boolean
  onClose: () => void
}

const GROUP_TITLE: Record<SettingGroup, string> = {
  voice: 'Voice coach',
  claude: 'Claude generation',
  text: 'Summary text model',
}

const PROVIDER_MODEL_DEFAULT: Record<string, string> = {
  openai: 'gpt-live-1',
  gemini: 'gemini-3.8-live-extended-thinking',
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
  const [draft, setDraft] = useState<Record<string, string>>({})
  const [saving, setSaving] = useState(false)
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
    api.getSettings().then(
      ({ fields }) => {
        if (!live) return
        setFields(fields)
        setDraft(Object.fromEntries(fields.map((f) => [f.key, f.secret ? '' : f.value])))
      },
      (e: unknown) => live && setNotice({ kind: 'error', text: e instanceof Error ? e.message : String(e) }),
    )
    return () => {
      live = false
    }
  }, [open])

  const provider = draft.VOICE_PROVIDER ?? 'openai'
  const effectiveModel = draft.VOICE_MODEL || PROVIDER_MODEL_DEFAULT[provider] || ''
  const changes = useMemo<SettingsUpdate>(() => {
    const update: SettingsUpdate = {}
    for (const f of fields ?? []) {
      if (f.secret ? draft[f.key] !== '' : draft[f.key] !== f.value) update[f.key] = draft[f.key]
    }
    return update
  }, [draft, fields])

  const edit = (key: string, value: string) => setDraft((d) => ({ ...d, [key]: value }))

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

  const visible = (f: SettingField): boolean => {
    if (f.key === 'VOICE_NAME') return provider === 'gemini'
    if (f.key === 'VOICE_THINKING') return effectiveModel.endsWith('-extended-thinking')
    return true
  }

  const suggestionsFor = (f: SettingField): string[] => {
    if (f.key !== 'VOICE_MODEL') return f.suggestions
    return f.suggestions.filter((m) => (provider === 'gemini' ? m.startsWith('gemini') : !m.startsWith('gemini')))
  }

  const groups = (['voice', 'claude', 'text'] as const).map((g) => ({
    group: g,
    fields: (fields ?? []).filter((f) => f.group === g && visible(f)),
  }))

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
          groups.map(({ group, fields }) => (
            <fieldset key={group} className="settings-group">
              <legend>{GROUP_TITLE[group]}</legend>
              {fields.map((f) => (
                <div key={f.key} className="settings-row">
                  <label htmlFor={`setting-${f.key}`}>
                    <code>{f.key}</code>
                  </label>
                  <Control
                    field={f}
                    value={draft[f.key] ?? ''}
                    suggestions={suggestionsFor(f)}
                    placeholder={f.key === 'VOICE_MODEL' ? PROVIDER_MODEL_DEFAULT[provider] : f.secret ? f.value || 'not set' : f.default}
                    onChange={(v) => edit(f.key, v)}
                  />
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
