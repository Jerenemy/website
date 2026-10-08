// The door: a recess in the presented step's riser, and the light that reaches into it. Pure
// arithmetic (no renderer types), shared by the frame (the bounce, the departure), the test
// hook and tools/check-geometry.mjs; src/monument.js evaluates the same transport per fragment,
// from the GLSL written here beside the arithmetic it mirrors.
//
// The door frame, per block, its lift included: the origin is the centre of the opening, on the
// riser (the block's leading face); x points out of the riser (the block's travel), y up its
// tread normal, z along its wall axis. The opening is the rectangle x = 0, |y| <= H/2 * open,
// |z| <= W/2 (the slot opens from a slit, lintel and sill sliding apart); behind it is a box
// cavity, -depth <= x <= 0, |y| <= H/2, |z| <= W/2. It is drawn by casting the line of sight
// into that box (src/monument.js), so its depth, jambs, sill and lintel parallax with the view.
// One block's own geometry: nothing here depends on distance along the view (the paradox rule).
//
// Light transport. The light is a sphere of radius R. A point of the cavity sees it through the
// opening, or directly when the light is itself inside the cavity (a box is convex):
//
//   V = max(the light's disc through the opening, the light inside the cavity)
//
// The first is the coverage of the light's disc as seen from the point (angular radius
// asin(R / d)) by the opening as seen from the point (a convex spherical quadrilateral), by
// their signed angular distance: exactly 0 when no ray from the point to the light passes the
// opening, exactly 1 when every one does, smooth between (the penumbra, sized by the light's
// apparent radius). Direct irradiance is V times the face's cosine to the light times the
// lantern's own falloff on the stone (src/monument.js), so the inside is lit by the same light as
// the outside, and by nothing else: with no line of sight it is exactly zero. One bounce fills
// the rest, ρ·Ē·(1 - F): Ē the cavity's mean direct irradiance, F the opening's form factor
// (the share of the hemisphere that is the way out). The hall's neutral air comes in through
// the same opening, ambient·F, so the back of the recess is darkest.
import { SHADING, MOTION } from './config.js';
import { smoothstep } from './spring.js';

export const LIGHT_RADIUS = SHADING.lightRadius;
const R = LIGHT_RADIUS;
const HW = SHADING.doorWidth / 2, HH = SHADING.doorHeight / 2;
const GLOW2 = SHADING.glowRadius * SHADING.glowRadius;

/** The lantern's falloff on the stone (src/monument.js), as a function of squared distance. */
export const falloff = (d2) => { const r2 = d2 / GLOW2; return 1 / (1 + r2 * r2 * 4 + r2 * 1.5); };

/** A fresh door frame record (see doorFrame). */
export const newFrame = () => ({ origin: [0, 0, 0], x: 0, y: 1, z: 2, depth: 0, run: 0 });

/** The door frame of block `blk` lifted `lift` beams: origin (structure space), the structure
 *  axis that is each door axis, the step's length along its travel and the cavity's depth. */
export function doorFrame(blk, lift, out = newFrame()) {
  const x = blk.travel, y = blk.tread, z = 3 - x - y;
  out.x = x; out.y = y; out.z = z;
  out.origin[0] = blk.center[0]; out.origin[1] = blk.center[1]; out.origin[2] = blk.center[2];
  out.origin[x] += blk.half[x];
  out.origin[y] += blk.half[y] - SHADING.doorDrop + lift;
  out.run = 2 * blk.half[x];
  // A short step (many works) keeps a recess no deeper than a fraction of its length.
  out.depth = Math.min(SHADING.doorDepth, SHADING.doorDepthMax * out.run);
  return out;
}
export function toDoor(f, p, out = [0, 0, 0]) {
  out[0] = p[f.x] - f.origin[f.x]; out[1] = p[f.y] - f.origin[f.y]; out[2] = p[f.z] - f.origin[f.z];
  return out;
}
export function fromDoor(f, q, out = [0, 0, 0]) {
  out[f.x] = q[0] + f.origin[f.x]; out[f.y] = q[1] + f.origin[f.y]; out[f.z] = q[2] + f.origin[f.z];
  return out;
}

