# summary-coach

A paragraph summed up out loud, with the paragraph in view. Two parts, and both work from the paragraph:

- **Ears:** Gemini's transcription model (`gemini-3.5-transcribe-live`) writes down what was said, in English or
  Korean only. It takes no prompt, so the paragraph reaches it as custom vocabulary: its words, so names and terms
  come back spelled as the paragraph spells them.
- **Judge:** a text run (`prompts/feedback.md`) reads the full paragraph and the transcript. It returns the key
  points missed, the weak spots in the reader's wording with a better version of each, and a model answer: what
  the reader said, cut to one or two short sentences.
