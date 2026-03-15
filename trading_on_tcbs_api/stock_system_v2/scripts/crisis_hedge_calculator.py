"""
Crisis Delta Hedging Calculator
================================
Reads an Excel file with current delta positions and computes:
1. Per-stock hedging requirements using K-Factor formula at trigger levels (3%, 5%, 6.5%)
2. VN30 futures contracts needed when stocks lose liquidity
3. Unwind batching plan with ADV-based priority ordering (equal_count or equal_value mode)
4. Tracking table ready to print for live session use

Usage:
    python crisis_hedge_calculator.py <path_to_positions.xlsx> [--vn30f-price 1200] [--regime EXTREME]

Excel format expected:
    Ticker | Price | Beta | ADV | Delta_At_Trigger | Delta_Limit

    - Ticker: Mã cổ phiếu (VD: HPG, VNM)
    - Price: Giá hiện tại (VND)
    - Beta: Beta so với VN30 Index
    - ADV: Average Daily Volume (đơn vị: tỷ VND)
    - Delta_At_Trigger: Delta exposure (số CP) tại giá hiện tại
    - Delta_Limit: Delta exposure (số CP) nếu cổ phiếu hit sàn/trần (±7%)

    Lưu ý:
    - DeltaCash sẽ được tính tự động = Price × Delta_At_Trigger
    - DeltaCash_Limit = Price × Delta_Limit (dùng cho futures hedge)
    - Không cần truyền DeltaShare — đã thay bằng Delta_At_Trigger và Delta_Limit
"""

import argparse
import math
import sys
from dataclasses import dataclass
from enum import Enum
from pathlib import Path

import pandas as pd


# =============================================================================
# Constants
# =============================================================================

VN30F_MULTIPLIER = 100_000  # 1 point = 100,000 VND
HOSE_LIMIT_PCT = 7.0  # ±7% daily price limit

# K-Factor: hệ số "sợ sàn" (Liquidity Insurance)
# Hedge = Delta_At_Trigger + K * (Delta_Limit - Delta_At_Trigger)
# K=0: chỉ hedge đúng delta neutral tại trigger
# K=0.3: bán thêm 30% khoảng cách đến sàn để "mua bảo hiểm"
K_FACTOR = 0.3

# Trigger levels (% move in session)
# Tại 3%: K-factor có giới hạn max 50% Delta_Limit (thị trường vẫn có thể hồi)
# Tại 5%: K-factor KHÔNG giới hạn (rủi ro sàn quá cao)
# Tại 6.5%: chuẩn bị futures
TRIGGER_LEVELS = [
    (3.0, True, "K-Factor hedge (max 50% Delta_Limit)"),
    (5.0, False, "K-Factor hedge (không giới hạn)"),
    (6.5, False, "K-Factor hedge + chuẩn bị futures + đặt ATC"),
]

# Crisis beta multiplier (correlations increase in stress)
CRISIS_BETA_MULTIPLIER = 1.15

# Giới hạn max hedge tại trigger đầu tiên (3%)
# 0.5 = không hedge quá 50% Delta_Limit khi thị trường mới giảm 3%
EARLY_TRIGGER_CAP = 0.5

# Trọng số priority khi unwind (tổng phải = 1.0)
UNWIND_WEIGHT_ADV = 0.4       # Thanh khoản → close trước
UNWIND_WEIGHT_DELTA = 0.3     # Delta lớn → giảm rủi ro nhanh
UNWIND_WEIGHT_VN30 = 0.2      # VN30 → correlation cao với futures
UNWIND_WEIGHT_BETA = 0.1      # Higher beta → more correlated

# Lot size và ngưỡng tối thiểu
LOT_SIZE = 100                # 1 lot = 100 CP trên HOSE
MIN_SHARES_THRESHOLD = 50     # Dưới 50 CP thì bỏ qua (không đủ nửa lot)

# Số batch mặc định và time windows
DEFAULT_NUM_BATCHES = 4
BATCH_TIME_WINDOWS = {
    1: "09:30 - 10:30",
    2: "10:30 - 11:30",
    3: "13:00 - 13:30",
    4: "13:30 - 14:15",
}


class Regime(Enum):
    NORMAL = "NORMAL"
    ELEVATED = "ELEVATED"
    EXTREME = "EXTREME"


