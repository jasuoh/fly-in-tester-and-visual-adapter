#!/usr/bin/env python3
"""Start flyin from a clone of this repository.

    python3 start.py            menu
    python3 start.py install    visualizer (pygame-ce) into .venv/
    python3 start.py test ...   every flyin command works the same

Uses .venv/ of this folder when it exists.
"""

import os
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
VENV = HERE / ".venv"
VENV_PYTHON = VENV / ("Scripts/python.exe" if os.name == "nt"
                      else "bin/python")


def install() -> int:
    """Create .venv with pygame-ce (needed only for the visualizer)."""
    if not VENV_PYTHON.exists():
        print("creating .venv ...")
        subprocess.run([sys.executable, "-m", "venv", str(VENV)],
                       check=True)
    print("installing pygame-ce ...")
    return subprocess.run([str(VENV_PYTHON), "-m", "pip", "install", "-q",
                           "--upgrade", "pip", "pygame-ce"]).returncode


def has_pygame() -> bool:
    """Return True if this Python can import pygame."""
    try:
        import pygame  # noqa: F401
    except ImportError:
        return False
    return True


def offer_install() -> None:
    """Menu start without the visualizer: offer to install it once."""
    if VENV_PYTHON.exists() or has_pygame() or not sys.stdin.isatty():
        return
    answer = input("The visualizer needs pygame-ce. Install it into "
                   ".venv/ now? [Y/n]: ").strip().lower()
    if answer in ("", "y", "yes", "j", "ja") and install() == 0:
        os.execv(str(VENV_PYTHON), [str(VENV_PYTHON), __file__])


if __name__ == "__main__":
    if sys.argv[1:2] == ["install"]:
        sys.exit(install())
    if not sys.argv[1:]:
        offer_install()
    if VENV_PYTHON.exists() and \
            Path(sys.prefix).resolve() != VENV.resolve():
        os.execv(str(VENV_PYTHON),
                 [str(VENV_PYTHON), __file__, *sys.argv[1:]])
    sys.path.insert(0, str(HERE))
    from flyin.app import main
    sys.exit(main())
