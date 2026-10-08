#!/usr/bin/env node
// The light on the stone: `node tools/check-pool.mjs /path/to/shot.mjs` (or HARNESS=...). Exits 1 on
// any failure.
//
// The model (src/hold.js, src/monument.js): the light lights every face by one law, power x cosine x
// falloff of the distance from the light as that face's block sees it, the law it lights the door's
// recess by. A face it holds is lit by it alone, in its colour; every other face keeps the key's grey
// and the light only adds to it. Two parts:
//
// 1. A proof, in node, over every station of every count n = 3..40, at rest and presented, with a
//    neighbour pointed at and with any step lifted by the idle life: every face is wholly held or
//    wholly free (a face half held is part dark), but for a riser standing less than RISER_SEEN
//    above the tread in front (a sliver), and a face is held only where the light reaches all of it.
// 2. In the browser, at DPR 2, at rest and presented at several roll angles, across the seam, at a
//    corner, at n = 3 and 24, on a phone, and with the light leaning in at a door: window.__demo
//    .poolLook (src/frame.js, src/probe.js) reads the frame back as drawn, as lit and with the light
//    off, and walks 120 rays out from the light, face by face. It fails on any sample of a face the
//    light does not hold that is darker than with the light off; any face the light holds that goes
//    dark; any valley in the light's share of a face (a ring, an annulus, a rim); any face whose hue
//    changes inside it; and any rose pixel on the stone as drawn (src/probe.js ROSE, the door's metric:
//    red hue, saturation 0.15..0.55, not dark, on a surface).
import { execFileSync } from 'node:child_process';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { MOTION } from '../src/config.js';
import { buildTribar } from '../src/tribar.js';
import { lightFor } from '../src/door.js';
import { createHold, RISER_SEEN } from '../src/hold.js';

const HARNESS = process.argv[2] || process.env.HARNESS;
if (!HARNESS) { console.error('usage: node tools/check-pool.mjs /path/to/shot.mjs (or set HARNESS)'); process.exit(2); }
const ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
const OUT = path.join(ROOT, 'shots/wip/pool');
const failures = [];
const check = (ok, what) => { if (!ok) failures.push(what); };

// ---- 1. wholly held or wholly free ----------------------------------------------------------------
let poses = 0, faces = 0;
const kinds = new Map();
for (let n = 3; n <= 40; n++) {
  const t = buildTribar(n), hold = createHold(t), N = t.blocks.length;
  const light = new Float64Array(N * 3), own = new Float64Array(N * 3), p = [0, 0, 0];
  for (let j = 0; j < n; j++) {
    for (let i = 0; i < N; i++) { lightFor(t, hold.loopOf[i], j, t.gap, p); light.set(p, i * 3); }
    const presentedBlock = t.stations[j].block, poseList = [];
    for (const presented of [false, true]) {
      const base = new Float64Array(N);
      if (presented) base[presentedBlock] = MOTION.selectLift;
      poseList.push([presented ? 'presented' : 'rest', base]);
      for (const k of [j - 1, j + 1]) {
        if (k < 0 || k >= n) continue;
        const l = base.slice(); l[t.stations[k].block] += MOTION.hoverLift; poseList.push([`station ${k} pointed at`, l]);
      }
      for (let k = 0; k < n; k++) {
        if (k === j || (presented && k === (j + 1) % n)) continue;   // the idle life spares the step in front of a presented one
        const l = base.slice(); l[t.stations[k].block] = MOTION.liftHeight; poseList.push([`station ${k} lifted`, l]);
      }
    }
    for (const [tag, lift] of poseList) {
      hold.solve(light, lift, own);
      poses++;
      const held = [];
      for (let q = 0; q < N * 3; q++) {
        const i = Math.floor(q / 3), b = t.blocks[i];
        const sliver = q % 3 === b.travel && b.step >= 0 && hold.riserHeight(i, lift) < RISER_SEEN;
        faces++;
        check(sliver || own[q] <= 0.02 || own[q] >= 0.98, `n=${n} station ${j} ${tag}: block ${i} +${'xyz'[q % 3]} is ${own[q].toFixed(3)} held`);
        if (own[q] >= 0.98) held.push((b.step < 0 ? 'cube' : i === presentedBlock ? 'its step' : 'the step behind') + (q % 3 === b.tread ? ' tread' : q % 3 === b.travel ? ' riser' : ' wall'));
      }
      if (tag === 'rest') { const key = held.sort().join(' + ') || 'nothing (a step too long to reach end to end)'; kinds.set(key, (kinds.get(key) || 0) + 1); }
    }
  }
}
console.log(`held or free: ${poses} poses, ${faces} faces, n = 3..40; at rest the light holds:`);
for (const [k, v] of kinds) console.log(`  ${k}: ${v} stations`);

