from ibapi.client import EClient
from ibapi.wrapper import EWrapper
from ibapi.contract import Contract
from ibapi.common import TickerId, TickAttrib
import logging
from typing import Dict, Optional, Callable
import threading
import queue
import time

class IBClient(EWrapper, EClient):
    def __init__(self):
        EClient.__init__(self, self)
        self.logger = logging.getLogger(__name__)
        self.data_queue = queue.Queue()
        self.market_data: Dict[str, Dict] = {}
        self.callbacks: Dict[str, Callable] = {}
        self.next_req_id = 1
        self.connected = False

    def connect_and_start(self, host: str = '127.0.0.1', port: int = 7497, client_id: int = 1):
        """Connect to IBKR TWS/Gateway and start the client thread"""
        try:
            self.connect(host, port, client_id)
            self.connected = True
            
            # Start the client thread
            api_thread = threading.Thread(target=self.run, daemon=True)
            api_thread.start()
            
            self.logger.info(f"Connected to IBKR at {host}:{port}")
        except Exception as e:
            self.logger.error(f"Failed to connect to IBKR: {str(e)}")
            raise

    def error(self, reqId: TickerId, errorCode: int, errorString: str):
        """Handle error messages from IBKR"""
        self.logger.error(f"IBKR Error {errorCode}: {errorString} (reqId: {reqId})")

    def nextValidId(self, orderId: int):
        """Handle next valid order ID"""
        self.next_req_id = orderId
        self.logger.info(f"Next valid order ID: {orderId}")

    def tickPrice(self, reqId: TickerId, tickType: int, price: float, attrib: TickAttrib):
        """Handle price updates"""
        symbol = self._get_symbol_from_req_id(reqId)
        if not symbol:
            return

        if symbol not in self.market_data:
            self.market_data[symbol] = {}

        # Map tick types to price types
        price_types = {
            1: 'bid',
            2: 'ask',
            4: 'last',
            6: 'high',
            7: 'low',
            9: 'close'
        }

        if tickType in price_types:
            self.market_data[symbol][price_types[tickType]] = price
            if 'price_update' in self.callbacks:
                self.callbacks['price_update'](symbol, price_types[tickType], price)

    def tickSize(self, reqId: TickerId, tickType: int, size: int):
        """Handle size updates (volume, etc.)"""
        symbol = self._get_symbol_from_req_id(reqId)
        if not symbol:
            return

        if symbol not in self.market_data:
            self.market_data[symbol] = {}

        # Map tick types to size types
        size_types = {
            0: 'bid_size',
            3: 'ask_size',
            5: 'last_size',
            8: 'volume'
        }

        if tickType in size_types:
            self.market_data[symbol][size_types[tickType]] = size
            if 'size_update' in self.callbacks:
                self.callbacks['size_update'](symbol, size_types[tickType], size)

    def _get_symbol_from_req_id(self, reqId: TickerId) -> Optional[str]:
        """Get symbol from request ID"""
        # TODO: Implement proper request ID to symbol mapping
        return None

    def request_market_data(self, symbol: str, exchange: str = "SMART", currency: str = "USD"):
        """Request market data for a symbol"""
        contract = Contract()
        contract.symbol = symbol
        contract.exchange = exchange
        contract.currency = currency
        contract.secType = "STK"  # Stock type

        try:
            self.reqMktData(self.next_req_id, contract, "", False, False, [])
            self.next_req_id += 1
            self.logger.info(f"Requested market data for {symbol}")
        except Exception as e:
            self.logger.error(f"Failed to request market data for {symbol}: {str(e)}")

    def get_market_data(self, symbol: str) -> Dict:
        """Get current market data for a symbol"""
        return self.market_data.get(symbol, {})

    def register_callback(self, event_type: str, callback: Callable):
        """Register callback for specific event types"""
        self.callbacks[event_type] = callback

    def disconnect(self):
        """Disconnect from IBKR"""
        if self.connected:
            self.disconnect()
            self.connected = False
            self.logger.info("Disconnected from IBKR") 