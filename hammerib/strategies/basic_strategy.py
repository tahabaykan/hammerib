from typing import Dict, Optional
import logging
from datetime import datetime

class BasicStrategy:
    def __init__(self, name: str):
        self.logger = logging.getLogger(__name__)
        self.name = name
        self.positions: Dict[str, Dict] = {}
        self.market_data: Dict[str, Dict] = {}
        self.is_active = False

    def update_market_data(self, symbol: str, data: Dict):
        """Update market data for a symbol"""
        self.market_data[symbol] = data
        self._check_conditions(symbol)

    def update_position(self, symbol: str, position_data: Dict):
        """Update position data for a symbol"""
        self.positions[symbol] = position_data

    def _check_conditions(self, symbol: str):
        """Check trading conditions for a symbol"""
        if not self.is_active:
            return

        try:
            market_data = self.market_data.get(symbol, {})
            position = self.positions.get(symbol, {})

            # Example conditions (to be implemented by specific strategies)
            self._evaluate_entry_conditions(symbol, market_data, position)
            self._evaluate_exit_conditions(symbol, market_data, position)

        except Exception as e:
            self.logger.error(f"Error checking conditions for {symbol}: {str(e)}")

    def _evaluate_entry_conditions(self, symbol: str, market_data: Dict, position: Dict):
        """Evaluate conditions for entering a position"""
        # To be implemented by specific strategies
        pass

    def _evaluate_exit_conditions(self, symbol: str, market_data: Dict, position: Dict):
        """Evaluate conditions for exiting a position"""
        # To be implemented by specific strategies
        pass

    def generate_order(self, symbol: str, action: str, quantity: int, order_type: str, price: Optional[float] = None) -> Dict:
        """Generate an order based on strategy conditions"""
        return {
            "symbol": symbol,
            "action": action,  # "BUY" or "SELL"
            "quantity": quantity,
            "order_type": order_type,  # "MARKET" or "LIMIT"
            "price": price,
            "strategy": self.name,
            "timestamp": datetime.now().isoformat()
        }

    def start(self):
        """Start the strategy"""
        self.is_active = True
        self.logger.info(f"Strategy {self.name} started")

    def stop(self):
        """Stop the strategy"""
        self.is_active = False
        self.logger.info(f"Strategy {self.name} stopped") 