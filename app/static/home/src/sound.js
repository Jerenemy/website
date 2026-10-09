// The scene's sound. Off until the visitor turns it on (a page never speaks first) with the speaker
// in the corner; the choice is kept for their next visit. Everything is synthesized with Web Audio:
// nothing to fetch, nothing to allowlist.
//
// Soft music and rumbling. The light is the music: a quiet drone that opens up while it moves, one
// note of a pentatonic scale for each work it settles on, a run of notes as its swell passes each
// block round the loop, a falling pair as it goes in at the door. The stone is a low rumble while it
// rolls or its steps rise and fall, and a soft, low thud where it locks or lands. Every note goes
// through one echo, so nothing is dry and nothing is sharp.
//
// Cheap by construction: the continuous voices are one noise source and two oscillators, and the
// frame's figures reach them only when they change (and at most SOUND.updateHz times a second);
// the one-shots are an oscillator or two each, gone when they decay. The context asks for a
// playback-sized buffer: none of this needs low latency.
//
// Browsers start a context suspended until a gesture, so the context is made on the visitor's
// first click or key with sound on (the toggle itself is one), suspended while the page is
// hidden, and the master is always faded, never cut.
import { SOUND } from './config.js';

const KEY = 'tribar:sound';
const clamp01 = (x) => Math.min(1, Math.max(0, x));
const GESTURES = ['pointerdown', 'keydown', 'touchend'];
// D dorian pentatonic over the drone's D: no leading tone, nothing that resolves, so any order works.
const SCALE = [293.66, 329.63, 392.0, 440.0, 523.25, 587.33, 659.26, 783.99];

