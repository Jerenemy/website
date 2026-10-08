#!/bin/sh
# The regression checklist in one command. Prints one PASS/FAIL line per check, a summary,
# and exits 1 if anything failed. Captures and the full harness output go to shots/wip/regress.
#   sh tools/regress.sh /path/to/harness/shot.mjs
#   HARNESS=/path/to/harness/shot.mjs sh tools/regress.sh
#
# Checks: geometry proof; 60 fps at 1440x900 DPR 2 at rest, during a far goTo, under a wheel
# stream at n=24, and at 390x844 mobile DPR 2 (rAF cadence from the harness, plus the real
# per-frame cost from window.__demo.bench); n = 3, 4, 10, 24 boot clean; reduced motion
# renders on demand; ?nogl=1 leaves the DOM index; input spam ends in a finite idle state;
# a lost WebGL context is recovered; the roll's launch and timings; the wheel classifier
# (notches, a stream, a fling); one station per swipe; sweep-then-click aim; the caption never
# blank under a held key; the arrival inert and ready at ignite; the door; exits and homes; the
# rail (numerals, a drag scrubs, 24 px hit rows with the nearest tick winning at n=40, the
# portrait strip at n=24); semantics (Tab order, normal-case names, the two-step announced);
# adopted markup and locate-driven clicks; the no-WebGL list; the three face tones stay apart
# at eight roll angles; the review's findings: the tilt opens at ordinary pointer speeds and
# the light stays in its ring; the door waits for the light; a double-click is one click; the
# caption and the rail's title are targets; a trackpad flick with equal first deltas is one
# gesture; a held key seats within 1.6 s of release; End carries focus; OPEN is 44 px on a
# phone; a key during the arrival only hurries, a tap on a step counts at the strike; the link
# is followed once and the scene returns; Back from a work page returns to the work left, with the
# back/forward cache on and off, marked once on the rail, never departs again, and a stopped
# navigation waits for the visitor's next input (tools/check-back.mjs); the second review's
# findings (tools/check-input.mjs): no rail box over the stone, the roll never turns back, OPEN
# clear of the strip on short phones, a double-click under reduced motion is one click, one
# current mark after a deep link, the strike only for a real tear in the scene, no tilt during
# the arrival, the seam step's door waits for the seam to shut, a modified click opens beside; the
# door is lit by the light alone, exactly zero without line of sight (model and GPU, src/probe.js);
# one hue at the door (no rose at rest, through the breath, entering, inside, departing); the light
# leans in while OPEN is pointed at; the idle lift spares the step under the door's sill; the light on
# the stone (tools/check-pool.mjs): every face wholly held or free at every station of n = 3..40, and,
# ray by ray against the frame with the light off, no face it does not hold darker, none it holds dark,
# no ring, no hue inside a face, no rose, at rest and presented.
HARNESS="${1:-${HARNESS:?usage: sh tools/regress.sh /path/to/shot.mjs (or set HARNESS)}}"
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
OUT="$ROOT/shots/wip/regress"
LOG="$OUT/harness.log"
FPS_AVG_MAX=17.5   # ms: a 60 Hz cadence is 16.67
FPS_P95_MAX=22     # ms: one dropped frame in twenty is the limit
BENCH_MAX=12       # ms per frame, tick and GPU drained: head-room under the 16.67 budget
mkdir -p "$OUT"; : > "$LOG"
FAILED=0; CHECKS=0
pass() { CHECKS=$((CHECKS + 1)); printf 'PASS  %s\n' "$1"; }
fail() { CHECKS=$((CHECKS + 1)); FAILED=1; printf 'FAIL  %s\n' "$1"; }
READY='{"waitFor":"window.__demo && window.__demo.ready"}'
PARK='{"move":[60,860]}'
STATE='{"eval":"window.__demo.state()"}'
IDLE='{"waitFor":"window.__demo.state().phase === \u0027idle\u0027"}'

# run <name> <harness args...>: the harness output is kept in $RES and appended to the log.
run() { name="$1"; shift; RES="$(node "$HARNESS" --root "$ROOT" --out "$OUT" "$@" 2>&1)"; printf '## %s\n%s\n\n' "$name" "$RES" >> "$LOG"; }
clean() { printf '%s\n' "$RES" | grep -q '^no console errors'; }
# evalN <n>: the n-th eval result in $RES
evalN() { printf '%s\n' "$RES" | grep '^eval ' | sed -n "${1}p" | sed 's/^eval //'; }
# js <expression over v> <json>: true/false from node; js2 prints the expression's value
js() { node -e 'const v = JSON.parse(process.argv[2]); process.exit(eval(process.argv[1]) ? 0 : 1)' "$1" "$2"; }
js2() { node -e 'const v = JSON.parse(process.argv[2]); console.log(eval(process.argv[1]))' "$1" "$2"; }
# fpsOK <n>: the first fps line and the n-th eval (bench ms per frame) in $RES are within budget
fpsOK() {
  FPS="$(printf '%s\n' "$RES" | grep '^fps ' | head -1 | sed 's/^fps //; s/ renderer:.*//')"
  BENCH="$(evalN "$1")"
  [ -n "$FPS" ] && [ -n "$BENCH" ] && js "v.f.avgMs <= $FPS_AVG_MAX && v.f.p95Ms <= $FPS_P95_MAX && v.b <= $BENCH_MAX" "{\"f\":$FPS,\"b\":$BENCH}"
}
report() { printf '%s (fps %s, bench %s ms/frame)' "$1" "$FPS" "$BENCH"; }

# ---- geometry ------------------------------------------------------------------------------
if node "$ROOT/tools/check-geometry.mjs" > "$OUT/geometry.log" 2>&1; then pass 'geometry: check-geometry.mjs'; else fail 'geometry: check-geometry.mjs (see shots/wip/regress/geometry.log)'; fi

# ---- frame rate ------------------------------------------------------------------------------
run fps-rest --dpr 2 --query skipIntro=1 --steps "[$READY,$PARK,{\"wait\":2600},{\"fps\":2000},{\"eval\":\"window.__demo.bench(90)\"}]"
if clean && fpsOK 1; then pass "$(report 'fps: 1440x900 DPR 2 at rest')"; else fail "$(report 'fps: 1440x900 DPR 2 at rest')"; fi

run fps-goto --dpr 2 --query skipIntro=1 --steps "[$READY,$PARK,{\"wait\":1200},{\"eval\":\"window.__demo.goTo('zaybot')\"},{\"fps\":1500},{\"eval\":\"window.__demo.goTo('diffusion')\"},{\"eval\":\"window.__demo.bench(90)\"}]"
if clean && fpsOK 3; then pass "$(report 'fps: during a far goTo')"; else fail "$(report 'fps: during a far goTo')"; fi

STREAM='{"eval":"window.__rs = setInterval(() => window.dispatchEvent(new WheelEvent(\"wheel\", {deltaY: 30})), 40); 1"}'
run fps-wheel --dpr 2 --query "skipIntro=1&n=24" --steps "[$READY,$PARK,{\"wait\":1200},$STREAM,{\"fps\":2000},{\"eval\":\"window.__demo.bench(90)\"},{\"eval\":\"clearInterval(window.__rs); 1\"},$IDLE,$STATE]"
if clean && fpsOK 2 && js 'v.phase === "idle" && Number.isFinite(v.position)' "$(evalN 4)"; then pass "$(report 'fps: wheel stream at n=24')"; else fail "$(report 'fps: wheel stream at n=24')"; fi

