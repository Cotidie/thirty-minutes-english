/**
 * Where a word or an expression is used in a sentence, in whatever form it takes there:
 * "fall through the cracks" finds "fell through the cracks", "run something by someone"
 * finds "ran the budget by Mina". Falls back to the longest part of the phrase that is there.
 */

/** Irregular forms; any form listed finds the others. */
const FORMS = [
  'be is am are was were been being',
  'fall falls fell fallen falling',
  'get gets got gotten getting',
  'give gives gave given giving',
  'bring brings brought bringing',
  'come comes came coming',
  'keep keeps kept keeping',
  'make makes made making',
  'draw draws drew drawn drawing',
  'run runs ran running',
  'go goes went gone going',
  'take takes took taken taking',
  'do does did done doing',
  'hold holds held holding',
  'put puts putting',
  'cut cuts cutting',
  'let lets letting',
  "can't cannot couldn't can",
].map((line) => line.split(' '))

/** Stand-ins for whatever the speaker puts there: a few words, or none. */
const SLOTS = new Set(['someone', 'something', 'somebody', 'sb', 'sth', 'or', 'doing'])
/** Possessives that change with the speaker ("put my finger on it", "off the top of your head"). */
const POSSESSIVES = new Set(['my', 'your', "one's", 'his', 'her', 'their', 'our'])

const GAP = null
type Token = string | typeof GAP

const escape = (s: string) => s.replace(/[.*+?^${}()|[\]\\]/g, '\\$&').replace(/'/g, "['’]")

function tokenPattern(word: string): Token {
  const w = word.toLowerCase().replace(/’/g, "'")
  if (SLOTS.has(w)) return GAP
  if (POSSESSIVES.has(w)) return "(?:my|your|one['’]s|his|her|their|our|its)"
  const forms = FORMS.find((group) => group.includes(w))
  if (forms) return `(?:${forms.map(escape).join('|')})`
  if (w.length <= 3) return escape(w)
  return `${escape(w.replace(/e$/, ''))}\\w*`
}

/** `loose`: a few words may sit between any two ("that's a bit of a stretch"). */
function join(tokens: Token[], loose = false): string {
  let pattern = ''
  let gap = false
  for (const t of tokens) {
    if (t === GAP) {
      gap = pattern !== ''
      continue
    }
    pattern += pattern === '' ? t : gap ? `(?:\\s+\\S+){0,4}?\\s+${t}` : loose ? `(?:\\s+\\S+){0,3}?\\s+${t}` : `\\s+${t}`
    gap = false
  }
  return pattern
}

function search(pattern: string, text: string): RegExp | null {
  const found = new RegExp(`\\b(${pattern})(?![\\w'’])`, 'gi')
  return found.test(text) ? new RegExp(found.source, 'gi') : null
}

/** The pattern that finds `phrase` in `text`, or null when no part of it is there. */
export function phrasePattern(phrase: string, text: string): RegExp | null {
  const tokens = phrase
    .replace(/\([^)]*\)/g, ' ')
    .split(/\s+/)
    .filter(Boolean)
    .map(tokenPattern)
  const words = tokens.filter((t) => t !== GAP).length
  const least = Math.min(2, words)
  // The whole phrase, then with a few extra words inside it, then its longest run that is there;
  // a run must hold at least two real words (one for a single word).
  const whole = search(join(tokens), text) ?? (words > 1 ? search(join(tokens, true), text) : null)
  if (whole) return whole
  for (let size = tokens.length - 1; size > 0; size--) {
    for (let start = 0; start + size <= tokens.length; start++) {
      const run = tokens.slice(start, start + size)
      if (run[0] === GAP || run[run.length - 1] === GAP || run.filter((t) => t !== GAP).length < least) continue
      const found = search(join(run), text)
      if (found) return found
    }
  }
  return null
}
