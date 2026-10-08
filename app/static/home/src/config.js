// Every tuning value in the prototype lives here, named. Units: one "beam" = the
// square cross-section of the tribar; seconds; radians unless stated.

export const DIM = {
  beam: 1,            // cross-section of every block
  span: 5.2,          // centre-line length of one side when it has a single step (pure tribar)
  rise: 0.17,         // drop between consecutive steps on a side
  hover: 0.78,        // height of the light above a tread
  hop: 0.1,           // extra arc height when the light crosses from one tread to the next
  cornerInset: 0.3,   // how far before/after a corner the light leaves the straight line
  minSteps: 3,        // a tribar needs one block per side
  liftReach: 0.7,     // beams: more than any block ever stands proud (a selection 0.4 landing on
                      // a step the idle life has lifted 0.26, or the arrival settle 0.55)
  sinkReach: 0.05,    // beams: more than any block ever sinks below its bearing (the idle lift's
                      // settle); the seam's phantom set is proven complete over both ranges
};

export const PALETTE = {
  // Linear-light values. Stone and air are strictly neutral (R = G = B).
  stoneAlbedo: 0.78,
  // Vermilion #ff4a1c: the one hue, and it means exactly one thing, "you are here".
  accentDisplay: [1.0, 0.29, 0.11],   // sRGB-encoded, for additive glows composited in display space
  accentLinear: [1.0, 0.0685, 0.0116], // the same colour in linear light, for lighting the stone
};

// The light is the theme's --accent (static/site/tokens.css), when there is a page to read it
// from and it is a #rrggbb colour; otherwise (Node, the proofs, an odd value) the vermilion above.
{
  const hex = typeof document === 'undefined' ? ''
    : getComputedStyle(document.documentElement).getPropertyValue('--accent').trim();
  const m = /^#([0-9a-f]{2})([0-9a-f]{2})([0-9a-f]{2})$/i.exec(hex);
  if (m) {
    const display = m.slice(1).map((h) => parseInt(h, 16) / 255);
    const linear = (c) => (c <= 0.04045 ? c / 12.92 : ((c + 0.055) / 1.055) ** 2.4);
    PALETTE.accentDisplay = display;
    PALETTE.accentLinear = display.map(linear);
  }
}

export const PLACE = {
  // The air of the hall, in linear light. For scale: the monument's darkest lit family is
  // about 0.05 (67/255), so even the brightest air here sits far below the stone.
  airDeep: 0.0009,     // top of the frame (4/255): near-black, the ceiling is beyond sight
  airLift: 0.0105,     // bottom of the frame (27/255): charcoal, the air thick with mist
  rampDrift: 0.22,     // fraction of the frame height the ramp wanders under the noise
  noiseScale: 2.2,     // noise cells across the frame's height
  drift: [0.02, 0.03], // cells per second the mist moves, sideways and down: slow enough to be felt, not watched
  pocket: 0.0032,      // extra lift behind the monument so its darkest faces still read as silhouette
  pocketReach: 1.25,   // radius of that pocket, in monument radii
  mist: 0.0085,        // ground mist pooling under the monument, at its thickest (adds ~15/255)
  mistReach: 1.7,      // its horizontal reach, in monument radii
  footDepth: 0.9,      // radii below the centre where the monument's foot is: the mist starts there
  vignette: 0.22,      // how far the corners fall away
  grain: 0.014,        // display units; also the dither that keeps the ramp from banding
};

