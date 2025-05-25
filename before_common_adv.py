import pandas as pd
import datetime
import time
import os
import re
from ib_insync import IB, Stock, util, BarData  # yfinance yerine ib_insync kullanıyoruz

# Veri klasörünü kontrol et, yoksa oluştur
data_folder = os.path.join(os.path.dirname(__file__), "data")
if not os.path.exists(data_folder):
    os.makedirs(data_folder)

def connect_to_ibkr():
    """IBKR Gateway'e bağlanır"""
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
            return None
            
        # Delayed data (gerçek hesap yoksa)
        ib.reqMarketDataType(3)
        
        return ib
        
    except Exception as e:
        print(f"IBKR bağlantı hatası: {e}")
        return None

def get_average_volume(ib, ticker_symbol, period_days):
    """IBKR Gateway üzerinden belirli bir hisse için ortalama hacim verisini çeker"""
    try:
        # Kontrat oluştur
        contract = Stock(ticker_symbol, exchange='SMART', currency='USD')
        
        # Bitiş tarihi bugün
        end_date = datetime.datetime.now()
        # Başlangıç tarihi belirtilen gün sayısı kadar geriden
        start_date = end_date - datetime.timedelta(days=period_days)
        
        # IBKR'den günlük veriler al (TRADES 'barlar', '1 day' zaman dilimi)
        bars = ib.reqHistoricalData(
            contract=contract,
            endDateTime=end_date.strftime('%Y%m%d %H:%M:%S'),
            durationStr=f"{period_days + 5} D",  # Biraz fazla gün istiyoruz, çünkü hafta sonları ve tatiller veri olmayabilir
            barSizeSetting="1 day",
            whatToShow="TRADES",
            useRTH=True,  # Regular Trading Hours
            formatDate=1
        )
        
        # Eğer veri boşsa veya yetersizse
        if not bars or len(bars) < 3:  # En az 3 gün veri olsun
            print(f"  [UYARI] {ticker_symbol} için yeterli veri yok ({len(bars) if bars else 0} gün)")
            return None
        
        # Hacim verilerini al ve ortalama hesapla
        volumes = [bar.volume for bar in bars]
        avg_volume = sum(volumes) / len(volumes)
        
        return avg_volume
        
    except Exception as e:
        print(f"  [HATA] {ticker_symbol} için hacim verisi çekilirken problem: {e}")
        return None

def process_dataframe(ib, df, input_file_name, output_file_name):
    """IBKR Gateway kullanarak DataFrame'deki her hisse için hacim verilerini toplar"""
    # Sonuçları saklamak için yeni sütunlar ekle
    df['ADV_6M'] = None
    df['ADV_3M'] = None
    df['ADV_15D'] = None
    df['AVG_ADV'] = None  # Ortalama ADV kolonu

    # İlerlemeyi takip et
    total_stocks = len(df)
    success_count = 0
    error_count = 0

    print(f"\n{input_file_name} dosyasındaki hisseler için ortalama günlük hacim verileri çekiliyor...")
    print("---------------------------------------------")

    # Her hisse için hacim verilerini çek
    for i, row in df.iterrows():
        ticker = row['PREF IBKR']
        
        print(f"İşleniyor ({i+1}/{total_stocks}): {ticker}", end="")
        
        try:
            # 6 aylık ortalama günlük hacim
            adv_6m = get_average_volume(ib, ticker, 180)
            
            # 3 aylık ortalama günlük hacim
            adv_3m = get_average_volume(ib, ticker, 90)
            
            # 15 günlük ortalama günlük hacim
            adv_15d = get_average_volume(ib, ticker, 15)
            
            # Sonuçları dataframe'e ekle
            if adv_6m is not None:
                df.at[i, 'ADV_6M'] = int(adv_6m)
            if adv_3m is not None:
                df.at[i, 'ADV_3M'] = int(adv_3m)
            if adv_15d is not None:
                df.at[i, 'ADV_15D'] = int(adv_15d)
                
            # AVG_ADV hesapla (mevcut değerlerin ortalaması)
            adv_values = []
            if adv_6m is not None:
                adv_values.append(adv_6m)
            if adv_3m is not None:
                adv_values.append(adv_3m)
            if adv_15d is not None:
                adv_values.append(adv_15d)
                
            if adv_values:
                df.at[i, 'AVG_ADV'] = int(sum(adv_values) / len(adv_values))
                
            # Başarılı sonuç
            if adv_6m is not None and adv_3m is not None and adv_15d is not None:
                success_count += 1
                print(f" - Başarılı! ADV: 6M={int(adv_6m):,}, 3M={int(adv_3m):,}, 15D={int(adv_15d):,}, AVG={df.at[i, 'AVG_ADV']:,}")
            else:
                error_count += 1
                print(" - Kısmen başarılı veya başarısız")
            
            # API sınırlamalarını aşmamak için kısa bir bekleme süresi ekle
            time.sleep(0.5)
            
        except Exception as e:
            error_count += 1
            print(f" - HATA: {e}")
            continue

    # Sonuçları yeni bir CSV dosyasına kaydet
    df.to_csv(output_file_name, index=False)

    print(f"\n{input_file_name} dosyası işleme sonuçları:")
    print("---------------------------------------------")
    print(f"Toplam hisse sayısı: {total_stocks}")
    print(f"Başarıyla veri çekilen hisse sayısı: {success_count}")
    print(f"Hata alınan veya eksik veri olan hisse sayısı: {error_count}")
    print(f"Sonuçlar '{output_file_name}' dosyasına kaydedildi.")

    # Hacim istatistiklerini göster
    print(f"\n{input_file_name} Hacim İstatistikleri:")
    print("---------------------------------------------")
    print("6 Aylık Ortalama Günlük Hacim (ADV_6M):")
    print(df['ADV_6M'].describe())

    print("\n3 Aylık Ortalama Günlük Hacim (ADV_3M):")
    print(df['ADV_3M'].describe())

    print("\n15 Günlük Ortalama Günlük Hacim (ADV_15D):")
    print(df['ADV_15D'].describe())
    
    print("\nOrtalama ADV (AVG_ADV):")
    print(df['AVG_ADV'].describe())

    # En yüksek ve en düşük hacimli hisseler
    print(f"\n{input_file_name} En Yüksek Ortalama ADV'ye Sahip 5 Hisse:")
    top_volume = df.sort_values('AVG_ADV', ascending=False).head(5)
    print(top_volume[['PREF IBKR', 'CMON', 'ADV_6M', 'ADV_3M', 'ADV_15D', 'AVG_ADV']])

    print(f"\n{input_file_name} En Düşük Ortalama ADV'ye Sahip 5 Hisse (0 olmayan):")
    bottom_volume = df[df['AVG_ADV'] > 0].sort_values('AVG_ADV').head(5)
    print(bottom_volume[['PREF IBKR', 'CMON', 'ADV_6M', 'ADV_3M', 'ADV_15D', 'AVG_ADV']])
    
    return df, success_count, error_count

