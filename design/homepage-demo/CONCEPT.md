# TRIBAR

**Idea.** A Penrose tribar of real blocks that never meet in 3D: each work a step, one light (the visitor) walking an endless loop.

## Decisions

Decision | Why
---|---
Air, mist and piers from screen x, y, time | Scale, paradox-safe
Open chain, gap `span·(1,1,1)`, seen along (1,1,1); no depth cues | Closes on screen only; honest torn open
Far start shifted forward along the view, never cut; tones keyed to the stone | Solid blocks at any angle; faces never tie
One step per work; sides grow with the count | Index and building are one
Vermilion once, as the light, alone on faces it reaches whole; DOM grey | One colour, one meaning: here; light only adds
The current step rolls to a fixed dock | Light, leader and caption share one line
Pointer motion tilts about the light; rest snaps shut, jolting after real tears; picking untilted, then as drawn | Felt at any speed; the light keeps its ring; targets hold
Light fast, stone heavy: minimum-jerk, sized by angle | Weight at every scale
Steps rise, stop dead, sink, raise dust | Every step seats itself
Idle: a step lifts; a crest laps the loop | Intent and scroll direction, wordlessly
Door: a real recess lit only where rays reach; pointed at, light leans in | The second action, physical, previewed
The second action arms once the caption is readable | A double-click is one click
One history entry per departure; Back returns to the work left; no timers | Leaving is reversible
Only Escape, the void, the name or the door end a presentation | What you reach for stays
Wheel read by shape and timing; one station per swipe | No runaway flings or false notches
The stone skips whole laps, never backwards | Held keys never leave it cruising
Caption on the dock's line, cross-faded | Where you are, never blank
Rail: bare ticks, current numbered, pointed-at named; 24 px rows, 44 px phone strip | No words at rest, no missed clicks
Server markup adopted; normal-case names; one live region | Real links first
Arrival usable at 2 s, inert until seen, untiltable; early taps count | No lost gesture
Reduced motion: no intro, tilt, travel, beats; no WebGL: the list | Degrades to its own index

## Interaction

Scrub: wheel, swipe, rail. Step: arrows, Home, End. Click presents; Enter, Open or a second click enters. Proofs: `tools/check-geometry.mjs`, `tools/regress.sh`.

## Known gaps

- Far jumps take 1.4 s; 24 phone ticks sit 15 px apart.
- Mid-tear, far blocks drawn off their place can mis-pick.
- Some rolls read lit from below (stone-fixed tones).
- Few works: long steps get a lift, not red.
- Images unused.
- Work pages behind the door still wear the old site (base.html); they only rise out of the void.
