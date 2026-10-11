import { fireEvent, render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi } from 'vitest'
import type { SessionNote } from '../lib/useNote'
import { NoteBox } from './NoteBox'

function note(text: string): SessionNote {
  return { text, status: 'saved', edit: vi.fn(), flush: vi.fn() }
}

describe('NoteBox', () => {
  it('stays shut until the button or n opens it, and Esc closes it', async () => {
    render(<NoteBox note={note('')} />)
    expect(screen.queryByRole('textbox')).not.toBeInTheDocument()

    await userEvent.click(screen.getByRole('button', { name: 'Open notes' }))
    expect(screen.getByRole('textbox', { name: 'Notes' })).toHaveFocus()

    fireEvent.keyDown(window, { key: 'Escape' })
    expect(screen.queryByRole('textbox')).not.toBeInTheDocument()

    fireEvent.keyDown(window, { key: 'n' })
    expect(screen.getByRole('textbox', { name: 'Notes' })).toBeInTheDocument()
  })

  it('opens a written note on a fresh line with the caret at the end', async () => {
    const written = note('hedge 발음')
    const { rerender } = render(<NoteBox note={written} />)
    await userEvent.click(screen.getByRole('button', { name: 'Open notes' }))
    expect(written.edit).toHaveBeenCalledWith('hedge 발음\n')

    rerender(<NoteBox note={{ ...written, text: 'hedge 발음\n' }} />)
    const box = screen.getByRole<HTMLTextAreaElement>('textbox', { name: 'Notes' })
    expect(box.selectionStart).toBe(box.value.length)
  })

  it('drops the fresh line again when the panel closes with nothing typed on it', async () => {
    const opened = note('hedge 발음\n')
    render(<NoteBox note={opened} />)
    fireEvent.keyDown(window, { key: 'n' })
    fireEvent.keyDown(window, { key: 'n' })
    expect(opened.edit).toHaveBeenLastCalledWith('hedge 발음')
  })

  it('leaves n alone while typing in the note', async () => {
    const blank = note('')
    render(<NoteBox note={blank} />)
    fireEvent.keyDown(window, { key: 'n' })
    fireEvent.keyDown(screen.getByRole('textbox', { name: 'Notes' }), { key: 'n' })
    expect(screen.getByRole('textbox', { name: 'Notes' })).toBeInTheDocument()
  })
})
