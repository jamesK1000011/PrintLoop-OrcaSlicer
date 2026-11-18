# SPDX-License-Identifier: AGPL-3.0-only
# Spike step 5: each domain has a fixture that raises it and one that does
# not; the raising one scores at least 20 points lower. Synthetic fixtures
# (tests/fixtures/synth.py) in both dialects; the Mac slices of §16.9
# (stringing_towers, overhang60, tall_abs, spire) replace them later.
import os

import pytest

import synth
from printloop.gcode import geom
from printloop.score import report as R

PAIRS = {
    "stringing": (lambda d: synth.towers(d), lambda d: synth.towers(d, single=True), None),
    "overhang": (lambda d: synth.overhang(d, 60), lambda d: synth.overhang(d, 0), None),
    "warp": (lambda d: synth.tall_thin(d), lambda d: synth.cube(d), {"filament_type": ["ABS"]}),
    "thermal": (lambda d: synth.spire(d), lambda d: synth.cube(d), None),
}


def score(tmp_path, name, text, profile=None):
    p = tmp_path / f"{name}.gcode"
    p.write_text(text)
    return R.score_file(str(p), profile=profile)


@pytest.mark.parametrize("dialect", ["bbl", "prusa"])
@pytest.mark.parametrize("domain", sorted(PAIRS))
def test_raising_fixture_scores_20_lower(tmp_path, dialect, domain):
    hi, lo, prof = PAIRS[domain]
    a = score(tmp_path, "hi", hi(dialect), prof)["domains"][domain]
    b = score(tmp_path, "lo", lo(dialect), None)["domains"][domain]
    assert a["status"] == b["status"] == "ok"
    assert b["score"] - a["score"] >= 20, (a["score"], b["score"])
    assert a["hot_spots"], "the raising fixture names where"


def test_retraction_lowers_stringing(tmp_path):
    raw = score(tmp_path, "raw", synth.towers("bbl"))["domains"]["stringing"]["score"]
    ret = score(tmp_path, "ret", synth.towers("bbl", retract=0.8, wipe=True))["domains"]["stringing"]["score"]
    assert ret > raw


def test_overhang_rises_with_angle(tmp_path):
    s = [score(tmp_path, f"o{a}", synth.overhang("bbl", a))["domains"]["overhang"]["score"] for a in (0, 45, 60, 70)]
    assert s[0] == 100 and s[1] >= s[2] > s[3]


def test_real_h2d_names_the_ledge(tmp_path):
    r = R.score_file(os.path.join(os.path.dirname(__file__), "fixtures", "mac", "cube_overhang_h2d.gcode.3mf"),
                     workdir=str(tmp_path))
    oh = r["domains"]["overhang"]
    # The 10 mm ledge at z 16-20 has no support: its first layer (81) is in the air.
    assert oh["hot_spots"][0]["layer"] == 81
    assert oh["critical"]
    assert r["domains"]["warp"]["score"] >= 90


@pytest.mark.parametrize("which", ["python"] + (["shapely"] if geom.HAVE_SHAPELY else []))
def test_backends(which, tmp_path):
    geom.use(which)
    try:
        r = score(tmp_path, "c", synth.cube("bbl"))
        assert r["overall"]["score"] >= 90
    finally:
        geom.use(None)
