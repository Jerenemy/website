// The seam: where the open chain closes on screen and nowhere else.
//
// The far start (the first blocks of side 0) must read IN FRONT of the near end (the last
// steps of side 2), although in 3D it is a whole gap behind. So it is drawn as if it stood
// nearer along the CURRENT view direction v, as a phantom
//
//   phantom = far block + t·v,
//
// and the near end yields wherever a phantom hides it from the eye (src/monument.js stands
// those fragments behind the far start in depth; nothing is ever cut away). A camera that
// looks along v cannot see displacement along v, so a phantom covers exactly the far block's
// own pixels, at every angle: the near end reads as an ordinary whole block partly behind the
// far one, never as a sliced one. At rest at the true angle v is parallel to the gap and
// t = gap·v puts every phantom exactly where the closed loop would: the paradox image is the
// closed tribar's.
//
// How far nearer. Off the true angle (the pointer's tilt, the arrival's swing) the phantom
// slides sideways against the near end, and gap·v alone would let it into a near-end block:
// one block passing through another. So t is raised, just enough, so that every phantom is in
// front of (or touching) every near-end block it overlaps on screen, and never inside one:
// what the eye gets is always the image of solid boxes that do not intersect, the far start
// sliding in front. t is a max of continuous functions of the pose and the lifts, so it never
// jumps; and since only t·v changes, nothing on screen depends on its exact value.
//
// During the arrival each side carries its own drift and twist (src/intro.js), so the test is
// made in side 0's frame, against side 2's blocks carried there: Q, K below. Pure arithmetic,
// no renderer types: tools/check-geometry.mjs runs it in node.
import { VIEW_AXIS } from './tribar.js';

const PARALLEL = 1e-12;   // |n·d| below this (relative) is "this axis is parallel to the motion"
const DEGENERATE = 1e-12; // cross products of edges this close to parallel are skipped (their faces are slivers)

// Scratch for sweepInterval: one candidate axis and a column of q (typed: no boxed doubles).
const axis = new Float64Array(3), col = [new Float64Array(3), new Float64Array(3), new Float64Array(3)];

/**
 * The interval of t over which box A (axis-aligned: centre ca, half ha) moved by t·d meets box
 * B (centre cb, half hb, its axes the columns of the row-major rotation q), by separating
 * axes: they meet iff their projections overlap on each face normal of either box and on each
 * cross product of an edge of each, and along every such axis that holds for one interval of
 * t. Writes [lo, hi] into `out`; lo > hi when no t works (the images do not overlap along d).
 * `aligned` (q the identity) needs only the three face normals.
 */
function sweepInterval(ca, ha, cb, hb, q, d, out, aligned = false) {
  let lo = -Infinity, hi = Infinity;
  for (let j = 0; j < 3; j++) { col[j][0] = q[j]; col[j][1] = q[3 + j]; col[j][2] = q[6 + j]; }
  const count = aligned ? 3 : 15;
  for (let k = 0; k < count; k++) {
    if (k < 3) { axis[0] = k === 0 ? 1 : 0; axis[1] = k === 1 ? 1 : 0; axis[2] = k === 2 ? 1 : 0; }
    else if (k < 6) { const c = col[k - 3]; axis[0] = c[0]; axis[1] = c[1]; axis[2] = c[2]; }
    else {
      const i = Math.floor((k - 6) / 3), c = col[(k - 6) % 3];   // e_i x column
      axis[0] = i === 0 ? 0 : i === 1 ? c[2] : -c[1];
      axis[1] = i === 0 ? -c[2] : i === 1 ? 0 : c[0];
      axis[2] = i === 0 ? c[1] : i === 1 ? -c[0] : 0;
      if (axis[0] * axis[0] + axis[1] * axis[1] + axis[2] * axis[2] < DEGENERATE * DEGENERATE) continue;
    }
    const nx = axis[0], ny = axis[1], nz = axis[2];
    const reach = ha[0] * Math.abs(nx) + ha[1] * Math.abs(ny) + ha[2] * Math.abs(nz)
      + hb[0] * Math.abs(nx * col[0][0] + ny * col[0][1] + nz * col[0][2])
      + hb[1] * Math.abs(nx * col[1][0] + ny * col[1][1] + nz * col[1][2])
      + hb[2] * Math.abs(nx * col[2][0] + ny * col[2][1] + nz * col[2][2]);
    const m = nx * (cb[0] - ca[0]) + ny * (cb[1] - ca[1]) + nz * (cb[2] - ca[2]);
    const s = nx * d[0] + ny * d[1] + nz * d[2];
    if (Math.abs(s) <= PARALLEL * Math.hypot(nx, ny, nz)) {
      if (Math.abs(m) > reach) { lo = Infinity; hi = -Infinity; break; }   // apart along an axis the motion cannot close
      continue;
    }
    let a = (m - reach) / s, b = (m + reach) / s;
    if (s < 0) { const x = a; a = b; b = x; }
    if (a > lo) lo = a;
    if (b < hi) hi = b;
  }
  out[0] = lo; out[1] = hi;
  return out;
}

