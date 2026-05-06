
import asyncio
import json
import os
import yaml
from pathlib import Path
from datetime import datetime

from trading_on_tcbs_api.stock_system_v2.auth.auth import StockAuth
from trading_on_tcbs_api.stock_system_v2.core.stock_api_client import StockTradingClient
from trading_on_tcbs_api.stock_system_v2 import config


# ─── Formatting helpers ───────────────────────────────────────────────────────

def vnd(value, default=0):
    try:
        v = float(value) if value is not None else default
        return f"{v:>18,.0f} VND"
    except (TypeError, ValueError):
        return f"{'N/A':>18}"


def pct(value):
    try:
        return f"{float(value):+.2f}%"
    except (TypeError, ValueError):
        return "N/A"


def divider(char="-", width=70):
    print("  " + char * width)


def section(title):
    print()
    print("  " + "=" * 70)
    print(f"  {title}")
    print("  " + "=" * 70)


def row(label, value, indent=4):
    print(f"  {' ' * indent}{label:<30} {value}")


# ─── Display functions ────────────────────────────────────────────────────────

def show_cash(data):
    if not data:
        print("    No cash data returned.")
        return

    # Normalise: API may return a list of cash entries
    entries = data if isinstance(data, list) else [data]

    fields = [
        ("cashBalance",         "Cash Balance"),
        ("availableBalance",    "Available Balance"),
        ("withdrawableBalance", "Withdrawable"),
        ("purchasingPower",     "Purchasing Power"),
        ("totalAssets",         "Total Assets"),
        ("nav",                 "NAV"),
        ("marginBalance",       "Margin Balance"),
        ("debtBalance",         "Debt Balance"),
        ("t0",                  "Receivable T+0"),
        ("t1",                  "Receivable T+1"),
        ("t2",                  "Receivable T+2"),
    ]

    for entry in entries:
        if not isinstance(entry, dict):
            print(f"    {entry}")
            continue
        label_prefix = entry.get("cashType", entry.get("type", ""))
        prefix = f"[{label_prefix}] " if label_prefix else ""
        found = False
        for key, label in fields:
            if key in entry and entry[key] not in (None, 0, ""):
                row(prefix + label, vnd(entry[key]))
                found = True
        if not found:
            for k, v in entry.items():
                if isinstance(v, (int, float)) and v != 0:
                    row(prefix + k, vnd(v))


def _extract_list(data):
    """Find the first list inside a dict response, trying common TCBS key names first."""
    if isinstance(data, list):
        return data
    if not isinstance(data, dict):
        return []
    priority_keys = ["data", "portfolios", "items", "equities", "positions",
                     "stockPortfolios", "equityItems", "stocks", "assets"]
    for key in priority_keys:
        if isinstance(data.get(key), list):
            return data[key]
    # Fallback: first list value found
    for v in data.values():
        if isinstance(v, list):
            return v
    return []


def _pick(item, *keys, default=0):
    """Return the value of the first key that EXISTS in the dict (even if 0)."""
    for k in keys:
        if k in item:
            return item[k]
    return default


def show_positions(data):
    items = _extract_list(data)
    if not items:
        print("    No positions held.")
        print(f"    [debug] raw response type={type(data).__name__}  value={data}")
        return

    hdr = f"  {'Symbol':<10}  {'Volume':>10}  {'Avail':>10}  {'Avg Cost':>12}  {'Mkt Price':>12}  {'Mkt Value':>16}  {'P&L':>16}  {'P&L%':>7}"
    print(hdr)
    divider()

    total_value = 0.0
    total_pnl   = 0.0

    for item in items:
        sym   = item.get("symbol", "?")
        vol   = float(item.get("totalQtty", 0) or 0)
        avail = float(item.get("availableTrading", 0) or 0)
        avg   = float(item.get("costPrice", 0) or 0)
        mkt   = float(item.get("currentPrice", 0) or 0)
        val   = vol * mkt
        pnl_v = (mkt - avg) * vol
        pnl_p = ((mkt - avg) / avg * 100) if avg else 0

        total_value += val
        total_pnl   += pnl_v

        print(
            f"  {sym:<10}  {int(vol):>10,}  {int(avail):>10,}  {avg:>12,.0f}  {mkt:>12,.0f}"
            f"  {val:>16,.0f}  {pnl_v:>16,.0f}  {pct(pnl_p):>7}"
        )

    divider()
    print(
        f"  {'TOTAL':<10}  {'':>10}  {'':>10}  {'':>12}  {'':>12}"
        f"  {total_value:>16,.0f}  {total_pnl:>16,.0f}"
    )


