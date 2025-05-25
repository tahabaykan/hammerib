import math
import json
import tkinter as tk
from tkinter import ttk, messagebox
import pandas as pd
import threading
import time
import queue
import pickle
import zlib
import base64
import datetime
import re
import os
import numpy as np
from collections import defaultdict
from PIL import Image, ImageTk
import matplotlib.pyplot as plt
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
from ib_insync import IB, Stock, Forex, util, MarketOrder, LimitOrder

# Helper function to safely format float values
def safe_format_float(value, format_str="{:.2f}"):
    """Safely format a potential float value, handling None, NaN, etc."""
    try:
        if value is None:
            return "0.00"
        
        # Convert to float and check if it's NaN
        val = float(value)
        if math.isnan(val):
            return "0.00"
            
        return format_str.format(val)
    except (ValueError, TypeError):
        return "0.00"

# Function to safely convert values to float
def safe_float(value, default=0.0):
    """Safely convert a value to float, returning default if conversion fails."""
    try:
        if value is None:
            return default
        val = float(value)
        if math.isnan(val):
            return default
        return val
    except (ValueError, TypeError):
        return default

# Function to safely convert values to int
def safe_int(value, default=0):
    """Safely convert a value to integer, returning default if conversion fails."""
    try:
        if value is None:
            return default
        # Önce float'a çevir, NaN kontrolü yap, sonra int'e çevir
        val = float(value)
        if math.isnan(val):
            return default
        return int(val)
    except (ValueError, TypeError):
        return default

class SpreadciDataWindow(tk.Toplevel):
    def __init__(self, parent):
        super().__init__(parent)
        self.title("Spreadci Data Monitor")
        self.geometry("1200x600")
        
        # IBKR bağlantısı
        self.ib = parent.ib  # Ana penceredeki IBKR bağlantısını kullan
        
        # Veri yönetimi
        self.tickers = {}  # Aktif abonelikler
        self.latest_data = defaultdict(dict)
        self.all_symbols = []  # Tüm semboller
        self.current_page = 0  # Mevcut sayfa
        self.symbols_per_page = 20  # Sayfa başına sembol sayısı
        self.running = True
        
        # UI oluştur
        self.setup_ui()
        
        # Verileri yükle
        self.load_data()
        
        # Event loop'u başlat
        self.after(100, self.run_event_loop)
        
    def setup_ui(self):
        # Ana frame
        self.main_frame = ttk.Frame(self)
        self.main_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)
        
        # Treeview
        self.tree = ttk.Treeview(self.main_frame)
        self.tree['columns'] = ('Symbol', 'Bid', 'Ask', 'Last', 'Volume', 'Spread', 'DIV AMOUNT')
        
        # Sütunları yapılandır
        self.tree.column('#0', width=0, stretch=tk.NO)
        self.tree.column('Symbol', anchor=tk.W, width=100)
        self.tree.column('Bid', anchor=tk.E, width=100)
        self.tree.column('Ask', anchor=tk.E, width=100)
        self.tree.column('Last', anchor=tk.E, width=100)
        self.tree.column('Volume', anchor=tk.E, width=100)
        self.tree.column('Spread', anchor=tk.E, width=100)
        self.tree.column('DIV AMOUNT', anchor=tk.E, width=100)
        
        # Başlıkları yapılandır
        self.tree.heading('Symbol', text='Symbol')
        self.tree.heading('Bid', text='Bid')
        self.tree.heading('Ask', text='Ask')
        self.tree.heading('Last', text='Last')
        self.tree.heading('Volume', text='Volume')
        self.tree.heading('Spread', text='Spread')
        self.tree.heading('DIV AMOUNT', text='DIV AMOUNT')
        
        # Scrollbar
        scrollbar = ttk.Scrollbar(self.main_frame, orient=tk.VERTICAL, command=self.tree.yview)
        self.tree.configure(yscrollcommand=scrollbar.set)
        
        # Yerleştirme
        self.tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        
        # Sayfalama kontrolleri
        self.nav_frame = ttk.Frame(self)
        self.nav_frame.pack(fill=tk.X, pady=5)
        
        self.prev_button = ttk.Button(self.nav_frame, text="Önceki Sayfa", command=self.prev_page)
        self.prev_button.pack(side=tk.LEFT, padx=5)
        
        self.next_button = ttk.Button(self.nav_frame, text="Sonraki Sayfa", command=self.next_page)
        self.next_button.pack(side=tk.LEFT, padx=5)
        
        self.page_label = ttk.Label(self.nav_frame, text="Sayfa: 1")
        self.page_label.pack(side=tk.LEFT, padx=20)
        
        # Son güncelleme zamanı
        self.last_update_label = ttk.Label(self.nav_frame, text="Son güncelleme: -")
        self.last_update_label.pack(side=tk.RIGHT)
    
    def load_data(self):
        try:
            # CSV'den verileri oku
            df = pd.read_csv('spreadci.csv')
            
            # Tüm sembolleri kaydet
            self.all_symbols = df[df['PREF IBKR'].notna()]['PREF IBKR'].tolist()
            
            # İlk sayfayı yükle
            self.current_page = 0
            self.load_page()
            
        except Exception as e:
            messagebox.showerror("Hata", f"Veri yüklenirken hata oluştu: {str(e)}")
    
    def load_page(self):
        # Mevcut abonelikleri temizle
        for symbol in self.tickers:
            self.ib.cancelMktData(self.tickers[symbol])
        self.tickers.clear()
        
        # Treeview'ı temizle
        for item in self.tree.get_children():
            self.tree.delete(item)
        
        # Sayfa için sembolleri al
        start_idx = self.current_page * self.symbols_per_page
        end_idx = start_idx + self.symbols_per_page
        page_symbols = self.all_symbols[start_idx:end_idx]
        
        # Her sembol için
        for symbol in page_symbols:
            contract = Stock(symbol, 'SMART', 'USD')
            self.tickers[symbol] = contract
            self.ib.reqMktData(contract)
            
            # Treeview'a ekle
            self.tree.insert('', tk.END, values=(
                symbol, '0.00', '0.00', '0.00', '0', '0.00', '0.00'
            ))
        
        # Sayfa bilgisini güncelle
        total_pages = math.ceil(len(self.all_symbols) / self.symbols_per_page)
        self.page_label.config(text=f"Sayfa: {self.current_page + 1}/{total_pages}")
        
        # Butonları güncelle
        self.prev_button.config(state=tk.NORMAL if self.current_page > 0 else tk.DISABLED)
        self.next_button.config(state=tk.NORMAL if self.current_page < total_pages - 1 else tk.DISABLED)
    
    def prev_page(self):
        if self.current_page > 0:
            self.current_page -= 1
            self.load_page()
    
    def next_page(self):
        total_pages = math.ceil(len(self.all_symbols) / self.symbols_per_page)
        if self.current_page < total_pages - 1:
            self.current_page += 1
            self.load_page()
    
    def run_event_loop(self):
        if self.running:
            try:
                # IBKR event loop'unu çalıştır
                self.ib.sleep(0.01)  # 10ms
                
                # Market verilerini işle
                self.process_market_data()
                
                # UI güncellemelerini planla
                self.after(0, self.update_ui)
                
            except Exception as e:
                print(f"Event loop error: {e}")
            
            # Bir sonraki iterasyonu planla
            self.after(10, self.run_event_loop)  # 10ms
    
    def process_market_data(self):
        updates = []
        for ticker in self.ib.tickers():
            if ticker.contract.symbol in self.tickers:
                updates.append({
                    'symbol': ticker.contract.symbol,
                    'bid': ticker.bid,
                    'ask': ticker.ask,
                    'last': ticker.last,
                    'volume': ticker.volume
                })
        
        # Toplu UI güncellemesi
        if updates:
            self.after(0, lambda: self.batch_update_ui(updates))
    
    def batch_update_ui(self, updates):
        """Toplu UI güncellemesi"""
        for update in updates:
            symbol = update['symbol']
            bid = update['bid']
            ask = update['ask']
            last = update['last']
            volume = update['volume']
            
            # Treeview'ı güncelle
            for item in self.stock_tree.get_children():
                if self.stock_tree.item(item)['values'][0] == symbol:
                    self.stock_tree.item(item, values=(
                        symbol,
                        f"{bid:.2f}",
                        f"{ask:.2f}",
                        f"{last:.2f}",
                        f"{volume}",
                        f"{self.latest_data[symbol].get('spread', '0.00')}",
                        f"{self.latest_data[symbol].get('div_amount', '0.00')}"
                    ))
        
        # Son güncelleme zamanını güncelle
        self.last_update_label.config(text=f"Son güncelleme: {time.strftime('%H:%M:%S')}")
    
    def update_ui(self):
        """Bu method batch_update_ui tarafından otomatik çağrılacağı için boş bırakılabilir"""
        pass
        
    def on_closing(self):
        """Pencere kapatılırken temizlik yap"""
        self.running = False
        for symbol in self.tickers:
            self.ib.cancelMktData(self.tickers[symbol])
        self.destroy()

