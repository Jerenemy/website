// What the visitor means, turned into state. Every way in (the pointer on a step, the rail's
// anchors, the keyboard, the wheel, a finger) ends in one of these, and each only moves a
// target: the voyage's position, the selection or the focus. Nothing queues and nothing
// locks the visitor out. A presentation stays with the visitor: moving on presents the next
// work; only Escape, the void, the name or the door end it. The door is the one thing that
// is allowed to be a sequence: the light goes through, the scene fades, the link follows,
// once; and should the visitor come back (Back with the page kept alive, or a navigation they
// stopped, noticed by their next click, key or wheel) the scene returns to the work they left.
// Never on a timer: a slow page is still on its way, and the homepage must not come back
// over it or forget where the visitor was.
//
// Two guards against reflexes: during the arrival input only hurries it (a tap on a step is
// kept and replayed the moment the light is struck, so the first gesture still counts; a key
// only hurries), and the second action on a work is accepted only once its presentation is
// readable, so a double-click or a double Enter is one action, not a departure.
import { INTRO, UI } from './config.js';

/**
 * @param parts  see src/frame.js
 * @param frame  the frame, for its effects (mark, depart) and what it alone knows
 */
export function createIntents(parts, frame) {
  const { tribar, seam, stage, voyage, tilt, lifts, idle, ui, state, works, flags } = parts;
  const { pointer, departure } = state;
  const stations = tribar.stepCount;
  let selectedAt = -1e9, replay = null, returnTimer = 0;
  const lastTap = { at: -1e9, x: 0, y: 0 };   // the last tap on the canvas that counted
  // During the arrival any input only hurries it; with the light through the door, nothing moves;
  // and the input that brings the scene back after a stopped navigation only brings it back.
  let resumedAt = -1e9;
  const busy = () => state.phase === 'intro' || departure.t >= 0 || performance.now() - resumedAt < UI.armDelay;
  const armed = () => performance.now() - selectedAt >= UI.armDelay;

  function touch() { idle.touch(); if (state.arrival.time < INTRO.duration) state.arrival.rate = INTRO.hurry; }
  /** A deliberate input (a key, the wheel, a press, a click on the interface) on a page that is
   *  still here after its link was followed: the navigation was stopped or failed, so the scene
   *  comes back for it. A bare pointer move, on the canvas or the rail, does not count. */
  function wake() {
    if (departure.gone && document.visibilityState === 'visible') { returned(false); resumedAt = performance.now(); }
  }
  function select(i, moveFocus = false) {
    if (i === state.selected) return;
    state.selected = i;
    selectedAt = performance.now();
    ui.setSelected(i >= 0 && works[i] ? i : -1, moveFocus);
    ui.cut();
    frame.mark();
  }
  /** Ends the presentation, exactly the same from Escape, the void and the name. Not once
   *  the light is on its way through the door: that sequence runs to its end. */
  function dismiss(viaKeyboard = false) {
    if (state.selected < 0 || departure.t >= 0) return;
    state.selected = -1;
    ui.setSelected(-1, viaKeyboard);
    ui.cut();
    frame.mark();
  }
  /** The visitor moved on (src/voyage.js): the caption follows, and so does a presentation. */
  function moved() {
    ui.setCurrent(voyage.current(), state.calm);
    if (state.selected >= 0 && voyage.current() !== state.selected) select(voyage.current());
    ui.cut();
    frame.mark();
  }
  /** Travel to a station; from inside the index, keyboard focus travels with the light. */
  function go(i) {
    const focused = ui.focusedIndex() >= 0;
    voyage.goTo(i);
    if (focused) ui.anchors[voyage.current()]?.focus({ preventScroll: true });
  }
  function step(dir) {
    if (busy()) return;
    // From inside the index, arrows travel from the focused entry and focus travels along.
    const from = ui.focusedIndex();
    if (from >= 0) go(voyage.wrap(from + dir)); else voyage.stepBy(dir);
  }
  /** Travel to a station without presenting it (the rail used as a scrubber). */
  function travel(i) {
    if (busy() || i < 0 || i >= stations) return;
    voyage.goTo(i);
  }
  function activate(i, viaKeyboard = false) {
    wake(); touch();
    if (busy() || i < 0 || i >= stations) return false;
    select(i, viaKeyboard);
    voyage.goTo(i);
    return true;
  }
  /** The second action: the light goes through the door, then the link is followed.
   *  @param viaKeyboard  a return to this page (without the page kept alive) puts focus back on OPEN */
  function open(viaKeyboard = false) {
    wake(); touch();
    const href = ui.href();
    if (!href || busy() || !armed()) return false;
    departure.href = href;
    departure.byKeyboard = viaKeyboard;
    if (state.calm) leave(); else frame.depart();
    return true;
  }
  /** Follows the link, once. The page may still be here afterwards (Back with the page kept
   *  alive, or a navigation that was stopped): then the scene comes back where it was. */
  function leave() {
    if (departure.gone) return;
    departure.gone = true;
    departure.left = departure.href;
    departure.leaves++;
    ui.leaving(true);
    clearTimeout(returnTimer);
    if (flags.stay) { returnTimer = setTimeout(returned, 400); return; }   // QA: stay, let the scene come back
    try {
      sessionStorage.setItem('tribar:left', works[state.selected]?.id ?? '');
      if (departure.byKeyboard) sessionStorage.setItem('tribar:left-by', 'keyboard'); else sessionStorage.removeItem('tribar:left-by');
    } catch { /* storage may be off */ }
    location.assign(departure.href);
    frame.pause();     // the canvas is already dark: nothing more is drawn while the next page loads
  }
  /**
   * The page is here again after a departure: the scene resumes at the work it was leaving, the
   * door ready for another.
   * @param shown true when the browser showed the kept-alive page again (Back): the return has
   *              happened, so the flag is spent. After a stopped navigation it stays, so a later
   *              Back to this page without the cache still finds the work presented.
   */
  function returned(shown = true) {
    clearTimeout(returnTimer);
    // Nothing to return from: no departure under way and no link followed. (Under reduced motion
    // the link is followed without the light's journey, so departure.t never leaves -1.)
    if (departure.t < 0 && !departure.gone) return;
    if (shown) try { sessionStorage.removeItem('tribar:left'); sessionStorage.removeItem('tribar:left-by'); } catch { /* storage may be off */ }
    departure.t = -1; departure.href = null; departure.gone = false;
    ui.leaving(false);
    frame.mark();
    frame.resume();
  }
  /** The name: the presentation ends and the light returns to the first work. */
  function exit() {
    wake(); touch();
    if (busy()) return;
    dismiss(false);
    go(0);
  }
  function setFocus(i, source) {
    if (i === state.focus && source === state.focusSource) return;
    state.focus = i; state.focusSource = i < 0 ? '' : source;
    ui.setFocus(i, source);
    ui.cursor(i >= 0 && source === 'scene' ? 'pointer' : '');
    if (i < 0 || source !== 'scene') ui.setTag(-1);
    frame.mark();
  }
  /** The step under the pointer: where it is about to be (untilted), else as drawn. A click
   *  (`generous`) that finds only void while the picture is torn open is not yet a dismissal:
   *  a step drawn within a few pixels of it is taken, since the stone is moving under the hand. */
  function pickStation(x, y, generous = false) {
    let hit = stage.pick(x, y, lifts.now, seam);
    if (hit < 0 && stage.tilted) hit = stage.pick(x, y, lifts.now, seam, true);
    if (hit < 0 && generous && stage.tilted) {
      search: for (const r of UI.tornReach) {
        for (let k = 0; k < 8; k++) {
          hit = stage.pick(x + r * Math.cos(k * Math.PI / 4), y + r * Math.sin(k * Math.PI / 4), lifts.now, seam, true);
          if (hit >= 0) break search;
        }
      }
    }
    return hit >= 0 ? tribar.blocks[hit].station : -1;
  }

  /** The handlers src/input.js wants, for the canvas, the wheel and the keyboard. */
  const input = {
    any() { wake(); touch(); },
    scrub(delta, max) { if (!busy()) voyage.scrub(delta, max); },
    settle() { pointer.dragging = false; voyage.settle(); },
    step,
    home() { if (!busy()) go(0); },
    end() { if (!busy()) go(stations - 1); },
    hover(x, y, dx, dy, type, dragging) {
      if (dx || dy) idle.stir();
      pointer.x = x; pointer.y = y; pointer.inside = type !== 'touch'; pointer.dragging = dragging;
      // The arrival's swing is authored to shut exactly at the strike, and the light leaves for
      // the door only once the seam is shut: the pointer opens the paradox only between the two.
      if (!state.calm && !busy()) tilt.push(dx, dy, state.focusSource === 'scene');
    },
    leave() { pointer.inside = false; if (state.focusSource === 'scene') setFocus(-1, ''); },
    tap(x, y, type, aside) {
      pointer.dragging = false;
      if (busy()) { if (state.phase === 'intro') replay = () => input.tap(x, y, type, aside); return; }   // hurries the arrival; counts at the strike
      // The second half of a double-click is the first one's own: whatever now lies under the
      // pointer (under reduced motion the monument has already snapped) it is not a new choice.
      const t = performance.now();
      if (t - lastTap.at < UI.armDelay && Math.hypot(x - lastTap.x, y - lastTap.y) <= 2 * UI.tapSlop) return;
      lastTap.at = t; lastTap.x = x; lastTap.y = y;
      const station = pickStation(x, y, true);
      if (station < 0) dismiss(false);                       // the void dismisses, like Escape
      else if (aside) window.open(works[station].href, '_blank', 'noopener');   // beside, like a modified click on a link
      else if (station !== state.selected) activate(station);
      else open();                                           // armed only once the caption is readable
    },
    enter(e) {
      if (e.target instanceof HTMLAnchorElement || e.target instanceof HTMLButtonElement) return false;   // links and buttons handle their own Enter
      if (state.phase === 'intro') return true;                 // a key only hurries the arrival
      if (state.selected >= 0) { open(true); return true; }  // a double Enter is one Enter until armed
      return activate(voyage.current(), true);
    },
    escape() { dismiss(true); },
  };

  return {
    input, moved, activate, open, exit, travel, setFocus, pickStation, leave, returned,
    /** OPEN is pointed at or focused (false: no longer): the light leans in at the door. */
    peek(on) { if (state.peek !== on) { state.peek = on; frame.mark(); } },
    /** A rail anchor is pointed at or focused (-1: no longer); not while the arrival hides it. */
    focus(i) { if (i >= 0) { touch(); if (busy()) return; } setFocus(i, 'rail'); },
    /** The light is struck: the gesture made during the arrival, if any, counts now. */
    ignited() { const r = replay; replay = null; r?.(); },
  };
}
