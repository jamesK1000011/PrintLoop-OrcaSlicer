# SPDX-License-Identifier: AGPL-3.0-only
import os
import sys
import tempfile

import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, ".."))
sys.path.insert(0, os.path.join(HERE, "fixtures"))


@pytest.fixture(autouse=True)
def plhome(monkeypatch, tmp_path):
    monkeypatch.setenv("PRINTLOOP_HOME", str(tmp_path / "plhome"))
    return tmp_path