class PreferredStockMonitor(tk.Tk):
    def __init__(self):
        """Uygulama başlatma ve ana verileri yükleme"""
        super().__init__()
        
        # En çok düşen ve yükselen hisseler için global cache
        self.global_ticker_cache = {
            'TLTR': {},  # TLTR hisseleri için
            'EXTLT': {}  # EXTLT hisseleri için
        }
        
        # Tüm hisselerin last close değerlerini saklama
        self.last_close_values = {
            'TLTR': {},  # TLTR hisseleri için
            'EXTLT': {}  # EXTLT hisseleri için
        }
        
        # Gelişmiş market data cache ve abonelik yönetimi
        self.market_data_cache = MarketDataCache()
        self.focused_symbols = set()  # Şu anda görüntülenen semboller
        self.page_data_snapshots = {}  # Sayfa bazlı veri snapshot'ları
        
        # Rotasyon için indeks
        self.rotation_index = 0
        self.rotation_batch_size = 20  # Her seferde 20 hisse
        
        # En çok düşen/yükselen listelerinin son güncellenme zamanı
        self.last_movers_update_time = None
        
        # Ana pencere özelliklerini ayarla
        self.title("Preferred Stock Monitor")
        self.geometry("1400x800")
        
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
        # Özel stil tanımlama
        self.style = ttk.Style()
        self.style.configure('Small.TButton', font=('Arial', 8))
        self.style.configure('Compact.TButton', padding=(2, 1), font=('Arial', 8))
        
        # Ana frame
        self.main_frame = ttk.Frame(self)
        self.main_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)
        
        # Üst kontrol paneli - iki satır kullanacağız
        self.control_frame = ttk.Frame(self.main_frame)
        self.control_frame.pack(fill=tk.X, pady=(0, 5))
        
        # Alt buton satırı
        self.button_frame2 = ttk.Frame(self.main_frame)
        self.button_frame2.pack(fill=tk.X, pady=(0, 5))
        
        # Bağlantı durumu etiketi
        self.status_label = ttk.Label(self.control_frame, text="Bağlantı durumu: Bağlı değil", font=('Arial', 8))
        self.status_label.pack(side=tk.LEFT, padx=(0, 5))
        
        # Bağlantı düğmesi
        self.connect_button = ttk.Button(self.control_frame, text="IBKR Bağlan", command=self.connect_to_ibkr, style='Compact.TButton')
        self.connect_button.pack(side=tk.LEFT, padx=1)
        
        # Bağlantıyı kes düğmesi
        self.disconnect_button = ttk.Button(self.control_frame, text="Bağlantıyı Kes", command=self.disconnect_from_ibkr, style='Compact.TButton')
        self.disconnect_button.pack(side=tk.LEFT, padx=1)
        
        # Pozisyonları görüntüleme düğmesi
        self.positions_button = ttk.Button(self.control_frame, text="Pozisyonlar", 
                                     command=self.show_positions, style='Compact.TButton')
        self.positions_button.pack(side=tk.LEFT, padx=1)
        self.positions_button.config(state=tk.DISABLED)  # Başlangıçta devre dışı
        
        # Opt50 Portföy butonu
        self.opt50_button = ttk.Button(self.control_frame, text="Opt50", 
                                 command=self.show_opt50_portfolio, style='Compact.TButton')
        self.opt50_button.pack(side=tk.LEFT, padx=1)
        
        # DIV Portföy butonu
        self.div_port_button = ttk.Button(self.control_frame, text="DIV", 
                                    command=self.show_div_portfolio, style='Compact.TButton')
        self.div_port_button.pack(side=tk.LEFT, padx=1)
        
        # ETF Listesi butonu
        self.etf_button = ttk.Button(self.control_frame, text="ETF", 
                                command=self.show_etf_list, style='Compact.TButton')
        self.etf_button.pack(side=tk.LEFT, padx=1)
        
        # Hidden Bid Placement butonu
        def on_hidden_bid_click():
            try:
                self.place_hidden_bids()
            except Exception as e:
                from tkinter import messagebox
                messagebox.showerror("Hata", f"Hidden Bid işlemi sırasında hata: {str(e)}")
                
        self.hidden_bid_button = ttk.Button(self.control_frame, text="Hidden Bid", 
                                      command=on_hidden_bid_click, style='Compact.TButton')
        self.hidden_bid_button.pack(side=tk.LEFT, padx=1)
        
        # Div Hidden Placement butonu
        def on_div_hidden_bid_click():
            try:
                self.place_div_hidden_bids()
            except Exception as e:
                from tkinter import messagebox
                messagebox.showerror("Hata", f"Div Hidden Bid işlemi sırasında hata: {str(e)}")
                
        self.div_hidden_bid_button = ttk.Button(self.control_frame, text="DIV Hidden", 
                                          command=on_div_hidden_bid_click, style='Compact.TButton')
        self.div_hidden_bid_button.pack(side=tk.LEFT, padx=1)
        
        # Take Profit Mechanism butonu - öne çıkardık
        def on_take_profit_click():
            try:
                self.manage_pff_spreads()
            except Exception as e:
                from tkinter import messagebox
                messagebox.showerror("Hata", f"Take Profit işlemi sırasında hata: {str(e)}")
                
        self.take_profit_button = ttk.Button(self.button_frame2, text="Take Profit", 
                                       command=on_take_profit_click, style='Compact.TButton')
        self.take_profit_button.pack(side=tk.LEFT, padx=1)
        
        # Emir Önizleme butonu
        def on_preview_orders_click():
            try:
                self.preview_hidden_bids()
            except Exception as e:
                from tkinter import messagebox
                messagebox.showerror("Hata", f"Emir önizleme işlemi sırasında hata: {str(e)}")
                
        self.preview_orders_button = ttk.Button(
            self.button_frame2, 
            text="Emir Önizleme", 
            command=on_preview_orders_click,
            style='Compact.TButton'
        )
        self.preview_orders_button.pack(side=tk.LEFT, padx=1)
        
        # Yenile düğmesi
        self.refresh_button = ttk.Button(self.button_frame2, text="Yenile", 
                                   command=self.force_refresh, style='Compact.TButton')
        self.refresh_button.pack(side=tk.LEFT, padx=1)
        
        # En Çok Düşenler butonu
        self.top_losers_button = ttk.Button(self.button_frame2, text="En Çok Düşenler", 
                                       command=self.show_top_movers, style='Compact.TButton')
        self.top_losers_button.pack(side=tk.LEFT, padx=1)
        
        # En Çok Yükselenler butonu
        self.top_gainers_button = ttk.Button(self.button_frame2, text="En Çok Yükselenler", 
                                        command=lambda: self.show_top_movers(show_gainers=True), 
                                        style='Compact.TButton')
        self.top_gainers_button.pack(side=tk.LEFT, padx=1)
        
        # Aktif abonelik sayısı etiketi
        self.subscription_count_label = ttk.Label(self.button_frame2, text="Aktif abonelikler: 0/40", font=('Arial', 8))
        self.subscription_count_label.pack(side=tk.RIGHT, padx=5)
        
        # Notebook (sekme yapısı)
        self.notebook = ttk.Notebook(self.main_frame)
        self.notebook.pack(fill=tk.BOTH, expand=True)
        
        # TLTR Prefs sekmesi
        self.tltr_frame = ttk.Frame(self.notebook)
        self.notebook.add(self.tltr_frame, text="TLTR Prefs")
        self.tltr_tree = self.create_simple_treeview(self.tltr_frame)
        
        # DIV Spread sekmesi
        self.divspread_frame = ttk.Frame(self.notebook)
        self.notebook.add(self.divspread_frame, text="DIV Spread")
        self.divspread_tree = self.create_simple_treeview(self.divspread_frame)
        
        # Alt panel - sayfalama kontrolleri
        self.navigation_frame = ttk.Frame(self.main_frame)
        self.navigation_frame.pack(fill=tk.X, pady=(10, 0))
        
        # Önceki sayfa düğmesi
        self.prev_button = ttk.Button(self.navigation_frame, text="< Önceki", command=self.prev_page, style='Compact.TButton')
        self.prev_button.pack(side=tk.LEFT)
        
        # Sayfa bilgisi
        self.page_info_label = ttk.Label(self.navigation_frame, text="Sayfa 1/1", font=('Arial', 8))
        self.page_info_label.pack(side=tk.LEFT, padx=10)
        
        # Sonraki sayfa düğmesi
        self.next_button = ttk.Button(self.navigation_frame, text="Sonraki >", command=self.next_page, style='Compact.TButton')
        self.next_button.pack(side=tk.LEFT)
        
        # Son güncelleme zamanı
        self.last_update_label = ttk.Label(self.navigation_frame, text="Son güncelleme: -", font=('Arial', 8))
        self.last_update_label.pack(side=tk.RIGHT)

        # Sekmelere özel ticker listelerini yükle
        self.load_tab_tickers()

        # Sekme değişimini dinle
        self.notebook.bind("<<NotebookTabChanged>>", self.on_tab_changed)

    def create_simple_treeview(self, parent):
        columns = ("Ticker", "last", "bid", "ask", "spread", "volume")
        tree = ttk.Treeview(parent, columns=columns, show="headings", height=20)
        headings = {
            "Ticker": "Ticker",
            "last": "Son",
            "bid": "Alış",
            "ask": "Satış",
            "spread": "Spread",
            "volume": "Hacim"
        }
        widths = {
            "Ticker": 100,
            "last": 80,
            "bid": 80,
            "ask": 80,
            "spread": 80,
            "volume": 100
        }
        for col in columns:
            tree.heading(col, text=headings[col])
            tree.column(col, width=widths[col], anchor="center")
        tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        return tree

    def load_tab_tickers(self):
        import pandas as pd
        # TLTR Prefs sekmesi için
        try:
            df_tltr = pd.read_csv("sma_results.csv")
            df_tltr = normalize_ticker_column(df_tltr)
            self.tltr_tickers = df_tltr["Ticker"].dropna().unique().tolist()
        except Exception as e:
            self.tltr_tickers = []
        # DIV Spread sekmesi için
        try:
            df_div = pd.read_csv("extlt_results.csv")
            df_div = normalize_ticker_column(df_div)
            self.divspread_tickers = df_div["Ticker"].dropna().unique().tolist()
        except Exception as e:
            self.divspread_tickers = []
        
        # Sayfalama değişkenleri
        self.tltr_current_page = 1
        self.divspread_current_page = 1
        self.items_per_page = 20
        
        # İlk sayfayı yükle - boş değerlerle
        self.populate_treeview()

    def load_stocks_from_csv(self, filename="final_thg_with_avg_adv.csv"):
        """CSV dosyasından hisse senetlerini yükle"""
        try:
            # CSV dosyasını oku
            df = pd.read_csv(filename)
            
            # Gerekli sütunları kontrol et
            required_columns = ["PREF IBKR", "CMON"]
            for column in required_columns:
                if column not in df.columns:
                    print(f"Uyarı: '{column}' sütunu CSV dosyasında bulunamadı!")
            
            print(f"{len(df)} hisse senedi yüklendi")
            return df
        except Exception as e:
            print(f"CSV yükleme hatası: {e}")
            # Boş DataFrame döndür
            return pd.DataFrame(columns=["PREF IBKR", "CMON"])
    
    def connect_to_ibkr(self):
        """IBKR'ye bağlan ve gerçek zamanlı veri akışını başlat"""
        if self.connected:
            print("Zaten bağlı")
            return
        
        try:
            print("IBKR bağlantısı kuruluyor...")
            self.ib = IB()
            
            # TWS ve Gateway portlarını dene
            ports = [7496, 4001]  # TWS ve Gateway portları
            connected = False
            
            for port in ports:
                try:
                    # Bağlantı kurarken event loop'u otomatik başlat
                    self.ib.connect('127.0.0.1', port, clientId=1, readonly=True)
                    connected = True
                    print(f"Port {port} ile bağlantı başarılı!")
                    break
                except Exception as e:
                    print(f"Port {port} bağlantı hatası: {e}")
            
            if not connected:
                print("Hiçbir porta bağlanılamadı! TWS veya Gateway çalışıyor mu?")
                return False
            
            # Delayed data (gerçek hesap yoksa)
            self.ib.reqMarketDataType(3)  
            
            # Event handler'ları ayarla
            self.ib.pendingTickersEvent += self.on_ticker_update
            self.ib.errorEvent += self.on_error
            self.ib.disconnectedEvent += self.on_disconnect
            self.connected = True
            self.running = True
            
            # Hisse verilerini yükle
            self.df = self.load_stocks_from_csv()
            if self.df.empty:
                print("Hisse verileri yüklenemedi!")
                self.disconnect_from_ibkr()
                return False
            
            # UI güncelle
            self.populate_treeview()
            self.update_status("Bağlı", True)
            
            # Görünen sayfa için abone ol
            self.subscribe_visible_tickers()
            
            # Common stock abonelikleri
            self.subscribe_common_stocks()
            
            # Tkinter'ın event loop'u ile çalışabilmesi için periyodik güncelleme
            self.after(100, self.update_ib)
            
            # 60 saniyede bir rotasyon başlat
            threading.Timer(60, self.rotate_subscriptions).start()
            
            # Tüm hisseler için rotasyonlu veri toplama başlat
            self.after(5000, self.rotate_ticker_data)
            
            return True
            
        except Exception as e:
            print(f"IBKR bağlantı hatası: {e}")
            self.update_status(f"Bağlantı hatası: {e}", False)
            return False
    
    def disconnect_from_ibkr(self):
        """IBKR bağlantısını kapat"""
        if not self.connected:
            return
        
        self.running = False
        
        # Tüm abonelikleri iptal et
        for ticker_info in self.tickers.values():
            if 'contract' in ticker_info:
                try:
                    self.ib.cancelMktData(ticker_info['contract'])
                except:
                    pass
        
        # Common stock aboneliklerini iptal et
        for ticker_info in self.common_tickers.values():
            if 'contract' in ticker_info:
                try:
                    self.ib.cancelMktData(ticker_info['contract'])
                except:
                    pass
        
        # Event handler'ları temizle
        if hasattr(self.ib, 'pendingTickersEvent'):
            try:
                util.clearEvents(self.ib.pendingTickersEvent)
            except Exception as e:
                print(f"Ticker events temizlenirken hata: {e}")
        
        if hasattr(self.ib, 'errorEvent'):
            try:
                util.clearEvents(self.ib.errorEvent)
            except Exception as e:
                print(f"Error events temizlenirken hata: {e}")
            
        if hasattr(self.ib, 'disconnectedEvent'):
            try:
                util.clearEvents(self.ib.disconnectedEvent)
            except Exception as e:
                print(f"Disconnect events temizlenirken hata: {e}")
        
        # Bağlantıyı kapat
        if self.ib and self.ib.isConnected():
            self.ib.disconnect()
        
        # Durumu güncelle
        self.connected = False
        self.update_status("Bağlı değil", False)
        
        # Tickers sözlüğünü temizle
        self.tickers = {}
        self.common_tickers = {}
        
        print("IBKR bağlantısı kapatıldı")
    
    def run_event_loop(self):
        if self.running:
            try:
                # IBKR event loop'unu çalıştır
                self.ib.sleep(0.01)  # 10ms
                
                # Market verilerini işle
                self.process_market_data()
                
                # UI güncellemelerini planla
                self.after(0, self.update_ui)
                
            except Exception as e:
                print(f"Event loop error: {e}")
            
            # Bir sonraki iterasyonu planla
            self.after(10, self.run_event_loop)  # 10ms
    
    def process_market_data(self):
        updates = []
        for ticker in self.ib.tickers():
            if ticker.contract.symbol in self.tickers:
                updates.append({
                    'symbol': ticker.contract.symbol,
                    'bid': ticker.bid,
                    'ask': ticker.ask,
                    'last': ticker.last,
                    'volume': ticker.volume
                })
        
        # Toplu UI güncellemesi
        if updates:
            self.after(0, lambda: self.batch_update_ui(updates))
    
    def batch_update_ui(self, updates):
        # Her iki treeview'ı da güncelle
        for tree in [self.tltr_tree, self.divspread_tree]:
            for item_id in tree.get_children():
                ticker = tree.item(item_id)["values"][0]
                if ticker in updates:
                    data = updates[ticker]
                    current_values = tree.item(item_id)["values"]
                    new_values = list(current_values)
                    new_values[1] = f"{data['last']:.2f}" if data['last'] else "-"
                    new_values[2] = f"{data['bid']:.2f}" if data['bid'] else "-"
                    new_values[3] = f"{data['ask']:.2f}" if data['ask'] else "-"
                    if data['bid'] and data['ask']:
                        spread = data['ask'] - data['bid']
                        new_values[4] = f"{spread:.2f}"
                    else:
                        new_values[4] = "-"
                    new_values[5] = f"{data['volume']:,}" if data['volume'] else "-"
                    tree.item(item_id, values=new_values)
                    tree.item(item_id, tags=('updated',))
                    self.after(1000, lambda t=tree, i=item_id: t.item(i, tags=()))
        self.last_update_label.config(text=f"Son güncelleme: {time.strftime('%H:%M:%S')}")
    
    def on_closing(self):
        """Pencere kapatılırken temizlik yap"""
        self.running = False
        for symbol in self.tickers:
            self.ib.cancelMktData(self.tickers[symbol])
        self.destroy()
    
    def update_status(self, status_text, is_connected=False):
        if is_connected:
            self.connect_button.config(state=tk.DISABLED)
            self.disconnect_button.config(state=tk.NORMAL)
            self.refresh_button.config(state=tk.NORMAL)
            self.positions_button.config(state=tk.NORMAL)  # Bağlıyken etkinleştir
            # Opt50 butonunu etkinleştirmeye gerek yok, her durumda etkin olabilir
        else:
            self.connect_button.config(state=tk.NORMAL)
            self.disconnect_button.config(state=tk.DISABLED)
            self.refresh_button.config(state=tk.DISABLED)
            self.positions_button.config(state=tk.DISABLED)  # Bağlı değilken devre dışı
            # Opt50 butonu her durumda etkin kalabilir, çünkü CSV verilerini gösterebilir
    
    def create_preferred_stock_contract(self, ticker_symbol):
        """Tercihli hisse senedi kontratı oluştur - Basitleştirilmiş yaklaşım"""
        try:
            # Tüm sembolleri basit Stock nesnesi olarak oluştur
            contract = Stock(symbol=ticker_symbol, exchange='SMART', currency='USD')
            return contract
        except Exception as e:
            print(f"Kontrat oluşturma hatası ({ticker_symbol}): {e}")
            return None
    
    def subscribe_visible_tickers(self):
        """Görünen sayfadaki hisselere abone ol"""
        if not self.connected or self.df is None or self.df.empty:
            print("Bağlantı veya veri yok, abonelik yapılamıyor")
            return False
        
        # Görünür sayfadaki hisseleri belirle
        visible_stocks = self.get_visible_stocks()
        
        # Geçersiz sembolleri izlemek için set oluştur
        if not hasattr(self, 'invalid_symbols'):
            self.invalid_symbols = set()
        
        # Mevcut abonelikleri iptal et
        for symbol in list(self.tickers.keys()):
            # Görünür sayfada değilse iptal et
            if symbol not in [stock['PREF IBKR'] for stock in visible_stocks]:
                try:
                    contract = self.tickers[symbol]['contract']
                    self.ib.cancelMktData(contract)
                    del self.tickers[symbol]
                    print(f"✓ {symbol} aboneliği iptal edildi (görünmüyor)")
                except Exception as e:
                    print(f"! {symbol} abonelik iptali hatası: {e}")
        
        # Maximum aktif ticker sayısı
        max_active_tickers = 50
        active_tickers = len(self.tickers)
        
        # Görünür sayfadaki yeni hisselere abone ol
        count = 0
        
        for idx, stock in enumerate(visible_stocks):
            ticker_symbol = stock['PREF IBKR']
            
            # Geçersiz sembol kontrolleri
            if ticker_symbol in self.tickers or ticker_symbol in self.invalid_symbols:
                continue
                
            if pd.isna(ticker_symbol) or ticker_symbol == '-':
                continue
            
            # Eğer aktif sembol limitine ulaştıysak durduralım
            if active_tickers >= max_active_tickers:
                print(f"⚠️ Aktif ticker limiti ({max_active_tickers}) aşıldı, abonelik süreci durduruldu.")
                print(f"Toplam {count} hisse için gerçek zamanlı abonelik başlatıldı")
                break
                        
            try:
                # Basit kontrat oluştur - tercihli hisseleri özel işleme almadan
                contract = Stock(symbol=ticker_symbol, exchange='SMART', currency='USD')
                
                # Market verisi için tick tipleri iste - BidAsk ve Last için
                self.ib.reqMktData(
                    contract, 
                    genericTickList="233,165,221",  # BidAsk + ek veriler
                    snapshot=False,  # Sürekli güncelleme iste
                    regulatorySnapshot=False
                )
                
                # Tickers sözlüğüne ekle
                self.tickers[ticker_symbol] = {
                    'contract': contract,
                    'row_id': ticker_symbol,  # TreeView için row ID
                    'subscription_time': time.time()  # Abonelik zamanını kaydedelim
                }
                
                count += 1
                active_tickers += 1
                print(f"✓ {ticker_symbol} için gerçek zamanlı abonelik başlatıldı ({active_tickers}/{max_active_tickers})")
                
                # Her 5 abonelikte bir API'nin işlemleri yapmasına zaman tanı
                if count % 5 == 0:
                    time.sleep(1.0)  # Daha uzun bekleme (0.5'ten 1.0'a çıkarıldı)
                    
            except Exception as e:
                print(f"! {ticker_symbol} abonelik hatası: {str(e)}")
                # Hatalı sembolleri takip et
                self.invalid_symbols.add(ticker_symbol)
        
        # Aktif abonelik sayısını güncelle
        total_subscriptions = len(self.tickers) + len(self.common_tickers)
        self.subscription_count_label.config(text=f"Aktif abonelikler: {total_subscriptions}/100")
        
        print(f"Toplam {count} görünür hisse için gerçek zamanlı abonelik başlatıldı")
        return True
    
    def subscribe_common_stocks(self):
        """Common stocks için abonelik başlat"""
        if not self.connected or self.df is None or self.df.empty:
            return
        
        # Ana thread'de olduğumuzdan emin olalım veya yeni bir event loop ayarlayalım
        try:
            if threading.current_thread() != threading.main_thread():
                # Eğer farklı bir thread'deyiz, event loop ayarla
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
        except Exception as e:
            print(f"Event loop ayarlama hatası: {e}")
        
        # Görünen sayfadaki hisseleri belirle
        visible_stocks = self.get_visible_stocks()
        
        # Görünür sayfadaki common stock'ları belirle
        common_symbols = []
        for stock in visible_stocks:
            if 'CMON' in stock and stock['CMON'] and pd.notna(stock['CMON']):
                common_symbol = stock['CMON']
                if common_symbol not in common_symbols:
                    common_symbols.append(common_symbol)
        
        # Görünmeyenlerin aboneliklerini iptal et
        for symbol in list(self.common_tickers.keys()):
            if symbol not in common_symbols:
                try:
                    contract = self.common_tickers[symbol]['contract']
                    self.ib.cancelMktData(contract)
                    del self.common_tickers[symbol]
                    print(f"✓ Common stock {symbol} aboneliği iptal edildi")
                except Exception as e:
                    print(f"! Common stock {symbol} abonelik iptali hatası: {e}")
        
        # Yeni abonelikler oluştur
        count = 0
        for symbol in common_symbols:
            # Zaten aboneyse atla
            if symbol in self.common_tickers:
                continue
                
            try:
                # Kontrat oluştur
                contract = Stock(symbol=symbol, exchange='SMART', currency='USD')
                
                # Market verisi iste (günlük % değişimi için)
                self.ib.reqMktData(
                    contract,
                    genericTickList="236",  # Günlük değişim
                    snapshot=False,
                    regulatorySnapshot=False
                )
                
                # Common tickers sözlüğüne ekle
                self.common_tickers[symbol] = {
                    'contract': contract,
                    'subscription_time': time.time()
                }
                
                count += 1
                print(f"✓ Common stock {symbol} için abonelik başlatıldı")
                
                # Her 2 abonelikte bir kısa bekle
                if count % 2 == 0:
                    time.sleep(0.2)
                    
            except Exception as e:
                print(f"! Common stock {symbol} abonelik hatası: {str(e)}")
        
        # Aktif abonelik sayısını güncelle
        total_subscriptions = len(self.tickers) + len(self.common_tickers)
        self.subscription_count_label.config(text=f"Aktif abonelikler: {total_subscriptions}/100")
        
        print(f"Toplam {count} common stock için abonelik başlatıldı")
        return True
    
    def rotate_subscriptions(self):
        """Abonelikleri döngüsel olarak yenile"""
        if not self.running or not self.connected:
            return
        
        try:
            # Görünen sayfadaki sembolleri her zaman aktif tut
            visible_symbols = [row['PREF IBKR'] for row in self.get_visible_stocks()]
            
            # Diğer abonelikleri yönet (görünen sayfada olmayanlar)
            other_tickers = {s: info for s, info in self.tickers.items() if s not in visible_symbols}
            
            # En eski abonelikleri bul ve iptal et (bu işlemi ana thread'e gönder)
            if other_tickers:
                # En eski 5 aboneliği iptal et
                ticker_ages = [(symbol, info['subscription_time']) 
                            for symbol, info in other_tickers.items()]
                ticker_ages.sort(key=lambda x: x[1])  # En eskiden yeniye sırala
                
                cancel_count = min(5, len(ticker_ages))
                for symbol, _ in ticker_ages[:cancel_count]:
                    try:
                        contract = self.tickers[symbol]['contract']
                        # API çağrısını kuyruğa ekle
                        self.queue_api_call(self.ib.cancelMktData, contract)
                        del self.tickers[symbol]
                        print(f"✓ {symbol} aboneliği iptal edildi (rotasyon)")
                    except Exception as e:
                        print(f"! {symbol} abonelik iptali hatası: {e}")
            
            # Yeni abonelikler ekle...
            # (benzer şekilde diğer API çağrılarını queue_api_call ile yap)
            
            # Bir sonraki rotasyon için zamanlayıcı kur
            if self.running:
                threading.Timer(30, self.rotate_subscriptions).start()
                
        except Exception as e:
            print(f"Rotasyon hatası: {e}")
    
    def on_ticker_update(self, tickers):
        """Ticker güncellemelerinde çağrılacak callback (her iki sekme için)"""
        for ticker in tickers:
            symbol = None
            if hasattr(ticker.contract, 'localSymbol') and ticker.contract.localSymbol:
                symbol = ticker.contract.localSymbol
            else:
                symbol = ticker.contract.symbol

            # Market data cache'e ekle (her sembol için veriyi sakla)
            self.market_data_cache.update(symbol, ticker)
            
            # Sadece şu anda odaklanılan (görüntülenen) semboller için UI güncellemesi yap
            if symbol not in self.focused_symbols:
                continue

            # TLTR Prefs sekmesi için
            if hasattr(self, 'tltr_tickers') and symbol in self.tltr_tickers:
                tree = self.tltr_tree
            # DIV Spread sekmesi için
            elif hasattr(self, 'divspread_tickers') and symbol in self.divspread_tickers:
                tree = self.divspread_tree
            else:
                continue

            # TreeView'daki ilgili satırı bul ve güncelle
            for item_id in tree.get_children():
                item_values = tree.item(item_id, "values")
                if item_values and item_values[0] == symbol:
                    values = list(item_values)
                    # Fiyatlar
                    if ticker.last is not None and not (isinstance(ticker.last, float) and (ticker.last != ticker.last)):
                        values[1] = f"{ticker.last:.2f}"
                    if ticker.bid is not None and not (isinstance(ticker.bid, float) and (ticker.bid != ticker.bid)):
                        values[2] = f"{ticker.bid:.2f}"
                    if ticker.ask is not None and not (isinstance(ticker.ask, float) and (ticker.ask != ticker.ask)):
                        values[3] = f"{ticker.ask:.2f}"
                    # Spread
                    if (ticker.bid is not None and not (isinstance(ticker.bid, float) and (ticker.bid != ticker.bid)) and
                        ticker.ask is not None and not (isinstance(ticker.ask, float) and (ticker.ask != ticker.ask))):
                        spread = ticker.ask - ticker.bid
                        values[4] = f"{spread:.2f}"
                    # Hacim
                    if ticker.volume is not None and not (isinstance(ticker.volume, float) and (ticker.volume != ticker.volume)):
                        values[5] = f"{int(ticker.volume):,}"
                    tree.item(item_id, values=values, tags=('updated',))
                    # Güvenli bir şekilde renk değişimini geri al 
                    # (Item kaybolmuşsa çağrılmayacak şekilde try-except ile sarmalıyoruz)
                    self.after(1000, lambda t=tree, i=item_id: self.safe_reset_tags(t, i))
                    break
                    
        # Son güncelleme zamanını güncelle
        self.last_update_label.config(text=f"Son güncelleme: {time.strftime('%H:%M:%S')}")
        
    def safe_reset_tags(self, tree, item_id):
        """Item'ı güvenli bir şekilde güncelleyen yardımcı metod"""
        try:
            tree.item(item_id, tags=())
        except Exception:
            # Item artık mevcut değilse sessizce devam et
            pass
    
    def update_common_stock_changes(self, common_symbol, change_percent):
        """İlgili preferred stock satırlarında common stock değişimini güncelle"""
        # Tüm görünür preferred stock'ları kontrol et
        for item_id in self.stock_tree.get_children():
            values = list(self.stock_tree.item(item_id, "values"))
            pref_symbol = values[0]
            
            # Bu preferred stock'ın ilişkili common stock'ı bu mu?
            for _, row in self.df.iterrows():
                if row['PREF IBKR'] == pref_symbol and row['CMON'] == common_symbol:
                    # Common stock değişimini güncelle
                    values[6] = f"{change_percent:.2f}%"
                    self.stock_tree.item(item_id, values=values)
                    
                    # Artış/düşüş durumuna göre renk tag'i uygula
                    if change_percent > 0:
                        self.stock_tree.item(item_id, tags=('common_up',))
                    elif change_percent < 0:
                        self.stock_tree.item(item_id, tags=('common_down',))
                    break
    
    def on_error(self, reqId, errorCode, errorString, contract):
        """IBKR API hata mesajları"""
        # Bazı yaygın bilgi mesajlarını görmezden gel
        ignore_codes = [2104, 2106, 2158]
        if errorCode in ignore_codes:
            return
            
        if contract:
            symbol = contract.localSymbol or contract.symbol
            print(f"! Hata ({symbol}): {errorString} (Kod: {errorCode})")
        else:
            print(f"! Genel hata: {errorString} (Kod: {errorCode})")
    
    def on_disconnect(self):
        """Bağlantı koptuğunda çağrılacak callback"""
        if not self.connected:
            return
            
        print("! IBKR bağlantısı koptu!")
        self.connected = False
        self.update_status("Bağlantı koptu", False)
        
        # Yeniden bağlanma girişimi
        if self.running:
            print("Yeniden bağlanma deneniyor...")
            threading.Timer(5, self.connect_to_ibkr).start()
    
    def on_tree_select(self, event):
        """TreeView'da satır seçildiğinde çağrılacak callback"""
        # Seçili satırı al
        selected_items = self.stock_tree.selection()
        if not selected_items:
            return
            
        item_id = selected_items[0]
        values = self.stock_tree.item(item_id, "values")
        if not values:
            return
            
        # Seçilen hissenin sembolü
        selected_symbol = values[0]
        print(f"Seçili hisse: {selected_symbol}")
        
        # Burada seçili hisse ile ilgili ek işlemler yapabilirsiniz
        # Örneğin, detaylı bilgileri gösterme, grafik çizme vb.
    
    def sort_treeview(self, column):
        """TreeView sütununa göre sıralama yap"""
        # Mevcut sıralama durumunu kontrol et
        if self.sort_column == column:
            self.sort_reverse = not self.sort_reverse
        else:
            self.sort_column = column
            self.sort_reverse = False
        
        # Sütun başlıklarını güncelle (sıralama okunun gösterimi için)
        for col in self.stock_tree["columns"]:
            if col == column:
                direction = " ▼" if self.sort_reverse else " ▲"
                self.stock_tree.heading(col, text=self.get_column_title(col) + direction)
            else:
                self.stock_tree.heading(col, text=self.get_column_title(col))
        
        # UI'yı güncelle
        self.populate_treeview()

    def get_column_title(self, column):
        """Sütun adına göre başlık metnini döndür (ok işaretleri olmadan)"""
        titles = {
            "ticker": "Ticker",
            "last": "Last Price",
            "bid": "Bid",
            "ask": "Ask",
            "spread": "Spread ¢",  # % -> ¢
            "volume": "Volume",
            "common_change": "Common Stock Chg%"
        }
        return titles.get(column, column)
    
    def apply_filter(self):
        """Filtreyi uygula"""
        self.filter_text = self.filter_var.get().lower()
        self.current_page = 1  # İlk sayfaya dön
        self.populate_treeview()
        
        # Filtre uygulanınca görünür sembollere abone ol
        if self.connected:
            self.subscribe_visible_tickers()
            self.subscribe_common_stocks()
    
    def clear_filter(self):
        """Filtreyi temizle"""
        self.filter_var.set("")
        self.filter_text = ""
        self.current_page = 1  # İlk sayfaya dön
        self.populate_treeview()
        
        # Filtre temizlenince görünür sembollere abone ol
        if self.connected:
            self.subscribe_visible_tickers()
            self.subscribe_common_stocks()
    
    def prev_page(self):
        """Önceki sayfaya geç"""
        print("\n--- Önceki sayfaya geçiliyor ---")
        
        # Eski abonelikleri takip et
        old_symbols = self.focused_symbols.copy()
        # Odaklanılan sembolleri temizle
        self.focused_symbols.clear()
        
        # Aktif sekmeyi belirle
        current_tab = self.notebook.index(self.notebook.select()) if self.notebook.select() else 0
        
        # Sayfa numarasını güncelle
        page_changed = False
        if current_tab == 0:  # TLTR Prefs sekmesi
            tickers = self.tltr_tickers
            if self.tltr_current_page > 1:
                self.tltr_current_page -= 1
                page_changed = True
        else:  # DIV Spread sekmesi
            tickers = self.divspread_tickers
            if self.divspread_current_page > 1:
                self.divspread_current_page -= 1
                page_changed = True
        
        # Sayfa değişmediyse (ilk sayfadaysak) işlem yapma
        if not page_changed:
            print("Zaten ilk sayfadasınız")
            return
            
        # Sayfa değiştiyse eski odaklanılan sembollerin aboneliklerini iptal et
        for symbol in old_symbols:
            self.market_data_cache.remove_subscription(symbol, self.ib)
            
        print(f"Sayfa değişti: Tab {current_tab}, Sayfa {self.tltr_current_page if current_tab == 0 else self.divspread_current_page}")
        
        # Yeni sayfa için cache anahtarı oluştur
        page_key = f"page_{current_tab}_{self.tltr_current_page if current_tab == 0 else self.divspread_current_page}"
        
        # Eğer bu sayfa cache'de varsa, kullan
        if page_key in self.page_data_snapshots and time.time() - self.page_data_snapshots[page_key]['last_update'] < 300:
            # Cache'deki verileri kullan
            page_data = self.page_data_snapshots[page_key]
            new_symbols = list(page_data['symbols'])
            print(f"Cache kullanılıyor: {page_key} - {len(new_symbols)} sembol")
            self.populate_treeview_from_cache(current_tab, new_symbols)
        else:
            # Cache yok veya eski, normal populate işlemi yap
            print(f"Yeni veri çekiliyor: {page_key}")
            self.populate_treeview()
            
        # Abonelik sayısını güncelle
        self.subscription_count_label.config(text=f"Aktif abonelikler: {len(self.market_data_cache.active_subscriptions)}/40")
    
    def next_page(self):
        """Sonraki sayfaya geç"""
        print("\n--- Sonraki sayfaya geçiliyor ---")
        
        # Eski abonelikleri takip et
        old_symbols = self.focused_symbols.copy()
        # Odaklanılan sembolleri temizle
        self.focused_symbols.clear()
        
        # Aktif sekmeyi belirle
        current_tab = self.notebook.index(self.notebook.select()) if self.notebook.select() else 0
        
        # Sayfa numarasını güncelle
        page_changed = False
        if current_tab == 0:  # TLTR Prefs sekmesi
            tickers = self.tltr_tickers
            total_pages = max(1, math.ceil(len(tickers) / self.items_per_page))
            if self.tltr_current_page < total_pages:
                self.tltr_current_page += 1
                page_changed = True
        else:  # DIV Spread sekmesi
            tickers = self.divspread_tickers
            total_pages = max(1, math.ceil(len(tickers) / self.items_per_page))
            if self.divspread_current_page < total_pages:
                self.divspread_current_page += 1
                page_changed = True
        
        # Sayfa değişmediyse (son sayfadaysak) işlem yapma
        if not page_changed:
            print("Zaten son sayfadasınız")
            return
            
        # Sayfa değiştiyse eski odaklanılan sembollerin aboneliklerini iptal et
        for symbol in old_symbols:
            self.market_data_cache.remove_subscription(symbol, self.ib)
            
        print(f"Sayfa değişti: Tab {current_tab}, Sayfa {self.tltr_current_page if current_tab == 0 else self.divspread_current_page}")
        
        # Yeni sayfa için cache anahtarı oluştur
        page_key = f"page_{current_tab}_{self.tltr_current_page if current_tab == 0 else self.divspread_current_page}"
        
        # Eğer bu sayfa cache'de varsa, kullan
        if page_key in self.page_data_snapshots and time.time() - self.page_data_snapshots[page_key]['last_update'] < 300:
            # Cache'deki verileri kullan
            page_data = self.page_data_snapshots[page_key]
            new_symbols = list(page_data['symbols'])
            print(f"Cache kullanılıyor: {page_key} - {len(new_symbols)} sembol")
            self.populate_treeview_from_cache(current_tab, new_symbols)
        else:
            # Cache yok veya eski, normal populate işlemi yap
            print(f"Yeni veri çekiliyor: {page_key}")
            self.populate_treeview()
            
        # Abonelik sayısını güncelle
        self.subscription_count_label.config(text=f"Aktif abonelikler: {len(self.market_data_cache.active_subscriptions)}/40")
    
    def clear_subscriptions(self):
        """Tüm market data aboneliklerini temizle ve cache sistemini kullan"""
        # Eski yöntemle yapılan abonelikleri temizle
        for ticker_info in list(self.tickers.values()):
            if 'contract' in ticker_info:
                try:
                    self.ib.cancelMktData(ticker_info['contract'])
                except Exception as e:
                    print(f"Abonelik iptali hatası: {e}")
                    
        # Cache sistemindeki tüm abonelikleri temizle
        if hasattr(self, 'market_data_cache'):
            self.market_data_cache.clear_all_subscriptions(self.ib)
            
        # Tickers sözlüğünü temizle
        self.tickers = {}
        
        # Odaklanılan sembolleri temizle
        if hasattr(self, 'focused_symbols'):
            self.focused_symbols.clear()
            
        # Abonelik sayısı etiketini güncelle
        if hasattr(self, 'subscription_count_label'):
            self.subscription_count_label.config(text="Aktif abonelikler: 0/50")
    
    def get_visible_stocks(self):
        """Görünür sayfadaki hisseleri belirle"""
        if self.df is None or self.df.empty:
            return []
        
        # Filtreyi uygula
        filtered_df = self.df
        if self.filter_text:
            # PREF IBKR ve CMON sütunlarında ara
            mask = (
                filtered_df['PREF IBKR'].astype(str).str.lower().str.contains(self.filter_text, na=False) |
                filtered_df['CMON'].astype(str).str.lower().str.contains(self.filter_text, na=False)
            )
            filtered_df = filtered_df[mask]
        
        # Sıralama uygula
        if self.sort_column:
            ascending = not self.sort_reverse
            if self.sort_column == "ticker":
                filtered_df = filtered_df.sort_values("PREF IBKR", ascending=ascending)
            elif self.sort_column == "common_change":
                # CMON sütununa göre sırala (eğer latest_data üzerinden sıralama yapmak istiyorsak
                # bu parçayı populate_treeview'a taşıyabiliriz)
                filtered_df = filtered_df.sort_values("CMON", ascending=ascending)
        
        # Toplam sayfa sayısını hesapla
        total_items = len(filtered_df)
        self.total_pages = max(1, math.ceil(total_items / self.items_per_page))
        
        # Geçerli sayfa numarasını kontrol et
        if self.current_page > self.total_pages:
            self.current_page = self.total_pages
        
        # Görünür hisseleri belirle
        start_idx = (self.current_page - 1) * self.items_per_page
        end_idx = min(start_idx + self.items_per_page, total_items)
        
        # DataFrame'i dictionary listesine dönüştür
        visible_stocks = filtered_df.iloc[start_idx:end_idx].to_dict("records")
        
        # Sayfa bilgisini güncelle
        self.page_info_label.config(text=f"Sayfa {self.current_page}/{self.total_pages}")
        
        return visible_stocks
    
    def populate_treeview(self):
        """Her iki sekme için treeview'ları doldur"""
        # Aktif sekmeyi belirle
        current_tab = self.notebook.index(self.notebook.select()) if self.notebook.select() else 0
        
        if current_tab == 0:  # TLTR Prefs sekmesi
            tree = self.tltr_tree
            tickers = self.tltr_tickers
            current_page = self.tltr_current_page
        else:  # DIV Spread sekmesi
            tree = self.divspread_tree
            tickers = self.divspread_tickers
            current_page = self.divspread_current_page
        
        # Sayfalama için indeks hesapla
        start_idx = (current_page - 1) * self.items_per_page
        end_idx = start_idx + self.items_per_page
        
        # Sayfa için toplam sayfa sayısını hesapla
        total_pages = max(1, math.ceil(len(tickers) / self.items_per_page))
        
        # Sayfadaki tickers'ları al
        page_tickers = tickers[start_idx:min(end_idx, len(tickers))]
        
        # Mevcut treeview içeriğini temizle
        for row in tree.get_children():
            tree.delete(row)
        
        # Sayfadaki tickerları ekle
        for t in page_tickers:
            tree.insert("", "end", values=(t, "-", "-", "-", "-", "-"))
        
        # Sayfa bilgisini güncelle
        self.page_info_label.config(text=f"Sayfa {current_page}/{total_pages}")
        
        # Sayfa geçiş butonlarını güncelle
        self.prev_button.config(state=tk.NORMAL if current_page > 1 else tk.DISABLED)
        self.next_button.config(state=tk.NORMAL if current_page < total_pages else tk.DISABLED)
        
        # Görünen ticker'lar için abonelik başlat
        if self.connected:
            self.subscribe_page_tickers(page_tickers)
    
    def subscribe_page_tickers(self, tickers):
        """Sayfa sembolleri için abonelik başlat, cache sistemini kullanarak"""
        if not self.connected:
            return
            
        # Ticker listesini normalize et - dictionary gelmesi durumunu kontrol et
        normalized_tickers = []
        for ticker in tickers:
            # String ticker doğrudan ekle
            if isinstance(ticker, str):
                normalized_tickers.append(ticker)
            # Dictionary kontrolü - farklı key yapılarını kontrol et
            elif isinstance(ticker, dict):
                # Olası sembol anahtarlarını kontrol et
                if 'symbol' in ticker:
                    normalized_tickers.append(ticker['symbol'])
                elif 'PREF IBKR' in ticker:
                    normalized_tickers.append(ticker['PREF IBKR'])
                elif 'Ticker' in ticker:
                    normalized_tickers.append(ticker['Ticker'])
                # Debug için dictionary içeriğini görüntüle (gerektiğinde)
                else:
                    keys_str = ", ".join(str(k) for k in ticker.keys())
                    print(f"Dictionary anahtarları: {keys_str}")
                    # Manüel olarak dictionary'den bilgi çıkarmaya çalış
                    values_str = []
                    for k, v in ticker.items():
                        if isinstance(v, str) and len(v) < 10:
                            values_str.append(f"{k}={v}")
                    if values_str:
                        print(f"Muhtemel sembol değerleri: {', '.join(values_str)}")
            else:
                # Geçersiz türleri atla
                print(f"Uyarı: Geçersiz ticker tipi: {type(ticker)}")
                continue
        
        # En az bir geçerli ticker olduğuna emin ol
        if not normalized_tickers:
            print("Uyarı: Geçerli ticker bulunamadı")
            return
            
        # Önce eski odaklanmış sembolleri unsubscribe et
        for old_symbol in self.focused_symbols.copy():
            if old_symbol not in normalized_tickers:
                # Bu sembol artık görünmüyor, aboneliği iptal et
                for ticker_info in list(self.tickers.values()):
                    if 'contract' in ticker_info and ticker_info.get('symbol') == old_symbol:
                        try:
                            self.market_data_cache.remove_subscription(old_symbol, self.ib)
                            del self.tickers[old_symbol]
                        except Exception as e:
                            print(f"Abonelik iptal hatası ({old_symbol}): {e}")
                
                # Focused sembollerden çıkar
                self.focused_symbols.discard(old_symbol)
        
        # Snapshot oluştur veya güncelle
        page_key = f"page_{self.active_tab}_{normalized_tickers[0] if normalized_tickers else 'empty'}"
        if page_key not in self.page_data_snapshots:
            self.page_data_snapshots[page_key] = {'symbols': set(normalized_tickers), 'last_update': time.time()}
        else:
            self.page_data_snapshots[page_key]['symbols'] = set(normalized_tickers)
            self.page_data_snapshots[page_key]['last_update'] = time.time()
        
        # Yeni semboller için abonelik başlat
        for symbol in normalized_tickers:
            if not symbol:
                continue
                
            try:
                # Sembolü odaklanmış semboller listesine ekle
                self.focused_symbols.add(symbol)
                
                # Sözlükte yoksa ekle
                if symbol not in self.tickers:
                    contract = Stock(symbol, 'SMART', 'USD')
                    self.tickers[symbol] = {'contract': contract, 'symbol': symbol}
                    # Cache sistemini kullanarak aboneliği başlat
                    self.market_data_cache.add_subscription(symbol, contract, self.ib)
                    
                # Bu sembolü öncelikli hale getir
                contract = self.tickers[symbol]['contract']
                self.market_data_cache.prioritize_symbol(symbol)
                
            except Exception as e:
                print(f"Abonelik hatası ({symbol}): {e}")
                
        # Aktif abonelik sayısını güncelle
        self.subscription_count_label.config(text=f"Aktif abonelikler: {len(self.market_data_cache.active_subscriptions)}/50")
    
    def force_refresh(self):
        """Verileri zorla yenile"""
        if not self.connected:
            print("IBKR'ye bağlı değil, yenileme yapılamıyor")
            return
        
        # Mevcut abonelikleri iptal et - Preferred Stocks
        for ticker_info in list(self.tickers.values()):
            if 'contract' in ticker_info:
                try:
                    self.ib.cancelMktData(ticker_info['contract'])
                except Exception as e:
                    print(f"Abonelik iptal hatası: {e}")
        
        # Common Stocks aboneliklerini iptal et
        for ticker_info in list(self.common_tickers.values()):
            if 'contract' in ticker_info:
                try:
                    self.ib.cancelMktData(ticker_info['contract'])
                except Exception as e:
                    print(f"Common stock abonelik iptal hatası: {e}")
        
        # Tickers sözlüklerini temizle
        self.tickers = {}
        self.common_tickers = {}
        
        # Yeniden abone ol
        self.subscribe_visible_tickers()
        self.subscribe_common_stocks()
        
        print("Veriler yenileniyor...")
    
    def update_ib(self):
        """IB event loop'unu güncelle"""
        if not self.connected or not self.ib or not self.ib.isConnected():
            self.after(100, self.update_ib)
            return
        
        try:
            self.ib.sleep(0.01)  # 10ms bekle
        except Exception as e:
            print(f"IB güncelleme hatası: {e}")
        finally:
            # Kendini tekrar zamanla
            self.after(100, self.update_ib)
            
    def rotate_ticker_data(self):
        """Tüm hisseleri rotasyonlu olarak alıp cache'de sakla"""
        if not self.connected or not self.ib or not self.ib.isConnected():
            self.after(60000, self.rotate_ticker_data)  # 1 dakika sonra tekrar dene
            return
        
        try:
            # Önce mevcut aboneleri kaydet ve temizle (Rotasyon öncesi)
            current_tickers = self.get_visible_stocks()
            self.clear_subscriptions()
            
            # Tüm ticker listelerini al
            all_tltr_tickers = self.tltr_tickers
            all_extlt_tickers = self.divspread_tickers
            
            # Başlangıç ve bitiş indislerini hesapla
            start_idx = self.rotation_index
            end_idx = min(start_idx + self.rotation_batch_size, 
                          max(len(all_tltr_tickers), len(all_extlt_tickers)))
            
            # Bu batch'teki TLTR tickerları
            if start_idx < len(all_tltr_tickers):
                batch_tltr = all_tltr_tickers[start_idx:min(end_idx, len(all_tltr_tickers))]
                print(f"TLTR rotasyon batch {start_idx}:{end_idx} - {len(batch_tltr)} hisse")
                
                for ticker in batch_tltr:
                    contract = self.create_preferred_stock_contract(ticker)
                    if contract:
                        self.ib.reqMarketDataType(3)  # Delayed data
                        self.ib.reqMktData(contract, '', False, False)
            
            # Bu batch'teki EXTLT tickerları
            if start_idx < len(all_extlt_tickers):
                batch_extlt = all_extlt_tickers[start_idx:min(end_idx, len(all_extlt_tickers))]
                print(f"EXTLT rotasyon batch {start_idx}:{end_idx} - {len(batch_extlt)} hisse")
                
                for ticker in batch_extlt:
                    contract = self.create_preferred_stock_contract(ticker)
                    if contract:
                        self.ib.reqMarketDataType(3)  # Delayed data
                        self.ib.reqMktData(contract, '', False, False)
            
            # Bir sonraki rotasyon için indeksi güncelle
            self.rotation_index = end_idx
            
            # Eğer tüm hisseleri taradıysak, başa dön
            if self.rotation_index >= max(len(all_tltr_tickers), len(all_extlt_tickers)):
                self.rotation_index = 0
                print("Rotasyon tamamlandı, başa dönülüyor")
            
            # 5 saniye bekle ve ardından verileri cache'e yaz
            self.after(5000, self.update_ticker_cache)
            
            # Mevcut görüntülenen hisseleri geri yükle
            self.after(6000, lambda: self.subscribe_page_tickers(current_tickers))
            
            # Bir sonraki rotasyonu zamanla (30 saniye sonra)
            self.after(30000, self.rotate_ticker_data)
        
        except Exception as e:
            print(f"Rotasyon hatası: {e}")
            # Hata durumunda bir sonraki rotasyonu zamanla
            self.after(60000, self.rotate_ticker_data)  # 1 dakika sonra tekrar dene
        finally:
            # Bu boş finally bloğu linter hatası için eklendi
            pass
            
    def update_ticker_cache(self):
        """Rotasyondaki hisseler için verileri cache'e kaydet"""
        if not self.connected or not self.ib:
            return
            
        try:
            # IB'den gelen tüm ticker verilerini işle
            for ticker in self.ib.tickers():
                symbol = ticker.contract.symbol
                
                # Ticker verilerini oku
                if ticker.last is None or math.isnan(ticker.last):
                    continue
                    
                # Close değeri için kontrol
                close_price = ticker.close if hasattr(ticker, 'close') and ticker.close is not None else ticker.last
                
                # Daily change hesapla
                if close_price and close_price > 0:
                    daily_change_cents = (ticker.last - close_price) * 100  # cent bazında
                else:
                    daily_change_cents = 0
                
                # Cache'e kaydet
                ticker_data = {
                    'symbol': symbol,
                    'last': ticker.last,
                    'bid': ticker.bid if hasattr(ticker, 'bid') and ticker.bid is not None else 0,
                    'ask': ticker.ask if hasattr(ticker, 'ask') and ticker.ask is not None else 0,
                    'spread': (ticker.ask - ticker.bid) if hasattr(ticker, 'ask') and hasattr(ticker, 'bid') and ticker.ask is not None and ticker.bid is not None else 0,
                    'volume': ticker.volume if hasattr(ticker, 'volume') and ticker.volume is not None else 0,
                    'daily_change_cents': daily_change_cents,
                    'close': close_price,
                    'last_update': time.time()  # datetime yerine time.time() kullan
                }
                
                # TLTR mi EXTLT mi belirle
                if symbol in self.tltr_tickers:
                    self.global_ticker_cache['TLTR'][symbol] = ticker_data
                    self.last_close_values['TLTR'][symbol] = close_price
                elif symbol in self.divspread_tickers:
                    self.global_ticker_cache['EXTLT'][symbol] = ticker_data
                    self.last_close_values['EXTLT'][symbol] = close_price
            
            # Abonelikleri temizle
            for ticker in self.ib.tickers():
                self.ib.cancelMktData(ticker.contract)
                
            print(f"Ticker cache güncellendi - TLTR: {len(self.global_ticker_cache['TLTR'])}, EXTLT: {len(self.global_ticker_cache['EXTLT'])}")
            
        except Exception as e:
            print(f"Cache güncelleme hatası: {e}")
            
    def show_top_movers(self, show_gainers=False):
        """En çok düşen veya yükselen hisseleri göster"""
        from tkinter import messagebox
        import math
        from datetime import datetime
        
        try:
            if len(self.global_ticker_cache['TLTR']) < 10 or len(self.global_ticker_cache['EXTLT']) < 10:
                # Eğer yeterli veri yoksa, rotasyonu başlat
                if not hasattr(self, 'movers_loading_shown'):
                    messagebox.showinfo("Bilgi", "Hisse verileri toplanıyor. Lütfen bekleyin ve birazdan tekrar deneyin.")
                    self.movers_loading_shown = True
                    
                if not self.last_movers_update_time or (datetime.now() - self.last_movers_update_time).total_seconds() > 60:
                    self.rotate_ticker_data()  # Veri toplamayı başlat
                    self.last_movers_update_time = datetime.now()
                return
                
            # En çok düşen/yükselen hisseleri bul
            tltr_movers = []
            extlt_movers = []
            
            # TLTR hisseleri
            for symbol, data in self.global_ticker_cache['TLTR'].items():
                # Geçerli veri kontrolü
                if 'daily_change_cents' in data and data['last'] is not None and not math.isnan(safe_float(data['daily_change_cents'])):
                    data_copy = data.copy()  # Orijinal veriyi değiştirmemek için kopya oluştur
                    # NaN ve None değerleri güvenli varsayılan değerlerle değiştir
                    for key in data_copy:
                        if isinstance(data_copy[key], (int, float)) and (data_copy[key] is None or math.isnan(data_copy[key])):
                            data_copy[key] = 0.0
                    tltr_movers.append(data_copy)
                    
            # EXTLT hisseleri
            for symbol, data in self.global_ticker_cache['EXTLT'].items():
                # Geçerli veri kontrolü
                if 'daily_change_cents' in data and data['last'] is not None and not math.isnan(safe_float(data['daily_change_cents'])):
                    data_copy = data.copy()  # Orijinal veriyi değiştirmemek için kopya oluştur
                    # NaN ve None değerleri güvenli varsayılan değerlerle değiştir
                    for key in data_copy:
                        if isinstance(data_copy[key], (int, float)) and (data_copy[key] is None or math.isnan(data_copy[key])):
                            data_copy[key] = 0.0
                    extlt_movers.append(data_copy)
            
            # Daily change'e göre sırala
            if show_gainers:
                # En çok yükselenler (büyükten küçüğe)
                tltr_movers.sort(key=lambda x: safe_float(x['daily_change_cents'], 0.0), reverse=True)
                extlt_movers.sort(key=lambda x: safe_float(x['daily_change_cents'], 0.0), reverse=True)
                window_title = "En Çok Yükselen Hisseler"
            else:
                # En çok düşenler (küçükten büyüğe)
                tltr_movers.sort(key=lambda x: safe_float(x['daily_change_cents'], 0.0))
                extlt_movers.sort(key=lambda x: safe_float(x['daily_change_cents'], 0.0))
                window_title = "En Çok Düşen Hisseler"
            
            # En çok düşen/yükselen 15 hisseyi al
            top_tltr_movers = tltr_movers[:15] if len(tltr_movers) >= 15 else tltr_movers
            top_extlt_movers = extlt_movers[:15] if len(extlt_movers) >= 15 else extlt_movers
            
            # Yeni pencere oluştur
            movers_window = tk.Toplevel(self)
            movers_window.title(window_title)
            movers_window.geometry("1100x600")
            movers_window.transient(self)
            
            # Sekme yapısı
            notebook = ttk.Notebook(movers_window)
            notebook.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)
            
            # TLTR sekmesi
            tltr_frame = ttk.Frame(notebook)
            notebook.add(tltr_frame, text="TLTR Hisseleri")
            
            # EXTLT sekmesi
            extlt_frame = ttk.Frame(notebook)
            notebook.add(extlt_frame, text="EXTLT Hisseleri")
            
            # Treeview kolonları
            columns = ("Ticker", "Last", "Daily_Change", "Bid", "Ask", "Spread", "Volume")
            
            # TLTR Treeview
            tltr_tree = ttk.Treeview(tltr_frame, columns=columns, show="headings", height=20)
            
            # EXTLT Treeview
            extlt_tree = ttk.Treeview(extlt_frame, columns=columns, show="headings", height=20)
            
            # Kolon ayarları (her iki treeview için)
            for tree in [tltr_tree, extlt_tree]:
                tree.heading("Ticker", text="Ticker")
                tree.heading("Last", text="Son")
                tree.heading("Daily_Change", text="Daily Chg (¢)")
                tree.heading("Bid", text="Alış")
                tree.heading("Ask", text="Satış")
                tree.heading("Spread", text="Spread")
                tree.heading("Volume", text="Hacim")
                
                tree.column("Ticker", width=100, anchor="center")
                tree.column("Last", width=80, anchor="center")
                tree.column("Daily_Change", width=100, anchor="center")
                tree.column("Bid", width=80, anchor="center")
                tree.column("Ask", width=80, anchor="center")
                tree.column("Spread", width=80, anchor="center")
                tree.column("Volume", width=100, anchor="center")
                
                # Scrollbar ekle
                scrollbar = ttk.Scrollbar(tree.master, orient="vertical", command=tree.yview)
                tree.configure(yscrollcommand=scrollbar.set)
                scrollbar.pack(side=tk.RIGHT, fill="y")
                tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
            
                        # TLTR verilerini doldur
            for data in top_tltr_movers:
                tltr_tree.insert("", "end", values=(
                    data['symbol'],
                    f"{safe_float(data['last'], 0.0):.2f}",
                    f"{safe_float(data['daily_change_cents'], 0.0):.2f}",
                    f"{safe_float(data['bid'], 0.0):.2f}" if data.get('bid') else "-",
                    f"{safe_float(data['ask'], 0.0):.2f}" if data.get('ask') else "-",
                    f"{safe_float(data['spread'], 0.0):.2f}" if data.get('spread') else "-",
                    f"{data['volume']}" if data.get('volume') else "-"
                ))
            
            # EXTLT verilerini doldur
            for data in top_extlt_movers:
                extlt_tree.insert("", "end", values=(
                    data['symbol'],
                    f"{safe_float(data['last'], 0.0):.2f}",
                    f"{safe_float(data['daily_change_cents'], 0.0):.2f}",
                    f"{safe_float(data['bid'], 0.0):.2f}" if data.get('bid') else "-",
                    f"{safe_float(data['ask'], 0.0):.2f}" if data.get('ask') else "-",
                    f"{safe_float(data['spread'], 0.0):.2f}" if data.get('spread') else "-",
                    f"{data['volume']}" if data.get('volume') else "-"
                ))
            
            # Alt panel - bilgi ve yenileme
            info_frame = ttk.Frame(movers_window)
            info_frame.pack(fill=tk.X, pady=10, padx=10)
            
            # Son güncelleme zamanı
            last_update = max([data.get('last_update', datetime.now()) for category in self.global_ticker_cache.values() for data in category.values()], default=datetime.now())
            update_label = ttk.Label(info_frame, text=f"Son Güncelleme: {last_update.strftime('%H:%M:%S')}")
            update_label.pack(side=tk.LEFT)
            
            # Yenile butonu
            def refresh_data():
                self.rotate_ticker_data()
                messagebox.showinfo("Bilgi", "Veriler yenileniyor. Lütfen birkaç saniye içinde tekrar kontrol edin.")
                movers_window.destroy()
                self.after(10000, lambda: self.show_top_movers(show_gainers))
                
            refresh_button = ttk.Button(info_frame, text="Verileri Yenile", command=refresh_data)
            refresh_button.pack(side=tk.RIGHT)
            
            # Basıldığında hisseyi ana ekranda gösterme fonksiyonu
            def show_ticker_in_main(event):
                tree = event.widget
                selection = tree.selection()
                if selection:
                    item = tree.item(selection[0])
                    symbol = item['values'][0]  # İlk kolon ticker sembolü
                    
                    # Ana pencerede bu hisseyi bul ve göster
                    if symbol in self.tltr_tickers:
                        self.notebook.select(0)  # TLTR sekmesine geç
                        page = (self.tltr_tickers.index(symbol) // self.items_per_page) + 1
                        self.tltr_current_page = page
                    elif symbol in self.divspread_tickers:
                        self.notebook.select(1)  # DIV Spread sekmesine geç
                        page = (self.divspread_tickers.index(symbol) // self.items_per_page) + 1
                        self.divspread_current_page = page
                        
                    self.populate_treeview()
                    messagebox.showinfo("Bilgi", f"{symbol} hissesi ana pencerede görüntüleniyor.")
                    
            # Çift tıklama olaylarını bağla
            tltr_tree.bind("<Double-1>", show_ticker_in_main)
            extlt_tree.bind("<Double-1>", show_ticker_in_main)
            
            # Kapatılırken işlem
            def on_closing():
                movers_window.destroy()
                
            movers_window.protocol("WM_DELETE_WINDOW", on_closing)
            
            # Movers penceresi ilk kez gösterildiğinde movers_loading_shown bayrağını temizle
            self.movers_loading_shown = False
            
        except Exception as e:
            messagebox.showerror("Hata", f"En çok değişen hisseleri gösterirken hata oluştu: {str(e)}")
            
    def process_api_calls(self):
        """Kuyruktaki API çağrılarını işler"""
        try:
            self.api_call_processing = True
            while not self.api_call_queue.empty():
                # En fazla 10 çağrı işle ve UI'ın yanıt vermesine izin ver
                for _ in range(10):
                    if self.api_call_queue.empty():
                        break
                    
                    func, args, kwargs = self.api_call_queue.get()
                    try:
                        func(*args, **kwargs)
                    except Exception as e:
                        print(f"API çağrı hatası: {e}")
                    finally:
                        self.api_call_queue.task_done()
                        
                    # Çağrılar arasında kısa bekle
                    time.sleep(0.1)
                    
                # UI'ı güncellemek için kontrol çevrimine izin ver
                break
        except Exception as e:
            print(f"API çağrı işleme hatası: {e}")
        finally:
            self.api_call_processing = False
            # Her 100 ms'de bir yeniden çağır
            self.after(100, self.process_api_calls)

    def queue_api_call(self, func, *args, **kwargs):
        """API çağrısını kuyruğa ekler"""
        self.api_call_queue.put((func, args, kwargs))

    def show_positions(self):
        """
        Mevcut pozisyonları ve PnL bilgilerini gösteren yeni bir pencere açar
        """
        if not self.connected or not self.ib.isConnected():
            print("IBKR bağlantısı yok, pozisyon bilgileri alınamıyor")
            return
        
        # Yeni bir pencere oluştur
        position_window = tk.Toplevel(self)
        position_window.title("Mevcut Pozisyonlar")
        position_window.geometry("800x500")
        position_window.grab_set()  # Pencereyi modal yap
        
        # Sıralama değişkenleri
        sort_column = None
        sort_reverse = False
        positions_data = []  # Pozisyon verilerini saklayacak liste
        
        # Yükleniyor etiketi
        loading_label = ttk.Label(position_window, text="Pozisyonlar getiriliyor...")
        loading_label.pack(pady=20)
        
        # Sıralama fonksiyonu
        def sort_positions(column):
            nonlocal sort_column, sort_reverse
            
            # Mevcut sıralama durumunu kontrol et
            if sort_column == column:
                sort_reverse = not sort_reverse
            else:
                sort_column = column
                sort_reverse = False
            
            # Sütun başlıklarını güncelle (sıralama okunun gösterimi için)
            for col in pos_tree["columns"]:
                if col == column:
                    direction = " ▼" if sort_reverse else " ▲"
                    pos_tree.heading(col, text=get_column_title(col) + direction)
                else:
                    pos_tree.heading(col, text=get_column_title(col))
            
            # Verileri sırala ve yeniden göster
            display_sorted_positions()
        
        # Sütun başlık metinlerini döndür
        def get_column_title(column):
            titles = {
                "symbol": "Sembol",
                "position": "Pozisyon",
                "avg_cost": "Ortalama Maliyet",
                "last_price": "Son Fiyat",
                "market_value": "Piyasa Değeri",
                "pnl": "P&L",
                "pnl_percent": "P&L %"
            }
            return titles.get(column, column)
        
        # Sıralanmış pozisyonları göster
        def display_sorted_positions():
            # Treeview temizle
            for item in pos_tree.get_children():
                pos_tree.delete(item)
                
            # Pozisyon verilerini sırala
            if sort_column:
                def extract_sort_key(item, column):
                    if column == "symbol":
                        return item["symbol"]
                    elif column == "position":
                        return float(item["position"].replace(",", ""))
                    elif column == "avg_cost":
                        return float(item["avg_cost"].replace("$", ""))
                    elif column == "last_price":
                        return float(item["last_price"].replace("$", ""))
                    elif column == "market_value":
                        return float(item["market_value"].replace("$", "").replace(",", ""))
                    elif column == "pnl":
                        return float(item["pnl"].replace("$", "").replace(",", ""))
                    elif column == "pnl_percent":
                        return float(item["pnl_percent"].replace("%", ""))
                    return 0
                    
                positions_data.sort(
                    key=lambda x: extract_sort_key(x, sort_column),
                    reverse=sort_reverse
                )
            
            # Sıralanmış verileri ekle
            for pos_data in positions_data:
                tag = 'profit' if float(pos_data["pnl"].replace("$", "").replace(",", "")) > 0 else ('loss' if float(pos_data["pnl"].replace("$", "").replace(",", "")) < 0 else '')
                pos_tree.insert(
                    "", "end",
                    values=(
                        pos_data["symbol"],
                        pos_data["position"],
                        pos_data["avg_cost"],
                        pos_data["last_price"],
                        pos_data["market_value"],
                        pos_data["pnl"],
                        pos_data["pnl_percent"]
                    ),
                    tags=(tag,)
                )
        
        # UI güncellemelerini ana thread'de yapan fonksiyon
        def update_ui_with_positions(positions):
            try:
                nonlocal positions_data
                
                # Yükleniyor etiketini kaldır
                loading_label.destroy()
                
                if not positions:
                    ttk.Label(position_window, text="Pozisyon bulunamadı").pack(pady=20)
                    return
                
                # Treeview için frame
                tree_frame = ttk.Frame(position_window)
                tree_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)
                
                # Treeview (pozisyon tablosu)
                columns = ("symbol", "position", "avg_cost", "last_price", "market_value", "pnl", "pnl_percent")
                global pos_tree
                pos_tree = ttk.Treeview(
                    tree_frame,
                    columns=columns,
                    show="headings",
                    selectmode="browse"
                )
                
                # Sütun başlıkları - sıralama komutlarıyla
                for col in columns:
                    pos_tree.heading(col, text=get_column_title(col), command=lambda c=col: sort_positions(c))
                
                # Sütun genişlikleri
                pos_tree.column("symbol", width=100, anchor=tk.W)
                pos_tree.column("position", width=80, anchor=tk.E)
                pos_tree.column("avg_cost", width=120, anchor=tk.E)
                pos_tree.column("last_price", width=120, anchor=tk.E)
                pos_tree.column("market_value", width=120, anchor=tk.E)
                pos_tree.column("pnl", width=120, anchor=tk.E)
                pos_tree.column("pnl_percent", width=120, anchor=tk.E)
                
                # Scrollbar
                scroll = ttk.Scrollbar(tree_frame, orient="vertical", command=pos_tree.yview)
                pos_tree.configure(yscrollcommand=scroll.set)
                
                # Yerleştirme
                scroll.pack(side=tk.RIGHT, fill=tk.Y)
                pos_tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
                
                # P&L için renkli etiketleme
                pos_tree.tag_configure('profit', background='#e6ffe6')  # Yeşil (kâr)
                pos_tree.tag_configure('loss', background='#ffe6e6')    # Kırmızı (zarar)
                
                # Toplam değerleri tutacak değişkenler
                total_market_value = 0
                total_pnl = 0
                
                # Pozisyonları işle
                for pos in positions:
                    try:
                        contract = pos.contract
                        symbol = contract.symbol
                        position_size = pos.position
                        avg_cost = pos.avgCost
                        
                        # Sembolün son fiyatını al
                        if symbol in self.latest_data and 'last' in self.latest_data[symbol]:
                            last_price = self.latest_data[symbol]['last']
                        elif symbol in self.latest_data and 'bid' in self.latest_data[symbol]:
                            last_price = self.latest_data[symbol]['bid']
                        else:
                            last_price = avg_cost  # Veri yoksa ortalama maliyeti kullan
                        
                        # Değerleri hesapla
                        market_value = position_size * last_price
                        pnl = market_value - (position_size * avg_cost)
                        pnl_percent = (pnl / (position_size * avg_cost)) * 100 if avg_cost > 0 and position_size != 0 else 0
                        
                        # Toplamları güncelle
                        total_market_value += market_value
                        total_pnl += pnl
                        
                        # Veriyi positions_data listesine ekle
                        pos_data = {
                            "symbol": symbol,
                            "position": f"{position_size:,.0f}",
                            "avg_cost": f"${avg_cost:.2f}",
                            "last_price": f"${last_price:.2f}",
                            "market_value": f"${market_value:,.2f}",
                            "pnl": f"${pnl:,.2f}",
                            "pnl_percent": f"{pnl_percent:.2f}%"
                        }
                        positions_data.append(pos_data)
                    
                    except Exception as e:
                        print(f"Pozisyon işleme hatası ({symbol}): {e}")
                
                # Pozisyonları göster
                display_sorted_positions()
                
                # Özet bilgileri göster
                summary_frame = ttk.Frame(position_window)
                summary_frame.pack(fill=tk.X, padx=10, pady=10)
                
                ttk.Label(summary_frame, text=f"Toplam Piyasa Değeri: ${total_market_value:,.2f}").pack(side=tk.LEFT, padx=10)
                
                # Toplam P&L'i renklendirerek göster
                pnl_label = ttk.Label(
                    summary_frame, 
                    text=f"Toplam P&L: ${total_pnl:,.2f}", 
                    foreground='green' if total_pnl > 0 else ('red' if total_pnl < 0 else 'black')
                )
                pnl_label.pack(side=tk.LEFT, padx=10)
                
                # Güncelleme zamanı
                update_time = ttk.Label(summary_frame, text=f"Son güncelleme: {time.strftime('%H:%M:%S')}")
                update_time.pack(side=tk.RIGHT, padx=10)
                
                # Yenile butonu
                refresh_btn = ttk.Button(
                    position_window, 
                    text="Yenile", 
                    command=lambda: (position_window.destroy(), self.show_positions())
                )
                refresh_btn.pack(pady=10)
                    
            except Exception as e:
                show_error(f"Pozisyon gösterimi sırasında hata: {e}")
        
        # Hata mesajı gösterme
        def show_error(message):
            loading_label.destroy()
            error_frame = ttk.Frame(position_window)
            error_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)
            
            ttk.Label(error_frame, text=message, foreground="red").pack(pady=20)
            
            # Yeniden deneme butonu
            retry_button = ttk.Button(
                error_frame,
                text="Yeniden Dene",
                command=lambda: (position_window.destroy(), self.show_positions())
            )
            retry_button.pack(pady=10)
        
        # Pozisyonları getirme işlemini ana thread'de çalıştırma
        def fetch_positions_safe():
            try:
                # Event loop yoksa oluştur
                try:
                    if threading.current_thread() != threading.main_thread():
                        loop = asyncio.new_event_loop()
                        asyncio.set_event_loop(loop)
                except Exception as e:
                    print(f"Event loop ayarlama hatası: {e}")
                
                # Mevcut pozisyonları al
                positions = self.ib.positions()
                
                # UI güncellemelerini ana thread'de yap
                self.after(0, lambda: update_ui_with_positions(positions))
                
            except Exception as e:
                error_msg = f"Pozisyon bilgileri alınırken hata: {e}"
                print(error_msg)
                self.after(0, lambda: show_error(error_msg))
        
        # Pozisyonları ana thread'de kuyruk üzerinden getir
        self.queue_api_call(fetch_positions_safe)

    def show_opt50_portfolio(self):
        """
        optimized_50_stocks_portfolio.csv dosyasından portföy verilerini görüntüler
        ve canlı fiyat verilerini gösterir
        """
        # Import gerekli modüller
        import os
        from tkinter import messagebox
        
        # CSV dosyasının yolunu belirle
        portfolio_file = "optimized_50_stocks_portfolio.csv"
        
        # Dosya var mı kontrol et
        if not os.path.exists(portfolio_file):
            messagebox.showerror("Dosya Bulunamadı", f"{portfolio_file} dosyası bulunamadı.")
            return
          # Yeni bir pencere oluştur
        portfolio_window = tk.Toplevel(self)
        portfolio_window.title("Opt50 Portföy")
        portfolio_window.geometry("1400x700")  # Pencere boyutunu artırdım (1200 -> 1400)
        
        # Yükleniyor etiketi
        loading_label = ttk.Label(portfolio_window, text="Portföy verileri yükleniyor...")
        loading_label.pack(pady=20)
        
        # Sayfalama ve sıralama değişkenleri
        sort_column = None
        sort_reverse = False
        
        # Sayfalama değişkenleri
        port_items_per_page = 10  # Sayfa başına gösterilecek hisse sayısı
        port_current_page = 1     # Mevcut sayfa numarası
        port_total_pages = 1      # Toplam sayfa sayısı
        
        try:
            # CSV dosyasını oku
            df = pd.read_csv(portfolio_file)
            
            # Gerekli sütunları kontrol et
            required_columns = ["PREF IBKR", "CMON", "FINAL_THG", "AVG_ADV", "Normalized_THG", "Final_Shares"]
            missing_columns = [col for col in required_columns if col not in df.columns]
            if missing_columns:
                error_msg = f"CSV dosyasında aşağıdaki sütunlar eksik: {', '.join(missing_columns)}"
                loading_label.destroy()
                messagebox.showerror("Eksik Sütunlar", error_msg)
                return
            
            # Treeview oluştur
            def setup_treeview():
                # Yükleniyor etiketini kaldır
                loading_label.destroy()
                
                # Treeview için frame
                tree_frame = ttk.Frame(portfolio_window)
                tree_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)
                
                # Sütunlar - Final_shares eklendi
                columns = (
                    "ticker", "common", "thg", "avg_adv", "norm_thg", "final_shares",
                    "last", "bid", "ask", "spread", "volume"
                )
                
                # Treeview
                port_tree = ttk.Treeview(
                    tree_frame,
                    columns=columns,
                    show="headings",
                    selectmode="browse"
                )
                
                # Sütun başlıkları
                column_titles = {
                    "ticker": "PREF IBKR",
                    "common": "CMON",
                    "thg": "FINAL_THG",
                    "avg_adv": "AVG_ADV",
                    "norm_thg": "Normalized_THG",
                    "final_shares": "Final_shares",  # Yeni kolon
                    "last": "Last Price",
                    "bid": "Bid",
                    "ask": "Ask",
                    "spread": "Spread %",
                    "volume": "Volume"
                }
                
                # Sıralama fonksiyonu
                def sort_portfolio(column):
                    nonlocal sort_column, sort_reverse
                    
                    # Mevcut sıralama durumunu kontrol et
                    if sort_column == column:
                        sort_reverse = not sort_reverse
                    else:
                        sort_column = column
                        sort_reverse = False
                    
                    # Sütun başlıklarını güncelle
                    for col in port_tree["columns"]:
                        if col == column:
                            direction = " ▼" if sort_reverse else " ▲"
                            port_tree.heading(col, text=column_titles[col] + direction)
                        else:
                            port_tree.heading(col, text=column_titles[col])
                    
                    # Treeview'i güncelle
                    update_treeview(df, port_tree)
                    
                # Sütun başlıklarını ayarla
                for col in columns:
                    port_tree.heading(col, text=column_titles[col], command=lambda c=col: sort_portfolio(c))
                
                # Sütun genişlikleri
                port_tree.column("ticker", width=110, anchor=tk.W)
                port_tree.column("common", width=110, anchor=tk.W)
                port_tree.column("thg", width=90, anchor=tk.E)
                port_tree.column("avg_adv", width=100, anchor=tk.E)
                port_tree.column("norm_thg", width=110, anchor=tk.E)
                port_tree.column("final_shares", width=100, anchor=tk.E)  # Yeni kolon genişliği
                port_tree.column("last", width=90, anchor=tk.E)
                port_tree.column("bid", width=90, anchor=tk.E)
                port_tree.column("ask", width=90, anchor=tk.E)
                port_tree.column("spread", width=90, anchor=tk.E)
                port_tree.column("volume", width=90, anchor=tk.E)
                
                # Scrollbar
                tree_scroll = ttk.Scrollbar(tree_frame, orient="vertical", command=port_tree.yview)
                port_tree.configure(yscrollcommand=tree_scroll.set)
                
                # Yerleştirme
                tree_scroll.pack(side=tk.RIGHT, fill=tk.Y)
                port_tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
                
                # Tag'ler
                port_tree.tag_configure('updated', background='#e6ffe6')  # Yeşil
                port_tree.tag_configure('high_value', background='#e6ffe6')  # Yeşil arkaplan (yüksek normalized_thg)
                port_tree.tag_configure('low_value', background='#ffe6e6')    # Kırmızı arkaplan (düşük normalized_thg)
                
                # Treeview'i doldur
                update_treeview(df, port_tree)
                  # Alt panel - kontrol ve bilgi
                bottom_frame = ttk.Frame(portfolio_window)
                bottom_frame.pack(fill=tk.X, pady=10, padx=10)
                
                # Toplam portföy büyüklüğü
                ttk.Label(bottom_frame, text=f"Toplam Sembol Sayısı: {len(df)}").pack(side=tk.LEFT, padx=10)
                
                # Ortalama Normalized_THG
                avg_norm_thg = df["Normalized_THG"].mean()
                ttk.Label(bottom_frame, text=f"Ort. Normalized_THG: {avg_norm_thg:.4f}").pack(side=tk.LEFT, padx=10)
                
                # Toplam Final_Shares
                total_shares = df["Final_Shares"].sum()
                ttk.Label(bottom_frame, text=f"Toplam Hisse: {total_shares:,.0f}").pack(side=tk.LEFT, padx=10)
                
                # Sayfalama kontrolleri
                page_nav_frame = ttk.Frame(bottom_frame)
                page_nav_frame.pack(side=tk.LEFT, padx=20)
                
                # Önceki sayfa butonu
                prev_page_btn = ttk.Button(
                    page_nav_frame, 
                    text="< Önceki Sayfa", 
                    command=lambda: navigate_page(-1)
                )
                prev_page_btn.pack(side=tk.LEFT)
                
                # Sayfa bilgisi
                port_page_info = ttk.Label(
                    page_nav_frame, 
                    text=f"Sayfa {port_current_page}/{port_total_pages} (Toplam: {len(df)})"
                )
                port_page_info.pack(side=tk.LEFT, padx=20)
                
                # Sonraki sayfa butonu
                next_page_btn = ttk.Button(
                    page_nav_frame, 
                    text="Sonraki Sayfa >", 
                    command=lambda: navigate_page(1)
                )
                next_page_btn.pack(side=tk.LEFT)
                
                # Sayfa navigasyon fonksiyonu
                def navigate_page(direction):
                    nonlocal port_current_page, port_total_pages
                    
                    # Yeni sayfa hesapla
                    new_page = port_current_page + direction
                    
                    # Sayfa sınırlarını kontrol et
                    if 1 <= new_page <= port_total_pages:
                        port_current_page = new_page
                        
                        # Sayfa bilgisini güncelle
                        port_page_info.config(text=f"Sayfa {port_current_page}/{port_total_pages} (Toplam: {len(df)})")
                        
                        # TreeView'i güncelle
                        update_treeview(df, port_tree)
                        
                        # Yeni sayfadaki hisseler için veri al
                        if self.connected and self.ib.isConnected():
                            subscribe_to_portfolio_tickers(df, port_tree, update_time_label)
                
                # Güncelleme zamanı
                update_time_label = ttk.Label(bottom_frame, text=f"Son güncelleme: {time.strftime('%H:%M:%S')}")
                update_time_label.pack(side=tk.RIGHT, padx=10)
                
                # Yenile butonu
                refresh_button = ttk.Button(
                    bottom_frame, 
                    text="Verileri Yenile", 
                    command=lambda: refresh_data(df, port_tree, update_time_label)
                )
                refresh_button.pack(side=tk.RIGHT, padx=10)
                
                # Aktif hisseler için otomatik veri aboneliği
                if self.connected and self.ib.isConnected():
                    subscribe_to_portfolio_tickers(df, port_tree, update_time_label)
                
                return port_tree
              # Treeview'i güncelleme fonksiyonu
            def update_treeview(data_df, tree):
                nonlocal port_items_per_page, port_current_page, port_total_pages
                
                # Mevcut verileri temizle
                for i in tree.get_children():
                    tree.delete(i)
                
                # Sıralama varsa uygula
                if sort_column:
                    ascending = not sort_reverse
                    
                    # CSV verileri için sıralama
                    if sort_column in ["ticker", "common"]:
                        # Metin sütunları
                        data_df = data_df.sort_values(
                            by={"ticker": "PREF IBKR", "common": "CMON"}[sort_column], 
                            ascending=ascending
                        )
                    elif sort_column in ["thg", "avg_adv", "norm_thg", "final_shares"]:
                        # Sayısal sütunlar
                        data_df = data_df.sort_values(
                            by={"thg": "FINAL_THG", "avg_adv": "AVG_ADV", 
                                "norm_thg": "Normalized_THG", "final_shares": "Final_Shares"}[sort_column],
                            ascending=ascending
                        )
                    else:
                        # Canlı veri sütunları (last, bid, ask, spread, volume)
                        # Bu durumda özel bir sıralama işlevi kullanacağız
                        sorted_rows = []
                        
                        for _, row in data_df.iterrows():
                            ticker = row["PREF IBKR"]
                            
                            # Varsayılan değerler
                            val = float('-inf') if ascending else float('inf')
                            
                            # Canlı veri varsa kullan
                            if ticker in self.latest_data:
                                data = self.latest_data[ticker]
                                if sort_column == "last" and "last" in data:
                                    val = data["last"] or 0
                                elif sort_column == "bid" and "bid" in data:
                                    val = data["bid"] or 0
                                elif sort_column == "ask" and "ask" in data:
                                    val = data["ask"] or 0
                                elif sort_column == "volume" and "volume" in data:
                                    val = data["volume"] or 0
                                elif sort_column == "spread":
                                    if "bid" in data and "ask" in data and data["ask"] > 0:
                                        val = ((data["ask"] - data["bid"]) / data["ask"]) * 100
                            
                            sorted_rows.append((val, row))
                        
                        # Sırala ve DataFrame'i yeniden oluştur
                        sorted_rows.sort(reverse=sort_reverse)
                        data_df = pd.DataFrame([row for _, row in sorted_rows])
                
                # Sayfalama için toplam sayfa sayısını hesapla
                total_stocks = len(data_df)
                port_total_pages = max(1, math.ceil(total_stocks / port_items_per_page))
                
                # Geçerli sayfa numarasını kontrol et
                if port_current_page > port_total_pages:
                    port_current_page = port_total_pages
                
                # Görünür hisseleri belirle (sayfalama)
                start_idx = (port_current_page - 1) * port_items_per_page
                end_idx = min(start_idx + port_items_per_page, total_stocks)
                
                # Sadece geçerli sayfadaki hisseleri göster
                page_df = data_df.iloc[start_idx:end_idx]
                
                # Sıralanmış verileri TreeView'e ekle (sadece geçerli sayfa)
                for _, row in page_df.iterrows():
                    ticker = row["PREF IBKR"]
                    
                    # Sayısal değerleri formatla
                    thg = f"{row['FINAL_THG']:.4f}" if pd.notna(row["FINAL_THG"]) else ""
                    avg_adv = f"{row['AVG_ADV']:,.0f}" if pd.notna(row["AVG_ADV"]) else ""
                    norm_thg = f"{row['Normalized_THG']:.4f}" if pd.notna(row["Normalized_THG"]) else ""
                    final_shares = f"{row['Final_Shares']:,.0f}" if pd.notna(row["Final_Shares"]) else ""
                    
                    # Canlı veri alanları için varsayılan değerler
                    last = bid = ask = spread = volume = ""
                    
                    # Canlı veriler varsa ekle
                    if ticker in self.latest_data:
                        data = self.latest_data[ticker]
                        
                        if "last" in data and data["last"] is not None and not math.isnan(data["last"]):
                            last = f"{data['last']:.2f}"
                            
                        if "bid" in data and data["bid"] is not None and not math.isnan(data["bid"]):
                            bid = f"{data['bid']:.2f}"
                            
                        if "ask" in data and data["ask"] is not None and not math.isnan(data["ask"]):
                            ask = f"{data['ask']:.2f}"
                            
                        # Spread hesapla
                        if ("bid" in data and data["bid"] is not None and not math.isnan(data["bid"]) and 
                            "ask" in data and data["ask"] is not None and not math.isnan(data["ask"]) and 
                            data["ask"] > 0):
                            spread_val = ((data["ask"] - data["bid"]) / data["ask"]) * 100
                            spread = f"{spread_val:.2f}%"
                            
                        if "volume" in data and data["volume"] is not None and not math.isnan(data["volume"]):
                            volume = f"{int(data['volume']):,}"
                    
                    # Tag belirle
                    tag = None
                    if pd.notna(row["Normalized_THG"]):
                        norm_thg_val = float(row["Normalized_THG"])
                        if norm_thg_val > 0.8:  # Yüksek değer
                            tag = "high_value"
                        elif norm_thg_val < 0.2:  # Düşük değer
                            tag = "low_value"
                    
                    # Satırı ekle
                    tree.insert(
                        "", "end",
                        values=(
                            ticker,
                            row["CMON"] if pd.notna(row["CMON"]) else "",
                            thg,
                            avg_adv,
                            norm_thg,
                            final_shares,  # Yeni kolon değeri
                            last,
                            bid,
                            ask,
                            spread,
                            volume
                        ),
                        tags=(tag,) if tag else ()
                    )
                
                # Diğer kodlar...
            
            # Verileri yenileme fonksiyonu
            def refresh_data(data_df, tree, time_label):
                # Tüm hisseler için güncelleme iste
                if self.connected and self.ib.isConnected():
                    subscribe_to_portfolio_tickers(data_df, tree, time_label)
                else:
                    messagebox.showinfo("Bağlantı Yok", "Canlı veri için IBKR bağlantısı gereklidir.")
              # Portföydeki hisselere abone ol
            def subscribe_to_portfolio_tickers(data_df, tree, time_label):
                nonlocal port_items_per_page, port_current_page, port_total_pages
                
                # Sayfalama için indeksleri hesapla
                total_stocks = len(data_df)
                start_idx = (port_current_page - 1) * port_items_per_page
                end_idx = min(start_idx + port_items_per_page, total_stocks)
                
                # Sadece geçerli sayfadaki hisselerin listesini al
                page_df = data_df.iloc[start_idx:end_idx]
                portfolio_tickers = page_df["PREF IBKR"].tolist()
                
                # Mevcut abonelikleri kaydet
                current_subscriptions = set(self.tickers.keys())
                
                # Aboneliği olmayan hisselere abone ol
                new_subscriptions = []
                for ticker in portfolio_tickers:
                    if not pd.isna(ticker) and ticker and ticker not in current_subscriptions:
                        new_subscriptions.append(ticker)
                
                # Maksimum yeni abonelik sayısı (API limitini aşmamak için)
                max_new = min(10, 50 - len(current_subscriptions))
                if len(new_subscriptions) > max_new:
                    new_subscriptions = new_subscriptions[:max_new]
                    messagebox.showinfo(
                        "Abonelik Sınırı",
                        f"API limitleri nedeniyle sadece {max_new} yeni hisse için veri alınabilir."
                    )
                
                # Yeni abonelikleri oluştur
                subscription_count = 0
                for ticker in new_subscriptions:
                    try:
                        # Kontrat oluştur
                        contract = Stock(symbol=ticker, exchange='SMART', currency='USD')
                        
                        # Market verisi iste
                        self.ib.reqMktData(
                            contract, 
                            genericTickList="233,165,221",  # BidAsk + ek veriler
                            snapshot=False,
                            regulatorySnapshot=False
                        )
                          # Tickers sözlüğüne ekle
                        self.tickers[ticker] = {
                            'contract': contract,
                            'row_id': ticker,
                            'subscription_time': time.time()
                        }
                        
                        subscription_count += 1
                        print(f"✓ Portföy için {ticker} aboneliği başlatıldı (Sayfa {port_current_page})")
                        
                        # Her 5 abonelikte bir bekle
                        if subscription_count % 5 == 0:
                            time.sleep(0.5)
                            
                    except Exception as e:
                        print(f"! Portföy abonelik hatası ({ticker}): {str(e)}")
                
                # Aktif abonelik sayısını güncelle
                total_subscriptions = len(self.tickers) + len(self.common_tickers)
                self.subscription_count_label.config(text=f"Aktif abonelikler: {total_subscriptions}/100")
                
                # Veri güncellemeleri için callback fonksiyonu
                def update_portfolio_data():
                    # Tüm satırları güncelle
                    for item_id in tree.get_children():
                        values = tree.item(item_id, "values")
                        ticker = values[0]
                        
                        if ticker in self.latest_data:
                            data = self.latest_data[ticker]
                            values_list = list(values)
                            
                            # Son fiyat
                            if "last" in data and data["last"] is not None and not math.isnan(data["last"]):
                                values_list[5] = f"{data['last']:.2f}"
                                
                            # Bid
                            if "bid" in data and data["bid"] is not None and not math.isnan(data["bid"]):
                                values_list[6] = f"{data['bid']:.2f}"
                                
                            # Ask
                            if "ask" in data and data["ask"] is not None and not math.isnan(data["ask"]):
                                values_list[7] = f"{data['ask']:.2f}"
                                
                            # Spread
                            if ("bid" in data and data["bid"] is not None and not math.isnan(data["bid"]) and 
                                "ask" in data and data["ask"] is not None and not math.isnan(data["ask"]) and 
                                data["ask"] > 0):
                                spread = ((data["ask"] - data["bid"]) / data["ask"]) * 100
                                values_list[8] = f"{spread:.2f}%"
                                
                            # Volume
                            if "volume" in data and data["volume"] is not None and not math.isnan(data["volume"]):
                                values_list[9] = f"{int(data['volume']):,}"
                            
                            # Satırı güncelle
                            tree.item(item_id, values=values_list)
                    
                    # Son güncelleme zamanını güncelle
                    time_label.config(text=f"Son güncelleme: {time.strftime('%H:%M:%S')}")
                    
                    # Her 5 saniyede bir güncelle
                    if not hasattr(portfolio_window, 'closed') or not portfolio_window.closed:
                        portfolio_window.after(5000, update_portfolio_data)
                
                # İlk güncellemeyi başlat
                portfolio_window.after(2000, update_portfolio_data)
                
                # Pencere kapandığında temizlik yapılması için method
                def on_window_close():
                    portfolio_window.closed = True
                    portfolio_window.destroy()
                
                portfolio_window.protocol("WM_DELETE_WINDOW", on_window_close)
            
            # TreeView'i oluştur
            port_tree = setup_treeview()
            
        except Exception as e:
            loading_label.destroy()
            error_frame = ttk.Frame(portfolio_window)
            error_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)
            
            ttk.Label(
                error_frame, 
                text=f"Portföy verileri yüklenirken hata oluştu:\n\n{str(e)}", 
                foreground="red"
            ).pack(pady=20)
            
            print(f"Portföy görüntüleme hatası: {str(e)}")

    def show_etf_list(self):
        """
        TLT, SPY, IWM, HYG, PFF, PGX ETF'lerinin fiyat ve değişim bilgilerini göster
        """
        # ETF sembolleri
        etf_symbols = ["TLT", "SPY", "IWM", "HYG", "PFF", "PGX"]
        
        # Yeni bir pencere oluştur
        etf_window = tk.Toplevel(self)
        etf_window.title("ETF İzleme")
        etf_window.geometry("600x400")
        
        # Yükleniyor etiketi
        loading_label = ttk.Label(etf_window, text="ETF verileri yükleniyor...")
        loading_label.pack(pady=20)
        
        # ETF verilerini getir ve göster
        def fetch_etf_data():
            try:
                # Abonelik ve veri takibi için liste
                etf_subscriptions = []
                etf_data = {}
                
                # TreeView için frame
                tree_frame = ttk.Frame(etf_window)
                tree_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)
                
                # TreeView
                columns = ("symbol", "last_price", "daily_change_percent", "daily_change_cents")
                etf_tree = ttk.Treeview(
                    tree_frame,
                    columns=columns,
                    show="headings",
                    selectmode="browse"
                )
                
                # Sütun başlıkları
                etf_tree.heading("symbol", text="Symbol")
                etf_tree.heading("last_price", text="Last Price")
                etf_tree.heading("daily_change_percent", text="Daily Change %")
                etf_tree.heading("daily_change_cents", text="Daily Change ¢")
                
                # Sütun genişlikleri
                etf_tree.column("symbol", width=100, anchor=tk.CENTER)
                etf_tree.column("last_price", width=150, anchor=tk.E)
                etf_tree.column("daily_change_percent", width=150, anchor=tk.E)
                etf_tree.column("daily_change_cents", width=150, anchor=tk.E)
                
                # Scrollbar
                scroll = ttk.Scrollbar(tree_frame, orient="vertical", command=etf_tree.yview)
                etf_tree.configure(yscrollcommand=scroll.set)
                
                # Yerleştirme
                scroll.pack(side=tk.RIGHT, fill=tk.Y)
                etf_tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
                
                # Tag'ler
                etf_tree.tag_configure('up', background='#e6ffe6')  # Yeşil (artış)
                etf_tree.tag_configure('down', background='#ffe6e6')  # Kırmızı (düşüş)
                
                # ETF'lere abone ol
                def subscribe_etfs():
                    if not self.connected or not self.ib.isConnected():
                        loading_label.destroy()
                        ttk.Label(etf_window, text="IBKR bağlantısı gerekiyor!", foreground="red").pack(pady=20)
                        return
                    
                    # Yükleniyor etiketini kaldır
                    loading_label.destroy()
                    
                    # İlerleme çubuğu
                    progress = ttk.Progressbar(etf_window, orient="horizontal", 
                                             length=300, mode="determinate", maximum=len(etf_symbols))
                    progress.pack(pady=10)
                    progress_label = ttk.Label(etf_window, text="ETF verilerine abone olunuyor...")
                    progress_label.pack(pady=5)
                    
                    for i, symbol in enumerate(etf_symbols):
                        try:
                            # İlerlemeyi güncelle
                            progress["value"] = i + 1
                            progress_label.config(text=f"Abone olunan: {symbol}")
                            etf_window.update()
                            
                            # Kontrat oluştur
                            contract = Stock(symbol=symbol, exchange='SMART', currency='USD')
                            
                            # Market verisi iste
                            self.ib.reqMktData(
                                contract,
                                genericTickList="233,236", # BidAsk + günlük değişim
                                snapshot=False,
                                regulatorySnapshot=False
                            )
                            
                            # ETF verilerini izlemek için sözlük
                            etf_data[symbol] = {}
                            
                            # TreeView'e ekle
                            etf_tree.insert("", "end", iid=symbol, values=(symbol, "...", "...", "..."))
                            
                            # Abonelikleri takip et
                            etf_subscriptions.append(symbol)
                            
                            # Küçük bir bekleme
                            time.sleep(0.5)
                            
                        except Exception as e:
                            print(f"ETF abonelik hatası ({symbol}): {str(e)}")
                    
                    # İlerleme çubuğunu kaldır
                    progress.destroy()
                    progress_label.destroy()
                    
                    # Alt bilgi çerçevesi
                    info_frame = ttk.Frame(etf_window)
                    info_frame.pack(fill=tk.X, padx=10, pady=10)
                    
                    # Son güncelleme zamanı
                    update_time_label = ttk.Label(info_frame, text=f"Son güncelleme: {time.strftime('%H:%M:%S')}")
                    update_time_label.pack(side=tk.RIGHT)
                    
                    # Yenile butonu
                    refresh_btn = ttk.Button(
                        info_frame, 
                        text="Yenile", 
                        command=lambda: refresh_etf_data(etf_tree, update_time_label)
                    )
                    refresh_btn.pack(side=tk.RIGHT, padx=10)
                    
                    # Ticker güncellemesi için callback
                    def on_ticker_update(tickers):
                        updated = False
                        for ticker in tickers:
                            symbol = ticker.contract.symbol
                            if symbol in etf_symbols:
                                # Son fiyat
                                if ticker.last is not None and not math.isnan(ticker.last):
                                    etf_data[symbol]['last'] = ticker.last
                                    updated = True
                                
                                # Günlük değişim
                                if hasattr(ticker, 'close') and ticker.close is not None and not math.isnan(ticker.close):
                                    etf_data[symbol]['prev_close'] = ticker.close
                                    updated = True
                                
                                # Değişim yüzdesi
                                if hasattr(ticker, 'changePercent') and ticker.changePercent is not None and not math.isnan(ticker.changePercent):
                                    etf_data[symbol]['change_percent'] = ticker.changePercent
                                    updated = True
                                
                                # TreeView güncelle
                                if updated and symbol in etf_data:
                                    update_etf_row(symbol, etf_tree)
                    
                    # TreeView satırını güncelle
                    def update_etf_row(symbol, tree):
                        if symbol not in etf_data:
                            return
                            
                        data = etf_data[symbol]
                        
                        # Değerleri hazırla
                        last_price = f"${data.get('last', 0):.2f}"
                        
                        # Değişim yüzdesi
                        change_percent = data.get('change_percent', 0)
                        change_percent_text = f"{change_percent:.2f}%" if change_percent is not None else "-"
                        
                        # Cent bazında değişim
                        change_cents = 0
                        if 'last' in data and 'prev_close' in data:
                            change_cents = (data['last'] - data['prev_close']) * 100  # Cent olarak değişim
                        change_cents_text = f"{change_cents:.2f}¢" if change_cents != 0 else "-"
                        
                        # Tag belirleme (artış/düşüş)
                        tag = 'up' if change_cents > 0 else ('down' if change_cents < 0 else '')
                        
                        # Satırı güncelle
                        tree.item(symbol, values=(symbol, last_price, change_percent_text, change_cents_text), tags=(tag,))
                        
                        # Son güncelleme zamanını güncelle
                        update_time_label.config(text=f"Son güncelleme: {time.strftime('%H:%M:%S')}")
                      # Event listener ekle (geçici olarak)
                    original_handlers = []
                    if hasattr(self.ib, 'pendingTickersEvent'):
                        # Mevcut tüm handler'ları kopyala
                        original_handlers = self.ib.pendingTickersEvent.handlers.copy() if hasattr(self.ib.pendingTickersEvent, 'handlers') else []
                    
                    # Yeni handler ekle
                    self.ib.pendingTickersEvent += on_ticker_update
                    
                    # Periyodik güncelleme için fonksiyon
                    def update_etf_data():
                        # Tüm ETF'leri güncelle
                        for symbol in etf_symbols:
                            if symbol in etf_data:
                                update_etf_row(symbol, etf_tree)
                        
                        # 5 saniyede bir güncelle
                        if not hasattr(etf_window, 'closed') or not etf_window.closed:
                            etf_window.after(5000, update_etf_data)
                    
                    # İlk güncellemeyi başlat
                    etf_window.after(2000, update_etf_data)
                      # Pencere kapandığında temizlik yap 
                    def on_window_close():
                        etf_window.closed = True
                        
                        # Event listener'ı kaldır
                        try:
                            if hasattr(self.ib, 'pendingTickersEvent'):
                                # Önce mevcut ticker update handler'ını kaldır
                                self.ib.pendingTickersEvent -= on_ticker_update
                                
                                # Orijinal handler'ları geri ekle (eğer varsa ve silinmişse)
                                if original_handlers:
                                    # Mevcut handler'ları temizle
                                    curr_handlers = getattr(self.ib.pendingTickersEvent, 'handlers', [])
                                    if not any(h in curr_handlers for h in original_handlers):
                                        # Orijinal handler'ları geri yükle
                                        for handler in original_handlers:
                                            self.ib.pendingTickersEvent += handler
                        except Exception as e:
                            print(f"Event handler temizleme hatası: {str(e)}")
                        
                        # Abonelikleri iptal et
                        for symbol in etf_subscriptions:
                            try:
                                contract = Stock(symbol=symbol, exchange='SMART', currency='USD')
                                self.ib.cancelMktData(contract)
                            except Exception as e:
                                print(f"ETF abonelik iptali hatası ({symbol}): {str(e)}")
                                
                        etf_window.destroy()
                    
                    etf_window.protocol("WM_DELETE_WINDOW", on_window_close)
                  # Refresh için fonksiyon
                def refresh_etf_data(tree, time_label):
                    # Mevcut ticker update handler'ını kaldır
                    try:
                        if hasattr(self.ib, 'pendingTickersEvent'):
                            self.ib.pendingTickersEvent -= on_ticker_update
                    except Exception as e:
                        print(f"Event handler kaldırma hatası: {str(e)}")
                        
                    # Abonelikleri iptal et
                    for symbol in etf_subscriptions:
                        try:
                            contract = Stock(symbol=symbol, exchange='SMART', currency='USD')
                            self.ib.cancelMktData(contract)
                        except Exception as e:
                            print(f"ETF abonelik iptali hatası ({symbol}): {str(e)}")
                    
                    # TreeView'i temizle
                    for item in tree.get_children():
                        tree.delete(item)
                    
                    # ETF verilerini temizle
                    etf_data.clear()
                    etf_subscriptions.clear()
                    
                    # Yeniden abone ol
                    subscribe_etfs()
                
                # Abonelik işlemini başlat
                subscribe_etfs()
                
            except Exception as e:
                loading_label.destroy()
                ttk.Label(etf_window, text=f"ETF verileri yüklenirken hata: {str(e)}", foreground="red").pack(pady=20)
        
        # API çağrılarını kuyruk üzerinden yap
        self.queue_api_call(fetch_etf_data)

    def load_from_spreadci(self):
        """spreadci.csv dosyasından preferred stock'leri yükle"""
        try:
            # Mevcut abonelikleri temizle
            for ticker in list(self.tickers.keys()):
                self.ib.cancelMktData(self.tickers[ticker])
                del self.tickers[ticker]
            
            # Treeview'ı temizle
            for item in self.stock_tree.get_children():
                self.stock_tree.delete(item)
            
            # spreadci.csv'yi oku
            df = pd.read_csv('spreadci.csv')
            
            # Her bir preferred stock için
            for _, row in df.iterrows():
                symbol = row['PREF IBKR']
                if pd.notna(symbol):
                    # Contract oluştur
                    contract = self.create_preferred_stock_contract(symbol)
                    if contract:
                        # Aboneliği başlat
                        self.tickers[symbol] = contract
                        self.ib.reqMktData(contract)
                        
                        # Treeview'a ekle
                        self.stock_tree.insert('', tk.END, values=(
                            symbol,  # ticker
                            '0.00',  # last
                            '0.00',  # bid
                            '0.00',  # ask
                            '0.00',  # spread
                            '0',     # volume
                            '0.00'   # common_change
                        ))
            
            # Abonelik sayısını güncelle
            self.update_subscription_count()
            
            # Bağlantı durumunu güncelle
            if not self.connected:
                self.connect_to_ibkr()
                
        except Exception as e:
            print(f"Error loading from spreadci.csv: {e}")

    def manage_pff_spreads(self):
        """
        Take Profit Mechanism - Mean reversion stratejisine uygun çıkış fırsatları
        - Long pozisyonlar için: PFF'ten pozitif ayrışanları sat
        - Short pozisyonlar için: PFF'ten negatif ayrışanları cover et
        """
        from tkinter import messagebox
        import time
        import pandas as pd
        import math
        from ib_insync import Stock, LimitOrder

        if not self.connected or not self.ib.isConnected():
            messagebox.showerror("Bağlantı Hatası", "Bu işlem için IBKR bağlantısı gereklidir!")
            return
            
        # SMA kontrolü
        sma_limit = 1000
        sma_value = None
        try:
            account_summaries = self.ib.accountSummary()
            for acc in account_summaries:
                if acc.tag == "SMA":
                    try:
                        sma_value = safe_float(acc.value)
                    except:
                        pass
                    break
        except Exception as e:
            messagebox.showwarning("SMA Hatası", f"SMA değeri alınamadı: {e}")
            return
            
        sma_warning = False
        if sma_value is None:
            messagebox.showwarning("SMA Hatası", "SMA değeri alınamadı!")
            sma_warning = True
        elif sma_value < sma_limit:
            messagebox.showwarning("SMA Yetersiz", f"SMA bakiyesi çok düşük: {sma_value}")
            sma_warning = True
            
        # Yükleniyor penceresi
        loading_window = tk.Toplevel(self)
        loading_window.title("Take Profit İşlemi")
        loading_window.geometry("300x150")
        loading_window.transient(self)
        loading_window.grab_set()
        
        # İlerleme çubuğu
        progress_frame = ttk.Frame(loading_window, padding=20)
        progress_frame.pack(fill=tk.BOTH, expand=True)
        
        progress_label = ttk.Label(progress_frame, text="ETF verileri alınıyor...")
        progress_label.pack(pady=10)
        
        progress = ttk.Progressbar(progress_frame, orient=tk.HORIZONTAL, length=250, mode='determinate')
        progress.pack(pady=10)
        progress["value"] = 10
        
        loading_window.update()
        
        # PFF ve TLT verilerini al
        pff_contract = Stock("PFF", "SMART", "USD")
        tlt_contract = Stock("TLT", "SMART", "USD")
        
        # PFF ticker'ı oluştur ve piyasa verisi iste
        self.ib.reqMktData(pff_contract)
        time.sleep(1)  # PFF verisi almak için bekle
        
        # TLT ticker'ı oluştur ve piyasa verisi iste
        self.ib.reqMktData(tlt_contract)
        time.sleep(1)  # TLT verisi almak için bekle
        
        progress["value"] = 30
        progress_label.config(text="ETF değişim verileri alınıyor...")
        loading_window.update()
        
        # PFF ve TLT verilerini çek
        self.ib.sleep(2)  # Biraz daha veri için bekle
        
        # PFF verilerini bul
        pff_ticker = self.ib.ticker(pff_contract)
        pff_last = safe_float(pff_ticker.last)
        
        # changePercent değeri gelmediyse hesapla - place_hidden_bids'deki gibi koruma ekle
        if hasattr(pff_ticker, 'changePercent') and pff_ticker.changePercent is not None:
            pff_change_percent = pff_ticker.changePercent
        elif pff_ticker.close is not None and pff_ticker.last is not None and pff_ticker.close > 0:
            pff_change_percent = ((pff_ticker.last / pff_ticker.close) - 1) * 100
        else:
            pff_change_percent = 0  # Değer yoksa 0 kullan
            
        pff_change_percent = safe_float(pff_change_percent)
        
        # TLT verilerini bul
        tlt_ticker = self.ib.ticker(tlt_contract)
        tlt_last = safe_float(tlt_ticker.last)
        
        # changePercent değeri gelmediyse hesapla - place_hidden_bids'deki gibi koruma ekle
        if hasattr(tlt_ticker, 'changePercent') and tlt_ticker.changePercent is not None:
            tlt_change_percent = tlt_ticker.changePercent
        elif tlt_ticker.close is not None and tlt_ticker.last is not None and tlt_ticker.close > 0:
            tlt_change_percent = ((tlt_ticker.last / tlt_ticker.close) - 1) * 100
        else:
            tlt_change_percent = 0  # Değer yoksa 0 kullan
            
        tlt_change_percent = safe_float(tlt_change_percent)
        
        progress["value"] = 50
        progress_label.config(text="Benchmark değerleri hesaplanıyor...")
        loading_window.update()
        
        if not pff_last or pff_change_percent is None:
            loading_window.destroy()
            messagebox.showerror("Hata", "PFF verisi alınamadı!")
            self.ib.cancelMktData(pff_contract)
            self.ib.cancelMktData(tlt_contract)
            return
            
        if not tlt_last or tlt_change_percent is None:
            loading_window.destroy()
            messagebox.showerror("Hata", "TLT verisi alınamadı!")
            self.ib.cancelMktData(pff_contract)
            self.ib.cancelMktData(tlt_contract)
            return
        
        # PFF ve TLT değişimlerini cent bazında hesapla
        try:
            # Ensure values are valid floats before calculation
            pff_last = safe_float(pff_last, 0.0)
            pff_change_percent = safe_float(pff_change_percent, 0.0)
            tlt_last = safe_float(tlt_last, 0.0)
            tlt_change_percent = safe_float(tlt_change_percent, 0.0)
            
            pff_change_cents = pff_last * (pff_change_percent / 100)
            tlt_change_cents = tlt_last * (tlt_change_percent / 100)
            
            print(f"Debug - PFF values: last={pff_last}, change={pff_change_percent}%, cents={pff_change_cents}")
            print(f"Debug - TLT values: last={tlt_last}, change={tlt_change_percent}%, cents={tlt_change_cents}")
        except Exception as e:
            print(f"Error calculating benchmark changes: {e}")
            # Set to zero if calculation fails
            pff_change_cents = 0.0
            tlt_change_cents = 0.0
        
        # Mevcut pozisyonları al
        progress["value"] = 60
        progress_label.config(text="Pozisyonlar alınıyor...")
        loading_window.update()
        
        positions = []
        try:
            positions = self.ib.positions()
        except Exception as e:
            loading_window.destroy()
            messagebox.showerror("Hata", f"Pozisyonlar alınamadı: {e}")
            return
        
        if not positions:
            loading_window.destroy()
            messagebox.showinfo("Bilgi", "Aktif pozisyon bulunamadı!")
            return
            
        # Pozisyonları ayır (long ve short)
        long_positions = [pos for pos in positions if pos.position > 0]
        short_positions = [pos for pos in positions if pos.position < 0]
        
        if not long_positions and not short_positions:
            loading_window.destroy()
            messagebox.showinfo("Bilgi", "Satılabilecek veya kapatılabilecek pozisyon bulunamadı!")
            return
            
        # Tüm pozisyon sembollerini topla
        position_symbols = [pos.contract.symbol for pos in positions]
            
        # Her pozisyon için market data iste
        progress["value"] = 70
        progress_label.config(text="Pozisyon market verileri alınıyor...")
        loading_window.update()
        
        # Hisseler için sözlük oluştur
        contracts = {}
        
        for symbol in position_symbols:
            contract = Stock(symbol, 'SMART', 'USD')
            contracts[symbol] = contract
            self.ib.reqMktData(contract)
            # Hızlı istekler nedeniyle limit aşımını önlemek için
            time.sleep(0.1)
        
        # Verilerin gelmesi için zaman tanı
        time.sleep(2)
        
        # Benchmark etf'lerine göre kategorize et
        tltr_symbols = [pos.contract.symbol for pos in positions if pos.contract.symbol.startswith("P")]
        div_symbols = [pos.contract.symbol for pos in positions if not pos.contract.symbol.startswith("P")]
        
        # Pozisyon verilerini sözlüğe dönüştür
        position_data = {}
        for pos in positions:
            symbol = pos.contract.symbol
            position_data[symbol] = {
                'symbol': symbol,
                'quantity': pos.position,
                'position_type': 'LONG' if pos.position > 0 else 'SHORT',
                'avg_cost': pos.avgCost,
                'symbol_type': 'TLTR' if symbol in tltr_symbols else 'DIV'
            }
        
        # Her sembol için spread ve benzer verileri hesapla
        progress["value"] = 80
        progress_label.config(text="Çıkış fırsatları hesaplanıyor...")
        loading_window.update()
        
        long_candidates = []
        short_candidates = []
        all_candidates = []
        
        for symbol in position_symbols:
            ticker = self.ib.ticker(contracts[symbol])
            
            # Temel değerler
            last_price = safe_float(ticker.last)
            bid_price = safe_float(ticker.bid)
            ask_price = safe_float(ticker.ask)
            close_price = safe_float(ticker.close)
            
            # changePercent değerini güvenli şekilde al - place_hidden_bids'deki gibi koruma ekle
            daily_change_percent = None
            if hasattr(ticker, 'changePercent') and ticker.changePercent is not None:
                daily_change_percent = ticker.changePercent
            elif ticker.close is not None and ticker.last is not None and ticker.close > 0:
                daily_change_percent = ((ticker.last / ticker.close) - 1) * 100
            else:
                # Değer yoksa atla
                print(f"Uyarı: {symbol} için değişim yüzdesi hesaplanamadı, atlanıyor")
                continue
                
            daily_change_percent = safe_float(daily_change_percent)
            
            # Eksiksiz veri kontrolü
            if not last_price or not bid_price or not ask_price:
                print(f"Uyarı: {symbol} için eksik piyasa verileri, atlanıyor")
                continue
            
            # Spread hesapla
            spread = ask_price - bid_price
            spread_cents = spread * 100  # Cent cinsinden
            
            # Pozisyon tipine göre potansiyel işlem fiyatı
            pos_type = position_data[symbol]['position_type']
            potential_fill_price = 0
            
            if pos_type == 'LONG':
                # Long pozisyonu sat - Spread'in %15'i kadar içeriden teklif ver
                spread_amount = spread_cents * 0.15 / 100
                potential_fill_price = ask_price - spread_amount
            else:  # 'SHORT'
                # Short pozisyonu kapat - Spread'in %15'i kadar içeriden teklif ver
                spread_amount = spread_cents * 0.15 / 100
                potential_fill_price = ask_price + spread_amount
            
            # Günlük değişimi cent olarak hesapla - artık last yerine potansiyel fill fiyatını kullanıyoruz
            if close_price is not None and close_price > 0:
                # Yeni: Potansiyel fill fiyatı üzerinden değişim
                daily_change_cents = (potential_fill_price - close_price) * 100
            else:
                # Veriler eksikse son bilinen fiyat farklılığını kullan
                daily_change_cents = last_price * (daily_change_percent / 100) if daily_change_percent is not None else 0
            
            # Sembol tipine göre benchmark değişimini hesapla
            benchmark_change_cents = 0
            benchmark_formula = ""
            symbol_type = "OTHER"
            
            try:
                if symbol in tltr_symbols:
                    # TLTR formülü: PFF*0.7 + TLT*0.1
                    benchmark_change_cents = ((pff_change_cents * 0.7) + (tlt_change_cents * 0.1)) * 100
                    benchmark_formula = "PFF*0.7 + TLT*0.1"
                    symbol_type = "TLTR"
                elif symbol in div_symbols:
                    # DIV Spread formülü: PFF*1.3 - TLT*0.1
                    benchmark_change_cents = ((pff_change_cents * 1.3) - (tlt_change_cents * 0.1)) * 100
                    benchmark_formula = "PFF*1.3 - TLT*0.1"
                    symbol_type = "DIV"
                else:
                    # Varsayılan: Sadece PFF
                    benchmark_change_cents = pff_change_cents * 100
                    benchmark_formula = "PFF"
                
                # Print debug info to verify values
                print(f"Debug - {symbol} benchmark calc: {benchmark_formula} = {benchmark_change_cents:.2f}¢")
            except Exception as e:
                print(f"Error calculating benchmark for {symbol}: {e}")
                benchmark_change_cents = 0
                benchmark_formula = "ERROR"
            
            # Benchmark'a göre performans farkı hesapla
            relative_to_benchmark_cents = daily_change_cents - benchmark_change_cents
            
            # Pozisyon verilerine yeni bilgileri ekle
            stock_data = {
                'symbol': symbol,
                'exchange': ticker.contract.exchange,
                'quantity': position_data[symbol]['quantity'],
                'last': last_price,
                'bid': bid_price,
                'ask': ask_price,
                'close': close_price,
                'daily_change_percent': daily_change_percent,
                'daily_change_cents': daily_change_cents,
                'benchmark_change_cents': benchmark_change_cents,
                'benchmark_formula': benchmark_formula,
                'relative_to_benchmark_cents': relative_to_benchmark_cents,
                'potential_fill': potential_fill_price,
                'spread': spread,
                'spread_cents': spread_cents,
                'position_type': pos_type,
                'symbol_type': symbol_type
            }
            
            # Pozisyon tipine göre aday listesine ekle
            if pos_type == 'LONG':
                # LONG için pozitif ayrışma olduğunda sat (PFF'ten daha iyi performans)
                # relative_to_benchmark_cents değerinden bağımsız olarak tüm long pozisyonları dahil et
                # ve daha sonra skor hesaplamada pozitif ayrışanları daha yüksek skorla değerlendir
                long_candidates.append(stock_data)
            else:  # 'SHORT'
                # SHORT için negatif ayrışma olduğunda cover et (PFF'ten daha kötü performans)
                # relative_to_benchmark_cents değerinden bağımsız olarak tüm short pozisyonları dahil et
                # ve daha sonra skor hesaplamada negatif ayrışanları daha yüksek skorla değerlendir
                short_candidates.append(stock_data)
        
        progress["value"] = 90
        progress_label.config(text="Sonuçlar hazırlanıyor...")
        loading_window.update()
        
        # Long adayları skorla
        for stock in long_candidates:
            # Safely convert all values before calculation
            spread_cents = safe_float(stock['spread_cents'], 0.0)
            rel_perf_cents = safe_float(stock['relative_to_benchmark_cents'], 0.0)
            
            # Toplam skor: spread_cents + pozitif ayrışma için bonus
            # LONG pozisyonları KAPATMA için:
            # Ne kadar POZİTİF ayrışmışsa o kadar yüksek skor almalı (benchmarktan iyi performans göstermiş longlar)
            # Çünkü benchmarktan iyi performans gösteren longları satma şansımız yüksektir
            stock['score'] = spread_cents + rel_perf_cents  # Pozitif rel_perf değeri skoru yükseltir
            print(f"LONG {stock['symbol']} ({stock['symbol_type']}): Spread {spread_cents:.2f}¢, Rel Perf {rel_perf_cents:.2f}¢, Score: {stock['score']:.2f}")
            all_candidates.append(stock)
        
        # Short adayları skorla
        for stock in short_candidates:
            # Safely convert all values before calculation
            spread_cents = safe_float(stock['spread_cents'], 0.0)
            rel_perf_cents = safe_float(stock['relative_to_benchmark_cents'], 0.0)
            
            # Toplam skor: spread_cents - relative_performance_cents
            # SHORT pozisyonları KAPATMA için:
            # Ne kadar NEGATİF ayrışmışsa o kadar yüksek skor almalı (benchmarktan kötü performans göstermiş shortlar)
            # Çünkü benchmarktan kötü performans gösteren shortları örtme (cover) şansımız yüksektir
            stock['score'] = spread_cents - rel_perf_cents  # Negatif rel_perf değeri skoru yükseltir (eksi eksi artı olur)
            print(f"SHORT {stock['symbol']} ({stock['symbol_type']}): Spread {spread_cents:.2f}¢, Rel Perf {rel_perf_cents:.2f}¢, Score: {stock['score']:.2f}")
            all_candidates.append(stock)
        
        # Aday yoksa bilgi ver ve çık
        if not all_candidates:
            loading_window.destroy()
            messagebox.showinfo("Bilgi", "PFF'e göre uygun çıkış fırsatı bulunan hisse bulunamadı!")
            # Abonelikleri temizle
            for symbol in position_symbols:
                self.ib.cancelMktData(contracts[symbol])
            self.ib.cancelMktData(pff_contract)
            self.ib.cancelMktData(tlt_contract)
            return
        
        # Skora göre sırala (yüksekten düşüğe)
        all_candidates.sort(key=lambda x: x['score'], reverse=True)
        
        # İlk 10 adayı al (veya tümü daha azsa)
        top_candidates = all_candidates[:10] if len(all_candidates) > 10 else all_candidates
        
        # Emir listesi oluştur
        orders_to_place = []
        
        for stock in top_candidates:
            # Pozisyon tipine göre emir detayları
            if stock['position_type'] == 'LONG':
                # Long pozisyonu sat
                # Spread'in %15'i kadar içeriden teklif ver
                spread_amount = stock['spread_cents'] * 0.15 / 100
                
                # Satış fiyatı: Ask - spread'in %15'i (Daha agresif satış emri)
                sell_price = stock['ask'] - spread_amount
                
                # Uygun miktarı belirle (max 200 adet)
                quantity = min(200, safe_int(stock['quantity']))
                
                orders_to_place.append({
                    'symbol': stock['symbol'],
                    'order_type': 'SELL (Hidden)',
                    'price': round(safe_float(sell_price), 2),
                    'quantity': quantity,
                    'venue': stock['exchange'],
                    'daily_change': safe_format_float(stock['daily_change_percent']) + "%",
                    'daily_change_cents': safe_format_float(stock['daily_change_cents']) + "¢",
                    'benchmark_change': safe_format_float(stock['benchmark_change_cents']) + "¢",
                    'relative_to_benchmark': safe_format_float(stock['relative_to_benchmark_cents']) + "¢",
                    'spread': safe_format_float(stock['spread_cents']) + "¢",
                    'score': safe_format_float(stock['score']),
                    'note': f"LONG SAT: Spread: {safe_format_float(stock['spread_cents'])}¢, vs {stock['benchmark_formula']}: {safe_format_float(stock['relative_to_benchmark_cents'])}¢, Toplam Skor: {safe_format_float(stock['score'])}",
                    'selected': True  # Varsayılan olarak seçili
                })
            else:  # 'SHORT'
                # Short pozisyonu kapat (cover)
                # Spread'in %15'i kadar içeriden teklif ver
                spread_amount = stock['spread_cents'] * 0.15 / 100
                
                # Alış fiyatı: Ask + spread'in %15'i (Daha agresif alış emri)
                buy_price = stock['ask'] + spread_amount
                
                # Uygun miktarı belirle (max 200 adet, abs kullan çünkü short miktarı negatif)
                quantity = min(200, abs(safe_int(stock['quantity'])))
                
                orders_to_place.append({
                    'symbol': stock['symbol'],
                    'order_type': 'BUY (Hidden)',
                    'price': round(safe_float(buy_price), 2),
                    'quantity': quantity,
                    'venue': stock['exchange'],
                    'daily_change': safe_format_float(stock['daily_change_percent']) + "%",
                    'daily_change_cents': safe_format_float(stock['daily_change_cents']) + "¢",
                    'benchmark_change': safe_format_float(stock['benchmark_change_cents']) + "¢",
                    'relative_to_benchmark': safe_format_float(stock['relative_to_benchmark_cents']) + "¢",
                    'spread': safe_format_float(stock['spread_cents']) + "¢",
                    'score': safe_format_float(stock['score']),
                    'note': f"SHORT COVER: Spread: {safe_format_float(stock['spread_cents'])}¢, vs {stock['benchmark_formula']}: {safe_format_float(stock['relative_to_benchmark_cents'])}¢, Toplam Skor: {safe_format_float(stock['score'])}",
                    'selected': True  # Varsayılan olarak seçili
                })
        
        # Debug: Kaç emir oluşturuldu?
        print(f"Toplam {len(orders_to_place)} emir oluşturuldu")
        
        # Loading penceresini kapat
        loading_window.destroy()
        
        # Eğer emirler varsa, emir önizleme penceresini göster
        if orders_to_place:
            # Hidden Bid Placement UI'ı gibi emir önizleme penceresi oluştur
            self.show_take_profit_orders(orders_to_place, contracts, pff_contract, tlt_contract, position_symbols)
        else:
            messagebox.showinfo("Bilgi", "Uygun emir oluşturulamadı!")
            
            # Abonelikleri temizle
            for symbol in position_symbols:
                self.ib.cancelMktData(contracts[symbol])
            self.ib.cancelMktData(pff_contract)
            self.ib.cancelMktData(tlt_contract)

    def preview_hidden_bids(self):
        from tkinter import messagebox
        import time
        from ib_insync import Stock, LimitOrder

        if not self.connected or not self.ib.isConnected():
            messagebox.showerror("Bağlantı Hatası", "Bu işlem için IBKR bağlantısı gereklidir!")
            return

        visible_stocks = self.get_visible_stocks()
        if not visible_stocks:
            messagebox.showinfo("Bilgi", "Görünür hisse bulunamadı!")
            return

        symbols = [row['PREF IBKR'] for row in visible_stocks if row.get('PREF IBKR')]
        market_data = {}
        contracts = {}

        # Market data aboneliklerini başlat
        for symbol in symbols:
            try:
                contract = Stock(symbol, 'SMART', 'USD')
                contracts[symbol] = contract
                market_data[symbol] = self.ib.reqMktData(contract, genericTickList="233", snapshot=False)
            except Exception as e:
                print(f"Market data aboneliği hatası ({symbol}): {e}")

        # Dashboard penceresi
        dashboard = tk.Toplevel(self)
        dashboard.title("Canlı Emir Önizleme")
        dashboard.geometry("900x500")
        columns = ("symbol", "bid", "ask", "last", "spread", "volume")
        tree = ttk.Treeview(dashboard, columns=columns, show="headings")
        for col, title in zip(columns, ["Sembol", "Bid", "Ask", "Last", "Spread", "Volume"]):
            tree.heading(col, text=title)
        for symbol in symbols:
            tree.insert("", "end", iid=symbol, values=(symbol, "-", "-", "-", "-", "-"))
        tree.pack(expand=True, fill="both", padx=10, pady=10)

        def update_market_data():
            for symbol in symbols:
                data = market_data[symbol]
                bid = f"{data.bid:.2f}" if data.bid is not None else "-"
                ask = f"{data.ask:.2f}" if data.ask is not None else "-"
                last = f"{data.last:.2f}" if data.last is not None else "-"
                spread = f"{(data.ask - data.bid)*100:.2f}¢" if data.bid is not None and data.ask is not None else "-"
                volume = f"{int(data.volume):,}" if data.volume is not None else "-"
                tree.item(symbol, values=(symbol, bid, ask, last, spread, volume))
            dashboard.after(500, update_market_data)

        update_market_data()

        def onayla():
            for symbol in symbols:
                data = market_data[symbol]
                if data.bid is not None and data.ask is not None:
                    spread_cents = (data.ask - data.bid) * 100
                    suggested_price = data.bid + (spread_cents * 0.1 / 100)
                    try:
                        contract = contracts[symbol]
                        limit_order = LimitOrder('BUY', 200, round(suggested_price, 2))
                        limit_order.hidden = True
                        self.ib.placeOrder(contract, limit_order)
                        print(f"Emir gönderildi: {symbol} @ {suggested_price:.2f}")
                    except Exception as e:
                        print(f"Emir gönderme hatası: {symbol} - {e}")
            messagebox.showinfo("Başarılı", "Emirler başarıyla gönderildi!")
            dashboard.destroy()

        def iptal():
            for symbol in symbols:
                self.ib.cancelMktData(contracts[symbol])
            dashboard.destroy()

        btn_frame = tk.Frame(dashboard)
        btn_frame.pack(pady=10)
        tk.Button(btn_frame, text="Onayla ve Emirleri Gönder", command=onayla, bg="green", fg="white").pack(side="left", padx=10)
        tk.Button(btn_frame, text="İptal", command=iptal, bg="red", fg="white").pack(side="left", padx=10)

    def on_tab_changed(self, event=None):
        """Sekme değişince sadece aktif sekmenin ticker'ları için canlı veri başlat"""
        # Sekme değişimi olduğunu belirt
        print("\n--- Sekme değişimi yapılıyor ---")
        
        # Eski abonelikleri temizle - bu kritik!
        old_symbols = self.focused_symbols.copy()
        
        # Tüm odaklanılan sembolleri temizle
        self.focused_symbols.clear()
        
        # Aktif sekmeyi belirle
        current_tab = self.notebook.index(self.notebook.select()) if self.notebook.select() else 0
        self.active_tab = current_tab
        
        # Sayfa cache'i için key üret
        if current_tab == 0:  # TLTR Prefs sekmesi
            page_key = f"page_0_{self.tltr_current_page}"
        else:  # DIV Spread sekmesi
            page_key = f"page_1_{self.divspread_current_page}"
        
        print(f"Sekme değişti: Tab {current_tab}, Page Key: {page_key}")
            
        # Artık odakta olmayan sembollerin aboneliklerini iptal et
        for symbol in old_symbols:
            self.market_data_cache.remove_subscription(symbol, self.ib)
            
        # Eğer bu sayfa için bir cache varsa, kullan
        if page_key in self.page_data_snapshots:
            page_data = self.page_data_snapshots[page_key]
            # Cache 5 dakikadan eskiyse, yeniden yükle
            if time.time() - page_data['last_update'] > 300:  # 5 dakika
                print(f"Cache eski, yenileniyor: {page_key}")
                # Cache'i güncelle
                self.populate_treeview()
            else:
                # Mevcut sembolleri odaklanılan semboller listesine ekle
                new_symbols = set(page_data['symbols'])
                self.focused_symbols.update(new_symbols)
                print(f"Cache kullanılıyor: {page_key} - {len(new_symbols)} sembol")
                # TreeView'ı güncellemek için mevcut verileri kullan
                self.populate_treeview_from_cache(current_tab, list(new_symbols))
        else:
            # Cache yok, normal populate işlemi yap
            print(f"Cache bulunamadı, yeni veri çekiliyor: {page_key}")
            # Aktif sekmenin sayfa numarasını sıfırla (her sekme değişiminde ilk sayfadan başla)
            if current_tab == 0:  # TLTR Prefs sekmesi
                self.tltr_current_page = 1
            else:  # DIV Spread sekmesi
                self.divspread_current_page = 1
            
            # TreeView'ı aktif sekme için güncelle
            self.populate_treeview()
            
        # Abonelik sayısını güncelle
        self.subscription_count_label.config(text=f"Aktif abonelikler: {len(self.market_data_cache.active_subscriptions)}/40")
            
    def populate_treeview_from_cache(self, tab_index, symbols):
        """Cache'den alınan verilerle TreeView'ı doldur"""
        if tab_index == 0:
            tree = self.tltr_tree
            page = self.tltr_current_page
            total_tickers = len(self.tltr_tickers)
        else:
            tree = self.divspread_tree
            page = self.divspread_current_page
            total_tickers = len(self.divspread_tickers)
            
        # TreeView'ı temizle
        tree.delete(*tree.get_children())
        
        # Cache'deki verileri kullanarak TreeView'ı doldur
        for symbol in symbols:
            # Cache'de varsa değerleri al
            cached_data = self.market_data_cache.get(symbol)
            if cached_data:
                last = f"{cached_data.get('last', 0):.2f}" if 'last' in cached_data else "-"
                bid = f"{cached_data.get('bid', 0):.2f}" if 'bid' in cached_data else "-"
                ask = f"{cached_data.get('ask', 0):.2f}" if 'ask' in cached_data else "-"
                
                if 'bid' in cached_data and 'ask' in cached_data:
                    spread = f"{(cached_data['ask'] - cached_data['bid']):.2f}"
                else:
                    spread = "-"
                    
                volume = f"{int(cached_data.get('volume', 0)):,}" if 'volume' in cached_data else "-"
                
                tree.insert("", "end", values=(symbol, last, bid, ask, spread, volume))
            else:
                # Cache'de yoksa boş değerlerle ekle
                tree.insert("", "end", values=(symbol, "-", "-", "-", "-", "-"))
                
        # Sayfa bilgisini güncelle
        items_per_page = 20
        total_pages = max(1, (total_tickers + items_per_page - 1) // items_per_page)
        self.page_info_label.config(text=f"Sayfa {page}/{total_pages}")
        
        # Fokus sembollere abone ol
        self.subscribe_page_tickers(list(symbols))

    def populate_treeview_page(self):
        if self.active_tab == 0:
            tree = self.tltr_tree
            tickers = self.tltr_tickers
            page = self.tltr_current_page
        else:
            tree = self.divspread_tree
            tickers = self.divspread_tickers
            page = self.divspread_current_page
        items_per_page = 20
        start = (page - 1) * items_per_page
        end = start + items_per_page
        page_tickers = tickers[start:end]
        tree.delete(*tree.get_children())
        for t in page_tickers:
            tree.insert("", "end", values=(t, "-", "-", "-", "-", "-"))
        total_pages = max(1, (len(tickers) + items_per_page - 1) // items_per_page)
        self.page_info_label.config(text=f"Sayfa {page}/{total_pages}")
        self.activate_tickers(page_tickers)

    def activate_tickers(self, tickers):
        # Önce tüm eski abonelikleri iptal et
        for ticker_info in list(getattr(self, 'tickers', {}).values()):
            if 'contract' in ticker_info:
                try:
                    self.ib.cancelMktData(ticker_info['contract'])
                except Exception:
                    pass
        self.tickers = {}
        # Sadece yeni tickerlar için abonelik başlat
        for symbol in tickers:
            if not symbol:
                continue
            try:
                contract = Stock(symbol, 'SMART', 'USD')
                self.ib.reqMktData(contract)
                self.tickers[symbol] = {'contract': contract}
            except Exception:
                pass
                
    def show_take_profit_orders(self, orders, contracts, pff_contract, tlt_contract, position_symbols):
        """
        Take Profit emirlerini önizleme penceresi ile göster
        Hidden Bid Placement'a benzer UI tasarımı
        """
        from tkinter import ttk, messagebox, font
        import math
        from ib_insync import Stock, LimitOrder

        # Ana pencere
        dashboard = tk.Toplevel(self)
        dashboard.title("Take Profit Emir Önizleme")
        dashboard.geometry("1550x650")
        dashboard.grab_set()  # Modal pencere yap

        # Tüm emirleri sakla
        all_orders = orders.copy()
        
        # Toplam emir sayısı
        total_orders = len(all_orders)
        
        # Sayfalama değişkenleri
        items_per_page = 20
        current_page = 1
        total_pages = math.ceil(total_orders / items_per_page)
        
        # Seçili durum bilgisi
        for order in all_orders:
            if 'selected' not in order:
                order['selected'] = True  # Varsayılan olarak seçili
        
        # Stil oluştur
        style = ttk.Style()
        style.configure("Accent.TButton", font=('Arial', 10, 'bold'))
        
        # PFF/TLT bilgisi için frame
        info_frame = ttk.Frame(dashboard, padding=5)
        info_frame.pack(fill=tk.X, padx=5, pady=5)
        
        # PFF ve TLT bilgilerini al
        pff_ticker = self.ib.ticker(pff_contract)
        tlt_ticker = self.ib.ticker(tlt_contract)
        pff_last = safe_float(pff_ticker.last, 0.0)
        tlt_last = safe_float(tlt_ticker.last, 0.0)
        
        # PFF/TLT değişim yüzdeleri
        pff_change = 0.0
        tlt_change = 0.0
        
        if hasattr(pff_ticker, 'changePercent') and pff_ticker.changePercent is not None:
            pff_change = pff_ticker.changePercent
        elif pff_ticker.close is not None and pff_ticker.last is not None and pff_ticker.close > 0:
            pff_change = ((pff_ticker.last / pff_ticker.close) - 1) * 100
            
        if hasattr(tlt_ticker, 'changePercent') and tlt_ticker.changePercent is not None:
            tlt_change = tlt_ticker.changePercent
        elif tlt_ticker.close is not None and tlt_ticker.last is not None and tlt_ticker.close > 0:
            tlt_change = ((tlt_ticker.last / tlt_ticker.close) - 1) * 100
        
        # SMA bilgisini al
        sma_value = None
        try:
            account_summaries = self.ib.accountSummary()
            for acc in account_summaries:
                if acc.tag == "SMA":
                    sma_value = safe_float(acc.value, 0.0)
                    break
        except Exception as e:
            print(f"SMA değeri alınamadı: {e}")
            
        # ETF ve SMA bilgileri
        etf_info = f"PFF: ${pff_last:.2f} ({pff_change:.2f}% = {pff_change*pff_last/100:.2f}¢) | TLT: ${tlt_last:.2f} ({tlt_change:.2f}% = {tlt_change*tlt_last/100:.2f}¢)"
        if sma_value is not None:
            etf_info += f" | SMA: ${sma_value:.2f}"
            
        ttk.Label(info_frame, text=etf_info, font=('Arial', 9)).pack(side=tk.LEFT, padx=5)
        
        # Sayfa bilgisi
        page_var = tk.StringVar(value=f"Sayfa {current_page}/{total_pages}")
        page_label = ttk.Label(info_frame, textvariable=page_var, font=('Arial', 9))
        page_label.pack(side=tk.RIGHT, padx=5)
        
        # Mevcut sayfadaki emirleri al
        def get_current_page_orders():
            start_idx = (current_page - 1) * items_per_page
            end_idx = min(start_idx + items_per_page, len(all_orders))
            return all_orders[start_idx:end_idx]
        
        # Sayfa değiştirme
        def change_page(page_num):
            nonlocal current_page
            if 1 <= page_num <= total_pages:
                current_page = page_num
                page_var.set(f"Sayfa {current_page}/{total_pages}")
                update_page()
        
        # Sayfalama frame'i
        page_frame = ttk.Frame(dashboard, padding=5)
        page_frame.pack(fill=tk.X, padx=5)
        
        ttk.Button(page_frame, text="< Önceki Sayfa", command=lambda: change_page(max(1, current_page-1))).pack(side=tk.LEFT, padx=5)
        ttk.Button(page_frame, text="Sonraki Sayfa >", command=lambda: change_page(min(total_pages, current_page+1))).pack(side=tk.LEFT, padx=5)
        
        # Emir listesi frame'i
        list_frame = ttk.Frame(dashboard)
        list_frame.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)
        
        # TreeView
        columns = ("sec", "symbol", "tip", "emir_tipi", "fiyat", "miktar", "model_shares", "mevcut_shares", 
                 "daily_chg", "daily_chg_cents", "benchmark", "bench_chg_cents", "vs_bench_cents", 
                 "spread", "skor", "not_detay")
        order_tree = ttk.Treeview(list_frame, columns=columns, show="headings", selectmode="browse")
        
        # Sütun başlıkları
        order_tree.heading("sec", text="Seç")
        order_tree.heading("symbol", text="Sembol")
        order_tree.heading("tip", text="Tip")
        order_tree.heading("emir_tipi", text="Emir Tipi")
        order_tree.heading("fiyat", text="Fiyat")
        order_tree.heading("miktar", text="Miktar")
        order_tree.heading("model_shares", text="Model Shares")
        order_tree.heading("mevcut_shares", text="Mevcut Shares")
        order_tree.heading("daily_chg", text="Daily Chg")
        order_tree.heading("daily_chg_cents", text="Daily Chg ¢")
        order_tree.heading("benchmark", text="Benchmark")
        order_tree.heading("bench_chg_cents", text="Bench Chg ¢")
        order_tree.heading("vs_bench_cents", text="vs Bench ¢")
        order_tree.heading("spread", text="Spread")
        order_tree.heading("skor", text="Skor")
        order_tree.heading("not_detay", text="Not/Detay")
        
        # Sütun genişlikleri
        order_tree.column("sec", width=40, anchor=tk.CENTER)
        order_tree.column("symbol", width=80, anchor=tk.CENTER)
        order_tree.column("tip", width=40, anchor=tk.CENTER)
        order_tree.column("emir_tipi", width=90, anchor=tk.CENTER)
        order_tree.column("fiyat", width=60, anchor=tk.CENTER)
        order_tree.column("miktar", width=60, anchor=tk.CENTER)
        order_tree.column("model_shares", width=100, anchor=tk.CENTER)
        order_tree.column("mevcut_shares", width=100, anchor=tk.CENTER)
        order_tree.column("daily_chg", width=80, anchor=tk.CENTER)
        order_tree.column("daily_chg_cents", width=90, anchor=tk.CENTER)
        order_tree.column("benchmark", width=120, anchor=tk.CENTER)
        order_tree.column("bench_chg_cents", width=90, anchor=tk.CENTER)
        order_tree.column("vs_bench_cents", width=90, anchor=tk.CENTER)
        order_tree.column("spread", width=70, anchor=tk.CENTER)
        order_tree.column("skor", width=60, anchor=tk.CENTER)
        order_tree.column("not_detay", width=250, anchor=tk.W)
        
        # Scrollbar
        scrollbar = ttk.Scrollbar(list_frame, orient="vertical", command=order_tree.yview)
        order_tree.configure(yscrollcommand=scrollbar.set)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        order_tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        
        # Item seçme/seçimi kaldırma
        def toggle_selection(item_id):
            # İlgili siparişi bul
            for order in all_orders:
                if f"{order['symbol']}_{order['order_type']}" == item_id:
                    order['selected'] = not order['selected']
                    break
            update_page()
            
        # Çift tıklama olayı - satır seçimini değiştir
        order_tree.bind("<Double-1>", lambda event: toggle_selection(order_tree.selection()[0]) if order_tree.selection() else None)
        
        # Tümünü seç/kaldır fonksiyonları
        def toggle_all_selections():
            # Mevcut sayfadaki tüm siparişleri seç/kaldır
            any_selected = any(order['selected'] for order in get_current_page_orders())
            
            for order in get_current_page_orders():
                order['selected'] = not any_selected
                
            update_page()
        
        # Tüm seçimleri kaldır
        def clear_all_selections():
            for order in all_orders:
                order['selected'] = False
            update_page()
        
        # Sayfayı güncelle
        def update_page():
            # Treeview'ı temizle
            order_tree.delete(*order_tree.get_children())
            
            # Mevcut sayfadaki emirleri göster
            page_orders = get_current_page_orders()
            for order in page_orders:
                # Benzersiz ID oluştur
                order_id = f"{order['symbol']}_{order['order_type']}"
                
                # Emir tipi kısaltması (TLTR/DIV)
                tip = "TLTR" if "TLTR" in order.get('note', '') else "DIV"
                
                # Model ve mevcut hisse değerleri
                model_shares = "-"  # Take Profit için kullanılmıyor
                mevcut_shares = "-"  # Take Profit için kullanılmıyor
                
                # Seçim durumu
                check_mark = "✓" if order['selected'] else ""
                
                # TreeView'e ekle
                order_tree.insert(
                    "", "end", iid=order_id,
                    values=(
                        check_mark,  # Seçildi işareti
                        order['symbol'],  # Sembol
                        tip,  # Tip (TLTR/DIV)
                        order['order_type'],  # Emir tipi
                        f"{order['price']:.2f}",  # Fiyat
                        order['quantity'],  # Miktar
                        model_shares,  # Model shares (Take Profit için boş)
                        mevcut_shares,  # Mevcut shares (Take Profit için boş)
                        order.get('daily_change', "-"),  # Daily change (%)
                        order.get('daily_change_cents', "-"),  # Daily change (cents)
                        order.get('benchmark_change', "-").replace("PFF*0.7 + TLT*0.1", "PFF*0.7 + TLT*0.1"),  # Benchmark
                        order.get('benchmark_change', "-"),  # Benchmark change (cents)
                        order.get('relative_to_benchmark', "-"),  # vs Benchmark (cents)
                        order.get('spread', "-"),  # Spread
                        order.get('score', "nan"),  # Skor
                        order.get('note', "")  # Not/Detay
                    )
                )
                
                # Tür bazlı renklendirme
                if "SELL" in order['order_type']:
                    order_tree.item(order_id, tags=('sell',))
                else:
                    order_tree.item(order_id, tags=('buy',))
                    
            # Türlere göre renklendirme
            order_tree.tag_configure('sell', background='#ffe6e6')  # Satış için açık kırmızı
            order_tree.tag_configure('buy', background='#e6ffe6')   # Alış için açık yeşil
            
        # Satırlar arasında gezinme ve değiştirme
        def on_tree_click(event):
            # Tıklanan sütunu belirle
            region = order_tree.identify_region(event.x, event.y)
            column = order_tree.identify_column(event.x)
            
            if region == "cell" and column == "#1":  # Seç sütunu
                item = order_tree.identify_row(event.y)
                if item:
                    toggle_selection(item)
                    
        # Tıklama olayını bağla
        order_tree.bind("<ButtonRelease-1>", on_tree_click)
        
        # Buton frame'i
        button_frame = ttk.Frame(dashboard, padding=5)
        button_frame.pack(fill=tk.X, padx=5, pady=5)
        
        ttk.Button(button_frame, text="Tümünü Seç", command=toggle_all_selections).pack(side=tk.LEFT, padx=5)
        ttk.Button(button_frame, text="Tümünü Kaldır", command=clear_all_selections).pack(side=tk.LEFT, padx=5)
        
        # Alt panel
        bottom_frame = ttk.Frame(dashboard, padding=10)
        bottom_frame.pack(fill=tk.X, padx=5, pady=10)
        
        # Bilgi içerikli metin kutusu
        instructions = ttk.Label(
            bottom_frame,
            text="Lütfen göndermek istediğiniz emirleri seçin ve 'ONAYLA VE EMİRLERİ GÖNDER' butonuna tıklayın",
            font=('Arial', 10)
        )
        instructions.pack(fill=tk.X, pady=5)
        
        # Buton çerçevesi
        btn_frame = ttk.Frame(bottom_frame)
        btn_frame.pack(fill=tk.X, pady=5)
        
        # Onayla fonksiyonu
        def onayla():
            try:
                # Seçilen emirleri topla
                selected_orders = [order for order in all_orders if order.get('selected', False)]
                
                if not selected_orders:
                    messagebox.showinfo("Bilgi", "Lütfen en az bir emir seçin.")
                    return
                
                # Kullanıcı onayı al
                confirm = messagebox.askyesno(
                    "Onay", 
                    f"{len(selected_orders)} adet emir gönderilecek. Onaylıyor musunuz?"
                )
                
                if not confirm:
                    return
                    
                # Emirleri gönder
                for order in selected_orders:
                    symbol = order['symbol']
                    price = order['price']
                    quantity = order['quantity']
                    order_type = order['order_type']
                    
                    # Kontrat oluştur
                    if symbol in contracts:
                        contract = contracts[symbol]
                    else:
                        contract = Stock(symbol, 'SMART', 'USD')
                    
                    # Emir tipi
                    if "SELL" in order_type:
                        action = 'SELL'
                    else:  # "BUY"
                        action = 'BUY'
                    
                    # Emir oluştur ve gönder
                    limit_order = LimitOrder(action, quantity, round(price, 2))
                    limit_order.hidden = True
                    self.ib.placeOrder(contract, limit_order)
                    print(f"Emir gönderildi: {symbol} @ {price:.2f} x {quantity}")
                
                messagebox.showinfo("Başarılı", f"{len(selected_orders)} emir başarıyla gönderildi!")
                
            except Exception as e:
                messagebox.showerror("Hata", f"Emirler gönderilirken hata: {str(e)}")
            finally:
                # Abonelikleri temizle
                for symbol in position_symbols:
                    if symbol in contracts:
                        self.ib.cancelMktData(contracts[symbol])
                self.ib.cancelMktData(pff_contract)
                self.ib.cancelMktData(tlt_contract)
                
                # Pencereyi kapat
                dashboard.destroy()
        
        # İptal fonksiyonu
        def iptal():
            # Abonelikleri temizle
            for symbol in position_symbols:
                if symbol in contracts:
                    self.ib.cancelMktData(contracts[symbol])
            self.ib.cancelMktData(pff_contract)
            self.ib.cancelMktData(tlt_contract)
            
            # Pencereyi kapat
            dashboard.destroy()
        
        # Daha büyük ve daha görünür Onayla butonu
        confirm_btn = ttk.Button(
            btn_frame, 
            text="ONAYLA VE EMİRLERİ GÖNDER", 
            command=onayla, 
            style="Accent.TButton"
        )
        confirm_btn.pack(side=tk.LEFT, padx=20, pady=10, fill=tk.X, expand=True, ipadx=20, ipady=10)  # Genişletilmiş buton
        
        # İptal butonu
        cancel_btn = ttk.Button(
            btn_frame, 
            text="İPTAL", 
            command=iptal,
            style="TButton"
        )
        cancel_btn.pack(side=tk.RIGHT, padx=20, pady=10, ipadx=10, ipady=10)
        
        # Sayfayı ilk kez güncelle
        update_page()
        
        # Bilgilendirme metni
        note_label = ttk.Label(
            bottom_frame,
            text="Not: Take Profit mekanizması, benchmarktan pozitif ayrışan LONGları ve negatif ayrışan SHORTları kapatmayı hedefler.",
            font=('Arial', 8), foreground='gray'
        )
        note_label.pack(side=tk.BOTTOM, pady=(10, 0))

    def open_spreadci_window(self):
        """Spreadci veri penceresini aç"""
        window = SpreadciDataWindow(self)
        window.protocol("WM_DELETE_WINDOW", window.on_closing)  # Kapatma olayını ayarla

    def compress_market_data(self, data):
        # Veriyi binary formata dönüştür
        binary_data = struct.pack('!4fI', 
            data['bid'],
            data['ask'],
            data['last'],
            data['volume']
        )
        return binary_data

    def decompress_market_data(self, binary_data):
        # Binary veriyi aç
        bid, ask, last, volume = struct.unpack('!4fI', binary_data)
        return {
            'bid': bid,
            'ask': ask,
            'last': last,
            'volume': volume
        }

    def send_orders(self, orders):
        for order in orders:
            # Burada IBKR API ile gerçek emir gönderme kodunuz olacak
            print(f"Emir gönderildi: {order}")
        messagebox.showinfo("Başarılı", "Emirler başarıyla gönderildi!")

    def place_hidden_bids(self):
        """
        Hidden Bid Placement - Opt50 portföy hisselerine gizli emirler yerleştir
        """
        from tkinter import messagebox
        import time
        import os
        import pandas as pd
        from ib_insync import Stock, LimitOrder

        if not self.connected or not self.ib.isConnected():
            messagebox.showerror("Bağlantı Hatası", "Bu işlem için IBKR bağlantısı gereklidir!")
            return

        # SMA kontrolü
        sma_limit = 1000
        sma_value = None
        try:
            # SMA değerini IBKR'dan çek
            account_summaries = self.ib.accountSummary()
            for acc in account_summaries:
                if acc.tag == "SMA":
                    try:
                        sma_value = float(acc.value)
                    except:
                        pass
                    break
        except Exception as e:
            messagebox.showwarning("SMA Hatası", f"SMA değeri alınamadı: {e}")
            return

        sma_warning = False
        if sma_value is None:
            messagebox.showwarning("SMA Hatası", "SMA değeri alınamadı!")
            sma_warning = True
        elif sma_value < sma_limit:
            messagebox.showwarning("SMA Yetersiz", f"SMA bakiyesi çok düşük: {sma_value}")
            sma_warning = True

        # Opt50 portföy dosyasını kontrol et ve yükle
        portfolio_file = "optimized_50_stocks_portfolio.csv"
        if not os.path.exists(portfolio_file):
            messagebox.showerror("Dosya Bulunamadı", f"{portfolio_file} dosyası bulunamadı!")
            return
        
        # Opt50 portföyünü yükle
        try:
            df = pd.read_csv(portfolio_file)
            opt50_symbols = df["PREF IBKR"].dropna().tolist()
            if not opt50_symbols:
                messagebox.showinfo("Bilgi", "Opt50 portföyünde hisse bulunamadı!")
                return
        except Exception as e:
            messagebox.showerror("Portföy Yükleme Hatası", f"Opt50 portföyü yüklenirken hata: {str(e)}")
            return

        # Mevcut pozisyonları al
        try:
            current_positions = self.ib.positions()
            position_dict = {}
            for pos in current_positions:
                position_dict[pos.contract.symbol] = pos.position
        except Exception as e:
            messagebox.showerror("Pozisyon Hatası", f"Mevcut pozisyonlar alınamadı: {str(e)}")
            return

        market_data = {}
        contracts = {}

        # TLTR ve DIV spread sembollerini yükle
        try:
            # TLTR sekmesi için
            df_tltr = pd.read_csv("sma_results.csv")
            df_tltr = normalize_ticker_column(df_tltr)
            tltr_symbols = set(df_tltr["Ticker"].dropna().unique().tolist())
            
            # DIV Spread sekmesi için
            df_div = pd.read_csv("extlt_results.csv")
            df_div = normalize_ticker_column(df_div)
            div_symbols = set(df_div["Ticker"].dropna().unique().tolist())
            
            print(f"TLTR sembolleri: {len(tltr_symbols)}, DIV sembolleri: {len(div_symbols)}")
        except Exception as e:
            print(f"Sembol listelerini yükleme hatası: {e}")
            tltr_symbols = set()
            div_symbols = set()

        # PFF ve TLT verilerini çek
        pff_contract = Stock('PFF', 'SMART', 'USD')
        tlt_contract = Stock('TLT', 'SMART', 'USD')
        self.ib.reqMktData(pff_contract, genericTickList="233,236", snapshot=False)
        self.ib.reqMktData(tlt_contract, genericTickList="233,236", snapshot=False)
        
        # PFF ve TLT verilerinin gelmesini bekle
        pff_last = None
        pff_change_percent = None
        tlt_last = None
        tlt_change_percent = None
        
        for _ in range(20):  # Max 10 saniye bekle
            self.ib.sleep(0.5)
            
            # PFF verilerini kontrol et
            for ticker in self.ib.tickers():
                if ticker.contract.symbol == 'PFF':
                    pff_last = ticker.last
                    # changePercent değeri gelmediyse hesapla
                    if hasattr(ticker, 'changePercent') and ticker.changePercent is not None:
                        pff_change_percent = ticker.changePercent
                    elif ticker.close is not None and ticker.last is not None and ticker.close > 0:
                        pff_change_percent = ((ticker.last / ticker.close) - 1) * 100
                
                elif ticker.contract.symbol == 'TLT':
                    tlt_last = ticker.last
                    # changePercent değeri gelmediyse hesapla
                    if hasattr(ticker, 'changePercent') and ticker.changePercent is not None:
                        tlt_change_percent = ticker.changePercent
                    elif ticker.close is not None and ticker.last is not None and ticker.close > 0:
                        tlt_change_percent = ((ticker.last / ticker.close) - 1) * 100
            
            # Tüm gerekli veriler geldiyse döngüden çık
            if (pff_last is not None and pff_change_percent is not None and 
                tlt_last is not None and tlt_change_percent is not None):
                break
        
        if pff_last is None or pff_change_percent is None:
            messagebox.showwarning("PFF Verisi Alınamadı", "PFF fiyat veya değişim verisi alınamadı!")
            self.ib.cancelMktData(pff_contract)
            self.ib.cancelMktData(tlt_contract)
            return
            
        if tlt_last is None or tlt_change_percent is None:
            messagebox.showwarning("TLT Verisi Alınamadı", "TLT fiyat veya değişim verisi alınamadı!")
            self.ib.cancelMktData(pff_contract)
            self.ib.cancelMktData(tlt_contract)
            return

        # PFF ve TLT değişimlerini cent bazında hesapla
        pff_change_cents = pff_last * (pff_change_percent / 100)
        tlt_change_cents = tlt_last * (tlt_change_percent / 100)
        
        print(f"PFF: {pff_last:.2f}, Change: {pff_change_percent:.2f}% = {pff_change_cents:.2f}¢")
        print(f"TLT: {tlt_last:.2f}, Change: {tlt_change_percent:.2f}% = {tlt_change_cents:.2f}¢")

        # Market data aboneliklerini başlat
        loading_window = tk.Toplevel(self)
        loading_window.title("Veri Yükleniyor")
        loading_window.geometry("400x150")
        loading_window.transient(self)
        loading_window.grab_set()
        
        # İlerleme çubuğu
        loading_label = ttk.Label(loading_window, text="Opt50 portföy verileri alınıyor...")
        loading_label.pack(pady=20)
        
        progress = ttk.Progressbar(loading_window, orient="horizontal", length=300, mode="determinate", maximum=len(opt50_symbols))
        progress.pack(pady=10)
        progress_text = ttk.Label(loading_window, text="0/" + str(len(opt50_symbols)))
        progress_text.pack(pady=5)
        
        for i, symbol in enumerate(opt50_symbols):
            try:
                contract = Stock(symbol, 'SMART', 'USD')
                contracts[symbol] = contract
                self.ib.reqMktData(contract, genericTickList="233,236", snapshot=False)  # 236 için daily change değerini ekledik
                
                # İlerleme çubuğunu güncelle
                progress["value"] = i + 1
                progress_text.config(text=f"{i+1}/{len(opt50_symbols)}: {symbol}")
                loading_window.update()
                
                # Yoğun API isteklerini önlemek için kısa bekleme
                if i % 5 == 0:
                    time.sleep(0.5)
                    
            except Exception as e:
                print(f"Market data hatası ({symbol}): {e}")
        
        # Verilerin gelmesi için bekleme
        time.sleep(5)  # 5 saniye bekle (veya daha fazla)
        loading_window.destroy()

        # Emir oluşturulacak hisseleri bul - Önce tüm uygun adayları topla
        candidate_stocks = []
        
        for symbol in opt50_symbols:
            try:
                # Model portföydeki Final_Shares değerini al
                model_shares = df.loc[df["PREF IBKR"] == symbol, "Final_Shares"].values[0] if "Final_Shares" in df.columns else 0
                
                # Mevcut pozisyondaki shares değerini al
                current_shares = position_dict.get(symbol, 0)
                
                # Güncel fiyat verilerini al
                ticker_data = None
                for ticker in self.ib.tickers():
                    if ticker.contract.symbol == symbol:
                        ticker_data = ticker
                        break
                
                # Veri yoksa veya eksikse atla
                if ticker_data is None or ticker_data.bid is None or ticker_data.ask is None:
                    continue
                
                # İlk koşul: Mevcut pozisyonumuz model portföydekinden AZ olmalı
                if current_shares < model_shares:
                    # Spread'i hesapla (cent olarak)
                    spread_cents = (ticker_data.ask - ticker_data.bid) * 100
                    
                    # Günlük değişim yüzdesini hesapla - bu kısım referans için kullanılabilir
                    daily_change = None
                    if hasattr(ticker_data, 'changePercent') and ticker_data.changePercent is not None:
                        daily_change = ticker_data.changePercent
                    elif ticker_data.close is not None and ticker_data.last is not None and ticker_data.close > 0:
                        daily_change = ((ticker_data.last / ticker_data.close) - 1) * 100
                    
                    # Veriler tam değilse atla
                    if daily_change is None:
                        continue
                    
                    # Önerilen fiyat: bid + spread'in %15'i (bu fiyat zaten fill fiyatımız)
                    suggested_price = ticker_data.bid + (spread_cents * 0.15 / 100)
                    
                    # Günlük değişimi cent olarak hesapla - artık last yerine potansiyel fill fiyatını kullanıyoruz
                    if ticker_data.close is not None and ticker_data.close > 0:
                        # Yeni: Potansiyel fill fiyatı üzerinden değişim
                        daily_change_cents = (suggested_price - ticker_data.close) * 100
                    else:
                        # Veriler eksikse son bilinen fiyat farklılığını kullan
                        price = ticker_data.last if ticker_data.last else ticker_data.bid
                        daily_change_cents = price * (daily_change / 100)
                    
                    # Sembol tipine göre benchmark değişimini hesapla
                    benchmark_change_cents = 0
                    benchmark_formula = ""
                    
                    try:
                        if symbol in tltr_symbols:
                            # TLTR formülü: PFF*0.7 + TLT*0.1
                            benchmark_change_cents = ((pff_change_cents * 0.7) + (tlt_change_cents * 0.1)) * 100
                            benchmark_formula = "PFF*0.7 + TLT*0.1"
                            symbol_type = "TLTR"
                        elif symbol in div_symbols:
                            # DIV Spread formülü: PFF*1.3 - TLT*0.1
                            benchmark_change_cents = ((pff_change_cents * 1.3) - (tlt_change_cents * 0.1)) * 100
                            benchmark_formula = "PFF*1.3 - TLT*0.1"
                            symbol_type = "DIV"
                        else:
                            # Varsayılan: Sadece PFF
                            benchmark_change_cents = pff_change_cents * 100
                            benchmark_formula = "PFF"
                        
                        # Print debug info to verify values
                        print(f"Debug - {symbol} benchmark calc: {benchmark_formula} = {benchmark_change_cents:.2f}¢")
                    except Exception as e:
                        print(f"Error calculating benchmark for {symbol}: {e}")
                        benchmark_change_cents = 0
                    
                    # Rölatif performansı hesapla (negatif değer = benchmark'ın gerisinde)
                    relative_performance_cents = daily_change_cents - benchmark_change_cents
                    
                    # Sadece benchmark'tan negatif ayrışan hisseleri dahil et
                    if relative_performance_cents >= 0:
                        print(f"Skipping {symbol} - positive relative performance: {relative_performance_cents:.2f}¢ vs {benchmark_formula}")
                        continue
                    
                    # Önerilen fiyat: bid + spread'in %15'i
                    suggested_price = ticker_data.bid + (spread_cents * 0.15 / 100)
                    
                    # Aday stoku kaydet
                    candidate_stocks.append({
                        "symbol": symbol,
                        "spread_cents": spread_cents,
                        "daily_change": daily_change,
                        "daily_change_cents": daily_change_cents,
                        "benchmark_change_cents": benchmark_change_cents,
                        "benchmark_formula": benchmark_formula,
                        "relative_to_benchmark_cents": relative_performance_cents,
                        "price": round(suggested_price, 2),
                        "model_shares": int(model_shares),
                        "current_shares": int(current_shares),
                        "ticker_data": ticker_data,
                        "symbol_type": "TLTR" if symbol in tltr_symbols else ("DIV" if symbol in div_symbols else "OTHER")
                    })
            except Exception as e:
                print(f"Hisse işleme hatası ({symbol}): {str(e)}")

        # Skor hesaplama ve sıralama
        scored_stocks = []
        if candidate_stocks:
            # Her stok için skor hesapla (sadece benchmark'tan negatif ayrışanları dahil et)
            for stock in candidate_stocks:
                # Spread (cent) skoru: Daha geniş spread daha iyi
                spread_cents = stock["spread_cents"]
                
                # Rölatif performans skoru: Negatif değerin mutlak değeri kadar (ne kadar negatifse o kadar iyi)
                relative_score = abs(stock["relative_to_benchmark_cents"])
                
                # Debug: Skor hesaplama detaylarını yazdır
                print(f"{stock['symbol']} ({stock['symbol_type']}): Spread {spread_cents:.2f}¢ → Score {spread_cents:.2f}, " +
                      f"Rel Perf {stock['relative_to_benchmark_cents']:.2f}¢ → Score {relative_score:.2f} " +
                      f"(vs {stock['benchmark_formula']})")
                
                # Toplam skor: İki faktörün toplamı (her ikisi de cent bazında)
                total_score = spread_cents + relative_score
                
                # Skor bilgilerini kaydet
                scored_stocks.append({
                    "symbol": stock["symbol"],
                    "symbol_type": stock["symbol_type"],
                    "score": total_score,
                    "daily_change": stock["daily_change"],
                    "daily_change_cents": stock["daily_change_cents"],
                    "benchmark_formula": stock["benchmark_formula"],
                    "benchmark_change_cents": stock["benchmark_change_cents"],
                    "relative_to_benchmark_cents": stock["relative_to_benchmark_cents"],
                    "spread_cents": stock["spread_cents"],
                    "relative_score": relative_score,
                    "spread_score": spread_cents,
                    "price": stock["price"],
                    "model_shares": stock["model_shares"],
                    "current_shares": stock["current_shares"],
                    "ticker_data": stock["ticker_data"]
                })
            
            # Skora göre sırala (yüksekten düşüğe)
            scored_stocks.sort(key=lambda x: x["score"], reverse=True)
            
            # 20 emir sınırını kaldırıyoruz ama en azından 20 emir hep gösterelim
            if not scored_stocks and candidate_stocks:
                # Eğer skor hesaplamada sorun varsa, en azından candidate_stocks'u göster
                scored_stocks = candidate_stocks[:20]
                print("Skor hesaplamada sorun oluştu, kandidat stokları doğrudan gösteriyorum")

            # Emirleri oluştur
            orders_to_place = []
            for stock in scored_stocks:
                ticker_data = stock["ticker_data"]
                spread_cents = stock["spread_cents"]
                relative_cents = stock["relative_to_benchmark_cents"]
                
                orders_to_place.append({
                    "symbol": stock["symbol"],
                    "symbol_type": stock["symbol_type"],
                    "order_type": "BUY (Hidden)",
                    "price": float(stock["price"]),  # Kesinlikle float olarak kullan
                    "quantity": 200,  # Her zaman 200 adet
                    "venue": "SMART",
                    "daily_change": f"{stock['daily_change']:.2f}%",
                    "daily_change_cents": f"{stock['daily_change_cents']:.2f}¢",
                    "benchmark_formula": stock["benchmark_formula"],
                    "benchmark_change": f"{stock['benchmark_change_cents']:.2f}¢",
                    "relative_to_benchmark": f"{relative_cents:.2f}¢",
                    "spread": f"{spread_cents:.2f}¢",
                    "score": f"{stock['score']:.2f}",
                    "model_shares": stock["model_shares"],
                    "current_shares": stock["current_shares"],
                    "note": f"{stock['symbol_type']}: Spread: {spread_cents:.2f}¢, vs {stock['benchmark_formula']}: {relative_cents:.2f}¢, Toplam Skor: {stock['score']:.2f}",
                    "selected": True  # Varsayılan olarak seçili
                })

            # Debug: Emirlerin oluşup oluşmadığını kontrol et
            print(f"Toplam {len(orders_to_place)} emir oluşturuldu")
            if len(orders_to_place) > 0:
                print(f"İlk emir örneği: {orders_to_place[0]['symbol']} fiyat: {orders_to_place[0]['price']}")

            # Emir önizleme penceresi
            if not orders_to_place:
                messagebox.showinfo("Bilgi", "Opt50 portföyünde uygun Hidden Bid için hisse bulunamadı!")
                # Abonelikleri temizle
                for symbol in opt50_symbols:
                    if symbol in contracts:
                        self.ib.cancelMktData(contracts[symbol])
                self.ib.cancelMktData(pff_contract)
                self.ib.cancelMktData(tlt_contract)
                return

            dashboard = tk.Toplevel(self)
            dashboard.title("Hidden Bid Placement - Opt50 Portföy")
            dashboard.geometry("1600x600")  # Genişletilmiş pencere
            
            main_frame = ttk.Frame(dashboard)
            main_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)
            
            # Sayfalama değişkenleri
            page_size = 20  # Sayfa başına emir sayısı
            current_page = 1
            total_pages = max(1, (len(orders_to_place) + page_size - 1) // page_size)
            
            columns = ("select", "symbol", "symbol_type", "order_type", "price", "quantity", "model_shares", "current_shares", 
                      "daily_change", "daily_change_cents", "benchmark_formula", "benchmark_change", "relative_to_benchmark", "spread", "score", "note")
            tree = ttk.Treeview(main_frame, columns=columns, show="headings")
            
            # Sütun başlıkları
            headings = {
                "select": "Seç",
                "symbol": "Sembol",
                "symbol_type": "Tip",
                "order_type": "Emir Tipi",
                "price": "Fiyat",
                "quantity": "Miktar",
                "model_shares": "Model Shares",
                "current_shares": "Mevcut Shares",
                "daily_change": "Daily Chg",
                "daily_change_cents": "Daily Chg ¢",
                "benchmark_formula": "Benchmark",
                "benchmark_change": "Bench Chg ¢",
                "relative_to_benchmark": "vs Bench ¢",
                "spread": "Spread",
                "score": "Skor",
                "note": "Not/Detay"
            }
            
            # Sütun genişlikleri
            widths = {
                "select": 50,  # Seçim kutusu için
                "symbol": 70,
                "symbol_type": 50,
                "order_type": 90,
                "price": 70,
                "quantity": 70,
                "model_shares": 100,
                "current_shares": 100,
                "daily_change": 80,
                "daily_change_cents": 80,
                "benchmark_formula": 90,
                "benchmark_change": 90,
                "relative_to_benchmark": 90,
                "spread": 70,
                "score": 70,
                "note": 300
            }
            
            for col in columns:
                tree.heading(col, text=headings[col])
                tree.column(col, width=widths.get(col, 100))
            
            # Renk tanımlamaları
            tree.tag_configure('tltr', background='#e6ffe6')  # TLTR için açık yeşil
            tree.tag_configure('div', background='#ffe6e6')   # DIV için açık kırmızı
            
            # Scrollbar ekle
            scrollbar = ttk.Scrollbar(main_frame, orient="vertical", command=tree.yview)
            tree.configure(yscrollcommand=scrollbar.set)
            
            tree.pack(side=tk.LEFT, expand=True, fill="both")
            scrollbar.pack(side=tk.RIGHT, fill="y")
            
            # Fonksiyon: Seçim durumunu değiştir
            def toggle_selection(item_id):
                item_values = tree.item(item_id, "values")
                symbol = item_values[1]  # Symbol kolonu 1. indeks
                
                # orders_to_place listesinde ilgili emri bul ve seçim durumunu değiştir
                for order in orders_to_place:
                    if order['symbol'] == symbol:
                        order['selected'] = not order['selected']
                        # Treeview'da güncelle
                        new_values = list(item_values)
                        new_values[0] = "✓" if order['selected'] else ""
                        tree.item(item_id, values=tuple(new_values))
                        break
            
            # Fonksiyon: Tüm emirleri seç/kaldır
            def toggle_all_selections():
                select_all = not any(order['selected'] for order in orders_to_place)
                
                # Tüm orders_to_place'i güncelle
                for order in orders_to_place:
                    order['selected'] = select_all
                
                # Mevcut sayfadaki Treeview öğelerini güncelle
                for item_id in tree.get_children():
                    item_values = list(tree.item(item_id, "values"))
                    item_values[0] = "✓" if select_all else ""
                    tree.item(item_id, values=tuple(item_values))
                    
                # Buton metnini güncelle
                select_all_btn.config(text="Tümünü Kaldır" if select_all else "Tümünü Seç")
            
            # Fonksiyon: Sayfa değiştir
            def change_page(page_num):
                nonlocal current_page
                if 1 <= page_num <= total_pages:
                    current_page = page_num
                    update_page()
                    page_label.config(text=f"Sayfa {current_page}/{total_pages}")
                    
                    # Sayfa butonlarını güncelle
                    prev_btn.config(state=tk.NORMAL if current_page > 1 else tk.DISABLED)
                    next_btn.config(state=tk.NORMAL if current_page < total_pages else tk.DISABLED)
            
            # Fonksiyon: Mevcut sayfayı güncelle
            def update_page():
                # Treeview'ı temizle
                for item in tree.get_children():
                    tree.delete(item)
                
                # Sayfa için indeksleri hesapla
                start_idx = (current_page - 1) * page_size
                end_idx = min(start_idx + page_size, len(orders_to_place))
                
                # Sayfadaki emirleri ekle
                for i in range(start_idx, end_idx):
                    order = orders_to_place[i]
                    # Sembol tipine göre tag belirle
                    tag = 'tltr' if order["symbol_type"] == "TLTR" else ('div' if order["symbol_type"] == "DIV" else '')
                    
                    try:
                        # Emir satırını ekle
                        tree.insert("", "end", values=(
                            "✓" if order["selected"] else "",  # Seçim durumu
                            order["symbol"],
                            order["symbol_type"],
                            order["order_type"],
                            f"{float(order['price']):.2f}",  # Fiyatı doğru formatta göster
                            order["quantity"],
                            order["model_shares"],
                            order["current_shares"],
                            order["daily_change"],
                            order["daily_change_cents"],
                            order["benchmark_formula"],
                            order["benchmark_change"],
                            order["relative_to_benchmark"],
                            order["spread"],
                            order["score"],
                            order["note"]
                        ), tags=(tag,))
                    except Exception as e:
                        print(f"Emir gösterilirken hata: {e} - Emir: {order['symbol']}")
            
            # Tıklama olayını yakala
            def on_tree_click(event):
                item_id = tree.identify_row(event.y)
                if item_id:
                    column = tree.identify_column(event.x)
                    if column == "#1":  # İlk kolon (seçim)
                        toggle_selection(item_id)
            
            # İlk sayfa için görüntüle
            update_page()
            
            # Treeview tıklama olayını bağla
            tree.bind("<ButtonRelease-1>", on_tree_click)
            
            # ETF bilgilerini göster
            info_frame = ttk.Frame(dashboard)
            info_frame.pack(fill=tk.X, padx=10, pady=(10, 5))
            
            ttk.Label(info_frame, text=f"PFF: ${pff_last:.2f} ({pff_change_percent:.2f}% = {pff_change_cents:.2f}¢) | TLT: ${tlt_last:.2f} ({tlt_change_percent:.2f}% = {tlt_change_cents:.2f}¢) | SMA: ${sma_value if sma_value is not None else 'N/A'}", 
                      font=("Arial", 10, "bold")).pack(side=tk.LEFT)
            
            # TLTR ve DIV sayılarını göster
            tltr_count = sum(1 for order in orders_to_place if order["symbol_type"] == "TLTR")
            div_count = sum(1 for order in orders_to_place if order["symbol_type"] == "DIV")
            other_count = sum(1 for order in orders_to_place if order["symbol_type"] not in ["TLTR", "DIV"])
            
            ttk.Label(info_frame, text=f"TLTR: {tltr_count} | DIV: {div_count} | Diğer: {other_count} | Toplam: {len(orders_to_place)}", 
                      font=("Arial", 10)).pack(side=tk.RIGHT, padx=10)
            
            # Sayfalama düğmeleri
            page_frame = ttk.Frame(dashboard)
            page_frame.pack(fill=tk.X, padx=10, pady=5)
            
            prev_btn = ttk.Button(page_frame, text="< Önceki Sayfa", command=lambda: change_page(current_page - 1))
            prev_btn.pack(side=tk.LEFT, padx=5)
            prev_btn.config(state=tk.DISABLED if current_page == 1 else tk.NORMAL)
            
            page_label = ttk.Label(page_frame, text=f"Sayfa {current_page}/{total_pages}")
            page_label.pack(side=tk.LEFT, padx=10)
            
            next_btn = ttk.Button(page_frame, text="Sonraki Sayfa >", command=lambda: change_page(current_page + 1))
            next_btn.pack(side=tk.LEFT, padx=5)
            next_btn.config(state=tk.DISABLED if current_page == total_pages else tk.NORMAL)
            
            # Tümünü Seç düğmesi
            select_all_btn = ttk.Button(page_frame, text="Tümünü Kaldır", command=toggle_all_selections)
            select_all_btn.pack(side=tk.RIGHT, padx=10)
            
            # Tümünü Kaldır düğmesi
            select_none_btn = ttk.Button(page_frame, text="Tümünü Kaldır", command=lambda: toggle_all_selections(False))
            select_none_btn.pack(side=tk.RIGHT, padx=10)
            
            # Alt düğme çerçevesi
            btn_frame = ttk.Frame(dashboard)
            btn_frame.pack(pady=20, fill=tk.X)  # Daha fazla alan için
            
            # Accent style tanımla
            s = ttk.Style()
            s.configure("Accent.TButton", foreground="white", background="green", font=("Arial", 12, "bold"))
            
            # Talimatları ekleyelim
            if len(orders_to_place) > 0:
                message_label = ttk.Label(
                    dashboard, 
                    text=f"Lütfen göndermek istediğiniz emirleri seçin ve 'ONAYLA VE EMİRLERİ GÖNDER' butonuna tıklayın", 
                    font=("Arial", 10, "bold"),
                    foreground="blue"
                )
                message_label.pack(pady=5)
            
            # Emirleri gönderme fonksiyonu
            def onayla():
                # Seçilen emirleri topla
                selected_orders = [order for order in orders_to_place if order.get("selected", False)]
                if not selected_orders:
                    messagebox.showinfo("Bilgi", "Lütfen göndermek için en az bir emir seçin!")
                    return
                
                try:
                    # Seçilen emirleri gönder
                    for order in selected_orders:
                        symbol = order["symbol"]
                        price = float(order["price"])
                        quantity = int(order["quantity"])
                        
                        # Sembol için kontrat bul
                        contract = contracts.get(symbol)
                        if not contract:
                            print(f"Kontrat bulunamadı: {symbol}")
                            continue
                        
                        # Emir oluştur ve gönder
                        limit_order = LimitOrder('BUY', quantity, round(price, 2))
                        limit_order.hidden = True
                        self.ib.placeOrder(contract, limit_order)
                        print(f"Emir gönderildi: {symbol} @ {price:.2f} x {quantity}")
                    
                    messagebox.showinfo("Başarılı", f"{len(selected_orders)} emir başarıyla gönderildi!")
                    
                except Exception as e:
                    messagebox.showerror("Hata", f"Emirler gönderilirken hata: {str(e)}")
                finally:
                    # Abonelikleri temizle
                    for symbol in opt50_symbols:
                        if symbol in contracts:
                            self.ib.cancelMktData(contracts[symbol])
                    self.ib.cancelMktData(pff_contract)
                    self.ib.cancelMktData(tlt_contract)
                    
                    # Pencereyi kapat
                    dashboard.destroy()
            
            # İptal fonksiyonu
            def iptal():
                # Abonelikleri temizle
                for symbol in opt50_symbols:
                    if symbol in contracts:
                        self.ib.cancelMktData(contracts[symbol])
                self.ib.cancelMktData(pff_contract)
                self.ib.cancelMktData(tlt_contract)
                
                # Pencereyi kapat
                dashboard.destroy()
            
            # Daha büyük ve daha görünür Onayla butonu
            confirm_btn = ttk.Button(
                btn_frame, 
                text="ONAYLA VE EMİRLERİ GÖNDER", 
                command=onayla, 
                style="Accent.TButton"
            )
            confirm_btn.pack(side=tk.LEFT, padx=20, pady=10, fill=tk.X, expand=True, ipadx=20, ipady=10)  # Genişletilmiş buton
            
            # İptal butonu
            cancel_btn = ttk.Button(
                btn_frame, 
                text="İPTAL", 
                command=iptal,
                style="TButton"
            )
            cancel_btn.pack(side=tk.RIGHT, padx=20, pady=10, ipadx=10, ipady=10)

    def show_div_portfolio(self):
        """
        optimized_35_extlt.csv dosyasından portföy verilerini görüntüler
        ve canlı fiyat verilerini gösterir
        """
        # Import gerekli modüller
        import os
        from tkinter import messagebox
        
        # CSV dosyasının yolunu belirle
        portfolio_file = "optimized_35_extlt.csv"
        
        # Dosya var mı kontrol et
        if not os.path.exists(portfolio_file):
            messagebox.showerror("Dosya Bulunamadı", f"{portfolio_file} dosyası bulunamadı.")
            return
          # Yeni bir pencere oluştur
        portfolio_window = tk.Toplevel(self)
        portfolio_window.title("DIV Portföy")
        portfolio_window.geometry("1400x700")  # Pencere boyutunu artırdım (1200 -> 1400)
        
        # Yükleniyor etiketi
        loading_label = ttk.Label(portfolio_window, text="Portföy verileri yükleniyor...")
        loading_label.pack(pady=20)
        
        # Sayfalama ve sıralama değişkenleri
        sort_column = None
        sort_reverse = False
        
        # Sayfalama değişkenleri
        port_items_per_page = 10  # Sayfa başına gösterilecek hisse sayısı
        port_current_page = 1     # Mevcut sayfa numarası
        port_total_pages = 1      # Toplam sayfa sayısı
        
        try:
            # CSV dosyasını oku
            df = pd.read_csv(portfolio_file)
            
            # Gerekli sütunları kontrol et
            required_columns = ["PREF IBKR", "CMON", "FINAL_THG", "AVG_ADV", "Normalized_THG", "Final_Shares"]
            missing_columns = [col for col in required_columns if col not in df.columns]
            if missing_columns:
                error_msg = f"CSV dosyasında aşağıdaki sütunlar eksik: {', '.join(missing_columns)}"
                loading_label.destroy()
                messagebox.showerror("Eksik Sütunlar", error_msg)
                return
            
            # Treeview oluştur
            def setup_treeview():
                # Yükleniyor etiketini kaldır
                loading_label.destroy()
                
                # Treeview için frame
                tree_frame = ttk.Frame(portfolio_window)
                tree_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)
                
                # Sütunlar - Final_shares eklendi
                columns = (
                    "ticker", "common", "thg", "avg_adv", "norm_thg", "final_shares",
                    "last", "bid", "ask", "spread", "volume"
                )
                
                # Treeview
                port_tree = ttk.Treeview(
                    tree_frame,
                    columns=columns,
                    show="headings",
                    selectmode="browse"
                )
            
            # Sütun başlıkları
                column_titles = {
                    "ticker": "PREF IBKR",
                    "common": "CMON",
                    "thg": "FINAL_THG",
                    "avg_adv": "AVG_ADV",
                    "norm_thg": "Normalized_THG",
                    "final_shares": "Final_shares",  # Yeni kolon
                    "last": "Last Price",
                    "bid": "Bid",
                    "ask": "Ask",
                    "spread": "Spread %",
                    "volume": "Volume"
                }
                
                # Sıralama fonksiyonu
                def sort_portfolio(column):
                    nonlocal sort_column, sort_reverse
                    
                    # Mevcut sıralama durumunu kontrol et
                    if sort_column == column:
                        sort_reverse = not sort_reverse
                    else:
                        sort_column = column
                        sort_reverse = False
                    
                    # Sütun başlıklarını güncelle
                    for col in port_tree["columns"]:
                        if col == column:
                            direction = " ▼" if sort_reverse else " ▲"
                            port_tree.heading(col, text=column_titles[col] + direction)
                        else:
                            port_tree.heading(col, text=column_titles[col])
                    
                    # Treeview'i güncelle
                    update_treeview(df, port_tree)
                    
                # Sütun başlıklarını ayarla
                for col in columns:
                    port_tree.heading(col, text=column_titles[col], command=lambda c=col: sort_portfolio(c))
            
            # Sütun genişlikleri
                port_tree.column("ticker", width=110, anchor=tk.W)
                port_tree.column("common", width=110, anchor=tk.W)
                port_tree.column("thg", width=90, anchor=tk.E)
                port_tree.column("avg_adv", width=100, anchor=tk.E)
                port_tree.column("norm_thg", width=110, anchor=tk.E)
                port_tree.column("final_shares", width=100, anchor=tk.E)  # Yeni kolon genişliği
                port_tree.column("last", width=90, anchor=tk.E)
                port_tree.column("bid", width=90, anchor=tk.E)
                port_tree.column("ask", width=90, anchor=tk.E)
                port_tree.column("spread", width=90, anchor=tk.E)
                port_tree.column("volume", width=90, anchor=tk.E)
            
            # Scrollbar
                tree_scroll = ttk.Scrollbar(tree_frame, orient="vertical", command=port_tree.yview)
                port_tree.configure(yscrollcommand=tree_scroll.set)
                
                # Yerleştirme
                tree_scroll.pack(side=tk.RIGHT, fill=tk.Y)
                port_tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
                
                # Tag'ler
                port_tree.tag_configure('updated', background='#e6ffe6')  # Yeşil
                port_tree.tag_configure('high_value', background='#e6ffe6')  # Yeşil arkaplan (yüksek normalized_thg)
                port_tree.tag_configure('low_value', background='#ffe6e6')    # Kırmızı arkaplan (düşük normalized_thg)
                
                # Treeview'i doldur
                update_treeview(df, port_tree)
                
                # Alt panel - kontrol ve bilgi
                bottom_frame = ttk.Frame(portfolio_window)
                bottom_frame.pack(fill=tk.X, pady=10, padx=10)
                
                # Toplam portföy büyüklüğü
                ttk.Label(bottom_frame, text=f"Toplam Sembol Sayısı: {len(df)}").pack(side=tk.LEFT, padx=10)
                
                # Ortalama Normalized_THG
                avg_norm_thg = df["Normalized_THG"].mean()
                ttk.Label(bottom_frame, text=f"Ort. Normalized_THG: {avg_norm_thg:.4f}").pack(side=tk.LEFT, padx=10)
                
                # Toplam Final_Shares
                total_shares = df["Final_Shares"].sum()
                ttk.Label(bottom_frame, text=f"Toplam Hisse: {total_shares:,.0f}").pack(side=tk.LEFT, padx=10)
                
                # Sayfalama kontrolleri
                page_nav_frame = ttk.Frame(bottom_frame)
                page_nav_frame.pack(side=tk.LEFT, padx=20)
                
                # Önceki sayfa butonu
                prev_page_btn = ttk.Button(
                    page_nav_frame, 
                    text="< Önceki Sayfa", 
                    command=lambda: navigate_page(-1)
                )
                prev_page_btn.pack(side=tk.LEFT)
                
                # Sayfa bilgisi
                port_page_info = ttk.Label(
                    page_nav_frame, 
                    text=f"Sayfa {port_current_page}/{port_total_pages} (Toplam: {len(df)})"
                )
                port_page_info.pack(side=tk.LEFT, padx=20)
                
                # Sonraki sayfa butonu
                next_page_btn = ttk.Button(
                    page_nav_frame, 
                    text="Sonraki Sayfa >", 
                    command=lambda: navigate_page(1)
                )
                next_page_btn.pack(side=tk.LEFT)
                
                # Sayfa navigasyon fonksiyonu
                def navigate_page(direction):
                    nonlocal port_current_page, port_total_pages
                    
                    # Yeni sayfa hesapla
                    new_page = port_current_page + direction
                    
                    # Sayfa sınırlarını kontrol et
                    if 1 <= new_page <= port_total_pages:
                        port_current_page = new_page
                        
                        # Sayfa bilgisini güncelle
                        port_page_info.config(text=f"Sayfa {port_current_page}/{port_total_pages} (Toplam: {len(df)})")
                        
                        # Treeview'i güncelle
                        update_treeview(df, port_tree)
                
                # Son güncelleme zamanı
                time_now = time.strftime("%H:%M:%S")
                time_label = ttk.Label(bottom_frame, text=f"Son güncelleme: {time_now}")
                time_label.pack(side=tk.RIGHT, padx=10)
                
                # Tüm ticker'lara abone ol ve canlı verileri göster
                self.after(100, lambda: subscribe_to_portfolio_tickers(df, port_tree, time_label))
                
                # Yenile butonu
                refresh_btn = ttk.Button(
                    bottom_frame, 
                    text="Yenile", 
                    command=lambda: refresh_data(df, port_tree, time_label)
                )
                refresh_btn.pack(side=tk.RIGHT, padx=10)
                
                # Pencere kapanma olayını izle
                portfolio_window.protocol("WM_DELETE_WINDOW", on_window_close)
                
                return port_tree
            
            # TreeView güncelleme fonksiyonu
            def update_treeview(data_df, tree):
                nonlocal port_items_per_page, port_current_page, port_total_pages
                
                # Treeview'i temizle
                for item in tree.get_children():
                    tree.delete(item)
                
                # Toplam hisse sayısı
                total_stocks = len(data_df)
                
                # Sıralama varsa uygula
                if sort_column:
                    # Sayısal sütunlar
                    numeric_columns = ["thg", "avg_adv", "norm_thg", "final_shares", 
                                      "last", "bid", "ask", "spread", "volume"]
                    
                    # Doğru sütun ismiyle eşleştir
                    column_mapping = {
                        "ticker": "PREF IBKR",
                        "common": "CMON",
                        "thg": "FINAL_THG",
                        "avg_adv": "AVG_ADV",
                        "norm_thg": "Normalized_THG",
                        "final_shares": "Final_Shares"
                    }
                    
                    # Sıralama sütununu belirle
                    sort_by = column_mapping.get(sort_column, sort_column)
                    
                    # Eğer sütun DataFrame'de varsa sırala
                    if sort_by in data_df.columns:
                        # Sayısal sütun mu kontrol et
                        if sort_column in numeric_columns:
                            # NaN değerleri en sona koy
                            data_df = data_df.sort_values(
                                by=sort_by, 
                                ascending=not sort_reverse,
                                na_position='last'
                            )
                        else:
                            # Metin sütunları için
                            data_df = data_df.sort_values(
                                by=sort_by,
                                ascending=not sort_reverse,
                                na_position='last'
                            )
                
                port_total_pages = max(1, math.ceil(total_stocks / port_items_per_page))
                
                # Geçerli sayfa numarasını kontrol et
                if port_current_page > port_total_pages:
                    port_current_page = port_total_pages
                
                # Görünür hisseleri belirle (sayfalama)
                start_idx = (port_current_page - 1) * port_items_per_page
                end_idx = min(start_idx + port_items_per_page, total_stocks)
                
                # Sadece geçerli sayfadaki hisseleri göster
                page_df = data_df.iloc[start_idx:end_idx]
                
                # Sıralanmış verileri TreeView'e ekle (sadece geçerli sayfa)
                for _, row in page_df.iterrows():
                    ticker = row["PREF IBKR"]
                    
                    # Sayısal değerleri formatla
                    thg = f"{row['FINAL_THG']:.4f}" if pd.notna(row["FINAL_THG"]) else ""
                    avg_adv = f"{row['AVG_ADV']:,.0f}" if pd.notna(row["AVG_ADV"]) else ""
                    norm_thg = f"{row['Normalized_THG']:.4f}" if pd.notna(row["Normalized_THG"]) else ""
                    final_shares = f"{row['Final_Shares']:,.0f}" if pd.notna(row["Final_Shares"]) else ""
                    
                    # Canlı veri alanları için varsayılan değerler
                    last = bid = ask = spread = volume = ""
                    
                    # Tag belirle (yüksek değerler için yeşil, düşük değerler için kırmızı)
                    tags = []
                    if pd.notna(row["Normalized_THG"]):
                        if row["Normalized_THG"] > 0.6:  # Yüksek değer
                            tags.append("high_value")
                        elif row["Normalized_THG"] < 0.4:  # Düşük değer
                            tags.append("low_value")
                    
                    # Hisseyi TreeView'e ekle
                    item_id = tree.insert(
                        "", "end",
                        values=(ticker, row["CMON"], thg, avg_adv, norm_thg, final_shares, 
                               last, bid, ask, spread, volume),
                        tags=tags
                    )
                
                return tree
            
            def refresh_data(data_df, tree, time_label):
                # Tüm hisseler için güncelleme iste
                subscribe_to_portfolio_tickers(data_df, tree, time_label)
                
                # Güncelleme zamanını yenile
                time_now = time.strftime("%H:%M:%S")
                time_label.config(text=f"Son güncelleme: {time_now}")
            
            def subscribe_to_portfolio_tickers(data_df, tree, time_label):
                # TreeView için şu anki sayfa verilerini al
                nonlocal port_current_page, port_items_per_page
                
                # İstenen indeksleri belirle
                total_stocks = len(data_df)
                start_idx = (port_current_page - 1) * port_items_per_page
                end_idx = min(start_idx + port_items_per_page, total_stocks)
                
                # Görünür hisseleri seç
                visible_df = data_df.iloc[start_idx:end_idx]
                visible_tickers = visible_df["PREF IBKR"].tolist()
                
                # Her ticker için 
                for ticker in visible_tickers:
                    # Hisseyi imha isteklerine ekle
                    contract = self.create_preferred_stock_contract(ticker)
                    
                    # İstekleri temizle (eski istekler kalmasın)
                    if ticker in self.market_data_requests:
                        req_id = self.market_data_requests[ticker]
                        try:
                            self.ib.cancelMktData(req_id)
                        except:
                            pass
                        del self.market_data_requests[ticker]
                    
                    # Yeni veri isteği oluştur (gerçek zamanlı veri için tickerId = 0)
                    req_id = self.get_req_id()
                    self.market_data_requests[ticker] = req_id
                    
                    # İsteği gönder
                    self.ib.reqMktData(req_id, contract, "", False, False, [])
                
                # Ticker güncelleme işleyicisini ayarla
                def on_ticker_update(tickers):
                    # Treeview boşsa işlem yapma
                    if not tree.winfo_exists():
                        return
                    
                    # Bekleyen güncellemeleri topla
                    updates = []
                    
                    for ticker_symbol, ticker_data in tickers.items():
                        # TreeView'de bu hisseyi bul
                        for item_id in tree.get_children():
                            item_values = tree.item(item_id, "values")
                            if item_values and item_values[0] == ticker_symbol:
                                # Mevcut değerleri al
                                values = list(item_values)
                                
                                # Son, Alış, Satış değerlerini güncelle
                                if "last" in ticker_data:
                                    values[6] = f"{ticker_data['last']:.2f}"
                                
                                if "bid" in ticker_data:
                                    values[7] = f"{ticker_data['bid']:.2f}"
                                
                                if "ask" in ticker_data:
                                    values[8] = f"{ticker_data['ask']:.2f}"
                                
                                # Spread hesapla
                                if "bid" in ticker_data and "ask" in ticker_data and ticker_data["bid"] > 0:
                                    spread = (ticker_data["ask"] - ticker_data["bid"]) / ticker_data["bid"] * 100
                                    values[9] = f"{spread:.2f}%"
                                
                                # Hacim
                                if "volume" in ticker_data:
                                    values[10] = f"{ticker_data['volume']:,}"
                                
                                # Güncellemeleri ekle
                                updates.append((item_id, values))
                                
                                # Bir kez bulduktan sonra ara
                        break
                    
                    # Treeview'i güncelle
                    if updates:
                        for item_id, values in updates:
                            tree.item(item_id, values=values)
                            
                            # Güncellenmiş etiketi ekle, sonra kaldır
                            tree.item(item_id, tags=tree.item(item_id, "tags") + ("updated",))
                            tree.after(1000, lambda id=item_id: tree.item(
                                id, tags=[tag for tag in tree.item(id, "tags") if tag != "updated"]
                            ))
                
                # Ticker güncellemelerini dinle
                self._portfolio_ticker_update_handler = on_ticker_update
                
                # Güncelleme zamanını göster
                time_now = time.strftime("%H:%M:%S")
                time_label.config(text=f"Son güncelleme: {time_now}")
                
                # Periyodik olarak veriyi güncelle
                def update_portfolio_data():
                    # Tüm satırları güncelle
                    if tree.winfo_exists():
                        # En son ticker verilerini topla
                        ticker_updates = {}
                        
                        for ticker in visible_tickers:
                            # Önbelleği kontrol et
                            cached_data = self.market_data_cache.get(ticker)
                            if cached_data:
                                ticker_updates[ticker] = cached_data
                        
                        # UI'ı güncelle
                        if ticker_updates:
                            on_ticker_update(ticker_updates)
                            
                        # Her 1 saniyede bir güncelle
                        tree.after(1000, update_portfolio_data)
                
                # Periyodik güncellemeyi başlat
                tree.after(100, update_portfolio_data)
            
            def on_window_close():
                # Ticker güncellemelerini temizle
                self._portfolio_ticker_update_handler = None
                
                # Abonelikleri iptal et
                for ticker, req_id in list(self.market_data_requests.items()):
                    try:
                        self.ib.cancelMktData(req_id)
                        del self.market_data_requests[ticker]
                    except Exception as e:
                        print(f"Abonelik iptal hatası ({ticker}): {e}")
                
                # Pencereyi kapat
                portfolio_window.destroy()
            
            # TreeView'i oluştur
            self.after(100, setup_treeview)
            
            # Pencere kapatma protokolünü ayarla
            portfolio_window.protocol("WM_DELETE_WINDOW", on_window_close)
            
        except Exception as e:
            import traceback
            traceback.print_exc()
            loading_label.destroy()
            messagebox.showerror("Hata", f"Portföy verileri yüklenirken bir hata oluştu: {e}")

    def calculate_benchmark_change(self, pff_daily_change_cents, tlt_daily_change_cents):
        # ETF değişimlerinin ağırlıklı ortalaması
        benchmark_change = (pff_daily_change_cents * 0.7) + (tlt_daily_change_cents * 0.1)
        # 100 ile çarparak, diğer yerlerdeki Daily Chg hesaplamaları ile aynı birimde olmasını sağla
        return benchmark_change * 100

    def place_div_hidden_bids(self):
        """
        Div Hidden Placement - ExtLT portföy hisselerine gizli emirler yerleştir
        """
        from tkinter import messagebox
        import time
        import os
        import pandas as pd
        from ib_insync import Stock, LimitOrder

        if not self.connected or not self.ib.isConnected():
            messagebox.showerror("Bağlantı Hatası", "Bu işlem için IBKR bağlantısı gereklidir!")
            return

        # SMA kontrolü
        sma_limit = 1000
        sma_value = None
        try:
            # SMA değerini IBKR'dan çek
            account_summaries = self.ib.accountSummary()
            for acc in account_summaries:
                if acc.tag == "SMA":
                    try:
                        sma_value = float(acc.value)
                    except:
                        pass
                    break
        except Exception as e:
            messagebox.showwarning("SMA Hatası", f"SMA değeri alınamadı: {e}")
            return

        sma_warning = False
        if sma_value is None:
            messagebox.showwarning("SMA Hatası", "SMA değeri alınamadı!")
            sma_warning = True
        elif sma_value < sma_limit:
            messagebox.showwarning("SMA Yetersiz", f"SMA bakiyesi çok düşük: {sma_value}")
            sma_warning = True

        # ExtLT portföy dosyasını kontrol et ve yükle
        portfolio_file = "optimized_35_extlt.csv"
        if not os.path.exists(portfolio_file):
            messagebox.showerror("Dosya Bulunamadı", f"{portfolio_file} dosyası bulunamadı!")
            return
        
        # ExtLT portföyünü yükle
        try:
            df = pd.read_csv(portfolio_file)
            opt50_symbols = df["PREF IBKR"].dropna().tolist()
            if not opt50_symbols:
                messagebox.showinfo("Bilgi", "ExtLT portföyünde hisse bulunamadı!")
                return
        except Exception as e:
            messagebox.showerror("Portföy Yükleme Hatası", f"ExtLT portföyü yüklenirken hata: {str(e)}")
            return

        # Mevcut pozisyonları al
        try:
            current_positions = self.ib.positions()
            position_dict = {}
            for pos in current_positions:
                position_dict[pos.contract.symbol] = pos.position
        except Exception as e:
            messagebox.showerror("Pozisyon Hatası", f"Mevcut pozisyonlar alınamadı: {str(e)}")
            return

        market_data = {}
        contracts = {}

        # TLTR ve DIV spread sembollerini yükle
        try:
            # TLTR sekmesi için
            df_tltr = pd.read_csv("sma_results.csv")
            df_tltr = normalize_ticker_column(df_tltr)
            tltr_symbols = set(df_tltr["Ticker"].dropna().unique().tolist())
            
            # DIV Spread sekmesi için
            df_div = pd.read_csv("extlt_results.csv")
            df_div = normalize_ticker_column(df_div)
            div_symbols = set(df_div["Ticker"].dropna().unique().tolist())
            
            print(f"TLTR sembolleri: {len(tltr_symbols)}, DIV sembolleri: {len(div_symbols)}")
        except Exception as e:
            print(f"Sembol listelerini yükleme hatası: {e}")
            tltr_symbols = set()
            div_symbols = set()

        # PFF ve TLT verilerini çek
        pff_contract = Stock('PFF', 'SMART', 'USD')
        tlt_contract = Stock('TLT', 'SMART', 'USD')
        self.ib.reqMktData(pff_contract, genericTickList="233,236", snapshot=False)
        self.ib.reqMktData(tlt_contract, genericTickList="233,236", snapshot=False)
        
        # PFF ve TLT verilerinin gelmesini bekle
        pff_last = None
        pff_change_percent = None
        tlt_last = None
        tlt_change_percent = None
        
        for _ in range(20):  # Max 10 saniye bekle
            self.ib.sleep(0.5)
            
            # PFF verilerini kontrol et
            for ticker in self.ib.tickers():
                if ticker.contract.symbol == 'PFF':
                    pff_last = ticker.last
                    # changePercent değeri gelmediyse hesapla
                    if hasattr(ticker, 'changePercent') and ticker.changePercent is not None:
                        pff_change_percent = ticker.changePercent
                    elif ticker.close is not None and ticker.last is not None and ticker.close > 0:
                        pff_change_percent = ((ticker.last / ticker.close) - 1) * 100
                
                elif ticker.contract.symbol == 'TLT':
                    tlt_last = ticker.last
                    # changePercent değeri gelmediyse hesapla
                    if hasattr(ticker, 'changePercent') and ticker.changePercent is not None:
                        tlt_change_percent = ticker.changePercent
                    elif ticker.close is not None and ticker.last is not None and ticker.close > 0:
                        tlt_change_percent = ((ticker.last / ticker.close) - 1) * 100
            
            # Tüm gerekli veriler geldiyse döngüden çık
            if (pff_last is not None and pff_change_percent is not None and 
                tlt_last is not None and tlt_change_percent is not None):
                break
        
        if pff_last is None or pff_change_percent is None:
            messagebox.showwarning("PFF Verisi Alınamadı", "PFF fiyat veya değişim verisi alınamadı!")
            self.ib.cancelMktData(pff_contract)
            self.ib.cancelMktData(tlt_contract)
            return
            
        if tlt_last is None or tlt_change_percent is None:
            messagebox.showwarning("TLT Verisi Alınamadı", "TLT fiyat veya değişim verisi alınamadı!")
            self.ib.cancelMktData(pff_contract)
            self.ib.cancelMktData(tlt_contract)
            return

        # PFF ve TLT değişimlerini cent bazında hesapla
        pff_change_cents = pff_last * (pff_change_percent / 100)
        tlt_change_cents = tlt_last * (tlt_change_percent / 100)
        
        print(f"PFF: {pff_last:.2f}, Change: {pff_change_percent:.2f}% = {pff_change_cents:.2f}¢")
        print(f"TLT: {tlt_last:.2f}, Change: {tlt_change_percent:.2f}% = {tlt_change_cents:.2f}¢")

        # Market data aboneliklerini başlat
        loading_window = tk.Toplevel(self)
        loading_window.title("Veri Yükleniyor")
        loading_window.geometry("400x150")
        loading_window.transient(self)
        loading_window.grab_set()
        
        # İlerleme çubuğu
        loading_label = ttk.Label(loading_window, text="ExtLT portföy verileri alınıyor...")
        loading_label.pack(pady=20)
        
        progress = ttk.Progressbar(loading_window, orient="horizontal", length=300, mode="determinate", maximum=len(opt50_symbols))
        progress.pack(pady=10)
        progress_text = ttk.Label(loading_window, text="0/" + str(len(opt50_symbols)))
        progress_text.pack(pady=5)
        
        for i, symbol in enumerate(opt50_symbols):
            try:
                contract = Stock(symbol, 'SMART', 'USD')
                contracts[symbol] = contract
                self.ib.reqMktData(contract, genericTickList="233,236", snapshot=False)  # 236 için daily change değerini ekledik
                
                # İlerleme çubuğunu güncelle
                progress["value"] = i + 1
                progress_text.config(text=f"{i+1}/{len(opt50_symbols)}: {symbol}")
                loading_window.update()
                
                # Yoğun API isteklerini önlemek için kısa bekleme
                if i % 5 == 0:
                    time.sleep(0.5)
                    
            except Exception as e:
                print(f"Market data hatası ({symbol}): {e}")
        
        # Verilerin gelmesi için bekleme
        time.sleep(5)  # 5 saniye bekle (veya daha fazla)
        loading_window.destroy()

        # Emir oluşturulacak hisseleri bul - Önce tüm uygun adayları topla
        candidate_stocks = []
        
        for symbol in opt50_symbols:
            try:
                # Model portföydeki Final_Shares değerini al
                model_shares = df.loc[df["PREF IBKR"] == symbol, "Final_Shares"].values[0] if "Final_Shares" in df.columns else 0
                
                # Mevcut pozisyondaki shares değerini al
                current_shares = position_dict.get(symbol, 0)
                
                # Güncel fiyat verilerini al
                ticker_data = None
                for ticker in self.ib.tickers():
                    if ticker.contract.symbol == symbol:
                        ticker_data = ticker
                        break
                
                if ticker_data is None or ticker_data.last is None or ticker_data.bid is None or ticker_data.ask is None:
                    print(f"Yetersiz veri: {symbol}")
                    continue
                
                # Spread hesapla (cent olarak)
                spread_cents = (ticker_data.ask - ticker_data.bid) * 100 if ticker_data.ask > ticker_data.bid else 0
                
                # Minimum 0 cent spread olsun (test için değiştirildi, normalde 20 cent)
                if spread_cents < 0:
                    print(f"Düşük spread: {symbol} = {spread_cents:.2f}¢")
                    continue
                
                # Günlük değişimi hesapla
                daily_change = None
                if hasattr(ticker_data, 'changePercent') and ticker_data.changePercent is not None:
                    daily_change = ticker_data.changePercent
                elif ticker_data.close is not None and ticker_data.last is not None and ticker_data.close > 0:
                    daily_change = ((ticker_data.last / ticker_data.close) - 1) * 100
                
                if daily_change is None:
                    print(f"Değişim verisi yok: {symbol}")
                    continue
                
                # Önerilen fiyat: bid + spread'in %15'i (bu fiyat zaten fill fiyatımız)
                suggested_price = ticker_data.bid + (spread_cents * 0.15 / 100)
                
                # Günlük değişimi cent olarak hesapla - artık last yerine potansiyel fill fiyatını kullanıyoruz
                if ticker_data.close is not None and ticker_data.close > 0:
                    # Yeni: Potansiyel fill fiyatı üzerinden değişim
                    daily_change_cents = (suggested_price - ticker_data.close) * 100
                else:
                    # Veriler eksikse son bilinen fiyat farklılığını kullan
                    price = ticker_data.last if ticker_data.last else ticker_data.bid
                    daily_change_cents = price * (daily_change / 100)
                
                # Sembol tipine göre benchmark değişimini hesapla
                benchmark_change_cents = 0
                benchmark_formula = ""
                
                try:
                    if symbol in tltr_symbols:
                        # TLTR formülü: PFF*0.7 + TLT*0.1
                        benchmark_change_cents = ((pff_change_cents * 0.7) + (tlt_change_cents * 0.1)) * 100
                        benchmark_formula = "PFF*0.7 + TLT*0.1"
                    elif symbol in div_symbols:
                        # DIV Spread formülü: PFF*1.3 - TLT*0.1
                        benchmark_change_cents = ((pff_change_cents * 1.3) - (tlt_change_cents * 0.1)) * 100
                        benchmark_formula = "PFF*1.3 - TLT*0.1"
                    else:
                        # Varsayılan: Sadece PFF
                        benchmark_change_cents = pff_change_cents * 100
                        benchmark_formula = "PFF"
                    
                    # Print debug info to verify values
                    print(f"Debug - {symbol} benchmark calc: {benchmark_formula} = {benchmark_change_cents:.2f}¢")
                except Exception as e:
                    print(f"Error calculating benchmark for {symbol}: {e}")
                    benchmark_change_cents = 0
                
                # Rölatif performansı hesapla (negatif değer = benchmark'ın gerisinde)
                relative_performance_cents = daily_change_cents - benchmark_change_cents
                
                # Sadece benchmark'tan negatif ayrışan hisseleri dahil et
                if relative_performance_cents >= 0:
                    print(f"Skipping {symbol} - positive relative performance: {relative_performance_cents:.2f}¢ vs {benchmark_formula}")
                    continue
                
                # Önerilen fiyat: bid + spread'in %15'i
                suggested_price = ticker_data.bid + (spread_cents * 0.15 / 100)
                
                # Aday stoku kaydet
                candidate_stocks.append({
                    "symbol": symbol,
                    "spread_cents": spread_cents,
                    "daily_change": daily_change,
                    "daily_change_cents": daily_change_cents,
                    "benchmark_change_cents": benchmark_change_cents,
                    "benchmark_formula": benchmark_formula,
                    "relative_to_benchmark_cents": relative_performance_cents,
                    "price": round(suggested_price, 2),
                    "model_shares": int(model_shares),
                    "current_shares": int(current_shares),
                    "ticker_data": ticker_data,
                    "symbol_type": "TLTR" if symbol in tltr_symbols else ("DIV" if symbol in div_symbols else "OTHER")
                })
            except Exception as e:
                print(f"Hisse işleme hatası ({symbol}): {str(e)}")

        # Skor hesaplama ve sıralama
        scored_stocks = []
        if candidate_stocks:
            # Her stok için skor hesapla (sadece benchmark'tan negatif ayrışanları dahil et)
            for stock in candidate_stocks:
                # Spread (cent) skoru: Daha geniş spread daha iyi
                spread_cents = stock["spread_cents"]
                
                # Rölatif performans skoru: Negatif değerin mutlak değeri kadar (ne kadar negatifse o kadar iyi)
                relative_score = abs(stock["relative_to_benchmark_cents"])
                
                # Debug: Skor hesaplama detaylarını yazdır
                print(f"{stock['symbol']} ({stock['symbol_type']}): Spread {spread_cents:.2f}¢ → Score {spread_cents:.2f}, " +
                      f"Rel Perf {stock['relative_to_benchmark_cents']:.2f}¢ → Score {relative_score:.2f} " +
                      f"(vs {stock['benchmark_formula']})")
                
                # Toplam skor: İki faktörün toplamı (her ikisi de cent bazında)
                total_score = spread_cents + relative_score
                
                # Skor bilgilerini kaydet
                scored_stocks.append({
                    "symbol": stock["symbol"],
                    "symbol_type": stock["symbol_type"],
                    "score": total_score,
                    "daily_change": stock["daily_change"],
                    "daily_change_cents": stock["daily_change_cents"],
                    "benchmark_formula": stock["benchmark_formula"],
                    "benchmark_change_cents": stock["benchmark_change_cents"],
                    "relative_to_benchmark_cents": stock["relative_to_benchmark_cents"],
                    "spread_cents": stock["spread_cents"],
                    "relative_score": relative_score,
                    "spread_score": spread_cents,
                    "price": stock["price"],
                    "model_shares": stock["model_shares"],
                    "current_shares": stock["current_shares"],
                    "ticker_data": stock["ticker_data"]
                })
            
            # Skora göre sırala (yüksekten düşüğe)
            scored_stocks.sort(key=lambda x: x["score"], reverse=True)
            
            # 20 emir sınırını kaldırıyoruz ama en azından 20 emir hep gösterelim
            if not scored_stocks and candidate_stocks:
                # Eğer skor hesaplamada sorun varsa, en azından candidate_stocks'u göster
                scored_stocks = candidate_stocks[:20]
                print("Skor hesaplamada sorun oluştu, kandidat stokları doğrudan gösteriyorum")

            # Emirleri oluştur
            orders_to_place = []
            for stock in scored_stocks:
                ticker_data = stock["ticker_data"]
                spread_cents = stock["spread_cents"]
                relative_cents = stock["relative_to_benchmark_cents"]
                
                orders_to_place.append({
                    "symbol": stock["symbol"],
                    "symbol_type": stock["symbol_type"],
                    "order_type": "BUY (Hidden)",
                    "price": float(stock["price"]),  # Kesinlikle float olarak kullan
                    "quantity": 200,  # Her zaman 200 adet
                    "venue": "SMART",
                    "daily_change": f"{stock['daily_change']:.2f}%",
                    "daily_change_cents": f"{stock['daily_change_cents']:.2f}¢",
                    "benchmark_formula": stock["benchmark_formula"],
                    "benchmark_change": f"{stock['benchmark_change_cents']:.2f}¢",
                    "relative_to_benchmark": f"{relative_cents:.2f}¢",
                    "spread": f"{spread_cents:.2f}¢",
                    "score": f"{stock['score']:.2f}",
                    "model_shares": stock["model_shares"],
                    "current_shares": stock["current_shares"],
                    "note": f"{stock['symbol_type']}: Spread: {spread_cents:.2f}¢, vs {stock['benchmark_formula']}: {relative_cents:.2f}¢, Toplam Skor: {stock['score']:.2f}",
                    "selected": True  # Varsayılan olarak seçili
                })

            # Debug: Emirlerin oluşup oluşmadığını kontrol et
            print(f"Toplam {len(orders_to_place)} emir oluşturuldu")
            if len(orders_to_place) > 0:
                print(f"İlk emir örneği: {orders_to_place[0]['symbol']} fiyat: {orders_to_place[0]['price']}")

            # Emir önizleme penceresi
            if not orders_to_place:
                messagebox.showinfo("Bilgi", "ExtLT portföyünde uygun Hidden Bid için hisse bulunamadı!")
                # Abonelikleri temizle
                for symbol in opt50_symbols:
                    if symbol in contracts:
                        self.ib.cancelMktData(contracts[symbol])
                self.ib.cancelMktData(pff_contract)
                self.ib.cancelMktData(tlt_contract)
                return

            dashboard = tk.Toplevel(self)
            dashboard.title("Div Hidden Placement - ExtLT Portföy")
            dashboard.geometry("1600x600")  # Genişletilmiş pencere
            
            main_frame = ttk.Frame(dashboard)
            main_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)
            
            # Sayfalama değişkenleri
            page_size = 20  # Sayfa başına emir sayısı
            current_page = 1
            total_pages = max(1, (len(orders_to_place) + page_size - 1) // page_size)
            
            columns = ("select", "symbol", "symbol_type", "order_type", "price", "quantity", "model_shares", "current_shares", 
                      "daily_change", "daily_change_cents", "benchmark_formula", "benchmark_change", "relative_to_benchmark", "spread", "score", "note")
            tree = ttk.Treeview(main_frame, columns=columns, show="headings")
            
            # Sütun başlıkları
            headings = {
                "select": "Seç",
                "symbol": "Sembol",
                "symbol_type": "Tip",
                "order_type": "Emir Tipi",
                "price": "Fiyat",
                "quantity": "Miktar",
                "model_shares": "Model Shares",
                "current_shares": "Mevcut Shares",
                "daily_change": "Daily Chg",
                "daily_change_cents": "Daily Chg ¢",
                "benchmark_formula": "Benchmark",
                "benchmark_change": "Bench Chg ¢",
                "relative_to_benchmark": "vs Bench ¢",
                "spread": "Spread",
                "score": "Skor",
                "note": "Not/Detay"
            }
            
            # Sütun genişlikleri
            widths = {
                "select": 50,  # Seçim kutusu için
                "symbol": 70,
                "symbol_type": 50,
                "order_type": 90,
                "price": 70,
                "quantity": 70,
                "model_shares": 100,
                "current_shares": 100,
                "daily_change": 80,
                "daily_change_cents": 80,
                "benchmark_formula": 90,
                "benchmark_change": 90,
                "relative_to_benchmark": 90,
                "spread": 70,
                "score": 70,
                "note": 300
            }
            
            for col in columns:
                tree.heading(col, text=headings[col])
                tree.column(col, width=widths.get(col, 100))
            
            # Renk tanımlamaları
            tree.tag_configure('tltr', background='#e6ffe6')  # TLTR için açık yeşil
            tree.tag_configure('div', background='#ffe6e6')   # DIV için açık kırmızı
            
            # Scrollbar ekle
            scrollbar = ttk.Scrollbar(main_frame, orient="vertical", command=tree.yview)
            tree.configure(yscrollcommand=scrollbar.set)
            
            tree.pack(side=tk.LEFT, expand=True, fill="both")
            scrollbar.pack(side=tk.RIGHT, fill="y")
            
            # Fonksiyon: Seçim durumunu değiştir
            def toggle_selection(item_id):
                item_values = tree.item(item_id, "values")
                symbol = item_values[1]  # Symbol kolonu 1. indeks
                
                # orders_to_place listesinde ilgili emri bul ve seçim durumunu değiştir
                for order in orders_to_place:
                    if order['symbol'] == symbol:
                        order['selected'] = not order['selected']
                        # Treeview'da güncelle
                        new_values = list(item_values)
                        new_values[0] = "✓" if order['selected'] else ""
                        tree.item(item_id, values=tuple(new_values))
                        break
                
            # Fonksiyon: Tüm emirleri seç/kaldır
            def toggle_all_selections():
                select_all = not any(order['selected'] for order in orders_to_place)
                
                # Tüm orders_to_place'i güncelle
                for order in orders_to_place:
                    order['selected'] = select_all
                
                # Mevcut sayfadaki Treeview öğelerini güncelle
                for item_id in tree.get_children():
                    item_values = list(tree.item(item_id, "values"))
                    item_values[0] = "✓" if select_all else ""
                    tree.item(item_id, values=tuple(item_values))
                    
                # Buton metnini güncelle
                select_all_btn.config(text="Tümünü Kaldır" if select_all else "Tümünü Seç")
            
            # Fonksiyon: Sayfa değiştir
            def change_page(page_num):
                nonlocal current_page
                if 1 <= page_num <= total_pages:
                    current_page = page_num
                update_page()
                page_label.config(text=f"Sayfa {current_page}/{total_pages}")
                
                # Sayfa butonlarını güncelle
                prev_btn.config(state=tk.NORMAL if current_page > 1 else tk.DISABLED)
                next_btn.config(state=tk.NORMAL if current_page < total_pages else tk.DISABLED)
            
            # Fonksiyon: Mevcut sayfayı güncelle
            def update_page():
                # Treeview'ı temizle
                for item in tree.get_children():
                    tree.delete(item)
                
                # Sayfa için indeksleri hesapla
                start_idx = (current_page - 1) * page_size
                end_idx = min(start_idx + page_size, len(orders_to_place))
                
                # Sayfadaki emirleri ekle
                for i in range(start_idx, end_idx):
                    order = orders_to_place[i]
                    # Sembol tipine göre tag belirle
                    tag = 'tltr' if order["symbol_type"] == "TLTR" else ('div' if order["symbol_type"] == "DIV" else '')
                    
                    try:
                        # Emir satırını ekle
                        tree.insert("", "end", values=(
                            "✓" if order["selected"] else "",  # Seçim durumu
                            order["symbol"],
                            order["symbol_type"],
                            order["order_type"],
                            f"{float(order['price']):.2f}",  # Fiyatı doğru formatta göster
                            order["quantity"],
                            order["model_shares"],
                            order["current_shares"],
                            order["daily_change"],
                            order["daily_change_cents"],
                            order["benchmark_formula"],
                            order["benchmark_change"],
                            order["relative_to_benchmark"],
                            order["spread"],
                            order["score"],
                            order["note"]
                        ), tags=(tag,))
                    except Exception as e:
                        print(f"Emir gösterilirken hata: {e} - Emir: {order['symbol']}")
            
            # Tıklama olayını yakala
            def on_tree_click(event):
                item_id = tree.identify_row(event.y)
                if item_id:
                    column = tree.identify_column(event.x)
                    if column == "#1":  # İlk kolon (seçim)
                        toggle_selection(item_id)
            
            # İlk sayfa için görüntüle
            update_page()
            
            # Treeview tıklama olayını bağla
            tree.bind("<ButtonRelease-1>", on_tree_click)
            
            # ETF bilgilerini göster
            info_frame = ttk.Frame(dashboard)
            info_frame.pack(fill=tk.X, padx=10, pady=(10, 5))
            
            ttk.Label(info_frame, text=f"PFF: ${pff_last:.2f} ({pff_change_percent:.2f}% = {pff_change_cents:.2f}¢) | TLT: ${tlt_last:.2f} ({tlt_change_percent:.2f}% = {tlt_change_cents:.2f}¢) | SMA: ${sma_value if sma_value is not None else 'N/A'}", 
                      font=("Arial", 10, "bold")).pack(side=tk.LEFT)
            
            # TLTR ve DIV sayılarını göster
            tltr_count = sum(1 for order in orders_to_place if order["symbol_type"] == "TLTR")
            div_count = sum(1 for order in orders_to_place if order["symbol_type"] == "DIV")
            other_count = sum(1 for order in orders_to_place if order["symbol_type"] not in ["TLTR", "DIV"])
            
            ttk.Label(info_frame, text=f"TLTR: {tltr_count} | DIV: {div_count} | Diğer: {other_count} | Toplam: {len(orders_to_place)}", 
                      font=("Arial", 10)).pack(side=tk.RIGHT, padx=10)
            
            # Sayfalama düğmeleri
            page_frame = ttk.Frame(dashboard)
            page_frame.pack(fill=tk.X, padx=10, pady=5)
            
            prev_btn = ttk.Button(page_frame, text="< Önceki Sayfa", command=lambda: change_page(current_page - 1))
            prev_btn.pack(side=tk.LEFT, padx=5)
            prev_btn.config(state=tk.DISABLED if current_page == 1 else tk.NORMAL)
            
            page_label = ttk.Label(page_frame, text=f"Sayfa {current_page}/{total_pages}")
            page_label.pack(side=tk.LEFT, padx=10)
            
            next_btn = ttk.Button(page_frame, text="Sonraki Sayfa >", command=lambda: change_page(current_page + 1))
            next_btn.pack(side=tk.LEFT, padx=5)
            next_btn.config(state=tk.DISABLED if current_page == total_pages else tk.NORMAL)
            
            # Tümünü Seç düğmesi
            select_all_btn = ttk.Button(page_frame, text="Tümünü Seç", command=lambda: toggle_all_selections(True))
            select_all_btn.pack(side=tk.RIGHT, padx=10)
            
            # Tümünü Kaldır düğmesi
            select_none_btn = ttk.Button(page_frame, text="Tümünü Kaldır", command=lambda: toggle_all_selections(False))
            select_none_btn.pack(side=tk.RIGHT, padx=10)
            
            # Alt düğme çerçevesi
            btn_frame = ttk.Frame(dashboard)
            btn_frame.pack(pady=20, fill=tk.X)  # Daha fazla alan için
            
            # Accent style tanımla
            s = ttk.Style()
            s.configure("Accent.TButton", foreground="white", background="green", font=("Arial", 12, "bold"))
            
            # Talimatları ekleyelim
            if len(orders_to_place) > 0:
                message_label = ttk.Label(
                    dashboard, 
                    text=f"Lütfen göndermek istediğiniz emirleri seçin ve 'ONAYLA VE EMİRLERİ GÖNDER' butonuna tıklayın", 
                    font=("Arial", 10, "bold"),
                    foreground="blue"
                )
                message_label.pack(pady=5)
            
            # Emirleri gönderme fonksiyonu
            def onayla():
                # Seçilen emirleri topla
                selected_orders = [order for order in orders_to_place if order.get("selected", False)]
                if not selected_orders:
                    messagebox.showinfo("Bilgi", "Lütfen göndermek için en az bir emir seçin!")
                    return
                
                try:
                    # Seçilen emirleri gönder
                    for order in selected_orders:
                        symbol = order["symbol"]
                        price = float(order["price"])
                        quantity = int(order["quantity"])
                        
                        # Sembol için kontrat bul
                        contract = contracts.get(symbol)
                        if not contract:
                            print(f"Kontrat bulunamadı: {symbol}")
                            continue
                        
                        # Emir oluştur ve gönder
                        limit_order = LimitOrder('BUY', quantity, round(price, 2))
                        limit_order.hidden = True
                        self.ib.placeOrder(contract, limit_order)
                        print(f"Emir gönderildi: {symbol} @ {price:.2f} x {quantity}")
                    
                    messagebox.showinfo("Başarılı", f"{len(selected_orders)} emir başarıyla gönderildi!")
                    
                except Exception as e:
                    messagebox.showerror("Hata", f"Emirler gönderilirken hata: {str(e)}")
                finally:
                    # Abonelikleri temizle
                    for symbol in opt50_symbols:
                        if symbol in contracts:
                            self.ib.cancelMktData(contracts[symbol])
                    self.ib.cancelMktData(pff_contract)
                    self.ib.cancelMktData(tlt_contract)
                    
                    # Pencereyi kapat
                    dashboard.destroy()
            
            # İptal fonksiyonu
            def iptal():
                # Abonelikleri temizle
                for symbol in opt50_symbols:
                    if symbol in contracts:
                        self.ib.cancelMktData(contracts[symbol])
                self.ib.cancelMktData(pff_contract)
                self.ib.cancelMktData(tlt_contract)
                
                # Pencereyi kapat
                dashboard.destroy()
            
            # Daha büyük ve daha görünür Onayla butonu
            confirm_btn = ttk.Button(
                btn_frame, 
                text="ONAYLA VE EMİRLERİ GÖNDER", 
                command=onayla, 
                style="Accent.TButton"
            )
            confirm_btn.pack(side=tk.LEFT, padx=20, pady=10, fill=tk.X, expand=True, ipadx=20, ipady=10)  # Genişletilmiş buton
            
            # İptal butonu
            cancel_btn = ttk.Button(
                btn_frame, 
                text="İPTAL", 
                command=iptal,
                style="TButton"
            )
            cancel_btn.pack(side=tk.RIGHT, padx=20, pady=10, ipadx=10, ipady=10)

class MarketDataCache:
    def __init__(self):
        self.cache = {}
        self.last_update = {}
        self.cache_timeout = 5.0  # 5 seconds cache timeout
        self.active_subscriptions = set()  # Track active subscriptions
        self.max_subscriptions = 40  # IBKR limit is ~50 for most accounts
        self.subscription_queue = []  # Queue for managing subscription priority

    def update(self, symbol, data):
        # Create a copy of the ticker data to store in cache
        cache_data = {}
        for attr in ['last', 'bid', 'ask', 'close', 'volume', 'changePercent']:
            if hasattr(data, attr):
                cache_data[attr] = getattr(data, attr)
        
        self.cache[symbol] = cache_data
        self.last_update[symbol] = time.time()

    def get(self, symbol):
        if symbol in self.cache:
            # Check if data is still fresh
            if time.time() - self.last_update.get(symbol, 0) < self.cache_timeout:
                return self.cache[symbol]
        return None
    
    def add_subscription(self, symbol, contract, ib):
        """Add a new subscription, managing the max subscription limit"""
        # If we're already at max subscriptions, unsubscribe from the oldest one
        if symbol in self.active_subscriptions:
            # Already subscribed, move to the end of queue to stay active longer
            self.prioritize_symbol(symbol)
            return True
            
                    # Enforce the max subscription limit
        while len(self.active_subscriptions) >= self.max_subscriptions:
            if not self.subscription_queue:
                print(f"Uyarı: Abonelik kuyruğu boş ama {len(self.active_subscriptions)} aktif abonelik var")
                # Temizleme yapılacak sembol yok, en eskilerden bazılarını kaldır
                oldest_symbols = list(self.active_subscriptions)[:5]  # En eski 5 aboneliği temizle
                for old_symbol in oldest_symbols:
                    print(f"Abonelik limiti aşıldı, {old_symbol} aboneliği kaldırılıyor")
                    self.remove_subscription(old_symbol, ib)
                break
                
            # Remove oldest subscription
            old_symbol = self.subscription_queue.pop(0)
            if old_symbol in self.active_subscriptions:
                print(f"Yeni abonelik için yer açılıyor: {old_symbol} -> {symbol}")
                self.remove_subscription(old_symbol, ib)
        
        # Add new subscription
        try:
            ib.reqMktData(contract, genericTickList="233,236", snapshot=False)
            self.active_subscriptions.add(symbol)
            self.subscription_queue.append(symbol)
            print(f"Yeni abonelik eklendi: {symbol} (Toplam: {len(self.active_subscriptions)})")
            return True
        except Exception as e:
            print(f"Subscription error for {symbol}: {e}")
            return False
    
    def remove_subscription(self, symbol, ib):
        """Remove a subscription"""
        if symbol in self.active_subscriptions:
            try:
                # Find all contracts for this symbol (sometimes dupes can occur)
                canceled = False
                for ticker in ib.tickers():
                    ticker_symbol = None
                    if hasattr(ticker, 'contract'):
                        if hasattr(ticker.contract, 'symbol') and ticker.contract.symbol == symbol:
                            ticker_symbol = ticker.contract.symbol
                        elif hasattr(ticker.contract, 'localSymbol') and ticker.contract.localSymbol == symbol:
                            ticker_symbol = ticker.contract.localSymbol
                            
                        if ticker_symbol == symbol:
                            ib.cancelMktData(ticker.contract)
                            canceled = True
                            print(f"Abonelik iptal edildi: {symbol}")
                
                # Aktif listeden çıkar
                self.active_subscriptions.remove(symbol)
                
                # Kuyruktan da çıkar (eğer varsa)
                if symbol in self.subscription_queue:
                    self.subscription_queue.remove(symbol)
                    
                # Aboneliği iptal edemedikse hata mesajı yazdır
                if not canceled:
                    print(f"Uyarı: {symbol} aboneliği ib.tickers() içinde bulunamadı")
                    
                return True
            except Exception as e:
                print(f"Error unsubscribing from {symbol}: {e}")
                # Hata olsa bile listeden çıkarmaya çalış
                if symbol in self.active_subscriptions:
                    self.active_subscriptions.remove(symbol)
                if symbol in self.subscription_queue:
                    self.subscription_queue.remove(symbol)
        return False
    
    def clear_all_subscriptions(self, ib):
        """Clear all active subscriptions"""
        print(f"Tüm abonelikler temizleniyor ({len(self.active_subscriptions)} abonelik)")
        
        # Önce tüm aktif abonelikleri iptal et
        for symbol in list(self.active_subscriptions):
            self.remove_subscription(symbol, ib)
            
        # İlave bir güvenlik olarak, tüm ticker'lar için aboneliği iptal et
        count = 0
        for ticker in ib.tickers():
            if hasattr(ticker, 'contract'):
                try:
                    ib.cancelMktData(ticker.contract)
                    count += 1
                except Exception as e:
                    print(f"Abonelik iptali hatası: {e}")
        
        if count > 0:
            print(f"Ek {count} abone temizlendi")
            
        # Listeleri temizle
        self.active_subscriptions.clear()
        self.subscription_queue.clear()
        print("Tüm abonelikler iptal edildi")
        
    def prioritize_symbol(self, symbol):
        """Move symbol to the end of the queue (highest priority)"""
        if symbol in self.subscription_queue:
            self.subscription_queue.remove(symbol)
        self.subscription_queue.append(symbol)

def normalize_ticker_column(df):
    for col in df.columns:
        if col.strip().upper() in ["PREF IBKR", "SYMBOL", "SEMBOL", "TICKER"]:
            df = df.rename(columns={col: "Ticker"})
            break
    return df

def main():
    """Ana program başlangıcı"""
    app = PreferredStockMonitor()
    
    # Başlangıçta CSV yükle
    app.df = app.load_stocks_from_csv()
    
    # TreeView'ı doldur
    app.populate_treeview()
    
    # Kapatma olayını ayarla
    app.protocol("WM_DELETE_WINDOW", lambda: (
        try_disconnect_and_destroy(app)
    ))
    
    # Uygulamayı başlat
    app.mainloop()

# Güvenli kapatma fonksiyonu
def try_disconnect_and_destroy(app):
    try:
        app.disconnect_from_ibkr()
    except Exception as e:
        print(f"Bağlantı kapatılırken hata: {e}")
    
    try:
        app.destroy()
    except Exception as e:
        print(f"Pencere kapatılırken hata: {e}")
        # Hala kapatılamadıysa, zorla sonlandır
        import os
        os._exit(0)

if __name__ == "__main__":
    main()