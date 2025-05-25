# StockTracker

StockTracker is a modularized application for tracking stock market data, with a specific focus on preferred stocks.

## Project Structure

The application has been modularized to improve maintainability and readability:

```
StockTracker/
├── stock_tracker.py          # Main application entry point
├── preferred_stock_tracker.original.bak.py  # Original non-modular version (backup)
├── tb_modules/               # Modularized components with 'tb' prefix
│   ├── __init__.py           # Package initialization
│   ├── tb_utils.py           # General utility functions
│   ├── tb_data_cache.py      # Market data caching functionality
│   ├── tb_compression.py     # Data compression utilities
│   ├── tb_spreadci_window.py # SpreadciDataWindow implementation
│   ├── tb_contracts.py       # Interactive Brokers contract creation
│   ├── tb_ui_utils.py        # UI-related utility functions
│   ├── tb_orders.py          # Order management functionality
│   ├── tb_ui_components.py   # UI components and display functions
│   ├── tb_ib_connection.py   # Interactive Brokers connection handling
│   └── tb_data_management.py # Data management and operations
└── README.md                 # This documentation file
```

## Modules

### tb_utils.py
Contains generic utility functions like:
- `safe_format_float` - Safely format float values
- `safe_float` - Convert values to float safely
- `safe_int` - Convert values to int safely
- `normalize_ticker_column` - Normalize ticker symbols in DataFrames

### tb_data_cache.py
Implements the `MarketDataCache` class for caching market data and managing API subscriptions.

### tb_compression.py
Handles data compression and decompression for efficient data storage and transmission:
- `compress_market_data` - Serializes, compresses, and encodes data
- `decompress_market_data` - Decodes, decompresses, and deserializes data

### tb_spreadci_window.py
Contains the `SpreadciDataWindow` class, a window for displaying and managing spreadci data.

### tb_contracts.py
Functions for creating Interactive Brokers contracts:
- `create_preferred_stock_contract` - Creates contracts for preferred stocks
- `create_common_stock_contract` - Creates contracts for common stocks

### tb_ui_utils.py
UI-related utility functions:
- `create_simple_treeview` - Creates a standardized Treeview widget
- `safe_reset_tags` - Safely resets tags on Treeview items

### tb_orders.py
Order management functionality:
- `create_limit_order` - Creates IB limit orders
- `create_market_order` - Creates IB market orders
- `format_order_row` - Formats order data for display
- `calculate_order_value` - Calculates total order value

### tb_ui_components.py
UI components and display functions:
- Status bar creation and updates
- Benchmark frame and label updates
- Filter frames
- Tab controls
- Page navigation controls
- Message popups

### tb_ib_connection.py
Interactive Brokers connection handling:
- `connect_to_ibkr` - Establishes connection to Interactive Brokers
- `disconnect_from_ibkr` - Disconnects from Interactive Brokers
- `subscribe_to_market_data` - Subscribes to market data for a contract
- `cancel_market_data_subscription` - Cancels market data subscription
- API call queue processing
- Ticker data parsing

### tb_data_management.py
Data management and operations:
- `get_filtered_stocks` - Filters stocks based on tab and text
- `sort_dataframe` - Sorts DataFrames by column
- `get_paginated_data` - Gets specific pages from DataFrames
- Treeview population and update functions
- Color tag application
- Top movers identification

## Running the Application

To run the application:

```bash
python stock_tracker.py
```

## Further Modularization

The application has been successfully modularized with a step-by-step approach. The next steps would be:
- Implementing the remaining UI functionality in each stub method
- Creating dedicated modules for portfolio/position-specific functionality
- Adding comprehensive documentation to each module
- Developing unit tests for each module 