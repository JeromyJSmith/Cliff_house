// Cliff House Lodge (115 Stone Street, Morrison CO): the north front as a Sunlit Elevation (v3; faces about 64 deg, NE, on the county map; owner calls it the north side).
// Engine: Sunlit Elevation from Flat to 3D (Samnang Aing, MIT). Model: this file + kit.js.
//
// GEOMETRY SOURCE (v3): the property Gaussian splat itself, full-property-original.sog, rendered orthographically by
// the reality viewer (apps/reality-viewer/scripts/render_ortho_lodge.ts). Views and their exact pixel mappings:
//   /Volumes/MARPA/_New_APP/data/projects/cliff-house/05_presentation/sunlit-elevation-2026-11-20/splat-views/
//     lodge-north-front-facade.png  (60 px/m, image x = along the front, image y = height)  <- every dimension below
//     lodge-plan-top.png     (50 px/m)  hip roof, ridge parallel to the north front, block 18.6 x 10.2 m
//     overview-top-80m.png   (20 px/m)  where the lodge frame was traced
// Splat scale is not independently verified; the front reads 18.6 m against the 18.87 m county footprint edge
// (-1.5 %), and the same splat gives Stone Street 9.9 x 6.3 m as its interior scan does. Read every figure +/-2 %,
// plus about +/-0.1 m for picking edges in the render.
// APPEARANCE: IMG_0949 t118-t128 (building-names-evidence/cmp_0949_E.jpg), drone 030 nadir frames, the owner's
// viewer screenshots of the same splat (2026-11-20 19:49-19:50).
// v1-v2.2 modelled the wrong face (the east end) from a footprint edge; superseded.
import { createStage, run, THREE, span, ease, smooth, lerp, CONVENTION, mulberry, mergeGeometries } from './engine/elevation.js';
import { kit } from './kit.js';

const S = createStage({ hatch: 0.11, hatchPhone: 0.12, drawSpan: [0, 9], wipe: [-14, 26], soft: 1.2 });
const { add, box, mat, lines, root } = S;
const K = kit(S);

const RENDER = [0x8e5446, 0x8a5143, 0x925847];   // smooth terracotta render on the west part (owner photo 2026-11-20; splat)
const ROCK = [0xb4836c, 0xa67460, 0xbe9078, 0x9c6a57, 0xc6a084];  // rusticated sandstone, pink-tan (owner photo)   // red rusticated, with a few buff blocks
const WHITE = 0xece4d2, MINT = 0x5f7a66, SLATE = 0x7b7d80, CREST = 0x9a99a3, ROOF = 0x5a4a3e;

// all from lodge-east-facade.png: x = (px - 335) / 60 m along the front from its east end, y = (790 - py) / 60 m
const L = 18.6, XA = 11.0, DEPTH = 10.2;          // whole front, start of the ashlar section, block depth (plan)
const EAVE_R = 6.1, CORN_A = 6.5, STR = 3.1, RIDGE = 8.8, PED_APEX = 7.5;
const block = new THREE.Group(); root.add(block);

