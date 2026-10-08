// The monument, as pure geometry (no renderer types, so it can be unit-checked in node).
//
// A Penrose tribar is three mutually perpendicular beams laid end to end:
//   side 0 travels +x, side 1 travels +y, side 2 travels +z.
// The chain does NOT close. Its end sits `gap` away from its start, and `gap` is made
// exactly parallel to (1,1,1). An orthographic camera looking down (1,1,1) cannot see
// displacement along its own axis, so the far start and the near end land on the same
// pixels: the loop closes on screen and nowhere else.
//
// Each side is cut into steps (one per work). Step j of a side is the same block as step
// j-1 pushed `rise` down that side's own "up" (its tread normal). The three sides use three
// different ups, cyclically:
//   side k: travel = axis k, tread normal = axis k-1 (the direction the PREVIOUS side
//   travelled), wall = axis k+1 (the direction the NEXT side will travel).
// With that choice every tread faces the camera and faces outward from the triangle.
//
// Closing condition. Walking side k moves the chain by
//   (body_k + beam) along travel,  -(n_k - 1) * rise  along tread,   (+/- beam/2 terms cancel)
// so with body_k = span - beam + (n_{k+1} - 1) * rise the three sides sum to
//   gap = span * (1,1,1)
// for ANY step counts. The true view axis never changes; only the proportions do.

import { DIM, MOTION } from './config.js';

export const VIEW_AXIS = [1 / Math.sqrt(3), 1 / Math.sqrt(3), 1 / Math.sqrt(3)];
// Orthonormal image basis for the true view (structure space -> screen right / up).
export const IMAGE_RIGHT = [1 / Math.SQRT2, 0, -1 / Math.SQRT2];
export const IMAGE_UP = [-1 / Math.sqrt(6), 2 / Math.sqrt(6), -1 / Math.sqrt(6)];

const SIDE_AXES = [
  { a: 0, t: 2, b: 1 },
  { a: 1, t: 0, b: 2 },
  { a: 2, t: 1, b: 0 },
];
const SIDES = 3;
const PATH_SAMPLES = 48;      // per segment between two stations
const PATH_OVERSAMPLE = 6;

const add = (p, q) => [p[0] + q[0], p[1] + q[1], p[2] + q[2]];
const sub = (p, q) => [p[0] - q[0], p[1] - q[1], p[2] - q[2]];
const dot = (p, q) => p[0] * q[0] + p[1] * q[1] + p[2] * q[2];
const lerp3 = (p, q, u) => [p[0] + (q[0] - p[0]) * u, p[1] + (q[1] - p[1]) * u, p[2] + (q[2] - p[2]) * u];
export const toImage = (p) => [dot(p, IMAGE_RIGHT), dot(p, IMAGE_UP)];

function splitSteps(total) {
  const base = Math.floor(total / SIDES), extra = total % SIDES;
  return [0, 1, 2].map((k) => base + (k < extra ? 1 : 0));
}

/**
 * Shadow of one axis-aligned box on another along a direction, exactly. Box P slid back along
 * `dir` by t meets box S iff on every axis |Pc_i - t·d_i - Sc_i| <= Ph_i + Sh_i, which is one
 * t-interval per axis (every component of a view direction is positive); the three must share
 * a point. Returns [lo, hi] or null: their images along `dir` overlap iff the interval exists,
 * and P's shadow falls on S iff hi >= 0 (P in front).
 */
export function shadowInterval(pc, ph, sc, sh, dir = VIEW_AXIS) {
  let lo = -Infinity, hi = Infinity;
  for (let i = 0; i < 3; i++) {
    const r = ph[i] + sh[i], c = pc[i] - sc[i];
    lo = Math.max(lo, (c - r) / dir[i]); hi = Math.min(hi, (c + r) / dir[i]);
  }
  return lo <= hi ? [lo, hi] : null;
}

/**
 * The direction toward the eye in structure space, for a monument rolled by `phi` about the true
 * axis and then tilted by `pitch` (about screen x) and `yaw` (about screen y), in that Euler
 * order (src/stage.js turns the rig by exactly this): the third row of the structure-to-world
 * rotation. At yaw = pitch = 0 it is VIEW_AXIS whatever the roll.
 */
