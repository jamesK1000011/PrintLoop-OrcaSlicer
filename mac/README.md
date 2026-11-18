# Spike steps on the Mac (for the main session)

These steps need OrcaSlicer 2.5 and FreeCAD on the Mac. The container cannot run them.
Background only: no step opens OrcaSlicer's or FreeCAD's window. No step starts a print.

- Step 1: `step1_pipeline_plugin.sh` (install, slice with `orca_slice`, check, remove).
- Step 2: done on 18 Nov 2026 (`../tests/fixtures/mac/STEP2.md`).
- Step 4: `step4_fiducial_freecad.json` (FreeCAD Agent Link `batch`), then `orca_project new`, `orca_slice`, and `step4_check.py`. Then move and turn the part, slice again, check again.
