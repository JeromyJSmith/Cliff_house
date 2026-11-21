// Cliff House Lodge (115 Stone Street, Morrison CO): the stone gable front as a Sunlit Elevation.
// Engine: Sunlit Elevation from Flat to 3D (Samnang Aing, MIT). Model: this file + kit.js.
//
// EVIDENCE (every element is from these; see README.md for the full table):
//  F1  IMG_0949 t118-t128 s (owner's grounds walk), contact sheet
//      /Volumes/MARPA/_New_APP/data/projects/cliff-house/03_bim/site-model/building-names-evidence/cmp_0949_E.jpg
//      -> gable front: 3 bays x 2 storeys, 2-over-2 sashes in mint frames, white eared surrounds with
//         lilac crest panels, white string course and corner pilasters, pediment with mint/lilac trim,
//         entrance + historic-site plaque in the left bay; rock-faced red wing to the left; low dark
//         shingled wing and redwood board fence to the right.
//  F2  drone 030 nadir frames 06045, 06182, 06286, 06615, 06729 (frames_2400_100fov)
//      -> salmon/buff mottled ashlar, buff quoins, white flat stone lintels, mint sashes, brown shingle
//         roof, red brick parapet, glazed timber roof monitor (the sunroom; not on this elevation).
//  F3  /Users/jero/Documents/cliffhouse2.mp4 (dusk aerial orbit) -> massing, brick chimneys, low roofs.
//  F4  footprint: cliff-house-site-v2.site-plan.json building 5, edge 6 = 9.30 m (SAM 3 trace of the
//      2024 county aerial, EPSG:32613). Used as the gable width. +/-0.3 m, and the assignment of this
//      edge to the photographed gable is MEDIUM confidence (orientation from F1 shadows + F3).
//  HEIGHTS: not measured in 3D yet. Eave 7.2 m and the opening sizes are read off F1 t124 as
//      proportions of the 9.30 m width (+/-10 %, perspective from a low camera). Replace with the
//      metric flight-030 splat when it lands.
import { createStage, run, THREE, span, ease, smooth, lerp, CONVENTION, mulberry, mergeGeometries } from './engine/elevation.js';
import { kit } from './kit.js';

const S = createStage({ hatch: 0.11, hatchPhone: 0.12, drawSpan: [0, 10], wipe: [-16, 14], soft: 1.2 });
const { add, box, mat, lines, root } = S;
const K = kit(S);

const ASHLAR = [0xc9907a, 0xc28a74, 0xcf9a82, 0xbf8670, 0xd3a588]; // salmon with a little buff (F1, F2)
const ROCK = [0xa65a43, 0x9a5240, 0xb06248, 0x8f4b3a];             // rock-faced red wing (F1 left)
const WHITE = 0xf1ede4, MINT = 0x8fb3a0, LILAC = 0xa995c4, ROOF = 0x4a3c36;

const W = 9.3, EAVE = 7.2, RISE = 2.2, STR = 3.75; // F4 width; heights from F1 proportions
const lodge = new THREE.Group(); root.add(lodge);

/* ---------- the gable front (F1 t122, t124) ---------- */
const bays = [1.75, 4.65, 7.55], ww = 1.0;
const door = [bays[0] - 0.55, 0.45, bays[0] + 0.55, 3.25];
const openings = [door,
  [bays[1] - ww / 2, 0.95, bays[1] + ww / 2, 3.05], [bays[2] - ww / 2, 0.95, bays[2] + ww / 2, 3.05],
  ...bays.map((b) => [b - ww / 2, 4.45, b + ww / 2, 6.55])];
