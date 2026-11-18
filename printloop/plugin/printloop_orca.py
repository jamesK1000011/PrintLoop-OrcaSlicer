# /// script
# requires-python = ">=3.9"
# dependencies = []
# [tool.orcaslicer.plugin]
# name = "PrintLoop probe"
# description = "Spike step 1: a no-op slicing-pipeline step at G-code post-processing. It writes a sidecar file and one comment line, and changes no move."
# author = "PrintLoop for OrcaSlicer"
# version = "0.1.0"
# ///
# SPDX-License-Identifier: AGPL-3.0-only
"""PrintLoop's optional OrcaSlicer 2.5 plugin (design D13), spike step 1.

It answers one question: does a slicing-pipeline plugin run when OrcaSlicer
slices from its command line (orca_slice), with no window and no prompt?

At psGCodePostProcess it:
1. appends one comment line to the G-code ("; printloop_probe: ..."), the
   one place a post-process step may always write;
2. writes a sidecar file beside the G-code (<name>.printloop.json), which
   needs no permission prompt (the G-code's own folder);
3. tries to append a line to ~/AgentLink/printloop/plugin-probe.jsonl.
   Outside the G-code's folder OrcaSlicer asks for permission on first use:
   the result (written or refused) goes in the sidecar.
It changes no move. It never connects to a printer.
"""
import datetime
import json
import os

import orca  # OrcaSlicer's plugin API (exists only inside OrcaSlicer)

MARK = "; printloop_probe: psGCodePostProcess ran"


class PrintLoopProbe(orca.slicing.SlicingPipelineCapabilityBase):
    def get_name(self):
        return "PrintLoop probe"

    def execute(self, ctx):
        if ctx.step != orca.slicing.Step.psGCodePostProcess:
            return orca.ExecutionResult.success()
        now = datetime.datetime.now(datetime.timezone.utc).isoformat()
        info = {"plugin": "printloop_probe", "step": "psGCodePostProcess", "time": now,
                "gcode": os.path.basename(ctx.gcode_path or ""), "output_name": getattr(ctx, "output_name", None)}
        with open(ctx.gcode_path, "a", encoding="utf-8") as f:
            f.write(MARK + " " + now + "\n")
        try:
            home = os.path.expanduser("~/AgentLink/printloop")
            os.makedirs(home, exist_ok=True)
            with open(os.path.join(home, "plugin-probe.jsonl"), "a", encoding="utf-8") as f:
                f.write(json.dumps(info) + "\n")
            info["user_folder"] = "written"
        except Exception as e:  # noqa: BLE001 - a refused permission is a result
            info["user_folder"] = f"refused: {type(e).__name__}: {e}"
        with open(ctx.gcode_path + ".printloop.json", "w", encoding="utf-8") as f:
            json.dump(info, f, indent=1)
        return orca.ExecutionResult.success("printloop probe ran")


@orca.plugin
class PrintLoopProbePlugin(orca.base):
    def register_capabilities(self):
        orca.register_capability(PrintLoopProbe)
