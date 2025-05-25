from typing import Dict, Optional, List
import logging
from datetime import datetime

class OrderManager:
    def __init__(self):
        self.logger = logging.getLogger(__name__)
        self.orders: Dict[str, Dict] = {}

    def update_orders(self, orders_data: List[Dict]):
        """Update orders from API response"""
        for order in orders_data:
            cl_ord_id = order.get("clOrdId")
            if cl_ord_id:
                self.orders[cl_ord_id] = order
        self.logger.info(f"Orders updated: {self.orders}")

    def get_order(self, cl_ord_id: str) -> Optional[Dict]:
        """Get order by client order ID"""
        return self.orders.get(cl_ord_id)

    def get_all_orders(self) -> Dict:
        """Get all orders"""
        return self.orders

    def create_order_request(self, symbol: str, side: str, quantity: int, 
                           order_type: str, price: Optional[float] = None, 
                           stop_price: Optional[float] = None) -> Dict:
        """Create a new order request"""
        order_data = {
            "messageType": "neworder",
            "reqId": str(int(datetime.now().timestamp())),
            "clOrdId": f"order_{int(datetime.now().timestamp())}",
            "symbol": symbol,
            "side": side,
            "orderQty": str(quantity),
            "ordType": order_type,
            "exDestination": "INET",
            "timeInForce": "DAY"
        }

        if price is not None:
            order_data["price"] = str(price)
        if stop_price is not None:
            order_data["stopPrice"] = str(stop_price)

        return order_data

    def create_cancel_request(self, cl_ord_id: str) -> Dict:
        """Create a cancel order request"""
        return {
            "messageType": "cancelorder",
            "reqId": str(int(datetime.now().timestamp())),
            "clOrdId": cl_ord_id
        }

    def get_open_orders(self) -> Dict:
        """Get all open orders"""
        return {cl_ord_id: order for cl_ord_id, order in self.orders.items() 
                if order.get("status") in ["Pending New", "New", "PartialFill"]}

    def get_filled_orders(self) -> Dict:
        """Get all filled orders"""
        return {cl_ord_id: order for cl_ord_id, order in self.orders.items() 
                if order.get("status") in ["Filled", "PartialFill"]} 