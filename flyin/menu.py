"""The interactive menu of ``flyin``: pick a number, press Enter."""

from pathlib import Path

from flyin import api, config
from flyin.app import (
    THEMES, ask, do_maps, do_show, do_show_problems, do_test, need_config,
    problems, say, setup,
)
from flyin.config import Config
from flyin.tester.runner import GROUP_ORDER

GROUP_TEXT = {
    "provided": "the maps of the subject, with their turn targets",
    "provided-invalid": "the broken maps of the subject (must be rejected)",
    "edge-valid": "tricky but valid maps",
    "edge-invalid": "every parser rule broken once (must be rejected)",
    "challenge": "hard maps, target = exact optimum (optional)",
}


def choose(title: str, options: list[str], allow_text: bool = False,
           back: str = "back") -> int | str | None:
    """Show numbered options; return the index, typed text, or None."""
    say(f"\n{title}", "bold")
    for number, option in enumerate(options, 1):
        print(f"  {number:>2}  {option}")
    print(f"   0  {back}")
    hint = "number" + (" or part of a name" if allow_text else "")
    answer = ask(f"Choose ({hint})")
    if answer in ("", "0", "q"):
        return None
    if answer.isdigit() and 1 <= int(answer) <= len(options):
        return int(answer) - 1
    if allow_text:
        return answer
    say("not a choice", "bad")
    return None


class Menu:
    """Main loop: shows the project, offers every action."""

    def __init__(self) -> None:
        """Load the settings (the setup runs on the first start)."""
        say("flyin: Fly-In tester & visualizer", "bold")
        self.cfg: Config = need_config()

    def run(self) -> int:
        """Loop until the user quits."""
        actions = [
            ("Test all maps", self.test_all),
            ("Test one group", self.test_group),
            ("Watch a map (your program in the visualizer)", self.watch),
            ("Watch the problems of the last test", self.watch_problems),
            ("Watch an output file", self.watch_file),
            ("List the maps", self.list_maps),
            ("Settings", self.settings),
        ]
        while True:
            say(f"\nProject: {self.cfg.project}", "dim")
            say(f"Command: {self.cfg.command}", "dim")
            labels = [label for label, _ in actions]
            count = len(problems())
            if count:
                labels[3] += f"  ({count})"
            picked = choose("What do you want to do?", labels, back="quit")
            if picked is None:
                return 0
            assert isinstance(picked, int)
            actions[picked][1]()

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
        """Pick a map, run the program on it, open the visualizer."""
        ref = self._pick_map()
        if ref is not None:
            do_show(self.cfg, ref)

    def watch_problems(self) -> None:
        """Play the problem maps of the last test."""
        do_show_problems(self.cfg)

    def watch_file(self) -> None:
        """Play an output that is already in a file."""
        ref = self._pick_map()
        if ref is None:
            return
        output = ask("Output file")
        if not Path(output).expanduser().is_file():
            say(f"no file '{output}'", "bad")
            return
        do_show(self.cfg, ref, str(Path(output).expanduser()))

    def list_maps(self) -> None:
        """Print the maps of one group (or all)."""
        group = self._pick_group(all_option=True)
        if group is not None:
            do_maps(group or None)

    def settings(self) -> None:
        """Change project and command, theme, timeout or parallel jobs."""
        cfg = self.cfg
        picked = choose("Settings", [
            f"Project and command   {cfg.project}  |  {cfg.command}",
            f"Visualizer theme      {cfg.theme}",
            f"Seconds per map       {cfg.timeout:g}",
            f"Maps in parallel      {cfg.jobs}",
        ])
        if picked == 0:
            self.cfg = setup() or cfg
            return
        if picked == 1:
            theme = choose("Theme", list(THEMES))
            if isinstance(theme, int):
                cfg.theme = THEMES[theme]
        elif picked == 2:
            cfg.timeout = self._number("Seconds per map", cfg.timeout)
        elif picked == 3:
            cfg.jobs = max(1, int(self._number("Maps in parallel",
                                               cfg.jobs)))
        config.save(cfg)

    # helpers ----------------------------------------------------------

    def _offer_problems(self) -> None:
        """After a test, offer to watch the problem maps."""
        if problems() and ask("Watch the problem maps now? (y/n)",
                              "n").lower().startswith("y"):
            do_show_problems(self.cfg)

    def _pick_group(self, all_option: bool = False) -> str | None:
        """Return a group name ('' for all), or None."""
        options = [f"{g:<17} {GROUP_TEXT[g]}" for g in GROUP_ORDER]
        if all_option:
            options.append("all")
        picked = choose("Which group?", options)
        if not isinstance(picked, int):
            return None
        return GROUP_ORDER[picked] if picked < len(GROUP_ORDER) else ""

    def _pick_map(self) -> str | None:
        """Return a map path: by group and number, by name or a file."""
        picked = choose("Which map?", [
            f"from group '{g}'" for g in GROUP_ORDER if g != "edge-invalid"
            and g != "provided-invalid"] + ["a map file of my own"],
            allow_text=True)
        if picked is None:
            return None
        if isinstance(picked, str):
            return self._by_name(picked)
        groups = [g for g in GROUP_ORDER if "invalid" not in g]
        if picked == len(groups):
            path = Path(ask("Map file")).expanduser()
            return str(path) if path.is_file() else None
        order = ["easy", "medium", "hard", "challenger", "critical"]
        cases = sorted(api.maps(groups[picked]), key=lambda c: (
            next((i for i, word in enumerate(order) if f"/{word}/" in
                  f"/{c.name}"), len(order)), c.name))
        chosen = choose(f"Maps in '{groups[picked]}'", [
            c.name.split("/", 1)[-1] + (f"   (target {c.target})"
                                        if c.target else "")
            for c in cases], allow_text=True)
        if isinstance(chosen, int):
            return str(cases[chosen].path)
        return None if chosen is None else self._by_name(chosen)

    @staticmethod
    def _by_name(text: str) -> str | None:
        """Resolve a typed name; list the candidates if it is ambiguous."""
        try:
            return str(api.find_map(text))
        except LookupError as error:
            say(str(error), "bad")
            return None

    @staticmethod
    def _number(question: str, current: float) -> float:
        """Ask for a positive number."""
        try:
            return max(1.0, float(ask(question, f"{current:g}")))
        except ValueError:
            return current
