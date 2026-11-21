// Stone Street Cottage (Cliff House Lodge, 121 Stone St, Morrison CO; twin building E3 / site building 9):
// the east elevation along Stone Street as a Sunlit Elevation.
// Engine: Sunlit Elevation from Flat to 3D (Samnang Aing, MIT). Model: this file + ../sunlit-elevation/kit.js.
//
// EVIDENCE (handoff: /Volumes/MARPA/_New_APP/data/projects/stone-street/handoff-modeling-2026-11-20/HANDOFF.md)
//  P1  iphone-patio 0001-0010: raised deck on a dry-stone retaining wall, green slat railings, green
//      open-rafter pergola, white sign panel in a green frame at the south end of the deck.
//  P2  iphone-patio 0011-0024: black iron fence along the sidewalk, iron gate, stone steps up, stone
//      pillar and utility pole (tag "10") at the south corner.
//  P3  iphone-patio 0025-0032: teal stucco walls; on the deck: trash cart, kettle grill (no hot tub).
//  P4  iphone-patio 0036-0041 + splat elevation-south: south end, glazed wooden door, window, meter.
//  P5  splat orthographic elevations, /Volumes/MARPA/_New_APP/data/projects/stone-street/02_reality_capture/
//      exterior-splat-ortho/v2/elevation-east.png, elevation-south.png (160 px/m, splat scale NOT
//      independently verified): flat roof parapet ~3.4-3.6 m above the cottage floor with a step about
//      2/3 of the way north; fascia ~3.0 m; pergola beam ~3.0 m; south wall ~6.3 m; brown porch roof
//      continues north; "Hot Tub Cottage" sign beyond it.
//  P6  flight-030-start 0012-0021: roof step, chimney with buckets, Wi-Fi unit, skylight, brown shingle
//      roof against the north edge. Owner: the brown roof is part of the cottage and covers the north
//      entry porch with the hot tub.
//  DIMENSIONS: long side 9.9 m and width 6.3 m (handoff section 4, splat plan; drone ortho 9.5-9.9 x
//      6.1-6.8); roof top 3.53 m above the floor (handoff). Deck depth 2.0 m, retaining wall 1.2 m,
//      porch length 3.9 m, east window sizes: ESTIMATED from P1/P5 (+/-15 %). East windows are partly
//      hidden behind the pergola in every photo: their count/position is LOW confidence.
import { createStage, run, THREE, span, ease, smooth, lerp, CONVENTION, mulberry, mergeGeometries } from '../sunlit-elevation/engine/elevation.js';
import { kit } from '../sunlit-elevation/kit.js';

const S = createStage({ hatch: 0.11, hatchPhone: 0.12, drawSpan: [0, 5], wipe: [-10, 18], soft: 1.2 });
const { add, box, mat, lines, root } = S;
const K = kit(S);

const TEAL = 0x7f9a8f, GREEN = 0x5f7f6c, FASCIA = 0x55433a, SHINGLE = 0x5a4234, STONE = [0xc9b79c, 0xb9a487, 0xd6c6ab, 0xa89377];
const F = 1.0;          // cottage floor above the sidewalk: ODM 030 point cloud parapet 4.55 m above the sidewalk minus the 3.53 m parapet (see README)
const L = 9.9, STEP = 6.6, P_LO = 3.38, P_HI = 3.53; // P5, handoff
const g = new THREE.Group(); g.position.set(0, F, 0); root.add(g);

