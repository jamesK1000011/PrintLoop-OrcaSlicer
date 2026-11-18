# SPDX-License-Identifier: AGPL-3.0-only
"""Loop policy (§16.5.1, §16.5.2): the autonomy dial, caps, the always-gated
list, and gate tokens. The server enforces the gates; it does not trust the
client to.

Change (§17, owner's decision, 18 Nov): a gate is approved with its own small tool,
print_approve, that the person can set to "ask first" in the client's MCP
permission layer. The 4-character token stays as a second check.
"""
import time

from .. import ids, paths, seeds


def table():
    return seeds.load("dial")


def dial_level(dial=None):
    t = table()
    if dial is None:
        dial = paths.config().get("dial", t["default"])
    d = int(dial)
    if str(d) not in t["levels"]:
        names = ", ".join(k + " " + v["name"] for k, v in t["levels"].items())
        raise ValueError(f"dial: 0 to 3 ({names}), not {dial}.")
    return d


def caps(dial):
    lv = table()["levels"][str(dial)]
    over = (paths.config().get("caps") or {}).get(str(dial)) or {}
    return {"slicer": int(over.get("slicer", lv["caps"]["slicer"])), "cad": int(over.get("cad", lv["caps"]["cad"]))}


def needs_gate(kind, dial):
    """kind: slicer_step, cad_edit, persist, or an always-gated kind."""
    t = table()
    if kind in t["always_gated"] or kind in ("preset_write", "calib_reset", "cap_exhausted"):
        return True
    lv = t["levels"][str(dial)]
    key = {"slicer_step": "slicer", "cad_edit": "cad", "persist": "persist"}[kind]
    return lv[key] == "gate"


def new_gate(kind, proposal, now=None):
    tok = ids.token(int(table()["gate"]["token_chars"]))
    return {"gate_id": ids.ulid(), "kind": kind, "proposal": proposal, "token_hint": f"approve {tok}", "_token": tok,
            "_created": now if now is not None else time.time()}


def check_token(gate, gate_id, token, now=None):
    """None when the approval is valid, else the reason (code gated)."""
    if gate is None:
        return "this run has no open gate."
    if gate_id != gate["gate_id"]:
        return f"gate_id {gate_id}: the open gate is {gate['gate_id']}."
    if not token:
        return "token: give the 4 characters that the person typed or confirmed (token_hint shows them to the person)."
    if str(token).strip().upper() != gate["_token"]:
        return "token: it does not match the open gate."
    age = (now if now is not None else time.time()) - gate["_created"]
    if age > table()["gate"]["token_max_age_s"]:
        return "token: older than 24 h. Call print_loop step to open a new gate."
    return None


def public(gate):
    return None if gate is None else {k: v for k, v in gate.items() if not k.startswith("_")}
