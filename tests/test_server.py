# SPDX-License-Identifier: AGPL-3.0-only
# The MCP surface (§16.2) through orcalink's server: orcalink finds PrintLoop
# by convention (ORCALINK_ADDONS), never by name. Stubs refuse with
# "unavailable: step 8+". Tool descriptions keep STE sentence length.
import io
import json
import os
import re
import subprocess
import sys

import pytest

from printloop import _orca, seeds

ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
MAC = os.path.join(ROOT, "tests", "fixtures", "mac")


@pytest.fixture
def server(tmp_path, monkeypatch):
    _orca.orcalink()
    monkeypatch.setenv("ORCALINK_ADDONS", ROOT)
    from orcalink.server import build

    return build(str(tmp_path))


def call(server, name, args):
    r = server.handle({"jsonrpc": "2.0", "id": 1, "method": "tools/call", "params": {"name": name, "arguments": args}})["result"]
    return r.get("isError", False), json.loads(r["content"][0]["text"])


def test_registered_by_discovery(server):
    names = [t["name"] for t in server.handle({"jsonrpc": "2.0", "id": 1, "method": "tools/list"})["result"]["tools"]]
    for n in ("print_score", "print_loop", "print_approve", "printer", "print_watch", "calib"):
        assert n in names
    err, st = call(server, "orca_status", {})
    assert st["addons"][0]["module"] == "printloop.orcalink_addon"
    assert st["addons"][0]["license"] == "AGPL-3.0-only"


def test_print_score_through_server(server):
    err, rep = call(server, "print_score", {"path": os.path.join(MAC, "cube_overhang_h2d.gcode.3mf")})
    assert not err, rep
    assert rep["schema"] == "printloop.score_report/1"
    err, r = call(server, "print_score", {"path": "nothing-here.gcode.3mf"})
    assert err and r["error"]["code"] == "not_found"


@pytest.mark.parametrize("tool,args", [("printer", {"action": "list"}), ("print_watch", {"action": "status"}), ("calib", {"action": "get"})])
def test_stubs_refuse(server, tool, args):
    err, r = call(server, tool, args)
    assert err and r["error"]["code"] == "unavailable"
    assert r["error"]["message"].startswith("unavailable: step 8+")


def test_print_loop_refusals(server):
    err, r = call(server, "print_loop", {"action": "approve", "run_id": "x"})
    assert err and r["error"]["code"] == "gated"
    err, r = call(server, "print_loop", {"action": "status"})
    assert err and r["error"]["code"] == "invalid_input"
    err, r = call(server, "print_loop", {"action": "status", "run_id": "NOPE"})
    assert err and r["error"]["code"] == "not_found"
    err, r = call(server, "print_approve", {"run_id": "NOPE", "gate_id": "g"})
    assert err and r["error"]["code"] == "not_found"


def test_absent_means_no_tools(tmp_path, monkeypatch):
    _orca.orcalink()
    monkeypatch.setenv("ORCALINK_ADDONS", str(tmp_path))
    # printloop must not be importable from the path for this check.
    monkeypatch.setattr(sys, "path", [p for p in sys.path if os.path.abspath(p) != os.path.abspath(ROOT)])
    from orcalink.server import build

    names = [t["name"] for t in build(str(tmp_path)).handle({"jsonrpc": "2.0", "id": 1, "method": "tools/list"})["result"]["tools"]]
    assert "print_score" not in names


def test_ste_sentence_length():
    for t in seeds.load("tools")["tools"]:
        for s in re.split(r"(?<=[.!?])\s+", t["description"]):
            words = [w for w in s.split() if re.search(r"[A-Za-z0-9]", w)]
            assert len(words) <= 20, (t["name"], s)


def test_standalone_server(tmp_path):
    env = dict(os.environ, PRINTLOOP_HOME=str(tmp_path))
    msgs = [{"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}}, {"jsonrpc": "2.0", "id": 2, "method": "tools/list"}]
    p = subprocess.run([sys.executable, os.path.join(ROOT, "printloop_server.py"), "--out", str(tmp_path)], input="\n".join(json.dumps(m) for m in msgs) + "\n",
                       capture_output=True, text=True, env=env, timeout=60)
    lines = [json.loads(x) for x in p.stdout.splitlines() if x.strip()]
    assert lines[0]["result"]["serverInfo"]["name"] == "printloop-orcaslicer"
    assert {t["name"] for t in lines[1]["result"]["tools"]} == {"print_score", "print_loop", "print_approve", "printer", "print_watch", "calib"}