/* ---------- the teal east wall, flat roof with its step (P3, P5, P6) ---------- */
const win = [[2.3, 0.9, 3.5, 2.1], [4.6, 0.9, 5.6, 2.1]]; // LOW confidence (behind the pergola)
K.slab(g, 0, -F, -6.3, L, 3.0, -0.2, 'plaster', TEAL, 1.3);
win.forEach((w) => { K.slab(g, w[0] - 0.1, w[1] - 0.1, -0.2, w[2] + 0.1, w[3] + 0.1, 0.02, 'plaster', 0xeeeae2, 0.7); K.sash(g, ...w, { frame: 0xf2eee6, recess: -0.1, T: 0.1 }); });
K.slab(g, 0, 3.0, -6.3, STEP, P_LO, 0.0, 'plaster', TEAL, 1.1);
K.slab(g, STEP, 3.0, -6.3, L, P_HI, 0.0, 'plaster', TEAL, 1.1);
K.slab(g, -0.05, 2.92, 0.0, STEP, 3.02, 0.06, 'steel', FASCIA, 0.8);
K.slab(g, -0.05, P_LO, -6.35, STEP, P_LO + 0.06, 0.05, 'steel', FASCIA, 0.8);
K.slab(g, STEP, P_HI, -6.35, L + 0.05, P_HI + 0.06, 0.05, 'steel', FASCIA, 0.8);
K.slab(g, 2.4, P_LO, -3.2, 2.95, P_LO + 0.75, -2.6, 'brick', 0x9a6a55, 0.8);       // old chimney (P6)
K.slab(g, 4.3, P_LO, -2.0, 4.8, P_LO + 0.35, -1.5, 'steel', 0x2a2a2a, 0.6);       // Wi-Fi/vent unit (P6)
K.slab(g, 0.8, P_LO + 0.06, -0.1, 0.9, P_LO + 0.9, 0.0, 'steel', 0x8a8a8a, 0.5);  // mast at the south corner (P5)
// string lights along the north part (P5)
{ const s = []; for (let x = STEP; x < L + 3.8; x += 0.4) s.push(x, 2.75 - 0.08 * Math.sin((x - STEP) * 7.8), 0.4, x + 0.4, 2.75 - 0.08 * Math.sin((x + 0.4 - STEP) * 7.8), 0.4); lines(s, 0.5, { drawOnly: false }); }

/* ---------- the raised deck, dry-stone wall, railings and the green pergola (P1, P3) ---------- */
const D0 = 0.2, D1 = STEP, DZ = 2.0;
K.slab(g, D0, -0.12, 0, D1, 0.0, DZ, 'wood', 0x7d6a55, 0.8);                       // deck boards
{ const gw = new THREE.Group(); gw.position.z = DZ + 0.12; root.add(gw); K.wall(gw, D0 - 0.2, D1 + 0.1, 0, F - 0.12, [], { tints: STONE, course: 0.22, block: 0.5, rough: 0.07, seed: 121, T: 0.4, outline: true }); }
K.slats(g, D0 + 1.95, D1, 0, 1.0, DZ, { color: GREEN, spacing: 0.16, w: 0.09 });
[0.25, 2.35, 4.45, D1 - 0.12].forEach((x) => K.slab(g, x, 0, DZ - 0.16, x + 0.12, 2.95, DZ - 0.04, 'wood', GREEN, 0.7)); // posts
K.slab(g, D0, 2.8, DZ - 0.2, D1, 2.98, DZ, 'wood', GREEN, 0.8);                    // beam (P5 ~3.0 m)
{ const r = []; for (let x = D0 + 0.1; x < D1; x += 0.6) r.push(box(x, 2.98, -0.1, x + 0.06, 3.14, DZ + 0.35)); add(mergeGeometries(r), mat('wood', { color: GREEN }), 0.5, { parent: g }); } // open rafters
K.slab(g, D0 + 0.08, 0.05, DZ + 0.01, D0 + 1.85, 1.5, DZ + 0.05, 'plaster', 0xeeeae2, 0.9); // sign panel, part of the railing at the south corner (P1 0001-0003, 0024-0025)
[[D0, 0.0, D0 + 1.93, 0.08], [D0, 1.47, D0 + 1.93, 1.57], [D0, 0.0, D0 + 0.08, 1.57], [D0 + 1.85, 0.0, D0 + 1.93, 1.57]].forEach(([a, b, c, d]) => K.slab(g, a, b, DZ - 0.02, c, d, DZ + 0.07, 'wood', GREEN, 0.5)); // its green frame
K.slab(g, 3.0, 0, -0.9, 3.7, 1.05, -0.3, 'plain', 0x3b4a45, 0.6);                  // trash cart (P3 0028-0032)

