// Proofs for the impossible geometry: `node tools/check-geometry.mjs` exits 1 on any failure.
// Pure node: the tribar, the seam solver and the arrival are plain arithmetic.
//
// For every step count from 1 to 40 (works beyond that are a content problem, not a geometry
// one) this checks:
//   - the closure: the open chain's gap is exactly span·(1,1,1), the two ends meet on screen,
//     and at rest at the true angle the seam's phantoms stand exactly where the closed loop
//     would put the far start (offset = |gap|);
//   - the phantom set: at the true angle every cross-seam pair is a phantom pair, under every lift;
//   - the tilt: over the pointer's whole cone (24 directions x 8 magnitudes, the spring's
//     overshoot included) and under several lift states, no phantom enters a near-end block,
//     and wherever a far-start block and a near-end block share pixels the far one is a phantom
//     standing in front, and no third block shares those pixels (the near end is stood behind
//     the far start there in depth); the same along the spring's open and shut, with the phantom offset
//     continuous in time (its steepest change per unit of pose does not grow with finer sampling);
//   - the arrival: no two real blocks ever intersect while the sides drift home (600 instants);
//     from the strike on (when the pointer may tilt) it is assembled at the true view;
//     over the swing's whole range of turns (src/intro.js, every 5 degrees, 130 instants each)
//     no phantom enters the near end, the far start and near end only share pixels in their
//     final order (far in front), and they meet once and stay met through the lock; every dock
//     turns the swing inside that range; the offset is continuous;
//   - picking: lines of sight through the near end, across the cone, pick the block the
//     arrangement shows (the far start standing in front at its phantoms);
//   - lifts: every lift, sink and the arrival's settle leave every pair of real blocks apart;
//   - the door (src/door.js): the light as a door sees it is exactly its dock when docked, moves
//     continuously as the light comes and goes, and lands on the light as drawn for every view of
//     the tilt cone (its depth across the seam resolved by the carry, along the view); the light's
//     way in clears every block, the door's own less its cavity, for every step of every count, the
//     neighbours lifted as far as they can be, the far start or near end standing beside the seam
//     steps; and the light reaching the cavity is exactly zero wherever no ray to it passes the
//     opening (src/probe.js's sweep, against a brute-force line of sight).
// "Intersect" means a common volume deeper than TOL beams; shared faces are allowed.
// The box and image tests here are independent of src/seam.js (corners, hulls, polygon
// clipping and slab chords), so they check the solver rather than restate it.
import { DIM, MOTION, INTRO, LAYOUT, SHADING } from '../src/config.js';
import { buildTribar, toImage, shadowInterval, liftedBox, viewDirection, tiltToward, VIEW_AXIS, IMAGE_RIGHT, IMAGE_UP, TILT_CONE } from '../src/tribar.js';
import { createSeam } from '../src/seam.js';
import { createIntro } from '../src/intro.js';
import { Spring } from '../src/spring.js';
import { newFrame, doorFrame, toDoor, lightFor, createPath, slideProgress, slideOn, LIGHT_RADIUS } from '../src/door.js';
import { probeModel } from '../src/probe.js';

const MAX_STEPS = 40;
const TOL = 1e-6;
const AREA_TOL = 1e-6;    // beams²: images sharing less than this only touch
const failures = [];
const check = (ok, what) => { if (!ok) failures.push(what); };
const stats = { tiltPoses: 0, introPoses: 0, pairsInFront: 0, thirdTests: 0, pushed: 0, maxPush: 0, maxIntroPush: 0, picks: 0, firstMeet: Infinity, lastMeet: 0 };

// ---- small linear algebra (row-major 3x3) -------------------------------------------------
const dot = (a, b) => a[0] * b[0] + a[1] * b[1] + a[2] * b[2];
const cross = (a, b) => [a[1] * b[2] - a[2] * b[1], a[2] * b[0] - a[0] * b[2], a[0] * b[1] - a[1] * b[0]];
const mulV = (m, v) => [0, 1, 2].map((r) => m[3 * r] * v[0] + m[3 * r + 1] * v[1] + m[3 * r + 2] * v[2]);
const column = (m, j) => [m[j], m[3 + j], m[6 + j]];
const IDENTITY = [1, 0, 0, 0, 1, 0, 0, 0, 1];

/** An oriented box: centre, unit axes (columns of a rotation), half extents. */
const obb = (center, axes, half) => ({ center, axes, half });
function corners(b) {
  const out = [];
  for (let c = 0; c < 8; c++) {
    const s = [0, 1, 2].map((k) => ((c >> k) & 1 ? 1 : -1) * b.half[k]);
    out.push([0, 1, 2].map((i) => b.center[i] + b.axes[0][i] * s[0] + b.axes[1][i] * s[1] + b.axes[2][i] * s[2]));
  }
  return out;
}
/** Depth of the common volume of two boxes: the least overlap of their corner projections over
 *  the 15 separating axes (normalised). <= 0 means apart or only touching. */
function penetration(a, b) {
  const ca = corners(a), cb = corners(b);
  const axes = [...a.axes, ...b.axes];
  for (const u of a.axes) for (const v of b.axes) { const n = cross(u, v); if (Math.hypot(...n) > 1e-9) axes.push(n); }
  let least = Infinity;
  for (const n0 of axes) {
    const len = Math.hypot(...n0), n = n0.map((x) => x / len);
    const pa = ca.map((p) => dot(p, n)), pb = cb.map((p) => dot(p, n));
    least = Math.min(least, Math.min(Math.max(...pa), Math.max(...pb)) - Math.max(Math.min(...pa), Math.min(...pb)));
  }
  return least;
}
const sphere = (b) => Math.hypot(...b.half);
const near = (a, b, pad = 0) => Math.hypot(a.center[0] - b.center[0], a.center[1] - b.center[1], a.center[2] - b.center[2]) < sphere(a) + sphere(b) + pad;

