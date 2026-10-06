"""The interactive menu of ``flyin``.

In a terminal: arrow keys, Enter, Space to mark several maps, typing to
filter. Elsewhere: numbers (see :mod:`flyin.ui`).
"""

import shutil
from collections import Counter
from pathlib import Path
from typing import Callable

from flyin import api, config, subject
from flyin.app import (
    THEMES, ask, do_compare, do_eval, do_generate, do_history, do_maps,
    do_rules, do_show, do_show_problems, do_test, need_config, problems,
    say, setup,
)
from flyin.config import Config
from flyin.tester.runner import FAIL, GROUP_ORDER, PASS, WARN, Case
from flyin.ui import Item, paint, pick, selection

__all__ = ["Menu", "selection"]

GROUP_TEXT = {
    "subject": "the subject's maps from your project, with their targets",
    "subject-invalid": "the subject's broken maps (must be rejected)",
    "extra": "more hand-made maps: capacity, deadlocks, mazes",
    "extra-invalid": "more broken maps (must be rejected)",
    "edge-valid": "tricky but valid input: comments, CRLF, 10 000 drones",
    "edge-invalid": "every parser rule broken once (must be rejected)",
    "challenge": "hard maps, target = exact optimum (optional)",
    "fuzz": "300 random maps with their exact optimum (optional)",
}
STATUS = {PASS: ("✓", "ok"), WARN: ("!", "warn"), FAIL: ("✗", "bad")}
Action = Callable[[], None]


def output_text(cfg: Config) -> str:
    """Say where the solution is read from."""
    if cfg.output_file:
        return f"file {cfg.output_file}"
    return "file {out}" if "{out}" in cfg.command else "terminal"


