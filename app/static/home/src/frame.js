// The frame: one step of everything, in order, then a render when the picture can differ
// from the last one; and the plumbing that turns the state into uniforms. Nothing here
// decides anything for the visitor: intents (src/intents.js) move the targets and the frame
// follows them, asking intents only for the things a frame alone can know (what the pointer
// is over this frame, the moment the light is through the door).
//
// The door opens on arrival, not on selection: a far work is presented at once (caption,
// lift, the roll), but its slot stays shut until the light is within reach of the step. What
// is inside is lit only by the light, where it can reach (src/door.js): from the dock, above
// the tread and behind the riser, it cannot, so an open door holds only the hall's air and the
// key until the light goes to it. Pointing at the way in (OPEN, or the presented step) the
// light leans out over the nosing, its beam falling into the slot; leaving, it carries on along
// the same way, lines up with the opening (its beam climbing the back wall), glides in and
// floods the recess; the riser hides it from then on, but for what the opening shows, and the
// scene fades to the void on that look, the stone it lit kept dark round the glowing slot.
//
// One hue: the light lights every face by one law, and a face it holds (src/hold.js) is lit by it
// alone, every other face keeping the key's grey with the light only added: red never lies over
// grey (src/monument.js). Its hold on the stone never breathes.
//
// Under reduced motion the clock is frozen, so once everything has landed and nothing is
// pending the renderer is left alone until an intent marks the picture dirty. With motion
// allowed the idle life (grain, dust, the breathing light, the drifting air) changes the
// picture every frame but slowly, so a settled scene is drawn at a fraction of the rAF rate;
// an intent, a travel or an idle beat (src/idle.js) brings it back to full rate at once.
import * as THREE from 'three';
import { DIM, MOTION, INTRO, IMPACT, SHADING, UI, RECOVERY, PALETTE, SOUND } from './config.js';
import { Spring, easeOutCubic, smoothstep } from './spring.js';
import { tiltToward } from './tribar.js';
import { newFrame, doorFrame, toDoor, fromDoor, lightFor, insideness, createPath, slideOn, cavityLight } from './door.js';
import { createHold } from './hold.js';

const LANTERN_Z = 150;   // world z of the drawn light: in front of everything (it has no depth test anyway)
const SEAM_BEHIND = 0.05; // beams: how far behind the far start a hidden near-end fragment stands (clear of depth precision)
const LEAN_HOME = 0.004;  // share of its lean below which the light leaning in is home (well under a pixel)

/**
 * @param parts  everything main.js built: canvas, tribar, seam, stage, monument, lantern, dust,
 *               backdrop, intro, voyage, tilt, lifts, idle, ui, sound, state, works, flags
 * @param hooks  { pickStation(x, y), setFocus(i, source), leave(), ready(), abandon() }
 */
