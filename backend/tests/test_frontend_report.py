"""The page's own report logic, checked under pytest.

frontend/index.html decides what the copied report and the scan list say:
which viewport a test opens in, the row for an ID the sheet does not book,
and "??" for a creative that was delivered and never on screen. Those checks
live in frontend/tests/test_report.js, which loads the page script into a
Node vm with a stub DOM — offline, no browser. This runs it, so a change to
the page that breaks them fails the suite like any other test.
"""
import shutil
import subprocess
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
SCRIPT = REPO / "frontend" / "tests" / "test_report.js"
NODE = shutil.which("node")


@pytest.mark.skipif(NODE is None, reason="node is not installed")
def test_frontend_report_checks_pass():
    proc = subprocess.run([NODE, str(SCRIPT)], cwd=str(REPO), capture_output=True,
                          text=True, encoding="utf-8", timeout=120)
    out = proc.stdout + proc.stderr
    assert proc.returncode == 0, out
    assert " 0 failed" in out, out
