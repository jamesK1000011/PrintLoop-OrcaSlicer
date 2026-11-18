# SPDX-License-Identifier: AGPL-3.0-only
"""The loop runner (§16.5.4): slice, score, decide, change one family,
slice again. It works on run copies of the project
(~/AgentLink/printloop/runs/<run_id>/<n>/project.3mf); the original
project is never changed. It never starts a print.

    start -> slice(n=0) -> score -> decide
    decide:
      no CRITICAL and n == 0 and overall >= 90         -> done (clean)
      no CRITICAL and n >= 2 and last 2 deltas sum < 2  -> done (plateau)
      caps exhausted                                     -> escalated (gate cap_exhausted)
      next action needs a gate at this dial level        -> input_required
      else apply one family (or a CAD op) -> slice(n+1) -> score -> decide
    regression: overall delta < -3 -> revert that change, mark the family
    tried, continue.

Changes (§17): a domain at or above the clean score (90) picks no family;
when no domain is below it and nothing is CRITICAL, the run is done
(clean) at any n. A CAD edit is done by the agent in FreeCAD; the runner
proposes it (next.do = cad_edit) and continues when print_loop step gets
the changed project in path.
"""
import json
import os
import shutil
import time

from .. import ids, paths, schema, seeds
from ..score import common, report
from . import knobs, policy



class Slicer:
    """The slicing adapter. Real: OrcalinkSlicer. Tests: a synthetic one."""

    def settings(self, project):
        raise NotImplementedError

    def apply(self, src, dest, overrides):
        raise NotImplementedError

    def slice(self, project, plate):
        raise NotImplementedError


class OrcalinkSlicer(Slicer):
    """Through orcalink: orca3mf to set the run copy's settings (checked
    against OrcaSlicer's table) and orcalink's orca_slice to slice it."""

    def __init__(self, tools):
        self.tools = tools

    def settings(self, project):
        from .. import _orca

        return dict(_orca.orca3mf().Project(project).config)

    def apply(self, src, dest, overrides):
        from .. import _orca

        pr = _orca.orca3mf().Project(src)
        for k, v in overrides.items():
            pr.set(k, v)
        pr.save(dest)

    def slice(self, project, plate):
        fn = self.tools.get("orca_slice")
        if fn is None:
            raise RuntimeError("orca_slice is not here: run PrintLoop inside OrcaSlicer Agent Link.")
        out = fn({"path": project, "plate": plate})
        sliced = out.get("sliced")
        if not sliced:
            raise RuntimeError(f"orca_slice gave no sliced project: {json.dumps(out)[:300]}")
        return sliced


def _state_path(run_id):
    return os.path.join(paths.run_dir(run_id), "state.json")


def load(run_id):
    p = _state_path(run_id)
    if not os.path.isfile(p):
        raise FileNotFoundError(f"run_id {run_id}: no such run.")
    with open(p, encoding="utf-8") as f:
        return json.load(f)


def save(st):
    p = _state_path(st["run_id"])
    tmp = p + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(st, f, indent=1)
    os.replace(tmp, p)


def public(st):
    out = {k: v for k, v in st.items() if not k.startswith("_")}
    out["gate"] = policy.public(st.get("_gate"))
    return out


def _report(st, n):
    with open(os.path.join(paths.run_dir(st["run_id"], n), "report.json"), encoding="utf-8") as f:
        return json.load(f)


def _iterate(st, slicer, n, changed):
    d = paths.run_dir(st["run_id"], n)
    proj = os.path.join(d, "project.3mf")
    slicer.apply(st["_base"], proj, st["_overrides"])
    with open(os.path.join(d, "overrides.json"), "w", encoding="utf-8") as f:
        json.dump(st["_overrides"], f, indent=1)
    sliced = slicer.slice(proj, st["_plate"])
    base = None
    if st.get("_baseline") is not None:
        base = _report(st, st["_baseline"])
    prof = dict(slicer.settings(proj))
    prof.update(st.get("_profile") or {})
    rep = report.score_file(sliced, st["_plate"], st.get("_context"), base, st.get("_printer"), st.get("_filament"),
                            run_id=st["run_id"], iteration=n, workdir=d, profile=prof)
    errs = schema.errors(rep, "score_report")
    if errs:
        raise RuntimeError("score report does not match its schema: " + "; ".join(errs[:3]))
    with open(os.path.join(d, "report.json"), "w", encoding="utf-8") as f:
        json.dump(rep, f, indent=1)
    with open(os.path.join(d, "gcode.sha256"), "w", encoding="utf-8") as f:
        f.write(rep["source"]["gcode_sha256"] + "\n")
    st["iteration"] = n
    st["history"].append({"n": n, "report_id": rep["report_id"], "overall": rep["overall"]["score"], "changed": changed,
                          "delta": rep["overall"]["delta"], "critical": rep["overall"]["critical"]})
    return rep


