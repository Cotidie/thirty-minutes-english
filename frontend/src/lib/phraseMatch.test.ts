import { describe, expect, it } from 'vitest'
import { phrasePattern } from './phraseMatch'

const marked = (phrase: string, text: string) => text.match(phrasePattern(phrase, text) ?? /$^/)?.[0] ?? null

describe('phrasePattern', () => {
  it('finds a word in another form', () => {
    expect(marked('retract', 'The magazine retracted the interview.')).toBe('retracted')
    expect(marked('premature', 'That was premature.')).toBe('premature')
  })

  it('finds an expression whose verb changed form, irregular ones too', () => {
    expect(marked('fall through the cracks', 'Your email fell through the cracks.')).toBe('fell through the cracks')
    expect(marked('get around to', 'I never got around to it.')).toBe('got around to')
    expect(marked('push back on', 'My advisor pushed back on the deadline.')).toBe('pushed back on')
    expect(marked('to be fair', 'To be fair, the projector died.')).toBe('To be fair')
    expect(marked("that's a stretch", 'That’s a stretch.')).toBe('That’s a stretch')
  })

  it('lets a stand-in take the words the speaker put there', () => {
    expect(marked('run something by someone', 'Can I run the budget by you?')).toBe('run the budget by')
    expect(marked('bring someone up to speed', 'She brought the new intern up to speed.')).toBe('brought the new intern up to speed')
    expect(marked("can't put my finger on it", "I couldn't put my finger on it.")).toBe("couldn't put my finger on it")
    expect(marked('off the top of my head', 'Off the top of your head, how many?')).toBe('Off the top of your head')
  })

  it('lets a few extra words sit inside the expression', () => {
    expect(marked("that's a stretch", "Honestly, that's a bit of a stretch.")).toBe("that's a bit of a stretch")
  })

  it('falls back to the longest part of the expression that is there', () => {
    expect(marked('where do you draw the line', 'We have to draw the line somewhere.')).toBe('draw the line')
    expect(marked('get around to', 'Nothing here.')).toBeNull()
  })
})