/* ---------- the north entry porch under the brown shingle roof, hot tub (P5, P6, owner) ---------- */
const N1 = L + 3.9;
{
  const s = new THREE.Shape([[0, 2.35], [3.9, 2.35], [3.9, 2.55], [0, 3.15]].map((p) => new THREE.Vector2(...p)));
  const roof = add(new THREE.ExtrudeGeometry(s, { depth: 6.9, bevelEnabled: false }).translate(L, 0, -6.5), mat('plain', { color: SHINGLE }), 1.2, { parent: g });
  [L + 0.1, N1 - 0.25].forEach((x) => K.slab(g, x, 0, 0.1, x + 0.15, 2.35, 0.25, 'wood', 0x6e5a48, 0.7));
  K.slab(g, L, -0.1, -5.5, N1, 0.0, 0.4, 'wood', 0x7d6a55, 0.6);
  K.slab(g, L + 0.9, 0.0, -3.2, L + 3.0, 0.95, -1.1, 'wood', 0x5b4535, 0.8);       // hot tub, brown hinged cover
  add(box(L, 0.0, -6.3, N1, 2.35, -0.6), mat('interior', { realOnly: true, color: 0x4a3a2e }), 0, { parent: g, cast: false });
}
K.slab(root, N1 + 0.8, 0, 2.2, N1 + 1.0, 1.0, 2.3, 'wood', 0x6e5a48, 0.6);
K.slab(root, N1 + 0.3, 1.0, 2.2, N1 + 1.5, 1.75, 2.28, 'plaster', 0xefe8dc, 0.8); // "Hot Tub Cottage" sign (P5)

/* ---------- street edge: iron fence, steps, stone pillar, pole (P2) ---------- */
{
  const bars = [];
  for (let x = -0.6; x < N1 + 2; x += 0.13) if (x < -0.45 || x > 0.6) bars.push(box(x, 0, 2.68, x + 0.02, 1.0, 2.7));
  bars.push(box(-0.6, 0.92, 2.66, N1 + 2, 0.96, 2.72), box(-0.6, 0.1, 2.66, N1 + 2, 0.14, 2.72));
  add(mergeGeometries(bars), mat('steel', { color: 0x1d1d1d }), 0.45, {});
  for (let i = 0; i < 5; i++) add(box(-0.4, i * 0.2, 2.7 - (i + 1) * 0.32, 0.25 + 0 * i, (i + 1) * 0.2, 2.7 - i * 0.32), mat('stone', { color: 0xb8ab98 }), 0.7, {}); // steps up (P2 0023-0024)
  { const gp = new THREE.Group(); gp.position.z = 3.1; root.add(gp); K.wall(gp, -1.35, -0.75, 0, 1.3, [], { tints: STONE, course: 0.25, block: 0.3, rough: 0.05, seed: 10, T: 0.6 }); }
  K.slab(root, -2.0, 0, 2.95, -1.75, 8.5, 3.2, 'wood', 0x6b5643, 0.8);               // pole "10"
}
// planting spilling over the dry-stone wall (P1 0001-0009)
{
  const R = mulberry(3864), blobs = [], segs = [];
  for (let i = 0; i < 22; i++) { const x = D0 + R() * (D1 - D0), r = 0.14 + R() * 0.22, y = F - 0.12 - R() * 0.3; blobs.push(new THREE.IcosahedronGeometry(r, 1).scale(1.3, 0.8, 0.6).translate(x, y, DZ + 0.4 + R() * 0.15)); segs.push(x - r * 1.2, y + r * 0.5, DZ + 0.75, x + r * 1.2, y + r * 0.5, DZ + 0.75); }
  add(mergeGeometries(blobs), mat('foliage', { color: 0x7b8f6a }), 0, {});
  lines(segs, 0.6);
}
// iron gate at the foot of the steps, standing half open (P2 0011-0012, 0018-0022)
{
  const gate = new THREE.Group(); gate.position.set(-0.45, 0, 2.7); gate.rotation.y = -0.7; root.add(gate);
  const gb = []; for (let x = 0.0; x < 1.0; x += 0.11) gb.push(box(x, 0.05, -0.01, x + 0.02, 1.0, 0.01));
  gb.push(box(0, 0.95, -0.015, 1.05, 1.0, 0.015), box(0, 0.08, -0.015, 1.05, 0.13, 0.015), box(0, 0.5, -0.015, 1.05, 0.54, 0.015));
  add(mergeGeometries(gb), mat('steel', { color: 0x1d1d1d }), 0.45, { parent: gate });
}
S.street(-25, 35);
S.tree(L + 1.5, -3.0, 8.5, 2.8);
S.tree(-4.0, -4.5, 9.0, 2.9);
S.figure(4.0, F + 1.0, 1, true);
S.aimSun(5, 3, 20);

const pins = document.getElementById('pins');
[[0, '±0.00', 'Sidewalk'], [F, '+1.00', 'Cottage floor (derived)'], [F + 3.0, '+4.00', 'Fascia / pergola beam'], [F + P_HI, '+4.53', 'Parapet (ODM 4.55)']]
  .forEach(([y, a, b]) => {
    const el = pins.appendChild(document.createElement('div'));
    el.className = 'lv'; el.innerHTML = `<em></em><i></i><b>${a}</b><span>${b}</span>`;
    S.pin(el, [-2.4, y, 2.8]);
  });