run fps-mobile --mobile --w 390 --h 844 --dpr 2 --query skipIntro=1 --steps "[$READY,{\"wait\":2600},{\"fps\":2000},{\"eval\":\"window.__demo.bench(90)\"}]"
if clean && fpsOK 1; then pass "$(report 'fps: 390x844 mobile DPR 2')"; else fail "$(report 'fps: 390x844 mobile DPR 2')"; fi

# ---- scale -----------------------------------------------------------------------------------
for N in 3 4 10 24; do
  run "n$N" --query "n=$N" --steps "[$READY,{\"wait\":600},{\"shot\":\"n$N\"},$STATE]"
  MARKUP="$([ "$N" = 10 ] && echo adopted || echo built)"
  if clean && [ -n "$(evalN 1)" ] && js "v.stations === $N && v.phase === 'idle' && v.markup === '$MARKUP'" "$(evalN 1)"; then pass "scale: n=$N boots clean, markup $MARKUP"; else fail "scale: n=$N (see shots/wip/regress/harness.log)"; fi
done

# ---- reduced motion: render on demand, and a hover still redraws ------------------------------
run reduced --reduced-motion --query skipIntro=1 --steps "[$READY,{\"wait\":500},$STATE,{\"wait\":3000},$STATE,{\"move\":[520,440]},{\"wait\":300},$STATE,{\"shot\":\"reduced\"}]"
if clean && js 'v[0].settled && v[1].renders === v[0].renders && v[2].renders > v[1].renders' "[$(evalN 1),$(evalN 2),$(evalN 3)]"; then pass 'reduced motion: no renders over 3 s idle, hover redraws'; else fail "reduced motion: renders $(evalN 1 | sed 's/.*renders":\([0-9]*\).*/\1/') -> $(evalN 2 | sed 's/.*renders":\([0-9]*\).*/\1/') -> $(evalN 3 | sed 's/.*renders":\([0-9]*\).*/\1/')"; fi

# ---- no WebGL: the DOM index stands alone -------------------------------------------------------
run nogl --query nogl=1 --steps "[$READY,{\"wait\":300},$STATE,{\"eval\":\"[document.documentElement.classList.contains('gl'), document.querySelectorAll('#rail a').length, document.querySelector('#rail .line').getBoundingClientRect().height, getComputedStyle(document.querySelector('#rail .line')).clipPath, !!(document.getElementById('links-nav').compareDocumentPosition(document.getElementById('rail')) & Node.DOCUMENT_POSITION_PRECEDING)]\"},{\"shot\":\"nogl\"}]"
if clean && js 'v[0].phase === "static" && v[0].markup === "adopted" && v[1][0] === false && v[1][1] === 10 && v[1][2] > 12 && v[1][3] === "none" && v[1][4]' "[$(evalN 1),$(evalN 2)]"; then pass 'nogl: the server-rendered list stands, descriptors visible, works before links'; else fail "nogl: $(evalN 1 | cut -c1-80) $(evalN 2)"; fi

# ---- input spam ends in a finite idle state ----------------------------------------------------
run stress --query skipIntro=1 --steps "[$READY,$PARK,{\"wait\":400},{\"scroll\":100,\"times\":15,\"gap\":20},{\"key\":\"ArrowRight\",\"times\":30,\"gap\":10},{\"click\":[700,450]},{\"click\":[900,300]},{\"eval\":\"window.__demo.goTo('sonar')\"},{\"key\":\"ArrowLeft\",\"times\":5,\"gap\":10},{\"click\":[60,860]},$IDLE,{\"wait\":1500},$STATE,{\"shot\":\"stress\"}]"
if clean && js 'v.phase === "idle" && Number.isInteger(v.position) && v.tilt < 1e-3 && v.selected === null' "$(evalN 2)"; then pass "stress: idle at position $(evalN 2 | sed 's/.*"position":\([-0-9.]*\).*/\1/') after wheel x15, arrows x35, clicks, goTo"; else fail "stress: $(evalN 2)"; fi

# ---- WebGL context loss and restore ---------------------------------------------------------------
run context --query skipIntro=1 --steps "[$READY,{\"wait\":400},{\"eval\":\"window.__demo.loseContext()\"},{\"wait\":300},$STATE,{\"eval\":\"window.__demo.restoreContext()\"},{\"wait\":600},$STATE,{\"shot\":\"context-restored\"}]"
if clean && js 'v[0].context === "lost" && v[1].context === "ok" && v[1].renders > v[0].renders' "[$(evalN 2),$(evalN 4)]"; then pass 'context: lost, restored, rendering again'; else fail 'context: loss/restore'; fi

# ---- motion and interaction grammar ------------------------------------------------------------
TRACE='{"eval":"window.__tr=[];window.__t0=performance.now();window.__iv=setInterval(()=>{window.__tr.push([performance.now()-window.__t0,window.__demo.state().stone])},10);1"}'
STOPTRACE='{"eval":"clearInterval(window.__iv); window.__tr"}'
# The roll: one station launches with mass (under 15% of the way at 150 ms) and is 99% seated
# by about 0.55 s of its 0.7 s plan; four stations of ten by about 1.05 s of 1.225 s (the last
# percent is the minimum-jerk tail).
run roll --query skipIntro=1 --steps "[$READY,$PARK,{\"wait\":500},$TRACE,{\"key\":\"ArrowRight\"},{\"wait\":1100},$STOPTRACE,$TRACE,{\"eval\":\"window.__demo.goTo('zaybot')\"},{\"wait\":1900},$STOPTRACE]"
ROLL='(() => { const seat = (v, from, d) => { const r = v.find((p) => Math.abs(p[1] - from) >= 0.99 * d); return r ? r[0] : 1e9; }; const early = v[0].find((p) => p[0] >= 150); return !!early && Math.abs(early[1]) < 0.15 && seat(v[0], 0, 1) >= 450 && seat(v[0], 0, 1) <= 800 && seat(v[1], 1, 4) >= 900 && seat(v[1], 1, 4) <= 1400; })()'
if clean && js "$ROLL" "[$(evalN 2),$(evalN 5)]"; then pass 'roll: heavy launch, one station seated in ~0.55 s, four stations in ~1.05 s'; else fail 'roll: timing (see shots/wip/regress/harness.log)'; fi

# Wheel: three notches are three stations; a 400 ms trackpad stream scrubs in proportion
# (300 px, two stations); a 1 s fling of decaying deltas moves at most two.
STREAM25='{"eval":"(() => { let n = 0; const t = setInterval(() => { window.dispatchEvent(new WheelEvent(\"wheel\", {deltaY: 12})); if (++n >= 25) clearInterval(t); }, 16); return 1; })()"}'
FLING='{"eval":"(() => { let d = 140, n = 0; const t = setInterval(() => { window.dispatchEvent(new WheelEvent(\"wheel\", {deltaY: d})); d = Math.max(2, d * 0.94); if (++n >= 60) clearInterval(t); }, 16); return 1; })()"}'
run wheel --query skipIntro=1 --steps "[$READY,$PARK,{\"wait\":400},{\"scroll\":100,\"times\":3,\"gap\":30},{\"wait\":80},$IDLE,$STATE,$STREAM25,{\"wait\":1300},$IDLE,$STATE,$FLING,{\"wait\":1700},$IDLE,$STATE]"
if clean && js 'v[0].position === 3 && v[1].position === 5 && v[2].position >= 6 && v[2].position <= 7' "[$(evalN 1),$(evalN 3),$(evalN 5)]"; then pass "wheel: notches x3 -> 3, stream -> +2, fling -> +$(( $(evalN 5 | sed 's/.*"position":\([0-9]*\).*/\1/') - 5 ))"; else fail "wheel: $(evalN 1) $(evalN 3) $(evalN 5)"; fi

