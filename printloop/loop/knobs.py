# SPDX-License-Identifier: AGPL-3.0-only
"""Knob families (§16.5.3, data/knobs.json): one family per iteration.

changes(family, settings, prof, domain) gives the OrcaSlicer settings to
set on the run copy, each checked against orcalink's options table
(limits, types) and the filament temperature range. An empty result means
the family has nothing to change here.
"""
from .. import _orca, seeds


def families():
    return seeds.load("knobs")["families"]


def family(name):
    for f in families():
        if f["family"] == name:
            return f
    raise KeyError(name)


def for_domain(domain, tried):
    """Families in table order that domain triggers and the run has not tried."""
    return [f for f in families() if domain in f["triggered_by"] and f["family"] not in tried]


def _first(v):
    if isinstance(v, list):
        v = v[0] if v else None
    return v


def _num(v, default=None):
    v = _first(v)
    try:
        return float(str(v).rstrip("%").split(",")[0])
    except (TypeError, ValueError):
        return default


def _default(key):
    opt = _orca.orca3mf().options()["options"].get(key) or {}
    return opt.get("default")


def _shape(cur, value):
    """value in the shape the setting has now (one per filament or extruder)."""
    if isinstance(cur, list) and cur:
        return [value] * len(cur)
    return value


def changes(fam, settings, prof, domain=None):
    O = _orca.orca3mf()
    out = {}
    for st in fam["steps"]:
        key = st["key"]
        when = st.get("when")
        if when == "shrink>=0.8" and prof.shrink < 0.8:
            continue
        cur = settings.get(key)
        if st["op"] == "set":
            v = st["to"]
            if _num(cur) is not None and isinstance(v, bool) and bool(_num(cur)) == v:
                continue
            if _first(cur) is not None and str(_first(cur)) == str(v):
                continue
        else:
            base = _num(cur, _num(_default(key), None))
            if base is None:
                continue
            if st["op"] == "add":
                by = st["by"]
                if st.get("raise_for") and domain == st["raise_for"]:
                    by = -by
                v = base + by
            else:  # scale
                if base == 0:
                    continue  # 0 means "no limit" or "off" in OrcaSlicer: nothing to scale
                v = base * st["by"]
            if "max" in st:
                v = min(v, st["max"])
            if st.get("floor") == "T_lo+5":
                v = max(v, prof.T_lo + 5)
                v = min(v, prof.T_hi)
            v = round(v, 3)
            if abs(v - base) < 1e-9:
                continue
            if float(v).is_integer() and ("int" in str((O.options()["options"].get(key) or {}).get("type", ""))):
                v = int(v)
        try:
            checked = O.check(key, _shape(cur, v), "project")
        except O.ProjectError:
            continue  # out of OrcaSlicer's limits: this step cannot be taken
        out[key] = checked
        if key == "nozzle_temperature" and "nozzle_temperature_initial_layer" in settings:
            try:
                out["nozzle_temperature_initial_layer"] = O.check("nozzle_temperature_initial_layer", _shape(settings["nozzle_temperature_initial_layer"], v), "project")
            except O.ProjectError:
                pass
    return out
