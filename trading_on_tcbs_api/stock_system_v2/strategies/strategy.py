"""SignalStrategy — abstract base for every V2 trading strategy.

Phase-4 refactor: `generate_signals` is now a concrete, final-style method
on the base. Subclasses override `_compute_signals` instead, and the base
takes care of warmup masking and (later) typed `signal_context`
attachment. This keeps the contract honest — no strategy can accidentally
emit a signal before its declared `min_bars_required`.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, Mapping

import pandas as pd

from trading_on_tcbs_api.stock_system_v2.schemas.strategy_meta import (
    StrategyDescription,
    StrategyParams,
)


class SignalStrategy(ABC):
    """Abstract base class for all V2 trading strategies.

    Subclass requirements (also enforced by `strategies/CONTRIBUTING.md`):
      - Define a nested `class Params(StrategyParams):` Pydantic model with
        every tunable knob constrained by `Field(ge=…, le=…)`.
      - Set the class-level `min_bars_required: int` to the longest
        lookback window the strategy uses. The base class refuses to
        emit any non-zero signal before that bar.
      - Override `_compute_signals(df) -> pd.DataFrame` to do the work.
        Read indicators by lower-case name (`sma_20`, `rsi_14`).
      - Override `describe() -> StrategyDescription` so an agent can
        introspect what the strategy does.
      - Override `get_required_indicators` to declare which engine outputs
        you depend on; the scanner uses this to extract context columns.

    Args:
        params: Either a `Params` instance, a dict that constructs one,
            or `None` (uses `Params()` defaults). Validation runs at
            construction so bad values fail fast.

    Example:
        >>> class MyMA(SignalStrategy):
        ...     name = "My MA"
        ...     description = "BUY above SMA20."
        ...     min_bars_required = 20
        ...     class Params(StrategyParams):
        ...         window: int = Field(20, ge=2, le=200)
        ...     def _compute_signals(self, df):
        ...         out = df.copy()
        ...         out["signal"] = (out["close"] > out[f"sma_{self.params.window}"]).astype(int)
        ...         return out
    """

    name: str = "Generic Strategy"
    description: str = "Base strategy"
    min_bars_required: int = 0

    Params: type[StrategyParams] = StrategyParams

    def __init__(self, params: StrategyParams | dict[str, Any] | None = None, **kwargs: Any) -> None:
        if params is None and kwargs:
            self.params = self.Params(**kwargs)
        elif isinstance(params, dict):
            self.params = self.Params(**params)
        elif params is None:
            self.params = self.Params()
        else:
            self.params = params

    # — public API —

    def get_brief(self) -> str:
        """Return a one-line label suitable for logs and TUIs."""
        return f"{self.name}: {self.description}"

    def generate_signals(self, data: pd.DataFrame) -> pd.DataFrame:
        """Compute the signal column, with warmup masking applied.

        Subclasses must override `_compute_signals`, not this method.
        Any non-zero signal in the first `min_bars_required` rows is
        zeroed out — the base class is the source of truth for warmup,
        not the subclass.

        Args:
            data: OHLCV frame already augmented with the indicator columns
                listed in `get_required_indicators()`.

        Returns:
            The frame with a `signal` column where 1=BUY, -1=SELL, 0=HOLD.

        Raises:
            ValueError: when a required indicator column is missing.
        """
        out = self._compute_signals(data)
        if self.min_bars_required > 0 and "signal" in out.columns and len(out) > 0:
            cap = min(self.min_bars_required, len(out))
            out.iloc[:cap, out.columns.get_loc("signal")] = 0
        return out

    @abstractmethod
    def _compute_signals(self, data: pd.DataFrame) -> pd.DataFrame:
        """Subclass hook: produce the `signal` column on `data`.

        Implementations should not pre-mask the warmup window — the base
        class does that. Just ensure the column exists in the returned
        frame even when no signal fires.
        """

    def analyze(self, data: pd.DataFrame) -> Mapping[str, Any]:
        """Optional: compute strategy-specific summary metrics for `data`."""
        return {}

    def get_required_indicators(self) -> list[str]:
        """Return engine column names this strategy reads.

        Used by `MarketScanner` to pick which extra columns to surface as
        `ScanResult.signal_context`. Default returns `[]`.
        """
        return []

    # — typed signal_context accessor (Phase 4) —

    # Subclass-specific names to surface on each scan row when present.
    # Override with extra strategy-specific columns (e.g. `dip_threshold`).
    context_columns: tuple[str, ...] = ()

    def extract_signal_context(self, row: pd.Series) -> dict[str, Any]:
        """Build the typed `signal_context` dict for one bar's signal.

        Default: take every column listed in `get_required_indicators()`
        plus `context_columns`, coerce numpy/pandas scalars to plain
        Python, and skip missing or NaN values. Strategies that compute
        derived context (e.g. `%_from_sma20`) should add the column name
        to `context_columns`.

        Args:
            row: A `pd.Series` representing one bar of a scored frame.

        Returns:
            Mapping of context-column name → value, JSON-serialisable.
        """
        out: dict[str, Any] = {}
        wanted: list[str] = list(self.get_required_indicators()) + list(self.context_columns)
        for col in wanted:
            if col not in row.index:
                continue
            value = row[col]
            if hasattr(value, "item"):
                try:
                    value = value.item()
                except (ValueError, AttributeError):
                    pass
            try:
                if pd.isna(value):  # type: ignore[arg-type]
                    continue
            except (TypeError, ValueError):
                pass
            out[col] = value
        return out

    def describe(self) -> StrategyDescription:
        """Return an agent-readable description of this strategy.

        Default implementation derives most fields from class attributes
        and the nested `Params` schema; subclasses can override to inject
        a richer rationale or document failure modes explicitly.
        """
        return StrategyDescription(
            name=self.name,
            rationale=self.description,
            signal_semantics="1=BUY, -1=SELL, 0=HOLD on each bar.",
            indicators_used=list(self.get_required_indicators()),
            min_bars_required=self.min_bars_required,
            params_schema=self.Params.model_json_schema(),
        )