class Menu:
    """Main loop: a status box and the actions."""

    def __init__(self) -> None:
        """Load the settings (the setup runs on the first start)."""
        self.cfg: Config = need_config()

    # main loop ----------------------------------------------------------

    def run(self) -> int:
        """Loop until the user quits."""
        while True:
            self.header()
            count = len(problems())
            actions: list[tuple[Item, Action]] = [
                (Item("Test all maps", "every map, problems listed"),
                 self.test_all),
                (Item("Watch maps", "your program in the visualizer"),
                 self.watch),
                (Item("Watch the problems of the last test",
                      f"{count} map{'s' if count != 1 else ''}" if count
                      else "none",
                      "●" if count else "", "warn"), self.watch_problems),
                (Item("Compare two solutions", "side by side, in sync"),
                 self.compare),
                (Item("Evaluation report", "checklist + every problem"),
                 self.evaluate),
                (Item("More …", "one group, history, random map, rules, "
                      "subject maps"), self.more),
                (Item("Settings", "project, command, output, theme"),
                 self.settings),
            ]
            chosen = pick("What do you want to do?",
                          [item for item, _ in actions], back="quit")
            if chosen is None:
                return 0
            actions[chosen[0]][1]()

    def header(self) -> None:
        """Print a box with the project and the last test."""
        cfg = self.cfg
        rows = [("project", cfg.project),
                ("command", f"{cfg.command}   ({output_text(cfg)})")]
        runs = config.history()
        if runs:
            counts = Counter(r[0] for r in runs[-1]["results"].values())
            rows.append(("last test", f"{runs[-1].get('time', '?')} · "
                         f"{counts[PASS]} pass · {counts[WARN]} warn · "
                         f"{counts[FAIL]} fail"))
        imported = subject.imported()
        rows.append(("subject maps", f"{imported} imported" if imported else
                     "not imported (More … → Import)"))
        rows = [(k, v.replace(str(Path.home()), "~")) for k, v in rows]
        width = min(shutil.get_terminal_size().columns - 2,
                    max(13 + len(v) for _, v in rows) + 4)
        title = " flyin · Fly-In tester & visualizer "
        print()
        print(paint("╭─" + title + "─" * max(0, width - len(title) - 3)
                    + "╮", "accent"))
        room = width - 17
        for key, value in rows:
            if len(value) > room:
                value = value[:room - 1] + "…"
            print(paint("│ ", "accent") + paint(f"{key:<13}", "dim")
                  + value.ljust(room) + paint(" │", "accent"))
        print(paint("╰" + "─" * (width - 2) + "╯", "accent"))

    # actions ----------------------------------------------------------

    def test_all(self) -> None:
        """Run every map."""
        do_test(self.cfg)
        self._offer_problems()

    def test_group(self) -> None:
        """Run one group."""
        group = self._pick_group()
        if group is not None:
            do_test(self.cfg, [group], verbose=True)
            self._offer_problems()

    def watch(self) -> None:
        """Pick maps, run the program on each and play it."""
        refs = self._pick_maps()
        for number, ref in enumerate(refs, 1):
            if len(refs) > 1:
                say(f"\n[{number}/{len(refs)}] {Path(ref).name} - close "
                    "the window (Esc) for the next one", "bold")
            do_show(self.cfg, ref)

    def watch_problems(self) -> None:
        """Play the problem maps of the last test."""
        do_show_problems(self.cfg)

    def watch_file(self) -> None:
        """Play an output that is already in a file."""
        refs = self._pick_maps(several=False)
        if not refs:
            return
        output = Path(ask("Output file")).expanduser()
        if not output.is_file():
            say(f"no file '{output}'", "bad")
            return
        do_show(self.cfg, refs[0], str(output))

    def more(self) -> None:
        """The actions used less often."""
        extras: list[tuple[Item, Action]] = [
            (Item("Import the subject maps", "from your project, with "
                  "the targets"), self.import_subject),
            (Item("Test one group", "e.g. only the challenge maps"),
             self.test_group),
            (Item("Watch an output file", "a solution saved earlier"),
             self.watch_file),
            (Item("History of your test runs", "better or worse over "
                  "time"), do_history),
            (Item("Generate a random map", "solvable, with its lower "
                  "bound"), self.generate),
            (Item("List the maps", "with targets"), self.list_maps),
            (Item("How flyin reads the subject", "the rules"), do_rules),
        ]
        chosen = pick("More", [item for item, _ in extras])
        if chosen is not None:
            extras[chosen[0]][1]()

    def import_subject(self) -> None:
        """Copy the subject's maps from a folder of the project."""
        default = Path(self.cfg.project) / "maps"
        folder = Path(ask("Folder with the subject maps",
                          str(default))).expanduser()
        found = subject.find_maps(folder)
        if not found:
            say(f"no .txt maps in {folder}", "bad")
            return
        count, targets = subject.import_maps(folder)
        say(f"Imported {count} maps ({targets} with the subject's target) "
            f"into {config.state_dir() / 'maps'}", "ok")

    def compare(self) -> None:
        """Pick a map and two solutions, play them side by side."""
        refs = self._pick_maps(several=False)
        if not refs:
            return
        sources = [Item("now", "run your program now"),
                   Item("last", "output of your last test"),
                   Item("previous", "output of the test before"),
                   Item("a file …", "a saved solution")]
        sides = []
        for side, default in (("Left", 1), ("Right", 0)):
            ordered = sources[default:] + sources[:default]
            chosen = pick(f"{side} side", ordered)
            if chosen is None:
                return
            name = ordered[chosen[0]].label
            if name == "a file …":
                name = str(Path(ask(f"{side} file")).expanduser())
                if not Path(name).is_file():
                    say(f"no file '{name}'", "bad")
                    return
            sides.append(name)
        do_compare(self.cfg, refs[0], sides[0], sides[1])

    def evaluate(self) -> None:
        """Test everything and write the report."""
        do_eval(self.cfg, ask("Report file", "flyin-report.md"))

    def generate(self) -> None:
        """Write a random map and offer to watch it."""
        seed = ask("Seed (empty: random)")
        size = ask("Size WIDTHxHEIGHT", "6x3")
        shapes = [Item("grid", "zones on a grid"),
                  Item("random", "zones scattered, nearest neighbours")]
        shape = pick("Shape", shapes)
        drones = ask("Drones", "10")
        if not drones.isdigit() or (seed and not seed.lstrip("-").isdigit()):
            say("seed and drones must be numbers", "bad")
            return
        path = Path(f"maps-generated/seed_{seed or 'random'}.txt")
        if do_generate(int(seed) if seed else None, size, int(drones),
                       None if not seed else str(path),
                       shapes[shape[0]].label if shape else "grid") != 0:
            return
        latest = max(Path("maps-generated").glob("seed_*.txt"),
                     key=lambda p: p.stat().st_mtime)
        if ask("Watch your program on it? (y/n)", "y").lower() \
                .startswith(("y", "j")):
            do_show(self.cfg, str(latest))

    def list_maps(self) -> None:
        """Print the maps of one group (or all)."""
        group = self._pick_group(all_option=True)
        if group is not None:
            do_maps(group or None)

    def settings(self) -> None:
        """Change project, command, output, theme, timeout or jobs."""
        cfg = self.cfg
        chosen = pick("Settings", [
            Item("Project, command and output",
                 f"{cfg.command} ({output_text(cfg)})"),
            Item("Visualizer theme", cfg.theme),
            Item("Seconds per map", f"{cfg.timeout:g}"),
            Item("Maps in parallel", str(cfg.jobs)),
        ])
        if chosen is None:
            return
        if chosen[0] == 0:
            self.cfg = setup() or cfg
            return
        if chosen[0] == 1:
            theme = pick("Theme", [Item(t) for t in THEMES])
            if theme is not None:
                cfg.theme = THEMES[theme[0]]
        elif chosen[0] == 2:
            cfg.timeout = self._number("Seconds per map", cfg.timeout)
        else:
            cfg.jobs = max(1, int(self._number("Maps in parallel",
                                               cfg.jobs)))
        config.save(cfg)

    # helpers ----------------------------------------------------------

    def _offer_problems(self) -> None:
        """After a test, offer to watch the problem maps."""
        if problems() and ask("Watch the problem maps now? (y/n)",
                              "n").lower().startswith(("y", "j")):
            do_show_problems(self.cfg)

    @staticmethod
    def _groups(solvable_only: bool = False) -> list[str]:
        """Return the groups that have maps here."""
        present = {c.group for c in api.maps()}
        return [g for g in GROUP_ORDER if g in present
                and not (solvable_only and "invalid" in g)]

    def _pick_group(self, all_option: bool = False) -> str | None:
        """Return a group name ('' for all), or None."""
        groups = self._groups()
        counts = Counter(c.group for c in api.maps())
        items = [Item(g, f"{counts[g]:>3}  {GROUP_TEXT.get(g, '')}")
                 for g in groups]
        if all_option:
            items.append(Item("all", f"{sum(counts.values()):>3}"))
        chosen = pick("Which group?", items)
        if chosen is None:
            return None
        return groups[chosen[0]] if chosen[0] < len(groups) else ""

    def _pick_maps(self, several: bool = True) -> list[str]:
        """Return map paths: a group and its maps, or a file."""
        groups = self._groups(solvable_only=True)
        counts = Counter(c.group for c in api.maps())
        items = [Item(g, f"{counts[g]:>3}  {GROUP_TEXT.get(g, '')}")
                 for g in groups] + [Item("a map file of my own …")]
        chosen = pick("Which maps?", items)
        if chosen is None:
            return []
        if chosen[0] == len(groups):
            path = Path(ask("Map file")).expanduser()
            if not path.is_file():
                say(f"no file '{path}'", "bad")
                return []
            return [str(path)]
        cases = self._sorted(api.maps(groups[chosen[0]]))
        status = {r["map"]: r["status"] for r in config.last_run()}
        rows = []
        for case in cases:
            mark, color = STATUS.get(status.get(case.name, ""), ("·", "dim"))
            hint = f"optimum {case.optimum}" if case.optimum else \
                f"target {case.target}" if case.target else ""
            rows.append(Item(case.name.split("/", 1)[-1], hint, mark,
                             color))
        picked = pick(f"Maps in {groups[chosen[0]]}", rows, multi=several,
                      filterable=True)
        return [str(cases[i].path) for i in picked or []]

    @staticmethod
    def _sorted(cases: list[Case]) -> list[Case]:
        """Order maps from easy to hard where the name says so."""
        order = ["easy", "medium", "hard", "challenger", "critical"]
        return sorted(cases, key=lambda c: (
            next((i for i, word in enumerate(order) if f"/{word}/" in
                  f"/{c.name}"), len(order)), c.name))

    @staticmethod
    def _number(question: str, current: float) -> float:
        """Ask for a positive number."""
        try:
            return max(1.0, float(ask(question, f"{current:g}")))
        except ValueError:
            return current
