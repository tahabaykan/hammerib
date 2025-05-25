import json
from ib_insync import IB, Stock
import pandas as pd
import time
from ibkrtry_checkpoint import CheckpointManager
from datetime import datetime, timedelta
import math

def load_historical_data():
    """Sabit tarihsel verileri yükle"""
    try:
        historical_df = pd.read_csv('historical_data.csv')
        # Tüm kolonları general formata çevir
        for col in historical_df.columns:
            if historical_df[col].dtype in ['float64', 'int64']:
                historical_df[col] = historical_df[col].apply(lambda x: f"{x:.2f}" if pd.notnull(x) else x)
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
    
    for idx, row in df.iterrows():
        ticker = row['PREF IBKR']
        try:
            contract = get_qualified_contract(ticker, ib)
            if contract is None:
                continue

            # 1.5 yıllık veri çek
            bars = ib.reqHistoricalData(
                contract,
                endDateTime='',
                durationStr='2 Y',  # 1.5 yıllık veri 
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
                        
                        print(f"✓ {ticker} SMA değerleri: SMA88={sma88:.2f}, SMA268={sma268:.2f}")
                    except Exception as e:
                        print(f"! {ticker} SMA hesaplama hatası: {str(e)}")
                else:
                    print(f"! {ticker} için yeterli veri yok (Mevcut: {len(bars_df)}, Gerekli: 268)")
                
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
                
                print(f"✓ {ticker} için tüm veriler güncellendi")
            
            ib.sleep(0.5)  # Rate limiting
            
        except Exception as e:
            print(f"! {ticker} için hata: {str(e)}")
            continue
    
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
                print(f"! Tarih format hatası: {row['EX-DIV DATE']} (hisse: {row['PREF IBKR']})")
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
                
                print(f"✓ {row['PREF IBKR']} için temettü hesaplandı: TIME TO DIV={days_until_div}, Div adj.price={div_adj_price:.2f}")
            except Exception as e:
                print(f"! {row['PREF IBKR']} için div_adj_price hesaplama hatası: {str(e)}")
        except Exception as e:
            print(f"! {row.get('PREF IBKR', 'Bilinmeyen hisse')} temettü hesaplama hatası: {str(e)}")
    
    return df

def main():
    # IB bağlantı testi
    ib = IB()
    try:
        print("IBKR bağlantı testi başlıyor...")
        ib.connect('127.0.0.1', 4001, clientId=2981, timeout=10)
        print("Bağlantı başarılı!")
        print(f"TWS versiyon: {ib.client.serverVersion()}")
        print(f"Bağlantı zamanı: {ib.client.connTime}")
        
        # Basit bir API çağrısı yap
        accounts = ib.reqAccountSummary()
        print(f"Hesap sayısı: {len(accounts)}")
        
    except Exception as e:
        print(f"Bağlantı hatası: {e}")
    finally:
        if ib.isConnected():
            ib.disconnect()
            print("Bağlantı kapatıldı")
    
    # Sabit verileri yükle
    df = load_historical_data()
      # IB bağlantısı
    ib = IB()
    ib.connect('127.0.0.1', 4001, clientId=2981)
    ib.reqMarketDataType(3)
    
    try:
        # Verileri yükle ve güncelle
        df = update_price_data(df, ib)

        # TIME TO DIV ve Div adj.price kolonlarını hesapla
        df = calculate_div_metrics(df)
        
        # Sonuçları kaydet
        df.to_csv('sma_results.csv', 
                  index=False,
                  float_format='%.2f',  # Tüm sayısal değerler için 2 decimal
                  sep=',',
                  encoding='utf-8-sig')
        
        print("\nGüncellenmiş veriler kaydedildi.")
        
    except Exception as e:
        print(f"Hata: {str(e)}")
    finally:
        if ib.isConnected():
            ib.disconnect()
            print("TWS bağlantısı kapatıldı")

if __name__ == "__main__":
    main()
