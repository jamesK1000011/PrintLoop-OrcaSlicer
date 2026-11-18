# SPDX-License-Identifier: AGPL-3.0-only
"""Domain 2: overhangs and bridging (§16.4), layers 2 and up.

Walls (Outer wall, Overhang wall): u is the fraction of the segment's own
ribbon (width w) outside buffer(P_{l-1}, w/2). Change (§17): the design
said the fraction of the centre line; with that, u stays 0 until the shift
per layer passes a whole line width (about 65 degrees at 0.2 mm layers)
and then jumps to 1. The ribbon fraction rises smoothly.
seg risk = u x (1 + 0.5 (1 - fan/100)) x clamp(v / V_ref, 0.5, 2).
Bridges: risk = clamp((L - L0) / L0, 0, 1) x (1 + 0.5 (1 - fan/100)).
r_l = the length-weighted p90 of segment risks on the layer.
"""
from statistics import median

from ...gcode import geom
from ..common import Hot, clamp, weighted_percentile

NAME = "overhang"
WALLS = ("Outer wall", "Overhang wall")
BRIDGES = ("Bridge", "Internal Bridge")


def score(model, prof, params, ctx=None):
    V_ref = prof.V_ref or params["overhang.V_ref_default"]
    fw = params["overhang.fan_weight"]
    L0 = params["overhang.L0"]
    lo, hi = params["overhang.v_clamp_lo"], params["overhang.v_clamp_hi"]
    sample = params["geom.sample_mm"]
    risks, hots = [], []
    prev = None
    for ly in model.layers:
        ext = [s for s in ly.segs if s.kind == "extrude"]
        region = ly.section(sample) if ext else None
        if prev is None or ly.index < 2:
            risks.append(0.0)
            prev = (region, ext)
            continue
        preg, pext = prev
        w_prev = median([s.width or 0.4 for s in pext]) if pext else 0.4
        grown = preg.grow(w_prev / 2.0) if preg is not None else None
        pairs, best = [], None
        bridges = {}
        for s in ext:
            fan_f = 1 + fw * (1 - (s.fan or 0.0) / 100.0)
            if s.feature in WALLS:
                L = s.length
                if L < 1e-9:
                    continue
                u = 1.0 if grown is None else grown.ribbon_outside(s.x0, s.y0, s.x1, s.y1, s.width or 0.4)
                r = u * fan_f * clamp((s.actual_speed or s.speed) / V_ref, lo, hi)
                pairs.append((r, L))
                if best is None or r > best[0]:
                    best = (r, s.mid, f"{s.feature.lower()} {100 * u:.0f}% unsupported, fan {s.fan:.0f}%, {s.actual_speed or s.speed:.0f} mm/s")
            elif s.feature in BRIDGES:
                bridges.setdefault(s.line, []).append(s)
        for segs in bridges.values():
            L = sum(s.length for s in segs)
            s = segs[0]
            r = clamp((L - L0) / L0) * (1 + fw * (1 - (s.fan or 0.0) / 100.0))
            pairs.append((r, L))
            if best is None or r > best[0]:
                best = (r, s.mid, f"bridge {L:.1f} mm, fan {s.fan:.0f}%")
        r_l = clamp(weighted_percentile(pairs, params["overhang.p"])) if pairs else 0.0
        risks.append(r_l)
        if best is not None and r_l > 0:
            hots.append(Hot(ly.index, ly.z, best[1], r_l, best[2]))
        # Only the layer below stays in memory (the design allows 3).
        prev = (region, ext)
    return risks, hots