# A trackpad flick whose first deltas happen to be equal (60, 60, 58, ...) at 16 ms is one gesture
# (at most two stations); a mouse spun four notches at 40 ms is four.
FLICK60='{"eval":"(() => { let n = 0; const d = [60, 60, 58, 55, 50, 44, 38, 30, 22, 15, 10, 6, 4, 2, 2]; const t = setInterval(() => { window.dispatchEvent(new WheelEvent(\"wheel\", {deltaY: d[n]})); if (++n >= d.length) clearInterval(t); }, 16); return 1; })()"}'
SPIN4='{"eval":"(() => { let n = 0; const t = setInterval(() => { window.dispatchEvent(new WheelEvent(\"wheel\", {deltaY: 100})); if (++n >= 4) clearInterval(t); }, 40); return 1; })()"}'
run flick --query skipIntro=1 --steps "[$READY,$PARK,{\"wait\":400},$FLICK60,{\"wait\":1400},$IDLE,$STATE,$SPIN4,{\"wait\":1400},$IDLE,$STATE]"
if clean && js 'v[0].position >= 1 && v[0].position <= 2 && v[1].position === v[0].position + 4' "[$(evalN 2),$(evalN 4)]"; then pass "flick: equal first deltas at 16 ms -> +$(evalN 2 | sed 's/.*"position":\([0-9]*\).*/\1/'), a spun mouse -> +4"; else fail "flick: $(evalN 2) $(evalN 4)"; fi

# A held key: 40 ArrowRights at 50 ms seat within 1.6 s of the last one (the stone is shifted by
# whole laps, so no journey is longer than about a half lap).
run hold --query skipIntro=1 --steps "[$READY,$PARK,{\"wait\":400},{\"key\":\"ArrowRight\",\"times\":40,\"gap\":50},{\"eval\":\"window.__t1 = performance.now(); 1\"},{\"waitFor\":\"window.__demo.state().phase === 'idle' && Math.abs(window.__demo.state().stone - window.__demo.state().position) < 1e-3\"},{\"eval\":\"[Math.round(performance.now() - window.__t1), window.__demo.state().position, window.__demo.state().current]\"}]"
if clean && js 'v[0] <= 1600 && v[1] === 40 && v[2] === "diffusion"' "$(evalN 2)"; then pass "hold: 40 keys at 50 ms seated $(evalN 2 | sed 's/\[\([0-9]*\).*/\1/') ms after the last"; else fail "hold: $(evalN 2)"; fi

# The tilt opens at ordinary pointer speeds (1264 px glides at ~320 and ~500 px/s reach 0.02 and
# 0.03 rad) and turns about the light: at its widest the drawn light is still on the dock's centre.
TILTMAX='{"eval":"window.__mx = 0; clearInterval(window.__ti); window.__ti = setInterval(() => { window.__mx = Math.max(window.__mx, window.__demo.state().tilt); }, 10); 1"}'
ONDOCK='{"eval":"[window.__demo.state().tilt, window.__demo.state().light.px, (r => [r.left + r.width / 2, r.top + r.height / 2])(document.getElementById(\u0027dock\u0027).getBoundingClientRect())]"}'
run tilt --query skipIntro=1 --steps "[$READY,$PARK,{\"wait\":1200},$TILTMAX,{\"glide\":[[60,860],[1324,860]],\"ms\":4000},{\"wait\":300},{\"eval\":\"window.__mx\"},{\"move\":[60,860]},{\"wait\":1200},$TILTMAX,{\"glide\":[[60,860],[1324,860]],\"ms\":2500},{\"wait\":300},{\"eval\":\"window.__mx\"},{\"glide\":[[1324,860],[60,860]],\"ms\":600},{\"wait\":60},$ONDOCK,{\"wait\":1500},{\"eval\":\"window.__demo.state().tilt\"}]"
if clean && js 'v[0] >= 0.02 && v[1] >= 0.03 && v[2][0] >= 0.06 && Math.abs(v[2][1][0] - v[2][2][0]) < 1 && Math.abs(v[2][1][1] - v[2][2][1]) < 1 && v[3] === 0' "[$(evalN 2),$(evalN 4),$(evalN 5),$(evalN 6)]"; then pass "tilt: sweeps at ~320 and ~500 px/s open $(evalN 2 | cut -c1-5) and $(evalN 4 | cut -c1-5) rad, the light on the dock at $(evalN 5 | sed 's/\[\([0-9.]*\).*/\1/' | cut -c1-5) rad, shut again exactly"; else fail "tilt: $(evalN 2) $(evalN 4) $(evalN 5) $(evalN 6)"; fi

# Touch: one swipe is one station, however long; with a work presented the presentation moves with it.
run swipe --mobile --w 390 --h 844 --query skipIntro=1 --steps "[$READY,{\"wait\":400},{\"swipe\":[[195,450],[195,100]],\"ms\":150},$IDLE,$STATE,{\"eval\":\"window.__demo.goTo('sonar')\"},{\"waitFor\":\"window.__demo.state().phase === 'idle' && window.__demo.state().settled\"},{\"swipe\":[[195,420],[195,160]],\"ms\":300},$IDLE,$STATE]"
if clean && js 'v[0].position === 1 && v[1].current === "ear" && v[1].selected === "ear" && Number.isInteger(v[1].position)' "[$(evalN 1),$(evalN 3)]"; then pass 'swipe: one station per swipe, presentation follows'; else fail "swipe: $(evalN 1 | cut -c1-120) $(evalN 3 | cut -c1-120)"; fi

# Hover targets do not flee: a sweep onto a step and an immediate click, at four speeds, lands on it.
GLIDE='{"glide":[[60,860],[900,509]],"ms":MS},{"click":[900,509]},{"wait":120},{"eval":"window.__demo.state().selected"},{"key":"Escape"},{"move":[60,860]},{"eval":"window.__demo.goTo(\"diffusion\")"},{"key":"Escape"},{"waitFor":"window.__demo.state().phase === \"idle\" && window.__demo.state().settled"}'
run glide --query skipIntro=1 --steps "[$READY,$PARK,{\"wait\":500},$(printf '%s' "$GLIDE" | sed 's/MS/60/'),$(printf '%s' "$GLIDE" | sed 's/MS/200/'),$(printf '%s' "$GLIDE" | sed 's/MS/600/'),$(printf '%s' "$GLIDE" | sed 's/MS/1500/')]"
if clean && js 'v.every((s) => s === "zaybot")' "[$(evalN 1),$(evalN 3),$(evalN 5),$(evalN 7)]"; then pass 'aim: glide then click lands at 60, 200, 600 and 1500 ms'; else fail "aim: $(evalN 1) $(evalN 3) $(evalN 5) $(evalN 7)"; fi

# The caption never blanks: under a held key one copy of number and title is always at least half visible.
CAPWATCH='{"eval":"window.__cap=[];window.__ci=setInterval(()=>{const L=[...document.querySelectorAll(\"#head .cap\")].filter(el=>el.querySelector(\".title\").textContent);window.__cap.push(Math.max(...L.map(el=>+getComputedStyle(el).opacity),0))},20);1"}'
run caption --query skipIntro=1 --steps "[$READY,$PARK,{\"wait\":400},$CAPWATCH,{\"key\":\"ArrowRight\",\"times\":20,\"gap\":30},{\"wait\":600},{\"eval\":\"clearInterval(window.__ci); [Math.min(...window.__cap), window.__cap.length]\"}]"
if clean && js 'v[0] >= 0.5 && v[1] > 40' "$(evalN 2)"; then pass "caption: never blank under a held key (min visible opacity $(evalN 2 | sed 's/\[\([0-9.]*\).*/\1/'))"; else fail "caption: $(evalN 2)"; fi

