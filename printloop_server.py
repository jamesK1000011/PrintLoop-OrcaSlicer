# SPDX-License-Identifier: AGPL-3.0-only
# PrintLoop as its own MCP server over stdio, for use without
# OrcaSlicer Agent Link's server. It still needs orcalink (the package) for
# gcode_view, orca3mf and orca_slice: put it on the path, or set
# ORCALINK_PATH to its folder.
#   python3 /path/to/printloop_server.py [--out ~/Documents/AgentLink]
import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))


def main(argv=None):
    from printloop import VERSION, _orca

    _orca.orcalink()
    from orcalink import tools as OT
    from orcalink.protocol import Server, Tool, ToolError, serve_lines

    from printloop import tools as PT

    ap = argparse.ArgumentParser(description="PrintLoop for OrcaSlicer: an MCP server over stdio.")
    ap.add_argument("--out", default=os.environ.get("AGENTLINK_OUT", "~/Documents/AgentLink"))
    args = ap.parse_args(argv)
    out_dir = os.path.expanduser(args.out)
    os.makedirs(out_dir, exist_ok=True)
    own = {t.name: t.fn for t in OT.tools(lambda: out_dir)}
    specs = PT.specs({"out_dir": out_dir, "tools": own, "ToolError": ToolError, "api": 1})
    tools = [Tool(s["name"], s["description"], s["inputSchema"], s["fn"], changes=s["changes"], group=s["group"]) for s in specs]
    server = Server("printloop-orcaslicer", VERSION, tools,
                    instructions="PrintLoop: print_score scores a sliced plate; print_loop improves it on run copies; print_approve takes the person's approval. It never starts a print.")
    out = sys.stdout
    sys.stdout = sys.stderr

    def write(line):
        out.write(line if line.endswith("\n") else line + "\n")
        out.flush()

    serve_lines(server, sys.stdin.readline, write)
    return 0


if __name__ == "__main__":
    sys.exit(main())