// ---- images along a view direction ------------------------------------------------------------
function planeBasis(v) {
  const e1 = cross(v, Math.abs(v[0]) < 0.9 ? [1, 0, 0] : [0, 1, 0]);
  const l1 = Math.hypot(...e1);
  const u = e1.map((x) => x / l1);
  return [u, cross(v, u)];
}
function hull(points) {   // monotone chain, counter-clockwise
  const p = points.slice().sort((a, b) => a[0] - b[0] || a[1] - b[1]);
  const turn = (o, a, b) => (a[0] - o[0]) * (b[1] - o[1]) - (a[1] - o[1]) * (b[0] - o[0]);
  const lower = [], upper = [];
  for (const q of p) { while (lower.length >= 2 && turn(lower[lower.length - 2], lower[lower.length - 1], q) <= 0) lower.pop(); lower.push(q); }
  for (let i = p.length - 1; i >= 0; i--) { const q = p[i]; while (upper.length >= 2 && turn(upper[upper.length - 2], upper[upper.length - 1], q) <= 0) upper.pop(); upper.push(q); }
  return lower.slice(0, -1).concat(upper.slice(0, -1));
}
function clip(subject, clipper) {   // Sutherland-Hodgman, both counter-clockwise and convex
  let out = subject;
  for (let i = 0; i < clipper.length && out.length; i++) {
    const a = clipper[i], b = clipper[(i + 1) % clipper.length];
    const inside = (p) => (b[0] - a[0]) * (p[1] - a[1]) - (b[1] - a[1]) * (p[0] - a[0]) >= 0;
    const meet = (p, q) => {
      const d1 = (b[0] - a[0]) * (p[1] - a[1]) - (b[1] - a[1]) * (p[0] - a[0]);
      const d2 = (b[0] - a[0]) * (q[1] - a[1]) - (b[1] - a[1]) * (q[0] - a[0]);
      const t = d1 / (d1 - d2);
      return [p[0] + (q[0] - p[0]) * t, p[1] + (q[1] - p[1]) * t];
    };
    const input = out; out = [];
    for (let j = 0; j < input.length; j++) {
      const p = input[j], q = input[(j + 1) % input.length];
      if (inside(q)) { if (!inside(p)) out.push(meet(p, q)); out.push(q); } else if (inside(p)) out.push(meet(p, q));
    }
  }
  return out;
}
const area = (poly) => Math.abs(poly.reduce((s, p, i) => { const q = poly[(i + 1) % poly.length]; return s + p[0] * q[1] - q[0] * p[1]; }, 0)) / 2;
/** Chord of the line x = o + s·v through box b: [s0, s1] or null (slab test in the box's frame). */
function chord(b, o, v) {
  let s0 = -Infinity, s1 = Infinity;
  for (let k = 0; k < 3; k++) {
    const ax = b.axes[k], oc = dot([o[0] - b.center[0], o[1] - b.center[1], o[2] - b.center[2]], ax), dv = dot(v, ax);
    if (Math.abs(dv) < 1e-12) { if (Math.abs(oc) > b.half[k]) return null; continue; }
    let lo = (-b.half[k] - oc) / dv, hi = (b.half[k] - oc) / dv;
    if (lo > hi) [lo, hi] = [hi, lo];
    s0 = Math.max(s0, lo); s1 = Math.min(s1, hi);
  }
  return s0 <= s1 ? [s0, s1] : null;
}
/**
 * Do `front` and `back` share pixels along v, and if so is `front` nearer the eye? Returns
 * null when the images only touch, else { inFront }. The order is read along the line of sight
 * through the centre of the shared region.
 */
function order(front, back, v) {
  const [e1, e2] = planeBasis(v);
  const img = (b) => hull(corners(b).map((p) => [dot(p, e1), dot(p, e2)]));
  const shared = clip(img(front), img(back));
  if (shared.length < 3 || area(shared) < AREA_TOL) return null;
  const m = shared.reduce((s, p) => [s[0] + p[0] / shared.length, s[1] + p[1] / shared.length], [0, 0]);
  const o = [0, 1, 2].map((i) => e1[i] * m[0] + e2[i] * m[1]);
  const f = chord(front, o, v), k = chord(back, o, v);
  if (!f || !k) return null;
  return { inFront: f[0] >= k[1] - 1e-6, shared, img };
}

// ---- the world as boxes ---------------------------------------------------------------------------
const AXES_ID = [[1, 0, 0], [0, 1, 0], [0, 0, 1]];
/** Block i of tribar t, lifted, in monument space under per-side transforms (null: assembled). */
function blockBox(t, i, lift, sides) {
  const b = t.blocks[i];
  const c = b.center.slice(); c[b.tread] += lift[i];
  if (!sides) return obb(c, AXES_ID, b.half);
  const k = b.side, R = sides.sideRot[k], piv = t.sideCentre[k], off = sides.sideOff[k];
  const rc = mulV(R, [c[0] - piv[0], c[1] - piv[1], c[2] - piv[2]]);
  return obb([0, 1, 2].map((r) => rc[r] + piv[r] + off[r]), [column(R, 0), column(R, 1), column(R, 2)], b.half);
}
const moved = (box, v, s) => obb(box.center.map((x, i) => x + v[i] * s), box.axes, box.half);

/**
 * One pose: the seam solved for view v, then (a) no phantom inside a near-end block, (b) every
 * side-0 block that shares pixels with a near-end step is a phantom standing in front of it.
 */
