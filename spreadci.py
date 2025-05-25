import json
from ib_insync import IB, Stock, util
import pandas as pd
import time
import threading
from collections import defaultdict
import tkinter as tk
from tkinter import ttk
import math
import asyncio
import queue
from preferred_stock_tracker import PreferredStockTracker

# Read the input CSV file
df = pd.read_csv('sma_results.csv')

# Filter rows where PREF IBKR is present and DIV AMOUNT is greater than 0.37
filtered_df = df[
    (df['PREF IBKR'].notna()) & 
    (df['DIV AMOUNT'] > 0.37)
]

# Save the filtered results to spreadci.csv
filtered_df.to_csv('spreadci.csv', index=False)

print("Filtering completed. Results saved to spreadci.csv")

class PreferredStockMonitor(tk.Tk):
    def __init__(self):
        super().__init__()
        
        # Temel pencere yapılandırması
        self.title("Preferred Stock Monitor")
        self.geometry("1350x700")
        
        # IBKR bağlantı değişkenleri
        self.ib = IB()
        self.tickers = {}  # Aktif abonelikler (preferred stocks)
        self.common_tickers = {}  # Common stock abonelikleri
        self.latest_data = defaultdict(dict)
        self.common_stock_data = defaultdict(dict)  # Common stock verisi
        self.connected = False
        self.running = False
        self.next_rotation_index = 0
        
        # UI değişkenleri
        self.items_per_page = 20
        self.current_page = 1
        self.total_pages = 1
        self.filter_text = ""
        self.sort_column = None
        self.sort_reverse = False
        
        # API çağrıları için kuyruk mekanizması
        self.api_call_queue = queue.Queue()
        self.api_call_processing = False
        
        # API işlemlerini düzenli aralıklarla işle
        self.after(100, self.process_api_calls)
        
        # UI oluştur
        self.setup_ui()
        
    def setup_ui(self):
        """Kullanıcı arayüzü bileşenlerini oluştur"""
        # Ana frame
        self.main_frame = ttk.Frame(self)
        self.main_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)
        
        # Üst kontrol paneli
        self.control_frame = ttk.Frame(self.main_frame)
        self.control_frame.pack(fill=tk.X, pady=(0, 10))
        
        # Bağlantı durumu etiketi
        self.status_label = ttk.Label(self.control_frame, text="Bağlantı durumu: Bağlı değil")
        self.status_label.pack(side=tk.LEFT, padx=(0, 20))
        
        # Bağlantı düğmesi
        self.connect_button = ttk.Button(self.control_frame, text="IBKR Bağlan", command=self.connect_to_ibkr)
        self.connect_button.pack(side=tk.LEFT, padx=5)
        
        # Bağlantıyı kes düğmesi
        self.disconnect_button = ttk.Button(self.control_frame, text="Bağlantıyı Kes", command=self.disconnect_from_ibkr)
        self.disconnect_button.pack(side=tk.LEFT, padx=5)
        
        # Pozisyonları görüntüleme düğmesi
        self.positions_button = ttk.Button(self.control_frame, text="Pozisyonları Göster", 
                                       command=self.show_positions)
        self.positions_button.pack(side=tk.LEFT, padx=5)
        self.positions_button.config(state=tk.DISABLED)  # Başlangıçta devre dışı
        
        # Opt50 Portföy butonu
        self.opt50_button = ttk.Button(self.control_frame, text="Opt50 Port", 
                                   command=self.show_opt50_portfolio)
        self.opt50_button.pack(side=tk.LEFT, padx=5)
        
        # ETF Listesi butonu
        self.etf_button = ttk.Button(self.control_frame, text="ETF List", 
                                  command=self.show_etf_list)
        self.etf_button.pack(side=tk.LEFT, padx=5)
        
        # Hidden Bid Placement butonu
        self.hidden_bid_button = ttk.Button(self.control_frame, text="Hidden Bid Placement", 
                                        command=self.place_hidden_bids)
        self.hidden_bid_button.pack(side=tk.LEFT, padx=5)
        
        # Preferred Stock Tracker butonu
        self.tracker_button = ttk.Button(self.control_frame, text="Preferred Stock Tracker",
                                      command=self.open_tracker)
        self.tracker_button.pack(side=tk.LEFT, padx=5)
        
        # Yenile düğmesi
        self.refresh_button = ttk.Button(self.control_frame, text="Zorla Yenile", command=self.force_refresh)
        self.refresh_button.pack(side=tk.LEFT, padx=5)
        
        # Aktif abonelik sayısı etiketi
        self.subscription_count_label = ttk.Label(self.control_frame, text="Aktif abonelikler: 0/50")
        self.subscription_count_label.pack(side=tk.RIGHT)
        
        # Filtre frame'i
        self.filter_frame = ttk.Frame(self.main_frame)
        self.filter_frame.pack(fill=tk.X, pady=(0, 10))
        
        # Filtre etiketi
        self.filter_label = ttk.Label(self.filter_frame, text="Sembol filtresi:")
        self.filter_label.pack(side=tk.LEFT, padx=(0, 5))
        
        # Filtre giriş alanı
        self.filter_var = tk.StringVar()
        self.filter_entry = ttk.Entry(self.filter_frame, textvariable=self.filter_var)
        self.filter_entry.pack(side=tk.LEFT, padx=(0, 5), fill=tk.X, expand=True)
        self.filter_entry.bind("<Return>", lambda e: self.apply_filter())
        
        # Filtre uygula düğmesi
        self.apply_filter_button = ttk.Button(self.filter_frame, text="Uygula", command=self.apply_filter)
        self.apply_filter_button.pack(side=tk.LEFT, padx=5)
        
        # Filtre temizle düğmesi
        self.clear_filter_button = ttk.Button(self.filter_frame, text="Temizle", command=self.clear_filter)
        self.clear_filter_button.pack(side=tk.LEFT, padx=5)
        
        # Treeview (preferred stocks tablosu)
        self.create_stock_treeview()
        
        # Alt panel - sayfalama kontrolleri
        self.navigation_frame = ttk.Frame(self.main_frame)
        self.navigation_frame.pack(fill=tk.X, pady=(10, 0))
        
        # Önceki sayfa düğmesi
        self.prev_button = ttk.Button(self.navigation_frame, text="< Önceki Sayfa", command=self.prev_page)
        self.prev_button.pack(side=tk.LEFT)
        
        # Sayfa bilgisi
        self.page_info_label = ttk.Label(self.navigation_frame, text="Sayfa 1/1")
        self.page_info_label.pack(side=tk.LEFT, padx=20)
        
        # Sonraki sayfa düğmesi
        self.next_button = ttk.Button(self.navigation_frame, text="Sonraki Sayfa >", command=self.next_page)
        self.next_button.pack(side=tk.LEFT)
        
        # Son güncelleme zamanı
        self.last_update_label = ttk.Label(self.navigation_frame, text="Son güncelleme: -")
        self.last_update_label.pack(side=tk.RIGHT)

    def open_tracker(self):
        """Preferred Stock Tracker penceresini açar"""
        tracker = PreferredStockTracker()
        tracker.run()

    # ... (diğer tüm orijinal metodlar aynen kalacak)

def main():
    """Ana program başlangıcı"""
    app = PreferredStockMonitor()
    
    # Başlangıçta CSV yükle
    app.df = app.load_stocks_from_csv()
    
    # TreeView'ı doldur
    app.populate_treeview()
    
    # Kapatma olayını ayarla
    app.protocol("WM_DELETE_WINDOW", lambda: (app.disconnect_from_ibkr(), app.destroy()))
    
    # Uygulamayı başlat
    app.mainloop()

if __name__ == "__main__":
    main()
