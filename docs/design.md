# G-Code Defect Scorer & Print Telemetry: Design Architecture v2 (Green Spike)

(Authoritative copy of the project doc claude/gcode-sim-telemetry-design-v2-2026-11-15.md, written by the main session on 18 Nov 2026. The owner PROMOTED this spike on 18 Nov: the "DESIGN ONLY" status below is lifted. Scope this run: spike steps 1–7, no printer connection.)

**Status: PROMOTED by the owner on 18 Nov 2026. Build spike steps 1–7. No printer connection.**
(The earlier status line "GREEN SPIKE — DESIGN ONLY" is lifted. Printer connection stays lowest priority.)
Repository: jamesK1000011/PrintLoop-OrcaSlicer. This file is the repository copy of the project doc; §17 records the changes made while building.

- **Supersedes:** `claude/gcode-sim-telemetry-design-2026-11-15.md` (v1). v2 adds §16, the implementation contract, so any agent can pick this up without guessing.
- **Date:** 2026-11-15.
- **Sources:** the owner's original spec, the grilling sessions (text and voice), and the research pass of 2026-11-15.
- **Decision rule:** Decisions D1–D13 are the owner's and locked. Everything in §16 is the design default; an agent may change it only by recording the change and its reason in this document.

---

## 1. Purpose

This closes the loop on the pipeline: FreeCAD (Agent Link + ScanRuler-FreeCAD + FEM) → OrcaSlicer (headless) → printer → back again.

1. **Pre-print scorer.** Scores the defect risk in a sliced `.gcode.3mf` before printing, then lets the agent improve the next iteration through slicer settings, or CAD changes if the slicer can't fix it.
2. **Execution telemetry and calibration.** Watches prints through a vendor-neutral printer HAL and learns per (printer, filament) without the owner logging anything. Its corrections feed the next run, never the current one.

It ships as an **OrcaSlicer add-on** under full headless MCP control and plugs into OrcaSlicer-AgentLink (`orcalink`).

## 2. Locked decisions

| # | Decision |
|---|---|
| D1 | Spec for later; built as an OrcaSlicer add-on with full headless control. OrcaSlicer is the only slicer (PrusaSlicer path retired). |
| D2 | The scorer is a **scoring layer on the existing `gcode_read`** (`orcalink.gcode_view`), not a new standalone parser. |
| D3 | **During a print the agent only monitors and logs**: no mid-print G-code injection, no autonomous aborts. Fixes go into the next run (Orca overrides and/or CAD). |
| D4 | **Autonomy dial**: one setting, from full auto to frequent stops. It governs the iteration caps and whether CAD edits need sign-off. The caps (4 slicer passes, 2 CAD passes) are placeholders on the dial. |
| D5 | Early versions score each pass **relative to the previous pass**. A fixed bar waits until calibration data exists. |
| D6 | **HAL socket first, drivers later**, tested last. Driver order is set by how open each spec is. **Local network first, cloud later. No extra hardware.** |
| D7 | **Vision uses the printer's native AI detection.** Our own model is only a fallback for homebrew printers without one. |
| D8 | **Detector settings are logged with every job.** "No defect detected" counts only if detection was on, and is weighted by its sensitivity. |
| D9 | **Calibration learns without human logging**: HAL telemetry, native warnings and G-code inference. |
| D10 | **Stringing**: the G-code prediction comes first. Post-print confirmation comes from a camera image (the printer's camera **or the user's own phone photo**) or an optional quick human rating. Both are optional inputs, never required. |
| D11 | **FreeCAD is the single source of truth** for geometry, keep-out/tolerance faces and FEM stress. ScanRuler-FreeCAD tools are used where they fit. |
| D12 | **License: AGPL-3.0** for the add-on. |
| D13 | **External MCP server as the core, with an optional thin OrcaSlicer 2.5 plugin.** The first spike task proves whether the plugin runs headless. |

## 3. Architecture

```
FreeCAD (Agent Link, ScanRuler-FreeCAD, FEM)   ← source of truth (D11)
        │ print_context: bodies, keep-out faces, stress peaks, placement
        ▼
orcalink MCP server (LGPL, existing)  ── finds, never imports by name ──┐
  orca_project / orca_slice / gcode_read                                │
                                                                        ▼
printloop package (AGPL, new; registers tools into orcalink or runs standalone)
  ├─ gcode dialect + layer model  (on top of gcode_view)      (D2)
  ├─ scorer (5 domains)                                       (D5)
  ├─ loop policy + runner (dial, caps, gates)                 (D4)
  ├─ calibration store (SQLite)                               (D9)
  └─ printer HAL (socket + drivers, read-only)                (D3, D6)
        ▲                                   │
        │ optional sidecar / preset writes  │ telemetry, events
OrcaSlicer 2.5 plugin (optional, thin, AGPL) ▼
                                            Printer (H2D first, LAN)
```

**Rules**
- The scorer must work from G-code alone; the plugin is optional.
- No compiled-in fork features.
- Base Agent Link and orcalink carry no token cost when printloop isn't installed.

## 4. Pre-print scorer (summary; contract in §16.4)

**Five domains:**
1. Stringing and oozing.
2. Overhangs and bridging.
3. Warping and adhesion.
4. Thermal buildup and under-extrusion.
5. Structural and tolerance collisions.

**Research corrections that must be applied (verify in spike step 2):**
- **Tag dialect.** Bambu-printer G-code uses `; FEATURE:`, `; CHANGE_LAYER`, `; Z_HEIGHT:`, `; LAYER_HEIGHT:` and `; LINE_WIDTH:`. Non-Bambu printers use `;TYPE:`, `;LAYER_CHANGE`, `;Z:`, `;HEIGHT:` and `;WIDTH:`. Support both.
- **Arcs.** Arc fitting is probably on by default for H2D, so support G2/G3.
- **Kinematics.** `gcode_view` actual speed and flow first; pyGCodeDecode (MIT) only for gaps.

