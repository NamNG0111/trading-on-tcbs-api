from typing import TypedDict

import pandas as pd
import pandas_ta as ta  # noqa: F401  # registers the `df.ta` accessor by side effect

from trading_on_tcbs_api.stock_system_v2.schemas.ohlcv import closed_bars

_ = ta  # silence unused-import linters that don't honour the noqa


class MACDParams(TypedDict, total=False):
    fast: int
    slow: int
    signal: int


class IndicatorConfig(TypedDict, total=False):
    """Typed shape of the dict accepted by `IndicatorEngine`.

    Each key is optional; missing keys mean "do not compute". Lengths are
    bar counts. Pandas-ta name conventions are documented on the engine
    class itself.
    """

    sma: list[int]
    ema: list[int]
    rsi: list[int]
    macd: list[MACDParams]
    vol_ma: list[int]
    roc: list[int]


class IndicatorEngine:
    """
    Centralized Technical Indicator processing engine using pandas-ta.
    Calculates all required indicators for strategies in a single pass.

    Look-ahead audit (Phase 2): every indicator below is **causal** — value at
    bar `t` depends only on closed bars in the inclusive window `[t-L+1, t]`,
    where `L` is the indicator's lookback length. Today's still-forming bar is
    excluded by `closed_bars(df)` before computation, so no synthetic OHLC ever
    contaminates a rolling window. Callers should treat signals derived from
    these indicators as actionable on the **same bar's close** at the earliest.

    Indicator        | Lookback (L)               | Source
    -----------------|----------------------------|--------------------
    SMA_<n>          | n closed bars              | pandas-ta `sma`
    EMA_<n>          | n closed bars (recursive)  | pandas-ta `ema`
    RSI_<n>          | n+1 closed bars            | pandas-ta `rsi`
    MACD_f_s_sig     | s + sig closed bars        | pandas-ta `macd`
    ROC_<n>          | n+1 closed bars            | pandas-ta `roc`
    VOL_SMA_<n>      | n closed bars (volume)     | pandas rolling mean

    None of these reference `t+k` (k>0) at any step. The `assert_no_lookahead`
    test utility (`tests/utils/lookahead.py`) verifies this property
    end-to-end at the strategy boundary.
    """
    
    def __init__(self, config: IndicatorConfig | None = None) -> None:
        """Initialise the engine.

        Args:
            config: Indicator selection. If `None`, the default set
                (SMA 20/50, RSI 14, ROC 3, VOL_MA 20) is used.
        """
        self.config: IndicatorConfig = config or self.get_default_config()

    @staticmethod
    def get_default_config() -> IndicatorConfig:
        """
        Returns the default indicator configuration required by current generic strategies.
        """
        return {
            "sma": [20, 50],
            "ema": [],
            "rsi": [14],
            "macd": [],      # e.g., [{"fast": 12, "slow": 26, "signal": 9}]
            "vol_ma": [20],  # Volume MA
            "roc": [3],      # Rate of Change (multi-day returns)
        }

    def append_indicators(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        Appends requested technical indicators to the DataFrame using pandas-ta.

        Indicators are computed on **closed bars only** — any row marked
        `is_partial=True` (today's still-forming bar) is dropped before
        computation so that synthetic OHLC values do not contaminate rolling
        windows. The partial bar is intentionally not re-attached: callers
        that need live-price context should obtain it separately from
        `DataProvider.get_realtime_price`.
        """
        if df.empty or 'close' not in df.columns:
            return df

        data = closed_bars(df)
        if data.empty:
            return data
        data = data.copy()

        # SMA
        if "sma" in self.config:
            for length in self.config["sma"]:
                # pandas-ta automatically names the column 'SMA_20'
                if len(data) >= length:
                    data.ta.sma(length=length, append=True)
                else:
                    data[f"SMA_{length}"] = float('nan')

        # EMA
        if "ema" in self.config:
            for length in self.config["ema"]:
                if len(data) >= length:
                    data.ta.ema(length=length, append=True)
                else:
                    data[f"EMA_{length}"] = float('nan')

        # RSI
        if "rsi" in self.config:
            for length in self.config["rsi"]:
                # pandas-ta names it 'RSI_14'
                if len(data) >= length:
                    data.ta.rsi(length=length, append=True)
                else:
                    data[f"RSI_{length}"] = float('nan')

        # MACD
        if "macd" in self.config:
            for params in self.config["macd"]:
                slow = params.get("slow", 26)
                if len(data) >= slow:
                    data.ta.macd(
                        fast=params.get("fast", 12),
                        slow=slow,
                        signal=params.get("signal", 9),
                        append=True
                    )
                else:
                    # Provide fallback column names pandas-ta normally generates
                    fast = params.get("fast", 12)
                    sig = params.get("signal", 9)
                    data[f"MACD_{fast}_{slow}_{sig}"] = float('nan')
                    data[f"MACDh_{fast}_{slow}_{sig}"] = float('nan')
                    data[f"MACDs_{fast}_{slow}_{sig}"] = float('nan')
        # ROC (Rate of Change)
        if "roc" in self.config:
            for length in self.config["roc"]:
                if len(data) >= length:
                    data.ta.roc(length=length, append=True)
                else:
                    data[f"ROC_{length}"] = float('nan')
                    
        # Volume MA (Requires raw rolling, pandas-ta SMA is for close prices by default unless specified)
        if "vol_ma" in self.config:
            for length in self.config["vol_ma"]:
                data[f'VOL_SMA_{length}'] = data['volume'].rolling(window=length).mean()

        # Standardize column names (lowercase) for strategies
        data.columns = [str(col).lower() for col in data.columns]
        
        return data
