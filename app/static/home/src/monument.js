// The stone. One instanced unit cube per block; all look development is in the shader.
//
// Paradox rule for shading: the far start and the near end of the loop must render
// identically where they meet, so NOTHING here may depend on distance along the view. No
// depth fog, no cast shadows, no screen-space AO. The mist is a function of where a fragment
// lands ON SCREEN (world x, y: the tilt included, so the two ends agree at every angle) and
// the key of face orientation only. The light lights each block from where that block sees it
// (src/door.js lightFor): its depth resolved from the block's own side of the seam and carried
// along the view, so where the two ends meet they see one light at one distance, whatever
// their real distance apart along the view. The key light is fixed to the stone, not to the
// screen: the three face families then keep three fixed tones at every roll, which is what
// lets the impossibility read, and turning the monument turns the whole picture, light included.
//
// Where the far start's phantoms hide the near end along the current view (src/seam.js), the
// near end is stood back in depth behind the far start, by the same translation along the
// view that the phantoms make forward: invisible on screen, it changes only who is in front.
// No block is ever cut, so none can look sliced, and the depth test resolves the far block's
// silhouette over the near end sample by sample. Two draws: the stone pass draws every block
// but those near-end fragments; the behind pass draws only them, its vertices moved back along
// the view (in an orthographic camera, a constant in depth and nothing on screen), so depth
// stays interpolated per sample and no fragment has to write its own.
//
// The material is the theme's (src/theme.js `surface`): a function of the block itself (its
// rest position, face, index) giving the albedo, a bump to the normal, a gloss and an emission;
// the void's is neutral stone. Everything else in the lighting (the three tones, the contact
// shadows, the lines, the light's hold of a face) is the scene's, and the material only
// modulates it, so a theme cannot break the paradox by accident.
import * as THREE from 'three';
import { PALETTE, SHADING, MOTION } from './config.js';
import { GRADE } from './glsl.js';
import { DOOR_GLSL, LIGHT_RADIUS } from './door.js';
import { hook, VOID_SURFACE } from './theme.js';

// The slab test divides by each component of the view; one exactly zero (never near, in
// practice) would make it 0/0 on a face, so it is nudged off zero.
const nonZero = (c) => (Math.abs(c) < 1e-6 ? 1e-6 : c);
const HALF_H = (SHADING.doorHeight / 2).toFixed(4), HALF_W = (SHADING.doorWidth / 2).toFixed(4), RADIUS = LIGHT_RADIUS.toFixed(4);
const KEY_SOFT = SHADING.doorKeySoft.toFixed(4), KNEE = SHADING.doorKnee.toFixed(3);
const LIFT = SHADING.lanternWhite.map((c) => c.toFixed(4)).join(', ');   // what the light adds to a face it does not hold

const transformChunk = /* glsl */ `
  uniform mat3 uStageRot;
  uniform vec3 uPivot;
  uniform mat3 uSideRot[3];
  uniform vec3 uSidePivot[3];
  uniform vec3 uSideOff[3];
  vec3 toStage(vec3 p, int side) {
    vec3 g = uSideRot[side] * (p - uSidePivot[side]) + uSidePivot[side] + uSideOff[side];
    return uStageRot * (g - uPivot);
  }
`;

const varyingsChunk = /* glsl */ `
  varying vec3 vStruct;     // paradox space, lift included
  varying vec3 vRest;       // paradox space without lift (texture sticks to the block)
  varying vec2 vScreen;     // world x, y: where the fragment lands on screen, tilt included
  varying vec3 vNormalMon;  // after the arrival's per-side twist, before the roll: lit by the key
  varying vec3 vNormalWorld;
  varying vec3 vBox;        // position inside the block
  varying vec3 vNormalStruct;
  flat varying vec3 vHalf;
  flat varying vec3 vOccAC;
  flat varying vec3 vOccAH;
  flat varying vec3 vOccBC;
  flat varying vec3 vOccBH;
  flat varying vec3 vJointNeg;
  flat varying vec3 vJointPos;
  flat varying vec4 vMeta;
  flat varying vec3 vExtra;  // occluder A is cross-side, occluder B is cross-side, emphasis
  flat varying vec3 vLight;  // the light as this block sees it (structure space: src/door.js lightFor)
  flat varying float vOwn;   // this face: how far the light holds it (0..1)
  flat varying vec3 vToEye;  // toward the eye, structure space (the material's view: src/theme.js)
`;

