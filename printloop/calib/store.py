# SPDX-License-Identifier: AGPL-3.0-only
"""The calibration store (§16.7): SQLite in the user folder
(~/AgentLink/printloop/calib.sqlite). It keeps learned values; an update of
the add-on never touches it.

This run (spike steps 1-7) gives the tables and the seed overrides
(params) that the scorer reads. Learning from jobs (spike step 9) is not
built yet.
"""
import datetime
import os
import sqlite3

from .. import paths

DDL = """
CREATE TABLE IF NOT EXISTS printers (printer_id TEXT PRIMARY KEY, driver TEXT, model TEXT, nozzle_mm REAL,
  capabilities_json TEXT, added_at TEXT);
CREATE TABLE IF NOT EXISTS filaments (filament TEXT PRIMARY KEY, filament_type TEXT, profile_json TEXT);
CREATE TABLE IF NOT EXISTS params (printer_id TEXT, filament TEXT, key TEXT, value REAL, source TEXT,
  updated_at TEXT, PRIMARY KEY (printer_id, filament, key));
CREATE TABLE IF NOT EXISTS beliefs (printer_id TEXT, filament TEXT, domain TEXT, bucket INTEGER,
  alpha REAL, beta REAL, PRIMARY KEY (printer_id, filament, domain, bucket));
CREATE TABLE IF NOT EXISTS jobs (job_id TEXT PRIMARY KEY, printer_id TEXT, filament TEXT, run_id TEXT,
  report_id TEXT, gcode_sha256 TEXT, started_at TEXT, ended_at TEXT, final_state TEXT,
  detector_json TEXT);
CREATE TABLE IF NOT EXISTS outcomes (job_id TEXT, domain TEXT, label TEXT, weight REAL, source TEXT,
  layer INTEGER, note TEXT);
CREATE TABLE IF NOT EXISTS overrides (printer_id TEXT, filament TEXT, key TEXT, value TEXT, status TEXT,
  evidence_json TEXT, created_at TEXT);
"""


def db_path():
    return os.path.join(paths.home(), "calib.sqlite")


def connect(create=True):
    p = db_path()
    if not create and not os.path.isfile(p):
        return None
    c = sqlite3.connect(p)
    c.executescript(DDL)
    return c


def params(printer, filament):
    """{seed key: value} overrides for (printer, filament), or {}."""
    c = connect(create=False)
    if c is None:
        return {}
    try:
        rows = c.execute("SELECT key, value FROM params WHERE printer_id = ? AND filament = ?", (printer, filament)).fetchall()
    finally:
        c.close()
    return {k: v for k, v in rows}


def set_param(printer, filament, key, value, source):
    c = connect()
    try:
        c.execute("INSERT OR REPLACE INTO params VALUES (?, ?, ?, ?, ?, ?)",
                  (printer, filament, key, float(value), source, datetime.datetime.now(datetime.timezone.utc).isoformat()))
        c.commit()
    finally:
        c.close()
