// Test hook (window.__demo.doorProbe): the door's light transport checked against an independent
// line-of-sight test, in the model (src/door.js) and on the GPU, as drawn.
//
// The light is swept round the presented step's opening (in front of it at every height and side,
// behind the riser above the tread where it docks, grazing the wall plane, inside the cavity). For
// every position and every point of a dense grid on the cavity's five inner faces, line of sight
// is decided by brute force, with none of the model's arithmetic: the light's sphere, slightly
// enlarged, is sampled densely, and a sample is seen from the point if the segment between them
// stays in the cavity (the sample inside it) or leaves it through the opening (it crosses the riser
// plane within the opening). The model must give exactly zero wherever no sample is seen, and more
// than zero wherever the light's centre is seen with a margin and faces the point. Then, drawing the
// monument lit by that light alone, the pixels inside the opening must carry no colour at all
// (R = G = B, exactly, after the grade and the grain) for every position with no line of sight into
// the cavity, and must be vermilion for the positions that light it. (Lights stand where a light can
// be: in the air above the step in front, never inside another block; no other block stands between
// them and the opening, so the riser is the only occluder the test needs: tools/check-geometry.mjs
// proves the porch's volume clear of stone at every lift a block can take while the door is open.)
import { SHADING } from './config.js';
import { LIGHT_RADIUS, eachInnerPoint, direct, meanDirect } from './door.js';

const HW = SHADING.doorWidth / 2, HH = SHADING.doorHeight / 2;
const GRID = 8;          // per inner face (320 points)
const SAMPLES = 600;     // on the enlarged sphere: spacing about 0.15 R, under the enlargement
const GROW = 0.012;      // beams added to the light's radius for "no sample seen" (so a sliver is never missed)
const MARGIN = 0.01;     // beams: the centre's ray must clear the opening's edge by this to count as seen

const sphere = (() => {   // Fibonacci points on the unit sphere
  const out = [], g = Math.PI * (3 - Math.sqrt(5));
  for (let i = 0; i < SAMPLES; i++) {
    const y = 1 - 2 * (i + 0.5) / SAMPLES, r = Math.sqrt(1 - y * y);
    out.push([Math.cos(g * i) * r, y, Math.sin(g * i) * r]);
  }
  return out;
})();

/** Is X seen from p (inside the cavity), by the segment between them? margin > 0 asks for room to spare. */
function seen(p, X, ho, depth, margin = 0) {
  if (X[0] <= 0) {
    return X[0] >= -depth + margin && Math.abs(X[1]) <= HH - margin && Math.abs(X[2]) <= HW - margin;
  }
  const t = -p[0] / (X[0] - p[0]);
  const y = p[1] + t * (X[1] - p[1]), z = p[2] + t * (X[2] - p[2]);
  return Math.abs(y) <= ho - margin && Math.abs(z) <= HW - margin;
}
function anySeen(p, L, ho, depth, r) {
  if (seen(p, L, ho, depth)) return true;
  const X = [0, 0, 0];
  for (const s of sphere) {
    X[0] = L[0] + r * s[0]; X[1] = L[1] + r * s[1]; X[2] = L[2] + r * s[2];
    if (seen(p, X, ho, depth)) return true;
  }
  return false;
}

/** What the line of sight through point (y, z) of the opening meets inside: [point, inward normal]. */
function seenInside(y, z, view, depth) {
  const d = [-view[0], -view[1], -view[2]];
  const tx = depth / view[0];
  const ty = Math.abs(d[1]) < 1e-9 ? Infinity : ((d[1] < 0 ? -HH : HH) - y) / d[1];
  const tz = Math.abs(d[2]) < 1e-9 ? Infinity : ((d[2] < 0 ? -HW : HW) - z) / d[2];
  const t = Math.min(tx, ty, tz);
  const p = [t * d[0], y + t * d[1], z + t * d[2]];
  const n = t === tx ? [1, 0, 0] : t === ty ? [0, -Math.sign(d[1]), 0] : [0, 0, -Math.sign(d[2])];
  return [p, n];
}

