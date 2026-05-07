"""Settings smoke tests."""

from __future__ import annotations

from pathlib import Path

import pytest
from pydantic import ValidationError

from trading_on_tcbs_api.stock_system_v2.settings import RiskParams, Settings


def test_load_returns_frozen_settings(tmp_path: Path):
    s = Settings.load(base_dir=tmp_path)
    assert s.base_dir == tmp_path
    assert s.data_dir.exists()
    assert s.export_dir.exists()
    assert s.symbols  # non-empty default universe

    with pytest.raises((TypeError, ValidationError)):
        s.symbols = ("X",)  # frozen


def test_local_config_overrides_data_dirs(tmp_path: Path):
    cfg_dir = tmp_path / "config"
    cfg_dir.mkdir()
    custom_data = tmp_path / "elsewhere" / "stocks"
    custom_export = tmp_path / "elsewhere" / "exports"
    (cfg_dir / "local_config.json").write_text(
        f'{{"DATA_DIR": "{custom_data}", "EXPORT_DIR": "{custom_export}"}}'
    )
    s = Settings.load(base_dir=tmp_path)
    assert s.data_dir == custom_data
    assert s.export_dir == custom_export


def test_per_call_override_via_model_copy(tmp_path: Path):
    s = Settings.load(base_dir=tmp_path)
    s2 = s.model_copy(update={"symbols": ("AAA", "BBB")})
    assert s2.symbols == ("AAA", "BBB")
    assert s.symbols != s2.symbols  # original untouched


def test_risk_params_validate():
    with pytest.raises(ValidationError):
        RiskParams(max_capital_per_trade_pct=2.0)
    with pytest.raises(ValidationError):
        RiskParams(max_open_positions=0)
