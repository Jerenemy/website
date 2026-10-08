#!/usr/bin/env node
// The input grammar's sharp edges, each found by a review and each checked the way it was
// found (real Chrome, real WebGL, real input events):
//   node tools/check-input.mjs /path/to/shot.mjs   (or HARNESS=...; it borrows the harness's
//   puppeteer and Chrome). Exits 1 on any failure.
//
//   - the rail: hovering a step in the scene never widens its rail anchor over the stone; a
//     click on a neighbouring step presents that step and departs nowhere (1024x768);
//   - the roll: bursts of 2, 6 and 40 forward keys at n = 3, 10, 24 never turn the stone
//     back (lap shifts excluded), and the 40-key burst seats within 1.6 s of the last key;
//   - phones under 700 px tall: OPEN's 44 px target stays 8 px clear of the strip's numeral
//     zone, a tap there presents that tick's work, and the links keep one row at 320 wide;
//   - reduced motion: a real double-click on a step presents that step (the monument has
//     snapped under the second click);
//   - one current mark on the rail after a deep link;
//   - the lock strike answers a real tear made in the scene, not a hand coming to rest or a
//     reach for the interface;
//   - the pointer cannot open the paradox during the arrival;
//   - on a seam step the light leaves through the door only once the seam has shut;
//   - a modified click on a step that is not presented opens its work beside, like the rail.
import { createRequire } from 'node:module';
import { pathToFileURL, fileURLToPath } from 'node:url';
import http from 'node:http';
import fs from 'node:fs';
import path from 'node:path';

const HARNESS = process.argv[2] || process.env.HARNESS;
if (!HARNESS) { console.error('usage: node tools/check-input.mjs /path/to/shot.mjs (or set HARNESS)'); process.exit(2); }
const { default: puppeteer } = await import(pathToFileURL(createRequire(path.resolve(HARNESS)).resolve('puppeteer-core')).href);
const ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
const MIME = { '.html': 'text/html; charset=utf-8', '.js': 'text/javascript; charset=utf-8', '.css': 'text/css; charset=utf-8' };
// The works' links point at a same-origin stub (data.js is rewritten in transit, as in
// tools/check-back.mjs), so a work opened beside commits at once, whatever the live site's latency.
const server = http.createServer((req, res) => {
  let p = decodeURIComponent(new URL(req.url, 'http://x').pathname);
  if (p === '/favicon.ico') { res.writeHead(204); return res.end(); }
  if (p.startsWith('/__work/')) { res.writeHead(200, { 'content-type': 'text/html; charset=utf-8' }); return res.end(`<!doctype html><title>work</title><p>${p}</p>`); }
  if (p.endsWith('/')) p += 'index.html';
  const f = path.join(ROOT, p);
  if (!f.startsWith(ROOT) || !fs.existsSync(f) || fs.statSync(f).isDirectory()) { res.writeHead(404); return res.end(); }
  res.writeHead(200, { 'content-type': MIME[path.extname(f)] || 'application/octet-stream', 'cache-control': 'no-store' });
  if (p === '/data.js') return res.end(fs.readFileSync(f, 'utf8').replaceAll('https://jeremyzay.com/', '/__work/').replaceAll('https://karchive.dad', '/__work/karchive'));
  fs.createReadStream(f).pipe(res);
});
await new Promise((r) => server.listen(0, '127.0.0.1', r));
const BASE = `http://127.0.0.1:${server.address().port}/index.html`;

const failures = [];
const check = (ok, what) => { if (!ok) failures.push(what); return ok; };
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
const browser = await puppeteer.launch({
  executablePath: '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome', headless: true,
  args: ['--enable-gpu', '--use-angle=metal', '--ignore-gpu-blocklist', '--enable-webgl', '--hide-scrollbars', '--mute-audio', '--no-first-run'],
});

/** A fresh page; `stay=1` keeps the door from following links. Returns helpers. */
async function open({ w = 1440, h = 900, dpr = 1, mobile = false, reduced = false, query = 'skipIntro=1&stay=1', hash = '' } = {}) {
  const page = await browser.newPage();
  await page.setViewport({ width: w, height: h, deviceScaleFactor: dpr, isMobile: mobile, hasTouch: mobile });
  if (reduced) await page.emulateMediaFeatures([{ name: 'prefers-reduced-motion', value: 'reduce' }]);
  const problems = [];
  page.on('pageerror', (e) => problems.push(e.message));
  page.on('console', (m) => { if (m.type() === 'error') problems.push(m.text()); });
  await page.goto(`${BASE}?${query}${hash}`, { waitUntil: 'load' });
  const S = () => page.evaluate('window.__demo.state()');
  // settled is stale until a frame has run after an intent: wait a frame's worth first.
  const idle = async () => { await sleep(120); await page.waitForFunction('window.__demo.state().phase === "idle" && window.__demo.state().settled', { timeout: 12000, polling: 30 }); };
  const ready = () => page.waitForFunction('window.__demo && window.__demo.state().phase !== "intro"', { timeout: 15000, polling: 20 });
  const step = async (id) => (await page.evaluate(`window.__demo.locate(${JSON.stringify(id)})`)).step;
  return { page, S, idle, ready, step, problems, close: () => page.close() };
}
/** Run one check; an exception is a failure, not a crash. */
async function scenario(name, fn) {
  const t0 = Date.now();
  try { await fn(); } catch (e) { failures.push(`${name}: ${e.message}`); }
  console.log(`${name}: ${((Date.now() - t0) / 1000).toFixed(1)} s`);
}