@dataclass
class FuturesHedge:
    """Result of futures hedge calculation."""
    unhedged_delta_vnd: float
    weighted_beta: float
    adjusted_beta: float  # after crisis multiplier
    vn30f_price: float
    contracts_exact: float
    contracts_rounded: int  # always round AWAY from zero (over-hedge)
    notional_per_contract: float


# =============================================================================
# Utility Functions
# =============================================================================

def round_to_lot(shares: float) -> int:
    """
    Làm tròn lên bội số 100 cổ phiếu, giữ nguyên dấu.
    Dùng half round up: 150 → 200, 149 → 100, -150 → -200.

    Logic:
    - Chia cho 100, round half up, nhân lại 100
    - math.floor(x + 0.5) là half round up cho số dương
    - Giữ nguyên dấu
    """
    if abs(shares) < MIN_SHARES_THRESHOLD:
        return 0
    sign = 1 if shares >= 0 else -1
    abs_shares = abs(shares)
    lots = abs_shares / LOT_SIZE
    rounded_lots = math.floor(lots + 0.5)  # half round up
    return sign * rounded_lots * LOT_SIZE


# =============================================================================
# Core Functions
# =============================================================================

def load_positions(filepath: str) -> pd.DataFrame:
    """
    Load position data from Excel file.

    Required columns: Ticker, Price, Beta, ADV, Delta_At_Trigger, Delta_Limit

    - ADV: đơn vị tỷ VND (ít số 0, dễ đọc)
    - Delta_At_Trigger: delta (số CP) tại giá hiện tại
    - Delta_Limit: delta (số CP) nếu CP hit sàn/trần (±7%)
    - DeltaCash tự tính = Price × Delta_At_Trigger
    """
    path = Path(filepath)
    if not path.exists():
        raise FileNotFoundError(f"File not found: {filepath}")

    df = pd.read_excel(filepath, engine="openpyxl")

    # Normalize column names (strip whitespace)
    df.columns = df.columns.str.strip()

    # Validate required columns
    required = {"Ticker", "Price", "Beta", "ADV", "Delta_At_Trigger", "Delta_Limit"}
    found = set(df.columns)
    missing = required - found
    if missing:
        raise ValueError(
            f"Missing columns: {missing}. "
            f"Required: Ticker, Price, Beta, ADV, Delta_At_Trigger, Delta_Limit"
        )

    # Compute DeltaCash = Price × Delta_At_Trigger (VND exposure tại giá hiện tại)
    df["DeltaCash"] = df["Price"] * df["Delta_At_Trigger"]

    # DeltaCash tại limit (dùng cho futures hedge sizing)
    df["DeltaCash_Limit"] = df["Price"] * df["Delta_Limit"]

    # Clean up
    df["Ticker"] = df["Ticker"].astype(str).str.strip().str.upper()
    df = df.dropna(subset=["Ticker", "Price", "Beta", "Delta_At_Trigger", "Delta_Limit"])

    return df


def compute_trigger_actions(df: pd.DataFrame, k_factor: float = K_FACTOR) -> pd.DataFrame:
    """
    Tính lượng hedge cần đặt tại mỗi trigger level, dùng công thức K-Factor.

    Công thức:
        K-Factor hedge = Delta_At_Trigger + K × (Delta_Limit − Delta_At_Trigger)

    Tại trigger 3% (có giới hạn):
        Hedge = min(50% × Delta_Limit, K-Factor hedge)

    Tại trigger ≥5% (không giới hạn):
        Hedge = K-Factor hedge

    Returns DataFrame with columns gốc + Hedge@3%, Hedge@5%, Hedge@6.5%
    Giá trị là số cổ phiếu cần mua/bán, đã làm tròn 100 CP (half round up).
    Dương = cần bán, Âm = cần mua (theo dấu của delta input).
    """
    result = df.copy()

    # K-Factor hedge (không giới hạn) — dùng chung cho tất cả trigger
    k_hedge = result["Delta_At_Trigger"] + k_factor * (result["Delta_Limit"] - result["Delta_At_Trigger"])

    for pct, has_cap, _ in TRIGGER_LEVELS:
        col_name = f"Hedge@{pct:.1f}%".replace(".0%", "%")

        if has_cap:
            # Tại 3%: có giới hạn max 50% Delta_Limit
            # min áp dụng trên giá trị tuyệt đối, giữ nguyên dấu
            cap = EARLY_TRIGGER_CAP * result["Delta_Limit"]
            # Dùng sign-aware min: lấy cái nào gần 0 hơn
            hedge = pd.Series([
                min(abs(k), abs(c)) * (1 if k >= 0 else -1)
                for k, c in zip(k_hedge, cap)
            ], index=result.index)
        else:
            # Tại ≥5%: không giới hạn
            hedge = k_hedge

        result[col_name] = hedge.apply(round_to_lot)

    return result


