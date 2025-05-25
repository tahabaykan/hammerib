import tkinter as tk
from tkinter import ttk
import pandas as pd
import threading
import time
from hammerib.gui.etf_panel import ETFPanel
from hammerib.ib_api.manager import ETF_SYMBOLS
from ib_insync import LimitOrder, Stock  # GEREKLİ İMPORT
from tkinter import messagebox  # messagebox fix

CHECKED = '\u2611'  # ☑
UNCHECKED = '\u2610'  # ☐

class MaltoplaWindow(tk.Toplevel):
    def __init__(self, parent, ibkr_manager, csv_path, benchmark_type):
        super().__init__(parent)
        self.title(f"{csv_path} Maltopla Analiz")
        self.ibkr = ibkr_manager
        self.csv_path = csv_path
        self.benchmark_type = benchmark_type  # 'T' or 'C'
        self.ticker_info = self.load_tickers_info()  # symbol -> dict with csv data
        self.tickers = list(self.ticker_info.keys())
        self.items_per_page = 20
        self.page = 0
        self.max_page = max(0, (len(self.tickers) - 1) // self.items_per_page)
        self.ticker_cache = {}  # symbol -> data dict
        self.ticker_handlers = {}  # symbol -> handler ref
        self.checked_tickers = set()
        self.etf_panel = ETFPanel(self, ETF_SYMBOLS, compact=True)
        self.etf_panel.pack(fill='x', padx=2, pady=2)
        self.after(1000, self.update_etf_panel)
        self.table = ttk.Treeview(self, columns=(
            'Seç', 'Ticker', 'Bid', 'Ask', 'Prev Close', 'TP Price', 'CPF', 'Skor',
            'FINAL_THG', 'Final_Shares', 'Mevcut Shares'), show='headings', height=20)
        for col in ('Seç', 'Ticker', 'Bid', 'Ask', 'Prev Close', 'TP Price', 'CPF', 'Skor',
                    'FINAL_THG', 'Final_Shares', 'Mevcut Shares'):
            self.table.heading(col, text=col)
            self.table.column(col, width=90 if col=='Seç' else 110, anchor='center')
        self.table.pack(fill='both', expand=True)
        self.table.bind('<Button-1>', self.on_table_click)
        # Selection buttons
        sel_frame = ttk.Frame(self)
        sel_frame.pack(fill='x', pady=2)
        btn_select_all = ttk.Button(sel_frame, text='Tümünü Seç', command=self.select_all)
        btn_select_all.pack(side='left', padx=2)
        btn_deselect_all = ttk.Button(sel_frame, text='Tümünü Kaldır', command=self.deselect_all)
        btn_deselect_all.pack(side='left', padx=2)
        # Navigation
        nav = ttk.Frame(self)
        nav.pack(fill='x')
        self.btn_prev = ttk.Button(nav, text='<', command=self.prev_page)
        self.btn_prev.pack(side='left', padx=5)
        self.lbl_page = ttk.Label(nav, text=f'Page {self.page+1}')
        self.lbl_page.pack(side='left', padx=5)
        self.btn_next = ttk.Button(nav, text='>', command=self.next_page)
        self.btn_next.pack(side='left', padx=5)
        # Action buttons
        action_frame = ttk.Frame(self)
        action_frame.pack(fill='x', pady=4)
        btn_spr_hidden_bid = ttk.Button(action_frame, text='spr hidden bid', command=self.on_spr_hidden_bid)
        btn_spr_hidden_bid.pack(side='left', padx=2)
        btn_spr_hidden_ask = ttk.Button(action_frame, text='spr hidden ask', command=self.on_spr_hidden_ask)
        btn_spr_hidden_ask.pack(side='left', padx=2)
        btn_adj_hidden_bid = ttk.Button(action_frame, text='adj hidden bid', command=self.on_adj_hidden_bid)
        btn_adj_hidden_bid.pack(side='left', padx=2)
        btn_adj_hidden_ask = ttk.Button(action_frame, text='adj hidden ask', command=self.on_adj_hidden_ask)
        btn_adj_hidden_ask.pack(side='left', padx=2)
        self.protocol('WM_DELETE_WINDOW', self.on_close)
        self._running = True
        self.subscribe_visible()
        self.populate_table_from_cache()

    def load_tickers_info(self):
        info = {}
        try:
            df = pd.read_csv(self.csv_path)
            # Kolon isimlerini normalize et
            cols = [c.strip() for c in df.columns]
            df.columns = cols
            for _, row in df.iterrows():
                symbol = row['PREF IBKR'] if 'PREF IBKR' in row and pd.notna(row['PREF IBKR']) else row.iloc[0]
                if pd.isna(symbol):
                    continue
                info[symbol] = {
                    'FINAL_THG': row['FINAL_THG'] if 'FINAL_THG' in row else '',
                    'Final_Shares': row['Final_Shares'] if 'Final_Shares' in row else '',
                }
        except Exception:
            pass
        return info

    def get_visible_tickers(self):
        start = self.page * self.items_per_page
        end = min(start + self.items_per_page, len(self.tickers))
        return self.tickers[start:end]

    def subscribe_visible(self):
        # Unsubscribe old
        for symbol in list(self.ticker_handlers.keys()):
            if symbol not in self.get_visible_tickers():
                handler = self.ticker_handlers.pop(symbol, None)
                ticker_obj = self.ibkr.tickers.get(symbol, {}).get('ticker')
                if ticker_obj and handler:
                    try:
                        ticker_obj.updateEvent -= handler
                    except Exception:
                        pass
        # Subscribe new
        self.ibkr.subscribe_tickers(self.get_visible_tickers())
        for symbol in self.get_visible_tickers():
            ticker_obj = self.ibkr.tickers.get(symbol, {}).get('ticker')
            if ticker_obj and symbol not in self.ticker_handlers:
                def make_handler(sym):
                    def handler(ticker):
                        self.on_ticker_update(sym, ticker)
                    return handler
                handler = make_handler(symbol)
                ticker_obj.updateEvent += handler
                self.ticker_handlers[symbol] = handler
        self.populate_table_from_cache()

    def on_ticker_update(self, symbol, ticker):
        # Update cache
        prev_close = self.ibkr.prev_closes.get(symbol)
        self.ticker_cache[symbol] = {
            'bid': ticker.bid,
            'ask': ticker.ask,
            'last': ticker.last,
            'prev_close': prev_close,
            'timestamp': time.time()
        }
        self.update_row(symbol)

    def populate_table_from_cache(self):
        self.table.delete(*self.table.get_children())
        # Tüm tickerlar için skor hesapla
        scored_tickers = []
        for symbol in self.tickers:
            d = self.ticker_cache.get(symbol, {})
            bid = d.get('bid', 'N/A')
            ask = d.get('ask', 'N/A')
            prev_close = d.get('prev_close', 'N/A')
            try:
                bid = float(bid)
                ask = float(ask)
                prev_close = float(prev_close)
                spread = ask - bid
                tp_price = round(bid + spread * 0.15, 3)
                cpf = round(tp_price - prev_close, 3)
                if self.benchmark_type == 'T':
                    etf_data = self.ibkr.get_etf_data()
                    pff_chg = etf_data.get('PFF', {}).get('change', 0) or 0
                    tlt_chg = etf_data.get('TLT', {}).get('change', 0) or 0
                    benchmark_change = round(pff_chg * 0.7 + tlt_chg * 0.1, 3)
                else:
                    etf_data = self.ibkr.get_etf_data()
                    pff_chg = etf_data.get('PFF', {}).get('change', 0) or 0
                    tlt_chg = etf_data.get('TLT', {}).get('change', 0) or 0
                    benchmark_change = round(pff_chg * 1.3 - tlt_chg * 0.1, 3)
                skor = round(benchmark_change - cpf, 3)
            except Exception:
                skor = -99999
            scored_tickers.append({
                'symbol': symbol,
                'bid': bid,
                'ask': ask,
                'prev_close': prev_close,
                'tp_price': tp_price if 'tp_price' in locals() else 'N/A',
                'cpf': cpf if 'cpf' in locals() else 'N/A',
                'skor': skor
            })
        # Skor'a göre yüksekten düşüğe sırala
        scored_tickers.sort(key=lambda x: x['skor'], reverse=True)
        # Sadece görünen sayfadaki tickerları göster
        start = self.page * self.items_per_page
        end = min(start + self.items_per_page, len(scored_tickers))
        for ticker in scored_tickers[start:end]:
            self.insert_or_update_row(ticker['symbol'])
        self.lbl_page.config(text=f'Page {self.page+1} / {max(1, (len(scored_tickers)-1)//self.items_per_page+1)}')

    def insert_or_update_row(self, symbol):
        d = self.ticker_cache.get(symbol, {})
        bid = d.get('bid', 'N/A')
        ask = d.get('ask', 'N/A')
        prev_close = d.get('prev_close', 'N/A')
        checked = CHECKED if symbol in self.checked_tickers else UNCHECKED
        # TP Price (alım için): bid+spr*0.15
        if bid is not None and ask is not None and prev_close is not None and bid != 'N/A' and ask != 'N/A' and prev_close != 'N/A':
            try:
                bid = float(bid)
                ask = float(ask)
                prev_close = float(prev_close)
                spread = ask - bid
                tp_price = round(bid + spread * 0.15, 3)
                cpf = round(tp_price - prev_close, 3)
                # Benchmark change (günlük değişim)
                if self.benchmark_type == 'T':
                    # T-benchmark change = PFF daily change * 0.7 + TLT daily change * 0.1
                    etf_data = self.ibkr.get_etf_data()
                    pff_chg = etf_data.get('PFF', {}).get('change', 0) or 0
                    tlt_chg = etf_data.get('TLT', {}).get('change', 0) or 0
                    benchmark_change = round(pff_chg * 0.7 + tlt_chg * 0.1, 3)
                else:
                    # C-benchmark change = PFF daily change * 1.3 - TLT daily change * 0.1
                    etf_data = self.ibkr.get_etf_data()
                    pff_chg = etf_data.get('PFF', {}).get('change', 0) or 0
                    tlt_chg = etf_data.get('TLT', {}).get('change', 0) or 0
                    benchmark_change = round(pff_chg * 1.3 - tlt_chg * 0.1, 3)
                skor = round(benchmark_change - cpf, 3)
            except Exception:
                tp_price = 'N/A'
                cpf = 'N/A'
                skor = 'N/A'
        else:
            tp_price = 'N/A'
            cpf = 'N/A'
            skor = 'N/A'
        # CSV'den FINAL_THG ve Final_Shares
        final_thg = self.ticker_info.get(symbol, {}).get('FINAL_THG', '')
        final_shares = self.ticker_info.get(symbol, {}).get('Final_Shares', '')
        # Mevcut Shares (IBKR pozisyonlarından)
        mevcut_shares = 0
        for pos in self.ibkr.get_positions():
            if pos['symbol'] == symbol:
                mevcut_shares = pos['quantity']
                break
        values = (checked, symbol, bid, ask, prev_close, tp_price, cpf, skor,
                  final_thg, final_shares, mevcut_shares)
        if self.table.exists(symbol):
            self.table.item(symbol, values=values)
        else:
            self.table.insert('', 'end', iid=symbol, values=values)

    def update_row(self, symbol):
        self.insert_or_update_row(symbol)

    def on_table_click(self, event):
        region = self.table.identify('region', event.x, event.y)
        if region != 'cell':
            return
        col = self.table.identify_column(event.x)
        if col != '#1':  # Only first column (checkbox)
            return
        row = self.table.identify_row(event.y)
        if not row:
            return
        symbol = self.table.item(row, 'values')[1]
        if symbol in self.checked_tickers:
            self.checked_tickers.remove(symbol)
        else:
            self.checked_tickers.add(symbol)
        self.update_row(symbol)

    def prev_page(self):
        if self.page > 0:
            self.page -= 1
            self.lbl_page.config(text=f'Page {self.page+1}')
            self.subscribe_visible()

    def next_page(self):
        if self.page < self.max_page:
            self.page += 1
            self.lbl_page.config(text=f'Page {self.page+1}')
            self.subscribe_visible()

    def select_all(self):
        for symbol in self.get_visible_tickers():
            self.checked_tickers.add(symbol)
            self.update_row(symbol)

    def deselect_all(self):
        for symbol in self.get_visible_tickers():
            if symbol in self.checked_tickers:
                self.checked_tickers.remove(symbol)
            self.update_row(symbol)

    def get_selected_tickers(self):
        return list(self.checked_tickers)

    def on_spr_hidden_bid(self):
        selected = self.get_selected_tickers()
        if not selected:
            messagebox.showinfo('Uyarı', 'Lütfen en az bir hisse seçin.')
            return
        sent_orders = 0
        errors = []
        for symbol in selected:
            d = self.ticker_cache.get(symbol, {})
            bid = d.get('bid')
            ask = d.get('ask')
            if bid is None or ask is None or bid == 'N/A' or ask == 'N/A':
                errors.append(f"{symbol}: Fiyat verisi yok.")
                continue
            try:
                bid = float(bid)
                ask = float(ask)
                price = round(bid + (ask - bid) * 0.15, 2)
                contract = Stock(symbol, 'SMART', 'USD')
                order = LimitOrder('BUY', 200, price)
                order.hidden = True
                self.ibkr.ib.placeOrder(contract, order)
                sent_orders += 1
            except Exception as e:
                errors.append(f"{symbol}: {e}")
        msg = f"{sent_orders} adet hidden buy emri gönderildi."
        if errors:
            msg += "\nHatalar:\n" + "\n".join(errors)
        messagebox.showinfo('Emir Sonucu', msg)

    def on_spr_hidden_ask(self):
        selected = self.get_selected_tickers()
        if not selected:
            messagebox.showinfo('Uyarı', 'Lütfen en az bir hisse seçin.')
            return
        sent_orders = 0
        errors = []
        for symbol in selected:
            d = self.ticker_cache.get(symbol, {})
            bid = d.get('bid')
            ask = d.get('ask')
            if bid is None or ask is None or bid == 'N/A' or ask == 'N/A':
                errors.append(f"{symbol}: Fiyat verisi yok.")
                continue
            try:
                bid = float(bid)
                ask = float(ask)
                price = round(ask - (ask - bid) * 0.15, 2)
                contract = Stock(symbol, 'SMART', 'USD')
                order = LimitOrder('SELL', 200, price)
                order.hidden = True
                self.ibkr.ib.placeOrder(contract, order)
                sent_orders += 1
            except Exception as e:
                errors.append(f"{symbol}: {e}")
        msg = f"{sent_orders} adet hidden sell emri gönderildi."
        if errors:
            msg += "\nHatalar:\n" + "\n".join(errors)
        messagebox.showinfo('Emir Sonucu', msg)

    def on_adj_hidden_bid(self):
        print('adj hidden bid:', self.get_selected_tickers())
    def on_adj_hidden_ask(self):
        print('adj hidden ask:', self.get_selected_tickers())

    def on_close(self):
        self._running = False
        # Unsubscribe all event handlers
        for symbol, handler in self.ticker_handlers.items():
            ticker_obj = self.ibkr.tickers.get(symbol, {}).get('ticker')
            if ticker_obj and handler:
                try:
                    ticker_obj.updateEvent -= handler
                except Exception:
                    pass
        self.ticker_handlers.clear()
        if self.ibkr and hasattr(self.ibkr, 'clear_subscriptions'):
            self.ibkr.clear_subscriptions()
        self.destroy()

    def update_etf_panel(self):
        etf_data = self.ibkr.get_etf_data()
        self.etf_panel.update(etf_data)
        self.after(1000, self.update_etf_panel) 