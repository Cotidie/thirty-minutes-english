export interface Phase {
  key: 'expressions' | 'article' | 'vocabulary'
  label: string
  minutes: number
}

export const PHASES: Phase[] = [
  { key: 'expressions', label: 'Expressions', minutes: 10 },
  { key: 'article', label: 'Article', minutes: 10 },
  { key: 'vocabulary', label: 'Vocabulary', minutes: 10 },
]

export const SESSION_SECONDS = PHASES.reduce((sum, p) => sum + p.minutes * 60, 0)

export function phaseIndexAt(elapsedSeconds: number): number {
  let boundary = 0
  for (let i = 0; i < PHASES.length; i++) {
    boundary += PHASES[i].minutes * 60
    if (elapsedSeconds < boundary) return i
  }
  return PHASES.length - 1
}

export function formatClock(seconds: number): string {
  const s = Math.max(0, Math.floor(seconds))
  const mm = String(Math.floor(s / 60)).padStart(2, '0')
  const ss = String(s % 60).padStart(2, '0')
  return `${mm}:${ss}`
}