K.wall(lodge, 0, W, 0.45, EAVE, openings, { tints: ASHLAR, course: 0.48, block: 1.05, seed: 1873 });
K.wall(lodge, -0.05, W + 0.05, 0, 0.45, [[door[0], 0, door[2], 0.45]], { tints: ROCK, course: 0.45, block: 0.8, rough: 0.04, T: 0.6, outline: false }); // plinth
openings.slice(1).forEach((o) => K.sash(lodge, ...o, { frame: MINT }));
// white trim: corner pilasters, string course, eave cornice (F1)
[[-0.08, 0.32], [W - 0.32, W + 0.08]].forEach(([a, b]) => K.slab(lodge, a, 0.45, -0.5, b, EAVE, 0.07, 'stone', WHITE, 1.0));
K.slab(lodge, -0.08, STR, -0.5, W + 0.08, STR + 0.2, 0.08, 'stone', WHITE, 1.0);
K.slab(lodge, -0.25, EAVE - 0.05, -0.5, W + 0.25, EAVE + 0.22, 0.2, 'stone', WHITE, 1.1);
// eared surrounds with crest panels (F1: every opening)
openings.forEach(([x0, y0, x1, y1], i) => {
  const t = 0.13, z = 0.05, sm = mat('stone', { color: WHITE });
  add(box(x0 - t, y0 - (i ? 0.12 : 0), -0.05, x0, y1, z), sm, 0.6, { parent: lodge });
  add(box(x1, y0 - (i ? 0.12 : 0), -0.05, x1 + t, y1, z), sm, 0.6, { parent: lodge });
  add(box(x0 - t - 0.09, y1, -0.05, x1 + t + 0.09, y1 + 0.24, z + 0.02), sm, 0.7, { parent: lodge }); // ears + head
  if (i) add(box(x0 - 0.06, y0 - 0.12, -0.05, x1 + 0.06, y0, z + 0.04), sm, 0.6, { parent: lodge }); // sill
  const cx = (x0 + x1) / 2, sh = new THREE.Shape([[cx - 0.16, y1 + 0.24], [cx + 0.16, y1 + 0.24], [cx + 0.12, y1 + 0.5], [cx - 0.12, y1 + 0.5]].map((p) => new THREE.Vector2(...p)));
  add(new THREE.ExtrudeGeometry(sh, { depth: 0.06, bevelEnabled: false }).translate(0, 0, z - 0.02), mat('plaster', { color: LILAC }), 0.6, { parent: lodge });
});
// the entrance: dark door leaf on a pivot, transom, the historic-site plaque (F1 t122)
const pz = -0.25;
const doorPivot = new THREE.Group(); doorPivot.position.set(door[0] + 0.05, 0, pz); lodge.add(doorPivot);
add(box(0, 0.45, -0.06, 1.0, 2.75, 0), mat('wood', { color: 0x3c4a46 }), 0.8, { parent: doorPivot });
add(box(0.12, 1.55, 0.0, 0.88, 2.6, 0.02), mat('glass'), 0.4, { parent: doorPivot, cast: false });
add(box(door[0], 2.75, pz - 0.06, door[2], 2.82, pz), mat('wood', { color: MINT }), 0.5, { parent: lodge });
add(new THREE.PlaneGeometry(1.0, 0.38).translate(bays[0], 3.03, pz - 0.04), mat('glass'), 0, { parent: lodge, cast: false });
add(box(door[0] + 0.03, 0.45, -6, door[2] - 0.03, 3.2, pz - 0.08), mat('interior', { realOnly: true }), 0, { parent: lodge, cast: false });
K.slab(lodge, 2.75, 1.45, 0, 3.55, 2.15, 0.05, 'steel', 0x3a3326, 0.7); // plaque
K.slab(lodge, door[0] - 0.2, 0, 0, door[2] + 0.2, 0.45, 0.9, 'stone', 0xb98e74, 0.9); // landing
// Flat mint cornice across the whole front, and a small CENTRAL pediment over the middle bay
// (F1 t124, corrected after review): lilac tympanum with a dentil band, framed in mint and white.
// Pitch ~20 deg: rake slopes in t124 are 0.58 (left) and 0.17 (right) of run because the camera is
// turned; their mean 0.37 -> 20 deg. Span ~6.0 m (about 2.1 bay spacings of 2.9 m), rise ~1.1 m.
K.slab(lodge, -0.3, EAVE + 0.22, -0.5, W + 0.3, EAVE + 0.5, 0.3, 'wood', MINT, 1.1);           // cornice
{ const br = []; for (let x = 0.2; x < W - 0.1; x += 0.6) br.push(box(x, EAVE + 0.02, 0.2, x + 0.12, EAVE + 0.22, 0.3)); add(mergeGeometries(br), mat('wood', { color: MINT }), 0.4, { parent: lodge }); } // brackets
const PW = 6.0, PR = 1.1, PB = EAVE + 0.5, PX0 = W / 2 - PW / 2;
{
  const tri = (inset, z0, z1, color, kind = 'stone', lw = 1.0) => {
    const s = new THREE.Shape([[PX0 + inset, PB], [PX0 + PW - inset, PB], [W / 2, PB + PR * (1 - 2 * inset / PW)]].map((p) => new THREE.Vector2(...p)));
    add(new THREE.ExtrudeGeometry(s, { depth: z1 - z0, bevelEnabled: false }).translate(0, 0, z0), mat(kind, { color }), lw, { parent: lodge });
  };
  tri(-0.25, 0.1, 0.32, MINT, 'wood', 1.0);      // mint raking cornice
  tri(0.05, 0.14, 0.34, WHITE, 'stone', 0.6);    // white bed moulding
  tri(0.35, 0.1, 0.36, LILAC, 'plaster', 0.8);   // lilac tympanum
  const dn = []; for (let x = PX0 + 0.5; x < PX0 + PW - 0.5; x += 0.22) dn.push(box(x, PB + 0.02, 0.33, x + 0.1, PB + 0.14, 0.38));
  add(mergeGeometries(dn), mat('wood', { color: 0x6c5a86 }), 0.3, { parent: lodge }); // dentils
}
K.hip(lodge, 0, W, EAVE + 0.4, 2.0, -19, -0.2, { color: ROOF, over: 0.1 }); // main shingled roof behind (F3; pitch NOT measured)
[[2.0, -5], [7.3, -12]].forEach(([x, z]) => K.slab(lodge, x - 0.35, EAVE + 0.5, z - 0.35, x + 0.35, EAVE + 3.2, z + 0.35, 'brick', 0x9a4b38, 0.9)); // brick chimneys (F3)
add(box(0, 0, -19, W, EAVE, -0.5), mat('plain', { color: 0xd8cfc0 }), 0, { parent: lodge });

