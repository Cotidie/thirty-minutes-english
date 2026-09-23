import { useEffect, useMemo, useRef, useState } from 'react'
import { UNSAFE_PortalProvider } from 'react-aria'
import { api } from '../api'
import type { KeyTestResult, SettingField, SettingGroup, SettingOption, SettingsUpdate } from '../types'
import { ChoiceSelect, ModelCombo } from './Choice'
import './SettingsModal.css'

interface Props {
  open: boolean
  onClose: () => void
}

type KeyTestState = KeyTestResult | 'testing'

/** What a field's control offers right now: its menu, the placeholder, and why it is off, if it is. */
interface Menu {
  options: SettingOption[]
  placeholder: string
  /** The model list the options come from, for pinning. */
  catalog?: string
  off?: string
}

/**
 * A model field follows its provider; an effort field offers what the chosen Claude
 * model takes (all levels any listed model takes when that model is not listed).
 */
function menuFor(f: SettingField, draft: Record<string, string>, byKey: Map<string, SettingField>): Menu {
  if (f.follows) {
    const variant = f.variants[draft[f.follows]]
    return {
      options: variant?.options ?? [],
      placeholder: variant?.default ?? '',
      catalog: variant?.catalog,
    }
  }
  if (f.effort_of) {
    const model = byKey.get(f.effort_of)
    const picked = draft[f.effort_of] || model?.default || ''
    const listed = model?.options.find((o) => o.id === picked)
    if (listed?.efforts?.length === 0)
      return {
        options: [],
        placeholder: '',
        off: `${listed.label || picked} takes no effort level`,
      }
    const levels = listed?.efforts ?? [...new Set((model?.options ?? []).flatMap((o) => o.efforts ?? []))]
    return {
      options: levels.map((id) => ({
        id,
        label: '',
        description: '',
        efforts: null,
      })),
      placeholder: f.default,
    }
  }
  if (f.secret)
    return {
      options: [],
      placeholder: f.value ? `Saved: ${f.value}. Type to replace.` : 'Not set',
    }
  return { options: f.options, placeholder: f.default, catalog: f.catalog ?? undefined }
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
  const [notice, setNotice] = useState<{
    kind: 'ok' | 'error'
    text: string
  } | null>(null)
  const [confirming, setConfirming] = useState(false)
  const [refreshing, setRefreshing] = useState(false)

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
      (e: unknown) =>
        live &&
        setNotice({
          kind: 'error',
          text: e instanceof Error ? e.message : String(e),
        }),
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
      setKeyTests((t) => ({
        ...t,
        [key]: {
          ok: false,
          message: e instanceof Error ? e.message : String(e),
        },
      }))
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
      setNotice({
        kind: 'error',
        text: e instanceof Error ? e.message : String(e),
      })
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
  const byKey = new Map((fields ?? []).map((f) => [f.key, f]))
  const hasModels = inGroup(tab).some((f) => f.free)

  const pin = async (catalog: string, model: string, pinned: boolean) => {
    try {
      setFields((await api.pinModel(catalog, model, pinned)).fields)
    } catch (e) {
      setNotice({ kind: 'error', text: e instanceof Error ? e.message : String(e) })
    }
  }

  const refreshModels = async () => {
    setRefreshing(true)
    try {
      setFields((await api.refreshModels()).fields)
    } catch (e) {
      setNotice({
        kind: 'error',
        text: e instanceof Error ? e.message : String(e),
      })
    } finally {
      setRefreshing(false)
    }
  }

  return (
    <dialog
      ref={dialogRef}
      className="settings"
      aria-label="Settings"
      onClose={onClose}
      onCancel={(e) => {
        e.preventDefault()
        // Esc with a menu open closes just the menu (react-aria handles that); it is not a request to leave.
        if (!dialogRef.current?.querySelector('.choice-popover')) requestClose()
      }}
    >
      {/* Popovers go inside the dialog: a modal <dialog> sits in the top layer, above anything in <body>. */}
      <UNSAFE_PortalProvider getContainer={() => dialogRef.current}>
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
            <button
              type="button"
              className="settings-close"
              aria-label="Close settings"
              title="Close (Esc)"
              onClick={requestClose}
            >
              <svg
                width="20"
                height="20"
                viewBox="0 0 20 20"
                fill="none"
                stroke="currentColor"
                strokeWidth="1.8"
                strokeLinecap="round"
                aria-hidden="true"
              >
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
              <section
                className="settings-panel"
                id="settings-panel"
                role="tabpanel"
                aria-labelledby={`settings-tab-${tab}`}
              >
                <div className="settings-panel-head">
                  {current && <h3 className="settings-panel-title">{current.title}</h3>}
                  {hasModels && (
                    <button
                      type="button"
                      className="btn-link settings-refresh"
                      onClick={() => void refreshModels()}
                      disabled={refreshing}
                    >
                      {refreshing ? 'Refreshing model lists…' : 'Refresh model lists'}
                    </button>
                  )}
                </div>
                {inGroup(tab).map((f) => (
                  <Row
                    key={f.key}
                    field={f}
                    value={draft[f.key] ?? ''}
                    menu={menuFor(f, draft, byKey)}
                    idle={!!f.used_when && draft[f.used_when[0]] !== f.used_when[1]}
                    test={keyTests[f.key]}
                    onChange={(v) => edit(f.key, v)}
                    onPin={(catalog, model, pinned) => void pin(catalog, model, pinned)}
                    onTest={() => void testKey(f.key)}
                  />
                ))}
              </section>
            </div>
          )}

          <footer className="settings-foot">
            <p className={`settings-notice${notice ? ` is-${notice.kind}` : ''}`} role="status">
              {notice
                ? notice.text
                : changed > 0
                  ? `${changed} unsaved ${changed === 1 ? 'change' : 'changes'}`
                  : 'No changes'}
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
      </UNSAFE_PortalProvider>
    </dialog>
  )
}

