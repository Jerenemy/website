// Renderer, camera, layout and the chain of spaces:
//
//   structure  --(pivot, true-view basis, roll about the view axis)-->  stage
//   stage      --(tilt about the light's own point, translation)----->  world
//   world      --(fixed orthographic camera looking down -z)--------->  pixels
//
// In stage space the true view axis IS +z. Rolling the monument about z keeps the paradox
// shut (it only turns the picture); tilting about x / y is the one thing that opens it. The
// tilt pivots about the point the light rests on, so however far the seam is torn open the
// light never leaves the dock ring, the leader and the caption that hang on it.
import * as THREE from 'three';
import { LAYOUT, SHADING } from './config.js';
import { IMAGE_RIGHT, IMAGE_UP, VIEW_AXIS, viewDirection } from './tribar.js';

const CAMERA_DISTANCE = 200;

export function createStage(canvas, tribar, { onContextLost, onContextRestored } = {}) {
  const renderer = new THREE.WebGLRenderer({ canvas, antialias: true, alpha: false, stencil: false, powerPreference: 'high-performance' });
  renderer.setClearColor(0x000000, 1);
  // three.js already prevents the default on loss (so the browser may restore) and rebuilds
  // its GL state on restore; programs, buffers and attributes are re-created lazily by the
  // next render. The app only needs to pause meanwhile and give up if restore never comes.
  const lost = () => onContextLost?.();
  const restored = () => onContextRestored?.();
  canvas.addEventListener('webglcontextlost', lost, false);
  canvas.addEventListener('webglcontextrestored', restored, false);
  const scene = new THREE.Scene();
  const camera = new THREE.OrthographicCamera(-1, 1, 1, -1, 1, CAMERA_DISTANCE * 2);
  camera.position.set(0, 0, CAMERA_DISTANCE);
  const rig = new THREE.Group();
  scene.add(rig);

  const layout = {
    width: 1, height: 1, dpr: 1, ppu: 1, portrait: false, restAngle: Math.PI,
    restPx: { x: 0, y: 0 }, rest: { x: 0, y: 0 }, dir: { x: -1, y: 0 },
    capReach: Infinity,   // px: how far left of the light the caption may sit (landscape)
    railEdge: Infinity,   // px: the rail's right edge is at most here (landscape)
  };
  const stageRot = new THREE.Matrix3();  // structure -> stage (rotation part)
  const tiltQuat = new THREE.Quaternion(), untilt = new THREE.Quaternion();
  const euler = new THREE.Euler();
  const o = new THREE.Vector3(), d = new THREE.Vector3(), about = new THREE.Vector3(), turned = new THREE.Vector3();
  const base = new THREE.Vector3();      // the rig's untilted position: where the picture rests
  const view = VIEW_AXIS.slice();        // toward the eye, structure space, tilt included
  const pivot = tribar.pivot;

  /** @param reserve portrait: CSS px the interface needs below the light (at least LAYOUT.tall.below) */
  function resize(reserve = 0) {
    const width = canvas.clientWidth || window.innerWidth, height = canvas.clientHeight || window.innerHeight;
    const dpr = Math.min(window.devicePixelRatio || 1, LAYOUT.maxDpr);
    const portrait = width / height < LAYOUT.portraitBelow;
    const bound = tribar.radius + LAYOUT.roamPad;
    let ppu, restX, restY;
    if (portrait) {
      const L = LAYOUT.tall;
      const top = Math.max(L.topMin, height * L.topFraction);
      ppu = Math.min((width - 2 * L.side) / (2 * bound), (height - top - Math.max(L.below, reserve)) / (tribar.rhoMax + bound));
      restX = Math.round(width / 2);
      restY = Math.round(top + (tribar.rhoMax + bound) * ppu);
      layout.restAngle = L.restAngle;
    } else {
      const L = LAYOUT.wide;
      restX = Math.round(Math.max(width * L.restX, width < L.narrowBelow ? L.restMinXNarrow : L.restMinX));   // never crowd the caption
      restY = Math.round((L.top + height - L.bottom) / 2);
      ppu = Math.min((height - L.top - L.bottom) / (2 * bound), (width - L.right - restX) / (tribar.rhoMax + bound));
      layout.restAngle = L.restAngle;
      layout.capReach = L.capReach;
      layout.railEdge = restX + (tribar.rhoMax + tribar.radius) * ppu + L.railReach;   // the monument's far edge, plus the reach
    }
    Object.assign(layout, { width, height, dpr, ppu, portrait });
    layout.restPx.x = restX; layout.restPx.y = restY;
    layout.rest.x = (restX - width / 2) / ppu; layout.rest.y = (height / 2 - restY) / ppu;
    layout.dir.x = Math.cos(layout.restAngle); layout.dir.y = Math.sin(layout.restAngle);
    renderer.setPixelRatio(dpr);
    renderer.setSize(width, height, false);
    camera.left = -width / (2 * ppu); camera.right = width / (2 * ppu);
    camera.top = height / (2 * ppu); camera.bottom = -height / (2 * ppu);
    camera.updateProjectionMatrix();
    return layout;
  }

  /**
   * @param s       loop position the monument is presenting (it turns so this point rests in place)
   * @param roll    extra rotation about the view axis (intro only)
   * @param anchor  structure-space point the tilt turns about (the light's), or null for the rig origin
   */
  function setPose(s, roll, yaw, pitch, shakeX, shakeY, anchor) {
    const phi = layout.restAngle - tribar.thetaAt(s) + roll;
    viewDirection(phi, yaw, pitch, view);
    const c = Math.cos(phi), n = Math.sin(phi);
    const R = IMAGE_RIGHT, U = IMAGE_UP, A = VIEW_AXIS;
    // rows: Rz(phi) applied to the rows of the true-view basis
    stageRot.set(
      c * R[0] - n * U[0], c * R[1] - n * U[1], c * R[2] - n * U[2],
      n * R[0] + c * U[0], n * R[1] + c * U[1], n * R[2] + c * U[2],
      A[0], A[1], A[2],
    );
    const rho = tribar.rhoAt(s);
    base.set(layout.rest.x - rho * layout.dir.x + shakeX, layout.rest.y - rho * layout.dir.y + shakeY, 0);
    euler.set(pitch, yaw, 0, 'XYZ');
    tiltQuat.setFromEuler(euler);
    untilt.copy(tiltQuat).invert();
    rig.quaternion.copy(tiltQuat);
    // The tilt is a rotation about the rig's origin; moving the rig by what it would do to
    // the anchor makes it a rotation about the anchor instead.
    rig.position.copy(base);
    if (anchor) {
      structToStage(anchor, about);
      turned.copy(about).applyQuaternion(tiltQuat);
      rig.position.add(about).sub(turned);
    }
    rig.updateMatrixWorld(true);
  }

  function structToStage(p, out) {
    return out.set(p[0] - pivot[0], p[1] - pivot[1], p[2] - pivot[2]).applyMatrix3(stageRot);
  }
  function stageToWorld(stage, out) {
    return out.copy(stage).applyQuaternion(tiltQuat).add(rig.position);
  }
  function worldToPx(world, out) {
    out.x = layout.width / 2 + world.x * layout.ppu;
    out.y = layout.height / 2 - world.y * layout.ppu;
    return out;
  }

  // Analytic picking against the blocks themselves, by the rule the shader draws with
  // (src/seam.js pick), so what you can point at is exactly what you see, at any tilt.
  // Picking is done against the UNTILTED pose first: the tilt is a transient the pointer
  // itself causes, and it is bleeding shut while the visitor aims, so the hit test is made
  // where the block is about to be, and a sweep then a click lands where it was aimed. With
  // `tilted` the test is made against the pose as drawn, for the click that comes while the
  // seam is still open: what is visibly under the pointer is a target too.
  const invRot = new THREE.Matrix3(), pivotV = new THREE.Vector3(...pivot);
  /** The line of sight through CSS pixel (px, py), structure space, into o and d (Vector3s). */
  function sight(px, py, tilted, oOut, dOut) {
    invRot.copy(stageRot).transpose();
    oOut.set((px - layout.width / 2) / layout.ppu, (layout.height / 2 - py) / layout.ppu, CAMERA_DISTANCE);
    dOut.set(0, 0, -1);
    if (tilted) { oOut.sub(rig.position).applyQuaternion(untilt); dOut.applyQuaternion(untilt); } else oOut.sub(base);
    oOut.applyMatrix3(invRot).add(pivotV);
    return dOut.applyMatrix3(invRot);
  }
  /** @param seam the seam solved this frame with the same lifts (src/seam.js) */
  function pick(px, py, lift, seam, tilted = false) {
    sight(px, py, tilted, o, d);
    return seam.pick(o.x, o.y, o.z, d.x, d.y, d.z, lift, tilted ? seam.offset : seam.restOffset);
  }

  return {
    renderer, scene, camera, rig, base, layout, stageRot, view,
    resize, setPose, structToStage, stageToWorld, worldToPx, pick, sight,
    /** True while the picture is tilted enough for the drawn and the untilted poses to differ by a pixel. */
    get tilted() { return Math.abs(tiltQuat.x) + Math.abs(tiltQuat.y) > 0.5 / (tribar.radius * layout.ppu); },
    /** Depth-buffer units per beam along the view (the camera is orthographic: depth is linear). */
    depthPerBeam: 1 / (camera.far - camera.near),
    /** Uniform scale of the whole picture about the screen centre (arrival only). */
    setZoom(zoom) {
      if (camera.zoom === zoom) return;
      camera.zoom = zoom;
      camera.updateProjectionMatrix();
    },
    mistRadii(out) { return out.set(SHADING.mistInner * tribar.radius, SHADING.mistOuter * tribar.radius, SHADING.mistFloor); },
    /** CSS pixel position of a structure-space point (test hook and tag placement). */
    project(p, out) { return worldToPx(stageToWorld(structToStage(p, o), d), out); },
    render() { renderer.render(scene, camera); },
    /** Test hooks: drop and recover the GL context through WEBGL_lose_context. */
    loseContext() { renderer.forceContextLoss(); },
    restoreContext() { renderer.forceContextRestore(); },
    dispose() {
      canvas.removeEventListener('webglcontextlost', lost, false);
      canvas.removeEventListener('webglcontextrestored', restored, false);
      renderer.dispose();
    },
  };
}
