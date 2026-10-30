import { useCallback } from 'react'
import { useNavigate } from 'react-router-dom'
import { useGenerationJob } from '../lib/useGenerationJob'
import { useTopics } from '../lib/useTopics'
import { GenerationProgress } from './GenerationProgress'
import { TopicPicker } from './TopicPicker'

/** Today's topics and the session being written, for an account allowed to create one. */
export function SessionCreator() {
  const navigate = useNavigate()
  const { topics, labels: topicLabels, pending, error: topicError, refresh } = useTopics()
  const open = useCallback((sessionId: number) => navigate(`/s/${sessionId}`), [navigate])
  const { job, running: busy, error, start: generate, close } = useGenerationJob(open)

  return (
    <>
      <TopicPicker
        suggestions={topics}
        labels={topicLabels}
        pending={pending}
        error={topicError}
        busy={busy}
        onGenerate={generate}
        onRefresh={refresh}
      />
      {job && <GenerationProgress job={job} onClose={close} onOpen={open} />}
      {error && <p className="error">Could not create the session: {error}</p>}
    </>
  )
}
