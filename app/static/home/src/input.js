// Every way in: wheel / trackpad, pointer (mouse, pen, touch), keyboard. Nothing here
// decides what happens; it only translates gestures into the handful of intents below.
//
// Wheel events do not say what sent them, so they are classified by their shape. A notched
// mouse sends large, isolated, equal deltas; a trackpad a stream that starts small and, in a
// fling, decays. A lone large delta is therefore HELD for a moment: if nothing follows it
// was a notch (one station); if a follow-up arrives it was the head of a stream, and the
// stream scrubs the light in proportion. A stream of equal large deltas is a wheel being
// spun, one station each. Equal deltas closer together than a detent can repeat are either a
// wheel spun fast or a trackpad flick whose first deltas happen to be equal (frame-synced,
// 8-17 ms apart), and only how the run ends tells them apart: the run is held, and if it
// falls silent still equal it was a wheel (one station per detent); if it breaks into
// unequal deltas, the decay of a fling, it was a stream from its first delta. Once a stream
// is a stream it stays one until it falls silent.
import { MOTION, UI } from './config.js';

/**
 * @param handlers { scrub(stations, max), settle(), step(dir), home(), end(), hover(x, y, dx, dy, type, dragging),
 *                   leave(), tap(x, y, type, aside), enter(e), escape(), any() }
 *                 aside: the tap carried a modifier or the middle button: open beside, not through the door
 */
