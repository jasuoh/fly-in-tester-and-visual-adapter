# flyin: Fly-In tester & visualizer

Test your **42 Fly-In** algorithm on 130 maps (+300 with a known
optimum) and **watch it fly**.

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
   2  Watch maps (your program in the visualizer)
   3  Watch the problems of the last test  (3)
   4  Compare two solutions side by side
   5  Evaluation report (all maps + checklist)
   6  More ...    (one group, output file, history, random map, map list, rules)
   7  Settings
   0  quit
```

Your answers are saved in `.flyin/` and can be changed under Settings.

## What it does for you

- **Test**: every map is run and judged by an independent checker. Only
  problems are listed. Every solved map shows the exact optimum (where
  known) or a proven **lower bound**; the **score** says on how many maps
  you reach it, how far off you are on average and where the most turns
  can still be won.
- **Watch**: your program runs on the maps you pick (one, `1,3,5`, `2-6`
  or `all`) and each solution plays in the visualizer.
- **See the mistake**: an invalid solution opens paused on the first
  broken turn; the zones and connections involved pulse red, the panel
  names the rule, red dots on the timeline mark every broken turn and `E`
  jumps to the next one.
- **Compare**: two solutions of one map side by side, in sync: your last
  test against now, the one before against the last, or any files.
- **History**: after every test you see which maps got better or worse
  than in the run before (`flyin history` lists all runs).
- **Evaluation report**: one Markdown file with a checklist of the
  subject's requirements (solves, rejects, line numbers, no crash, no
  timeout, targets), results, score, slowest maps and every problem.
- **Random maps**: `flyin generate --seed 7` writes a solvable map with
  its lower bound; the same seed always gives the same map.
- **Rules**: [flyin/RULES.md](flyin/RULES.md) says how the open points of
  the subject are read (capacity when leaving, flights, link counting).

| An invalid solution: the broken rule is marked | Compare: the last test against the one before |
| --- | --- |
| ![invalid](docs/invalid.png) | ![compare](docs/compare.png) |

That is all you need. The rest of this page is reference.

## Your own visual part is not ready yet?

You do not need to build anything to watch your algorithm: it only has to
print the turn lines (`D1-roof1 D2-corridorA`, one turn per line). The
visualizer reads the map itself, so your data structures do not matter,
and it plays unfinished or wrong solutions too (the broken rule is marked
red, `E` jumps to the next one).

**No code at all**: use the menu (`make`, then *Watch maps*), or hand it
your output directly:

```sh
python3 main.py map.txt | python3 start.py show map.txt -
python3 start.py show map.txt my_output.txt
```

**From your own program**, e.g. a `--visual` flag while developing
(install once in your project's environment, see [As a library](#as-a-library)):

```python
import sys
import flyin

turns = my_algorithm(map_path)        # list of strings, one per turn
print("\n".join(turns))

if "--visual" in sys.argv:
    flyin.show(map_path, turns)       # opens the window
```

Without pip, put this repository next to your project and add it to the
path first: `sys.path.insert(0, "../flyin")`.

> **For the evaluation:** the subject asks for a visual representation of
> your own. Use flyin to debug your algorithm, not as the visual part you
> hand in: it would be someone else's code in your project.

## As a library

```sh
pip install git+https://github.com/jasuoh/fly-in-tester-and-visual-adapter
pip install pygame-ce        # only for flyin.show
```

```python
import flyin

map_path = flyin.find_map("easy/01")     # a short name or any map file
turns = my_solver(map_path)              # your code: one string per turn

result = flyin.check(map_path, turns)    # every rule of the subject
print(result.valid, result.turns, result.errors)

flyin.show(map_path, turns)              # opens the visualizer
flyin.show(map_path, turns, screenshot="turn3.png", turn=3)
flyin.compare(map_path, old_turns, turns, labels=("old", "new"))

outcomes = flyin.test("python3 main.py {map}", cwd=".", only="challenge")
for o in outcomes:
    print(o.status, o.case.name, o.message)
```

All functions: [docs/REFERENCE.md](docs/REFERENCE.md#library).

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

## More

- [docs/REFERENCE.md](docs/REFERENCE.md): every command and option, the
  visualizer keys, all library functions, how a map is judged, the map
  groups, development.
- [flyin/RULES.md](flyin/RULES.md): how flyin reads the open points of
  the subject. The checker agrees with the independent validator of
  [42-fly-in-claude](https://github.com/jasuoh/42-fly-in-claude) on 4605
  deliberately broken solutions.
- Tests: `make dev-test`; lint: `make lint`; CI runs both on Linux and
  macOS.

The visualizer comes from [42-fly-in-claude](https://github.com/jasuoh/42-fly-in-claude),
the tester from [fly-in-tests](https://github.com/jasuoh/fly-in-tests). Fonts:
SIL Open Font License (`flyin/visual/assets/fonts/OFL-*.txt`).
