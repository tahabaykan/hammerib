import pandas as pd
from ib_insync import IB, util, Stock
import logging
import time

def try_connect_ibkr(host='127.0.0.1', client_id=1, timeout=20, readonly=True):
    util.logToConsole(logging.WARNING)
    ib = IB()
    ports = [7497, 7496, 4001]  # TWS ve Gateway portları
    connected = False
    for port in ports:
        try:
            print(f"Port {port} ile bağlantı deneniyor...")
            ib.connect(host, port, clientId=client_id, readonly=readonly, timeout=timeout)
            if ib.isConnected():
                print(f"IBKR bağlantısı başarılı! Port: {port}")
                connected = True
                break
        except Exception as e:
            print(f"Port {port} bağlantı hatası: {e}")
    if not connected:
        print("Hiçbir IBKR portuna bağlanılamadı! TWS/Gateway açık mı?")
    return ib, connected

class MarketDataManager:
    def __init__(self, connect_on_init=False):
        self.ib = None
        self.connected = False
        logging.basicConfig(level=logging.INFO)
        self.logger = logging.getLogger(__name__)
        if connect_on_init:
            self.connect()
        self.historical_data = pd.read_csv('historical_data.csv')
        self.extended_data = pd.read_csv('extlthistorical.csv')
        self.active_contracts = {}
        self.market_data = {}
    
    def connect(self):
        if not self.connected:
            self.ib, self.connected = try_connect_ibkr()
            if self.connected:
                self.logger.info('Connected to IBKR')
                # Önce gecikmeli, sonra canlı veri iste
                self.ib.reqMarketDataType(3)
                time.sleep(0.2)
                self.ib.reqMarketDataType(1)
            else:
                self.logger.error('IBKR bağlantısı başarısız!')
    
    def get_historical_tickers(self, start_idx, end_idx):
        """Get tickers from historical data for the given page range."""
        return self.historical_data['PREF IBKR'].dropna().iloc[start_idx:end_idx].tolist()
    
    def get_extended_tickers(self, start_idx, end_idx):
        """Get tickers from extended data for the given page range."""
        return self.extended_data['PREF IBKR'].dropna().iloc[start_idx:end_idx].tolist()
    
    def get_max_pages(self, items_per_page):
        """Calculate maximum number of pages based on data size."""
        return max(
            len(self.historical_data) // items_per_page,
            len(self.extended_data) // items_per_page
        )
    
    def subscribe_page_tickers(self, tickers):
        """Subscribe only to tickers on the current page."""
        self.cancel_unsubscribed_tickers(tickers)
        for ticker in tickers:
            if not self.connected:
                continue
            if ticker not in self.active_contracts:
                try:
                    contract = Stock(ticker, 'SMART', 'USD')
                    self.ib.qualifyContracts(contract)
                    self.active_contracts[ticker] = contract
                    self.ib.reqMktData(contract)
                    self.logger.info(f"Subscribed to {ticker}")
                    time.sleep(0.05)  # Flood koruması için kısa bekleme
                except Exception as e:
                    self.logger.error(f"Error subscribing to {ticker}: {str(e)}")
    
    def cancel_unsubscribed_tickers(self, page_tickers):
        """Cancel subscriptions for tickers not on the current page."""
        to_cancel = [t for t in self.active_contracts if t not in page_tickers]
        for ticker in to_cancel:
            try:
                contract = self.active_contracts[ticker]
                self.ib.cancelMktData(contract)
                self.logger.info(f"Unsubscribed from {ticker}")
            except Exception as e:
                self.logger.error(f"Error unsubscribing from {ticker}: {str(e)}")
            del self.active_contracts[ticker]
    
    def get_market_data(self):
        """Get current market data for all active contracts."""
        if not self.connected:
            return {}
        for ticker, contract in self.active_contracts.items():
            ticker_data = self.ib.ticker(contract)
            if ticker_data:
                self.market_data[ticker] = {
                    'bid': ticker_data.bid,
                    'ask': ticker_data.ask,
                    'last': ticker_data.last,
                    'volume': ticker_data.volume
                }
        return self.market_data
    
    def disconnect(self):
        """Disconnect from IB and clean up."""
        if not self.connected or not self.ib:
            return
        try:
            # Cancel all market data subscriptions
            for contract in self.active_contracts.values():
                self.ib.cancelMktData(contract)
            
            # Disconnect from IB
            self.ib.disconnect()
            self.connected = False
            self.logger.info("Disconnected from IB")
        except Exception as e:
            self.logger.error(f"Error during disconnect: {str(e)}") 