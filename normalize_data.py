import pandas as pd
import numpy as np
import time
from ib_insync import IB, Stock, util  # yfinance yerine ib_insync kullanacağız

def get_last_prices(symbols):
    """IBKR Gateway'den son fiyatları al"""
    last_prices = {}
    print("\nIBKR Gateway'den son fiyatlar alınıyor...")
    
    # IBKR'ye bağlan
    ib = IB()
    connected = False
    
    try:
        # TWS ve Gateway portlarını dene
        ports = [7496, 4001]  # TWS ve Gateway portları
        for port in ports:
            try:
                ib.connect('127.0.0.1', port, clientId=10, readonly=True)
                connected = True
                print(f"✓ IBKR {port} portu ile bağlantı başarılı!")
                break
            except Exception as e:
                print(f"! IBKR {port} bağlantı hatası: {e}")
        
        if not connected:
            print("! Hiçbir porta bağlanılamadı. TWS veya Gateway çalışıyor mu?")
            return {}
        
        # Delayed data (gerçek hesap yoksa)
        ib.reqMarketDataType(3)
        
        # Sembolleri gruplara böl (50 sembol/batch)
        batch_size = 50
        symbol_batches = [symbols[i:i+batch_size] for i in range(0, len(symbols), batch_size)]
        
        for batch_idx, symbol_batch in enumerate(symbol_batches):
            print(f"Batch {batch_idx+1}/{len(symbol_batches)} işleniyor ({len(symbol_batch)} sembol)")
            
            # Bu batch için kontratları ve istekleri hazırla
            contracts = {}
            
            for symbol in symbol_batch:
                try:
                    # Sembol geçerlilik kontrolü
                    if pd.isna(symbol) or symbol == '-':
                        continue
                    
                    # Kontrat oluştur
                    contract = Stock(symbol=symbol, exchange='SMART', currency='USD')
                    contracts[symbol] = contract
                    
                    # Market verisi iste
                    ib.reqMktData(contract, '', False, False)
                    
                    # Her 10 istekte bir kısa bekleme yap
                    if len(contracts) % 10 == 0:
                        time.sleep(0.2)
                        
                except Exception as e:
                    print(f"! {symbol} veri isteği hatası: {e}")
            
            # Verilerin gelmesini bekle
            time.sleep(2)  # İlk verilerin gelmesi için bekle
            
            # Toplanan verileri işle
            max_wait_time = 8  # Maksimum 8 saniye bekle
            start_time = time.time()
            collected = 0
            
            while time.time() - start_time < max_wait_time:
                # IBKR olaylarını işle
                ib.sleep(0.5)
                
                # Gelen verileri kontrol et ve kaydet
                for ticker in ib.tickers():
                    symbol = ticker.contract.symbol
                    
                    # Tercihli hisse kontrolü
                    if hasattr(ticker.contract, 'localSymbol') and ticker.contract.localSymbol:
                        if ' PR' in ticker.contract.localSymbol:
                            symbol = ticker.contract.localSymbol
                    
                    # Bu sembol batch'te var mı ve henüz kaydedilmemiş mi?
                    if symbol in symbol_batch and symbol not in last_prices:
                        # Son fiyat veya kapanış fiyatını kullan
                        if ticker.last and not pd.isna(ticker.last):
                            last_prices[symbol] = float(ticker.last)
                            collected += 1
                            print(f"✓ {symbol} son fiyat: ${ticker.last:.2f}")
                        elif ticker.close and not pd.isna(ticker.close):
                            last_prices[symbol] = float(ticker.close)
                            collected += 1
                            print(f"✓ {symbol} kapanış fiyatı: ${ticker.close:.2f}")
                
                # Tüm fiyatlar alındı mı?
                if collected >= len(symbol_batch) * 0.8:  # En az %80'i alınırsa yeterli say
                    break
                elif (time.time() - start_time) % 2 < 0.1:  # Her 2 saniyede bir durum raporu ver
                    print(f"İşleniyor... {collected}/{len(symbol_batch)} sembol alındı (%{collected/len(symbol_batch)*100:.1f})")
            
            # Market verisi aboneliklerini iptal et
            for contract in contracts.values():
                try:
                    ib.cancelMktData(contract)
                except:
                    pass
            
            # Batch'ler arası bekleme yap
            if batch_idx < len(symbol_batches) - 1:
                print(f"Rate limit'e takılmamak için 5 saniye bekleniyor...")
                time.sleep(5)
        
        # Eksik sembolleri raporla
        missing = [s for s in symbols if s not in last_prices and s != '-' and not pd.isna(s)]
        if missing:
            print(f"\n! {len(missing)} sembol için fiyat alınamadı:")
            if len(missing) <= 20:
                for symbol in missing:
                    print(f"- {symbol}")
            else:
                print(f"- İlk 20 sembol: {missing[:20]}...")
        
        print(f"\nToplam {len(last_prices)} sembol için fiyat alındı ({len(last_prices)/len([s for s in symbols if s != '-' and not pd.isna(s)])*100:.1f}%)")
        
    except Exception as e:
        print(f"Veri çekme hatası: {e}")
    
    finally:
        # Bağlantıyı her durumda kapat
        if ib.isConnected():
            ib.disconnect()
            print("IBKR bağlantısı kapatıldı.")
    
    return last_prices

