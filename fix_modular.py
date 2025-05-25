import re

def fix_stock_tracker():
    with open('stock_tracker.py', 'r', encoding='utf-8') as f:
        content = f.read()
    
    # 1. Hatalı hidden_buy_opt50 fonksiyonunu kaldır (satır 3678)
    pattern = re.compile(r'            else:\s+# Hidden Buy butonu - Seçili hisseler için \(Opt50\)\s+def hidden_buy_opt50\(\):[^}]*?\)\s+', re.DOTALL)
    content = pattern.sub('            else:\n', content)
    
    # 2. Opt50 bölümüne hidden_buy_opt50 fonksiyonunu ekle ve hidden_buy_selected fonksiyonunu kaldır
    # Önce hidden_buy_selected fonksiyonunu bul
    pattern_opt50 = re.compile(r'def opt50_mal_topla.*?# Hidden Buy butonu - Seçili hisseler için\s+def hidden_buy_selected\(\):.*?print\("Emirler iptal edildi!"\)\s+', re.DOTALL)
    match_opt50 = pattern_opt50.search(content)
    
    if match_opt50:
        # Bulunan hidden_buy_selected yerine hidden_buy_opt50 ekle
        replacement = '''def opt50_mal_topla(self):
        """Opt50 portföyündeki hisseler için ucuzluk skoru hesaplama ve alım fırsatı analizi - MODULAR VERSION"""
        try:
            # tb_modules'dan gerekli modülleri import et
            from tb_modules.tb_ui_utils import create_selectable_treeview
            from tb_modules.tb_orders import place_hidden_orders
            from tb_modules.tb_ui_components import create_benchmark_frame, update_benchmark_labels
            
            # Hidden Buy butonu - Seçili hisseler için (Opt50)
            def hidden_buy_opt50():
                # Modüler yapıyı kullanarak hidden buy emri ver
                place_hidden_orders(
                    self.ib,                # IB bağlantısı
                    opportunity_tree,       # Treeview
                    action="BUY",
                    parent_window=opportunity_window,
                    lot_size=200,
                    spread_multiplier=0.15
                )
            
'''
        content = pattern_opt50.sub(replacement, content)
    
    # 3. Cashpark35 bölümüne hidden_buy_cash35 fonksiyonunu ekle ve hidden_buy_selected fonksiyonunu kaldır
    pattern_cash35 = re.compile(r'def cashpark35_mal_topla.*?# Hidden Buy butonu - Seçili hisseler için\s+def hidden_buy_selected\(\):.*?print\("Emirler iptal edildi!"\)\s+', re.DOTALL)
    match_cash35 = pattern_cash35.search(content)
    
    if match_cash35:
        # Bulunan hidden_buy_selected yerine hidden_buy_cash35 ekle
        replacement = '''def cashpark35_mal_topla(self):
        """Cashpark35 portföyündeki hisseler için ucuzluk skoru hesaplama ve alım fırsatı analizi"""
        try:
            # tb_modules'dan gerekli modülleri import et
            from tb_modules.tb_ui_utils import create_selectable_treeview
            from tb_modules.tb_orders import place_hidden_orders
            from tb_modules.tb_ui_components import create_benchmark_frame, update_benchmark_labels
            
            # Hidden Buy butonu - Seçili hisseler için (Cashpark35)
            def hidden_buy_cash35():
                # Modüler yapıyı kullanarak hidden buy emri ver
                place_hidden_orders(
                    self.ib,                # IB bağlantısı
                    opportunity_tree,       # Treeview
                    action="BUY",
                    parent_window=opportunity_window,
                    lot_size=200,
                    spread_multiplier=0.15
                )
            
'''
        content = pattern_cash35.sub(replacement, content)
    
    # 4. Buton command'leri düzelt (Opt50 -> hidden_buy_opt50, Cashpark35 -> hidden_buy_cash35)
    pattern_cash35_btn = re.compile(r'# Hidden Buy butonu\s+hidden_buy_btn = ttk\.Button\(\s+button_frame,\s+text="Seçili Hisseler İçin Hidden Buy",\s+command=hidden_buy_opt50\s+\)', re.DOTALL)
    content = pattern_cash35_btn.sub('''# Hidden Buy butonu
            hidden_buy_btn = ttk.Button(
                button_frame,
                text="Seçili Hisseler İçin Hidden Buy",
                command=hidden_buy_cash35
            )''', content)
    
    # 5. Take Profit Shorts bölümünde hidden_buy_shorts fonksiyonunu ekle
    pattern_shorts = re.compile(r'def take_profit_from_shorts.*?# Tamamen yeniden yazılmış Hidden Buy butonu - Çoklu seçim destekli\s+def hidden_buy_selected\(\):.*?print\("Emirler iptal edildi!"\)\s+', re.DOTALL)
    match_shorts = pattern_shorts.search(content)
    
    if match_shorts:
        replacement = '''def take_profit_from_shorts(self):
        """Short pozisyonlar için take profit fırsatlarını hesaplayarak gösterir"""
        try:
            # tb_modules'dan gerekli modülleri import et
            from tb_modules.tb_ui_utils import create_selectable_treeview
            from tb_modules.tb_orders import place_hidden_orders
            from tb_modules.tb_ui_components import create_benchmark_frame, update_benchmark_labels
            
            # Hidden Buy butonu - Seçili hisseler için (Take Profit Shorts)
            def hidden_buy_shorts():
                # Modüler yapıyı kullanarak hidden buy emri ver
                place_hidden_orders(
                    self.ib,                # IB bağlantısı
                    profit_tree,            # Treeview
                    action="BUY",
                    parent_window=profit_window,
                    lot_size=200,
                    spread_multiplier=0.15
                )
            
'''
        content = pattern_shorts.sub(replacement, content)
    
    # 6. Take Profit Shorts butonunu düzelt
    pattern_shorts_btn = re.compile(r'# Create a bigger, more noticeable button\s+hidden_buy_btn = tk\.Button\(\s+bottom_button_frame,\s+text="HIDDEN BUY EMRİ GÖNDER",\s+command=hidden_buy_selected,', re.DOTALL)
    content = pattern_shorts_btn.sub('''# Create a bigger, more noticeable button
            hidden_buy_btn = tk.Button(
                bottom_button_frame,
                text="HIDDEN BUY EMRİ GÖNDER",
                command=hidden_buy_shorts,''', content)
    
    # 7. Take Profit Longs bölümünde hidden_sell_longs fonksiyonu oluştur
    pattern_longs = re.compile(r'# Hidden Sell butonu \(quick trade için\)\s+def hidden_sell_selected\(\):', re.DOTALL)
    content = pattern_longs.sub('''# Hidden Sell butonu (quick trade için)
            def hidden_sell_longs():''', content)
    
    # 8. Take Profit Longs butonunu da düzelt
    pattern_longs_btn = re.compile(r'hidden_sell_btn = ttk\.Button\(\s+button_frame,\s+text="Hidden Sell Emri",\s+command=hidden_sell_selected', re.DOTALL)
    content = pattern_longs_btn.sub('''hidden_sell_btn = ttk.Button(
                button_frame,
                text="Hidden Sell Emri",
                command=hidden_sell_longs''', content)
    
    # Dosyaya geri yaz
    with open('stock_tracker.py', 'w', encoding='utf-8') as f:
        f.write(content)
    
    print("Modüler yapı düzeltmeleri tamamlandı!")

if __name__ == "__main__":
    fix_stock_tracker() 