// Line / axis-aligned box, for picking. Returns the entry distance, or -1 on a miss.
// Scalar-only on purpose: this runs for every block on every pointer frame and must not
// allocate (the interval lives in one typed array, never in boxed doubles).
const slabSpan = new Float64Array(2);   // [near, far]
function slabAxis(o, d, h) {
  if (Math.abs(d) < 1e-9) return Math.abs(o) <= h;
  let n = (-h - o) / d, f = (h - o) / d;
  if (n > f) { const s = n; n = f; f = s; }
  if (n > slabSpan[0]) slabSpan[0] = n;
  if (f < slabSpan[1]) slabSpan[1] = f;
  return true;
}
function slab(ox, oy, oz, dx, dy, dz, cx, cy, cz, half) {
  slabSpan[0] = -Infinity; slabSpan[1] = Infinity;
  if (!slabAxis(ox - cx, dx, half[0]) || !slabAxis(oy - cy, dy, half[1]) || !slabAxis(oz - cz, dz, half[2])) return -1;
  return slabSpan[1] > Math.max(slabSpan[0], 1e-4) ? Math.max(slabSpan[0], 0) : -1;
}

/** How far nearer a phantom must stand to be clear of a block: the far end of the meeting
 *  interval when the two overlap on screen, and below it, continuously, when they do not. */
const clearance = (lo, hi) => (lo <= hi ? hi : 2 * hi - lo);

