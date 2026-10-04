# fly-in-arena

Test your **42 Fly-In** algorithm and **watch it fly**.

The arena combines two things:

- **the tester** ([fly-in-tests](https://github.com/jasuoh/fly-in-tests)):
  runs your program on 130 maps and checks every solution with its own,
  independent rule checker;
- **the visualizer** from
  [42-fly-in-claude](https://github.com/jasuoh/42-fly-in-claude): the
  interactive pygame player, cut loose from that project's solver so it
  plays **any** program's output.

![The visualizer playing a solution](docs/screenshot.png)

Your project needs no changes and no imports from here. It only has to be
runnable as a command that prints the turns (`D1-roof1 D2-corridorA`, one
line per turn). Any language works.

## Quick start

```sh
git clone <this repo> fly-in-arena && cd fly-in-arena
make install            # .venv with pygame-ce (only the visualizer needs it)

# 1. test your program on every map
make run  PROJECT=../my-fly-in CMD="python3 main.py {map}"

# 2. watch it solve one map
make view PROJECT=../my-fly-in CMD="python3 main.py {map}" \
          MAP=maps/challenge/04_city_grid.txt

# 3. watch every map where it failed or missed the target, one after another
make view-fail PROJECT=../my-fly-in CMD="python3 main.py {map}"
```

`{map}` is replaced by the path of the map, `PROJECT` is the directory your
command runs in. No project yet? Leave `PROJECT` and `CMD` out: the arena
then uses `examples/naive_solver.py` (valid, but every drone flies alone).
Beat it.

Without `make`, the same commands are
`python3 -m fly_in_tester run|view|check|list ...`, run from this
directory (the tester needs no packages; the visualizer needs
`pip install pygame-ce`).

## The visualizer

```sh
python3 -m fly_in_tester view MAP --cmd "python3 main.py {map}" --cwd ../my-fly-in
python3 -m fly_in_tester view MAP my_output.txt
./my_fly_in MAP | python3 -m fly_in_tester view MAP -
```

It first prints the checker's verdict, then opens the window.

| Key | Action |
| --- | --- |
| `Space` | play / pause |
| `←` `→` | one turn back / forward |
| `+` `-` | speed |
| `R` | restart |
| `T` | next theme (`mission`, `blueprint`, `graphite`, `ashen`) |
| mouse | drag the timeline, hover a zone for its details |
| `Esc` / `Q` | close (with `--view`: on to the next map) |

What you see: zones in their map colours with their type (hatched with a
clock = restricted, star = priority, X = blocked), `occupied / max` rings
that light up when a zone is full, connections that glow when used, drones
gliding between zones (a restricted flight crosses its connection over two
turns), and a side panel with the turn, delivered drones, this turn's
output line, metrics and a moves-per-turn chart.

### Adaptive: it plays whatever your program prints

The original visualizer only ever saw a perfect solver. Here a small layer
(`fly_in_visual/replay.py`) sits between your output and the GUI:

- drone ids from `D0` or from `D1` are detected;
- banners, debug prints and other lines around the turns are ignored;
- **invalid solutions are shown anyway**, so you can watch the mistake
  happen: an overfull zone shows `3/2`, a jump over a missing connection is
  drawn, the panel title says `INVALID` and the terminal lists the
  checker's errors with their turn numbers;
- only tokens that cannot be drawn at all are left out and listed (unknown
  zone, unknown drone, a drone moving twice in one turn or after it was
  delivered).

The map is read by the tester's own reader, never by your program, so the
picture always shows the real map.

### No display (SSH, WSL without GUI, CI)

```sh
python3 -m fly_in_tester view MAP out.txt --screenshot turn12.png --turn 12
python3 -m fly_in_tester run --cmd "..." --save-outputs out/   # keep every output
```

`--save-outputs DIR` writes each solvable map's output to `DIR/<map path>`,
ready for `view` or `check`.

## The tester

```sh
python3 -m fly_in_tester run --cmd "python3 main.py {map}" --cwd ../my-project
```

| Option | Meaning |
| --- | --- |
| `--cwd DIR` | working directory of your program |
| `--timeout N` | seconds per map (default 60) |
| `--jobs N` | run N maps in parallel |
| `--group G` / `--filter TEXT` | only some maps (`provided`, `provided-invalid`, `edge-valid`, `edge-invalid`, `challenge`) |
| `--source file` or `{out}` in `--cmd` | read the solution from a file your program writes |
| `--strict-output` | fail if your program prints anything besides turn lines |
| `--strict-targets` | turns above the reference target become failures, not warnings |
| `--no-check-lines` | do not require the line number in error messages |
| `--shell` | run `--cmd` through the shell (pipes, `&&`, ...) |
| `--view fail\|warn\|all` | afterwards, play those maps in the visualizer |
| `--save-outputs DIR` | keep the output of every solvable map |
| `-v`, `--json`, `--no-color` | output control |

The exit status is `1` if any map **fails**, `0` otherwise (warnings do not
change it).

### What your program must do

1. take the map (as an argument, on stdin, or via `{map}`);
2. for a solvable map print the turns, one line per turn, to the terminal
   or to a file (`{out}`), and exit with status **0**;
3. for a broken or unsolvable map print a message (with the line number for
   parse errors) to stderr and exit with a status **other than 0**;
4. never open a window and never crash with a traceback.

| Project | `--cmd` |
| --- | --- |
| script, map as argument | `python3 main.py {map}` |
| package | `python3 -m fly_in {map}` |
| program with an option | `python3 main.py --map {map} --no-gui` |
| compiled program | `./fly_in {map}` |
| map on stdin (needs `--shell`) | `./fly_in < {map}` |
| solution written to a file | `python3 main.py {map} {out}` |

If your entry point always opens a window, copy `adapters/template.py`,
fill in three lines (your parser and simulation) and use the adapter as
`--cmd`. The tester sets `SDL_VIDEODRIVER=dummy` anyway.

### How a map is judged

| Map kind | Expected behaviour | Result |
| --- | --- | --- |
| **valid** (must be solved) | exit status 0, no traceback, and a solution the checker accepts | `PASS`; `WARN` if it uses more turns than the target or ignores a priority zone; otherwise `FAIL` |
| **invalid** (must be rejected) | non-zero exit status, no traceback, a message on stderr that names the line of the mistake, and **no** solution printed | `PASS`, else `FAIL` |

`required` maps must behave as described. `recommended` maps are debatable
readings of the subject (tabs between fields, a comment after a definition,
...): a deviation is only a `WARN`.

### What the checker verifies

Every line is one turn; a token is `D<id>-<zone>` or, for a two-turn flight
into a restricted zone, `D<id>-<from>-<to>`. A solution fails when:

- a drone acts twice in a turn, or a token is malformed;
- ids are not `D0..D(n-1)` or `D1..Dn`;
- a move uses a missing connection, enters a **blocked** zone, or enters a
  **restricted** zone without the flight notation;
- a drone in flight does not land in the **next** turn;
- a zone holds more than `max_drones` drones at the end of a turn (start and
  end are unlimited; a drone leaving frees its place in the same turn);
- a connection carries more than `max_link_capacity` drones in a turn;
- a delivered drone moves again, a turn line is empty, or not every drone
  ends in the end zone.

## The maps

`maps/manifest.json` describes every map (expected behaviour, target,
accepted error lines, level).

| Group | Maps | Content |
| --- | --- | --- |
| `provided` | 28 | the maps of the subject with their "≤ N turns" targets (challenger: 44, optional) |
| `provided-invalid` | 10 | the broken maps that come with them |
| `edge-valid` | 29 | comments, CRLF, negative coordinates, huge capacities, 100 and 10 000 drones, restricted chains, ... |
| `edge-invalid` | 58 | every parser rule broken one by one, plus maps without a solution |
| `challenge` | 5 | hard hand-made maps; the target is the **exact optimum**, computed with an integer linear program over the time-expanded graph (optional) |

The reference solver of 42-fly-in-claude reaches all five optima. To test a
map of your own, add the file below `maps/` and an entry to the manifest,
or just `view` it directly: `view` works with any map file.

## Development

```sh
make test     # 70+ tests: checker, map reader, runner, replay, GUI (headless)
make lint     # flake8 + mypy --strict
```

```
fly_in_tester/   mapfile.py   independent map reader
                 checker.py   solution checker
                 runner.py    runs your program, judges the result
                 __main__.py  command line: run, view, check, list
fly_in_visual/   loader.py    tester map -> GUI graph
                 replay.py    any output -> playable result (the adaptive layer)
                 cli.py       the view command
                 gui/         the pygame player from 42-fly-in-claude
                 assets/      Geist and Cinzel fonts (SIL Open Font License)
maps/            provided/, edge/, challenge/, manifest.json
examples/        naive_solver.py
adapters/        template.py
tests/           tests of the arena
```

The fonts are under the SIL Open Font License, see
`fly_in_visual/assets/fonts/OFL-*.txt`.
