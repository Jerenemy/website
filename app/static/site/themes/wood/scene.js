// THEME: wood. The monument is a child's set of wooden blocks, decades old: cherry, hand-cut from
// different boards, the edges rounded unevenly by hand and by years, dented, chipped at a corner
// here and there, the grain grimed and the high spots polished by fingers. The air is a playroom in the afternoon: cream above, honey below, slow light on the wall.
// The light is a small candle; the dust is sunlit. The contract is static/home/src/theme.js.
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
      ambient: 0.075,
      fill: 0.27,
      topLight: 0.08,
      aoStrength: 0.7,
      // The far side of the monument sits in the same bright room, only a little quieter.
      mistFloor: 0.62,
      dimSelected: 0.3,
      // What the candle adds to a face it does not hold: a warm white, per unit of its red.
      lanternWhite: [0.2, 0.15, 0.09],
      lanternEdge: 0.15,
    },
    LANTERN: {
      // The candle is drawn by the light hook below; these size its quad and its comet.
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
    // ------------------------------------------------------------ the blocks: old cherry, hand-cut
    surface: /* glsl */ `
      // A board's grain on a face: cherry's fine, nearly straight late-wood lines across the
      // grain (bunching and spreading a little), broken here and there; a fine fibre between.
      float plank(vec3 p, vec3 along, vec3 cross_, vec3 nAxis) {
        float u = dot(p, cross_) + 0.37 * dot(p, nAxis);   // across the grain (the face's own offset in)
        float spread = valueNoise(p * (along * 0.5 + cross_ * 1.4) + 3.0) - 0.5;
        float wander = valueNoise(p * (along * 0.8 + cross_ * 3.2) + 11.0) - 0.5;
        float jitter = valueNoise(p * (along * 9.0 + cross_ * 14.0) + 17.0) - 0.5;
        float phase = u * 8.0 + spread * 2.6 + wander * 0.9 + jitter * 0.15;
        float line = pow(0.5 + 0.5 * sin(6.2832 * phase), 4.0);
        float broken = 0.5 + 0.5 * valueNoise(p * (along * 2.0 + cross_ * 30.0) + 7.0);
        return line * broken;
      }
      // A dent pressed into a face: sparse low bumps (the gradient of this bends the normal).
      float dents(vec3 q) {
        return smoothstep(0.76, 0.9, valueNoise(q * 4.0 + 50.0));
      }
      Surface surfaceAt(SurfaceIn s) {
        vec3 along = abs(s.travel);                         // the grain runs along the block
        vec3 nAxis = abs(s.n);
        vec3 cross_ = clamp(vec3(1.0) - along - nAxis, 0.0, 1.0);   // across the grain, on this face
        float endGrain = dot(along, nAxis);                 // 1 on a face cut across the grain

        // Each block is cut from its own board: its own offset into it, tone, cast and age.
        float piece = hash13(vec3(s.block * 3.17, 1.0, 5.0));
        float tint = hash13(vec3(s.block * 1.31, 9.0, 2.0)) - 0.5;
        float hue = hash13(vec3(s.block * 0.77, 4.0, 8.0)) - 0.5;
        float age = hash13(vec3(s.block * 2.09, 6.0, 1.0));
        vec3 p = s.rest + vec3(piece * 41.0, piece * 17.0, piece * 29.0);

        // --- the wood -------------------------------------------------------------------------
        float lines = plank(p, along, cross_, nAxis);
        float fibre = valueNoise(p * (along * 6.0 + cross_ * 80.0 + nAxis * 80.0) + 5.0);
        float figure = valueNoise(p * (along * 0.6 + cross_ * 1.6 + nAxis * 1.6) + 31.0);
        // A streak of pale sapwood down some boards; the small dark gum streaks cherry has.
        float sap = smoothstep(0.6, 0.78, valueNoise(p * (along * 0.35 + cross_ * 2.2 + nAxis * 2.2) + 77.0)) * step(0.55, piece);
        float gum = smoothstep(0.82, 0.9, valueNoise(p * (along * 1.5 + cross_ * 60.0 + nAxis * 60.0) + 41.0));
        // On the ends, the rings round an off-centre pith.
        vec3 acrossAll = vec3(1.0) - along;
        vec3 c = s.box * acrossAll + (vec3(0.18, -0.12, 0.22) + piece * 0.3) * acrossAll;
        float r = length(c) * 7.0 + (valueNoise(p * 3.0 + 23.0) - 0.5) * 1.4;
        float rings = pow(0.5 + 0.5 * sin(6.2832 * r), 3.0);
        float grain = mix(lines, rings * 0.8, endGrain);

        // Cherry, decades old, in linear light: a warm red-brown, the late wood darker.
        vec3 heart = vec3(0.42, 0.145, 0.055);
        vec3 late = vec3(0.17, 0.052, 0.02);
        vec3 sapCol = vec3(0.64, 0.38, 0.21);
        vec3 albedo = mix(heart, late, 0.08 + grain * 0.26 + (figure - 0.5) * 0.24 + (fibre - 0.5) * 0.08);
        albedo = mix(albedo, sapCol, sap * 0.5);
        albedo = mix(albedo, late * 0.5, gum * 0.7);
        albedo *= 0.72 + 0.5 * age;                                     // one board darker with age than the next
        albedo *= 1.0 + tint * 0.14;
        albedo *= vec3(1.0 + hue * 0.06, 1.0, 1.0 - hue * 0.14);        // one redder, one browner
        albedo *= mix(vec3(1.0), vec3(0.82, 0.76, 0.72), endGrain * 0.6);   // the ends drink the light

        // --- the hands' wear --------------------------------------------------------------------
        // The edges were rounded by hand and then by years: the radius wanders along each edge
        // and differs block to block.
        float rrBase = 0.055 + 0.05 * hash13(vec3(s.block * 1.7, 3.0, 3.0));
        vec3 rrv = rrBase * (0.65 + 0.8 * vec3(valueNoise(p * 5.0 + 3.0), valueNoise(p * 5.0 + 13.0), valueNoise(p * 5.0 + 23.0)));
        vec3 t = clamp(1.0 - s.edge / rrv, 0.0, 1.0);
        float nearEdge = max(max(t.x, t.y), t.z);
        // Some corners took a knock: a chip, a bigger bite out of the rounding, pale wood inside.
        vec3 cornerId = sign(s.box) * 3.0 + s.block * 7.0;
        float cornerT = max(max(t.x * t.y, t.y * t.z), t.z * t.x);
        float chip = step(0.62, hash13(cornerId + 0.5)) * smoothstep(0.03, 0.4, cornerT);
        vec3 round_ = (t * t) * sign(s.box) * (vec3(1.0) - nAxis);
        vec3 bump = (1.0 + 1.6 * chip) * round_;
        albedo = mix(albedo, sapCol * 1.05, chip * 0.55);
        // Dents and dings pressed into the faces: the normal follows their slope, grime sits in them.
        float e = 0.015;
        float dent = dents(p);
        vec2 slope = vec2(dents(p + e * along) - dents(p - e * along), dents(p + e * cross_) - dents(p - e * cross_)) / (2.0 * e);
        bump += 0.03 * (slope.x * along + slope.y * cross_) * (1.0 - endGrain);   // the normal follows the hollow
        // Faint tool marks: shallow planing ridges along the grain, on parts of a face only.
        float uAcross = dot(p, cross_) + 0.37 * dot(p, nAxis);
        float ridgeMask = smoothstep(0.5, 0.68, valueNoise(p * (along * 0.9 + cross_ * 2.0 + nAxis * 2.0) + 90.0)) * (1.0 - endGrain);
        float ridgeWarp = valueNoise(p * (along * 2.5 + cross_ * 5.0) + 60.0);
        bump += cross_ * cos(uAcross * 52.0 + ridgeWarp * 4.0) * 0.018 * ridgeMask;
        // A scratch across some faces: a thin pale line, where the patina was cut through.
        float seed = hash13(vec3(s.block * 5.3, dot(nAxis, vec3(1.0, 2.0, 3.0)), sign(dot(s.n, vec3(1.0))) * 2.0 + 4.0));
        float a = seed * 6.2832;
        vec3 dir2 = cos(a) * along + sin(a) * cross_, perp = -sin(a) * along + cos(a) * cross_;
        float sc = dot(s.box, perp) - (hash13(vec3(seed * 9.0, 1.0, 1.0)) - 0.5) * 0.5;
        float sl = dot(s.box, dir2) - (hash13(vec3(seed * 4.0, 2.0, 2.0)) - 0.5) * 0.4;
        float scratch = step(0.55, seed) * smoothstep(0.0045, 0.0012, abs(sc)) * (1.0 - smoothstep(0.12, 0.26, abs(sl))) * (1.0 - endGrain);
        albedo = mix(albedo, sapCol * 0.9, scratch * 0.55);
        // Grime in the hollows and in a band just inside the rounded edges and at the joints,
        // and the arrises themselves worn paler, the patina rubbed through by hands.
        float grime = 0.15 * smoothstep(0.08, 0.55, nearEdge) * (1.0 - smoothstep(0.55, 1.0, nearEdge)) * (0.5 + 0.7 * valueNoise(p * 8.0 + 5.0)) + 0.14 * dent + 0.06 * lines;
        albedo *= 1.0 - grime;
        albedo = mix(albedo, sapCol * 0.85, smoothstep(0.7, 1.0, nearEdge) * 0.4 * (0.5 + 0.5 * valueNoise(p * 9.0 + 71.0)));

        // The sheen: finger-polished on the high spots and the rounded edges, dull in the grain
        // and the hollows, and never even.
        float polish = 0.6 + 0.4 * valueNoise(p * 2.0 + 99.0);
        float gloss = 0.025 + 0.09 * polish * (1.0 - dent) * (1.0 - 0.6 * lines) + 0.08 * smoothstep(0.5, 1.0, nearEdge);
        return Surface(albedo, bump, gloss, 14.0, vec3(0.0));
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

    // ------------------------------------------------------------ the light: a candle
    // Drawn on the light's quad (LANTERN.haloSize beams wide, l.uv -1..1 across it): the flame
    // sits at the light's point, the point the scene lights the stone from; a stub of wax hangs
    // below it. Screened over the world, so it only brightens: the flame is what reads, the wax
    // is a pale stroke over the wood, and the wick is where nothing is drawn.
    light: /* glsl */ `
      float roundBox(vec2 p, vec2 c, vec2 b, float r) {
        vec2 d = abs(p - c) - b + r;
        return length(max(d, 0.0)) + min(max(d.x, d.y), 0.0) - r;
      }
      vec3 lightAt(LightIn l) {
        vec2 q = l.uv * 1.5;                       // beams from the flame's point (haloSize 3.0 / 2)
        float aa = max(fwidth(q.y), 0.0015);       // about a device pixel
        vec3 amber = uAccent;
        if (l.part < 0.5) {
          // Under the stone: the air lit round the flame, warm, a little deeper than the accent.
          float halo = 0.03 / (l.r * l.r + 0.03) * smoothstep(1.5, 0.6, l.r);
          vec3 deep = amber * vec3(1.0, 0.8, 0.5);
          return deep * halo * 0.65 * l.power + grain(l.frag, l.time, 0.008) * step(0.004, halo);
        }
        // The flicker: a few slow sines, so it breathes and leans without ever guttering.
        float t = l.time;
        float breath = 0.5 * sin(t * 7.3) + 0.3 * sin(t * 11.7 + 1.0) + 0.2 * sin(t * 3.1 + 2.0);
        float sway = 0.5 * sin(t * 5.1 + 0.7) + 0.3 * sin(t * 9.4 + 2.3) + 0.2 * sin(t * 2.3);
        float h = 0.13 * (1.0 + 0.1 * breath);     // the flame's height, beams
        float lean = 0.02 * sway;

        // The flame: a teardrop from the wick's tip, widest a third of the way up, leaning at the tip.
        float base = -0.03;
        float ft = (q.y - base) / h;               // 0 at the wick's tip, 1 at the flame's
        float up = clamp(ft, 0.0, 1.0);
        float xc = lean * up * up;
        float rad = 0.04 * 2.6 * sqrt(up) * (1.0 - up);
        float dx = abs(q.x - xc);
        float inFlame = smoothstep(rad + aa, rad - aa, dx) * step(0.0, ft) * (1.0 - smoothstep(1.0, 1.0 + aa / h, ft));
        float core = smoothstep(0.6, 0.15, dx / max(rad, 1.0e-4)) * smoothstep(0.05, 0.3, ft) * smoothstep(0.85, 0.45, ft);
        vec3 flame = mix(amber * vec3(1.0, 0.72, 0.4), vec3(1.0, 0.97, 0.8), core) * inFlame;
        // Its glow in the eye, a little above its base.
        vec2 g = q - vec2(xc * 0.5, h * 0.3);
        flame += amber * vec3(1.0, 0.8, 0.5) * exp(-dot(g, g) / 0.008) * 0.35;
        // The wick: a thin dark thread the flame is drawn round (the only dark thing: nothing drawn).
        float wick = smoothstep(0.006 + aa, 0.006 - aa, abs(q.x)) * smoothstep(-0.06, -0.052, q.y) * smoothstep(0.014, 0.0, q.y);
        flame *= 1.0 - wick;

        // The wax: a short stub below the wick, rounded, a pale highlight down one side, its rim
        // lit by the flame, and one drip run down its right.
        float body = roundBox(q, vec2(0.0, -0.13), vec2(0.034, 0.08), 0.009);
        float drip = min(length(q - vec2(0.031, -0.083)) - 0.012, roundBox(q, vec2(0.0335, -0.108), vec2(0.006, 0.032), 0.0055));
        float inWax = smoothstep(aa, -aa, min(body, drip));
        vec3 wax = vec3(0.9, 0.84, 0.7);
        wax *= 1.0 + 0.25 * exp(-(q.x + 0.015) * (q.x + 0.015) / 0.00015);         // the highlight
        wax *= 1.0 + 0.4 * exp(-(q.y + 0.052) * (q.y + 0.052) / 0.0015) * (0.8 + 0.2 * breath); // the lit rim
        wax = mix(wax, amber * 0.9 + 0.1, 0.35 * exp(-(q.y + 0.056) * (q.y + 0.056) / 0.0025));      // warmed by the flame

        float lit = min(l.power, 1.0);
        return wax * inWax * 0.95 * lit + flame * min(l.power, 1.3);
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