export const SHADING = {
  // Light directions are in STRUCTURE space, fixed to the stone, so the three visible face
  // families (+x, +y, +z) keep three fixed tones at every roll: with a screen-fixed key two
  // families must tie somewhere in every 120 degrees of turn. Chosen so that at the first
  // station of ten works the key reads as upper left, toward the viewer, and the family
  // tones come out 0.15 / 0.51 / 0.86 (x / z / y): a guaranteed gap of 0.35 in linear light.
  keyDir: [-0.3856, 0.7711, 0.5067],
  fillDir: [0.4219, 0.7264, -0.5426], // ~105 degrees round from the key; lifts +x and +y a little
  ambient: 0.014,
  key: 1.0,
  fill: 0.15,
  fillWrapPower: 1.6,
  keyWrapPower: 2.6,             // >1 steepens the three-tone separation between face families
  topLight: 0.09,                // a weak SCREEN-fixed light from straight above (stage +y): treads keep a
                                 // slight lift at every roll, so no station reads as lit from below; it is
                                 // a function of face orientation only, and far weaker than the key
  aoStrength: 0.85,
  aoBias: 0.006,
  jointDarken: 0.55,
  bevelGain: 0.3,
  lineWidthPx: 1.1,
  jointOpen: 0.03,               // beams: a joint between two sides opens into two free edges (bright
                                 // bevels) over this much separation, and closes the instant they touch
  grainAmount: 0.018,
  mottling: 0.11,
  blockVariance: 0.045,          // each block is its own piece of stone
  speckle: 0.035,
  wearWidth: 0.045,               // beams: soft lightening toward free edges, like a worn arris
  wearGain: 0.07,
  mistFloor: 0.07,                // brightness multiplier far from the focus
  mistInner: 0.3,               // radii as a fraction of the monument's bounding radius
  mistOuter: 1.75,
  mistFocus: 0.55,               // where the stone's mist is brightest: this fraction of the way from the
                                 // dock to the monument's centre, so the lit end sits in the clearest air
  // The light (src/monument.js, src/hold.js) lights every surface by one law, its door's recess
  // included: power x cosine x falloff of the distance from the light as that block sees it.
  glowRadius: 1.35,              // beams: the falloff's scale (src/door.js falloff)
  glowPower: 2.0,                // so right under it, resting over a tread, a held face is just into the shoulder
  dimSelected: 0.42,             // how far the rest of the monument recedes when a work is selected
  lanternWhite: [0.17, 0.15, 0.14], // linear, per unit of the light's red: what it adds to a face it does not hold, a
                                 // warm white (sRGB saturation 0.09, under any tint that reads as a colour)
  lanternEdge: 0.35,             // a free arris or worn edge catches this much more of the light
  lanternHold: [0.11, 0.16],     // beams: it holds a face while its foot on the face's plane lies within the first of
                                 // the face, and lets it go by the second (src/hold.js)...
  lanternReach: 0.03,            // ...if it reaches all of it: resting over the face's step, at the face's farthest
                                 // point it still gives this share of what it gives right under itself...
  lanternLetGo: [0.012, 0.02],   // ...and from wherever it is, it lets such a face go as that share falls through this
  moteRed: [1.0, 1.8],           // beams from the light on screen: a mote of dust carries its hue within the first and
                                 // none beyond the second (src/dust.js)
  // The door (src/door.js, src/monument.js): a slot in the presented step's riser, its leading face,
  // with a box cavity behind it. The slot sits low enough that a seated step hides it behind the
  // next step; the selection lift (0.4) reveals it. Its inside is lit by the light alone, and only
  // where the light can reach through the opening (or from inside): no glow is painted.
  doorWidth: 0.34,               // beams, along the wall axis
  doorHeight: 0.26,              // beams, down the riser
  doorDrop: 0.2,                 // beams: the slot's centre below the nosing
  doorDepth: 0.14,               // beams: how deep the cavity runs behind the riser...
  doorDepthMax: 0.3,             // ...and never more than this share of a short step's length
  lightRadius: 0.058,            // beams: the light's burning core (src/lantern.js), the source the cavity's
                                 // penumbrae are sized by
  doorAmbient: 0.05,             // linear light of the hall's neutral air as the recess sees it through the
                                 // opening: times the opening's form factor, near-black, darkest at the back
  doorKeySoft: 0.02,             // rad: the key's apparent radius as the recess sees it, so the patch it lets fall
                                 // inside is crisp but antialiased (about a device pixel at the cavity's depth)
  doorOwn: 0.01,                 // irradiance (per unit of the light) by which its light owns the recess's stone where it
                                 // lands: under 0.01 linear of red, too dark to read against even the darkest grey, so
                                 // wherever red is seen in the recess the key's patch has gone (the face-by-face rule of
                                 // src/hold.js, at the scale of the patch: its edge is the opening's shadow)
  doorKnee: 0.6,                 // linear: above this the flooded recess rolls off with its hue kept (no orange clip)
  doorPorch: 0.3,                // beams: where the light lines up in front of the opening before it goes in
  doorLean: 0.1,                 // beams in front of the riser the light leans out to while the way in is pointed at:
                                 // just past the nosing, its own radius clear of the riser's plane, so its beam
                                 // reaches down into the opening and lights the sill
  doorArc: 0.12,                 // beams: how high it rises over the nosing on its way there
};

