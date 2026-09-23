import { useRef, useState } from 'react'
import { Button, ComboBox, Input, ListBox, ListBoxItem, Popover, Select, SelectValue } from 'react-aria-components'
import type { SettingOption } from '../types'
import './Choice.css'

/** One menu row: the name, the id when the name differs, and a one-line description. */
function OptionRow({ option, textValue }: { option: SettingOption; textValue?: string }) {
  const name = option.label || option.id
  return (
    <ListBoxItem id={option.id} textValue={textValue ?? name} className="choice-item">
      <span className="choice-item-name">
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
}

/**
 * A model id: pick one the provider lists, or type one it does not list yet.
 * Opening shows the whole list; it narrows only to what is typed after that.
 */
export function ModelCombo({ labelledBy, options, value, onChange, placeholder }: ModelComboProps) {
  const [typed, setTyped] = useState(false)
  const toggle = useRef<HTMLButtonElement>(null)
  const needle = value.trim().toLowerCase()
  const shown = typed && needle
    ? options.filter((o) => `${o.id} ${o.label} ${o.description}`.toLowerCase().includes(needle))
    : options
  return (
    <ComboBox
      className="choice"
      aria-labelledby={labelledBy}
      items={shown}
      inputValue={value}
      selectedKey={options.some((o) => o.id === value) ? value : null}
      onInputChange={(v) => {
        setTyped(true)
        onChange(v)
      }}
      onSelectionChange={(key) => key !== null && onChange(String(key))}
      onOpenChange={(open) => open && setTyped(false)}
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
        <ListBox className="choice-list" renderEmptyState={() => <p className="choice-empty">No listed model matches. It is saved as typed.</p>}>
          {(o: SettingOption) => <OptionRow option={o} textValue={o.id} />}
        </ListBox>
      </Popover>
    </ComboBox>
  )
}
