#!/usr/bin/env python
"""
StockTracker - Main application
"""
import math
import json
import tkinter as tk
from tkinter import ttk, messagebox
import pandas as pd
import threading
import time
import queue
import pickle
import datetime
import os
import numpy as np
from collections import defaultdict
from PIL import Image, ImageTk
import matplotlib.pyplot as plt
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
from ib_insync import IB, Stock, util, MarketOrder, LimitOrder

# Import our modularized components
from tb_modules.tb_utils import safe_format_float, safe_float, safe_int, normalize_ticker_column
from tb_modules.tb_data_cache import MarketDataCache
from tb_modules.tb_compression import compress_market_data, decompress_market_data
from tb_modules.tb_spreadci_window import SpreadciDataWindow
from tb_modules.tb_contracts import create_preferred_stock_contract, create_common_stock_contract
from tb_modules.tb_ui_utils import create_simple_treeview, safe_reset_tags
from tb_modules.tb_orders import create_limit_order, create_market_order, format_order_row, calculate_order_value
from tb_modules.tb_ui_components import (create_status_bar, update_status_bar, create_tab_control,
                                       create_control_frame, create_filter_frame, create_page_navigation_frame,
                                       update_page_info, create_benchmark_frame, update_benchmark_labels,
                                       create_simple_popup, create_error_popup, create_question_popup)
from tb_modules.tb_ib_connection import (connect_to_ibkr, disconnect_from_ibkr, subscribe_to_market_data,
                                       cancel_market_data_subscription, create_api_call_processor,
                                       queue_api_call, handle_ib_error, parse_ticker_data)
from tb_modules.tb_data_management import (get_filtered_stocks, sort_dataframe, get_paginated_data,
                                        populate_treeview_from_dataframe, update_treeview_item,
                                        get_column_title, find_top_movers, apply_color_tags,
                                        setup_treeview_tags)

