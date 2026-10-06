"""Command line interface: ``python -m flyin.tester``."""

import argparse
import json
import shutil
import sys
from collections import Counter
from pathlib import Path

from .checker import check_solution
from .mapfile import MapError, read_map
from .runner import (
    DEFAULT_GROUPS, FAIL, MAPS_DIR, PASS, WARN, Case, Outcome, Runner,
    extract_turns,
    load_manifest,
)

COLORS = {PASS: "\033[32m", WARN: "\033[33m", FAIL: "\033[31m"}


def _select(cases: list[Case], args: argparse.Namespace) -> list[Case]:
    """Apply the --group and --filter options (fuzz only on request)."""
    if args.group:
        cases = [c for c in cases if c.group in args.group]
    elif not args.filter or "fuzz" not in args.filter:
        cases = [c for c in cases if c.group in DEFAULT_GROUPS]
    if args.filter:
        cases = [c for c in cases if args.filter in c.name]
    return cases


def _print_outcome(outcome: Outcome, color: bool, verbose: bool) -> None:
    """Print one result line (and details for failures or with -v)."""
    tag = outcome.status
    if color:
        tag = f"{COLORS[tag]}{tag}\033[0m"
    time_text = f"{outcome.seconds:5.1f}s"
    best = ""
    if outcome.turns and outcome.best and outcome.status != FAIL:
        label = "optimum" if outcome.case.optimum else "bound"
        best = f"  [{label} {outcome.best}]" if outcome.turns > \
            outcome.best else f"  [= {label}]"
    message = outcome.message
    if not verbose:
        room = shutil.get_terminal_size().columns - 72 - len(best)
        if len(message) > max(30, room):
            message = message[:max(29, room - 1)] + "…"
    print(f"  {tag:>4}  {outcome.case.name:<52} {time_text}  "
          f"{message}{best}")
    if verbose or outcome.status == FAIL:
        for detail in outcome.details:
            print(f"          | {detail}")


def print_outcomes(outcomes: list[Outcome], color: bool = False,
                   verbose: bool = False) -> None:
    """Print the results per group: problems only, everything with -v."""
    groups: dict[str, list[Outcome]] = {}
    for outcome in outcomes:
        groups.setdefault(outcome.case.group, []).append(outcome)
    for group, members in groups.items():
        counts = Counter(o.status for o in members)
        print(f"\n[{group}] {counts[PASS]}/{len(members)} passed"
              + (f", {counts[WARN]} warnings" if counts[WARN] else "")
              + (f", {counts[FAIL]} failed" if counts[FAIL] else ""))
        for outcome in members:
            if verbose or outcome.status != PASS:
                _print_outcome(outcome, color, verbose)
    counts = Counter(o.status for o in outcomes)
    print(f"\n{len(outcomes)} maps: {counts[PASS]} passed, "
          f"{counts[WARN]} warnings, {counts[FAIL]} failed"
          + ("" if verbose else "   (-v shows every map)"))
    line = score_line(outcomes)
    if line:
        print(line)


def score_line(outcomes: list[Outcome]) -> str:
    """Summarise the valid solutions against the best possible per map
    (the exact optimum where known, else the lower bound).

    The gap is averaged per map, so a map with 10 000 drones counts as
    much as a map with 2.
    """
    scored = [o for o in outcomes if o.turns and o.best
              and o.status != FAIL]
    if not scored:
        return ""
    at_best = sum(1 for o in scored if o.turns == o.best)
    gaps = [100 * ((o.turns or 0) - (o.best or 0)) / (o.best or 1)
            for o in scored]
    worst = max(scored, key=lambda o: (o.turns or 0) - (o.best or 0))
    line = (f"Score: at the best possible on {at_best}/{len(scored)} "
            f"solved maps, on average +{sum(gaps) / len(gaps):.1f}% turns")
    if worst.turns != worst.best:
        line += (f"; most to win: {worst.case.name} ({worst.turns} vs "
                 f"{worst.best})")
    return line


def command_run(args: argparse.Namespace) -> int:
    """Run the program under test on the selected maps."""
    cases = _select(load_manifest(Path(args.maps_dir)), args)
    if not cases:
        print("no maps selected", file=sys.stderr)
        return 2
    runner = Runner(
        args.cmd, timeout=args.timeout, cwd=args.cwd, source=args.source,
        shell=args.shell, check_lines=not args.no_check_lines,
        strict_output=args.strict_output, strict_targets=args.strict_targets,
    )
    outcomes = runner.run_all(cases, jobs=args.jobs)
    if args.save_outputs:
        _save_outputs(outcomes, Path(args.save_outputs))
    if args.json:
        print(json.dumps([
            {"map": o.case.name, "group": o.case.group, "status": o.status,
             "message": o.message, "turns": o.turns, "best": o.best,
             "seconds": round(o.seconds, 2)} for o in outcomes
        ], indent=2))
    else:
        print_outcomes(outcomes, sys.stdout.isatty() and not args.no_color,
                       args.verbose)
    if args.view:
        _view_outcomes(outcomes, args)
    return 1 if any(o.status == FAIL for o in outcomes) else 0


