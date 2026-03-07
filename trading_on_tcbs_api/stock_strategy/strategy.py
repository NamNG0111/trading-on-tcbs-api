"""
Stock trading strategy framework with technical indicators
"""
import asyncio
import numpy as np
import pandas as pd
from typing import Dict, List, Optional, Any, Tuple
from datetime import datetime, timedelta
from dataclasses import dataclass

from .stock_api_client import StockTradingClient, StockAPIClient
from .data_manager import HistoricalDataManager, RealTimeDataIntegrator
from ..indicators.base import BaseIndicator, Signal, SignalType, IndicatorRegistry
from ..indicators.signal_generator import SignalGenerator, SignalRule, CombinationLogic, CommonSignalRules
from ..indicators.technical_indicators import TechnicalIndicators
from ..utils.config_manager import ConfigManager
from ..logger_utils.fast_logger import get_logger
from ..utils.common import is_within_time_range


@dataclass
class TradingConfig:
    """Configuration for stock trading strategy - values loaded from YAML config"""
    symbols: List[str]
    max_position_per_symbol: int
    max_portfolio_value: float
    risk_per_trade: float
    stop_loss_pct: float
    take_profit_pct: float
    min_signal_strength: float
    trading_hours: Tuple[Tuple[int, int], Tuple[int, int]]
    data_update_interval: int
    use_talib: bool