// ---- the rail: no invisible box over the stone -----------------------------------------------
await scenario('rail', async () => {
  const d = await open({ w: 1024, h: 768 });
  await d.ready(); await d.page.mouse.move(5, 763); await d.idle();
  await d.page.evaluate("window.__demo.goTo('zaybot')"); await d.idle(); await sleep(300);
  const a = await d.step('zaybot');
  await d.page.mouse.move(a.x, a.y); await sleep(400);
  const widths = await d.page.evaluate("[...document.querySelectorAll('#rail a')].map((a) => Math.round(a.getBoundingClientRect().width))");
  const b = await d.step('asteroids');
  await d.page.mouse.move(b.x, b.y); await sleep(150);
  await d.page.mouse.click(b.x, b.y); await sleep(300);
  const s = await d.S();
  check(widths.every((x) => x === 44), `rail: a step hovered in the scene widened rail anchors to ${JSON.stringify(widths)}`);
  check(s.selected === 'asteroids' && s.door.leaves === 0 && s.door.departing === null, `rail: a click on asteroids' step after resting on zaybot gave selected ${s.selected}, leaves ${s.door.leaves}, departing ${s.door.departing}`);
  check(!d.problems.length, `rail: page problems ${d.problems.join(' | ')}`);
  await d.close();
});

// ---- the roll never turns back against the keys -------------------------------------------------
await scenario('roll', async () => {
  for (const n of [3, 10, 24]) {
    const d = await open({ query: `skipIntro=1&stay=1&n=${n}` });
    await d.ready(); await d.page.mouse.move(1300, 850); await d.idle();
    for (const keys of [2, 6, 40]) {
      await d.page.evaluate('window.__tr = []; window.__run = true; (function f() { window.__tr.push([performance.now(), window.__demo.state().stone]); if (window.__run) requestAnimationFrame(f); })(); 1');
      for (let k = 0; k < keys; k++) { await d.page.keyboard.press('ArrowRight'); await sleep(50); }
      const last = await d.page.evaluate('performance.now()');
      await d.page.waitForFunction('window.__demo.state().phase === "idle" && Math.abs(window.__demo.state().stone - window.__demo.state().position) < 1e-3', { timeout: 8000, polling: 16 });
      const seated = await d.page.evaluate('performance.now()');
      const tr = await d.page.evaluate('window.__run = false; window.__tr');
      let back = 0;
      for (let i = 1; i < tr.length; i++) {
        let dv = tr[i][1] - tr[i - 1][1];
        if (Math.abs(dv) > n / 2) dv -= Math.round(dv / n) * n;   // a lap shift: invisible, not motion
        if (dv < 0) back -= dv;
      }
      check(back < 1e-6, `roll: n=${n}, ${keys} forward keys: the stone turned back ${back.toFixed(4)} stations`);
      if (keys === 40) check(seated - last <= 1700, `roll: n=${n}, 40 keys: seated ${Math.round(seated - last)} ms after the last (want <= 1.6 s, plus a frame of polling)`);
      await sleep(300);
    }
    check(!d.problems.length, `roll n=${n}: page problems ${d.problems.join(' | ')}`);
    await d.close();
  }
});