// ---- the transport (mirrored in GLSL below) -------------------------------------------------
const corners = [new Float64Array(3), new Float64Array(3), new Float64Array(3), new Float64Array(3)];
const SY = [-1, 1, 1, -1], SZ = [-1, -1, 1, 1];
const n0 = new Float64Array(3), w = new Float64Array(3), c = new Float64Array(3);
const crossInto = (a, b, o) => { o[0] = a[1] * b[2] - a[2] * b[1]; o[1] = a[2] * b[0] - a[0] * b[2]; o[2] = a[0] * b[1] - a[1] * b[0]; return o; };
const dot3 = (a, b) => a[0] * b[0] + a[1] * b[1] + a[2] * b[2];
const clamp1 = (x) => Math.min(1, Math.max(-1, x));
/** The opening's corners as unit directions from p (written into `corners`). @returns false if p is in the plane */
function aim(p, ho, hw) {
  if (Math.abs(p[0]) < 1e-7) return false;
  for (let i = 0; i < 4; i++) {
    const a = corners[i];
    a[0] = -p[0]; a[1] = SY[i] * ho - p[1]; a[2] = SZ[i] * hw - p[2];
    const l = Math.hypot(a[0], a[1], a[2]); a[0] /= l; a[1] /= l; a[2] /= l;
  }
  return true;
}

/**
 * Signed angular distance (radians) from the unit direction u to the opening as seen from p:
 * positive inside it (the distance to its edge), negative outside (the distance to it). The
 * opening seen from a point off its plane is a convex spherical quadrilateral; its edges are
 * arcs of great circles. Exact.
 */
export function apertureAngle(p, u, ho, hw = HW) {
  if (!aim(p, ho, hw) || ho <= 0) return -Math.PI;
  const side = p[0] < 0 ? 1 : -1;   // corners run anticlockwise seen from behind the riser
  let within = true, inside = Infinity, outside = Infinity;
  for (let i = 0; i < 4; i++) {
    const A = corners[i], B = corners[(i + 1) & 3];
    crossInto(A, B, n0);
    const l = Math.hypot(n0[0], n0[1], n0[2]);
    n0[0] /= l; n0[1] /= l; n0[2] /= l;
    const s = side * dot3(u, n0);         // sine of the distance to the edge's great circle, + inward
    if (s < 0) within = false;
    inside = Math.min(inside, s);
    // Distance to the edge's arc: to its great circle if the foot falls between its ends, else to the nearer end.
    const t = dot3(u, n0);
    w[0] = u[0] - t * n0[0]; w[1] = u[1] - t * n0[1]; w[2] = u[2] - t * n0[2];
    const between = dot3(crossInto(A, w, c), n0) >= 0 && dot3(crossInto(w, B, c), n0) >= 0;
    const arc = between ? Math.asin(Math.min(1, Math.abs(s))) : Math.min(Math.acos(clamp1(dot3(u, A))), Math.acos(clamp1(dot3(u, B))));
    outside = Math.min(outside, arc);
  }
  return within ? Math.asin(Math.min(1, inside)) : -outside;
}

/** Signed distance from q to the cavity's box (negative inside). */
export function cavityDistance(q, depth, hh = HH, hw = HW) {
  const dx = Math.abs(q[0] + depth / 2) - depth / 2, dy = Math.abs(q[1]) - hh, dz = Math.abs(q[2]) - hw;
  const ox = Math.max(dx, 0), oy = Math.max(dy, 0), oz = Math.max(dz, 0);
  return Math.hypot(ox, oy, oz) + Math.min(Math.max(dx, dy, dz), 0);
}

const u = new Float64Array(3);
/**
 * Direct irradiance from the light at L (door frame) on a point p of the cavity with inward
 * normal n, per unit of the light's power: visibility x cosine x the lantern's falloff.
 * @param ho the opening's half height now (H/2 x how open)
 */
