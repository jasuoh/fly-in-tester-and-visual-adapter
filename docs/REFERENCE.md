# flyin reference

Everything in detail; the [README](../README.md) has the short version.

## The visualizer

The visualizer plays **whatever your program prints**:

- drone ids from `D0` or `D1`, debug prints and banners around the turns
  are fine;
- **invalid solutions are shown too**, so you can watch the mistake: an
  overfull zone shows `3/2`, the title says `INVALID` and the terminal
  lists every broken rule with its turn;
- only what cannot be drawn at all (an unknown zone, a drone moving twice
  in one turn) is left out and listed.

| Key | |
| --- | --- |
| `Space` | play / pause |
| `←` `→` | one turn back / forward |
| `+` `-` | speed |
| `R` | restart |
| `T` | theme: `mission`, `blueprint`, `graphite`, `ashen` |
| `E` | jump to the next broken rule (invalid solutions) |
| mouse | drag the timeline, hover a zone for details |
| `Esc` | close (with "problems": on to the next map) |

No display (SSH, a server)? Save a picture instead:
`python3 start.py show easy/01 --screenshot frame.png --turn 3`.

## Commands

Every menu entry is also a command (`python3 start.py ...`, or `flyin ...`
after `pip install`, or `make ...`):

| Command | |
| --- | --- |
| `setup [PROJECT] [--cmd "..."] [--output-file FILE]` | connect your project |
| `test [WHAT ...] [-v] [--strict] [--show]` | all maps, a group (`challenge`, `fuzz`) or part of a name (`hard`); `-v` lists every map, not only problems |
| `show MAP` | run your program on a map and watch it |
| `show MAP OUTPUT` | watch an output file (`-` = stdin) |
| `show --problems` | watch every map of the last test that failed or missed its target |
| `compare MAP [A] [B]` | two solutions side by side; `now`, `last`, `previous` or a file (default `last now`) |
| `eval [-o FILE]` | evaluation report (`flyin-report.md`) |
| `history` | results of all earlier test runs |
| `generate [--seed N] [--size 8x4] [--drones N] [--shape grid\|random]` | a random solvable map in `maps-generated/` |
| `rules` | how flyin reads the subject |
| `maps [WHAT]` | list the maps with their targets |
| `check MAP OUTPUT` | check an output without watching |
| `run --cmd "..." [options]` | the full tester for scripts and CI (`run --help`) |

`MAP` is a file or a short name of a bundled map: `easy/01`,
`city_grid`, `hard/03`.

## Library

| Function | Returns |
| --- | --- |
| `check(map, output)` | `CheckResult`: `.valid`, `.errors`, `.turns`, `.moves` |
| `show(map, output, theme=, screenshot=, turn=)` | `True` if valid; opens the window |
| `compare(map, left, right, labels=, theme=, screenshot=, turn=)` | `True` if both valid; side by side |
| `run(map, command, cwd=)` | `Outcome` of one map (`.status`, `.message`, `.output`) |
| `test(command, cwd=, only=, timeout=, jobs=, strict_targets=)` | list of `Outcome` |
| `maps(query=None)` / `find_map(name)` / `load_map(name)` | bundled maps |

`output` is text, a list of turn lines, or a `Path`. A full example:
`examples/use_as_library.py`.

## How a map is judged

Details and the reasons: [RULES.md](../flyin/RULES.md).

| Map kind | Expected | Result |
| --- | --- | --- |
| **valid** | exit 0, no traceback, a solution the checker accepts | `PASS`; `WARN` above the target or ignoring a priority zone; else `FAIL` |
| **invalid** | exit ≠ 0, no traceback, a message naming the line, **no** solution | `PASS`, else `FAIL` |

`recommended` maps are debatable readings of the subject (tabs, a comment
after a definition, ...): a deviation is only a `WARN`.

A token is `D<id>-<zone>` or, for the two-turn flight into a restricted
zone, `D<id>-<from>-<to>`. A solution fails when:

- a drone acts twice in a turn, or a token is malformed;
- ids are not `D0..D(n-1)` or `D1..Dn`;
- a move uses a missing connection, enters a **blocked** zone, or enters a
  **restricted** zone without the flight notation;
- a drone in flight does not land in the **next** turn;
- a zone holds more than `max_drones` at the end of a turn (start and end
  are unlimited; leaving frees the place in the same turn);
- a connection carries more than `max_link_capacity` drones in a turn;
- a delivered drone moves again, a turn line is empty, or a drone never
  reaches the end.

## The maps

| Group | Maps | |
| --- | --- | --- |
| `provided` | 28 | the maps of the subject with their "≤ N turns" targets |
| `provided-invalid` | 10 | their broken maps (must be rejected) |
| `edge-valid` | 29 | comments, CRLF, negative coordinates, 10 000 drones, restricted chains, ... |
| `edge-invalid` | 58 | every parser rule broken once, plus maps without a solution |
| `challenge` | 5 | hard maps whose target is the **exact optimum** (integer linear program); optional |
| `fuzz` | 300 | seeded random maps with their exact optimum; only when asked for (`flyin test fuzz`) |

Your own map: `python3 start.py show path/to/map.txt` works with any file.

## Development

```sh
make dev-test    # ~100 tests: checker, bounds, runner, replay, GUI (headless), commands
make lint        # flake8 + mypy --strict
```

```
start.py         starts flyin from this folder (uses .venv/ if present)
flyin/           api.py      the library (check, show, run, test, maps)
                 app.py      the flyin command        menu.py   the menu
                 config.py   settings, last results, history in .flyin/
                 report.py   the evaluation report
                 RULES.md    how the subject is read
                 tester/     map reader, checker, lower bounds, map generator,
                             runner, full command line
                 visual/     replay.py (any output -> playable), the pygame GUI
                 maps/       the 430 maps and manifest.json
examples/        naive_solver.py, use_as_library.py
adapters/        template.py
tests/
```
