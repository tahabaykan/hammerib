import pandas as pd
import numpy as np

def normalize_custom(series):
    """Excel'deki özel normalizasyon formülü"""
    try:
        valid_series = series[pd.notnull(series)]
        if valid_series.empty:
            return pd.Series(1, index=series.index)
            
        max_val = valid_series.max()
        min_val = valid_series.min()
        
        if max_val == min_val:
            return pd.Series(1, index=series.index)
            
        # Sadece 2 ondalık basamak kullan
        return (1 + ((series - min_val) / (max_val - min_val)) * 99).round(2)
        
    except Exception as e:
        print(f"Normalizasyon hatası: {e}")
        return pd.Series(1, index=series.index)

def show_top_bottom_stocks(df, column, n=20):
    """Belirtilen kolona göre en iyi ve en kötü n hisseyi göster"""
    print(f"\n=== {column} - En İyi {n} Hisse ===")
    print(df.nlargest(n, column)[['PREF IBKR', column]].to_string(index=False))
    
    print(f"\n=== {column} - En Kötü {n} Hisse ===")
    print(df.nsmallest(n, column)[['PREF IBKR', column]].to_string(index=False))

def fill_missing_values():
    """
    Eksik SOLIDITY_SCORE verilerini doldurmak için:
    1. CRDT_SCORE eksik olan hisseleri 8 değeriyle doldurur
    2. CRDT_NORM değerlerini yeniden hesaplar
    3. COM_ ile başlayan eksik değerleri ortalama ile doldurur
    4. SOLIDITY_SCORE değerini hesaplar, eksik verileri doldurduğumuz hisseler için 30 puan düşürür
    """
    try:
        # Pandas ayarlarını güncelle - tüm çıktılarda 2 ondalık göster
        pd.set_option('display.float_format', '{:.2f}'.format)
        
        print("Veri dosyaları yükleniyor...")
        # Mevcut verileri yükle
        scored_stocks = pd.read_csv('scored_stocks.csv')
        original_len = len(scored_stocks)
        
        print(f"\nToplam hisse sayısı: {original_len}")
        print(f"SOLIDITY_SCORE eksik olan hisse sayısı: {scored_stocks['SOLIDITY_SCORE'].isna().sum()}")
        
        # Doldurduğumuz hisseleri takip etmek için ekliyoruz
        filled_stocks = pd.Series(False, index=scored_stocks.index)
        
        # CRDT_SCORE eksik değerleri doldur
        crdt_missing_count = scored_stocks['CRDT_SCORE'].isna().sum()
        if crdt_missing_count > 0:
            print(f"\n1. CRDT_SCORE eksik olan {crdt_missing_count} hisse için değer 8 atanıyor...")
            scored_stocks['CRDT_SCORE'] = scored_stocks['CRDT_SCORE'].fillna(8)
        
        # CRDT_NORM değerlerini yeniden hesapla
        print("2. CRDT_NORM değerleri yeniden hesaplanıyor...")
        scored_stocks['CRDT_NORM'] = normalize_custom(scored_stocks['CRDT_SCORE'])
        
        # COM_ ile başlayan eksik değerleri ortalama ile doldur
        com_columns = [col for col in scored_stocks.columns if col.startswith('COM_')]
        print(f"\n3. COM_ sütunlarındaki eksik değerler ortalama ile doldurulacak: {', '.join(com_columns)}")
        
        for col in com_columns:
            missing_count = scored_stocks[col].isna().sum()
            if missing_count > 0:
                # Eksik değer olan hisseleri işaretle
                missing_mask = scored_stocks[col].isna()
                filled_stocks = filled_stocks | missing_mask
                
                # Ortalama ile doldur
                col_mean = round(scored_stocks[col].mean(), 2)
                
                print(f"   {col} için {missing_count} eksik değer, ortalama={col_mean} ile dolduruldu")
                scored_stocks[col] = scored_stocks[col].fillna(col_mean)
        
        # Tüm numerik kolonları 2 ondalık basamağa yuvarla
        numeric_cols = scored_stocks.select_dtypes(include=['float64']).columns
        for col in numeric_cols:
            scored_stocks[col] = scored_stocks[col].round(2)
        
        # RECENT_TOTAL değerlerini hesapla (COM_3M_PRICE ve COM_6M_PRICE doldurulduğu için)
        print("\n4. Performans değerleri yeniden hesaplanıyor...")
        scored_stocks['3M_PERF'] = ((scored_stocks['COM_LAST_PRICE'] / scored_stocks['COM_3M_PRICE'] - 1)).round(2)
        scored_stocks['6M_PERF'] = ((scored_stocks['COM_LAST_PRICE'] / scored_stocks['COM_6M_PRICE'] - 1)).round(2)
        scored_stocks['RECENT_TOTAL'] = (scored_stocks['3M_PERF'] + scored_stocks['6M_PERF']).round(2)
        
        # 52W_HIGH_SKOR ve 5Y_HIGH_SKOR değerlerini hesapla
        print("5. HIGH skorları yeniden hesaplanıyor...")
        
        # Score ratio fonksiyonu
        def calculate_score_ratio(current, high):
            """Fiyat/High oranını hesapla ve 10-90 arası skora çevir"""
            try:
                if pd.isna(current) or pd.isna(high) or high == 0:
                    return 10
                ratio = current / high
                # 2 ondalık basamağa yuvarla
                return round(min(90, max(10, 90 * ratio)), 2)
            except:
                return 10
        
        scored_stocks['52W_HIGH_SKOR'] = scored_stocks.apply(
            lambda x: calculate_score_ratio(x['COM_LAST_PRICE'], x['COM_52W_HIGH']), 
            axis=1
        )
        
        scored_stocks['5Y_HIGH_SKOR'] = scored_stocks.apply(
            lambda x: calculate_score_ratio(x['COM_LAST_PRICE'], x['COM_5Y_HIGH']), 
            axis=1
        )
        
        # TOTAL_HIGH_SCORE hesapla
        scored_stocks['TOTAL_HIGH_SCORE'] = ((scored_stocks['52W_HIGH_SKOR'] + scored_stocks['5Y_HIGH_SKOR']) / 2).round(2)
        
        # Market Cap normalize et - normalize_market_cap fonksiyonu ile
        print("6. Market Cap değerleri yeniden normalize ediliyor...")
        
        # Market Cap normalize fonksiyonu
        def normalize_market_cap(x):
            """Market Cap değerini normalize et (milyar $ bazında)"""
            if pd.isna(x):
                return 35
                
            # Değer zaten milyar dolar cinsinden
            billions = float(x)
            
            # Puanlama aralıkları
            if billions >= 500:      # 500B+ şirketler
                return 95
            elif billions >= 200:    # 200-500B arası
                return round(90 + ((billions - 200) / 300) * 5, 2)
            elif billions >= 100:    # 100-200B arası
                return round(85 + ((billions - 100) / 100) * 5, 2)
            elif billions >= 50:     # 50-100B arası
                return round(77 + ((billions - 50) / 50) * 8, 2)
            elif billions >= 10:     # 10-50B arası
                return round(60 + ((billions - 10) / 40) * 17, 2)
            elif billions >= 5:      # 5-10B arası
                return round(50 + ((billions - 5) / 5) * 10, 2)
            elif billions >= 1:      # 1-5B arası
                return round(40 + ((billions - 1) / 4) * 10, 2)
            else:                    # 1B altı
                return round(max(35, 35 + (billions * 5)), 2)
        
        scored_stocks['MKTCAP_NORM'] = scored_stocks['COM_MKTCAP'].apply(normalize_market_cap)
            
        # SOLIDITY_SCORE değerini yeniden hesapla
        print("7. SOLIDITY_SCORE değerleri yeniden hesaplanıyor...")

        # Solidity hesaplama fonksiyonu
        def calculate_solidity(row):
            try:
                total_perf = row['RECENT_TOTAL']
                
                # Son dönem performansına göre ağırlıklar
                if total_perf >= 0.8:
                    # Yüksek performans - Market Cap'e daha fazla ağırlık
                    solidity = (
                        row['TOTAL_HIGH_SCORE'] * 0.26 +
                        row['MKTCAP_NORM'] * 0.49 +     # Market Cap ağırlığını artır
                        row['CRDT_NORM'] * 0.25
                    )
                else:
                    # Düşük performans - Total Score'a daha fazla ağırlık
                    solidity = (
                        row['TOTAL_HIGH_SCORE'] * 0.42 +
                        row['MKTCAP_NORM'] * 0.39 +     # Market Cap ağırlığını koru
                        row['CRDT_NORM'] * 0.20
                    )
                
                # BB bond kontrolü
                bond = str(row.get('BOND_', '')).strip()
                if bond == 'BB':
                    solidity *= 1.02
                
                # 2 ondalık basamağa yuvarla
                return round(solidity, 2)
                
            except Exception as e:
                print(f"Satır hesaplama hatası ({row.get('PREF IBKR', 'Bilinmeyen')}): {e}")
                return None

        # Önce normal SOLIDITY_SCORE değerlerini hesapla
        scored_stocks['ORIGINAL_SOLIDITY'] = scored_stocks.apply(calculate_solidity, axis=1)
        
        # Sonra eksik verileri doldurduğumuz hisselerin skorlarını 30 puan düşür
        scored_stocks['SOLIDITY_SCORE'] = scored_stocks['ORIGINAL_SOLIDITY']
        scored_stocks.loc[filled_stocks, 'SOLIDITY_SCORE'] = \
            (scored_stocks.loc[filled_stocks, 'ORIGINAL_SOLIDITY'] - 20).round(2)
        
        # Negatif skorları 1 ile sınırla
        scored_stocks.loc[scored_stocks['SOLIDITY_SCORE'] < 1, 'SOLIDITY_SCORE'] = 1
        
        # Sonuçları kontrol et
        new_missing = scored_stocks['SOLIDITY_SCORE'].isna().sum()
        print(f"\nSonuçlar:")
        print(f"Başlangıçta SOLIDITY_SCORE eksik olan hisse sayısı: {scored_stocks['SOLIDITY_SCORE'].isna().sum()}")
        print(f"İşlem sonrası SOLIDITY_SCORE eksik olan hisse sayısı: {new_missing}")
        
        # Doldurduğumuz ve skorunu düşürdüğümüz hisseleri göster
        if filled_stocks.any():
            print(f"\nEksik verileri doldurulan ve SOLIDITY_SCORE değeri 30 puan düşürülen {filled_stocks.sum()} hisse:")
            print("Ticker      | Original | Adjusted | Değişim")
            print("------------|----------|----------|--------")
            
            # Doldurduğumuz tüm hisseler için göster
            for idx in scored_stocks[filled_stocks].index:
                ticker = scored_stocks.loc[idx, 'PREF IBKR']
                original = scored_stocks.loc[idx, 'ORIGINAL_SOLIDITY']
                adjusted = scored_stocks.loc[idx, 'SOLIDITY_SCORE']
                
                print(f"{ticker:<12}| {original:>8.2f} | {adjusted:>8.2f} | {adjusted-original:>+8.2f}")
        
        # ORIGINAL_SOLIDITY sütununu kaldır
        scored_stocks = scored_stocks.drop(columns=['ORIGINAL_SOLIDITY'])
        
        # Sonuçları yeni bir CSV dosyasına kaydet - 2 ondalık basamak formatıyla
        output_file = 'scored_stocks_filled.csv'
        scored_stocks.to_csv(output_file, index=False, float_format='%.2f')
        print(f"\nTamamlanmış veriler '{output_file}' dosyasına kaydedildi.")
        
        # SOLIDITY bileşenlerini analiz et
        print("\n\n=============================================")
        print("SOLIDITY SCORE BİLEŞENLERİ ANALİZİ")
        print("=============================================")
        
        # Solidity hesaplamasında kullanılan bileşenler
        solidity_components = [
            'SOLIDITY_SCORE',      # Final Solidity skoru
            'TOTAL_HIGH_SCORE',    # HIGH skorlarının ortalaması
            '52W_HIGH_SKOR',       # 52 haftalık yüksek skoru
            '5Y_HIGH_SKOR',        # 5 yıllık yüksek skoru
            'MKTCAP_NORM',         # Normalize edilmiş Market Cap
            'COM_MKTCAP',          # Ham Market Cap değeri
            'CRDT_NORM',           # Normalize edilmiş kredi skoru
            'CRDT_SCORE',          # Ham kredi skoru
            'RECENT_TOTAL',        # Son dönem performansı
            '3M_PERF',             # 3 aylık performans
            '6M_PERF'              # 6 aylık performans
        ]
        
        # Her bileşen için en iyi ve en kötü 20 hisseyi göster
        for component in solidity_components:
            show_top_bottom_stocks(scored_stocks, component)
            
        # BB bond olanları göster
        bb_bonds = scored_stocks[scored_stocks['BOND_'] == 'BB']
        if not bb_bonds.empty:
            print("\n\n=== BB Bond Olan Hisseler ===")
            print(bb_bonds[['PREF IBKR', 'BOND_', 'SOLIDITY_SCORE']].sort_values('SOLIDITY_SCORE', ascending=False).to_string(index=False))
        else:
            print("\n\n=== BB Bond Olan Hisse Bulunamadı ===")
        
        return scored_stocks
            
    except Exception as e:
        print(f"Hata oluştu: {e}")
        import traceback
        traceback.print_exc()

if __name__ == '__main__':
    filled_data = fill_missing_values()