# SPDX-License-Identifier: AGPL-3.0-only
# Spike step 3: dialect + arcs on top of gcode_view. Real fixtures from the
# Mac (spike step 2, 18 Nov 2026) and synthetic ones in both dialects.
import math
import os
import re

import pytest

import synth
from printloop import _orca
from printloop.gcode import dialect as D
from printloop.gcode import layers as L

MAC = os.path.join(os.path.dirname(__file__), "fixtures", "mac")
H2D = os.path.join(MAC, "cube_overhang_h2d.gcode.3mf")
PRUSA = os.path.join(MAC, "prusa_dialect_sample.gcode")
PRUSA3MF = os.path.join(MAC, "cube_overhang_prusa.gcode.3mf")
# gcode_read's totals per feature (lengthMm) on the Mac, STEP2.md.
H2D_TOTALS = {"Sparse infill": 13283.1, "Outer wall": 8187.7, "Inner wall": 7746.1, "Internal solid infill": 6993.8, "Internal Bridge": 1162.7,
              "Bridge": 497.3, "Top surface": 1498.1, "Bottom surface": 698.5, "Overhang wall": 75.8}


def model_of(path, tmp_path):
    g, info = L.open_source(path, 1, str(tmp_path))
    return L.build(g), g, info


@pytest.mark.parametrize("path,dia,arcs", [(H2D, "bbl", True), (PRUSA, "prusa", False), (PRUSA3MF, "prusa", False)])
def test_real_fixture_matches_gcode_read(path, dia, arcs, tmp_path):
    m, g, info = model_of(path, tmp_path)
    assert m.dialect == dia
    assert m.arcs is arcs
    G = _orca.gcode_view()
    data = G.read(g)
    assert len(m.layers) == len(data["layers"]) == 100
    for a, b in zip(m.layers, data["layers"]):
        ref = sum(f["length"] for f in b.features.values())
        if ref > 0:
            assert abs(a.extrude_length - ref) / ref < 0.01, (a.index, a.extrude_length, ref)


def test_h2d_feature_totals_match_mac(tmp_path):
    m, _, info = model_of(H2D, tmp_path)
    assert info["md5"] is True
    assert "Metadata/plate_1.gcode" in info["files"]
    tot = {}
    for ly in m.layers:
        for s in ly.segs:
            if s.kind == "extrude":
                tot[s.feature] = tot.get(s.feature, 0.0) + s.length
    for k, v in H2D_TOTALS.items():
        assert abs(tot[k] - v) / v < 0.01, (k, tot[k], v)


def test_real_arcs_chord_error(tmp_path):
    _, g, _ = model_of(H2D, tmp_path)
    arg = re.compile(r"([XYIJ])\s*(-?\d*\.?\d+)")
    x = y = 0.0
    worst, n = 0.0, 0
    with open(g, encoding="utf-8") as f:
        for line in f:
            code = line.split(";", 1)[0].strip()
            if not code or code.split()[0] not in ("G0", "G1", "G2", "G3"):
                continue
            a = {k: float(v) for k, v in arg.findall(code[2:])}
            nx, ny = a.get("X", x), a.get("Y", y)
            if code.startswith(("G2", "G3")) and ("I" in a or "J" in a):
                worst = max(worst, L.chord_error(x, y, nx, ny, a, code.startswith("G2"), 0.05))
                n += 1
            x, y = nx, ny
    # 107 arcs at the start of a line (STEP2.md) and one indented spiral lift
    # in the printer's start G-code.
    assert n == 108
    assert worst <= 0.1


@pytest.mark.parametrize("cw", [False, True])
def test_arc_points_chord_limit(cw):
    for r in (0.5, 2.0, 25.0, 200.0):
        args = {"I": -r, "J": 0.0}
        err = L.chord_error(r, 0.0, -r, 0.0, args, cw, 0.05)
        assert err <= 0.1
        pts = L.arc_points(r, 0.0, -r, 0.0, args, cw, 0.05)
        assert pts[-1] == (-r, 0.0)
        for px, py in pts:
            assert abs(math.hypot(px, py) - r) < 1e-6


def test_arc_r_form():
    pts = L.arc_points(10.0, 0.0, 0.0, 10.0, {"R": 10.0}, False, 0.05)
    assert all(abs(math.hypot(x - 0.0, y - 0.0) - 10.0) < 1e-6 for x, y in pts)


def test_both_dialects_same_layers(tmp_path):
    out = {}
    for d in ("bbl", "prusa"):
        p = tmp_path / f"spire_{d}.gcode"
        p.write_text(synth.spire(d))
        m = L.build(str(p))
        assert m.dialect == d
        assert m.arcs
        out[d] = [round(ly.extrude_length, 4) for ly in m.layers]
    assert len(out["bbl"]) == len(out["prusa"]) == 50
    for a, b in zip(out["bbl"], out["prusa"]):
        assert abs(a - b) <= 0.01 * max(a, 1e-9)
    # A 1 mm circle: 2 pi r of chords.
    assert abs(out["bbl"][0] - 2 * math.pi) < 0.01 * 2 * math.pi


def test_dialect_detect_and_features():
    assert D.detect(synth.cube("bbl")) == "bbl"
    assert D.detect(synth.cube("prusa")) == "prusa"
    assert D.detect("G1 X0\n") is None
    assert D.feature("External perimeter") == "Outer wall"
    assert D.feature("Overhang perimeter") == "Overhang wall"
    assert D.feature("Internal Bridge") == "Internal Bridge"


def test_travel_flags(tmp_path):
    p = tmp_path / "t.gcode"
    p.write_text(synth.towers("bbl", retract=0.8, wipe=True, zhop=0.4))
    m = L.build(str(p))
    long = [s for ly in m.layers for s in ly.travels() if s.length > 30]
    assert long and all(s.retracted for s in long)
    assert all(s.zhop for s in long)
    assert any(s.wiped for s in long)
