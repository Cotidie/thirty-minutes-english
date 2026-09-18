// Turns the microphone into 100 ms chunks of 16-bit PCM at the context's
// sample rate (the transport opens the context at 16 kHz).

class PcmCapture extends AudioWorkletProcessor {
  constructor() {
    super()
    this.chunk = new Int16Array(Math.round(sampleRate / 10))
    this.filled = 0
  }

  process(inputs) {
    const samples = inputs[0]?.[0]
    if (!samples) return true
    for (const s of samples) {
      const clamped = Math.max(-1, Math.min(1, s))
      this.chunk[this.filled++] = clamped < 0 ? clamped * 0x8000 : clamped * 0x7fff
      if (this.filled === this.chunk.length) {
        this.port.postMessage(this.chunk.buffer.slice(0))
        this.filled = 0
      }
    }
    return true
  }
}

registerProcessor('pcm-capture', PcmCapture)
