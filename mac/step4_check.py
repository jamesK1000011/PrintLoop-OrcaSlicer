#!/usr/bin/env python3
# SPDX-License-Identifier: AGPL-3.0-only
"""Spike step 4, part 2: the mapping check on a real slice of the fiducial.

    python3 mac/step4_check.py <fiducial_L-sliced.3mf> [--plate 1] [--printer h2d] [--setup plate1] [--store]

It maps the corners of the second and top layers' outer walls from G-code
to model coordinates (build-item x component transform, source_offset) and
compares them with the three known vertices of the L-bracket:
(40, 0, 0), (38, 21, 0), (6, 15, 29). Pass: each within 0.2 mm.
--store records the result as aligned in ~/AgentLink/printloop/config.json.
It reads files only (and config.json with --store). Needs orcalink: put
AgentLink-OrcaSlicer beside this repository or set ORCALINK_PATH.
"""
import argparse
import json
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))

from printloop import align  # noqa: E402
from printloop.gcode import layers as L  # noqa: E402

VERTICES = [(40.0, 0.0, 0.0), (38.0, 21.0, 0.0), (6.0, 15.0, 29.0)]


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("sliced")
    ap.add_argument("--plate", type=int, default=1)
    ap.add_argument("--object", default=None)
    ap.add_argument("--printer", default="h2d")
    ap.add_argument("--setup", default=None)
    ap.add_argument("--store", action="store_true")
    a = ap.parse_args(argv)
    g, info = L.open_source(os.path.expanduser(a.sliced), a.plate)
    model = L.build(g)
    mapper = align.Mapper(os.path.expanduser(a.sliced), a.object, 0, a.plate)
    res = align.fiducial_check(model, mapper, VERTICES)
    res["object"] = mapper.object
    res["layers"] = len(model.layers)
    res["dialect"] = model.dialect
    if a.store:
        res["stored"] = align.store_aligned(a.printer, a.setup or f"plate{a.plate}", res)
    print(json.dumps(res, indent=1))
    return 0 if res["pass"] else 1


if __name__ == "__main__":
    sys.exit(main())
