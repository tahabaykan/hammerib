import tkinter as tk
from tkinter import ttk

class BenchmarkPanel(ttk.Frame):
    def __init__(self, parent):
        super().__init__(parent)
        self.table = ttk.Treeview(self, columns=('Benchmark', 'Value'), show='headings', height=2)
        for col in ('Benchmark', 'Value'):
            self.table.heading(col, text=col)
            self.table.column(col, width=100, anchor='center')
        self.table.pack(fill='x', expand=False)
        self.table.insert('', 'end', iid='T-Benchmark', values=('T-Benchmark', 'N/A'))
        self.table.insert('', 'end', iid='C-Benchmark', values=('C-Benchmark', 'N/A'))

    def update(self, benchmark_data):
        for benchmark, value in benchmark_data.items():
            self.table.item(benchmark, values=(benchmark, value)) 