// The arrival, as a pure function of time: three monoliths hang apart in the dark, drift
// home while the view swings toward the one true angle, and the last degree falls shut.
//
// The swing is a line of sight fixed to the monument, not to the screen, so the event the eye
// sees is one that has been proven, wherever the loop opens: authored as seen landing on the
// first work docked at the left, and for any other dock (a deep link, a reload, a phone's dock
// below) turned about the true axis, within INTRO.turnRange, so that the seam's tear lies along
// the screen's long side and the monoliths stay in frame.
//
// Pure arithmetic, no renderer types, so tools/check-geometry.mjs can sample the whole
// timeline in node and prove it physical: each side only ever moves along a path that keeps
// both of its real joints open until they close (the next side hangs further along both
// travel axes that meet at the corner, and each twist is about the side's own centre, small
// next to that clearance), so no block passes through another; and the seam's two ends are
// ordered by the phantom rule of src/seam.js, so the far start reads in front of the near end
// from the first pixel they share.
import { INTRO, LAYOUT } from './config.js';
import { VIEW_AXIS, viewDirection } from './tribar.js';
import { ramp, easeOutCubic, easeInOutCubic, easeInQuad, easeOutQuint } from './spring.js';

const TWIST_AXIS = [[0, 1, 0], [0, 0, 1], [1, 0, 0]];

/** Row-major rotation by `angle` about the unit `axis` (Rodrigues), written into `out`. */
function rotation(axis, angle, out) {
  const [x, y, z] = axis, c = Math.cos(angle), s = Math.sin(angle), k = 1 - c;
  out[0] = c + x * x * k;     out[1] = x * y * k - z * s; out[2] = x * z * k + y * s;
  out[3] = y * x * k + z * s; out[4] = c + y * y * k;     out[5] = y * z * k - x * s;
  out[6] = z * x * k - y * s; out[7] = z * y * k + x * s; out[8] = c + z * z * k;
  return out;
}

export function createIntro(tribar) {
  const { blocks, pivot, sideCentre } = tribar;
  const A = VIEW_AXIS;
  // Each side hangs outward in the picture plane and a little along the view axis (side 0
  // furthest, side 2 nearest), so each one waits beyond the next along both travel axes of
  // the corner they share.
  const drift = sideCentre.map((centre, k) => {
    const c = [0, 1, 2].map((i) => centre[i] - pivot[i]);
    const along = c[0] * A[0] + c[1] * A[1] + c[2] * A[2];
    for (let i = 0; i < 3; i++) c[i] -= A[i] * along;
    const len = Math.hypot(c[0], c[1], c[2]);
    return c.map((v, i) => (v / len) * INTRO.sideDrift + A[i] * INTRO.sideDepth * (k - 1));
  });
  const jitter = blocks.map((_, i) => 0.45 + 0.55 * Math.abs(Math.sin(i * 12.9898) * 43758.5453 % 1));
  const snapFraction = INTRO.snapFrom / Math.abs(INTRO.startYaw);
  const authored = LAYOUT.wide.restAngle - tribar.thetaAt(0);
  const [turnMin, turnMax] = INTRO.turnRange;

  const out = {
    exposure: 0, roll: 0, zoom: 1, assembled: 0,
    /** The line of sight, toward the eye, structure space (src/frame.js turns it into a tilt). */
    view: VIEW_AXIS.slice(),
    /** Per side: a translation and a row-major rotation about the side's centre (tribar.sideCentre). */
    sideOff: [[0, 0, 0], [0, 0, 0], [0, 0, 0]],
    sideRot: [0, 1, 2].map(() => rotation(TWIST_AXIS[0], 0, new Float64Array(9))),
    lift: new Float32Array(blocks.length),
    /** Per corner, how far apart (beams) its two sides still hang; corner 0 is the seam, which
     *  never touches in 3D (src/seam.js measures its tear). */
    apart: [0, 0, 0],
  };
  const closing = [0, 1, 2].map((k) => { const p = (k + 2) % 3; return Math.hypot(...drift[k].map((v, i) => v - drift[p][i])); });
  const away = [0, 0, 0];

  const intro = {
    duration: INTRO.duration,
    /** Radians about the true axis the authored swing is turned by (set by dock). */
    turn: 0,
    /**
     * Fix the swing for an arrival that opens with `station` at the dock: the monument is then
     * rolled by delta from the authored view, and the swing is turned by delta, plus a quarter
     * turn when the screen is taller than wide, modulo a half turn (a tear either way along an
     * axis frames the same), into the proven range.
     */
    dock(station, restAngle, portrait) {
      let turn = restAngle - tribar.thetaAt(station) - authored + (portrait ? Math.PI / 2 : 0);
      turn -= Math.PI * Math.floor((turn - turnMin) / Math.PI);          // into [turnMin, turnMin + pi)
      if (turn > turnMax) turn = turn - turnMax < turnMin + Math.PI - turn ? turnMax : turnMin;   // the nearer end
      intro.turn = turn;
      return turn;
    },
    sample(t) {
      out.exposure = easeOutCubic(ramp(t, INTRO.fadeIn[0], INTRO.fadeIn[1]));
      for (let k = 0; k < 3; k++) {
        away[k] = 1 - easeInOutCubic(ramp(t, INTRO.converge[0] + k * INTRO.stagger, INTRO.converge[1] - (2 - k) * INTRO.stagger));
        for (let i = 0; i < 3; i++) out.sideOff[k][i] = drift[k][i] * away[k];
        rotation(TWIST_AXIS[k], INTRO.sideTwist * (k === 1 ? -1 : 1) * away[k], out.sideRot[k]);
      }
      for (let k = 1; k < 3; k++) out.apart[k] = Math.max(away[k - 1], away[k]) * closing[k];
      // Swing: ease out toward a hair short of true. Snap: the hair closes accelerating,
      // the way a heavy latch drops, so the stop is abrupt and the impact has a moment.
      const swing = 1 - (1 - snapFraction) * easeOutQuint(ramp(t, INTRO.swing[0], INTRO.swing[1]));
      const open = t < INTRO.snap[0] ? swing : snapFraction * (1 - easeInQuad(ramp(t, INTRO.snap[0], INTRO.snap[1])));
      out.roll = INTRO.startRoll * (1 - easeInOutCubic(ramp(t, 0, INTRO.swing[1])));
      viewDirection(authored + intro.turn + out.roll, INTRO.startYaw * open, INTRO.startPitch * open, out.view);
      out.zoom = INTRO.startZoom + (1 - INTRO.startZoom) * easeInOutCubic(ramp(t, 0, INTRO.snap[1]));
      out.assembled = ramp(t, INTRO.converge[1] - 0.3, INTRO.converge[1]);
      const [settleFrom, settleStep, settleSpan] = INTRO.settle;
      for (let i = 0; i < blocks.length; i++) {
        const start = settleFrom + i * settleStep;
        out.lift[i] = INTRO.settleLift * jitter[i] * (1 - easeOutCubic(ramp(t, start, start + settleSpan)));
      }
      return out;
    },
  };
  return intro;
}
