import sys
from pathlib import Path

# Ensure the src layout is on the path when the .pth file isn't honoured
# (can happen with Python 3.14 and certain poetry configurations).
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))
