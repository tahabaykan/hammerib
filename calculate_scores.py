import pandas as pd
import numpy as np
import csv

def clean_numeric_data(df):
    """Sayısal verileri temizle ve düzelt"""
    try:
        # Sayısal kolonları belirle
        numeric_columns = [
            'COM_LAST_PRICE', 'COM_52W_LOW', 'COM_52W_HIGH',
            'COM_6M_PRICE', 'COM_3M_PRICE', 'COM_5Y_LOW',
            'COM_5Y_HIGH', 'COM_MKTCAP', 'CRDT_SCORE',
            'COM_FEB2020_PRICE', 'COM_MAR2020_PRICE'
        ]
        
        for col in numeric_columns:
            if col in df.columns:
                # String formatındaki sayıları temizle
                df[col] = df[col].astype(str).str.replace(',', '')
                df[col] = df[col].astype(str).str.replace('$', '')
                df[col] = df[col].astype(str).str.replace('B', '')
                df[col] = pd.to_numeric(df[col], errors='coerce')
        
        return df
    except Exception as e:
        print(f"Veri temizleme hatası: {e}")
        return df

def normalize_score(series):
    """Skorları 10-90 arasında normalize et"""
    try:
        # NaN değerleri filtrele
        valid_series = series.dropna()
        
        if valid_series.empty:
            return pd.Series(10, index=series.index)
        
        min_val = valid_series.min()
        max_val = valid_series.max()
        
        if min_val == max_val:
            return pd.Series(10, index=series.index)
            
        # Normalize et ve 10-90 aralığına getir
        normalized = 10 + ((series - min_val) / (max_val - min_val)) * 80
        
        # 10-90 aralığına zorla
        normalized = normalized.clip(lower=10, upper=90)
        
        return normalized
        
    except Exception as e:
        print(f"Normalizasyon hatası: {e}")
        return pd.Series(10, index=series.index)

def calculate_52w_high_score(df):
    """
    52W HIGH skorunu hesapla ve normalize et
    Mantık: High değere ne kadar yakınsa o kadar iyi
    """
    try:
        # Mevcut fiyatın 52 haftalık yüksekten uzaklığı
        df['52W_HIGH_CHG'] = (df['COM_LAST_PRICE'] - df['COM_52W_HIGH']) / df['COM_52W_HIGH']
        
        # Değişimi normalize et
        df['52W_HIGH_SKOR'] = normalize_score(df['52W_HIGH_CHG'])
        
        return df
    except Exception as e:
        print(f"52W HIGH skor hesaplama hatası: {e}")
        return df

def calculate_5y_high_score(df):
    """
    5Y HIGH skorunu hesapla ve normalize et
    Mantık: 5 yıllık yükseğe ne kadar yakınsa o kadar iyi
    """
    try:
        # Mevcut fiyatın 5 yıllık yüksekten uzaklığı
        df['5Y_HIGH_CHG'] = (df['COM_LAST_PRICE'] - df['COM_5Y_HIGH']) / df['COM_5Y_HIGH']
        
        # Değişimi normalize et
        df['5Y_HIGH_SKOR'] = normalize_score(df['5Y_HIGH_CHG'])
        
        return df
    except Exception as e:
        print(f"5Y HIGH skor hesaplama hatası: {e}")
        return df

def calculate_low_scores(df):
    """LOW skorlarını hesapla (52W LOW ve 5Y LOW için)"""
    try:
        # 52W LOW için
        df['52W_LOW_CHG'] = (df['COM_LAST_PRICE'] - df['COM_52W_LOW']) / df['COM_52W_LOW']
        df['52W_LOW_SKOR'] = df['52W_LOW_CHG'].apply(lambda x:
            10 if pd.isna(x) or x <= 0 else  # Düşüş varsa minimum puan
            min(90, 10 + (x * 80))  # Artış yüzdesi ile orantılı puan
        )
        
        # 5Y LOW için
        df['5Y_LOW_CHG'] = (df['COM_LAST_PRICE'] - df['COM_5Y_LOW']) / df['COM_5Y_LOW']
        df['5Y_LOW_SKOR'] = df['5Y_LOW_CHG'].apply(lambda x:
            10 if pd.isna(x) or x <= 0 else  # Düşüş varsa minimum puan
            min(90, 10 + (x * 80))  # Artış yüzdesi ile orantılı puan
        )
        
        return df
    except Exception as e:
        print(f"LOW skor hesaplama hatası: {e}")
        return df