/** @param pass 'stone' or 'behind' (the near end, moved back along the view: see the header) */
const blockVertexShader = (pass) => /* glsl */ `
  ${transformChunk}
  attribute vec3 aCenter;
  attribute vec3 aHalf;
  attribute vec3 aOccAC;
  attribute vec3 aOccAH;
  attribute vec3 aOccBC;
  attribute vec3 aOccBH;
  attribute vec3 aJointNeg;
  attribute vec3 aJointPos;
  attribute vec4 aMeta;     // side, flags (1 = the near end, behind the far start where a phantom hides it; 2 = step), tread axis, block index
  attribute vec4 aOcc;      // per occluder: tread axis, +10 if it belongs to another side (x, y); +1 / -1 if it is
                            // across the seam (one gap on / back), else 0 (z, w)
  attribute vec4 aDyn;      // own lift, occluder lifts, emphasis
  attribute vec3 aLight;    // the light as this block sees it (src/frame.js lights)
  attribute vec3 aOwn;      // per face (+x, +y, +z): how far the light holds it (src/hold.js)
  uniform vec3 uSeamCarry;  // where the far start stands beside the near end (src/seam.js carry)
  uniform float uSeamDepth; // depth-buffer distance that stands the near end just behind the far start
  ${varyingsChunk}

  vec3 axisVec(float i) { return vec3(1.0) - min(abs(vec3(i) - vec3(0.0, 1.0, 2.0)), 1.0); }

  void main() {
    vec3 box = position * 2.0 * aHalf;
    vec3 rest = aCenter + box;
    vec3 p = rest + axisVec(aMeta.z) * aDyn.x;
    int side = int(aMeta.x + 0.5);
    vec3 st = toStage(p, side);

    vStruct = p; vRest = rest; vBox = box;
    vScreen = (modelMatrix * vec4(st, 1.0)).xy;
    vNormalStruct = normal;
    vNormalMon = uSideRot[side] * normal;
    vNormalWorld = mat3(modelMatrix) * (uStageRot * vNormalMon);
    vHalf = aHalf;
    // A neighbour across the seam stands where the far start stands now, beside the near end:
    // a gap away at rest, wherever the phantoms are once the view leaves the true angle.
    vOccAC = aOccAC + aOcc.z * uSeamCarry + axisVec(mod(aOcc.x, 10.0)) * aDyn.y; vOccAH = aOccAH;
    vOccBC = aOccBC + aOcc.w * uSeamCarry + axisVec(mod(aOcc.y, 10.0)) * aDyn.z; vOccBH = aOccBH;
    vJointNeg = aJointNeg; vJointPos = aJointPos;
    vMeta = aMeta;
    vExtra = vec3(step(9.5, aOcc.x), step(9.5, aOcc.y), aDyn.w);
    vLight = aLight;
    vOwn = dot(aOwn, max(normal, 0.0));   // the visible faces are the + ones; a - face is never held
    // The eye is world +z (an orthographic camera): back through the rig, the roll and the side's twist.
    vToEye = normalize(((vec3(0.0, 0.0, 1.0) * mat3(modelMatrix)) * uStageRot) * uSideRot[side]);
    gl_Position = projectionMatrix * modelViewMatrix * vec4(st, 1.0);
    ${pass === 'behind' ? 'gl_Position.z += 2.0 * uSeamDepth;   // NDC spans two depth units' : ''}
  }
`;

/** @param pass 'stone' (every block, less the near end where a phantom hides it) or 'behind'
 *  (only that: the near-end fragments within a pixel of a phantom's shadow, stood back). */