def start(project, slicer, plate=1, context=None, dial=None, printer=None, filament=None, profile=None):
    project = os.path.expanduser(project)
    if not os.path.isfile(project):
        raise FileNotFoundError(f"path {project}: no such project.")
    dl = policy.dial_level(dial)
    run_id = ids.ulid()
    st = {"run_id": run_id, "state": "running", "dial": dl, "iteration": 0, "caps": policy.caps(dl), "used": {"slicer": 0, "cad": 0},
          "history": [], "gate": None, "exit_reason": None, "next": None,
          "_base": os.path.join(paths.run_dir(run_id), "base.3mf"), "_plate": int(plate), "_context": context, "_printer": printer,
          "_filament": filament, "_overrides": {}, "_tried": [], "_pending": None, "_gate": None, "_baseline": None, "_profile": profile}
    shutil.copyfile(project, st["_base"])
    st["source"] = project
    if policy.needs_gate("slicer_step", dl):
        # Dial 0: a gate before every iteration, the first slice too.
        return _gate(st, "slicer_step", {"do": "slice", "n": 0, "changed": None}, {"n": 0, "changed": None})
    _iterate(st, slicer, 0, None)
    st["_baseline"] = 0
    return advance(st, slicer)


def _gate(st, kind, proposal, pending):
    st["_gate"] = policy.new_gate(kind, proposal)
    st["_pending"] = pending
    st["state"] = "escalated" if kind == "cap_exhausted" else "input_required"
    save(st)
    return st


def _done(st, why):
    st["state"] = "done"
    st["exit_reason"] = why
    st["next"] = None
    save(st)
    return st


def _cad_proposal(st, rep, domain):
    cad = seeds.load("knobs")["cad"]
    ops = [o for o in cad["ops"] if o["for"] == domain] or cad["ops"][:1]
    hots = rep["domains"][domain]["hot_spots"][:5]
    keep = [f.get("face") for f in ((st.get("_context") or {}).get("keepout_faces") or [])]
    return {"do": "cad_edit", "domain": domain, "ops": ops, "near": [{"layer": h["layer"], "z": h["z"], "xy": h["xy"], "model_xyz": h["model_xyz"]} for h in hots],
            "never": {"rule": cad["never"], "faces": keep},
            "then": "Make the edit in FreeCAD (feature tools; tool_groups gives their names). Run FEM again if a study exists. "
                    "Then orca_project replace, then print_loop step with run_id and path (the changed project)."}


def _next_action(st, rep):
    """('slicer', family, changes, domain) or ('cad', None, proposal, domain) or (None, ...)."""
    clean = policy.table()["exit"]["clean_score"]
    doms = [(d["score"], name) for name, d in rep["domains"].items() if d["score"] is not None]
    doms.sort()
    settings = st.get("_settings") or {}
    prof = common.Profile(settings)
    for score, name in doms:
        if score >= clean and not rep["domains"][name]["critical"]:
            continue
        for fam in knobs.for_domain(name, st["_tried"]):
            ch = knobs.changes(fam, settings, prof, name)
            if ch:
                return "slicer", fam["family"], ch, name
            st["_tried"].append(fam["family"])  # nothing to change here
        if rep["domains"][name]["critical"]:
            return "cad", None, _cad_proposal(st, rep, name), name
    return None, None, None, None


