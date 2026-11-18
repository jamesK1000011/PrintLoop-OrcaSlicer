# SPDX-License-Identifier: AGPL-3.0-only
"""The user folder: ~/AgentLink/printloop/ (PRINTLOOP_HOME sets another).

config.json (dial, caps, printers, aligned setups; no secrets),
calib.sqlite (the calibration store), runs/<run_id>/<n>/ and jobs/.
An update of the add-on never writes here except through these calls.
"""
import json
import os


def home():
    h = os.path.expanduser(os.environ.get("PRINTLOOP_HOME") or "~/AgentLink/printloop")
    os.makedirs(h, exist_ok=True)
    return h


def config_path():
    return os.path.join(home(), "config.json")


def config():
    try:
        with open(config_path(), encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return {}


def save_config(cfg):
    p = config_path()
    tmp = p + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(cfg, f, indent=1)
    os.replace(tmp, p)


def run_dir(run_id, n=None):
    d = os.path.join(home(), "runs", run_id) if n is None else os.path.join(home(), "runs", run_id, str(n))
    os.makedirs(d, exist_ok=True)
    return d