function checkPose(t, seam, tag, v, lift, sides) {
  let shared = false;
  seam.solve(v, sides, lift);
  const phantomSet = new Set(t.phantomSources), seamSet = new Set(t.seamBlocks);
  const boxes = t.blocks.map((_, i) => blockBox(t, i, lift, sides));
  for (const pi of t.phantomSources) {
    const ph = moved(boxes[pi], v, seam.offset);
    for (const si of t.seamBlocks) {
      if (!near(ph, boxes[si])) continue;
      const depth = penetration(ph, boxes[si]);
      check(depth <= TOL, `${tag}: phantom ${pi} enters near-end block ${si} by ${depth.toExponential(2)} (offset ${seam.offset.toFixed(4)})`);
    }
  }
  t.blocks.forEach((p, pi) => {
    if (p.side !== 0) return;
    t.blocks.forEach((s, si) => {
      if (s.side !== 2 || s.step < 0) return;   // the near end: side 2's steps (its corner cube is a real joint, far away)
      // Cheap screen-space prefilter: the two centres' images within the sum of the radii.
      const d = [0, 1, 2].map((k) => boxes[si].center[k] - boxes[pi].center[k]);
      const along = dot(d, v);
      if (Math.hypot(d[0] - v[0] * along, d[1] - v[1] * along, d[2] - v[2] * along) > sphere(boxes[pi]) + sphere(boxes[si])) return;
      const o = order(moved(boxes[pi], v, seam.offset), boxes[si], v);
      if (!o) return;
      check(phantomSet.has(pi) && seamSet.has(si), `${tag}: far block ${pi} and near-end step ${si} share pixels but are not a phantom / seam pair`);
      check(o.inFront, `${tag}: phantom ${pi} is behind near block ${si} where they share pixels`);
      stats.pairsInFront++;
      shared = true;
      // Where they share pixels the shader stands the near end behind the far start in depth
      // (src/monument.js 'behind'): sound only if no third block (one that is neither a phantom
      // nor a seam step, so is drawn by the plain rule) shares those pixels too.
      t.blocks.forEach((x, xi) => {
        if (phantomSet.has(xi) || seamSet.has(xi)) return;
        const dx = [0, 1, 2].map((k) => boxes[xi].center[k] - boxes[si].center[k]);
        const ax = dot(dx, v);
        if (Math.hypot(dx[0] - v[0] * ax, dx[1] - v[1] * ax, dx[2] - v[2] * ax) > sphere(boxes[xi]) + sphere(boxes[si])) return;
        const third = clip(o.shared, o.img(boxes[xi]));
        stats.thirdTests++;
        check(third.length < 3 || area(third) < AREA_TOL, `${tag}: block ${xi} (side ${x.side}) shares the pixels where near-end step ${si} stands behind phantom ${pi}`);
      });
    });
  });
  return shared;
}

/** Every pair of real blocks apart (shared faces allowed). */
function checkSolid(t, tag, lift, sides) {
  const boxes = t.blocks.map((_, i) => blockBox(t, i, lift, sides));
  for (let i = 0; i < boxes.length; i++) for (let j = i + 1; j < boxes.length; j++) {
    if (!near(boxes[i], boxes[j])) continue;
    const depth = penetration(boxes[i], boxes[j]);
    check(depth <= TOL, `${tag}: blocks ${i} and ${j} intersect by ${depth.toExponential(2)}`);
  }
}

// Deterministic pseudo-random lifts in each block's real range: steps sink or rise, corner cubes
// only ever rise (the arrival's settle) and never sink.
let seed = 7;
const random = () => ((seed = (seed * 16807) % 2147483647) / 2147483647);
function liftStates(t) {
  const range = (b, u) => (b.step >= 0 ? -DIM.sinkReach + u * (DIM.liftReach + DIM.sinkReach) : u * INTRO.settleLift);
  const n = t.blocks.length;
  const states = [
    new Float32Array(n),
    Float32Array.from(t.blocks, (b) => range(b, 1)),
    Float32Array.from(t.blocks, (b) => range(b, 0)),
    Float32Array.from(t.blocks, (b) => range(b, random())),
    Float32Array.from(t.blocks, (b) => range(b, random())),
  ];
  // The presented step on the seam, lifted to meet the light, everything else at rest.
  const sel = new Float32Array(n); sel[t.seamBlocks[t.seamBlocks.length - 1]] = MOTION.selectLift; states.push(sel);
  return states;
}

/** A view in the tilt cone: angle `mag` from the true axis, toward azimuth `az` in the picture. */
const coneView = (mag, az) => [0, 1, 2].map((i) => Math.cos(mag) * VIEW_AXIS[i] + Math.sin(mag) * (Math.cos(az) * IMAGE_RIGHT[i] + Math.sin(az) * IMAGE_UP[i]));
/**
 * Continuity of the phantom offset along a motion: `at(time)` gives [offset, pose], the pose
 * being everything the offset is a function of (view, side transforms, lifts). The measure is
 * the steepest change of offset per unit change of pose between neighbouring samples. A
 * continuous offset keeps that ratio bounded however finely it is sampled; a jump of size J
 * reads as J over an ever smaller pose step. So: scan the motion, then zoom into the steepest
 * step twice, 64 times finer each time, and require the ratio to have stopped growing between
 * the two zooms (a jump would multiply it by 64 again). (Per
 * unit of TIME would not do: the spring is fastest exactly where it swings through the true
 * angle, which is where the offset has its V-shaped kink, the push changing sides.)
 * @returns [ratio at the first zoom, ratio at the second]
 */
function steepness(at, from, to, samples) {
  const scan = (a, b, n) => {
    let prev = at(a), best = 0, where = a;
    for (let i = 1; i <= n; i++) {
      const time = a + ((b - a) * i) / n, cur = at(time);
      let dp = 0;
      for (let k = 0; k < cur[1].length; k++) dp = Math.max(dp, Math.abs(cur[1][k] - prev[1][k]));
      if (dp > 0) { const r = Math.abs(cur[0] - prev[0]) / dp; if (r > best) { best = r; where = time; } } else check(cur[0] === prev[0], 'the phantom offset changed with nothing moving');
      prev = cur;
    }
    return { best, where, step: (b - a) / n };
  };
  let level = scan(from, to, samples);
  const ratios = [];
  for (let zoom = 0; zoom < 2; zoom++) {
    level = scan(Math.max(from, level.where - 2 * level.step), Math.min(to, level.where + level.step), 192);
    ratios.push(level.best);
  }
  return ratios;
}
const continuous = ([coarse, fine]) => fine <= 1.5 * coarse + 1e-6;

