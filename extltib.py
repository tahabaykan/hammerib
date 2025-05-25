import json
from ib_insync import IB, Stock
import pandas as pd
import time
from ibkrtry_checkpoint import CheckpointManager
from datetime import datetime, timedelta
import math
import sys
import locale

# Karakter kodlama sorununu çöz
sys.stdout.reconfigure(encoding='utf-8', errors='replace')
try:
    # Daha genel bir yaklaşım kullan - birden fazla olasılığı dene
    for loc in ['Turkish_Turkey.1254', 'tr_TR.UTF-8', 'tr_TR', 'tr']:
        try:
            locale.setlocale(locale.LC_ALL, loc)
            print(f"Locale ayarlandı: {loc}")
            break
        except locale.Error:
            continue
    else:
        # Hiçbir Türkçe locale çalışmazsa, varsayılanı kullan
        locale.setlocale(locale.LC_ALL, '')
        print("Türkçe locale bulunamadı, varsayılan locale kullanılıyor")
except Exception as e:
    print(f"Locale ayarlaması başarısız: {e}")
    print("Program devam ediyor...")

def load_extlt_historical_data():
    """Sabit tarihsel verileri yükle"""
    try:
        historical_df = pd.read_csv('extlthistorical.csv')
        # Tüm kolonları general formata çevir
        for col in historical_df.columns:
            if historical_df[col].dtype in ['float64', 'int64']:
                historical_df[col] = historical_df[col].apply(lambda x: f"{x:.2f}" if pd.notnull(x) else x)
        print("Yüklenen veri satır sayısı:", len(historical_df))
        print("Kolonlar:", historical_df.columns.tolist())
        return historical_df
    except FileNotFoundError:
        return pd.DataFrame()

def get_qualified_contract(ticker, ib):  # ib parametresi eklendi
    """Otomatik exchange tanımı yapan fonksiyon"""
    try:
        base_contract = Stock(symbol=ticker, exchange='SMART', currency='USD')
        details = ib.reqContractDetails(base_contract)
        time.sleep(0.5)  # API rate limiting
        if details:
            return details[0].contract
        else:
            print(f"{ticker}: Contract details alınamadı")
            return None
    except Exception as e:
        print(f"{ticker} için hata: {e}")
        return None

