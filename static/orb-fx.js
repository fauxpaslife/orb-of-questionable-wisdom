// Animation only. Receives state from UI; never reads questions or calls an API.
export class OrbFX {
  constructor(room, motion) {
    this.room = room;
    this.motion = motion;
    this.fogs = [...room.querySelectorAll('.fog')];
    this.reduced = matchMedia('(prefers-reduced-motion: reduce)');
    this.energy = 0;
    this.target = 0;
    this.state = 'idle';
    this.conflicted = false;
    this.candles = [];
    this.flicker = 0;
    this.start = performance.now();
    this.frame = requestAnimationFrame(t => this.animate(t));
  }
  intensity(value) { this.target = Math.max(0, Math.min(1, value)); }
  setCandles(candles) { this.candles = candles; }
  setState(state) {
    this.state = state;
    this.room.classList.toggle('busy', ['stirring', 'listening', 'murmuring'].includes(state));
    this.room.classList.toggle('revealed', state === 'revealed');
    if (state !== 'revealed') this.room.classList.remove('conflicted');
    if (state !== 'revealed') this.candles.forEach(candle => candle.classList.remove('lit'));
  }
  reveal(result) {
    this.conflicted = result.conflicted;
    this.room.classList.toggle('conflicted', this.conflicted);
    this.setState('revealed');
    this.flicker = result.flicker;
    this.revealStarted = performance.now();
    this.candles.forEach((candle, i) => candle.classList.toggle('lit', i < result.candleCount));
    // Fixed palette chosen once; all per-frame work is transform + opacity.
    this.fogs[0].style.background = result.vibe < .7
      ? 'radial-gradient(ellipse at 35% 45%,#8863adb0,transparent 58%)'
      : result.vibe > 1.3
        ? 'radial-gradient(ellipse at 35% 45%,#3cbaacb0,transparent 58%)'
        : '';
  }
  animate(now) {
    const t = (now - this.start) / 1000;
    this.energy += (this.target - this.energy) * .12;
    const busy = ['stirring', 'listening', 'murmuring'].includes(this.state);
    if (this.reduced.matches) {
      this.motion.style.transform = 'none';
      this.fogs.forEach(f => { f.style.transform = 'none'; f.style.opacity = busy ? '.75' : '.5'; });
    } else {
      const amplitude = this.energy * 15;
      this.motion.style.transform = `translate(${Math.sin(t * 29) * amplitude}px,${Math.sin(t * .85) * 4 + Math.cos(t * 23) * amplitude * .3}px) rotate(${Math.sin(t * 24) * this.energy * 5}deg)`;
      this.fogs.forEach((fog, i) => {
        const phase = t * (busy ? .7 : .18) * (1 + this.energy * 3) + i * 2.1;
        fog.style.transform = `translate(${Math.sin(phase) * (10 + this.energy * 22)}px,${Math.cos(phase * .7) * 15}px) rotate(${Math.sin(phase * .3) * 35}deg) scale(${1 + this.energy * .15})`;
        fog.style.opacity = String(this.conflicted && this.state === 'revealed' ? .5 + Math.sin(t * (9 + i)) * .25 : .65 + Math.sin(phase) * .15);
      });
    }
    this.candles.forEach((candle, i) => {
      const flame = candle.firstElementChild;
      const lit = candle.classList.contains('lit');
      const wave = this.reduced.matches ? 0 : Math.sin(t * (7 + i * .37) + i * 2) * (.06 + this.flicker * .22);
      const rise = this.reduced.matches ? 1 : Math.min(1, Math.max(0, (now - this.revealStarted) / 1000));
      flame.style.opacity = lit ? String((.8 + wave) * rise) : '0';
      flame.style.transform = this.reduced.matches ? 'none' : `scale(${1 + wave * .4},${1 + wave * .65}) rotate(${wave * 12}deg)`;
    });
    this.frame = requestAnimationFrame(tick => this.animate(tick));
  }
  destroy() { cancelAnimationFrame(this.frame); }
}
