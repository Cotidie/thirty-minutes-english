// What each English sound is, in words a reader can act on: a keyword that
// carries it, and where the mouth goes. Azure names sounds in IPA (en-US set);
// the card looks them up here so "æ" reads as "a as in cat".

export interface SoundGuide {
  /** A common word that carries the sound, the letters for it in caps. */
  like: string
  /** Where the mouth goes. */
  how: string
}

const GUIDE: Record<string, SoundGuide> = {
  // Vowels
  i: { like: 'sEE', how: 'Lips spread, tongue high and front. Hold it long.' },
  ɪ: { like: 'sIt', how: 'Short and relaxed. Tongue a little lower than for "see".' },
  eɪ: { like: 'dAY', how: 'Start at "e", glide up toward "ee".' },
  ɛ: { like: 'bEd', how: 'Mouth half open, tongue mid-front. Short.' },
  æ: { like: 'cAt', how: 'Jaw drops, mouth wide, tongue low and front. Longer than "e".' },
  ɑ: { like: 'fAther', how: 'Jaw fully open, tongue low and back.' },
  ɔ: { like: 'lAW', how: 'Jaw open, lips slightly rounded.' },
  oʊ: { like: 'gO', how: 'Start at "o", round the lips tighter at the end.' },
  ʊ: { like: 'bOOk', how: 'Short, lips loosely rounded.' },
  u: { like: 'fOOd', how: 'Lips tight and round. Hold it long.' },
  ʌ: { like: 'cUp', how: 'Short, mouth half open, tongue relaxed in the middle.' },
  ə: { like: 'About', how: 'Weak and short, mouth barely open. Unstressed.' },
  ɚ: { like: 'lettER', how: 'Weak vowel with the tongue curled back for r.' },
  ɝ: { like: 'bIRd', how: 'Tongue curled back, lips slightly rounded. Hold it.' },
  aɪ: { like: 'mY', how: 'Start open at "ah", glide to "ee".' },
  aʊ: { like: 'nOW', how: 'Start open at "ah", round the lips to "oo".' },
  ɔɪ: { like: 'bOY', how: 'Start at "aw", glide to "ee".' },
  // Consonants
  p: { like: 'Pen', how: 'Lips together, then a puff of air.' },
  b: { like: 'Bat', how: 'Lips together, voice on, no puff.' },
  t: { like: 'Top', how: 'Tongue tip on the ridge behind the top teeth, puff of air.' },
  d: { like: 'Dog', how: 'Same place as t, voice on.' },
  k: { like: 'Cat', how: 'Back of the tongue up, puff of air.' },
  ɡ: { like: 'Go', how: 'Same as k, voice on.' },
  g: { like: 'Go', how: 'Same as k, voice on.' },
  f: { like: 'Fan', how: 'Top teeth on the lower lip, blow. Lips never close.' },
  v: { like: 'Van', how: 'Top teeth on the lower lip, voice on. Lips never close (closed lips make b).' },
  θ: { like: 'THink', how: 'Tongue tip between the teeth, blow. Not s.' },
  ð: { like: 'THis', how: 'Tongue tip between the teeth, voice on. Not d.' },
  s: { like: 'See', how: 'Tongue tip near the ridge, hiss.' },
  z: { like: 'Zoo', how: 'Same as s, voice on. Not j.' },
  ʃ: { like: 'SHe', how: 'Lips pushed forward, tongue further back than for s.' },
  ʒ: { like: 'viSion', how: 'Same as sh, voice on.' },
  h: { like: 'Hat', how: 'Breathe out. No friction in the throat.' },
  tʃ: { like: 'CHair', how: 't then sh, in one burst.' },
  dʒ: { like: 'Jump', how: 'd then zh, in one burst, voice on.' },
  m: { like: 'Man', how: 'Lips closed, hum.' },
  n: { like: 'No', how: 'Tongue tip on the ridge, hum.' },
  ŋ: { like: 'siNG', how: 'Back of the tongue up, hum through the nose. No g after it.' },
  l: { like: 'Light', how: 'Tongue tip touches the ridge; air flows around the sides.' },
  r: { like: 'Red', how: 'Tongue curls back and touches nothing. Lips slightly rounded.' },
  ɹ: { like: 'Red', how: 'Tongue curls back and touches nothing. Lips slightly rounded.' },
  w: { like: 'We', how: 'Lips tight and round, then open.' },
  j: { like: 'Yes', how: 'Tongue high like "ee", then move to the vowel.' },
  ɾ: { like: 'waTer', how: 'Quick tap of the tongue tip. Sounds like a soft d.' },
}

/** The guide for an IPA sound; a sound outside the table gets the symbol only. */
export const soundGuide = (phoneme: string): SoundGuide | null => GUIDE[phoneme] ?? null

/** "æ as in cAt", or just the symbol when unknown. */
export function nameSound(phoneme: string): string {
  const g = soundGuide(phoneme)
  return g ? `${phoneme} as in ${g.like}` : phoneme
}
