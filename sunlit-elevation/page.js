// Cliff House, Morrison, Colorado, as a Sunlit Elevation.
// Built on the Sunlit Elevation engine from Flat to 3D (Samnang Aing, MIT).
//
// Sources for the massing (see docs/reconnaissance-20261111/BRIEF.md in the main branch):
//  - George P. Morrison's 1873 residence: three storeys of local sandstone, French casement windows,
//    alternating red and buff sandstone in the original section.
//  - East wing added 1889: red sandstone with buff corner quoins.
// Dimensions, openings and roof form are SCHEMATIC. They are not yet taken from the measured
// LiDAR/photogrammetry baseline and must be replaced once that baseline is accepted.
import { createStage, run, THREE, span, ease, smooth, lerp, CONVENTION, mulberry } from './engine/elevation.js';

const S = createStage({ hatch: 0.11, hatchPhone: 0.12, drawSpan: [0, 13.5], wipe: [-14, 14], soft: 1.2 });
const { add, box, mat, lines, root } = S;

const RED = 0xa4583f, BUFF = 0xd9c39a, RED2 = 0x98503a;
const T = 0.55; // wall thickness

// A coursed sandstone wall built course by course around its openings, so the colour banding is real geometry.
// holes: [x0, y0, x1, y1]. colorOf(courseIndex) picks the stone colour.
function stoneWall(g, x0, x1, y0, y1, holes, courseH, colorOf, outline = true) {
  const byColor = new Map();
  for (let c = 0, y = y0; y < y1 - 1e-6; c++, y += courseH) {
    const ya = y, yb = Math.min(y1, y + courseH);
    let segs = [[x0, x1]];
    holes.forEach(([hx0, hy0, hx1, hy1]) => {
      if (hy1 <= ya + 1e-6 || hy0 >= yb - 1e-6) return;
      segs = segs.flatMap(([a, b]) => {
        const out = [];
        if (hx0 > a) out.push([a, Math.min(b, hx0)]);
        if (hx1 < b) out.push([Math.max(a, hx1), b]);
        return out.filter(([p, q]) => q - p > 1e-4);
      });
    });
    const col = colorOf(c);
    if (!byColor.has(col)) byColor.set(col, []);
    segs.forEach(([a, b]) => byColor.get(col).push(box(a, ya, -T, b, yb, 0)));
  }
  byColor.forEach((geos, col) => add(mergeGeometries(geos), mat('stone', { color: col }), 0, { parent: g }));
  if (outline) {
    const segs = [x0, y0, 0, x1, y0, 0, x1, y0, 0, x1, y1, 0, x1, y1, 0, x0, y1, 0, x0, y1, 0, x0, y0, 0];
    holes.forEach(([a, b, c, d]) => segs.push(a, b, 0, c, b, 0, c, b, 0, c, d, 0, c, d, 0, a, d, 0, a, d, 0, a, b, 0));
    lines(segs, 1.4, { parent: g, drawOnly: false });
  }
}
import { mergeGeometries } from 'three/addons/utils/BufferGeometryUtils.js';

// A French casement: two tall leaves, a transom light, a sandstone sill and lintel.
function casement(g, x0, y0, x1, y1, o = {}) {
  const fw = 0.07, z1 = -0.16, z0 = z1 - 0.07, fm = mat('wood', { color: 0xe9e2d2 });
  const fr = new THREE.Shape(); fr.moveTo(x0, y0); fr.lineTo(x1, y0); fr.lineTo(x1, y1); fr.lineTo(x0, y1); fr.closePath();
  const h = new THREE.Path(); h.moveTo(x0 + fw, y0 + fw); h.lineTo(x0 + fw, y1 - fw); h.lineTo(x1 - fw, y1 - fw); h.lineTo(x1 - fw, y0 + fw); h.closePath();
  fr.holes.push(h);
  add(new THREE.ExtrudeGeometry(fr, { depth: z1 - z0, bevelEnabled: false }).translate(0, 0, z0), fm, 0.7, { parent: g });
  const mx = (x0 + x1) / 2, tr = y1 - (y1 - y0) * 0.2;
  add(box(mx - 0.03, y0 + fw, z0, mx + 0.03, tr, z1), fm, 0.6, { parent: g });
  add(box(x0 + fw, tr - 0.03, z0, x1 - fw, tr + 0.03, z1), fm, 0.6, { parent: g });
  add(new THREE.PlaneGeometry(x1 - x0 - 0.04, y1 - y0 - 0.04).translate(mx, (y0 + y1) / 2, z0 + 0.02), mat('glass'), 0, { parent: g, cast: false });
  // reveals
  const st = mat('stone', { color: o.trim || BUFF });
  add(box(x0 - 0.02, y0 - 0.1, -T + 0.05, x1 + 0.02, y0, 0.07), st, 0.9, { parent: g });   // sill
  add(box(x0 - 0.12, y1, -T + 0.05, x1 + 0.12, y1 + 0.26, 0.04), st, 0.9, { parent: g });  // lintel
  add(box(x0, y0, -T, x0 + 0.02, y1, z0), mat('plaster'), 0, { parent: g, cast: false });
  add(box(x1 - 0.02, y0, -T, x1, y1, z0), mat('plaster'), 0, { parent: g, cast: false });
}

