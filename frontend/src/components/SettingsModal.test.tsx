import { render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { api } from '../api'
import type { SettingField, SettingGroup } from '../types'
import { SettingsModal } from './SettingsModal'

vi.mock('../api', () => ({ api: { getSettings: vi.fn(), putSettings: vi.fn(), testKey: vi.fn(), refreshModels: vi.fn() } }))

const opt = (id: string, description = '', label = '', efforts: string[] | null = null) => ({ id, label, description, efforts })

function field(partial: Partial<SettingField> & Pick<SettingField, 'key' | 'group'>): SettingField {
  return {
    value: '',
    secret: false,
    default: '',
    options: [],
    free: false,
    testable: false,
    follows: null,
    variants: {},
    effort_of: null,
    shown_when: null,
    used_when: null,
    help: '',
    multi: false,
    ...partial,
  }
}

const FIELDS: SettingField[] = [
  field({ key: 'VOICE_PROVIDER', group: 'voice', value: 'openai', options: [opt('openai'), opt('gemini')] }),
  field({
    key: 'VOICE_MODEL',
    group: 'voice',
    follows: 'VOICE_PROVIDER',
    free: true,
    variants: {
      openai: { default: 'gpt-live-1', options: [opt('gpt-live-1')] },
      gemini: { default: 'gemini-3.8-live-extended-thinking', options: [opt('gemini-3.8-live-extended-thinking'), opt('gemini-3.8-live')] },
    },
  }),
  field({
    key: 'VOICE_THINKING',
    group: 'voice',
    value: 'low',
    default: 'low',
    options: [opt('low'), opt('medium'), opt('high')],
    shown_when: ['VOICE_PROVIDER', 'gemini'],
  }),
  field({
    key: 'VOICE_NAME',
    group: 'voice',
    value: 'Kore',
    default: 'Kore',
    options: [opt('Kore', 'Firm'), opt('Puck', 'Upbeat')],
    shown_when: ['VOICE_PROVIDER', 'gemini'],
  }),
  field({ key: 'OPENAI_API_KEY', group: 'keys', value: '…1234', secret: true, testable: true }),
  field({ key: 'GEMINI_API_KEY', group: 'keys', secret: true, testable: true }),
  field({ key: 'AZURE_SPEECH_KEY', group: 'keys', secret: true, testable: true }),
  field({ key: 'AZURE_SPEECH_REGION', group: 'assess', value: 'koreacentral', default: 'koreacentral' }),
  field({
    key: 'CLAUDE_MODEL',
    group: 'claude',
    value: 'sonnet',
    default: 'opus',
    free: true,
    options: [opt('opus', 'Most capable', 'Opus 5.5', ['low', 'max']), opt('sonnet', 'Efficient', 'Sonnet 5', ['low', 'high']), opt('haiku', 'Fastest', 'Haiku 4.5', [])],
  }),
  field({ key: 'CLAUDE_EFFORT', group: 'claude', value: 'high', default: 'xhigh', effort_of: 'CLAUDE_MODEL' }),
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

async function open(onClose = () => undefined) {
  render(<SettingsModal open onClose={onClose} />)
  await screen.findByLabelText('OPENAI_API_KEY')
}

async function showTab(title: string) {
  await userEvent.click(screen.getByRole('tab', { name: new RegExp(title) }))
}

/** Opens a Select by its setting name and picks one option. */
async function pick(key: string, option: string) {
  await userEvent.click(screen.getByRole('button', { name: new RegExp(`${key}$`) }))
  await userEvent.click(await screen.findByRole('option', { name: new RegExp(`^${option}`) }))
}

function rowOf(label: string): HTMLElement {
  return screen.getByLabelText(label).closest<HTMLElement>('.settings-row')!
}

describe('SettingsModal', () => {
  it('shows one group at a time, secrets masked, the saved value as the placeholder', async () => {
    await open()
    expect(screen.getAllByRole('tab').map((t) => t.textContent)).toEqual(GROUPS.map((g) => g.title))
    const key = screen.getByLabelText('OPENAI_API_KEY') as HTMLInputElement
    expect(key.type).toBe('password')
    expect(key.value).toBe('')
    expect(key.placeholder).toBe('Saved: …1234. Type to replace.')
    expect(screen.queryByLabelText('CLAUDE_MODEL')).not.toBeInTheDocument()

    await showTab('Claude generation')
    expect(screen.getByRole('combobox', { name: 'CLAUDE_MODEL' })).toHaveValue('sonnet')
  })

  it('hides the Gemini-only fields under OpenAI and shows them once the provider flips', async () => {
    await open()
    await showTab('Voice coach')
    expect(screen.queryByLabelText('VOICE_NAME')).not.toBeInTheDocument()
    expect(screen.queryByLabelText('VOICE_THINKING')).not.toBeInTheDocument()

    await pick('VOICE_PROVIDER', 'gemini')
    await userEvent.click(screen.getByRole('button', { name: /VOICE_NAME$/ }))
    expect((await screen.findAllByRole('option')).map((o) => o.textContent)).toEqual(['KoreFirm', 'PuckUpbeat'])
    await userEvent.keyboard('{Escape}')
    expect(screen.getByRole('button', { name: /VOICE_THINKING$/ })).toBeInTheDocument()
    const model = screen.getByRole('combobox', { name: 'VOICE_MODEL' })
    expect(model).toHaveAttribute('placeholder', 'gemini-3.8-live-extended-thinking')
    await userEvent.click(screen.getByRole('button', { name: /^Show models/ }))
    expect((await screen.findAllByRole('option')).map((o) => o.textContent)).toEqual([
      'gemini-3.8-live-extended-thinking',
      'gemini-3.8-live',
    ])
  })

  it('saves only what changed across groups, counts the edits, and discards on request', async () => {
    await open()
    const save = screen.getByRole('button', { name: 'Save' })
    expect(save).toBeDisabled()
    expect(screen.getByText('No changes')).toBeInTheDocument()

    await userEvent.type(screen.getByLabelText('GEMINI_API_KEY'), 'AIza-new')
    await showTab('Voice coach')
    await pick('VOICE_PROVIDER', 'gemini')
    expect(screen.getByText('2 unsaved changes')).toBeInTheDocument()
    expect(screen.getByRole('tab', { name: /API keys/ })).toHaveTextContent('edited')

    await userEvent.click(save)
    await waitFor(() => expect(api.putSettings).toHaveBeenCalledTimes(1))
    expect(vi.mocked(api.putSettings).mock.calls[0][0]).toEqual({
      VOICE_PROVIDER: 'gemini',
      GEMINI_API_KEY: 'AIza-new',
    })
    expect(await screen.findByText('Saved. The next round uses these.')).toBeInTheDocument()

    await pick('VOICE_PROVIDER', 'gemini')
    await userEvent.click(screen.getByRole('button', { name: 'Discard' }))
    expect(screen.getByText('No changes')).toBeInTheDocument()
  })

  it('tests the typed key and shows the verdict on its name line', async () => {
    vi.mocked(api.testKey).mockResolvedValueOnce({ ok: false, message: '401: Incorrect API key provided' })
    await open()
    const row = rowOf('OPENAI_API_KEY')
    expect(row).toHaveTextContent('Not checked')
    await userEvent.type(screen.getByLabelText('OPENAI_API_KEY'), 'sk-typed')
    await userEvent.click(within(row).getByRole('button', { name: 'Test' }))

    expect(api.testKey).toHaveBeenCalledWith('OPENAI_API_KEY', 'sk-typed')
    expect(await within(row).findByRole('status')).toHaveTextContent('✗ 401: Incorrect API key provided')
    expect(screen.getByRole('tab', { name: /API keys/ })).toHaveTextContent('1 refused')

    vi.mocked(api.testKey).mockResolvedValueOnce({ ok: true, message: 'key works' })
    await userEvent.click(within(row).getByRole('button', { name: 'Test' }))
    expect(await within(row).findByRole('status')).toHaveTextContent('✓ key works')
  })

  it('marks a key idle while its provider is not selected', async () => {
    vi.mocked(api.getSettings).mockResolvedValue({
      groups: GROUPS,
      fields: FIELDS.map((f) => (f.key === 'GEMINI_API_KEY' ? { ...f, used_when: ['VOICE_PROVIDER', 'gemini'] } : f)),
    })
    await open()
    expect(rowOf('GEMINI_API_KEY')).toHaveTextContent('Not in use now')
    expect(rowOf('OPENAI_API_KEY')).not.toHaveTextContent('Not in use now')
  })

  it('shows the backend error when saving fails', async () => {
    vi.mocked(api.putSettings).mockRejectedValueOnce(new Error('VOICE_PROVIDER must be one of openai, gemini'))
    await open()
    await showTab('Voice coach')
    await pick('VOICE_PROVIDER', 'gemini')
    await userEvent.click(screen.getByRole('button', { name: 'Save' }))
    expect(await screen.findByText(/must be one of/)).toBeInTheDocument()
  })
})

describe('SettingsModal help', () => {
  it('explains a setting in a tooltip tied to its info button', async () => {
    vi.mocked(api.getSettings).mockResolvedValue({
      groups: GROUPS,
      fields: FIELDS.map((f) => (f.key === 'OPENAI_API_KEY' ? { ...f, help: 'Runs the OpenAI voice coaches.' } : f)),
    })
    await open()
    const info = screen.getByRole('button', { name: 'About OPENAI_API_KEY' })
    expect(info).toHaveAccessibleDescription('Runs the OpenAI voice coaches.')
    expect(screen.queryByRole('button', { name: 'About GEMINI_API_KEY' })).not.toBeInTheDocument()
  })
})

describe('SettingsModal models', () => {
  it('lists every model on open even while one is set, and offers the effort levels that model takes', async () => {
    await open()
    await showTab('Claude generation')
    const model = screen.getByRole('combobox', { name: 'CLAUDE_MODEL' })
    await userEvent.click(model)
    expect((await screen.findAllByRole('option')).map((o) => o.textContent)).toEqual([
      'Opus 5.5opusMost capable',
      'Sonnet 5sonnetEfficient',
      'Haiku 4.5haikuFastest',
    ])
    await userEvent.click(screen.getByRole('option', { name: /^Haiku/ }))
    expect(model).toHaveValue('haiku')
    const effort = screen.getByRole('button', { name: /CLAUDE_EFFORT$/ })
    expect(effort).toBeDisabled()
    expect(effort).toHaveTextContent('Haiku 4.5 takes no effort level')
  })

  it('keeps a typed model id nobody lists', async () => {
    await open()
    await showTab('Claude generation')
    const model = screen.getByRole('combobox', { name: 'CLAUDE_MODEL' })
    await userEvent.clear(model)
    await userEvent.type(model, 'claude-next')
    expect(await screen.findByText(/No listed model matches/)).toBeInTheDocument()
    await userEvent.tab()
    expect(model).toHaveValue('claude-next')
    await userEvent.click(screen.getByRole('button', { name: 'Save' }))
    await waitFor(() => expect(api.putSettings).toHaveBeenCalledTimes(1))
    expect(vi.mocked(api.putSettings).mock.calls[0][0]).toEqual({ CLAUDE_MODEL: 'claude-next' })
  })

  it('refreshes the model lists on request', async () => {
    vi.mocked(api.refreshModels).mockResolvedValueOnce({
      groups: GROUPS,
      fields: FIELDS.map((f) => (f.key === 'CLAUDE_MODEL' ? { ...f, options: [opt('claude-fable-5-1', '', 'Fable 5.1')] } : f)),
    })
    await open()
    await showTab('Claude generation')
    await userEvent.click(screen.getByRole('button', { name: 'Refresh model lists' }))
    await userEvent.click(screen.getByRole('combobox', { name: 'CLAUDE_MODEL' }))
    expect((await screen.findAllByRole('option')).map((o) => o.textContent)).toEqual(['Fable 5.1claude-fable-5-1'])
  })
})

describe('SettingsModal skills', () => {
  it('ticks host skills from a filtered list and saves them as a comma list', async () => {
    vi.mocked(api.getSettings).mockResolvedValue({
      groups: GROUPS,
      fields: [
        ...FIELDS,
        field({
          key: 'CLAUDE_SKILLS',
          group: 'claude',
          value: 'stop-slop',
          multi: true,
          options: [opt('humanizer', 'Remove signs of AI writing.'), opt('stop-slop', 'Remove AI writing patterns.'), opt('tdd', 'Test first.')],
        }),
      ],
    })
    await open()
    await showTab('Claude generation')
    expect(screen.getByText('1 ticked')).toBeInTheDocument()
    expect(screen.getByRole('checkbox', { name: /stop-slop/ })).toBeChecked()

    await userEvent.type(screen.getByLabelText('CLAUDE_SKILLS'), 'writing')
    expect(screen.queryByRole('checkbox', { name: /tdd/ })).not.toBeInTheDocument()
    await userEvent.click(screen.getByRole('checkbox', { name: /humanizer/ }))
    expect(screen.getByText('2 ticked')).toBeInTheDocument()

    await userEvent.click(screen.getByRole('button', { name: 'Save' }))
    await waitFor(() => expect(api.putSettings).toHaveBeenCalledTimes(1))
    expect(vi.mocked(api.putSettings).mock.calls[0][0]).toEqual({ CLAUDE_SKILLS: 'humanizer,stop-slop' })
  })
})

describe('SettingsModal closing', () => {
  it('closes at once with nothing edited', async () => {
    const onClose = vi.fn()
    await open(onClose)
    await userEvent.click(screen.getByRole('button', { name: 'Close settings' }))
    expect(onClose).toHaveBeenCalledOnce()
  })

  it('asks before dropping unsaved edits', async () => {
    const onClose = vi.fn()
    await open(onClose)
    await userEvent.type(screen.getByLabelText('OPENAI_API_KEY'), 'sk-new')
    await userEvent.click(screen.getByRole('button', { name: 'Close settings' }))
    expect(onClose).not.toHaveBeenCalled()
    expect(screen.getByRole('alertdialog')).toHaveTextContent('1 unsaved change will be dropped.')

    await userEvent.click(screen.getByRole('button', { name: 'Keep editing' }))
    expect(screen.queryByRole('alertdialog')).not.toBeInTheDocument()
    expect(screen.getByLabelText('OPENAI_API_KEY')).toHaveValue('sk-new')

    await userEvent.click(screen.getByRole('button', { name: 'Close settings' }))
    await userEvent.click(screen.getByRole('button', { name: 'Discard and close' }))
    expect(onClose).toHaveBeenCalledOnce()
  })
})

describe('SettingsModal assessor', () => {
  it('shows the assessor group and a Test button beside the Azure key', async () => {
    vi.mocked(api.testKey).mockResolvedValueOnce({ ok: true, message: 'key works' })
    await open()
    const row = rowOf('AZURE_SPEECH_KEY')
    await userEvent.click(within(row).getByRole('button', { name: 'Test' }))
    expect(api.testKey).toHaveBeenCalledWith('AZURE_SPEECH_KEY', '')
    expect(await within(row).findByRole('status')).toHaveTextContent('✓ key works')
    await showTab('Read aloud assessor')
    expect(screen.getByLabelText('AZURE_SPEECH_REGION')).toHaveValue('koreacentral')
  })
})