interface RowProps {
  field: SettingField
  value: string
  menu: Menu
  /** A key whose provider is not selected: kept, but nothing calls it now. */
  idle: boolean
  test: KeyTestState | undefined
  onChange: (value: string) => void
  onTest: () => void
  onPin: (catalog: string, model: string, pinned: boolean) => void
}

function Row({ field, value, menu, idle, test, onChange, onTest, onPin }: RowProps) {
  const id = `setting-${field.key}`
  return (
    <div className={`settings-row${field.testable ? ' is-key' : ''}`}>
      <div className="settings-row-head">
        <label id={`${id}-label`} htmlFor={id}>
          <code>{field.key}</code>
        </label>
        {field.help && <InfoTip id={`${id}-help`} name={field.key} text={field.help} />}
        <span className="settings-row-gap" />
        <KeyStatus test={test} idle={idle} testable={field.testable} />
      </div>
      <div className="settings-row-control">
        <Control id={id} field={field} value={value} menu={menu} onChange={onChange} onPin={onPin} />
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
        <svg
          width="16"
          height="16"
          viewBox="0 0 16 16"
          fill="none"
          stroke="currentColor"
          strokeWidth="1.4"
          aria-hidden="true"
        >
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
  id: string
  field: SettingField
  value: string
  menu: Menu
  onChange: (value: string) => void
  onPin: (catalog: string, model: string, pinned: boolean) => void
}

function Control({ id, field, value, menu, onChange, onPin }: ControlProps) {
  const labelledBy = `${id}-label`
  if (field.multi) return <MultiPick id={id} field={field} value={value} onChange={onChange} />
  if (field.free)
    return (
      <ModelCombo
        labelledBy={labelledBy}
        options={menu.options}
        value={value}
        placeholder={menu.placeholder}
        onChange={onChange}
        onPin={menu.catalog ? (model, pinned) => onPin(menu.catalog!, model, pinned) : undefined}
      />
    )
  if (menu.off || menu.options.length > 0 || field.effort_of)
    return (
      <ChoiceSelect
        labelledBy={labelledBy}
        options={menu.options}
        value={value}
        placeholder={menu.off}
        disabled={!!menu.off}
        onChange={onChange}
      />
    )
  return (
    <input
      id={id}
      type={field.secret ? 'password' : 'text'}
      autoComplete="off"
      value={value}
      placeholder={menu.placeholder}
      onChange={(e) => onChange(e.target.value)}
    />
  )
}

/** A comma list ticked from `options`, each shown with its description; a filter narrows a long list. */
function MultiPick({
  id,
  field,
  value,
  onChange,
}: {
  id: string
  field: SettingField
  value: string
  onChange: (value: string) => void
}) {
  const [filter, setFilter] = useState('')
  const picked = value
    .split(',')
    .map((s) => s.trim())
    .filter(Boolean)
  const choices = field.options.map((o) => o.id)
  const describe = new Map(field.options.map((o) => [o.id, o.description]))
  const needle = filter.trim().toLowerCase()
  const shown = choices.filter((c) => !needle || `${c} ${describe.get(c) ?? ''}`.toLowerCase().includes(needle))
  const toggle = (name: string) =>
    onChange(choices.filter((c) => (c === name ? !picked.includes(c) : picked.includes(c))).join(','))

  return (
    <div className="settings-multi">
      <div className="settings-multi-bar">
        <input
          id={id}
          type="search"
          autoComplete="off"
          placeholder={`Filter ${choices.length} skills`}
          value={filter}
          onChange={(e) => setFilter(e.target.value)}
        />
        <span className="settings-multi-count">{picked.length === 0 ? 'None ticked' : `${picked.length} ticked`}</span>
      </div>
      <ul className="settings-multi-list" aria-label={`${field.key} choices`}>
        {shown.map((name) => (
          <li key={name}>
            <label className="settings-multi-item">
              <input type="checkbox" checked={picked.includes(name)} onChange={() => toggle(name)} />
              <span>
                <span className="settings-multi-name">{name}</span>
                {describe.get(name) && <span className="settings-multi-desc">{describe.get(name)}</span>}
              </span>
            </label>
          </li>
        ))}
        {shown.length === 0 && <li className="settings-multi-empty">No skill matches “{filter}”.</li>}
      </ul>
    </div>
  )
}

/** jsdom has no showModal; the attribute keeps the tests honest. */
function showDialog(dialog: HTMLDialogElement) {
  if (typeof dialog.showModal === 'function') dialog.showModal()
  else dialog.setAttribute('open', '')
}