# Arrival: invisible controls are inert and Tab cannot land on them; ready resolves at ignite, not the end.
run arrival --steps "[{\"eval\":\"window.__t0=performance.now(); [document.getElementById('masthead').inert, document.getElementById('rail').inert]\"},{\"wait\":300},{\"key\":\"Tab\",\"times\":3,\"gap\":30},{\"eval\":\"document.activeElement.tagName\"},$READY,{\"eval\":\"[Math.round(performance.now()-window.__t0), window.__demo.state().arrival, window.__demo.state().phase]\"},{\"wait\":300},{\"eval\":\"[document.getElementById('masthead').inert, document.getElementById('rail').inert]\"}]"
if clean && js 'v[0][0] && v[0][1] && v[1] === "BODY" && v[2][0] <= 2300 && v[2][1] < 2.2 && v[2][2] === "idle" && !v[3][0] && !v[3][1]' "[$(evalN 1),$(evalN 2),$(evalN 3),$(evalN 4)]"; then pass "arrival: inert while hidden, ready at $(evalN 3 | sed 's/\[\([0-9]*\).*/\1/') ms"; else fail "arrival: $(evalN 1) $(evalN 2) $(evalN 3) $(evalN 4)"; fi

# Arrival input: Enter at 300 ms presents nothing, during or after (a key only hurries); a click
# on a step at 1100 ms presents nothing mid-convergence and that step once the light is struck.
run arrival-input --steps "[{\"wait\":300},{\"key\":\"Enter\"},{\"wait\":100},{\"eval\":\"[window.__demo.state().phase, window.__demo.state().selected, window.__demo.state().door.open, Math.max(...window.__demo.state().lifts.slice(0, 3))]\"},$READY,{\"wait\":300},{\"eval\":\"[window.__demo.state().selected, window.__demo.state().door.open]\"}]"
A_CLEAN="$(clean && echo 1)"; A1="$(evalN 1)"; A2="$(evalN 2)"
run arrival-tap --steps "[{\"wait\":1100},{\"click\":[970,536]},{\"eval\":\"[window.__demo.state().phase, window.__demo.state().selected]\"},$READY,{\"wait\":400},{\"eval\":\"window.__demo.state().selected\"}]"
if [ "$A_CLEAN" = 1 ] && clean && js 'v[0][0] === "intro" && v[0][1] === null && v[0][2] === 0 && v[1][0] === null && v[1][1] === 0 && v[2][1] === null && v[3] === "zaybot"' "[$A1,$A2,$(evalN 1),$(evalN 2)]"; then pass 'arrival input: Enter only hurries, a tap on a step counts at the strike'; else fail "arrival input: $A1 $A2 $(evalN 1) $(evalN 2)"; fi

# The door: the second action sends the light through and follows the link (held back by ?stay=1).
# At rest the slot is open and dark (the light docks above the tread, behind the riser: it cannot
# reach in); 300 ms after the second action the light is inside it and lights it.
run door --query "skipIntro=1&stay=1" --steps "[$READY,$PARK,{\"wait\":300},{\"eval\":\"window.__demo.goTo('zaychess')\"},{\"waitFor\":\"window.__demo.state().phase === 'idle' && window.__demo.state().settled\"},{\"eval\":\"window.__demo.state().door\"},{\"eval\":\"window.__demo.open()\"},{\"wait\":300},{\"eval\":\"(d => [d.departing, d.inside, d.lit])(window.__demo.state().door)\"},{\"wait\":1400},{\"eval\":\"[window.__demo.state().door.left, getComputedStyle(document.getElementById('stage')).opacity]\"}]"
if clean && js 'v[0].open === 1 && v[0].lit === 0 && v[0].patch === 0 && v[0].inside === 0 && v[1][0] > 0.2 && v[1][1] === 1 && v[1][2] > 0.3 && v[2][0] === "https://jeremyzay.com/zaychess" && v[2][1] === "1"' "[$(evalN 2),$(evalN 4),$(evalN 5)]"; then pass 'door: opens dark with the selection, the light goes in and lights it, the link follows'; else fail "door: $(evalN 2) $(evalN 4) $(evalN 5)"; fi

# The door's light is physical (src/door.js, src/probe.js): with the light swept round the opening,
# every inner point with no line of sight to it gets exactly zero, every point that sees it gets
# some; drawn lit by that light alone the opening has not one coloured pixel with no line of sight
# into it, and is vermilion with one; and pixel by pixel (the bounce off), every surface seen with
# no line of sight to the light is exactly neutral and every one well lit is vermilion. A plain step, both ends of the seam, n = 3, 10 and 24;
# the light the door is lit from lands on the light as drawn.
PROBE='{"eval":"window.__demo.doorProbe().then((r) => r.error ? r : ({ ok: r.ok, block: r.block, violations: r.violations, pairs: r.pairs, blind: r.blindPositions, lit: r.litPositions, gpuBlindPx: r.gpu.blindPixels, gpuBlindChroma: r.gpu.blindChroma, gpuLitMin: +r.gpu.litChromaMin.toFixed(3), shadow: r.gpu.shadowPixels, shadowChroma: r.gpu.shadowChroma, sun: r.gpu.sunPixels, sunNeutral: r.gpu.sunNeutral, dock: r.dock.mean, dockError: r.dockError, err: +r.drawnError.toFixed(5) }))"}'
SETTLE='{"waitFor":"window.__demo.state().phase === \u0027idle\u0027 && window.__demo.state().settled && window.__demo.state().door.open === 1"}'
probeOK='v.every((r) => r.ok === true && r.violations === 0 && r.gpuBlindChroma === 0 && r.gpuBlindPx > 0 && r.gpuLitMin > 0 && r.shadow > 0 && r.shadowChroma === 0 && r.sun > 0 && r.sunNeutral === 0 && r.dock === 0 && r.dockError < 1e-6 && r.err < 0.01)'
run door-light --dpr 2 --query "skipIntro=1&stay=1" --steps "[$READY,$PARK,{\"wait\":300},{\"eval\":\"window.__demo.goTo('zaychess')\"},{\"wait\":250},$SETTLE,$PROBE,{\"eval\":\"window.__demo.goTo('asteroids')\"},{\"wait\":250},$SETTLE,$PROBE,{\"eval\":\"window.__demo.goTo('diffusion')\"},{\"wait\":250},$SETTLE,$PROBE]"
D_CLEAN="$(clean && echo 1)"; D10="$(evalN 2),$(evalN 4),$(evalN 6)"
run door-light-3 --dpr 2 --query "skipIntro=1&stay=1&n=3" --steps "[$READY,$PARK,{\"wait\":300},{\"eval\":\"window.__demo.goTo('curve-explorer')\"},{\"wait\":250},$SETTLE,$PROBE,{\"eval\":\"window.__demo.goTo('diffusion')\"},{\"wait\":250},$SETTLE,$PROBE]"
D3_CLEAN="$(clean && echo 1)"; D3="$(evalN 2),$(evalN 4)"
run door-light-24 --dpr 2 --query "skipIntro=1&stay=1&n=24" --steps "[$READY,$PARK,{\"wait\":300},{\"eval\":\"window.__demo.goTo('karchive-3')\"},{\"wait\":250},$SETTLE,$PROBE,{\"eval\":\"window.__demo.goTo('diffusion')\"},{\"wait\":250},$SETTLE,$PROBE]"
DALL="[$D10,$D3,$(evalN 2),$(evalN 4)]"
if [ "$D_CLEAN" = 1 ] && [ "$D3_CLEAN" = 1 ] && clean && js "v.length === 7 && $probeOK" "$DALL"; then pass "door light: zero without line of sight in $(js2 'v.reduce((s, r) => s + r.pairs, 0)' "$DALL") point-light pairs and $(js2 'v.reduce((s, r) => s + r.shadow, 0)' "$DALL") shadowed pixels; plain step, both seam ends, n = 3, 10, 24"; else fail "door light: $DALL"; fi

