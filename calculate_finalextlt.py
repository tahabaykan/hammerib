import pandas as pd
import numpy as np

def load_required_data():
    """Load data from all required sources"""
    try:
        # Normalize edilmiş verileri ADV bilgisiyle yükle
        normalized_df = pd.read_csv('normalize_extlt_with_adv.csv')
        
        # Yeni solidity skorlarını yükle - extlt versiyonu kullan
        solidity_df = pd.read_csv('scored_extlt.csv')  # scored_stocks.csv yerine extlt versiyonu
        print("Doldurulmuş SOLIDITY skorları 'scored_extlt.csv' dosyasından yüklendi")
        
        # IBKR verilerini yükle (CUR_YIELD için)
        ibkr_df = pd.read_csv('sma_results.csv')
        
        # Common stock performans verilerini yükle
        common_stock_df = pd.read_csv('common_stock_results.csv')
        print("Common stock performans verileri 'common_stock_results.csv' dosyasından yüklendi")
        
        print("Tüm veri dosyaları başarıyla yüklendi!")
        
        # Bilgi yazdır
        print(f"normalize_extlt_with_adv.csv: {len(normalized_df)} satır")
        print(f"scored_extlt.csv: {len(solidity_df)} satır")
        print(f"extlt_results.csv: {len(ibkr_df)} satır")
        print(f"common_stock_results.csv: {len(common_stock_df)} satır")
        
        # SOLIDITY_SCORE kontrolü
        missing_solidity = solidity_df['SOLIDITY_SCORE'].isna().sum()
        if missing_solidity > 0:
            print(f"UYARI: scored_extlt.csv'de hala {missing_solidity} eksik SOLIDITY_SCORE var!")
        else:
            print("scored_extlt.csv'de tüm SOLIDITY_SCORE değerleri mevcut.")
        
        # ADV değerleri kontrolü
        if 'AVG_ADV' in normalized_df.columns:
            missing_adv = normalized_df['AVG_ADV'].isna().sum()
            print(f"AVG_ADV değerleri kontrolü: {len(normalized_df) - missing_adv}/{len(normalized_df)} hisse için mevcut")
        else:
            print("UYARI: normalize_extlt_with_adv.csv dosyasında AVG_ADV kolonu bulunamadı!")
        
        return normalized_df, solidity_df, ibkr_df, common_stock_df
    
    except Exception as e:
        print(f"Veri yükleme hatası: {e}")
        return None, None, None, None

def prepare_data_for_calculation(normalized_df, solidity_df, ibkr_df, common_stock_df):
    """Prepare and merge all required data"""
    try:
        # Print column names for debugging
        print("\nAvailable columns in normalized_df:")
        print(sorted(normalized_df.columns.tolist()))
        
        # Duplike satırları temizle
        normalized_df = normalized_df.drop_duplicates(subset=['PREF IBKR'])
        
        # Yeni SOLIDITY skorları için birleştir
        df = normalized_df.merge(
            solidity_df[['PREF IBKR', 'SOLIDITY_SCORE']], 
            on='PREF IBKR',
            how='left'
        )
        
        # Birleştirme sonuçlarını kontrol et
        merge_success = df['SOLIDITY_SCORE'].notna().sum()
        print(f"\nSOLIDITY_SCORE birleştirildi: {merge_success}/{len(df)} hisse")
        
        # Common stock performans verilerini birleştir
        # CMON sütunu üzerinden birleştir
        df = df.merge(
            common_stock_df[['CMON', 'Normalized_COM_6M', 'Normalized_COM_3M', 'Normalized_52W_LOW']], 
            left_on='CMON',
            right_on='CMON',
            how='left'
        )
        
        # Common stock birleştirme sonuçlarını kontrol et
        common_merge_success = df['Normalized_COM_6M'].notna().sum()
        print(f"Common stock verileri birleştirildi: {common_merge_success}/{len(df)} hisse")
        
        # Not: CUR_YIELD artık kullanılmadığı için hesaplanmayacak
        
        # Tüm numeric kolonları 2 ondalık basamağa yuvarla
        numeric_cols = df.select_dtypes(include=['float64']).columns
        for col in numeric_cols:
            df[col] = df[col].round(2)
            
        return df
        
    except Exception as e:
        print(f"\nVeri hazırlama hatası: {e}")
        print("Hata detayı:", str(e))
        return None