// ---- short phones: OPEN and the strip ---------------------------------------------------------
await scenario('phones', async () => {
  for (const [w, h] of [[375, 667], [360, 640]]) {
    const d = await open({ w, h, dpr: 2, mobile: true });
    await d.ready(); await sleep(300);
    await d.page.evaluate("window.__demo.goTo('diffusion')"); await d.idle(); await sleep(400);
    const r = await d.page.evaluate(`(() => { const o = document.getElementById('cap-open').getBoundingClientRect();
      const a = [...document.querySelectorAll('#rail a')].map((x) => x.getBoundingClientRect());
      return { openBottom: o.bottom, openHeight: o.height, stripTop: Math.min(...a.map((x) => x.top)), tick5: (a[4].left + a[4].right) / 2 }; })()`);
    check(r.openHeight >= 44 && r.openBottom + 8 <= r.stripTop + 0.5, `phones ${w}x${h}: OPEN (${Math.round(r.openHeight)} px tall) ends at ${Math.round(r.openBottom)}, the strip's numeral zone starts at ${Math.round(r.stripTop)} (want 8 px clear)`);
    await d.page.touchscreen.tap(r.tick5, r.stripTop + 8); await sleep(500);
    const s = await d.S();
    check(s.selected === 'zaychess' && s.door.leaves === 0 && s.door.departing === null, `phones ${w}x${h}: a tap on the numeral zone above tick 5 gave selected ${s.selected}, departing ${s.door.departing}, leaves ${s.door.leaves}`);
    await d.close();
  }
  const d = await open({ w: 320, h: 568, dpr: 2, mobile: true });
  await d.ready(); await sleep(300);
  const r = await d.page.evaluate(`(() => { const l = document.getElementById('links').getBoundingClientRect(); const a = [...document.querySelectorAll('#rail li')].map((x) => x.getBoundingClientRect());
    return { linksHeight: l.height, linksTop: l.top, stripBottom: Math.max(...a.map((x) => x.bottom)) }; })()`);
  check(r.linksHeight <= 40 && r.linksTop >= r.stripBottom, `phones 320x568: the links are ${Math.round(r.linksHeight)} px tall from ${Math.round(r.linksTop)}, the strip ends at ${Math.round(r.stripBottom)} (want one row below it)`);
  await d.close();
});

// ---- reduced motion: a double-click is one click --------------------------------------------------
await scenario('calm double-click', async () => {
  const d = await open({ query: 'stay=1', reduced: true });
  await d.ready(); await d.page.mouse.move(80, 870); await sleep(300);
  const ids = await d.page.evaluate("[...document.querySelectorAll('#rail a')].map((a) => a.dataset.id)");
  const wrong = [];
  for (const id of ids.slice(1)) {
    await d.page.keyboard.press('Escape'); await d.page.keyboard.press('Home'); await sleep(300);
    const p = await d.step(id);
    await d.page.mouse.click(p.x, p.y, { count: 2, delay: 30 }); await sleep(500);
    const s = await d.S();
    if (s.selected !== id || s.door.leaves !== 0) wrong.push([id, s.selected, s.door.leaves]);
  }
  check(!wrong.length, `calm double-click: ${wrong.length} of ${ids.length - 1} steps presented something else or departed: ${JSON.stringify(wrong)}`);
  await d.close();
});

// ---- one current mark after a deep link ----------------------------------------------------------
await scenario('rail mark', async () => {
  const d = await open({ hash: '#zaybot' });
  await d.ready(); await sleep(400);
  const marked = await d.page.evaluate("[...document.querySelectorAll('#rail a[aria-current]')].map((a) => a.dataset.id)");
  const lit = await d.page.evaluate("[...document.querySelectorAll('#rail a .no')].filter((n) => +getComputedStyle(n).opacity > 0.5).length");
  check(marked.length === 1 && marked[0] === 'zaybot' && lit === 1, `rail mark: after a deep link to #zaybot the rail marks ${JSON.stringify(marked)} with ${lit} numerals shown`);
  await d.close();
});

// ---- the lock strike answers a tear made in the scene ---------------------------------------------
await scenario('strike', async () => {
  const d = await open();
  await d.ready(); await sleep(1500);
  const reach = async (from, to, ms) => {   // a hand's minimum-jerk reach at 60 Hz
    const n = Math.max(2, Math.round(ms / 16.67)), t0 = Date.now();
    for (let i = 1; i <= n; i++) {
      const u = i / n, e = u * u * u * (10 - 15 * u + 6 * u * u);
      await d.page.mouse.move(from[0] + (to[0] - from[0]) * e, from[1] + (to[1] - from[1]) * e);
      const wait = t0 + i * 16.67 - Date.now(); if (wait > 0) await sleep(wait);
    }
  };
  const strikes = async (from, to, ms) => {
    await d.page.mouse.move(...from); await sleep(1800);
    await d.page.evaluate('window.__n = 0; window.__last = window.__demo.state().impact.age; window.__run = true; (function f() { const a = window.__demo.state().impact.age; if (a < window.__last) window.__n++; window.__last = a; if (window.__run) requestAnimationFrame(f); })(); 1');
    await reach(from, to, ms); await sleep(1600);
    return d.page.evaluate('window.__run = false; window.__n');
  };
  const nudge = await strikes([200, 150], [350, 180], 300);
  const toRail = await strikes([200, 150], [1380, 420], 700);
  const sweep = await strikes([1250, 150], [250, 820], 500);
  check(nudge === 0 && toRail === 0 && sweep === 1, `strike: a nudge struck ${nudge}, a reach to the rail ${toRail}, a fast sweep through the void ${sweep} (want 0, 0, 1)`);
  await d.close();
});