def update_price_data(df, ib):
    """Son fiyatları ve tüm teknik verileri güncelle"""
    
    # Gerekli kolonları kontrol et ve yoksa oluştur
    required_columns = [
        'Last Price', 'Oct19_diff', 'Aug2022_diff',
        'SMA88', 'SMA268', 'SMA88 chg', 'SMA268 chg',
        '6M Low', '6M High', '1Y Low', '1Y High'
    ]
    
    for col in required_columns:
        if col not in df.columns:
            df[col] = None
            print(f"'{col}' kolonu oluşturuldu")
    
    # İşlemleri izlemek için sayaç oluştur
    total_symbols = len(df)
    processed = 0
    success = 0
    failed = 0
    
    for idx, row in df.iterrows():
        ticker = row['PREF IBKR']
        processed += 1
        
        try:
            # İlerleme durumunu göster
            progress = (processed / total_symbols) * 100
            print(f"İşleniyor: {ticker} ({processed}/{total_symbols}, %{progress:.1f})")
            
            contract = get_qualified_contract(ticker, ib)
            if contract is None:
                failed += 1
                continue

            # 2 yıllık veri çek
            bars = ib.reqHistoricalData(
                contract,
                endDateTime='',
                durationStr='2 Y',
                barSizeSetting='1 day',
                whatToShow='TRADES',
                useRTH=True
            )
            
            if bars and len(bars) > 0:
                # DataFrame'e çevir ve close değerlerini numeric yap
                bars_df = pd.DataFrame(bars)
                bars_df['close'] = pd.to_numeric(bars_df['close'], errors='coerce')
                
                last_price = float(bars_df['close'].iloc[-1])
                df.at[idx, 'Last Price'] = f"{last_price:.2f}"
                
                # SMA hesaplamaları - veri kontrolü ekle
                if len(bars_df) >= 268:
                    try:
                        # SMA değerlerini hesapla
                        sma88 = float(bars_df['close'].rolling(window=88).mean().iloc[-1])
                        sma268 = float(bars_df['close'].rolling(window=268).mean().iloc[-1])
                        
                        # SMA değerlerini kaydet
                        df.at[idx, 'SMA88'] = f"{sma88:.2f}"
                        df.at[idx, 'SMA268'] = f"{sma268:.2f}"
                        
                        # SMA değişim yüzdelerini hesapla
                        sma88_chg = ((last_price - sma88) / sma88) * 100
                        sma268_chg = ((last_price - sma268) / sma268) * 100
                        
                        df.at[idx, 'SMA88 chg'] = f"{sma88_chg:.2f}"
                        df.at[idx, 'SMA268 chg'] = f"{sma268_chg:.2f}"
                        
                        print(f"OK - {ticker} SMA değerleri: SMA88={sma88:.2f}, SMA268={sma268:.2f}")
                        success += 1
                    except Exception as e:
                        print(f"HATA - {ticker} SMA hesaplama hatası: {str(e)}")
                        failed += 1
                else:
                    print(f"HATA - {ticker} için yeterli veri yok (Mevcut: {len(bars_df)}, Gerekli: 268)")
                    failed += 1
                
                # 6 aylık high/low hesaplamaları
                six_month_data = bars_df.tail(180)  # Son 6 ay
                if not six_month_data.empty:
                    six_month_high = six_month_data['high'].max()
                    six_month_low = six_month_data['low'].min()
                    df.at[idx, '6M High'] = f"{six_month_high:.2f}"
                    df.at[idx, '6M Low'] = f"{six_month_low:.2f}"
                
                # 1 yıllık high/low hesaplamaları
                year_high = bars_df['high'].max()
                year_low = bars_df['low'].min()
                df.at[idx, '1Y High'] = f"{year_high:.2f}"
                df.at[idx, '1Y Low'] = f"{year_low:.2f}"
                
                # Aug2022 ve Oct19 farkları
                if pd.notnull(row.get('Aug2022_Price')):
                    df.at[idx, 'Aug2022_diff'] = f"{(last_price - float(row['Aug2022_Price'])):.2f}"
                if pd.notnull(row.get('Oct19_Price')):
                    df.at[idx, 'Oct19_diff'] = f"{(last_price - float(row['Oct19_Price'])):.2f}"
                
                print(f"OK - {ticker} için tüm veriler güncellendi")
            
            # Her 10 işlemde bir sonuçları kaydet
            if processed % 10 == 0:
                df.to_csv('extlt_results_temp.csv', 
                      index=False,
                      float_format='%.2f',
                      sep=',',
                      encoding='utf-8-sig')
                print(f"Ara kayıt yapıldı: {processed}/{total_symbols} işlem tamamlandı")
            
            ib.sleep(0.5)  # Rate limiting
            
        except Exception as e:
            print(f"HATA - {ticker} için işlem hatası: {str(e)}")
            failed += 1
            continue
    
    print(f"\nTüm işlemler tamamlandı: {success} başarılı, {failed} başarısız, toplam {processed} hisse")
    return df