**Confirmed in spike step 2** (main session, live on the Mac, 18 Nov 2026; OrcaSlicer 2.5.0 CLI; fixtures in `tests/fixtures/mac/`, notes in `STEP2.md`):
- **Bambu dialect** (machine "Bambu Lab H2D 0.4 nozzle", process "0.20mm Standard @BBL H2D", filament "Bambu PLA Basic @BBL H2D"): tags exactly `; FEATURE: <name>`, `; CHANGE_LAYER`, `; Z_HEIGHT: 0.2`, `; LAYER_HEIGHT: 0.2`, `; LINE_WIDTH: 0.5` (one space after `;`). Also `; WIPE_START`, `; WIPE_END`, `; SKIPTYPE:`, `; SKIPPABLE_START`, `; SKIPPABLE_END`, `;_SET_FAN_SPEED_CHANGING_LAYER`, `; MACHINE_START_GCODE_END`, `; MACHINE_END_GCODE_START`, and header, config and executable blocks.
- **Arcs:** `enable_arc_fitting = enabled` on H2D; 107 G2/G3 lines at the start of a line, plus one indented spiral lift (`G3 Z… I… J… P1`) in the printer's start G-code. CONFIRMED: G2/G3 support is needed.
- **Prusa dialect** (machine "Prusa MK3S 0.4 nozzle", "0.20mm Standard @MK3S", "Generic PLA"): `;TYPE:<name>`, `;LAYER_CHANGE`, `;Z:0.2`, `;HEIGHT:0.2`, `;WIDTH:0.499999` (no space), plus `;BEFORE_LAYER_CHANGE`, `;AFTER_LAYER_CHANGE`, `;WIPE_START`, `;WIPE_END`. Arc fitting disabled: 0 arcs.
- **Sliced .gcode.3mf members:** `Metadata/plate_1.gcode`, `Metadata/plate_1.gcode.md5` (md5 present), `plate_1.json`, `plate_1.statistics.json`, `project_settings.config`, `model_settings.config`, `slice_info.config`, `filament_sequence.json`, the PNGs, `3D/3dmodel.model`, `3D/Objects/<name>_1.model`.
- **Features seen:** Outer wall, Inner wall, Overhang wall, Sparse infill, Internal solid infill, Internal Bridge, Bridge, Top surface, Bottom surface, Custom.
- **Finding:** orcalink's `gcode_view` counted wipes only for `;WIPE_START`, so Bambu wipes were 0. Fixed in AgentLink-OrcaSlicer (18 Nov 2026), not yet seen live.
- **Privacy:** the fixtures hold no serial, IP, access code or user path (checked before commit).

## 5. Loop policy (summary; contract in §16.5)

- **Tier 1:** Orca settings only, applied as per-run overrides.
- **Tier 2:** CAD changes in FreeCAD that respect keep-out faces, then FEM and slice revalidation.
- **Enforcement:** the server enforces gates; the client is not trusted to.

## 6. Printer HAL (summary; contract in §16.6)

**Build order:**
1. Socket plus ReplayDriver.
2. Read-only Bambu LAN driver.
3. Moonraker.
4. PrusaLink / OctoPrint.
5. Cloud.

**Bambu LAN facts:**
- **Connection:** MQTT over TLS on port 8883, user `bblp`, LAN access code, topic `device/<serial>/report`.
- **Updates:** merge deltas over a full `pushall`.
- **H2D temperatures:** also under `device.bed/ctc/extruder`.
- **HMS decoding:** severity comes from bits 16–31 of `code`. Text comes from Bambu Studio's `hms_en_<model>.json`, loaded at runtime.
- **`print_error`:** transient, so latch it.
- **Detector config:** in `xcam`.
- **Camera:** RTSPS on port 322; off until "LAN Only Liveview" is enabled; open on demand only.

**Note from spike step 2:** the sliced .gcode.3mf carries `Metadata/plate_<n>.gcode.md5`. `print_watch` can bind a job by that md5 or by the G-code's sha256 (`gcode_sha256` in the ScoreReport) when the printer reports one. Not yet checked against a printer (step 8+).

## 7. Calibration store (summary; contract in §16.7)

- **Key:** printer × nozzle × filament profile (+ lot/colour when known).
- **Labels:** weak, from telemetry and events. Optional D10 confirmations weigh more.
- **Learning:** per-domain Beta-Bernoulli updates. Change one settings family per run.

## 8. Vision fallback (homebrew printers only)

- **Options:** PrintGuard (LiteRT/ONNX, CoreML on macOS; license unchecked) or the Obico ONNX model (AGPL).
- **How it runs:** subprocess or HTTP, about one frame per layer or every 10 s, smoothed.
- **Limits:** a signal only; it never triggers an action.

## 9. MCP layer

- **Spec target:** MCP 2026-07-28 (stateless), with a fallback for 2025-11-25 clients.
- **IDs:** the server mints IDs and passes them as arguments.
- **Long work:** the Tasks extension (`io.modelcontextprotocol/tasks`), with a synchronous short-timeout fallback.
- **Live data:** resources followed via `subscriptions/listen`.
- **Avoid:** Sampling, Roots and Logging (deprecated).

## 10. Coordinate alignment

- **Mapping:** model point = inverse(build-item transform × component transform) × G-code point, then the inverse FreeCAD export placement.
- **Shortcut:** orcalink already maps FreeCAD face names to Orca parts exactly (`orca_paint` by faces, even after arrange); reuse that path.
- **Validation:** an asymmetric L-bracket fiducial (§16.8, step 4).

## 11. Prior art

