# SPDX-License-Identifier: AGPL-3.0-only
"""Domain 4: thermal buildup and under-extrusion (§16.4).

r_time = clamp((t_min - t_layer) / t_min) when t_layer < t_min (the layer
time after OrcaSlicer's own slow-down, from gcode_view).
r_flow = max over moves of clamp((Q - 0.9 Q_max) / (0.2 Q_max)), Q the
actual volumetric flow. r_l = max(r_time, r_flow). The hot spot is the
worst move.
"""
from ..common import Hot, clamp

NAME = "thermal"


def score(model, prof, params, ctx=None):
    t_min, Q_max = prof.t_min, prof.Q_max
    a, span = params["thermal.flow_start"], params["thermal.flow_span"]
    risks, hots = [], []
    for ly in model.layers:
        ext = [s for s in ly.segs if s.kind == "extrude"]
        if not ext:
            risks.append(0.0)
            continue
        r_time = clamp((t_min - ly.time) / t_min) if t_min and ly.time < t_min else 0.0
        worst, r_flow = None, 0.0
        for s in ext:
            q = s.actual_flow or 0.0
            r = clamp((q - a * Q_max) / (span * Q_max)) if Q_max else 0.0
            if worst is None or r > r_flow or (r == r_flow == 0 and q > (worst.actual_flow or 0)):
                if r >= r_flow:
                    r_flow = r
                    worst = s
        r_l = max(r_time, r_flow)
        risks.append(r_l)
        if r_l > 0:
            if r_flow >= r_time:
                why = f"flow {worst.actual_flow:.1f} of {Q_max:.1f} mm³/s"
            else:
                why = f"layer time {ly.time:.1f} s under {t_min:.0f} s"
            hots.append(Hot(ly.index, ly.z, worst.mid, r_l, why))
    return risks, hots
