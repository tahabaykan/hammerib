def fix_indentation():
    with open('stock_tracker.py', 'r', encoding='utf-8') as f:
        content = f.read()
    
    # 1. Opt50 fonksiyonundaki indentasyon hatasını düzelt
    content = content.replace('# Hidden Buy butonu\n            hidden_buy_btn = ttk.Button(\n', '            # Hidden Buy butonu\n            hidden_buy_btn = ttk.Button(\n')
    
    # 2. Cashpark35 fonksiyonundaki indentasyon hatasını düzelt
    content = content.replace('# Hidden Buy butonu\n            hidden_buy_btn = ttk.Button(\n', '            # Hidden Buy butonu\n            hidden_buy_btn = ttk.Button(\n')
    
    # 3. Toplam kayıt sayısı olan yerdeki indentasyon hatasını düzelt
    content = content.replace('# Toplam kayıt sayısı\n            count_label = ttk.Label(', '            # Toplam kayıt sayısı\n            count_label = ttk.Label(')
    
    # Dosyaya geri yaz
    with open('stock_tracker.py', 'w', encoding='utf-8') as f:
        f.write(content)
    
    print("İndentasyon düzeltmeleri tamamlandı!")

if __name__ == "__main__":
    fix_indentation() 