export function viewDirection(phi, yaw, pitch, out = [0, 0, 0]) {
  const c = Math.cos(phi), n = Math.sin(phi);
  const sx = -Math.sin(yaw) * Math.cos(pitch), sy = Math.sin(pitch), sz = Math.cos(yaw) * Math.cos(pitch);
  for (let i = 0; i < 3; i++) {
    out[i] = sx * (c * IMAGE_RIGHT[i] - n * IMAGE_UP[i]) + sy * (n * IMAGE_RIGHT[i] + c * IMAGE_UP[i]) + sz * VIEW_AXIS[i];
  }
  return out;
}

/**
 * The inverse of viewDirection: the yaw and pitch that make a monument rolled by `phi` show
 * `view` (a unit vector toward the eye, structure space). Written into out as [yaw, pitch].
 */
export function tiltToward(view, phi, out = [0, 0]) {
  const c = Math.cos(phi), n = Math.sin(phi);
  let sx = 0, sy = 0, sz = 0;
  for (let i = 0; i < 3; i++) {
    sx += view[i] * (c * IMAGE_RIGHT[i] - n * IMAGE_UP[i]);
    sy += view[i] * (n * IMAGE_RIGHT[i] + c * IMAGE_UP[i]);
    sz += view[i] * VIEW_AXIS[i];
  }
  out[0] = Math.atan2(-sx, sz);
  out[1] = Math.asin(Math.max(-1, Math.min(1, sy)));
  return out;
}

/** The largest angle between the view and the true axis the pointer can make: both tilt axes
 *  at their limit, times the worst case of their under-damped spring driven by a target that
 *  moves anywhere within that limit (the L1 norm of its impulse response, (1 + e) / (1 - e)
 *  with e the step overshoot; a single step overshoots only by e). src/tilt.js also clamps
 *  the drawn tilt to this cone, so the proof's cone is a guarantee. */
const TILT_OVERSHOOT = Math.exp(-Math.PI * MOTION.tiltZeta / Math.sqrt(1 - MOTION.tiltZeta * MOTION.tiltZeta));
export const TILT_CONE = Math.hypot(MOTION.tiltMax, MOTION.tiltMax) * (1 + TILT_OVERSHOOT) / (1 - TILT_OVERSHOOT);

/** A block's box with its whole range of travel along its tread (-sinkReach to liftReach) swept in. */
export function liftedBox(blk, shift = [0, 0, 0]) {
  const { liftReach, sinkReach } = DIM;
  const center = [0, 1, 2].map((i) => blk.center[i] + shift[i] + (i === blk.tread ? (liftReach - sinkReach) / 2 : 0));
  const half = [0, 1, 2].map((i) => blk.half[i] + (i === blk.tread ? (liftReach + sinkReach) / 2 : 0));
  return { center, half };
}

/**
 * @param {number} stationCount number of works
 * @returns the block list, the gap vector, the light's path, and the tables that tell
 *          the stage how to turn the monument so a given loop position rests in place.
 */
