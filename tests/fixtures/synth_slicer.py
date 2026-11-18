# SPDX-License-Identifier: AGPL-3.0-only
"""A synthetic slicer for the runner tests. A "project" is a JSON file:
{"shape": ..., settings as OrcaSlicer keeps them}. slice writes synthetic
G-code that follows the settings the loop changes. It stands in for
orca_slice, which needs the Mac."""
import json
import os

import synth


def _f(v, d=0.0):
    if isinstance(v, list):
        v = v[0] if v else d
    try:
        return float(v)
    except (TypeError, ValueError):
        return d


class SynthSlicer:
    def __init__(self):
        self.calls = 0

    def settings(self, project):
        with open(project, encoding="utf-8") as f:
            return json.load(f)

    def apply(self, src, dest, overrides):
        s = self.settings(src)
        s.update(overrides)
        with open(dest, "w", encoding="utf-8") as f:
            json.dump(s, f)

    def slice(self, project, plate):
        self.calls += 1
        s = self.settings(project)
        shape = s.get("shape", "towers")
        temp = _f(s.get("nozzle_temperature"), 220)
        if shape == "towers":
            text = synth.towers(s.get("dialect", "bbl"), retract=_f(s.get("retraction_length")), wipe=_f(s.get("wipe")) > 0, temp=temp)
        elif shape == "spire":
            text = synth.spire(s.get("dialect", "bbl"), speed=max(_f(s.get("slow_down_min_speed"), 20), 20))
        else:
            raise ValueError(shape)
        out = os.path.splitext(project)[0] + ".gcode"
        with open(out, "w", encoding="utf-8") as f:
            f.write(text)
        return out


def project(path, shape="towers", **settings):
    base = {"shape": shape, "retraction_length": ["0"], "wipe": ["0"], "nozzle_temperature": ["230"], "nozzle_temperature_range_low": ["190"],
            "nozzle_temperature_range_high": ["240"], "reduce_crossing_wall": "0", "filament_type": ["PLA"], "slow_down_layer_time": ["8"],
            "filament_max_volumetric_speed": ["12"], "overhang_fan_speed": ["100"], "slow_down_min_speed": ["10"]}
    if shape == "towers":
        # The two 10 mm towers print fast; OrcaSlicer would slow them to the
        # layer time. 3 s keeps the thermal domain out of this fixture, and
        # 215 °C is the middle of the range (no temperature factor).
        base.update({"slow_down_layer_time": ["3"], "nozzle_temperature": ["215"]})
    base.update(settings)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(base, f)
    return path
