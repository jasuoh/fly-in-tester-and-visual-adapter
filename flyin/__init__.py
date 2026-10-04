"""flyin: test your 42 Fly-In algorithm and watch it in a visualizer.

Run ``flyin`` (or ``./flyin`` in this repository) for the interactive
menu, or use it as a library::

    import flyin

    flyin.show("easy/01", lines)            # play a solution
    flyin.check("easy/01", lines).valid     # check it
    flyin.test("python3 main.py {map}", cwd="../my-project")

See :mod:`flyin.api` for every function.
"""

from flyin.api import (
    case_for, check, find_map, load_map, maps, run, show, test,
)

__version__ = "2.0.0"
__all__ = ["case_for", "check", "find_map", "load_map", "maps", "run",
           "show", "test"]
