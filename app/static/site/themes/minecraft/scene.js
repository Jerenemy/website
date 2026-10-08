// THEME: minecraft. The homepage's world as the game draws it: every block a 16 x 16 texel
// pixel-art tile (grass blocks for the steps, stone, dirt and ore for the rest), flat-shaded
// under the three fixed face tones; a day sky with pixel clouds; a torch; square particles.
// A plain ES module with no imports, of the shape static/home/src/theme.js describes.

// The game's textures, as sRGB hex, converted once to the linear light the surface hook returns.
const lin = (hex) => {
  const c = [1, 3, 5].map((i) => parseInt(hex.slice(i, i + 2), 16) / 255)
    .map((v) => (v <= 0.04045 ? v / 12.92 : ((v + 0.055) / 1.055) ** 2.4));
  return `vec3(${c.map((v) => v.toFixed(4)).join(', ')})`;
};
// Display-space colours (the light and the motes are composited in display space).
const disp = (hex) => `vec3(${[1, 3, 5].map((i) => (parseInt(hex.slice(i, i + 2), 16) / 255).toFixed(3)).join(', ')})`;

const TEXELS = 16;   // one block = one beam = 16 texels, nearest-neighbour

const SURFACE = /* glsl */ `
  // The game's stone: a 16 x 16 tile of close greys, mostly the base, with short horizontal
  // runs of a lighter or a darker shade (the streaks), and the odd single texel off by one.
  Surface surfaceAt(SurfaceIn s) {
    const float T = ${TEXELS.toFixed(1)};
    // The texel: the point pushed half a texel into the block, so each face owns its own texels.
    vec3 t = floor((s.rest - s.n * (0.5 / T)) * T);
    // The tile's axes on this face: across (the streaks run along it) and down.
    vec3 across = s.onTop > 0.5 ? s.travel : abs(cross(s.n, s.up));
    vec3 down = s.onTop > 0.5 ? abs(cross(s.n, s.travel)) : s.up;
    float u = dot(t, across), v = dot(t, down), w = dot(t, abs(s.n));
    // Runs: two to four texels long, each row offset so the runs never line up.
    float rowOff = floor(hash12(vec2(v, w)) * 4.0);
    float run = floor((u + rowOff) / 3.0);
    float r = hash13(vec3(run, v, w));
    float rowOff2 = floor(hash12(vec2(v + 3.0, w)) * 4.0);
    float run2 = floor((u + rowOff2) / 2.0);
    float r2 = hash13(vec3(run2 + 9.0, v, w + 1.0));
    float h = hash13(t + 5.0);
    // Shade index 0..4 about the base (2): a run lifts or drops it, a lone texel nudges it.
    float idx = 2.0;
    idx += step(0.8, r) - step(r, 0.2);
    idx += (step(0.9, r2) - step(r2, 0.1)) * step(0.5, h);
    idx += step(0.93, h) - step(h, 0.06);
    idx = clamp(idx, 0.0, 4.0);
    vec3 albedo = idx < 0.5 ? ${lin('#6a6a6a')} : idx < 1.5 ? ${lin('#737373')} : idx < 2.5 ? ${lin('#7c7c7c')} : idx < 3.5 ? ${lin('#868686')} : ${lin('#909090')};
    return Surface(albedo, vec3(0.0), 0.0, 1.0, vec3(0.0));
  }
`;

