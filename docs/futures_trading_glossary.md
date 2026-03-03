# VN30 Trading System V2 - Technical Glossary

## Core Classes

### **TCBSClient** (`core/api_client.py`)
Unified API client for TCBS trading platform integration.

**Key Methods:**
- `initialize_token()` - Load and validate authentication token
- `place_order(ticker, side, quantity, price, order_type)` - Submit trading orders
- `modify_order(order_id, new_price, new_quantity)` - Update existing orders
- `cancel_order(order_id)` - Cancel pending orders
- `get_positions()` - Retrieve current portfolio positions
- `get_order_status(order_id)` - Check order execution status

**Attributes:**
- `token` - Current authentication token
- `base_url` - TCBS API endpoint
- `headers` - HTTP request headers with authentication

---

### **StreamingDataHandler** (`core/streaming_data_handler.py`)
Processes real-time market data and calculates statistical spreads.

**Key Methods:**
- `connect()` - Establish WebSocket connection for market data
- `process_message(message)` - Handle incoming market data messages
- `_setting_long_short_spread()` - Calculate statistical arbitrage spreads
- `write_to_file(text)` - Write real-time price data to file
- `process_s21_messages()` - Process matched price messages

**Attributes:**
- `ticker_f1m`, `ticker_f2m` - Trading instrument symbols
- `shared_array` - Numpy array for inter-process data sharing
- `tick_data` - Deque storing historical price data
- `spread_long`, `spread_short` - Calculated arbitrage thresholds

---

### **ProcessingStrategy** (`core/processing_strategy.py`)
Main trading strategy implementation with order management.

**Key Methods:**
- `get_data()` - Extract market data from shared memory
- `get_positions(prev_spread_long, prev_spread_short)` - Initialize position data
- `_apply_dca_method(max_qty_place)` - Calculate DCA quantities
- `connect_order_change()` - Connect to order status WebSocket
- `receive_messages_order_change(message)` - Process order updates
- `handle_after_stop_process(is_expiry)` - Cleanup on system shutdown

**Attributes:**
- `pos_f1m`, `pos_f2m` - Current positions in each instrument
- `placing_order_f1m`, `placing_order_f2m` - Order placement flags
- `order_id_f1m`, `order_id_f2m` - Active order identifiers
- `qty_long_f2m`, `qty_short_f2m` - DCA calculated quantities
- `cut_loss` - Risk management flag

---

### **OrderMonitor** (`core/order_monitor.py`)
Enhanced order state monitoring with transition validation.

**Key Methods:**
- `is_valid_transition(current, next_state)` - Validate state changes
- `log_transition(current, next_state, valid)` - Log state transitions
- `alert_monitor(timeout)` - Monitor order alerts and detect invalid states
- `get_stats()` - Return monitoring statistics

**Attributes:**
- `queue_alert` - Async queue for order alerts
- `stop_event` - System shutdown event
- `prev_state` - Previous order state
- `transition_count` - Number of state transitions

---

## Utility Classes

### **TokenManager** (`utils/token_manager.py`)
Centralized authentication token management.

**Key Methods:**
- `load_token()` - Load token from file
- `save_token(token_data)` - Save token to file
- `is_token_valid()` - Check token expiration
- `renew_token(otp_code)` - Renew token using OTP
- `get_valid_token()` - Get valid token with auto-renewal

**Attributes:**
- `token_file` - Path to token storage file
- `current_token` - Cached token data

---

### **PositionManager** (`utils/position_manager.py`)
Unified position retrieval and caching system.

**Key Methods:**
- `get_positions()` - Retrieve current positions from API
- `get_total_position()` - Calculate sum of all positions
- `get_position_summary()` - Format positions for display
- `_update_cache(positions)` - Update position cache
- `_is_cache_valid()` - Check cache expiration

**Attributes:**
- `client` - TCBSClient instance for API calls
- `tickers` - List of instruments to track
- `cache` - Cached position data
- `cache_timestamp` - Cache last update time

---

## WebSocket Classes

### **BaseWebSocketClient** (`websockets/base_websocket.py`)
Base class providing common WebSocket functionality.

**Key Methods:**
- `connect_with_retry(token, max_retries)` - Connect with exponential backoff
- `authenticate(token)` - Authenticate WebSocket connection
- `send_ping()` - Send periodic ping messages
- `receive_loop(message_handler)` - Main message receiving loop
- `disconnect()` - Close WebSocket connection gracefully

**Attributes:**
- `websocket` - WebSocket connection object
- `token` - Authentication token
- `ping_interval` - Ping frequency in seconds
- `is_connected` - Connection status flag

---

### **DerivativeStreamingClient** (`websockets/base_websocket.py`)
Specialized client for derivative market data streaming.

**Key Methods:**
- `subscribe_to_tickers(tickers)` - Subscribe to market data
- `_handle_derivative_message(message)` - Process derivative data