export function createFrame(parts, hooks) {
  const { canvas, tribar, seam, stage, monument, lantern, dust, backdrop, intro, voyage, tilt, lifts, idle, ui, sound, state, works, flags } = parts;
  const { light, stone } = voyage;
  const { arrival, door, departure, impact, pointer } = state;
  const reducedMotion = matchMedia('(prefers-reduced-motion: reduce)');
  const dim = new Spring(0, MOTION.dimOmega, 1);
  let arrivedAt = voyage.position, stoneMoving = false;
  let lastStamp = 0, raf = 0, ticks = 0, drawn = false;
  let contextDown = false, restoreTimer = 0;
  // The last hit test, reused while neither the pointer nor the stone has moved (the pose, the
  // tilt, every lift and the shake all still, this frame and the last): the idle life's swell
  // and grain change the picture, not what is under the pointer.
  const picked = { x: -2, y: -2, station: -1, still: false };
  let trailDrawn = false;
  // One reusable record of "this frame" for the modules that step (no per-frame garbage).
  const now = {
    calm: state.calm, hold: true, quiet: true, seated: false, dragging: false, light, clock: 0,
    currentBlock: -1, focusBlock: -1, selectedBlock: -1, heldBlock: -1, settling: null, beatBlock: -1, beatLift: 0,
  };
  const v3 = new THREE.Vector3(), w3 = new THREE.Vector3(), x3 = new THREE.Vector3(), px = { x: 0, y: 0 };
  const lightStage = new THREE.Vector3(), lightWorld = new THREE.Vector3(), farWorld = new THREE.Vector3(), drawnWorld = new THREE.Vector3();
  // The door: its frame this frame, the light as it sees it, the way in, the outline on screen.
  const doorAt = newFrame(), doorLight = [0, 0, 0], path = createPath();
  // The light leaning in at the door while the visitor points at the way in (OPEN, or the presented
  // step itself): a share of the way it would take, so going in it simply carries on.
  const lean = new Spring(0, MOTION.lightOmega, 1);
  let slideFrom = 0;   // the share of the way in the slide began from
  const lit = { L: [NaN, 0, 0], ho: -1, depth: -1, mean: 0, share: 0, inside: 0 };   // the last bounce solved
  const corner3 = [0, 0, 0], cornerW = [new THREE.Vector3(), new THREE.Vector3(), new THREE.Vector3()];
  let pinned = null;   // QA (doorPin): the light held at a door-frame point
  let sliding = false, fadeFrom = -1;   // departure time the fade to the void began
  const identity3 = new THREE.Matrix3();
  const seamPoint = tribar.blocks[0].center, point3 = [0, 0, 0], anchor3 = [0, 0, 0], near3 = [0, 0, 0], far3 = [0, 0, 0];
  const swing = [0, 0];   // the arrival's tilt this frame
  // The light on the stone: where each block sees it, and how far it holds each face (+x, +y, +z).
  const owner = createHold(tribar);
  const seenLight = new Float32Array(tribar.blocks.length * 3), faceOwn = new Float32Array(tribar.blocks.length * 3);
  const blockLight = [0, 0, 0], doorThere = [0, 0, 0], heldAt = [0, 0, 0];
  // What the sound hears this frame (src/sound.js), and what it measured the last one by.
  const heard = { rumble: 0, light: 0, swell: 0, swellHead: 0, swellPan: 0, blocks: tribar.blocks.length };
  const liftWas = new Float32Array(tribar.blocks.length);
  let sidesWere = -1, doorWas = 0;

  const blockOf = (station) => (station >= 0 ? tribar.stations[station].block : -1);
  /** 1 while two blocks touch, 0 once they stand SHADING.jointOpen apart (smooth between). */
  const shut = (apart) => { const x = Math.min(1, apart / SHADING.jointOpen); return 1 - x * x * (3 - 2 * x); };
  const structToWorld = (p, out) => stage.stageToWorld(stage.structToStage(p, v3), out);

  // ---- effects ---------------------------------------------------------------------------
  function mark() { state.dirty = true; }
  function strike(scale) { impact.age = 0; impact.scale = scale; sound.thud(scale); }
  /** Where a structure point lies across the screen, for the sound (-1 left .. 1 right, held in from the edges). */
  function panAt(structPoint) {
    stage.project(structPoint, px);
    return Math.max(-1, Math.min(1, px.x / stage.layout.width * 2 - 1)) * 0.7;
  }
  function treadOf(block) {
    const b = tribar.blocks[block];
    point3[0] = b.center[0]; point3[1] = b.center[1]; point3[2] = b.center[2];
    point3[b.tread] += b.half[b.tread];
    return point3;
  }
  function burstAt(structPoint, gain = 1) {
    // Dust leaves outward, away from the monument's centre.
    structToWorld(structPoint, w3);
    dust.burst(w3, w3.x - stage.base.x, w3.y - stage.base.y, state.clock, gain);
  }
  function burstFromTread(block, gain) {
    burstAt(treadOf(block), gain);
    sound.contact(gain);
  }

  // ---- layout ----------------------------------------------------------------------------
  let reserve = 0;   // portrait: what the caption and the strip need below the light (measured)
  function resize() {
    let layout = stage.resize(reserve);
    ui.setLayout(layout);
    if (layout.portrait) {
      const need = ui.portraitReserve(layout.height);
      if (need !== reserve) { reserve = need; layout = stage.resize(reserve); ui.setLayout(layout); }
    }
    dust.uniforms.uExtent.value.set(layout.width / (2 * layout.ppu), layout.height / (2 * layout.ppu));
    dust.uniforms.uPixelRatio.value = layout.dpr;
    lantern.trailUniforms.uPixelsPerBeam.value = layout.ppu * layout.dpr;
    const reach = (tribar.rhoMin + tribar.rhoMax) / 2;       // typical distance, dock to centre
    const cx = layout.restPx.x - reach * layout.dir.x * layout.ppu, cy = layout.restPx.y + reach * layout.dir.y * layout.ppu;
    backdrop.place(layout, cx, cy, tribar.radius * layout.ppu);
    monument.uniforms.uFocus.value.set(layout.rest.x - reach * SHADING.mistFocus * layout.dir.x, layout.rest.y - reach * SHADING.mistFocus * layout.dir.y);
    stage.mistRadii(monument.uniforms.uMist.value);
    picked.still = false;     // the same pointer is over a different picture
    mark();
  }
  const resizeObserver = new ResizeObserver(resize);

  // ---- the frame, in order ---------------------------------------------------------------
  function advanceArrival(dt) {
    arrival.sample = null;
    if (arrival.done) return;
    // The swing is turned once, for the dock the loop opens at (src/intro.js).
    if (arrival.time === 0) intro.dock(voyage.position, stage.layout.restAngle, stage.layout.portrait);
    arrival.time = Math.min(intro.duration, arrival.time + dt * arrival.rate);
    const sample = arrival.sample = intro.sample(arrival.time);
    const u = monument.uniforms;
    for (let k = 0; k < 3; k++) {
      const r = sample.sideRot[k];
      u.uSideOff.value[k].fromArray(sample.sideOff[k]);
      u.uSideRot.value[k].set(r[0], r[1], r[2], r[3], r[4], r[5], r[6], r[7], r[8]);
    }
    u.uAssembled.value = sample.assembled;
    if (!arrival.ignited && arrival.time >= INTRO.ignite) {
      // The seam shuts, and the light is struck from the impact: it is born at the seam and
      // settles onto the first step. From here the visitor is in: input is taken and the
      // page is ready, while the blocks finish settling under them.
      arrival.ignited = true;
      if (!state.calm && !flags.skipIntro) { strike(1); sound.ignite(); light.snap(voyage.position - 0.5); burstAt(seamPoint); }
      state.phase = 'idle';
      hooks.ready();
    }
    if (!arrival.live && arrival.time >= INTRO.uiIn) { arrival.live = true; ui.reveal(); }
    if (arrival.time >= intro.duration) {
      arrival.done = true;
      arrival.sample = null;
      for (let k = 0; k < 3; k++) { u.uSideOff.value[k].set(0, 0, 0); u.uSideRot.value[k].copy(identity3); }
      u.uAssembled.value = 1;
      if (!arrival.ignited) { arrival.ignited = true; state.phase = 'idle'; hooks.ready(); }
      if (!arrival.live) { arrival.live = true; ui.reveal(); }
    }
  }

  /** Stations between the light and the presented step, round the loop; 0 with nothing presented. */
  function lightAway() {
    if (state.selected < 0) return 0;
    let away = Math.abs(light.value - state.selected) % tribar.stepCount;
    return away > tribar.stepCount / 2 ? tribar.stepCount - away : away;
  }
  /** The light is at the presented step's dock and still: the one place it leaves for the door from. */
  const docked = () => lightAway() < MOTION.doorDocked && Math.abs(light.velocity) < MOTION.stoneRestSpeed;
  const doorWant = { open: 0, block: -1 };
  function wantDoor() {
    const block = blockOf(state.selected);
    // The light leaning in comes back to its dock before its door may shut or move (its step stays
    // up for it meanwhile: now.heldBlock).
    if (door.block >= 0 && lean.value > LEAN_HOME) { doorWant.block = door.block; doorWant.open = 1; return doorWant; }
    // A door still open on a step the visitor has left shuts there first, as that step drops.
    if (door.block >= 0 && door.block !== block && door.open > 0) { doorWant.block = door.block; doorWant.open = 0; return doorWant; }
    doorWant.block = block;
    // The slot is revealed by the rising step and opened by the arriving light; departing, it is open.
    const lifted = block >= 0 && (lifts.now[block] > 0 || state.calm);
    doorWant.open = block >= 0 && (departure.t >= 0 || (lifted && lightAway() < MOTION.doorReach)) ? 1 : 0;
    return doorWant;
  }
  function advanceDoor(dt) {
    // The slot opens as the light arrives and shuts faster than the step drops, so a seated
    // step never shows an open door. The link is followed once.
    const want = wantDoor();
    door.block = want.block;
    if (state.calm) door.open = want.open;
    else door.open = Math.min(1, Math.max(0, door.open + (want.open ? dt / MOTION.doorOpen : -dt / MOTION.doorClose)));
    // The slot is heard as it starts to slide: open from shut, or shut from wide open.
    if (door.block >= 0 && doorWas === 0 && door.open > 0) sound.door(true, state.calm ? 0.05 : MOTION.doorOpen, panAt(tribar.blocks[door.block].center));
    else if (door.block >= 0 && doorWas === 1 && door.open < 1) sound.door(false, state.calm ? 0.05 : MOTION.doorClose, panAt(tribar.blocks[door.block].center));
    doorWas = door.open;
    // Leaning in: only at a door wide open on the presented step, the light docked, the seam shut (as
    // for going in, so the way is the proven one), and only while the visitor points at the way in.
    // Going in, the lean is where the slide begins; with the light gone, it is spent.
    if (departure.t < 0) {
      const asked = state.peek || (state.focusSource === 'scene' && state.focus >= 0 && state.focus === state.selected);
      const presented = door.block >= 0 && door.block === blockOf(state.selected);
      lean.target = asked && !state.calm && presented && door.open === 1 && docked() && tilt.shut ? 1 : 0;
      // Called home by the presentation ending or moving on, it comes back briskly: its step waits.
      lean.omega = presented ? MOTION.lightOmega : MOTION.lightOmega * MOTION.leanHome;
      if (state.calm || (lean.target === 0 && lean.value < LEAN_HOME)) lean.snap(0); else lean.step(dt);
    } else if (departure.gone) lean.snap(0);
    if (departure.t < 0) fadeFrom = -1;
    if (departure.t < 0 || departure.gone) return;
    // The light leaves only through a door the eye can see and it can pass: the seam shut (on a
    // seam step a torn seam puts the far start in front of the riser; about 0.15 s), the slot
    // wide open, and the light at its dock, where its way over the nosing is proven clear.
    if (departure.t === 0 && (!tilt.shut || door.open < 1 || !docked())) return;
    departure.t += dt;
    // The scene fades to the void from the moment the light is in (its light leaves the outside
    // stone then, but for the spill through the opening), and the link follows the fade.
    if (fadeFrom < 0 && (lit.inside >= 0.5 || departure.t >= MOTION.doorTotal - MOTION.doorFade)) { fadeFrom = departure.t; ui.leaving(true); }
    if (fadeFrom >= 0 && departure.t >= fadeFrom + MOTION.doorFade) hooks.leave();
  }

  /** The cavity's direct light (mean and lit share, per unit power) for the light at L, solved again only when it moved. */
  function solveBounce(L, ho, depth) {
    if (L[0] === lit.L[0] && L[1] === lit.L[1] && L[2] === lit.L[2] && ho === lit.ho && depth === lit.depth) return lit;
    lit.L[0] = L[0]; lit.L[1] = L[1]; lit.L[2] = L[2]; lit.ho = ho; lit.depth = depth;
    return cavityLight(L, ho, depth, lit);
  }
  /** The door's uniforms, with the light at door-frame point L of the given power (breathing) and hold (not). */
  function doorUniforms(open, L, power, hold) {
    const u = monument.uniforms;
    if (!(door.block >= 0 && door.open > 0)) { u.uDoor.value.set(-1, 0, -1, SHADING.doorDepth); u.uDoorBounce.value = 0; lit.mean = lit.share = 0; lit.ho = -1; return; }
    const f = doorAt, next = (door.block + 1) % tribar.blocks.length;
    u.uDoor.value.set(door.block, open, next, f.depth);
    u.uDoorO.value.fromArray(f.origin);
    u.uDoorAxes.value.set(
      f.x === 0 ? 1 : 0, f.x === 1 ? 1 : 0, f.x === 2 ? 1 : 0,
      f.y === 0 ? 1 : 0, f.y === 1 ? 1 : 0, f.y === 2 ? 1 : 0,
      f.z === 0 ? 1 : 0, f.z === 1 ? 1 : 0, f.z === 2 ? 1 : 0,
    );
    u.uDoorLight.value.set(L[0], L[1], L[2], power);
    u.uDoorHold.value = hold;
    const v = stage.view;
    u.uDoorView.value.set(v[f.x], v[f.y], v[f.z]);
    // The block in front of the near end's last step is the far start's first cube: beside it, where the carry stands it.
    if (next === 0) u.uDoorShift.value.fromArray(seam.carry); else u.uDoorShift.value.set(0, 0, 0);
    u.uDoorBounce.value = PALETTE.stoneAlbedo * solveBounce(L, open * SHADING.doorHeight / 2, f.depth).mean;
  }
  /**
   * The light as each block sees it (src/door.js lightFor: its depth resolved from the block's side of
   * the seam; or, where the door places it, that point carried the same way), and the faces it holds
   * (src/hold.js), times `strength`: an unlit light holds nothing. Local to each block, like the
   * door's own light: nothing depends on distance along the view.
   */
  function lights(held, strength) {
    if (held) {
      fromDoor(doorAt, doorLight, heldAt);
      lightFor(tribar, owner.loopOf[door.block], light.value, seam.carry, doorThere);
    }
    for (let i = 0; i < tribar.blocks.length; i++) {
      lightFor(tribar, owner.loopOf[i], light.value, seam.carry, blockLight);
      for (let k = 0; k < 3; k++) seenLight[i * 3 + k] = blockLight[k] + (held ? heldAt[k] - doorThere[k] : 0);
    }
    owner.solve(seenLight, lifts.now, faceOwn, { strength, door: held ? door.block : -1 });
    monument.setLights(seenLight, faceOwn);
  }
  /** The opening's outline on screen (world x, y): corner (-y, -z) and its two edges, into cornerW. */
  function outline(ho) {
    for (let k = 0; k < 3; k++) {
      corner3[0] = 0; corner3[1] = k === 1 ? ho : -ho; corner3[2] = k === 2 ? SHADING.doorWidth / 2 : -SHADING.doorWidth / 2;
      structToWorld(fromDoor(doorAt, corner3, point3), cornerW[k]);
    }
    cornerW[1].sub(cornerW[0]); cornerW[2].sub(cornerW[0]);
    return cornerW;
  }

  function present() {
    const { clock } = state;
    const shake = impact.scale * Math.exp(-impact.age * IMPACT.shakeDecay) * Math.sin(impact.age * IMPACT.shakeHz * 2 * Math.PI) * IMPACT.shakeAmount;
    const flash = impact.scale * Math.exp(-impact.age * IMPACT.flashDecay);
    const sample = arrival.sample;
    const fade = sample ? sample.exposure : 1;
    const breathe = 1 + MOTION.breatheDepth * Math.sin(clock * MOTION.breatheHz * 2 * Math.PI);
    const struck = arrival.ignited ? 1 - Math.exp(-impact.age * IMPACT.igniteRate) + flash * IMPACT.flashLantern : 0;
    // The light's power, and its hold on the stone it lights (how much of the key it displaces):
    // the hold never breathes, so through the breath only the brightness moves and the hue stays.
    const steady = state.phase === 'intro' ? struck : 1 + flash * IMPACT.flashLantern;
    const lanternPower = steady * breathe, hold = Math.min(steady, 1);

    // The tilt turns about the point the light rests on at the stone's current position
    // (the dock, once seated), so the light never leaves its ring; through the seam that
    // point cross-fades between the two ends like the light itself, and never jumps.
    tribar.pathAt(stone.value, near3, 0); tribar.pathAt(stone.value, far3, 1);
    const across = tribar.seamBlend(stone.value);
    for (let k = 0; k < 3; k++) anchor3[k] = near3[k] + (far3[k] - near3[k]) * across;
    stage.setZoom(sample ? sample.zoom : 1);
    // The arrival's line of sight is fixed to the monument; seen from this dock it is this tilt.
    if (sample) tiltToward(sample.view, stage.layout.restAngle - tribar.thetaAt(stone.value) + sample.roll, swing);
    else swing[0] = swing[1] = 0;
    stage.setPose(
      stone.value, sample ? sample.roll : 0,
      swing[0] + tilt.yaw.value, swing[1] + tilt.pitch.value,
      shake * IMPACT.shakeX, shake, sample ? null : anchor3,
    );
    // The seam for this pose: where the far start's phantoms stand along the view, in front of
    // the near end and never inside it (src/seam.js).
    seam.solve(stage.view, sample, lifts.now);

    // Crossing the seam the light is drawn at both ends; each block sees one light between them,
    // weighted like the sprites (src/door.js lightFor; one place at rest).
    let blend = tribar.seamBlend(light.value);
    stage.structToStage(tribar.pathAt(light.value, undefined, 0), lightStage);
    // The door, and the light as it sees it: the drawn light, its depth resolved from the door's
    // side of the seam (src/door.js lightFor). On the way in the door places the light.
    const open = easeOutCubic(door.open);
    const doorOn = door.block >= 0 && door.open > 0;
    if (doorOn) doorFrame(tribar.blocks[door.block], lifts.now[door.block], doorAt);
    const wasSliding = sliding;
    sliding = doorOn && departure.t > 0;
    let held = false;
    if (doorOn && pinned) { doorLight[0] = pinned[0]; doorLight[1] = pinned[1]; doorLight[2] = pinned[2]; held = true; }
    else if (doorOn) {
      toDoor(doorAt, lightFor(tribar, tribar.blocks[door.block].station, light.value, seam.carry, point3), doorLight);
      if (sliding) {
        // From its dock, over the nosing, to the porch, in: carrying on from as far as it leaned.
        if (!wasSliding) { path.plan(doorLight, doorAt.depth); slideFrom = lean.value * path.alongTo(SHADING.doorLean); sound.enter(MOTION.doorSlide, panAt(doorAt.origin)); }
        path.at(slideOn(departure.t / MOTION.doorSlide, path.porch, slideFrom), doorLight);
        held = true;
      } else if (lean.value > 0) {
        // Leaning in: the first stretch of the same way, as far as just past the nosing.
        path.plan(doorLight, doorAt.depth);
        path.at(lean.value * path.alongTo(SHADING.doorLean), doorLight);
        held = true;
      }
    }
    if (held) { stage.structToStage(fromDoor(doorAt, doorLight, point3), lightStage); blend = 0; }
    stage.stageToWorld(lightStage, lightWorld);
    stage.stageToWorld(stage.structToStage(tribar.pathAt(light.value, undefined, 1), v3), farWorld);
    // Where the light is drawn: crossing the seam, between its two ends as the sprites are weighted.
    drawnWorld.lerpVectors(lightWorld, farWorld, blend);
    // Gone in at the door, the light reaches the outside only through the opening (the spill), and
    // the riser round the opening hides it from the eye.
    const ho = open * SHADING.doorHeight / 2;
    const inside = doorOn ? insideness(doorLight, ho) : 0;
    lit.inside = inside;
    // Going in, it leaves the outside stone: inside the wall it reaches it only through the opening.
    const outside = lanternPower * smoothstep(0.5, 1, 1 - inside);
    lantern.setLight(lightWorld, farWorld, LANTERN_Z, lanternPower, blend);
    if (inside > 0) { outline(ho); lantern.setMask(inside, cornerW[0], cornerW[1], cornerW[2]); } else lantern.setMask(0);
    lantern.uniforms.uTime.value = clock;
    const comet = state.calm || departure.t > 0 ? 0 : Math.min(1, Math.abs(light.velocity) / MOTION.trailFullSpeed) * lanternPower;
    if (comet > 0 || trailDrawn) {     // at rest the comet is invisible and its points are left alone
      for (let k = 0; k < lantern.trailPoints; k++) {
        const age = (k + 1) / lantern.trailPoints;
        const s = light.value - light.velocity * age * MOTION.trailSeconds;
        structToWorld(tribar.pathAt(s, undefined, 0), w3);
        structToWorld(tribar.pathAt(s, undefined, 1), x3);
        lantern.setTrailPoint(k, w3, x3, LANTERN_Z, comet * (1 - age) ** 2, tribar.seamBlend(s));
      }
      lantern.commitTrail();
      trailDrawn = comet > 0;
    }

    monument.setDynamics(lifts.now, lifts.emphasis, seam);
    const u = monument.uniforms;
    const lightX = drawnWorld.x, lightY = drawnWorld.y;
    u.uStageRot.value.copy(stage.stageRot);
    u.uRigRot.value.setFromMatrix4(stage.rig.matrixWorld);   // the tilt: a bumped normal into world space
    u.uLantern.value = outside;
    u.uTime.value = clock;
    u.uExposure.value = fade * (1 + flash * IMPACT.flashExposure);
    u.uDim.value = dim.value;
    u.uSelected.value = blockOf(state.selected);
    u.uSwell.value.set(idle.swellHead, idle.swellAmp);
    // Where a phantom hides it the near end stands just behind the far start (src/monument.js).
    u.uSeamDepth.value = (seam.offset + SEAM_BEHIND) * stage.depthPerBeam;
    // A corner's joint line is drawn only while its two blocks touch: the seam's while it is shut.
    u.uCorner.value.set(shut(seam.tear), sample ? shut(sample.apart[1]) : 1, sample ? shut(sample.apart[2]) : 1);
    doorUniforms(open, doorLight, lanternPower, hold);
    lights(held, hold);
    backdrop.uniforms.uTime.value = clock;
    backdrop.uniforms.uExposure.value = fade;
    dust.uniforms.uTime.value = clock;
    dust.uniforms.uFade.value = fade;
    dust.uniforms.uLight.value.set(lightX, lightY, outside);
  }

  function noteArrival() {
    if (state.phase === 'intro') return;
    const moving = Math.abs(stone.value - voyage.position) > MOTION.arriveEps || Math.abs(stone.velocity) > MOTION.stoneRestSpeed;
    // The dock answers when the monument seats a new station.
    if (stoneMoving && !moving && !voyage.scrubbing && voyage.position !== arrivedAt) {
      arrivedAt = voyage.position;
      ui.arrive();
      sound.seat(voyage.current());
      if (!state.calm) burstAt(tribar.stations[voyage.current()].tread);
    }
    stoneMoving = moving;
    state.phase = moving && voyage.position !== arrivedAt ? 'travel' : 'idle';
  }

  const tagAt = { x: 0, y: 0 }, tagSize = { w: 0, h: 0 };
  const CORNERS = [[0, 0], [-1, -1], [1, -1], [-1, 1], [1, 1]];
  /** Would a tag centred here run onto stone (its centre and corners are hit-tested like a
   *  pointer), or onto the dock, the leader or the caption's head (it would read as a caption)? */
  function tagCovers(x, y) {
    if (ui.onFurniture(x, y, tagSize.w, tagSize.h)) return true;
    const hw = tagSize.w / 2 - 2, hh = tagSize.h / 2 - 2;
    for (let k = 0; k < CORNERS.length; k++) {
      if (stage.pick(x + CORNERS[k][0] * hw, y + CORNERS[k][1] * hh, lifts.now, seam) >= 0) return true;
    }
    return false;
  }
  // Retreat directions, in units of the outward one: in portrait the band below the light is
  // the caption's, so the tag tries either side first.
  const RETREAT_WIDE = [[1, 0], [-1, 0], [0, 1], [0, -1]], RETREAT_TALL = [[0, 1], [0, -1], [1, 0], [-1, 0]];
  function point() {
    if (state.phase !== 'intro' && pointer.inside && !pointer.dragging) {
      // The hit test is remade only when the pointer or the stone has moved.
      const still = stone.resting && tilt.resting && lifts.resting && idle.block < 0 && impact.age > IMPACT.life;
      if (pointer.x !== picked.x || pointer.y !== picked.y || !still || !picked.still) {
        picked.x = pointer.x; picked.y = pointer.y;
        picked.station = hooks.pickStation(pointer.x, pointer.y);
      }
      picked.still = still;
      const { station } = picked;
      if (station >= 0) hooks.setFocus(station, 'scene'); else if (state.focusSource === 'scene') hooks.setFocus(-1, '');
    }
    const { focus } = state;
    if (focus < 0 || state.focusSource !== 'scene' || !works[focus]) return;
    // The pointed-at step is named on the step itself, unless the caption already names it.
    if (focus === voyage.current()) { ui.setTag(-1); return; }
    stage.project(tribar.stations[focus].tread, px);
    const { width, height, ppu } = stage.layout;
    const ox = px.x - (width / 2 + stage.base.x * ppu), oy = px.y - (height / 2 - stage.base.y * ppu);
    const len = Math.hypot(ox, oy) || 1;
    const reach = DIM.beam * ppu * UI.tagClearance + UI.tagOffset;   // clear of the block, outward
    ui.tagSize(focus, tagSize);
    // Outward from the centre, unless that runs onto stone (the step's own length, or the
    // next side's): then inward, or to either side, the first that is clear of all of it.
    const ux = ox / len, uy = oy / len;
    tagAt.x = px.x + ux * reach; tagAt.y = px.y + uy * reach;
    if (tagCovers(tagAt.x, tagAt.y)) {
      const order = stage.layout.portrait ? RETREAT_TALL : RETREAT_WIDE;
      search: for (const far of UI.tagRetreat) {
        for (const [a, b] of order) {
          // a along the outward direction, b across it
          const dx = a * ux - b * uy, dy = a * uy + b * ux;
          const x = px.x + dx * reach * far, y = px.y + dy * reach * far;
          if (!tagCovers(x, y)) { tagAt.x = x; tagAt.y = y; break search; }
        }
      }
    }
    ui.setTag(focus, tagAt.x, tagAt.y);
  }

  /** The continuous voices: how fast the stone and its steps and the light move, and the swell (src/sound.js). */
  function listen(dt) {
    if (!sound.live) { sidesWere = -1; liftWas.set(lifts.now); return; }
    const moving = !state.calm && dt > 0;
    // The arrival: the three sides drifting home, measured by how far apart they still hang.
    let sides = 0;
    if (arrival.sample) for (const off of arrival.sample.sideOff) sides += Math.hypot(off[0], off[1], off[2]);
    const gathering = moving && sidesWere >= 0 ? Math.abs(sidesWere - sides) / dt / (3 * INTRO.sideDrift) : 0;
    sidesWere = arrival.sample ? sides : -1;
    let shifting = 0;
    for (let i = 0; i < liftWas.length; i++) { shifting += Math.abs(lifts.now[i] - liftWas[i]); liftWas[i] = lifts.now[i]; }
    heard.rumble = moving ? Math.max(Math.abs(stone.velocity) / SOUND.rollFull, shifting / dt / SOUND.grindFull, gathering) : 0;
    heard.light = moving && departure.t < 0 ? Math.abs(light.velocity) / MOTION.trailFullSpeed : 0;
    heard.swell = idle.swellAmp; heard.swellHead = idle.swellHead;
    if (idle.swellAmp > 0) heard.swellPan = panAt(tribar.blocks[Math.floor(idle.swellHead) % tribar.blocks.length].center);
    sound.step(heard);
  }

  function tick(stamp) {
    raf = requestAnimationFrame(tick);
    // ?slow=k scales the clock here, before anything integrates.
    const dt = Math.min(MOTION.maxFrame, lastStamp ? (stamp - lastStamp) / 1000 : 1 / 60) / flags.slow;
    lastStamp = stamp;
    advance(dt);
  }
  /** One step of everything, then a render when the picture can have changed. @returns whether it rendered */
  function advance(dt) {
    const { calm } = state;
    if (!calm) state.clock += dt;       // reduced motion freezes every time-driven effect, grain included
    ticks++;

    now.calm = calm; now.clock = state.clock; now.dragging = pointer.dragging;
    now.hold = now.quiet = state.phase === 'intro';
    now.seated = state.phase === 'idle';
    voyage.step(dt, now);
    advanceArrival(dt);
    // The paradox locks shut again: a jolt sized by how wide the seam was torn, and only for a
    // gesture that ends in the scene. None for a hand that merely came to rest, none for a reach
    // that ends on the rail, the caption, the name or the links (the eye is there, not on the
    // stone), and none while the light is leaving through the door.
    const tear = tilt.step(dt, calm);
    if (tear > 0 && pointer.inside && state.phase !== 'intro' && departure.t < 0) {
      const size = smoothstep(IMPACT.tearFrom, IMPACT.tearFull, tear);
      if (size > 0) strike(IMPACT.tiltLock * size);
      if (tear >= IMPACT.tearDust) burstAt(seamPoint, size);
    }
    now.currentBlock = blockOf(voyage.current()); now.focusBlock = blockOf(state.focus); now.selectedBlock = blockOf(state.selected);
    now.heldBlock = lean.value > LEAN_HOME && door.block !== now.selectedBlock ? door.block : -1;
    now.settling = arrival.sample ? arrival.sample.lift : null;
    idle.step(dt, now);
    now.beatBlock = idle.block; now.beatLift = idle.lift;
    lifts.step(dt, now);
    // Contacts: a step that dropped back onto the loop raises dust, more after a long fall.
    if (!calm) {
      for (const b of lifts.landed) burstFromTread(b, Math.min(1, Math.sqrt(lifts.fallen[b] / MOTION.selectLift)));
      if (idle.landed >= 0) burstFromTread(idle.landed, 1);
    }
    dim.target = state.selected >= 0 ? 1 : 0;
    if (calm) dim.snap(dim.target); else dim.step(dt);
    advanceDoor(dt);
    impact.age += dt;

    present();
    noteArrival();
    point();
    listen(dt);

    // Settled: every spring landed exactly, nothing in flight, nothing pending from the
    // visitor, no idle beat under way. The picture can then only change by an intent
    // (which marks it dirty) or, with motion allowed, by the slow idle life.
    const want = wantDoor();
    const doorStill = door.open === want.open && door.block === want.block && departure.t < 0 && !pinned && lean.resting;
    state.settled = state.phase !== 'intro' && !voyage.scrubbing && !pointer.dragging && doorStill
      && light.resting && stone.resting && tilt.resting && dim.resting && lifts.resting && idle.resting
      && impact.age > IMPACT.life && !(!calm && dust.bursting(state.clock));   // a calm clock never expires a burst
    const due = state.dirty || !state.settled || (!calm && ticks % MOTION.idleRenderEvery === 0);
    if (!due) return false;
    stage.render(); state.renders++; state.dirty = false;
    if (!drawn) { drawn = true; ui.drawn(); }   // the first real frame exists: fade the canvas up
    return true;
  }
  function setRunning(run) {
    cancelAnimationFrame(raf);
    lastStamp = 0;
    if (run) raf = requestAnimationFrame(tick);
  }
  const onVisibility = () => { mark(); setRunning(!document.hidden && !contextDown); };
  const onMotionPreference = () => { state.calm = reducedMotion.matches; mark(); };

  return {
    mark, strike,
    /** The light leaves for the door from where it is drawn this frame. */
    depart() { departure.t = 0; tilt.release(); mark(); },
    /** The link has been followed: no more frames until the page is shown again. */
    pause() { setRunning(false); sound.hush(); },
    /** The page is here again after a departure: the loop runs on. */
    resume() { mark(); setRunning(!document.hidden && !contextDown); },
    /** Attach to the page and start the loop. */
    start() {
      resizeObserver.observe(canvas);
      resize();
      document.addEventListener('visibilitychange', onVisibility);
      reducedMotion.addEventListener('change', onMotionPreference);
      setRunning(!document.hidden);
    },
    // The GL context: pause while it is gone, give up if it never comes back.
    contextLost() {
      contextDown = true;
      setRunning(false);
      clearTimeout(restoreTimer);
      restoreTimer = setTimeout(() => { if (contextDown) hooks.abandon(); }, RECOVERY.restoreTimeout * 1000);
    },
    contextRestored() {
      contextDown = false;
      clearTimeout(restoreTimer);
      mark();
      setRunning(!document.hidden);
    },
    /** Test hooks: drop and recover the GL context through WEBGL_lose_context. */
    loseContext: () => stage.loseContext(),
    restoreContext: () => stage.restoreContext(),
    /** CSS pixel centre of a station's tread, lift included (test hook: `locate`). */
    stepPoint(station, out) {
      const b = tribar.blocks[tribar.stations[station].block];
      point3[0] = b.center[0]; point3[1] = b.center[1]; point3[2] = b.center[2];
      point3[b.tread] += b.half[b.tread] + lifts.now[tribar.stations[station].block];
      return stage.project(point3, out);
    },
    /** Screen centre of every face the true view can see, by block and axis (tests). */
    facePoints() {
      const out = [];
      tribar.blocks.forEach((b, i) => {
        for (let axis = 0; axis < 3; axis++) {
          const c = b.center.slice();
          c[b.tread] += lifts.now[i];
          c[axis] += b.half[axis];
          out.push({ block: i, side: b.side, step: b.step, axis, ...stage.project(c, { x: 0, y: 0 }) });
        }
      });
      return out;
    },
    /** Milliseconds per frame for `frames` consecutive frames, tick and GPU together: the
     *  real cost, whatever the display's cadence. A one-pixel readback is the sync; finish()
     *  returns before the queue has drained on some drivers. */
    bench(frames = 90) {
      const gl = stage.renderer.getContext(), pixel = new Uint8Array(4);
      const drain = () => gl.readPixels(0, 0, 1, 1, gl.RGBA, gl.UNSIGNED_BYTE, pixel);
      drain();
      const t0 = performance.now();
      for (let i = 0; i < frames; i++) { if (!advance(1 / 60)) { stage.render(); state.renders++; } }
      drain();
      return (performance.now() - t0) / frames;
    },
    /** QA: hold the light at a door-frame point (x out of the riser, y up, z along the wall; beams),
     *  or let it go (null). Only while a door is open; the light is drawn and lights there. */
    doorPin(at) { pinned = at ? at.slice(0, 3) : null; mark(); return !!(door.block >= 0 && door.open > 0); },
    /** Test hook: the door's light transport against an independent line-of-sight test, in the
     *  model and on the GPU as drawn. `probe` is src/probe.js, which main.js loads only when a
     *  test asks: visitors never fetch it. */
    doorProbe(options, { probeDoor }) {
      if (!(door.block >= 0 && door.open === 1) || departure.t >= 0) return { error: 'no open door: present a work and let the slot open' };
      const gl = stage.renderer.getContext(), { width, height, dpr } = stage.layout;
      const hidden = [...lantern.sprites, dust.points].map((o) => [o, o.visible]);
      const u = monument.uniforms, outside = u.uLantern.value, ho = SHADING.doorHeight / 2;
      const result = probeDoor({
        depth: doorAt.depth, ho, ...options,
        block: door.block, station: tribar.blocks[door.block].station,
        // Docked, the light the door sees is its station's own dock, in depth too (beams; NaN while not docked).
        dockError: docked() ? (([x, y, z]) => Math.hypot(x - doorLight[0], y - doorLight[1], z - doorLight[2]))(toDoor(doorAt, tribar.stations[tribar.blocks[door.block].station].anchor, [0, 0, 0])) : NaN,
        // The light as the door sees it, projected, against the light as drawn (CSS px).
        light: doorLight.slice(), drawnPx: stage.worldToPx(drawnWorld, { x: 0, y: 0 }),
        lightPx: stage.worldToPx(structToWorld(fromDoor(doorAt, doorLight, [0, 0, 0]), new THREE.Vector3()), { x: 0, y: 0 }),
        view: [u.uDoorView.value.x, u.uDoorView.value.y, u.uDoorView.value.z],
        /**
         * Draws the monument alone, lit only by the door's light at L (none from outside, no sprite), and reads
         * back the opening. With `classify(y, z)` (a point of the opening, door frame: 0 no line of
         * sight from what is seen there, 1 lit, -1 neither) each pixel is checked against it, its
         * neighbours too for the blind ones (the samples of an antialiased pixel spread a pixel).
         */
        render(L, { bounce = true, classify = null } = {}) {
          hidden.forEach(([o]) => { o.visible = false; });
          u.uLantern.value = 0;
          doorUniforms(1, L, 1, 1);
          if (!bounce) u.uDoorBounce.value = 0;
          stage.render();
          const [o, du, dv] = outline(ho);
          const toPx = (w) => stage.worldToPx(w, { x: 0, y: 0 });
          const p0 = toPx(o), pu = toPx(o.clone().add(du)), pv = toPx(o.clone().add(dv));
          const ox = p0.x * dpr, oy = p0.y * dpr, ux = (pu.x - p0.x) * dpr, uy = (pu.y - p0.y) * dpr, vx = (pv.x - p0.x) * dpr, vy = (pv.y - p0.y) * dpr;
          const xs = [ox, ox + ux, ox + vx, ox + ux + vx], ys = [oy, oy + uy, oy + vy, oy + uy + vy];
          const x0 = Math.max(0, Math.floor(Math.min(...xs))), x1 = Math.min(Math.round(width * dpr), Math.ceil(Math.max(...xs)));
          const y0 = Math.max(0, Math.floor(Math.min(...ys))), y1 = Math.min(Math.round(height * dpr), Math.ceil(Math.max(...ys)));
          const w = Math.max(1, x1 - x0), h = Math.max(1, y1 - y0), pixels = new Uint8Array(w * h * 4);
          gl.readPixels(x0, Math.round(height * dpr) - y1, w, h, gl.RGBA, gl.UNSIGNED_BYTE, pixels);
          // Pixels whose centres lie inside the opening by at least 2 device px (clear of its antialiased edge).
          const det = ux * vy - uy * vx, lu = Math.hypot(ux, uy), lv = Math.hypot(vx, vy);
          const mu = 2 * lv / Math.abs(det), mv = 2 * lu / Math.abs(det);
          const hw = SHADING.doorWidth / 2;
          const at = (row, col) => {   // the pixel's centre in the opening: (a along +y, b along +z), 0..1
            const rx = x0 + col + 0.5 - ox, ry = y1 - row - 0.5 - oy;
            return [(rx * vy - ry * vx) / det, (ux * ry - uy * rx) / det];
          };
          let classes = null;
          if (classify) {
            classes = new Int8Array(w * h).fill(-1);
            for (let row = 0; row < h; row++) {
              for (let col = 0; col < w; col++) {
                const [a, b] = at(row, col);
                if (a > 0 && a < 1 && b > 0 && b < 1) classes[row * w + col] = classify(-ho + 2 * ho * a, -hw + 2 * hw * b);
              }
            }
          }
          let inside = 0, chroma = 0, maxRG = 0, sumR = 0, blindPixels = 0, blindChroma = 0, litPixels = 0, litNeutral = 0;
          for (let row = 0; row < h; row++) {
            for (let col = 0; col < w; col++) {
              const [a, b] = at(row, col);
              if (a < mu || a > 1 - mu || b < mv || b > 1 - mv) continue;
              const i = (row * w + col) * 4, r = pixels[i], g = pixels[i + 1], bl = pixels[i + 2];
              const coloured = r !== g || g !== bl;
              inside++; sumR += r;
              if (coloured) chroma++;
              maxRG = Math.max(maxRG, r - g);
              if (!classes) continue;
              const k = row * w + col;
              if (classes[k] === 1) { litPixels++; if (!(r > g)) litNeutral++; }
              if (row > 0 && col > 0 && row < h - 1 && col < w - 1 && classes[k] === 0 && classes[k - 1] === 0 && classes[k + 1] === 0 && classes[k - w] === 0 && classes[k + w] === 0) {
                blindPixels++; if (coloured) blindChroma++;
              }
            }
          }
          return { pixels: inside, chroma, maxRG, meanR: inside ? sumR / inside : 0, bounce: lit.mean, blindPixels, blindChroma, litPixels, litNeutral };
        },
      });
      hidden.forEach(([o, v]) => { o.visible = v; });
      u.uLantern.value = outside;
      mark();
      return result;
    },
    /**
     * Test hook: how the door and the step in front of it look, as drawn without the light's sprite
     * (its glare is the lens's, not the stone's). Optionally with the light held at a door-frame point
     * (`pin`, as doorPin), after `frames` frames of 1/60 s. Returns the rose pixels over both blocks
     * (src/probe.js roseIn) and the colour (5 x 5 mean, 8-bit) at each of `points` (door frame) and
     * at named points: the riser round the opening, the door's tread, the tread in front along the
     * spill's falloff.
     */
    doorLook({ pin, frames = 1, points = [] } = {}, { roseIn }) {
      if (!(door.block >= 0 && door.open === 1)) return { error: 'no open door: present a work and let the slot open' };
      if (pin !== undefined) pinned = pin ? pin.slice(0, 3) : null;
      for (let i = 0; i < frames; i++) advance(1 / 60);
      const gl = stage.renderer.getContext(), { width, height, dpr } = stage.layout;
      const hidden = [...lantern.sprites, dust.points].map((o) => [o, o.visible]);
      hidden.forEach(([o]) => { o.visible = false; });
      stage.render();
      // Both blocks, lifted, on screen: the readback box. The block in front of the near end's last
      // step is the far start's first, where the carry stands it beside the door (as the spill sees it).
      const front = (door.block + 1) % tribar.blocks.length, toPx = (p) => stage.project(p, { x: 0, y: 0 });
      const carry = front === 0 ? seam.carry : [0, 0, 0];
      let x0 = Infinity, y0 = Infinity, x1 = -Infinity, y1 = -Infinity;
      for (const i of [door.block, front]) {
        const b = tribar.blocks[i], sh = i === front ? carry : [0, 0, 0];
        for (let k = 0; k < 8; k++) {
          for (let a = 0; a < 3; a++) point3[a] = b.center[a] + sh[a] + ((k >> a) & 1 ? 1 : -1) * b.half[a] + (a === b.tread ? lifts.now[i] : 0);
          const p = toPx(point3);
          x0 = Math.min(x0, p.x); x1 = Math.max(x1, p.x); y0 = Math.min(y0, p.y); y1 = Math.max(y1, p.y);
        }
      }
      const W = Math.round(width * dpr), H = Math.round(height * dpr);
      const bx0 = Math.max(0, Math.floor(x0 * dpr)), bx1 = Math.min(W, Math.ceil(x1 * dpr)), by0 = Math.max(0, Math.floor(y0 * dpr)), by1 = Math.min(H, Math.ceil(y1 * dpr));
      const w = Math.max(1, bx1 - bx0), h = Math.max(1, by1 - by0), pixels = new Uint8Array(w * h * 4);
      gl.readPixels(bx0, H - by1, w, h, gl.RGBA, gl.UNSIGNED_BYTE, pixels);
      const colourAt = (q) => {
        const p = toPx(fromDoor(doorAt, q, point3)), cx = Math.round(p.x * dpr) - bx0, cy = by1 - 1 - Math.round(p.y * dpr);
        if (cx < 2 || cy < 2 || cx >= w - 2 || cy >= h - 2) return null;
        const c = [0, 0, 0];
        for (let dy = -2; dy <= 2; dy++) for (let dx = -2; dx <= 2; dx++) for (let a = 0; a < 3; a++) c[a] += pixels[((cy + dy) * w + cx + dx) * 4 + a];
        return c.map((v) => Math.round(v / 25));
      };
      // Named points: the riser round the opening (between it and the arrises), the middle of the door's
      // tread, and down the middle of the tread in front, from the riser's foot outward.
      const H2 = SHADING.doorHeight / 2, W2 = SHADING.doorWidth / 2, fb = tribar.blocks[front];
      const frontTop = toDoor(doorAt, fb.center.map((c, a) => c + carry[a]), [0, 0, 0])[1] + fb.half[doorAt.y] + (fb.tread === doorAt.y ? lifts.now[front] : 0);
      // (Below the opening, half way down to the tread in front: at the near end the far start's first
      // block, carried beside it, stands closer under the sill than a step does.)
      const riser = [[0, H2 + 0.04, 0], [0, (Math.max(frontTop, -0.5) - H2) / 2, 0], [0, 0, W2 + 0.08], [0, 0, -W2 - 0.08]].map(colourAt);
      const tread = colourAt([-doorAt.run / 2, SHADING.doorDrop, 0]);
      const spill = Array.from({ length: 12 }, (_, k) => colourAt([0.04 + k * 0.06, frontTop, 0]));
      const rose = roseIn(pixels, w, h);
      rose.worst.forEach((p) => { p[4] = (bx0 + p[4]) / dpr; p[5] = (by1 - 1 - p[5]) / dpr; });   // CSS px
      const result = { ...rose, riser, tread, spill, points: points.map(colourAt), inside: lit.inside, light: doorLight.slice(), frontTop };
      hidden.forEach(([o, v]) => { o.visible = v; });
      mark();
      return result;
    },
    /**
     * Test hook: the light's pool against the stone as the key alone lights it (src/probe.js poolRays).
     * Reads back a box round the light as drawn three times from one frame: as drawn, the stone alone
     * as lit (no sprites: their glare is the lens's, not the stone's), and the stone with the light off
     * (no power, no hold, nothing through the door); and hands them, with each pixel's face (from the
     * line of sight), to the probe. Optionally after `frames` frames of 1/60 s.
     */
    poolLook({ frames = 0, reach = 280, rays = 120 } = {}, { poolRays }) {
      for (let i = 0; i < frames; i++) advance(1 / 60);
      const gl = stage.renderer.getContext(), { width, height, dpr, ppu } = stage.layout, u = monument.uniforms;
      const at = stage.worldToPx(drawnWorld, { x: 0, y: 0 });
      const W = Math.round(width * dpr), H = Math.round(height * dpr), R = Math.round(reach * dpr) + 6;
      const bx0 = Math.max(0, Math.round(at.x * dpr) - R), bx1 = Math.min(W, Math.round(at.x * dpr) + R);
      const by0 = Math.max(0, Math.round(at.y * dpr) - R), by1 = Math.min(H, Math.round(at.y * dpr) + R);
      const w = bx1 - bx0, h = by1 - by0;
      const read = () => { stage.render(); const p = new Uint8Array(w * h * 4); gl.readPixels(bx0, H - by1, w, h, gl.RGBA, gl.UNSIGNED_BYTE, p); return p; };
      const seen = read();
      const hidden = [...lantern.sprites, dust.points].map((o) => [o, o.visible]);
      hidden.forEach(([o]) => { o.visible = false; });
      const on = read();
      const kept = [u.uLantern.value, u.uDoorLight.value.w, u.uDoorHold.value];
      u.uLantern.value = 0; u.uDoorLight.value.w = 0; u.uDoorHold.value = 0;
      monument.setLights(seenLight, new Float32Array(faceOwn.length));
      const off = read();
      [u.uLantern.value, u.uDoorLight.value.w, u.uDoorHold.value] = kept;
      monument.setLights(seenLight, faceOwn);
      hidden.forEach(([o, v]) => { o.visible = v; });
      // Each pixel's face: the block the line of sight meets (as drawn, the seam's rule) and the axis it
      // enters by; the door's opening is a face of its own.
      const o = new THREE.Vector3(), d = new THREE.Vector3(), ho = easeOutCubic(door.open) * SHADING.doorHeight / 2;
      const faceAt = (x, y) => {
        const px = (bx0 + x + 0.5) / dpr, py = (by0 + y + 0.5) / dpr;
        const i = stage.pick(px, py, lifts.now, seam, true);
        if (i < 0) return -1;
        stage.sight(px, py, true, o, d);
        const b = tribar.blocks[i];
        let axis = 0, enter = -Infinity;
        for (let a = 0; a < 3; a++) {
          const t = (b.center[a] + b.half[a] + (a === b.tread ? lifts.now[i] : 0) - o.getComponent(a)) / d.getComponent(a);
          if (t > enter) { enter = t; axis = a; }
        }
        if (i === door.block && door.open > 0 && axis === b.travel) {
          for (let a = 0; a < 3; a++) point3[a] = o.getComponent(a) + enter * d.getComponent(a);
          const q = toDoor(doorAt, point3, corner3);
          if (Math.abs(q[1]) <= ho + 0.02 && Math.abs(q[2]) <= SHADING.doorWidth / 2 + 0.02) return tribar.blocks.length * 3;
        }
        return i * 3 + axis;
      };
      // Runs are trimmed clear of the worn arrises (three of their widths).
      const result = poolRays({ seen, on, off }, w, h, { cx: at.x * dpr - bx0, cy: at.y * dpr - by0, reach: R - 6, rays, faceAt,
        trim: Math.ceil(3 * SHADING.wearWidth * ppu * dpr) + 2, bloom: lantern.bloomRadius * ppu * dpr });
      mark();
      return { ...result, light: [+at.x.toFixed(1), +at.y.toFixed(1)] };
    },
    snapshot: () => ({
      current: works[voyage.current()]?.id ?? null,
      selected: state.selected >= 0 ? works[state.selected]?.id ?? null : null,
      focus: state.focus >= 0 ? works[state.focus]?.id ?? null : null,
      phase: state.phase,
      position: voyage.position,
      stone: stone.value,
      stations: tribar.stepCount,
      tilt: tilt.amount,
      settled: state.settled,
      renders: state.renders,
      context: contextDown ? 'lost' : 'ok',
      idle: { lifting: idle.block >= 0 ? idle.block : null, lift: idle.lift, swell: idle.swellAmp },
      // The door: how open, and what the light puts into it this frame (per unit of its power): the
      // cavity's mean direct irradiance and the share of its inner faces the light reaches; inside: the
      // light has gone into the opening (0..1).
      door: {
        open: door.open, block: door.block, lit: lit.mean, patch: lit.share, inside: lit.inside,
        px: door.block >= 0 ? (({ x, y }) => [x, y])(stage.project(doorAt.origin, { x: 0, y: 0 })) : null,   // the opening's centre (CSS px)
        light: door.block >= 0 ? doorLight.map((v) => +v.toFixed(4)) : null,                               // the light, door frame
        lean: lean.value,                                                                                  // leaning in at it (0..1)
        departing: departure.t >= 0 ? departure.t : null, left: departure.left, leaves: departure.leaves,
      },
      lifts: Array.from(lifts.now),
      // The light in stage space, and where it is drawn (CSS px), the tilt and the seam's
      // cross-fade included (the point the stone is lit from).
      light: { x: lightStage.x, y: lightStage.y, power: lantern.uniforms.uPower.value, px: (({ x, y }) => [x, y])(stage.worldToPx(drawnWorld, {})) },
      arrival: arrival.time,
      // The last strike: seconds since, and its size (1 is the arrival's).
      impact: { age: impact.age, scale: impact.scale },
    }),
    dispose() {
      setRunning(false); resizeObserver.disconnect(); clearTimeout(restoreTimer);
      document.removeEventListener('visibilitychange', onVisibility);
      reducedMotion.removeEventListener('change', onMotionPreference);
      monument.dispose(); lantern.dispose(); dust.dispose(); backdrop.dispose(); stage.dispose();
    },
  };
}
