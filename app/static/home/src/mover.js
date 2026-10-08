// A heavy body on a planned journey. Each time the target changes the journey is re-planned
// from the body's current position, velocity AND acceleration, so a retarget mid-flight is
// continuous to the second derivative: no kink, no kick. The journey is one quintic Hermite
// segment that ends at rest. Zero velocity and acceleration at both ends is the minimum-jerk
// profile: speed builds quadratically from rest, the launch of a heavy thing, and drains the
// same way into the stop. The duration is the caller's (a function of distance); two guards
// sit under it.
//
// It never turns back. A body heading for its target keeps heading there until it stops: the
// segment's velocity is (1 - s)^2 g(s) with g a quadratic in s (below), so whether it changes
// sign is known exactly, and the duration is shortened until it does not (a body arriving
// fast at a near target is braked instead of swung past it; one still decelerating from an
// earlier plan is not let run backwards). Only if the hardest brake would still turn back is
// the carried acceleration let go, a kink the eye forgives where a reversal it does not.
// And no journey is shorter than MIN_DURATION.
const MIN_DURATION = 0.12;   // s: the hardest brake there is
const SHORTEN = 0.85;        // each try at a monotone journey is this much shorter

/**
 * Does the quintic from (0, v0, a0) to (d, 0, 0) over D seconds keep moving toward d? With
 * s = t / D its velocity is (1 - s)^2 g(s), g(s) = c0 + c1 s + c2 s^2.
 */
function monotone(d, v0, a0, D) {
  const k = Math.sign(d);
  const Q = (k * d) / D, V = k * v0, A = k * a0 * D;
  if (V < 0) return true;     // moving away (the visitor reversed): turning is the point
  const c0 = V, c1 = 2 * V + A, c2 = 30 * Q - 15 * V - 2.5 * A;
  const eps = -1e-9 * (Q + V + Math.abs(A) + 1);
  if (c0 + c1 + c2 < eps) return false;
  if (c2 > 0) { const s = -c1 / (2 * c2); if (s > 0 && s < 1 && c0 - (c1 * c1) / (4 * c2) < eps) return false; }
  return true;
}

export class Mover {
  constructor(value = 0) {
    this.value = value;
    this.target = value;
    this.velocity = 0;
    this.acceleration = 0;
    this.t = 0;
    this.duration = 0;
    this.p0 = value; this.v0 = 0; this.a0 = 0;
  }

  snap(value) {
    this.value = this.target = this.p0 = value;
    this.velocity = this.acceleration = this.v0 = this.a0 = 0;
    this.t = this.duration = 0;
  }

  /** Re-plan toward `target`, to arrive in about `duration` seconds. */
  go(target, duration) {
    this.target = target;
    this.p0 = this.value; this.v0 = this.velocity; this.a0 = this.acceleration;
    const d = target - this.value;
    if (d === 0 && this.v0 === 0 && this.a0 === 0) { this.t = this.duration = 0; return; }
    let D = Math.max(MIN_DURATION, duration);
    if (d !== 0) {
      while (D > MIN_DURATION && !monotone(d, this.v0, this.a0, D)) D = Math.max(MIN_DURATION, D * SHORTEN);
      if (!monotone(d, this.v0, this.a0, D)) {
        this.a0 = 0;
        D = Math.max(MIN_DURATION, duration);
        while (D > MIN_DURATION && !monotone(d, this.v0, 0, D)) D = Math.max(MIN_DURATION, D * SHORTEN);
      }
    }
    this.duration = D;
    this.t = 0;
  }

  step(dt) {
    if (this.resting) return this.value;
    this.t += dt;
    const D = this.duration;
    if (this.t >= D) {
      this.value = this.target; this.velocity = this.acceleration = 0;
      this.t = D;
      return this.value;
    }
    const s = this.t / D, s2 = s * s, s3 = s2 * s, s4 = s3 * s, s5 = s4 * s;
    const { p0, a0 } = this, v = this.v0 * D, a = a0 * D * D, p1 = this.target;
    // Quintic Hermite with the end velocity and acceleration at zero.
    const h0 = 1 - 10 * s3 + 15 * s4 - 6 * s5, h1 = s - 6 * s3 + 8 * s4 - 3 * s5;
    const h2 = 0.5 * s2 - 1.5 * s3 + 1.5 * s4 - 0.5 * s5, h3 = 10 * s3 - 15 * s4 + 6 * s5;
    const d0 = -30 * s2 + 60 * s3 - 30 * s4, d1 = 1 - 18 * s2 + 32 * s3 - 15 * s4;
    const d2 = s - 4.5 * s2 + 6 * s3 - 2.5 * s4, d3 = 30 * s2 - 60 * s3 + 30 * s4;
    const e0 = -60 * s + 180 * s2 - 120 * s3, e1 = -36 * s + 96 * s2 - 60 * s3;
    const e2 = 1 - 9 * s + 18 * s2 - 10 * s3, e3 = 60 * s - 180 * s2 + 120 * s3;
    this.value = p0 * h0 + v * h1 + a * h2 + p1 * h3;
    this.velocity = (p0 * d0 + v * d1 + a * d2 + p1 * d3) / D;
    this.acceleration = (p0 * e0 + v * e1 + a * e2 + p1 * e3) / (D * D);
    return this.value;
  }

  /** Exactly at the target and still. */
  get resting() {
    return this.value === this.target && this.velocity === 0 && this.acceleration === 0;
  }
}