const AIR = /* glsl */ `
  // A cloud slab in one cell of the cloud grid: 1 on its top face, 2 on its underside strip.
  float slab(vec2 q, vec2 cellId, float seed, float thin) {
    vec2 f = q - cellId;                       // 0..1 within the cell
    float on = step(0.62, hash12(cellId + seed));
    float x0 = hash12(cellId + seed + 1.0) * 0.3;
    float wdt = 0.3 + hash12(cellId + seed + 2.0) * 0.6;
    float y0 = 0.2 + hash12(cellId + seed + 3.0) * 0.4;
    float hgt = (0.16 + hash12(cellId + seed + 4.0) * 0.3) * thin;
    float inX = step(x0, f.x) * step(f.x, x0 + wdt);
    float top = inX * step(y0, f.y) * step(f.y, y0 + hgt);
    float under = inX * step(y0 - 0.05 * thin, f.y) * step(f.y, y0);
    return on * max(top, 2.0 * under);
  }
  vec3 airAt(AirIn a) {
    float foot = -0.95;                                    // radii: the monument's foot (PLACE.footDepth)
    float vh = a.frag.y / max(a.uv.y, 1.0e-4);             // the frame's height, device pixels
    // The night: a smooth fall from navy at the top to indigo at the horizon; the ground
    // under the monument's foot a flat, darker band.
    float horizon = clamp(a.uv.y + (foot - a.toCentre.y) * a.radius / vh, 0.0, 1.0);   // the horizon's uv.y
    float h = clamp((a.uv.y - horizon) / max(1.0 - horizon, 0.2), 0.0, 1.0);
    vec3 c = mix(${lin('#3a4270')}, ${lin('#141a33')}, pow(h, 0.8));
    c = a.uv.y < horizon - 0.12 ? ${lin('#11152a')} : c;
    if (a.uv.y > horizon) {
      // Clouds: big flat slabs on a coarse grid, two layers, drifting slowly, pixel-snapped;
      // dark grey-blue with a darker underside, nothing inside.
      vec2 px = floor(vec2(a.uv.x * a.aspect, a.uv.y) * 90.0) / 90.0;
      vec2 q1 = (px + vec2(a.time * 0.006, 0.0)) / vec2(0.6, 0.16);
      vec2 q2 = (px + vec2(a.time * 0.004 + 0.37, 0.05)) / vec2(0.8, 0.2);
      float thin = 0.4 + 0.6 * h;                            // flatter toward the horizon
      float s1 = slab(q1, floor(q1), 1.0, thin), s2 = slab(q2, floor(q2), 7.0, thin);
      float sl = max(s1, s2);
      vec3 cloud = mix(${lin('#252b47')}, ${lin('#1a1f37')}, step(1.5, sl));
      c = mix(c, cloud, step(0.5, sl));
      // Stars: two-pixel cells, sparse, most steady, some blinking, the odd plus-shaped one.
      vec2 sg = floor(a.frag / 2.0);
      float lit = 0.0;
      for (int i = 0; i < 5; i++) {
        vec2 o = i == 0 ? vec2(0.0) : i == 1 ? vec2(1.0, 0.0) : i == 2 ? vec2(-1.0, 0.0) : i == 3 ? vec2(0.0, 1.0) : vec2(0.0, -1.0);
        vec2 g = sg + o;
        float star = step(0.9993, hash12(g * 0.731 + 0.5));
        float plus = step(0.7, hash12(g + 11.0));
        float blink = mix(1.0, step(0.4, hash12(vec2(hash12(g), floor(a.time * 1.5 + hash12(g + 3.0) * 5.0)))), step(0.6, hash12(g + 23.0)));
        lit = max(lit, star * blink * (i == 0 ? 0.5 + 0.5 * hash12(g + 9.0) : 0.35 * plus));
      }
      c = mix(c, ${lin('#eef0ff')}, lit * (1.0 - step(0.5, sl)));
      // The moon: the game's eight-by-eight sprite, a gibbous lit from the right, its dark
      // sliver to the left, two darker texels on the face; high at the left of the frame.
      float mp = 1.0 / 64.0;                                   // one moon pixel, in uv.y
      vec2 m = floor((vec2(a.uv.x * a.aspect, a.uv.y) - vec2(0.3 * a.aspect, 0.82)) / mp);
      if (m.x >= 0.0 && m.x < 8.0 && m.y >= 0.0 && m.y < 8.0) {
        vec2 d = m + 0.5 - 4.0;
        float disc = step(length(d), 3.9);
        float shadow = step(m.x + step(1.5, abs(d.y)) + step(2.5, abs(d.y)), 1.5);
        float crater = step(0.5, abs(m.x - 4.0) + abs(m.y - 2.0)) * step(0.5, abs(m.x - 5.0) + abs(m.y - 5.0));
        vec3 face = mix(${lin('#b9b9bd')}, ${lin('#e6e6e6')}, crater);
        face = mix(face, ${lin('#3b3f55')}, shadow);
        c = mix(c, face, disc);
      }
    }
    return c;
  }
`;

