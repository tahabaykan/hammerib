import tkinter as tk
from tkinter import ttk
import threading
import pandas as pd
from hammerib.ib_api.manager import IBKRManager, ETF_SYMBOLS
import time
from hammerib.gui.etf_panel import ETFPanel
from hammerib.gui.opt_buttons import create_opt_buttons
from hammerib.gui.benchmark_panel import BenchmarkPanel
from hammerib.gui.maltopla_window import MaltoplaWindow
from hammerib.gui.pos_orders_buttons import create_pos_orders_buttons
from hammerib.gui.top_movers_buttons import create_top_movers_buttons
from hammerib.gui.orderable_table import OrderableTableFrame

class MainWindow(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("Stock Tracker Modular")
        self.ibkr = IBKRManager()
        self.historical_tickers = pd.read_csv('historical_data.csv')['PREF IBKR'].dropna().tolist()
        self.extended_tickers = pd.read_csv('extlthistorical.csv')['PREF IBKR'].dropna().tolist()
        self.items_per_page = 20
        self.historical_page = 0
        self.extended_page = 0
        self.active_tab = 0  # 0: historical, 1: extended
        self.etf_panel = ETFPanel(self, ETF_SYMBOLS, compact=True)
        self.etf_panel.pack(fill='x', padx=5, pady=2)
        self.loop_running = False
        self.loop_job = None
        self.setup_ui()
        # Create BenchmarkPanel instances after setup_ui() so that historical_frame and extended_frame exist
        self.historical_benchmark = BenchmarkPanel(self.historical_frame)
        self.historical_benchmark.pack(fill='x', padx=5, pady=5)
        self.extended_benchmark = BenchmarkPanel(self.extended_frame)
        self.extended_benchmark.pack(fill='x', padx=5, pady=5)
        self.data_thread = None
        self.after(1000, self.update_etf_panel)

    def setup_ui(self):
        top = ttk.Frame(self)
        top.pack(fill='x')
        self.btn_connect = ttk.Button(top, text="IBKR'ye Bağlan", command=self.connect_ibkr)
        self.btn_connect.pack(side='left', padx=5)
        self.btn_loop = ttk.Button(top, text='Döngü Başlat', command=self.toggle_loop)
        self.btn_loop.pack(side='left', padx=5)
        create_opt_buttons(top, self)
        create_pos_orders_buttons(top, self)
        create_top_movers_buttons(top, self)
        self.btn_take_profit_longs = ttk.Button(top, text='Take Profit Longs', command=self.open_take_profit_longs_window)
        self.btn_take_profit_longs.pack(side='left', padx=2)
        self.btn_take_profit_shorts = ttk.Button(top, text='Take Profit Shorts', command=self.open_take_profit_shorts_window)
        self.btn_take_profit_shorts.pack(side='left', padx=2)
        self.status_label = ttk.Label(top, text="Durum: Bekleniyor")
        self.status_label.pack(side='left', padx=10)
        self.notebook = ttk.Notebook(self)
        self.notebook.pack(fill='both', expand=True)
        # Historical tab
        self.historical_frame = ttk.Frame(self.notebook)
        self.historical_table = self.create_table(self.historical_frame)
        self.historical_nav = self.create_nav(self.historical_frame, self.prev_historical, self.next_historical)
        self.notebook.add(self.historical_frame, text="T-prefs")
        # Extended tab
        self.extended_frame = ttk.Frame(self.notebook)
        self.extended_table = self.create_table(self.extended_frame)
        self.extended_nav = self.create_nav(self.extended_frame, self.prev_extended, self.next_extended)
        self.notebook.add(self.extended_frame, text="C-prefs")
        self.notebook.bind("<<NotebookTabChanged>>", self.on_tab_changed)
        self.update_tables()

    def create_table(self, parent):
        columns = ('Ticker', 'Bid', 'Ask', 'Last', 'Volume')
        table = ttk.Treeview(parent, columns=columns, show='headings', height=20)
        for col in columns:
            table.heading(col, text=col)
            table.column(col, width=100, anchor='center')
        table.pack(fill='both', expand=True)
        return table

    def create_nav(self, parent, prev_cmd, next_cmd):
        nav = ttk.Frame(parent)
        nav.pack(fill='x')
        btn_prev = ttk.Button(nav, text="<", command=prev_cmd)
        btn_prev.pack(side='left', padx=5)
        lbl = ttk.Label(nav, text="Page 1")
        lbl.pack(side='left', padx=5)
        btn_next = ttk.Button(nav, text=">", command=next_cmd)
        btn_next.pack(side='left', padx=5)
        return {'frame': nav, 'btn_prev': btn_prev, 'btn_next': btn_next, 'lbl': lbl}

    def connect_ibkr(self):
        self.ibkr.connect()
        self.status_label.config(text="Durum: IBKR'ye bağlı")
        self.subscribe_visible()
        if not self.data_thread:
            self.data_thread = threading.Thread(target=self.update_data_loop, daemon=True)
            self.data_thread.start()

    def subscribe_visible(self):
        if not self.ibkr.connected:
            return
        if self.active_tab == 0:
            tickers = self.get_visible_tickers(self.historical_tickers, self.historical_page)
        else:
            tickers = self.get_visible_tickers(self.extended_tickers, self.extended_page)
        self.ibkr.clear_subscriptions()
        self.ibkr.subscribe_tickers(tickers)

    def get_visible_tickers(self, ticker_list, page):
        start = page * self.items_per_page
        end = min(start + self.items_per_page, len(ticker_list))
        return ticker_list[start:end]

    def update_tables(self):
        # Historical
        self.update_table(self.historical_table, self.historical_tickers, self.historical_page)
        self.historical_nav['lbl'].config(text=f"Page {self.historical_page + 1}")
        # Extended
        self.update_table(self.extended_table, self.extended_tickers, self.extended_page)
        self.extended_nav['lbl'].config(text=f"Page {self.extended_page + 1}")

    def update_table(self, table, ticker_list, page):
        for item in table.get_children():
            table.delete(item)
        for ticker in self.get_visible_tickers(ticker_list, page):
            table.insert('', 'end', values=(ticker, 'N/A', 'N/A', 'N/A', 'N/A'))

    def update_data_loop(self):
        while True:
            if self.active_tab == 0:
                tickers = self.get_visible_tickers(self.historical_tickers, self.historical_page)
                table = self.historical_table
                benchmark_panel = self.historical_benchmark
            else:
                tickers = self.get_visible_tickers(self.extended_tickers, self.extended_page)
                table = self.extended_table
                benchmark_panel = self.extended_benchmark
            data = self.ibkr.get_market_data(tickers)
            for item in table.get_children():
                try:
                    ticker = table.item(item)['values'][0]
                    d = data.get(ticker)
                    if d:
                        table.item(item, values=(ticker, d['bid'], d['ask'], d['last'], d['volume']))
                except tk.TclError:
                    # Item not found, skip
                    pass
            benchmark_data = self.ibkr.calculate_benchmarks()
            benchmark_panel.update(benchmark_data)
            time.sleep(1)

    def prev_historical(self):
        if self.historical_page > 0:
            self.historical_page -= 1
            self.update_tables()
            if self.active_tab == 0:
                self.subscribe_visible()

    def next_historical(self):
        max_page = (len(self.historical_tickers) - 1) // self.items_per_page
        if self.historical_page < max_page:
            self.historical_page += 1
            self.update_tables()
            if self.active_tab == 0:
                self.subscribe_visible()

    def prev_extended(self):
        if self.extended_page > 0:
            self.extended_page -= 1
            self.update_tables()
            if self.active_tab == 1:
                self.subscribe_visible()

    def next_extended(self):
        max_page = (len(self.extended_tickers) - 1) // self.items_per_page
        if self.extended_page < max_page:
            self.extended_page += 1
            self.update_tables()
            if self.active_tab == 1:
                self.subscribe_visible()

    def on_tab_changed(self, event):
        self.active_tab = self.notebook.index(self.notebook.select())
        self.subscribe_visible()

    def update_etf_panel(self):
        etf_data = self.ibkr.get_etf_data()
        self.etf_panel.update(etf_data)
        self.after(1000, self.update_etf_panel)

    def run(self):
        self.mainloop()

    def close(self):
        if self.ibkr:
            self.ibkr.disconnect()
        self.destroy()

    def open_extlt35_window(self):
        self.open_csv_window('optimized_35_extlt.csv', 'Extlt35')

    def open_opt50_window(self):
        self.open_csv_window('optimized_50_stocks_portfolio.csv', 'Opt50')

    def open_csv_window(self, csv_path, title):
        try:
            df = pd.read_csv(csv_path)
            # Kolon isimlerini normalize et
            cols = [c.strip() for c in df.columns]
            df.columns = cols
            # Gerekli kolonları çek
            show_cols = ['PREF IBKR', 'Final_Shares', 'FINAL_THG', 'AVG_ADV']
            # Alternatif kolon isimleri için fallback
            for alt in ['Final Shares', 'Final_Shares']:
                if alt in df.columns:
                    df['Final_Shares'] = df[alt]
            for alt in ['FINAL THG', 'FINAL_THG']:
                if alt in df.columns:
                    df['FINAL_THG'] = df[alt]
            for alt in ['AVG ADV', 'AVG_ADV']:
                if alt in df.columns:
                    df['AVG_ADV'] = df[alt]
            df = df[[c for c in show_cols if c in df.columns]]
        except Exception as e:
            import tkinter.messagebox as mb
            mb.showerror(title, f"CSV okunamadı: {e}")
            return
        win = tk.Toplevel(self)
        win.title(title)
        table = ttk.Treeview(win, columns=list(df.columns), show='headings')
        for col in df.columns:
            table.heading(col, text=col)
            table.column(col, width=120, anchor='center')
        for _, row in df.iterrows():
            table.insert('', 'end', values=[row.get(col, '') for col in df.columns])
        table.pack(fill='both', expand=True)
        # Scrollbar ekle
        scrollbar = ttk.Scrollbar(win, orient="vertical", command=table.yview)
        table.configure(yscrollcommand=scrollbar.set)
        scrollbar.pack(side="right", fill="y")

    def open_opt50_maltopla_window(self):
        MaltoplaWindow(self, self.ibkr, 'optimized_50_stocks_portfolio.csv', 'T')

    def open_extlt35_maltopla_window(self):
        MaltoplaWindow(self, self.ibkr, 'optimized_35_extlt.csv', 'C')

    def open_positions_window(self):
        win = tk.Toplevel(self)
        win.title('Pozisyonlarım')
        columns = ('Symbol', 'Quantity', 'Avg Cost', 'Account', 'Benchmark Rel.')
        table = ttk.Treeview(win, columns=columns, show='headings')
        for col in columns:
            table.heading(col, text=col)
            table.column(col, width=100, anchor='center')
        table.pack(fill='both', expand=True)
        def update_table():
            for item in table.get_children():
                table.delete(item)
            positions = self.ibkr.get_positions()
            for pos in positions:
                rel = self.ibkr.get_benchmark_change_since_fill(pos['symbol'])
                rel_str = f"{rel:.3f}" if rel is not None else '-'
                table.insert('', 'end', values=(pos['symbol'], pos['quantity'], pos['avgCost'], pos['account'], rel_str))
            win.after(5000, update_table)
        update_table()

    def open_orders_window(self):
        win = tk.Toplevel(self)
        win.title('Emirlerim')
        columns = ('Symbol', 'Action', 'Quantity', 'Price', 'Status', 'OrderId')
        table = ttk.Treeview(win, columns=columns, show='headings')
        for col in columns:
            table.heading(col, text=col)
            table.column(col, width=100, anchor='center')
        table.pack(fill='both', expand=True)
        def update_table():
            for item in table.get_children():
                table.delete(item)
            orders = self.ibkr.get_open_orders()
            for o in orders:
                table.insert('', 'end', values=(o['symbol'], o['action'], o['quantity'], o['price'], o['status'], o['orderId']))
            win.after(3000, update_table)
        update_table()

    def open_t_top_losers_window(self):
        self.open_top_movers_window('T', 'losers')

    def open_t_top_gainers_window(self):
        self.open_top_movers_window('T', 'gainers')

    def open_c_top_losers_window(self):
        self.open_top_movers_window('C', 'losers')

    def open_c_top_gainers_window(self):
        self.open_top_movers_window('C', 'gainers')

    def open_top_movers_window(self, pref_type, direction):
        win = tk.Toplevel(self)
        win.title(f"{pref_type}-{'çok düşenler' if direction=='losers' else 'çok yükselenler'}")
        etf_panel = ETFPanel(win, ETF_SYMBOLS, compact=True)
        etf_panel.pack(fill='x', padx=2, pady=2)
        columns = ('Seç', 'Ticker', 'Bid', 'Ask', 'Last', 'Prev Close', 'TP Price', 'CPF', 'Skor')
        table = ttk.Treeview(win, columns=columns, show='headings')
        for col in columns:
            table.heading(col, text=col)
            table.column(col, width=90 if col=='Seç' else 100, anchor='center')
        table.pack(fill='both', expand=True)
        checked = set()
        items_per_page = 20
        page = [0]
        if pref_type == 'T':
            tickers = self.historical_tickers
        else:
            tickers = self.extended_tickers
        def calculate_scores():
            etf_data = self.ibkr.get_etf_data()
            scored_tickers = []
            for symbol in tickers:
                d = self.ibkr.tickers.get(symbol, {}).get('ticker')
                bid = d.bid if d else 'N/A'
                ask = d.ask if d else 'N/A'
                last = d.last if d else 'N/A'
                prev_close = self.ibkr.prev_closes.get(symbol, 'N/A')
                spread = (ask - bid) if (d and bid is not None and ask is not None) else 'N/A'
                if pref_type == 'T':
                    pff_chg = etf_data.get('PFF', {}).get('change', 0) or 0
                    tlt_chg = etf_data.get('TLT', {}).get('change', 0) or 0
                    benchmark_change = round(pff_chg * 0.7 + tlt_chg * 0.1, 3)
                else:
                    pff_chg = etf_data.get('PFF', {}).get('change', 0) or 0
                    tlt_chg = etf_data.get('TLT', {}).get('change', 0) or 0
                    benchmark_change = round(pff_chg * 1.3 - tlt_chg * 0.1, 3)
                if bid != 'N/A' and ask != 'N/A' and prev_close != 'N/A' and spread != 'N/A':
                    if direction == 'losers':
                        tp_price = round(bid + spread * 0.15, 3)
                        cpf = round(tp_price - prev_close, 3)
                        skor = round(benchmark_change - cpf, 3)
                    else:
                        tp_price = round(ask - spread * 0.15, 3)
                        cpf = round(tp_price - prev_close, 3)
                        skor = round(cpf - benchmark_change, 3)
                else:
                    tp_price = 'N/A'
                    cpf = 'N/A'
                    skor = -99999
                scored_tickers.append({
                    'symbol': symbol,
                    'bid': bid,
                    'ask': ask,
                    'last': last,
                    'prev_close': prev_close,
                    'tp_price': tp_price,
                    'cpf': cpf,
                    'skor': skor
                })
            return sorted(scored_tickers, key=lambda x: x['skor'], reverse=True)
        def populate():
            table.delete(*table.get_children())
            scored_tickers = calculate_scores()
            start = page[0] * items_per_page
            end = min(start + items_per_page, len(scored_tickers))
            for ticker in scored_tickers[start:end]:
                sel = '\u2611' if ticker['symbol'] in checked else '\u2610'
                table.insert('', 'end', iid=ticker['symbol'], values=(
                    sel, ticker['symbol'], ticker['bid'], ticker['ask'],
                    ticker['last'], ticker['prev_close'], ticker['tp_price'],
                    ticker['cpf'], ticker['skor']
                ))
            nav_lbl.config(text=f'Page {page[0]+1} / {max(1, (len(scored_tickers)-1)//items_per_page+1)}')
        def on_table_click(event):
            region = table.identify('region', event.x, event.y)
            if region != 'cell': return
            col = table.identify_column(event.x)
            if col != '#1': return
            row = table.identify_row(event.y)
            if not row: return
            symbol = table.item(row, 'values')[1]
            if symbol in checked:
                checked.remove(symbol)
            else:
                checked.add(symbol)
            populate()
        table.bind('<Button-1>', on_table_click)
        def select_all():
            checked.clear()
            scored_tickers = calculate_scores()
            start = page[0] * items_per_page
            end = min(start + items_per_page, len(scored_tickers))
            for ticker in scored_tickers[start:end]:
                checked.add(ticker['symbol'])
            populate()
        def deselect_all():
            checked.clear()
            populate()
        sel_frame = ttk.Frame(win)
        sel_frame.pack(fill='x', pady=2)
        ttk.Button(sel_frame, text='Tümünü Seç', command=select_all).pack(side='left', padx=2)
        ttk.Button(sel_frame, text='Tümünü Kaldır', command=deselect_all).pack(side='left', padx=2)
        def send_orders():
            from ib_insync import LimitOrder, Stock
            from tkinter import messagebox
            sent = 0
            errors = []
            for symbol in checked:
                d = self.ibkr.tickers.get(symbol, {}).get('ticker')
                bid = d.bid if d else None
                ask = d.ask if d else None
                if bid is None or ask is None:
                    errors.append(f"{symbol}: Fiyat verisi yok.")
                    continue
                spread = ask - bid
                if direction == 'losers':
                    price = round(bid + spread * 0.15, 2)
                    action = 'BUY'
                else:
                    price = round(ask - spread * 0.15, 2)
                    action = 'SELL'
                contract = Stock(symbol, 'SMART', 'USD')
                order = LimitOrder(action, 200, price)
                order.hidden = True
                try:
                    self.ibkr.ib.placeOrder(contract, order)
                    sent += 1
                except Exception as e:
                    errors.append(f"{symbol}: {e}")
            msg = f"{sent} adet hidden {action.lower()} emri gönderildi."
            if errors:
                msg += "\nHatalar:\n" + "\n".join(errors)
            messagebox.showinfo('Emir Sonucu', msg)
        action_frame = ttk.Frame(win)
        action_frame.pack(fill='x', pady=4)
        ttk.Button(action_frame, text='Seçili Tickerlara Hidden Order', command=send_orders).pack(side='left', padx=2)
        nav = ttk.Frame(win)
        nav.pack(fill='x')
        btn_prev = ttk.Button(nav, text='<', command=lambda: (page.__setitem__(0, max(0, page[0]-1)), populate()))
        btn_prev.pack(side='left', padx=5)
        nav_lbl = ttk.Label(nav, text='Page 1')
        nav_lbl.pack(side='left', padx=5)
        btn_next = ttk.Button(nav, text='>', command=lambda: (page.__setitem__(0, page[0]+1), populate()))
        btn_next.pack(side='left', padx=5)
        def update_etf_panel():
            etf_panel.update(self.ibkr.get_etf_data())
            win.after(1000, update_etf_panel)
        update_etf_panel()
        populate()

    def toggle_loop(self):
        if self.loop_running:
            self.loop_running = False
            self.btn_loop.config(text='Döngü Başlat')
            if self.loop_job:
                self.after_cancel(self.loop_job)
                self.loop_job = None
        else:
            self.loop_running = True
            self.btn_loop.config(text='Döngüyü Durdur')
            self.loop_state = {'tab': 0, 'page': 0, 'phase': 'T'}
            self.notebook.select(0)
            self.historical_page = 0
            self.extended_page = 0
            self.update_tables()
            self.subscribe_visible()
            self.loop_job = self.after(100, self.loop_step)

    def loop_step(self):
        if not self.loop_running:
            return
        # Determine current phase and page
        if self.loop_state['phase'] == 'T':
            max_page = (len(self.historical_tickers) - 1) // self.items_per_page
            if self.historical_page < max_page:
                self.historical_page += 1
                self.update_tables()
                self.subscribe_visible()
                self.loop_job = self.after(3000, self.loop_step)
            else:
                self.loop_state['phase'] = 'C'
                self.notebook.select(1)
                self.extended_page = 0
                self.update_tables()
                self.subscribe_visible()
                self.loop_job = self.after(3000, self.loop_step)
        elif self.loop_state['phase'] == 'C':
            max_page = (len(self.extended_tickers) - 1) // self.items_per_page
            if self.extended_page < max_page:
                self.extended_page += 1
                self.update_tables()
                self.subscribe_visible()
                self.loop_job = self.after(3000, self.loop_step)
            else:
                self.loop_state['phase'] = 'T'
                self.notebook.select(0)
                self.historical_page = 0
                self.update_tables()
                self.subscribe_visible()
                self.loop_job = self.after(3000, self.loop_step)

    def open_take_profit_longs_window(self):
        win = tk.Toplevel(self)
        win.title('Take Profit Longs')
        etf_panel = ETFPanel(win, ETF_SYMBOLS, compact=True)
        etf_panel.pack(fill='x', padx=2, pady=2)
        columns = ('Seç', 'Symbol', 'Quantity', 'Avg Cost', 'Last', 'Bid', 'Ask', 'Spread', 'PrefType', 'Benchmark', 'TP Price', 'CPF', 'Skor', 'Benchmark Rel.')
        table = ttk.Treeview(win, columns=columns, show='headings')
        for col in columns:
            table.heading(col, text=col)
            table.column(col, width=90 if col=='Seç' else 100, anchor='center')
        table.pack(fill='both', expand=True)
        checked = set()
        items_per_page = 20
        page = [0]
        def get_long_positions():
            return [pos for pos in self.ibkr.get_positions() if pos['quantity'] > 0]
        def calculate_scores(positions):
            t_set = set(self.historical_tickers)
            c_set = set(self.extended_tickers)
            etf_data = self.ibkr.get_etf_data()
            scored_positions = []
            for pos in positions:
                symbol = pos['symbol']
                d = self.ibkr.tickers.get(symbol, {}).get('ticker')
                last = d.last if d else 'N/A'
                bid = d.bid if d else 'N/A'
                ask = d.ask if d else 'N/A'
                spread = (ask - bid) if (d and bid is not None and ask is not None) else 'N/A'
                prev_close = self.ibkr.prev_closes.get(symbol, 'N/A')
                if symbol in t_set:
                    pref = 'T'
                    pff_chg = etf_data.get('PFF', {}).get('change', 0) or 0
                    tlt_chg = etf_data.get('TLT', {}).get('change', 0) or 0
                    benchmark_change = round(pff_chg * 0.7 + tlt_chg * 0.1, 3)
                elif symbol in c_set:
                    pref = 'C'
                    pff_chg = etf_data.get('PFF', {}).get('change', 0) or 0
                    tlt_chg = etf_data.get('TLT', {}).get('change', 0) or 0
                    benchmark_change = round(pff_chg * 1.3 - tlt_chg * 0.1, 3)
                else:
                    pref = '-'
                    benchmark_change = 0
                if ask != 'N/A' and spread != 'N/A' and prev_close != 'N/A':
                    tp_price = round(ask - spread * 0.15, 3)
                    cpf = round(tp_price - prev_close, 3)
                    skor = round(cpf - benchmark_change, 3)
                else:
                    tp_price = 'N/A'
                    cpf = 'N/A'
                    skor = -99999
                rel = self.ibkr.get_benchmark_change_since_fill(symbol)
                rel_str = f"{rel:.3f}" if rel is not None else '-'
                scored_positions.append({
                    'symbol': symbol,
                    'quantity': pos['quantity'],
                    'avgCost': pos['avgCost'],
                    'last': last,
                    'bid': bid,
                    'ask': ask,
                    'spread': spread,
                    'pref': pref,
                    'benchmark': benchmark_change,
                    'tp_price': tp_price,
                    'cpf': cpf,
                    'skor': skor,
                    'benchmark_rel': rel_str
                })
            return sorted(scored_positions, key=lambda x: x['skor'], reverse=True)
        def populate():
            table.delete(*table.get_children())
            positions = get_long_positions()
            scored_positions = calculate_scores(positions)
            start = page[0] * items_per_page
            end = min(start + items_per_page, len(scored_positions))
            for pos in scored_positions[start:end]:
                sel = '\u2611' if pos['symbol'] in checked else '\u2610'
                table.insert('', 'end', iid=pos['symbol'], values=(
                    sel, pos['symbol'], pos['quantity'], pos['avgCost'],
                    pos['last'], pos['bid'], pos['ask'], pos['spread'],
                    pos['pref'], pos['benchmark'], pos['tp_price'],
                    pos['cpf'], pos['skor'], pos['benchmark_rel']
                ))
            nav_lbl.config(text=f'Page {page[0]+1} / {max(1, (len(scored_positions)-1)//items_per_page+1)}')
        def on_table_click(event):
            region = table.identify('region', event.x, event.y)
            if region != 'cell': return
            col = table.identify_column(event.x)
            if col != '#1': return
            row = table.identify_row(event.y)
            if not row: return
            symbol = table.item(row, 'values')[1]
            if symbol in checked:
                checked.remove(symbol)
            else:
                checked.add(symbol)
            populate()
        table.bind('<Button-1>', on_table_click)
        def select_all():
            checked.clear()
            positions = get_long_positions()
            scored_positions = calculate_scores(positions)
            start = page[0] * items_per_page
            end = min(start + items_per_page, len(scored_positions))
            for pos in scored_positions[start:end]:
                checked.add(pos['symbol'])
            populate()
        def deselect_all():
            checked.clear()
            populate()
        sel_frame = ttk.Frame(win)
        sel_frame.pack(fill='x', pady=2)
        ttk.Button(sel_frame, text='Tümünü Seç', command=select_all).pack(side='left', padx=2)
        ttk.Button(sel_frame, text='Tümünü Kaldır', command=deselect_all).pack(side='left', padx=2)
        def send_orders():
            from ib_insync import LimitOrder, Stock
            from tkinter import messagebox
            sent = 0
            errors = []
            for symbol in checked:
                d = self.ibkr.tickers.get(symbol, {}).get('ticker')
                bid = d.bid if d else None
                ask = d.ask if d else None
                if bid is None or ask is None:
                    errors.append(f"{symbol}: Fiyat verisi yok.")
                    continue
                spread = ask - bid
                price = round(ask - spread * 0.15, 2)
                contract = Stock(symbol, 'SMART', 'USD')
                order = LimitOrder('SELL', 200, price)
                order.hidden = True
                try:
                    self.ibkr.ib.placeOrder(contract, order)
                    sent += 1
                except Exception as e:
                    errors.append(f"{symbol}: {e}")
            msg = f"{sent} adet hidden sell emri gönderildi."
            if errors:
                msg += "\nHatalar:\n" + "\n".join(errors)
            messagebox.showinfo('Emir Sonucu', msg)
        action_frame = ttk.Frame(win)
        action_frame.pack(fill='x', pady=4)
        ttk.Button(action_frame, text='Seçili Pozisyonlara Hidden Sell', command=send_orders).pack(side='left', padx=2)
        nav = ttk.Frame(win)
        nav.pack(fill='x')
        btn_prev = ttk.Button(nav, text='<', command=lambda: (page.__setitem__(0, max(0, page[0]-1)), populate()))
        btn_prev.pack(side='left', padx=5)
        nav_lbl = ttk.Label(nav, text='Page 1')
        nav_lbl.pack(side='left', padx=5)
        btn_next = ttk.Button(nav, text='>', command=lambda: (page.__setitem__(0, page[0]+1), populate()))
        btn_next.pack(side='left', padx=5)
        def update_etf_panel():
            etf_panel.update(self.ibkr.get_etf_data())
            win.after(1000, update_etf_panel)
        update_etf_panel()
        populate()

    def open_take_profit_shorts_window(self):
        win = tk.Toplevel(self)
        win.title('Take Profit Shorts')
        etf_panel = ETFPanel(win, ETF_SYMBOLS, compact=True)
        etf_panel.pack(fill='x', padx=2, pady=2)
        columns = ('Seç', 'Symbol', 'Quantity', 'Avg Cost', 'Last', 'Bid', 'Ask', 'Spread', 'PrefType', 'Benchmark', 'TP Price', 'CPF', 'Skor', 'Benchmark Rel.')
        table = ttk.Treeview(win, columns=columns, show='headings')
        for col in columns:
            table.heading(col, text=col)
            table.column(col, width=90 if col=='Seç' else 100, anchor='center')
        table.pack(fill='both', expand=True)
        checked = set()
        items_per_page = 20
        page = [0]
        def get_short_positions():
            return [pos for pos in self.ibkr.get_positions() if pos['quantity'] < 0]
        def calculate_scores(positions):
            t_set = set(self.historical_tickers)
            c_set = set(self.extended_tickers)
            etf_data = self.ibkr.get_etf_data()
            scored_positions = []
            for pos in positions:
                symbol = pos['symbol']
                d = self.ibkr.tickers.get(symbol, {}).get('ticker')
                last = d.last if d else 'N/A'
                bid = d.bid if d else 'N/A'
                ask = d.ask if d else 'N/A'
                spread = (ask - bid) if (d and bid is not None and ask is not None) else 'N/A'
                prev_close = self.ibkr.prev_closes.get(symbol, 'N/A')
                if symbol in t_set:
                    pref = 'T'
                    pff_chg = etf_data.get('PFF', {}).get('change', 0) or 0
                    tlt_chg = etf_data.get('TLT', {}).get('change', 0) or 0
                    benchmark_change = round(pff_chg * 0.7 + tlt_chg * 0.1, 3)
                elif symbol in c_set:
                    pref = 'C'
                    pff_chg = etf_data.get('PFF', {}).get('change', 0) or 0
                    tlt_chg = etf_data.get('TLT', {}).get('change', 0) or 0
                    benchmark_change = round(pff_chg * 1.3 - tlt_chg * 0.1, 3)
                else:
                    pref = '-'
                    benchmark_change = 0
                if bid != 'N/A' and spread != 'N/A' and prev_close != 'N/A':
                    tp_price = round(bid + spread * 0.15, 3)
                    cpf = round(tp_price - prev_close, 3)
                    skor = round(benchmark_change - cpf, 3)
                else:
                    tp_price = 'N/A'
                    cpf = 'N/A'
                    skor = -99999
                rel = self.ibkr.get_benchmark_change_since_fill(symbol)
                rel_str = f"{rel:.3f}" if rel is not None else '-'
                scored_positions.append({
                    'symbol': symbol,
                    'quantity': pos['quantity'],
                    'avgCost': pos['avgCost'],
                    'last': last,
                    'bid': bid,
                    'ask': ask,
                    'spread': spread,
                    'pref': pref,
                    'benchmark': benchmark_change,
                    'tp_price': tp_price,
                    'cpf': cpf,
                    'skor': skor,
                    'benchmark_rel': rel_str
                })
            return sorted(scored_positions, key=lambda x: x['skor'], reverse=True)
        def populate():
            table.delete(*table.get_children())
            positions = get_short_positions()
            scored_positions = calculate_scores(positions)
            start = page[0] * items_per_page
            end = min(start + items_per_page, len(scored_positions))
            for pos in scored_positions[start:end]:
                sel = '\u2611' if pos['symbol'] in checked else '\u2610'
                table.insert('', 'end', iid=pos['symbol'], values=(
                    sel, pos['symbol'], pos['quantity'], pos['avgCost'],
                    pos['last'], pos['bid'], pos['ask'], pos['spread'],
                    pos['pref'], pos['benchmark'], pos['tp_price'],
                    pos['cpf'], pos['skor'], pos['benchmark_rel']
                ))
            nav_lbl.config(text=f'Page {page[0]+1} / {max(1, (len(scored_positions)-1)//items_per_page+1)}')
        def on_table_click(event):
            region = table.identify('region', event.x, event.y)
            if region != 'cell': return
            col = table.identify_column(event.x)
            if col != '#1': return
            row = table.identify_row(event.y)
            if not row: return
            symbol = table.item(row, 'values')[1]
            if symbol in checked:
                checked.remove(symbol)
            else:
                checked.add(symbol)
            populate()
        table.bind('<Button-1>', on_table_click)
        def select_all():
            checked.clear()
            positions = get_short_positions()
            scored_positions = calculate_scores(positions)
            start = page[0] * items_per_page
            end = min(start + items_per_page, len(scored_positions))
            for pos in scored_positions[start:end]:
                checked.add(pos['symbol'])
            populate()
        def deselect_all():
            checked.clear()
            populate()
        sel_frame = ttk.Frame(win)
        sel_frame.pack(fill='x', pady=2)
        ttk.Button(sel_frame, text='Tümünü Seç', command=select_all).pack(side='left', padx=2)
        ttk.Button(sel_frame, text='Tümünü Kaldır', command=deselect_all).pack(side='left', padx=2)
        def send_orders():
            from ib_insync import LimitOrder, Stock
            from tkinter import messagebox
            sent = 0
            errors = []
            for symbol in checked:
                d = self.ibkr.tickers.get(symbol, {}).get('ticker')
                bid = d.bid if d else None
                ask = d.ask if d else None
                if bid is None or ask is None:
                    errors.append(f"{symbol}: Fiyat verisi yok.")
                    continue
                spread = ask - bid
                price = round(bid + spread * 0.15, 2)
                contract = Stock(symbol, 'SMART', 'USD')
                order = LimitOrder('BUY', 200, price)
                order.hidden = True
                try:
                    self.ibkr.ib.placeOrder(contract, order)
                    sent += 1
                except Exception as e:
                    errors.append(f"{symbol}: {e}")
            msg = f"{sent} adet hidden buy emri gönderildi."
            if errors:
                msg += "\nHatalar:\n" + "\n".join(errors)
            messagebox.showinfo('Emir Sonucu', msg)
        action_frame = ttk.Frame(win)
        action_frame.pack(fill='x', pady=4)
        ttk.Button(action_frame, text='Seçili Pozisyonlara Hidden Buy', command=send_orders).pack(side='left', padx=2)
        nav = ttk.Frame(win)
        nav.pack(fill='x')
        btn_prev = ttk.Button(nav, text='<', command=lambda: (page.__setitem__(0, max(0, page[0]-1)), populate()))
        btn_prev.pack(side='left', padx=5)
        nav_lbl = ttk.Label(nav, text='Page 1')
        nav_lbl.pack(side='left', padx=5)
        btn_next = ttk.Button(nav, text='>', command=lambda: (page.__setitem__(0, page[0]+1), populate()))
        btn_next.pack(side='left', padx=5)
        def update_etf_panel():
            etf_panel.update(self.ibkr.get_etf_data())
            win.after(1000, update_etf_panel)
        update_etf_panel()
        populate() 