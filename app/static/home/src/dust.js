// Motes: idle life, and the only thing that gives the void a volume. They drift entirely in
// the vertex shader (no per-frame CPU work). A second, short-lived population is thrown
// from a point whenever something heavy locks into place.
import * as THREE from 'three';
import { PALETTE, SHADING } from './config.js';

const AMBIENT_COUNT = 150;
const BURST_COUNT = 90;
const BURST_LIFE = 2.2;

export function createDust() {
  const total = AMBIENT_COUNT + BURST_COUNT;
  const seed = new Float32Array(total * 4);
  const kind = new Float32Array(total);
  let s = 1337;
  const rnd = () => ((s = (s * 16807) % 2147483647) / 2147483647);
  for (let i = 0; i < total; i++) {
    seed.set([rnd(), rnd(), rnd(), rnd()], i * 4);
    kind[i] = i < AMBIENT_COUNT ? 0 : 1;
  }
  const geometry = new THREE.BufferGeometry();
  geometry.setAttribute('position', new THREE.BufferAttribute(new Float32Array(total * 3), 3));
  geometry.setAttribute('aSeed', new THREE.BufferAttribute(seed, 4));
  geometry.setAttribute('aKind', new THREE.BufferAttribute(kind, 1));

  const uniforms = {
    uTime: { value: 0 },
    uExtent: { value: new THREE.Vector2(10, 6) },   // half-size of the visible world
    uPixelRatio: { value: 1 },
    uLight: { value: new THREE.Vector3() },         // world xy, power
    uAccent: { value: new THREE.Vector3(...PALETTE.accentDisplay) },
    uBurstAt: { value: new THREE.Vector3() },       // world position
    uBurstTime: { value: -100 },
    uBurstDir: { value: new THREE.Vector2(0, 1) },
    uBurstGain: { value: 1 },                       // how much dust: a small drop raises less
    uFade: { value: 0 },
  };
  const material = new THREE.ShaderMaterial({
    uniforms,
    transparent: true,
    depthWrite: false,
    blending: THREE.AdditiveBlending,
    vertexShader: /* glsl */ `
      uniform float uTime;
      uniform vec2 uExtent;
      uniform float uPixelRatio;
      uniform vec3 uLight;
      uniform vec3 uBurstAt;
      uniform float uBurstTime;
      uniform vec2 uBurstDir;
      uniform float uBurstGain;
      uniform float uFade;
      attribute vec4 aSeed;
      attribute float aKind;
      varying float vAlpha;
      varying float vWarm;
      varying float vChroma;
      void main() {
        vec3 p;
        float alpha;
        float size;
        if (aKind < 0.5) {
          // ambient: a slow fall with a sideways wander, wrapped inside the view
          float speed = 0.012 + aSeed.w * 0.02;
          vec2 q = aSeed.xy * 2.0 - 1.0;
          q.y = fract(q.y * 0.5 + 0.5 - uTime * speed) * 2.0 - 1.0;
          q.x += 0.03 * sin(uTime * (0.11 + aSeed.z * 0.13) + aSeed.w * 40.0);
          p = vec3(q * uExtent * 1.05, (aSeed.z - 0.5) * 16.0);
          float twinkle = 0.6 + 0.4 * sin(uTime * (0.4 + aSeed.x) + aSeed.y * 30.0);
          alpha = (0.015 + 0.075 * aSeed.w * aSeed.w) * twinkle * smoothstep(1.0, 0.8, abs(q.y));
          size = 1.0 + 1.6 * aSeed.z * aSeed.z;
        } else {
          // burst: thrown, slowed by drag, then left to sink
          float age = uTime - uBurstTime;
          float life = clamp(age / ${BURST_LIFE.toFixed(1)}, 0.0, 1.0);
          float ang = (aSeed.x - 0.5) * 2.6;
          vec2 dir = mat2(cos(ang), -sin(ang), sin(ang), cos(ang)) * uBurstDir;
          float reach = (0.25 + aSeed.y * 1.5) * (1.0 - exp(-age * 3.2));
          p = uBurstAt + vec3(dir * reach + vec2(0.0, -0.22 * age * age * (0.4 + aSeed.w)), (aSeed.z - 0.5) * 0.6);
          alpha = uBurstGain * (0.14 + 0.3 * aSeed.w) * (1.0 - life) * (1.0 - life) * step(0.0, age) * step(age, ${BURST_LIFE.toFixed(1)});
          size = 1.0 + 1.8 * aSeed.z;
        }
        vec2 toLight = uLight.xy - p.xy;
        vWarm = uLight.z / (1.0 + dot(toLight, toLight) * 1.6);
        // A mote in the light's reach carries its hue; further out the light only brightens it.
        vChroma = 1.0 - smoothstep(${SHADING.moteRed[0].toFixed(3)}, ${SHADING.moteRed[1].toFixed(3)}, length(toLight));
        vAlpha = alpha * uFade;
        gl_Position = projectionMatrix * modelViewMatrix * vec4(p, 1.0);
        gl_PointSize = size * uPixelRatio;
      }
    `,
    fragmentShader: /* glsl */ `
      precision highp float;
      uniform vec3 uAccent;
      varying float vAlpha;
      varying float vWarm;
      varying float vChroma;
      void main() {
        float d = length(gl_PointCoord - 0.5) * 2.0;
        float a = smoothstep(1.0, 0.2, d) * vAlpha;
        // Motes are neutral; near the lantern they carry its light, nothing else.
        vec3 tint = mix(vec3(dot(uAccent, vec3(0.2126, 0.7152, 0.0722))), uAccent, vChroma);
        vec3 c = vec3(0.75) + tint * vWarm * 2.5;
        gl_FragColor = vec4(c * a, 1.0);
      }
    `,
  });
  const points = new THREE.Points(geometry, material);
  points.frustumCulled = false;
  points.renderOrder = 5;
  return {
    points, uniforms,
    /** @param gain 1 for a heavy contact; less for a small step dropping back */
    burst(world, dirX, dirY, time, gain = 1) {
      uniforms.uBurstAt.value.copy(world);
      if (dirX || dirY) uniforms.uBurstDir.value.set(dirX, dirY).normalize();
      uniforms.uBurstTime.value = time;
      uniforms.uBurstGain.value = gain;
    },
    /** True while a burst is still in the air. */
    bursting: (time) => time - uniforms.uBurstTime.value < BURST_LIFE,
    dispose() { geometry.dispose(); material.dispose(); },
  };
}