// A gable roof seen from the eave side, running back into the hill.
function gable(g, x0, x1, eave, ridge, z0, z1, color = 0x5c524a) {
  const s = new THREE.Shape([[x0 - 0.35, eave], [x1 + 0.35, eave], [(x0 + x1) / 2, ridge]].map((p) => new THREE.Vector2(...p)));
  add(new THREE.ExtrudeGeometry(s, { depth: z1 - z0, bevelEnabled: false }).translate(0, 0, z0), mat('plain', { color }), 1.4, { parent: g });
  add(box(x0 - 0.4, eave - 0.18, z0, x1 + 0.4, eave, z1 + 0.05), mat('wood', { color: 0xe6dfcf }), 0.8, { parent: g }); // fascia
}

const house = new THREE.Group(); root.add(house);

/* ---------- 1873: the original three-storey block ---------- */
const OX0 = 0, OX1 = 10.4, OEAVE = 9.9;
const doorH = [4.55, 0.75, 5.85, 3.55];
const oHoles = [
  doorH,
  [1.25, 1.25, 2.45, 3.35], [7.95, 1.25, 9.15, 3.35],
  [1.25, 4.35, 2.45, 6.55], [4.6, 4.35, 5.8, 6.55], [7.95, 4.35, 9.15, 6.55],
  [1.25, 7.45, 2.45, 9.15], [4.6, 7.45, 5.8, 9.15], [7.95, 7.45, 9.15, 9.15],
];
stoneWall(house, OX0, OX1, 0, OEAVE, oHoles, 0.33, (c) => (Math.floor(c / 2) % 2 ? BUFF : RED));
oHoles.slice(1).forEach((h) => casement(house, ...h));
add(box(OX0, 0, -11, OX1, OEAVE, -T), mat('plain', { color: 0xd8cfc0 }), 0, { parent: house }); // body
add(box(OX0 - 0.12, 0, -T, OX1 + 0.12, 0.75, 0.1), mat('stone', { color: RED2 }), 1.2, { parent: house }); // plinth
[3.65, 6.75].forEach((y) => add(box(OX0 - 0.06, y, -T, OX1 + 0.06, y + 0.14, 0.07), mat('stone', { color: BUFF }), 0.9, { parent: house })); // string courses
add(box(OX0 - 0.2, OEAVE - 0.05, -T, OX1 + 0.2, OEAVE + 0.2, 0.18), mat('stone', { color: BUFF }), 1.1, { parent: house }); // cornice
gable(house, OX0, OX1, OEAVE + 0.2, 13.2, -11.2, 0.25);
[[1.4, 2.3], [8.1, 9.0]].forEach(([a, b]) => add(box(a, 11.0, -6.2, b, 14.4, -5.3), mat('stone', { color: RED }), 1.1, { parent: house })); // chimneys

