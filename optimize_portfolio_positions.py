import pandas as pd
import numpy as np
import math

print("Portföy optimizasyonu ve pozisyon boyutlandırma işlemi başlatılıyor...")

def select_top_stocks(data, num_stocks=35, max_stocks_per_company=2, group_limits=None):
    """
    En yüksek FINAL_THG değerlerine göre hisseleri seçer,
    aynı şirketten en fazla max_stocks_per_company kadar hisse alır,
    ve her gruptan belirtilen limitte hisse seçer
    """
    print(f"\nEn yüksek FINAL_THG değerlerine göre {num_stocks} hisse seçiliyor...")
    print(f"Şirket başına maksimum {max_stocks_per_company} hisse seçilecek")
    
    if group_limits:
        print("Grup başına maksimum hisse limitleri:")
        for group, limit in group_limits.items():
            print(f"  Grup {group}: Maksimum {limit} hisse")
    
    # Sütunların var olduğunu kontrol et
    required_columns = ['PREF IBKR', 'CMON', 'FINAL_THG']
    if group_limits:
        required_columns.append('Group')
        
    for col in required_columns:
        if col not in data.columns:
            print(f"HATA: {col} kolonu verilerinizde bulunamadı!")
            return None
    
    # FINAL_THG'ye göre sırala
    sorted_data = data.sort_values('FINAL_THG', ascending=False).copy()
    
    # Hisse seçimi için
    selected_stocks = []
    company_counts = {}  # Şirket başına hisse sayısı
    group_counts = {}    # Grup başına hisse sayısı
    
    # Her hisseyi değerlendir
    for index, row in sorted_data.iterrows():
        ticker = row['PREF IBKR']
        company = row['CMON']
        
        # Grup limiti kontrolü
        include_stock = True
        
        if group_limits and 'Group' in row:
            group = row['Group']
            
            # NaN kontrolü
            if pd.isna(group):
                group = -1  # NaN gruplar için -1 kullanıyoruz
                
            # Grup sayısını kontrol et
            current_group_count = group_counts.get(group, 0)
            
            # Eğer bu grup için limit tanımlıysa ve limit aşıldıysa, stoku dahil etme
            if group in group_limits and current_group_count >= group_limits[group]:
                include_stock = False
        
        # Bu şirketten kaç hisse seçilmiş
        current_company_count = company_counts.get(company, 0)
        
        # Şirket limitini ve grup limitini aşmadıysa ve portföy henüz dolmadıysa seç
        if include_stock and current_company_count < max_stocks_per_company and len(selected_stocks) < num_stocks:
            selected_stocks.append(index)
            
            # Sayaçları güncelle
            company_counts[company] = current_company_count + 1
            
            if group_limits and 'Group' in row:
                group = row['Group'] if not pd.isna(row['Group']) else -1
                group_counts[group] = group_counts.get(group, 0) + 1
    
    # Seçilen hisseleri DataFrame'e dönüştür
    selected_portfolio = sorted_data.loc[selected_stocks].copy()
    
    # İstatistikler
    print(f"\nSeçilen hisse sayısı: {len(selected_portfolio)}")
    
    companies_at_limit = sum(1 for company, count in company_counts.items() if count >= max_stocks_per_company)
    print(f"Maksimum hisse limitini dolduran şirket sayısı: {companies_at_limit}")
    
    if group_limits and 'Group' in selected_portfolio.columns:
        print("\nGruplara göre hisse dağılımı:")
        
        # NaN değerleri -1 ile değiştir (görüntüleme için)
        group_display = selected_portfolio['Group'].fillna(-1).astype(int)
        group_distribution = group_display.value_counts().sort_index()
        
        for group, count in group_distribution.items():
            group_name = f"Grup {group}" if group != -1 else "Tanımlanmamış Grup"
            limit_info = f" (Limit: {group_limits.get(group, 'Sınırsız')})" if group in group_limits else ""
            print(f"  {group_name}: {count} hisse{limit_info}")
    
    return selected_portfolio

