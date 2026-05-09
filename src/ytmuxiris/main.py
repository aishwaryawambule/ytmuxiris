from __future__ import annotations

import sys
from pathlib import Path

# Ensure the src layout is on sys.path when the venv .pth isn't honoured
# (reproducible with Python 3.14 + poetry editable installs).
_src = str(Path(__file__).parent.parent.parent)
if _src not in sys.path:
    sys.path.insert(0, _src)


def main() -> None:
    from ytmuxiris.app import YTMUXIRIS

    app = YTMUXIRIS()
    app.run()


if __name__ == "__main__":
    main()
