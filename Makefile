# Phase 0 — test harness foundation. Targets are deliberately thin so CI and
# local devs run the same commands. Add `--strict` flags here only after the
# corresponding phase DoD lands (mypy strict = Phase 3 DoD).

PY ?= python
PIP ?= $(PY) -m pip
PYTEST ?= $(PY) -m pytest

.PHONY: help install install-dev test lint typecheck ci fixtures clean strategy-smoke strategy-smoke-all

help:
	@echo "Targets:"
	@echo "  install               Install runtime dependencies (requirements.txt)."
	@echo "  install-dev           Install dev dependencies (requirements-dev.txt)."
	@echo "  test                  Run pytest."
	@echo "  lint                  Run ruff."
	@echo "  typecheck             Run mypy on the V2 package."
	@echo "  ci                    Run lint + typecheck + test (the CI bundle)."
	@echo "  fixtures              Regenerate test fixture CSVs and expected signals."
	@echo "  strategy-smoke NAME=… Run Phase-4 smoke gates for one strategy."
	@echo "  strategy-smoke-all    Run smoke gates for every registered strategy."
	@echo "  clean                 Remove pyc / pytest cache."

install:
	$(PIP) install -r requirements.txt

install-dev: install
	$(PIP) install -r requirements-dev.txt

test:
	$(PYTEST)

lint:
	$(PY) -m ruff check trading_on_tcbs_api/stock_system_v2 tests

typecheck:
	$(PY) -m mypy trading_on_tcbs_api/stock_system_v2

# CI bundle. Lint + typecheck are non-fatal at Phase 0 (we just need the
# tools to run); tests must pass. Phase 3 will tighten the bar.
ci: test
	-$(MAKE) lint
	-$(MAKE) typecheck

fixtures:
	$(PY) tests/fixtures/generate_fixtures.py

# Phase-4 strategy smoke gates. Pass the registry id via NAME=…, e.g.
#   make strategy-smoke NAME=rsi
strategy-smoke:
	@if [ -z "$(NAME)" ]; then echo "usage: make strategy-smoke NAME=<registry_id>"; exit 2; fi
	$(PY) -m trading_on_tcbs_api.stock_system_v2.scripts.strategy_smoke $(NAME)

# Smoke every strategy in the registry. CI runs this on PRs that touch
# strategies/ — see .github/workflows/ci.yml.
strategy-smoke-all:
	@$(PY) -c "from trading_on_tcbs_api.stock_system_v2.strategies import STRATEGIES; print('\n'.join(STRATEGIES))" \
		| xargs -I{} $(PY) -m trading_on_tcbs_api.stock_system_v2.scripts.strategy_smoke {}

clean:
	find . -type d -name __pycache__ -prune -exec rm -rf {} +
	rm -rf .pytest_cache .mypy_cache .ruff_cache