def calculate_final_thg(df):
    """Calculate FINAL THG score based on Excel formula"""
    try:
        # Gerekli kolonları kontrol et
        required_cols = [
            'SMA88_chg_norm',           # O2 - Normalized CHG88
            'SMA268_chg_norm',          # Q2 - Normalized CHG 268
            '6M_High_diff_norm',        # S2 - Normalized 6M H
            '6M_Low_diff_norm',         # U2 - Normalized 6M L
            '1Y_High_diff_norm',        # W2 - Normalized 52HOP (52 Week High)
            '1Y_Low_diff_norm',         # Y2 - Normalized 52LOP (52 Week Low)
            'SOLIDITY_SCORE',           # M2 - Solidity Test
            'AVG_ADV'                   # Average Daily Volume
        ]
        
        # ADV için varsayılan ağırlık
        adv_weight = 0.00025
        
        # AVG_ADV için opsiyonel kontrol - yoksa formülden çıkar
        use_adv = 'AVG_ADV' in df.columns
        if not use_adv:
            print("AVG_ADV kolonu bulunamadı. Volume bilgisi olmadan hesaplamaya devam ediliyor.")
            required_cols.remove('AVG_ADV')
        else:
            print(f"AVG_ADV verileri bulundu, ağırlık: {adv_weight:.6f}")
        
        missing_cols = [col for col in required_cols if col not in df.columns]
        if missing_cols:
            print(f"Eksik kolonlar: {missing_cols}")
            return df
        
        # Eksik değerleri raporla
        for col in required_cols:
            missing_count = df[col].isna().sum()
            if missing_count > 0:
                print(f"{col} için {missing_count} eksik değer var")
        
        # Eksik değerleri en kötü %12'lik değerlerle doldur (güncellendi: %20'den %12'ye)
        for col in required_cols:
            if df[col].isna().any():
                # %12'lik dilime denk gelen değeri hesapla
                quantile_value = df[col].dropna().quantile(0.12).round(2)
                print(f"{col} eksik değerleri en alt %12'lik dilim değeri {quantile_value} ile dolduruluyor")
                df[col] = df[col].fillna(quantile_value)
        
        # ADV değeri varsa formüle ekle, yoksa eski formülü kullan
        if use_adv:
            df['FINAL_THG'] = (
                # SMA değişimleri - Çok daha önemli hale getirildi
                (df['SMA88_chg_norm'] * 2.2 + 
                 df['SMA268_chg_norm'] * 1.7) +
                
                # Normalized değerler grubu - Etkisi azaltıldı (0.45 -> 0.25)
                (df['6M_High_diff_norm'] + 
                 df['6M_Low_diff_norm'] + 
                 df['1Y_High_diff_norm'] + 
                 df['1Y_Low_diff_norm'] * 1.2) * 0.25 +
                
                # Solidity Score * 2.5 (değiştirilmedi)
                df['SOLIDITY_SCORE'] * 2.5 +
                
                # AVG_ADV * ağırlık
                df['AVG_ADV'] * adv_weight
            )
        else:
            df['FINAL_THG'] = (
                # SMA değişimleri - Çok daha önemli hale getirildi
                (df['SMA88_chg_norm'] * 2.2 + 
                 df['SMA268_chg_norm'] * 1.7) +
                
                # Normalized değerler grubu - Etkisi azaltıldı (0.45 -> 0.25)
                (df['6M_High_diff_norm'] + 
                 df['6M_Low_diff_norm'] + 
                 df['1Y_High_diff_norm'] + 
                 df['1Y_Low_diff_norm'] * 1.2) * 0.25 +
                
                # Solidity Score * 2.5 (değiştirilmedi)
                df['SOLIDITY_SCORE'] * 2.5
            )
        
        # FINAL_THG değerini 2 ondalık basamağa yuvarla
        df['FINAL_THG'] = df['FINAL_THG'].round(2)
        
        # Common Stock Performansı Düzeltmesi
        # Problemli şirketleri tanımla 
        problem_companies = ['RC', 'HFRO', 'EIX', 'PEB', 'INN']
        
        # Common Stock performansına göre düzeltme faktörü
        print("\nCommon Stock performansı düzeltmeleri uygulanıyor...")
        
        # Common stock performans düzeltme faktörü
        df['CS_FACTOR'] = 1.0  # Varsayılan değer: 1.0 (düzeltme yok)
        
        # Şirketlere özel düzeltmeler
        for company in problem_companies:
            mask = df['CMON'] == company
            if mask.any():
                # Eğer bu şirket tüm şirketlerin %n'sini oluşturuyorsa, onlara özel indirim uygula
                discount = 0.75  # %25 indirim
                df.loc[mask, 'CS_FACTOR'] = discount
                print(f"  {company} için common stock performans faktörü: {discount:.2f} (%{(1-discount)*100:.0f} indirim)")
        
        # Diğer common stock performans değerlendirmeleri
        # COM_6M ve COM_3M değerlerine göre değerlendirme
        if 'Normalized_COM_6M' in df.columns and 'Normalized_COM_3M' in df.columns:
            # Common stock performansı kötü olan ancak henüz belirli bir şirket listesinde olmayan hisseleri bul
            com_perf_mask = ((df['Normalized_COM_6M'] < 30) & (df['Normalized_COM_3M'] < 25)) & (df['CS_FACTOR'] == 1.0)
            df.loc[com_perf_mask, 'CS_FACTOR'] = 0.85  # %15 indirim
            print(f"  Common stock son 6 ay ve 3 ay performansı kötü olan {com_perf_mask.sum()} hisse için %15 indirim")
            
            # Daha az kötü performans için daha az indirim
            mild_perf_mask = ((df['Normalized_COM_6M'] < 40) & (df['Normalized_COM_3M'] < 35)) & (df['CS_FACTOR'] == 1.0)
            df.loc[mild_perf_mask, 'CS_FACTOR'] = 0.92  # %8 indirim
            print(f"  Common stock performansı sınırda olan {mild_perf_mask.sum()} hisse için %8 indirim")
            
        # FINAL_THG skorunu common stock faktörüyle çarp
        df['FINAL_THG'] = df['FINAL_THG'] * df['CS_FACTOR']
        df['FINAL_THG'] = df['FINAL_THG'].round(2)  # Tekrar yuvarlama
        
        # Debug bilgisi
        print("\n=== FINAL THG Bileşen Katkıları ===")
        component_cols = [
            'PREF IBKR',
            'SMA88_chg_norm', 'SMA268_chg_norm',
            '6M_High_diff_norm', '6M_Low_diff_norm',
            '1Y_High_diff_norm', '1Y_Low_diff_norm',
            'SOLIDITY_SCORE',
            'CS_FACTOR', 'FINAL_THG'
        ]
        print(df[component_cols].head().round(2))
        
        return df
        
    except Exception as e:
        print(f"FINAL THG hesaplama hatası: {e}")
        return df

