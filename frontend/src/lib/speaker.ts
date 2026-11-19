import type { Summary } from '../types'

/** Who said a summary, as the one reading sees it: themselves, someone by name, or someone no longer known. */
export function speakerOf(summary: Summary): string {
  if (summary.mine) return 'You'
  return summary.speaker ?? 'Someone'
}
