import { describe, expect, it } from 'vitest'
import { labelFor, metaFor, percentFor, type JobStatus } from './progress'

function job(over: Partial<JobStatus>): JobStatus {
  return {
    id: 'j',
    topic: 't',
    status: 'running',
    stage: 'starting',
    searches: 0,
    activity: '',
    input_tokens: 0,
    output_tokens: 0,
    pictures_done: 0,
    pictures_total: 0,
    elapsed_seconds: 0,
    stage_elapsed_seconds: 0,
    stage_expected_seconds: 20,
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

  it('creeps through writing against the usual time of that stage', () => {
    expect(percentFor(job({ stage: 'writing', stage_elapsed_seconds: 10, stage_expected_seconds: 20 }))).toBe(63)
    expect(percentFor(job({ stage: 'writing', stage_elapsed_seconds: 600, stage_expected_seconds: 20 }))).toBe(78)
  })

  it('moves through the pictures by how many are drawn', () => {
    expect(percentFor(job({ stage: 'illustrating', pictures_done: 4, pictures_total: 8 }))).toBe(92)
    expect(percentFor(job({ stage: 'illustrating', pictures_done: 8, pictures_total: 8 }))).toBe(99)
  })

  it('is 100 when done and frozen when failed or cancelled', () => {
    expect(percentFor(job({ status: 'done' }))).toBe(100)
    expect(percentFor(job({ status: 'failed' }), 42)).toBe(42)
    expect(percentFor(job({ status: 'cancelled' }), 42)).toBe(42)
  })
})

describe('labelFor', () => {
  it('shows what the model is doing, else the stage in plain words', () => {
    expect(labelFor(job({ stage: 'searching', activity: 'Searching "preprints"' }))).toBe('Searching "preprints"')
    expect(labelFor(job({ stage: 'searching' }))).toBe('Searching the web')
    expect(labelFor(job({ status: 'done' }))).toBe('Done')
  })
})

describe('metaFor', () => {
  it('shows tokens, then searches and pictures once there are any', () => {
    expect(metaFor(job({ input_tokens: 950, output_tokens: 12 }))).toBe('950 in · 12 out')
    expect(metaFor(job({ input_tokens: 48210, output_tokens: 3100, searches: 1, pictures_done: 3, pictures_total: 8 }))).toBe(
      '48.2k in · 3.1k out · 1 search · 3 / 8 pictures',
    )
  })
})