def optimize_portfolio(portfolio_data, target_shares=25000, target_dollars=None):
    """
    Verilen portföyü optimize eder ve hisse dağılımlarını belirler
    """
    # FINAL_THG değerlerini normalize et (0.1 ile 1.0 arasında)
    # Normalizasyon aralığını genişleterek farkları vurguluyoruz (0.3-0.9 yerine 0.1-1.0)
    max_thg = portfolio_data["FINAL_THG"].max()
    min_thg = portfolio_data["FINAL_THG"].min()
    
    # Yeni normalizasyon fonksiyonu - daha geniş aralık ve üstel ölçekleme
    def normalize_thg(value):
        # Doğrusal normalizasyon (0.1-1.0 arasına ölçeklendirme)
        normalized = 0.1 + 0.9 * (value - min_thg) / (max_thg - min_thg)
        # Farkları vurgulamak için üstel ölçekleme
        return normalized ** 1.5  # Üs 1.5 kullanarak farkları artır
    
    # Normalize edilmiş FINAL_THG değerlerini hesapla
    portfolio_data["Normalized_THG"] = portfolio_data["FINAL_THG"].apply(normalize_thg)
    
    # AVG_ADV değerlerini de normalize et (0.1 ile 1.0 arasında)
    max_adv = portfolio_data["AVG_ADV"].max()
    min_adv = portfolio_data["AVG_ADV"].min() if portfolio_data["AVG_ADV"].min() > 0 else 1
    
    def normalize_adv(value):
        if value <= 0:
            return 0.1  # Minimum değer
        # Doğrusal normalizasyon (0.1-1.0 arasına ölçeklendirme)
        normalized = 0.1 + 0.9 * (value - min_adv) / (max_adv - min_adv)
        # Farkları vurgulamak için üstel ölçekleme
        return normalized ** 1.3  # Üs 1.3 kullanarak farkları artır
    
    portfolio_data["Normalized_ADV"] = portfolio_data["AVG_ADV"].apply(normalize_adv)
    
    # Önerilen pozisyon boyutlarını hesapla - FINAL_THG %80, AVG_ADV %20 ağırlıkla
    # Ağırlık değişimi: 75-25% -> 80-20%
    portfolio_data["Raw_Size"] = (portfolio_data["Normalized_THG"] * 0.8 + portfolio_data["Normalized_ADV"] * 0.2) * 1000
    
    # Yuvarla (en yakın 100'e)
    def round_to_nearest(x, base=100):
        return base * round(x/base)
    
    portfolio_data["Recommended_Shares"] = portfolio_data["Raw_Size"].apply(lambda x: round_to_nearest(x))
    
    # Önerilen toplam hisse sayısını hesapla
    total_recommended_shares = portfolio_data["Recommended_Shares"].sum()
    print(f"Toplam önerilen hisse sayısı: {total_recommended_shares:,.0f}")
    
    # Hedef için ölçeklendirme faktörü
    scaling_factor = target_shares / total_recommended_shares
    
    # Ölçeklendirilmiş hisse sayılarını hesapla
    portfolio_data["Scaled_Shares"] = (portfolio_data["Recommended_Shares"] * scaling_factor).apply(lambda x: round_to_nearest(x, 50))
    
    # Minimum şart: Her hisse için en az 200 hisse
    portfolio_data["Final_Shares"] = portfolio_data["Scaled_Shares"].apply(lambda x: max(200, x))
    
    # Son toplam hisse sayısını kontrol et
    final_total_shares = portfolio_data["Final_Shares"].sum()
    print(f"Ölçeklendirilmiş toplam hisse sayısı: {final_total_shares:,.0f}")
    
    # Hedef geçildiyse uyar
    if final_total_shares > target_shares:
        print(f"UYARI: Ölçeklendirme ve minimum şartlardan sonra toplam hisse sayısı {final_total_shares:,.0f} oldu (hedef: {target_shares:,.0f}).")
        print(f"Hedefi {final_total_shares - target_shares:,.0f} hisse aşıyoruz.")
    
    # Fiyatları hesapla (varsa)
    if "LAST" in portfolio_data.columns:
        portfolio_data["Estimated_Cost"] = portfolio_data["Final_Shares"] * portfolio_data["LAST"]
        total_cost = portfolio_data["Estimated_Cost"].sum()
        print(f"Tahmini toplam maliyet: ${total_cost:,.2f}")
        
        # Eğer hedef dolar varsa, dolar bazında ölçeklendirme yap
        if target_dollars is not None:
            dollar_scaling_factor = target_dollars / total_cost
            print(f"Dolar bazlı ölçeklendirme faktörü: {dollar_scaling_factor:.4f}")
            
            # Payları hedef dolara göre yeniden ölçeklendir
            portfolio_data["Dollar_Scaled_Shares"] = (portfolio_data["Final_Shares"] * dollar_scaling_factor).apply(lambda x: round_to_nearest(x, 50))
            
            # Minimum şartı uygula
            portfolio_data["Final_Shares"] = portfolio_data["Dollar_Scaled_Shares"].apply(lambda x: max(200, x))
            
            # Yeniden hesaplanmış maliyet
            portfolio_data["Estimated_Cost"] = portfolio_data["Final_Shares"] * portfolio_data["LAST"]
            final_cost = portfolio_data["Estimated_Cost"].sum()
            print(f"Ölçeklendirilmiş toplam maliyet: ${final_cost:,.2f}")
    else:
        print("UYARI: LAST fiyat kolonu bulunamadı, dolar bazlı ölçeklendirme yapılamıyor")
        
        # Varsayılan fiyat ile tahmin yap
        avg_price = 35  # Varsayılan ortalama hisse fiyatı
        est_cost = portfolio_data["Final_Shares"].sum() * avg_price
        print(f"Tahmini maliyet (varsayılan ${avg_price} fiyatla): ${est_cost:,.2f}")
        
        # Eğer hedef dolar varsa, kabaca ölçeklendirme yap
        if target_dollars is not None:
            approx_scaling_factor = target_dollars / est_cost
            print(f"Yaklaşık dolar ölçeklendirme faktörü: {approx_scaling_factor:.4f}")
            
            # Payları hedef dolara göre yeniden ölçeklendir
            portfolio_data["Final_Shares"] = (portfolio_data["Final_Shares"] * approx_scaling_factor).apply(lambda x: round_to_nearest(x, 50))
            
            # Minimum şartı uygula
            portfolio_data["Final_Shares"] = portfolio_data["Final_Shares"].apply(lambda x: max(200, x))
    
    # Son toplam hisse sayısını kontrol et
    final_total_shares = portfolio_data["Final_Shares"].sum()
    print(f"Son toplam hisse sayısı: {final_total_shares:,.0f}")
    
    return portfolio_data

