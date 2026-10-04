# Shortcuts for `python3 start.py ...`. Everything also works without make.

PYTHON ?= python3
START   = $(PYTHON) start.py

.DEFAULT_GOAL := menu
.PHONY: menu run install setup test show problems maps dev-test lint clean

menu:            ## the interactive menu (also: make run)
	@$(START)

run: menu

install:         ## visualizer (pygame-ce) into .venv/
	@$(START) install

setup:           ## connect your project
	@$(START) setup

test:            ## test all maps (WHAT=group or part of a name)
	@$(START) test $(WHAT)

show:            ## watch a map, e.g. make show MAP=easy/01
	@$(START) show $(MAP)

problems:        ## watch the problem maps of the last test
	@$(START) show --problems

maps:            ## list the maps
	@$(START) maps $(WHAT)

dev-test:        ## tests of flyin itself
	$(if $(wildcard .venv/bin/python),.venv/bin/python,$(PYTHON)) -m unittest discover -s tests -t .

lint:            ## flake8 + mypy --strict
	$(PYTHON) -m flake8 .
	$(PYTHON) -m mypy .

clean:
	@find . -path ./.venv -prune -o -type d \( -name __pycache__ -o -name .mypy_cache \) -prune -exec rm -rf {} +
