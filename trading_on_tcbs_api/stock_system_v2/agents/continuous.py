"""Phase 9 — Continuous Learning.

Three small primitives that close the agent loop:

  - `decisions_dataset(...)` reads `decisions.jsonl` and aggregates it
    into per-(symbol, strategy, side) stats the research agent can feed
    into its next ranking run. The audit trail becomes input data.

  - `strategy_proposal_brief(...)` produces a structured brief for the
    strategy-proposal agent: which strategies exist today, which
    market regimes are under-represented, and which symbols have
    persistently inconclusive research notes. The brief is the input
    the agent uses to draft a PR (code + backtest + walk-forward).

  - `drift_check(...)` compares the most recent paper-trade window
    against the strategy's walk-forward OOS expectation and raises a
    structured `DriftAlert` when the live PnL diverges past a
    threshold.

  - `flag_tool_output(...)` lets any agent record "this tool returned
    something I couldn't use" into a single jsonl file — the operator
    reviews flags weekly and either fixes the tool contract or closes
    the flag with a rationale.

Every primitive is read-only or append-only; nothing here mutates
positions or places orders.
"""

from __future__ import annotations

import json
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from trading_on_tcbs_api.stock_system_v2 import config
from trading_on_tcbs_api.stock_system_v2.obs import (
    current_correlation_id,
    get_logger,
    log_event,
    record_metric,
)
from trading_on_tcbs_api.stock_system_v2.tools import invoke

_logger = get_logger("continuous")


# — decisions dataset —

class DecisionStats(BaseModel):
    """Per-(symbol, strategy, side) aggregate over the audit log."""

    model_config = ConfigDict(frozen=True)

    symbol: str
    side: str
    n_decisions: int
    n_submitted: int
    n_skipped_reject: int
    n_skipped_warning: int
    n_skipped_error: int


class DecisionsDataset(BaseModel):
    """Roll-up of `decisions.jsonl`; input to future research runs."""

    model_config = ConfigDict(frozen=True)

    captured_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    n_rows: int
    n_correlation_ids: int
    by_symbol: dict[str, DecisionStats]
    raw_decision_codes: dict[str, int]


def decisions_dataset(*, path: str | Path | None = None, limit: int | None = None) -> DecisionsDataset:
    """Aggregate `decisions.jsonl` into agent-readable stats.

    Args:
        path: Override the default `EXPORT_DIR/decisions.jsonl`.
        limit: Read only the most recent N rows. None = read all.

    Returns:
        `DecisionsDataset`. Empty (`n_rows=0`) when the log doesn't exist.
    """
    target = Path(path) if path is not None else Path(config.EXPORT_DIR) / "decisions.jsonl"
    if not target.exists():
        return DecisionsDataset(n_rows=0, n_correlation_ids=0, by_symbol={}, raw_decision_codes={})

    lines = target.read_text().strip().splitlines()
    if limit is not None:
        lines = lines[-limit:]

    correlation_ids: set[str] = set()
    decision_codes: dict[str, int] = defaultdict(int)
    bucket: dict[tuple[str, str], dict[str, int]] = defaultdict(
        lambda: {"n": 0, "submitted": 0, "reject": 0, "warning": 0, "error": 0}
    )

    for line in lines:
        if not line.strip():
            continue
        try:
            row: dict[str, Any] = json.loads(line)
        except json.JSONDecodeError:
            continue
        cid = row.get("correlation_id")
        if cid:
            correlation_ids.add(cid)
        decision = (row.get("decision") or "").strip()
        decision_codes[decision or "(empty)"] += 1
        symbol = row.get("symbol") or "?"
        side = row.get("side") or "?"
        b = bucket[(symbol, side)]
        b["n"] += 1
        if decision.startswith("submit"):
            b["submitted"] += 1
        elif decision.startswith("reject"):
            b["reject"] += 1
        elif decision.startswith("skipped:warning"):
            b["warning"] += 1
        elif decision.startswith("skipped:error"):
            b["error"] += 1

    by_symbol: dict[str, DecisionStats] = {}
    for (symbol, side), b in bucket.items():
        key = f"{symbol}:{side}"
        by_symbol[key] = DecisionStats(
            symbol=symbol,
            side=side,
            n_decisions=b["n"],
            n_submitted=b["submitted"],
            n_skipped_reject=b["reject"],
            n_skipped_warning=b["warning"],
            n_skipped_error=b["error"],
        )

    return DecisionsDataset(
        n_rows=len(lines),
        n_correlation_ids=len(correlation_ids),
        by_symbol=by_symbol,
        raw_decision_codes=dict(decision_codes),
    )


# — strategy proposal brief —

class StrategyCoverageGap(BaseModel):
    """One regime / failure-mode the registry doesn't cover well."""

    model_config = ConfigDict(frozen=True)

    regime: str
    n_strategies: int
    note: str


class StrategyProposalBrief(BaseModel):
    """Input for the strategy-proposal agent's PR draft."""

    model_config = ConfigDict(frozen=True)

    captured_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    registered_strategies: list[str]
    by_regime: dict[str, list[str]]
    gaps: list[StrategyCoverageGap]
    instructions: str


