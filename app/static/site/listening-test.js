/* Don't Fret's listening test (/dont-fret/listening-test). Plays each piece's clips in sync through
   Web Audio, so switching clips keeps your place in the music; keeps the listener's progress in
   this browser; posts their answers after every piece. Which clip is which never reaches the page:
   the server scores the answers (blueprints/dont_fret). Markup: templates/dont_fret/
   listening_test.html. Look: static/site/listening-test.css. */
(() => {
  "use strict";
  const root = document.getElementById("lt");
  if (!root) return;
  const BANDS = ["Bad", "Poor", "Fair", "Good", "Excellent"];
  const LETTERS = "ABCDEFGH";
  const MIN_HEARD = 2;                       // seconds of listening before a clip can be rated
  const STORE = "dont-fret-listening-test";
  const intro = root.querySelector(".lt-intro");
  const S = {
    manifest: null, base: null, listener: null, info: { experience: "", playback: "" },
    order: [], letters: {}, ratings: {}, heard: {}, index: 0, finished: false,
    saved: null, limited: false, note: "", view: "intro",
  };

  // ---------- small helpers ----------
  const el = (tag, attrs = {}, ...kids) => {
    const n = document.createElement(tag);
    for (const [k, v] of Object.entries(attrs)) {
      if (k === "class") n.className = v;
      else if (k === "text") n.textContent = v;
      else if (k.startsWith("on")) n.addEventListener(k.slice(2), v);
      else if (v !== false && v != null) n.setAttribute(k, v === true ? "" : v);
    }
    for (const c of kids.flat()) if (c != null) n.append(c.nodeType ? c : document.createTextNode(c));
    return n;
  };
  const shuffle = (a) => { a = a.slice(); for (let i = a.length - 1; i > 0; i--) { const j = Math.floor(Math.random() * (i + 1)); [a[i], a[j]] = [a[j], a[i]]; } return a; };
  const trial = (id) => S.manifest.trials.find((t) => t.id === id);
  const complete = (id) => (S.letters[id] || []).every((f) => S.ratings[id] && S.ratings[id][f] != null);
  const uuid = () => {
    if (window.crypto && crypto.randomUUID) return crypto.randomUUID();
    const b = crypto.getRandomValues(new Uint8Array(16)); b[6] = (b[6] & 15) | 64; b[8] = (b[8] & 63) | 128;
    const h = [...b].map((x) => x.toString(16).padStart(2, "0")).join("");
    return `${h.slice(0, 8)}-${h.slice(8, 12)}-${h.slice(12, 16)}-${h.slice(16, 20)}-${h.slice(20)}`;
  };
  const remember = () => {
    try { localStorage.setItem(STORE, JSON.stringify({ listener: S.listener, info: S.info, order: S.order, letters: S.letters, ratings: S.ratings, index: S.index, finished: S.finished, saved: S.saved })); } catch (e) { /* private window: progress lasts for this visit */ }
  };
  const recall = () => { try { return JSON.parse(localStorage.getItem(STORE) || "null"); } catch (e) { return null; } };

  // ---------- audio: a piece's clips all run together; switching only changes which one you hear ----------
  let ctx = null, deck = null, raf = 0;
  const buffers = new Map();
  const audio = () => { if (!ctx) ctx = new (window.AudioContext || window.webkitAudioContext)(); if (ctx.state === "suspended") ctx.resume(); return ctx; };
  const url = (file) => new URL(file, S.base).href;
  async function load(t) {
    await Promise.all(t.stimuli.map(async (s) => {
      if (buffers.has(s.file)) return;
      const res = await fetch(url(s.file));
      if (!res.ok) throw new Error(res.status);
      buffers.set(s.file, await audio().decodeAudioData(await res.arrayBuffer()));
    }));
  }
  function stop() {
    if (!deck) return;
    for (const v of deck.voices) { try { v.src.stop(); } catch (e) { /* already stopped */ } }
    deck = null; cancelAnimationFrame(raf); paintTime();
  }
  function start(t, offset) {
    stop();
    const c = audio(), at = c.currentTime + 0.03, files = S.letters[t.id];
    const dur = Math.min(...files.map((f) => buffers.get(f).duration));
    const voices = files.map((f) => {
      const src = c.createBufferSource(), g = c.createGain();
      src.buffer = buffers.get(f); src.loop = true; src.loopEnd = dur; g.gain.value = 0;
      src.connect(g).connect(c.destination); src.start(at, offset % dur);
      return { file: f, src, g };
    });
    deck = { trial: t.id, voices, t0: at - offset, dur, selected: null, last: at };
    tick();
  }
  function select(file) {
    const now = audio().currentTime;
    for (const v of deck.voices) {
      v.g.gain.cancelScheduledValues(now); v.g.gain.setValueAtTime(v.g.gain.value, now);
      v.g.gain.linearRampToValueAtTime(v.file === file ? 1 : 0, now + 0.012);   // 12 ms, no click
    }
    deck.selected = file;
  }
  async function play(t, file) {
    try { await load(t); } catch (e) { S.note = "A clip didn't load. Check your connection and press Play again."; render(); return; }
    S.note = "";
    if (deck && deck.trial === t.id && deck.selected === file) { stop(); render(); return; }
    if (!deck || deck.trial !== t.id) start(t, deck ? audio().currentTime - deck.t0 : 0);
    select(file); render();
  }
  function tick() {
    if (!deck) return;
    const now = ctx.currentTime, dt = Math.max(0, now - deck.last); deck.last = now;
    if (deck.selected && now > deck.t0) {
      const h = (S.heard[deck.trial] = S.heard[deck.trial] || {});
      const before = h[deck.selected] || 0;
      h[deck.selected] = before + dt;
      if (before < MIN_HEARD && h[deck.selected] >= MIN_HEARD) unlock(deck.trial, deck.selected);
    }
    paintTime(); raf = requestAnimationFrame(tick);
  }
  function unlock(id, file) {   // one row, not a redraw: never interrupt a fader in hand
    const i = (S.letters[id] || []).indexOf(file);
    const range = document.getElementById(`lt-rate-${i}`), clip = document.getElementById(`lt-clip-${i}`);
    if (range && S.order[S.index] === id) range.disabled = false;
    if (clip && S.order[S.index] === id) clip.classList.add("is-heard");
  }
  function paintTime() {
    const fill = document.getElementById("lt-fill"), time = document.getElementById("lt-time");
    if (!fill || !time || !S.manifest) return;
    const dur = S.manifest.seconds;
    const pos = deck ? (((ctx.currentTime - deck.t0) % deck.dur) + deck.dur) % deck.dur : 0;
    fill.style.width = (100 * pos / dur).toFixed(2) + "%";
    time.textContent = `${pos.toFixed(1)} / ${dur.toFixed(0)} s`;
  }

  // ---------- answers ----------
  let chain = Promise.resolve();
  function post() {
    if (S.limited) return chain;
    const body = JSON.stringify({ listener: S.listener, info: S.info, letters: S.letters, ratings: S.ratings, finished: S.finished });
    chain = chain.then(async () => {
      try {
        const res = await fetch(root.dataset.answers, { method: "POST", headers: { "Content-Type": "application/json" }, body, keepalive: true, credentials: "same-origin" });
        S.saved = res.status === 204;
        if (res.status === 429) S.limited = true;
      } catch (e) { S.saved = false; }
      remember();
      if (S.view === "done") render();
    });
    return chain;
  }

  // ---------- views ----------
  function render() {
    root.replaceChildren(...({ intro: () => [intro], piece: pieceView, done: doneView }[S.view])());
    paintTime();
  }

  function begin(event) {
    event.preventDefault();
    audio();                                            // a click is the only time a page may start sound
    S.info = { experience: document.getElementById("lt-experience").value, playback: document.getElementById("lt-playback").value };
    if (!S.order.length || S.finished) {
      S.listener = uuid();
      S.order = shuffle(S.manifest.trials.map((t) => t.id));
      S.letters = {}; S.ratings = {}; S.heard = {}; S.finished = false; S.saved = null;
      for (const t of S.manifest.trials) S.letters[t.id] = shuffle(t.stimuli.map((s) => s.file));
      S.index = 0;
    } else {
      S.index = Math.max(0, S.order.findIndex((id) => !complete(id)));
    }
    remember();
    show("piece");
  }
  function show(view) {
    stop(); S.view = view; render();
    if (view === "piece") for (const id of S.order.slice(S.index, S.index + 2)) load(trial(id)).catch(() => {});
    const top = root.getBoundingClientRect().top;
    if (top < 0) root.scrollIntoView({ block: "start", behavior: matchMedia("(prefers-reduced-motion: reduce)").matches ? "auto" : "smooth" });
  }

  function pieceView() {
    const id = S.order[S.index], t = trial(id), files = S.letters[id];
    const heard = S.heard[id] || {}, ratings = (S.ratings[id] = S.ratings[id] || {});
    const playing = (f) => deck && deck.trial === id && deck.selected === f;
    const rate = (e) => {
      const i = +e.target.dataset.i, f = files[i];
      ratings[f] = +e.target.value;
      e.target.classList.add("is-set");
      const score = document.getElementById(`lt-score-${i}`);
      score.textContent = e.target.value; score.className = "lt-score";
      document.getElementById("lt-next").disabled = !complete(id);
      remember();
    };
    const strip = el("div", { class: "lt-strip" },
      el("div", { class: "lt-row lt-row--scale", "aria-hidden": "true" },
        el("span"), el("div", { class: "lt-scale label" }, BANDS.map((b) => el("span", { text: b }))), el("span")));
    files.forEach((f, i) => {
      const ok = (heard[f] || 0) >= MIN_HEARD || ratings[f] != null;
      strip.append(el("div", { class: "lt-row" },
        el("button", { type: "button", id: `lt-clip-${i}`, class: "lt-clip" + (playing(f) ? " is-on" : "") + (ok ? " is-heard" : ""),
          "aria-pressed": String(!!playing(f)), onclick: () => play(t, f) }, el("span", { class: "lt-dot", "aria-hidden": "true" }), `Clip ${LETTERS[i]}`),
        el("input", { type: "range", class: "lt-range" + (ratings[f] != null ? " is-set" : ""), id: `lt-rate-${i}`, "data-i": String(i),
          min: "0", max: "100", step: "1", value: String(ratings[f] != null ? ratings[f] : 50), disabled: !ok,
          "aria-label": `Clip ${LETTERS[i]}: 0 is bad, 100 is excellent`, oninput: rate, onclick: rate }),
        el("span", { class: "lt-score" + (ratings[f] == null ? " is-empty" : ""), id: `lt-score-${i}`, text: ratings[f] == null ? "–" : String(ratings[f]) })));
    });
    const last = S.index === S.order.length - 1;
    return [el("div", { class: "lt-piece" },
      el("div", { class: "lt-piece__head" },
        el("div", {}, el("p", { class: "label", text: `Piece ${S.index + 1} of ${S.order.length}` }), el("h3", { class: "lt-piece__title", text: t.label })),
        el("div", { class: "lt-dots", "aria-hidden": "true" }, S.order.map((tid, i) => el("i", { class: i === S.index ? "is-now" : complete(tid) ? "is-done" : "" })))),
      el("p", { class: "note", text: `${S.manifest.question} A clip's slider unlocks after two seconds of listening.` }),
      el("div", { class: "lt-transport" },
        el("button", { type: "button", class: "open", onclick: () => { if (deck) { stop(); render(); } else play(t, files[0]); } }, el("span", { text: deck ? "Stop" : "Play" })),
        el("div", { class: "lt-bar", title: "Jump to a point in the clip", onclick: (e) => {
          const r = e.currentTarget.getBoundingClientRect(), off = Math.max(0, Math.min(0.999, (e.clientX - r.left) / r.width)) * S.manifest.seconds;
          const sel = (deck && deck.selected) || files[0];
          load(t).then(() => { start(t, off); select(sel); render(); }).catch(() => {});
        } }, el("span", { class: "lt-bar__fill", id: "lt-fill" })),
        el("span", { class: "lt-time label", id: "lt-time" })),
      strip,
      el("p", { class: "note", text: `Keys: 1 to ${files.length} switch clips, Space plays or stops.` }),
      el("div", { class: "actions" },
        el("button", { type: "button", class: "open open--quiet", disabled: S.index === 0, onclick: () => { S.index--; remember(); show("piece"); } }, el("span", { text: "Back" })),
        el("button", { type: "button", class: "open", id: "lt-next", disabled: !complete(id), onclick: next }, el("span", { text: last ? "Finish" : "Next piece" }))),
      el("p", { class: "status", role: "status", text: S.note }))];
  }
  function next() {
    if (S.index === S.order.length - 1) { S.finished = true; remember(); post(); show("done"); }
    else { S.index++; remember(); post(); show("piece"); }
  }

  function doneView() {
    const out = [];
    if (S.saved === null) out.push(el("p", { class: "lede", text: "Saving your answers…" }));
    else if (S.saved) out.push(el("div", { class: "prose" }, el("p", { class: "lede", text: "Thank you. Your answers are saved, so you can close this page." })));
    else if (S.limited) out.push(el("div", { class: "prose" }, el("p", { class: "lede", text: "Too many listeners have started from your network today. Please try again tomorrow." })));
    else out.push(el("div", { class: "prose" }, el("p", { class: "lede", text: "Your answers didn't reach the site. Check your connection and press Try again." })),
      el("div", { class: "actions" }, el("button", { type: "button", class: "open", onclick: () => { S.saved = null; render(); post(); } }, el("span", { text: "Try again" }))));
    out.push(el("div", { class: "actions" }, el("button", { type: "button", class: "open open--quiet", onclick: () => { S.order = []; S.finished = false; startLabel(); show("intro"); } }, el("span", { text: "Take it again" }))));
    return [el("div", { class: "lt-piece" }, ...out)];
  }

  // ---------- keyboard ----------
  document.addEventListener("keydown", (e) => {
    if (S.view !== "piece" || e.metaKey || e.ctrlKey || e.altKey || /SELECT|TEXTAREA/.test(e.target.tagName)) return;
    const t = trial(S.order[S.index]), files = S.letters[t.id];
    if (e.code === "Space" && e.target.tagName !== "BUTTON") { e.preventDefault(); if (deck) { stop(); render(); } else play(t, files[0]); }
    const n = parseInt(e.key, 10);
    if (n >= 1 && n <= files.length) { e.preventDefault(); play(t, files[n - 1]); }
  });

  // ---------- boot ----------
  const button = document.getElementById("lt-start"), status = document.getElementById("lt-status");
  function startLabel() {
    button.querySelector("span").textContent = S.order.length && !S.finished ? "Continue where you left off" : "Start the test";
  }
  const saved = recall();
  if (saved && saved.listener && saved.order && saved.order.length) {
    Object.assign(S, { listener: saved.listener, info: saved.info || S.info, order: saved.order, letters: saved.letters || {},
                       ratings: saved.ratings || {}, index: saved.index || 0, finished: !!saved.finished, saved: saved.saved ?? null });
    document.getElementById("lt-experience").value = S.info.experience || "";
    document.getElementById("lt-playback").value = S.info.playback || "";
  }
  document.getElementById("lt-form").addEventListener("submit", begin);
  fetch(root.dataset.manifest).then((r) => { if (!r.ok) throw new Error(r.status); return r.json(); }).then((m) => {
    S.manifest = m; S.base = new URL(root.dataset.manifest, location.href);
    // progress from an older set of clips doesn't fit this one: start afresh
    const ids = new Set(m.trials.map((t) => t.id));
    if (S.order.some((id) => !ids.has(id))) { S.order = []; S.finished = false; }
    startLabel(); button.disabled = false;
  }).catch(() => { status.textContent = "The clips didn't load. Reload the page to try again."; });
})();
