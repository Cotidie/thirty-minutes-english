import { render, screen } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { expect, it } from 'vitest'
import { CornerTools } from './CornerTools'

it('puts the corpus beside the settings in the corner', () => {
  render(
    <MemoryRouter>
      <CornerTools />
    </MemoryRouter>,
  )
  expect(screen.getByRole('link', { name: 'Expression corpus' })).toHaveAttribute('href', '/corpus')
  expect(screen.getByRole('button', { name: 'Settings' })).toBeInTheDocument()
})
