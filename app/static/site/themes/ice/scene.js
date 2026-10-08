// THEME: ice. The world of static/site/themes/ice: the blocks are ice cubes fresh from the
// freezer and starting to melt, the air a cold clean gradient, the light a cold cyan, the dust
// snow. A plain module (no imports) of the shape static/home/src/theme.js describes: `config`
// over src/config.js, `glsl` the four hooks.
export default {
  config: {
    PALETTE: {
      coreDisplay: [0.9, 0.98, 1.0],       // the core burns to a blue-white
    },
    PLACE: {
      grain: 0.004,                        // ice is clean: barely a dither
      noiseScale: 2.2,
      drift: [0.02, 0.025],
      vignette: 0.2,
    },
    SHADING: {
      key: 1.15,                           // a bright key, little ambient, steep tones
      ambient: 0.01,
      fill: 0.12,
      keyWrapPower: 3.0,
      topLight: 0.07,
      bevelGain: 0.9,                      // bright arrises...
      lineWidthPx: 1.3,                    // a little wider than the void's: at one pixel a near-vertical joint
                                           // rasterises as alternate pixels, and the ice shows it
      jointDarken: 0.6,
      wearWidth: 0.05,                     // ...softening into worn, melting edges
      wearGain: 0.12,
      grainAmount: 0.003,
      lanternWhite: [0.14, 0.17, 0.2],     // what the light adds to a face it does not hold: cold white
      lanternEdge: 0.5,
      mistFloor: 0.55,                     // far from the focus the ice still reads as ice
    },
    LANTERN: {
      haloSize: 2.8,
      haloGain: 0.5,
      haloGrain: 0.004,
      bloom: 0.01,                         // a tight bloom: a hard, small core
      bloomGain: 0.9,
      trailSize: 0.28,
    },
    DUST: {
      ambientCount: 260,
      burstCount: 110,
      fall: [0.028, 0.04],                 // snow, falling slowly
      wander: 0.05,
      size: [1.6, 5.0],
      alpha: [0.14, 0.28],
      twinkle: 0.0,                        // steady flakes
      depth: 14,
    },
  },
  glsl: {
    // The ice: a clear cube, deep blue in the middle of each face and paler toward its edges,
    // soft inclusions and trapped bubbles inside, a hairline fracture here and there, a glassy
    // relief, and the melt: a film of water on the treads, runs down the walls with a bead at
    // their end, one drop crawling, drops hanging under the bottom edge.
    surface: `
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
      // The face's own two coordinates of a point: the texture sticks to the block.
      vec2 onFace(vec3 p, vec3 n) {
        return n.x > 0.5 ? p.yz : (n.y > 0.5 ? p.zx : p.xy);
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
      Surface surfaceAt(SurfaceIn s) {
        vec3 p = s.rest + vec3(s.block * 0.37);                   // each block its own ice
        vec2 q = onFace(p, s.n) + s.block * 0.61;
        float pxq = max(fwidth(q.x), fwidth(q.y));                // one device pixel, in q
        vec3 tan = vec3(1.0) - abs(s.n);

        // --- the body: deep in the middle of a face, pale at its edges and corners ----------
        vec3 rel = abs(s.box) / max(s.ext, vec3(1.0e-4)) * tan;
        float toCentre = max(max(rel.x, rel.y), rel.z);           // 0 at the face's centre, 1 at its edge
        float toEdge = min(min(s.edge.x, s.edge.y), s.edge.z);
        float rim = min(smoothstep(0.6, 1.0, toCentre) * 0.25 + (1.0 - smoothstep(0.0, 0.05, toEdge)) * 0.5, 1.0);
        // A freezer cube is cloudy in the middle, where the air was trapped, and clear round it.
        float cloud = valueNoise(p * 1.9 + 5.0) * 0.6 + valueNoise(p * 4.7 + 9.0) * 0.4;
        float rad = length(rel) * (0.75 + 0.3 * hash12(vec2(s.block, 1.5)));  // each cube froze its own cloud
        float core = (1.0 - smoothstep(0.1, 0.9, rad + (cloud - 0.5) * 0.8)) * (0.4 + 0.6 * cloud);
        float cloudy = core * 0.6 + smoothstep(0.55, 0.9, cloud) * 0.15;
        float inside = smoothstep(0.05, 0.5, core);                 // the bubbles are in the cloud
        float bub = bubbles(q * 11.0, 0.3 * inside, pxq * 11.0) + 0.7 * bubbles(q * 23.0 + 4.0, 0.22 * inside, pxq * 23.0);
        float where = smoothstep(0.56, 0.64, valueNoise(p * 0.9 + 23.0));
        float crack = worleyEdge(q * 0.9 + 3.7, max(0.012, 1.4 * pxq * 0.9)) * where;
        vec3 bump = -(undulation(p * 1.7 + 31.0) * 0.045 + undulation(p * 6.0 + 67.0) * 0.012) * tan;
        // The arrises have begun to melt round.
        bump -= 0.5 * (1.0 - smoothstep(0.0, 0.05, s.edge)) * sign(s.box) * tan;

        // --- the melt --------------------------------------------------------------------------
        // Down is the structure's -y: the key is fixed to the stone and the whole picture turns with
        // it, so this is the down the picture shows, the same on every side (a block's own tread,
        // s.up, differs from side to side round the loop). Its +y face is its top.
        float top = step(0.5, s.n.y);
        float wall = 1.0 - top;
        vec3 across = vec3(s.n.z, 0.0, -s.n.x);                  // along the wall, level
        float x = dot(s.rest, across) + s.block * 0.53;
        float down = s.ext.y - s.box.y;                           // beams down from the top edge
        float height = 2.0 * s.ext.y;
        // Runs: some columns of the wall carry a trickle from the top edge, wobbling a little,
        // ending in a bead; on a few of them one drop is crawling down.
        float cols = 5.0;
        float col = floor(x * cols);
        float hc = hash12(vec2(col, s.block + 0.5));
        float has = step(0.55, hc) * wall;
        float len = 0.25 + 0.95 * hash12(vec2(col + 7.0, s.block));
        float w = 0.024 + 0.016 * hash12(vec2(col + 3.0, s.block));
        float dx = (fract(x * cols) - 0.5) / cols - 0.012 * sin(down * 14.0 + hc * 20.0);
        float run = smoothstep(w, w * 0.45, abs(dx)) * smoothstep(len, len - 0.12, down) * has;
        float r = w * 1.9;
        vec2 bd = vec2(dx, down - len);
        float bead = smoothstep(r, r * 0.65, length(bd)) * has;
        float crawlAt = fract(s.time * 0.045 * (0.6 + hc) + hc * 3.0) * len;
        vec2 cd = vec2(dx, down - crawlAt);
        float crawl = smoothstep(r * 0.95, r * 0.6, length(cd)) * has * step(0.55, hash12(vec2(col + 13.0, s.block)));
        // Drops hanging under the bottom edge.
        // (not on the side that runs up and down, where a wall's bottom edge is a joint)
        float bcols = 4.0;
        float bcol = floor(x * bcols + 0.5);
        float hb = hash12(vec2(bcol, s.block + 9.0));
        float rb = 0.035 + 0.025 * hb;
        vec2 bb = vec2((fract(x * bcols + 0.5) - 0.5) / bcols, down - (height - rb * 0.5));
        float hang = smoothstep(rb, rb * 0.6, length(bb)) * step(0.5, hb) * wall * (1.0 - step(0.5, abs(s.travel.y)));
        float pool = smoothstep(height - 0.12, height - 0.02, down) * wall * smoothstep(0.3, 0.7, valueNoise(p * 3.0 + 83.0));
        float wet = max(max(max(run, bead), max(crawl, hang)), pool);
        // What water does to the light: a bright line down one side of a run and a dark one down the
        // other, a spot on each drop and a dark rim under it.
        float side = clamp(dx / w, -1.0, 1.0);
        float shineLine = smoothstep(0.1, 0.45, side) * (1.0 - smoothstep(0.55, 0.95, side)) * run;
        float shadeLine = smoothstep(-0.1, -0.5, side) * run;
        vec2 bq = bd / r, cq = cd / r, hq = bb / rb;
        float spot = smoothstep(0.5, 0.15, length(bq - vec2(-0.3, -0.3))) * bead + smoothstep(0.5, 0.15, length(cq - vec2(-0.3, -0.3))) * crawl + smoothstep(0.5, 0.15, length(hq - vec2(-0.3, -0.3))) * hang;
        float dropRim = smoothstep(0.55, 1.0, length(bq)) * bead + smoothstep(0.55, 1.0, length(cq)) * crawl + smoothstep(0.55, 1.0, length(hq)) * hang;
        // Water's own relief: a half-round for the run, a sphere for every drop.
        vec3 waterBump = across * (dx / w) * 0.45 * run
          + (across * bd.x - s.up * bd.y) / r * 0.7 * bead
          + (across * cd.x - s.up * cd.y) / r * 0.7 * crawl
          + (across * bb.x - s.up * bb.y) / rb * 0.7 * hang;
        // The tread: a film of meltwater, flat and glassy, pooling here and there.
        float film = top;
        float puddle = smoothstep(0.48, 0.6, valueNoise(p * 2.3 + 51.0)) * film;
        bump = mix(bump * (1.0 - 0.5 * film) * (1.0 - 0.85 * puddle), waterBump, wet);

        // --- the colour --------------------------------------------------------------------------
        vec3 deep = vec3(0.30, 0.60, 0.90);
        vec3 pale = vec3(0.80, 0.90, 1.0);
        float white = min(rim + cloudy + crack * 0.4 + bub * 0.9, 1.0);
        vec3 albedo = mix(deep, pale, white);
        albedo *= mix(vec3(1.0), vec3(0.72, 0.86, 1.0), max(wet * 0.8, puddle * 0.45));   // water: clearer, bluer
        albedo *= 1.0 - 0.3 * max(shadeLine, dropRim);
        float glassy = max(wet, max(film, puddle));
        float gloss = mix(0.75, 1.0, glassy);
        float shine = mix(90.0, 170.0, glassy);
        // Light caught inside the cube: deepest in the middle of a face.
        vec3 emit = vec3(0.012, 0.024, 0.04) * (1.0 - 0.6 * toCentre) * (1.0 + 0.8 * core) * (1.0 - 0.4 * wet)
          + vec3(0.09, 0.12, 0.15) * max(shineLine, spot)                                    // the water's own glints
          + vec3(0.025, 0.04, 0.055) * bub;                                                  // a bubble scatters the light
        return Surface(albedo, bump, gloss, shine, emit);
      }`,
    // The air: a clean cold gradient, white above through steel blue to a deep cool blue below,
    // a soft glow round the monument and a pale pool of mist under it.
    air: `
      vec3 airAt(AirIn a) {
        float t = a.uv.y + (a.n - 0.5) * 0.06;
        vec3 top = vec3(0.86, 0.91, 0.96);
        vec3 mid = vec3(0.28, 0.40, 0.55);
        vec3 low = vec3(0.11, 0.19, 0.31);
        float up = smoothstep(0.45, 1.0, t);
        vec3 tone = mix(mix(low, mid, smoothstep(0.0, 0.55, t)), top, up * up);
        tone += vec3(0.09, 0.12, 0.15) * exp(-dot(a.toCentre, a.toCentre) / 1.7);
        tone += vec3(0.06, 0.08, 0.1) * a.below * a.across * (0.5 + 0.6 * a.n);
        float v = length((a.uv - 0.5) * vec2(1.0, 1.2));
        tone *= 1.0 - 0.22 * smoothstep(0.45, 0.95, v);
        return tone;
      }`,
    // The light: a hard, small core, a tight bloom, a four-point glint, a little halo.
    light: `
      vec3 lightAt(LightIn l) {
        float halo = 0.025 / (l.r * l.r + 0.025) * smoothstep(1.4, 0.45, l.r);
        float bloom = exp(-l.r * l.r / 0.01);
        float core = smoothstep(0.075, 0.03, l.r);
        float ang = atan(l.uv.y, l.uv.x);
        float rays = pow(abs(cos(ang * 2.0)), 48.0) * exp(-l.r * 2.6) * smoothstep(0.02, 0.09, l.r);
        return l.part < 0.5
          ? uAccent * halo * 0.5 * l.power + grain(l.frag, l.time, 0.004) * step(0.004, halo)
          : uAccent * (bloom * 0.9 + rays * 0.8) * l.power + vec3(0.9, 0.98, 1.0) * core * min(l.power, 1.0);
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
