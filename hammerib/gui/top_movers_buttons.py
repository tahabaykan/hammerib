import tkinter as tk
from tkinter import ttk

def create_top_movers_buttons(parent, main_window):
    btn_t_down = ttk.Button(parent, text='T-çok düşenler', command=main_window.open_t_top_losers_window)
    btn_t_up = ttk.Button(parent, text='T-çok yükselenler', command=main_window.open_t_top_gainers_window)
    btn_c_down = ttk.Button(parent, text='C-çok düşenler', command=main_window.open_c_top_losers_window)
    btn_c_up = ttk.Button(parent, text='C-çok yükselenler', command=main_window.open_c_top_gainers_window)
    btn_t_down.pack(side='left', padx=2)
    btn_t_up.pack(side='left', padx=2)
    btn_c_down.pack(side='left', padx=2)
    btn_c_up.pack(side='left', padx=2)
    return btn_t_down, btn_t_up, btn_c_down, btn_c_up 