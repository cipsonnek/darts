// Three-dimensional board (three.js): the sisal face is a canvas texture drawn from the
// served geometry, wires are real metal, and every detected dart flies in and sticks where
// the engine located it. Coordinates are board millimetres (x right, y up, z towards the
// player), exactly as in the API.

import { useEffect, useRef } from "react";
import * as THREE from "three";
import { DEFAULT_BOARD, polarToXY } from "@/lib/board";
import type { BoardInfo } from "@/lib/types";
import type { BoardMarker } from "./Dartboard";

interface Props {
  board?: BoardInfo;
  markers?: BoardMarker[];
  highlight?: string[];
  className?: string;
  /** Camera tilt and pointer parallax; off for small thumbnails. */
  interactive?: boolean;
}

const COLORS = { black: "#1c1a19", white: "#eadcbc", red: "#c8223a", green: "#13804a", surround: "#111010", number: "#f4efe6" };
const TEX = 2048;

function cssVar(name: string, fallback: string): string {
  const v = getComputedStyle(document.documentElement).getPropertyValue(name).trim();
  return v || fallback;
}

function hash(s: string): number {
  let h = 2166136261;
  for (let i = 0; i < s.length; i++) h = Math.imul(h ^ s.charCodeAt(i), 16777619);
  return (h >>> 0) / 4294967295;
}

/** The face: sectors, rings and the number ring, with everything outside `highlight` dimmed. */
function drawFace(ctx: CanvasRenderingContext2D, b: BoardInfo, highlight: Set<string>) {
  const R = b.board_radius_mm;
  const k = TEX / 2 / R;
  const c = TEX / 2;
  const rr = b.radii_mm;
  const half = b.sector_angle_deg / 2;
  const rad = (deg: number) => ((deg - 90) * Math.PI) / 180; // clockwise from up → canvas angle
  ctx.clearRect(0, 0, TEX, TEX);
  ctx.fillStyle = COLORS.surround;
  ctx.beginPath();
  ctx.arc(c, c, R * k, 0, Math.PI * 2);
  ctx.fill();

  const ring = (r0: number, r1: number, a0: number, a1: number, fill: string, label: string) => {
    ctx.beginPath();
    ctx.arc(c, c, r1 * k, rad(a0), rad(a1));
    ctx.arc(c, c, r0 * k, rad(a1), rad(a0), true);
    ctx.closePath();
    ctx.fillStyle = fill;
    ctx.globalAlpha = highlight.size && !highlight.has(label) ? 0.5 : 1;
    ctx.fill();
    ctx.globalAlpha = 1;
  };
  b.sector_order.forEach((sector, i) => {
    const a0 = i * b.sector_angle_deg - half;
    const a1 = a0 + b.sector_angle_deg;
    const even = i % 2 === 0;
    const single = even ? COLORS.black : COLORS.white;
    const col = even ? COLORS.red : COLORS.green;
    ring(rr.outer_bull, rr.triple_inner, a0, a1, single, `S${sector}`);
    ring(rr.triple_inner, rr.triple_outer, a0, a1, col, `T${sector}`);
    ring(rr.triple_outer, rr.double_inner, a0, a1, single, `S${sector}`);
    ring(rr.double_inner, rr.double_outer, a0, a1, col, `D${sector}`);
  });
  const disc = (r: number, fill: string, label: string) => {
    ctx.beginPath();
    ctx.arc(c, c, r * k, 0, Math.PI * 2);
    ctx.fillStyle = fill;
    ctx.globalAlpha = highlight.size && !highlight.has(label) ? 0.5 : 1;
    ctx.fill();
    ctx.globalAlpha = 1;
  };
  disc(rr.outer_bull, COLORS.green, "25");
  disc(rr.inner_bull, COLORS.red, "BULL");

  // Highlighted fields glow so a checkout route reads from across the room.
  if (highlight.size) {
    ctx.save();
    ctx.globalCompositeOperation = "lighter";
    ctx.shadowColor = "rgba(255,180,60,0.9)";
    ctx.shadowBlur = 40;
    ctx.globalAlpha = 0.22;
    b.sector_order.forEach((sector, i) => {
      const a0 = i * b.sector_angle_deg - half;
      const a1 = a0 + b.sector_angle_deg;
      if (highlight.has(`T${sector}`)) ring(rr.triple_inner, rr.triple_outer, a0, a1, "#ffb020", "*");
      if (highlight.has(`D${sector}`)) ring(rr.double_inner, rr.double_outer, a0, a1, "#ffb020", "*");
      if (highlight.has(`S${sector}`)) ring(rr.outer_bull, rr.double_inner, a0, a1, "#ffb020", "*");
    });
    ctx.restore();
  }

  // Numbers on the surround.
  ctx.fillStyle = COLORS.number;
  ctx.font = `800 ${Math.round(30 * k)}px "Barlow Condensed", "Inter Variable", sans-serif`;
  ctx.textAlign = "center";
  ctx.textBaseline = "middle";
  b.sector_order.forEach((s, i) => {
    const [x, y] = polarToXY((rr.double_outer + R) / 2 + 2, i * b.sector_angle_deg);
    ctx.fillText(String(s), c + x * k, c - y * k);
  });
}

