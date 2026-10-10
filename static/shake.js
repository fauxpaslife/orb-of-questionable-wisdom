// Input energy is used only to trigger a shake. It is never sent to the oracle.
export class ShakeInput {
  constructor(orb, callbacks) {
    this.orb = orb;
    this.callbacks = callbacks;
    this.enabled = true;
    this.energy = 0;
    this.velocity = 0;
    this.pointer = null;
    this.calm = null;
    this.visualTimer = null;
    orb.addEventListener('pointerdown', event => this.down(event));
    orb.addEventListener('pointermove', event => this.move(event));
    orb.addEventListener('pointerup', event => this.up(event));
    orb.addEventListener('pointercancel', event => this.up(event));
    orb.addEventListener('lostpointercapture', event => this.up(event));
    document.addEventListener('keydown', event => {
      if (event.code !== 'Space' || event.repeat || !this.enabled || document.querySelector('dialog[open]')) return;
      if (['INPUT', 'TEXTAREA', 'SELECT', 'BUTTON'].includes(event.target.tagName) || event.target.isContentEditable) return;
      event.preventDefault();
      this.polite();
    });
  }
  setEnabled(enabled) {
    this.enabled = enabled;
    this.orb.setAttribute('aria-disabled', String(!enabled));
    if (!enabled) {
      clearTimeout(this.calm);
      clearTimeout(this.visualTimer);
      this.energy = 0;
      this.pointer = null;
      this.orb.classList.remove('dragging');
      this.callbacks.intensity(0);
    }
  }
  down(event) {
    if (!this.enabled || event.button !== 0) return;
    this.pointer = {id: event.pointerId, x: event.clientX, y: event.clientY, time: performance.now()};
    this.orb.setPointerCapture(event.pointerId);
    this.orb.classList.add('dragging');
    this.orb.focus({preventScroll: true});
    this.energy = 0;
    this.velocity = 0;
    clearTimeout(this.calm);
  }
  move(event) {
    if (!this.enabled || !this.pointer || this.pointer.id !== event.pointerId) return;
    const now = performance.now();
    const dt = Math.max(.008, Math.min(.08, (now - this.pointer.time) / 1000));
    const speed = Math.hypot(event.clientX - this.pointer.x, event.clientY - this.pointer.y) / dt;
    this.velocity = this.velocity * .55 + Math.min(1, speed / 900) * .45;
    this.pointer = {id: event.pointerId, x: event.clientX, y: event.clientY, time: now};
    this.feed(this.velocity, dt);
  }
  feed(intensity, dt) {
    if (!this.enabled) return;
    this.energy += intensity * dt;
    this.callbacks.intensity(intensity);
    clearTimeout(this.visualTimer);
    this.visualTimer = setTimeout(() => this.callbacks.intensity(0), 130);
    if (intensity > .12) this.settle();
  }
  settle() {
    clearTimeout(this.calm);
    this.calm = setTimeout(() => {
      if (!this.enabled) return;
      const enough = this.energy >= .28;
      this.energy = 0;
      this.callbacks.intensity(0);
      this.callbacks[enough ? 'trigger' : 'weak']();
    }, 400);
  }
  up(event) {
    if (!this.pointer || this.pointer.id !== event.pointerId) return;
    this.pointer = null;
    this.orb.classList.remove('dragging');
    if (this.orb.hasPointerCapture(event.pointerId)) this.orb.releasePointerCapture(event.pointerId);
    this.settle();
  }
  polite() {
    this.energy = .3;
    this.callbacks.intensity(.55);
    clearTimeout(this.visualTimer);
    this.visualTimer = setTimeout(() => this.callbacks.intensity(0), 250);
    this.settle();
  }
  async enableMotion() {
    if (!window.isSecureContext) throw new Error('Phone shake needs HTTPS or localhost; LAN HTTP cannot access sensors.');
    if (typeof DeviceMotionEvent === 'undefined') throw new Error('This browser has no motion sensor access.');
    if (typeof DeviceMotionEvent.requestPermission === 'function') {
      if (await DeviceMotionEvent.requestPermission() !== 'granted') throw new Error('Motion permission was not granted.');
    }
    if (this.motionEnabled) return;
    this.motionEnabled = true;
    let previous = null;
    let last = performance.now();
    window.addEventListener('devicemotion', event => {
      const acceleration = event.accelerationIncludingGravity;
      if (!acceleration || acceleration.x == null) return;
      const now = performance.now();
      const vector = [acceleration.x, acceleration.y, acceleration.z];
      if (previous && this.enabled && !document.querySelector('dialog[open]')) {
        const intensity = Math.min(1, Math.hypot(...vector.map((value, i) => value - previous[i])) / 18);
        if (intensity > .12) this.feed(intensity, Math.min(.1, (now - last) / 1000));
      }
      previous = vector;
      last = now;
    });
  }
}
