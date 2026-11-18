# SPDX-License-Identifier: AGPL-3.0-only
"""Domain 5: structural and tolerance collisions (§16.4).

Needs an aligned context (the fiducial passed); otherwise the status is
unaligned and the domain has no score. Candidate points per layer: seams,
outer-wall speed steps (|dv| > 50 mm/s within 2 mm), and support-interface
contacts with the part. Each maps to model coordinates. Risk per point =
the larger of max(ratio x exp(-d / r0)) over stress peaks and
max(exp(-d / r0)) over keep-out samples; r0 = 2 w. r_l = max over points.
"""
import math

from ...gcode import geom
from ..common import Hot

NAME = "collision"


def _candidates(ly, params):
    pts = []
    for x, y in ly.seams:
        pts.append((x, y, "seam"))
    walls = [s for s in ly.segs if s.kind == "extrude" and s.feature == "Outer wall"]
    step, win = params["collision.speed_step"], params["collision.speed_window"]
    for a, b in zip(walls, walls[1:]):
        if math.hypot(b.x0 - a.x1, b.y0 - a.y1) <= win and abs((b.actual_speed or b.speed) - (a.actual_speed or a.speed)) > step:
            pts.append((b.x0, b.y0, "speed step"))
    sup = [s for s in ly.segs if s.kind == "extrude" and s.feature == "Support interface"]
    if sup:
        part = [(s.x0, s.y0, s.x1, s.y1, s.width or 0.4) for s in ly.segs if s.kind == "extrude" and not s.feature.startswith("Support")]
        if part:
            reg = geom.region(part, params["geom.sample_mm"])
            for s in sup:
                mx, my = s.mid
                if reg.distance(mx, my, limit=(s.width or 0.4) * 2) <= (s.width or 0.4):
                    pts.append((mx, my, "support contact"))
    return pts


def score(model, prof, params, ctx=None):
    peaks = ((ctx.context.get("stress") or {}).get("peaks") or []) if ctx else []
    keep = [p for f in (ctx.context.get("keepout_faces") or []) for p in (f.get("samples") or [])] if ctx else []
    risks, hots = [], []
    for ly in model.layers:
        ext = [s for s in ly.segs if s.kind == "extrude"]
        w = (sum(s.width or 0.4 for s in ext) / len(ext)) if ext else 0.4
        r0 = params["collision.r0_widths"] * w
        best = (0.0, None, None, "")
        for x, y, kind in _candidates(ly, params):
            m = ctx.mapper(x, y, ly.z)
            r = 0.0
            why = ""
            for pk in peaks:
                v = float(pk.get("ratio", 1.0)) * math.exp(-math.dist(m, pk["xyz"]) / r0)
                if v > r:
                    r, why = v, f"{kind} {math.dist(m, pk['xyz']):.1f} mm from a stress peak ({pk.get('vm_mpa', '?')} MPa)"
            for q in keep:
                v = math.exp(-math.dist(m, q) / r0)
                if v > r:
                    r, why = v, f"{kind} {math.dist(m, q):.1f} mm from a keep-out face"
            if r > best[0]:
                best = (r, (x, y), m, why)
        risks.append(best[0])
        if best[0] > 0:
            hots.append(Hot(ly.index, ly.z, best[1], best[0], best[3], best[2]))
    return risks, hots
