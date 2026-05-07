"""Strategy metadata schemas (Phase 4).

Two cross-cutting types live here:

- `StrategyParams` — the Pydantic base every concrete strategy uses for
  its tunable knobs. Subclassed as a nested `Params` on each strategy so
  param validation (range, type) happens at construction time, before
  any bar is processed. An agent listing strategies gets a complete JSON
  schema for free via `Params.model_json_schema()`.

- `StrategyDescription` — a frozen, agent-readable description of a
  strategy: human label, one-paragraph rationale, signal semantics,
  warmup requirement, indicators it reads, and the params schema.
  `MarketScanner.list_strategies()` (Phase 7 tool) emits a list of these.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class StrategyParams(BaseModel):
    """Base class for every strategy's typed param block.

    Concrete strategies declare a nested `class Params(StrategyParams):`
    with fields constrained by `Field(ge=…, le=…)`. Agents reading the
    JSON schema can render an accurate input form without prior
    knowledge of the strategy.

    `extra='forbid'` means typos at construction time raise rather than
    silently noop — the exact failure mode that bites tool-driven use.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)


class StrategyDescription(BaseModel):
    """Agent-readable description of one strategy.

    Use `Strategy.describe()` to obtain. The `params_schema` field is
    `Params.model_json_schema()` — an agent can construct a valid
    `Params` from it without code-reading the strategy.
    """

    model_config = ConfigDict(frozen=True)

    name: str = Field(..., description="Human-friendly label, e.g. 'RSI Reversal'.")
    rationale: str = Field(..., description="One-paragraph explanation of when and why this strategy fires.")
    signal_semantics: str = Field(..., description="What BUY / SELL / HOLD mean for this specific strategy.")
    expected_regime: str = Field(
        "any",
        description="Market regime the strategy expects to do well in (trend / mean-revert / vol-expansion / any).",
    )
    known_failure_modes: str = Field(
        "",
        description="Known regimes or conditions where this strategy is expected to underperform.",
    )
    indicators_used: list[str] = Field(default_factory=list, description="`IndicatorEngine` column names this strategy reads.")
    min_bars_required: int = Field(..., ge=0, description="Bars of warmup before any non-zero signal is allowed.")
    params_schema: dict[str, Any] = Field(default_factory=dict, description="`Params.model_json_schema()` snapshot.")
