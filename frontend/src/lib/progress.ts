type Stage = 'starting' | 'skills' | 'searching' | 'writing' | 'finalizing' | 'illustrating'

export interface JobStatus {
  id: string
  topic: string
  status: 'running' | 'done' | 'failed' | 'cancelled'
  stage: Stage
  searches: number
  /** The tool call under way in words, e.g. `Searching "preprints"`; blank outside skills and searching. */
  activity: string
  input_tokens: number
  output_tokens: number
  pictures_done: number
  pictures_total: number
  elapsed_seconds: number
  stage_elapsed_seconds: number
  /** How long this stage took on recent runs (median). */
  stage_expected_seconds: number
  /** Whole run: finished stages as they took, the rest as they usually take. */
  expected_seconds: number
  session_id: number | null
  error: string | null
}

/** Where each stage starts on the bar. */
const FLOORS: Record<Stage, number> = {
  starting: 3,
  skills: 8,
  searching: 15,
  writing: 45,
  finalizing: 80,
  illustrating: 84,
}
const NEXT: Record<Stage, number> = {
  starting: FLOORS.searching,
  skills: FLOORS.searching,
  searching: FLOORS.writing,
  writing: FLOORS.finalizing,
  finalizing: FLOORS.illustrating,
  illustrating: 100,
}
const SEARCH_STEP = 10
const MAX_SEARCHES = 3

function floorOf(job: JobStatus): number {
  if (job.stage === 'searching') return FLOORS.searching + SEARCH_STEP * Math.min(job.searches, MAX_SEARCHES)
  return FLOORS[job.stage]
}

/** Share of the stage done: finished pictures when there are any, else elapsed time against the usual stage time. */
function stageShare(job: JobStatus): number {
  if (job.stage === 'illustrating' && job.pictures_total > 0) return job.pictures_done / job.pictures_total
  return job.stage_elapsed_seconds / Math.max(1, job.stage_expected_seconds)
}

/** Bar percent: the stage sets the floor, the stage share moves toward the next stage, never past it, never backwards. */
export function percentFor(job: JobStatus, previous = 0): number {
  if (job.status === 'done') return 100
  if (job.status !== 'running') return previous
  const floor = floorOf(job)
  const ceiling = NEXT[job.stage]
  const value = Math.round(floor + (ceiling - floor) * Math.min(0.95, stageShare(job)))
  return Math.max(previous, Math.min(ceiling - 1, value))
}

export function labelFor(job: JobStatus): string {
  if (job.status === 'done') return 'Done'
  if (job.status === 'failed') return 'Failed'
  if (job.status === 'cancelled') return 'Cancelled'
  if (job.activity) return job.activity
  switch (job.stage) {
    case 'starting':
      return 'Reading the brief'
    case 'skills':
      return 'Loading writing skills'
    case 'searching':
      return 'Searching the web'
    case 'writing':
      return 'Writing the article, expressions, and words'
    case 'finalizing':
      return 'Checking the structure'
    case 'illustrating':
      return 'Drawing a picture for each word'
  }
}

function tokens(n: number): string {
  return n < 1000 ? String(n) : `${(n / 1000).toFixed(1)}k`
}

/** The counts under the bar: tokens so far, searches, and pictures once drawing starts. */
export function metaFor(job: JobStatus): string {
  const parts = [`${tokens(job.input_tokens)} in`, `${tokens(job.output_tokens)} out`]
  if (job.searches > 0) parts.push(`${job.searches} ${job.searches === 1 ? 'search' : 'searches'}`)
  if (job.pictures_total > 0) parts.push(`${job.pictures_done} / ${job.pictures_total} pictures`)
  return parts.join(' · ')
}