/* ---------- east part (left): three bays of rusticated red sandstone ---------- */
const rOpen = [
  [2.65, 0.5, 3.45, 2.5], [5.7, 0.5, 6.5, 2.5], [8.75, 0.0, 9.6, 2.5],          // window, window, glazed door
  [2.65, 3.75, 3.45, 5.75], [5.7, 3.75, 6.5, 5.75], [8.75, 3.75, 9.6, 5.75],
];
K.wall(block, 0, XA, 0, EAVE_R, rOpen, { tints: ROCK, course: 0.5, block: 0.95, rough: 0.08, seed: 1889 });
rOpen.forEach((o, i) => {
  if (i !== 2) K.sash(block, ...o, { frame: MINT });
  K.slab(block, o[0] - 0.1, o[3], -0.1, o[2] + 0.1, o[3] + 0.2, 0.06, 'stone', WHITE, 0.7);   // white lintel
  if (i !== 2) K.slab(block, o[0] - 0.08, o[1] - 0.1, -0.1, o[2] + 0.08, o[1], 0.07, 'stone', WHITE, 0.6); // sill
});
add(box(8.8, 0.0, -0.3, 9.55, 2.45, -0.24), mat('wood', { color: 0x6e7f6a }), 0.7, { parent: block });
add(box(8.95, 1.3, -0.24, 9.4, 2.3, -0.22), mat('glass'), 0.4, { parent: block, cast: false });
// buff corner blocks at the south corner (owner screenshots)
for (let i = 0, y = 0; y < EAVE_R - 0.2; i++, y += 0.5) add(box(-0.02, y + 0.01, -0.5, i % 2 ? 0.5 : 0.9, y + 0.49, 0.03), mat('stone', { color: 0xc9a77e }), 0.4, { parent: block });
K.slab(block, -0.15, EAVE_R - 0.1, -0.5, XA, EAVE_R + 0.12, 0.18, 'wood', 0xe8e4da, 1.0);   // eave fascia

/* ---------- west part (right, toward the mountain): three bays of smooth ashlar with white trim and the central pediment ---------- */
const aOpen = [
  [11.83, 0.0, 12.75, 2.45],                                                      // entrance (transom above)
  [14.08, 0.5, 15.08, 2.5], [16.28, 0.5, 17.28, 2.5],
  [11.83, 3.75, 12.83, 5.83], [14.08, 3.75, 15.08, 5.83], [16.28, 3.75, 17.28, 5.83],
];
K.wall(block, XA, L, 0, CORN_A - 0.3, aOpen, { tints: RENDER, kind: 'plaster', course: 3.2, block: 30, seed: 1873 });
aOpen.slice(1).forEach((o) => K.sash(block, ...o, { frame: MINT }));
[[XA - 0.05, XA + 0.28], [L - 0.3, L + 0.05]].forEach(([a, b]) => K.slab(block, a, 0, -0.5, b, CORN_A - 0.3, 0.07, 'stone', WHITE, 1.0)); // pilasters
K.slab(block, XA, STR, -0.5, L, STR + 0.18, 0.08, 'stone', WHITE, 1.0);                        // string course
K.slab(block, XA - 0.1, CORN_A - 0.3, -0.5, L + 0.15, CORN_A, 0.25, 'wood', SLATE, 1.1);          // cornice (grey, owner photo)
{ const br = []; for (let x = XA + 0.2; x < L - 0.1; x += 0.6) br.push(box(x, CORN_A - 0.5, 0.15, x + 0.12, CORN_A - 0.3, 0.25)); add(mergeGeometries(br), mat('wood', { color: SLATE }), 0.4, { parent: block }); }
aOpen.forEach(([x0, y0, x1, y1], i) => {
  const t = 0.13, z = 0.05, sm = mat('stone', { color: WHITE });
  add(box(x0 - t, y0 - (i ? 0.12 : 0), -0.05, x0, y1, z), sm, 0.6, { parent: block });
  add(box(x1, y0 - (i ? 0.12 : 0), -0.05, x1 + t, y1, z), sm, 0.6, { parent: block });
  add(box(x0 - t - 0.09, y1, -0.05, x1 + t + 0.09, y1 + 0.22, z + 0.02), sm, 0.7, { parent: block });
  if (i) add(box(x0 - 0.06, y0 - 0.12, -0.05, x1 + 0.06, y0, z + 0.04), sm, 0.6, { parent: block });
  const cx = (x0 + x1) / 2, sh = new THREE.Shape([[cx - 0.15, y1 + 0.22], [cx + 0.15, y1 + 0.22], [cx + 0.11, y1 + 0.46], [cx - 0.11, y1 + 0.46]].map((p) => new THREE.Vector2(...p)));
  add(new THREE.ExtrudeGeometry(sh, { depth: 0.06, bevelEnabled: false }).translate(0, 0, z - 0.02), mat('stone', { color: CREST }), 0.6, { parent: block });
});
const pz = -0.25;
const doorPivot = new THREE.Group(); doorPivot.position.set(aOpen[0][0] + 0.05, 0, pz); block.add(doorPivot);
add(box(0, 0.0, -0.06, 0.82, 2.05, 0), mat('wood', { color: 0x4a2f22 }), 0.8, { parent: doorPivot });
add(new THREE.PlaneGeometry(0.9, 0.34).translate((aOpen[0][0] + aOpen[0][2]) / 2, 2.25, pz - 0.04), mat('glass'), 0, { parent: block, cast: false });
add(box(aOpen[0][0], 2.05, pz - 0.06, aOpen[0][2], 2.1, pz), mat('wood', { color: MINT }), 0.5, { parent: block });
add(box(aOpen[0][0] + 0.03, 0.0, -6, aOpen[0][2] - 0.03, 2.4, pz - 0.08), mat('interior', { realOnly: true }), 0, { parent: block, cast: false });
K.slab(block, 13.0, 1.05, 0, 13.75, 1.7, 0.05, 'steel', 0x3a3326, 0.7);                        // historic-site plaque
{ // central pediment: 12.4..17.4 m, base 6.5, apex 7.5 (about 21 deg)
  const P0 = 12.4, P1 = 17.4, PB = CORN_A, PR = PED_APEX - CORN_A;
  const tri = (inset, z0, z1, color, kind, lw) => {
    const s = new THREE.Shape([[P0 + inset, PB], [P1 - inset, PB], [(P0 + P1) / 2, PB + PR * (1 - 2 * inset / (P1 - P0))]].map((p) => new THREE.Vector2(...p)));
    add(new THREE.ExtrudeGeometry(s, { depth: z1 - z0, bevelEnabled: false }).translate(0, 0, z0), mat(kind, { color }), lw, { parent: block });
  };
  tri(-0.2, 0.1, 0.3, SLATE, 'wood', 1.0);
  tri(0.05, 0.14, 0.32, 0x8c8d90, 'wood', 0.6);
  tri(0.3, 0.1, 0.34, 0x8a8794, 'plaster', 0.8);   // grey tympanum (owner photo; IMG_0949 reads lilac in its light)
  const dn = []; for (let x = P0 + 0.45; x < P1 - 0.45; x += 0.22) dn.push(box(x, PB + 0.02, 0.31, x + 0.1, PB + 0.13, 0.36));
  add(mergeGeometries(dn), mat('wood', { color: 0x6f6d78 }), 0.3, { parent: block });
}