def compute_futures_hedge(
    df: pd.DataFrame,
    vn30f_price: float,
    unhedged_tickers: list[str] | None = None,
    regime: Regime = Regime.EXTREME,
) -> FuturesHedge:
    """
    Calculate the number of VN30 futures contracts needed to hedge
    unhedged delta exposure.

    Dùng DeltaCash_Limit (delta tại sàn/trần) vì khi chuyển sang futures,
    nghĩa là cổ phiếu đã mất thanh khoản tại limit.

    Parameters
    ----------
    df : DataFrame with position data
    vn30f_price : Current VN30 futures price (points, e.g. 1200)
    unhedged_tickers : List of tickers that lost liquidity (if None, use all)
    regime : Market regime (EXTREME applies crisis beta multiplier)

    Returns
    -------
    FuturesHedge with all calculation details
    """
    if unhedged_tickers:
        mask = df["Ticker"].isin([t.upper() for t in unhedged_tickers])
        subset = df[mask].copy()
    else:
        subset = df.copy()

    if subset.empty:
        return FuturesHedge(
            unhedged_delta_vnd=0, weighted_beta=0, adjusted_beta=0,
            vn30f_price=vn30f_price, contracts_exact=0, contracts_rounded=0,
            notional_per_contract=vn30f_price * VN30F_MULTIPLIER,
        )

    # Total unhedged delta in VND — dùng delta tại LIMIT vì đó là worst case
    total_delta_vnd = subset["DeltaCash_Limit"].sum()

    # Beta-weighted delta: Σ(|delta_i| × beta_i) / Σ(|delta_i|)
    # Use absolute values for weighting to avoid sign cancellation
    abs_delta = subset["DeltaCash_Limit"].abs()
    if abs_delta.sum() == 0:
        weighted_beta = 1.0
    else:
        weighted_beta = (subset["Beta"] * abs_delta).sum() / abs_delta.sum()

    # Apply crisis multiplier in EXTREME regime
    adjusted_beta = weighted_beta
    if regime == Regime.EXTREME:
        adjusted_beta *= CRISIS_BETA_MULTIPLIER

    # Number of contracts
    notional_per_contract = vn30f_price * VN30F_MULTIPLIER
    contracts_exact = (total_delta_vnd * adjusted_beta) / notional_per_contract

    # Always round AWAY from zero (over-hedge is safer in crisis)
    if contracts_exact >= 0:
        contracts_rounded = math.ceil(contracts_exact)
    else:
        contracts_rounded = math.floor(contracts_exact)

    return FuturesHedge(
        unhedged_delta_vnd=total_delta_vnd,
        weighted_beta=weighted_beta,
        adjusted_beta=adjusted_beta,
        vn30f_price=vn30f_price,
        contracts_exact=contracts_exact,
        contracts_rounded=contracts_rounded,
        notional_per_contract=notional_per_contract,
    )


