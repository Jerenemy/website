// THEME: ice. The world of static/site/themes/ice: the blocks are clear ice cubes out in the sun
// and starting to melt (their arrises rounding, a slick of water over them), the air a summer sky
// with the sun's glare in it, the light a cold cyan orb drawn over the frame, the dust the glints
// that drift up through sunlight. A plain module (no imports) of the shape static/home/src/theme.js
// describes: `config` over src/config.js, `glsl` the four hooks.
export default {
  config: {
    PALETTE: {
      coreDisplay: [0.92, 0.99, 1.0],      // the core burns to a blue-white
    },
    PLACE: {
      grain: 0.004,                        // a clean sky: barely a dither
      noiseScale: 2.2,
      drift: [0.02, 0.012],
      vignette: 0.12,
    },
    SHADING: {
      key: 0.95,                           // the sun: a bright key, steep tones...
      ambient: 0.05,                       // ...over a sky's worth of ambient
      fill: 0.2,
      keyWrapPower: 2.8,
      topLight: 0.06,
      bevelGain: 0.0,                      // the arrises have melted round: no crisp line at all
      lineWidthPx: 1.3,                    // a little wider than the void's: at one pixel a near-vertical joint
                                           // rasterises as alternate pixels, and the ice shows it
      jointDarken: 0.15,                   // the joints are grooves between rounded cubes: the rounding shades them
      wearWidth: 0.08,
      wearGain: 0.0,
      lanternEdge: 0.1,
      grainAmount: 0.003,
      lanternWhite: [0.14, 0.17, 0.2],     // what the light adds to a face it does not hold: cold white
      lanternEdge: 0.4,
      mistFloor: 0.7,                      // sunlit everywhere: the far ice still reads as ice
    },
    LANTERN: {
      blend: 'over',                       // the air is bright: the orb is drawn as a thing, with coverage
      haloSize: 2.8,
      haloGain: 0.5,
      haloGrain: 0.004,
      bloom: 0.01,
      bloomGain: 0.9,
      trailSize: 0.28,
    },
    DUST: {
      ambientCount: 120,
      burstCount: 70,
      fall: [-0.004, -0.008],              // warm air: the glints drift up, slowly
      wander: 0.05,
      size: [1.6, 3.5],
      alpha: [0.3, 0.5],
      twinkle: 0.0,                        // the flash is the mote's own (below)
      depth: 14,
    },
  },
  glsl: {
    // THE ICE. A clear cube, seen into: the view is refracted through the wet skin into the body,
    // runs through it (thicker is bluer, by absorption) and leaves by a far face, whose arrises show
    // through as the bright lines that make ice read as glass; what comes back is the sky, the
    // ground and the sun that enter by that far face. Over that, the skin: the sun's hard glint and
    // the sky's soft reflection on a slick of meltwater that creeps slowly, arrises that have
    // melted round (unevenly), puddles on the tops, a wet band where water gathers at the foot of
    // a wall, the traces of a trickle or two. Inside: a faint freezer cloud, trapped bubbles, a
    // hairline fracture here and there, all of it swimming a little as the skin's relief bends the
    // view. The view direction is the true angle, fixed to the stone (the roll turns about it), so
    // nothing here depends on distance along it.
    surface: /* glsl */ `
      vec2 onFace(vec3 p, vec3 n) { return n.x > 0.5 ? p.yz : (n.y > 0.5 ? p.zx : p.xy); }
      float nz(float v) { return abs(v) < 1.0e-4 ? (v < 0.0 ? -1.0e-4 : 1.0e-4) : v; }
      // Hairline fractures: the borders of a cellular partition of the face, thin bright lines.
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
      // Trapped bubbles: at most one per cell of a grid across the face, a small lens with a
      // bright rim and a dimmer middle. density is the share of cells that hold one.
      float bubbles(vec2 q, float density, float px) {
        vec2 i = floor(q), f = fract(q);
        float h = hash12(i + 0.5);
        vec2 c = vec2(hash12(i + 3.1), hash12(i + 7.7)) * 0.5 + 0.25;
        float r = 0.05 + 0.07 * hash12(i + 11.3);
        float d = length(f - c);
        float lens = smoothstep(r + px, max(r - px, 0.0), d) * (0.55 + 0.45 * smoothstep(r * 0.3, r * 0.8, d));
        return lens * step(1.0 - density, h);
      }
      // The gradient of a slow noise, for a glassy relief.
      vec3 undulation(vec3 p) {
        float e = 0.01;
        float u0 = valueNoise(p);
        return vec3(valueNoise(p + vec3(e, 0.0, 0.0)) - u0, valueNoise(p + vec3(0.0, e, 0.0)) - u0, valueNoise(p + vec3(0.0, 0.0, e)) - u0) / e;
      }
      // The world the ice stands in, by a direction (structure space, +y up): a summer sky, the haze
      // at the horizon, a bright ground below. Linear light.
      vec3 envAt(vec3 d) {
        vec3 zenith = vec3(0.20, 0.40, 0.85), horizon = vec3(0.80, 0.86, 0.92), ground = vec3(0.78, 0.74, 0.66);
        vec3 sky = mix(horizon, zenith, smoothstep(0.0, 0.85, d.y));
        return mix(ground, sky, smoothstep(-0.1, 0.1, d.y));
      }
      // The light that comes in through a face of the cube (its outward normal n): the sky and the
      // ground it sees, and the sun, which is the scene's key (SHADING.keyDir).
      vec3 inflow(vec3 n) {
        vec3 SUN = vec3(-0.3856, 0.7711, 0.5067);
        return envAt(n) * 0.85 + vec3(1.0, 0.96, 0.88) * 0.8 * max(dot(n, SUN), 0.0);
      }
      Surface surfaceAt(SurfaceIn s) {
        vec3 p = s.rest + vec3(s.block * 0.37);                   // each block its own ice
        vec3 tg = vec3(1.0) - abs(s.n);                             // the face's tangent plane
        vec3 E = normalize(vec3(1.0));                            // toward the eye, structure space: the true angle
        vec3 SUN = vec3(-0.3856, 0.7711, 0.5067);
        float top = step(0.5, s.n.y), wall = 1.0 - top;           // down is structure -y: what the picture shows as down
        vec3 across = vec3(s.n.z, 0.0, -s.n.x);                   // along a wall, level

        // --- the skin: arrises melting round, the body's slow glassy swell, the water creeping ------
        float rr = 0.15 + 0.07 * valueNoise(p * 5.0 + 3.0);      // the rounding wanders: the melt is uneven
        vec3 t = clamp(1.0 - s.edge / rr, 0.0, 1.0);
        float nearEdge = max(max(t.x, t.y), t.z);
        // A quarter-round's profile: over the radius the normal turns from the face's own to 45
        // degrees at the arris, where the next face's normal meets it turning the other way, so the
        // tone runs smoothly over the edge with no line; the turn starts flat and quickens.
        vec3 u = 1.0 - t;
        vec3 roundB = tan(0.785 * (1.0 - u * u)) * sign(s.box) * tg;
        vec3 bump = -(undulation(p * 1.6 + 31.0) * 0.07 + undulation(p * 5.0 + 67.0) * 0.02) * tg;
        bump -= undulation(p * 9.0 + vec3(0.0, s.time * 0.06, 0.0) + 90.0) * 0.007 * tg;   // the film, creeping down
        // Puddles on the tops, flat; a wet band where the water gathers at the foot of a wall; the
        // traces of a trickle or two, their water spread thin.
        float puddle = smoothstep(0.5, 0.62, valueNoise(p * 2.3 + 51.0)) * top;
        float x = dot(s.rest, across) + s.block * 0.53;
        float down = s.ext.y - s.box.y, height = 2.0 * s.ext.y;
        float cols = 4.0, col = floor(x * cols);
        float hc = hash12(vec2(col, s.block + 0.5));
        float dx = (fract(x * cols) - 0.5) / cols - 0.02 * sin(down * 11.0 + hc * 20.0);
        float w = 0.03 + 0.02 * hash12(vec2(col + 3.0, s.block));
        float run = smoothstep(w, w * 0.3, abs(dx)) * step(0.6, hc) * wall * smoothstep(0.1, 0.4, down);
        float foot = smoothstep(height - 0.18, height - 0.03, down) * wall;
        bump = mix(bump, bump * 0.1, puddle);
        bump += across * clamp(dx / w, -1.0, 1.0) * 0.25 * run;
        bump -= roundB;
        vec3 Nb = normalize(s.n + bump);
        float cosE = dot(E, Nb);
        if (cosE < 0.08) { Nb = normalize(Nb + E * (0.08 - cosE) * 2.0); cosE = dot(E, Nb); }

        // --- through the ice: the view refracted in, the way out, the far arrises --------------------
        vec3 I = -E;
        vec3 r = refract(I, Nb, 1.0 / 1.31);
        vec3 rs = vec3(nz(r.x), nz(r.y), nz(r.z));
        vec3 tx = (sign(rs) * s.ext - s.box) / rs;                // along the ray, to each far face
        float tExit = max(min(min(tx.x, tx.y), tx.z), 0.0);
        vec3 pe = s.box + r * tExit;                              // where the view leaves the cube
        vec3 ea = step(tx, vec3(tExit + 1.0e-4));                 // the face it leaves by
        vec3 nExit = sign(rs) * ea;
        vec3 pass = exp(-vec3(0.95, 0.38, 0.1) * tExit);         // absorption: a long way through is bluer
        vec3 de = (s.ext - abs(pe)) * (1.0 - ea) + ea * 10.0;     // the exit point from that face's edges
        float dEdge = min(min(de.x, de.y), de.z);
        float farEdge = exp(-dEdge / 0.025);                      // the far arrises, seen through
        vec3 seen = (inflow(nExit) + vec3(0.9, 0.97, 1.0) * farEdge * 0.45) * pass;

        // --- inside: a faint freezer cloud, bubbles, a fracture; all seen through the bent skin ------
        vec3 pin = p + r * 0.3;
        vec2 q = onFace(pin, s.n) + s.block * 0.61;
        float pxq = max(fwidth(q.x), fwidth(q.y));                // one device pixel, in q
        vec3 rel = abs(s.box) / max(s.ext, vec3(1.0e-4)) * tg;
        float cloud = valueNoise(pin * 1.9 + 5.0) * 0.6 + valueNoise(pin * 4.7 + 9.0) * 0.4;
        float rad = length(rel) * (0.8 + 0.3 * hash12(vec2(s.block, 1.5)));
        float core = (1.0 - smoothstep(0.1, 0.8, rad + (cloud - 0.5) * 0.8)) * (0.4 + 0.6 * cloud);
        float cloudy = core * 0.25;                               // faint: this ice is nearly clear
        float inside = smoothstep(0.05, 0.5, core);
        float bub = bubbles(q * 11.0, 0.2 * inside, pxq * 11.0) + 0.6 * bubbles(q * 23.0 + 4.0, 0.15 * inside, pxq * 23.0);
        float where = smoothstep(0.58, 0.66, valueNoise(p * 0.9 + 23.0));
        float crack = worleyEdge(q * 0.8 + 3.7, max(0.012, 1.4 * pxq * 0.8)) * where;

        // --- the skin's reflections: the sky, softly; the sun, hard, on the wet ----------------------
        float F = 0.02 + 0.98 * pow(1.0 - max(cosE, 0.0), 5.0);
        vec3 R = reflect(I, Nb);
        vec3 refl = envAt(R) * F * 0.55;
        // The sun stands where the wet tops just mirror it (a few degrees off the tread's own
        // reflection of the eye), so the film's ripples throw it back as sparkles that creep with
        // the water, and the whole tread carries its sheen; the walls mirror the sky.
        vec3 GLARE = vec3(-0.538, 0.651, -0.538);
        float sunR = max(dot(R, GLARE), 0.0);
        float wetness = 0.6 + 0.4 * max(max(puddle, foot), run);
        vec3 glint = vec3(1.0, 0.97, 0.9) * (pow(sunR, 900.0) * 2.5 + pow(sunR, 40.0) * 0.1) * wetness * (0.5 + F * 6.0);

        // --- the colour ---------------------------------------------------------------------------------
        // The albedo is what the key shades, face by face: pale, bluer where the ice is clear, whiter
        // where it is cloudy, cracked, bubbled or rounding at an arris. What shows through is emitted,
        // scaled by the key's own tone of this face (SHADING.keyDir), so the three tones keep apart.
        float white = min(cloudy + crack * 0.35 + bub * 0.8 + nearEdge * nearEdge * 0.1, 1.0);
        vec3 albedo = mix(vec3(0.25, 0.48, 0.76), vec3(0.55, 0.72, 0.9), white);
        albedo *= mix(vec3(1.0), vec3(0.8, 0.9, 1.0), max(puddle * 0.5, foot * 0.4));   // water: clearer, bluer
        float fam = pow(0.5 + 0.5 * dot(s.n, SUN), 2.8);
        vec3 emit = seen * (1.0 - F) * (0.35 + 0.65 * fam) * 0.34
          + refl + glint
          + vec3(0.03, 0.05, 0.07) * bub + vec3(0.05, 0.07, 0.09) * crack;
        float wet = max(max(puddle, foot), run);
        float gloss = mix(0.8, 1.0, wet);
        float shine = mix(120.0, 220.0, max(puddle, foot));
        return Surface(albedo, bump, gloss, shine, emit);
      }
      // The outline: the melt has rounded the cube's corners off, by the same wandering radius as
      // the arrises, so the silhouette is a softened block too.
      float surfaceCover(SurfaceIn s) {
        vec3 p = s.rest + vec3(s.block * 0.37);
        return silhouetteCover(s, 0.15 + 0.07 * valueNoise(p * 5.0 + 3.0));
      }`,
    // The air: a summer sky, deep blue above, the haze pale toward the bottom of the frame, the
    // sun's glare in the upper left (where the key comes from), lit haze round the monument.
    air: /* glsl */ `
      vec3 airAt(AirIn a) {
        float t = a.uv.y + (a.n - 0.5) * 0.05;
        vec3 zenith = vec3(0.16, 0.36, 0.82), mid = vec3(0.45, 0.62, 0.88), low = vec3(0.82, 0.87, 0.92);
        vec3 tone = mix(mix(low, mid, smoothstep(0.0, 0.5, t)), zenith, smoothstep(0.5, 1.05, t));
        vec2 sun = vec2(0.14, 0.95);
        vec2 d = (a.uv - sun) * vec2(a.aspect, 1.0);
        float dd = dot(d, d);
        tone += vec3(1.0, 0.95, 0.85) * (0.7 * exp(-dd / 0.05) + 0.3 * exp(-dd / 0.9));
        tone += vec3(0.08, 0.09, 0.1) * exp(-dot(a.toCentre, a.toCentre) / 1.7);
        tone += vec3(0.07, 0.07, 0.07) * a.below * a.across * (0.5 + 0.6 * a.n);
        float v = length((a.uv - 0.5) * vec2(1.0, 1.2));
        tone *= 1.0 - 0.12 * smoothstep(0.5, 1.0, v);
        return tone;
      }`,
    // The light: an orb of cold cyan drawn over the frame (LANTERN.blend 'over'), a hard blue-white
    // core, a tight bloom, a four-point glint, a soft halo of its colour in the air.
    light: /* glsl */ `
      void orb(LightIn l, out vec3 c, out float a) {
        float core = smoothstep(0.08, 0.04, l.r);
        float bloom = exp(-l.r * l.r / 0.012);
        float halo = 0.03 / (l.r * l.r + 0.03) * smoothstep(1.4, 0.4, l.r);
        float ang = atan(l.uv.y, l.uv.x);
        float rays = pow(abs(cos(ang * 2.0)), 40.0) * exp(-l.r * 2.4) * smoothstep(0.02, 0.1, l.r);
        if (l.part < 0.5) {
          a = halo * 0.6 * min(l.power, 1.5);
          c = mix(uAccent, vec3(1.0), 0.15);
        } else {
          a = clamp(core + bloom * 0.9 + rays * 0.7, 0.0, 1.0) * min(l.power, 1.0);
          c = mix(uAccent, vec3(0.92, 0.99, 1.0), core);
        }
      }
      vec3 lightAt(LightIn l) { vec3 c; float a; orb(l, c, a); return c * a; }
      float lightCover(LightIn l) { vec3 c; float a; orb(l, c, a); return a; }`,
    // The dust: glints in the sunlight, each flashing in its own time (a four-point star while it
    // flashes, a speck between); the spray thrown when the ice knocks, fine drops.
    mote: /* glsl */ `
      vec4 moteAt(MoteIn m) {
        float d = length(m.pc);
        float disc = smoothstep(0.55, 0.1, d);
        if (m.kind > 0.5) return vec4(vec3(0.9, 0.95, 1.0) * disc * m.alpha, 1.0);
        float period = 1.4 + 2.2 * m.seed.z;
        float ph = fract(m.time / period + m.seed.x);
        float on = smoothstep(0.0, 0.07, ph) * (1.0 - smoothstep(0.1, 0.32, ph));
        float star = max(smoothstep(0.1, 0.0, abs(m.pc.x)), smoothstep(0.1, 0.0, abs(m.pc.y))) * smoothstep(1.0, 0.15, d);
        float a = (disc + star * 0.6 * on) * m.alpha * (0.2 + on);
        vec3 tint = mix(vec3(dot(uAccent, vec3(0.2126, 0.7152, 0.0722))), uAccent, m.chroma);
        vec3 c = vec3(1.0, 0.98, 0.93) + tint * m.warm * 1.5;
        return vec4(c * a, 1.0);
      }`,
  },
};
