import { expect, test } from 'vitest'
import { safeNext } from './safeNext'

test.each(['//evil.example', 'https://evil.example', '/\\evil.example', '/\t/evil.example', 'evil', '', null, '//%5B', '/login', '/login?next=/x', '/signup#top'])(
  'next %j goes home',
  (raw) => {
    expect(safeNext(raw)).toBe('/')
  },
)

test('a path on this site is kept', () => {
  expect(safeNext('/s/26?x=1#article')).toBe('/s/26?x=1#article')
})