// ---- 2. the frame, ray by ray -----------------------------------------------------------------------
const READY = '{"waitFor":"window.__demo && window.__demo.ready"}', PARK = '{"move":[60,860]}';
const LOOK = '{"eval":"window.__demo.poolLook().then((r) => JSON.stringify({ ...r, selected: window.__demo.state().selected, current: window.__demo.state().current }))"}';
const present = (id) => `{"eval":"window.__demo.goTo('${id}')"},{"wait":2800}`;
const rest = (id) => `{"eval":"window.__demo.goTo('${id}')"},{"wait":2200},{"key":"Escape"},{"wait":1500}`;
// [name, query, steps, the work presented (or at rest under the light), harness flags]
const CASES = [
  ['rest, a side\'s first step', 'skipIntro=1', `{"wait":1500}`, [null, 'diffusion']],
  ['rest, a middle step', 'skipIntro=1&stay=1', rest('polydiff'), [null, 'polydiff']],
  ['rest, the third side', 'skipIntro=1&stay=1', rest('sonar'), [null, 'sonar']],
  ['rest, the seam step', 'skipIntro=1&stay=1', rest('asteroids'), [null, 'asteroids']],
  ['presented, a side\'s first step', 'skipIntro=1&stay=1', present('zaychess'), ['zaychess']],
  ['presented, the seam step', 'skipIntro=1&stay=1', present('asteroids'), ['asteroids']],
  ['presented, a corner', 'skipIntro=1&stay=1', present('karchive'), ['karchive']],
  ['leaning in at the door', 'skipIntro=1&stay=1', `${present('zaychess')},{"move":[133,570]},{"wait":900}`, ['zaychess']],
  ['n=3, rest', 'skipIntro=1&n=3', `{"wait":1500}`, [null, 'diffusion']],
  ['n=3, presented', 'skipIntro=1&n=3&stay=1', present('reinforcement-learning'), ['reinforcement-learning']],
  ['n=24, rest', 'skipIntro=1&n=24', `{"wait":1500}`, [null, 'diffusion']],
  ['n=24, presented', 'skipIntro=1&n=24&stay=1', present('zaybot'), ['zaybot']],
  ['phone, rest', 'skipIntro=1', `{"wait":1500}`, [null, 'diffusion'], ['--mobile', '--w', '390', '--h', '844']],
  ['phone, presented', 'skipIntro=1&stay=1', present('zaychess'), ['zaychess'], ['--mobile', '--w', '390', '--h', '844']],
];
let rays = 0, samples = 0, held = 0, heldMin = Infinity;
for (const [name, query, steps, [selected, current = selected], extra = []] of CASES) {
  const all = `[${READY},${extra.length ? '{"wait":300}' : PARK},{"wait":300},${steps},${LOOK}]`;
  const log = execFileSync('node', [HARNESS, '--root', ROOT, '--out', OUT, '--dpr', '2', '--query', query, ...extra, '--steps', all], { encoding: 'utf8' });
  check(/^no console errors/m.test(log), `${name}: harness reported problems`);
  const line = log.split('\n').find((l) => l.startsWith('eval "{'));
  if (!line) { failures.push(`${name}: no poolLook result`); continue; }
  const r = JSON.parse(JSON.parse(line.slice(5)));
  check(r.selected === selected && r.current === current, `${name}: the scene is not where the case puts it (selected ${r.selected}, current ${r.current})`);
  rays += r.rays; samples += r.samples; held += r.held;
  if (r.heldMin !== null) heldMin = Math.min(heldMin, r.heldMin);
  const worst = r.worst.length ? ` (${JSON.stringify(r.worst.slice(0, 2))})` : '';
  check(r.darker === 0, `${name}: ${r.darker} samples darker than with the light off${worst}`);
  check(r.heldDark === 0, `${name}: ${r.heldDark} faces the light holds go dark${worst}`);
  check(r.valleys === 0, `${name}: ${r.valleys} valleys in the light (a ring)${worst}`);
  check(r.hueInFace === 0, `${name}: ${r.hueInFace} faces change hue inside${worst}`);
  check(r.rose.rose === 0, `${name}: ${r.rose.rose} rose pixels on the stone as drawn ${JSON.stringify(r.rose.worst)}`);
  console.log(`${name}: ${r.runs} face runs on ${r.rays} rays (${r.samples} samples), ${r.held} held; darker ${r.darker}, dark ${r.heldDark}, valleys ${r.valleys}, hue ${r.hueInFace}, rose ${r.rose.rose} of ${r.rose.surface}`);
}

if (failures.length) {
  console.error(`\nFAIL (${failures.length}):`);
  failures.slice(0, 30).forEach((f) => console.error('  ' + f));
  process.exit(1);
}
console.log(`\nPASS: every face wholly held or free (${poses} poses); ${CASES.length} frames, ${rays} rays, ${samples} samples: the light only adds where it does not hold, holds only what it reaches, no ring, no hue inside a face, no rose (held faces at least ${(heldMin * 100).toFixed(0)}% of the grey's luminance in their red).`);
