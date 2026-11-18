# SPDX-License-Identifier: AGPL-3.0-only
"""The layer model on top of orcalink's gcode_view (decision D2).

gcode_view replays the file: layers, features, widths, speeds, fan,
temperatures, retracts, wipes, seams, layer times. It keeps an arc (G2/G3)
as one straight step from its start to its end. This module takes those
steps by their G-code line and cuts each arc into chords with an error of
at most geom.arc_chord_mm (0.05 mm; the limit is 0.1 mm), and at most 2%
of the radius on small arcs. It adds the
travel flags that scoring needs: retracted, wiped and z-hop.

open_source(path, plate) accepts a .gcode file or a sliced .3mf
(.gcode.3mf) and gives the G-code path, the dialect and the project's
settings (for the filament profile).
"""
import hashlib
import json
import math
import os
import re
import zipfile

from .. import _orca, seeds
from . import dialect as D

_ARG = re.compile(r"([A-Za-z])\s*(-?\d*\.?\d+(?:[eE][-+]?\d+)?)")


class Seg:
    __slots__ = ("kind", "x0", "y0", "x1", "y1", "z", "feature", "width", "speed", "actual_speed", "fan", "flow", "actual_flow",
                 "line", "arc", "retracted", "wiped", "zhop")

    def __init__(self, kind, x0, y0, x1, y1, z, feature, line, width=None, speed=0.0, actual_speed=0.0, fan=0.0, flow=0.0, actual_flow=0.0, arc=False):
        self.kind, self.x0, self.y0, self.x1, self.y1, self.z = kind, x0, y0, x1, y1, z
        self.feature, self.line, self.width = feature, line, width
        self.speed, self.actual_speed, self.fan, self.flow, self.actual_flow = speed, actual_speed, fan, flow, actual_flow
        self.arc = arc
        self.retracted = self.wiped = self.zhop = False

    @property
    def length(self):
        return math.hypot(self.x1 - self.x0, self.y1 - self.y0)

    @property
    def mid(self):
        return ((self.x0 + self.x1) / 2.0, (self.y0 + self.y1) / 2.0)


class Layer:
    __slots__ = ("index", "z", "height", "segs", "time", "temp", "seams", "fan_mean")

    def __init__(self, index, z, height):
        self.index, self.z, self.height = index, z, height
        self.segs = []
        self.time = 0.0
        self.temp = None
        self.seams = []
        self.fan_mean = 0.0

    def extrusions(self, features=None):
        return [s for s in self.segs if s.kind == "extrude" and (features is None or s.feature in features)]

    def section(self, sample=0.1):
        """The layer's cross-section region: its extrusions plus the inside
        of its outer-wall loops (sparse infill counts as inside)."""
        from . import geom

        ext = [(s.x0, s.y0, s.x1, s.y1, s.width or 0.4) for s in self.segs if s.kind == "extrude"]
        walls = [(s.x0, s.y0, s.x1, s.y1) for s in self.segs if s.kind == "extrude" and s.feature == "Outer wall"]
        return geom.filled(ext, geom.loops(walls, tol=0.05, close_tol=1.0), sample)

    def travels(self):
        return [s for s in self.segs if s.kind == "travel"]

    @property
    def extrude_length(self):
        return sum(s.length for s in self.segs if s.kind == "extrude")


class LayerModel:
    def __init__(self, layers, header, dialect, arcs, sha256, path, summary):
        self.layers, self.header, self.dialect, self.arcs = layers, header, dialect, arcs
        self.sha256, self.path, self.summary = sha256, path, summary

    @property
    def top_z(self):
        return self.layers[-1].z if self.layers else 0.0


def arc_points(x0, y0, x1, y1, args, cw, tol):
    """The chord points (end included, start not) of an arc from (x0, y0)
    to (x1, y1). args: the line's I, J or R. Chord error <= tol."""
    if "I" in args or "J" in args:
        cx, cy = x0 + args.get("I", 0.0), y0 + args.get("J", 0.0)
    elif "R" in args:
        r = args["R"]
        dx, dy = x1 - x0, y1 - y0
        d = math.hypot(dx, dy)
        if d < 1e-12 or abs(r) < d / 2 - 1e-9:
            return [(x1, y1)]
        h = math.sqrt(max(0.0, r * r - d * d / 4))
        mx, my = (x0 + x1) / 2, (y0 + y1) / 2
        # The centre on the side that gives the short arc for R > 0 (G2: right of the chord).
        side = (-1 if cw else 1) * (1 if r > 0 else -1)
        cx, cy = mx - side * h * dy / d, my + side * h * dx / d
    else:
        return [(x1, y1)]
    r = math.hypot(x0 - cx, y0 - cy)
    a0 = math.atan2(y0 - cy, x0 - cx)
    a1 = math.atan2(y1 - cy, x1 - cx)
    sweep = (a0 - a1) % (2 * math.pi) if cw else (a1 - a0) % (2 * math.pi)
    if sweep < 1e-12:
        sweep = 2 * math.pi
    # The chord error is at most tol, and at most 2% of r: then the chord
    # length is within 0.7% of the arc length (about tol / 3r), so small
    # arcs keep the per-layer length within 1% of gcode_read's.
    tol = min(tol, 0.02 * r)
    if r <= 1e-9:
        n = 1
    else:
        step = 2 * math.acos(1 - tol / r)
        n = max(1, int(math.ceil(sweep / step)))
    pts = []
    for k in range(1, n + 1):
        a = a0 - sweep * k / n if cw else a0 + sweep * k / n
        pts.append((cx + r * math.cos(a), cy + r * math.sin(a)))
    pts[-1] = (x1, y1)
    return pts


