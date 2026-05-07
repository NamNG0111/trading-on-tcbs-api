# Contributing a strategy to V2

This document is the bar a strategy must clear to merge — for a human, a
teammate, or a Phase-9 agent proposing a strategy as a PR. CI is the
referee; if `make ci` and `make strategy-smoke <name>` pass, the
strategy is mergeable. If they don't, it isn't.

## Why these rules exist

V2 strategies are tools an AI agent will call. That means: bad params
must fail at construction (not at runtime); claims must be backed by
tests (not by author assertion); and the strategy must self-describe in
JSON so the agent can pick it without code-reading. Every rule below
maps to one of those three goals.

---

## 1. Code requirements

- [ ] Subclass `SignalStrategy` and live in `strategies/<name>_strategy.py`.
- [ ] Declare a nested `class Params(StrategyParams):` Pydantic model.
      Every field has a type and a `Field(ge=…, le=…, description=…)` —
      the description shows up in the JSON schema agents read.
- [ ] Set `min_bars_required: int` (instance attribute is fine; assign
      in `__init__` after `super().__init__`). It must be ≥ the longest
      lookback your strategy uses.
- [ ] Override `_compute_signals(df) -> pd.DataFrame`, not
      `generate_signals`. The base class enforces warmup masking and
      will eventually attach typed context.
- [ ] Implement `get_required_indicators() -> list[str]` listing the
      `IndicatorEngine` columns you read. Do **not** invent indicators in
      the strategy itself — extend `IndicatorEngine` in a separate PR.
- [ ] Override `describe() -> StrategyDescription` and fill in
      `expected_regime` + `known_failure_modes`. Default rationale is
      derived from the class docstring; only override if the default is
      misleading.
- [ ] Add the strategy to `STRATEGIES` in `strategies/registry.py`.
- [ ] No `print()`. Use `logger.info(event, **fields)` (Phase 6 standard).
- [ ] No catch-all `except Exception`. Raise typed errors from
      `stock_system_v2.exceptions` so the tool layer can surface them.

## 2. Required tests

Add a file `tests/strategies/test_<name>.py` with at least:

- [ ] **Regression seal** — runs the strategy on `tests/fixtures/<symbol>.csv`
      and asserts the resulting signal series matches a checked-in
      `tests/fixtures/expected/<name>__<symbol>.csv`. Generate the
      expected file with `python tests/fixtures/generate_fixtures.py`
      and review the diff before committing.
- [ ] **No-lookahead** — call `assert_no_lookahead(strategy, df)` from
      `tests/utils/lookahead.py`. Catches strategies that peek at
      future bars.
- [ ] **Warmup** — assert `(out["signal"].iloc[: min_bars_required] == 0).all()`.
- [ ] **Param validation** — instantiate via `cls(params={...})` with
      out-of-range values and confirm a `pydantic.ValidationError`.
- [ ] **Determinism** — run the strategy twice on the same input and
      assert the outputs are equal.

## 3. Performance smoke gates

Run `make strategy-smoke <name>` locally. CI runs the same gates on any
PR touching `strategies/` (see `.github/workflows/ci.yml`).

- [ ] Walk-forward backtest on the standard equity universe completes
      without error.
- [ ] Out-of-sample Sharpe is reported (negative is allowed — being bad
      is fine, hiding it is not).
- [ ] Trade count over the test window is between 5 and 500 by default.
      Strategies that never fire or fire on every bar fail the gate.
- [ ] Max single-bar drawdown is finite and reported.

The gates intentionally *do not* require the strategy to be profitable.
They require it to be measurable, bounded, and honest.

## 4. Documentation

- [ ] One-line entry in `strategies/README.md` (create if missing).
- [ ] Class-level docstring written for an agent, not a coworker — no
      shorthand, no internal jargon, no "see Slack for context."

---

When CI is green and the diff is reviewed, the strategy is mergeable.
