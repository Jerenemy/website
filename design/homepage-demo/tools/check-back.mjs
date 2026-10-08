#!/usr/bin/env node
// Back from a work, with the browser's back/forward cache on and off:
//   node tools/check-back.mjs /path/to/shot.mjs   (or HARNESS=...; it borrows the harness's
//   puppeteer and Chrome). Exits 1 on any failure.
//
// Serves the demo with every work's link pointed at a same-origin stub page (data.js is
// rewritten in transit; nothing in the demo knows), opens a work through the door with a
// real click on OPEN, presses Back, and checks:
//   - one departure is one history entry and one request for the work's page;
//   - Back lands on the homepage at the work that was left, still presented, and it does not
//     depart again (the URL stays put and the work page is not requested a second time);
//   - kept alive (bfcache), the page is restored as it was (pageshow persisted) with the
//     departure reset and the canvas visible; not kept, a cold load that skips the arrival;
//   - the scene takes input afterwards (ArrowRight moves the presentation on), and a second
//     Back leaves the site instead of returning to the work;
//   - the rail marks one work as current, the one returned to (the server marks work 01);
//   - a navigation the visitor stops (the work's page held, then the browser's Stop): the page
//     stays dark, with no timer bringing it back over a page that may still be loading, until
//     the next deliberate input, which only brings the scene back (the work still presented,
//     the return flag kept); a bare pointer move, over the canvas or along the rail, does not;
//   - under reduced motion (the link is followed at once, without the light's journey) the same
//     two returns: Back with the page kept alive, and a stopped navigation.
// The work page is served at once, except in the stopped journeys.
import { createRequire } from 'node:module';
import { pathToFileURL, fileURLToPath } from 'node:url';
import http from 'node:http';
import fs from 'node:fs';
import path from 'node:path';

const HARNESS = process.argv[2] || process.env.HARNESS;
if (!HARNESS) { console.error('usage: node tools/check-back.mjs /path/to/shot.mjs (or set HARNESS)'); process.exit(2); }
const { default: puppeteer } = await import(pathToFileURL(createRequire(path.resolve(HARNESS)).resolve('puppeteer-core')).href);
const ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
const OUT = path.join(ROOT, 'shots/wip/back');
fs.mkdirSync(OUT, { recursive: true });
const WORK = 'zaychess', NEXT = 'zaybot';
const MIME = { '.html': 'text/html; charset=utf-8', '.js': 'text/javascript; charset=utf-8', '.css': 'text/css; charset=utf-8' };

// No Cache-Control: no-store on the document, or Chrome would never keep the page alive.
const hits = [];
let holdWork = false;   // the stopped journey: the work's page never answers
const server = http.createServer((req, res) => {
  let p = decodeURIComponent(new URL(req.url, 'http://x').pathname);
  if (p === '/favicon.ico') { res.writeHead(204); return res.end(); }
  if (p.startsWith('/__work/')) {
    hits.push(p);
    if (holdWork) return;
    res.writeHead(200, { 'content-type': 'text/html; charset=utf-8' });
    return res.end(`<!doctype html><title>work</title><p>${p}</p>`);
  }
  if (p.endsWith('/')) p += 'index.html';
  const f = path.join(ROOT, p);
  if (!f.startsWith(ROOT) || !fs.existsSync(f) || fs.statSync(f).isDirectory()) { res.writeHead(404); return res.end(); }
  res.writeHead(200, { 'content-type': MIME[path.extname(f)] || 'application/octet-stream' });
  if (p === '/data.js') return res.end(fs.readFileSync(f, 'utf8').replaceAll('https://jeremyzay.com/', '/__work/'));
  fs.createReadStream(f).pipe(res);
});
await new Promise((r) => server.listen(0, '127.0.0.1', r));
const BASE = `http://127.0.0.1:${server.address().port}`;

const failures = [];
const check = (ok, what) => { if (!ok) failures.push(what); };
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
const STATE = `(() => { const s = window.__demo.state(); return { current: s.current, selected: s.selected, phase: s.phase, departing: s.door.departing, leaves: s.door.leaves, arrival: s.arrival,
  leaving: document.documentElement.classList.contains('is-leaving'), stage: +getComputedStyle(document.getElementById('stage')).opacity,
  nav: performance.getEntriesByType('navigation')[0].type, shows: window.__shows || [],
  marked: [...document.querySelectorAll('#rail a[aria-current]')].map((a) => a.dataset.id) }; })()`;

