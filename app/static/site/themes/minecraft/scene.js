// THEME: minecraft. The homepage's world as the game draws it: every block the game's own
// stone tile (16 x 16 texels, baked below), flat-shaded under the game's three face tones; a
// clean day sky; an experience orb for the light; square particles.
// A plain ES module with no imports, of the shape static/home/src/theme.js describes.

// sRGB hex to the linear light the surface and air hooks return, as a GLSL literal.
const lin = (hex) => {
  const c = [1, 3, 5].map((i) => parseInt(hex.slice(i, i + 2), 16) / 255)
    .map((v) => (v <= 0.04045 ? v / 12.92 : ((v + 0.055) / 1.055) ** 2.4));
  return `vec3(${c.map((v) => v.toFixed(4)).join(', ')})`;
};
const linf = (hex) => lin(hex).slice(5).split(',')[0];   // one channel, for a grey
// Display-space colours (the light and the motes are composited in display space).
const disp = (hex) => `vec3(${[1, 3, 5].map((i) => (parseInt(hex.slice(i, i + 2), 16) / 255).toFixed(3)).join(', ')})`;

// The game's stone texture (assets/minecraft/textures/block/stone.png, Java Edition 1.14 to
// now, "JE5"), read texel by texel with Pillow from the Minecraft Wiki's copy
// (minecraft.wiki/images/Stone_(texture)_JE5_BE3.png), identical to the file in the public
// mirrors of the vanilla assets (PrismarineJS/minecraft-assets, InventivetalentDev/
// minecraft-assets). Four greys: #686868, #747474, #7f7f7f, #8f8f8f. Each row of 16 texels is
// four bytes, each byte four texels of two bits (texel k in bits 2k..2k+1), row 0 the top.
const STONE_ROWS = [
  [255, 150, 81, 170], [154, 169, 42, 100], [6, 21, 149, 170], [250, 174, 175, 86],
  [105, 101, 254, 167], [174, 170, 22, 209], [233, 223, 87, 170], [5, 81, 90, 169],
  [191, 235, 175, 106], [186, 250, 235, 191], [152, 5, 153, 86], [170, 190, 170, 239],
  [86, 110, 41, 68], [111, 105, 165, 213], [150, 170, 170, 255], [170, 90, 190, 166],
];
const STONE_PALETTE = ['#686868', '#747474', '#7f7f7f', '#8f8f8f'];
const rowSelect = STONE_ROWS.map((r, i) => `r = y == ${i}.0 ? vec4(${r.map((b) => b.toFixed(1)).join(', ')}) : r;`).join('\n    ');

const SURFACE = /* glsl */ `
  // The tile's texel at column x, row y (0..15 each): its shade index 0..3.
  float stoneIndex(float x, float y) {
    vec4 r = vec4(0.0);
    ${rowSelect}
    float grp = floor(x / 4.0);
    float byte = dot(r, vec4(equal(vec4(0.0, 1.0, 2.0, 3.0), vec4(grp))));
    return mod(floor(byte / pow(4.0, x - grp * 4.0)), 4.0);
  }
  Surface surfaceAt(SurfaceIn s) {
    const float T = 16.0;   // one block, one tile
    // The texel: the point pushed half a texel into the block, so each face owns its own texels.
    vec3 q = s.rest - s.n * (0.5 / T);
    vec3 t = floor(q * T);
    // The tile's axes on this face: across, and down from the top edge (the walls hang from the
    // tread; the tread's tile is turned a quarter turn or more per block, as the game turns its
    // stone at random).
    vec3 across = s.onTop > 0.5 ? s.travel : abs(cross(s.n, s.up));
    vec3 down = s.onTop > 0.5 ? abs(cross(s.n, s.travel)) : s.up;
    float u = mod(dot(t, across), T);
    float v = s.onTop > 0.5 ? mod(dot(t, down), T) : floor(s.fromTop * T);
    if (s.onTop > 0.5) {
      float turn = floor(hash13(floor(q * vec3(1.0) * abs(s.travel)) + 3.0) * 4.0);   // per block along the side
      vec2 uv = turn < 0.5 ? vec2(u, v) : turn < 1.5 ? vec2(15.0 - v, u) : turn < 2.5 ? vec2(15.0 - u, 15.0 - v) : vec2(v, 15.0 - u);
      u = uv.x; v = uv.y;
    }
    float idx = stoneIndex(clamp(u, 0.0, 15.0), clamp(v, 0.0, 15.0));
    float grey = dot(vec4(${STONE_PALETTE.map(linf).join(', ')}), vec4(equal(vec4(0.0, 1.0, 2.0, 3.0), vec4(idx))));
    return Surface(vec3(grey), vec3(0.0), 0.0, 1.0, vec3(0.0));
  }
`;