def calculate_change_scores(df):
    """Değişim skorlarını hesapla"""
    try:
        # 5 yıllık değişim hesaplama
        df['5Y_CHG'] = (df['COM_LAST_PRICE'] - df['COM_5Y_LOW']) / df['COM_5Y_LOW']
        df['5Y CHG SKOR'] = normalize_score(df['5Y_CHG'])
        
        # 52 haftalık değişim hesaplama
        df['52W_CHG'] = (df['COM_LAST_PRICE'] - df['COM_52W_LOW']) / df['COM_52W_LOW']
        df['52W CHG SKOR'] = normalize_score(df['52W_CHG'])
        
        return df
    except Exception as e:
        print(f"Değişim skoru hesaplama hatası: {e}")
        return df

def calculate_score_ratio(current, high):
    """Fiyat/High oranını hesapla ve 10-90 arası skora çevir"""
    try:
        if pd.isna(current) or pd.isna(high) or high == 0:
            return 10
        ratio = current / high
        return min(90, max(10, 90 * ratio))
    except:
        return 10

def calculate_solidity_scores(df):
    """Spreadsheet'teki gibi Solidity hesaplama"""
    try:
        # 1. HIGH score hesaplamaları
        df['52W_HIGH_SKOR'] = df.apply(
            lambda x: calculate_score_ratio(x['COM_LAST_PRICE'], x['COM_52W_HIGH']), 
            axis=1
        )
        
        df['5Y_HIGH_SKOR'] = df.apply(
            lambda x: calculate_score_ratio(x['COM_LAST_PRICE'], x['COM_5Y_HIGH']), 
            axis=1
        )
        
        # 2. TOTAL HIGH SCORE (ortalama)
        df['TOTAL_HIGH_SCORE'] = (df['52W_HIGH_SKOR'] + df['5Y_HIGH_SKOR']) / 2
        
        # 3. Son dönem performans kontrolü
        df['3M_PERF'] = (df['COM_LAST_PRICE'] / df['COM_3M_PRICE'] - 1)
        df['6M_PERF'] = (df['COM_LAST_PRICE'] / df['COM_6M_PRICE'] - 1)
        df['RECENT_TOTAL'] = df['3M_PERF'] + df['6M_PERF']
        
        # 4. Market Cap normalize - Yeni normalizasyon kullan
        df['MKTCAP_NORM'] = normalize_market_cap(df['COM_MKTCAP'])
        
        # 5. Credit Score normalize
        df['CRDT_NORM'] = normalize_custom(df['CRDT_SCORE'])
        
        # 6. Solidity Hesaplama
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
                if str(row['BOND_']).strip() == 'BB':
                    solidity *= 1.02
                    
                return solidity
                
            except Exception as e:
                print(f"Satır hesaplama hatası: {e}")
                return None
        
        # 7. Solidity skorunu hesapla
        df['SOLIDITY_SCORE'] = df.apply(calculate_solidity, axis=1)
        
        # 8. Common stock verisi eksik olanlar için solidity skoru düşür
        # COM_LAST_PRICE değeri eksik olanlar olarak belirle
        missing_common_stock = df['COM_LAST_PRICE'].isna()
        
        if missing_common_stock.any():
            # Orijinal skorları kaydet (log için)
            original_scores = df.loc[missing_common_stock, 'SOLIDITY_SCORE'].copy()
            
            # Skorlardan 30 puan düş
            df.loc[missing_common_stock, 'SOLIDITY_SCORE'] = df.loc[missing_common_stock, 'SOLIDITY_SCORE'] - 30
            
            # Sonuçları raporla
            print(f"\n=== Common Stock verisi eksik olan {missing_common_stock.sum()} hissenin SOLIDITY skorları düşürüldü ===")
            print("Hisse     | Önceki  | Yeni    | Fark")
            print("----------|---------|---------|-------")
            
            # Değişiklikleri göster (en fazla 10 örnek)
            count = 0
            for idx in df[missing_common_stock].index:
                if count >= 10:
                    print("... ve diğerleri")
                    break
                    
                ticker = df.loc[idx, 'PREF IBKR']
                old_score = original_scores.loc[idx]
                new_score = df.loc[idx, 'SOLIDITY_SCORE']
                
                print(f"{ticker:<10}| {old_score:>7.2f} | {new_score:>7.2f} | {new_score-old_score:>+7.2f}")
                count += 1
        
        # 9. Debug için top 10 şirketi göster
        print("\n=== Top 10 Solidity Scores ===")
        top_10 = df.nlargest(10, 'SOLIDITY_SCORE')[['PREF IBKR', 'MKTCAP_NORM', 'CRDT_NORM', 'TOTAL_HIGH_SCORE', 'SOLIDITY_SCORE']]
        print(top_10.round(2).to_string(index=False))
        
        return df
        
    except Exception as e:
        print(f"Solidity hesaplama hatası: {e}")
        return df

