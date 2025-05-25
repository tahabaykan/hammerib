import tkinter as tk
from tkinter import ttk

def create_hidden_buttons(parent, callbacks):
    btn_spr_hidden_buy = ttk.Button(parent, text='spr hidden buy', command=callbacks.get('spr_hidden_buy'))
    btn_spr_hidden_sell = ttk.Button(parent, text='spr hidden sell', command=callbacks.get('spr_hidden_sell'))
    btn_adj_hidden_buy = ttk.Button(parent, text='adj hidden buy', command=callbacks.get('adj_hidden_buy'))
    btn_adj_hidden_sell = ttk.Button(parent, text='adj hidden sell', command=callbacks.get('adj_hidden_sell'))
    return btn_spr_hidden_buy, btn_spr_hidden_sell, btn_adj_hidden_buy, btn_adj_hidden_sell 