// THEME: ice. The world of static/site/themes/ice: the blocks are ice, the air a freezer's
// glare, the light a cold cyan, the dust snow. A plain module (no imports) of the shape
// static/home/src/theme.js describes: `config` over src/config.js, `glsl` the four hooks.
export default {
  config: {
    PALETTE: {
      coreDisplay: [0.9, 0.98, 1.0],       // the core burns to a blue-white
    },
    PLACE: {
      grain: 0.004,                        // ice is clean: barely a dither
      noiseScale: 3.0,
      drift: [0.08, 0.01],                 // blown snow: sideways, fast
      vignette: 0.3,
    },
    SHADING: {
      key: 1.15,                           // harsher: brighter key, less ambient, steeper tones
      ambient: 0.006,
      fill: 0.1,
      keyWrapPower: 3.2,
      topLight: 0.06,
      bevelGain: 0.7,                      // crisp, bright arrises
      lineWidthPx: 1.0,
      jointDarken: 0.8,                    // joints cut deep
      wearWidth: 0.03,
      wearGain: 0.05,
      grainAmount: 0.003,
      lanternWhite: [0.14, 0.17, 0.2],     // what the light adds to a face it does not hold: cold white
      lanternEdge: 0.5,
      mistFloor: 0.5,                      // far from the focus the ice still reads as ice
    },
    LANTERN: {
      haloSize: 2.6,
      haloGain: 0.3,
      haloGrain: 0.004,
      bloom: 0.006,                        // a tight bloom: a hard, small core
      bloomGain: 0.9,
      trailSize: 0.26,
    },
    DUST: {
      ambientCount: 420,
      burstCount: 120,
      fall: [0.05, 0.07],                  // snow falls, not drifts
      wander: 0.05,
      size: [1.8, 6.0],
      alpha: [0.18, 0.32],
      twinkle: 0.0,                        // steady flakes
      depth: 14,
    },
  },
  glsl: {
    // The ice: pale blue-white, cloudy inclusions, fine fracture planes, frost at the edges.
    surface: `
      // Fracture planes seen edge on: the borders of a cellular (Worley) partition of the face,
      // straight and branching, drawn as thin bright ridges.
      float worleyEdge(vec2 q, float w) {
        vec2 i = floor(q), f = fract(q);
        float d1 = 8.0, d2 = 8.0;
        for (int y = -1; y <= 1; y++) for (int x = -1; x <= 1; x++) {
          vec2 c = vec2(float(x), float(y));
          vec2 o = vec2(hash12(i + c), hash12(i + c + 17.0));
          float d = length(c + o - f);
          if (d < d1) { d2 = d1; d1 = d; } else if (d < d2) { d2 = d; }
        }
        return 1.0 - smoothstep(0.0, w, d2 - d1);
      }
      // The face's own two coordinates of a point: the texture sticks to the block.
      vec2 onFace(vec3 p, vec3 n) {
        return n.x > 0.5 ? p.yz : (n.y > 0.5 ? p.zx : p.xy);
      }
      // px is one device pixel in q: a crack is never drawn thinner than that, so it never breaks into dots.
      float crackField(vec2 q, float fine, float px) {
        return worleyEdge(q * 1.35 + 3.7, max(0.026, 1.5 * px * 1.35)) + fine * 0.5 * worleyEdge(q * 3.6 + 19.0, max(0.045, 1.5 * px * 3.6));
      }
      Surface surfaceAt(SurfaceIn s) {
        vec3 p = s.rest + vec3(s.block * 0.37);                   // each block its own ice
        vec2 q = onFace(p, s.n) + s.block * 0.61;
        // Cloudy inclusions: layered noise, large and fine; the ice went white where it froze fast.
        float cloud = valueNoise(p * 1.4) * 0.5 + valueNoise(p * 3.7 + 5.0) * 0.3 + valueNoise(p * 9.0 + 9.0) * 0.2;
        float cloudy = smoothstep(0.44, 0.78, cloud);
        // Rime: patches of the face frozen over matte and grainy, a crust on the clear ice.
        float rime = smoothstep(0.5, 0.68, valueNoise(p * 5.5 + 53.0) * 0.7 + valueNoise(p * 17.0 + 61.0) * 0.3) * smoothstep(0.3, 0.6, cloud);
        // Fractures: a sparse network of planes, a finer one only where the ice is stressed.
        float fine = smoothstep(0.52, 0.6, valueNoise(p * 1.1 + 23.0));
        float px = max(fwidth(q.x), fwidth(q.y));
        float f0 = crackField(q, fine, px);
        float e = 0.008;
        vec2 g = vec2(crackField(q + vec2(e, 0.0), fine, px) - f0, crackField(q + vec2(0.0, e), fine, px) - f0) / e;
        float crack = min(f0, 1.0);
        // The relief: the crack ridges, and a slow undulation so the sheet is no mirror.
        float u0 = valueNoise(p * 2.0 + 31.0);
        vec3 gu = vec3(valueNoise(p * 2.0 + 31.0 + vec3(e, 0.0, 0.0)) - u0, valueNoise(p * 2.0 + 31.0 + vec3(0.0, e, 0.0)) - u0, valueNoise(p * 2.0 + 31.0 + vec3(0.0, 0.0, e)) - u0) / e;
        vec3 tan = vec3(1.0) - abs(s.n);
        vec3 gCrack = s.n.x > 0.5 ? vec3(0.0, g.x, g.y) : (s.n.y > 0.5 ? vec3(g.y, 0.0, g.x) : vec3(g.x, g.y, 0.0));
        vec3 bump = -(gCrack * 0.012 + gu * 0.03) * tan;
        // Frost: the edges crust over, matte and white.
        float toEdge = min(min(s.edge.x, s.edge.y), s.edge.z);
        float rim = valueNoise(p * 16.0 + 41.0);
        float frost = (1.0 - smoothstep(0.0, 0.05 + 0.05 * rim, toEdge)) * (0.5 + 0.5 * rim);
        frost = smoothstep(0.15, 0.8, frost);
        // The colour: clear ice is blue, and the ice is white where it is cloudy, cracked or frosted.
        vec3 clear = vec3(0.47, 0.71, 0.92);
        vec3 white = vec3(0.90, 0.95, 1.0);
        float matte = max(frost, rime);
        vec3 albedo = mix(clear, white, min(cloudy * 0.55 + crack * 0.6 + matte * 0.9, 1.0));
        albedo *= 0.95 + 0.1 * valueNoise(p * 0.8 + 77.0);
        float gloss = mix(0.7, 0.06, matte) * (1.0 - 0.3 * cloudy);
        float shine = mix(110.0, 12.0, matte);
        // Light caught inside the block: faint, bluest in the clear ice.
        vec3 emit = vec3(0.006, 0.013, 0.022) * (1.0 - cloudy * 0.5) * (1.0 - frost * 0.6);
        return Surface(albedo, bump, gloss, shine, emit);
      }`,
    // The air: a freezer's white glare above, steel blue round the monument, a hard horizon at its
    // foot and a colder field below it, where blown snow streams past.
    air: `
      vec3 airAt(AirIn a) {
        float y = a.uv.y;
        vec3 glare = vec3(0.90, 0.94, 0.97);
        vec3 steel = vec3(0.19, 0.29, 0.41);
        vec3 field = vec3(0.10, 0.17, 0.27);
        float sky = smoothstep(0.3, 0.98, y + (a.n - 0.5) * 0.03);
        vec3 tone = mix(steel, glare, sky * sky * sky);
        // The horizon: a hard line at the monument's foot, a thin bright edge on it.
        float horizonY = -1.0;
        float h = a.toCentre.y - horizonY;
        float px = 1.0 / a.radius;
        float ground = 1.0 - smoothstep(-px, px, h);
        float edge = (1.0 - smoothstep(0.0, 2.5 * px, h)) * (1.0 - ground);
        tone = mix(tone, field, ground);
        tone += vec3(0.55, 0.6, 0.65) * edge;
        // Blown snow near the ground: the drifting noise thickest at the foot, and long streaks
        // of it streaming sideways, stretched flat and running faster than the mist.
        float haze = a.below * (0.3 + 0.7 * a.across) * smoothstep(0.35, 0.9, a.n);
        vec2 run = vec2(a.uv.x * a.aspect * 5.0 - a.time * 0.35, a.uv.y * 60.0);
        float streak = smoothstep(0.5, 0.95, vnoise(run) * 0.6 + vnoise(run * vec2(2.3, 1.7) + 9.0) * 0.4) * a.below * (0.5 + 0.5 * a.n);
        tone += vec3(0.22, 0.25, 0.28) * haze + vec3(0.3, 0.33, 0.36) * streak;
        // A cold lift behind the monument so its darkest faces keep their silhouette.
        tone += vec3(0.03, 0.04, 0.05) * exp(-dot(a.toCentre, a.toCentre) / 1.4);
        // The corners fall away, hard.
        float v = length((a.uv - 0.5) * vec2(1.0, 1.2));
        tone *= 1.0 - 0.34 * smoothstep(0.45, 0.95, v);
        return tone;
      }`,
    // The light: a hard, small core, a tight bloom, a four-point glint, hardly any halo.
    light: `
      vec3 lightAt(LightIn l) {
        float halo = 0.025 / (l.r * l.r + 0.025) * smoothstep(1.3, 0.45, l.r);
        float bloom = exp(-l.r * l.r / 0.008);
        float core = smoothstep(0.075, 0.03, l.r);
        float ang = atan(l.uv.y, l.uv.x);
        float rays = pow(abs(cos(ang * 2.0)), 48.0) * exp(-l.r * 3.0) * smoothstep(0.02, 0.09, l.r);
        return l.part < 0.5
          ? uAccent * halo * 0.45 * l.power + grain(l.frag, l.time, 0.004) * step(0.004, halo)
          : uAccent * (bloom * 1.0 + rays * 0.8) * l.power + vec3(0.9, 0.98, 1.0) * core * min(l.power, 1.0);
      }`,
    // Snow: a crisp white flake, six-pointed where it is big enough to be seen, turning as it falls.
    mote: `
      vec4 moteAt(MoteIn m) {
        float d = length(m.pc);
        float spin = m.seed.x * 6.2832 + m.time * (0.6 + m.seed.y * 1.2) * (m.seed.z > 0.5 ? 1.0 : -1.0);
        float ang = atan(m.pc.y, m.pc.x) + spin;
        float star = 0.5 + 0.5 * cos(ang * 6.0);
        float reach = mix(0.45, 1.0, pow(star, 0.7));
        float flake = smoothstep(reach, reach - 0.35, d);
        float disc = smoothstep(0.9, 0.3, d);
        float a = mix(disc, flake, m.seed.w) * m.alpha;
        vec3 tint = mix(vec3(dot(uAccent, vec3(0.2126, 0.7152, 0.0722))), uAccent, m.chroma);
        vec3 c = vec3(0.92, 0.97, 1.0) + tint * m.warm * 1.5;
        return vec4(c * a, 1.0);
      }`,
  },
};
