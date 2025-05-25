from ib_insync import IB, Stock
import pandas as pd
import numpy as np
import time
from datetime import datetime, timedelta
import os
import sys
# yfinance import removed - using IBKR for prices and Finviz for market cap
import requests
from bs4 import BeautifulSoup

# IBKR TWS API'ye bağlan
ib = IB()
ib.connect('127.0.0.1', 4001, clientId=189)  # Farklı bir clientId kullan

# Gecikmeli veri modunu etkinleştir
ib.reqMarketDataType(3)

# Ana CSV'den CMON tickerları oku - gelişmiş hata yönetimi ile
try:
    # Önce CSV'nin ilk birkaç satırını kontrol et
    df_test = pd.read_csv('sma_results.csv', nrows=5)
    
    # Eğer tüm veriler tek kolonda ise, virgülle ayır
    if len(df_test.columns) == 1:
        df_main = pd.read_csv('sma_results.csv', 
                            sep=None,  # otomatik ayraç tespiti
                            engine='python',  # daha esnek okuma motoru
                            encoding='utf-8-sig')  # UTF-8 BOM desteği
    else:
        df_main = pd.read_csv('sma_results.csv',
                            encoding='utf-8-sig')
    
    # CMON kolonu var mı kontrol et
    if 'CMON' not in df_main.columns:
        raise ValueError("CMON kolonu bulunamadı!")
    
    # Boş olmayan CMON değerlerini al
    common_tickers = df_main['CMON'].dropna().unique().tolist()
    
    print(f"Toplam {len(common_tickers)} adet common stock bulundu.")
    print("İlk 5 ticker:", common_tickers[:5])

except FileNotFoundError:
    print("sma_results.csv dosyası bulunamadı!")
    print("Lütfen dosyanın aşağıdaki konumda olduğundan emin olun:")
    print(os.path.abspath('sma_results.csv'))
    sys.exit(1)
except Exception as e:
    print(f"CSV okuma hatası: {e}")
    print("Dosya formatını kontrol edin.")
    sys.exit(1)

def get_qualified_contract(ticker):
    try:
        # Mevcut bağlantıları temizle
        ib.reqGlobalCancel()
        time.sleep(0.5)  # Temizleme için kısa bekleme
        
        base_contract = Stock(symbol=ticker, exchange='SMART', currency='USD')
        details = ib.reqContractDetails(base_contract)
        time.sleep(1)
        if details:
            return details[0].contract
        return None
    except Exception as e:
        print(f"{ticker} için hata: {e}")
        return None

def get_historical_data(contract, duration, endDateTime=''):
    try:
        # Her istek öncesi bekleyen istekleri temizle
        ib.reqGlobalCancel()
        time.sleep(0.5)
        
        bars = ib.reqHistoricalData(
            contract,
            endDateTime=endDateTime,
            durationStr=duration,
            barSizeSetting='1 day',
            whatToShow='TRADES',
            useRTH=True,
            timeout=5  # Timeout ekle
        )
        return pd.DataFrame(bars) if bars else None
    except Exception as e:
        print(f"Veri çekme hatası: {e}")
        # Hata durumunda tekrar bağlan
        if not ib.isConnected():
            print("Bağlantı koptu, yeniden bağlanılıyor...")
            ib.connect('127.0.0.1', 4001, clientId=189)
            time.sleep(1)
        return None

def get_historical_data_for_date(contract, date_str):
    """Belirli bir tarih için veri çek"""
    try:
        ib.reqGlobalCancel()
        time.sleep(0.5)
        
        bars = ib.reqHistoricalData(
            contract,
            endDateTime=date_str,
            durationStr='1 D',
            barSizeSetting='1 day',
            whatToShow='TRADES',
            useRTH=True,
            timeout=5
        )
        if bars:
            return bars[0].close
        return None
    except Exception as e:
        print(f"Tarih verisi çekme hatası: {e}")
        return None

# Yahoo Finance market cap function removed - using Finviz instead

