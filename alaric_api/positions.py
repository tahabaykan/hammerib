from typing import Dict, List
import logging
from datetime import datetime

class PositionManager:
    def __init__(self):
        self.logger = logging.getLogger(__name__)
        self.positions: Dict[str, Dict] = {}

    def update_positions(self, positions_data: List[Dict]):
        """Update positions from API response"""
        for position in positions_data:
            symbol = position.get("symbol")
            if symbol:
                self.positions[symbol] = {
                    "quantity": position.get("qty", 0),
                    "average_price": position.get("averagePrice", 0.0)
                }
        self.logger.info(f"Positions updated: {self.positions}")

    def get_position(self, symbol: str) -> Dict:
        """Get position for a specific symbol"""
        return self.positions.get(symbol, {"quantity": 0, "average_price": 0.0})

    def get_all_positions(self) -> Dict:
        """Get all positions"""
        return self.positions

    def calculate_position_value(self, symbol: str, current_price: float) -> float:
        """Calculate current value of a position"""
        position = self.get_position(symbol)
        return position["quantity"] * current_price

    def calculate_position_pnl(self, symbol: str, current_price: float) -> float:
        """Calculate P&L for a position"""
        position = self.get_position(symbol)
        if position["quantity"] == 0:
            return 0.0
        return (current_price - position["average_price"]) * position["quantity"] 