/* ---------- one hip roof over the whole block, ridge parallel to the front (lodge-plan-top.png) ---------- */
K.hipX(block, 0, L, -DEPTH, -0.2, EAVE_R + 0.1, RIDGE, DEPTH / 2 - 0.2, L - DEPTH / 2 + 0.2, { color: ROOF, over: 0.25 });
[[17.85, -1.6, 8.2], [10.0, -5.1, 9.4]].forEach(([x, z, top]) => K.slab(block, x - 0.3, EAVE_R, z - 0.3, x + 0.3, top, z + 0.3, 'brick', 0x9a4b38, 0.9)); // brick chimneys
[[1.75, 8.6], [10.0, 9.0]].forEach(([x, top]) => K.slab(block, x - 0.05, RIDGE - 0.3, -DEPTH / 2 - 0.05, x + 0.05, top, -DEPTH / 2 + 0.05, 'steel', 0x5a5a5a, 0.4)); // vent pipes
add(box(0, 0, -DEPTH, L, EAVE_R, -0.5), mat('plain', { color: 0xd8cfc0 }), 0, { parent: block });

/* ---------- west: the low dark annex behind the board fence; east: a low shed and fence ---------- */
const north = new THREE.Group(); north.position.set(0, 0, -1.2); root.add(north);
K.slab(north, L, 0, -7, L + 6.5, 2.5, 0, 'plaster', 0x5f4e55, 1.0);
K.hip(north, L, L + 6.5, 2.5, 0.8, -7, 0, { color: ROOF, over: 0.35 });
K.slats(root, L + 0.4, L + 7.5, 0, 1.8, 0.9, { color: 0x8a4a33, spacing: 0.15, w: 0.14, t: 0.025, lw: 0.4 });
K.slats(root, -6.5, -0.4, 0, 1.6, 0.4, { color: 0x7d4a35, spacing: 0.15, w: 0.14, t: 0.025, lw: 0.4 });