// front door: a panelled leaf on a pivot, with a transom light, behind three sandstone steps
const pz = -0.3;
const doorPivot = new THREE.Group(); doorPivot.position.set(doorH[0] + 0.06, 0, pz); house.add(doorPivot);
add(box(0, 0.75, -0.07, doorH[2] - doorH[0] - 0.12, 2.95, 0), mat('wood', { color: 0x5b3a26 }), 0.8, { parent: doorPivot });
add(box(0.15, 1.9, 0.0, doorH[2] - doorH[0] - 0.27, 2.75, 0.02), mat('wood', { color: 0x6b4630 }), 0.5, { parent: doorPivot });
add(box(0.15, 0.95, 0.0, doorH[2] - doorH[0] - 0.27, 1.75, 0.02), mat('wood', { color: 0x6b4630 }), 0.5, { parent: doorPivot });
add(new THREE.PlaneGeometry(doorH[2] - doorH[0] - 0.1, 0.5).translate((doorH[0] + doorH[2]) / 2, 3.25, pz - 0.05), mat('glass'), 0, { parent: house, cast: false });
add(box(doorH[0], 2.98, pz - 0.08, doorH[2], 3.04, pz), mat('wood', { color: 0xe9e2d2 }), 0.6, { parent: house });
add(box(doorH[0] - 0.25, 3.55, -T + 0.05, doorH[2] + 0.25, 3.9, 0.06), mat('stone', { color: BUFF }), 1.0, { parent: house }); // door lintel
add(box(doorH[0] + 0.05, 0.75, -6, doorH[2] - 0.05, 3.4, pz - 0.1), mat('interior', { realOnly: true }), 0, { parent: house, cast: false }); // warm hall
const stepShape = new THREE.Shape([[0, 0], [0.9, 0], [0.9, 0.25], [0.6, 0.25], [0.6, 0.5], [0.3, 0.5], [0.3, 0.75], [0, 0.75]].map((p) => new THREE.Vector2(...p)));
add(new THREE.ExtrudeGeometry(stepShape, { depth: 2.2, bevelEnabled: false }).rotateY(-Math.PI / 2).translate(doorH[2] + 0.4, 0, 0), mat('stone', { color: BUFF }), 1.0, { parent: house });

/* ---------- 1889: the east wing, red stone with buff quoins ---------- */
const wing = new THREE.Group(); wing.position.set(0, 0, -0.9); root.add(wing);
const WX0 = 10.4, WX1 = 18.2, WEAVE = 7.0;
const wHoles = [[11.6, 1.25, 12.8, 3.35], [15.8, 1.25, 17.0, 3.35], [11.6, 4.2, 12.8, 6.25], [15.8, 4.2, 17.0, 6.25], [13.7, 1.25, 14.9, 3.35], [13.7, 4.2, 14.9, 6.25]];
stoneWall(wing, WX0, WX1, 0, WEAVE, wHoles, 0.3, (c) => (c % 3 === 1 ? RED2 : RED));
wHoles.forEach((h) => casement(wing, ...h, { trim: BUFF }));
add(box(WX0, 0, -9, WX1, WEAVE, -T), mat('plain', { color: 0xd8cfc0 }), 0, { parent: wing });
add(box(WX0, 0, -T, WX1 + 0.1, 0.6, 0.08), mat('stone', { color: RED2 }), 1.1, { parent: wing });
for (let i = 0, y = 0.6; y < WEAVE - 0.1; i++, y += 0.36) { // quoins: alternate long and short at the east corner
  const L = i % 2 ? 0.45 : 0.85;
  add(box(WX1 - L, y + 0.01, -T, WX1 + 0.04, y + 0.35, 0.035), mat('stone', { color: BUFF }), 0.6, { parent: wing });
}
add(box(WX0, WEAVE - 0.05, -T, WX1 + 0.2, WEAVE + 0.18, 0.15), mat('stone', { color: BUFF }), 1.0, { parent: wing });
gable(wing, WX0 - 0.3, WX1, WEAVE + 0.18, 9.6, -9.2, 0.2, 0x564c45);

/* ---------- the site: the hogback rocks behind, cottonwoods, a figure ---------- */
{
  const R = mulberry(1873), rocks = [];
  for (let i = 0; i < 90; i++) {
    const x = -22 + R() * 66, h = 6 + R() * 16 * (1 - Math.abs(x - 9) / 40);
    rocks.push(new THREE.DodecahedronGeometry(2.4 + R() * 3.5, 0).scale(1.4, h / 5, 1).translate(x, h * 0.45 - 1, -30 - R() * 16));
  }
  add(mergeGeometries(rocks), mat('stone', { color: 0x9c5a44, realOnly: true }), 0, { cast: true });
  const ridge = []; // the ridge line, drawn
  for (let i = 0; i <= 60; i++) { const x = -22 + i * 1.1; ridge.push([x, 13 + 7 * Math.sin(i * 0.23) * Math.exp(-((x - 9) ** 2) / 900) + 2 * Math.sin(i * 1.3)]); }
  const segs = []; for (let i = 0; i < ridge.length - 1; i++) segs.push(ridge[i][0], ridge[i][1], -28, ridge[i + 1][0], ridge[i + 1][1], -28);
  lines(segs, 0.8);
}
S.street(-26, 44);
S.tree(-4.5, 1.6, 9.5, 3.0);
S.tree(22.5, 0.8, 8.5, 2.6);
S.figure(7.2, 2.0, 1, true);
S.aimSun(8, 6, 28);