def get_market_cap_from_finviz(ticker):
    """Finviz.com'dan market cap değerini çek"""
    try:
        # Finviz URL'si
        url = f"https://finviz.com/quote.ashx?t={ticker}"
        
        # HTTP isteği gönder
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
        }
        response = requests.get(url, headers=headers, timeout=10)
        
        if response.status_code != 200:
            print(f"! {ticker}: Finviz'den veri alınamadı (HTTP {response.status_code})")
            return None
            
        # HTML içeriğini parse et
        soup = BeautifulSoup(response.content, 'html.parser')
        
        # Market Cap değerini bul (snapshot tablosunda)
        for table_row in soup.select('table.snapshot-table2 tr'):
            cells = table_row.find_all('td')
            if len(cells) >= 2:
                if "Market Cap" in cells[0].text:
                    market_cap_text = cells[1].text.strip()
                    
                    # Değeri sayısal formata çevir
                    if 'B' in market_cap_text:
                        market_cap = float(market_cap_text.replace('B', ''))
                    elif 'M' in market_cap_text:
                        market_cap = float(market_cap_text.replace('M', '')) / 1000
                    else:
                        try:
                            market_cap = float(market_cap_text) / 1000000000  # Milyar dolara çevir
                        except ValueError:
                            print(f"! {ticker}: Finviz market cap değeri dönüştürülemedi: {market_cap_text}")
                            return None
                            
                    print(f"✓ Market Cap bulundu ({ticker}): {market_cap:.2f}B")
                    return market_cap
        
        print(f"! {ticker}: Finviz'de Market Cap bulunamadı")
        return None
        
    except Exception as e:
        print(f"! {ticker} için Finviz market cap verisi alma hatası: {str(e)}")
        return None

# Yahoo Finance last price function removed - using IBKR instead

def get_last_price_from_ibkr(ticker, contract=None):
    """IBKR Gateway'den last price değerini çek"""
    try:
        # Eğer kontrat verilmediyse yeni bir kontrat oluştur
        if contract is None:
            contract = get_qualified_contract(ticker)
            if not contract:
                print(f"! {ticker}: IBKR kontrat bulunamadı")
                return None
        
        # IBKR'den market verisi iste
        ib.reqMarketDataType(3)  # 3 = Delayed
        
        # Market verisi talebi
        ib.reqMktData(contract, '', False, False)
        
        # Veri gelmesini bekle
        start_time = time.time()
        max_wait = 10  # Maksimum 10 saniye bekle
        
        while time.time() - start_time < max_wait:
            ib.sleep(0.5)  # 0.5 saniye aralıklarla kontrol et
            
            # Veri geldi mi?
            ticker_data = ib.ticker(contract)
            
            # Farklı fiyat kaynaklarını kontrol et
            if ticker_data.last and ticker_data.last > 0:
                price = ticker_data.last
                ib.cancelMktData(contract)
                print(f"✓ {ticker}: ${price:.2f} (last)")
                return price
            elif ticker_data.close and ticker_data.close > 0:
                price = ticker_data.close
                ib.cancelMktData(contract)
                print(f"✓ {ticker}: ${price:.2f} (close)")
                return price
            
        # Süre doldu, veri alınamadı
        ib.cancelMktData(contract)
        print(f"! {ticker}: IBKR'den fiyat alınamadı (timeout)")
        return None
        
    except Exception as e:
        try:
            ib.cancelMktData(contract)
        except:
            pass
        print(f"! {ticker} için IBKR fiyat verisi alma hatası: {str(e)}")
        return None

# Sonuçları saklamak için liste
common_stock_results = []