async function journey(mode, { calm = false } = {}) {
  hits.length = 0;
  const browser = await puppeteer.launch({
    executablePath: '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome',
    headless: true,
    args: ['--enable-gpu', '--use-angle=metal', '--ignore-gpu-blocklist', '--enable-webgl', '--hide-scrollbars', '--mute-audio', '--no-first-run',
      '--window-size=1440,900', ...(mode === 'bfcache' ? [] : ['--disable-features=BackForwardCache'])],
  });
  const problems = [];
  try {
    const page = await browser.newPage();
    await page.setViewport({ width: 1440, height: 900 });
    if (calm) await page.emulateMediaFeatures([{ name: 'prefers-reduced-motion', value: 'reduce' }]);
    page.on('pageerror', (e) => problems.push(e.message));
    page.on('console', (m) => { if (m.type() === 'error' || m.type() === 'warning') problems.push(m.text()); });
    await page.evaluateOnNewDocument(() => addEventListener('pageshow', (e) => { window.__shows = (window.__shows || []).concat(e.persisted); }));
    const navs = [];
    page.on('framenavigated', (f) => { if (f === page.mainFrame()) navs.push(new URL(f.url()).pathname); });

    // A cold arrival, then present the work with the scene's own hook and wait for it to seat.
    await page.goto(`${BASE}/index.html`, { waitUntil: 'load' });
    await page.waitForFunction('window.__demo && window.__demo.state().phase === "idle"', { timeout: 10000 });
    await page.mouse.move(60, 860);
    await page.evaluate(`window.__demo.goTo('${WORK}')`);
    await page.waitForFunction('window.__demo.state().phase === "idle" && window.__demo.state().settled', { timeout: 10000 });
    await sleep(400);   // the hash is written once the changes stop
    const before = await page.evaluate('[history.length, location.hash]');

    // Through the door with a real click on OPEN, and wait on the work's page.
    const open = await page.evaluate("(r => [r.left + r.width / 2, r.top + r.height / 2])(document.getElementById('cap-open').getBoundingClientRect())");
    await page.mouse.click(open[0], open[1]);
    await page.waitForFunction(`location.pathname === '/__work/${WORK}'`, { timeout: 5000 });
    await sleep(600);
    const away = await page.evaluate('history.length');
    const hitsAway = hits.length;

    // Back, and give a second departure every chance to happen.
    await page.goBack({ waitUntil: 'load', timeout: 8000 });
    await page.waitForFunction('window.__demo && window.__demo.state().phase !== "intro"', { timeout: 8000 });
    await sleep(1500);
    const back = await page.evaluate(`[location.pathname, location.hash, history.length, ${STATE}]`);
    await page.screenshot({ path: path.join(OUT, `back-${mode}.png`) });

    // Input is taken: the presentation moves on with the light.
    await page.keyboard.press('ArrowRight');
    await page.waitForFunction('window.__demo.state().phase === "idle" && window.__demo.state().settled', { timeout: 8000 });
    const moved = await page.evaluate('[window.__demo.state().current, window.__demo.state().selected, location.pathname]');

    // A second Back leaves the site: there is no second entry for the work.
    await page.goBack({ waitUntil: 'load', timeout: 8000 }).catch(() => null);
    await sleep(300);
    const second = page.url();

    const [path0, hash0, len0, s] = back;
    const tag = `${mode}${calm ? ' (reduced motion)' : ''}:`;
    check(before[1] === `#${WORK}` && hash0 === `#${WORK}`, `${tag} the hash names the work before (${before[1]}) and after Back (${hash0})`);
    check(away === before[0] + 1, `${tag} one departure pushed ${away - before[0]} history entries (${before[0]} -> ${away})`);
    check(hitsAway === 1, `${tag} the work page was requested ${hitsAway} times on one departure`);
    check(path0 === '/index.html' && len0 === away, `${tag} after Back the page is ${path0} with history.length ${len0} (want /index.html, ${away})`);
    check(hits.length === 1, `${tag} the work page was requested ${hits.length} times in all: Back departed again`);
    check(s.current === WORK && s.selected === WORK, `${tag} after Back current ${s.current}, selected ${s.selected} (want ${WORK} presented)`);
    check(s.marked.length === 1 && s.marked[0] === WORK, `${tag} after Back the rail marks ${JSON.stringify(s.marked)} as current (want only ${WORK})`);
    check(s.departing === null && !s.leaving && s.stage === 1 && s.phase === 'idle', `${tag} after Back departing ${s.departing}, is-leaving ${s.leaving}, canvas opacity ${s.stage}, phase ${s.phase}`);
    if (mode === 'bfcache') check(s.shows.length === 2 && s.shows[1] === true && s.leaves === 1, `${tag} not restored from the back/forward cache (pageshow ${JSON.stringify(s.shows)}, leaves ${s.leaves})`);
    else check(s.nav === 'back_forward' && s.shows.length === 1 && s.leaves === 0 && s.arrival === 2.6, `${tag} not a cold return that skips the arrival (nav ${s.nav}, pageshow ${JSON.stringify(s.shows)}, arrival ${s.arrival})`);
    check(moved[0] === NEXT && moved[1] === NEXT && moved[2] === '/index.html', `${tag} ArrowRight after Back gave ${JSON.stringify(moved)} (want ${NEXT} presented)`);
    check(!second.includes('/__work/'), `${tag} a second Back returned to the work (${second})`);
    check(!problems.length, `${tag} page problems: ${problems.join(' | ')}`);
    console.log(`${tag} history ${before[0]} -> ${away} -> ${len0}, work requested ${hits.length}x, navigations ${JSON.stringify(navs)}, after Back ${JSON.stringify(s)}, then ${JSON.stringify(moved)}, second Back ${second}`);
  } catch (e) {
    failures.push(`${mode}${calm ? ' (reduced motion)' : ''}: ${e.message}`);
  } finally {
    await browser.close();
  }
}

