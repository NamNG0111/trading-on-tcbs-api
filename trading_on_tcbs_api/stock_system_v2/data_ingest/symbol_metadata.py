"""Per-symbol metadata — the deterministic replacement for the `<500 → ×1000`
price-scaling heuristic.

The vnstock KBS source returns daily prices in *thousands of VND* for HoSE/HNX
equities. Multiplying by 1000 only when `df['close'].mean() < 500` is a
heuristic an agent cannot reason about: it can silently flip for low-priced
stocks during a crash, or for newly-listed names whose mean is dragged down by
the first few days. Instead, look the scale up.

Phase 1 introduces a minimal table covering the production universe in
`config.SYMBOLS`. Add new symbols here, not by tuning thresholds.

Future-phase migration: move this table out of code and into a CSV/YAML loaded
once at startup, keyed off the broader exchange (HOSE / HNX / UPCOM).
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class SymbolMeta:
    """Static metadata for a tradable symbol."""

    symbol: str
    exchange: str  # "HOSE", "HNX", "UPCOM"
    # Multiply raw vnstock prices by this factor to obtain VND.
    # vnstock-KBS returns thousand-VND for equities → factor 1000.
    vnstock_price_scale: int = 1000
    lot_size: int = 100  # HoSE round-lot default


_SYMBOL_TABLE: dict[str, SymbolMeta] = {
    sym: SymbolMeta(symbol=sym, exchange="HOSE")
    for sym in ("TCB", "HPG", "SSI", "VHM", "VIC", "VRE", "VNM", "FPT")
}


def get_symbol_meta(symbol: str) -> SymbolMeta:
    """Return metadata for `symbol`, falling back to a HOSE/×1000 default.

    The fallback exists so an unknown symbol still scales correctly under the
    overwhelmingly-common HoSE convention; the caller is expected to register
    explicit entries for any production symbol.
    """
    if symbol in _SYMBOL_TABLE:
        return _SYMBOL_TABLE[symbol]
    return SymbolMeta(symbol=symbol, exchange="HOSE")


def register_symbol(meta: SymbolMeta) -> None:
    """Register or overwrite the metadata entry for a symbol.

    Used by tests and by the eventual config-file loader.
    """
    _SYMBOL_TABLE[meta.symbol] = meta
