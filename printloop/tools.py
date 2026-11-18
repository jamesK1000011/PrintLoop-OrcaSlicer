# SPDX-License-Identifier: AGPL-3.0-only
"""The PrintLoop tools (§16.2). The descriptions and input schemas are data
(data/tools.json); this module gives each tool its function.

specs(ctx) gives the tools as dicts for orcalink's add-on loader
(orcalink/addons.py) and for the standalone server. ctx: out_dir (where a
relative path goes), tools (orcalink's tool functions, for orca_slice),
ToolError (the class orcalink answers refusals with).

Refusal codes (orcalink's shape): invalid_input, not_found, gated,
unaligned, unavailable.
"""
import os

from . import seeds
from .loop import runner
from .score import report

UNAVAILABLE = "unavailable: step 8+"


class Refusal(Exception):
    def __init__(self, code, message):
        super().__init__(message)
        self.code, self.message = code, message


def specs(ctx):
    out_dir = ctx.get("out_dir") or os.path.expanduser("~/Documents/AgentLink")
    own = ctx.get("tools") or {}
    TE = ctx.get("ToolError") or Refusal
    slicer_factory = ctx.get("slicer") or (lambda: runner.OrcalinkSlicer(own))

    def where(p):
        p = os.path.expanduser(str(p))
        return p if os.path.isabs(p) else os.path.join(out_dir, p)

    def guard(fn):
        def run(a):
            try:
                return fn(a)
            except Refusal as e:
                raise TE(e.code, e.message)
            except PermissionError as e:
                raise TE("gated", str(e))
            except FileNotFoundError as e:
                raise TE("not_found", str(e))
            except ImportError as e:
                raise TE("unavailable", str(e))
            except (ValueError, KeyError) as e:
                raise TE("invalid_input", str(e))

        return run

    def ctx_of(a):
        c = a.get("context")
        if isinstance(c, str):
            return where(c)
        return c

    def print_score(a):
        p = where(a["path"])
        if not os.path.isfile(p):
            raise FileNotFoundError(f"{p}: no such file (orca_slice answers the sliced project in sliced).")
        base = a.get("baseline")
        if base and not os.path.isabs(os.path.expanduser(base)) and os.path.isfile(where(base)):
            base = where(base)
        return report.score_file(p, int(a.get("plate", 1)), ctx_of(a), base, a.get("printer"), a.get("filament"))

    def print_loop(a):
        act = a["action"]
        if act in ("approve", "reject"):
            raise Refusal("gated", "approve and reject go through print_approve (the person sets it to ask first in the client).")
        if act == "start":
            if not a.get("path"):
                raise ValueError("start: path is needed (an OrcaSlicer project, .3mf).")
            st = runner.start(where(a["path"]), slicer_factory(), int(a.get("plate", 1)), ctx_of(a), a.get("dial"), a.get("printer"), a.get("filament"))
            return runner.public(st)
        if not a.get("run_id"):
            raise ValueError(f"{act}: run_id is needed (print_loop start answers it).")
        if act == "step":
            return runner.public(runner.step(a["run_id"], slicer_factory(), where(a["path"]) if a.get("path") else None))
        if act == "status":
            return runner.public(runner.status(a["run_id"]))
        if act == "stop":
            return runner.public(runner.stop(a["run_id"]))
        raise ValueError(f"action: start, step, status or stop; not {act}.")

    def print_approve(a):
        return runner.public(runner.approve(a["run_id"], a["gate_id"], a.get("token"), slicer_factory(), a.get("decision", "approve")))

    def unavailable(a):
        raise Refusal("unavailable", UNAVAILABLE + " (PrintLoop for OrcaSlicer builds spike steps 1-7 now; printer connection is the lowest priority).")

    fns = {"print_score": print_score, "print_loop": print_loop, "print_approve": print_approve,
           "printer": unavailable, "print_watch": unavailable, "calib": unavailable}
    out = []
    for t in seeds.load("tools")["tools"]:
        out.append({"name": t["name"], "description": t["description"], "inputSchema": t["inputSchema"], "fn": guard(fns[t["name"]]),
                    "group": t.get("group", "printloop"), "changes": t["name"] in ("print_loop", "print_approve")})
    return out
