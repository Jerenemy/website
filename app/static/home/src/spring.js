// A damped spring integrated in closed form, so it is exact and stable for any frame time
// and can be retargeted mid-flight without a discontinuity in velocity.
const REST = 1e-6;   // below this displacement and speed a spring is declared at rest, exactly

export class Spring {
  constructor(value = 0, omega = 10, zeta = 1) {
    this.value = value;
    this.target = value;
    this.velocity = 0;
    this.omega = omega;
    this.zeta = zeta;
  }

  snap(value) {
    this.value = this.target = value;
    this.velocity = 0;
  }

  step(dt) {
    const { omega: w, zeta: z } = this;
    const d = this.value - this.target;
    if (z >= 1) {
      // critically damped
      const c = this.velocity + w * d;
      const e = Math.exp(-w * dt);
      this.value = this.target + (d + c * dt) * e;
      this.velocity = (c - w * (d + c * dt)) * e;
    } else {
      const wd = w * Math.sqrt(1 - z * z);
      const c2 = (this.velocity + z * w * d) / wd;
      const e = Math.exp(-z * w * dt), cos = Math.cos(wd * dt), sin = Math.sin(wd * dt);
      this.value = this.target + e * (d * cos + c2 * sin);
      this.velocity = e * ((c2 * wd - z * w * d) * cos - (d * wd + z * w * c2) * sin);
    }
    // The tail of an exponential never reaches zero on its own: land it, so a resting
    // spring is exactly at its target and the state it feeds never carries denormals.
    if (Math.abs(this.value - this.target) < REST && Math.abs(this.velocity) < REST) {
      this.value = this.target;
      this.velocity = 0;
    }
    return this.value;
  }

  /** Exactly at the target and still: true only once step() has landed it. */
  get resting() {
    return this.value === this.target && this.velocity === 0;
  }
}

export const clamp = (v, lo, hi) => Math.min(hi, Math.max(lo, v));
export const saturate = (v) => clamp(v, 0, 1);
/** 0 before a, 1 after b, linear between. */
export const ramp = (t, a, b) => saturate((t - a) / (b - a));
export const easeOutCubic = (t) => 1 - (1 - t) ** 3;
export const easeInOutCubic = (t) => (t < 0.5 ? 4 * t * t * t : 1 - (-2 * t + 2) ** 3 / 2);
export const easeInQuad = (t) => t * t;
export const easeOutQuint = (t) => 1 - (1 - t) ** 5;
/** 0 before a, 1 after b, smooth (C1) between. */
export const smoothstep = (a, b, t) => { const x = saturate((t - a) / (b - a)); return x * x * (3 - 2 * x); };