def strategy_proposal_brief() -> StrategyProposalBrief:
    """Produce the brief the strategy-proposal agent works from.

    Walks `list_strategies` to bucket every existing strategy by
    declared `expected_regime`; flags regimes covered by 0–1 strategies
    as gaps the proposal agent should target.
    """
    resp = invoke("list_strategies")
    descs = resp.result.strategies
    by_regime: dict[str, list[str]] = defaultdict(list)
    for name, desc in descs.items():
        by_regime[desc.expected_regime].append(name)

    gaps: list[StrategyCoverageGap] = []
    for regime in ("trend", "mean-revert", "vol-expansion"):
        coverage = by_regime.get(regime, [])
        if len(coverage) <= 1:
            gaps.append(StrategyCoverageGap(
                regime=regime,
                n_strategies=len(coverage),
                note=(
                    f"Only {len(coverage)} strategy registered for regime {regime!r}. "
                    f"A proposal here would broaden the toolbelt."
                ),
            ))

    return StrategyProposalBrief(
        registered_strategies=sorted(descs),
        by_regime={k: sorted(v) for k, v in by_regime.items()},
        gaps=gaps,
        instructions=(
            "For each gap, draft one strategy as a PR. The PR must satisfy "
            "trading_on_tcbs_api/stock_system_v2/strategies/CONTRIBUTING.md "
            "(nested Params, min_bars_required, describe(), regression seal, "
            "no-lookahead test, smoke gate). The strategy proposal is "
            "approved iff `make strategy-smoke NAME=<id>` passes."
        ),
    )


# — drift detection —

class DriftAlert(BaseModel):
    """Live vs backtest divergence over `window_days`."""

    model_config = ConfigDict(frozen=True)

    captured_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    strategy: str
    symbol: str
    expected_oos_return_pct: float
    observed_live_return_pct: float
    delta_pct_points: float
    threshold_pct_points: float
    breached: bool
    rationale: str


def drift_check(
    *,
    strategy: str,
    symbol: str,
    observed_live_return_pct: float,
    walk_forward_days: int = 365 * 2,
    threshold_pct_points: float = 30.0,
) -> DriftAlert:
    """Compare live-paper PnL against the strategy's walk-forward OOS.

    Args:
        strategy: Registry id of the strategy whose live performance is
            being assessed.
        symbol: Symbol whose paper-trade book is in question.
        observed_live_return_pct: Compounded paper return over the
            same window as the WF rolling test.
        walk_forward_days: Window the WF run covers.
        threshold_pct_points: |observed - expected| past this triggers
            `breached=True`. Default 30 percentage points — generous
            so the alert fires on real drift, not noise.

    Returns:
        `DriftAlert`. Always returned; `breached` is the actionable bit.
    """
    resp = invoke("walk_forward", {
        "strategy": strategy,
        "symbol": symbol,
        "days": walk_forward_days,
    })
    expected = resp.result.result.oos_total_return_pct
    delta = observed_live_return_pct - expected
    breached = abs(delta) > threshold_pct_points
    if breached:
        log_event(
            _logger, "drift.alert.breach", level=40,
            strategy=strategy, symbol=symbol,
            expected=expected, observed=observed_live_return_pct,
            delta=delta,
        )
        record_metric("drift.alerts", 1.0, strategy=strategy, symbol=symbol)
        rationale = (
            f"Live paper return {observed_live_return_pct:.2f}% diverges "
            f"{abs(delta):.2f} pp from walk-forward OOS expectation "
            f"{expected:.2f}%. Investigate before continuing the soak."
        )
    else:
        rationale = (
            f"Live paper return {observed_live_return_pct:.2f}% is within "
            f"{threshold_pct_points:.0f} pp of WF OOS expectation "
            f"{expected:.2f}%."
        )
    return DriftAlert(
        strategy=strategy,
        symbol=symbol,
        expected_oos_return_pct=expected,
        observed_live_return_pct=observed_live_return_pct,
        delta_pct_points=delta,
        threshold_pct_points=threshold_pct_points,
        breached=breached,
        rationale=rationale,
    )


# — tool-quality feedback —

def flag_tool_output(
    *,
    tool_name: str,
    issue: str,
    arguments: dict[str, Any] | None = None,
    received: Any = None,
    severity: str = "minor",
    path: str | Path | None = None,
) -> None:
    """Append one row to `tool_quality.jsonl`.

    Any agent (or test) that observes a tool output it can't use should
    call this and continue. The operator's weekly review either fixes
    the tool contract or closes the flag. The file is append-only.

    Args:
        tool_name: Tool that produced the bad output.
        issue: One-line description ("returned None where a number was expected").
        arguments: The tool args that triggered the issue.
        received: Whatever the tool actually returned (best-effort serialised).
        severity: `minor`, `major`, or `blocking`.
        path: Override default `EXPORT_DIR/tool_quality.jsonl`.
    """
    target = Path(path) if path is not None else Path(config.EXPORT_DIR) / "tool_quality.jsonl"
    target.parent.mkdir(parents=True, exist_ok=True)
    row = {
        "ts": datetime.now(timezone.utc).isoformat(),
        "correlation_id": current_correlation_id(),
        "tool": tool_name,
        "issue": issue,
        "severity": severity,
        "arguments": arguments,
        "received": _safe(received),
    }
    with open(target, "a", encoding="utf-8") as f:
        f.write(json.dumps(row, default=_repr_fallback, ensure_ascii=False) + "\n")
    log_event(_logger, "tool_quality.flag", tool=tool_name, severity=severity)
    record_metric("tool_quality.flags", 1.0, tool=tool_name, severity=severity)


def _safe(value: Any) -> Any:
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if hasattr(value, "model_dump"):
        try:
            return value.model_dump()
        except Exception:  # noqa: BLE001
            pass
    if isinstance(value, (list, tuple)):
        return [_safe(v) for v in value]
    if isinstance(value, dict):
        return {str(k): _safe(v) for k, v in value.items()}
    return repr(value)


def _repr_fallback(value: Any) -> Any:
    if hasattr(value, "isoformat"):
        try:
            return value.isoformat()
        except Exception:  # noqa: BLE001
            pass
    return repr(value)
