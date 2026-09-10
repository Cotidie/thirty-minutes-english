import { describe, expect, it } from 'vitest'
import { labelFor, percentFor, type JobStatus } from './progress'

function job(over: Partial<JobStatus>): JobStatus {
  return {
    id: 'j',
    topic: 't',
    status: 'running',
    stage: 'starting',
    searches: 0,
    elapsed_seconds: 0,
    stage_elapsed_seconds: 0,
    expected_seconds: 100,
    session_id: null,
    error: null,
    ...over,
  }
}

describe('percentFor', () => {
  it('starts near zero and creeps within the stage without reaching the next stage', () => {
    expect(percentFor(job({}))).toBe(3)
    expect(percentFor(job({ stage_elapsed_seconds: 1000 }))).toBe(14)
  })

  it('raises the floor with each search, capped at three', () => {
    expect(percentFor(job({ stage: 'searching', searches: 1 }))).toBe(25)
    expect(percentFor(job({ stage: 'searching', searches: 3 }))).toBe(44)
    expect(percentFor(job({ stage: 'searching', searches: 7 }))).toBe(44)
  })

  it('never moves backwards even if the stage regresses', () => {
    expect(percentFor(job({ stage: 'starting' }), 60)).toBe(60)
  })

  it('creeps through writing by elapsed time against the expected budget', () => {
    expect(percentFor(job({ stage: 'writing', stage_elapsed_seconds: 30 }))).toBe(71)
    expect(percentFor(job({ stage: 'writing', stage_elapsed_seconds: 600 }))).toBe(93)
  })

  it('is 100 when done and frozen when failed', () => {
    expect(percentFor(job({ status: 'done' }))).toBe(100)
    expect(percentFor(job({ status: 'failed' }), 42)).toBe(42)
  })
})

describe('labelFor', () => {
  it('names the stage in plain words', () => {
    expect(labelFor(job({ stage: 'searching', searches: 2 }))).toBe('Searching the web (2)')
    expect(labelFor(job({ status: 'done' }))).toBe('Done')
  })
})
