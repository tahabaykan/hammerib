import tkinter as tk
from tkinter import ttk

def create_pos_orders_buttons(parent, main_window):
    btn_positions = ttk.Button(parent, text='Pozisyonlarım', command=main_window.open_positions_window)
    btn_orders = ttk.Button(parent, text='Emirlerim', command=main_window.open_orders_window)
    btn_positions.pack(side='left', padx=2)
    btn_orders.pack(side='left', padx=2)
    return btn_positions, btn_orders 