/** The visitor stops the navigation: the work's page is held and loading is stopped. While a
 *  navigation is pending the page cannot be evaluated, so it reports itself to the console. */
async function stopped({ calm = false } = {}) {
  hits.length = 0; holdWork = true;
  const browser = await puppeteer.launch({
    executablePath: '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome', headless: true,
    args: ['--enable-gpu', '--use-angle=metal', '--ignore-gpu-blocklist', '--enable-webgl', '--hide-scrollbars', '--mute-audio', '--no-first-run', '--window-size=1440,900'],
  });
  const tag = calm ? 'stopped (reduced motion):' : 'stopped:';
  try {
    const page = await browser.newPage();
    await page.setViewport({ width: 1440, height: 900 });
    if (calm) await page.emulateMediaFeatures([{ name: 'prefers-reduced-motion', value: 'reduce' }]);
    let last = null;
    page.on('console', (m) => { if (m.text().startsWith('{"leaving"')) last = JSON.parse(m.text()); });
    await page.goto(`${BASE}/index.html?skipIntro=1`, { waitUntil: 'load' });
    await page.waitForFunction('window.__demo && window.__demo.state().phase === "idle"', { timeout: 10000 });
    await page.mouse.move(60, 860);
    await page.evaluate(`window.__demo.goTo('${WORK}')`);
    await sleep(150);   // settled is stale until the next frame has run
    await page.waitForFunction('window.__demo.state().phase === "idle" && window.__demo.state().settled', { timeout: 10000 });
    await sleep(400);
    await page.evaluate(`setInterval(() => { const s = window.__demo.state(); console.log(JSON.stringify({ leaving: document.documentElement.classList.contains('is-leaving'), stage: +getComputedStyle(document.getElementById('stage')).opacity, selected: s.selected, departing: s.door.departing, leaves: s.door.leaves, flag: sessionStorage.getItem('tribar:left') })); }, 200); 1`);
    const open = await page.evaluate("(r => [r.left + r.width / 2, r.top + r.height / 2])(document.getElementById('cap-open').getBoundingClientRect())");
    await page.mouse.click(open[0], open[1]);
    await sleep(1500);
    const cdp = await page.createCDPSession();
    await cdp.send('Page.stopLoading');
    await sleep(6000);                       // longer than any timer the old return used (5 s)
    const dark = last;
    await page.mouse.move(700, 300); await page.mouse.move(1378, 420, { steps: 8 }); await page.mouse.move(1378, 480, { steps: 4 }); await sleep(500);
    const moved = last;   // over the canvas, then along the (invisible) rail
    await page.mouse.click(1250, 820); await sleep(700);
    const resumed = last;
    check(hits.length === 1, `${tag} the work page was requested ${hits.length} times`);
    check(dark && dark.leaving && dark.stage === 0 && dark.leaves === 1, `${tag} 6 s after the stop the page is not dark and waiting: ${JSON.stringify(dark)}`);
    check(moved && moved.leaving, `${tag} a bare pointer move brought the scene back: ${JSON.stringify(moved)}`);
    check(resumed && !resumed.leaving && resumed.stage === 1 && resumed.selected === WORK && resumed.departing === null && resumed.flag === WORK,
      `${tag} the first click did not just bring the scene back with ${WORK} presented and the return flag kept: ${JSON.stringify(resumed)}`);
    console.log(`${tag} 6 s after Stop ${JSON.stringify(dark)}; after a pointer move ${JSON.stringify(moved)}; after a click ${JSON.stringify(resumed)}`);
  } catch (e) {
    failures.push(`${tag} ${e.message}`);
  } finally {
    holdWork = false;
    await browser.close();
  }
}

await journey('bfcache');
await journey('nocache');
await stopped();
await journey('bfcache', { calm: true });
await stopped({ calm: true });
server.close();
if (failures.length) {
  console.error(`\nFAIL (${failures.length}):`);
  failures.forEach((f) => console.error('  ' + f));
  process.exit(1);
}
console.log('\nPASS: one entry per departure; Back returns to the work left, kept alive or cold, marked once on the rail, and never departs again; a stopped navigation waits for the visitor; both returns also under reduced motion.');
