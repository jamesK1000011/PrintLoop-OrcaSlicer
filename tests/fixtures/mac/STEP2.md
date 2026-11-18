# Spike step 2 result (main session, live on the Mac, 18 Nov 2026 14:33 ET)
Model: 20 x 20 x 20 mm cube + 10 x 20 x 4 mm ledge at z 16-20 on +x (10 mm overhang); made in FreeCAD (headless), STL cube_overhang2.stl.
OrcaSlicer 2.5.0 (CLI via orca_slice).
- H2D: machine "Bambu Lab H2D 0.4 nozzle", process "0.20mm Standard @BBL H2D", filament "Bambu PLA Basic @BBL H2D". 100 layers, 14m45s, 4.01 g.
  Tags (exact, with one space after ";"): "; FEATURE: <name>", "; CHANGE_LAYER", "; Z_HEIGHT: 0.2", "; LAYER_HEIGHT: 0.2", "; LINE_WIDTH: 0.5". Also: "; WIPE_START", "; WIPE_END", "; SKIPTYPE:", "; SKIPPABLE_START", "; SKIPPABLE_END", ";_SET_FAN_SPEED_CHANGING_LAYER", "; MACHINE_START_GCODE_END", "; MACHINE_END_GCODE_START", header/config/executable blocks.
  Arcs: enable_arc_fitting = enabled; 107 G2/G3 lines. CONFIRMED.
  Sliced 3mf files: Metadata/plate_1.gcode, plate_1.gcode.md5 (md5 present), plate_1.json, plate_1.statistics.json, project_settings.config, model_settings.config, slice_info.config, filament_sequence.json, pngs; 3D/3dmodel.model, 3D/Objects/<name>_1.model.
  Features seen: Outer wall, Inner wall, Overhang wall, Sparse infill, Internal solid infill, Internal Bridge, Bridge, Top surface, Bottom surface, Custom.
  gcode_read totals: layers 100, z 0.2..20.0; per feature lengthMm/filamentMm: Sparse infill 13283.1/440.6, Outer wall 8187.7/252.1, Inner wall 7746.1/257.3, Internal solid infill 6993.8/214.7, Internal Bridge 1162.7/59.5, Bridge 497.3/14.5, Top surface 1498.1/46.3, Bottom surface 698.5/26.3, Overhang wall 75.8/2.2.
- Prusa dialect: machine "Prusa MK3S 0.4 nozzle", process "0.20mm Standard @MK3S", filament "Generic PLA". 100 layers.
  Tags (no space): ";TYPE:<name>", ";LAYER_CHANGE", ";Z:0.2", ";HEIGHT:0.2", ";WIDTH:0.499999", plus ";BEFORE_LAYER_CHANGE", ";AFTER_LAYER_CHANGE", ";WIPE_START/END". enable_arc_fitting = disabled; 0 arcs.
