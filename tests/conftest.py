import sys
import os

# All source modules import each other by bare name, so src/ must be on sys.path.
SRC = os.path.join(os.path.dirname(__file__), "..", "src")
if SRC not in sys.path:
    sys.path.insert(0, os.path.abspath(SRC))

# Run any Qt GUI smoke tests headlessly (no window pops up locally; works in CI).
# Must be set before a QApplication is created.
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

# Use non-interactive matplotlib backend before any mpl import.
import matplotlib
matplotlib.use("Agg")
