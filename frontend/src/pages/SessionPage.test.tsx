import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter, Route, Routes, useLocation } from 'react-router-dom'
import { describe, expect, it, vi } from 'vitest'
import { SessionPage } from './SessionPage'

const session = {
  id: 3,
  created_at: '',
  topic: 'X',
  title: 'T',
  content: {
    topic: 'X',
    expressions: [{ phrase: 'a moving target', meaning: 'keeps changing', usage_note: 'n', examples: ['e1', 'e2'] }],
    article: { title: 'Title', body: 'Body.', questions: [], sources: [], translation: [] },
    vocabulary: [{ word: 'mitigate', pos: 'verb', definition: 'make less severe', example: 'We mitigated it.' }],
  },
}

vi.mock('../api', () => ({
  api: {
    getSession: vi.fn(async () => session),
    getStars: vi.fn(async () => ({ expressions: [], words: [] })),
    listExamples: vi.fn(async () => []),
    pictureStyles: vi.fn(async () => ({ current: '', options: [] })),
  },
}))
vi.mock('../lib/liveClient', () => ({ connectExample: vi.fn() }))

function Hash() {
  return <output aria-label="hash">{useLocation().hash}</output>
}

function renderAt(path: string) {
  render(
    <MemoryRouter initialEntries={[path]}>
      <Routes>
        <Route path="/s/:id" element={<><SessionPage /><Hash /></>} />
      </Routes>
    </MemoryRouter>,
  )
}

describe('SessionPage', () => {
  it('opens on the tab named in the address, so a reload stays there', async () => {
    renderAt('/s/3#vocabulary')
    expect(await screen.findByText('mitigate')).toBeInTheDocument()
    expect(screen.queryByText('a moving target')).not.toBeInTheDocument()
  })

  it('names the picked tab in the address, and opens on Expressions without one', async () => {
    renderAt('/s/3')
    expect(await screen.findByText('a moving target')).toBeInTheDocument()
    await userEvent.click(screen.getByRole('button', { name: /Article/ }))
    expect(screen.getByLabelText('hash')).toHaveTextContent('#article')
  })
})
