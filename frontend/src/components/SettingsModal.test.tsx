import { render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { api } from '../api'
import type { SettingField } from '../types'
import { SettingsModal } from './SettingsModal'

vi.mock('../api', () => ({ api: { getSettings: vi.fn(), putSettings: vi.fn(), testKey: vi.fn() } }))

function field(partial: Partial<SettingField> & Pick<SettingField, 'key' | 'group'>): SettingField {
  return {
    value: '',
    secret: false,
    default: '',
    choices: null,
    suggestions: [],
    labels: {},
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
  field({
    key: 'VOICE_NAME',
    group: 'voice',
    value: 'Kore',
    default: 'Kore',
    choices: ['Kore', 'Puck'],
    labels: { Kore: 'Firm', Puck: 'Upbeat' },
  }),
  field({ key: 'OPENAI_API_KEY', group: 'voice', value: '…1234', secret: true }),
  field({ key: 'GEMINI_API_KEY', group: 'voice', secret: true }),
  field({ key: 'CLAUDE_MODEL', group: 'claude', value: 'sonnet', default: 'opus', suggestions: ['opus', 'sonnet'] }),
  field({ key: 'SUMMARY_MODEL', group: 'text', value: 'gpt-5.6-luna', default: 'gpt-5.6-luna' }),
]

beforeEach(() => {
  vi.mocked(api.getSettings).mockReset().mockResolvedValue({ fields: FIELDS })
  vi.mocked(api.putSettings).mockReset().mockImplementation(async () => ({ fields: FIELDS }))
  vi.mocked(api.testKey).mockReset()
})

async function open() {
  render(<SettingsModal open onClose={() => undefined} />)
  await screen.findByLabelText(/VOICE_PROVIDER/)
}

describe('SettingsModal', () => {
  it('shows the effective value and masks secrets as placeholders', async () => {
    await open()
    const key = screen.getByLabelText(/OPENAI_API_KEY/) as HTMLInputElement
    expect(key.type).toBe('password')
    expect(key.value).toBe('')
    expect(key.placeholder).toBe('…1234')
    expect((screen.getByLabelText(/CLAUDE_MODEL/) as HTMLInputElement).value).toBe('sonnet')
  })

  it('hides the Gemini-only fields under OpenAI and shows them once the provider flips', async () => {
    await open()
    expect(screen.queryByLabelText(/VOICE_NAME/)).not.toBeInTheDocument()
    expect(screen.queryByLabelText(/VOICE_THINKING/)).not.toBeInTheDocument()

    await userEvent.selectOptions(screen.getByLabelText(/VOICE_PROVIDER/), 'gemini')
    const voice = screen.getByLabelText(/VOICE_NAME/) as HTMLSelectElement
    expect(voice.tagName).toBe('SELECT')
    expect(Array.from(voice.options).map((o) => o.textContent)).toEqual(['Kore · Firm', 'Puck · Upbeat'])
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

  it('saves only what changed, including a typed secret', async () => {
    await open()
    expect(screen.getByRole('button', { name: 'Save' })).toBeDisabled()

    await userEvent.selectOptions(screen.getByLabelText(/VOICE_PROVIDER/), 'gemini')
    await userEvent.type(screen.getByLabelText(/GEMINI_API_KEY/), 'AIza-new')
    await userEvent.click(screen.getByRole('button', { name: 'Save' }))

    await waitFor(() => expect(api.putSettings).toHaveBeenCalledTimes(1))
    expect(vi.mocked(api.putSettings).mock.calls[0][0]).toEqual({
      VOICE_PROVIDER: 'gemini',
      GEMINI_API_KEY: 'AIza-new',
    })
    expect(await screen.findByRole('status')).toHaveTextContent('Saved')
  })

  it('tests the typed key and shows the verdict beside it', async () => {
    vi.mocked(api.testKey).mockResolvedValueOnce({ ok: false, message: '401: Incorrect API key provided' })
    await open()
    const row = screen.getByLabelText(/OPENAI_API_KEY/).closest<HTMLElement>('.settings-row')!
    await userEvent.type(screen.getByLabelText(/OPENAI_API_KEY/), 'sk-typed')
    await userEvent.click(within(row).getByRole('button', { name: 'Test' }))

    expect(api.testKey).toHaveBeenCalledWith('OPENAI_API_KEY', 'sk-typed')
    expect(await within(row).findByRole('status')).toHaveTextContent('✗ 401: Incorrect API key provided')

    vi.mocked(api.testKey).mockResolvedValueOnce({ ok: true, message: 'key works' })
    await userEvent.click(within(row).getByRole('button', { name: 'Test' }))
    expect(await within(row).findByRole('status')).toHaveTextContent('✓ key works')
  })

  it('shows the backend error when saving fails', async () => {
    vi.mocked(api.putSettings).mockRejectedValueOnce(new Error('VOICE_PROVIDER must be one of openai, gemini'))
    await open()
    await userEvent.selectOptions(screen.getByLabelText(/VOICE_PROVIDER/), 'gemini')
    await userEvent.click(screen.getByRole('button', { name: 'Save' }))
    expect(await screen.findByRole('status')).toHaveTextContent('must be one of')
  })
})