def process_file(input_file, output_file, num_stocks=50, max_stocks_per_company=2, target_shares=25000, target_dollars=None, group_limits=None):
    """
    Verilen dosyayı işler ve portföyü optimize eder
    
    Parameters:
    -----------
    input_file : str
        Girdi dosyasının adı
    output_file : str
        Çıktı dosyasının adı
    num_stocks : int, optional
        Seçilecek hisse sayısı (default: 50)
    max_stocks_per_company : int, optional
        Şirket başına maksimum hisse sayısı (default: 2)
    target_shares : int, optional
        Hedef toplam hisse sayısı (default: 25000)
    target_dollars : float, optional
        Hedef toplam dolar değeri (default: None)
    group_limits : dict, optional
        Grup başına maksimum hisse limitleri (default: None)
    """
    try:
        print(f"\n{input_file} dosyası işleniyor...")
        data = pd.read_csv(input_file)
        print(f"Toplam {len(data)} hisse yüklendi.")
        
        # En iyi hisseleri seç
        portfolio = select_top_stocks(data, num_stocks, max_stocks_per_company, group_limits)
        
        if portfolio is None or len(portfolio) == 0:
            print(f"HATA: Portföy oluşturulamadı! Lütfen giriş verilerinizi kontrol edin.")
            return None
        
        # Portföyü optimize et
        optimized_portfolio = optimize_portfolio(
            portfolio,
            target_shares=target_shares,
            target_dollars=target_dollars
        )
        
        # Optimize edilmiş portföyü döndür
        portfolio_results = optimized_portfolio
        
        # Sonuçları göster
        print("\nSeçilen hisseler ve önerilen pozisyon boyutları:")
        if len(portfolio_results) <= 15:
            print(portfolio_results.to_string(index=False))
        else:
            print(portfolio_results.head(15).to_string(index=False))
            print("...")
            print(portfolio_results.tail(15).to_string(index=False))
            
        # FINAL_THG skorlarına göre sıralı liste de göster
        print("\nHisse dağılımı (FINAL_THG skoruna göre sıralı):")
        print(portfolio_results.sort_values("FINAL_THG", ascending=False).head(15).to_string(index=False))
        
        # Grup dağılımını göster (eğer Group sütunu varsa)
        if 'Group' in portfolio_results.columns:
            print("\nPortföydeki hisselerin grup dağılımı:")
            group_counts = portfolio_results['Group'].value_counts().sort_index()
            for group, count in group_counts.items():
                if pd.isna(group):
                    print(f"  Tanımlanmamış Grup: {count} hisse")
                else:
                    print(f"  Grup {int(group)}: {count} hisse")
        
        # Çıktıyı dosyaya kaydet
        portfolio_results.to_csv(output_file, index=False)
        print(f"\nSonuçlar '{output_file}' dosyasına kaydedildi.")
        
        # İstatistikler
        final_total_shares = portfolio_results["Final_Shares"].sum()
        
        print("\nPOZİSYON BOYUTLARI İSTATİSTİKLERİ:")
        print(f"En yüksek pozisyon: {portfolio_results['Final_Shares'].max():,.0f} hisse")
        print(f"En düşük pozisyon: {portfolio_results['Final_Shares'].min():,.0f} hisse")
        print(f"Ortalama pozisyon: {portfolio_results['Final_Shares'].mean():,.0f} hisse")
        print(f"Medyan pozisyon: {portfolio_results['Final_Shares'].median():,.0f} hisse")
        print("\nPozisyon boyutları dağılımı:")
        print(pd.cut(portfolio_results['Final_Shares'], bins=[0, 300, 500, 750, 1000, 2000, float('inf')]).value_counts().sort_index())
        
        # Maksimum ve minimum hisseler arasındaki oran
        max_shares = portfolio_results['Final_Shares'].max()
        min_shares = portfolio_results['Final_Shares'].min()
        share_ratio = max_shares / min_shares if min_shares > 0 else 0
        print(f"\nEn büyük pozisyon / En küçük pozisyon oranı: {share_ratio:.2f}x")
        
        # FINAL_THG ile Final_Shares arasındaki korelasyon
        thg_share_corr = portfolio_results[['FINAL_THG', 'Final_Shares']].corr().iloc[0,1]
        print(f"FINAL_THG ile Final_Shares arasındaki korelasyon: {thg_share_corr:.4f}")
        
        # FINAL_THG ve AVG_ADV arasındaki korelasyonu kontrol et
        correlation = portfolio_results[['FINAL_THG', 'AVG_ADV']].corr().iloc[0,1]
        print(f"FINAL_THG ve AVG_ADV arasındaki korelasyon: {correlation:.4f}")
        
        # Ağırlıklandırma bilgisi
        print("\nPOZİSYON AĞIRLIKLARI:")
        print("FINAL_THG etkisi: %80 (Önceki: %75)")
        print("AVG_ADV etkisi: %20 (Önceki: %25)")
        print("Not: Farkları artırmak için normalizasyon değerleri üstel ölçekleme ile hesaplandı")
        
        # Ağırlıklandırmanın etkisini göster
        print("\nAĞIRLIKLANDIRMA ETKİSİ ÖRNEKLERİ:")
        sample_stocks = portfolio_results.sort_values("FINAL_THG", ascending=False).head(3)
        sample_stocks = pd.concat([sample_stocks, portfolio_results.sort_values("FINAL_THG").head(3)])
        
        sample_columns = ['PREF IBKR', 'FINAL_THG', 'Normalized_THG', 'AVG_ADV', 'Normalized_ADV', 'Final_Shares']
        if 'Group' in portfolio_results.columns:
            sample_columns.insert(1, 'Group')
            
        print("Normalize değerler örnek karşılaştırması (en yüksek ve en düşük FINAL_THG'ler):")
        print(sample_stocks[sample_columns].to_string(index=False))
        
        # Hisse bazında FINAL_THG ve AVG_ADV analizleri
        print("\nEn yüksek FINAL_THG'ye sahip 10 hisse:")
        high_thg_columns = ['PREF IBKR', 'FINAL_THG', 'AVG_ADV', 'Final_Shares']
        if 'Group' in portfolio_results.columns:
            high_thg_columns.insert(1, 'Group')
            
        high_thg = portfolio_results.sort_values('FINAL_THG', ascending=False).head(10)
        print(high_thg[high_thg_columns].to_string(index=False))
        
        return portfolio_results
        
    except Exception as e:
        print(f"HATA: {input_file} dosyası işlenirken bir sorun oluştu: {e}")
        return None

