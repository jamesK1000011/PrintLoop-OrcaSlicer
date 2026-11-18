# SPDX-License-Identifier: AGPL-3.0-only
"""Domain 3: warping and adhesion (§16.4), a part-level risk.

A1 = area(P_1); H = top Z; aspect = clamp(H / sqrt(A1) / 3, 0, 1);
corners = convex corners under 90 degrees on the outer boundary of
P_1 + P_2 + P_3, / 8, clamped; early_fan = mean part fan of layers 1-3 /
100; shrink by filament type.
r = shrink x (w_a aspect + w_c corners + w_f early_fan x shrink); a brim
or brim ears multiply r by 0.6.
Change (§17): the domain score is 100 x (1 - r), not the layer p95. The
p95 over all layers makes a part-level risk depend on the layer count.
The risk is still reported on layers 1-3.
"""
import math

from ...gcode import geom
from ..common import Hot, clamp

NAME = "warp"


def _first(model, n):
    return [ly for ly in model.layers[:n]]


def corners_of(layers, params):
    """Acute convex corners on the outer boundary of the first layers."""
    limit = params["warp.corner_deg"]
    if geom.backend() == "shapely":  # pragma: no cover - needs shapely
        regs = [geom.region([(s.x0, s.y0, s.x1, s.y1, s.width or 0.4) for s in ly.segs if s.kind == "extrude"]) for ly in layers]
        pts = geom.union(regs).exterior()
        return geom.acute_corners(pts, limit), pts
    # Fallback: the largest outer-wall loop of these layers.
    best, best_a = [], 0.0
    for ly in layers:
        segs = [(s.x0, s.y0, s.x1, s.y1) for s in ly.segs if s.kind == "extrude" and s.feature == "Outer wall"]
        for lp in geom.loops(segs, tol=0.6):
            a = geom.polygon_area(lp)
            if a > best_a:
                best, best_a = lp, a
    if not best:
        return 0, []
    pts = geom.simplify(best, 0.2)
    return geom.acute_corners(pts, limit), pts


def part_risk(model, prof, params):
    n = int(params["warp.layers"])
    first = _first(model, n)
    if not first:
        return 0.0, None, ""
    P1 = [(s.x0, s.y0, s.x1, s.y1, s.width or 0.4) for s in first[0].segs if s.kind == "extrude" and s.feature not in ("Brim", "Skirt")]
    if not P1:
        return 0.0, None, ""
    reg = geom.region(P1, params["geom.sample_mm"])
    b = reg.bounds()
    cell = max(params["geom.sample_mm"], math.sqrt(max(1e-6, (b[2] - b[0]) * (b[3] - b[1]))) / 300.0)
    A1 = reg.area(cell)
    H = model.top_z
    aspect = clamp(H / math.sqrt(max(A1, 1e-6)) / params["warp.aspect_div"])
    nc, pts = corners_of(first, params)
    corners = clamp(nc / params["warp.corner_norm"])
    early_fan = sum(ly.fan_mean for ly in first) / len(first) / 100.0
    sh = prof.shrink
    r = sh * (params["warp.w_a"] * aspect + params["warp.w_c"] * corners + params["warp.w_f"] * early_fan * sh)
    brim = prof.brim or any(s.feature == "Brim" for s in first[0].segs if s.kind == "extrude")
    if brim:
        r *= params["warp.brim_factor"]
    r = clamp(r)
    where = (b[0], b[1]) if pts == [] else min(pts, key=lambda p: p[0] + p[1])
    why = f"{prof.filament_type} (shrink {sh}), height/footprint {aspect:.2f}, {nc} sharp corners, early fan {100 * early_fan:.0f}%" + (", brim" if brim else "")
    return r, where, why


def score(model, prof, params, ctx=None):
    r, where, why = part_risk(model, prof, params)
    n = int(params["warp.layers"])
    risks = [r if i < n else 0.0 for i in range(len(model.layers))]
    hots = [Hot(1, model.layers[0].z, where, r, why)] if r > 0 and where is not None else []
    return risks, hots


def domain_score(risks, params):
    r = max(risks) if risks else 0.0
    return int(round(100 * (1 - r))), r >= params["score.critical"], r, r