const KEYS = [
  { p: 0, t: [5.1, 3.4, 0], fh: 9.6, fov: 2, phone: { t: [5.4, 3.4, 0], minW: 17 } },
  { p: 18, t: [5.1, 3.4, 0], fh: 9.6, fov: 2, phone: { t: [5.4, 3.4, 0], minW: 17 } },
  { p: 115, t: [6.3, 2.8, 0], fh: 8.0, fov: 16, yaw: -18, pitch: -6, phone: { minW: 16 } },
  { p: 228, t: [6.0, 2.6, 0], fh: 7.6, fov: 22, yaw: 16, pitch: -7, phone: { minW: 15 } },
  { p: 300, t: [12.0, 2.4, -1], fh: 4.6, fov: 32, yaw: -30, pitch: -6 },
  { p: 370, t: [0.2, 1.6, 2.4], fh: 3.6, fov: 40, yaw: 30, pitch: -6 },
  { p: 440, t: [2.8, 3.0, 1.0], fh: 3.4, fov: 50, yaw: 8, pitch: 6 },
  { p: 500, t: [4.0, 3.2, 1.0], fh: 3.0, fov: 56, yaw: -6, pitch: 14 },
];

const LATE = new THREE.Vector3(-1.4, 0.55, 0.9).normalize();
const sunDir = new THREE.Vector3(), warm = new THREE.Color(0xffcf96), white = new THREE.Color(0xfff1dc);

run(S, {
  length: 520,
  heroOut: [14, 70],
  radar: { ox: 0, zones: [{ id: 'street', label: 'STREET', tag: 'SIDEWALK ±0.00M', at: 95, u0: -4, u1: 0 }] },
  frame(p) {
    S.setCam(S.camAt(p, KEYS));
    S.U.uDepthCue.value = span(p, 22, 90) * (1 - span(p, 150, 205));
    const u = span(p, 118, 212);
    S.U.uSweep.value.z = u <= 0 ? -60 : u >= 1 ? 60 : lerp(-12, 20, smooth(u));
    const m = ease(span(p, 226, 300));
    sunDir.copy(CONVENTION).lerp(LATE, m).normalize();
    S.setSun(sunDir);
    S.sun.color.copy(white).lerp(warm, m);
    S.sun.intensity = lerp(3.4, 3.1, m);
    S.hemi.intensity = lerp(0.52, 0.46, m);
  },
  beats: [
    { from: 72, to: 128, html: '<span class="n">01 &nbsp;·&nbsp; Relief</span><p>The deck stands two metres out from the wall on a dry-stone retaining wall. The fence runs along the sidewalk below it.</p>' },
    { from: 140, to: 222, html: '<span class="n">02 &nbsp;·&nbsp; Teal and green</span><p>Every shadow was hatched at 45 degrees. So is <em>this</em> sun. Teal stucco, a dark metal fascia, green railings and pergola, as photographed.</p>' },
    { from: 236, to: 300, html: '<span class="n">03 &nbsp;·&nbsp; Late afternoon</span><p>The sun drops and the pergola rafters stripe the deck.</p>' },
    { from: 300, to: 366, html: '<span class="n">04 &nbsp;·&nbsp; The north porch</span><p>The brown shingle roof belongs to the cottage. It covers the entry porch and the <em>hot tub.</em></p><div class="row"><div><span>Source</span>Clip 035 f10, owner</div><div><span>Roof</span>Shingle</div><div><span>Porch</span>≈3.9 m (est.)</div></div>' },
    { from: 372, to: 436, html: '<span class="n">05 &nbsp;·&nbsp; From the sidewalk</span><p>Stone steps climb from the sidewalk past the stone pillar, through the iron <em>gate.</em></p>' },
    { from: 444, to: 540, html: '<span class="n">06 &nbsp;·&nbsp; Stone Street Cottage</span><p>9.9 by 6.3 metres, a flat roof in two levels, 3.5 m to the parapet. Under the green <em>pergola.</em></p><div class="row"><div><span>Plan</span>9.9 × 6.3 m</div><div><span>Parapet</span>3.53 m</div><div><span>Building</span>E3 / 9</div></div><a class="pill solid" href="../sunlit-elevation/">The lodge</a>' },
  ],
});