# One hue at the door (window.__demo.doorLook: the door's step and the step in front as drawn, without
# the light's sprite). At rest the riser round the slot is the key's plain grey (the docked light is
# behind its plane) and neither step has a rose pixel, the pool's rim included; through a whole breath
# the lit tread holds its vermilion (only brightness breathes);
# with the light in the cavity, and half way through the wall, nothing on either step is dusty rose and
# the spill falls off from vermilion through dark to grey; on a real departure, frame by frame at 60 Hz,
# no frame after the light is in has a rose pixel. A plain step (the spill on its own side), the
# near end (the spill across the seam, on the far start), and a corner (the spill on the next side's
# first cube). Clocked by the frame (?slow=1000 parks rAF).
LOOK='(r => JSON.stringify({ rose: r.rose, riser: r.riser, tread: r.tread, spill: r.spill, inside: +r.inside.toFixed(3) }))'
DEPART="(async () => { await new Promise((r) => setTimeout(r, 400)); window.__demo.open(); const out = []; for (let i = 0; i < 26; i++) { const r = await window.__demo.doorLook(); out.push([+r.inside.toFixed(3), r.rose]); } return JSON.stringify(out); })()"
colourSteps() { printf '[%s,%s,{"eval":"window.__demo.goTo(%s)"},{"eval":"window.__demo.bench(300)"},{"eval":"window.__demo.doorLook().then(%s)"},' "$READY" "$PARK" "'$1'" "$LOOK"
  for k in 1 2 3 4 5 6; do printf '{"eval":"window.__demo.doorLook({ frames: 48 }).then(%s)"},' "$LOOK"; done
  printf '{"eval":"window.__demo.doorLook({ pin: [-0.07, 0, 0], frames: 2 }).then(%s)"},{"eval":"window.__demo.doorLook({ pin: [0, 0, 0], frames: 2 }).then(%s)"},{"eval":"window.__demo.doorLook({ pin: [-0.03, 0.02, 0.05], frames: 2 }).then(%s)"},{"eval":"window.__demo.doorLook({ pin: null, frames: 2 }).then(%s)"},{"eval":"%s"}]' "$LOOK" "$LOOK" "$LOOK" "$LOOK" "$DEPART"; }
colourOK='const n = (c) => c && Math.abs(c[0] - c[1]) <= 2 && Math.abs(c[1] - c[2]) <= 2, sat = (c) => (Math.max(...c) - Math.min(...c)) / Math.max(...c);
  const tail = (c) => !c || n(c) || Math.max(...c) <= 48 || sat(c) >= 0.75;
  v.every((r) => r[0].riser.every(n) && r.slice(0, 7).every((b) => b.rose === 0) && r.slice(1, 7).every((b) => sat(b.tread) >= 0.85) && [7, 8, 9].every((k) => r[k].rose === 0) && r[7].spill.every(tail) && r[7].spill.some((c) => c && sat(c) >= 0.85)
    && r[7].riser.every(n) && r[10].riser.every(n) && r[11].some((f) => f[0] >= 0.5) && r[11].every((f) => f[0] < 0.5 || f[1] === 0))'
run door-colour --dpr 2 --query "skipIntro=1&stay=1&slow=1000" --steps "$(colourSteps zaychess)"
C_CLEAN="$(clean && echo 1)"; C1="[$(evalN 3),$(evalN 4),$(evalN 5),$(evalN 6),$(evalN 7),$(evalN 8),$(evalN 9),$(evalN 10),$(evalN 11),$(evalN 12),$(evalN 13),$(evalN 14)]"
run door-colour-seam --dpr 2 --query "skipIntro=1&stay=1&slow=1000" --steps "$(colourSteps asteroids)"
C_CLEAN="$C_CLEAN$(clean && echo 1)"; C2="[$(evalN 3),$(evalN 4),$(evalN 5),$(evalN 6),$(evalN 7),$(evalN 8),$(evalN 9),$(evalN 10),$(evalN 11),$(evalN 12),$(evalN 13),$(evalN 14)]"
run door-colour-corner --dpr 2 --query "skipIntro=1&stay=1&slow=1000" --steps "$(colourSteps karchive)"
C3="[$(evalN 3),$(evalN 4),$(evalN 5),$(evalN 6),$(evalN 7),$(evalN 8),$(evalN 9),$(evalN 10),$(evalN 11),$(evalN 12),$(evalN 13),$(evalN 14)]"
unwrap='JSON.stringify(v.map((x) => typeof x === "string" ? JSON.parse(x) : x))'
CALL="[$(js2 "$unwrap" "$C1"),$(js2 "$unwrap" "$C2"),$(js2 "$unwrap" "$C3")]"
if [ "$C_CLEAN" = 11 ] && clean && js "$colourOK && v.length === 3" "$CALL"; then pass "door colour: riser grey at rest, the hue holds through the breath (tread saturation $(js2 'Math.min(...v.flatMap((r) => r.slice(1, 7).map((b) => +((Math.max(...b.tread) - Math.min(...b.tread)) / Math.max(...b.tread)).toFixed(2))))' "$CALL") at least), no rose with the light in or entering or gone in, the spill vermilion to dark to grey; a plain step, across the seam, a corner"; else fail "door colour: $(printf '%s' "$CALL" | cut -c1-900)"; fi

# The light leans in at the door while the way in is pointed at (OPEN): just past the nosing, its beam
# in the slot and its own riser lit; it comes home when the pointer leaves, and going in from the lean
# carries on along the same way. Escape while it leans: the light comes home first, its step waits up,
# then the slot shuts and the step drops.
OPENAT='{"eval":"(r => [r.left < 133 && r.right > 133 && r.top < 570 && r.bottom > 570])(document.getElementById(\u0027cap-open\u0027).getBoundingClientRect())"}'
DOORNOW='{"eval":"(d => [+d.lean.toFixed(3), d.light, +d.lit.toFixed(3), d.open, d.departing, +d.inside.toFixed(3)])(window.__demo.state().door)"}'
run door-lean --query "skipIntro=1&stay=1" --steps "[$READY,$PARK,{\"wait\":300},{\"eval\":\"window.__demo.goTo('zaychess')\"},$SETTLE,$OPENAT,{\"move\":[133,570]},{\"wait\":900},$DOORNOW,$PARK,{\"wait\":900},$DOORNOW,{\"move\":[133,570]},{\"wait\":700},{\"eval\":\"window.__demo.open()\"},{\"wait\":300},$DOORNOW,{\"wait\":1300},{\"move\":[133,570]},{\"wait\":800},$DOORNOW,{\"key\":\"Escape\"},{\"wait\":100},{\"eval\":\"(s => [s.selected, s.door.open, s.door.lean > 0, s.lifts[s.door.block]])(window.__demo.state())\"},{\"wait\":900},{\"eval\":\"(s => [s.selected, s.door.open, s.door.lean, s.door.block, Math.max(...s.lifts)])(window.__demo.state())\"}]"
if clean && js 'v[0][0] === true && v[1][0] > 0.99 && Math.abs(v[1][1][0] - 0.1) < 0.003 && v[1][2] > 0.05 && v[2][0] === 0 && v[2][2] === 0 && v[3][4] > 0.2 && v[3][5] === 1 && v[4][0] > 0.95 && v[5][0] === null && v[5][1] === 1 && v[5][2] === true && v[5][3] > 0.39 && v[6][0] === null && v[6][1] === 0 && v[6][2] === 0 && v[6][3] === -1 && v[6][4] < 0.02' "[$(evalN 2),$(evalN 3),$(evalN 4),$(evalN 6),$(evalN 7),$(evalN 8),$(evalN 9)]"; then pass 'door lean: OPEN pointed at, the light leans in and lights the slot, comes home, goes in from the lean; Escape brings it home before the step drops'; else fail "door lean: $(evalN 2) $(evalN 3) $(evalN 4) $(evalN 6) $(evalN 7) $(evalN 8) $(evalN 9)"; fi

