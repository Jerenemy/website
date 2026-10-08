// Where the visitor is on the loop, and the two bodies that follow them: the light, then
// the stone. Position is measured in stations and is any real number (the loop has no first
// or last station; station i and i + stations are the same place).
//
// The light is weightless: a critically damped spring. The stone is heavy: a planned journey
// (src/mover.js) whose length grows with the angle the monument must turn through, so one
// station is a short roll and a half lap a long one, at every scale; the plan is remade from
// the stone's current motion whenever the visitor moves on, so it never jolts.
//
// The pose is the same every lap (the roll turns 2 pi, the path wraps), so when the visitor
// has run a whole lap or more ahead (a held key, a burst of notches) the stone is shifted by
// whole laps before its journey is planned: it is never left cruising round and round. The
// shift never passes the target, so the rest of the roll keeps the input's direction and is
// under one lap: the monument never turns back against the hand.
import { MOTION } from './config.js';
import { Spring } from './spring.js';
import { Mover } from './mover.js';

/** @param start station the loop opens at (a deep link, or the work a visitor returns from) */
export function createVoyage(tribar, onMove, start = 0) {
  const stations = tribar.stepCount;
  let position = start;
  const light = new Spring(start, MOTION.lightOmega, 1);
  const stone = new Mover(start);
  const gesture = { active: false, from: 0, quietFor: 0 };

  const wrap = (i) => ((i % stations) + stations) % stations;
  /** Seconds the stone should take from where it is to loop position `target`. */
  const journey = (target) => {
    const halfLaps = Math.abs(tribar.thetaAt(target) - tribar.thetaAt(stone.value)) / Math.PI;
    return Math.min(MOTION.rollLongest, MOTION.rollLaunch + MOTION.rollHalfLap * Math.min(halfLaps, 1) + MOTION.rollBeyond * Math.max(0, halfLaps - 1));
  };
  const set = (target) => {
    if (target === position) return;
    position = target;
    onMove();
  };
  /**
   * Bring a body to within one lap of the target, plus the room it needs to stop, by whole
   * laps; invisible, the pose repeats. Never past the target (a shift past it would roll the
   * body back against the input), and never so close that a body arriving fast must brake
   * hard (the next re-plan would carry that braking into a turn back).
   * @param brake seconds of travel at its current speed the body needs to come to rest
   */
  const nearest = (body, brake) => {
    const d = position - body.value, k = Math.sign(d);
    const stop = Math.max(0, k * body.velocity) * brake;
    const laps = k * Math.max(0, Math.floor((k * d - stop) / stations));
    if (!laps) return;
    body.value += laps * stations; body.target += laps * stations;
    if (body.p0 !== undefined) body.p0 += laps * stations;
  };

  const voyage = {
    light, stone,
    get position() { return position; },
    get scrubbing() { return gesture.active; },
    current: () => wrap(Math.round(position)),
    wrap,

    /**
     * Continuous input (trackpad, drag): carries the light along, to be settled later. One
     * gesture reaches at most `max` stations from where it began, softly (tanh), so a fling
     * cannot run away and a short deliberate stroke still commits to the next station.
     */
    scrub(delta, max) {
      if (!gesture.active) { gesture.from = Math.round(position); gesture.raw = 0; }
      gesture.active = true; gesture.quietFor = 0;
      gesture.raw += delta;
      set(gesture.from + max * Math.tanh(gesture.raw / max));
    },
    /** End of a gesture. Snaps in the direction of travel, so a small deliberate gesture
     *  always advances one station instead of springing back. */
    settle() {
      if (!gesture.active) return;
      gesture.active = false;
      const travelled = position - gesture.from;
      const whole = Math.trunc(travelled), part = Math.abs(travelled - whole);
      set(gesture.from + whole + (part >= MOTION.snapBias ? Math.sign(travelled) : 0));
    },
    /** Go to a station by the shorter way round. */
    goTo(station) {
      gesture.active = false;
      set(station + stations * Math.round((position - station) / stations));
    },
    stepBy(dir) {
      gesture.active = false;
      set(Math.round(position) + dir);
    },

    /**
     * @param hold     true while the monument must not chase the light (the arrival)
     */
    step(dt, { calm, hold, dragging }) {
      if (gesture.active && (gesture.quietFor += dt) > MOTION.wheelSnapDelay && !dragging) voyage.settle();

      light.target = position;
      if (calm) { light.snap(position); stone.snap(position); return; }
      if (hold) stone.snap(position);
      else if (stone.target !== position) {
        nearest(stone, MOTION.rollLaunch); nearest(light, 1 / MOTION.lightOmega);
        light.target = position;
        stone.go(position, journey(position));
      }
      light.step(dt); stone.step(dt);
    },
  };
  return voyage;
}
