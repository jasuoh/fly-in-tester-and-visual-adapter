"""The ``flyin`` command: the menu, plus short commands for every action.

    flyin                       interactive menu
    flyin setup [PROJECT]       tell flyin how to run your project
    flyin test [WHAT ...]       test all maps, a group or some maps
    flyin show MAP [OUTPUT]     watch your program (or an output file)
    flyin show --problems       watch every map of the last test that
                                failed or missed its target
    flyin maps [WHAT]           list the maps
    flyin check MAP OUTPUT      check an output file

``flyin run|view|list`` keep every option of the full tester
(:mod:`flyin.tester.cli`), for scripts and CI.
"""

import argparse
import sys
from pathlib import Path

from flyin import api, config
from flyin.config import Config
from flyin.tester.cli import main as tester_main, print_outcomes
from flyin.tester.runner import FAIL, PASS, WARN, Outcome

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


def need_config() -> Config:
    """Return the settings, running the setup the first time."""
    current = config.load()
    if current is not None:
        return current
    say("First start: let's connect your project.\n", "bold")
    created = setup()
    if created is None:
        raise SystemExit(2)
    return created


# actions ----------------------------------------------------------------

def do_test(cfg: Config, only: list[str] | None = None,
            verbose: bool = False, strict: bool = False) -> list[Outcome]:
    """Test the maps, print the results and remember them."""
    count = len(api.maps()) if not only else \
        len({c.name for q in only for c in api.maps(q)})
    if count == 0:
        say(f"no map matches {' '.join(only or [])}", "bad")
        return []
    say(f"Testing {count} maps with: {cfg.command}", "dim")
    outcomes = api.test(cfg.command, cfg.project, only or None,
                        cfg.timeout, cfg.jobs, strict, cfg.output_file)
    print_outcomes(outcomes, sys.stdout.isatty(), verbose)
    config.save_run(outcomes)
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
            cfg = need_config()
        say(f"Running: {cfg.command.replace('{map}', path.name)}", "dim")
        outcome = api.run(path, cfg.command, cfg.project, cfg.timeout,
                          cfg.output_file)
        say(f"{outcome.status}: {outcome.message}",
            {PASS: "ok", WARN: "warn", FAIL: "bad"}[outcome.status])
        text = outcome.output
    return api.show(path, text, theme, screenshot, turn)


def problems() -> list[dict[str, str]]:
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
    maps_p = sub.add_parser("maps", help="list the maps")
    maps_p.add_argument("what", nargs="?")
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
        outcomes = do_test(need_config(), args.what, args.verbose,
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
    do_maps(args.what)
    return 0