/** @param button the toggle (aria-pressed), or null: the sound then stays off */
export function createSound(button) {
  let on = false;
  try { on = !!button && localStorage.getItem(KEY) === 'on'; } catch { /* storage may be off */ }
  let ctx = null, master = null, wet = null, noise = null, v = null, sleepTimer = 0;
  let sentAt = -1, lastBlock = -1;
  const sent = new Map();   // param -> the value last sent to it

  // ---- building blocks -------------------------------------------------------------------
  const gainNode = (value = 0) => { const g = ctx.createGain(); g.gain.value = value; return g; };
  function filter(type, frequency, Q = 0.7) {
    const f = ctx.createBiquadFilter();
    f.type = type; f.frequency.value = frequency; f.Q.value = Q;
    return f;
  }
  /** A stereo position in front of `dest` (dest itself where there is none to be had, or no need). */
  function panner(dest, pan = 0) {
    if (!pan || !ctx.createStereoPanner) return dest;
    const p = ctx.createStereoPanner(); p.pan.value = pan; p.connect(dest);
    return p;
  }
  const chain = (...nodes) => { for (let i = 1; i < nodes.length; i++) nodes[i - 1].connect(nodes[i]); return nodes[nodes.length - 1]; };
  function oscillator(type, frequency) { const o = ctx.createOscillator(); o.type = type; o.frequency.value = frequency; o.start(); return o; }
  /** Send a figure to a param only when it has moved by more than `eps` since it was last sent. */
  function send(param, value, eps, tc = SOUND.follow) {
    const was = sent.get(param);
    if (was !== undefined && Math.abs(was - value) <= eps) return;
    sent.set(param, value);
    param.setTargetAtTime(value, ctx.currentTime, tc);
  }

  // One-shots: an oscillator from `at`, gliding f0 -> f1, into an envelope (attack, exponential decay).
  function envelope(dest, at, peak, attack, decay) {
    const g = gainNode(0); g.connect(dest);
    g.gain.setValueAtTime(0, at);
    g.gain.linearRampToValueAtTime(peak, at + attack);
    g.gain.setTargetAtTime(0, at + attack, decay);
    return g;
  }
  const tail = (attack, decay) => attack + decay * 6;
  function tone(f0, f1, glide, at, len, type = 'sine') {
    const o = ctx.createOscillator(); o.type = type;
    o.frequency.setValueAtTime(f0, at);
    if (f1 !== f0) o.frequency.exponentialRampToValueAtTime(f1, at + glide);
    o.start(at); o.stop(at + len);
    return o;
  }
  /** A soft note: a sine and a quieter octave over it, a slow attack, into the echo too. */
  function note(f, peak, at = ctx.currentTime, pan = 0, decay = SOUND.noteDecay) {
    const out = panner(master, pan), attack = SOUND.noteAttack, len = tail(attack, decay);
    const g = envelope(out, at, peak, attack, decay);
    g.connect(wet);
    tone(f, f, 0, at, len).connect(g);
    chain(tone(f * 2, f * 2, 0, at, len), gainNode(0.18), g);
  }
  /** A low, soft thud: a sine falling in pitch, its attack rounded off. */
  function thump(peak, at, decay, f0 = 70, f1 = 38) {
    chain(tone(f0, f1, decay * 1.5, at, tail(0.012, decay)), envelope(master, at, peak, 0.012, decay));
  }
  /** A soft breath of noise through a moving low band (the door's slide). */
  function breath(peak, at, span, f0, f1, pan = 0) {
    const s = ctx.createBufferSource(); s.buffer = noise; s.loop = true;
    const f = filter('lowpass', f0, 0.9);
    f.frequency.setValueAtTime(f0, at); f.frequency.exponentialRampToValueAtTime(f1, at + span);
    chain(s, f, envelope(panner(master, pan), at, peak, span * 0.5, span * 0.4));
    s.start(at, Math.random() * noise.duration); s.stop(at + tail(span * 0.5, span * 0.4));
  }

  function build() {
    const AC = window.AudioContext || window.webkitAudioContext;
    if (!AC) return false;
    try { ctx = new AC({ latencyHint: 'playback' }); } catch { ctx = new AC(); }
    noise = ctx.createBuffer(1, ctx.sampleRate * 2, ctx.sampleRate);
    const data = noise.getChannelData(0);
    // Brown noise (integrated white): the weight is low already, so the rumble needs little filtering.
    for (let i = 0, last = 0; i < data.length; i++) { last = (last + 0.02 * (Math.random() * 2 - 1)) / 1.02; data[i] = last * 3.5; }
    master = gainNode(0);
    master.connect(ctx.destination);
    // The echo every note goes through: one delay fed back through a darkening filter.
    wet = gainNode(SOUND.echo);
    const delay = ctx.createDelay(1), feedback = gainNode(SOUND.echoFeedback), dark = filter('lowpass', 1800);
    chain(wet, delay, dark, feedback, delay);
    delay.delayTime.value = SOUND.echoTime;
    dark.connect(master);

    // The stone: brown noise under a low band, one source for every rumble.
    const source = ctx.createBufferSource(); source.buffer = noise; source.loop = true; source.start();
    const rumble = gainNode(0), rumbleLow = filter('lowpass', 120);
    chain(source, rumbleLow, rumble, master);
    // The light moving: a little air from the same source.
    const air = gainNode(0), airBand = filter('bandpass', 500, 0.8);
    chain(source, airBand, air, master);
    // The drone: D and A, low and dark, opening up while the light moves.
    const drone = gainNode(0), droneTone = filter('lowpass', 300);
    oscillator('sine', 73.42).connect(droneTone);
    chain(oscillator('triangle', 110), gainNode(0.4), droneTone);
    chain(droneTone, drone, master);

    v = { rumble, rumbleLow, air, airBand, drone, droneTone };
    return true;
  }

  // ---- on and off ------------------------------------------------------------------------
  const live = () => on && !!ctx && ctx.state === 'running';
  /** Make or resume the context and fade the master up; resolves once it runs (false if it cannot). */
  function wake() {
    if (!on || (!ctx && !build())) return Promise.resolve(false);
    clearTimeout(sleepTimer);
    master.gain.setTargetAtTime(SOUND.master, ctx.currentTime, SOUND.fade);
    return (ctx.state === 'running' ? Promise.resolve() : ctx.resume()).then(live, () => false);
  }
  function sleep() {
    if (!ctx) return;
    master.gain.setTargetAtTime(0, ctx.currentTime, SOUND.fade);
    clearTimeout(sleepTimer);
    sleepTimer = setTimeout(() => { if (!on && ctx.state === 'running') ctx.suspend().catch(() => {}); }, SOUND.fade * 8000);
  }
  /** With sound kept on from a last visit, the first gesture anywhere makes the context. */
  function onGesture() { if (on) wake().then((running) => { if (running) unlisten(); }); }
  const listen = () => GESTURES.forEach((type) => window.addEventListener(type, onGesture, true));
  const unlisten = () => GESTURES.forEach((type) => window.removeEventListener(type, onGesture, true));
  function onVisibility() {
    if (!ctx) return;
    if (document.hidden) ctx.suspend().catch(() => {}); else if (on) ctx.resume().catch(() => {});
  }
  function show() { button?.setAttribute('aria-pressed', on ? 'true' : 'false'); }
  function onToggle() {
    on = !on;
    try { localStorage.setItem(KEY, on ? 'on' : 'off'); } catch { /* storage may be off */ }
    show();
    // Turned on, it answers at once with a soft note, so the visitor knows it is on.
    if (on) wake().then((running) => { if (running) { unlisten(); note(SCALE[0], SOUND.seat); } }); else sleep();
  }

  if (button) {
    show();
    button.addEventListener('click', onToggle);
    document.addEventListener('visibilitychange', onVisibility);
    if (on) listen();
  }

  // ---- the scene -------------------------------------------------------------------------
  const sound = {
    get live() { return live(); },
    /**
     * Every frame: how fast the stone and the light move, as a share of full (0..1), and the swell.
     * @param s { rumble, light, swell, swellHead, swellPan, blocks }
     */
    step(s) {
      if (!live()) return;
      // The swell: a note as its crest reaches each block, climbing the scale round the loop.
      const block = s.swell > 0 ? Math.floor(s.swellHead) : -1;
      if (block !== lastBlock && block >= 0 && lastBlock >= 0) {
        const k = ((block % s.blocks) + s.blocks) % s.blocks;
        note(SCALE[Math.round(k / s.blocks * (SCALE.length - 1))], SOUND.swell * s.swell, ctx.currentTime, s.swellPan, SOUND.noteDecay * 0.6);
      }
      lastBlock = block;
      const t = ctx.currentTime;
      if (t - sentAt < 1 / SOUND.updateHz) return;
      sentAt = t;
      const rumble = clamp01(s.rumble), light = clamp01(s.light);
      send(v.rumble.gain, SOUND.rumble * rumble ** 1.3, 0.002);
      send(v.rumbleLow.frequency, 90 + 90 * rumble, 4);
      send(v.air.gain, SOUND.air * light ** 1.5, 0.002);
      send(v.airBand.frequency, 400 + 700 * light, 10);
      send(v.drone.gain, SOUND.drone * (1 + light), 0.002, SOUND.droneFade);
      send(v.droneTone.frequency, 260 + 500 * light, 8, SOUND.droneFade);
    },
    /** The frame has stopped (through the door): nothing may hang on. */
    hush() {
      if (!ctx) return;
      for (const g of [v.rumble, v.air, v.drone]) { g.gain.setTargetAtTime(0, ctx.currentTime, SOUND.follow); sent.delete(g.gain); }
    },
    /** The paradox locking shut: 1 is the arrival's, a tilt springing shut is a fraction of it. */
    thud(scale) {
      if (!live() || !(scale > 0)) return;
      const at = ctx.currentTime;
      thump(SOUND.thud * Math.min(1, scale) ** 0.7, at, 0.12 + 0.25 * scale);
    },
    /** The light struck from the impact: a low chord blooming slowly under it. */
    ignite() {
      if (!live()) return;
      const at = ctx.currentTime + 0.05;
      for (const f of [SCALE[0], SCALE[3], SCALE[5]]) note(f, SOUND.ignite, at, 0, SOUND.noteDecay * 1.6);
    },
    /** A step landing on the loop, sized by how far it fell (0..1). */
    contact(size) {
      if (!live() || !(size > 0)) return;
      thump(SOUND.contact * size, ctx.currentTime, 0.07, 95, 60);
    },
    /** The light settling on a work: that work's own note. */
    seat(station) {
      if (!live()) return;
      note(SCALE[((station % SCALE.length) + SCALE.length) % SCALE.length], SOUND.seat);
    },
    /** The slot in the riser sliding open (or shut) over `span` seconds. */
    door(opening, span, pan = 0) {
      if (!live()) return;
      const [f0, f1] = opening ? [140, 380] : [380, 140];
      breath(SOUND.door, ctx.currentTime, Math.max(span, 0.12), f0, f1, pan);
    },
    /** The light going in at the door: a falling pair, and a soft low knock once it is in. */
    enter(slide, pan = 0) {
      if (!live()) return;
      const at = ctx.currentTime;
      note(SCALE[5], SOUND.enter, at, pan);
      note(SCALE[0], SOUND.enter, at + slide * 0.6, pan, SOUND.noteDecay * 1.4);
      thump(SOUND.thud * 0.5, at + slide * 0.85, 0.15);
    },
    dispose() {
      unlisten(); clearTimeout(sleepTimer);
      button?.removeEventListener('click', onToggle);
      document.removeEventListener('visibilitychange', onVisibility);
      ctx?.close().catch(() => {});
      ctx = null;
    },
  };
  return sound;
}
