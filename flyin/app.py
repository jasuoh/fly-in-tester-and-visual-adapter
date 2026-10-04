"""The ``flyin`` command: the menu, plus short commands for every action.

    flyin                       interactive menu
    flyin setup [PROJECT]       tell flyin how to run your project
    flyin test [WHAT ...]       test all maps, a group or some maps
    flyin show MAP [OUTPUT]     watch your program (or an output file)
    flyin show --problems       watch every map of the last test that
                                failed or missed its target
    flyin maps [WHAT]           list the maps
    flyin compare MAP [A] [B]   two solutions side by side; A and B are
                                now (run it), last, previous (outputs
                                of the last two tests) or a file
    flyin history               results of the earlier test runs
    flyin eval [-o FILE]        evaluation report (Markdown)
    flyin rules                 how flyin reads the subject
    flyin generate [--seed N]   write a random solvable map
    flyin check MAP OUTPUT      check an output file

``flyin run|view|list`` keep every option of the full tester
(:mod:`flyin.tester.cli`), for scripts and CI.
"""

import argparse
import random
import sys
from pathlib import Path
from typing import Any

from flyin import api, config
from flyin.config import Config
from flyin.tester.cli import main as tester_main, print_outcomes
from flyin.tester.generate import generate
from flyin.tester.runner import DEFAULT_GROUPS, FAIL, PASS, WARN, Outcome

THEMES = ("mission", "blueprint", "graphite", "ashen")
FIRST_MAP = "provided/easy/01_linear_path.txt"


def say(text: str = "", color: str = "") -> None:
    """Print, coloured on a terminal (``ok``, ``warn``, ``bad``, ``dim``)."""
    codes = {"ok": "32", "warn": "33", "bad": "31", "dim": "2",
             "bold": "1"}
    if color and sys.stdout.isatty():
        text = f"\033[{codes[color]}m{text}\033[0m"
    print(text)


def ask(question: str, default: str = "") -> str:
    """Ask a question; Enter keeps the default. Ctrl-D/Ctrl-C quit."""
    hint = f" [{default}]" if default else ""
    try:
        answer = input(f"{question}{hint}: ").strip()
    except (EOFError, KeyboardInterrupt):
        print()
        raise SystemExit(0)
    return answer or default


# setup ----------------------------------------------------------------

def setup(project: str | None = None, command: str | None = None,
          interactive: bool = True, output_file: str | None = None
          ) -> Config | None:
    """Find out how to run the project, try it on one map and save it.

    Asks (when ``interactive``) for the folder, the command and how the
    program hands over its solution: terminal, a file passed as
    ``{out}``, or always the same file.
    """
    old = config.load()
    if project is None:
        default = old.project if old else str(Path.cwd())
        project = ask("Folder of your Fly-In project", default) \
            if interactive else default
    folder = Path(project).expanduser().resolve()
    if not folder.is_dir():
        say(f"'{folder}' is not a folder", "bad")
        return None
    if command is None:
        guess = config.detect_command(folder) or \
            (old.command if old else "python3 main.py {map}")
        if interactive:
            say("\nThe command that runs your program on ONE map; {map} is "
                "replaced by the map path.", "dim")
            say("It must print the turns (D1-zone ...) and must not open a "
                "window.", "dim")
            command = ask("Command", guess)
        else:
            command = guess
    if "{map}" not in command:
        command += " {map}"
    if output_file is None:
        command, output_file = _ask_output(command, old) if interactive \
            else (command, old.output_file if old else "")
    new = Config(str(folder), command, output_file=output_file)
    if old is not None:
        new.theme, new.timeout, new.jobs = old.theme, old.timeout, old.jobs
    say(f"\nTrying it on {FIRST_MAP} ...", "dim")
    outcome = api.run(FIRST_MAP, new.command, new.project, 20,
                      new.output_file)
    _explain_first_run(outcome)
    config.save(new)
    say(f"Saved in {config.state_dir() / 'config.json'}", "dim")
    return new


