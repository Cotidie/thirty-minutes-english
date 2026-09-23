type Stage = 'starting' | 'skills' | 'searching' | 'writing' | 'finalizing' | 'illustrating'

export interface JobStatus {
  id: string
  topic: string
  status: 'running' | 'done' | 'failed'
  stage: Stage
  searches: number
  elapsed_seconds: number
  stage_elapsed_seconds: number
  expected_seconds: number
  session_id: number | null
  error: string | null
}

/** Where each stage starts on the bar, and how much of the expected time it usually takes. */
const STAGES: Record<Stage, { floor: number; share: number }> = {
  starting: { floor: 3, share: 0.1 },
  skills: { floor: 8, share: 0.05 },
  searching: { floor: 15, share: 0.1 },
  writing: { floor: 45, share: 0.5 },
  finalizing: { floor: 80, share: 0.05 },
  illustrating: { floor: 84, share: 0.3 },
}
const SEARCH_STEP = 10
const MAX_SEARCHES = 3

function floorOf(job: JobStatus): number {
  if (job.stage === 'searching') return STAGES.searching.floor + SEARCH_STEP * Math.min(job.searches, MAX_SEARCHES)
  return STAGES[job.stage].floor
}

function ceilingOf(job: JobStatus): number {
  switch (job.stage) {
    case 'starting':
    case 'skills':
      return STAGES.searching.floor
    case 'searching':
      return STAGES.writing.floor
    case 'writing':
      return STAGES.finalizing.floor
    case 'finalizing':
      return STAGES.illustrating.floor
    case 'illustrating':
      return 100
  }
}

/** Bar percent: the stage sets the floor, elapsed time creeps toward the next stage, never past it, never backwards. */
export function percentFor(job: JobStatus, previous = 0): number {
  if (job.status === 'done') return 100
  if (job.status === 'failed') return previous
  const floor = floorOf(job)
  const ceiling = ceilingOf(job)
  const budget = Math.max(1, job.expected_seconds * STAGES[job.stage].share)
  const creep = Math.min(0.95, job.stage_elapsed_seconds / budget)
  const value = Math.round(floor + (ceiling - floor) * creep)
  return Math.max(previous, Math.min(ceiling - 1, value))
}

export function labelFor(job: JobStatus): string {
  if (job.status === 'done') return 'Done'
  if (job.status === 'failed') return 'Failed'
  switch (job.stage) {
    case 'starting':
      return 'Reading the brief'
    case 'skills':
      return 'Loading writing skills'
    case 'searching':
      return `Searching the web (${job.searches})`
    case 'writing':
      return 'Writing the article, expressions, and words'
    case 'finalizing':
      return 'Checking the structure'
    case 'illustrating':
      return 'Drawing a picture for each word'
  }
}