- **No public tool combines** pre-print defect scoring, FEM/tolerance mapping and per-filament learning over MCP.
- **Protocol references only:** Bambu MCP servers (synman, griches, rafaelquintanilha, Wixely and others). Copy no GPL-2.0 code.
- **CAXTON (Nature Communications 2022):** reuse its idea of labelling defects by parameter deviation.

## 12. Licenses

| Component | License | Use |
|---|---|---|
| printloop (new) | AGPL-3.0-only | This add-on |
| orcalink / OrcaSlicer-AgentLink | LGPL (existing) | Imported by printloop; never imports printloop |
| OrcaSlicer | AGPL-3.0 | Host slicer; plugin runs inside it |
| FreeCAD | LGPL-2.1+ | CAD/FEM host |
| ScanRuler-FreeCAD | AGPL-3.0-only | Credit Stefan Hermann / CNC Kitchen where it loads |
| shapely (GEOS) | BSD-3 (LGPL-2.1) | Geometry |
| paho-mqtt | EPL-2.0 / EDL-1.0 | Bambu driver (confirm EDL option) |
| websockets | BSD-3 | Moonraker driver |
| pyGCodeDecode | MIT | Optional extra |
| ha-bambulab tables | MIT | HMS/print_error text, with attribution |
| Bambu Studio HMS JSON | AGPL-3.0 | Loaded at runtime from the user's install |
| Klipper/Moonraker | GPL-3.0 | Reference only |
| Obico model | AGPL-3.0 | Vision fallback |

This is an engineering reading, not legal advice.

## 13. Open risks

- **Unconfirmed details:** the tag dialect and H2D arc default are not yet confirmed against source.
- **Changing APIs:** the Orca plugin API is experimental; MCP Tasks is an extension and may change.
- **Bambu firmware:** Developer Mode policy shifts between releases. Whether AI detection works in LAN-only mode is unknown.
- **Not yet researched:** PrusaLink fields, filament databases, the PrintGuard license, exact Bambu volumetric limits.
- **Silent defects:** stringing raises no printer event; its learning depends on D10.

## 14. Key sources

- OrcaSlicer 2.5.0 release notes and plugin wiki: github.com/OrcaSlicer/OrcaSlicer/releases/tag/v2.5.0-alpha; orcaslicer.com/wiki/plugins/plugins_types; orcaslicer.com/wiki/developer_reference/plugin_development/plugin_development
- OrcaSlicer CLI wiki: orcaslicer.com/wiki/cli/cli_actions
- Post-processing scripts: github.com/OrcaSlicer/OrcaSlicer/wiki/others_settings_post_processing_scripts
- Bambu MQTT: github.com/Doridian/OpenBambuAPI/blob/main/mqtt.md and …/video.md
- ha-bambulab print_error: github.com/greghesp/ha-bambulab/issues/525
- Moonraker: moonraker.readthedocs.io/en/latest/printer_objects/
- MCP 2026-07-28: modelcontextprotocol.io/specification/2026-07-28/changelog
- pyGCodeDecode: pypi.org/project/pyGCodeDecode/
- PrintGuard: github.com/oliverbravery/PrintGuard

## 15. Glossary

| Term | Meaning |
|---|---|
| run | One loop from first slice to exit (`run_id`). |
| iteration | One slice and score within a run (`iteration_id` = `run_id/n`). |
| job | One physical print being watched (`job_id`). |
| gate | A point where the server waits for human approval (`gate_id`). |
| knob family | A group of Orca settings changed together in one iteration (§16.5.3). |
| hot spot | A located risk: layer, G-code XY, model XYZ, domain, risk. |

---

## 16. Implementation contract

### 16.0 Rules for the implementing agent

1. **Only after promotion.** Do not start until the owner says so in chat or the roadmap lists this spike as active. (the owner promoted it on 18 Nov 2026.)
2. **Verify first.** Spike steps 1–2 (§16.8) confirm the unverified facts. If a fact differs, update §4, §6 or §16 in this document, then continue.
3. **Stop and ask the owner only if:** a license conflict appears, a locked decision can't be met, or a step would start a print, write his preset files, or touch credentials outside the secrets file.
4. **Project rules apply:** background only on the Mac, test through the MCP tools, commit rules per project instructions, limited CI, credits where Stefan's work loads.
5. **Units throughout:** mm, s, °C, mm/s, mm³/s, % (0–100), degrees. Coordinates are right-handed, Z up.

### 16.1 Repository, package and files

- **Repo:** `jamesK1000011/PrintLoop-OrcaSlicer` (working name; rename freely). License AGPL-3.0-only. Python ≥ 3.9, matching orcalink.
- **Discovery:** orcalink finds `printloop` the same quiet way Agent Link finds orcalink: a `printloop_find` lookup, or the `AGENTLINK_PRINTLOOP` env var. orcalink never imports printloop by name. If printloop is absent, no tools are registered and no tokens are spent. printloop imports orcalink's public functions (`gcode_view`, `orca3mf`, the options table); AGPL may use LGPL.
- **Standalone:** `printloop_server.py` runs its own MCP server for use without orcalink's server.