const AIR = /* glsl */ `
  vec3 airAt(AirIn a) {
    // The game's day: one blue, with its fog's haze blending in toward the horizon (the
    // monument's foot), and the same haze on below it.
    float vh = a.frag.y / max(a.uv.y, 1.0e-4);                               // the frame's height, device pixels
    float horizon = clamp(a.uv.y + (-0.95 - a.toCentre.y) * a.radius / vh, 0.05, 0.6);   // its uv.y (PLACE.footDepth)
    float h = smoothstep(horizon, horizon + 0.42, a.uv.y);
    return mix(${lin('#a9c8ff')}, ${lin('#78a7ff')}, h);
  }
`;

const LIGHT = /* glsl */ `
  // The experience orb: a round sprite of eight texels, its colour swirling between the game's
  // lime and yellow, a lighter core, a darker rim, bobbing a texel or two; and the glow it
  // casts on the air (part 0), under the stone.
  const float TX = 0.036;   // beams per texel of the orb (its diameter 8 texels, 0.29 beams)
  const float H = 1.0;      // beams: half the quad (LANTERN.haloSize / 2)
  vec2 orbTexel(LightIn l) {
    float bob = floor(sin(l.time * 2.4) * 1.5 + 0.5);                        // texels up and down
    return floor(l.uv * H / TX) - vec2(0.0, bob) + 0.5;                       // the texel's centre
  }
  float lightCover(LightIn l) {
    vec2 m = orbTexel(l);
    if (l.part < 0.5) {
      float r2 = dot(l.uv * H, l.uv * H);
      return exp(-r2 / 0.11) * 0.55 * min(l.power, 1.5);
    }
    return step(length(m), 4.0) * min(l.power, 1.0);
  }
  vec3 lightAt(LightIn l) {
    float cover = lightCover(l);
    if (l.part < 0.5) return ${disp('#9dff3c')} * cover;
    vec2 m = orbTexel(l);
    float d = length(m);
    // The swirl: a slow cycle, each texel a little ahead or behind its neighbours.
    float phase = l.time * 2.2 + (m.x - m.y) * 0.45 + hash12(m) * 0.8;
    vec3 c = mix(${disp('#7fff00')}, ${disp('#fff52a')}, smoothstep(-0.1, 1.0, sin(phase)));   // mostly lime, yellow passing through
    c = mix(c, ${disp('#f6ffd0')}, 0.55 * (1.0 - step(1.6, d)));              // the core
    c *= 1.0 - 0.22 * step(3.1, d);                                           // the rim
    return c * cover;
  }
`;

const MOTE = /* glsl */ `
  vec4 moteAt(MoteIn m) {
    // A square, on or off: the game's particles.
    float on = step(max(abs(m.pc.x), abs(m.pc.y)), 0.85);
    // It blinks in steps, each mote on its own clock, and its weight is one of a few levels.
    float blink = step(0.35, hash12(vec2(floor(m.time * 3.0 + m.seed.x * 10.0), m.seed.y * 50.0)));
    float a = floor(m.alpha * blink * 16.0) / 16.0;
    // Lime near the orb, white specks beyond; burst motes are the dust of a block landing.
    vec3 c = mix(vec3(0.95), mix(uAccent, ${disp('#f6ffd0')}, m.seed.z), m.chroma);
    c = mix(c, ${disp('#e8dcc4')}, m.kind);
    return vec4(c * a * on, 1.0);
  }
`;

export default {
  config: {
    PLACE: {
      grain: 0.003,        // just enough to keep the sky's fall from banding
    },
    SHADING: {
      // The game's three tones, top 1.0 and the walls 0.8 and 0.6 (sRGB), as the reference
      // render of a stone block shows: in linear light 1.0 / 0.61 / 0.325 (y / z / x), which
      // these land on (0.98 / 0.61 / 0.32). No screen-fixed light: the game has none.
      keyWrapPower: 3.5,
      fillWrapPower: 1.0,
      key: 1.0,
      fill: 0.15,
      ambient: 0.2,
      topLight: 0,
      aoStrength: 0.5,     // the game's smooth lighting: a little contact shadow, no more
      grainAmount: 0,
      jointDarken: 0,
      bevelGain: 0,
      wearGain: 0,
      wearWidth: 0.002,
      lineWidthPx: 0.2,
      mistFloor: 1.0,      // the game lights everything alike: no darkening far from the focus
      dimSelected: 0.3,
      lanternWhite: [0.14, 0.17, 0.12],   // a faces the orb does not hold takes a faint lime-white
      lanternEdge: 0,
      glowRadius: 1.25,
      lightRadius: 0.14,   // the orb's radius, beams
    },
    LANTERN: {
      blend: 'over',       // the orb is a solid thing on the bright sky (src/theme.js)
      haloSize: 2.0,
      trailSize: 0.2,
      trailGain: 0.12,
    },
    DUST: {
      ambientCount: 60,
      burstCount: 60,
      fall: [-0.008, -0.014],   // the particles rise
      wander: 0.02,
      size: [4, 2],
      alpha: [0.12, 0.3],
      twinkle: 0,               // the motes blink in the hook instead
      depth: 12,
    },
  },
  glsl: { surface: SURFACE, air: AIR, light: LIGHT, mote: MOTE },
};
