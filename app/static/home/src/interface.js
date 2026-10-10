// The semantic layer. Everything a visitor can reach in the scene is a real anchor here
// first; the canvas is a second way of pointing at the same anchors. The markup is the
// server's: index.html (in production the Flask template, from the same data) carries the
// name, the rail, the caption and the links, and this module ADOPTS it, binding behaviour
// to what is there; only when the rail is missing or does not match the works (the ?n=
// scale test) is it built here, from the same data (src/content.js). Without JavaScript or
// WebGL that markup, styled as a list, is the whole site.
//
// The rail is one pointer target, not many: wherever the pointer is on it the nearest tick
// wins, so a hit row is never under 24 px however close the ticks are (they overlap then),
// a finger can scrub along the portrait strip, and a tap between two ticks lands on the
// nearer. Keyboard focus is per anchor, as always.
//
// Assistive technology hears normal case: the visible uppercase is CSS on aria-hidden spans,
// each anchor's accessible name is its visually hidden "Title, Kind, line", and one live
// region in the caption says where the visitor is and what the second action does.
//
// The caption is never blank: its number and title live on two stacked layers that
// cross-fade on every station change, and while changes come faster than a swap (a key
// held down) the visible layer keeps the last text until the next swap is due; the rail's
// numeral changes through the same gate, so the two never name different stations.
//
// The station is kept in the URL's hash (replaced, never pushed), so a reload or a return
// without the page kept alive lands where the visitor was. Every DOM write of the scene
// (cursor, the canvas classes, the departure) goes through here.
import { UI, MOTION } from './config.js';

const pad2 = (n) => String(n).padStart(2, '0');
const KIND = { about: 'About', research: 'Research', engineering: 'Engineering', product: 'Product', play: 'Play' };
const kindLabel = (k) => KIND[k] ?? (k ? k[0].toUpperCase() + k.slice(1) : '');
const reduced = matchMedia('(prefers-reduced-motion: reduce)');

/**
 * @param scaled                       the ?n= test is on: the server's rail is expected not to match
 * @param onFocus(i)                   a work is pointed at (-1: none)
 * @param onActivate(i, viaKeyboard)   present a work
 * @param onTravel(i)                  go to a work without presenting it (the rail scrubbed)
 * @param onOpen(viaKeyboard)          follow the presented work's link, through the door
 * @param onPeek(on)                   OPEN is pointed at or focused (false: no longer)
 * @param onHome()                     the name: dismiss and return to the first station
 */