export const MOTION = {
  lightOmega: 11,         // rad/s, critically damped: the light is weightless
  // The roll is a planned journey (src/mover.js): minimum-jerk, so it builds speed
  // quadratically from rest, the launch of a heavy thing, and lands at rest. Its length is
  // set by the ANGLE the monument turns through, the same visual law at every scale.
  rollLaunch: 0.525,      // s: a journey of no distance still takes this long: the mass of
                          // the thing; one station at ten works (36 degrees) comes out at 0.7 s
  rollHalfLap: 0.875,     // s added per half lap of roll: a half lap, the longest shortest-way
                          // journey, takes 1.4 s at any n
  rollBeyond: 0.2,        // s per further half lap: the lap shift (src/voyage.js) leaves about one lap at
                          // most to roll (it keeps the input's direction and the stone's room to stop)...
  rollLongest: 1.5,       // s: ...and no roll is planned longer than this: a held key seats within 1.6 s
  trailSeconds: 0.17,     // how far back in time the light's comet reaches
  trailFullSpeed: 3.5,    // stations/s at which the comet is fully visible
  passLift: 0.07,         // steps rise a touch as the light passes over them
  passReach: 0.9,         // stations either side of the light that feel it
  passSpeed: 5,           // light speed (stations/s) at which the effect is full
  passRate: 14,           // 1/s: the pass follows the light's position this quickly, no spring
  // Step grammar (src/lifts.js): a step rises fast and stops dead, falls faster and stops
  // dead, and after each stop sinks once into its bearing by a few percent of the travel.
  hoverLift: 0.11,        // beams: the pointed-at step
  selectLift: 0.4,        // beams: the presented step rises to meet the light
  stepRise: 0.17,         // s: a step answers the pointer at once
  stepFall: 0.14,         // s: and drops back faster, under its own weight
  stepSink: 0.04,         // fraction of the travel the step sinks after a stop...
  stepSinkRate: 24,       // 1/s: ...peaking at 1/rate and gone by 6/rate (250 ms)
  tiltMax: 0.125,         // ~7 degrees: enough to open the seam by about one beam
  tiltGain: 0.0004,       // radians per CSS pixel of pointer travel: a sweep opens the seam, careful aiming barely does
  tiltHold: 0.3,          // time constant with which the requested tilt bleeds away at rest,
                          // and while the pointer is on a step (the request is frozen then, so
                          // the target holds still while the visitor aims)
  tiltOmega: 9,
  tiltLockOmega: 19,      // stiffer once the pointer rests: the paradox "snaps" shut
  tiltLockBelow: 0.012,   // a request this small is dropped, once the pointer has rested (a moving
                          // pointer may build it up from nothing: an ordinary sweep must open the seam)
  tiltRest: 0.06,         // s without a pointer move before the pointer counts as resting: pointer events
                          // are not synced to frames (a 90 Hz trackpad on a 120 Hz display skips some)
  tiltZeta: 0.82,
  // Wheel and trackpad (src/input.js). A notched mouse is one station per notch; a trackpad
  // scrubs the light in proportion to the finger and snaps to a station on release.
  wheelPerStation: 170,   // trackpad deltaY (CSS px) per station
  wheelNotchMin: 50,      // CSS px: a lone delta at least this large is a mouse notch, not a finger
  wheelNotchHold: 0.03,   // s: a lone large delta is held this long for a follow-up before it counts as a notch
  wheelNotchGap: 0.025,   // s: two equal large deltas closer than this are one gesture (a trackpad flick
                          // arrives frame-synced at 8-17 ms); a physical detent cannot repeat faster
  wheelStreamGap: 0.1,    // s of silence that ends a trackpad stream
  wheelSnapDelay: 0.14,   // seconds of wheel silence before the position snaps to a station
  wheelGestureMax: 2,     // stations: one stream, fling included, moves at most this far (soft, tanh)
  snapBias: 0.22,         // a gesture that travels at least this far past a station commits to the next
  dragPerStation: 110,    // CSS px of swipe that count as a full station...
  swipeMax: 1,            // ...and one swipe moves exactly this many, however long (soft, tanh)
  // Idle life, timed from the visitor's last touch while the monument is seated (src/idle.js).
  liftFirst: 9,           // idle seconds before the first step lifts on its own...
  liftEvery: 12,          // ...and between lifts
  liftRise: 0.55,         // s: the step leaves its bearing, easing out: slower than a step
                          // answering the visitor, this one moves of its own accord
  liftHang: 0.9,          // s: hangs
  liftFall: 0.32,         // s: drops, accelerating, to a dead stop
  liftHeight: 0.26,       // beams: clear of the hover (0.11), well under a selection (0.4)
  swellFirst: 3.5,        // idle seconds before the first lap swell: early, it is the hint that teaches the scroll direction
  swellEvery: 16,
  swellSpeed: 8,          // blocks per second
  swellMinLap: 1.4,       // s: a short loop still gets a readable lap
  swellWidth: 1.3,        // blocks: width of the crest
  swellGain: 1.0,         // brightening at the crest: with swellFace, about +25/255 on a lit face, far more on an arris
  swellFace: 0.4,         // the crest's share on a plain face (arrises and worn edges add their own)
  swellCentre: 0.5,       // the crest starts half a block past the visitor's own, so it leaves from under the light
  swellEnvelope: 8,       // the crest fades in and out over an eighth of the lap
  idleRenderEvery: 2,     // frames: while everything is settled and motion is allowed the frame is drawn
                          // every n-th rAF (grain reseeds at 24 Hz and the rest of the idle life is slow)
  breatheHz: 0.21,
  breatheDepth: 0.07,
  arriveEps: 0.012,       // stations: closer than this to its target the stone counts as there...
  stoneRestSpeed: 0.05,   // stations/s: ...and slower than this as seated (the dock answers, dust leaves the tread)
  dimOmega: 7,            // rad/s, critically damped: the rest of the monument recedes behind a presented work
  maxFrame: 1 / 20,       // s: never integrate more than this in one frame (a stall must not become a leap)
  // A door is a link (src/main.js, src/door.js): the presented step's riser opens a slot; the
  // second action sends the light through it.
  doorOpen: 0.28,         // s: the slot opens as the light arrives, after the step has begun to rise
  doorReach: 0.6,         // stations: the slot opens only once the light is this close to the presented step
  doorDocked: 0.02,       // stations: the light leaves for the door only from this close to its dock
  doorSlide: 0.26,        // s: the light hops off the dock, over the nosing, down to the opening and in
  doorLineUp: 0.62,       // share of the slide spent reaching the porch, slowing as it lines up...
  doorEnter: 1.5,         // ...and its speed there, in units of the glide in's mean (an ease to rest inside)
  doorFade: 0.16,         // s: the canvas fades to the void from the moment the light is in...
  doorTotal: 0.42,        // s: ...and the link follows the fade, by this long after the slide began at the latest
  doorClose: 0.12,        // s: the slot shuts faster than the step drops (stepFall 0.14), so a seated
                          // step never shows an open door
  leanHome: 2.5,          // the light leaning in at a door (SHADING.doorLean) returns this many times brisker
                          // than it leaned when the presentation ends or moves on; its step stays up till it is home
  seamFade: 0.36,         // fraction of the seam segment over which the light cross-fades from the
                          // near end to the far start, so a tilt never makes it jump across the gap
};

