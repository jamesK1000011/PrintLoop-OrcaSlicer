# SPDX-License-Identifier: AGPL-3.0-only
"""Score a sliced plate and build the ScoreReport (§16.3, §16.4).

score_file(path, plate, context, baseline, printer, filament) reads the
G-code (a .gcode or a sliced .3mf), builds the layer model on gcode_view,
runs the five domains and gives the report. The overall score is the
lowest domain score; a domain without a score (collision when unaligned)
is left out of it.
"""
import json
import os
import time
import types
import xml.etree.ElementTree as ET
import zipfile

from .. import align, ids, paths, schema, seeds
from ..gcode import dialect as D
from ..gcode import layers as L
from .common import Profile, domain_score
from .domains import collision, overhang, stringing, thermal, warp

DOMAINS = (stringing, overhang, warp, thermal, collision)


def _warnings(container):
    if not container:
        return []
    try:
        with zipfile.ZipFile(container) as z:
            if "Metadata/slice_info.config" not in z.namelist():
                return []
            root = ET.fromstring(z.read("Metadata/slice_info.config"))
    except (OSError, zipfile.BadZipFile, ET.ParseError):
        return []
    out = []
    for w in root.iter("warning"):
        try:
            lvl = int(w.get("level", 1))
        except ValueError:
            lvl = 1
        out.append({"level": lvl, "code": w.get("error_code") or w.get("code") or "", "msg": w.get("msg") or ""})
    return out


def _baseline(baseline):
    if not baseline:
        return None
    if isinstance(baseline, dict):
        return baseline
    p = os.path.expanduser(str(baseline))
    if not os.path.isfile(p) and "/" in str(baseline):
        run, n = str(baseline).rsplit("/", 1)
        p = os.path.join(paths.home(), "runs", run, n, "report.json")
    if not os.path.isfile(p):
        raise FileNotFoundError(f"baseline {baseline}: no such report (a report.json path, or an iteration_id run_id/n).")
    with open(p, encoding="utf-8") as f:
        return json.load(f)


def _params(printer, filament, overrides=None):
    over = dict(overrides or {})
    if printer and filament:
        try:
            from ..calib import store

            over = {**store.params(printer, filament), **over}
        except Exception:  # noqa: BLE001 - no store yet: seeds only
            pass
    return seeds.Params(over)


def _ctx(context, container, plate, printer):
    ctx = align.load_context(context)
    # aligned: set by the FreeCAD side after the fiducial passed, or the
    # fiducial result stored for this printer and plate setup (§16.3).
    aligned = bool(ctx.get("aligned")) or bool(printer and align.is_aligned(printer, ctx.get("setup") or f"plate{plate}"))
    mapper = None
    if aligned and container:
        try:
            mapper = align.Mapper(container, ctx.get("orca_object"), int(ctx.get("instance", 0)), plate, align.placement_matrix(ctx))
        except Exception:  # noqa: BLE001 - no project to map with
            mapper = None
    return types.SimpleNamespace(context=ctx, mapper=mapper, aligned=bool(aligned and mapper is not None), has=bool(ctx))


def score_model(model, prof, params, ctx, base=None):
    out = {}
    nhot = int(params["report.hot_spots"])
    for dom in DOMAINS:
        name = dom.NAME
        if name == "collision" and not ctx.aligned:
            status = "unaligned" if ctx.has else "no_context"
            out[name] = {"score": None, "delta": None, "critical": False, "status": status, "p95_risk": 0.0, "max_risk": 0.0, "hot_spots": []}
            continue
        risks, hots = dom.score(model, prof, params, ctx)
        if name == "warp":
            sc, crit, p95, mx = warp.domain_score(risks, params)
        else:
            sc, crit, p95, mx = domain_score(risks, params)
        hots.sort(key=lambda h: -h.risk)
        hs = []
        for h in hots[:nhot]:
            if ctx.aligned and h.model_xyz is None and h.xy is not None:
                h.model_xyz = ctx.mapper(h.xy[0], h.xy[1], h.z)
            if not ctx.aligned:
                h.model_xyz = None
            hs.append(h.as_dict())
        prev = (((base or {}).get("domains") or {}).get(name) or {}).get("score")
        out[name] = {"score": sc, "delta": (sc - prev) if prev is not None else None, "critical": bool(crit), "status": "ok",
                     "p95_risk": round(min(1.0, p95), 4), "max_risk": round(min(1.0, mx), 4), "hot_spots": hs}
    return out


def score_file(path, plate=1, context=None, baseline=None, printer=None, filament=None, run_id=None, iteration=0, overrides=None,
               workdir=None, profile=None):
    t0 = time.time()
    path = os.path.expanduser(path)
    # A sliced .3mf's G-code is copied out to the user folder's cache, not
    # beside the person's file.
    gpath, info = L.open_source(path, plate, workdir or os.path.join(paths.home(), "cache"))
    model = L.build(gpath)
    settings = dict(info.get("settings") or {})
    settings.update(profile or {})
    prof = Profile(settings)
    params = _params(printer, filament, overrides)
    ctx = _ctx(context, info.get("container"), plate, printer)
    base = _baseline(baseline)
    domains = score_model(model, prof, params, ctx, base)
    scored = [d for d in domains.values() if d["score"] is not None]
    overall = min(d["score"] for d in scored) if scored else 100
    prev = ((base or {}).get("overall") or {}).get("score")
    with open(gpath, encoding="utf-8", errors="replace") as f:
        head = f.read(4000)
    fs = settings.get("filament_settings_id")
    fil = filament or (fs[0] if isinstance(fs, list) and fs else fs if isinstance(fs, str) else None)
    rep = {
        "schema": "printloop.score_report/1",
        "report_id": ids.ulid(),
        "run_id": run_id,
        "iteration": int(iteration),
        "source": {"path": path, "plate": int(plate), "gcode_sha256": model.sha256, "dialect": model.dialect, "arcs": bool(model.arcs),
                   "orca_version": D.orca_version(head), "md5": info.get("md5")},
        "printer": printer or (settings.get("printer_settings_id") if isinstance(settings.get("printer_settings_id"), str) else None),
        "filament": fil,
        "overall": {"score": int(overall), "critical": any(d["critical"] for d in domains.values()), "delta": (overall - prev) if prev is not None else None},
        "domains": domains,
        "orca_warnings": _warnings(info.get("container")),
        "inputs": {"params_source": {"calib": params.from_calib, "defaults": True}},
        "timing_ms": int((time.time() - t0) * 1000),
    }
    return rep


def validate(rep):
    return schema.errors(rep, "score_report")