def _ask_output(command: str, old: Config | None) -> tuple[str, str]:
    """Ask where the solution goes; return the command and output file."""
    current = "3" if old and old.output_file else \
        "2" if "{out}" in command else "1"
    say("\nWhere does your program put the solution (the turn lines)?",
        "bold")
    print("   1  prints it in the terminal")
    print("   2  writes it to a file whose name it gets as an argument")
    print("   3  always writes the same file (e.g. output.txt)")
    answer = ask("Choose", current)
    if answer == "2":
        if "{out}" not in command:
            say("{out} stands for that file name in the command.", "dim")
            command = ask("Command", command + " {out}")
        return command, ""
    command = command.replace(" {out}", "")
    if answer == "3":
        name = ask("File name, relative to your project",
                   (old.output_file if old else "") or "output.txt")
        return command, name
    return command, ""


def _explain_first_run(outcome: Outcome) -> None:
    """Say whether the test run worked and what to do if not."""
    if outcome.status == PASS:
        say(f"Works: {outcome.message}", "ok")
        return
    say(f"{outcome.status}: {outcome.message}", "warn")
    if "timeout" in outcome.message:
        say("Does your program open a window? Give it a flag without one "
            "(e.g. --no-gui) and add it to the command.", "warn")
    elif "no solution" in outcome.message:
        say("No turn lines ('D1-zone ...') found where flyin looked. Check "
            "where your program puts the solution (setup question 3).",
            "warn")
    say("Saved anyway; change it under Settings or with 'flyin setup'.",
        "dim")


def need_config(interactive: bool = True) -> Config:
    """Return the settings, running the setup the first time.

    Without a terminal to ask questions (scripts, CI) it stops with a
    hint instead of waiting for input.
    """
    current = config.load()
    if current is not None:
        return current
    if not interactive:
        say("flyin is not set up in this folder yet. Run 'flyin' (menu) or "
            "'flyin setup PROJECT --cmd \"python3 main.py {map}\"'.", "bad")
        raise SystemExit(2)
    say("First start: let's connect your project.\n", "bold")
    created = setup()
    if created is None:
        raise SystemExit(2)
    return created


# actions ----------------------------------------------------------------

def do_test(cfg: Config, only: list[str] | None = None,
            verbose: bool = False, strict: bool = False) -> list[Outcome]:
    """Test the maps, print the results and remember them."""
    count = len([c for c in api.maps() if c.group in DEFAULT_GROUPS]) \
        if not only else \
        len({c.name for q in only for c in api.maps(q)})
    if count == 0:
        say(f"no map matches {' '.join(only or [])}", "bad")
        return []
    say(f"Testing {count} maps with: {cfg.command}", "dim")
    outcomes = api.test(cfg.command, cfg.project, only or None,
                        cfg.timeout, cfg.jobs, strict, cfg.output_file)
    print_outcomes(outcomes, sys.stdout.isatty(), verbose)
    runs = config.history()
    config.save_run(outcomes)
    if runs:
        print_changes(runs[-1], outcomes)
    problems = sum(1 for o in outcomes if o.status != PASS
                   and o.case.expect == "solve")
    if problems:
        say(f"Watch them: flyin show --problems ({problems} maps)", "dim")
    return outcomes


def do_show(cfg: Config | None, ref: str, output: str | None = None,
            theme: str | None = None, screenshot: str | None = None,
            turn: int | None = None) -> bool:
    """Watch your program on a map, or an output file."""
    try:
        path = api.find_map(ref)
    except LookupError as error:
        say(str(error), "bad")
        return False
    theme = theme or (cfg.theme if cfg else "mission")
    if output is not None:
        text = sys.stdin.read() if output == "-" else \
            api.output_text(Path(output))
    else:
        if cfg is None:
            cfg = need_config(sys.stdin.isatty())
        say(f"Running: {cfg.command.replace('{map}', path.name)}", "dim")
        outcome = api.run(path, cfg.command, cfg.project, cfg.timeout,
                          cfg.output_file)
        say(f"{outcome.status}: {outcome.message}",
            {PASS: "ok", WARN: "warn", FAIL: "bad"}[outcome.status])
        text = outcome.output
    return api.show(path, text, theme, screenshot, turn)