def main():
    # Dosyaları yükle
    print("Normalize edilmiş veri dosyaları yükleniyor...")
    
    input_files = [
        {"file_name": "normalized_results.csv", "output": "normalize_data_with_adv.csv"},
        {"file_name": "normalized_extlt.csv", "output": "normalize_extlt_with_adv.csv"}
    ]
    
    dataframes = []
    for file_info in input_files:
        file_name = file_info["file_name"]
        try:
            df = pd.read_csv(file_name)
            print(f"{file_name} dosyası başarıyla yüklendi: {len(df)} satır")
            dataframes.append({
                "df": df,
                "input": file_name,
                "output": file_info["output"]
            })
        except Exception as e:
            print(f"{file_name} dosyası yüklenirken hata: {e}")
    
    if not dataframes:
        print("Hiçbir normalize veri dosyası yüklenemedi. Program sonlandırılıyor.")
        return
    
    # IBKR'ye bağlan
    print("\nIBKR Gateway'e bağlanılıyor...")
    ib = connect_to_ibkr()

    if ib is None:
        print("IBKR bağlantısı başarısız oldu. Program sonlandırılıyor.")
        exit(1)
    
    # Her bir DataFrame'i işle
    total_success = 0
    total_error = 0
    processed_dfs = []
    
    for df_info in dataframes:
        processed_df, success, error = process_dataframe(
            ib, 
            df_info["df"], 
            df_info["input"], 
            df_info["output"]
        )
        processed_dfs.append(processed_df)
        total_success += success
        total_error += error
    
    # İki dataframe'i birleştir
    if len(processed_dfs) == 2:
        print("\nİki veri setini birleştirme işlemi başlatılıyor...")
        combined_df = pd.concat(processed_dfs, ignore_index=True)
        print(f"Birleştirilmiş veri boyutu: {len(combined_df)} satır")
        
        # Birleştirilmiş veriyi kaydet
        combined_output = "final_thg_with_avg_adv.csv"
        combined_df.to_csv(combined_output, index=False)
        print(f"Birleştirilmiş veri '{combined_output}' dosyasına kaydedildi.")
    
    # IBKR bağlantısını kapat
    if ib and ib.isConnected():
        ib.disconnect()
        print("\nIBKR bağlantısı kapatıldı.")
    
    print("\n---------------------------------------------")
    print("Tüm işlemler tamamlandı!")
    print(f"Toplam başarılı veri çekilen hisse sayısı: {total_success}")
    print(f"Toplam hata alınan veya eksik veri olan hisse sayısı: {total_error}")

if __name__ == '__main__':
    main()