const fragmentShader = ({ phantoms, count, pass }) => /* glsl */ `
  precision highp float;
  uniform vec3 uPhC[${phantoms}];  // the far start's blocks, lifted, in side 0's own frame
  uniform vec3 uPhH[${phantoms}];
  uniform mat3 uSeamRot;     // a near-end point into side 0's frame (src/seam.js rot, origin)...
  uniform vec3 uSeamOrigin;  // ...already moved back by the phantoms' offset
  uniform vec3 uSeamDir;     // the view, in side 0's frame, toward the eye
  uniform vec3 uKeyDir;
  uniform vec3 uFillDir;
  uniform float uLantern;   // the light's power on the outside stone (breathing in)
  uniform vec3 uAccent;
  uniform vec2 uFocus;      // world x, y of the clearest air (mist is fixed to the world)
  uniform vec3 uMist;       // inner radius, outer radius, floor
  uniform float uTime;
  uniform float uExposure;
  uniform float uDim;
  uniform float uSelected;  // block index, or -1
  uniform float uAssembled; // 0 while the sides hang apart: cross-side contact shadows off
  uniform vec2 uSwell;      // the idle lap swell: head of the crest in loop units (block index + fraction), weight
  uniform vec3 uCorner;     // how shut each corner's joint is (1: its two sides touch): the seam, corner 1, corner 2
  // The door (src/door.js): a slot in one step's riser with a cavity behind it, lit by the light alone.
  uniform vec4 uDoor;       // its block, how open (0..1), the block in front of its riser, the cavity's depth
  uniform vec3 uDoorO;      // the opening's centre, structure space, lift included
  uniform mat3 uDoorAxes;   // structure -> door frame: out of the riser, up the tread normal, along the wall
  uniform vec4 uDoorLight;  // the light in the door frame (its depth resolved from the door's side of the seam), its power
  uniform float uDoorHold;  // its power without the breath (at most 1): where its light lands it displaces the key by this
  uniform vec3 uDoorView;   // toward the eye, door frame
  uniform vec3 uDoorShift;  // the block in front, across the seam: where it stands beside the door's (the carry)
  uniform float uDoorBounce; // one bounce: albedo x the cavity's mean direct irradiance (per unit of power)
  uniform mat3 uSideRot[3];  // (as the vertex shader's) a bumped normal into monument space...
  uniform mat3 uStageRot;    // ...the roll...
  uniform mat3 uRigRot;      // ...and the tilt: into world space
  ${varyingsChunk}

  ${GRADE}
  ${hook('surface', VOID_SURFACE)}
  ${DOOR_GLSL}

  vec3 axisVec(float i) { return vec3(1.0) - min(abs(vec3(i) - vec3(0.0, 1.0, 2.0)), 1.0); }

  // THE SEAM. The first blocks of side 0 must appear IN FRONT of the last blocks of side 2,
  // although they are really a whole gap behind them. A phantom (side 0 restated nearer along
  // the view, src/seam.js) hides part of the near end from the eye: the length of the line of
  // sight from a near-end point that runs through a phantom, > 0 inside one's shadow, and
  // falling through zero, one pixel per fwidth, across its silhouette.
  float shadowOf(vec3 o, vec3 d, int i) {
    vec3 t0 = (uPhC[i] - uPhH[i] - o) / d;
    vec3 t1 = (uPhC[i] + uPhH[i] - o) / d;
    vec3 enter = min(t0, t1), leave = max(t0, t1);
    float near = max(max(enter.x, enter.y), max(enter.z, 0.0));
    float far = min(min(leave.x, leave.y), leave.z);
    return far - near;
  }
  float phantomChord(vec3 p) {
    vec3 o = uSeamRot * p + uSeamOrigin;
    float f = -1.0e3;
    for (int i = 0; i < ${phantoms}; i++) f = max(f, shadowOf(o, uSeamDir, i));
    return f;
  }
  // A soft shoulder that keeps the hue: above the knee the brightest channel rolls off toward 1 and
  // the others follow it in proportion, so an over-lit vermilion stays vermilion instead of
  // clipping toward orange (the light's core is the sprite's to burn white).
  vec3 shoulder(vec3 c) {
    float m = max(c.r, max(c.g, c.b));
    if (m <= ${KNEE}) return c;
    return c * ((${KNEE} + (1.0 - ${KNEE}) * (1.0 - exp(-(m - ${KNEE}) / (1.0 - ${KNEE})))) / m);
  }
  // A joint flag (src/tribar.js): 0 free, 1 always a joint, 2 + c a joint only while corner c is shut.
  float shut(float j) { return j < 1.5 ? j : j < 2.5 ? uCorner.x : j < 3.5 ? uCorner.y : uCorner.z; }
  // Contact shadow from an axis-aligned neighbour: the cosine-weighted sky hidden by a wall
  // of height 'rise' at distance 'd' is (1 - d / sqrt(d^2 + rise^2)) / 2.
  float wallShadow(vec3 p, vec3 n, vec3 oc, vec3 oh) {
    float rise = dot(oc - p, n) + dot(oh, abs(n)) - ${SHADING.aoBias.toFixed(4)};
    if (rise <= 0.0) return 0.0;
    vec3 gap = max(abs(p - oc) - oh, 0.0) * (1.0 - abs(n));
    float d = length(gap) + ${SHADING.aoBias.toFixed(4)};
    return 0.5 * (1.0 - d / sqrt(d * d + rise * rise));
  }

  void main() {
    float flags = vMeta.y;
    bool seam = mod(flags, 2.0) > 0.5;
    bool isStep = flags > 1.5;
    float blockIndex = vMeta.w;
    if (seam) {
      // Within a pixel of a phantom's shadow the near end stands back, behind every far block
      // on this line of sight (each is the phantom moved back by the same offset), so where
      // the far block covers a sample it is in front, and where it does not the near end is
      // still the nearest thing there. Per sample, so the far block keeps its own antialiased
      // arris; nothing is cut, so the void never shows through. (Nothing else stands between
      // the two: tools/check-geometry.mjs proves only phantoms share pixels with the near end.)
      float f = phantomChord(vStruct);
      bool hidden = f > -max(fwidth(f), 1.0e-5);
      ${pass === 'stone' ? 'if (hidden) discard;' : 'if (!hidden) discard;'}
    }

    vec3 nS = normalize(vNormalStruct);
    vec3 axisN = abs(nS);
    vec3 travel = axisVec(vMeta.x);   // the side's own direction, which is the loop's here
    vec3 tread = axisVec(vMeta.z);    // the block's up: the tread's axis
    vec3 toEdge = vHalf - abs(vBox) + axisN * 1.0e3;

    // --- the material (src/theme.js) ---------------------------------------------------------
    SurfaceIn sIn = SurfaceIn(vRest, vBox, vHalf, nS, toEdge, travel, tread, step(0.5, dot(nS, tread)), dot(vHalf - vBox, tread), blockIndex, isStep ? 1.0 : 0.0, uTime, vToEye);
    Surface sf = surfaceAt(sIn);
    // A theme whose blocks are not boxes carves their outline: the fragment's coverage (src/theme.js
    // surfaceCover), written as alpha and turned into sample coverage (alphaToCoverage), so the carved
    // edge is antialiased by the same multisampling as every arris.
    float cover = surfaceCover(sIn);
    if (cover <= 0.0) discard;
    int side = int(vMeta.x + 0.5);
    vec3 bumpM = uSideRot[side] * sf.bump;
    vec3 nM = normalize(normalize(vNormalMon) + bumpM);                           // monument space: the key's
    vec3 N = normalize(normalize(vNormalWorld) + uRigRot * (uStageRot * bumpM));  // world space: the screen's
    vec3 nSb = normalize(nS + sf.bump);                                          // structure space: the light's

    // --- light: three deliberate tones, one per face family ---------------------------
    float key = pow(0.5 + 0.5 * dot(nM, uKeyDir), ${SHADING.keyWrapPower.toFixed(2)});
    float fill = pow(0.5 + 0.5 * dot(nM, uFillDir), ${SHADING.fillWrapPower.toFixed(2)});
    // A weak light from straight above the SCREEN (world +y), so treads keep a slight lift
    // whichever way the monument has rolled: orientation only, never depth.
    float top = pow(0.5 + 0.5 * N.y, 2.0);
    float light = ${SHADING.ambient.toFixed(3)} + ${SHADING.key.toFixed(3)} * key + ${SHADING.fill.toFixed(3)} * fill + ${SHADING.topLight.toFixed(3)} * top;

    // --- contact shadows -----------------------------------------------------------------
    float sA = wallShadow(vStruct, nS, vOccAC, vOccAH) * mix(1.0, uAssembled, vExtra.x);
    float sB = wallShadow(vStruct, nS, vOccBC, vOccBH) * mix(1.0, uAssembled, vExtra.y);
    float ao = 1.0 - ${SHADING.aoStrength.toFixed(2)} * min(sA + sB, 0.62);

    // --- edges: joints between blocks read dark, free edges catch the light -------------
    vec3 px = toEdge / max(fwidth(toEdge), 1.0e-6);
    vec3 line = 1.0 - smoothstep(${(SHADING.lineWidthPx - 0.5).toFixed(2)}, ${(SHADING.lineWidthPx + 0.5).toFixed(2)}, px);
    vec3 joint = mix(vJointNeg, vJointPos, step(0.0, vBox));
    joint = vec3(shut(joint.x), shut(joint.y), shut(joint.z));
    if (isStep) {
      // The leading edge of a tread is a nosing, not a joint: the next step is lower.
      float onTread = step(0.5, dot(nS, tread));
      joint *= 1.0 - onTread * travel * step(0.0, vBox);
    }
    float jointLine = max(max(line.x * joint.x, line.y * joint.y), line.z * joint.z);
    float bevelLine = max(max(line.x * (1.0 - joint.x), line.y * (1.0 - joint.y)), line.z * (1.0 - joint.z));
    vec3 worn = exp(-toEdge / ${SHADING.wearWidth.toFixed(3)}) * (1.0 - joint);
    float wear = max(max(worn.x, worn.y), worn.z);

    // --- stone -------------------------------------------------------------------------------
    vec3 albedo = sf.albedo;

    float mist = mix(1.0, uMist.z, smoothstep(uMist.x, uMist.y, length(vScreen - uFocus)));
    float selected = 1.0 - min(abs(blockIndex - uSelected), 1.0);
    float dim = 1.0 - ${SHADING.dimSelected.toFixed(2)} * uDim * (1.0 - selected);

    vec3 tone = albedo * light * ao;
    tone *= 1.0 - ${SHADING.jointDarken.toFixed(2)} * jointLine;
    tone += (${SHADING.bevelGain.toFixed(2)} * bevelLine + ${SHADING.wearGain.toFixed(2)} * wear) * (0.2 + key) * albedo;
    tone *= 1.0 + 0.16 * vExtra.z;
    // The lap swell: a crest of light running round the loop, caught mostly by the arrises.
    // Loop units: block index plus the fraction along the block's travel, which is the
    // direction the light goes; the loop wraps, so the crest closes on itself at the seam.
    float along = 0.5 + 0.5 * dot(vBox, travel) / max(dot(vHalf, travel), 1.0e-4);
    float behind = mod(blockIndex + along - uSwell.x + ${(count / 2).toFixed(1)}, ${count.toFixed(1)}) - ${(count / 2).toFixed(1)};
    float crest = uSwell.y * exp(-behind * behind / ${(MOTION.swellWidth * MOTION.swellWidth).toFixed(3)});
    tone *= 1.0 + ${MOTION.swellGain.toFixed(2)} * crest * (${MOTION.swellFace.toFixed(2)} + 2.0 * bevelLine + 1.5 * wear);
    // A glossy material (the theme's) catches the key in a highlight, seen from straight ahead.
    vec3 V = vec3(0.0, 0.0, 1.0);
    if (sf.gloss > 0.0) {
      vec3 Lk = normalize(uRigRot * (uStageRot * uKeyDir));
      tone += vec3(sf.gloss * ${SHADING.key.toFixed(3)} * pow(max(dot(N, normalize(Lk + V)), 0.0), sf.shine) * ao);
    }
    tone *= mist * dim * uExposure;

    // --- the light ------------------------------------------------------------------------------
    // Two lights: the key (above, neutral, fixed to the stone) and the light, a small sphere of
    // vermilion. It lights every face by the law it lights its door's recess by (src/door.js
    // direct): its power, times the cosine, times the falloff of the distance, from the light as
    // this block sees it (vLight), smoothed over its radius where it crosses the face's plane (a
    // face turned away takes none of it, edge to edge).
    vec3 toL = vLight - vStruct;
    float d2 = dot(toL, toL);
    float ahead = dot(nS, toL);
    float fall = lanternFall(d2);
    float facing = max(dot(nSb, toL), 0.0) * inversesqrt(max(d2, 1.0e-8)) * smoothstep(-${RADIUS}, ${RADIUS}, ahead);
    // The stone's own form under it: joints read dark, free arrises and worn edges catch it.
    float form = (1.0 - ${SHADING.jointDarken.toFixed(2)} * jointLine) * (1.0 + ${SHADING.lanternEdge.toFixed(2)} * max(bevelLine, wear));
    vec3 lantern = uLantern * ${SHADING.glowPower.toFixed(2)} * fall * facing * albedo * ao * form * uExposure;
    if (sf.gloss > 0.0) {
      // Its highlight on a glossy material, by the same law (and held by the same face).
      vec3 Ll = normalize(uRigRot * (uStageRot * (uSideRot[side] * toL)));
      lantern += vec3(sf.gloss * uLantern * ${SHADING.glowPower.toFixed(2)} * fall * smoothstep(-${RADIUS}, ${RADIUS}, ahead) * pow(max(dot(N, normalize(Ll + V)), 0.0), sf.shine) * ao * uExposure);
    }
    // Who lights a face is decided per face, never per pixel (vOwn, src/hold.js): a face the light
    // holds is lit by it alone, vermilion falling to deep red, never the pink of red over lit grey;
    // every other face keeps the key's grey and the light only adds to it, a warm white well below
    // any tint that reads as a second colour. So the colour changes only at an edge, and on every
    // face the light rises toward its nearest point and falls away from it: no ring, no rim. A face
    // changing hands (the light passing on) gives up the key's grey before the red arrives, or the
    // red before the grey returns, over a tenth of the hold: at the light's speed a frame of dark,
    // never of rose.
    float keyOn = 1.0 - smoothstep(0.4, 0.5, vOwn);
    float redOn = smoothstep(0.5, 0.6, vOwn);
    vec3 glow = shoulder(uAccent * (redOn * lantern)) + vec3(${LIFT}) * (keyOn * lantern);
    tone *= keyOn;

    // --- the door's spill --------------------------------------------------------------------
    // The tread in front of the door's riser takes light out of the opening: the light's own,
    // through it, while the light is inside, and the lit cavity's glow. While the opening is lit
    // the light hangs over that tread (src/hold.js), so the spill falls on stone the key has left.
    float doorHo = ${HALF_H} * uDoor.y;
    if (abs(blockIndex - uDoor.z) < 0.5 && uDoor.y > 0.0 && dot(uDoorAxes * nS, vec3(0.0, 1.0, 0.0)) > 0.5) {
      vec3 q = uDoorAxes * (vStruct + uDoorShift - uDoorO);
      vec3 sight = doorSight(q, vec3(0.0, 1.0, 0.0), uDoorLight.xyz, doorHo, ${HALF_W});
      float through = doorCover(sight.x, sight.y);
      float inCavity = 1.0 - smoothstep(-${RADIUS}, ${RADIUS}, cavityDistance(uDoorLight.xyz, uDoor.w, ${HALF_H}, ${HALF_W}));
      float spill = step(1.0e-4, q.x) * (through * inCavity * sight.z + uDoorBounce * openingFactor(q, vec3(0.0, 1.0, 0.0), doorHo, ${HALF_W}));
      vec3 spilled = uDoorLight.w * ${SHADING.glowPower.toFixed(2)} * spill * albedo * ao * uExposure;
      glow += uAccent * (redOn * spilled) + vec3(${LIFT}) * (keyOn * spilled);
    }

    vec3 lin = tone + glow + sf.emit * dim * uExposure;
    // --- the door ---------------------------------------------------------------------------
    // The door's riser has a real recess: inside the opening the line of sight is cast into the
    // box behind it (interior mapping), so the jamb, the sill and the back wall shift with the
    // view as solid faces do. What it lands on is lit by the light only where the light can be
    // seen from there through the opening (or when the light is inside), with the face's cosine
    // and the lantern's falloff, plus one bounce of what the cavity caught (src/door.js). The rest
    // is neutral: the hall's air through the opening (darkest at the back), and the stone-fixed key
    // where the opening lets it fall in (a directional light: a crisp patch, with the outside's
    // own wrap, so an inner and an outer face of one orientation share a tone). With no line of
    // sight to the light the recess has no colour at all.
    if (isStep && abs(blockIndex - uDoor.x) < 0.5 && uDoor.y > 0.0 && dot(nS, travel) > 0.5) {
      vec3 q = uDoorAxes * (vStruct - uDoorO);                 // x = 0 here, on the riser
      float depth = uDoor.w;
      vec2 d = abs(q.yz) - vec2(doorHo, ${HALF_W});
      float edge = -max(d.x, d.y);
      float door = clamp(edge / max(fwidth(edge), 1.0e-5) + 0.5, 0.0, 1.0);
      // Into the cavity along the line of sight, to the first inner face.
      vec3 dir = -uDoorView;
      vec3 e = vec3(0.0, clamp(q.y, -${HALF_H}, ${HALF_H}), clamp(q.z, -${HALF_W}, ${HALF_W}));
      vec3 safe = vec3(min(dir.x, -1.0e-4), abs(dir.y) < 1.0e-6 ? 1.0e-6 : dir.y, abs(dir.z) < 1.0e-6 ? 1.0e-6 : dir.z);
      vec3 hits = (vec3(-depth, sign(safe.y) * ${HALF_H}, sign(safe.z) * ${HALF_W}) - e) / safe;
      float t = min(hits.x, min(hits.y, hits.z));
      vec3 p = e + t * safe;
      vec3 n = hits.x <= min(hits.y, hits.z) ? vec3(1.0, 0.0, 0.0) : hits.y <= hits.z ? vec3(0.0, -sign(safe.y), 0.0) : vec3(0.0, 0.0, -sign(safe.z));
      vec3 sight = doorSight(p, n, uDoorLight.xyz, doorHo, ${HALF_W});
      float through = doorCover(sight.x, sight.y);
      float inCavity = 1.0 - smoothstep(-${RADIUS}, ${RADIUS}, cavityDistance(uDoorLight.xyz, depth, ${HALF_H}, ${HALF_W}));
      float form = openingFactor(p, n, doorHo, ${HALF_W});
      float lit = max(through, inCavity) * sight.z + uDoorBounce * (1.0 - form);
      // The inner face's own stone: the hit point, back in the block's rest coordinates.
      vec3 wallAxis = vec3(1.0) - travel - tread;
      vec3 rest = vRest - vBox + travel * (p.x + dot(vHalf, travel)) + tread * (p.y + dot(vHalf, tread) - ${SHADING.doorDrop.toFixed(3)}) + wallAxis * p.z;
      vec3 keyD = uDoorAxes * uKeyDir;
      float keyIn = smoothstep(-${KEY_SOFT}, ${KEY_SOFT}, apertureAngle(p, keyD, doorHo, ${HALF_W})) * pow(0.5 + 0.5 * dot(n, keyD), ${SHADING.keyWrapPower.toFixed(2)}) * ${SHADING.key.toFixed(3)};
      float own = smoothstep(0.0, ${SHADING.doorOwn.toFixed(4)}, lit * uDoorHold);
      float neutral = (${SHADING.doorAmbient.toFixed(4)} * form + keyIn) * (1.0 - own) * mist * dim;
      vec3 nIn = n * uDoorAxes;   // the inner face's normal, structure space
      vec3 inner = surfaceAt(SurfaceIn(rest, vBox, vHalf, nIn, vec3(1.0e3), travel, tread, step(0.5, dot(nIn, tread)), dot(vHalf - vBox, tread), blockIndex, 1.0, uTime, vToEye)).albedo
        * (vec3(neutral) + uAccent * (uDoorLight.w * ${SHADING.glowPower.toFixed(2)} * lit)) * uExposure;
      lin = mix(lin, shoulder(inner), door);
    }
    vec3 color = toSRGB(lin);
    color += grain(gl_FragCoord.xy, uTime, ${SHADING.grainAmount.toFixed(4)});
    gl_FragColor = vec4(color, cover);
  }
`;

