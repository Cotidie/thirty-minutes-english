import { act, renderHook } from '@testing-library/react'
import { beforeEach, expect, test, vi } from 'vitest'
import { api } from '../api'
import type { JobStatus } from './progress'
import { useGenerationJob } from './useGenerationJob'

vi.mock('../api', () => ({ api: { listJobs: vi.fn(), startGeneration: vi.fn(), getJob: vi.fn(), cancelJob: vi.fn() } }))

const started: JobStatus = {
  id: 'j',
  topic: 'Trams',
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
  stage_expected_seconds: 10,
  expected_seconds: 150,
  session_id: null,
  error: null,
  spent: false,
}

beforeEach(() => {
  vi.mocked(api.listJobs).mockReset().mockResolvedValue([])
  vi.mocked(api.startGeneration).mockReset().mockResolvedValue(started)
  vi.mocked(api.getJob).mockReset().mockResolvedValue({ ...started, spent: true })
})

test('a new job is read again at once, so Cancel does not wait a poll to say what it costs', async () => {
  const { result } = renderHook(() => useGenerationJob(() => undefined))
  await act(() => result.current.start('Trams'))
  expect(api.getJob).toHaveBeenCalledExactlyOnceWith('j')
  expect(result.current.job?.spent).toBe(true)
})

test('a start the server refused reads nothing back', async () => {
  vi.mocked(api.startGeneration).mockRejectedValue(new Error('Not enough credits: this needs 200 and you have 100.'))
  const { result } = renderHook(() => useGenerationJob(() => undefined))
  await act(() => result.current.start('Trams'))
  expect(api.getJob).not.toHaveBeenCalled()
  expect(result.current.error).toBe('Not enough credits: this needs 200 and you have 100.')
  expect(result.current.job).toBeNull()
})
