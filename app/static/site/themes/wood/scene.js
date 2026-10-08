// THEME: wood. The monument is a child's set of wooden blocks: sanded maple, rounded edges, a
// grain that runs along each block and shows its rings on the ends, each block cut from its own
// plank. The air is a playroom in the afternoon: cream above, honey below, slow light on the wall.
// The light is a toy's red lamp; the dust is sunlit. The contract is static/home/src/theme.js.
//
// Kept: the paradox rule (every surface is a function of the block's own rest coordinates, its
// face, its index and the time; the air of screen position and time), the three face tones
// (the key stays fixed to the stone; the material only modulates it), one light (the only
// saturated colour; the wood stays a pale warm neutral beside it).
export default {
  config: {
    PLACE: {
      noiseScale: 1.6,
      drift: [0.012, 0.018],
      grain: 0.008,
    },
    SHADING: {
      // Sanded wood has no arris to catch a line: the joints barely read, the bevels and wear
      // are gone (the edges are rounded by the material's bump instead).
      lineWidthPx: 0.9,
      jointDarken: 0.26,
      bevelGain: 0.0,
      wearGain: 0.0,
      wearWidth: 0.05,
      // A room lit all round: a little more ambient and fill, the three families kept apart.
      ambient: 0.05,
      fill: 0.22,
      topLight: 0.08,
      aoStrength: 0.7,
      // The far side of the monument sits in the same bright room, only a little quieter.
      mistFloor: 0.62,
      dimSelected: 0.3,
      // What the lamp adds to a face it does not hold: a warm white, per unit of its red.
      lanternWhite: [0.2, 0.16, 0.12],
      lanternEdge: 0.15,
    },
    LANTERN: {
      // The lamp's look is the light hook below; these size its quad and its comet.
      haloSize: 3.0,
      trailGain: 0.25,
    },
    DUST: {
      ambientCount: 170,
      fall: [0.006, 0.012],
      wander: 0.04,
      size: [1.4, 2.2],
      alpha: [0.05, 0.12],
      twinkle: 0.5,
    },
  },
  glsl: {
    // ------------------------------------------------------------ the blocks: sanded maple
    surface: /* glsl */ `
      // A plank's grain on a face: late-wood lines spaced across the grain (bunching and
      // spreading as a real plank's do), running nearly straight along it, broken here and
      // there; a fine fibre between them; broad patches of darker and paler wood under it all.
      float plank(vec3 p, vec3 along, vec3 cross_, vec3 nAxis) {
        float u = dot(p, cross_) + 0.37 * dot(p, nAxis);   // across the grain (the face's own offset in)
        float spread = valueNoise(p * (along * 0.5 + cross_ * 1.4) + 3.0) - 0.5;   // slow: lines bunch and spread
        float wander = valueNoise(p * (along * 0.9 + cross_ * 3.2) + 11.0) - 0.5;  // the lines lean and sway
        float jitter = valueNoise(p * (along * 9.0 + cross_ * 14.0) + 17.0) - 0.5; // a little roughness
        float phase = u * 5.5 + spread * 3.4 + wander * 1.2 + jitter * 0.18;
        float line = pow(0.5 + 0.5 * sin(6.2832 * phase), 5.0);
        float broken = 0.55 + 0.45 * valueNoise(p * (along * 2.2 + cross_ * 30.0) + 7.0);
        return line * broken;
      }
      Surface surfaceAt(SurfaceIn s) {
        vec3 along = abs(s.travel);                         // the grain runs along the block
        vec3 nAxis = abs(s.n);
        vec3 cross_ = clamp(vec3(1.0) - along - nAxis, 0.0, 1.0);   // across the grain, on this face
        float endGrain = dot(along, nAxis);                 // 1 on a face cut across the grain

        // Each block is its own piece of wood: its own offset into the plank, its own tint.
        float piece = hash13(vec3(s.block * 3.17, 1.0, 5.0));
        float tint = hash13(vec3(s.block * 1.31, 9.0, 2.0)) - 0.5;
        float hue = hash13(vec3(s.block * 0.77, 4.0, 8.0)) - 0.5;
        vec3 p = s.rest + vec3(piece * 41.0, piece * 17.0, piece * 29.0);

        // The face's grain: lines along the block...
        float lines = plank(p, along, cross_, nAxis);
        float fibre = valueNoise(p * (along * 6.0 + cross_ * 80.0 + nAxis * 80.0) + 5.0);
        float figure = valueNoise(p * (along * 0.7 + cross_ * 1.8 + nAxis * 1.8) + 31.0);   // sapwood and heartwood
        // ...and on the ends, the rings round an off-centre pith.
        vec3 acrossAll = vec3(1.0) - along;
        vec3 c = s.box * acrossAll + (vec3(0.18, -0.12, 0.22) + piece * 0.3) * acrossAll;
        float r = length(c) * 6.0 + (valueNoise(p * 3.0 + 23.0) - 0.5) * 1.6;
        float rings = pow(0.5 + 0.5 * sin(6.2832 * r), 3.0);
        float grain = mix(lines, rings * 0.8, endGrain);

        // Pale maple in linear light, the late wood darker and warmer, the figure between.
        vec3 pale = vec3(0.86, 0.64, 0.38);
        vec3 late = vec3(0.56, 0.32, 0.13);
        vec3 albedo = mix(pale, late, 0.08 + grain * 0.3 + (figure - 0.5) * 0.2 + (fibre - 0.5) * 0.1);
        albedo *= 1.0 + tint * 0.12;                                    // one plank lighter, one darker
        albedo *= vec3(1.0 + hue * 0.03, 1.0, 1.0 - hue * 0.08);        // one pinker (birch), one yellower (pine)
        albedo *= mix(vec3(1.0), vec3(0.92, 0.86, 0.78), endGrain * 0.6);   // the ends drink the light

        // The edges are sanded round: near an edge the normal bends out toward the face beyond,
        // and the sanding has cut through the grain there, so the arris is a shade paler.
        float rr = 0.09;
        vec3 t = clamp(1.0 - s.edge / rr, 0.0, 1.0);
        vec3 round_ = (t * t) * sign(s.box) * (vec3(1.0) - nAxis);
        float sanded = max(max(t.x, t.y), t.z);
        albedo = mix(albedo, pale * 1.04, sanded * sanded * 0.35);
        vec3 bump = 1.0 * round_;

        // A sanded sheen: low, broad.
        float gloss = 0.1 + 0.04 * (1.0 - grain);
        return Surface(albedo, bump, gloss, 10.0, vec3(0.0));
      }
    `,

    // ------------------------------------------------------------ the air: a playroom's wall
    air: /* glsl */ `
      vec3 airAt(AirIn a) {
        // Ivory above, honey toward the floor, the ramp wandering a little under the light.
        float h = smoothstep(-0.15, 1.1, a.uv.y + (a.n - 0.5) * 0.14);
        vec3 tone = mix(vec3(0.45, 0.37, 0.25), vec3(0.80, 0.755, 0.66), h);
        // Afternoon light from a window off to the left: a broad warm patch, breathing very slowly.
        vec2 sun = vec2(0.22 + 0.03 * sin(a.time * 0.07), 0.82);
        vec2 d = (a.uv - sun) * vec2(a.aspect, 1.0);
        tone += vec3(0.15, 0.125, 0.08) * exp(-dot(d, d) / 1.6) * (0.85 + 0.3 * a.n);
        // The wall a touch quieter right behind the monument, so the pale treads keep their edge.
        tone *= 1.0 - 0.13 * exp(-dot(a.toCentre, a.toCentre) / 1.3);
        // The corners fall away, softly.
        float v = length((a.uv - 0.5) * vec2(1.0, 1.2));
        tone *= 1.0 - 0.14 * smoothstep(0.45, 1.05, v);
        return tone;
      }
    `,

    // ------------------------------------------------------------ the light: a toy lamp
    light: /* glsl */ `
      vec3 lightAt(LightIn l) {
        float edge = smoothstep(1.5, 0.75, l.r);
        float halo = 0.05 / (l.r * l.r + 0.05) * edge;
        float bloom = exp(-l.r * l.r / 0.02);
        float core = smoothstep(0.082, 0.036, l.r);
        // Screened over a bright room the hue thins, so the halo carries it deeper than the accent;
        // the core burns to a warm white (the void's PALETTE.coreDisplay, warmed).
        vec3 deep = uAccent * uAccent;
        return l.part < 0.5
          ? deep * halo * 0.8 * l.power + grain(l.frag, l.time, 0.008) * step(0.004, halo)
          : mix(deep, uAccent, 0.5) * bloom * 1.1 * l.power + vec3(1.0, 0.9, 0.78) * core * min(l.power, 1.0);
      }
    `,

    // ------------------------------------------------------------ the dust: sunlit
    mote: /* glsl */ `
      vec4 moteAt(MoteIn m) {
        float d = length(m.pc);
        float a = smoothstep(1.0, 0.15, d) * m.alpha;
        vec3 gold = vec3(1.0, 0.88, 0.62);
        vec3 tint = mix(gold, uAccent, m.chroma);
        vec3 c = gold * 0.85 + tint * m.warm * 2.0;
        return vec4(c * a, 1.0);
      }
    `,
  },
};
