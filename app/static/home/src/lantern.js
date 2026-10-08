// The one coloured thing in the world: a small light. It is drawn without depth test
// because on an impossible object "behind" has no meaning for something that floats
// outside the surface; its influence on the stone is computed in the stone shader.
//
// Crossing the seam the light exists at both ends of the chain at once, a gap apart along
// the view axis: from the true angle one place, tilted two. So it is drawn twice there,
// cross-fading from the near end to the far start, and never visibly jumps the gap.
//
// It is drawn in two parts. Its halo, and the comet it leaves while it moves, are the hall's air lit
// round it: drawn before the stone, so the stone stands in front of them and shows only the light
// that falls on it (src/monument.js), never a veil of red over grey. Its core and bloom are the
// eye's: drawn over everything. Both are screened (src + dst - src * dst), brightening toward white
// and never past it.
//
// The one place it can be behind something is the door: once it has gone into the opening the
// riser round it hides it, and only what lies within the opening on screen is still seen
// (src/frame.js passes the opening's outline and how far in the light is).
//
// How it looks is the theme's (src/theme.js `light`, with the LANTERN values of src/config.js):
// the void's is a halo of lit air, a bloom in the eye and a core that burns white.
import * as THREE from 'three';
import { PALETTE, SHADING, LANTERN } from './config.js';
import { GRADE } from './glsl.js';
import { hook, VOID_LIGHT } from './theme.js';

const HALO_SIZE = LANTERN.haloSize;   // beams, full quad width
const CORE_RADIUS = SHADING.lightRadius;
const BLOOM = LANTERN.bloom;          // beams squared: the bloom's spread (exp(-r^2 / BLOOM))
const TRAIL_POINTS = LANTERN.trailPoints; // afterimages laid back along the path while the light is moving
const TRAIL_SIZE = LANTERN.trailSize; // beams, diameter of the newest afterimage
const SCREEN = { blending: THREE.CustomBlending, blendEquation: THREE.AddEquation, blendSrc: THREE.OneMinusDstColorFactor, blendDst: THREE.OneFactor };
// A theme may draw its light OVER the frame instead (LANTERN.blend 'over'): premultiplied colour and
// coverage, so it can be opaque and darker than the air behind it (an orb, a lantern's body).
const OVER = { blending: THREE.CustomBlending, blendEquation: THREE.AddEquation, blendSrc: THREE.OneFactor, blendDst: THREE.OneMinusSrcAlphaFactor };
const over = LANTERN.blend === 'over';

const spriteVertex = /* glsl */ `
  varying vec2 vUv;
  varying vec2 vWorld;
  void main() {
    vUv = uv * 2.0 - 1.0;
    vWorld = (modelMatrix * vec4(position, 1.0)).xy;
    gl_Position = projectionMatrix * modelViewMatrix * vec4(position, 1.0);
  }
`;
const spriteFragment = /* glsl */ `
  precision highp float;
  uniform vec3 uAccent;
  uniform float uPower;
  uniform float uWeight;   // share of the light drawn here (the two ends of a crossing sum to 1)
  uniform float uTime;
  uniform vec2 uMaskO, uMaskU, uMaskV;   // the door's opening on screen (world x, y): a corner and its two edges
  uniform float uMaskOn;                // how far the light is inside the opening (0: nothing hides it)
  uniform float uPart;                  // 0: the halo, under the stone; 1: core and bloom, over everything
  varying vec2 vUv;
  varying vec2 vWorld;
  ${GRADE}
  ${hook('light', VOID_LIGHT)}
  void main() {
    // Inside the wall the riser hides the light except through the opening (antialiased edges).
    float seen = 1.0;
    if (uMaskOn > 0.0) {
      vec2 w = vWorld - uMaskO;
      float det = uMaskU.x * uMaskV.y - uMaskU.y * uMaskV.x;
      vec2 ab = vec2(w.x * uMaskV.y - w.y * uMaskV.x, uMaskU.x * w.y - uMaskU.y * w.x) / det;
      vec2 edge = min(ab, 1.0 - ab) / max(fwidth(ab), 1.0e-6);
      seen = mix(1.0, clamp(min(edge.x, edge.y) + 0.5, 0.0, 1.0), uMaskOn);
    }
    float r = length(vUv) * ${(HALO_SIZE / 2).toFixed(3)};   // beams from the centre
    vec3 c = lightAt(LightIn(r, vUv, gl_FragCoord.xy, uPower, uPart, uTime));
    gl_FragColor = vec4(max(c, 0.0) * uWeight * seen, ${over ? 'clamp(lightCover(LightIn(r, vUv, gl_FragCoord.xy, uPower, uPart, uTime)), 0.0, 1.0) * uWeight * seen' : '1.0'});
  }
`;

