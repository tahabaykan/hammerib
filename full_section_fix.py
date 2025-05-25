with open('stock_tracker.py', 'r', encoding='utf-8') as f:
    lines = f.readlines()

# 3725-3740 arasındaki satırları tamamen düzelt
problematic_section = """                    
                    if confirm:
                        # Gerçek emir gönderme işlemi burada olacak
                        messagebox.showinfo("Bilgi", f"{len(orders_to_place)} adet hidden buy emri gönderildi (Gösterim amaçlı)")
                
                hidden_buy_btn = ttk.Button(
                    button_frame,
                    text="Hidden Buy Emri",
                    command=hidden_buy_selected
                )
                hidden_buy_btn.pack(side=tk.LEFT, padx=5)
            
            # Son güncelleme zamanını ekle
"""

fixed_section = """                    
                    if confirm:
                        # Gerçek emir gönderme işlemi burada olacak
                        messagebox.showinfo("Bilgi", f"{len(orders_to_place)} adet hidden buy emri gönderildi (Gösterim amaçlı)")
                
                    hidden_buy_btn = ttk.Button(
                        button_frame,
                        text="Hidden Buy Emri",
                        command=hidden_buy_selected
                    )
                    hidden_buy_btn.pack(side=tk.LEFT, padx=5)
            
            # Son güncelleme zamanını ekle
"""

# Bu bölümü dosyada arayıp düzelt
content = ''.join(lines)
if problematic_section in content:
    content = content.replace(problematic_section, fixed_section)
    
    with open('stock_tracker.py', 'w', encoding='utf-8') as f:
        f.write(content)
    
    print("Problematik bölüm düzeltildi!")
else:
    print("Problematik bölüm bulunamadı, alternatif yöntem deneniyor...")
    
    # Elle düzelt
    if len(lines) > 3734 and "hidden_buy_btn" in lines[3730]:
        # İndentasyon düzeltmesi yap
        lines[3730] = "                    hidden_buy_btn = ttk.Button(\n"
        lines[3731] = "                        button_frame,\n"
        lines[3732] = "                        text=\"Hidden Buy Emri\",\n"
        lines[3733] = "                        command=hidden_buy_selected\n"
        lines[3734] = "                    )\n"
        
        with open('stock_tracker.py', 'w', encoding='utf-8') as f:
            f.writelines(lines)
        
        print("Satır 3730-3734 elle düzeltildi!") 