/* ---------- site ---------- */
S.street(-30, 45);
S.tree(L + 1.2, 2.2, 3.0, 1.3);      // the juniper by the entrance (t124)
S.tree(L + 8.5, -9, 11, 2.8);        // pine to the west
S.tree(-7.5, -3, 10, 3.2);           // bare cottonwoods to the east
{
  const R = mulberry(115), hills = [];
  for (let i = 0; i < 70; i++) {
    const x = -40 + R() * 100, h = 10 + R() * 18;
    hills.push(new THREE.DodecahedronGeometry(6 + R() * 6, 0).scale(1.8, h / 10, 1).translate(x, h * 0.3, -70 - R() * 25));
  }
  add(mergeGeometries(hills), mat('stone', { color: 0x8d8063, realOnly: true }), 0, { cast: false });
  const segs = []; let py = 22;
  for (let x = -40; x < 60; x += 1.5) { const y = 20 + 6 * Math.sin(x * 0.07) + 2 * Math.sin(x * 0.31); segs.push(x, py, -60, x + 1.5, y, -60); py = y; }
  lines(segs, 0.7);
}
S.figure(13.5, 1.6, 1, true);
S.aimSun(9, 4, 30);

const pins = document.getElementById('pins');
[[0, '±0.00', 'Grade at the wall'], [STR, '+3.10', 'String course (prov.)'], [EAVE_R, '+6.10', 'Eave, rusticated (prov.)'], [CORN_A, '+6.50', 'Cornice (prov.)'], [PED_APEX, '+7.50', 'Pediment apex (prov.)'], [RIDGE, '+8.80', 'Hip ridge (ODM-checked)']]
  .forEach(([y, a, b]) => {
    const el = pins.appendChild(document.createElement('div'));
    el.className = 'lv'; el.innerHTML = `<em></em><i></i><b>${a}</b><span>${b}</span>`;
    S.pin(el, [-0.5, y, 0.6]);
  });

const KEYS = [
  { p: 0, t: [8.6, 4.6, 0], fh: 13.6, fov: 2, phone: { t: [14.9, 4.6, 0], minW: 9.5 } },
  { p: 18, t: [8.6, 4.6, 0], fh: 13.6, fov: 2, phone: { t: [14.9, 4.6, 0], minW: 9.5 } },
  { p: 115, t: [9.3, 4.4, 0], fh: 13.0, fov: 16, yaw: -16, pitch: -5, phone: { t: [14.9, 4.4, 0], minW: 9.5 } },
  { p: 228, t: [10.0, 4.2, 0], fh: 12.4, fov: 22, yaw: 14, pitch: -6, phone: { t: [14.9, 4.2, 0], minW: 9.5 } },
  { p: 300, t: [14.9, 6.9, 0], fh: 3.6, fov: 30, yaw: -8, pitch: -4 },
  { p: 360, t: [5.5, 3.2, 0], fh: 6.5, fov: 34, yaw: 20, pitch: -3 },
  { p: 430, t: [12.3, 1.6, 0], fh: 4.2, fov: 44, yaw: 8, pitch: -2 },
  { p: 500, t: [12.3, 1.3, 0], fh: 3.2, fov: 50, yaw: 2, pitch: -2 },
];

const LATE = new THREE.Vector3(-1.5, 0.52, 0.8).normalize();
const sunDir = new THREE.Vector3(), warm = new THREE.Color(0xffcf96), white = new THREE.Color(0xfff1dc);

