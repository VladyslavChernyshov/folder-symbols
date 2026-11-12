# Folder Symbols: everyday commands. Run `make` (or `make help`) to list them.
# In PhpStorm / JetBrains IDEs the "Makefile Language" plugin shows a green arrow next to each target.
#
# Settings can be overridden on the command line, e.g.:
#   make test K=svg                      only tests whose name matches "svg"
#   make release TAG=v2 OUT=~/release    build release archives for tag v2
#   make sample THEMES=Yaru,Yaru-dark    sample set for two variants

PYTHON     ?= python3
ICONS_ROOT ?= /usr/share/icons
SYMBOLS    ?= $(ICONS_ROOT)/Yaru/scalable
THEMES     ?= Yaru,Yaru-dark,Yaru-purple-dark,Yaru-sage
# a small, varied subset of symbols (same as in CI), so trial runs take seconds
ONLY       ?= ^(a|c|d|e|network-w|share|view-)
DIST       ?= dist
OUT        ?= $(HOME)/release
TAG        ?= v1
K          ?=

.DEFAULT_GOAL := help
.PHONY: help deps \
        test test-fast test-one test-no-yaru check \
        sample sample-svg centering sheets \
        release \
        screenshot social-preview themes-json \
        cli-help clean

help: ## Show this list
	@awk 'BEGIN {FS = ":.*## "} \
	  /^##@/ {printf "\n\033[1m%s\033[0m\n", substr($$0, 5); next} \
	  /^[a-zA-Z_-]+:.*## / {printf "  \033[36mmake %-15s\033[0m %s\n", $$1, $$2}' $(MAKEFILE_LIST)
	@echo

##@ Setup
deps: ## Install system packages (Ubuntu): Yaru icons, Pillow, numpy, scipy, pytest, rsvg-convert
	sudo apt-get install -y yaru-theme-icon python3-pil python3-numpy python3-scipy python3-pytest librsvg2-bin

##@ Tests
test: ## Run all tests (stops with an error if Yaru is not installed)
	$(PYTHON) -m pytest -v

test-fast: ## Run all tests quietly and stop at the first failure
	$(PYTHON) -m pytest -q -x

test-one: ## Run only tests matching K, e.g. make test-one K=screenshot
	@test -n "$(K)" || { echo "usage: make test-one K=<part of a test name>"; exit 2; }
	$(PYTHON) -m pytest -v -k "$(K)"

test-no-yaru: ## Run only the tests that do not need Yaru; the rest are skipped (shows which)
	ALLOW_NO_YARU=1 YARU_ICONS_ROOT=/nonexistent YARU_SYMBOLS_DIR=/nonexistent $(PYTHON) -m pytest -q -rs

check: test sample-svg centering cli-help ## Everything CI runs on every push (tests, samples, centring)

##@ Generate icons (output goes to dist/, which git ignores)
sample: ## PNG sample set (256 px) for a few variants and symbols
	$(PYTHON) folder-symbols batch --out $(DIST) --themes $(THEMES) --sizes 256 --only '$(ONLY)' --jobs 4 | tail -3

sample-svg: ## SVG sample set for all variants; checks that rsvg-convert can render them
	$(PYTHON) folder-symbols batch --out $(DIST)-svg --themes all --sizes svg --only '$(ONLY)' --jobs 4 | tail -3
	@test "$$(find $(DIST)-svg -name '*.svg' | wc -l)" -gt 100
	@for f in $$(find $(DIST)-svg -name 'share.svg'); do rsvg-convert -w 128 "$$f" > /dev/null || exit 1; done
	@echo "SVG sample set renders OK"

centering: sample ## Check that every symbol is centred on the folder (needs the PNG sample set)
	@for t in $$(echo "$(THEMES)" | tr ',' ' '); do \
	  d=$(DIST)/$$t/256; [ -d "$$d" ] || continue; \
	  echo "== $$d"; \
	  $(PYTHON) tools/check_centering.py "$$d" --max-offset 1.0 | head -3 || exit 1; \
	done

sheets: sample ## Contact sheets (one picture per variant) for eyeballing, in sheets/
	@mkdir -p sheets
	@for t in $$(echo "$(THEMES)" | tr ',' ' '); do \
	  [ -d $(DIST)/$$t/256 ] && $(PYTHON) tools/contact_sheet.py $(DIST)/$$t/256 sheets/$$t.png --every 4 || true; \
	done
	@echo "Open the pictures in sheets/"

##@ Release (icons repository)
release: ## Build release archives: SVG zips for all variants + checksums + notes (OUT=, TAG=)
	$(PYTHON) tools/make_release.py --out $(OUT) --symbols-dir $(SYMBOLS) --tag $(TAG)
	@echo "Upload the contents of $(OUT) as release assets"

##@ Docs and data
screenshot: ## Redraw docs/screenshot.png (fake Nautilus, light | dark)
	$(PYTHON) tools/make_screenshot.py --symbols-dir $(SYMBOLS) --out docs/screenshot.png

social-preview: ## Redraw docs/social-preview.png (1280x640 for GitHub, 8x3 grid)
	$(PYTHON) tools/make_screenshot.py --symbols-dir $(SYMBOLS) --grid 8x3 --size 1280x640 --out docs/social-preview.png

themes-json: ## Rebuild assets/themes.json after a Yaru update (then run `make test`)
	$(PYTHON) tools/build_themes_json.py --icons-root $(ICONS_ROOT) --out assets/themes.json

##@ Misc
cli-help: ## Check that running the script without arguments prints the help
	@$(PYTHON) folder-symbols 2>&1 | grep -q -- --skip-existing && echo "help OK"

clean: ## Delete generated files: dist/, dist-svg/, sheets/, caches
	rm -rf $(DIST) $(DIST)-svg sheets .pytest_cache
	find . -name __pycache__ -type d -prune -exec rm -rf {} +