```
printloop/
  __init__.py            version, CREDIT, LICENSE strings
  server.py              tool + resource registration (hook into orcalink, or standalone)
  ids.py                 run/iteration/job/gate id minting (ULID)
  gcode/dialect.py       tag tables: BBL, PRUSA; detect(header) -> dialect
  gcode/layers.py        LayerModel from gcode_view output; G2/G3 → segments (≤0.1 mm chord error)
  gcode/geom.py          per-layer extrusion polygons (shapely), travel moves, retract flags
  score/domains/stringing.py | overhang.py | warp.py | thermal.py | collision.py
  score/report.py        ScoreReport build, deltas, CRITICAL flags, schema validation
  loop/policy.py         dial levels, caps, always-gated list, gate tokens
  loop/knobs.py          knob families, Orca keys, step sizes, bounds
  loop/runner.py         iteration state machine (§16.5.4)
  calib/store.py         SQLite access (DDL §16.7)
  calib/learn.py         Beta-Bernoulli updates, priors from the Orca filament profile
  hal/base.py            Driver ABC, TelemetryPacket, Capabilities
  hal/events.py          severity mapping, HMS decode, print_error latch
  hal/replay.py          ReplayDriver (JSONL recordings)
  hal/bambu_lan.py       read-only MQTT driver
  hal/moonraker.py       read-only WebSocket driver
  vision/fallback.py     subprocess/HTTP adapter (homebrew printers only)
  plugin/printloop_orca.py   optional OrcaSlicer 2.5 slicing-pipeline plugin
  data/defaults.json     seed parameters (§16.4), dial table (§16.5)
  data/schema/*.json     JSON Schemas: score_report, print_context, telemetry_packet, run_state
tests/
  fixtures/              §16.9
  test_dialect.py test_layers.py test_domains.py test_report.py test_policy.py
  test_runner.py test_store.py test_learn.py test_events.py test_replay.py test_server.py
```

**Runtime files (never in the repo):**

| Path | Contents |
|---|---|
| `~/AgentLink/printloop/config.json` | dial level, caps, printers (no secrets) |
| `~/AgentLink/printloop/calib.sqlite` | calibration store |
| `~/AgentLink/printloop/runs/<run_id>/<n>/` | `report.json`, `project.3mf` (sliced copy), `overrides.json`, `gcode.sha256` |
| `~/AgentLink/printloop/jobs/<job_id>/` | `telemetry.jsonl`, `events.json`, `detector.json`, `snapshots/` |
| `~/.config/printloop/secrets.json` | LAN access codes and API keys; mode 0600; never logged or echoed |

**Dependencies:**
- Core: `shapely>=2`.
- Extras: `[bambu]` = `paho-mqtt>=2`; `[moonraker]` = `websockets`; `[kin]` = `pyGCodeDecode`.
- Nothing else without recording it in §12.

**CI (limited, per project rule):**
- Unit tests on push to `main` only, Python 3.9 and 3.12, no matrix beyond that.
- An Orca AppImage end-to-end job on `workflow_dispatch` only.
(the owner limits CI: add no workflow in this run.)

### 16.2 MCP surface

Tool group `printloop`. Every tool returns JSON. Errors use orcalink's refusal shape: `{error:{code, message}}`, with codes `invalid_input | not_found | gated | unaligned | unavailable`.

| Tool | Arguments | Returns | Task? |
|---|---|---|---|
| `print_score` | `path` (.gcode.3mf or .3mf sliced), `plate`=1, `context?` (PrintContext), `baseline?` (report path or `iteration_id`), `printer?`, `filament?` | ScoreReport | yes if > 10 s |
| `print_context` | `body?` or `object?`, `fea?` (study name) | PrintContext. FreeCAD-side; registered by the Agent Link bridge only | no |
| `print_loop` | `action`: `start`, `step`, `status`, `approve`, `reject`, `stop`; `run_id?`, `path?` (project), `context?`, `dial?`, `gate_id?`, `token?` | RunState | `start` and `step` are tasks |
| `printer` | `action`: `list`, `add`, `remove`, `capabilities`, `telemetry`, `events`, `snapshot`; `printer_id?`, `driver?`, `host?`, `serial?` | Capabilities, TelemetryPacket or events. `add` asks for the access code through the secrets flow, never as a tool argument echoed back | no |
| `print_watch` | `action`: `start`, `stop`, `status`; `printer_id`, `path` + `plate` (the sliced file the owner printed), `run_id?` | WatchState. Binds a print the owner started to a job; never starts one | `start` is a task |
| `calib` | `action`: `get`, `propose`, `record`, `explain`, `reset`; `printer_id`, `filament`; `record`: `job_id`, `rating?` (`good`, `minor`, `bad` per domain), `photo?` (path) | Calibration view, proposals or explanation. `reset` is always gated | no |

**Resources:**
- `printer://{printer_id}/telemetry` (latest packet)
- `job://{job_id}/events`
- `run://{run_id}` (RunState)
- `calib://{printer_id}/{filament}`

Clients follow these with `subscriptions/listen`.

### 16.3 Schemas

**PrintContext** (from FreeCAD; any part may be empty):
```json
{
  "body": "Body", "orca_object": "Body", "doc": "part.FCStd",
  "export_placement": {"matrix4": [16 numbers, row-major], "units": "mm"},
  "bbox": {"min": [x,y,z], "max": [x,y,z]},
  "keepout_faces": [{"face": "Face12", "reason": "fit|note|tolerance", "tol_mm": 0.1,
                     "samples": [[x,y,z], ...]}],
  "stress": {"study": "FEMStudy", "max_vm_mpa": 31.2,
             "peaks": [{"xyz": [x,y,z], "vm_mpa": 29.8, "ratio": 0.96}]},
  "aligned": false
}
```

**How the fields are filled:**
- `keepout_faces`: faces in fit records (`fit`/`asm_fits`), faces with a note containing "keep-out", and tolerance faces from TechDraw/GD&T. `samples` are points laid by area, about one per 4 mm².
- `stress.peaks`: FEM result nodes with ratio ≥ 0.8 of max von Mises, thinned to ≤ 200 by farthest-point sampling.
- `aligned`: becomes true only after the fiducial test passes for this printer and plate setup (§16.8, step 4). The result is stored in `config.json`.