# CSV dosyasını oku - dosya adını kontrol et
try:
    df = pd.read_csv('sma_results.csv', sep=',')  # CSV ayracını belirt
    print("CSV dosyası başarıyla okundu.")
    print("\nOkunan kolonlar:", df.columns.tolist())

    # IBKR Gateway'den son fiyatları al
    symbols = df['PREF IBKR'].dropna().unique().tolist()
    last_prices = get_last_prices(symbols)
    
    # Last Price kolonunu oluştur
    df['Last Price'] = df['PREF IBKR'].map(last_prices)
    
    # NaN değerleri kontrol et
    nan_prices = df[df['Last Price'].isna()]['PREF IBKR'].tolist()
    if nan_prices:
        print("\n! Fiyat alınamayan semboller:")
        for symbol in nan_prices[:20]:  # İlk 20'yi göster
            print(f"- {symbol}")
        if len(nan_prices) > 20:
            print(f"... ve {len(nan_prices)-20} sembol daha")

except Exception as e:
    print("CSV okuma hatası:", e)
    exit()

def normalize_values(series, lower_bound=-15, upper_bound=15, max_score=90, score_range=80):
    """
    Excel formülünü taklit eden normalize fonksiyonu
    
    Parameters:
    -----------
    series : pd.Series
        Normalize edilecek veri serisi
    lower_bound : float
        Alt sınır (default: -15)
    upper_bound : float
        Üst sınır (default: 15)
    max_score : float
        En yüksek puan (default: 90)
    score_range : float
        Puan aralığı (default: 80)
    """
    # -15 ile 15 arasındaki değerleri filtrele
    mask = (series >= lower_bound) & (series < upper_bound)
    filtered_series = series[mask]
    
    if filtered_series.empty:
        return pd.Series(index=series.index)
    
    # Min ve max değerleri bul
    min_val = filtered_series.min()
    max_val = filtered_series.max()
    
    # Normalize et (en negatif değer en yüksek puanı alacak)
    normalized = pd.Series(index=series.index)
    normalized[mask] = max_score - (
        (series[mask] - min_val) / (max_val - min_val) * score_range
    )
    
    return normalized

def normalize_6m_values(series, lower_bound=-8, upper_bound=15, max_score=90, score_range=80):
    """
    6 aylık değişimler için özel normalize fonksiyonu
    
    Parameters:
    -----------
    series : pd.Series
        Normalize edilecek veri serisi
    lower_bound : float
        Alt sınır (default: -8)
    upper_bound : float
        Üst sınır (default: 15)
    max_score : float
        En yüksek puan (default: 90)
    score_range : float
        Puan aralığı (default: 80)
    """
    # -8 ile 15 arasındaki değerleri filtrele
    mask = (series >= lower_bound) & (series < upper_bound)
    filtered_series = series[mask]
    
    if filtered_series.empty:
        return pd.Series(index=series.index)
    
    # Min ve max değerleri bul
    min_val = filtered_series.min()
    max_val = filtered_series.max()
    
    # Normalize et (en negatif değer en yüksek puanı alacak)
    normalized = pd.Series(index=series.index)
    normalized[mask] = max_score - (
        (series[mask] - min_val) / (max_val - min_val) * score_range
    )
    
    return normalized

