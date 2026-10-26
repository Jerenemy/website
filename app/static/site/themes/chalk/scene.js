// THEME: chalk. The void's world inverted: the blocks are pale chalk, matte, their free arrises
// drawn darker instead of catching the light; the air a white hall, falling to grey where the
// mist pools under the monument; the light a vermilion bead drawn over the frame (on white a
// screened glow would vanish); the dust faint grey. A plain module (no imports) of the shape
// static/home/src/theme.js describes: `config` over src/config.js, `glsl` the hooks.

const AIR = /* glsl */ `
  vec3 airAt(AirIn a) {
    // The void's ramp turned over: white above, a soft grey below, the mist wandering across.
    float h = smoothstep(-0.05, 1.05, a.uv.y + (a.n - 0.5) * 0.22);
    float tone = mix(0.66, 0.86, h);
    // The mist that pools under the monument, here a shade, not a glow.
    tone -= 0.07 * a.below * a.across * (0.45 + 1.1 * a.n);
    // The corners fall away, a little.
    float v = length((a.uv - 0.5) * vec2(1.0, 1.15));
    tone *= 1.0 - 0.1 * smoothstep(0.35, 0.95, v);
    return vec3(tone);
  }
`;

const LIGHT = /* glsl */ `
  // A bead of vermilion: an opaque core, lit a little on its upper side (part 1, over everything), and a
  // soft tinted shadow of light on the air under the stone (part 0).
  float lightCover(LightIn l) {
    if (l.part < 0.5) return exp(-l.r * l.r / 0.12) * 0.35 * min(l.power, 1.5);
    float core = smoothstep(0.075, 0.05, l.r);
    float bloom = exp(-l.r * l.r / 0.01) * 0.5;
    return max(core, bloom) * min(l.power, 1.0);
  }
  vec3 lightAt(LightIn l) {
    float cover = lightCover(l);
    if (l.part < 0.5) return uAccent * cover;
    // beams across the quad: LANTERN.haloSize / 2 = 1.2
    float lit = smoothstep(0.06, 0.0, length(l.uv * 1.2 - vec2(-0.02, 0.025)));
    vec3 c = mix(uAccent, vec3(1.0, 0.6, 0.45), lit * 0.45);
    return c * cover;
  }
`;

const MOTE = /* glsl */ `
  vec4 moteAt(MoteIn m) {
    // The motes are added to the frame, so on white they can only show near the light, in its hue.
    float a = smoothstep(1.0, 0.2, length(m.pc)) * m.alpha;
    return vec4(uAccent * m.warm * m.chroma * 2.0 * a, 1.0);
  }
`;

export default {
  config: {
    PALETTE: {
      stoneAlbedo: 0.86,
    },
    PLACE: {
      grain: 0.006,
    },
    SHADING: {
      ambient: 0.16,          // a white hall: the shadow faces are grey, never black...
      key: 0.82,
      fill: 0.22,
      keyWrapPower: 2.6,      // ...but the three tones stay apart
      topLight: 0.06,
      bevelGain: -0.35,       // the free arrises are drawn in, like chalk lines on a drawing
      wearGain: -0.05,
      jointDarken: 0.6,
      mottling: 0.06,
      speckle: 0.02,
      blockVariance: 0.03,
      mistFloor: 1.0,         // nothing fades to dark far from the focus
      lanternWhite: [0.1, 0.08, 0.07],
      heldKeep: 0.75,         // a held face is the stone's grey with the red over it: the hall is white, so
                              // the far end of the face stays pale, never black
    },
    LANTERN: {
      blend: 'over',
      haloSize: 2.4,
      trailSize: 0.22,
      trailGain: 0.14,
    },
    DUST: {
      ambientCount: 80,
      alpha: [0.05, 0.15],
    },
  },
  glsl: { air: AIR, light: LIGHT, mote: MOTE },
};
