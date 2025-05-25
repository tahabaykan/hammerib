import pandas as pd
import numpy as np
import os
import market_risk_analyzer as mra
from datetime import datetime



def get_market_weights():
    # Piyasa koşullarına göre ağırlıkları belirler
    weights_file = 'market_weights.csv'
    
    # Dosya varsa ve bugüne aitse kullan
    if os.path.exists(weights_file):
        try:
            df = pd.read_csv(weights_file)
            if len(df) > 0:
                today = datetime.now().strftime('%Y-%m-%d')
                if 'date' in df.columns and df['date'].iloc[0] == today:
                    weights = {
                        'solidity_weight': df['solidity_weight'].iloc[0],
                        'yield_weight': df['yield_weight'].iloc[0]
                    }
                    print(f"\nBugünün piyasa ağırlıkları kullanılıyor: Solidity={weights['solidity_weight']:.2f}, Yield={weights['yield_weight']:.2f}")
                    return weights
        except Exception as e:
            print(f"Kaydedilmiş ağırlıkları yüklerken hata: {e}")
    
    # IBKR'den güncel piyasa koşullarını analiz et
    try:
        print("\nPiyasa koşulları analiz ediliyor...")
        market_weights = mra.main()
        return market_weights
    except Exception as e:
        print(f"Piyasa analizi yapılamadı: {e}")
        # Varsayılan ağırlıkları döndür
        return {'solidity_weight': 2.5, 'yield_weight': 600}

def load_required_data():
    """Load data from all required sources"""
    try:
        # Normalize edilmiş verileri ADV bilgisiyle yükle
        normalized_df = pd.read_csv('normalize_data_with_adv.csv')
        
        # Yeni solidity skorlarını yükle - filled versiyonu kullan
        solidity_df = pd.read_csv('scored_stocks_filled.csv')  # scored_stocks.csv yerine filled versiyonu
        print("Doldurulmuş SOLIDITY skorları 'scored_stocks_filled.csv' dosyasından yüklendi")
        
        # IBKR verilerini yükle (CUR_YIELD için)
        ibkr_df = pd.read_csv('sma_results.csv')
        
        print("Tüm veri dosyaları başarıyla yüklendi!")
        
        # Bilgi yazdır
        print(f"normalize_data_with_adv.csv: {len(normalized_df)} satır")
        print(f"scored_stocks_filled.csv: {len(solidity_df)} satır")
        print(f"sma_results.csv: {len(ibkr_df)} satır")
        
        # SOLIDITY_SCORE kontrolü
        missing_solidity = solidity_df['SOLIDITY_SCORE'].isna().sum()
        if missing_solidity > 0:
            print(f"UYARI: scored_stocks_filled.csv'de hala {missing_solidity} eksik SOLIDITY_SCORE var!")
        else:
            print("scored_stocks_filled.csv'de tüm SOLIDITY_SCORE değerleri mevcut.")
        
        # ADV değerleri kontrolü
        if 'AVG_ADV' in normalized_df.columns:
            missing_adv = normalized_df['AVG_ADV'].isna().sum()
            print(f"AVG_ADV değerleri kontrolü: {len(normalized_df) - missing_adv}/{len(normalized_df)} hisse için mevcut")
        else:
            print("UYARI: normalize_data_with_adv.csv dosyasında AVG_ADV kolonu bulunamadı!")
        
        return normalized_df, solidity_df, ibkr_df
    
    except Exception as e:
        print(f"Veri yükleme hatası: {e}")
        return None, None, None

def prepare_data_for_calculation(normalized_df, solidity_df, ibkr_df, market_weights=None):
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
        
        # CUR_YIELD hesaplama
        try:
            # Veri tiplerini kontrol et
            print("\nCOUPON örnek veriler:")
            print(normalized_df[['PREF IBKR', 'COUPON']].head())
            
            # COUPON ve Last Price kolonlarını sayısala çevir
            df['COUPON'] = pd.to_numeric(normalized_df['COUPON'].str.replace('%', ''), errors='coerce')
            df['Last Price'] = pd.to_numeric(normalized_df['Last Price'], errors='coerce')
            
            # CUR_YIELD hesapla: (25*COUPON)/Last Price
            df['CUR_YIELD'] = df.apply(
                lambda row: (25 * row['COUPON']) / row['Last Price'] / 100 if pd.notnull(row['COUPON']) and row['Last Price'] != 0 else np.nan, 
                axis=1
            )
            
            # Tüm numeric kolonları 2 ondalık basamağa yuvarla
            numeric_cols = df.select_dtypes(include=['float64']).columns
            for col in numeric_cols:
                df[col] = df[col].round(2)
            
            # Debug bilgisi
            print("\n=== CUR_YIELD Hesaplama Detayları ===")
            print("Formül: (25 * COUPON) / Last Price")
            print(df[['PREF IBKR', 'COUPON', 'Last Price', 'CUR_YIELD']].head().to_string())
            
            return df
            
        except Exception as e:
            print(f"\nCUR_YIELD hesaplama hatası: {e}")
            print("\nKolon değerleri:")
            print("COUPON değerleri:", normalized_df['COUPON'].unique()[:5])
            print("Last Price değerleri:", normalized_df['Last Price'].unique()[:5])
            raise
        
    except Exception as e:
        print(f"\nVeri hazırlama hatası: {e}")
        print("Hata detayı:", str(e))
        return None