def advance(st, slicer, max_steps=50):
    """Run the loop until it is done, needs a gate, waits for a CAD edit,
    or stops."""
    xt = policy.table()["exit"]
    for _ in range(max_steps):
        if st["state"] != "running":
            break
        hist = st["history"]
        last = hist[-1]
        n = last["n"]
        base_n = st["_baseline"] if st["_baseline"] is not None else n
        rep = _report(st, base_n)
        st["_settings"] = slicer.settings(os.path.join(paths.run_dir(st["run_id"], base_n), "project.3mf"))
        crit = rep["overall"]["critical"]
        if not crit and n == 0 and rep["overall"]["score"] >= xt["clean_score"]:
            return _done(st, "clean")
        live = [h for h in hist if not h.get("reverted")]
        deltas = [h["delta"] for h in live[1:] if h.get("delta") is not None]
        if not crit and n >= xt["plateau_window"] and len(deltas) >= xt["plateau_window"] and sum(deltas[-xt["plateau_window"]:]) < xt["plateau_delta"]:
            return _done(st, "plateau")
        kind, fam, ch, dom = _next_action(st, rep)
        if kind is None:
            return _done(st, "clean" if all((d["score"] or 100) >= xt["clean_score"] for d in rep["domains"].values()) else "families_tried")
        if kind == "slicer" and st["used"]["slicer"] >= st["caps"]["slicer"]:
            if crit and st["used"]["cad"] < st["caps"]["cad"]:
                kind, fam, ch = "cad", None, _cad_proposal(st, rep, dom)
            else:
                return _gate(st, "cap_exhausted", {"used": st["used"], "caps": st["caps"], "overall": rep["overall"]["score"]}, {"cap": "slicer"})
        if kind == "cad" and st["used"]["cad"] >= st["caps"]["cad"]:
            return _gate(st, "cap_exhausted", {"used": st["used"], "caps": st["caps"], "overall": rep["overall"]["score"]}, {"cap": "cad"})
        if kind == "slicer":
            pending = {"family": fam, "set": ch, "domain": dom}
            if policy.needs_gate("slicer_step", st["dial"]):
                return _gate(st, "slicer_step", {"do": "slicer_step", **pending}, pending)
            _apply_slicer(st, slicer, pending)
        else:
            if policy.needs_gate("cad_edit", st["dial"]):
                return _gate(st, "cad_edit", ch, {"cad": ch})
            st["next"] = ch
            st["state"] = "running"
            save(st)
            return st  # the agent does the CAD edit, then print_loop step with path
    save(st)
    return st


def _apply_slicer(st, slicer, pending):
    fam, ch = pending["family"], pending["set"]
    before = {k: st["_overrides"].get(k) for k in ch}
    st["_overrides"].update(ch)
    st["_tried"].append(fam)
    st["used"]["slicer"] += 1
    n = st["history"][-1]["n"] + 1
    rep = _iterate(st, slicer, n, {"family": fam, "set": ch})
    d = rep["overall"]["delta"]
    if d is not None and d < policy.table()["exit"]["regression_delta"]:
        for k, v in before.items():
            if v is None:
                st["_overrides"].pop(k, None)
            else:
                st["_overrides"][k] = v
        st["history"][-1]["reverted"] = True
    else:
        st["_baseline"] = n
    save(st)


def step(run_id, slicer, path=None):
    st = load(run_id)
    if st["state"] in ("done", "stopped"):
        return st
    if st.get("_gate") is not None:
        raise PermissionError(f"gate {st['_gate']['gate_id']} is open ({st['_gate']['kind']}): the person approves it with print_approve.")
    if st.get("next") and st["next"].get("do") == "cad_edit":
        if not path:
            raise ValueError("path: the project after the CAD edit (orca_project replace), as next.then says.")
        path = os.path.expanduser(path)
        if not os.path.isfile(path):
            raise FileNotFoundError(f"path {path}: no such project.")
        shutil.copyfile(path, st["_base"])
        st["used"]["cad"] += 1
        st["next"] = None
        n = st["history"][-1]["n"] + 1
        _iterate(st, slicer, n, {"cad": (st.get("_pending") or {}).get("cad") or True})
        st["_baseline"] = n
        st["_pending"] = None
    return advance(st, slicer)


def approve(run_id, gate_id, token, slicer, decision="approve", now=None):
    st = load(run_id)
    why = policy.check_token(st.get("_gate"), gate_id, token, now)
    if why:
        raise PermissionError(why)
    gate, pending = st["_gate"], st.get("_pending") or {}
    st["_gate"] = None
    st["state"] = "running"
    if decision == "reject":
        if gate["kind"] == "slicer_step" and pending.get("family"):
            st["_tried"].append(pending["family"])
            st["_pending"] = None
            save(st)
            return advance(st, slicer)
        if gate["kind"] == "slicer_step" and pending.get("n") == 0:
            st["_pending"] = None
            return _stop(st, "rejected")
        st["_pending"] = None
        return _stop(st, "rejected")
    if gate["kind"] == "slicer_step":
        st["_pending"] = None
        if pending.get("n") == 0:
            _iterate(st, slicer, 0, None)
            st["_baseline"] = 0
        else:
            _apply_slicer(st, slicer, pending)
        return advance(st, slicer)  # at dial 0 the next iteration opens a new gate
    if gate["kind"] == "cad_edit":
        st["next"] = pending.get("cad")
        save(st)
        return st
    if gate["kind"] == "cap_exhausted":
        which = pending.get("cap", "slicer")
        st["caps"][which] += 2 if which == "slicer" else 1
        st["_pending"] = None
        save(st)
        return advance(st, slicer)
    save(st)
    return st


def _stop(st, why):
    st["state"] = "stopped"
    st["exit_reason"] = why
    st["next"] = None
    st["_gate"] = None
    save(st)
    return st


def stop(run_id):
    return _stop(load(run_id), "stopped by request")


def status(run_id):
    return load(run_id)


def now():
    return time.time()