for idx, ticker in enumerate(common_tickers):
    try:
        print(f"İşleniyor: {ticker} ({idx+1}/{len(common_tickers)})")
        
        # Her 50 işlemde bir bağlantıyı yenile
        if idx > 0 and idx % 50 == 0:
            print("\nBağlantı yenileniyor...")
            ib.disconnect()
            time.sleep(2)
            ib.connect('127.0.0.1', 4001, clientId=189)
            time.sleep(1)
            print("Bağlantı yenilendi.\n")
        
        contract = get_qualified_contract(ticker)
        if not contract:
            continue        # Son fiyatı IBKR'den, Market Cap'i Finviz'den al
        com_last_price = get_last_price_from_ibkr(ticker, contract)
        market_cap = get_market_cap_from_finviz(ticker)
        
        if com_last_price is None:
            print(f"! {ticker} için last price alınamadı")
            continue

        # 1 yıllık veri - IBKR'den
        df_1y = get_historical_data(contract, '1 Y')
        if df_1y is not None:
            com_52week_low = df_1y['low'].min()
            com_52week_high = df_1y['high'].max()
        else:
            com_52week_low = com_52week_high = None

        # 6 ay önceki fiyat - IBKR'den
        six_months_ago = (datetime.now() - timedelta(days=180)).strftime('%Y%m%d 23:59:59')
        df_6m = get_historical_data(contract, '1 D', endDateTime=six_months_ago)
        com_6m_price = df_6m['close'].iloc[0] if df_6m is not None else None

        # 3 ay önceki fiyat - IBKR'den
        three_months_ago = (datetime.now() - timedelta(days=90)).strftime('%Y%m%d 23:59:59')
        df_3m = get_historical_data(contract, '1 D', endDateTime=three_months_ago)
        com_3m_price = df_3m['close'].iloc[0] if df_3m is not None else None

        # 5 yıllık veri - IBKR'den
        df_5y = get_historical_data(contract, '5 Y')
        if df_5y is not None:
            com_5year_low = df_5y['low'].min()
            com_5year_high = df_5y['high'].max()
        else:
            com_5year_low = com_5year_high = None

        # 10 Şubat 2020 fiyatı
        feb_2020_price = get_historical_data_for_date(contract, '20200210 23:59:59')
        
        # 20 Mart 2020 fiyatı
        mar_2020_price = get_historical_data_for_date(contract, '20200320 23:59:59')        # CRDT SCORE'u ana DataFrame'den al
        crdt_score = df_main.loc[df_main['CMON'] == ticker, 'CRDT SCORE_'].iloc[0] if not df_main.empty else None

        # Sonuçları kaydet
        common_stock_results.append({
            'CMON': ticker,
            'COM_LAST_PRICE': com_last_price,  # IBKR'den
            'COM_52W_LOW': com_52week_low,     # IBKR'den
            'COM_52W_HIGH': com_52week_high,   # IBKR'den
            'COM_6M_PRICE': com_6m_price,      # IBKR'den
            'COM_3M_PRICE': com_3m_price,      # IBKR'den
            'COM_5Y_LOW': com_5year_low,       # IBKR'den
            'COM_5Y_HIGH': com_5year_high,     # IBKR'den
            'COM_MKTCAP': market_cap,          # Finviz'den
            'CRDT_SCORE': crdt_score,          # Ana CSV'den
            'COM_FEB2020_PRICE': feb_2020_price,
            'COM_MAR2020_PRICE': mar_2020_price
        })

        time.sleep(1)  # Rate limiting için kısa bekleme

    except Exception as e:
        print(f"{ticker} için hata oluştu: {e}")
        common_stock_results.append({
            'CMON': ticker,
            'COM_LAST_PRICE': None,
            'COM_52W_LOW': None,
            'COM_52W_HIGH': None,
            'COM_6M_PRICE': None,
            'COM_3M_PRICE': None,
            'COM_5Y_LOW': None,
            'COM_5Y_HIGH': None,
            'COM_MKTCAP': None,
            'CRDT_SCORE': None,
            'COM_FEB2020_PRICE': None,
            'COM_MAR2020_PRICE': None
        })

# Sonuçları DataFrame'e çevir
df_common = pd.DataFrame(common_stock_results)

# Debug için yeni kolonları kontrol et
print("\n=== Market Cap ve CRDT Score Değerleri ===")
print(df_common[['CMON', 'COM_LAST_PRICE', 'COM_MKTCAP', 'CRDT_SCORE']].head(10))

# Sonuçları kontrol et
print("\n=== Market Cap Değerleri (Güncellendi) ===")
print(df_common[['CMON', 'COM_LAST_PRICE', 'COM_MKTCAP']].head(10))

# Market Cap istatistikleri
print("\n=== Market Cap İstatistikleri ===")
print("Minimum Market Cap (milyar $):", df_common['COM_MKTCAP'].min())
print("Maximum Market Cap (milyar $):", df_common['COM_MKTCAP'].max())
print("Ortalama Market Cap (milyar $):", df_common['COM_MKTCAP'].mean())

