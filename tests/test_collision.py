# SPDX-License-Identifier: AGPL-3.0-only
# Spike step 6: on the fiducial with a synthetic stress peak, a seam on the
# peak scores lower than a seam away from it. Without alignment the domain
# is unaligned and has no score.
from test_align import make

from printloop.score import report as R

PEAK = {"aligned": True, "stress": {"study": "FEMStudy", "max_vm_mpa": 31.2, "peaks": [{"xyz": [6.0, 15.0, 20.0], "vm_mpa": 29.8, "ratio": 0.96}]}}


def test_seam_on_peak_scores_lower(tmp_path):
    on = make(tmp_path, 90, (150, 60), "on.gcode.3mf", seam=(6.0, 15.0))
    off = make(tmp_path, 90, (150, 60), "off.gcode.3mf", seam=(0.0, 0.0))
    a = R.score_file(on, context=PEAK, workdir=str(tmp_path))["domains"]["collision"]
    b = R.score_file(off, context=PEAK, workdir=str(tmp_path))["domains"]["collision"]
    assert a["status"] == b["status"] == "ok"
    assert a["score"] < b["score"], (a["score"], b["score"])
    hs = a["hot_spots"][0]
    assert hs["model_xyz"] is not None
    assert abs(hs["model_xyz"][2] - 20.0) <= 1.0
    assert "stress peak" in hs["why"]


def test_keepout_face(tmp_path):
    ctx = {"aligned": True, "keepout_faces": [{"face": "Face12", "reason": "fit", "tol_mm": 0.1, "samples": [[6.0, 15.0, 10.0]]}]}
    on = make(tmp_path, 0, (100, 100), "k.gcode.3mf", seam=(6.0, 15.0))
    r = R.score_file(on, context=ctx, workdir=str(tmp_path))["domains"]["collision"]
    assert r["score"] < 100 and "keep-out" in r["hot_spots"][0]["why"]


def test_unaligned(tmp_path):
    on = make(tmp_path, 0, (100, 100), "u.gcode.3mf", seam=(6.0, 15.0))
    ctx = dict(PEAK, aligned=False)
    r = R.score_file(on, context=ctx, workdir=str(tmp_path))
    assert r["domains"]["collision"]["status"] == "unaligned"
    assert r["domains"]["collision"]["score"] is None
    assert all(h["model_xyz"] is None for d in r["domains"].values() for h in d["hot_spots"])
