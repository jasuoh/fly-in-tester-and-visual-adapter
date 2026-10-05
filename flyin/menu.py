"""The interactive menu of ``flyin``: pick a number, press Enter."""

from pathlib import Path

from flyin import api, config
from flyin.app import (
    SOURCES, THEMES, ask, do_compare, do_eval, do_generate, do_history,
    do_maps, do_rules, do_show, do_show_problems, do_test, need_config,
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
    "fuzz": "300 random maps with their exact optimum (optional)",
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


def selection(text: str, count: int) -> list[int] | None:
    """Parse ``all``, ``1,3,5`` or ``2-6`` into 0-based indexes.

    Returns None if ``text`` is not a selection (e.g. a map name).
    """
    text = text.replace(" ", "")
    if text.lower() == "all":
        return list(range(count))
    indexes: list[int] = []
    for part in text.split(","):
        first, dash, last = part.partition("-")
        if not first.isdigit() or (dash and not last.isdigit()):
            return None
        stop = int(last) if dash else int(first)
        for number in range(int(first), stop + 1):
            if 1 <= number <= count and number - 1 not in indexes:
                indexes.append(number - 1)
    return indexes or None


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
            ("Watch maps (your program in the visualizer)", self.watch),
            ("Watch the problems of the last test", self.watch_problems),
            ("Compare two solutions side by side", self.compare),
            ("Evaluation report (all maps + checklist)", self.evaluate),
            ("More ...", self.more),
            ("Settings", self.settings),
        ]
        while True:
            say(f"\nProject: {self.cfg.project}", "dim")
            say(f"Command: {self.cfg.command}", "dim")
            say("Output:  " + (f"file {self.cfg.output_file}"
                               if self.cfg.output_file else
                               "file {out}" if "{out}" in self.cfg.command
                               else "terminal"), "dim")
            labels = [label for label, _ in actions]
            count = len(problems())
            if count:
                labels[2] += f"  ({count})"
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
        ref = refs[0]
        output = ask("Output file")
        if not Path(output).expanduser().is_file():
            say(f"no file '{output}'", "bad")
            return
        do_show(self.cfg, ref, str(Path(output).expanduser()))

    def more(self) -> None:
        """The actions used less often."""
        extras = [
            ("Test one group", self.test_group),
            ("Watch an output file", self.watch_file),
            ("History of your test runs", do_history),
            ("Generate a random map", self.generate),
            ("List the maps", self.list_maps),
            ("How flyin reads the subject (rules)", do_rules),
        ]
        picked = choose("More", [label for label, _ in extras])
        if isinstance(picked, int):
            extras[picked][1]()

    def compare(self) -> None:
        """Pick a map and two solutions, play them side by side."""
        refs = self._pick_maps(several=False)
        if not refs:
            return
        say("A solution is: now (run your program), last / previous (the "
            "outputs of your last two tests) or a file.", "dim")
        left = ask("Left", "last")
        right = ask("Right", "now")
        for side in (left, right):
            if side not in SOURCES and not Path(side).expanduser().is_file():
                say(f"'{side}' is neither {', '.join(SOURCES)} nor a file",
                    "bad")
                return
        do_compare(self.cfg, refs[0], left, right)

    def evaluate(self) -> None:
        """Test everything and write the report."""
        do_eval(self.cfg, ask("Report file", "flyin-report.md"))

    def generate(self) -> None:
        """Write a random map and offer to watch it."""
        seed = ask("Seed (empty: random)")
        size = ask("Size WIDTHxHEIGHT", "6x3")
        shape = "random" if ask("Shape: grid or random", "grid") \
            .lower().startswith("r") else "grid"
        drones = ask("Drones", "10")
        if not drones.isdigit() or (seed and not seed.lstrip("-").isdigit()):
            say("seed and drones must be numbers", "bad")
            return
        path = Path(f"maps-generated/seed_{seed or 'random'}.txt")
        if do_generate(int(seed) if seed else None, size, int(drones),
                       None if not seed else str(path), shape) != 0:
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

    def _pick_maps(self, several: bool = True) -> list[str]:
        """Return map paths: by group and number(s), by name or a file."""
        groups = [g for g in GROUP_ORDER if "invalid" not in g]
        picked = choose("Which map?", [f"from group '{g}'" for g in groups]
                        + ["a map file of my own"], allow_text=True)
        if picked is None:
            return []
        if isinstance(picked, str):
            return self._by_name(picked)
        if picked == len(groups):
            path = Path(ask("Map file")).expanduser()
            if not path.is_file():
                say(f"no file '{path}'", "bad")
                return []
            return [str(path)]
        order = ["easy", "medium", "hard", "challenger", "critical"]
        cases = sorted(api.maps(groups[picked]), key=lambda c: (
            next((i for i, word in enumerate(order) if f"/{word}/" in
                  f"/{c.name}"), len(order)), c.name))
        if several:
            say("One number, several (1,3,5), a range (2-6) or 'all'.",
                "dim")
        chosen = choose(f"Maps in '{groups[picked]}'", [
            c.name.split("/", 1)[-1] + (f"   (target {c.target})"
                                        if c.target else "")
            for c in cases], allow_text=True)
        if isinstance(chosen, int):
            return [str(cases[chosen].path)]
        if chosen is None:
            return []
        numbers = selection(chosen, len(cases)) if several else None
        if numbers:
            return [str(cases[i].path) for i in numbers]
        return self._by_name(chosen)

    @staticmethod
    def _by_name(text: str) -> list[str]:
        """Resolve a typed name; list the candidates if it is ambiguous."""
        try:
            return [str(api.find_map(text))]
        except LookupError as error:
            say(str(error), "bad")
            return []

    @staticmethod
    def _number(question: str, current: float) -> float:
        """Ask for a positive number."""
        try:
            return max(1.0, float(ask(question, f"{current:g}")))
        except ValueError:
            return current