RANK = {FAIL: 0, WARN: 1, PASS: 2}


def changes(before: dict[str, Any], outcomes: list[Outcome]
            ) -> tuple[list[str], list[str]]:
    """Return (better, worse) lines compared with an earlier run."""
    better: list[str] = []
    worse: list[str] = []
    old = before.get("results", {})
    for outcome in outcomes:
        if outcome.case.name not in old:
            continue
        status, turns = old[outcome.case.name]
        was = f"{status} {turns or ''}".strip()
        now = f"{outcome.status} {outcome.turns or ''}".strip()
        if was == now:
            continue
        line = f"{outcome.case.name}: {was} -> {now}"
        rank, new_rank = RANK.get(status, 0), RANK[outcome.status]
        if new_rank != rank:
            (better if new_rank > rank else worse).append(line)
        elif turns and outcome.turns:
            (better if outcome.turns < turns else worse).append(line)
    return better, worse


def print_changes(before: dict[str, Any], outcomes: list[Outcome]) -> None:
    """Print what got better or worse since the previous run."""
    better, worse = changes(before, outcomes)
    if not better and not worse:
        say(f"Same results as the run of {before.get('time', '?')}.", "dim")
        return
    say(f"\nSince the run of {before.get('time', '?')}: {len(better)} "
        f"better, {len(worse)} worse", "bold")
    for line in better[:10]:
        say(f"  better  {line}", "ok")
    for line in worse[:10]:
        say(f"  worse   {line}", "bad")
    if len(better) > 10 or len(worse) > 10:
        say("  (only the first 10 of each)", "dim")
    if worse:
        say("Watch old and new side by side: flyin compare MAP previous "
            "last", "dim")


SOURCES = ("now", "last", "previous")


def solution_text(cfg: Config | None, path: Path, source: str
                  ) -> tuple[str, str] | None:
    """Return (label, output) for a compare side, or None with a message.

    ``source``: ``now`` runs your program, ``last``/``previous`` are the
    outputs of the last test run and the one before, ``-`` is stdin,
    anything else a file.
    """
    if source == "now":
        cfg = cfg or need_config(sys.stdin.isatty())
        outcome = api.run(path, cfg.command, cfg.project, cfg.timeout,
                          cfg.output_file)
        return "now", outcome.output
    if source in ("last", "previous"):
        saved = config.saved_output(api.case_for(path).name, source)
        if saved is None:
            say(f"no '{source}' output for {path.name}: test it "
                f"{'once' if source == 'last' else 'twice'} first", "bad")
            return None
        return f"{source} test", api.output_text(saved)
    if source == "-":
        return "stdin", sys.stdin.read()
    file = Path(source)
    if not file.is_file():
        say(f"'{source}' is neither a file nor one of {', '.join(SOURCES)}",
            "bad")
        return None
    return file.name, api.output_text(file)


def do_compare(cfg: Config | None, ref: str, left: str, right: str,
               theme: str | None = None, screenshot: str | None = None,
               turn: int | None = None) -> int:
    """Play two solutions of one map side by side."""
    try:
        path = api.find_map(ref)
    except LookupError as error:
        say(str(error), "bad")
        return 2
    sides = []
    for source in (left, right):
        side = solution_text(cfg, path, source)
        if side is None:
            return 2
        sides.append(side)
    labels = (sides[0][0], sides[1][0])
    if labels[0] == labels[1]:
        labels = (f"A: {labels[0]}", f"B: {labels[1]}")
    valid = api.compare(path, sides[0][1], sides[1][1], labels,
                        theme or (cfg.theme if cfg else "mission"),
                        screenshot, turn)
    return 0 if valid else 1


