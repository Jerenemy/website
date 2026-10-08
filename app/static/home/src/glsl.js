// Shader chunks shared by every material so the whole frame is graded identically.
export const GRADE = /* glsl */ `
  // Exact sRGB OETF: materials write linear light, the canvas wants sRGB.
  vec3 toSRGB(vec3 c) {
    c = max(c, 0.0);
    return mix(c * 12.92, 1.055 * pow(c, vec3(1.0 / 2.4)) - 0.055, step(0.0031308, c));
  }
  float hash12(vec2 p) {
    vec3 p3 = fract(vec3(p.xyx) * 0.1031);
    p3 += dot(p3, p3.yzx + 33.33);
    return fract((p3.x + p3.y) * p3.z);
  }
  // Monochrome film grain, triangular distribution, re-seeded 24 times a second.
  // It doubles as dither: without it the void and the soft falloffs band on 8-bit panels.
  float grain(vec2 frag, float time, float amount) {
    float t = floor(time * 24.0);
    float a = hash12(frag + t * 17.13), b = hash12(frag * 1.37 + 91.7 + t * 5.71);
    return (a + b - 1.0) * amount;
  }
`;
