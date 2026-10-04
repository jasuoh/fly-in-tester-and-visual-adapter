"""Graphical simulation player built with pygame-ce.

Modules, from data to pixels:

* ``themes``: the three looks (all colours in one place).
* ``colors``, ``fonts``, ``painter``: colour maths, Geist fonts,
  anti-aliased drawing primitives.
* ``layout``: window regions and map-to-screen projection.
* ``timeline``: moves -> drone states, replayed lazily with snapshots.
* ``animation``: drone states -> smooth positions, fades, highlights.
* ``scene`` (static, cached) and ``map_layer`` (per frame): the map.
* ``panel``, ``hud``, ``timeline_bar``: side panel and timeline.
* ``player``, ``window``, ``icon``: playback position, event loop,
  window title and the procedurally drawn app icon.
* ``visualizer``: :class:`GuiVisualizer`, the public entry point.
"""

import os

os.environ.setdefault("PYGAME_HIDE_SUPPORT_PROMPT", "1")

from fly_in_visual.gui.visualizer import GuiVisualizer  # noqa: E402

__all__ = ["GuiVisualizer"]
