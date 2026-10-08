// THE THEME CONTRACT for the homepage's world. The site's look is tokens (static/site/tokens.css);
// a theme is a folder, static/site/themes/<name>/, whose theme.css overrides them. The scene
// renders its own world (stone, air, light, dust) in shaders, which no stylesheet reaches, so a
// theme that changes the world adds a scene.js beside its theme.css, a plain ES module with no
// imports, exporting an object of this shape (every part optional):
//
//   export default {
//     config: { PALETTE: {…}, PLACE: {…}, SHADING: {…}, MOTION: {…}, LANTERN: {…}, DUST: {…}, … },
//     glsl: { surface: `…`, air: `…`, light: `…`, mote: `…` },
//   };
//
// `config` is laid over src/config.js before the scene is built (deep-merged; arrays, such as a
// colour, are replaced whole), so a theme tunes the key light, the mist, the halo or the motes by
// name, and never has to rewrite a shader to do it. `glsl` holds the four looks a theme can
// draw itself, one shader chunk each, every one defining a function the scene's shaders call:
//
//   surface  Surface surfaceAt(SurfaceIn s)   the blocks' material (src/monument.js)
//   air      vec3 airAt(AirIn a)              the air behind everything (src/backdrop.js)
//   light    vec3 lightAt(LightIn l)          the light itself as drawn (src/lantern.js)
//   mote     vec4 moteAt(MoteIn m)            one mote of dust (src/dust.js)
//
// The structs are declared below (THEME_GLSL) and prepended to every chunk, with the helpers of
// src/glsl.js (toSRGB, hash12, grain) and the noise functions here (hash13, valueNoise, vnoise).
// A chunk may define its own helper functions before the one the contract names. The defaults
// below ARE the scene's own world (void), and the reference for what each hook must deliver.
//
// What a theme must keep, so the paradox still reads and the interface still works:
//   * The paradox rule. Nothing in a surface may depend on distance along the view: a block's
//     look is a function of the block itself (rest position, face, index, time), the air of
//     screen position and time only. No fog, no cast shadows.
//   * Three tones. The three visible face families (+x, +y, +z) must stay told apart at every
//     roll: keep the key fixed to the stone (SHADING.keyDir) and let the material modulate it;
//     a material that flattens the families turns the monument into a silhouette.
//   * One light. The light is what the visitor is: PALETTE.accent* (from --accent in theme.css)
//     is its colour, and it is the only thing in the world that reads as a colour against the
//     material. A warm material should keep its accent clearly apart from it.
//   * The DOM is the theme's too: --world-* in theme.css are what the interface is drawn in over
//     this world, so a bright air needs dark --world-ink and so on; nothing here styles the DOM.
//   * Linear light in, display in the hooks that say so: surfaceAt and airAt return linear light
//     (the frame is graded once, by toSRGB); lightAt and moteAt return display-space colour,
//     composited additively (the light screened, a mote added).
//
// Loading: src/main.js calls loadTheme() before importing the scene. The module's URL is the
// page's <html data-scene> (templates/home.html, from app/design.py); the standalone demo
// (design/homepage-demo) derives it from ?theme=<name>. A theme that fails to load or evaluate
// is logged and ignored: the scene keeps its own world rather than breaking.
import * as CONFIG from './config.js';

export const THEME = {
  name: 'void',
  glsl: { surface: '', air: '', light: '', mote: '' },
};