def calculate_final_thg(df, market_weights=None):
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
            'Aug4_chg_norm',            # AA2 - Normalized ORH
            'Oct19_chg_norm',           # AC2 - Normalized OSL
            'SOLIDITY_SCORE',           # M2 - Solidity Test
            'CUR_YIELD',                # G2 - CUR YIELD
            'AVG_ADV'                   # Average Daily Volume
        ]
        
        # Piyasa koşullarına göre ağırlıkları belirle (varsayılan değerleri kullan veya piyasa koşullarına göre)
        if market_weights is None:
            solidity_weight = 2.5    # Varsayılan Solidity ağırlığı
            yield_weight = 600       # Varsayılan CUR_YIELD ağırlığı
            adv_weight = 0.00025     # Varsayılan AVG_ADV ağırlığı
            print("\nVarsayılan ağırlıklar kullanılıyor: Solidity=2.5, Yield=600, ADV=0.00025")
        else:
            solidity_weight = market_weights['solidity_weight']
            yield_weight = market_weights['yield_weight']
            adv_weight = market_weights.get('adv_weight', 0.00025)  # Varsayılan değer sağla
            print(f"\nPiyasa koşullarına göre ağırlıklar: Solidity={solidity_weight:.2f}, Yield={yield_weight:.2f}, ADV={adv_weight:.6f}")
        
        # AVG_ADV için opsiyonel kontrol - yoksa formülden çıkar
        use_adv = 'AVG_ADV' in df.columns
        if not use_adv:
            print("AVG_ADV kolonu bulunamadı. Volume bilgisi olmadan hesaplamaya devam ediliyor.")
            required_cols.remove('AVG_ADV')
        
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
                # SMA değişimleri
                (df['SMA88_chg_norm'] * 0.6 + 
                 df['SMA268_chg_norm'] * 0.9) +
                
                # Normalized değerler grubu * 0.35
                (df['6M_High_diff_norm'] + 
                 df['6M_Low_diff_norm'] + 
                 df['1Y_High_diff_norm'] + 
                 df['1Y_Low_diff_norm'] * 1.2) * 0.35 +
                
                # Aug4 ve Oct19 değerleri * 0.25
                (df['Aug4_chg_norm'] * 0.7 + 
                 df['Oct19_chg_norm'] * 1.3) * 0.25 +
                
                # Solidity Score * piyasa koşullarına göre ağırlık
                df['SOLIDITY_SCORE'] * solidity_weight +
                
                # CUR_YIELD * piyasa koşullarına göre ağırlık
                df['CUR_YIELD'] * yield_weight +
                
                # AVG_ADV * piyasa koşullarına göre ağırlık
                df['AVG_ADV'] * adv_weight
            )
        else:
            df['FINAL_THG'] = (
                # SMA değişimleri
                (df['SMA88_chg_norm'] * 0.6 + 
                 df['SMA268_chg_norm'] * 0.9) +
                
                # Normalized değerler grubu * 0.35
                (df['6M_High_diff_norm'] + 
                 df['6M_Low_diff_norm'] + 
                 df['1Y_High_diff_norm'] + 
                 df['1Y_Low_diff_norm'] * 1.2) * 0.35 +
                
                # Aug4 ve Oct19 değerleri * 0.25
                (df['Aug4_chg_norm'] * 0.7 + 
                 df['Oct19_chg_norm'] * 1.3) * 0.25 +
                
                # Solidity Score * piyasa koşullarına göre ağırlık
                df['SOLIDITY_SCORE'] * solidity_weight +
                
                # CUR_YIELD * piyasa koşullarına göre ağırlık
                df['CUR_YIELD'] * yield_weight
            )
        
        # FINAL_THG değerini 2 ondalık basamağa yuvarla
        df['FINAL_THG'] = df['FINAL_THG'].round(2)
        
        # Debug bilgisi
        print("\n=== FINAL THG Bileşen Katkıları ===")
        component_cols = [
            'PREF IBKR',
            'SMA88_chg_norm', 'SMA268_chg_norm',
            '6M_High_diff_norm', '6M_Low_diff_norm',
            '1Y_High_diff_norm', '1Y_Low_diff_norm',
            'Aug4_chg_norm', 'Oct19_chg_norm',
            'SOLIDITY_SCORE', 'CUR_YIELD',
            'FINAL_THG'
        ]
        print(df[component_cols].head().round(2))
        
        # Kullanılan ağırlıkları kaydet
        df['SOLIDITY_WEIGHT_USED'] = solidity_weight
        df['YIELD_WEIGHT_USED'] = yield_weight
        
        return df
        
    except Exception as e:
        print(f"FINAL THG hesaplama hatası: {e}")
        return df