try:
    # Div adj.price kolonunun varlığını kontrol et
    if 'Div adj.price' not in df.columns:
        print("! Uyarı: 'Div adj.price' kolonu bulunamadı, 'Last Price' kullanılacak.")
        price_column = 'Last Price'
    else:
        # Div adj.price kolonunu numeric hale getir
        df['Div adj.price'] = pd.to_numeric(df['Div adj.price'], errors='coerce')
        # NaN değerleri Last Price ile doldur
        df['Div adj.price'].fillna(df['Last Price'], inplace=True)
        price_column = 'Div adj.price'
        print(f"✓ Hesaplamalarda '{price_column}' kullanılıyor.")
    
    # Mevcut normalize işlemleri
    df['6M_Low_diff'] = df[price_column] - df['6M Low']
    df['6M_High_diff'] = df[price_column] - df['6M High']
    df['SMA88_chg_norm'] = normalize_values(df['SMA88 chg'])
    df['SMA268_chg_norm'] = normalize_values(df['SMA268 chg'])
    df['6M_Low_diff_norm'] = normalize_6m_values(df['6M_Low_diff'])
    df['6M_High_diff_norm'] = normalize_6m_values(df['6M_High_diff'])

    # Aug4 ve Oct19 için normalize işlemleri ekle
    # Önce fark hesapla
    df['Aug4_chg'] = df[price_column] - df['Aug2022_Price']
    df['Oct19_chg'] = df[price_column] - df['Oct19_Price']
    
    # Sonra normalize et (-8 ile 15 arası için)
    df['Aug4_chg_norm'] = normalize_6m_values(df['Aug4_chg'])
    df['Oct19_chg_norm'] = normalize_6m_values(df['Oct19_chg'])    # 1Y High ve Low diff'leri hesapla
    df['1Y_High_diff'] = df[price_column] - df['1Y High']
    df['1Y_Low_diff'] = df[price_column] - df['1Y Low']
    
    # 1Y değerleri için normalize (-8 ile 15 arası)
    df['1Y_High_diff_norm'] = normalize_6m_values(df['1Y_High_diff'])
    df['1Y_Low_diff_norm'] = normalize_6m_values(df['1Y_Low_diff'])

    # TLT içeren satırları filtrele
    before_filter = len(df)
    df = df[~df['PREF IBKR'].str.contains('TLT', na=False)]
    removed = before_filter - len(df)
    if removed > 0:
        print(f"\nUyarı: {removed} adet TLT satırı çıkarıldı.")
    
    # Sonuçları kontrol et
    print("\n=== 6 Aylık Puan Farkları ve Normalize Değerler ===")
    print(df[['PREF IBKR', price_column, '6M Low', '6M_Low_diff', '6M_Low_diff_norm',
              '6M High', '6M_High_diff', '6M_High_diff_norm']].head(10))

    print("\n=== Aug4 ve Oct19 Normalize Değerleri ===")
    print(df[['PREF IBKR', price_column, 
              'Aug2022_Price', 'Aug4_chg', 'Aug4_chg_norm',
              'Oct19_Price', 'Oct19_chg', 'Oct19_chg_norm']].head(10))

    print("\n=== 1Y High/Low Normalize Değerleri ===")
    print(df[['PREF IBKR', price_column, 
              '1Y High', '1Y_High_diff', '1Y_High_diff_norm',
              '1Y Low', '1Y_Low_diff', '1Y_Low_diff_norm']].head(10))    # En yüksek normalize değerlerine sahip hisseleri göster
    print("\n=== En Yüksek 6M Low Diff Normalize Değerler (Top 5) ===")
    print(df.nlargest(5, '6M_Low_diff_norm')[
        ['PREF IBKR', price_column, '6M Low', '6M_Low_diff', '6M_Low_diff_norm']
    ])

    print("\n=== En Yüksek 6M High Diff Normalize Değerler (Top 5) ===")
    print(df.nlargest(5, '6M_High_diff_norm')[
        ['PREF IBKR', price_column, '6M High', '6M_High_diff', '6M_High_diff_norm']
    ])

    print("\n=== En Yüksek Aug4 Normalize Değerler (Top 5) ===")
    print(df.nlargest(5, 'Aug4_chg_norm')[
        ['PREF IBKR', price_column, 'Aug2022_Price', 'Aug4_chg', 'Aug4_chg_norm']
    ])

    print("\n=== En Yüksek Oct19 Normalize Değerler (Top 5) ===")
    print(df.nlargest(5, 'Oct19_chg_norm')[
        ['PREF IBKR', price_column, 'Oct19_Price', 'Oct19_chg', 'Oct19_chg_norm']
    ])

    print("\n=== En Yüksek 1Y High Diff Normalize Değerler (Top 5) ===")
    print(df.nlargest(5, '1Y_High_diff_norm')[
        ['PREF IBKR', price_column, '1Y High', '1Y_High_diff', '1Y_High_diff_norm']
    ])

    print("\n=== En Yüksek 1Y Low Diff Normalize Değerler (Top 5) ===")
    print(df.nlargest(5, '1Y_Low_diff_norm')[
        ['PREF IBKR', price_column, '1Y Low', '1Y_Low_diff', '1Y_Low_diff_norm']
    ])

    # Sayısal kolonları float'a çevir
    numeric_columns = df.select_dtypes(include=[np.number]).columns
    for col in numeric_columns:
        df[col] = df[col].astype(float)

    # CSV dosyasını oluştur
    df.to_csv('normalized_results.csv', 
             index=False,
             float_format='%.6f',
             sep=',',                
             encoding='utf-8-sig',   
             lineterminator='\n',    
             quoting=1)              # Tüm değerleri tırnak içine al

    print("\nSonuçlar 'normalized_results.csv' dosyasına kaydedildi.")

except Exception as e:
    print("İşlem sırasında hata oluştu:", e)
    print("Hata detayı:", e.__class__.__name__)
    print("\nÇözüm önerileri:")
    print("1. CSV dosyasının formatını kontrol edin")
    print("2. IBKR TWS veya Gateway'in açık olduğunu kontrol edin")
    print("3. API bağlantılarına izin verildiğini kontrol edin")

input_files = [
    {"file_name": "normalized_results.csv", "output": "normalize_data_with_adv.csv"},
    {"file_name": "normalized_extlt.csv", "output": "normalize_extlt_with_adv.csv"}
]