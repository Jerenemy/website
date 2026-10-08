// The one motion that opens the paradox. Moving the pointer asks for a tilt; the request
// bleeds away as soon as the pointer rests, or the moment it is over a step (a target must
// not flee), and once it is nearly gone it is dropped outright and the spring stiffens, so
// the last of the gap closes as a snap rather than a long tail. While the pointer is still
// moving the request is never dropped, however small: an ordinary sweep builds the tilt up
// from nothing (a 500 px/s sweep settles near 3 degrees); only a pointer that has rested for
// a few frames lets go.
//
// The snap shut is reported with how wide the seam was torn since it last locked, so the
// strike can be sized to the tear: a real reveal locks with a jolt, a hand coming to rest
// after an ordinary move does not spend the arrival's signature beat.
import { MOTION } from './config.js';
import { Spring, clamp } from './spring.js';
import { TILT_CONE } from './tribar.js';

const SHUT = 0.004;   // radians: below this the paradox has locked

export function createTilt() {
  const want = { x: 0, y: 0 };
  const yaw = new Spring(0, MOTION.tiltOmega, MOTION.tiltZeta);
  const pitch = new Spring(0, MOTION.tiltOmega, MOTION.tiltZeta);
  let peak = 0, sincePush = 1e3;

  return {
    yaw, pitch,
    get amount() { return Math.hypot(yaw.value, pitch.value); },
    /** Closed to within the lock: what the eye reads as the true view. */
    get shut() { return Math.hypot(yaw.value, pitch.value) < SHUT; },
    /** Shut and still, with no request pending. */
    get resting() { return want.x === 0 && want.y === 0 && yaw.resting && pitch.resting; },
    /** @param aiming true while the pointer is on a step: the request is frozen, and bleeds
     *         away with the usual hold, so the target holds still for the click. */
    push(dx, dy, aiming) {
      if (aiming) return;
      sincePush = 0;
      want.x = clamp(want.x + dx * MOTION.tiltGain, -MOTION.tiltMax, MOTION.tiltMax);
      want.y = clamp(want.y + dy * MOTION.tiltGain, -MOTION.tiltMax, MOTION.tiltMax);
    },
    /** Drop the request now, as if the pointer had long rested: the seam snaps shut. */
    release() { want.x = want.y = 0; sincePush = 1e3; },
    /** @returns 0, or on the frame the paradox locks shut again, the widest tear (radians)
     *           since it last locked. */
    step(dt, calm) {
      if (calm) { want.x = want.y = 0; yaw.snap(0); pitch.snap(0); peak = 0; sincePush = 1e3; return 0; }
      const bleed = Math.exp(-dt / MOTION.tiltHold);
      want.x *= bleed; want.y *= bleed;
      sincePush += dt;
      const letGo = sincePush > MOTION.tiltRest && Math.hypot(want.x, want.y) < MOTION.tiltLockBelow;
      if (letGo) want.x = want.y = 0;
      yaw.omega = pitch.omega = letGo ? MOTION.tiltLockOmega : MOTION.tiltOmega;
      yaw.target = want.x; pitch.target = want.y;
      yaw.step(dt); pitch.step(dt);

      let open = Math.hypot(yaw.value, pitch.value);
      // The geometry is proven over TILT_CONE (tools/check-geometry.mjs); the springs' own
      // bound keeps them inside it, and this makes it a guarantee.
      if (open > TILT_CONE) { const k = TILT_CONE / open; yaw.value *= k; pitch.value *= k; open = TILT_CONE; }
      if (open > peak) peak = open;
      if (peak >= SHUT && letGo && open < SHUT) { const tear = peak; peak = 0; return tear; }
      return 0;
    },
  };
}