for (let n = 1; n <= MAX_STEPS; n++) {
  const t = buildTribar(n);
  const { blocks, gap, phantomSources, seamBlocks } = t;
  const seam = createSeam(t);
  const tag = `n=${n}`;
  const reach = Math.hypot(...gap);

  // ---- closure ----------------------------------------------------------------------------
  // The chain must miss itself by exactly span along the view axis, in every component.
  check(gap.every((g) => Math.abs(g - DIM.span) < 1e-9), `${tag}: gap ${gap} is not span·(1,1,1)`);
  const c0 = blocks[0].center, a = toImage(c0), b = toImage(c0.map((v, i) => v + gap[i]));
  check(Math.hypot(a[0] - b[0], a[1] - b[1]) < 1e-9, `${tag}: the seam does not close on screen`);
  // At rest the phantoms are the closed loop's far start: offset |gap| along the true axis.
  const zero = new Float32Array(blocks.length);
  seam.solve(VIEW_AXIS, null, zero);
  check(Math.abs(seam.offset - reach) < 1e-9 && Math.abs(seam.restOffset - reach) < 1e-9, `${tag}: at rest the phantom offset is ${seam.offset}, not |gap| ${reach}`);
  check([0, 1, 2].every((k) => Math.abs(seam.origin[k] + gap[k]) < 1e-9 && Math.abs(seam.carry[k] - gap[k]) < 1e-9), `${tag}: at rest the seam transform is not the gap`);

  // ---- the phantom set at the true angle ------------------------------------------------------
  // Every side-0 block whose restated image overlaps a seam step, under any lift of either, must
  // be a phantom; and the phantom must be the one in front (hi >= 0), or the wrong block
  // would be drawn in front. Tested at the ends of the lift range AND over the whole range swept.
  check(seamBlocks.every((i) => blocks[i].side === 2 && blocks[i].step >= 0), `${tag}: seam list holds a block that is not a near-side step`);
  check(phantomSources.every((i) => blocks[i].side === 0), `${tag}: a phantom is not on side 0`);
  check(phantomSources.length >= 1, `${tag}: no phantoms (the corner cube always shadows the last step)`);
  const lifts = [-DIM.sinkReach, 0, DIM.liftReach];
  blocks.forEach((p, i) => {
    if (p.side !== 0) return;
    for (const si of seamBlocks) {
      const s = blocks[si];
      for (const lp of lifts) for (const ls of lifts) {
        const pc = p.center.map((v, k) => v + gap[k] + (k === p.tread ? lp : 0));
        const sc = s.center.map((v, k) => v + (k === s.tread ? ls : 0));
        const span = shadowInterval(pc, p.half, sc, s.half);
        if (!span) continue;
        check(span[1] >= 0, `${tag}: side0 step ${p.step} sits behind side2 step ${s.step} (lifts ${lp},${ls}); the far start would be hidden`);
        check(phantomSources.includes(i), `${tag}: side0 step ${p.step} overlaps side2 step ${s.step} on screen (lifts ${lp},${ls}) but is not a phantom`);
      }
      const pb = liftedBox(p, gap), sb = liftedBox(s);
      const swept = shadowInterval(pb.center, pb.half, sb.center, sb.half);
      if (!swept) continue;
      check(swept[1] >= 0, `${tag}: side0 step ${p.step} sits behind side2 step ${s.step} somewhere in the swept lift range`);
      check(phantomSources.includes(i), `${tag}: side0 step ${p.step} overlaps side2 step ${s.step} somewhere in the swept lift range but is not a phantom`);
    }
  });
  // The closed configuration abuts and never overlaps: restated phantoms and seam steps only
  // touch, so the near end loses nothing but what the far start really hides.
  phantomSources.forEach((i) => {
    for (const si of seamBlocks) {
      const p = blocks[i], s = blocks[si];
      const overlap = [0, 1, 2].every((k) => Math.abs(p.center[k] + gap[k] - s.center[k]) < p.half[k] + s.half[k] - 1e-9);
      check(!overlap, `${tag}: phantom ${i} interpenetrates seam block ${si} at rest`);
    }
  });

  // ---- lifts: real blocks never pass through each other -------------------------------------------
  const states = liftStates(t);
  states.forEach((lift, k) => checkSolid(t, `${tag} lifts#${k}`, lift, null));

  // ---- the tilt cone ------------------------------------------------------------------------------
  // 24 directions x 8 magnitudes up to the cone (both tilt axes at their limit, plus the spring's
  // overshoot), under every lift state.
  for (let m = 1; m <= 8; m++) {
    for (let d = 0; d < 24; d++) {
      const v = coneView((TILT_CONE * m) / 8, (2 * Math.PI * d) / 24);
      states.forEach((lift, k) => {
        checkPose(t, seam, `${tag} tilt ${((TILT_CONE * m) / 8).toFixed(3)} rad az ${d * 15}° lifts#${k}`, v, lift, null);
        stats.tiltPoses++;
        const push = seam.offset - dot(gap, v);
        if (push > 1e-9) { stats.pushed++; stats.maxPush = Math.max(stats.maxPush, push); }
      });
    }
  }
  // Picking (src/seam.js pick, which src/stage.js uses) against the arrangement it stands for:
  // lines of sight through random points of the near end, along views across the cone, must
  // meet first the same block as a plain raycast of solid boxes in which the far start really
  // stands at its phantoms, in front. (Index of the far block = index of its phantom.)
  for (let m = 0; m <= 8; m += 2) {
    for (let d = 0; d < 24; d += 2) {
      const v = coneView((TILT_CONE * m) / 8, (2 * Math.PI * d) / 24);
      for (const lift of [states[0], states[5], states[3]]) {
        seam.solve(v, null, lift);
        const boxes = blocks.map((_, i) => blockBox(t, i, lift, null));
        const arranged = boxes.map((b, i) => (phantomSources.includes(i) ? moved(b, v, seam.offset) : b));
        for (const si of seamBlocks) {
          for (let r = 0; r < 12; r++) {
            const b = boxes[si];
            const x = b.center.map((c, k) => c + (random() * 2 - 1) * b.half[k]);
            const o = x.map((c, k) => c + v[k] * 40), dir = v.map((c) => -c);
            const shown = seam.pick(o[0], o[1], o[2], dir[0], dir[1], dir[2], lift, seam.offset);
            // The arrangement, raycast plainly: nearest entry wins; lines grazing an edge (two
            // entries within 1e-6) are ties either answer may take.
            const hits = arranged.map((bx, i) => [chord(bx, o, dir), i]).filter(([c]) => c && c[1] > c[0] + 1e-9 && c[1] > 0).map(([c, i]) => [Math.max(c[0], 0), i]).sort((p, q) => p[0] - q[0]);
            if (hits.length > 1 && hits[1][0] - hits[0][0] < 1e-6) continue;
            stats.picks++;
            check(hits.length && shown === hits[0][1], `${tag}: pick through near block ${si} at tilt ${((TILT_CONE * m) / 8).toFixed(3)} az ${d * 15}° returns ${shown}, the arrangement shows ${hits.length ? hits[0][1] : -1}`);
          }
        }
      }
    }
  }

  // The spring: opened toward a corner of the tilt square, then let go and snapped shut (the
  // overshoot carries it past zero), checked pose by pose at 240 Hz, and the phantom offset
  // continuous along it.
  for (const az of [0, 1, 2, 3, 4, 5, 6, 7].map((k) => (k * Math.PI) / 4 + 0.3)) {
    const phi = LAYOUT.wide.restAngle - t.thetaAt(0);
    const corner = [Math.cos(az), Math.sin(az)].map((c) => Math.max(-MOTION.tiltMax, Math.min(MOTION.tiltMax, c * MOTION.tiltMax * 1.5)));
    // The spring in closed form from rest: open for 0.6 s, then let go at the stiffer rate.
    const pose = (time) => {
      const yaw = new Spring(0, MOTION.tiltOmega, MOTION.tiltZeta), pitch = new Spring(0, MOTION.tiltOmega, MOTION.tiltZeta);
      yaw.target = corner[0]; pitch.target = corner[1];
      yaw.step(Math.min(time, 0.6)); pitch.step(Math.min(time, 0.6));
      if (time > 0.6) { yaw.target = pitch.target = 0; yaw.omega = pitch.omega = MOTION.tiltLockOmega; yaw.step(time - 0.6); pitch.step(time - 0.6); }
      return viewDirection(phi, yaw.value, pitch.value);
    };
    for (let i = 0; i <= 384; i++) checkPose(t, seam, `${tag} spring az ${az.toFixed(2)} at ${(i / 240).toFixed(3)} s`, pose(i / 240), states[5], null);
    const ratios = steepness((time) => { const v = pose(time); seam.solve(v, null, states[5]); return [seam.offset, v]; }, 0, 1.6, 1600);
    check(continuous(ratios), `${tag}: phantom offset jumps along the tilt spring (steepest ${ratios[0].toFixed(3)} beams per unit of pose zoomed in, ${ratios[1].toFixed(3)} zoomed in 64 times further)`);
  }

  // ---- the arrival ----------------------------------------------------------------------------------
  // The swing is fixed to the monument and turned per dock within INTRO.turnRange
  // (src/intro.js), so the whole range is swept, every 5 degrees, 130 instants each: no
  // phantom enters the near end, the far start / near end only share pixels in their final
  // order, and they meet once and stay met through the lock. No two real blocks intersect at
  // 600 instants (the sides' paths do not depend on the swing). Every dock (each station, both
  // layouts) gets a turn inside the range, along the screen's long side within 10 degrees, and
  // the tilt the frame makes of it shows exactly the swing's line of sight. The offset is
  // continuous over the timeline, and the arrival ends closed.
  const intro = createIntro(t);
  for (let i = 0; i <= 600; i++) { const time = (intro.duration * i) / 600, s = intro.sample(time); checkSolid(t, `${tag} arrival t=${time.toFixed(3)} s`, s.lift, s); }
  const [turnMin, turnMax] = INTRO.turnRange;
  const turns = [];
  for (let k = 0; turnMin + (k * Math.PI) / 36 < turnMax; k++) turns.push(turnMin + (k * Math.PI) / 36);
  turns.push(turnMax);
  for (const turn of turns) {
    intro.turn = turn;
    let met = -1, parted = -1;
    for (let i = 0; i <= 130; i++) {
      const time = (intro.duration * i) / 130;
      const s = intro.sample(time);
      const tg = `${tag} arrival t=${time.toFixed(3)} s turned ${((turn * 180) / Math.PI).toFixed(0)}°`;
      // The seam's ends meet once: from the first instant they share pixels to the end.
      if (checkPose(t, seam, tg, s.view, s.lift, s)) { if (met < 0) met = time; } else if (met >= 0 && parted < 0) parted = time;
      stats.introPoses++;
      stats.maxIntroPush = Math.max(stats.maxIntroPush, seam.offset - dot(gap, s.view));
    }
    check(met >= 0 && parted < 0, `${tag} turned ${((turn * 180) / Math.PI).toFixed(0)}°: during the arrival the seam's ends ${met < 0 ? 'never meet' : `meet at ${met.toFixed(3)} s, then part at ${parted.toFixed(3)} s`}`);
    stats.firstMeet = Math.min(stats.firstMeet, met); stats.lastMeet = Math.max(stats.lastMeet, met);
    if (turn === turnMin || turn === turnMax || turn === turns[18]) {
      const ratios = steepness((time) => {
        const s = intro.sample(time);
        seam.solve(s.view, s, s.lift);
        return [seam.offset, [...s.view, ...s.sideOff.flat(), ...s.sideRot.flatMap((r) => [...r]), ...s.lift]];
      }, 0, intro.duration, 1600);
      check(continuous(ratios), `${tag}: phantom offset jumps during the arrival (steepest ${ratios[0].toFixed(3)} beams per unit of pose zoomed in, ${ratios[1].toFixed(3)} zoomed in 64 times further)`);
    }
    const end = intro.sample(intro.duration);
    seam.solve(end.view, end, end.lift);
    check(Math.abs(seam.offset - reach) < 1e-9, `${tag}: the arrival does not end with the phantoms closed (${seam.offset})`);
  }
  // The pointer tilts the picture only from the strike on (src/intents.js ignores it while the
  // arrival is under way): by then every side is home and the swing has closed onto the true
  // axis, so what the pointer adds is a tilt of the assembled monument, the cone proven above
  // (its lift states span the settle that is still landing).
  for (const turn of [turnMin, 0, turnMax]) {
    intro.turn = turn;
    for (let i = 0; i <= 64; i++) {
      const time = INTRO.ignite + ((intro.duration - INTRO.ignite) * i) / 64, s = intro.sample(time);
      const home = s.sideOff.every((o) => o.every((x) => x === 0)) && s.sideRot.every((r) => r.every((x, k) => Math.abs(x - IDENTITY[k]) < 1e-15));
      const trueView = Math.hypot(s.view[0] - VIEW_AXIS[0], s.view[1] - VIEW_AXIS[1], s.view[2] - VIEW_AXIS[2]) < 1e-12;
      check(home && trueView, `${tag}: at ${time.toFixed(3)} s, after the strike, the arrival is ${home ? '' : 'not assembled'}${home || trueView ? '' : ' and '}${trueView ? '' : 'off the true view'}: the pointer's tilt would add to an unproven pose`);
    }
  }
  for (let station = 0; station < t.stepCount; station++) {
    for (const [rest, portrait] of [[LAYOUT.wide.restAngle, false], [LAYOUT.tall.restAngle, true]]) {
      const turn = intro.dock(station, rest, portrait);
      check(turn >= turnMin - 1e-12 && turn <= turnMax + 1e-12, `${tag}: station ${station} ${portrait ? 'tall' : 'wide'} turns the arrival by ${turn}, outside the proven range`);
      // On screen the authored swing appears turned by (turn - roll from the authored dock): a
      // multiple of a half turn (wide) or a quarter turn off it (tall), within 10 degrees.
      const off = turn - (rest - t.thetaAt(station) - (LAYOUT.wide.restAngle - t.thetaAt(0))) - (portrait ? Math.PI / 2 : 0);
      const miss = Math.abs(off - Math.PI * Math.round(off / Math.PI));
      check(miss <= (10 * Math.PI) / 180 + 1e-9, `${tag}: station ${station} ${portrait ? 'tall' : 'wide'}: the arrival's tear is ${((miss * 180) / Math.PI).toFixed(1)}° off the screen's long side`);
      const s = intro.sample(0.3), phi = rest - t.thetaAt(station) + s.roll;
      const [yaw, pitch] = tiltToward(s.view, phi);
      const v = viewDirection(phi, yaw, pitch);
      check(Math.hypot(v[0] - s.view[0], v[1] - s.view[1], v[2] - s.view[2]) < 1e-9, `${tag}: the frame's tilt does not show the arrival's line of sight at station ${station}`);
    }
  }

  // ---- the light's path -------------------------------------------------------------------------------
  // The roll table must be monotonic and the light's path continuous on screen.
  let prev = t.thetaAt(0), mono = true;
  for (let s = 0.01; s <= t.stepCount + 1e-9; s += 0.01) { const th = t.thetaAt(s); if (th < prev - 1e-6) mono = false; prev = th; }
  check(mono, `${tag}: theta is not monotonic`);
  check(Math.abs(Math.abs(t.thetaAt(t.stepCount) - t.thetaAt(0)) - 2 * Math.PI) < 1e-6, `${tag}: one lap does not turn 2π`);
  let jump = 0, pp = toImage(t.pathAt(0).slice());
  for (let s = 0.005; s <= t.stepCount + 0.5; s += 0.005) { const q = toImage(t.pathAt(s).slice()); jump = Math.max(jump, Math.hypot(q[0] - pp[0], q[1] - pp[1])); pp = q; }
  check(jump < 0.06, `${tag}: on-screen path jumps ${jump.toFixed(4)} per 0.005 station`);

  // In the seam segment the two ends differ by exactly the gap, and the cross-fade is a
  // monotone 0 -> 1 ramp confined to that segment.
  const s0 = t.stepCount - 1;
  check(t.seamBlend(s0) === 0 && t.seamBlend(s0 + 0.999) === 1 && t.seamBlend(s0 - 0.5) === 0, `${tag}: seam blend does not span 0..1 inside the seam segment`);
  let last = 0, blendMono = true;
  for (let f = 0; f <= 1; f += 0.01) { const w = t.seamBlend(s0 + f); if (w < last - 1e-9) blendMono = false; last = w; }
  check(blendMono, `${tag}: seam blend is not monotone`);
  const nearEnd = t.pathAt(s0 + 0.5, [0, 0, 0], 0), farEnd = t.pathAt(s0 + 0.5, [0, 0, 0], 1);
  check([0, 1, 2].every((k) => Math.abs(nearEnd[k] - farEnd[k] - gap[k]) < 1e-9), `${tag}: near and far light positions do not differ by the gap`);
}