# The idle lift spares the step in front of a presented one (its tread lies under the door's sill):
# with diffusion presented, 22 s of idle life (two lifts), clocked by the frame.
IDLELIFTS="(() => { const seen = []; for (let i = 0; i < 1320; i++) { window.__demo.bench(1); const s = window.__demo.state(); if (s.idle.lifting !== null && seen[seen.length - 1] !== s.idle.lifting) seen.push(s.idle.lifting); } const s = window.__demo.state(); return [seen, s.door.block, s.lifts.length]; })()"
run idle-front --query "skipIntro=1&stay=1&slow=1000" --steps "[$READY,$PARK,{\"eval\":\"window.__demo.goTo('diffusion')\"},{\"eval\":\"window.__demo.bench(200)\"},{\"eval\":\"$IDLELIFTS\"}]"
if clean && js 'v[0].length >= 2 && v[1] >= 0 && !v[0].includes((v[1] + 1) % v[2])' "$(evalN 3)"; then pass "idle: the lifts ($(js2 'v[0].join(", ")' "$(evalN 3)")) spare the step in front of the open door"; else fail "idle front: $(evalN 3)"; fi

# The door waits for the light: 200 ms into a five-station presentation the slot is still shut and
# dark; it is open once the light has arrived, and still dark (the docked light cannot reach in). The link is followed exactly once per departure,
# Escape and the void cannot cancel a departure, and the scene comes back (?stay=1) with input taken.
run door-gate --query "skipIntro=1&stay=1" --steps "[$READY,$PARK,{\"wait\":300},{\"eval\":\"window.__demo.goTo('zaybot')\"},{\"wait\":200},{\"eval\":\"[window.__demo.state().selected, window.__demo.state().door.open, window.__demo.state().door.lit]\"},{\"waitFor\":\"window.__demo.state().phase === 'idle' && window.__demo.state().settled\"},{\"eval\":\"[window.__demo.state().door.open, window.__demo.state().door.lit]\"},{\"eval\":\"window.__demo.open()\"},{\"wait\":250},{\"key\":\"Escape\"},{\"click\":[1200,800]},{\"wait\":60},{\"eval\":\"[window.__demo.state().selected, window.__demo.state().door.open]\"},{\"wait\":1500},{\"eval\":\"[window.__demo.state().door.leaves, window.__demo.state().door.departing, document.documentElement.classList.contains('is-leaving')]\"},{\"key\":\"ArrowRight\"},$IDLE,{\"eval\":\"window.__demo.state().current\"}]"
if clean && js 'v[0][0] === "zaybot" && v[0][1] === 0 && v[0][2] === 0 && v[1][0] === 1 && v[1][1] === 0 && v[2][0] === "zaybot" && v[2][1] === 1 && v[3][0] === 1 && v[3][1] === null && v[3][2] === false && v[4] === "polydiff"' "[$(evalN 2),$(evalN 3),$(evalN 5),$(evalN 6),$(evalN 7)]"; then pass 'door: shut until the light arrives, one leave per departure, Escape cannot cancel it, the scene returns'; else fail "door gate: $(evalN 2) $(evalN 3) $(evalN 5) $(evalN 6) $(evalN 7)"; fi

# Back from a work (tools/check-back.mjs, its own server and Chrome): one departure is one history
# entry and one request; Back lands at the work left, kept alive (bfcache) or cold, and never departs again.
if node "$ROOT/tools/check-back.mjs" "$HARNESS" > "$OUT/back.log" 2>&1; then pass 'back: one entry per departure, Back returns to the work left (bfcache on and off), no second departure'; else fail "back: $(grep -A3 '^FAIL' "$OUT/back.log" | tail -3 | tr '\n' ' ' | cut -c1-300) (see shots/wip/regress/back.log)"; fi

# The second review's findings, each the way it was found (tools/check-input.mjs, its own server and Chrome).
if node "$ROOT/tools/check-input.mjs" "$HARNESS" > "$OUT/input.log" 2>&1; then pass 'input: no rail box over the stone, the roll never turns back, OPEN clear of the strip, calm double-click, one mark, strikes for tears only, no arrival tilt, the seam door waits, modified clicks beside'; else fail "input: $(grep -A12 '^FAIL' "$OUT/input.log" | tail -n +2 | tr '\n' ' ' | cut -c1-400) (see shots/wip/regress/input.log)"; fi

# Reflexes: a second click 150 ms after the first is one click (presented, not departed); a click
# after the caption is readable goes through the door. The caption's title and descriptor are
# targets that keep the presentation; only the void dismisses.
run reflex-locate --query skipIntro=1 --steps "[$READY,$PARK,{\"wait\":300},{\"eval\":\"window.__demo.goTo('zaybot')\"},{\"waitFor\":\"window.__demo.state().phase === 'idle' && window.__demo.state().settled\"},{\"eval\":\"window.__demo.locate('zaybot').step\"}]"
SEAT_X="$(js2 'Math.round(v.x)' "$(evalN 2)")"; SEAT_Y="$(js2 'Math.round(v.y)' "$(evalN 2)")"
run reflex --query "skipIntro=1&stay=1" --steps "[$READY,$PARK,{\"wait\":1200},{\"click\":[970,536]},{\"wait\":150},{\"click\":[970,536]},{\"wait\":400},{\"eval\":\"[window.__demo.state().selected, window.__demo.state().door.departing, window.__demo.state().door.leaves]\"},{\"waitFor\":\"window.__demo.state().phase === 'idle' && window.__demo.state().settled\"},{\"click\":[$SEAT_X,$SEAT_Y]},{\"wait\":700},{\"eval\":\"[window.__demo.state().door.leaves, window.__demo.state().door.departing]\"},{\"wait\":1200},{\"eval\":\"window.__demo.goTo('zaychess')\"},{\"waitFor\":\"window.__demo.state().phase === 'idle' && window.__demo.state().settled\"},{\"click\":[140,457]},{\"wait\":200},{\"click\":[160,525]},{\"wait\":200},{\"eval\":\"window.__demo.state().selected\"},{\"click\":[1200,800]},{\"wait\":200},{\"eval\":\"[window.__demo.state().selected, document.activeElement.tagName]\"},{\"click\":[60,457]},{\"wait\":300},{\"eval\":\"window.__demo.state().selected\"}]"
if clean && js 'v[0][0] === "zaybot" && v[0][1] === null && v[0][2] === 0 && v[1][0] === 1 && v[2] === "zaychess" && v[3][0] === null && v[3][1] === "BODY" && v[4] === "zaychess"' "[$(evalN 1),$(evalN 2),$(evalN 4),$(evalN 5),$(evalN 6)]"; then pass "reflexes: a double-click is one click, an armed click at ($SEAT_X,$SEAT_Y) opens, caption text keeps the presentation, the head presents"; else fail "reflexes: $(evalN 1) $(evalN 2) $(evalN 4) $(evalN 5) $(evalN 6)"; fi

