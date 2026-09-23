import { useRef, useState } from 'react'
import {
  Button,
  ComboBox,
  Header,
  Input,
  ListBox,
  ListBoxItem,
  ListBoxSection,
  Popover,
  Select,
  SelectValue,
} from 'react-aria-components'
import type { SettingOption } from '../types'
import './Choice.css'

/** One menu row: the name (marked when pinned), the id when the name differs, and a one-line description. */
function OptionRow({ option, textValue }: { option: SettingOption; textValue?: string }) {
  const name = option.label || option.id
  return (
    <ListBoxItem id={option.id} textValue={textValue ?? name} className="choice-item">
      <span className="choice-item-name">
        {option.pinned && (
          <span className="choice-item-pin" role="img" aria-label="Pinned">
            <PinIcon filled />
          </span>
        )}
        {name}
        {option.label && option.label !== option.id && <code className="choice-item-id">{option.id}</code>}
      </span>
      {option.description && <span className="choice-item-desc">{option.description}</span>}
    </ListBoxItem>
  )
}

function Chevron() {
  return (
    <svg width="14" height="14" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.6" aria-hidden="true">
      <path d="M4 6l4 4 4-4" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  )
}

interface ChoiceSelectProps {
  labelledBy: string
  options: SettingOption[]
  value: string
  onChange: (value: string) => void
  /** Shown instead of a value, e.g. why the field is off. */
  placeholder?: string
  disabled?: boolean
}

/** A strict pick from `options`. */
export function ChoiceSelect({ labelledBy, options, value, onChange, placeholder, disabled }: ChoiceSelectProps) {
  return (
    <Select
      className="choice"
      aria-labelledby={labelledBy}
      selectedKey={disabled ? null : value || null}
      onSelectionChange={(key) => key !== null && onChange(String(key))}
      placeholder={placeholder}
      isDisabled={disabled}
    >
      <Button className="choice-field">
        <SelectValue className="choice-value" />
        <Chevron />
      </Button>
      <Popover className="choice-popover">
        <ListBox className="choice-list" items={options}>
          {(o) => <OptionRow option={o} />}
        </ListBox>
      </Popover>
    </Select>
  )
}

interface ModelComboProps {
  labelledBy: string
  options: SettingOption[]
  value: string
  onChange: (value: string) => void
  placeholder: string
  /** Pins or unpins a model on this list; no pin button without it. */
  onPin?: (model: string, pinned: boolean) => void
}

export function PinIcon({ filled }: { filled: boolean }) {
  return (
    <svg width="15" height="15" viewBox="0 0 16 16" fill={filled ? 'currentColor' : 'none'} stroke="currentColor" strokeWidth="1.4" aria-hidden="true">
      <path d="M6 2h4l-.6 4 2.6 2.4V10H4V8.4L6.6 6 6 2z" strokeLinejoin="round" />
      <path d="M8 10v4" strokeLinecap="round" />
    </svg>
  )
}

/**
 * A model id: pick one the provider lists, or type one it does not list yet. Pinned models
 * lead the menu. Opening shows the whole list; it narrows only to what is typed after that.
 */
export function ModelCombo({ labelledBy, options, value, onChange, placeholder, onPin }: ModelComboProps) {
  const [typed, setTyped] = useState(false)
  const toggle = useRef<HTMLButtonElement>(null)
  const current = value || placeholder
  const chosen = options.find((o) => o.id === current)
  const needle = value.trim().toLowerCase()
  const shown = typed && needle ? options.filter((o) => `${o.id} ${o.label}`.toLowerCase().includes(needle)) : options
  const pinned = shown.filter((o) => o.pinned)
  const rest = shown.filter((o) => !o.pinned)
  const isPinned = !!chosen?.pinned
  return (
    <div className="choice-model">
      <ComboBox
        className="choice"
        aria-labelledby={labelledBy}
        inputValue={value}
        selectedKey={options.some((o) => o.id === value) ? value : null}
        onInputChange={(v) => {
          setTyped(true)
          onChange(v)
        }}
        onSelectionChange={(key) => key !== null && onChange(String(key))}
        onOpenChange={(open) => open && setTyped(false)}
        defaultFilter={() => true} // the list above is already narrowed
        allowsCustomValue
        allowsEmptyCollection
        menuTrigger="focus"
      >
        <div className="choice-field">
          <Input
            className="choice-input"
            placeholder={placeholder}
            // A click on the text opens the list too, not only the chevron.
            onClick={(e) => e.currentTarget.getAttribute('aria-expanded') !== 'true' && toggle.current?.click()}
          />
          <Button ref={toggle} className="choice-toggle" aria-label="Show models">
            <Chevron />
          </Button>
        </div>
        <Popover className="choice-popover">
          <ListBox
            className="choice-list"
            renderEmptyState={() => <p className="choice-empty">No listed model matches. It is saved as typed.</p>}
          >
            {pinned.length > 0 && (
              <ListBoxSection className="choice-section">
                <Header className="choice-section-head">Pinned</Header>
                {pinned.map((o) => (
                  <OptionRow key={o.id} option={o} textValue={o.id} />
                ))}
              </ListBoxSection>
            )}
            {rest.length > 0 && (
              <ListBoxSection className="choice-section">
                {pinned.length > 0 && <Header className="choice-section-head">Newest</Header>}
                {rest.map((o) => (
                  <OptionRow key={o.id} option={o} textValue={o.id} />
                ))}
              </ListBoxSection>
            )}
          </ListBox>
        </Popover>
      </ComboBox>
      {onPin && current && (
        <button
          type="button"
          className={`choice-pin${isPinned ? ' is-on' : ''}`}
          aria-pressed={isPinned}
          aria-label={`${isPinned ? 'Unpin' : 'Pin'} ${current}`}
          title={isPinned ? 'Unpin: let it drop off when newer models come out' : 'Pin: keep it at the top of this menu'}
          onClick={() => onPin(current, !isPinned)}
        >
          <PinIcon filled={isPinned} />
        </button>
      )}
    </div>
  )
}
