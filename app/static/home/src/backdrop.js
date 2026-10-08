// The place. One full-screen pass behind everything: the air of a hall too large to see.
// Near-black above (the ceiling is beyond sight), lifting through slow, drifting mist to
// charcoal below; a pocket of lifted air behind the monument keeps its darkest faces legible; ground mist
// pools under it; the corners fall away.
//
// Paradox rule: everything here is a function of screen x, y and time only, never of
// distance along the view axis. And all of it is neutral grey: the monument is the only
// object with full contrast, the light the only colour. Grain doubles as dither.
//
// The air itself is the theme's (src/theme.js `air`, with the PLACE values of src/config.js):
// this pass computes what every air needs (the frame, the monument's place in it, the drifting
// mist noise) and grades what the hook returns.
import * as THREE from 'three';
import { PLACE } from './config.js';
import { GRADE } from './glsl.js';
import { hook, VOID_AIR } from './theme.js';

const f = (v) => v.toFixed(5);

export function createBackdrop() {
  const uniforms = {
    uViewport: { value: new THREE.Vector2(1, 1) },   // device pixels
    uCenter: { value: new THREE.Vector2(0.5, 0.5) }, // monument centre, device pixels, y up
    uRadius: { value: 600 },                         // monument bounding radius, device pixels
    uTime: { value: 0 },
    uExposure: { value: 1 },
  };
  const material = new THREE.ShaderMaterial({
    uniforms,
    depthTest: false,
    depthWrite: false,
    vertexShader: /* glsl */ `void main() { gl_Position = vec4(position.xy, 0.0, 1.0); }`,
    fragmentShader: /* glsl */ `
      precision highp float;
      uniform vec2 uViewport;
      uniform vec2 uCenter;
      uniform float uRadius;
      uniform float uTime;
      uniform float uExposure;
      ${GRADE}
      ${hook('air', VOID_AIR)}
      void main() {
        vec2 frag = gl_FragCoord.xy;
        vec2 uv = frag / uViewport;
        float aspect = uViewport.x / uViewport.y;
        vec2 q = vec2(uv.x * aspect, uv.y) * ${f(PLACE.noiseScale)};   // square cells, whatever the frame
        vec2 run = vec2(${f(PLACE.drift[0])}, -${f(PLACE.drift[1])}) * uTime;
        float n = vnoise(q + run) * 0.65 + vnoise(q * 2.7 - run * 1.6 + 7.3) * 0.35;

        // Where the monument stands: the pocket of air behind it, the mist that pools under it.
        vec2 toCentre = (frag - uCenter) / uRadius;
        float foot = uCenter.y - uRadius * ${f(PLACE.footDepth)};
        float below = smoothstep(foot + 0.4 * uRadius, foot - 0.7 * uRadius, frag.y);
        float across = exp(-toCentre.x * toCentre.x / ${f(PLACE.mistReach * PLACE.mistReach)});

        vec3 tone = airAt(AirIn(uv, frag, aspect, toCentre, uRadius, below, across, n, uTime));
        vec3 c = toSRGB(tone * uExposure) + grain(frag, uTime, ${f(PLACE.grain)});
        gl_FragColor = vec4(c, 1.0);
      }
    `,
  });
  const mesh = new THREE.Mesh(new THREE.PlaneGeometry(2, 2), material);
  mesh.frustumCulled = false;
  mesh.renderOrder = -10;
  return {
    mesh, uniforms,
    /** @param layout the stage layout  @param cx, cy monument centre in CSS px (y down)  @param radius bounding radius in CSS px */
    place(layout, cx, cy, radius) {
      uniforms.uViewport.value.set(layout.width * layout.dpr, layout.height * layout.dpr);
      uniforms.uCenter.value.set(cx * layout.dpr, (layout.height - cy) * layout.dpr);
      uniforms.uRadius.value = radius * layout.dpr;
    },
    dispose() { mesh.geometry.dispose(); material.dispose(); },
  };
}
