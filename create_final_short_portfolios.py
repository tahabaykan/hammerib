import pandas as pd
import numpy as np
import os
import sys
import re

def extract_company_code(symbol):
    """Sembolden şirket kodunu çıkartır (örn: AAPL PR -> AAPL)"""
    # Semboldeki boşluk veya özel karakterlerden önceki kısmı al
    match = re.match(r'^([A-Z]+)', symbol)
    if match:
        return match.group(1)
    return symbol

def create_optimized_short_portfolio(input_file, output_file, max_stocks, max_per_company=2, max_per_group=6):
    """
    Optimize edilmiş final short portföyü oluşturur
    - FINAL_THG en düşük 100 hisseyi seçer
    - SMI < 0.28 olan hisseleri filtreler
    - SHORT_FINAL = FINAL_THG + (SMI * 500) formülü ile hesaplanır
    - Aynı şirketten max_per_company kadar hisse seçilir
    - Aynı gruptan max_per_group kadar hisse seçilir
    - Toplamda max_stocks kadar hisse seçilir
    """
    print(f"\n{'-'*50}")
    print(f"OPTİMİZE SHORT PORTFÖY OLUŞTURULUYOR: {input_file} -> {output_file}")
    print(f"{'-'*50}")
    
    try:
        # Dosyayı yükle
        df = pd.read_csv(input_file)
        print(f"Dosya başarıyla yüklendi: {len(df)} hisse")
        
        # 1. FINAL_THG değerine göre en düşük 100 hisseyi seç
        df_filtered = df.nsmallest(100, "FINAL_THG").copy()
        print(f"FINAL_THG en düşük 100 hisse seçildi.")
        
        # 2. SMI değeri 0.28'den küçük olan hisseleri filtrele
        df_filtered = df_filtered[df_filtered["SMI"] < 0.28].copy()
        print(f"SMI < 0.28 olan hisse sayısı: {len(df_filtered)}")
        
        if len(df_filtered) == 0:
            print("⚠️ Filtreleme sonucunda hisse kalmadı!")
            return None
        
        # 3. SHORT_FINAL skorunu hesapla
        df_filtered["SHORT_FINAL"] = df_filtered["FINAL_THG"] + (df_filtered["SMI"] * 500)
        
        # 4. Şirket kodu oluştur
        df_filtered["COMPANY"] = df_filtered["PREF IBKR"].apply(extract_company_code)
        
        # 5. SHORT_FINAL'a göre sırala
        df_sorted = df_filtered.sort_values("SHORT_FINAL")
        
        # 6. Optimize edilmiş portföy oluştur
        selected_stocks = []
        company_counts = {}  # Şirket bazında sayım
        group_counts = {}    # Grup bazında sayım
        
        for _, row in df_sorted.iterrows():
            company = row["COMPANY"]
            group = row["GROUP"] if "GROUP" in df_filtered.columns else "NOGROUP"
            
            # Şirket ve grup sayılarını kontrol et
            company_count = company_counts.get(company, 0)
            group_count = group_counts.get(group, 0)
            
            # Limitleri aşmıyorsa ekle
            if (company_count < max_per_company and 
                group_count < max_per_group and 
                len(selected_stocks) < max_stocks):
                
                selected_stocks.append(row)
                company_counts[company] = company_count + 1
                group_counts[group] = group_count + 1
        
        # Seçilen hisseleri DataFrame'e dönüştür
        final_df = pd.DataFrame(selected_stocks)
        print(f"Optimize edilmiş portföyde {len(final_df)} hisse seçildi.")
        
        # Detaylı istatistikler göster
        print("\nOPTİMİZE SHORT PORTFÖY İSTATİSTİKLERİ:")
        print(f"FINAL_THG Ortalama: {final_df['FINAL_THG'].mean():.2f}")
        print(f"SMI Ortalama: {final_df['SMI'].mean():.2f}%")
        print(f"SHORT_FINAL Ortalama: {final_df['SHORT_FINAL'].mean():.2f}")
        
        # Şirket dağılımını göster
        print("\nŞİRKET BAZLI DAĞILIM:")
        company_distribution = final_df["COMPANY"].value_counts()
        for company, count in company_distribution.items():
            if count > 1:
                print(f"{company}: {count} hisse")
        
        # Grup dağılımını göster (eğer GROUP kolonu varsa)
        if "GROUP" in final_df.columns:
            print("\nGRUP BAZLI DAĞILIM:")
            group_counts = final_df["GROUP"].value_counts()
            for group, count in group_counts.items():
                print(f"Grup {group}: {count} hisse")
        
        # Seçilen hisseleri göster
        print("\nOPTİMİZE SHORT PORTFÖY:")
        display_cols = ["PREF IBKR", "COMPANY", "FINAL_THG", "SMI", "SHORT_FINAL"]
        if "GROUP" in final_df.columns:
            display_cols.insert(2, "GROUP")
        
        print(final_df[display_cols].to_string(index=False))
        
        # COMPANY kolonunu çıkar ve dosyayı kaydet
        final_df.drop(columns=["COMPANY"], inplace=True)
        final_df.to_csv(output_file, index=False)
        print(f"\nOptimize short portföy '{output_file}' dosyasına kaydedildi.")
        
        return final_df
    
    except Exception as e:
        print(f"HATA: Optimize short portföy oluşturulurken bir sorun oluştu: {e}")
        return None

def main():
    """Ana program"""
    print("Optimize Short Portfolyo Oluşturma İşlemi Başlatılıyor...")
    
    # İşlenecek dosyalar ve parametreler
    input_files = [
        {
            "input": "short_histport.csv", 
            "output": "short_opt20_port.csv", 
            "max_stocks": 20,
            "max_per_company": 2,
            "max_per_group": 8
        },
        {
            "input": "short_extlt.csv", 
            "output": "short_extlt10.csv", 
            "max_stocks": 10,
            "max_per_company": 2,
            "max_per_group": 8
        }
    ]
    
    # İlk önce dosyaların var olduğunu kontrol et
    for file_info in input_files:
        if not os.path.exists(file_info["input"]):
            print(f"HATA: {file_info['input']} dosyası bulunamadı!")
            print(f"İlk olarak 'get_short_fee_rates.py' çalıştırarak SMI verilerini çekmeniz gerekiyor.")
            sys.exit(1)
    
    # Tüm dosyaları işle
    results = {}
    try:
        for file_info in input_files:
            results[file_info["input"]] = create_optimized_short_portfolio(
                input_file=file_info["input"],
                output_file=file_info["output"],
                max_stocks=file_info["max_stocks"],
                max_per_company=file_info["max_per_company"],
                max_per_group=file_info["max_per_group"]
            )
                
    except Exception as e:
        print(f"HATA: İşlem sırasında bir sorun oluştu: {e}")
    
    print("\nTüm işlemler tamamlandı!")
    
    # Özet tablo: Hangi hisseler her iki portföyde de var?
    try:
        if all(results.values()):
            hist_symbols = set(results["short_histport.csv"]["PREF IBKR"])
            extlt_symbols = set(results["short_extlt.csv"]["PREF IBKR"])
            
            common_symbols = hist_symbols.intersection(extlt_symbols)
            
            print(f"\nHer iki portföyde bulunan hisseler ({len(common_symbols)}):")
            if common_symbols:
                for symbol in sorted(common_symbols):
                    print(f"- {symbol}")
            else:
                print("Ortak hisse bulunmamaktadır.")
    except Exception as e:
        print(f"Ortak hisse analizi yapılırken bir hata oluştu: {e}")

if __name__ == "__main__":
    main() 