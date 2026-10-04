# Fly-In arena: tester + visualizer. Run `make` (or `make help`) for the targets.

# Your project: the directory your command runs in.
PROJECT ?= .
# Interpreter for the arena itself (needs pygame-ce only for the visualizer).
PYTHON  ?= $(if $(wildcard .venv/bin/python),.venv/bin/python,python3)
# Command that runs one map; {map} is replaced by the map path, {out} by a
# file your program should write. Default: the naive example solver.
CMD     ?= $(PYTHON) $(CURDIR)/examples/naive_solver.py {map}
JOBS    ?= 4
TIMEOUT ?= 25
# Optional: GROUP=provided|provided-invalid|edge-valid|edge-invalid|challenge
#           FILTER=<text in the map path>   ARGS=<extra options>
GROUP   ?=
FILTER  ?=
ARGS    ?=
# For `make view`: the map, and optionally an output file instead of CMD.
MAP     ?= maps/provided/hard/03_ultimate_challenge.txt
OUT     ?=
THEME   ?= mission

.DEFAULT_GOAL := help
.PHONY: help install run run-strict view view-fail list check test lint all clean

help:
	@echo 'make install      create .venv with pygame-ce (visualizer), flake8, mypy'
	@echo 'make run          test your program on all maps (PROJECT, CMD, GROUP, FILTER, JOBS, TIMEOUT, ARGS)'
	@echo 'make run-strict   like run, but turns above the targets fail too'
	@echo 'make view         watch your program solve one map (MAP, CMD or OUT, THEME)'
	@echo 'make view-fail    run, then watch every map that failed or missed its target'
	@echo 'make list         list the maps (GROUP, FILTER)'
	@echo 'make check        check an output: make check MAP=<map> OUT=<file or ->'
	@echo 'make test         tests of the arena itself'
	@echo 'make lint         flake8 and mypy --strict'
	@echo 'make all          lint + test'
	@echo 'make clean        remove caches'
	@echo
	@echo 'Examples:'
	@echo '  make run  PROJECT=../my-fly-in CMD="python3 main.py {map}"'
	@echo '  make view PROJECT=../my-fly-in CMD="python3 main.py {map}" MAP=maps/challenge/04_city_grid.txt'
	@echo '  make view OUT=my_output.txt MAP=maps/provided/easy/01_linear_path.txt THEME=ashen'
	@echo '  make view-fail PROJECT=../my-fly-in CMD="./fly_in {map}" GROUP=challenge'

install:
	python3 -m venv .venv
	.venv/bin/python -m pip install -q --upgrade pip
	.venv/bin/python -m pip install -q pygame-ce flake8 mypy

run:
	$(PYTHON) -m fly_in_tester run --cmd '$(CMD)' --cwd '$(PROJECT)' --jobs $(JOBS) --timeout $(TIMEOUT) \
		$(if $(GROUP),--group $(GROUP)) $(if $(FILTER),--filter '$(FILTER)') $(ARGS)

run-strict:
	$(MAKE) run ARGS='--strict-targets $(ARGS)'

view:
	$(PYTHON) -m fly_in_tester view '$(MAP)' $(if $(OUT),'$(OUT)',--cmd '$(CMD)' --cwd '$(PROJECT)') \
		--theme $(THEME) $(ARGS)

view-fail:
	$(MAKE) run ARGS='--view warn --theme $(THEME) $(ARGS)'

list:
	$(PYTHON) -m fly_in_tester list $(if $(GROUP),--group $(GROUP)) $(if $(FILTER),--filter '$(FILTER)')

check:
	@test -n '$(MAP)' -a -n '$(OUT)' || { echo 'usage: make check MAP=<map> OUT=<file or ->'; exit 2; }
	$(PYTHON) -m fly_in_tester check '$(MAP)' '$(OUT)'

test:
	$(PYTHON) -m unittest discover -s tests -t .

lint:
	$(PYTHON) -m flake8 .
	$(PYTHON) -m mypy .

all: lint test

clean:
	@find . -path ./.venv -prune -o -type d \( -name __pycache__ -o -name .mypy_cache \) -prune -exec rm -rf {} +