def do_eval(cfg: Config, out: str = "flyin-report.md") -> int:
    """Run every standard map and write the evaluation report."""
    from flyin import report
    outcomes = do_test(cfg)
    if not outcomes:
        return 2
    path = Path(out)
    path.write_text(report.build(outcomes, cfg.project, cfg.command),
                    "utf-8")
    say("\nChecklist:", "bold")
    for ok, requirement, details in report.checklist(outcomes):
        say(f"  {report.MARK[ok]} {requirement}: {details}",
            "ok" if ok else "bad")
    say(f"Report written to {path.resolve()}", "dim")
    return 1 if any(o.status == FAIL for o in outcomes) else 0


def do_rules() -> None:
    """Print how flyin reads the subject."""
    print((Path(__file__).parent / "RULES.md").read_text("utf-8"))


def do_history() -> None:
    """Print one line per remembered run."""
    runs = config.history()
    if not runs:
        say("No test runs yet.", "dim")
        return
    for run in runs[-20:]:
        results = list(run["results"].values())
        counts = {s: sum(1 for r in results if r[0] == s)
                  for s in (PASS, WARN, FAIL)}
        turns = sum(r[1] or 0 for r in results)
        print(f"  {run.get('time', '?'):<17} {len(results):>4} maps  "
              f"{counts[PASS]:>4} pass {counts[WARN]:>4} warn "
              f"{counts[FAIL]:>4} fail   {turns:>6} turns")


def problems() -> list[dict[str, Any]]:
    """Return the solvable maps of the last test that were not PASS."""
    return [r for r in config.last_run()
            if r.get("expect") == "solve" and r.get("status") != PASS
            and r.get("output")]


def do_show_problems(cfg: Config | None) -> None:
    """Watch every problem map of the last test, one after another."""
    todo = problems()
    if not todo:
        say("No problems in the last test (or no test yet).", "ok")
        return
    for number, record in enumerate(todo, 1):
        say(f"\n[{number}/{len(todo)}] {record['map']}: {record['status']} "
            f"{record['message']}", "bold")
        say("Close the window (Esc) for the next one.", "dim")
        api.show(record["map"], Path(record["output"]),
                 cfg.theme if cfg else "mission")


def do_maps(query: str | None = None) -> None:
    """Print the maps with their group and target."""
    for case in api.maps(query):
        extra = f"target <= {case.target}" if case.target else \
            ("must be rejected" if case.expect == "error" else "")
        print(f"  {case.group:<17} {case.name:<52} {extra}")


def do_generate(seed: int | None, size: str, drones: int,
                out: str | None) -> int:
    """Write a random solvable map and say how to use it."""
    seed = random.randrange(1_000_000) if seed is None else seed
    try:
        width, height = (int(n) for n in size.lower().split("x"))
        text = generate(seed, width, height, drones)
    except ValueError as error:
        say(f"cannot generate: {error}", "bad")
        return 2
    path = Path(out or f"maps-generated/seed_{seed}.txt")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, "utf-8")
    say(f"wrote {path} ({text.splitlines()[1].lstrip('# ')})", "ok")
    say(f"watch your program on it: flyin show {path}", "dim")
    return 0


# command line -------------------------------------------------------------

