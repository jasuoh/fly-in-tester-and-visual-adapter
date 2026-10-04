"""Settings and results of ``flyin``, kept in ``.flyin/`` of the folder it
is started in.

``config.json`` remembers your project and its command, ``last_run.json``
and ``outputs/`` the last test, so its problem maps can be watched later.
"""

import json
import os
import sys
from dataclasses import asdict, dataclass
from pathlib import Path

from flyin.tester.runner import Outcome

STATE_DIR = ".flyin"


@dataclass
class Config:
    """What ``flyin`` needs to know about your project.

    Attributes:
        project: Folder your command runs in.
        command: Runs one map; ``{map}`` is the map path, ``{out}`` an
            output file (optional).
        theme: Visualizer theme.
        timeout: Seconds per map.
        jobs: Maps tested in parallel.
        output_file: For programs that always write the solution to the
            same file (relative to ``project``); empty when it is printed
            or written to ``{out}``.
    """

    project: str
    command: str
    theme: str = "mission"
    timeout: float = 30.0
    jobs: int = 4
    output_file: str = ""


def state_dir() -> Path:
    """Return the ``.flyin`` folder of the current directory."""
    return Path.cwd() / STATE_DIR


def load() -> Config | None:
    """Return the saved settings, or None before the first setup."""
    try:
        data = json.loads((state_dir() / "config.json").read_text("utf-8"))
        return Config(**data)
    except (OSError, ValueError, TypeError):
        return None


def save(config: Config) -> None:
    """Store the settings."""
    folder = state_dir()
    folder.mkdir(exist_ok=True)
    (folder / ".gitignore").write_text("*\n", "utf-8")
    (folder / "config.json").write_text(
        json.dumps(asdict(config), indent=2) + "\n", "utf-8")


def python_for(project: Path) -> str:
    """Return the project's virtualenv Python if it has one."""
    for venv in (".venv", "venv"):
        candidate = project / venv / "bin" / "python"
        if candidate.is_file():
            return str(candidate.resolve())
    return "python3" if sys.platform != "win32" else "python"


def detect_command(project: Path) -> str | None:
    """Guess how to run the project on one map, or None.

    Looks for ``main.py``, a compiled ``fly_in`` program and a package
    with ``__main__.py``, in that order.
    """
    python = python_for(project)
    for script in ("main.py", "fly_in.py", "fly-in.py"):
        if (project / script).is_file():
            return f"{python} {script} {{map}}"
    for binary in ("fly_in", "fly-in", "flyin"):
        path = project / binary
        if path.is_file() and os.access(path, os.X_OK):
            return f"./{binary} {{map}}"
    for package in sorted(project.iterdir()) if project.is_dir() else []:
        if (package / "__main__.py").is_file() and package.name != "flyin":
            return f"{python} -m {package.name} {{map}}"
    return None


def save_run(outcomes: list[Outcome]) -> None:
    """Remember the last test: verdicts plus the output of every map."""
    folder = state_dir()
    outputs = folder / "outputs"
    folder.mkdir(exist_ok=True)
    records = []
    for outcome in outcomes:
        record = {"map": outcome.case.name, "status": outcome.status,
                  "message": outcome.message, "expect": outcome.case.expect}
        if outcome.case.expect == "solve":
            target = outputs / outcome.case.name
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(outcome.output, "utf-8")
            record["output"] = str(target)
        records.append(record)
    (folder / "last_run.json").write_text(
        json.dumps(records, indent=2) + "\n", "utf-8")


def last_run() -> list[dict[str, str]]:
    """Return the records of the last test (empty if there was none)."""
    try:
        data = json.loads(
            (state_dir() / "last_run.json").read_text("utf-8"))
    except (OSError, ValueError):
        return []
    return [r for r in data if isinstance(r, dict)]