def calculate_custom_score(series, threshold, multiplier):
    """Excel formülündeki özel skor hesaplama"""
    try:
        # NaN değerleri filtrele ve ortalama hesapla
        valid_series = series[pd.notnull(series)]
        avg = valid_series.mean()
        
        def score_formula(x):
            if pd.isna(x):
                return 0
            if x < threshold:
                return (((x + 1) / (avg + 1) - 1) * 25 * multiplier)
            return (np.log((x/avg) + 1) + 1) * 25
            
        return series.apply(score_formula)
        
    except Exception as e:
        print(f"Skor hesaplama hatası: {e}")
        return pd.Series(0, index=series.index)

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
            
        return 1 + ((series - min_val) / (max_val - min_val)) * 99
        
    except Exception as e:
        print(f"Normalizasyon hatası: {e}")
        return pd.Series(1, index=series.index)

def normalize_market_cap(series):
    """Market Cap için yumuşak logaritmik normalizasyon (milyar dolar bazında)"""
    try:
        def score_market_cap(x):
            if pd.isna(x):
                return 35
                
            # Değer zaten milyar dolar cinsinden
            billions = float(x)
            
            # Debug print
            print(f"\nHesaplanan Market Cap (milyar $): {billions}")
            
            # Puanlama aralıkları (milyar dolar bazında)
            if billions >= 500:      # 500B+ şirketler
                return 95
            elif billions >= 200:    # 200-500B arası
                return 90 + ((billions - 200) / 300) * 5
            elif billions >= 100:    # 100-200B arası
                return 85 + ((billions - 100) / 100) * 5
            elif billions >= 50:     # 50-100B arası
                return 77 + ((billions - 50) / 50) * 8
            elif billions >= 10:     # 10-50B arası
                return 60 + ((billions - 10) / 40) * 17
            elif billions >= 5:      # 5-10B arası
                return 50 + ((billions - 5) / 5) * 10
            elif billions >= 1:      # 1-5B arası
                return 40 + ((billions - 1) / 4) * 10
            else:                    # 1B altı
                return max(35, 35 + (billions * 5))
            
        # Debug için print ekleyelim
        scored_series = series.apply(score_market_cap)
        print("\nÖrnek Market Cap Skorları:")
        sample_data = pd.DataFrame({
            'Market Cap (B$)': series,
            'Skor': scored_series
        }).head(10)
        print(sample_data)
        
        return scored_series
        
    except Exception as e:
        print(f"Market Cap normalizasyon hatası: {e}")
        print(f"Hatalı değer örneği: {series.head()}")
        return pd.Series(35, index=series.index)

