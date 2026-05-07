"""Agent layer (Phases 8 + 9).

Two views of every agent:

  1. **Programmatic recipe** — a Python function that drives the tool
     layer in a deterministic, testable order. Tests assert on its
     output. The LLM-driven version of the same agent ends up making
     the same tool calls in the same order; the recipe is the spec.

  2. **LLM system prompt** — a markdown file under `agents/prompts/`
     that an operator drops into the Claude Anthropic API or Claude
     Code session. The prompt describes the toolbelt the agent has,
     the success criteria, and the structured output schema.

Both views call the same `tools.invoke(...)` dispatcher. There is no
back-channel. If the recipe can't do the work with the tools, the LLM
can't either — and the toolbelt has a gap to fix.

Phase-8 agents:

    research_strategy_for_symbol(symbol, …) → ResearchNote
    daily_scan(...)                         → ScannerReport
    evaluate_proposed_order(req, …)         → RiskOpinion
    paper_trade_cycle(...)                  → PaperTradeReport

Phase-9 continuous-learning primitives (`agents.continuous`):

    decisions_dataset(...)                  → DecisionsDataset
    strategy_proposal_brief()               → StrategyProposalBrief
    drift_check(strategy, symbol, …)        → DriftAlert
    flag_tool_output(...)                   → appends one row to tool_quality.jsonl
"""

from .continuous import (
    DecisionsDataset,
    DriftAlert,
    StrategyProposalBrief,
    decisions_dataset,
    drift_check,
    flag_tool_output,
    strategy_proposal_brief,
)
from .paper_trader import PaperTradeReport, paper_trade_cycle
from .research import ResearchNote, research_strategy_for_symbol
from .risk import RiskOpinion, evaluate_proposed_order
from .scanner import ScannerReport, daily_scan

__all__ = [
    "DecisionsDataset",
    "DriftAlert",
    "PaperTradeReport",
    "ResearchNote",
    "RiskOpinion",
    "ScannerReport",
    "StrategyProposalBrief",
    "daily_scan",
    "decisions_dataset",
    "drift_check",
    "evaluate_proposed_order",
    "flag_tool_output",
    "paper_trade_cycle",
    "research_strategy_for_symbol",
    "strategy_proposal_brief",
]
