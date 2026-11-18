# SPDX-License-Identifier: AGPL-3.0-only
"""Domain 1: stringing and oozing (§16.4).

For each travel on a layer: d_open is the travel's length outside the
layer's extrusion region P_l. m = sigmoid((d_open - D0) / S), times
k_retract when retracted, k_wipe when wiped, k_zhop with a z-hop, and a
temperature factor. Change (§17): a travel with d_open under d_open_min
adds no risk, and so does a travel that does not start and end on the
layer's printed section (the approach from the start G-code or a park
move: a string needs two ends on the part). r_l = 1 - prod(1 - m), clamped.
"""
from ..common import Hot, clamp, sigmoid

NAME = "stringing"


def _moves(segs):
    """Travel segments grouped by G-code line (an arc is one move)."""
    out, cur, line = [], [], None
    for s in segs:
        if s.kind != "travel":
            continue
        if cur and s.line != line:
            out.append(cur)
            cur = []
        cur.append(s)
        line = s.line
    if cur:
        out.append(cur)
    return out


def score(model, prof, params, ctx=None):
    D0, S = params["stringing.D0"], params["stringing.S"]
    dmin = params["stringing.d_open_min"]
    mid_t = (prof.T_lo + prof.T_hi) / 2.0
    half = max(1e-6, (prof.T_hi - prof.T_lo) / 2.0)
    risks, hots = [], []
    sample = params["geom.sample_mm"]
    for ly in model.layers:
        ext = [(s.x0, s.y0, s.x1, s.y1, s.width or 0.4) for s in ly.segs if s.kind == "extrude"]
        moves = _moves(ly.segs)
        if not ext or not moves:
            risks.append(0.0)
            continue
        P = ly.section(sample)
        tfac = 1 + max(0.0, ((ly.temp or mid_t) - mid_t) / half) * params["stringing.k_temp"]
        keep = 1.0
        best = None
        for mv in moves:
            if not (P.contains(mv[0].x0, mv[0].y0) and P.contains(mv[-1].x1, mv[-1].y1)):
                continue
            d_open, mid, longest = 0.0, None, 0.0
            for s in mv:
                d, m_ = P.outside(s.x0, s.y0, s.x1, s.y1)
                d_open += d
                if m_ is not None and d > longest:
                    longest, mid = d, m_
            if d_open < dmin:
                continue
            m = sigmoid((d_open - D0) / S)
            first = mv[0]
            if first.retracted:
                m *= params["stringing.k_retract"]
            if first.wiped:
                m *= params["stringing.k_wipe"]
            if any(s.zhop for s in mv):
                m *= params["stringing.k_zhop"]
            m = clamp(m * tfac)
            keep *= 1 - m
            if best is None or m > best[0]:
                why = f"travel {d_open:.1f} mm open air, " + ("retracted" if first.retracted else "not retracted") + (", wiped" if first.wiped else "")
                best = (m, mid, why)
        r = clamp(1 - keep)
        risks.append(r)
        if best is not None and r > 0:
            hots.append(Hot(ly.index, ly.z, best[1], r, best[2]))
    return risks, hots
