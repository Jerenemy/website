// THEME: nature. The homepage's world as a summer dusk in a wood: the blocks are grey-brown rock,
// mossy on top, soil in their seams; the air a dusk under a canopy; the light a firefly; the dust
// other fireflies, far off, each blinking in its own time. The contract is static/home/src/theme.js.
export default {
  config: {
    PALETTE: { coreDisplay: [1.0, 1.0, 0.82] },
    PLACE: { drift: [0.015, 0.02], vignette: 0.3, grain: 0.012 },
    SHADING: {
      jointDarken: 0.4,
      bevelGain: 0.14,
      wearGain: 0.04,
      wearWidth: 0.06,
      mistFloor: 0.16,
      mistOuter: 2.0,
      glowPower: 1.8,
      lanternWhite: [0.14, 0.16, 0.11],
    },
    LANTERN: { haloGain: 0.5, haloSize: 3.4, bloom: 0.013, bloomGain: 0.85, trailGain: 0.14 },
    DUST: {
      ambientCount: 34,
      fall: [-0.006, -0.01],     // fireflies rise, slowly
      wander: 0.09,
      size: [7.0, 5.0],
      alpha: [0.6, 0.3],
      twinkle: 0.0,              // the blinking is the mote's own (below)
    },
  },
  glsl: {
    surface: /* glsl */ `
      // The rock's relief, a height field fixed to the block.
      float rockHeight(vec3 p) {
        return valueNoise(p * 4.5) * 0.55 + valueNoise(p * 13.0 + 3.1) * 0.3 + valueNoise(p * 38.0 + 9.7) * 0.15;
      }
      Surface surfaceAt(SurfaceIn s) {
        vec3 p = s.rest;
        vec3 tangent = vec3(1.0) - abs(s.n);
        vec3 e = s.edge;                       // very large along the face's own axis already
        float edgeMin = min(min(e.x, e.y), e.z);
        float fromTop = dot(s.ext - s.box, s.up);   // on a wall: how far down from the block's top

        // --- the rock: grey-brown, each block its own piece ---
        float q1 = hash13(vec3(s.block, 7.0, 3.0)), q2 = hash13(vec3(s.block, 1.0, 2.0));
        vec3 rockA = vec3(0.30, 0.262, 0.212), rockB = vec3(0.255, 0.24, 0.218), rockC = vec3(0.34, 0.275, 0.19);
        vec3 rock = mix(mix(rockA, rockB, q1), rockC, q2 * 0.5) * (0.88 + 0.24 * hash13(vec3(s.block, 5.0, 9.0)));
        float mottle = valueNoise(p * 2.1 + 17.0) * 0.6 + valueNoise(p * 7.3 + 1.0) * 0.3 + valueNoise(p * 27.0) * 0.1;
        float speckle = hash13(floor(p * 110.0)) - 0.5;
        rock *= (1.0 + (mottle - 0.5) * 0.45 + speckle * 0.14) * vec3(1.04, 1.0, 0.93);
        // A few fine cracks, sparse: a thin contour of a noise where a slower one allows it.
        float vein = valueNoise(p * vec3(4.0, 7.0, 4.0) + 41.0);
        float crack = (1.0 - smoothstep(0.0, 0.03, abs(vein - 0.5))) * smoothstep(0.55, 0.8, valueNoise(p * 1.3 + 77.0));
        rock *= 1.0 - 0.3 * crack;

        // --- the relief: a rough rocky surface, arrises slightly rounded ---
        float h0 = rockHeight(p);
        float eps = 0.012;
        vec3 grad = vec3(
          rockHeight(p + vec3(eps, 0.0, 0.0)) - h0,
          rockHeight(p + vec3(0.0, eps, 0.0)) - h0,
          rockHeight(p + vec3(0.0, 0.0, eps)) - h0) / eps;
        vec3 bump = -grad * tangent * 0.09;
        float r = 0.05;
        vec3 roundOff = (1.0 - smoothstep(0.0, r, e)) * sign(s.box) * tangent;
        bump -= 0.3 * roundOff;

        // --- the soil: dark, warm, in the seams and the crevices, and pooled on the treads ---
        float seamN = valueNoise(p * 9.0 + 5.0);
        float seam = 1.0 - smoothstep(0.015, 0.06 + 0.07 * seamN, edgeMin);
        float crevice = smoothstep(0.5, 0.3, h0) * (0.35 + 0.65 * s.onTop);   // the low places of the relief hold soil, most on a tread
        float pooled = s.onTop * smoothstep(0.62, 0.35, valueNoise(p * 2.6 + 23.0)) * 0.35;
        float dirt = clamp(seam * (0.55 + 0.45 * seamN) + crack * 0.6 + crevice * 0.55 + pooled, 0.0, 1.0);
        vec3 soil = vec3(0.075, 0.05, 0.028) * (0.8 + 0.4 * valueNoise(p * 31.0));

        // --- the moss: soft green, patched over the tops and creeping down from the top edge ---
        float patchN = valueNoise(p * 2.4 + vec3(s.block * 3.7, 0.0, 0.0)) * 0.65 + valueNoise(p * 6.8 + 2.0) * 0.35;
        float clump = smoothstep(0.42, 0.6, patchN);
        float ragged = valueNoise(p * 8.0 + 61.0);
        float creep = smoothstep(0.3, 0.0, fromTop - 0.18 * ragged + 0.06) * smoothstep(0.35, 0.55, patchN + 0.1 * ragged);
        float moss = max(s.onTop * clump, (1.0 - s.onTop) * creep);
        moss = max(moss, s.onTop * seam * 0.5 * smoothstep(0.3, 0.5, patchN));   // moss gathers in the seams of a tread
        moss *= 1.0 - 0.6 * crack;
        float mossTone = valueNoise(p * 19.0 + 7.0) * 0.5 + valueNoise(p * 55.0) * 0.5;
        vec3 mossC = mix(vec3(0.07, 0.16, 0.03), vec3(0.17, 0.30, 0.06), mossTone);
        mossC = mix(mossC, vec3(0.22, 0.28, 0.08), smoothstep(0.7, 0.95, mossTone) * 0.5);   // its bright tips

        // --- lichen: pale flecks on bare rock ---
        float lich = smoothstep(0.6, 0.72, valueNoise(p * 16.0 + 31.0)) * smoothstep(0.5, 0.7, valueNoise(p * 1.4 + 53.0));
        vec3 lichenC = vec3(0.38, 0.44, 0.26);

        vec3 albedo = rock;
        albedo = mix(albedo, lichenC, lich * 0.6);
        albedo = mix(albedo, soil, dirt);
        albedo = mix(albedo, mossC, moss);
        // Moss has a pile: it softens the relief under it and bumps its own tufts.
        bump = mix(bump, -grad * tangent * 0.03, moss);
        float gloss = 0.06 * moss;            // a touch of damp on the moss; the rock is dry
        return Surface(albedo, bump, gloss, 14.0, vec3(0.0));
      }
    `,
    air: /* glsl */ `
      vec3 airAt(AirIn a) {
        // Dusk under a canopy: deep blue-green above, lifting warm toward the ground.
        float h = smoothstep(-0.05, 1.05, a.uv.y + (a.n - 0.5) * 0.2);
        vec3 deep = vec3(0.004, 0.0095, 0.016);
        vec3 lift = vec3(0.030, 0.031, 0.015);
        vec3 tone = mix(lift, deep, h);
        // The canopy: the drifting noise reads as leaves against the last light, above.
        float canopy = smoothstep(0.35, 0.75, a.n);
        tone = mix(tone, tone * 0.5, canopy * smoothstep(0.25, 0.9, a.uv.y));
        tone += vec3(0.006, 0.009, 0.004) * (1.0 - canopy) * smoothstep(0.4, 1.0, a.uv.y);
        // The pocket of air behind the stone, so its darkest faces still read.
        tone += vec3(0.0035, 0.004, 0.003) * exp(-dot(a.toCentre, a.toCentre) / 1.6);
        // Ground mist, pale and warm, pooling under the stone.
        tone += vec3(0.013, 0.014, 0.009) * a.below * a.across * (0.45 + 1.1 * a.n);
        // The corners fall away, into the wood.
        float v = length((a.uv - 0.5) * vec2(1.0, 1.15));
        tone *= 1.0 - 0.3 * smoothstep(0.35, 0.95, v);
        return tone;
      }
    `,
    light: /* glsl */ `
      vec3 lightAt(LightIn l) {
        // A firefly: its glow breathes, slow and uneven, never quite out.
        float breath = sin(l.time * 1.5) + 0.45 * sin(l.time * 0.61 + 1.0);
        float pulse = 0.55 + 0.45 * smoothstep(-0.9, 1.0, breath);
        vec3 glowC = mix(uAccent, vec3(0.55, 1.0, 0.35), 0.3);   // the lit air is greener than the body
        float edge = smoothstep(1.7, 0.9, l.r);
        float halo = 0.06 / (l.r * l.r + 0.06) * edge;
        float bloom = exp(-l.r * l.r / 0.013);
        float near = exp(-l.r * l.r / 0.0016);
        // The body: a small oval, burning a pale yellow.
        vec2 b = l.uv * 1.7 * vec2(1.0, 0.8);
        float body = smoothstep(0.075, 0.03, length(b));
        return l.part < 0.5
          ? glowC * halo * 0.5 * l.power * pulse + grain(l.frag, l.time, 0.012) * step(0.004, halo)
          : uAccent * (bloom * 0.85 + near * 0.5) * l.power * pulse + vec3(1.0, 1.0, 0.82) * body * min(l.power, 1.0) * (0.75 + 0.25 * pulse);
      }
    `,
    mote: /* glsl */ `
      vec4 moteAt(MoteIn m) {
        float d = length(m.pc);
        if (m.kind > 0.5) {
          // Thrown dust: a little dry earth, neutral and dim.
          float a = smoothstep(1.0, 0.2, d) * m.alpha;
          return vec4(vec3(0.5, 0.45, 0.35) * a, 1.0);
        }
        // A firefly far off: its own flash, in its own time: up quickly, a hang, a slow fade.
        float period = 2.4 + 3.4 * m.seed.z;
        float ph = fract(m.time / period + m.seed.x);
        float on = smoothstep(0.0, 0.06, ph) * (1.0 - smoothstep(0.16, 0.4, ph));
        float glow = exp(-d * d * 2.6) * 0.55 + smoothstep(0.45, 0.05, d);
        glow *= smoothstep(1.0, 0.7, d);
        vec3 c = vec3(0.8, 1.0, 0.34);
        float a = m.alpha * (0.03 + on);     // between flashes, a faint ember
        return vec4(c * glow * a * 1.8, 1.0);
      }
    `,
  },
};