class StockTradingStrategy:
    """Main stock trading strategy with technical indicators"""
    
    def __init__(self, config: TradingConfig):
        self.config = config
        self.client = StockTradingClient()
        self.historical_manager = HistoricalDataManager()
        self.realtime_integrator = RealTimeDataIntegrator(self.historical_manager)
        self.signal_generator = SignalGenerator()
        self.logger = get_logger('stock_strategy', 'Stock Strategy')
        
        # Trading state
        self.active_positions: Dict[str, Dict] = {}
        self.pending_orders: Dict[str, str] = {}  # symbol -> order_id
        self.last_signals: Dict[str, List[Signal]] = {}
        self.last_update: datetime = datetime.now()
        
        # Control flags
        self.is_running = False
        self.stop_event = asyncio.Event()
        
    async def initialize(self, account_no: str = None):
        """Initialize the trading strategy"""
        try:
            # Initialize API client
            await self.client.initialize_stock_trading(account_no)
            
            # Setup indicators based on configuration
            await self._setup_indicators()
            
            # Setup signal generation rules
            await self._setup_signal_rules()
            
            # Preload historical data
            await self.historical_manager.preload_data(
                self.config.symbols, 
                periods=100  # Load 100 periods for indicators
            )
            
            # Load current positions
            await self._load_current_positions()
            
            await self.logger.log("Stock trading strategy initialized successfully")
            
        except Exception as e:
            await self.logger.log_error(f"Error initializing strategy: {e}")
            raise
    
    async def _setup_indicators(self):
        """Setup technical indicators"""
        try:
            # Try to use TA-Lib indicators first, fallback to custom
            if self.config.use_talib:
                try:
                    self.signal_generator.add_indicator("RSI", RSI(period=14, oversold=30, overbought=70))
                    self.signal_generator.add_indicator("SMA", SMA(period=20))
                    self.signal_generator.add_indicator("EMA", EMA(period=20))
                    self.signal_generator.add_indicator("MACD", MACD())
                    await self.logger.log("Using TA-Lib indicators")
                except ImportError:
                    await self.logger.log("TA-Lib not available, using custom indicators")
                    self._setup_custom_indicators()
            else:
                self._setup_custom_indicators()
                
        except Exception as e:
            await self.logger.log_error(f"Error setting up indicators: {e}")
            # Fallback to custom indicators
            self._setup_custom_indicators()
    
    def _setup_custom_indicators(self):
        """Setup custom indicators as fallback"""
        self.signal_generator.add_indicator("RSI", CustomRSI(period=14, oversold=30, overbought=70))
        self.signal_generator.add_indicator("SMA", CustomSMA(period=20))
        self.signal_generator.add_indicator("EMA", CustomEMA(period=20))
    
    async def _setup_signal_rules(self):
        """Setup signal generation rules"""
        # RSI oversold/overbought rule
        rsi_rule = CommonSignalRules.rsi_oversold_overbought()
        self.signal_generator.add_rule(rsi_rule)
        
        # RSI + MA combination rule
        combo_rule = CommonSignalRules.rsi_ma_combo()
        self.signal_generator.add_rule(combo_rule)
        
        # Custom rule: Strong buy when RSI < 30 AND price > MA20
        strong_buy_rule = SignalRule(
            name="STRONG_BUY_RSI_MA",
            indicators=["RSI", "SMA"],
            conditions={
                "RSI": {
                    "signal_type": SignalType.BUY,
                    "min_strength": 0.5,
                    "value_conditions": {"lte": 30}
                },
                "SMA": {
                    "signal_type": SignalType.BUY,
                    "min_strength": 0.3
                }
            },
            logic=CombinationLogic.AND,
            min_strength=0.6
        )
        self.signal_generator.add_rule(strong_buy_rule)
        
        await self.logger.log("Signal generation rules configured")
    
    async def _load_current_positions(self):
        """Load current positions from API"""
        try:
            positions = await self.client.get_stock_positions()
            
            for position in positions:
                symbol = position.get('symbol')
                if symbol in self.config.symbols:
                    self.active_positions[symbol] = {
                        'quantity': position.get('quantity', 0),
                        'avg_price': position.get('avgPrice', 0),
                        'market_value': position.get('marketValue', 0),
                        'unrealized_pnl': position.get('unrealizedPnL', 0),
                        'entry_time': datetime.now()  # Approximate, real system would track this
                    }
            
            await self.logger.log(f"Loaded {len(self.active_positions)} active positions")
            
        except Exception as e:
            await self.logger.log_error(f"Error loading positions: {e}")
    
    async def start_trading(self):
        """Start the trading strategy"""
        if self.is_running:
            await self.logger.log("Strategy is already running")
            return
        
        self.is_running = True
        self.stop_event.clear()
        
        await self.logger.log("Starting stock trading strategy")
        
        # Start main trading loop
        trading_task = asyncio.create_task(self._trading_loop())
        
        # Start data update loop
        data_task = asyncio.create_task(self._data_update_loop())
        
        try:
            await asyncio.gather(trading_task, data_task)
        except Exception as e:
            await self.logger.log_error(f"Error in trading strategy: {e}")
        finally:
            self.is_running = False
    
    async def stop_trading(self):
        """Stop the trading strategy"""
        await self.logger.log("Stopping stock trading strategy")
        self.stop_event.set()
        self.is_running = False
        
        # Cancel all pending orders
        await self._cancel_all_pending_orders()
    
    async def _trading_loop(self):
        """Main trading loop"""
        while not self.stop_event.is_set():
            try:
                # Check if within trading hours
                if not self._is_trading_hours():
                    await asyncio.sleep(60)  # Check every minute
                    continue
                
                # Process each symbol
                for symbol in self.config.symbols:
                    await self._process_symbol(symbol)
                
                # Check existing positions for stop loss/take profit
                await self._check_position_management()
                
                # Wait before next iteration
                await asyncio.sleep(self.config.data_update_interval)
                
            except Exception as e:
                await self.logger.log_error(f"Error in trading loop: {e}")
                await asyncio.sleep(10)  # Short delay on error
    
    async def _data_update_loop(self):
        """Data update loop for real-time price integration"""
        while not self.stop_event.is_set():
            try:
                # In a real implementation, this would connect to WebSocket
                # For now, we'll simulate with periodic updates
                await asyncio.sleep(5)  # Update every 5 seconds
                
            except Exception as e:
                await self.logger.log_error(f"Error in data update loop: {e}")
                await asyncio.sleep(10)
    
    async def _process_symbol(self, symbol: str):
        """Process trading signals for a specific symbol"""
        try:
            # Get current price (in real implementation, from streaming data)
            current_price = self.realtime_integrator.get_current_price(symbol)
            if not current_price:
                # Fallback: get latest price from historical data
                close_prices = await self.historical_manager.get_close_prices(symbol, 1)
                if len(close_prices) > 0:
                    current_price = close_prices[-1]
                else:
                    return
            
            # Get data for indicators
            indicator_data = {}
            for indicator_name in self.signal_generator.indicators.keys():
                data = await self.realtime_integrator.get_indicator_data(
                    symbol, 
                    periods=50,  # Get enough data for indicators
                    include_current=True
                )
                indicator_data[indicator_name] = data
            
            # Generate signals
            signals = self.signal_generator.generate_signals(indicator_data, current_price)
            
            if signals:
                self.last_signals[symbol] = signals
                await self._process_signals(symbol, signals, current_price)
            
        except Exception as e:
            await self.logger.log_error(f"Error processing symbol {symbol}: {e}")
    
    async def _process_signals(self, symbol: str, signals: List[Signal], current_price: float):
        """Process generated signals and execute trades"""
        try:
            # Filter signals by minimum strength
            strong_signals = [s for s in signals if s.strength >= self.config.min_signal_strength]
            
            if not strong_signals:
                return
            
            # Get the strongest signal
            strongest_signal = max(strong_signals, key=lambda s: s.strength)
            
            await self.logger.log(
                f"Processing signal for {symbol}: {strongest_signal.signal_type.value} "
                f"(strength: {strongest_signal.strength:.2f})"
            )
            
            # Check if we already have a pending order for this symbol
            if symbol in self.pending_orders:
                await self.logger.log(f"Pending order exists for {symbol}, skipping")
                return
            
            # Process buy signals
            if strongest_signal.signal_type == SignalType.BUY:
                await self._execute_buy_signal(symbol, strongest_signal, current_price)
            
            # Process sell signals
            elif strongest_signal.signal_type == SignalType.SELL:
                await self._execute_sell_signal(symbol, strongest_signal, current_price)
            
        except Exception as e:
            await self.logger.log_error(f"Error processing signals for {symbol}: {e}")
    
    async def _execute_buy_signal(self, symbol: str, signal: Signal, current_price: float):
        """Execute buy signal"""
        try:
            # Check if we already have a position
            if symbol in self.active_positions:
                await self.logger.log(f"Already have position in {symbol}, skipping buy")
                return
            
            # Calculate position size based on risk management
            position_size = await self._calculate_position_size(symbol, current_price, signal.strength)
            
            if position_size <= 0:
                await self.logger.log(f"Position size too small for {symbol}")
                return
            
            # Validate order
            validation = await self.client.validate_order(symbol, "BUY", position_size, current_price)
            if not validation.get('valid', False):
                await self.logger.log_error(f"Order validation failed for {symbol}: {validation.get('reason')}")
                return
            
            # Place buy order
            order_id = await self.client.place_stock_order(
                symbol=symbol,
                side="BUY",
                quantity=position_size,
                price=current_price,
                order_type="LO"  # Limit order
            )
            
            if order_id:
                self.pending_orders[symbol] = order_id
                await self.logger.log(f"Buy order placed for {symbol}: {position_size} shares @ {current_price}")
            
        except Exception as e:
            await self.logger.log_error(f"Error executing buy signal for {symbol}: {e}")
    
    async def _execute_sell_signal(self, symbol: str, signal: Signal, current_price: float):
        """Execute sell signal"""
        try:
            # Check if we have a position to sell
            if symbol not in self.active_positions:
                await self.logger.log(f"No position to sell in {symbol}")
                return
            
            position = self.active_positions[symbol]
            quantity_to_sell = position['quantity']
            
            if quantity_to_sell <= 0:
                await self.logger.log(f"No shares to sell for {symbol}")
                return
            
            # Validate order
            validation = await self.client.validate_order(symbol, "SELL", quantity_to_sell, current_price)
            if not validation.get('valid', False):
                await self.logger.log_error(f"Sell order validation failed for {symbol}: {validation.get('reason')}")
                return
            
            # Place sell order
            order_id = await self.client.place_stock_order(
                symbol=symbol,
                side="SELL",
                quantity=quantity_to_sell,
                price=current_price,
                order_type="LO"  # Limit order
            )
            
            if order_id:
                self.pending_orders[symbol] = order_id
                await self.logger.log(f"Sell order placed for {symbol}: {quantity_to_sell} shares @ {current_price}")
            
        except Exception as e:
            await self.logger.log_error(f"Error executing sell signal for {symbol}: {e}")
    
    async def _calculate_position_size(self, symbol: str, price: float, signal_strength: float) -> int:
        """Calculate position size based on risk management"""
        try:
            # Get portfolio value
            portfolio = await self.client.get_portfolio_summary()
            portfolio_value = portfolio.get('total_portfolio_value', 0)
            
            if portfolio_value <= 0:
                return 0
            
            # Calculate risk amount
            risk_amount = portfolio_value * self.config.risk_per_trade * signal_strength
            
            # Calculate position size based on stop loss
            stop_loss_amount = price * self.config.stop_loss_pct
            position_value = risk_amount / self.config.stop_loss_pct
            
            # Calculate number of shares
            shares = int(position_value / price)
            
            # Apply maximum position limit
            max_shares = min(shares, self.config.max_position_per_symbol)
            
            # Ensure we don't exceed portfolio limits
            position_value = max_shares * price
            max_portfolio_position = self.config.max_portfolio_value * 0.1  # Max 10% per position
            
            if position_value > max_portfolio_position:
                max_shares = int(max_portfolio_position / price)
            
            return max(max_shares, 0)
            
        except Exception as e:
            await self.logger.log_error(f"Error calculating position size for {symbol}: {e}")
            return 0
    
    async def _check_position_management(self):
        """Check existing positions for stop loss and take profit"""
        try:
            for symbol, position in self.active_positions.items():
                current_price = self.realtime_integrator.get_current_price(symbol)
                if not current_price:
                    continue
                
                avg_price = position['avg_price']
                quantity = position['quantity']
                
                # Calculate P&L percentage
                pnl_pct = (current_price - avg_price) / avg_price
                
                # Check stop loss
                if pnl_pct <= -self.config.stop_loss_pct:
                    await self.logger.log(f"Stop loss triggered for {symbol}: {pnl_pct:.2%}")
                    await self._execute_stop_loss(symbol, current_price, quantity)
                
                # Check take profit
                elif pnl_pct >= self.config.take_profit_pct:
                    await self.logger.log(f"Take profit triggered for {symbol}: {pnl_pct:.2%}")
                    await self._execute_take_profit(symbol, current_price, quantity)
            
        except Exception as e:
            await self.logger.log_error(f"Error in position management: {e}")
    
    async def _execute_stop_loss(self, symbol: str, current_price: float, quantity: int):
        """Execute stop loss order"""
        try:
            order_id = await self.client.place_stock_order(
                symbol=symbol,
                side="SELL",
                quantity=quantity,
                price=current_price * 0.99,  # Sell slightly below market
                order_type="LO"
            )
            
            if order_id:
                self.pending_orders[symbol] = order_id
                await self.logger.log(f"Stop loss order placed for {symbol}")
            
        except Exception as e:
            await self.logger.log_error(f"Error executing stop loss for {symbol}: {e}")
    
    async def _execute_take_profit(self, symbol: str, current_price: float, quantity: int):
        """Execute take profit order"""
        try:
            order_id = await self.client.place_stock_order(
                symbol=symbol,
                side="SELL",
                quantity=quantity,
                price=current_price * 1.01,  # Sell slightly above market
                order_type="LO"
            )
            
            if order_id:
                self.pending_orders[symbol] = order_id
                await self.logger.log(f"Take profit order placed for {symbol}")
            
        except Exception as e:
            await self.logger.log_error(f"Error executing take profit for {symbol}: {e}")
    
    def _is_trading_hours(self) -> bool:
        """Check if current time is within trading hours"""
        now = datetime.now().time()
        start_time = datetime.time(*self.config.trading_hours[0])
        end_time = datetime.time(*self.config.trading_hours[1])
        
        return start_time <= now <= end_time
    
    async def _cancel_all_pending_orders(self):
        """Cancel all pending orders"""
        try:
            for symbol, order_id in self.pending_orders.items():
                await self.client.cancel_stock_order(order_id)
                await self.logger.log(f"Cancelled pending order for {symbol}")
            
            self.pending_orders.clear()
            
        except Exception as e:
            await self.logger.log_error(f"Error cancelling pending orders: {e}")
    
    async def get_strategy_status(self) -> Dict[str, Any]:
        """Get current strategy status"""
        try:
            portfolio = await self.client.get_portfolio_summary()
            
            return {
                'is_running': self.is_running,
                'active_positions': len(self.active_positions),
                'pending_orders': len(self.pending_orders),
                'portfolio_value': portfolio.get('total_portfolio_value', 0),
                'cash_balance': portfolio.get('total_cash', 0),
                'last_update': self.last_update.isoformat(),
                'positions': self.active_positions,
                'recent_signals': {
                    symbol: [{'type': s.signal_type.value, 'strength': s.strength} for s in signals[-3:]]
                    for symbol, signals in self.last_signals.items()
                }
            }
            
        except Exception as e:
            await self.logger.log_error(f"Error getting strategy status: {e}")
            return {'error': str(e)}


# Example usage and configuration
async def create_sample_strategy() -> StockTradingStrategy:
    """Create a sample stock trading strategy"""
    config = TradingConfig(
        symbols=["VIC", "VHM", "VNM", "SAB", "MSN"],  # Vietnamese blue-chip stocks
        max_position_per_symbol=1000,
        max_portfolio_value=500000000,  # 500M VND
        risk_per_trade=0.02,
        stop_loss_pct=0.05,
        take_profit_pct=0.10,
        min_signal_strength=0.4,
        trading_hours=((9, 0), (15, 0)),
        data_update_interval=60,
        use_talib=True
    )
    
    strategy = StockTradingStrategy(config)
    return strategy
