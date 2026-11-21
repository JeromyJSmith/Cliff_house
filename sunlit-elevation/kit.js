// Small modelling kit on top of the Sunlit Elevation engine, shared by the Cliff House lodge and
// Stone Street Cottage pages. Facade plane z = 0, x along the facade, y up, z towards the viewer.
import { THREE, mergeGeometries, mulberry } from './engine/elevation.js';

export function kit(S) {
  const { add, box, mat, lines } = S;

  // A wall laid course by course around its openings. Each course gets its own tint, and with
  // rough > 0 every block stands a little proud by a random amount (rock-faced stone).
  function wall(g, x0, x1, y0, y1, holes, o = {}) {
    const ch = o.course || 0.45, bl = o.block || 0.9, T = o.T || 0.5, R = mulberry(o.seed || 7);
    const tints = o.tints || [o.color || 0xc8907a];
    const by = new Map();
    for (let c = 0, y = y0; y < y1 - 1e-6; c++, y += ch) {
      const ya = y, yb = Math.min(y1, y + ch);
      let segs = [[x0, x1]];
      holes.forEach(([hx0, hy0, hx1, hy1]) => {
        if (hy1 <= ya + 1e-6 || hy0 >= yb - 1e-6) return;
        segs = segs.flatMap(([a, b]) => [[a, Math.min(b, hx0)], [Math.max(a, hx1), b]]).filter(([p, q]) => q - p > 1e-3);
      });
      segs.forEach(([a, b]) => {
        // split into blocks so tints and roughness vary block by block
        const off = (c % 2) * bl / 2;
        let xs = [a];
        for (let x = x0 - off + bl; x < b; x += bl) if (x > a + 0.05) xs.push(x);
        xs.push(b);
        for (let i = 0; i < xs.length - 1; i++) {
          const col = tints[Math.floor(R() * tints.length)];
          const pro = o.rough ? R() * o.rough : 0;
          if (!by.has(col)) by.set(col, []);
          by.get(col).push(box(xs[i] + (o.rough ? 0.006 : 0), ya + (o.rough ? 0.006 : 0), -T, xs[i + 1] - (o.rough ? 0.006 : 0), yb - (o.rough ? 0.006 : 0), pro));
        }
      });
    }
    by.forEach((geos, col) => add(mergeGeometries(geos), mat(o.kind || 'stone', { color: col }), 0, { parent: g }));
    if (o.outline !== false) {
      const s = [x0, y0, 0, x1, y0, 0, x1, y0, 0, x1, y1, 0, x0, y1, 0, x1, y1, 0, x0, y0, 0, x0, y1, 0];
      holes.forEach(([a, b, c, d]) => s.push(a, b, 0.01, c, b, 0.01, c, b, 0.01, c, d, 0.01, c, d, 0.01, a, d, 0.01, a, d, 0.01, a, b, 0.01));
      lines(s, 1.3, { parent: g, drawOnly: false });
    }
  }

  // Sash window: outer frame, meeting rail, a vertical muntin per sash (2-over-2), glass, dark room behind.
  function sash(g, x0, y0, x1, y1, o = {}) {
    const fw = o.fw || 0.07, z1 = -(o.recess || 0.16), z0 = z1 - 0.07, fm = mat('wood', { color: o.frame || 0x8fb3a0 });
    const fr = new THREE.Shape(); fr.moveTo(x0, y0); fr.lineTo(x1, y0); fr.lineTo(x1, y1); fr.lineTo(x0, y1); fr.closePath();
    const h = new THREE.Path(); h.moveTo(x0 + fw, y0 + fw); h.lineTo(x0 + fw, y1 - fw); h.lineTo(x1 - fw, y1 - fw); h.lineTo(x1 - fw, y0 + fw); h.closePath();
    fr.holes.push(h);
    add(new THREE.ExtrudeGeometry(fr, { depth: z1 - z0, bevelEnabled: false }).translate(0, 0, z0), fm, 0.7, { parent: g });
    const mx = (x0 + x1) / 2, my = (y0 + y1) / 2;
    if (o.panes !== 1) {
      add(box(x0 + fw, my - 0.035, z0, x1 - fw, my + 0.035, z1 + 0.02), fm, 0.6, { parent: g });
      add(box(mx - 0.022, y0 + fw, z0, mx + 0.022, y1 - fw, z1), fm, 0.5, { parent: g });
    }
    if (o.grid) for (let i = 1; i < o.grid; i++) { const yy = y0 + (y1 - y0) * i / o.grid; add(box(x0 + fw, yy - 0.02, z0, x1 - fw, yy + 0.02, z1), fm, 0.4, { parent: g }); }
    add(new THREE.PlaneGeometry(x1 - x0 - 0.03, y1 - y0 - 0.03).translate(mx, my, z0 + 0.02), mat('glass'), 0, { parent: g, cast: false });
    add(box(x0, y0, -(o.T || 0.5), x1, y1, z0 - 0.02), mat('interior', { realOnly: true, color: 0x6a5642 }), 0, { parent: g, cast: false });
    const rv = mat('plaster', { color: o.reveal || 0xe9e2d6 });
    add(box(x0 - 0.001, y0, -(o.T || 0.5), x0 + 0.02, y1, 0), rv, 0, { parent: g, cast: false });
    add(box(x1 - 0.02, y0, -(o.T || 0.5), x1 + 0.001, y1, 0), rv, 0, { parent: g, cast: false });
    add(box(x0, y1 - 0.02, -(o.T || 0.5), x1, y1 + 0.001, 0), rv, 0, { parent: g, cast: false });
  }

  // gable or hip roof over a rectangle x0..x1, z0..z1 (z1 at the facade), eave height e, rise r.
  function gableEnd(g, x0, x1, e, rise, z0, z1, o = {}) {
    const ov = o.over || 0.3;
    const sh = new THREE.Shape([[x0 - ov, e], [x1 + ov, e], [(x0 + x1) / 2, e + rise]].map((p) => new THREE.Vector2(...p)));
    add(new THREE.ExtrudeGeometry(sh, { depth: z1 - z0 + ov, bevelEnabled: false }).translate(0, -0.001, z0), mat('plain', { color: o.color || 0x4e4039 }), 1.3, { parent: g });
  }
  function hip(g, x0, x1, e, rise, z0, z1, o = {}) {
    const ov = o.over || 0.35, cx = (x0 + x1) / 2, cz = (z0 + z1) / 2;
    const w = x1 - x0 + 2 * ov, d = z1 - z0 + 2 * ov;
    const geo = new THREE.ConeGeometry(Math.SQRT1_2, 1, 4, 1, true).rotateY(Math.PI / 4).scale(w, rise, d).translate(cx, e + rise / 2, cz);
    add(geo, mat('plain', { color: o.color || 0x4e4039 }), 1.2, { parent: g });
  }

  function slab(g, x0, y0, z0, x1, y1, z1, kind, color, lw = 0.9) { return add(box(x0, y0, z0, x1, y1, z1), mat(kind, color ? { color } : {}), lw, { parent: g }); }

  // vertical-slat railing / board fence along x at depth z
  function slats(g, x0, x1, y0, h, z, o = {}) {
    const geos = [], sp = o.spacing || 0.14, w = o.w || 0.09, t = o.t || 0.03;
    for (let x = x0; x < x1 - w * 0.5; x += sp) geos.push(box(x, y0, z - t, x + w, y0 + h, z));
    if (o.rails !== false) { geos.push(box(x0, y0 + h - 0.08, z - t - 0.04, x1, y0 + h, z + 0.01)); geos.push(box(x0, y0 + 0.08, z - t - 0.04, x1, y0 + 0.16, z + 0.01)); }
    add(mergeGeometries(geos), mat(o.kind || 'wood', { color: o.color }), o.lw ?? 0.5, { parent: g });
  }

  return { wall, sash, gableEnd, hip, slab, slats };
}
