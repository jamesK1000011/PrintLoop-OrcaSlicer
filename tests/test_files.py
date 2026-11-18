# SPDX-License-Identifier: AGPL-3.0-only
# FILES lists the files that the Claude extension's launcher (FreeCAD Agent
# Link's packaging/mcpb/server/index.js) fetches for this add-on. The
# launcher reads them as plain files. It does not use GitHub's API (60 calls
# an hour). Only the package and its licence go: not the tests, the Mac
# scripts or the CI files. A package file added or removed without FILES
# fails here. Make it again with
#   git ls-files LICENSE README.md pyproject.toml printloop | grep -v -E '(^|/)__pycache__/' | sort > FILES
import os
import subprocess

import pytest

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def test_files_list_is_current():
    try:
        out = subprocess.run(["git", "ls-files", "LICENSE", "README.md", "pyproject.toml", "printloop"], cwd=HERE,
                             capture_output=True, text=True, check=True).stdout
    except (OSError, subprocess.CalledProcessError):
        pytest.skip("not a git checkout")
    tracked = sorted(p for p in out.splitlines() if "__pycache__/" not in p)
    with open(os.path.join(HERE, "FILES"), encoding="utf-8") as f:
        listed = [ln.strip() for ln in f if ln.strip() and not ln.startswith("#")]
    assert listed == tracked, "FILES is stale: make it again (see the comment at the top of this test)"
    assert "printloop/orcalink_addon.py" in listed and "LICENSE" in listed