// The worst stacks: a selection landing on a step the idle life has lifted (the beat lets it
// down at once, but the two overlap while it falls), or a hovered step under the passing
// light while the idle life lets it down; the arrival's settle, which hangs every block
// above its bearing with nothing else stacked (input is only taken once the seam shuts, and
// the settle is gone before the first lift could land: no stack); and the idle sink is the
// only way below the bearing.
check(DIM.liftReach >= Math.max(MOTION.selectLift, MOTION.hoverLift + MOTION.passLift) + MOTION.liftHeight, 'liftReach is smaller than the lifts can stack to');
check(DIM.liftReach >= INTRO.settleLift, 'liftReach is smaller than the arrival settle');
// Every stop sinks by stepSink of its travel; a step let down by the idle life while its own
// lift drops can sink by both at once.
check(DIM.sinkReach >= MOTION.stepSink * (Math.max(MOTION.selectLift, MOTION.hoverLift + MOTION.passLift) + MOTION.liftHeight), 'sinkReach is smaller than the sinks can stack to');

// ---- the door ---------------------------------------------------------------------------------------
const doorStats = { stations: 0, pathPoints: 0, minClear: Infinity, clearAt: null, depths: new Set(), transportPairs: 0, porches: 0 };
/** Distance from point q to an axis-aligned box (centre c, half h); 0 inside. */
const boxDistance = (q, c, h) => Math.hypot(...[0, 1, 2].map((i) => Math.max(Math.abs(q[i] - c[i]) - h[i], 0)));
for (let n = 1; n <= MAX_STEPS; n++) {
  const t = buildTribar(n), N = t.stepCount, seam = createSeam(t);
  const rest = new Float64Array(t.blocks.length);
  // (a) the light as a door sees it
  const views = [VIEW_AXIS, coneView(TILT_CONE, 0.3), coneView(TILT_CONE * 0.6, 2.1), coneView(TILT_CONE, 4.4)];
  for (let j = 0; j < N; j++) {
    const a = t.stations[j].anchor, p = lightFor(t, j, j, t.gap);
    check(Math.hypot(p[0] - a[0], p[1] - a[1], p[2] - a[2]) < 1e-12, `door n=${n} j=${j}: the docked light is not at its dock`);
    const reach = Math.min(1.5, N / 2 - 0.05);
    const jumps = [400, 800].map((steps) => {
      let prev = null, most = 0;
      for (let k = -steps; k <= steps; k++) {
        const q = lightFor(t, j, j + (k / steps) * reach, t.gap);
        if (prev) most = Math.max(most, Math.hypot(q[0] - prev[0], q[1] - prev[1], q[2] - prev[2]));
        prev = q;
      }
      return most;
    });
    check(jumps[1] <= 0.6 * jumps[0], `door n=${n} j=${j}: the light the door sees jumps (${jumps[0].toFixed(4)} then ${jumps[1].toFixed(4)})`);
    for (const v of views) {
      seam.solve(v, null, rest);
      for (let k = -40; k <= 40; k++) {
        const sAt = j + (k / 40) * reach, b = t.seamBlend(sAt);
        const c0 = t.pathAt(sAt, [0, 0, 0], 0), c1 = t.pathAt(sAt, [0, 0, 0], 1), q = lightFor(t, j, sAt, seam.carry);
        const e = [0, 1, 2].map((i) => q[i] - ((1 - b) * c0[i] + b * c1[i])), along = dot(e, v);
        check(Math.hypot(e[0] - along * v[0], e[1] - along * v[1], e[2] - along * v[2]) < 1e-9, `door n=${n} j=${j}: the light the door sees is off the drawn light at s=${sAt.toFixed(3)}`);
      }
    }
  }
  // (b) the way in. Every other step stands at one lift of its range at a time (a lift moves a block
  // along its tread, so each block's distance is checked over its range); the seam steps see the
  // far start and the near end where the closed loop stands them, a gap along the true view (the
  // light leaves only once the seam is shut).
  const others = [-DIM.sinkReach, 0, MOTION.liftHeight / 3, (2 * MOTION.liftHeight) / 3, MOTION.liftHeight];
  const path = createPath(), q = [0, 0, 0], f = newFrame(), L = [0, 0, 0];
  for (let j = 0; j < N; j++) {
    const door = t.stations[j].block;
    for (const own of [MOTION.selectLift * (1 - MOTION.stepSink), MOTION.selectLift]) {
      doorFrame(t.blocks[door], own, f);
      doorStats.depths.add(+f.depth.toFixed(6));
      const H = SHADING.doorHeight / 2, W = SHADING.doorWidth / 2;
      // The door's block less its cavity, as five boxes in the door frame: behind, above, below, either side.
      const back = -f.run, top = SHADING.doorDrop, bottom = SHADING.doorDrop - DIM.beam;
      const solid = [
        [[(back - f.depth) / 2, (top + bottom) / 2, 0], [(-f.depth - back) / 2, (top - bottom) / 2, DIM.beam / 2]],
        [[-f.depth / 2, (top + H) / 2, 0], [f.depth / 2, (top - H) / 2, DIM.beam / 2]],
        [[-f.depth / 2, (bottom - H) / 2, 0], [f.depth / 2, (-H - bottom) / 2, DIM.beam / 2]],
        [[-f.depth / 2, 0, (-DIM.beam / 2 - W) / 2], [f.depth / 2, H, (DIM.beam / 2 - W) / 2]],
        [[-f.depth / 2, 0, (DIM.beam / 2 + W) / 2], [f.depth / 2, H, (DIM.beam / 2 - W) / 2]],
      ];
      toDoor(f, lightFor(t, j, j, t.gap), L);
      path.plan(L, f.depth);
      for (const lift of others) {
        const boxes = [];
        t.blocks.forEach((b, i) => {
          if (i === door) return;
          const c = b.center.slice(); if (b.step >= 0) c[b.tread] += lift;
          const shifts = [[0, 0, 0]];
          if (b.side === 0) shifts.push(t.gap); if (b.side === 2) shifts.push(t.gap.map((g) => -g));
          for (const sh of shifts) boxes.push([toDoor(f, c.map((x, k) => x + sh[k])), [b.half[f.x], b.half[f.y], b.half[f.z]]]);
        });
        for (let k = 0; k <= 600; k++) {
          path.at(slideProgress(k / 600, path.porch), q);
          doorStats.pathPoints++;
          let clear = Infinity;
          for (const [c, h] of solid) clear = Math.min(clear, boxDistance(q, c, h));
          for (const [c, h] of boxes) clear = Math.min(clear, boxDistance(q, c, h));
          if (clear < doorStats.minClear) { doorStats.minClear = clear; doorStats.clearAt = [n, j, k / 600]; }
          if (clear < LIGHT_RADIUS) { failures.push(`door n=${n} j=${j}: the light passes through stone on its way in (clearance ${clear.toFixed(4)} at ${(k / 600).toFixed(3)})`); break; }
        }
      }
      path.at(1, q);
      check(q[0] <= -LIGHT_RADIUS && q[0] >= -f.depth + LIGHT_RADIUS && Math.abs(q[1]) <= H - LIGHT_RADIUS, `door n=${n} j=${j}: the light does not come to rest wholly inside the cavity`);
      // Nothing stands in front of the opening: the porch's volume (the opening carried out to the porch
      // and the light's radius beyond) is clear of every block at every lift it can take while the door is
      // open. The step in front of a presented one is spared by the idle lift (src/idle.js), so it rises
      // only by the pointer's hover and the light's pass; any other step by up to the idle lift. (The
      // light transport and src/probe.js take the riser as the opening's only occluder.)
      const front = (door + 1) % t.blocks.length;
      const porchC = [(SHADING.doorPorch + LIGHT_RADIUS) / 2, 0, 0], porchH = [(SHADING.doorPorch + LIGHT_RADIUS) / 2, H, W];
      t.blocks.forEach((b, i) => {
        if (i === door) return;
        const top = b.step < 0 ? 0 : i === front ? MOTION.hoverLift + MOTION.passLift : MOTION.liftHeight;
        for (const lift of [-DIM.sinkReach, 0, top]) {
          const c = b.center.slice(); c[b.tread] += lift;
          const shifts = [[0, 0, 0]];
          if (b.side === 0) shifts.push(t.gap); if (b.side === 2) shifts.push(t.gap.map((g) => -g));
          for (const sh of shifts) {
            const bc = toDoor(f, c.map((x, k) => x + sh[k])), bh = [b.half[f.x], b.half[f.y], b.half[f.z]];
            const overlap = [0, 1, 2].every((k) => Math.abs(bc[k] - porchC[k]) < bh[k] + porchH[k] - 1e-9);
            check(!overlap, `door n=${n} j=${j}: block ${i} lifted ${lift.toFixed(3)} stands in front of the opening`);
          }
        }
      });
      doorStats.porches++;
      // The slide arrives, and never turns back along its way: from the dock, and from anywhere the
      // light may have leaned out to (a share of the same way, short of the porch: so the clearance
      // above, which samples the whole way, covers the lean and every slide begun from it).
      const lean = path.alongTo(SHADING.doorLean);
      path.at(lean, q);
      check(lean > 0 && lean < path.porch && Math.abs(q[0] - SHADING.doorLean) < 1e-6, `door n=${n} j=${j}: the lean is not on the way in short of the porch (${lean}, x ${q[0]})`);
      for (const from of [0, lean / 3, (2 * lean) / 3, lean]) {
        let last = -1;
        for (let k = 0; k <= 400; k++) { const u = slideOn(k / 400, path.porch, from); check(u >= last - 1e-12 && u >= from - 1e-12, `door n=${n} j=${j}: the slide from ${from.toFixed(3)} turns back`); last = u; }
        check(Math.abs(slideOn(0, path.porch, from) - from) < 1e-12 && Math.abs(slideOn(1, path.porch, from) - 1) < 1e-12, `door n=${n} j=${j}: the slide from ${from.toFixed(3)} does not start there or does not arrive`);
      }
      check(Math.abs(slideProgress(1, path.porch) - 1) < 1e-12, `door n=${n} j=${j}: the slide does not arrive`);
    }
    doorStats.stations++;
  }
}
// (c) the transport, at every depth a cavity takes
for (const depth of doorStats.depths) {
  for (const open of [1, 0.6]) {
    const r = probeModel(depth, (SHADING.doorHeight / 2) * open);
    doorStats.transportPairs += r.pairs;
    check(r.violations.length === 0, `door transport depth=${depth} open=${open}: ${r.violations.length} violations, e.g. ${JSON.stringify(r.violations[0])}`);
    check(r.blindPairs > 0 && r.sightedPairs > 0, `door transport depth=${depth}: the sweep tested nothing`);
  }
}