def generate_unwind_plan(
    df: pd.DataFrame,
    vn30f_price: float,
    num_batches: int = DEFAULT_NUM_BATCHES,
    batch_mode: str = "equal_count",
) -> pd.DataFrame:
    """
    Generate a prioritized unwind plan with batch assignments.

    Priority logic (trọng số):
    1. ADV (40%) — Thanh khoản cao nhất → close trước, ít market impact
    2. Absolute DeltaCash (30%) — Exposure lớn nhất → giảm rủi ro nhanh
    3. VN30 membership (20%) — Correlation cao nhất với futures
    4. Beta (10%) — Beta cao → correlated mạnh hơn

    Batch modes:
    - "equal_count": Chia đều theo số lượng mã (mỗi batch ~25% số mã)
    - "equal_value": Chia đều theo GIÁ TRỊ (mỗi batch ~25% tổng |DeltaCash|)
      Vẫn sort theo priority trước, chỉ cắt batch theo giá trị tích lũy.

    Returns DataFrame sorted by priority with batch assignments.
    """
    VN30_TICKERS = {
        "ACB", "BCM", "BID", "BVH", "CTG", "FPT", "GAS", "GVR", "HDB", "HPG",
        "MBB", "MSN", "MWG", "PLX", "POW", "SAB", "SHB", "SSB", "SSI", "STB",
        "TCB", "TPB", "VCB", "VHM", "VIB", "VIC", "VJC", "VNM", "VPB", "VRE",
    }

    plan = df.copy()
    plan["AbsDeltaCash"] = plan["DeltaCash_Limit"].abs()
    plan["IsVN30"] = plan["Ticker"].isin(VN30_TICKERS).astype(int)

    # Normalize each factor to 0-1
    max_delta = plan["AbsDeltaCash"].max()
    plan["DeltaScore"] = plan["AbsDeltaCash"] / max_delta if max_delta > 0 else 0

    max_adv = plan["ADV"].max()
    plan["ADVScore"] = plan["ADV"] / max_adv if max_adv > 0 else 0

    # Priority score: higher = close first
    plan["PriorityScore"] = (
        plan["ADVScore"] * UNWIND_WEIGHT_ADV +
        plan["DeltaScore"] * UNWIND_WEIGHT_DELTA +
        plan["IsVN30"] * UNWIND_WEIGHT_VN30 +
        plan["Beta"].clip(0, 2) / 2 * UNWIND_WEIGHT_BETA
    )

    plan = plan.sort_values("PriorityScore", ascending=False).reset_index(drop=True)

    # --- Assign batches ---
    n = len(plan)
    if batch_mode == "equal_value":
        # Chia batch sao cho tổng |DeltaCash| mỗi batch tương đối đều
        # Vẫn giữ nguyên thứ tự priority (sorted ở trên)
        total_value = plan["AbsDeltaCash"].sum()
        target_per_batch = total_value / num_batches

        batch_labels = []
        current_batch = 1
        cumulative = 0.0

        for i, row in plan.iterrows():
            cumulative += row["AbsDeltaCash"]
            batch_labels.append(current_batch)

            # Chuyển sang batch mới nếu đã vượt target VÀ chưa phải batch cuối
            if cumulative >= target_per_batch and current_batch < num_batches:
                current_batch += 1
                cumulative = 0.0

        plan["Batch"] = batch_labels
    else:
        # equal_count: chia đều theo số lượng mã
        batch_size = math.ceil(n / num_batches)
        plan["Batch"] = [(i // batch_size) + 1 for i in range(n)]
        plan["Batch"] = plan["Batch"].clip(upper=num_batches)

    # Futures equivalent per stock (dùng DeltaCash_Limit × Beta / notional)
    notional = vn30f_price * VN30F_MULTIPLIER
    plan["FuturesEquiv"] = (plan["DeltaCash_Limit"] * plan["Beta"] / notional).round(1)

    # Batch time windows
    plan["TimeWindow"] = plan["Batch"].map(BATCH_TIME_WINDOWS)

    # Select display columns
    display_cols = [
        "Batch", "TimeWindow", "Ticker", "Price", "Delta_At_Trigger",
        "Delta_Limit", "ADV", "DeltaCash", "Beta", "FuturesEquiv", "IsVN30",
    ]

    return plan[display_cols]


def generate_quick_reference_table(vn30f_price: float) -> pd.DataFrame:
    """Generate futures quick reference table for given VN30F price."""
    notional = vn30f_price * VN30F_MULTIPLIER
    deltas = [0.5e9, 1e9, 2e9, 3e9, 5e9, 10e9]
    betas = [0.8, 1.0, 1.2, 1.5]

    rows = []
    for delta in deltas:
        row = {"Unhedged Delta (tỷ VND)": delta / 1e9}
        for beta in betas:
            contracts = math.ceil(abs(delta * beta / notional))
            row[f"β={beta}"] = contracts
        rows.append(row)

    return pd.DataFrame(rows)


# =============================================================================
# Report Generation
# =============================================================================

def print_full_report(
    filepath: str,
    vn30f_price: float,
    regime: Regime,
    unhedged_tickers: list[str] | None = None,
    batch_mode: str = "equal_count",
):
    """
    Generate and print the complete hedging analysis report.
    This is the main entry point for interactive use.
    """
    # Load data
    df = load_positions(filepath)
    print(f"\n{'='*80}")
    print(f"🚨 CRISIS DELTA HEDGING CALCULATOR (K-Factor = {K_FACTOR})")
    print(f"{'='*80}")
    print(f"  File:         {filepath}")
    print(f"  Regime:       {regime.value}")
    print(f"  VN30F:        {vn30f_price:,.0f} points")
    print(f"  Stocks:       {len(df)}")
    print(f"  Batch mode:   {batch_mode}")
    print(f"  Total ΔCash:  {df['DeltaCash'].sum():,.0f} VND  (tại trigger)")
    print(f"  Total ΔLimit: {df['DeltaCash_Limit'].sum():,.0f} VND  (tại sàn/trần)")
    print(f"{'='*80}\n")

    # ── SECTION 1: Trigger actions ──────────────────────────────────────
    print("┌─────────────────────────────────────────────────────┐")
    print("│  SECTION 1: INTRADAY TRIGGER ACTIONS (K-Factor)     │")
    print("└─────────────────────────────────────────────────────┘\n")

    triggers = compute_trigger_actions(df)
    trigger_cols = ["Ticker", "Price", "ADV", "Delta_At_Trigger", "Delta_Limit", "Beta"]
    trigger_cols += [f"Hedge@{pct:.1f}%".replace(".0%", "%") for pct, _, _ in TRIGGER_LEVELS]
    print(triggers[trigger_cols].to_string(index=False))

    # Sum row
    print("\n" + "-" * 80)
    for pct, has_cap, desc in TRIGGER_LEVELS:
        col = f"Hedge@{pct:.1f}%".replace(".0%", "%")
        total = triggers[col].sum()
        total_cash = (triggers[col] * triggers["Price"]).sum()
        cap_note = " (max 50% Limit)" if has_cap else ""
        print(f"  @{pct}%: Total shares = {total:+,.0f}  |  "
              f"Total VND = {total_cash:+,.0f}  |  {desc}")

    print(f"\n  K-Factor = {K_FACTOR}  |  Round: half-round-up to 100 CP")

    # ── SECTION 2: Futures hedge ────────────────────────────────────────
    print(f"\n┌─────────────────────────────────────────────────────┐")
    print(f"│  SECTION 2: VN30 FUTURES HEDGE CALCULATION          │")
    print(f"└─────────────────────────────────────────────────────┘\n")

    hedge = compute_futures_hedge(df, vn30f_price, unhedged_tickers, regime)

    label = "ALL STOCKS" if not unhedged_tickers else ", ".join(unhedged_tickers)
    print(f"  Scope:                 {label}")
    print(f"  Unhedged Δ (VND):      {hedge.unhedged_delta_vnd:+,.0f}  (tại limit)")
    print(f"  Weighted Beta:         {hedge.weighted_beta:.3f}")
    if regime == Regime.EXTREME:
        print(f"  Crisis-Adj Beta:       {hedge.adjusted_beta:.3f}  "
              f"(×{CRISIS_BETA_MULTIPLIER})")
    print(f"  VN30F Price:           {hedge.vn30f_price:,.0f}")
    print(f"  Notional/contract:     {hedge.notional_per_contract:,.0f} VND")
    print(f"  Contracts (exact):     {hedge.contracts_exact:+.2f}")
    print(f"  ►► CONTRACTS NEEDED:   {hedge.contracts_rounded:+d}  "
          f"{'SHORT ⬇️' if hedge.contracts_rounded < 0 else 'LONG ⬆️' if hedge.contracts_rounded > 0 else 'NONE'}")

    # Quick reference
    print(f"\n  Quick reference (VN30F @ {vn30f_price:,.0f}):")
    qr = generate_quick_reference_table(vn30f_price)
    print("  " + qr.to_string(index=False).replace("\n", "\n  "))

    # ── SECTION 3: Unwind plan ──────────────────────────────────────────
    mode_label = "EQUAL VALUE" if batch_mode == "equal_value" else "EQUAL COUNT"
    print(f"\n┌─────────────────────────────────────────────────────┐")
    print(f"│  SECTION 3: UNWIND PLAN — {mode_label:<24s}│")
    print(f"└─────────────────────────────────────────────────────┘\n")
    print(f"  Priority weights: ADV 40% + Delta 30% + VN30 20% + Beta 10%\n")

    unwind = generate_unwind_plan(df, vn30f_price, batch_mode=batch_mode)
    for batch_num in sorted(unwind["Batch"].unique()):
        batch = unwind[unwind["Batch"] == batch_num]
        time_window = batch["TimeWindow"].iloc[0]
        batch_delta = batch["DeltaCash"].sum()
        batch_futures = batch["FuturesEquiv"].sum()
        batch_adv = batch["ADV"].sum()

        print(f"  ═══ BATCH {batch_num} ({time_window}) ═══")
        print(f"  Total ΔCash: {batch_delta:+,.0f} VND  |  "
              f"Futures equiv: {batch_futures:+.1f} contracts  |  "
              f"ADV: {batch_adv:,.1f} tỷ")
        display = batch[["Ticker", "Price", "Delta_At_Trigger", "Delta_Limit",
                         "ADV", "DeltaCash", "Beta", "FuturesEquiv", "IsVN30"]]
        print("  " + display.to_string(index=False).replace("\n", "\n  "))
        print()

    # Summary
    total_futures = unwind["FuturesEquiv"].sum()
    print("-" * 80)
    print(f"  TỔNG SỐ HĐ FUTURES CẦN ĐÓNG KHI UNWIND: {total_futures:+.1f}")
    print("-" * 80)

    # ── SECTION 4: Action checklist ─────────────────────────────────────
    print(f"\n┌─────────────────────────────────────────────────────┐")
    print(f"│  SECTION 4: ACTION CHECKLIST                        │")
    print(f"└─────────────────────────────────────────────────────┘\n")

    if hedge.contracts_rounded < 0:
        action = "SHORT"
    elif hedge.contracts_rounded > 0:
        action = "LONG"
    else:
        action = "KHÔNG CẦN"

    print(f"  ☐ Regime hiện tại: {regime.value}")
    print(f"  ☐ Tổng delta chưa hedge: {hedge.unhedged_delta_vnd:+,.0f} VND")
    print(f"  ☐ → Cần {action} {abs(hedge.contracts_rounded)} HĐ VN30F1M @{vn30f_price:,.0f}")
    print(f"  ☐ Sau khi vào lệnh: GHI CHÉP thời gian, giá, lý do")
    print(f"  ☐ Ngày hôm sau: Follow unwind plan (4 batches, mode={batch_mode})")
    print(f"  ☐ Close CỔ PHIẾU + FUTURES song song, không close 1 bên trước")
    print()

    return {
        "positions": df,
        "triggers": triggers,
        "futures_hedge": hedge,
        "unwind_plan": unwind,
    }


# =============================================================================
# Export to Excel (for live session tracking)
# =============================================================================

def export_tracking_sheet(
    filepath: str,
    output_path: str,
    vn30f_price: float,
    regime: Regime = Regime.EXTREME,
    batch_mode: str = "equal_count",
):
    """
    Export a ready-to-print tracking sheet as Excel file.
    Use this the night before the unwind session.
    """
    df = load_positions(filepath)
    unwind = generate_unwind_plan(df, vn30f_price, batch_mode=batch_mode)

    # Add tracking columns (to fill in during session)
    unwind["TargetPrice"] = ""
    unwind["Status"] = ""  # Pending / Filled / ATC / Failed
    unwind["FillPrice"] = ""
    unwind["FillTime"] = ""
    unwind["FuturesClosed"] = ""  # Yes / No

    output = Path(output_path)
    with pd.ExcelWriter(output, engine="openpyxl") as writer:
        unwind.to_excel(writer, sheet_name="Unwind Plan", index=False)

        # Also add the original positions
        df.to_excel(writer, sheet_name="Positions", index=False)

        # Quick reference
        qr = generate_quick_reference_table(vn30f_price)
        qr.to_excel(writer, sheet_name="Futures Quick Ref", index=False)

    print(f"✅ Tracking sheet exported to: {output}")
    return output


# =============================================================================
# CLI
# =============================================================================

def main():
    parser = argparse.ArgumentParser(
        description="Crisis Delta Hedging Calculator",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Full report with all stocks (equal count batching)
  python crisis_hedge_calculator.py positions.xlsx --vn30f-price 1200

  # Equal value batching (mỗi batch ~25% tổng giá trị)
  python crisis_hedge_calculator.py positions.xlsx --vn30f-price 1200 --batch-mode equal_value

  # EXTREME regime, specific tickers lost liquidity
  python crisis_hedge_calculator.py positions.xlsx --vn30f-price 1200 \\
      --regime EXTREME --unhedged HPG,VNM,FPT,VCB

  # Export tracking sheet for tomorrow's unwind session
  python crisis_hedge_calculator.py positions.xlsx --vn30f-price 1200 \\
      --export-tracking unwind_tracking.xlsx
        """,
    )
    parser.add_argument("filepath", help="Path to positions Excel file")
    parser.add_argument(
        "--vn30f-price", type=float, default=1200,
        help="Current VN30 futures price in points (default: 1200)",
    )
    parser.add_argument(
        "--regime", type=str, default="EXTREME",
        choices=["NORMAL", "ELEVATED", "EXTREME"],
        help="Market regime (default: EXTREME)",
    )
    parser.add_argument(
        "--unhedged", type=str, default=None,
        help="Comma-separated list of tickers that lost liquidity "
             "(default: all stocks)",
    )
    parser.add_argument(
        "--batch-mode", type=str, default="equal_count",
        choices=["equal_count", "equal_value"],
        help="Unwind batch mode: equal_count (by # of stocks) or "
             "equal_value (by DeltaCash value). Default: equal_count",
    )
    parser.add_argument(
        "--export-tracking", type=str, default=None,
        help="Export tracking sheet to this Excel file path",
    )

    args = parser.parse_args()
    regime = Regime(args.regime)
    unhedged = args.unhedged.split(",") if args.unhedged else None

    # Print full report
    result = print_full_report(
        args.filepath, args.vn30f_price, regime, unhedged, args.batch_mode,
    )

    # Export tracking sheet if requested
    if args.export_tracking:
        export_tracking_sheet(
            args.filepath, args.export_tracking, args.vn30f_price, regime,
            args.batch_mode,
        )

    return result


if __name__ == "__main__":
    # =====================================================================
    # PYCHARM INTERACTIVE MODE
    # =====================================================================
    # Khi chạy bằng nút ▶️ Run trong PyCharm (không có CLI args),
    # sửa các dòng config bên dưới rồi nhấn Run.
    # Kết quả sẽ hiện trong cửa sổ Variables (SciView).
    # =====================================================================

    if len(sys.argv) <= 1:
        # ── CONFIG: Sửa các dòng này ────────────────────────────────────
        POSITIONS_FILE = "/tmp/sample_positions.xlsx"  # ← Đổi thành file Excel thật
        VN30F_PRICE = 1840                              # ← Giá VN30F hiện tại
        MARKET_REGIME = Regime.ELEVATED                  # ← NORMAL / ELEVATED / EXTREME
        UNHEDGED_TICKERS = None                         # ← None = tất cả, hoặc ["HPG","VNM",...]
        BATCH_MODE = "equal_value"                      # ← "equal_count" hoặc "equal_value"
        # ─────────────────────────────────────────────────────────────────

        result = print_full_report(
            POSITIONS_FILE, VN30F_PRICE, MARKET_REGIME, UNHEDGED_TICKERS, BATCH_MODE,
        )

        # Export to globals → hiện trong PyCharm Variables window
        df_positions = result["positions"]
        df_triggers = result["triggers"]
        df_unwind = result["unwind_plan"]
        futures_hedge = result["futures_hedge"]
        df_quick_ref = generate_quick_reference_table(VN30F_PRICE)

        print("\n✅ Exported to PyCharm Variables:")
        print("   • df_positions  — Bảng vị thế gốc")
        print("   • df_triggers   — Lượng hedge ở mỗi trigger (3%, 5%, 6.5%)")
        print("   • df_unwind     — Kế hoạch unwind chia batch")
        print("   • futures_hedge — Kết quả tính futures (dataclass)")
        print("   • df_quick_ref  — Bảng tra nhanh số HĐ futures")
    else:
        result = main()
