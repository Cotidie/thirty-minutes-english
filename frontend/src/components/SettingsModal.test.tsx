import { render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { api } from '../api'
import type { SettingField, SettingGroup } from '../types'
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
    testable: false,
    follows: null,
    variants: {},
    shown_when: null,
    ...partial,
  }
}

const FIELDS: SettingField[] = [
  field({ key: 'VOICE_PROVIDER', group: 'voice', value: 'openai', choices: ['openai', 'gemini'] }),
  field({
    key: 'VOICE_MODEL',
    group: 'voice',
    follows: 'VOICE_PROVIDER',
    variants: {
      openai: { default: 'gpt-live-1', suggestions: ['gpt-live-1'] },
      gemini: { default: 'gemini-3.8-live-extended-thinking', suggestions: ['gemini-3.8-live-extended-thinking', 'gemini-3.8-live'] },
    },
  }),
  field({
    key: 'VOICE_THINKING',
    group: 'voice',
    value: 'low',
    default: 'low',
    choices: ['low', 'medium', 'high'],
    shown_when: ['VOICE_PROVIDER', 'gemini'],
  }),
  field({
    key: 'VOICE_NAME',
    group: 'voice',
    value: 'Kore',
    default: 'Kore',
    choices: ['Kore', 'Puck'],
    labels: { Kore: 'Firm', Puck: 'Upbeat' },
    shown_when: ['VOICE_PROVIDER', 'gemini'],
  }),
  field({ key: 'OPENAI_API_KEY', group: 'keys', value: '…1234', secret: true, testable: true }),
  field({ key: 'GEMINI_API_KEY', group: 'keys', secret: true, testable: true }),
  field({ key: 'AZURE_SPEECH_KEY', group: 'keys', secret: true, testable: true }),
  field({ key: 'AZURE_SPEECH_REGION', group: 'assess', value: 'koreacentral', default: 'koreacentral' }),
  field({ key: 'CLAUDE_MODEL', group: 'claude', value: 'sonnet', default: 'opus', suggestions: ['opus', 'sonnet'] }),
  field({ key: 'SUMMARY_MODEL', group: 'text', value: 'gpt-5.6-luna', default: 'gpt-5.6-luna' }),
]

const GROUPS: SettingGroup[] = [
  { id: 'keys', title: 'API keys' },
  { id: 'voice', title: 'Voice coach' },
  { id: 'assess', title: 'Read aloud assessor' },
  { id: 'claude', title: 'Claude generation' },
  { id: 'text', title: 'Summary text model' },
]

beforeEach(() => {
  vi.mocked(api.getSettings).mockReset().mockResolvedValue({ groups: GROUPS, fields: FIELDS })
  vi.mocked(api.putSettings).mockReset().mockImplementation(async () => ({ groups: GROUPS, fields: FIELDS }))
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
    const legends = Array.from(document.querySelectorAll('legend')).map((l) => l.textContent)
    expect(legends).toEqual(GROUPS.map((g) => g.title))
  })

  it('hides the Gemini-only fields under OpenAI and shows them once the provider flips', async () => {
    await open()
    expect(screen.queryByLabelText(/VOICE_NAME/)).not.toBeInTheDocument()
    expect(screen.queryByLabelText(/VOICE_THINKING/)).not.toBeInTheDocument()

    await userEvent.selectOptions(screen.getByLabelText(/VOICE_PROVIDER/), 'gemini')
    const voice = screen.getByLabelText(/VOICE_NAME/) as HTMLSelectElement
    expect(voice.tagName).toBe('SELECT')
    expect(Array.from(voice.options).map((o) => o.textContent)).toEqual(['Kore · Firm', 'Puck · Upbeat'])
    expect(screen.getByLabelText(/VOICE_THINKING/)).toBeInTheDocument()
    const model = screen.getByLabelText(/VOICE_MODEL/) as HTMLInputElement
    expect(model.placeholder).toBe('gemini-3.8-live-extended-thinking')
    const options = Array.from(document.querySelectorAll('#setting-VOICE_MODEL-options option')).map((o) =>
      o.getAttribute('value'),
    )
    expect(options).toEqual(['gemini-3.8-live-extended-thinking', 'gemini-3.8-live'])
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

describe('SettingsModal assessor', () => {
  it('shows the assessor group and a Test button beside the Azure key', async () => {
    vi.mocked(api.testKey).mockResolvedValueOnce({ ok: true, message: 'key works' })
    await open()
    expect(screen.getByText('Read aloud assessor')).toBeInTheDocument()
    expect(screen.getByLabelText(/AZURE_SPEECH_REGION/)).toHaveValue('koreacentral')
    const row = screen.getByLabelText(/AZURE_SPEECH_KEY/).closest<HTMLElement>('.settings-row')!
    await userEvent.click(within(row).getByRole('button', { name: 'Test' }))
    expect(api.testKey).toHaveBeenCalledWith('AZURE_SPEECH_KEY', '')
    expect(await within(row).findByRole('status')).toHaveTextContent('✓ key works')
  })
})