export function direct(p, n, L, ho, depth) {
  u[0] = L[0] - p[0]; u[1] = L[1] - p[1]; u[2] = L[2] - p[2];
  const d2 = u[0] * u[0] + u[1] * u[1] + u[2] * u[2], d = Math.sqrt(d2);
  u[0] /= d; u[1] /= d; u[2] /= d;
  const cos = n[0] * u[0] + n[1] * u[1] + n[2] * u[2];
  if (cos <= 0) return 0;
  const alpha = Math.asin(Math.min(1, R / d));
  const sigma = apertureAngle(p, u, ho);
  const through = sigma <= -alpha ? 0 : smoothstep(-alpha, alpha, sigma);
  const sd = cavityDistance(L, depth);
  const within = sd >= R ? 0 : 1 - smoothstep(-R, R, sd);
  return Math.max(through, within) * cos * falloff(d2);
}

/** Form factor from a point p (normal n) to the opening: the share of its view that is the way out. */
export function openingFactor(p, n, ho, hw = HW) {
  if (!aim(p, ho, hw) || ho <= 0) return 0;
  let f = 0;
  for (let i = 0; i < 4; i++) {
    const A = corners[i], B = corners[(i + 1) & 3];
    crossInto(A, B, c);
    const l = Math.hypot(c[0], c[1], c[2]);
    if (l > 1e-9) f += Math.atan2(l, dot3(A, B)) * dot3(n, c) / l;
  }
  return Math.abs(f) / (2 * Math.PI);
}

// The cavity's five inner faces: [normal, fixed axis, fixed coordinate (in units of the face's
// own half size or of depth), the two axes spanned]. The back, the floor (sill), the ceiling
// (lintel), the jamb at -z and the jamb at +z.
const FACES = [
  { n: [1, 0, 0], axis: 0, at: 'back', span: [1, 2] },
  { n: [0, 1, 0], axis: 1, at: -1, span: [0, 2] },
  { n: [0, -1, 0], axis: 1, at: 1, span: [0, 2] },
  { n: [0, 0, 1], axis: 2, at: -1, span: [0, 1] },
  { n: [0, 0, -1], axis: 2, at: 1, span: [0, 1] },
];
const GRID = 6;
const sample = new Float64Array(3), half = new Float64Array(3), mid = new Float64Array(3);
/** Calls visit(point, normal, area) at the centres of a GRID x GRID grid on every inner face. */
export function eachInnerPoint(depth, visit, grid = GRID) {
  half[0] = depth / 2; half[1] = HH; half[2] = HW; mid[0] = -depth / 2;
  for (let f = 0; f < FACES.length; f++) {
    const face = FACES[f];
    const [s, t] = face.span;
    const area = (2 * half[s] / grid) * (2 * half[t] / grid);
    for (let i = 0; i < grid; i++) {
      for (let j = 0; j < grid; j++) {
        sample[face.axis] = face.at === 'back' ? -depth : face.at * half[face.axis];
        sample[s] = mid[s] + half[s] * (2 * (i + 0.5) / grid - 1);
        sample[t] = mid[t] + half[t] * (2 * (j + 0.5) / grid - 1);
        visit(sample, face.n, area);
      }
    }
  }
}

const lit = { L: null, ho: 0, depth: 0, sum: 0, area: 0, litArea: 0 };
const gather = (p, n, a) => { const e = direct(p, n, lit.L, lit.ho, lit.depth); lit.sum += e * a; lit.area += a; if (e > 0) lit.litArea += a; };
/** What the light at L puts into the cavity, per unit power: its inner faces' mean direct irradiance
 *  (what one bounce spreads) and the share of their area it reaches. Writes { mean, share } into out. */
export function cavityLight(L, ho, depth, out = { mean: 0, share: 0 }) {
  lit.L = L; lit.ho = ho; lit.depth = depth; lit.sum = lit.area = lit.litArea = 0;
  eachInnerPoint(depth, gather);
  out.mean = lit.sum / lit.area; out.share = lit.litArea / lit.area;
  return out;
}
/** The cavity's mean direct irradiance from the light at L (per unit power). */
export const meanDirect = (L, ho, depth) => cavityLight(L, ho, depth).mean;

