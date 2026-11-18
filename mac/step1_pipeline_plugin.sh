#!/bin/bash
# SPDX-License-Identifier: AGPL-3.0-only
# Spike step 1 on the Mac: does an OrcaSlicer 2.5 slicing-pipeline plugin run
# under the command line (orca_slice), with no window and no prompt?
#
#   mac/step1_pipeline_plugin.sh install     # put the probe plugin in OrcaSlicer's plugin folder
#   (slice any project with orca_slice through the MCP tools)
#   mac/step1_pipeline_plugin.sh check <folder with the sliced G-code or -sliced.3mf>
#   mac/step1_pipeline_plugin.sh remove      # take the probe out again
#
# It touches only <OrcaSlicer data>/orca_plugins/printloop_probe/. It does not
# touch presets, the printer or any other setting. It never starts a print.
set -euo pipefail
HERE="$(cd "$(dirname "$0")/.." && pwd)"
DATA="${ORCA_DATA_DIR:-$HOME/Library/Application Support/OrcaSlicer}"
DEST="$DATA/orca_plugins/printloop_probe"
EXE="${AGENTLINK_ORCASLICER:-/Applications/OrcaSlicer.app/Contents/MacOS/OrcaSlicer}"

case "${1:-}" in
  install)
    [ -d "$DATA" ] || { echo "No OrcaSlicer data folder at: $DATA (set ORCA_DATA_DIR)"; exit 1; }
    mkdir -p "$DEST"
    cp "$HERE/printloop/plugin/printloop_orca.py" "$DEST/printloop_probe.py"
    echo "Installed: $DEST/printloop_probe.py"
    echo "Command-line options that name a plugin (empty: none):"
    "$EXE" --help 2>&1 | grep -i -E "plugin|pipeline" || true
    echo "Next: slice one project with orca_slice (MCP), then: $0 check <its -out folder>"
    ;;
  check)
    OUT="${2:?give the folder with the sliced G-code (the project's -out folder)}"
    found=0
    while IFS= read -r g; do
      if grep -q "^; printloop_probe: psGCodePostProcess ran" "$g"; then
        echo "YES marker in: $g"; found=1
      else
        echo "no marker in: $g"
      fi
      [ -f "$g.printloop.json" ] && { echo "sidecar: $g.printloop.json"; cat "$g.printloop.json"; echo; }
    done < <(find "$OUT" -maxdepth 2 -name "*.gcode" -newer "$DEST/printloop_probe.py" 2>/dev/null)
    for z in $(find "$OUT" -maxdepth 2 -name "*-sliced.3mf" -newer "$DEST/printloop_probe.py" 2>/dev/null); do
      if unzip -p "$z" "Metadata/plate_*.gcode" 2>/dev/null | grep -q "^; printloop_probe:"; then echo "YES marker inside: $z"; found=1; else echo "no marker inside: $z"; fi
    done
    [ -f "$HOME/AgentLink/printloop/plugin-probe.jsonl" ] && { echo "user folder log:"; tail -3 "$HOME/AgentLink/printloop/plugin-probe.jsonl"; }
    if [ "$found" = 1 ]; then echo "RESULT: the plugin ran headless."; else echo "RESULT: the plugin did not run headless (or no slice is newer than the install)."; fi
    ;;
  remove)
    rm -rf "$DEST" && echo "Removed: $DEST"
    ;;
  *)
    sed -n '3,13p' "$0"; exit 2 ;;
esac