# Ana DataFrame ile birleştir
df_final = df_main.merge(df_common, on='CMON', how='left')

def calculate_5y_low_score(chg_value, min_chg):
    """
    5Y LOW SKOR hesaplama
    Formula: IF(chg<0.15, (((chg + 1)/(min_chg + 1) - 1) * 25 * 1.5), (LN(chg/min_chg+1)+1)*25)
    """
    try:
        if pd.isna(chg_value) or pd.isna(min_chg):
            return None
        
        if chg_value < 0.15:
            return (((chg_value + 1)/(min_chg + 1) - 1) * 25 * 1.5)
        else:
            return (np.log(chg_value/min_chg + 1) + 1) * 25
    except:
        return 0

def calculate_5y_high_score(value, min_val):
    """5Y HIGH skor hesaplama"""
    try:
        if pd.isna(value) or pd.isna(min_val):
            return None
            
        if value <= -0.2:
            return (((value + 1) / (min_val + 1) - 1) * 25 * 1.25)
        elif value > -0.1:
            return (np.log(value/min_val + 1) + 1) * 25
        else:
            return (((value + 1) / (min_val + 1) - 1) * 25 * 1.1)
    except:
        return 0

def calculate_52w_low_score(value, min_val):
    """52 Week LOW skor hesaplama"""
    try:
        if pd.isna(value) or pd.isna(min_val):
            return None
            
        if value < 0.15:
            return (((value + 1) / (min_val + 1) - 1) * 25 * 1.5)
        else:
            return (np.log(value/min_val + 1) + 1) * 25
    except:
        return 0

def calculate_6m_3m_score(value, min_val):
    """6M ve 3M skor hesaplama"""
    try:
        if pd.isna(value) or pd.isna(min_val):
            return None
            
        if value < -0.22:
            return (((value + 1) / (min_val + 1) - 1) * 25 * 1.25)
        else:
            return (((value + 1) / (min_val + 1) - 1) * 25)
    except:
        return 0

def normalize_scores(series):
    """
    Skorları 1-100 arasında normalize et
    Formula: 1 + ((value - min) / (max - min)) * 99
    """
    if series.empty or series.isna().all():
        return pd.Series(index=series.index)
    
    min_val = series.min()
    max_val = series.max()
    
    if min_val == max_val:
        return pd.Series(1, index=series.index)
        
    return 1 + ((series - min_val) / (max_val - min_val)) * 99

def calculate_solidity(row):
    """
    Excel formülü:
    =EĞERHATA(EĞER(AL3="BB", 
        EĞER(AA3+AD3<80, (AF3*0.4 + AI3*0.32 + AG3*0.28)*1.02, (AF3*0.2 + AI3*0.42 + AG3*0.38)*1.02), 
        EĞER(AA3+AD3<80, AF3*0.4 + AI3*0.32 + AG3*0.28, AF3*0.2 + AI3*0.42 + AG3*0.38)), 0)
    """
    try:
        # Excel'deki AA3+AD3 = 6M + 3M değişim toplamı
        six_three_month_total = (float(row['Normalized_COM_6M']) if pd.notnull(row['Normalized_COM_6M']) else 0) + \
                              (float(row['Normalized_COM_3M']) if pd.notnull(row['Normalized_COM_3M']) else 0)
        
        # Excel'deki AF3 = Normalized_TOTAL_COM_CHG
        total_chg = float(row['Normalized_TOTAL_COM_CHG']) if pd.notnull(row['Normalized_TOTAL_COM_CHG']) else 0
        
        # Excel'deki AI3 = Normalized_MKTCAP
        mktcap = float(row['Normalized_MKTCAP']) if pd.notnull(row['Normalized_MKTCAP']) else 0
        
        # Excel'deki AG3 = Normalized_CRDT_SCORE
        crdt = float(row['Normalized_CRDT_SCORE']) if pd.notnull(row['Normalized_CRDT_SCORE']) else 0
        
        # Excel'deki AL3 = BOND_
        bond = str(row['BOND_']).strip() if pd.notnull(row['BOND_']) else ''

        # Excel formülünün birebir uygulanması
        if bond == 'BB':
            if six_three_month_total < 80:
                return (total_chg * 0.4 + mktcap * 0.32 + crdt * 0.28) * 1.02
            else:
                return (total_chg * 0.2 + mktcap * 0.42 + crdt * 0.38) * 1.02
        else:
            if six_three_month_total < 80:
                return total_chg * 0.4 + mktcap * 0.32 + crdt * 0.28
            else:
                return total_chg * 0.2 + mktcap * 0.42 + crdt * 0.38
    except:
        return 0