/** How far the light sphere is inside the cavity, through the opening (0 outside, 1 in): it
 *  then lights the outside only through the opening, and the riser hides it from the eye. */
export function insideness(L, ho, hw = HW) {
  const behind = 1 - smoothstep(-R, R, L[0]);
  const lateral = smoothstep(-R, R, Math.min(ho - Math.abs(L[1]), hw - Math.abs(L[2])));
  return behind * lateral;
}

// ---- where the light is, for a door ----------------------------------------------------------
const c0 = [0, 0, 0], c1 = [0, 0, 0];
/**
 * The light's structure-space position as station j (its step, its door, its cube) sees it. The
 * loop position s is taken the short way round from j; where that way crosses the seam, the part
 * of the light beyond it stands where the far start (or the near end) stands beside j: moved by
 * the seam's carry (src/seam.js), the very shift the phantoms and the cross-seam contact shadows
 * make. In the seam segment the light is drawn at both ends, cross-faded (tribar.seamBlend); here
 * the two ends are cross-faded with the same weight, each carried beside j. Carry runs along the
 * view, so the point lands exactly on the light as drawn: only its depth is resolved, from j's
 * side of the seam. The stone is lit from here, block by block (src/monument.js).
 */
export function lightFor(tribar, j, s, carry, out = [0, 0, 0]) {
  const N = tribar.stepCount;
  let d = (((s - j) % N) + N) % N;
  if (d > N / 2) d -= N;
  const b = j + d;                       // loop position unrolled from j
  const seamSegment = (((s % N) + N) % N) >= N - 1;
  let s0 = 0, s1 = 0;                    // carries applied to the near and the far end
  if (seamSegment) { if (b >= j) s1 = 1; else s0 = -1; }   // into the seam segment: its far (forward) or near (backward) end stands beside j
  else if (b >= N) s0 = s1 = 1;          // beyond it, forward: the far start, beside the near end
  else if (b < 0) s0 = s1 = -1;          // beyond it, backward: the near end, beside the far start
  const blend = tribar.seamBlend(s);
  tribar.pathAt(s, c0, 0); tribar.pathAt(s, c1, 1);
  for (let k = 0; k < 3; k++) out[k] = (1 - blend) * (c0[k] + s0 * carry[k]) + blend * (c1[k] + s1 * carry[k]);
  return out;
}