**Attributes:**
- `tickers` - List of subscribed instruments
- `subscription_channels` - Active data channels

---

### **OrderChangeStreamingClient** (`websockets/base_websocket.py`)
Specialized client for order status updates.

**Key Methods:**
- `subscribe_to_orders()` - Subscribe to order updates
- `_handle_order_message(message)` - Process order status changes

---

## Logging Classes

### **FastLogger** (`logger_utils/fast_logger.py`)
Enhanced asynchronous logging with buffering.

**Key Methods:**
- `log(message, level)` - Add log entry with level
- `log_info(message)` - Log info level message
- `log_warning(message)` - Log warning level message
- `log_error(message)` - Log error level message
- `log_debug(message)` - Log debug level message
- `flush()` - Force write buffered logs to file

**Attributes:**
- `buffer` - In-memory log buffer
- `file_path` - Log file path
- `flush_interval` - Auto-flush interval
- `max_buffer_size` - Buffer size limit

---

### **LoggerManager** (`logger_utils/fast_logger.py`)
Centralized management of multiple loggers.

**Key Methods:**
- `get_logger(name, directory)` - Get or create logger instance
- `flush_all()` - Flush all managed loggers
- `shutdown()` - Gracefully shutdown all loggers

**Attributes:**
- `loggers` - Dictionary of managed logger instances

---

## Utility Functions

### **Common Utilities** (`utils/common.py`)

**Functions:**
- `is_within_time_range(morning_session, afternoon_session)` - Check trading hours
- `parse_positions(response_data)` - Parse API position response
- `calculate_required_margin(quantity, price, margin_rate)` - Calculate margin requirements
- `save_json_async(data, filepath)` - Asynchronously save JSON data
- `load_json_config(filepath)` - Load JSON configuration file

---

## Configuration Constants

### **Trading Parameters** (`config.py`)

**Instruments:**
- `ticker_f1m` - Primary futures contract symbol
- `ticker_f2m` - Secondary futures contract symbol
- `expiry_date` - Contract expiration date

**Risk Management:**
- `max_position` - Maximum allowed position size
- `cut_points` - Stop-loss threshold in points
- `cut_time` - Stop-loss time threshold in seconds
- `slippage_points` - Expected slippage allowance

**Statistical Parameters:**
- `windows` - Rolling window size for calculations
- `z_scores` - Z-score threshold for spread signals
- `min_adj_std` - Minimum adjusted standard deviation

**DCA Configuration:**
- `avg_price_config` - Dictionary mapping position sizes to price adjustments

---

## Data Structures

### **Shared Memory Array Layout**
10-element numpy array for inter-process communication:
```
Index | Description
------|------------
[0]   | F1M Bid Price 1
[1]   | F1M Bid Price 2  
[2]   | F1M Ask Price 1
[3]   | F1M Ask Price 2
[4]   | F2M Bid Price 1
[5]   | F2M Bid Price 2
[6]   | F2M Ask Price 1
[7]   | F2M Ask Price 2
[8]   | Calculated Spread Long
[9]   | Calculated Spread Short
```

### **Order States**
Valid order state transitions:
- `placing` → `placed` | `fully_filled`
- `cancelling` → `fully_filled` | `canceled`

### **Message Types**
WebSocket message prefixes:
- `s|21` - Matched price messages
- `s|23` - Bid price updates
- `s|24` - Ask price updates
- `message_proto|DE_ORDER` - Order status changes

---

## API Endpoints

### **TCBS API Endpoints**
- **Authentication**: `/api/v1/auth/login`
- **Order Placement**: `/api/v1/orders`
- **Order Modification**: `/api/v1/orders/{order_id}`
- **Order Cancellation**: `/api/v1/orders/{order_id}/cancel`
- **Position Retrieval**: `/api/v1/positions`
- **WebSocket**: `wss://api.tcbs.com.vn/ws`

---

## Error Codes

### **Common Error Responses**
- `401` - Unauthorized (invalid token)
- `400` - Bad Request (invalid parameters)
- `429` - Rate Limit Exceeded
- `500` - Internal Server Error
- `503` - Service Unavailable

### **Custom Error States**
- `TOKEN_EXPIRED` - Authentication token expired
- `INVALID_TRANSITION` - Invalid order state transition
- `CONNECTION_LOST` - WebSocket connection dropped
- `POSITION_LIMIT_EXCEEDED` - Position size exceeds maximum

---

## Performance Metrics

### **Monitoring Attributes**
- `transition_count` - Number of order state transitions
- `buffer_size` - Current log buffer size
- `cache_hit_rate` - Position cache effectiveness
- `connection_uptime` - WebSocket connection duration
- `message_latency` - Average message processing time

This glossary provides comprehensive technical documentation for all classes, methods, and data structures in the VN30 Trading System V2.
