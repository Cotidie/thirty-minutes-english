import { describe, expect, it } from 'vitest'
import { pairSentences } from './sentences'

describe('pairSentences', () => {
  it('cuts each paragraph into its paired sentences with the spacing kept as plain runs', () => {
    const paragraphs = ['Ambition is cheap. Upkeep pays.', 'A twin delivers.']
    const pairs = [
      { en: 'Ambition is cheap.', ko: '야심은 싸다.' },
      { en: 'Upkeep pays.', ko: '유지가 돈이 된다.' },
      { en: 'A twin delivers.', ko: '트윈은 값을 한다.' },
    ]
    expect(pairSentences(paragraphs, pairs)).toEqual([
      [
        { text: 'Ambition is cheap.', start: 0, ko: '야심은 싸다.' },
        { text: ' ', start: 18, ko: null },
        { text: 'Upkeep pays.', start: 19, ko: '유지가 돈이 된다.' },
      ],
      [{ text: 'A twin delivers.', start: 0, ko: '트윈은 값을 한다.' }],
    ])
  })

  it('leaves a sentence with no pair, or a pair not in the text, as plain English', () => {
    const paragraphs = ['One. Two. Three.']
    const pairs = [
      { en: 'One.', ko: '하나.' },
      { en: 'Missing.', ko: '없음.' },
    ]
    expect(pairSentences(paragraphs, pairs)).toEqual([
      [
        { text: 'One.', start: 0, ko: '하나.' },
        { text: ' Two. Three.', start: 4, ko: null },
      ],
    ])
  })

  it('takes pairs in order, so a repeated short sentence lands on its own occurrence', () => {
    const paragraphs = ['Not yet. It works. Not yet.']
    const pairs = [
      { en: 'Not yet.', ko: '아직이다.' },
      { en: 'It works.', ko: '된다.' },
      { en: 'Not yet.', ko: '아직은 아니다.' },
    ]
    const [pieces] = pairSentences(paragraphs, pairs)
    expect(pieces.filter((p) => p.ko).map((p) => [p.start, p.ko])).toEqual([
      [0, '아직이다.'],
      [9, '된다.'],
      [19, '아직은 아니다.'],
    ])
  })

  it('renders an untranslated article as one plain run per paragraph', () => {
    expect(pairSentences(['A.', 'B.'], [])).toEqual([[{ text: 'A.', start: 0, ko: null }], [{ text: 'B.', start: 0, ko: null }]])
  })
})