def chord_error(x0, y0, x1, y1, args, cw, tol):
    """The largest distance of the chords from the true arc (for tests)."""
    pts = [(x0, y0)] + arc_points(x0, y0, x1, y1, args, cw, tol)
    cx, cy = x0 + args.get("I", 0.0), y0 + args.get("J", 0.0)
    r = math.hypot(x0 - cx, y0 - cy)
    worst = 0.0
    for (ax, ay), (bx, by) in zip(pts, pts[1:]):
        mx, my = (ax + bx) / 2, (ay + by) / 2
        worst = max(worst, r - math.hypot(mx - cx, my - cy))
    return worst


def open_source(path, plate=1, workdir=None):
    """(gcode_path, info) for a .gcode or a sliced .3mf. info: files (the
    archive's member names), md5 (a .gcode.md5 is there), settings (the
    project's settings JSON), plate."""
    info = {"plate": plate, "files": None, "md5": None, "settings": {}, "container": None}
    if path.lower().endswith(".3mf"):
        with zipfile.ZipFile(path) as z:
            names = z.namelist()
            info["files"] = sorted(names)
            info["container"] = path
            want = f"Metadata/plate_{int(plate)}.gcode"
            inner = want if want in names else None
            if inner is None:
                gc = sorted(n for n in names if n.endswith(".gcode"))
                if not gc:
                    raise ValueError(f"{os.path.basename(path)} holds no G-code: slice it first (orca_slice).")
                raise ValueError(f"plate {plate}: this file holds G-code for: {', '.join(gc)}.")
            info["md5"] = (inner + ".md5") in names
            if "Metadata/project_settings.config" in names:
                try:
                    info["settings"] = json.loads(z.read("Metadata/project_settings.config"))
                except ValueError:
                    info["settings"] = {}
            dest_dir = workdir or os.path.dirname(os.path.abspath(path))
            os.makedirs(dest_dir, exist_ok=True)
            dest = os.path.join(dest_dir, os.path.basename(path)[:-4] + f"-plate{int(plate)}.printloop.gcode")
            with z.open(inner) as src, open(dest, "wb") as f:
                f.write(src.read())
            return dest, info
    return path, info


def build(path, filament_diameter=1.75, tol=None, view=None):
    """The LayerModel of a .gcode file, on top of gcode_view.read."""
    G = view or _orca.gcode_view()
    tol = tol if tol is not None else seeds.Params()["geom.arc_chord_mm"]
    with open(path, "rb") as f:
        raw = f.read()
    sha = hashlib.sha256(raw).hexdigest()
    text = raw.decode("utf-8", errors="replace")
    lines = text.splitlines()
    dia = D.detect(text)
    data = G.read(path, keep_paths="all", filament_diameter=filament_diameter)
    summ = G.summary(data)
    arcs = False
    layers = []
    for gl in data["layers"]:
        ly = Layer(gl.index, gl.z, gl.height)
        ly.time = gl.time + gl.travel_time
        ly.temp = max(gl.temp) if gl.temp else None
        ly.seams = list(gl.seams)
        paths = iter(gl.paths)
        actual = iter(gl.actual_speeds)
        curz = gl.z
        lifted = False
        pending_retract = pending_wipe = False
        fans = []
        for st in gl.steps:
            kind, lineno, x0, y0, x1, y1, v, role = st
            code = lines[lineno - 1].split(";", 1)[0].strip() if 0 < lineno <= len(lines) else ""
            head = code.split()[0].upper() if code else ""
            args = {k.upper(): float(n) for k, n in _ARG.findall(code[len(head):])} if code else {}
            if "Z" in args:
                newz = args["Z"]
                lifted = newz > gl.z + 0.02
                curz = newz
            if kind == "retract":
                pending_retract = True
                continue
            feat = D.feature(role)
            if kind == "extrude":
                p = next(paths, None)
                a = next(actual, v)
                width = p[5] if p else 0.4
                fan = p[7] if p else 0.0
                flow = p[8] if p else 0.0
                aflow = flow * (a / v) if v else flow
                fans.append(fan)
                pending_retract = pending_wipe = False
                lifted = False
                pts = [(x1, y1)]
                is_arc = head in ("G2", "G3")
                if is_arc:
                    arcs = True
                    pts = arc_points(x0, y0, x1, y1, args, head == "G2", tol)
                px, py = x0, y0
                for qx, qy in pts:
                    ly.segs.append(Seg("extrude", px, py, qx, qy, gl.z, feat, lineno, width, v, a, fan, flow, aflow, is_arc))
                    px, py = qx, qy
                continue
            # travel or wipe
            if "E" in args and args["E"] < 0:
                pending_retract = True
            if kind == "wipe":
                pending_wipe = True
                pending_retract = True if "E" in args and args["E"] < 0 else pending_retract
            if math.hypot(x1 - x0, y1 - y0) < 1e-9:
                continue  # a pure Z move: the lift is kept in lifted
            pts = [(x1, y1)]
            is_arc = head in ("G2", "G3")
            if is_arc:
                arcs = True
                pts = arc_points(x0, y0, x1, y1, args, head == "G2", tol)
            px, py = x0, y0
            for qx, qy in pts:
                s = Seg(kind, px, py, qx, qy, curz, feat, lineno, None, v, v, 0.0, 0.0, 0.0, is_arc)
                s.retracted, s.wiped, s.zhop = pending_retract, pending_wipe, lifted or curz > gl.z + 0.02
                ly.segs.append(s)
                px, py = qx, qy
        ly.fan_mean = sum(fans) / len(fans) if fans else 0.0
        layers.append(ly)
    return LayerModel(layers, data["header"], dia, arcs, sha, path, summ)