export const INTRO = {
  duration: 2.6,          // s: the whole arrival, settle of the blocks included
  hurry: 8,               // time scale when the visitor acts during the intro
  fadeIn: [0.0, 0.8],
  converge: [0.1, 1.8],   // sides drift home, staggered
  stagger: 0.16,
  swing: [0.0, 1.85],     // camera swings toward the true angle...
  snap: [1.85, 1.98],     // ...and the last three degrees fall shut
  snapFrom: 0.055,
  // The swing, as seen landing on the first work docked at the left. It is a line of sight fixed
  // to the monument (src/intro.js), from the side that keeps the seam's two ends apart while
  // the corners join: they meet once, late, the far start sliding in front, and stay met
  // through the snap. Landing elsewhere it is turned about the true axis, by at most turnRange,
  // so the tear lies along the screen's long side; tools/check-geometry.mjs proves the whole range.
  startYaw: 0.46,
  startPitch: -0.2,
  turnRange: [-1.571, 1.222],   // radians, -90 to +70 degrees: inside the range where the seam's ends still meet once
  startRoll: -0.32,
  ignite: 1.98,           // the seam shuts: the light is struck, input is accepted, ready resolves
  uiIn: 2.12,             // the interface fades in (and stops being inert)
  settle: [0.5, 0.035, 0.9], // s: first block settles from here, next ones this much later, each over this long
  settleLift: 0.55,       // beams: how far the blocks hang above their bearings before settling
  startZoom: 0.84,        // the view pushes in slowly while the pieces come home
  sideDrift: 1.4,         // beams: how far apart the three sides hang
  sideDepth: 2.8,
  sideTwist: 0.2,
};

