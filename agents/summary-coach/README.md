# summary-coach

A paragraph summed up out loud. Gemini's transcription model (`gemini-3.5-transcribe-live`) writes down what
was said, in English or Korean only; it has no prompt and is not given the paragraph, so the transcript holds
only the reader's own words. A text run then judges the summary against the paragraph, rewrites it the way a
skilled speaker would say it, and names what was unskilled in the reader's own wording (`prompts/feedback.md`).
