// Composition root: builds the parts, wires them together and exposes the test hooks. All
// behaviour lives in the modules: src/state.js holds the shared facts, src/frame.js steps
// everything once per frame and fills the uniforms, src/intents.js turns input into state,
// and src/interface.js is the DOM, which is the whole site without WebGL.
//
// Where the loop opens: at the work named in the URL's hash (written by the interface as
// the visitor moves), or the first. A visitor coming back from a work's page in the same
// session (the flag the departure leaves) skips the arrival and finds that work presented,
// whether or not the browser kept the page alive; a kept-alive page simply resumes. Back (or
// Forward) to this page from anywhere else, not kept alive, also skips the arrival and
// presents again the work that was presented (the history entry's state, src/interface.js).
// A departure by keyboard returns focus to OPEN.
import { INTRO } from './config.js';
import { works, person, flags } from './content.js';
import { buildTribar } from './tribar.js';
import { createSeam } from './seam.js';
import { createStage } from './stage.js';
import { createMonument } from './monument.js';
import { createLantern } from './lantern.js';
import { createDust } from './dust.js';
import { createBackdrop } from './backdrop.js';
import { createInterface } from './interface.js';
import { bindInput } from './input.js';
import { createIntro } from './intro.js';
import { createVoyage } from './voyage.js';
import { createTilt } from './tilt.js';
import { createLifts } from './lifts.js';
import { createIdle } from './idle.js';
import { createState } from './state.js';
import { createFrame } from './frame.js';
import { createIntents } from './intents.js';

const root = document.documentElement;
const reducedMotion = matchMedia('(prefers-reduced-motion: reduce)');

let resolveReady;
const ready = new Promise((resolve) => { resolveReady = resolve; });
let app = null;
const ui = createInterface({
  person, works, scaled: flags.scaled,
  onFocus: (i) => app?.intents.focus(i),
  onActivate: (i, viaKeyboard) => app?.intents.activate(i, viaKeyboard),
  onTravel: (i) => app?.intents.travel(i),
  onOpen: (viaKeyboard) => app?.intents.open(viaKeyboard),
  onPeek: (on) => app?.intents.peek(on),
  onHome: () => app?.intents.exit(),
});
const indexOf = (id) => works.findIndex((w) => w.id === id);
let returningTo = -1, leftByKeyboard = false;
try {
  returningTo = indexOf(sessionStorage.getItem('tribar:left'));
  leftByKeyboard = returningTo >= 0 && sessionStorage.getItem('tribar:left-by') === 'keyboard';
  sessionStorage.removeItem('tribar:left'); sessionStorage.removeItem('tribar:left-by');
} catch { /* storage may be off */ }
let named = '';
try { named = decodeURIComponent(location.hash.slice(1)); } catch { /* a malformed hash names no work */ }
const revisit = performance.getEntriesByType?.('navigation')?.[0]?.type === 'back_forward';
const kept = revisit && history.state && typeof history.state === 'object' ? indexOf(history.state.presented) : -1;
const start = Math.max(0, returningTo >= 0 ? returningTo : indexOf(named));
const represent = returningTo >= 0 ? returningTo : (kept === start ? kept : -1);

function hasWebGL2() {
  try { return !!document.createElement('canvas').getContext('webgl2'); } catch { return false; }
}

/** The scene is gone for good: the DOM index, which was always complete, stands alone. */
function abandonScene() {
  const gone = app;
  app = null;
  gone?.dispose();
  root.classList.remove('gl', 'is-live', 'is-tall', 'is-drawn', 'is-leaving');
  ui.reveal();
  resolveReady(true);
}