// ---- the departure -------------------------------------------------------------------------------
// The light leaves the dock, rises over the nosing, swings down in front of the opening and goes
// in level, coming to rest inside: a cubic from where it is to the porch (in front of the
// opening, at its height), then straight in. tools/check-geometry.mjs proves the light's sphere
// clears every block along it, for every step of every count.
const PATH_SAMPLES = 64;
export function createPath() {
  const p0 = [0, 0, 0], k1 = [0, 0, 0], k2 = [0, 0, 0], porch = [0, 0, 0], end = [0, 0, 0];
  const table = new Float64Array(PATH_SAMPLES + 1);
  let curve = 0, total = 0;
  const bezier = (t, out) => {
    const v = 1 - t, a = v * v * v, b = 3 * v * v * t, e = 3 * v * t * t, f = t * t * t;
    for (let k = 0; k < 3; k++) out[k] = a * p0[k] + b * k1[k] + e * k2[k] + f * porch[k];
    return out;
  };
  const q = [0, 0, 0], r = [0, 0, 0];
  return {
    /** @param from the light's door-frame position as the slide begins  @param depth the cavity's */
    plan(from, depth) {
      for (let k = 0; k < 3; k++) p0[k] = from[k];
      porch[0] = SHADING.doorPorch; porch[1] = 0; porch[2] = 0;
      k1[0] = SHADING.doorPorch * 0.17; k1[1] = from[1] + SHADING.doorArc; k1[2] = from[2];
      k2[0] = SHADING.doorPorch * 2; k2[1] = 0; k2[2] = 0;
      end[0] = -depth / 2; end[1] = 0; end[2] = 0;
      // Arc length of the curve, tabulated, so the light's speed is its own and not the curve's.
      bezier(0, r);
      table[0] = 0;
      for (let i = 1; i <= PATH_SAMPLES; i++) {
        bezier(i / PATH_SAMPLES, q);
        table[i] = table[i - 1] + Math.hypot(q[0] - r[0], q[1] - r[1], q[2] - r[2]);
        r[0] = q[0]; r[1] = q[1]; r[2] = q[2];
      }
      curve = table[PATH_SAMPLES];
      total = curve + Math.hypot(porch[0] - end[0], porch[1] - end[1], porch[2] - end[2]);
    },
    get length() { return total; },
    /** The share of the length that reaches the porch. */
    get porch() { return total > 0 ? curve / total : 1; },
    /** The share of the length at which the way in first stands `x` beams in front of the riser
     *  (the light leaning in at the door: src/frame.js). The curve leaves the dock behind the riser
     *  and reaches the porch in front of it, so it crosses x once on the way out. */
    alongTo(x) {
      let i = 1;
      while (i <= PATH_SAMPLES && bezier(i / PATH_SAMPLES, q)[0] < x) i++;
      if (i > PATH_SAMPLES) return this.porch;
      let lo = (i - 1) / PATH_SAMPLES, hi = i / PATH_SAMPLES;
      for (let k = 0; k < 30; k++) { const mid = (lo + hi) / 2; if (bezier(mid, q)[0] < x) lo = mid; else hi = mid; }
      // Curve parameter to share of length, through the arc-length table.
      const f = hi * PATH_SAMPLES, j = Math.min(Math.floor(f), PATH_SAMPLES - 1);
      return (table[j] + (table[j + 1] - table[j]) * (f - j)) / total;
    },
    /** The point a fraction `along` (0..1) of the way by length. */
    at(along, out) {
      const s = Math.min(1, Math.max(0, along)) * total;
      if (s >= curve) {
        const t = total > curve ? (s - curve) / (total - curve) : 1;
        for (let k = 0; k < 3; k++) out[k] = porch[k] + (end[k] - porch[k]) * t;
        return out;
      }
      let i = 1;
      while (i < PATH_SAMPLES && table[i] < s) i++;
      const t = (i - 1 + (s - table[i - 1]) / Math.max(table[i] - table[i - 1], 1e-12)) / PATH_SAMPLES;
      return bezier(t, out);
    },
  };
}

/**
 * Where the light is along its way in, as a fraction of the length, at a fraction t of the slide:
 * it leaves the dock from rest, slows as it lines up with the opening, glides in and comes to
 * rest inside. Two cubic Hermite pieces in time meeting at the porch (a share `porch` of the
 * length) with one speed, chosen so that neither piece ever turns back.
 */
export function slideProgress(t, porch) {
  const x = Math.min(1, Math.max(0, t)), k = MOTION.doorLineUp, e = porch, h = 1 - e;
  const v = Math.min(3 * e / k, MOTION.doorEnter * h / (1 - k));   // length per slide, at the porch
  if (x <= k) {
    const s = x / k;
    return e * (3 * s * s - 2 * s * s * s) + (s * s * s - s * s) * v * k;
  }
  const s = (x - k) / (1 - k);
  return e + h * (3 * s * s - 2 * s * s * s) + (s * s * s - 2 * s * s + s) * v * (1 - k);
}

/**
 * The slide begun from a share `from` of the way in (the light was leaning in at the door): on along
 * the same way, from rest, the same two pieces fitted to what is left of it. From 0 it is slideProgress.
 */
export function slideOn(t, porch, from = 0) {
  if (from <= 0) return slideProgress(t, porch);
  return from + (1 - from) * slideProgress(t, (porch - from) / (1 - from));
}

