"""backend/ is a flat package-less directory (app.py does `from verifier import
...`), so put it on the path the same way running `python app.py` does."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