try:
    # 1. Önce tüm değişimleri hesapla
    print("\n=== Değişim Hesaplamaları ===")
    df_final['COM_5Y_LOW_CHG'] = (df_final['COM_LAST_PRICE'] - df_final['COM_5Y_LOW']) / df_final['COM_5Y_LOW']
    df_final['COM_5Y_HIGH_CHG'] = (df_final['COM_LAST_PRICE'] - df_final['COM_5Y_HIGH']) / df_final['COM_5Y_HIGH']
    df_final['COM_52W_LOW_CHG'] = (df_final['COM_LAST_PRICE'] - df_final['COM_52W_LOW']) / df_final['COM_52W_LOW']
    df_final['COM_52W_HIGH_CHG'] = (df_final['COM_LAST_PRICE'] - df_final['COM_52W_HIGH']) / df_final['COM_52W_HIGH']
    df_final['COM_6M_CHG'] = (df_final['COM_LAST_PRICE'] - df_final['COM_6M_PRICE']) / df_final['COM_6M_PRICE']
    df_final['COM_3M_CHG'] = (df_final['COM_LAST_PRICE'] - df_final['COM_3M_PRICE']) / df_final['COM_3M_PRICE']
    df_final['COM_FEB2020_CHG'] = (df_final['COM_LAST_PRICE'] - df_final['COM_FEB2020_PRICE']) / df_final['COM_FEB2020_PRICE']
    df_final['COM_MAR2020_CHG'] = (df_final['COM_LAST_PRICE'] - df_final['COM_MAR2020_PRICE']) / df_final['COM_MAR2020_PRICE']

    # 2. Her değişim için skor hesapla
    print("\n=== Skor Hesaplamaları ===")
    # 5Y LOW için
    min_5y_low = df_final['COM_5Y_LOW_CHG'].min()
    df_final['5Y_LOW_SKOR'] = df_final['COM_5Y_LOW_CHG'].apply(
        lambda x: calculate_5y_low_score(x, min_5y_low)
    )
    
    # 5Y HIGH için
    min_5y_high = df_final['COM_5Y_HIGH_CHG'].min()
    df_final['5Y_HIGH_SKOR'] = df_final['COM_5Y_HIGH_CHG'].apply(
        lambda x: calculate_5y_high_score(x, min_5y_high)
    )
    
    # 52W LOW için
    min_52w_low = df_final['COM_52W_LOW_CHG'].min()
    df_final['52W_LOW_SKOR'] = df_final['COM_52W_LOW_CHG'].apply(
        lambda x: calculate_52w_low_score(x, min_52w_low)
    )
    
    # 52W HIGH için
    min_52w_high = df_final['COM_52W_HIGH_CHG'].min()
    df_final['52W_HIGH_SKOR'] = df_final['COM_52W_HIGH_CHG'].apply(
        lambda x: calculate_5y_high_score(x, min_52w_high)
    )
    
    # 6M için
    min_6m = df_final['COM_6M_CHG'].min()
    df_final['COM_6M_SKOR'] = df_final['COM_6M_CHG'].apply(
        lambda x: calculate_6m_3m_score(x, min_6m)
    )
    
    # 3M için
    min_3m = df_final['COM_3M_CHG'].min()
    df_final['COM_3M_SKOR'] = df_final['COM_3M_CHG'].apply(
        lambda x: calculate_6m_3m_score(x, min_3m)
    )
    
    # FEB 2020 için
    min_feb2020 = df_final['COM_FEB2020_CHG'].min()
    df_final['FEB2020_SKOR'] = df_final['COM_FEB2020_CHG'].apply(
        lambda x: calculate_6m_3m_score(x, min_feb2020)
    )
    
    # MAR 2020 için
    min_mar2020 = df_final['COM_MAR2020_CHG'].min()
    df_final['MAR2020_SKOR'] = df_final['COM_MAR2020_CHG'].apply(
        lambda x: calculate_6m_3m_score(x, min_mar2020)
    )

    # 3. Her skoru normalize et - kolon isimlerini düzelt
    print("\n=== Normalizasyon İşlemleri ===")
    df_final['Normalized_5Y_LOW'] = normalize_scores(df_final['5Y_LOW_SKOR'])
    df_final['Normalized_5Y_HIGH'] = normalize_scores(df_final['5Y_HIGH_SKOR'])
    df_final['Normalized_52W_LOW'] = normalize_scores(df_final['52W_LOW_SKOR'])
    df_final['Normalized_52W_HIGH'] = normalize_scores(df_final['52W_HIGH_SKOR'])
    df_final['Normalized_COM_6M'] = normalize_scores(df_final['COM_6M_SKOR'])
    df_final['Normalized_COM_3M'] = normalize_scores(df_final['COM_3M_SKOR'])
    df_final['Normalized_FEB2020'] = normalize_scores(df_final['FEB2020_SKOR'])
    df_final['Normalized_MAR2020'] = normalize_scores(df_final['MAR2020_SKOR'])

    # Normalizasyon kontrol kısmında da kolon isimlerini düzelt
    print("\n=== Sonuçlar ===")
    column_mappings = {
        '5Y_LOW': 'Normalized_5Y_LOW',
        '5Y_HIGH': 'Normalized_5Y_HIGH',
        '52W_LOW': 'Normalized_52W_LOW',
        '52W_HIGH': 'Normalized_52W_HIGH',
        'COM_6M': 'Normalized_COM_6M',
        'COM_3M': 'Normalized_COM_3M',
        'FEB2020': 'Normalized_FEB2020',
        'MAR2020': 'Normalized_MAR2020'
    }

    for col, norm_name in column_mappings.items():
        print(f"\n{col} İstatistikleri:")
        
        # Değişim kolonu ismini düzelt
        if col.startswith('COM_'):
            chg_col = f'{col}_CHG'  # Zaten COM_ ile başlıyorsa ekstra ekleme
        else:
            chg_col = f'COM_{col}_CHG'  # COM_ ekle
            
        skor_col = f'{col}_SKOR'
        
        print(f"{chg_col} - Min: {df_final[chg_col].min():.4f}, Max: {df_final[chg_col].max():.4f}")
        print(f"{skor_col} - Min: {df_final[skor_col].min():.4f}, Max: {df_final[skor_col].max():.4f}")
        print(f"{norm_name} - Min: {df_final[norm_name].min():.4f}, Max: {df_final[norm_name].max():.4f}")