def calculate_all_scores(df):
    """Tüm skorları hesapla"""
    try:
        # 1. FEB2020 (H2020) hesaplamaları
        df['H2020_SKOR'] = calculate_custom_score(
            df['COM_FEB2020_PRICE'],
            threshold=0.15,
            multiplier=1.5
        )
        df['H2020_NORM'] = normalize_custom(df['H2020_SKOR'])
        
        # 2. MAR2020 (L2020) hesaplamaları
        df['L2020_SKOR'] = calculate_custom_score(
            df['COM_MAR2020_PRICE'],
            threshold=-0.2,
            multiplier=1.25
        )
        df['L2020_NORM'] = normalize_custom(df['L2020_SKOR'])
        
        # 3. 6M değişim hesaplamaları
        df['COM_6M_CHG'] = df['COM_LAST_PRICE'] / df['COM_6M_PRICE'] - 1
        df['COM_6M_SKOR'] = df['COM_6M_CHG'].apply(lambda x: 
            (((x + 1) / (df['COM_6M_CHG'].mean() + 1) - 1) * 25 * 1.25) if x < -0.22 
            else (((x + 1) / (df['COM_6M_CHG'].mean() + 1) - 1) * 25)
        )
        df['COM_6M_NORM'] = normalize_custom(df['COM_6M_SKOR'])
        
        # 4. 3M değişim hesaplamaları
        df['COM_3M_CHG'] = df['COM_LAST_PRICE'] / df['COM_3M_PRICE'] - 1
        df['COM_3M_SKOR'] = df['COM_3M_CHG'].apply(lambda x: 
            (((x + 1) / (df['COM_3M_CHG'].mean() + 1) - 1) * 25 * 1.25) if x < -0.22 
            else (((x + 1) / (df['COM_3M_CHG'].mean() + 1) - 1) * 25)
        )
        df['COM_3M_NORM'] = normalize_custom(df['COM_3M_SKOR'])
        
        return df
        
    except Exception as e:
        print(f"Skor hesaplama hatası: {e}")
        return df

def calculate_final_scores(df):
    """Final skorları hesapla - Spreadsheet'teki son formüller"""
    try:
        # 1. Total Score (AE kolonu) hesaplama
        df['TOTAL_SCORE'] = (
            df['Normalized COM 3M'] +  # AD3
            df['Normalized COM 6M'] +  # AA3
            df['Normalized L2020'] +   # X3
            df['Normalized H2020'] +   # U3
            df['Normalized 52WH'] +    # R3
            df['Normalized 52WL'] +    # O3
            df['L2020_NORM'] +         # L3
            df['H2020_NORM']          # I3
        )
        
        # 2. Total Score Normalize (AF kolonu)
        df['TOTAL_SCORE_NORM'] = normalize_custom(df['TOTAL_SCORE'])
        
        # 3. Credit Score Normalize (AH kolonu)
        df['CRDT_SCORE_NORM'] = normalize_custom(df['CRDT_SCORE'])
        
        # 4. Market Cap Normalize (AJ kolonu) - Logaritmik normalize
        def log_normalize(series):
            valid_series = series[pd.notnull(series)]
            if valid_series.empty:
                return pd.Series(1, index=series.index)
                
            max_val = valid_series.max()
            min_val = valid_series.min()
            
            if max_val == min_val:
                return pd.Series(1, index=series.index)
                
            return 1 + ((np.log(series + 1) - np.log(min_val + 1)) / 
                       (np.log(max_val + 1) - np.log(min_val + 1))) * 99
        
        df['MKTCAP_NORM'] = log_normalize(df['COM_MKTCAP'])
        
        # 5. Final Solidity Score (AK kolonu)
        def calculate_solidity(row):
            try:
                recent_perf = row['Normalized COM 6M'] + row['Normalized COM 3M']
                is_bb = str(row['BOND_']).strip() == 'BB'
                
                if recent_perf < 80:
                    # Düşük performans ağırlıkları
                    base_score = (
                        row['TOTAL_SCORE_NORM'] * 0.40 +
                        row['MKTCAP_NORM'] * 0.32 +
                        row['CRDT_SCORE_NORM'] * 0.28
                    )
                else:
                    # Yüksek performans ağırlıkları
                    base_score = (
                        row['TOTAL_SCORE_NORM'] * 0.20 +
                        row['MKTCAP_NORM'] * 0.42 +
                        row['CRDT_SCORE_NORM'] * 0.38
                    )
                
                # BB bond kontrolü
                return base_score * 1.02 if is_bb else base_score
                
            except Exception as e:
                print(f"Solidity hesaplama hatası: {e}")
                return 0
        
        df['SOLIDITY_SCORE'] = df.apply(calculate_solidity, axis=1)
        
        return df
        
    except Exception as e:
        print(f"Final skor hesaplama hatası: {e}")
        return df

