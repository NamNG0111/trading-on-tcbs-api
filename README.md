# trading-on-tcbs-api

[![CI](https://github.com/NamNG0111/trading-on-tcbs-api/actions/workflows/ci.yml/badge.svg)](https://github.com/NamNG0111/trading-on-tcbs-api/actions/workflows/ci.yml)

Algorithmic trading system integrated with the Vietnamese TCBS brokerage API. Supports historical backtesting, live market scanning, and paper/live order execution.

See `CLAUDE.md` for the architecture overview and `docs/AI_INTEGRATION_PLAN.md` for the multi-phase roadmap toward agent readiness.

## Quick start

```bash
make install-dev   # install runtime + dev deps
make test          # 56 tests, network-free
make ci            # test + lint + typecheck (lint/typecheck non-blocking until Phase 3)
make fixtures      # regenerate test OHLCV fixtures (rare; review the diff)
```

The fixtures used by the regression seals live under `tests/fixtures/` and are deterministic by seed. Update them only with intent.