/* ---------- left: the rock-faced red sandstone wing (F1 t122 left edge, F3) ---------- */
const left = new THREE.Group(); left.position.set(0, 0, -1.4); root.add(left);
const LW0 = -6.2, LE = 6.7;
const lOpen = [[-1.75, 0.45, -0.75, 3.0], [-4.5, 0.95, -3.5, 3.0], [-1.75, 4.25, -0.75, 6.2], [-4.5, 4.25, -3.5, 6.2]];
// t122/t124: two storeys of rusticated (rock-faced) red sandstone in large blocks, eave slightly below
// the main front, mint cornice; door with white crested surround on the ground floor, a window over it.
// Its roof is not visible in F1 and only as a dark low roof in F3: drawn as a low hip, UNVERIFIED.
K.wall(left, LW0, 0, 0, LE, lOpen, { tints: ROCK, course: 0.52, block: 0.95, rough: 0.09, seed: 1889 });
K.slab(left, LW0 - 0.2, LE, -0.5, 0.0, LE + 0.25, 0.22, 'wood', MINT, 1.0);
lOpen.forEach((o, i) => { if (i) K.sash(left, ...o, { frame: MINT }); K.slab(left, o[0] - 0.12, o[3], -0.1, o[2] + 0.12, o[3] + 0.22, 0.07, 'stone', WHITE, 0.7); });
add(box(lOpen[0][0], 0.45, -0.3, lOpen[0][2], 2.6, -0.24), mat('wood', { color: 0x3c4a46 }), 0.7, { parent: left });
K.hip(left, LW0, 0, LE, 1.6, -12, 0, { color: ROOF });
add(box(LW0, 0, -12, 0, LE, -0.5), mat('plain', { color: 0xd8cfc0 }), 0, { parent: left });

/* ---------- right: the low dark shingled wing and the board fence (F1 t124-t128) ---------- */
const right = new THREE.Group(); right.position.set(0, 0, -2.2); root.add(right);
K.slab(right, W, 0, -8, W + 9.5, 3.0, 0, 'plaster', 0x6d5a62, 1.0);
K.slab(right, W + 2.2, 2.1, 0, W + 2.8, 2.45, 0.35, 'steel', 0xcfcfcf, 0.6); // window AC unit
K.hip(right, W, W + 9.5, 3.0, 1.2, -8, 0, { color: ROOF, over: 0.45 });
K.slats(root, W + 0.2, W + 10.5, 0, 1.95, 1.6, { color: 0x8a4a33, spacing: 0.15, w: 0.14, t: 0.025, lw: 0.4 });
K.slab(root, W + 0.15, 0, 1.45, W + 0.3, 2.6, 1.62, 'wood', 0x7a4a30, 0.7); // the tall post

/* ---------- site: gravel, the juniper, pines, the hogback behind ---------- */
S.street(-30, 40);
S.tree(W + 0.8, 2.6, 3.0, 1.3);
S.tree(W + 5.5, -9, 10, 2.6);
S.tree(-9.5, 1.0, 8.5, 2.6);
{
  const R = mulberry(115), hills = [];
  for (let i = 0; i < 70; i++) {
    const x = -40 + R() * 90, h = 10 + R() * 18;
    hills.push(new THREE.DodecahedronGeometry(6 + R() * 6, 0).scale(1.8, h / 10, 1).translate(x, h * 0.3, -70 - R() * 25));
  }
  add(mergeGeometries(hills), mat('stone', { color: 0x8d8063, realOnly: true }), 0, { cast: false });
  const segs = []; let py = 22;
  for (let x = -40; x < 50; x += 1.5) { const y = 20 + 6 * Math.sin(x * 0.07) + 2 * Math.sin(x * 0.31); segs.push(x, py, -60, x + 1.5, y, -60); py = y; }
  lines(segs, 0.7);
}
S.figure(3.3, 1.6, 1, true);
S.aimSun(4, 5, 28);

