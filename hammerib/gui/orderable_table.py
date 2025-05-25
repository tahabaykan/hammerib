import tkinter as tk
from tkinter import ttk, messagebox
from ib_insync import LimitOrder, Stock
import time

CHECKED = '\u2611'  # ☑
UNCHECKED = '\u2610'  # ☐

class OrderableTableFrame(ttk.Frame):
    def __init__(self, parent, ibkr_manager, tickers, get_ticker_data=None):
        super().__init__(parent)
        self.ibkr = ibkr_manager
        self.tickers = tickers
        self.get_ticker_data = get_ticker_data or self.default_get_ticker_data
        self.checked_tickers = set()
        self.ticker_cache = {}
        self.table = ttk.Treeview(self, columns=(
            'Seç', 'Ticker', 'Bid', 'Ask', 'Last', 'Volume', 'Spread'), show='headings', height=20)
        for col in ('Seç', 'Ticker', 'Bid', 'Ask', 'Last', 'Volume', 'Spread'):
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
        self.populate_table()

    def default_get_ticker_data(self, symbol):
        # Varsayılan olarak ibkr_manager'dan canlı veri çek
        d = self.ibkr.tickers.get(symbol, {}).get('ticker')
        if d:
            return {
                'bid': d.bid,
                'ask': d.ask,
                'last': d.last,
                'volume': d.volume,
                'spread': (d.ask - d.bid) if d.bid is not None and d.ask is not None else None
            }
        return {}

    def populate_table(self):
        self.table.delete(*self.table.get_children())
        for symbol in self.tickers:
            d = self.get_ticker_data(symbol)
            bid = d.get('bid', 'N/A')
            ask = d.get('ask', 'N/A')
            last = d.get('last', 'N/A')
            volume = d.get('volume', 'N/A')
            spread = d.get('spread', 'N/A')
            checked = CHECKED if symbol in self.checked_tickers else UNCHECKED
            values = (checked, symbol, bid, ask, last, volume, spread)
            self.table.insert('', 'end', iid=symbol, values=values)

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
        self.populate_table()

    def select_all(self):
        for symbol in self.tickers:
            self.checked_tickers.add(symbol)
        self.populate_table()

    def deselect_all(self):
        self.checked_tickers.clear()
        self.populate_table()

    def get_selected_tickers(self):
        return list(self.checked_tickers)

    def on_spr_hidden_bid(self):
        self._send_orders(order_type='BUY', price_func=lambda bid, ask: round(bid + (ask - bid) * 0.15, 2), label='hidden buy')

    def on_spr_hidden_ask(self):
        self._send_orders(order_type='SELL', price_func=lambda bid, ask: round(ask - (ask - bid) * 0.15, 2), label='hidden sell')

    def on_adj_hidden_bid(self):
        messagebox.showinfo('Bilgi', 'adj hidden bid: ' + ', '.join(self.get_selected_tickers()))

    def on_adj_hidden_ask(self):
        messagebox.showinfo('Bilgi', 'adj hidden ask: ' + ', '.join(self.get_selected_tickers()))

    def _send_orders(self, order_type, price_func, label):
        selected = self.get_selected_tickers()
        if not selected:
            messagebox.showinfo('Uyarı', 'Lütfen en az bir hisse seçin.')
            return
        sent_orders = 0
        errors = []
        for symbol in selected:
            d = self.get_ticker_data(symbol)
            bid = d.get('bid')
            ask = d.get('ask')
            if bid is None or ask is None or bid == 'N/A' or ask == 'N/A':
                errors.append(f"{symbol}: Fiyat verisi yok.")
                continue
            try:
                bid = float(bid)
                ask = float(ask)
                price = price_func(bid, ask)
                contract = Stock(symbol, 'SMART', 'USD')
                order = LimitOrder(order_type, 200, price)
                order.hidden = True
                self.ibkr.ib.placeOrder(contract, order)
                sent_orders += 1
            except Exception as e:
                errors.append(f"{symbol}: {e}")
        msg = f"{sent_orders} adet {label} emri gönderildi."
        if errors:
            msg += "\nHatalar:\n" + "\n".join(errors)
        messagebox.showinfo('Emir Sonucu', msg) 