def analyze_top_bottom_scores(df):
    """Top 10 ve Bottom 10 skorları analiz et ve göster"""
    try:
        # Symbol kolonu olarak PREF IBKR'yi kullan
        symbol_column = 'PREF IBKR'
            
        print("\n=== 5Y CHG SKOR Analizi ===")
        print("\nTop 10 - 5Y CHG SKOR:")
        print(df.nlargest(10, '5Y CHG SKOR')[[symbol_column, '5Y CHG SKOR']].to_string(index=False))
        print("\nBottom 10 - 5Y CHG SKOR:")
        print(df.nsmallest(10, '5Y CHG SKOR')[[symbol_column, '5Y CHG SKOR']].to_string(index=False))

        print("\n" + "="*50)

        print("\n=== 52W CHG SKOR Analizi ===")
        print("\nTop 10 - 52W CHG SKOR:")
        print(df.nlargest(10, '52W CHG SKOR')[[symbol_column, '52W CHG SKOR']].to_string(index=False))
        print("\nBottom 10 - 52W CHG SKOR:")
        print(df.nsmallest(10, '52W CHG SKOR')[[symbol_column, '52W CHG SKOR']].to_string(index=False))

    except Exception as e:
        print(f"Skor analizi hatası: {e}")
        print("\nMevcut kolonlar:")
        print(df.columns.tolist())

def process_data(df):
    """Tüm veri işleme adımlarını çalıştır"""
    try:
        # Önceki hesaplamalar
        df = clean_numeric_data(df)
        df = calculate_all_scores(df)
        
        # Final hesaplamalar
        df = calculate_final_scores(df)
        
        # Sonuçları kontrol et
        print("\n=== Final Skorlar ===")
        print("\nTop 10 Solidity:")
        print(df.nlargest(10, 'SOLIDITY_SCORE')[['PREF IBKR', 'SOLIDITY_SCORE']].to_string())
        
        return df
        
    except Exception as e:
        print(f"Veri işleme hatası: {e}")
        return df

