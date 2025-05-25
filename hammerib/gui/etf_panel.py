import tkinter as tk
from tkinter import ttk

class ETFPanel(ttk.Frame):
    def __init__(self, parent, etf_symbols, compact=False):
        super().__init__(parent)
        self.compact = compact
        self.table = ttk.Treeview(self, columns=('ETF', 'Last', 'Change', 'Change%'), show='headings', height=len(etf_symbols))
        font = ('Arial', 8) if compact else ('Arial', 10)
        col_width = 60 if compact else 90
        for col in ('ETF', 'Last', 'Change', 'Change%'):
            self.table.heading(col, text=col)
            self.table.column(col, width=col_width, anchor='center')
        self.table.pack(fill='x', expand=False)
        self.etf_symbols = etf_symbols
        for symbol in etf_symbols:
            self.table.insert('', 'end', iid=symbol, values=(symbol, 'N/A', 'N/A', 'N/A'))
        # Set font
        style = ttk.Style(self)
        style.configure('Treeview', font=font, rowheight=(16 if compact else 22))
    def update(self, etf_data):
        for symbol in self.etf_symbols:
            d = etf_data.get(symbol)
            if d:
                self.table.item(symbol, values=(symbol, d['last'], d['change'], d['change_pct'])) 