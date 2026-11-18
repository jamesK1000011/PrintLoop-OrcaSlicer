# SPDX-License-Identifier: AGPL-3.0-only
"""Coordinate alignment (§10, spike step 4).

G-code point g (plate coordinates) to model point:
  world = g + plate origin (OrcaSlicer lays plates side by side)
  part  = inverse(build-item transform x component transform) x world
  body  = part + source_offset (OrcaSlicer keeps a loaded mesh centred and
          records the shift, as orcalink's orca_paint uses it)
  model = inverse(FreeCAD export placement) x body
The fiducial check takes the corners of the second and top layers' outer
walls, moves each out by half a line width, maps it, and compares it with
the known vertices of the model (limit 0.2 mm).
"""
import json
import math
import os

from . import _orca, paths
from .gcode import geom

IDENTITY = [[1.0, 0, 0, 0], [0, 1.0, 0, 0], [0, 0, 1.0, 0], [0, 0, 0, 1.0]]


def placement_matrix(ctx):
    m = ((ctx or {}).get("export_placement") or {}).get("matrix4")
    if not m or len(m) != 16:
        return IDENTITY
    return [list(map(float, m[0:4])), list(map(float, m[4:8])), list(map(float, m[8:12])), list(map(float, m[12:16]))]


class Mapper:
    """G-code (x, y, z) -> model (x, y, z) for one object instance."""

    def __init__(self, project, obj=None, instance=0, plate=1, export_placement=None):
        O = _orca.orca3mf()
        pr = project if hasattr(project, "objects") else O.Project(project)
        objs = pr.objects()
        o = pr.object(obj) if obj is not None else objs[0]
        part = next((p for p in o["parts"] if p["kind"] == "normal_part"), o["parts"][0])
        inst = o["instances"][instance]["transform"] if o["instances"] else O.matrix(None)
        self.T_inv = O.invert(O.mul(inst, part["transform"]))
        self.offset = part.get("sourceOffset") or [0.0, 0.0, 0.0]
        self.origin = pr.plate_origin(plate) if plate and plate > 1 else (0.0, 0.0)
        self.P_inv = O.invert(export_placement) if export_placement and export_placement != IDENTITY else None
        self._apply = O.apply
        self.object = o["name"]

    def __call__(self, x, y, z):
        w = (x + self.origin[0], y + self.origin[1], z)
        p = self._apply(self.T_inv, w)
        b = (p[0] + self.offset[0], p[1] + self.offset[1], p[2] + self.offset[2])
        return self._apply(self.P_inv, b) if self.P_inv else b


def wall_corners(layer, limit_deg=150.0):
    """Corners of a layer's outer-wall loops, each moved out by half a
    line width along its bisector: the model's own corner in G-code space."""
    segs = [s for s in layer.segs if s.kind == "extrude" and s.feature == "Outer wall"]
    if not segs:
        return []
    w = sum(s.width or 0.4 for s in segs) / len(segs)
    out = []
    for lp in geom.loops([(s.x0, s.y0, s.x1, s.y1) for s in segs], tol=0.6):
        pts = geom.simplify(lp, 0.05)
        n = len(pts)
        if n < 3:
            continue
        area2 = sum(pts[i][0] * pts[(i + 1) % n][1] - pts[(i + 1) % n][0] * pts[i][1] for i in range(n))
        ccw = area2 > 0
        for i in range(n):
            a, b, c = pts[i - 1], pts[i], pts[(i + 1) % n]
            e1 = (b[0] - a[0], b[1] - a[1])
            e2 = (c[0] - b[0], c[1] - b[1])
            l1, l2 = math.hypot(*e1), math.hypot(*e2)
            if l1 < 1e-6 or l2 < 1e-6:
                continue
            # Outward normals of both edges (right of the edge for a CCW loop).
            n1 = (e1[1] / l1, -e1[0] / l1) if ccw else (-e1[1] / l1, e1[0] / l1)
            n2 = (e2[1] / l2, -e2[0] / l2) if ccw else (-e2[1] / l2, e2[0] / l2)
            turn = math.degrees(math.acos(max(-1.0, min(1.0, (e1[0] * e2[0] + e1[1] * e2[1]) / (l1 * l2)))))
            if 180.0 - turn > limit_deg:
                continue  # nearly straight: not a corner
            bx, by = n1[0] + n2[0], n1[1] + n2[1]
            bl = math.hypot(bx, by)
            if bl < 1e-9:
                continue
            cos_half = (n1[0] * bx + n1[1] * by) / bl
            d = (w / 2.0) / max(cos_half, 1e-6)
            out.append((b[0] + bx / bl * d, b[1] + by / bl * d))
    return out


def fiducial_check(model, mapper, vertices, tol=0.2):
    """Map the corners of the first and top layers to the model and match
    each known vertex [x, y, z] (model coordinates) to the nearest mapped
    corner at its height. Answer: errors per vertex and pass."""
    # Layer 2 for the bottom vertices: the first layer may be inset by
    # elephant-foot compensation. The walls are vertical there.
    first, top = model.layers[1 if len(model.layers) > 2 else 0], model.layers[-1]
    cand = []
    for ly, zb in ((first, 0.0), (top, top.z)):
        for x, y in wall_corners(ly):
            cand.append(mapper(x, y, zb))
    out = []
    for v in vertices:
        best = min(cand, key=lambda p: math.dist(p, v)) if cand else None
        err = math.dist(best, v) if best is not None else None
        out.append({"vertex": list(v), "mapped": [round(c, 3) for c in best] if best else None, "error_mm": round(err, 3) if err is not None else None})
    ok = bool(out) and all(e["error_mm"] is not None and e["error_mm"] <= tol for e in out)
    return {"pass": ok, "tol_mm": tol, "vertices": out}


def store_aligned(printer, setup, result):
    """Record the fiducial result in config.json (the user folder)."""
    cfg = paths.config()
    cfg.setdefault("aligned", {})[f"{printer}|{setup}"] = {"pass": bool(result["pass"]), "vertices": result["vertices"]}
    paths.save_config(cfg)
    return cfg["aligned"][f"{printer}|{setup}"]


def is_aligned(printer, setup):
    a = paths.config().get("aligned", {}).get(f"{printer}|{setup}")
    return bool(a and a.get("pass"))


def load_context(ctx):
    if isinstance(ctx, str):
        with open(os.path.expanduser(ctx), encoding="utf-8") as f:
            return json.load(f)
    return ctx or {}
