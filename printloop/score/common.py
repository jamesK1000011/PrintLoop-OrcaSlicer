# SPDX-License-Identifier: AGPL-3.0-only
"""Shared scoring math (§16.4): percentiles, the domain score, hot spots,
and the inputs from the filament profile."""
import math

from .. import seeds


def clamp(v, lo=0.0, hi=1.0):
    return lo if v < lo else hi if v > hi else v


def sigmoid(x):
    if x < -60:
        return 0.0
    return 1.0 / (1.0 + math.exp(-x))


def percentile(vals, p):
    """Nearest-rank percentile (p in 0..1) of a list; 0 for an empty list."""
    if not vals:
        return 0.0
    s = sorted(vals)
    k = max(0, min(len(s) - 1, int(math.ceil(p * len(s))) - 1))
    return s[k]


def weighted_percentile(pairs, p):
    """pairs: [(value, weight)]. The smallest value whose cumulative weight
    reaches p of the total."""
    pairs = [(v, w) for v, w in pairs if w > 0]
    if not pairs:
        return 0.0
    pairs.sort()
    tot = sum(w for _, w in pairs)
    acc = 0.0
    for v, w in pairs:
        acc += w
        if acc >= p * tot - 1e-12:
            return v
    return pairs[-1][0]


def domain_score(risks, params):
    """score, critical, p95, max of layer risks."""
    if not risks:
        return 100, False, 0.0, 0.0
    p95 = percentile(risks, params["score.p95"])
    mx = max(risks)
    score = int(round(100 * (1 - max(p95, params["score.max_weight"] * mx))))
    return max(0, min(100, score)), mx >= params["score.critical"], p95, mx


class Hot:
    __slots__ = ("layer", "z", "xy", "risk", "why", "model_xyz")

    def __init__(self, layer, z, xy, risk, why, model_xyz=None):
        self.layer, self.z, self.xy, self.risk, self.why, self.model_xyz = layer, z, xy, risk, why, model_xyz

    def as_dict(self):
        return {"layer": self.layer, "z": round(self.z, 3), "xy": [round(self.xy[0], 2), round(self.xy[1], 2)],
                "model_xyz": [round(v, 3) for v in self.model_xyz] if self.model_xyz is not None else None,
                "risk": round(self.risk, 3), "why": self.why}


class Profile:
    """The filament and printer inputs (§16.4 shared inputs)."""

    def __init__(self, settings=None, capabilities=None):
        s = settings or {}
        self.settings = s
        self.T_lo = seeds.filament_value(s, "nozzle_temperature_range_low")
        self.T_hi = seeds.filament_value(s, "nozzle_temperature_range_high")
        q = seeds.filament_value(s, "filament_max_volumetric_speed")
        cap = (capabilities or {}).get("max_flow")
        self.Q_max = min(q, cap) if cap else q
        self.t_min = seeds.filament_value(s, "slow_down_layer_time")
        self.filament_type = seeds.filament_value(s, "filament_type")
        self.shrink = seeds.shrink(self.filament_type)
        v = s.get("overhang_3_4_speed")
        if isinstance(v, list):
            v = v[0] if v else None
        try:
            self.V_ref = float(str(v).rstrip("%")) if v not in (None, "") and not str(v).endswith("%") and float(str(v)) > 0 else None
        except ValueError:
            self.V_ref = None
        self.brim = str(s.get("brim_type", "")).strip() in ("brim_ears", "outer_only", "inner_only", "outer_and_inner", "painted")