function positions(depth, live) {
  const out = [{ L: live, tag: 'dock' }];
  for (const x of [0.07, 0.12, 0.2, 0.35, 0.6, 1.0]) {
    for (const y of [-0.1, 0, 0.08, 0.15, 0.25, 0.4, 0.6, 0.9]) {
      for (const z of [-0.6, -0.3, -0.12, 0, 0.12, 0.3, 0.6]) out.push({ L: [x, y, z], tag: 'front' });
    }
  }
  for (const x of [-0.07, -0.2, -0.4, -0.7]) {
    for (const y of [0.3, 0.45, 0.6, 0.9]) for (const z of [-0.3, 0, 0.3]) out.push({ L: [x, y, z], tag: 'behind' });
  }
  for (const L of [[0, 0, 0], [0.03, 0, 0], [-0.03, 0.02, -0.04], [-depth / 2, 0, 0], [-depth / 2, 0.05, 0.08]]) out.push({ L, tag: 'in' });
  // In front but at a grazing angle, beyond the jambs or above the lintel, close to the wall:
  // the opening's edges hide the light from every inner point.
  for (const x of [0.065, 0.09]) {
    for (const z of [-1.4, -0.9, 0.9, 1.4]) for (const y of [0, 0.08]) out.push({ L: [x, y, z], tag: 'graze' });
    for (const y of [1.4, 2]) out.push({ L: [x, y, 0], tag: 'graze' });
  }
  return out;
}

/**
 * The model alone: every swept light position against every point of the grid.
 * @returns { tally (per position: blindAll, anySighted, mean), violations, pairs, blindPairs, sightedPairs }
 */
export function probeModel(depth, ho, live = [-0.7, 0.6, 0]) {
  const list = positions(depth, live);
  const points = [];
  eachInnerPoint(depth, (p, n) => points.push([p.slice(), n.slice()]), GRID);
  const violations = [];
  let pairs = 0, blindPairs = 0, sightedPairs = 0;
  const tally = list.map(({ L, tag }) => {
    let blindAll = true, anySighted = false;
    for (const [p, n] of points) {
      pairs++;
      const E = direct(p, n, L, ho, depth);
      const blind = !anySeen(p, L, ho, depth, LIGHT_RADIUS + GROW);
      if (!blind) blindAll = false;
      const toL = [L[0] - p[0], L[1] - p[1], L[2] - p[2]], d = Math.hypot(...toL);
      const facing = (n[0] * toL[0] + n[1] * toL[1] + n[2] * toL[2]) / d;
      const sighted = facing > 0.05 && seen(p, L, ho, depth, MARGIN);
      if (blind) { blindPairs++; if (E !== 0) violations.push({ L, p, E, why: 'lit without line of sight' }); }
      if (sighted) { sightedPairs++; anySighted = true; if (!(E > 0)) violations.push({ L, p, E, why: 'dark with the light in sight' }); }
    }
    return { L, tag, blindAll, anySighted, mean: meanDirect(L, ho, depth) };
  });
  // The cavity as a whole: no line of sight anywhere in it, no light in it.
  for (const t of tally) if (t.blindAll && t.mean !== 0) violations.push({ L: t.L, E: t.mean, why: 'cavity lit with no line of sight into it' });
  return { tally, violations, pairs, blindPairs, sightedPairs, points: points.length };
}

/**
 * @param ctx { depth, ho, light (the live light, door frame), drawnPx, lightPx, render(L) -> pixel stats, block, station }
 * @returns a summary; `ok` is the verdict
 */
