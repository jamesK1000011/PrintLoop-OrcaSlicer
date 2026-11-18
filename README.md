# PrintLoop for OrcaSlicer

PrintLoop scores the defect risk of a sliced plate before the print. It then improves the next slice in a loop.
It is an add-on for [OrcaSlicer Agent Link](https://github.com/jamesK1000011/AgentLink-OrcaSlicer) (the `orcalink` package).
FreeCAD gives the geometry only (the print context).

PrintLoop never starts a print. It never sends a command to a printer. It never writes your presets.

Licence: AGPL-3.0-only (see LICENSE). The design is in `docs/design.md`.

## What it does

- `print_score` reads the G-code of a sliced `.gcode.3mf` or `.gcode` and scores five domains: stringing, overhang, warp, thermal and collision.
  Each domain has a score from 0 to 100 and hot spots. The overall score is the lowest domain score.
- `print_loop` slices, scores and changes one family of OrcaSlicer settings per iteration. It works on run copies in `~/AgentLink/printloop/runs/`.
  The autonomy dial (0 to 3) sets where it stops for your approval.
- `print_approve` approves or rejects a gate. Set this tool to "ask first" in your MCP client.
- `printer`, `print_watch` and `calib` are not available yet (spike step 8 and later). They refuse with code `unavailable`.

The scores are a risk estimate. They are not a sign-off.

## Install

1. Install OrcaSlicer Agent Link.
2. Clone this repository beside it, or anywhere.
3. Set `ORCALINK_ADDONS` to the folder of this repository in the environment of the OrcaSlicer Agent Link server.
   Or put the `printloop` package on that server's Python path.

OrcaSlicer Agent Link finds PrintLoop by its `orcalink_addon` module. It never names PrintLoop.
Without PrintLoop, OrcaSlicer Agent Link adds no tool and spends no tokens.

To run PrintLoop as its own MCP server: `python3 printloop_server.py --out ~/Documents/AgentLink`.
It still needs the `orcalink` package (beside this repository, or `ORCALINK_PATH`).

Dependencies: Python 3.9 or later, `orcalink`, and `shapely>=2` (GEOS) for speed.
Without shapely, a pure-Python fallback gives the same answers more slowly.

## Your data

PrintLoop keeps its data in `~/AgentLink/printloop/` (`PRINTLOOP_HOME` sets another folder):
`config.json` (dial, caps, aligned setups), `calib.sqlite` (learned values), `runs/`.
An update of PrintLoop does not change this folder. The seed values in `printloop/data/` are starting points; the calibration store overrides them per printer and filament.

## Status (spike steps, design §16.8)

| Step | Work | Status |
|---|---|---|
| 1 | OrcaSlicer 2.5 pipeline plugin under the command line | Plugin and script ready (`printloop/plugin/printloop_orca.py`, `mac/step1_pipeline_plugin.sh`). Waits for the Mac. |
| 2 | Real H2D and Prusa-dialect slices | Done on the Mac, 18 Nov 2026 (`tests/fixtures/mac/`). |
| 3 | Dialect and arcs on gcode_view | Done. Met on the real fixtures. |
| 4 | Fiducial alignment | Code and synthetic tests done. The real check waits for the Mac (`mac/step4_fiducial_freecad.json`, `mac/step4_check.py`). |
| 5 | Domains 1–4, report, schema | Done on synthetic fixtures in both dialects. The Mac slices of §16.9 and the 6 h performance target wait for the Mac. |
| 6 | Domain 5 (collision) | Done on the synthetic fiducial. |
| 7 | Loop policy and runner | Done with a synthetic slicer. A live loop through `orca_slice` waits for the Mac. |

## Tests

`python3 -m pytest -q tests` (needs `orcalink` beside this repository or on `ORCALINK_PATH`; no OrcaSlicer, no FreeCAD).

## Credits

PrintLoop uses OrcaSlicer Agent Link (LGPL-2.1-or-later) and OrcaSlicer (AGPL-3.0).
Where ScanRuler-FreeCAD tools give the print context, the credit for those features goes to Stefan Hermann / CNC Kitchen.
