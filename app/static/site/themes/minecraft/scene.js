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
  // One of four shades, by a number 0..1: no smoothing between texels.
  vec3 shade4(vec3 a, vec3 b, vec3 c, vec3 d, float v) {
    return v < 0.25 ? a : v < 0.5 ? b : v < 0.75 ? c : d;
  }
  vec3 grassTop(float h, float coarse) {
    float v = clamp(0.5 + (h - 0.5) * 0.9 + (coarse - 0.5) * 0.5, 0.0, 0.999);
    return shade4(${lin('#67a548')}, ${lin('#70b150')}, ${lin('#79bd59')}, ${lin('#80c35f')}, v);
  }
  vec3 dirt(float h, float coarse) {
    float v = clamp(0.5 + (h - 0.5) * 0.8 + (coarse - 0.5) * 0.5, 0.0, 0.999);
    return shade4(${lin('#5f4229')}, ${lin('#79553a')}, ${lin('#7f5a3e')}, ${lin('#92694a')}, v);
  }
  vec3 stone(float h, float coarse) {
    float v = clamp(0.5 + (h - 0.5) * 0.7 + (coarse - 0.5) * 0.9, 0.0, 0.999);
    return shade4(${lin('#6b6b6b')}, ${lin('#767676')}, ${lin('#7f7f7f')}, ${lin('#8a8a8a')}, v);
  }
  Surface surfaceAt(SurfaceIn s) {
    const float T = ${TEXELS.toFixed(1)};
    // The texel: the point pushed half a texel into the block, so each face owns its own row of
    // texels and no face sits on a texel boundary.
    vec3 q = s.rest - s.n * (0.5 / T);
    vec3 t = floor(q * T);
    float h = hash13(t);                              // this texel's own number
    float h2 = hash13(t + 71.0);
    float coarse = hash13(floor(q * (T / 4.0)) + 13.0);   // 4 x 4 texel patches: the blotches of stone and dirt
    float cluster = hash13(floor(q * (T / 3.0)) + 29.0);  // 3 x 3: where ore gathers
    float row = floor(s.fromTop * T);                     // texel rows down from the block's top edge
    vec3 albedo;
    if (s.isStep > 0.5) {
      // A grass block: grass on the tread, dirt on the walls under a ragged band of grass.
      vec3 grass = grassTop(h, coarse);
      if (s.onTop > 0.5) {
        albedo = grass;
      } else {
        float hang = step(row, 2.0) + step(row, 3.0) * step(0.5, h2) + step(row, 4.0) * step(0.82, h2);
        albedo = mix(dirt(h, coarse), grass * 0.9, min(hang, 1.0));
      }
    } else {
      float kind = hash13(vec3(s.block, 3.0, 9.0));
      if (kind < 0.62) {
        albedo = stone(h, coarse);
      } else if (kind < 0.8) {
        albedo = dirt(h, coarse);
      } else if (kind < 0.91) {
        // Coal ore: dark specks gathered in a few patches of the stone.
        float ore = step(0.72, cluster) * step(0.3, h2);
        albedo = mix(stone(h, coarse), shade4(${lin('#262626')}, ${lin('#2e2e2e')}, ${lin('#363636')}, ${lin('#3e3e3e')}, h), ore);
      } else {
        // Iron ore: the same, in beige.
        float ore = step(0.74, cluster) * step(0.35, h2);
        albedo = mix(stone(h, coarse), shade4(${lin('#c4a07a')}, ${lin('#d8af93')}, ${lin('#e0bc9f')}, ${lin('#d1a888')}, h), ore);
      }
    }
    return Surface(albedo, vec3(0.0), 0.0, 1.0, vec3(0.0));
  }
`;

const AIR = /* glsl */ `
  // 1 below the edge b, 0 above it, a checkerboard over the w above it.
  float bandBelow(float y, float b, float w, float checker) {
    return y < b ? 1.0 : (y < b + w ? checker : 0.0);
  }
  vec3 airAt(AirIn a) {
    // The frame in pixels: square cells, 1/80 of the height; everything is decided per cell.
    float cell = 1.0 / 80.0;
    vec2 p = vec2(a.uv.x * a.aspect, a.uv.y);
    vec2 g = floor(p / cell);
    vec2 pc = (g + 0.5) * cell;                            // the cell's centre, same units
    // The cell's centre relative to the monument, in its radii.
    float vh = a.frag.y / max(a.uv.y, 1.0e-4);             // the frame's height, device pixels
    vec2 cr = a.toCentre + (pc - p) * vh / a.radius;
    float foot = -0.95;                                    // radii: the monument's foot (PLACE.footDepth)
    // The night sky: near-black above, bluer toward the horizon in flat bands, each edge a
    // checkerboard dither two cells deep (the old way to blend two colours); the fog at the
    // monument's foot, the dark plain beyond it.
    float checker = mod(g.x + g.y, 2.0);
    vec3 c = ${lin('#05081a')};
    c = mix(c, ${lin('#080d26')}, bandBelow(cr.y, foot + 1.6, 0.12, checker));
    c = mix(c, ${lin('#0c1434')}, bandBelow(cr.y, foot + 0.8, 0.12, checker));
    c = mix(c, ${lin('#131f4a')}, bandBelow(cr.y, foot + 0.3, 0.1, checker));
    c = mix(c, ${lin('#1a2a5c')}, bandBelow(cr.y, foot + 0.02, 0.06, checker));
    c = mix(c, ${lin('#0b1512')}, bandBelow(cr.y, foot - 0.3, 0.06, checker));
    if (cr.y > foot + 0.02) {
      // Stars: half a cell each, a few of them, blinking in steps.
      vec2 sg = floor(p / (cell * 0.5));
      float star = step(0.9965, hash12(sg + 0.5));
      float blink = step(0.3, hash12(vec2(hash12(sg), floor(a.time * 2.0 + hash12(sg + 3.0) * 7.0))));
      c = mix(c, ${lin('#dfe4ff')}, star * blink * (0.35 + 0.5 * hash12(sg + 9.0)));
      // Clouds: blocks of dim grey drifting one cell at a time, a darker underside; up high.
      if (cr.y > foot + 1.3) {
        float drift = floor(a.time * 1.5);
        vec2 cg = (g + vec2(drift, 0.0)) / vec2(14.0, 6.0);
        float n = vnoise(cg) * 0.7 + vnoise(cg * 2.3 + 5.0) * 0.3;
        float nUnder = vnoise(cg - vec2(0.0, 1.0 / 6.0)) * 0.7 + vnoise((cg - vec2(0.0, 1.0 / 6.0)) * 2.3 + 5.0) * 0.3;
        float cloud = step(0.62, n);
        float underside = cloud * (1.0 - step(0.62, nUnder));
        c = mix(c, mix(${lin('#2a3352')}, ${lin('#1c243d')}, underside), cloud);
      }
      // The moon: an eight-by-eight sprite of single cells, high at the left, its corners cut,
      // a few darker seas, its right edge in shadow. Over the clouds, so it is always seen.
      vec2 m = floor((p - vec2(0.3 * a.aspect, 0.86)) / cell);
      if (m.x >= 0.0 && m.x < 8.0 && m.y >= 0.0 && m.y < 8.0) {
        float corner = step(6.0, abs(m.x - 3.5) + abs(m.y - 3.5));
        float sea = step(0.7, hash12(m + 17.0)) + step(6.5, m.x);
        vec3 face = mix(${lin('#e8e8dc')}, ${lin('#a9a9a0')}, min(sea, 1.0));
        c = mix(c, face, 1.0 - corner);
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
      grain: 0,            // no dither: the sky is flat by design
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
