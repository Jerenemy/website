// THEME: nature. The homepage's world as a summer dusk in a wood: the blocks are sarsen, the
// weathered grey sandstone of Stonehenge (pitted, lichened, their arrises rounded by weather),
// soil and a little moss in their seams; the air a dusk under a canopy; the light a firefly; the
// dust other fireflies, far off, each blinking in its own time. The contract is static/home/src/theme.js.
export default {
  config: {
    PALETTE: { coreDisplay: [1.0, 1.0, 0.82] },
    PLACE: { drift: [0.015, 0.02], vignette: 0.3, grain: 0.012 },
    SHADING: {
      jointDarken: 0.15,          // the joints are grooves between rounded stones: the rounding shades them, not a line
      bevelGain: 0.0,             // no crisp arris at all: a sarsen's edges are round, and the rounding is the material's
      wearGain: 0.0,
      wearWidth: 0.09,
      lineWidthPx: 1.0,
      lanternEdge: 0.1,
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
      // THE STONE: sarsen, the silcrete of the Stonehenge uprights. A hard grey sandstone whose
      // skin is sand grain, knobbly lumps and weather pits, its arrises rounded by millennia and
      // lumpy along their length, a knock taken out here and there; lichen crusts over the open
      // faces, a pale grey-green and a sooty black; rain streaks down the walls; soil and a little
      // moss in the seams and the hollows of a tread; the deeper hollows of a tread hold water.
      // The relief is a height field on the face, evaluated once per fragment and read into the
      // normal through its screen derivatives (so a face costs one height, not three), with the
      // noise in two dimensions on the face's own coordinates: a fragment costs a few hundred
      // hashes, which keeps the stone well inside a GPU's frame budget at retina sizes.

      // Fractal of the value noise on the face, each octave turned so the lattice never shows.
      float fbm2(vec2 q) {
        mat2 R = mat2(0.8, 0.6, -0.6, 0.8);
        float a = 0.0, w = 0.5;
        for (int i = 0; i < 3; i++) { a += w * vnoise(q); q = R * q * 2.03 + 7.1; w *= 0.5; }
        return a / 0.875;
      }
      float fbm2b(vec2 q) {
        return vnoise(q) * 0.65 + vnoise(mat2(0.8, 0.6, -0.6, 0.8) * q * 2.1 + 3.0) * 0.35;
      }
      // Weather pits: a jittered grid, at most one hollow per cell, each its own size and shape:
      // a shallow dimple with a soft rim (most), or a small sharp hole (a few). A hollow never
      // reaches past the middle of the next cell, so only the four nearest cells are looked at.
      float pits(vec2 q, float density, float seed) {
        vec2 i = floor(q), f = fract(q);
        vec2 side = step(0.5, f) * 2.0 - 1.0;
        float d = 0.0;
        for (int k = 0; k < 4; k++) {
          vec2 c = vec2(mod(float(k), 2.0), floor(float(k) * 0.5)) * side;
          vec2 id = i + c + seed;
          vec2 o = c + vec2(hash12(id + 3.3), hash12(id + 7.7)) * 0.6 + 0.2;
          float r = 0.2 + 0.28 * hash12(id + 11.1);
          vec2 v = (o - f) * vec2(1.0 + 0.6 * hash12(id + 5.5), 1.0 + 0.6 * hash12(id + 9.9));   // not round
          float dist = length(v) / r;
          float sharp = step(0.8, hash12(id + 13.0));
          float bowl = mix(smoothstep(1.0, 0.25, dist) * 0.7, max(1.0 - dist * dist * 2.5, 0.0), sharp);
          d = max(d, bowl * step(1.0 - density, hash12(id + 0.5)));
        }
        return d;
      }
      // The gradient on the face of a value known per pixel, from its screen derivatives and the
      // face coordinates' own: exact where the map is locally linear, which on a flat face it is.
      vec2 gradOnFace(float h, vec2 dqx, vec2 dqy, float det) {
        float hx = dFdx(h), hy = dFdy(h);
        vec2 g = vec2(hx * dqy.y - hy * dqx.y, hy * dqx.x - hx * dqy.x) / det;
        float m = length(g);
        return g * min(m, 12.0) / max(m, 1.0e-6);     // a quad straddling an edge gives a wild number: capped
      }
      Surface surfaceAt(SurfaceIn s) {
        vec3 p = s.rest;
        vec3 tangent = vec3(1.0) - abs(s.n);
        vec3 t1 = s.n.yzx, t2 = s.n.zxy;           // the face's two tangent axes
        vec2 q = vec2(dot(p, t1), dot(p, t2)) + s.block * 0.73;
        vec2 dqx = dFdx(q), dqy = dFdy(q);
        float det = dqx.x * dqy.y - dqx.y * dqy.x;
        det = sign(det) * max(abs(det), 1.0e-9) + step(abs(det), 1.0e-9) * 1.0e-9;
        float pxl = sqrt(abs(det));                 // one device pixel, in beams
        float fine = 1.0 - smoothstep(0.008, 0.022, pxl);
        float wall = 1.0 - s.onTop;

        // --- the arrises: rounded, the radius wandering along each edge, a knock here and there -----
        float r0 = 0.17 + 0.07 * hash13(vec3(s.block, 2.0, 2.0));
        vec3 wander = vec3(vnoise(q * 5.5 + 1.0), vnoise(q * 5.5 + 11.0), vnoise(q * 5.5 + 21.0));
        float knock = smoothstep(0.6, 0.7, vnoise(q * 3.3 + 50.0));              // a bite out of the edge
        vec3 rr = r0 * (0.45 + 1.1 * wander) * (1.0 + 1.6 * knock);
        vec3 t = clamp(1.0 - s.edge / rr, 0.0, 1.0);
        float nearEdge = max(max(t.x, t.y), t.z);
        float corner = max(max(t.x * t.y, t.y * t.z), t.z * t.x);              // where two roundings meet
        // A quarter-round's profile. Over the radius the normal turns from the face's own to 45
        // degrees at the arris, where the next face's normal, turning the other way, meets it: the two
        // faces agree there, so the tone runs smoothly over the edge with no line at all. The turn
        // starts flat (zero slope where the round meets the face) and quickens toward the edge.
        vec3 tt = min(t * (1.0 + 0.5 * knock + 0.4 * corner), 1.0);
        vec3 u = 1.0 - tt;
        vec3 roundB = tan(0.785 * (1.0 - u * u)) * sign(s.box) * tangent;

        // --- the relief: lumps, a knobbly skin, sand grain (fading out under a pixel), pits and pockets
        vec2 qw = q + 0.06 * vec2(vnoise(q * 7.0 + 2.0), vnoise(q * 7.0 + 12.0)) - 0.03;   // warped: no two alike
        float lumps = fbm2(q * 2.1);
        float skin = fbm2b(q * 6.5 + 3.0);
        float grain = vnoise(q * 36.0 + 9.0);
        float pit = pits(qw * 4.0, 0.3, 1.0) * 0.8 + pits(qw * 11.0, 0.22, 2.0) * 0.4;
        float pocket = pits(qw * 2.0, 0.14, 4.0);                                 // where an inclusion weathered out
        float h0 = lumps * 0.5 + skin * 0.3 + grain * 0.06 * fine - pit * 0.45 - pocket * 0.7;
        vec2 gH = gradOnFace(h0, dqx, dqy, det);
        vec2 gL = gradOnFace(lumps, dqx, dqy, det);    // the lumps again, stronger: a sarsen's faces bulge and sag
        vec2 g = gH * 0.12 + gL * 0.4;
        vec3 bump = -(g.x * t1 + g.y * t2) * (1.0 - 0.5 * nearEdge) - roundB;

        // --- the stone: grey sarsen, buff where the iron is, each block its own piece -----------------
        float q1 = hash13(vec3(s.block, 7.0, 3.0)), q2 = hash13(vec3(s.block, 1.0, 2.0));
        vec3 grey = vec3(0.285, 0.28, 0.265), buff = vec3(0.34, 0.295, 0.215), cool = vec3(0.24, 0.245, 0.245);
        vec3 rock = mix(mix(grey, cool, q1 * 0.7), buff, q2 * 0.45) * (0.9 + 0.2 * hash13(vec3(s.block, 5.0, 9.0)));
        float stain = fbm2b(q * 1.6 + 17.0);                                      // iron in patches: a rusty buff
        rock = mix(rock, vec3(0.37, 0.285, 0.18), smoothstep(0.5, 0.78, stain) * 0.65);
        float weather = fbm2b(q * 1.1 + 123.0);                                   // the skin weathers darker in zones
        rock *= 0.84 + 0.32 * weather;
        float mottle = fbm2b(q * 9.0 + 1.0);
        float sand = hash12(floor(q * 64.0) + s.block) - 0.5;                     // the sand grain
        rock *= 1.0 + (mottle - 0.5) * 0.5 + sand * 0.22 * fine;
        // Form in the colour: the hollows are darker (the stone shades itself), the pits and pockets
        // darkest, the worn arrises a touch paler.
        rock *= 0.74 + 0.4 * smoothstep(0.15, 0.8, h0 + pit * 0.4);
        rock *= 1.0 - 0.28 * pit - 0.5 * pocket;
        rock *= 1.0 + 0.1 * nearEdge * nearEdge + 0.12 * knock * nearEdge;
        // At a silhouette edge (the round turning away to a face the eye cannot see) the stone falls
        // into its own shadow, so the outline is a soft darkening and not a cut.
        vec3 away = t * (1.0 - step(0.0, s.box));
        float silhouette = max(max(away.x, away.y), away.z);
        rock *= 1.0 - 0.4 * silhouette * silhouette;
        // Rain streaks down the walls (down is structure -y, what the picture shows as down).
        vec2 sq = vec2(dot(p, vec3(s.n.z, 0.0, -s.n.x)), p.y);
        float streak = vnoise(sq * vec2(18.0, 1.3) + 70.0) * 0.6 + vnoise(sq * vec2(40.0, 2.0) + 80.0) * 0.4;
        rock *= 1.0 - 0.14 * smoothstep(0.52, 0.72, streak) * wall;

        // --- lichen: crusts on the open faces, never on the worn arrises -------------------------------
        float lichN = fbm2b(q * 4.2 + 40.0) * 0.7 + fbm2b(q * 14.0 + 44.0) * 0.2 + 0.1 * vnoise(q * 40.0 + 3.0);
        float open = (1.0 - smoothstep(0.3, 0.9, nearEdge)) * (1.0 - 0.7 * pit - pocket);
        float lichA = smoothstep(0.585, 0.615, lichN) * open;                                     // grey-green crust, a ragged edge
        float lichRim = (smoothstep(0.56, 0.585, lichN) - smoothstep(0.585, 0.63, lichN)) * open; // its darker margin
        float pale = step(0.5, hash13(vec3(s.block, 4.0, 4.0)));                                  // on some stones the crust is whitish
        float soot = smoothstep(0.6, 0.68, fbm2b(q * 3.1 + 90.0)) * open * (0.4 + 0.6 * wall);     // the black crusts, mostly on the walls
        vec3 lichC = mix(mix(vec3(0.36, 0.385, 0.32), vec3(0.45, 0.45, 0.37), vnoise(q * 15.0 + 7.0)), vec3(0.5, 0.5, 0.45), pale * 0.7);
        vec3 sootC = vec3(0.10, 0.10, 0.095);
        bump += (lichA - 0.5 * lichRim) * -(gH.x * t1 + gH.y * t2) * 0.01;                     // a crust has its own thin pile

        // --- soil and moss: in the seams, and in the hollows of a tread ------------------------------
        float edgeMin = min(min(s.edge.x, s.edge.y), s.edge.z);
        float seamN = vnoise(q * 9.0 + 5.0);
        float seam = 1.0 - smoothstep(0.012, 0.05 + 0.06 * seamN, edgeMin);
        float hollow = smoothstep(0.45, 0.2, h0) * s.onTop;
        float dirt = clamp(seam * (0.5 + 0.5 * seamN) + hollow * 0.4 + pit * 0.25 * s.onTop + pocket * 0.5, 0.0, 1.0);
        vec3 soil = vec3(0.07, 0.048, 0.027) * (0.8 + 0.4 * vnoise(q * 31.0));
        float patchN = fbm2b(q * 3.0 + s.block * 3.7) * 0.8 + fbm2b(q * 16.0 + 8.0) * 0.2;
        float moss = s.onTop * smoothstep(0.66, 0.74, patchN + 0.25 * hollow) * (1.0 - nearEdge)
          + s.onTop * seam * smoothstep(0.66, 0.76, patchN);                 // a clump where a tread's seam holds soil
        moss = clamp(moss, 0.0, 1.0);
        float mossTone = vnoise(q * 19.0 + 7.0) * 0.5 + vnoise(q * 55.0) * 0.5;
        vec3 mossC = mix(vec3(0.07, 0.16, 0.03), vec3(0.16, 0.29, 0.06), mossTone);

        // --- water: the deep hollows of a tread hold the day's rain ----------------------------------
        float pool = smoothstep(0.55, 0.85, pits(q * 2.6, 0.22, 3.0)) * s.onTop;
        vec3 waterC = vec3(0.03, 0.035, 0.03);

        vec3 albedo = rock;
        albedo = mix(albedo, lichC, lichA * 0.8);
        albedo = mix(albedo, lichC * 0.6, lichRim * 0.5);
        albedo = mix(albedo, sootC, soot * 0.75);
        albedo = mix(albedo, soil, dirt);
        albedo = mix(albedo, mossC, moss);
        albedo = mix(albedo, waterC, pool);
        // Moss has a pile: it softens the relief under it; water is flat.
        bump = mix(bump, -(gH.x * t1 + gH.y * t2) * 0.02 - roundB, moss);
        bump = mix(bump, vec3(0.0), pool);
        // Dry stone has a dull, broad sheen that is what lets the eye read its relief; the moss is
        // damp; the water in a hollow is a mirror.
        float gloss = mix(0.05 * (1.0 - 0.6 * dirt), 0.07, moss);
        float shine = mix(5.0, 14.0, moss);
        gloss = mix(gloss, 0.9, pool);
        shine = mix(shine, 90.0, pool);
        return Surface(albedo, bump, gloss, shine, vec3(0.0));
      }
      // The outline: a sarsen is no box. Its corners are carved off by the rounding, and the radius
      // wanders along the edge as the arrises' does, so the silhouette goes a little lumpy too.
      float surfaceCover(SurfaceIn s) {
        float r = 0.12 + 0.08 * valueNoise(s.rest * 5.5 + 1.0) + 0.06 * smoothstep(0.6, 0.7, valueNoise(s.rest * 3.3 + 50.0));
        return silhouetteCover(s, r);
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