// ---------------------------------------------------------------- the shared GLSL
// Declared before every hook: the structs the hooks take and give, and noise for materials.
export const THEME_GLSL = /* glsl */ `
  float hash13(vec3 p) {
    p = fract(p * 0.1031);
    p += dot(p, p.zyx + 31.32);
    return fract((p.x + p.y) * p.z);
  }
  // Smooth value noise, 0..1, cells one unit wide.
  float valueNoise(vec3 p) {
    vec3 i = floor(p), f = fract(p);
    f = f * f * (3.0 - 2.0 * f);
    return mix(
      mix(mix(hash13(i), hash13(i + vec3(1, 0, 0)), f.x), mix(hash13(i + vec3(0, 1, 0)), hash13(i + vec3(1, 1, 0)), f.x), f.y),
      mix(mix(hash13(i + vec3(0, 0, 1)), hash13(i + vec3(1, 0, 1)), f.x), mix(hash13(i + vec3(0, 1, 1)), hash13(i + vec3(1, 1, 1)), f.x), f.y),
      f.z);
  }
  float vnoise(vec2 p) {
    vec2 i = floor(p), f = fract(p);
    f = f * f * (3.0 - 2.0 * f);
    return mix(mix(hash12(i), hash12(i + vec2(1, 0)), f.x), mix(hash12(i + vec2(0, 1)), hash12(i + vec2(1, 1)), f.x), f.y);
  }

  // A point of a block's surface, as the material sees it. Structure space: the blocks' own
  // axes, before any roll or tilt; one beam is the block's cross-section.
  struct SurfaceIn {
    vec3 rest;      // the point in the block's rest coordinates (lift removed): texture sticks to the block
    vec3 box;       // the point relative to the block's centre
    vec3 ext;       // the block's half extents (a step is one beam square and longer along its travel)
    vec3 n;         // the face's normal, unit, axis-aligned (only +x, +y, +z faces are ever seen)
    vec3 edge;      // distance to the block's edges along each axis (very large along n's own axis)
    vec3 travel;    // the unit axis the block's side runs along (the loop's direction here)
    vec3 up;        // the unit axis of the block's tread (its top; the light hovers above it)
    float onTop;    // 1 on the block's top face, 0 on its two walls
    float block;    // the block's index round the loop: each block its own piece
    float isStep;   // 1 on a step (one per work), 0 on a plain block of a side
    float time;     // seconds
  };
  // What the material gives back, in linear light.
  struct Surface {
    vec3 albedo;    // the colour of the stuff (0..1 per channel; the void's stone is vec3(0.78))
    vec3 bump;      // a nudge to the face normal, structure space, tangent to the face (vec3(0): flat)
    float gloss;    // the specular highlight's strength (0: matte stone; 0.2: a sheen; 1: wet)
    float shine;    // its exponent (8: broad; 60: tight). Ignored while gloss is 0.
    vec3 emit;      // light the surface gives off of itself (vec3(0): none)
  };

  // A point of the air (the full-screen pass behind everything). Screen x, y and time only.
  struct AirIn {
    vec2 uv;        // 0..1 across the frame, y up
    vec2 frag;      // device pixels
    float aspect;   // width / height
    vec2 toCentre;  // this pixel from the monument's centre, in monument radii (y up)
    float radius;   // the monument's bounding radius, device pixels
    float below;    // 0..1: how far under the monument's foot this pixel lies (where ground mist pools)
    float across;   // 0..1: how near the monument's column this pixel lies, sideways
    float n;        // the drifting mist noise, 0..1 (PLACE.noiseScale cells, PLACE.drift)
    float time;     // seconds
  };

  // A point of the light's quad. The light is drawn in two passes: part 0 (the halo) under the
  // stone, part 1 (the core and bloom) over everything. Both screened: never past white.
  struct LightIn {
    float r;        // beams from the light's centre
    vec2 uv;        // -1..1 across the quad
    vec2 frag;      // device pixels
    float power;    // the light's power now (0 before it is struck, 1 at full, more in a flare)
    float part;     // 0 or 1, as above
    float time;     // seconds
  };

  // A point of one mote's point sprite.
  struct MoteIn {
    vec2 pc;        // -1..1 across the sprite
    float alpha;    // the mote's weight now (its twinkle, its fade in and out)
    float warm;     // how much of the light reaches it (0 far away)
    float chroma;   // 1 within the light's reach, where a mote carries its hue; 0 beyond
    vec4 seed;      // the mote's own four random numbers, 0..1
    float kind;     // 0 an ambient mote, 1 a burst mote (thrown when something lands)
    float time;     // seconds
  };
`;

// ---------------------------------------------------------------- the void: the scene's own world
// The default of each hook, reproducing exactly what the scene drew before themes existed.

/** The stone: neutral, mottled, speckled, each block its own piece (PALETTE, SHADING). */
export const VOID_SURFACE = () => /* glsl */ `
  Surface surfaceAt(SurfaceIn s) {
    float mottle = valueNoise(s.rest * 1.7) * 0.6 + valueNoise(s.rest * 6.3 + 11.0) * 0.3 + valueNoise(s.rest * 23.0) * 0.1;
    float speckle = hash13(floor(s.rest * 90.0)) - 0.5;
    float quarry = hash13(vec3(s.block, 7.0, 3.0)) - 0.5;
    float albedo = ${CONFIG.PALETTE.stoneAlbedo.toFixed(3)} * (1.0 + (mottle - 0.5) * ${(CONFIG.SHADING.mottling * 2).toFixed(3)} + speckle * ${(CONFIG.SHADING.speckle * 2).toFixed(3)} + quarry * ${(CONFIG.SHADING.blockVariance * 2).toFixed(3)});
    return Surface(vec3(albedo), vec3(0.0), 0.0, 1.0, vec3(0.0));
  }
`;

/** The air of a hall too large to see: near-black above, charcoal and mist below (PLACE). */
export const VOID_AIR = () => {
  const P = CONFIG.PLACE, f = (v) => v.toFixed(5);
  return /* glsl */ `
  vec3 airAt(AirIn a) {
    // The air: a vertical ramp the mist wanders across.
    float h = smoothstep(-0.05, 1.05, a.uv.y + (a.n - 0.5) * ${f(P.rampDrift)});
    float tone = mix(${f(P.airLift)}, ${f(P.airDeep)}, h);
    // A pocket of lifted air behind the monument, and the mist that pools under it.
    tone += ${f(P.pocket)} * exp(-dot(a.toCentre, a.toCentre) / ${f(P.pocketReach * P.pocketReach)});
    tone += ${f(P.mist)} * a.below * a.across * (0.45 + 1.1 * a.n);
    // The corners fall away.
    float v = length((a.uv - 0.5) * vec2(1.0, 1.15));
    tone *= 1.0 - ${f(P.vignette)} * smoothstep(0.35, 0.95, v);
    return vec3(tone);
  }
`;
};