export function createInterface({ person, works, scaled, onFocus, onActivate, onTravel, onOpen, onPeek = () => {}, onHome }) {
  const $ = (id) => document.getElementById(id);
  const root = document.documentElement;
  const canvas = $('stage');
  const masthead = $('masthead'), rail = $('rail'), links = $('links'), caption = $('caption'), head = $('head');
  const themes = $('themes');   // the theme switcher (templates/_themes.html), when the page has one
  const soundToggle = $('sound');   // the speaker (src/sound.js), when the page has one
  const leader = $('leader'), dock = $('dock'), tag = $('tag'), tagNo = $('tag-no'), tagTitle = $('tag-title');
  const layers = [$('cap-a'), $('cap-b')].map((el) => ({ el, no: el.querySelector('.no'), title: el.querySelector('.title') }));
  const detail = $('detail'), capKind = $('cap-kind'), capLine = $('cap-line'), capOpen = $('cap-open'), announcer = $('announce');
  const home = $('home');
  const n = works.length;
  const aside = (e) => e.metaKey || e.ctrlKey || e.shiftKey || e.altKey || e.button !== 0;
  const live = () => root.classList.contains('gl');   // with the scene; otherwise every anchor is a plain link
  const tall = () => root.classList.contains('is-tall');

  // ---- the markup: adopt it, or build the same ----------------------------------------------
  const el = (tagName, className, text) => {
    const node = document.createElement(tagName);
    if (className) node.className = className;
    if (text != null) node.textContent = text;
    return node;
  };
  function anchorFor(work, i) {
    const a = el('a');
    a.href = work.href; a.dataset.index = String(i); a.dataset.id = work.id;
    const label = el('span', 'label'); label.setAttribute('aria-hidden', 'true');
    label.append(el('span', 'no', pad2(i + 1)), el('span', 't', work.title));
    a.append(label, el('span', 'sr', `${work.title}, ${kindLabel(work.kind)}, `), el('span', 'line', work.line));
    return a;
  }
  let anchors = [...rail.querySelectorAll('a[data-index]')];
  // Adopted only when it is the contract: every work, in order, each with its spoken name.
  const adopted = anchors.length === n && anchors.every((a, i) => a.dataset.id === works[i].id && a.querySelector('.sr') && a.querySelector('.line'));
  if (!adopted) {
    if (anchors.length && !scaled) console.warn('rail rebuilt: the server markup differs from the works data');   // drift, made visible in development
    rail.replaceChildren(...works.map((w, i) => { const li = el('li'); li.append(anchorFor(w, i)); return li; }));
    anchors = [...rail.querySelectorAll('a[data-index]')];
  }
  // The stylesheet mirrors three timings; they are published from the one place they are set.
  root.style.setProperty('--door-fade', `${MOTION.doorFade}s`);
  root.style.setProperty('--detail-dip', `${UI.detailDip}ms`);
  root.style.setProperty('--cap-fade', `${UI.capFade}ms`);
  if (!links.querySelector('a')) {
    links.replaceChildren(...person.links.map((l) => {
      const li = el('li'), a = el('a', null, l.label);
      a.href = l.href; a.rel = 'noopener'; a.setAttribute('aria-label', l.label);
      li.append(a);
      return li;
    }));
  }
  if (!home.textContent) home.textContent = person.name;

  home.addEventListener('click', (e) => {
    if (aside(e) || !live()) return;    // a modified click, or the plain index: a link
    e.preventDefault();
    onHome();
  });
  capOpen.addEventListener('click', (e) => {
    if (aside(e)) return;
    e.preventDefault();
    onOpen(e.detail === 0);   // detail 0: Enter on OPEN
  });
  // Pointing at OPEN, or reaching it by keyboard, shows the way in: the light leans in at the door.
  capOpen.addEventListener('pointerenter', (e) => { if (e.pointerType !== 'touch') onPeek(true); });
  capOpen.addEventListener('pointerleave', () => onPeek(false));
  capOpen.addEventListener('focus', () => { if (capOpen.matches(':focus-visible')) onPeek(true); });
  capOpen.addEventListener('blur', () => onPeek(false));
  // The caption is a thing, not a hole: its head presents the work it names (like Enter), the
  // descriptor is inert and selectable, and only the void beyond it dismisses.
  head.addEventListener('click', (e) => { if (live() && !aside(e)) onActivate(current, false); });

  // ---- the rail as one pointer target --------------------------------------------------------
  let centres = null;     // tick centres along the rail's axis; measured when first needed after a layout change
  function nearest(x, y) {
    if (!centres) centres = anchors.map((a) => { const r = a.getBoundingClientRect(); return tall() ? (r.left + r.right) / 2 : (r.top + r.bottom) / 2; });
    const v = tall() ? x : y;
    const spacing = centres.length > 1 ? Math.abs(centres[1] - centres[0]) : 0;
    let best = -1, bd = Math.max(UI.hitRadius, spacing / 2);
    for (let i = 0; i < centres.length; i++) { const d = Math.abs(centres[i] - v); if (d < bd) { bd = d; best = i; } }
    return best;
  }
  const down = { id: -1, x: 0, y: 0, moved: false, endedAt: -1e9 };
  rail.addEventListener('pointerdown', (e) => {
    if (e.button !== 0 || !live()) return;
    down.id = e.pointerId; down.x = e.clientX; down.y = e.clientY; down.moved = false;
  });
  rail.addEventListener('pointermove', (e) => {
    if (!live()) return;
    if (down.id === e.pointerId) {
      if (!down.moved && Math.hypot(e.clientX - down.x, e.clientY - down.y) > UI.tapSlop) down.moved = true;
      if (down.moved) {
        // A drag along the rail scrubs: the station under the pointer is travelled to.
        const i = nearest(e.clientX, e.clientY);
        if (i >= 0) { onFocus(i); onTravel(i); }
        return;
      }
    }
    if (e.pointerType !== 'touch') onFocus(nearest(e.clientX, e.clientY));   // a finger does not hover
  });
  const release = (e) => {
    if (down.id !== e.pointerId) return;
    down.id = -1;
    if (down.moved) down.endedAt = e.timeStamp;
    if (e.pointerType !== 'mouse') onFocus(-1);
  };
  rail.addEventListener('pointerup', release);
  rail.addEventListener('pointercancel', release);
  rail.addEventListener('pointerleave', () => { down.id = -1; onFocus(-1); });
  rail.addEventListener('dragstart', (e) => { if (live()) e.preventDefault(); });   // a drag scrubs; it does not lift the link
  rail.addEventListener('click', (e) => {
    // A plain click presents the nearest work; a second plain click, on the work already
    // presented, follows the link through the door. A modified click is left alone so it
    // behaves like the link it is, and the click that ends a drag is the drag's own.
    if (aside(e) || !live()) return;
    e.preventDefault();
    if (e.timeStamp - down.endedAt < UI.tapAfterDrag * 1000) return;
    const a = e.target.closest('a[data-index]');
    const i = e.detail === 0 && a ? +a.dataset.index : nearest(e.clientX, e.clientY);   // detail 0: the keyboard
    if (i < 0) return;
    if (anchors[i].dataset.selected === '1') onOpen(e.detail === 0); else onActivate(i, e.detail === 0);
  });
  // Only keyboard focus points at a work; the focus a click leaves behind does not.
  rail.addEventListener('focusin', (e) => { const a = e.target.closest('a[data-index]'); if (a && a.matches(':focus-visible')) onFocus(+a.dataset.index); });
  rail.addEventListener('focusout', () => onFocus(-1));

  // ---- the caption ---------------------------------------------------------------------------
  let current = -1, shown = -1, pending = -1, swapTimer = 0, front = 0, hashTimer = 0;
  let selected = -1, dipTimer = 0;
  const say = (text) => { announcer.textContent = text; };
  /** The station in the URL (the hash of the first is empty), and the work presented in the
   *  history entry's state (so Back to this page, kept alive or not, finds it presented), written
   *  after the changes stop. */
  function writeHash(i) {
    clearTimeout(hashTimer);
    hashTimer = setTimeout(() => {
      const hash = i > 0 && works[i] ? `#${works[i].id}` : '';
      const kept = history.state && typeof history.state === 'object' ? history.state : {};
      const presented = selected >= 0 && works[selected] ? works[selected].id : null;
      if (location.hash === hash && (kept.presented ?? null) === presented) return;
      try { history.replaceState({ ...kept, presented }, '', location.pathname + location.search + hash); } catch { /* rate-limited: the next change writes it */ }
    }, UI.hashDelay);
  }

  // The furniture a hover tag must not land on (the dock, the leader, the caption's head), as
  // rects, measured when first asked for after a change of layout or caption.
  let furniture = null;
  const PAD = 6;   // px of air kept round the furniture
  function measureFurniture() {
    furniture = [dock, leader, layers[front].el].map((node) => {
      const r = node.getBoundingClientRect();
      return [r.left - PAD, r.top - PAD, r.right + PAD, r.bottom + PAD];
    });
  }
  let furnitureTimer = 0;
  function measureLeader() {
    // Measured again once the leader's own transition (0.45 s) has landed.
    furniture = null; clearTimeout(furnitureTimer); furnitureTimer = setTimeout(() => { furniture = null; }, 500);
    root.style.setProperty('--cap-no', `${layers[front].no.getBoundingClientRect().width}px`);
    if (tall()) return;
    const right = head.getBoundingClientRect().right;
    const end = parseFloat(getComputedStyle(root).getPropertyValue('--rest-x')) - UI.dockGap;
    leader.style.left = `${Math.round(right + UI.leaderGap)}px`;
    leader.style.width = `${Math.max(0, Math.round(end - right - UI.leaderGap))}px`;
  }
  /** Put station `i` on the back layer and bring it to the front: the old text fades under it. */
  function swap(i, instant) {
    // One mark, one meaning: whatever carried it before (the server marks work 01) gives it up.
    for (const a of anchors) if (a !== anchors[i]) a.removeAttribute('aria-current');
    shown = i;
    const work = works[i];
    if (anchors[i]) anchors[i].setAttribute('aria-current', 'true');
    front = 1 - front;
    const inLayer = layers[front], outLayer = layers[1 - front];
    inLayer.no.textContent = work ? `${pad2(i + 1)} / ${pad2(n)}` : '';
    inLayer.title.textContent = work ? work.title : '';
    if (instant) { head.classList.add('is-still'); void head.offsetWidth; }
    inLayer.el.classList.add('is-on');
    outLayer.el.classList.remove('is-on');
    if (instant) head.classList.remove('is-still');
    if (work && i !== selected) say(`${i + 1} of ${n}, ${work.title}`);
    measureLeader();
  }
  function writeDetail(work) {
    capKind.textContent = kindLabel(work.kind);
    capLine.textContent = work.line;
    capOpen.href = work.href;
    capOpen.setAttribute('aria-label', `Open ${work.title}`);
  }

  return {
    anchors,
    /** True when index.html's markup was taken as is (false: rebuilt from the data). */
    adopted,
    setLayout(layout) {
      root.classList.toggle('is-tall', layout.portrait);
      root.style.setProperty('--rest-x', `${layout.restPx.x}px`);
      root.style.setProperty('--rest-y', `${layout.restPx.y}px`);
      // On a wide monitor the caption and the rail close in on the light and the monument,
      // so the three stay one reading span while the name and the links keep the corners.
      const margin = parseFloat(getComputedStyle(root).getPropertyValue('--margin')) || 40;
      root.style.setProperty('--cap-x', `${Math.round(Math.max(margin, layout.restPx.x - layout.capReach))}px`);
      root.style.setProperty('--rail-right', `${Math.round(Math.max(margin, layout.width - layout.railEdge))}px`);
      const row = Math.max(UI.rowMin, Math.min(UI.rowMax, Math.floor((layout.height - UI.railReserve) / n)));
      root.style.setProperty('--row', `${row}px`);
      root.style.setProperty('--hit', `${Math.max(UI.hitRow, row)}px`);   // the anchor: never under the hit row, overlapping if it must
      centres = null;
      measureLeader();
    },
    setCurrent(i, instant) {
      if (i === current) return;
      current = i;
      pending = i;
      writeHash(i);
      if (instant) { clearTimeout(swapTimer); swapTimer = 0; swap(i, true); return; }
      if (swapTimer) return;                         // a swap is recent: this one waits its turn
      swap(i, false);
      const later = () => {
        swapTimer = 0;
        if (pending !== shown) { swap(pending, false); swapTimer = setTimeout(later, UI.swapEvery); }
      };
      swapTimer = setTimeout(later, UI.swapEvery);
    },
    /**
     * Portrait: the height the caption (with the tallest descriptor of any work, at this width)
     * and the strip need below the light, in CSS px, so OPEN never lies over the strip's numeral
     * zone however short the phone. Measured from the laid-out page (call after setLayout);
     * it does not depend on where the light rests, so one correction settles the layout.
     */
    portraitReserve(height) {
      const restY = parseFloat(root.style.getPropertyValue('--rest-y')) || 0;
      const drop = caption.getBoundingClientRect().top - restY;
      const keep = [capKind.textContent, capLine.textContent];
      let tallest = 0;
      for (const w of works) {
        capKind.textContent = kindLabel(w.kind); capLine.textContent = w.line;
        tallest = Math.max(tallest, detail.offsetTop + capOpen.offsetTop + capOpen.offsetHeight);   // layout, not transforms
      }
      [capKind.textContent, capLine.textContent] = keep;
      let strip = height;
      for (const a of anchors) strip = Math.min(strip, a.getBoundingClientRect().top);
      return Math.ceil(drop + tallest + UI.stripGap + (height - strip));
    },
    /** @param moveFocus keyboard: focus goes to Open on presenting, back to the rail on dismissing */
    setSelected(i, moveFocus) {
      const was = selected;
      if (was >= 0 && anchors[was]) { delete anchors[was].dataset.selected; anchors[was].removeAttribute('aria-describedby'); }
      const wasOpenFocused = document.activeElement === capOpen;
      selected = i;
      if (current >= 0) writeHash(current);
      const work = works[i];
      caption.classList.toggle('is-selected', !!work);
      capOpen.tabIndex = work ? 0 : -1;
      if (work) {
        anchors[i].dataset.selected = '1';
        anchors[i].setAttribute('aria-describedby', 'cap-hint');
        clearTimeout(dipTimer);
        if (was >= 0 && !reduced.matches) {
          // The presentation moved with the light: the descriptor dips while its text changes.
          detail.classList.add('is-dipped');
          dipTimer = setTimeout(() => { writeDetail(work); detail.classList.remove('is-dipped'); }, UI.detailDip);
        } else writeDetail(work);
        say(`${work.title} selected. ${kindLabel(work.kind)}: ${work.line}. Press Enter to open.`);
        if (moveFocus) capOpen.focus({ preventScroll: true });
      } else {
        if (was >= 0 && works[was]) say(`${works[was].title} closed.`);
        // The keyboard journey (focus went to Open on presenting) returns to the work's anchor;
        // a mouse user's Escape leaves no focus ring behind on the rail.
        const back = anchors[was >= 0 ? was : current];
        if (wasOpenFocused && back) back.focus({ preventScroll: true });
        else if (anchors.includes(document.activeElement)) document.activeElement.blur();
      }
    },
    /** @param source 'rail' when the rail itself is pointed at: its titles show then */
    setFocus(i, source) {
      const hot = i >= 0 && source === 'rail';
      // The anchor the rail is pointed at reaches exactly as far as its own label (styles.css).
      if (hot) anchors[i].style.setProperty('--reach', `${anchors[i].querySelector('.label').offsetWidth}px`);
      anchors.forEach((a, k) => a.classList.toggle('is-focus', k === i));
      rail.classList.toggle('is-hot', hot);
    },
    /** Number and title pinned to a block; x, y in CSS pixels, or index = -1 to hide. */
    setTag(index, x, y) {
      if (index < 0) { tag.classList.remove('is-on'); return; }
      this.tagSize(index);
      tag.style.transform = `translate3d(${Math.round(x)}px, ${Math.round(y)}px, 0) translate(-50%, -50%)`;
      tag.classList.add('is-on');
    },
    /** Would a box of w x h centred at (x, y) lie on the dock, the leader or the caption's head? */
    onFurniture(x, y, w, h) {
      if (!furniture) measureFurniture();
      const l = x - w / 2, t = y - h / 2, r = x + w / 2, b = y + h / 2;
      for (const f of furniture) if (l < f[2] && r > f[0] && t < f[3] && b > f[1]) return true;
      return false;
    },
    /** The tag's size for a work, in CSS px (measured once per work, when its text is set). */
    tagSize(index, out = {}) {
      if (tag.dataset.index !== String(index)) {
        tag.dataset.index = String(index);
        tagNo.textContent = pad2(index + 1);
        tagTitle.textContent = works[index].title;
        tag.dataset.w = tag.offsetWidth; tag.dataset.h = tag.offsetHeight;
      }
      out.w = +tag.dataset.w; out.h = +tag.dataset.h;
      return out;
    },
    /** The scene's DOM effects, from one place: the pointer's cursor, a cut under reduced
     *  motion (one short fade of the canvas), the first drawn frame, and the departure. */
    cursor(kind) { canvas.style.cursor = kind; },
    cut() {
      if (!reduced.matches) return;
      canvas.classList.remove('is-cut'); void canvas.offsetWidth; canvas.classList.add('is-cut');
    },
    drawn() { root.classList.add('is-drawn'); },
    leaving(on) { root.classList.toggle('is-leaving', on); },
    arrive() {
      dock.classList.remove('is-arrived');
      void dock.offsetWidth; // restart the keyframes
      dock.classList.add('is-arrived');
    },
    /** The presented work's link, or null. */
    href: () => (selected >= 0 ? works[selected].href : null),
    /** Index of the rail anchor holding keyboard focus, or -1. */
    focusedIndex: () => anchors.indexOf(document.activeElement),
    /** CSS-pixel centre of a work's rail anchor (test hook: `locate`). */
    tickPoint(i) {
      const r = anchors[i].getBoundingClientRect();
      return { x: (r.left + r.right) / 2, y: (r.top + r.bottom) / 2 };
    },
    /** The arrival: the interface is invisible, so nothing in it may take focus. */
    withhold() { for (const node of [masthead, rail, caption, links, themes, soundToggle]) if (node) node.inert = true; },
    reveal() {
      if (live()) root.classList.add('is-live');
      for (const node of [masthead, rail, caption, links, themes, soundToggle]) if (node) node.inert = false;
      measureLeader();
    },
  };
}
