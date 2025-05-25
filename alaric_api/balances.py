from typing import Dict, Optional
import logging

class BalanceManager:
    def __init__(self):
        self.logger = logging.getLogger(__name__)
        self.balances: Dict[str, Dict] = {}

    def update_balances(self, balances_data: Dict):
        """Update balances from API response"""
        self.balances = balances_data
        self.logger.info(f"Balances updated: {self.balances}")

    def get_balance(self, currency: str = "USD") -> Optional[Dict]:
        """Get balance for specific currency"""
        return self.balances.get(currency)

    def get_all_balances(self) -> Dict:
        """Get all balances"""
        return self.balances

    def get_available_cash(self, currency: str = "USD") -> float:
        """Get available cash for trading"""
        balance = self.get_balance(currency)
        if balance:
            return float(balance.get("availableCash", 0))
        return 0.0

    def get_buying_power(self, currency: str = "USD") -> float:
        """Get buying power"""
        balance = self.get_balance(currency)
        if balance:
            return float(balance.get("buyingPower", 0))
        return 0.0

    def get_margin_used(self, currency: str = "USD") -> float:
        """Get margin used"""
        balance = self.get_balance(currency)
        if balance:
            return float(balance.get("marginUsed", 0))
        return 0.0

    def get_equity(self, currency: str = "USD") -> float:
        """Get account equity"""
        balance = self.get_balance(currency)
        if balance:
            return float(balance.get("equity", 0))
        return 0.0 