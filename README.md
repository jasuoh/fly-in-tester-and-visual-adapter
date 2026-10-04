# flyin: Fly-In tester & visualizer

Test your **42 Fly-In** algorithm on 130 maps and **watch it fly**.

![The visualizer](docs/screenshot.png)

## Start

```sh
git clone https://github.com/jasuoh/fly-in-tester-and-visual-adapter.git flyin
cd flyin
make            # or: make run, or: python3 start.py
```

The first start offers to install the visualizer (pygame-ce, into
`.venv/`) and then asks three things:

1. **Where is your Fly-In project?** (the folder)
2. **How is it started for one map?** It guesses the command:
   `python3 main.py {map}`, `./fly_in {map}`, `python3 -m pkg {map}`, ...
3. **Where does it put the solution?** In the terminal, in a file whose
   name it gets as an argument (`{out}`), or always in the same file
   (e.g. `output.txt`).

It tries your program on one map and tells you if something is off. Then
the menu:

```
What do you want to do?
   1  Test all maps
   2  Test one group
   3  Watch a map (your program in the visualizer)
   4  Watch the problems of the last test  (3)
   5  Watch an output file
   6  List the maps
   7  Settings
   0  quit
```

**Watch a map** runs your program on the maps you pick and plays each one
in the visualizer: one number, several (`1,3,5`), a range (`2-6`) or
`all`; close the window for the next one. Your answers are saved in
`.flyin/` and can be changed under Settings.

That is all you need. The rest of this page is reference.

## Watching your algorithm

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
| mouse | drag the timeline, hover a zone for details |
| `Esc` | close (with "problems": on to the next map) |

No display (SSH, a server)? Save a picture instead:
`python3 start.py show easy/01 --screenshot frame.png --turn 3`.

## Without the menu

Every menu entry is also a command (`python3 start.py ...`, or `flyin ...`
after `pip install`, or `make ...`):

| Command | |
| --- | --- |
| `setup [PROJECT] [--cmd "..."] [--output-file FILE]` | connect your project |
| `test [WHAT ...] [-v] [--strict] [--show]` | all maps, a group (`challenge`) or part of a name (`hard`); `-v` lists every map, not only problems |
| `show MAP` | run your program on a map and watch it |
| `show MAP OUTPUT` | watch an output file (`-` = stdin) |
| `show --problems` | watch every map of the last test that failed or missed its target |
| `maps [WHAT]` | list the maps with their targets |
| `check MAP OUTPUT` | check an output without watching |
| `run --cmd "..." [options]` | the full tester for scripts and CI (`run --help`) |

`MAP` is a file or a short name of a bundled map: `easy/01`,
`city_grid`, `hard/03`.

## As a library

```sh
pip install git+https://github.com/jasuoh/fly-in-tester-and-visual-adapter
pip install pygame-ce        # only for flyin.show
```

```python
import flyin

turns = my_solver("maps/easy.txt")       # your code: one string per turn

result = flyin.check("easy/01", turns)   # every rule of the subject
print(result.valid, result.turns, result.errors)

flyin.show("easy/01", turns)             # opens the visualizer
flyin.show("easy/01", turns, screenshot="turn3.png", turn=3)

outcomes = flyin.test("python3 main.py {map}", cwd=".", only="challenge")
for o in outcomes:
    print(o.status, o.case.name, o.message)
```

| Function | Returns |
| --- | --- |
| `check(map, output)` | `CheckResult`: `.valid`, `.errors`, `.turns`, `.moves` |
| `show(map, output, theme=, screenshot=, turn=)` | `True` if valid; opens the window |
| `run(map, command, cwd=)` | `Outcome` of one map (`.status`, `.message`, `.output`) |
| `test(command, cwd=, only=, timeout=, jobs=, strict_targets=)` | list of `Outcome` |
| `maps(query=None)` / `find_map(name)` / `load_map(name)` | bundled maps |

`output` is text, a list of turn lines, or a `Path`. A full example:
`examples/use_as_library.py`.

## What your program must do

1. take the map path as an argument (or on stdin with `--shell`);
2. for a solvable map give one line per turn (`D1-roof1 D2-corridorA`) in
   the terminal or in a file, and exit with **0**;
3. for a broken or unsolvable map print an error naming the line to
   stderr and exit with **non-zero**;
4. never open a window and never crash with a traceback.

If your program always opens a window, give it a flag like `--no-gui` and
put that in the command, or copy `adapters/template.py` (three lines to
fill in). Any language works: flyin only runs a command.

<details>
<summary><b>How a map is judged and what the checker verifies</b></summary>

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

</details>

## The maps

| Group | Maps | |
| --- | --- | --- |
| `provided` | 28 | the maps of the subject with their "≤ N turns" targets |
| `provided-invalid` | 10 | their broken maps (must be rejected) |
| `edge-valid` | 29 | comments, CRLF, negative coordinates, 10 000 drones, restricted chains, ... |
| `edge-invalid` | 58 | every parser rule broken once, plus maps without a solution |
| `challenge` | 5 | hard maps whose target is the **exact optimum** (integer linear program); optional |

Your own map: `python3 start.py show path/to/map.txt` works with any file.

## Development

```sh
make dev-test    # 80+ tests: checker, map reader, runner, replay, GUI (headless), menu commands
make lint        # flake8 + mypy --strict
```

```
start.py         starts flyin from this folder (uses .venv/ if present)
flyin/           api.py      the library (check, show, run, test, maps)
                 app.py      the flyin command        menu.py   the menu
                 config.py   settings + last results in .flyin/ of the current folder
                 tester/     map reader, checker, runner, full command line
                 visual/     replay.py (any output -> playable), the pygame GUI
                 maps/       the 130 maps and manifest.json
examples/        naive_solver.py, use_as_library.py
adapters/        template.py
tests/
```

The visualizer comes from [42-fly-in-claude](https://github.com/jasuoh/42-fly-in-claude),
the tester from [fly-in-tests](https://github.com/jasuoh/fly-in-tests). Fonts:
SIL Open Font License (`flyin/visual/assets/fonts/OFL-*.txt`).