run(S, {
  length: 520,
  heroOut: [14, 70],
  radar: { ox: 0, zones: [{ id: 'site', label: 'SITE', tag: 'GRADE ±0.00M', at: 95, u0: -4, u1: 0 }] },
  frame(p) {
    S.setCam(S.camAt(p, KEYS));
    S.U.uDepthCue.value = span(p, 22, 90) * (1 - span(p, 150, 205));
    const u = span(p, 118, 212);
    S.U.uSweep.value.z = u <= 0 ? -60 : u >= 1 ? 60 : lerp(-16, 30, smooth(u));
    const m = ease(span(p, 226, 300));
    sunDir.copy(CONVENTION).lerp(LATE, m).normalize();
    S.setSun(sunDir);
    S.sun.color.copy(white).lerp(warm, m);
    S.sun.intensity = lerp(3.4, 3.1, m);
    S.hemi.intensity = lerp(0.52, 0.46, m);
    doorPivot.rotation.y = smooth(span(p, 430, 495)) * 1.35;
  },
  beats: [
    { from: 72, to: 128, html: '<span class="n">01 &nbsp;·&nbsp; One front, two stones</span><p>18.6 metres under one hip roof: three bays of rusticated red sandstone, then three of smooth ashlar framed in white.</p>' },
    { from: 140, to: 222, html: '<span class="n">02 &nbsp;·&nbsp; The stone</span><p>Every shadow was hatched at 45 degrees. So is <em>this</em> sun. The ink turns into the sandstone, white trim and mint sashes of the splat and the photos.</p>' },
    { from: 236, to: 300, html: '<span class="n">03 &nbsp;·&nbsp; Late afternoon, Morrison</span><p>The sun drops toward the plains, and the shadows slide across the coursing.</p>' },
    { from: 300, to: 360, html: '<span class="n">04 &nbsp;·&nbsp; The pediment</span><p>A small central pediment over the ashlar bays: a grey tympanum with a carved scroll, under a grey cornice.</p><div class="row"><div><span>Source</span>Splat (provisional)</div><div><span>Span</span>5.0 m</div><div><span>Apex</span>7.5 m</div></div>' },
    { from: 362, to: 428, html: '<span class="n">05 &nbsp;·&nbsp; c. 1873</span><p>Morrison&rsquo;s house per the NPS register and Morrison History (assessor records say 1934; one archive catalog says 1864). Local sandstone, tall 2-over-2 <em>sashes.</em></p><div class="row"><div><span>Front</span>18.6 m</div><div><span>Ridge</span>8.8 m</div><div><span>Built</span>c. 1873 (conflicts)</div></div>' },
    { from: 440, to: 540, html: '<span class="n">06 &nbsp;·&nbsp; Cliff House Lodge</span><p>The entrance with its historic-site plaque, at 115 Stone Street. Across the yard is the <em>Stone Street Cottage.</em></p><a class="pill solid" href="../stone-street/">Stone Street Cottage</a>' },
  ],
});
// arched head over the entrance (owner photo): white semicircular surround and a dark fanlight
{
  const [x0, , x1, y1] = aOpen[0], cx = (x0 + x1) / 2, r = (x1 - x0) / 2;
  const outer = new THREE.Shape(); outer.absarc(cx, y1, r + 0.16, 0, Math.PI, false); outer.lineTo(cx + r + 0.16, y1);
  const hole = new THREE.Path(); hole.absarc(cx, y1, r, 0, Math.PI, false); hole.lineTo(cx + r, y1); outer.holes.push(hole);
  add(new THREE.ExtrudeGeometry(outer, { depth: 0.1, bevelEnabled: false, curveSegments: 24 }).translate(0, 0, -0.04), mat('stone', { color: WHITE }), 0.6, { parent: block });
  const fan = new THREE.Shape(); fan.absarc(cx, y1, r, 0, Math.PI, false); fan.lineTo(cx + r, y1);
  add(new THREE.ShapeGeometry(fan, 24).translate(0, 0, 0.03), mat('steel', { color: 0x2e2a26 }), 0.4, { parent: block, cast: false });
}
