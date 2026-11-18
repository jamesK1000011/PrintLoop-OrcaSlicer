# SPDX-License-Identifier: AGPL-3.0-only
"""A minimal sliced OrcaSlicer project (.gcode.3mf) for tests: one object
with a component transform, a build-item (instance) transform, the
source_offset that OrcaSlicer records, project settings and plate G-code.
Synthetic: the Mac's real slices replace it (spike step 4)."""
import json
import zipfile

NS = "http://schemas.microsoft.com/3dmanufacturing/core/2015/02"


def _t(m):
    # 4x4 row-major -> 3MF "m00 m10 m20 m01 m11 m21 m02 m12 m22 m03 m13 m23"
    return " ".join(f"{m[r][c]:.6f}" for c in range(4) for r in range(3))


def write(path, gcode, comp, inst, source_offset=(0, 0, 0), settings=None, name="fiducial_L.stl"):
    model = f"""<?xml version="1.0" encoding="UTF-8"?>
<model unit="millimeter" xml:lang="en-US" xmlns="{NS}" xmlns:p="http://schemas.microsoft.com/3dmanufacturing/production/2015/06" requiredextensions="p">
 <metadata name="OrcaSlicer">2.5.0</metadata>
 <resources>
  <object id="2" type="model">
   <components>
    <component p:path="/3D/Objects/obj_1.model" objectid="1" transform="{_t(comp)}"/>
   </components>
  </object>
 </resources>
 <build>
  <item objectid="2" transform="{_t(inst)}" printable="1"/>
 </build>
</model>
"""
    obj = f"""<?xml version="1.0" encoding="UTF-8"?>
<model unit="millimeter" xmlns="{NS}"><resources><object id="1" type="model"><mesh><vertices>
<vertex x="0" y="0" z="0"/><vertex x="1" y="0" z="0"/><vertex x="0" y="1" z="0"/></vertices>
<triangles><triangle v1="0" v2="1" v3="2"/></triangles></mesh></object></resources></model>
"""
    so = source_offset
    cfg = f"""<?xml version="1.0" encoding="UTF-8"?>
<config>
  <object id="2">
    <metadata key="name" value="{name}"/>
    <part id="1" subtype="normal_part">
      <metadata key="name" value="{name}"/>
      <metadata key="source_file" value="{name}"/>
      <metadata key="source_offset_x" value="{so[0]}"/>
      <metadata key="source_offset_y" value="{so[1]}"/>
      <metadata key="source_offset_z" value="{so[2]}"/>
    </part>
  </object>
  <plate>
    <metadata key="plater_id" value="1"/>
    <metadata key="gcode_file" value="Metadata/plate_1.gcode"/>
    <model_instance><metadata key="object_id" value="2"/><metadata key="instance_id" value="0"/></model_instance>
  </plate>
</config>
"""
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("[Content_Types].xml", '<?xml version="1.0"?><Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types"/>')
        z.writestr("3D/3dmodel.model", model)
        z.writestr("3D/Objects/obj_1.model", obj)
        z.writestr("Metadata/model_settings.config", cfg)
        z.writestr("Metadata/project_settings.config", json.dumps(settings or {}))
        z.writestr("Metadata/plate_1.gcode", gcode)
        z.writestr("Metadata/plate_1.gcode.md5", "0" * 32)
    return path
