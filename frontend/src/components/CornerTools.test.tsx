import { render, screen } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { expect, it } from 'vitest'
import { CornerTools } from './CornerTools'

it('puts the database beside the settings in the corner', () => {
  render(
    <MemoryRouter>
      <CornerTools />
    </MemoryRouter>,
  )
  expect(screen.getByRole('link', { name: 'Database' })).toHaveAttribute('href', '/database')
  expect(screen.getByRole('button', { name: 'Settings' })).toBeInTheDocument()
})
