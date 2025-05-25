import asyncio
import json
import logging
from typing import Dict, Optional, Callable, List
from datetime import datetime

from .websocket import WebSocketClient
from .positions import PositionManager
from .orders import OrderManager
from .balances import BalanceManager

class HammerClient:
    def __init__(self, base_url: str, api_key: str, api_secret: str, account: str):
        self.logger = logging.getLogger(__name__)
        self.base_url = base_url
        self.api_key = api_key
        self.api_secret = api_secret
        self.account = account
        
        # Initialize managers
        self.websocket = WebSocketClient(base_url)
        self.positions = PositionManager()
        self.orders = OrderManager()
        self.balances = BalanceManager()
        
        # Register message handlers
        self.websocket.register_callback("positions", self._handle_positions)
        self.websocket.register_callback("balances", self._handle_balances)
        self.websocket.register_callback("orders", self._handle_orders)

    async def connect(self):
        """Connect to Hammer API"""
        await self.websocket.connect()
        await self._authenticate()

    async def _authenticate(self):
        """Authenticate with Hammer API"""
        auth_message = {
            "messageType": "login",
            "reqId": str(int(datetime.now().timestamp())),
            "apiKey": self.api_key,
            "apiSecret": self.api_secret,
            "account": self.account
        }
        await self.websocket.send_message(auth_message)

    def _handle_positions(self, message: Dict):
        """Handle positions update"""
        positions_data = message.get("positions", [])
        self.positions.update_positions(positions_data)

    def _handle_balances(self, message: Dict):
        """Handle balances update"""
        balances_data = message.get("balances", {})
        self.balances.update_balances(balances_data)

    def _handle_orders(self, message: Dict):
        """Handle orders update"""
        orders_data = message.get("orders", [])
        self.orders.update_orders(orders_data)

    async def place_order(self, symbol: str, side: str, quantity: int, 
                         order_type: str, price: Optional[float] = None,
                         stop_price: Optional[float] = None) -> str:
        """Place a new order"""
        order_data = self.orders.create_order_request(
            symbol, side, quantity, order_type, price, stop_price
        )
        await self.websocket.send_message(order_data)
        return order_data["clOrdId"]

    async def cancel_order(self, cl_ord_id: str):
        """Cancel an existing order"""
        cancel_data = self.orders.create_cancel_request(cl_ord_id)
        await self.websocket.send_message(cancel_data)

    def get_position(self, symbol: str) -> Optional[Dict]:
        """Get current position for a symbol"""
        return self.positions.get_position(symbol)

    def get_all_positions(self) -> Dict:
        """Get all current positions"""
        return self.positions.get_all_positions()

    def get_balance(self, currency: str = "USD") -> Optional[Dict]:
        """Get account balance"""
        return self.balances.get_balance(currency)

    def get_all_balances(self) -> Dict:
        """Get all account balances"""
        return self.balances.get_all_balances()

    def get_open_orders(self) -> Dict:
        """Get all open orders"""
        return self.orders.get_open_orders()

    def get_filled_orders(self) -> Dict:
        """Get all filled orders"""
        return self.orders.get_filled_orders()

    async def close(self):
        """Close the connection"""
        await self.websocket.close() 