/** The light: a halo of lit air, a bloom in the eye, a core that burns to white (LANTERN, PALETTE). */
export const VOID_LIGHT = () => {
  const L = CONFIG.LANTERN, R = CONFIG.SHADING.lightRadius, core = CONFIG.PALETTE.coreDisplay.map((c) => c.toFixed(3)).join(', ');
  return /* glsl */ `
  vec3 lightAt(LightIn l) {
    float edge = smoothstep(${(L.haloSize / 2).toFixed(3)}, ${(L.haloSize / 2 * 0.55).toFixed(3)}, l.r);
    float halo = 0.055 / (l.r * l.r + 0.055) * edge;
    float bloom = exp(-l.r * l.r / ${L.bloom.toFixed(3)});
    float core = smoothstep(${(R * 1.25).toFixed(4)}, ${(R * 0.55).toFixed(4)}, l.r);
    // In display space: halo and bloom carry the hue, the core burns to white.
    return l.part < 0.5
      ? uAccent * halo * ${L.haloGain.toFixed(3)} * l.power + grain(l.frag, l.time, ${L.haloGrain.toFixed(4)}) * step(0.004, halo)
      : uAccent * bloom * ${L.bloomGain.toFixed(3)} * l.power + vec3(${core}) * core * min(l.power, 1.0);
  }
`;
};

/** A mote: a soft neutral point that carries the light's hue within its reach. */
export const VOID_MOTE = () => /* glsl */ `
  vec4 moteAt(MoteIn m) {
    float d = length(m.pc);
    float a = smoothstep(1.0, 0.2, d) * m.alpha;
    // Motes are neutral; near the light they carry its light, nothing else.
    vec3 tint = mix(vec3(dot(uAccent, vec3(0.2126, 0.7152, 0.0722))), uAccent, m.chroma);
    vec3 c = vec3(0.75) + tint * m.warm * 2.5;
    return vec4(c * a, 1.0);
  }
`;

/** The chunk a shader includes: the shared declarations, then the theme's hook or the void's. */
export function hook(name, fallback) {
  return THEME_GLSL + '\n' + (THEME.glsl[name] || fallback());
}

// ---------------------------------------------------------------- loading
const isPlain = (v) => v !== null && typeof v === 'object' && !Array.isArray(v);

/** Lays `over` onto `base` in place: plain objects recurse, anything else (arrays included) replaces. */
export function merge(base, over) {
  for (const key of Object.keys(over)) {
    if (isPlain(base[key]) && isPlain(over[key])) merge(base[key], over[key]);
    else base[key] = over[key];
  }
  return base;
}

/** The theme module's URL for this page: the server's, or the demo's from ?theme=<name>. */
export function themeUrl() {
  const root = document.documentElement;
  if (root.dataset.scene) return root.dataset.scene;
  if (root.dataset.theme) return '';   // the server named the theme and gave it no scene: the void's world
  const name = new URLSearchParams(location.search).get('theme') || '';
  return /^[a-z0-9-]+$/.test(name) && name !== 'void' ? new URL(`../site/themes/${name}/scene.js`, import.meta.url).href : '';
}

/** Applies a loaded theme object: its config over src/config.js, its chunks into THEME.glsl. */
export function applyTheme(theme, name = 'theme') {
  if (!isPlain(theme)) throw new TypeError('a theme is an object');
  const config = theme.config || {};
  for (const key of Object.keys(config)) {
    if (!isPlain(CONFIG[key])) throw new Error(`unknown config object ${key}`);
    if (!isPlain(config[key])) throw new Error(`config.${key} must be an object`);
    merge(CONFIG[key], config[key]);
  }
  const glsl = theme.glsl || {};
  for (const key of Object.keys(glsl)) {
    if (!(key in THEME.glsl)) throw new Error(`unknown shader hook ${key}`);
    if (typeof glsl[key] !== 'string') throw new Error(`glsl.${key} must be a string`);
    THEME.glsl[key] = glsl[key];
  }
  THEME.name = name;
  return THEME;
}

/** Loads the page's theme, if it has a scene module; resolves either way. */
export async function loadTheme() {
  const url = themeUrl();
  if (!url) return THEME;
  try {
    const mod = await import(url);
    const name = document.documentElement.dataset.theme || new URLSearchParams(location.search).get('theme') || 'theme';
    return applyTheme(mod.default ?? mod.theme, name);
  } catch (err) {
    console.warn(`theme ${url} could not be loaded; the scene keeps its own world`, err);
    return THEME;
  }
}
