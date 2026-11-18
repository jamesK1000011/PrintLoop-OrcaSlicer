# SPDX-License-Identifier: AGPL-3.0-only
# Spike step 7: the loop. On the stringing fixture at dial 3 the runner
# improves the overall score and exits plateau or clean within the caps.
# At dial 1 a CAD edit stops at a gate, and approve without the token is
# refused. A synthetic slicer stands in for orca_slice (it needs the Mac).
import json
import os
import time

import pytest

from synth_slicer import SynthSlicer, project
from printloop.loop import policy, runner


def test_dial3_stringing_improves_and_exits(tmp_path):
    sl = SynthSlicer()
    st = runner.start(project(str(tmp_path / "towers.json")), sl, dial=3)
    pub = runner.public(st)
    assert pub["state"] == "done", pub
    assert pub["exit_reason"] in ("plateau", "clean")
    h = pub["history"]
    assert h[-1]["overall"] > h[0]["overall"]
    assert pub["used"]["slicer"] <= pub["caps"]["slicer"]
    assert h[1]["changed"]["family"] == "retraction"
    # Run copies only: the original project is unchanged.
    assert json.load(open(tmp_path / "towers.json"))["retraction_length"] == ["0"]
    d = os.path.join(os.environ["PRINTLOOP_HOME"], "runs", pub["run_id"], "1")
    for f in ("report.json", "project.3mf", "overrides.json", "gcode.sha256"):
        assert os.path.isfile(os.path.join(d, f)), f
    assert json.load(open(os.path.join(d, "overrides.json")))["retraction_length"] == ["0.2"]
    from printloop import schema

    assert schema.errors(pub, "run_state") == []


def cad_gate(tmp_path):
    sl = SynthSlicer()
    st = runner.start(project(str(tmp_path / "spire.json"), shape="spire"), sl, dial=1)
    return sl, runner.public(st)


def test_dial1_cad_edit_stops_at_gate(tmp_path):
    sl, pub = cad_gate(tmp_path)
    assert pub["state"] == "input_required", pub
    assert pub["gate"]["kind"] == "cad_edit"
    assert pub["gate"]["proposal"]["domain"] == "thermal"
    assert len(pub["gate"]["token_hint"].split()[1]) == 4
    # Slicer families ran without a stop at dial 1.
    assert pub["used"]["slicer"] >= 1
    with pytest.raises(PermissionError):
        runner.approve(pub["run_id"], pub["gate"]["gate_id"], None, sl)
    with pytest.raises(PermissionError):
        runner.approve(pub["run_id"], pub["gate"]["gate_id"], "ZZZZ", sl)
    with pytest.raises(PermissionError):
        runner.step(pub["run_id"], sl)  # a step does not pass an open gate
    tok = pub["gate"]["token_hint"].split()[1]
    st = runner.public(runner.approve(pub["run_id"], pub["gate"]["gate_id"], tok.lower(), sl))
    assert st["state"] == "running" and st["next"]["do"] == "cad_edit"
    # The agent made the edit in FreeCAD and replaced the part: the loop goes on.
    edited = project(str(tmp_path / "spire2.json"), shape="towers", retraction_length=["0.8"], wipe=["1"])
    st = runner.public(runner.step(pub["run_id"], sl, edited))
    assert st["used"]["cad"] == 1
    assert any((h["changed"] or {}).get("cad") for h in st["history"])


def test_token_too_old(tmp_path):
    sl, pub = cad_gate(tmp_path)
    tok = pub["gate"]["token_hint"].split()[1]
    with pytest.raises(PermissionError, match="24 h"):
        runner.approve(pub["run_id"], pub["gate"]["gate_id"], tok, sl, now=time.time() + 25 * 3600)


def test_dial0_gates_every_iteration(tmp_path):
    sl = SynthSlicer()
    st = runner.public(runner.start(project(str(tmp_path / "t.json")), sl, dial=0))
    assert st["state"] == "input_required" and st["gate"]["kind"] == "slicer_step"
    assert sl.calls == 0  # not even the first slice before approval
    tok = st["gate"]["token_hint"].split()[1]
    st = runner.public(runner.approve(st["run_id"], st["gate"]["gate_id"], tok, sl))
    assert sl.calls == 1 and st["gate"]["kind"] == "slicer_step"
    st = runner.public(runner.approve(st["run_id"], st["gate"]["gate_id"], st["gate"]["token_hint"].split()[1], sl, decision="reject"))
    assert st["state"] in ("input_required", "done")


def test_caps_exhausted_escalates(tmp_path, monkeypatch):
    from printloop import paths

    paths.save_config({"caps": {"2": {"slicer": 1, "cad": 0}}})
    sl = SynthSlicer()
    st = runner.public(runner.start(project(str(tmp_path / "s.json"), shape="spire"), sl, dial=2))
    assert st["state"] == "escalated" and st["gate"]["kind"] == "cap_exhausted"


def test_stop_and_status(tmp_path):
    sl, pub = cad_gate(tmp_path)
    assert runner.public(runner.status(pub["run_id"]))["state"] == "input_required"
    st = runner.public(runner.stop(pub["run_id"]))
    assert st["state"] == "stopped" and st["gate"] is None


def test_always_gated():
    for k in ("preset_write", "calib_reset", "cap_exhausted"):
        assert all(policy.needs_gate(k, d) for d in range(4))
    assert not policy.needs_gate("cad_edit", 2)
    assert policy.needs_gate("cad_edit", 1)