export const LAYOUT = {
  maxDpr: 2,
  portraitBelow: 1.05,    // aspect ratio under which the portrait layout is used
  // Landscape: the light rests left of the monument, on the caption's baseline.
  wide: {
    restAngle: Math.PI, restX: 0.325, right: 96, top: 56, bottom: 40,
    restMinX: 344,        // px: the light never rests closer to the left edge than this (the caption's room)...
    restMinXNarrow: 400,  // ...and under narrowBelow a little further, so the longest title keeps a real leader
    narrowBelow: 1200,
    capReach: 480,        // px: the caption never sits further left of the light than this: on a wide monitor
                          // caption, light and rail stay one reading span instead of spreading to the corners
    railReach: 320,       // px: nor the rail further right of the monument's edge than this
  },
  // Portrait: the light rests below the monument, plumb above the caption.
  // `below` is the least height kept free under the dock for caption, index and links; the
  // interface measures what they really need (the tallest caption at this width, the strip with
  // its numeral zone) and the layout keeps that much when it is more (src/frame.js resize).
  tall: { restAngle: -Math.PI / 2, topFraction: 0.133, topMin: 64, below: 300, side: 14 },
  roamPad: 0.25,
};

export const IMPACT = {
  // A strike: the seam locking shut (the arrival, and every tilt that springs shut again)
  // shakes the picture and flashes the exposure and the light, all decaying from the contact.
  shakeHz: 17,            // Hz: the shake's frequency, fast enough to read as a jolt, not a wobble
  shakeDecay: 13,         // 1/s: gone within a quarter second
  shakeAmount: 0.035,     // beams: the first swing (about 2 px at 1440 wide)
  flashDecay: 5.5,        // 1/s
  flashExposure: 0.5,     // the whole picture brightens by this fraction at the strike
  flashLantern: 1.6,      // the light flares by this fraction
  igniteRate: 7,          // 1/s: the struck light comes up to full power in about half a second
  tiltLock: 0.3,          // a tilt springing shut is at most this fraction of the arrival's strike...
  tearFrom: 0.04,         // rad: ...sized by the widest tear since the last lock: none below this (a hand
  tearFull: 0.1,          // coming to rest after an ordinary move), full from this (a real reveal)...
  tearDust: 0.06,         // ...and the seam raises dust only for a tear at least this wide
  shakeX: 0.6,            // the shake is mostly vertical: this much of it sideways
  life: 2.5,              // s after a strike by which its shake and flash have died away (settled test)
};

export const UI = {
  // The desktop rail: one tick per work, right edge. Tick spacing follows the height and the
  // count; the hit row does not fall below 24 px (WCAG 2.5.8): when the spacing does, the
  // anchors overlap and the nearest tick to the pointer wins (src/interface.js).
  rowMax: 24,             // px: tick spacing at most...
  rowMin: 12,             // px: ...and at least (24 works at 900 px tall still get 24 px)
  hitRow: 24,             // px: the least height of a rail anchor
  railReserve: 220,       // px: height kept clear of the rail for the masthead and the bottom margin
  hitRadius: 22,          // px: on the rail a pointer reaches the nearest tick this far away (or half
                          // the spacing, whichever is more); the portrait strip's tap fallback
  tapSlop: 6,             // px: a pointer may wander this far and still count as a tap
  tornReach: [3, 6],      // px: while the seam is torn a click on void takes a step drawn this close instead
  tapAfterDrag: 0.5,      // s: a click arriving this soon after a rail drag is the drag's own, ignored
  leaderGap: 16,          // px: between the caption and the leader line
  dockGap: 20,            // px: between the leader's end and the dock ring
  swapEvery: 140,         // ms: the caption changes at most this often while input repeats
  detailDip: 110,         // ms: the descriptor dips while its text changes under a moving selection
  tagOffset: 30,          // px: the hover tag sits this far outward from the block's edge
  tagClearance: 0.75,     // beams: how far outward from the tread's centre the tag sits (with tagOffset)
  tagRetreat: [1, 1.5, 2.1], // multiples of that reach tried, in four directions each, when the tag would run onto stone
                          // or onto the dock, the leader or the caption's head
  stripGap: 8,            // px: in portrait, OPEN (its whole 44 px target) stays this far above the strip's numeral zone
  armDelay: 350,          // ms: the second action (through the door) is accepted once the presentation is
                          // readable; a second click or Enter sooner is the first one's own double
  hashDelay: 250,         // ms: the station is written to the URL's hash this long after it last changed
  // Published to CSS (src/interface.js) so the stylesheet shares the timings it mirrors.
  capFade: 180,           // ms: the caption's cross-fade (swapEvery is tuned against it)
};

export const RECOVERY = {
  restoreTimeout: 4,      // seconds to wait for a lost WebGL context to come back before the
                          // scene is abandoned and the DOM index stands alone
  // A followed link has no timeout: a page still here after its navigation was stopped comes
  // back at the visitor's next click, key or wheel (src/intents.js), never while it may be loading.
};