export function probeDoor(ctx) {
  const { depth, ho } = ctx;
  const t0 = performance.now();
  const { tally, violations, pairs, blindPairs, sightedPairs, points } = probeModel(depth, ho, ctx.light);
  const modelMs = performance.now() - t0;

  // On the GPU: a spread of positions with no line of sight, and of positions that light the cavity.
  const pick = (want, count) => {
    const pool = tally.filter(want);
    return Array.from({ length: Math.min(count, pool.length) }, (_, i) => pool[Math.floor((i * pool.length) / Math.min(count, pool.length))]);
  };
  const blindSet = pick((t) => t.blindAll, 10), litSet = pick((t) => t.anySighted && t.mean > 0.02, 10);
  const gpu = { blind: blindSet.map((t) => ({ L: t.L, tag: t.tag, ...ctx.render(t.L) })), lit: litSet.map((t) => ({ L: t.L, tag: t.tag, mean: +t.mean.toFixed(4), ...ctx.render(t.L) })) };
  // Pixel by pixel, without the bounce (which rightly lights what the light cannot see): whatever
  // is seen through a pixel with no line of sight to the light must have no colour at all, and
  // whatever is seen lit, well inside the light, must be vermilion.
  const classify = (L) => (y, z) => {
    const [p, n] = seenInside(y, z, ctx.view, depth);
    if (!anySeen(p, L, ho, depth, LIGHT_RADIUS + GROW)) return 0;
    const toL = [L[0] - p[0], L[1] - p[1], L[2] - p[2]], d = Math.hypot(...toL);
    const facing = (n[0] * toL[0] + n[1] * toL[1] + n[2] * toL[2]) / d;
    return facing > 0.2 && seen(p, L, ho, depth, MARGIN) && direct(p, n, L, ho, depth) > 0.03 ? 1 : -1;
  };
  const partial = pick((t) => t.anySighted && t.tag !== 'in', 12);
  gpu.pixels = partial.map((t) => { const r = ctx.render(t.L, { bounce: false, classify: classify(t.L) }); return { L: t.L, tag: t.tag, blindPixels: r.blindPixels, blindChroma: r.blindChroma, litPixels: r.litPixels, litNeutral: r.litNeutral }; });
  const dock = tally[0];
  const drawnError = Math.hypot(ctx.drawnPx.x - ctx.lightPx.x, ctx.drawnPx.y - ctx.lightPx.y);
  const summary = {
    block: ctx.block, station: ctx.station, depth, positions: tally.length, points, pairs, blindPairs, sightedPairs,
    blindPositions: tally.filter((t) => t.blindAll).length, litPositions: tally.filter((t) => t.mean > 0).length,
    violations: violations.length, firstViolations: violations.slice(0, 5),
    dock: { L: dock.L.map((v) => +v.toFixed(4)), blind: dock.blindAll, mean: dock.mean },
    gpu: {
      blindPixels: gpu.blind.reduce((s, r) => s + r.pixels, 0), blindChroma: gpu.blind.reduce((s, r) => s + r.chroma, 0),
      litPixels: gpu.lit.reduce((s, r) => s + r.pixels, 0), litChromaMin: Math.min(...gpu.lit.map((r) => r.chroma / Math.max(1, r.pixels))),
      litMaxRG: Math.max(...gpu.lit.map((r) => r.maxRG)),
      // per pixel, bounce off: pixels seen with no line of sight (and their neighbours) / coloured among them; lit pixels / neutral among them
      shadowPixels: gpu.pixels.reduce((s, r) => s + r.blindPixels, 0), shadowChroma: gpu.pixels.reduce((s, r) => s + r.blindChroma, 0),
      sunPixels: gpu.pixels.reduce((s, r) => s + r.litPixels, 0), sunNeutral: gpu.pixels.reduce((s, r) => s + r.litNeutral, 0),
      detail: gpu,
    },
    drawnError, dockError: ctx.dockError,
    modelMs: Math.round(modelMs),
  };
  summary.ok = summary.violations === 0 && gpu.blind.length > 0 && gpu.lit.length > 0 && summary.gpu.blindChroma === 0
    && summary.gpu.shadowPixels > 0 && summary.gpu.shadowChroma === 0 && summary.gpu.sunPixels > 0 && summary.gpu.sunNeutral === 0
    && gpu.blind.every((r) => r.pixels > 20) && gpu.lit.every((r) => r.pixels > 20 && r.chroma > 0) && drawnError < 0.01 && ctx.dockError < 1e-6;
  return summary;
}

// ---- one hue (window.__demo.doorLook) -------------------------------------------------------------
// The one colour must never mix with the grey: red light over bright grey reads as dusty rose, a
// second colour. A pixel is rose when its hue is red, it is neither vermilion nor grey (saturation
// 0.15..0.55) and it is not dark (its brightest channel at least 64/255), on a surface rather than at
// an arris (the antialiased line between a red face and a grey one is two faces, not a colour): its
// 5 x 5 neighbourhood holds within 30/255 in red and in green.
export const ROSE = { satLow: 0.15, satHigh: 0.55, brightMin: 64, edgeRange: 30 };
export function hueSat(r, g, b) {
  const mx = Math.max(r, g, b), mn = Math.min(r, g, b), s = mx ? (mx - mn) / mx : 0;
  let h = 0;
  if (mx !== mn) { if (mx === r) h = ((g - b) / (mx - mn) + 6) % 6; else if (mx === g) h = (b - r) / (mx - mn) + 2; else h = (r - g) / (mx - mn) + 4; h *= 60; }
  return [h, s, mx];
}
/** Rose pixels in an RGBA readback (w x h, bottom-up as GL reads it), sampled every `stride` pixels
 *  (only where `keep(x, y)`, if given); `worst` lists the first few as [r, g, b, saturation, x, y]
 *  (x, y in the readback). */