def main():
    try:
        # Piyasa koşullarını analiz et
        market_weights = get_market_weights()
        
        # Verileri yükle
        normalized_df, solidity_df, ibkr_df = load_required_data()
        
        if normalized_df is None or solidity_df is None or ibkr_df is None:
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
        merged_df = prepare_data_for_calculation(normalized_df, solidity_df, ibkr_df, market_weights)
        
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
        result_df = calculate_final_thg(merged_df, market_weights)
        
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
        filtered_df.to_csv('final_thg_results.csv', 
                      index=False,
                      float_format='%.2f',  # 2 ondalık basamak
                      sep=',',              # Virgül ayracını belirt
                      encoding='utf-8-sig', # Excel için BOM ekle
                      lineterminator='\n',  # Windows satır sonu
                      quoting=1)            # Excel için tüm değerleri tırnak içine al
    
        print("\nSonuçlar 'final_thg_results.csv' dosyasına kaydedildi.")
        
        # Top 20 ve Bottom 20 FINAL THG skorlarını göster
        print("\n=== En Yüksek FINAL THG Skorları (Top 20) ===")
        print("PREF IBKR  SOLIDITY  CUR_YIELD   FINAL_THG   SMA88   SMA268   1Y_HIGH   1Y_LOW")
        print("-" * 80)
        
        top_20 = filtered_df.nlargest(20, 'FINAL_THG')[
            ['PREF IBKR', 'SOLIDITY_SCORE', 'CUR_YIELD', 'FINAL_THG',
             'SMA88_chg_norm', 'SMA268_chg_norm', 
             '1Y_High_diff_norm', '1Y_Low_diff_norm']
        ]
        
        for _, row in top_20.iterrows():
            print(f"{row['PREF IBKR']:<10} {row['SOLIDITY_SCORE']:>8.2f} {row['CUR_YIELD']:>10.2f} {row['FINAL_THG']:>10.2f} "
                  f"{row['SMA88_chg_norm']:>7.2f} {row['SMA268_chg_norm']:>7.2f} "
                  f"{row['1Y_High_diff_norm']:>7.2f} {row['1Y_Low_diff_norm']:>7.2f}")
        
        # Bottom 20 FINAL THG skorlarını göster
        print("\n=== En Düşük FINAL THG Skorları (Bottom 20) ===")
        print("PREF IBKR  SOLIDITY  CUR_YIELD   FINAL_THG   SMA88   SMA268   1Y_HIGH   1Y_LOW")
        print("-" * 80)
        
        bottom_20 = filtered_df.nsmallest(20, 'FINAL_THG')[
            ['PREF IBKR', 'SOLIDITY_SCORE', 'CUR_YIELD', 'FINAL_THG',
             'SMA88_chg_norm', 'SMA268_chg_norm', 
             '1Y_High_diff_norm', '1Y_Low_diff_norm']
        ]
        
        for _, row in bottom_20.iterrows():
            print(f"{row['PREF IBKR']:<10} {row['SOLIDITY_SCORE']:>8.2f} {row['CUR_YIELD']:>10.2f} {row['FINAL_THG']:>10.2f} "
                  f"{row['SMA88_chg_norm']:>7.2f} {row['SMA268_chg_norm']:>7.2f} "
                  f"{row['1Y_High_diff_norm']:>7.2f} {row['1Y_Low_diff_norm']:>7.2f}")
                
    except Exception as e:
        print(f"Bir hata oluştu: {e}")
        import traceback
        traceback.print_exc()

if __name__ == '__main__':
    main()