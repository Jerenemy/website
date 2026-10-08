// The building moves on its own. Two beats, timed from the visitor's last touch and only
// while the monument is seated. Neither may move the current, pointed-at or presented
// step, nor the step in front of the presented one (its door's sill), and neither runs
// under reduced motion.
//
//   The lift. Now and then one other step rises out of the loop, hangs, and drops: the
//   step grammar of src/lifts.js at a slower pace (rise, dead stop, fall, dead stop, one
//   sink into the bearing, dust at the contact). Should the visitor reach that step
//   mid-flight, it is let down at once from wherever it is.
//
//   The swell. A faint crest of light runs one full lap round the arrises, from the
//   visitor's own step and back to it, in the scroll direction: "a loop with no first or
//   last", and which way it goes, said by motion instead of words.
import { MOTION } from './config.js';
import { Lift } from './lifts.js';

export function createIdle(tribar) {
  const { blocks } = tribar;
  const count = blocks.length;
  const steps = blocks.map((_, i) => i).filter((i) => blocks[i].step >= 0);
  const lapTime = Math.max(MOTION.swellMinLap, count / MOTION.swellSpeed);
  let seed = 11;
  const random = () => ((seed = (seed * 16807) % 2147483647) / 2147483647);

  let idleFor = 0, liftDue = MOTION.liftFirst, swellDue = MOTION.swellFirst, lastLifted = -1;
  const lift = new Lift({ rise: MOTION.liftRise, fall: MOTION.liftFall });
  let block = -1, hang = 0;    // the lifted block, and how long it has hung at the top
  const swell = { t: -1, from: 0 };

  const out = {
    /** The lifted block and how far it stands proud (negative while it sinks), or -1. */
    block: -1, lift: 0,
    /** Head of the crest in loop units (block index + fraction) and its weight, 0 when off. */
    swellHead: 0, swellAmp: 0,
    /** The block that landed this frame, or -1: it wants a puff of dust. */
    landed: -1,
    /** True when neither beat is in flight. */
    resting: true,
  };

  function rewind() { idleFor = 0; liftDue = MOTION.liftFirst; swellDue = MOTION.swellFirst; }

  return Object.assign(out, {
    /** The visitor did something (a click, a key, the wheel, a drag): both beats start over. */
    touch: rewind,
    /** The pointer merely moved: the lift waits for stillness, but the swell, which teaches the
     *  scroll direction, still plays once on every landing, so a visitor who keeps the mouse moving sees it. */
    stir() { liftDue = idleFor + MOTION.liftFirst; },
    /**
     * @param s { calm, quiet, seated, currentBlock, focusBlock, selectedBlock }
     *          quiet: the arrival; seated: the monument is at rest on a station
     */
    step(dt, s) {
      out.landed = -1;
      if (s.calm || s.quiet) {
        lift.snap(0); block = -1; swell.t = -1; rewind();
        out.block = -1; out.lift = 0; out.swellAmp = 0; out.resting = true;
        return;
      }
      // Nor the step in front of a presented one: its tread lies under the open door's sill, and
      // the lift (liftHeight) would raise it over the sill and into the opening.
      const below = s.selectedBlock >= 0 ? (s.selectedBlock + 1) % count : -1;
      const busy = (i) => i === s.currentBlock || i === s.focusBlock || i === s.selectedBlock || i === below;
      if (s.seated) idleFor += dt;

      // ---- the lift ------------------------------------------------------------------
      if (block < 0 && idleFor >= liftDue) {
        liftDue += MOTION.liftEvery;
        const free = steps.filter((i) => !busy(i) && i !== lastLifted);
        if (free.length) {
          block = free[Math.floor(random() * free.length)];
          lastLifted = block;
          lift.target = MOTION.liftHeight; hang = 0;
        }
      }
      if (block >= 0) {
        if (lift.target > 0 && lift.phase !== 1) hang += dt;     // the hang counts from the dead stop
        if (lift.target > 0 && (busy(block) || hang >= MOTION.liftHang)) lift.target = 0;
        lift.step(dt);
        if (lift.landed) out.landed = block;
        if (lift.target === 0 && lift.resting) block = -1;
      }
      out.block = block; out.lift = block >= 0 ? lift.value : 0;

      // ---- the swell -----------------------------------------------------------------
      if (swell.t < 0 && idleFor >= swellDue) {
        swellDue += MOTION.swellEvery;
        swell.t = 0;
        swell.from = (s.currentBlock >= 0 ? s.currentBlock : 0) + MOTION.swellCentre;
      }
      if (swell.t >= 0) {
        swell.t += dt;
        const progress = swell.t / lapTime;
        if (progress >= 1) { swell.t = -1; out.swellAmp = 0; } else {
          out.swellHead = swell.from + progress * count;
          out.swellAmp = Math.min(1, Math.min(progress, 1 - progress) * MOTION.swellEnvelope);
        }
      }
      out.resting = block < 0 && swell.t < 0;
    },
  });
}