export function roseIn(pixels, w, h, stride = 2, keep = null) {
  let rose = 0, surface = 0;
  const worst = [];
  for (let y = 2; y < h - 2; y += stride) {
    for (let x = 2; x < w - 2; x += stride) {
      if (keep && !keep(x, y)) continue;
      let r = 0, g = 0, b = 0, rLo = 255, rHi = 0, gLo = 255, gHi = 0;
      for (let dy = -2; dy <= 2; dy++) {
        for (let dx = -2; dx <= 2; dx++) {
          const i = ((y + dy) * w + x + dx) * 4;
          r += pixels[i]; g += pixels[i + 1]; b += pixels[i + 2];
          rLo = Math.min(rLo, pixels[i]); rHi = Math.max(rHi, pixels[i]);
          gLo = Math.min(gLo, pixels[i + 1]); gHi = Math.max(gHi, pixels[i + 1]);
        }
      }
      if (rHi - rLo > ROSE.edgeRange || gHi - gLo > ROSE.edgeRange) continue;
      surface++;
      r /= 25; g /= 25; b /= 25;
      const [hue, s, mx] = hueSat(r, g, b);
      if (mx < ROSE.brightMin || s < ROSE.satLow || s > ROSE.satHigh || !(hue <= 30 || hue >= 340)) continue;
      rose++;
      if (worst.length < 4) worst.push([Math.round(r), Math.round(g), Math.round(b), +s.toFixed(2), x, y]);
    }
  }
  return { rose, surface, worst };
}

// ---- the pool (window.__demo.poolLook) ------------------------------------------------------------
// The light against the stone as the key alone lights it. Readbacks of one frame: as drawn (the light,
// its glare, the dust), the stone alone as lit, and the stone with the light off (no power, no hold,
// nothing through the door), with every pixel's face known from the line of sight (src/frame.js).
// Rays leave the light where it is drawn; each is cut into runs, one per face it crosses (trimmed at
// each end clear of the worn arrises, which catch the light, and of the antialiased edge). On a run:
//   - a face the light does not hold only gains: luminance never below the light-off frame's;
//   - the light's share of the face (lit over unlit, so the stone's own grain and mottle cancel; its
//     red, on a face it holds) has no valley: it may rise to the point nearest the light and fall away,
//     never fall and rise again (a ring, an annulus, a dark rim);
//   - the hue never changes inside a face: a run is vermilion all along, or not at all, and a face
//     the light holds never goes dark (src/hold.js: it holds only what it reaches);
// and the picture as drawn has no rose pixel on the stone (roseIn). Faces the light holds are reported:
// how far their luminance sits below the key's grey (the price of the hue: no pixel can be vermilion
// and as luminous as the lit grey).
export const POOL = { minRun: 8, tolY: 0.004, tolShare: 0.1, smooth: 3, red: 0.55, dark: 24, inset: 3 };
const LIN = Array.from({ length: 256 }, (_, v) => { const c = v / 255; return c <= 0.04045 ? c / 12.92 : ((c + 0.055) / 1.055) ** 2.4; });
const lum = (c) => 0.2126 * LIN[Math.round(c[0])] + 0.7152 * LIN[Math.round(c[1])] + 0.0722 * LIN[Math.round(c[2])];
/**
 * @param px   { seen, on, off }: RGBA readbacks (w x h, bottom-up as GL reads them)
 * @param o    { cx, cy: the light, top-down pixels of the box; reach (px); rays; trim (px); bloom: the light's own
 *             bloom (px); faceAt(x, y) -> face id or -1 }
 */
