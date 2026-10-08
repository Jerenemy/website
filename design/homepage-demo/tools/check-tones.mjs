#!/usr/bin/env node
// Tone audit, run through the capture harness: `node tools/check-tones.mjs /path/to/shot.mjs`
// (or HARNESS=...). Exits 1 on any failure.
//
// At eight roll angles (four stations each of ten and of twenty-four works) it shoots the
// settled scene at DPR 2, samples the centre of every visible tread and wall face (the
// window.__demo.facePoints hook), and checks what the paradox needs of the shading:
//   - the three face families keep their fixed order (+x darkest, +z, +y brightest) on every
//     block, and their medians stay apart, at every roll;
//   - on every block the brighter of its two faces is at least RATIO_MIN times the darker in
//     linear light (mist is a smooth screen-space multiplier, so neighbours keep the ratio);
//     the last step of a side is exempt, because the next side's first step stands on its
//     corner and its contact shadow legitimately darkens that wall;
//   - stone beyond the light's reach is strictly neutral (R = G = B within the grain).
import { execFileSync } from 'node:child_process';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { readPng, boxStats } from './png-sample.mjs';
import { SHADING } from '../src/config.js';

const HARNESS = process.argv[2] || process.env.HARNESS;
if (!HARNESS) { console.error('usage: node tools/check-tones.mjs /path/to/shot.mjs (or set HARNESS)'); process.exit(2); }
const ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
const OUT = path.join(ROOT, 'shots/wip/tones');
const DPR = 2, BOX = 5;                  // sample box: (2·BOX+1)² device pixels, averages the grain away
const MEDIAN_GAP_MIN = 15;               // sRGB /255 between family medians
const RATIO_MIN = 1.5;                   // linear; the design ratios are 1.7 (y/z) and 3.4 (z/x)
const SPREAD_MAX = 2;                    // max |R-G|, |G-B| on neutral stone (8-bit rounding)
const POOL_CLEAR_PX = 250;               // CSS px from the light within which the pool is allowed its hue
const CASES = [
  [10, 'diffusion'], [10, 'karchive'], [10, 'zaybot'], [10, 'sonar'],
  [24, 'diffusion'], [24, 'zaybot'], [24, 'reinforcement-learning-2'], [24, 'ear-2'],
];
const lin = (v) => { const c = v / 255; return c <= 0.04045 ? c / 12.92 : ((c + 0.055) / 1.055) ** 2.4; };
const READY = '{"waitFor":"window.__demo && window.__demo.ready"}';
const PROBE = 'JSON.stringify({fp:window.__demo.facePoints(),st:window.__demo.state(),rest:[getComputedStyle(document.documentElement).getPropertyValue(\'--rest-x\'),getComputedStyle(document.documentElement).getPropertyValue(\'--rest-y\')]})';

const failures = [];
const check = (ok, what) => { if (!ok) failures.push(what); };

for (const [n, id] of CASES) {
  const name = `tones-n${n}-${id}`;
  // Present the station (which rolls the monument), then dismiss it so nothing is dimmed.
  const steps = `[${READY},{"move":[60,860]},{"wait":300},{"eval":"window.__demo.goTo('${id}')"},{"wait":2200},{"key":"Escape"},{"wait":900},{"shot":"${name}"},{"eval":"${PROBE}"}]`;
  const log = execFileSync('node', [HARNESS, '--root', ROOT, '--out', OUT, '--dpr', String(DPR), '--query', `skipIntro=1&n=${n}`, '--steps', steps], { encoding: 'utf8' });
  check(/^no console errors/m.test(log), `${name}: harness reported problems`);
  const line = log.split('\n').find((l) => l.startsWith('eval "{'));
  if (!line) { failures.push(`${name}: no probe result`); continue; }
  const { fp, st, rest } = JSON.parse(JSON.parse(line.slice(5)));
  check(st.tilt === 0 && st.phase === 'idle', `${name}: scene not at rest (tilt ${st.tilt}, phase ${st.phase})`);
  const png = readPng(path.join(OUT, name + '.png'));
  const counts = [0, 1, 2].map((k) => fp.filter((f) => f.side === k && f.axis === 0 && f.step >= 0).length);
  const restX = parseFloat(rest[0]), restY = parseFloat(rest[1]);
  const fam = [[], [], []];
  const blocks = new Map();
  for (const f of fp) {
    const travel = f.side, tread = (f.side + 2) % 3;
    if (f.axis === travel) continue;                              // +travel faces are joints or nosings
    if (f.side === 2 && f.step >= counts[2] - 2) continue;        // the near end, partly behind the far start
    if (f.step < 0 && f.axis !== tread) continue;                 // cube walls meet the previous side
    if (Math.hypot(f.x - restX, f.y - restY) < POOL_CLEAR_PX) continue;
    const x = Math.round(f.x * DPR), y = Math.round(f.y * DPR);
    const s = boxStats(png, x - BOX, y - BOX, x + BOX + 1, y + BOX + 1);
    if (!s.n) continue;
    const lum = 0.2126 * s.mean[0] + 0.7152 * s.mean[1] + 0.0722 * s.mean[2];
    fam[f.axis].push(lum);
    check(s.maxSpread <= SPREAD_MAX, `${name}: block ${f.block} +${'xyz'[f.axis]} face is not neutral (spread ${s.maxSpread})`);
    if (!blocks.has(f.block)) blocks.set(f.block, { side: f.side, step: f.step, faces: {} });
    blocks.get(f.block).faces['xyz'[f.axis]] = lum;
  }
  const med = fam.map((l) => { l.sort((a, b) => a - b); return l[Math.floor(l.length / 2)]; });
  check(med[0] + MEDIAN_GAP_MIN <= med[2] && med[2] + MEDIAN_GAP_MIN <= med[1], `${name}: family medians x=${med[0].toFixed(0)} z=${med[2].toFixed(0)} y=${med[1].toFixed(0)} are not x < z < y by ${MEDIAN_GAP_MIN}`);
  let minRatio = Infinity;
  for (const [b, v] of blocks) {
    const { x = -1, y = 1e9, z } = v.faces;
    if (z === undefined || (x < 0 && y > 1e8)) continue;
    check(x < z && z < y, `${name}: block ${b} (side ${v.side}, step ${v.step}) faces out of order x=${x.toFixed(0)} z=${z.toFixed(0)} y=${y.toFixed(0)}`);
    const lastStep = v.step === counts[v.side] - 1;
    const ratio = y < 1e8 ? lin(y) / lin(z) : lin(z) / Math.max(lin(x), 1e-4);
    if (!lastStep) minRatio = Math.min(minRatio, ratio);
    check(lastStep || ratio >= RATIO_MIN, `${name}: block ${b} (side ${v.side}, step ${v.step}) tread/wall ratio ${ratio.toFixed(2)} < ${RATIO_MIN}`);
  }
  console.log(`${name}: medians x=${med[0].toFixed(0)} z=${med[2].toFixed(0)} y=${med[1].toFixed(0)}; ${blocks.size} blocks, min local ratio ${minRatio.toFixed(2)}`);
}

if (failures.length) {
  console.error(`\nFAIL (${failures.length}):`);
  failures.slice(0, 30).forEach((f) => console.error('  ' + f));
  process.exit(1);
}
console.log(`\nPASS: three tones apart at ${CASES.length} roll angles; stone neutral beyond ${POOL_CLEAR_PX} px of the light.`);
