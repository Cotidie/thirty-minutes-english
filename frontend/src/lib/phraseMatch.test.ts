import { describe, expect, it } from 'vitest'
import { phrasePattern, strongestMatches } from './phraseMatch'

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

describe('strongestMatches', () => {
  it('picks the line that uses the expression over one that only shares two of its words', () => {
    expect(strongestMatches('Tell me about it', ["I'll think about it tonight.", 'Tell me about it, my boss does the same.'])).toEqual([false, true])
    expect(strongestMatches("I'm not buying it", ["He says he's a doctor now, but I'm not sure.", "Sorry, I'm not buying it."])).toEqual([false, true])
  })

  it('picks the longest part when no line can hold the whole phrase', () => {
    expect(strongestMatches('When it comes to ~,', ['It comes with fries.', 'When it comes to coffee, I am picky.'])).toEqual([false, true])
  })

  it('picks every line that holds the phrase as fully', () => {
    expect(strongestMatches('paid off', ['It paid off.', 'All that work paid off.'])).toEqual([true, true])
  })

  it('picks none when no line holds any part of the phrase', () => {
    expect(strongestMatches('a moving target', ['How are you?', 'Fine, thanks.'])).toEqual([false, false])
  })
})