export function createSeam(tribar) {
  const { blocks, gap, phantomSources: phantoms, seamBlocks, sideCentre } = tribar;
  const reach = Math.hypot(gap[0], gap[1], gap[2]);
  const IDENTITY = new Float64Array([1, 0, 0, 0, 1, 0, 0, 0, 1]);
  const ZERO = [0, 0, 0];
  // Scratch: one phantom, one near-end block, the interval, the transform under construction.
  const ca = new Float64Array(3), cb = new Float64Array(3), lifted = new Float64Array(3), span = new Float64Array(2);
  const q = new Float64Array(9), k = new Float64Array(3), d = new Float64Array(3), tmp = new Float64Array(3);
  // What the last assembled solve was made for: at rest (and while only the tilt moves) the
  // answer, or half of it, is already known, and the frame asks again every frame.
  const solved = { valid: false, view: new Float64Array(3), lift: new Float64Array(blocks.length) };
  const liftsAsSolved = (lift) => {
    for (let n = 0; n < phantoms.length; n++) if (lift[phantoms[n]] !== solved.lift[phantoms[n]]) return false;
    for (let n = 0; n < seamBlocks.length; n++) if (lift[seamBlocks[n]] !== solved.lift[seamBlocks[n]]) return false;
    return true;
  };

  /** Smallest t >= base that keeps every phantom clear of every near-end block, with side 2
   *  carried into side 0's frame by p -> rot·p + shift, the phantoms moving along dir. */
  function solveOffset(rot, shift, dir, aligned, lift, base) {
    let t = base;
    for (let a = 0; a < phantoms.length; a++) {
      const pi = phantoms[a], p = blocks[pi];
      ca[0] = p.center[0]; ca[1] = p.center[1]; ca[2] = p.center[2];
      ca[p.tread] += lift[pi];
      for (let b = 0; b < seamBlocks.length; b++) {
        const si = seamBlocks[b], s = blocks[si];
        lifted[0] = s.center[0]; lifted[1] = s.center[1]; lifted[2] = s.center[2];
        lifted[s.tread] += lift[si];
        for (let r = 0; r < 3; r++) cb[r] = rot[3 * r] * lifted[0] + rot[3 * r + 1] * lifted[1] + rot[3 * r + 2] * lifted[2] + shift[r];
        sweepInterval(ca, p.half, cb, s.half, rot, dir, span, aligned);
        const need = clearance(span[0], span[1]);
        if (need > t) t = need;
      }
    }
    return t;
  }

  /** Does a phantom meet the line o + s·d at or before s = t (where it enters a near-end step)? */
  function hiddenAt(t, ox, oy, oz, dx, dy, dz, lift, reach) {
    for (let a = 0; a < phantoms.length; a++) {
      const pi = phantoms[a], p = blocks[pi], l = lift[pi];
      const enter = slab(ox, oy, oz, dx, dy, dz,
        p.center[0] - dx * reach + (p.tread === 0 ? l : 0), p.center[1] - dy * reach + (p.tread === 1 ? l : 0), p.center[2] - dz * reach + (p.tread === 2 ? l : 0), p.half);
      if (enter >= 0 && enter <= t + 1e-6) return true;
    }
    return false;
  }

  const seam = {
    /** The far-start blocks restated as phantoms (block indices, all on side 0). */
    phantoms,
    /** The view direction the seam was solved for, monument space, pointing at the eye. */
    view: VIEW_AXIS.slice(),
    /** t: how far along `view` the phantoms stand from the far start. */
    offset: reach,
    /** t for the same lifts at the true angle, assembled (what the untilted hit test uses). */
    restOffset: reach,
    /** Side 2's structure frame into side 0's (row-major rotation, then origin): the shader
     *  carries a near-end fragment there and casts it along `dir` (the view, in side 0's frame). */
    rot: IDENTITY.slice(), origin: gap.map((g) => -g), dir: VIEW_AXIS.slice(),
    /** Where side 0's structure frame sits in side 2's, rotation aside: the shift that places a
     *  far-start neighbour beside the near end for contact shadows (the gap, at rest). */
    carry: gap.slice(),
    /** How far, on screen (beams), the far start stands from where the closed loop would put
     *  it: 0 exactly when the seam is shut. */
    tear: 0,
    /** Counts the solves that changed anything (src/monument.js uploads the seam only then). */
    version: 0,

    /**
     * The block a line of sight meets first, by the rule the shader draws with: a near-end step
     * is passed over wherever a phantom (its far block moved `reach` toward the eye) meets the
     * line nearer the eye than the step does, and the line goes on to the far block itself.
     * The line is the view, so this is exactly what is drawn. Assembled only (picking waits for
     * the arrival); structure space, d pointing away from the eye. @returns block index or -1
     */
    pick(ox, oy, oz, dx, dy, dz, lift, reach) {
      let best = -1, bestT = Infinity;
      for (let i = 0; i < blocks.length; i++) {
        const b = blocks[i], l = lift[i];
        const t = slab(ox, oy, oz, dx, dy, dz, b.center[0] + (b.tread === 0 ? l : 0), b.center[1] + (b.tread === 1 ? l : 0), b.center[2] + (b.tread === 2 ? l : 0), b.half);
        if (t < 0 || t >= bestT) continue;
        if (b.side === 2 && b.step >= 0 && hiddenAt(t, ox, oy, oz, dx, dy, dz, lift, reach)) continue;
        best = i; bestT = t;
      }
      return best;
    },

    /**
     * @param view   unit vector toward the eye, monument space (src/stage.js `view`)
     * @param sides  the arrival's per-side transforms (a sample of src/intro.js: sideRot, sideOff), or null once assembled
     * @param lift   per-block lift along its tread, beams
     */
    solve(view, sides, lift) {
      const sameLifts = !sides && solved.valid && liftsAsSolved(lift);
      if (sameLifts && view[0] === solved.view[0] && view[1] === solved.view[1] && view[2] === solved.view[2]) return seam;
      seam.version++;
      seam.view[0] = view[0]; seam.view[1] = view[1]; seam.view[2] = view[2];
      const base = gap[0] * view[0] + gap[1] * view[1] + gap[2] * view[2];
      let aligned = true;
      if (!sides) { q.set(IDENTITY); k[0] = k[1] = k[2] = 0; d[0] = view[0]; d[1] = view[1]; d[2] = view[2]; } else {
        // Monument point of side s: R_s (p - c_s) + c_s + off_s. Side 2 into side 0:
        //   p0 = R0^T R2 p2 + R0^T (c2 - R2 c2 + off2 - c0 - off0) + c0.
        const R0 = sides.sideRot[0], R2 = sides.sideRot[2], c0 = sideCentre[0], c2 = sideCentre[2], o0 = sides.sideOff[0], o2 = sides.sideOff[2];
        for (let r = 0; r < 3; r++) {
          for (let c = 0; c < 3; c++) q[3 * r + c] = R0[r] * R2[c] + R0[3 + r] * R2[3 + c] + R0[6 + r] * R2[6 + c];
          tmp[r] = c2[r] - (R2[3 * r] * c2[0] + R2[3 * r + 1] * c2[1] + R2[3 * r + 2] * c2[2]) + o2[r] - c0[r] - o0[r];
        }
        for (let r = 0; r < 3; r++) {
          k[r] = R0[r] * tmp[0] + R0[3 + r] * tmp[1] + R0[6 + r] * tmp[2] + c0[r];
          d[r] = R0[r] * view[0] + R0[3 + r] * view[1] + R0[6 + r] * view[2];
        }
        aligned = false;
      }
      const t = solveOffset(q, k, d, aligned, lift, base);
      seam.offset = t;
      if (sides) seam.restOffset = reach;
      else if (!sameLifts) seam.restOffset = solveOffset(IDENTITY, ZERO, VIEW_AXIS, true, lift, reach);
      solved.valid = !sides;
      if (solved.valid) {
        solved.view[0] = view[0]; solved.view[1] = view[1]; solved.view[2] = view[2];
        for (let n = 0; n < phantoms.length; n++) solved.lift[phantoms[n]] = lift[phantoms[n]];
        for (let n = 0; n < seamBlocks.length; n++) solved.lift[seamBlocks[n]] = lift[seamBlocks[n]];
      }
      seam.rot.set(q);
      for (let r = 0; r < 3; r++) {
        seam.dir[r] = d[r];
        seam.origin[r] = k[r] - t * d[r];
        seam.carry[r] = t * d[r] - k[r];
        tmp[r] = seam.carry[r] - gap[r];
      }
      const along = tmp[0] * view[0] + tmp[1] * view[1] + tmp[2] * view[2];
      seam.tear = Math.hypot(tmp[0] - along * view[0], tmp[1] - along * view[1], tmp[2] - along * view[2]);
      return seam;
    },
  };
  return seam;
}