export function createLantern() {
  const shared = {
    uAccent: { value: new THREE.Vector3(...PALETTE.accentDisplay) },
    uTime: { value: 0 },
    uMaskO: { value: new THREE.Vector2() }, uMaskU: { value: new THREE.Vector2(1, 0) }, uMaskV: { value: new THREE.Vector2(0, 1) },
    uMaskOn: { value: 0 },
  };
  const uniforms = { ...shared, uPower: { value: 0 }, uWeight: { value: 1 } };
  const twinUniforms = { ...shared, uPower: uniforms.uPower, uWeight: { value: 0 } };
  const quad = new THREE.PlaneGeometry(HALO_SIZE, HALO_SIZE);
  const materials = [];
  /** One part of one end of the light: the halo (under the stone) or the core and bloom (over all). */
  const sprite = (u, part) => {
    const material = new THREE.ShaderMaterial({
      uniforms: { ...u, uPart: { value: part } }, depthTest: false, depthWrite: false, transparent: over || part === 1, ...(over ? OVER : SCREEN),
      vertexShader: spriteVertex, fragmentShader: spriteFragment,
    });
    materials.push(material);
    const m = new THREE.Mesh(quad, material);
    m.frustumCulled = false;
    m.renderOrder = part === 1 ? 10 : -5;   // the backdrop is -10, the stone 0
    return m;
  };
  const halo = sprite(uniforms, 0), haloTwin = sprite(twinUniforms, 0);
  const mesh = sprite(uniforms, 1), twin = sprite(twinUniforms, 1);
  twin.visible = haloTwin.visible = false;

  // The trail: the light is weightless, the eye is not. A short comet, the air it has just lit,
  // shows which way round the loop it went (under the stone, like the halo); at rest every point
  // has zero fade and nothing is drawn. Each point is two, one per end of the seam, weighted like
  // the light itself.
  const trailGeometry = new THREE.BufferGeometry();
  const trailPosition = new THREE.BufferAttribute(new Float32Array(TRAIL_POINTS * 2 * 3), 3);
  const trailFade = new THREE.BufferAttribute(new Float32Array(TRAIL_POINTS * 2), 1);
  trailPosition.setUsage(THREE.DynamicDrawUsage); trailFade.setUsage(THREE.DynamicDrawUsage);
  trailGeometry.setAttribute('position', trailPosition);
  trailGeometry.setAttribute('aFade', trailFade);
  const trailUniforms = { uAccent: shared.uAccent, uPixelsPerBeam: { value: 100 } };
  const trailMaterial = new THREE.ShaderMaterial({
    uniforms: trailUniforms,
    depthTest: false,
    depthWrite: false,
    ...SCREEN,
    vertexShader: /* glsl */ `
      uniform float uPixelsPerBeam;
      attribute float aFade;
      varying float vFade;
      void main() {
        vFade = aFade;
        gl_Position = projectionMatrix * modelViewMatrix * vec4(position, 1.0);
        gl_PointSize = ${TRAIL_SIZE.toFixed(2)} * uPixelsPerBeam * (0.35 + 0.65 * aFade);
      }
    `,
    fragmentShader: /* glsl */ `
      precision highp float;
      uniform vec3 uAccent;
      varying float vFade;
      void main() {
        float d = length(gl_PointCoord - 0.5) * 2.0;
        gl_FragColor = vec4(uAccent * max(exp(-d * d * 3.5) - 0.03, 0.0) * vFade * ${LANTERN.trailGain.toFixed(3)}, 1.0);
      }
    `,
  });
  const trail = new THREE.Points(trailGeometry, trailMaterial);
  trail.frustumCulled = false;
  trail.renderOrder = -4;   // in the air, under the stone (the backdrop is -10, the halo -5)

  return {
    mesh, twin, trail, uniforms, trailUniforms, trailPoints: TRAIL_POINTS, coreRadius: CORE_RADIUS,
    bloomRadius: Math.sqrt(BLOOM * Math.log(30)),   // beams: where the bloom has fallen under 1/30
    /** Everything drawn for the light (test hooks hide it all to look at the stone alone). */
    sprites: [halo, haloTwin, mesh, twin, trail],
    /**
     * @param near  world position at the near end of the seam (or simply where the light is)
     * @param far   world position at the far start; only read while blend > 0
     * @param blend 0 = all at near, 1 = all at far
     */
    setLight(near, far, z, power, blend) {
      mesh.position.set(near.x, near.y, z); halo.position.copy(mesh.position);
      uniforms.uPower.value = power;
      uniforms.uWeight.value = 1 - blend;
      twin.visible = haloTwin.visible = blend > 0;
      if (twin.visible) { twin.position.set(far.x, far.y, z); haloTwin.position.copy(twin.position); twinUniforms.uWeight.value = blend; }
    },
    /** The light is `inside` (0..1) the opening whose screen outline is corner o and edges du, dv (world x, y). */
    setMask(inside, o, du, dv) {
      shared.uMaskOn.value = inside;
      if (inside > 0) { shared.uMaskO.value.set(o.x, o.y); shared.uMaskU.value.set(du.x, du.y); shared.uMaskV.value.set(dv.x, dv.y); }
    },
    setTrailPoint(i, near, far, z, fade, blend) {
      trailPosition.setXYZ(2 * i, near.x, near.y, z); trailFade.array[2 * i] = fade * (1 - blend);
      trailPosition.setXYZ(2 * i + 1, far.x, far.y, z); trailFade.array[2 * i + 1] = fade * blend;
    },
    commitTrail() { trailPosition.needsUpdate = true; trailFade.needsUpdate = true; },
    dispose() { quad.dispose(); materials.forEach((m) => m.dispose()); trailGeometry.dispose(); trailMaterial.dispose(); },
  };
}
