# How flyin reads the subject

The Fly-In subject leaves some details open. Every checker has to decide
them somehow; this page says how flyin decides, so a verdict can be
discussed instead of guessed. If you read the subject differently, open
an issue and say which sentence you base it on.

`flyin rules` prints this page.

The checker was compared with the independent validator of
[42-fly-in-claude](https://github.com/jasuoh/42-fly-in-claude) on 4605
solutions (valid ones and deliberately broken variants: moves dropped,
moved to another turn, retargeted, duplicated, turns swapped or merged)
on 119 maps: both gave the same verdict every time. That shows the two
read the subject the same way; it cannot show that this reading is the
only possible one.

## Output

1. **One line per turn.** The number of turns is the number of turn lines.
   An empty line between turns is an error (a turn in which nothing
   happens is not allowed).
2. **Tokens** are `D<id>-<zone>` (a move) or `D<id>-<from>-<to>` (the
   first turn of a flight into a restricted zone). Anything else on a
   turn line is malformed.
3. **Other lines are ignored**: banners, debug prints, blank lines around
   the turns. Only lines made entirely of tokens count as turns
   (`--strict-output` turns other lines into a failure).
4. **Drone ids** are `D1..Dn` or `D0..D(n-1)`; both are accepted, mixing
   is not. Every drone must appear (it has to reach the end anyway).

## Moving

5. A drone **acts at most once per turn** and only along a connection.
6. **Blocked** zones are never entered.
7. **Restricted** zones take two turns: turn *t* `D1-a-r` (the drone is on
   the connection), turn *t+1* `D1-r` (it lands). Landing later, landing
   somewhere else or entering a restricted zone with the plain form is an
   error; so is using the flight form for a zone that is not restricted.
8. **Priority** zones cost one turn like normal zones. Some maps check that
   a priority route is preferred when it is just as fast; ignoring it is a
   warning, not a failure.
9. A drone that reached the **end** is delivered and must not move again.

## Capacity

10. **Zones**: at the end of every turn a zone holds at most `max_drones`
    drones. Start and end are unlimited.
11. **Leaving frees the place in the same turn.** A drone may move into a
    zone that another drone leaves in the same turn, so a full corridor can
    advance as a whole. (Otherwise a chain of capacity-1 zones could only
    move every second turn, which no reference solution does.)
12. **Drones in flight** towards a restricted zone are in no zone: they do
    not count for the zone they left (it is free in the departure turn) nor
    for the restricted zone until they land.
13. **Connections**: at most `max_link_capacity` drones *start* along a
    connection per turn, both directions together. The landing turn of a
    flight does not use the connection again (the departure already did),
    so the connection is free for another departure in that turn.

## Maps that must be rejected

14. A broken or unsolvable map must end with a **non-zero exit status**,
    **no traceback**, an error message on stderr and **no turn lines**.
15. For syntax errors the message must contain the **line number** of the
    mistake (any number in the message that matches counts). Maps whose
    rule is debatable are marked `recommended`: a different verdict is only
    a warning.

## Targets and scores

16. The `provided` targets are the "≤ N turns" values of the subject; more
    turns is a warning (`--strict` makes it a failure). The challenger
    target 44 (beat the record of 45) is optional.
17. `challenge` and `fuzz` targets are the **exact optimum**, computed once
    with an integer linear program over the time-expanded graph; missing
    them is an optional warning.
18. The **lower bound** shown for other maps is proven (see
    `flyin/tester/bounds.py`: a relaxed flow over time) but not always
    reachable: being above it does not mean a better solution exists. It
    equals the optimum on 230 of the 305 maps where the optimum is known.