# Exits and homes: the void dismisses like Escape, Escape returns focus to the rail, the name goes home.
run exits --query skipIntro=1 --steps "[$READY,$PARK,{\"wait\":300},{\"eval\":\"window.__demo.goTo('zaychess')\"},{\"waitFor\":\"window.__demo.state().phase === 'idle' && window.__demo.state().settled\"},{\"click\":[1200,800]},{\"wait\":200},{\"eval\":\"window.__demo.state().selected\"},{\"eval\":\"window.__demo.goTo('zaychess')\"},{\"waitFor\":\"window.__demo.state().phase === 'idle' && window.__demo.state().settled\"},{\"key\":\"Escape\"},{\"wait\":200},{\"eval\":\"[window.__demo.state().selected, document.activeElement.tagName]\"},{\"eval\":\"document.querySelector('#rail a[data-index=\\\"4\\\"]').focus(); 1\"},{\"key\":\"Enter\"},{\"wait\":300},{\"eval\":\"[window.__demo.state().selected, document.activeElement.id]\"},{\"key\":\"Escape\"},{\"wait\":200},{\"eval\":\"[window.__demo.state().selected, document.activeElement.dataset.index]\"},{\"eval\":\"window.__demo.goTo('sonar')\"},{\"waitFor\":\"window.__demo.state().phase === 'idle' && window.__demo.state().settled\"},{\"click\":[82,48]},$IDLE,{\"eval\":\"[window.__demo.state().selected, window.__demo.state().current]\"},{\"key\":\"End\"},$IDLE,{\"key\":\"k\"},$IDLE,{\"eval\":\"window.__demo.state().current\"},{\"key\":\"Tab\"},{\"key\":\"Tab\"},{\"key\":\"End\"},$IDLE,{\"wait\":200},{\"eval\":\"[window.__demo.state().current, document.activeElement.dataset.index]\"},{\"key\":\"Enter\"},{\"wait\":300},{\"eval\":\"window.__demo.state().selected\"},{\"key\":\"Home\"},$IDLE,{\"wait\":200},{\"eval\":\"[window.__demo.state().current, window.__demo.state().selected]\"}]"
if clean && js 'v[0] === null && v[1][0] === null && v[1][1] === "BODY" && v[2][0] === "zaychess" && v[2][1] === "cap-open" && v[3][0] === null && v[3][1] === "4" && v[4][0] === null && v[4][1] === "diffusion" && v[5] === "ear" && v[6][0] === "asteroids" && v[6][1] === "9" && v[7] === "asteroids" && v[8][0] === "diffusion" && v[8][1] === "diffusion"' "[$(evalN 2),$(evalN 4),$(evalN 6),$(evalN 7),$(evalN 9),$(evalN 10),$(evalN 11),$(evalN 12),$(evalN 13)]"; then pass 'exits: void and Escape dismiss, Escape refocuses the rail only on the keyboard journey, the name goes home, End carries focus, Home travels'; else fail "exits: $(evalN 2) $(evalN 4) $(evalN 6) $(evalN 7) $(evalN 9) $(evalN 10) $(evalN 11) $(evalN 12) $(evalN 13)"; fi

# ---- the rail ------------------------------------------------------------------------------------
# Numerals: only the current tick is numbered at rest; a pointed-at tick numbers and names
# itself; a drag along the rail scrubs to the station under the pointer.
run rail --query skipIntro=1 --steps "[$READY,$PARK,{\"wait\":1200},{\"eval\":\"[...document.querySelectorAll('#rail a')].map(a=>+getComputedStyle(a.querySelector('.no')).opacity)\"},{\"eval\":\"window.__demo.locate('curve-explorer').tick\"},{\"glide\":[[60,860],[1378,398]],\"ms\":400},{\"wait\":500},{\"eval\":\"[window.__demo.state().focus, +getComputedStyle(document.querySelector('#rail a.is-focus .no')).opacity, +getComputedStyle(document.querySelector('#rail a.is-focus .t')).opacity]\"},{\"shot\":\"rail-hover\"},{\"drag\":[[1378,398],[1378,470]],\"ms\":300},$IDLE,{\"eval\":\"[window.__demo.state().current, window.__demo.state().selected]\"}]"
if clean && js 'v[0][0] === 1 && v[0].slice(1).every((o) => o === 0) && Math.abs(v[1].y - 398) < 2 && v[2][0] === "curve-explorer" && v[2][1] === 1 && v[2][2] === 1 && v[3][0] === "zaybot" && v[3][1] === null' "[$(evalN 1),$(evalN 2),$(evalN 3),$(evalN 4)]"; then pass 'rail: current numbered, hover numbers and names, a drag scrubs'; else fail "rail: $(evalN 1) $(evalN 2) $(evalN 3) $(evalN 4)"; fi

# The hover title is a target: gliding from the tick onto the title keeps it shown, and a click there presents.
run railtitle --query skipIntro=1 --steps "[$READY,$PARK,{\"wait\":1200},{\"glide\":[[60,860],[1378,398]],\"ms\":400},{\"wait\":400},{\"glide\":[[1378,398],[1250,398]],\"ms\":300},{\"wait\":300},{\"eval\":\"[window.__demo.state().focus, document.getElementById('rail').classList.contains('is-hot'), +getComputedStyle(document.querySelector('#rail a.is-focus .t')).opacity]\"},{\"click\":[1250,398]},{\"wait\":300},{\"eval\":\"window.__demo.state().selected\"}]"
if clean && js 'v[0][0] === "curve-explorer" && v[0][1] === true && v[0][2] === 1 && v[1] === "curve-explorer"' "[$(evalN 1),$(evalN 2)]"; then pass 'rail: the hover title stays while reached for, and a click on it presents'; else fail "rail title: $(evalN 1) $(evalN 2)"; fi

# Hit rows: at n=40 the ticks are 17 px apart but every anchor is 24 px tall, and a click
# between two ticks lands on the nearer (10 at 40% of the way, 11 at 60%).
run hitrows --query "skipIntro=1&n=40" --steps "[$READY,$PARK,{\"wait\":1200},{\"eval\":\"[getComputedStyle(document.documentElement).getPropertyValue('--row'), Math.min(...[...document.querySelectorAll('#rail a')].map(a=>a.getBoundingClientRect().height)), window.__demo.locate('diffusion-2').tick.y, window.__demo.locate('reinforcement-learning-2').tick.y]\"},{\"click\":[1378,303]},{\"wait\":200},{\"eval\":\"window.__demo.state().selected\"},{\"key\":\"Escape\"},{\"click\":[1378,307]},{\"wait\":200},{\"eval\":\"window.__demo.state().selected\"}]"
if clean && js 'v[0][0].trim() === "17px" && v[0][1] >= 24 && Math.abs(v[0][2] - 296.5) < 1 && Math.abs(v[0][3] - 313.5) < 1 && v[1] === "diffusion-2" && v[2] === "reinforcement-learning-2"' "[$(evalN 1),$(evalN 2),$(evalN 3)]"; then pass 'rail: n=40 rows 17 px apart, anchors 24 px, the nearest tick wins'; else fail "rail hit rows: $(evalN 1) $(evalN 2) $(evalN 3)"; fi

