"""The subject's maps: imported from your project, never shipped.

The 42 subject comes with maps (easy, medium, hard, challenger) and turn
targets. They belong to the subject, so flyin does not publish them;
``flyin import-maps`` (or the setup) copies them from your project into
``.flyin/maps/`` and adds the known targets.
"""

import json
import shutil
from pathlib import Path

from flyin.tester.runner import LOCAL_MAPS

# "≤ N turns" of the subject; the challenger target 44 beats the record
# of 45 and is optional.
TARGETS = {
    "01_linear_path": 6, "02_simple_fork": 6, "03_basic_capacity": 8,
    "01_dead_end_trap": 15, "02_circular_loop": 20,
    "03_priority_puzzle": 12, "01_maze_nightmare": 45,
    "02_capacity_hell": 60, "03_ultimate_challenge": 35,
    "01_the_impossible_dream": 44,
}
OPTIONAL = {"01_the_impossible_dream"}


def find_maps(folder: Path) -> list[Path]:
    """Return the map files below ``folder`` (``*.txt``), sorted."""
    if not folder.is_dir():
        return []
    return sorted(p for p in folder.rglob("*.txt")
                  if not any(part.startswith(".") for part in
                             p.relative_to(folder).parts))


def import_maps(source: Path) -> tuple[int, int]:
    """Copy the maps below ``source`` into ``.flyin/maps/subject/``.

    Maps in a folder called ``invalid`` must be rejected; all others must
    be solved, with the subject's target where the name is known.

    Returns:
        (maps imported, maps with a known target)
    """
    target_dir = Path.cwd() / LOCAL_MAPS
    if target_dir.exists():
        shutil.rmtree(target_dir)
    entries = []
    with_target = 0
    for path in find_maps(source):
        relative = path.relative_to(source)
        name = f"subject/{relative.as_posix()}"
        destination = target_dir / name
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(path, destination)
        invalid = "invalid" in relative.parts
        entry: dict[str, object] = {
            "path": name, "group": "subject-invalid" if invalid
            else "subject", "expect": "error" if invalid else "solve"}
        if not invalid and path.stem in TARGETS:
            entry["target"] = TARGETS[path.stem]
            with_target += 1
            if path.stem in OPTIONAL:
                entry.update(optional_target=True,
                             note="optional: beat the record of 45 turns")
        entries.append(entry)
    target_dir.mkdir(parents=True, exist_ok=True)
    (target_dir / "manifest.json").write_text(
        json.dumps({"version": 1, "maps": entries}, indent=2) + "\n",
        "utf-8")
    return len(entries), with_target


def imported() -> int:
    """Return how many subject maps are imported here."""
    try:
        data = json.loads((Path.cwd() / LOCAL_MAPS / "manifest.json")
                          .read_text("utf-8"))
    except (OSError, ValueError):
        return 0
    return len(data.get("maps", []))
