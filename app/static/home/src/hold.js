// Which faces the light holds. Pure arithmetic (no renderer types), shared by the frame and
// tools/check-pool.mjs.
//
// Red light over lit grey stone reads as rose, a second colour, and no pixel can be both vermilion
// and as luminous as the lit grey (vermilion's own luminance is 0.26, the lit faces 0.4 and 0.67),
// so the two lights never share a face: a face the light holds is lit by it alone, in its colour
// (src/monument.js), and every other face keeps the key's grey, the light only adding to it. The
// choice is made per face, never per pixel, so colour changes only at an edge, and on any one face
// the light rises toward its nearest point and falls away from it: no ring, no rim.
//
// The light holds a face when
//   - it is in front of the face's plane (Lambert's sign, smooth over the light's radius);
//   - it hangs over the face: its foot on the face's plane lies within lanternHold of the face (a
//     side's first step and its corner cube are one plane; a short step lets go before a docked
//     light's foot reaches its neighbour);
//   - it reaches all of the face: at the face's farthest point it gives at least lanternReach of
//     what it gives right under itself resting over a tread, so a held face is deep red at worst
//     and never goes dark where the key would have lit it (a long step, at a few works, keeps its
//     grey and takes the light as a lift). Whether the light resting over a face's own step reaches
//     it is a property of the building at this count, and such a face is let go only once the
//     light no longer reaches it at all (lanternLetGo: leaning out at a door, its corner cube); any
//     other face is taken only while the light reaches it from where it is (a corner cube as the
//     light rounds the corner). So at rest no face sits on a threshold;
// and a step's riser is held with the tread it walls in, while it stands above that tread. Docked
// over a tread's middle the light holds that tread (with its cube) and its back riser and nothing
// else, at every count, at rest and presented: every face wholly held or wholly free
// (tools/check-pool.mjs proves it for n = 3..40). Where the door places the light (leaning in, going
// in) its own step keeps the light until it has gone down below its tread.
import { DIM, SHADING } from './config.js';
import { smoothstep } from './spring.js';
import { falloff, lightFor } from './door.js';

const UNDER = falloff(DIM.hover * DIM.hover);   // what the light gives right under itself, resting over a tread
export const RISER_SEEN = 0.04;   // beams of a riser standing above the tread in front for the light to hold it whole

export function createHold(tribar) {
  const { blocks } = tribar, n = blocks.length, R = SHADING.lightRadius, [h0, h1] = SHADING.lanternHold;
  // The block whose face a step's riser walls in (the next one in the loop, a corner cube at a side's
  // end), and how far the riser stands above that face: a step's rise, or nothing at a corner, where
  // the last step is flush with the cube and only its lift shows its riser.
  const riserOver = (i) => (i + 1) % n;
  const riserHeight = (i, lift) => (blocks[riserOver(i)].step >= 0 ? DIM.rise : 0) + lift[i] - lift[riserOver(i)];
  const [letGo0, letGo1] = SHADING.lanternLetGo, take0 = SHADING.lanternReach, take1 = take0 * 4 / 3;
  // Each block's place in the loop (a corner cube takes its side's first step: they stand together)
  // and the run of its tread plane along its travel.
  const loopOf = new Int32Array(n), runLo = new Float64Array(n), runHi = new Float64Array(n);
  tribar.stations.forEach((st, k) => { loopOf[st.block] = k; });
  blocks.forEach((b, i) => {
    const a = b.travel;
    runLo[i] = b.center[a] - b.half[a]; runHi[i] = b.center[a] + b.half[a];
    if (b.step < 0) loopOf[i] = loopOf[i + 1];
    const pair = b.step < 0 ? i + 1 : b.step === 0 ? i - 1 : -1;
    if (pair >= 0) { const o = blocks[pair]; runLo[i] = Math.min(runLo[i], o.center[a] - o.half[a]); runHi[i] = Math.max(runHi[i], o.center[a] + o.half[a]); }
  });
  const front = new Float64Array(n * 3);
  // Whether the light resting over a block's own step reaches all of each of its faces.
  const reached = new Uint8Array(n * 3), p = [0, 0, 0];
  blocks.forEach((b, i) => {
    lightFor(tribar, loopOf[i], loopOf[i], tribar.gap, p);
    for (let a = 0; a < 3; a++) {
      const h2 = Math.max(p[a] - b.center[a] - b.half[a], R) ** 2;
      let far2 = 0;
      for (let e = 0; e < 3; e++) if (e !== a) far2 += (Math.abs(p[e] - b.center[e]) + b.half[e]) ** 2;
      reached[i * 3 + a] = falloff(h2 + far2) * Math.sqrt(h2 / (h2 + far2)) / UNDER >= SHADING.lanternReach ? 1 : 0;
    }
  });

  return {
    loopOf,
    riserHeight,
    /**
     * @param light  per block (3 each): the light as that block sees it, structure space
     * @param lift   per block: its lift along its tread
     * @param own    out, per block and face (+x, +y, +z; 3 each): how far the light holds it (0..1)
     * @param o      strength: how lit the light is (an unlit light holds nothing); door: the block
     *               whose door places the light, or -1
     */
    solve(light, lift, own, { strength = 1, door = -1 } = {}) {
      for (let i = 0; i < n; i++) {
        const b = blocks[i], L = i * 3;
        let let1 = Math.min(h1, b.half[b.travel] - 0.02), let0 = Math.min(h0, let1 - 0.01);
        if (i === door) { let0 = SHADING.doorPorch + R; let1 = let0 + R; }
        for (let a = 0; a < 3; a++) {
          const up = light[L + a] - b.center[a] - b.half[a] - (a === b.tread ? lift[i] : 0);
          front[L + a] = smoothstep(-R, R, up);
          let out2 = 0, far2 = 0;
          for (let e = 0; e < 3; e++) {
            if (e === a) continue;
            const q = light[L + e], shift = e === b.tread ? lift[i] : 0;
            far2 += Math.max(q - (b.center[e] - b.half[e] + shift), b.center[e] + b.half[e] + shift - q) ** 2;
            const lo = a === b.tread && e === b.travel ? runLo[i] : b.center[e] - b.half[e] + shift;
            const hi = a === b.tread && e === b.travel ? runHi[i] : b.center[e] + b.half[e] + shift;
            const d = Math.max(lo - q, q - hi, 0);
            out2 += d * d;
          }
          const h2 = Math.max(up, R) ** 2, reach = falloff(h2 + far2) * Math.sqrt(h2 / (h2 + far2)) / UNDER;
          own[L + a] = front[L + a] * (1 - smoothstep(let0, let1, Math.sqrt(out2)))
            * (i === door ? 1 : reached[L + a] ? smoothstep(letGo0, letGo1, reach) : smoothstep(take0, take1, reach));
        }
      }
      for (let i = 0; i < n; i++) {
        const b = blocks[i], k = i * 3 + b.travel;
        // A step's riser (its leading face) walls in the face in front of it along its tread: the next
        // step's tread, or, for a side's last step, the next corner cube's face flush with its tread,
        // which the riser stands above only by its lift. A cube's leading face is covered.
        own[k] = b.step >= 0 ? front[k] * own[riserOver(i) * 3 + b.tread] * smoothstep(0, RISER_SEEN, riserHeight(i, lift)) : 0;
      }
      for (let q = 0; q < n * 3; q++) own[q] *= strength;
      return own;
    },
  };
}
