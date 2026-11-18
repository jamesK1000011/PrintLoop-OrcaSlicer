# SPDX-License-Identifier: AGPL-3.0-only
# Spike step 4 (synthetic part): the fiducial L-bracket. Three known
# vertices map from G-code to model coordinates within 0.2 mm, also after
# the object is moved and turned (as arrange does). The real check needs
# the Mac: mac/step4_fiducial.md and mac/step4_check.py.
import math

import mk3mf
import synth
from printloop import align
from printloop.gcode import layers as L

SO = (20.0, 10.5, 14.5)  # where OrcaSlicer centres the mesh (source_offset)


def rot(deg, t):
    c, s = math.cos(math.radians(deg)), math.sin(math.radians(deg))
    return [[c, -s, 0, t[0]], [s, c, 0, t[1]], [0, 0, 1, t[2]], [0, 0, 0, 1]]


def comp():
    return [[1, 0, 0, SO[0]], [0, 1, 0, SO[1]], [0, 0, 1, SO[2]], [0, 0, 0, 1]]


def make(tmp_path, deg, t, name="f.gcode.3mf", seam=None):
    inst = rot(deg, (t[0], t[1], 0.0))
    c, s = math.cos(math.radians(deg)), math.sin(math.radians(deg))

    def place(x, y):
        return (c * x - s * y + t[0], s * x + c * y + t[1])

    text = synth.l_bracket_layers("bbl", seam=place(*seam) if seam else None, place=place)
    return mk3mf.write(str(tmp_path / name), text, comp(), inst, SO, {"filament_type": ["PLA"]})


def check(path, mapper_path, tmp_path):
    g, _ = L.open_source(path, 1, str(tmp_path))
    m = L.build(g)
    return align.fiducial_check(m, align.Mapper(mapper_path), synth.fiducial_vertices())


def test_fiducial_maps_within_02(tmp_path):
    p = make(tmp_path, 0, (100, 100))
    r = check(p, p, tmp_path)
    assert r["pass"], r
    assert all(v["error_mm"] <= 0.2 for v in r["vertices"])


def test_fiducial_after_arrange(tmp_path):
    p = make(tmp_path, 90, (150, 60), "arranged.gcode.3mf")
    r = check(p, p, tmp_path)
    assert r["pass"], r


def test_stale_transform_fails(tmp_path):
    a = make(tmp_path, 0, (100, 100), "a.gcode.3mf")
    b = make(tmp_path, 90, (150, 60), "b.gcode.3mf")
    r = check(b, a, tmp_path)  # G-code of b mapped with a's placement
    assert not r["pass"]


def test_store_aligned(tmp_path):
    p = make(tmp_path, 0, (100, 100))
    r = check(p, p, tmp_path)
    align.store_aligned("h2d-test", "plate1", r)
    assert align.is_aligned("h2d-test", "plate1")
    assert not align.is_aligned("h2d-test", "plate2")


def test_export_placement_inverse(tmp_path):
    p = make(tmp_path, 0, (100, 100))
    # The body was exported moved by +5 mm in x: the model is 5 mm back.
    P = [[1, 0, 0, 5.0], [0, 1, 0, 0], [0, 0, 1, 0], [0, 0, 0, 1]]
    mp = align.Mapper(p, export_placement=P)
    x, y, z = mp(100 + 40, 100, 0)
    assert abs(x - 35.0) < 1e-6 and abs(y) < 1e-6


def test_mac_step4_script(tmp_path, capsys):
    import importlib.util
    import json
    import os

    spec = importlib.util.spec_from_file_location("step4_check", os.path.join(os.path.dirname(__file__), "..", "mac", "step4_check.py"))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    p = make(tmp_path, 90, (150, 60), "m.gcode.3mf")
    assert mod.main([p, "--store", "--printer", "h2d-test"]) == 0
    out = json.loads(capsys.readouterr().out)
    assert out["pass"] and out["stored"]["pass"]
    assert align.is_aligned("h2d-test", "plate1")