// ---- the arrival: the pointer cannot open the paradox ----------------------------------------------
await scenario('arrival', async () => {
  const d = await open({ query: 'stay=1' });
  await d.page.evaluate("window.__tr = []; (function f() { if (window.__demo) { const s = window.__demo.state(); window.__tr.push([s.phase, s.tilt]); } if (window.__tr.length < 400) requestAnimationFrame(f); })(); 1");
  const t0 = Date.now();
  while (Date.now() - t0 < 2600) { const a = (Date.now() - t0) / 150; await d.page.mouse.move(720 + 200 * Math.cos(a), 450 + 200 * Math.sin(a)); await sleep(16); }
  const tr = await d.page.evaluate('window.__tr');
  const during = tr.filter((x) => x[0] === 'intro'), after = tr.filter((x) => x[0] !== 'intro');
  check(during.length > 30 && Math.max(...during.map((x) => x[1])) === 0, `arrival: the pointer tilted the arrival (max ${Math.max(...during.map((x) => x[1]))} rad over ${during.length} frames)`);
  check(after.length && Math.max(...after.map((x) => x[1])) > 0.005, 'arrival: after the strike the pointer no longer opens the paradox');
  await d.close();
});

// ---- the door on a seam step waits for the seam to shut ---------------------------------------------
await scenario('seam door', async () => {
  const d = await open();
  await d.ready(); await d.page.mouse.move(60, 860);
  await d.page.evaluate("window.__demo.goTo('asteroids')"); await d.idle(); await sleep(300);
  // an ordinary sweep held over the void (pointer events at 60 Hz), then the second action
  await d.page.evaluate("const c = document.getElementById('stage'); window.__hi = setInterval(() => c.dispatchEvent(new PointerEvent('pointermove', { clientX: 6, clientY: 6, movementX: 0, movementY: 4, pointerType: 'mouse', pointerId: 1, isPrimary: true, bubbles: true })), 16); 1");
  await sleep(1500);
  const r = await d.page.evaluate(`new Promise((res) => { const tr = []; window.__demo.open(); (function f() { const s = window.__demo.state(); tr.push([s.tilt, s.door.departing]); if (tr.length < 40) requestAnimationFrame(f); else res(tr); })(); })`);
  await d.page.evaluate('clearInterval(window.__hi)');
  const startTilt = r[0][0], moving = r.filter((x) => x[1] > 0);
  check(startTilt > 0.02, `seam door: the held sweep tilted only ${startTilt.toFixed(4)} rad`);
  check(moving.length > 0 && moving.every((x) => x[0] < 0.004) && r.filter((x) => x[0] >= 0.004).every((x) => x[1] === 0),
    `seam door: the light left for the door while the seam was torn: ${JSON.stringify(r.slice(0, 14).map((x) => [+x[0].toFixed(4), x[1] === null ? null : +x[1].toFixed(3)]))}`);
  await d.close();
});

// ---- a modified click beside, on any step ----------------------------------------------------------
await scenario('aside', async () => {
  const d = await open();
  await d.ready(); await d.page.mouse.move(80, 870); await d.idle();
  let tabs = 0;
  const count = (t) => { if (t.type() === 'page') { tabs++; t.page().then((p) => p && p.close()).catch(() => {}); } };
  browser.on('targetcreated', count);
  await d.page.setRequestInterception(true);
  d.page.on('request', (r) => (r.url().startsWith('http://127.0.0.1') ? r.continue() : r.abort()));
  const p = await d.step('zaybot');
  await d.page.keyboard.down('Meta'); await d.page.mouse.click(p.x, p.y); await d.page.keyboard.up('Meta'); await sleep(800);
  const s = await d.S();
  browser.off('targetcreated', count);
  check(tabs === 1 && s.selected === null && s.door.leaves === 0, `aside: Cmd+click on a step not presented opened ${tabs} tabs, selected ${s.selected}, leaves ${s.door.leaves} (want one tab, nothing else)`);
  await d.close();
});

await browser.close();
server.close();
if (failures.length) {
  console.error(`\nFAIL (${failures.length}):`);
  failures.forEach((f) => console.error('  ' + f));
  process.exit(1);
}
console.log('\nPASS: no box over the stone; the roll never turns back; OPEN clear of the strip; a calm double-click is one; one mark; strikes only for real tears; no tilt in the arrival; the door waits for the seam; a modified click opens beside.');