def calculate_div_metrics(df):
    """Temettü gününe kalan süreyi ve düzeltilmiş fiyatı hesapla"""
    # Gerekli kolonları kontrol et ve yoksa oluştur
    if 'TIME TO DIV' not in df.columns:
        df['TIME TO DIV'] = None
    if 'Div adj.price' not in df.columns:
        df['Div adj.price'] = None
    
    # Bugünün tarihi
    today = datetime.now()
    
    for idx, row in df.iterrows():
        try:
            # EX-DIV DATE kolonunu kontrol et
            if pd.isna(row['EX-DIV DATE']) or not row['EX-DIV DATE']:
                continue
            
            # DIV AMOUNT kontrolü
            if pd.isna(row.get('DIV AMOUNT')) or not row.get('DIV AMOUNT'):
                continue
                
            # Last Price kontrolü
            if pd.isna(row.get('Last Price')) or not row.get('Last Price'):
                continue
                
            # Ex-Div tarihini parse et
            try:
                ex_div_date = datetime.strptime(row['EX-DIV DATE'], '%m/%d/%Y')
            except ValueError:
                print(f"HATA - Tarih format hatası: {row['EX-DIV DATE']} (hisse: {row['PREF IBKR']})")
                continue
                
            # 90 günlük döngüleri ekleyerek bir sonraki ex-div tarihini bul
            next_div_date = ex_div_date
            while next_div_date <= today:
                next_div_date += timedelta(days=90)
                
            # Kalan gün sayısını hesapla
            days_until_div = (next_div_date - today).days
            df.at[idx, 'TIME TO DIV'] = days_until_div
            
            # Div adj.price hesapla
            # Div adj.price = Last price - (((90-Time to Div)/90)*DIV AMOUNT)
            try:
                last_price = float(row['Last Price'])
                div_amount = float(row['DIV AMOUNT'])
                
                days_factor = (90 - days_until_div) / 90
                div_adj_price = last_price - (days_factor * div_amount)
                df.at[idx, 'Div adj.price'] = f"{div_adj_price:.2f}"
                
                print(f"OK - {row['PREF IBKR']} için temettü hesaplandı: TIME TO DIV={days_until_div}, Div adj.price={div_adj_price:.2f}")
            except Exception as e:
                print(f"HATA - {row['PREF IBKR']} için div_adj_price hesaplama hatası: {str(e)}")
        except Exception as e:
            print(f"HATA - {row.get('PREF IBKR', 'Bilinmeyen hisse')} temettü hesaplama hatası: {str(e)}")
    
    return df

def main():
    print("EXTLT Veri toplama işlemi başlıyor...")
    
    try:
        # Sabit verileri yükle
        df = load_extlt_historical_data()
        print(f"EXTLT tarihsel veri yüklendi: {len(df)} hisse")
        
        # IB bağlantısı
        print("\nIBKR bağlantısı kuruluyor...")
        ib = IB()
        try:
            ib.connect('127.0.0.1', 7496, clientId=2)  # Önce 7496 portunu dene
            ib.reqMarketDataType(3)  # Delayed data
            print("IBKR bağlantısı başarılı (port 7496)")
        except Exception as e1:
            print(f"Port 7496 bağlantı hatası: {e1}")
            print("4001 portu deneniyor...")
            ib.connect('127.0.0.1', 4001, clientId=2)
            ib.reqMarketDataType(3)  # Delayed data
            print("IBKR bağlantısı başarılı (port 4001)")
    except Exception as e:
        print(f"IBKR bağlantısı kurulamadı: {e}")
        print("Lütfen TWS veya IB Gateway uygulamasının açık olduğundan emin olun.")
        return
    
    try:
        # Verileri yükle ve güncelle
        print("\nFiyat verilerini güncelleme işlemi başlatılıyor...")
        df = update_price_data(df, ib)

        # TIME TO DIV ve Div adj.price kolonlarını hesapla
        print("\nTemettü metriklerini hesaplama işlemi başlatılıyor...")
        df = calculate_div_metrics(df)
        
        # Sonuçları kaydet
        df.to_csv('extlt_results.csv', 
                  index=False,
                  float_format='%.2f',  # Tüm sayısal değerler için 2 decimal
                  sep=',',
                  encoding='utf-8-sig')
        
        print("\nTüm EXTLT verileri başarıyla kaydedildi.")
        
    except Exception as e:
        print(f"İşlem sırasında hata oluştu: {str(e)}")
    finally:
        if ib.isConnected():
            ib.disconnect()
            print("IBKR bağlantısı kapatıldı")

if __name__ == "__main__":
    main()