export function buildTribar(stationCount) {
  const { beam: w, span, rise: h } = DIM;
  const stepCount = Math.max(stationCount, DIM.minSteps);
  const counts = splitSteps(stepCount);
  const body = (k) => span - w + (counts[(k + 1) % SIDES] - 1) * h;

  // --- frames -------------------------------------------------------------
  // origin[k] is the start of side k's body, on its first tread plane, at wall centre.
  // origin[3] is where side 0 would have to start for the loop to close in 3D.
  const origin = [[0, 0, 0]];
  for (let k = 0; k < SIDES; k++) {
    const { a, t, b } = SIDE_AXES[k];
    const o = origin[k].slice();
    o[a] += body(k) + w;
    o[t] += -(counts[k] - 1) * h - w / 2;
    o[b] += w / 2;
    origin.push(o);
  }
  const gap = sub(origin[SIDES], origin[0]);
  const local = (k, la, lt, lb) => {
    const { a, t, b } = SIDE_AXES[k % SIDES];
    const p = k >= SIDES ? add(origin[k % SIDES], gap) : origin[k].slice();
    p[a] += la; p[t] += lt; p[b] += lb;
    return p;
  };
  const box = (k, a0, a1, t0, t1) => {
    const lo = local(k, a0, t0, -w / 2), hi = local(k, a1, t1, w / 2);
    return { center: lerp3(lo, hi, 0.5), half: [(hi[0] - lo[0]) / 2, (hi[1] - lo[1]) / 2, (hi[2] - lo[2]) / 2] };
  };

  // --- blocks, in loop order: [cube0, steps of side 0, cube1, steps of side 1, ...] ----
  const blocks = [];
  const stepBlocks = [];
  for (let k = 0; k < SIDES; k++) {
    const { a, t } = SIDE_AXES[k];
    const run = body(k) / counts[k];
    // [-x,-y,-z,+x,+y,+z]: 0 where the face is free, 1 where a block of the same side is
    // attached, 2 + c where the face meets the previous or next side at corner c (corner k is
    // where side k-1 arrives under cube k; corner 0 is the seam). A corner's joint is only a
    // joint while its two blocks touch: the arrival brings them together, a tilt tears the seam.
    const joints = [0, 0, 0, 0, 0, 0];
    // Corner cube: the previous side arrives underneath it (-tread), this side leaves at +travel.
    const cubeJoints = joints.slice(); cubeJoints[t] = 2 + k; cubeJoints[3 + a] = 1;
    blocks.push({ ...box(k, -w, 0, -w, 0), side: k, step: -1, station: -1, travel: a, tread: t, joints: cubeJoints });
    for (let j = 0; j < counts[k]; j++) {
      const stepJoints = joints.slice(); stepJoints[a] = 1; stepJoints[3 + a] = j === counts[k] - 1 ? 2 + (k + 1) % SIDES : 1;
      const index = stepBlocks.length;
      stepBlocks.push(blocks.length);
      blocks.push({
        ...box(k, j * run, (j + 1) * run, -j * h - w, -j * h),
        side: k, step: j, station: index < stationCount ? index : -1,
        travel: a, tread: t, joints: stepJoints,
      });
    }
  }

  // --- occluders for contact shadows ------------------------------------------
  // Each block is shadowed by its two loop neighbours. Across the seam the neighbour is
  // referenced where the paradox says it is (shifted by +/- gap), so the shading closes too.
  const count = blocks.length;
  const neighbour = (i, dir) => {
    let j = i + dir, shift = [0, 0, 0];
    if (j >= count) { j -= count; shift = gap; }
    if (j < 0) { j += count; shift = [-gap[0], -gap[1], -gap[2]]; }
    return { index: j, shift };
  };
  blocks.forEach((blk, i) => {
    const prev = neighbour(i, -1);
    let next = neighbour(i, 1);
    // The last step of a side is flush with the corner cube; what actually stands over its
    // wall is the first step of the next side.
    if (blk.step >= 0 && blocks[next.index].step < 0) {
      const beyond = neighbour(next.index, 1);
      next = { index: beyond.index, shift: add(next.shift, beyond.shift) };
    }
    blk.occluders = [prev, next].map((n) => ({ ...n, cross: blocks[n.index].side !== blk.side }));
  });

  // --- the light's path -------------------------------------------------------
  const stations = stepBlocks.map((bi) => {
    const blk = blocks[bi];
    const run = body(blk.side) / counts[blk.side];
    return {
      block: bi,
      anchor: local(blk.side, (blk.step + 0.5) * run, -blk.step * h + DIM.hover, 0),
      tread: local(blk.side, (blk.step + 0.5) * run, -blk.step * h, 0),
    };
  });

  const segments = []; // one per station: dense points from station i to station i+1
  for (let i = 0; i < stepCount; i++) {
    const from = blocks[stepBlocks[i]];
    const to = blocks[stepBlocks[(i + 1) % stepCount]];
    const k = from.side;
    const wraps = i === stepCount - 1;
    const p0 = stations[i].anchor;
    const dense = [];
    let hopAxis = -1;
    if (to.side === k && !wraps) {
      const p1 = stations[i + 1].anchor;
      for (let m = 0; m <= PATH_SAMPLES * PATH_OVERSAMPLE; m++) dense.push(lerp3(p0, p1, m / (PATH_SAMPLES * PATH_OVERSAMPLE)));
      hopAxis = from.tread;
    } else {
      // Round the corner: straight to the corner entry, a cubic that is tangent to both
      // sides' travel directions, straight on to the next station. Built entirely in
      // "near" coordinates (side k+1, even when that is the phantom side 3).
      const runIn = body(k) / counts[k], runOut = body((k + 1) % SIDES) / counts[(k + 1) % SIDES];
      const mIn = Math.min(runIn / 2, DIM.cornerInset), mOut = Math.min(runOut / 2, DIM.cornerInset);
      const top = -(counts[k] - 1) * h + DIM.hover;
      const pin = local(k, body(k) - mIn, top, 0);
      const pout = local(k + 1, mOut, DIM.hover, 0);
      const pEnd = local(k + 1, runOut / 2, DIM.hover, 0);
      const c1 = local(k, body(k) + (w + DIM.hover) * 0.72, top, 0);
      const c2 = local(k + 1, -(w / 2 + DIM.hover) * 0.72, DIM.hover, 0);
      const pieces = [
        (u) => lerp3(p0, pin, u),
        (u) => { const v = 1 - u; return [0, 1, 2].map((c) => v * v * v * pin[c] + 3 * v * v * u * c1[c] + 3 * v * u * u * c2[c] + u * u * u * pout[c]); },
        (u) => lerp3(pout, pEnd, u),
      ];
      const per = PATH_SAMPLES * PATH_OVERSAMPLE;
      pieces.forEach((f, pi) => { for (let m = pi ? 1 : 0; m <= per; m++) dense.push(f(m / per)); });
    }
    // Resample to uniform speed ON SCREEN (image arc length), which is what the eye follows.
    const acc = [0];
    for (let m = 1; m < dense.length; m++) {
      const a2 = toImage(dense[m - 1]), b2 = toImage(dense[m]);
      acc.push(acc[m - 1] + Math.hypot(b2[0] - a2[0], b2[1] - a2[1]));
    }
    const points = [];
    let cursor = 0;
    for (let m = 0; m <= PATH_SAMPLES; m++) {
      const want = (acc[acc.length - 1] * m) / PATH_SAMPLES;
      while (cursor < acc.length - 2 && acc[cursor + 1] < want) cursor++;
      const spanLen = acc[cursor + 1] - acc[cursor] || 1;
      points.push(lerp3(dense[cursor], dense[cursor + 1], (want - acc[cursor]) / spanLen));
    }
    segments.push({ points, hopAxis, wraps, length: acc[acc.length - 1] });
  }

  // --- how the monument must turn ------------------------------------------------
  // Image centre of the triangle; depth-centred so a tilt opens both ends of the seam evenly.
  const cubes = blocks.filter((blk) => blk.step < 0).map((blk) => blk.center);
  let pivot = [0, 1, 2].map((c) => (cubes[0][c] + cubes[1][c] + cubes[2][c]) / 3);
  const depthMid = dot(cubes[0], VIEW_AXIS) + dot(gap, VIEW_AXIS) / 2;
  pivot = add(pivot, VIEW_AXIS.map((c) => c * (depthMid - dot(pivot, VIEW_AXIS))));
  const centre2 = toImage(pivot);

  // Polar angle (unwrapped) and radius of the path, as seen from the true angle.
  const theta = new Float32Array(stepCount * PATH_SAMPLES + 1);
  const rho = new Float32Array(stepCount * PATH_SAMPLES + 1);
  let last = 0;
  for (let i = 0; i < stepCount; i++) {
    for (let m = 0; m < PATH_SAMPLES + (i === stepCount - 1 ? 1 : 0); m++) {
      const q = toImage(segments[i].points[m]);
      const dx = q[0] - centre2[0], dy = q[1] - centre2[1];
      let ang = Math.atan2(dy, dx);
      const n = i * PATH_SAMPLES + m;
      if (n > 0) { while (ang - last > Math.PI) ang -= 2 * Math.PI; while (ang - last < -Math.PI) ang += 2 * Math.PI; }
      theta[n] = ang; rho[n] = Math.hypot(dx, dy); last = ang;
    }
  }
  const turn = theta[theta.length - 1] - theta[0]; // +/- 2 pi per lap

  let radius = 0; // bounding radius of the silhouette about the image centre
  for (const blk of blocks) {
    for (let c = 0; c < 8; c++) {
      const corner = [0, 1, 2].map((ax) => blk.center[ax] + blk.half[ax] * ((c >> ax) & 1 ? 1 : -1));
      const q = toImage(corner);
      radius = Math.max(radius, Math.hypot(q[0] - centre2[0], q[1] - centre2[1]));
    }
  }
  let rhoMin = Infinity, rhoMax = 0;
  for (let i = 0; i < stepCount; i++) { const r = rho[i * PATH_SAMPLES]; rhoMin = Math.min(rhoMin, r); rhoMax = Math.max(rhoMax, r); }

  const scratch = [0, 0, 0];
  /**
   * Position of the light at loop position s (in stations, any real number).
   * @param end  in the seam segment the light exists at both ends of the chain, one gap
   *             apart along the view axis: 0 = the near end, 1 = the far start (really where
   *             it is once past the corner), undefined = whichever side of the corner it is on.
   */
  function pathAt(s, out = scratch, end) {
    const wrapped = ((s % stepCount) + stepCount) % stepCount;
    const i = Math.min(Math.floor(wrapped), stepCount - 1);
    const seg = segments[i];
    const f = (wrapped - i) * PATH_SAMPLES;
    const m = Math.min(Math.floor(f), PATH_SAMPLES - 1), u = f - m;
    const p = seg.points[m], q = seg.points[m + 1];
    out[0] = p[0] + (q[0] - p[0]) * u; out[1] = p[1] + (q[1] - p[1]) * u; out[2] = p[2] + (q[2] - p[2]) * u;
    if (seg.hopAxis >= 0) out[seg.hopAxis] += DIM.hop * Math.sin(Math.PI * (wrapped - i));
    // From the true angle the two ends coincide on screen, so the choice is invisible there.
    const far = end === undefined ? wrapped - i >= 0.5 : end === 1;
    if (seg.wraps && far) { out[0] -= gap[0]; out[1] -= gap[1]; out[2] -= gap[2]; }
    return out;
  }
  /** 0 before the seam crossing, 1 after it, a smooth ramp through the middle of the seam
   *  segment: how much of the light belongs to the far start rather than the near end. */
  function seamBlend(s) {
    const wrapped = ((s % stepCount) + stepCount) % stepCount;
    const f = wrapped - (stepCount - 1);
    if (f < 0) return 0;
    const t = Math.min(1, Math.max(0, (f - 0.5) / MOTION.seamFade + 0.5));
    return t * t * (3 - 2 * t);
  }
  const table = (arr, perLap) => (s) => {
    const laps = Math.floor(s / stepCount);
    const f = (s - laps * stepCount) * PATH_SAMPLES;
    const m = Math.min(Math.floor(f), arr.length - 2);
    return arr[m] + (arr[m + 1] - arr[m]) * (f - m) + laps * perLap;
  };

  // --- the seam (src/seam.js) ------------------------------------------------------
  // The near end of side 2 is hidden behind phantoms of side 0's first blocks (the far start
  // restated nearer along the view), and only side 0's: restated, sides 1 and 2 would shadow
  // their own real neighbours. Which blocks take part is decided here, with every block
  // allowed its full lift range and the view anywhere in the pointer's tilt cone: a far block
  // and a near-end step are a pair if their images along the true axis come within the cone's
  // sideways reach of each other (a line of sight in the cone, over the depth between the two
  // boxes, stays within depth·tan(cone) of a line along the axis). The phantoms are the far
  // blocks in some pair, the seam the near-end steps in some pair: complete at every tilt, and
  // no larger, since every seam step is drawn twice (src/monument.js).
  const spread = Math.tan(TILT_CONE);
  const paired = (p, s) => {
    const depth = Math.abs(dot(sub(s.center, p.center), VIEW_AXIS)) + dot(add(p.half, s.half), VIEW_AXIS);
    return shadowInterval(p.center, p.half.map((h) => h + spread * depth), s.center, s.half) !== null;
  };
  const near = [], far = [];
  blocks.forEach((blk, i) => { if (blk.side === 2 && blk.step >= 0) near.push(i); else if (blk.side === 0) far.push(i); });
  const phantomSources = far.filter((pi) => near.some((si) => paired(liftedBox(blocks[pi]), liftedBox(blocks[si]))));
  const seamBlocks = near.filter((si) => far.some((pi) => paired(liftedBox(blocks[pi]), liftedBox(blocks[si]))));
  // Each side's centre (the mean of its blocks' centres): the arrival twists a side about it.
  const sideCentre = [0, 1, 2].map((k) => {
    const own = blocks.filter((blk) => blk.side === k);
    return [0, 1, 2].map((c) => own.reduce((sum, blk) => sum + blk.center[c], 0) / own.length);
  });

  return {
    blocks, stations, stepCount, stationCount, counts, gap, pivot, radius, rhoMin, rhoMax,
    pathAt, seamBlend, thetaAt: table(theta, turn), rhoAt: table(rho, 0),
    phantomSources, seamBlocks, sideCentre,
  };
}