const pins = document.getElementById('pins');
[[0, '±0.00', 'Grade'], [0.45, '+0.45', 'Ground floor (est.)'], [STR, '+3.75', 'String course (est.)'], [EAVE, '+7.20', 'Eave (est.)'], [8.8, '+8.80', 'Pediment apex (est.)']]
  .forEach(([y, a, b]) => {
    const el = pins.appendChild(document.createElement('div'));
    el.className = 'lv'; el.innerHTML = `<em></em><i></i><b>${a}</b><span>${b}</span>`;
    S.pin(el, [-0.4, y, 0.6]);
  });

const KEYS = [
  { p: 0, t: [3.6, 5.6, 0], fh: 13.5, fov: 2, phone: { t: [4.65, 5.6, 0], minW: 12 } },
  { p: 18, t: [3.6, 5.6, 0], fh: 13.5, fov: 2, phone: { t: [4.65, 5.6, 0], minW: 12 } },
  { p: 115, t: [4.0, 5.0, 0], fh: 12.5, fov: 16, yaw: -16, pitch: -5, phone: { minW: 12 } },
  { p: 228, t: [4.4, 4.8, 0], fh: 12.0, fov: 22, yaw: 14, pitch: -6, phone: { minW: 11 } },
  { p: 300, t: [4.65, 8.3, 0], fh: 3.6, fov: 30, yaw: -8, pitch: -4 },
  { p: 360, t: [4.65, 3.6, 0], fh: 5.5, fov: 34, yaw: 20, pitch: -3 },
  { p: 430, t: [1.9, 2.2, 0], fh: 4.4, fov: 44, yaw: 10, pitch: -2 },
  { p: 500, t: [1.8, 1.9, 0], fh: 3.6, fov: 50, yaw: 2, pitch: -2 },
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
    S.U.uSweep.value.z = u <= 0 ? -60 : u >= 1 ? 60 : lerp(-16, 22, smooth(u));
    const m = ease(span(p, 226, 300));
    sunDir.copy(CONVENTION).lerp(LATE, m).normalize();
    S.setSun(sunDir);
    S.sun.color.copy(white).lerp(warm, m);
    S.sun.intensity = lerp(3.4, 3.1, m);
    S.hemi.intensity = lerp(0.52, 0.46, m);
    doorPivot.rotation.y = smooth(span(p, 430, 495)) * 1.35;
  },
  beats: [
    { from: 72, to: 128, html: '<span class="n">01 &nbsp;·&nbsp; Relief</span><p>The pilasters, string course and eared surrounds stand proud of the ashlar. The red rock-faced wing steps back on the left, the low dark wing on the right.</p>' },
    { from: 140, to: 222, html: '<span class="n">02 &nbsp;·&nbsp; The stone</span><p>Every shadow was hatched at 45 degrees. So is <em>this</em> sun. The ink turns into salmon sandstone ashlar, white trim and mint sashes, as photographed.</p>' },
    { from: 236, to: 300, html: '<span class="n">03 &nbsp;·&nbsp; Late afternoon, Morrison</span><p>The sun drops toward the plains, and the shadows slide across the stone.</p>' },
    { from: 300, to: 360, html: '<span class="n">04 &nbsp;·&nbsp; The pediment</span><p>A small central pediment over the middle bay: a lilac tympanum with dentils, framed in white and mint, pitched about 20°.</p><div class="row"><div><span>Source</span>IMG_0949 t124s</div><div><span>Width</span>9.30 m ±0.3</div><div><span>Apex</span>≈8.8 m (est.)</div></div>' },
    { from: 362, to: 428, html: '<span class="n">05 &nbsp;·&nbsp; 1873</span><p>Morrison&rsquo;s 1873 house per the NPS register and Morrison History (assessor records say 1934; one archive catalog says 1864). Three bays, tall 2-over-2 sashes, a crest panel over every <em>opening.</em></p><div class="row"><div><span>Built</span>1873</div><div><span>Wing</span>1889</div><div><span>Stone</span>Local sandstone</div></div>' },
    { from: 440, to: 540, html: '<span class="n">06 &nbsp;·&nbsp; Cliff House Lodge</span><p>After 1895 it became a rooming house, and today it is a lodge at 115 Stone Street. Across the yard is the <em>Stone Street Cottage.</em></p><a class="pill solid" href="../stone-street/">Stone Street Cottage</a>' },
  ],
});