export function poolRays({ seen, on, off }, w, h, { cx, cy, reach, rays = 120, trim = 4, bloom = 0, faceAt }) {
  const mean = (px, x, y, out) => {
    out[0] = out[1] = out[2] = 0;
    for (let dy = -1; dy <= 1; dy++) for (let dx = -1; dx <= 1; dx++) {
      const i = ((h - 1 - (y + dy)) * w + x + dx) * 4;
      out[0] += px[i]; out[1] += px[i + 1]; out[2] += px[i + 2];
    }
    out[0] /= 9; out[1] /= 9; out[2] /= 9;
    return out;
  };
  const faces = new Int32Array(w * h).fill(-2);
  const face = (x, y) => { const k = y * w + x; if (faces[k] === -2) faces[k] = faceAt(x, y); return faces[k]; };
  // Inside one face, clear of its edges in every direction.
  const inner = (x, y, f) => { const d = POOL.inset; return face(x - d, y) === f && face(x + d, y) === f && face(x, y - d) === f && face(x, y + d) === f; };
  const stats = { rays, samples: 0, runs: 0, held: 0, darker: 0, heldDark: 0, valleys: 0, hueInFace: 0, heldMin: Infinity, worst: [] };
  const note = (why, k, t, extra) => { if (stats.worst.length < 8) stats.worst.push({ why, ray: k, at: t, ...extra }); };
  for (let k = 0; k < rays; k++) {
    const a = (2 * Math.PI * k) / rays, ux = Math.cos(a), uy = -Math.sin(a);
    const line = [];
    for (let t = 0; t <= reach; t++) {
      const x = Math.round(cx + t * ux), y = Math.round(cy + t * uy);
      if (x < POOL.inset + 1 || y < POOL.inset + 1 || x >= w - POOL.inset - 1 || y >= h - POOL.inset - 1) break;
      const f = face(x, y);
      line.push({ t, f, inner: f >= 0 && inner(x, y, f), on: mean(on, x, y, [0, 0, 0]), off: mean(off, x, y, [0, 0, 0]) });
    }
    for (let i = 0; i < line.length;) {
      let j = i;
      while (j < line.length && line[j].f === line[i].f) j++;
      const run = j - i > 2 * trim ? line.slice(i + trim, j - trim).filter((s) => s.inner) : [];
      i = j;
      if (line[i - 1].f < 0 || run.length < POOL.minRun) continue;
      stats.runs++; stats.samples += run.length;
      const hues = run.map((s) => { const [hue, sat, mx] = hueSat(...s.on); return mx < POOL.dark ? 0 : sat >= POOL.red && (hue <= 30 || hue >= 340) ? 1 : -1; });
      const held = hues.includes(1);
      if (held && hues.includes(-1)) { stats.hueInFace++; const m = hues.indexOf(-1); note('the hue changes inside a face', k, run[m].t, { face: run[m].f, on: run[m].on.map(Math.round) }); }
      if (held && hues.includes(0)) { stats.heldDark++; const m = hues.indexOf(0); note('a face the light holds goes dark', k, run[m].t, { face: run[m].f, on: run[m].on.map(Math.round) }); }
      // The light's share: luminance (or, on a face it holds, its red) over the light-off frame's.
      const raw = run.map((s) => (held ? LIN[Math.round(s.on[0])] : lum(s.on)) / Math.max(lum(s.off), 1e-4));
      const share = raw.map((_, m) => { let sum = 0, c = 0; for (let q = Math.max(0, m - POOL.smooth); q <= Math.min(raw.length - 1, m + POOL.smooth); q++) { sum += raw[q]; c++; } return sum / c; });
      if (held) { stats.held++; stats.heldMin = Math.min(stats.heldMin, ...raw); }
      else run.forEach((s) => { if (lum(s.on) < lum(s.off) - POOL.tolY) { stats.darker++; note('darker than with the light off', k, s.t, { face: s.f, on: s.on.map(Math.round), off: s.off.map(Math.round) }); } });
      const pre = [], suf = [];
      for (let m = 0; m < share.length; m++) pre[m] = Math.max(share[m], m ? pre[m - 1] : -Infinity);
      for (let m = share.length - 1; m >= 0; m--) suf[m] = Math.max(share[m], m < share.length - 1 ? suf[m + 1] : -Infinity);
      for (let m = 1; m < share.length - 1; m++) {
        const rim = Math.min(pre[m], suf[m]), depth = rim - share[m];
        if (depth > POOL.tolShare * Math.max(1, rim)) { stats.valleys++; note('a valley in the light', k, run[m].t, { face: run[m].f, depth: +depth.toFixed(3) }); break; }
      }
    }
  }
  // The picture as drawn: no rose on the stone, the light's glare and the dust included (but for the
  // light's own bloom, the lens's, where it lies over the stone right round the light).
  stats.rose = roseIn(seen, w, h, 2, (x, y) => (x - cx) ** 2 + (h - 1 - y - cy) ** 2 > bloom * bloom && face(x, h - 1 - y) >= 0);
  stats.heldMin = Number.isFinite(stats.heldMin) ? +stats.heldMin.toFixed(3) : null;
  return stats;
}