def build_parser() -> argparse.ArgumentParser:
    """Build the parser of the short commands."""
    parser = argparse.ArgumentParser(
        prog="flyin", description="Test your Fly-In algorithm and watch it. "
        "Without a command: interactive menu.",
        epilog="Full tester options: flyin run --help")
    sub = parser.add_subparsers(dest="command")
    setup_p = sub.add_parser("setup", help="connect your project")
    setup_p.add_argument("project", nargs="?")
    setup_p.add_argument("--cmd", help="command for one map ({map}; "
                         "{out} if it takes an output file)")
    setup_p.add_argument("--output-file", help="the file your program "
                         "always writes, if it does not print the turns")
    test_p = sub.add_parser("test", help="test all maps, a group or a few")
    test_p.add_argument("what", nargs="*", help="group or part of a map "
                        "name (default: all)")
    test_p.add_argument("-v", "--verbose", action="store_true",
                        help="show every map, not only problems")
    test_p.add_argument("--strict", action="store_true",
                        help="turns above the target fail")
    test_p.add_argument("--show", action="store_true",
                        help="afterwards, watch the problem maps")
    show_p = sub.add_parser("show", help="watch a map in the visualizer")
    show_p.add_argument("map", nargs="?", help="map file or short name, "
                        "e.g. easy/01")
    show_p.add_argument("output", nargs="?", help="output file or - "
                        "(default: run your program)")
    show_p.add_argument("--problems", action="store_true",
                        help="watch the problem maps of the last test")
    show_p.add_argument("--theme", choices=THEMES)
    show_p.add_argument("--screenshot", metavar="PNG")
    show_p.add_argument("--turn", type=int)
    cmp_p = sub.add_parser("compare", help="two solutions side by side")
    cmp_p.add_argument("map")
    cmp_p.add_argument("left", nargs="?", default="last",
                       help="now | last | previous | FILE (default: last)")
    cmp_p.add_argument("right", nargs="?", default="now",
                       help="now | last | previous | FILE (default: now)")
    cmp_p.add_argument("--theme", choices=THEMES)
    cmp_p.add_argument("--screenshot", metavar="PNG")
    cmp_p.add_argument("--turn", type=int)
    sub.add_parser("history", help="results of the earlier test runs")
    eval_p = sub.add_parser("eval", help="evaluation report of all maps")
    eval_p.add_argument("-o", "--out", default="flyin-report.md")
    sub.add_parser("rules", help="how flyin reads the subject")
    maps_p = sub.add_parser("maps", help="list the maps")
    maps_p.add_argument("what", nargs="?")
    gen_p = sub.add_parser("generate", help="write a random solvable map")
    gen_p.add_argument("--seed", type=int, help="same seed, same map "
                       "(default: random)")
    gen_p.add_argument("--size", default="6x3", help="WIDTHxHEIGHT")
    gen_p.add_argument("--drones", type=int, default=10)
    gen_p.add_argument("-o", "--out", help="file (default: "
                       "maps-generated/seed_<seed>.txt)")
    sub.add_parser("check", help="check an output: flyin check MAP OUTPUT")
    sub.add_parser("run", help="the full tester with every option")
    return parser


def main(argv: list[str] | None = None) -> int:
    """Entry point of ``flyin``."""
    argv = sys.argv[1:] if argv is None else argv
    if argv and argv[0] in ("run", "view", "list", "check"):
        if argv[0] in ("view", "check") and len(argv) > 1:
            try:
                argv = [argv[0], str(api.find_map(argv[1])), *argv[2:]]
            except LookupError:
                pass
        return tester_main(argv)
    args = build_parser().parse_args(argv)
    try:
        return _dispatch(args)
    except KeyboardInterrupt:
        print()
        return 130


def _dispatch(args: argparse.Namespace) -> int:
    """Run one short command (or the menu)."""
    if args.command is None:
        from flyin.menu import Menu
        return Menu().run()
    if args.command == "setup":
        cmd = args.cmd
        return 0 if setup(args.project, cmd, cmd is None,
                          args.output_file) else 2
    if args.command == "test":
        outcomes = do_test(need_config(sys.stdin.isatty()), args.what,
                           args.verbose,
                           args.strict)
        if args.show:
            do_show_problems(config.load())
        return 1 if any(o.status == FAIL for o in outcomes) else 0
    if args.command == "show":
        if args.problems:
            do_show_problems(config.load())
            return 0
        if not args.map:
            say("which map? e.g. flyin show easy/01  (list: flyin maps)",
                "bad")
            return 2
        return 0 if do_show(config.load(), args.map, args.output,
                            args.theme, args.screenshot, args.turn) else 1
    if args.command == "compare":
        return do_compare(config.load(), args.map, args.left, args.right,
                          args.theme, args.screenshot, args.turn)
    if args.command == "eval":
        return do_eval(need_config(sys.stdin.isatty()), args.out)
    if args.command == "rules":
        do_rules()
        return 0
    if args.command == "history":
        do_history()
        return 0
    if args.command == "generate":
        return do_generate(args.seed, args.size, args.drones, args.out)
    do_maps(args.what)
    return 0
