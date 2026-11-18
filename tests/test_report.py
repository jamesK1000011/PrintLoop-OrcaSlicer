# SPDX-License-Identifier: AGPL-3.0-only
# The ScoreReport (§16.3): it validates against its schema; overall is the
# lowest domain score; deltas against a baseline; at most 20 hot spots;
# model_xyz is null unless aligned. Performance is logged (the target is
# for the MacBook Air with shapely).
import json
import os
import time

import synth
from printloop import schema
from printloop.score import report as R

MAC = os.path.join(os.path.dirname(__file__), "fixtures", "mac")


def test_real_reports_validate(tmp_path):
    for f in ("cube_overhang_h2d.gcode.3mf", "cube_overhang_prusa.gcode.3mf", "prusa_dialect_sample.gcode"):
        r = R.score_file(os.path.join(MAC, f), workdir=str(tmp_path))
        assert schema.errors(r, "score_report") == []
        assert schema.errors_builtin(r, "score_report") == []
        scored = [d["score"] for d in r["domains"].values() if d["score"] is not None]
        assert r["overall"]["score"] == min(scored)
        assert r["domains"]["collision"]["status"] == "no_context"
        for d in r["domains"].values():
            assert len(d["hot_spots"]) <= 20
            assert all(h["model_xyz"] is None for h in d["hot_spots"])
    assert r["source"]["dialect"] == "prusa"


def test_h2d_source_facts(tmp_path):
    r = R.score_file(os.path.join(MAC, "cube_overhang_h2d.gcode.3mf"), workdir=str(tmp_path))
    s = r["source"]
    assert (s["dialect"], s["arcs"], s["orca_version"], s["md5"]) == ("bbl", True, "2.5.0", True)
    assert r["filament"] == "Bambu PLA Basic @BBL H2D"


def test_baseline_delta(tmp_path):
    p1, p2 = tmp_path / "a.gcode", tmp_path / "b.gcode"
    p1.write_text(synth.towers("bbl"))
    p2.write_text(synth.towers("bbl", retract=0.8, wipe=True))
    a = R.score_file(str(p1))
    bp = tmp_path / "a.json"
    bp.write_text(json.dumps(a))
    b = R.score_file(str(p2), baseline=str(bp))
    assert b["domains"]["stringing"]["delta"] == b["domains"]["stringing"]["score"] - a["domains"]["stringing"]["score"]
    assert b["overall"]["delta"] == b["overall"]["score"] - a["overall"]["score"]


def test_broken_report_fails_schema(tmp_path):
    p = tmp_path / "a.gcode"
    p.write_text(synth.cube("bbl"))
    r = R.score_file(str(p))
    r["domains"]["warp"]["status"] = "bad"
    del r["overall"]["critical"]
    assert schema.errors(r, "score_report")
    assert schema.errors_builtin(r, "score_report")


def test_calib_params_override(tmp_path):
    from printloop.calib import store

    p = tmp_path / "t.gcode"
    p.write_text(synth.towers("bbl", retract=0.8))
    a = R.score_file(str(p), printer="h2d-test", filament="PLA test")
    store.set_param("h2d-test", "PLA test", "stringing.D0", 100.0, "test")
    b = R.score_file(str(p), printer="h2d-test", filament="PLA test")
    assert b["inputs"]["params_source"]["calib"] is True
    assert b["domains"]["stringing"]["score"] > a["domains"]["stringing"]["score"]


def test_performance_logged(tmp_path, capsys):
    t = time.time()
    R.score_file(os.path.join(MAC, "cube_overhang_h2d.gcode.3mf"), workdir=str(tmp_path))
    dt = time.time() - t
    # 100 layers, 15 min print: the 6 h plate target (60 s) waits for the Mac.
    assert dt < 30
