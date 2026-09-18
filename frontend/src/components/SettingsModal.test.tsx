import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { api } from '../api'
import type { SettingField } from '../types'
import { SettingsModal } from './SettingsModal'

vi.mock('../api', () => ({ api: { getSettings: vi.fn(), putSettings: vi.fn() } }))

function field(partial: Partial<SettingField> & Pick<SettingField, 'key' | 'group'>): SettingField {
  return {
    value: '',
    source: 'default',
    secret: false,
    default: '',
    choices: null,
    suggestions: [],
    ...partial,
  }
}

const FIELDS: SettingField[] = [
  field({ key: 'VOICE_PROVIDER', group: 'voice', value: 'openai', choices: ['openai', 'gemini'] }),
  field({
    key: 'VOICE_MODEL',
    group: 'voice',
    suggestions: ['gpt-live-1', 'gemini-3.8-live', 'gemini-3.8-live-extended-thinking'],
  }),
  field({ key: 'VOICE_THINKING', group: 'voice', value: 'low', default: 'low', choices: ['low', 'medium', 'high'] }),
  field({ key: 'VOICE_NAME', group: 'voice', value: 'Kore', default: 'Kore' }),
  field({ key: 'OPENAI_API_KEY', group: 'voice', value: '…1234', source: 'env', secret: true }),
  field({ key: 'GEMINI_API_KEY', group: 'voice', secret: true }),
  field({ key: 'CLAUDE_MODEL', group: 'claude', value: 'sonnet', source: 'db', default: 'opus', suggestions: ['opus', 'sonnet'] }),
  field({ key: 'SUMMARY_MODEL', group: 'text', value: 'gpt-5.6-luna', default: 'gpt-5.6-luna' }),
]

beforeEach(() => {
  vi.mocked(api.getSettings).mockReset().mockResolvedValue({ fields: FIELDS })
  vi.mocked(api.putSettings).mockReset().mockImplementation(async () => ({ fields: FIELDS }))
})

async function open() {
  render(<SettingsModal open onClose={() => undefined} />)
  await screen.findByLabelText(/VOICE_PROVIDER/)
}

describe('SettingsModal', () => {
  it('shows each field with its source and masks secrets as placeholders', async () => {
    await open()
    const key = screen.getByLabelText(/OPENAI_API_KEY/) as HTMLInputElement
    expect(key.type).toBe('password')
    expect(key.value).toBe('')
    expect(key.placeholder).toBe('…1234')
    expect(screen.getByLabelText(/OPENAI_API_KEY/).closest('.settings-row')).toHaveTextContent('env')
    expect(screen.getByLabelText(/CLAUDE_MODEL/).closest('.settings-row')).toHaveTextContent('db')
  })

  it('hides the Gemini-only fields under OpenAI and shows them once the provider flips', async () => {
    await open()
    expect(screen.queryByLabelText(/VOICE_NAME/)).not.toBeInTheDocument()
    expect(screen.queryByLabelText(/VOICE_THINKING/)).not.toBeInTheDocument()

    await userEvent.selectOptions(screen.getByLabelText(/VOICE_PROVIDER/), 'gemini')
    expect(screen.getByLabelText(/VOICE_NAME/)).toBeInTheDocument()
    // Default Gemini model is the extended-thinking one, so the level shows.
    expect(screen.getByLabelText(/VOICE_THINKING/)).toBeInTheDocument()
    const model = screen.getByLabelText(/VOICE_MODEL/) as HTMLInputElement
    expect(model.placeholder).toBe('gemini-3.8-live-extended-thinking')
    const options = Array.from(document.querySelectorAll('#setting-VOICE_MODEL-options option')).map((o) =>
      o.getAttribute('value'),
    )
    expect(options).toEqual(['gemini-3.8-live', 'gemini-3.8-live-extended-thinking'])

    await userEvent.type(model, 'gemini-3.8-live')
    expect(screen.queryByLabelText(/VOICE_THINKING/)).not.toBeInTheDocument()
  })

  it('saves only what changed, sending a typed secret and a reset as null', async () => {
    await open()
    expect(screen.getByRole('button', { name: 'Save' })).toBeDisabled()

    await userEvent.selectOptions(screen.getByLabelText(/VOICE_PROVIDER/), 'gemini')
    await userEvent.type(screen.getByLabelText(/GEMINI_API_KEY/), 'AIza-new')
    await userEvent.click(screen.getByRole('button', { name: 'Reset' }))
    await userEvent.click(screen.getByRole('button', { name: 'Save' }))

    await waitFor(() => expect(api.putSettings).toHaveBeenCalledTimes(1))
    expect(vi.mocked(api.putSettings).mock.calls[0][0]).toEqual({
      VOICE_PROVIDER: 'gemini',
      GEMINI_API_KEY: 'AIza-new',
      CLAUDE_MODEL: null,
    })
    expect(await screen.findByRole('status')).toHaveTextContent('Saved')
  })

  it('shows the backend error when saving fails', async () => {
    vi.mocked(api.putSettings).mockRejectedValueOnce(new Error('VOICE_PROVIDER must be one of openai, gemini'))
    await open()
    await userEvent.selectOptions(screen.getByLabelText(/VOICE_PROVIDER/), 'gemini')
    await userEvent.click(screen.getByRole('button', { name: 'Save' }))
    expect(await screen.findByRole('status')).toHaveTextContent('must be one of')
  })
})
