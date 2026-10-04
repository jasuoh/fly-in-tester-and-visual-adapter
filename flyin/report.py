"""``flyin eval``: one report with everything an evaluation looks at.

Runs every standard map and writes a Markdown file: a checklist of the
subject's requirements, the results per group, the score, the slowest
maps and every problem with its reason.
"""

import time
from collections import Counter
from pathlib import Path

from flyin.tester.cli import score_line
from flyin.tester.runner import FAIL, PASS, WARN, Outcome

MARK = {True: "✅", False: "❌"}


def _problems(outcomes: list[Outcome], *words: str) -> list[Outcome]:
    """Return the failed outcomes whose message contains one of
    ``words``."""
    return [o for o in outcomes if o.status == FAIL
            and any(w in o.message for w in words)]


def checklist(outcomes: list[Outcome]) -> list[tuple[bool, str, str]]:
    """Return (ok, requirement, detail) rows."""
    def failed(groups: tuple[str, ...]) -> list[Outcome]:
        return [o for o in outcomes if o.case.group in groups
                and o.status == FAIL and o.case.level == "required"]

    solve = failed(("provided", "edge-valid"))
    reject = failed(("provided-invalid", "edge-invalid"))
    crashes = _problems(outcomes, "traceback", "crashed")
    timeouts = _problems(outcomes, "timeout")
    targets = [o for o in outcomes if o.case.group == "provided"
               and o.case.target and not o.case.optional_target
               and (o.turns is None or o.turns > o.case.target)]
    lines = _problems(outcomes, "does not name line")

    def detail(items: list[Outcome]) -> str:
        names = ", ".join(Path(o.case.name).stem for o in items[:4])
        more = f" (+{len(items) - 4})" if len(items) > 4 else ""
        return f"{len(items)}: {names}{more}" if items else "all good"

    return [
        (not solve, "Valid maps are solved with a valid output",
         detail(solve)),
        (not reject, "Broken and unsolvable maps are rejected",
         detail(reject)),
        (not lines, "Parse errors name the line of the mistake",
         detail(lines)),
        (not crashes, "No crash, no traceback", detail(crashes)),
        (not timeouts, "No timeout", detail(timeouts)),
        (not targets, "Turn targets of the subject are met",
         detail(targets)),
    ]


def build(outcomes: list[Outcome], project: str, command: str) -> str:
    """Return the report as Markdown."""
    out = ["# Fly-In evaluation report", "",
           f"- Date: {time.strftime('%Y-%m-%d %H:%M')}",
           f"- Project: `{project}`", f"- Command: `{command}`",
           f"- Maps: {len(outcomes)}", "", "## Checklist", "",
           "| | Requirement | Details |", "| --- | --- | --- |"]
    for ok, requirement, details in checklist(outcomes):
        out.append(f"| {MARK[ok]} | {requirement} | {details} |")
    out += ["", "## Results per group", "",
            "| Group | Maps | Pass | Warn | Fail |",
            "| --- | ---: | ---: | ---: | ---: |"]
    groups: dict[str, list[Outcome]] = {}
    for outcome in outcomes:
        groups.setdefault(outcome.case.group, []).append(outcome)
    for group, members in groups.items():
        counts = Counter(o.status for o in members)
        out.append(f"| {group} | {len(members)} | {counts[PASS]} | "
                   f"{counts[WARN]} | {counts[FAIL]} |")
    score = score_line(outcomes)
    if score:
        out += ["", "## Score", "", score]
    targets = [o for o in outcomes if o.case.target and o.turns]
    if targets:
        out += ["", "## Turns against the targets", "",
                "| Map | Turns | Target | Optimum / bound |",
                "| --- | ---: | ---: | ---: |"]
        for o in targets:
            out.append(f"| {o.case.name} | {o.turns} | {o.case.target} | "
                       f"{o.best or '-'} |")
    slow = sorted(outcomes, key=lambda o: o.seconds, reverse=True)[:5]
    out += ["", "## Slowest maps", "", "| Map | Seconds |",
            "| --- | ---: |"]
    out += [f"| {o.case.name} | {o.seconds:.2f} |" for o in slow]
    problems = [o for o in outcomes if o.status != PASS]
    out += ["", "## Every problem", ""]
    if not problems:
        out.append("None.")
    for o in problems:
        out.append(f"- **{o.status}** `{o.case.name}`: {o.message}")
        out += [f"  - {d}" for d in o.details[:3]]
    return "\n".join(out) + "\n"