// ---- the same transport, for the shader --------------------------------------------------------
const f4 = (x) => x.toFixed(4);
export const DOOR_GLSL = /* glsl */ `
  // The door (src/door.js): the opening x = 0, |y| <= ho, |z| <= hw seen from p, and a light of
  // radius ${f4(R)} at L. Returns the signed angular distance from u to the opening (exact, for a
  // convex spherical quadrilateral: + inside, the distance to its edge; - outside, the distance to it).
  float apertureAngle(vec3 p, vec3 u, float ho, float hw) {
    if (abs(p.x) < 1.0e-7 || ho <= 0.0) return -3.14159;
    vec3 a[4];
    a[0] = normalize(vec3(0.0, -ho, -hw) - p); a[1] = normalize(vec3(0.0, ho, -hw) - p);
    a[2] = normalize(vec3(0.0, ho, hw) - p); a[3] = normalize(vec3(0.0, -ho, hw) - p);
    float side = p.x < 0.0 ? 1.0 : -1.0;
    bool within = true;
    float inside = 1.0e3, outside = 1.0e3;
    for (int i = 0; i < 4; i++) {
      vec3 A = a[i], B = a[(i + 1) & 3];
      vec3 n = normalize(cross(A, B));
      float t = dot(u, n), s = side * t;
      if (s < 0.0) within = false;
      inside = min(inside, s);
      vec3 w = u - t * n;
      bool between = dot(cross(A, w), n) >= 0.0 && dot(cross(w, B), n) >= 0.0;
      float arc = between ? asin(min(1.0, abs(s))) : min(acos(clamp(dot(u, A), -1.0, 1.0)), acos(clamp(dot(u, B), -1.0, 1.0)));
      outside = min(outside, arc);
    }
    return within ? asin(min(1.0, inside)) : -outside;
  }
  float cavityDistance(vec3 q, float depth, float hh, float hw) {
    vec3 d = abs(q - vec3(-0.5 * depth, 0.0, 0.0)) - vec3(0.5 * depth, hh, hw);
    return length(max(d, 0.0)) + min(max(d.x, max(d.y, d.z)), 0.0);
  }
  float lanternFall(float d2) { float r2 = d2 / ${f4(GLOW2)}; return 1.0 / (1.0 + r2 * r2 * 4.0 + r2 * 1.5); }
  // The light's disc through the opening, as seen from p: (signed angle, the disc's angular radius,
  // cosine x falloff toward its centre).
  vec3 doorSight(vec3 p, vec3 n, vec3 L, float ho, float hw) {
    vec3 toL = L - p;
    float d2 = dot(toL, toL), d = sqrt(d2);
    vec3 u = toL / d;
    return vec3(apertureAngle(p, u, ho, hw), asin(min(1.0, ${f4(R)} / d)), max(dot(n, u), 0.0) * lanternFall(d2));
  }
  // Exactly 0 when the disc misses the opening, 1 when it lies wholly inside. (The penumbra, 2 alpha,
  // spans many pixels wherever the light is near enough to matter, so it needs no pixel term.)
  float doorCover(float sigma, float alpha) {
    return sigma <= -alpha ? 0.0 : smoothstep(-alpha, alpha, sigma);
  }
  // Form factor from p (normal n) to the opening (Lambert's polygon formula).
  float edgeFactor(vec3 A, vec3 B, vec3 n) {
    vec3 c = cross(A, B);
    float l = length(c);
    return l < 1.0e-9 ? 0.0 : atan(l, dot(A, B)) * dot(n, c) / l;
  }
  float openingFactor(vec3 p, vec3 n, float ho, float hw) {
    if (abs(p.x) < 1.0e-7 || ho <= 0.0) return 0.0;
    vec3 a0 = normalize(vec3(0.0, -ho, -hw) - p), a1 = normalize(vec3(0.0, ho, -hw) - p);
    vec3 a2 = normalize(vec3(0.0, ho, hw) - p), a3 = normalize(vec3(0.0, -ho, hw) - p);
    return abs(edgeFactor(a0, a1, n) + edgeFactor(a1, a2, n) + edgeFactor(a2, a3, n) + edgeFactor(a3, a0, n)) / 6.2831853;
  }
`;