// A short report for the counts the shots use.
for (const n of [3, 4, 10, 24, 40]) {
  const t = buildTribar(n);
  console.log(`n=${n} counts=${t.counts} blocks=${t.blocks.length} phantoms=[${t.phantomSources}] seam=${t.seamBlocks.length} radius=${t.radius.toFixed(3)} rho=[${t.rhoMin.toFixed(2)},${t.rhoMax.toFixed(2)}]`);
}
console.log(`door: ${doorStats.stations} steps, the light's way in clear of stone at ${doorStats.pathPoints} points (least clearance ${doorStats.minClear.toFixed(4)} beams, light radius ${LIGHT_RADIUS}, at n=${doorStats.clearAt?.[0]}), leaning and sliding on from the lean never turning back, ${doorStats.porches} porches clear of stone at every lift, ${doorStats.depths.size} cavity depths, ${doorStats.transportPairs} point-light pairs zero exactly without line of sight`);
console.log(`tilt: ${stats.tiltPoses} poses (cone ${TILT_CONE.toFixed(4)} rad), ${stats.pushed} needed a push toward the eye (at most ${stats.maxPush.toFixed(3)} beams); arrival: ${stats.introPoses} poses (push at most ${stats.maxIntroPush.toFixed(3)}; the seam's ends meet once, between ${stats.firstMeet.toFixed(2)} and ${stats.lastMeet.toFixed(2)} s); ${stats.pairsInFront} shared-pixel pairs, all phantom in front, ${stats.thirdTests} third blocks near them, none sharing their pixels; ${stats.picks} lines of sight picked as drawn`);
if (failures.length) {
  console.error(`\nFAIL (${failures.length}):`);
  failures.slice(0, 30).forEach((f) => console.error('  ' + f));
  process.exit(1);
}
console.log(`\nPASS: geometry holds for n = 1..${MAX_STEPS}: closed at rest, no block ever inside another (lifts, tilt cone, arrival), the far start always in front where it meets the near end, the phantom offset continuous.`);