def _save_outputs(outcomes: list[Outcome], directory: Path) -> None:
    """Write the output of every solvable map to ``directory/<map>``."""
    for outcome in outcomes:
        if outcome.case.expect != "solve":
            continue
        target = directory / outcome.case.name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(outcome.output, "utf-8")


def _view_outcomes(outcomes: list[Outcome], args: argparse.Namespace) -> None:
    """Open the visualizer for the solvable maps chosen by ``--view``."""
    from flyin.visual.view import headless, show
    wanted = {"fail": (FAIL,), "warn": (FAIL, WARN),
              "all": (FAIL, WARN, PASS)}[args.view]
    chosen = [o for o in outcomes if o.case.expect == "solve"
              and o.status in wanted and extract_turns(o.output)[0]]
    if not chosen:
        print("\nnothing to view")
        return
    if headless():
        print("\nno display: cannot open the visualizer "
              "(use --save-outputs and view --screenshot)")
        return
    for number, outcome in enumerate(chosen, 1):
        print(f"\n[view {number}/{len(chosen)}] {outcome.case.name} "
              f"({outcome.status}) - close the window (Esc) for the next")
        show(str(outcome.case.path), outcome.output, args.theme,
             title=f"{Path(outcome.case.name).stem} ({outcome.status})")


def command_check(args: argparse.Namespace) -> int:
    """Check an existing output (file or stdin) against a map."""
    try:
        fly_map = read_map(args.map)
    except (MapError, OSError) as error:
        print(f"cannot read map: {error}", file=sys.stderr)
        return 2
    text = sys.stdin.read() if args.output == "-" else \
        Path(args.output).read_text("utf-8", errors="replace")
    turns = text.splitlines() if args.raw else extract_turns(text)[0]
    result = check_solution(fly_map, turns)
    if result.valid:
        print(f"VALID solution: {result.turns} turns, {result.moves} moves "
              f"(drone ids start at {result.id_base})")
        return 0
    print(f"INVALID solution ({len(result.errors)} problems):")
    for problem in result.errors:
        print(f"  - {problem}")
    return 1


def command_list(args: argparse.Namespace) -> int:
    """List the maps of the manifest."""
    for case in _select(load_manifest(Path(args.maps_dir)), args):
        extra = f"target<={case.target}" if case.target else case.expect
        print(f"{case.group:<16} {case.name:<52} {extra}")
    return 0


def build_parser() -> argparse.ArgumentParser:
    """Build the argument parser."""
    parser = argparse.ArgumentParser(
        prog="flyin", description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)

    def common(p: argparse.ArgumentParser) -> None:
        p.add_argument("--maps-dir", default=str(MAPS_DIR))
        p.add_argument("--group", action="append",
                       help="only this group (repeatable)")
        p.add_argument("--filter", help="only maps whose path contains this")

    run = sub.add_parser("run", help="run a program on the maps")
    common(run)
    run.add_argument("--cmd", required=True,
                     help="command; {map} = map path, {out} = output file")
    run.add_argument("--cwd", help="working directory for the command")
    run.add_argument("--timeout", type=float, default=60.0)
    run.add_argument("--source", choices=("stdout", "file"), default="stdout")
    run.add_argument("--shell", action="store_true")
    run.add_argument("--jobs", type=int, default=1)
    run.add_argument("--no-check-lines", action="store_true")
    run.add_argument("--strict-output", action="store_true")
    run.add_argument("--strict-targets", action="store_true")
    run.add_argument("--no-color", action="store_true")
    run.add_argument("--json", action="store_true")
    run.add_argument("-v", "--verbose", action="store_true")
    run.add_argument("--save-outputs", metavar="DIR",
                     help="write each solvable map's output to DIR/<map>")
    run.add_argument("--view", choices=("fail", "warn", "all"),
                     help="afterwards, play these maps in the visualizer "
                     "(fail; warn = fail+warn; all)")
    run.add_argument("--theme", default="mission",
                     choices=("mission", "blueprint", "graphite", "ashen"),
                     help="visualizer theme for --view")
    run.set_defaults(func=command_run)

    check = sub.add_parser("check", help="check an output against a map")
    check.add_argument("map")
    check.add_argument("output", help="file with the output, or - for stdin")
    check.add_argument("--raw", action="store_true",
                       help="every line is a turn (no noise filtering)")
    check.set_defaults(func=command_check)

    listing = sub.add_parser("list", help="list the maps")
    common(listing)
    listing.set_defaults(func=command_list)

    from flyin.visual.view import add_view_parser
    add_view_parser(sub)
    return parser


def main(argv: list[str] | None = None) -> int:
    """Entry point."""
    args = build_parser().parse_args(argv)
    code: int = args.func(args)
    return code


if __name__ == "__main__":
    sys.exit(main())