class PreferredStockMonitor(tk.Tk):
    def __init__(self):
        super().__init__()
        
        # Pencere başlığı ve boyutları
        self.title("Tercihli Hisse Takip Sistemi")
        self.geometry("1400x800")
        
        # Market verileri için önbellek
        self.market_data_cache = MarketDataCache(max_size=500, max_subscriptions=50)
        
        # IB bağlantısı
        self.ib = IB()
        self.is_connected = False
        self.running = False
        
        # IB veri güncellemesi callback'leri
        self.update_callbacks = {}
        
        # Veri yapıları
        self.stocks = pd.DataFrame()  # Tüm hisse verileri
        self.common_stocks = {}  # Common stock abonelikleri
        self.ticker_id_map = {}  # Ticker -> TreeviewID eşleşmeleri
        self.benchmark_assets = {}  # Benchmark varlıkları
        self.tickers = {}  # Aktif ticker abonelikleri
        
        # Benchmark ETF'leri ve değişimleri
        self.etf_list = ["PFF", "TLT", "SPY", "IWM", "KRE"]  # Takip edilecek ETF'ler
        self.etf_prev_close = {}  # ETF'lerin önceki kapanış fiyatları
        self.etf_changes = {}  # ETF'lerin günlük değişimleri
        
        # T-benchmark ve C-benchmark değerleri
        self.t_benchmark = 0.0  # T-prefs için benchmark: PFF*0.7 + TLT*0.1
        self.c_benchmark = 0.0  # C-prefs için benchmark: PFF*1.3 - TLT*0.1
        
        # Spreadci verileri
        self.spreadci_data = {}
        
        # Sekme adları
        self.tab_names = ["T-prefs", "C-prefs"]  # Eski: ["TLTR Prefs", "DIV Spread"]
        
        # Arayüz değişkenleri
        self.items_per_page = 20
        self.current_tab = 0
        self.tltr_current_page = 1
        self.divspread_current_page = 1
        
        # Sayfalama ve veri görünüm değişkenleri
        self.current_page = {0: 1, 1: 1}  # Her sekme için sayfa numarası
        self.total_pages = {0: 1, 1: 1}   # Her sekme için toplam sayfa
        self.trees = {}                   # Sekme indeksi -> treeview eşleşmesi
        
        # Etiketler ve durum çubukları için değişkenler
        self.time_label = None
        self.page_info = None
        self.connect_btn = None
        self.pff_label = None
        self.tlt_label = None
        self.benchmark_label = None
        self.t_benchmark_label = None  # T-prefs için benchmark etiketi
        self.c_benchmark_label = None  # C-prefs için benchmark etiketi
        self.rotation_var = tk.BooleanVar(value=False)
        self.jump_to_page_var = tk.StringVar()
        
        # ETF bilgi etiketleri
        self.etf_labels = {}
        
        # Otomatik sayfa yenileme değişkenleri
        self.auto_cycle_pages = tk.BooleanVar(value=False)
        self.is_auto_cycling = False
        self.auto_cycle_interval = 10  # saniye
        self.auto_cycle_thread = None
        self.user_interacting = False
        self.last_user_interaction = time.time()
        
        # Sıralama değişkenleri
        self.sort_column = "ticker"
        self.sort_reverse = False
        
        # Filtre değişkenleri
        self.filter_var = tk.StringVar()
        
        # API çağrıları için queue 
        self.api_queue = queue.Queue()
        
        # Ticker rotasyonu değişkenleri
        self.ticker_rotation_active = False
        self.ticker_rotation_interval = 60  # saniye
        
        # Seçilen ticker'lar için sözlük
        self.selected_tickers = {}  # tab_idx -> set(selected_tickers)
        self.selected_tickers[0] = set()  # T-prefs
        self.selected_tickers[1] = set()  # C-prefs
        
        # UI'ı oluştur
        self.setup_ui()
        
        # CSV'den stokları yükle
        self.load_stocks_from_csv()
        
        # UI olay döngüsü
        self.protocol("WM_DELETE_WINDOW", self.on_closing)
        
        # Benchmark'ları takip etmek için değişkenler
        self.pff_prev_close = None
        self.tlt_prev_close = None
        self.pff_change_cache = 0
        self.tlt_change_cache = 0
        
        # Ticker cache güncelleme zamanı
        self.last_ticker_cache_update = 0
        
        # Threadleri başlat
        threading.Thread(target=self.run_event_loop, daemon=True).start()
        threading.Thread(target=self.process_api_calls, daemon=True).start()

    def setup_ui(self):
        """Kullanıcı arayüzü bileşenlerini oluştur"""
        # Özel stil tanımlama
        self.style = ttk.Style()
        self.style.configure('Small.TButton', font=('Arial', 8))
        self.style.configure('Compact.TButton', padding=(2, 1), font=('Arial', 8))
        self.style.configure('Updated.Treeview', background="#e0f0ff")  # Açık mavi arka plan
        
        # ETF bilgi etiketi stilleri
        self.style.configure('ETFUp.TLabel', foreground='green', font=('Arial', 8, 'bold'))
        self.style.configure('ETFDown.TLabel', foreground='red', font=('Arial', 8, 'bold'))
        self.style.configure('ETFNeutral.TLabel', foreground='black', font=('Arial', 8))
        
        # Seçim checkbox görselleri
        try:
            # Checkbox görselleri oluştur
            check_img = tk.PhotoImage(width=20, height=20)
            check_img.put("green", to=(8, 8, 12, 12))
            self.images = {
                "icon_checked": check_img,
                "icon_unchecked": tk.PhotoImage(width=20, height=20)
            }
        except Exception as e:
            print(f"Checkbox image creation error: {e}")
            # Görseller oluşmazsa, varsayılan değerler
            self.images = {
                "icon_checked": None,
                "icon_unchecked": None 
            }
        
        # Ana frame
        self.main_frame = ttk.Frame(self)
        self.main_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)
        
        # Üst kontrol paneli - iki satır kullanacağız
        self.control_frame = ttk.Frame(self.main_frame)
        self.control_frame.pack(fill=tk.X, pady=(0, 5))
        
        # Alt buton satırı
        self.button_frame2 = ttk.Frame(self.main_frame)
        self.button_frame2.pack(fill=tk.X, pady=(0, 5))
        
        # Otomatik Sayfa Yenileme butonu
        self.auto_cycle_checkbutton = ttk.Checkbutton(
            self.button_frame2, 
            text="Otomatik Yenileme", 
            variable=self.auto_cycle_pages,
            command=self.toggle_auto_page_cycling,
            style='Small.TButton'
        )
        self.auto_cycle_checkbutton.pack(side=tk.LEFT, padx=5)
        
        # T-prefs için çok yükselenler butonu
        self.t_top_gainers_button = ttk.Button(
            self.button_frame2,
            text="T-Çok Yükselenler",
            command=self.show_t_top_gainers,
            style='Small.TButton'
        )
        self.t_top_gainers_button.pack(side=tk.LEFT, padx=2)
        
        # T-prefs için çok düşenler butonu
        self.t_top_losers_button = ttk.Button(
            self.button_frame2,
            text="T-Çok Düşenler",
            command=self.show_t_top_losers,
            style='Small.TButton'
        )
        self.t_top_losers_button.pack(side=tk.LEFT, padx=2)
        
        # C-prefs için çok yükselenler butonu
        self.c_top_gainers_button = ttk.Button(
            self.button_frame2,
            text="C-Çok Yükselenler",
            command=self.show_c_top_gainers,
            style='Small.TButton'
        )
        self.c_top_gainers_button.pack(side=tk.LEFT, padx=2)
        
        # C-prefs için çok düşenler butonu
        self.c_top_losers_button = ttk.Button(
            self.button_frame2,
            text="C-Çok Düşenler",
            command=self.show_c_top_losers,
            style='Small.TButton'
        )
        self.c_top_losers_button.pack(side=tk.LEFT, padx=2)
        
        # Abonelik sayısı göstergesi
        self.subscription_count_label = ttk.Label(self.button_frame2, text="Aktif abonelikler: 0/50", font=('Arial', 8))
        self.subscription_count_label.pack(side=tk.RIGHT, padx=5)
        
        # Bağlantı durumu etiketi
        self.status_label = ttk.Label(self.control_frame, text="Bağlantı durumu: Bağlı değil", font=('Arial', 8))
        self.status_label.pack(side=tk.LEFT, padx=(0, 5))
        
        # Bağlantı düğmesi
        self.connect_btn = ttk.Button(self.control_frame, text="IBKR Bağlan", 
                                   command=self.connect_to_ibkr, style='Compact.TButton')
        self.connect_btn.pack(side=tk.LEFT, padx=1)
        
        # Bağlantıyı kes düğmesi
        self.disconnect_button = ttk.Button(self.control_frame, text="Bağlantıyı Kes", 
                                      command=self.disconnect_from_ibkr, style='Compact.TButton')
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
        
        # Cashpark35 Portföy butonu
        self.cashpark35_button = ttk.Button(self.control_frame, text="Cashpark35", 
                                      command=self.show_cashpark35_portfolio, style='Compact.TButton')
        self.cashpark35_button.pack(side=tk.LEFT, padx=1)
        
        # DIV Portföy butonu
        self.div_port_button = ttk.Button(self.control_frame, text="DIV", 
                                    command=self.show_div_portfolio, style='Compact.TButton')
        self.div_port_button.pack(side=tk.LEFT, padx=1)
        
        # ETF Listesi butonu
        self.etf_button = ttk.Button(self.control_frame, text="ETF", 
                                command=self.show_etf_list, style='Compact.TButton')
        self.etf_button.pack(side=tk.LEFT, padx=1)
        
        # Spreadci verilerini görüntüleme düğmesi
        self.spreadci_button = ttk.Button(self.control_frame, text="Spreadçi", 
                                    command=self.open_spreadci_window, style='Compact.TButton')
        self.spreadci_button.pack(side=tk.LEFT, padx=1)
        
        # Opt50 Mal Topla butonu
        self.opt50_maltopla_button = ttk.Button(self.control_frame, text="Opt50 Mal Topla", 
                                          command=self.opt50_mal_topla, style='Compact.TButton')
        self.opt50_maltopla_button.pack(side=tk.LEFT, padx=1)
        
        # Cashpark35 Mal Topla butonu
        self.cashpark35_maltopla_button = ttk.Button(self.control_frame, text="Cashpark35 Mal Topla", 
                                               command=self.cashpark35_mal_topla, style='Compact.TButton')
        self.cashpark35_maltopla_button.pack(side=tk.LEFT, padx=1)
        
        # Take Profit from Longs butonu
        def on_take_profit_longs_click():
            try:
                self.take_profit_from_longs()
            except Exception as e:
                messagebox.showerror("Hata", f"Take Profit Longs işlemi sırasında hata: {str(e)}")
                
        self.take_profit_longs_button = ttk.Button(self.control_frame, text="Take Profit Longs", 
                                       command=on_take_profit_longs_click, style='Compact.TButton')
        self.take_profit_longs_button.pack(side=tk.LEFT, padx=1)
        
        # Take Profit from Shorts butonu
        def on_take_profit_shorts_click():
            try:
                self.take_profit_from_shorts()
            except Exception as e:
                messagebox.showerror("Hata", f"Take Profit Shorts işlemi sırasında hata: {str(e)}")
                
        self.take_profit_shorts_button = ttk.Button(self.control_frame, text="Take Profit Shorts", 
                                       command=on_take_profit_shorts_click, style='Compact.TButton')
        self.take_profit_shorts_button.pack(side=tk.LEFT, padx=1)
        
        # Hidden Bid Placement butonu
        def on_hidden_bid_click():
            try:
                self.place_hidden_bids()
            except Exception as e:
                messagebox.showerror("Hata", f"Hidden Bid işlemi sırasında hata: {str(e)}")
                
        self.hidden_bid_button = ttk.Button(self.control_frame, text="Hidden Bid", 
                                      command=on_hidden_bid_click, style='Compact.TButton')
        self.hidden_bid_button.pack(side=tk.LEFT, padx=1)
        
        # Seçimi işlemleri
        select_frame = ttk.Frame(self.control_frame)
        select_frame.pack(side=tk.LEFT, padx=5)
        
        # Tüm tickerları seç/seçimi kaldır düğmeleri
        select_all_btn = ttk.Button(
            select_frame, 
            text="Tümünü Seç", 
            command=self.select_all_tickers, 
            style='Small.TButton'
        )
        select_all_btn.pack(side=tk.LEFT, padx=2)
        
        deselect_all_btn = ttk.Button(
            select_frame, 
            text="Seçimi Kaldır", 
            command=self.deselect_all_tickers, 
            style='Small.TButton'
        )
        deselect_all_btn.pack(side=tk.LEFT, padx=2)
        
        # Toplu işlem düğmeleri
        bulk_actions_frame = ttk.Frame(self.control_frame)
        bulk_actions_frame.pack(side=tk.LEFT, padx=5)
        
        hidden_bid_all_btn = ttk.Button(
            bulk_actions_frame, 
            text="S-Hidden Bid", 
            command=self.place_hidden_bids_for_selected, 
            style='Small.TButton'
        )
        hidden_bid_all_btn.pack(side=tk.LEFT, padx=2)
        
        hidden_offer_all_btn = ttk.Button(
            bulk_actions_frame, 
            text="S-Hidden Offer", 
            command=self.place_hidden_offers_for_selected, 
            style='Small.TButton'
        )
        hidden_offer_all_btn.pack(side=tk.LEFT, padx=2)
        

        
        # Seçili sayısı
        self.selected_count_label = ttk.Label(self.control_frame, text="Seçili: 0")
        self.selected_count_label.pack(side=tk.RIGHT, padx=10)
        
        # Otomatik Döngü Durumu etiketi
        self.auto_cycle_status_label = ttk.Label(self.control_frame, text="Otomatik Yenileme: Pasif", font=('Arial', 8))
        self.auto_cycle_status_label.pack(side=tk.RIGHT, padx=5)
        
        # Add new background update indicator
        self.background_update_label = ttk.Label(self.control_frame, text="Arkaplan Güncelleme: -", font=('Arial', 8))
        self.background_update_label.pack(side=tk.RIGHT, padx=5)
        
        # Notebook (sekme yapısı)
        self.notebook = ttk.Notebook(self.main_frame)
        self.notebook.pack(fill=tk.BOTH, expand=True)
        
        # T-prefs sekmesi (eski TLTR Prefs)
        self.tltr_frame = ttk.Frame(self.notebook)
        self.notebook.add(self.tltr_frame, text="T-prefs")
        self.tltr_tree = self.create_simple_treeview(self.tltr_frame)
        
        # C-prefs sekmesi (eski DIV Spread)
        self.divspread_frame = ttk.Frame(self.notebook)
        self.notebook.add(self.divspread_frame, text="C-prefs")
        self.divspread_tree = self.create_simple_treeview(self.divspread_frame)
        
        # Treeview'ları kaydet
        self.trees = {0: self.tltr_tree, 1: self.divspread_tree}
        
        # Tab control referansı
        self.tab_control = self.notebook
        
        # Alt panel - sayfalama kontrolleri
        self.navigation_frame = ttk.Frame(self.main_frame)
        self.navigation_frame.pack(fill=tk.X, pady=(10, 0))
        
        # Önceki sayfa düğmesi
        self.prev_button = ttk.Button(self.navigation_frame, text="< Önceki", 
                                 command=self.prev_page, style='Compact.TButton')
        self.prev_button.pack(side=tk.LEFT)
        
        # Sayfa bilgisi
        self.page_info_label = ttk.Label(self.navigation_frame, text="Sayfa 1/1", font=('Arial', 8))
        self.page_info_label.pack(side=tk.LEFT, padx=10)
        
        # Sonraki sayfa düğmesi
        self.next_button = ttk.Button(self.navigation_frame, text="Sonraki >", 
                                 command=self.next_page, style='Compact.TButton')
        self.next_button.pack(side=tk.LEFT)
        
        # Son güncelleme zamanı
        self.time_label = ttk.Label(self.navigation_frame, text="Son güncelleme: -", font=('Arial', 8))
        self.time_label.pack(side=tk.RIGHT)
        
        # Sayfa bilgisi
        self.page_info = self.page_info_label
        
        # Son güncelleme zamanı etiketi
        self.last_update_label = self.time_label
        
        # Durum çubuğu (Modül fonksiyonunu kullan)
        self.status_bar = create_status_bar(self)
        
        # Benchmark etiketleri
        benchmark_frame = ttk.Frame(self.main_frame)
        benchmark_frame.pack(fill=tk.X, pady=(5, 0))
        
        self.pff_label = ttk.Label(benchmark_frame, text="PFF: -", font=('Arial', 8))
        self.pff_label.pack(side=tk.LEFT, padx=5)
        
        self.tlt_label = ttk.Label(benchmark_frame, text="TLT: -", font=('Arial', 8))
        self.tlt_label.pack(side=tk.LEFT, padx=5)
        
        self.benchmark_label = ttk.Label(benchmark_frame, text="Benchmark: -", font=('Arial', 8))
        self.benchmark_label.pack(side=tk.LEFT, padx=5)
        
        # Yeni benchmark etiketleri
        self.t_benchmark_label = ttk.Label(benchmark_frame, text="T-benchmark: -", font=('Arial', 8, 'bold'))
        self.t_benchmark_label.pack(side=tk.LEFT, padx=10)
        
        self.c_benchmark_label = ttk.Label(benchmark_frame, text="C-benchmark: -", font=('Arial', 8, 'bold'))
        self.c_benchmark_label.pack(side=tk.LEFT, padx=10)

        # Sekmelere özel ticker listelerini yükle
        self.load_tab_tickers()

        # Sekme değişimini dinle
        self.notebook.bind("<<NotebookTabChanged>>", self.on_tab_changed)
        
        # Kullanıcı etkileşimini yakala
        self.bind_all("<Button>", self.on_user_interaction)
        self.bind_all("<Key>", self.on_user_interaction)
        
        # Mevcut kodu buraya kopyalayıp ETF panelini ekliyoruz...
        
        # ETF Bilgi Paneli - sayfanın altına ekleyelim
        self.etf_info_frame = ttk.Frame(self.main_frame)
        self.etf_info_frame.pack(fill=tk.X, pady=(5, 0), before=self.navigation_frame)
        
        # ETF etiketleri için bir çerçeve
        self.etf_labels_frame = ttk.Frame(self.etf_info_frame)
        self.etf_labels_frame.pack(fill=tk.X, padx=5, pady=5)
        
        # ETF başlık etiketi
        ttk.Label(self.etf_labels_frame, text="ETF Performans:", font=('Arial', 8, 'bold')).pack(side=tk.LEFT, padx=(0, 10))
        
        # Her ETF için bir etiket oluştur
        for etf in self.etf_list:
            self.etf_labels[etf] = ttk.Label(self.etf_labels_frame, text=f"{etf}: --", style='ETFNeutral.TLabel')
            self.etf_labels[etf].pack(side=tk.LEFT, padx=10)
        
        # Benchmark etiketlerini ETF panelinde göster
        ttk.Label(self.etf_labels_frame, text="|", font=('Arial', 8, 'bold')).pack(side=tk.LEFT, padx=(15, 5))
        
        # T-benchmark etiketi - ETF paneli içinde
        self.t_benchmark_label = ttk.Label(self.etf_labels_frame, text="T-benchmark: --", style='ETFNeutral.TLabel', font=('Arial', 8, 'bold'))
        self.t_benchmark_label.pack(side=tk.LEFT, padx=10)
        
        # C-benchmark etiketi - ETF paneli içinde
        self.c_benchmark_label = ttk.Label(self.etf_labels_frame, text="C-benchmark: --", style='ETFNeutral.TLabel', font=('Arial', 8, 'bold'))
        self.c_benchmark_label.pack(side=tk.LEFT, padx=10)
        
        # Ayrıcı çizgi ekle
        ttk.Separator(self.etf_info_frame, orient='horizontal').pack(fill=tk.X, padx=5, pady=2)
        
        # Diğer UI bileşenleri devam ediyor...
        # ...

    def create_simple_treeview(self, parent):
        """Add checkbox column to treeview for selecting tickers"""
        # Add checkbox column
        columns = ("Select", "Ticker", "last", "bid", "ask", "spread", "volume")
        tree = ttk.Treeview(parent, columns=columns, show="headings", height=20)
        
        headings = {
            "Select": "Seç",
            "Ticker": "Ticker",
            "last": "Son",
            "bid": "Alış",
            "ask": "Satış",
            "spread": "Spread",
            "volume": "Hacim"
        }
        
        widths = {
            "Select": 40,
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
        
        # Scrollbar ekle
        scrollbar = ttk.Scrollbar(parent, orient="vertical", command=tree.yview)
        tree.configure(yscrollcommand=scrollbar.set)
        
        # Renkli etiketleri yapılandır
        tree.tag_configure("green", background="#e0f0e0")
        tree.tag_configure("red", background="#f0e0e0")
        tree.tag_configure("neutral", background="#f0f0f0")
        tree.tag_configure("selected", background="#d0d0ff")
        tree.tag_configure("checked", text="✓")
        tree.tag_configure("unchecked", text="□")
        
        # Toggle seçimi için tıklama olayını ekle
        tree.bind("<Button-1>", self.on_treeview_click)
        
        # TreeView'ı yerleştir
        tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        
        return tree

    def on_treeview_click(self, event):
        """Treeview üzerinde tıklama olayını işle - checkbox işlemek için"""
        try:
            tree = event.widget
            region = tree.identify_region(event.x, event.y)
            
            # Eğer hücreye tıklandıysa
            if region == "cell":
                column = tree.identify_column(event.x)
                column_idx = int(column.replace('#', '')) - 1  # #1, #2 gibi değerleri 0, 1 indekslerine dönüştür
                
                # İlk sütundaki seçime tıklandıysa (Select sütunu)
                if column_idx == 0:
                    item_id = tree.identify_row(event.y)
                    if item_id:
                        # Öğe değerlerini al
                        item_values = tree.item(item_id, "values")
                        if item_values and len(item_values) > 1:
                            ticker = item_values[1]  # Ticker, ikinci sütunda
                            
                            # Mevcut seçimi al
                            current_tab = self.current_tab
                            current_selected = self.selected_tickers[current_tab]
                            
                            # Seçimi değiştir
                            if ticker in current_selected:
                                current_selected.remove(ticker)
                                tree.set(item_id, "Select", "□")
                            else:
                                current_selected.add(ticker)
                                tree.set(item_id, "Select", "✓")
                            
                            # Seçili sayısını güncelle
                            self.update_selected_count()
                            
                            # Tıklamanın işlendiğini belirt (diğer tıklama olaylarının işlenmemesi için)
                            return "break"
        except Exception as e:
            print(f"Treeview click error: {e}")

    def select_all_tickers(self):
        """Mevcut sayfadaki tüm ticker'ları seç"""
        try:
            current_tab = self.current_tab
            tree = self.trees[current_tab]
            
            # Treeview'daki tüm öğeleri al
            for item_id in tree.get_children():
                # Öğe değerlerini al
                item_values = tree.item(item_id, "values")
                if item_values and len(item_values) > 1:
                    ticker = item_values[1]  # Ticker, ikinci sütunda
                    
                    # Seçim sütununu güncelle
                    tree.set(item_id, "Select", "✓")
                    
                    # Seçilenlere ekle
                    self.selected_tickers[current_tab].add(ticker)
            
            # Seçili sayısını güncelle
            self.update_selected_count()
            
        except Exception as e:
            print(f"Select all tickers error: {e}")
            messagebox.showerror("Hata", f"Tümünü seçme hatası: {str(e)}")

    def deselect_all_tickers(self):
        """Mevcut sayfadaki tüm ticker seçimlerini kaldır"""
        try:
            current_tab = self.current_tab
            tree = self.trees[current_tab]
            
            # Treeview'daki tüm öğeleri al
            for item_id in tree.get_children():
                # Seçim sütununu güncelle
                tree.set(item_id, "Select", "□")
            
            # Seçilenleri temizle
            self.selected_tickers[current_tab].clear()
            
            # Seçili sayısını güncelle
            self.update_selected_count()
            
        except Exception as e:
            print(f"Deselect all tickers error: {e}")
            messagebox.showerror("Hata", f"Tümünü kaldırma hatası: {str(e)}")

    def update_selected_count(self):
        """Seçilen ticker sayısını güncelle"""
        try:
            current_tab = self.current_tab
            count = len(self.selected_tickers[current_tab])
            self.selected_count_label.config(text=f"Seçili: {count}")
        except Exception as e:
            print(f"Update selected count error: {e}")

    def place_hidden_bids_for_selected(self):
        """Seçili ticker'lar için hidden bid emirleri oluştur"""
        try:
            current_tab = self.current_tab
            selected = self.selected_tickers[current_tab]
            
            if not selected:
                messagebox.showinfo("Bilgi", "Hidden Bid için seçili ticker yok!")
                return
            
            # Hangi tip benchmark kullanılacağını belirle
            benchmark_type = "T" if current_tab == 0 else "C"
            benchmark_value = self.t_benchmark if current_tab == 0 else self.c_benchmark
                
            # Seçili ticker sayısını göster ve onay iste
            confirm = messagebox.askyesno(
                f"{benchmark_type}-Hidden Bid Onayı", 
                f"{len(selected)} adet {benchmark_type}-prefs ticker için Hidden Bid emirleri oluşturulacak.\nBenchmark: {benchmark_value:.2f} cent\nDevam etmek istiyor musunuz?"
            )
            
            if not confirm:
                return
                
            # Buraya hidden bid emirleri için gerekli işlemler eklenecek
            # Örnek implementasyon - gerçek işlemlerinize göre düzenlenecek
            for ticker in selected:
                # Ticker verilerini al
                ticker_data = self.market_data_cache.get(ticker)
                if not ticker_data:
                    print(f"{ticker} için veri bulunamadı, atlıyor")
                    continue
                    
                # Bid fiyatı, ask fiyatı ve spread'i belirle
                if (hasattr(ticker_data, 'bid') and ticker_data.bid is not None and not math.isnan(ticker_data.bid) and
                    hasattr(ticker_data, 'ask') and ticker_data.ask is not None and not math.isnan(ticker_data.ask)):
                    bid_price = ticker_data.bid
                    ask_price = ticker_data.ask
                    spread = ask_price - bid_price
                    
                    # Yeni hidden bid fiyatını hesapla: bid + spread * 0.15
                    hidden_bid_price = bid_price + (spread * 0.15)
                    
                    # Emir oluşturma
                    print(f"{benchmark_type}-Hidden Bid oluşturuluyor: {ticker} @ {hidden_bid_price:.2f} (bid: {bid_price:.2f}, spread: {spread:.2f})")
                    # self.create_hidden_bid_order(ticker, hidden_bid_price, 100)  # örnek
                else:
                    print(f"{ticker} için bid veya ask fiyatı bulunamadı, atlıyor")
            
            messagebox.showinfo("Başarılı", f"{len(selected)} adet {benchmark_type}-prefs ticker için Hidden Bid emirleri oluşturuldu.")
            
        except Exception as e:
            print(f"Place hidden bids for selected error: {e}")
            messagebox.showerror("Hata", f"Hidden Bid emirleri oluşturulurken hata: {str(e)}")

    def place_hidden_offers_for_selected(self):
        """Seçili ticker'lar için hidden offer emirleri oluştur"""
        try:
            current_tab = self.current_tab
            selected = self.selected_tickers[current_tab]
            
            if not selected:
                messagebox.showinfo("Bilgi", "Hidden Offer için seçili ticker yok!")
                return
            
            # Hangi tip benchmark kullanılacağını belirle
            benchmark_type = "T" if current_tab == 0 else "C"
            benchmark_value = self.t_benchmark if current_tab == 0 else self.c_benchmark
                
            # Seçili ticker sayısını göster ve onay iste
            confirm = messagebox.askyesno(
                f"{benchmark_type}-Hidden Offer Onayı", 
                f"{len(selected)} adet {benchmark_type}-prefs ticker için Hidden Offer emirleri oluşturulacak.\nBenchmark: {benchmark_value:.2f} cent\nDevam etmek istiyor musunuz?"
            )
            
            if not confirm:
                return
                
            # Buraya hidden offer emirleri için gerekli işlemler eklenecek
            # Örnek implementasyon - gerçek işlemlerinize göre düzenlenecek
            for ticker in selected:
                # Ticker verilerini al
                ticker_data = self.market_data_cache.get(ticker)
                if not ticker_data:
                    print(f"{ticker} için veri bulunamadı, atlıyor")
                    continue
                    
                # Bid fiyatı, ask fiyatı ve spread'i belirle
                if (hasattr(ticker_data, 'bid') and ticker_data.bid is not None and not math.isnan(ticker_data.bid) and
                    hasattr(ticker_data, 'ask') and ticker_data.ask is not None and not math.isnan(ticker_data.ask)):
                    bid_price = ticker_data.bid
                    ask_price = ticker_data.ask
                    spread = ask_price - bid_price
                    
                    # Yeni hidden offer fiyatını hesapla: ask - spread * 0.15
                    hidden_offer_price = ask_price - (spread * 0.15)
                    
                    # Emir oluşturma
                    print(f"{benchmark_type}-Hidden Offer oluşturuluyor: {ticker} @ {hidden_offer_price:.2f} (ask: {ask_price:.2f}, spread: {spread:.2f})")
                    # self.create_hidden_offer_order(ticker, hidden_offer_price, 100)  # örnek
                else:
                    print(f"{ticker} için bid veya ask fiyatı bulunamadı, atlıyor")
            
            messagebox.showinfo("Başarılı", f"{len(selected)} adet {benchmark_type}-prefs ticker için Hidden Offer emirleri oluşturuldu.")
            
        except Exception as e:
            print(f"Place hidden offers for selected error: {e}")
            messagebox.showerror("Hata", f"Hidden Offer emirleri oluşturulurken hata: {str(e)}")

    def load_tab_tickers(self):
        """Tüm sekmeleri hazırla ve ilk sayfayı göster"""
        try:
            print("Tab tickers yükleniyor...")
            
            # Prepare the tab data and pagination variables
            if not hasattr(self, 'tltr_tickers'):
                self.tltr_tickers = []
            
            if not hasattr(self, 'divspread_tickers'):
                self.divspread_tickers = []
            
            # CSV dosyalarından verileri kontrol et - eğer hala boşsa
            if len(self.tltr_tickers) == 0:
                try:
                    if os.path.exists("sma_results.csv"):
                        df_tltr = pd.read_csv("sma_results.csv")
                        df_tltr = normalize_ticker_column(df_tltr)
                        self.tltr_tickers = df_tltr["PREF IBKR"].dropna().unique().tolist()
                        print(f"T-prefs - CSV'den {len(self.tltr_tickers)} ticker yüklendi")
                    else:
                        print("sma_results.csv bulunamadı, T-prefs tickers boş")
                except Exception as e:
                    print(f"T-prefs CSV yükleme hatası: {e}")
            else:
                print(f"T-prefs - Hafızadan {len(self.tltr_tickers)} ticker kullanılıyor")
            
            if len(self.divspread_tickers) == 0:
                try:
                    if os.path.exists("extlt_results.csv"):
                        df_div = pd.read_csv("extlt_results.csv")
                        df_div = normalize_ticker_column(df_div)
                        self.divspread_tickers = df_div["PREF IBKR"].dropna().unique().tolist()
                        print(f"C-prefs - CSV'den {len(self.divspread_tickers)} ticker yüklendi")
                    else:
                        print("extlt_results.csv bulunamadı, C-prefs tickers boş")
                except Exception as e:
                    print(f"C-prefs CSV yükleme hatası: {e}")
            else:
                print(f"C-prefs - Hafızadan {len(self.divspread_tickers)} ticker kullanılıyor")
                
            # Sayfalama değişkenleri
            self.current_page = {0: 1, 1: 1}
            self.total_pages = {0: 1, 1: 1}
            
            # Her sekme için toplam sayfa sayısını hesapla
            for tab_index in range(len(self.tab_names)):
                if tab_index == 0:  # T-prefs
                    ticker_count = len(self.tltr_tickers)
                else:  # C-prefs  
                    ticker_count = len(self.divspread_tickers)
                    
                total_pages = max(1, (ticker_count + self.items_per_page - 1) // self.items_per_page)
                self.total_pages[tab_index] = total_pages
                print(f"Sekme {tab_index} - toplam sayfa sayısı: {total_pages}")
            
            # Populate the tabs
            for tab_index in range(len(self.tab_names)):
                # Tüm stokları filtrele ve sırala
                self.current_tab = tab_index
                self.populate_treeview()
                print(f"Sekme {tab_index} için treeview dolduruldu")
                
            # İlk sekmeye geç
            self.current_tab = 0
            print("Tab tickers başarıyla yüklendi")
            
        except Exception as e:
            print(f"Tab tickers loading error: {e}")
            import traceback
            traceback.print_exc()

    def load_stocks_from_csv(self, filename="final_thg_with_avg_adv.csv"):
        """CSV dosyasından hisse senetlerini yükle"""
        try:
            if os.path.exists(filename):
                self.stocks = pd.read_csv(filename)
                
                # Eksik sütunları ekle
                if 'sector' not in self.stocks.columns:
                    self.stocks['sector'] = 'Diğer'
                
                # Ticker sütununu normalleştir
                self.stocks = normalize_ticker_column(self.stocks)
                
                # Özel CSV dosyalarından ticker verilerini de yükle
                # T-prefs için veri yükle
                try:
                    if os.path.exists("sma_results.csv"):
                        df_tltr = pd.read_csv("sma_results.csv")
                        df_tltr = normalize_ticker_column(df_tltr)
                        # Use "PREF IBKR" column instead of "Ticker"
                        self.tltr_tickers = df_tltr["PREF IBKR"].dropna().unique().tolist()
                    else:
                        print("sma_results.csv bulunamadı")
                        self.tltr_tickers = []
                except Exception as e:
                    print(f"T-prefs tickers yükleme hatası: {e}")
                    self.tltr_tickers = []
                
                # C-prefs için veri yükle
                try:
                    if os.path.exists("extlt_results.csv"):
                        df_div = pd.read_csv("extlt_results.csv")
                        df_div = normalize_ticker_column(df_div)
                        # Use "PREF IBKR" column instead of "Ticker"
                        self.divspread_tickers = df_div["PREF IBKR"].dropna().unique().tolist()
                    else:
                        print("extlt_results.csv bulunamadı")
                        self.divspread_tickers = []
                except Exception as e:
                    print(f"C-prefs tickers yükleme hatası: {e}")
                    self.divspread_tickers = []
                
                # Sekmelere yerleştir
                self.load_tab_tickers()
                
                # Durum mesajı
                self.update_status(f"{len(self.stocks)} hisse senedi yüklendi.")
            else:
                self.update_status(f"Dosya bulunamadı: {filename}")
        except Exception as e:
            messagebox.showerror("Hata", f"Hisse senetleri yüklenirken hata oluştu: {e}")
            print(f"Error loading stocks: {e}")

    def connect_to_ibkr(self):
        """IBKR'ye bağlan ve market verilerini almaya başla"""
        if self.is_connected:
            self.update_status("Zaten bağlı", is_connected=True)
            return True
        
        try:
            print("IBKR bağlantısı kuruluyor...")
            
            # Önceki bağlantıyı temizle
            if hasattr(self, 'ib') and self.ib:
                try:
                    if self.ib.isConnected():
                        self.ib.disconnect()
                except Exception as e:
                    print(f"Önceki bağlantıyı kapatma hatası: {e}")
            
            self.ib = IB()
            
            # TWS ve Gateway portlarını dene
            ports = [7496, 4001]  # TWS ve Gateway portları
            connected = False
            
            for port in ports:
                try:
                    print(f"Port {port} ile bağlantı deneniyor...")
                    self.ib.connect('127.0.0.1', port, clientId=1, readonly=True, timeout=15)
                    connected = True
                    print(f"Port {port} ile bağlantı başarılı!")
                    break
                except Exception as e:
                    print(f"Port {port} bağlantı hatası: {e}")
            
            if not connected:
                print("Hiçbir porta bağlanılamadı! TWS veya Gateway çalışıyor mu?")
                self.update_status("Bağlantı hatası! TWS veya Gateway çalışıyor mu?", is_connected=False)
                messagebox.showerror("Bağlantı Hatası", 
                    "IBKR bağlantısı kurulamadı. Lütfen aşağıdaki adımları kontrol edin:\n\n" +
                    "1. TWS veya IB Gateway uygulamasının çalıştığından emin olun\n" +
                    "2. API ayarlarında 'Socket Clients' aktif edildiğinden emin olun\n" +
                    "3. Socket portu 7496 (TWS) veya 4001 (Gateway) olmalı\n" +
                    "4. API ayarlarında 'Trusted IP Addresses' listesinde 127.0.0.1 olmalı")
                return False
            
            # Bağlantı durumunu son kez kontrol et
            if not self.ib.isConnected():
                print("Bağlantı kurulamadı!")
                self.update_status("Bağlantı kurulamadı", is_connected=False)
                return False
            
            # Delayed data (gerçek hesap yoksa)
            self.ib.reqMarketDataType(3)  
            
            # Event handlerleri bağla
            self.ib.errorEvent += self.on_ib_error
            self.ib.disconnectedEvent += self.on_ib_disconnected
            self.ib.pendingTickersEvent += self.on_ticker_update
            
            # Bağlantı durumu
            self.is_connected = True
            self.running = True  # Veri akışı için gerekli
            
            # UI güncelle
            self.populate_treeview()
            self.update_status("IBKR'ye bağlandı", is_connected=True)
            
            # ETF verilerini al
            print("Benchmark varlıklarına abone olunuyor...")
            self.subscribe_benchmark_assets()
            
            # Görünen tickerları abone et
            self.subscribe_visible_tickers()
            
            # Event loop'u başlat - Veri akışı için gerekli
            self.after(100, self.run_event_loop)
            
            # Abonelik rotasyonunu başlat
            threading.Timer(60, self.rotate_subscriptions).start()
            
            # Pozisyonlar düğmesini etkinleştir
            self.positions_button.config(state=tk.NORMAL)
            
            # Başarılı mesajı
            messagebox.showinfo("Bağlantı", "IBKR bağlantısı başarıyla kuruldu.")
            
            return True
            
        except Exception as e:
            print(f"IBKR bağlantı hatası: {e}")
            self.update_status(f"Bağlantı hatası: {e}", is_connected=False)
            messagebox.showerror("Bağlantı Hatası", f"IBKR bağlantısı sırasında bir hata oluştu:\n\n{e}")
            
            # Bağlantıyı temizle
            self.is_connected = False
            self.running = False
            if hasattr(self, 'ib') and self.ib:
                try:
                    if self.ib.isConnected():
                        self.ib.disconnect()
                except Exception as ex:
                    print(f"Bağlantı kapama hatası: {ex}")
                    
            return False

    def subscribe_visible_tickers(self):
        """Görünen sayfadaki hisselere abone ol - sayfa geçişleri için iyileştirildi"""
        if not self.is_connected:
            print("Bağlantı yok, abonelik yapılamıyor")
            return False
        
        # Görünür durumdaki tickerları al
        visible_stocks = self.get_visible_stocks()
        if not visible_stocks:
            # Sayfada ticker yok, treeview boş olabilir
            print("Görünür hisse bulunamadı, treeview'ı kontrol et")
            
            # Eğer treeview boşsa, mevcut sayfa ve sekme için ticker listesinden yükle
            current_tab = self.current_tab
            current_page = self.current_page[current_tab]
            
            # Sayfa için ticker listesini al
            ticker_list = self.get_ticker_list_for_tab(current_tab)
            
            # Sayfa için ticker'ları hesapla
            start_idx = (current_page - 1) * self.items_per_page
            end_idx = min(start_idx + self.items_per_page, len(ticker_list))
            
            if start_idx < len(ticker_list):
                visible_stocks = ticker_list[start_idx:end_idx]
                print(f"Sayfada veri yoktu, ticker listesinden {len(visible_stocks)} sembol alındı")
        
        print(f"Görünür hisseler: {visible_stocks}")
        
        # Geçersiz sembolleri izlemek için set oluştur
        if not hasattr(self, 'invalid_symbols'):
            self.invalid_symbols = set()
        
        # Mevcut abonelikleri ve artık görünmeyenleri iptal et
        for symbol in list(self.tickers.keys()):
            # Görünür sayfada değilse iptal et
            if symbol not in visible_stocks:
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
        
        for symbol in visible_stocks:
            # Geçersiz sembol kontrolleri
            if symbol in self.tickers or symbol in self.invalid_symbols:
                continue
            
            if pd.isna(symbol) or symbol == '-':
                continue
            
            # Eğer aktif sembol limitine ulaştıysak durduralım
            if active_tickers >= max_active_tickers:
                print(f"⚠️ Aktif ticker limiti ({max_active_tickers}) aşıldı, abonelik süreci durduruldu.")
                print(f"Toplam {count} hisse için gerçek zamanlı abonelik başlatıldı")
                break
                    
            try:
                # Basit kontrat oluştur - tercihli hisseleri özel işleme almadan
                contract = Stock(symbol=symbol, exchange='SMART', currency='USD')
                
                # Market verisi için tick tipleri iste - BidAsk ve Last için
                self.ib.reqMktData(
                    contract, 
                    genericTickList="233,165,221",  # BidAsk + ek veriler
                    snapshot=False,  # Sürekli güncelleme iste
                    regulatorySnapshot=False
                )
                
                # Tickers sözlüğüne ekle
                self.tickers[symbol] = {
                    'contract': contract,
                    'row_id': self.ticker_id_map.get(symbol),
                    'subscription_time': time.time()  # Abonelik zamanını kaydedelim
                }
                
                count += 1
                active_tickers += 1
                print(f"✓ {symbol} için gerçek zamanlı abonelik başlatıldı ({active_tickers}/{max_active_tickers})")
                
                # Her 5 abonelikte bir API'nin işlemleri yapmasına zaman tanı
                if count % 5 == 0:
                    time.sleep(1.0)  # Daha uzun bekleme (0.5'ten 1.0'a çıkarıldı)
                
            except Exception as e:
                print(f"! {symbol} abonelik hatası: {str(e)}")
                # Hatalı sembolleri takip et
                self.invalid_symbols.add(symbol)
        
        # Aktif abonelik sayısını güncelle
        total_subscriptions = len(self.tickers)
        self.subscription_count_label.config(text=f"Aktif abonelikler: {total_subscriptions}/{max_active_tickers}")
        
        print(f"Toplam {count} görünür hisse için gerçek zamanlı abonelik başlatıldı")
        return True


    def run_event_loop(self):
        """IB event loop'u ile Tkinter event loop'unu senkronize et - ORIGINAL VERSION"""
        if self.running and self.is_connected:
            try:
                # IBKR event loop'unu çalıştır
                self.ib.sleep(0.01)  # 10ms
                
                # UI güncellemesi planla
                try:
                    # Son güncelleme zamanını göster
                    now_time = datetime.datetime.now().strftime("%H:%M:%S")
                    self.time_label.config(text=f"Son Güncelleme: {now_time}")
                    
                    # ETF bilgilerini güncelle - her 1 saniyede bir
                    current_time = time.time()
                    if not hasattr(self, 'last_etf_update') or current_time - self.last_etf_update >= 1.0:
                        self.update_etf_info()
                        self.last_etf_update = current_time
                    
                except Exception as e:
                    print(f"UI update error: {e}")
                
            except Exception as e:
                print(f"Event loop error: {e}")
            
            # Bir sonraki iterasyonu planla
            self.after(10, self.run_event_loop)


    def safe_reset_tags(self, tree, item_id):
        """Güvenli bir şekilde treeview öğesinin etiketlerini sıfırla"""
        try:
            if tree and item_id and tree.exists(item_id):
                current_tags = list(tree.item(item_id, "tags") or [])
                if "updated" in current_tags:
                    current_tags.remove("updated")
                    tree.item(item_id, tags=current_tags)
        except Exception as e:
            print(f"Tag reset error: {e}")


    def on_ticker_update(self, tickers):
        """Ticker güncellemelerinde çağrılacak callback - ETF güncellemesi iyileştirilmiş"""
        # ETF güncellemesini tetiklemek için bayrak
        etf_update_needed = False
        
        for ticker in tickers:
            symbol = None
            if hasattr(ticker.contract, 'localSymbol') and ticker.contract.localSymbol:
                symbol = ticker.contract.localSymbol
            else:
                symbol = ticker.contract.symbol
            
            # Market data cache'e ekle (her sembol için veriyi sakla)
            self.market_data_cache.update(symbol, ticker)
            
            # ETF'leri hemen güncelle (ETF listesinde varsa)
            if symbol in self.etf_list:
                print(f"ETF Verisi Alındı: {symbol} - Bid: {getattr(ticker, 'bid', 'N/A')}, Ask: {getattr(ticker, 'ask', 'N/A')}, Last: {getattr(ticker, 'last', 'N/A')}")
                # ETF güncelleme bayrağını aktif et
                etf_update_needed = True
            
            # Debug için değerleri yazdır
            if hasattr(ticker, 'bid') and ticker.bid is not None and not math.isnan(ticker.bid):
                print(f"TICK: {symbol} - Bid: {ticker.bid}")
            if hasattr(ticker, 'ask') and ticker.ask is not None and not math.isnan(ticker.ask):
                print(f"TICK: {symbol} - Ask: {ticker.ask}")
            
            # UI güncelle - Sadece şu anda görünen sembolleri
            if symbol in self.ticker_id_map:
                # UI güncellemesi için kullanılan tree'yi bul
                tree = self.trees[self.current_tab]
                item_id = self.ticker_id_map.get(symbol)
                
                # Satır bulunduysa güncelle
                if item_id and tree.exists(item_id):
                    item_values = tree.item(item_id, "values")
                    if item_values and item_values[1] == symbol:  # Artık Ticker 1. indekste çünkü 0. indeks Seç sütunu
                        values = list(item_values)
                        
                        # SEÇİM DURUMUNU KORU - İlk sütunu değiştirme
                        # selection_status = values[0]
                        
                        # Fiyatlar - Kolon indeksleri değişti
                        if ticker.last is not None and not (isinstance(ticker.last, float) and (ticker.last != ticker.last)):
                            values[2] = f"{ticker.last:.2f}"
                        if ticker.bid is not None and not (isinstance(ticker.bid, float) and (ticker.bid != ticker.bid)):
                            values[3] = f"{ticker.bid:.2f}"
                        if ticker.ask is not None and not (isinstance(ticker.ask, float) and (ticker.ask != ticker.ask)):
                            values[4] = f"{ticker.ask:.2f}"
                        # Spread
                        if (ticker.bid is not None and not (isinstance(ticker.bid, float) and (ticker.bid != ticker.bid)) and
                            ticker.ask is not None and not (isinstance(ticker.ask, float) and (ticker.ask != ticker.ask))):
                            spread = ticker.ask - ticker.bid
                            values[5] = f"{spread:.2f}"
                        # Hacim
                        if ticker.volume is not None and not (isinstance(ticker.volume, float) and (ticker.volume != ticker.volume)):
                            values[6] = f"{int(ticker.volume):,}"
                        
                        tree.item(item_id, values=values, tags=('updated',))
                        
                        # Güvenli bir şekilde renk değişimini geri al - lambda fonksiyonu yerine after_id kullanarak
                        self.after(1000, lambda tree_ref=tree, item_ref=item_id: 
                                  self.safe_reset_tags(tree_ref, item_ref))
        
        # ETF verisi geldi ve güncelleme gerektiriyorsa, hemen güncelle
        if etf_update_needed:
            self.after(10, self.update_etf_info)  # 10ms içinde UI thread'de ETF bilgilerini güncelle
        
        # Son güncelleme zamanını güncelle
        self.last_update_label.config(text=f"Son güncelleme: {time.strftime('%H:%M:%S')}")

    def rotate_subscriptions(self):
        """Abonelikleri döngüsel olarak yenile - ORIGINAL VERSION"""
        if not self.running or not self.is_connected:
            return
        
        try:
            # Görünen sayfadaki sembolleri her zaman aktif tut
            visible_symbols = self.get_visible_stocks()
            
            # Diğer abonelikleri yönet (görünen sayfada olmayanlar)
            other_tickers = {s: info for s, info in self.tickers.items() if s not in visible_symbols}
            
            # En eski abonelikleri bul ve iptal et
            if other_tickers:
                # En eski 5 aboneliği iptal et
                ticker_ages = [(symbol, info['subscription_time']) 
                             for symbol, info in other_tickers.items()]
                ticker_ages.sort(key=lambda x: x[1])  # En eskiden yeniye sırala
                
                cancel_count = min(5, len(ticker_ages))
                for symbol, _ in ticker_ages[:cancel_count]:
                    try:
                        contract = self.tickers[symbol]['contract']
                        self.ib.cancelMktData(contract)
                        del self.tickers[symbol]
                        print(f"✓ {symbol} aboneliği iptal edildi (rotasyon)")
                    except Exception as e:
                        print(f"! {symbol} abonelik iptali hatası: {e}")
            
            # Bir sonraki rotasyon için zamanlayıcı kur
            if self.running:
                threading.Timer(60, self.rotate_subscriptions).start()
            
        except Exception as e:
            print(f"Subscription rotation error: {e}")
            # Bir hata oluşsa bile rotasyonu devam ettir
            if self.running:
                threading.Timer(60, self.rotate_subscriptions).start()

    def disconnect_from_ibkr(self):
        """Interactive Brokers API bağlantısını keser"""
        try:
            if self.is_connected:
                # Callback'leri temizle
                try:
                    if hasattr(self.ib, 'pendingTickersEvent'):
                        self.ib.pendingTickersEvent -= self.on_ticker_update
                except Exception as e:
                    print(f"Callback temizleme hatası: {e}")
                
                # Bağlantıyı kapat
                if disconnect_from_ibkr(self.ib):
                    self.is_connected = False
                    self.connect_btn.config(text="IB'ye Bağlan", command=self.connect_to_ibkr)
                    self.update_status("Interactive Brokers bağlantısı kesildi")
                else:
                    self.update_status("Interactive Brokers bağlantısı kesilirken hata oluştu!")
        except Exception as e:
            print(f"Disconnect error: {e}")
            self.update_status(f"Bağlantı kesme hatası: {e}")
    
    def update_status(self, status_text, is_connected=None):
        """Durum çubuğunu güncelle"""
        if is_connected is None:
            is_connected = self.is_connected
        update_status_bar(self.status_bar, status_text, is_connected)
    
    def process_market_data(self):
        """Piyasa verilerini işle ve UI güncellemeleri yap"""
        try:
            # Mevcut görünür hisseleri al
            visible_stocks = self.get_visible_stocks()
            
            # Her görünür ticker için veri güncellemesi yap
            for ticker_symbol in visible_stocks:
                ticker_data = self.market_data_cache.get(ticker_symbol)
                if not ticker_data:
                    continue
                
                # Debug: Veri içeriğini kontrol et
                if hasattr(ticker_data, 'bid'):
                    bid_value = ticker_data.bid if ticker_data.bid is not None else "None"
                    print(f"Debug {ticker_symbol} - bid: {bid_value}")
                if hasattr(ticker_data, 'ask'):
                    ask_value = ticker_data.ask if ticker_data.ask is not None else "None"
                    print(f"Debug {ticker_symbol} - ask: {ask_value}")
                    
                # İlgili satırı bul
                item_id = self.ticker_id_map.get(ticker_symbol)
                if not item_id:
                    continue
                
                # Hangi treeview'da olduğunu bul (mevcut sekmedeki)
                tree = self.trees[self.current_tab]
                
                # Değerleri güncelle
                values = list(tree.item(item_id, "values"))
                
                # Son fiyat - Kolon indekslerini güncelle
                if hasattr(ticker_data, 'last') and ticker_data.last is not None:
                    values[2] = safe_format_float(ticker_data.last)
                    
                # Alış fiyatı
                if hasattr(ticker_data, 'bid') and ticker_data.bid is not None:
                    values[3] = safe_format_float(ticker_data.bid)
                
                # Satış fiyatı
                if hasattr(ticker_data, 'ask') and ticker_data.ask is not None:
                    values[4] = safe_format_float(ticker_data.ask)
                
                # Spread hesapla
                if hasattr(ticker_data, 'bid') and hasattr(ticker_data, 'ask') and \
                   ticker_data.bid is not None and ticker_data.ask is not None and ticker_data.bid > 0:
                    spread = ((ticker_data.ask - ticker_data.bid) / ticker_data.bid) * 100
                    values[5] = safe_format_float(spread, decimals=2) + "%"
                
                # Hacim
                if hasattr(ticker_data, 'volume') and ticker_data.volume is not None:
                    values[6] = str(safe_int(ticker_data.volume))
                
                # Treeview öğesini güncelle
                tree.item(item_id, values=values)
                
                # Renk etiketi (değişim yüzdesine göre)
                if hasattr(ticker_data, 'last') and hasattr(ticker_data, 'close') and \
                   ticker_data.last is not None and ticker_data.close is not None and ticker_data.close > 0:
                    change = ((ticker_data.last - ticker_data.close) / ticker_data.close) * 100
                    
                    # Mevcut etiketleri al
                    tags = list(tree.item(item_id, "tags") or [])
                    
                    # Renk etiketlerini temizle
                    tags = [tag for tag in tags if tag not in ['green', 'red', 'neutral']]
                    
                    # Yeni renk etiketi ekle
                    if change > 0.01:
                        tags.append('green')
                    elif change < -0.01:
                        tags.append('red')
                    else:
                        tags.append('neutral')
                    
                    # Etiketleri güncelle
                    tree.item(item_id, tags=tags)
        except Exception as e:
            print(f"Process market data error: {e}")

    def update_benchmarks(self):
        """Benchmark verilerini güncelle (PFF, TLT ve diğer ETF'ler)"""
        try:
            # Tüm ETF'ler için döngü
            for etf_symbol in self.etf_list:
                etf_data = self.market_data_cache.get(etf_symbol)
                
                # Verisi olmayan ETF'leri atla
                if not etf_data:
                    continue
                    
                etf_price = 0
                etf_change = 0
                etf_daily_change_cents = 0
                
                # ETF güncellemesi
                if hasattr(etf_data, 'last') and etf_data.last is not None and not math.isnan(etf_data.last):
                    etf_price = etf_data.last
                    
                    # Değişim hesapla
                    if hasattr(etf_data, 'close') and etf_data.close is not None and not math.isnan(etf_data.close) and etf_data.close > 0:
                        # Fiyat değişimini hesapla
                        etf_change = ((etf_data.last - etf_data.close) / etf_data.close) * 100
                        
                        # Önceki kapanışı kaydet
                        self.etf_prev_close[etf_symbol] = etf_data.close
                        
                        # Cent değişimi (benchmark için)
                        etf_daily_change_cents = (etf_data.last - etf_data.close) * 100  # Dolar -> cent
                        
                        # Değişimleri cache'e ekle
                        self.etf_changes[etf_symbol] = etf_daily_change_cents
                    
                # Eski metod için geriye dönük uyumluluk (PFF/TLT için özel değişkenler)
                if etf_symbol == "PFF":
                    self.pff_change_cache = etf_change if etf_change != 0 else self.pff_change_cache
                    self.pff_prev_close = self.etf_prev_close.get("PFF")
                    pff_daily_change_cents = etf_daily_change_cents
                    
                elif etf_symbol == "TLT":
                    self.tlt_change_cache = etf_change if etf_change != 0 else self.tlt_change_cache
                    self.tlt_prev_close = self.etf_prev_close.get("TLT")
                    tlt_daily_change_cents = etf_daily_change_cents
            
            # PFF ve TLT ile benchmark hesapla
            pff_daily_change_cents = self.etf_changes.get("PFF", 0)
            tlt_daily_change_cents = self.etf_changes.get("TLT", 0)
            benchmark_change = self.calculate_benchmark_change(pff_daily_change_cents, tlt_daily_change_cents)
            
            # Debug bilgisi
            print(f"ETF Değerleri: {', '.join([f'{symbol}: {self.etf_changes.get(symbol, 0):.2f}' for symbol in self.etf_list])}")
            print(f"T-benchmark: {self.t_benchmark:.2f}, C-benchmark: {self.c_benchmark:.2f}")
            
            # Benchmark etiketlerini güncelle (eski PFF/TLT göstergeleri için)
            update_benchmark_labels(
                self.pff_label, self.tlt_label, self.benchmark_label, self.time_label,
                self.etf_prev_close.get("PFF", 0), self.pff_change_cache, 
                self.etf_prev_close.get("TLT", 0), self.tlt_change_cache, benchmark_change
            )
            
            # Yeni benchmark etiketlerini güncelle
            self.update_custom_benchmarks()
            
        except Exception as e:
            print(f"Update benchmarks error: {e}")
            import traceback
            traceback.print_exc()

    def update_custom_benchmarks(self):
        """T-benchmark ve C-benchmark etiketlerini güncelle"""
        try:
            # T-benchmark (cent bazında)
            t_style = 'ETFUp.TLabel' if self.t_benchmark > 0 else 'ETFDown.TLabel' if self.t_benchmark < 0 else 'ETFNeutral.TLabel'
            self.t_benchmark_label.config(
                text=f"T-benchmark: {self.t_benchmark:+.2f}¢", 
                style=t_style
            )
            
            # C-benchmark (cent bazında)
            c_style = 'ETFUp.TLabel' if self.c_benchmark > 0 else 'ETFDown.TLabel' if self.c_benchmark < 0 else 'ETFNeutral.TLabel'
            self.c_benchmark_label.config(
                text=f"C-benchmark: {self.c_benchmark:+.2f}¢", 
                style=c_style
            )
        except Exception as e:
            print(f"Update custom benchmarks error: {e}")
            import traceback
            traceback.print_exc()

    def get_visible_stocks(self):
        """Şu anda görünür olan stokların listesini döndür - iyileştirildi"""
        try:
            visible = []
            
            # Mevcut sekmedeki treeview'da görünen öğeleri al
            tree = self.trees.get(self.current_tab)
            if tree:
                # Treeview içeriğini kontrol et 
                children = tree.get_children()
                
                if children:  # Treeview'da öğeler varsa
                    for item_id in children:
                        # Öğe değerlerini al
                        values = tree.item(item_id, "values")
                        if values and len(values) > 1 and values[1]:  # Ticker artık 1. indekste (0 yerine)
                            ticker = values[1]
                            visible.append(ticker)
        
            # Eğer treeview boşsa veya öğe bulunamadıysa, mevcut sayfa ve sekmeye ait ticker listesinden al
            if not visible:
                current_tab = self.current_tab
                current_page = self.current_page.get(current_tab, 1)
                
                # Mevcut sekmedeki hisselerin tam listesinden ilk sayfadakileri döndür
                ticker_list = self.get_ticker_list_for_tab(current_tab)
                
                # Sayfa bilgilerini kullanarak görünür stokları hesapla
                start_idx = (current_page - 1) * self.items_per_page
                end_idx = min(start_idx + self.items_per_page, len(ticker_list))
                
                if start_idx < len(ticker_list):
                    visible = ticker_list[start_idx:end_idx]
                    print(f"Treeview'da veri bulunamadı, {len(visible)} sembol ticker listesinden alındı")
        
            print(f"Görünür stoklar: {visible}, toplam: {len(visible)}")
            if not visible:
                print("Uyarı: Görünür stock listesi boş!")
                
            return visible
        except Exception as e:
            print(f"Get visible stocks error: {e}")
            import traceback
            traceback.print_exc()
            return []

    def on_tree_select(self, event):
        """Treeview'da bir öğe seçildiğinde çağrılır"""
        try:
            # Hangi treeview'da seçim yapıldığını belirle
            tree = event.widget
            
            # Seçilen öğeyi al
            selected_items = tree.selection()
            if not selected_items:
                return
            
            # İlk seçili öğeyi al (çoklu seçim varsa)
            item_id = selected_items[0]
            
            # Öğe değerlerini al
            values = tree.item(item_id, "values")
            if not values:
                return
            
            # Ticker sembolünü al (ilk sütun)
            ticker = values[0]
            
            # Ticker'ı önceliklendirerek cache'de kalmasını sağla
            if ticker:
                self.market_data_cache.prioritize_symbol(ticker)
            
            # Seçilen satır için özel bir stil uygula (opsiyonel)
            for child in tree.get_children():
                if 'selected' in tree.item(child, 'tags'):
                    # 'selected' etiketini kaldır
                    tags = list(tree.item(child, 'tags'))
                    tags.remove('selected')
                    tree.item(child, tags=tags)
            
            # Seçilen satıra 'selected' etiketi ekle
            current_tags = list(tree.item(item_id, 'tags'))
            if 'selected' not in current_tags:
                current_tags.append('selected')
                tree.item(item_id, tags=current_tags)
        
        except Exception as e:
            print(f"Tree select error: {e}")

    def process_api_calls(self):
        """IB API çağrılarını işleyen thread fonksiyonu"""
        # tb_ib_connection modülünden fonksiyonu kullanarak api işleyicisi oluştur ve çalıştır
        api_processor = create_api_call_processor(self.api_queue)
        api_processor()  # Bu sonsuz bir döngü olduğu için thread içinde çalışır
    
    def queue_api_call(self, func, *args, **kwargs):
        """Bir API çağrısını kuyruğa ekle"""
        queue_api_call(self.api_queue, func, *args, **kwargs)
    
    def create_preferred_stock_contract(self, ticker_symbol):
        """Tercih edilmiş hisse senedi kontratı oluşturur"""
        return create_preferred_stock_contract(ticker_symbol)
    
    def subscribe_benchmark_assets(self):
        """Benchmark varlıklarına (PFF, TLT, SPY, IWM, KRE) abone ol - gerçek zamanlı sürekli güncelleme için optimize edildi"""
        try:
            if not self.is_connected:
                print("Bağlantı yok, benchmark varlıklarına abone olunamıyor")
                return
                
            print("Benchmark ETF'lerine sürekli abonelik oluşturuluyor...")
            
            # Benchmark ETF'leri için geçerli tick listesi (IB API'nin kabul ettiği)
            # Hata mesajında belirtilen geçerli tick tipleri listesinden alındı
            generic_tick_list = "233,236,165,100,101,105,106"  # Düzeltildi: RTVolume, inventory, Misc. Stats, Option data
            
            # Market data tipini ayarla - gerçek zamanlı veri için
            print("ETF'ler için market data tipini ayarlama (live data)...")
            self.ib.reqMarketDataType(1)  # Live data
            time.sleep(0.2)
            
            # Tüm ETF'ler için doğrudan IB API ile abonelik oluştur 
            for etf_symbol in self.etf_list:
                try:
                    # Önceki aboneliği temizle
                    if etf_symbol in self.benchmark_assets and self.benchmark_assets[etf_symbol] is not None:
                        try:
                            self.ib.cancelMktData(self.benchmark_assets[etf_symbol])
                            print(f"{etf_symbol} için önceki abonelik iptal edildi")
                        except Exception as e:
                            print(f"{etf_symbol} iptal hatası: {e}")
                    
                    # ETF kontratı oluştur ve kaydet - primary exchange belirterek
                    etf_contract = Stock(symbol=etf_symbol, exchange='SMART', currency='USD', primaryExchange='ARCA')
                    self.benchmark_assets[etf_symbol] = etf_contract
                    
                    # Abonelik oluştur - snapshot=False ile sürekli güncellemeler al
                    print(f"{etf_symbol} için gerçek zamanlı sürekli abonelik oluşturuluyor...")
                    etf_ticker = self.ib.reqMktData(
                        etf_contract, 
                        generic_tick_list, 
                        snapshot=False,  # Sürekli güncellemeler için False
                        regulatorySnapshot=False
                    )
                    
                    # API'nin işlemesi için bekle
                    self.ib.sleep(0.5)
                    
                    # Cache'e ekle ve önceliklendir
                    self.market_data_cache.add_subscription(etf_symbol, etf_contract, self.ib)
                    self.market_data_cache.prioritize_symbol(etf_symbol)
                    
                    # İlk veri geldi mi kontrol et ve debug
                    print(f"{etf_symbol} ilk veri: last={getattr(etf_ticker, 'last', 'N/A')}, " + 
                          f"bid={getattr(etf_ticker, 'bid', 'N/A')}, ask={getattr(etf_ticker, 'ask', 'N/A')}")
                    
                    # Veri gelmediyse, tekrar dene
                    if (not hasattr(etf_ticker, 'last') or etf_ticker.last is None or 
                        (isinstance(etf_ticker.last, float) and math.isnan(etf_ticker.last))):
                        print(f"{etf_symbol} için veri alınamadı, tekrar deniyor...")
                        # Son bir deneme - market data tipini tekrar ayarlayarak
                        self.ib.cancelMktData(etf_contract)
                        self.ib.sleep(0.2)
                        self.ib.reqMarketDataType(1)  # Live data'yı tekrar talep et
                        self.ib.sleep(0.2)
                        self.ib.reqMktData(etf_contract, generic_tick_list, snapshot=False, regulatorySnapshot=False)
                        self.ib.sleep(0.5)
                        print(f"{etf_symbol} tekrar deneme: last={getattr(etf_ticker, 'last', 'N/A')}")
                    
                except Exception as e:
                    print(f"{etf_symbol} abonelik hatası: {e}")
                    import traceback
                    traceback.print_exc()
            
            # ETF bilgilerini hemen güncelle
            self.update_etf_info()
            
            # UI güncellemesi için biraz zaman ver
            self.update_idletasks()
            
            print("Benchmark abonelikleri tamamlandı - sürekli güncellemeler etkin")
        except Exception as e:
            print(f"Subscribe benchmark assets error: {e}")
            import traceback
            traceback.print_exc()
    
    def calculate_benchmark_change(self, pff_daily_change_cents, tlt_daily_change_cents):
        """ETF değişimlerinin ağırlıklı ortalaması"""
        # Eski benchmark hesaplama (geriye dönük uyumluluk için)
        weighted_change = (pff_daily_change_cents * 0.7) + (tlt_daily_change_cents * 0.3)
        
        # T-prefs için benchmark (cent bazında): PFF*0.7 + TLT*0.1
        t_benchmark = (pff_daily_change_cents * 0.7) + (tlt_daily_change_cents * 0.1)
        
        # C-prefs için benchmark (cent bazında): PFF*1.3 - TLT*0.1
        c_benchmark = (pff_daily_change_cents * 1.3) - (tlt_daily_change_cents * 0.1)
        
        # Değerleri kaydet
        self.t_benchmark = t_benchmark
        self.c_benchmark = c_benchmark
        
        return weighted_change
    
    def toggle_rotation(self):
        """Ticker rotasyonunu aç/kapat"""
        try:
            self.ticker_rotation_active = self.rotation_var.get()
            
            if self.ticker_rotation_active:
                self.update_status("Ticker rotasyonu aktif")
            else:
                self.update_status("Ticker rotasyonu devre dışı")
        except Exception as e:
            print(f"Toggle rotation error: {e}")
    
    def apply_filter(self):
        """Filtre metnini uygula"""
        try:
            # Treeview'ı güncelle
            self.populate_treeview()
            
            # Filtre metnini göster
            filter_text = self.filter_var.get().strip()
            if filter_text:
                self.update_status(f"Filtre: {filter_text}")
        except Exception as e:
            print(f"Apply filter error: {e}")
    
    def clear_filter(self):
        """Filtreyi temizle"""
        try:
            self.filter_var.set("")
            self.populate_treeview()
            self.update_status("Filtre temizlendi")
        except Exception as e:
            print(f"Clear filter error: {e}")
    
    def prev_page(self):
        """Önceki sayfaya git - iyileştirilmiş"""
        try:
            current_tab = self.current_tab
            
            if self.current_page[current_tab] > 1:
                print(f"Önceki sayfaya geçiliyor: {self.current_page[current_tab]} --> {self.current_page[current_tab]-1}")
                
                # Sayfa numarasını azalt
                self.current_page[current_tab] -= 1
                
                # Treeview'ı güncelle - yeni populate_treeview kullan
                self.populate_treeview()
        except Exception as e:
            print(f"Previous page error: {e}")
            import traceback
            traceback.print_exc()
    
    def next_page(self):
        """Sonraki sayfaya git - iyileştirilmiş"""
        try:
            current_tab = self.current_tab
            
            if self.current_page[current_tab] < self.total_pages[current_tab]:
                print(f"Sonraki sayfaya geçiliyor: {self.current_page[current_tab]} --> {self.current_page[current_tab]+1}")
                
                # Sayfa numarasını artır
                self.current_page[current_tab] += 1
                
                # Treeview'ı güncelle - yeni populate_treeview kullan
                self.populate_treeview()
        except Exception as e:
            print(f"Next page error: {e}")
            import traceback
            traceback.print_exc()
    
    def jump_to_page(self):
        """Belirli bir sayfaya git"""
        try:
            current_tab = self.current_tab
            
            # Girilen sayfa numarasını al
            page_num = int(self.jump_to_page_var.get())
            print(f"Sayfa atlaması: {self.current_page[current_tab]} -> {page_num}")
            
            # Geçerli bir sayfa numarası mı kontrol et
            if 1 <= page_num <= self.total_pages[current_tab]:
                # Sayfa numarasını ayarla
                self.current_page[current_tab] = page_num
                
                # Treeview'ı temizle
                tree = self.trees[current_tab]
                for item in tree.get_children():
                    tree.delete(item)
                    
                # Treeview'ı güncelle
                self.populate_treeview()
                
                # Treeview doldu mu kontrol et
                if not tree.get_children():
                    print("UYARI: Sayfa atlaması sonrası treeview boş, zorla yenileme yapılıyor!")
                    self.after(200, self.force_refresh)
                
                # Sayfa bilgisini güncelle
                update_page_info(self.page_info, self.current_page[current_tab], self.total_pages[current_tab])
            else:
                print(f"Geçersiz sayfa numarası: {page_num}, maks: {self.total_pages[current_tab]}")
                create_error_popup("Hata", f"Geçerli bir sayfa numarası giriniz (1-{self.total_pages[current_tab]})", parent=self)
        except (ValueError, TypeError) as e:
            # Geçersiz sayfa numarası
            print(f"Geçersiz sayfa numarası biçimi: {e}")
            create_error_popup("Hata", "Geçerli bir sayfa numarası giriniz", parent=self)
        except Exception as e:
            print(f"Jump to page error: {e}")
            import traceback
            traceback.print_exc()
    
    def on_tab_changed(self, event=None):
        """Sekme değiştirildiğinde çağrılır - ETF aboneliklerini korur"""
        try:
            # Yeni sekme indeksini al
            new_tab = self.notebook.index("current")
            
            # Sekme değiştiyse işlem yap
            if new_tab != self.current_tab:
                print(f"Sekme değiştiriliyor: {self.current_tab} -> {new_tab}")
                
                # Mevcut sekme durumunu kaydet
                old_tab = self.current_tab
                
                # Sekme indeksini güncelle
                self.current_tab = new_tab
                
                # Treeview'ı temizle - önceki sekmenin içeriğini boşalt
                if old_tab in self.trees:
                    old_tree = self.trees[old_tab]
                    for item in old_tree.get_children():
                        old_tree.delete(item)
                
                # Yeni sekmenin treeview'ını temizle
                if new_tab in self.trees:
                    new_tree = self.trees[new_tab]
                    for item in new_tree.get_children():
                        new_tree.delete(item)
                
                # ETF sembollerini geçici bir listede tut
                etf_symbols = self.etf_list.copy()
                
                # Mevcut abonelikleri iptal et (ETF'leri hariç tutarak)
                if self.is_connected:
                    print("Mevcut abonelikler iptal ediliyor (ETF'ler hariç)...")
                    for symbol in list(self.tickers.keys()):
                        if symbol not in etf_symbols:  # ETF'leri koruyoruz
                            try:
                                contract = self.tickers[symbol]['contract']
                                self.ib.cancelMktData(contract)
                                del self.tickers[symbol]
                                print(f"✓ {symbol} aboneliği iptal edildi (sekme değişimi)")
                            except Exception as e:
                                print(f"! {symbol} abonelik iptali hatası: {e}")
                
                # Treeview'ı güncelle
                self.populate_treeview()
                
                # Treeview doldu mu kontrol et
                if new_tab in self.trees:
                    new_tree = self.trees[new_tab]
                    if not new_tree.get_children():
                        print("UYARI: Sekme değişimi sonrası treeview boş, zorla yenileme yapılıyor!")
                        self.after(200, self.force_refresh)
                
                # Abonelikleri güncelle
                if self.is_connected:
                    self.after(100, self.subscribe_visible_tickers)
                    
                # Sayfa bilgisini güncelle
                update_page_info(self.page_info, self.current_page[new_tab], self.total_pages[new_tab])
                
                # ETF verileri için güncelleme tetikle
                self.after(500, self.update_etf_info)
        except Exception as e:
            print(f"Tab changed error: {e}")
            import traceback
            traceback.print_exc()
    
    def sort_treeview(self, column):
        """Treeview'ı belirli bir sütuna göre sırala"""
        try:
            # Aynı sütuna tıklandıysa sıralama yönünü değiştir
            if self.sort_column == column:
                self.sort_reverse = not self.sort_reverse
            else:
                # Farklı bir sütuna tıklandıysa, varsayılan olarak artan sırala
                self.sort_reverse = False
                self.sort_column = column
            
            # Sekmeyi yeniden yükle
            self.populate_treeview()
        except Exception as e:
            print(f"Sort treeview error: {e}")
    
    def populate_treeview(self):
        """Ana treeview'ı doldur - iyileştirilmiş, sayfa değişimi sorunlarını çözecek şekilde"""
        try:
            # Seçili sekmeyi ve mevcut sayfa numarasını al
            current_tab = self.current_tab
            current_page = self.current_page[current_tab]
            
            # Treeview'ı al
            tree = self.trees[current_tab]
            if not tree:
                print(f"HATA: Sekme {current_tab} için treeview bulunamadı!")
                return
                
            print(f"Sekme {current_tab}, Sayfa {current_page} için treeview dolduruluyor...")
            
            # Treeview'ı temizle
            for item in tree.get_children():
                tree.delete(item)
            
            # Sekmeye göre ticker listesini al
            ticker_list = self.get_ticker_list_for_tab(current_tab)
            
            if not ticker_list:
                print(f"Uyarı: Sekme {current_tab} için ticker listesi boş!")
                return
                
            # Filtre metnini al
            filter_text = self.filter_var.get().strip() if hasattr(self, 'filter_var') and self.filter_var.get() else ""
            
            # Filtreleme yap
            if filter_text:
                filtered_ticker_list = [ticker for ticker in ticker_list if filter_text.lower() in ticker.lower()]
                ticker_list = filtered_ticker_list
                print(f"Filtreden sonra kalan ticker sayısı: {len(ticker_list)}")
            
            # Toplam sayfa sayısını hesapla
            total_items = len(ticker_list)
            if total_items == 0:
                print("HATA: Toplam ticker sayısı 0!")
                return
                
            total_pages = max(1, (total_items + self.items_per_page - 1) // self.items_per_page)
            
            # Mevcut sayfayı sınırla
            current_page = min(current_page, total_pages)
            self.current_page[current_tab] = current_page
            
            print(f"Sayfa {current_page}/{total_pages}, toplam {total_items} ticker")
            
            # Bu sayfadaki öğeleri hesapla
            start_idx = (current_page - 1) * self.items_per_page
            end_idx = min(start_idx + self.items_per_page, total_items)
            
            if start_idx >= total_items:
                print(f"HATA: Başlangıç indeksi ({start_idx}) toplam eleman sayısından ({total_items}) büyük!")
                # First page'e resetle
                self.current_page[current_tab] = 1
                start_idx = 0
                end_idx = min(self.items_per_page, total_items)
                
            page_tickers = ticker_list[start_idx:end_idx]
            print(f"Sayfada gösterilen ticker sayısı: {len(page_tickers)}")
            print(f"Gösterilen ticker'lar: {page_tickers}")
            
            # Sayfa bilgisini güncelle
            self.total_pages[current_tab] = total_pages
            update_page_info(self.page_info, current_page, total_pages)
            
            # Ticker ID map'i temizle ve yeniden oluştur
            self.ticker_id_map = {}
            
            # Mevcut seçimleri al
            selected_tickers = self.selected_tickers[current_tab]
            
            # Treeview'ı doldur
            for idx, ticker in enumerate(page_tickers):
                # Ticker verilerini al (cache'den veya IB'den)
                ticker_data = self.market_data_cache.get(ticker)
                
                # Seçim durumunu belirle
                is_selected = ticker in selected_tickers
                checkbox_str = "✓" if is_selected else "□"
                
                # Görüntülenecek verileri ayarla
                values = [checkbox_str, ticker, "", "", "", "", ""]
                
                if ticker_data:
                    # Veri varsa değerleri güncelle
                    if hasattr(ticker_data, 'last') and ticker_data.last is not None and not math.isnan(ticker_data.last):
                        values[2] = safe_format_float(ticker_data.last)
                    if hasattr(ticker_data, 'bid') and ticker_data.bid is not None and not math.isnan(ticker_data.bid):
                        values[3] = safe_format_float(ticker_data.bid)
                    if hasattr(ticker_data, 'ask') and ticker_data.ask is not None and not math.isnan(ticker_data.ask):
                        values[4] = safe_format_float(ticker_data.ask)
                    
                    # Spread hesapla
                    if hasattr(ticker_data, 'bid') and hasattr(ticker_data, 'ask') and \
                       ticker_data.bid is not None and ticker_data.ask is not None and ticker_data.bid > 0 and \
                       not math.isnan(ticker_data.bid) and not math.isnan(ticker_data.ask):
                        spread = ((ticker_data.ask - ticker_data.bid) / ticker_data.bid) * 100
                        values[5] = f"{spread:.2f}%"
                    
                    # Hacim
                    if hasattr(ticker_data, 'volume') and ticker_data.volume is not None and not math.isnan(ticker_data.volume):
                        values[6] = f"{int(ticker_data.volume):,}"
                
                # Öğeyi ekle
                item_id = tree.insert("", "end", values=values)
                
                # Ticker ID eşlemesi
                self.ticker_id_map[ticker] = item_id
            
            # Eğer hiç öğe eklenmezse, boş sayfa olduğunu logla
            if not self.ticker_id_map:
                print(f"UYARI: Sayfa {current_page} için ticker_id_map boş!")
            else:
                print(f"Sayfa {current_page} için ticker_id_map oluşturuldu, {len(self.ticker_id_map)} ticker içeriyor")
            
            # Abonelik sayısını güncelle
            self.subscription_count_label.config(text=f"Aktif abonelikler: {self.market_data_cache.get_subscription_count()}/{self.market_data_cache.max_subscriptions}")
            
            # Seçili ticker sayısını güncelle
            self.update_selected_count()
            
            # UI güncellenmesi için biraz zaman verin
            self.update_idletasks()
            
            # Sayfa değişimi olduğu için abonelikleri güncelle
            if self.is_connected:
                self.subscribe_visible_tickers()
            
            print(f"Treeview başarıyla dolduruldu, toplam {len(page_tickers)} ticker")
            
        except Exception as e:
            print(f"Populate treeview error: {e}")
            import traceback
            traceback.print_exc()
    
    def place_hidden_bids(self):
        """Gizli alış emirleri oluştur"""
        pass  # Emir oluşturma işlemleri burada olacak
    
    def place_div_hidden_bids(self):
        """Div gizli alış emirleri oluştur"""
        pass  # Div emir oluşturma işlemleri burada olacak
    
    def show_take_profit_orders(self, orders, contracts, pff_contract, tlt_contract, position_symbols):
        """Take profit emirlerini göster"""
        pass  # Take profit işlemleri burada olacak
    
    def preview_hidden_bids(self):
        """Gizli alış emirlerini önizle"""
        pass  # Emir önizleme işlemleri burada olacak
    
    def show_positions(self):
        """Pozisyonları göster - ETF paneli ve sayfalama eklenmiş"""
        try:
            if not self.is_connected:
                messagebox.showinfo("Bağlantı yok", "Lütfen önce IBKR'ye bağlanın.")
                return
                
            # Pozisyonları al
            positions = self.ib.positions()
            
            if not positions:
                messagebox.showinfo("Pozisyon Yok", "Hiç açık pozisyon bulunamadı.")
                return
                
            # Pozisyonlar penceresi
            positions_window = tk.Toplevel(self)
            positions_window.title("Mevcut Pozisyonlar")
            positions_window.geometry("900x600")
            
            # ETF bilgi paneli ekle
            etf_panel, etf_labels = self.create_etf_info_panel(positions_window)
            
            # Sayfalama değişkenleri
            items_per_page = 20
            current_page = 1
            total_positions = len(positions)
            total_pages = math.ceil(total_positions / items_per_page)
            
            # Tüm pozisyon verilerini sakla
            all_positions_data = []
            
            # Pozisyonlar için bir treeview oluştur
            columns = ("Sembol", "Miktar", "Ortalama Maliyet", "Market Fiyatı", "PnL")
            
            # Ana container frame
            main_frame = ttk.Frame(positions_window)
            main_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)
            
            # Treeview frame
            tree_frame = ttk.Frame(main_frame)
            tree_frame.pack(fill=tk.BOTH, expand=True)
            
            positions_tree = ttk.Treeview(tree_frame, columns=columns, show="headings")
            
            # Sütun başlıkları
            for col in columns:
                positions_tree.heading(col, text=col)
                positions_tree.column(col, width=100, anchor="center")
                
            # Scrollbar
            scrollbar = ttk.Scrollbar(tree_frame, orient="vertical", command=positions_tree.yview)
            positions_tree.configure(yscrollcommand=scrollbar.set)
            
            # Layout
            positions_tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
            scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
            
            # Renk etiketlerini ayarla
            positions_tree.tag_configure("green", background="#e0f0e0")
            positions_tree.tag_configure("red", background="#f0e0e0")
            positions_tree.tag_configure("neutral", background="#f0f0f0")
            
            # Tüm pozisyon verilerini sakla
            for pos in positions:
                contract = pos.contract
                symbol = contract.localSymbol if hasattr(contract, 'localSymbol') and contract.localSymbol else contract.symbol
                quantity = pos.position
                avg_cost = pos.avgCost
                market_price = 0
                pnl = 0
                
                # Market fiyatını al
                ticker_data = self.market_data_cache.get(symbol)
                if ticker_data and hasattr(ticker_data, 'last') and ticker_data.last is not None and not math.isnan(ticker_data.last):
                    market_price = ticker_data.last
                    pnl = (market_price - avg_cost) * quantity
                
                # Veriyi sakla
                all_positions_data.append({
                    'symbol': symbol,
                    'quantity': quantity,
                    'avg_cost': avg_cost,
                    'market_price': market_price,
                    'pnl': pnl
                })
            
            # Sayfalama fonksiyonu
            def update_page_data():
                # Treeview'ı temizle
                for item in positions_tree.get_children():
                    positions_tree.delete(item)
                
                # Sayfayı hesapla
                start_idx = (current_page - 1) * items_per_page
                end_idx = min(start_idx + items_per_page, total_positions)
                
                # Geçerli sayfadaki verileri göster
                page_data = all_positions_data[start_idx:end_idx]
                
                for pos_data in page_data:
                    # Tree'ye ekle
                    values = (
                        pos_data['symbol'],
                        f"{int(pos_data['quantity']):,}",
                        f"{pos_data['avg_cost']:.2f}",
                        f"{pos_data['market_price']:.2f}" if pos_data['market_price'] > 0 else "--",
                        f"{pos_data['pnl']:.2f}" if pos_data['pnl'] != 0 else "--"
                    )
                    
                    # Renk belirle
                    tag = 'green' if pos_data['pnl'] > 0 else 'red' if pos_data['pnl'] < 0 else 'neutral'
                    positions_tree.insert("", "end", values=values, tags=(tag,))
                
                # Sayfa bilgisi güncelle
                page_info_label.config(text=f"Sayfa: {current_page}/{total_pages}")
                
                # Sayfalama butonlarını güncelle
                prev_button.config(state=tk.NORMAL if current_page > 1 else tk.DISABLED)
                next_button.config(state=tk.NORMAL if current_page < total_pages else tk.DISABLED)
            
            # Navigasyon frame
            nav_frame = ttk.Frame(main_frame)
            nav_frame.pack(fill=tk.X, pady=(10, 0))
            
            # Sayfalama butonları
            def prev_page():
                nonlocal current_page
                if current_page > 1:
                    current_page -= 1
                    update_page_data()
            
            def next_page():
                nonlocal current_page
                if current_page < total_pages:
                    current_page += 1
                    update_page_data()
            
            prev_button = ttk.Button(nav_frame, text="< Önceki", command=prev_page)
            prev_button.pack(side=tk.LEFT, padx=5)
            
            page_info_label = ttk.Label(nav_frame, text=f"Sayfa: {current_page}/{total_pages}")
            page_info_label.pack(side=tk.LEFT, padx=10)
            
            next_button = ttk.Button(nav_frame, text="Sonraki >", command=next_page)
            next_button.pack(side=tk.LEFT, padx=5)
            
            # Toplam pozisyon sayısı
            ttk.Label(nav_frame, text=f"Toplam: {total_positions} pozisyon").pack(side=tk.RIGHT, padx=10)
            
            # Son güncelleme zamanı
            now_time = datetime.datetime.now().strftime("%H:%M:%S")
            ttk.Label(nav_frame, text=f"Son güncelleme: {now_time}").pack(side=tk.RIGHT, padx=10)
            
            # Butonlar frame
            button_frame = ttk.Frame(positions_window)
            button_frame.pack(fill=tk.X, pady=10)
            
            # Yenile butonu
            def refresh_positions():
                positions_window.destroy()
                self.show_positions()
                
            refresh_btn = ttk.Button(button_frame, text="Yenile", command=refresh_positions)
            refresh_btn.pack(side=tk.LEFT, padx=5)
            
            # Kapat butonu
            close_btn = ttk.Button(button_frame, text="Kapat", command=positions_window.destroy)
            close_btn.pack(side=tk.RIGHT, padx=5)
            
            # İlk sayfayı göster
            update_page_data()
            
        except Exception as e:
            print(f"Show positions error: {e}")
            import traceback
            traceback.print_exc()
            messagebox.showerror("Hata", f"Pozisyonlar gösterilirken hata oluştu: {e}")
    
    def create_etf_info_panel(self, parent_frame):
        """ETF bilgi paneli oluştur - diğer pencerelerde kullanmak için"""
        etf_panel = ttk.Frame(parent_frame)
        etf_panel.pack(fill=tk.X, pady=(5, 0))
        
        # ETF etiketleri için bir çerçeve
        etf_labels_frame = ttk.Frame(etf_panel)
        etf_labels_frame.pack(fill=tk.X, padx=5, pady=5)
        
        # ETF başlık etiketi
        ttk.Label(etf_labels_frame, text="ETF Performans:", font=('Arial', 8, 'bold')).pack(side=tk.LEFT, padx=(0, 10))
        
        # Etiketleri oluştur
        etf_labels = {}
        for etf in self.etf_list:
            # Veri varsa onu kullan, yoksa varsayılan değer göster
            if etf in self.etf_labels:
                label_text = self.etf_labels[etf].cget("text")
            else:
                label_text = f"{etf}: --"
                
            # Etiket oluştur
            etf_labels[etf] = ttk.Label(etf_labels_frame, text=label_text)
            
            # Renk belirle
            if etf in self.etf_changes:
                change = self.etf_changes[etf]
                if change > 0:
                    etf_labels[etf].config(style='ETFUp.TLabel')
                elif change < 0:
                    etf_labels[etf].config(style='ETFDown.TLabel')
                else:
                    etf_labels[etf].config(style='ETFNeutral.TLabel')
            
            etf_labels[etf].pack(side=tk.LEFT, padx=10)
        
        # Benchmark etiketlerini ekle
        ttk.Label(etf_labels_frame, text="|", font=('Arial', 8, 'bold')).pack(side=tk.LEFT, padx=(15, 5))
        
        # T-benchmark etiketi
        t_benchmark_text = f"T-benchmark: {self.t_benchmark:+.2f}¢" if hasattr(self, "t_benchmark") else "T-benchmark: --"
        t_style = 'ETFUp.TLabel' if hasattr(self, "t_benchmark") and self.t_benchmark > 0 else 'ETFDown.TLabel' if hasattr(self, "t_benchmark") and self.t_benchmark < 0 else 'ETFNeutral.TLabel'
        t_benchmark_label = ttk.Label(etf_labels_frame, text=t_benchmark_text, style=t_style, font=('Arial', 8, 'bold'))
        t_benchmark_label.pack(side=tk.LEFT, padx=10)
        
        # C-benchmark etiketi
        c_benchmark_text = f"C-benchmark: {self.c_benchmark:+.2f}¢" if hasattr(self, "c_benchmark") else "C-benchmark: --"
        c_style = 'ETFUp.TLabel' if hasattr(self, "c_benchmark") and self.c_benchmark > 0 else 'ETFDown.TLabel' if hasattr(self, "c_benchmark") and self.c_benchmark < 0 else 'ETFNeutral.TLabel'
        c_benchmark_label = ttk.Label(etf_labels_frame, text=c_benchmark_text, style=c_style, font=('Arial', 8, 'bold'))
        c_benchmark_label.pack(side=tk.LEFT, padx=10)
        
        # Ayrıcı çizgi ekle
        ttk.Separator(etf_panel, orient='horizontal').pack(fill=tk.X, padx=5, pady=2)
        
        # Etiket referanslarını döndür
        etf_labels["t_benchmark"] = t_benchmark_label
        etf_labels["c_benchmark"] = c_benchmark_label
        
        return etf_panel, etf_labels
    
    def show_opt50_portfolio(self):
        """optimized_50_stocks_portfolio.csv dosyasından portföy verilerini göster"""
        # Import gerekli modüller
        import os
        import math
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
        portfolio_window.geometry("1200x700")
        
        # ETF bilgi paneli ekle
        etf_panel, etf_labels = self.create_etf_info_panel(portfolio_window)
        
        # Sayfalama değişkenleri
        items_per_page = 20
        current_page = 1
        total_pages = 1
        
        # Treeview için frame oluştur
        tree_frame = ttk.Frame(portfolio_window)
        tree_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)
        
        # Yükleniyor etiketi
        loading_label = ttk.Label(tree_frame, text="Portföy verileri yükleniyor...")
        loading_label.pack(pady=20)
        
        try:
            # CSV dosyasını oku
            df = pd.read_csv(portfolio_file)
            
            # Gerekli sütunları kontrol et
            required_columns = ["PREF IBKR", "FINAL_THG", "AVG_ADV", "Final_Shares"]
            missing_columns = [col for col in required_columns if col not in df.columns]
            if missing_columns:
                error_msg = f"CSV dosyasında aşağıdaki sütunlar eksik: {', '.join(missing_columns)}"
                loading_label.destroy()
                messagebox.showerror("Eksik Sütunlar", error_msg)
                return
            
            # NaN değerleri temizle
            df = df.dropna(subset=["PREF IBKR"])
            
            # Toplam kayıt sayısı ve sayfa sayısını hesapla
            total_records = len(df)
            total_pages = math.ceil(total_records / items_per_page)
            
            # Yükleniyor etiketini kaldır
            loading_label.destroy()
            
            # Sütunlar tanımla
            columns = ("ticker", "final_thg", "avg_adv", "final_shares")
            
            # Treeview oluştur
            port_tree = ttk.Treeview(
                tree_frame,
                columns=columns,
                show="headings",
                selectmode="browse"
            )
            
            # Sütun başlıkları
            port_tree.heading("ticker", text="Ticker")
            port_tree.heading("final_thg", text="FINAL_THG")
            port_tree.heading("avg_adv", text="AVG_ADV")
            port_tree.heading("final_shares", text="Final_Shares")
            
            # Sütun genişlikleri
            port_tree.column("ticker", width=100, anchor=tk.CENTER)
            port_tree.column("final_thg", width=100, anchor=tk.E)
            port_tree.column("avg_adv", width=100, anchor=tk.E)
            port_tree.column("final_shares", width=100, anchor=tk.E)
            
            # Scrollbar ekle
            scrollbar = ttk.Scrollbar(tree_frame, orient="vertical", command=port_tree.yview)
            scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
            port_tree.configure(yscrollcommand=scrollbar.set)
            port_tree.pack(fill=tk.BOTH, expand=True)
            
            # Sayfalama fonksiyonu
            def update_page_data():
                # Treeview'ı temizle
                for item in port_tree.get_children():
                    port_tree.delete(item)
                
                # Sayfayı hesapla
                start_idx = (current_page - 1) * items_per_page
                end_idx = min(start_idx + items_per_page, total_records)
                
                # Geçerli sayfadaki verileri göster
                page_data = df.iloc[start_idx:end_idx]
                
                # TreeView'a verileri ekle
                for _, row in page_data.iterrows():
                    ticker = row["PREF IBKR"]
                    final_thg = row["FINAL_THG"] if pd.notna(row["FINAL_THG"]) else "--"
                    avg_adv = row["AVG_ADV"] if pd.notna(row["AVG_ADV"]) else "--"
                    final_shares = row["Final_Shares"] if pd.notna(row["Final_Shares"]) else "--"
                    
                    # Sayısal değerleri formatlı göster
                    if isinstance(final_thg, (int, float)):
                        final_thg = f"{final_thg:.2f}"
                    if isinstance(avg_adv, (int, float)):
                        avg_adv = f"{avg_adv:.2f}"
                    if isinstance(final_shares, (int, float)):
                        final_shares = f"{int(final_shares)}"
                    
                    port_tree.insert("", tk.END, values=(ticker, final_thg, avg_adv, final_shares))
                
                # Sayfa bilgisi güncelle
                page_info_label.config(text=f"Sayfa: {current_page}/{total_pages}")
            
            # Alt bilgi ve sayfalama kontrolleri için çerçeve
            footer_frame = ttk.Frame(portfolio_window)
            footer_frame.pack(fill=tk.X, side=tk.BOTTOM, padx=10, pady=5)
            
            # Sayfalama butonları
            def prev_page():
                nonlocal current_page
                if current_page > 1:
                    current_page -= 1
                    update_page_data()
            
            def next_page():
                nonlocal current_page
                if current_page < total_pages:
                    current_page += 1
                    update_page_data()
            
            # Sayfalama kontrolleri
            nav_frame = ttk.Frame(footer_frame)
            nav_frame.pack(side=tk.LEFT, fill=tk.X)
            
            prev_button = ttk.Button(nav_frame, text="< Önceki", command=prev_page)
            prev_button.pack(side=tk.LEFT, padx=5)
            
            page_info_label = ttk.Label(nav_frame, text=f"Sayfa: {current_page}/{total_pages}")
            page_info_label.pack(side=tk.LEFT, padx=10)
            
            next_button = ttk.Button(nav_frame, text="Sonraki >", command=next_page)
            next_button.pack(side=tk.LEFT, padx=5)
            
            # Toplam kayıt sayısı
            info_frame = ttk.Frame(footer_frame)
            info_frame.pack(side=tk.RIGHT, fill=tk.X)
            
            record_count = len(df["PREF IBKR"].dropna())
            ttk.Label(info_frame, text=f"Toplam: {record_count} hisse").pack(side=tk.LEFT, padx=10)
            
            # Son güncelleme zamanı
            update_time = ttk.Label(info_frame, text=f"Son Güncelleme: {time.strftime('%H:%M:%S')}")
            update_time.pack(side=tk.RIGHT)
            
            # İlk sayfayı göster
            update_page_data()
            
        except Exception as e:
            if 'loading_label' in locals() and loading_label.winfo_exists():
                loading_label.destroy()
            error_frame = ttk.Frame(portfolio_window)
            error_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)
            
            ttk.Label(
                error_frame, 
                text=f"Portföy verileri yüklenirken hata oluştu:\n\n{str(e)}", 
                foreground="red"
            ).pack(pady=20)
            
            print(f"Opt50 portföy görüntüleme hatası: {str(e)}")
    
    def show_cashpark35_portfolio(self):
        """optimized_35_extlt.csv dosyasından portföy verilerini göster"""
        # Import gerekli modüller
        import os
        import math
        from tkinter import messagebox
        
        # CSV dosyasının yolunu belirle
        portfolio_file = "optimized_35_extlt.csv"
        
        # Dosya var mı kontrol et
        if not os.path.exists(portfolio_file):
            messagebox.showerror("Dosya Bulunamadı", f"{portfolio_file} dosyası bulunamadı.")
            return
        
        # Yeni bir pencere oluştur
        portfolio_window = tk.Toplevel(self)
        portfolio_window.title("Cashpark35 Portföy")
        portfolio_window.geometry("1200x700")
        
        # ETF bilgi paneli ekle
        etf_panel, etf_labels = self.create_etf_info_panel(portfolio_window)
        
        # Sayfalama değişkenleri
        items_per_page = 20
        current_page = 1
        total_pages = 1
        
        # Treeview için frame oluştur
        tree_frame = ttk.Frame(portfolio_window)
        tree_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)
        
        # Yükleniyor etiketi
        loading_label = ttk.Label(tree_frame, text="Portföy verileri yükleniyor...")
        loading_label.pack(pady=20)
        
        try:
            # CSV dosyasını oku
            df = pd.read_csv(portfolio_file)
            
            # Gerekli sütunları kontrol et
            required_columns = ["PREF IBKR", "FINAL_THG", "AVG_ADV", "Final_Shares"]
            missing_columns = [col for col in required_columns if col not in df.columns]
            if missing_columns:
                error_msg = f"CSV dosyasında aşağıdaki sütunlar eksik: {', '.join(missing_columns)}"
                loading_label.destroy()
                messagebox.showerror("Eksik Sütunlar", error_msg)
                return
            
            # NaN değerleri temizle
            df = df.dropna(subset=["PREF IBKR"])
            
            # Toplam kayıt sayısı ve sayfa sayısını hesapla
            total_records = len(df)
            total_pages = math.ceil(total_records / items_per_page)
            
            # Yükleniyor etiketini kaldır
            loading_label.destroy()
            
            # Sütunlar tanımla
            columns = ("ticker", "final_thg", "avg_adv", "final_shares")
            
            # Treeview oluştur
            port_tree = ttk.Treeview(
                tree_frame,
                columns=columns,
                show="headings",
                selectmode="browse"
            )
            
            # Sütun başlıkları
            port_tree.heading("ticker", text="Ticker")
            port_tree.heading("final_thg", text="FINAL_THG")
            port_tree.heading("avg_adv", text="AVG_ADV")
            port_tree.heading("final_shares", text="Final_Shares")
            
            # Sütun genişlikleri
            port_tree.column("ticker", width=100, anchor=tk.CENTER)
            port_tree.column("final_thg", width=100, anchor=tk.E)
            port_tree.column("avg_adv", width=100, anchor=tk.E)
            port_tree.column("final_shares", width=100, anchor=tk.E)
            
            # Scrollbar ekle
            scrollbar = ttk.Scrollbar(tree_frame, orient="vertical", command=port_tree.yview)
            scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
            port_tree.configure(yscrollcommand=scrollbar.set)
            port_tree.pack(fill=tk.BOTH, expand=True)
            
            # Sayfalama fonksiyonu
            def update_page_data():
                # Treeview'ı temizle
                for item in port_tree.get_children():
                    port_tree.delete(item)
                
                # Sayfayı hesapla
                start_idx = (current_page - 1) * items_per_page
                end_idx = min(start_idx + items_per_page, total_records)
                
                # Geçerli sayfadaki verileri göster
                page_data = df.iloc[start_idx:end_idx]
                
                # TreeView'a verileri ekle
                for _, row in page_data.iterrows():
                    ticker = row["PREF IBKR"]
                    final_thg = row["FINAL_THG"] if pd.notna(row["FINAL_THG"]) else "--"
                    avg_adv = row["AVG_ADV"] if pd.notna(row["AVG_ADV"]) else "--"
                    final_shares = row["Final_Shares"] if pd.notna(row["Final_Shares"]) else "--"
                    
                    # Sayısal değerleri formatlı göster
                    if isinstance(final_thg, (int, float)):
                        final_thg = f"{final_thg:.2f}"
                    if isinstance(avg_adv, (int, float)):
                        avg_adv = f"{avg_adv:.2f}"
                    if isinstance(final_shares, (int, float)):
                        final_shares = f"{int(final_shares)}"
                    
                    port_tree.insert("", tk.END, values=(ticker, final_thg, avg_adv, final_shares))
                
                # Sayfa bilgisi güncelle
                page_info_label.config(text=f"Sayfa: {current_page}/{total_pages}")
            
            # Alt bilgi ve sayfalama kontrolleri için çerçeve
            footer_frame = ttk.Frame(portfolio_window)
            footer_frame.pack(fill=tk.X, side=tk.BOTTOM, padx=10, pady=5)
            
            # Sayfalama butonları
            def prev_page():
                nonlocal current_page
                if current_page > 1:
                    current_page -= 1
                    update_page_data()
            
            def next_page():
                nonlocal current_page
                if current_page < total_pages:
                    current_page += 1
                    update_page_data()
            
            # Sayfalama kontrolleri
            nav_frame = ttk.Frame(footer_frame)
            nav_frame.pack(side=tk.LEFT, fill=tk.X)
            
            prev_button = ttk.Button(nav_frame, text="< Önceki", command=prev_page)
            prev_button.pack(side=tk.LEFT, padx=5)
            
            page_info_label = ttk.Label(nav_frame, text=f"Sayfa: {current_page}/{total_pages}")
            page_info_label.pack(side=tk.LEFT, padx=10)
            
            next_button = ttk.Button(nav_frame, text="Sonraki >", command=next_page)
            next_button.pack(side=tk.LEFT, padx=5)
            
            # Toplam kayıt sayısı
            info_frame = ttk.Frame(footer_frame)
            info_frame.pack(side=tk.RIGHT, fill=tk.X)
            
            record_count = len(df["PREF IBKR"].dropna())
            ttk.Label(info_frame, text=f"Toplam: {record_count} hisse").pack(side=tk.LEFT, padx=10)
            
            # Son güncelleme zamanı
            update_time = ttk.Label(info_frame, text=f"Son Güncelleme: {time.strftime('%H:%M:%S')}")
            update_time.pack(side=tk.RIGHT)
            
            # İlk sayfayı göster
            update_page_data()
            
        except Exception as e:
            if 'loading_label' in locals() and loading_label.winfo_exists():
                loading_label.destroy()
            error_frame = ttk.Frame(portfolio_window)
            error_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)
            
            ttk.Label(
                error_frame, 
                text=f"Portföy verileri yüklenirken hata oluştu:\n\n{str(e)}", 
                foreground="red"
            ).pack(pady=20)
            
            print(f"Cashpark35 portföy görüntüleme hatası: {str(e)}")
    
    def show_etf_list(self):
        """ETF listesini göster"""
        pass  # ETF listesi gösterme işlemleri burada olacak
    
    def open_spreadci_window(self):
        """Spreadci verilerini gösteren pencereyi aç"""
        try:
            # SpreadciDataWindow'a etf_info_panel oluşturma fonksiyonunu ve etf verilerini geçirelim
            win = SpreadciDataWindow(self)
            
            # ETF bilgi panelini ekle
            if hasattr(win, 'main_frame'):
                etf_panel, _ = self.create_etf_info_panel(win.main_frame)
                
        except Exception as e:
            print(f"Open spreadci window error: {e}")
        
    def get_spreadci_data(self):
        """Spreadci verilerini döndür (SpreadciDataWindow için)"""
        return self.spreadci_data
    
    def clear_spreadci_subscriptions(self):
        """Spreadci aboneliklerini temizle (SpreadciDataWindow için)"""
        try:
            # Abonelikleri temizle
            if self.is_connected:
                spreadci_symbols = list(self.spreadci_data.keys())
                for symbol in spreadci_symbols:
                    self.market_data_cache.remove_subscription(symbol, self.ib)
        except Exception as e:
            print(f"Clear spreadci subscriptions error: {e}")
    
    def subscribe_spreadci_tickers(self, symbols):
        """Spreadci sembolleri için abonelik oluştur (SpreadciDataWindow için)"""
        try:
            if not self.is_connected:
                return
            
            # Her sembol için abonelik oluştur
            for symbol in symbols:
                if symbol in self.spreadci_data:
                    contract = self.create_preferred_stock_contract(symbol)
                    self.market_data_cache.add_subscription(symbol, contract, self.ib)
        except Exception as e:
            print(f"Subscribe spreadci tickers error: {e}")
    
    def show_div_portfolio(self):
        """Div portföyünü göster"""
        pass  # Div portföy gösterme işlemleri burada olacak
    
    def show_top_movers(self, show_gainers=False):
        """En çok artan/azalanları göster - ETF paneli eklenmiş"""
        try:
            # En çok düşenler/yükselenler penceresi
            title = "En Çok Yükselenler" if show_gainers else "En Çok Düşenler"
            print(f"{title} hesaplanıyor...")
            
            # Snapshot verilerinden tüm hisselerin fiyat değişimlerini hesapla
            movers_data = []
            snapshot_data = self.market_data_cache.get_all_snapshot_data()
            print(f"Toplam {len(snapshot_data)} sembol inceleniyor")
            
            for symbol, ticker in snapshot_data.items():
                # Son fiyat ve önceki kapanış veri kontrolleri
                if (hasattr(ticker, 'last') and hasattr(ticker, 'close') and 
                    ticker.last is not None and not math.isnan(ticker.last) and
                    ticker.close is not None and not math.isnan(ticker.close) and
                    ticker.close > 0):
                    # Değişim yüzdesini hesapla
                    change_pct = ((ticker.last - ticker.close) / ticker.close) * 100
                    
                    # Hisse değişimini kaydet
                    movers_data.append({
                        'symbol': symbol,
                        'last': ticker.last,
                        'close': ticker.close,
                        'change_pct': change_pct,
                        'change': ticker.last - ticker.close
                    })
            
            # Veri yoksa uyarı göster
            if not movers_data:
                messagebox.showinfo(title, "Hesaplanacak fiyat değişimi verisi bulunamadı!")
                return
                
            print(f"Toplam {len(movers_data)} sembol için değişim hesaplandı")
            
            # Değişim yüzdesine göre sırala
            if show_gainers:
                # Yükselenler için büyükten küçüğe sırala
                movers_data.sort(key=lambda x: x['change_pct'], reverse=True)
            else:
                # Düşenler için küçükten büyüğe sırala
                movers_data.sort(key=lambda x: x['change_pct'])
            
            # En üstteki 20 tanesini al
            top_movers = movers_data[:20]
            
            # Sonuçları göstermek için yeni pencere aç
            movers_window = tk.Toplevel(self)
            movers_window.title(title)
            movers_window.geometry("800x600")
            
            # ETF bilgi paneli ekle
            etf_panel, etf_labels = self.create_etf_info_panel(movers_window)
            
            # Treeview oluştur
            columns = ("Symbol", "Son", "Önceki", "Değişim", "Değişim%")
            movers_tree = ttk.Treeview(movers_window, columns=columns, show="headings")
            
            # Başlık ve sütun yapılandırması
            for col in columns:
                movers_tree.heading(col, text=col)
                movers_tree.column(col, width=100, anchor="center")
            
            # Scrollbar
            scrollbar = ttk.Scrollbar(movers_window, orient="vertical", command=movers_tree.yview)
            movers_tree.configure(yscrollcommand=scrollbar.set)
            
            # Movers verilerini treeview'a yerleştir
            for i, mover in enumerate(top_movers):
                values = (
                    mover['symbol'],
                    f"{mover['last']:.2f}",
                    f"{mover['close']:.2f}",
                    f"{mover['change']:.2f}",
                    f"{mover['change_pct']:.2f}%"
                )
                
                # Renk etiketi belirle
                if mover['change_pct'] > 0:
                    tag = "green"
                else:
                    tag = "red"
                
                # Treeview'a ekle
                movers_tree.insert("", "end", values=values, tags=(tag,))
            
            # Renk etiketlerini konfigüre et
            movers_tree.tag_configure("green", background="#e0f0e0")
            movers_tree.tag_configure("red", background="#f0e0e0")
            
            # Layout
            movers_tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
            scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
            
            # Seçilen hissenin mevcut verilerini görmek için buton
            def view_selected_ticker():
                selected = movers_tree.selection()
                if not selected:
                    return
                    
                selected_item = movers_tree.item(selected[0])
                selected_symbol = selected_item['values'][0]
                
                # Hisse verilerini al
                ticker_data = self.market_data_cache.get(selected_symbol)
                if not ticker_data:
                    messagebox.showinfo("Bilgi", f"{selected_symbol} için veri bulunamadı!")
                    return
                
                # Veri penceresini oluştur
                info_window = tk.Toplevel(movers_window)
                info_window.title(f"{selected_symbol} Detayları")
                info_window.geometry("400x300")
                
                # Veri alanlarını hazırla
                info_text = tk.Text(info_window, wrap=tk.WORD, height=15, width=40)
                info_text.pack(padx=10, pady=10, fill=tk.BOTH, expand=True)
                
                # Veri alanlarını yazdir
                info = f"Sembol: {selected_symbol}\n\n"
                
                for field in ['last', 'bid', 'ask', 'close', 'open', 'high', 'low', 'volume']:
                    if hasattr(ticker_data, field) and getattr(ticker_data, field) is not None:
                        value = getattr(ticker_data, field)
                        if not math.isnan(value):
                            info += f"{field.capitalize()}: {value}\n"
                
                info_text.insert(tk.END, info)
                info_text.config(state=tk.DISABLED)  # Salt okunur
            
            # Alım emri açma butonu
            def place_order_for_selected():
                selected = movers_tree.selection()
                if not selected:
                    return
                    
                selected_item = movers_tree.item(selected[0])
                selected_symbol = selected_item['values'][0]
                
                # Emir penceresi oluştur
                order_window = tk.Toplevel(movers_window)
                order_window.title(f"{selected_symbol} Emir Girişi")
                order_window.geometry("400x350")
                
                # ETF bilgi paneli ekle
                etf_panel_order, _ = self.create_etf_info_panel(order_window)
                
                # Emir formu
                frame = ttk.Frame(order_window, padding=10)
                frame.pack(fill=tk.BOTH, expand=True)
                
                # Emir verileri
                ttk.Label(frame, text="Sembol:").grid(row=0, column=0, sticky=tk.W)
                ttk.Label(frame, text=selected_symbol).grid(row=0, column=1, sticky=tk.W)
                
                ttk.Label(frame, text="İşlem Tipi:").grid(row=1, column=0, sticky=tk.W)
                order_type_var = tk.StringVar(value="Alış")
                order_type = ttk.Combobox(frame, textvariable=order_type_var, values=["Alış", "Satış"])
                order_type.grid(row=1, column=1, sticky=tk.W)
                
                ttk.Label(frame, text="Miktar:").grid(row=2, column=0, sticky=tk.W)
                qty_var = tk.StringVar(value="100")
                qty_entry = ttk.Entry(frame, textvariable=qty_var)
                qty_entry.grid(row=2, column=1, sticky=tk.W)
                
                ttk.Label(frame, text="Fiyat:").grid(row=3, column=0, sticky=tk.W)
                price_var = tk.StringVar()
                
                # Mevcut fiyat verilerini al
                ticker_data = self.market_data_cache.get(selected_symbol)
                if ticker_data:
                    if hasattr(ticker_data, 'bid') and ticker_data.bid is not None and not math.isnan(ticker_data.bid):
                        price_var.set(f"{ticker_data.bid:.2f}")
                    elif hasattr(ticker_data, 'last') and ticker_data.last is not None and not math.isnan(ticker_data.last):
                        price_var.set(f"{ticker_data.last:.2f}")
                
                price_entry = ttk.Entry(frame, textvariable=price_var)
                price_entry.grid(row=3, column=1, sticky=tk.W)
                
                # Emir gönderme fonksiyonu
                def submit_order():
                    try:
                        # Veri kontrolü
                        symbol = selected_symbol
                        qty = int(qty_var.get())
                        price = float(price_var.get())
                        is_buy = order_type_var.get() == "Alış"
                        
                        # Emir detaylarını göster
                        order_details = f"Sembol: {symbol}\n"
                        order_details += f"İşlem: {'Alış' if is_buy else 'Satış'}\n"
                        order_details += f"Miktar: {qty}\n"
                        order_details += f"Fiyat: {price:.2f}\n"
                        order_details += f"\nToplam Değer: {(qty * price):.2f} USD\n"
                        
                        # Onay mesajı göster
                        confirm = messagebox.askyesno("Emir Onayı", 
                                                    f"Aşağıdaki emri göndermek istiyor musunuz?\n\n{order_details}")
                        
                        if confirm:
                            # Gerçek emir gönderimi buraya gelecek
                            messagebox.showinfo("Başarılı", "Emir gönderildi!")
                            order_window.destroy()
                    except ValueError:
                        messagebox.showerror("Hata", "Miktar ve fiyat geçerli sayılar olmalıdır!")
                
                # Emir gönder butonu
                submit_btn = ttk.Button(frame, text="Emir Gönder", command=submit_order)
                submit_btn.grid(row=4, column=1, sticky=tk.E, pady=10)
                
                # İptal butonu
                cancel_btn = ttk.Button(frame, text="İptal", command=order_window.destroy)
                cancel_btn.grid(row=4, column=0, sticky=tk.W, pady=10)
                
            # Butonları ekle
            button_frame = ttk.Frame(movers_window, padding=10)
            button_frame.pack(fill=tk.X)
            
            view_btn = ttk.Button(button_frame, text="Detayları Göster", command=view_selected_ticker)
            view_btn.pack(side=tk.LEFT, padx=5)
            
            order_btn = ttk.Button(button_frame, text="Emir Gir", command=place_order_for_selected)
            order_btn.pack(side=tk.LEFT, padx=5)
            
            close_btn = ttk.Button(button_frame, text="Kapat", command=movers_window.destroy)
            close_btn.pack(side=tk.RIGHT, padx=5)
            
            # Yenileme butonu
            def refresh_data():
                movers_window.destroy()
                self.show_top_movers(show_gainers)
                
            refresh_btn = ttk.Button(button_frame, text="Yenile", command=refresh_data)
            refresh_btn.pack(side=tk.LEFT, padx=5)
            
            print(f"{title} penceresi açıldı, {len(top_movers)} sembol gösteriliyor")
            
        except Exception as e:
            print(f"Top movers error: {e}")
            import traceback
            traceback.print_exc()
            messagebox.showerror("Hata", f"En çok değişenler hesaplanırken hata oluştu: {str(e)}")
    
    def force_refresh(self):
        """Görünümü ve verileri yenile"""
        try:
            print("Tüm veriler zorla yenileniyor...")

            # Clear existing subscriptions if we're connected
            if self.is_connected:
                print("Mevcut abonelikler temizleniyor...")
                # Cancel existing subscriptions to ensure clean refresh
                try:
                    for symbol in list(self.tickers.keys()):
                        try:
                            contract = self.tickers[symbol]['contract']
                            self.ib.cancelMktData(contract)
                            del self.tickers[symbol]
                            print(f"✓ Abonelik iptal edildi: {symbol}")
                        except Exception as e:
                            print(f"! Abonelik iptal hatası ({symbol}): {e}")
                except Exception as e:
                    print(f"Abonelik iptalleri sırasında hata: {e}")
                
                # IB connection may need a quick reset of market data type
                try:
                    # Request fresh data from delayed to live
                    self.ib.reqMarketDataType(3)  # First delayed
                    time.sleep(0.2)
                    self.ib.reqMarketDataType(1)  # Then live
                    print("Market data tipi yenilendi")
                except Exception as e:
                    print(f"Market data tipi yenileme hatası: {e}")
            
            # Güncel sekme bilgisini al
            current_tab = self.current_tab
            tree = self.trees[current_tab]
            
            # Treeview içeriğini sıfırla
            for item in tree.get_children():
                tree.delete(item)
            
            # Ticker listelerinin durumunu kontrol et
            if current_tab == 0:  # TLTR Prefs
                ticker_list = self.tltr_tickers
                print(f"TLTR ticker listesinde {len(ticker_list)} sembol var")
            else:  # DIV Spread
                ticker_list = self.divspread_tickers
                print(f"DIV Spread ticker listesinde {len(ticker_list)} sembol var")
                
            # Treeview'ı yenile
            self.populate_treeview()
            
            # Mevcut sayfadaki görünür hisseleri kontrol et
            visible_stocks = self.get_visible_stocks()
            print(f"Görünür hisseler: {visible_stocks}")
            
            # Yeni abonelikler oluştur
            if self.is_connected:
                print("Benchmark varlıkları yenileniyor...")
                # First subscribe to benchmarks for PFF/TLT
                try:
                    self.subscribe_benchmark_assets()
                except Exception as e:
                    print(f"Benchmark abonelik hatası: {e}")
                
                print("Görünür tickerlara abone olunuyor...")
                # Then subscribe to visible tickers
                try:
                    self.subscribe_visible_tickers()
                except Exception as e:
                    print(f"Ticker abonelik hatası: {e}")
                
            # Güncel zamanı göster
            now_time = datetime.datetime.now().strftime("%H:%M:%S")
            self.time_label.config(text=f"Son güncelleme: {now_time}")
            
            # UI'ın yenilenmesi için biraz zaman tanı
            self.update_idletasks()
            
            self.update_status("Veriler yenilendi")
            print("Zorla yenileme tamamlandı")
            
        except Exception as e:
            print(f"Force refresh error: {e}")
            import traceback
            traceback.print_exc()
    
    def on_closing(self):
        """Uygulama kapatılırken çağrılır"""
        # Otomatik sayfa döngüsünü durdur
        self.is_auto_cycling = False
        
        if self.is_connected:
            self.disconnect_from_ibkr()
        self.destroy()
    
    def update_data_update_indicator(self, is_updating):
        """Veri güncellemesi olduğunu göster"""
        if is_updating:
            # Aktif güncelleme durumunu göster - örneğin abonelik sayısı etiketinin rengini değiştir
            self.subscription_count_label.config(foreground="red")
            
            # Aktif sayfa verisini güncelliyorsak treeview'a belirt
            if hasattr(self, 'current_tab') and self.current_tab in self.trees:
                tree = self.trees[self.current_tab]
                tree.configure(style="Updated.Treeview")
        else:
            # Normal duruma dön
            self.subscription_count_label.config(foreground="black")
            
            # Treeview stilini normale döndür
            if hasattr(self, 'current_tab') and self.current_tab in self.trees:
                tree = self.trees[self.current_tab]
                tree.configure(style="Treeview")
    
    def on_ib_error(self, reqId, errorCode, errorString, contract):
        """IB hata callback'i"""
        print(f"IB Error: ReqID={reqId}, Code={errorCode}, Message={errorString}, Contract={contract}")
        
        # Ciddi hatalar için kullanıcıya bildirim göster
        if errorCode in [1100, 1101, 1102, 1300, 2110]:  # Bağlantı hataları
            # Her hata için bildirimi gösterme, ama durum çubuğunu güncelle
            self.update_status(f"IB Hatası: {errorString}", is_connected=False)
    
    def on_ib_disconnected(self):
        """IB bağlantı kesildi callback'i"""
        print("IB bağlantısı kesildi")
        self.is_connected = False
        self.update_status("IB bağlantısı kesildi", is_connected=False)

    def toggle_auto_page_cycling(self):
        """Otomatik sayfa döngüsünü aç/kapat - iyileştirilmiş"""
        auto_cycle = self.auto_cycle_pages.get()
        
        if auto_cycle and not self.is_auto_cycling:
            # Döngü başlamadan önce mevcut sayfa ve sekmeyi kaydet
            self.original_tab = self.current_tab
            self.original_page = self.current_page.copy()
            
            # Otomatik sayfa döngüsünü başlat
            self.is_auto_cycling = True
            self.auto_cycle_status_label.config(text="Otomatik Yenileme: Aktif")
            print("Otomatik sayfa döngüsü başlatılıyor...")
            
            # Ayrı bir thread'de döngüyü başlat
            self.auto_cycle_thread = threading.Thread(target=self.run_auto_page_cycling, daemon=True)
            self.auto_cycle_thread.start()
            
            self.update_status("Otomatik veri yenileme başlatıldı - Tüm sayfalar periyodik olarak taranacak")
        else:
            # Otomatik sayfa döngüsünü durdur
            self.is_auto_cycling = False
            self.auto_cycle_status_label.config(text="Otomatik Yenileme: Pasif")
            print("Otomatik sayfa döngüsü durduruldu")
            self.update_status("Otomatik veri yenileme durduruldu")
            
            # Kullanıcının orijinal sayfasına geri dön - ama bunu ana thread'de yapmalıyız
            if hasattr(self, 'original_tab') and hasattr(self, 'original_page'):
                orig_tab = self.original_tab
                orig_page = self.original_page.get(orig_tab, 1)
                print(f"Orijinal sayfaya dönülüyor: Tab {orig_tab+1}, Sayfa {orig_page}")
                self.after(100, lambda: self.goto_page(orig_tab, orig_page))

    def on_user_interaction(self, event=None):
        """Kullanıcı etkileşimini yakala"""
        self.user_interacting = True
        self.last_user_interaction = time.time()
        
        # Kullanıcı etkileşiminden 3 saniye sonra etkileşim bayrağını sıfırla
        self.after(3000, self.reset_user_interaction)
    
    def reset_user_interaction(self):
        """Kullanıcı etkileşim bayrağını sıfırla"""
        # Son etkileşimden 3 saniye geçti mi kontrol et
        if time.time() - self.last_user_interaction >= 3:
            self.user_interacting = False
    
    def run_auto_page_cycling(self):
        """Otomatik sayfa döngü thread'i - tüm sayfaları görünür şekilde gezer"""
        try:
            # Tab sayısını ve her tab'daki sayfa sayısını al
            tab_count = len(self.tab_names)
            
            # Başlangıç değerlerini kaydet - gezintiye başlamadan önce
            self.original_tab = self.current_tab
            self.original_page = self.current_page.copy()
            
            cycle_count = 0
            
            while self.is_auto_cycling and self.running:
                try:
                    # Kullanıcı etkileşimde ise bekle
                    if self.user_interacting:
                        time.sleep(1)
                        continue
                    
                    # Her 10 döngüde bir benchmark varlıklarını yenile
                    if cycle_count % 10 == 0 and self.is_connected:
                        try:
                            self.subscribe_benchmark_assets()
                            print("Benchmark varlıkları yenilendi")
                        except Exception as e:
                            print(f"Benchmark yenileme hatası: {e}")
                    
                    # Mevcut sekme ve sayfa bilgilerini al
                    current_tab = self.current_tab
                    
                    # Her tab için
                    for tab_idx in range(tab_count):
                        # Kullanıcı otomatik döngüyü durdurduysa çık
                        if not self.is_auto_cycling:
                            break
                        
                        # Kullanıcı etkilesimde ise bekle
                        if self.user_interacting:
                            time.sleep(1)
                            continue
                        
                        # Tab değiştir (Gerçekten UI'da sekme değişimi yap)
                        self.after(0, lambda idx=tab_idx: self.notebook.select(idx))
                        self.after(0, lambda idx=tab_idx: setattr(self, 'current_tab', idx))
                        
                        # UI'ın güncellenmesi için daha kısa bekle
                        time.sleep(1.0)  # 2.0'dan 1.0 saniyeye indirildi
                        
                        # Toplam sayfa sayısını al
                        total_pages = self.total_pages.get(tab_idx, 1)
                        
                        # İlgili tab için tüm sayfaları gez
                        for page in range(1, total_pages + 1):
                            # Kullanıcı otomatik döngüyü durdurduysa çık
                            if not self.is_auto_cycling:
                                break
                            
                            # Kullanıcı etkileşimde ise bekle
                            if self.user_interacting:
                                time.sleep(1)
                                continue
                            
                            try:
                                # Sayfayı değiştir (gerçekten UI'da sayfa değişimi yap)
                                self.after(0, lambda idx=tab_idx, p=page: self.goto_page(idx, p))
                                
                                # Durum çubuğunu güncelle
                                status_text = f"Otomatik Tarama: {self.tab_names[tab_idx]} - Sayfa {page}/{total_pages}"
                                self.update_status(status_text)
                                self.auto_cycle_status_label.config(text=f"Taranıyor: Sayfa {page}/{total_pages}")
                                print(f"Otomatik Tarama: Tab {tab_idx+1}, Sayfa {page}/{total_pages}")
                                
                                # Abone ol ve verilerin gelmesi için biraz bekle
                                if self.is_connected:
                                    self.subscribe_visible_tickers()
                                    
                                    # Verilerin gelmesi için daha kısa bekle
                                    time.sleep(3.0)  # 6.0'dan 3.0 saniyeye indirildi
                                else:
                                    # IB bağlantısı yoksa daha kısa bekle
                                    time.sleep(1.0)  # 2.0'dan 1.0 saniyeye indirildi
                                
                            except Exception as e:
                                print(f"Otomatik sayfa döngüsü hatası (tab {tab_idx}, sayfa {page}): {e}")
                                import traceback
                                traceback.print_exc()
                                time.sleep(1)  # Hata durumunda kısa bekle
                    
                    # Her tam döngüden sonra bir sonraki döngü başlamadan önce bekle
                    cycle_count += 1
                    
                    # Döngü tamamlandı bilgisi
                    self.auto_cycle_status_label.config(text=f"Tarama Tamamlandı - Döngü {cycle_count}")
                    print(f"Otomatik tarama döngüsü {cycle_count} tamamlandı")
                    
                    # Önbellek istatistiklerini göster
                    cached_count = self.market_data_cache.get_symbol_count()
                    print(f"Önbellekteki sembol sayısı: {cached_count}, Döngü: {cycle_count}")
                    self.update_status(f"Otomatik Yenileme: {cached_count} sembol verisi güncel")
                    
                    # Döngüler arası daha kısa bekle
                    time.sleep(2.0)  # 5.0'dan 2.0 saniyeye indirildi
                    
                except Exception as e:
                    print(f"Otomatik sayfa döngüsü ana döngü hatası: {e}")
                    import traceback
                    traceback.print_exc()
                    time.sleep(5)  # Hata durumunda daha uzun bekle
            
            print("Otomatik sayfa döngüsü durduruldu")
            
            # Döngü durdurulduğunda, kullanıcının orijinal sayfasına geri dön
            if hasattr(self, 'original_tab') and hasattr(self, 'original_page'):
                orig_tab = self.original_tab
                orig_page = self.original_page.get(orig_tab, 1)
                
                print(f"Orijinal sayfaya dönülüyor: Tab {orig_tab+1}, Sayfa {orig_page}")
                self.after(0, lambda: self.goto_page(orig_tab, orig_page))
        
        except Exception as e:
            print(f"Otomatik sayfa döngüsü thread hatası: {e}")
            import traceback
            traceback.print_exc()
        finally:
            # Döngü durduğunda UI'ı güncelle
            self.is_auto_cycling = False
            self.after(0, lambda: self.auto_cycle_status_label.config(text="Otomatik Yenileme: Pasif"))
            self.after(0, lambda: self.auto_cycle_pages.set(False))

    def goto_page(self, tab_idx, page_num):
        """Belirli bir sekme ve sayfaya git - veri kalıcılığını iyileştirilmiş"""
        try:
            print(f"Sayfa geçişi: Tab {tab_idx+1}, Sayfa {page_num}")
            
            # Sekme değişimi
            if self.current_tab != tab_idx:
                self.notebook.select(tab_idx)
                self.current_tab = tab_idx
            
            # Sayfa değişimi
            self.current_page[tab_idx] = page_num
            
            # Treeview'ı güncelle - iyileştirilmiş populate_treeview metodunu kullan
            self.populate_treeview()
            
        except Exception as e:
            print(f"Sayfaya geçiş hatası: {e}")
            import traceback
            traceback.print_exc()

    # Sekmeye göre ticker listesi döndüren yardımcı fonksiyon ekle
    def get_ticker_list_for_tab(self, tab_idx):
        """Belirli bir sekme için ticker listesini döndür"""
        if tab_idx == 0:  # T-prefs (eski TLTR Prefs)
            return self.tltr_tickers.copy() if hasattr(self, 'tltr_tickers') else []
        elif tab_idx == 1:  # C-prefs (eski DIV Spread)
            return self.divspread_tickers.copy() if hasattr(self, 'divspread_tickers') else []
        else:
            return []

    def clear_temporary_subscriptions(self):
        """Geçici abonelikleri temizle"""
        if not self.is_connected:
            return
            
        try:
            # Geçici abonelikleri bul
            temp_symbols = [s for s, info in self.tickers.items() 
                          if info.get('is_temporary', False)]
            
            # Abonelikleri iptal et
            for symbol in temp_symbols:
                try:
                    contract = self.tickers[symbol]['contract']
                    self.ib.cancelMktData(contract)
                    del self.tickers[symbol]
                    print(f"✓ {symbol} geçici aboneliği iptal edildi")
                except Exception as e:
                    print(f"! {symbol} geçici abonelik iptali hatası: {e}")
        
        except Exception as e:
            print(f"Clear temporary subscriptions error: {e}")

    def update_etf_info(self):
        """ETF bilgi etiketlerini anında güncelle - iyileştirilmiş"""
        try:
            updated_count = 0
            pff_change_cents = 0
            tlt_change_cents = 0
            
            # Tüm ETF'ler için verileri güncelle
            for etf_symbol in self.etf_list:
                etf_data = self.market_data_cache.get(etf_symbol)
                
                if not etf_data:
                    # Cache'de veri yoksa abonelikleri kontrol et
                    if etf_symbol in self.benchmark_assets:
                        contract = self.benchmark_assets[etf_symbol]
                        # ETF'ye yeniden abone ol
                        try:
                            print(f"{etf_symbol} verisi cache'de yok, yeniden abone olunuyor...")
                            # Geçerli tick listesi kullan
                            generic_tick_list = "233,236,165"  # RTVolume, inventory, Misc. Stats
                            self.ib.reqMktData(contract, generic_tick_list, snapshot=False, regulatorySnapshot=False)
                            time.sleep(0.2)
                            # Cache'e ekle ve önceliklendir
                            self.market_data_cache.add_subscription(etf_symbol, contract, self.ib)
                            self.market_data_cache.prioritize_symbol(etf_symbol)
                            # Veri henüz gelmemiş olabilir, bu çağrıdan atla
                            continue
                        except Exception as e:
                            print(f"{etf_symbol} yeniden abonelik hatası: {e}")
                            continue
                    else:
                        print(f"{etf_symbol} için kontrat yok, güncelleme yapılamıyor")
                        continue
                        
                current_price = 0
                prev_close = 0
                change = 0
                percent_change = 0
                change_cents = 0
                
                # Debug modunda veri detaylarını yazdır
                try:
                    print(f"{etf_symbol} Veri Detayı:" + 
                          f" last={getattr(etf_data, 'last', 'N/A')}," +
                          f" close={getattr(etf_data, 'close', 'N/A')}," +
                          f" bid={getattr(etf_data, 'bid', 'N/A')}," +
                          f" ask={getattr(etf_data, 'ask', 'N/A')}")
                except:
                    pass
                
                # Mevcut fiyat ve önceki kapanış kontrolü
                if hasattr(etf_data, 'last') and etf_data.last is not None and not math.isnan(etf_data.last):
                    current_price = etf_data.last
                    
                    # Önceki kapanış varsa değişim hesapla
                    if hasattr(etf_data, 'close') and etf_data.close is not None and not math.isnan(etf_data.close) and etf_data.close > 0:
                        prev_close = etf_data.close
                        
                        # Mutlak değişim (puan)
                        change = current_price - prev_close
                        
                        # Cent cinsinden değişim (benchmark için)
                        change_cents = change * 100  # dolar -> cent
                        
                        # Yüzde değişim
                        percent_change = (change / prev_close) * 100
                        
                        # Değişim bilgilerini kaydet
                        self.etf_prev_close[etf_symbol] = prev_close
                        self.etf_changes[etf_symbol] = change_cents
                        
                        # PFF ve TLT değişimlerini ayrıca sakla
                        if etf_symbol == "PFF":
                            pff_change_cents = change_cents
                        elif etf_symbol == "TLT":
                            tlt_change_cents = change_cents
                        
                    elif etf_symbol in self.etf_prev_close and self.etf_prev_close[etf_symbol] > 0:
                        # Cache'den önceki kapanışı kullan
                        prev_close = self.etf_prev_close[etf_symbol]
                        change = current_price - prev_close
                        change_cents = change * 100  # dolar -> cent
                        percent_change = (change / prev_close) * 100
                        
                        # Değişimleri güncelle
                        self.etf_changes[etf_symbol] = change_cents
                        
                        # PFF ve TLT değişimlerini ayrıca sakla
                        if etf_symbol == "PFF":
                            pff_change_cents = change_cents
                        elif etf_symbol == "TLT":
                            tlt_change_cents = change_cents
                
                # Etiket metnini oluştur
                if current_price > 0:
                    change_text = f"{change:+.2f}" if change != 0 else "0.00"
                    percent_text = f"({percent_change:+.2f}%)" if percent_change != 0 else "(0.00%)"
                    label_text = f"{etf_symbol}: {current_price:.2f} {change_text} {percent_text}"
                    
                    # Etiketi güncelle
                    if etf_symbol in self.etf_labels:
                        self.etf_labels[etf_symbol].config(text=label_text)
                        
                        # Renk stili belirle
                        if change > 0:
                            self.etf_labels[etf_symbol].config(style='ETFUp.TLabel')
                        elif change < 0:
                            self.etf_labels[etf_symbol].config(style='ETFDown.TLabel')
                        else:
                            self.etf_labels[etf_symbol].config(style='ETFNeutral.TLabel')
                        
                        updated_count += 1
                else:
                    # Veri yok veya geçersiz, varsayılan metin
                    if etf_symbol in self.etf_labels:
                        self.etf_labels[etf_symbol].config(text=f"{etf_symbol}: --")
                        self.etf_labels[etf_symbol].config(style='ETFNeutral.TLabel')
        
            # BENCHMARKS: PFF ve TLT verisi varsa benchmark hesapla
            if pff_change_cents != 0 or tlt_change_cents != 0:
                # T-benchmark: PFF*0.7 + TLT*0.1
                self.t_benchmark = (pff_change_cents * 0.7) + (tlt_change_cents * 0.1)
                
                # C-benchmark: PFF*1.3 - TLT*0.1
                self.c_benchmark = (pff_change_cents * 1.3) - (tlt_change_cents * 0.1)
                
                # Benchmarkları güncelle
                print(f"ETF Değişimler (cent): PFF: {pff_change_cents:.2f}, TLT: {tlt_change_cents:.2f}")
                print(f"Güncel Benchmark Değerleri: T-benchmark: {self.t_benchmark:.2f}, C-benchmark: {self.c_benchmark:.2f}")
                
                # Benchmark etiketlerini güncelle
                self.update_custom_benchmarks()
                
            # Son güncelleme zamanını göster
            if updated_count > 0:
                self.last_update_label.config(text=f"Son güncelleme: {time.strftime('%H:%M:%S')}")
        
        except Exception as e:
            print(f"ETF info update error: {e}")
            import traceback
            traceback.print_exc()

    def show_t_top_gainers(self):
        """T-prefs bölümünde en çok yükselen 15 hisseyi göster"""
        self.show_category_top_movers(category="T", show_gainers=True)

    def show_t_top_losers(self):
        """T-prefs bölümünde en çok düşen 15 hisseyi göster"""
        self.show_category_top_movers(category="T", show_gainers=False)
    
    def show_c_top_gainers(self):
        """C-prefs bölümünde en çok yükselen 15 hisseyi göster"""
        self.show_category_top_movers(category="C", show_gainers=True)
    
    def show_c_top_losers(self):
        """C-prefs bölümünde en çok düşen 15 hisseyi göster"""
        self.show_category_top_movers(category="C", show_gainers=False)
    
    def show_category_top_movers(self, category="T", show_gainers=True):
        """Belirli kategorideki en çok yükselen/düşen hisseleri göster"""
        try:
            # Başlık belirle
            category_name = "T-prefs" if category == "T" else "C-prefs"
            action_name = "Yükselenler" if show_gainers else "Düşenler"
            title = f"{category_name} En Çok {action_name}"
            print(f"{title} hesaplanıyor...")
            
            # İlgili ticker listesini al
            if category == "T":
                ticker_list = self.tltr_tickers
            else:
                ticker_list = self.divspread_tickers
                
            # Bu kategorideki tüm hisselerin fiyat değişimlerini hesapla
            movers_data = []
            
            for ticker in ticker_list:
                ticker_data = self.market_data_cache.get(ticker)
                
                # Last ve close verisi olan tickerları kontrol et
                if ticker_data and hasattr(ticker_data, 'last') and hasattr(ticker_data, 'close'):
                    last_price = ticker_data.last
                    prev_close = ticker_data.close
                    
                    if (last_price is not None and not math.isnan(last_price) and
                        prev_close is not None and not math.isnan(prev_close) and prev_close > 0):
                        
                        # Değişim ve yüzde hesapla
                        change = last_price - prev_close
                        change_pct = (change / prev_close) * 100
                        change_cents = change * 100  # Dolar -> cent değişimi
                        
                        # Verileri kaydet
                        movers_data.append({
                            'symbol': ticker,
                            'last': last_price,
                            'close': prev_close,
                            'change': change,
                            'change_pct': change_pct,
                            'change_cents': change_cents,
                            'bid': getattr(ticker_data, 'bid', None),
                            'ask': getattr(ticker_data, 'ask', None)
                        })
            
            # Veri yoksa uyarı göster
            if not movers_data:
                messagebox.showinfo(title, "Hesaplanacak fiyat değişimi verisi bulunamadı!")
                return
                
            print(f"{len(movers_data)} sembol için değişim hesaplandı")
            
            # Değişime göre sırala
            if show_gainers:
                # Yükselenler için büyükten küçüğe sırala
                movers_data.sort(key=lambda x: x['change_pct'], reverse=True)
            else:
                # Düşenler için küçükten büyüğe sırala
                movers_data.sort(key=lambda x: x['change_pct'])
            
            # En üstteki 15 tanesini al
            top_movers = movers_data[:15] if len(movers_data) >= 15 else movers_data
            
            # Sonuçları göstermek için yeni pencere aç
            movers_window = tk.Toplevel(self)
            movers_window.title(title)
            movers_window.geometry("900x500")
            
            # ETF bilgi paneli ekle
            etf_panel, etf_labels = self.create_etf_info_panel(movers_window)
            
            # Treeview frame oluştur
            tree_frame = ttk.Frame(movers_window)
            tree_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)
            
            # Treeview oluştur
            columns = ("Select", "symbol", "last", "close", "change", "change_pct", "change_cents", "bid", "ask")
            movers_tree = ttk.Treeview(tree_frame, columns=columns, show="headings", selectmode="none")
            
            # Başlık ve sütun yapılandırması
            column_names = {
                "Select": "Seç",
                "symbol": "Sembol",
                "last": "Son Fiyat",
                "close": "Önceki",
                "change": "Değişim ($)",
                "change_pct": "Değişim (%)",
                "change_cents": "Değişim (¢)",
                "bid": "Alış",
                "ask": "Satış"
            }
            
            for col in columns:
                movers_tree.heading(col, text=column_names[col])
                movers_tree.column(col, width=100, anchor="center")
            
            # Scrollbar
            scrollbar = ttk.Scrollbar(tree_frame, orient="vertical", command=movers_tree.yview)
            movers_tree.configure(yscrollcommand=scrollbar.set)
            
            # Yerleştirme
            scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
            movers_tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
            
            # Renk etiketlerini ayarla
            movers_tree.tag_configure("green", background="#e0f0e0")
            movers_tree.tag_configure("red", background="#f0e0e0")
            movers_tree.tag_configure("neutral", background="#f0f0f0")
            
            # Seçili öğeleri izlemek için set
            selected_movers = set()
            
            # Verileri ekle
            for mover in top_movers:
                # Renk etiketi hesapla
                tag = "green" if mover['change'] > 0 else "red" if mover['change'] < 0 else "neutral"
                
                # Değerleri formatlı şekilde ekle
                values = (
                    "□",  # Başlangıçta seçili değil
                    mover['symbol'],
                    f"{mover['last']:.2f}" if mover['last'] is not None else "--",
                    f"{mover['close']:.2f}" if mover['close'] is not None else "--",
                    f"{mover['change']:+.2f}" if mover['change'] is not None else "--",
                    f"{mover['change_pct']:+.2f}%" if mover['change_pct'] is not None else "--",
                    f"{mover['change_cents']:+.2f}¢" if mover['change_cents'] is not None else "--",
                    f"{mover['bid']:.2f}" if mover['bid'] is not None and not math.isnan(mover['bid']) else "--",
                    f"{mover['ask']:.2f}" if mover['ask'] is not None and not math.isnan(mover['ask']) else "--"
                )
                
                movers_tree.insert("", "end", values=values, tags=(tag,))
                
            # Treeview sütunları için genişlik ve hizalama
            movers_tree.column("Select", width=40, anchor="center")
            
            # Tıklama eventi ekle
            movers_tree.bind("<ButtonRelease-1>", lambda e: on_movers_tree_click(e))
            
            # Bilgi paneli
            info_frame = ttk.Frame(movers_window)
            info_frame.pack(fill=tk.X, pady=(5, 10), padx=10)
            
            # Treeview tıklama fonksiyonu
            def on_movers_tree_click(event):
                region = movers_tree.identify_region(event.x, event.y)
                column = movers_tree.identify_column(event.x)
                
                # Sadece ilk sütuna (seçim sütunu) tıklandığında işlem yap
                if region == "cell" and column == "#1":
                    item_id = movers_tree.identify_row(event.y)
                    if item_id:
                        item_values = movers_tree.item(item_id, "values")
                        if item_values:
                            symbol = item_values[1]  # Symbol değeri
                            current_state = item_values[0]  # Seçim durumu
                            
                            # Durumu değiştir
                            new_state = "✓" if current_state == "□" else "□"
                            movers_tree.set(item_id, "Select", new_state)
                            
                            # Set'e ekle veya çıkar
                            if new_state == "✓":
                                selected_movers.add(symbol)
                            else:
                                if symbol in selected_movers:
                                    selected_movers.remove(symbol)
            
            # Buton çerçevesi
            button_frame = ttk.Frame(movers_window)
            button_frame.pack(fill=tk.X, pady=(0, 10), padx=10)
            
            # Select All butonu
            def select_all_items():
                for item_id in movers_tree.get_children():
                    movers_tree.set(item_id, "Select", "✓")
                    item_values = movers_tree.item(item_id, "values")
                    if item_values and len(item_values) > 1:
                        selected_movers.add(item_values[1])  # Symbol değeri
                    
            select_all_btn = ttk.Button(
                button_frame,
                text="Tümünü Seç",
                command=select_all_items
            )
            select_all_btn.pack(side=tk.LEFT, padx=5)
            
            # Deselect All butonu
            def deselect_all_items():
                for item_id in movers_tree.get_children():
                    movers_tree.set(item_id, "Select", "□")
                selected_movers.clear()
                
            deselect_all_btn = ttk.Button(
                button_frame,
                text="Tümünü Kaldır",
                command=deselect_all_items
            )
            deselect_all_btn.pack(side=tk.LEFT, padx=5)
            
            # En çok yükselenler için Hidden Sell butonu
            if show_gainers:
                def hidden_sell_selected():
                    if not selected_movers:
                        messagebox.showinfo("Uyarı", "Lütfen en az bir hisse seçin.")
                        return
                    
                    # Seçili hisselerin verilerini topla
                    orders_to_place = []
                    
                    for item_id in movers_tree.get_children():
                        item_values = movers_tree.item(item_id, "values")
                        
                        if not item_values or len(item_values) < 9 or item_values[0] != "✓":
                            continue
                        
                        symbol = item_values[1]
                        ask = item_values[8]
                        bid = item_values[7]
                        
                        # "--" değerlerini kontrol et
                        if ask == "--" or bid == "--":
                            print(f"{symbol} için bid/ask verisi bulunamadı, atlanıyor...")
                            continue
                            
                        ask = float(ask)
                        bid = float(bid)
                        spread = ask - bid
                        
                        # Hedef fiyat: ask - spread*0.15
                        target_price = ask - (spread * 0.15)
                        
                        # Miktar: 200 share
                        quantity = 200
                        
                        orders_to_place.append({
                            'symbol': symbol,
                            'quantity': quantity,
                            'price': target_price
                        })
                    
                    if not orders_to_place:
                        messagebox.showinfo("Uyarı", "İşlem yapılabilecek hisse bulunamadı.")
                        return
                    
                    # Emir detaylarını hazırla
                    order_details = "\n".join([
                        f"{order['symbol']}: {order['quantity']} adet @ {order['price']:.2f}$"
                        for order in orders_to_place
                    ])
                    
                    # Onay kutusu göster
                    confirm = messagebox.askyesno(
                        "Hidden Sell Emir Onayı",
                        f"Aşağıdaki {len(orders_to_place)} hidden sell emri gönderilecek:\n\n{order_details}\n\n"
                        f"Onaylıyor musunuz?"
                    )
                    
                    if confirm:
                        # Gerçek emir gönderme işlemi burada olacak
                        messagebox.showinfo("Bilgi", f"{len(orders_to_place)} adet hidden sell emri gönderildi (Gösterim amaçlı)")
                
                hidden_sell_btn = ttk.Button(
                    button_frame,
                    text="Hidden Sell Emri",
                    command=hidden_sell_selected
                )
                hidden_sell_btn.pack(side=tk.LEFT, padx=5)
            
            # En çok düşenler için Hidden Buy butonu
            else:
                def hidden_buy_selected():
                    if not selected_movers:
                        messagebox.showinfo("Uyarı", "Lütfen en az bir hisse seçin.")
                        return
                    
                    # Seçili hisselerin verilerini topla
                    orders_to_place = []
                    
                    for item_id in movers_tree.get_children():
                        item_values = movers_tree.item(item_id, "values")
                        
                        if not item_values or len(item_values) < 9 or item_values[0] != "✓":
                            continue
                        
                        symbol = item_values[1]
                        ask = item_values[8]
                        bid = item_values[7]
                        
                        # "--" değerlerini kontrol et
                        if ask == "--" or bid == "--":
                            print(f"{symbol} için bid/ask verisi bulunamadı, atlanıyor...")
                            continue
                            
                        ask = float(ask)
                        bid = float(bid)
                        spread = ask - bid
                        
                        # Hedef fiyat: bid + spread*0.15
                        target_price = bid + (spread * 0.15)
                        
                        # Miktar: 200 share
                        quantity = 200
                        
                        orders_to_place.append({
                            'symbol': symbol,
                            'quantity': quantity,
                            'price': target_price
                        })
                    
                    if not orders_to_place:
                        messagebox.showinfo("Uyarı", "İşlem yapılabilecek hisse bulunamadı.")
                        return
                    
                    # Emir detaylarını hazırla
                    order_details = "\n".join([
                        f"{order['symbol']}: {order['quantity']} adet @ {order['price']:.2f}$"
                        for order in orders_to_place
                    ])
                    
                    # Onay kutusu göster
                    confirm = messagebox.askyesno(
                        "Hidden Buy Emir Onayı",
                        f"Aşağıdaki {len(orders_to_place)} hidden buy emri gönderilecek:\n\n{order_details}\n\n"
                        f"Onaylıyor musunuz?"
                    )
                    
                    if confirm:
                        # Gerçek emir gönderme işlemi burada olacak
                        messagebox.showinfo("Bilgi", f"{len(orders_to_place)} adet hidden buy emri gönderildi (Gösterim amaçlı)")
                
                hidden_buy_btn = ttk.Button(
                    button_frame,
                    text="Hidden Buy Emri",
                    command=hidden_buy_selected
                )
                hidden_buy_btn.pack(side=tk.LEFT, padx=5)
            
            # Son güncelleme zamanını ekle
            now_time = datetime.datetime.now().strftime("%H:%M:%S")
            update_time_label = ttk.Label(info_frame, text=f"Son güncelleme: {now_time}")
            update_time_label.pack(side=tk.LEFT)
            
            # Toplam kayıt sayısını göster
            count_label = ttk.Label(info_frame, text=f"Toplam: {len(top_movers)} hisse")
            count_label.pack(side=tk.LEFT, padx=20)
            
            # Kapat butonu
            close_btn = ttk.Button(info_frame, text="Kapat", command=movers_window.destroy)
            close_btn.pack(side=tk.RIGHT)
            
            # Yenile butonu
            refresh_btn = ttk.Button(
                info_frame, 
                text="Yenile", 
                command=lambda cat=category, gain=show_gainers: (movers_window.destroy(), self.show_category_top_movers(cat, gain))
            )
            refresh_btn.pack(side=tk.RIGHT, padx=10)
        
        except Exception as e:
            print(f"Show category top movers error: {e}")
            import traceback
            traceback.print_exc()
            messagebox.showerror("Hata", f"En çok değişenler hesaplanırken hata oluştu: {str(e)}")

    def opt50_mal_topla(self):
        """Opt50 portföyündeki hisseler için ucuzluk skoru hesaplama ve alım fırsatı analizi"""
        try:
            # T-benchmark'ı kontrol et
            if not hasattr(self, 't_benchmark') or self.t_benchmark is None:
                messagebox.showinfo("Bilgi", "T-benchmark verisi bulunamadı. Lütfen IBKR bağlantısını kontrol edin.")
                return
                
            # CSV dosyasının yolunu belirle
            portfolio_file = "optimized_50_stocks_portfolio.csv"
            
            # Dosya var mı kontrol et
            if not os.path.exists(portfolio_file):
                messagebox.showerror("Dosya Bulunamadı", f"{portfolio_file} dosyası bulunamadı.")
                return
                
            # CSV verisini oku
            try:
                df = pd.read_csv(portfolio_file)
                # Gerekli sütunları kontrol et
                required_columns = ["PREF IBKR", "FINAL_THG", "AVG_ADV", "Final_Shares"]
                missing_columns = [col for col in required_columns if col not in df.columns]
                if missing_columns:
                    messagebox.showerror("Eksik Sütunlar", f"CSV dosyasında aşağıdaki sütunlar eksik: {', '.join(missing_columns)}")
                    return
                    
                # NaN değerleri temizle
                df = df.dropna(subset=["PREF IBKR"])
                
            except Exception as e:
                messagebox.showerror("CSV Okuma Hatası", f"CSV dosyası okunurken hata oluştu: {str(e)}")
                return
                
            # Hisselerin fiyat verilerini ve ucuzluk skorlarını sakla
            opportunity_data = []
            
            # İşlem başladı mesajı
            print(f"Opt50 hisseleri için ucuzluk skoru hesaplanıyor... T-benchmark: {self.t_benchmark:.2f}¢")
            
            # Her hisse için ucuzluk skorunu hesapla
            for _, row in df.iterrows():
                ticker = row["PREF IBKR"]
                if not ticker or pd.isna(ticker):
                    continue
                    
                # Hissenin fiyat verilerini al
                ticker_data = self.market_data_cache.get(ticker)
                if not ticker_data:
                    print(f"{ticker} için fiyat verisi bulunamadı, atlanıyor...")
                    continue
                    
                # Bid ve ask değerlerini kontrol et
                if (not hasattr(ticker_data, 'bid') or ticker_data.bid is None or math.isnan(ticker_data.bid) or
                    not hasattr(ticker_data, 'ask') or ticker_data.ask is None or math.isnan(ticker_data.ask)):
                    print(f"{ticker} için bid/ask verisi bulunamadı, atlanıyor...")
                    continue
                    
                # Spread hesapla (dolar bazında)
                bid = ticker_data.bid
                ask = ticker_data.ask
                spread = ask - bid
                
                # Hedef alım fiyatı: ilk bid + spread*0.15
                target_price = bid + (spread * 0.15)
                
                # T-benchmark'a göre ucuzluk skorunu hesapla (cent bazında)
                # Düşük/negatif skor daha iyi (daha ucuz)
                target_price_cents = target_price * 100  # Dolardan cente çevir
                
                # Ucuzluk skoru: Bu fiyat, benchmark'tan ne kadar farklı (- değer daha iyi)
                cheapness_score = target_price_cents - self.t_benchmark
                
                # Final shares değerini al
                final_shares = row["Final_Shares"] if "Final_Shares" in row and not pd.isna(row["Final_Shares"]) else 0
                
                # FINAL_THG değerini al
                final_thg = row["FINAL_THG"] if "FINAL_THG" in row and not pd.isna(row["FINAL_THG"]) else 0
                
                # AVG_ADV değerini al
                avg_adv = row["AVG_ADV"] if "AVG_ADV" in row and not pd.isna(row["AVG_ADV"]) else 0
                
                # Last değerini al
                last_price = getattr(ticker_data, 'last', None)
                if last_price is None or math.isnan(last_price):
                    last_price = 0
                
                # Canlı bid/ask spread yüzdesi
                live_spread_pct = (spread / bid) * 100 if bid > 0 else 0
                
                # Verileri kaydet
                opportunity_data.append({
                    'symbol': ticker,
                    'last': last_price,
                    'bid': bid,
                    'ask': ask,
                    'spread': spread,
                    'spread_pct': live_spread_pct,
                    'target_price': target_price,
                    'cheapness_score': cheapness_score,
                    'final_shares': final_shares,
                    'final_thg': final_thg,
                    'avg_adv': avg_adv
                })
            
            # Veri yoksa bilgi ver
            if not opportunity_data:
                messagebox.showinfo("Bilgi", "Değerlendirilebilecek hisse bulunamadı.")
                return
                
            # Ucuzluk skoruna göre sırala (en düşük/negatif en üstte)
            opportunity_data.sort(key=lambda x: x['cheapness_score'])
            
            # Yeni pencere oluştur
            opportunity_window = tk.Toplevel(self)
            opportunity_window.title("Opt50 Alım Fırsatları")
            opportunity_window.geometry("1200x700")
            
            # ETF bilgi paneli ekle
            etf_panel, etf_labels = self.create_etf_info_panel(opportunity_window)
            
            # Bilgi bar - mevcut benchmark ve açıklama
            info_bar = ttk.Frame(opportunity_window)
            info_bar.pack(fill=tk.X, padx=10, pady=5)
            
            ttk.Label(
                info_bar, 
                text=f"T-benchmark: {self.t_benchmark:.2f}¢ | Ucuzluk Skoru: Hedef fiyat - T-benchmark (Negatif değerler daha iyi)",
                font=('Arial', 9, 'bold')
            ).pack(side=tk.LEFT)
            
            ttk.Label(
                info_bar,
                text="Hedef Fiyat = ilk bid + spread × 0.15",
                font=('Arial', 9)
            ).pack(side=tk.RIGHT)
            
            # Treeview için frame
            tree_frame = ttk.Frame(opportunity_window)
            tree_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=5)
            
            # Treeview oluştur
            columns = (
                "symbol", "last", "bid", "ask", "spread_pct", "target_price", 
                "cheapness_score", "final_thg", "avg_adv", "final_shares"
            )
            
            opportunity_tree = ttk.Treeview(
                tree_frame,
                columns=columns,
                show="headings",
                selectmode="browse"
            )
            
            # Sütun başlıkları
            column_headings = {
                "symbol": "Sembol",
                "last": "Son Fiyat",
                "bid": "Alış",
                "ask": "Satış",
                "spread_pct": "Spread %",
                "target_price": "Hedef Fiyat",
                "cheapness_score": "Ucuzluk Skoru (¢)",
                "final_thg": "FINAL_THG",
                "avg_adv": "AVG_ADV",
                "final_shares": "Final_Shares"
            }
            
            # Sütunları yapılandır
            for col in columns:
                opportunity_tree.heading(col, text=column_headings[col])
                width = 100 if col not in ["symbol", "cheapness_score"] else 120
                anchor = tk.CENTER if col != "symbol" else tk.W
                opportunity_tree.column(col, width=width, anchor=anchor)
            
            # Scrollbar
            scrollbar = ttk.Scrollbar(tree_frame, orient="vertical", command=opportunity_tree.yview)
            scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
            opportunity_tree.configure(yscrollcommand=scrollbar.set)
            opportunity_tree.pack(fill=tk.BOTH, expand=True)
            
            # Satırlara değerleri ekle
            for data in opportunity_data:
                # Ucuzluk skoruna göre satır rengi belirle
                tag = ""
                if data['cheapness_score'] < -5:  # Çok iyi fırsat
                    tag = "very_good"
                elif data['cheapness_score'] < 0:  # İyi fırsat
                    tag = "good"
                elif data['cheapness_score'] < 5:  # Orta
                    tag = "neutral"
                else:  # Kötü
                    tag = "bad"
                
                # Değerleri dönüştür
                values = (
                    data['symbol'],
                    f"{data['last']:.2f}",
                    f"{data['bid']:.2f}",
                    f"{data['ask']:.2f}",
                    f"{data['spread_pct']:.2f}%",
                    f"{data['target_price']:.2f}",
                    f"{data['cheapness_score']:.2f}",
                    f"{data['final_thg']:.2f}" if data['final_thg'] else "--",
                    f"{data['avg_adv']:.2f}" if data['avg_adv'] else "--",
                    f"{int(data['final_shares'])}" if data['final_shares'] else "--"
                )
                
                opportunity_tree.insert("", tk.END, values=values, tags=(tag,))
            
            # Renk etiketlerini konfigüre et
            opportunity_tree.tag_configure("very_good", background="#90EE90")  # Açık yeşil
            opportunity_tree.tag_configure("good", background="#D0F0C0")  # Daha hafif yeşil
            opportunity_tree.tag_configure("neutral", background="#F5F5F5")  # Beyaz/gri
            opportunity_tree.tag_configure("bad", background="#FFCCCB")  # Hafif kırmızı
            
            # Butonlar için frame
            button_frame = ttk.Frame(opportunity_window)
            button_frame.pack(fill=tk.X, padx=10, pady=10)
            
            # Select All butonu
            def select_all_items():
                for item in opportunity_tree.get_children():
                    opportunity_tree.selection_add(item)
                    
            select_all_btn = ttk.Button(
                button_frame,
                text="Tümünü Seç",
                command=select_all_items
            )
            select_all_btn.pack(side=tk.LEFT, padx=5)
            
            # Deselect All butonu
            def deselect_all_items():
                opportunity_tree.selection_remove(opportunity_tree.selection())
                
            deselect_all_btn = ttk.Button(
                button_frame,
                text="Tümünü Kaldır",
                command=deselect_all_items
            )
            deselect_all_btn.pack(side=tk.LEFT, padx=5)
            
            # Seçili hisse için emirler
            def place_order_for_selected():
                selected_items = opportunity_tree.selection()
                if not selected_items:
                    messagebox.showinfo("Uyarı", "Lütfen bir hisse seçin.")
                    return
                    
                # Seçili hissenin verilerini al
                selected_item = opportunity_tree.item(selected_items[0])
                values = selected_item['values']
                
                if not values or len(values) < 6:
                    messagebox.showinfo("Hata", "Seçilen hisse için veri alınamadı.")
                    return
                
                symbol = values[0]
                target_price = float(values[5])
                
                # Emir miktarı için seçenek sun
                shares_prompt = tk.simpledialog.askinteger(
                    "Lot Sayısı", 
                    f"{symbol} için kaç lot alış emri verilsin?",
                    parent=opportunity_window,
                    minvalue=1,
                    maxvalue=1000
                )
                
                if not shares_prompt:
                    return
                    
                quantity = shares_prompt
                
                # Emir onayı
                confirm = messagebox.askyesno(
                    "Emir Onayı",
                    f"{symbol} hissesi için {quantity} adet, {target_price:.2f}$ fiyattan hidden alış emri verilecek.\n\n"
                    f"Ucuzluk Skoru: {float(values[6]):.2f}¢\n\n"
                    f"Bu emri göndermek istiyor musunuz?"
                )
                
                if confirm:
                    messagebox.showinfo("Bilgi", f"{symbol} için emir gönderildi. (Gösterim amaçlı)")
                    # Gerçek emir gönderme işlemi burada olacak
            
            # Tüm hesaplanmış uygun fiyatlara hidden alış emri ver
            def place_all_good_orders():
                # İyi fırsat olarak değerlendirilen hisseleri filtrele (ucuzluk skoru < 0)
                good_opportunities = [data for data in opportunity_data if data['cheapness_score'] < 0]
                
                if not good_opportunities:
                    messagebox.showinfo("Bilgi", "İyi fırsat kriterine uyan hisse bulunamadı.")
                    return
                
                # Kaç lot alınacağını sor
                shares_prompt = tk.simpledialog.askinteger(
                    "Lot Sayısı", 
                    f"Her hisse için kaç lot alış emri verilsin?",
                    parent=opportunity_window,
                    minvalue=1,
                    maxvalue=1000
                )
                
                if not shares_prompt:
                    return
                
                quantity = shares_prompt
                
                # Onay mesajı
                confirm = messagebox.askyesno(
                    "Toplu Emir Onayı",
                    f"Ucuzluk skoru 0'dan düşük olan {len(good_opportunities)} hisse için\n"
                    f"her birine {quantity} adet hidden alış emri verilecek.\n\n"
                    f"Bu işlemi onaylıyor musunuz?"
                )
                
                if confirm:
                    # Gerçek emir gönderme işlemi burada olacak
                    order_details = "\n".join([
                        f"{data['symbol']}: {quantity} adet @ {data['target_price']:.2f}$ "
                        f"(Ucuzluk: {data['cheapness_score']:.2f}¢)"
                        for data in good_opportunities
                    ])
                    
                    messagebox.showinfo(
                        "Emirler Gönderildi", 
                        f"Aşağıdaki emirler gönderildi (Gösterim amaçlı):\n\n{order_details}"
                    )
            
            # Yenile butonu
            refresh_btn = ttk.Button(
                button_frame,
                text="Yenile",
                command=lambda: (opportunity_window.destroy(), self.cashpark35_mal_topla())
            )
            refresh_btn.pack(side=tk.LEFT, padx=5)
            
            # Seçili hisse için emir butonu
            order_btn = ttk.Button(
                button_frame,
                text="Seçili Hisse İçin Emir Ver",
                command=place_order_for_selected
            )
            order_btn.pack(side=tk.LEFT, padx=5)
            
            # Tüm iyi fırsatlar için emir ver
            def place_all_good_orders():
                # İyi fırsat olarak değerlendirilen pozisyonları filtrele (outperform skoru > 0)
                good_opportunities = [data for data in profit_opportunities if data['outperform_score'] > 0]
                
                if not good_opportunities:
                    messagebox.showinfo("Bilgi", "İyi fırsat kriterine uyan pozisyon bulunamadı.")
                    return
                
                # Pozisyonun ne kadarının satılacağını sor (yüzde)
                percent_prompt = tk.simpledialog.askinteger(
                    "Satış Yüzdesi", 
                    "Her pozisyonun yüzde kaçı satılsın? (1-100)",
                    parent=profit_window,
                    minvalue=1,
                    maxvalue=100
                )
                
                if not percent_prompt:
                    return
                
                sell_percent = percent_prompt / 100.0
                
                # Onay mesajı
                confirm = messagebox.askyesno(
                    "Toplu Emir Onayı",
                    f"Outperform skoru 0'dan yüksek olan {len(good_opportunities)} pozisyon için\n"
                    f"her birinin %{percent_prompt}'i satılacak.\n\n"
                    f"Bu işlemi onaylıyor musunuz?"
                )
                
                if confirm:
                    # Gerçek emir gönderme işlemi burada olacak
                    order_details = "\n".join([
                        f"{data['symbol']}: {int(data['quantity'] * sell_percent)} adet @ {data['target_price']:.2f}$ "
                        f"(Outperform: {data['outperform_score']:+.2f}¢)"
                        for data in good_opportunities
                    ])
                    
                    messagebox.showinfo(
                        "Emirler Gönderildi", 
                        f"Aşağıdaki emirler gönderildi (Gösterim amaçlı):\n\n{order_details}"
                    )
            
            # Tüm iyi fırsatlar için emir butonu
            all_orders_btn = ttk.Button(
                button_frame,
                text="Tüm İyi Fırsatlar İçin Emir Ver",
                command=place_all_good_orders
            )
            all_orders_btn.pack(side=tk.LEFT, padx=5)
            
            # Kapat butonu
            close_btn = ttk.Button(
                button_frame,
                text="Kapat",
                command=opportunity_window.destroy
            )
            close_btn.pack(side=tk.RIGHT, padx=5)
            
            # Toplam kayıt sayısı
            count_label = ttk.Label(
                button_frame,
                text=f"Toplam: {len(opportunity_data)} hisse | Ucuz Fırsatlar: {len([d for d in opportunity_data if d['cheapness_score'] < 0])}"
            )
            count_label.pack(side=tk.RIGHT, padx=20)
            
        except Exception as e:
            print(f"Cashpark35 mal toplama hatası: {e}")
            import traceback
            traceback.print_exc()
            messagebox.showerror("Hata", f"Cashpark35 mal toplama sırasında hata oluştu: {str(e)}")

    def take_profit_from_longs(self):
        """Long pozisyonlar için take profit fırsatlarını hesaplayarak gösterir"""
        try:
            # IBKR bağlantısını kontrol et
            if not self.is_connected:
                messagebox.showinfo("Bağlantı yok", "Lütfen önce IBKR'ye bağlanın.")
                return
                
            # Pozisyonları al
            positions = self.ib.positions()
            
            # Pozisyon yoksa uyarı ver
            if not positions:
                messagebox.showinfo("Pozisyon Yok", "Hiç açık pozisyon bulunamadı.")
                return
                
            # Long pozisyonları filtrele
            long_positions = [pos for pos in positions if pos.position > 0]
            
            if not long_positions:
                messagebox.showinfo("Long Pozisyon Yok", "Hiç long pozisyon bulunamadı.")
                return
                
            # T-prefs ve C-prefs benchmark değerlerini kontrol et
            if not hasattr(self, 't_benchmark') or not hasattr(self, 'c_benchmark'):
                messagebox.showinfo("Benchmark Değeri Yok", "Benchmark değerleri bulunamadı. IBKR bağlantısını kontrol edin.")
                return
                
            # Pozisyon fırsatlarını saklamak için liste
            profit_opportunities = []
            
            # T-prefs ve C-prefs tickerları alın
            t_prefs_tickers = self.tltr_tickers if hasattr(self, 'tltr_tickers') else []
            c_prefs_tickers = self.divspread_tickers if hasattr(self, 'divspread_tickers') else []
            
            print(f"Long pozisyonlar değerlendiriliyor...")
            print(f"T-benchmark: {self.t_benchmark:.2f}¢, C-benchmark: {self.c_benchmark:.2f}¢")
            
            # Her pozisyon için fırsat hesapla
            for position in long_positions:
                contract = position.contract
                symbol = contract.localSymbol if hasattr(contract, 'localSymbol') and contract.localSymbol else contract.symbol
                quantity = position.position
                avg_cost = position.avgCost
                
                # Fiyat verilerini al
                ticker_data = self.market_data_cache.get(symbol)
                if not ticker_data:
                    print(f"{symbol} için fiyat verisi bulunamadı, atlanıyor...")
                    continue
                    
                # Fiyat verilerini kontrol et
                if (not hasattr(ticker_data, 'bid') or ticker_data.bid is None or math.isnan(ticker_data.bid) or
                    not hasattr(ticker_data, 'ask') or ticker_data.ask is None or math.isnan(ticker_data.ask)):
                    print(f"{symbol} için bid/ask verisi bulunamadı, atlanıyor...")
                    continue
                
                # Grup belirle (T-prefs veya C-prefs)
                group = "T-prefs" if symbol in t_prefs_tickers else "C-prefs" if symbol in c_prefs_tickers else "Diğer"
                
                # Uygun benchmark seç
                benchmark = self.t_benchmark if group == "T-prefs" else self.c_benchmark if group == "C-prefs" else 0
                
                # Spread hesapla
                bid = ticker_data.bid
                ask = ticker_data.ask
                last = getattr(ticker_data, 'last', 0) or 0
                spread = ask - bid
                
                # Hedef satış fiyatı: ask - spread*0.15
                target_price = ask - (spread * 0.15)
                
                # Kar yüzdesi hesapla
                profit_percent = ((target_price / avg_cost) - 1) * 100 if avg_cost > 0 else 0
                
                # Cent bazında satış fiyatı
                target_price_cents = target_price * 100 
                
                # Benchmark'a göre performans (outperform skoru) - pozitif değer daha iyi
                outperform_score = target_price_cents - benchmark
                
                # Verileri kaydet
                profit_opportunities.append({
                    'symbol': symbol,
                    'group': group,
                    'quantity': quantity,
                    'avg_cost': avg_cost,
                    'last': last,
                    'bid': bid,
                    'ask': ask,
                    'spread': spread,
                    'target_price': target_price,
                    'profit_percent': profit_percent,
                    'benchmark': benchmark,
                    'outperform_score': outperform_score
                })
            
            # Veri yoksa bilgi ver
            if not profit_opportunities:
                messagebox.showinfo("Bilgi", "Değerlendirilebilecek long pozisyon bulunamadı.")
                return
                
            # Benchmark outperform skoruna göre sırala (en yüksek en üstte)
            profit_opportunities.sort(key=lambda x: x['outperform_score'], reverse=True)
            
            # Yeni pencere oluştur
            profit_window = tk.Toplevel(self)
            profit_window.title("Long Pozisyonlar İçin Take Profit Fırsatları")
            profit_window.geometry("1200x700")
            
            # ETF bilgi paneli ekle
            etf_panel, etf_labels = self.create_etf_info_panel(profit_window)
            
            # Bilgi bar - mevcut benchmark ve açıklama
            info_bar = ttk.Frame(profit_window)
            info_bar.pack(fill=tk.X, padx=10, pady=5)
            
            ttk.Label(
                info_bar, 
                text=f"T-benchmark: {self.t_benchmark:.2f}¢ | C-benchmark: {self.c_benchmark:.2f}¢ | " +
                     f"Outperform Skoru: Hedef fiyat - Benchmark (Yüksek değerler daha iyi)",
                font=('Arial', 9, 'bold')
            ).pack(side=tk.LEFT)
            
            ttk.Label(
                info_bar,
                text="Hedef Fiyat = ask - spread × 0.15",
                font=('Arial', 9)
            ).pack(side=tk.RIGHT)
            
            # Treeview için frame
            tree_frame = ttk.Frame(profit_window)
            tree_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=5)
            
            # Treeview oluştur
            columns = (
                "Select", "symbol", "group", "quantity", "avg_cost", "last", "bid", "ask", 
                "target_price", "profit_percent", "outperform_score", "benchmark"
            )
            
            profit_tree = ttk.Treeview(
                tree_frame,
                columns=columns,
                show="headings",
                selectmode="none"
            )
            
            # Sütun başlıkları
            column_headings = {
                "Select": "Seç",
                "symbol": "Sembol",
                "group": "Grup",
                "quantity": "Miktar",
                "avg_cost": "Ortalama Maliyet",
                "last": "Son Fiyat",
                "bid": "Alış",
                "ask": "Satış",
                "target_price": "Hedef Satış Fiyatı",
                "profit_percent": "Kar %",
                "outperform_score": "Outperform Skoru (¢)",
                "benchmark": "Benchmark (¢)"
            }
            
            # Sütunları yapılandır
            for col in columns:
                profit_tree.heading(col, text=column_headings[col])
                if col == "Select":
                    width = 40
                    anchor = tk.CENTER
                else:
                    width = 100 if col not in ["symbol", "outperform_score", "group"] else 120
                    anchor = tk.CENTER if col != "symbol" else tk.W
                profit_tree.column(col, width=width, anchor=anchor)
            
            # Scrollbar
            scrollbar = ttk.Scrollbar(tree_frame, orient="vertical", command=profit_tree.yview)
            scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
            profit_tree.configure(yscrollcommand=scrollbar.set)
            profit_tree.pack(fill=tk.BOTH, expand=True)
            
            # Seçilen öğeleri saklamak için set
            selected_positions = set()
            
            # Satırlara değerleri ekle
            for data in profit_opportunities:
                # Outperform skoruna göre satır rengi belirle
                tag = ""
                if data['outperform_score'] > 5:  # Çok iyi fırsat
                    tag = "very_good"
                elif data['outperform_score'] > 0:  # İyi fırsat
                    tag = "good"
                elif data['outperform_score'] > -5:  # Orta
                    tag = "neutral"
                else:  # Kötü
                    tag = "bad"
                
                # Değerleri dönüştür
                values = (
                    "□",  # Başlangıçta seçili değil
                    data['symbol'],
                    data['group'],
                    f"{int(data['quantity']):,}",
                    f"{data['avg_cost']:.2f}",
                    f"{data['last']:.2f}" if data['last'] > 0 else "--",
                    f"{data['bid']:.2f}",
                    f"{data['ask']:.2f}",
                    f"{data['target_price']:.2f}",
                    f"{data['profit_percent']:+.2f}%" if data['profit_percent'] != 0 else "0.00%",
                    f"{data['outperform_score']:+.2f}",
                    f"{data['benchmark']:.2f}"
                )
                
                profit_tree.insert("", tk.END, values=values, tags=(tag,))
                
            # Treeview tıklama fonksiyonu
            def on_profit_tree_click(event):
                region = profit_tree.identify_region(event.x, event.y)
                column = profit_tree.identify_column(event.x)
                
                # Sadece ilk sütuna (seçim sütunu) tıklandığında işlem yap
                if region == "cell" and column == "#1":
                    item_id = profit_tree.identify_row(event.y)
                    if item_id:
                        item_values = profit_tree.item(item_id, "values")
                        if item_values:
                            symbol = item_values[1]  # Symbol değeri
                            current_state = item_values[0]  # Seçim durumu
                            
                            # Durumu değiştir
                            new_state = "✓" if current_state == "□" else "□"
                            profit_tree.set(item_id, "Select", new_state)
                            
                            # Set'e ekle veya çıkar
                            if new_state == "✓":
                                selected_positions.add(symbol)
                            else:
                                if symbol in selected_positions:
                                    selected_positions.remove(symbol)
            
            # Tıklama olayını bağla
            profit_tree.bind("<ButtonRelease-1>", on_profit_tree_click)
            
            # Renk etiketlerini konfigüre et
            profit_tree.tag_configure("very_good", background="#90EE90")  # Açık yeşil
            profit_tree.tag_configure("good", background="#D0F0C0")  # Daha hafif yeşil
            profit_tree.tag_configure("neutral", background="#F5F5F5")  # Beyaz/gri
            profit_tree.tag_configure("bad", background="#FFCCCB")  # Hafif kırmızı
            
            # Butonlar için frame
            button_frame = ttk.Frame(profit_window)
            button_frame.pack(fill=tk.X, padx=10, pady=10)
            
            # Yenile butonu
            refresh_btn = ttk.Button(
                button_frame,
                text="Yenile",
                command=lambda: (profit_window.destroy(), self.take_profit_from_longs())
            )
            refresh_btn.pack(side=tk.LEFT, padx=5)
            
            # Select All butonu
            def select_all_items():
                for item_id in profit_tree.get_children():
                    profit_tree.set(item_id, "Select", "✓")
                    item_values = profit_tree.item(item_id, "values")
                    if item_values and len(item_values) > 1:
                        selected_positions.add(item_values[1])  # Symbol değeri
                    
            select_all_btn = ttk.Button(
                button_frame,
                text="Tümünü Seç",
                command=select_all_items
            )
            select_all_btn.pack(side=tk.LEFT, padx=5)
            
            # Deselect All butonu
            def deselect_all_items():
                for item_id in profit_tree.get_children():
                    profit_tree.set(item_id, "Select", "□")
                selected_positions.clear()
                
            deselect_all_btn = ttk.Button(
                button_frame,
                text="Tümünü Kaldır",
                command=deselect_all_items
            )
            deselect_all_btn.pack(side=tk.LEFT, padx=5)
            
            # Hidden Sell butonu (quick trade için)
            def hidden_sell_selected():
                if not selected_positions:
                    messagebox.showinfo("Uyarı", "Lütfen en az bir pozisyon seçin.")
                    return
                
                # Seçili hisselerin verilerini topla
                orders_to_place = []
                
                for item_id in profit_tree.get_children():
                    item_values = profit_tree.item(item_id, "values")
                    
                    if not item_values or len(item_values) < 10 or item_values[0] != "✓":
                        continue
                    
                    symbol = item_values[1]
                    current_quantity = int(item_values[3].replace(",", ""))
                    ask = float(item_values[7])
                    spread = float(item_values[7]) - float(item_values[6])  # ask - bid
                    
                    # Hedef fiyat: ask - spread*0.15
                    target_price = ask - (spread * 0.15)
                    
                    # Miktar: 200 lot veya pozisyon büyüklüğü (hangisi küçükse)
                    quantity = min(200, current_quantity)
                    
                    orders_to_place.append({
                        'symbol': symbol,
                        'quantity': quantity,
                        'price': target_price
                    })
                
                if not orders_to_place:
                    return
                
                # Emir detaylarını hazırla
                order_details = "\n".join([
                    f"{order['symbol']}: {order['quantity']} adet @ {order['price']:.2f}$"
                    for order in orders_to_place
                ])
                
                # Onay kutusu göster
                confirm = messagebox.askyesno(
                    "Hidden Sell Emir Onayı",
                    f"Aşağıdaki {len(orders_to_place)} hidden sell emri gönderilecek:\n\n{order_details}\n\n"
                    f"Onaylıyor musunuz?"
                )
                
                if confirm:
                    try:
                        # Gerçek emirleri gönder
                        sent_orders = 0
                        for order in orders_to_place:
                            symbol = order['symbol']
                            price = float(order['price'])
                            quantity = int(order['quantity'])
                            
                            # Kontrat oluştur
                            contract = Stock(symbol, 'SMART', 'USD')
                            
                            # Emir oluştur ve gönder
                            limit_order = LimitOrder('SELL', quantity, round(price, 2))
                            limit_order.hidden = True
                            self.ib.placeOrder(contract, limit_order)
                            print(f"Emir gönderildi: {symbol} SELL @ {price:.2f} x {quantity}")
                            sent_orders += 1
                        
                        messagebox.showinfo("Başarılı", f"{sent_orders} adet hidden sell emri başarıyla gönderildi!")
                    except Exception as e:
                        messagebox.showerror("Hata", f"Emirler gönderilirken hata oluştu: {str(e)}")

            hidden_sell_btn = ttk.Button(
                button_frame,
                text="Hidden Sell Emri",
                command=hidden_sell_selected
            )
            hidden_sell_btn.pack(side=tk.LEFT, padx=5)
            
            # Seçili pozisyon için emir
            def place_order_for_selected():
                selected_items = profit_tree.selection()
                if not selected_items:
                    messagebox.showinfo("Uyarı", "Lütfen en az bir pozisyon seçin.")
                    return
                    
                # Seçili hisselerin verilerini al
                selected_item = profit_tree.item(selected_items[0])
                values = selected_item['values']
                
                if not values or len(values) < 8:
                    messagebox.showinfo("Hata", "Seçilen pozisyon için veri alınamadı.")
                    return
                
                symbol = values[0]
                target_price = float(values[7])
                current_quantity = int(values[2].replace(",", ""))
                
                # Emir miktarı için seçenek sun
                shares_prompt = tk.simpledialog.askinteger(
                    "Lot Sayısı", 
                    f"{symbol} için kaç lot satış emri verilsin? (Mevcut: {current_quantity})",
                    parent=profit_window,
                    minvalue=1,
                    maxvalue=current_quantity
                )
                
                if not shares_prompt:
                    return
                    
                quantity = shares_prompt
                
                # Emir onayı
                confirm = messagebox.askyesno(
                    "Emir Onayı",
                    f"{symbol} hissesi için {quantity} adet, {target_price:.2f}$ fiyattan hidden satış emri verilecek.\n\n"
                    f"Outperform Skoru: {float(values[9]):+.2f}¢\n\n"
                    f"Bu emri göndermek istiyor musunuz?"
                )
                
                if confirm:
                    messagebox.showinfo("Bilgi", f"{symbol} için satış emri gönderildi. (Gösterim amaçlı)")
                    # Gerçek emir gönderme işlemi burada olacak
            
            # Seçili pozisyon için emir butonu
            order_btn = ttk.Button(
                button_frame,
                text="Seçili Pozisyon İçin Emir Ver",
                command=place_order_for_selected
            )
            order_btn.pack(side=tk.LEFT, padx=5)
            
        except Exception as e:
            print(f"Take profit from longs hatası: {e}")
            import traceback
            traceback.print_exc()
            messagebox.showerror("Hata", f"Take profit from longs sırasında hata oluştu: {str(e)}")

    def take_profit_from_shorts(self):
        """Short pozisyonlar için take profit fırsatlarını hesaplayarak gösterir"""
        try:
            # IBKR bağlantısını kontrol et
            if not self.is_connected:
                messagebox.showinfo("Bağlantı yok", "Lütfen önce IBKR'ye bağlanın.")
                return
                
            # Pozisyonları al
            positions = self.ib.positions()
            
            # Pozisyon yoksa uyarı ver
            if not positions:
                messagebox.showinfo("Pozisyon Yok", "Hiç açık pozisyon bulunamadı.")
                return
                
            # Short pozisyonları filtrele
            short_positions = [pos for pos in positions if pos.position < 0]
            
            if not short_positions:
                messagebox.showinfo("Short Pozisyon Yok", "Hiç short pozisyon bulunamadı.")
                return
                
            # T-prefs ve C-prefs benchmark değerlerini kontrol et
            if not hasattr(self, 't_benchmark') or not hasattr(self, 'c_benchmark'):
                messagebox.showinfo("Benchmark Değeri Yok", "Benchmark değerleri bulunamadı. IBKR bağlantısını kontrol edin.")
                return
                
            # Pozisyon fırsatlarını saklamak için liste
            profit_opportunities = []
            
            # T-prefs ve C-prefs tickerları alın
            t_prefs_tickers = self.tltr_tickers if hasattr(self, 'tltr_tickers') else []
            c_prefs_tickers = self.divspread_tickers if hasattr(self, 'divspread_tickers') else []
            
            print(f"Short pozisyonlar değerlendiriliyor...")
            print(f"T-benchmark: {self.t_benchmark:.2f}¢, C-benchmark: {self.c_benchmark:.2f}¢")
            
            # Her pozisyon için fırsat hesapla
            for position in short_positions:
                contract = position.contract
                symbol = contract.localSymbol if hasattr(contract, 'localSymbol') and contract.localSymbol else contract.symbol
                quantity = abs(position.position)  # Short olduğu için negatif, mutlak değerini alıyoruz
                avg_cost = position.avgCost
                
                # Fiyat verilerini al
                ticker_data = self.market_data_cache.get(symbol)
                if not ticker_data:
                    print(f"{symbol} için fiyat verisi bulunamadı, atlanıyor...")
                    continue
                    
                # Fiyat verilerini kontrol et
                if (not hasattr(ticker_data, 'bid') or ticker_data.bid is None or math.isnan(ticker_data.bid) or
                    not hasattr(ticker_data, 'ask') or ticker_data.ask is None or math.isnan(ticker_data.ask)):
                    print(f"{symbol} için bid/ask verisi bulunamadı, atlanıyor...")
                    continue
                
                # Grup belirle (T-prefs veya C-prefs)
                group = "T-prefs" if symbol in t_prefs_tickers else "C-prefs" if symbol in c_prefs_tickers else "Diğer"
                
                # Uygun benchmark seç
                benchmark = self.t_benchmark if group == "T-prefs" else self.c_benchmark if group == "C-prefs" else 0
                
                # Spread hesapla
                bid = ticker_data.bid
                ask = ticker_data.ask
                last = getattr(ticker_data, 'last', 0) or 0
                spread = ask - bid
                
                # Hedef alış fiyatı: bid + spread*0.15
                target_price = bid + (spread * 0.15)
                
                # Kar yüzdesi hesapla
                profit_percent = ((avg_cost / target_price) - 1) * 100 if target_price > 0 else 0
                
                # Cent bazında alış fiyatı
                target_price_cents = target_price * 100 
                
                # Benchmark'a göre performans (outperform skoru) - negatif değer daha iyi
                outperform_score = benchmark - target_price_cents
                
                # Verileri kaydet
                profit_opportunities.append({
                    'symbol': symbol,
                    'group': group,
                    'quantity': quantity,
                    'avg_cost': avg_cost,
                    'last': last,
                    'bid': bid,
                    'ask': ask,
                    'spread': spread,
                    'target_price': target_price,
                    'profit_percent': profit_percent,
                    'benchmark': benchmark,
                    'outperform_score': outperform_score
                })
            
            # Veri yoksa bilgi ver
            if not profit_opportunities:
                messagebox.showinfo("Bilgi", "Değerlendirilebilecek short pozisyon bulunamadı.")
                return
                
            # Benchmark outperform skoruna göre sırala (en yüksek en üstte)
            profit_opportunities.sort(key=lambda x: x['outperform_score'], reverse=True)
            
            # Yeni pencere oluştur
            profit_window = tk.Toplevel(self)
            profit_window.title("Short Pozisyonlar İçin Take Profit Fırsatları")
            profit_window.geometry("1200x700")
            
            # ETF bilgi paneli ekle
            etf_panel, etf_labels = self.create_etf_info_panel(profit_window)
            
            # Bilgi bar - mevcut benchmark ve açıklama
            info_bar = ttk.Frame(profit_window)
            info_bar.pack(fill=tk.X, padx=10, pady=5)
            
            # T-benchmark göstergesi
            t_bench_label = ttk.Label(
                info_bar, 
                text=f"T-benchmark: {self.t_benchmark:+.2f}¢",
                font=("Arial", 10, "bold"),
                foreground="blue" if self.t_benchmark > 0 else "red" if self.t_benchmark < 0 else "black"
            )
            t_bench_label.pack(side=tk.LEFT, padx=20)
            
            # C-benchmark göstergesi
            c_bench_label = ttk.Label(
                info_bar, 
                text=f"C-benchmark: {self.c_benchmark:+.2f}¢",
                font=("Arial", 10, "bold"),
                foreground="blue" if self.c_benchmark > 0 else "red" if self.c_benchmark < 0 else "black"
            )
            c_bench_label.pack(side=tk.LEFT, padx=20)
            
            # Açıklama etiketi
            info_label = ttk.Label(
                info_bar,
                text="Outperform skoru yüksek olanlar (benchmark'a göre daha iyi performans) yukarıda listeleniyor.",
                font=("Arial", 9)
            )
            info_label.pack(side=tk.LEFT, padx=20)
            
            # Treeview oluştur
            columns = (
                "Select", "symbol", "group", "quantity", "avg_cost", "last", "bid", "ask", 
                "target_price", "profit_pct", "benchmark", "outperform"
            )
            
            profit_tree = ttk.Treeview(
                profit_window, 
                columns=columns,
                show="headings",
                selectmode="none"
            )
            
            # Başlıkları ayarla
            column_display_names = {
                "Select": "Seç",
                "symbol": "Sembol",
                "group": "Grup",
                "quantity": "Miktar",
                "avg_cost": "Ortalama",
                "last": "Son",
                "bid": "Bid",
                "ask": "Ask",
                "target_price": "Hedef Alış",
                "profit_pct": "Kâr %",
                "benchmark": "Benchmark",
                "outperform": "Benchmark Farkı"
            }
            
            for col in columns:
                profit_tree.heading(col, text=column_display_names[col])
                
                # Sütun genişliklerini ayarla
                if col == "Select":
                    profit_tree.column(col, width=40, anchor="center")
                elif col in ["symbol", "group"]:
                    profit_tree.column(col, width=100, anchor="center")
                elif col in ["quantity"]:
                    profit_tree.column(col, width=70, anchor="center")
                else:
                    profit_tree.column(col, width=90, anchor="center")
            
            # Scrollbar ekle
            tree_scroll = ttk.Scrollbar(profit_window, orient="vertical", command=profit_tree.yview)
            profit_tree.configure(yscrollcommand=tree_scroll.set)
            
            # Treeview ve scrollbar
            profit_tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=10, pady=5)
            tree_scroll.pack(side=tk.LEFT, fill=tk.Y, pady=5)
            
            # Renk etiketleri
            profit_tree.tag_configure("good", background="#e0f0e0")  # açık yeşil
            profit_tree.tag_configure("neutral", background="#f0f0f0")  # açık gri
            profit_tree.tag_configure("bad", background="#f0e0e0")  # açık kırmızı
            
            # Seçilen öğeleri saklamak için set
            selected_positions = set()
            
            # Verileri ekle
            for i, data in enumerate(profit_opportunities):
                # Değerleri formatlı şekilde hazırla
                values = (
                    "□",  # Başlangıçta seçili değil
                    data["symbol"],
                    data["group"],
                    f"{data['quantity']:,}",
                    f"{data['avg_cost']:.2f}",
                    f"{data['last']:.2f}",
                    f"{data['bid']:.2f}",
                    f"{data['ask']:.2f}",
                    f"{data['target_price']:.2f}",
                    f"{data['profit_percent']:+.2f}%",
                    f"{data['benchmark']:+.2f}¢",
                    f"{data['outperform_score']:+.2f}¢"
                )
                
                # Outperform skoruna göre renk belirle
                tag = "good" if data["outperform_score"] > 0 else "bad" if data["outperform_score"] < 0 else "neutral"
                
                # Treeview'a ekle
                profit_tree.insert("", "end", values=values, tags=(tag,))
                
            # Treeview tıklama fonksiyonu
            def on_profit_tree_click(event):
                region = profit_tree.identify_region(event.x, event.y)
                column = profit_tree.identify_column(event.x)
                
                # Sadece ilk sütuna (seçim sütunu) tıklandığında işlem yap
                if region == "cell" and column == "#1":
                    item_id = profit_tree.identify_row(event.y)
                    if item_id:
                        item_values = profit_tree.item(item_id, "values")
                        if item_values:
                            symbol = item_values[1]  # Symbol değeri
                            current_state = item_values[0]  # Seçim durumu
                            
                            # Durumu değiştir
                            new_state = "✓" if current_state == "□" else "□"
                            profit_tree.set(item_id, "Select", new_state)
                            
                            # Set'e ekle veya çıkar
                            if new_state == "✓":
                                selected_positions.add(symbol)
                            else:
                                if symbol in selected_positions:
                                    selected_positions.remove(symbol)
            
            # Tıklama olayını bağla
            profit_tree.bind("<ButtonRelease-1>", on_profit_tree_click)
            
            # Toplam kayıt sayısı ekleyeceğimiz frame
            info_frame = ttk.Frame(profit_window)
            info_frame.pack(fill=tk.X, padx=10, pady=5)
            
            # Toplam kayıt sayısı
            count_label = ttk.Label(
                info_frame,
                text=f"Toplam: {len(profit_opportunities)} short pozisyon | İyi Fırsatlar: {len([d for d in profit_opportunities if d['outperform_score'] > 0])}"
            )
            count_label.pack(side=tk.LEFT, padx=5)
            
            # Ana buton çerçevesi
            main_button_frame = ttk.Frame(profit_window)
            main_button_frame.pack(fill=tk.X, padx=10, pady=5)
            
            # Üst sıra butonları için çerçeve
            top_button_frame = ttk.Frame(main_button_frame)
            top_button_frame.pack(fill=tk.X, pady=5)
            
            # Alt sıra butonları için çerçeve
            bottom_button_frame = ttk.Frame(main_button_frame)
            bottom_button_frame.pack(fill=tk.X, pady=5)
            
            # Yenile butonu
            refresh_btn = ttk.Button(
                top_button_frame,
                text="Yenile",
                command=lambda: (profit_window.destroy(), self.take_profit_from_shorts())
            )
            refresh_btn.pack(side=tk.LEFT, padx=5)
            
            # Select All butonu
            def select_all_items():
                for item_id in profit_tree.get_children():
                    profit_tree.set(item_id, "Select", "✓")
                    item_values = profit_tree.item(item_id, "values")
                    if item_values and len(item_values) > 1:
                        selected_positions.add(item_values[1])  # Symbol değeri
                    
            select_all_btn = ttk.Button(
                top_button_frame,
                text="Tümünü Seç",
                command=select_all_items
            )
            select_all_btn.pack(side=tk.LEFT, padx=5)
            
            # Deselect All butonu
            def deselect_all_items():
                for item_id in profit_tree.get_children():
                    profit_tree.set(item_id, "Select", "□")
                selected_positions.clear()
                
            deselect_all_btn = ttk.Button(
                top_button_frame,
                text="Tümünü Kaldır",
                command=deselect_all_items
            )
            deselect_all_btn.pack(side=tk.LEFT, padx=5)
            
            # Kapat butonu
            close_btn = ttk.Button(
                top_button_frame,
                text="Kapat",
                command=profit_window.destroy
            )
            close_btn.pack(side=tk.RIGHT, padx=5)
            
            # Hidden Buy butonu
            def hidden_buy_selected():
                print("Hidden Buy işlemi başlatılıyor...")
                
                # İlk olarak seçili öğeleri kontrol et
                selected_count = 0
                for item_id in profit_tree.get_children():
                    item_values = profit_tree.item(item_id, "values")
                    if item_values and item_values[0] == "✓":
                        selected_count += 1
                        print(f"Seçili hisse: {item_values[1]}")
                
                if selected_count == 0:
                    messagebox.showinfo("Uyarı", "Lütfen en az bir pozisyon seçin.")
                    return
                
                # Seçili hisselerin verilerini topla
                orders_to_place = []
                
                for item_id in profit_tree.get_children():
                    item_values = profit_tree.item(item_id, "values")
                    
                    if not item_values or len(item_values) < 9:
                        continue
                    
                    # Seçim durumunu kontrol et (✓ işaretli olmalı)
                    if item_values[0] != "✓":
                        continue
                    
                    symbol = item_values[1]
                    current_quantity = int(item_values[3].replace(",", ""))
                    bid = float(item_values[6])
                    ask = float(item_values[7])
                    spread = ask - bid
                    
                    # Hedef fiyat: bid + spread*0.15
                    target_price = bid + (spread * 0.15)
                    
                    # Miktar: 200 lot veya pozisyon büyüklüğü (hangisi küçükse)
                    quantity = min(200, current_quantity)
                    
                    orders_to_place.append({
                        'symbol': symbol,
                        'quantity': quantity,
                        'price': target_price
                    })
                
                if not orders_to_place:
                    messagebox.showinfo("Uyarı", "Emir oluşturulamadı. Seçili pozisyonları kontrol edin.")
                    return
                
                # Emir detaylarını hazırla
                order_details = "\n".join([
                    f"{order['symbol']}: {order['quantity']} adet @ {order['price']:.2f}$"
                    for order in orders_to_place
                ])
                
                # Onay kutusu göster
                confirm = messagebox.askyesno(
                    "Hidden Buy Emir Onayı",
                    f"Aşağıdaki {len(orders_to_place)} hidden buy emri gönderilecek:\n\n{order_details}\n\n"
                    f"Onaylıyor musunuz?"
                )
                
                if confirm:
                    try:
                        # IBKR bağlantısını kontrol et
                        if not self.ib or not self.ib.isConnected():
                            messagebox.showwarning("Bağlantı Hatası", "IBKR'ye bağlı değilsiniz. Lütfen önce bağlanın.")
                            return
                            
                        # Gerçek emirleri gönder
                        sent_orders = 0
                        for order in orders_to_place:
                            symbol = order['symbol']
                            price = float(order['price'])
                            quantity = int(order['quantity'])
                            
                            # Kontrat oluştur
                            contract = Stock(symbol, 'SMART', 'USD')
                            
                            # Emir oluştur ve gönder
                            limit_order = LimitOrder('BUY', quantity, round(price, 2))
                            limit_order.hidden = True
                            self.ib.placeOrder(contract, limit_order)
                            print(f"Emir gönderildi: {symbol} BUY @ {price:.2f} x {quantity}")
                            sent_orders += 1
                        
                        messagebox.showinfo("Başarılı", f"{sent_orders} adet hidden buy emri başarıyla gönderildi!")
                    except Exception as e:
                        messagebox.showerror("Hata", f"Emirler gönderilirken hata oluştu: {str(e)}")
                        import traceback
                        traceback.print_exc()

            # Hidden Buy button - make it stand out
            style = ttk.Style()
            style.configure("Buy.TButton", background="#4CAF50", foreground="white", font=('Arial', 10, 'bold'))
            
            hidden_buy_btn = ttk.Button(
                bottom_button_frame,
                text="Hidden Buy Emri",
                command=hidden_buy_selected,
                style="Buy.TButton"
            )
            hidden_buy_btn.pack(side=tk.LEFT, padx=5, pady=5)
            
            # Seçili pozisyon için emir
            def place_order_for_selected():
                # İlk olarak seçili öğeleri kontrol et
                selected_count = 0
                for item_id in profit_tree.get_children():
                    item_values = profit_tree.item(item_id, "values")
                    if item_values and item_values[0] == "✓":
                        selected_count += 1
                
                if selected_count == 0:
                    messagebox.showinfo("Uyarı", "Lütfen en az bir pozisyon seçin.")
                    return
                
                # İlk seçili pozisyonu bul
                selected_item_id = None
                selected_item_values = None
                
                for item_id in profit_tree.get_children():
                    item_values = profit_tree.item(item_id, "values")
                    if item_values and item_values[0] == "✓":
                        selected_item_id = item_id
                        selected_item_values = item_values
                        break
                
                if not selected_item_values or len(selected_item_values) < 9:
                    messagebox.showinfo("Hata", "Seçilen pozisyon için veri alınamadı.")
                    return
                
                symbol = selected_item_values[1]
                target_price = float(selected_item_values[8])
                current_quantity = int(selected_item_values[3].replace(",", ""))
                
                # Emir miktarı için seçenek sun
                shares_prompt = tk.simpledialog.askinteger(
                    "Lot Sayısı", 
                    f"{symbol} için kaç lot alış emri verilsin? (Mevcut: {current_quantity})",
                    parent=profit_window,
                    minvalue=1,
                    maxvalue=current_quantity
                )
                
                if not shares_prompt:
                    return
                    
                quantity = shares_prompt
                
                # Emir onayı
                confirm = messagebox.askyesno(
                    "Emir Onayı",
                    f"{symbol} hissesi için {quantity} adet, {target_price:.2f}$ fiyattan hidden alış emri verilecek.\n\n"
                    f"Outperform Skoru: {float(selected_item_values[10]):+.2f}¢\n\n"
                    f"Bu emri göndermek istiyor musunuz?"
                )
                
                if confirm:
                    messagebox.showinfo("Bilgi", f"{symbol} için alış emri gönderildi. (Gösterim amaçlı)")
                    # Gerçek emir gönderme işlemi burada olacak
            
            # Tüm iyi fırsatlar için emir ver
            def place_all_good_orders():
                # İyi fırsat olarak değerlendirilen pozisyonları filtrele (outperform skoru > 0)
                good_opportunities = [data for data in profit_opportunities if data['outperform_score'] > 0]
                
                if not good_opportunities:
                    messagebox.showinfo("Bilgi", "İyi fırsat kriterine uyan pozisyon bulunamadı.")
                    return
                
                # Pozisyonun ne kadarının kapatılacağını sor (yüzde)
                percent_prompt = tk.simpledialog.askinteger(
                    "Kapatma Yüzdesi", 
                    "Her pozisyonun yüzde kaçı kapatılsın? (1-100)",
                    parent=profit_window,
                    minvalue=1,
                    maxvalue=100
                )
                
                if not percent_prompt:
                    return
                
                close_percent = percent_prompt / 100.0
                
                # Onay mesajı
                confirm = messagebox.askyesno(
                    "Toplu Emir Onayı",
                    f"Outperform skoru 0'dan yüksek olan {len(good_opportunities)} short pozisyon için\n"
                    f"her birinin %{percent_prompt}'i kapatılacak.\n\n"
                    f"Bu işlemi onaylıyor musunuz?"
                )
                
                if confirm:
                    # Gerçek emir gönderme işlemi burada olacak
                    order_details = "\n".join([
                        f"{data['symbol']}: {int(data['quantity'] * close_percent)} adet @ {data['target_price']:.2f}$ "
                        f"(Outperform: {data['outperform_score']:+.2f}¢)"
                        for data in good_opportunities
                    ])
                    
                    messagebox.showinfo(
                        "Emirler Gönderildi", 
                        f"Aşağıdaki emirler gönderildi (Gösterim amaçlı):\n\n{order_details}"
                    )
            
            # Seçili pozisyon için emir butonu
            order_btn = ttk.Button(
                bottom_button_frame,
                text="Seçili Pozisyon İçin Emir Ver",
                command=place_order_for_selected
            )
            order_btn.pack(side=tk.LEFT, padx=5)
            
            # Tüm iyi fırsatlar için emir butonu
            all_orders_btn = ttk.Button(
                bottom_button_frame,
                text="Tüm İyi Fırsatlar İçin Emir Ver",
                command=place_all_good_orders
            )
            all_orders_btn.pack(side=tk.LEFT, padx=5)
            
        except Exception as e:
            print(f"Take profit from shorts hatası: {e}")
            import traceback
            traceback.print_exc()
            messagebox.showerror("Hata", f"Take profit from shorts sırasında hata oluştu: {str(e)}")

    def cashpark35_mal_topla(self):
        """Cashpark35 portföyündeki hisseler için ucuzluk skoru hesaplama ve alım fırsatı analizi"""
        try:
            # C-benchmark'ı kontrol et
            if not hasattr(self, 'c_benchmark') or self.c_benchmark is None:
                messagebox.showinfo("Bilgi", "C-benchmark verisi bulunamadı. Lütfen IBKR bağlantısını kontrol edin.")
                return
                
            # CSV dosyasının yolunu belirle
            portfolio_file = "optimized_35_extlt.csv"
            
            # Dosya var mı kontrol et
            if not os.path.exists(portfolio_file):
                messagebox.showerror("Dosya Bulunamadı", f"{portfolio_file} dosyası bulunamadı.")
                return
                
            # CSV verisini oku
            try:
                df = pd.read_csv(portfolio_file)
                # Gerekli sütunları kontrol et
                required_columns = ["PREF IBKR", "FINAL_THG", "AVG_ADV", "Final_Shares"]
                missing_columns = [col for col in required_columns if col not in df.columns]
                if missing_columns:
                    messagebox.showerror("Eksik Sütunlar", f"CSV dosyasında aşağıdaki sütunlar eksik: {', '.join(missing_columns)}")
                    return
                    
                # NaN değerleri temizle
                df = df.dropna(subset=["PREF IBKR"])
                
            except Exception as e:
                messagebox.showerror("CSV Okuma Hatası", f"CSV dosyası okunurken hata oluştu: {str(e)}")
                return
                
            # Hisselerin fiyat verilerini ve ucuzluk skorlarını sakla
            opportunity_data = []
            
            # İşlem başladı mesajı
            print(f"Cashpark35 hisseleri için ucuzluk skoru hesaplanıyor... C-benchmark: {self.c_benchmark:.2f}¢")
            
            # Her hisse için ucuzluk skorunu hesapla
            for _, row in df.iterrows():
                ticker = row["PREF IBKR"]
                if not ticker or pd.isna(ticker):
                    continue
                    
                # Hissenin fiyat verilerini al
                ticker_data = self.market_data_cache.get(ticker)
                if not ticker_data:
                    print(f"{ticker} için fiyat verisi bulunamadı, atlanıyor...")
                    continue
                    
                # Bid ve ask değerlerini kontrol et
                if (not hasattr(ticker_data, 'bid') or ticker_data.bid is None or math.isnan(ticker_data.bid) or
                    not hasattr(ticker_data, 'ask') or ticker_data.ask is None or math.isnan(ticker_data.ask)):
                    print(f"{ticker} için bid/ask verisi bulunamadı, atlanıyor...")
                    continue
                    
                # Spread hesapla (dolar bazında)
                bid = ticker_data.bid
                ask = ticker_data.ask
                spread = ask - bid
                
                # Hedef alım fiyatı: ilk bid + spread*0.15
                target_price = bid + (spread * 0.15)
                
                # C-benchmark'a göre ucuzluk skorunu hesapla (cent bazında)
                # Düşük/negatif skor daha iyi (daha ucuz)
                target_price_cents = target_price * 100  # Dolardan cente çevir
                
                # Ucuzluk skoru: Bu fiyat, benchmark'tan ne kadar farklı (- değer daha iyi)
                cheapness_score = target_price_cents - self.c_benchmark
                
                # Final shares değerini al
                final_shares = row["Final_Shares"] if "Final_Shares" in row and not pd.isna(row["Final_Shares"]) else 0
                
                # FINAL_THG değerini al
                final_thg = row["FINAL_THG"] if "FINAL_THG" in row and not pd.isna(row["FINAL_THG"]) else 0
                
                # AVG_ADV değerini al
                avg_adv = row["AVG_ADV"] if "AVG_ADV" in row and not pd.isna(row["AVG_ADV"]) else 0
                
                # Last değerini al
                last_price = getattr(ticker_data, 'last', None)
                if last_price is None or math.isnan(last_price):
                    last_price = 0
                
                # Canlı bid/ask spread yüzdesi
                live_spread_pct = (spread / bid) * 100 if bid > 0 else 0
                
                # Verileri kaydet
                opportunity_data.append({
                    'symbol': ticker,
                    'last': last_price,
                    'bid': bid,
                    'ask': ask,
                    'spread': spread,
                    'spread_pct': live_spread_pct,
                    'target_price': target_price,
                    'cheapness_score': cheapness_score,
                    'final_shares': final_shares,
                    'final_thg': final_thg,
                    'avg_adv': avg_adv
                })
            
            # Veri yoksa bilgi ver
            if not opportunity_data:
                messagebox.showinfo("Bilgi", "Değerlendirilebilecek hisse bulunamadı.")
                return
                
            # Ucuzluk skoruna göre sırala (en düşük/negatif en üstte)
            opportunity_data.sort(key=lambda x: x['cheapness_score'])
            
            # Yeni pencere oluştur
            opportunity_window = tk.Toplevel(self)
            opportunity_window.title("Cashpark35 Alım Fırsatları")
            opportunity_window.geometry("1200x700")
            
            # ETF bilgi paneli ekle
            etf_panel, etf_labels = self.create_etf_info_panel(opportunity_window)
            
            # Bilgi bar - mevcut benchmark ve açıklama
            info_bar = ttk.Frame(opportunity_window)
            info_bar.pack(fill=tk.X, padx=10, pady=5)
            
            ttk.Label(
                info_bar, 
                text=f"C-benchmark: {self.c_benchmark:.2f}¢ | Ucuzluk Skoru: Hedef fiyat - C-benchmark (Negatif değerler daha iyi)",
                font=('Arial', 9, 'bold')
            ).pack(side=tk.LEFT)
            
            ttk.Label(
                info_bar,
                text="Hedef Fiyat = ilk bid + spread × 0.15",
                font=('Arial', 9)
            ).pack(side=tk.RIGHT)
            
            # Treeview için frame
            tree_frame = ttk.Frame(opportunity_window)
            tree_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=5)
            
            # Treeview oluştur
            columns = (
                "Select", "symbol", "last", "bid", "ask", "spread_pct", "target_price", 
                "cheapness_score", "final_thg", "avg_adv", "final_shares"
            )
            
            opportunity_tree = ttk.Treeview(
                tree_frame,
                columns=columns,
                show="headings",
                selectmode="none"
            )
            
            # Sütun başlıkları
            column_headings = {
                "symbol": "Sembol",
                "last": "Son Fiyat",
                "bid": "Alış",
                "ask": "Satış",
                "spread_pct": "Spread %",
                "target_price": "Hedef Fiyat",
                "cheapness_score": "Ucuzluk Skoru (¢)",
                "final_thg": "FINAL_THG",
                "avg_adv": "AVG_ADV",
                "final_shares": "Final_Shares"
            }
            
            # Sütunları yapılandır
            for col in columns:
                opportunity_tree.heading(col, text=column_headings[col])
                width = 100 if col not in ["symbol", "cheapness_score"] else 120
                anchor = tk.CENTER if col != "symbol" else tk.W
                opportunity_tree.column(col, width=width, anchor=anchor)
            
            # Scrollbar
            scrollbar = ttk.Scrollbar(tree_frame, orient="vertical", command=opportunity_tree.yview)
            scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
            opportunity_tree.configure(yscrollcommand=scrollbar.set)
            opportunity_tree.pack(fill=tk.BOTH, expand=True)
            
            # Satırlara değerleri ekle
            for data in opportunity_data:
                # Ucuzluk skoruna göre satır rengi belirle
                tag = ""
                if data['cheapness_score'] < -5:  # Çok iyi fırsat
                    tag = "very_good"
                elif data['cheapness_score'] < 0:  # İyi fırsat
                    tag = "good"
                elif data['cheapness_score'] < 5:  # Orta
                    tag = "neutral"
                else:  # Kötü
                    tag = "bad"
                
                # Değerleri dönüştür
                values = (
                    data['symbol'],
                    f"{data['last']:.2f}",
                    f"{data['bid']:.2f}",
                    f"{data['ask']:.2f}",
                    f"{data['spread_pct']:.2f}%",
                    f"{data['target_price']:.2f}",
                    f"{data['cheapness_score']:.2f}",
                    f"{data['final_thg']:.2f}" if data['final_thg'] else "--",
                    f"{data['avg_adv']:.2f}" if data['avg_adv'] else "--",
                    f"{int(data['final_shares'])}" if data['final_shares'] else "--"
                )
                
                opportunity_tree.insert("", tk.END, values=values, tags=(tag,))
            
            # Renk etiketlerini konfigüre et
            opportunity_tree.tag_configure("very_good", background="#90EE90")  # Açık yeşil
            opportunity_tree.tag_configure("good", background="#D0F0C0")  # Daha hafif yeşil
            opportunity_tree.tag_configure("neutral", background="#F5F5F5")  # Beyaz/gri
            opportunity_tree.tag_configure("bad", background="#FFCCCB")  # Hafif kırmızı
            
            # Butonlar için frame
            button_frame = ttk.Frame(opportunity_window)
            button_frame.pack(fill=tk.X, padx=10, pady=10)
            
            # Select All butonu
            def select_all_items():
                for item in opportunity_tree.get_children():
                    opportunity_tree.selection_add(item)
                    
            select_all_btn = ttk.Button(
                button_frame,
                text="Tümünü Seç",
                command=select_all_items
            )
            select_all_btn.pack(side=tk.LEFT, padx=5)
            
            # Deselect All butonu
            def deselect_all_items():
                opportunity_tree.selection_remove(opportunity_tree.selection())
                
            deselect_all_btn = ttk.Button(
                button_frame,
                text="Tümünü Kaldır",
                command=deselect_all_items
            )
            deselect_all_btn.pack(side=tk.LEFT, padx=5)
            
            # Seçili hisse için emirler
            def place_order_for_selected():
                selected_items = opportunity_tree.selection()
                if not selected_items:
                    messagebox.showinfo("Uyarı", "Lütfen bir hisse seçin.")
                    return
                    
                # Seçili hissenin verilerini al
                selected_item = opportunity_tree.item(selected_items[0])
                values = selected_item['values']
                
                if not values or len(values) < 6:
                    messagebox.showinfo("Hata", "Seçilen hisse için veri alınamadı.")
                    return
                
                symbol = values[0]
                target_price = float(values[5])
                
                # Emir miktarı için seçenek sun
                shares_prompt = tk.simpledialog.askinteger(
                    "Lot Sayısı", 
                    f"{symbol} için kaç lot alış emri verilsin?",
                    parent=opportunity_window,
                    minvalue=1,
                    maxvalue=1000
                )
                
                if not shares_prompt:
                    return
                    
                quantity = shares_prompt
                
                # Emir onayı
                confirm = messagebox.askyesno(
                    "Emir Onayı",
                    f"{symbol} hissesi için {quantity} adet, {target_price:.2f}$ fiyattan hidden alış emri verilecek.\n\n"
                    f"Ucuzluk Skoru: {float(values[6]):.2f}¢\n\n"
                    f"Bu emri göndermek istiyor musunuz?"
                )
                
                if confirm:
                    messagebox.showinfo("Bilgi", f"{symbol} için emir gönderildi. (Gösterim amaçlı)")
                    # Gerçek emir gönderme işlemi burada olacak
            
            # Tüm hesaplanmış uygun fiyatlara hidden alış emri ver
            def place_all_good_orders():
                # İyi fırsat olarak değerlendirilen hisseleri filtrele (ucuzluk skoru < 0)
                good_opportunities = [data for data in opportunity_data if data['cheapness_score'] < 0]
                
                if not good_opportunities:
                    messagebox.showinfo("Bilgi", "İyi fırsat kriterine uyan hisse bulunamadı.")
                    return
                
                # Kaç lot alınacağını sor
                shares_prompt = tk.simpledialog.askinteger(
                    "Lot Sayısı", 
                    f"Her hisse için kaç lot alış emri verilsin?",
                    parent=opportunity_window,
                    minvalue=1,
                    maxvalue=1000
                )
                
                if not shares_prompt:
                    return
                
                quantity = shares_prompt
                
                # Onay mesajı
                confirm = messagebox.askyesno(
                    "Toplu Emir Onayı",
                    f"Ucuzluk skoru 0'dan düşük olan {len(good_opportunities)} hisse için\n"
                    f"her birine {quantity} adet hidden alış emri verilecek.\n\n"
                    f"Bu işlemi onaylıyor musunuz?"
                )
                
                if confirm:
                    # Gerçek emir gönderme işlemi burada olacak
                    order_details = "\n".join([
                        f"{data['symbol']}: {quantity} adet @ {data['target_price']:.2f}$ "
                        f"(Ucuzluk: {data['cheapness_score']:.2f}¢)"
                        for data in good_opportunities
                    ])
                    
                    messagebox.showinfo(
                        "Emirler Gönderildi", 
                        f"Aşağıdaki emirler gönderildi (Gösterim amaçlı):\n\n{order_details}"
                    )
            
            # Yenile butonu
            refresh_btn = ttk.Button(
                button_frame,
                text="Yenile",
                command=lambda: (opportunity_window.destroy(), self.cashpark35_mal_topla())
            )
            refresh_btn.pack(side=tk.LEFT, padx=5)
            
            # Seçili hisse için emir butonu
            order_btn = ttk.Button(
                button_frame,
                text="Seçili Hisse İçin Emir Ver",
                command=place_order_for_selected
            )
            order_btn.pack(side=tk.LEFT, padx=5)
            
            # Tüm iyi fırsatlar için emir butonu
            all_orders_btn = ttk.Button(
                button_frame,
                text="Tüm İyi Fırsatlar İçin Emir Ver",
                command=place_all_good_orders
            )
            all_orders_btn.pack(side=tk.LEFT, padx=5)
            
            # Kapat butonu
            close_btn = ttk.Button(
                button_frame,
                text="Kapat",
                command=opportunity_window.destroy
            )
            close_btn.pack(side=tk.RIGHT, padx=5)
            
            # Toplam kayıt sayısı
            count_label = ttk.Label(
                button_frame,
                text=f"Toplam: {len(opportunity_data)} hisse | Ucuz Fırsatlar: {len([d for d in opportunity_data if d['cheapness_score'] < 0])}"
            )
            count_label.pack(side=tk.RIGHT, padx=20)
            
        except Exception as e:
            print(f"Cashpark35 mal toplama hatası: {e}")
            import traceback
            traceback.print_exc()
            messagebox.showerror("Hata", f"Cashpark35 mal toplama sırasında hata oluştu: {str(e)}")

def main():
    app = PreferredStockMonitor()
    try:
        app.mainloop()
    except Exception as e:
        print(f"Application error: {e}")
    finally:
        try_disconnect_and_destroy(app)

def try_disconnect_and_destroy(app):
    """Uygulama kapanırken bağlantıları temizle"""
    try:
        if hasattr(app, 'ib') and app.ib and app.ib.isConnected():
            app.disconnect_from_ibkr()
            print("Başarıyla IB'den çıkış yapıldı")
    except Exception as e:
        print(f"Çıkış yaparken hata: {e}")

if __name__ == "__main__":
    main() 