import datetime
from trading_on_tcbs_api.stock_system_v2 import config

class TradeManager:
    """
    Manages trade execution and position tracking.
    Currently implements PAPER TRADING (simulation).
    """
    def __init__(self, auth):
        self.auth = auth
        self.positions = {}  # Symbol -> {quantity, avg_price}
        self.cash = 100_000_000  # Virtual 100M VND starting capital
        
    def execute(self, opportunity):
        """
        Execute a trade based on the opportunity logic.
        """
        symbol = opportunity['symbol']
        signal = opportunity['signal']
        price = opportunity['price']
        reason = opportunity['reason']
        
        if signal == "BUY":
            self._buy(symbol, price, reason)
        elif signal == "SELL":
            self._sell(symbol, price, reason)
            
    def _buy(self, symbol, price, reason):
        if symbol in self.positions:
            print(f"[Trader] Already hold {symbol}, skipping buy.")
            return
            
        # Calculate size based on risk
        max_trade_val = self.cash * config.RISK_PARAMS["max_capital_per_trade_pct"]
        quantity = int(max_trade_val // price)
        
        if quantity < 100: # Minimum lot size usually 100
             print(f"[Trader] Insufficient capital for {symbol} (Need {price*100:,.0f}, have {max_trade_val:,.0f})")
             return
             
        cost = quantity * price
        self.cash -= cost
        self.positions[symbol] = {
            "quantity": quantity,
            "avg_price": price,
            "time": datetime.datetime.now()
        }
        
        print(f"✅ [BUY] {symbol} | Qty: {quantity} | Price: {price:,.0f} | Cost: {cost:,.0f} | Reason: {reason}")
        print(f"   [Balance] Cash: {self.cash:,.0f} | Positions: {list(self.positions.keys())}")

    def _sell(self, symbol, price, reason):
        if symbol not in self.positions:
            return
            
        pos = self.positions[symbol]
        qty = pos['quantity']
        avg_price = pos['avg_price']
        
        revenue = qty * price
        profit = revenue - (qty * avg_price)
        pct = profit / (qty * avg_price)
        
        self.cash += revenue
        del self.positions[symbol]
        
        print(f"🔻 [SELL] {symbol} | Qty: {qty} | Price: {price:,.0f} | PnL: {profit:,.0f} ({pct:.2%}) | Reason: {reason}")