/** Fine noise used as a bump map: the fibres of a sisal board. */
function sisalBump(): THREE.CanvasTexture {
  const n = 512;
  const cv = document.createElement("canvas");
  cv.width = cv.height = n;
  const ctx = cv.getContext("2d")!;
  const img = ctx.createImageData(n, n);
  for (let i = 0; i < n * n; i++) {
    const v = 110 + Math.random() * 145;
    img.data[i * 4] = img.data[i * 4 + 1] = img.data[i * 4 + 2] = v;
    img.data[i * 4 + 3] = 255;
  }
  ctx.putImageData(img, 0, 0);
  const t = new THREE.CanvasTexture(cv);
  t.wrapS = t.wrapT = THREE.RepeatWrapping;
  t.repeat.set(6, 6);
  return t;
}

/** A steel-tip dart pointing along -z (tip at the origin, flights towards the player). */
function makeDart(flightColor: string): THREE.Group {
  const g = new THREE.Group();
  const steel = new THREE.MeshStandardMaterial({ color: "#d9dde3", metalness: 1, roughness: 0.25 });
  const tungsten = new THREE.MeshStandardMaterial({ color: "#5d6168", metalness: 0.95, roughness: 0.38 });
  const shaftMat = new THREE.MeshStandardMaterial({ color: "#151515", metalness: 0.2, roughness: 0.5 });
  const flightMat = new THREE.MeshStandardMaterial({ color: flightColor, roughness: 0.45, metalness: 0.1, side: THREE.DoubleSide });
  const along = (geo: THREE.BufferGeometry, mat: THREE.Material, z: number) => {
    const m = new THREE.Mesh(geo, mat);
    m.rotation.x = Math.PI / 2; // cylinders are built along y
    m.position.z = z;
    m.castShadow = true;
    g.add(m);
    return m;
  };
  // the tip is partly inside the board
  along(new THREE.CylinderGeometry(1.1, 0.25, 26, 10), steel, 5);
  along(new THREE.CylinderGeometry(3.4, 3.0, 46, 20), tungsten, 41);
  for (let i = 0; i < 5; i++) along(new THREE.TorusGeometry(3.25, 0.35, 6, 20), steel, 24 + i * 8).rotation.x = 0;
  along(new THREE.CylinderGeometry(2.7, 1.7, 8, 16), tungsten, 68);
  along(new THREE.CylinderGeometry(1.7, 1.9, 40, 12), shaftMat, 90);
  // flights: four kites in an X
  const shape = new THREE.Shape();
  shape.moveTo(0, 0);
  shape.lineTo(17, 6);
  shape.lineTo(19, 34);
  shape.lineTo(0, 40);
  shape.closePath();
  const kite = new THREE.ShapeGeometry(shape);
  for (let i = 0; i < 4; i++) {
    const f = new THREE.Mesh(kite, flightMat);
    f.castShadow = true;
    f.userData.flight = true;
    const holder = new THREE.Group();
    f.rotation.x = Math.PI / 2; // kite y → +z
    holder.add(f);
    holder.rotation.z = (i * Math.PI) / 2 + Math.PI / 4;
    holder.position.z = 92;
    g.add(holder);
  }
  return g;
}