def main():
    try:
        # Verileri yükle
        normalized_df, solidity_df, ibkr_df, common_stock_df = load_required_data()
        
        if normalized_df is None or solidity_df is None or ibkr_df is None or common_stock_df is None:
            print("Veri yükleme başarısız!")
            return
        
        # TLT ile ilgili satırları filtrele
        if 'PREF IBKR' in normalized_df.columns:
            before_filter = len(normalized_df)
            normalized_df = normalized_df[~normalized_df['PREF IBKR'].str.contains('TLT', na=False)]
            removed = before_filter - len(normalized_df)
            if removed > 0:
                print(f"Normalize edilmiş veriden {removed} adet TLT satırı çıkarıldı.")
        
        # Verileri hazırla
        merged_df = prepare_data_for_calculation(normalized_df, solidity_df, ibkr_df, common_stock_df)
        
        if merged_df is None:
            print("Veri hazırlama başarısız!")
            return
        
        # TLT ile ilgili satırları tekrar kontrol et ve filtrele
        if 'PREF IBKR' in merged_df.columns:
            before_filter = len(merged_df)
            merged_df = merged_df[~merged_df['PREF IBKR'].str.contains('TLT', na=False)]
            removed = before_filter - len(merged_df)
            if removed > 0:
                print(f"Birleştirilmiş veriden {removed} adet TLT satırı çıkarıldı.")
        
        # FINAL_THG değerlerini hesapla
        result_df = calculate_final_thg(merged_df)
        
        # Last Price değeri eksik olan hisseleri filtrele (PRS ve PRH hariç)
        last_price_missing = result_df['Last Price'].isna() | (result_df['Last Price'] == 0)
        contains_prs_prh = result_df['PREF IBKR'].str.contains('PRS|PRH', na=False)
        
        # Last Price eksik veya sıfır OLAN VE aynı zamanda PRS veya PRH içermeyen hisseleri çıkar
        rows_to_remove = last_price_missing & ~contains_prs_prh
        filtered_df = result_df[~rows_to_remove].copy()
        
        # Çıkarılan hisseler hakkında bilgi ver
        removed_count = rows_to_remove.sum()
        print(f"\nLast Price değeri eksik/sıfır olan hisse sayısı: {last_price_missing.sum()}")
        print(f"Bunların içinden PRS veya PRH içeren ve korunan hisse sayısı: {(last_price_missing & contains_prs_prh).sum()}")
        print(f"Çıkarılan hisse sayısı: {removed_count}")
        print(f"Son hisse sayısı: {len(filtered_df)} (Orijinal: {len(result_df)})")
        
        # Korunan PRS/PRH hisselerini listele
        kept_prs_prh = filtered_df[filtered_df['PREF IBKR'].str.contains('PRS|PRH', na=False) & 
                                  (filtered_df['Last Price'].isna() | (filtered_df['Last Price'] == 0))]
        if len(kept_prs_prh) > 0:
            print("\nLast Price eksik olmasına rağmen korunan PRS/PRH hisseleri:")
            for _, row in kept_prs_prh.iterrows():
                print(f"  {row['PREF IBKR']} ({row['CMON']})")
        
        # CSV dosyasını oluştur - filtrelenmiş veri ile (tüm ondalık değerler 2 basamaklı)
        filtered_df.to_csv('final_extlt.csv', 
                      index=False,
                      float_format='%.2f',  # 2 ondalık basamak
                      sep=',',              # Virgül ayracını belirt
                      encoding='utf-8-sig', # Excel için BOM ekle
                      lineterminator='\n',  # Windows satır sonu
                      quoting=1)            # Excel için tüm değerleri tırnak içine al
    
        print("\nSonuçlar 'final_extlt.csv' dosyasına kaydedildi.")
        
        # Top 20 ve Bottom 20 FINAL THG skorlarını göster
        print("\n=== En Yüksek FINAL THG Skorları (Top 20) ===")
        print("PREF IBKR  SOLIDITY  FINAL_THG   SMA88   SMA268   1Y_HIGH   1Y_LOW")
        print("-" * 80)
        
        top_20 = filtered_df.nlargest(20, 'FINAL_THG')[
            ['PREF IBKR', 'SOLIDITY_SCORE', 'FINAL_THG',
             'SMA88_chg_norm', 'SMA268_chg_norm', 
             '1Y_High_diff_norm', '1Y_Low_diff_norm']
        ]
        
        for _, row in top_20.iterrows():
            print(f"{row['PREF IBKR']:<10} {row['SOLIDITY_SCORE']:>8.2f} {row['FINAL_THG']:>10.2f} "
                  f"{row['SMA88_chg_norm']:>7.2f} {row['SMA268_chg_norm']:>7.2f} "
                  f"{row['1Y_High_diff_norm']:>7.2f} {row['1Y_Low_diff_norm']:>7.2f}")
        
        # Bottom 20 FINAL THG skorlarını göster
        print("\n=== En Düşük FINAL THG Skorları (Bottom 20) ===")
        print("PREF IBKR  SOLIDITY  FINAL_THG   SMA88   SMA268   1Y_HIGH   1Y_LOW")
        print("-" * 80)
        
        bottom_20 = filtered_df.nsmallest(20, 'FINAL_THG')[
            ['PREF IBKR', 'SOLIDITY_SCORE', 'FINAL_THG',
             'SMA88_chg_norm', 'SMA268_chg_norm', 
             '1Y_High_diff_norm', '1Y_Low_diff_norm']
        ]
        
        for _, row in bottom_20.iterrows():
            print(f"{row['PREF IBKR']:<10} {row['SOLIDITY_SCORE']:>8.2f} {row['FINAL_THG']:>10.2f} "
                  f"{row['SMA88_chg_norm']:>7.2f} {row['SMA268_chg_norm']:>7.2f} "
                  f"{row['1Y_High_diff_norm']:>7.2f} {row['1Y_Low_diff_norm']:>7.2f}")
                
    except Exception as e:
        print(f"Bir hata oluştu: {e}")
        import traceback
        traceback.print_exc()

if __name__ == '__main__':
    main()