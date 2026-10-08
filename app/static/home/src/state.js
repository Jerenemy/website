// The facts the modules share, in one record. Intents (src/intents.js) write it; the frame
// (src/frame.js) reads it and advances the bodies that chase it. The whole state is:
//
//   voyage.position  where the visitor is on the loop, in stations (owned by src/voyage.js)
//   selected         the station whose work is being presented, or -1
//   focus            the station being pointed at (pointer, or keyboard focus on its anchor), or -1
//
// Everything that moves chases one of those, so input at any moment simply moves a target;
// nothing queues and nothing locks the visitor out. The rest is bookkeeping for the two
// sequences that are allowed to exist, the arrival and the door, and for the frame itself.
export function createState({ calm, skipArrival, arrivalDuration }) {
  return {
    phase: 'intro',                    // 'intro' | 'idle' | 'travel'
    selected: -1,
    focus: -1, focusSource: '',        // 'scene' (pointer on a step) | 'rail' (its anchor) | ''
    peek: false,                       // OPEN is pointed at or focused: the light leans in at the door
    calm,                              // prefers-reduced-motion, kept live
    arrival: { time: skipArrival ? arrivalDuration : 0, rate: 1, ignited: false, live: false, done: false, sample: null },
    door: { open: 0, block: -1 },      // the slot: how open (0..1), and the step it is in (it shuts there before it moves)
    // Through the door: seconds since, where to, gone (the link has been followed, once), where
    // it last went and how many links have been followed (QA).
    departure: { t: -1, href: null, gone: false, left: null, leaves: 0, byKeyboard: false },
    impact: { age: 1e3, scale: 0 },    // the last strike: seconds since, and its size
    pointer: { x: -1, y: -1, inside: false, dragging: false },
    clock: 0,                          // s of motion time (frozen under reduced motion)
    dirty: true, settled: false, renders: 0,
  };
}
