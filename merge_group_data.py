import pandas as pd

def merge_group_data():
    print("Mastermind Grup verilerini CSV dosyalarına aktarma işlemi başlatılıyor...")
    
    # 1. Historical veri seti için işlem
    try:
        # CSV dosyalarını yükle
        print("Historical veri setleri yükleniyor...")
        
        # Ana veri dosyası (volume verileri ile)
        final_thg = pd.read_csv('final_thg_results.csv')
        print(f"final_thg_results.csv yüklendi: {len(final_thg)} satır")
        
        # Grup bilgisi dosyası
        mastermind_hist = pd.read_csv('mastermind_historical_results.csv')
        print(f"mastermind_historical_results.csv yüklendi: {len(mastermind_hist)} satır")
        
        # Ortak sütun belirleme - genellikle ticker/sembol sütunu
        # İki dosyada da 'PREF IBKR' sütunu olduğunu varsayıyoruz
        # Eğer farklı isimlerde ise burası değiştirilmeli
        
        # final_thg dosyasındaki ticker sütunu adı
        ticker_col_thg = 'PREF IBKR' if 'PREF IBKR' in final_thg.columns else None
        
        if ticker_col_thg is None:
            # Olası alternatif sütun adları kontrol et
            for col in ['Symbol', 'TICKER', 'Ticker', 'ticker', 'symbol']:
                if col in final_thg.columns:
                    ticker_col_thg = col
                    break
        
        # mastermind_hist dosyasındaki ticker sütunu adı
        ticker_col_hist = 'Symbol' if 'Symbol' in mastermind_hist.columns else None
        
        if ticker_col_hist is None:
            # Olası alternatif sütun adları kontrol et
            for col in ['PREF IBKR', 'TICKER', 'Ticker', 'ticker', 'symbol']:
                if col in mastermind_hist.columns:
                    ticker_col_hist = col
                    break
        
        # Eğer ticker sütunları bulunamadıysa
        if ticker_col_thg is None or ticker_col_hist is None:
            print("HATA: CSV dosyalarında eşleştirilecek ortak sütun bulunamadı.")
            print(f"final_thg_with_adv.csv sütunları: {final_thg.columns.tolist()}")
            print(f"mastermind_historical_results.csv sütunları: {mastermind_hist.columns.tolist()}")
            return
        
        print(f"Eşleştirme için kullanılacak sütunlar: {ticker_col_thg} (final_thg) ve {ticker_col_hist} (mastermind_hist)")
        
        # Grup verilerini al
        mastermind_hist_group = mastermind_hist[[ticker_col_hist, 'Group']]
        
        # Verileri birleştir
        final_thg_with_group = pd.merge(
            final_thg, 
            mastermind_hist_group,
            how='left',
            left_on=ticker_col_thg,
            right_on=ticker_col_hist
        )
        
        # Eğer farklı isimlerde sütunlar kullanıldıysa, gereksiz sütunu kaldır
        if ticker_col_thg != ticker_col_hist and ticker_col_hist in final_thg_with_group.columns:
            final_thg_with_group = final_thg_with_group.drop(columns=[ticker_col_hist])
        
        # Gruplara göre hacim ve diğer özelliklerin ortalama/medyan değerlerini hesapla
        print("\nHer grup için istatistikler hesaplanıyor...")
        group_stats = final_thg_with_group.groupby('Group').agg({
            'FINAL_THG': ['mean', 'median', 'count'],
            'AVG_ADV': ['mean', 'median'],
            'SOLIDITY_SCORE': ['mean', 'median']
        }).reset_index()
        
        # Grup istatistiklerini göster
        print("\n=== GRUP İSTATİSTİKLERİ ===")
        print(group_stats.to_string(index=False))
        
        # Yeni CSV dosyasına kaydet
        final_thg_with_group.to_csv('mastermind_histport.csv', index=False)
        print(f"mastermind_histport.csv dosyası oluşturuldu: {len(final_thg_with_group)} satır")
        
        # Eksik grup bilgisi olanları kontrol et
        missing_groups = final_thg_with_group[final_thg_with_group['Group'].isna()]
        if len(missing_groups) > 0:
            print(f"UYARI: {len(missing_groups)} hisse için grup bilgisi bulunamadı.")
            print(f"Eksik grup bilgisi olan ilk 5 sembol: {missing_groups[ticker_col_thg].head(5).tolist()}")
            
            # Eksik grup verisi olan semboller için en yakın grup ataması yapılabilir
            # Basit bir yöntem olarak en büyük gruba atanabilir
            if len(missing_groups) > 0 and len(group_stats) > 0:
                largest_group = group_stats.sort_values(by=('FINAL_THG', 'count'), ascending=False)['Group'].iloc[0]
                print(f"Eksik grup verisi olan hisseler '{largest_group}' grubuna atanacak")
                final_thg_with_group['Group'] = final_thg_with_group['Group'].fillna(largest_group)
                
                # Güncellenmiş dosyayı tekrar kaydet
                final_thg_with_group.to_csv('mastermind_histport.csv', index=False)
                print(f"Güncellenmiş mastermind_histport.csv dosyası oluşturuldu")
        
    except Exception as e:
        print(f"Historical veri işlenirken hata oluştu: {e}")
    
    # 2. EXTLT veri seti için işlem
    try:
        # CSV dosyalarını yükle
        print("\nEXTLT veri setleri yükleniyor...")
        
        # Ana veri dosyası
        final_extlt = pd.read_csv('final_extlt.csv')
        print(f"final_extlt.csv yüklendi: {len(final_extlt)} satır")
        
        # Grup bilgisi dosyası
        mastermind_extlt = pd.read_csv('mastermind_extlt_results.csv')
        print(f"mastermind_extlt_results.csv yüklendi: {len(mastermind_extlt)} satır")
        
        # Ortak sütun belirleme
        # final_extlt dosyasındaki ticker sütunu adı
        ticker_col_extlt_file = 'PREF IBKR' if 'PREF IBKR' in final_extlt.columns else None
        
        if ticker_col_extlt_file is None:
            # Olası alternatif sütun adları kontrol et
            for col in ['Symbol', 'TICKER', 'Ticker', 'ticker', 'symbol']:
                if col in final_extlt.columns:
                    ticker_col_extlt_file = col
                    break
        
        # mastermind_extlt dosyasındaki ticker sütunu adı
        ticker_col_extlt_results = 'Symbol' if 'Symbol' in mastermind_extlt.columns else None
        
        if ticker_col_extlt_results is None:
            # Olası alternatif sütun adları kontrol et
            for col in ['PREF IBKR', 'TICKER', 'Ticker', 'ticker', 'symbol']:
                if col in mastermind_extlt.columns:
                    ticker_col_extlt_results = col
                    break
        
        # Eğer ticker sütunları bulunamadıysa
        if ticker_col_extlt_file is None or ticker_col_extlt_results is None:
            print("HATA: EXTLT CSV dosyalarında eşleştirilecek ortak sütun bulunamadı.")
            print(f"final_extlt_with_adv.csv sütunları: {final_extlt.columns.tolist()}")
            print(f"mastermind_extlt_results.csv sütunları: {mastermind_extlt.columns.tolist()}")
            return
        
        print(f"Eşleştirme için kullanılacak sütunlar: {ticker_col_extlt_file} (final_extlt) ve {ticker_col_extlt_results} (mastermind_extlt)")
        
        # Grup verilerini al
        mastermind_extlt_group = mastermind_extlt[[ticker_col_extlt_results, 'Group']]
        
        # Verileri birleştir
        final_extlt_with_group = pd.merge(
            final_extlt, 
            mastermind_extlt_group,
            how='left',
            left_on=ticker_col_extlt_file,
            right_on=ticker_col_extlt_results
        )
        
        # Eğer farklı isimlerde sütunlar kullanıldıysa, gereksiz sütunu kaldır
        if ticker_col_extlt_file != ticker_col_extlt_results and ticker_col_extlt_results in final_extlt_with_group.columns:
            final_extlt_with_group = final_extlt_with_group.drop(columns=[ticker_col_extlt_results])
        
        # Gruplara göre hacim ve diğer özelliklerin ortalama/medyan değerlerini hesapla
        print("\nHer grup için istatistikler hesaplanıyor...")
        group_stats = final_extlt_with_group.groupby('Group').agg({
            'FINAL_THG': ['mean', 'median', 'count'],
            'AVG_ADV': ['mean', 'median'],
            'SOLIDITY_SCORE': ['mean', 'median']
        }).reset_index()
        
        # Grup istatistiklerini göster
        print("\n=== GRUP İSTATİSTİKLERİ ===")
        print(group_stats.to_string(index=False))
        
        # Yeni CSV dosyasına kaydet
        final_extlt_with_group.to_csv('mastermind_extltport.csv', index=False)
        print(f"mastermind_extltport.csv dosyası oluşturuldu: {len(final_extlt_with_group)} satır")
        
        # Eksik grup bilgisi olanları kontrol et
        missing_groups = final_extlt_with_group[final_extlt_with_group['Group'].isna()]
        if len(missing_groups) > 0:
            print(f"UYARI: {len(missing_groups)} hisse için grup bilgisi bulunamadı.")
            print(f"Eksik grup bilgisi olan ilk 5 sembol: {missing_groups[ticker_col_extlt_file].head(5).tolist()}")
            
            # Eksik grup verisi olan semboller için en yakın grup ataması yapılabilir
            # Basit bir yöntem olarak en büyük gruba atanabilir
            if len(missing_groups) > 0 and len(group_stats) > 0:
                largest_group = group_stats.sort_values(by=('FINAL_THG', 'count'), ascending=False)['Group'].iloc[0]
                print(f"Eksik grup verisi olan hisseler '{largest_group}' grubuna atanacak")
                final_extlt_with_group['Group'] = final_extlt_with_group['Group'].fillna(largest_group)
                
                # Güncellenmiş dosyayı tekrar kaydet
                final_extlt_with_group.to_csv('mastermind_extltport.csv', index=False)
                print(f"Güncellenmiş mastermind_extltport.csv dosyası oluşturuldu")
        
    except Exception as e:
        print(f"EXTLT veri işlenirken hata oluştu: {e}")
    
    print("\nİşlem tamamlandı.")

if __name__ == "__main__":
    merge_group_data() 