# Ana hesaplama kısmında şu şekilde kullanılır:
try:
    # CSV'yi oku ve sayısal verileri temizle
    df = pd.read_csv('common_stock_results.csv', encoding='utf-8-sig')
    df = clean_numeric_data(df)
    
    # HIGH skorlarını hesapla
    df = calculate_52w_high_score(df)
    df = calculate_5y_high_score(df)
    
    # LOW skorlarını hesapla
    df = calculate_low_scores(df)
    
    # Değişim skorlarını hesapla
    df = calculate_change_scores(df)
    
    # Solidity skorlarını hesapla
    df = calculate_solidity_scores(df)
    
    # Özel skorları hesapla
    df = calculate_all_scores(df)
    
    # Final skorları hesapla
    df = calculate_final_scores(df)
    
    # Market Cap normalizasyonu
    df['MKTCAP_NORM'] = normalize_market_cap(df['COM_MKTCAP'])
    
    # Market Cap skorlarını kontrol et
    print("\n=== Market Cap Skor Analizi ===")
    df_sorted = df.sort_values('COM_MKTCAP', ascending=False)
    print("\nTop 20 Market Cap Şirketleri ve Skorları:")
    print(df_sorted[['PREF IBKR', 'COM_MKTCAP', 'MKTCAP_NORM']].head(20).to_string(index=False))
    
    # Market Cap aralıklarına göre ortalama skorları göster
    print("\nMarket Cap Aralıklarına Göre Ortalama Skorlar:")
    
    def get_mktcap_range(x):
        billions = x / 1_000_000_000
        if billions >= 500: return "500B+ USD"
        elif billions >= 200: return "200B-500B USD"
        elif billions >= 100: return "100B-200B USD"
        elif billions >= 50: return "50B-100B USD"
        elif billions >= 10: return "10B-50B USD"
        elif billions >= 5: return "5B-10B USD"
        elif billions >= 1: return "1B-5B USD"
        else: return "<1B USD"
    
    df['MKTCAP_RANGE'] = df['COM_MKTCAP'].apply(get_mktcap_range)
    mktcap_stats = df.groupby('MKTCAP_RANGE')['MKTCAP_NORM'].agg([
        ('Şirket Sayısı', 'count'),
        ('Ortalama Skor', 'mean'),
        ('Min Skor', 'min'),
        ('Max Skor', 'max')
    ]).round(2)
    
    print(mktcap_stats)
    
    # Sonuçları kontrol et
    print("\n=== Veri Kontrolü ===")
    numeric_cols = ['COM_LAST_PRICE', 'COM_52W_HIGH', 'COM_5Y_HIGH', 'COM_MKTCAP']
    print("\nÖrnek veriler:")
    print(df[numeric_cols].head())
    
    print("\n=== Skor Dağılımları ===")
    score_cols = ['52W_HIGH_SKOR', '5Y_HIGH_SKOR', '52W_LOW_SKOR', '5Y_LOW_SKOR']
    for col in score_cols:
        print(f"\n{col} dağılımı:")
        print(df[col].describe())
    
    # Top ve Bottom analizini yap
    analyze_top_bottom_scores(df)
    
    # Market Cap skorlarını kontrol et
    print("\n=== Market Cap Skor Analizi ===")
    df_sorted = df.sort_values('COM_MKTCAP', ascending=False)
    print("\nTop 20 Market Cap Şirketleri ve Skorları:")
    print(df_sorted[['PREF IBKR', 'COM_MKTCAP', 'MKTCAP_NORM']].head(20).to_string(index=False))
    
    # Market Cap aralıklarına göre ortalama skorları göster
    print("\nMarket Cap Aralıklarına Göre Ortalama Skorlar:")
    
    def get_mktcap_range(x):
        billions = x / 1_000_000_000
        if billions >= 500: return "500B+ USD"
        elif billions >= 200: return "200B-500B USD"
        elif billions >= 100: return "100B-200B USD"
        elif billions >= 50: return "50B-100B USD"
        elif billions >= 10: return "10B-50B USD"
        elif billions >= 5: return "5B-10B USD"
        elif billions >= 1: return "1B-5B USD"
        else: return "<1B USD"
    
    df['MKTCAP_RANGE'] = df['COM_MKTCAP'].apply(get_mktcap_range)
    print(df.groupby('MKTCAP_RANGE')['MKTCAP_NORM'].agg(['count', 'mean', 'min', 'max']).round(2))
    
    # Solidity sonuçlarını göster
    print("\n=== Solidity Skor Analizi ===")
    print("\nTop 10 - Solidity:")
    print(df.nlargest(30, 'SOLIDITY_SCORE')[['PREF IBKR', 'SOLIDITY_SCORE']].to_string(index=False))
    print("\nBottom 10 - Solidity:")
    print(df.nsmallest(30, 'SOLIDITY_SCORE')[['PREF IBKR', 'SOLIDITY_SCORE']].to_string(index=False))
    
    # Sonuçları kaydet
    df.to_csv('scored_stocks.csv', 
              index=False, 
              encoding='utf-8-sig',
              float_format='%.6f',  # 6 decimal places
              date_format='%Y-%m-%d',
              quoting=csv.QUOTE_NONNUMERIC)  # Sadece string'leri quote'la

except Exception as e:
    print(f"Hata oluştu: {e}")
    raise e