function createApp() {
  const canvas = document.getElementById('stage');
  root.classList.add('gl');
  ui.withhold();

  const tribar = buildTribar(works.length);
  const calm = reducedMotion.matches;
  const state = createState({ calm, skipArrival: flags.skipIntro || calm || represent >= 0 || revisit, arrivalDuration: INTRO.duration });
  const stage = createStage(canvas, tribar, { onContextLost: () => frame.contextLost(), onContextRestored: () => frame.contextRestored() });
  const monument = createMonument(tribar), lantern = createLantern(), dust = createDust(), backdrop = createBackdrop();
  stage.scene.add(backdrop.mesh, dust.points, ...lantern.sprites);
  stage.rig.add(...monument.meshes);
  const voyage = createVoyage(tribar, () => intents.moved(), start);
  const parts = {
    canvas, tribar, seam: createSeam(tribar), stage, monument, lantern, dust, backdrop, voyage, ui, state, works, flags,
    intro: createIntro(tribar), tilt: createTilt(), lifts: createLifts(tribar), idle: createIdle(tribar),
  };
  const frame = createFrame(parts, {
    pickStation: (x, y) => intents.pickStation(x, y),
    setFocus: (i, source) => intents.setFocus(i, source),
    leave: () => intents.leave(),
    ready: () => { resolveReady(true); intents.ignited(); },
    abandon: abandonScene,
  });
  const intents = createIntents(parts, frame);
  const unbind = bindInput(canvas, intents.input);
  ui.setCurrent(start, true);
  // Back to a page the browser kept alive: the scene is still here, at the work it was leaving.
  const onPageShow = (e) => { if (e.persisted) intents.returned(); };
  window.addEventListener('pageshow', onPageShow);
  frame.start();
  if (represent >= 0) ready.then(() => intents.activate(represent, leftByKeyboard));
  return { intents, frame, dispose() { unbind(); window.removeEventListener('pageshow', onPageShow); frame.dispose(); } };
}

if (!flags.noGL && works.length && hasWebGL2()) {
  try { app = createApp(); } catch (err) { console.error('the scene could not be built; the list stands', err); abandonScene(); }
}
if (!app) { root.classList.remove('gl'); resolveReady(true); }   // index.html adopted the scene's layout early

// Test hooks.
const qa = () => import('./probe.js');
window.__demo = {
  ready,
  /** Present a work by id. `{ select: false }` only points at it, as hovering would. */
  goTo(id, { select = true } = {}) {
    const i = indexOf(id);
    if (i < 0 || !app) return false;
    if (select) return app.intents.activate(i);
    app.intents.focus(i);
    return true;
  },
  /** The second action on the presented work: through the door, then the link (unless ?stay=1). */
  open: () => (app ? app.intents.open() : false),
  /** CSS-pixel centres of a work's step (null without the scene) and of its rail tick. */
  locate(id) {
    const i = indexOf(id);
    if (i < 0) return null;
    return { step: app ? app.frame.stepPoint(i, { x: 0, y: 0 }) : null, tick: ui.tickPoint(i) };
  },
  state: () => ({
    ...(app ? app.frame.snapshot() : { current: null, selected: null, focus: null, phase: 'static', settled: true, renders: 0, context: 'none' }),
    markup: ui.adopted ? 'adopted' : 'built',
  }),
  facePoints: () => (app ? app.frame.facePoints() : []),
  /** Drop and recover the WebGL context (WEBGL_lose_context); the page must survive both. */
  loseContext: () => { app?.frame.loseContext(); return !!app; },
  restoreContext: () => { app?.frame.restoreContext(); return !!app; },
  bench: (frames) => (app ? app.frame.bench(frames) : 0),
  /** The door's light transport against an independent line-of-sight test, model and GPU (src/probe.js,
   *  fetched on the first call, so it never loads for a visitor). Resolves to the result. */
  doorProbe: async (options) => { const probe = await qa(); return app ? app.frame.doorProbe(options, probe) : { error: 'no scene' }; },
  /** QA: hold the light at a point of the open door's frame ([out of the riser, up, along the wall], beams), or null. */
  doorPin: (at) => (app ? app.frame.doorPin(at) : false),
  /** The door and the step in front as drawn (no sprite): rose pixels, the riser, the tread, the spill (src/frame.js).
   *  Resolves to the result, as doorProbe. */
  doorLook: async (options) => { const probe = await qa(); return app ? app.frame.doorLook(options, probe) : { error: 'no scene' }; },
  /** The light's pool against the stone with the light off, along rays from the light (src/frame.js, src/probe.js). */
  poolLook: async (options) => { const probe = await qa(); return app ? app.frame.poolLook(options, probe) : { error: 'no scene' }; },
};