# The portrait strip at n=24: 44 px tall, a tap lands on the nearest tick (between two, the
# nearer), a swipe along it scrubs, and a presentation follows a swipe.
run strip --mobile --w 390 --h 844 --query "skipIntro=1&n=24" --steps "[$READY,{\"wait\":600},{\"eval\":\"[Math.min(...[...document.querySelectorAll('#rail a')].map(a=>a.getBoundingClientRect().height)), window.__demo.locate('karchive').tick.x]\"},{\"tap\":[73,764]},{\"wait\":300},{\"eval\":\"window.__demo.state().selected\"},{\"tap\":[113,764]},{\"wait\":300},{\"eval\":\"window.__demo.state().selected\"},{\"swipe\":[[360,765],[200,765]],\"ms\":300},$IDLE,{\"eval\":\"[window.__demo.state().current, window.__demo.state().selected]\"},{\"shot\":\"strip-n24\"}]"
if clean && js 'v[0][0] >= 44 && Math.abs(v[0][1] - 71) < 2 && v[1] === "karchive" && v[2] === "polydiff" && v[3][0] === "curve-explorer-2" && v[3][1] === "curve-explorer-2"' "[$(evalN 1),$(evalN 2),$(evalN 3),$(evalN 4)]"; then pass 'strip: 44 px, taps land on the nearest tick, a swipe scrubs'; else fail "strip: $(evalN 1) $(evalN 2) $(evalN 3) $(evalN 4)"; fi

# On a phone OPEN is at least 44 px tall and 80 wide; a tap on the descriptor above it keeps the
# presentation (nothing departs); a tap on the numeral above a tick presents that work.
run mobile-open --mobile --w 390 --h 844 --query "skipIntro=1&stay=1" --steps "[$READY,{\"wait\":600},{\"eval\":\"window.__demo.goTo('zaychess')\"},{\"waitFor\":\"window.__demo.state().phase === 'idle' && window.__demo.state().settled\"},{\"eval\":\"(r => [r.width, r.height, Math.round(r.left + r.width / 2), Math.round(r.top - 16)])(document.getElementById('cap-open').getBoundingClientRect())\"},{\"eval\":\"(r => { window.__t = [Math.round(r.left + r.width / 2), Math.round(r.top - 16)]; return 1; })(document.getElementById('cap-open').getBoundingClientRect())\"},{\"tap\":[195,574]},{\"wait\":500},{\"eval\":\"[window.__demo.state().selected, window.__demo.state().door.departing, window.__demo.state().door.leaves]\"},{\"eval\":\"(r => [Math.round(r.left + r.width / 2), Math.round(r.top - 6)])(document.querySelector('#rail a[data-index=\\\"5\\\"] .no').getBoundingClientRect())\"},{\"tap\":[212,734]},{\"wait\":500},{\"eval\":\"window.__demo.state().selected\"}]"
if clean && js 'v[0][0] >= 80 && v[0][1] >= 44 && Math.abs(v[0][2] - 195) < 4 && Math.abs(v[0][3] - 574) < 4 && v[1][0] === "zaychess" && v[1][1] === null && v[1][2] === 0 && Math.abs(v[2][0] - 212) < 4 && Math.abs(v[2][1] - 734) < 6 && v[3] === "zaybot"' "[$(evalN 2),$(evalN 4),$(evalN 5),$(evalN 6)]"; then pass 'mobile: OPEN is 44 px, a tap on the descriptor is inert, the numeral above a tick is part of it'; else fail "mobile open: $(evalN 2) $(evalN 4) $(evalN 5) $(evalN 6)"; fi

# ---- semantics ------------------------------------------------------------------------------------
# Tab: the name, then work 01. Enter presents and moves focus to Open, with the two-step said
# by the live region and aria-describedby; names are normal case (no CSS uppercase leaks).
run semantics --query skipIntro=1 --steps "[$READY,{\"wait\":300},{\"key\":\"Tab\"},{\"eval\":\"document.activeElement.id\"},{\"key\":\"Tab\"},{\"eval\":\"document.activeElement.dataset.index\"},{\"key\":\"Enter\"},{\"wait\":300},{\"eval\":\"[window.__demo.state().selected, document.activeElement.id, document.getElementById('cap-open').getAttribute('aria-describedby'), document.querySelector('#rail a[data-selected]').getAttribute('aria-describedby'), document.getElementById('announce').textContent, document.getElementById('cap-hint').textContent]\"},{\"a11y\":true}]"
a11yOK() {
  printf '%s\n' "$RES" | grep -q 'link "Diffusion, Research, Diffusion models that design molecules for mutant p53"' \
  && ! printf '%s\n' "$RES" | grep -q 'link "DIFFUSION\|link "RÉSUMÉ\|link "OPEN' \
  && [ "$(printf '%s\n' "$RES" | grep -n 'link "Jeremy Zay, home"' | head -1 | cut -d: -f1)" -lt "$(printf '%s\n' "$RES" | grep -n 'link "Diffusion, ' | head -1 | cut -d: -f1)" ]
}
if clean && js 'v[0] === "home" && v[1] === "0" && v[2][0] === "diffusion" && v[2][1] === "cap-open" && v[2][2] === "cap-hint" && v[2][3] === "cap-hint" && /selected\. .*Press Enter to open\./.test(v[2][4]) && /Press Enter to open/.test(v[2][5])' "[$(evalN 1),$(evalN 2),$(evalN 3)]" && a11yOK; then pass 'semantics: name then work 01 on Tab, two-step announced, normal-case names'; else fail "semantics: $(evalN 1) $(evalN 2) $(evalN 3 | cut -c1-160)"; fi

# locate: real clicks at the centres it reports select the work, on the step and on the tick.
run locate --query skipIntro=1 --steps "[$READY,$PARK,{\"wait\":1200},{\"eval\":\"window.__demo.locate('zaybot')\"}]"
STEP_X="$(js2 'Math.round(v.step.x)' "$(evalN 1)")"; STEP_Y="$(js2 'Math.round(v.step.y)' "$(evalN 1)")"; TICK_X="$(js2 'Math.round(v.tick.x)' "$(evalN 1)")"; TICK_Y="$(js2 'Math.round(v.tick.y)' "$(evalN 1)")"
run locate-click --query skipIntro=1 --steps "[$READY,$PARK,{\"wait\":1200},{\"click\":[$STEP_X,$STEP_Y]},{\"wait\":200},{\"eval\":\"window.__demo.state().selected\"},{\"key\":\"Escape\"},{\"eval\":\"window.__demo.goTo('diffusion')\"},{\"key\":\"Escape\"},{\"waitFor\":\"window.__demo.state().phase === 'idle' && window.__demo.state().settled\"},{\"click\":[$TICK_X,$TICK_Y]},{\"wait\":200},{\"eval\":\"window.__demo.state().selected\"}]"
if clean && js 'v[0] === "zaybot" && v[1] === "zaybot"' "[$(evalN 1),$(evalN 3)]"; then pass "locate: clicks at the step ($STEP_X,$STEP_Y) and the tick ($TICK_X,$TICK_Y) select the work"; else fail "locate: $(evalN 1) $(evalN 2)"; fi

# ---- shading ------------------------------------------------------------------------------------
if node "$ROOT/tools/check-tones.mjs" "$HARNESS" > "$OUT/tones.log" 2>&1; then pass 'tones: three families apart at 8 roll angles, stone neutral beyond the light'; else fail 'tones: check-tones.mjs (see shots/wip/regress/tones.log)'; fi
if node "$ROOT/tools/check-pool.mjs" "$HARNESS" > "$OUT/pool.log" 2>&1; then pass "pool: $(tail -1 "$OUT/pool.log" | sed 's/^PASS: //' | cut -c1-260)"; else fail "pool: $(grep -A4 '^FAIL' "$OUT/pool.log" | tail -4 | tr '\n' ' ' | cut -c1-400) (see shots/wip/regress/pool.log)"; fi

printf '\n%s\n' "$([ "$FAILED" = 0 ] && printf 'ALL %s CHECKS PASSED' "$CHECKS" || printf 'SOME OF %s CHECKS FAILED' "$CHECKS")"
exit $FAILED
