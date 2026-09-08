"""The verdict table must survive a cp1250 console.

This has regressed once already. `render_table` prints ✅/❌, and a Polish
Windows console gives stdout cp1250, which cannot encode either character. The
crash lands at the very end of `capture` — after the browser work is done and
paid for — so it is expensive and easy to miss until it happens for real.
"""
import io
import subprocess
import sys
from pathlib import Path

from core.analyze import findings

REPO = Path(__file__).resolve().parents[2]


def _row(**over):
    r = dict(label="slot", expected_id="90069259", impression=True, click=True,
             impression_in_markup_only=False, other_serving_ids=[], error=None,
             measurement_vendors=[], verdict=findings.PASS)
    r.update(over)
    return r


def test_table_needs_a_utf8_stream():
    """Pins *why* the cli.py guard exists.

    The table deliberately uses ✅/❌ — that is the intended output, not a bug
    to encode away. What it needs is a stdout that can carry them. So: assert
    the glyphs are genuinely outside cp1250 (if this ever stops being true the
    guard is dead weight), and that a UTF-8 stream takes them fine.
    """
    text = findings.render_table([
        _row(),
        _row(impression=False, click=False, verdict=findings.MISSING),
        _row(impression=False, impression_in_markup_only=True,
             verdict=findings.INCONCLUSIVE),
    ])

    try:
        text.encode("cp1250")
    except UnicodeEncodeError:
        pass
    else:
        raise AssertionError(
            "table is now cp1250-clean; the cli.py stdout guard may be obsolete")

    io.TextIOWrapper(io.BytesIO(), encoding="utf-8", errors="strict").write(text)


def test_cli_module_forces_utf8_stdout():
    """Importing core.cli must leave stdout able to carry the table glyphs."""
    out = subprocess.run(
        [sys.executable, "-c",
         "import sys, core.cli; sys.stderr.write(sys.stdout.encoding)"],
        cwd=REPO, capture_output=True, text=True,
        env={"PYTHONIOENCODING": "cp1250", "PATH": "", "SYSTEMROOT": r"C:\Windows"},
    )
    assert out.stderr.strip().lower().replace("-", "") == "utf8", out.stderr