**ScoreReport:**
```json
{
  "schema": "printloop.score_report/1",
  "report_id": "ULID", "run_id": "ULID|null", "iteration": 0,
  "source": {"path": "...", "plate": 1, "gcode_sha256": "...", "dialect": "bbl|prusa",
             "arcs": true, "orca_version": "2.5.0"},
  "printer": "h2d-home", "filament": "Bambu PLA Basic @BBL H2D",
  "overall": {"score": 0-100, "critical": false, "delta": null},
  "domains": {
    "stringing|overhang|warp|thermal|collision": {
      "score": 0-100, "delta": null|number, "critical": false,
      "status": "ok|unaligned|no_context|skipped",
      "p95_risk": 0-1, "max_risk": 0-1,
      "hot_spots": [{"layer": 42, "z": 8.4, "xy": [x,y], "model_xyz": [x,y,z]|null,
                     "risk": 0-1, "why": "travel 6.2 mm open air, retracted"}]
    }
  },
  "orca_warnings": [{"level": 1, "code": "...", "msg": "..."}],
  "inputs": {"params_source": {"calib": true|false, "defaults": true}},
  "timing_ms": 0
}
```

**Report rules:**
- At most 20 hot spots per domain, highest risk first.
- `model_xyz` is null unless `aligned`.

**TelemetryPacket:** as proposed in the research, frozen as schema `printloop.telemetry/1`:
```json
{ "ts": "ISO8601", "printer_id": "", "driver": "bambu_lan|moonraker|replay|...", "job_id": "",
  "gcode_sha256": "", "state": "idle|preparing|printing|paused|finished|failed|offline",
  "progress_pct": 0, "layer": {"current": 0, "total": 0, "source": "native|inferred_z|file_pos"},
  "temps": {"nozzle": [{"actual": 0, "target": 0}], "bed": {"actual": 0, "target": 0},
            "chamber": {"actual": 0, "target": 0}},
  "fans": {"part_pct": 0, "aux_pct": 0, "chamber_pct": 0}, "speed_level": 2,
  "active_extruder": 0,
  "events": [{"code": "", "source": "hms|print_error|klippy|vision|human",
              "severity": "FATAL|SERIOUS|WARNING|INFO|DEFECT_SIGNAL", "text": "",
              "layer": 0, "first_seen": "", "cleared": null}],
  "detector_config": {"spaghetti": {"on": true, "sens": "low|medium|high"},
                      "first_layer": {"on": true}, "nozzle_clog": {"on": true}},
  "raw_ref": "jobs/<job_id>/telemetry.jsonl#L123" }
```

**RunState:**
```json
{ "run_id": "", "state": "running|input_required|done|escalated|stopped",
  "dial": 1, "iteration": 2, "caps": {"slicer": 4, "cad": 2},
  "used": {"slicer": 2, "cad": 0},
  "history": [{"n": 0, "report_id": "", "overall": 61, "changed": null},
              {"n": 1, "report_id": "", "overall": 68,
               "changed": {"family": "retraction", "set": {"retraction_length": 1.0}}}],
  "gate": {"gate_id": "", "kind": "cad_edit|preset_write|cap_exhausted|calib_reset",
           "proposal": {}, "token_hint": "approve 7F3K"} | null,
  "exit_reason": null }
```

### 16.4 Scoring math v0

