# HammerIB Trading Application

This application integrates Alaric (Hammer) API for order execution and Interactive Brokers (IB) API for market data and strategy conditioning.

## How to Run

1. Open a terminal and navigate to the project root directory:
   ```
   cd C:/Users/User/OneDrive/Masaüstü/Proje/StockTracker
   ```
2. Run the application using:
   ```
   python -m hammerib.main
   ```
   This ensures all imports work correctly and the modular structure is respected.

## Project Structure & Modular Design

- **hammerib/main.py**: Main entry point. Starts the GUI (`MainWindow`).
- **hammerib/gui/**: All GUI (Tkinter) code and windows.
  - `main_window.py`: Main application window, tab logic, and top-level controls.
  - `etf_panel.py`: Compact, always-live ETF panel (used in all windows).
  - `maltopla_window.py`: Event-driven, cache-enabled analysis windows (Opt50/Extlt35/top movers).
  - `opt_buttons.py`, `pos_orders_buttons.py`, `top_movers_buttons.py`: Modular button creators for top bar.
  - `benchmark_panel.py`, `hidden_buttons.py`: Other reusable GUI widgets.
- **hammerib/ib_api/**: Interactive Brokers API integration.
  - `manager.py`: Handles IBKR connection, live data subscriptions, ETF/ticker management, and caching.
- **hammerib/alaric_api/**: Alaric/Hammer WebSocket API integration (for order execution, not market data).
- **hammerib/data/**: Data helpers, CSV reading, etc.
- **hammerib/strategies/**: (If used) Trading strategies and logic.
- **hammerib/config/**: Configuration files and settings.
- **hammerib/utils/**: Utility functions.

## Key Features

- **Event-driven, modular GUI**: Each window/tab is independent and subscribes only to the tickers it needs.
- **Live data & snapshot cache**: Only 20 tickers at a time are live-subscribed; all others are cached for fast analysis.
- **ETF panel**: Always visible, compact, and live-updating in every window.
- **Pagination**: All tables show max 20 tickers per page, with navigation.
- **Batch analysis**: "Döngü Başlat" button cycles through all pages to keep cache fresh for all tickers.
- **Multi-select & action buttons**: Checkboxes for manual or bulk selection, with 4 action buttons for future order logic.
- **Positions/Orders**: Placeholder windows for future WebSocket-based integration.
- **Top movers**: T/C-prefs for biggest gainers/losers, with all the above features.

## For New Developers/Assistants

- **Start from `main.py`**. All main logic is in `hammerib/gui/main_window.py`.
- Each module is responsible for a single concern (GUI, IBKR, Alaric, etc.).
- To add a new feature, create a new file in the relevant module and import it where needed.
- All windows and panels are designed to be reusable and composable.
- For live data, only subscribe to what is visible; use the cache for everything else.
- For order execution, see `hammerib/alaric_api/` (not yet fully integrated).

---

**If you are a new developer or AI assistant:**
- Attach or review the `hammerib/` folder and this README.
- Use `python -m hammerib.main` to run.
- All code is modular and extendable; follow the structure for new features. 