const LIGHT = /* glsl */ `
  vec3 lightAt(LightIn l) {
    const float T = ${TEXELS.toFixed(1)};
    const float H = 1.5;   // beams: half the quad (LANTERN.haloSize / 2)
    vec2 p = (floor(l.uv * H * T) + 0.5) / T;    // the texel's centre, beams from the light
    float tick = floor(l.time * 10.0);           // the flame flickers in steps
    float flick = 0.88 + 0.24 * hash12(vec2(tick, 7.0));
    // Light spreads a level per block, as the game counts it: part Manhattan.
    float d = mix(length(p), abs(p.x) + abs(p.y), 0.4);
    if (l.part < 0.5) {
      // The halo: light levels stepping down over the air, square texels.
      float level = floor(clamp(1.0 - d / 1.35, 0.0, 1.0) * 6.0) / 6.0;
      return uAccent * level * level * 0.55 * l.power * flick;
    }
    // The torch: a flame three texels wide, a lick on top that wanders, orange about it.
    vec2 tx = floor(l.uv * H * T);               // integer texel
    float lick = floor(hash12(vec2(tick, 3.0)) * 3.0) - 1.0;
    float flame = step(max(abs(tx.x + 0.5), abs(tx.y + 0.5)), 1.5);
    flame = max(flame, step(abs(tx.x + 0.5 - lick), 0.5) * step(abs(tx.y + 0.5 - 2.0), 0.5));
    float ring = step(max(abs(tx.x + 0.5), abs(tx.y + 0.5)), 2.5) * (1.0 - flame);
    // The stick: two texels wide, four down from the flame.
    float stick = step(abs(tx.x + 0.5), 1.0) * step(-5.5, tx.y + 0.5) * step(tx.y + 0.5, -1.5);
    float bloom = floor(clamp(1.0 - d / 0.5, 0.0, 1.0) * 4.0) / 4.0;
    vec3 core = ${disp('#fff3b0')};
    return (core * flame + uAccent * (ring * 0.95 + bloom * bloom * 0.6) + ${disp('#6b4a2a')} * stick * (1.0 - ring)) * min(l.power, 1.0) * flick
      + uAccent * max(l.power - 1.0, 0.0) * bloom;
  }
`;

const MOTE = /* glsl */ `
  vec4 moteAt(MoteIn m) {
    // A square, on or off: the game's particles.
    float on = step(max(abs(m.pc.x), abs(m.pc.y)), 0.85);
    // It blinks in steps, each mote on its own clock, and its weight is one of a few levels.
    float blink = step(0.35, hash12(vec2(floor(m.time * 3.0 + m.seed.x * 10.0), m.seed.y * 50.0)));
    float a = floor(m.alpha * blink * 16.0) / 16.0;
    // Flame particles near the torch, white specks beyond; burst motes are the dust of a block landing.
    vec3 warm = mix(uAccent, ${disp('#fff3b0')}, m.seed.z);
    vec3 c = mix(vec3(0.9), warm, m.chroma);
    c = mix(c, ${disp('#e8dcc4')}, m.kind);
    return vec4(c * a * on, 1.0);
  }
`;

export default {
  config: {
    PALETTE: {
      coreDisplay: [1.0, 0.95, 0.69],   // the flame's core, yellow-white
    },
    PLACE: {
      grain: 0.004,        // just enough to keep the sky's fall from banding
    },
    SHADING: {
      // The game's three tones: top full, one wall at 0.8, the other at 0.6 (in sRGB terms, which
      // the key below lands near in linear light: about 1.0 / 0.7 / 0.3).
      keyWrapPower: 1.6,
      key: 1.05,
      fill: 0.12,
      ambient: 0.08,
      topLight: 0.05,
      aoStrength: 0.6,     // the game's smooth lighting: a little contact shadow, no more
      grainAmount: 0,
      jointDarken: 0,
      bevelGain: 0,
      wearGain: 0,
      wearWidth: 0.002,
      lineWidthPx: 0.2,
      mottling: 0, speckle: 0, blockVariance: 0,
      mistFloor: 1.0,      // the game lights everything alike: no darkening far from the focus
      dimSelected: 0.35,
      lanternWhite: [0.2, 0.17, 0.12],
      lanternEdge: 0,
      glowRadius: 1.25,
      lightRadius: 0.1,    // the flame is three texels wide
    },
    LANTERN: {
      haloSize: 3.0,
      haloGain: 0.55,
      haloGrain: 0,
      bloom: 0.03,
      bloomGain: 0.7,
      trailSize: 0.22,
      trailGain: 0.16,
    },
    DUST: {
      ambientCount: 70,
      burstCount: 60,
      fall: [-0.008, -0.014],   // the particles rise, like a torch's smoke
      wander: 0.02,
      size: [4, 2],
      alpha: [0.12, 0.3],
      twinkle: 0,            // the motes blink in the hook instead
      depth: 12,
    },
  },
  glsl: { surface: SURFACE, air: AIR, light: LIGHT, mote: MOTE },
};