**General rules:**
- Every domain computes a **layer risk** r_l in [0, 1].
- Domain score = `round(100 × (1 − max(p95(r_l), 0.5 × max(r_l))))`.
- Domain CRITICAL if any r_l ≥ 0.8.
- **Overall score = the minimum domain score** (not an average, so one bad domain can't hide). Overall CRITICAL if any domain is CRITICAL.
- delta = score − the previous iteration's score in the same run.
- All constants below are **seed values** in `data/defaults.json`. The calibration store may override them per (printer, filament). They are starting points, not literature values.

**Shared inputs from the Orca filament profile and printer:**

| Symbol | Source |
|---|---|
| T_lo, T_hi | `nozzle_temperature_range_low`, `nozzle_temperature_range_high` |
| Q_max | min(`filament_max_volumetric_speed`, capabilities.max_flow if known) |
| t_min | `slow_down_layer_time` |
| w | line width per move from `; LINE_WIDTH:` / `;WIDTH:` |

**Layer polygons.** P_l = union of the layer's extrusion segments buffered by w/2 (shapely). Use `buffer(…, cap_style=flat)` per segment and `unary_union` per layer.

**Domain 1, stringing.** For each travel move on layer l (no E increase, length > 0):
- d_open = length of the travel segment outside P_l.
- retracted = a retract occurs before the travel (from `gcode_view` retracts). wiped and zhop are recorded the same way.
- m = sigmoid((d_open − D0) / S) with seeds D0 = 2.0 mm, S = 1.0 mm.
- m ×= 0.35 if retracted (seed `k_retract`); ×= 0.8 if wiped; ×= 1.1 if zhop (Z-hop dwell oozes).
- m ×= 1 + max(0, (T_set − (T_lo + T_hi)/2) / ((T_hi − T_lo)/2)) × 0.5.
- r_l = 1 − Π(1 − m) over the layer's travels, clamped to [0, 1].
- Hot spot = the midpoint of the open-air portion.

**Domain 2, overhangs and bridging.** For layers l ≥ 2:
- Wall and overhang features: `Outer wall`, `Overhang wall`.
- For each such segment, u = the fraction of its length outside buffer(P_{l−1}, w/2).
- fan = part fan % at that move; v = actual speed.
- seg risk = u × (1 + 0.5 × (1 − fan/100)) × clamp(v / V_ref, 0.5, 2), with V_ref = the profile's `overhang_3_4_speed`, or 30 mm/s if absent.
- **Bridges** (`Bridge`, `Internal Bridge`): risk = clamp((L − L0) / L0, 0, 1) × (1 + 0.5 × (1 − fan/100)), with L the bridge length and L0 = 10 mm.
- r_l = the length-weighted p90 of segment risks on the layer, clamped.

**Domain 3, warping and adhesion.** This is a part-level risk assigned to layers 1–3.
- Inputs:
  - A1 = area(P_1); H = top Z.
  - aspect = clamp(H / √A1 / 3, 0, 1).
  - corners = the count of convex corners < 90° on the outer boundary of P_1 ∪ P_2 ∪ P_3, normalised by /8, clamped.
  - early_fan = mean part fan % over layers 1–3 / 100.
  - shrink = class by `filament_type`: PLA, TPU, PVA = 0.2; PETG, PCTG = 0.4; ABS, ASA, HIPS = 0.8; PC, PA, PA-CF, PPS = 1.0; unknown = 0.5.
- Seed weights: w_a 0.4, w_c 0.3, w_f 0.3.
- r = shrink × (w_a·aspect + w_c·corners + w_f·early_fan × shrink), clamped.
- Brim or brim-ear presence multiplies r by 0.6.

**Domain 4, thermal and under-extrusion.** Per layer:
- r_time = clamp((t_min − t_layer) / t_min, 0, 1) where t_layer < t_min, using `layer_time` after Orca's own slowdown.
- r_flow = max over moves of clamp((Q − 0.9 Q_max) / (0.2 Q_max), 0, 1), with Q from `actual_flow`.
- r_l = max(r_time, r_flow).
- The hot spot is the worst move.

**Domain 5, collisions.** Requires `context.aligned` = true; otherwise status `unaligned`, score omitted, overall computed from domains 1–4.
- Candidate points per layer:
  - seam points (`gcode_view` seams);
  - outer-wall speed steps where |Δv| > 50 mm/s within 2 mm;
  - `Support interface` contacts with the part (support-interface segments within w of P_l of the part).
- Map each to model coordinates.
- Risk per point = max over stress peaks of ratio × exp(−d / r0), and max over keep-out samples of exp(−d / r0), with r0 = 2w. Take the larger of the two.
- r_l = the max over the layer's points.

**Performance target.** Score a 6-hour H2D plate in under 60 s on the MacBook Air. Precompute P_l once, use STRtree for point and segment queries, and do not hold more than 3 layers of polygons in memory at once for domains 1–2.

### 16.5 Loop policy

**16.5.1 Dial levels** (`config.json` `dial`; default 1)

| Level | Name | Tier 1 (slicer) | Tier 2 (CAD) | Persist overrides to calib defaults |
|---|---|---|---|---|
| 0 | Manual | gate before every iteration | proposal only, gate | gate |
| 1 | Guarded | auto up to the slicer cap | gate every CAD edit | gate |
| 2 | Trusted | auto | auto up to the CAD cap | gate |
| 3 | Full auto | auto | auto | auto |

- **Caps per level:** slicer 4, CAD 2 (placeholders, configurable per level).
- **Always gated, at every level:**
  - starting a print (the agent never does this);
  - writing the owner's own preset files;
  - editing or removing keep-out faces;
  - `calib reset`;
  - anything touching secrets.

**16.5.2 Gates**
- A gate sets RunState `input_required`, with `gate_id` and a 4-character `token_hint`.
- `print_loop approve` succeeds only with the matching `gate_id` and `token`. The agent passes the token only after the owner types or confirms it in chat, or presses Go in the Agent Link panel (reusing the `queue_go` pattern).
- The server rejects tokens older than 24 h.
- (Main-session note, 18 Nov: the owner decided that approvals use the client's own MCP permission layer. Keep the gate model, but make the approve action a separate small tool or action that the person can set to "ask first" in the client; do not rely on a typed token alone. Record this change here.)

**16.5.3 Knob families** (Tier 1). Change **one family per iteration**. Keys are Orca option keys, bounded by `orcalink/data/orca-options.json` limits and the filament temperature range.

| Family | Orca keys | Step | Triggered by |
|---|---|---|---|
| retraction | `retraction_length`, `retraction_speed`, `wipe`, `wipe_distance`, `z_hop`, `z_hop_types` | length ±0.2 mm, wipe on | stringing |
| travel | `reduce_crossing_wall`, `max_travel_detour_distance`, `travel_speed` | avoid-crossing on, then detour +50% | stringing |
| temperature | `nozzle_temperature` (and initial layer) | −5 °C, never below T_lo + 5 | stringing, thermal (raise for flow) |
| overhang | `enable_overhang_bridge_fan`, `overhang_fan_speed`, `overhang_1_4_speed` … `overhang_4_4_speed`, `bridge_speed` | fan +20%, speeds −20% | overhang |
| cooling | `slow_down_layer_time`, `slow_down_min_speed`, `fan_min_speed`, `fan_max_speed`, `close_fan_the_first_x_layers` | time +2 s; first-layer fans off for shrink ≥ 0.8 | thermal, warp |
| adhesion | `brim_type`, `brim_width`, `brim_ears` points at corners < 90° | ears on, then width +3 mm | warp |
| seam | `seam_position`, `seam_gap`, painted seam via `orca_paint` | move away from collision hot spots | collision |
| speed | `outer_wall_speed`, `outer_wall_acceleration` | −15% | collision, overhang |
| flow | `filament_max_volumetric_speed` (per-run cap only) | −10% | thermal (flow) |

- **Family choice:** the domain with the lowest score picks next. Within it, take the first family in table order not yet tried this run.
- **How overrides apply:** as per-run overrides through `orca_project set` on a run copy of the project (`runs/<run_id>/<n>/project.3mf`). The original project is untouched.

**Tier 2 (CAD)** is entered only when a domain is still CRITICAL after its families are exhausted, or the slicer cap is reached.
- **Allowed ops:** chamfer (45°) or fillet on edges bounding faces under overhang hot spots, and corner fillets ≥ 2 mm on first-layer corners for warp.
- **Never on keep-out faces or their edges.**
- **Tools:** use the hub's feature tools; look up current names with `tool_groups`.
- **After each CAD edit:** FEM re-run if a study exists, then `orca_project replace`, then a re-slice.

**16.5.4 Runner state machine**
```
start → slice(n=0) → score → decide
decide:
  no CRITICAL and (n ≥ 2 and sum of last 2 overall deltas < 2) → done ("plateau")
  no CRITICAL and n == 0 and overall ≥ 90 → done ("clean")
  caps exhausted → escalated (gate cap_exhausted)
  next action needs a gate at this dial level → input_required
  else apply one family (or CAD op) → slice(n+1) → score → decide
regression rule: if overall delta < −3, revert that change, mark the family tried, continue
```

### 16.6 HAL contract

```python
class Driver(ABC):
    id: str
    def capabilities(self) -> Capabilities: ...      # firmware, kinematics, has_camera,
                                                     # native_warnings, max_flow, extruders
    def connect(self) -> None: ...                   # read-only session
    def poll(self) -> TelemetryPacket: ...           # merged state; latches events
    def snapshot(self) -> Optional[ImageRef]: ...    # on demand; closes stream after
    def close(self) -> None: ...
    # upload_and_start: deliberately absent (D3, "starting a print is the owner's call")
```

- **Polling:** every 5 s while printing, every 60 s when idle. Write every packet to `telemetry.jsonl`.
- **Job binding:** `print_watch` matches the printer's job by filename or `gcode_sha256` when available. Otherwise it is bound when the owner confirms.
- **Layer source order:** native → `inferred_z` (Z matched to the scored layer table) → `file_pos` (Moonraker).
- **Events:**
  - Latch any non-zero `print_error` with the current layer.
  - HMS severity = `(code >> 16) & 0xFFFF` mapped 1 → FATAL, 2 → SERIOUS, 3 → WARNING, 4 → INFO.
  - Text comes from Bambu Studio's `resources/hms/hms_en_<model>.json` found on the Mac. If missing, store the code only.
- **Detector config:** read `xcam` at job start and on change; store it in `detector.json`.
- **ReplayDriver:** plays JSONL lines `{t, topic, payload}` at real time or ×N speed.

### 16.7 Calibration store

```sql
CREATE TABLE printers (printer_id TEXT PRIMARY KEY, driver TEXT, model TEXT, nozzle_mm REAL,
  capabilities_json TEXT, added_at TEXT);
CREATE TABLE filaments (filament TEXT PRIMARY KEY, filament_type TEXT, profile_json TEXT);
CREATE TABLE params (printer_id TEXT, filament TEXT, key TEXT, value REAL, source TEXT,
  updated_at TEXT, PRIMARY KEY (printer_id, filament, key));         -- seed overrides (§16.4)
CREATE TABLE beliefs (printer_id TEXT, filament TEXT, domain TEXT, bucket INTEGER,
  alpha REAL, beta REAL, PRIMARY KEY (printer_id, filament, domain, bucket));
CREATE TABLE jobs (job_id TEXT PRIMARY KEY, printer_id TEXT, filament TEXT, run_id TEXT,
  report_id TEXT, gcode_sha256 TEXT, started_at TEXT, ended_at TEXT, final_state TEXT,
  detector_json TEXT);
CREATE TABLE outcomes (job_id TEXT, domain TEXT, label TEXT, weight REAL, source TEXT,
  layer INTEGER, note TEXT);       -- label: ok | defect ; source: event | photo | rating | inferred
CREATE TABLE overrides (printer_id TEXT, filament TEXT, key TEXT, value TEXT, status TEXT,
  evidence_json TEXT, created_at TEXT);   -- status: proposed | approved | rejected
```

**Labels:**
- **Buckets:** the predicted p95 risk falls into one of five buckets (0–0.2, …, 0.8–1).
- **Defect:** a SERIOUS-or-worse event or a DEFECT_SIGNAL at layer L. The domain is the one with the highest predicted risk within ±3 layers of L. Weight 1.0, multiplied by 0.5 if that detector's sensitivity was low.
- **OK:** final state `finished` and no event in a domain counts as ok for that domain, weight 0.5. If the detector for that domain was off, the weight is 0 (D8). Stringing has no detector, so its weight is 0.2.
- **Photo or rating (D10):** weight 1.5, overrides the inferred label for that domain.
- **Update:** alpha += weight for a defect, beta += weight for ok.

**Proposals:**
- Propose a seed change when the posterior mean defect rate in the top two buckets is ≥ 0.5 with alpha + beta ≥ 4.
- The proposal moves the domain's threshold seed one step (e.g. D0 −0.5 mm), or records a knob family as preferred-first for that filament.

### 16.8 Spike steps and acceptance criteria

| Step | Work | Done when |
|---|---|---|
| 1 | Prove the OrcaSlicer 2.5 pipeline plugin under the CLI (`--slicing-pipeline-plugin`): a no-op plugin at `psGCodePostProcess` that writes a sidecar file. | A headless `orca_slice` produces the sidecar, with no prompt or window. Record yes/no and how permissions behave in §13. If no, the plugin stays GUI-only and §3 is noted. |
| 2 | Slice a 20 mm cube with an overhang on H2D presets; unzip it. | §4/§6 updated with the real file list, the exact tag strings, the arc state and md5 presence. Fixture saved. |
| 3 | Dialect + arcs in `gcode/` on top of `gcode_view`. | Both fixtures parse to the same layer count and the same per-layer extrusion length within 1% as `gcode_read`'s totals; arcs segmented with chord error ≤ 0.1 mm. |
| 4 | Fiducial alignment. | An asymmetric L-bracket (FreeCAD) is sliced. Three known vertices map from G-code to model coordinates within 0.2 mm, including after `arrange`. `aligned` is stored. |
| 5 | Domains 1–4 + report + schema. | Each domain has a fixture that raises it (long travel, 60° overhang, tall thin ABS part, tiny spire) and one that does not. The raising fixture scores ≥ 20 points lower. The report validates against its schema. Performance target met. |
| 6 | Domain 5. | On the fiducial with a synthetic stress peak, a seam placed on the peak scores lower than a seam painted away from it. |
| 7 | Loop policy + runner. | On the stringing fixture at dial 3, the runner improves the overall score and exits "plateau" or "clean" within the caps. At dial 1, a CAD edit stops at a gate, and `approve` without the token is refused. |
| 8 | HAL socket + ReplayDriver + events. | Replaying a recorded or synthesized Bambu session produces packets that validate, latches a transient `print_error`, maps HMS severity correctly, and stores detector config. |
| 9 | Calibration store + learning. | Replaying 6 synthetic jobs (3 with spaghetti at high-risk layers) yields a proposal for the right domain, and none when the detector was off. |
| 10 | Read-only Bambu LAN driver. | **Needs the owner** (printer on LAN, access code entered by him through the secrets flow): live packets for one real print, no writes sent to the printer. |
| 11 | Moonraker driver. | Passes the replay suite with recorded Moonraker JSON; live test only if a Klipper printer is ever available. |

### 16.9 Fixtures

- `cube_overhang_h2d.gcode.3mf` (from step 2)
- `prusa_dialect_sample.gcode` (from a non-Bambu Orca preset, sliced by Orca)
- `stringing_towers.3mf`, `overhang60.3mf`, `tall_abs.3mf`, `spire.3mf`
- `fiducial_L.FCStd` + sliced copy
- `replay/bambu_print_ok.jsonl`, `replay/bambu_spaghetti.jsonl`, `replay/moonraker_print.jsonl` (synthesized from documented payloads until real captures exist; mark them as synthesized)

### 16.10 Privacy and safety

- **Secrets:** access codes, serials and IPs never appear in tool output, logs, commits or fixtures. Replay files replace them with placeholders.
- **No printer writes:** no command that changes printer state is ever sent. Drivers subscribe and read only.
- **Credits:** `CREDIT` string, plus attribution for ha-bambulab tables and for Stefan Hermann / CNC Kitchen wherever ScanRuler-FreeCAD tools are called.

---

## 17. Changes made while building (18 Nov 2026)

§16 lets an agent change a design default when it records the change and the reason here.

| # | Where | Change | Reason |
|---|---|---|---|
| C1 | §16.1 discovery | orcalink finds add-ons by convention: a package with an `orcalink_addon` module, on the path or in a folder that `ORCALINK_ADDONS` lists. No `AGENTLINK_PRINTLOOP` variable. | orcalink must name no add-on, even in a variable name. Same pattern as Agent Link's `agentlink_families`. |
| C2 | §16.1 data | Seeds, dial table, knob families, dialect tags and tool descriptions are versioned data files under `printloop/data/` (`defaults.json`, `dial.json`, `knobs.json`, `dialects.json`, `tools.json`, `schema/`), each entry with a source and a date. | Data first (the owner, 18 Nov). |
| C3 | §16.4 stringing | A travel with d_open under `stringing.d_open_min` (0.5 mm) adds no risk. A travel that does not start and end on the layer's printed section adds no risk. | With the plain sigmoid every short travel added about 0.04, and a normal layer scored as stringy. The approach from the start G-code is not a string between two points of the part. |
| C4 | §16.4 regions | For stringing and overhang, P_l is the layer's section: the extrusions plus the inside of the outer-wall loops (even-odd, so holes stay holes). | Sparse infill leaves gaps. Travels over the infill of the part are inside the part (OrcaSlicer does not retract there). |
| C5 | §16.4 overhang | u is the fraction of the segment's own ribbon (width w) outside buffer(P_{l-1}, w/2), not the fraction of its centre line. | With the centre line, u stays 0 until the shift per layer is more than one line width (about 65° at 0.2 mm) and then jumps to 1. |
| C6 | §16.4 warp | The warp domain score is 100 × (1 − r) for the part-level risk r, not the p95 of layer risks. | The p95 over all layers makes a part-level risk depend on the layer count. |
| C7 | §16.4 arcs | Chord error at most 0.05 mm and at most 2% of the radius. | A 1 mm arc at 0.05 mm loses 1.7% of its length; the step-3 criterion is 1%. |
| C8 | §16.5.2 gates | Approval goes through its own tool, `print_approve`, that the person sets to "ask first" in the client's MCP permission layer. The 4-character token stays as a second check. `print_loop` actions approve and reject are refused and point there. | the owner, 18 Nov (main-session note in §16.5.2). |
| C9 | §16.5.4 runner | A domain at or above the clean score (90) and not CRITICAL picks no family. With no domain left to work on, the run is done: "clean" when all domains are at 90 or more, else "families_tried". A CAD edit is made by the agent in FreeCAD; the runner proposes it (`next.do = cad_edit`) and continues when `print_loop step` gets the changed project in `path`. The regression rule's delta is against the last kept iteration. | The design did not say what happens when no family is left and nothing is CRITICAL. The orcalink server has no FreeCAD. |
| C10 | §16.2 resources, Tasks | Not built in this run: the tools answer synchronously. | Steps 1–7 scope. |
| C11 | §16.4 thermal, overhang speed | The actual speed is gcode_view's estimate (from rest at the layer's acceleration, over half the move). | It is what `gcode_read` gives (D2). |

