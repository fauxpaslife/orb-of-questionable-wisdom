// Synthesized locally. No audio files, network calls, or autoplay.
export class OrbSound {
  constructor() { this.enabled = false; this.context = null; }
  setEnabled(enabled) {
    this.enabled = Boolean(enabled);
    if (this.context && !this.enabled) this.context.suspend().catch(() => {});
  }
  unlock() {
    if (!this.enabled) return;
    try {
      if (!this.context) {
        const Audio = window.AudioContext || window.webkitAudioContext;
        if (!Audio) return;
        this.context = new Audio();
        const hum = this.context.createOscillator();
        const gain = this.context.createGain(); gain.gain.value = .012;
        hum.frequency.value = 62; hum.connect(gain).connect(this.context.destination); hum.start();
        const buffer = this.context.createBuffer(1, this.context.sampleRate, this.context.sampleRate);
        const samples = buffer.getChannelData(0);
        for (let i = 0; i < samples.length; i++) samples[i] = (Math.random() * 2 - 1) * .3;
        const noise = this.context.createBufferSource(); noise.buffer = buffer; noise.loop = true;
        const filter = this.context.createBiquadFilter(); filter.type = 'bandpass'; filter.frequency.value = 450;
        this.rattle = this.context.createGain(); this.rattle.gain.value = 0;
        noise.connect(filter).connect(this.rattle).connect(this.context.destination); noise.start();
      }
      this.context.resume().catch(() => {});
    } catch { /* Unsupported audio must never interfere with shaking. */ }
  }
  intensity(value) {
    if (this.enabled && this.context && this.rattle) this.rattle.gain.setTargetAtTime(Math.max(0, Math.min(1, value)) * .15, this.context.currentTime, .06);
  }
  reveal() {
    if (!this.enabled || !this.context || this.context.state !== 'running') return;
    const now = this.context.currentTime;
    const tone = this.context.createOscillator(), gain = this.context.createGain();
    tone.frequency.setValueAtTime(660, now); tone.frequency.exponentialRampToValueAtTime(440, now + .7);
    gain.gain.setValueAtTime(.0001, now); gain.gain.exponentialRampToValueAtTime(.07, now + .02); gain.gain.exponentialRampToValueAtTime(.0001, now + .8);
    tone.connect(gain).connect(this.context.destination); tone.start(); tone.stop(now + .85);
    tone.onended = () => { tone.disconnect(); gain.disconnect(); };
  }
}
