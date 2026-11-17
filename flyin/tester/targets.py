"""The turn targets of the subject's maps, for both subject versions.

Subject 3.0 ships new versions of the maps under the same names, with
one reference per map: the optimum, the fewest turns physically possible.
To validate, a solution must stay within 25% of it (at most 1.25 x
optimum turns) on each of the 9 easy, medium and hard maps; the optimum
itself is a bonus, the challenger is optional.

The maps of the older subject have the same file names but other
content (other capacities, other zone types), so the 3.0 optimum does not
apply to them: on the old ``03_basic_capacity`` 4 turns are impossible.
A map is therefore recognised by its content (a fingerprint that ignores
comments and blank lines). Maps of the older subject keep the older rule:
"at most N turns", more is a warning.
"""

import hashlib
import math
from pathlib import Path

SUBJECT_VERSION = "3.0"
TOLERANCE = 1.25

# Subject 3.0: the optimum per map (file stem) ...
OPTIMUM = {
    "01_linear_path": 4, "02_simple_fork": 4, "03_basic_capacity": 4,
    "01_dead_end_trap": 8, "02_circular_loop": 10,
    "03_priority_puzzle": 6, "01_maze_nightmare": 13,
    "02_capacity_hell": 16, "03_ultimate_challenge": 26,
    "01_the_impossible_dream": 43,
}
# ... and the fingerprint of the 3.0 map with that name.
FINGERPRINT = {
    "01_the_impossible_dream": "4d2300c2d3acba12",
    "01_linear_path": "da9031866a8217e7",
    "02_simple_fork": "6072dc157ea22bcc",
    "03_basic_capacity": "fc9f5c4cf325e33d",
    "01_maze_nightmare": "0bcedbfb52ce7c97",
    "02_capacity_hell": "d20e4441fc42ed1a",
    "03_ultimate_challenge": "b2f83244d2efc9d0",
    "01_dead_end_trap": "9eeeb678186ef5fc",
    "02_circular_loop": "b5afa632278ce4c0",
    "03_priority_puzzle": "bc90bbe714d4b15c",
}
# The older subject: "<= N turns" per map; the challenger target 44
# (beat the record of 45) is optional.
OLD_TARGETS = {
    "01_linear_path": 6, "02_simple_fork": 6, "03_basic_capacity": 8,
    "01_dead_end_trap": 15, "02_circular_loop": 20,
    "03_priority_puzzle": 12, "01_maze_nightmare": 45,
    "02_capacity_hell": 60, "03_ultimate_challenge": 35,
    "01_the_impossible_dream": 44,
}
OPTIONAL = {"01_the_impossible_dream"}


def allowed_turns(optimum: int) -> int:
    """Return the most turns that still validate (1.25 x optimum)."""
    return math.floor(optimum * TOLERANCE)


def fingerprint(text: str) -> str:
    """Return a short hash of a map's content, without comments, blank
    lines and surrounding whitespace."""
    lines = [line.split("#")[0].strip()
             for line in text.replace("﻿", "").splitlines()]
    content = "\n".join(line for line in lines if line)
    return hashlib.sha256(content.encode()).hexdigest()[:16]


def is_current(stem: str, path: Path | None) -> bool:
    """Return True if ``path`` is the subject 3.0 map called ``stem``."""
    if path is None or stem not in FINGERPRINT:
        return False
    try:
        text = path.read_text("utf-8", errors="replace")
    except OSError:
        return False
    return fingerprint(text) == FINGERPRINT[stem]


def subject_entry(stem: str, path: Path | None = None) -> dict[str, object]:
    """Return the manifest fields of a subject map.

    Every field is always present, so a stale value of an earlier import
    is replaced. Unknown maps get no target.
    """
    entry: dict[str, object] = {
        "optimum": None, "target": None, "optional_target": False,
        "target_required": False, "note": "", "subject_version": None}
    optional = stem in OPTIONAL
    if is_current(stem, path):
        optimum = OPTIMUM[stem]
        entry.update(optimum=optimum, subject_version=SUBJECT_VERSION)
        if optional:
            entry.update(target=optimum, optional_target=True,
                         note=f"optional challenger (subject 3.0): the "
                              f"optimum is {optimum} turns")
        else:
            entry.update(target=allowed_turns(optimum),
                         target_required=True,
                         note=f"subject 3.0, required: at most "
                              f"{allowed_turns(optimum)} turns (1.25 x "
                              f"optimum {optimum}); the optimum is a bonus")
    elif stem in OLD_TARGETS:
        target = OLD_TARGETS[stem]
        entry.update(target=target, optional_target=optional,
                     subject_version="2",
                     note="optional: beat the record of 45 turns "
                          "(older subject)" if optional else
                     f"map of the older subject: target <= {target} turns "
                     "(the 3.0 optimum belongs to the new version of this "
                     "map)")
    return entry