export function bindInput(canvas, handlers) {
  const disposers = [];
  const on = (target, type, fn, opts) => { target.addEventListener(type, fn, opts); disposers.push(() => target.removeEventListener(type, fn, opts)); };

  const wheel = { last: -1e9, lastSize: 0, stream: false, notching: false, held: null, timer: 0 };
  const notch = (deltaY, count = 1) => { wheel.notching = true; for (let k = 0; k < count; k++) handlers.step(Math.sign(deltaY)); };
  const scrub = (deltaY) => { wheel.stream = true; handlers.scrub(deltaY / MOTION.wheelPerStation, MOTION.wheelGestureMax); };
  const releaseHold = () => { clearTimeout(wheel.timer); const h = wheel.held; wheel.held = null; return h; };
  /** Hold a large delta (or a run of equal ones) until a follow-up or silence says what it was. */
  const hold = (h) => {
    clearTimeout(wheel.timer);
    wheel.held = h;
    wheel.timer = setTimeout(() => { const r = releaseHold(); if (r) notch(r.deltaY, r.count); }, MOTION.wheelNotchHold * 1000);
  };
  on(window, 'wheel', (e) => {
    if (e.ctrlKey) return;                                   // pinch-zoom belongs to the browser
    if (Math.abs(e.deltaX) > Math.abs(e.deltaY)) return;     // so do horizontal swipes (history)
    handlers.any();
    const size = Math.abs(e.deltaY), gap = (e.timeStamp - wheel.last) / 1000;
    wheel.last = e.timeStamp;
    if (gap >= MOTION.wheelStreamGap) wheel.stream = wheel.notching = false;   // silence: a new gesture
    if (e.deltaMode !== 0) { notch(e.deltaY); }                // lines or pages: a notched device, said so
    else if (wheel.held) {
      // A follow-up to a held delta: equal and large, detents if they are a detent apart, and
      // a run still to be decided if they come faster; anything else, a stream from the start.
      const held = wheel.held;
      if (size >= MOTION.wheelNotchMin && e.deltaY === held.deltaY && gap < MOTION.wheelNotchGap) { held.count++; hold(held); }
      else if (size >= MOTION.wheelNotchMin && size === held.size && gap >= MOTION.wheelNotchGap) { releaseHold(); notch(held.deltaY, held.count); notch(e.deltaY); }
      else { releaseHold(); scrub(held.deltaY * held.count); scrub(e.deltaY); }
    }
    else if (wheel.notching && size >= MOTION.wheelNotchMin && size === wheel.lastSize && gap >= MOTION.wheelNotchGap) notch(e.deltaY);
    else if (wheel.stream) scrub(e.deltaY);
    else if (size >= MOTION.wheelNotchMin) hold({ deltaY: e.deltaY, size, count: 1 });
    else scrub(e.deltaY);
    wheel.lastSize = size;
  }, { passive: true });

  let drag = null;
  const aside = (e) => e.metaKey || e.ctrlKey || e.shiftKey || e.altKey || e.button === 1;
  on(canvas, 'pointerdown', (e) => {
    if (e.button !== 0) return;
    handlers.any();
    drag = { id: e.pointerId, x0: e.clientX, y0: e.clientY, x: e.clientX, y: e.clientY, moved: false, axis: 0, type: e.pointerType };
    canvas.setPointerCapture(e.pointerId);
  });
  on(canvas, 'pointermove', (e) => {
    const dx = e.movementX ?? 0, dy = e.movementY ?? 0;
    if (drag && drag.id === e.pointerId) {
      const ddx = e.clientX - drag.x, ddy = e.clientY - drag.y;
      if (!drag.moved && Math.hypot(e.clientX - drag.x0, e.clientY - drag.y0) > UI.tapSlop) {
        drag.moved = true;
        drag.axis = Math.abs(e.clientX - drag.x0) > Math.abs(e.clientY - drag.y0) ? 0 : 1;
      }
      if (drag.moved) {
        // A finger moves exactly one station per swipe, however far it travels; a mouse drag
        // scrubs like a trackpad.
        const along = -(drag.axis === 0 ? ddx : ddy) / MOTION.dragPerStation;
        handlers.scrub(along, drag.type === 'touch' ? MOTION.swipeMax : MOTION.wheelGestureMax);
      }
      handlers.hover(e.clientX, e.clientY, ddx, ddy, e.pointerType, true);
      drag.x = e.clientX; drag.y = e.clientY;
    } else {
      handlers.hover(e.clientX, e.clientY, dx, dy, e.pointerType, false);
    }
  });
  const end = (e) => {
    if (!drag || drag.id !== e.pointerId) return;
    const d = drag; drag = null;
    if (canvas.hasPointerCapture(e.pointerId)) canvas.releasePointerCapture(e.pointerId);
    if (e.type === 'pointercancel' || d.moved) handlers.settle();
    else handlers.tap(e.clientX, e.clientY, e.pointerType, aside(e));
    if (e.pointerType !== 'mouse') handlers.leave();
  };
  on(canvas, 'pointerup', end);
  on(canvas, 'pointercancel', end);
  on(canvas, 'pointerleave', (e) => { if (!drag) handlers.leave(e); });
  // The middle button never starts a drag; its click opens beside, like a middle-click on a link.
  on(canvas, 'auxclick', (e) => { if (e.button === 1) { handlers.any(); handlers.tap(e.clientX, e.clientY, 'mouse', true); } });

  on(window, 'keydown', (e) => {
    if (e.metaKey || e.ctrlKey || e.altKey) return;
    switch (e.key) {
      case 'ArrowRight': case 'ArrowDown': case 'PageDown': case 'j': handlers.any(); handlers.step(1); e.preventDefault(); break;
      case 'ArrowLeft': case 'ArrowUp': case 'PageUp': case 'k': handlers.any(); handlers.step(-1); e.preventDefault(); break;
      case 'Home': handlers.any(); handlers.home(); e.preventDefault(); break;
      case 'End': handlers.any(); handlers.end(); e.preventDefault(); break;
      case 'Enter': handlers.any(); if (handlers.enter(e)) e.preventDefault(); break;
      case 'Escape': handlers.any(); handlers.escape(); break;
      default: break;
    }
  });

  return () => { disposers.forEach((off) => off()); clearTimeout(wheel.timer); };
}
