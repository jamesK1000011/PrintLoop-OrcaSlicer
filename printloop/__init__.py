# SPDX-License-Identifier: AGPL-3.0-only
"""PrintLoop for OrcaSlicer: score the defect risk of a sliced plate before
the print, and improve the next slice in a loop.

PrintLoop is an add-on for OrcaSlicer Agent Link (the orcalink package).
It reads the G-code through orcalink's gcode_view, scores five risk
domains, and changes one family of OrcaSlicer settings per iteration on a
copy of the project. It never starts a print and never sends a command to
a printer. FreeCAD gives the geometry only (the print context).
"""

VERSION = "0.1.0"
LICENSE = "AGPL-3.0-only"
CREDIT = (
    "PrintLoop for OrcaSlicer (AGPL-3.0-only). It uses OrcaSlicer Agent Link (orcalink, LGPL-2.1-or-later) "
    "and OrcaSlicer (AGPL-3.0). Where ScanRuler-FreeCAD tools give the print context, the credit for those "
    "features goes to Stefan Hermann / CNC Kitchen."
)