except Exception as e:
    print(f"Hata oluştu: {e}")
    raise e

# Sonuçları kaydet - doğru parametre adıyla
try:
    df_final.to_csv('common_stock_results.csv', 
                    index=False,
                    sep=',',
                    encoding='utf-8-sig',
                    float_format='%.6f',
                    lineterminator='\n',    
                    quoting=1)  # Tüm değerleri tırnak içine al

    print("\nSonuçlar 'common_stock_results.csv' dosyasına kaydedildi.")

    # Doğrulama için tekrar oku
    test_df = pd.read_csv('common_stock_results.csv', nrows=5)
    print("\n=== Doğrulama: CSV başarıyla kaydedildi ===")
    print(f"Kolonlar: {test_df.columns.tolist()}")
    print("\nİlk 5 satır:")
    print(test_df.head())

except Exception as e:
    print(f"CSV kaydetme hatası: {e}")
    
    # Yedek olarak Excel formatında kaydetmeyi dene
    try:
        df_final.to_excel('common_stock_results.xlsx', 
                         index=False,
                         float_format='%.6f')
        print("\nCSV kaydetme başarısız oldu, veriler Excel formatında kaydedildi.")
    except:
        print("\nVeriler kaydedilemedi!")

print("\n=== Common Stock Sonuçları ===")
print(df_common.head())

# Bağlantıyı kapat
ib.disconnect()