def setup_group_limits(data_file, type_name="Historical"):
    """
    Grup limitlerini hesaplar ve grup başına hisse limitlerini döndürür
    """
    try:
        # Dosyayı yükle ve grup dağılımını bul
        data = pd.read_csv(data_file)
        
        if 'Group' not in data.columns:
            print(f"UYARI: {data_file} dosyasında 'Group' sütunu yok!")
            return None
        
        # Grup dağılımını hesapla, NaN değerleri -1 olarak düşün
        data['Group'] = data['Group'].fillna(-1)
        group_counts = data['Group'].value_counts().sort_values(ascending=False)
        
        print(f"\n{type_name} veri setindeki grup dağılımı:")
        for group, count in group_counts.items():
            group_name = f"Grup {int(group)}" if group != -1 else "Tanımlanmamış Grup"
            print(f"  {group_name}: {count} hisse")
        
        # En çok hisse içeren gruplar
        top_groups = group_counts.index.tolist()
        
        # Historical için özel limitler (50 hisseye göre ayarlanmış)
        if type_name == "Historical":
            limits = {}
            # Yeni limitler: 11, 8, 7, 6, 5, 4 ve diğerleri için 4
            limit_values = [11, 8, 7, 6, 5, 4]
            
            for i, group in enumerate(top_groups):
                if i < len(limit_values):
                    limits[group] = limit_values[i]
                else:
                    limits[group] = 4  # Diğer gruplar için limit 4
            
            return limits
            
        # EXTLT için özel limitler (35 hisseye göre ayarlanmış)
        elif type_name == "EXTLT":
            limits = {}
            # Yeni limitler: 9, 7, 6, 5, 4 ve diğerleri için 4
            limit_values = [9, 7, 6, 5, 4]
            
            for i, group in enumerate(top_groups):
                if i < len(limit_values):
                    limits[group] = limit_values[i]
                else:
                    limits[group] = 4  # Diğer gruplar için limit 4
            
            return limits
            
    except Exception as e:
        print(f"HATA: Grup limitleri hesaplanırken bir sorun oluştu: {e}")
        return None