export function createMonument(tribar) {
  const { blocks, gap, phantomSources, seamBlocks, sideCentre } = tribar;
  const count = blocks.length;
  const phantoms = phantomSources.length;
  const cube = new THREE.BoxGeometry(1, 1, 1);
  const seamSet = new Set(seamBlocks);

  /** One instanced unit cube per listed block, carrying everything the shader reads about it. */
  function instances(list) {
    const geometry = new THREE.InstancedBufferGeometry();
    geometry.index = cube.index;
    geometry.setAttribute('position', cube.getAttribute('position'));
    geometry.setAttribute('normal', cube.getAttribute('normal'));
    geometry.instanceCount = list.length;
    const attr = (name, size) => {
      const a = new THREE.InstancedBufferAttribute(new Float32Array(list.length * size), size);
      geometry.setAttribute(name, a);
      return a;
    };
    const aCenter = attr('aCenter', 3), aHalf = attr('aHalf', 3);
    const occ = [[attr('aOccAC', 3), attr('aOccAH', 3)], [attr('aOccBC', 3), attr('aOccBH', 3)]];
    const aJointNeg = attr('aJointNeg', 3), aJointPos = attr('aJointPos', 3);
    const aMeta = attr('aMeta', 4), aOcc = attr('aOcc', 4), aDyn = attr('aDyn', 4);
    const aLight = attr('aLight', 3), aOwn = attr('aOwn', 3);
    aDyn.setUsage(THREE.DynamicDrawUsage); aLight.setUsage(THREE.DynamicDrawUsage); aOwn.setUsage(THREE.DynamicDrawUsage);
    list.forEach((i, n) => {
      const blk = blocks[i];
      aCenter.setXYZ(n, ...blk.center);
      aHalf.setXYZ(n, ...blk.half);
      blk.occluders.forEach((o, slot) => {
        const other = blocks[o.index];
        // Across the seam the shift is +/- the gap; the shader adds where the far start stands now.
        occ[slot][0].setXYZ(n, ...other.center);
        occ[slot][1].setXYZ(n, ...other.half);
        aOcc.array[n * 4 + slot] = other.tread + (o.cross ? 10 : 0);
        aOcc.array[n * 4 + 2 + slot] = Math.sign(o.shift[0] * gap[0] + o.shift[1] * gap[1] + o.shift[2] * gap[2]);
      });
      aJointNeg.setXYZ(n, blk.joints[0], blk.joints[1], blk.joints[2]);
      aJointPos.setXYZ(n, blk.joints[3], blk.joints[4], blk.joints[5]);
      aMeta.setXYZW(n, blk.side, (seamSet.has(i) ? 1 : 0) + (blk.step >= 0 ? 2 : 0), blk.tread, i);
    });
    return { geometry, aDyn, aLight, aOwn, list };
  }
  const sets = [instances(blocks.map((_, i) => i)), instances(seamBlocks)];
  // What setDynamics last handed the GPU.
  const uploaded = { lifts: false, lift: new Float32Array(blocks.length), emphasis: new Float32Array(blocks.length), seam: -1, light: new Float32Array(blocks.length * 3), own: new Float32Array(blocks.length * 3) };

  const uniforms = {
    uStageRot: { value: new THREE.Matrix3() },
    uPivot: { value: new THREE.Vector3(...tribar.pivot) },
    uSideRot: { value: [new THREE.Matrix3(), new THREE.Matrix3(), new THREE.Matrix3()] },
    uSidePivot: { value: sideCentre.map((c) => new THREE.Vector3(...c)) },
    uSideOff: { value: [new THREE.Vector3(), new THREE.Vector3(), new THREE.Vector3()] },
    uPhC: { value: phantomSources.map((i) => new THREE.Vector3(...blocks[i].center)) },
    uPhH: { value: phantomSources.map((i) => new THREE.Vector3(...blocks[i].half)) },
    uSeamRot: { value: new THREE.Matrix3() },
    uSeamOrigin: { value: new THREE.Vector3(-gap[0], -gap[1], -gap[2]) },
    uSeamDir: { value: new THREE.Vector3(1, 1, 1).normalize() },
    uSeamCarry: { value: new THREE.Vector3(...gap) },
    uSeamDepth: { value: 0 },
    uKeyDir: { value: new THREE.Vector3(...SHADING.keyDir).normalize() },
    uFillDir: { value: new THREE.Vector3(...SHADING.fillDir).normalize() },
    uRigRot: { value: new THREE.Matrix3() },
    uLantern: { value: 0 },
    uAccent: { value: new THREE.Vector3(...PALETTE.accentLinear) },
    uFocus: { value: new THREE.Vector2() },
    uMist: { value: new THREE.Vector3(1, 2, SHADING.mistFloor) },
    uTime: { value: 0 },
    uExposure: { value: 1 },
    uDim: { value: 0 },
    uSelected: { value: -1 },
    uAssembled: { value: 1 },
    uSwell: { value: new THREE.Vector2(0, 0) },
    uCorner: { value: new THREE.Vector3(1, 1, 1) },
    uDoor: { value: new THREE.Vector4(-1, 0, -1, SHADING.doorDepth) },
    uDoorO: { value: new THREE.Vector3() },
    uDoorAxes: { value: new THREE.Matrix3() },
    uDoorLight: { value: new THREE.Vector4(0, 10, 0, 0) },
    uDoorHold: { value: 0 },
    uDoorView: { value: new THREE.Vector3(1, 1, 1).normalize() },
    uDoorShift: { value: new THREE.Vector3() },
    uDoorBounce: { value: 0 },
  };
  const materials = ['stone', 'behind'].map((pass) => new THREE.ShaderMaterial({
    uniforms, vertexShader: blockVertexShader(pass), fragmentShader: fragmentShader({ phantoms, count, pass }),
    alphaToCoverage: true,   // a theme's carved outline (surfaceCover) is antialiased by the multisampling
  }));
  const meshes = sets.map((set, k) => {
    const mesh = new THREE.Mesh(set.geometry, materials[k]);
    mesh.frustumCulled = false;
    return mesh;
  });

  return {
    /** The stone pass, then the near end stood behind the far start. */
    meshes, uniforms, count,
    /**
     * @param {Float32Array} lift per block  @param {Float32Array} emphasis per block
     * @param seam the seam solved for this frame (src/seam.js), with the same lifts
     */
    setDynamics(lift, emphasis, seam) {
      // Uploaded only when something moved: a settled monument costs no buffer traffic.
      let moved = !uploaded.lifts;
      for (let i = 0; i < blocks.length && !moved; i++) moved = lift[i] !== uploaded.lift[i] || emphasis[i] !== uploaded.emphasis[i];
      if (moved) {
        uploaded.lifts = true;
        uploaded.lift.set(lift); uploaded.emphasis.set(emphasis);
        for (let k = 0; k < sets.length; k++) {
          const { aDyn, list } = sets[k];
          for (let n = 0; n < list.length; n++) {
            const i = list[n], o = blocks[i].occluders;
            aDyn.setXYZW(n, lift[i], lift[o[0].index], lift[o[1].index], emphasis[i]);
          }
          aDyn.needsUpdate = true;
        }
        // The phantoms are the far blocks as they stand, lifted, in side 0's frame; the near end
        // is carried there and cast along the view, so the seam follows every lift and tilt.
        for (let slot = 0; slot < phantoms; slot++) {
          const i = phantomSources[slot], blk = blocks[i], l = lift[i];
          uniforms.uPhC.value[slot].set(
            blk.center[0] + (blk.tread === 0 ? l : 0),
            blk.center[1] + (blk.tread === 1 ? l : 0),
            blk.center[2] + (blk.tread === 2 ? l : 0),
          );
        }
      }
      if (seam.version === uploaded.seam) return;
      uploaded.seam = seam.version;
      const r = seam.rot;
      uniforms.uSeamRot.value.set(r[0], r[1], r[2], r[3], r[4], r[5], r[6], r[7], r[8]);
      uniforms.uSeamOrigin.value.fromArray(seam.origin);
      const d = seam.dir;
      uniforms.uSeamDir.value.set(nonZero(d[0]), nonZero(d[1]), nonZero(d[2]));
      uniforms.uSeamCarry.value.fromArray(seam.carry);
    },
    /**
     * @param {Float32Array} light per block (3 each): the light as that block sees it, structure space
     * @param {Float32Array} own   per block and face (+x, +y, +z; 3 per block): how far the light holds the face (0..1; src/hold.js)
     */
    setLights(light, own) {
      let moved = false;
      for (let i = 0; i < light.length && !moved; i++) moved = light[i] !== uploaded.light[i] || own[i] !== uploaded.own[i];
      if (!moved) return;
      uploaded.light.set(light); uploaded.own.set(own);
      for (const { aLight, aOwn, list } of sets) {
        for (let n = 0; n < list.length; n++) {
          for (let k = 0; k < 3; k++) { aLight.array[n * 3 + k] = light[list[n] * 3 + k]; aOwn.array[n * 3 + k] = own[list[n] * 3 + k]; }
        }
        aLight.needsUpdate = true; aOwn.needsUpdate = true;
      }
    },
    dispose() { sets.forEach((set) => set.geometry.dispose()); materials.forEach((m) => m.dispose()); cube.dispose(); },
  };
}