interface DartObj {
  group: THREE.Group;
  born: number;
  tilt: THREE.Euler;
  ghost: boolean;
  mats: THREE.MeshStandardMaterial[];
  flights: THREE.MeshStandardMaterial[];
  color: string;
}

export default function Board3D({ board = DEFAULT_BOARD, markers = [], highlight = [], className, interactive = true }: Props) {
  const host = useRef<HTMLDivElement>(null);
  const api = useRef<{
    setMarkers: (m: BoardMarker[]) => void;
    setHighlight: (h: string[]) => void;
  } | null>(null);

  useEffect(() => {
    const el = host.current!;
    const reduced = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    const renderer = new THREE.WebGLRenderer({ antialias: true, alpha: true, powerPreference: "high-performance" });
    renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2));
    renderer.toneMapping = THREE.ACESFilmicToneMapping;
    renderer.toneMappingExposure = 1.05;
    renderer.shadowMap.enabled = true;
    renderer.shadowMap.type = THREE.PCFSoftShadowMap;
    el.appendChild(renderer.domElement);
    renderer.domElement.style.display = "block";

    const scene = new THREE.Scene();
    const camera = new THREE.PerspectiveCamera(30, 1, 10, 5000);

    // light: warm key from the upper left, cool fill, an ember rim from behind
    scene.add(new THREE.HemisphereLight("#fff4e8", "#2a1610", 1.1));
    const key = new THREE.DirectionalLight("#fff1df", 2.3);
    key.position.set(-380, 520, 900);
    key.castShadow = true;
    key.shadow.mapSize.set(2048, 2048);
    Object.assign(key.shadow.camera, { left: -260, right: 260, top: 260, bottom: -260, near: 200, far: 2200 });
    key.shadow.bias = -0.0004;
    key.shadow.radius = 4;
    scene.add(key);
    const rim = new THREE.PointLight(cssVar("--accent", "#ff5a1f"), 2.5, 0, 0);
    rim.position.set(420, -320, 160);
    scene.add(rim);

    const R = board.board_radius_mm;
    const rr = board.radii_mm;
    const root = new THREE.Group();
    scene.add(root);

    // the board: a thick sisal cylinder with a printed face and a dark rim
    const cv = document.createElement("canvas");
    cv.width = cv.height = TEX;
    const ctx = cv.getContext("2d")!;
    let hl = new Set<string>();
    drawFace(ctx, board, hl);
    const faceTex = new THREE.CanvasTexture(cv);
    faceTex.colorSpace = THREE.SRGBColorSpace;
    faceTex.anisotropy = renderer.capabilities.getMaxAnisotropy();
    const bump = sisalBump();
    const face = new THREE.Mesh(new THREE.CircleGeometry(R, 128),
      new THREE.MeshStandardMaterial({ map: faceTex, roughness: 0.92, metalness: 0, bumpMap: bump, bumpScale: 0.5 }));
    face.receiveShadow = true;
    root.add(face);
    const side = new THREE.Mesh(new THREE.CylinderGeometry(R, R * 1.01, 38, 128, 1, true),
      new THREE.MeshStandardMaterial({ color: "#0c0b0b", roughness: 0.7, metalness: 0.2 }));
    side.rotation.x = Math.PI / 2;
    side.position.z = -19;
    root.add(side);
    const backGlow = new THREE.Mesh(new THREE.CircleGeometry(R * 1.35, 64), new THREE.MeshBasicMaterial({
      map: (() => {
        const g = document.createElement("canvas");
        g.width = g.height = 256;
        const c2 = g.getContext("2d")!;
        const grad = c2.createRadialGradient(128, 128, 60, 128, 128, 128);
        grad.addColorStop(0, "rgba(0,0,0,0.85)");
        grad.addColorStop(1, "rgba(0,0,0,0)");
        c2.fillStyle = grad;
        c2.fillRect(0, 0, 256, 256);
        return new THREE.CanvasTexture(g);
      })(),
      transparent: true, depthWrite: false,
    }));
    backGlow.position.set(18, -26, -60);
    root.add(backGlow);

    // wires: rings and spokes in polished steel, slightly proud of the face
    const wire = new THREE.MeshStandardMaterial({ color: "#c9ccd2", metalness: 1, roughness: 0.28 });
    const wr = Math.max(board.wire_width_mm * 0.5, 0.45);
    for (const r of [rr.inner_bull, rr.outer_bull, rr.triple_inner, rr.triple_outer, rr.double_inner, rr.double_outer]) {
      const t = new THREE.Mesh(new THREE.TorusGeometry(r, wr, 8, 160), wire);
      t.position.z = wr * 0.6;
      t.castShadow = true;
      root.add(t);
    }
    const spokeLen = rr.double_outer - rr.outer_bull;
    const spokeGeo = new THREE.CylinderGeometry(wr * 0.85, wr * 0.85, spokeLen, 6);
    board.sector_order.forEach((_, i) => {
      const a = ((i * board.sector_angle_deg + board.sector_angle_deg / 2) * Math.PI) / 180;
      const mid = rr.outer_bull + spokeLen / 2;
      const s = new THREE.Mesh(spokeGeo, wire);
      s.position.set(mid * Math.sin(a), mid * Math.cos(a), wr * 0.6);
      s.rotation.z = -a;
      s.castShadow = true;
      root.add(s);
    });
    // number ring
    const numRing = new THREE.Mesh(new THREE.TorusGeometry((rr.double_outer + R) / 2 + 22, 1.1, 8, 160), wire);
    numRing.position.z = 1;
    root.add(numRing);

    // ---------------------------------------------------------------- darts
    const darts = new Map<string, DartObj>();
    const accent = cssVar("--accent", "#ff5a1f");
    const warn = cssVar("--warn", "#fbbf24");
    let firstSync = true;

    function setMarkers(ms: BoardMarker[]) {
      const now = performance.now();
      const seen = new Set<string>();
      for (const m of ms) {
        seen.add(m.id);
        let d = darts.get(m.id);
        if (!d) {
          const group = makeDart(m.color ?? (m.uncertain ? warn : accent));
          const h = hash(m.id);
          // darts land a little off-axis, tails slightly up (they arrive on a falling arc)
          const tilt = new THREE.Euler(-0.08 - h * 0.14, (h - 0.5) * 0.22, h * Math.PI * 2, "XYZ");
          group.position.set(m.x_mm, m.y_mm, 0);
          group.rotation.copy(tilt);
          const mats: THREE.MeshStandardMaterial[] = [];
          const flights: THREE.MeshStandardMaterial[] = [];
          group.traverse((o) => {
            const mesh = o as THREE.Mesh;
            if (mesh.isMesh) {
              const mat = (mesh.material as THREE.MeshStandardMaterial).clone();
              mesh.material = mat;
              mats.push(mat);
              if (mesh.userData.flight) flights.push(mat);
            }
          });
          root.add(group);
          // darts already in the board when the view opens appear without flying in
          d = { group, born: firstSync || reduced ? -1e9 : now, tilt, ghost: false, mats, flights, color: "" };
          darts.set(m.id, d);
        }
        d.group.position.x = m.x_mm;
        d.group.position.y = m.y_mm;
        const ghost = !!m.ghost;
        if (ghost !== d.ghost) {
          d.ghost = ghost;
          for (const mat of d.mats) {
            mat.transparent = ghost;
            mat.opacity = ghost ? 0.3 : 1;
          }
        }
        const col = m.color ?? (m.uncertain ? warn : accent);
        if (col !== d.color) {
          d.color = col;
          d.flights.forEach((f) => f.color.set(col));
        }
      }
      for (const [id, d] of darts) {
        if (!seen.has(id)) {
          root.remove(d.group);
          d.group.traverse((o) => (o as THREE.Mesh).geometry?.dispose());
          d.mats.forEach((m) => m.dispose());
          darts.delete(id);
        }
      }
      firstSync = false;
    }

    function setHighlight(h: string[]) {
      hl = new Set(h);
      drawFace(ctx, board, hl);
      faceTex.needsUpdate = true;
    }
    api.current = { setMarkers, setHighlight };
    // redraw once the display font is ready so the numbers use it
    document.fonts?.ready.then(() => { drawFace(ctx, board, hl); faceTex.needsUpdate = true; }).catch(() => {});

    // ---------------------------------------------------------------- sizing, pointer, loop
    const resize = () => {
      const w = el.clientWidth || 1;
      const h = el.clientHeight || w;
      renderer.setSize(w, h, false);
      renderer.domElement.style.width = "100%";
      renderer.domElement.style.height = "100%";
      camera.aspect = w / h;
      // keep the whole board in view whatever the aspect
      const need = (R * 1.18) / Math.tan((camera.fov * Math.PI) / 360);
      const dist = camera.aspect < 1 ? need / camera.aspect : need;
      camera.position.set(0, interactive ? -dist * 0.12 : 0, dist);
      camera.lookAt(0, 0, 0);
      camera.updateProjectionMatrix();
    };
    const ro = new ResizeObserver(resize);
    ro.observe(el);
    resize();

    const target = { x: 0, y: 0 };
    const onMove = (e: PointerEvent) => {
      if (!interactive || reduced) return;
      const r = el.getBoundingClientRect();
      target.y = ((e.clientX - r.left) / r.width - 0.5) * 0.28;
      target.x = ((e.clientY - r.top) / r.height - 0.5) * 0.2;
    };
    const onLeave = () => { target.x = 0; target.y = 0; };
    window.addEventListener("pointermove", onMove);
    el.addEventListener("pointerleave", onLeave);

    let raf = 0;
    let last = 0;
    const FLY = 320;
    const tick = (t: number) => {
      raf = requestAnimationFrame(tick);
      let animating = false;
      for (const d of darts.values()) if (t - d.born < FLY + 900) animating = true;
      // 60 fps while something moves, ~24 fps otherwise (the board PC also runs the cameras)
      if (!animating && t - last < 42) return;
      last = t;
      const sway = interactive && !reduced ? Math.sin(t / 2600) * 0.025 : 0;
      root.rotation.x += ((interactive ? -0.16 : 0) + target.x - root.rotation.x) * 0.06;
      // seen a little from the right so darts show their length
      root.rotation.y += ((interactive ? -0.2 : 0) + target.y + sway - root.rotation.y) * 0.06;
      for (const d of darts.values()) {
        const age = t - d.born;
        if (age < FLY) {
          const p = age / FLY;
          const e = 1 - Math.pow(1 - p, 3);
          d.group.position.z = (1 - e) * 900;
          d.group.rotation.set(d.tilt.x - (1 - e) * 0.25, d.tilt.y, d.tilt.z + (1 - e) * 3);
        } else if (age < FLY + 900) {
          const w = (age - FLY) / 900;
          const wobble = Math.sin(w * 26) * 0.07 * (1 - w) * (1 - w);
          d.group.position.z = 0;
          d.group.rotation.set(d.tilt.x + wobble, d.tilt.y + wobble * 0.6, d.tilt.z);
        } else if (d.group.position.z !== 0) {
          d.group.position.z = 0;
          d.group.rotation.copy(d.tilt);
        }
      }
      renderer.render(scene, camera);
    };
    raf = requestAnimationFrame(tick);

    return () => {
      cancelAnimationFrame(raf);
      ro.disconnect();
      window.removeEventListener("pointermove", onMove);
      el.removeEventListener("pointerleave", onLeave);
      api.current = null;
      scene.traverse((o) => {
        const mesh = o as THREE.Mesh;
        mesh.geometry?.dispose();
        const mat = mesh.material as THREE.Material | THREE.Material[] | undefined;
        (Array.isArray(mat) ? mat : mat ? [mat] : []).forEach((m) => m.dispose());
      });
      faceTex.dispose();
      bump.dispose();
      renderer.dispose();
      renderer.domElement.remove();
    };
  }, [board, interactive]);

  useEffect(() => { api.current?.setMarkers(markers); }, [markers, board, interactive]);
  const hlKey = highlight.join(",");
  // eslint-disable-next-line react-hooks/exhaustive-deps
  useEffect(() => { api.current?.setHighlight(highlight); }, [hlKey, board, interactive]);

  return <div ref={host} className={className} style={{ width: "100%", height: "100%" }} role="img" aria-label="Tarcza 3D" />;
}