// levels, on the sheet only
const pins = document.getElementById('pins');
[[0, '±0.00', 'Grade'], [0.75, '+0.75', 'Ground floor'], [3.8, '+3.80', 'First floor'], [6.9, '+6.90', 'Second floor'], [9.9, '+9.90', 'Eave, 1873'], [7.0, '+7.00', 'Eave, 1889 wing']]
  .forEach(([y, a, b], i) => {
    const el = pins.appendChild(document.createElement('div'));
    el.className = 'lv'; el.innerHTML = `<em></em><i></i><b>${a}</b><span>${b}</span>`;
    S.pin(el, i === 5 ? [WX1 + 0.4, y, -0.6] : [-0.6, y, 0.5]);
  });

const KEYS = [
  { p: 0, t: [9.1, 7.2, 0], fh: 17.5, fov: 2, phone: { t: [9.1, 7.6, 0], minW: 22 } },
  { p: 18, t: [9.1, 7.2, 0], fh: 17.5, fov: 2, phone: { t: [9.1, 7.6, 0], minW: 22 } },
  { p: 115, t: [9.4, 6.4, 0], fh: 16.5, fov: 16, yaw: -14, pitch: -5, phone: { minW: 22 } },
  { p: 228, t: [9.0, 6.0, 0], fh: 15.5, fov: 20, yaw: 12, pitch: -6, phone: { minW: 20 } },
  { p: 300, t: [16.6, 3.6, 0], fh: 6.0, fov: 30, yaw: -32, pitch: -4 },
  { p: 360, t: [7.0, 4.0, 0], fh: 7.0, fov: 30, yaw: 18, pitch: -4 },
  { p: 430, t: [5.2, 2.6, 0], fh: 6.0, fov: 40, yaw: 6, pitch: -3 },
  { p: 500, t: [5.2, 2.2, 0], fh: 4.6, fov: 46, yaw: 2, pitch: -3 },
];

const LATE = new THREE.Vector3(-1.6, 0.5, 0.75).normalize(); // a late-afternoon sun, low over the plains
const sunDir = new THREE.Vector3();
const warm = new THREE.Color(0xffcf96), white = new THREE.Color(0xfff1dc);

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
    { from: 72, to: 128, html: '<span class="n">01 &nbsp;·&nbsp; Relief</span><p>The east wing stands back from the 1873 block. Sills, lintels and string courses stand out. The drawing already said so.</p>' },
    { from: 140, to: 222, html: '<span class="n">02 &nbsp;·&nbsp; The stone</span><p>Every shadow was hatched at 45 degrees. So is <em>this</em> sun. The ink turns into local sandstone, red and buff in alternating courses.</p>' },
    { from: 236, to: 300, html: '<span class="n">03 &nbsp;·&nbsp; Late afternoon, Morrison</span><p>The sun drops toward the plains, and the shadows slide across the coursing.</p>' },
    { from: 300, to: 360, html: '<span class="n">04 &nbsp;·&nbsp; 1889</span><p>The east wing: red sandstone, tied together at the corner with buff <em>quoins.</em></p><div class="row"><div><span>Added</span>1889</div><div><span>Walls</span>Red sandstone</div><div><span>Corners</span>Buff quoins</div></div>' },
    { from: 362, to: 428, html: '<span class="n">05 &nbsp;·&nbsp; 1873</span><p>George P. Morrison built his house from the stone of the valley he founded the town in. Three storeys, French <em>casements.</em></p><div class="row"><div><span>Built</span>1873</div><div><span>Storeys</span>3</div><div><span>Stone</span>Red &amp; buff</div></div>' },
    { from: 440, to: 540, html: '<span class="n">06 &nbsp;·&nbsp; Cliff House</span><p>After 1895 it became a rooming house, and today it is a lodge at 115 Stone Street. Next, this schematic is replaced by the <em>measured scan.</em></p><a class="pill solid" href="../">Open the splat</a>' },
  ],
});
