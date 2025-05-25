import tkinter as tk
from tkinter import ttk

def create_opt_buttons(parent, main_window):
    btn_opt50 = ttk.Button(parent, text='Opt50', command=main_window.open_opt50_window)
    btn_extlt35 = ttk.Button(parent, text='Extlt35', command=main_window.open_extlt35_window)
    btn_opt50.pack(side='left', padx=2)
    btn_extlt35.pack(side='left', padx=2)
    btn_opt50_maltopla = ttk.Button(parent, text='Opt50 maltopla', command=main_window.open_opt50_maltopla_window)
    btn_extlt35_maltopla = ttk.Button(parent, text='Extlt35 maltopla', command=main_window.open_extlt35_maltopla_window)
    btn_opt50_maltopla.pack(side='left', padx=2)
    btn_extlt35_maltopla.pack(side='left', padx=2)
    return btn_opt50, btn_extlt35, btn_opt50_maltopla, btn_extlt35_maltopla 