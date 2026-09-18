// Plays 16-bit PCM chunks in order at the context's sample rate (the
// transport opens the context at 24 kHz). Messages in:
//   ArrayBuffer            a chunk to queue
//   { type: 'flush' }      drop the queue (the user interrupted the coach)
//   { type: 'drain' }      answer { type: 'drained' } once the queue runs dry
// Silence plays when the queue is empty.

class PcmPlayer extends AudioWorkletProcessor {
  constructor() {
    super()
    this.queue = []
    this.offset = 0
    this.drainRequested = false
    this.port.onmessage = ({ data }) => {
      if (data instanceof ArrayBuffer) {
        this.queue.push(new Int16Array(data))
      } else if (data?.type === 'flush') {
        this.queue = []
        this.offset = 0
      } else if (data?.type === 'drain') {
        this.drainRequested = true
        this.reportIfDrained()
      }
    }
  }

  reportIfDrained() {
    if (!this.drainRequested || this.queue.length > 0) return
    this.drainRequested = false
    this.port.postMessage({ type: 'drained' })
  }

  process(_inputs, outputs) {
    const out = outputs[0]?.[0]
    if (!out) return true
    let written = 0
    while (written < out.length && this.queue.length > 0) {
      const head = this.queue[0]
      const take = Math.min(out.length - written, head.length - this.offset)
      for (let i = 0; i < take; i++) out[written + i] = head[this.offset + i] / 0x8000
      written += take
      this.offset += take
      if (this.offset >= head.length) {
        this.queue.shift()
        this.offset = 0
      }
    }
    for (let i = written; i < out.length; i++) out[i] = 0
    this.reportIfDrained()
    return true
  }
}

registerProcessor('pcm-player', PcmPlayer)
