"""Test fakes — drop-in substitutes for production network/IO clients.

Phase 0 builds the minimum needed to run the V2 pipeline offline:
- `FakeStockApiClient` — stand-in for `auth` + TCBS REST surface used by tests.
- `FakeDataProvider` — fixture-backed `DataProvider` substitute returning
  frames that conform to `schemas.ohlcv.validate_ohlcv`.
"""

from tests.fakes.fake_data_provider import FakeDataProvider
from tests.fakes.fake_stock_api_client import FakeStockApiClient

__all__ = ["FakeStockApiClient", "FakeDataProvider"]
