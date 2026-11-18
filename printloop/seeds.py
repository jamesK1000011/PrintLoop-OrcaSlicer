# SPDX-License-Identifier: AGPL-3.0-only
"""The versioned data files under printloop/data/: seeds, dial table, knob
families, dialect tags, tool descriptions and schemas.

Each entry has a source and a date. The calibration store in the user
folder can override a seed per (printer, filament); this module never
writes there, and an update of the add-on never touches that folder.
"""
import json
import os

HERE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data")
_CACHE = {}


def load(name):
    """A data file by its name without .json (schema/x for a schema)."""
    if name not in _CACHE:
        with open(os.path.join(HERE, name + ".json"), encoding="utf-8") as f:
            _CACHE[name] = json.load(f)
    return _CACHE[name]


class Params:
    """Seed values with overrides (from the calibration store or a test).
    p["stringing.D0"] gives the value; p.source(key) says where it came from."""

    def __init__(self, overrides=None):
        self._seeds = load("defaults")["seeds"]
        self._over = dict(overrides or {})

    def __getitem__(self, key):
        if key in self._over:
            return self._over[key]
        return self._seeds[key]["value"]

    def source(self, key):
        return "calib" if key in self._over else "defaults"

    @property
    def from_calib(self):
        return bool(self._over)


def shrink(filament_type):
    s = load("defaults")["shrink"]
    t = (filament_type or "").strip().upper()
    if t in s["classes"]:
        return s["classes"][t]
    # A type with a suffix (PLA+, PETG-CF, ABS-GF): its base class.
    for k in sorted(s["classes"], key=len, reverse=True):
        if t.startswith(k):
            return s["classes"][k]
    return s["unknown"]


def filament_value(profile, key):
    """A value from an OrcaSlicer filament profile (a list or a string, as
    Orca keeps them), else the recorded fallback."""
    v = (profile or {}).get(key)
    if isinstance(v, list):
        v = v[0] if v else None
    if v in (None, "", "nil"):
        v = load("defaults")["filament_fallback"]["values"].get(key)
    if key == "filament_type":
        return str(v)
    try:
        return float(str(v).rstrip("%"))
    except (TypeError, ValueError):
        return load("defaults")["filament_fallback"]["values"].get(key)
