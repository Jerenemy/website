// How far each block stands proud of the loop, and the grammar every lift obeys: a step
// rises fast (easing out) and stops dead; falls faster, accelerating, and stops dead; and
// after either stop sinks once into its new bearing by a few percent of the travel, over-
// damped, so there is never a bounce. Landing on the loop itself is a contact: the frame it
// happens is reported so dust can leave the tread.
//
// The pointed-at step rises a little; the presented step rises to meet the light; steps
// under a passing light stir; the arrival settles every block; and the idle life lifts one
// step at a time with the same grammar at its own pace (src/idle.js). Every lift feeds the
// contact shadows and the seam.
import { MOTION } from './config.js';

const EMPHASIS_RATE = 12;   // 1/s
const SINK_SPAN = 6;        // sink durations (1/rate) after which the sink is below a thousandth

/** One lifting body: value chases target with the grammar above. */
export class Lift {
  /** @param pace { rise, fall } seconds for a full travel; the sink is MOTION.stepSink of it */
  constructor(pace) {
    this.pace = pace;
    this.value = 0; this.target = 0;
    this.from = 0; this.to = 0; this.t = 0;
    this.phase = 0;           // 0 at rest, 1 rising, 2 falling, 3 sinking
    this.sink = 0;            // beams: depth of the sink under way
    this.landed = false;      // true on the frame the body stops on the loop (target 0)
  }
  get resting() { return this.phase === 0 && this.value === this.target; }
  snap(value) { this.value = this.target = value; this.phase = 0; this.landed = false; }
  step(dt) {
    this.landed = false;
    if (this.target !== this.to) {
      // A new target: the move starts from wherever the body is, whichever way it was going.
      this.from = this.value; this.to = this.target; this.t = 0;
      this.phase = this.to > this.from ? 1 : 2;
    }
    if (this.phase === 0) return this.value;
    this.t += dt;
    const travel = this.to - this.from;
    if (this.phase === 1) {
      const f = Math.min(1, this.t / this.pace.rise);
      this.value = this.from + travel * (1 - (1 - f) ** 3);      // easing out, to a dead stop
      if (f >= 1) this.stop(travel);
    } else if (this.phase === 2) {
      const f = Math.min(1, this.t / this.pace.fall);
      this.value = this.to - travel * (1 - f * f);                // accelerating, to a dead stop
      if (f >= 1) this.stop(travel);
    } else {
      const k = MOTION.stepSinkRate * this.t;
      this.value = this.to - this.sink * k * Math.exp(1 - k);     // one over-damped sink, no oscillation
      if (k >= SINK_SPAN) { this.phase = 0; this.value = this.to; }
    }
    return this.value;
  }
  stop(travel) {
    this.value = this.to; this.t = 0; this.phase = 3;
    this.sink = MOTION.stepSink * Math.abs(travel);
    this.landed = this.to === 0;
  }
}

export function createLifts(tribar) {
  const { blocks, stepCount: stations } = tribar;
  const pace = { rise: MOTION.stepRise, fall: MOTION.stepFall };
  const lifts = blocks.map(() => new Lift(pace));
  const pass = new Float32Array(blocks.length);
  const now = new Float32Array(blocks.length);
  const emphasis = new Float32Array(blocks.length);
  const landed = [], fallen = new Float32Array(blocks.length);
  let resting = false;

  return {
    now, emphasis,
    /** Blocks that stopped on the loop this frame: each wants a puff of dust, sized by how
     *  far it fell (`fallen`, beams, valid for those blocks). */
    landed, fallen,
    /** True when every block is exactly where its targets put it (the idle lift aside). */
    get resting() { return resting; },
    /**
     * @param s { focusBlock, selectedBlock, heldBlock, light: Spring, calm, settling, beatBlock, beatLift }
     *          heldBlock: a step that stays up for the light still coming home from its door, or -1
     *          settling: extra per-block lift (the arrival), or null; beatBlock: the block the
     *          idle life is lifting by beatLift, or -1
     */
    step(dt, s) {
      const passing = s.calm ? 0 : MOTION.passLift * Math.min(1, Math.abs(s.light.velocity) / MOTION.passSpeed);
      const ease = 1 - Math.exp(-dt * EMPHASIS_RATE), passEase = 1 - Math.exp(-dt * MOTION.passRate);
      resting = !s.settling;
      landed.length = 0;
      for (let i = 0; i < lifts.length; i++) {
        const lift = lifts[i];
        lift.target = i === s.selectedBlock || i === s.heldBlock ? MOTION.selectLift : i === s.focusBlock ? MOTION.hoverLift : 0;
        if (s.calm) lift.snap(lift.target); else lift.step(dt);
        if (lift.landed) { landed.push(i); fallen[i] = lift.sink / MOTION.stepSink; }
        // The stir under a passing light is an envelope that travels with the light, not a
        // lift of its own: it follows the light's position directly.
        let stir = 0;
        const station = blocks[i].station;
        if (passing > 0 && station >= 0 && i !== s.selectedBlock && i !== s.heldBlock) {
          let away = Math.abs(s.light.value - station) % stations;     // distance round the loop
          if (away > stations / 2) away = stations - away;
          if (away < MOTION.passReach) stir = passing * (1 - away / MOTION.passReach) ** 2;
        }
        pass[i] = s.calm ? stir : pass[i] + (stir - pass[i]) * passEase;
        if (Math.abs(pass[i] - stir) < 1e-6) pass[i] = stir;
        now[i] = lift.value + pass[i] + (s.settling ? s.settling[i] : 0) + (i === s.beatBlock ? s.beatLift : 0);
        const pointed = i === s.focusBlock ? 1 : 0;
        emphasis[i] = s.calm ? pointed : emphasis[i] + (pointed - emphasis[i]) * ease;
        if (Math.abs(emphasis[i] - pointed) < 1e-6) emphasis[i] = pointed;   // land it, like a spring
        if (!lift.resting || pass[i] !== stir || emphasis[i] !== pointed) resting = false;
      }
    },
  };
}