def main():
    # Toplam hedef: 1 milyon dolar
    # Historical: 650K, EXTLT: 350K
    
    # İşlenecek dosyalar ve çıktı dosyaları
    files_to_process = [
        {
            "input": "mastermind_histport.csv", 
            "output": "optimized_50_stocks_portfolio.csv",  # Dosya adı güncellendi
            "stocks": 50,  # 35'ten 50'ye çıkarıldı
            "type": "Historical",
            "target_dollars": 650000
        },
        {
            "input": "mastermind_extltport.csv", 
            "output": "optimized_35_extlt.csv",  # Dosya adı güncellendi
            "stocks": 35,  # 25'ten 35'e çıkarıldı
            "type": "EXTLT",
            "target_dollars": 350000
        }
    ]
    
    results = {}
    
    # Her dosyayı işle
    for file_info in files_to_process:
        # Grup limitlerini ayarla
        group_limits = setup_group_limits(file_info["input"], file_info["type"])
        
        results[file_info["input"]] = process_file(
            input_file=file_info["input"],
            output_file=file_info["output"],
            num_stocks=file_info["stocks"],
            max_stocks_per_company=2,
            target_shares=25000,
            target_dollars=file_info["target_dollars"],
            group_limits=group_limits
        )
    
    print("\nTüm portföy optimizasyonları tamamlandı!")
    print("\nToplam Exposure Hedefi: $1,000,000")
    print("Historical Portföy (50 hisse): $650,000")
    print("EXTLT Portföy (35 hisse): $350,000")

if __name__ == '__main__':
    main()