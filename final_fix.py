def final_fix():
    with open('stock_tracker.py', 'r', encoding='utf-8') as f:
        lines = f.readlines()
    
    new_lines = []
    in_opt50 = False
    in_cashpark35 = False
    
    for i, line in enumerate(lines):
        # Opt50 fonksiyonunu tespit et
        if "def opt50_mal_topla(self):" in line:
            in_opt50 = True
            in_cashpark35 = False
        # Cashpark35 fonksiyonunu tespit et
        elif "def cashpark35_mal_topla(self):" in line:
            in_opt50 = False
            in_cashpark35 = True
        # Başka bir fonksiyona geçince sıfırla
        elif line.strip().startswith("def ") and "self" in line:
            in_opt50 = False
            in_cashpark35 = False
        
        # İndentasyon düzeltmeleri - Yerine göre 12 boşluk ekle
        if (in_opt50 or in_cashpark35) and line.strip() == "# Hidden Buy butonu":
            new_lines.append("            # Hidden Buy butonu\n")
        elif ((in_opt50 or in_cashpark35) and 
              line.strip().startswith("hidden_buy_btn = ttk.Button(") and 
              new_lines[-1].strip() == "# Hidden Buy butonu"):
            new_lines.append("            hidden_buy_btn = ttk.Button(\n")
        # Eğer önceki düzeltme uygulanmışsa, bu satırları normal şekilde ekle
        elif not ((in_opt50 or in_cashpark35) and 
                line.strip().startswith("hidden_buy_btn = ttk.Button(") and 
                new_lines[-1].strip() == "# Hidden Buy butonu"):
            new_lines.append(line)
    
    # Dosyaya geri yaz
    with open('stock_tracker.py', 'w', encoding='utf-8') as f:
        f.writelines(new_lines)
    
    print("Tüm indentasyon düzeltmeleri tamamlandı!")

if __name__ == "__main__":
    final_fix() 