def show_buying_power(data):
    if not data:
        print("    No data returned.")
        return

    entries = data if isinstance(data, list) else [data]
    fields = [
        ("purchasingPower",  "Purchasing Power"),
        ("buyingPower",      "Buying Power"),
        ("maxBuyingPower",   "Max Buying Power"),
        ("pp",               "PP"),
        ("ppSe",             "PP (SE)"),
        ("margin",           "Margin Available"),
        ("maxMargin",        "Max Margin"),
    ]
    for entry in entries:
        if not isinstance(entry, dict):
            print(f"    {entry}")
            continue
        found = False
        for key, label in fields:
            if key in entry and entry[key] not in (None, 0, ""):
                row(label, vnd(entry[key]))
                found = True
        if not found:
            for k, v in entry.items():
                if isinstance(v, (int, float)) and v != 0:
                    row(k, vnd(v))


# ─── Module-level results (visible in PyCharm variable pane) ─────────────────
# After running, inspect these directly in the Variables panel.
import pandas as pd

raw_cash      = {}           # {account_id: raw API response}
raw_positions = {}           # {account_id: raw API response}
raw_power     = {}           # {account_id: raw API response}
df_positions  = pd.DataFrame()  # combined positions table across all accounts


# ─── Main ─────────────────────────────────────────────────────────────────────

async def fetch_real_assets():
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    print()
    print("  " + "█" * 70)
    print(f"  {'TCBS REAL PORTFOLIO  —  ' + now:^70}")
    print("  " + "█" * 70)

    # Auth
    auth = StockAuth()
    if not auth.validate():
        print("\n  Authentication failed. Please refresh your token.")
        return

    # Load credentials from YAML directly
    try:
        with open(config.CREDENTIALS_FILE, "r") as f:
            creds_raw = yaml.safe_load(f)
        tcbs = creds_raw.get("tcbs_api", {})
    except Exception as e:
        print(f"\n  Cannot load credentials: {e}")
        return

    normal_acc  = tcbs.get("normal_sub_account_id")
    margin_acc  = tcbs.get("margin_sub_account_id")
    futures_acc = tcbs.get("futures_sub_account_id")

    # Fix the global config_manager's path before StockTradingClient.__init__ calls it
    from trading_on_tcbs_api.utils.config_manager import get_config_manager
    _cm = get_config_manager()
    _cm.config_dir = Path(config.CREDENTIALS_FILE).parent
    _cm._credentials = None  # clear cache so it reloads from the absolute path

    # Build client
    client = StockTradingClient(token_file=config.TOKEN_FILE)
    client.token = auth.token

    accounts = []
    if normal_acc:
        accounts.append({"id": normal_acc,  "label": "Normal Account"})
    if margin_acc:
        accounts.append({"id": margin_acc,  "label": "Margin Account"})

    global raw_cash, raw_positions, raw_power, df_positions
    all_position_rows = []

    # ── Stock accounts ────────────────────────────────────────────────────────
    for acc in accounts:
        acc_id = acc["id"]
        label  = acc["label"]
        client.account_no = acc_id

        section(f"{label}  [{acc_id}]")

        # Cash
        print("\n    Cash & Balances")
        divider()
        cash = await client.get_cash_balance()
        raw_cash[acc_id] = cash
        show_cash(cash)

        # Positions
        print("\n    Stock Positions")
        divider()
        positions = await client.get_stock_positions()
        raw_positions[acc_id] = positions
        show_positions(positions)

        # Build DataFrame rows for this account
        for item in _extract_list(positions):
            vol   = float(item.get("totalQtty", 0) or 0)
            avg   = float(item.get("costPrice", 0) or 0)
            mkt   = float(item.get("currentPrice", 0) or 0)
            val   = vol * mkt
            pnl_v = (mkt - avg) * vol
            pnl_p = ((mkt - avg) / avg * 100) if avg else 0
            all_position_rows.append({
                "account":       label,
                "symbol":        item.get("symbol", "?"),
                "volume":        int(vol),
                "avail":         int(float(item.get("availableTrading", 0) or 0)),
                "avg_cost":      avg,
                "market_price":  mkt,
                "market_value":  val,
                "pnl":           pnl_v,
                "pnl_pct":       round(pnl_p, 2),
                **{k: item[k] for k in item if k not in
                   ("symbol", "totalQtty", "availableTrading", "costPrice", "currentPrice")},
            })

        # Buying power
        print("\n    Buying Power")
        divider()
        power = await client.get_buying_power()
        raw_power[acc_id] = power
        show_buying_power(power)

    # ── Futures account ───────────────────────────────────────────────────────
    if futures_acc:
        client.account_no = futures_acc
        section(f"Futures Account  [{futures_acc}]")

        print("\n    Cash & Balances")
        divider()
        cash = await client.get_cash_balance()
        raw_cash[futures_acc] = cash
        show_cash(cash)

    # Assemble combined DataFrame — visible in PyCharm Variables panel as df_positions
    if all_position_rows:
        df_positions = pd.DataFrame(all_position_rows).set_index("symbol")
        df_positions.index.name = "symbol"

    print()
    print("  " + "═" * 70)
    print()


if __name__ == "__main__":
    asyncio.run(fetch_real_assets())
