import sys
import os

# All source modules import each other by bare name, so src/ must be on sys.path.
SRC = os.path.join(os.path.dirname(__file__), "..", "src")
if SRC not in sys.path:
    sys.path.insert(0, os.path.abspath(SRC))

# Use non-interactive matplotlib backend before any mpl import.
import matplotlib
matplotlib.use("Agg")
