# SPDX-License-Identifier: AGPL-3.0-only
"""Find orcalink (OrcaSlicer Agent Link) and import its public modules.

printloop imports orcalink (AGPL may use LGPL); orcalink never imports
printloop by name. Order: orcalink already on the path; the folder in
ORCALINK_PATH; a sibling checkout named agentlink-orcaslicer or
AgentLink-OrcaSlicer beside this repository.
"""
import os
import sys

_HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _candidates():
    env = os.environ.get("ORCALINK_PATH")
    if env:
        yield os.path.expanduser(env)
    parent = os.path.dirname(_HERE)
    for name in ("agentlink-orcaslicer", "AgentLink-OrcaSlicer", "OrcaSlicer-AgentLink"):
        yield os.path.join(parent, name)


def orcalink():
    try:
        import orcalink as ol  # noqa: F401

        return ol
    except ImportError:
        pass
    for d in _candidates():
        if os.path.isfile(os.path.join(d, "orcalink", "__init__.py")):
            sys.path.insert(0, d)
            import orcalink as ol

            return ol
    raise ImportError("orcalink not found: install OrcaSlicer Agent Link, or set ORCALINK_PATH to its folder.")


def gcode_view():
    orcalink()
    from orcalink import gcode_view as G

    return G


def orca3mf():
    orcalink()
    from orcalink import orca3mf as O

    return O
